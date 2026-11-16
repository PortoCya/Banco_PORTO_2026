"""
Registro de respostas do respondente — o coração do núcleo.

Numa única transação: SUBMISSAO + LINK_PESQUISA.usado_em + SNAPSHOT_NPS
(+ JOB_IA, se houver comentário). A IA nunca participa: só recebe o id depois
do commit.

Duplicidade (idempotência):
- chave_idempotencia já usada por uma resposta VALIDA (reenvio do cliente);
- link NOMINAL já utilizado (token de uso único);
- link ABERTO com o cookie de "já respondeu" (verificado na rota).
A tentativa é gravada como BLOQUEADA_DUPLICADA e quem chama responde 409 sem
dizer qual regra barrou.
"""
import logging
import uuid
from dataclasses import dataclass
from typing import Optional

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.models import JobIa, LinkPesquisa, Pesquisa, Submissao, agora_utc
from app.services.nps import atualizar_snapshot_do_dia

logger = logging.getLogger(__name__)


class PesquisaNaoPublicada(Exception):
    pass


class RespostaDuplicada(Exception):
    pass


@dataclass(frozen=True)
class DadosResposta:
    nota_nps: int
    texto_comentario: Optional[str]
    chave_idempotencia: str
    fingerprint_dispositivo: Optional[str]
    endereco_ip: Optional[str]          # já pseudonimizado


@dataclass(frozen=True)
class RespostaRegistrada:
    submissao: Submissao
    tem_job_ia: bool


def registrar_resposta(
    db: Session, link: LinkPesquisa, dados: DadosResposta, ja_respondeu_cookie: bool
) -> RespostaRegistrada:
    try:
        return _registrar(db, link, dados, ja_respondeu_cookie)
    except IntegrityError:
        db.rollback()
        # Duas requisições com a mesma chave passaram juntas pela checagem e o
        # índice único deixou só uma entrar? Então esta é a duplicada.
        # Qualquer outra violação é erro de verdade e sobe como tal.
        if not _existe_valida(db, dados.chave_idempotencia):
            raise
        _gravar_bloqueada(db, link, dados)
        raise RespostaDuplicada()


def _existe_valida(db: Session, chave_idempotencia: str) -> bool:
    return db.execute(
        select(Submissao.id).where(
            Submissao.chave_idempotencia == chave_idempotencia, Submissao.status == "VALIDA"
        )
    ).first() is not None


def _registrar(
    db: Session, link: LinkPesquisa, dados: DadosResposta, ja_respondeu_cookie: bool
) -> RespostaRegistrada:
    # Trava a pesquisa: serializa respostas simultâneas da mesma pesquisa, o
    # que mantém o snapshot exato. (No SQLite o FOR UPDATE é ignorado.)
    pesquisa = db.execute(
        select(Pesquisa).where(Pesquisa.id == link.id_pesquisa).with_for_update()
    ).scalar_one()
    if pesquisa.status != "PUBLICADA":
        db.rollback()
        raise PesquisaNaoPublicada()

    duplicada = ja_respondeu_cookie or _existe_valida(db, dados.chave_idempotencia)

    if not duplicada:
        # UPDATE condicional: entre duas requisições com o mesmo token NOMINAL,
        # só uma consegue marcar o uso.
        marcou = db.execute(
            update(LinkPesquisa)
            .where(LinkPesquisa.id == link.id, LinkPesquisa.usado_em.is_(None))
            .values(usado_em=agora_utc())
        ).rowcount
        if link.tipo == "NOMINAL" and marcou == 0:
            duplicada = True

    if duplicada:
        db.rollback()
        _gravar_bloqueada(db, link, dados)
        raise RespostaDuplicada()

    submissao = _nova_submissao(link, dados, "VALIDA")
    db.add(submissao)
    db.flush()   # a submissão precisa existir antes do job que aponta para ela
    tem_comentario = bool(dados.texto_comentario and dados.texto_comentario.strip())
    if tem_comentario:
        # Comentário vazio não gera job: a IA nem é chamada
        db.add(JobIa(id_submissao=submissao.id, status="NA_FILA", proxima_tentativa_em=agora_utc()))
    atualizar_snapshot_do_dia(db, pesquisa.id)
    db.commit()
    return RespostaRegistrada(submissao, tem_comentario)


def _nova_submissao(link: LinkPesquisa, dados: DadosResposta, status: str) -> Submissao:
    return Submissao(
        id=uuid.uuid4(),
        id_pesquisa=link.id_pesquisa,
        id_link_pesquisa=link.id,
        nota_nps=dados.nota_nps,
        texto_comentario=dados.texto_comentario or None,
        chave_idempotencia=dados.chave_idempotencia,
        fingerprint_dispositivo=dados.fingerprint_dispositivo,
        endereco_ip=dados.endereco_ip,
        status=status,
    )


def _gravar_bloqueada(db: Session, link: LinkPesquisa, dados: DadosResposta) -> None:
    """Fora do NPS e sem job de IA; fica só o registro da tentativa."""
    try:
        db.add(_nova_submissao(link, dados, "BLOQUEADA_DUPLICADA"))
        db.commit()
    except Exception:
        # O registro da tentativa é acessório: se falhar, o 409 sai do mesmo jeito
        db.rollback()
        logger.warning("Não foi possível registrar a tentativa duplicada")

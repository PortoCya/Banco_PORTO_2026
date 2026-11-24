"""
Endpoints — Pesquisas, links, NPS e exportação.
"""
import csv
import io
import secrets
import uuid
from datetime import date
from typing import Iterator, List, Optional

from fastapi import APIRouter, Depends, Query, Response, status
from fastapi.responses import StreamingResponse
from sqlalchemy import delete, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import Paginacao, paginacao, requer_papel
from app.core.database import SessionLocal, get_db
from app.core.errors import ConflictError, ForbiddenError, InvalidInputError, NotFoundError
from app.models.models import (
    AnaliseFeedback, JobIa, LinkPesquisa, LogExportacao, Pesquisa, SnapshotNps, Submissao, Usuario,
)
from app.schemas.schemas import (
    LinkPesquisaCreate, LinkPesquisaResponse, NpsResponse, PesquisaCreate,
    PesquisaResponse, PesquisaUpdate, RespostaResponse, SnapshotNpsResponse, StatusPesquisa,
)
from app.services.auditoria import estado_pesquisa, registrar_auditoria
from app.services.analises import ultima_sequencia
from app.services.nps import faixa_nps, filtrar_periodo, nps_da_pesquisa
from app.services.pii import texto_anonimizado

router = APIRouter(tags=["Pesquisas"])

_admin = requer_papel("ADMIN")
_leitura = requer_papel("ADMIN", "ANALYST")


def _buscar_pesquisa(db: Session, id_pesquisa: uuid.UUID, travar: bool = False) -> Pesquisa:
    consulta = select(Pesquisa).where(Pesquisa.id == id_pesquisa)
    if travar:
        consulta = consulta.with_for_update()
    pesquisa = db.execute(consulta).scalar_one_or_none()
    if pesquisa is None:
        raise NotFoundError("Pesquisa não encontrada.")
    return pesquisa


# ══════════════════════════════════════════════════════════════════
# Cadastro e versionamento
# ══════════════════════════════════════════════════════════════════

@router.post("/pesquisas", response_model=PesquisaResponse, status_code=status.HTTP_201_CREATED,
             summary="Criar pesquisa (nasce como RASCUNHO)")
def criar_pesquisa(payload: PesquisaCreate, db: Session = Depends(get_db), admin: Usuario = Depends(_admin)):
    """**Códigos:** 201 | 401 | 403 | 422"""
    pesquisa = Pesquisa(
        id=uuid.uuid4(),
        titulo=payload.titulo,
        texto_pergunta_nps=payload.texto_pergunta_nps,
        texto_pergunta_aberta=payload.texto_pergunta_aberta or None,
        status="RASCUNHO",
        numero_versao=1,
        criado_por=admin.id,
    )
    db.add(pesquisa)
    registrar_auditoria(db, admin, "CRIAR_PESQUISA", "PESQUISA", pesquisa.id,
                        estado_depois=estado_pesquisa(pesquisa))
    db.commit()
    return pesquisa


@router.get("/pesquisas", response_model=List[PesquisaResponse], summary="Listar pesquisas",
            dependencies=[Depends(_leitura)])
def listar_pesquisas(
    status_pesquisa: Optional[StatusPesquisa] = Query(None, alias="status"),
    pag: Paginacao = Depends(paginacao),
    db: Session = Depends(get_db),
):
    """**Códigos:** 200 | 401 | 403 | 422"""
    consulta = select(Pesquisa)
    if status_pesquisa:
        consulta = consulta.where(Pesquisa.status == status_pesquisa)
    consulta = consulta.order_by(Pesquisa.criada_em.desc(), Pesquisa.id).offset(pag.skip).limit(pag.limit)
    return db.execute(consulta).scalars().all()


@router.get("/pesquisas/{id_pesquisa}", response_model=PesquisaResponse, summary="Detalhar pesquisa",
            dependencies=[Depends(_leitura)])
def buscar_pesquisa(id_pesquisa: uuid.UUID, db: Session = Depends(get_db)):
    """**Códigos:** 200 | 401 | 403 | 404 | 422"""
    return _buscar_pesquisa(db, id_pesquisa)


@router.patch("/pesquisas/{id_pesquisa}", response_model=PesquisaResponse,
              summary="Editar pesquisa (com respostas, cria nova versão)")
def atualizar_pesquisa(
    id_pesquisa: uuid.UUID,
    payload: PesquisaUpdate,
    db: Session = Depends(get_db),
    admin: Usuario = Depends(_admin),
):
    """
    Pesquisa sem respostas é alterada no lugar. Pesquisa que já tem respostas
    **nunca é sobrescrita**: nasce uma nova PESQUISA (RASCUNHO) com
    `id_pesquisa_pai` apontando para a original, que continua como está.

    **Códigos:** 200 | 401 | 403 | 404 | 409 (arquivada ou já possui versão mais nova) | 422
    """
    # Trava a linha: uma resposta não pode chegar entre a checagem e a edição
    pesquisa = _buscar_pesquisa(db, id_pesquisa, travar=True)
    if pesquisa.status == "ARQUIVADA":
        raise ConflictError("Pesquisa arquivada não pode ser editada.")

    mudancas = payload.model_dump(exclude_unset=True)
    if "texto_pergunta_aberta" in mudancas:
        mudancas["texto_pergunta_aberta"] = mudancas["texto_pergunta_aberta"] or None

    tem_respostas = db.execute(
        select(Submissao.id).where(Submissao.id_pesquisa == pesquisa.id).limit(1)
    ).first() is not None

    if not tem_respostas:
        antes = estado_pesquisa(pesquisa)
        for campo, valor in mudancas.items():
            setattr(pesquisa, campo, valor)
        registrar_auditoria(db, admin, "EDITAR_PESQUISA", "PESQUISA", pesquisa.id,
                            estado_antes=antes, estado_depois=estado_pesquisa(pesquisa))
        db.commit()
        return pesquisa

    ja_tem_filha = db.execute(
        select(Pesquisa.id).where(Pesquisa.id_pesquisa_pai == pesquisa.id).limit(1)
    ).first() is not None
    if ja_tem_filha:
        raise ConflictError("Esta pesquisa já possui uma versão mais nova. Edite a versão mais recente.")

    nova = Pesquisa(
        id=uuid.uuid4(),
        titulo=mudancas.get("titulo", pesquisa.titulo),
        texto_pergunta_nps=mudancas.get("texto_pergunta_nps", pesquisa.texto_pergunta_nps),
        texto_pergunta_aberta=mudancas.get("texto_pergunta_aberta", pesquisa.texto_pergunta_aberta),
        status="RASCUNHO",
        numero_versao=pesquisa.numero_versao + 1,
        id_pesquisa_pai=pesquisa.id,
        criado_por=admin.id,
    )
    db.add(nova)
    registrar_auditoria(db, admin, "VERSIONAR_PESQUISA", "PESQUISA", nova.id,
                        estado_antes=estado_pesquisa(pesquisa), estado_depois=estado_pesquisa(nova))
    db.commit()
    return nova


@router.delete("/pesquisas/{id_pesquisa}", status_code=status.HTTP_204_NO_CONTENT,
               summary="Excluir pesquisa e seus vínculos")
def excluir_pesquisa(
    id_pesquisa: uuid.UUID,
    db: Session = Depends(get_db),
    admin: Usuario = Depends(_admin),
):
    """**Códigos:** 204 | 401 | 403 | 404 | 422"""
    pesquisa = _buscar_pesquisa(db, id_pesquisa, travar=True)
    antes = estado_pesquisa(pesquisa)

    # Desvincula eventuais versões filhas para não violar FK auto-referenciada
    db.execute(
        update(Pesquisa).where(Pesquisa.id_pesquisa_pai == id_pesquisa).values(id_pesquisa_pai=None)
    )

    ids_submissoes = list(
        db.execute(select(Submissao.id).where(Submissao.id_pesquisa == id_pesquisa)).scalars()
    )
    if ids_submissoes:
        db.execute(delete(AnaliseFeedback).where(AnaliseFeedback.id_submissao.in_(ids_submissoes)))
        db.execute(delete(JobIa).where(JobIa.id_submissao.in_(ids_submissoes)))
        db.execute(delete(Submissao).where(Submissao.id_pesquisa == id_pesquisa))

    db.execute(delete(LinkPesquisa).where(LinkPesquisa.id_pesquisa == id_pesquisa))
    db.execute(delete(SnapshotNps).where(SnapshotNps.id_pesquisa == id_pesquisa))
    db.execute(delete(LogExportacao).where(LogExportacao.id_pesquisa == id_pesquisa))

    registrar_auditoria(db, admin, "EXCLUIR_PESQUISA", "PESQUISA", pesquisa.id, estado_antes=antes)
    db.delete(pesquisa)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ══════════════════════════════════════════════════════════════════
# Ciclo de vida: RASCUNHO → PUBLICADA ⇄ PAUSADA → ARQUIVADA
# ══════════════════════════════════════════════════════════════════

_TRANSICOES = {
    "publicar": ("PUBLICADA", {"RASCUNHO", "PAUSADA"}),
    "pausar": ("PAUSADA", {"PUBLICADA"}),
    "arquivar": ("ARQUIVADA", {"RASCUNHO", "PUBLICADA", "PAUSADA"}),
}


def _mudar_status(db: Session, admin: Usuario, id_pesquisa: uuid.UUID, acao: str) -> Pesquisa:
    destino, origens = _TRANSICOES[acao]
    pesquisa = _buscar_pesquisa(db, id_pesquisa, travar=True)
    if pesquisa.status not in origens:
        raise ConflictError(f"Não é possível {acao} uma pesquisa com status {pesquisa.status}.")
    antes = estado_pesquisa(pesquisa)
    pesquisa.status = destino
    registrar_auditoria(db, admin, f"{acao.upper()}_PESQUISA", "PESQUISA", pesquisa.id,
                        estado_antes=antes, estado_depois=estado_pesquisa(pesquisa))
    db.commit()
    return pesquisa


@router.post("/pesquisas/{id_pesquisa}/publicar", response_model=PesquisaResponse, summary="Publicar pesquisa")
def publicar_pesquisa(id_pesquisa: uuid.UUID, db: Session = Depends(get_db), admin: Usuario = Depends(_admin)):
    """**Códigos:** 200 | 401 | 403 | 404 | 409 (transição inválida) | 422"""
    return _mudar_status(db, admin, id_pesquisa, "publicar")


@router.post("/pesquisas/{id_pesquisa}/pausar", response_model=PesquisaResponse, summary="Pausar pesquisa")
def pausar_pesquisa(id_pesquisa: uuid.UUID, db: Session = Depends(get_db), admin: Usuario = Depends(_admin)):
    """**Códigos:** 200 | 401 | 403 | 404 | 409 (transição inválida) | 422"""
    return _mudar_status(db, admin, id_pesquisa, "pausar")


@router.post("/pesquisas/{id_pesquisa}/arquivar", response_model=PesquisaResponse, summary="Arquivar pesquisa")
def arquivar_pesquisa(id_pesquisa: uuid.UUID, db: Session = Depends(get_db), admin: Usuario = Depends(_admin)):
    """**Códigos:** 200 | 401 | 403 | 404 | 409 (transição inválida) | 422"""
    return _mudar_status(db, admin, id_pesquisa, "arquivar")


# ══════════════════════════════════════════════════════════════════
# Links
# ══════════════════════════════════════════════════════════════════

@router.post("/pesquisas/{id_pesquisa}/links", response_model=LinkPesquisaResponse,
             status_code=status.HTTP_201_CREATED, summary="Gerar link (NOMINAL de uso único ou ABERTO)")
def criar_link(
    id_pesquisa: uuid.UUID,
    payload: LinkPesquisaCreate,
    db: Session = Depends(get_db),
    admin: Usuario = Depends(_admin),
):
    """**Códigos:** 201 | 401 | 403 | 404 | 409 (arquivada ou token em uso) | 422"""
    pesquisa = _buscar_pesquisa(db, id_pesquisa)
    if pesquisa.status == "ARQUIVADA":
        raise ConflictError("Pesquisa arquivada não aceita novos links.")
    link = LinkPesquisa(
        id=uuid.uuid4(),
        id_pesquisa=pesquisa.id,
        tipo=payload.tipo,
        token=payload.token_customizado or secrets.token_urlsafe(24),
    )
    db.add(link)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise ConflictError("Token já está em uso.", field="token_customizado")
    # O token é uma credencial: não vai para o log de auditoria
    registrar_auditoria(db, admin, "CRIAR_LINK_PESQUISA", "LINK_PESQUISA", link.id,
                        estado_depois={"id_pesquisa": str(pesquisa.id), "tipo": link.tipo})
    db.commit()
    return link


@router.get("/pesquisas/{id_pesquisa}/links", response_model=List[LinkPesquisaResponse],
            summary="Listar links da pesquisa", dependencies=[Depends(_admin)])
def listar_links(id_pesquisa: uuid.UUID, pag: Paginacao = Depends(paginacao), db: Session = Depends(get_db)):
    """**Códigos:** 200 | 401 | 403 | 404 | 422"""
    _buscar_pesquisa(db, id_pesquisa)
    return db.execute(
        select(LinkPesquisa)
        .where(LinkPesquisa.id_pesquisa == id_pesquisa)
        .order_by(LinkPesquisa.criado_em.desc(), LinkPesquisa.id)
        .offset(pag.skip).limit(pag.limit)
    ).scalars().all()


@router.delete("/pesquisas/{id_pesquisa}/links/{id_link}", status_code=status.HTTP_204_NO_CONTENT,
               summary="Excluir link de pesquisa (preservando respostas já enviadas)")
def excluir_link(
    id_pesquisa: uuid.UUID,
    id_link: uuid.UUID,
    db: Session = Depends(get_db),
    admin: Usuario = Depends(_admin),
):
    """**Códigos:** 204 | 401 | 403 | 404 | 422"""
    _buscar_pesquisa(db, id_pesquisa)
    link = db.execute(
        select(LinkPesquisa).where(
            LinkPesquisa.id == id_link,
            LinkPesquisa.id_pesquisa == id_pesquisa,
        )
    ).scalar_one_or_none()
    if link is None:
        raise NotFoundError("Link de pesquisa não encontrado.")

    # Preserva as respostas já coletadas desvinculando o id_link_pesquisa (nullable)
    db.execute(
        update(Submissao).where(Submissao.id_link_pesquisa == id_link).values(id_link_pesquisa=None)
    )
    registrar_auditoria(
        db,
        admin,
        "EXCLUIR_LINK_PESQUISA",
        "LINK_PESQUISA",
        link.id,
        estado_antes={"id_pesquisa": str(id_pesquisa), "tipo": link.tipo},
    )
    db.delete(link)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ══════════════════════════════════════════════════════════════════
# NPS
# ══════════════════════════════════════════════════════════════════

@router.get("/pesquisas/{id_pesquisa}/nps", response_model=NpsResponse, summary="NPS da pesquisa",
            dependencies=[Depends(_leitura)])
def nps(
    id_pesquisa: uuid.UUID,
    periodo_inicio: Optional[date] = None,
    periodo_fim: Optional[date] = None,
    db: Session = Depends(get_db),
):
    """
    Sem respostas: `valor_nps: null` e `status: "sem_dados_suficientes"` (nunca 0).
    **Códigos:** 200 | 401 | 403 | 404 | 422
    """
    _buscar_pesquisa(db, id_pesquisa)
    if periodo_inicio and periodo_fim and periodo_inicio > periodo_fim:
        raise InvalidInputError("periodo_inicio não pode ser depois de periodo_fim.")
    r = nps_da_pesquisa(db, id_pesquisa, periodo_inicio, periodo_fim)
    return NpsResponse(
        id_pesquisa=id_pesquisa,
        valor_nps=r.valor_nps,
        status=r.status,
        total_respostas=r.total_respostas,
        qtd_promotores=r.qtd_promotores,
        qtd_neutros=r.qtd_neutros,
        qtd_detratores=r.qtd_detratores,
        periodo_inicio=periodo_inicio,
        periodo_fim=periodo_fim,
    )


@router.get("/pesquisas/{id_pesquisa}/nps/historico", response_model=List[SnapshotNpsResponse],
            summary="Histórico diário do NPS acumulado", dependencies=[Depends(_leitura)])
def nps_historico(
    id_pesquisa: uuid.UUID,
    limit: int = Query(365, ge=1, le=1000),
    db: Session = Depends(get_db),
):
    """Do dia mais recente para o mais antigo. **Códigos:** 200 | 401 | 403 | 404 | 422"""
    _buscar_pesquisa(db, id_pesquisa)
    return db.execute(
        select(SnapshotNps)
        .where(SnapshotNps.id_pesquisa == id_pesquisa)
        .order_by(SnapshotNps.periodo_fim.desc())
        .limit(limit)
    ).scalars().all()


@router.get("/pesquisas/{id_pesquisa}/respostas", response_model=List[RespostaResponse],
            summary="Respostas da pesquisa para os painéis (comentário anonimizado)",
            dependencies=[Depends(_leitura)])
def listar_respostas(
    id_pesquisa: uuid.UUID,
    periodo_inicio: Optional[date] = None,
    periodo_fim: Optional[date] = None,
    skip: int = Query(0, ge=0, le=1_000_000),
    limit: int = Query(500, ge=1, le=1000),
    db: Session = Depends(get_db),
):
    """
    Só respostas VALIDAS, da mais recente para a mais antiga, com a análise
    sugerida vigente (uma consulta, sem N+1). O comentário sai sempre com PII
    mascarada — para dados identificados, ADMIN usa a exportação, que é auditada.

    **Códigos:** 200 | 401 | 403 | 404 | 422
    """
    _buscar_pesquisa(db, id_pesquisa)
    if periodo_inicio and periodo_fim and periodo_inicio > periodo_fim:
        raise InvalidInputError("periodo_inicio não pode ser depois de periodo_fim.")
    ultima = ultima_sequencia()
    consulta = (
        select(Submissao, AnaliseFeedback)
        .outerjoin(ultima, ultima.c.id_submissao == Submissao.id)
        .outerjoin(AnaliseFeedback, (AnaliseFeedback.id_submissao == Submissao.id)
                   & (AnaliseFeedback.sequencia_versao == ultima.c.sequencia))
        .where(Submissao.id_pesquisa == id_pesquisa, Submissao.status == "VALIDA")
    )
    consulta = filtrar_periodo(consulta, periodo_inicio, periodo_fim)
    consulta = consulta.order_by(Submissao.criada_em.desc(), Submissao.id).offset(skip).limit(limit)
    return [
        RespostaResponse(
            id=s.id,
            nota_nps=s.nota_nps,
            faixa_nps=faixa_nps(s.nota_nps),
            texto_comentario=texto_anonimizado(s.texto_comentario),
            criada_em=s.criada_em,
            status_analise=a.status if a else None,
            sentimento=a.sentimento if a else None,
            tema=a.tema if a else None,
            confianca=a.confianca if a else None,
            justificativa=a.justificativa if a else None,
        )
        for s, a in db.execute(consulta)
    ]


# ══════════════════════════════════════════════════════════════════
# Exportação (LGPD)
# ══════════════════════════════════════════════════════════════════

_CAMPOS_ANONIMIZADO = ["id", "nota_nps", "faixa_nps", "texto_comentario", "criada_em"]
_CAMPOS_IDENTIFICADO = _CAMPOS_ANONIMIZADO + ["id_link_pesquisa", "endereco_ip", "fingerprint_dispositivo"]


def _celula(valor) -> str:
    """Neutraliza fórmulas: célula começando com = + - @ é executada pelo Excel."""
    texto = "" if valor is None else str(valor)
    return "'" + texto if texto[:1] in ("=", "+", "-", "@", "\t", "\r") else texto


def _linhas_csv(id_pesquisa: uuid.UUID, anonimizado: bool) -> Iterator[str]:
    """Gera o CSV aos poucos: a exportação não carrega a pesquisa inteira na memória."""
    campos = _CAMPOS_ANONIMIZADO if anonimizado else _CAMPOS_IDENTIFICADO
    buffer = io.StringIO()
    escritor = csv.writer(buffer)

    def descarregar() -> str:
        conteudo = buffer.getvalue()
        buffer.seek(0)
        buffer.truncate()
        return conteudo

    escritor.writerow(campos)
    yield "﻿" + descarregar()   # BOM: o Excel abre como UTF-8

    with SessionLocal() as db:
        consulta = (
            select(Submissao)
            .where(Submissao.id_pesquisa == id_pesquisa, Submissao.status == "VALIDA")
            .order_by(Submissao.criada_em, Submissao.id)
            .execution_options(yield_per=500)
        )
        for i, s in enumerate(db.execute(consulta).scalars(), start=1):
            comentario = texto_anonimizado(s.texto_comentario) if anonimizado else s.texto_comentario
            linha = [s.id, s.nota_nps, faixa_nps(s.nota_nps), _celula(comentario), s.criada_em.isoformat()]
            if not anonimizado:
                linha += [s.id_link_pesquisa, s.endereco_ip, _celula(s.fingerprint_dispositivo)]
            escritor.writerow(linha)
            if i % 500 == 0:
                yield descarregar()
    yield descarregar()


@router.get("/pesquisas/{id_pesquisa}/exportacao", summary="Exportar respostas em CSV",
            response_class=StreamingResponse)
def exportar(
    id_pesquisa: uuid.UUID,
    anonimizado: bool = True,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(_leitura),
):
    """
    ANALYST só recebe a versão anonimizada (PII do comentário mascarada, sem
    link/IP/fingerprint). Só ADMIN pode pedir `anonimizado=false`.
    Toda exportação grava LOG_EXPORTACAO e LOG_AUDITORIA antes de sair.

    **Códigos:** 200 | 401 | 403 | 404 | 422
    """
    _buscar_pesquisa(db, id_pesquisa)
    if not anonimizado and usuario.papel != "ADMIN":
        raise ForbiddenError("Somente ADMIN exporta dados identificados.")

    campos = _CAMPOS_ANONIMIZADO if anonimizado else _CAMPOS_IDENTIFICADO
    log = LogExportacao(
        id=uuid.uuid4(),
        id_analista=usuario.id,
        id_pesquisa=id_pesquisa,
        campos_exportados=",".join(campos),
        anonimizado=anonimizado,
    )
    db.add(log)
    registrar_auditoria(db, usuario, "EXPORTAR_RESPOSTAS", "PESQUISA", id_pesquisa,
                        estado_depois={"id_log_exportacao": str(log.id), "anonimizado": anonimizado})
    db.commit()   # o registro existe antes de o primeiro byte sair

    return StreamingResponse(
        _linhas_csv(id_pesquisa, anonimizado),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="nps_{id_pesquisa.hex[:8]}.csv"'},
    )

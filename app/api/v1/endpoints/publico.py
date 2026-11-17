"""
Endpoints públicos — RESPONDENT (sem login).

Só existem estas duas rotas públicas além do login. Ambas têm rate limit por IP.
"""
import logging

from fastapi import APIRouter, Depends, Path, Request, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import ip_do_cliente, limite_por_ip
from app.core.config import settings
from app.core.database import get_db
from app.core.errors import ConflictError, ForbiddenError, NotFoundError
from app.core.rate_limit import RateLimiter
from app.core.security import hash_ip
from app.models.models import LinkPesquisa, Pesquisa
from app.schemas.schemas import (
    PesquisaPublicaResponse, RespostaPublicaCreate, RespostaPublicaResponse,
)
from app.services import fila
from app.services.submissoes import (
    DadosResposta, PesquisaNaoPublicada, RespostaDuplicada, registrar_resposta,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/public", tags=["Público (respondente)"])

limite_leitura = RateLimiter("publico_leitura", settings.PUBLICO_MAX_LEITURAS_IP, settings.PUBLICO_JANELA_SEGUNDOS)
limite_envio = RateLimiter("publico_envio", settings.PUBLICO_MAX_ENVIOS_IP, settings.PUBLICO_JANELA_SEGUNDOS)

TokenLink = Path(..., min_length=8, max_length=128, pattern=r"^[A-Za-z0-9_-]+$")

# Mesma mensagem para qualquer regra de duplicidade: não revela qual barrou
_JA_RESPONDIDA = "Esta pesquisa já foi respondida."
_NAO_DISPONIVEL = "Esta pesquisa não está recebendo respostas."
_COOKIE_24H = 24 * 60 * 60


def _buscar_link(db: Session, token: str) -> LinkPesquisa:
    link = db.execute(select(LinkPesquisa).where(LinkPesquisa.token == token)).scalar_one_or_none()
    if link is None:
        raise NotFoundError("Link de pesquisa não encontrado.")
    return link


def _nome_cookie(link: LinkPesquisa) -> str:
    return f"nps_resp_{link.id.hex}"


@router.get(
    "/respostas/{token}",
    response_model=PesquisaPublicaResponse,
    summary="Carregar a pesquisa pelo token do link",
    dependencies=[Depends(limite_por_ip(limite_leitura))],
)
def carregar_pesquisa(request: Request, token: str = TokenLink, db: Session = Depends(get_db)):
    """**Códigos:** 200 | 403 (não publicada) | 404 | 409 (já respondida) | 422 | 429"""
    link = _buscar_link(db, token)
    pesquisa = db.get(Pesquisa, link.id_pesquisa)
    if pesquisa.status != "PUBLICADA":
        raise ForbiddenError(_NAO_DISPONIVEL)
    if (link.tipo == "NOMINAL" and link.usado_em is not None) or (
        link.tipo == "ABERTO" and _nome_cookie(link) in request.cookies
    ):
        raise ConflictError(_JA_RESPONDIDA)
    return PesquisaPublicaResponse(
        titulo=pesquisa.titulo,
        texto_pergunta_nps=pesquisa.texto_pergunta_nps,
        texto_pergunta_aberta=pesquisa.texto_pergunta_aberta,
        tipo_link=link.tipo,
    )


@router.post(
    "/respostas/{token}",
    response_model=RespostaPublicaResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Enviar a resposta (nota de 0 a 10 e comentário opcional)",
    dependencies=[Depends(limite_por_ip(limite_envio))],
)
def enviar_resposta(
    payload: RespostaPublicaCreate,
    request: Request,
    response: Response,
    token: str = TokenLink,
    db: Session = Depends(get_db),
):
    """
    Grava a resposta e atualiza o NPS na mesma transação; responde 201 sem
    esperar a IA. `chave_idempotencia` é gerada pelo cliente (um uuid por
    formulário aberto): reenviar a mesma requisição nunca conta duas vezes.

    **Códigos:** 201 | 403 (não publicada) | 404 | 409 (duplicada) | 422 (nada gravado) | 429
    """
    link = _buscar_link(db, token)
    dados = DadosResposta(
        nota_nps=payload.nota_nps,
        texto_comentario=payload.texto_comentario,
        chave_idempotencia=payload.chave_idempotencia,
        fingerprint_dispositivo=payload.fingerprint_dispositivo,
        endereco_ip=hash_ip(ip_do_cliente(request)),
    )
    ja_respondeu = link.tipo == "ABERTO" and _nome_cookie(link) in request.cookies
    try:
        registrada = registrar_resposta(db, link, dados, ja_respondeu)
    except PesquisaNaoPublicada:
        raise ForbiddenError(_NAO_DISPONIVEL)
    except RespostaDuplicada:
        raise ConflictError(_JA_RESPONDIDA)

    # Daqui para baixo a resposta já está confirmada no banco. Nada da IA pode
    # derrubar o 201.
    if registrada.tem_job_ia:
        try:
            fila.publicar_analise(registrada.submissao.id)
        except Exception:
            logger.warning("Falha ao publicar job de IA; o worker pega pela varredura")

    if link.tipo == "ABERTO":
        response.set_cookie(
            _nome_cookie(link), "1",
            max_age=_COOKIE_24H,
            httponly=True,
            secure=settings.COOKIE_SECURE,
            # Front e API em origens diferentes: o cookie só volta com SameSite=None
            samesite="none" if settings.COOKIE_SECURE else "lax",
            path="/api/v1/public",
        )
    s = registrada.submissao
    return RespostaPublicaResponse(id=s.id, nota_nps=s.nota_nps, criada_em=s.criada_em)

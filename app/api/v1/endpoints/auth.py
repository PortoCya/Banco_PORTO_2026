"""
Endpoints — Autenticação
"""
import logging

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_usuario_atual, ip_do_cliente
from app.core.config import settings
from app.core.database import get_db
from app.core.errors import TooManyRequestsError, UnauthorizedError
from app.core.rate_limit import RateLimiter
from app.core.security import criar_token_acesso, gerar_hash_senha, precisa_rehash, verificar_senha
from app.models.models import Usuario
from app.schemas.schemas import LoginRequest, TokenResponse, UsuarioResponse

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Autenticação"])

# Por IP conta toda tentativa; por e-mail só as falhas (zera no login certo).
# Assim pega tanto quem varre vários e-mails quanto quem chuta senha de uma conta.
limite_ip = RateLimiter("login_ip", settings.LOGIN_MAX_TENTATIVAS_IP, settings.LOGIN_JANELA_SEGUNDOS)
limite_email = RateLimiter("login_email", settings.LOGIN_MAX_FALHAS_EMAIL, settings.LOGIN_JANELA_SEGUNDOS)

# Mesma mensagem para e-mail inexistente, senha errada e usuário inativo
_CREDENCIAIS_INVALIDAS = "E-mail ou senha inválidos."


@router.post("/auth/login", response_model=TokenResponse, summary="Login")
def login(payload: LoginRequest, request: Request, db: Session = Depends(get_db)):
    """
    **Recebe:** email, senha
    **Retorna:** JWT de acesso
    **Códigos:** 200 OK | 401 Unauthorized | 422 Unprocessable | 429 Too Many Requests
    """
    ip = ip_do_cliente(request)

    if limite_ip.bloqueado(ip) or limite_email.bloqueado(payload.email):
        logger.warning("Login bloqueado por rate limit")
        raise TooManyRequestsError(
            "Muitas tentativas. Tente novamente mais tarde.",
            retry_after=settings.LOGIN_JANELA_SEGUNDOS,
        )
    limite_ip.registrar(ip)

    usuario = db.execute(select(Usuario).where(Usuario.email == payload.email)).scalar_one_or_none()
    # verificar_senha roda mesmo sem usuário, para o tempo de resposta não
    # revelar se o e-mail existe
    senha_ok = verificar_senha(payload.senha, usuario.senha_hash if usuario else None)

    if not (usuario and senha_ok and usuario.ativo):
        limite_email.registrar(payload.email)
        logger.info("Falha de login")
        raise UnauthorizedError(_CREDENCIAIS_INVALIDAS)

    limite_email.resetar(payload.email)

    # Atualiza hashes antigos quando os parâmetros do Argon2 ficarem mais fortes
    if precisa_rehash(usuario.senha_hash):
        usuario.senha_hash = gerar_hash_senha(payload.senha)
        db.commit()

    logger.info("Login bem-sucedido (usuario=%s)", usuario.id)
    return TokenResponse(
        access_token=criar_token_acesso(usuario.id),
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


@router.get("/auth/me", response_model=UsuarioResponse, summary="Usuário logado")
def usuario_logado(usuario: Usuario = Depends(get_usuario_atual)):
    """
    **Retorna:** dados do usuário dono do token (papel e ativo lidos do banco)
    **Códigos:** 200 OK | 401 Unauthorized
    """
    return usuario

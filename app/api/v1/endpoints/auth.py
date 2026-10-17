"""
Endpoints — Autenticação
"""
import logging

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.errors import TooManyRequestsError, UnauthorizedError
from app.core.rate_limit import RateLimiter
from app.core.security import criar_token_acesso, gerar_hash_senha, precisa_rehash, verificar_senha
from app.models.models import Usuario
from app.schemas.schemas import LoginRequest, TokenResponse

logger = logging.getLogger(__name__)

router = APIRouter()

# Por IP conta toda tentativa; por e-mail só as falhas (zera no login certo).
# Assim pega tanto quem varre vários e-mails quanto quem chuta senha de uma conta.
limite_ip = RateLimiter(settings.LOGIN_MAX_TENTATIVAS_IP, settings.LOGIN_JANELA_SEGUNDOS)
limite_email = RateLimiter(settings.LOGIN_MAX_FALHAS_EMAIL, settings.LOGIN_JANELA_SEGUNDOS)

# Mesma mensagem para e-mail inexistente, senha errada e usuário inativo
_CREDENCIAIS_INVALIDAS = "E-mail ou senha inválidos."


@router.post(
    "/auth/login",
    response_model=TokenResponse,
    summary="Login",
    tags=["Autenticação"],
)
def login(payload: LoginRequest, request: Request, db: Session = Depends(get_db)):
    """
    **Recebe:** email, senha
    **Retorna:** JWT de acesso
    **Códigos:** 200 OK | 401 Unauthorized | 422 Unprocessable | 429 Too Many Requests
    """
    ip = request.client.host if request.client else "desconhecido"

    if limite_ip.bloqueado(ip) or limite_email.bloqueado(payload.email):
        logger.warning("Login bloqueado por rate limit (ip=%s)", ip)
        raise TooManyRequestsError("Muitas tentativas. Tente novamente mais tarde.")
    limite_ip.registrar(ip)

    usuario = db.query(Usuario).filter(Usuario.email == payload.email).first()
    # verificar_senha roda mesmo sem usuário, para o tempo de resposta não
    # revelar se o e-mail existe
    senha_ok = verificar_senha(payload.senha, usuario.senha_hash if usuario else None)

    if not (usuario and senha_ok and usuario.ativo):
        limite_email.registrar(payload.email)
        logger.info("Falha de login (ip=%s)", ip)
        raise UnauthorizedError(_CREDENCIAIS_INVALIDAS)

    limite_email.resetar(payload.email)

    # Atualiza hashes antigos quando os parâmetros do Argon2 ficarem mais fortes
    if precisa_rehash(usuario.senha_hash):
        usuario.senha_hash = gerar_hash_senha(payload.senha)
        db.commit()

    logger.info("Login bem-sucedido (usuario=%s)", usuario.uuid)
    return TokenResponse(
        access_token=criar_token_acesso(usuario.uuid),
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )

"""
Dependencies comuns das rotas: autenticação, autorização e paginação.

Uso:
    @router.post("/pesquisas")
    def criar(..., admin: Usuario = Depends(requer_papel("ADMIN"))): ...
"""
from dataclasses import dataclass

from fastapi import Depends, Query, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.errors import ForbiddenError, TooManyRequestsError, UnauthorizedError
from app.core.rate_limit import RateLimiter
from app.core.security import decodificar_token
from app.models.models import Usuario

_bearer = HTTPBearer(auto_error=False)


def get_usuario_atual(
    credenciais: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> Usuario:
    """
    Valida o JWT e carrega o usuário do banco a cada requisição.
    Papel e status vêm do banco, não do token: desativar um usuário ou trocar
    o papel vale na hora, mesmo para tokens já emitidos.
    """
    if credenciais is None:
        raise UnauthorizedError("Não autenticado.")

    id_usuario = decodificar_token(credenciais.credentials)
    if id_usuario is None:
        raise UnauthorizedError("Token inválido ou expirado.")

    usuario = db.get(Usuario, id_usuario)
    if usuario is None or not usuario.ativo:
        raise UnauthorizedError("Token inválido ou expirado.")
    return usuario


def requer_papel(*papeis: str):
    """Libera a rota só para os papéis informados (ex.: requer_papel("ADMIN"))."""
    def _verificar(usuario: Usuario = Depends(get_usuario_atual)) -> Usuario:
        if usuario.papel not in papeis:
            raise ForbiddenError("Permissão insuficiente.")
        return usuario
    return _verificar


@dataclass(frozen=True)
class Paginacao:
    skip: int
    limit: int


def paginacao(
    skip: int = Query(0, ge=0, le=1_000_000),
    limit: int = Query(50, ge=1, le=200),
) -> Paginacao:
    return Paginacao(skip, limit)


def ip_do_cliente(request: Request) -> str:
    # Atrás de proxy, suba o uvicorn com --proxy-headers e --forwarded-allow-ips
    # apontando para o proxy; nunca leia X-Forwarded-For direto (é forjável).
    return request.client.host if request.client else "desconhecido"


def limite_por_ip(limiter: RateLimiter):
    """Dependency: conta a requisição por IP e responde 429 acima do limite."""
    def _verificar(request: Request) -> None:
        ip = ip_do_cliente(request)
        if limiter.bloqueado(ip):
            raise TooManyRequestsError(
                "Muitas requisições. Tente novamente em instantes.", retry_after=limiter.janela
            )
        limiter.registrar(ip)
    return _verificar

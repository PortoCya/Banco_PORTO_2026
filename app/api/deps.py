"""
Dependencies de autenticação e autorização para as rotas.

Uso:
    @router.post("/pesquisas", dependencies=[Depends(requer_papel("ADMIN"))])
    def criar(..., usuario: Usuario = Depends(get_usuario_atual)): ...
"""
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.errors import ForbiddenError, NotFoundError, UnauthorizedError
from app.core.security import decodificar_token
from app.models.models import Conversa, Gerenciacao, Usuario

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

    usuario = db.query(Usuario).filter(Usuario.uuid == id_usuario).first()
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


def e_dono_ou_admin(usuario: Usuario, id_dono: str | None) -> bool:
    """ADMIN vê tudo; os demais só o que é deles."""
    return usuario.papel == "ADMIN" or id_dono == usuario.uuid


# ─── Busca com checagem de dono ──────────────────────────────────────────────
# Respondem 404 tanto se não existe quanto se é de outro usuário, para não
# revelar que o registro existe.

def buscar_conversa_do_usuario(db: Session, uuid: str, usuario: Usuario) -> Conversa:
    conversa = db.query(Conversa).filter(Conversa.uuid == uuid).first()
    if not conversa or not e_dono_ou_admin(usuario, conversa.fk_usuario):
        raise NotFoundError(f"Conversa '{uuid}' não encontrada.")
    return conversa


def buscar_gerenciacao_do_usuario(db: Session, uuid: str, usuario: Usuario) -> Gerenciacao:
    g = db.query(Gerenciacao).filter(Gerenciacao.uuid == uuid).first()
    if not g or not e_dono_ou_admin(usuario, g.fk_pessoa):
        raise NotFoundError(f"Gerenciação '{uuid}' não encontrada.")
    return g

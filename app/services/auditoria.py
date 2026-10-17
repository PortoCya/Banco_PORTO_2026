"""
Registro de auditoria (LOG_AUDITORIA).

Adiciona o log na sessão sem dar commit: quem chama faz o commit junto com a
alteração, para que a mudança e o seu registro fiquem na mesma transação.
"""
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.models.models import LogAuditoria, Usuario


def estado_usuario(usuario: Usuario) -> dict[str, Any]:
    """Snapshot do usuário para auditoria. Nunca inclui senha_hash."""
    return {
        "nome": usuario.nome,
        "email": usuario.email,
        "papel": usuario.papel,
        "ativo": usuario.ativo,
    }


def registrar_auditoria(
    db: Session,
    ator: Usuario,
    acao: str,
    tipo_entidade: str,
    id_entidade: str,
    estado_antes: Optional[dict[str, Any]] = None,
    estado_depois: Optional[dict[str, Any]] = None,
) -> None:
    db.add(LogAuditoria(
        id_usuario_ator=ator.uuid,
        acao=acao,
        tipo_entidade=tipo_entidade,
        id_entidade=id_entidade,
        estado_antes=estado_antes,
        estado_depois=estado_depois,
    ))

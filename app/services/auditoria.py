"""
Registro de auditoria (LOG_AUDITORIA).

Adiciona o log na sessão sem dar commit: quem chama faz o commit junto com a
alteração, para que a mudança e o seu registro fiquem na mesma transação.
"""
import uuid
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.models.models import LogAuditoria, Pesquisa, Usuario, VersaoModelo

# Rede de segurança: mesmo que alguém passe um estado com estes campos, eles
# não chegam ao log.
_CAMPOS_PROIBIDOS = {"senha", "senha_hash", "token", "access_token", "secret_key"}


def estado_usuario(usuario: Usuario) -> dict[str, Any]:
    """Snapshot do usuário para auditoria. Nunca inclui senha_hash."""
    return {
        "nome": usuario.nome,
        "email": usuario.email,
        "papel": usuario.papel,
        "ativo": usuario.ativo,
    }


def estado_pesquisa(pesquisa: Pesquisa) -> dict[str, Any]:
    return {
        "titulo": pesquisa.titulo,
        "texto_pergunta_nps": pesquisa.texto_pergunta_nps,
        "texto_pergunta_aberta": pesquisa.texto_pergunta_aberta,
        "status": pesquisa.status,
        "numero_versao": pesquisa.numero_versao,
        "id_pesquisa_pai": str(pesquisa.id_pesquisa_pai) if pesquisa.id_pesquisa_pai else None,
    }


def estado_versao_modelo(versao: VersaoModelo) -> dict[str, Any]:
    return {
        "provedor": versao.provedor,
        "nome_modelo": versao.nome_modelo,
        "rotulo_versao": versao.rotulo_versao,
        "id_prompt": str(versao.id_prompt),
        "ativo": versao.ativo,
    }


def _limpar(estado: Optional[dict[str, Any]]) -> Optional[dict[str, Any]]:
    if estado is None:
        return None
    return {k: v for k, v in estado.items() if k.lower() not in _CAMPOS_PROIBIDOS}


def registrar_auditoria(
    db: Session,
    ator: Usuario,
    acao: str,
    tipo_entidade: str,
    id_entidade: uuid.UUID,
    estado_antes: Optional[dict[str, Any]] = None,
    estado_depois: Optional[dict[str, Any]] = None,
) -> None:
    db.add(LogAuditoria(
        id_usuario_ator=ator.id,
        acao=acao,
        tipo_entidade=tipo_entidade,
        id_entidade=id_entidade,
        estado_antes=_limpar(estado_antes),
        estado_depois=_limpar(estado_depois),
    ))

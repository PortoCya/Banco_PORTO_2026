"""
Endpoints — Usuários e VideoModelo
"""
from typing import List
from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.deps import requer_papel
from app.core.database import get_db
from app.core.errors import NotFoundError, ConflictError
from app.core.security import gerar_hash_senha
from app.models.models import Usuario, VideoModelo
from app.schemas.schemas import (
    UsuarioCreate, UsuarioUpdate, UsuarioResponse,
    VideoModeloCreate, VideoModeloResponse,
)
from app.services.auditoria import estado_usuario, registrar_auditoria

router = APIRouter()


# ══════════════════════════════════════════════════════════════════
# USUÁRIOS — somente ADMIN
# ══════════════════════════════════════════════════════════════════

def _buscar_usuario(db: Session, uuid: str) -> Usuario:
    usuario = db.query(Usuario).filter(Usuario.uuid == uuid).first()
    if not usuario:
        raise NotFoundError(f"Usuário '{uuid}' não encontrado.")
    return usuario


@router.post(
    "/usuarios",
    response_model=UsuarioResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Criar usuário",
    tags=["Usuários"],
)
def criar_usuario(
    payload: UsuarioCreate,
    db: Session = Depends(get_db),
    admin: Usuario = Depends(requer_papel("ADMIN")),
):
    """
    **Recebe:** nome, email, senha, papel (ADMIN|ANALYST)
    **Retorna:** objeto do usuário criado
    **Códigos:** 201 Created | 401 | 403 | 409 Conflict | 422 Unprocessable
    """
    if db.query(Usuario).filter(Usuario.email == payload.email).first():
        raise ConflictError("E-mail já cadastrado.", field="email")
    usuario = Usuario(
        nome=payload.nome,
        email=payload.email,
        senha_hash=gerar_hash_senha(payload.senha),
        papel=payload.papel,
    )
    db.add(usuario)
    db.flush()
    registrar_auditoria(db, admin, "CRIAR_USUARIO", "USUARIO", usuario.uuid,
                        estado_depois=estado_usuario(usuario))
    db.commit()
    db.refresh(usuario)
    return usuario


@router.get(
    "/usuarios",
    response_model=List[UsuarioResponse],
    summary="Listar usuários",
    tags=["Usuários"],
    dependencies=[Depends(requer_papel("ADMIN"))],
)
def listar_usuarios(skip: int = 0, limit: int = 50, db: Session = Depends(get_db)):
    """
    **Recebe:** query params skip, limit
    **Retorna:** lista de usuários
    **Códigos:** 200 OK | 401 | 403
    """
    return db.query(Usuario).offset(skip).limit(min(limit, 200)).all()


@router.get(
    "/usuarios/{uuid}",
    response_model=UsuarioResponse,
    summary="Buscar usuário por UUID",
    tags=["Usuários"],
    dependencies=[Depends(requer_papel("ADMIN"))],
)
def buscar_usuario(uuid: str, db: Session = Depends(get_db)):
    """
    **Recebe:** uuid no path
    **Retorna:** objeto do usuário
    **Códigos:** 200 OK | 401 | 403 | 404 Not Found
    """
    return _buscar_usuario(db, uuid)


@router.patch(
    "/usuarios/{uuid}",
    response_model=UsuarioResponse,
    summary="Alterar nome, papel ou status do usuário",
    tags=["Usuários"],
)
def atualizar_usuario(
    uuid: str,
    payload: UsuarioUpdate,
    db: Session = Depends(get_db),
    admin: Usuario = Depends(requer_papel("ADMIN")),
):
    """
    **Recebe:** nome, papel e/ou ativo
    **Retorna:** usuário atualizado
    **Códigos:** 200 OK | 401 | 403 | 404 | 409 (ADMIN rebaixando ou desativando a si mesmo)
    """
    usuario = _buscar_usuario(db, uuid)
    mudancas = payload.model_dump(exclude_unset=True)

    # Evita que o ADMIN se tranque fora da plataforma
    if usuario.uuid == admin.uuid and (
        mudancas.get("ativo") is False or mudancas.get("papel", "ADMIN") != "ADMIN"
    ):
        raise ConflictError("Um ADMIN não pode rebaixar ou desativar a própria conta.")

    antes = estado_usuario(usuario)
    for campo, valor in mudancas.items():
        setattr(usuario, campo, valor)
    registrar_auditoria(db, admin, "ATUALIZAR_USUARIO", "USUARIO", usuario.uuid,
                        estado_antes=antes, estado_depois=estado_usuario(usuario))
    db.commit()
    db.refresh(usuario)
    return usuario


@router.delete(
    "/usuarios/{uuid}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Desativar usuário",
    tags=["Usuários"],
)
def remover_usuario(
    uuid: str,
    db: Session = Depends(get_db),
    admin: Usuario = Depends(requer_papel("ADMIN")),
):
    """
    Desativa o usuário (ativo=false) em vez de apagar, para não quebrar o
    histórico de auditoria. Tokens já emitidos param de valer na hora.
    **Recebe:** uuid no path
    **Retorna:** 204 No Content
    **Códigos:** 204 | 401 | 403 | 404 | 409 (ADMIN desativando a si mesmo)
    """
    usuario = _buscar_usuario(db, uuid)
    if usuario.uuid == admin.uuid:
        raise ConflictError("Um ADMIN não pode desativar a própria conta.")
    antes = estado_usuario(usuario)
    usuario.ativo = False
    registrar_auditoria(db, admin, "DESATIVAR_USUARIO", "USUARIO", usuario.uuid,
                        estado_antes=antes, estado_depois=estado_usuario(usuario))
    db.commit()


# ══════════════════════════════════════════════════════════════════
# VIDEO MODELO
# ══════════════════════════════════════════════════════════════════

@router.post(
    "/video-modelos",
    response_model=VideoModeloResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Registrar modelo de IA",
    tags=["Modelos de IA"],
)
def criar_video_modelo(payload: VideoModeloCreate, db: Session = Depends(get_db)):
    """
    **Recebe:** provider, nome_modelo, status_ativo, is_current
    **Retorna:** modelo registrado
    **Códigos:** 201 | 409 | 422
    """
    modelo = VideoModelo(**payload.model_dump())
    db.add(modelo)
    db.commit()
    db.refresh(modelo)
    return modelo


@router.get(
    "/video-modelos",
    response_model=List[VideoModeloResponse],
    summary="Listar modelos de IA",
    tags=["Modelos de IA"],
)
def listar_video_modelos(db: Session = Depends(get_db)):
    """
    **Retorna:** todos os modelos cadastrados
    **Códigos:** 200
    """
    return db.query(VideoModelo).all()


@router.patch(
    "/video-modelos/{uuid}/ativar",
    response_model=VideoModeloResponse,
    summary="Definir modelo como ativo (current)",
    tags=["Modelos de IA"],
)
def ativar_video_modelo(uuid: str, db: Session = Depends(get_db)):
    """
    Define um modelo como `is_current=True` e desativa os demais.
    **Códigos:** 200 | 404
    """
    modelo = db.query(VideoModelo).filter(VideoModelo.uuid == uuid).first()
    if not modelo:
        raise NotFoundError(f"Modelo '{uuid}' não encontrado.")
    db.query(VideoModelo).update({"is_current": False})
    modelo.is_current = True
    db.commit()
    db.refresh(modelo)
    return modelo

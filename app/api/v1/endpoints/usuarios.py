"""
Endpoints — Usuários e VideoModelo
"""
from typing import List
from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.errors import NotFoundError, ConflictError
from app.models.models import Usuario, VideoModelo
from app.schemas.schemas import (
    UsuarioCreate, UsuarioResponse,
    VideoModeloCreate, VideoModeloResponse,
)

router = APIRouter()


# ══════════════════════════════════════════════════════════════════
# USUÁRIOS
# ══════════════════════════════════════════════════════════════════

@router.post(
    "/usuarios",
    response_model=UsuarioResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Criar usuário",
    tags=["Usuários"],
)
def criar_usuario(payload: UsuarioCreate, db: Session = Depends(get_db)):
    """
    **Recebe:** nome, email, role (ADMIN|ANALISTA|PT)
    **Retorna:** objeto do usuário criado
    **Códigos:** 201 Created | 409 Conflict | 422 Unprocessable
    """
    if db.query(Usuario).filter(Usuario.email == payload.email).first():
        raise ConflictError("E-mail já cadastrado.", field="email")
    usuario = Usuario(**payload.model_dump())
    db.add(usuario)
    db.commit()
    db.refresh(usuario)
    return usuario


@router.get(
    "/usuarios",
    response_model=List[UsuarioResponse],
    summary="Listar usuários",
    tags=["Usuários"],
)
def listar_usuarios(skip: int = 0, limit: int = 50, db: Session = Depends(get_db)):
    """
    **Recebe:** query params skip, limit
    **Retorna:** lista de usuários
    **Códigos:** 200 OK
    """
    return db.query(Usuario).offset(skip).limit(limit).all()


@router.get(
    "/usuarios/{uuid}",
    response_model=UsuarioResponse,
    summary="Buscar usuário por UUID",
    tags=["Usuários"],
)
def buscar_usuario(uuid: str, db: Session = Depends(get_db)):
    """
    **Recebe:** uuid no path
    **Retorna:** objeto do usuário
    **Códigos:** 200 OK | 404 Not Found
    """
    usuario = db.query(Usuario).filter(Usuario.uuid == uuid).first()
    if not usuario:
        raise NotFoundError(f"Usuário '{uuid}' não encontrado.")
    return usuario


@router.delete(
    "/usuarios/{uuid}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remover usuário",
    tags=["Usuários"],
)
def remover_usuario(uuid: str, db: Session = Depends(get_db)):
    """
    **Recebe:** uuid no path
    **Retorna:** 204 No Content
    **Códigos:** 204 | 404 Not Found
    """
    usuario = db.query(Usuario).filter(Usuario.uuid == uuid).first()
    if not usuario:
        raise NotFoundError(f"Usuário '{uuid}' não encontrado.")
    db.delete(usuario)
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

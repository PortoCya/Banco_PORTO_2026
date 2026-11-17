"""
Endpoints — Usuários (somente ADMIN)
"""
import uuid
from typing import List

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import Paginacao, paginacao, requer_papel
from app.core.database import get_db
from app.core.errors import ConflictError, NotFoundError
from app.core.security import gerar_hash_senha
from app.models.models import Usuario
from app.schemas.schemas import UsuarioCreate, UsuarioResponse, UsuarioUpdate
from app.services.auditoria import estado_usuario, registrar_auditoria

router = APIRouter(tags=["Usuários"])


def _buscar_usuario(db: Session, id_usuario: uuid.UUID) -> Usuario:
    usuario = db.get(Usuario, id_usuario)
    if not usuario:
        raise NotFoundError("Usuário não encontrado.")
    return usuario


@router.post("/usuarios", response_model=UsuarioResponse, status_code=status.HTTP_201_CREATED,
             summary="Criar usuário")
def criar_usuario(
    payload: UsuarioCreate,
    db: Session = Depends(get_db),
    admin: Usuario = Depends(requer_papel("ADMIN")),
):
    """
    **Recebe:** nome, email, senha (12 a 128 caracteres), papel (ADMIN|ANALYST)
    **Códigos:** 201 | 401 | 403 | 409 (e-mail já cadastrado) | 422
    """
    usuario = Usuario(
        nome=payload.nome,
        email=payload.email,
        senha_hash=gerar_hash_senha(payload.senha),
        papel=payload.papel,
    )
    db.add(usuario)
    try:
        # O UNIQUE do banco é quem decide: checar antes com SELECT deixaria
        # passar duas criações simultâneas com o mesmo e-mail.
        db.flush()
    except IntegrityError:
        db.rollback()
        raise ConflictError("E-mail já cadastrado.", field="email")
    registrar_auditoria(db, admin, "CRIAR_USUARIO", "USUARIO", usuario.id,
                        estado_depois=estado_usuario(usuario))
    db.commit()
    return usuario


@router.get("/usuarios", response_model=List[UsuarioResponse], summary="Listar usuários",
            dependencies=[Depends(requer_papel("ADMIN"))])
def listar_usuarios(pag: Paginacao = Depends(paginacao), db: Session = Depends(get_db)):
    """**Códigos:** 200 | 401 | 403 | 422"""
    return db.execute(
        select(Usuario).order_by(Usuario.criado_em, Usuario.id).offset(pag.skip).limit(pag.limit)
    ).scalars().all()


@router.get("/usuarios/{id_usuario}", response_model=UsuarioResponse, summary="Buscar usuário",
            dependencies=[Depends(requer_papel("ADMIN"))])
def buscar_usuario(id_usuario: uuid.UUID, db: Session = Depends(get_db)):
    """**Códigos:** 200 | 401 | 403 | 404 | 422"""
    return _buscar_usuario(db, id_usuario)


@router.patch("/usuarios/{id_usuario}", response_model=UsuarioResponse,
              summary="Alterar nome, papel ou status do usuário")
def atualizar_usuario(
    id_usuario: uuid.UUID,
    payload: UsuarioUpdate,
    db: Session = Depends(get_db),
    admin: Usuario = Depends(requer_papel("ADMIN")),
):
    """
    **Recebe:** nome, papel e/ou ativo
    **Códigos:** 200 | 401 | 403 | 404 | 409 (ADMIN rebaixando ou desativando a si mesmo) | 422
    """
    usuario = _buscar_usuario(db, id_usuario)
    mudancas = payload.model_dump(exclude_unset=True)

    # Evita que o ADMIN se tranque fora da plataforma
    if usuario.id == admin.id and (
        mudancas.get("ativo") is False or mudancas.get("papel", "ADMIN") != "ADMIN"
    ):
        raise ConflictError("Um ADMIN não pode rebaixar ou desativar a própria conta.")

    antes = estado_usuario(usuario)
    for campo, valor in mudancas.items():
        setattr(usuario, campo, valor)
    registrar_auditoria(db, admin, "ATUALIZAR_USUARIO", "USUARIO", usuario.id,
                        estado_antes=antes, estado_depois=estado_usuario(usuario))
    db.commit()
    return usuario


@router.delete("/usuarios/{id_usuario}", status_code=status.HTTP_204_NO_CONTENT,
               summary="Desativar usuário")
def remover_usuario(
    id_usuario: uuid.UUID,
    db: Session = Depends(get_db),
    admin: Usuario = Depends(requer_papel("ADMIN")),
):
    """
    Desativa o usuário (ativo=false) em vez de apagar, para não quebrar o
    histórico de auditoria. Tokens já emitidos param de valer na hora.
    **Códigos:** 204 | 401 | 403 | 404 | 409 (ADMIN desativando a si mesmo)
    """
    usuario = _buscar_usuario(db, id_usuario)
    if usuario.id == admin.id:
        raise ConflictError("Um ADMIN não pode desativar a própria conta.")
    antes = estado_usuario(usuario)
    usuario.ativo = False
    registrar_auditoria(db, admin, "DESATIVAR_USUARIO", "USUARIO", usuario.id,
                        estado_antes=antes, estado_depois=estado_usuario(usuario))
    db.commit()

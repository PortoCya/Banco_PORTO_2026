"""
Endpoints de Autenticação, Autorização (RBAC) e Gestão de Usuários — NPS KeyCore v1.0.
Atende RF-001 (Auth segura no backend) e RF-002 (Gestão ADMIN / ANALYST) + Auditoria (RF-020).
"""
from typing import List

from fastapi import APIRouter, Depends, status
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.errors import ConflictError, NotFoundError, UnauthorizedError
from app.core.security import (
    bearer_scheme,
    criar_token_acesso,
    gerar_senha_hash,
    get_current_user,
    rate_limit,
    registrar_auditoria,
    require_roles,
    revogar_token,
    verificar_senha,
)
from app.models.models import Usuario
from app.schemas.schemas import (
    LoginRequest,
    TokenResponse,
    UsuarioCreate,
    UsuarioResponse,
)

router = APIRouter()


# ══════════════════════════════════════════════════════════════════
# AUTENTICAÇÃO (/auth)
# ══════════════════════════════════════════════════════════════════

@router.post(
    "/auth/login",
    response_model=TokenResponse,
    summary="Autenticar usuário (ADMIN ou ANALYST)",
    tags=["Auth"],
    dependencies=[Depends(rate_limit("auth_login", max_requests=10, window_seconds=60))],
)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    """
    Valida credenciais com hash PBKDF2-HMAC-SHA256 e emite token JWT assinado.
    Protegido por Rate Limiting (máx. 10 tentativas/min por IP).
    """
    usuario = db.query(Usuario).filter(Usuario.email == payload.email).first()
    if not usuario or not usuario.ativo or not verificar_senha(payload.senha, usuario.senha_hash):
        raise UnauthorizedError("E-mail ou senha inválidos.")

    token = criar_token_acesso(usuario_id=usuario.id, papel=usuario.papel)
    registrar_auditoria(
        db=db,
        id_usuario_ator=usuario.id,
        acao="AUTH_LOGIN_SUCCESS",
        tipo_entidade="USUARIO",
        id_entidade=usuario.id,
        estado_depois={"email": usuario.email, "papel": usuario.papel},
    )
    db.commit()

    return TokenResponse(
        access_token=token,
        expires_in_minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES,
        papel=usuario.papel,
        usuario_id=usuario.id,
    )


@router.post(
    "/auth/logout",
    status_code=status.HTTP_200_OK,
    summary="Encerrar sessão e revogar token atual",
    tags=["Auth"],
)
def logout(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    usuario_atual: Usuario = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if credentials and credentials.credentials:
        revogar_token(credentials.credentials)
    registrar_auditoria(
        db=db,
        id_usuario_ator=usuario_atual.id,
        acao="AUTH_LOGOUT",
        tipo_entidade="USUARIO",
        id_entidade=usuario_atual.id,
    )
    db.commit()
    return {"status": "ok", "message": "Sessão encerrada e token revogado com sucesso."}


@router.get(
    "/auth/me",
    response_model=UsuarioResponse,
    summary="Obter perfil do usuário autenticado",
    tags=["Auth"],
)
def me(usuario_atual: Usuario = Depends(get_current_user)):
    return usuario_atual


# ══════════════════════════════════════════════════════════════════
# GESTÃO DE USUÁRIOS (RBAC: Exclusivo ADMIN)
# ══════════════════════════════════════════════════════════════════

@router.post(
    "/usuarios",
    response_model=UsuarioResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Criar novo usuário (Requer ADMIN)",
    tags=["Usuários"],
)
def criar_usuario(
    payload: UsuarioCreate,
    db: Session = Depends(get_db),
    admin: Usuario = Depends(require_roles("ADMIN")),
):
    existente = db.query(Usuario).filter(Usuario.email == payload.email).first()
    if existente:
        raise ConflictError(f"E-mail '{payload.email}' já está cadastrado.")

    novo = Usuario(
        nome=payload.nome,
        email=payload.email,
        senha_hash=gerar_senha_hash(payload.senha),
        papel=payload.papel,
        ativo=True,
    )
    db.add(novo)
    db.flush()

    registrar_auditoria(
        db=db,
        id_usuario_ator=admin.id,
        acao="CRIAR_USUARIO",
        tipo_entidade="USUARIO",
        id_entidade=novo.id,
        estado_depois={"nome": novo.nome, "email": novo.email, "papel": novo.papel, "ativo": novo.ativo},
    )
    db.commit()
    db.refresh(novo)
    return novo


@router.get(
    "/usuarios",
    response_model=List[UsuarioResponse],
    summary="Listar usuários (Requer ADMIN)",
    tags=["Usuários"],
)
def listar_usuarios(
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db),
    admin: Usuario = Depends(require_roles("ADMIN")),
):
    return db.query(Usuario).offset(skip).limit(min(limit, 100)).all()


@router.patch(
    "/usuarios/{usuario_id}/desativar",
    response_model=UsuarioResponse,
    summary="Desativar usuário mantendo histórico de auditoria (Requer ADMIN)",
    tags=["Usuários"],
)
def desativar_usuario(
    usuario_id: str,
    db: Session = Depends(get_db),
    admin: Usuario = Depends(require_roles("ADMIN")),
):
    alvo = db.query(Usuario).filter(Usuario.id == usuario_id).first()
    if not alvo:
        raise NotFoundError(f"Usuário '{usuario_id}' não encontrado.")

    antes = {"ativo": alvo.ativo}
    alvo.ativo = False
    registrar_auditoria(
        db=db,
        id_usuario_ator=admin.id,
        acao="DESATIVAR_USUARIO",
        tipo_entidade="USUARIO",
        id_entidade=alvo.id,
        estado_antes=antes,
        estado_depois={"ativo": False},
    )
    db.commit()
    db.refresh(alvo)
    return alvo

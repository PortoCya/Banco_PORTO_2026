"""
Endpoints — Auditoria (somente ADMIN)
"""
import uuid
from datetime import datetime
from typing import Annotated, List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import Paginacao, paginacao, requer_papel
from app.core.database import get_db
from app.core.errors import InvalidInputError
from app.models.models import LogAuditoria, LogExportacao
from app.schemas.schemas import LogAuditoriaResponse, LogExportacaoResponse

router = APIRouter(tags=["Auditoria"], dependencies=[Depends(requer_papel("ADMIN"))])

_Nome = Annotated[Optional[str], Query(max_length=150, pattern=r"^[A-Za-z0-9_]+$")]


@router.get("/log-auditoria", response_model=List[LogAuditoriaResponse], summary="Trilha de auditoria")
def listar_log_auditoria(
    acao: _Nome = None,
    tipo_entidade: _Nome = None,
    id_entidade: Optional[uuid.UUID] = None,
    id_usuario_ator: Optional[uuid.UUID] = None,
    de: Optional[datetime] = None,
    ate: Optional[datetime] = None,
    pag: Paginacao = Depends(paginacao),
    db: Session = Depends(get_db),
):
    """Do mais recente para o mais antigo. **Códigos:** 200 | 401 | 403 | 422"""
    for limite in (de, ate):
        if limite is not None and limite.tzinfo is None:
            raise InvalidInputError("Informe data e hora com fuso (ex.: 2026-01-31T00:00:00Z).")
    consulta = select(LogAuditoria)
    if acao:
        consulta = consulta.where(LogAuditoria.acao == acao)
    if tipo_entidade:
        consulta = consulta.where(LogAuditoria.tipo_entidade == tipo_entidade)
    if id_entidade:
        consulta = consulta.where(LogAuditoria.id_entidade == id_entidade)
    if id_usuario_ator:
        consulta = consulta.where(LogAuditoria.id_usuario_ator == id_usuario_ator)
    if de:
        consulta = consulta.where(LogAuditoria.criado_em >= de)
    if ate:
        consulta = consulta.where(LogAuditoria.criado_em < ate)
    consulta = consulta.order_by(LogAuditoria.criado_em.desc(), LogAuditoria.id)
    return db.execute(consulta.offset(pag.skip).limit(pag.limit)).scalars().all()


@router.get("/log-exportacao", response_model=List[LogExportacaoResponse], summary="Registro de exportações")
def listar_log_exportacao(
    id_pesquisa: Optional[uuid.UUID] = None,
    pag: Paginacao = Depends(paginacao),
    db: Session = Depends(get_db),
):
    """**Códigos:** 200 | 401 | 403 | 422"""
    consulta = select(LogExportacao)
    if id_pesquisa:
        consulta = consulta.where(LogExportacao.id_pesquisa == id_pesquisa)
    consulta = consulta.order_by(LogExportacao.criado_em.desc(), LogExportacao.id)
    return db.execute(consulta.offset(pag.skip).limit(pag.limit)).scalars().all()

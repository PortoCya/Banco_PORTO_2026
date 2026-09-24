"""
Endpoints — Gerenciacao, SOA_IA, Prompts, Dimensões KPIs
"""
from typing import List
from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session
import uuid as uuid_lib

from app.core.database import get_db
from app.core.errors import NotFoundError
from app.models.models import Gerenciacao, SoaIa, Prompt, DimensoesKpis
from app.schemas.schemas import (
    GerenciacaoCreate, GerenciacaoResponse,
    SoaIaResponse,
    PromptCreate, PromptResponse,
    DimensoesKpisResponse,
)

router = APIRouter()


# ══════════════════════════════════════════════════════════════════
# GERENCIACAO
# ══════════════════════════════════════════════════════════════════

@router.post(
    "/gerenciacoes",
    response_model=GerenciacaoResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Criar sessão de gerenciação",
    tags=["Gerenciação"],
)
def criar_gerenciacao(payload: GerenciacaoCreate, db: Session = Depends(get_db)):
    """
    **Recebe:** fk_pessoa, tipo_pot, fingerprint_dispositivo, credencial_ip
    **Retorna:** registro de gerenciação com chave_referencia única
    **Códigos:** 201 | 422
    """
    gerenciacao = Gerenciacao(
        **payload.model_dump(),
        status="ABERTO",
        chave_referencia=str(uuid_lib.uuid4()),
    )
    db.add(gerenciacao)
    db.commit()
    db.refresh(gerenciacao)
    return gerenciacao


@router.get(
    "/gerenciacoes/{uuid}",
    response_model=GerenciacaoResponse,
    summary="Buscar gerenciação por UUID",
    tags=["Gerenciação"],
)
def buscar_gerenciacao(uuid: str, db: Session = Depends(get_db)):
    """
    **Recebe:** uuid no path
    **Retorna:** objeto de gerenciação
    **Códigos:** 200 | 404
    """
    g = db.query(Gerenciacao).filter(Gerenciacao.uuid == uuid).first()
    if not g:
        raise NotFoundError(f"Gerenciação '{uuid}' não encontrada.")
    return g


@router.get(
    "/gerenciacoes",
    response_model=List[GerenciacaoResponse],
    summary="Listar gerenciações",
    tags=["Gerenciação"],
)
def listar_gerenciacoes(
    fk_pessoa: str = None,
    status_filtro: str = None,
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db),
):
    """
    **Recebe:** filtros opcionais por pessoa e status
    **Retorna:** lista paginada
    **Códigos:** 200
    """
    q = db.query(Gerenciacao)
    if fk_pessoa:
        q = q.filter(Gerenciacao.fk_pessoa == fk_pessoa)
    if status_filtro:
        q = q.filter(Gerenciacao.status == status_filtro)
    return q.offset(skip).limit(limit).all()


@router.patch(
    "/gerenciacoes/{uuid}/status",
    response_model=GerenciacaoResponse,
    summary="Atualizar status de gerenciação",
    tags=["Gerenciação"],
)
def atualizar_status_gerenciacao(
    uuid: str,
    novo_status: str,
    db: Session = Depends(get_db),
):
    """
    **Recebe:** uuid no path, novo_status como query param
    Valores válidos: ABERTO | PROCESSANDO | CONCLUIDO | FALHA | PENDENTE
    **Retorna:** gerenciação atualizada
    **Códigos:** 200 | 404 | 422
    """
    validos = {"ABERTO", "PROCESSANDO", "CONCLUIDO", "FALHA", "PENDENTE"}
    if novo_status not in validos:
        from app.core.errors import ValidationError
        raise ValidationError(f"Status inválido. Use: {validos}")
    g = db.query(Gerenciacao).filter(Gerenciacao.uuid == uuid).first()
    if not g:
        raise NotFoundError(f"Gerenciação '{uuid}' não encontrada.")
    g.status = novo_status
    db.commit()
    db.refresh(g)
    return g


# ══════════════════════════════════════════════════════════════════
# SOA_IA
# ══════════════════════════════════════════════════════════════════

@router.get(
    "/soa-ia/{uuid}",
    response_model=SoaIaResponse,
    summary="Buscar status SOA_IA",
    tags=["SOA IA"],
)
def buscar_soa_ia(uuid: str, db: Session = Depends(get_db)):
    """
    **Recebe:** uuid do SOA_IA
    **Retorna:** status do orquestrador IA
    **Códigos:** 200 | 404
    """
    soa = db.query(SoaIa).filter(SoaIa.uuid == uuid).first()
    if not soa:
        raise NotFoundError(f"SOA_IA '{uuid}' não encontrado.")
    return soa


@router.get(
    "/soa-ia/gerenciacao/{gerenciacao_uuid}",
    response_model=SoaIaResponse,
    summary="Buscar SOA_IA por gerenciação",
    tags=["SOA IA"],
)
def buscar_soa_ia_por_gerenciacao(gerenciacao_uuid: str, db: Session = Depends(get_db)):
    """
    **Recebe:** gerenciacao_uuid no path
    **Retorna:** SOA_IA associado
    **Códigos:** 200 | 404
    """
    soa = db.query(SoaIa).filter(SoaIa.fk_gerenciacao == gerenciacao_uuid).first()
    if not soa:
        raise NotFoundError(f"SOA_IA para gerenciação '{gerenciacao_uuid}' não encontrado.")
    return soa


# ══════════════════════════════════════════════════════════════════
# PROMPTS
# ══════════════════════════════════════════════════════════════════

@router.post(
    "/prompts",
    response_model=PromptResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Criar prompt de engenharia",
    tags=["Prompts"],
)
def criar_prompt(payload: PromptCreate, db: Session = Depends(get_db)):
    """
    **Recebe:** fk_video_modelo, conteudo, contexto, template, status_ativo
    **Retorna:** prompt criado
    **Códigos:** 201 | 422
    """
    prompt = Prompt(**payload.model_dump())
    db.add(prompt)
    db.commit()
    db.refresh(prompt)
    return prompt


@router.get(
    "/prompts",
    response_model=List[PromptResponse],
    summary="Listar prompts ativos",
    tags=["Prompts"],
)
def listar_prompts(apenas_ativos: bool = True, db: Session = Depends(get_db)):
    """
    **Recebe:** apenas_ativos (default True)
    **Retorna:** lista de prompts
    **Códigos:** 200
    """
    q = db.query(Prompt)
    if apenas_ativos:
        q = q.filter(Prompt.status_ativo == True)
    return q.all()


@router.patch(
    "/prompts/{uuid}/desativar",
    response_model=PromptResponse,
    summary="Desativar prompt",
    tags=["Prompts"],
)
def desativar_prompt(uuid: str, db: Session = Depends(get_db)):
    """
    **Recebe:** uuid no path
    **Retorna:** prompt atualizado
    **Códigos:** 200 | 404
    """
    p = db.query(Prompt).filter(Prompt.uuid == uuid).first()
    if not p:
        raise NotFoundError(f"Prompt '{uuid}' não encontrado.")
    p.status_ativo = False
    db.commit()
    db.refresh(p)
    return p


# ══════════════════════════════════════════════════════════════════
# DIMENSÕES KPIs
# ══════════════════════════════════════════════════════════════════

@router.get(
    "/dimensoes-kpis/{gerenciacao_uuid}",
    response_model=List[DimensoesKpisResponse],
    summary="Buscar KPIs de uma gerenciação",
    tags=["KPIs"],
)
def buscar_dimensoes_kpis(gerenciacao_uuid: str, db: Session = Depends(get_db)):
    """
    **Recebe:** gerenciacao_uuid no path
    **Retorna:** lista de dimensões de KPI
    **Códigos:** 200 | 404
    """
    g = db.query(Gerenciacao).filter(Gerenciacao.uuid == gerenciacao_uuid).first()
    if not g:
        raise NotFoundError(f"Gerenciação '{gerenciacao_uuid}' não encontrada.")
    return db.query(DimensoesKpis).filter(DimensoesKpis.fk_gerencia == gerenciacao_uuid).all()

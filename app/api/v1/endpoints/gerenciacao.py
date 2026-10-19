"""
Endpoints de Analytics Determinístico (SNAPSHOT_NPS), IA Qualitativa (PROMPT, VERSAO_MODELO,
JOB_IA, ANALISE_FEEDBACK), Golden Set, Circuit Breaker, Telemetria e Auditoria — NPS KeyCore v1.0.
"""
from datetime import date, datetime
from typing import List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.errors import ConflictError, NotFoundError
from app.core.security import registrar_auditoria, require_roles
from app.models.models import (
    AnaliseFeedback,
    AvaliacaoGoldenSet,
    ComentarioGoldenSet,
    EventoCircuitBreaker,
    JobIa,
    LogAuditoria,
    LogExportacao,
    Pesquisa,
    Prompt,
    SnapshotNps,
    SnapshotTelemetria,
    Submissao,
    Usuario,
    VersaoModelo,
)
from app.schemas.schemas import (
    AnaliseFeedbackResponse,
    ComentarioGoldenSetCreate,
    ComentarioGoldenSetResponse,
    EventoCircuitBreakerResponse,
    JobIaResponse,
    LogAuditoriaResponse,
    LogExportacaoResponse,
    PromptCreate,
    PromptResponse,
    SnapshotNpsResponse,
    SnapshotTelemetriaResponse,
    VersaoModeloCreate,
    VersaoModeloResponse,
)
from app.services.ia_service import calcular_nps_deterministico, processar_job_ia_background

router = APIRouter()


# ══════════════════════════════════════════════════════════════════
# 1. ANALYTICS E CÁLCULO DETERMINÍSTICO DE NPS (RF-014 a RF-017)
# ══════════════════════════════════════════════════════════════════

@router.get(
    "/analytics/overview",
    summary="Dashboard Geral: NPS determinístico global, volume, classificação e temas IA",
    tags=["Analytics e NPS"],
)
def analytics_overview(
    data_inicio: Optional[date] = None,
    data_fim: Optional[date] = None,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(require_roles("ADMIN", "ANALYST")),
):
    """
    Calcula o NPS oficial de forma 100% determinística no backend/banco (Prioritariamente agregado - LGPD).
    Fórmula: % Promotores (9-10) - % Detratores (0-6), faixa [-100, +100].
    """
    q = db.query(Submissao).filter(Submissao.status == "VALIDA")
    if data_inicio:
        q = q.filter(Submissao.criada_em >= datetime.combine(data_inicio, datetime.min.time()))
    if data_fim:
        q = q.filter(Submissao.criada_em <= datetime.combine(data_fim, datetime.max.time()))

    notas = [row.nota_nps for row in q.all()]
    metricas_nps = calcular_nps_deterministico(notas)

    # Agregado derivado de IA (nunca interfere no cálculo oficial do NPS)
    analises = db.query(AnaliseFeedback).filter(AnaliseFeedback.status == "CONCLUIDA").all()
    sentimentos = {"POSITIVO": 0, "NEUTRO": 0, "NEGATIVO": 0}
    temas: dict[str, int] = {}
    for a in analises:
        sentimentos[a.sentimento] = sentimentos.get(a.sentimento, 0) + 1
        temas[a.tema] = temas.get(a.tema, 0) + 1

    return {
        "nucleo_deterministico_nps": metricas_nps,
        "total_pesquisas_ativas": db.query(Pesquisa).filter(Pesquisa.status == "PUBLICADA").count(),
        "camada_qualitativa_ia": {
            "total_analises_concluidas": len(analises),
            "distribuicao_sentimento": sentimentos,
            "distribuicao_temas": temas,
        },
    }


@router.get(
    "/analytics/surveys/{pesquisa_id}",
    response_model=SnapshotNpsResponse,
    summary="Calcular NPS determinístico de uma pesquisa e registrar SNAPSHOT_NPS",
    tags=["Analytics e NPS"],
)
def analytics_por_pesquisa(
    pesquisa_id: str,
    periodo_inicio: Optional[date] = None,
    periodo_fim: Optional[date] = None,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(require_roles("ADMIN", "ANALYST")),
):
    pesquisa = db.query(Pesquisa).filter(Pesquisa.id == pesquisa_id).first()
    if not pesquisa:
        raise NotFoundError(f"Pesquisa '{pesquisa_id}' não encontrada.")

    q = db.query(Submissao).filter(
        Submissao.id_pesquisa == pesquisa_id,
        Submissao.status == "VALIDA",
    )
    dt_ini = periodo_inicio or pesquisa.criada_em.date()
    dt_fim = periodo_fim or date.today()

    if periodo_inicio:
        q = q.filter(Submissao.criada_em >= datetime.combine(periodo_inicio, datetime.min.time()))
    if periodo_fim:
        q = q.filter(Submissao.criada_em <= datetime.combine(periodo_fim, datetime.max.time()))

    notas = [s.nota_nps for s in q.all()]
    calc = calcular_nps_deterministico(notas)

    snapshot = SnapshotNps(
        id_pesquisa=pesquisa_id,
        periodo_inicio=dt_ini,
        periodo_fim=dt_fim,
        valor_nps=calc["valor_nps"],
        total_respostas=calc["total_respostas"],
        qtd_promotores=calc["qtd_promotores"],
        qtd_neutros=calc["qtd_neutros"],
        qtd_detratores=calc["qtd_detratores"],
    )
    db.add(snapshot)
    db.commit()
    db.refresh(snapshot)

    resp = SnapshotNpsResponse.model_validate(snapshot)
    resp.pct_promotores = calc["pct_promotores"]
    resp.pct_neutros = calc["pct_neutros"]
    resp.pct_detratores = calc["pct_detratores"]
    return resp


@router.get(
    "/analytics/surveys/{pesquisa_id}/historico",
    response_model=List[SnapshotNpsResponse],
    summary="Listar série histórica de SNAPSHOT_NPS de uma pesquisa (RF-017)",
    tags=["Analytics e NPS"],
)
def listar_historico_snapshots(
    pesquisa_id: str,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(require_roles("ADMIN", "ANALYST")),
):
    return (
        db.query(SnapshotNps)
        .filter(SnapshotNps.id_pesquisa == pesquisa_id)
        .order_by(SnapshotNps.calculado_em.desc())
        .all()
    )


# ══════════════════════════════════════════════════════════════════
# 2. GOVERNANÇA DE IA: PROMPTS, VERSÕES DE MODELO, JOBS E ANÁLISES
# ══════════════════════════════════════════════════════════════════

@router.post(
    "/prompts",
    response_model=PromptResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Cadastrar novo Prompt para análise qualitativa (Requer ADMIN)",
    tags=["Governança de IA"],
)
def criar_prompt(
    payload: PromptCreate,
    db: Session = Depends(get_db),
    admin: Usuario = Depends(require_roles("ADMIN")),
):
    novo = Prompt(**payload.model_dump())
    db.add(novo)
    db.commit()
    db.refresh(novo)
    return novo


@router.get(
    "/prompts",
    response_model=List[PromptResponse],
    summary="Listar Prompts cadastrados (Requer ADMIN ou ANALYST)",
    tags=["Governança de IA"],
)
def listar_prompts(
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(require_roles("ADMIN", "ANALYST")),
):
    return db.query(Prompt).order_by(Prompt.criado_em.desc()).all()


@router.post(
    "/versoes-modelo",
    response_model=VersaoModeloResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Registrar nova versão de modelo de IA (Requer ADMIN)",
    tags=["Governança de IA"],
)
def criar_versao_modelo(
    payload: VersaoModeloCreate,
    db: Session = Depends(get_db),
    admin: Usuario = Depends(require_roles("ADMIN")),
):
    if db.query(VersaoModelo).filter(VersaoModelo.rotulo_versao == payload.rotulo_versao).first():
        raise ConflictError(f"Rótulo de versão '{payload.rotulo_versao}' já existe.")

    if payload.ativa:
        db.query(VersaoModelo).update({"ativa": False})

    versao = VersaoModelo(**payload.model_dump())
    db.add(versao)
    db.commit()
    db.refresh(versao)
    return versao


@router.get(
    "/versoes-modelo",
    response_model=List[VersaoModeloResponse],
    summary="Listar versões de modelo de IA (Requer ADMIN ou ANALYST)",
    tags=["Governança de IA"],
)
def listar_versoes_modelo(
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(require_roles("ADMIN", "ANALYST")),
):
    return db.query(VersaoModelo).order_by(VersaoModelo.promovida_em.desc()).all()


@router.get(
    "/ia/jobs",
    response_model=List[JobIaResponse],
    summary="Listar fila de jobs assíncronos da IA (JOB_IA)",
    tags=["Governança de IA"],
)
def listar_jobs_ia(
    status_filtro: Optional[str] = None,
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(require_roles("ADMIN", "ANALYST")),
):
    q = db.query(JobIa)
    if status_filtro:
        q = q.filter(JobIa.status == status_filtro.upper())
    return q.order_by(JobIa.criado_em.desc()).offset(skip).limit(min(limit, 100)).all()


@router.post(
    "/ia/jobs/{job_id}/reprocessar",
    response_model=JobIaResponse,
    summary="Reprocessar Job de IA (Gera nova sequencia_versao em ANALISE_FEEDBACK sem duplicar)",
    tags=["Governança de IA"],
)
async def reprocessar_job_ia(
    job_id: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(require_roles("ADMIN", "ANALYST")),
):
    job = db.query(JobIa).filter(JobIa.id == job_id).first()
    if not job:
        raise NotFoundError(f"Job IA '{job_id}' não encontrado.")
    job.status = "NA_FILA"
    db.commit()
    db.refresh(job)
    background_tasks.add_task(processar_job_ia_background, job.id)
    return job


@router.get(
    "/ia/analises-feedback",
    response_model=List[AnaliseFeedbackResponse],
    summary="Listar análises qualitativas derivadas da IA (ANALISE_FEEDBACK)",
    tags=["Governança de IA"],
)
def listar_analises_feedback(
    id_submissao: Optional[str] = None,
    sentimento: Optional[str] = None,
    tema: Optional[str] = None,
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(require_roles("ADMIN", "ANALYST")),
):
    q = db.query(AnaliseFeedback)
    if id_submissao:
        q = q.filter(AnaliseFeedback.id_submissao == id_submissao)
    if sentimento:
        q = q.filter(AnaliseFeedback.sentimento == sentimento.upper())
    if tema:
        q = q.filter(AnaliseFeedback.tema == tema.upper())
    return q.order_by(AnaliseFeedback.criada_em.desc()).offset(skip).limit(min(limit, 100)).all()


# ══════════════════════════════════════════════════════════════════
# 3. GOLDEN SET, CIRCUIT BREAKER, TELEMETRIA E AUDITORIA (RF-020)
# ══════════════════════════════════════════════════════════════════

@router.post(
    "/golden-set/comentarios",
    response_model=ComentarioGoldenSetResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Adicionar comentário ao Golden Set para calibração da IA (Requer ADMIN)",
    tags=["Golden Set e Observabilidade"],
)
def criar_comentario_golden(
    payload: ComentarioGoldenSetCreate,
    db: Session = Depends(get_db),
    admin: Usuario = Depends(require_roles("ADMIN")),
):
    item = ComentarioGoldenSet(**payload.model_dump())
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@router.get(
    "/golden-set/comentarios",
    response_model=List[ComentarioGoldenSetResponse],
    summary="Listar comentários do Golden Set",
    tags=["Golden Set e Observabilidade"],
)
def listar_comentarios_golden(
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(require_roles("ADMIN", "ANALYST")),
):
    return db.query(ComentarioGoldenSet).all()


@router.get(
    "/circuit-breaker",
    response_model=List[EventoCircuitBreakerResponse],
    summary="Listar eventos de Circuit Breaker de IA",
    tags=["Golden Set e Observabilidade"],
)
def listar_circuit_breaker(
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(require_roles("ADMIN", "ANALYST")),
):
    return db.query(EventoCircuitBreaker).order_by(EventoCircuitBreaker.disparado_em.desc()).all()


@router.get(
    "/telemetria",
    response_model=List[SnapshotTelemetriaResponse],
    summary="Listar snapshots de telemetria (latência p50/p95, taxa 5xx, falhas PII)",
    tags=["Golden Set e Observabilidade"],
)
def listar_telemetria(
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(require_roles("ADMIN", "ANALYST")),
):
    return db.query(SnapshotTelemetria).order_by(SnapshotTelemetria.inicio_janela.desc()).limit(50).all()


@router.get(
    "/audit-logs",
    response_model=List[LogAuditoriaResponse],
    summary="Consultar trilha de auditoria imutável (Requer ADMIN - RF-020)",
    tags=["Auditoria e LGPD"],
)
def listar_logs_auditoria(
    acao: Optional[str] = None,
    tipo_entidade: Optional[str] = None,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    admin: Usuario = Depends(require_roles("ADMIN")),
):
    q = db.query(LogAuditoria)
    if acao:
        q = q.filter(LogAuditoria.acao == acao)
    if tipo_entidade:
        q = q.filter(LogAuditoria.tipo_entidade == tipo_entidade.upper())
    return q.order_by(LogAuditoria.criado_em.desc()).offset(skip).limit(min(limit, 200)).all()


@router.get(
    "/export-logs",
    response_model=List[LogExportacaoResponse],
    summary="Consultar registro de exportações CSV para conformidade LGPD (Requer ADMIN)",
    tags=["Auditoria e LGPD"],
)
def listar_logs_exportacao(
    db: Session = Depends(get_db),
    admin: Usuario = Depends(require_roles("ADMIN")),
):
    return db.query(LogExportacao).order_by(LogExportacao.criado_em.desc()).limit(100).all()

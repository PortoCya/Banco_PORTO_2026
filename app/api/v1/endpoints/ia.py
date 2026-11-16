"""
Endpoints — Camada de IA (análises sugeridas, modelos, golden set, custo).

A API nunca chama o provedor de IA: ela só lê/gera estado no banco e publica
ids na fila. Quem fala com o provedor é o worker, em outro processo.
"""
import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import Paginacao, paginacao, requer_papel
from app.core.config import settings
from app.core.database import get_db
from app.core.errors import ConflictError, NotFoundError, ServiceUnavailableError
from app.models.models import (
    AnaliseFeedback, AvaliacaoGoldenSet, ComentarioGoldenSet,
    EventoCircuitBreaker, JobIa, Pesquisa, Prompt, SnapshotTelemetria, Submissao, Usuario,
    VersaoModelo, agora_utc,
)
from app.schemas.schemas import (
    AnaliseFeedbackResponse, AnaliseFeedbackUpdate, AvaliacaoGoldenSetCreate,
    AvaliacaoGoldenSetResponse, AvaliacaoSolicitadaResponse, ComentarioGoldenSetCreate,
    ComentarioGoldenSetResponse, EventoCircuitBreakerResponse, JobIaResponse,
    LimiteCustoResponse, LimiteCustoUpdate, PromptCreate, PromptResponse,
    ResumoAnalisesResponse, Sentimento, SnapshotTelemetriaResponse, StatusAnalise, StatusJobIa, Tema,
    VersaoModeloCreate, VersaoModeloResponse,
)
from app.services import custo_ia, fila
from app.services.auditoria import estado_versao_modelo, registrar_auditoria
from app.services.pii import texto_anonimizado

router = APIRouter()

_admin = requer_papel("ADMIN")
_analyst = requer_papel("ANALYST")
_leitura = requer_papel("ADMIN", "ANALYST")

_TAG_ANALISES = ["IA — análises sugeridas"]
_TAG_GESTAO = ["IA — gestão (ADMIN)"]


def _ultima_sequencia():
    """Subconsulta: a maior sequencia_versao de cada submissão (a análise vigente)."""
    return (
        select(
            AnaliseFeedback.id_submissao.label("id_submissao"),
            func.max(AnaliseFeedback.sequencia_versao).label("sequencia"),
        )
        .group_by(AnaliseFeedback.id_submissao)
        .subquery()
    )


def _exigir_pesquisa(db: Session, id_pesquisa: uuid.UUID) -> None:
    if db.execute(select(Pesquisa.id).where(Pesquisa.id == id_pesquisa)).first() is None:
        raise NotFoundError("Pesquisa não encontrada.")


def _resposta_analise(analise: AnaliseFeedback, nota_nps: int, comentario: Optional[str]) -> AnaliseFeedbackResponse:
    return AnaliseFeedbackResponse(
        id=analise.id,
        id_submissao=analise.id_submissao,
        id_versao_modelo=analise.id_versao_modelo,
        sentimento=analise.sentimento,
        tema=analise.tema,
        confianca=analise.confianca,
        justificativa=analise.justificativa,
        sequencia_versao=analise.sequencia_versao,
        status=analise.status,
        nota_nps=nota_nps,
        texto_comentario=texto_anonimizado(comentario),
        criada_em=analise.criada_em,
        atualizada_em=analise.atualizada_em,
    )


# ══════════════════════════════════════════════════════════════════
# Análises sugeridas
# ══════════════════════════════════════════════════════════════════

@router.get("/pesquisas/{id_pesquisa}/analises-feedback", response_model=List[AnaliseFeedbackResponse],
            summary="Análises sugeridas pela IA (a mais recente de cada resposta)",
            tags=_TAG_ANALISES, dependencies=[Depends(_leitura)])
def listar_analises(
    id_pesquisa: uuid.UUID,
    status_analise: Optional[StatusAnalise] = Query(None, alias="status"),
    sentimento: Optional[Sentimento] = None,
    tema: Optional[Tema] = None,
    pag: Paginacao = Depends(paginacao),
    db: Session = Depends(get_db),
):
    """
    Uma única consulta traz análise + nota + comentário (sem N+1). O comentário
    sai com PII mascarada. **Códigos:** 200 | 401 | 403 | 404 | 422
    """
    _exigir_pesquisa(db, id_pesquisa)
    ultima = _ultima_sequencia()
    consulta = (
        select(AnaliseFeedback, Submissao.nota_nps, Submissao.texto_comentario)
        .join(Submissao, Submissao.id == AnaliseFeedback.id_submissao)
        .join(ultima, (ultima.c.id_submissao == AnaliseFeedback.id_submissao)
              & (ultima.c.sequencia == AnaliseFeedback.sequencia_versao))
        .where(Submissao.id_pesquisa == id_pesquisa)
    )
    if status_analise:
        consulta = consulta.where(AnaliseFeedback.status == status_analise)
    if sentimento:
        consulta = consulta.where(AnaliseFeedback.sentimento == sentimento)
    if tema:
        consulta = consulta.where(AnaliseFeedback.tema == tema)
    consulta = consulta.order_by(Submissao.criada_em.desc(), Submissao.id).offset(pag.skip).limit(pag.limit)
    return [_resposta_analise(a, nota, comentario) for a, nota, comentario in db.execute(consulta)]


@router.get("/pesquisas/{id_pesquisa}/analises-feedback/resumo", response_model=ResumoAnalisesResponse,
            summary="Contagem de sentimento e tema (só análises CONCLUIDA)",
            tags=_TAG_ANALISES, dependencies=[Depends(_leitura)])
def resumo_analises(id_pesquisa: uuid.UUID, db: Session = Depends(get_db)):
    """BAIXA_CONFIANCA, descartadas e falhas ficam fora das contagens. **Códigos:** 200 | 401 | 403 | 404"""
    _exigir_pesquisa(db, id_pesquisa)
    ultima = _ultima_sequencia()
    linhas = db.execute(
        select(AnaliseFeedback.sentimento, AnaliseFeedback.tema, func.count())
        .join(Submissao, Submissao.id == AnaliseFeedback.id_submissao)
        .join(ultima, (ultima.c.id_submissao == AnaliseFeedback.id_submissao)
              & (ultima.c.sequencia == AnaliseFeedback.sequencia_versao))
        .where(Submissao.id_pesquisa == id_pesquisa, AnaliseFeedback.status == "CONCLUIDA")
        .group_by(AnaliseFeedback.sentimento, AnaliseFeedback.tema)
    ).all()
    por_sentimento: dict[str, int] = {}
    por_tema: dict[str, int] = {}
    for sentimento, tema, qtd in linhas:
        por_sentimento[sentimento] = por_sentimento.get(sentimento, 0) + qtd
        por_tema[tema] = por_tema.get(tema, 0) + qtd
    return ResumoAnalisesResponse(
        id_pesquisa=id_pesquisa,
        total_analises_concluidas=sum(por_sentimento.values()),
        por_sentimento=por_sentimento,
        por_tema=por_tema,
    )


@router.patch("/analises-feedback/{id_analise}", response_model=AnaliseFeedbackResponse,
              summary="Descartar ou corrigir uma análise sugerida", tags=_TAG_ANALISES)
def revisar_analise(
    id_analise: uuid.UUID,
    payload: AnaliseFeedbackUpdate,
    db: Session = Depends(get_db),
    analista: Usuario = Depends(_analyst),
):
    """
    Só a análise mais recente da resposta pode ser revisada. A revisão é
    auditada (antes/depois) e não mexe em nota nem em NPS.
    **Códigos:** 200 | 401 | 403 | 404 | 409 | 422
    """
    analise = db.execute(
        select(AnaliseFeedback).where(AnaliseFeedback.id == id_analise).with_for_update()
    ).scalar_one_or_none()
    if analise is None:
        raise NotFoundError("Análise não encontrada.")
    mais_recente = db.execute(
        select(func.max(AnaliseFeedback.sequencia_versao)).where(AnaliseFeedback.id_submissao == analise.id_submissao)
    ).scalar()
    if analise.sequencia_versao != mais_recente:
        raise ConflictError("Existe uma análise mais recente para esta resposta.")

    antes = {"status": analise.status, "sentimento": analise.sentimento, "tema": analise.tema}
    if payload.status == "DESCARTADA_MANUAL":
        analise.status = "DESCARTADA_MANUAL"
    else:
        sentimento = payload.sentimento or analise.sentimento
        tema = payload.tema or analise.tema
        if sentimento is None or tema is None:
            raise ConflictError("Esta análise não tem sugestão da IA: informe sentimento e tema.")
        analise.sentimento, analise.tema, analise.status = sentimento, tema, "CONCLUIDA"
    registrar_auditoria(
        db, analista, "REVISAR_ANALISE_FEEDBACK", "ANALISE_FEEDBACK", analise.id,
        estado_antes=antes,
        estado_depois={"status": analise.status, "sentimento": analise.sentimento, "tema": analise.tema},
    )
    submissao = db.get(Submissao, analise.id_submissao)
    db.commit()
    return _resposta_analise(analise, submissao.nota_nps, submissao.texto_comentario)


# ══════════════════════════════════════════════════════════════════
# Prompts e versões de modelo
# ══════════════════════════════════════════════════════════════════

@router.post("/prompts", response_model=PromptResponse, status_code=status.HTTP_201_CREATED,
             summary="Cadastrar nova versão de prompt", tags=_TAG_GESTAO)
def criar_prompt(payload: PromptCreate, db: Session = Depends(get_db), admin: Usuario = Depends(_admin)):
    """**Códigos:** 201 | 401 | 403 | 422"""
    prompt = Prompt(id=uuid.uuid4(), **payload.model_dump())
    db.add(prompt)
    registrar_auditoria(db, admin, "CRIAR_PROMPT", "PROMPT", prompt.id, estado_depois=payload.model_dump())
    db.commit()
    return prompt


@router.get("/prompts", response_model=List[PromptResponse], summary="Listar prompts",
            tags=_TAG_GESTAO, dependencies=[Depends(_admin)])
def listar_prompts(pag: Paginacao = Depends(paginacao), db: Session = Depends(get_db)):
    """**Códigos:** 200 | 401 | 403 | 422"""
    return db.execute(
        select(Prompt).order_by(Prompt.criado_em.desc(), Prompt.id).offset(pag.skip).limit(pag.limit)
    ).scalars().all()


@router.post("/modelos-ia", response_model=VersaoModeloResponse, status_code=status.HTTP_201_CREATED,
             summary="Registrar versão de modelo (nasce inativa)", tags=_TAG_GESTAO)
def criar_modelo(payload: VersaoModeloCreate, db: Session = Depends(get_db), admin: Usuario = Depends(_admin)):
    """**Códigos:** 201 | 401 | 403 | 404 (prompt) | 409 (rótulo já existe) | 422"""
    if db.get(Prompt, payload.id_prompt) is None:
        raise NotFoundError("Prompt não encontrado.")
    versao = VersaoModelo(id=uuid.uuid4(), ativo=False, **payload.model_dump())
    db.add(versao)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise ConflictError("Rótulo de versão já existe.", field="rotulo_versao")
    registrar_auditoria(db, admin, "CRIAR_VERSAO_MODELO", "VERSAO_MODELO", versao.id,
                        estado_depois=estado_versao_modelo(versao))
    db.commit()
    return versao


@router.get("/modelos-ia", response_model=List[VersaoModeloResponse], summary="Listar versões de modelo",
            tags=_TAG_GESTAO, dependencies=[Depends(_admin)])
def listar_modelos(pag: Paginacao = Depends(paginacao), db: Session = Depends(get_db)):
    """**Códigos:** 200 | 401 | 403 | 422"""
    return db.execute(
        select(VersaoModelo).order_by(VersaoModelo.criada_em.desc(), VersaoModelo.id)
        .offset(pag.skip).limit(pag.limit)
    ).scalars().all()


@router.post("/modelos-ia/{id_versao_modelo}/ativar", response_model=VersaoModeloResponse,
             summary="Ativar versão de modelo (gate do golden set)", tags=_TAG_GESTAO)
def ativar_modelo(id_versao_modelo: uuid.UUID, db: Session = Depends(get_db), admin: Usuario = Depends(_admin)):
    """
    Só ativa se a ÚLTIMA avaliação da versão no golden set for APROVADO.
    Reprovada ou sem avaliação → 409 e a versão anterior continua ativa.
    Desativar a antiga, ativar a nova e auditar acontecem na mesma transação.

    **Códigos:** 200 | 401 | 403 | 404 | 409 | 422
    """
    versao = db.execute(
        select(VersaoModelo).where(VersaoModelo.id == id_versao_modelo).with_for_update()
    ).scalar_one_or_none()
    if versao is None:
        raise NotFoundError("Versão de modelo não encontrada.")
    ultima = db.execute(
        select(AvaliacaoGoldenSet.status)
        .where(AvaliacaoGoldenSet.id_versao_modelo == versao.id)
        .order_by(AvaliacaoGoldenSet.executada_em.desc())
        .limit(1)
    ).scalar_one_or_none()
    if ultima != "APROVADO":
        raise ConflictError("Modelo não aprovado no golden set. A versão ativa foi mantida.")
    if versao.ativo:
        return versao

    antes = estado_versao_modelo(versao)
    anterior = db.execute(select(VersaoModelo.id).where(VersaoModelo.ativo.is_(True))).scalar_one_or_none()
    db.execute(update(VersaoModelo).where(VersaoModelo.ativo.is_(True)).values(ativo=False))
    versao.ativo = True
    versao.promovida_em = agora_utc()
    depois = estado_versao_modelo(versao)
    depois["id_versao_anterior"] = str(anterior) if anterior else None
    registrar_auditoria(db, admin, "ATIVAR_VERSAO_MODELO", "VERSAO_MODELO", versao.id,
                        estado_antes=antes, estado_depois=depois)
    db.commit()
    return versao


# ══════════════════════════════════════════════════════════════════
# Golden set
# ══════════════════════════════════════════════════════════════════

@router.post("/golden-set/comentarios", response_model=ComentarioGoldenSetResponse,
             status_code=status.HTTP_201_CREATED, summary="Adicionar comentário rotulado ao golden set",
             tags=_TAG_GESTAO)
def criar_comentario_golden(
    payload: ComentarioGoldenSetCreate, db: Session = Depends(get_db), admin: Usuario = Depends(_admin),
):
    """**Códigos:** 201 | 401 | 403 | 422"""
    comentario = ComentarioGoldenSet(id=uuid.uuid4(), **payload.model_dump())
    db.add(comentario)
    registrar_auditoria(
        db, admin, "CRIAR_COMENTARIO_GOLDEN_SET", "COMENTARIO_GOLDEN_SET", comentario.id,
        estado_depois={"rotulo_sentimento_humano": comentario.rotulo_sentimento_humano,
                       "rotulo_tema_humano": comentario.rotulo_tema_humano},
    )
    db.commit()
    return comentario


@router.get("/golden-set/comentarios", response_model=List[ComentarioGoldenSetResponse],
            summary="Listar golden set", tags=_TAG_GESTAO, dependencies=[Depends(_admin)])
def listar_comentarios_golden(pag: Paginacao = Depends(paginacao), db: Session = Depends(get_db)):
    """**Códigos:** 200 | 401 | 403 | 422"""
    return db.execute(
        select(ComentarioGoldenSet).order_by(ComentarioGoldenSet.criado_em, ComentarioGoldenSet.id)
        .offset(pag.skip).limit(pag.limit)
    ).scalars().all()


@router.post("/golden-set/avaliacoes", response_model=AvaliacaoSolicitadaResponse,
             status_code=status.HTTP_202_ACCEPTED, summary="Pedir avaliação de uma versão no golden set",
             tags=_TAG_GESTAO)
def solicitar_avaliacao(
    payload: AvaliacaoGoldenSetCreate, db: Session = Depends(get_db), admin: Usuario = Depends(_admin),
):
    """
    A avaliação roda no worker (a API não chama o provedor). O resultado
    aparece em `GET /golden-set/avaliacoes`.

    **Códigos:** 202 | 401 | 403 | 404 | 409 (golden set incompleto) | 422 | 503 (fila indisponível)
    """
    if db.get(VersaoModelo, payload.id_versao_modelo) is None:
        raise NotFoundError("Versão de modelo não encontrada.")
    total = db.execute(select(func.count()).select_from(ComentarioGoldenSet)).scalar_one()
    if total < settings.GOLDEN_SET_MINIMO:
        raise ConflictError(
            f"Golden set incompleto: {total} de {settings.GOLDEN_SET_MINIMO} comentários rotulados."
        )
    registrar_auditoria(db, admin, "SOLICITAR_AVALIACAO_GOLDEN_SET", "VERSAO_MODELO", payload.id_versao_modelo)
    db.commit()
    if not fila.publicar_avaliacao(payload.id_versao_modelo):
        raise ServiceUnavailableError("Fila da IA indisponível. Tente novamente em instantes.", retry_after=30)
    return AvaliacaoSolicitadaResponse(id_versao_modelo=payload.id_versao_modelo)


@router.get("/golden-set/avaliacoes", response_model=List[AvaliacaoGoldenSetResponse],
            summary="Listar avaliações", tags=_TAG_GESTAO, dependencies=[Depends(_admin)])
def listar_avaliacoes(
    id_versao_modelo: Optional[uuid.UUID] = None,
    pag: Paginacao = Depends(paginacao),
    db: Session = Depends(get_db),
):
    """**Códigos:** 200 | 401 | 403 | 422"""
    consulta = select(AvaliacaoGoldenSet)
    if id_versao_modelo:
        consulta = consulta.where(AvaliacaoGoldenSet.id_versao_modelo == id_versao_modelo)
    consulta = consulta.order_by(AvaliacaoGoldenSet.executada_em.desc(), AvaliacaoGoldenSet.id)
    return db.execute(consulta.offset(pag.skip).limit(pag.limit)).scalars().all()


# ══════════════════════════════════════════════════════════════════
# Custo, circuit breaker, telemetria e jobs
# ══════════════════════════════════════════════════════════════════

def _estado_custo(db: Session) -> LimiteCustoResponse:
    try:
        return LimiteCustoResponse(
            limite_custo=custo_ia.obter_limite(),
            custo_acumulado=custo_ia.custo_acumulado(),
            circuit_breaker_aberto=custo_ia.evento_aberto(db) is not None,
        )
    except custo_ia.CustoIndisponivel:
        raise ServiceUnavailableError("Controle de custo da IA indisponível.", retry_after=30)


@router.get("/ia/limite-custo", response_model=LimiteCustoResponse, summary="Limite e custo acumulado do mês",
            tags=_TAG_GESTAO, dependencies=[Depends(_admin)])
def consultar_limite_custo(db: Session = Depends(get_db)):
    """**Códigos:** 200 | 401 | 403 | 503 (Redis indisponível)"""
    return _estado_custo(db)


@router.put("/ia/limite-custo", response_model=LimiteCustoResponse, summary="Definir o limite de custo da IA",
            tags=_TAG_GESTAO)
def definir_limite_custo(payload: LimiteCustoUpdate, db: Session = Depends(get_db), admin: Usuario = Depends(_admin)):
    """
    Se o novo limite ficar acima do custo acumulado, os eventos de circuit
    breaker abertos são resolvidos e os envios voltam.

    **Códigos:** 200 | 401 | 403 | 422 | 503 (Redis indisponível)
    """
    try:
        anterior = custo_ia.obter_limite()
        acumulado = custo_ia.custo_acumulado()
        custo_ia.definir_limite(payload.limite_custo)
    except custo_ia.CustoIndisponivel:
        raise ServiceUnavailableError("Controle de custo da IA indisponível.", retry_after=30)

    resolvidos = 0
    if payload.limite_custo > acumulado:
        resolvidos = db.execute(
            update(EventoCircuitBreaker)
            .where(EventoCircuitBreaker.resolvido_em.is_(None))
            .values(resolvido_em=agora_utc())
        ).rowcount
    # A configuração não é uma linha de tabela: o id nulo marca "configuração global"
    registrar_auditoria(
        db, admin, "DEFINIR_LIMITE_CUSTO_IA", "CONFIGURACAO_IA", uuid.UUID(int=0),
        estado_antes={"limite_custo": anterior},
        estado_depois={"limite_custo": payload.limite_custo, "eventos_resolvidos": resolvidos},
    )
    db.commit()
    return _estado_custo(db)


@router.get("/ia/circuit-breaker/eventos", response_model=List[EventoCircuitBreakerResponse],
            summary="Eventos de circuit breaker", tags=_TAG_GESTAO, dependencies=[Depends(_admin)])
def listar_eventos_circuit_breaker(pag: Paginacao = Depends(paginacao), db: Session = Depends(get_db)):
    """**Códigos:** 200 | 401 | 403 | 422"""
    return db.execute(
        select(EventoCircuitBreaker)
        .order_by(EventoCircuitBreaker.disparado_em.desc(), EventoCircuitBreaker.id)
        .offset(pag.skip).limit(pag.limit)
    ).scalars().all()


@router.get("/ia/telemetria", response_model=List[SnapshotTelemetriaResponse], summary="Snapshots de telemetria",
            tags=_TAG_GESTAO, dependencies=[Depends(_admin)])
def listar_telemetria(pag: Paginacao = Depends(paginacao), db: Session = Depends(get_db)):
    """**Códigos:** 200 | 401 | 403 | 422"""
    return db.execute(
        select(SnapshotTelemetria)
        .order_by(SnapshotTelemetria.inicio_janela.desc(), SnapshotTelemetria.id)
        .offset(pag.skip).limit(pag.limit)
    ).scalars().all()


@router.get("/ia/jobs", response_model=List[JobIaResponse], summary="Fila de jobs da IA",
            tags=_TAG_GESTAO, dependencies=[Depends(_admin)])
def listar_jobs(
    status_job: Optional[StatusJobIa] = Query(None, alias="status"),
    pag: Paginacao = Depends(paginacao),
    db: Session = Depends(get_db),
):
    """**Códigos:** 200 | 401 | 403 | 422"""
    consulta = select(JobIa)
    if status_job:
        consulta = consulta.where(JobIa.status == status_job)
    consulta = consulta.order_by(JobIa.criado_em.desc(), JobIa.id)
    return db.execute(consulta.offset(pag.skip).limit(pag.limit)).scalars().all()


@router.post("/ia/jobs/{id_job}/reprocessar", response_model=JobIaResponse, status_code=status.HTTP_202_ACCEPTED,
             summary="Reanalisar a resposta de um job", tags=_TAG_GESTAO)
def reprocessar_job(id_job: uuid.UUID, db: Session = Depends(get_db), admin: Usuario = Depends(_admin)):
    """
    Cria um NOVO job para a mesma resposta; a reanálise gera nova linha em
    ANALISE_FEEDBACK com `sequencia_versao` maior (o histórico fica).

    **Códigos:** 202 | 401 | 403 | 404 | 409 (já existe job em andamento) | 422
    """
    job = db.execute(select(JobIa).where(JobIa.id == id_job).with_for_update()).scalar_one_or_none()
    if job is None:
        raise NotFoundError("Job não encontrado.")
    em_andamento = db.execute(
        select(JobIa.id).where(
            JobIa.id_submissao == job.id_submissao,
            JobIa.status.in_(("NA_FILA", "PROCESSANDO", "TENTANDO_NOVAMENTE")),
        ).limit(1)
    ).first()
    if em_andamento is not None:
        raise ConflictError("Já existe um job em andamento para esta resposta.")
    novo = JobIa(id=uuid.uuid4(), id_submissao=job.id_submissao, status="NA_FILA", proxima_tentativa_em=agora_utc())
    db.add(novo)
    registrar_auditoria(db, admin, "REPROCESSAR_JOB_IA", "JOB_IA", novo.id,
                        estado_depois={"id_submissao": str(job.id_submissao), "id_job_origem": str(job.id)})
    db.commit()
    fila.publicar_analise(novo.id_submissao)
    return novo

"""
Endpoints — Conversas e consulta principal à IA.
Fluxo: Frontend → /conversas/consultar → LOA_PUNICAO → GERENCIACAO → SOA_IA → IA → ANALISE_FEEDBACK → resposta
"""
import logging
import uuid as uuid_lib
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, Query, status, BackgroundTasks
from sqlalchemy.orm import Session

from app.api.deps import buscar_conversa_do_usuario, buscar_gerenciacao_do_usuario, get_usuario_atual
from app.core.database import SessionLocal, get_db
from app.models.models import (
    Conversa, LoaPunicao, Gerenciacao, SoaIa, AnaliseFeedback, Prompt, VideoModelo, Usuario,
)
from app.schemas.schemas import (
    ConversaCreate, ConversaResponse,
    MensagemInput, ConsultaIAResponse,
    LoaPunicaoCreate, LoaPunicaoResponse,
    AnaliseFeedbackCreate, AnaliseFeedbackResponse,
)
from app.services.ia_service import gerar_resposta_ia, analisar_sentimento

logger = logging.getLogger(__name__)

# Todas as rotas deste arquivo exigem login
router = APIRouter(dependencies=[Depends(get_usuario_atual)])


# ══════════════════════════════════════════════════════════════════
# CONVERSAS — CRUD
# ══════════════════════════════════════════════════════════════════

@router.post(
    "/conversas",
    response_model=ConversaResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Criar nova conversa",
    tags=["Conversas"],
)
def criar_conversa(
    payload: ConversaCreate,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_atual),
):
    """
    **Recebe:** titulo, tipo_consultor, configuracoes (o dono é o usuário logado)
    **Retorna:** objeto da conversa criada
    **Códigos:** 201 | 401 | 422
    """
    conversa = Conversa(**payload.model_dump(), fk_usuario=usuario.uuid)
    db.add(conversa)
    db.commit()
    db.refresh(conversa)
    return conversa


@router.get(
    "/conversas",
    response_model=List[ConversaResponse],
    summary="Listar conversas",
    tags=["Conversas"],
)
def listar_conversas(
    fk_usuario: Optional[str] = None,
    status: Optional[str] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_atual),
):
    """
    **Recebe:** filtros opcionais fk_usuario (só ADMIN) e status
    **Retorna:** lista paginada de conversas
    **Códigos:** 200 | 401
    """
    q = db.query(Conversa)
    if usuario.papel != "ADMIN":
        q = q.filter(Conversa.fk_usuario == usuario.uuid)
    elif fk_usuario:
        q = q.filter(Conversa.fk_usuario == fk_usuario)
    if status:
        q = q.filter(Conversa.status == status)
    return q.offset(skip).limit(limit).all()


@router.get(
    "/conversas/{uuid}",
    response_model=ConversaResponse,
    summary="Buscar conversa por UUID",
    tags=["Conversas"],
)
def buscar_conversa(
    uuid: str,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_atual),
):
    """
    **Recebe:** uuid no path
    **Retorna:** objeto da conversa
    **Códigos:** 200 | 401 | 404
    """
    return buscar_conversa_do_usuario(db, uuid, usuario)


# ══════════════════════════════════════════════════════════════════
# ENDPOINT PRINCIPAL — CONSULTA À IA
# Fluxo completo: Frontend → API → Gerenciacao → SOA_IA → IA → AnaliseFeedback → Resposta
# ══════════════════════════════════════════════════════════════════

@router.post(
    "/conversas/consultar",
    response_model=ConsultaIAResponse,
    status_code=status.HTTP_200_OK,
    summary="Enviar mensagem e obter resposta da IA",
    tags=["Consulta IA"],
)
async def consultar_ia(
    payload: MensagemInput,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_atual),
):
    """
    **Fluxo completo:**
    1. Valida a conversa
    2. Registra LOA_PUNICAO com o input
    3. Cria GERENCIACAO (sessão de processamento)
    4. Cria SOA_IA com status PROCESSANDO
    5. Busca o prompt ativo do modelo IA atual
    6. Chama a IA (OpenAI)
    7. Atualiza SOA_IA → CONCLUIDO
    8. Agenda análise de feedback em background
    9. Retorna a resposta

    **Recebe:** conversa_uuid, mensagem, tipo_consultor (opcional)
    **Retorna:** resposta da IA + metadados de uso
    **Códigos:** 200 | 401 | 404 | 422 | 502 | 503 | 504
    """
    # 1. Valida conversa
    conversa = buscar_conversa_do_usuario(db, payload.conversa_uuid, usuario)

    # 2. Registra LOA_PUNICAO (atributos de entrada)
    loa = LoaPunicao(
        fk_conversa_set=conversa.uuid,
        tipo="CONSULTA_USUARIO",
        boolean_status=True,
        metodo_ativo=payload.tipo_consultor or conversa.tipo_consultor,
    )
    db.add(loa)
    db.flush()

    # 3. Cria GERENCIACAO
    gerenciacao = Gerenciacao(
        fk_pessoa=conversa.fk_usuario,
        fk_loa_punicao=loa.uuid,
        tipo_pot="Q",
        status="PROCESSANDO",
        chave_referencia=str(uuid_lib.uuid4()),
    )
    db.add(gerenciacao)
    db.flush()

    # 4. Cria SOA_IA
    soa = SoaIa(
        fk_gerenciacao=gerenciacao.uuid,
        status="PROCESSANDO",
        allow_queue=True,
    )
    db.add(soa)
    db.commit()

    # 5. Busca prompt ativo
    modelo_atual = db.query(VideoModelo).filter(VideoModelo.is_current == True).first()
    prompt_obj = None
    if modelo_atual:
        prompt_obj = (
            db.query(Prompt)
            .filter(Prompt.fk_video_modelo == modelo_atual.uuid, Prompt.status_ativo == True)
            .first()
        )

    prompt_sistema = (
        prompt_obj.conteudo if prompt_obj
        else "Você é um consultor especializado. Responda de forma clara e objetiva."
    )

    # 6. Chama a IA (erros tratados em ia_service → propagados para error handlers).
    # Se falhar, marca FALHA antes de propagar, para não ficar PROCESSANDO para sempre.
    try:
        resultado_ia = await gerar_resposta_ia(
            prompt_sistema=prompt_sistema,
            mensagem_usuario=payload.mensagem,
        )
    except Exception:
        soa.status = "FALHA"
        gerenciacao.status = "FALHA"
        db.commit()
        raise

    # 7. Atualiza SOA_IA
    soa.status = "CONCLUIDO"
    gerenciacao.status = "CONCLUIDO"
    db.commit()
    db.refresh(soa)

    # 8. Análise de feedback em background (não bloqueia a resposta)
    background_tasks.add_task(
        _salvar_analise_feedback,
        gerenciacao_uuid=gerenciacao.uuid,
        texto=payload.mensagem + " " + resultado_ia["content"],
        fk_video_modelo=modelo_atual.uuid if modelo_atual else None,
    )

    return ConsultaIAResponse(
        gerenciacao_uuid=gerenciacao.uuid,
        soa_ia_uuid=soa.uuid,
        resposta=resultado_ia["content"],
        tokens_entrada=resultado_ia["tokens_entrada"],
        tokens_saida=resultado_ia["tokens_saida"],
        modelo_utilizado=resultado_ia["modelo_utilizado"],
        finish_reason=resultado_ia["finish_reason"],
        created_at=datetime.now(timezone.utc),
    )


async def _salvar_analise_feedback(gerenciacao_uuid: str, texto: str, fk_video_modelo: str = None):
    """Tarefa de background: analisa sentimento e persiste ANALISE_FEEDBACK."""
    db = SessionLocal()
    try:
        resultado = await analisar_sentimento(texto)   # já validado pelo Pydantic
        db.add(AnaliseFeedback(
            fk_gerenciacao=gerenciacao_uuid,
            fk_video_modelo=fk_video_modelo,
            **resultado,
            status="CONCLUIDO",
        ))
        db.commit()
    except Exception as exc:
        # Só o tipo: a mensagem pode trazer trechos do texto analisado
        logger.error("Erro ao salvar análise de feedback (%s)", type(exc).__name__)
        db.rollback()
    finally:
        db.close()


# ══════════════════════════════════════════════════════════════════
# LOA_PUNICAO
# ══════════════════════════════════════════════════════════════════

@router.post(
    "/loa-punicao",
    response_model=LoaPunicaoResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Registrar LOA / Punição",
    tags=["LOA Punição"],
)
def criar_loa_punicao(
    payload: LoaPunicaoCreate,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_atual),
):
    """
    **Recebe:** fk_conversa_set, tipo, boolean_status, valor, metodo_ativo
    **Retorna:** registro criado
    **Códigos:** 201 | 401 | 404 | 422
    """
    buscar_conversa_do_usuario(db, payload.fk_conversa_set, usuario)
    loa = LoaPunicao(**payload.model_dump())
    db.add(loa)
    db.commit()
    db.refresh(loa)
    return loa


@router.get(
    "/loa-punicao/{conversa_uuid}",
    response_model=List[LoaPunicaoResponse],
    summary="Listar LOAs de uma conversa",
    tags=["LOA Punição"],
)
def listar_loa_punicao(
    conversa_uuid: str,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_atual),
):
    """
    **Recebe:** conversa_uuid no path
    **Retorna:** lista de LOAs associadas
    **Códigos:** 200 | 401 | 404
    """
    buscar_conversa_do_usuario(db, conversa_uuid, usuario)
    return db.query(LoaPunicao).filter(LoaPunicao.fk_conversa_set == conversa_uuid).all()


# ══════════════════════════════════════════════════════════════════
# ANALISE_FEEDBACK
# ══════════════════════════════════════════════════════════════════

@router.get(
    "/analises-feedback",
    response_model=List[AnaliseFeedbackResponse],
    summary="Listar análises de feedback",
    tags=["Análise Feedback"],
)
def listar_analises_feedback(
    fk_gerenciacao: Optional[str] = None,
    sentimento: Optional[str] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_atual),
):
    """
    **Recebe:** filtros opcionais fk_gerenciacao e sentimento
    **Retorna:** lista paginada (só das gerenciações do usuário, exceto ADMIN)
    **Códigos:** 200 | 401
    """
    q = db.query(AnaliseFeedback)
    if usuario.papel != "ADMIN":
        q = q.join(Gerenciacao, AnaliseFeedback.fk_gerenciacao == Gerenciacao.uuid) \
             .filter(Gerenciacao.fk_pessoa == usuario.uuid)
    if fk_gerenciacao:
        q = q.filter(AnaliseFeedback.fk_gerenciacao == fk_gerenciacao)
    if sentimento:
        q = q.filter(AnaliseFeedback.sentimento == sentimento)
    return q.offset(skip).limit(limit).all()


@router.post(
    "/analises-feedback",
    response_model=AnaliseFeedbackResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Solicitar análise de feedback manualmente",
    tags=["Análise Feedback"],
)
async def criar_analise_feedback(
    payload: AnaliseFeedbackCreate,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_atual),
):
    """
    Dispara análise de sentimento via IA manualmente.
    **Recebe:** fk_gerenciacao, fk_video_modelo, texto_para_analisar
    **Retorna:** resultado da análise
    **Códigos:** 201 | 401 | 404 | 422 | 502 | 503
    """
    buscar_gerenciacao_do_usuario(db, payload.fk_gerenciacao, usuario)
    resultado = await analisar_sentimento(payload.texto_para_analisar)
    fb = AnaliseFeedback(
        fk_gerenciacao=payload.fk_gerenciacao,
        fk_video_modelo=payload.fk_video_modelo,
        **resultado,
        status="CONCLUIDO",
    )
    db.add(fb)
    db.commit()
    db.refresh(fb)
    return fb

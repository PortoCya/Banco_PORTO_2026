"""
Endpoints de Pesquisas (Surveys), Links (NOMINAL/ABERTO), Submissões Públicas e Exportação CSV — NPS KeyCore v1.0.
Atende RF-003 a RF-013, RF-019 e Regras de Integridade 1 a 8 do PRD.
"""
import csv
import io
import secrets
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.errors import BusinessRuleError, ConflictError, NotFoundError
from app.core.security import (
    hash_ip,
    mascarar_pii,
    rate_limit,
    registrar_auditoria,
    require_roles,
)
from app.models.models import (
    JobIa,
    LinkPesquisa,
    LogExportacao,
    Pesquisa,
    Submissao,
    Usuario,
)
from app.schemas.schemas import (
    LinkPesquisaCreate,
    LinkPesquisaResponse,
    PesquisaCreate,
    PesquisaResponse,
    PesquisaUpdate,
    SubmissaoPublicaCreate,
    SubmissaoResponse,
)
from app.services.ia_service import classificar_nota_nps, processar_job_ia_background

router = APIRouter()


# ══════════════════════════════════════════════════════════════════
# 1. PESQUISAS (SURVEYS) — Administração e Versionamento (RF-003, RF-004)
# ══════════════════════════════════════════════════════════════════

@router.post(
    "/surveys",
    response_model=PesquisaResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Criar nova pesquisa NPS (Requer ADMIN)",
    tags=["Pesquisas (Surveys)"],
)
def criar_pesquisa(
    payload: PesquisaCreate,
    db: Session = Depends(get_db),
    admin: Usuario = Depends(require_roles("ADMIN")),
):
    pesquisa = Pesquisa(
        titulo=payload.titulo,
        texto_pergunta_nps=payload.texto_pergunta_nps,
        texto_pergunta_aberta=payload.texto_pergunta_aberta,
        status="RASCUNHO",
        numero_versao=1,
        criado_por=admin.id,
    )
    db.add(pesquisa)
    db.flush()

    registrar_auditoria(
        db=db,
        id_usuario_ator=admin.id,
        acao="CRIAR_PESQUISA",
        tipo_entidade="PESQUISA",
        id_entidade=pesquisa.id,
        estado_depois={"titulo": pesquisa.titulo, "status": pesquisa.status, "versao": 1},
    )
    db.commit()
    db.refresh(pesquisa)
    return pesquisa


@router.get(
    "/surveys",
    response_model=List[PesquisaResponse],
    summary="Listar pesquisas (Requer ADMIN ou ANALYST)",
    tags=["Pesquisas (Surveys)"],
)
def listar_pesquisas(
    status_filtro: Optional[str] = None,
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(require_roles("ADMIN", "ANALYST")),
):
    q = db.query(Pesquisa)
    if status_filtro:
        q = q.filter(Pesquisa.status == status_filtro.upper())
    return q.order_by(Pesquisa.criada_em.desc()).offset(skip).limit(min(limit, 100)).all()


@router.get(
    "/surveys/{pesquisa_id}",
    response_model=PesquisaResponse,
    summary="Detalhar pesquisa por ID (Requer ADMIN ou ANALYST)",
    tags=["Pesquisas (Surveys)"],
)
def buscar_pesquisa(
    pesquisa_id: str,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(require_roles("ADMIN", "ANALYST")),
):
    pesquisa = db.query(Pesquisa).filter(Pesquisa.id == pesquisa_id).first()
    if not pesquisa:
        raise NotFoundError(f"Pesquisa '{pesquisa_id}' não encontrada.")
    return pesquisa


@router.patch(
    "/surveys/{pesquisa_id}",
    response_model=PesquisaResponse,
    summary="Atualizar pesquisa (Versiona automaticamente se já houver respostas - RF-004)",
    tags=["Pesquisas (Surveys)"],
)
def atualizar_pesquisa(
    pesquisa_id: str,
    payload: PesquisaUpdate,
    db: Session = Depends(get_db),
    admin: Usuario = Depends(require_roles("ADMIN")),
):
    """
    RF-004: Preservação de histórico e versionamento após a primeira resposta.
    Se a pesquisa já possui submissões registradas, cria uma nova versão apontando
    `id_pesquisa_pai` para a pesquisa original sem quebrar o histórico coletado.
    """
    pesquisa = db.query(Pesquisa).filter(Pesquisa.id == pesquisa_id).first()
    if not pesquisa:
        raise NotFoundError(f"Pesquisa '{pesquisa_id}' não encontrada.")

    qtd_respostas = db.query(Submissao).filter(Submissao.id_pesquisa == pesquisa.id).count()
    dados_update = payload.model_dump(exclude_unset=True)

    if qtd_respostas > 0:
        nova_versao = Pesquisa(
            titulo=dados_update.get("titulo", pesquisa.titulo),
            texto_pergunta_nps=dados_update.get("texto_pergunta_nps", pesquisa.texto_pergunta_nps),
            texto_pergunta_aberta=dados_update.get("texto_pergunta_aberta", pesquisa.texto_pergunta_aberta),
            status=pesquisa.status,
            numero_versao=pesquisa.numero_versao + 1,
            id_pesquisa_pai=pesquisa.id,
            criado_por=admin.id,
        )
        pesquisa.status = "ARQUIVADA"
        db.add(nova_versao)
        db.flush()
        registrar_auditoria(
            db=db,
            id_usuario_ator=admin.id,
            acao="VERSIONAR_PESQUISA_COM_RESPOSTAS",
            tipo_entidade="PESQUISA",
            id_entidade=nova_versao.id,
            estado_antes={"id_pai": pesquisa.id, "versao_anterior": pesquisa.numero_versao},
            estado_depois={"id_nova": nova_versao.id, "numero_versao": nova_versao.numero_versao},
        )
        db.commit()
        db.refresh(nova_versao)
        return nova_versao

    antes = {"titulo": pesquisa.titulo, "texto_pergunta_nps": pesquisa.texto_pergunta_nps}
    for campo, valor in dados_update.items():
        setattr(pesquisa, campo, valor)

    registrar_auditoria(
        db=db,
        id_usuario_ator=admin.id,
        acao="EDITAR_PESQUISA",
        tipo_entidade="PESQUISA",
        id_entidade=pesquisa.id,
        estado_antes=antes,
        estado_depois=dados_update,
    )
    db.commit()
    db.refresh(pesquisa)
    return pesquisa


@router.post(
    "/surveys/{pesquisa_id}/status/{novo_status}",
    response_model=PesquisaResponse,
    summary="Alterar ciclo de vida da pesquisa: PUBLICADA | PAUSADA | ARQUIVADA (Requer ADMIN)",
    tags=["Pesquisas (Surveys)"],
)
def alterar_status_pesquisa(
    pesquisa_id: str,
    novo_status: str,
    db: Session = Depends(get_db),
    admin: Usuario = Depends(require_roles("ADMIN")),
):
    novo_status_up = novo_status.upper()
    if novo_status_up not in {"RASCUNHO", "PUBLICADA", "PAUSADA", "ARQUIVADA"}:
        raise BusinessRuleError("Status permitido: RASCUNHO, PUBLICADA, PAUSADA ou ARQUIVADA.")

    pesquisa = db.query(Pesquisa).filter(Pesquisa.id == pesquisa_id).first()
    if not pesquisa:
        raise NotFoundError(f"Pesquisa '{pesquisa_id}' não encontrada.")

    status_anterior = pesquisa.status
    pesquisa.status = novo_status_up

    registrar_auditoria(
        db=db,
        id_usuario_ator=admin.id,
        acao=f"ALTERAR_STATUS_PESQUISA_{novo_status_up}",
        tipo_entidade="PESQUISA",
        id_entidade=pesquisa.id,
        estado_antes={"status": status_anterior},
        estado_depois={"status": novo_status_up},
    )
    db.commit()
    db.refresh(pesquisa)
    return pesquisa


# ══════════════════════════════════════════════════════════════════
# 2. LINKS DE PESQUISA (NOMINAL uso único / ABERTO slug público - RF-005, RF-009)
# ══════════════════════════════════════════════════════════════════

@router.post(
    "/surveys/{pesquisa_id}/links",
    response_model=LinkPesquisaResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Gerar link/token para distribuição da pesquisa (Requer ADMIN)",
    tags=["Links e Convites"],
)
def criar_link_pesquisa(
    pesquisa_id: str,
    payload: LinkPesquisaCreate,
    db: Session = Depends(get_db),
    admin: Usuario = Depends(require_roles("ADMIN")),
):
    pesquisa = db.query(Pesquisa).filter(Pesquisa.id == pesquisa_id).first()
    if not pesquisa:
        raise NotFoundError(f"Pesquisa '{pesquisa_id}' não encontrada.")

    token = payload.token_customizado or secrets.token_urlsafe(16)
    if db.query(LinkPesquisa).filter(LinkPesquisa.token == token).first():
        raise ConflictError(f"Token/slug '{token}' já está em uso.")

    link = LinkPesquisa(
        id_pesquisa=pesquisa.id,
        tipo=payload.tipo,
        token=token,
    )
    db.add(link)
    db.flush()

    registrar_auditoria(
        db=db,
        id_usuario_ator=admin.id,
        acao="CRIAR_LINK_PESQUISA",
        tipo_entidade="LINK_PESQUISA",
        id_entidade=link.id,
        estado_depois={"id_pesquisa": pesquisa.id, "tipo": link.tipo, "token": link.token},
    )
    db.commit()
    db.refresh(link)
    return link


@router.get(
    "/surveys/{pesquisa_id}/links",
    response_model=List[LinkPesquisaResponse],
    summary="Listar links de uma pesquisa (Requer ADMIN ou ANALYST)",
    tags=["Links e Convites"],
)
def listar_links_pesquisa(
    pesquisa_id: str,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(require_roles("ADMIN", "ANALYST")),
):
    return db.query(LinkPesquisa).filter(LinkPesquisa.id_pesquisa == pesquisa_id).all()


# ══════════════════════════════════════════════════════════════════
# 3. FLUXO PÚBLICO DO RESPONDENTE (Mobile-First, Antiduplicidade, IA Assíncrona)
# ══════════════════════════════════════════════════════════════════

@router.get(
    "/public/surveys/{token}",
    summary="Carregar pesquisa pública por token/slug (Sem necessidade de conta)",
    tags=["Fluxo Público (Respondente)"],
    dependencies=[Depends(rate_limit("public_survey_view", max_requests=60, window_seconds=60))],
)
def carregar_pesquisa_publica(token: str, db: Session = Depends(get_db)):
    link = db.query(LinkPesquisa).filter(LinkPesquisa.token == token).first()
    if not link:
        raise NotFoundError("Link de pesquisa inválido ou expirado.")

    if link.tipo == "NOMINAL" and link.usado_em is not None:
        raise ConflictError("Este convite nominal já foi respondido.")

    pesquisa = db.query(Pesquisa).filter(Pesquisa.id == link.id_pesquisa).first()
    if not pesquisa or pesquisa.status != "PUBLICADA":
        raise BusinessRuleError("Esta pesquisa não está ativa para coleta de respostas no momento.")

    return {
        "id_pesquisa": pesquisa.id,
        "titulo": pesquisa.titulo,
        "texto_pergunta_nps": pesquisa.texto_pergunta_nps,
        "texto_pergunta_aberta": pesquisa.texto_pergunta_aberta,
        "tipo_link": link.tipo,
        "escala_nps": {"min": 0, "max": 10},
    }


@router.post(
    "/public/submissions",
    response_model=SubmissaoResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Enviar resposta NPS (Persistência transacional + Job IA assíncrono não-bloqueante)",
    tags=["Fluxo Público (Respondente)"],
    dependencies=[Depends(rate_limit("public_submission", max_requests=20, window_seconds=60))],
)
async def enviar_submissao_publica(
    payload: SubmissaoPublicaCreate,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """
    Regras de Integridade do PRD:
      1. Somente pesquisa PUBLICADA (ACTIVE) aceita resposta.
      2. A nota NPS deve ser um inteiro entre 0 e 10.
      3. Mesma chave_idempotencia ou token NOMINAL já utilizado bloqueia duplicidade (409).
      4. Submissão é persistida em transação única e é imutável.
      5. A IA roda em JOB_IA assíncrono e NUNCA bloqueia ou desfaz a submissão.
    """
    # 1. Verifica link e pesquisa ativa
    link = db.query(LinkPesquisa).filter(LinkPesquisa.token == payload.token_link).first()
    if not link:
        raise NotFoundError("Token de pesquisa não encontrado.")

    pesquisa = db.query(Pesquisa).filter(Pesquisa.id == link.id_pesquisa).first()
    if not pesquisa or pesquisa.status != "PUBLICADA":
        raise BusinessRuleError("Somente pesquisas com status PUBLICADA aceitam respostas.")

    # 2. Antiduplicidade: token NOMINAL de uso único (RF-012)
    if link.tipo == "NOMINAL" and link.usado_em is not None:
        raise ConflictError("Este link nominal já foi utilizado para uma submissão anterior.")

    # 3. Antiduplicidade: chave_idempotencia única (Regra 6 do PRD)
    duplicada = (
        db.query(Submissao)
        .filter(Submissao.chave_idempotencia == payload.chave_idempotencia)
        .first()
    )
    if duplicada:
        raise ConflictError("Submissão duplicada detectada pela chave de idempotência.")

    # 4. LGPD: avalia status de mascaramento de PII e pseudonimiza IP com SHA-256
    _, status_pii = mascarar_pii(payload.texto_comentario)
    client_ip = request.client.host if request.client else None
    ip_pseudonimizado = hash_ip(client_ip)

    # 5. Transação atômica: persiste Submissao + marca LinkPesquisa + cria JobIa
    submissao = Submissao(
        id_pesquisa=pesquisa.id,
        id_link_pesquisa=link.id,
        nota_nps=payload.nota_nps,
        texto_comentario=payload.texto_comentario,
        chave_idempotencia=payload.chave_idempotencia,
        fingerprint_dispositivo=payload.fingerprint_dispositivo,
        endereco_ip=ip_pseudonimizado,
        status="VALIDA",
        status_mascaramento_pii=status_pii,
    )
    db.add(submissao)
    db.flush()

    if link.tipo == "NOMINAL":
        link.usado_em = datetime.utcnow()

    job_ia = None
    if payload.texto_comentario and payload.texto_comentario.strip():
        job_ia = JobIa(
            id_submissao=submissao.id,
            status="NA_FILA",
            tentativas=0,
        )
        db.add(job_ia)

    db.commit()
    db.refresh(submissao)

    # 6. Dispara análise qualitativa por IA em background (falha na IA jamais afeta a submissão)
    if job_ia:
        background_tasks.add_task(processar_job_ia_background, job_ia.id)

    resposta = SubmissaoResponse.model_validate(submissao)
    resposta.classificacao_nps = classificar_nota_nps(submissao.nota_nps)
    return resposta


# ══════════════════════════════════════════════════════════════════
# 4. CONSULTA DE SUBMISSÕES E EXPORTAÇÃO CSV AUDITADA (RF-016, RF-019, LGPD)
# ══════════════════════════════════════════════════════════════════

@router.get(
    "/submissions",
    response_model=List[SubmissaoResponse],
    summary="Listar submissões com filtros por pesquisa e classificação (Requer ADMIN ou ANALYST)",
    tags=["Submissões e Exportação"],
)
def listar_submissoes(
    id_pesquisa: Optional[str] = None,
    classificacao: Optional[str] = None,
    busca: Optional[str] = None,
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(require_roles("ADMIN", "ANALYST")),
):
    q = db.query(Submissao).filter(Submissao.status == "VALIDA")
    if id_pesquisa:
        q = q.filter(Submissao.id_pesquisa == id_pesquisa)
    if classificacao:
        c = classificacao.upper()
        if c == "PROMOTOR":
            q = q.filter(Submissao.nota_nps >= 9)
        elif c == "NEUTRO":
            q = q.filter(Submissao.nota_nps.between(7, 8))
        elif c == "DETRATOR":
            q = q.filter(Submissao.nota_nps <= 6)
    if busca:
        q = q.filter(Submissao.texto_comentario.ilike(f"%{busca}%"))

    itens = q.order_by(Submissao.criada_em.desc()).offset(skip).limit(min(limit, 200)).all()
    resultado = []
    for sub in itens:
        r = SubmissaoResponse.model_validate(sub)
        r.classificacao_nps = classificar_nota_nps(sub.nota_nps)
        # Mascaramento preventivo na visualização se houver PII no comentário
        if sub.texto_comentario:
            texto_limpo, _ = mascarar_pii(sub.texto_comentario)
            r.texto_comentario = texto_limpo
        resultado.append(r)
    return resultado


@router.get(
    "/submissions/export/csv",
    summary="Exportar submissões de uma pesquisa em CSV com registro obrigatório em LOG_EXPORTACAO",
    tags=["Submissões e Exportação"],
)
def exportar_submissoes_csv(
    id_pesquisa: str,
    anonimizado: bool = True,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(require_roles("ADMIN", "ANALYST")),
):
    pesquisa = db.query(Pesquisa).filter(Pesquisa.id == id_pesquisa).first()
    if not pesquisa:
        raise NotFoundError(f"Pesquisa '{id_pesquisa}' não encontrada.")

    # LGPD: Analistas só podem exportar dados anonimizados; apenas ADMIN pode solicitar não-anonimizado
    if not anonimizado and usuario.papel != "ADMIN":
        anonimizado = True

    submissoes = (
        db.query(Submissao)
        .filter(Submissao.id_pesquisa == id_pesquisa, Submissao.status == "VALIDA")
        .order_by(Submissao.criada_em.asc())
        .all()
    )

    campos = ["id", "id_pesquisa", "nota_nps", "classificacao_nps", "texto_comentario", "criada_em"]
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(campos)

    for s in submissoes:
        comentario = s.texto_comentario or ""
        if anonimizado and comentario:
            comentario, _ = mascarar_pii(comentario)
        writer.writerow([
            s.id,
            s.id_pesquisa,
            s.nota_nps,
            classificar_nota_nps(s.nota_nps),
            comentario,
            s.criada_em.isoformat(),
        ])

    # Registra obrigatoriamente em LOG_EXPORTACAO e LOG_AUDITORIA (Pág. 7 e 9 do PRD)
    log_exp = LogExportacao(
        id_analista=usuario.id,
        id_pesquisa=id_pesquisa,
        campos_exportados=",".join(campos),
        anonimizado=anonimizado,
    )
    db.add(log_exp)
    db.flush()

    registrar_auditoria(
        db=db,
        id_usuario_ator=usuario.id,
        acao="EXPORTAR_CSV_SUBMISSOES",
        tipo_entidade="LOG_EXPORTACAO",
        id_entidade=log_exp.id,
        estado_depois={
            "id_pesquisa": id_pesquisa,
            "qtd_registros": len(submissoes),
            "anonimizado": anonimizado,
        },
    )
    db.commit()

    output.seek(0)
    filename = f"nps_keycore_{id_pesquisa[:8]}.csv"
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )

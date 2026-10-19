"""
Schemas Pydantic v2 — NPS KeyCore v1.0.
Proteção contra Mass Assignment (extra='forbid'), validação estrita de limites e sanitização XSS.
"""
from datetime import datetime, date
from typing import Optional, List, Literal, Dict, Any
from pydantic import BaseModel, EmailStr, Field, ConfigDict, field_validator

from app.core.security import sanitizar_texto


# ─── Base segura contra Mass Assignment ───────────────────────────────────────
class StrictInputModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ORMOutputModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ─── 1. AUTENTICAÇÃO E USUARIO (ADMIN | ANALYST) ──────────────────────────────
class LoginRequest(StrictInputModel):
    email: EmailStr
    senha: str = Field(..., min_length=6, max_length=128)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in_minutes: int
    papel: str
    usuario_id: str


class UsuarioCreate(StrictInputModel):
    nome: str = Field(..., min_length=2, max_length=200)
    email: EmailStr
    senha: str = Field(..., min_length=8, max_length=128, description="Mínimo 8 caracteres")
    papel: Literal["ADMIN", "ANALYST"] = "ANALYST"

    @field_validator("nome")
    @classmethod
    def _clean_nome(cls, v: str) -> str:
        return sanitizar_texto(v)


class UsuarioResponse(ORMOutputModel):
    id: str
    nome: str
    email: str
    papel: str
    ativo: bool
    criado_em: datetime
    # NOTA DE SEGURANÇA: senha_hash JAMAIS é incluída no response schema


# ─── 2. PESQUISA (Survey — RASCUNHO | PUBLICADA | PAUSADA | ARQUIVADA) ────────
class PesquisaCreate(StrictInputModel):
    titulo: str = Field(..., min_length=3, max_length=300)
    texto_pergunta_nps: str = Field(
        default="Em uma escala de 0 a 10, o quanto você recomendaria a KeyCore?",
        min_length=5,
        max_length=1000,
    )
    texto_pergunta_aberta: Optional[str] = Field(
        default="Qual é o principal motivo para a sua nota?",
        max_length=1000,
    )

    @field_validator("titulo", "texto_pergunta_nps", "texto_pergunta_aberta")
    @classmethod
    def _clean_text(cls, v: Optional[str]) -> Optional[str]:
        return sanitizar_texto(v)


class PesquisaUpdate(StrictInputModel):
    titulo: Optional[str] = Field(None, min_length=3, max_length=300)
    texto_pergunta_nps: Optional[str] = Field(None, min_length=5, max_length=1000)
    texto_pergunta_aberta: Optional[str] = Field(None, max_length=1000)

    @field_validator("titulo", "texto_pergunta_nps", "texto_pergunta_aberta")
    @classmethod
    def _clean_text(cls, v: Optional[str]) -> Optional[str]:
        return sanitizar_texto(v)


class PesquisaResponse(ORMOutputModel):
    id: str
    titulo: str
    texto_pergunta_nps: str
    texto_pergunta_aberta: Optional[str]
    status: str
    numero_versao: int
    id_pesquisa_pai: Optional[str]
    criado_por: str
    criada_em: datetime
    atualizada_em: datetime


# ─── 3. LINK_PESQUISA (Convites / Links públicos: NOMINAL | ABERTO) ───────────
class LinkPesquisaCreate(StrictInputModel):
    tipo: Literal["NOMINAL", "ABERTO"] = "ABERTO"
    token_customizado: Optional[str] = Field(None, min_length=4, max_length=100, pattern=r"^[a-zA-Z0-9_-]+$")


class LinkPesquisaResponse(ORMOutputModel):
    id: str
    id_pesquisa: str
    tipo: str
    token: str
    usado_em: Optional[datetime]
    criado_em: datetime


# ─── 4. SUBMISSAO (Fluxo Público Mobile-First + Persistência Transacional) ────
class SubmissaoPublicaCreate(StrictInputModel):
    token_link: str = Field(..., min_length=4, max_length=128, description="Token do LINK_PESQUISA")
    nota_nps: int = Field(..., ge=0, le=10, description="Nota NPS inteira obrigatória entre 0 e 10")
    texto_comentario: Optional[str] = Field(None, max_length=4000, description="Comentário complementar opcional")
    chave_idempotencia: str = Field(..., min_length=8, max_length=128, description="Chave única para evitar duplicidade")
    fingerprint_dispositivo: Optional[str] = Field(None, max_length=255)

    @field_validator("texto_comentario")
    @classmethod
    def _clean_comentario(cls, v: Optional[str]) -> Optional[str]:
        return sanitizar_texto(v)


class SubmissaoResponse(ORMOutputModel):
    id: str
    id_pesquisa: str
    id_link_pesquisa: Optional[str]
    nota_nps: int
    classificacao_nps: Optional[str] = None
    texto_comentario: Optional[str]
    chave_idempotencia: str
    status: str
    status_mascaramento_pii: str
    criada_em: datetime


# ─── 5. SNAPSHOT_NPS E ANALYTICS DETERMINÍSTICO ──────────────────────────────
class SnapshotNpsResponse(ORMOutputModel):
    id: str
    id_pesquisa: str
    periodo_inicio: date
    periodo_fim: date
    valor_nps: int
    total_respostas: int
    qtd_promotores: int
    qtd_neutros: int
    qtd_detratores: int
    pct_promotores: float = 0.0
    pct_neutros: float = 0.0
    pct_detratores: float = 0.0
    calculado_em: datetime


# ─── 6. IA QUALITATIVA: PROMPT, VERSAO_MODELO, JOB_IA, ANALISE_FEEDBACK ──────
class PromptCreate(StrictInputModel):
    objetivo: str = Field(..., min_length=5, max_length=2000)
    contexto: str = Field(..., min_length=5, max_length=4000)
    saida_esperada: str = Field(..., min_length=5, max_length=2000)
    problemas_encontrados: Optional[str] = Field(None, max_length=2000)


class PromptResponse(ORMOutputModel):
    id: str
    objetivo: str
    contexto: str
    saida_esperada: str
    problemas_encontrados: Optional[str]
    criado_em: datetime


class VersaoModeloCreate(StrictInputModel):
    provedor: str = Field(default="Google Gemini", max_length=100)
    nome_modelo: str = Field(default="gemini-2.0-flash", max_length=100)
    rotulo_versao: str = Field(..., max_length=100)
    id_prompt: str
    ativa: bool = True


class VersaoModeloResponse(ORMOutputModel):
    id: str
    provedor: str
    nome_modelo: str
    rotulo_versao: str
    id_prompt: str
    ativa: bool
    promovida_em: Optional[datetime]


class JobIaResponse(ORMOutputModel):
    id: str
    id_submissao: str
    status: str
    tentativas: int
    ultimo_erro: Optional[str]
    proxima_tentativa_em: Optional[datetime]
    criado_em: datetime


class AnaliseFeedbackResponse(ORMOutputModel):
    id: str
    id_submissao: str
    id_versao_modelo: str
    sentimento: str
    tema: str
    confianca: float
    justificativa: Optional[str]
    sequencia_versao: int
    status: str
    criada_em: datetime
    atualizada_em: datetime


# ─── 7. GOLDEN SET, AUDITORIA, EXPORTAÇÃO, CIRCUIT BREAKER E TELEMETRIA ──────
class ComentarioGoldenSetCreate(StrictInputModel):
    texto_comentario: str = Field(..., min_length=3, max_length=2000)
    rotulo_sentimento_humano: Literal["POSITIVO", "NEUTRO", "NEGATIVO"]
    rotulo_tema_humano: str = Field(..., min_length=2, max_length=100)


class ComentarioGoldenSetResponse(ORMOutputModel):
    id: str
    texto_comentario: str
    rotulo_sentimento_humano: str
    rotulo_tema_humano: str
    criado_em: datetime


class LogAuditoriaResponse(ORMOutputModel):
    id: str
    id_usuario_ator: Optional[str]
    acao: str
    tipo_entidade: str
    id_entidade: str
    estado_antes: Optional[Dict[str, Any]]
    estado_depois: Optional[Dict[str, Any]]
    criado_em: datetime


class LogExportacaoResponse(ORMOutputModel):
    id: str
    id_analista: str
    id_pesquisa: str
    campos_exportados: str
    anonimizado: bool
    criado_em: datetime


class EventoCircuitBreakerResponse(ORMOutputModel):
    id: str
    motivo: str
    custo_acumulado: float
    limite_custo: float
    disparado_em: datetime
    resolvido_em: Optional[datetime]


class SnapshotTelemetriaResponse(ORMOutputModel):
    id: str
    inicio_janela: datetime
    fim_janela: datetime
    latencia_p50_ms: int
    latencia_p95_ms: int
    taxa_erro_5xx: float
    pct_descartado_ec12: float
    pct_descartado_ec13: float
    qtd_pii_mascaramento_falhou: int
    status_circuit_breaker: str

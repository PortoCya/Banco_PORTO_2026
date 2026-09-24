"""
Schemas Pydantic — Request / Response para todos os endpoints.
"""
from __future__ import annotations
from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, EmailStr, Field, field_validator
import uuid


# ─── Helpers ──────────────────────────────────────────────────────────────────

class OkResponse(BaseModel):
    ok: bool = True
    message: str = "Operação realizada com sucesso."


class ErrorDetail(BaseModel):
    code: str
    message: str
    details: Optional[Any] = None


class ErrorResponse(BaseModel):
    error: ErrorDetail


# ══════════════════════════════════════════════════════════════════
# USUARIO
# ══════════════════════════════════════════════════════════════════

class UsuarioCreate(BaseModel):
    nome: str = Field(..., min_length=2, max_length=200)
    email: EmailStr
    role: str = Field("ANALISTA", pattern="^(ADMIN|ANALISTA|PT)$")

class UsuarioResponse(BaseModel):
    uuid: str
    nome: str
    email: str
    role: str
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}


# ══════════════════════════════════════════════════════════════════
# VIDEO_MODELO
# ══════════════════════════════════════════════════════════════════

class VideoModeloCreate(BaseModel):
    provider: str = Field(..., min_length=1, max_length=100)
    nome_modelo: str = Field(..., min_length=1, max_length=100)
    status_ativo: bool = True
    is_current: bool = False

class VideoModeloResponse(BaseModel):
    uuid: str
    provider: str
    nome_modelo: str
    status_ativo: bool
    is_current: bool
    created_at: datetime

    model_config = {"from_attributes": True}


# ══════════════════════════════════════════════════════════════════
# CONVERSA
# ══════════════════════════════════════════════════════════════════

class ConversaCreate(BaseModel):
    fk_usuario: str
    titulo: Optional[str] = None
    tipo_consultor: Optional[str] = None
    configuracoes: Optional[Dict[str, Any]] = None

class MensagemInput(BaseModel):
    """Mensagem enviada pelo usuário dentro de uma conversa."""
    conversa_uuid: str
    mensagem: str = Field(..., min_length=1, max_length=10000)
    tipo_consultor: Optional[str] = None

    @field_validator("mensagem")
    @classmethod
    def mensagem_nao_vazia(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Mensagem não pode ser vazia ou apenas espaços.")
        return v.strip()

class ConversaResponse(BaseModel):
    uuid: str
    fk_usuario: str
    titulo: Optional[str]
    tipo_consultor: Optional[str]
    status: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ══════════════════════════════════════════════════════════════════
# GERENCIACAO
# ══════════════════════════════════════════════════════════════════

class GerenciacaoCreate(BaseModel):
    fk_pessoa: str
    tipo_pot: Optional[str] = None
    fingerprint_dispositivo: Optional[str] = None
    credencial_ip: Optional[str] = None

class GerenciacaoResponse(BaseModel):
    uuid: str
    fk_pessoa: str
    tipo_pot: Optional[str]
    status: str
    chave_referencia: str
    created_at: datetime

    model_config = {"from_attributes": True}


# ══════════════════════════════════════════════════════════════════
# SOA_IA
# ══════════════════════════════════════════════════════════════════

class SoaIaResponse(BaseModel):
    uuid: str
    fk_gerenciacao: str
    status: str
    allow_queue: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ══════════════════════════════════════════════════════════════════
# ANALISE_FEEDBACK
# ══════════════════════════════════════════════════════════════════

class AnaliseFeedbackCreate(BaseModel):
    fk_gerenciacao: str
    fk_video_modelo: Optional[str] = None
    texto_para_analisar: str = Field(..., min_length=5)

class AnaliseFeedbackResponse(BaseModel):
    uuid: str
    fk_gerenciacao: str
    sentimento: Optional[str]
    tema: Optional[str]
    confianca: Optional[float]
    justificativa: Optional[str]
    sugestoes_acao: Optional[Any]
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}


# ══════════════════════════════════════════════════════════════════
# LOA_PUNICAO
# ══════════════════════════════════════════════════════════════════

class LoaPunicaoCreate(BaseModel):
    fk_conversa_set: str
    tipo: str = Field(..., max_length=50)
    boolean_status: bool = False
    valor: Optional[float] = None
    metodo_ativo: Optional[str] = None

class LoaPunicaoResponse(BaseModel):
    uuid: str
    fk_conversa_set: str
    tipo: str
    boolean_status: bool
    valor: Optional[float]
    created_at: datetime

    model_config = {"from_attributes": True}


# ══════════════════════════════════════════════════════════════════
# PROMPT
# ══════════════════════════════════════════════════════════════════

class PromptCreate(BaseModel):
    fk_video_modelo: str
    conteudo: str = Field(..., min_length=10)
    contexto: Optional[str] = None
    prompt_engenharia_template: Optional[str] = None
    status_ativo: bool = True

class PromptResponse(BaseModel):
    uuid: str
    fk_video_modelo: str
    conteudo: str
    status_ativo: bool

    model_config = {"from_attributes": True}


# ══════════════════════════════════════════════════════════════════
# DIMENSOES_KPIS
# ══════════════════════════════════════════════════════════════════

class DimensoesKpisResponse(BaseModel):
    uuid: str
    fk_gerencia: str
    data: Optional[datetime]
    periodo_fim: Optional[datetime]
    valor_pot: Optional[float]
    get_pontuacoes: Optional[float]
    get_pontuacoes2: Optional[float]
    created_at: datetime

    model_config = {"from_attributes": True}


# ══════════════════════════════════════════════════════════════════
# MATRIZ_PUNICAO_SET
# ══════════════════════════════════════════════════════════════════

class MatrizPunicaoSetResponse(BaseModel):
    uuid: str
    fk_loa_punicao: str
    boolean_relevante: bool
    nota_pot: Optional[float]
    nota_relevancia: Optional[float]
    get_pontuacao: Optional[float]
    get_pontuacao2: Optional[float]
    created_at: datetime

    model_config = {"from_attributes": True}


# ══════════════════════════════════════════════════════════════════
# RESPOSTAS DA IA (endpoint /consultar)
# ══════════════════════════════════════════════════════════════════

class ConsultaIAResponse(BaseModel):
    gerenciacao_uuid: str
    soa_ia_uuid: str
    resposta: str
    tokens_entrada: int
    tokens_saida: int
    modelo_utilizado: str
    finish_reason: str
    created_at: datetime

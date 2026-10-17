"""
Schemas Pydantic — Request / Response para todos os endpoints.
"""
from __future__ import annotations
import json
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

# Teto de 128 evita que uma senha gigante deixe o Argon2 lento de propósito
SENHA_MIN, SENHA_MAX = 12, 128


class UsuarioCreate(BaseModel):
    nome: str = Field(..., min_length=2, max_length=200)
    email: EmailStr = Field(..., max_length=200)
    senha: str = Field(..., min_length=SENHA_MIN, max_length=SENHA_MAX)
    papel: str = Field("ANALYST", pattern="^(ADMIN|ANALYST)$")

    @field_validator("email")
    @classmethod
    def email_minusculo(cls, v: str) -> str:
        return v.lower()

class UsuarioUpdate(BaseModel):
    nome: Optional[str] = Field(None, min_length=2, max_length=200)
    papel: Optional[str] = Field(None, pattern="^(ADMIN|ANALYST)$")
    ativo: Optional[bool] = None

class UsuarioResponse(BaseModel):
    uuid: str
    nome: str
    email: str
    papel: str
    ativo: bool
    criado_em: datetime

    model_config = {"from_attributes": True}


# ══════════════════════════════════════════════════════════════════
# AUTENTICAÇÃO
# ══════════════════════════════════════════════════════════════════

class LoginRequest(BaseModel):
    email: EmailStr = Field(..., max_length=200)
    senha: str = Field(..., min_length=1, max_length=SENHA_MAX)

    @field_validator("email")
    @classmethod
    def email_minusculo(cls, v: str) -> str:
        return v.lower()

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int                 # segundos


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
    # fk_usuario não vem do cliente: é sempre o usuário logado
    titulo: Optional[str] = Field(None, max_length=200)
    tipo_consultor: Optional[str] = Field(None, max_length=100)
    configuracoes: Optional[Dict[str, Any]] = None

    @field_validator("configuracoes")
    @classmethod
    def configuracoes_pequenas(cls, v):
        if v is not None and len(json.dumps(v)) > 10_000:
            raise ValueError("configuracoes muito grande (máx. 10.000 caracteres em JSON).")
        return v

class MensagemInput(BaseModel):
    """Mensagem enviada pelo usuário dentro de uma conversa."""
    conversa_uuid: str = Field(..., max_length=36)
    mensagem: str = Field(..., min_length=1, max_length=10000)
    tipo_consultor: Optional[str] = Field(None, max_length=100)

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
    # fk_pessoa e credencial_ip não vêm do cliente: saem do login e da conexão
    tipo_pot: Optional[str] = Field(None, max_length=50)
    fingerprint_dispositivo: Optional[str] = Field(None, max_length=255)

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
    fk_gerenciacao: str = Field(..., max_length=36)
    fk_video_modelo: Optional[str] = Field(None, max_length=36)
    texto_para_analisar: str = Field(..., min_length=5, max_length=2000)

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
    fk_conversa_set: str = Field(..., max_length=36)
    tipo: str = Field(..., max_length=50)
    boolean_status: bool = False
    valor: Optional[float] = None
    metodo_ativo: Optional[str] = Field(None, max_length=100)

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
    fk_video_modelo: str = Field(..., max_length=36)
    conteudo: str = Field(..., min_length=10, max_length=20000)
    contexto: Optional[str] = Field(None, max_length=5000)
    prompt_engenharia_template: Optional[str] = Field(None, max_length=20000)
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

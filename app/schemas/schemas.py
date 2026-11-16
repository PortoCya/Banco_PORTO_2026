"""
Schemas Pydantic v2 — tudo o que entra e sai da API.

Entrada: campos desconhecidos são rejeitados (extra="forbid"), todo texto tem
tamanho máximo e valores fechados são Literal. Nome do campo = nome da coluna.
"""
import uuid
from datetime import date, datetime
from typing import Annotated, Any, Literal, Optional

from pydantic import (
    AfterValidator, BaseModel, ConfigDict, EmailStr, Field, StringConstraints, model_validator,
)

Papel = Literal["ADMIN", "ANALYST"]
StatusPesquisa = Literal["RASCUNHO", "PUBLICADA", "PAUSADA", "ARQUIVADA"]
TipoLink = Literal["NOMINAL", "ABERTO"]
Sentimento = Literal["POSITIVO", "NEUTRO", "NEGATIVO"]
Tema = Literal["atendimento", "preco", "produto", "prazo", "usabilidade", "outro"]
StatusAnalise = Literal["PENDENTE", "CONCLUIDA", "FALHA_SCHEMA", "DESCARTADA_MANUAL", "BAIXA_CONFIANCA"]
StatusJobIa = Literal["NA_FILA", "PROCESSANDO", "CONCLUIDO", "FALHOU", "TENTANDO_NOVAMENTE"]

# Teto de 128 evita que uma senha gigante deixe o Argon2 lento de propósito
SENHA_MIN, SENHA_MAX = 12, 128
COMENTARIO_MAX = 2000


def _sem_caracteres_de_controle(v: str) -> str:
    # \x00 derruba o INSERT no PostgreSQL; os demais só servem para poluir log/CSV
    if any(ord(c) < 32 and c not in "\n\r\t" for c in v):
        raise ValueError("Texto contém caracteres de controle inválidos.")
    return v


def Texto(minimo: int, maximo: int):
    return Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=minimo, max_length=maximo),
        AfterValidator(_sem_caracteres_de_controle),
    ]


def _minusculo(v: str) -> str:
    return v.lower()


Email = Annotated[EmailStr, Field(max_length=255), AfterValidator(_minusculo)]


class Entrada(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Saida(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ─── Autenticação e usuários ─────────────────────────────────────────────────

class LoginRequest(Entrada):
    email: Email
    senha: str = Field(..., min_length=1, max_length=SENHA_MAX)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int                 # segundos


class UsuarioCreate(Entrada):
    nome: Texto(2, 200)
    email: Email
    senha: str = Field(..., min_length=SENHA_MIN, max_length=SENHA_MAX)
    papel: Papel = "ANALYST"


class UsuarioUpdate(Entrada):
    nome: Optional[Texto(2, 200)] = None
    papel: Optional[Papel] = None
    ativo: Optional[bool] = None

    @model_validator(mode="after")
    def _sem_nulos(self):
        if any(getattr(self, campo) is None for campo in self.model_fields_set):
            raise ValueError("Campos enviados não podem ser nulos.")
        return self


class UsuarioResponse(Saida):
    id: uuid.UUID
    nome: str
    email: str
    papel: str
    ativo: bool
    criado_em: datetime
    # senha_hash nunca entra em schema de resposta


# ─── Pesquisas e links ───────────────────────────────────────────────────────

class PesquisaCreate(Entrada):
    titulo: Texto(3, 300)
    texto_pergunta_nps: Texto(5, 1000) = "Em uma escala de 0 a 10, o quanto você recomendaria a KeyCore?"
    texto_pergunta_aberta: Optional[Texto(0, 1000)] = "Qual é o principal motivo para a sua nota?"


class PesquisaUpdate(Entrada):
    titulo: Optional[Texto(3, 300)] = None
    texto_pergunta_nps: Optional[Texto(5, 1000)] = None
    texto_pergunta_aberta: Optional[Texto(0, 1000)] = None

    @model_validator(mode="after")
    def _valida(self):
        if not self.model_fields_set:
            raise ValueError("Informe ao menos um campo para alterar.")
        for campo in ("titulo", "texto_pergunta_nps"):
            if campo in self.model_fields_set and getattr(self, campo) is None:
                raise ValueError(f"{campo} não pode ser nulo.")
        return self


class PesquisaResponse(Saida):
    id: uuid.UUID
    titulo: str
    texto_pergunta_nps: str
    texto_pergunta_aberta: Optional[str]
    status: str
    numero_versao: int
    id_pesquisa_pai: Optional[uuid.UUID]
    criado_por: uuid.UUID
    criada_em: datetime
    atualizada_em: datetime


class LinkPesquisaCreate(Entrada):
    tipo: TipoLink = "ABERTO"
    # Slug legível, só para link ABERTO. Link NOMINAL sempre recebe token aleatório.
    token_customizado: Optional[str] = Field(None, min_length=8, max_length=100, pattern=r"^[A-Za-z0-9_-]+$")

    @model_validator(mode="after")
    def _slug_so_em_link_aberto(self):
        if self.tipo == "NOMINAL" and self.token_customizado:
            raise ValueError("Link NOMINAL não aceita token_customizado.")
        return self


class LinkPesquisaResponse(Saida):
    id: uuid.UUID
    id_pesquisa: uuid.UUID
    tipo: str
    token: str
    usado_em: Optional[datetime]
    criado_em: datetime


# ─── Fluxo público (respondente) ─────────────────────────────────────────────

class PesquisaPublicaResponse(BaseModel):
    titulo: str
    texto_pergunta_nps: str
    texto_pergunta_aberta: Optional[str]
    tipo_link: str
    nota_minima: int = 0
    nota_maxima: int = 10
    comentario_max_caracteres: int = COMENTARIO_MAX


class RespostaPublicaCreate(Entrada):
    # strict: "10", 9.0 ou true não viram nota
    nota_nps: int = Field(..., ge=0, le=10, strict=True)
    texto_comentario: Optional[Texto(0, COMENTARIO_MAX)] = None
    chave_idempotencia: str = Field(..., min_length=16, max_length=128, pattern=r"^[A-Za-z0-9_-]+$")
    fingerprint_dispositivo: Optional[str] = Field(None, max_length=255, pattern=r"^[\x21-\x7e]*$")


class RespostaPublicaResponse(BaseModel):
    id: uuid.UUID
    nota_nps: int
    criada_em: datetime


class RespostaResponse(BaseModel):
    """
    Uma resposta VALIDA para os painéis. Comentário sempre anonimizado (PII
    mascarada). Os campos de análise são a análise SUGERIDA mais recente pela
    IA (nulos se ainda não houver): nunca alteram nota, faixa ou NPS.
    """
    id: uuid.UUID
    nota_nps: int
    faixa_nps: Literal["PROMOTOR", "NEUTRO", "DETRATOR"]
    texto_comentario: Optional[str]
    criada_em: datetime
    status_analise: Optional[str] = None
    sentimento: Optional[str] = None
    tema: Optional[str] = None
    confianca: Optional[float] = None
    justificativa: Optional[str] = None


# ─── NPS ─────────────────────────────────────────────────────────────────────

class NpsResponse(BaseModel):
    id_pesquisa: uuid.UUID
    valor_nps: Optional[int]        # null quando não há respostas (nunca 0)
    status: Literal["ok", "sem_dados_suficientes"]
    total_respostas: int
    qtd_promotores: int
    qtd_neutros: int
    qtd_detratores: int
    periodo_inicio: Optional[date]
    periodo_fim: Optional[date]


class SnapshotNpsResponse(Saida):
    id: uuid.UUID
    id_pesquisa: uuid.UUID
    periodo_inicio: date
    periodo_fim: date
    valor_nps: int
    total_respostas: int
    qtd_promotores: int
    qtd_neutros: int
    qtd_detratores: int
    calculado_em: datetime


# ─── Camada de IA ────────────────────────────────────────────────────────────

class AnaliseFeedbackResponse(BaseModel):
    """Sempre uma ANÁLISE SUGERIDA pela IA — nunca altera nota, faixa ou NPS."""
    id: uuid.UUID
    id_submissao: uuid.UUID
    id_versao_modelo: uuid.UUID
    rotulo: Literal["análise sugerida"] = "análise sugerida"
    sentimento: Optional[str]
    tema: Optional[str]
    confianca: Optional[float]
    justificativa: Optional[str]
    sequencia_versao: int
    status: str
    nota_nps: int
    texto_comentario: Optional[str]     # com PII mascarada
    criada_em: datetime
    atualizada_em: datetime


class AnaliseFeedbackUpdate(Entrada):
    """ANALYST descarta a sugestão (status) ou corrige sentimento/tema."""
    status: Optional[Literal["DESCARTADA_MANUAL"]] = None
    sentimento: Optional[Sentimento] = None
    tema: Optional[Tema] = None

    @model_validator(mode="after")
    def _valida(self):
        corrigindo = self.sentimento is not None or self.tema is not None
        if self.status is None and not corrigindo:
            raise ValueError("Informe status=DESCARTADA_MANUAL ou sentimento/tema corrigidos.")
        if self.status is not None and corrigindo:
            raise ValueError("Descartar e corrigir são operações exclusivas.")
        return self


class ResumoAnalisesResponse(BaseModel):
    id_pesquisa: uuid.UUID
    rotulo: Literal["análise sugerida"] = "análise sugerida"
    total_analises_concluidas: int
    por_sentimento: dict[str, int]
    por_tema: dict[str, int]


class PromptCreate(Entrada):
    objetivo: Texto(5, 2000)
    contexto: Texto(5, 4000)
    saida_esperada: Texto(5, 2000)
    problemas_encontrados: Optional[Texto(0, 2000)] = None


class PromptResponse(Saida):
    id: uuid.UUID
    objetivo: str
    contexto: str
    saida_esperada: str
    problemas_encontrados: Optional[str]
    criado_em: datetime


class VersaoModeloCreate(Entrada):
    provedor: Texto(2, 100)
    nome_modelo: Annotated[str, StringConstraints(min_length=2, max_length=100, pattern=r"^[A-Za-z0-9._:/-]+$")]
    rotulo_versao: Annotated[str, StringConstraints(min_length=2, max_length=100, pattern=r"^[A-Za-z0-9._:-]+$")]
    id_prompt: uuid.UUID
    # Não existe "ativo" aqui: ativação só pelo gate do golden set.


class VersaoModeloResponse(Saida):
    id: uuid.UUID
    provedor: str
    nome_modelo: str
    rotulo_versao: str
    id_prompt: uuid.UUID
    ativo: bool
    promovida_em: Optional[datetime]
    criada_em: datetime


class JobIaResponse(Saida):
    id: uuid.UUID
    id_submissao: uuid.UUID
    status: str
    tentativas: int
    ultimo_erro: Optional[str]
    proxima_tentativa_em: Optional[datetime]
    criado_em: datetime


class ComentarioGoldenSetCreate(Entrada):
    texto_comentario: Texto(3, COMENTARIO_MAX)
    rotulo_sentimento_humano: Sentimento
    rotulo_tema_humano: Tema


class ComentarioGoldenSetResponse(Saida):
    id: uuid.UUID
    texto_comentario: str
    rotulo_sentimento_humano: str
    rotulo_tema_humano: str
    criado_em: datetime


class AvaliacaoGoldenSetCreate(Entrada):
    id_versao_modelo: uuid.UUID


class AvaliacaoGoldenSetResponse(Saida):
    id: uuid.UUID
    id_versao_modelo: uuid.UUID
    acuracia_sentimento: float
    acuracia_tema: float
    taxa_falso_positivo: float
    status: str
    executada_em: datetime


class AvaliacaoSolicitadaResponse(BaseModel):
    id_versao_modelo: uuid.UUID
    status: Literal["NA_FILA"] = "NA_FILA"


class LimiteCustoUpdate(Entrada):
    limite_custo: float = Field(..., ge=0, le=1_000_000, allow_inf_nan=False)


class LimiteCustoResponse(BaseModel):
    limite_custo: float
    custo_acumulado: float
    circuit_breaker_aberto: bool


class EventoCircuitBreakerResponse(Saida):
    id: uuid.UUID
    motivo: str
    custo_acumulado: float
    limite_custo: float
    disparado_em: datetime
    resolvido_em: Optional[datetime]


class SnapshotTelemetriaResponse(Saida):
    id: uuid.UUID
    inicio_janela: datetime
    fim_janela: datetime
    latencia_p50_ms: int
    latencia_p95_ms: int
    taxa_erro_5xx: float
    pct_descartado_ec12: float
    pct_descartado_ec13: float
    qtd_pii_mascaramento_falhou: int
    status_circuit_breaker: str


# ─── Auditoria ───────────────────────────────────────────────────────────────

class LogAuditoriaResponse(Saida):
    id: uuid.UUID
    id_usuario_ator: Optional[uuid.UUID]
    acao: str
    tipo_entidade: str
    id_entidade: uuid.UUID
    estado_antes: Optional[dict[str, Any]]
    estado_depois: Optional[dict[str, Any]]
    criado_em: datetime


class LogExportacaoResponse(Saida):
    id: uuid.UUID
    id_analista: uuid.UUID
    id_pesquisa: uuid.UUID
    campos_exportados: str
    anonimizado: bool
    criado_em: datetime

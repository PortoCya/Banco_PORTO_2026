"""
Modelos ORM (SQLAlchemy 2.0) — as 16 tabelas do AGENTS.md.

Convenções:
- Toda PK é uuid. Nome do campo na API = nome da coluna.
- Datas sempre em UTC, com fuso (timestamptz no PostgreSQL).
- Enums são VARCHAR + CHECK (não tipo nativo): acrescentar um valor vira uma
  migration simples, sem ALTER TYPE.
- Toda coluna usada em filtro, junção ou ordenação tem índice.
- Qualquer mudança aqui exige uma migration do Alembic (ver alembic/README.md).
"""
import uuid
from datetime import date, datetime, timezone

from sqlalchemy import (
    JSON, Boolean, CheckConstraint, Date, DateTime, Enum, Float, ForeignKey,
    Index, Integer, Numeric, String, Text, UniqueConstraint, Uuid, text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import TypeDecorator

from app.core.database import Base

# ─── Valores fechados (fonte única; schemas e serviços importam daqui) ───────
PAPEIS = ("ADMIN", "ANALYST")
STATUS_PESQUISA = ("RASCUNHO", "PUBLICADA", "PAUSADA", "ARQUIVADA")
TIPOS_LINK = ("NOMINAL", "ABERTO")
STATUS_SUBMISSAO = ("VALIDA", "BLOQUEADA_DUPLICADA")
STATUS_PII = ("NAO_APLICAVEL", "MASCARADO", "FALHA_MASCARAMENTO_PII")
STATUS_JOB_IA = ("NA_FILA", "PROCESSANDO", "CONCLUIDO", "FALHOU", "TENTANDO_NOVAMENTE")
STATUS_ANALISE = ("PENDENTE", "CONCLUIDA", "FALHA_SCHEMA", "DESCARTADA_MANUAL", "BAIXA_CONFIANCA")
SENTIMENTOS = ("POSITIVO", "NEUTRO", "NEGATIVO")
TEMAS = ("atendimento", "preco", "produto", "prazo", "usabilidade", "outro")
STATUS_AVALIACAO = ("APROVADO", "REPROVADO")


def agora_utc() -> datetime:
    return datetime.now(timezone.utc)


class DataHoraUTC(TypeDecorator):
    """timestamptz que sempre devolve datetime com fuso UTC (inclusive no SQLite)."""
    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is not None and value.tzinfo is None:
            raise ValueError("Use datetime com fuso (agora_utc()).")
        return value.astimezone(timezone.utc) if value is not None else None

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _enum(valores: tuple[str, ...], nome: str) -> Enum:
    return Enum(*valores, name=nome, native_enum=False, create_constraint=True, length=40)


def _pk() -> Mapped[uuid.UUID]:
    return mapped_column(Uuid, primary_key=True, default=uuid.uuid4)


# ══════════════════════════════════════════════════════════════════
# NÚCLEO
# ══════════════════════════════════════════════════════════════════

class Usuario(Base):
    __tablename__ = "usuario"

    id: Mapped[uuid.UUID] = _pk()
    nome: Mapped[str] = mapped_column(String(200))
    email: Mapped[str] = mapped_column(String(255), unique=True)   # sempre minúsculo
    senha_hash: Mapped[str] = mapped_column(String(255))
    papel: Mapped[str] = mapped_column(_enum(PAPEIS, "ck_usuario_papel"), default="ANALYST")
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)
    criado_em: Mapped[datetime] = mapped_column(DataHoraUTC, default=agora_utc)


class Pesquisa(Base):
    __tablename__ = "pesquisa"
    __table_args__ = (
        Index("ix_pesquisa_status_criada_em", "status", "criada_em"),
        Index("ix_pesquisa_id_pesquisa_pai", "id_pesquisa_pai"),
        Index("ix_pesquisa_criado_por", "criado_por"),
    )

    id: Mapped[uuid.UUID] = _pk()
    titulo: Mapped[str] = mapped_column(String(300))
    texto_pergunta_nps: Mapped[str] = mapped_column(Text)
    texto_pergunta_aberta: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(_enum(STATUS_PESQUISA, "ck_pesquisa_status"), default="RASCUNHO")
    numero_versao: Mapped[int] = mapped_column(Integer, default=1)
    # Editar pesquisa com respostas cria uma nova linha apontando para a anterior
    id_pesquisa_pai: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("pesquisa.id", ondelete="RESTRICT"))
    criado_por: Mapped[uuid.UUID] = mapped_column(ForeignKey("usuario.id", ondelete="RESTRICT"))
    criada_em: Mapped[datetime] = mapped_column(DataHoraUTC, default=agora_utc)
    atualizada_em: Mapped[datetime] = mapped_column(DataHoraUTC, default=agora_utc, onupdate=agora_utc)


class LinkPesquisa(Base):
    __tablename__ = "link_pesquisa"
    __table_args__ = (
        Index("ix_link_pesquisa_id_pesquisa_criado_em", "id_pesquisa", "criado_em"),
    )

    id: Mapped[uuid.UUID] = _pk()
    id_pesquisa: Mapped[uuid.UUID] = mapped_column(ForeignKey("pesquisa.id", ondelete="RESTRICT"))
    tipo: Mapped[str] = mapped_column(_enum(TIPOS_LINK, "ck_link_pesquisa_tipo"))
    token: Mapped[str] = mapped_column(String(128), unique=True)
    usado_em: Mapped[datetime | None] = mapped_column(DataHoraUTC)   # nulo até a 1ª resposta
    criado_em: Mapped[datetime] = mapped_column(DataHoraUTC, default=agora_utc)


class Submissao(Base):
    """Resposta do cliente. Imutável: guarda só a nota; a faixa é calculada na hora."""
    __tablename__ = "submissao"
    __table_args__ = (
        CheckConstraint("nota_nps >= 0 AND nota_nps <= 10", name="ck_submissao_nota_nps_0_10"),
        # Cálculo do NPS: WHERE id_pesquisa = ? AND status = 'VALIDA' GROUP BY faixa
        Index("ix_submissao_pesquisa_status_nota", "id_pesquisa", "status", "nota_nps"),
        # Listagem/exportação/período: WHERE id_pesquisa = ? ORDER BY criada_em
        Index("ix_submissao_pesquisa_criada_em", "id_pesquisa", "criada_em"),
        Index("ix_submissao_id_link_pesquisa", "id_link_pesquisa"),
        # Idempotência: a chave é única entre as respostas VALIDAS. As tentativas
        # bloqueadas ficam registradas com a mesma chave, para auditoria.
        Index(
            "uq_submissao_chave_idempotencia_valida", "chave_idempotencia", unique=True,
            postgresql_where=text("status = 'VALIDA'"), sqlite_where=text("status = 'VALIDA'"),
        ),
    )

    id: Mapped[uuid.UUID] = _pk()
    id_pesquisa: Mapped[uuid.UUID] = mapped_column(ForeignKey("pesquisa.id", ondelete="RESTRICT"))
    id_link_pesquisa: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("link_pesquisa.id", ondelete="RESTRICT"))
    nota_nps: Mapped[int] = mapped_column(Integer)
    texto_comentario: Mapped[str | None] = mapped_column(Text)      # original, íntegro
    chave_idempotencia: Mapped[str] = mapped_column(String(128))
    fingerprint_dispositivo: Mapped[str | None] = mapped_column(String(255))
    endereco_ip: Mapped[str | None] = mapped_column(String(128))    # HMAC do IP, nunca o IP
    status: Mapped[str] = mapped_column(_enum(STATUS_SUBMISSAO, "ck_submissao_status"), default="VALIDA")
    status_mascaramento_pii: Mapped[str] = mapped_column(
        _enum(STATUS_PII, "ck_submissao_status_pii"), default="NAO_APLICAVEL"
    )
    criada_em: Mapped[datetime] = mapped_column(DataHoraUTC, default=agora_utc)


class SnapshotNps(Base):
    """
    NPS acumulado da pesquisa ao final de cada dia (UTC). A linha do dia é
    atualizada na mesma transação de cada resposta; a série é o histórico.
    """
    __tablename__ = "snapshot_nps"
    __table_args__ = (
        CheckConstraint("valor_nps >= -100 AND valor_nps <= 100", name="ck_snapshot_nps_valor"),
        UniqueConstraint("id_pesquisa", "periodo_inicio", "periodo_fim", name="uq_snapshot_nps_pesquisa_periodo"),
    )

    id: Mapped[uuid.UUID] = _pk()
    id_pesquisa: Mapped[uuid.UUID] = mapped_column(ForeignKey("pesquisa.id", ondelete="RESTRICT"))
    periodo_inicio: Mapped[date] = mapped_column(Date)
    periodo_fim: Mapped[date] = mapped_column(Date)
    valor_nps: Mapped[int] = mapped_column(Integer)
    total_respostas: Mapped[int] = mapped_column(Integer)
    qtd_promotores: Mapped[int] = mapped_column(Integer)
    qtd_neutros: Mapped[int] = mapped_column(Integer)
    qtd_detratores: Mapped[int] = mapped_column(Integer)
    calculado_em: Mapped[datetime] = mapped_column(DataHoraUTC, default=agora_utc)


class LogAuditoria(Base):
    __tablename__ = "log_auditoria"
    __table_args__ = (
        Index("ix_log_auditoria_criado_em", "criado_em"),
        Index("ix_log_auditoria_acao_criado_em", "acao", "criado_em"),
        Index("ix_log_auditoria_entidade", "tipo_entidade", "id_entidade", "criado_em"),
        Index("ix_log_auditoria_ator_criado_em", "id_usuario_ator", "criado_em"),
    )

    id: Mapped[uuid.UUID] = _pk()
    id_usuario_ator: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("usuario.id", ondelete="RESTRICT"))
    acao: Mapped[str] = mapped_column(String(150))
    tipo_entidade: Mapped[str] = mapped_column(String(100))
    id_entidade: Mapped[uuid.UUID] = mapped_column(Uuid)
    estado_antes: Mapped[dict | None] = mapped_column(JSON)
    estado_depois: Mapped[dict | None] = mapped_column(JSON)
    criado_em: Mapped[datetime] = mapped_column(DataHoraUTC, default=agora_utc)


class LogExportacao(Base):
    __tablename__ = "log_exportacao"
    __table_args__ = (
        Index("ix_log_exportacao_criado_em", "criado_em"),
        Index("ix_log_exportacao_id_pesquisa", "id_pesquisa"),
        Index("ix_log_exportacao_id_analista", "id_analista"),
    )

    id: Mapped[uuid.UUID] = _pk()
    id_analista: Mapped[uuid.UUID] = mapped_column(ForeignKey("usuario.id", ondelete="RESTRICT"))
    id_pesquisa: Mapped[uuid.UUID] = mapped_column(ForeignKey("pesquisa.id", ondelete="RESTRICT"))
    campos_exportados: Mapped[str] = mapped_column(String(500))
    anonimizado: Mapped[bool] = mapped_column(Boolean)
    criado_em: Mapped[datetime] = mapped_column(DataHoraUTC, default=agora_utc)


# ══════════════════════════════════════════════════════════════════
# CAMADA DE IA (o usuário de banco do worker só escreve nestas tabelas)
# ══════════════════════════════════════════════════════════════════

class Prompt(Base):
    """Prompt versionado: cada linha é uma versão; nunca é editado depois de criado."""
    __tablename__ = "prompt"

    id: Mapped[uuid.UUID] = _pk()
    objetivo: Mapped[str] = mapped_column(Text)
    contexto: Mapped[str] = mapped_column(Text)
    saida_esperada: Mapped[str] = mapped_column(Text)
    problemas_encontrados: Mapped[str | None] = mapped_column(Text)
    criado_em: Mapped[datetime] = mapped_column(DataHoraUTC, default=agora_utc)


class VersaoModelo(Base):
    __tablename__ = "versao_modelo"
    __table_args__ = (
        Index("ix_versao_modelo_id_prompt", "id_prompt"),
        # No máximo uma versão ativa, garantido pelo banco
        Index(
            "uq_versao_modelo_unica_ativa", "ativo", unique=True,
            postgresql_where=text("ativo"), sqlite_where=text("ativo"),
        ),
    )

    id: Mapped[uuid.UUID] = _pk()
    provedor: Mapped[str] = mapped_column(String(100))
    nome_modelo: Mapped[str] = mapped_column(String(100))
    rotulo_versao: Mapped[str] = mapped_column(String(100), unique=True)
    id_prompt: Mapped[uuid.UUID] = mapped_column(ForeignKey("prompt.id", ondelete="RESTRICT"))
    # Só vira true pelo gate do golden set (POST /modelos-ia/{id}/ativar)
    ativo: Mapped[bool] = mapped_column(Boolean, default=False)
    promovida_em: Mapped[datetime | None] = mapped_column(DataHoraUTC)
    criada_em: Mapped[datetime] = mapped_column(DataHoraUTC, default=agora_utc)

    prompt: Mapped[Prompt] = relationship(lazy="raise")


class JobIa(Base):
    __tablename__ = "job_ia"
    __table_args__ = (
        Index("ix_job_ia_id_submissao", "id_submissao"),
        # Varredura do worker: WHERE status IN (...) AND proxima_tentativa_em <= agora
        Index("ix_job_ia_status_proxima_tentativa", "status", "proxima_tentativa_em"),
    )

    id: Mapped[uuid.UUID] = _pk()
    id_submissao: Mapped[uuid.UUID] = mapped_column(ForeignKey("submissao.id", ondelete="RESTRICT"))
    status: Mapped[str] = mapped_column(_enum(STATUS_JOB_IA, "ck_job_ia_status"), default="NA_FILA")
    tentativas: Mapped[int] = mapped_column(Integer, default=0)
    ultimo_erro: Mapped[str | None] = mapped_column(String(500))
    # NA_FILA/TENTANDO_NOVAMENTE: quando pode rodar. PROCESSANDO: fim do lease.
    proxima_tentativa_em: Mapped[datetime | None] = mapped_column(DataHoraUTC)
    criado_em: Mapped[datetime] = mapped_column(DataHoraUTC, default=agora_utc)


class AnaliseFeedback(Base):
    """Sugestão da IA. Reanálise cria nova linha; a API mostra a de maior sequencia_versao."""
    __tablename__ = "analise_feedback"
    __table_args__ = (
        CheckConstraint("confianca IS NULL OR (confianca >= 0 AND confianca <= 1)", name="ck_analise_confianca_0_1"),
        UniqueConstraint("id_submissao", "sequencia_versao", name="uq_analise_submissao_sequencia"),
        Index("ix_analise_feedback_id_versao_modelo", "id_versao_modelo"),
    )

    id: Mapped[uuid.UUID] = _pk()
    id_submissao: Mapped[uuid.UUID] = mapped_column(ForeignKey("submissao.id", ondelete="RESTRICT"))
    id_versao_modelo: Mapped[uuid.UUID] = mapped_column(ForeignKey("versao_modelo.id", ondelete="RESTRICT"))
    # Nulos enquanto PENDENTE ou quando a saída do modelo não passou no schema
    sentimento: Mapped[str | None] = mapped_column(_enum(SENTIMENTOS, "ck_analise_sentimento"))
    tema: Mapped[str | None] = mapped_column(_enum(TEMAS, "ck_analise_tema"))
    confianca: Mapped[float | None] = mapped_column(Float)
    justificativa: Mapped[str | None] = mapped_column(Text)
    sequencia_versao: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(_enum(STATUS_ANALISE, "ck_analise_status"))
    criada_em: Mapped[datetime] = mapped_column(DataHoraUTC, default=agora_utc)
    atualizada_em: Mapped[datetime] = mapped_column(DataHoraUTC, default=agora_utc, onupdate=agora_utc)


# ══════════════════════════════════════════════════════════════════
# GOLDEN SET
# ══════════════════════════════════════════════════════════════════

class ComentarioGoldenSet(Base):
    __tablename__ = "comentario_golden_set"

    id: Mapped[uuid.UUID] = _pk()
    texto_comentario: Mapped[str] = mapped_column(Text)
    rotulo_sentimento_humano: Mapped[str] = mapped_column(_enum(SENTIMENTOS, "ck_golden_sentimento"))
    rotulo_tema_humano: Mapped[str] = mapped_column(_enum(TEMAS, "ck_golden_tema"))
    criado_em: Mapped[datetime] = mapped_column(DataHoraUTC, default=agora_utc)


class RotuloGoldenSet(Base):
    __tablename__ = "rotulo_golden_set"
    __table_args__ = (
        Index("ix_rotulo_golden_set_id_comentario", "id_comentario_golden_set"),
        Index("ix_rotulo_golden_set_rotulado_por", "rotulado_por"),
    )

    id: Mapped[uuid.UUID] = _pk()
    id_comentario_golden_set: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("comentario_golden_set.id", ondelete="RESTRICT")
    )
    rotulado_por: Mapped[uuid.UUID] = mapped_column(ForeignKey("usuario.id", ondelete="RESTRICT"))
    eh_desempate: Mapped[bool] = mapped_column(Boolean, default=False)
    rotulo_sentimento: Mapped[str] = mapped_column(_enum(SENTIMENTOS, "ck_rotulo_sentimento"))
    rotulo_tema: Mapped[str] = mapped_column(_enum(TEMAS, "ck_rotulo_tema"))


class AvaliacaoGoldenSet(Base):
    __tablename__ = "avaliacao_golden_set"
    __table_args__ = (
        # "Última avaliação da versão": WHERE id_versao_modelo = ? ORDER BY executada_em DESC
        Index("ix_avaliacao_versao_executada_em", "id_versao_modelo", "executada_em"),
    )

    id: Mapped[uuid.UUID] = _pk()
    id_versao_modelo: Mapped[uuid.UUID] = mapped_column(ForeignKey("versao_modelo.id", ondelete="RESTRICT"))
    acuracia_sentimento: Mapped[float] = mapped_column(Numeric(5, 4, asdecimal=False))
    acuracia_tema: Mapped[float] = mapped_column(Numeric(5, 4, asdecimal=False))
    taxa_falso_positivo: Mapped[float] = mapped_column(Numeric(5, 4, asdecimal=False))
    status: Mapped[str] = mapped_column(_enum(STATUS_AVALIACAO, "ck_avaliacao_status"))
    executada_em: Mapped[datetime] = mapped_column(DataHoraUTC, default=agora_utc)


# ══════════════════════════════════════════════════════════════════
# OPERACIONAIS (sem FK)
# ══════════════════════════════════════════════════════════════════

class EventoCircuitBreaker(Base):
    """Enquanto houver evento com resolvido_em nulo, nenhum comentário sai para o provedor."""
    __tablename__ = "evento_circuit_breaker"
    __table_args__ = (
        Index("ix_evento_circuit_breaker_resolvido_em", "resolvido_em"),
        Index("ix_evento_circuit_breaker_disparado_em", "disparado_em"),
    )

    id: Mapped[uuid.UUID] = _pk()
    motivo: Mapped[str] = mapped_column(String(300))
    custo_acumulado: Mapped[float] = mapped_column(Numeric(12, 4, asdecimal=False))
    limite_custo: Mapped[float] = mapped_column(Numeric(12, 4, asdecimal=False))
    disparado_em: Mapped[datetime] = mapped_column(DataHoraUTC, default=agora_utc)
    resolvido_em: Mapped[datetime | None] = mapped_column(DataHoraUTC)


class SnapshotTelemetria(Base):
    __tablename__ = "snapshot_telemetria"
    __table_args__ = (
        Index("ix_snapshot_telemetria_inicio_janela", "inicio_janela"),
    )

    id: Mapped[uuid.UUID] = _pk()
    inicio_janela: Mapped[datetime] = mapped_column(DataHoraUTC)
    fim_janela: Mapped[datetime] = mapped_column(DataHoraUTC)
    latencia_p50_ms: Mapped[int] = mapped_column(Integer, default=0)
    latencia_p95_ms: Mapped[int] = mapped_column(Integer, default=0)
    taxa_erro_5xx: Mapped[float] = mapped_column(Numeric(5, 4, asdecimal=False), default=0)
    pct_descartado_ec12: Mapped[float] = mapped_column(Numeric(5, 4, asdecimal=False), default=0)
    pct_descartado_ec13: Mapped[float] = mapped_column(Numeric(5, 4, asdecimal=False), default=0)
    qtd_pii_mascaramento_falhou: Mapped[int] = mapped_column(Integer, default=0)
    status_circuit_breaker: Mapped[str] = mapped_column(String(50), default="FECHADO")

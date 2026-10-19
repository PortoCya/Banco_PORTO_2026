"""
Modelos ORM SQLAlchemy — NPS KeyCore v1.0 (16 entidades fiéis ao diagrama ER e ao PRD).
Inclui Constraints de integridade, índices de performance e campos de segurança/LGPD.
"""
import uuid
from datetime import datetime, date
from sqlalchemy import (
    Column, String, Text, Integer, Float, Boolean, Numeric,
    DateTime, Date, ForeignKey, Enum, JSON, CheckConstraint, Index
)
from sqlalchemy.orm import relationship
from app.core.database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.utcnow()


# ══════════════════════════════════════════════════════════════════
# 1. USUARIO (Administração e RBAC: ADMIN | ANALYST)
# ══════════════════════════════════════════════════════════════════
class Usuario(Base):
    __tablename__ = "usuario"

    id          = Column(String(36), primary_key=True, default=_uuid)
    nome        = Column(String(200), nullable=False)
    email       = Column(String(255), nullable=False, unique=True, index=True)
    senha_hash  = Column(String(255), nullable=False)
    papel       = Column(Enum("ADMIN", "ANALYST", name="papel_usuario_enum"), nullable=False, default="ANALYST")
    ativo       = Column(Boolean, nullable=False, default=True)
    criado_em   = Column(DateTime, nullable=False, default=_now)

    pesquisas_criadas = relationship("Pesquisa", back_populates="criador")
    logs_auditoria    = relationship("LogAuditoria", back_populates="usuario_ator")
    logs_exportacao   = relationship("LogExportacao", back_populates="analista")
    rotulos_golden    = relationship("RotuloGoldenSet", back_populates="rotulador")


# ══════════════════════════════════════════════════════════════════
# 2. PESQUISA (Com auto-referência para versionamento sem perder histórico - RF-004)
# ══════════════════════════════════════════════════════════════════
class Pesquisa(Base):
    __tablename__ = "pesquisa"

    id                    = Column(String(36), primary_key=True, default=_uuid)
    titulo                = Column(String(300), nullable=False)
    texto_pergunta_nps    = Column(Text, nullable=False)
    texto_pergunta_aberta = Column(Text, nullable=True)
    status                = Column(
        Enum("RASCUNHO", "PUBLICADA", "PAUSADA", "ARQUIVADA", name="status_pesquisa_enum"),
        nullable=False,
        default="RASCUNHO",
        index=True,
    )
    numero_versao         = Column(Integer, nullable=False, default=1)
    id_pesquisa_pai       = Column(String(36), ForeignKey("pesquisa.uuid" if False else "pesquisa.id", ondelete="SET NULL"), nullable=True)
    criado_por            = Column(String(36), ForeignKey("usuario.id", ondelete="RESTRICT"), nullable=False)
    criada_em             = Column(DateTime, nullable=False, default=_now)
    atualizada_em         = Column(DateTime, nullable=False, default=_now, onupdate=_now)

    criador               = relationship("Usuario", back_populates="pesquisas_criadas")
    pesquisa_pai          = relationship("Pesquisa", remote_side=[id], backref="versoes_filhas")
    links                 = relationship("LinkPesquisa", back_populates="pesquisa", cascade="all, delete-orphan")
    submissoes            = relationship("Submissao", back_populates="pesquisa")
    snapshots_nps         = relationship("SnapshotNps", back_populates="pesquisa", cascade="all, delete-orphan")
    logs_exportacao       = relationship("LogExportacao", back_populates="pesquisa")


# ══════════════════════════════════════════════════════════════════
# 3. LINK_PESQUISA (Tokens NOMINAL de uso único ou ABERTO - RF-005, RF-009, RF-012)
# ══════════════════════════════════════════════════════════════════
class LinkPesquisa(Base):
    __tablename__ = "link_pesquisa"

    id          = Column(String(36), primary_key=True, default=_uuid)
    id_pesquisa = Column(String(36), ForeignKey("pesquisa.id", ondelete="CASCADE"), nullable=False, index=True)
    tipo        = Column(Enum("NOMINAL", "ABERTO", name="tipo_link_enum"), nullable=False, default="ABERTO")
    token       = Column(String(128), nullable=False, unique=True, index=True)
    usado_em    = Column(DateTime, nullable=True)   # nulo até a 1ª submissão (bloqueia reuso em NOMINAL)
    criado_em   = Column(DateTime, nullable=False, default=_now)

    pesquisa    = relationship("Pesquisa", back_populates="links")
    submissoes  = relationship("Submissao", back_populates="link_pesquisa")


# ══════════════════════════════════════════════════════════════════
# 4. SUBMISSAO (Dado primário imutável, nota NPS 0-10, antiduplicidade e LGPD)
# ══════════════════════════════════════════════════════════════════
class Submissao(Base):
    __tablename__ = "submissao"
    __table_args__ = (
        CheckConstraint("nota_nps >= 0 AND nota_nps <= 10", name="ck_submissao_nota_nps_0_10"),
        Index("ix_submissao_pesquisa_criada", "id_pesquisa", "criada_em"),
    )

    id                      = Column(String(36), primary_key=True, default=_uuid)
    id_pesquisa             = Column(String(36), ForeignKey("pesquisa.id", ondelete="RESTRICT"), nullable=False)
    id_link_pesquisa        = Column(String(36), ForeignKey("link_pesquisa.id", ondelete="SET NULL"), nullable=True)
    nota_nps                = Column(Integer, nullable=False)       # 0 a 10, dado primário determinístico
    texto_comentario        = Column(Text, nullable=True)           # íntegro na base interna
    chave_idempotencia      = Column(String(128), nullable=False, unique=True, index=True)
    fingerprint_dispositivo = Column(String(255), nullable=True)
    endereco_ip             = Column(String(128), nullable=True)    # armazenado como hash SHA-256 (LGPD)
    status                  = Column(
        Enum("VALIDA", "BLOQUEADA_DUPLICIDADE", name="status_submissao_enum"),
        nullable=False,
        default="VALIDA",
    )
    status_mascaramento_pii = Column(
        Enum("NAO_APLICAVEL", "MASCARADO", "FALHA_MASCARAMENTO_PII", name="status_pii_enum"),
        nullable=False,
        default="NAO_APLICAVEL",
    )
    criada_em               = Column(DateTime, nullable=False, default=_now)

    pesquisa                = relationship("Pesquisa", back_populates="submissoes")
    link_pesquisa           = relationship("LinkPesquisa", back_populates="submissoes")
    jobs_ia                 = relationship("JobIa", back_populates="submissao", cascade="all, delete-orphan")
    analises_feedback       = relationship("AnaliseFeedback", back_populates="submissao", cascade="all, delete-orphan")


# ══════════════════════════════════════════════════════════════════
# 5. SNAPSHOT_NPS (Cálculo determinístico: %Promotores - %Detratores, -100 a +100)
# ══════════════════════════════════════════════════════════════════
class SnapshotNps(Base):
    __tablename__ = "snapshot_nps"
    __table_args__ = (
        CheckConstraint("valor_nps >= -100 AND valor_nps <= 100", name="ck_snapshot_valor_nps"),
    )

    id              = Column(String(36), primary_key=True, default=_uuid)
    id_pesquisa     = Column(String(36), ForeignKey("pesquisa.id", ondelete="CASCADE"), nullable=False, index=True)
    periodo_inicio  = Column(Date, nullable=False, default=date.today)
    periodo_fim     = Column(Date, nullable=False, default=date.today)
    valor_nps       = Column(Integer, nullable=False)               # -100 a +100, recalculável
    total_respostas = Column(Integer, nullable=False, default=0)
    qtd_promotores  = Column(Integer, nullable=False, default=0)    # notas 9 e 10
    qtd_neutros     = Column(Integer, nullable=False, default=0)    # notas 7 e 8
    qtd_detratores  = Column(Integer, nullable=False, default=0)    # notas 0 a 6
    calculado_em    = Column(DateTime, nullable=False, default=_now)

    pesquisa        = relationship("Pesquisa", back_populates="snapshots_nps")


# ══════════════════════════════════════════════════════════════════
# 6. PROMPT (Engenharia de prompt para análise qualitativa)
# ══════════════════════════════════════════════════════════════════
class Prompt(Base):
    __tablename__ = "prompt"

    id                    = Column(String(36), primary_key=True, default=_uuid)
    objetivo              = Column(Text, nullable=False)
    contexto              = Column(Text, nullable=False)
    saida_esperada        = Column(Text, nullable=False)
    problemas_encontrados = Column(Text, nullable=True)
    criado_em             = Column(DateTime, nullable=False, default=_now)

    versoes_modelo        = relationship("VersaoModelo", back_populates="prompt")


# ══════════════════════════════════════════════════════════════════
# 7. VERSAO_MODELO (Registro e governança de modelos LLM)
# ══════════════════════════════════════════════════════════════════
class VersaoModelo(Base):
    __tablename__ = "versao_modelo"

    id            = Column(String(36), primary_key=True, default=_uuid)
    provedor      = Column(String(100), nullable=False)             # Google Gemini, OpenAI, etc.
    nome_modelo   = Column(String(100), nullable=False)             # gemini-2.0-flash, gpt-4o, etc.
    rotulo_versao = Column(String(100), nullable=False, unique=True)
    id_prompt     = Column(String(36), ForeignKey("prompt.id", ondelete="RESTRICT"), nullable=False)
    ativa         = Column(Boolean, nullable=False, default=True, index=True)
    promovida_em  = Column(DateTime, nullable=True, default=_now)

    prompt            = relationship("Prompt", back_populates="versoes_modelo")
    avaliacoes_golden = relationship("AvaliacaoGoldenSet", back_populates="versao_modelo", cascade="all, delete-orphan")
    analises_feedback = relationship("AnaliseFeedback", back_populates="versao_modelo")


# ══════════════════════════════════════════════════════════════════
# 8. JOB_IA (Fila assíncrona desacoplada — falha nunca bloqueia Submissao)
# ══════════════════════════════════════════════════════════════════
class JobIa(Base):
    __tablename__ = "job_ia"

    id                   = Column(String(36), primary_key=True, default=_uuid)
    id_submissao         = Column(String(36), ForeignKey("submissao.id", ondelete="CASCADE"), nullable=False, index=True)
    status               = Column(
        Enum("NA_FILA", "PROCESSANDO", "CONCLUIDO", "FALHOU", "TENTANDO_NOVAMENTE", name="status_job_ia_enum"),
        nullable=False,
        default="NA_FILA",
        index=True,
    )
    tentativas           = Column(Integer, nullable=False, default=0)
    ultimo_erro          = Column(String(500), nullable=True)
    proxima_tentativa_em = Column(DateTime, nullable=True)
    criado_em            = Column(DateTime, nullable=False, default=_now)

    submissao            = relationship("Submissao", back_populates="jobs_ia")


# ══════════════════════════════════════════════════════════════════
# 9. ANALISE_FEEDBACK (Camada derivada da IA — não altera resposta original)
# ══════════════════════════════════════════════════════════════════
class AnaliseFeedback(Base):
    __tablename__ = "analise_feedback"
    __table_args__ = (
        CheckConstraint("confianca >= 0.0 AND confianca <= 1.0", name="ck_analise_confianca_0_1"),
    )

    id               = Column(String(36), primary_key=True, default=_uuid)
    id_submissao     = Column(String(36), ForeignKey("submissao.id", ondelete="CASCADE"), nullable=False, index=True)
    id_versao_modelo = Column(String(36), ForeignKey("versao_modelo.id", ondelete="RESTRICT"), nullable=False)
    sentimento       = Column(Enum("POSITIVO", "NEUTRO", "NEGATIVO", name="sentimento_enum"), nullable=False)
    tema             = Column(String(200), nullable=False)          # taxonomia fechada
    confianca        = Column(Float, nullable=False)                # 0.0 a 1.0
    justificativa    = Column(Text, nullable=True)
    sequencia_versao = Column(Integer, nullable=False, default=1)   # reprocessamento gera nova versão
    status           = Column(
        Enum(
            "PENDENTE", "CONCLUIDA", "FALHA_SCHEMA",
            "DESCARTADA_PARCIAL", "BAIXA_CONFIANCA",
            name="status_analise_feedback_enum"
        ),
        nullable=False,
        default="CONCLUIDA",
    )
    criada_em        = Column(DateTime, nullable=False, default=_now)
    atualizada_em    = Column(DateTime, nullable=False, default=_now, onupdate=_now)

    submissao        = relationship("Submissao", back_populates="analises_feedback")
    versao_modelo    = relationship("VersaoModelo", back_populates="analises_feedback")


# ══════════════════════════════════════════════════════════════════
# 10. AVALIACAO_GOLDEN_SET (Benchmark de qualidade do modelo de IA)
# ══════════════════════════════════════════════════════════════════
class AvaliacaoGoldenSet(Base):
    __tablename__ = "avaliacao_golden_set"

    id                  = Column(String(36), primary_key=True, default=_uuid)
    id_versao_modelo    = Column(String(36), ForeignKey("versao_modelo.id", ondelete="CASCADE"), nullable=False)
    acuracia_sentimento = Column(Numeric(5, 4), nullable=False)
    acuracia_tema       = Column(Numeric(5, 4), nullable=False)
    taxa_falso_positivo = Column(Numeric(5, 4), nullable=False)
    status              = Column(Enum("APROVADO", "REPROVADO", name="status_golden_enum"), nullable=False)
    executada_em        = Column(DateTime, nullable=False, default=_now)

    versao_modelo       = relationship("VersaoModelo", back_populates="avaliacoes_golden")


# ══════════════════════════════════════════════════════════════════
# 11. COMENTARIO_GOLDEN_SET (Dataset padrão-ouro para calibração da IA)
# ══════════════════════════════════════════════════════════════════
class ComentarioGoldenSet(Base):
    __tablename__ = "comentario_golden_set"

    id                       = Column(String(36), primary_key=True, default=_uuid)
    texto_comentario         = Column(Text, nullable=False)
    rotulo_sentimento_humano = Column(String(50), nullable=False)
    rotulo_tema_humano       = Column(String(100), nullable=False)
    criado_em                = Column(DateTime, nullable=False, default=_now)

    rotulos                  = relationship("RotuloGoldenSet", back_populates="comentario_golden", cascade="all, delete-orphan")


# ══════════════════════════════════════════════════════════════════
# 12. ROTULO_GOLDEN_SET (Rotulagem dupla + desempate por analistas)
# ══════════════════════════════════════════════════════════════════
class RotuloGoldenSet(Base):
    __tablename__ = "rotulo_golden_set"

    id                       = Column(String(36), primary_key=True, default=_uuid)
    id_comentario_golden_set = Column(String(36), ForeignKey("comentario_golden_set.id", ondelete="CASCADE"), nullable=False)
    rotulado_por             = Column(String(36), ForeignKey("usuario.id", ondelete="RESTRICT"), nullable=False)
    eh_desempate             = Column(Boolean, nullable=False, default=False)
    rotulo_sentimento        = Column(String(50), nullable=False)
    rotulo_tema              = Column(String(100), nullable=False)

    comentario_golden        = relationship("ComentarioGoldenSet", back_populates="rotulos")
    rotulador                = relationship("Usuario", back_populates="rotulos_golden")


# ══════════════════════════════════════════════════════════════════
# 13. LOG_AUDITORIA (Trilha imutável de ações críticas - RF-020 / LGPD)
# ══════════════════════════════════════════════════════════════════
class LogAuditoria(Base):
    __tablename__ = "log_auditoria"

    id              = Column(String(36), primary_key=True, default=_uuid)
    id_usuario_ator = Column(String(36), ForeignKey("usuario.id", ondelete="SET NULL"), nullable=True, index=True)
    acao            = Column(String(150), nullable=False, index=True)
    tipo_entidade   = Column(String(100), nullable=False)
    id_entidade     = Column(String(36), nullable=False)
    estado_antes    = Column(JSON, nullable=True)
    estado_depois   = Column(JSON, nullable=True)
    criado_em       = Column(DateTime, nullable=False, default=_now, index=True)

    usuario_ator    = relationship("Usuario", back_populates="logs_auditoria")


# ══════════════════════════════════════════════════════════════════
# 14. LOG_EXPORTACAO (Governança LGPD de exportações CSV - Pág. 9 PRD)
# ══════════════════════════════════════════════════════════════════
class LogExportacao(Base):
    __tablename__ = "log_exportacao"

    id                = Column(String(36), primary_key=True, default=_uuid)
    id_analista       = Column(String(36), ForeignKey("usuario.id", ondelete="RESTRICT"), nullable=False, index=True)
    id_pesquisa       = Column(String(36), ForeignKey("pesquisa.id", ondelete="RESTRICT"), nullable=False, index=True)
    campos_exportados = Column(String(500), nullable=False)
    anonimizado       = Column(Boolean, nullable=False, default=True)
    criado_em         = Column(DateTime, nullable=False, default=_now)

    analista          = relationship("Usuario", back_populates="logs_exportacao")
    pesquisa          = relationship("Pesquisa", back_populates="logs_exportacao")


# ══════════════════════════════════════════════════════════════════
# 15. EVENTO_CIRCUIT_BREAKER (Proteção financeira e operacional de IA)
# ══════════════════════════════════════════════════════════════════
class EventoCircuitBreaker(Base):
    __tablename__ = "evento_circuit_breaker"

    id              = Column(String(36), primary_key=True, default=_uuid)
    motivo          = Column(String(300), nullable=False)
    custo_acumulado = Column(Numeric(10, 4), nullable=False, default=0)
    limite_custo    = Column(Numeric(10, 4), nullable=False, default=100.0)
    disparado_em    = Column(DateTime, nullable=False, default=_now)
    resolvido_em    = Column(DateTime, nullable=True)


# ══════════════════════════════════════════════════════════════════
# 16. SNAPSHOT_TELEMETRIA (Observabilidade p50, p95, 5xx, falhas PII - Pág. 9 PRD)
# ══════════════════════════════════════════════════════════════════
class SnapshotTelemetria(Base):
    __tablename__ = "snapshot_telemetria"

    id                          = Column(String(36), primary_key=True, default=_uuid)
    inicio_janela               = Column(DateTime, nullable=False, default=_now)
    fim_janela                  = Column(DateTime, nullable=False, default=_now)
    latencia_p50_ms             = Column(Integer, nullable=False, default=0)
    latencia_p95_ms             = Column(Integer, nullable=False, default=0)
    taxa_erro_5xx               = Column(Numeric(5, 4), nullable=False, default=0)
    pct_descartado_ec12         = Column(Numeric(5, 4), nullable=False, default=0)
    pct_descartado_ec13         = Column(Numeric(5, 4), nullable=False, default=0)
    qtd_pii_mascaramento_falhou = Column(Integer, nullable=False, default=0)
    status_circuit_breaker      = Column(String(50), nullable=False, default="FECHADO")

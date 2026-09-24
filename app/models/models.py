"""
Modelos SQLAlchemy — todas as 16 entidades do diagrama.

Convenções:
  • uuid4 como PK (String 36) para portabilidade entre SGBDs
  • created_at / updated_at preenchidos automaticamente
  • FKs explícitas com ondelete="CASCADE" onde faz sentido
"""
import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean, Column, DateTime, Enum, Float, ForeignKey,
    Integer, String, Text, JSON
)
from sqlalchemy.orm import relationship

from app.core.database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.utcnow()


# ══════════════════════════════════════════════════════════════════
# 1. VIDEO_MODELO
# ══════════════════════════════════════════════════════════════════
class VideoModelo(Base):
    __tablename__ = "video_modelo"

    uuid        = Column(String(36), primary_key=True, default=_uuid)
    provider    = Column(String(100), nullable=False)          # ex: OpenAI, Anthropic
    nome_modelo = Column(String(100), nullable=False)
    status_ativo = Column(Boolean, default=True)
    is_current  = Column(Boolean, default=False)
    created_at  = Column(DateTime, default=_now)

    # Relacionamentos reversos
    tutores     = relationship("TutorCircuitoTreinado", back_populates="video_modelo")


# ══════════════════════════════════════════════════════════════════
# 2. TUTOR_CIRCUITO_TREINADO
# ══════════════════════════════════════════════════════════════════
class TutorCircuitoTreinado(Base):
    __tablename__ = "tutor_circuito_treinado"

    uuid                = Column(String(36), primary_key=True, default=_uuid)
    fk_video_modelo     = Column(String(36), ForeignKey("video_modelo.uuid", ondelete="SET NULL"), nullable=True)
    rodadas_benchmarks  = Column(Integer, default=0)
    document_base       = Column(Text)                          # path/URL do documento base
    base_train_pipeline = Column(Text)                          # pipeline de treino
    analise             = Column(Text)
    created_at          = Column(DateTime, default=_now)

    # Relacionamentos
    video_modelo        = relationship("VideoModelo", back_populates="tutores")
    configurar_sets     = relationship("ConfigurarCircuitoSet", back_populates="tutor")
    avaliacao_sets      = relationship("AvaliacaoCircuitoSet", back_populates="tutor")
    prompts             = relationship("Prompt", back_populates="tutor")


# ══════════════════════════════════════════════════════════════════
# 3. TEMPLATE_ELEMENTOS
# ══════════════════════════════════════════════════════════════════
class TemplateElementos(Base):
    __tablename__ = "template_elementos"

    uuid              = Column(String(36), primary_key=True, default=_uuid)
    nome_area         = Column(String(200))
    balance_pdf_src   = Column(Text)                            # caminho/URL do PDF
    template_para_3   = Column(String(100))                     # referência ao template
    get_dimensionamento_kpis = Column(Text)
    modelo_agr        = Column(String(200))
    status_circuito_treinado = Column(String(50))

    # Sem FK direta no diagrama; referenciado via TutorCircuitoTreinado
    tutores_config    = relationship("ConfigurarCircuitoSet", back_populates="template")


# ══════════════════════════════════════════════════════════════════
# 4. AVALIACAO_CIRCUITO_SET
# ══════════════════════════════════════════════════════════════════
class AvaliacaoCircuitoSet(Base):
    __tablename__ = "avaliacao_circuito_set"

    uuid                = Column(String(36), primary_key=True, default=_uuid)
    fk_video_modelo     = Column(String(36), ForeignKey("tutor_circuito_treinado.uuid", ondelete="CASCADE"))
    rodadas_benchmarks  = Column(Integer, default=0)
    document_base       = Column(Text)
    base_train_pipeline = Column(Text)
    analise             = Column(Text)
    created_at          = Column(DateTime, default=_now)

    tutor               = relationship("TutorCircuitoTreinado", back_populates="avaliacao_sets")


# ══════════════════════════════════════════════════════════════════
# 5. PROMPT
# ══════════════════════════════════════════════════════════════════
class Prompt(Base):
    __tablename__ = "prompt"

    uuid            = Column(String(36), primary_key=True, default=_uuid)
    conteudo        = Column(Text, nullable=False)              # texto do prompt
    contexto        = Column(Text)
    fk_video_modelo = Column(String(36), ForeignKey("tutor_circuito_treinado.uuid", ondelete="CASCADE"))
    prompt_engenharia_template = Column(Text)
    status_ativo    = Column(Boolean, default=True)

    tutor           = relationship("TutorCircuitoTreinado", back_populates="prompts")


# ══════════════════════════════════════════════════════════════════
# 6. CONFIGURAR_CIRCUITO_SET
# ══════════════════════════════════════════════════════════════════
class ConfigurarCircuitoSet(Base):
    __tablename__ = "configurar_circuito_set"

    uuid                        = Column(String(36), primary_key=True, default=_uuid)
    fk_tutor                    = Column(String(36), ForeignKey("tutor_circuito_treinado.uuid", ondelete="CASCADE"))
    fk_template                 = Column(String(36), ForeignKey("template_elementos.uuid", ondelete="SET NULL"), nullable=True)
    status_certifica_humanizado  = Column(String(50))
    status_certifica_humanizado2 = Column(String(50))
    forma_reposta_elementos     = Column(Text)
    created_at                  = Column(DateTime, default=_now)

    tutor    = relationship("TutorCircuitoTreinado", back_populates="configurar_sets")
    template = relationship("TemplateElementos", back_populates="tutores_config")


# ══════════════════════════════════════════════════════════════════
# 7. USUARIO (EQUIPO)
# ══════════════════════════════════════════════════════════════════
class Usuario(Base):
    __tablename__ = "usuario"

    uuid       = Column(String(36), primary_key=True, default=_uuid)
    nome       = Column(String(200), nullable=False)
    email      = Column(String(200), unique=True, nullable=False, index=True)  # ADMIN/ANALISTA/PT
    role       = Column(Enum("ADMIN", "ANALISTA", "PT", name="role_enum"), nullable=False, default="ANALISTA")
    status     = Column(String(30), default="ativo")
    created_at = Column(DateTime, default=_now)

    conversas  = relationship("Conversa", back_populates="usuario")
    gerenciacoes = relationship("Gerenciacao", back_populates="usuario")


# ══════════════════════════════════════════════════════════════════
# 8. CONVERSA
# ══════════════════════════════════════════════════════════════════
class Conversa(Base):
    __tablename__ = "conversa"

    uuid              = Column(String(36), primary_key=True, default=_uuid)
    fk_usuario        = Column(String(36), ForeignKey("usuario.uuid", ondelete="CASCADE"))
    titulo            = Column(String(300))
    tipo_consultor    = Column(String(50))                     # personagem IA ativo
    status            = Column(String(30), default="aberta")
    configuracoes     = Column(JSON)                           # ajustes da sessão
    created_at        = Column(DateTime, default=_now)
    updated_at        = Column(DateTime, default=_now, onupdate=_now)

    usuario           = relationship("Usuario", back_populates="conversas")
    loa_punicoes      = relationship("LoaPunicao", back_populates="conversa")


# ══════════════════════════════════════════════════════════════════
# 9. LOA_PUNICAO  (atributos da requisição de IA)
# ══════════════════════════════════════════════════════════════════
class LoaPunicao(Base):
    __tablename__ = "loa_punicao"

    uuid             = Column(String(36), primary_key=True, default=_uuid)
    fk_conversa_set  = Column(String(36), ForeignKey("conversa.uuid", ondelete="CASCADE"))
    tipo             = Column(String(50))                      # tipo_atributo
    boolean_status   = Column(Boolean, default=False)
    valor            = Column(Float)
    metodo_ativo     = Column(String(100))
    created_at       = Column(DateTime, default=_now)

    conversa         = relationship("Conversa", back_populates="loa_punicoes")
    matriz_punicoes  = relationship("MatrizPunicaoSet", back_populates="loa_punicao")


# ══════════════════════════════════════════════════════════════════
# 10. MATRIZ_PUNICAO_SET
# ══════════════════════════════════════════════════════════════════
class MatrizPunicaoSet(Base):
    __tablename__ = "matriz_punicao_set"

    uuid              = Column(String(36), primary_key=True, default=_uuid)
    fk_loa_punicao    = Column(String(36), ForeignKey("loa_punicao.uuid", ondelete="CASCADE"))
    fk_kpis_pot       = Column(String(36))                     # FK opcional para dimensoes_kpis
    boolean_relevante = Column(Boolean, default=False)
    nota_pot          = Column(Float)
    nota_relevancia   = Column(Float)
    get_pontuacao     = Column(Float)                          # calculado
    get_pontuacao2    = Column(Float)
    created_at        = Column(DateTime, default=_now)

    loa_punicao       = relationship("LoaPunicao", back_populates="matriz_punicoes")


# ══════════════════════════════════════════════════════════════════
# 11. LINHA_RACIOCINIO
# ══════════════════════════════════════════════════════════════════
class LinhaRaciocinio(Base):
    __tablename__ = "linha_raciocinio"

    uuid          = Column(String(36), primary_key=True, default=_uuid)
    fk_gerencia   = Column(String(36), ForeignKey("gerenciacao.uuid", ondelete="CASCADE"))
    nome          = Column(String(200))
    trace         = Column(Text)                              # log da linha de raciocínio IA
    status        = Column(String(50))
    created_at    = Column(DateTime, default=_now)
    created_at2   = Column(DateTime)

    gerenciacao   = relationship("Gerenciacao", back_populates="linhas_raciocinio")


# ══════════════════════════════════════════════════════════════════
# 12. DIMENSOES_KPIS
# ══════════════════════════════════════════════════════════════════
class DimensoesKpis(Base):
    __tablename__ = "dimensoes_kpis"

    uuid             = Column(String(36), primary_key=True, default=_uuid)
    fk_gerencia      = Column(String(36), ForeignKey("gerenciacao.uuid", ondelete="CASCADE"))
    data             = Column(DateTime, default=_now)
    periodo_fim      = Column(DateTime)
    valor_pot        = Column(Float)                          # 100 + 1.1% remunerado
    get_pontuacoes   = Column(Float)
    get_pontuacoes2  = Column(Float)
    created_at       = Column(DateTime, default=_now)

    gerenciacao      = relationship("Gerenciacao", back_populates="dimensoes_kpis")


# ══════════════════════════════════════════════════════════════════
# 13. LOG_DIRECIONAR
# ══════════════════════════════════════════════════════════════════
class LogDirecionar(Base):
    __tablename__ = "log_direcionar"

    uuid             = Column(String(36), primary_key=True, default=_uuid)
    fk_usuario       = Column(String(36), ForeignKey("usuario.uuid", ondelete="CASCADE"))
    fk_associacao    = Column(String(36), ForeignKey("gerenciacao.uuid", ondelete="SET NULL"), nullable=True)
    destino_associado = Column(String(200))
    boolean_status   = Column(Boolean, default=False)
    created_at       = Column(DateTime, default=_now)

    gerenciacao      = relationship("Gerenciacao", back_populates="logs_direcionar")


# ══════════════════════════════════════════════════════════════════
# 14. GERENCIACAO
# ══════════════════════════════════════════════════════════════════
class Gerenciacao(Base):
    __tablename__ = "gerenciacao"

    uuid               = Column(String(36), primary_key=True, default=_uuid)
    fk_pessoa          = Column(String(36), ForeignKey("usuario.uuid", ondelete="CASCADE"))
    fk_loa_punicao     = Column(String(36), ForeignKey("loa_punicao.uuid", ondelete="SET NULL"), nullable=True)
    tipo_pot           = Column(String(50))                   # O/N/Q base primário
    tempo_gerenciacao  = Column(DateTime)
    chave_referencia   = Column(String(200), unique=True, index=True)  # UK
    fingerprint_dispositivo = Column(String(500))
    credencial_ip      = Column(String(50))
    status             = Column(String(50))                   # ABERTO/PROCESSANDO/CONCLUIDO/FALHA/PENDENTE
    status_associacao  = Column(String(50))
    created_at         = Column(DateTime, default=_now)

    # Relacionamentos
    usuario            = relationship("Usuario", back_populates="gerenciacoes")
    linhas_raciocinio  = relationship("LinhaRaciocinio", back_populates="gerenciacao")
    dimensoes_kpis     = relationship("DimensoesKpis", back_populates="gerenciacao")
    logs_direcionar    = relationship("LogDirecionar", back_populates="gerenciacao")
    soa_ia             = relationship("SoaIa", back_populates="gerenciacao", uselist=False)
    analises_feedback  = relationship("AnaliseFeedback", back_populates="gerenciacao")


# ══════════════════════════════════════════════════════════════════
# 15. SOA_IA  (orquestrador de chamadas IA)
# ══════════════════════════════════════════════════════════════════
class SoaIa(Base):
    __tablename__ = "soa_ia"

    uuid             = Column(String(36), primary_key=True, default=_uuid)
    fk_gerenciacao   = Column(String(36), ForeignKey("gerenciacao.uuid", ondelete="CASCADE"), unique=True)
    status           = Column(
        Enum("NA", "FILA", "PROCESSANDO", "CONCLUIDO", "FALHA", "TIMEOUT", "REMANENTE", name="soa_status_enum"),
        default="NA"
    )
    allow_queue      = Column(Boolean, default=True)
    created_at       = Column(DateTime, default=_now)
    updated_at       = Column(DateTime, default=_now, onupdate=_now)
    created_at2      = Column(DateTime)

    gerenciacao      = relationship("Gerenciacao", back_populates="soa_ia")


# ══════════════════════════════════════════════════════════════════
# 16. ANALISE_FEEDBACK
# ══════════════════════════════════════════════════════════════════
class AnaliseFeedback(Base):
    __tablename__ = "analise_feedback"

    uuid               = Column(String(36), primary_key=True, default=_uuid)
    fk_gerenciacao     = Column(String(36), ForeignKey("gerenciacao.uuid", ondelete="CASCADE"))
    fk_video_modelo    = Column(String(36), ForeignKey("video_modelo.uuid", ondelete="SET NULL"), nullable=True)
    sentimento         = Column(Enum("POSITIVO", "NEUTRO", "NEGATIVO", name="sentimento_enum"))
    tema               = Column(String(200))
    confianca          = Column(Float)                        # 0.0–1.0
    justificativa      = Column(Text)
    sugestoes_acao     = Column(JSON)                         # lista de ações sugeridas pela IA
    status             = Column(String(50))
    created_at         = Column(DateTime, default=_now)

    gerenciacao        = relationship("Gerenciacao", back_populates="analises_feedback")

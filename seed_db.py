"""
Script utilitário: cria as 16 tabelas do banco NPS KeyCore v1.0 e popula dados iniciais seguros (seed).
Execute: python seed_db.py
"""
import logging
from datetime import datetime

from app.core.database import Base, engine, SessionLocal
from app.core.security import gerar_senha_hash
from app.models.models import (
    Usuario,
    Pesquisa,
    LinkPesquisa,
    Prompt,
    VersaoModelo,
    ComentarioGoldenSet,
    AvaliacaoGoldenSet,
    SnapshotTelemetria,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def criar_tabelas():
    logger.info("Criando as 16 tabelas do NPS KeyCore v1.0...")
    Base.metadata.create_all(bind=engine)
    logger.info("Tabelas criadas com sucesso.")


def popular_dados():
    db = SessionLocal()
    try:
        # 1. Usuários padrão (ADMIN e ANALYST) com hash forte PBKDF2-HMAC-SHA256
        admin = db.query(Usuario).filter(Usuario.email == "admin@keycore.com.br").first()
        if not admin:
            admin = Usuario(
                nome="Admin KeyCore",
                email="admin@keycore.com.br",
                senha_hash=gerar_senha_hash("Admin@KeyCore2026!"),
                papel="ADMIN",
                ativo=True,
            )
            db.add(admin)
            db.flush()

        analista = db.query(Usuario).filter(Usuario.email == "analista@keycore.com.br").first()
        if not analista:
            analista = Usuario(
                nome="Analista KeyCore",
                email="analista@keycore.com.br",
                senha_hash=gerar_senha_hash("Analista@KeyCore2026!"),
                papel="ANALYST",
                ativo=True,
            )
            db.add(analista)
            db.flush()

        # 2. Prompt e VersaoModelo (Google Gemini gratuito por padrão)
        if not db.query(Prompt).first():
            prompt = Prompt(
                objetivo="Classificar sentimento e tema de feedbacks NPS com alta precisão e sem alucinação.",
                contexto="Comentários abertos de clientes respondendo pesquisas de satisfação NPS da KeyCore.",
                saida_esperada='JSON estrito com {"sentimento": "POSITIVO|NEUTRO|NEGATIVO", "tema": "...", "confianca": 0.0-1.0, "justificativa": "..."}',
                problemas_encontrados="Nenhum. PII mascarado previamente no backend antes do envio.",
            )
            db.add(prompt)
            db.flush()

            versao = VersaoModelo(
                provedor="Google Gemini",
                nome_modelo="gemini-2.0-flash",
                rotulo_versao="gemini-2.0-flash-v1.0",
                id_prompt=prompt.id,
                ativa=True,
            )
            db.add(versao)
            db.flush()

            avaliacao = AvaliacaoGoldenSet(
                id_versao_modelo=versao.id,
                acuracia_sentimento=0.9450,
                acuracia_tema=0.9120,
                taxa_falso_positivo=0.0210,
                status="APROVADO",
            )
            db.add(avaliacao)

        # 3. Pesquisa inicial publicada + Link público para teste imediato
        if not db.query(Pesquisa).first():
            pesquisa = Pesquisa(
                titulo="Pesquisa Oficial de Satisfação NPS KeyCore 2026",
                texto_pergunta_nps="Em uma escala de 0 a 10, o quanto você recomendaria a KeyCore para um colega ou parceiro?",
                texto_pergunta_aberta="Qual foi o principal motivo para a sua nota?",
                status="PUBLICADA",
                numero_versao=1,
                criado_por=admin.id,
            )
            db.add(pesquisa)
            db.flush()

            link_aberto = LinkPesquisa(
                id_pesquisa=pesquisa.id,
                tipo="ABERTO",
                token="nps-keycore-2026",
            )
            db.add(link_aberto)

        # 4. Comentário Golden Set e Telemetria inicial
        if not db.query(ComentarioGoldenSet).first():
            db.add(
                ComentarioGoldenSet(
                    texto_comentario="O suporte técnico resolveu meu chamado em 5 minutos, excelente!",
                    rotulo_sentimento_humano="POSITIVO",
                    rotulo_tema_humano="SUPORTE",
                )
            )

        if not db.query(SnapshotTelemetria).first():
            db.add(
                SnapshotTelemetria(
                    inicio_janela=datetime.utcnow(),
                    fim_janela=datetime.utcnow(),
                    latencia_p50_ms=42,
                    latencia_p95_ms=115,
                    taxa_erro_5xx=0.0,
                    pct_descartado_ec12=0.0,
                    pct_descartado_ec13=0.0,
                    qtd_pii_mascaramento_falhou=0,
                    status_circuit_breaker="FECHADO",
                )
            )

        db.commit()
        logger.info("Dados iniciais inseridos com sucesso.")

    except Exception as exc:
        db.rollback()
        logger.error("Erro ao popular banco: %s", exc)
        raise
    finally:
        db.close()


if __name__ == "__main__":
    criar_tabelas()
    popular_dados()

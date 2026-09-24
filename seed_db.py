"""
Script utilitário: cria as tabelas do banco e popula dados iniciais (seed).
Execute: python seed_db.py
"""
import logging

from app.core.database import Base, engine, SessionLocal
import app.models.models  # noqa: F401 — registra todos os modelos

from app.models.models import VideoModelo, Prompt, Usuario, TutorCircuitoTreinado

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def criar_tabelas():
    logger.info("Criando tabelas...")
    Base.metadata.create_all(bind=engine)
    logger.info("Tabelas criadas.")


def popular_dados():
    db = SessionLocal()
    try:
        # Modelo de IA padrão
        if not db.query(VideoModelo).first():
            modelo = VideoModelo(
                provider="OpenAI",
                nome_modelo="gpt-4o",
                status_ativo=True,
                is_current=True,
            )
            db.add(modelo)
            db.flush()

            # Tutor vinculado ao modelo
            tutor = TutorCircuitoTreinado(
                fk_video_modelo=modelo.uuid,
                rodadas_benchmarks=0,
                document_base="docs/base.pdf",
                analise="Tutor padrão do sistema",
            )
            db.add(tutor)
            db.flush()

            # Prompt padrão do sistema
            prompt = Prompt(
                fk_video_modelo=tutor.uuid,   # FK aponta para tutor_circuito_treinado
                conteudo=(
                    "Você é um consultor de negócios especializado, experiente e direto. "
                    "Ajude o usuário a tomar decisões estratégicas com base em dados e boas práticas. "
                    "Use linguagem profissional mas acessível."
                ),
                contexto="Contexto geral de consultoria empresarial",
                status_ativo=True,
            )
            db.add(prompt)

        # Usuário admin padrão
        if not db.query(Usuario).filter(Usuario.email == "admin@consultoria.ai").first():
            admin = Usuario(
                nome="Administrador",
                email="admin@consultoria.ai",
                role="ADMIN",
                status="ativo",
            )
            db.add(admin)

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

"""
Script utilitário: cria as tabelas do banco e popula dados iniciais (seed).
Execute: python seed_db.py
"""
import logging
import os

from dotenv import load_dotenv

load_dotenv()  # ADMIN_EMAIL/ADMIN_SENHA/SECRET_KEY vêm do .env

from app.core.database import Base, engine, SessionLocal
import app.models.models  # noqa: F401 — registra todos os modelos

from app.core.security import gerar_hash_senha
from app.models.models import VideoModelo, Prompt, Usuario, TutorCircuitoTreinado
from app.schemas.schemas import SENHA_MIN

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

        # Primeiro ADMIN: credenciais só pelo ambiente, nunca fixas no código
        admin_email = os.environ.get("ADMIN_EMAIL", "").strip().lower()
        admin_senha = os.environ.get("ADMIN_SENHA", "")
        if not admin_email or len(admin_senha) < SENHA_MIN:
            logger.warning(
                "ADMIN_EMAIL/ADMIN_SENHA não definidos (senha mín. %d caracteres) — "
                "nenhum ADMIN criado.", SENHA_MIN,
            )
        elif not db.query(Usuario).filter(Usuario.email == admin_email).first():
            db.add(Usuario(
                nome="Administrador",
                email=admin_email,
                senha_hash=gerar_hash_senha(admin_senha),
                papel="ADMIN",
            ))
            logger.info("ADMIN inicial criado.")

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

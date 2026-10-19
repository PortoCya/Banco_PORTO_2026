"""
Configuração do banco de dados com SQLAlchemy.
Utiliza SQLite por padrão (ajuste DATABASE_URL em .env para PostgreSQL/MySQL).
"""
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from sqlalchemy.pool import StaticPool
import logging

from app.core.config import settings

logger = logging.getLogger(__name__)

# ─── Engine ──────────────────────────────────────────────────────────────────
connect_args = {}
if settings.DATABASE_URL.startswith("sqlite"):
    connect_args = {"check_same_thread": False}
    engine = create_engine(
        settings.DATABASE_URL,
        connect_args=connect_args,
        poolclass=StaticPool,
        echo=settings.DB_ECHO,
    )
else:
    engine = create_engine(
        settings.DATABASE_URL,
        pool_pre_ping=True,          # reconecta se conexão morrer
        pool_size=10,
        max_overflow=20,
        pool_timeout=30,
        pool_recycle=1800,
        echo=settings.DB_ECHO,
    )


# Habilita FK para SQLite
@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    if settings.DATABASE_URL.startswith("sqlite"):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


# ─── Session ─────────────────────────────────────────────────────────────────
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


# ─── Base declarativa ────────────────────────────────────────────────────────
class Base(DeclarativeBase):
    pass


# ─── Dependency para FastAPI ──────────────────────────────────────────────────
def get_db():
    """Gera uma sessão por requisição e garante fechamento ao final."""
    db = SessionLocal()
    try:
        yield db
    except Exception as exc:
        logger.error("Erro na sessão do banco: %s", exc)
        db.rollback()
        raise
    finally:
        db.close()

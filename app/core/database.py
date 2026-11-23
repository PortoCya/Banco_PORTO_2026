"""
Banco de dados (SQLAlchemy 2.0).

Um único engine por processo, com pool de conexões: cada requisição pega uma
conexão emprestada e devolve ao final (nunca abre uma conexão por request).
Toda conexão PostgreSQL nasce com timeouts de conexão, de comando e de lock.
"""
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import settings


def criar_engine(url: str, nome_aplicacao: str = "nps-api") -> Engine:
    if url.startswith("sqlite"):
        # SQLite só em desenvolvimento/testes
        opcoes: dict = {"connect_args": {"check_same_thread": False, "timeout": 5}}
        if ":memory:" in url or url in ("sqlite://", "sqlite:///"):
            opcoes["poolclass"] = StaticPool   # banco em memória = uma conexão só
        engine = create_engine(url, echo=settings.DB_ECHO, hide_parameters=True, **opcoes)

        @event.listens_for(engine, "connect")
        def _ativar_fk(dbapi_connection, _):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

        return engine

    return create_engine(
        url,
        echo=settings.DB_ECHO,
        hide_parameters=True,                             # erro de SQL nunca carrega dados
        pool_pre_ping=True,                               # descarta conexão morta
        pool_size=settings.DB_POOL_SIZE,
        max_overflow=settings.DB_MAX_OVERFLOW,
        pool_timeout=settings.DB_POOL_TIMEOUT_SEGUNDOS,
        pool_recycle=settings.DB_POOL_RECYCLE_SEGUNDOS,
        connect_args={
            "connect_timeout": settings.DB_CONNECT_TIMEOUT_SEGUNDOS,
            "application_name": nome_aplicacao,
            "options": (
                f"-c statement_timeout={settings.DB_STATEMENT_TIMEOUT_MS} "
                f"-c lock_timeout={settings.DB_LOCK_TIMEOUT_MS} "
                "-c idle_in_transaction_session_timeout=60000 "
                "-c timezone=UTC"
            ),
        },
    )


engine = criar_engine(settings.DATABASE_URL)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db():
    """
    Uma sessão por requisição. A rota decide quando dar commit (uma transação
    por operação); qualquer erro desfaz tudo o que não foi confirmado.
    """
    db = SessionLocal()
    try:
        yield db
    except Exception:
        # Sem log aqui: a mensagem de erros do banco carrega os parâmetros do
        # SQL (e-mail, hash, comentário). Quem loga é o handler global.
        db.rollback()
        raise
    finally:
        db.close()

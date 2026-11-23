"""
Ambiente do Alembic. A URL vem de DATABASE_URL (mesma configuração da app).
"""
from logging.config import fileConfig

from alembic import context

from app.core.config import settings
from app.core.database import Base, criar_engine
import app.models.models  # noqa: F401 — registra as tabelas no metadata

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata
URL = config.get_main_option("sqlalchemy.url") or settings.DATABASE_URL


def _renderizar(tipo, objeto, autogen_context):
    """Migration não importa código da app: DataHoraUTC vira o tipo do banco."""
    if tipo == "type" and type(objeto).__name__ == "DataHoraUTC":
        return "sa.DateTime(timezone=True)"
    return False


def run_migrations_offline() -> None:
    """Gera o SQL sem conectar (alembic upgrade head --sql), para revisão."""
    context.configure(
        url=URL, target_metadata=target_metadata, literal_binds=True,
        dialect_opts={"paramstyle": "named"}, compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = criar_engine(URL, nome_aplicacao="nps-alembic")
    with engine.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            render_item=_renderizar,
            # SQLite (dev/testes) não tem ALTER completo: o modo batch recria a tabela
            render_as_batch=connection.dialect.name == "sqlite",
        )
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

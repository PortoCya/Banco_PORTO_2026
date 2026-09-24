"""
Ponto de entrada da aplicação FastAPI.
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware

from app.core.config import settings
from app.core.database import Base, engine
from app.core.errors import register_exception_handlers
from app.api.v1.router import api_router

# Importa todos os modelos para que o SQLAlchemy os registre antes de criar as tabelas
import app.models.models  # noqa: F401

logging.basicConfig(
    level=logging.DEBUG if settings.DEBUG else logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Cria as tabelas no banco ao iniciar a aplicação."""
    logger.info("Iniciando aplicação — criando tabelas...")
    Base.metadata.create_all(bind=engine)
    logger.info("Tabelas criadas com sucesso.")
    yield
    logger.info("Encerrando aplicação.")


# ─── App ─────────────────────────────────────────────────────────────────────
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description=(
        "API de Consultoria com IA — gerencia conversas, modelos de linguagem, "
        "gerenciação de sessões, análise de feedback e orquestração de IA."
    ),
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# ─── Middlewares ──────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],        # ajuste para domínios específicos em produção
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Exception Handlers ───────────────────────────────────────────────────────
register_exception_handlers(app)

# ─── Rotas ───────────────────────────────────────────────────────────────────
app.include_router(api_router)


@app.get("/health", tags=["Health"])
def health_check():
    """
    Health check básico.
    **Retorna:** status da aplicação
    **Códigos:** 200
    """
    return {"status": "ok", "version": settings.APP_VERSION}

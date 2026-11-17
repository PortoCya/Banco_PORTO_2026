"""
Ponto de entrada da API (FastAPI).

O schema do banco é responsabilidade do Alembic (`alembic upgrade head`):
a aplicação não cria nem altera tabelas ao subir.
"""
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.api.v1.router import api_router
from app.core.config import settings
from app.core.database import engine
from app.core.errors import register_exception_handlers
from app.core.logs import configurar_logs
from app.core.middleware import RequisicaoMiddleware

configurar_logs(settings.DEBUG)
logger = logging.getLogger("nps.api")

app = FastAPI(
    title="NPS KeyCore — API",
    version=settings.APP_VERSION,
    description="Pesquisas de satisfação/NPS: coleta pública, NPS determinístico, auditoria e análise sugerida por IA.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Request-ID", "X-Correlation-ID"],
    expose_headers=["X-Request-ID", "Retry-After", "Content-Disposition"],
)
# Adicionado por último = mais externo: toda requisição (inclusive preflight e
# erros) passa por ele e ganha request id, log de acesso e limite de payload.
app.add_middleware(RequisicaoMiddleware)

register_exception_handlers(app)
app.include_router(api_router)


@app.get("/health/live", tags=["Health"], summary="Liveness: o processo está de pé")
def health_live():
    return {"status": "ok"}


@app.get("/health", tags=["Health"], summary="Readiness: confere o banco de dados")
def health():
    """
    Executa uma consulta real no banco. Responde 503 se o banco não responder —
    é este endpoint que o balanceador/orquestrador deve consultar.
    O Redis é opcional para o núcleo e por isso não derruba o health check.
    """
    try:
        with engine.connect() as conexao:
            conexao.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        logger.error("Health check: banco indisponível (%s)", type(exc).__name__)
        return JSONResponse(status_code=503, content={"status": "indisponivel", "banco": "erro"})
    return {"status": "ok", "banco": "ok", "versao": settings.APP_VERSION}

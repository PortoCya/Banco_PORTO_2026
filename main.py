"""
Ponto de entrada da aplicação FastAPI — NPS KeyCore v1.0.
Inclui Middlewares de Segurança (Headers HTTP, Limite de Payload, CORS restritivo)
e Observabilidade estruturada (Correlation ID, rota, status, duração).
"""
import logging
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.core.database import Base, engine
from app.core.errors import register_exception_handlers
from app.api.v1.router import api_router

import app.models.models  # noqa: F401 — registra as 16 entidades no metadata

logging.basicConfig(
    level=logging.DEBUG if settings.DEBUG else logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("nps_keycore")

MAX_PAYLOAD_BYTES = 64 * 1024  # 64 KB — limite seguro de payload contra abuso/DoS


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Iniciando NPS KeyCore v1.0 — verificando schema de 16 tabelas...")
    Base.metadata.create_all(bind=engine)
    logger.info("Schema validado com sucesso.")
    yield
    logger.info("Encerrando NPS KeyCore v1.0.")


app = FastAPI(
    title="NPS KeyCore v1.0 — API",
    version=settings.APP_VERSION,
    description=(
        "Plataforma corporativa NPS KeyCore v1.0 para criação de pesquisas, coleta mobile-first, "
        "cálculo determinístico de NPS, auditoria LGPD e análise qualitativa assíncrona por IA (Google Gemini)."
    ),
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# ─── CORS Restritivo (PRD Pág. 8 e 9) ────────────────────────────────────────
ALLOWED_ORIGINS = [
    "https://nps.keycore.com.br",
    "https://apinps.keycore.com.br",
    "http://localhost:3000",
    "http://localhost:8000",
    "http://127.0.0.1:8000",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Correlation-ID", "X-Idempotency-Key"],
)


# ─── Middleware de Segurança, Limite de Payload e Observabilidade ────────────
@app.middleware("http")
async def security_and_observability_middleware(request: Request, call_next):
    correlation_id = request.headers.get("X-Correlation-ID") or str(uuid.uuid4())
    request.state.correlation_id = correlation_id

    # Limite de tamanho de payload (PRD Pág. 9)
    content_length = request.headers.get("content-length")
    if content_length and int(content_length) > MAX_PAYLOAD_BYTES:
        return JSONResponse(
            status_code=413,
            content={
                "error": {
                    "code": "PAYLOAD_TOO_LARGE",
                    "message": f"Payload excede o limite máximo permitido de {MAX_PAYLOAD_BYTES} bytes.",
                    "correlation_id": correlation_id,
                }
            },
        )

    inicio = time.perf_counter()
    response = await call_next(request)
    duracao_ms = round((time.perf_counter() - inicio) * 1000, 2)

    # Headers de Segurança (PRD Pág. 9: CSP, HSTS, nosniff, Frame-Options)
    response.headers["X-Correlation-ID"] = correlation_id
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    if not request.url.path.startswith(("/docs", "/redoc", "/openapi.json")):
        response.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'"
        response.headers["Cache-Control"] = "no-store"

    logger.info(
        "correlation_id=%s rota=%s metodo=%s status=%d duracao_ms=%.2f",
        correlation_id,
        request.url.path,
        request.method,
        response.status_code,
        duracao_ms,
    )
    return response


register_exception_handlers(app)
app.include_router(api_router)


@app.get("/health", tags=["Health"])
def health_check():
    return {
        "status": "ok",
        "service": "NPS KeyCore v1.0",
        "version": settings.APP_VERSION,
        "ai_provider": settings.AI_PROVIDER,
    }

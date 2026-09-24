"""
Tratamento centralizado de erros da aplicação.
Cobre: dados inválidos, banco indisponível, API externa, timeout,
resposta inesperada e erros da IA.
"""
import logging
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from sqlalchemy.exc import OperationalError, IntegrityError, TimeoutError as SATimeout
import httpx

logger = logging.getLogger(__name__)


# ─── Exceções customizadas ────────────────────────────────────────────────────

class AppError(Exception):
    """Base para todos os erros da aplicação."""
    status_code: int = 500
    error_code: str = "INTERNAL_ERROR"

    def __init__(self, detail: str, **extra: Any):
        self.detail = detail
        self.extra = extra
        super().__init__(detail)


class ValidationError(AppError):
    status_code = 422
    error_code = "VALIDATION_ERROR"


class NotFoundError(AppError):
    status_code = 404
    error_code = "NOT_FOUND"


class ConflictError(AppError):
    status_code = 409
    error_code = "CONFLICT"


class DatabaseUnavailableError(AppError):
    status_code = 503
    error_code = "DATABASE_UNAVAILABLE"


class ExternalAPIError(AppError):
    status_code = 502
    error_code = "EXTERNAL_API_ERROR"


class TimeoutError(AppError):
    status_code = 504
    error_code = "TIMEOUT"


class UnexpectedResponseError(AppError):
    status_code = 502
    error_code = "UNEXPECTED_RESPONSE"


class AIError(AppError):
    status_code = 502
    error_code = "AI_ERROR"


class AIQuotaExceededError(AIError):
    error_code = "AI_QUOTA_EXCEEDED"


class AIContentFilterError(AIError):
    status_code = 422
    error_code = "AI_CONTENT_FILTER"


# ─── Formatador de resposta de erro ──────────────────────────────────────────

def _error_response(status_code: int, error_code: str, detail: str, **extra) -> JSONResponse:
    body = {"error": {"code": error_code, "message": detail}}
    if extra:
        body["error"]["details"] = extra
    return JSONResponse(status_code=status_code, content=body)


# ─── Registro de handlers no FastAPI ─────────────────────────────────────────

def register_exception_handlers(app: FastAPI) -> None:

    # 1. Dados inválidos (Pydantic / FastAPI)
    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        logger.warning("Dados inválidos na requisição %s: %s", request.url, exc.errors())
        return _error_response(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "VALIDATION_ERROR",
            "Dados de entrada inválidos.",
            fields=exc.errors(),
        )

    # 2. Erros customizados da aplicação
    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError):
        logger.error("[%s] %s", exc.error_code, exc.detail, extra=exc.extra)
        return _error_response(exc.status_code, exc.error_code, exc.detail, **exc.extra)

    # 3. Banco indisponível (SQLAlchemy OperationalError)
    @app.exception_handler(OperationalError)
    async def db_operational_handler(request: Request, exc: OperationalError):
        logger.critical("Banco de dados indisponível: %s", exc, exc_info=True)
        return _error_response(503, "DATABASE_UNAVAILABLE", "Banco de dados temporariamente indisponível.")

    # 4. Violação de integridade (FK, UNIQUE)
    @app.exception_handler(IntegrityError)
    async def db_integrity_handler(request: Request, exc: IntegrityError):
        logger.error("Violação de integridade no banco: %s", exc)
        return _error_response(409, "CONFLICT", "Conflito de dados: registro duplicado ou referência inválida.")

    # 5. Timeout de banco
    @app.exception_handler(SATimeout)
    async def db_timeout_handler(request: Request, exc: SATimeout):
        logger.error("Timeout no banco de dados: %s", exc)
        return _error_response(504, "DATABASE_TIMEOUT", "A consulta ao banco excedeu o tempo limite.")

    # 6. API externa / IA — timeout de rede
    @app.exception_handler(httpx.TimeoutException)
    async def http_timeout_handler(request: Request, exc: httpx.TimeoutException):
        logger.error("Timeout na API externa: %s", exc)
        return _error_response(504, "TIMEOUT", "A requisição para a API externa excedeu o tempo limite.")

    # 7. Erro de conexão com API externa
    @app.exception_handler(httpx.ConnectError)
    async def http_connect_handler(request: Request, exc: httpx.ConnectError):
        logger.error("API externa indisponível: %s", exc)
        return _error_response(502, "EXTERNAL_API_ERROR", "API externa indisponível.")

    # 8. Erros não tratados → 500
    @app.exception_handler(Exception)
    async def generic_handler(request: Request, exc: Exception):
        logger.critical("Erro inesperado: %s", exc, exc_info=True)
        return _error_response(500, "INTERNAL_ERROR", "Erro interno do servidor.")

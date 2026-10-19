"""
Tratamento centralizado de erros da aplicação (NPS KeyCore v1.0).
Cobre: dados inválidos, autenticação/RBAC, rate limit, banco indisponível,
API externa, timeout, resposta inesperada e erros da IA, sem vazar stack traces ou PII.
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


class BusinessRuleError(AppError):
    status_code = 400
    error_code = "BUSINESS_RULE_VIOLATION"


class UnauthorizedError(AppError):
    status_code = 401
    error_code = "UNAUTHORIZED"


class ForbiddenError(AppError):
    status_code = 403
    error_code = "FORBIDDEN"


class NotFoundError(AppError):
    status_code = 404
    error_code = "NOT_FOUND"


class ConflictError(AppError):
    status_code = 409
    error_code = "CONFLICT"


class ValidationError(AppError):
    status_code = 422
    error_code = "VALIDATION_ERROR"


class RateLimitExceededError(AppError):
    status_code = 429
    error_code = "RATE_LIMIT_EXCEEDED"


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


# ─── Formatador seguro de resposta de erro ───────────────────────────────────

def _error_response(status_code: int, error_code: str, detail: str, request: Request = None, **extra) -> JSONResponse:
    correlation_id = getattr(request.state, "correlation_id", None) if request else None
    body: dict[str, Any] = {
        "error": {
            "code": error_code,
            "message": detail,
        }
    }
    if correlation_id:
        body["error"]["correlation_id"] = correlation_id
    if extra:
        body["error"]["details"] = extra
    return JSONResponse(status_code=status_code, content=body)


# ─── Registro de handlers no FastAPI ─────────────────────────────────────────

def register_exception_handlers(app: FastAPI) -> None:

    # 1. Dados inválidos (Pydantic / FastAPI) — sanitizado para não vazar objetos internos
    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        safe_fields = [
            {
                "loc": [str(x) for x in err.get("loc", [])],
                "msg": err.get("msg", "Valor inválido"),
                "type": err.get("type", "value_error"),
            }
            for err in exc.errors()
        ]
        logger.warning("Dados inválidos na requisição %s: %s", request.url.path, safe_fields)
        return _error_response(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "VALIDATION_ERROR",
            "Dados de entrada inválidos ou campos não permitidos.",
            request=request,
            fields=safe_fields,
        )

    # 2. Erros customizados da aplicação
    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError):
        logger.warning("[%s] %s (rota=%s)", exc.error_code, exc.detail, request.url.path)
        return _error_response(exc.status_code, exc.error_code, exc.detail, request=request, **exc.extra)

    # 3. Banco indisponível (SQLAlchemy OperationalError) — nunca vaza SQL bruto
    @app.exception_handler(OperationalError)
    async def db_operational_handler(request: Request, exc: OperationalError):
        logger.critical("Banco de dados indisponível na rota %s", request.url.path, exc_info=True)
        return _error_response(
            503,
            "DATABASE_UNAVAILABLE",
            "Banco de dados temporariamente indisponível.",
            request=request,
        )

    # 4. Violação de integridade (FK, UNIQUE, CHECK) — nunca vaza estrutura interna da tabela
    @app.exception_handler(IntegrityError)
    async def db_integrity_handler(request: Request, exc: IntegrityError):
        logger.error("Violação de integridade no banco na rota %s", request.url.path)
        return _error_response(
            409,
            "CONFLICT",
            "Conflito de integridade: registro duplicado, referência inválida ou violação de regra do banco.",
            request=request,
        )

    # 5. Timeout de banco
    @app.exception_handler(SATimeout)
    async def db_timeout_handler(request: Request, exc: SATimeout):
        logger.error("Timeout no banco de dados na rota %s", request.url.path)
        return _error_response(
            504,
            "DATABASE_TIMEOUT",
            "A consulta ao banco excedeu o tempo limite.",
            request=request,
        )

    # 6. API externa / IA — timeout de rede
    @app.exception_handler(httpx.TimeoutException)
    async def http_timeout_handler(request: Request, exc: httpx.TimeoutException):
        logger.error("Timeout na API externa na rota %s", request.url.path)
        return _error_response(
            504,
            "TIMEOUT",
            "A requisição para a API externa excedeu o tempo limite.",
            request=request,
        )

    # 7. Erro de conexão com API externa
    @app.exception_handler(httpx.ConnectError)
    async def http_connect_handler(request: Request, exc: httpx.ConnectError):
        logger.error("API externa indisponível na rota %s", request.url.path)
        return _error_response(
            502,
            "EXTERNAL_API_ERROR",
            "API externa indisponível.",
            request=request,
        )

    # 8. Erros não tratados → 500 (mensagem genérica segura sem stack trace)
    @app.exception_handler(Exception)
    async def generic_handler(request: Request, exc: Exception):
        logger.critical("Erro inesperado na rota %s: %s", request.url.path, type(exc).__name__, exc_info=True)
        return _error_response(
            500,
            "INTERNAL_ERROR",
            "Erro interno do servidor.",
            request=request,
        )

"""
Tratamento centralizado de erros.

Toda resposta de erro tem o mesmo formato e carrega o id da requisição:
    {"error": {"code": "...", "message": "...", "correlation_id": "..."}}

Nada de stack trace, SQL ou dado de entrada na resposta ou no log.
"""
import logging
from typing import Any, Optional

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import DBAPIError, IntegrityError, OperationalError
from sqlalchemy.exc import TimeoutError as PoolTimeoutError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.logs import caminho_para_log, request_id_atual

logger = logging.getLogger(__name__)


# ─── Exceções da aplicação ───────────────────────────────────────────────────

class AppError(Exception):
    """Base para todos os erros da aplicação."""
    status_code: int = 500
    error_code: str = "INTERNAL_ERROR"

    def __init__(self, detail: str, *, retry_after: Optional[int] = None, **extra: Any):
        self.detail = detail
        self.retry_after = retry_after
        self.extra = extra
        super().__init__(detail)


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


class InvalidInputError(AppError):
    """Entrada inválida que o Pydantic não tem como pegar (ex.: período invertido)."""
    status_code = 422
    error_code = "VALIDATION_ERROR"


class TooManyRequestsError(AppError):
    status_code = 429
    error_code = "TOO_MANY_REQUESTS"


class ServiceUnavailableError(AppError):
    status_code = 503
    error_code = "SERVICE_UNAVAILABLE"


# ─── Formato único de resposta ───────────────────────────────────────────────

def resposta_erro(
    status_code: int,
    error_code: str,
    detail: str,
    *,
    retry_after: Optional[int] = None,
    **extra: Any,
) -> JSONResponse:
    request_id = request_id_atual()
    corpo: dict[str, Any] = {
        "error": {"code": error_code, "message": detail, "correlation_id": request_id}
    }
    if extra:
        corpo["error"]["details"] = extra
    headers = {"X-Request-ID": request_id, "X-Correlation-ID": request_id}
    if retry_after is not None:
        headers["Retry-After"] = str(retry_after)
    if status_code == 401:
        headers["WWW-Authenticate"] = "Bearer"
    return JSONResponse(status_code=status_code, content=corpo, headers=headers)


# ─── Handlers ────────────────────────────────────────────────────────────────

def register_exception_handlers(app: FastAPI) -> None:

    @app.exception_handler(RequestValidationError)
    async def _validacao(request: Request, exc: RequestValidationError):
        # Só loc/msg/type: o "input" (que pode ser uma senha) nunca sai daqui
        campos = [
            {
                "loc": [str(x) for x in err.get("loc", [])],
                "msg": err.get("msg", "Valor inválido"),
                "type": err.get("type", "value_error"),
            }
            for err in exc.errors()
        ]
        logger.info("Entrada inválida em %s: %s", caminho_para_log(request.url.path),
                    [(c["loc"], c["type"]) for c in campos])
        return resposta_erro(422, "VALIDATION_ERROR", "Dados de entrada inválidos.", fields=campos)

    @app.exception_handler(AppError)
    async def _app_error(request: Request, exc: AppError):
        logger.info("[%s] %s (rota=%s)", exc.error_code, exc.detail, caminho_para_log(request.url.path))
        return resposta_erro(exc.status_code, exc.error_code, exc.detail,
                             retry_after=exc.retry_after, **exc.extra)

    @app.exception_handler(StarletteHTTPException)
    async def _http(request: Request, exc: StarletteHTTPException):
        codigos = {404: "NOT_FOUND", 405: "METHOD_NOT_ALLOWED"}
        return resposta_erro(exc.status_code, codigos.get(exc.status_code, "HTTP_ERROR"), str(exc.detail))

    # Pool esgotado = servidor saturado. Pede para o cliente voltar depois em
    # vez de estourar um 500 ou deixar a fila crescer.
    @app.exception_handler(PoolTimeoutError)
    async def _saturado(request: Request, exc: PoolTimeoutError):
        logger.error("Pool de conexões esgotado (rota=%s)", caminho_para_log(request.url.path))
        return resposta_erro(429, "SERVER_BUSY", "Servidor ocupado. Tente novamente em instantes.",
                             retry_after=5)

    @app.exception_handler(IntegrityError)
    async def _integridade(request: Request, exc: IntegrityError):
        logger.warning("Violação de integridade (rota=%s, tipo=%s)",
                       caminho_para_log(request.url.path), type(exc.orig).__name__)
        return resposta_erro(409, "CONFLICT", "Conflito com um registro existente.")

    # Banco fora do ar, comando cancelado por statement_timeout/lock_timeout...
    @app.exception_handler(OperationalError)
    async def _banco_indisponivel(request: Request, exc: OperationalError):
        logger.error("Banco indisponível ou lento (rota=%s, tipo=%s)",
                     caminho_para_log(request.url.path), type(exc.orig).__name__)
        return resposta_erro(503, "DATABASE_UNAVAILABLE",
                             "Banco de dados temporariamente indisponível.", retry_after=5)

    @app.exception_handler(DBAPIError)
    async def _banco(request: Request, exc: DBAPIError):
        logger.error("Erro de banco (rota=%s, tipo=%s)", caminho_para_log(request.url.path), type(exc.orig).__name__)
        return resposta_erro(500, "INTERNAL_ERROR", "Erro interno do servidor.")

    @app.exception_handler(Exception)
    async def _generico(request: Request, exc: Exception):
        logger.critical("Erro inesperado (rota=%s)", caminho_para_log(request.url.path), exc_info=True)
        return resposta_erro(500, "INTERNAL_ERROR", "Erro interno do servidor.")

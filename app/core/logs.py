"""
Logs com request id.

O id da requisição fica em um ContextVar; um filtro o injeta em TODA linha de
log (não só no log de acesso), então dá para seguir uma requisição de ponta a
ponta com um grep. O worker usa o mesmo mecanismo com o id do job.
"""
import logging
import re
import uuid
from contextvars import ContextVar

_request_id: ContextVar[str] = ContextVar("request_id", default="-")

# O id vindo do cliente é texto não confiável: só aceitamos um formato
# restrito, para ninguém injetar quebras de linha ou lixo nos logs.
_FORMATO_ID = re.compile(r"^[A-Za-z0-9._-]{8,64}$")


_TOKEN_PUBLICO = re.compile(r"(/public/respostas/)[^/?]+")


def caminho_para_log(caminho: str) -> str:
    """O token do link público é uma credencial de uso único: fora dos logs."""
    return _TOKEN_PUBLICO.sub(r"\1***", caminho)


def novo_request_id(recebido: str | None = None) -> str:
    if recebido and _FORMATO_ID.fullmatch(recebido):
        return recebido
    return uuid.uuid4().hex


def definir_request_id(valor: str):
    return _request_id.set(valor)


def restaurar_request_id(token) -> None:
    _request_id.reset(token)


def request_id_atual() -> str:
    return _request_id.get()


class _FiltroRequestId(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = _request_id.get()
        return True


class _HandlerDaApp(logging.StreamHandler):
    """Marca o handler da aplicação para configurar_logs ser idempotente."""


def configurar_logs(debug: bool = False) -> None:
    raiz = logging.getLogger()
    if not any(isinstance(h, _HandlerDaApp) for h in raiz.handlers):
        handler = _HandlerDaApp()
        handler.addFilter(_FiltroRequestId())
        handler.setFormatter(logging.Formatter(
            "%(asctime)s | %(levelname)s | request_id=%(request_id)s | %(name)s | %(message)s"
        ))
        raiz.addHandler(handler)
    raiz.setLevel(logging.DEBUG if debug else logging.INFO)
    # Cliente HTTP em DEBUG loga URLs e cabeçalhos; fica sempre em WARNING
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)

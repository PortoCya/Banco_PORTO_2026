"""
Middleware HTTP (ASGI puro): request id, log de acesso, limite de payload e
cabeçalhos de segurança.
"""
import logging
import time

from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.config import settings
from app.core.errors import resposta_erro
from app.core.logs import caminho_para_log, definir_request_id, novo_request_id

logger = logging.getLogger("nps.acesso")

_ROTAS_DOCS = ("/docs", "/redoc", "/openapi.json")


class _PayloadGrandeDemais(Exception):
    pass


class RequisicaoMiddleware:
    def __init__(self, app: ASGIApp, max_payload_bytes: int | None = None):
        self.app = app
        self.max_payload_bytes = max_payload_bytes or settings.MAX_PAYLOAD_BYTES

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = Headers(scope=scope)
        request_id = novo_request_id(headers.get("x-request-id") or headers.get("x-correlation-id"))
        # Não é restaurado ao final de propósito: o handler de erro 500 roda
        # depois deste middleware e ainda precisa do id.
        definir_request_id(request_id)

        caminho = scope["path"]
        caminho_log = caminho_para_log(caminho)
        inicio = time.perf_counter()
        status = 500
        resposta_iniciada = False

        async def enviar(message: Message) -> None:
            nonlocal status, resposta_iniciada
            if estourou and not resposta_iniciada:
                return   # descarta a resposta da app; quem responde é o 413 abaixo
            if message["type"] == "http.response.start":
                resposta_iniciada = True
                status = message["status"]
                h = MutableHeaders(scope=message)
                h["X-Request-ID"] = request_id
                h["X-Correlation-ID"] = request_id
                h["X-Content-Type-Options"] = "nosniff"
                h["X-Frame-Options"] = "DENY"
                h["Referrer-Policy"] = "strict-origin-when-cross-origin"
                h["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
                if not caminho.startswith(_ROTAS_DOCS):
                    h["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'"
                    h["Cache-Control"] = "no-store"
            await send(message)

        # Limite de payload: confere o Content-Length declarado e também conta
        # os bytes que chegam de fato (corpo "chunked" não declara tamanho).
        recebidos = 0
        estourou = False

        async def receber() -> Message:
            nonlocal recebidos, estourou
            message = await receive()
            if message["type"] == "http.request":
                recebidos += len(message.get("body", b""))
                if recebidos > self.max_payload_bytes:
                    estourou = True
                    raise _PayloadGrandeDemais()
            return message

        try:
            declarado = headers.get("content-length")
            if declarado is not None and (not declarado.isdigit() or int(declarado) > self.max_payload_bytes):
                estourou = True
            else:
                try:
                    await self.app(scope, receber, enviar)
                except _PayloadGrandeDemais:
                    pass
            if estourou and not resposta_iniciada:
                estourou = False   # libera o envio do 413
                resposta = resposta_erro(
                    413, "PAYLOAD_TOO_LARGE",
                    f"Payload inválido ou acima do limite de {self.max_payload_bytes} bytes.",
                )
                await resposta(scope, receive, enviar)
        finally:
            # Só o caminho (sem query string, que pode carregar dados)
            logger.info(
                "metodo=%s rota=%s status=%d duracao_ms=%.1f",
                scope["method"], caminho_log, status, (time.perf_counter() - inicio) * 1000,
            )

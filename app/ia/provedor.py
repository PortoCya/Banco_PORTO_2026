"""
Adaptador único do provedor de IA.

Fala o protocolo de "chat completions" (OpenAI, Gemini e compatíveis). Trocar
de provedor = trocar IA_BASE_URL/IA_API_KEY; o resto do worker não muda.

- Toda chamada tem timeout explícito (conexão e resposta).
- O adaptador NÃO repete chamadas. Ele só classifica a falha; quem decide
  repetir (com backoff) é o worker, e só para ErroTransitorio.
"""
from dataclasses import dataclass
from typing import Optional, Protocol

import httpx

from app.core.config import settings


class ErroProvedor(Exception):
    """A mensagem nunca carrega o corpo da requisição nem da resposta."""


class ErroTransitorio(ErroProvedor):
    """Vale tentar de novo: timeout, rede, 408/425/429, 5xx."""


class ErroPermanente(ErroProvedor):
    """Repetir não resolve: 400/401/403/404, resposta em formato inesperado."""


@dataclass(frozen=True)
class RespostaProvedor:
    texto: str
    tokens_entrada: int
    tokens_saida: int


class ProvedorIA(Protocol):
    def completar(self, *, modelo: str, sistema: str, usuario: str) -> RespostaProvedor: ...


_STATUS_TRANSITORIOS = {408, 425, 429}


class ProvedorHTTP:
    def __init__(self, base_url: str, api_key: str, transport: Optional[httpx.BaseTransport] = None):
        self._cliente = httpx.Client(
            base_url=base_url.rstrip("/"),
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=httpx.Timeout(
                settings.IA_TIMEOUT_RESPOSTA_SEGUNDOS,
                connect=settings.IA_TIMEOUT_CONEXAO_SEGUNDOS,
            ),
            transport=transport,
        )

    def completar(self, *, modelo: str, sistema: str, usuario: str) -> RespostaProvedor:
        try:
            resposta = self._cliente.post("/chat/completions", json={
                "model": modelo,
                "messages": [
                    {"role": "system", "content": sistema},
                    {"role": "user", "content": usuario},
                ],
                "temperature": 0,
                "max_tokens": settings.IA_MAX_TOKENS_RESPOSTA,
                "response_format": {"type": "json_object"},
            })
        except httpx.TimeoutException as exc:
            raise ErroTransitorio("timeout do provedor") from exc
        except httpx.TransportError as exc:
            raise ErroTransitorio(f"falha de rede ({type(exc).__name__})") from exc

        codigo = resposta.status_code
        if codigo in _STATUS_TRANSITORIOS or codigo >= 500:
            raise ErroTransitorio(f"provedor respondeu HTTP {codigo}")
        if codigo >= 400:
            raise ErroPermanente(f"provedor respondeu HTTP {codigo}")

        try:
            corpo = resposta.json()
            texto = corpo["choices"][0]["message"]["content"]
            uso = corpo.get("usage") or {}
            if not isinstance(texto, str):
                raise TypeError
            return RespostaProvedor(
                texto=texto,
                tokens_entrada=int(uso.get("prompt_tokens") or 0),
                tokens_saida=int(uso.get("completion_tokens") or 0),
            )
        except (ValueError, KeyError, IndexError, TypeError, AttributeError) as exc:
            raise ErroPermanente("resposta do provedor em formato inesperado") from exc

    def fechar(self) -> None:
        self._cliente.close()

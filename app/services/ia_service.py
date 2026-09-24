"""
Serviço de IA — integração com OpenAI com retry, timeout e tratamento de erros.
"""
import asyncio
import logging
from typing import Optional

import httpx
from openai import AsyncOpenAI, RateLimitError, APITimeoutError, APIConnectionError

from app.core.config import settings
from app.core.errors import AIError, AIQuotaExceededError, AIContentFilterError, TimeoutError, ExternalAPIError

logger = logging.getLogger(__name__)

_client: Optional[AsyncOpenAI] = None


def get_openai_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(
            api_key=settings.OPENAI_API_KEY,
            timeout=settings.OPENAI_TIMEOUT_SECONDS,
            max_retries=settings.OPENAI_MAX_RETRIES,
        )
    return _client


async def gerar_resposta_ia(
    prompt_sistema: str,
    mensagem_usuario: str,
    modelo: str = None,
    max_tokens: int = None,
    temperatura: float = 0.7,
) -> dict:
    """
    Envia prompt para a IA e retorna dicionário com:
      - content: texto da resposta
      - tokens_entrada: int
      - tokens_saida: int
      - modelo_utilizado: str
      - finish_reason: str

    Erros tratados:
      - RateLimitError          → AIQuotaExceededError
      - APITimeoutError         → TimeoutError
      - APIConnectionError      → ExternalAPIError
      - Resposta vazia/inesper. → AIError
      - Content filter          → AIContentFilterError
    """
    modelo = modelo or settings.OPENAI_MODEL
    max_tokens = max_tokens or settings.MAX_TOKENS_RESPONSE
    client = get_openai_client()

    logger.info("Chamando IA: modelo=%s, max_tokens=%d", modelo, max_tokens)

    try:
        resposta = await client.chat.completions.create(
            model=modelo,
            messages=[
                {"role": "system", "content": prompt_sistema},
                {"role": "user", "content": mensagem_usuario},
            ],
            max_tokens=max_tokens,
            temperature=temperatura,
        )
    except RateLimitError as exc:
        logger.error("Quota da IA excedida: %s", exc)
        raise AIQuotaExceededError("Limite de uso da IA atingido. Tente novamente mais tarde.")
    except APITimeoutError as exc:
        logger.error("Timeout na chamada à IA: %s", exc)
        raise TimeoutError("A IA não respondeu dentro do tempo limite.")
    except APIConnectionError as exc:
        logger.error("Erro de conexão com a IA: %s", exc)
        raise ExternalAPIError("Não foi possível conectar à API de IA.")
    except Exception as exc:
        logger.error("Erro inesperado na IA: %s", exc, exc_info=True)
        raise AIError(f"Erro inesperado ao processar com IA: {str(exc)}")

    # Valida a resposta
    escolha = resposta.choices[0] if resposta.choices else None
    if escolha is None:
        raise AIError("A IA retornou uma resposta vazia inesperada.")

    if escolha.finish_reason == "content_filter":
        raise AIContentFilterError("Conteúdo bloqueado pelos filtros de segurança da IA.")

    conteudo = getattr(escolha.message, "content", None)
    if not conteudo:
        raise AIError("A IA retornou conteúdo nulo.")

    return {
        "content": conteudo,
        "tokens_entrada": resposta.usage.prompt_tokens if resposta.usage else 0,
        "tokens_saida": resposta.usage.completion_tokens if resposta.usage else 0,
        "modelo_utilizado": resposta.model,
        "finish_reason": escolha.finish_reason,
    }


async def analisar_sentimento(texto: str) -> dict:
    """Analisa sentimento de um texto. Retorna: sentimento, confianca, tema, justificativa."""
    prompt = (
        "Você é um analisador de sentimentos. Dado o texto do usuário, retorne um JSON com:\n"
        '{"sentimento": "POSITIVO|NEUTRO|NEGATIVO", "confianca": 0.0-1.0, '
        '"tema": "string", "justificativa": "string", "sugestoes_acao": ["..."]}\n'
        "Responda APENAS com o JSON, sem formatação extra."
    )
    resultado = await gerar_resposta_ia(prompt, texto, temperatura=0.2)
    import json
    try:
        return json.loads(resultado["content"])
    except (json.JSONDecodeError, KeyError) as exc:
        raise AIError(f"Resposta da IA com formato inesperado: {exc}")

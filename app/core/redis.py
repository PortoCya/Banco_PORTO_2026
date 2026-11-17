"""
Cliente Redis compartilhado (opcional). Toda chamada tem timeout explícito.
"""
from functools import lru_cache
from typing import Optional

import redis

from app.core.config import settings


@lru_cache(maxsize=1)
def get_redis() -> Optional[redis.Redis]:
    """Retorna o cliente (com pool próprio) ou None se REDIS_URL não foi definido."""
    if not settings.REDIS_URL:
        return None
    return redis.Redis.from_url(
        settings.REDIS_URL,
        decode_responses=True,
        socket_connect_timeout=settings.REDIS_TIMEOUT_SEGUNDOS,
        socket_timeout=settings.REDIS_TIMEOUT_SEGUNDOS,
        health_check_interval=30,
    )

"""
Orçamento da camada de IA (contador de custo no Redis + circuit breaker).

- O custo acumulado é contado por mês (UTC).
- Quando o acumulado atinge o limite, o worker abre um EVENTO_CIRCUIT_BREAKER.
  Enquanto existir evento com resolvido_em nulo, nada é enviado ao provedor.
- O ADMIN resolve subindo o limite (PUT /ia/limite-custo).

Sem Redis não há como contar custo: as funções levantam CustoIndisponivel e
cada chamador decide (o worker adia o envio; a API responde 503 só nessa rota).
"""
from typing import Optional

import redis
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.redis import get_redis
from app.models.models import EventoCircuitBreaker, agora_utc

_CHAVE_LIMITE = "ia:limite_custo"


class CustoIndisponivel(Exception):
    pass


def _redis() -> redis.Redis:
    r = get_redis()
    if r is None:
        raise CustoIndisponivel("REDIS_URL não configurado")
    return r


def _chave_mes() -> str:
    return f"ia:custo:{agora_utc():%Y-%m}"


def _chamar(funcao):
    try:
        return funcao(_redis())
    except redis.RedisError as exc:
        raise CustoIndisponivel(type(exc).__name__) from exc


def obter_limite() -> float:
    valor = _chamar(lambda r: r.get(_CHAVE_LIMITE))
    return float(valor) if valor is not None else settings.IA_LIMITE_CUSTO_PADRAO


def definir_limite(limite: float) -> None:
    _chamar(lambda r: r.set(_CHAVE_LIMITE, repr(float(limite))))


def custo_acumulado() -> float:
    valor = _chamar(lambda r: r.get(_chave_mes()))
    return float(valor) if valor is not None else 0.0


def somar_custo(tokens_entrada: int, tokens_saida: int) -> float:
    custo = (
        tokens_entrada / 1000 * settings.IA_CUSTO_1K_TOKENS_ENTRADA
        + tokens_saida / 1000 * settings.IA_CUSTO_1K_TOKENS_SAIDA
    )
    def _somar(r: redis.Redis) -> float:
        pipe = r.pipeline()
        pipe.incrbyfloat(_chave_mes(), custo)
        pipe.expire(_chave_mes(), 100 * 24 * 3600)
        return float(pipe.execute()[0])
    return _chamar(_somar)


def evento_aberto(db: Session) -> Optional[EventoCircuitBreaker]:
    return db.execute(
        select(EventoCircuitBreaker)
        .where(EventoCircuitBreaker.resolvido_em.is_(None))
        .order_by(EventoCircuitBreaker.disparado_em.desc())
        .limit(1)
    ).scalar_one_or_none()

"""
Fila da camada de IA (Redis Streams).

Pela fila só trafega o id da submissão — nunca o texto do comentário.

Publicar é "melhor esforço": a fonte da verdade é a linha em JOB_IA, gravada
na mesma transação da resposta. Se o Redis estiver fora, o job continua
NA_FILA no banco e o worker o encontra na varredura periódica. Nenhuma falha
daqui chega ao respondente.
"""
import logging
import uuid

import redis

from app.core.redis import get_redis

logger = logging.getLogger(__name__)

STREAM_ANALISES = "ia:analises"
STREAM_AVALIACOES = "ia:avaliacoes"
GRUPO_WORKERS = "workers-ia"
_TAMANHO_MAXIMO = 100_000


def publicar_analise(id_submissao: uuid.UUID) -> bool:
    return _publicar(STREAM_ANALISES, {"id_submissao": str(id_submissao)})


def publicar_avaliacao(id_versao_modelo: uuid.UUID) -> bool:
    return _publicar(STREAM_AVALIACOES, {"id_versao_modelo": str(id_versao_modelo)})


def _publicar(stream: str, campos: dict[str, str]) -> bool:
    r = get_redis()
    if r is None:
        return False
    try:
        r.xadd(stream, campos, maxlen=_TAMANHO_MAXIMO, approximate=True)
        return True
    except redis.RedisError as exc:
        logger.warning("Não foi possível publicar em %s (%s); o worker pega pela varredura",
                       stream, type(exc).__name__)
        return False

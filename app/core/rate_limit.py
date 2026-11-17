"""
Rate limit com janela deslizante.

Com REDIS_URL definido o contador é compartilhado entre todos os processos da
API. Sem Redis — ou se ele cair — vale o contador em memória deste processo:
o limite fica menos preciso, mas nunca deixa de existir nem derruba a rota.
"""
import hashlib
import logging
import time
import uuid
from collections import deque
from threading import Lock

import redis

from app.core.redis import get_redis

logger = logging.getLogger(__name__)

# Teto de chaves em memória: sem isso, um atacante variando a chave (e-mails
# aleatórios no login) faria o processo crescer sem limite.
_MAX_CHAVES_MEMORIA = 50_000


class RateLimiter:
    def __init__(self, nome: str, limite: int, janela_segundos: int):
        self.nome = nome
        self.limite = limite
        self.janela = janela_segundos
        self._eventos: dict[str, deque[float]] = {}
        self._lock = Lock()

    # ── Interface ────────────────────────────────────────────────────────────

    def bloqueado(self, chave: str) -> bool:
        r = get_redis()
        if r is not None:
            try:
                agora = time.time()
                pipe = r.pipeline()
                pipe.zremrangebyscore(self._chave(chave), 0, agora - self.janela)
                pipe.zcard(self._chave(chave))
                return pipe.execute()[1] >= self.limite
            except redis.RedisError:
                logger.warning("Redis indisponível no rate limit '%s'; usando memória", self.nome)
        with self._lock:
            return len(self._limpar(chave, time.monotonic())) >= self.limite

    def registrar(self, chave: str) -> None:
        # Registra sempre em memória também: é o que vale se o Redis cair
        with self._lock:
            agora = time.monotonic()
            if chave not in self._eventos and len(self._eventos) >= _MAX_CHAVES_MEMORIA:
                self._descartar_expirados(agora)
            self._limpar(chave, agora, criar=True).append(agora)
        r = get_redis()
        if r is not None:
            try:
                agora = time.time()
                pipe = r.pipeline()
                pipe.zadd(self._chave(chave), {uuid.uuid4().hex: agora})
                pipe.expire(self._chave(chave), self.janela + 1)
                pipe.execute()
            except redis.RedisError:
                logger.warning("Redis indisponível no rate limit '%s'; usando memória", self.nome)

    def resetar(self, chave: str) -> None:
        with self._lock:
            self._eventos.pop(chave, None)
        r = get_redis()
        if r is not None:
            try:
                r.delete(self._chave(chave))
            except redis.RedisError:
                pass

    def limpar_tudo(self) -> None:
        """Só para testes."""
        with self._lock:
            self._eventos.clear()

    # ── Interno ──────────────────────────────────────────────────────────────

    def _chave(self, chave: str) -> str:
        # Hash: a chave é um IP ou e-mail e não precisa ficar legível no Redis
        return f"ratelimit:{self.nome}:{hashlib.sha256(chave.encode()).hexdigest()[:32]}"

    def _limpar(self, chave: str, agora: float, criar: bool = False) -> deque[float]:
        eventos = self._eventos.get(chave)
        if eventos is None:
            eventos = deque()
            if criar:
                self._eventos[chave] = eventos
            return eventos
        while eventos and eventos[0] <= agora - self.janela:
            eventos.popleft()
        if not eventos and not criar:
            del self._eventos[chave]
        return eventos

    def _descartar_expirados(self, agora: float) -> None:
        for chave in [c for c, e in self._eventos.items() if not e or e[-1] <= agora - self.janela]:
            del self._eventos[chave]
        if len(self._eventos) >= _MAX_CHAVES_MEMORIA:
            # Ainda cheio só com chaves ativas: descarta as mais antigas
            for chave in list(self._eventos)[: _MAX_CHAVES_MEMORIA // 10]:
                del self._eventos[chave]

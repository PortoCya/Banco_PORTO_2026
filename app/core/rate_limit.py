"""
Rate limit em memória com janela deslizante.

Vale por processo: com mais de um worker do uvicorn, cada um conta separado.
Quando o Redis entrar na stack, trocar esta classe por uma versão em Redis
mantendo a mesma interface.
"""
import time
from collections import defaultdict, deque
from threading import Lock


class RateLimiter:
    def __init__(self, limite: int, janela_segundos: int):
        self.limite = limite
        self.janela = janela_segundos
        self._eventos: dict[str, deque[float]] = defaultdict(deque)
        self._lock = Lock()

    def _limpar(self, chave: str, agora: float) -> deque[float]:
        eventos = self._eventos[chave]
        while eventos and eventos[0] <= agora - self.janela:
            eventos.popleft()
        return eventos

    def bloqueado(self, chave: str) -> bool:
        with self._lock:
            return len(self._limpar(chave, time.monotonic())) >= self.limite

    def registrar(self, chave: str) -> None:
        with self._lock:
            agora = time.monotonic()
            self._limpar(chave, agora).append(agora)

    def resetar(self, chave: str) -> None:
        with self._lock:
            self._eventos.pop(chave, None)

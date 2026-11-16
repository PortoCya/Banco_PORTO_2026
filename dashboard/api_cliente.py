"""
Cliente da API do NPS KeyCore para o dashboard (sem dependência de Streamlit).

O dashboard não acessa o banco nem a IA diretamente: lê tudo da API, com o
login de um usuário ANALYST ou ADMIN. Assim valem as mesmas regras de acesso,
auditoria e LGPD da API (comentários chegam com dados pessoais mascarados).
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date
from typing import Any, Optional

import httpx

API_URL = os.getenv("NPS_API_URL", "http://localhost:8000").rstrip("/")
# Toda chamada externa tem timeout explícito
TIMEOUT = httpx.Timeout(10.0, connect=5.0)
_PAGINA = 1000              # máximo aceito por GET /pesquisas/{id}/respostas
_MAX_RESPOSTAS = 20_000     # teto por carga, para o dashboard não travar


class ErroApi(Exception):
    """Mensagem pronta para mostrar na tela; status 0 = sem conexão."""

    def __init__(self, mensagem: str, status: int = 0):
        super().__init__(mensagem)
        self.status = status


def nps_inteiro(promotores: int, neutros: int, detratores: int) -> Optional[int]:
    """
    Mesma regra do backend (app/services/nps.py), para recortes que a API não
    calcula (por tema, por semana): inteiro de -100 a 100, arredondamento meio
    para cima; sem respostas → None (nunca 0). O NPS oficial vem de /nps.
    """
    total = promotores + neutros + detratores
    if total == 0:
        return None
    return (200 * (promotores - detratores) + total) // (2 * total)


@dataclass
class ClienteApi:
    token: Optional[str] = None
    http: Optional[httpx.Client] = None     # injetável nos testes

    def __post_init__(self):
        if self.http is None:
            self.http = httpx.Client(base_url=API_URL, timeout=TIMEOUT)

    # ── infra ────────────────────────────────────────────────────────────────
    def _req(self, metodo: str, caminho: str, **kw) -> Any:
        headers = kw.pop("headers", {})
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        try:
            r = self.http.request(metodo, f"/api/v1{caminho}", headers=headers, **kw)
        except httpx.TimeoutException:
            raise ErroApi("A API demorou demais para responder. Tente de novo.")
        except httpx.TransportError:
            raise ErroApi(f"Não foi possível conectar à API em {API_URL}.")
        if r.status_code >= 400:
            try:
                msg = r.json()["error"]["message"]
            except Exception:
                msg = "Erro inesperado da API."
            raise ErroApi(msg, r.status_code)
        return r.json()

    # ── endpoints ────────────────────────────────────────────────────────────
    def login(self, email: str, senha: str) -> dict:
        dados = self._req("POST", "/auth/login", json={"email": email, "senha": senha})
        self.token = dados["access_token"]
        return self.usuario()

    def usuario(self) -> dict:
        return self._req("GET", "/auth/me")

    def pesquisas(self) -> list[dict]:
        return self._req("GET", "/pesquisas", params={"limit": 200})

    def nps(self, id_pesquisa: str, inicio: Optional[date] = None, fim: Optional[date] = None) -> dict:
        params = {k: v.isoformat() for k, v in (("periodo_inicio", inicio), ("periodo_fim", fim)) if v}
        return self._req("GET", f"/pesquisas/{id_pesquisa}/nps", params=params)

    def historico(self, id_pesquisa: str) -> list[dict]:
        return self._req("GET", f"/pesquisas/{id_pesquisa}/nps/historico")

    def respostas(self, id_pesquisa: str, inicio: Optional[date] = None,
                  fim: Optional[date] = None) -> list[dict]:
        """Todas as respostas VALIDAS do período, paginando (comentários anonimizados)."""
        params: dict[str, Any] = {"limit": _PAGINA}
        if inicio:
            params["periodo_inicio"] = inicio.isoformat()
        if fim:
            params["periodo_fim"] = fim.isoformat()
        itens: list[dict] = []
        while len(itens) < _MAX_RESPOSTAS:
            pagina = self._req("GET", f"/pesquisas/{id_pesquisa}/respostas",
                               params={**params, "skip": len(itens)})
            itens.extend(pagina)
            if len(pagina) < _PAGINA:
                break
        return itens

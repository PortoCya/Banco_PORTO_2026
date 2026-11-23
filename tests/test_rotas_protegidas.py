"""
Controle de acesso: toda rota que não é pública exige login, e cada papel só
alcança o que é seu. As rotas são lidas do próprio OpenAPI — rota nova sem
proteção quebra este teste sem ninguém precisar lembrar de listá-la aqui.
"""
import uuid

import pytest

from main import app

PUBLICAS = {
    ("post", "/api/v1/auth/login"),
    ("get", "/api/v1/public/respostas/{token}"),
    ("post", "/api/v1/public/respostas/{token}"),
    ("get", "/health"),
    ("get", "/health/live"),
}

ROTAS = sorted(
    (metodo, caminho)
    for caminho, operacoes in app.openapi()["paths"].items()
    for metodo in operacoes
)
PROTEGIDAS = [r for r in ROTAS if r not in PUBLICAS]

# Rotas em que o ANALYST pode entrar; todo o resto é só ADMIN
ANALYST_PODE = {
    ("get", "/api/v1/auth/me"),
    ("get", "/api/v1/pesquisas"),
    ("get", "/api/v1/pesquisas/{id_pesquisa}"),
    ("get", "/api/v1/pesquisas/{id_pesquisa}/nps"),
    ("get", "/api/v1/pesquisas/{id_pesquisa}/nps/historico"),
    ("get", "/api/v1/pesquisas/{id_pesquisa}/respostas"),
    ("get", "/api/v1/pesquisas/{id_pesquisa}/exportacao"),
    ("get", "/api/v1/pesquisas/{id_pesquisa}/analises-feedback"),
    ("get", "/api/v1/pesquisas/{id_pesquisa}/analises-feedback/resumo"),
    ("patch", "/api/v1/analises-feedback/{id_analise}"),
}


def _url(caminho: str) -> str:
    while "{" in caminho:
        inicio, fim = caminho.index("{"), caminho.index("}")
        caminho = caminho[:inicio] + str(uuid.uuid4()) + caminho[fim + 1:]
    return caminho


def test_lista_de_rotas_publicas_esta_atualizada():
    assert PUBLICAS <= set(ROTAS)
    assert len(PROTEGIDAS) > 25


@pytest.mark.parametrize("metodo,caminho", PROTEGIDAS)
def test_rota_exige_login(client, metodo, caminho):
    r = client.request(metodo, _url(caminho), json={})
    assert r.status_code == 401, f"{metodo.upper()} {caminho} respondeu {r.status_code} sem token"
    assert r.json()["error"]["code"] == "UNAUTHORIZED"


@pytest.mark.parametrize("metodo,caminho", [r for r in PROTEGIDAS if r not in ANALYST_PODE])
def test_rota_de_admin_recusa_analyst(client, analyst, metodo, caminho):
    r = client.request(metodo, _url(caminho), json={}, headers=analyst)
    assert r.status_code == 403, f"{metodo.upper()} {caminho} respondeu {r.status_code} para ANALYST"


def test_revisar_analise_e_so_do_analyst(client, admin):
    r = client.patch(f"/api/v1/analises-feedback/{uuid.uuid4()}", headers=admin, json={"status": "DESCARTADA_MANUAL"})
    assert r.status_code == 403

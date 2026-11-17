"""
Cliente da API usado pelo dashboard (dashboard/api_cliente.py), rodando
contra a API de verdade (TestClient no lugar do httpx.Client).
"""
import itertools
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "dashboard"))
import api_cliente  # noqa: E402

from app.services.nps import calcular_nps  # noqa: E402
from tests.conftest import SENHA, criar_pesquisa, criar_usuario, responder  # noqa: E402


@pytest.fixture
def api(client):
    criar_usuario("an@x.com")
    cli = api_cliente.ClienteApi(http=client)
    cli.login("an@x.com", SENHA)
    return cli


def test_regra_do_nps_igual_a_do_backend():
    for p, n, d in itertools.product(range(12), repeat=3):
        notas = [10] * p + [7] * n + [0] * d
        assert api_cliente.nps_inteiro(p, n, d) == calcular_nps(notas).valor_nps


def test_login_e_leitura_de_pesquisa_nps_e_respostas(client, api):
    id_pesquisa, tok = criar_pesquisa()
    for nota, comentario in ((10, "ótimo"), (9, None), (3, "CPF 123.456.789-00")):
        responder(client, tok, nota, comentario)

    assert api.usuario()["papel"] == "ANALYST"
    assert [p["id"] for p in api.pesquisas()] == [str(id_pesquisa)]
    nps = api.nps(str(id_pesquisa))
    assert (nps["valor_nps"], nps["total_respostas"]) == (33, 3)
    respostas = api.respostas(str(id_pesquisa))
    assert sorted(r["nota_nps"] for r in respostas) == [3, 9, 10]
    assert all("123.456.789-00" not in (r["texto_comentario"] or "") for r in respostas)


def test_respostas_paginam_ate_o_fim(client, api, monkeypatch):
    monkeypatch.setattr(api_cliente, "_PAGINA", 2)
    id_pesquisa, tok = criar_pesquisa()
    for _ in range(5):
        responder(client, tok, 8)
    assert len(api.respostas(str(id_pesquisa))) == 5


def test_erros_viram_mensagem_com_status(client):
    cli = api_cliente.ClienteApi(http=client)
    with pytest.raises(api_cliente.ErroApi) as erro:
        cli.login("nao@x.com", "errada")
    assert erro.value.status == 401 and str(erro.value) == "E-mail ou senha inválidos."
    with pytest.raises(api_cliente.ErroApi) as erro:
        api_cliente.ClienteApi(token="invalido", http=client).pesquisas()
    assert erro.value.status == 401


def test_api_fora_do_ar_vira_status_zero():
    import httpx

    def recusa(request):
        raise httpx.ConnectError("recusado")
    cli = api_cliente.ClienteApi(http=httpx.Client(base_url="http://x", transport=httpx.MockTransport(recusa)))
    with pytest.raises(api_cliente.ErroApi) as erro:
        cli.pesquisas()
    assert erro.value.status == 0


def test_cliente_tem_timeout_explicito():
    t = api_cliente.ClienteApi().http.timeout
    assert None not in (t.connect, t.read, t.write, t.pool)

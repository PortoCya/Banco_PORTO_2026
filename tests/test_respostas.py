"""Fluxo público: coleta, duplicidade (idempotência), snapshot e isolamento da IA."""
import uuid

import pytest

from app.api.v1.endpoints import publico
from app.core.config import settings
from app.core.database import SessionLocal
from app.models.models import JobIa, LinkPesquisa, SnapshotNps, Submissao
from app.services import fila
from tests.conftest import criar_pesquisa, novo_link, responder


def _submissoes(status=None):
    with SessionLocal() as db:
        q = db.query(Submissao)
        return q.filter_by(status=status).all() if status else q.all()


def _nps(client, admin, id_pesquisa):
    return client.get(f"/api/v1/pesquisas/{id_pesquisa}/nps", headers=admin).json()


# ─── Caminho feliz ───────────────────────────────────────────────────────────

def test_carrega_pesquisa_publica_sem_login(client):
    _, tok = criar_pesquisa()
    r = client.get(f"/api/v1/public/respostas/{tok}")
    assert r.status_code == 200
    assert r.json()["texto_pergunta_nps"] == "De 0 a 10?"
    assert "id" not in r.json()


def test_resposta_grava_submissao_link_e_snapshot_na_mesma_transacao(client, admin):
    id_pesquisa, tok = criar_pesquisa()
    r = responder(client, tok, 10, "Muito bom")
    assert r.status_code == 201
    assert set(r.json()) == {"id", "nota_nps", "criada_em"}

    with SessionLocal() as db:
        s = db.query(Submissao).one()
        assert (s.status, s.nota_nps, s.texto_comentario) == ("VALIDA", 10, "Muito bom")
        assert s.endereco_ip and "testclient" not in s.endereco_ip      # só o HMAC do IP
        assert db.query(LinkPesquisa).one().usado_em is not None
        snap = db.query(SnapshotNps).one()
        assert (snap.valor_nps, snap.total_respostas, snap.qtd_promotores) == (100, 1, 1)
        assert db.query(JobIa).one().status == "NA_FILA"


def test_nps_e_historico_acompanham_as_respostas(client, admin):
    id_pesquisa, tok = criar_pesquisa()
    assert _nps(client, admin, id_pesquisa) == {
        "id_pesquisa": str(id_pesquisa), "valor_nps": None, "status": "sem_dados_suficientes",
        "total_respostas": 0, "qtd_promotores": 0, "qtd_neutros": 0, "qtd_detratores": 0,
        "periodo_inicio": None, "periodo_fim": None,
    }
    for nota in (10, 9, 9, 8, 6):
        assert responder(client, tok, nota).status_code == 201
    nps = _nps(client, admin, id_pesquisa)
    assert (nps["valor_nps"], nps["status"], nps["total_respostas"]) == (40, "ok", 5)

    historico = client.get(f"/api/v1/pesquisas/{id_pesquisa}/nps/historico", headers=admin).json()
    assert len(historico) == 1                       # um snapshot por dia, atualizado a cada resposta
    assert (historico[0]["valor_nps"], historico[0]["total_respostas"]) == (40, 5)


def test_comentario_vazio_nao_gera_job_de_ia(client):
    _, tok = criar_pesquisa()
    assert responder(client, tok, 7).status_code == 201
    assert responder(client, tok, 7, "   ").status_code == 201
    with SessionLocal() as db:
        assert db.query(JobIa).count() == 0
        assert {s.texto_comentario for s in db.query(Submissao)} == {None}


def test_comentario_fica_integro_no_banco(client):
    _, tok = criar_pesquisa()
    original = "Meu CPF é 123.456.789-00 <b>e gostei</b> = ótimo"
    assert responder(client, tok, 9, original).status_code == 201
    assert _submissoes()[0].texto_comentario == original


# ─── Validação: 422 e nada gravado ───────────────────────────────────────────

@pytest.mark.parametrize("corpo", [
    {"nota_nps": 11},
    {"nota_nps": -1},
    {"nota_nps": "10"},
    {"nota_nps": 9.5},
    {"nota_nps": True},
    {"nota_nps": None},
    {},
    {"nota_nps": 10, "texto_comentario": "x" * 2001},
    {"nota_nps": 10, "texto_comentario": "nulo\x00aqui"},
    {"nota_nps": 10, "status": "VALIDA"},
    {"nota_nps": 10, "id_pesquisa": str(uuid.uuid4())},
    {"nota_nps": 10, "chave_idempotencia": "curta"},
    {"nota_nps": 10, "chave_idempotencia": "com espaço e ' aspas -- 123456"},
])
def test_entrada_invalida_retorna_422_e_nada_e_gravado(client, corpo):
    _, tok = criar_pesquisa()
    corpo.setdefault("chave_idempotencia", uuid.uuid4().hex)
    r = client.post(f"/api/v1/public/respostas/{tok}", json=corpo)
    assert r.status_code == 422
    with SessionLocal() as db:
        assert db.query(Submissao).count() == db.query(SnapshotNps).count() == db.query(JobIa).count() == 0
        assert db.query(LinkPesquisa).one().usado_em is None


def test_token_invalido_ou_inexistente(client):
    assert responder(client, "token-que-nao-existe", 10).status_code == 404
    assert client.get("/api/v1/public/respostas/a'%20OR%201=1--").status_code == 422
    assert client.get("/api/v1/public/respostas/" + "x" * 200).status_code == 422


@pytest.mark.parametrize("status", ["RASCUNHO", "PAUSADA", "ARQUIVADA"])
def test_pesquisa_nao_publicada_retorna_403(client, status):
    _, tok = criar_pesquisa(status=status)
    assert client.get(f"/api/v1/public/respostas/{tok}").status_code == 403
    assert responder(client, tok, 10).status_code == 403
    assert _submissoes() == []


# ─── Duplicidade ─────────────────────────────────────────────────────────────

def test_mesma_chave_de_idempotencia_nao_conta_duas_vezes(client, admin):
    id_pesquisa, tok = criar_pesquisa()
    chave = uuid.uuid4().hex
    assert responder(client, tok, 10, chave=chave).status_code == 201
    repetida = responder(client, tok, 10, chave=chave)      # cliente reenviou após timeout
    assert repetida.status_code == 409
    assert len(_submissoes("VALIDA")) == 1
    assert len(_submissoes("BLOQUEADA_DUPLICADA")) == 1     # a tentativa fica registrada
    assert _nps(client, admin, id_pesquisa)["total_respostas"] == 1


def test_link_nominal_e_de_uso_unico(client, admin):
    id_pesquisa, tok = criar_pesquisa(tipo_link="NOMINAL")
    assert responder(client, tok, 9).status_code == 201
    segunda = responder(client, tok, 0)                     # outra chave, mesmo token
    assert segunda.status_code == 409
    assert client.get(f"/api/v1/public/respostas/{tok}").status_code == 409
    nps = _nps(client, admin, id_pesquisa)
    assert (nps["total_respostas"], nps["valor_nps"]) == (1, 100)
    assert len(_submissoes("BLOQUEADA_DUPLICADA")) == 1


def test_link_aberto_bloqueia_pelo_cookie_httponly_de_24h(client, admin):
    id_pesquisa, tok = criar_pesquisa()
    primeira = responder(client, tok, 10)
    cookie = primeira.headers["set-cookie"]
    assert "HttpOnly" in cookie and "Max-Age=86400" in cookie

    # Mesmo navegador (cookie presente), chave nova → duplicada
    segunda = client.post(f"/api/v1/public/respostas/{tok}",
                          json={"nota_nps": 0, "chave_idempotencia": uuid.uuid4().hex})
    assert segunda.status_code == 409
    # Outro respondente (sem cookie) responde normalmente
    assert responder(client, tok, 8).status_code == 201
    assert _nps(client, admin, id_pesquisa)["total_respostas"] == 2


def test_409_nao_revela_qual_regra_barrou(client):
    id_pesquisa, aberto = criar_pesquisa()
    nominal = novo_link(id_pesquisa, "NOMINAL")
    chave = uuid.uuid4().hex
    responder(client, aberto, 10, chave=chave)
    por_chave = responder(client, aberto, 10, chave=chave)
    responder(client, nominal, 10)
    por_token = responder(client, nominal, 10)
    responder(client, aberto, 10)
    por_cookie = client.post(f"/api/v1/public/respostas/{aberto}",
                             json={"nota_nps": 1, "chave_idempotencia": uuid.uuid4().hex})
    mensagens = {r.json()["error"]["message"] for r in (por_chave, por_token, por_cookie)}
    assert {r.status_code for r in (por_chave, por_token, por_cookie)} == {409}
    assert len(mensagens) == 1


def test_duplicada_nao_gera_job_de_ia(client):
    _, tok = criar_pesquisa(tipo_link="NOMINAL")
    responder(client, tok, 9, "primeiro")
    responder(client, tok, 9, "segundo")
    with SessionLocal() as db:
        assert db.query(JobIa).count() == 1


# ─── Saturação: 429 ──────────────────────────────────────────────────────────

def test_excesso_por_ip_retorna_429(client, monkeypatch):
    _, tok = criar_pesquisa()
    monkeypatch.setattr(publico.limite_envio, "limite", 3)
    codigos = [responder(client, tok, 10).status_code for _ in range(5)]
    assert codigos == [201, 201, 201, 429, 429]
    assert len(_submissoes()) == 3


# ─── Regra de ouro: a IA nunca atrapalha a coleta ────────────────────────────

def test_fila_da_ia_fora_do_ar_nao_afeta_a_resposta(client, admin, monkeypatch):
    def explode(_):
        raise RuntimeError("fila caiu")
    monkeypatch.setattr(fila, "publicar_analise", explode)

    id_pesquisa, tok = criar_pesquisa()
    assert responder(client, tok, 10, "comentário").status_code == 201
    assert _nps(client, admin, id_pesquisa)["valor_nps"] == 100
    with SessionLocal() as db:
        assert db.query(JobIa).one().status == "NA_FILA"      # o worker pega pela varredura


def test_pela_fila_so_trafega_o_id(client, redis_falso):
    _, tok = criar_pesquisa()
    r = responder(client, tok, 10, "texto que não pode ir para a fila")
    mensagens = redis_falso.xrange(fila.STREAM_ANALISES)
    assert [campos for _, campos in mensagens] == [{"id_submissao": r.json()["id"]}]


def test_cookie_secure_em_producao(client, monkeypatch):
    monkeypatch.setattr(settings, "COOKIE_SECURE", True)
    _, tok = criar_pesquisa()
    cookie = responder(client, tok, 10).headers["set-cookie"]
    assert "Secure" in cookie and "SameSite=none" in cookie

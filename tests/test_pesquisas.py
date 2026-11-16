"""Pesquisas: ciclo de vida, versionamento, links, exportação (LGPD) e auditoria."""
import csv
import io
import uuid

import pytest

from app.core.database import SessionLocal
from app.models.models import LogAuditoria, LogExportacao, Pesquisa
from tests.conftest import criar_pesquisa, responder

BASE = "/api/v1/pesquisas"


def _criar(client, admin, **campos) -> dict:
    r = client.post(BASE, headers=admin, json={"titulo": "Pós-atendimento", **campos})
    assert r.status_code == 201, r.text
    return r.json()


def _acoes_auditadas() -> list[str]:
    with SessionLocal() as db:
        return [l.acao for l in db.query(LogAuditoria).order_by(LogAuditoria.criado_em)]


# ─── Cadastro e validação ────────────────────────────────────────────────────

def test_pesquisa_nasce_rascunho_e_e_auditada(client, admin):
    p = _criar(client, admin)
    assert (p["status"], p["numero_versao"], p["id_pesquisa_pai"]) == ("RASCUNHO", 1, None)
    assert _acoes_auditadas() == ["CRIAR_PESQUISA"]


@pytest.mark.parametrize("corpo", [
    {},
    {"titulo": "ab"},
    {"titulo": "x" * 301},
    {"titulo": "ok ok", "status": "PUBLICADA"},           # não dá para nascer publicada
    {"titulo": "ok ok", "criado_por": str(uuid.uuid4())},  # nem em nome de outra pessoa
    {"titulo": "ok ok", "texto_pergunta_nps": "abc"},
    {"titulo": "nul\x00o aqui"},
])
def test_cadastro_invalido_422_e_nada_gravado(client, admin, corpo):
    assert client.post(BASE, headers=admin, json=corpo).status_code == 422
    with SessionLocal() as db:
        assert db.query(Pesquisa).count() == 0


@pytest.mark.parametrize("url", [
    f"{BASE}/nao-e-uuid",
    f"{BASE}?limit=100000",
    f"{BASE}?limit=0",
    f"{BASE}?skip=-1",
    f"{BASE}?status=QUALQUER",
    f"{BASE}/{uuid.uuid4()}/nps?periodo_inicio=ontem",
    f"{BASE}/{uuid.uuid4()}/nps/historico?limit=99999",
])
def test_parametros_invalidos_422(client, admin, url):
    assert client.get(url, headers=admin).status_code == 422


def test_periodo_invertido_422(client, admin):
    p = _criar(client, admin)
    r = client.get(f"{BASE}/{p['id']}/nps?periodo_inicio=2026-02-01&periodo_fim=2026-01-01", headers=admin)
    assert r.status_code == 422


def test_pesquisa_inexistente_404(client, admin):
    for sufixo in ("", "/nps", "/nps/historico", "/exportacao", "/links", "/analises-feedback"):
        assert client.get(f"{BASE}/{uuid.uuid4()}{sufixo}", headers=admin).status_code == 404


# ─── Ciclo de vida ───────────────────────────────────────────────────────────

def test_ciclo_de_vida_e_transicoes_invalidas(client, admin):
    id_ = _criar(client, admin)["id"]
    assert client.post(f"{BASE}/{id_}/pausar", headers=admin).status_code == 409      # rascunho não pausa
    assert client.post(f"{BASE}/{id_}/publicar", headers=admin).json()["status"] == "PUBLICADA"
    assert client.post(f"{BASE}/{id_}/publicar", headers=admin).status_code == 409    # já publicada
    assert client.post(f"{BASE}/{id_}/pausar", headers=admin).json()["status"] == "PAUSADA"
    assert client.post(f"{BASE}/{id_}/publicar", headers=admin).json()["status"] == "PUBLICADA"
    assert client.post(f"{BASE}/{id_}/arquivar", headers=admin).json()["status"] == "ARQUIVADA"
    for acao in ("publicar", "pausar", "arquivar"):                                   # arquivada é final
        assert client.post(f"{BASE}/{id_}/{acao}", headers=admin).status_code == 409
    assert _acoes_auditadas() == ["CRIAR_PESQUISA", "PUBLICAR_PESQUISA", "PAUSAR_PESQUISA",
                                  "PUBLICAR_PESQUISA", "ARQUIVAR_PESQUISA"]
    with SessionLocal() as db:
        ultimo = db.query(LogAuditoria).filter_by(acao="ARQUIVAR_PESQUISA").one()
        assert (ultimo.estado_antes["status"], ultimo.estado_depois["status"]) == ("PUBLICADA", "ARQUIVADA")


# ─── Versionamento ───────────────────────────────────────────────────────────

def test_editar_sem_respostas_altera_no_lugar(client, admin):
    p = _criar(client, admin)
    r = client.patch(f"{BASE}/{p['id']}", headers=admin, json={"titulo": "Novo título"})
    assert (r.json()["id"], r.json()["titulo"], r.json()["numero_versao"]) == (p["id"], "Novo título", 1)


def test_editar_com_respostas_cria_nova_versao_e_nao_sobrescreve(client, admin):
    id_pesquisa, tok = criar_pesquisa()
    responder(client, tok, 10)

    r = client.patch(f"{BASE}/{id_pesquisa}", headers=admin, json={"titulo": "Título revisado"})
    assert r.status_code == 200
    nova = r.json()
    assert nova["id"] != str(id_pesquisa)
    assert (nova["id_pesquisa_pai"], nova["numero_versao"], nova["status"]) == (str(id_pesquisa), 2, "RASCUNHO")

    original = client.get(f"{BASE}/{id_pesquisa}", headers=admin).json()
    assert (original["titulo"], original["status"]) == ("Pesquisa", "PUBLICADA")   # intacta e ainda coletando
    assert responder(client, tok, 9).status_code == 201
    assert client.get(f"{BASE}/{id_pesquisa}/nps", headers=admin).json()["total_respostas"] == 2
    assert "VERSIONAR_PESQUISA" in _acoes_auditadas()

    # A original já tem sucessora: novas edições vão na versão mais recente
    assert client.patch(f"{BASE}/{id_pesquisa}", headers=admin, json={"titulo": "De novo"}).status_code == 409


def test_patch_vazio_ou_com_campo_proibido_422(client, admin):
    p = _criar(client, admin)
    for corpo in ({}, {"status": "PUBLICADA"}, {"numero_versao": 9}, {"titulo": None}):
        assert client.patch(f"{BASE}/{p['id']}", headers=admin, json=corpo).status_code == 422


# ─── Links ───────────────────────────────────────────────────────────────────

def test_links_token_aleatorio_e_fora_da_auditoria(client, admin):
    id_ = _criar(client, admin)["id"]
    nominal = client.post(f"{BASE}/{id_}/links", headers=admin, json={"tipo": "NOMINAL"}).json()
    aberto = client.post(f"{BASE}/{id_}/links", headers=admin,
                         json={"tipo": "ABERTO", "token_customizado": "satisfacao-2026"}).json()
    assert len(nominal["token"]) >= 32 and aberto["token"] == "satisfacao-2026"
    assert len(client.get(f"{BASE}/{id_}/links", headers=admin).json()) == 2
    with SessionLocal() as db:
        for log in db.query(LogAuditoria).filter_by(acao="CRIAR_LINK_PESQUISA"):
            assert nominal["token"] not in str(log.estado_depois)

    # slug repetido → 409; NOMINAL com slug escolhido → 422 (seria adivinhável)
    assert client.post(f"{BASE}/{id_}/links", headers=admin,
                       json={"tipo": "ABERTO", "token_customizado": "satisfacao-2026"}).status_code == 409
    assert client.post(f"{BASE}/{id_}/links", headers=admin,
                       json={"tipo": "NOMINAL", "token_customizado": "convite-joao"}).status_code == 422
    assert client.post(f"{BASE}/{id_}/links", headers=admin, json={"tipo": "OUTRO"}).status_code == 422


# ─── Exportação ──────────────────────────────────────────────────────────────

def _csv(resposta) -> list[dict]:
    return list(csv.DictReader(io.StringIO(resposta.text.lstrip("﻿"))))


def test_analyst_recebe_exportacao_anonimizada(client, analyst):
    id_pesquisa, tok = criar_pesquisa()
    responder(client, tok, 10, "Ótimo! Meu CPF é 123.456.789-00 e o e-mail joao@empresa.com.br")
    responder(client, tok, 3, "=HYPERLINK(\"http://malicioso\")")
    responder(client, tok, 8)

    r = client.get(f"{BASE}/{id_pesquisa}/exportacao", headers=analyst)
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    linhas = _csv(r)
    assert [l["faixa_nps"] for l in linhas] == ["PROMOTOR", "DETRATOR", "NEUTRO"]
    assert "123.456.789-00" not in r.text and "joao@empresa.com.br" not in r.text
    assert "[CPF]" in linhas[0]["texto_comentario"] and "[EMAIL]" in linhas[0]["texto_comentario"]
    assert linhas[1]["texto_comentario"].startswith("'=")          # fórmula neutralizada
    assert "endereco_ip" not in linhas[0] and "id_link_pesquisa" not in linhas[0]

    with SessionLocal() as db:
        log = db.query(LogExportacao).one()
        assert log.anonimizado is True and "endereco_ip" not in log.campos_exportados
        assert db.query(LogAuditoria).filter_by(acao="EXPORTAR_RESPOSTAS").count() == 1


def test_so_admin_exporta_identificado(client, admin, analyst):
    id_pesquisa, tok = criar_pesquisa()
    responder(client, tok, 10, "CPF 123.456.789-00")

    negado = client.get(f"{BASE}/{id_pesquisa}/exportacao?anonimizado=false", headers=analyst)
    assert negado.status_code == 403
    with SessionLocal() as db:
        assert db.query(LogExportacao).count() == 0                # pedido negado não exporta nada

    r = client.get(f"{BASE}/{id_pesquisa}/exportacao?anonimizado=false", headers=admin)
    linha = _csv(r)[0]
    assert "123.456.789-00" in linha["texto_comentario"] and linha["id_link_pesquisa"]
    with SessionLocal() as db:
        assert db.query(LogExportacao).one().anonimizado is False


def test_exportacao_ignora_respostas_bloqueadas(client, admin):
    id_pesquisa, tok = criar_pesquisa(tipo_link="NOMINAL")
    responder(client, tok, 10)
    responder(client, tok, 0)
    assert len(_csv(client.get(f"{BASE}/{id_pesquisa}/exportacao", headers=admin))) == 1


# ─── Auditoria ───────────────────────────────────────────────────────────────

def test_log_auditoria_filtra_e_pagina(client, admin):
    id_ = _criar(client, admin)["id"]
    client.post(f"{BASE}/{id_}/publicar", headers=admin)
    todos = client.get("/api/v1/log-auditoria", headers=admin).json()
    assert [l["acao"] for l in todos] == ["PUBLICAR_PESQUISA", "CRIAR_PESQUISA"]
    so_criar = client.get(f"/api/v1/log-auditoria?acao=CRIAR_PESQUISA&id_entidade={id_}", headers=admin).json()
    assert len(so_criar) == 1
    assert client.get("/api/v1/log-auditoria?limit=1", headers=admin).json()[0]["acao"] == "PUBLICAR_PESQUISA"
    assert client.get("/api/v1/log-auditoria?acao=x';DROP TABLE usuario;--", headers=admin).status_code == 422
    assert client.get("/api/v1/log-auditoria?de=2026-01-01T00:00:00", headers=admin).status_code == 422

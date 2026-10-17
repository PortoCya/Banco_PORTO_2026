import json

import pytest

from app.api.v1.endpoints import conversas
from app.core.config import settings
from app.core.database import SessionLocal
from app.core.errors import TimeoutError
from app.models.models import Gerenciacao, SoaIa
from app.services import ia_service
from tests.conftest import auth_header, criar_usuario, token


@pytest.fixture
def dois_usuarios(client):
    criar_usuario("ana@x.com")
    criar_usuario("bia@x.com")
    criar_usuario("adm@x.com", papel="ADMIN")
    return {
        "ana": auth_header(token(client, "ana@x.com")),
        "bia": auth_header(token(client, "bia@x.com")),
        "adm": auth_header(token(client, "adm@x.com")),
    }


ROTAS_FECHADAS = [
    ("get", "/api/v1/conversas"),
    ("post", "/api/v1/conversas"),
    ("post", "/api/v1/conversas/consultar"),
    ("get", "/api/v1/analises-feedback"),
    ("get", "/api/v1/gerenciacoes"),
    ("post", "/api/v1/gerenciacoes"),
    ("get", "/api/v1/prompts"),
    ("get", "/api/v1/video-modelos"),
    ("post", "/api/v1/video-modelos"),
]


@pytest.mark.parametrize("metodo,rota", ROTAS_FECHADAS)
def test_rotas_exigem_login(client, metodo, rota):
    assert getattr(client, metodo)(rota).status_code == 401


def test_conversa_pertence_a_quem_criou(client, dois_usuarios):
    h = dois_usuarios
    # Tentar criar em nome de outra pessoa é ignorado: o dono é quem está logado
    r = client.post("/api/v1/conversas", headers=h["ana"], json={"titulo": "minha", "fk_usuario": "outro"})
    assert r.status_code == 201
    cid = r.json()["uuid"]

    assert client.get(f"/api/v1/conversas/{cid}", headers=h["ana"]).status_code == 200
    assert client.get(f"/api/v1/conversas/{cid}", headers=h["bia"]).status_code == 404
    assert client.get(f"/api/v1/conversas/{cid}", headers=h["adm"]).status_code == 200

    assert len(client.get("/api/v1/conversas", headers=h["ana"]).json()) == 1
    # Filtro por outro usuário não funciona para quem não é ADMIN
    ana_id = r.json()["fk_usuario"]
    assert client.get(f"/api/v1/conversas?fk_usuario={ana_id}", headers=h["bia"]).json() == []


def test_gerenciacao_isolada_e_ip_do_servidor(client, dois_usuarios):
    h = dois_usuarios
    r = client.post("/api/v1/gerenciacoes", headers=h["ana"],
                    json={"tipo_pot": "Q", "credencial_ip": "1.2.3.4", "fk_pessoa": "outro"})
    assert r.status_code == 201
    gid = r.json()["uuid"]
    db = SessionLocal()
    g = db.get(Gerenciacao, gid)
    assert g.credencial_ip != "1.2.3.4"
    db.close()
    assert client.get(f"/api/v1/gerenciacoes/{gid}", headers=h["bia"]).status_code == 404
    assert client.patch(f"/api/v1/gerenciacoes/{gid}/status?novo_status=FALHA", headers=h["bia"]).status_code == 404
    assert client.patch(f"/api/v1/gerenciacoes/{gid}/status?novo_status=XYZ", headers=h["ana"]).status_code == 422


def test_limite_de_paginacao(client, dois_usuarios):
    assert client.get("/api/v1/conversas?limit=100000", headers=dois_usuarios["ana"]).status_code == 422


def test_prompts_e_modelos_so_admin(client, dois_usuarios):
    h = dois_usuarios
    r = client.post("/api/v1/video-modelos", headers=h["ana"], json={"provider": "x", "nome_modelo": "y"})
    assert r.status_code == 403
    r = client.post("/api/v1/video-modelos", headers=h["adm"], json={"provider": "x", "nome_modelo": "y"})
    assert r.status_code == 201
    mid = r.json()["uuid"]
    assert client.patch(f"/api/v1/video-modelos/{mid}/ativar", headers=h["ana"]).status_code == 403
    assert client.post("/api/v1/prompts", headers=h["ana"],
                       json={"fk_video_modelo": mid, "conteudo": "x" * 20}).status_code == 403


def test_falha_da_ia_marca_falha_em_vez_de_processando(client, dois_usuarios, monkeypatch):
    async def ia_fora_do_ar(**_):
        raise TimeoutError("A IA não respondeu dentro do tempo limite.")
    monkeypatch.setattr(conversas, "gerar_resposta_ia", ia_fora_do_ar)

    h = dois_usuarios["ana"]
    cid = client.post("/api/v1/conversas", headers=h, json={}).json()["uuid"]
    r = client.post("/api/v1/conversas/consultar", headers=h, json={"conversa_uuid": cid, "mensagem": "oi"})
    assert r.status_code == 504

    db = SessionLocal()
    assert db.query(SoaIa).one().status == "FALHA"
    assert db.query(Gerenciacao).one().status == "FALHA"
    db.close()


def test_sem_chave_da_ia_retorna_503(client, dois_usuarios, monkeypatch):
    monkeypatch.setattr(settings, "OPENAI_API_KEY", None)
    h = dois_usuarios["ana"]
    cid = client.post("/api/v1/conversas", headers=h, json={}).json()["uuid"]
    r = client.post("/api/v1/conversas/consultar", headers=h, json={"conversa_uuid": cid, "mensagem": "oi"})
    assert r.status_code == 503


# ─── Validação da saída da IA ────────────────────────────────────────────────

def _ia_responde(monkeypatch, conteudo: str):
    async def falsa(*_, **__):
        return {"content": conteudo}
    monkeypatch.setattr(ia_service, "gerar_resposta_ia", falsa)


async def test_saida_da_ia_valida(monkeypatch):
    _ia_responde(monkeypatch, json.dumps({
        "sentimento": "NEGATIVO", "confianca": 0.9, "tema": "prazo", "justificativa": "atraso",
    }))
    r = await ia_service.analisar_sentimento("entrega atrasou")
    assert r["sentimento"] == "NEGATIVO" and r["sugestoes_acao"] == []


@pytest.mark.parametrize("conteudo", [
    "não é json",
    json.dumps({"sentimento": "FELIZ", "confianca": 0.9, "tema": "x", "justificativa": "y"}),
    json.dumps({"sentimento": "POSITIVO", "confianca": 7, "tema": "x", "justificativa": "y"}),
    json.dumps({"sentimento": "POSITIVO"}),
])
async def test_saida_da_ia_fora_do_formato_e_descartada(monkeypatch, conteudo):
    _ia_responde(monkeypatch, conteudo)
    with pytest.raises(ia_service.AIError):
        await ia_service.analisar_sentimento("texto")

import logging

import jwt

from app.core.config import settings
from app.core.database import SessionLocal
from app.core.security import gerar_hash_senha, verificar_senha
from app.models.models import LogAuditoria, Usuario
from tests.conftest import SENHA, auth_header, criar_usuario, token

LOGIN = "/api/v1/auth/login"


# ─── Hash ────────────────────────────────────────────────────────────────────

def test_hash_e_argon2id_e_confere():
    h = gerar_hash_senha(SENHA)
    assert h.startswith("$argon2id$")
    assert SENHA not in h
    assert verificar_senha(SENHA, h)
    assert not verificar_senha("outra-senha-qualquer", h)
    assert not verificar_senha(SENHA, None)
    assert not verificar_senha(SENHA, "lixo")


# ─── Login ───────────────────────────────────────────────────────────────────

def test_login_ok(client):
    criar_usuario("a@x.com")
    r = client.post(LOGIN, json={"email": "A@X.com", "senha": SENHA})
    assert r.status_code == 200
    assert r.json()["token_type"] == "bearer"


def test_login_erro_generico(client):
    criar_usuario("a@x.com")
    criar_usuario("inativo@x.com", ativo=False)
    senha_errada = client.post(LOGIN, json={"email": "a@x.com", "senha": "errada"})
    inexistente = client.post(LOGIN, json={"email": "nao@x.com", "senha": SENHA})
    inativo = client.post(LOGIN, json={"email": "inativo@x.com", "senha": SENHA})
    assert senha_errada.status_code == inexistente.status_code == inativo.status_code == 401
    assert senha_errada.json() == inexistente.json() == inativo.json()


def test_me_retorna_usuario_sem_hash(client):
    criar_usuario("a@x.com", papel="ADMIN")
    r = client.get("/api/v1/auth/me", headers=auth_header(token(client, "a@x.com")))
    assert r.status_code == 200
    assert r.json()["email"] == "a@x.com"
    assert r.json()["papel"] == "ADMIN"
    assert "senha_hash" not in r.json()


def test_me_sem_token(client):
    assert client.get("/api/v1/auth/me").status_code == 401


def test_validacao_nao_vaza_senha(client, caplog):
    senha = "senha-secreta-" + "y" * 200   # passa do máximo → 422
    with caplog.at_level(logging.DEBUG):
        r = client.post(LOGIN, json={"email": "a@x.com", "senha": senha})
    assert r.status_code == 422
    assert senha not in r.text
    assert senha not in caplog.text


def test_rate_limit_por_email(client):
    criar_usuario("a@x.com")
    for _ in range(settings.LOGIN_MAX_FALHAS_EMAIL):
        assert client.post(LOGIN, json={"email": "a@x.com", "senha": "errada"}).status_code == 401
    # Bloqueia até a senha certa
    assert client.post(LOGIN, json={"email": "a@x.com", "senha": SENHA}).status_code == 429


def test_rate_limit_por_ip(client):
    for i in range(settings.LOGIN_MAX_TENTATIVAS_IP):
        client.post(LOGIN, json={"email": f"u{i}@x.com", "senha": "errada"})
    assert client.post(LOGIN, json={"email": "novo@x.com", "senha": "errada"}).status_code == 429


# ─── Token ───────────────────────────────────────────────────────────────────

def test_rota_protegida_sem_token_ou_token_invalido(client):
    assert client.get("/api/v1/usuarios").status_code == 401
    assert client.get("/api/v1/usuarios", headers=auth_header("abc")).status_code == 401


def test_token_expirado(client):
    uid = criar_usuario("adm@x.com", papel="ADMIN")
    expirado = jwt.encode({"sub": uid, "iat": 0, "exp": 1}, settings.SECRET_KEY, algorithm="HS256")
    assert client.get("/api/v1/usuarios", headers=auth_header(expirado)).status_code == 401


def test_token_assinado_com_outra_chave(client):
    uid = criar_usuario("adm@x.com", papel="ADMIN")
    falso = jwt.encode({"sub": uid, "iat": 0, "exp": 9999999999}, "outra-chave" * 4, algorithm="HS256")
    assert client.get("/api/v1/usuarios", headers=auth_header(falso)).status_code == 401


def test_usuario_desativado_perde_acesso_na_hora(client):
    uid = criar_usuario("adm@x.com", papel="ADMIN")
    t = token(client, "adm@x.com")
    db = SessionLocal()
    db.get(Usuario, uid).ativo = False
    db.commit()
    db.close()
    assert client.get("/api/v1/usuarios", headers=auth_header(t)).status_code == 401


# ─── Papéis ──────────────────────────────────────────────────────────────────

def test_analyst_nao_acessa_rotas_de_admin(client):
    criar_usuario("an@x.com")
    t = token(client, "an@x.com")
    r = client.post("/api/v1/usuarios", headers=auth_header(t),
                    json={"nome": "Novo", "email": "n@x.com", "senha": SENHA})
    assert r.status_code == 403


def test_admin_cria_usuario_sem_expor_hash_e_audita(client):
    criar_usuario("adm@x.com", papel="ADMIN")
    t = token(client, "adm@x.com")
    r = client.post("/api/v1/usuarios", headers=auth_header(t),
                    json={"nome": "Novo", "email": "n@x.com", "senha": SENHA, "papel": "ANALYST"})
    assert r.status_code == 201
    assert "senha" not in r.text and "hash" not in r.text
    # Novo usuário consegue logar
    token(client, "n@x.com")

    db = SessionLocal()
    log = db.query(LogAuditoria).filter_by(acao="CRIAR_USUARIO").one()
    assert log.estado_depois["papel"] == "ANALYST"
    assert "senha_hash" not in log.estado_depois
    db.close()


def test_senha_curta_rejeitada(client):
    criar_usuario("adm@x.com", papel="ADMIN")
    t = token(client, "adm@x.com")
    r = client.post("/api/v1/usuarios", headers=auth_header(t),
                    json={"nome": "Novo", "email": "n@x.com", "senha": "curta"})
    assert r.status_code == 422


def test_troca_de_papel_auditada_e_vale_na_hora(client):
    criar_usuario("adm@x.com", papel="ADMIN")
    uid = criar_usuario("an@x.com")
    t_admin = token(client, "adm@x.com")
    t_an = token(client, "an@x.com")
    assert client.get("/api/v1/usuarios", headers=auth_header(t_an)).status_code == 403

    r = client.patch(f"/api/v1/usuarios/{uid}", headers=auth_header(t_admin), json={"papel": "ADMIN"})
    assert r.status_code == 200
    # Mesmo token antigo já ganha o novo papel
    assert client.get("/api/v1/usuarios", headers=auth_header(t_an)).status_code == 200

    db = SessionLocal()
    log = db.query(LogAuditoria).filter_by(acao="ATUALIZAR_USUARIO").one()
    assert (log.estado_antes["papel"], log.estado_depois["papel"]) == ("ANALYST", "ADMIN")
    db.close()


def test_admin_nao_se_tranca_fora(client):
    uid = criar_usuario("adm@x.com", papel="ADMIN")
    t = token(client, "adm@x.com")
    h = auth_header(t)
    assert client.patch(f"/api/v1/usuarios/{uid}", headers=h, json={"papel": "ANALYST"}).status_code == 409
    assert client.patch(f"/api/v1/usuarios/{uid}", headers=h, json={"ativo": False}).status_code == 409
    assert client.delete(f"/api/v1/usuarios/{uid}", headers=h).status_code == 409


def test_delete_desativa_em_vez_de_apagar(client):
    criar_usuario("adm@x.com", papel="ADMIN")
    uid = criar_usuario("an@x.com")
    t = token(client, "adm@x.com")
    assert client.delete(f"/api/v1/usuarios/{uid}", headers=auth_header(t)).status_code == 204
    db = SessionLocal()
    assert db.get(Usuario, uid).ativo is False
    db.close()

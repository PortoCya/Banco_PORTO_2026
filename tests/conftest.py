import os

# Precisa vir antes de importar o app: config e engine são lidos no import
os.environ["SECRET_KEY"] = "chave-de-teste-" + "x" * 32
os.environ["DATABASE_URL"] = "sqlite://"

import pytest
from fastapi.testclient import TestClient

from app.api.v1.endpoints import auth
from app.core.database import Base, SessionLocal, engine
from app.core.security import gerar_hash_senha
from app.models.models import Usuario
from main import app

SENHA = "senha-forte-123"


@pytest.fixture(autouse=True)
def banco_limpo():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    for limiter in (auth.limite_ip, auth.limite_email):
        limiter._eventos.clear()
    yield


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def criar_usuario(email: str, papel: str = "ANALYST", ativo: bool = True) -> str:
    db = SessionLocal()
    u = Usuario(nome="Teste", email=email, senha_hash=gerar_hash_senha(SENHA), papel=papel, ativo=ativo)
    db.add(u)
    db.commit()
    uid = u.uuid
    db.close()
    return uid


def token(client, email: str, senha: str = SENHA) -> str:
    r = client.post("/api/v1/auth/login", json={"email": email, "senha": senha})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def auth_header(t: str) -> dict:
    return {"Authorization": f"Bearer {t}"}

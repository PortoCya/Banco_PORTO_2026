import os
import uuid

# Precisa vir antes de importar o app: config e engine são lidos no import.
# Por padrão roda em SQLite na memória; defina TEST_DATABASE_URL para rodar a
# mesma suíte contra um PostgreSQL de teste (o schema é recriado a cada teste).
os.environ["SECRET_KEY"] = "chave-de-teste-" + "x" * 32
os.environ["DATABASE_URL"] = os.environ.get("TEST_DATABASE_URL", "sqlite://")
os.environ["COOKIE_SECURE"] = "false"
os.environ["GOLDEN_SET_MINIMO"] = "4"
os.environ["IA_CUSTO_1K_TOKENS_ENTRADA"] = "1"
os.environ["IA_CUSTO_1K_TOKENS_SAIDA"] = "1"
for variavel in ("REDIS_URL", "WORKER_DATABASE_URL", "IA_API_KEY"):
    os.environ.pop(variavel, None)

import fakeredis
import pytest
import redis
from fastapi.testclient import TestClient

from app.api.v1.endpoints import auth, publico
from app.core import redis as modulo_redis
from app.core.config import settings
from app.core.database import Base, SessionLocal, engine
from app.core.security import gerar_hash_senha
from app.models.models import LinkPesquisa, Pesquisa, Prompt, Usuario, VersaoModelo
from main import app

SENHA = "senha-forte-123"
LIMITADORES = (auth.limite_ip, auth.limite_email, publico.limite_leitura, publico.limite_envio)


def _pragma_fk(valor: str) -> None:
    if engine.dialect.name == "sqlite":
        conexao = engine.raw_connection()
        conexao.execute(f"PRAGMA foreign_keys={valor}")
        conexao.close()


def _recriar_schema() -> None:
    # No SQLite o DROP de tabela autorreferenciada (pesquisa → pesquisa pai)
    # esbarra na FK; desligamos a checagem só durante o drop.
    _pragma_fk("OFF")
    Base.metadata.drop_all(bind=engine)
    _pragma_fk("ON")
    Base.metadata.create_all(bind=engine)


@pytest.fixture(autouse=True)
def banco_limpo():
    _recriar_schema()
    for limiter in LIMITADORES:
        limiter.limpar_tudo()
    modulo_redis.get_redis.cache_clear()
    yield
    modulo_redis.get_redis.cache_clear()


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def db():
    with SessionLocal() as sessao:
        yield sessao


@pytest.fixture
def redis_falso(monkeypatch):
    """Liga o Redis (falso, em memória) para os testes que precisam dele."""
    servidor = fakeredis.FakeServer()
    monkeypatch.setattr(settings, "REDIS_URL", "redis://falso")
    monkeypatch.setattr(
        redis.Redis, "from_url",
        classmethod(lambda cls, url, **kw: fakeredis.FakeRedis(server=servidor, decode_responses=True)),
    )
    modulo_redis.get_redis.cache_clear()
    return fakeredis.FakeRedis(server=servidor, decode_responses=True)


def criar_usuario(email: str, papel: str = "ANALYST", ativo: bool = True) -> uuid.UUID:
    with SessionLocal() as s:
        u = Usuario(nome="Teste", email=email, senha_hash=gerar_hash_senha(SENHA), papel=papel, ativo=ativo)
        s.add(u)
        s.commit()
        return u.id


def token(client, email: str, senha: str = SENHA) -> str:
    r = client.post("/api/v1/auth/login", json={"email": email, "senha": senha})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def auth_header(t: str) -> dict:
    return {"Authorization": f"Bearer {t}"}


@pytest.fixture
def admin(client) -> dict:
    criar_usuario("adm@x.com", papel="ADMIN")
    return auth_header(token(client, "adm@x.com"))


@pytest.fixture
def analyst(client) -> dict:
    criar_usuario("an@x.com")
    return auth_header(token(client, "an@x.com"))


def criar_pesquisa(status: str = "PUBLICADA", tipo_link: str = "ABERTO") -> tuple[uuid.UUID, str]:
    """Cria pesquisa + link direto no banco. Devolve (id_pesquisa, token do link)."""
    with SessionLocal() as s:
        dono = s.query(Usuario).filter_by(email="dono@x.com").first()
        if dono is None:
            dono = Usuario(nome="Dono", email="dono@x.com", senha_hash="x", papel="ADMIN")
            s.add(dono)
            s.flush()
        p = Pesquisa(titulo="Pesquisa", texto_pergunta_nps="De 0 a 10?", status=status, criado_por=dono.id)
        s.add(p)
        s.flush()
        link = LinkPesquisa(id_pesquisa=p.id, tipo=tipo_link, token="tok-" + uuid.uuid4().hex)
        s.add(link)
        s.commit()
        return p.id, link.token


def novo_link(id_pesquisa: uuid.UUID, tipo: str = "ABERTO") -> str:
    with SessionLocal() as s:
        link = LinkPesquisa(id_pesquisa=id_pesquisa, tipo=tipo, token="tok-" + uuid.uuid4().hex)
        s.add(link)
        s.commit()
        return link.token


def responder(client, tok: str, nota: int, comentario: str | None = None, chave: str | None = None):
    """Envia uma resposta sem reaproveitar cookies (cada chamada é um respondente novo)."""
    client.cookies.clear()
    corpo = {"nota_nps": nota, "chave_idempotencia": chave or uuid.uuid4().hex}
    if comentario is not None:
        corpo["texto_comentario"] = comentario
    return client.post(f"/api/v1/public/respostas/{tok}", json=corpo)


def criar_versao_modelo(ativo: bool = False, rotulo: str | None = None) -> uuid.UUID:
    with SessionLocal() as s:
        prompt = Prompt(objetivo="Classificar comentários de NPS.", contexto="Pesquisas KeyCore.",
                        saida_esperada="JSON com sentimento, tema, confianca e justificativa.")
        s.add(prompt)
        s.flush()
        v = VersaoModelo(provedor="teste", nome_modelo="modelo-teste",
                         rotulo_versao=rotulo or "v-" + uuid.uuid4().hex[:8], id_prompt=prompt.id, ativo=ativo)
        s.add(v)
        s.commit()
        return v.id

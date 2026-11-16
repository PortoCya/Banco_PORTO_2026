"""Infraestrutura: request id, health check, saturação, payload, erros e migrations."""
import logging
import re
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy.exc import OperationalError
from sqlalchemy.exc import TimeoutError as PoolTimeoutError

import main
from app.api.v1.endpoints import pesquisas
from app.core.config import settings
from app.core.database import engine
from tests.conftest import criar_pesquisa, responder

RAIZ = Path(__file__).resolve().parent.parent


# ─── Request id ──────────────────────────────────────────────────────────────

def test_toda_resposta_tem_request_id_inclusive_erros(client):
    for r in (client.get("/health"), client.get("/api/v1/usuarios"), client.get("/nao-existe")):
        assert re.fullmatch(r"[0-9a-f]{32}", r.headers["X-Request-ID"])
    erro = client.get("/api/v1/usuarios")
    assert erro.json()["error"]["correlation_id"] == erro.headers["X-Request-ID"]


def test_request_id_do_cliente_e_propagado_ate_os_logs(client, caplog):
    with caplog.at_level(logging.INFO):
        r = client.post("/api/v1/auth/login", json={"email": "a@x.com", "senha": "errada"},
                        headers={"X-Request-ID": "pedido-12345678"})
    assert r.headers["X-Request-ID"] == "pedido-12345678"
    assert r.json()["error"]["correlation_id"] == "pedido-12345678"
    registros = [x for x in caplog.records if x.name.startswith(("app.", "nps."))]
    assert len(registros) >= 2                                   # log da rota + log de acesso
    assert all(x.request_id == "pedido-12345678" for x in registros)


@pytest.mark.parametrize("malicioso", ["curto", "x" * 200, "id com espaco", "linha1\nlinha2 FALSO LOG"])
def test_request_id_invalido_e_substituido(client, malicioso):
    r = client.get("/health/live", headers={"X-Request-ID": malicioso})
    assert re.fullmatch(r"[0-9a-f]{32}", r.headers["X-Request-ID"])


def test_token_do_link_publico_nao_aparece_nos_logs(client, caplog):
    _, tok = criar_pesquisa(tipo_link="NOMINAL")
    with caplog.at_level(logging.DEBUG):
        responder(client, tok, 10)
        responder(client, tok, 10)                               # 409 também passa pelo log de erro
    nossos = "\n".join(x.getMessage() for x in caplog.records if x.name.startswith(("app.", "nps.")))
    assert "/public/respostas/***" in nossos and tok not in nossos


# ─── Health check ────────────────────────────────────────────────────────────

def test_health_consulta_o_banco(client):
    r = client.get("/health")
    assert r.status_code == 200 and r.json()["banco"] == "ok"
    assert client.get("/health/live").json() == {"status": "ok"}


def test_health_503_quando_o_banco_cai(client, monkeypatch):
    def sem_banco():
        raise OperationalError("SELECT 1", {}, Exception("connection refused"))
    monkeypatch.setattr(main.engine, "connect", sem_banco)
    r = client.get("/health")
    assert r.status_code == 503 and r.json()["banco"] == "erro"
    assert "connection refused" not in r.text
    assert client.get("/health/live").status_code == 200         # o processo continua de pé


# ─── Saturação e indisponibilidade ───────────────────────────────────────────

def _quebrar_banco(monkeypatch, excecao):
    def falha(*_, **__):
        raise excecao
    monkeypatch.setattr(pesquisas, "_buscar_pesquisa", falha)


def test_pool_esgotado_responde_429_com_retry_after_e_nao_500(client, admin, monkeypatch):
    _quebrar_banco(monkeypatch, PoolTimeoutError("QueuePool limit of size 10 overflow 10 reached"))
    r = client.get(f"/api/v1/pesquisas/{'0' * 8}-0000-0000-0000-{'0' * 12}/nps", headers=admin)
    assert r.status_code == 429
    assert r.json()["error"]["code"] == "SERVER_BUSY" and int(r.headers["Retry-After"]) > 0
    assert "QueuePool" not in r.text


def test_banco_fora_responde_503_sem_vazar_sql(client, admin, monkeypatch):
    _quebrar_banco(monkeypatch, OperationalError("SELECT senha_hash FROM usuario", {"p": "segredo"}, Exception("down")))
    r = client.get(f"/api/v1/pesquisas/{'0' * 8}-0000-0000-0000-{'0' * 12}/nps", headers=admin)
    assert r.status_code == 503 and "Retry-After" in r.headers
    assert "senha_hash" not in r.text and "segredo" not in r.text


def test_erro_inesperado_responde_500_generico(admin, monkeypatch):
    from fastapi.testclient import TestClient
    _quebrar_banco(monkeypatch, RuntimeError("detalhe interno secreto"))
    with TestClient(main.app, raise_server_exceptions=False) as c:
        r = c.get(f"/api/v1/pesquisas/{'0' * 8}-0000-0000-0000-{'0' * 12}/nps", headers=admin)
    assert r.status_code == 500 and "secreto" not in r.text
    assert r.json()["error"]["correlation_id"] == r.headers["X-Request-ID"]


def test_pool_de_conexoes_e_timeouts_configurados_para_postgres(monkeypatch):
    from app.core import database
    recebido = {}
    monkeypatch.setattr(database, "create_engine", lambda url, **kw: recebido.update(kw))
    database.criar_engine("postgresql+psycopg://u:s@localhost:1/x")
    assert recebido["pool_size"] == settings.DB_POOL_SIZE and recebido["pool_pre_ping"] is True
    assert recebido["pool_timeout"] == settings.DB_POOL_TIMEOUT_SEGUNDOS
    assert recebido["hide_parameters"] is True
    args = recebido["connect_args"]
    assert args["connect_timeout"] == settings.DB_CONNECT_TIMEOUT_SEGUNDOS
    assert "statement_timeout" in args["options"] and "lock_timeout" in args["options"]


# ─── Payload e formato de erro ───────────────────────────────────────────────

def test_payload_grande_demais_413(client):
    _, tok = criar_pesquisa()
    grande = {"nota_nps": 10, "chave_idempotencia": "k" * 32, "texto_comentario": "x" * (settings.MAX_PAYLOAD_BYTES + 1)}
    assert client.post(f"/api/v1/public/respostas/{tok}", json=grande).status_code == 413

    def em_pedacos():                                            # sem Content-Length (chunked)
        for _ in range(40):
            yield b"x" * 4096
    r = client.post(f"/api/v1/public/respostas/{tok}", content=em_pedacos(),
                    headers={"Content-Type": "application/json"})
    assert r.status_code == 413 and r.json()["error"]["code"] == "PAYLOAD_TOO_LARGE"


def test_content_length_invalido_nao_vira_500(client):
    r = client.post("/api/v1/auth/login", content=b"{}", headers={"Content-Length": "abc"})
    assert r.status_code in (400, 413)


def test_erros_tem_formato_unico(client):
    for r in (client.get("/nao-existe"), client.delete("/health"), client.post("/api/v1/auth/login", content=b"{lixo")):
        assert set(r.json()["error"]) >= {"code", "message", "correlation_id"}
    assert client.get("/nao-existe").json()["error"]["code"] == "NOT_FOUND"


def test_cabecalhos_de_seguranca_e_cors(client):
    r = client.get("/health")
    assert r.headers["X-Content-Type-Options"] == "nosniff" and r.headers["X-Frame-Options"] == "DENY"
    permitido = client.options("/api/v1/auth/login", headers={
        "Origin": settings.cors_origins[0], "Access-Control-Request-Method": "POST"})
    assert permitido.headers["access-control-allow-origin"] == settings.cors_origins[0]
    negado = client.options("/api/v1/auth/login", headers={
        "Origin": "https://malicioso.example", "Access-Control-Request-Method": "POST"})
    assert "access-control-allow-origin" not in negado.headers


# ─── Configuração e segredos ─────────────────────────────────────────────────

def test_app_nao_sobe_sem_secret_key():
    r = subprocess.run(
        [sys.executable, "-c", "import app.core.config"], cwd=RAIZ, capture_output=True, text=True,
        env={"PATH": "/usr/bin:/bin", "PYTHONPATH": str(RAIZ), "HOME": "/nonexistent"},
    )
    assert r.returncode != 0 and "SECRET_KEY" in r.stderr


@pytest.mark.parametrize("variavel,valor", [("CORS_ORIGINS", "*"), ("ALGORITHM", "none"), ("SECRET_KEY", "curta")])
def test_configuracao_insegura_e_recusada(variavel, valor):
    from pydantic import ValidationError
    from app.core.config import Settings
    with pytest.raises(ValidationError):
        Settings(**{"SECRET_KEY": "x" * 40, variavel: valor})


def test_nenhum_segredo_versionado():
    arquivos = subprocess.run(["git", "ls-files"], cwd=RAIZ, capture_output=True, text=True).stdout.split()
    assert ".env" not in arquivos
    padroes = re.compile(r"AIza[0-9A-Za-z_\-]{30,}|sk-[A-Za-z0-9]{20,}|ghp_[A-Za-z0-9]{30,}|@KeyCore2026")
    suspeitos = [a for a in arquivos if a.endswith((".py", ".md", ".example", ".yml", ".sh", ".toml", ".ini"))
                 and not a.startswith("tests/") and (RAIZ / a).is_file() and padroes.search((RAIZ / a).read_text(errors="ignore"))]
    assert suspeitos == []


# ─── Migrations ──────────────────────────────────────────────────────────────

def _alembic(*args, url: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args], cwd=RAIZ, capture_output=True, text=True,
        env={"PATH": "/usr/bin:/bin", "PYTHONPATH": str(RAIZ), "SECRET_KEY": "x" * 40, "DATABASE_URL": url},
    )


def test_migrations_criam_exatamente_o_schema_dos_modelos(tmp_path):
    """Mudou um modelo e esqueceu a migration? Este teste quebra."""
    url = f"sqlite:///{tmp_path / 'migracao.db'}"
    subir = _alembic("upgrade", "head", url=url)
    assert subir.returncode == 0, subir.stderr
    conferir = _alembic("check", url=url)
    assert conferir.returncode == 0, conferir.stdout + conferir.stderr
    assert _alembic("downgrade", "base", url=url).returncode == 0


def test_migration_nao_remove_coluna_ou_tabela_sem_marcacao():
    """
    Regra do "não apaga no mesmo deploy": o upgrade() só pode ter DROP se a
    migration declarar, com `# contrato: <revisão/PR que parou de usar>`, que
    o código que usava aquilo já saiu em um deploy anterior.
    """
    destrutivo = re.compile(r"op\.(drop_column|drop_table)|batch_op\.drop_column")
    for arquivo in sorted((RAIZ / "alembic" / "versions").glob("*.py")):
        upgrade = arquivo.read_text().split("def upgrade()")[1].split("def downgrade()")[0]
        if destrutivo.search(upgrade):
            assert re.search(r"#\s*contrato:\s*\S+", upgrade), f"{arquivo.name}: DROP sem '# contrato:'"


def test_tabelas_do_agents_md():
    from app.core.database import Base
    assert set(Base.metadata.tables) == {
        "usuario", "pesquisa", "link_pesquisa", "submissao", "snapshot_nps", "log_auditoria", "log_exportacao",
        "analise_feedback", "job_ia", "versao_modelo", "prompt",
        "comentario_golden_set", "rotulo_golden_set", "avaliacao_golden_set",
        "evento_circuit_breaker", "snapshot_telemetria",
    }
    assert engine.pool is not None

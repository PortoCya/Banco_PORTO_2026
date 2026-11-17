"""
Concorrência e N+1.

Os testes de corrida só fazem sentido em PostgreSQL (o SQLite serializa tudo):
    TEST_DATABASE_URL=postgresql+psycopg://... pytest tests/test_concorrencia.py
"""
import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event

from app.core.database import SessionLocal, engine
from app.models.models import AnaliseFeedback, JobIa, SnapshotNps, Submissao
from main import app
from tests.conftest import criar_pesquisa, criar_versao_modelo, responder

so_postgres = pytest.mark.skipif(engine.dialect.name != "postgresql", reason="corrida real só em PostgreSQL")


def _em_paralelo(tok: str, corpos: list[dict]) -> list[int]:
    def enviar(corpo):
        with TestClient(app) as c:                       # um cliente (sem cookies) por respondente
            return c.post(f"/api/v1/public/respostas/{tok}", json=corpo).status_code
    with ThreadPoolExecutor(max_workers=16) as pool:
        return list(pool.map(enviar, corpos))


@so_postgres
def test_respostas_simultaneas_mantem_snapshot_exato(monkeypatch):
    from app.api.v1.endpoints import publico
    monkeypatch.setattr(publico.limite_envio, "limite", 10_000)
    id_pesquisa, tok = criar_pesquisa()
    notas = [10, 9, 8, 7, 3, 0] * 10
    codigos = _em_paralelo(tok, [{"nota_nps": n, "chave_idempotencia": uuid.uuid4().hex} for n in notas])
    assert codigos == [201] * 60
    with SessionLocal() as db:
        snap = db.query(SnapshotNps).one()
        assert (snap.total_respostas, snap.qtd_promotores, snap.qtd_neutros, snap.qtd_detratores) == (60, 20, 20, 20)
        assert snap.valor_nps == 0


@so_postgres
def test_mesma_chave_em_paralelo_entra_uma_vez_so():
    id_pesquisa, tok = criar_pesquisa()
    chave = uuid.uuid4().hex
    codigos = _em_paralelo(tok, [{"nota_nps": 10, "chave_idempotencia": chave}] * 12)
    assert sorted(codigos) == [201] + [409] * 11
    with SessionLocal() as db:
        assert db.query(Submissao).filter_by(status="VALIDA").count() == 1
        assert db.query(SnapshotNps).one().total_respostas == 1


@so_postgres
def test_token_nominal_em_paralelo_e_usado_uma_vez_so():
    id_pesquisa, tok = criar_pesquisa(tipo_link="NOMINAL")
    codigos = _em_paralelo(tok, [{"nota_nps": 9, "chave_idempotencia": uuid.uuid4().hex} for _ in range(12)])
    assert sorted(codigos) == [201] + [409] * 11
    with SessionLocal() as db:
        assert db.query(Submissao).filter_by(status="VALIDA").count() == 1
        assert db.query(Submissao).filter_by(status="BLOQUEADA_DUPLICADA").count() == 11


class _ContadorDeConsultas:
    def __enter__(self):
        self.total = 0
        event.listen(engine, "before_cursor_execute", self._contar)
        return self

    def __exit__(self, *_):
        event.remove(engine, "before_cursor_execute", self._contar)

    def _contar(self, conn, cursor, statement, *_):
        if statement.lstrip().upper().startswith("SELECT"):
            self.total += 1


def _consultas(client, url, headers) -> int:
    with _ContadorDeConsultas() as contador:
        assert client.get(url, headers=headers).status_code == 200
    return contador.total


def test_listagens_nao_tem_n_mais_1(client, admin):
    """O número de consultas não cresce com o número de linhas devolvidas."""
    id_versao = criar_versao_modelo(ativo=True)
    id_pesquisa, tok = criar_pesquisa()

    def popular(quantidade: int) -> None:
        for _ in range(quantidade):
            responder(client, tok, 9, "comentário")
        with SessionLocal() as db:
            for job in db.query(JobIa).filter_by(status="NA_FILA"):
                db.add(AnaliseFeedback(id_submissao=job.id_submissao, id_versao_modelo=id_versao,
                                       sentimento="POSITIVO", tema="produto", confianca=0.9, status="CONCLUIDA"))
                job.status = "CONCLUIDO"
            db.commit()

    urls = [
        f"/api/v1/pesquisas/{id_pesquisa}/analises-feedback",
        f"/api/v1/pesquisas/{id_pesquisa}/analises-feedback/resumo",
        f"/api/v1/pesquisas/{id_pesquisa}/exportacao",
        f"/api/v1/pesquisas/{id_pesquisa}/nps",
        f"/api/v1/pesquisas/{id_pesquisa}/nps/historico",
        f"/api/v1/pesquisas/{id_pesquisa}/respostas",
        "/api/v1/pesquisas",
        "/api/v1/ia/jobs",
        "/api/v1/log-auditoria",
    ]
    popular(2)
    com_poucas = [_consultas(client, u, admin) for u in urls]
    popular(15)
    com_muitas = [_consultas(client, u, admin) for u in urls]
    assert com_muitas == com_poucas
    assert len(client.get(urls[0], headers=admin).json()) == 17
    assert max(com_muitas) <= 4          # usuário do token + existência da pesquisa + a consulta em si

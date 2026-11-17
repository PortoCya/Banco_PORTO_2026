"""
Cálculo do NPS — regra de domínio, determinística, sem IA.

NPS = %promotores (9–10) − %detratores (0–6). Neutros (7–8) só contam no
total. Resultado inteiro de −100 a +100, arredondando meio para cima.
Sem respostas não existe NPS: valor_nps é None (nunca 0).
"""
import uuid
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from typing import Optional

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.models.models import SnapshotNps, Submissao, agora_utc


def faixa_nps(nota: int) -> str:
    if not 0 <= nota <= 10:
        raise ValueError("A nota NPS deve ser um inteiro entre 0 e 10.")
    if nota >= 9:
        return "PROMOTOR"
    if nota >= 7:
        return "NEUTRO"
    return "DETRATOR"


@dataclass(frozen=True)
class ResultadoNps:
    qtd_promotores: int
    qtd_neutros: int
    qtd_detratores: int

    @property
    def total_respostas(self) -> int:
        return self.qtd_promotores + self.qtd_neutros + self.qtd_detratores

    @property
    def valor_nps(self) -> Optional[int]:
        total = self.total_respostas
        if total == 0:
            return None
        # Aritmética inteira: floor(x + 0,5) com x = 100·(P − D)/total.
        # Evita float e o arredondamento "do banqueiro" do round() do Python.
        return (200 * (self.qtd_promotores - self.qtd_detratores) + total) // (2 * total)

    @property
    def status(self) -> str:
        return "ok" if self.total_respostas else "sem_dados_suficientes"


def calcular_nps(notas: list[int]) -> ResultadoNps:
    faixas = [faixa_nps(n) for n in notas]
    return ResultadoNps(
        qtd_promotores=faixas.count("PROMOTOR"),
        qtd_neutros=faixas.count("NEUTRO"),
        qtd_detratores=faixas.count("DETRATOR"),
    )


def _inicio_do_dia(d: date) -> datetime:
    return datetime.combine(d, time.min, tzinfo=timezone.utc)


def filtrar_periodo(consulta, periodo_inicio: Optional[date], periodo_fim: Optional[date]):
    """Restringe a submissões criadas entre os dois dias (UTC), inclusive."""
    if periodo_inicio:
        consulta = consulta.where(Submissao.criada_em >= _inicio_do_dia(periodo_inicio))
    if periodo_fim:
        consulta = consulta.where(Submissao.criada_em < _inicio_do_dia(periodo_fim + timedelta(days=1)))
    return consulta


def nps_da_pesquisa(
    db: Session,
    id_pesquisa: uuid.UUID,
    periodo_inicio: Optional[date] = None,
    periodo_fim: Optional[date] = None,
) -> ResultadoNps:
    """Conta as faixas no banco (uma consulta agregada). Só submissões VALIDAS."""
    consulta = select(
        func.coalesce(func.sum(case((Submissao.nota_nps >= 9, 1), else_=0)), 0),
        func.coalesce(func.sum(case((Submissao.nota_nps.between(7, 8), 1), else_=0)), 0),
        func.coalesce(func.sum(case((Submissao.nota_nps <= 6, 1), else_=0)), 0),
    ).where(Submissao.id_pesquisa == id_pesquisa, Submissao.status == "VALIDA")
    consulta = filtrar_periodo(consulta, periodo_inicio, periodo_fim)
    promotores, neutros, detratores = db.execute(consulta).one()
    return ResultadoNps(int(promotores), int(neutros), int(detratores))


def atualizar_snapshot_do_dia(db: Session, id_pesquisa: uuid.UUID) -> None:
    """
    Recalcula o NPS acumulado e grava no snapshot de hoje (cria ou atualiza).
    Sem commit: roda na transação de quem chama, que deve estar com a linha da
    PESQUISA travada (FOR UPDATE) para serializar respostas simultâneas.
    """
    db.flush()
    resultado = nps_da_pesquisa(db, id_pesquisa)
    if resultado.valor_nps is None:
        return
    hoje = agora_utc().date()
    snapshot = db.execute(
        select(SnapshotNps).where(
            SnapshotNps.id_pesquisa == id_pesquisa,
            SnapshotNps.periodo_inicio == hoje,
            SnapshotNps.periodo_fim == hoje,
        )
    ).scalar_one_or_none()
    if snapshot is None:
        snapshot = SnapshotNps(id_pesquisa=id_pesquisa, periodo_inicio=hoje, periodo_fim=hoje)
        db.add(snapshot)
    snapshot.valor_nps = resultado.valor_nps
    snapshot.total_respostas = resultado.total_respostas
    snapshot.qtd_promotores = resultado.qtd_promotores
    snapshot.qtd_neutros = resultado.qtd_neutros
    snapshot.qtd_detratores = resultado.qtd_detratores
    snapshot.calculado_em = agora_utc()

"""Consultas compartilhadas sobre ANALISE_FEEDBACK (a análise sugerida vigente)."""
from sqlalchemy import func, select

from app.models.models import AnaliseFeedback


def ultima_sequencia():
    """
    Subconsulta: a maior sequencia_versao de cada submissão. Reanálise cria
    linha nova; a API mostra sempre a mais recente.
    """
    return (
        select(
            AnaliseFeedback.id_submissao.label("id_submissao"),
            func.max(AnaliseFeedback.sequencia_versao).label("sequencia"),
        )
        .group_by(AnaliseFeedback.id_submissao)
        .subquery()
    )

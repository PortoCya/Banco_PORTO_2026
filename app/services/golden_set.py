"""
Golden set — gate de ativação de modelo (regra de domínio, pura).

Uma VERSAO_MODELO só pode ficar ativa se a última AVALIACAO_GOLDEN_SET for
APROVADO:
- acurácia de sentimento ≥ 80%
- acurácia de tema ≥ 70%
- falso positivo ≤ 5% (comentário NEGATIVO que o modelo chamou de POSITIVO,
  sobre o total de comentários NEGATIVOS do golden set)
- nenhuma métrica pode piorar mais de 5 p.p. em relação à versão ativa
"""
from dataclasses import dataclass
from typing import Optional

MIN_ACURACIA_SENTIMENTO = 0.80
MIN_ACURACIA_TEMA = 0.70
MAX_FALSO_POSITIVO = 0.05
MAX_QUEDA = 0.05
_EPS = 1e-9


@dataclass(frozen=True)
class Par:
    """Rótulo humano x saída do modelo (None = o modelo não devolveu saída válida)."""
    sentimento_humano: str
    tema_humano: str
    sentimento_modelo: Optional[str]
    tema_modelo: Optional[str]


@dataclass(frozen=True)
class Metricas:
    acuracia_sentimento: float
    acuracia_tema: float
    taxa_falso_positivo: float


def calcular_metricas(pares: list[Par]) -> Metricas:
    if not pares:
        raise ValueError("Golden set vazio.")
    total = len(pares)
    negativos = [p for p in pares if p.sentimento_humano == "NEGATIVO"]
    falsos_positivos = sum(1 for p in negativos if p.sentimento_modelo == "POSITIVO")
    return Metricas(
        acuracia_sentimento=round(sum(p.sentimento_modelo == p.sentimento_humano for p in pares) / total, 4),
        acuracia_tema=round(sum(p.tema_modelo == p.tema_humano for p in pares) / total, 4),
        taxa_falso_positivo=round(falsos_positivos / len(negativos), 4) if negativos else 0.0,
    )


def decidir(novas: Metricas, anterior: Optional[Metricas]) -> str:
    aprovado = (
        novas.acuracia_sentimento >= MIN_ACURACIA_SENTIMENTO
        and novas.acuracia_tema >= MIN_ACURACIA_TEMA
        and novas.taxa_falso_positivo <= MAX_FALSO_POSITIVO
    )
    if aprovado and anterior is not None:
        aprovado = (
            anterior.acuracia_sentimento - novas.acuracia_sentimento <= MAX_QUEDA + _EPS
            and anterior.acuracia_tema - novas.acuracia_tema <= MAX_QUEDA + _EPS
            and novas.taxa_falso_positivo - anterior.taxa_falso_positivo <= MAX_QUEDA + _EPS
        )
    return "APROVADO" if aprovado else "REPROVADO"

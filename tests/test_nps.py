"""Cálculo do NPS (regra de domínio pura)."""
import pytest

from app.services.nps import calcular_nps, faixa_nps


def test_so_promotores():
    r = calcular_nps([9, 10, 10])
    assert (r.valor_nps, r.status, r.total_respostas) == (100, "ok", 3)


def test_so_detratores():
    assert calcular_nps([0, 3, 6]).valor_nps == -100


def test_so_neutros():
    r = calcular_nps([7, 8, 8])
    assert r.valor_nps == 0
    assert (r.qtd_promotores, r.qtd_neutros, r.qtd_detratores) == (0, 3, 0)
    assert r.status == "ok"       # zero com respostas é NPS válido


@pytest.mark.parametrize("nota,esperado", [(10, 100), (7, 0), (0, -100)])
def test_uma_resposta(nota, esperado):
    assert calcular_nps([nota]).valor_nps == esperado


def test_zero_respostas_nao_e_zero():
    r = calcular_nps([])
    assert r.valor_nps is None
    assert r.status == "sem_dados_suficientes"
    assert r.total_respostas == 0


def test_neutros_so_contam_no_total():
    # 2 promotores, 2 neutros, 1 detrator → 40% − 20% = 20
    assert calcular_nps([10, 9, 8, 7, 3]).valor_nps == 20


@pytest.mark.parametrize("promotores,detratores,neutros,esperado", [
    (1, 0, 7, 13),     # 12,5 → 13 (round() do Python daria 12)
    (0, 1, 7, -12),    # −12,5 → −12 (meio para cima = em direção a +∞)
    (3, 0, 5, 38),     # 37,5 → 38
    (1, 0, 2, 33),     # 33,33 → 33
    (2, 0, 1, 67),     # 66,67 → 67
    (0, 2, 1, -67),    # −66,67 → −67
])
def test_arredondamento_meio_para_cima(promotores, detratores, neutros, esperado):
    notas = [10] * promotores + [0] * detratores + [7] * neutros
    assert calcular_nps(notas).valor_nps == esperado


def test_faixas():
    assert [faixa_nps(n) for n in range(11)] == ["DETRATOR"] * 7 + ["NEUTRO"] * 2 + ["PROMOTOR"] * 2


@pytest.mark.parametrize("nota", [-1, 11])
def test_nota_fora_da_escala(nota):
    with pytest.raises(ValueError):
        faixa_nps(nota)

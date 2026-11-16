"""Mascaramento de PII em vários formatos."""
import pytest

from app.services.pii import mascarar_pii, texto_anonimizado


@pytest.mark.parametrize("texto,mascara,vazou", [
    ("Meu CPF é 123.456.789-00, podem conferir", "[CPF]", "123.456.789-00"),
    ("cpf 12345678900", "[CPF]", "12345678900"),
    ("cpf 123 456 789 00", "[CPF]", "789 00"),
    ("CPF:123.456.789/00", "[CPF]", "456"),
    ("CNPJ 12.345.678/0001-90", "[CNPJ]", "0001-90"),
    ("cnpj 12345678000190", "[CNPJ]", "12345678000190"),
    ("me escreve em joao.silva+nps@empresa.com.br", "[EMAIL]", "joao.silva"),
    ("JOAO@EMPRESA.COM", "[EMAIL]", "EMPRESA"),
    ("joao arroba empresa ponto com", "[EMAIL]", "empresa"),
    ("joao [at] empresa.com", "[EMAIL]", "empresa"),
    ("liga no (11) 91234-5678", "[TELEFONE]", "91234"),
    ("whats +55 11 912345678", "[TELEFONE]", "912345678"),
    ("fixo 11 3456-7890", "[TELEFONE]", "3456"),
    ("tel 11.91234.5678", "[TELEFONE]", "5678"),
    ("0xx11 3456 7890", "[TELEFONE]", "7890"),
])
def test_mascara_formatos(texto, mascara, vazou):
    r = mascarar_pii(texto)
    assert r.status == "MASCARADO"
    assert mascara in r.texto
    assert vazou not in r.texto


def test_varios_dados_no_mesmo_texto():
    r = mascarar_pii("CPF 123.456.789-00, joao@x.com, (11) 91234-5678. Atendimento ótimo!")
    assert r.texto == "CPF [CPF], [EMAIL], [TELEFONE]. Atendimento ótimo!"


@pytest.mark.parametrize("texto", [
    "Atendimento excelente, nota 10!",
    "Demorou 15 dias e paguei R$ 1.200,00 em 2026",
    "Comprei 3 unidades do produto 4500",
])
def test_texto_sem_pii_nao_e_alterado(texto):
    r = mascarar_pii(texto)
    assert (r.texto, r.status) == (texto, "NAO_APLICAVEL")


@pytest.mark.parametrize("texto", [None, "", "   "])
def test_vazio(texto):
    assert mascarar_pii(texto).status == "NAO_APLICAVEL"


@pytest.mark.parametrize("texto", [
    "protocolo 9988776655443322",                                # dígitos que nenhuma regra reconhece
    "fala comigo em joao@",                                      # e-mail quebrado
])
def test_na_duvida_falha_e_o_texto_nao_sai(texto):
    r = mascarar_pii(texto)
    assert r.status == "FALHA_MASCARAMENTO_PII"
    assert r.texto is None and not r.seguro
    assert texto_anonimizado(texto).startswith("[COMENTÁRIO OCULTO")


def test_numero_de_cartao_nunca_sai_legivel():
    assert "1111" not in texto_anonimizado("meu cartão 4111 1111 1111 1111 foi cobrado duas vezes")

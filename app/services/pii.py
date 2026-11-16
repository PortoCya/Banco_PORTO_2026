"""
Mascaramento de PII (CPF, CNPJ, e-mail, telefone).

Usado antes de qualquer envio ao provedor de IA, na varredura da resposta do
modelo e nas visões anonimizadas (ANALYST). O texto original nunca é alterado
no banco.

Política conservadora: se depois de mascarar ainda sobrar algo com cara de
dado pessoal (sequência longa de dígitos, "@"), o resultado é INCERTO e o
texto não deve sair.
"""
import re
from dataclasses import dataclass
from typing import Optional

_SEP = r"[\s.\-/]{0,3}"
_CNPJ = re.compile(rf"(?<!\d)\d{{2}}{_SEP}\d{{3}}{_SEP}\d{{3}}{_SEP}\d{{4}}{_SEP}\d{{2}}(?!\d)")
_CPF = re.compile(rf"(?<!\d)\d{{3}}{_SEP}\d{{3}}{_SEP}\d{{3}}{_SEP}\d{{2}}(?!\d)")
_EMAIL = re.compile(
    r"[A-Za-z0-9._%+\-]+\s?(?:@|\[at\]|\(at\)|\s+arroba\s+)\s?[A-Za-z0-9.\-]+"
    r"(?:\.|\s+ponto\s+)[A-Za-z]{2,}(?:\.[A-Za-z]{2,})?",
    re.IGNORECASE,
)
_TELEFONE = re.compile(
    r"(?<!\d)(?:\+?55[\s.\-]?)?(?:\(?0?\d{2}\)?[\s.\-]?)?9?[\s.\-]?\d{4}[\s.\-]?\d{4}(?!\d)"
)
# O que não pode sobrar depois de mascarar
_DIGITOS_RESIDUAIS = re.compile(r"(?:\d[\s.\-/()]{0,2}){8,}")

MASCARAS = ("[CPF]", "[CNPJ]", "[EMAIL]", "[TELEFONE]")


@dataclass(frozen=True)
class ResultadoMascaramento:
    texto: Optional[str]        # None quando status == FALHA_MASCARAMENTO_PII
    status: str                 # NAO_APLICAVEL | MASCARADO | FALHA_MASCARAMENTO_PII

    @property
    def seguro(self) -> bool:
        return self.status != "FALHA_MASCARAMENTO_PII"


def mascarar_pii(texto: Optional[str]) -> ResultadoMascaramento:
    if not texto or not texto.strip():
        return ResultadoMascaramento(texto, "NAO_APLICAVEL")
    try:
        mascarado = _EMAIL.sub("[EMAIL]", texto)
        mascarado = _CNPJ.sub("[CNPJ]", mascarado)
        mascarado = _CPF.sub("[CPF]", mascarado)
        mascarado = _TELEFONE.sub("[TELEFONE]", mascarado)
        if "@" in mascarado or _DIGITOS_RESIDUAIS.search(mascarado):
            return ResultadoMascaramento(None, "FALHA_MASCARAMENTO_PII")
    except Exception:
        return ResultadoMascaramento(None, "FALHA_MASCARAMENTO_PII")
    return ResultadoMascaramento(mascarado, "MASCARADO" if mascarado != texto else "NAO_APLICAVEL")


def texto_anonimizado(texto: Optional[str]) -> Optional[str]:
    """Para exibição/exportação anonimizada: na dúvida, oculta o comentário inteiro."""
    resultado = mascarar_pii(texto)
    return resultado.texto if resultado.seguro else "[COMENTÁRIO OCULTO: possível dado pessoal]"

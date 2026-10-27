"""
Mascaramento de dados pessoais (CPF, e-mail, telefone) antes de enviar texto à IA.

Regra (AGENTS.md): na dúvida, não envia. Depois de mascarar, se ainda sobrar algo
com cara de documento/telefone (8+ dígitos seguidos) ou um "@", o texto é
considerado inseguro e não sai do sistema. O original nunca é alterado.

Só regex por enquanto; o reconhecimento de nomes/endereços (NER) fica para o
worker de IA do backend.
"""
import re

_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_CPF = re.compile(r"(?<!\d)\d{3}[.\s]?\d{3}[.\s]?\d{3}[-.\s]?\d{2}(?!\d)")
_TELEFONE = re.compile(
    r"(?<!\d)(?:\+?55[\s.-]?)?(?:\(?\d{2}\)?[\s.-]?)?9?\d{4}[\s.-]?\d{4}(?!\d)"
)
# Sobra suspeita: 8+ dígitos só separados por espaço, ponto, hífen ou parênteses
# (datas com "/" e valores com "," não entram)
_SOBRA_SUSPEITA = re.compile(r"\d(?:[\s.()-]?\d){7,}")


def mascarar(texto: str) -> tuple[str, bool]:
    """
    Devolve (texto_mascarado, seguro_para_enviar).
    seguro=False → o texto NÃO deve ser enviado à IA.
    """
    try:
        t = _EMAIL.sub("[EMAIL]", texto)
        t = _CPF.sub("[CPF]", t)
        t = _TELEFONE.sub("[TELEFONE]", t)
    except Exception:
        return "", False
    seguro = "@" not in t and not _SOBRA_SUSPEITA.search(t)
    return t, seguro

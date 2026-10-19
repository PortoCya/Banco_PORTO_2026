"""
Camada de Segurança, RBAC, Rate Limiting e LGPD (Mascaramento de PII e Pseudonimização de IP).
Atende aos requisitos de Segurança e LGPD do PRD NPS KeyCore v1.0.
"""
import base64
import hashlib
import hmac
import json
import re
import secrets
import time
from collections import defaultdict
from typing import Callable, Optional, Tuple

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.errors import (
    ForbiddenError,
    RateLimitExceededError,
    UnauthorizedError,
)
from app.models.models import LogAuditoria, Usuario

bearer_scheme = HTTPBearer(auto_error=False)

# Lista de revogação de tokens em memória (para POST /auth/logout)
_REVOKED_TOKENS: set[str] = set()

# Rate limit em memória: {(ip_hash, bucket): [timestamps]}
_RATE_BUCKETS: dict[Tuple[str, str], list[float]] = defaultdict(list)


# ══════════════════════════════════════════════════════════════════
# 1. HASH FORTE DE SENHA (OWASP PBKDF2-HMAC-SHA256, 310.000 iterações)
# ══════════════════════════════════════════════════════════════════
PBKDF2_ITERATIONS = 310_000


def gerar_senha_hash(senha: str) -> str:
    salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", senha.encode("utf-8"), salt.encode("utf-8"), PBKDF2_ITERATIONS)
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${salt}${dk.hex()}"


def verificar_senha(senha_plana: str, senha_hash: str) -> bool:
    try:
        algoritmo, iteracoes_str, salt, hash_armazenado = senha_hash.split("$", 3)
        if algoritmo != "pbkdf2_sha256":
            return False
        dk = hashlib.pbkdf2_hmac(
            "sha256",
            senha_plana.encode("utf-8"),
            salt.encode("utf-8"),
            int(iteracoes_str),
        )
        return hmac.compare_digest(dk.hex(), hash_armazenado)
    except Exception:
        return False


# ══════════════════════════════════════════════════════════════════
# 2. TOKENS ASSINADOS (JWT HS256 nativo com expiração e revogação)
# ══════════════════════════════════════════════════════════════════
def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding)


def criar_token_acesso(usuario_id: str, papel: str, expira_minutos: Optional[int] = None) -> str:
    exp_min = expira_minutos or settings.ACCESS_TOKEN_EXPIRE_MINUTES
    agora = int(time.time())
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {
        "sub": usuario_id,
        "role": papel,
        "iat": agora,
        "exp": agora + (exp_min * 60),
        "jti": secrets.token_hex(12),
    }
    h_b64 = _b64url_encode(json.dumps(header, separators=(",", ":")).encode("utf-8"))
    p_b64 = _b64url_encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    signing_input = f"{h_b64}.{p_b64}".encode("ascii")
    sig = hmac.new(settings.SECRET_KEY.encode("utf-8"), signing_input, hashlib.sha256).digest()
    return f"{h_b64}.{p_b64}.{_b64url_encode(sig)}"


def decodificar_token_acesso(token: str) -> dict:
    if token in _REVOKED_TOKENS:
        raise UnauthorizedError("Sessão encerrada ou token revogado.")
    try:
        parts = token.split(".")
        if len(parts) != 3:
            raise UnauthorizedError("Formato de token inválido.")
        h_b64, p_b64, s_b64 = parts
        signing_input = f"{h_b64}.{p_b64}".encode("ascii")
        expected_sig = hmac.new(settings.SECRET_KEY.encode("utf-8"), signing_input, hashlib.sha256).digest()
        actual_sig = _b64url_decode(s_b64)
        if not hmac.compare_digest(expected_sig, actual_sig):
            raise UnauthorizedError("Assinatura de token inválida.")
        payload = json.loads(_b64url_decode(p_b64).decode("utf-8"))
        if int(time.time()) >= int(payload.get("exp", 0)):
            raise UnauthorizedError("Token expirado.")
        return payload
    except UnauthorizedError:
        raise
    except Exception:
        raise UnauthorizedError("Token inválido ou corrompido.")


def revogar_token(token: str) -> None:
    _REVOKED_TOKENS.add(token)


# ══════════════════════════════════════════════════════════════════
# 3. DEPENDÊNCIAS DE AUTENTICAÇÃO E RBAC NO BACKEND (RF-001, RF-002)
# ══════════════════════════════════════════════════════════════════
def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> Usuario:
    if not credentials or not credentials.credentials:
        raise UnauthorizedError("Autenticação obrigatória. Envie o header Authorization: Bearer <token>.")
    payload = decodificar_token_acesso(credentials.credentials)
    usuario = db.query(Usuario).filter(Usuario.id == payload.get("sub")).first()
    if not usuario or not usuario.ativo:
        raise UnauthorizedError("Usuário inexistente ou inativo.")
    return usuario


def require_roles(*allowed_roles: str) -> Callable:
    def _role_checker(usuario: Usuario = Depends(get_current_user)) -> Usuario:
        if usuario.papel not in allowed_roles:
            raise ForbiddenError(
                f"Acesso negado. Perfil '{usuario.papel}' não possui permissão para esta operação."
            )
        return usuario
    return _role_checker


# ══════════════════════════════════════════════════════════════════
# 4. RATE LIMITING EM AUTENTICAÇÃO E ENDPOINTS PÚBLICOS (PRD Pág. 9)
# ══════════════════════════════════════════════════════════════════
def rate_limit(bucket: str, max_requests: int = 30, window_seconds: int = 60) -> Callable:
    def _limiter(request: Request) -> None:
        client_ip = request.client.host if request.client else "unknown"
        ip_h = hash_ip(client_ip)
        now = time.time()
        key = (ip_h, bucket)
        timestamps = [t for t in _RATE_BUCKETS[key] if now - t < window_seconds]
        if len(timestamps) >= max_requests:
            raise RateLimitExceededError(
                f"Limite de requisições excedido ({max_requests} por {window_seconds}s). Tente novamente em instantes."
            )
        timestamps.append(now)
        _RATE_BUCKETS[key] = timestamps
    return _limiter


# ══════════════════════════════════════════════════════════════════
# 5. LGPD: PSEUDONIMIZAÇÃO DE IP E MASCARAMENTO DE PII
# ══════════════════════════════════════════════════════════════════
_REGEX_CPF = re.compile(r"\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b")
_REGEX_CNPJ = re.compile(r"\b\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}\b")
_REGEX_EMAIL = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
_REGEX_TELEFONE = re.compile(r"(?:\+?55\s?)?(?:\(?\d{2}\)?\s?)?(?:9\d{4}|\d{4})-?\d{4}\b")


def hash_ip(ip_raw: Optional[str]) -> Optional[str]:
    """Pseudonimiza o endereço IP usando HMAC-SHA256 com SECRET_KEY (LGPD / AuditLog)."""
    if not ip_raw:
        return None
    digest = hmac.new(settings.SECRET_KEY.encode("utf-8"), ip_raw.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"ip_sha256:{digest[:32]}"


def mascarar_pii(texto: Optional[str]) -> Tuple[Optional[str], str]:
    """
    Detecta e mascara PII (CPF, CNPJ, E-mail, Telefone) antes de enviar o comentário para LLMs externas.
    Retorna: (texto_mascarado, status_mascaramento_pii)
    Valores de status: 'NAO_APLICAVEL' | 'MASCARADO' | 'FALHA_MASCARAMENTO_PII'
    """
    if not texto or not texto.strip():
        return texto, "NAO_APLICAVEL"
    try:
        original = texto
        mascarado = _REGEX_CPF.sub("[CPF_MASCARADO]", original)
        mascarado = _REGEX_CNPJ.sub("[CNPJ_MASCARADO]", mascarado)
        mascarado = _REGEX_EMAIL.sub("[EMAIL_MASCARADO]", mascarado)
        mascarado = _REGEX_TELEFONE.sub("[TELEFONE_MASCARADO]", mascarado)
        status_pii = "MASCARADO" if mascarado != original else "NAO_APLICAVEL"
        return mascarado, status_pii
    except Exception:
        return None, "FALHA_MASCARAMENTO_PII"


def sanitizar_texto(texto: Optional[str]) -> Optional[str]:
    """Remove tags HTML/script maliciosas (proteção contra XSS armazenado)."""
    if texto is None:
        return None
    limpo = re.sub(r"<\s*script[^>]*>.*?<\s*/\s*script\s*>", "", texto, flags=re.IGNORECASE | re.DOTALL)
    limpo = re.sub(r"<[^>]+>", "", limpo)
    return limpo.strip()


# ══════════════════════════════════════════════════════════════════
# 6. AUDITORIA SEGURA (RF-020 — Sem vazar secrets/senhas)
# ══════════════════════════════════════════════════════════════════
_CAMPOS_SENSIVEIS = {"senha", "senha_hash", "password", "token", "secret"}


def _limpar_estado_auditoria(dados: Optional[dict]) -> Optional[dict]:
    if not dados:
        return None
    return {
        k: ("[REDACTED]" if k.lower() in _CAMPOS_SENSIVEIS else v)
        for k, v in dados.items()
    }


def registrar_auditoria(
    db: Session,
    id_usuario_ator: Optional[str],
    acao: str,
    tipo_entidade: str,
    id_entidade: str,
    estado_antes: Optional[dict] = None,
    estado_depois: Optional[dict] = None,
) -> LogAuditoria:
    log = LogAuditoria(
        id_usuario_ator=id_usuario_ator,
        acao=acao,
        tipo_entidade=tipo_entidade,
        id_entidade=id_entidade,
        estado_antes=_limpar_estado_auditoria(estado_antes),
        estado_depois=_limpar_estado_auditoria(estado_depois),
    )
    db.add(log)
    return log

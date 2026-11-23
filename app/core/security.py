"""
Segurança: hash de senha (Argon2id), tokens JWT e pseudonimização de IP.
"""
import hashlib
import hmac
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

from app.core.config import settings

# PasswordHasher usa Argon2id por padrão (parâmetros recomendados pela RFC 9106)
_hasher = PasswordHasher()

# Hash de uma senha qualquer, usado quando o e-mail não existe: o login leva o
# mesmo tempo nos dois casos e não revela quais e-mails estão cadastrados.
_HASH_FICTICIO = _hasher.hash("senha-ficticia-para-tempo-constante")


# ─── Senhas ──────────────────────────────────────────────────────────────────

def gerar_hash_senha(senha: str) -> str:
    return _hasher.hash(senha)


def verificar_senha(senha: str, senha_hash: Optional[str]) -> bool:
    """Retorna True se a senha confere. Nunca lança exceção."""
    try:
        return _hasher.verify(senha_hash or _HASH_FICTICIO, senha) and senha_hash is not None
    except (VerificationError, InvalidHashError):
        return False


def precisa_rehash(senha_hash: str) -> bool:
    """True se o hash foi gerado com parâmetros mais fracos que os atuais."""
    return _hasher.check_needs_rehash(senha_hash)


# ─── JWT ─────────────────────────────────────────────────────────────────────

def criar_token_acesso(id_usuario: uuid.UUID) -> str:
    agora = datetime.now(timezone.utc)
    payload = {
        "sub": str(id_usuario),
        "iat": agora,
        "exp": agora + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decodificar_token(token: str) -> Optional[uuid.UUID]:
    """Valida assinatura e expiração. Retorna o id do usuário ou None."""
    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM],
            options={"require": ["sub", "iat", "exp"]},
        )
        return uuid.UUID(payload["sub"])
    except (jwt.PyJWTError, ValueError, TypeError, AttributeError):
        return None


# ─── LGPD ────────────────────────────────────────────────────────────────────

def hash_ip(ip: Optional[str]) -> Optional[str]:
    """Pseudonimiza o IP (HMAC-SHA256 com a SECRET_KEY) antes de gravar."""
    if not ip:
        return None
    return hmac.new(settings.SECRET_KEY.encode(), ip.encode(), hashlib.sha256).hexdigest()

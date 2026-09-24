"""
Configurações da aplicação via variáveis de ambiente (Pydantic Settings).
"""
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # ── App ──────────────────────────────────────────────────────────────────
    APP_NAME: str = "AI Consulting Platform"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False

    # ── Banco de dados ───────────────────────────────────────────────────────
    DATABASE_URL: str = "sqlite:///./ai_consulting.db"
    DB_ECHO: bool = False          # True → loga SQL no console

    # ── Segurança ────────────────────────────────────────────────────────────
    SECRET_KEY: str = "TROQUE_ESTA_CHAVE_EM_PRODUCAO"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    ALGORITHM: str = "HS256"

    # ── IA / OpenAI ──────────────────────────────────────────────────────────
    OPENAI_API_KEY: Optional[str] = None
    OPENAI_MODEL: str = "gpt-4o"
    OPENAI_TIMEOUT_SECONDS: int = 30
    OPENAI_MAX_RETRIES: int = 3

    # ── Limites ──────────────────────────────────────────────────────────────
    MAX_TOKENS_RESPONSE: int = 2048
    REQUEST_TIMEOUT_SECONDS: int = 60


settings = Settings()

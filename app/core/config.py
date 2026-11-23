"""
Configurações da aplicação via variáveis de ambiente (Pydantic Settings).

Segredos nunca têm valor padrão aqui: vêm do ambiente (.env fora do git).
"""
from typing import Literal, Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # ── App ──────────────────────────────────────────────────────────────────
    APP_NAME: str = "NPS KeyCore"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False

    # ── Banco de dados ───────────────────────────────────────────────────────
    # Produção: postgresql+psycopg://usuario:senha@host:5432/banco
    DATABASE_URL: str = "sqlite:///./nps_keycore.db"
    # Usuário de banco do worker de IA (só escreve nas tabelas de IA).
    # Sem valor, o worker usa DATABASE_URL (aceitável apenas em desenvolvimento).
    WORKER_DATABASE_URL: Optional[str] = None
    DB_ECHO: bool = False
    DB_POOL_SIZE: int = Field(10, ge=1, le=200)
    DB_MAX_OVERFLOW: int = Field(10, ge=0, le=200)
    # Espera curta por conexão livre: saturou, responde 429 em vez de empilhar
    DB_POOL_TIMEOUT_SEGUNDOS: int = Field(5, ge=1, le=60)
    DB_POOL_RECYCLE_SEGUNDOS: int = Field(1800, ge=60)
    DB_CONNECT_TIMEOUT_SEGUNDOS: int = Field(5, ge=1, le=60)
    DB_STATEMENT_TIMEOUT_MS: int = Field(15_000, ge=100)
    DB_LOCK_TIMEOUT_MS: int = Field(5_000, ge=100)

    # ── Redis (fila da IA, rate limit, contador de custo) ────────────────────
    # Opcional: sem Redis o rate limit fica em memória (por processo) e o
    # worker encontra os jobs varrendo a tabela JOB_IA.
    REDIS_URL: Optional[str] = None
    REDIS_TIMEOUT_SEGUNDOS: float = Field(2.0, gt=0, le=30)

    # ── Segurança ────────────────────────────────────────────────────────────
    # Sem valor padrão: a aplicação não sobe sem SECRET_KEY no ambiente.
    # Gere com: openssl rand -hex 32
    SECRET_KEY: str = Field(..., min_length=32)
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(60, ge=1, le=1440)
    ALGORITHM: Literal["HS256"] = "HS256"

    # ── Rate limit (janela deslizante) ───────────────────────────────────────
    LOGIN_JANELA_SEGUNDOS: int = Field(900, ge=1)          # 15 min
    LOGIN_MAX_TENTATIVAS_IP: int = Field(20, ge=1)         # qualquer tentativa, por IP
    LOGIN_MAX_FALHAS_EMAIL: int = Field(5, ge=1)           # só falhas, por e-mail
    PUBLICO_JANELA_SEGUNDOS: int = Field(60, ge=1)
    PUBLICO_MAX_LEITURAS_IP: int = Field(60, ge=1)         # GET /public/respostas/{token}
    PUBLICO_MAX_ENVIOS_IP: int = Field(20, ge=1)           # POST /public/respostas/{token}

    # ── HTTP ─────────────────────────────────────────────────────────────────
    # Lista separada por vírgula. Nunca "*" junto com credenciais.
    CORS_ORIGINS: str = "http://localhost:3000"
    MAX_PAYLOAD_BYTES: int = Field(64 * 1024, ge=1024)
    # Cookie antiduplicidade do link ABERTO. Em produção (HTTPS) mantenha true.
    COOKIE_SECURE: bool = True

    @field_validator("CORS_ORIGINS")
    @classmethod
    def _sem_curinga(cls, v: str) -> str:
        # A API responde com credenciais (cookie do link ABERTO): com "*" o
        # navegador de qualquer site poderia chamar a API em nome do usuário.
        if "*" in v:
            raise ValueError('CORS_ORIGINS não aceita "*": liste as origens do front.')
        return v

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    # ── Camada de IA (usada só pelo worker) ──────────────────────────────────
    # Endpoint compatível com a API de chat completions (OpenAI, Gemini...).
    IA_BASE_URL: str = "https://generativelanguage.googleapis.com/v1beta/openai"
    IA_API_KEY: Optional[str] = None
    IA_TIMEOUT_CONEXAO_SEGUNDOS: float = Field(5.0, gt=0, le=60)
    IA_TIMEOUT_RESPOSTA_SEGUNDOS: float = Field(30.0, gt=0, le=300)
    IA_MAX_TOKENS_RESPOSTA: int = Field(300, ge=50, le=4000)
    IA_MAX_TENTATIVAS: int = Field(5, ge=1, le=20)
    IA_BACKOFF_BASE_SEGUNDOS: int = Field(30, ge=1)
    IA_BACKOFF_MAX_SEGUNDOS: int = Field(3600, ge=1)
    # Job em PROCESSANDO há mais tempo que isso é considerado órfão e reprocessado
    IA_LEASE_SEGUNDOS: int = Field(300, ge=30)
    IA_CONFIANCA_MINIMA: float = Field(0.6, ge=0, le=1)
    # Custo (mesma moeda do limite) por 1.000 tokens; alimenta o circuit breaker
    IA_CUSTO_1K_TOKENS_ENTRADA: float = Field(0.0, ge=0)
    IA_CUSTO_1K_TOKENS_SAIDA: float = Field(0.0, ge=0)
    IA_LIMITE_CUSTO_PADRAO: float = Field(50.0, ge=0)
    GOLDEN_SET_MINIMO: int = Field(100, ge=1)


settings = Settings()

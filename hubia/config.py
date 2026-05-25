"""Application configuration via pydantic-settings."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables and .env file."""

    # Server
    host: str = "0.0.0.0"
    port: int = 8089
    debug: bool = False

    # Database
    database_url: str = "sqlite+aiosqlite:///./hubia.db"

    # Auth
    secret_key: str = "change-me"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60

    # Encryption
    encryption_key: str = ""  # Fernet key, generate with cryptography.fernet

    # CORS — allow frontend dev servers and production origins
    cors_origins: list[str] = [
        "http://localhost:3000",
        "http://localhost:8089",
        "http://127.0.0.1:8089",
        "http://localhost:5173",
        "http://0.0.0.0:8089",
        "http://127.0.0.1:8089",
    ]

    # Provider defaults
    meta_ai_doc_ids: dict[str, str] = {
        "muse-spark": "25010949351905993",
    }
    qwen_default_model: str = "qwen3.7-max"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


settings = Settings()  # type: ignore[call-arg]

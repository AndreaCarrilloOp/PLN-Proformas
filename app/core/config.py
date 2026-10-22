from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "PLN Proformas"
    app_env: str = "development"
    app_version: str = "1.1.0"
    debug: bool = False
    enable_docs: bool = True
    auth_enabled: bool = True

    database_url: str
    auto_create_tables: bool = True
    seed_on_startup: bool = True

    session_secret: str = "local-dev-session-secret-change-me"
    session_cookie_name: str = "pln_session"
    session_cookie_secure: bool = False
    session_ttl_minutes: int = Field(default=480, ge=15, le=10080)
    local_auth_username: str | None = None
    local_auth_password: str | None = None
    local_auth_display_name: str = "Usuario local"

    max_pdf_mb: int = Field(default=5, ge=1, le=20)
    cors_origins: str = ""

    smtp_fernet_key: str | None = None  # clave Fernet distinta del secreto de sesión
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_user: str | None = None
    smtp_password: str | None = None
    smtp_from: str | None = None
    smtp_use_tls: bool = True

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def cors_origin_list(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]

    @property
    def sqlalchemy_database_url(self) -> str:
        """Use psycopg 3 even when a provider returns a plain postgresql:// URL."""
        if self.database_url.startswith("postgresql://"):
            return self.database_url.replace("postgresql://", "postgresql+psycopg://", 1)
        return self.database_url


@lru_cache
def get_settings() -> Settings:
    return Settings()

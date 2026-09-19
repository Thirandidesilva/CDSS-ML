"""App settings, sourced from environment / .env — never hardcoded connection strings or secrets."""
from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # pydantic-settings reads these from a .env file (see .env.example) or real
    # environment variables — field names map to env vars case-insensitively
    # (database_url <-> DATABASE_URL).
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str  # required — no default, so a missing .env fails loudly at startup
    jwt_secret: str     # required — signs/verifies every access + reset token
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60
    reset_token_expire_minutes: int = 15
    reports_dir: str = "reports/generated"  # gitignored — rendered vet-report PDFs live here


@lru_cache
def get_settings() -> Settings:
    # Cached so Settings() — and its .env read — only runs once per process, not once
    # per request; every caller shares the same instance.
    return Settings()

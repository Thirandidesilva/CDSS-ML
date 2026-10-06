"""App settings, sourced from environment / .env — never hardcoded connection strings or secrets."""
from __future__ import annotations

from functools import lru_cache
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # pydantic-settings reads these from a .env file (see .env.example) or real
    # environment variables — field names map to env vars case-insensitively
    # (database_url <-> DATABASE_URL).
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str  # required — no default, so a missing .env fails loudly at startup
    jwt_secret: str     # required — signs/verifies every access + reset token
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    # How long a refresh token (which renews the access token above) stays usable. Each
    # refresh issues a new one, so this is the longest a user can stay away and remain
    # signed in.
    refresh_token_expire_days: int = 30
    reset_token_expire_minutes: int = 15

    # "pool" keeps SQLAlchemy's own connection pool (normal server, e.g. Render). "null"
    # opens a connection per request and closes it afterwards, for a serverless host where
    # each instance is short-lived and the database is reached through Supabase's
    # transaction pooler (port 6543), which does the real pooling.
    db_pool_mode: str = "pool"

    # Resend's HTTP API (not SMTP — avoids the port/implicit-TLS mismatches SMTP hit).
    # Required (no default): fail loudly at startup if unconfigured, same as
    # database_url/jwt_secret. The "from" address must be either Resend's sandbox
    # sender (onboarding@resend.dev — only deliverable to the Resend account's own
    # email) or an address on a domain verified in that Resend account; no address on a
    # domain you don't control (e.g. gmail.com) will ever work, on SMTP or the API.
    resend_api_key: str
    email_from_address: str

    # Public https URL of the Pawsitivity logo PNG (Cloudinary) shown in the HTML email
    # header. Optional: without it the emails render with no logo.
    email_logo_url: Optional[str] = None

    otp_expire_minutes: int = 10
    otp_max_attempts: int = 5

    # Cloudinary hosts profile photos. A base64 photo sent in `profile_picture` on
    # users/update and dogs/create|update is uploaded from the server (services/cloudinary.py),
    # so the API secret never leaves it. Optional (unlike the settings above) so a deployment
    # that hasn't set them yet still boots — only a request that actually carries a photo
    # fails, with business code 5001.
    cloudinary_cloud_name: Optional[str] = None
    cloudinary_api_key: Optional[str] = None
    cloudinary_api_secret: Optional[str] = None


@lru_cache
def get_settings() -> Settings:
    # Cached so Settings() — and its .env read — only runs once per process, not once
    # per request; every caller shares the same instance.
    return Settings()

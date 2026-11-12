"""Application settings.

All configuration comes from environment variables prefixed ``UPTIVORA_``. Any setting can
instead be read from a file by setting ``UPTIVORA_<NAME>_FILE`` (Docker secrets pattern), e.g.
``UPTIVORA_SECRET_KEY_FILE=/run/secrets/secret_key``.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ENV_PREFIX = "UPTIVORA_"
_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}
_INSECURE_SECRET_MARKERS = ("change-me", "changeme", "dev-only")


def _file_secrets_source() -> dict[str, Any]:
    """Load ``UPTIVORA_X_FILE`` variables as setting ``x``."""
    values: dict[str, Any] = {}
    for key, path in os.environ.items():
        if key.startswith(ENV_PREFIX) and key.endswith("_FILE") and path:
            field = key[len(ENV_PREFIX) : -len("_FILE")].lower()
            values[field] = Path(path).read_text(encoding="utf-8").strip()
    return values


def is_local_host(host: str | None) -> bool:
    if not host:
        return False
    host = host.lower().strip("[]")
    return host in _LOCAL_HOSTS or host.endswith(".localhost") or host.endswith(".test")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix=ENV_PREFIX, env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    env: Literal["development", "test", "production"] = "production"
    edition: Literal["hosted", "selfhosted"] = "selfhosted"
    version: str = "0.1.0"

    secret_key: SecretStr = Field(default=SecretStr(""))
    database_url: str = "postgresql+asyncpg://uptivora:uptivora@localhost:5433/uptivora"
    db_pool_size: int = Field(default=10, ge=1, le=100)

    # Public base URL of the web app, used in emails and Origin checks.
    public_url: str = "http://localhost:3000"

    # SMTP
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: SecretStr = Field(default=SecretStr(""))
    smtp_security: Literal["starttls", "tls", "none"] = "starttls"
    smtp_from: str = "Uptivora <alerts@localhost>"
    smtp_timeout_seconds: int = 20

    # Billing (hosted edition only)
    billing_provider: Literal["disabled", "test", "stripe"] = "disabled"
    allow_test_billing_in_production: bool = False

    # Licensing (self-hosted edition)
    license_path: Path | None = None
    dev_key_dir: Path = Path(__file__).resolve().parents[2] / ".dev-keys"

    # Monitoring engine
    worker_concurrency: int = Field(default=50, ge=1, le=1000)
    raw_retention_days: int = Field(default=30, ge=1, le=3650)
    rollup_retention_days: int = Field(default=400, ge=30, le=3650)
    monitor_user_agent: str = "UptivoraBot/0.1 (+https://uptivora.com/bot)"

    @classmethod
    def settings_customise_sources(
        cls, settings_cls, init_settings, env_settings, dotenv_settings, file_secret_settings
    ):
        # Precedence: explicit init > env var > *_FILE secret > .env file
        return (init_settings, env_settings, _file_secrets_source, dotenv_settings)

    @model_validator(mode="after")
    def _check_environment(self) -> Settings:
        public = urlsplit(self.public_url)
        if public.scheme not in ("http", "https") or not public.hostname:
            raise ValueError("UPTIVORA_PUBLIC_URL must be an absolute http(s) URL")

        if self.env == "production":
            secret = self.secret_key.get_secret_value()
            if len(secret) < 32 or any(m in secret.lower() for m in _INSECURE_SECRET_MARKERS):
                raise ValueError("UPTIVORA_SECRET_KEY must be a random value of >= 32 characters")
            if public.scheme != "https" and not is_local_host(public.hostname):
                raise ValueError("UPTIVORA_PUBLIC_URL must use https in production")
            if self.billing_provider == "test" and not self.allow_test_billing_in_production:
                raise ValueError(
                    "Test-mode billing is refused in production. Set "
                    "UPTIVORA_ALLOW_TEST_BILLING_IN_PRODUCTION=true only on a staging system."
                )
        else:
            # Development/test mode trusts the local dev licence key and relaxes cookies.
            # Refuse to run that way on a public hostname so it cannot be used in production.
            if not is_local_host(public.hostname):
                raise ValueError(
                    f"UPTIVORA_ENV={self.env} is only allowed with a local UPTIVORA_PUBLIC_URL "
                    "(localhost, 127.0.0.1, *.localhost, *.test)"
                )
            if not self.secret_key.get_secret_value():
                self.secret_key = SecretStr("insecure-development-secret-key-not-for-production")

        if self.edition == "selfhosted" and self.billing_provider != "disabled":
            raise ValueError("Billing is only available in the hosted edition")
        if self.billing_provider == "stripe":
            raise ValueError("The Stripe provider is not implemented yet; use 'test' or 'disabled'")
        return self

    @property
    def is_production(self) -> bool:
        return self.env == "production"

    @property
    def is_hosted(self) -> bool:
        return self.edition == "hosted"

    @property
    def billing_test_mode(self) -> bool:
        return self.billing_provider == "test"


@lru_cache
def get_settings() -> Settings:
    return Settings()

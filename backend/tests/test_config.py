from pathlib import Path

import pytest
from pydantic import ValidationError

from app.core.config import Settings

STRONG = "q8Zr3xV7mK2pW9nB4tY6uJ1cL5hD0sFgAeRw"


def make(**kw) -> Settings:
    kw.setdefault("billing_provider", "disabled")
    kw.setdefault("edition", "selfhosted")
    return Settings(_env_file=None, **kw)


def test_production_requires_strong_secret() -> None:
    with pytest.raises(ValidationError, match="SECRET_KEY"):
        make(env="production", public_url="https://app.uptivora.com", secret_key="short")
    with pytest.raises(ValidationError, match="SECRET_KEY"):
        make(
            env="production",
            public_url="https://app.uptivora.com",
            secret_key="dev-only-change-me-dev-only-change-me-0000",
        )


def test_production_requires_https() -> None:
    with pytest.raises(ValidationError, match="https"):
        make(env="production", public_url="http://app.uptivora.com", secret_key=STRONG)


def test_production_refuses_test_billing_unless_opted_in() -> None:
    kw = dict(
        env="production",
        edition="hosted",
        public_url="https://app.uptivora.com",
        secret_key=STRONG,
        billing_provider="test",
    )
    with pytest.raises(ValidationError, match="Test-mode billing"):
        make(**kw)
    assert make(**kw, allow_test_billing_in_production=True).billing_test_mode


def test_development_mode_refused_on_public_host() -> None:
    with pytest.raises(ValidationError, match="only allowed with a local"):
        make(env="development", public_url="https://monitor.customer.com")
    assert make(env="development", public_url="http://uptivora.localhost:3000").env == "development"


def test_selfhosted_cannot_enable_billing() -> None:
    with pytest.raises(ValidationError, match="hosted edition"):
        make(env="test", edition="selfhosted", billing_provider="test")


def test_stripe_not_yet_available() -> None:
    with pytest.raises(ValidationError, match="Stripe"):
        make(env="test", edition="hosted", billing_provider="stripe")


def test_file_secrets(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    secret = tmp_path / "secret_key"
    secret.write_text(STRONG + "\n")
    monkeypatch.delenv("UPTIVORA_SECRET_KEY", raising=False)
    monkeypatch.setenv("UPTIVORA_SECRET_KEY_FILE", str(secret))
    s = make(env="production", public_url="https://app.uptivora.com")
    assert s.secret_key.get_secret_value() == STRONG


def test_secret_not_in_repr() -> None:
    s = make(env="production", public_url="https://app.uptivora.com", secret_key=STRONG)
    assert STRONG not in repr(s)

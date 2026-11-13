"""Production readiness checks (python -m app.cli preflight)."""

from __future__ import annotations

import pytest

from app import preflight


def _by_name(results):
    return {r.name: r for r in results}


async def test_preflight_flags_unsafe_configuration(
    migrated_db_url, settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "trusted_proxies", ["0.0.0.0/0"])
    monkeypatch.setattr(settings, "smtp_host", "")
    monkeypatch.setattr(settings, "edition", "selfhosted")
    monkeypatch.setattr(preflight, "PRODUCTION_PUBLIC_KEYS", {})
    r = _by_name(await preflight.run_checks(settings))
    assert r["Public URL"].level == "FAIL"  # tests run on http://localhost
    assert r["Trusted proxies"].level == "FAIL"
    assert r["SMTP"].level == "FAIL"
    assert r["Licence keys"].level == "FAIL"
    assert r["Database schema"].level == "PASS"
    assert r["Check partitions"].level == "PASS"
    assert "FAIL" in preflight.render(list(r.values()))


async def test_preflight_passes_a_good_hosted_setup(
    migrated_db_url, settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "public_url", "https://app.uptivora.example")
    monkeypatch.setattr(settings, "network_canaries", ["https://www.example.org/"])
    monkeypatch.setattr(settings, "heartbeat_url", "https://hc.example.org/ping/x")
    r = _by_name(await preflight.run_checks(settings))
    for name in (
        "Public URL",
        "Secret key",
        "Trusted proxies",
        "Database schema",
        "SMTP",
        "Alert-storm guard",
        "External heartbeat",
    ):
        assert r[name].level == "PASS", (name, r[name].detail)

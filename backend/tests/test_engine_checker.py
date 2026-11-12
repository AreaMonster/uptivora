"""Check executor against real local HTTP/HTTPS servers, including SSRF scenarios."""

from __future__ import annotations

import asyncio
import ipaddress
import socket
import time

import pytest

from app.core import netguard
from app.engine.checker import CheckSpec, run_check
from app.engine.netclient import build_clients
from tests.localserver import LocalServer, make_self_signed

# Captured before the autouse fake_dns fixture patches the module attribute.
REAL_RESOLVE = netguard.resolve_public_addresses
UA = "UptivoraBot/test"

# Test-only resolver: these public-looking names point at the local test server. Any other
# name, or any other private address, is refused exactly like in production.
LOOPBACK_TEST_HOSTS = {"site.example.com", "secure.example.com", "other.example.com"}


async def local_resolver(host: str, port: int):
    if host in LOOPBACK_TEST_HOSTS:
        return [ipaddress.ip_address("127.0.0.1")]
    return await REAL_RESOLVE(host, port)


@pytest.fixture
async def clients():
    c = build_clients(resolver=local_resolver)
    yield c
    await c.aclose()


@pytest.fixture
def server():
    with LocalServer() as s:
        yield s


@pytest.fixture
def tls_server(tmp_path):
    not_after = make_self_signed(tmp_path, "secure.example.com")
    with LocalServer(tls_dir=tmp_path) as s:
        s.not_after = not_after
        yield s


def spec(url: str, **kw) -> CheckSpec:
    return CheckSpec(url=url, **kw)


async def test_up(clients, server) -> None:
    out = await run_check(clients, spec(server.url("site.example.com", "/ok")), UA)
    assert out.is_up and out.status_code == 200 and out.error_kind is None
    assert out.response_ms is not None and out.response_ms < 5000
    assert server.hits == [("GET", "/ok")]


async def test_unexpected_status(clients, server) -> None:
    out = await run_check(clients, spec(server.url("site.example.com", "/status/503")), UA)
    assert not out.is_up and out.status_code == 503 and out.error_kind == "http_status"
    assert "503 Service Unavailable" in out.error_message and "200-399" in out.error_message
    custom = await run_check(
        clients, spec(server.url("site.example.com", "/status/404"), expected_status="404"), UA
    )
    assert custom.is_up


async def test_keyword(clients, server) -> None:
    url = server.url("site.example.com", "/ok")
    assert (await run_check(clients, spec(url, keyword="Hello Uptivora"), UA)).is_up
    missing = await run_check(clients, spec(url, keyword="Out of stock"), UA)
    assert missing.error_kind == "keyword_missing" and missing.status_code == 200


async def test_head_method(clients, server) -> None:
    out = await run_check(clients, spec(server.url("site.example.com", "/ok"), method="HEAD"), UA)
    assert out.is_up and server.hits == [("HEAD", "/ok")]


async def test_timeout_is_enforced(clients, server) -> None:
    started = time.monotonic()
    out = await run_check(
        clients, spec(server.url("site.example.com", "/slow"), timeout_seconds=1), UA
    )
    assert out.error_kind == "timeout" and not out.is_up
    assert time.monotonic() - started < 2.5


async def test_connection_refused(clients) -> None:
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    out = await run_check(clients, spec(f"http://site.example.com:{port}/"), UA)
    assert out.error_kind == "connection_error"


async def test_redirects(clients, server) -> None:
    ok = await run_check(clients, spec(server.url("site.example.com", "/redirect/ok")), UA)
    assert ok.is_up and ok.final_url.endswith("/ok")
    no_follow = await run_check(
        clients, spec(server.url("site.example.com", "/redirect/ok"), follow_redirects=False), UA
    )
    assert no_follow.is_up and no_follow.status_code == 302  # 3xx is expected by default
    loop = await run_check(clients, spec(server.url("site.example.com", "/redirect/loop")), UA)
    assert loop.error_kind == "too_many_redirects"
    see_other = await run_check(
        clients, spec(server.url("site.example.com", "/redirect/see-other"), method="HEAD"), UA
    )
    assert see_other.is_up and server.hits[-1] == ("GET", "/ok")


async def test_redirect_to_private_network_is_blocked(clients, server) -> None:
    for path in ("/redirect/private", "/redirect/internal"):
        out = await run_check(clients, spec(server.url("site.example.com", path)), UA)
        assert out.error_kind == "blocked", path
    server.set_redirect_target("http://169.254.169.254/latest/meta-data/")
    meta = await run_check(clients, spec(server.url("site.example.com", "/redirect/target")), UA)
    assert meta.error_kind == "blocked"
    # Only the initial requests reached our server; nothing was sent anywhere private.
    assert all(p.startswith("/redirect/") for _, p in server.hits)


async def test_dns_rebinding_to_loopback_is_blocked(server, monkeypatch) -> None:
    """A public-looking name that resolves to 127.0.0.1 must never be dialled (production
    resolver, real address check)."""

    async def fake_getaddrinfo(host, port, **_kw):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", port))]

    monkeypatch.setattr(asyncio.get_running_loop(), "getaddrinfo", fake_getaddrinfo)
    prod_clients = build_clients(resolver=REAL_RESOLVE)
    try:
        out = await run_check(prod_clients, spec(server.url("evil.example.com", "/ok")), UA)
    finally:
        await prod_clients.aclose()
    assert out.error_kind == "blocked" and "private or reserved" in out.error_message
    assert server.hits == []  # the request never reached the local server


async def test_mixed_dns_answer_is_blocked(server, monkeypatch) -> None:
    async def fake_getaddrinfo(host, port, **_kw):
        return [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.215.14", port)),
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", port)),
        ]

    monkeypatch.setattr(asyncio.get_running_loop(), "getaddrinfo", fake_getaddrinfo)
    prod_clients = build_clients(resolver=REAL_RESOLVE)
    try:
        out = await run_check(prod_clients, spec(server.url("mixed.example.com", "/ok")), UA)
    finally:
        await prod_clients.aclose()
    assert out.error_kind == "blocked" and server.hits == []


async def test_tls_certificate_captured_when_not_verifying(clients, tls_server) -> None:
    out = await run_check(
        clients, spec(tls_server.url("secure.example.com", "/ok"), verify_tls=False), UA
    )
    assert out.is_up and out.tls is not None
    assert out.tls.expires_at == tls_server.not_after
    assert "Uptivora Test CA" in out.tls.issuer and out.tls.subject == "secure.example.com"


async def test_untrusted_certificate_fails_when_verifying(clients, tls_server) -> None:
    out = await run_check(clients, spec(tls_server.url("secure.example.com", "/ok")), UA)
    assert out.error_kind == "tls_error" and out.tls_error and not out.is_up


async def test_https_to_http_downgrade_rejected(clients, tls_server, server) -> None:
    tls_server.set_redirect_target(server.url("site.example.com", "/ok"))
    out = await run_check(
        clients,
        spec(tls_server.url("secure.example.com", "/redirect/target"), verify_tls=False),
        UA,
    )
    assert out.error_kind == "insecure_redirect" and server.hits == []


async def test_user_agent_sent(clients, server) -> None:
    seen = {}
    orig = server.httpd.RequestHandlerClass.do_GET

    def capture(handler):
        seen["ua"] = handler.headers.get("User-Agent")
        orig(handler)

    server.httpd.RequestHandlerClass.do_GET = capture
    try:
        await run_check(clients, spec(server.url("site.example.com", "/ok")), UA)
    finally:
        server.httpd.RequestHandlerClass.do_GET = orig
    assert seen["ua"] == UA

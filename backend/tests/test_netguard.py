import ipaddress
import socket

import pytest

from app.core import netguard
from app.core.netguard import (
    UnsafeURLError,
    is_public_ip,
    resolve_public_addresses,
    validate_monitor_url,
)


@pytest.mark.parametrize(
    "ip",
    [
        "127.0.0.1",
        "127.255.255.254",
        "10.0.0.1",
        "172.16.5.4",
        "172.31.255.255",
        "192.168.1.1",
        "169.254.169.254",
        "100.64.0.1",
        "0.0.0.0",
        "0.1.2.3",
        "224.0.0.1",
        "239.255.255.250",
        "240.0.0.1",
        "255.255.255.255",
        "192.0.2.10",
        "198.18.0.1",
        "198.51.100.7",
        "203.0.113.9",
        "192.0.0.8",
        "::1",
        "::",
        "fe80::1",
        "fc00::1",
        "fd12:3456::1",
        "ff02::1",
        "::ffff:127.0.0.1",
        "::ffff:10.0.0.1",
        "::ffff:169.254.169.254",
        "64:ff9b::7f00:1",
        "64:ff9b::808:808",
        "2002:7f00:1::",
        "2001:db8::1",
        "2001::1",
        "::127.0.0.1",
        "fec0::1",
    ],
)
def test_non_public_addresses_rejected(ip: str) -> None:
    assert not is_public_ip(ipaddress.ip_address(ip))


@pytest.mark.parametrize(
    "ip",
    [
        "8.8.8.8",
        "1.1.1.1",
        "93.184.215.14",
        "2606:4700:4700::1111",
        "2001:4860:4860::8888",
        "::ffff:8.8.8.8",
    ],
)
def test_public_addresses_allowed(ip: str) -> None:
    assert is_public_ip(ipaddress.ip_address(ip))


@pytest.mark.parametrize(
    ("url", "code"),
    [
        ("", "invalid_url"),
        ("ftp://example.com/", "invalid_scheme"),
        ("file:///etc/passwd", "invalid_scheme"),
        ("gopher://example.com", "invalid_scheme"),
        ("javascript:alert(1)", "invalid_scheme"),
        ("http://localhost/", "invalid_host"),  # single label
        ("http://localhost.localdomain/", "blocked_host"),
        ("http://foo.localhost/", "blocked_host"),
        ("http://printer.local/", "blocked_host"),
        ("http://metadata.google.internal/", "blocked_host"),
        ("http://api.svc.cluster.local/", "blocked_host"),
        ("http://127.0.0.1/", "blocked_address"),
        ("http://[::1]/", "blocked_address"),
        ("http://[::ffff:127.0.0.1]/", "blocked_address"),
        ("http://169.254.169.254/latest/meta-data/", "blocked_address"),
        ("http://10.1.2.3:8080/", "blocked_address"),
        ("http://2130706433/", "invalid_host"),  # decimal 127.0.0.1
        ("http://0x7f.0.0.1/", "invalid_host"),  # hex
        ("http://127.1/", "invalid_host"),  # short form
        ("http://017700000001/", "invalid_host"),  # octal
        ("http://user:pass@example.com/", "invalid_url"),
        ("http://example.com@127.0.0.1/", "invalid_url"),
        ("http://example.com:22/", "blocked_port"),
        ("http://example.com:6379/", "blocked_port"),
        ("http://example.com:8/", "blocked_port"),
        ("http://example.com:99999/", "invalid_url"),
        ("http://exa mple.com/", "invalid_url"),
        ("http://example.com/\r\nHost: evil", "invalid_url"),
        ("http://example.com\\@127.0.0.1/", "invalid_url"),
        ("http://-bad-.com/", "invalid_host"),
        ("http://" + "a" * 2050 + ".com/", "invalid_url"),
    ],
)
def test_unsafe_urls_rejected(url: str, code: str) -> None:
    with pytest.raises(UnsafeURLError) as exc:
        validate_monitor_url(url)
    assert exc.value.code == code


def test_valid_url_normalised() -> None:
    safe = validate_monitor_url("  HTTPS://Example.COM./status?x=1#frag ")
    assert safe.url == "https://example.com/status?x=1"
    assert (safe.host, safe.port, safe.scheme) == ("example.com", 443, "https")


def test_idn_and_custom_port() -> None:
    safe = validate_monitor_url("http://bücher.ch:8080")
    assert safe.host == "xn--bcher-kva.ch"
    assert safe.url == "http://xn--bcher-kva.ch:8080/"


def test_public_ip_literal_allowed() -> None:
    assert (
        validate_monitor_url("http://[2606:4700:4700::1111]/").url
        == "http://[2606:4700:4700::1111]/"
    )


async def test_resolution_to_loopback_is_blocked() -> None:
    with pytest.raises(UnsafeURLError) as exc:
        await resolve_public_addresses("localhost", 80)
    assert exc.value.code == "blocked_address"


async def test_mixed_public_and_private_records_blocked(monkeypatch: pytest.MonkeyPatch) -> None:
    """A DNS answer containing ANY private address must be refused (rebinding defence)."""

    async def fake_getaddrinfo(host, port, **_kw):
        return [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.215.14", port)),
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.5", port)),
        ]

    loop = __import__("asyncio").get_running_loop()
    monkeypatch.setattr(loop, "getaddrinfo", fake_getaddrinfo)
    with pytest.raises(UnsafeURLError) as exc:
        await resolve_public_addresses("rebind.example.com", 443)
    assert exc.value.code == "blocked_address"


async def test_public_records_returned(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_getaddrinfo(host, port, **_kw):
        return [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.215.14", port)),
            (
                socket.AF_INET6,
                socket.SOCK_STREAM,
                6,
                "",
                ("2606:2800:21f:cb07:6820:80da:af6b:8b2c", port, 0, 0),
            ),
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.215.14", port)),
        ]

    loop = __import__("asyncio").get_running_loop()
    monkeypatch.setattr(loop, "getaddrinfo", fake_getaddrinfo)
    addrs = await resolve_public_addresses("example.com", 443)
    assert [str(a) for a in addrs] == ["93.184.215.14", "2606:2800:21f:cb07:6820:80da:af6b:8b2c"]


async def test_dns_failure_reported(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_getaddrinfo(host, port, **_kw):
        raise socket.gaierror("nxdomain")

    loop = __import__("asyncio").get_running_loop()
    monkeypatch.setattr(loop, "getaddrinfo", fake_getaddrinfo)
    with pytest.raises(UnsafeURLError) as exc:
        await resolve_public_addresses("nonexistent.example.com", 443)
    assert exc.value.code == "dns_error"


def test_blocklist_is_parsed() -> None:
    assert len(netguard._BLOCKED_NETWORKS) > 25

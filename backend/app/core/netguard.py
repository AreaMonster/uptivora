"""SSRF protection for customer-supplied URLs.

Two layers live here:

* :func:`validate_monitor_url` — syntactic/policy validation when a URL is submitted.
* :func:`resolve_public_addresses` — DNS resolution that fails if *any* address is not a
  public unicast address. The monitoring engine (Phase 3) dials only addresses returned by
  this function, which is what defeats DNS rebinding.

See docs/ARCHITECTURE.md §4.3.
"""

from __future__ import annotations

import asyncio
import ipaddress
import re
import socket
from dataclasses import dataclass
from urllib.parse import urlsplit, urlunsplit

IPAddress = ipaddress.IPv4Address | ipaddress.IPv6Address

MAX_URL_LENGTH = 2048

# Explicit blocklist, on top of Python's is_global, so behaviour does not drift between
# Python versions. Includes every special-purpose range from the IANA registries.
_BLOCKED_NETWORKS = [
    ipaddress.ip_network(n)
    for n in (
        "0.0.0.0/8",
        "10.0.0.0/8",
        "100.64.0.0/10",
        "127.0.0.0/8",
        "169.254.0.0/16",
        "172.16.0.0/12",
        "192.0.0.0/24",
        "192.0.2.0/24",
        "192.88.99.0/24",
        "192.168.0.0/16",
        "198.18.0.0/15",
        "198.51.100.0/24",
        "203.0.113.0/24",
        "224.0.0.0/4",
        "240.0.0.0/4",
        "255.255.255.255/32",
        "::/96",
        "::1/128",
        "::ffff:0:0/96",
        "64:ff9b::/96",
        "64:ff9b:1::/48",
        "100::/64",
        "2001::/23",
        "2001:db8::/32",
        "2002::/16",
        "3fff::/20",
        "5f00::/16",
        "fc00::/7",
        "fe80::/10",
        "fec0::/10",
        "ff00::/8",
    )
]
_NAT64 = (ipaddress.ip_network("64:ff9b::/96"), ipaddress.ip_network("64:ff9b:1::/48"))

_BLOCKED_HOSTNAMES = {
    "localhost",
    "localhost.localdomain",
    "ip6-localhost",
    "ip6-loopback",
    "metadata",
    "metadata.google.internal",
    "instance-data",
    "kubernetes.default",
}
_BLOCKED_SUFFIXES = (
    ".localhost",
    ".local",
    ".localdomain",
    ".internal",
    ".intranet",
    ".lan",
    ".home",
    ".corp",
    ".private",
    ".home.arpa",
    ".arpa",
    ".onion",
    ".test",
    ".invalid",
    ".example",
    ".cluster.local",
    ".svc",
)
# Ports commonly used by internal infrastructure; refused even on public addresses to limit
# abuse of the monitor as a port scanner.
_BLOCKED_PORTS = {
    22,
    23,
    25,
    53,
    110,
    111,
    135,
    137,
    138,
    139,
    143,
    445,
    465,
    587,
    993,
    995,
    1433,
    1521,
    2049,
    2375,
    2376,
    2379,
    2380,
    3306,
    3389,
    5432,
    5672,
    5984,
    6379,
    6443,
    9000,
    9042,
    9092,
    9200,
    9300,
    10250,
    11211,
    15672,
    27017,
    27018,
}
_LABEL_RE = re.compile(r"^(?!-)[a-z0-9_-]{1,63}(?<!-)$")
_NUMERIC_LABEL_RE = re.compile(r"^(0x[0-9a-f]*|[0-9]+)$")


class UnsafeURLError(ValueError):
    """Raised when a URL or resolved address must not be contacted."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def is_public_ip(ip: IPAddress) -> bool:
    """True only for globally routable unicast addresses (recursing into v4-in-v6 forms)."""
    if isinstance(ip, ipaddress.IPv6Address):
        if ip.ipv4_mapped is not None:
            return is_public_ip(ip.ipv4_mapped)
        if ip.sixtofour is not None:  # 2002::/16 wraps an IPv4 address
            return False
        if ip.teredo is not None:
            return False
        for net in _NAT64:
            if ip in net:
                return False
        if ip.scope_id:
            return False
    if any(ip.version == net.version and ip in net for net in _BLOCKED_NETWORKS):
        return False
    return (
        ip.is_global
        and not ip.is_multicast
        and not ip.is_private
        and not ip.is_loopback
        and not ip.is_link_local
        and not ip.is_reserved
        and not ip.is_unspecified
    )


def _parse_ip_literal(host: str) -> IPAddress | None:
    try:
        return ipaddress.ip_address(host.strip("[]"))
    except ValueError:
        return None


@dataclass(frozen=True, slots=True)
class SafeURL:
    url: str  # normalised URL (IDNA host, no fragment)
    scheme: str
    host: str  # ASCII hostname or IP literal without brackets
    port: int
    is_ip_literal: bool


def _normalise_host(raw_host: str) -> str:
    host = raw_host.rstrip(".").lower()
    if not host:
        raise UnsafeURLError("invalid_host", "The URL has no hostname")
    try:
        ascii_host = host.encode("idna").decode("ascii")
    except UnicodeError as exc:
        raise UnsafeURLError("invalid_host", "The hostname is not a valid domain name") from exc
    if len(ascii_host) > 253:
        raise UnsafeURLError("invalid_host", "The hostname is too long")
    labels = ascii_host.split(".")
    if len(labels) < 2:
        raise UnsafeURLError("invalid_host", "Use a fully qualified domain name (e.g. example.com)")
    if not all(_LABEL_RE.match(label) for label in labels):
        raise UnsafeURLError("invalid_host", "The hostname contains invalid characters")
    if all(_NUMERIC_LABEL_RE.match(label) for label in labels) or _NUMERIC_LABEL_RE.match(
        labels[-1]
    ):
        # e.g. "2130706433", "0x7f.1", "127.1" — non-canonical IPv4 spellings
        raise UnsafeURLError("invalid_host", "Numeric hostnames are not allowed")
    if ascii_host in _BLOCKED_HOSTNAMES or ascii_host.endswith(_BLOCKED_SUFFIXES):
        raise UnsafeURLError(
            "blocked_host", "This hostname refers to a private or reserved network"
        )
    return ascii_host


def validate_monitor_url(raw_url: str) -> SafeURL:
    """Validate a customer-submitted URL. Raises :class:`UnsafeURLError`."""
    url = (raw_url or "").strip()
    if not url:
        raise UnsafeURLError("invalid_url", "URL is required")
    if len(url) > MAX_URL_LENGTH:
        raise UnsafeURLError("invalid_url", f"URL must be at most {MAX_URL_LENGTH} characters")
    if any(ord(c) < 0x21 or ord(c) == 0x7F for c in url) or "\\" in url:
        raise UnsafeURLError("invalid_url", "URL contains whitespace or control characters")

    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError as exc:
        raise UnsafeURLError("invalid_url", "URL could not be parsed") from exc

    scheme = parts.scheme.lower()
    if scheme not in ("http", "https"):
        raise UnsafeURLError("invalid_scheme", "Only http:// and https:// URLs can be monitored")
    if not parts.netloc or parts.hostname is None:
        raise UnsafeURLError("invalid_host", "The URL has no hostname")
    if "@" in parts.netloc:
        raise UnsafeURLError("invalid_url", "URLs with embedded credentials are not allowed")

    if port is None:
        port = 443 if scheme == "https" else 80
    if (
        not (1 <= port <= 65535)
        or port in _BLOCKED_PORTS
        or (port < 1024 and port not in (80, 443))
    ):
        raise UnsafeURLError("blocked_port", f"Port {port} cannot be monitored")

    ip = _parse_ip_literal(parts.hostname)
    if ip is not None:
        if not is_public_ip(ip):
            raise UnsafeURLError(
                "blocked_address", "Private or reserved IP addresses are not allowed"
            )
        host = ip.compressed
        netloc_host = f"[{host}]" if ip.version == 6 else host
    else:
        host = _normalise_host(parts.hostname)
        netloc_host = host

    default_port = 443 if scheme == "https" else 80
    netloc = netloc_host if port == default_port else f"{netloc_host}:{port}"
    normalised = urlunsplit((scheme, netloc, parts.path or "/", parts.query, ""))
    return SafeURL(
        url=normalised, scheme=scheme, host=host, port=port, is_ip_literal=ip is not None
    )


async def resolve_public_addresses(
    host: str, port: int, *, dns_timeout: float = 5.0
) -> list[IPAddress]:
    """Resolve ``host`` and return its addresses, refusing if ANY is not public.

    Rejecting when any record is private (rather than filtering) prevents an attacker from
    publishing one public and one private A record and winning a race.
    """
    literal = _parse_ip_literal(host)
    if literal is not None:
        if not is_public_ip(literal):
            raise UnsafeURLError(
                "blocked_address", "Private or reserved IP addresses are not allowed"
            )
        return [literal]

    loop = asyncio.get_running_loop()
    try:
        infos = await asyncio.wait_for(
            loop.getaddrinfo(host, port, type=socket.SOCK_STREAM, proto=socket.IPPROTO_TCP),
            timeout=dns_timeout,
        )
    except TimeoutError as exc:
        raise UnsafeURLError("dns_timeout", f"DNS lookup for {host} timed out") from exc
    except socket.gaierror as exc:
        raise UnsafeURLError("dns_error", f"DNS lookup for {host} failed") from exc

    addresses: list[IPAddress] = []
    for family, _type, _proto, _canon, sockaddr in infos:
        if family not in (socket.AF_INET, socket.AF_INET6):
            continue
        ip = ipaddress.ip_address(sockaddr[0].split("%", 1)[0])
        if not is_public_ip(ip):
            raise UnsafeURLError(
                "blocked_address", f"{host} resolves to a private or reserved address"
            )
        if ip not in addresses:
            addresses.append(ip)
    if not addresses:
        raise UnsafeURLError("dns_error", f"{host} has no IPv4/IPv6 address")
    return addresses

"""Client IP resolution that only trusts X-Forwarded-For from configured proxies."""

from __future__ import annotations

import ipaddress
from functools import lru_cache

from fastapi import Request

from app.core.config import get_settings


@lru_cache
def _trusted_networks(cidrs: tuple[str, ...]) -> tuple[ipaddress._BaseNetwork, ...]:
    return tuple(ipaddress.ip_network(c, strict=False) for c in cidrs)


def _is_trusted(ip: str, networks) -> bool:
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return any(addr.version == n.version and addr in n for n in networks)


def client_ip(request: Request) -> str:
    """Walk X-Forwarded-For from the right, skipping trusted proxies."""
    peer = request.client.host if request.client else "0.0.0.0"  # noqa: S104
    networks = _trusted_networks(tuple(get_settings().trusted_proxies))
    if not _is_trusted(peer, networks):
        return peer
    forwarded = request.headers.get("x-forwarded-for", "")
    hops = [h.strip() for h in forwarded.split(",") if h.strip()]
    for hop in reversed(hops):
        if not _is_trusted(hop, networks):
            try:
                return str(ipaddress.ip_address(hop))
            except ValueError:
                return peer
    return peer


def user_agent(request: Request) -> str:
    return request.headers.get("user-agent", "")[:400]

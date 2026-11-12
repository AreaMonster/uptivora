"""HTTP client for monitoring checks with SSRF protection at the socket layer.

``GuardedNetworkBackend`` replaces httpcore's network backend. For every new connection it
resolves the hostname itself, refuses the connection if ANY resolved address is not public
(see :mod:`app.core.netguard`), and then dials the already-validated IP address. TLS SNI and
certificate verification still use the hostname, because httpcore takes them from the request
origin, not from the dialled address. Because the checked address is the address that is
dialled, DNS rebinding between "check" and "connect" is impossible.

Keep-alive is disabled: every check opens a fresh connection, so results reflect what a new
visitor would experience and a reused socket can never bypass the address check.
"""

from __future__ import annotations

import ssl
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass

import httpcore
import httpx
from httpx import create_ssl_context

from app.core import netguard
from app.core.netguard import IPAddress

Resolver = Callable[[str, int], Awaitable[list[IPAddress]]]


async def _default_resolver(host: str, port: int) -> list[IPAddress]:
    return await netguard.resolve_public_addresses(host, port)


class GuardedNetworkBackend(httpcore.AsyncNetworkBackend):
    def __init__(self, resolver: Resolver | None = None) -> None:
        self._inner = httpcore.AnyIOBackend()
        self._resolver = resolver or _default_resolver

    async def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,  # noqa: ASYNC109 - httpcore interface
        local_address: str | None = None,
        socket_options: Iterable | None = None,
    ) -> httpcore.AsyncNetworkStream:
        # Raises netguard.UnsafeURLError (propagates unchanged through httpx) when blocked.
        addresses = await self._resolver(host, port)
        last_error: Exception | None = None
        for address in addresses:
            try:
                return await self._inner.connect_tcp(
                    str(address),
                    port,
                    timeout=timeout,
                    local_address=local_address,
                    socket_options=socket_options,
                )
            except (httpcore.ConnectError, httpcore.ConnectTimeout) as exc:
                last_error = exc
        assert last_error is not None
        raise last_error

    async def connect_unix_socket(self, *args, **kwargs):  # pragma: no cover - never allowed
        raise httpcore.ConnectError("Unix sockets are not allowed")

    async def sleep(self, seconds: float) -> None:
        await self._inner.sleep(seconds)


class GuardedTransport(httpx.AsyncHTTPTransport):
    def __init__(self, *, verify: bool, resolver: Resolver | None, max_connections: int) -> None:
        super().__init__(trust_env=False)
        if verify:
            ssl_context = create_ssl_context(verify=True, trust_env=False)
        else:
            ssl_context = ssl.create_default_context()
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE
        self._pool = httpcore.AsyncConnectionPool(
            ssl_context=ssl_context,
            max_connections=max_connections,
            max_keepalive_connections=0,
            http1=True,
            http2=False,
            retries=0,
            network_backend=GuardedNetworkBackend(resolver),
        )


@dataclass
class MonitorClients:
    """One client that verifies TLS certificates and one that does not (per-monitor option)."""

    verified: httpx.AsyncClient
    unverified: httpx.AsyncClient

    def for_monitor(self, verify_tls: bool) -> httpx.AsyncClient:
        return self.verified if verify_tls else self.unverified

    async def aclose(self) -> None:
        await self.verified.aclose()
        await self.unverified.aclose()


def build_clients(
    *, max_connections: int = 200, resolver: Resolver | None = None
) -> MonitorClients:
    def make(verify: bool) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            transport=GuardedTransport(
                verify=verify, resolver=resolver, max_connections=max_connections
            ),
            trust_env=False,  # never use HTTP(S)_PROXY from the environment
            follow_redirects=False,  # redirects are followed manually and re-validated
            cookies=None,
        )

    return MonitorClients(verified=make(True), unverified=make(False))

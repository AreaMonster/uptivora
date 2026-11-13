"""Alert-storm guard: tell "the internet is down for us" apart from "many sites are down".

If the monitoring server loses its own network or DNS, every check fails at once and every
customer would get an outage email. When most recently checked hosts fail with network-level
errors, the worker checks a few operator-configured canary URLs (``network_canaries``):

* canaries fail too  -> local problem: hold the failed checks (retry a minute later, no
  incident, no email) and report it through the heartbeat and the health endpoints;
* a canary answers   -> the outages are real and are handled normally.

Without canaries (the self-hosted default) the guard is off: no extra outbound requests and
no risk of suppressing a real outage, e.g. of a provider hosting all of a customer's sites.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable

from app.engine.checker import CheckOutcome, CheckSpec, run_check
from app.engine.netclient import MonitorClients

log = logging.getLogger("uptivora.netwatch")

NETWORK_ERRORS = frozenset({"timeout", "connection_error", "dns_error"})
WINDOW_SECONDS = 120.0  # hosts checked within this window form the sample
MIN_HOSTS = 10  # never judge from a handful of monitors
FAILURE_RATIO = 0.5  # share of hosts whose latest check failed at network level
VERDICT_SECONDS = 30.0  # canary result is reused this long

Checker = Callable[[MonitorClients, CheckSpec, str], Awaitable[CheckOutcome]]


def is_network_failure(outcome: CheckOutcome) -> bool:
    return not outcome.is_up and outcome.error_kind in NETWORK_ERRORS


class NetworkWatch:
    def __init__(
        self,
        canaries: list[str],
        clients: MonitorClients | None,
        user_agent: str,
        *,
        checker: Checker = run_check,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.canaries = list(canaries)
        self.clients = clients
        self.user_agent = user_agent
        self.checker = checker
        self.clock = clock
        self._latest: dict[str, tuple[float, bool]] = {}
        self._verdict: tuple[float, bool] | None = None  # (when, local outage?)
        self._lock = asyncio.Lock()

    @property
    def enabled(self) -> bool:
        return bool(self.canaries)

    @property
    def held(self) -> bool:
        """True while a local network problem is the current verdict."""
        if self._verdict is None:
            return False
        when, local = self._verdict
        return local and self.clock() - when < 2 * VERDICT_SECONDS

    def record(self, host: str, outcome: CheckOutcome) -> None:
        if self.enabled:
            self._latest[host] = (self.clock(), is_network_failure(outcome))

    def mass_failure(self) -> bool:
        now = self.clock()
        for host in [h for h, (t, _) in self._latest.items() if now - t > WINDOW_SECONDS]:
            del self._latest[host]
        hosts = len(self._latest)
        failed = sum(1 for _, bad in self._latest.values() if bad)
        return hosts >= MIN_HOSTS and failed / hosts >= FAILURE_RATIO

    async def local_outage(self) -> bool:
        """Should this network failure be held back? Only with canaries and a mass failure."""
        if not self.enabled or not self.mass_failure():
            return False
        async with self._lock:
            if self._verdict and self.clock() - self._verdict[0] < VERDICT_SECONDS:
                return self._verdict[1]
            results = await asyncio.gather(
                *(
                    self.checker(
                        self.clients, CheckSpec(url=u, timeout_seconds=10), self.user_agent
                    )
                    for u in self.canaries
                ),
                return_exceptions=True,
            )
            local = not any(isinstance(r, CheckOutcome) and r.is_up for r in results)
            self._verdict = (self.clock(), local)
            if local:
                log.warning(
                    "Most monitored sites and all canary URLs are unreachable: the monitoring "
                    "server's own network or DNS is probably down. Outage alerts are held "
                    "back and checks retried every minute until it recovers."
                )
            return local

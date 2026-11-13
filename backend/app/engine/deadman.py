"""Optional outbound heartbeat ("dead man's switch") for monitoring Uptivora itself.

When ``UPTIVORA_HEARTBEAT_URL`` is set (e.g. a healthchecks.io ping URL or the operator's own
monitoring), the worker requests it once a minute — but only while checks are actually
running and no local network problem is detected. If the pings stop, that service alerts the
operator; this also covers a dead server, which no in-app alert could report.

Off by default: with no URL configured this module makes no network requests at all.
"""

from __future__ import annotations

import logging
import time

import httpx

from app.core.config import Settings
from app.engine.scheduler import Scheduler

log = logging.getLogger("uptivora.deadman")

STALL_SECONDS = 120


async def ping(settings: Settings, scheduler: Scheduler) -> bool:
    if not settings.heartbeat_url:
        return False
    if time.monotonic() - scheduler.last_loop > STALL_SECONDS:
        log.warning("Scheduler loop stalled; not sending the heartbeat")
        return False
    if scheduler.stats.network_held:
        return False  # the operator should hear about the network problem
    try:
        # Operator-configured URL (not customer input), so the SSRF-guarded clients are not
        # used: a private monitoring server on the operator's network is a valid target.
        async with httpx.AsyncClient(timeout=10, trust_env=False, follow_redirects=False) as client:
            resp = await client.get(
                settings.heartbeat_url, headers={"User-Agent": settings.monitor_user_agent}
            )
        if resp.status_code >= 400:
            log.warning("Heartbeat URL answered HTTP %s", resp.status_code)
            return False
        return True
    except httpx.HTTPError as exc:
        log.warning("Heartbeat ping failed: %s", type(exc).__name__)
        return False

"""Monitor state machine (pure, no I/O). See docs/ARCHITECTURE.md §4.2.

* An outage is declared only after ``down_threshold`` consecutive failures.
* A recovery is declared only after ``recovery_threshold`` consecutive successes.
* Exactly one "down" event and one "up" event per outage.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from app.models import MonitorStatus

Event = Literal["down", "up"] | None


@dataclass(frozen=True, slots=True)
class Transition:
    status: MonitorStatus
    consecutive_failures: int
    consecutive_successes: int
    event: Event

    @property
    def confirming(self) -> bool:
        """A failure was seen but the outage is not confirmed yet."""
        return self.consecutive_failures > 0 and self.status != MonitorStatus.DOWN


def transition(
    status: MonitorStatus,
    consecutive_failures: int,
    consecutive_successes: int,
    *,
    is_up: bool,
    down_threshold: int,
    recovery_threshold: int,
) -> Transition:
    if is_up:
        successes = consecutive_successes + 1
        if status == MonitorStatus.DOWN:
            if successes >= recovery_threshold:
                return Transition(MonitorStatus.UP, 0, successes, "up")
            return Transition(MonitorStatus.DOWN, 0, successes, None)
        return Transition(MonitorStatus.UP, 0, successes, None)

    failures = consecutive_failures + 1
    if status == MonitorStatus.DOWN:
        return Transition(MonitorStatus.DOWN, failures, 0, None)
    if failures >= down_threshold:
        return Transition(MonitorStatus.DOWN, failures, 0, "down")
    # Not confirmed yet: keep showing the previous state (up or pending).
    keep = status if status in (MonitorStatus.UP, MonitorStatus.PENDING) else MonitorStatus.PENDING
    return Transition(keep, failures, 0, None)

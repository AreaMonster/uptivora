import random

import pytest

from app.engine.state import transition
from app.models import MonitorStatus as S


def run(seq: str, *, down: int = 2, up: int = 1, start: S = S.PENDING):
    """Feed a string of u (up) / d (down) results; return (final status, events)."""
    status, cf, cs, events = start, 0, 0, []
    for ch in seq:
        t = transition(status, cf, cs, is_up=ch == "u", down_threshold=down, recovery_threshold=up)
        status, cf, cs = t.status, t.consecutive_failures, t.consecutive_successes
        if t.event:
            events.append(t.event)
    return status, events


@pytest.mark.parametrize(
    ("seq", "status", "events"),
    [
        ("u", S.UP, []),
        ("d", S.PENDING, []),  # first failure on a new monitor: not confirmed
        ("ud", S.UP, []),  # single blip: still shown as up, no alert
        ("udu", S.UP, []),
        ("udd", S.DOWN, ["down"]),
        ("uddddd", S.DOWN, ["down"]),  # stays down, exactly one alert
        ("uddu", S.UP, ["down", "up"]),
        ("uddudd", S.DOWN, ["down", "up", "down"]),
        ("dd", S.DOWN, ["down"]),  # never up before, still an outage
    ],
)
def test_sequences(seq, status, events) -> None:
    assert run(seq) == (status, events)


def test_recovery_threshold() -> None:
    assert run("udduu", up=3) == (S.DOWN, ["down"])
    assert run("uddduuu", up=3) == (S.UP, ["down", "up"])
    assert run("uddudu", up=2) == (S.DOWN, ["down"])  # success streak broken


def test_down_threshold_one() -> None:
    assert run("ud", down=1) == (S.DOWN, ["down"])


def test_confirming_flag() -> None:
    t = transition(S.UP, 0, 5, is_up=False, down_threshold=3, recovery_threshold=1)
    assert t.confirming and t.status == S.UP
    t2 = transition(S.DOWN, 4, 0, is_up=False, down_threshold=3, recovery_threshold=1)
    assert not t2.confirming


def test_random_sequences_alternate_events() -> None:
    """Property: events always alternate down/up, starting with down."""
    rng = random.Random(7)  # noqa: S311 - deterministic test data
    for _ in range(500):
        seq = "".join(rng.choice("uud") for _ in range(rng.randint(1, 60)))
        _, events = run(seq, down=rng.randint(1, 4), up=rng.randint(1, 3))
        for i, e in enumerate(events):
            assert e == ("down" if i % 2 == 0 else "up")

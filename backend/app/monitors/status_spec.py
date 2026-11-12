"""Expected HTTP status specification, e.g. ``"200-399"`` or ``"200,204,301-302"``."""

from __future__ import annotations

import re

_PART = re.compile(r"^(\d{3})(?:-(\d{3}))?$")
MAX_PARTS = 10


def parse_status_spec(spec: str) -> list[tuple[int, int]]:
    spec = (spec or "").replace(" ", "")
    if not spec:
        raise ValueError("Expected status codes are required (e.g. 200-399)")
    ranges: list[tuple[int, int]] = []
    parts = spec.split(",")
    if len(parts) > MAX_PARTS:
        raise ValueError(f"At most {MAX_PARTS} status code ranges")
    for part in parts:
        m = _PART.match(part)
        if not m:
            raise ValueError(f"'{part}' is not a status code or range like 200-299")
        lo = int(m.group(1))
        hi = int(m.group(2) or lo)
        if not (100 <= lo <= hi <= 599):
            raise ValueError(f"'{part}' must be within 100-599 and ascending")
        ranges.append((lo, hi))
    return ranges


def normalize_status_spec(spec: str) -> str:
    return ",".join(f"{lo}" if lo == hi else f"{lo}-{hi}" for lo, hi in parse_status_spec(spec))


def status_matches(code: int, ranges: list[tuple[int, int]]) -> bool:
    return any(lo <= code <= hi for lo, hi in ranges)

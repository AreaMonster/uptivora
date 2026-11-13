from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.models import (
    CheckResult,
    Incident,
    Monitor,
    NotificationKind,
    NotificationOutbox,
    OutboxStatus,
)
from tests.conftest import give_plan, register

NEW = {"name": "Checkout", "url": "https://checkout.example.com", "interval_seconds": 60}


async def _setup(client, db) -> tuple[uuid.UUID, list[uuid.UUID]]:
    me = await register(client)
    await give_plan(db, me["user"]["id"], "pro")
    mid = uuid.UUID((await client.post("/api/monitors", json=NEW)).json()["id"])
    seq = await db.scalar(select(Monitor.seq).where(Monitor.id == mid))
    now = datetime.now(UTC)
    old = Incident(
        monitor_id=mid,
        started_at=now - timedelta(days=3, minutes=30),
        resolved_at=now - timedelta(days=3),
        cause="HTTP 502",
        status_code=502,
    )
    mid_ = Incident(
        monitor_id=mid,
        started_at=now - timedelta(hours=5, minutes=10),
        resolved_at=now - timedelta(hours=5),
        cause="Timeout",
        error_kind="timeout",
    )
    open_ = Incident(monitor_id=mid, started_at=now - timedelta(minutes=4), cause="DNS failed")
    db.add_all([old, mid_, open_])
    await db.flush()
    for i in range(14):  # checks around the 5 h-ago incident
        t = now - timedelta(hours=5, minutes=14) + timedelta(minutes=i)
        down = 4 <= i < 14 and t < mid_.resolved_at
        db.add(
            CheckResult(
                monitor_seq=seq,
                checked_at=t,
                is_up=not down,
                status_code=None if down else 200,
                error_kind="timeout" if down else None,
            )
        )
    db.add(
        NotificationOutbox(
            incident_id=mid_.id,
            monitor_id=mid,
            user_id=uuid.UUID(me["user"]["id"]),
            kind=NotificationKind.MONITOR_DOWN,
            recipient="x@example.com",
            subject="DOWN",
            body_text="b",
            dedupe_key=f"t:{uuid.uuid4()}",
            status=OutboxStatus.SENT,
            attempts=1,
            sent_at=now,
        )
    )
    await db.commit()
    return mid, [open_.id, mid_.id, old.id]


async def test_list_filters_and_pagination(client, db) -> None:
    _, (open_id, mid_id, old_id) = await _setup(client, db)
    all_ = (await client.get("/api/incidents")).json()
    assert [i["id"] for i in all_["items"]] == [str(open_id), str(mid_id), str(old_id)]
    assert all_["items"][0]["resolved_at"] is None and all_["next_before"] is None
    opened = (await client.get("/api/incidents?status=open")).json()["items"]
    assert [i["id"] for i in opened] == [str(open_id)]
    resolved = (await client.get("/api/incidents?status=resolved")).json()["items"]
    assert [i["id"] for i in resolved] == [str(mid_id), str(old_id)]

    page1 = (await client.get("/api/incidents?limit=2")).json()
    assert len(page1["items"]) == 2 and page1["next_before"]
    page2 = (
        await client.get("/api/incidents", params={"limit": 2, "before": page1["next_before"]})
    ).json()
    assert [i["id"] for i in page2["items"]] == [str(old_id)] and page2["next_before"] is None


async def test_summary(client, db) -> None:
    await _setup(client, db)
    s = (await client.get("/api/incidents/summary?days=30")).json()
    assert s["total"] == 3 and s["open"] == 1
    assert s["mean_time_to_recovery_seconds"] == (30 * 60 + 10 * 60) // 2
    assert (
        30 * 60 + 10 * 60 + 4 * 60 - 5 <= s["downtime_seconds"] <= 30 * 60 + 10 * 60 + 4 * 60 + 60
    )
    week = (await client.get("/api/incidents/summary?days=1")).json()
    assert week["total"] == 2  # 3-day-old incident is outside the window


async def test_detail_timeline(client, db) -> None:
    _, (_, mid_id, _) = await _setup(client, db)
    d = (await client.get(f"/api/incidents/{mid_id}")).json()
    assert d["incident"]["cause"] == "Timeout" and d["incident"]["duration_seconds"] == 600
    assert d["monitor"]["name"] == "Checkout"
    # Window: 2 check intervals before the start until 2 after the end (12 of 14 checks).
    assert len(d["checks"]) == 12 and d["checks"][0]["is_up"] is True
    assert any(not c["is_up"] for c in d["checks"])
    assert d["notifications"][0]["status"] == "sent"


async def test_acknowledge_and_note(client, db) -> None:
    _, (open_id, _, _) = await _setup(client, db)
    r = await client.patch(
        f"/api/incidents/{open_id}",
        json={"acknowledged": True, "note": "  Hosting provider issue  "},
    )
    assert (
        r.status_code == 200
        and r.json()["acknowledged_at"]
        and r.json()["note"] == "Hosting provider issue"
    )
    d = (await client.get(f"/api/incidents/{open_id}")).json()
    assert d["incident"]["acknowledged_by"] == "Test User"
    r2 = await client.patch(f"/api/incidents/{open_id}", json={"acknowledged": False, "note": ""})
    assert r2.json()["acknowledged_at"] is None and r2.json()["note"] is None
    too_long = await client.patch(f"/api/incidents/{open_id}", json={"note": "x" * 2001})
    assert too_long.status_code == 422


async def test_incidents_are_private(client, make_client, db) -> None:
    _, (open_id, _, _) = await _setup(client, db)
    other = make_client()
    await register(other)
    assert (await other.get(f"/api/incidents/{open_id}")).status_code == 404
    assert (await other.patch(f"/api/incidents/{open_id}", json={"note": "x"})).status_code == 404
    assert (await other.get("/api/incidents")).json()["items"] == []
    assert (await other.get("/api/incidents/summary")).json()["total"] == 0


async def test_old_incident_timeline_comes_from_retained_checks(client, db) -> None:
    from app.models import RetainedCheck

    me = await register(client)
    await give_plan(db, me["user"]["id"], "pro")
    mid = uuid.UUID((await client.post("/api/monitors", json=NEW)).json()["id"])
    seq = await db.scalar(select(Monitor.seq).where(Monitor.id == mid))
    start = datetime.now(UTC) - timedelta(days=12)
    incident = Incident(
        monitor_id=mid, started_at=start, resolved_at=start + timedelta(minutes=10), cause="503"
    )
    db.add(incident)
    db.add_all(
        RetainedCheck(
            monitor_seq=seq,
            checked_at=start + timedelta(minutes=5 * i),
            is_up=i == 2,
            status_code=200 if i == 2 else 503,
        )
        for i in range(3)
    )
    await db.commit()
    body = (await client.get(f"/api/incidents/{incident.id}")).json()
    assert [c["is_up"] for c in body["checks"]] == [False, False, True]

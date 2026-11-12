from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import update

from app.models import CheckResult, CheckRollup, Incident, User, UserRole
from tests.conftest import give_plan, register

NEW = {"name": "Shop", "url": "https://shop.example.com", "interval_seconds": 300}


async def _with_plan(client, db, plan: str = "starter") -> dict:
    me = await register(client)
    await give_plan(db, me["user"]["id"], plan)
    return me


async def test_no_plan_cannot_create(client) -> None:
    await register(client)
    resp = await client.post("/api/monitors", json=NEW)
    assert resp.status_code == 402 and resp.json()["error"]["code"] == "no_plan"


async def test_create_list_get(client, db) -> None:
    await _with_plan(client, db)
    resp = await client.post(
        "/api/monitors",
        json={**NEW, "url": "HTTPS://Shop.Example.com#x", "expected_status": " 200 , 301-302 "},
    )
    assert resp.status_code == 201, resp.text
    m = resp.json()
    assert m["url"] == "https://shop.example.com/" and m["status"] == "pending"
    assert m["expected_status"] == "200,301-302"
    listed = (await client.get("/api/monitors")).json()
    assert [x["id"] for x in listed] == [m["id"]]
    detail = (await client.get(f"/api/monitors/{m['id']}")).json()
    assert detail["monitor"]["name"] == "Shop" and detail["uptime"]["24h"] is None
    me = (await client.get("/api/auth/me")).json()
    assert me["usage"]["active_monitors"] == 1 and me["limits"]["plan_code"] == "starter"


async def test_plan_limits(client, db) -> None:
    await _with_plan(client, db, "starter")  # 3 monitors, min 300 s
    fast = await client.post("/api/monitors", json={**NEW, "interval_seconds": 60})
    assert fast.status_code == 402 and "interval_seconds" in fast.json()["error"]["fields"]
    ids = []
    for i in range(3):
        r = await client.post("/api/monitors", json={**NEW, "name": f"S{i}"})
        assert r.status_code == 201
        ids.append(r.json()["id"])
    over = await client.post("/api/monitors", json=NEW)
    assert over.status_code == 402 and over.json()["error"]["code"] == "limit_exceeded"
    assert (await client.post(f"/api/monitors/{ids[0]}/pause")).json()["status"] == "paused"
    assert (await client.post("/api/monitors", json=NEW)).status_code == 201
    resume = await client.post(f"/api/monitors/{ids[0]}/resume")
    assert resume.status_code == 402


async def test_ssrf_targets_rejected(client, db) -> None:
    await _with_plan(client, db)
    cases = {
        "http://127.0.0.1/": "blocked_address",
        "http://169.254.169.254/latest/meta-data": "blocked_address",
        "http://intranet.local/": "blocked_host",
        "https://private.example.com/": "blocked_address",  # DNS -> 10.0.0.1
        "https://nxdomain.example.com/": "dns_error",
        "file:///etc/passwd": "invalid_scheme",
    }
    for url, code in cases.items():
        resp = await client.post("/api/monitors", json={**NEW, "url": url})
        assert resp.status_code == 422, url
        assert resp.json()["error"]["code"] == code and "url" in resp.json()["error"]["fields"]


async def test_validation_rules(client, db) -> None:
    await _with_plan(client, db, "business")
    cases = [
        {"timeout_seconds": 60, "interval_seconds": 30},
        {"method": "HEAD", "keyword": "Welcome"},
        {"expected_status": "abc"},
        {"expected_status": "399-200"},
        {"name": "   "},
        {"interval_seconds": 10},
    ]
    for extra in cases:
        resp = await client.post("/api/monitors", json={**NEW, **extra})
        assert resp.status_code == 422, (extra, resp.text)


async def test_other_users_monitors_are_invisible(client, make_client, db) -> None:
    await _with_plan(client, db)
    mid = (await client.post("/api/monitors", json=NEW)).json()["id"]
    intruder = make_client()
    await _with_plan(intruder, db)
    for method, path in [
        ("GET", ""),
        ("PATCH", ""),
        ("DELETE", ""),
        ("POST", "/pause"),
        ("GET", "/series"),
        ("GET", "/incidents"),
        ("GET", "/checks"),
    ]:
        resp = await intruder.request(
            method, f"/api/monitors/{mid}{path}", json={"name": "x"} if method == "PATCH" else None
        )
        assert resp.status_code == 404, (method, path)
    assert (await intruder.get("/api/monitors")).json() == []
    assert (await client.get(f"/api/monitors/{mid}")).status_code == 200


async def test_update_and_delete(client, db) -> None:
    await _with_plan(client, db, "pro")
    mid = (await client.post("/api/monitors", json=NEW)).json()["id"]
    r = await client.patch(
        f"/api/monitors/{mid}",
        json={"name": "Renamed", "interval_seconds": 60, "url": "https://other.example.org/health"},
    )
    assert r.status_code == 200
    assert r.json()["name"] == "Renamed" and r.json()["url"] == "https://other.example.org/health"
    assert (
        await client.patch(f"/api/monitors/{mid}", json={"interval_seconds": 30})
    ).status_code == 402
    assert (
        await client.patch(f"/api/monitors/{mid}", json={"timeout_seconds": 60})
    ).status_code == 422
    assert (
        await client.patch(f"/api/monitors/{mid}", json={"url": "http://10.0.0.1/"})
    ).status_code == 422
    assert (await client.patch(f"/api/monitors/{mid}", json={"status": "up"})).status_code == 422
    assert (await client.patch(f"/api/monitors/{mid}", json={"name": None})).status_code == 422
    assert (await client.delete(f"/api/monitors/{mid}")).status_code == 204
    assert (await client.get(f"/api/monitors/{mid}")).status_code == 404


async def test_admin_has_no_plan_limits(client, db) -> None:
    me = await register(client)
    await db.execute(
        update(User).where(User.id == uuid.UUID(me["user"]["id"])).values(role=UserRole.ADMIN)
    )
    await db.commit()
    resp = await client.post("/api/monitors", json={**NEW, "interval_seconds": 30})
    assert resp.status_code == 201


async def test_statistics_and_incidents(client, db) -> None:
    await _with_plan(client, db, "pro")
    mid = uuid.UUID((await client.post("/api/monitors", json=NEW)).json()["id"])
    now = datetime.now(UTC)
    # 24 h: 9 up + 1 down -> 90 %
    for i in range(10):
        db.add(
            CheckResult(
                monitor_id=mid,
                checked_at=now - timedelta(minutes=10 * i + 1),
                is_up=i != 3,
                status_code=200 if i != 3 else 503,
                response_ms=100 + i,
            )
        )
    # Older data only in rollups (raw purged): 40 days ago, 100 checks, 50 up
    db.add(
        CheckRollup(
            monitor_id=mid,
            bucket_start=(now - timedelta(days=40)).replace(minute=0, second=0, microsecond=0),
            checks_total=100,
            checks_up=50,
            response_ms_avg=200,
            response_ms_min=100,
            response_ms_max=300,
            response_ms_p95=290,
        )
    )
    db.add(
        Incident(
            monitor_id=mid,
            started_at=now - timedelta(minutes=35),
            resolved_at=now - timedelta(minutes=25),
            cause="HTTP 503",
            status_code=503,
        )
    )
    await db.commit()

    listed = (await client.get("/api/monitors")).json()
    assert listed[0]["uptime_24h"] == 90.0
    detail = (await client.get(f"/api/monitors/{mid}")).json()
    assert detail["uptime"]["24h"] == 90.0 and detail["uptime"]["30d"] == 90.0
    assert detail["uptime"]["90d"] == round(100 * 59 / 110, 3)

    s24 = (await client.get(f"/api/monitors/{mid}/series?range=24h")).json()["points"]
    assert sum(p["checks"] for p in s24) == 10
    s90 = (await client.get(f"/api/monitors/{mid}/series?range=90d")).json()["points"]
    assert sum(p["checks"] for p in s90) == 110
    assert (await client.get(f"/api/monitors/{mid}/series?range=1y")).status_code == 422

    checks = (await client.get(f"/api/monitors/{mid}/checks?limit=5")).json()
    assert len(checks) == 5 and checks[0]["response_ms"] == 100
    inc = (await client.get(f"/api/monitors/{mid}/incidents")).json()
    assert inc[0]["duration_seconds"] == 600 and inc[0]["cause"] == "HTTP 503"
    all_inc = (await client.get("/api/incidents")).json()["items"]
    assert all_inc[0]["monitor_name"] == "Shop"

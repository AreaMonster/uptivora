from __future__ import annotations

from tests.conftest import PASSWORD, register, unique_email


async def test_profile_update(client) -> None:
    await register(client)
    bad = await client.patch("/api/account", json={"timezone": "Mars/Olympus"})
    assert bad.status_code == 422
    ok = await client.patch("/api/account", json={"timezone": "Europe/Zurich", "full_name": "Eva"})
    assert ok.status_code == 200
    assert (
        ok.json()["user"]["timezone"] == "Europe/Zurich" and ok.json()["user"]["full_name"] == "Eva"
    )


async def test_change_password_revokes_other_sessions(client, make_client) -> None:
    email = unique_email()
    await register(client, email)
    second = make_client()
    login = await second.post("/api/auth/login", json={"email": email, "password": PASSWORD})
    assert login.status_code == 200
    sessions = (await client.get("/api/account/sessions")).json()
    assert len(sessions) == 2 and sum(s["current"] for s in sessions) == 1

    wrong = await client.post(
        "/api/account/password",
        json={"current_password": "nope-nope-nope", "new_password": "X-new-pass-99"},
    )
    assert wrong.status_code == 403
    ok = await client.post(
        "/api/account/password",
        json={"current_password": PASSWORD, "new_password": "X-new-pass-99"},
    )
    assert ok.status_code == 204
    assert (await client.get("/api/auth/me")).status_code == 200
    assert (await second.get("/api/auth/me")).status_code == 401


async def test_revoke_specific_session(client, make_client) -> None:
    email = unique_email()
    await register(client, email)
    second = make_client()
    await second.post("/api/auth/login", json={"email": email, "password": PASSWORD})
    other = next(s for s in (await client.get("/api/account/sessions")).json() if not s["current"])
    assert (await client.delete(f"/api/account/sessions/{other['id']}")).status_code == 204
    assert (await second.get("/api/auth/me")).status_code == 401


async def test_notification_preferences(client) -> None:
    await register(client)
    prefs = (await client.get("/api/account/notifications")).json()
    assert prefs["notify_down"] is True and prefs["ssl_warning_days"] == 14
    new = {
        "notify_down": True,
        "notify_recovery": False,
        "notify_ssl": True,
        "ssl_warning_days": 30,
        "alert_email": "Ops@Example.com",
    }
    saved = await client.put("/api/account/notifications", json=new)
    assert saved.status_code == 200 and saved.json()["alert_email"] == "ops@example.com"
    assert (await client.get("/api/account/notifications")).json()["notify_recovery"] is False
    bad = await client.put("/api/account/notifications", json={**new, "ssl_warning_days": 0})
    assert bad.status_code == 422


async def test_delete_account(client, make_client) -> None:
    email = unique_email()
    await register(client, email)
    wrong = await client.request("DELETE", "/api/account", json={"password": "wrong-password-1"})
    assert wrong.status_code == 403
    ok = await client.request("DELETE", "/api/account", json={"password": PASSWORD})
    assert ok.status_code == 204
    again = await make_client().post("/api/auth/login", json={"email": email, "password": PASSWORD})
    assert again.status_code == 401

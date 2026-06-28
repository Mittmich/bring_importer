"""Tests for server-side Google Calendar integration + meal-plan sync.

The Google network helpers in ``api.google_calendar`` are patched (AsyncMock),
so no real HTTP happens. Patching at ``api.google_calendar.*`` covers both the
integrations router and the meal-plan router, which call them via the module.
"""

import sqlite3
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException

from api.routers.integrations import _encode_state


def _user_id(tmp_db_path) -> int:
    conn = sqlite3.connect(str(tmp_db_path))
    try:
        row = conn.execute("SELECT id FROM users WHERE email = ?", ("test@example.com",)).fetchone()
        return row[0]
    finally:
        conn.close()


def _connect_google(tmp_db_path, calendar_id="primary", refresh_token="rt-123"):
    conn = sqlite3.connect(str(tmp_db_path))
    try:
        conn.execute(
            "INSERT INTO google_integrations (user_id, refresh_token, calendar_id) "
            "VALUES (?, ?, ?)",
            (_user_id(tmp_db_path), refresh_token, calendar_id),
        )
        conn.commit()
    finally:
        conn.close()


def _make_recipe(client, auth_headers) -> str:
    resp = client.post("/recipes/parse", headers=auth_headers, data={"image": "aGVsbG8="})
    assert resp.status_code == 200
    return resp.json()["uuid"]


def _add_entry(client, auth_headers, date, recipe_uuid) -> int:
    resp = client.post(
        "/meal-plan", headers=auth_headers, json={"date": date, "recipe_uuid": recipe_uuid}
    )
    assert resp.status_code == 200
    return resp.json()["id"]


def _event_id(tmp_db_path, entry_id):
    conn = sqlite3.connect(str(tmp_db_path))
    try:
        row = conn.execute(
            "SELECT google_event_id FROM meal_plan_entries WHERE id = ?", (entry_id,)
        ).fetchone()
        return row[0]
    finally:
        conn.close()


def _set_event_id(tmp_db_path, entry_id, event_id):
    conn = sqlite3.connect(str(tmp_db_path))
    try:
        conn.execute(
            "UPDATE meal_plan_entries SET google_event_id = ? WHERE id = ?", (event_id, entry_id)
        )
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Connect / status
# ---------------------------------------------------------------------------


def test_status_not_connected(client, auth_headers):
    resp = client.get("/integrations/google/status", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body == {"configured": True, "connected": False, "calendar_id": None}


def test_connect_returns_consent_url(client, auth_headers):
    resp = client.get("/integrations/google/connect", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["url"].startswith("https://accounts.google.com/o/oauth2/v2/auth")


def test_callback_stores_token_and_connects(client, auth_headers, tmp_db_path):
    state = _encode_state("test@example.com")
    with patch(
        "api.google_calendar.exchange_code",
        new=AsyncMock(return_value={"refresh_token": "rt-xyz"}),
    ):
        resp = client.get(
            "/integrations/google/callback",
            params={"code": "auth-code", "state": state},
            follow_redirects=False,
        )
    assert resp.status_code in (302, 307)
    assert "google=connected" in resp.headers["location"]

    status = client.get("/integrations/google/status", headers=auth_headers).json()
    assert status["connected"] is True
    assert status["calendar_id"] == "primary"


def test_callback_invalid_state_redirects_error(client):
    resp = client.get(
        "/integrations/google/callback",
        params={"code": "x", "state": "not-a-valid-jwt"},
        follow_redirects=False,
    )
    assert resp.status_code in (302, 307)
    assert "google=error" in resp.headers["location"]


def test_calendars_and_select(client, auth_headers, tmp_db_path):
    _connect_google(tmp_db_path)
    cals = [
        {"id": "primary", "summary": "Me", "primary": True},
        {"id": "work@x", "summary": "Work"},
    ]
    with (
        patch("api.google_calendar.refresh_access_token", new=AsyncMock(return_value="at")),
        patch("api.google_calendar.list_calendars", new=AsyncMock(return_value=cals)),
    ):
        resp = client.get("/integrations/google/calendars", headers=auth_headers)
    assert resp.status_code == 200
    assert [c["id"] for c in resp.json()] == ["primary", "work@x"]

    sel = client.put(
        "/integrations/google/calendar", headers=auth_headers, json={"calendar_id": "work@x"}
    )
    assert sel.status_code == 204
    status = client.get("/integrations/google/status", headers=auth_headers).json()
    assert status["calendar_id"] == "work@x"


# ---------------------------------------------------------------------------
# Sync
# ---------------------------------------------------------------------------


def test_sync_creates_events_with_recipe_link(client, auth_headers, mocked_openai, tmp_db_path):
    uuid = _make_recipe(client, auth_headers)
    entry_id = _add_entry(client, auth_headers, "2026-06-22", uuid)
    _connect_google(tmp_db_path)

    insert = AsyncMock(return_value="evt-1")
    with (
        patch("api.google_calendar.refresh_access_token", new=AsyncMock(return_value="at")),
        patch("api.google_calendar.insert_event", new=insert),
    ):
        resp = client.post(
            "/meal-plan/sync",
            headers=auth_headers,
            json={"start": "2026-06-22", "end": "2026-06-28"},
        )
    assert resp.status_code == 200
    assert resp.json() == {"created": 1, "recreated": 0, "total": 1}
    assert _event_id(tmp_db_path, entry_id) == "evt-1"
    # The event description carries a link back to the recipe.
    description = insert.call_args.args[4]
    assert f"https://app.test/recipes/{uuid}" in description


def test_sync_recreates_missing_event(client, auth_headers, mocked_openai, tmp_db_path):
    uuid = _make_recipe(client, auth_headers)
    entry_id = _add_entry(client, auth_headers, "2026-06-22", uuid)
    _connect_google(tmp_db_path)
    _set_event_id(tmp_db_path, entry_id, "stale-event")

    with (
        patch("api.google_calendar.refresh_access_token", new=AsyncMock(return_value="at")),
        patch("api.google_calendar.event_exists", new=AsyncMock(return_value=False)),
        patch("api.google_calendar.insert_event", new=AsyncMock(return_value="evt-2")),
    ):
        resp = client.post(
            "/meal-plan/sync",
            headers=auth_headers,
            json={"start": "2026-06-22", "end": "2026-06-28"},
        )
    assert resp.json() == {"created": 0, "recreated": 1, "total": 1}
    assert _event_id(tmp_db_path, entry_id) == "evt-2"


def test_sync_requires_connection(client, auth_headers, mocked_openai):
    uuid = _make_recipe(client, auth_headers)
    _add_entry(client, auth_headers, "2026-06-22", uuid)
    resp = client.post(
        "/meal-plan/sync", headers=auth_headers, json={"start": "2026-06-22", "end": "2026-06-28"}
    )
    assert resp.status_code == 400


def test_sync_status_classifies_entries(client, auth_headers, mocked_openai, tmp_db_path):
    uuid = _make_recipe(client, auth_headers)
    synced = _add_entry(client, auth_headers, "2026-06-22", uuid)
    missing = _add_entry(client, auth_headers, "2026-06-23", uuid)
    unsynced = _add_entry(client, auth_headers, "2026-06-24", uuid)
    _connect_google(tmp_db_path)
    _set_event_id(tmp_db_path, synced, "evt-ok")
    _set_event_id(tmp_db_path, missing, "evt-gone")

    async def fake_exists(_token, _cal, event_id):
        return event_id == "evt-ok"

    with (
        patch("api.google_calendar.refresh_access_token", new=AsyncMock(return_value="at")),
        patch("api.google_calendar.event_exists", new=fake_exists),
    ):
        resp = client.post(
            "/meal-plan/sync-status",
            headers=auth_headers,
            json={"start": "2026-06-22", "end": "2026-06-28"},
        )
    body = resp.json()
    assert body["connected"] is True
    assert body["statuses"][str(synced)] == "synced"
    assert body["statuses"][str(missing)] == "missing"
    assert body["statuses"][str(unsynced)] == "unsynced"


def test_sync_status_expired_google_token_degrades_gracefully(
    client, auth_headers, mocked_openai, tmp_db_path
):
    """A lapsed Google authorization must NOT 401 (which logs the user out of
    the whole app). The read-only poll degrades to unsynced + needs_reconnect."""
    uuid = _make_recipe(client, auth_headers)
    entry_id = _add_entry(client, auth_headers, "2026-06-22", uuid)
    _connect_google(tmp_db_path)

    expired = AsyncMock(
        side_effect=HTTPException(status_code=409, detail="Google authorization expired")
    )
    with patch("api.google_calendar.refresh_access_token", new=expired):
        resp = client.post(
            "/meal-plan/sync-status",
            headers=auth_headers,
            json={"start": "2026-06-22", "end": "2026-06-28"},
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["connected"] is True
    assert body["needs_reconnect"] is True
    assert body["statuses"][str(entry_id)] == "unsynced"


def test_sync_expired_google_token_is_not_401(client, auth_headers, mocked_openai, tmp_db_path):
    """Interactive sync surfaces a reconnect (409), never a session-killing 401."""
    uuid = _make_recipe(client, auth_headers)
    _add_entry(client, auth_headers, "2026-06-22", uuid)
    _connect_google(tmp_db_path)

    expired = AsyncMock(
        side_effect=HTTPException(status_code=409, detail="Google authorization expired")
    )
    with patch("api.google_calendar.refresh_access_token", new=expired):
        resp = client.post(
            "/meal-plan/sync",
            headers=auth_headers,
            json={"start": "2026-06-22", "end": "2026-06-28"},
        )
    assert resp.status_code == 409


def test_sync_status_not_connected_all_unsynced(client, auth_headers, mocked_openai):
    uuid = _make_recipe(client, auth_headers)
    entry_id = _add_entry(client, auth_headers, "2026-06-22", uuid)
    resp = client.post(
        "/meal-plan/sync-status",
        headers=auth_headers,
        json={"start": "2026-06-22", "end": "2026-06-28"},
    )
    body = resp.json()
    assert body["connected"] is False
    assert body["statuses"][str(entry_id)] == "unsynced"


def test_delete_entry_removes_calendar_event(client, auth_headers, mocked_openai, tmp_db_path):
    uuid = _make_recipe(client, auth_headers)
    entry_id = _add_entry(client, auth_headers, "2026-06-22", uuid)
    _connect_google(tmp_db_path)
    _set_event_id(tmp_db_path, entry_id, "evt-del")

    delete = AsyncMock()
    with (
        patch("api.google_calendar.refresh_access_token", new=AsyncMock(return_value="at")),
        patch("api.google_calendar.delete_event", new=delete),
    ):
        resp = client.delete(f"/meal-plan/{entry_id}", headers=auth_headers)
    assert resp.status_code == 204
    assert delete.call_args.args == ("at", "primary", "evt-del")


def test_disconnect_clears_integration_and_event_ids(
    client, auth_headers, mocked_openai, tmp_db_path
):
    uuid = _make_recipe(client, auth_headers)
    entry_id = _add_entry(client, auth_headers, "2026-06-22", uuid)
    _connect_google(tmp_db_path)
    _set_event_id(tmp_db_path, entry_id, "evt-1")

    resp = client.delete("/integrations/google/connect", headers=auth_headers)
    assert resp.status_code == 204

    status = client.get("/integrations/google/status", headers=auth_headers).json()
    assert status["connected"] is False
    assert _event_id(tmp_db_path, entry_id) is None

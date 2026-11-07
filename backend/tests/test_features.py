"""Feature flags: the global ``planner`` switch between weekly plan and menus."""

import sqlite3

from passlib.context import CryptContext

from api import config, create_access_token

PWD = CryptContext(schemes=["bcrypt"])


def _user(db, email, admin=False):
    conn = sqlite3.connect(str(db))
    try:
        conn.execute(
            "INSERT INTO users (email, hashed_password, is_admin) VALUES (?, ?, ?)",
            (email, PWD.hash("password123"), int(admin)),
        )
        conn.commit()
    finally:
        conn.close()
    return {"Authorization": f"Bearer {create_access_token(data={'sub': email})}"}


def test_default_is_weekly(client, auth_headers):
    resp = client.get("/features", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json() == {"planner": "weekly"}


def test_env_default_is_used_until_set(client, auth_headers, monkeypatch):
    monkeypatch.setattr(config, "PLANNER_MODE", "menus")
    assert client.get("/features", headers=auth_headers).json()["planner"] == "menus"
    monkeypatch.setattr(config, "PLANNER_MODE", "nonsense")
    assert client.get("/features", headers=auth_headers).json()["planner"] == "weekly"


def test_admin_switches_planner_for_everyone(client, auth_headers, tmp_db_path):
    admin = _user(tmp_db_path, "admin@example.com", admin=True)
    resp = client.put("/admin/features", headers=admin, json={"planner": "menus"})
    assert resp.status_code == 200
    assert resp.json() == {"planner": "menus"}
    # Another user sees the switch.
    assert client.get("/features", headers=auth_headers).json()["planner"] == "menus"
    client.put("/admin/features", headers=admin, json={"planner": "weekly"})
    assert client.get("/features", headers=auth_headers).json()["planner"] == "weekly"


def test_non_admin_cannot_switch(client, auth_headers):
    resp = client.put("/admin/features", headers=auth_headers, json={"planner": "menus"})
    assert resp.status_code == 403
    assert client.get("/features", headers=auth_headers).json()["planner"] == "weekly"


def test_invalid_value_is_rejected(client, tmp_db_path):
    admin = _user(tmp_db_path, "admin@example.com", admin=True)
    resp = client.put("/admin/features", headers=admin, json={"planner": "monthly"})
    assert resp.status_code == 422


def test_features_need_auth(client):
    assert client.get("/features").status_code == 401

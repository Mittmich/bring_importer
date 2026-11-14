"""Admin control plane: revocable sessions, one-time links, admin endpoints."""

import sqlite3
from datetime import datetime, timedelta, timezone

import pytest
from passlib.context import CryptContext

from api import create_access_token

PWD = CryptContext(schemes=["bcrypt"])


def _add_user(db, email, password="password123", admin=False):
    conn = sqlite3.connect(str(db))
    try:
        cur = conn.execute(
            "INSERT INTO users (email, hashed_password, is_admin) VALUES (?, ?, ?)",
            (email, PWD.hash(password), int(admin)),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def _headers(email):
    return {"Authorization": f"Bearer {create_access_token(data={'sub': email})}"}


def _login(client, email, password="password123"):
    return client.post("/token", data={"username": email, "password": password})


def _q(db, sql, *args):
    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    try:
        return conn.execute(sql, args).fetchall()
    finally:
        conn.close()


@pytest.fixture
def admin(client, tmp_db_path):
    uid = _add_user(tmp_db_path, "admin@example.com", admin=True)
    return {"id": uid, "email": "admin@example.com", "headers": _headers("admin@example.com")}


@pytest.fixture
def bob(client, tmp_db_path):
    uid = _add_user(tmp_db_path, "bob@example.com")
    return {"id": uid, "email": "bob@example.com", "headers": _headers("bob@example.com")}


# ---------------------------------------------------------------------------
# Sessions
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_login_records_last_login_and_token_carries_version(client, tmp_db_path, bob):
    resp = _login(client, bob["email"])
    assert resp.status_code == 200
    token = resp.json()["access_token"]
    assert (
        client.get("/account/profile", headers={"Authorization": f"Bearer {token}"}).json()[
            "is_admin"
        ]
        is False
    )
    assert _q(tmp_db_path, "SELECT last_login_at FROM users WHERE id = ?", bob["id"])[0][0]


@pytest.mark.integration
def test_logout_everywhere_revokes_old_tokens(client, admin, bob):
    old = {"Authorization": f"Bearer {_login(client, bob['email']).json()['access_token']}"}
    legacy = bob["headers"]  # a pre-existing token without "ver"
    assert client.get("/recipes", headers=old).status_code == 200
    assert client.get("/recipes", headers=legacy).status_code == 200

    assert (
        client.post(f"/admin/users/{bob['id']}/logout", headers=admin["headers"]).status_code == 204
    )
    assert client.get("/recipes", headers=old).status_code == 401
    assert client.get("/recipes", headers=legacy).status_code == 401
    fresh = {"Authorization": f"Bearer {_login(client, bob['email']).json()['access_token']}"}
    assert client.get("/recipes", headers=fresh).status_code == 200


@pytest.mark.integration
def test_disable_blocks_login_and_sessions(client, admin, bob):
    assert (
        client.patch(
            f"/admin/users/{bob['id']}", headers=admin["headers"], json={"disabled": True}
        ).status_code
        == 204
    )
    assert client.get("/recipes", headers=bob["headers"]).status_code == 401
    assert _login(client, bob["email"]).status_code == 403
    assert _login(client, bob["email"], "wrong-password").status_code == 401  # no hint

    client.patch(f"/admin/users/{bob['id']}", headers=admin["headers"], json={"disabled": False})
    assert _login(client, bob["email"]).status_code == 200


# ---------------------------------------------------------------------------
# Access control and guard rails
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_admin_routes_require_admin(client, bob):
    assert client.get("/admin/users").status_code == 401
    assert client.get("/admin/users", headers=bob["headers"]).status_code == 403
    assert client.post("/admin/invites", headers=bob["headers"], json={}).status_code == 403
    assert client.delete("/admin/users/1?confirm=x", headers=bob["headers"]).status_code == 403


@pytest.mark.integration
def test_users_list_with_stats(client, admin, bob, tmp_db_path):
    client.post("/recipes", headers=bob["headers"], json={"title": "Soup"})
    users = {u["email"]: u for u in client.get("/admin/users", headers=admin["headers"]).json()}
    assert users["bob@example.com"]["recipe_count"] == 1
    assert users["bob@example.com"]["is_admin"] is False
    assert users["admin@example.com"]["is_self"] is True
    assert users["admin@example.com"]["is_admin"] is True


@pytest.mark.integration
def test_self_and_last_admin_guards(client, admin, bob):
    h = admin["headers"]
    assert (
        client.patch(f"/admin/users/{admin['id']}", headers=h, json={"is_admin": False}).status_code
        == 422
    )
    assert (
        client.patch(f"/admin/users/{admin['id']}", headers=h, json={"disabled": True}).status_code
        == 422
    )
    assert (
        client.delete(f"/admin/users/{admin['id']}?confirm={admin['email']}", headers=h).status_code
        == 422
    )

    # Promote bob; bob can then demote admin, but not the last remaining admin (himself).
    assert (
        client.patch(f"/admin/users/{bob['id']}", headers=h, json={"is_admin": True}).status_code
        == 204
    )
    bh = bob["headers"]
    assert (
        client.patch(
            f"/admin/users/{admin['id']}", headers=bh, json={"is_admin": False}
        ).status_code
        == 204
    )
    assert client.get("/admin/users", headers=h).status_code == 403  # admin is no longer one
    assert (
        client.patch(f"/admin/users/{bob['id']}", headers=bh, json={"is_admin": False}).status_code
        == 422
    )
    assert client.patch("/admin/users/9999", headers=bh, json={"disabled": True}).status_code == 404


# ---------------------------------------------------------------------------
# Sign-up links
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_invite_lifecycle(client, admin, tmp_db_path):
    created = client.post(
        "/admin/invites", headers=admin["headers"], json={"note": "for Anna", "expires_in_days": 3}
    ).json()
    token = created["token"]
    assert created["status"] == "active" and created["note"] == "for Anna"
    # Only a hash is stored.
    assert token not in str([dict(r) for r in _q(tmp_db_path, "SELECT * FROM auth_links")])

    assert client.get(f"/auth/links/{token}").json() == {"kind": "signup", "email": None}
    resp = client.post(
        "/auth/signup",
        json={
            "token": token,
            "email": "Anna@Example.com",
            "password": "anna-pass-1",
            "display_name": " Anna  B ",
        },
    )
    assert resp.status_code == 200
    me = client.get(
        "/account/profile", headers={"Authorization": f"Bearer {resp.json()['access_token']}"}
    ).json()
    assert me["email"] == "anna@example.com" and me["display_name"] == "Anna B"
    assert _login(client, "anna@example.com", "anna-pass-1").status_code == 200

    # Single use.
    assert client.get(f"/auth/links/{token}").status_code == 404
    again = client.post(
        "/auth/signup", json={"token": token, "email": "x@example.com", "password": "password123"}
    )
    assert again.status_code == 404

    listed = client.get("/admin/invites", headers=admin["headers"]).json()
    assert listed[0]["status"] == "used" and listed[0]["used_by"] == "anna@example.com"
    assert "token" not in listed[0]
    users = {u["email"]: u for u in client.get("/admin/users", headers=admin["headers"]).json()}
    assert users["anna@example.com"]["invited_by"] == "admin@example.com"
    assert users["anna@example.com"]["created_at"]


@pytest.mark.integration
def test_invite_locked_to_email_and_validation(client, admin, bob):
    h = admin["headers"]
    assert (
        client.post("/admin/invites", headers=h, json={"email": "bob@example.com"}).status_code
        == 409
    )
    assert client.post("/admin/invites", headers=h, json={"expires_in_days": 0}).status_code == 422
    assert client.post("/admin/invites", headers=h, json={"email": "nope"}).status_code == 422

    token = client.post("/admin/invites", headers=h, json={"email": "cara@example.com"}).json()[
        "token"
    ]
    assert client.get(f"/auth/links/{token}").json()["email"] == "cara@example.com"
    wrong = client.post(
        "/auth/signup", json={"token": token, "email": "dan@example.com", "password": "password123"}
    )
    assert wrong.status_code == 422
    short = client.post(
        "/auth/signup", json={"token": token, "email": "cara@example.com", "password": "short"}
    )
    assert short.status_code == 422
    ok = client.post(
        "/auth/signup",
        json={"token": token, "email": "cara@example.com", "password": "password123"},
    )
    assert ok.status_code == 200


@pytest.mark.integration
def test_open_invite_rejects_existing_email(client, admin, bob):
    token = client.post("/admin/invites", headers=admin["headers"], json={}).json()["token"]
    resp = client.post(
        "/auth/signup", json={"token": token, "email": "BOB@example.com", "password": "password123"}
    )
    assert resp.status_code == 409
    assert client.get(f"/auth/links/{token}").status_code == 200  # not consumed


@pytest.mark.integration
def test_revoked_and_expired_invites(client, admin, tmp_db_path):
    h = admin["headers"]
    revoked = client.post("/admin/invites", headers=h, json={}).json()
    assert client.delete(f"/admin/invites/{revoked['id']}", headers=h).status_code == 204
    assert client.get(f"/auth/links/{revoked['token']}").status_code == 404

    expired = client.post("/admin/invites", headers=h, json={}).json()
    past = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
    conn = sqlite3.connect(str(tmp_db_path))
    conn.execute("UPDATE auth_links SET expires_at = ? WHERE id = ?", (past, expired["id"]))
    conn.commit()
    conn.close()
    assert client.get(f"/auth/links/{expired['token']}").status_code == 404
    statuses = {i["id"]: i["status"] for i in client.get("/admin/invites", headers=h).json()}
    assert statuses == {revoked["id"]: "revoked", expired["id"]: "expired"}
    assert client.delete("/admin/invites/9999", headers=h).status_code == 404
    assert client.get("/auth/links/garbage").status_code == 404


# ---------------------------------------------------------------------------
# Password resets
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_reset_link_flow(client, admin, bob):
    old_session = {"Authorization": f"Bearer {_login(client, bob['email']).json()['access_token']}"}
    first = client.post(f"/admin/users/{bob['id']}/reset-link", headers=admin["headers"]).json()
    second = client.post(f"/admin/users/{bob['id']}/reset-link", headers=admin["headers"]).json()
    assert client.get(f"/auth/links/{first['token']}").status_code == 404  # superseded
    assert client.get(f"/auth/links/{second['token']}").json() == {
        "kind": "reset",
        "email": bob["email"],
    }

    assert (
        client.post("/auth/reset", json={"token": second["token"], "password": "short"}).status_code
        == 422
    )
    resp = client.post("/auth/reset", json={"token": second["token"], "password": "brand-new-pass"})
    assert resp.status_code == 200
    assert (
        client.get(
            "/recipes", headers={"Authorization": f"Bearer {resp.json()['access_token']}"}
        ).status_code
        == 200
    )
    assert client.get("/recipes", headers=old_session).status_code == 401  # other sessions gone
    assert _login(client, bob["email"]).status_code == 401
    assert _login(client, bob["email"], "brand-new-pass").status_code == 200
    assert (
        client.post(
            "/auth/reset", json={"token": second["token"], "password": "another-pass"}
        ).status_code
        == 404
    )


@pytest.mark.integration
def test_reset_link_not_usable_as_signup_and_disabled_user(client, admin, bob):
    token = client.post(f"/admin/users/{bob['id']}/reset-link", headers=admin["headers"]).json()[
        "token"
    ]
    signup = client.post(
        "/auth/signup", json={"token": token, "email": "z@example.com", "password": "password123"}
    )
    assert signup.status_code == 404
    client.patch(f"/admin/users/{bob['id']}", headers=admin["headers"], json={"disabled": True})
    assert (
        client.post("/auth/reset", json={"token": token, "password": "password123"}).status_code
        == 404
    )
    assert (
        client.post(f"/admin/users/{bob['id']}/reset-link", headers=admin["headers"]).status_code
        == 422
    )


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_delete_user_removes_their_data(client, admin, bob, tmp_db_path, tmp_path, monkeypatch):
    import base64
    import io

    from PIL import Image

    import api.config as config

    monkeypatch.setattr(config, "RECIPE_IMAGES_DIR", str(tmp_path / "images"))
    bh, ah = bob["headers"], admin["headers"]
    r1 = client.post("/recipes", headers=bh, json={"title": "Bob soup", "tags": ["Soup"]}).json()[
        "uuid"
    ]
    buf = io.BytesIO()
    Image.new("RGB", (40, 20)).save(buf, format="JPEG")
    client.put(
        f"/recipes/{r1}/image",
        headers=bh,
        json={"image": base64.b64encode(buf.getvalue()).decode()},
    )
    assert (tmp_path / "images" / f"{r1}.jpg").exists()
    admin_recipe = client.post("/recipes", headers=ah, json={"title": "Admin stew"}).json()["uuid"]

    conn = sqlite3.connect(str(tmp_db_path))
    conn.execute(
        "INSERT INTO meal_plan_entries (user_id, date, recipe_uuid) VALUES (?, '2026-11-06', ?)",
        (admin["id"], r1),
    )
    conn.execute(
        "INSERT INTO meal_plan_entries (user_id, date, recipe_uuid) VALUES (?, '2026-11-06', ?)",
        (bob["id"], admin_recipe),
    )
    conn.execute(
        "INSERT INTO friendships (requester_id, addressee_id, status) VALUES (?, ?, 'accepted')",
        (admin["id"], bob["id"]),
    )
    conn.commit()
    conn.close()

    assert (
        client.delete(f"/admin/users/{bob['id']}?confirm=wrong@example.com", headers=ah).status_code
        == 422
    )
    assert (
        client.delete(f"/admin/users/{bob['id']}?confirm=BOB@example.com", headers=ah).status_code
        == 204
    )

    assert _q(tmp_db_path, "SELECT * FROM users WHERE id = ?", bob["id"]) == []
    assert _q(tmp_db_path, "SELECT * FROM recipes WHERE user_id = ?", bob["id"]) == []
    assert _q(tmp_db_path, "SELECT * FROM tags WHERE user_id = ?", bob["id"]) == []
    assert (
        _q(
            tmp_db_path,
            "SELECT * FROM meal_plan_entries WHERE recipe_uuid = ? OR user_id = ?",
            r1,
            bob["id"],
        )
        == []
    )
    assert _q(tmp_db_path, "SELECT * FROM friendships") == []
    assert not (tmp_path / "images" / f"{r1}.jpg").exists()
    # The admin's own data is untouched.
    assert client.get(f"/recipes/{admin_recipe}.json", headers=ah).status_code == 200
    assert client.get("/recipes", headers=bh).status_code == 401
    assert (
        client.delete(f"/admin/users/{bob['id']}?confirm=bob@example.com", headers=ah).status_code
        == 404
    )


# ---------------------------------------------------------------------------
# Friendships and shares
# ---------------------------------------------------------------------------


@pytest.fixture
def carol(client, tmp_db_path):
    uid = _add_user(tmp_db_path, "carol@example.com")
    return {"id": uid, "email": "carol@example.com", "headers": _headers("carol@example.com")}


def _menu_of(client, user):
    return client.post("/menus", headers=user["headers"], json={"title": "Feast"}).json()["id"]


def test_friendship_and_share_routes_need_admin(client, bob, carol):
    h = bob["headers"]
    assert client.get("/admin/friendships", headers=h).status_code == 403
    body = {"user_a": bob["id"], "user_b": carol["id"]}
    assert client.post("/admin/friendships", headers=h, json=body).status_code == 403
    assert client.get("/admin/shares", headers=h).status_code == 403
    assert client.get(f"/admin/users/{bob['id']}/resources?type=menu", headers=h).status_code == 403


def test_admin_connects_lists_and_removes_friends(client, admin, bob, carol):
    h = admin["headers"]
    body = {"user_a": bob["id"], "user_b": carol["id"]}
    assert client.post("/admin/friendships", headers=h, json=body).status_code == 201
    assert client.post("/admin/friendships", headers=h, json=body).status_code == 409
    same = {"user_a": bob["id"], "user_b": bob["id"]}
    assert client.post("/admin/friendships", headers=h, json=same).status_code == 422
    # Both sides see the friendship.
    assert [f["email"] for f in client.get("/friends", headers=bob["headers"]).json()] == [
        "carol@example.com"
    ]
    rows = client.get(f"/admin/friendships?user_id={carol['id']}", headers=h).json()
    assert len(rows) == 1 and rows[0]["status"] == "accepted"
    assert rows[0]["requester"]["email"] == "bob@example.com"
    assert client.delete(f"/admin/friendships/{rows[0]['id']}", headers=h).status_code == 204
    assert client.get("/friends", headers=bob["headers"]).json() == []


def test_admin_connect_accepts_pending_request(client, admin, bob, carol):
    client.post("/friends/requests", headers=bob["headers"], json={"email": carol["email"]})
    body = {"user_a": carol["id"], "user_b": bob["id"]}
    assert client.post("/admin/friendships", headers=admin["headers"], json=body).status_code == 201
    rows = client.get("/admin/friendships", headers=admin["headers"]).json()
    assert [r["status"] for r in rows] == ["accepted"]


def test_admin_share_requires_friends_unless_ensured(client, admin, bob, carol):
    h = admin["headers"]
    mid = _menu_of(client, bob)
    share = {"type": "menu", "resource_id": mid, "user_id": carol["id"], "role": "editor"}
    assert client.post("/admin/shares", headers=h, json=share).status_code == 409
    resp = client.post("/admin/shares", headers=h, json={**share, "ensure_friends": True})
    assert resp.status_code == 201
    # Accepted at once: Carol can edit without accepting anything.
    menu = client.get(f"/menus/{mid}", headers=carol["headers"]).json()
    assert menu["role"] == "editor"
    assert len(client.get("/friends", headers=carol["headers"]).json()) == 1


def test_admin_share_validates_role_and_owner(client, admin, bob, carol):
    h = admin["headers"]
    mid = _menu_of(client, bob)
    base = {"type": "menu", "resource_id": mid, "ensure_friends": True}
    bad_role = {**base, "user_id": carol["id"], "role": "manager"}
    assert client.post("/admin/shares", headers=h, json=bad_role).status_code == 422
    to_owner = {**base, "user_id": bob["id"], "role": "viewer"}
    assert client.post("/admin/shares", headers=h, json=to_owner).status_code == 422
    missing = {**base, "resource_id": 9999, "user_id": carol["id"], "role": "viewer"}
    assert client.post("/admin/shares", headers=h, json=missing).status_code == 404


def test_admin_lists_patches_and_revokes_shares(client, admin, bob, carol):
    h = admin["headers"]
    mid = _menu_of(client, bob)
    cid = client.post("/cookbooks", headers=bob["headers"], json={"name": "Soups"}).json()["id"]
    for share in (
        {"type": "menu", "resource_id": mid, "role": "viewer"},
        {"type": "cookbook", "resource_id": cid, "role": "manager"},
    ):
        body = {**share, "user_id": carol["id"], "ensure_friends": True}
        assert client.post("/admin/shares", headers=h, json=body).status_code == 201

    rows = client.get(f"/admin/shares?user_id={carol['id']}", headers=h).json()
    assert sorted((r["type"], r["resource_name"], r["role"]) for r in rows) == [
        ("cookbook", "Soups", "manager"),
        ("menu", "Feast", "viewer"),
    ]
    assert all(r["owner"]["email"] == "bob@example.com" for r in rows)
    assert len(client.get("/admin/shares?type=menu", headers=h).json()) == 1

    path = f"/admin/shares/menu/{mid}/{carol['id']}"
    assert client.patch(path, headers=h, json={"role": "manager"}).status_code == 422
    assert client.patch(path, headers=h, json={"role": "editor"}).status_code == 204
    assert client.get(f"/menus/{mid}", headers=carol["headers"]).json()["role"] == "editor"
    assert client.delete(path, headers=h).status_code == 204
    assert client.get(f"/menus/{mid}", headers=carol["headers"]).status_code == 404
    assert client.delete(path, headers=h).status_code == 404


def test_admin_unfriend_revokes_shares(client, admin, bob, carol):
    h = admin["headers"]
    mid = _menu_of(client, bob)
    body = {"type": "menu", "resource_id": mid, "user_id": carol["id"], "role": "viewer"}
    client.post("/admin/shares", headers=h, json={**body, "ensure_friends": True})
    fid = client.get("/admin/friendships", headers=h).json()[0]["id"]
    assert client.delete(f"/admin/friendships/{fid}", headers=h).status_code == 204
    assert client.get("/admin/shares", headers=h).json() == []
    assert client.get(f"/menus/{mid}", headers=carol["headers"]).status_code == 404


def test_admin_lists_user_resources(client, admin, bob):
    _menu_of(client, bob)
    client.post("/cookbooks", headers=bob["headers"], json={"name": "Soups"})
    h = admin["headers"]
    menus = client.get(f"/admin/users/{bob['id']}/resources?type=menu", headers=h).json()
    assert [m["name"] for m in menus] == ["Feast"]
    books = client.get(f"/admin/users/{bob['id']}/resources?type=cookbook", headers=h).json()
    assert [b["name"] for b in books] == ["Soups"]


def test_delete_user_removes_menu_shares(client, admin, bob, carol, tmp_db_path):
    h = admin["headers"]
    bob_menu = _menu_of(client, bob)
    carol_menu = _menu_of(client, carol)
    for mid, grantee in ((bob_menu, carol["id"]), (carol_menu, bob["id"])):
        body = {"type": "menu", "resource_id": mid, "user_id": grantee, "role": "viewer"}
        client.post("/admin/shares", headers=h, json={**body, "ensure_friends": True})
    resp = client.delete(f"/admin/users/{bob['id']}?confirm={bob['email']}", headers=h)
    assert resp.status_code == 204
    assert _q(tmp_db_path, "SELECT * FROM menu_members") == []

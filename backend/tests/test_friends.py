"""Integration tests for the friend graph (Phase 1 of sharing).

User A is the seeded user (``auth_headers``); B and C are created per-test with
``_make_user``. Tables already exist because the ``client`` fixture ran
``init_db`` first.
"""

import sqlite3

import pytest
from passlib.context import CryptContext

from api import create_access_token

_pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")


def _make_user(tmp_db_path, email: str):
    """Insert a user and return (id, email, auth_headers)."""
    conn = sqlite3.connect(str(tmp_db_path))
    try:
        conn.execute(
            "INSERT INTO users (email, hashed_password) VALUES (?, ?)",
            (email, _pwd.hash("pw")),
        )
        conn.commit()
        uid = conn.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()[0]
    finally:
        conn.close()
    headers = {"Authorization": f"Bearer {create_access_token(data={'sub': email})}"}
    return uid, email, headers


def _emails(items):
    return sorted(i["email"] for i in items)


@pytest.mark.integration
def test_send_request_shows_in_both_inboxes(client, auth_headers, tmp_db_path):
    _, b_email, b_headers = _make_user(tmp_db_path, "b@example.com")

    resp = client.post("/friends/requests", headers=auth_headers, json={"email": b_email})
    assert resp.status_code == 200
    assert resp.json()["status"] == "pending"

    out = client.get("/friends/requests?direction=outgoing", headers=auth_headers).json()
    assert _emails(out) == ["b@example.com"]
    inc = client.get("/friends/requests?direction=incoming", headers=b_headers).json()
    assert _emails(inc) == ["test@example.com"]
    # Not friends yet.
    assert client.get("/friends", headers=auth_headers).json() == []


@pytest.mark.integration
def test_accept_creates_mutual_friendship(client, auth_headers, tmp_db_path):
    _, b_email, b_headers = _make_user(tmp_db_path, "b@example.com")
    client.post("/friends/requests", headers=auth_headers, json={"email": b_email})
    req_id = client.get("/friends/requests?direction=incoming", headers=b_headers).json()[0]["id"]

    assert client.post(f"/friends/requests/{req_id}/accept", headers=b_headers).status_code == 200

    assert _emails(client.get("/friends", headers=auth_headers).json()) == ["b@example.com"]
    assert _emails(client.get("/friends", headers=b_headers).json()) == ["test@example.com"]
    # No lingering pending requests.
    assert client.get("/friends/requests?direction=incoming", headers=b_headers).json() == []


@pytest.mark.integration
def test_mutual_requests_auto_accept(client, auth_headers, tmp_db_path):
    _, b_email, b_headers = _make_user(tmp_db_path, "b@example.com")
    client.post("/friends/requests", headers=auth_headers, json={"email": b_email})

    # B sends back to A while A's request is pending → instant friendship.
    resp = client.post("/friends/requests", headers=b_headers, json={"email": "test@example.com"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "accepted"
    assert _emails(client.get("/friends", headers=b_headers).json()) == ["test@example.com"]


@pytest.mark.integration
def test_cannot_friend_self(client, auth_headers):
    resp = client.post(
        "/friends/requests", headers=auth_headers, json={"email": "test@example.com"}
    )
    assert resp.status_code == 422


@pytest.mark.integration
def test_request_unknown_email_404(client, auth_headers):
    resp = client.post(
        "/friends/requests", headers=auth_headers, json={"email": "nobody@example.com"}
    )
    assert resp.status_code == 404


@pytest.mark.integration
def test_duplicate_request_conflicts(client, auth_headers, tmp_db_path):
    _, b_email, _ = _make_user(tmp_db_path, "b@example.com")
    client.post("/friends/requests", headers=auth_headers, json={"email": b_email})
    resp = client.post("/friends/requests", headers=auth_headers, json={"email": b_email})
    assert resp.status_code == 409


@pytest.mark.integration
def test_request_when_already_friends_conflicts(client, auth_headers, tmp_db_path):
    _, b_email, b_headers = _make_user(tmp_db_path, "b@example.com")
    client.post("/friends/requests", headers=auth_headers, json={"email": b_email})
    req_id = client.get("/friends/requests?direction=incoming", headers=b_headers).json()[0]["id"]
    client.post(f"/friends/requests/{req_id}/accept", headers=b_headers)

    resp = client.post("/friends/requests", headers=auth_headers, json={"email": b_email})
    assert resp.status_code == 409


@pytest.mark.integration
def test_decline_removes_and_allows_resend(client, auth_headers, tmp_db_path):
    _, b_email, b_headers = _make_user(tmp_db_path, "b@example.com")
    client.post("/friends/requests", headers=auth_headers, json={"email": b_email})
    req_id = client.get("/friends/requests?direction=incoming", headers=b_headers).json()[0]["id"]

    assert client.post(f"/friends/requests/{req_id}/decline", headers=b_headers).status_code == 204
    assert client.get("/friends/requests?direction=incoming", headers=b_headers).json() == []
    # Can be re-sent after a decline.
    assert (
        client.post("/friends/requests", headers=auth_headers, json={"email": b_email}).status_code
        == 200
    )


@pytest.mark.integration
def test_only_addressee_can_accept(client, auth_headers, tmp_db_path):
    _, b_email, _ = _make_user(tmp_db_path, "b@example.com")
    _, _, c_headers = _make_user(tmp_db_path, "c@example.com")
    client.post("/friends/requests", headers=auth_headers, json={"email": b_email})
    req_id = client.get("/friends/requests?direction=outgoing", headers=auth_headers).json()[0][
        "id"
    ]

    # The requester (A) can't accept their own request; an unrelated user (C) can't either.
    assert (
        client.post(f"/friends/requests/{req_id}/accept", headers=auth_headers).status_code == 404
    )
    assert client.post(f"/friends/requests/{req_id}/accept", headers=c_headers).status_code == 404


@pytest.mark.integration
def test_unfriend_removes_relationship(client, auth_headers, tmp_db_path):
    b_id, b_email, b_headers = _make_user(tmp_db_path, "b@example.com")
    client.post("/friends/requests", headers=auth_headers, json={"email": b_email})
    req_id = client.get("/friends/requests?direction=incoming", headers=b_headers).json()[0]["id"]
    client.post(f"/friends/requests/{req_id}/accept", headers=b_headers)

    assert client.delete(f"/friends/{b_id}", headers=auth_headers).status_code == 204
    assert client.get("/friends", headers=auth_headers).json() == []
    assert client.get("/friends", headers=b_headers).json() == []


@pytest.mark.integration
def test_unfriend_cancels_outgoing_request(client, auth_headers, tmp_db_path):
    b_id, b_email, b_headers = _make_user(tmp_db_path, "b@example.com")
    client.post("/friends/requests", headers=auth_headers, json={"email": b_email})

    assert client.delete(f"/friends/{b_id}", headers=auth_headers).status_code == 204
    assert client.get("/friends/requests?direction=incoming", headers=b_headers).json() == []


@pytest.mark.integration
def test_friends_endpoints_require_auth(client):
    assert client.get("/friends").status_code == 401
    assert client.post("/friends/requests", json={"email": "x@example.com"}).status_code == 401

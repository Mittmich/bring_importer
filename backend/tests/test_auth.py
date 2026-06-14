"""Unit and integration tests for authentication (``/token`` and JWT verification).

The protected endpoint used to exercise ``get_current_user`` is
``POST /recipes/parse``. We do NOT mock OpenAI for the auth-failure cases
(auth is checked first; the request never reaches the parser); for the
auth-success case we use the ``mocked_openai`` fixture so the call returns
cleanly.
"""

from datetime import datetime, timedelta

import jwt
import pytest

import api

# ---------------------------------------------------------------------------
# POST /token — login
# ---------------------------------------------------------------------------


def test_token_with_correct_credentials_returns_200(client, seed_user):
    resp = client.post(
        "/token",
        data={"username": seed_user["email"], "password": seed_user["password"]},
    )
    assert resp.status_code == 200


def test_token_response_shape(client, seed_user):
    resp = client.post(
        "/token",
        data={"username": seed_user["email"], "password": seed_user["password"]},
    )
    body = resp.json()
    assert "access_token" in body
    assert body["token_type"] == "bearer"
    # The token is a non-empty string and looks like a JWT (three dot-separated
    # base64-ish segments).
    assert isinstance(body["access_token"], str)
    assert body["access_token"].count(".") == 2


def test_token_with_wrong_password_returns_401(client, seed_user):
    resp = client.post(
        "/token",
        data={"username": seed_user["email"], "password": "WRONG"},
    )
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Incorrect email or password"


def test_token_with_unknown_user_returns_401(client):
    resp = client.post(
        "/token",
        data={"username": "nobody@example.com", "password": "anything"},
    )
    assert resp.status_code == 401
    # No user enumeration: same detail for "unknown user" and "wrong password".
    assert resp.json()["detail"] == "Incorrect email or password"


def test_token_with_missing_form_fields_returns_422(client):
    # No username, no password.
    resp = client.post("/token", data={})
    assert resp.status_code == 422


def test_token_with_missing_password_returns_422(client, seed_user):
    resp = client.post("/token", data={"username": seed_user["email"]})
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# JWT verification — get_current_user
# ---------------------------------------------------------------------------


@pytest.fixture
def valid_bearer(client, auth_headers):
    return auth_headers["Authorization"]


def test_protected_endpoint_with_valid_token_succeeds(client, valid_bearer, mocked_openai):
    """A real, valid JWT must pass the auth check and reach the handler."""
    # The parse endpoint requires `image` form data. Use a tiny base64 stub.
    resp = client.post(
        "/recipes/parse",
        headers={"Authorization": valid_bearer},
        data={"image": "aGVsbG8="},  # "hello" in base64
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "uuid" in body
    assert "url" in body
    assert body["url"].endswith(".json")


def test_protected_endpoint_without_auth_header_returns_401(client):
    resp = client.post("/recipes/parse", data={"image": "aGVsbG8="})
    assert resp.status_code == 401
    assert resp.headers.get("www-authenticate") == "Bearer"


def test_protected_endpoint_with_malformed_authorization_header_returns_401(client):
    resp = client.post(
        "/recipes/parse",
        headers={"Authorization": "NotBearer somegarbage"},
        data={"image": "aGVsbG8="},
    )
    assert resp.status_code == 401


def test_protected_endpoint_with_expired_token_returns_401(client, seed_user, monkeypatch):
    """A token whose ``exp`` is in the past must be rejected."""
    # Build an already-expired token using the same secret.
    expired = jwt.encode(
        {
            "sub": seed_user["email"],
            "exp": datetime.utcnow() - timedelta(minutes=5),
        },
        api.SECRET_KEY,
        algorithm=api.ALGORITHM,
    )
    resp = client.post(
        "/recipes/parse",
        headers={"Authorization": f"Bearer {expired}"},
        data={"image": "aGVsbG8="},
    )
    assert resp.status_code == 401


def test_protected_endpoint_with_token_signed_by_wrong_secret_returns_401(client, seed_user):
    bad = jwt.encode(
        {"sub": seed_user["email"], "exp": datetime.utcnow() + timedelta(minutes=10)},
        "totally-wrong-secret",
        algorithm=api.ALGORITHM,
    )
    resp = client.post(
        "/recipes/parse",
        headers={"Authorization": f"Bearer {bad}"},
        data={"image": "aGVsbG8="},
    )
    assert resp.status_code == 401


def test_protected_endpoint_with_token_missing_sub_claim_returns_401(client):
    """A token that decodes but has no ``sub`` must be rejected."""
    no_sub = jwt.encode(
        {"exp": datetime.utcnow() + timedelta(minutes=10)},  # no 'sub'
        api.SECRET_KEY,
        algorithm=api.ALGORITHM,
    )
    resp = client.post(
        "/recipes/parse",
        headers={"Authorization": f"Bearer {no_sub}"},
        data={"image": "aGVsbG8="},
    )
    assert resp.status_code == 401


def test_protected_endpoint_with_garbage_token_returns_401(client):
    resp = client.post(
        "/recipes/parse",
        headers={"Authorization": "Bearer not-a-jwt"},
        data={"image": "aGVsbG8="},
    )
    assert resp.status_code == 401


def test_protected_endpoint_with_token_for_unknown_user_returns_401(client):
    """Valid signature, valid shape, but ``sub`` doesn't match any user."""
    ghost = jwt.encode(
        {"sub": "ghost@example.com", "exp": datetime.utcnow() + timedelta(minutes=10)},
        api.SECRET_KEY,
        algorithm=api.ALGORITHM,
    )
    resp = client.post(
        "/recipes/parse",
        headers={"Authorization": f"Bearer {ghost}"},
        data={"image": "aGVsbG8="},
    )
    assert resp.status_code == 401

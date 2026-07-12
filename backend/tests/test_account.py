"""Tests for self-service password change (POST /account/password)."""

import pytest


def _login(client, email, password):
    return client.post("/token", data={"username": email, "password": password})


@pytest.mark.integration
def test_change_password_updates_login(client, auth_headers, seed_user):
    resp = client.post(
        "/account/password",
        headers=auth_headers,
        json={"current_password": "correctpassword", "new_password": "brandnewpass1"},
    )
    assert resp.status_code == 204

    # New password works; old one no longer does.
    assert _login(client, seed_user["email"], "brandnewpass1").status_code == 200
    assert _login(client, seed_user["email"], "correctpassword").status_code == 401


@pytest.mark.integration
def test_change_password_wrong_current_is_403(client, auth_headers, seed_user):
    resp = client.post(
        "/account/password",
        headers=auth_headers,
        json={"current_password": "wrongpassword", "new_password": "brandnewpass1"},
    )
    assert resp.status_code == 403
    # Password unchanged.
    assert _login(client, seed_user["email"], "correctpassword").status_code == 200


@pytest.mark.integration
def test_change_password_too_short_is_422(client, auth_headers, seed_user):
    resp = client.post(
        "/account/password",
        headers=auth_headers,
        json={"current_password": "correctpassword", "new_password": "short"},
    )
    assert resp.status_code == 422
    assert _login(client, seed_user["email"], "correctpassword").status_code == 200


@pytest.mark.integration
def test_change_password_requires_auth(client):
    resp = client.post(
        "/account/password",
        json={"current_password": "x", "new_password": "brandnewpass1"},
    )
    assert resp.status_code == 401


@pytest.mark.integration
def test_profile_default_and_update(client, auth_headers, seed_user):
    prof = client.get("/account/profile", headers=auth_headers).json()
    assert prof == {"email": seed_user["email"], "display_name": ""}

    resp = client.put(
        "/account/profile", headers=auth_headers, json={"display_name": "  Chef Mike  "}
    )
    assert resp.status_code == 200
    assert resp.json()["display_name"] == "Chef Mike"  # trimmed
    assert (
        client.get("/account/profile", headers=auth_headers).json()["display_name"] == "Chef Mike"
    )


@pytest.mark.integration
def test_display_name_too_long_is_422(client, auth_headers):
    resp = client.put("/account/profile", headers=auth_headers, json={"display_name": "x" * 61})
    assert resp.status_code == 422

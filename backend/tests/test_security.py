"""Regression tests for the 2026-11-05 security audit fixes."""

import json
import os
import re
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from api.bring_page import recipe_page, script_safe_json

XSS_NAME = "</script><script>alert(document.cookie)</script><img src=x onerror=alert(1)>"


def _jsonld(html: str) -> dict:
    match = re.search(r'<script type="application/ld\+json">\s*(.*?)\s*</script>', html, re.S)
    assert match, html
    return json.loads(match.group(1))


# --- Stored XSS in the Bring pages ------------------------------------------


def test_bring_page_escapes_markup_and_keeps_valid_jsonld():
    resp = recipe_page(XSS_NAME, {"@type": "Recipe", "name": XSS_NAME}, lang='en"><script>')
    html = bytes(resp.body).decode()
    # Exactly one script element: the JSON-LD one. Nothing breaks out of it.
    assert html.count("<script") == 1
    assert "<img" not in html
    assert 'lang="en"' in html
    # Bring still reads the exact original name.
    assert _jsonld(html)["name"] == XSS_NAME
    assert "default-src 'none'" in resp.headers["content-security-policy"]
    assert resp.headers["x-content-type-options"] == "nosniff"


def test_script_safe_json_round_trips():
    data = {"a": "</script>&<>", "b": ["ü", 1]}
    text = script_safe_json(data)
    assert "<" not in text and ">" not in text and "&" not in text
    assert json.loads(text) == data


@pytest.mark.integration
def test_recipe_html_endpoint_is_not_injectable(client, auth_headers):
    created = client.post(
        "/recipes",
        headers=auth_headers,
        json={"title": XSS_NAME, "ingredients": [{"amount": "1", "name": "</script>x"}]},
    )
    assert created.status_code == 200, created.text
    resp = client.get(f"/recipes/{created.json()['uuid']}.html")
    assert resp.status_code == 200
    assert resp.text.count("<script") == 1
    assert "<img" not in resp.text
    assert _jsonld(resp.text)["name"] == XSS_NAME
    assert "content-security-policy" in resp.headers


# --- Token confusion --------------------------------------------------------


@pytest.mark.integration
def test_google_state_token_is_not_a_session(client, seed_user):
    from api.routers.integrations import _encode_state

    state = _encode_state(seed_user["email"])
    resp = client.get("/account/profile", headers={"Authorization": f"Bearer {state}"})
    assert resp.status_code == 401


# --- Brute force ------------------------------------------------------------


def _login(client, email, password, ip="198.51.100.7"):
    return client.post(
        "/token", data={"username": email, "password": password}, headers={"X-Real-IP": ip}
    )


@pytest.mark.integration
def test_login_locks_after_repeated_failures_per_account(client, seed_user):
    from api import rate_limit

    for i in range(rate_limit.LOGIN_FAILURES_PER_EMAIL):
        assert _login(client, seed_user["email"], "wrong", ip=f"203.0.113.{i}").status_code == 401
    # Even the right password is refused while locked, from any address.
    locked = _login(client, seed_user["email"], seed_user["password"], ip="192.0.2.1")
    assert locked.status_code == 429
    assert "Retry-After" in locked.headers


@pytest.mark.integration
def test_login_limits_failures_per_address(client, seed_user):
    from api import rate_limit

    for i in range(rate_limit.LOGIN_FAILURES_PER_IP):
        _login(client, f"nobody{i}@example.com", "wrong")
    assert _login(client, seed_user["email"], seed_user["password"]).status_code == 429
    # Another address is unaffected.
    assert (
        _login(client, seed_user["email"], seed_user["password"], ip="192.0.2.9").status_code == 200
    )


@pytest.mark.integration
def test_successful_login_clears_account_failures(client, seed_user):
    from api import rate_limit

    for _ in range(rate_limit.LOGIN_FAILURES_PER_EMAIL - 1):
        _login(client, seed_user["email"], "wrong")
    assert _login(client, seed_user["email"], seed_user["password"]).status_code == 200
    for _ in range(rate_limit.LOGIN_FAILURES_PER_EMAIL - 1):
        _login(client, seed_user["email"], "wrong")
    assert _login(client, seed_user["email"], seed_user["password"]).status_code == 200


@pytest.mark.integration
def test_link_guessing_is_limited(client):
    from api import rate_limit

    headers = {"X-Real-IP": "198.51.100.20"}
    for i in range(rate_limit.LINK_FAILURES_PER_IP):
        assert client.get(f"/auth/links/guess{i}", headers=headers).status_code == 404
    assert client.get("/auth/links/another", headers=headers).status_code == 429
    resp = client.post(
        "/auth/reset", headers=headers, json={"token": "x", "password": "longenough1"}
    )
    assert resp.status_code == 429


@pytest.mark.integration
def test_unknown_email_still_runs_a_password_check(client, seed_user):
    with patch("api.auth.verify_password", return_value=False) as verify:
        assert _login(client, "ghost@example.com", "whatever").status_code == 401
    assert verify.call_count == 1


# --- CORS ------------------------------------------------------------------


@pytest.mark.integration
def test_cors_allows_only_configured_origins(client):
    def preflight(origin):
        return client.options(
            "/health",
            headers={"Origin": origin, "Access-Control-Request-Method": "GET"},
        )

    assert preflight("https://evil.example").headers.get("access-control-allow-origin") is None
    allowed = preflight("http://localhost:5173")
    assert allowed.headers.get("access-control-allow-origin") == "http://localhost:5173"
    assert allowed.headers.get("access-control-allow-credentials") is None


# --- OAuth callback ---------------------------------------------------------


@pytest.mark.integration
def test_oauth_error_is_url_encoded(client):
    resp = client.get(
        "/integrations/google/callback",
        params={"error": "x&google=connected#frag"},
        follow_redirects=False,
    )
    location = resp.headers["location"]
    assert "google=connected" not in location
    assert "#" not in location


# --- SECRET_KEY -------------------------------------------------------------


@pytest.mark.parametrize("value", ["", "please_change_this_to_a_random_key_in_production"])
def test_missing_or_placeholder_secret_key_is_replaced(value):
    env = {**os.environ, "SECRET_KEY": value}
    out = subprocess.run(
        [sys.executable, "-c", "import api.config as c; print(len(c.SECRET_KEY), c.SECRET_KEY)"],
        env=env,
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        check=True,
    )
    length, key = out.stdout.split()
    assert key != "please_change_this_to_a_random_key_in_production"
    assert int(length) >= 32
    assert "SECRET_KEY is not set" in out.stderr

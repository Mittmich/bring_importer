"""SSRF guard for URL import (api/safe_fetch.py)."""

import asyncio

import httpx
import pytest

from api.safe_fetch import FetchError, fetch_page, is_public_address


def _fetch(url, max_bytes=1024):
    return asyncio.run(fetch_page(url, headers={}, timeout=5.0, max_bytes=max_bytes))


def _ok(request):
    return httpx.Response(200, text="<p>hi</p>", headers={"Content-Type": "text/html"})


@pytest.mark.parametrize(
    "ip",
    [
        "127.0.0.1",
        "10.0.0.5",
        "172.17.0.2",
        "192.168.1.1",
        "169.254.169.254",
        "100.64.0.1",
        "0.0.0.0",
        "::1",
        "fd00::1",
        "fe80::1",
        "::ffff:127.0.0.1",
        "224.0.0.1",
    ],
)
def test_non_public_addresses_are_refused(ip):
    assert not is_public_address(ip)


def test_public_addresses_are_allowed():
    assert is_public_address("93.184.215.14")
    assert is_public_address("2606:4700::6810:84e5")


def test_happy_path_returns_text(fake_web):
    with fake_web(_ok):
        final, text = _fetch("https://example.test/recipe")
    assert final == "https://example.test/recipe"
    assert text == "<p>hi</p>"


@pytest.mark.parametrize(
    "url",
    ["http://127.0.0.1:8001/health", "http://169.254.169.254/latest/meta-data/", "http://[::1]/"],
)
def test_literal_internal_ips_are_refused(fake_web, url):
    with fake_web(_ok), pytest.raises(FetchError, match="can't be imported"):
        _fetch(url)


def test_hostname_resolving_to_internal_ip_is_refused(fake_web):
    with (
        fake_web(_ok, resolve={"evil.test": ["93.184.215.14", "10.0.0.1"]}),
        pytest.raises(FetchError, match="can't be imported"),
    ):
        _fetch("https://evil.test/")


@pytest.mark.parametrize(
    "url", ["file:///etc/passwd", "ftp://example.test/", "javascript:alert(1)"]
)
def test_other_schemes_are_refused(fake_web, url):
    with fake_web(_ok), pytest.raises(FetchError):
        _fetch(url)


def test_redirect_to_internal_address_is_refused(fake_web):
    def handler(request):
        if request.url.host == "example.test":
            return httpx.Response(302, headers={"Location": "http://127.0.0.1:8001/admin/users"})
        raise AssertionError("must not reach the internal address")

    with fake_web(handler), pytest.raises(FetchError, match="can't be imported"):
        _fetch("https://example.test/start")


def test_public_redirect_is_followed(fake_web):
    def handler(request):
        if request.url.path == "/old":
            return httpx.Response(301, headers={"Location": "/new"})
        return _ok(request)

    with fake_web(handler):
        final, _ = _fetch("https://example.test/old")
    assert final == "https://example.test/new"


def test_redirect_loop_stops(fake_web):
    def handler(request):
        return httpx.Response(302, headers={"Location": "/again"})

    with fake_web(handler), pytest.raises(FetchError, match="too many"):
        _fetch("https://example.test/")


def test_oversized_body_is_refused_while_streaming(fake_web):
    def handler(request):
        return httpx.Response(200, content=b"x" * 5000)

    with fake_web(handler), pytest.raises(FetchError, match="too large"):
        _fetch("https://example.test/")


def test_http_errors_are_reported(fake_web):
    with (
        fake_web(lambda r: httpx.Response(404)),
        pytest.raises(FetchError, match="HTTP 404"),
    ):
        _fetch("https://example.test/")


def test_import_url_endpoint_refuses_internal_targets(
    client, auth_headers, mocked_openai, fake_web
):
    with fake_web(_ok, resolve={"localhost": ["127.0.0.1", "::1"]}):
        resp = client.post(
            "/recipes/import-url",
            headers=auth_headers,
            json={"url": "http://localhost:8001/health"},
        )
    assert resp.status_code == 422
    assert "can't be imported" in resp.json()["detail"]


def test_import_url_endpoint_refuses_metadata_ip(client, auth_headers, mocked_openai, fake_web):
    with fake_web(_ok):
        resp = client.post(
            "/recipes/import-url",
            headers=auth_headers,
            json={"url": "http://169.254.169.254/latest/meta-data/"},
        )
    assert resp.status_code == 422
    assert "can't be imported" in resp.json()["detail"]

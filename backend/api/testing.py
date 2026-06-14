"""Test-only mocks activated by the ``RECIPE_TEST_MOCKS`` environment variable.

When ``RECIPE_TEST_MOCKS=1`` is in the environment at import time of
``api.main``, this module installs request-level stubs for:

  - ``POST https://api.openai.com/v1/chat/completions`` (image + text flows)
  - ``GET`` to arbitrary URLs (URL import flow)

The stubs return canned schema.org/Recipe HTML so the backend can
exercise its full parsing and storage code without any real network
calls. The Playwright config sets ``RECIPE_TEST_MOCKS=1`` in the
``webServer`` environment, so the uvicorn-spawned backend has the mocks
installed before the first request.

These stubs are intentionally minimal: a single image-openai response and
a single text-openai response that the parse flow can use, plus URL
responses keyed by the URL being fetched. The URL stub returns a static
JSON-LD page that exercises the JSON-LD-first path of the URL import
flow.

This module is imported once, and only when the env var is set. In
production it is a no-op.
"""

from __future__ import annotations

import os
from urllib.parse import urlparse

import requests
import responses as responses_lib

# Canned image-extraction response (used by /recipes/parse and
# the URL import's OpenAI text fallback).
CANONICAL_RECIPE_HTML = """\
<div itemscope itemtype="https://schema.org/Recipe">
  <h1 itemprop="name">Test Pancakes</h1>
  <span itemprop="recipeYield">4 servings</span>
  <p itemprop="description">Light and fluffy.</p>
  <ul>
    <li itemprop="recipeIngredient">1 cup flour</li>
    <li itemprop="recipeIngredient">2 eggs</li>
    <li itemprop="recipeIngredient">1 cup milk</li>
  </ul>
</div>
"""

# Canned URL-import response (used when a URL is fetched server-side
# and exercises the JSON-LD-first path). Keyed by URL.
URL_RESPONSES: dict[str, str] = {
    "https://example.test/recipe": """\
<html>
<head>
<script type="application/ld+json">
{
  "@context": "https://schema.org",
  "@type": "Recipe",
  "name": "Test URL Recipe",
  "recipeIngredient": ["1 cup flour", "2 eggs"],
  "recipeYield": "4 servings",
  "description": "Imported from a mocked URL."
}
</script>
</head>
<body><h1>Test URL Recipe</h1></body>
</html>
""",
}


def install() -> None:
    """Install the request stubs in-process. Idempotent."""
    if os.environ.get("RECIPE_TEST_MOCKS") != "1":
        return

    rsps = responses_lib.RequestsMock(assert_all_requests_are_fired=False)
    rsps.start()

    # Image + text fallback: any OpenAI chat completion returns the
    # canonical recipe HTML wrapped in OpenAI's response shape. We use
    # `add` (not `add_callback`) because `add_callback` with a tuple
    # return trips responses' body-validation; the canned body is the
    # same for every call so a static payload is fine.
    openai_body = {"choices": [{"message": {"content": CANONICAL_RECIPE_HTML}}]}
    rsps.add(
        responses_lib.POST,
        "https://api.openai.com/v1/chat/completions",
        json=openai_body,
        status=200,
    )

    # Allow the Bring widget script through (real, but the test page
    # may not actually load it).
    rsps.add_passthru("https://platform.getbring.com")

    # URL import: route the request through the URL_RESPONSES table
    # first, then fall back to a generic 404 if the URL isn't known.
    # ``responses`` doesn't natively support per-URL arbitrary
    # callbacks, so we wrap ``requests.get`` directly.
    _orig_get = requests.get

    def _patched_get(url, *args, **kwargs):
        # Normalize and check our response table.
        parsed = url if isinstance(url, str) else urlparse(url).geturl()
        if parsed in URL_RESPONSES:
            body = URL_RESPONSES[parsed]
            resp = requests.models.Response()
            resp.status_code = 200
            resp._content = body.encode("utf-8")
            resp.headers["Content-Type"] = "text/html; charset=utf-8"
            resp.url = parsed
            return resp
        # Unknown URL: forward to the original (so the real network is
        # attempted; the test should be mocking what it needs).
        return _orig_get(url, *args, **kwargs)

    requests.get = _patched_get  # type: ignore[assignment]

    # Same for httpx, which the URL import flow uses for the actual
    # outbound fetch. The URL import uses ``httpx.AsyncClient`` as a
    # context manager, so we install a ``MockTransport`` that
    # intercepts the request. ``MockTransport`` is the recommended way
    # to stub httpx.
    import httpx as _httpx

    def _handle_httpx(request: _httpx.Request) -> _httpx.Response:
        url = str(request.url)
        if url in URL_RESPONSES:
            return _httpx.Response(
                200,
                content=URL_RESPONSES[url].encode("utf-8"),
                headers={"Content-Type": "text/html; charset=utf-8"},
                request=request,
            )
        return _httpx.Response(404, request=request)

    mock_transport = _httpx.MockTransport(_handle_httpx)

    # Patch httpx.AsyncClient to default to the mock transport. The URL
    # import flow doesn't pass a ``transport=`` arg, so the default
    # transport swap is enough.
    _orig_async_client = _httpx.AsyncClient

    def _patched_async_client(*args, **kwargs):
        kwargs.setdefault("transport", mock_transport)
        return _orig_async_client(*args, **kwargs)

    _httpx.AsyncClient = _patched_async_client  # type: ignore[assignment,misc]

    # Auto-seed a test user on first import. This is the user the E2E
    # tests log in as. Only happens when RECIPE_TEST_MOCKS=1.
    from passlib.context import CryptContext

    from api.db import get_db_connection, init_db  # noqa: E402

    init_db()
    pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")
    conn = get_db_connection()
    try:
        row = conn.execute("SELECT id FROM users WHERE email = ?", ("test@example.com",)).fetchone()
        if row is None:
            conn.execute(
                "INSERT INTO users (email, hashed_password) VALUES (?, ?)",
                ("test@example.com", pwd.hash("correctpassword")),
            )
            conn.commit()
    finally:
        conn.close()

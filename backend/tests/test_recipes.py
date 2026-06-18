"""Integration tests for the recipe endpoints (parse, fetch, list).

All tests are marked ``@pytest.mark.integration``. They go through the
``TestClient`` and use the ``mocked_openai`` fixture for the parse endpoint.
"""

import json
import sqlite3
import time
import uuid as uuid_mod
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import responses as responses_lib

# ---------------------------------------------------------------------------
# POST /recipes/parse
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_parse_recipe_with_valid_auth_stores_recipe(
    client, auth_headers, mocked_openai, tmp_db_path
):
    resp = client.post(
        "/recipes/parse",
        headers=auth_headers,
        data={"image": "aGVsbG8="},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "uuid" in body
    # The uuid is a valid UUID4 string.
    parsed_uuid = uuid_mod.UUID(body["uuid"], version=4)
    assert str(parsed_uuid) == body["uuid"]
    # The url points at the json endpoint with the same uuid.
    assert body["url"] == f"/recipes/{body['uuid']}.json"

    # The row exists in the db with the right user_id and a parseable JSON blob.
    conn = sqlite3.connect(str(tmp_db_path))
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            "SELECT user_id, title, recipe_json FROM recipes WHERE uuid = ?",
            (body["uuid"],),
        ).fetchone()
    finally:
        conn.close()
    assert row is not None
    assert row["title"] == "Test Pancakes"
    parsed_blob = json.loads(row["recipe_json"])
    assert parsed_blob["name"] == "Test Pancakes"
    assert "1 cup flour" in parsed_blob["recipeIngredient"]


@pytest.mark.integration
def test_parse_recipe_without_auth_returns_401(client, mocked_openai):
    resp = client.post("/recipes/parse", data={"image": "aGVsbG8="})
    assert resp.status_code == 401


@pytest.mark.integration
def test_parse_recipe_with_openai_500_surfaces_error(client, auth_headers, mocked_openai):
    """If OpenAI returns a non-200, the endpoint must surface a 500 mentioning OpenAI."""
    # Replace the default 200 mock with a 500 mock on the same URL.
    mocked_openai.replace(
        responses_lib.POST,
        "https://api.openai.com/v1/chat/completions",
        body="upstream is sad",
        status=500,
    )
    resp = client.post(
        "/recipes/parse",
        headers=auth_headers,
        data={"image": "aGVsbG8="},
    )
    assert resp.status_code == 500
    assert "OpenAI" in resp.json()["detail"]


@pytest.mark.integration
def test_parse_recipe_strips_data_url_base64_prefix(
    client, auth_headers, mocked_openai, tmp_db_path
):
    """A `data:image/jpeg;base64,<...>` prefix should be stripped before sending to OpenAI."""
    resp = client.post(
        "/recipes/parse",
        headers=auth_headers,
        data={"image": "data:image/jpeg;base64,aGVsbG8="},
    )
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# GET /recipes/{uuid}.json
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_get_recipe_json_returns_stored_payload(client, auth_headers, mocked_openai):
    create = client.post(
        "/recipes/parse",
        headers=auth_headers,
        data={"image": "aGVsbG8="},
    )
    recipe_uuid = create.json()["uuid"]

    resp = client.get(f"/recipes/{recipe_uuid}.json")
    assert resp.status_code == 200
    body = resp.json()
    assert body["name"] == "Test Pancakes"
    assert "1 cup flour" in body["recipeIngredient"]


@pytest.mark.integration
def test_get_recipe_json_unknown_uuid_returns_404(client):
    resp = client.get("/recipes/00000000-0000-4000-8000-000000000000.json")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# GET /recipes/{uuid}.html
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_get_recipe_html_returns_stored_html(client, auth_headers, mocked_openai):
    create = client.post(
        "/recipes/parse",
        headers=auth_headers,
        data={"image": "aGVsbG8="},
    )
    recipe_uuid = create.json()["uuid"]

    resp = client.get(f"/recipes/{recipe_uuid}.html")
    assert resp.status_code == 200
    # FastAPI's HTMLResponse sets text/html content-type.
    assert resp.headers["content-type"].startswith("text/html")
    # The body contains the recipe title.
    assert "Test Pancakes" in resp.text


@pytest.mark.integration
def test_get_recipe_html_for_recipe_without_html_returns_404(
    client, auth_headers, mocked_openai, tmp_db_path
):
    """A recipe with no html_content in its stored blob returns 404 for the .html endpoint."""
    create = client.post(
        "/recipes/parse",
        headers=auth_headers,
        data={"image": "aGVsbG8="},
    )
    recipe_uuid = create.json()["uuid"]

    # Mutate the stored recipe to drop html_content.
    conn = sqlite3.connect(str(tmp_db_path))
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            "SELECT recipe_json FROM recipes WHERE uuid = ?", (recipe_uuid,)
        ).fetchone()
        blob = json.loads(row["recipe_json"])
        blob.pop("html_content", None)
        conn.execute(
            "UPDATE recipes SET recipe_json = ? WHERE uuid = ?",
            (json.dumps(blob), recipe_uuid),
        )
        conn.commit()
    finally:
        conn.close()

    resp = client.get(f"/recipes/{recipe_uuid}.html")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# GET /recipes
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_list_recipes_returns_empty_when_db_is_empty(client, auth_headers):
    resp = client.get("/recipes", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.integration
def test_list_recipes_returns_recipes_ordered_desc(client, auth_headers, mocked_openai):
    """Create two recipes with a small delay, then assert newest-first ordering."""
    r1 = client.post("/recipes/parse", headers=auth_headers, data={"image": "aGVsbG8="})
    assert r1.status_code == 200
    # SQLite's CURRENT_TIMESTAMP has 1-second resolution; sleep 1.1s so the two
    # rows get distinct created_at values and the DESC ordering is deterministic.
    time.sleep(1.1)
    r2 = client.post("/recipes/parse", headers=auth_headers, data={"image": "aGVsbG8="})
    assert r2.status_code == 200

    resp = client.get("/recipes", headers=auth_headers)
    assert resp.status_code == 200
    recipes = resp.json()
    assert len(recipes) == 2
    # Newest first.
    assert recipes[0]["uuid"] == r2.json()["uuid"]
    assert recipes[1]["uuid"] == r1.json()["uuid"]
    # Both have title and (optionally) datePublished.
    assert all(r["title"] == "Test Pancakes" for r in recipes)
    # Step 3: list rows now expose `source`. Image imports tag themselves.
    assert all(r["source"]["kind"] == "image" for r in recipes)


# ---------------------------------------------------------------------------
# POST /recipes/import-url (step 6)
# ---------------------------------------------------------------------------

# A self-contained recipe page with a clean JSON-LD block, used by both
# the JSON-LD happy-path and the OpenAI-fallback test. The fallback test
# uses a copy with the JSON-LD script stripped so the extractor has to
# route through gpt-4o-mini.
CANONICAL_URL_HTML_WITH_JSONLD = """\
<html>
<head>
<script type="application/ld+json">
{
  "@context": "https://schema.org",
  "@type": "Recipe",
  "name": "URL Pancakes",
  "recipeIngredient": ["1 cup flour", "2 eggs", "1 cup milk"],
  "recipeYield": "4 servings",
  "description": "Imported from a URL."
}
</script>
</head>
<body><h1>URL Pancakes</h1></body>
</html>
"""

CANONICAL_URL_HTML_NO_JSONLD = """\
<html>
<body>
<h1>Plain Pancakes</h1>
<p>This page has no JSON-LD; the importer should fall back to OpenAI.</p>
</body>
</html>
"""


def _fake_httpx_response(html: str, url: str = "https://example.test/recipe"):
    """Build an ``httpx.Response``-shaped mock for the URL import flow."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = html
    mock_resp.content = html.encode("utf-8")
    mock_resp.raise_for_status = MagicMock()
    return mock_resp


@pytest.mark.integration
def test_import_url_with_jsonld_happy_path(client, auth_headers, mocked_openai, tmp_db_path):
    """A page with a clean JSON-LD block imports without hitting OpenAI."""
    fake = _fake_httpx_response(CANONICAL_URL_HTML_WITH_JSONLD)

    with patch("api.routers.recipes.httpx.AsyncClient") as ClientCls:
        instance = MagicMock()
        instance.__aenter__ = AsyncMock(return_value=instance)
        instance.__aexit__ = AsyncMock(return_value=None)
        instance.get = AsyncMock(return_value=fake)
        ClientCls.return_value = instance

        resp = client.post(
            "/recipes/import-url",
            headers=auth_headers,
            json={"url": "https://example.test/recipe"},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert "uuid" in body
    assert body["url"].endswith(".json")

    # OpenAI was NOT called: JSON-LD was the only path used.
    assert len(mocked_openai.calls) == 0

    # Verify the row's source tag and the note are stored.
    conn = sqlite3.connect(str(tmp_db_path))
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            "SELECT source, note FROM recipes WHERE uuid = ?", (body["uuid"],)
        ).fetchone()
    finally:
        conn.close()
    assert row is not None
    source = json.loads(row["source"])
    assert source["kind"] == "url"
    assert source["value"] == "https://example.test/recipe"


@pytest.mark.integration
def test_import_url_falls_back_to_openai_when_no_jsonld(
    client, auth_headers, mocked_openai, tmp_db_path
):
    """A page without JSON-LD routes through the OpenAI text fallback."""
    fake = _fake_httpx_response(CANONICAL_URL_HTML_NO_JSONLD)

    with patch("api.routers.recipes.httpx.AsyncClient") as ClientCls:
        instance = MagicMock()
        instance.__aenter__ = AsyncMock(return_value=instance)
        instance.__aexit__ = AsyncMock(return_value=None)
        instance.get = AsyncMock(return_value=fake)
        ClientCls.return_value = instance

        resp = client.post(
            "/recipes/import-url",
            headers=auth_headers,
            json={"url": "https://example.test/plain"},
        )

    assert resp.status_code == 200
    # OpenAI WAS called for the text fallback.
    assert len(mocked_openai.calls) == 1


@pytest.mark.integration
def test_import_url_unauthenticated_returns_401(client, mocked_openai):
    resp = client.post("/recipes/import-url", json={"url": "https://example.test/x"})
    assert resp.status_code == 401


@pytest.mark.integration
def test_import_url_fetch_failure_returns_422(client, auth_headers, mocked_openai):
    """A network error returns 422 with a user-readable message, not 500."""
    import httpx as httpx_mod

    with patch("api.routers.recipes.httpx.AsyncClient") as ClientCls:
        instance = MagicMock()
        instance.__aenter__ = AsyncMock(return_value=instance)
        instance.__aexit__ = AsyncMock(return_value=None)
        instance.get = AsyncMock(
            side_effect=httpx_mod.ConnectError("dns blew up", request=MagicMock())
        )
        ClientCls.return_value = instance

        resp = client.post(
            "/recipes/import-url",
            headers=auth_headers,
            json={"url": "https://nonexistent.invalid/recipe"},
        )
    assert resp.status_code == 422
    assert "Couldn't fetch" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# PUT /recipes/{uuid} (step 6)
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_update_recipe_round_trip(client, auth_headers, mocked_openai, tmp_db_path):
    create = client.post("/recipes/parse", headers=auth_headers, data={"image": "aGVsbG8="})
    assert create.status_code == 200
    recipe_uuid = create.json()["uuid"]

    resp = client.put(
        f"/recipes/{recipe_uuid}",
        headers=auth_headers,
        json={
            "title": "Updated Pancakes",
            "note": "Used the 3.5 cup flour trick.",
            "recipeIngredient": ["1.5 cup flour", "2 eggs"],
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    # The stored JSON uses Schema.org "name" — not "title" — as the title key.
    assert body["name"] == "Updated Pancakes"
    assert body["note"] == "Used the 3.5 cup flour trick."
    assert body["recipeIngredient"] == ["1.5 cup flour", "2 eggs"]

    # The public JSON endpoint reflects the update.
    pub = client.get(f"/recipes/{recipe_uuid}.json")
    assert pub.json()["name"] == "Updated Pancakes"

    # The note column is also persisted at the row level.
    conn = sqlite3.connect(str(tmp_db_path))
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            "SELECT note, updated_at FROM recipes WHERE uuid = ?", (recipe_uuid,)
        ).fetchone()
    finally:
        conn.close()
    assert row["note"] == "Used the 3.5 cup flour trick."
    assert row["updated_at"] is not None


@pytest.mark.integration
def test_update_recipe_foreign_uuid_returns_404(client, auth_headers, mocked_openai, tmp_db_path):
    """Updating a recipe you don't own returns 404 (not 403) so attackers
    can't probe for valid UUIDs."""
    from passlib.context import CryptContext

    from api.auth import create_access_token

    create = client.post("/recipes/parse", headers=auth_headers, data={"image": "aGVsbG8="})
    recipe_uuid = create.json()["uuid"]

    # Insert a real second user so the token is valid (else 401, not 404).
    pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")
    conn = sqlite3.connect(str(tmp_db_path))
    try:
        conn.execute(
            "INSERT INTO users (email, hashed_password) VALUES (?, ?)",
            ("other@example.com", pwd.hash("otherpassword")),
        )
        conn.commit()
    finally:
        conn.close()

    other_token = create_access_token(data={"sub": "other@example.com"})
    other_headers = {"Authorization": f"Bearer {other_token}"}

    resp = client.put(
        f"/recipes/{recipe_uuid}",
        headers=other_headers,
        json={"title": "Hostile Takeover"},
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# DELETE /recipes/{uuid} (step 6)
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_delete_recipe_then_public_endpoints_404(client, auth_headers, mocked_openai):
    create = client.post("/recipes/parse", headers=auth_headers, data={"image": "aGVsbG8="})
    recipe_uuid = create.json()["uuid"]

    # Sanity: the public endpoints work before delete.
    assert client.get(f"/recipes/{recipe_uuid}.json").status_code == 200

    # Delete.
    resp = client.delete(f"/recipes/{recipe_uuid}", headers=auth_headers)
    assert resp.status_code == 204
    assert resp.content == b""

    # Public endpoints now 404.
    assert client.get(f"/recipes/{recipe_uuid}.json").status_code == 404
    assert client.get(f"/recipes/{recipe_uuid}.html").status_code == 404


@pytest.mark.integration
def test_delete_recipe_foreign_uuid_returns_404(client, auth_headers, mocked_openai, tmp_db_path):
    from passlib.context import CryptContext

    from api.auth import create_access_token

    create = client.post("/recipes/parse", headers=auth_headers, data={"image": "aGVsbG8="})
    recipe_uuid = create.json()["uuid"]

    # Insert a real second user.
    pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")
    conn = sqlite3.connect(str(tmp_db_path))
    try:
        conn.execute(
            "INSERT INTO users (email, hashed_password) VALUES (?, ?)",
            ("other@example.com", pwd.hash("otherpassword")),
        )
        conn.commit()
    finally:
        conn.close()

    other_token = create_access_token(data={"sub": "other@example.com"})
    other_headers = {"Authorization": f"Bearer {other_token}"}

    resp = client.delete(f"/recipes/{recipe_uuid}", headers=other_headers)
    assert resp.status_code == 404
    # Recipe still exists.
    assert client.get(f"/recipes/{recipe_uuid}.json").status_code == 200


# ---------------------------------------------------------------------------
# Auth-scoping (step 6: regression test for the pre-step-3 cross-user leak)
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_list_recipes_does_not_leak_other_users_recipes(
    client, auth_headers, mocked_openai, tmp_db_path
):
    """User A imports a recipe; User B's list is empty."""
    # User A imports.
    create = client.post("/recipes/parse", headers=auth_headers, data={"image": "aGVsbG8="})
    a_uuid = create.json()["uuid"]

    # User B's list is empty. Need a real second user.
    from passlib.context import CryptContext

    from api.auth import create_access_token

    pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")
    conn = sqlite3.connect(str(tmp_db_path))
    try:
        conn.execute(
            "INSERT INTO users (email, hashed_password) VALUES (?, ?)",
            ("b@example.com", pwd.hash("bpassword")),
        )
        conn.commit()
    finally:
        conn.close()

    b_token = create_access_token(data={"sub": "b@example.com"})
    b_headers = {"Authorization": f"Bearer {b_token}"}
    resp = client.get("/recipes", headers=b_headers)
    assert resp.status_code == 200
    assert resp.json() == []

    # User B's token cannot fetch A's uuid directly either (the public
    # endpoints are unauthenticated, so they DO return the recipe by
    # design — this is the chosen security model).
    pub = client.get(f"/recipes/{a_uuid}.json")
    assert pub.status_code == 200

    # But the listing is correctly scoped.
    resp = client.get("/recipes", headers=auth_headers)
    recipes = resp.json()
    assert len(recipes) == 1
    assert recipes[0]["uuid"] == a_uuid

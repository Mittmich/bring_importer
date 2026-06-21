"""Integration tests for the recipe endpoints (parse, fetch, list, edit, delete).

All tests are marked ``@pytest.mark.integration``. They go through the
``TestClient`` and use the ``mocked_openai`` fixture to avoid real OpenAI calls.
"""

import json
import sqlite3
import time
import uuid as uuid_mod
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api.models import Ingredient, InstructionStep, Recipe


def _recipe_named(title: str) -> Recipe:
    """A minimal Recipe with a given title, for search/pagination tests."""
    return Recipe(
        title=title,
        ingredients=[Ingredient(amount="1 cup", name="flour")],
        instructions=[InstructionStep(text="Mix.", ingredients=[0])],
        recipeYield="2 servings",
        description="",
    )


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
    assert body["url"] == f"/recipes/{body['uuid']}.json"

    # The row exists in the db with a parseable JSON blob in the new format.
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
    blob = json.loads(row["recipe_json"])
    assert blob["name"] == "Test Pancakes"
    # New format: structured ingredients list
    assert "ingredients" in blob
    ingredient_names = [ing["name"] for ing in blob["ingredients"]]
    assert "flour" in ingredient_names


@pytest.mark.integration
def test_parse_recipe_without_auth_returns_401(client, mocked_openai):
    resp = client.post("/recipes/parse", data={"image": "aGVsbG8="})
    assert resp.status_code == 401


@pytest.mark.integration
def test_parse_recipe_with_openai_error_surfaces_500(client, auth_headers):
    """If the extraction function raises, the endpoint must surface a 500."""
    from fastapi import HTTPException

    with patch(
        "api.routers.recipes.parse_recipe_with_openai",
        side_effect=HTTPException(status_code=500, detail="OpenAI API error: upstream sad"),
    ):
        resp = client.post(
            "/recipes/parse",
            headers=auth_headers,
            data={"image": "aGVsbG8="},
        )
    assert resp.status_code == 500
    assert "OpenAI" in resp.json()["detail"]


@pytest.mark.integration
def test_parse_recipe_strips_data_url_base64_prefix(client, auth_headers, mocked_openai):
    """A `data:image/jpeg;base64,<...>` prefix is accepted without errors."""
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

    # Owner can always fetch their own recipe (even private).
    resp = client.get(f"/recipes/{recipe_uuid}.json", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["name"] == "Test Pancakes"
    # New format — structured ingredients
    assert "ingredients" in body
    assert any(ing["name"] == "flour" for ing in body["ingredients"])
    assert body["is_public"] is False


@pytest.mark.integration
def test_get_recipe_json_private_recipe_returns_404_for_unauthenticated(
    client, auth_headers, mocked_openai
):
    create = client.post(
        "/recipes/parse",
        headers=auth_headers,
        data={"image": "aGVsbG8="},
    )
    recipe_uuid = create.json()["uuid"]
    # No auth — private recipe must not be exposed.
    resp = client.get(f"/recipes/{recipe_uuid}.json")
    assert resp.status_code == 404


@pytest.mark.integration
def test_get_recipe_json_public_recipe_accessible_without_auth(client, auth_headers, mocked_openai):
    create = client.post(
        "/recipes/parse",
        headers=auth_headers,
        data={"image": "aGVsbG8="},
    )
    recipe_uuid = create.json()["uuid"]
    # Make it public.
    client.put(
        f"/recipes/{recipe_uuid}",
        headers=auth_headers,
        json={"is_public": True},
    )
    resp = client.get(f"/recipes/{recipe_uuid}.json")
    assert resp.status_code == 200
    assert resp.json()["is_public"] is True


@pytest.mark.integration
def test_get_recipe_json_unknown_uuid_returns_404(client):
    resp = client.get("/recipes/00000000-0000-4000-8000-000000000000.json")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# GET /recipes/{uuid}.html
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_get_recipe_html_returns_html_page(client, auth_headers, mocked_openai):
    create = client.post(
        "/recipes/parse",
        headers=auth_headers,
        data={"image": "aGVsbG8="},
    )
    recipe_uuid = create.json()["uuid"]

    resp = client.get(f"/recipes/{recipe_uuid}.html")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/html")
    assert "Test Pancakes" in resp.text


@pytest.mark.integration
def test_get_recipe_html_embeds_jsonld_with_flat_ingredient_strings(
    client, auth_headers, mocked_openai
):
    """The .html endpoint converts structured ingredients to flat strings for Bring."""
    create = client.post(
        "/recipes/parse",
        headers=auth_headers,
        data={"image": "aGVsbG8="},
    )
    recipe_uuid = create.json()["uuid"]

    resp = client.get(f"/recipes/{recipe_uuid}.html")
    assert resp.status_code == 200
    assert "application/ld+json" in resp.text
    assert '"@type": "Recipe"' in resp.text
    # Flat string ingredient must appear in the JSON-LD
    assert "1 cup flour" in resp.text


@pytest.mark.integration
def test_get_recipe_html_unknown_uuid_returns_404(client):
    resp = client.get("/recipes/00000000-0000-4000-8000-000000000000.html")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# GET /recipes
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_list_recipes_returns_empty_when_db_is_empty(client, auth_headers):
    resp = client.get("/recipes", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["items"] == []
    assert body["total"] == 0


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
    body = resp.json()
    recipes = body["items"]
    assert body["total"] == 2
    assert len(recipes) == 2
    assert recipes[0]["uuid"] == r2.json()["uuid"]
    assert recipes[1]["uuid"] == r1.json()["uuid"]
    assert all(r["title"] == "Test Pancakes" for r in recipes)
    assert all(r["source"]["kind"] == "image" for r in recipes)


@pytest.mark.integration
def test_list_recipes_pagination(client, auth_headers, mocked_openai):
    """limit/offset page through the user's recipes and report the true total."""
    for _ in range(5):
        client.post("/recipes/parse", headers=auth_headers, data={"image": "aGVsbG8="})

    page1 = client.get("/recipes", headers=auth_headers, params={"limit": 2, "offset": 0}).json()
    assert page1["total"] == 5
    assert page1["limit"] == 2
    assert len(page1["items"]) == 2

    page3 = client.get("/recipes", headers=auth_headers, params={"limit": 2, "offset": 4}).json()
    assert page3["total"] == 5
    assert len(page3["items"]) == 1  # last page has the remainder

    # limit is clamped to a sane maximum.
    clamped = client.get("/recipes", headers=auth_headers, params={"limit": 9999}).json()
    assert clamped["limit"] == 100


@pytest.mark.integration
def test_list_recipes_search_filters_by_title(client, auth_headers):
    """The q parameter filters by case-insensitive title substring."""
    with patch(
        "api.routers.recipes.parse_recipe_with_openai",
        return_value=_recipe_named("Banana Bread"),
    ):
        client.post("/recipes/parse", headers=auth_headers, data={"image": "aGVsbG8="})
    with patch(
        "api.routers.recipes.parse_recipe_with_openai",
        return_value=_recipe_named("Tomato Soup"),
    ):
        client.post("/recipes/parse", headers=auth_headers, data={"image": "aGVsbG8="})

    resp = client.get("/recipes", headers=auth_headers, params={"q": "banana"}).json()
    assert resp["total"] == 1
    assert resp["items"][0]["title"] == "Banana Bread"


@pytest.mark.integration
def test_get_recipe_includes_owned_flag(client, auth_headers, mocked_openai):
    """owned is True for the owner; the field is present on the JSON payload."""
    uuid = client.post("/recipes/parse", headers=auth_headers, data={"image": "aGVsbG8="}).json()[
        "uuid"
    ]
    body = client.get(f"/recipes/{uuid}.json", headers=auth_headers).json()
    assert body["owned"] is True


# ---------------------------------------------------------------------------
# POST /recipes/import-url
# ---------------------------------------------------------------------------

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


def _fake_httpx_response(html: str):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = html
    mock_resp.content = html.encode("utf-8")
    mock_resp.raise_for_status = MagicMock()
    return mock_resp


@pytest.mark.integration
def test_import_url_with_jsonld_happy_path(client, auth_headers, mocked_openai, tmp_db_path):
    """A page with a clean JSON-LD block imports via the JSON-LD path."""
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

    # JSON-LD path was used (extract_recipe_from_jsonld was called)
    assert mocked_openai["jsonld"].call_count == 1
    # HTML text fallback was NOT triggered
    assert mocked_openai["html_text"].call_count == 0

    # Source is tagged correctly
    conn = sqlite3.connect(str(tmp_db_path))
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute("SELECT source FROM recipes WHERE uuid = ?", (body["uuid"],)).fetchone()
    finally:
        conn.close()
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
    # HTML text fallback was called
    assert mocked_openai["html_text"].call_count == 1
    # JSON-LD extractor was not called (no JSON-LD block found)
    assert mocked_openai["jsonld"].call_count == 0


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
# PUT /recipes/{uuid}
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_update_recipe_round_trip(client, auth_headers, mocked_openai, tmp_db_path):
    create = client.post("/recipes/parse", headers=auth_headers, data={"image": "aGVsbG8="})
    assert create.status_code == 200
    recipe_uuid = create.json()["uuid"]

    new_ingredients = [
        {"amount": "1.5 cups", "name": "flour"},
        {"amount": "2", "name": "eggs"},
    ]
    new_instructions = [
        {"text": "Mix flour and eggs.", "ingredients": [0, 1]},
    ]

    resp = client.put(
        f"/recipes/{recipe_uuid}",
        headers=auth_headers,
        json={
            "title": "Updated Pancakes",
            "note": "Used the 1.5 cup flour trick.",
            "ingredients": new_ingredients,
            "instructions": new_instructions,
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["name"] == "Updated Pancakes"
    assert body["note"] == "Used the 1.5 cup flour trick."
    assert body["ingredients"] == new_ingredients
    assert body["instructions"] == new_instructions

    # The JSON endpoint reflects the update (owner auth required for private recipes).
    pub = client.get(f"/recipes/{recipe_uuid}.json", headers=auth_headers)
    assert pub.json()["name"] == "Updated Pancakes"

    # The Bring HTML uses the updated ingredients as flat strings.
    html = client.get(f"/recipes/{recipe_uuid}.html")
    assert "1.5 cups flour" in html.text

    # Note column is persisted at the row level.
    conn = sqlite3.connect(str(tmp_db_path))
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            "SELECT note, updated_at FROM recipes WHERE uuid = ?", (recipe_uuid,)
        ).fetchone()
    finally:
        conn.close()
    assert row["note"] == "Used the 1.5 cup flour trick."
    assert row["updated_at"] is not None


@pytest.mark.integration
def test_update_recipe_foreign_uuid_returns_404(client, auth_headers, mocked_openai, tmp_db_path):
    """Updating a recipe you don't own returns 404 (not 403)."""
    from passlib.context import CryptContext

    from api.auth import create_access_token

    create = client.post("/recipes/parse", headers=auth_headers, data={"image": "aGVsbG8="})
    recipe_uuid = create.json()["uuid"]

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
# DELETE /recipes/{uuid}
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_delete_recipe_then_public_endpoints_404(client, auth_headers, mocked_openai):
    create = client.post("/recipes/parse", headers=auth_headers, data={"image": "aGVsbG8="})
    recipe_uuid = create.json()["uuid"]

    assert client.get(f"/recipes/{recipe_uuid}.json", headers=auth_headers).status_code == 200

    resp = client.delete(f"/recipes/{recipe_uuid}", headers=auth_headers)
    assert resp.status_code == 204
    assert resp.content == b""

    assert client.get(f"/recipes/{recipe_uuid}.json").status_code == 404
    assert client.get(f"/recipes/{recipe_uuid}.html").status_code == 404


@pytest.mark.integration
def test_delete_recipe_foreign_uuid_returns_404(client, auth_headers, mocked_openai, tmp_db_path):
    from passlib.context import CryptContext

    from api.auth import create_access_token

    create = client.post("/recipes/parse", headers=auth_headers, data={"image": "aGVsbG8="})
    recipe_uuid = create.json()["uuid"]

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
    # Recipe still exists and owner can still access it.
    assert client.get(f"/recipes/{recipe_uuid}.json", headers=auth_headers).status_code == 200


# ---------------------------------------------------------------------------
# Auth scoping
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_list_recipes_does_not_leak_other_users_recipes(
    client, auth_headers, mocked_openai, tmp_db_path
):
    """User A imports a recipe; User B's list is empty."""
    from passlib.context import CryptContext

    from api.auth import create_access_token

    create = client.post("/recipes/parse", headers=auth_headers, data={"image": "aGVsbG8="})
    a_uuid = create.json()["uuid"]

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
    assert resp.json()["items"] == []

    # Owner can always access their own recipe.
    assert client.get(f"/recipes/{a_uuid}.json", headers=auth_headers).status_code == 200

    # But the listing is correctly scoped.
    resp = client.get("/recipes", headers=auth_headers)
    recipes = resp.json()["items"]
    assert len(recipes) == 1
    assert recipes[0]["uuid"] == a_uuid


# ---------------------------------------------------------------------------
# POST /recipes/{uuid}/clone
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_clone_public_recipe_creates_new_recipe(client, auth_headers, mocked_openai, tmp_db_path):
    """A logged-in user can clone a public recipe; the clone appears in their list."""
    from passlib.context import CryptContext

    from api.auth import create_access_token

    # User A creates and publishes a recipe.
    create = client.post("/recipes/parse", headers=auth_headers, data={"image": "aGVsbG8="})
    original_uuid = create.json()["uuid"]
    client.put(f"/recipes/{original_uuid}", headers=auth_headers, json={"is_public": True})

    # User B clones it.
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

    resp = client.post(f"/recipes/{original_uuid}/clone", headers=b_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert "uuid" in body
    # Clone gets a different uuid.
    assert body["uuid"] != original_uuid

    # Clone appears in B's recipe list.
    list_resp = client.get("/recipes", headers=b_headers)
    assert list_resp.status_code == 200
    uuids = [r["uuid"] for r in list_resp.json()["items"]]
    assert body["uuid"] in uuids

    # Original still belongs to A only.
    a_list = client.get("/recipes", headers=auth_headers).json()["items"]
    assert any(r["uuid"] == original_uuid for r in a_list)
    assert not any(r["uuid"] == body["uuid"] for r in a_list)


@pytest.mark.integration
def test_clone_private_recipe_returns_404(client, auth_headers, mocked_openai, tmp_db_path):
    """Cloning a private recipe returns 404 even if the caller is authenticated."""
    from passlib.context import CryptContext

    from api.auth import create_access_token

    create = client.post("/recipes/parse", headers=auth_headers, data={"image": "aGVsbG8="})
    recipe_uuid = create.json()["uuid"]
    # Recipe is private by default; do NOT make it public.

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

    resp = client.post(f"/recipes/{recipe_uuid}/clone", headers=b_headers)
    assert resp.status_code == 404


@pytest.mark.integration
def test_clone_nonexistent_recipe_returns_404(client, auth_headers):
    """Cloning a UUID that doesn't exist returns 404."""
    resp = client.post(
        "/recipes/00000000-0000-4000-8000-000000000000/clone",
        headers=auth_headers,
    )
    assert resp.status_code == 404

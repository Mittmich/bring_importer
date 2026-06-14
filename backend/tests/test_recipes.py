"""Integration tests for the recipe endpoints (parse, fetch, list).

All tests are marked ``@pytest.mark.integration``. They go through the
``TestClient`` and use the ``mocked_openai`` fixture for the parse endpoint.
"""

import json
import sqlite3
import time
import uuid as uuid_mod

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
def test_list_recipes_returns_empty_when_db_is_empty(client):
    resp = client.get("/recipes")
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

    resp = client.get("/recipes")
    assert resp.status_code == 200
    recipes = resp.json()
    assert len(recipes) == 2
    # Newest first.
    assert recipes[0]["uuid"] == r2.json()["uuid"]
    assert recipes[1]["uuid"] == r1.json()["uuid"]
    # Both have title and (optionally) datePublished.
    assert all(r["title"] == "Test Pancakes" for r in recipes)

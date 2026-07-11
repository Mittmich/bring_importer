"""Integration tests for personal cookbooks (Phase 2 of sharing)."""

import sqlite3
from unittest.mock import patch

import pytest
from passlib.context import CryptContext

from api import create_access_token
from api.models import Ingredient, InstructionStep, Recipe

_pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")


def _store_recipe(client, auth_headers, title, ingredients):
    """Store a recipe with a specific title + ingredients (for search tests)."""
    recipe = Recipe(
        title=title,
        ingredients=[Ingredient(amount=a, name=n) for a, n in ingredients],
        instructions=[InstructionStep(text="Cook.", ingredients=[])],
        recipeYield="2 servings",
        description="",
    )
    with patch("api.routers.recipes.parse_recipe_with_openai", return_value=recipe):
        resp = client.post("/recipes/parse", headers=auth_headers, data={"image": "aGVsbG8="})
    assert resp.status_code == 200
    return resp.json()["uuid"]


def _make_user(tmp_db_path, email: str):
    conn = sqlite3.connect(str(tmp_db_path))
    try:
        conn.execute(
            "INSERT INTO users (email, hashed_password) VALUES (?, ?)", (email, _pwd.hash("pw"))
        )
        conn.commit()
    finally:
        conn.close()
    return {"Authorization": f"Bearer {create_access_token(data={'sub': email})}"}


def _make_recipe(client, auth_headers) -> str:
    resp = client.post("/recipes/parse", headers=auth_headers, data={"image": "aGVsbG8="})
    assert resp.status_code == 200
    return resp.json()["uuid"]


def _create_cookbook(client, auth_headers, name="Weeknight") -> int:
    resp = client.post("/cookbooks", headers=auth_headers, json={"name": name})
    assert resp.status_code == 200
    return resp.json()["id"]


@pytest.mark.integration
def test_create_and_list_cookbook(client, auth_headers):
    cid = _create_cookbook(client, auth_headers, "Desserts")
    books = client.get("/cookbooks", headers=auth_headers).json()
    assert [(b["id"], b["name"], b["recipe_count"]) for b in books] == [(cid, "Desserts", 0)]


@pytest.mark.integration
def test_create_empty_name_is_422(client, auth_headers):
    assert client.post("/cookbooks", headers=auth_headers, json={"name": "  "}).status_code == 422


@pytest.mark.integration
def test_add_and_remove_recipe(client, auth_headers, mocked_openai):
    cid = _create_cookbook(client, auth_headers)
    r = _make_recipe(client, auth_headers)

    assert (
        client.post(
            f"/cookbooks/{cid}/recipes", headers=auth_headers, json={"recipe_uuid": r}
        ).status_code
        == 200
    )
    detail = client.get(f"/cookbooks/{cid}", headers=auth_headers).json()
    assert detail["recipe_count"] == 1
    assert [i["uuid"] for i in detail["recipes"]] == [r]

    # Adding again is idempotent.
    client.post(f"/cookbooks/{cid}/recipes", headers=auth_headers, json={"recipe_uuid": r})
    assert client.get(f"/cookbooks/{cid}", headers=auth_headers).json()["recipe_count"] == 1

    assert client.delete(f"/cookbooks/{cid}/recipes/{r}", headers=auth_headers).status_code == 204
    assert client.get(f"/cookbooks/{cid}", headers=auth_headers).json()["recipe_count"] == 0


@pytest.mark.integration
def test_add_unknown_recipe_is_404(client, auth_headers):
    cid = _create_cookbook(client, auth_headers)
    resp = client.post(
        f"/cookbooks/{cid}/recipes", headers=auth_headers, json={"recipe_uuid": "no-such-uuid"}
    )
    assert resp.status_code == 404


@pytest.mark.integration
def test_add_to_unknown_cookbook_is_404(client, auth_headers, mocked_openai):
    r = _make_recipe(client, auth_headers)
    resp = client.post("/cookbooks/9999/recipes", headers=auth_headers, json={"recipe_uuid": r})
    assert resp.status_code == 404


@pytest.mark.integration
def test_rename_cookbook(client, auth_headers):
    cid = _create_cookbook(client, auth_headers, "Old")
    assert (
        client.patch(f"/cookbooks/{cid}", headers=auth_headers, json={"name": "New"}).status_code
        == 200
    )
    assert client.get(f"/cookbooks/{cid}", headers=auth_headers).json()["name"] == "New"


@pytest.mark.integration
def test_delete_cookbook(client, auth_headers, mocked_openai):
    cid = _create_cookbook(client, auth_headers)
    r = _make_recipe(client, auth_headers)
    client.post(f"/cookbooks/{cid}/recipes", headers=auth_headers, json={"recipe_uuid": r})

    assert client.delete(f"/cookbooks/{cid}", headers=auth_headers).status_code == 204
    assert client.get(f"/cookbooks/{cid}", headers=auth_headers).status_code == 404
    # The recipe itself still exists.
    assert client.get(f"/recipes/{r}.json", headers=auth_headers).status_code == 200


@pytest.mark.integration
def test_list_with_recipe_uuid_reports_contains(client, auth_headers, mocked_openai):
    in_cid = _create_cookbook(client, auth_headers, "Has it")
    out_cid = _create_cookbook(client, auth_headers, "Empty")
    r = _make_recipe(client, auth_headers)
    client.post(f"/cookbooks/{in_cid}/recipes", headers=auth_headers, json={"recipe_uuid": r})

    books = {
        b["id"]: b for b in client.get(f"/cookbooks?recipe_uuid={r}", headers=auth_headers).json()
    }
    assert books[in_cid]["contains"] is True
    assert books[out_cid]["contains"] is False


@pytest.mark.integration
def test_cookbooks_are_owner_isolated(client, auth_headers, tmp_db_path):
    cid = _create_cookbook(client, auth_headers, "Private")
    other = _make_user(tmp_db_path, "other@example.com")

    assert client.get(f"/cookbooks/{cid}", headers=other).status_code == 404
    assert client.patch(f"/cookbooks/{cid}", headers=other, json={"name": "Hax"}).status_code == 404
    assert client.delete(f"/cookbooks/{cid}", headers=other).status_code == 404
    assert client.get("/cookbooks", headers=other).json() == []


@pytest.mark.integration
def test_cookbooks_require_auth(client):
    assert client.get("/cookbooks").status_code == 401
    assert client.post("/cookbooks", json={"name": "x"}).status_code == 401


# --- bulk add ---


def _detail_uuids(client, auth_headers, cid):
    return {
        i["uuid"] for i in client.get(f"/cookbooks/{cid}", headers=auth_headers).json()["recipes"]
    }


@pytest.mark.integration
def test_bulk_add_by_query_adds_all_matches(client, auth_headers):
    cid = _create_cookbook(client, auth_headers)
    pancakes = _store_recipe(client, auth_headers, "Pancakes", [("50 g", "butter")])
    toast = _store_recipe(client, auth_headers, "Buttered toast", [("2 slices", "bread")])
    _store_recipe(client, auth_headers, "Green salad", [("1", "lettuce")])

    resp = client.post(f"/cookbooks/{cid}/recipes/bulk", headers=auth_headers, json={"q": "butter"})
    assert resp.status_code == 200
    assert resp.json() == {"matched": 2, "added": 2}
    assert _detail_uuids(client, auth_headers, cid) == {pancakes, toast}


@pytest.mark.integration
def test_bulk_add_by_tags(client, auth_headers, mocked_openai):
    cid = _create_cookbook(client, auth_headers)
    r1 = _make_recipe(client, auth_headers)
    r2 = _make_recipe(client, auth_headers)
    r3 = _make_recipe(client, auth_headers)
    for r in (r1, r2):
        client.put(f"/recipes/{r}", headers=auth_headers, json={"tags": ["Quick"]})
    client.put(f"/recipes/{r3}", headers=auth_headers, json={"tags": ["Slow"]})

    resp = client.post(
        f"/cookbooks/{cid}/recipes/bulk", headers=auth_headers, json={"tags": ["Quick"]}
    )
    assert resp.json() == {"matched": 2, "added": 2}
    assert _detail_uuids(client, auth_headers, cid) == {r1, r2}


@pytest.mark.integration
def test_bulk_add_by_uuids_skips_existing_and_unowned(
    client, auth_headers, tmp_db_path, mocked_openai
):
    cid = _create_cookbook(client, auth_headers)
    r1 = _make_recipe(client, auth_headers)
    r2 = _make_recipe(client, auth_headers)
    client.post(f"/cookbooks/{cid}/recipes", headers=auth_headers, json={"recipe_uuid": r1})

    resp = client.post(
        f"/cookbooks/{cid}/recipes/bulk",
        headers=auth_headers,
        json={"recipe_uuids": [r1, r2, "not-a-real-uuid"]},
    )
    # r1 already present (skipped), r2 added, bogus uuid ignored (not owned).
    assert resp.json() == {"matched": 2, "added": 1}
    assert _detail_uuids(client, auth_headers, cid) == {r1, r2}


@pytest.mark.integration
def test_bulk_add_to_unknown_cookbook_404(client, auth_headers):
    resp = client.post("/cookbooks/9999/recipes/bulk", headers=auth_headers, json={"q": "x"})
    assert resp.status_code == 404

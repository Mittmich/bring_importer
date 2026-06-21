"""Integration tests for the meal-plan + shopping-list endpoints."""

from unittest.mock import patch

from api.models import Ingredient


def _make_recipe(client, auth_headers, mocked_openai) -> str:
    """Create a recipe via the mocked parse endpoint; return its uuid."""
    resp = client.post("/recipes/parse", headers=auth_headers, data={"image": "aGVsbG8="})
    assert resp.status_code == 200
    return resp.json()["uuid"]


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


def test_add_and_list_meal_plan_entry(client, auth_headers, mocked_openai):
    uuid = _make_recipe(client, auth_headers, mocked_openai)
    resp = client.post(
        "/meal-plan",
        headers=auth_headers,
        json={"date": "2026-06-22", "recipe_uuid": uuid},
    )
    assert resp.status_code == 200
    entry = resp.json()
    assert entry["recipe_uuid"] == uuid
    assert entry["recipe_title"] == "Test Pancakes"
    assert entry["position"] == 0

    listed = client.get(
        "/meal-plan", headers=auth_headers, params={"start": "2026-06-22", "end": "2026-06-28"}
    )
    assert listed.status_code == 200
    assert [e["id"] for e in listed.json()] == [entry["id"]]


def test_list_respects_date_range(client, auth_headers, mocked_openai):
    uuid = _make_recipe(client, auth_headers, mocked_openai)
    client.post(
        "/meal-plan", headers=auth_headers, json={"date": "2026-06-22", "recipe_uuid": uuid}
    )
    client.post(
        "/meal-plan", headers=auth_headers, json={"date": "2026-07-01", "recipe_uuid": uuid}
    )

    listed = client.get(
        "/meal-plan", headers=auth_headers, params={"start": "2026-06-22", "end": "2026-06-28"}
    )
    assert [e["date"] for e in listed.json()] == ["2026-06-22"]


def test_positions_increment_per_day(client, auth_headers, mocked_openai):
    uuid = _make_recipe(client, auth_headers, mocked_openai)
    first = client.post(
        "/meal-plan", headers=auth_headers, json={"date": "2026-06-22", "recipe_uuid": uuid}
    ).json()
    second = client.post(
        "/meal-plan", headers=auth_headers, json={"date": "2026-06-22", "recipe_uuid": uuid}
    ).json()
    assert first["position"] == 0
    assert second["position"] == 1


def test_add_entry_for_unowned_recipe_returns_404(client, auth_headers):
    resp = client.post(
        "/meal-plan",
        headers=auth_headers,
        json={"date": "2026-06-22", "recipe_uuid": "does-not-exist"},
    )
    assert resp.status_code == 404


def test_add_entry_without_auth_returns_401(client):
    resp = client.post("/meal-plan", json={"date": "2026-06-22", "recipe_uuid": "x"})
    assert resp.status_code == 401


def test_delete_entry(client, auth_headers, mocked_openai):
    uuid = _make_recipe(client, auth_headers, mocked_openai)
    entry = client.post(
        "/meal-plan", headers=auth_headers, json={"date": "2026-06-22", "recipe_uuid": uuid}
    ).json()
    resp = client.delete(f"/meal-plan/{entry['id']}", headers=auth_headers)
    assert resp.status_code == 204

    listed = client.get(
        "/meal-plan", headers=auth_headers, params={"start": "2026-06-22", "end": "2026-06-28"}
    )
    assert listed.json() == []


def test_delete_unknown_entry_returns_404(client, auth_headers):
    resp = client.delete("/meal-plan/9999", headers=auth_headers)
    assert resp.status_code == 404


def test_patch_moves_entry_to_new_date(client, auth_headers, mocked_openai):
    uuid = _make_recipe(client, auth_headers, mocked_openai)
    entry = client.post(
        "/meal-plan", headers=auth_headers, json={"date": "2026-06-22", "recipe_uuid": uuid}
    ).json()
    resp = client.patch(
        f"/meal-plan/{entry['id']}",
        headers=auth_headers,
        json={"date": "2026-06-24", "position": 3},
    )
    assert resp.status_code == 204

    listed = client.get(
        "/meal-plan", headers=auth_headers, params={"start": "2026-06-22", "end": "2026-06-28"}
    ).json()
    assert listed[0]["date"] == "2026-06-24"
    assert listed[0]["position"] == 3


def test_patch_unknown_entry_returns_404(client, auth_headers):
    resp = client.patch("/meal-plan/9999", headers=auth_headers, json={"position": 1})
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Shopping list
# ---------------------------------------------------------------------------


def test_shopping_list_merges_and_persists(client, auth_headers, mocked_openai):
    uuid = _make_recipe(client, auth_headers, mocked_openai)
    client.post(
        "/meal-plan", headers=auth_headers, json={"date": "2026-06-22", "recipe_uuid": uuid}
    )

    merged = [Ingredient(amount="2 cups", name="flour"), Ingredient(amount="4", name="eggs")]
    with patch("api.routers.meal_plan.merge_ingredients", return_value=merged) as mock_merge:
        resp = client.post(
            "/meal-plan/shopping-list",
            headers=auth_headers,
            json={"start": "2026-06-22", "end": "2026-06-28"},
        )
    assert resp.status_code == 200
    # The merge received the recipe's flattened ingredients.
    assert mock_merge.call_count == 1
    body = resp.json()
    assert body["items"] == [
        {"amount": "2 cups", "name": "flour"},
        {"amount": "4", "name": "eggs"},
    ]
    assert body["token"]

    # The merged list is served publicly for Bring (no auth) as JSON-LD.
    html = client.get(f"/meal-plan/shopping-list/{body['token']}.html")
    assert html.status_code == 200
    assert "application/ld+json" in html.text
    assert "2 cups flour" in html.text
    assert "4 eggs" in html.text


def test_shopping_list_unknown_token_returns_404(client):
    resp = client.get("/meal-plan/shopping-list/nonexistent.html")
    assert resp.status_code == 404


def test_cross_user_isolation(client, auth_headers, mocked_openai, tmp_db_path):
    """A second user can't see or delete the first user's entries."""
    import sqlite3

    from passlib.context import CryptContext

    from api import create_access_token

    uuid = _make_recipe(client, auth_headers, mocked_openai)
    entry = client.post(
        "/meal-plan", headers=auth_headers, json={"date": "2026-06-22", "recipe_uuid": uuid}
    ).json()

    # Create a second user and their token.
    pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")
    conn = sqlite3.connect(str(tmp_db_path))
    conn.execute(
        "INSERT INTO users (email, hashed_password) VALUES (?, ?)",
        ("other@example.com", pwd.hash("pw")),
    )
    conn.commit()
    conn.close()
    other_headers = {
        "Authorization": f"Bearer {create_access_token(data={'sub': 'other@example.com'})}"
    }

    listed = client.get(
        "/meal-plan", headers=other_headers, params={"start": "2026-06-22", "end": "2026-06-28"}
    )
    assert listed.json() == []

    resp = client.delete(f"/meal-plan/{entry['id']}", headers=other_headers)
    assert resp.status_code == 404

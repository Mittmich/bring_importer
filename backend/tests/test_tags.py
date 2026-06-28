"""Integration tests for recipe tags: assign, list, filter, manage, colour."""

import sqlite3

from passlib.context import CryptContext

from api import create_access_token


def _make_recipe(client, auth_headers) -> str:
    return client.post("/recipes/parse", headers=auth_headers, data={"image": "aGVsbG8="}).json()[
        "uuid"
    ]


def _set_tags(client, auth_headers, uuid, tags):
    return client.put(f"/recipes/{uuid}", headers=auth_headers, json={"tags": tags})


def _names(tags) -> list:
    """Tag names from the embedded ``{name, color}`` list on a recipe."""
    return [t["name"] for t in tags]


def _name_counts(tags) -> list:
    """``(name, count)`` pairs from the ``GET /recipes/tags`` listing."""
    return [(t["name"], t["count"]) for t in tags]


def _second_user(tmp_db_path):
    pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")
    conn = sqlite3.connect(str(tmp_db_path))
    try:
        conn.execute(
            "INSERT INTO users (email, hashed_password) VALUES (?, ?)",
            ("b@example.com", pwd.hash("pw")),
        )
        conn.commit()
    finally:
        conn.close()
    return {"Authorization": f"Bearer {create_access_token(data={'sub': 'b@example.com'})}"}


def test_assign_tags_roundtrip(client, auth_headers, mocked_openai):
    uuid = _make_recipe(client, auth_headers)
    resp = _set_tags(client, auth_headers, uuid, ["Dinner", "Quick"])
    assert resp.status_code == 200
    assert _names(resp.json()["tags"]) == ["Dinner", "Quick"]

    fetched = client.get(f"/recipes/{uuid}.json", headers=auth_headers).json()
    assert _names(fetched["tags"]) == ["Dinner", "Quick"]
    # New tags carry no explicit colour; the frontend derives a default.
    assert all(t["color"] is None for t in fetched["tags"])

    listed = client.get("/recipes", headers=auth_headers).json()["items"]
    assert _names(listed[0]["tags"]) == ["Dinner", "Quick"]


def test_tags_case_insensitive_dedupe(client, auth_headers, mocked_openai):
    uuid = _make_recipe(client, auth_headers)
    resp = _set_tags(client, auth_headers, uuid, ["Dinner", "dinner ", " DINNER"])
    assert _names(resp.json()["tags"]) == ["Dinner"]  # first-seen display form, deduped


def test_reassign_replaces_tags(client, auth_headers, mocked_openai):
    uuid = _make_recipe(client, auth_headers)
    _set_tags(client, auth_headers, uuid, ["A", "B"])
    resp = _set_tags(client, auth_headers, uuid, ["C"])
    assert _names(resp.json()["tags"]) == ["C"]


def test_list_tags_with_counts(client, auth_headers, mocked_openai):
    r1 = _make_recipe(client, auth_headers)
    r2 = _make_recipe(client, auth_headers)
    _set_tags(client, auth_headers, r1, ["Shared", "Only1"])
    _set_tags(client, auth_headers, r2, ["Shared"])

    tags = client.get("/recipes/tags", headers=auth_headers).json()
    assert _name_counts(tags) == [("Only1", 1), ("Shared", 2)]
    # Each tag carries a stable id and (initially absent) colour.
    assert all(isinstance(t["id"], int) for t in tags)
    assert all(t["color"] is None for t in tags)


def test_filter_by_single_tag(client, auth_headers, mocked_openai):
    r1 = _make_recipe(client, auth_headers)
    r2 = _make_recipe(client, auth_headers)
    _set_tags(client, auth_headers, r1, ["Vegan"])
    _set_tags(client, auth_headers, r2, ["Meat"])

    resp = client.get("/recipes", headers=auth_headers, params={"tag": "vegan"}).json()
    assert resp["total"] == 1
    assert resp["items"][0]["uuid"] == r1


def test_filter_by_multiple_tags_is_and(client, auth_headers, mocked_openai):
    r1 = _make_recipe(client, auth_headers)
    r2 = _make_recipe(client, auth_headers)
    _set_tags(client, auth_headers, r1, ["Quick", "Vegan"])
    _set_tags(client, auth_headers, r2, ["Quick"])

    # Both tags required → only r1 qualifies.
    resp = client.get("/recipes", headers=auth_headers, params={"tag": ["Quick", "Vegan"]}).json()
    assert [i["uuid"] for i in resp["items"]] == [r1]


def test_delete_recipe_orphans_tag_with_zero_count(client, auth_headers, mocked_openai):
    uuid = _make_recipe(client, auth_headers)
    _set_tags(client, auth_headers, uuid, ["Lonely"])
    assert _name_counts(client.get("/recipes/tags", headers=auth_headers).json()) == [("Lonely", 1)]

    client.delete(f"/recipes/{uuid}", headers=auth_headers)
    # The tag is no longer used, but lingers (count 0) so it stays manageable.
    assert _name_counts(client.get("/recipes/tags", headers=auth_headers).json()) == [("Lonely", 0)]


def test_tags_are_user_isolated(client, auth_headers, mocked_openai, tmp_db_path):
    uuid = _make_recipe(client, auth_headers)
    _set_tags(client, auth_headers, uuid, ["Private"])
    b_headers = _second_user(tmp_db_path)

    assert client.get("/recipes/tags", headers=b_headers).json() == []
    # Filtering by A's tag returns nothing for B.
    resp = client.get("/recipes", headers=b_headers, params={"tag": "Private"}).json()
    assert resp["items"] == []


def _tag_id(client, auth_headers, name) -> int:
    tags = client.get("/recipes/tags", headers=auth_headers).json()
    return next(t["id"] for t in tags if t["name"] == name)


def test_set_tag_colour(client, auth_headers, mocked_openai):
    uuid = _make_recipe(client, auth_headers)
    _set_tags(client, auth_headers, uuid, ["Dinner"])
    tag_id = _tag_id(client, auth_headers, "Dinner")

    resp = client.patch(f"/recipes/tags/{tag_id}", headers=auth_headers, json={"color": "#6366f1"})
    assert resp.status_code == 200
    assert resp.json()["color"] == "#6366f1"

    # Colour surfaces on the recipe's embedded tags too.
    fetched = client.get(f"/recipes/{uuid}.json", headers=auth_headers).json()
    assert fetched["tags"][0]["color"] == "#6366f1"


def test_rename_tag(client, auth_headers, mocked_openai):
    uuid = _make_recipe(client, auth_headers)
    _set_tags(client, auth_headers, uuid, ["Dinner"])
    tag_id = _tag_id(client, auth_headers, "Dinner")

    resp = client.patch(f"/recipes/tags/{tag_id}", headers=auth_headers, json={"name": "Supper"})
    assert resp.status_code == 200
    assert resp.json()["name"] == "Supper"
    assert _names(client.get(f"/recipes/{uuid}.json", headers=auth_headers).json()["tags"]) == [
        "Supper"
    ]


def test_rename_tag_collision_conflicts(client, auth_headers, mocked_openai):
    uuid = _make_recipe(client, auth_headers)
    _set_tags(client, auth_headers, uuid, ["Dinner", "Lunch"])
    tag_id = _tag_id(client, auth_headers, "Lunch")

    # Case-insensitive clash with the existing "Dinner".
    resp = client.patch(f"/recipes/tags/{tag_id}", headers=auth_headers, json={"name": "dinner"})
    assert resp.status_code == 409


def test_delete_tag(client, auth_headers, mocked_openai):
    uuid = _make_recipe(client, auth_headers)
    _set_tags(client, auth_headers, uuid, ["Dinner", "Quick"])
    tag_id = _tag_id(client, auth_headers, "Quick")

    resp = client.delete(f"/recipes/tags/{tag_id}", headers=auth_headers)
    assert resp.status_code == 204
    # Removed from the listing and detached from the recipe.
    assert _names(client.get("/recipes/tags", headers=auth_headers).json()) == ["Dinner"]
    assert _names(client.get(f"/recipes/{uuid}.json", headers=auth_headers).json()["tags"]) == [
        "Dinner"
    ]


def test_manage_tag_user_isolation(client, auth_headers, mocked_openai, tmp_db_path):
    uuid = _make_recipe(client, auth_headers)
    _set_tags(client, auth_headers, uuid, ["Private"])
    tag_id = _tag_id(client, auth_headers, "Private")
    b_headers = _second_user(tmp_db_path)

    # B cannot recolour or delete A's tag.
    assert (
        client.patch(
            f"/recipes/tags/{tag_id}", headers=b_headers, json={"color": "#000"}
        ).status_code
        == 404
    )
    assert client.delete(f"/recipes/tags/{tag_id}", headers=b_headers).status_code == 404

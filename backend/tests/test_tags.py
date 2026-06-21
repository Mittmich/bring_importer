"""Integration tests for recipe tags: assign, list, and filter."""

import sqlite3

from passlib.context import CryptContext

from api import create_access_token


def _make_recipe(client, auth_headers) -> str:
    return client.post("/recipes/parse", headers=auth_headers, data={"image": "aGVsbG8="}).json()[
        "uuid"
    ]


def _set_tags(client, auth_headers, uuid, tags):
    return client.put(f"/recipes/{uuid}", headers=auth_headers, json={"tags": tags})


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
    assert resp.json()["tags"] == ["Dinner", "Quick"]

    fetched = client.get(f"/recipes/{uuid}.json", headers=auth_headers).json()
    assert fetched["tags"] == ["Dinner", "Quick"]

    listed = client.get("/recipes", headers=auth_headers).json()["items"]
    assert listed[0]["tags"] == ["Dinner", "Quick"]


def test_tags_case_insensitive_dedupe(client, auth_headers, mocked_openai):
    uuid = _make_recipe(client, auth_headers)
    resp = _set_tags(client, auth_headers, uuid, ["Dinner", "dinner ", " DINNER"])
    assert resp.json()["tags"] == ["Dinner"]  # first-seen display form, deduped


def test_reassign_replaces_tags(client, auth_headers, mocked_openai):
    uuid = _make_recipe(client, auth_headers)
    _set_tags(client, auth_headers, uuid, ["A", "B"])
    resp = _set_tags(client, auth_headers, uuid, ["C"])
    assert resp.json()["tags"] == ["C"]


def test_list_tags_with_counts(client, auth_headers, mocked_openai):
    r1 = _make_recipe(client, auth_headers)
    r2 = _make_recipe(client, auth_headers)
    _set_tags(client, auth_headers, r1, ["Shared", "Only1"])
    _set_tags(client, auth_headers, r2, ["Shared"])

    tags = client.get("/recipes/tags", headers=auth_headers).json()
    assert tags == [{"name": "Only1", "count": 1}, {"name": "Shared", "count": 2}]


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


def test_delete_recipe_removes_tags_from_listing(client, auth_headers, mocked_openai):
    uuid = _make_recipe(client, auth_headers)
    _set_tags(client, auth_headers, uuid, ["Lonely"])
    assert client.get("/recipes/tags", headers=auth_headers).json() == [
        {"name": "Lonely", "count": 1}
    ]

    client.delete(f"/recipes/{uuid}", headers=auth_headers)
    # Tag is no longer in use → drops out of the listing.
    assert client.get("/recipes/tags", headers=auth_headers).json() == []


def test_tags_are_user_isolated(client, auth_headers, mocked_openai, tmp_db_path):
    uuid = _make_recipe(client, auth_headers)
    _set_tags(client, auth_headers, uuid, ["Private"])
    b_headers = _second_user(tmp_db_path)

    assert client.get("/recipes/tags", headers=b_headers).json() == []
    # Filtering by A's tag returns nothing for B.
    resp = client.get("/recipes", headers=b_headers, params={"tag": "Private"}).json()
    assert resp["items"] == []

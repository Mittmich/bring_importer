"""Integration tests for personal cookbooks (Phase 2 of sharing)."""

import sqlite3

import pytest
from passlib.context import CryptContext

from api import create_access_token

_pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")


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

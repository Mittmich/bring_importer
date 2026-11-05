"""Tests for hand-entered recipes (POST /recipes) and duplicating (POST /recipes/{uuid}/clone)."""

import base64
import io
import json
import sqlite3

import pytest
from PIL import Image

import api.config as config


def _stored(db_path, recipe_uuid):
    conn = sqlite3.connect(str(db_path))
    try:
        row = conn.execute(
            "SELECT recipe_json, note, source, user_id, has_image FROM recipes WHERE uuid = ?",
            (recipe_uuid,),
        ).fetchone()
    finally:
        conn.close()
    return {
        "recipe": json.loads(row[0]),
        "note": row[1],
        "source": json.loads(row[2]),
        "user_id": row[3],
        "has_image": row[4],
    }


def _other_user_headers(db_path):
    from passlib.context import CryptContext

    from api.auth import create_access_token

    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            "INSERT INTO users (email, hashed_password) VALUES (?, ?)",
            ("b@example.com", CryptContext(schemes=["bcrypt"]).hash("bpassword")),
        )
        conn.commit()
    finally:
        conn.close()
    return {"Authorization": f"Bearer {create_access_token(data={'sub': 'b@example.com'})}"}


# ---------------------------------------------------------------------------
# POST /recipes
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_create_manual_recipe_minimal(client, auth_headers, tmp_db_path):
    resp = client.post(
        "/recipes",
        headers={**auth_headers, "Accept-Language": "de"},
        json={"title": "  Omas Gulasch  "},
    )
    assert resp.status_code == 200
    uuid = resp.json()["uuid"]
    stored = _stored(tmp_db_path, uuid)
    assert stored["recipe"]["name"] == "Omas Gulasch"
    assert stored["recipe"]["inLanguage"] == "de"  # from the request language
    assert stored["recipe"]["ingredients"] == []
    assert stored["source"] == {"kind": "manual", "value": ""}

    items = client.get("/recipes", headers=auth_headers).json()["items"]
    assert any(r["uuid"] == uuid for r in items)
    detail = client.get(f"/recipes/{uuid}.json", headers=auth_headers).json()
    assert detail["owned"] is True and detail["name"] == "Omas Gulasch"


@pytest.mark.integration
def test_create_manual_recipe_full(client, auth_headers, tmp_db_path):
    resp = client.post(
        "/recipes",
        headers=auth_headers,
        json={
            "title": "Pancakes",
            "language": "en",
            "recipeYield": "2 servings",
            "description": "Fluffy.",
            "note": "Kids love them.",
            "tags": ["Breakfast", "breakfast", "Sweet"],
            "is_public": True,
            "ingredients": [{"amount": "200 g", "name": "flour"}, {"amount": "2", "name": "eggs"}],
            "instructions": [{"text": "Mix.", "ingredients": [0, 1, 5, -1]}],
        },
    )
    assert resp.status_code == 200
    stored = _stored(tmp_db_path, resp.json()["uuid"])
    assert stored["recipe"]["inLanguage"] == "en"
    assert stored["recipe"]["recipeYield"] == "2 servings"
    assert stored["recipe"]["instructions"] == [{"text": "Mix.", "ingredients": [0, 1]}]
    assert stored["note"] == "Kids love them."
    detail = client.get(f"/recipes/{resp.json()['uuid']}.json").json()  # public → anonymous ok
    assert sorted(t["name"] for t in detail["tags"]) == ["Breakfast", "Sweet"]


@pytest.mark.integration
def test_create_manual_recipe_validation(client, auth_headers):
    assert client.post("/recipes", json={"title": "x"}).status_code == 401
    assert client.post("/recipes", headers=auth_headers, json={"title": "  "}).status_code == 422
    assert client.post("/recipes", headers=auth_headers, json={}).status_code == 422
    bad_lang = client.post("/recipes", headers=auth_headers, json={"title": "x", "language": "xx"})
    assert bad_lang.status_code == 422


# ---------------------------------------------------------------------------
# POST /recipes/{uuid}/clone — duplicating
# ---------------------------------------------------------------------------


@pytest.fixture
def image_dir(tmp_path, monkeypatch):
    d = tmp_path / "recipe_images"
    monkeypatch.setattr(config, "RECIPE_IMAGES_DIR", str(d))
    return d


def _jpeg_b64():
    buf = io.BytesIO()
    Image.new("RGB", (800, 450), (90, 140, 60)).save(buf, format="JPEG")
    return base64.b64encode(buf.getvalue()).decode()


def _owned_recipe(client, auth_headers):
    uuid = client.post(
        "/recipes",
        headers=auth_headers,
        json={"title": "Gulasch", "language": "de", "note": "Scharf!"},
    ).json()["uuid"]
    client.put(f"/recipes/{uuid}", headers=auth_headers, json={"tags": ["Hauptspeise"]})
    client.put(f"/recipes/{uuid}/image", headers=auth_headers, json={"image": _jpeg_b64()})
    return uuid


@pytest.mark.integration
def test_duplicate_own_private_recipe(client, auth_headers, tmp_db_path, image_dir):
    uuid = _owned_recipe(client, auth_headers)
    resp = client.post(f"/recipes/{uuid}/clone", headers=auth_headers)
    assert resp.status_code == 200
    new_uuid = resp.json()["uuid"]
    assert new_uuid != uuid

    copy = client.get(f"/recipes/{new_uuid}.json", headers=auth_headers).json()
    assert copy["name"] == "Gulasch (Kopie)"
    assert copy["note"] == "Scharf!"
    assert [t["name"] for t in copy["tags"]] == ["Hauptspeise"]
    assert copy["has_image"] is True
    assert (image_dir / f"{new_uuid}.jpg").read_bytes() == (image_dir / f"{uuid}.jpg").read_bytes()
    assert copy["is_public"] is False

    # The copy is independent: deleting the original keeps it (and its image).
    assert client.delete(f"/recipes/{uuid}", headers=auth_headers).status_code == 204
    assert client.get(f"/recipes/{new_uuid}/image", headers=auth_headers).status_code == 200


@pytest.mark.integration
def test_duplicate_suffixes_translations_in_their_language(client, auth_headers, tmp_db_path):
    uuid = client.post(
        "/recipes", headers=auth_headers, json={"title": "Pancakes", "language": "en"}
    ).json()["uuid"]
    conn = sqlite3.connect(str(tmp_db_path))
    data = json.loads(
        conn.execute("SELECT recipe_json FROM recipes WHERE uuid = ?", (uuid,)).fetchone()[0]
    )
    data["translations"] = {"de": {"name": "Pfannkuchen", "ingredients": [], "instructions": []}}
    conn.execute("UPDATE recipes SET recipe_json = ? WHERE uuid = ?", (json.dumps(data), uuid))
    conn.commit()
    conn.close()

    new_uuid = client.post(f"/recipes/{uuid}/clone", headers=auth_headers).json()["uuid"]
    stored = _stored(tmp_db_path, new_uuid)["recipe"]
    assert stored["name"] == "Pancakes (copy)"
    assert stored["translations"]["de"]["name"] == "Pfannkuchen (Kopie)"


@pytest.mark.integration
def test_clone_public_recipe_of_someone_else(client, auth_headers, tmp_db_path, image_dir):
    uuid = _owned_recipe(client, auth_headers)
    client.put(f"/recipes/{uuid}", headers=auth_headers, json={"is_public": True})
    b_headers = _other_user_headers(tmp_db_path)

    new_uuid = client.post(f"/recipes/{uuid}/clone", headers=b_headers).json()["uuid"]
    copy = client.get(f"/recipes/{new_uuid}.json", headers=b_headers).json()
    assert copy["owned"] is True
    assert copy["name"] == "Gulasch"  # not a duplicate of your own → no suffix
    assert copy["note"] == ""  # the owner's note and tags stay private
    assert copy["tags"] == []
    assert copy["has_image"] is True


@pytest.mark.integration
def test_clone_requires_visibility(client, auth_headers, tmp_db_path):
    uuid = client.post("/recipes", headers=auth_headers, json={"title": "Secret"}).json()["uuid"]
    b_headers = _other_user_headers(tmp_db_path)
    assert client.post(f"/recipes/{uuid}/clone", headers=b_headers).status_code == 404
    assert client.post(f"/recipes/{uuid}/clone").status_code == 401


# ---------------------------------------------------------------------------
# Ingredient lines ("one per line" in the manual form)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "line,amount,name",
    [
        ("500 g Rindfleisch", "500 g", "Rindfleisch"),
        ("2 Zwiebeln", "2", "Zwiebeln"),
        ("1 EL Paprikapulver, edelsüß", "1 EL", "Paprikapulver, edelsüß"),
        ("1/2 TL Kümmel", "1/2 TL", "Kümmel"),
        ("1 1/2 cups flour", "1 1/2 cups", "flour"),
        ("½ Bund Petersilie", "½ Bund", "Petersilie"),
        ("1,5 l Brühe", "1,5 l", "Brühe"),
        ("2-3 Knoblauchzehen", "2-3", "Knoblauchzehen"),
        ("ca. 200 ml Sahne", "ca. 200 ml", "Sahne"),
        ("3 Zehen Knoblauch", "3 Zehen", "Knoblauch"),
        ("200g Mehl", "200g", "Mehl"),
        ("- 1 Prise Salz", "1 Prise", "Salz"),
        ("• Salz und Pfeffer", "", "Salz und Pfeffer"),
        ("Salt, to taste", "", "Salt, to taste"),
        ("2 large eggs", "2", "large eggs"),
        ("1 Glasnudeln", "1", "Glasnudeln"),  # unit prefix of a word isn't a unit
        ("4", "", "4"),  # nothing after the number → keep as name
    ],
)
def test_parse_ingredient_line(line, amount, name):
    from api.ingredient_lines import parse_ingredient_line

    ing = parse_ingredient_line(line)
    assert (ing.amount, ing.name) == (amount, name)


def test_parse_ingredient_lines_skips_blanks():
    from api.ingredient_lines import parse_ingredient_lines

    parsed = parse_ingredient_lines("500 g Mehl\n\n  \n- \n2 Eier\r\n")
    assert [(i.amount, i.name) for i in parsed] == [("500 g", "Mehl"), ("2", "Eier")]


@pytest.mark.integration
def test_create_manual_recipe_with_ingredient_text(client, auth_headers, tmp_db_path):
    resp = client.post(
        "/recipes",
        headers=auth_headers,
        json={
            "title": "Gulasch",
            "recipeYield": "4 Portionen",
            "ingredients_text": "500 g Rindfleisch\n2 Zwiebeln\nSalz",
        },
    )
    stored = _stored(tmp_db_path, resp.json()["uuid"])["recipe"]
    assert stored["ingredients"] == [
        {"amount": "500 g", "name": "Rindfleisch"},
        {"amount": "2", "name": "Zwiebeln"},
        {"amount": "", "name": "Salz"},
    ]
    assert stored["recipeYield"] == "4 Portionen"

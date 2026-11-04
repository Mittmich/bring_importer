"""Tests for the recipe PDF export: scaling, document model, rendering, endpoint."""

import base64
import io
import json
import sqlite3
from datetime import date
from unittest.mock import patch

import pytest
from PIL import Image

import api.config as config
from api.i18n import BACKEND_STRINGS, SUPPORTED_LANGUAGES
from api.recipe_pdf import (
    build_document,
    content_disposition,
    format_amount,
    parse_servings,
    pdf_filename,
    render_pdf,
    sanitize,
    scale_text,
    servings_unit,
)

# ---------------------------------------------------------------------------
# Scaling — must match frontend-react/src/lib/scaling.ts
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text,factor,expected",
    [
        ("200 g", 1.5, "300 g"),
        ("1/2 TL", 1.5, "¾ TL"),
        ("1 1/2 EL", 2, "3 EL"),
        ("1,5 l", 2, "3 l"),
        ("2", 1.5, "3"),
        ("3 eggs", 1 / 3, "1 eggs"),
        ("1 cup", 1 / 3, "⅓ cup"),
        ("2 cups", 1.25, "2½ cups"),
        ("0.3 l", 1, "0.3 l"),  # factor 1 → untouched
        ("1 Prise", 2.2, "2¼ Prise"),  # near a fraction → fraction (like the app)
        ("1 Prise", 2.4, "2.4 Prise"),
        ("to taste", 3, "to taste"),
    ],
)
def test_scale_text(text, factor, expected):
    assert scale_text(text, factor) == expected


def test_format_amount_and_servings_parsing():
    assert format_amount(0.25) == "¼"
    assert format_amount(2.0) == "2"
    assert format_amount(2.66) == "2⅔"
    assert parse_servings("4 Portionen") == 4
    assert parse_servings("serves 6-8") == 6
    assert parse_servings("") == 4
    assert servings_unit("4 Portionen", "servings") == "Portionen"
    assert servings_unit("4", "servings") == "servings"
    assert servings_unit(None, "Portionen") == "Portionen"


# ---------------------------------------------------------------------------
# Text, labels, filenames
# ---------------------------------------------------------------------------


def test_sanitize_keeps_latin_drops_emoji():
    assert sanitize("Kaiserschmarrn 🍽 „süß“ – ½ ⅓ 180 °C") == "Kaiserschmarrn „süß“ – ½ ⅓ 180 °C"
    assert sanitize("ﬃ") == "ffi"  # decomposed ligature
    assert sanitize("a\tb\x00c") == "a bc"
    assert sanitize(None) == ""


def test_backend_strings_complete_for_every_language():
    keys = set(BACKEND_STRINGS["en"])
    for lang in SUPPORTED_LANGUAGES:
        assert set(BACKEND_STRINGS[lang]) == keys, lang


def test_filename_and_content_disposition():
    assert pdf_filename("Kaiserschmarrn / Omas Art") == "Kaiserschmarrn Omas Art.pdf"
    assert pdf_filename("  ") == "recipe.pdf"
    header = content_disposition("Gefüllte Paprika.pdf")
    assert header.startswith('inline; filename="Gefullte Paprika.pdf"')
    assert "filename*=UTF-8''Gef%C3%BCllte%20Paprika.pdf" in header


# ---------------------------------------------------------------------------
# Document model
# ---------------------------------------------------------------------------

RECIPE = {
    "name": "Pfannkuchen",
    "language": "de",
    "recipeYield": "4 Portionen",
    "description": "Locker.",
    "source": {"kind": "url", "value": "https://www.example.at/pfannkuchen"},
    "tags": [{"name": "Frühstück", "color": None}],
    "note": "Mit Ahornsirup.",
    "ingredients": [
        {"amount": "200 g", "name": "Mehl"},
        {"amount": "2", "name": "Eier"},
        {"amount": "", "name": "Salz"},
    ],
    "instructions": [
        {"text": "Mehl und Eier verrühren.", "ingredients": [0, 1]},
        {"text": "  ", "ingredients": []},  # blank steps are skipped
        {"text": "Salzen.", "ingredients": [2, 99]},  # out-of-range index ignored
    ],
}


def test_build_document_scales_and_localizes():
    doc = build_document(RECIPE, servings=6, lang="de", today=date(2026, 11, 5))
    assert doc.title == "Pfannkuchen"
    assert doc.servings == "6 Portionen"
    assert doc.source == "example.at"
    assert doc.tags == ["Frühstück"]
    assert [(i.amount, i.name) for i in doc.ingredients] == [
        ("300 g", "Mehl"),
        ("3", "Eier"),
        ("", "Salz"),
    ]
    assert [s.number for s in doc.steps] == [1, 2]
    assert doc.steps[0].uses == ["300 g Mehl", "3 Eier"]
    assert doc.steps[1].uses == ["Salz"]
    assert doc.labels["ingredients"] == "Zutaten"
    assert doc.exported == "Exportiert aus Meine Rezepte am 05.11.2026"


def test_build_document_defaults_and_english_labels():
    doc = build_document({**RECIPE, "recipeYield": ""}, lang="en")
    assert doc.servings is None  # no yield, no explicit servings → no servings line
    assert doc.labels["instructions"] == "Instructions"
    assert doc.ingredients[0].amount == "200 g"  # unscaled


def test_build_document_handles_old_flat_format_and_missing_title():
    doc = build_document(
        {"recipeIngredient": ["2 eggs"], "recipeInstructions": ["Whisk."]}, lang="en"
    )
    assert doc.title == "Untitled recipe"
    assert doc.ingredients[0].name == "2 eggs"
    assert doc.steps[0].text == "Whisk."


def _photo(path, size=(1200, 900)):
    Image.new("RGB", size, (200, 120, 60)).save(path, format="JPEG")


def test_render_pdf_with_and_without_photo(tmp_path):
    doc = build_document(RECIPE, lang="de")
    plain = render_pdf(doc)
    assert plain.startswith(b"%PDF-")
    assert b"/Subtype /Image" not in plain

    photo = tmp_path / "hero.jpg"
    _photo(photo)
    with_photo = render_pdf(doc, str(photo))
    assert b"/Subtype /Image" in with_photo
    assert b"/DCTDecode" in with_photo  # embedded as JPEG, not lossless


def test_render_pdf_survives_unreadable_image_and_long_recipes(tmp_path):
    broken = tmp_path / "broken.jpg"
    broken.write_bytes(b"not an image")
    long_recipe = {
        **RECIPE,
        "ingredients": [{"amount": f"{i} g", "name": "Zutat " * 12} for i in range(60)],
        "instructions": [{"text": "Rühren. " * 80, "ingredients": [0, 1]} for _ in range(25)],
    }
    out = render_pdf(build_document(long_recipe, lang="de"), str(broken))
    assert out.startswith(b"%PDF-")
    assert out.count(b"/Type /Page\n") > 2 or out.count(b"/Type /Page ") > 2 or b"/Count " in out


# ---------------------------------------------------------------------------
# GET /recipes/{uuid}.pdf
# ---------------------------------------------------------------------------


@pytest.fixture
def image_dir(tmp_path, monkeypatch):
    d = tmp_path / "recipe_images"
    monkeypatch.setattr(config, "RECIPE_IMAGES_DIR", str(d))
    return d


def _make_recipe(client, auth_headers):
    resp = client.post(
        "/recipes/parse", headers=auth_headers, data={"image": "aGVsbG8=", "language": "en"}
    )
    assert resp.status_code == 200
    return resp.json()["uuid"]


@pytest.mark.integration
def test_pdf_endpoint_owner(client, auth_headers, mocked_openai):
    uuid = _make_recipe(client, auth_headers)
    resp = client.get(f"/recipes/{uuid}.pdf", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    assert resp.content.startswith(b"%PDF-")
    assert 'filename="Test Pancakes.pdf"' in resp.headers["content-disposition"]
    assert resp.headers["cache-control"] == "private, no-store"


@pytest.mark.integration
def test_pdf_endpoint_access(client, auth_headers, mocked_openai):
    uuid = _make_recipe(client, auth_headers)
    assert client.get(f"/recipes/{uuid}.pdf").status_code == 404  # private, anonymous
    assert client.get("/recipes/nope.pdf", headers=auth_headers).status_code == 404
    client.put(f"/recipes/{uuid}", headers=auth_headers, json={"is_public": True})
    assert client.get(f"/recipes/{uuid}.pdf").status_code == 200  # public


@pytest.mark.integration
def test_pdf_endpoint_validates_servings(client, auth_headers, mocked_openai):
    uuid = _make_recipe(client, auth_headers)
    assert client.get(f"/recipes/{uuid}.pdf?servings=0", headers=auth_headers).status_code == 422
    assert client.get(f"/recipes/{uuid}.pdf?servings=8", headers=auth_headers).status_code == 200


@pytest.mark.integration
def test_pdf_endpoint_uses_language_and_servings(client, auth_headers, mocked_openai, tmp_db_path):
    uuid = _make_recipe(client, auth_headers)
    conn = sqlite3.connect(str(tmp_db_path))
    data = json.loads(
        conn.execute("SELECT recipe_json FROM recipes WHERE uuid = ?", (uuid,)).fetchone()[0]
    )
    data["translations"] = {
        "de": {
            "name": "Test-Pfannkuchen",
            "recipeYield": "4 Portionen",
            "ingredients": [{"amount": "1 Tasse", "name": "Mehl"}],
            "instructions": [{"text": "Mischen.", "ingredients": [0]}],
        }
    }
    conn.execute("UPDATE recipes SET recipe_json = ? WHERE uuid = ?", (json.dumps(data), uuid))
    conn.commit()
    conn.close()

    with patch("api.routers.recipes.build_document", wraps=build_document) as spy:
        resp = client.get(
            f"/recipes/{uuid}.pdf?servings=8",
            headers={**auth_headers, "Accept-Language": "de-AT"},
        )
    assert resp.status_code == 200
    assert "Test-Pfannkuchen.pdf" in resp.headers["content-disposition"]
    payload = spy.call_args.args[0]
    assert payload["name"] == "Test-Pfannkuchen"
    assert spy.call_args.kwargs == {"servings": 8, "lang": "de"}


@pytest.mark.integration
def test_pdf_endpoint_embeds_photo(client, auth_headers, mocked_openai, image_dir, tmp_path):
    uuid = _make_recipe(client, auth_headers)
    buf = io.BytesIO()
    Image.new("RGB", (1600, 900), (90, 140, 60)).save(buf, format="JPEG")
    client.put(
        f"/recipes/{uuid}/image",
        headers=auth_headers,
        json={"image": base64.b64encode(buf.getvalue()).decode()},
    )
    resp = client.get(f"/recipes/{uuid}.pdf", headers=auth_headers)
    assert resp.status_code == 200
    assert b"/Subtype /Image" in resp.content

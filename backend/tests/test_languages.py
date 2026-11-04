"""Tests for language support: profile language, localization, translation, imports."""

import json
import sqlite3
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api import translation as translation_mod
from api.i18n import localize_recipe, normalize_language, parse_accept_language
from api.models import Ingredient
from api.translation import TranslationError, _TranslationOutput, translate_recipe_content

DE = {"Accept-Language": "de-AT,de;q=0.9,en;q=0.5"}

GERMAN_VARIANT = {
    "name": "Test-Pfannkuchen",
    "description": "Locker und flaumig.",
    "recipeYield": "4 Portionen",
    "ingredients": [
        {"amount": "1 Tasse", "name": "Mehl"},
        {"amount": "2", "name": "Eier"},
        {"amount": "1 Tasse", "name": "Milch"},
    ],
    "instructions": [
        {"text": "Trockene Zutaten mischen.", "ingredients": [0]},
        {"text": "Eier und Milch zugeben, rühren.", "ingredients": [1, 2]},
    ],
}


def _make_recipe(client, auth_headers, headers=None, data=None) -> str:
    resp = client.post(
        "/recipes/parse",
        headers={**auth_headers, **(headers or {})},
        data={"image": "aGVsbG8=", **(data or {})},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["uuid"]


def _stored(tmp_db_path, uuid):
    conn = sqlite3.connect(str(tmp_db_path))
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute("SELECT recipe_json FROM recipes WHERE uuid = ?", (uuid,)).fetchone()
    finally:
        conn.close()
    return json.loads(row["recipe_json"])


def _patch_stored(tmp_db_path, uuid, **changes):
    data = _stored(tmp_db_path, uuid)
    data.update(changes)
    conn = sqlite3.connect(str(tmp_db_path))
    try:
        conn.execute("UPDATE recipes SET recipe_json = ? WHERE uuid = ?", (json.dumps(data), uuid))
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


def test_normalize_language():
    assert normalize_language("de-AT") == "de"
    assert normalize_language("EN_us") == "en"
    assert normalize_language("fr") is None
    assert normalize_language("") is None
    assert normalize_language(None) is None


def test_parse_accept_language_respects_weights_and_support():
    assert parse_accept_language("fr-FR,de;q=0.8,en;q=0.9") == "en"
    assert parse_accept_language("fr,de") == "de"
    assert parse_accept_language("fr,it") is None
    assert parse_accept_language(None) is None


def test_localize_recipe_picks_translation_and_flags_missing():
    stored = {
        "name": "Pancakes",
        "ingredients": [],
        "instructions": [],
        "inLanguage": "en",
        "translations": {"de": {"name": "Pfannkuchen"}},
    }
    de = localize_recipe(stored, "de")
    assert de["name"] == "Pfannkuchen"
    assert de["language"] == "de"
    assert de["translation_available"] is True
    assert "translations" not in de
    assert de["available_languages"] == ["en", "de"]

    en = localize_recipe(stored, "en")
    assert en["name"] == "Pancakes" and en["language"] == "en"

    # Known base language, no translation → flagged as missing.
    no_de = localize_recipe({"name": "X", "inLanguage": "en"}, "de")
    assert no_de["translation_available"] is False
    # Unknown base language → not flagged (we can't know).
    legacy = localize_recipe({"name": "X"}, "de")
    assert legacy["translation_available"] is True
    assert legacy["language"] is None


def test_translate_recipe_content_preserves_structure():
    out = _TranslationOutput(
        source_language="en",
        name="Pfannkuchen",
        description="",
        recipeYield="4 Portionen",
        ingredients=[Ingredient(amount="1 Tasse", name="Mehl")],
        instructions=["Mischen."],
    )
    content = {
        "name": "Pancakes",
        "ingredients": [{"amount": "1 cup", "name": "flour"}],
        "instructions": [{"text": "Mix.", "ingredients": [0]}],
    }
    with patch.dict(
        translation_mod._PROVIDERS,
        {"openai": translation_mod.Provider(translate=lambda c, t: out, detect=lambda x: "en")},
    ):
        translated, src = translate_recipe_content(content, "de")
    assert src == "en"
    assert translated["instructions"] == [{"text": "Mischen.", "ingredients": [0]}]
    assert translated["ingredients"] == [{"amount": "1 Tasse", "name": "Mehl"}]


def test_translate_recipe_content_rejects_count_mismatch():
    out = _TranslationOutput(
        source_language="en",
        name="x",
        description="",
        recipeYield="",
        ingredients=[],
        instructions=[],
    )
    content = {"name": "x", "ingredients": [{"amount": "", "name": "a"}], "instructions": []}
    with patch.dict(
        translation_mod._PROVIDERS,
        {"openai": translation_mod.Provider(translate=lambda c, t: out, detect=lambda x: "en")},
    ):
        with pytest.raises(TranslationError):
            translate_recipe_content(content, "de")


# ---------------------------------------------------------------------------
# Profile language
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_profile_language_roundtrip(client, auth_headers):
    resp = client.put("/account/profile", headers=auth_headers, json={"language": "de"})
    assert resp.status_code == 200
    assert resp.json()["language"] == "de"
    # Display-name-only update leaves the language alone.
    client.put("/account/profile", headers=auth_headers, json={"display_name": "Chef"})
    prof = client.get("/account/profile", headers=auth_headers).json()
    assert prof["language"] == "de" and prof["display_name"] == "Chef"


@pytest.mark.integration
def test_profile_unsupported_language_is_422(client, auth_headers):
    resp = client.put("/account/profile", headers=auth_headers, json={"language": "xx"})
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Extraction in the target language
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_parse_uses_request_language(client, auth_headers, mocked_openai, tmp_db_path):
    uuid = _make_recipe(client, auth_headers, headers=DE)
    args = mocked_openai["parse_image"].call_args
    assert args.args[1] == "de"
    assert _stored(tmp_db_path, uuid)["inLanguage"] == "de"


@pytest.mark.integration
def test_parse_explicit_language_wins(client, auth_headers, mocked_openai, tmp_db_path):
    uuid = _make_recipe(client, auth_headers, headers=DE, data={"language": "en"})
    assert mocked_openai["parse_image"].call_args.args[1] == "en"
    assert _stored(tmp_db_path, uuid)["inLanguage"] == "en"


@pytest.mark.integration
def test_parse_falls_back_to_profile_language(client, auth_headers, mocked_openai):
    client.put("/account/profile", headers=auth_headers, json={"language": "de"})
    _make_recipe(client, auth_headers)
    assert mocked_openai["parse_image"].call_args.args[1] == "de"


def _fake_get(html: str):
    resp = MagicMock()
    resp.status_code = 200
    resp.text = html
    resp.content = html.encode()
    resp.raise_for_status = MagicMock()
    instance = MagicMock()
    instance.__aenter__ = AsyncMock(return_value=instance)
    instance.__aexit__ = AsyncMock(return_value=None)
    instance.get = AsyncMock(return_value=resp)
    return instance


JSONLD_PAGE = (
    '<script type="application/ld+json">{"@type": "Recipe", "name": "Pancakes",'
    ' "recipeIngredient": ["1 cup flour"]}</script>'
)


@pytest.mark.integration
def test_import_url_jsonld_keeps_original_and_stores_translation(
    client, auth_headers, mocked_openai, tmp_db_path
):
    with (
        patch("api.routers.recipes.httpx.AsyncClient", return_value=_fake_get(JSONLD_PAGE)),
        patch(
            "api.routers.recipes.translate_recipe_content",
            return_value=(GERMAN_VARIANT, "en"),
        ) as mock_translate,
    ):
        resp = client.post(
            "/recipes/import-url",
            headers={**auth_headers, **DE},
            json={"url": "https://example.test/r"},
        )
    assert resp.status_code == 200, resp.text
    assert mock_translate.call_args.args[1] == "de"
    stored = _stored(tmp_db_path, resp.json()["uuid"])
    assert stored["inLanguage"] == "en"
    assert stored["name"] == "Test Pancakes"  # original kept as base
    assert stored["translations"]["de"]["name"] == "Test-Pfannkuchen"


@pytest.mark.integration
def test_import_url_jsonld_translation_failure_still_imports(
    client, auth_headers, mocked_openai, tmp_db_path
):
    with (
        patch("api.routers.recipes.httpx.AsyncClient", return_value=_fake_get(JSONLD_PAGE)),
        patch(
            "api.routers.recipes.translate_recipe_content",
            side_effect=TranslationError("boom"),
        ),
    ):
        resp = client.post(
            "/recipes/import-url",
            headers={**auth_headers, **DE},
            json={"url": "https://example.test/r"},
        )
    assert resp.status_code == 200
    stored = _stored(tmp_db_path, resp.json()["uuid"])
    assert "translations" not in stored


@pytest.mark.integration
def test_import_url_html_fallback_gets_language(client, auth_headers, mocked_openai):
    with patch("api.routers.recipes.httpx.AsyncClient", return_value=_fake_get("<p>no jsonld</p>")):
        resp = client.post(
            "/recipes/import-url",
            headers=auth_headers,
            json={"url": "https://example.test/r", "language": "de"},
        )
    assert resp.status_code == 200
    assert mocked_openai["html_text"].call_args.kwargs["language"] == "de"


# ---------------------------------------------------------------------------
# Localized display
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_get_recipe_localized(client, auth_headers, mocked_openai, tmp_db_path):
    uuid = _make_recipe(client, auth_headers, data={"language": "en"})
    _patch_stored(tmp_db_path, uuid, translations={"de": GERMAN_VARIANT})

    de = client.get(f"/recipes/{uuid}.json", headers={**auth_headers, **DE}).json()
    assert de["name"] == "Test-Pfannkuchen"
    assert de["ingredients"][0]["name"] == "Mehl"
    assert de["language"] == "de"
    assert de["available_languages"] == ["en", "de"]

    # ?lang= overrides the header.
    en = client.get(f"/recipes/{uuid}.json?lang=en", headers={**auth_headers, **DE}).json()
    assert en["name"] == "Test Pancakes"


@pytest.mark.integration
def test_get_recipe_flags_missing_translation(client, auth_headers, mocked_openai):
    uuid = _make_recipe(client, auth_headers, data={"language": "en"})
    de = client.get(f"/recipes/{uuid}.json", headers={**auth_headers, **DE}).json()
    assert de["name"] == "Test Pancakes"
    assert de["translation_available"] is False
    assert de["requested_language"] == "de"


@pytest.mark.integration
def test_list_and_search_localized(client, auth_headers, mocked_openai, tmp_db_path):
    uuid = _make_recipe(client, auth_headers, data={"language": "en"})
    _patch_stored(tmp_db_path, uuid, translations={"de": GERMAN_VARIANT})

    items = client.get("/recipes", headers={**auth_headers, **DE}).json()["items"]
    assert items[0]["title"] == "Test-Pfannkuchen"
    assert items[0]["language"] == "de"

    # Translated text is searchable.
    found = client.get("/recipes?q=Mehl", headers=auth_headers).json()
    assert found["total"] == 1


@pytest.mark.integration
def test_recipe_html_localized(client, auth_headers, mocked_openai, tmp_db_path):
    uuid = _make_recipe(client, auth_headers, data={"language": "en"})
    _patch_stored(tmp_db_path, uuid, translations={"de": GERMAN_VARIANT})
    html = client.get(f"/recipes/{uuid}.html?lang=de").text
    assert '<html lang="de">' in html
    assert "1 Tasse Mehl" in html


@pytest.mark.integration
def test_meal_plan_title_localized(client, auth_headers, mocked_openai, tmp_db_path):
    uuid = _make_recipe(client, auth_headers, data={"language": "en"})
    _patch_stored(tmp_db_path, uuid, translations={"de": GERMAN_VARIANT})
    client.post(
        "/meal-plan", headers=auth_headers, json={"date": "2026-06-22", "recipe_uuid": uuid}
    )
    entries = client.get(
        "/meal-plan?start=2026-06-22&end=2026-06-28", headers={**auth_headers, **DE}
    ).json()
    assert entries[0]["recipe_title"] == "Test-Pfannkuchen"


# ---------------------------------------------------------------------------
# Editing a language variant
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_put_edits_translation_not_base(client, auth_headers, mocked_openai, tmp_db_path):
    uuid = _make_recipe(client, auth_headers, data={"language": "en"})
    _patch_stored(tmp_db_path, uuid, translations={"de": GERMAN_VARIANT})

    resp = client.put(
        f"/recipes/{uuid}",
        headers=auth_headers,
        json={"language": "de", "title": "Omas Pfannkuchen"},
    )
    assert resp.status_code == 200
    assert resp.json()["name"] == "Omas Pfannkuchen"
    stored = _stored(tmp_db_path, uuid)
    assert stored["name"] == "Test Pancakes"
    assert stored["translations"]["de"]["name"] == "Omas Pfannkuchen"


@pytest.mark.integration
def test_put_declares_base_language(client, auth_headers, mocked_openai, tmp_db_path):
    uuid = _make_recipe(client, auth_headers)  # no language → unknown base
    assert _stored(tmp_db_path, uuid)["inLanguage"] is None
    resp = client.put(f"/recipes/{uuid}", headers=auth_headers, json={"inLanguage": "en"})
    assert resp.status_code == 200
    assert resp.json()["language"] == "en"
    bad = client.put(f"/recipes/{uuid}", headers=auth_headers, json={"inLanguage": "xx"})
    assert bad.status_code == 422


# ---------------------------------------------------------------------------
# POST /recipes/{uuid}/translate
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_translate_endpoint_stores_translation(client, auth_headers, mocked_openai, tmp_db_path):
    uuid = _make_recipe(client, auth_headers, data={"language": "en"})
    with patch(
        "api.translation.translate_recipe_content", return_value=(GERMAN_VARIANT, "en")
    ) as mock_translate:
        resp = client.post(
            f"/recipes/{uuid}/translate", headers=auth_headers, json={"language": "de"}
        )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["name"] == "Test-Pfannkuchen"
    assert body["language"] == "de"
    assert body["translation_available"] is True
    # Source sent to the provider is the base content.
    assert mock_translate.call_args.args[0]["name"] == "Test Pancakes"
    assert _stored(tmp_db_path, uuid)["translations"]["de"]["name"] == "Test-Pfannkuchen"


@pytest.mark.integration
def test_translate_detects_unknown_base_language(client, auth_headers, mocked_openai, tmp_db_path):
    uuid = _make_recipe(client, auth_headers)  # unknown base
    # Detected source equals target → nothing stored but language recorded.
    with patch("api.translation.translate_recipe_content", return_value=(GERMAN_VARIANT, "de")):
        resp = client.post(
            f"/recipes/{uuid}/translate", headers=auth_headers, json={"language": "de"}
        )
    assert resp.status_code == 200
    stored = _stored(tmp_db_path, uuid)
    assert stored["inLanguage"] == "de"
    assert "translations" not in stored


@pytest.mark.integration
def test_translate_provider_error_is_502(client, auth_headers, mocked_openai):
    uuid = _make_recipe(client, auth_headers, data={"language": "en"})
    with patch("api.translation.translate_recipe_content", side_effect=TranslationError("nope")):
        resp = client.post(
            f"/recipes/{uuid}/translate", headers=auth_headers, json={"language": "de"}
        )
    assert resp.status_code == 502


@pytest.mark.integration
def test_translate_validation_and_access(client, auth_headers, mocked_openai):
    uuid = _make_recipe(client, auth_headers, data={"language": "en"})
    bad = client.post(f"/recipes/{uuid}/translate", headers=auth_headers, json={"language": "xx"})
    assert bad.status_code == 422
    missing = client.post(
        "/recipes/does-not-exist/translate", headers=auth_headers, json={"language": "de"}
    )
    assert missing.status_code == 404
    anon = client.post(f"/recipes/{uuid}/translate", json={"language": "de"})
    assert anon.status_code == 401


@pytest.mark.integration
def test_clone_keeps_translations(client, auth_headers, mocked_openai, tmp_db_path):
    uuid = _make_recipe(client, auth_headers, data={"language": "en"})
    _patch_stored(tmp_db_path, uuid, translations={"de": GERMAN_VARIANT})
    client.put(f"/recipes/{uuid}", headers=auth_headers, json={"is_public": True})
    new_uuid = client.post(f"/recipes/{uuid}/clone", headers=auth_headers).json()["uuid"]
    stored = _stored(tmp_db_path, new_uuid)
    assert stored["inLanguage"] == "en"
    assert stored["translations"]["de"]["name"] == "Test-Pfannkuchen"

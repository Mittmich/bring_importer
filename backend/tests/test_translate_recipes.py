"""Tests for the one-off ``translate_recipes.py`` language backfill script."""

import json
import sqlite3
from unittest.mock import patch

import pytest

import translate_recipes
from api.translation import TranslationError

GERMAN = {
    "name": "Test-Pfannkuchen",
    "description": "",
    "recipeYield": "4 Portionen",
    "ingredients": [{"amount": "1 Tasse", "name": "Mehl"}],
    "instructions": [{"text": "Mischen.", "ingredients": [0]}],
}


def _translated_into(target_marker):
    """A translate_recipe_content stand-in that tags the output with the target."""

    def fake(content, target):
        return ({**GERMAN, "name": f"{target_marker}-{target}"}, "en")

    return fake


def _seed(client, auth_headers, tmp_db_path, n=1):
    """Create ``n`` legacy recipes (no inLanguage) via the mocked import."""
    uuids = []
    for _ in range(n):
        resp = client.post("/recipes/parse", headers=auth_headers, data={"image": "aGVsbG8="})
        uuids.append(resp.json()["uuid"])
    conn = sqlite3.connect(str(tmp_db_path))
    for u in uuids:
        data = json.loads(
            conn.execute("SELECT recipe_json FROM recipes WHERE uuid = ?", (u,)).fetchone()[0]
        )
        data.pop("inLanguage", None)
        conn.execute("UPDATE recipes SET recipe_json = ? WHERE uuid = ?", (json.dumps(data), u))
    conn.commit()
    conn.close()
    return uuids


def _stored(tmp_db_path, uuid):
    conn = sqlite3.connect(str(tmp_db_path))
    try:
        raw = conn.execute("SELECT recipe_json FROM recipes WHERE uuid = ?", (uuid,)).fetchone()[0]
    finally:
        conn.close()
    return json.loads(raw)


@pytest.fixture
def legacy(client, auth_headers, mocked_openai, tmp_db_path):
    return _seed(client, auth_headers, tmp_db_path, n=2)


def test_dry_run_makes_no_calls_or_writes(legacy, tmp_db_path):
    with (
        patch("translate_recipes.detect_recipe_language") as detect,
        patch("api.translation.translate_recipe_content") as translate,
    ):
        stats = translate_recipes.run(dry_run=True)
    assert stats["processed"] == 2
    detect.assert_not_called()
    translate.assert_not_called()
    assert "inLanguage" not in _stored(tmp_db_path, legacy[0])


def test_detects_then_translates_missing_languages(legacy, tmp_db_path):
    with (
        patch("translate_recipes.detect_recipe_language", return_value="en"),
        patch("api.translation.translate_recipe_content", side_effect=_translated_into("x")),
    ):
        stats = translate_recipes.run()
    assert stats["detected"] == 2
    assert stats["translations"] == 2  # only German — the base is already English
    stored = _stored(tmp_db_path, legacy[0])
    assert stored["inLanguage"] == "en"
    assert list(stored["translations"]) == ["de"]
    assert stored["translations"]["de"]["name"] == "x-de"


def test_rerun_is_idempotent(legacy):
    with (
        patch("translate_recipes.detect_recipe_language", return_value="en"),
        patch("api.translation.translate_recipe_content", side_effect=_translated_into("x")),
    ):
        translate_recipes.run()
    with (
        patch("translate_recipes.detect_recipe_language") as detect,
        patch("api.translation.translate_recipe_content") as translate,
    ):
        stats = translate_recipes.run()
    assert stats["complete"] == 2 and stats["processed"] == 0
    detect.assert_not_called()
    translate.assert_not_called()


def test_detect_only(legacy, tmp_db_path):
    with (
        patch("translate_recipes.detect_recipe_language", return_value="de"),
        patch("api.translation.translate_recipe_content") as translate,
    ):
        translate_recipes.run(detect_only=True)
    translate.assert_not_called()
    stored = _stored(tmp_db_path, legacy[0])
    assert stored["inLanguage"] == "de"
    assert "translations" not in stored


def test_unsupported_language_translates_into_all_targets(legacy, tmp_db_path):
    with (
        patch("translate_recipes.detect_recipe_language", return_value="fr"),
        patch(
            "api.translation.translate_recipe_content",
            side_effect=lambda c, t: ({**GERMAN, "name": t}, "fr"),
        ),
    ):
        translate_recipes.run(limit=1)
    stored = _stored(tmp_db_path, legacy[0])
    assert stored.get("inLanguage") is None  # unsupported codes aren't stored
    assert sorted(stored["translations"]) == ["de", "en"]


def test_translation_error_keeps_progress_and_fails(legacy, tmp_db_path):
    with (
        patch("translate_recipes.detect_recipe_language", return_value="en"),
        patch("api.translation.translate_recipe_content", side_effect=TranslationError("boom")),
    ):
        stats = translate_recipes.run()
    assert stats["errors"] == 2
    # Detection still saved, so the next run only has to translate.
    assert _stored(tmp_db_path, legacy[0])["inLanguage"] == "en"


def test_skips_recipe_edited_meanwhile(legacy, tmp_db_path):
    def edit_then_translate(content, target):
        conn = sqlite3.connect(str(tmp_db_path))
        conn.execute("UPDATE recipes SET updated_at = 'edited-by-user'")
        conn.commit()
        conn.close()
        return (GERMAN, "en")

    with (
        patch("translate_recipes.detect_recipe_language", return_value="en"),
        patch("api.translation.translate_recipe_content", side_effect=edit_then_translate),
    ):
        stats = translate_recipes.run(only_uuid=legacy[0])
    assert stats["changed_meanwhile"] == 1
    assert "translations" not in _stored(tmp_db_path, legacy[0])


def test_limit_and_languages(legacy, tmp_db_path):
    with (
        patch("translate_recipes.detect_recipe_language", return_value="en"),
        patch("api.translation.translate_recipe_content", side_effect=_translated_into("x")),
    ):
        stats = translate_recipes.run(limit=1, targets=["en"])
    assert stats["processed"] == 1
    # Target "en" equals the detected base → nothing to translate.
    assert "translations" not in _stored(tmp_db_path, legacy[0])
    assert _stored(tmp_db_path, legacy[1]).get("inLanguage") is None


def test_parse_languages():
    assert translate_recipes.parse_languages("de, EN,de") == ["de", "en"]
    assert translate_recipes.parse_languages(None) == ["en", "de"]
    with pytest.raises(SystemExit):
        translate_recipes.parse_languages("xx")


def test_main_exit_code(legacy):
    with (
        patch("translate_recipes.detect_recipe_language", return_value="en"),
        patch("api.translation.translate_recipe_content", side_effect=TranslationError("x")),
    ):
        assert translate_recipes.main(["--languages", "de"]) == 1
    assert translate_recipes.main(["--dry-run"]) == 0


# ---------------------------------------------------------------------------
# Mislabelled recipes (German dish name, English text — e.g. "Pilzparfait")
# ---------------------------------------------------------------------------


def _mislabel(tmp_db_path, uuid):
    """Simulate the bad state: labelled German, with an English 'translation' copy."""
    conn = sqlite3.connect(str(tmp_db_path))
    data = json.loads(
        conn.execute("SELECT recipe_json FROM recipes WHERE uuid = ?", (uuid,)).fetchone()[0]
    )
    data["inLanguage"] = "de"
    data["translations"] = {"en": {**GERMAN, "name": "copy"}}
    conn.execute("UPDATE recipes SET recipe_json = ? WHERE uuid = ?", (json.dumps(data), uuid))
    conn.commit()
    conn.close()


def test_detection_ignores_dish_name_when_text_exists():
    from api import translation as translation_mod

    seen = []
    provider = translation_mod.Provider(
        translate=lambda c, t: None, detect=lambda sample: seen.append(sample) or "en"
    )
    stored = {
        "name": "Pilzparfait",
        "description": "Ein Klassiker",
        "ingredients": [{"amount": "200 g", "name": "mushrooms"}],
        "instructions": [{"text": "Slice the mushrooms.", "ingredients": [0]}],
    }
    with patch.dict(translation_mod._PROVIDERS, {"openai": provider}):
        assert translation_mod.detect_recipe_language(stored) == "en"
    assert "Pilzparfait" not in seen[0] and "Klassiker" not in seen[0]
    assert "Slice the mushrooms." in seen[0]


def test_add_translation_corrects_label_when_already_in_target():
    from api.translation import add_translation

    stored = {
        "name": "Pilzparfait",
        "ingredients": [],
        "instructions": [],
        "inLanguage": "de",
        "translations": {"en": {"name": "copy"}},
    }
    with patch("api.translation.translate_recipe_content", return_value=(GERMAN, "en")):
        assert add_translation(stored, "en") is False
    assert stored["inLanguage"] == "en"
    assert "translations" not in stored  # the stale copy is gone


def test_redetect_fixes_mislabelled_recipe(legacy, tmp_db_path):
    _mislabel(tmp_db_path, legacy[0])
    with (
        patch("translate_recipes.detect_recipe_language", return_value="en"),
        patch("api.translation.translate_recipe_content", side_effect=_translated_into("x")),
    ):
        stats = translate_recipes.run(redetect=True, only_uuid=legacy[0])
    assert stats["corrected"] == 1 and stats["translations"] == 1
    stored = _stored(tmp_db_path, legacy[0])
    assert stored["inLanguage"] == "en"
    assert list(stored["translations"]) == ["de"]  # a real German version now
    assert stored["translations"]["de"]["name"] == "x-de"


def test_redetect_leaves_correct_labels_alone(legacy, tmp_db_path):
    with (
        patch("translate_recipes.detect_recipe_language", return_value="en"),
        patch("api.translation.translate_recipe_content", side_effect=_translated_into("x")),
    ):
        translate_recipes.run()
        before = _stored(tmp_db_path, legacy[0])
        stats = translate_recipes.run(redetect=True, detect_only=True)
    assert stats["corrected"] == 0
    assert _stored(tmp_db_path, legacy[0]) == before


def test_inspect_is_read_only(legacy, tmp_db_path, capsys):
    _mislabel(tmp_db_path, legacy[0])
    with (
        patch("translate_recipes.detect_recipe_language") as detect,
        patch("api.translation.translate_recipe_content") as translate,
    ):
        assert translate_recipes.main(["--inspect"]) == 0
    detect.assert_not_called()
    translate.assert_not_called()
    out = capsys.readouterr().out
    assert "base=de translations=en" in out
    assert "step 1:" in out

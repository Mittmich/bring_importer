"""Imports from several photos and from a PDF document."""

from types import SimpleNamespace
from unittest.mock import patch

from api import recipe_extraction
from api.recipe_extraction import MAX_IMAGES, _RecipeOutput

PDF = b"%PDF-1.4\n1 0 obj << >> endobj\ntrailer << >>\n%%EOF\n"


def _completion():
    out = _RecipeOutput.model_validate(
        {
            "title": "Tart",
            "description": "",
            "recipeYield": "8 servings",
            "ingredients": [{"amount": "250 g", "name": "flour"}],
            "instructions": [{"text": "Bake.", "ingredients": [0]}],
        }
    )
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(parsed=out))])


def test_several_photos_are_sent_together(client, auth_headers, mocked_openai):
    resp = client.post(
        "/recipes/parse", headers=auth_headers, data={"image": ["aGVsbG8=", "d29ybGQ="]}
    )
    assert resp.status_code == 200, resp.text
    assert mocked_openai["parse_image"].call_args.args[0] == ["aGVsbG8=", "d29ybGQ="]
    # A single photo is still passed as a plain string.
    client.post("/recipes/parse", headers=auth_headers, data={"image": "aGVsbG8="})
    assert mocked_openai["parse_image"].call_args.args[0] == "aGVsbG8="


def test_too_many_photos_rejected(client, auth_headers, mocked_openai):
    resp = client.post(
        "/recipes/parse", headers=auth_headers, data={"image": ["aGVsbG8="] * (MAX_IMAGES + 1)}
    )
    assert resp.status_code == 422
    mocked_openai["parse_image"].assert_not_called()


def test_multi_image_prompt_has_every_image():
    with patch.object(recipe_extraction, "_get_client") as get:
        parse = get.return_value.beta.chat.completions.parse
        parse.return_value = _completion()
        recipe = recipe_extraction.parse_recipe_with_openai(
            ["data:image/jpeg;base64,AAA", "BBB", "CCC"], "en"
        )
    assert recipe.title == "Tart"
    content = parse.call_args.kwargs["messages"][1]["content"]
    assert "3 images" in content[0]["text"]
    urls = [c["image_url"]["url"] for c in content[1:]]
    assert urls == [f"data:image/jpeg;base64,{x}" for x in ("AAA", "BBB", "CCC")]


def test_pdf_goes_to_the_model_as_a_file():
    with patch.object(recipe_extraction, "_get_client") as get:
        parse = get.return_value.beta.chat.completions.parse
        parse.return_value = _completion()
        recipe = recipe_extraction.parse_recipe_from_pdf(PDF, "tart.pdf", "de")
    assert recipe.inLanguage == "de"
    part = parse.call_args.kwargs["messages"][1]["content"][1]
    assert part["type"] == "file" and part["file"]["filename"] == "tart.pdf"
    assert part["file"]["file_data"].startswith("data:application/pdf;base64,JVBERi0")


def test_import_document(client, auth_headers):
    with patch.object(recipe_extraction, "_get_client") as get:
        get.return_value.beta.chat.completions.parse.return_value = _completion()
        resp = client.post(
            "/recipes/import-document",
            headers=auth_headers,
            files={"file": ("../../Lemon Tart.pdf", PDF, "application/pdf")},
            data={"note": " from grandma ", "language": "en"},
        )
    assert resp.status_code == 200, resp.text
    recipe = client.get(f"/recipes/{resp.json()['uuid']}.json", headers=auth_headers).json()
    assert recipe["name"] == "Tart"
    assert recipe["source"] == {"kind": "document", "value": "Lemon Tart.pdf"}
    assert recipe["note"] == "from grandma"


def test_import_document_rejects_non_pdf_and_large_files(client, auth_headers):
    with patch.object(recipe_extraction, "_get_client") as get:
        resp = client.post(
            "/recipes/import-document",
            headers=auth_headers,
            files={"file": ("x.pdf", b"<html>not a pdf</html>", "application/pdf")},
        )
        assert resp.status_code == 422
        with patch("api.routers.recipes.MAX_PDF_BYTES", 10):
            resp = client.post(
                "/recipes/import-document",
                headers=auth_headers,
                files={"file": ("x.pdf", PDF, "application/pdf")},
            )
        assert resp.status_code == 413
        get.assert_not_called()


def test_import_document_failure_and_auth(client, auth_headers):
    with patch.object(recipe_extraction, "_get_client", side_effect=RuntimeError("down")):
        resp = client.post(
            "/recipes/import-document",
            headers=auth_headers,
            files={"file": ("x.pdf", PDF, "application/pdf")},
        )
    assert resp.status_code == 500
    assert resp.json()["detail"] == "Could not read a recipe from this document"
    assert (
        client.post(
            "/recipes/import-document", files={"file": ("x.pdf", PDF, "application/pdf")}
        ).status_code
        == 401
    )

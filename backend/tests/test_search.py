"""Tests for fuzzy full-recipe search: the ``api.search`` scorer (unit) and the
``GET /recipes?q=`` endpoint that searches across all recipe components."""

from unittest.mock import patch

import pytest

from api.models import Ingredient, InstructionStep, Recipe
from api.search import match_score, recipe_haystack, tokenize

# ---------------------------------------------------------------------------
# Unit: haystack + scorer
# ---------------------------------------------------------------------------


def test_haystack_includes_all_components():
    rj = {
        "name": "Chocolate Cake",
        "description": "Rich and moist",
        "note": "Grandma's recipe",
        "ingredients": [{"amount": "100 g", "name": "cocoa"}, {"amount": "50 g", "name": "butter"}],
        "instructions": [{"text": "Melt the butter", "ingredients": [1]}],
    }
    hay = recipe_haystack(rj, ["Dessert"])
    for needle in ["chocolate", "moist", "grandma", "cocoa", "butter", "melt", "dessert"]:
        assert needle in hay


def test_haystack_supports_old_flat_format():
    rj = {
        "name": "Old Recipe",
        "recipeIngredient": ["2 eggs", "1 cup flour"],
        "recipeInstructions": ["Whisk eggs"],
    }
    hay = recipe_haystack(rj, [])
    assert "eggs" in hay and "flour" in hay and "whisk" in hay


def test_match_score_exact_substring():
    hay = recipe_haystack(
        {"name": "Pancakes", "ingredients": [{"amount": "", "name": "butter"}]}, []
    )
    assert match_score("butter", hay) > 0
    assert match_score("lettuce", hay) == 0


def test_match_score_is_fuzzy():
    hay = recipe_haystack({"name": "Chocolate Cake"}, [])
    assert match_score("choclate", hay) > 0  # transposition typo still matches


def test_match_score_requires_all_query_words():
    hay = recipe_haystack(
        {"name": "Pancakes", "ingredients": [{"amount": "2", "name": "eggs"}]}, []
    )
    assert match_score("eggs pancakes", hay) > 0
    assert match_score("eggs lettuce", hay) == 0  # AND: lettuce is absent


def test_tokenize_splits_and_lowercases():
    assert tokenize("2 Cups of Flour!") == ["2", "cups", "of", "flour"]


# ---------------------------------------------------------------------------
# Integration: GET /recipes?q=
# ---------------------------------------------------------------------------


def _store(client, auth_headers, recipe: Recipe) -> str:
    with patch("api.routers.recipes.parse_recipe_with_openai", return_value=recipe):
        resp = client.post("/recipes/parse", headers=auth_headers, data={"image": "aGVsbG8="})
    assert resp.status_code == 200
    return resp.json()["uuid"]


def _recipe(title: str, ingredients: list[tuple[str, str]]) -> Recipe:
    return Recipe(
        title=title,
        ingredients=[Ingredient(amount=a, name=n) for a, n in ingredients],
        instructions=[InstructionStep(text="Combine everything.", ingredients=[])],
        recipeYield="2 servings",
        description="",
    )


@pytest.fixture
def seeded(client, auth_headers):
    return {
        "pancakes": _store(
            client, auth_headers, _recipe("Pancakes", [("2", "eggs"), ("50 g", "butter")])
        ),
        "salad": _store(client, auth_headers, _recipe("Green Salad", [("1", "lettuce")])),
        "cake": _store(client, auth_headers, _recipe("Chocolate Cake", [("100 g", "cocoa")])),
    }


@pytest.mark.integration
def test_search_matches_ingredient_not_in_title(client, auth_headers, seeded):
    """'butter' is only an ingredient of Pancakes — search should still find it."""
    resp = client.get("/recipes", headers=auth_headers, params={"q": "butter"}).json()
    assert [i["uuid"] for i in resp["items"]] == [seeded["pancakes"]]
    assert resp["total"] == 1


@pytest.mark.integration
def test_search_is_fuzzy(client, auth_headers, seeded):
    resp = client.get("/recipes", headers=auth_headers, params={"q": "choclate"}).json()
    assert [i["uuid"] for i in resp["items"]] == [seeded["cake"]]


@pytest.mark.integration
def test_search_multi_word_is_and(client, auth_headers, seeded):
    resp = client.get("/recipes", headers=auth_headers, params={"q": "butter eggs"}).json()
    assert [i["uuid"] for i in resp["items"]] == [seeded["pancakes"]]


@pytest.mark.integration
def test_search_no_match_returns_empty(client, auth_headers, seeded):
    resp = client.get("/recipes", headers=auth_headers, params={"q": "zzzznope"}).json()
    assert resp["items"] == []
    assert resp["total"] == 0


@pytest.mark.integration
def test_search_paginates_ranked_results(client, auth_headers):
    # Three recipes all mention "butter"; search should page through all of them.
    for i in range(3):
        _store(client, auth_headers, _recipe(f"Bake {i}", [("10 g", "butter")]))
    p0 = client.get("/recipes", headers=auth_headers, params={"q": "butter", "limit": 2}).json()
    p1 = client.get(
        "/recipes", headers=auth_headers, params={"q": "butter", "limit": 2, "offset": 2}
    ).json()
    assert p0["total"] == 3
    assert len(p0["items"]) == 2 and len(p1["items"]) == 1
    assert len({i["uuid"] for i in p0["items"] + p1["items"]}) == 3

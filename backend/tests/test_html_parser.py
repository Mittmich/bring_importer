"""Unit tests for JSON-LD extraction helpers in ``api.recipe_extraction``.

Tests the pure ``_find_recipe_in_jsonld`` walker, the high-level
``extract_recipe_from_jsonld`` function (with LLM helpers mocked out),
and unit tests for the LLM helper functions themselves (with the OpenAI
client mocked).
"""

from unittest.mock import MagicMock, patch

import pytest

from api.models import Ingredient, InstructionStep
from api.recipe_extraction import (
    _find_recipe_in_jsonld,
    _flatten_instruction_texts,
    _map_ingredients_to_instructions,
    _parse_ingredient_strings,
    extract_recipe_from_html_text,
    extract_recipe_from_jsonld,
    parse_recipe_with_openai,
)

# ---------------------------------------------------------------------------
# _flatten_instruction_texts — handles strings, HowToStep, HowToSection nesting
# ---------------------------------------------------------------------------


def test_flatten_instructions_howto_section_nesting():
    """HowToSection wrappers (e.g. chefkoch.de) nest the real steps under
    itemListElement; the section name must not leak in as a step."""
    raw = [
        {
            "@type": "HowToSection",
            "name": "Zubereitung",
            "itemListElement": [
                {"@type": "HowToStep", "text": "Step one.", "name": "Step one."},
                {"@type": "HowToStep", "text": "Step two.", "name": "Step two."},
            ],
        }
    ]
    assert _flatten_instruction_texts(raw) == ["Step one.", "Step two."]


def test_flatten_instructions_mixed_strings_and_steps():
    raw = ["Plain step.", {"@type": "HowToStep", "text": "Dict step."}]
    assert _flatten_instruction_texts(raw) == ["Plain step.", "Dict step."]


def test_flatten_instructions_single_string():
    assert _flatten_instruction_texts("Just mix.") == ["Just mix."]


def test_flatten_instructions_empty():
    assert _flatten_instruction_texts(None) == []
    assert _flatten_instruction_texts([]) == []


# ---------------------------------------------------------------------------
# _find_recipe_in_jsonld — pure function, no LLM required
# ---------------------------------------------------------------------------

FLAT_RECIPE_OBJ = {
    "@context": "https://schema.org",
    "@type": "Recipe",
    "name": "Flat Recipe",
    "recipeIngredient": ["1 cup flour"],
    "recipeYield": "4 servings",
}


def test_find_recipe_in_flat_dict():
    result = _find_recipe_in_jsonld(FLAT_RECIPE_OBJ)
    assert result is not None
    assert result["name"] == "Flat Recipe"


def test_find_recipe_in_graph_wrapper():
    graph = {
        "@graph": [
            {"@type": "WebPage", "name": "Page"},
            {**FLAT_RECIPE_OBJ, "name": "Graph Recipe"},
        ]
    }
    result = _find_recipe_in_jsonld(graph)
    assert result is not None
    assert result["name"] == "Graph Recipe"


def test_find_recipe_in_multi_type_list():
    multi = {**FLAT_RECIPE_OBJ, "@type": ["Thing", "Recipe"], "name": "Multi-type"}
    result = _find_recipe_in_jsonld(multi)
    assert result is not None
    assert result["name"] == "Multi-type"


def test_find_recipe_in_list_of_dicts():
    lst = [{"@type": "WebSite"}, {**FLAT_RECIPE_OBJ, "name": "List Recipe"}]
    result = _find_recipe_in_jsonld(lst)
    assert result is not None
    assert result["name"] == "List Recipe"


def test_find_recipe_returns_none_when_absent():
    assert _find_recipe_in_jsonld({"@type": "WebSite", "name": "Not a Recipe"}) is None
    assert _find_recipe_in_jsonld([]) is None
    assert _find_recipe_in_jsonld({}) is None


# ---------------------------------------------------------------------------
# extract_recipe_from_jsonld — LLM helpers mocked
# ---------------------------------------------------------------------------

STUB_INGREDIENTS = [
    Ingredient(amount="1 cup", name="flour"),
    Ingredient(amount="2", name="eggs"),
]
STUB_STEPS = [
    InstructionStep(text="Mix ingredients.", ingredients=[0, 1]),
]


@pytest.fixture
def mock_llm_helpers():
    with (
        patch(
            "api.recipe_extraction._parse_ingredient_strings",
            return_value=STUB_INGREDIENTS,
        ),
        patch(
            "api.recipe_extraction._map_ingredients_to_instructions",
            return_value=STUB_STEPS,
        ),
    ):
        yield


def test_extract_recipe_from_jsonld_happy_path(mock_llm_helpers):
    jsonld = {
        "@context": "https://schema.org",
        "@type": "Recipe",
        "name": "JSON-LD Pancakes",
        "recipeIngredient": ["1 cup flour", "2 eggs"],
        "recipeInstructions": [{"@type": "HowToStep", "text": "Mix ingredients."}],
        "recipeYield": "4 servings",
        "description": "Quick and easy.",
    }
    recipe = extract_recipe_from_jsonld(jsonld)
    assert recipe is not None
    assert recipe.title == "JSON-LD Pancakes"
    assert recipe.recipeYield == "4 servings"
    assert recipe.description == "Quick and easy."
    assert recipe.ingredients == STUB_INGREDIENTS
    assert recipe.instructions == STUB_STEPS


def test_extract_recipe_from_jsonld_missing_name_uses_untitled(mock_llm_helpers):
    jsonld = {
        "@type": "Recipe",
        "recipeIngredient": ["flour"],
        "recipeYield": "2 servings",
    }
    recipe = extract_recipe_from_jsonld(jsonld)
    assert recipe is not None
    assert recipe.title == "Untitled Recipe"


def test_extract_recipe_from_jsonld_returns_none_for_non_recipe(mock_llm_helpers):
    assert extract_recipe_from_jsonld({"@type": "WebSite"}) is None


def test_extract_recipe_from_jsonld_handles_string_instructions(mock_llm_helpers):
    jsonld = {
        "@type": "Recipe",
        "name": "String Steps",
        "recipeIngredient": ["flour"],
        "recipeInstructions": "Just mix everything.",
    }
    recipe = extract_recipe_from_jsonld(jsonld)
    assert recipe is not None


def test_extract_recipe_from_jsonld_handles_yield_as_list(mock_llm_helpers):
    jsonld = {
        "@type": "Recipe",
        "name": "List Yield",
        "recipeIngredient": ["flour"],
        "recipeYield": ["4", "servings"],
    }
    recipe = extract_recipe_from_jsonld(jsonld)
    assert recipe is not None
    assert "4" in recipe.recipeYield


def test_extract_recipe_from_jsonld_handles_list_description(mock_llm_helpers):
    """description as a list of strings should be joined (line 293)."""
    jsonld = {
        "@type": "Recipe",
        "name": "List Desc",
        "recipeIngredient": ["flour"],
        "description": ["Line one.", "Line two."],
    }
    recipe = extract_recipe_from_jsonld(jsonld)
    assert recipe is not None
    assert recipe.description is not None
    assert "Line one." in recipe.description


def test_extract_recipe_from_jsonld_handles_string_ingredient(mock_llm_helpers):
    """recipeIngredient as a plain string should be wrapped in a list (line 298)."""
    jsonld = {
        "@type": "Recipe",
        "name": "Single Ingredient",
        "recipeIngredient": "flour",
    }
    recipe = extract_recipe_from_jsonld(jsonld)
    assert recipe is not None


def test_extract_recipe_from_jsonld_handles_string_steps_in_list(mock_llm_helpers):
    """Plain strings inside recipeInstructions list should be collected (lines 309-310)."""
    jsonld = {
        "@type": "Recipe",
        "name": "Plain Steps",
        "recipeIngredient": ["flour"],
        "recipeInstructions": ["Step one.", "", "Step three."],
    }
    recipe = extract_recipe_from_jsonld(jsonld)
    assert recipe is not None


# ---------------------------------------------------------------------------
# LLM helper functions — OpenAI client mocked
# ---------------------------------------------------------------------------


def _make_completion(parsed_value):
    """Return a minimal fake OpenAI completion with .choices[0].message.parsed."""
    msg = MagicMock()
    msg.parsed = parsed_value
    choice = MagicMock()
    choice.message = msg
    comp = MagicMock()
    comp.choices = [choice]
    return comp


@pytest.fixture
def mock_client():
    """Patch _get_client() to return a MagicMock OpenAI client."""
    with patch("api.recipe_extraction._get_client") as get_client:
        client = MagicMock()
        get_client.return_value = client
        yield client


def test_parse_ingredient_strings_empty_list():
    assert _parse_ingredient_strings([]) == []


def test_parse_ingredient_strings_calls_openai(mock_client):
    expected = [Ingredient(amount="1 cup", name="flour")]
    parsed = MagicMock()
    parsed.ingredients = expected
    mock_client.beta.chat.completions.parse.return_value = _make_completion(parsed)

    result = _parse_ingredient_strings(["1 cup flour"])
    assert result == expected
    mock_client.beta.chat.completions.parse.assert_called_once()


def test_parse_ingredient_strings_returns_fallback_when_parsed_is_none(mock_client):
    mock_client.beta.chat.completions.parse.return_value = _make_completion(None)
    result = _parse_ingredient_strings(["1 cup flour"])
    assert len(result) == 1
    assert result[0].name == "1 cup flour"
    assert result[0].amount == ""


def test_map_ingredients_to_instructions_empty_steps():
    ingredients = [Ingredient(amount="1 cup", name="flour")]
    assert _map_ingredients_to_instructions(ingredients, []) == []


def test_map_ingredients_to_instructions_calls_openai(mock_client):
    ingredients = [Ingredient(amount="1 cup", name="flour")]
    expected = [InstructionStep(text="Mix flour.", ingredients=[0])]
    parsed = MagicMock()
    parsed.steps = expected
    mock_client.beta.chat.completions.parse.return_value = _make_completion(parsed)

    result = _map_ingredients_to_instructions(ingredients, ["Mix flour."])
    assert result[0].text == "Mix flour."
    assert result[0].ingredients == [0]


def test_map_ingredients_to_instructions_fallback_when_parsed_is_none(mock_client):
    ingredients = [Ingredient(amount="1 cup", name="flour")]
    mock_client.beta.chat.completions.parse.return_value = _make_completion(None)
    result = _map_ingredients_to_instructions(ingredients, ["Mix."])
    assert len(result) == 1
    assert result[0].text == "Mix."
    assert result[0].ingredients == []


def test_parse_recipe_with_openai_calls_openai(mock_client):
    from api.models import Recipe

    out = MagicMock()
    out.title = "Image Recipe"
    out.recipeYield = "2 servings"
    out.description = "From a photo."
    out.ingredients = [Ingredient(amount="1 cup", name="flour")]
    out.instructions = [InstructionStep(text="Mix.", ingredients=[0])]
    mock_client.beta.chat.completions.parse.return_value = _make_completion(out)

    result = parse_recipe_with_openai("aGVsbG8=")
    assert isinstance(result, Recipe)
    assert result.title == "Image Recipe"


def test_extract_recipe_from_html_text_calls_openai(mock_client):
    from api.models import Recipe

    out = MagicMock()
    out.title = "HTML Recipe"
    out.recipeYield = "4 servings"
    out.description = "From HTML."
    out.ingredients = [Ingredient(amount="", name="salt")]
    out.instructions = [InstructionStep(text="Season.", ingredients=[0])]
    mock_client.beta.chat.completions.parse.return_value = _make_completion(out)

    result = extract_recipe_from_html_text("<html><body>recipe</body></html>")
    assert isinstance(result, Recipe)
    assert result.title == "HTML Recipe"

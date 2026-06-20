"""Recipe extraction: OpenAI structured-output calls + JSON-LD parser.

Entry points:

  - ``parse_recipe_with_openai(image_base64)``: calls OpenAI vision with
    structured output to extract a ``Recipe`` directly from an image.

  - ``extract_recipe_from_jsonld(jsonld_obj)``: converts a parsed
    ``application/ld+json`` Recipe object into the new structured ``Recipe``
    model, using two helper LLM calls (_parse_ingredient_strings and
    _map_ingredients_to_instructions).

  - ``extract_recipe_from_html_text(text)``: strips a raw HTML body and sends
    it to OpenAI with structured output to extract a ``Recipe``.

  - ``_parse_ingredient_strings(strings)``: splits flat ingredient strings
    ("2 cups flour") into ``Ingredient`` objects. Shared by JSON-LD extraction
    and the migration script.

  - ``_map_ingredients_to_instructions(ingredients, instruction_texts)``: given
    the ingredient list and plain instruction texts, asks the LLM to return
    ``InstructionStep`` objects with ingredient-index references. Shared by
    JSON-LD extraction and the migration script.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from bs4 import BeautifulSoup
from fastapi import HTTPException
from openai import OpenAI
from pydantic import BaseModel

from api.config import OPENAI_API_KEY
from api.models import Ingredient, InstructionStep, Recipe

# User-Agent sent when we fetch a page server-side. A real browser string
# avoids getting soft-banned by sites that reject default python user agents.
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

# Cap the HTML body sent to OpenAI for the text fallback.
# 30K chars is ~7.5K tokens; enough to cover ~99% of real recipe pages.
MAX_HTML_CHARS_FOR_OPENAI = 30_000

# Lazy singleton — avoids crashing at import time when OPENAI_API_KEY is absent
# (e.g. during the health-check startup path or in tests).
_client: Optional[OpenAI] = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(api_key=OPENAI_API_KEY)
    return _client


# ---------------------------------------------------------------------------
# Intermediate Pydantic model for structured output (image + text extraction)
# ---------------------------------------------------------------------------


class _RecipeOutput(BaseModel):
    """Schema returned by OpenAI for image and HTML-text extraction.

    Ingredients include indices in instructions so the LLM produces the
    full mapping in a single call.
    """

    title: str
    recipeYield: str
    description: str
    ingredients: List[Ingredient]
    instructions: List[InstructionStep]


# ---------------------------------------------------------------------------
# Public helpers shared with the migration script
# ---------------------------------------------------------------------------


def _parse_ingredient_strings(strings: List[str]) -> List[Ingredient]:
    """Split flat ingredient strings into ``Ingredient`` objects.

    E.g. "2 cups flour, sifted" → ``Ingredient(amount="2 cups", name="flour, sifted")``.
    Uses ``gpt-5.4-nano`` with structured output.
    """
    if not strings:
        return []

    class _IngredientList(BaseModel):
        ingredients: List[Ingredient]

    numbered = "\n".join(f"{i}. {s}" for i, s in enumerate(strings))
    completion = _get_client().beta.chat.completions.parse(
        model="gpt-5.4-nano",
        messages=[
            {
                "role": "system",
                "content": (
                    "You split recipe ingredient strings into amount and name. "
                    "amount is the quantity + unit (e.g. '2 cups', '200 g', '1 tbsp'), "
                    "name is everything else (e.g. 'flour', 'eggs, beaten', 'salt to taste'). "
                    "If there is no quantity, leave amount as an empty string."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Split each of these {len(strings)} ingredient strings into amount and name, "
                    f"preserving order:\n{numbered}"
                ),
            },
        ],
        response_format=_IngredientList,
    )
    result = completion.choices[0].message.parsed
    if result is None:
        return [Ingredient(amount="", name=s) for s in strings]
    return result.ingredients


def _map_ingredients_to_instructions(
    ingredients: List[Ingredient],
    instruction_texts: List[str],
) -> List[InstructionStep]:
    """Return ``InstructionStep`` objects with ingredient-index references.

    For each instruction step, determines which ingredient indices (0-based)
    from the ingredient list are used in that step. Uses ``gpt-5.4-nano``
    with structured output.
    """
    if not instruction_texts:
        return []

    class _StepList(BaseModel):
        steps: List[InstructionStep]

    ing_list = "\n".join(
        f"{i}. {ing.amount} {ing.name}".strip() for i, ing in enumerate(ingredients)
    )
    step_list = "\n".join(f"{i}. {t}" for i, t in enumerate(instruction_texts))

    completion = _get_client().beta.chat.completions.parse(
        model="gpt-5.4-nano",
        messages=[
            {
                "role": "system",
                "content": (
                    "You map recipe instruction steps to the ingredient indices they use. "
                    "Return one step per input step, preserving order. "
                    "The 'text' field must be the original step text verbatim. "
                    "The 'ingredients' field is the list of 0-based ingredient indices "
                    "needed for that step. Use [] if a step needs no specific ingredients."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Ingredients (indexed 0–{len(ingredients) - 1}):\n{ing_list}\n\n"
                    f"Instruction steps (map each to its ingredient indices):\n{step_list}"
                ),
            },
        ],
        response_format=_StepList,
    )
    result = completion.choices[0].message.parsed
    if result is None:
        return [InstructionStep(text=t, ingredients=[]) for t in instruction_texts]
    # Ensure the step texts are preserved (LLM might paraphrase)
    steps = result.steps
    for i, text in enumerate(instruction_texts):
        if i < len(steps):
            steps[i].text = text
        else:
            steps.append(InstructionStep(text=text, ingredients=[]))
    return steps[: len(instruction_texts)]


# ---------------------------------------------------------------------------
# Image extraction
# ---------------------------------------------------------------------------


def parse_recipe_with_openai(image_base64: str) -> Recipe:
    """Extract a structured recipe from a base64-encoded image."""
    if "base64," in image_base64:
        image_base64 = image_base64.split("base64,")[1]

    completion = _get_client().beta.chat.completions.parse(
        model="gpt-5.4-nano",
        messages=[
            {
                "role": "system",
                "content": (
                    "You extract recipes from images and return structured data. "
                    "Ingredients are individual shopping-list items with amounts. "
                    "Instructions are ordered cooking steps. "
                    "In each instruction step, list the 0-based indices of ingredients "
                    "from the ingredient list that are used in that step."
                ),
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": (
                            "Extract the recipe from this image. "
                            "Return all ingredients with their amounts and the ingredient's name "
                            "separately. For each instruction step, include the indices of the "
                            "ingredients used."
                        ),
                    },
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{image_base64}"},
                    },
                ],
            },
        ],
        response_format=_RecipeOutput,
        max_completion_tokens=2000,
    )

    out = completion.choices[0].message.parsed
    if out is None:
        raise HTTPException(status_code=500, detail="OpenAI returned no structured content")

    return Recipe(
        title=out.title,
        ingredients=out.ingredients,
        instructions=out.instructions,
        recipeYield=out.recipeYield or "4 servings",
        description=out.description,
        datePublished=datetime.now().strftime("%Y-%m-%d"),
    )


# ---------------------------------------------------------------------------
# URL import helpers
# ---------------------------------------------------------------------------


def _find_recipe_in_jsonld(obj: Any) -> Optional[Dict[str, Any]]:
    """Walk an ``application/ld+json`` payload and return the Recipe object.

    Handles three real-world shapes:
      1. ``{"@type": "Recipe", ...}``
      2. ``{"@type": ["Thing", "Recipe"], ...}`` (multi-type)
      3. ``{"@graph": [{"@type": "Recipe", ...}, ...]}`` (graph wrapper)
    """
    if isinstance(obj, dict):
        t = obj.get("@type")
        if t == "Recipe" or (isinstance(t, list) and "Recipe" in t):
            return obj
        graph = obj.get("@graph")
        if isinstance(graph, list):
            for inner in graph:
                found = _find_recipe_in_jsonld(inner)
                if found is not None:
                    return found
    elif isinstance(obj, list):
        for item in obj:
            found = _find_recipe_in_jsonld(item)
            if found is not None:
                return found
    return None


def extract_recipe_from_jsonld(jsonld_obj: Any) -> Optional[Recipe]:
    """Convert a parsed JSON-LD object into a ``Recipe``, or ``None``.

    Returns ``None`` if no Recipe-shaped object is present. The caller
    is expected to fall back to OpenAI text extraction in that case.

    After extracting the flat ingredient/instruction strings from JSON-LD,
    makes two LLM calls to split ingredients into {amount, name} and to
    map ingredient indices onto each instruction step.
    """
    found = _find_recipe_in_jsonld(jsonld_obj)
    if found is None:
        return None

    name = found.get("name") or "Untitled Recipe"
    yield_ = found.get("recipeYield") or "4 servings"
    if isinstance(yield_, list):
        yield_ = ", ".join(str(y) for y in yield_)
    description = found.get("description") or ""
    if isinstance(description, list):
        description = " ".join(str(d) for d in description)

    # Flat ingredient strings from JSON-LD
    raw_ingredients = found.get("recipeIngredient") or []
    if isinstance(raw_ingredients, str):
        raw_ingredients = [raw_ingredients]

    # Flat instruction strings from JSON-LD
    raw_instr = found.get("recipeInstructions") or []
    instruction_texts: List[str] = []
    if isinstance(raw_instr, str):
        if raw_instr:
            instruction_texts = [raw_instr]
    elif isinstance(raw_instr, list):
        for step in raw_instr:
            if isinstance(step, str):
                if step:
                    instruction_texts.append(step)
            elif isinstance(step, dict):
                text = step.get("text") or step.get("name") or ""
                if text:
                    instruction_texts.append(text)

    # LLM calls to produce structured data
    ingredients = _parse_ingredient_strings(raw_ingredients)
    instructions = _map_ingredients_to_instructions(ingredients, instruction_texts)

    return Recipe(
        title=name,
        ingredients=ingredients,
        instructions=instructions,
        recipeYield=str(yield_),
        description=description,
        datePublished=datetime.now().strftime("%Y-%m-%d"),
    )


def extract_recipe_from_html_text(html: str, source_url: str = "") -> Recipe:
    """OpenAI structured-output extraction fallback for URL import.

    Strips the HTML to a reasonable size, then calls OpenAI with structured
    output to extract a fully-mapped ``Recipe`` in a single call.
    """
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "iframe"]):
        tag.decompose()
    cleaned = str(soup)
    if len(cleaned) > MAX_HTML_CHARS_FOR_OPENAI:
        cleaned = cleaned[:MAX_HTML_CHARS_FOR_OPENAI]

    completion = _get_client().beta.chat.completions.parse(
        model="gpt-5.4-nano",
        messages=[
            {
                "role": "system",
                "content": (
                    "You extract recipes from webpage HTML and return structured data. "
                    "Ingredients are individual shopping-list items with amounts. "
                    "Instructions are ordered cooking steps. "
                    "In each instruction step, list the 0-based indices of ingredients "
                    "from the ingredient list that are used in that step."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Extract the recipe from the following page"
                    f"{f' (source: {source_url})' if source_url else ''}. "
                    "Return all ingredients with amount and name separated. "
                    "For each instruction step include the indices of ingredients used.\n\n"
                    f"{cleaned}"
                ),
            },
        ],
        response_format=_RecipeOutput,
        max_tokens=2000,
    )

    out = completion.choices[0].message.parsed
    if out is None:
        raise HTTPException(status_code=500, detail="OpenAI returned no structured content")

    return Recipe(
        title=out.title,
        ingredients=out.ingredients,
        instructions=out.instructions,
        recipeYield=out.recipeYield or "4 servings",
        description=out.description,
        datePublished=datetime.now().strftime("%Y-%m-%d"),
    )

"""Recipe extraction: OpenAI HTTP call + schema.org/Recipe HTML parser.

Two entry points:

  - ``_extract_recipe_from_html(html)``: pure function, parses a
    ``schema.org/Recipe`` HTML string into a ``Recipe`` model. Unit-tested
    in ``backend/tests/test_html_parser.py``.
  - ``parse_recipe_with_openai(image_base64)``: HTTP wrapper that calls
    OpenAI's chat completions endpoint and delegates the response to
    ``_extract_recipe_from_html``.

URL import (step 5) adds two more:

  - ``extract_recipe_from_jsonld(jsonld)``: turns a parsed
    ``application/ld+json`` object whose ``@type`` is ``Recipe`` into a
    ``Recipe``. Tolerant of the @graph / array shapes real-world
    schema.org emits.
  - ``extract_recipe_from_html_text(text)``: takes a raw HTML body,
    strips it to a reasonable size, and calls OpenAI with a text-only
    prompt that asks for the same schema.org/Recipe HTML it asks for
    in the image flow. Returns a ``Recipe``.

The two-function split was introduced by the tests/CI plan's step 4 to
make the HTML parser testable without HTTP mocks. This package split
(step 1 of the comprehensive plan) inherits the same shape.
"""

import re
from datetime import datetime
from typing import Any, Dict, Optional

import requests
from bs4 import BeautifulSoup
from fastapi import HTTPException

from api.config import OPENAI_API_KEY
from api.models import Recipe

# User-Agent sent when we fetch a page server-side (step 5). A real
# browser string avoids getting soft-banned by sites that reject
# default urllib/python-requests user agents.
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

# Cap the HTML body sent to OpenAI for the text fallback (step 5).
# 30K chars is ~7.5K tokens; enough to cover ~99% of real recipe
# pages after the chrome/ads are stripped.
MAX_HTML_CHARS_FOR_OPENAI = 30_000


def _extract_recipe_from_html(html: str) -> Recipe:
    """Parse a schema.org/Recipe HTML string into a ``Recipe`` model.

    Tolerant of three real-world shapes OpenAI's chat completions returns:
      1. Clean ``schema.org/Recipe`` HTML.
      2. Markdown-fenced HTML (`` ```html ... ``` ``).
      3. Plain markdown-fenced HTML with no language (`` ``` ... ``` ``).

    Falls back to ``<ul><li>`` items if no ``recipeIngredient`` itemprops are
    present, and to the entire ``soup`` if no ``itemtype`` wrapper is found.
    """
    html_content = html

    # Clean up the HTML content - remove markdown code blocks if present
    if "```html" in html_content:
        html_match = re.search(r"```html\s*(.*?)\s*```", html_content, re.DOTALL)
        if html_match:
            html_content = html_match.group(1)
    elif "```" in html_content:
        html_match = re.search(r"```\s*(.*?)\s*```", html_content, re.DOTALL)
        if html_match:
            html_content = html_match.group(1)

    soup = BeautifulSoup(html_content, "html.parser")

    # Find recipe element
    recipe_element = soup.find(itemtype=re.compile(r"schema.org/Recipe"))

    if not recipe_element:
        # Try alternate format
        recipe_element = soup.find(attrs={"itemtype": re.compile(r"schema.org/Recipe")})

    if not recipe_element:
        # If still not found, use the entire soup
        recipe_element = soup

    # Extract title
    title_element = recipe_element.find(attrs={"itemprop": "name"})
    title = title_element.text.strip() if title_element else "Untitled Recipe"

    # Extract ingredients
    ingredient_elements = recipe_element.find_all(attrs={"itemprop": "recipeIngredient"})
    ingredients = [ing.text.strip() for ing in ingredient_elements]

    # If no specific ingredients found, look for list items
    ul_element = recipe_element.find("ul")
    if not ingredients and ul_element is not None:
        ingredients = [li.text.strip() for li in ul_element.find_all("li")]

    # Extract yield
    yield_element = recipe_element.find(attrs={"itemprop": "recipeYield"})
    recipe_yield = yield_element.text.strip() if yield_element else "4 servings"

    # Extract description
    description_element = recipe_element.find(attrs={"itemprop": "description"})
    description = description_element.text.strip() if description_element else ""

    # Extract instruction steps.
    # Prefer elements tagged itemprop="recipeInstructions"; fall back to <ol><li>.
    instruction_elements = recipe_element.find_all(attrs={"itemprop": "recipeInstructions"})
    instructions: list = []
    for el in instruction_elements:
        sub_steps = el.find_all("li")
        if sub_steps:
            instructions.extend(
                li.get_text(" ", strip=True) for li in sub_steps if li.get_text(strip=True)
            )
        else:
            text = el.get_text(" ", strip=True)
            if text:
                instructions.append(text)
    if not instructions:
        ol = recipe_element.find("ol")
        if ol:
            instructions = [
                li.get_text(" ", strip=True) for li in ol.find_all("li") if li.get_text(strip=True)
            ]

    return Recipe(
        title=title,
        recipeIngredient=ingredients,
        recipeInstructions=instructions or None,
        recipeYield=recipe_yield,
        description=description,
        datePublished=datetime.now().strftime("%Y-%m-%d"),
        html_content=str(soup),
    )


def parse_recipe_with_openai(image_base64: str) -> Recipe:
    url = "https://api.openai.com/v1/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {OPENAI_API_KEY}",
    }

    # Ensure base64 is properly formatted
    if "base64," in image_base64:
        image_base64 = image_base64.split("base64,")[1]

    payload = {
        "model": "gpt-5.4-nano",
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a helpful assistant that extracts recipe information from images "
                    "and returns valid HTML with schema.org/Recipe markup. Follow these rules strictly:\n"
                    "- Ingredients (individual items with amounts) must each appear in their own element "
                    'with itemprop="recipeIngredient". One ingredient per element.\n'
                    "- Cooking steps (what to do, in order) must each appear in their own element "
                    'with itemprop="recipeInstructions". One step per element.\n'
                    "- Never mix ingredients and instructions — they are always distinct sections. "
                    "Ingredients are a shopping list; instructions are numbered cooking actions."
                ),
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": (
                            "Extract the recipe information from this image. "
                            "Return valid HTML with proper schema.org/Recipe markup — "
                            "include itemscope, itemtype, and itemprop attributes. "
                            "It is vital that:\n"
                            '1. Every ingredient has its own element with itemprop="recipeIngredient" '
                            '(e.g. <li itemprop="recipeIngredient">200g flour</li>).\n'
                            '2. Every cooking step has its own element with itemprop="recipeInstructions" '
                            '(e.g. <li itemprop="recipeInstructions">Mix flour and water until smooth.</li>).\n'
                            "3. The two sections are kept completely separate — "
                            "ingredients list shopping items, instructions list cooking actions.\n"
                            "Do not include JSON blocks in your response, only return valid HTML."
                        ),
                    },
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{image_base64}"},
                    },
                ],
            },
        ],
        "max_tokens": 2000,
    }

    response = requests.post(url, headers=headers, json=payload)
    if response.status_code != 200:
        raise HTTPException(status_code=500, detail=f"OpenAI API error: {response.text}")

    result = response.json()
    html_content = result["choices"][0]["message"]["content"]

    try:
        return _extract_recipe_from_html(html_content)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to parse recipe: {str(e)}") from e


# ---------------------------------------------------------------------------
# URL import helpers (step 5)
# ---------------------------------------------------------------------------


def _find_recipe_in_jsonld(obj: Any) -> Optional[Dict[str, Any]]:
    """Walk an ``application/ld+json`` payload and return the Recipe object.

    Handles three real-world shapes:

      1. ``{"@type": "Recipe", ...}`` (most common)
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
    """
    found = _find_recipe_in_jsonld(jsonld_obj)
    if found is None:
        return None

    name = found.get("name") or "Untitled Recipe"
    ingredients = found.get("recipeIngredient") or []
    if isinstance(ingredients, str):
        ingredients = [ingredients]
    yield_ = found.get("recipeYield") or "4 servings"
    if isinstance(yield_, list):
        yield_ = ", ".join(str(y) for y in yield_)
    description = found.get("description") or ""
    if isinstance(description, list):
        description = " ".join(str(d) for d in description)

    # recipeInstructions can be a string, list of strings, or list of HowToStep dicts.
    raw_instr = found.get("recipeInstructions") or []
    instructions: list = []
    if isinstance(raw_instr, str):
        if raw_instr:
            instructions = [raw_instr]
    elif isinstance(raw_instr, list):
        for step in raw_instr:
            if isinstance(step, str):
                if step:
                    instructions.append(step)
            elif isinstance(step, dict):
                text = step.get("text") or step.get("name") or ""
                if text:
                    instructions.append(text)

    return Recipe(
        title=name,
        recipeIngredient=ingredients,
        recipeInstructions=instructions or None,
        recipeYield=str(yield_),
        description=description,
        datePublished=datetime.now().strftime("%Y-%m-%d"),
        html_content=None,  # URL imports don't have the original OpenAI HTML
    )


def extract_recipe_from_html_text(html: str, source_url: str = "") -> Recipe:
    """OpenAI text-extraction fallback for URL import.

    Strips the HTML to a reasonable size, sends the cleaned body to
    OpenAI with the same schema.org/Recipe prompt used by the image
    flow, and delegates the response to ``_extract_recipe_from_html``.
    """
    # Cheap chrome-strip: drop script/style, then keep just the visible
    # text. We keep tags so OpenAI sees some structural cues (itemtype,
    # itemprop) where the page exposes them.
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "iframe"]):
        tag.decompose()
    cleaned = str(soup)
    if len(cleaned) > MAX_HTML_CHARS_FOR_OPENAI:
        cleaned = cleaned[:MAX_HTML_CHARS_FOR_OPENAI]

    url = "https://api.openai.com/v1/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {OPENAI_API_KEY}",
    }
    payload = {
        "model": "gpt-5-mini",
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a helpful assistant that extracts recipe information "
                    "from webpage HTML. The most important aspect of the recipe is "
                    "the ingredients, which must be included in the recipeIngredient "
                    "itemprop. Return a valid HTML with proper schema.org/Recipe "
                    "markup. Do not include JSON blocks, only return valid HTML."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Extract the recipe from the following page"
                    f"{f' (source: {source_url})' if source_url else ''}. "
                    "Return a valid HTML with proper schema.org/Recipe markup, including "
                    "itemscope, itemtype, and itemprop attributes. It is vital that all "
                    "ingredients individually receive the recipeIngredient itemprop.\n\n"
                    f"{cleaned}"
                ),
            },
        ],
        "max_tokens": 2000,
    }
    response = requests.post(url, headers=headers, json=payload)
    if response.status_code != 200:
        raise HTTPException(status_code=500, detail=f"OpenAI API error: {response.text}")
    result = response.json()
    html_content = result["choices"][0]["message"]["content"]
    return _extract_recipe_from_html(html_content)

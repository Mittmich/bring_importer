"""Unit tests for ``api._extract_recipe_from_html``.

These tests cover the three real-world shapes OpenAI's chat completions
returns, plus the fallback paths the helper implements (missing itemtype,
missing ingredients, missing yield).
"""

import re

import api

# ---------------------------------------------------------------------------
# 1. Clean schema.org/Recipe HTML
# ---------------------------------------------------------------------------


def test_clean_schema_recipe_html_extracts_all_fields():
    html = """\
<div itemscope itemtype="https://schema.org/Recipe">
  <h1 itemprop="name">Test Pancakes</h1>
  <span itemprop="recipeYield">4 servings</span>
  <p itemprop="description">Light and fluffy.</p>
  <ul>
    <li itemprop="recipeIngredient">1 cup flour</li>
    <li itemprop="recipeIngredient">2 eggs</li>
    <li itemprop="recipeIngredient">1 cup milk</li>
  </ul>
</div>
"""
    r = api._extract_recipe_from_html(html)

    assert r.title == "Test Pancakes"
    assert r.recipeIngredient == ["1 cup flour", "2 eggs", "1 cup milk"]
    assert r.recipeYield == "4 servings"
    assert r.description == "Light and fluffy."
    # default datePublished is today's date as YYYY-MM-DD
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", r.datePublished)
    # html_content is the rendered soup, non-empty
    assert "Test Pancakes" in r.html_content


def test_clean_schema_recipe_html_missing_name_uses_untitled():
    html = """\
<div itemscope itemtype="https://schema.org/Recipe">
  <span itemprop="recipeYield">4 servings</span>
  <ul>
    <li itemprop="recipeIngredient">flour</li>
  </ul>
</div>
"""
    r = api._extract_recipe_from_html(html)
    assert r.title == "Untitled Recipe"


def test_clean_schema_recipe_html_missing_description_is_empty_string():
    html = """\
<div itemscope itemtype="https://schema.org/Recipe">
  <h1 itemprop="name">Bread</h1>
  <ul>
    <li itemprop="recipeIngredient">flour</li>
  </ul>
</div>
"""
    r = api._extract_recipe_from_html(html)
    assert r.description == ""


# ---------------------------------------------------------------------------
# 2. Markdown-fenced ```html ... ```
# ---------------------------------------------------------------------------


def test_html_fenced_code_block_is_stripped():
    raw = (
        "```html\n"
        '<div itemscope itemtype="https://schema.org/Recipe">\n'
        '  <h1 itemprop="name">Fenced Recipe</h1>\n'
        "  <ul>\n"
        '    <li itemprop="recipeIngredient">sugar</li>\n'
        "  </ul>\n"
        "</div>\n"
        "```\n"
    )
    r = api._extract_recipe_from_html(raw)
    assert r.title == "Fenced Recipe"
    assert r.recipeIngredient == ["sugar"]


# ---------------------------------------------------------------------------
# 3. Plain ``` ... ``` (no language)
# ---------------------------------------------------------------------------


def test_plain_fenced_code_block_is_stripped():
    raw = (
        "```\n"
        '<div itemscope itemtype="https://schema.org/Recipe">\n'
        '  <h1 itemprop="name">Plain Fence</h1>\n'
        "  <ul>\n"
        '    <li itemprop="recipeIngredient">salt</li>\n'
        "  </ul>\n"
        "</div>\n"
        "```\n"
    )
    r = api._extract_recipe_from_html(raw)
    assert r.title == "Plain Fence"
    assert r.recipeIngredient == ["salt"]


# ---------------------------------------------------------------------------
# 4. Missing recipeIngredient — falls back to <ul><li>
# ---------------------------------------------------------------------------


def test_missing_recipe_ingredient_falls_back_to_li_items():
    html = """\
<div itemscope itemtype="https://schema.org/Recipe">
  <h1 itemprop="name">Fallback Recipe</h1>
  <ul>
    <li>first ingredient</li>
    <li>second ingredient</li>
  </ul>
</div>
"""
    r = api._extract_recipe_from_html(html)
    assert r.recipeIngredient == ["first ingredient", "second ingredient"]


def test_no_ul_no_ingredients_yields_empty_list():
    html = """\
<div itemscope itemtype="https://schema.org/Recipe">
  <h1 itemprop="name">No List</h1>
  <p>Just text, no list.</p>
</div>
"""
    r = api._extract_recipe_from_html(html)
    assert r.recipeIngredient == []


# ---------------------------------------------------------------------------
# 5. Missing recipeYield — defaults to "4 servings"
# ---------------------------------------------------------------------------


def test_missing_recipe_yield_defaults_to_4_servings():
    html = """\
<div itemscope itemtype="https://schema.org/Recipe">
  <h1 itemprop="name">No Yield</h1>
  <ul>
    <li itemprop="recipeIngredient">flour</li>
  </ul>
</div>
"""
    r = api._extract_recipe_from_html(html)
    assert r.recipeYield == "4 servings"


# ---------------------------------------------------------------------------
# 6. No itemtype at all — falls back to entire soup
# ---------------------------------------------------------------------------


def test_no_itemtype_uses_entire_soup():
    html = """\
<html>
<body>
  <h1 itemprop="name">Soup-Wide Recipe</h1>
  <ul>
    <li itemprop="recipeIngredient">broth</li>
    <li itemprop="recipeIngredient">noodles</li>
  </ul>
</body>
</html>
"""
    r = api._extract_recipe_from_html(html)
    assert r.title == "Soup-Wide Recipe"
    assert r.recipeIngredient == ["broth", "noodles"]


# ---------------------------------------------------------------------------
# Alternate itemtype lookup (attrs={"itemtype": ...}) — same as itemtype= kwarg
# ---------------------------------------------------------------------------


def test_itemtype_as_attribute_only_form_also_found():
    """Some serializations emit itemtype only as an attribute string. Both
    lookup styles should work; the helper tries both."""
    html = """\
<div itemscope itemtype="http://schema.org/Recipe">
  <h1 itemprop="name">Attr-Only Recipe</h1>
  <ul>
    <li itemprop="recipeIngredient">pepper</li>
  </ul>
</div>
"""
    r = api._extract_recipe_from_html(html)
    assert r.title == "Attr-Only Recipe"
    assert r.recipeIngredient == ["pepper"]

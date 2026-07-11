"""Fuzzy, full-recipe search used by ``GET /recipes?q=...``.

The recipe list can be searched across *all* of a recipe's text — title,
description, note, ingredient names/amounts, instruction steps, and tag names —
not just the title, so a query like "butter" finds recipes that merely use it.
Matching is typo-tolerant (fuzzy) so "choclate" still finds "chocolate".

Search runs in the application layer over the user's recipes rather than in SQL:
at this app's scale (a personal collection) scanning the rows is cheap, and it
keeps ranking logic in one testable place without an FTS index to maintain.
"""

import re
from typing import Any, Dict, List

from rapidfuzz import fuzz

_WORD_RE = re.compile(r"[a-z0-9]+")

# A query word must reach this fuzzy ratio (0..100) against some word in the
# recipe to count as a match. High enough to tolerate a typo or two without
# matching unrelated words.
FUZZY_THRESHOLD = 80


def tokenize(text: str) -> List[str]:
    """Lowercase word tokens (alphanumeric runs) of ``text``."""
    return _WORD_RE.findall(text.lower())


def recipe_haystack(recipe_json: Dict[str, Any], tag_names: List[str]) -> str:
    """Flatten every searchable part of a recipe into one lowercased string.

    Handles both the structured format (``ingredients``/``instructions`` as
    lists of dicts) and the older flat format (``recipeIngredient`` /
    ``recipeInstructions`` as string lists).
    """
    parts: List[str] = [
        recipe_json.get("name") or "",
        recipe_json.get("description") or "",
        recipe_json.get("note") or "",
    ]

    for ing in recipe_json.get("ingredients") or []:
        if isinstance(ing, dict):
            parts.append(f"{ing.get('amount', '')} {ing.get('name', '')}")
        else:
            parts.append(str(ing))

    for step in recipe_json.get("instructions") or []:
        if isinstance(step, dict):
            parts.append(step.get("text", ""))
        else:
            parts.append(str(step))

    # Old flat format.
    for key in ("recipeIngredient", "recipeInstructions"):
        value = recipe_json.get(key)
        if isinstance(value, list):
            parts.extend(item if isinstance(item, str) else str(item) for item in value)

    parts.extend(tag_names)
    return " ".join(parts).lower()


def match_score(query: str, haystack: str) -> float:
    """Score ``query`` against a recipe ``haystack``; 0 means "no match".

    Semantics: every word in the query must match the recipe (AND), either as a
    substring (covers "butter" inside "buttermilk") or via a fuzzy ratio above
    ``FUZZY_THRESHOLD`` against some word in the recipe. The returned score is
    the mean per-word score, so exact and more-complete matches rank higher.
    """
    q_tokens = tokenize(query)
    if not q_tokens:
        return 0.0

    haystack_tokens = set(tokenize(haystack))
    total = 0.0
    for qt in q_tokens:
        if qt in haystack:
            total += 100.0
            continue
        best = max((fuzz.ratio(qt, ht) for ht in haystack_tokens), default=0.0)
        if best < FUZZY_THRESHOLD:
            return 0.0  # this query word matched nothing → whole recipe is out
        total += best

    return total / len(q_tokens)

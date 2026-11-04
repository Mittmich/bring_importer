"""Language registry, request-language resolution, and recipe localization.

A recipe stores its *base* content at the top level of ``recipe_json`` (the
historical shape) plus two optional keys:

  - ``inLanguage``: language code of the base content (schema.org field). Absent
    on recipes created before languages existed — their language is unknown.
  - ``translations``: ``{lang: {name, description, recipeYield, ingredients,
    instructions}}``. Each variant is self-contained (its own ingredient indices)
    so it can be edited independently of the base.

``localize_recipe`` picks the variant for a requested language and annotates the
result so the client can tell whether a translation exists.
"""

import copy
from typing import Any, Dict, List, Optional

from fastapi import Header, Query

# Code -> English name (used in LLM prompts) and native name (for UIs/emails).
SUPPORTED_LANGUAGES: Dict[str, Dict[str, str]] = {
    "en": {"english": "English", "native": "English"},
    "de": {"english": "German", "native": "Deutsch"},
}
DEFAULT_LANGUAGE = "en"

# Content fields that make up one language variant of a recipe.
CONTENT_FIELDS = ("name", "description", "recipeYield", "ingredients", "instructions")


def normalize_language(value: Optional[str]) -> Optional[str]:
    """Map ``"de-AT"``/``"DE"``/``"de_at"`` to ``"de"``; ``None`` if unsupported."""
    if not value:
        return None
    code = value.strip().lower().replace("_", "-").split("-")[0]
    return code if code in SUPPORTED_LANGUAGES else None


def parse_accept_language(header: Optional[str]) -> Optional[str]:
    """Return the highest-weighted supported language from an Accept-Language header."""
    if not header:
        return None
    candidates = []
    for i, part in enumerate(header.split(",")):
        pieces = part.strip().split(";")
        weight = 1.0
        for p in pieces[1:]:
            p = p.strip()
            if p.startswith("q="):
                try:
                    weight = float(p[2:])
                except ValueError:
                    weight = 0.0
        candidates.append((-weight, i, pieces[0]))
    for _, _, tag in sorted(candidates):
        code = normalize_language(tag)
        if code:
            return code
    return None


def language_name(code: Optional[str]) -> str:
    """English name of a language code for LLM prompts (falls back to the code)."""
    if not code:
        return ""
    return SUPPORTED_LANGUAGES.get(code, {}).get("english", code)


async def request_language(
    lang: Optional[str] = Query(None, include_in_schema=False),
    accept_language: Optional[str] = Header(None),
) -> Optional[str]:
    """FastAPI dependency: ``?lang=`` wins, then ``Accept-Language``, else ``None``."""
    return normalize_language(lang) or parse_accept_language(accept_language)


def available_languages(stored: Dict[str, Any]) -> List[str]:
    """Languages a recipe has content in (base language first, if known)."""
    langs: List[str] = []
    base = stored.get("inLanguage")
    if base:
        langs.append(base)
    for code in (stored.get("translations") or {}).keys():
        if code not in langs:
            langs.append(code)
    return langs


def variant_language(stored: Dict[str, Any], lang: Optional[str]) -> Optional[str]:
    """The translation key to use for ``lang``, or ``None`` to use the base content."""
    if not lang or lang == stored.get("inLanguage"):
        return None
    if lang in (stored.get("translations") or {}):
        return lang
    return None


def localize_recipe(stored: Dict[str, Any], lang: Optional[str]) -> Dict[str, Any]:
    """Return a copy of ``stored`` with ``lang``'s content on top, plus language metadata.

    Added keys:
      - ``language``: language of the returned content (``None`` = unknown legacy base).
      - ``requested_language``: the language that was asked for.
      - ``available_languages``: every language the recipe has content in.
      - ``translation_available``: ``False`` only when we *know* the requested
        language is missing (base language known and different, no translation).
    The raw ``translations`` map is dropped from the payload.
    """
    out = copy.deepcopy(stored)
    translations = out.pop("translations", None) or {}
    base_lang = out.get("inLanguage")
    key = variant_language(stored, lang)
    if key is not None:
        for field in CONTENT_FIELDS:
            if field in translations[key]:
                out[field] = translations[key][field]
        out.pop("recipeIngredient", None)
        out.pop("recipeInstructions", None)
        content_lang: Optional[str] = key
    else:
        content_lang = base_lang

    out["language"] = content_lang
    out["requested_language"] = lang
    out["available_languages"] = available_languages(stored)
    out["translation_available"] = not (
        lang is not None and content_lang != lang and base_lang is not None
    )
    return out


def localized_title(stored: Dict[str, Any], fallback: str, lang: Optional[str]) -> str:
    """Title in ``lang`` if a translation exists, else ``fallback`` (the base title)."""
    key = variant_language(stored, lang)
    if key is not None:
        name = (stored.get("translations") or {}).get(key, {}).get("name")
        if name:
            return str(name)
    return fallback


def all_variants(stored: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Base content followed by each translation — used for search haystacks."""
    variants = [stored]
    for v in (stored.get("translations") or {}).values():
        if isinstance(v, dict):
            variants.append(v)
    return variants


# Server-rendered strings (currently the PDF export). Keyed by language; every
# language must define every key — enforced by tests/test_recipe_pdf.py.
BACKEND_STRINGS: Dict[str, Dict[str, str]] = {
    "en": {
        "ingredients": "Ingredients",
        "instructions": "Instructions",
        "note": "Note",
        "servings": "servings",
        "uses": "Uses",
        "tags": "Tags",
        "source": "Source",
        "page": "Page {page} of {pages}",
        "exported": "Exported from {app} on {date}",
        "app": "My Recipes",
        "untitled": "Untitled recipe",
    },
    "de": {
        "ingredients": "Zutaten",
        "instructions": "Zubereitung",
        "note": "Notiz",
        "servings": "Portionen",
        "uses": "Benötigt",
        "tags": "Tags",
        "source": "Quelle",
        "page": "Seite {page} von {pages}",
        "exported": "Exportiert aus {app} am {date}",
        "app": "Meine Rezepte",
        "untitled": "Rezept ohne Titel",
    },
}


def backend_text(lang: Optional[str], key: str, **params: Any) -> str:
    """A server-rendered string in ``lang`` (falls back to English)."""
    table = BACKEND_STRINGS.get(lang or "", BACKEND_STRINGS[DEFAULT_LANGUAGE])
    template = table.get(key) or BACKEND_STRINGS[DEFAULT_LANGUAGE][key]
    return template.format(**params) if params else template

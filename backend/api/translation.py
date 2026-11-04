"""LLM-backed recipe translation behind a small provider seam.

``translate_recipe_content(content, target)`` translates one recipe variant
(``name``, ``description``, ``recipeYield``, ``ingredients``, ``instructions``)
into ``target`` and returns it in the same shape, together with the detected
source language.

Structure is preserved deterministically: the LLM only returns texts, and the
ingredient count, step count and each step's ingredient indices are copied
from the source. A response with the wrong number of items is rejected rather
than silently mixing languages.

Providers are registered in ``_PROVIDERS`` and selected with the
``TRANSLATION_PROVIDER`` env var (default ``openai``). Adding a provider means
writing one ``(content, target_name) -> _TranslationOutput`` function.
"""

from typing import Any, Callable, Dict, List, Optional, Tuple

from pydantic import BaseModel

from api.config import TRANSLATION_MODEL, TRANSLATION_PROVIDER
from api.i18n import language_name, normalize_language
from api.models import Ingredient


class TranslationError(Exception):
    """The provider failed or returned a structurally unusable translation."""


class _TranslationOutput(BaseModel):
    source_language: str  # ISO 639-1 code of the input, e.g. "de"
    name: str
    description: str
    recipeYield: str
    ingredients: List[Ingredient]
    instructions: List[str]


_SYSTEM_PROMPT = (
    "You translate cooking recipes. Translate every text field into the target language "
    "naturally, as a native cookbook would phrase it. Keep quantities and numbers exactly; "
    "translate units only when the target language uses a different word or abbreviation "
    "(e.g. 'tbsp' -> 'EL', 'tsp' -> 'TL' for German) and never convert between measurement "
    "systems. Return exactly as many ingredients and instruction steps as given, in the same "
    "order. If a field is already in the target language, return it unchanged. "
    "source_language is the ISO 639-1 code of the original text."
)


def _user_prompt(content: Dict[str, Any], target_name: str) -> str:
    ingredients = content.get("ingredients") or []
    steps = content.get("instructions") or []
    ing_lines = "\n".join(
        f"{i}. amount: {ing.get('amount', '')!r} | name: {ing.get('name', '')!r}"
        for i, ing in enumerate(ingredients)
    )
    step_lines = "\n".join(f"{i}. {s.get('text', '')}" for i, s in enumerate(steps))
    return (
        f"Target language: {target_name}\n\n"
        f"Title: {content.get('name') or ''}\n"
        f"Description: {content.get('description') or ''}\n"
        f"Yield: {content.get('recipeYield') or ''}\n\n"
        f"Ingredients ({len(ingredients)}):\n{ing_lines}\n\n"
        f"Instruction steps ({len(steps)}):\n{step_lines}"
    )


def _translate_openai(content: Dict[str, Any], target_name: str) -> Optional[_TranslationOutput]:
    # Imported lazily so this module has no import-time dependency on the
    # extraction module (and its OpenAI client singleton).
    from api.recipe_extraction import _get_client

    completion = _get_client().beta.chat.completions.parse(
        model=TRANSLATION_MODEL,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": _user_prompt(content, target_name)},
        ],
        response_format=_TranslationOutput,
    )
    return completion.choices[0].message.parsed


_PROVIDERS: Dict[str, Callable[[Dict[str, Any], str], Optional[_TranslationOutput]]] = {
    "openai": _translate_openai,
}


def translate_recipe_content(
    content: Dict[str, Any], target: str
) -> Tuple[Dict[str, Any], Optional[str]]:
    """Translate one recipe variant into ``target``.

    Returns ``(translated_variant, detected_source_language)``. Raises
    ``TranslationError`` on provider failure or a count mismatch.
    """
    provider = _PROVIDERS.get(TRANSLATION_PROVIDER)
    if provider is None:
        raise TranslationError(f"Unknown translation provider '{TRANSLATION_PROVIDER}'")

    try:
        out = provider(content, language_name(target))
    except Exception as e:  # provider/network errors
        raise TranslationError(f"Translation provider failed: {type(e).__name__}") from e
    if out is None:
        raise TranslationError("Translation provider returned no content")

    src_ingredients = content.get("ingredients") or []
    src_steps = content.get("instructions") or []
    if len(out.ingredients) != len(src_ingredients) or len(out.instructions) != len(src_steps):
        raise TranslationError("Translation came back incomplete — please try again")

    translated = {
        "name": out.name,
        "description": out.description,
        "recipeYield": out.recipeYield,
        "ingredients": [ing.model_dump() for ing in out.ingredients],
        "instructions": [
            {"text": text, "ingredients": list(step.get("ingredients") or [])}
            for text, step in zip(out.instructions, src_steps)
        ],
    }
    return translated, normalize_language(out.source_language)

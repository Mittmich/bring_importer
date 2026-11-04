"""LLM-backed recipe translation behind a small provider seam.

``translate_recipe_content(content, target)`` translates one recipe variant
(``name``, ``description``, ``recipeYield``, ``ingredients``, ``instructions``)
into ``target`` and returns it in the same shape, together with the detected
source language.

Structure is preserved deterministically: the LLM only returns texts, and the
ingredient count, step count and each step's ingredient indices are copied
from the source. A response with the wrong number of items is rejected rather
than silently mixing languages.

``detect_recipe_language(stored)`` asks the provider which language a stored
recipe is written in, and ``add_translation(stored, target)`` translates a
stored recipe's base content and records the result on it — the shared
building blocks of ``POST /recipes/{uuid}/translate`` and the
``translate_recipes.py`` backfill script.

Providers are registered in ``_PROVIDERS`` and selected with the
``TRANSLATION_PROVIDER`` env var (default ``openai``). Adding a provider means
writing a ``translate`` and a ``detect`` function and registering a
``Provider``.
"""

from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Tuple

from pydantic import BaseModel

from api.config import TRANSLATION_MODEL, TRANSLATION_PROVIDER
from api.i18n import CONTENT_FIELDS, language_name, normalize_language
from api.models import Ingredient


class TranslationError(Exception):
    """The provider failed or returned a structurally unusable translation."""


class _DetectionOutput(BaseModel):
    language: str  # ISO 639-1 code, e.g. "de"


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


def _detect_openai(sample: str) -> Optional[str]:
    from api.recipe_extraction import _get_client

    completion = _get_client().beta.chat.completions.parse(
        model=TRANSLATION_MODEL,
        messages=[
            {
                "role": "system",
                "content": (
                    "Identify the language a recipe is written in. Answer with its ISO 639-1 "
                    "code (e.g. 'en', 'de', 'fr'). Judge by the instructions and ingredient "
                    "names, not by loanwords or dish names."
                ),
            },
            {"role": "user", "content": sample},
        ],
        response_format=_DetectionOutput,
    )
    out = completion.choices[0].message.parsed
    return out.language if out else None


@dataclass(frozen=True)
class Provider:
    translate: Callable[[Dict[str, Any], str], Optional[_TranslationOutput]]
    detect: Callable[[str], Optional[str]]


_PROVIDERS: Dict[str, Provider] = {
    "openai": Provider(translate=_translate_openai, detect=_detect_openai),
}


def _provider() -> Provider:
    provider = _PROVIDERS.get(TRANSLATION_PROVIDER)
    if provider is None:
        raise TranslationError(f"Unknown translation provider '{TRANSLATION_PROVIDER}'")
    return provider


def recipe_content(stored: Dict[str, Any]) -> Dict[str, Any]:
    """The base-language content of a stored recipe, in the structured shape.

    Old flat-format recipes (``recipeIngredient`` / ``recipeInstructions``
    string lists) are wrapped so the translator always sees one shape.
    """
    content = {f: stored.get(f) for f in CONTENT_FIELDS}
    if "ingredients" not in stored:
        content["ingredients"] = [
            {"amount": "", "name": str(x)} for x in stored.get("recipeIngredient") or []
        ]
        content["instructions"] = [
            {"text": str(x), "ingredients": []} for x in stored.get("recipeInstructions") or []
        ]
    return content


def translate_recipe_content(
    content: Dict[str, Any], target: str
) -> Tuple[Dict[str, Any], Optional[str]]:
    """Translate one recipe variant into ``target``.

    Returns ``(translated_variant, detected_source_language)``. Raises
    ``TranslationError`` on provider failure or a count mismatch.
    """
    provider = _provider()
    try:
        out = provider.translate(content, language_name(target))
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


def detect_recipe_language(stored: Dict[str, Any]) -> Optional[str]:
    """Detect the language of a stored recipe's base content.

    Returns a lowercase ISO 639-1 code — possibly one the app doesn't support
    (e.g. ``"fr"``) — or ``None`` if the recipe has no text to judge. Raises
    ``TranslationError`` if the provider fails.
    """
    content = recipe_content(stored)
    # Judge by the running text — steps first, then ingredients. Titles (and
    # often descriptions) are dish names like "Pilzparfait" that stay German
    # in an otherwise English recipe, so they are only used as a last resort.
    lines = [s.get("text", "") for s in content["instructions"][:6]]
    lines += [str(i.get("name", "")) for i in content["ingredients"][:15]]
    if not any(line.strip() for line in lines):
        lines = [content.get("description") or "", content.get("name") or ""]
    sample = "\n".join(line.strip() for line in lines if line and line.strip())
    if not sample:
        return None
    try:
        code = _provider().detect(sample[:4000])
    except Exception as e:
        raise TranslationError(f"Language detection failed: {type(e).__name__}") from e
    if not code:
        return None
    return code.strip().lower().replace("_", "-").split("-")[0] or None


def add_translation(stored: Dict[str, Any], target: str) -> bool:
    """Translate ``stored``'s base content into ``target`` and record it on ``stored``.

    Mutates ``stored``: when its base language is unknown, the provider's
    detected source language is recorded as ``inLanguage``. If the provider
    reports the base is *already* in ``target``, the recorded language was wrong
    (or unknown): ``inLanguage`` is corrected to ``target``, any stale copy under
    ``translations[target]`` is dropped, and nothing is stored — a "translation"
    of a recipe into its own language is just a copy. Otherwise the translation
    is stored under ``translations[target]``. Returns True when a translation
    was stored. Raises ``TranslationError``.
    """
    if stored.get("inLanguage") == target:
        return False
    translated, source_lang = translate_recipe_content(recipe_content(stored), target)
    source_lang = normalize_language(source_lang)  # only supported codes are stored
    if source_lang == target:
        set_base_language(stored, target)
        return False
    if not stored.get("inLanguage") and source_lang:
        stored["inLanguage"] = source_lang
    stored.setdefault("translations", {})[target] = translated
    return True


def set_base_language(stored: Dict[str, Any], language: str) -> None:
    """Record ``language`` as the base content's language.

    A stored translation into that language is a copy of the base (or an
    artefact of an earlier wrong label) and would be unreachable, so it is
    dropped.
    """
    stored["inLanguage"] = language
    translations = stored.get("translations") or {}
    translations.pop(language, None)
    if not translations:
        stored.pop("translations", None)

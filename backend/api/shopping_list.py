"""Shopping-list ingredient merging via an LLM pass.

``merge_ingredients`` takes the flattened ingredient lists of every recipe in a
meal-plan week and collapses them into a single de-duplicated shopping list,
summing quantities where units are compatible. It mirrors the structured-output
pattern used in :mod:`api.recipe_extraction`.
"""

from typing import List

from pydantic import BaseModel

from api.models import Ingredient
from api.recipe_extraction import _get_client


def merge_ingredients(items: List[Ingredient]) -> List[Ingredient]:
    """Merge duplicate ingredients, summing compatible quantities.

    Rules (enforced via the prompt):
      - Combine entries for the same ingredient.
      - Sum quantities when units match or convert cleanly
        ("2 cups" + "1 cup" -> "3 cups").
      - Keep separate line items when units are incompatible or non-numeric
        ("salt to taste").
      - Normalize names to a readable singular form; never invent items.

    Degrades gracefully: returns ``[]`` for empty input (no LLM call) and falls
    back to the un-merged list if the LLM call fails or returns nothing.
    """
    if not items:
        return []

    class _MergedList(BaseModel):
        ingredients: List[Ingredient]

    numbered = "\n".join(f"{i}. {ing.amount} {ing.name}".strip() for i, ing in enumerate(items))
    try:
        completion = _get_client().beta.chat.completions.parse(
            model="gpt-5.4-nano",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You consolidate a combined grocery list assembled from several recipes. "
                        "Merge entries that refer to the same ingredient. Sum quantities when the "
                        "units are the same or convert cleanly (e.g. '2 cups'+'1 cup'='3 cups'). "
                        "Keep entries as separate line items when their units are incompatible or "
                        "the amount is non-numeric (e.g. 'to taste'). Normalize each name to a "
                        "readable singular form. Never invent ingredients that were not provided. "
                        "amount is the quantity + unit (empty string if there is none); name is "
                        "the ingredient."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Consolidate these {len(items)} ingredient lines into a deduplicated "
                        f"shopping list:\n{numbered}"
                    ),
                },
            ],
            response_format=_MergedList,
        )
    except Exception:
        return items

    result = completion.choices[0].message.parsed
    if result is None or not result.ingredients:
        return items
    return result.ingredients

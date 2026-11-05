"""Split hand-typed ingredient lines ("500 g Rindfleisch") into amount + name.

Used when a recipe is entered by hand: the user pastes one ingredient per line
and we store structured ``Ingredient`` objects like the LLM extraction does.
Deterministic and deliberately conservative — anything that doesn't start with
a quantity is kept whole as the name with an empty amount.
"""

import re
from typing import List

from api.models import Ingredient

# A leading quantity: "2", "1.5", "1,5", "1/2", "1 1/2", "½", "1½", "2-3", "2–3",
# optionally prefixed with "ca." / "approx." style hedges.
_NUMBER = r"(?:\d+(?:[.,]\d+)?(?:\s*[½⅓⅔¼¾⅛])?|[½⅓⅔¼¾⅛])"
_QUANTITY = (
    rf"(?:(?:ca\.?|approx\.?|etwa|about)\s+)?"
    rf"(?:\d+\s+\d+\s*/\s*\d+|\d+\s*/\s*\d+|{_NUMBER})"
    rf"(?:\s*[-–]\s*{_NUMBER})?"
)

# Units that belong to the amount (case-insensitive, optional trailing dot).
_UNITS = [
    # metric
    "mg",
    "g",
    "gr",
    "kg",
    "ml",
    "cl",
    "dl",
    "l",
    "ltr",
    # spoons / cups (de + en)
    "el",
    "tl",
    "msp",
    "tbsp",
    "tbs",
    "tsp",
    "cup",
    "cups",
    "tasse",
    "tassen",
    # imperial
    "oz",
    "lb",
    "lbs",
    "pint",
    "pints",
    "quart",
    "quarts",
    # counts / packaging
    "stk",
    "stück",
    "pkg",
    "pck",
    "päckchen",
    "packung",
    "packungen",
    "pack",
    "dose",
    "dosen",
    "can",
    "cans",
    "glas",
    "gläser",
    "becher",
    "flasche",
    "flaschen",
    "bund",
    "bunch",
    "bunches",
    "zehe",
    "zehen",
    "clove",
    "cloves",
    "scheibe",
    "scheiben",
    "slice",
    "slices",
    "prise",
    "prisen",
    "pinch",
    "pinches",
    "handvoll",
    "handful",
    "handfuls",
    "würfel",
    "zweig",
    "zweige",
    "sprig",
    "sprigs",
    "blatt",
    "blätter",
    "stange",
    "stangen",
    "kopf",
    "köpfe",
    "knolle",
    "knollen",
    "tablespoon",
    "tablespoons",
    "teaspoon",
    "teaspoons",
    "gramm",
    "kilogramm",
    "liter",
    "milliliter",
]
_UNIT = "(?:" + "|".join(sorted(map(re.escape, _UNITS), key=len, reverse=True)) + r")\.?"

_LINE_RE = re.compile(rf"^(?P<amount>{_QUANTITY}(?:\s*{_UNIT}(?=\s|$))?)\s+(?P<name>.+)$", re.I)
# Leading list markers people paste along: "- ", "• ", "* ", "1) ".
_BULLET_RE = re.compile(r"^\s*(?:[-–•*·]|\d+[.)](?=\s))\s*")


def parse_ingredient_line(line: str) -> Ingredient:
    """One line → ``Ingredient(amount, name)``; no quantity → empty amount."""
    text = _BULLET_RE.sub("", line).strip()
    text = re.sub(r"\s+", " ", text)
    match = _LINE_RE.match(text)
    if match:
        return Ingredient(amount=match["amount"].strip(), name=match["name"].strip())
    return Ingredient(amount="", name=text)


def parse_ingredient_lines(text: str) -> List[Ingredient]:
    """Every non-blank line of ``text`` as an ingredient, in order."""
    return [
        parse_ingredient_line(line)
        for line in text.splitlines()
        if _BULLET_RE.sub("", line).strip()
    ]

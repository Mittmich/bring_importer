"""Draft a recipe's prep steps for a menu's prep plan.

``draft_prep_steps`` turns a recipe's instructions into timed steps: a short name,
a duration, whether it needs the cook's hands, equipment (oven temperature) and
when it must be finished relative to serving. Drafts are only a starting point;
the user edits them in the app.

It asks the LLM for structured output and sanitises the result (clamps, rounds to
5 minutes, drops junk). Without an answer it falls back to one step per
instruction, laid out back to back so the last one ends at serving time.
"""

import logging
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel

from api.i18n import language_name
from api.recipe_extraction import _get_client

logger = logging.getLogger(__name__)

MAX_STEPS = 12
DAY_BEFORE_START = 18 * 60  # day-before steps start at 18:00 by default
EQUIPMENT = ("", "oven", "stove", "fridge")


class PrepStepDraft(BaseModel):
    name: str
    duration: int  # minutes
    hands: bool = True  # needs the cook (False: runs by itself, e.g. baking, resting)
    equipment: str = ""  # one of EQUIPMENT
    temp: Optional[int] = None  # oven temperature in °C
    day: int = 0  # 0 = cooking day, -1 = day before
    lead: int = 0  # day 0: minutes before serving by which it must be finished
    at: Optional[int] = None  # day -1: start, minutes after midnight


class _LlmStep(BaseModel):
    name: str
    duration_minutes: int
    hands_on: bool
    equipment: Literal["", "oven", "stove", "fridge"]
    oven_temp_c: Optional[int]
    make_day_before: bool
    ready_minutes_before_serving: int


class _LlmPlan(BaseModel):
    steps: List[_LlmStep]


def _round5(n: float, lo: int, hi: int) -> int:
    return int(max(lo, min(hi, round(n / 5) * 5)))


def _instruction_texts(recipe: Dict[str, Any]) -> List[str]:
    out = []
    for step in recipe.get("instructions") or []:
        text = step.get("text") if isinstance(step, dict) else step
        if isinstance(text, str) and text.strip():
            out.append(text.strip())
    return out


def _layout(steps: List[PrepStepDraft]) -> List[PrepStepDraft]:
    """Give day-before steps consecutive starts from 18:00."""
    at = DAY_BEFORE_START
    for s in steps:
        if s.day == -1:
            s.at = at
            at += s.duration
    return steps


def fallback_steps(recipe: Dict[str, Any]) -> List[PrepStepDraft]:
    """One 10-minute hands-on step per instruction, back to back up to serving."""
    texts = _instruction_texts(recipe)[:MAX_STEPS] or [str(recipe.get("name") or "Prepare")]
    steps = []
    for i, text in enumerate(texts):
        name = text if len(text) <= 80 else text[:77].rstrip() + "…"
        steps.append(PrepStepDraft(name=name, duration=10, lead=10 * (len(texts) - 1 - i)))
    return steps


def sanitize(raw: List[_LlmStep]) -> List[PrepStepDraft]:
    steps = []
    for s in raw[:MAX_STEPS]:
        name = " ".join((s.name or "").split())[:120]
        if not name:
            continue
        equipment = s.equipment if s.equipment in EQUIPMENT else ""
        temp = None
        if equipment == "oven":
            temp = _round5(s.oven_temp_c or 180, 50, 300)
        steps.append(
            PrepStepDraft(
                name=name,
                duration=_round5(s.duration_minutes, 5, 24 * 60),
                hands=bool(s.hands_on),
                equipment=equipment,
                temp=temp,
                day=-1 if s.make_day_before else 0,
                lead=_round5(s.ready_minutes_before_serving, 0, 24 * 60),
            )
        )
    return steps


def draft_prep_steps(recipe: Dict[str, Any], language: Optional[str] = None) -> List[PrepStepDraft]:
    """Timed prep steps for ``recipe`` (a stored/localized recipe dict)."""
    texts = _instruction_texts(recipe)
    if not texts:
        return _layout(fallback_steps(recipe))
    ingredients = "\n".join(
        f"- {i.get('amount', '')} {i.get('name', '')}".strip()
        for i in recipe.get("ingredients") or []
        if isinstance(i, dict)
    )
    numbered = "\n".join(f"{n}. {t}" for n, t in enumerate(texts, 1))
    try:
        completion = _get_client().beta.chat.completions.parse(
            model="gpt-5.4-mini",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You plan the cooking of one recipe for a dinner. Turn its instructions "
                        f"into at most {MAX_STEPS} prep steps in cooking order. Merge tiny "
                        "instructions; split long passive waits (baking, braising, resting, "
                        "chilling, marinating, rising) into their own step. For each step give: "
                        "a short imperative name (max 6 words); a realistic duration in minutes; "
                        "hands_on = false only when it runs by itself; equipment ('oven', "
                        "'stove', 'fridge' or ''); oven_temp_c for oven steps; make_day_before = "
                        "true only for steps that are commonly done a day ahead (doughs to rest, "
                        "marinades, things to set overnight); and ready_minutes_before_serving: "
                        "when the step must be finished, in minutes before the dish is served "
                        "(0 = right at serving). Steps that happen one after another must not "
                        "overlap; a hands-on step may run while a passive one does."
                        + (
                            f" Write the step names in {language_name(language)}."
                            if language
                            else ""
                        )
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Recipe: {recipe.get('name') or ''}\n"
                        f"Yield: {recipe.get('recipeYield') or ''}\n"
                        f"Ingredients:\n{ingredients}\n\nInstructions:\n{numbered}"
                    ),
                },
            ],
            response_format=_LlmPlan,
        )
        parsed = completion.choices[0].message.parsed
        steps = sanitize(parsed.steps) if parsed is not None else []
    except Exception:
        logger.exception("Drafting prep steps failed; using the fallback")
        steps = []
    return _layout(steps or fallback_steps(recipe))

"""Draft a recipe's prep steps for a menu's prep plan.

``draft_prep_steps`` turns a recipe's instructions into timed steps: a short name,
a duration, whether it needs the cook's hands, equipment (oven temperature) and
when it must be finished relative to serving. Drafts are only a starting point;
the user edits them in the app.

It asks the LLM for structured output and sanitises the result (clamps, rounds to
5 minutes, drops junk). Without an answer it falls back to one step per
instruction, laid out back to back so the last one ends at serving time. The cook
can add instructions ("make the dough the day before").

``revise_plan`` rewrites a whole menu's plan from a request in plain words ("serve
dessert at 21:30"). It returns only what the AI changed; on failure it raises
``PlanRevisionError`` and the plan stays as it is.
"""

import json
import logging
from typing import Any, Dict, List, Literal, Optional, Sequence

from pydantic import BaseModel

from api.i18n import language_name
from api.recipe_extraction import _get_client

logger = logging.getLogger(__name__)

MAX_STEPS = 12
MAX_INSTRUCTIONS = 500  # characters of cook's notes / edit request
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


class _RevStep(_LlmStep):
    day_before_start_minutes: Optional[int]  # day-before steps: start, minutes after midnight


class _RevCourse(BaseModel):
    course_id: int
    serve_minutes: int
    steps: List[_RevStep]


class _RevPlan(BaseModel):
    courses: List[_RevCourse]


class PlanRevisionError(Exception):
    """The AI could not revise the plan."""


class CourseRevision(BaseModel):
    course_id: int
    serve: int
    steps: List[PrepStepDraft]


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
    """Give day-before steps without a start consecutive starts from 18:00."""
    at = DAY_BEFORE_START
    for s in steps:
        if s.day == -1:
            if s.at is None:
                s.at = at
            at = s.at + s.duration
    return steps


def _notes(instructions: Optional[str]) -> str:
    text = " ".join((instructions or "").split())[:MAX_INSTRUCTIONS]
    return f"\n\nThe cook's instructions (follow them): {text}" if text else ""


def fallback_steps(recipe: Dict[str, Any]) -> List[PrepStepDraft]:
    """One 10-minute hands-on step per instruction, back to back up to serving."""
    texts = _instruction_texts(recipe)[:MAX_STEPS] or [str(recipe.get("name") or "Prepare")]
    steps = []
    for i, text in enumerate(texts):
        name = text if len(text) <= 80 else text[:77].rstrip() + "…"
        steps.append(PrepStepDraft(name=name, duration=10, lead=10 * (len(texts) - 1 - i)))
    return steps


def sanitize(raw: Sequence[_LlmStep]) -> List[PrepStepDraft]:
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
        at = getattr(s, "day_before_start_minutes", None)
        if steps[-1].day == -1 and at is not None:
            steps[-1].at = _round5(at, 0, 1435)
    return steps


def draft_prep_steps(
    recipe: Dict[str, Any],
    language: Optional[str] = None,
    instructions: Optional[str] = None,
) -> List[PrepStepDraft]:
    """Timed prep steps for ``recipe`` (a stored/localized recipe dict), optionally
    following the cook's ``instructions``."""
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
                        "overlap; a hands-on step may run while a passive one does. If the "
                        "cook gives instructions, follow them where they make sense."
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
                        + _notes(instructions)
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


def _hhmm(m: Optional[int]) -> Optional[str]:
    return None if m is None else f"{m // 60:02d}:{m % 60:02d}"


def _plan_for_llm(menu: Dict[str, Any]) -> Dict[str, Any]:
    """The menu as the AI sees it: courses with serving times and their steps."""
    courses = []
    for c in sorted(menu["courses"], key=lambda c: (c["serve"], c["position"], c["id"])):
        steps = [s for s in menu["steps"] if s["course_id"] == c["id"]]
        courses.append(
            {
                "course_id": c["id"],
                "name": c["name"],
                "recipe": c.get("recipe_title") or "",
                "serve_minutes": c["serve"],
                "serve_time": _hhmm(c["serve"]),
                "steps": [
                    {
                        "name": s["name"],
                        "duration_minutes": s["duration"],
                        "hands_on": bool(s["hands"]),
                        "equipment": s["equipment"] or "",
                        "oven_temp_c": s["temp"],
                        "make_day_before": s["day"] == -1,
                        "ready_minutes_before_serving": s["lead"],
                        "day_before_start_minutes": s["at"] if s["day"] == -1 else None,
                    }
                    for s in steps
                ],
            }
        )
    return {"guests": menu.get("guests"), "courses": courses}


def revise_plan(
    menu: Dict[str, Any], request: str, language: Optional[str] = None
) -> List[CourseRevision]:
    """Apply the cook's ``request`` to ``menu`` (the API's menu payload).

    Returns a revision per course the AI changed; courses it leaves out, unknown
    course ids and duplicates are dropped. Raises ``PlanRevisionError`` when the AI
    gives no usable answer.
    """
    text = " ".join((request or "").split())[:MAX_INSTRUCTIONS]
    if not text or not menu.get("courses"):
        raise PlanRevisionError("Nothing to revise")
    plan = _plan_for_llm(menu)
    try:
        completion = _get_client().beta.chat.completions.parse(
            model="gpt-5.4-mini",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You edit the prep plan of a dinner menu. You get the courses (each "
                        "with its serving time in minutes after midnight) and their timed "
                        "steps, and the cook's request. Apply the request and return every "
                        "course you change with ALL of its steps (the steps you return replace "
                        "the course's steps) and its serving time; leave out courses you don't "
                        "change. Don't add or remove courses. Keep steps the request doesn't "
                        "touch exactly as they are. Step fields: a short imperative name (max 6 "
                        "words); duration_minutes; hands_on = false only when it runs by itself; "
                        "equipment ('oven', 'stove', 'fridge' or ''); oven_temp_c for oven steps; "
                        "make_day_before; ready_minutes_before_serving for cooking-day steps "
                        "(when it must be finished, in minutes before that course is served); "
                        "day_before_start_minutes for day-before steps (start time in minutes "
                        "after midnight, else null). At most "
                        f"{MAX_STEPS} steps per course. Times are multiples of 5 minutes."
                        + (
                            f" Write new step names in {language_name(language)}."
                            if language
                            else ""
                        )
                    ),
                },
                {
                    "role": "user",
                    "content": f"Plan:\n{json.dumps(plan, ensure_ascii=False)}\n\nRequest: {text}",
                },
            ],
            response_format=_RevPlan,
        )
        parsed = completion.choices[0].message.parsed
    except Exception as exc:
        logger.exception("Revising the prep plan failed")
        raise PlanRevisionError("The AI could not revise the plan") from exc
    if parsed is None:
        raise PlanRevisionError("The AI gave no answer")

    known = {c["id"] for c in menu["courses"]}
    out: List[CourseRevision] = []
    seen = set()
    for c in parsed.courses:
        if c.course_id not in known or c.course_id in seen:
            continue
        seen.add(c.course_id)
        steps = _layout(sanitize(c.steps))
        if not steps:
            continue  # never wipe a course
        out.append(
            CourseRevision(
                course_id=c.course_id, serve=_round5(c.serve_minutes, 0, 1435), steps=steps
            )
        )
    return out

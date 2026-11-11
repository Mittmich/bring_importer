"""Menus with prep planning. See .claude/plans/menus-prep-planning.md.

A menu is a set of courses (each a recipe with a serving time) plus editable,
timed prep steps. Every endpoint is scoped to the menu's owner; another user's
menu is a 404.

- ``GET /menus`` — the user's menus, newest first, with course titles.
- ``POST /menus`` — create a menu.
- ``GET /menus/{id}`` — the full menu: courses + steps.
- ``GET /menus/{id}/plan.pdf`` — the menu and its prep plan as a printable PDF.
- ``PATCH /menus/{id}`` / ``DELETE /menus/{id}``.
- ``POST /menus/{id}/courses`` — add a recipe as a course; drafts its prep steps.
- ``PATCH|DELETE /menus/{id}/courses/{course_id}``.
- ``PUT /menus/{id}/courses/order`` — ``{"course_ids": [...]}``: all the menu's courses in
  their new order.
- ``POST /menus/{id}/courses/{course_id}/redraft`` — replace the course's steps with a new draft
  (optional ``{"instructions": ...}`` for the AI, as on ``POST /courses``).
- ``POST /menus/{id}/revise`` — ``{"request": ...}``: the AI edits the whole plan (serving
  times and steps). 502 if it can't; the plan is then unchanged.
- ``POST /menus/{id}/steps`` / ``PATCH|DELETE /menus/{id}/steps/{step_id}``.
- ``POST /menus/{id}/shopping-list`` — merged ingredients for the guest count; the token
  works with the weekly plan's public Bring page (``/meal-plan/shopping-list/{token}.html``).

Every mutation returns the full menu, so the client can replace its copy.
"""

import json
import uuid as uuid_mod
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from starlette.concurrency import run_in_threadpool

from api import db, recipe_images
from api.access import accessible_recipes_sql
from api.auth import get_current_user, get_user_id
from api.i18n import BACKEND_STRINGS, localize_recipe, localized_title, request_language
from api.menu_pdf import MenuRecipe, render_menu_pdf
from api.models import (
    Ingredient,
    MenuCourseCreate,
    MenuCourseOrder,
    MenuCourseUpdate,
    MenuCreate,
    MenuRedraft,
    MenuRevise,
    MenuStepCreate,
    MenuStepUpdate,
    MenuUpdate,
    User,
)
from api.prep_steps import (
    DAY_BEFORE_START,
    PlanRevisionError,
    PrepStepDraft,
    draft_prep_steps,
    revise_plan,
)
from api.recipe_pdf import (
    build_document,
    content_disposition,
    parse_servings,
    pdf_filename,
    scale_text,
)
from api.shopping_list import merge_ingredients

router = APIRouter(prefix="/menus", tags=["menus"])

FIRST_SERVE = 19 * 60  # a new menu's first course is served at 19:00
COURSE_GAP = 45  # each further course 45 minutes after the previous one


def _uid(current_user: User) -> int:
    user_id = get_user_id(current_user.email)
    if user_id is None:
        raise HTTPException(status_code=401, detail="Unknown user")
    return user_id


def _owned_menu(cursor, menu_id: int, user_id: int):
    row = cursor.execute(
        "SELECT id, title, date, guests, created_at, updated_at FROM menus "
        "WHERE id = ? AND user_id = ?",
        (menu_id, user_id),
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Menu not found")
    return row


def _touch(cursor, menu_id: int) -> None:
    cursor.execute("UPDATE menus SET updated_at = CURRENT_TIMESTAMP WHERE id = ?", (menu_id,))


def _load_json(text: Optional[str]) -> Dict[str, Any]:
    try:
        data = json.loads(text or "{}")
    except (TypeError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _menu_payload(cursor, menu, lang: Optional[str]) -> Dict[str, Any]:
    courses = cursor.execute(
        "SELECT c.id, c.recipe_uuid, c.name, c.serve, c.position, r.title AS recipe_title, "
        "r.recipe_json FROM menu_courses c JOIN recipes r ON r.uuid = c.recipe_uuid "
        "WHERE c.menu_id = ? ORDER BY c.position, c.serve, c.id",
        (menu["id"],),
    ).fetchall()
    course_ids = [c["id"] for c in courses]
    steps = []
    if course_ids:
        marks = ",".join("?" * len(course_ids))
        steps = cursor.execute(
            "SELECT id, course_id, name, duration, day, lead, at, hands, equipment, temp, done, "
            f"position FROM menu_steps WHERE course_id IN ({marks}) ORDER BY position, id",
            course_ids,
        ).fetchall()

    course_list = []
    for c in courses:
        stored = _load_json(c["recipe_json"])
        recipe_yield = localize_recipe(stored, lang).get("recipeYield") or ""
        course_list.append(
            {
                "id": c["id"],
                "recipe_uuid": c["recipe_uuid"],
                "recipe_title": localized_title(stored, c["recipe_title"] or "", lang),
                "recipe_yield": recipe_yield,
                "servings": parse_servings(recipe_yield),
                "name": c["name"],
                "serve": c["serve"],
                "position": c["position"],
            }
        )
    return {
        "id": menu["id"],
        "title": menu["title"],
        "date": menu["date"],
        "guests": menu["guests"],
        "updated_at": menu["updated_at"],
        "courses": course_list,
        "steps": [
            {
                "id": s["id"],
                "course_id": s["course_id"],
                "name": s["name"],
                "duration": s["duration"],
                "day": s["day"],
                "lead": s["lead"],
                "at": s["at"],
                "hands": bool(s["hands"]),
                "equipment": s["equipment"],
                "temp": s["temp"],
                "done": bool(s["done"]),
                "position": s["position"],
            }
            for s in steps
        ],
    }


def _respond(menu_id: int, user_id: int, lang: Optional[str]) -> Dict[str, Any]:
    conn = db.get_db_connection()
    try:
        cursor = conn.cursor()
        return _menu_payload(cursor, _owned_menu(cursor, menu_id, user_id), lang)
    finally:
        conn.close()


def _insert_steps(cursor, menu_id: int, course_id: int, steps: List[PrepStepDraft]) -> None:
    start = cursor.execute(
        "SELECT COALESCE(MAX(position), -1) + 1 AS p FROM menu_steps WHERE menu_id = ?",
        (menu_id,),
    ).fetchone()["p"]
    for i, s in enumerate(steps):
        cursor.execute(
            "INSERT INTO menu_steps (menu_id, course_id, name, duration, day, lead, at, hands, "
            "equipment, temp, position) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                menu_id,
                course_id,
                s.name,
                s.duration,
                s.day,
                s.lead,
                s.at if s.day == -1 else None,
                int(s.hands),
                s.equipment,
                s.temp if s.equipment == "oven" else None,
                start + i,
            ),
        )


def _accessible_recipe(cursor, recipe_uuid: str, user_id: int):
    return cursor.execute(
        f"SELECT r.uuid, r.recipe_json FROM recipes r WHERE r.uuid = ? AND "
        f"{accessible_recipes_sql('r')}",
        (recipe_uuid, user_id, user_id, user_id, user_id),
    ).fetchone()


def _course_recipe(cursor, menu_id: int, course_id: int):
    row = cursor.execute(
        "SELECT c.id, r.recipe_json FROM menu_courses c JOIN recipes r ON r.uuid = c.recipe_uuid "
        "WHERE c.id = ? AND c.menu_id = ?",
        (course_id, menu_id),
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Course not found")
    return row


# ---------------------------------------------------------------------------
# Menus
# ---------------------------------------------------------------------------


@router.get("")
async def list_menus(
    current_user: User = Depends(get_current_user),  # noqa: B008
    lang: Optional[str] = Depends(request_language),  # noqa: B008
):
    user_id = _uid(current_user)
    conn = db.get_db_connection()
    try:
        cursor = conn.cursor()
        menus = cursor.execute(
            "SELECT id, title, date, guests, updated_at FROM menus WHERE user_id = ? "
            "ORDER BY COALESCE(date, '9999-12-31') DESC, updated_at DESC, id DESC",
            (user_id,),
        ).fetchall()
        out = []
        for m in menus:
            courses = cursor.execute(
                "SELECT c.name, c.serve, r.title AS recipe_title, r.recipe_json "
                "FROM menu_courses c JOIN recipes r ON r.uuid = c.recipe_uuid "
                "WHERE c.menu_id = ? ORDER BY c.position, c.serve, c.id",
                (m["id"],),
            ).fetchall()
            out.append(
                {
                    "id": m["id"],
                    "title": m["title"],
                    "date": m["date"],
                    "guests": m["guests"],
                    "updated_at": m["updated_at"],
                    "courses": [
                        {
                            "name": c["name"],
                            "serve": c["serve"],
                            "recipe_title": localized_title(
                                _load_json(c["recipe_json"]), c["recipe_title"] or "", lang
                            ),
                        }
                        for c in courses
                    ],
                }
            )
        return out
    finally:
        conn.close()


@router.post("")
async def create_menu(
    body: MenuCreate,
    current_user: User = Depends(get_current_user),  # noqa: B008
    lang: Optional[str] = Depends(request_language),  # noqa: B008
):
    user_id = _uid(current_user)
    conn = db.get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO menus (user_id, title, date, guests) VALUES (?, ?, ?, ?)",
            (user_id, body.title.strip(), body.date, body.guests),
        )
        menu_id = cursor.lastrowid
        conn.commit()
    finally:
        conn.close()
    assert menu_id is not None
    return _respond(menu_id, user_id, lang)


def _course_recipes(menu: Dict[str, Any], user_id: int, lang: str) -> List[MenuRecipe]:
    """Each course's recipe for the PDF, in course order, scaled to the guests."""
    out = []
    conn = db.get_db_connection()
    try:
        cursor = conn.cursor()
        for c in sorted(menu["courses"], key=lambda c: (c["position"], c["serve"], c["id"])):
            row = cursor.execute(
                f"SELECT r.recipe_json, r.has_image FROM recipes r WHERE r.uuid = ? AND "
                f"{accessible_recipes_sql('r')}",
                (c["recipe_uuid"], user_id, user_id, user_id, user_id),
            ).fetchone()
            if row is None:
                continue
            data = localize_recipe(_load_json(row["recipe_json"]), lang)
            doc = build_document(data, servings=menu["guests"], lang=lang)
            image = recipe_images.image_path(c["recipe_uuid"]) if row["has_image"] else None
            out.append(MenuRecipe(c["name"], doc, image))
    finally:
        conn.close()
    return out


@router.get("/{menu_id}/plan.pdf", include_in_schema=False)
async def get_menu_pdf(
    menu_id: int,
    recipes: bool = Query(False),
    current_user: User = Depends(get_current_user),  # noqa: B008
    lang: Optional[str] = Depends(request_language),  # noqa: B008
):
    """The menu and its prep plan as a printable PDF, in the request language.

    ``recipes`` appends each course's recipe, scaled to the guests. A recipe the
    user can no longer open (unshared since it was added) is left out.
    """
    user_id = _uid(current_user)
    menu = _respond(menu_id, user_id, lang)
    pdf_lang = lang if lang in BACKEND_STRINGS else "en"
    extra = _course_recipes(menu, user_id, pdf_lang) if recipes else None
    pdf_bytes = await run_in_threadpool(render_menu_pdf, menu, pdf_lang, None, extra)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": content_disposition(pdf_filename(menu["title"]))},
    )


@router.get("/{menu_id}")
async def get_menu(
    menu_id: int,
    current_user: User = Depends(get_current_user),  # noqa: B008
    lang: Optional[str] = Depends(request_language),  # noqa: B008
):
    return _respond(menu_id, _uid(current_user), lang)


@router.patch("/{menu_id}")
async def update_menu(
    menu_id: int,
    body: MenuUpdate,
    current_user: User = Depends(get_current_user),  # noqa: B008
    lang: Optional[str] = Depends(request_language),  # noqa: B008
):
    user_id = _uid(current_user)
    conn = db.get_db_connection()
    try:
        cursor = conn.cursor()
        _owned_menu(cursor, menu_id, user_id)
        changes = body.model_dump(exclude_unset=True)
        if changes.get("title") is not None:
            cursor.execute(
                "UPDATE menus SET title = ? WHERE id = ?", (changes["title"].strip(), menu_id)
            )
        if "date" in changes:
            cursor.execute(
                "UPDATE menus SET date = ? WHERE id = ?", (changes["date"] or None, menu_id)
            )
        if changes.get("guests") is not None:
            cursor.execute("UPDATE menus SET guests = ? WHERE id = ?", (changes["guests"], menu_id))
        _touch(cursor, menu_id)
        conn.commit()
    finally:
        conn.close()
    return _respond(menu_id, user_id, lang)


@router.delete("/{menu_id}", status_code=204)
async def delete_menu(
    menu_id: int,
    current_user: User = Depends(get_current_user),  # noqa: B008
):
    user_id = _uid(current_user)
    conn = db.get_db_connection()
    try:
        cursor = conn.cursor()
        _owned_menu(cursor, menu_id, user_id)
        cursor.execute("DELETE FROM menu_steps WHERE menu_id = ?", (menu_id,))
        cursor.execute("DELETE FROM menu_courses WHERE menu_id = ?", (menu_id,))
        cursor.execute("DELETE FROM menus WHERE id = ?", (menu_id,))
        conn.commit()
    finally:
        conn.close()
    return None


# ---------------------------------------------------------------------------
# Courses
# ---------------------------------------------------------------------------


@router.post("/{menu_id}/courses")
async def add_course(
    menu_id: int,
    body: MenuCourseCreate,
    current_user: User = Depends(get_current_user),  # noqa: B008
    lang: Optional[str] = Depends(request_language),  # noqa: B008
):
    """Add a recipe the user can access as a course, and draft its prep steps."""
    user_id = _uid(current_user)
    conn = db.get_db_connection()
    try:
        cursor = conn.cursor()
        _owned_menu(cursor, menu_id, user_id)
        recipe = _accessible_recipe(cursor, body.recipe_uuid, user_id)
        if recipe is None:
            raise HTTPException(status_code=404, detail="Recipe not found")
        stats = cursor.execute(
            "SELECT COUNT(*) AS n, MAX(serve) AS last, COALESCE(MAX(position), -1) AS pos "
            "FROM menu_courses WHERE menu_id = ?",
            (menu_id,),
        ).fetchone()
        serve = body.serve
        if serve is None:
            serve = FIRST_SERVE if stats["last"] is None else min(1439, stats["last"] + COURSE_GAP)
        name = (body.name or "").strip() or f"Course {stats['n'] + 1}"
        localized = localize_recipe(_load_json(recipe["recipe_json"]), lang)
    finally:
        conn.close()

    # The LLM call can take a few seconds; keep it off the event loop and the DB.
    steps = await run_in_threadpool(draft_prep_steps, localized, lang, body.instructions)

    conn = db.get_db_connection()
    try:
        cursor = conn.cursor()
        _owned_menu(cursor, menu_id, user_id)
        cursor.execute(
            "INSERT INTO menu_courses (menu_id, recipe_uuid, name, serve, position) "
            "VALUES (?, ?, ?, ?, ?)",
            (menu_id, body.recipe_uuid, name, serve, stats["pos"] + 1),
        )
        course_id = cursor.lastrowid
        assert course_id is not None
        _insert_steps(cursor, menu_id, course_id, steps)
        _touch(cursor, menu_id)
        conn.commit()
    finally:
        conn.close()
    return _respond(menu_id, user_id, lang)


@router.put("/{menu_id}/courses/order")
async def reorder_courses(
    menu_id: int,
    body: MenuCourseOrder,
    current_user: User = Depends(get_current_user),  # noqa: B008
    lang: Optional[str] = Depends(request_language),  # noqa: B008
):
    """Put the courses in the given order (it must list each course exactly once)."""
    user_id = _uid(current_user)
    conn = db.get_db_connection()
    try:
        cursor = conn.cursor()
        _owned_menu(cursor, menu_id, user_id)
        ids = [
            r["id"]
            for r in cursor.execute(
                "SELECT id FROM menu_courses WHERE menu_id = ?", (menu_id,)
            ).fetchall()
        ]
        if sorted(body.course_ids) != sorted(ids):
            raise HTTPException(status_code=400, detail="List every course of the menu once")
        for position, course_id in enumerate(body.course_ids):
            cursor.execute(
                "UPDATE menu_courses SET position = ? WHERE id = ?", (position, course_id)
            )
        _touch(cursor, menu_id)
        conn.commit()
    finally:
        conn.close()
    return _respond(menu_id, user_id, lang)


@router.patch("/{menu_id}/courses/{course_id}")
async def update_course(
    menu_id: int,
    course_id: int,
    body: MenuCourseUpdate,
    current_user: User = Depends(get_current_user),  # noqa: B008
    lang: Optional[str] = Depends(request_language),  # noqa: B008
):
    user_id = _uid(current_user)
    conn = db.get_db_connection()
    try:
        cursor = conn.cursor()
        _owned_menu(cursor, menu_id, user_id)
        _course_recipe(cursor, menu_id, course_id)
        for field in ("name", "serve", "position"):
            value = getattr(body, field)
            if value is not None:
                if field == "name":
                    value = value.strip()
                cursor.execute(
                    f"UPDATE menu_courses SET {field} = ? WHERE id = ?", (value, course_id)
                )
        _touch(cursor, menu_id)
        conn.commit()
    finally:
        conn.close()
    return _respond(menu_id, user_id, lang)


@router.delete("/{menu_id}/courses/{course_id}")
async def delete_course(
    menu_id: int,
    course_id: int,
    current_user: User = Depends(get_current_user),  # noqa: B008
    lang: Optional[str] = Depends(request_language),  # noqa: B008
):
    user_id = _uid(current_user)
    conn = db.get_db_connection()
    try:
        cursor = conn.cursor()
        _owned_menu(cursor, menu_id, user_id)
        row = cursor.execute(
            "SELECT id FROM menu_courses WHERE id = ? AND menu_id = ?", (course_id, menu_id)
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Course not found")
        cursor.execute("DELETE FROM menu_steps WHERE course_id = ?", (course_id,))
        cursor.execute("DELETE FROM menu_courses WHERE id = ?", (course_id,))
        _touch(cursor, menu_id)
        conn.commit()
    finally:
        conn.close()
    return _respond(menu_id, user_id, lang)


@router.post("/{menu_id}/courses/{course_id}/redraft")
async def redraft_course(
    menu_id: int,
    course_id: int,
    body: Optional[MenuRedraft] = None,
    current_user: User = Depends(get_current_user),  # noqa: B008
    lang: Optional[str] = Depends(request_language),  # noqa: B008
):
    """Throw away the course's steps (including edits) and draft them again."""
    user_id = _uid(current_user)
    conn = db.get_db_connection()
    try:
        cursor = conn.cursor()
        _owned_menu(cursor, menu_id, user_id)
        localized = localize_recipe(
            _load_json(_course_recipe(cursor, menu_id, course_id)["recipe_json"]), lang
        )
    finally:
        conn.close()

    instructions = body.instructions if body else None
    steps = await run_in_threadpool(draft_prep_steps, localized, lang, instructions)

    conn = db.get_db_connection()
    try:
        cursor = conn.cursor()
        _owned_menu(cursor, menu_id, user_id)
        _course_recipe(cursor, menu_id, course_id)
        cursor.execute("DELETE FROM menu_steps WHERE course_id = ?", (course_id,))
        _insert_steps(cursor, menu_id, course_id, steps)
        _touch(cursor, menu_id)
        conn.commit()
    finally:
        conn.close()
    return _respond(menu_id, user_id, lang)


@router.post("/{menu_id}/revise")
async def revise_menu_plan(
    menu_id: int,
    body: MenuRevise,
    current_user: User = Depends(get_current_user),  # noqa: B008
    lang: Optional[str] = Depends(request_language),  # noqa: B008
):
    """Let the AI edit the plan from the cook's request. Courses it changes get
    their new serving time and steps (done marks reset); the rest stay as they are."""
    user_id = _uid(current_user)
    menu = _respond(menu_id, user_id, lang)
    if not menu["courses"]:
        raise HTTPException(status_code=400, detail="Add a course first")
    try:
        revisions = await run_in_threadpool(revise_plan, menu, body.request, lang)
    except PlanRevisionError:
        raise HTTPException(
            status_code=502, detail="The AI could not edit the plan. Try again."
        ) from None

    conn = db.get_db_connection()
    try:
        cursor = conn.cursor()
        _owned_menu(cursor, menu_id, user_id)
        for rev in revisions:
            row = cursor.execute(
                "SELECT id FROM menu_courses WHERE id = ? AND menu_id = ?",
                (rev.course_id, menu_id),
            ).fetchone()
            if row is None:  # removed meanwhile
                continue
            cursor.execute(
                "UPDATE menu_courses SET serve = ? WHERE id = ?", (rev.serve, rev.course_id)
            )
            cursor.execute("DELETE FROM menu_steps WHERE course_id = ?", (rev.course_id,))
            _insert_steps(cursor, menu_id, rev.course_id, rev.steps)
        _touch(cursor, menu_id)
        conn.commit()
    finally:
        conn.close()
    return _respond(menu_id, user_id, lang)


# ---------------------------------------------------------------------------
# Steps
# ---------------------------------------------------------------------------


def _owned_step(cursor, menu_id: int, step_id: int):
    row = cursor.execute(
        "SELECT id, day, at, equipment FROM menu_steps WHERE id = ? AND menu_id = ?",
        (step_id, menu_id),
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Step not found")
    return row


@router.post("/{menu_id}/steps")
async def add_step(
    menu_id: int,
    body: MenuStepCreate,
    current_user: User = Depends(get_current_user),  # noqa: B008
    lang: Optional[str] = Depends(request_language),  # noqa: B008
):
    user_id = _uid(current_user)
    conn = db.get_db_connection()
    try:
        cursor = conn.cursor()
        _owned_menu(cursor, menu_id, user_id)
        _course_recipe(cursor, menu_id, body.course_id)
        draft = PrepStepDraft(
            name=body.name.strip(),
            duration=body.duration,
            hands=body.hands,
            equipment=body.equipment,
            temp=body.temp if body.equipment != "oven" else (body.temp or 180),
            day=body.day,
            lead=body.lead,
            at=body.at if body.at is not None else DAY_BEFORE_START,
        )
        _insert_steps(cursor, menu_id, body.course_id, [draft])
        _touch(cursor, menu_id)
        conn.commit()
    finally:
        conn.close()
    return _respond(menu_id, user_id, lang)


@router.patch("/{menu_id}/steps/{step_id}")
async def update_step(
    menu_id: int,
    step_id: int,
    body: MenuStepUpdate,
    current_user: User = Depends(get_current_user),  # noqa: B008
    lang: Optional[str] = Depends(request_language),  # noqa: B008
):
    user_id = _uid(current_user)
    conn = db.get_db_connection()
    try:
        cursor = conn.cursor()
        _owned_menu(cursor, menu_id, user_id)
        step = _owned_step(cursor, menu_id, step_id)
        changes = body.model_dump(exclude_unset=True)
        if "name" in changes and changes["name"] is not None:
            changes["name"] = changes["name"].strip()
        for key in ("hands", "done"):
            if changes.get(key) is not None:
                changes[key] = int(changes[key])
        # Moving a step to the day before needs a start time.
        if changes.get("day") == -1 and step["at"] is None and changes.get("at") is None:
            changes["at"] = DAY_BEFORE_START
        equipment = changes.get("equipment", step["equipment"])
        if equipment == "oven" and changes.get("equipment") == "oven" and "temp" not in changes:
            changes["temp"] = 180
        if equipment != "oven":
            changes["temp"] = None
        nullable = {"at", "temp"}
        for key, value in changes.items():
            if value is None and key not in nullable:
                continue
            cursor.execute(f"UPDATE menu_steps SET {key} = ? WHERE id = ?", (value, step_id))
        _touch(cursor, menu_id)
        conn.commit()
    finally:
        conn.close()
    return _respond(menu_id, user_id, lang)


@router.delete("/{menu_id}/steps/{step_id}")
async def delete_step(
    menu_id: int,
    step_id: int,
    current_user: User = Depends(get_current_user),  # noqa: B008
    lang: Optional[str] = Depends(request_language),  # noqa: B008
):
    user_id = _uid(current_user)
    conn = db.get_db_connection()
    try:
        cursor = conn.cursor()
        _owned_menu(cursor, menu_id, user_id)
        _owned_step(cursor, menu_id, step_id)
        cursor.execute("DELETE FROM menu_steps WHERE id = ?", (step_id,))
        _touch(cursor, menu_id)
        conn.commit()
    finally:
        conn.close()
    return _respond(menu_id, user_id, lang)


# ---------------------------------------------------------------------------
# Shopping list
# ---------------------------------------------------------------------------


@router.post("/{menu_id}/shopping-list")
async def menu_shopping_list(
    menu_id: int,
    current_user: User = Depends(get_current_user),  # noqa: B008
    lang: Optional[str] = Depends(request_language),  # noqa: B008
):
    """Every course's ingredients scaled to the guest count, merged and cached.

    Returns ``{token, items}``; Bring imports ``/meal-plan/shopping-list/{token}.html``.
    """
    user_id = _uid(current_user)
    conn = db.get_db_connection()
    try:
        cursor = conn.cursor()
        menu = _owned_menu(cursor, menu_id, user_id)
        rows = cursor.execute(
            "SELECT r.recipe_json FROM menu_courses c JOIN recipes r ON r.uuid = c.recipe_uuid "
            "WHERE c.menu_id = ?",
            (menu_id,),
        ).fetchall()
    finally:
        conn.close()

    raw: List[Ingredient] = []
    for row in rows:
        recipe = localize_recipe(_load_json(row["recipe_json"]), lang)
        factor = menu["guests"] / parse_servings(recipe.get("recipeYield"))
        for ing in recipe.get("ingredients") or []:
            if not isinstance(ing, dict):
                continue
            raw.append(
                Ingredient(
                    amount=scale_text(str(ing.get("amount") or ""), factor),
                    name=str(ing.get("name") or ""),
                )
            )

    merged = await run_in_threadpool(merge_ingredients, raw, lang)
    token = str(uuid_mod.uuid4())
    conn = db.get_db_connection()
    try:
        conn.execute(
            "INSERT INTO shopping_lists (token, user_id, items_json) VALUES (?, ?, ?)",
            (token, user_id, json.dumps([i.model_dump() for i in merged])),
        )
        conn.commit()
    finally:
        conn.close()
    return {"token": token, "items": [i.model_dump() for i in merged]}

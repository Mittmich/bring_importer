"""Weekly meal-plan endpoints.

- ``GET /meal-plan?start=&end=`` — auth; entries in a date range with recipe titles.
- ``POST /meal-plan`` — auth; assign a recipe to a day.
- ``PATCH /meal-plan/{id}`` — auth; move/reorder an entry.
- ``DELETE /meal-plan/{id}`` — auth; remove an entry.
- ``POST /meal-plan/shopping-list`` — auth; merge a week's ingredients, cache them,
  return a token + merged items for a Bring deeplink.
- ``GET /meal-plan/shopping-list/{token}.html`` — public; schema.org/Recipe HTML for Bring.
- ``POST /meal-plan/sync`` — auth; push the week's plan to Google Calendar (planner wins).
- ``POST /meal-plan/sync-status`` — auth; read-only per-entry sync state for the week.
"""

import json
import uuid as uuid_mod
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse

from api import google_calendar as gcal
from api.auth import get_current_user, get_user_id
from api.config import app_origin
from api.db import get_db_connection
from api.models import (
    DateRange,
    Ingredient,
    MealPlanEntry,
    MealPlanEntryCreate,
    MealPlanEntryUpdate,
    User,
)
from api.shopping_list import merge_ingredients

router = APIRouter(prefix="/meal-plan", tags=["meal-plan"])


def _require_user_id(current_user: User) -> int:
    user_id = get_user_id(current_user.email)
    if user_id is None:
        raise HTTPException(status_code=401, detail="Unknown user")
    return user_id


def _google_integration(user_id: int) -> Optional[Tuple[str, str]]:
    """Return ``(refresh_token, calendar_id)`` if the user has connected Google."""
    conn = get_db_connection()
    cursor = conn.cursor()
    row = cursor.execute(
        "SELECT refresh_token, calendar_id FROM google_integrations WHERE user_id = ?",
        (user_id,),
    ).fetchone()
    conn.close()
    if row is None:
        return None
    return row["refresh_token"], row["calendar_id"]


def _recipe_link(recipe_uuid: str) -> str:
    return f"{app_origin()}/recipes/{recipe_uuid}"


@router.get("", response_model=List[MealPlanEntry])
async def list_meal_plan(
    start: str,
    end: str,
    current_user: User = Depends(get_current_user),  # noqa: B008
):
    """Return the user's meal-plan entries in ``[start, end]`` (inclusive).

    Joined to ``recipes.title``; entries whose recipe was deleted are skipped.
    """
    user_id = _require_user_id(current_user)
    conn = get_db_connection()
    cursor = conn.cursor()
    rows = cursor.execute(
        "SELECT m.id, m.date, m.recipe_uuid, m.position, r.title AS recipe_title "
        "FROM meal_plan_entries m JOIN recipes r ON r.uuid = m.recipe_uuid "
        "WHERE m.user_id = ? AND m.date >= ? AND m.date <= ? "
        "ORDER BY m.date, m.position, m.id",
        (user_id, start, end),
    ).fetchall()
    conn.close()
    return [
        MealPlanEntry(
            id=row["id"],
            date=row["date"],
            recipe_uuid=row["recipe_uuid"],
            recipe_title=row["recipe_title"],
            position=row["position"],
        )
        for row in rows
    ]


@router.post("", response_model=MealPlanEntry)
async def add_meal_plan_entry(
    body: MealPlanEntryCreate,
    current_user: User = Depends(get_current_user),  # noqa: B008
):
    """Assign a recipe the user owns to a day, appended after that day's entries."""
    user_id = _require_user_id(current_user)
    conn = get_db_connection()
    cursor = conn.cursor()

    recipe = cursor.execute(
        "SELECT title, user_id FROM recipes WHERE uuid = ?",
        (body.recipe_uuid,),
    ).fetchone()
    if recipe is None or recipe["user_id"] != user_id:
        conn.close()
        raise HTTPException(status_code=404, detail="Recipe not found")

    next_pos = cursor.execute(
        "SELECT COALESCE(MAX(position), -1) + 1 AS pos FROM meal_plan_entries "
        "WHERE user_id = ? AND date = ?",
        (user_id, body.date),
    ).fetchone()["pos"]

    cursor.execute(
        "INSERT INTO meal_plan_entries (user_id, date, recipe_uuid, position) "
        "VALUES (?, ?, ?, ?)",
        (user_id, body.date, body.recipe_uuid, next_pos),
    )
    entry_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return MealPlanEntry(
        id=entry_id,
        date=body.date,
        recipe_uuid=body.recipe_uuid,
        recipe_title=recipe["title"],
        position=next_pos,
    )


@router.patch("/{entry_id}", status_code=204)
async def update_meal_plan_entry(
    entry_id: int,
    body: MealPlanEntryUpdate,
    current_user: User = Depends(get_current_user),  # noqa: B008
):
    """Move an entry to another day and/or change its position. 404 if not owned."""
    user_id = _require_user_id(current_user)
    conn = get_db_connection()
    cursor = conn.cursor()
    row = cursor.execute(
        "SELECT user_id FROM meal_plan_entries WHERE id = ?",
        (entry_id,),
    ).fetchone()
    if row is None or row["user_id"] != user_id:
        conn.close()
        raise HTTPException(status_code=404, detail="Entry not found")

    if body.date is not None:
        cursor.execute("UPDATE meal_plan_entries SET date = ? WHERE id = ?", (body.date, entry_id))
    if body.position is not None:
        cursor.execute(
            "UPDATE meal_plan_entries SET position = ? WHERE id = ?", (body.position, entry_id)
        )
    conn.commit()
    conn.close()
    return None


@router.delete("/{entry_id}", status_code=204)
async def delete_meal_plan_entry(
    entry_id: int,
    current_user: User = Depends(get_current_user),  # noqa: B008
):
    """Remove a meal-plan entry. 404 if it doesn't belong to the current user.

    If the entry was synced to Google Calendar, its event is deleted too so the
    calendar reflects the removal (best effort — failures don't block deletion).
    """
    user_id = _require_user_id(current_user)
    conn = get_db_connection()
    cursor = conn.cursor()
    row = cursor.execute(
        "SELECT user_id, google_event_id FROM meal_plan_entries WHERE id = ?",
        (entry_id,),
    ).fetchone()
    if row is None or row["user_id"] != user_id:
        conn.close()
        raise HTTPException(status_code=404, detail="Entry not found")
    cursor.execute("DELETE FROM meal_plan_entries WHERE id = ?", (entry_id,))
    conn.commit()
    conn.close()

    event_id = row["google_event_id"]
    if event_id:
        integration = _google_integration(user_id)
        if integration is not None:
            refresh_token, calendar_id = integration
            try:
                token = await gcal.refresh_access_token(refresh_token)
                await gcal.delete_event(token, calendar_id, event_id)
            except Exception:
                pass  # cleanup is best-effort; the entry is already gone
    return None


@router.post("/shopping-list")
async def build_shopping_list(
    body: DateRange,
    current_user: User = Depends(get_current_user),  # noqa: B008
):
    """Merge every ingredient in the week's recipes and cache the result.

    Returns ``{token, items}``. The frontend builds the Bring deeplink pointing
    at ``/meal-plan/shopping-list/{token}.html`` (it knows the public origin).
    """
    user_id = _require_user_id(current_user)
    conn = get_db_connection()
    cursor = conn.cursor()
    rows = cursor.execute(
        "SELECT r.recipe_json FROM meal_plan_entries m "
        "JOIN recipes r ON r.uuid = m.recipe_uuid "
        "WHERE m.user_id = ? AND m.date >= ? AND m.date <= ?",
        (user_id, body.start, body.end),
    ).fetchall()

    raw_items: List[Ingredient] = []
    for row in rows:
        try:
            data = json.loads(row["recipe_json"])
        except Exception:
            continue
        for ing in data.get("ingredients", []):
            raw_items.append(Ingredient(amount=ing.get("amount", ""), name=ing.get("name", "")))

    merged = merge_ingredients(raw_items)

    token = str(uuid_mod.uuid4())
    items_json = json.dumps([ing.model_dump() for ing in merged])
    cursor.execute(
        "INSERT INTO shopping_lists (token, user_id, items_json) VALUES (?, ?, ?)",
        (token, user_id, items_json),
    )
    conn.commit()
    conn.close()
    return {"token": token, "items": [ing.model_dump() for ing in merged]}


@router.get("/shopping-list/{token}.html", include_in_schema=False)
async def shopping_list_html(token: str):
    """Public schema.org/Recipe HTML page with the merged ingredients for Bring."""
    conn = get_db_connection()
    cursor = conn.cursor()
    row = cursor.execute(
        "SELECT items_json FROM shopping_lists WHERE token = ?",
        (token,),
    ).fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="Shopping list not found")

    items = json.loads(row["items_json"])
    ingredient_strings = [f"{i.get('amount', '')} {i.get('name', '')}".strip() for i in items]
    name = "Weekly Shopping List"

    jsonld: Dict[str, Any] = {
        "@context": "https://schema.org/",
        "@type": "Recipe",
        "name": name,
        "recipeIngredient": ingredient_strings,
        "recipeYield": "",
        "description": "Consolidated shopping list for the week's meal plan.",
    }
    html = (
        "<!DOCTYPE html>\n"
        '<html lang="en">\n'
        "<head>\n"
        '  <meta charset="UTF-8">\n'
        f"  <title>{name}</title>\n"
        '  <script type="application/ld+json">\n'
        f"  {json.dumps(jsonld, ensure_ascii=False)}\n"
        "  </script>\n"
        "</head>\n"
        "<body>\n"
        f"  <h1>{name}</h1>\n"
        "</body>\n"
        "</html>"
    )
    return HTMLResponse(content=html)


def _week_entries(cursor, user_id: int, start: str, end: str):
    """Entries (joined to recipe title) in ``[start, end]`` for a user."""
    return cursor.execute(
        "SELECT m.id, m.date, m.recipe_uuid, m.google_event_id, r.title AS recipe_title "
        "FROM meal_plan_entries m JOIN recipes r ON r.uuid = m.recipe_uuid "
        "WHERE m.user_id = ? AND m.date >= ? AND m.date <= ? "
        "ORDER BY m.date, m.position, m.id",
        (user_id, start, end),
    ).fetchall()


@router.post("/sync")
async def sync_to_calendar(
    body: DateRange,
    current_user: User = Depends(get_current_user),  # noqa: B008
):
    """Push the week's plan to Google Calendar — planner wins.

    For each entry in range: create an event if it has none, or recreate it if
    its stored event no longer exists in Google. Each event is all-day, titled
    with the recipe name, and links back to the recipe. Returns counts.
    """
    user_id = _require_user_id(current_user)
    integration = _google_integration(user_id)
    if integration is None:
        raise HTTPException(status_code=400, detail="Google Calendar not connected")
    refresh_token, calendar_id = integration
    token = await gcal.refresh_access_token(refresh_token)

    conn = get_db_connection()
    cursor = conn.cursor()
    rows = _week_entries(cursor, user_id, body.start, body.end)

    created = 0
    recreated = 0
    for row in rows:
        event_id = row["google_event_id"]
        needs_create = event_id is None
        if not needs_create:
            if not await gcal.event_exists(token, calendar_id, event_id):
                needs_create = True
                recreated += 1
        if needs_create:
            new_id = await gcal.insert_event(
                token,
                calendar_id,
                row["recipe_title"],
                row["date"],
                f"Recipe: {_recipe_link(row['recipe_uuid'])}",
            )
            cursor.execute(
                "UPDATE meal_plan_entries SET google_event_id = ? WHERE id = ?",
                (new_id, row["id"]),
            )
            if event_id is None:
                created += 1
    conn.commit()
    conn.close()
    return {"created": created, "recreated": recreated, "total": len(rows)}


@router.post("/sync-status")
async def sync_status(
    body: DateRange,
    current_user: User = Depends(get_current_user),  # noqa: B008
):
    """Read-only per-entry sync state for the week (no writes).

    Each entry is classified ``synced`` (event exists), ``missing`` (was synced
    but the event is gone), or ``unsynced`` (never synced). When Google isn't
    connected, every entry is ``unsynced``.
    """
    user_id = _require_user_id(current_user)
    conn = get_db_connection()
    cursor = conn.cursor()
    rows = _week_entries(cursor, user_id, body.start, body.end)
    conn.close()

    integration = _google_integration(user_id)
    if integration is None:
        return {
            "connected": False,
            "statuses": {str(row["id"]): "unsynced" for row in rows},
        }

    refresh_token, calendar_id = integration
    try:
        token = await gcal.refresh_access_token(refresh_token)
    except HTTPException as err:
        # This is a passive, background poll. If the Google authorization has
        # lapsed, degrade gracefully (entries shown as unsynced) and flag that a
        # reconnect is needed — never let it bubble up and error the page.
        if err.status_code == 409:
            return {
                "connected": True,
                "needs_reconnect": True,
                "statuses": {str(row["id"]): "unsynced" for row in rows},
            }
        raise

    statuses: Dict[str, str] = {}
    for row in rows:
        event_id = row["google_event_id"]
        if event_id is None:
            statuses[str(row["id"])] = "unsynced"
        elif await gcal.event_exists(token, calendar_id, event_id):
            statuses[str(row["id"])] = "synced"
        else:
            statuses[str(row["id"])] = "missing"
    return {"connected": True, "statuses": statuses}

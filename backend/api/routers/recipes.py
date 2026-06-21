"""Recipe endpoints.

- ``POST /recipes/parse`` — auth required; image → OpenAI → store → uuid.
- ``POST /recipes/import-url`` — auth required; URL → JSON-LD/OpenAI → store → uuid.
- ``GET /recipes`` — auth required; list the current user's recipes.
- ``PUT /recipes/{uuid}`` — auth required; edit structured fields.
- ``DELETE /recipes/{uuid}`` — auth required; 204 on success.
- ``GET /recipes/{uuid}.json`` — public; full recipe JSON.
- ``GET /recipes/{uuid}.html`` — public; schema.org/Recipe HTML page for Bring.
"""

import json
import re
import uuid as uuid_mod
from datetime import datetime
from typing import Any, Dict, List, Optional

import httpx
from fastapi import APIRouter, Depends, Form, HTTPException, Query
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

from api.auth import get_current_user, get_current_user_optional, get_user_id
from api.db import get_db_connection
from api.models import Ingredient, InstructionStep, Recipe, RecipeResponse, RecipeUpdate, User
from api.recipe_extraction import (
    USER_AGENT,
    extract_recipe_from_html_text,
    extract_recipe_from_jsonld,
    parse_recipe_with_openai,
)

# 5 MB is enough for any recipe page; bigger bodies are almost certainly a
# feed or wrapper page and not a single recipe.
MAX_FETCH_BYTES = 5 * 1024 * 1024
FETCH_TIMEOUT_SECONDS = 10.0

router = APIRouter(prefix="/recipes", tags=["recipes"])


def _store_recipe(
    recipe_uuid: str,
    user_id: int,
    recipe,
    source: Dict[str, str],
    note: str = "",
) -> None:
    """Persist a parsed recipe with the standard shape and metadata."""
    schema_recipe = {
        "@context": "https://schema.org/",
        "@type": "Recipe",
        "name": recipe.title,
        "ingredients": [ing.model_dump() for ing in recipe.ingredients],
        "instructions": [step.model_dump() for step in recipe.instructions],
        "recipeYield": recipe.recipeYield,
        "datePublished": recipe.datePublished,
        "description": recipe.description,
        "source": source,
        "note": note,
    }
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO recipes (uuid, user_id, title, recipe_json, note, source) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (
            recipe_uuid,
            user_id,
            recipe.title,
            json.dumps(schema_recipe),
            note,
            json.dumps(source),
        ),
    )
    conn.commit()
    conn.close()


@router.post("/parse", response_model=RecipeResponse)
async def parse_recipe(
    image: str = Form(...),
    current_user: User = Depends(get_current_user),  # noqa: B008
):
    try:
        recipe = parse_recipe_with_openai(image)
        recipe_uuid = str(uuid_mod.uuid4())
        user_id = get_user_id(current_user.email)
        if user_id is None:
            raise HTTPException(status_code=401, detail="Unknown user")
        _store_recipe(
            recipe_uuid=recipe_uuid,
            user_id=user_id,
            recipe=recipe,
            source={"kind": "image", "value": ""},
        )
        return RecipeResponse(uuid=recipe_uuid, url=f"/recipes/{recipe_uuid}.json")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error parsing recipe: {str(e)}") from e


class ImportURLBody(BaseModel):
    url: str
    note: Optional[str] = None


@router.post("/import-url", response_model=RecipeResponse)
async def import_url(
    body: ImportURLBody,
    current_user: User = Depends(get_current_user),  # noqa: B008
):
    """Import a recipe from a public URL.

    Flow:
      1. Server-side fetch with a real User-Agent (10 s timeout, 5 MB cap).
      2. Try JSON-LD extraction (covers ~3/5 of mainstream sites).
         On hit, uses two LLM calls to produce structured ingredients +
         instruction-ingredient mappings.
      3. Fall back to OpenAI structured-output text extraction.
      4. Store with ``source={"kind":"url","value":url}`` and return uuid.
    """
    user_id = get_user_id(current_user.email)
    if user_id is None:
        raise HTTPException(status_code=401, detail="Unknown user")

    url = body.url.strip()
    if not url:
        raise HTTPException(status_code=422, detail="URL is required")

    # 1. Fetch.
    try:
        async with httpx.AsyncClient(
            timeout=FETCH_TIMEOUT_SECONDS,
            follow_redirects=True,
            headers={"User-Agent": USER_AGENT, "Accept": "text/html,*/*"},
        ) as client:
            response = await client.get(url)
            response.raise_for_status()
    except httpx.HTTPStatusError as e:
        raise HTTPException(
            status_code=422,
            detail=f"The page at that URL returned HTTP {e.response.status_code}.",
        ) from e
    except httpx.RequestError as e:
        raise HTTPException(
            status_code=422,
            detail=f"Couldn't fetch that URL ({type(e).__name__}). Check the link and try again.",
        ) from e

    if len(response.content) > MAX_FETCH_BYTES:
        raise HTTPException(
            status_code=422,
            detail="The page is too large to import (>5 MB).",
        )

    html_body = response.text

    # 2. JSON-LD first.
    recipe = None
    for match in re.finditer(
        r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        html_body,
        re.IGNORECASE | re.DOTALL,
    ):
        raw = match.group(1).strip()
        if raw.endswith(";"):
            raw = raw[:-1]
        try:
            obj = json.loads(raw)
        except json.JSONDecodeError:
            continue
        recipe = extract_recipe_from_jsonld(obj)
        if recipe is not None:
            break

    # 3. OpenAI text fallback.
    if recipe is None:
        try:
            recipe = extract_recipe_from_html_text(html_body, source_url=url)
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to parse recipe from URL: {e}",
            ) from e

    # 4. Store.
    recipe_uuid = str(uuid_mod.uuid4())
    _store_recipe(
        recipe_uuid=recipe_uuid,
        user_id=user_id,
        recipe=recipe,
        source={"kind": "url", "value": url},
        note=body.note or "",
    )
    return RecipeResponse(uuid=recipe_uuid, url=f"/recipes/{recipe_uuid}.json")


@router.get("/{recipe_uuid}.json", include_in_schema=False)
async def get_recipe(
    recipe_uuid: str,
    current_user: Optional[User] = Depends(get_current_user_optional),  # noqa: B008
):
    """Return recipe JSON if the recipe is public or the requester is the owner."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT recipe_json, is_public, user_id FROM recipes WHERE uuid = ?",
        (recipe_uuid,),
    )
    row = cursor.fetchone()

    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Recipe not found")

    is_public = bool(row["is_public"])
    owner_id = get_user_id(current_user.email) if current_user else None
    owned = owner_id is not None and owner_id == row["user_id"]
    if not is_public and not owned:
        conn.close()
        raise HTTPException(status_code=404, detail="Recipe not found")

    data = json.loads(row["recipe_json"])
    data["is_public"] = is_public
    # Lets the public share page tell whether the viewer owns this recipe
    # without fetching their whole recipe list.
    data["owned"] = owned
    data["tags"] = _tags_for(cursor, [recipe_uuid]).get(recipe_uuid, [])
    conn.close()
    return JSONResponse(content=data)


def _ingredient_string(ing: Dict[str, Any]) -> str:
    """Format a structured ingredient dict as a flat string for Bring."""
    amount = ing.get("amount", "")
    name = ing.get("name", "")
    return f"{amount} {name}".strip()


@router.get("/{recipe_uuid}.html", include_in_schema=False)
async def get_recipe_html(recipe_uuid: str):
    """HTML page with embedded JSON-LD for Bring and other recipe parsers.

    Converts the new structured {ingredients, instructions} format into the
    flat schema.org/Recipe arrays (recipeIngredient: string[],
    recipeInstructions: HowToStep[]) that Bring's deeplink API expects.

    Also handles old-format recipes (recipeIngredient: string[]) so the
    endpoint keeps working before the migration script is run.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT recipe_json FROM recipes WHERE uuid = ?", (recipe_uuid,))
    row = cursor.fetchone()
    conn.close()

    if not row:
        raise HTTPException(status_code=404, detail="Recipe not found")

    data = json.loads(row["recipe_json"])
    name = data.get("name", "Recipe")

    # Support both new format (ingredients list of dicts) and old (flat strings).
    if "ingredients" in data:
        ingredient_strings = [_ingredient_string(ing) for ing in data["ingredients"]]
        instruction_texts = [s.get("text", "") for s in data.get("instructions", [])]
    else:
        ingredient_strings = data.get("recipeIngredient") or []
        instruction_texts = data.get("recipeInstructions") or []

    jsonld: Dict[str, Any] = {
        "@context": "https://schema.org/",
        "@type": "Recipe",
        "name": name,
        "recipeIngredient": ingredient_strings,
        "recipeYield": data.get("recipeYield") or "",
        "description": data.get("description") or "",
    }
    if instruction_texts:
        jsonld["recipeInstructions"] = [
            {"@type": "HowToStep", "text": text} for text in instruction_texts
        ]

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


def _normalize_tag(name: str) -> str:
    """Trim and collapse internal whitespace; preserves the display casing."""
    return " ".join(name.split())


def _set_recipe_tags(cursor, user_id: int, recipe_uuid: str, names: List[str]) -> None:
    """Replace a recipe's tag set, creating any new tags for the user.

    De-dupes case-insensitively, keeping the first-seen display form.
    """
    seen: Dict[str, str] = {}
    for raw in names:
        n = _normalize_tag(raw)
        if n and n.lower() not in seen:
            seen[n.lower()] = n

    cursor.execute("DELETE FROM recipe_tags WHERE recipe_uuid = ?", (recipe_uuid,))
    for display in seen.values():
        cursor.execute(
            "INSERT INTO tags (user_id, name) VALUES (?, ?) ON CONFLICT DO NOTHING",
            (user_id, display),
        )
        tag_id = cursor.execute(
            "SELECT id FROM tags WHERE user_id = ? AND name = ? COLLATE NOCASE",
            (user_id, display),
        ).fetchone()["id"]
        cursor.execute(
            "INSERT OR IGNORE INTO recipe_tags (recipe_uuid, tag_id) VALUES (?, ?)",
            (recipe_uuid, tag_id),
        )


def _tags_for(cursor, recipe_uuids: List[str]) -> Dict[str, List[str]]:
    """Map each recipe uuid to its sorted list of tag names."""
    if not recipe_uuids:
        return {}
    placeholders = ",".join("?" * len(recipe_uuids))
    rows = cursor.execute(
        f"SELECT rt.recipe_uuid AS uuid, t.name AS name FROM recipe_tags rt "
        f"JOIN tags t ON t.id = rt.tag_id WHERE rt.recipe_uuid IN ({placeholders}) "
        "ORDER BY t.name COLLATE NOCASE",
        recipe_uuids,
    ).fetchall()
    out: Dict[str, List[str]] = {}
    for r in rows:
        out.setdefault(r["uuid"], []).append(r["name"])
    return out


@router.get("/tags", include_in_schema=False)
async def list_tags(current_user: User = Depends(get_current_user)):  # noqa: B008
    """Return the current user's in-use tags with usage counts, name-sorted."""
    user_id = get_user_id(current_user.email)
    if user_id is None:
        return []
    conn = get_db_connection()
    cursor = conn.cursor()
    rows = cursor.execute(
        "SELECT t.name AS name, COUNT(rt.recipe_uuid) AS count FROM tags t "
        "JOIN recipe_tags rt ON rt.tag_id = t.id WHERE t.user_id = ? "
        "GROUP BY t.id HAVING count > 0 ORDER BY t.name COLLATE NOCASE",
        (user_id,),
    ).fetchall()
    conn.close()
    return [{"name": r["name"], "count": r["count"]} for r in rows]


@router.get("")
async def list_recipes(
    limit: int = 30,
    offset: int = 0,
    q: Optional[str] = None,
    tag: Optional[List[str]] = Query(default=None),  # noqa: B008
    current_user: User = Depends(get_current_user),  # noqa: B008
):
    """Return a page of the current user's recipes, newest first.

    Response envelope: ``{items, total, limit, offset}``. ``q`` filters by title
    (case-insensitive substring). ``limit`` is clamped to 1..100.
    """
    user_id = get_user_id(current_user.email)
    if user_id is None:
        return {"items": [], "total": 0, "limit": limit, "offset": offset}

    limit = max(1, min(limit, 100))
    offset = max(0, offset)

    where = "WHERE user_id = ?"
    params: List[Any] = [user_id]
    if q:
        where += " AND LOWER(title) LIKE ?"
        params.append(f"%{q.lower()}%")

    # Tag filter (AND): the recipe must carry every named tag.
    tags_norm = sorted({t.strip().lower() for t in (tag or []) if t.strip()})
    if tags_norm:
        placeholders = ",".join("?" * len(tags_norm))
        where += (
            f" AND uuid IN (SELECT rt.recipe_uuid FROM recipe_tags rt "
            f"JOIN tags t ON t.id = rt.tag_id WHERE LOWER(t.name) IN ({placeholders}) "
            f"GROUP BY rt.recipe_uuid HAVING COUNT(DISTINCT LOWER(t.name)) = ?)"
        )
        params.extend([*tags_norm, len(tags_norm)])

    conn = get_db_connection()
    cursor = conn.cursor()
    total = cursor.execute(f"SELECT COUNT(*) AS c FROM recipes {where}", params).fetchone()["c"]
    rows = cursor.execute(
        f"SELECT uuid, title, recipe_json, created_at, is_public FROM recipes {where} "
        "ORDER BY created_at DESC LIMIT ? OFFSET ?",
        (*params, limit, offset),
    ).fetchall()

    tag_map = _tags_for(cursor, [row["uuid"] for row in rows])
    conn.close()

    items: List[Dict[str, Any]] = []
    for row in rows:
        try:
            recipe_json = json.loads(row["recipe_json"])
        except Exception:
            recipe_json = {}
        source = recipe_json.get("source") or {"kind": "unknown", "value": ""}
        items.append(
            {
                "uuid": row["uuid"],
                "title": row["title"],
                "datePublished": recipe_json.get("datePublished"),
                "createdAt": row["created_at"],
                "source": source,
                "is_public": bool(row["is_public"]),
                "tags": tag_map.get(row["uuid"], []),
            }
        )
    return {"items": items, "total": total, "limit": limit, "offset": offset}


@router.put("/{recipe_uuid}")
async def update_recipe(
    recipe_uuid: str,
    body: RecipeUpdate,
    current_user: User = Depends(get_current_user),  # noqa: B008
):
    """Update the structured fields of a recipe owned by the current user.

    Returns 404 (not 403) when the recipe exists but is owned by another
    user, so an attacker can't probe for valid UUIDs.

    Accepts the new structured ``ingredients`` and ``instructions`` fields.
    The ``instructions`` field carries full ``InstructionStep`` objects so
    the caller can edit both step text and ingredient-index mappings in one
    PUT.
    """
    user_id = get_user_id(current_user.email)
    if user_id is None:
        raise HTTPException(status_code=401, detail="Unknown user")

    conn = get_db_connection()
    cursor = conn.cursor()
    row = cursor.execute(
        "SELECT user_id, recipe_json, note, source, is_public FROM recipes WHERE uuid = ?",
        (recipe_uuid,),
    ).fetchone()
    if row is None or row["user_id"] != user_id:
        conn.close()
        raise HTTPException(status_code=404, detail="Recipe not found")

    try:
        stored = json.loads(row["recipe_json"])
    except Exception:
        stored = {}

    if body.title is not None:
        stored["name"] = body.title
    if body.recipeYield is not None:
        stored["recipeYield"] = body.recipeYield
    if body.description is not None:
        stored["description"] = body.description
    if body.note is not None:
        stored["note"] = body.note
    if body.ingredients is not None:
        stored["ingredients"] = [ing.model_dump() for ing in body.ingredients]
        # Remove old-format key if present
        stored.pop("recipeIngredient", None)
    if body.instructions is not None:
        stored["instructions"] = [step.model_dump() for step in body.instructions]
        stored.pop("recipeInstructions", None)

    new_title = stored.get("name", "")
    new_note = stored.get("note", "")
    new_is_public = int(body.is_public) if body.is_public is not None else int(row["is_public"])

    cursor.execute(
        "UPDATE recipes SET title = ?, recipe_json = ?, note = ?, "
        "is_public = ?, updated_at = CURRENT_TIMESTAMP WHERE uuid = ?",
        (new_title, json.dumps(stored), new_note, new_is_public, recipe_uuid),
    )
    if body.tags is not None:
        _set_recipe_tags(cursor, user_id, recipe_uuid, body.tags)
    conn.commit()

    stored["is_public"] = bool(new_is_public)
    stored["tags"] = _tags_for(cursor, [recipe_uuid]).get(recipe_uuid, [])
    conn.close()
    return JSONResponse(content=stored)


@router.post("/{recipe_uuid}/clone", response_model=RecipeResponse)
async def clone_recipe(
    recipe_uuid: str,
    current_user: User = Depends(get_current_user),  # noqa: B008
):
    """Clone a public recipe into the current user's collection.

    Returns 404 if the recipe doesn't exist or is not public.
    """
    user_id = get_user_id(current_user.email)
    if user_id is None:
        raise HTTPException(status_code=401, detail="Unknown user")

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT recipe_json, source, is_public FROM recipes WHERE uuid = ?",
        (recipe_uuid,),
    )
    row = cursor.fetchone()
    conn.close()

    if not row or not row["is_public"]:
        raise HTTPException(status_code=404, detail="Recipe not found or not public")

    data = json.loads(row["recipe_json"])
    source = json.loads(row["source"]) if row["source"] else {"kind": "shared", "value": ""}

    recipe = Recipe(
        title=data.get("name", "Untitled"),
        ingredients=[Ingredient(**ing) for ing in data.get("ingredients", [])],
        instructions=[InstructionStep(**step) for step in data.get("instructions", [])],
        recipeYield=data.get("recipeYield", "4 servings"),
        description=data.get("description"),
        datePublished=datetime.now().strftime("%Y-%m-%d"),
    )
    new_uuid = str(uuid_mod.uuid4())
    _store_recipe(recipe_uuid=new_uuid, user_id=user_id, recipe=recipe, source=source)
    return RecipeResponse(uuid=new_uuid, url=f"/recipes/{new_uuid}.json")


@router.delete("/{recipe_uuid}", status_code=204)
async def delete_recipe(
    recipe_uuid: str,
    current_user: User = Depends(get_current_user),  # noqa: B008
):
    """Delete a recipe owned by the current user.

    Returns 204 on success, 404 (not 403) if the recipe doesn't belong
    to the current user. After deletion, public endpoints for that UUID
    will 404.
    """
    user_id = get_user_id(current_user.email)
    if user_id is None:
        raise HTTPException(status_code=401, detail="Unknown user")

    conn = get_db_connection()
    cursor = conn.cursor()
    row = cursor.execute("SELECT user_id FROM recipes WHERE uuid = ?", (recipe_uuid,)).fetchone()
    if row is None or row["user_id"] != user_id:
        conn.close()
        raise HTTPException(status_code=404, detail="Recipe not found")

    cursor.execute("DELETE FROM recipe_tags WHERE recipe_uuid = ?", (recipe_uuid,))
    cursor.execute("DELETE FROM recipes WHERE uuid = ?", (recipe_uuid,))
    conn.commit()
    conn.close()
    return None

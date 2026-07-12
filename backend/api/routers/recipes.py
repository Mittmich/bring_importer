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
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from urllib.parse import quote_plus

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, Form, HTTPException, Query
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from pydantic import BaseModel

from api import recipe_images
from api.access import effective_role, role_at_least
from api.auth import get_current_user, get_current_user_optional, get_user_id
from api.data_collection import collect_image_extraction
from api.db import get_db_connection
from api.models import (
    Ingredient,
    InstructionStep,
    Recipe,
    RecipeResponse,
    RecipeUpdate,
    Tag,
    TagUpdate,
    User,
)
from api.recipe_extraction import (
    IMAGE_MODEL,
    IMAGE_PROMPT_VERSION,
    USER_AGENT,
    extract_recipe_from_html_text,
    extract_recipe_from_jsonld,
    parse_recipe_with_openai,
)
from api.search import match_score, recipe_haystack

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
    background_tasks: BackgroundTasks,
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
        # Opt-in: stash the image + raw extraction for the eval dataset. Runs
        # after the response so it never adds latency to the import.
        background_tasks.add_task(
            collect_image_extraction,
            recipe_uuid,
            image,
            recipe,
            IMAGE_MODEL,
            IMAGE_PROMPT_VERSION,
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


def _image_url(recipe_uuid: str, has_image: bool, version: Any) -> Optional[str]:
    """Public URL for a recipe's hero image, or None when there isn't one.

    A ``?v=`` cache-buster derived from the recipe's ``updated_at`` makes the
    browser refetch after the image is replaced, while still allowing long
    caching between edits.
    """
    if not has_image:
        return None
    suffix = f"?v={quote_plus(str(version))}" if version else ""
    return f"/recipes/{recipe_uuid}/image{suffix}"


@router.get("/{recipe_uuid}.json", include_in_schema=False)
async def get_recipe(
    recipe_uuid: str,
    current_user: Optional[User] = Depends(get_current_user_optional),  # noqa: B008
):
    """Return recipe JSON if the recipe is public, owned, or shared with the requester."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT recipe_json, is_public, user_id, training_verified, has_image, updated_at "
        "FROM recipes WHERE uuid = ?",
        (recipe_uuid,),
    )
    row = cursor.fetchone()

    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Recipe not found")

    is_public = bool(row["is_public"])
    owner_id = get_user_id(current_user.email) if current_user else None
    owned = owner_id is not None and owner_id == row["user_id"]
    role = effective_role(cursor, owner_id, recipe_uuid) if owner_id is not None else "none"
    if not is_public and not role_at_least(role, "viewer"):
        conn.close()
        raise HTTPException(status_code=404, detail="Recipe not found")

    data = json.loads(row["recipe_json"])
    data["is_public"] = is_public
    # Lets the public share page tell whether the viewer owns this recipe
    # without fetching their whole recipe list.
    data["owned"] = owned
    # The viewer's role, so the client can gate edit controls on shared recipes.
    data["role"] = role
    # Who owns it (for "shared by …" labels) and the version for edit-conflict checks.
    owner = cursor.execute(
        "SELECT email, display_name FROM users WHERE id = ?", (row["user_id"],)
    ).fetchone()
    data["owner_email"] = owner["email"] if owner else None
    data["owner_name"] = (
        ((owner["display_name"] or "").strip() or owner["email"]) if owner else None
    )
    data["updated_at"] = row["updated_at"]
    data["training_verified"] = bool(row["training_verified"])
    data["has_image"] = bool(row["has_image"])
    data["image_url"] = _image_url(recipe_uuid, bool(row["has_image"]), row["updated_at"])
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


def _tags_for(cursor, recipe_uuids: List[str]) -> Dict[str, List[Dict[str, Any]]]:
    """Map each recipe uuid to its sorted list of ``{name, color}`` tags."""
    if not recipe_uuids:
        return {}
    placeholders = ",".join("?" * len(recipe_uuids))
    rows = cursor.execute(
        f"SELECT rt.recipe_uuid AS uuid, t.name AS name, t.color AS color FROM recipe_tags rt "
        f"JOIN tags t ON t.id = rt.tag_id WHERE rt.recipe_uuid IN ({placeholders}) "
        "ORDER BY t.name COLLATE NOCASE",
        recipe_uuids,
    ).fetchall()
    out: Dict[str, List[Dict[str, Any]]] = {}
    for r in rows:
        out.setdefault(r["uuid"], []).append({"name": r["name"], "color": r["color"]})
    return out


@router.get("/tags", include_in_schema=False, response_model=List[Tag])
async def list_tags(
    scope: str = Query("mine"),
    current_user: User = Depends(get_current_user),  # noqa: B008
):
    """List tags with usage counts, name-sorted.

    - ``scope=mine`` (default): the current user's own tags, including orphaned
      (zero-use) ones — the tag-management page needs to clean those up.
    - ``scope=filter``: distinct tag names appearing on any recipe accessible to
      the user (own **or** shared), aggregated by name, counted over accessible
      recipes — this is what the search bar's tag filter offers, so shared
      recipes' tags are selectable too.
    """
    user_id = get_user_id(current_user.email)
    if user_id is None:
        return []
    conn = get_db_connection()
    cursor = conn.cursor()

    if scope == "filter":
        rows = cursor.execute(
            "SELECT MIN(t.id) AS id, MIN(t.name) AS name, MAX(t.color) AS color, "
            "COUNT(DISTINCT r.uuid) AS count "
            "FROM recipe_tags rt JOIN tags t ON t.id = rt.tag_id "
            "JOIN recipes r ON r.uuid = rt.recipe_uuid "
            "WHERE (r.user_id = ? OR r.uuid IN ("
            "SELECT cr.recipe_uuid FROM cookbook_recipes cr "
            "JOIN cookbooks c ON c.id = cr.cookbook_id "
            "LEFT JOIN cookbook_members m ON m.cookbook_id = c.id AND m.user_id = ? "
            "AND m.status = 'accepted' WHERE c.owner_id = ? OR m.user_id IS NOT NULL)) "
            "GROUP BY LOWER(t.name) ORDER BY name COLLATE NOCASE",
            (user_id, user_id, user_id),
        ).fetchall()
    else:
        rows = cursor.execute(
            "SELECT t.id AS id, t.name AS name, t.color AS color, "
            "COUNT(rt.recipe_uuid) AS count FROM tags t "
            "LEFT JOIN recipe_tags rt ON rt.tag_id = t.id WHERE t.user_id = ? "
            "GROUP BY t.id ORDER BY t.name COLLATE NOCASE",
            (user_id,),
        ).fetchall()
    conn.close()
    return [
        {"id": r["id"], "name": r["name"], "count": r["count"], "color": r["color"]} for r in rows
    ]


@router.patch("/tags/{tag_id}", include_in_schema=False, response_model=Tag)
async def update_tag(
    tag_id: int,
    body: TagUpdate,
    current_user: User = Depends(get_current_user),  # noqa: B008
):
    """Rename and/or recolour one of the current user's tags.

    Returns 404 if the tag isn't owned by the user, 409 if a rename would
    collide (case-insensitively) with another of the user's tags.
    """
    user_id = get_user_id(current_user.email)
    if user_id is None:
        raise HTTPException(status_code=401, detail="Unknown user")

    conn = get_db_connection()
    cursor = conn.cursor()
    row = cursor.execute(
        "SELECT id, user_id, name, color FROM tags WHERE id = ?", (tag_id,)
    ).fetchone()
    if row is None or row["user_id"] != user_id:
        conn.close()
        raise HTTPException(status_code=404, detail="Tag not found")

    new_name = row["name"]
    if body.name is not None:
        new_name = _normalize_tag(body.name)
        if not new_name:
            conn.close()
            raise HTTPException(status_code=422, detail="Tag name cannot be empty")
        clash = cursor.execute(
            "SELECT id FROM tags WHERE user_id = ? AND name = ? COLLATE NOCASE AND id != ?",
            (user_id, new_name, tag_id),
        ).fetchone()
        if clash is not None:
            conn.close()
            raise HTTPException(status_code=409, detail="A tag with that name already exists")

    new_color = body.color if body.color is not None else row["color"]
    cursor.execute(
        "UPDATE tags SET name = ?, color = ? WHERE id = ?",
        (new_name, new_color, tag_id),
    )
    count = cursor.execute(
        "SELECT COUNT(*) AS c FROM recipe_tags WHERE tag_id = ?", (tag_id,)
    ).fetchone()["c"]
    conn.commit()
    conn.close()
    return {"id": tag_id, "name": new_name, "count": count, "color": new_color}


@router.delete("/tags/{tag_id}", include_in_schema=False, status_code=204)
async def delete_tag(
    tag_id: int,
    current_user: User = Depends(get_current_user),  # noqa: B008
):
    """Delete one of the current user's tags and detach it from all recipes."""
    user_id = get_user_id(current_user.email)
    if user_id is None:
        raise HTTPException(status_code=401, detail="Unknown user")

    conn = get_db_connection()
    cursor = conn.cursor()
    row = cursor.execute("SELECT user_id FROM tags WHERE id = ?", (tag_id,)).fetchone()
    if row is None or row["user_id"] != user_id:
        conn.close()
        raise HTTPException(status_code=404, detail="Tag not found")

    cursor.execute("DELETE FROM recipe_tags WHERE tag_id = ?", (tag_id,))
    cursor.execute("DELETE FROM tags WHERE id = ?", (tag_id,))
    conn.commit()
    conn.close()
    return None


def _list_item(row, tag_map: Dict[str, List[Dict[str, Any]]], me: int) -> Dict[str, Any]:
    """Shape a recipes row into a list item for the ``GET /recipes`` envelope.

    ``row`` must carry ``owner_id`` and ``owner_email`` so shared recipes can show
    who they belong to. ``me`` is the requesting user, used to set ``owned``.
    """
    try:
        recipe_json = json.loads(row["recipe_json"])
    except Exception:
        recipe_json = {}
    source = recipe_json.get("source") or {"kind": "unknown", "value": ""}
    has_image = bool(row["has_image"])
    owner_id = row["owner_id"]
    return {
        "uuid": row["uuid"],
        "title": row["title"],
        "datePublished": recipe_json.get("datePublished"),
        "createdAt": row["created_at"],
        "source": source,
        "is_public": bool(row["is_public"]),
        "has_image": has_image,
        "image_url": _image_url(row["uuid"], has_image, row["updated_at"]),
        "tags": tag_map.get(row["uuid"], []),
        "owned": owner_id == me,
        "owner_email": row["owner_email"],
        "owner_name": (row["owner_display_name"] or "").strip() or row["owner_email"],
    }


@router.get("")
async def list_recipes(
    limit: int = 30,
    offset: int = 0,
    q: Optional[str] = None,
    tag: Optional[List[str]] = Query(default=None),  # noqa: B008
    current_user: User = Depends(get_current_user),  # noqa: B008
):
    """Return a page of recipes accessible to the current user.

    Includes the user's own recipes **and** recipes reachable through a shared
    cookbook (owned or accepted membership), so shared recipes surface
    everywhere, each tagged with its ``owner_email``/``owned``. Envelope:
    ``{items, total, limit, offset}``. ``limit`` clamps to 1..100. Without ``q``,
    newest-first; with ``q``, a fuzzy full-recipe search ranked by score.
    """
    user_id = get_user_id(current_user.email)
    if user_id is None:
        return {"items": [], "total": 0, "limit": limit, "offset": offset}

    limit = max(1, min(limit, 100))
    offset = max(0, offset)

    # Accessible = own it, or it's in a cookbook I own or am an accepted member of.
    where = (
        "WHERE (r.user_id = ? OR r.uuid IN ("
        "SELECT cr.recipe_uuid FROM cookbook_recipes cr "
        "JOIN cookbooks c ON c.id = cr.cookbook_id "
        "LEFT JOIN cookbook_members m ON m.cookbook_id = c.id AND m.user_id = ? "
        "AND m.status = 'accepted' "
        "WHERE c.owner_id = ? OR m.user_id IS NOT NULL))"
    )
    params: List[Any] = [user_id, user_id, user_id]

    # Tag filter (AND): the recipe must carry every named tag.
    tags_norm = sorted({t.strip().lower() for t in (tag or []) if t.strip()})
    if tags_norm:
        placeholders = ",".join("?" * len(tags_norm))
        where += (
            f" AND r.uuid IN (SELECT rt.recipe_uuid FROM recipe_tags rt "
            f"JOIN tags t ON t.id = rt.tag_id WHERE LOWER(t.name) IN ({placeholders}) "
            f"GROUP BY rt.recipe_uuid HAVING COUNT(DISTINCT LOWER(t.name)) = ?)"
        )
        params.extend([*tags_norm, len(tags_norm)])

    select_cols = (
        "SELECT r.uuid AS uuid, r.title AS title, r.recipe_json AS recipe_json, "
        "r.created_at AS created_at, r.updated_at AS updated_at, r.is_public AS is_public, "
        "r.has_image AS has_image, r.user_id AS owner_id, uo.email AS owner_email, "
        "uo.display_name AS owner_display_name "
        f"FROM recipes r JOIN users uo ON uo.id = r.user_id {where} "
    )

    conn = get_db_connection()
    cursor = conn.cursor()

    query = (q or "").strip()
    if query:
        # Fuzzy full-recipe search. Load the tag-filtered candidates, score each
        # against the query over all its text, keep the matches, rank by score
        # (newest first as a tiebreak), then paginate in memory. Fine at a
        # personal collection's scale; avoids maintaining an FTS index.
        candidates = cursor.execute(select_cols, params).fetchall()
        cand_tag_map = _tags_for(cursor, [r["uuid"] for r in candidates])
        scored = []
        for row in candidates:
            try:
                recipe_json = json.loads(row["recipe_json"])
            except Exception:
                recipe_json = {}
            tag_names = [t["name"] for t in cand_tag_map.get(row["uuid"], [])]
            score = match_score(query, recipe_haystack(recipe_json, tag_names))
            if score > 0:
                scored.append((score, row["created_at"] or "", row))
        scored.sort(key=lambda s: (s[0], s[1]), reverse=True)
        total = len(scored)
        page_rows = [s[2] for s in scored[offset : offset + limit]]
        tag_map = cand_tag_map
    else:
        total = cursor.execute(f"SELECT COUNT(*) AS c FROM recipes r {where}", params).fetchone()[
            "c"
        ]
        page_rows = cursor.execute(
            select_cols + "ORDER BY r.created_at DESC LIMIT ? OFFSET ?",
            (*params, limit, offset),
        ).fetchall()
        tag_map = _tags_for(cursor, [row["uuid"] for row in page_rows])

    conn.close()

    items = [_list_item(row, tag_map, user_id) for row in page_rows]
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
        "SELECT user_id, recipe_json, note, source, is_public, training_verified, updated_at "
        "FROM recipes WHERE uuid = ?",
        (recipe_uuid,),
    ).fetchone()
    # Editors (own the recipe, or have editor+ via a shared cookbook) may change
    # content. Owner-only fields (sharing flag, verification, tags) are ignored
    # for non-owners.
    role = effective_role(cursor, user_id, recipe_uuid)
    if row is None or not role_at_least(role, "editor"):
        conn.close()
        raise HTTPException(status_code=404, detail="Recipe not found")
    is_owner = role == "owner"

    # Optimistic concurrency: reject if the recipe changed since the client loaded it.
    if body.base_updated_at is not None and row["updated_at"] != body.base_updated_at:
        conn.close()
        raise HTTPException(
            status_code=409,
            detail="This recipe was changed since you opened it. Reload and try again.",
        )

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
    # Sharing flag and verification are the owner's call only.
    new_is_public = (
        int(body.is_public) if (body.is_public is not None and is_owner) else int(row["is_public"])
    )
    new_verified = (
        int(body.training_verified)
        if (body.training_verified is not None and is_owner)
        else int(row["training_verified"])
    )

    # Microsecond-precision timestamp so consecutive edits always differ — the
    # basis for the optimistic-concurrency check above (SQLite's CURRENT_TIMESTAMP
    # is only second-resolution).
    new_updated = datetime.now(timezone.utc).isoformat()
    cursor.execute(
        "UPDATE recipes SET title = ?, recipe_json = ?, note = ?, "
        "is_public = ?, training_verified = ?, updated_at = ? WHERE uuid = ?",
        (
            new_title,
            json.dumps(stored),
            new_note,
            new_is_public,
            new_verified,
            new_updated,
            recipe_uuid,
        ),
    )
    # A recipe's tags live in the owner's namespace and follow the recipe's own
    # permissions: anyone who can edit the recipe (editor+) can edit its tags.
    if body.tags is not None:
        _set_recipe_tags(cursor, row["user_id"], recipe_uuid, body.tags)
    conn.commit()

    stored["is_public"] = bool(new_is_public)
    stored["training_verified"] = bool(new_verified)
    stored["updated_at"] = new_updated
    stored["tags"] = _tags_for(cursor, [recipe_uuid]).get(recipe_uuid, [])
    conn.close()
    return JSONResponse(content=stored)


class RecipeImageBody(BaseModel):
    image: str  # base64-encoded JPEG (optionally a data URL)


@router.put("/{recipe_uuid}/image", include_in_schema=False)
async def set_recipe_image(
    recipe_uuid: str,
    body: RecipeImageBody,
    current_user: User = Depends(get_current_user),  # noqa: B008
):
    """Store (or replace) the hero image for a recipe owned by the current user.

    The client sends an already-cropped, downscaled JPEG. Bumps ``updated_at``
    so the image URL's cache-buster changes and viewers refetch.
    """
    user_id = get_user_id(current_user.email)
    if user_id is None:
        raise HTTPException(status_code=401, detail="Unknown user")

    conn = get_db_connection()
    cursor = conn.cursor()
    row = cursor.execute("SELECT user_id FROM recipes WHERE uuid = ?", (recipe_uuid,)).fetchone()
    if row is None or not role_at_least(effective_role(cursor, user_id, recipe_uuid), "editor"):
        conn.close()
        raise HTTPException(status_code=404, detail="Recipe not found")

    try:
        raw = recipe_images.decode_image(body.image)
    except ValueError as e:
        conn.close()
        raise HTTPException(status_code=422, detail=str(e)) from e

    recipe_images.save_image(recipe_uuid, raw)
    cursor.execute(
        "UPDATE recipes SET has_image = 1, updated_at = CURRENT_TIMESTAMP WHERE uuid = ?",
        (recipe_uuid,),
    )
    updated_at = cursor.execute(
        "SELECT updated_at FROM recipes WHERE uuid = ?", (recipe_uuid,)
    ).fetchone()["updated_at"]
    conn.commit()
    conn.close()
    return {"has_image": True, "image_url": _image_url(recipe_uuid, True, updated_at)}


@router.delete("/{recipe_uuid}/image", include_in_schema=False, status_code=204)
async def delete_recipe_image(
    recipe_uuid: str,
    current_user: User = Depends(get_current_user),  # noqa: B008
):
    """Remove the hero image from a recipe (owner or an editor via a shared cookbook)."""
    user_id = get_user_id(current_user.email)
    if user_id is None:
        raise HTTPException(status_code=401, detail="Unknown user")

    conn = get_db_connection()
    cursor = conn.cursor()
    row = cursor.execute("SELECT user_id FROM recipes WHERE uuid = ?", (recipe_uuid,)).fetchone()
    if row is None or not role_at_least(effective_role(cursor, user_id, recipe_uuid), "editor"):
        conn.close()
        raise HTTPException(status_code=404, detail="Recipe not found")

    recipe_images.delete_image(recipe_uuid)
    cursor.execute(
        "UPDATE recipes SET has_image = 0, updated_at = CURRENT_TIMESTAMP WHERE uuid = ?",
        (recipe_uuid,),
    )
    conn.commit()
    conn.close()
    return None


@router.get("/{recipe_uuid}/image", include_in_schema=False)
async def get_recipe_image(
    recipe_uuid: str,
    current_user: Optional[User] = Depends(get_current_user_optional),  # noqa: B008
):
    """Serve a recipe's hero image if the recipe is public or the requester owns it.

    404s (rather than 403s) for private recipes the requester can't see, so the
    endpoint doesn't leak which UUIDs exist.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    row = cursor.execute(
        "SELECT user_id, is_public, has_image FROM recipes WHERE uuid = ?",
        (recipe_uuid,),
    ).fetchone()

    if row is None or not row["has_image"]:
        conn.close()
        raise HTTPException(status_code=404, detail="Image not found")

    is_public = bool(row["is_public"])
    owner_id = get_user_id(current_user.email) if current_user else None
    role = effective_role(cursor, owner_id, recipe_uuid) if owner_id is not None else "none"
    conn.close()
    if not is_public and not role_at_least(role, "viewer"):
        raise HTTPException(status_code=404, detail="Image not found")

    path = recipe_images.image_path(recipe_uuid)
    if path is None:
        raise HTTPException(status_code=404, detail="Image not found")
    # Long-lived cache; the URL carries a ?v= cache-buster tied to updated_at.
    return FileResponse(
        path,
        media_type="image/jpeg",
        headers={"Cache-Control": "public, max-age=31536000, immutable"},
    )


class ShareRecipeBody(BaseModel):
    friend_id: int
    role: str  # viewer | editor | manager


@router.post("/{recipe_uuid}/share", include_in_schema=False)
async def share_recipe(
    recipe_uuid: str,
    body: ShareRecipeBody,
    current_user: User = Depends(get_current_user),  # noqa: B008
):
    """Share a single recipe with a friend by wrapping it in a lightweight
    ``quickshare`` cookbook — keeping one sharing primitive. Owner only."""
    user_id = get_user_id(current_user.email)
    if user_id is None:
        raise HTTPException(status_code=401, detail="Unknown user")
    if body.role not in ("viewer", "editor", "manager"):
        raise HTTPException(status_code=422, detail="Invalid role")

    conn = get_db_connection()
    cursor = conn.cursor()
    row = cursor.execute(
        "SELECT user_id, title FROM recipes WHERE uuid = ?", (recipe_uuid,)
    ).fetchone()
    if row is None or row["user_id"] != user_id:
        conn.close()
        raise HTTPException(status_code=404, detail="Recipe not found")

    friend = cursor.execute(
        "SELECT 1 FROM friendships WHERE status = 'accepted' AND "
        "((requester_id = ? AND addressee_id = ?) OR (requester_id = ? AND addressee_id = ?))",
        (user_id, body.friend_id, body.friend_id, user_id),
    ).fetchone()
    if friend is None:
        conn.close()
        raise HTTPException(status_code=403, detail="You can only share with friends")

    name = row["title"] or "Shared recipe"
    existing = cursor.execute(
        "SELECT id FROM cookbooks WHERE owner_id = ? AND kind = 'quickshare' AND name = ?",
        (user_id, name),
    ).fetchone()
    if existing is not None:
        cookbook_id = existing["id"]
    else:
        cursor.execute(
            "INSERT INTO cookbooks (owner_id, name, kind) VALUES (?, ?, 'quickshare')",
            (user_id, name),
        )
        cookbook_id = cursor.lastrowid

    cursor.execute(
        "INSERT OR IGNORE INTO cookbook_recipes (cookbook_id, recipe_uuid, added_by) "
        "VALUES (?, ?, ?)",
        (cookbook_id, recipe_uuid, user_id),
    )
    cursor.execute(
        "INSERT INTO cookbook_members (cookbook_id, user_id, role, status, invited_by) "
        "VALUES (?, ?, ?, 'pending', ?) "
        "ON CONFLICT(cookbook_id, user_id) DO UPDATE SET role = excluded.role",
        (cookbook_id, body.friend_id, body.role, user_id),
    )
    conn.commit()
    conn.close()
    return {"cookbook_id": cookbook_id}


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
    recipe_images.delete_image(recipe_uuid)
    return None

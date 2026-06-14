"""Recipe endpoints.

- ``POST /recipes/parse`` — auth required; image → OpenAI → store → uuid.
- ``POST /recipes/import-url`` — auth required; URL → JSON-LD/OpenAI → store → uuid.
- ``GET /recipes`` — auth required; list the current user's recipes.
- ``PUT /recipes/{uuid}`` — auth required; edit structured fields.
- ``DELETE /recipes/{uuid}`` — auth required; 204 on success.
- ``GET /recipes/{uuid}.json`` — public; full recipe JSON for Bring etc.
- ``GET /recipes/{uuid}.html`` — public; raw HTML for Bring etc.
"""

import json
import re
import uuid as uuid_mod
from typing import Any, Dict, List, Optional

import httpx
from fastapi import APIRouter, Depends, Form, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

from api.auth import get_current_user, get_user_id
from api.db import get_db_connection
from api.models import RecipeResponse, RecipeUpdate, User
from api.recipe_extraction import (
    USER_AGENT,
    extract_recipe_from_html_text,
    extract_recipe_from_jsonld,
    parse_recipe_with_openai,
)

# 5 MB is enough for any recipe page; bigger bodies are almost
# certainly a feed or wrapper page and not a single recipe.
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
    """Persist a parsed recipe with the standard shape and metadata.

    Shared by the image import and the URL import; keeps both
    endpoints in sync.
    """
    schema_recipe = {
        "@context": "https://schema.org/",
        "@type": "Recipe",
        "name": recipe.title,
        "recipeIngredient": recipe.recipeIngredient,
        "recipeYield": recipe.recipeYield,
        "datePublished": recipe.datePublished,
        "description": recipe.description,
        "html_content": recipe.html_content,
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
         422 on a network/HTTP error with a user-readable message.
      2. Try JSON-LD extraction (covers ~3/5 of mainstream sites per the
         step-2 spike). On hit, normalise to a ``Recipe``.
      3. Fall back to OpenAI text extraction (gpt-4o-mini) on a
         chrome-stripped version of the page; the response is parsed
         by the same ``_extract_recipe_from_html`` used by the image
         flow.
      4. Store with ``source={"kind":"url","value":url}`` and return
         the same ``RecipeResponse`` shape as the image endpoint.
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
async def get_recipe(recipe_uuid: str):
    # Public endpoint (no auth) so Bring can fetch the recipe by UUID.
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT recipe_json FROM recipes WHERE uuid = ?", (recipe_uuid,))
    recipe = cursor.fetchone()
    conn.close()

    if not recipe:
        raise HTTPException(status_code=404, detail="Recipe not found")

    return JSONResponse(content=json.loads(recipe["recipe_json"]))


@router.get("/{recipe_uuid}.html", include_in_schema=False)
async def get_recipe_html(recipe_uuid: str):
    # Public endpoint (no auth) so Bring can fetch the rendered HTML.
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT recipe_json FROM recipes WHERE uuid = ?", (recipe_uuid,))
    recipe = cursor.fetchone()
    conn.close()

    if not recipe:
        raise HTTPException(status_code=404, detail="Recipe not found")

    recipe_data = json.loads(recipe["recipe_json"])
    html_content = recipe_data.get("html_content")

    if not html_content:
        raise HTTPException(status_code=404, detail="No HTML content available for this recipe")

    return HTMLResponse(content=html_content, status_code=200)


@router.get("", response_model=List[Dict[str, Any]])
async def list_recipes(current_user: User = Depends(get_current_user)):  # noqa: B008
    """Return the current user's recipes (uuid, title, datePublished, source).

    Auth required (step 3) so a user only sees their own recipes. The
    pre-existing endpoint returned every user's recipes to anyone who
    hit it; that cross-user leak is now closed.
    """
    user_id = get_user_id(current_user.email)
    if user_id is None:
        return []

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT uuid, title, recipe_json FROM recipes WHERE user_id = ? ORDER BY created_at DESC",
        (user_id,),
    )
    rows = cursor.fetchall()
    conn.close()
    recipes: List[Dict[str, Any]] = []
    for row in rows:
        try:
            recipe_json = json.loads(row["recipe_json"])
        except Exception:
            recipe_json = {}
        # Backfill source for pre-step-3 rows.
        source = recipe_json.get("source") or {"kind": "unknown", "value": ""}
        recipes.append(
            {
                "uuid": row["uuid"],
                "title": row["title"],
                "datePublished": recipe_json.get("datePublished"),
                "source": source,
            }
        )
    return recipes


@router.put("/{recipe_uuid}")
async def update_recipe(
    recipe_uuid: str,
    body: RecipeUpdate,
    current_user: User = Depends(get_current_user),  # noqa: B008
):
    """Update the structured fields of a recipe owned by the current user.

    Returns 404 (not 403) when the recipe exists but is owned by another
    user, so an attacker can't probe for valid UUIDs.
    """
    user_id = get_user_id(current_user.email)
    if user_id is None:
        raise HTTPException(status_code=401, detail="Unknown user")

    conn = get_db_connection()
    cursor = conn.cursor()
    row = cursor.execute(
        "SELECT user_id, recipe_json, note, source FROM recipes WHERE uuid = ?",
        (recipe_uuid,),
    ).fetchone()
    if row is None or row["user_id"] != user_id:
        conn.close()
        raise HTTPException(status_code=404, detail="Recipe not found")

    try:
        stored = json.loads(row["recipe_json"])
    except Exception:
        stored = {}

    for field in ("title", "recipeIngredient", "recipeYield", "description", "html_content"):
        value = getattr(body, field)
        if value is not None:
            stored[field] = value
    if body.note is not None:
        stored["note"] = body.note
    new_title = stored.get("title", "")
    new_note = stored.get("note", "")

    cursor.execute(
        "UPDATE recipes SET title = ?, recipe_json = ?, note = ?, "
        "updated_at = CURRENT_TIMESTAMP WHERE uuid = ?",
        (new_title, json.dumps(stored), new_note, recipe_uuid),
    )
    conn.commit()
    conn.close()

    return JSONResponse(content=stored)


@router.delete("/{recipe_uuid}", status_code=204)
async def delete_recipe(
    recipe_uuid: str,
    current_user: User = Depends(get_current_user),  # noqa: B008
):
    """Delete a recipe owned by the current user.

    Returns 204 on success, 404 (not 403) if the recipe exists but is
    owned by another user. After deletion, the public JSON/HTML
    endpoints for that UUID will 404, which is fine for Bring.
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

    cursor.execute("DELETE FROM recipes WHERE uuid = ?", (recipe_uuid,))
    conn.commit()
    conn.close()
    return None

"""Cookbook endpoints — Phase 2 of recipe sharing (personal collections).

A cookbook is a named collection of recipes owned by one user. Phase 2 is
personal-only: every endpoint is scoped to the current user as owner. Sharing
(cookbook_members, effective_role) arrives in Phase 3. See
``.claude/plans/friends-cookbooks-sharing.md``.
"""

import json
from typing import Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from api.auth import get_current_user, get_user_id
from api.db import get_db_connection
from api.models import User
from api.routers.recipes import _list_item, _tags_for
from api.search import match_score, recipe_haystack

router = APIRouter(prefix="/cookbooks", tags=["cookbooks"])


class CookbookCreate(BaseModel):
    name: str


class CookbookRename(BaseModel):
    name: str


class AddRecipeBody(BaseModel):
    recipe_uuid: str


def _require_me(current_user: User) -> int:
    uid = get_user_id(current_user.email)
    if uid is None:
        raise HTTPException(status_code=401, detail="Unknown user")
    return uid


def _owned_cookbook(cursor, cookbook_id: int, user_id: int):
    """Return the cookbook row iff it exists and is owned by ``user_id``, else None."""
    row = cursor.execute(
        "SELECT id, owner_id, name FROM cookbooks WHERE id = ?", (cookbook_id,)
    ).fetchone()
    if row is None or row["owner_id"] != user_id:
        return None
    return row


def _clean_name(name: str) -> str:
    return " ".join(name.split())


@router.post("", include_in_schema=False)
async def create_cookbook(
    body: CookbookCreate,
    current_user: User = Depends(get_current_user),  # noqa: B008
):
    """Create a new (empty) cookbook owned by the current user."""
    me = _require_me(current_user)
    name = _clean_name(body.name)
    if not name:
        raise HTTPException(status_code=422, detail="Cookbook name cannot be empty")
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO cookbooks (owner_id, name) VALUES (?, ?)", (me, name))
    cookbook_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return {"id": cookbook_id, "name": name, "recipe_count": 0, "cover_image_url": None}


@router.get("", include_in_schema=False)
async def list_cookbooks(
    recipe_uuid: Optional[str] = Query(default=None),
    current_user: User = Depends(get_current_user),  # noqa: B008
):
    """List the current user's cookbooks (name-sorted) with a recipe count and cover.

    If ``recipe_uuid`` is given, each cookbook also reports ``contains`` — whether
    that recipe is already in it (used by the "Add to cookbook" picker).
    """
    me = _require_me(current_user)
    conn = get_db_connection()
    cursor = conn.cursor()
    rows = cursor.execute(
        """
        SELECT c.id AS id, c.name AS name,
          (SELECT COUNT(*) FROM cookbook_recipes cr WHERE cr.cookbook_id = c.id) AS recipe_count,
          (SELECT cr.recipe_uuid FROM cookbook_recipes cr
             JOIN recipes r ON r.uuid = cr.recipe_uuid
             WHERE cr.cookbook_id = c.id AND r.has_image = 1
             ORDER BY cr.added_at DESC LIMIT 1) AS cover_uuid
        FROM cookbooks c WHERE c.owner_id = ?
        ORDER BY c.name COLLATE NOCASE
        """,
        (me,),
    ).fetchall()

    contains_ids: set = set()
    if recipe_uuid:
        contains_ids = {
            r["cookbook_id"]
            for r in cursor.execute(
                "SELECT cr.cookbook_id AS cookbook_id FROM cookbook_recipes cr "
                "JOIN cookbooks c ON c.id = cr.cookbook_id "
                "WHERE cr.recipe_uuid = ? AND c.owner_id = ?",
                (recipe_uuid, me),
            ).fetchall()
        }
    conn.close()

    out: List[dict] = []
    for r in rows:
        item = {
            "id": r["id"],
            "name": r["name"],
            "recipe_count": r["recipe_count"],
            # No version param — a cover only needs to be roughly fresh.
            "cover_image_url": f"/recipes/{r['cover_uuid']}/image" if r["cover_uuid"] else None,
        }
        if recipe_uuid:
            item["contains"] = r["id"] in contains_ids
        out.append(item)
    return out


@router.get("/{cookbook_id}", include_in_schema=False)
async def get_cookbook(
    cookbook_id: int,
    current_user: User = Depends(get_current_user),  # noqa: B008
):
    """Return a cookbook with its recipes (as list items). 404 if not the owner's."""
    me = _require_me(current_user)
    conn = get_db_connection()
    cursor = conn.cursor()
    cb = _owned_cookbook(cursor, cookbook_id, me)
    if cb is None:
        conn.close()
        raise HTTPException(status_code=404, detail="Cookbook not found")

    rows = cursor.execute(
        "SELECT r.uuid, r.title, r.recipe_json, r.created_at, r.updated_at, r.is_public, "
        "r.has_image FROM cookbook_recipes cr JOIN recipes r ON r.uuid = cr.recipe_uuid "
        "WHERE cr.cookbook_id = ? ORDER BY cr.added_at DESC",
        (cookbook_id,),
    ).fetchall()
    tag_map = _tags_for(cursor, [row["uuid"] for row in rows])
    conn.close()

    items = [_list_item(row, tag_map) for row in rows]
    return {"id": cb["id"], "name": cb["name"], "recipe_count": len(items), "recipes": items}


@router.patch("/{cookbook_id}", include_in_schema=False)
async def rename_cookbook(
    cookbook_id: int,
    body: CookbookRename,
    current_user: User = Depends(get_current_user),  # noqa: B008
):
    """Rename a cookbook the current user owns."""
    me = _require_me(current_user)
    name = _clean_name(body.name)
    if not name:
        raise HTTPException(status_code=422, detail="Cookbook name cannot be empty")
    conn = get_db_connection()
    cursor = conn.cursor()
    if _owned_cookbook(cursor, cookbook_id, me) is None:
        conn.close()
        raise HTTPException(status_code=404, detail="Cookbook not found")
    cursor.execute(
        "UPDATE cookbooks SET name = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (name, cookbook_id),
    )
    conn.commit()
    conn.close()
    return {"id": cookbook_id, "name": name}


@router.delete("/{cookbook_id}", include_in_schema=False, status_code=204)
async def delete_cookbook(
    cookbook_id: int,
    current_user: User = Depends(get_current_user),  # noqa: B008
):
    """Delete a cookbook (and its membership rows). Recipes themselves are untouched."""
    me = _require_me(current_user)
    conn = get_db_connection()
    cursor = conn.cursor()
    if _owned_cookbook(cursor, cookbook_id, me) is None:
        conn.close()
        raise HTTPException(status_code=404, detail="Cookbook not found")
    cursor.execute("DELETE FROM cookbook_recipes WHERE cookbook_id = ?", (cookbook_id,))
    cursor.execute("DELETE FROM cookbooks WHERE id = ?", (cookbook_id,))
    conn.commit()
    conn.close()
    return None


def _owns_recipe(cursor, recipe_uuid: str, user_id: int) -> bool:
    row = cursor.execute("SELECT user_id FROM recipes WHERE uuid = ?", (recipe_uuid,)).fetchone()
    return row is not None and row["user_id"] == user_id


def _matching_owned_uuids(
    cursor, user_id: int, q: Optional[str], tags: Optional[List[str]]
) -> List[str]:
    """UUIDs of the user's own recipes matching a search — same filtering as the
    recipe list (tag AND-filter + fuzzy full-text ``q``), but returns every match
    (no pagination) so a search can be bulk-added to a cookbook."""
    where = "WHERE user_id = ?"
    params: List[Any] = [user_id]
    tags_norm = sorted({t.strip().lower() for t in (tags or []) if t.strip()})
    if tags_norm:
        placeholders = ",".join("?" * len(tags_norm))
        where += (
            f" AND uuid IN (SELECT rt.recipe_uuid FROM recipe_tags rt "
            f"JOIN tags t ON t.id = rt.tag_id WHERE LOWER(t.name) IN ({placeholders}) "
            f"GROUP BY rt.recipe_uuid HAVING COUNT(DISTINCT LOWER(t.name)) = ?)"
        )
        params.extend([*tags_norm, len(tags_norm)])

    rows = cursor.execute(f"SELECT uuid, recipe_json FROM recipes {where}", params).fetchall()

    query = (q or "").strip()
    if not query:
        return [r["uuid"] for r in rows]

    tag_map = _tags_for(cursor, [r["uuid"] for r in rows])
    matched: List[str] = []
    for r in rows:
        try:
            recipe_json = json.loads(r["recipe_json"])
        except Exception:
            recipe_json = {}
        names = [t["name"] for t in tag_map.get(r["uuid"], [])]
        if match_score(query, recipe_haystack(recipe_json, names)) > 0:
            matched.append(r["uuid"])
    return matched


class BulkAddBody(BaseModel):
    # Either add an explicit list of recipes, or everything matching a search.
    recipe_uuids: Optional[List[str]] = None
    q: Optional[str] = None
    tags: Optional[List[str]] = None


@router.post("/{cookbook_id}/recipes/bulk", include_in_schema=False)
async def bulk_add_recipes(
    cookbook_id: int,
    body: BulkAddBody,
    current_user: User = Depends(get_current_user),  # noqa: B008
):
    """Add many of the current user's recipes to a cookbook at once.

    Pass ``recipe_uuids`` for an explicit set, or ``q``/``tags`` to add every
    recipe matching that search. Only recipes the user owns are added; already
    present ones are skipped. Returns ``{matched, added}``.
    """
    me = _require_me(current_user)
    conn = get_db_connection()
    cursor = conn.cursor()
    if _owned_cookbook(cursor, cookbook_id, me) is None:
        conn.close()
        raise HTTPException(status_code=404, detail="Cookbook not found")

    if body.recipe_uuids is not None:
        uuids = [u for u in dict.fromkeys(body.recipe_uuids) if _owns_recipe(cursor, u, me)]
    else:
        uuids = _matching_owned_uuids(cursor, me, body.q, body.tags)

    added = 0
    for u in uuids:
        cursor.execute(
            "INSERT OR IGNORE INTO cookbook_recipes (cookbook_id, recipe_uuid, added_by) "
            "VALUES (?, ?, ?)",
            (cookbook_id, u, me),
        )
        added += cursor.rowcount  # 1 when inserted, 0 when already present
    conn.commit()
    conn.close()
    return {"matched": len(uuids), "added": added}


@router.post("/{cookbook_id}/recipes", include_in_schema=False)
async def add_recipe(
    cookbook_id: int,
    body: AddRecipeBody,
    current_user: User = Depends(get_current_user),  # noqa: B008
):
    """Add one of the current user's recipes to their cookbook (idempotent)."""
    me = _require_me(current_user)
    conn = get_db_connection()
    cursor = conn.cursor()
    if _owned_cookbook(cursor, cookbook_id, me) is None:
        conn.close()
        raise HTTPException(status_code=404, detail="Cookbook not found")
    if not _owns_recipe(cursor, body.recipe_uuid, me):
        conn.close()
        raise HTTPException(status_code=404, detail="Recipe not found")
    cursor.execute(
        "INSERT OR IGNORE INTO cookbook_recipes (cookbook_id, recipe_uuid, added_by) "
        "VALUES (?, ?, ?)",
        (cookbook_id, body.recipe_uuid, me),
    )
    conn.commit()
    conn.close()
    return {"ok": True}


@router.delete("/{cookbook_id}/recipes/{recipe_uuid}", include_in_schema=False, status_code=204)
async def remove_recipe(
    cookbook_id: int,
    recipe_uuid: str,
    current_user: User = Depends(get_current_user),  # noqa: B008
):
    """Remove a recipe from the current user's cookbook (the recipe itself stays)."""
    me = _require_me(current_user)
    conn = get_db_connection()
    cursor = conn.cursor()
    if _owned_cookbook(cursor, cookbook_id, me) is None:
        conn.close()
        raise HTTPException(status_code=404, detail="Cookbook not found")
    cursor.execute(
        "DELETE FROM cookbook_recipes WHERE cookbook_id = ? AND recipe_uuid = ?",
        (cookbook_id, recipe_uuid),
    )
    conn.commit()
    conn.close()
    return None

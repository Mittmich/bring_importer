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

from api.access import cookbook_role, effective_role, role_at_least
from api.auth import get_current_user, get_user_id
from api.db import get_db_connection
from api.models import User
from api.routers.recipes import _list_item, _tags_for
from api.search import match_score, recipe_haystack

router = APIRouter(prefix="/cookbooks", tags=["cookbooks"])


def _are_friends(cursor, a: int, b: int) -> bool:
    row = cursor.execute(
        "SELECT 1 FROM friendships WHERE status = 'accepted' AND "
        "((requester_id = ? AND addressee_id = ?) OR (requester_id = ? AND addressee_id = ?))",
        (a, b, b, a),
    ).fetchone()
    return row is not None


class CookbookCreate(BaseModel):
    name: str


class CookbookRename(BaseModel):
    name: str


class AddRecipeBody(BaseModel):
    recipe_uuid: str


class InviteBody(BaseModel):
    friend_id: int
    role: str  # viewer | editor | manager


class RoleBody(BaseModel):
    role: str


VALID_ROLES = {"viewer", "editor", "manager"}


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
    # My own cookbooks plus any shared with me (accepted membership).
    rows = cursor.execute(
        """
        SELECT c.id AS id, c.name AS name, c.owner_id AS owner_id, m.role AS member_role,
          (SELECT COUNT(*) FROM cookbook_recipes cr WHERE cr.cookbook_id = c.id) AS recipe_count,
          (SELECT cr.recipe_uuid FROM cookbook_recipes cr
             JOIN recipes r ON r.uuid = cr.recipe_uuid
             WHERE cr.cookbook_id = c.id AND r.has_image = 1
             ORDER BY cr.added_at DESC LIMIT 1) AS cover_uuid
        FROM cookbooks c
        LEFT JOIN cookbook_members m
          ON m.cookbook_id = c.id AND m.user_id = ? AND m.status = 'accepted'
        WHERE c.owner_id = ? OR m.user_id IS NOT NULL
        ORDER BY c.name COLLATE NOCASE
        """,
        (me, me),
    ).fetchall()

    contains_ids: set = set()
    if recipe_uuid:
        ids = [r["id"] for r in rows]
        if ids:
            ph = ",".join("?" * len(ids))
            contains_ids = {
                r["cookbook_id"]
                for r in cursor.execute(
                    f"SELECT cookbook_id FROM cookbook_recipes "
                    f"WHERE recipe_uuid = ? AND cookbook_id IN ({ph})",
                    (recipe_uuid, *ids),
                ).fetchall()
            }
    conn.close()

    out: List[dict] = []
    for r in rows:
        role = "owner" if r["owner_id"] == me else r["member_role"]
        item = {
            "id": r["id"],
            "name": r["name"],
            "recipe_count": r["recipe_count"],
            # No version param — a cover only needs to be roughly fresh.
            "cover_image_url": f"/recipes/{r['cover_uuid']}/image" if r["cover_uuid"] else None,
            "role": role,
            "shared": r["owner_id"] != me,
        }
        if recipe_uuid:
            item["contains"] = r["id"] in contains_ids
        out.append(item)
    return out


# --- Invitations. Declared before /{cookbook_id} so the static "invitations"
#     segment isn't captured by the {cookbook_id} path param. ---


@router.get("/invitations", include_in_schema=False)
async def list_cookbook_invitations(current_user: User = Depends(get_current_user)):  # noqa: B008
    """Pending cookbook invitations addressed to the current user."""
    me = _require_me(current_user)
    conn = get_db_connection()
    cursor = conn.cursor()
    rows = cursor.execute(
        "SELECT m.cookbook_id AS cookbook_id, c.name AS name, u.email AS owner_email, "
        "m.role AS role FROM cookbook_members m "
        "JOIN cookbooks c ON c.id = m.cookbook_id JOIN users u ON u.id = c.owner_id "
        "WHERE m.user_id = ? AND m.status = 'pending' ORDER BY m.created_at DESC",
        (me,),
    ).fetchall()
    conn.close()
    return [
        {
            "cookbook_id": r["cookbook_id"],
            "name": r["name"],
            "owner_email": r["owner_email"],
            "role": r["role"],
        }
        for r in rows
    ]


def _pending_invite(cursor, cookbook_id: int, me: int):
    return cursor.execute(
        "SELECT 1 FROM cookbook_members "
        "WHERE cookbook_id = ? AND user_id = ? AND status = 'pending'",
        (cookbook_id, me),
    ).fetchone()


@router.post("/invitations/{cookbook_id}/accept", include_in_schema=False)
async def accept_invitation(
    cookbook_id: int,
    current_user: User = Depends(get_current_user),  # noqa: B008
):
    """Accept a pending cookbook invitation."""
    me = _require_me(current_user)
    conn = get_db_connection()
    cursor = conn.cursor()
    if _pending_invite(cursor, cookbook_id, me) is None:
        conn.close()
        raise HTTPException(status_code=404, detail="Invitation not found")
    cursor.execute(
        "UPDATE cookbook_members SET status = 'accepted', responded_at = CURRENT_TIMESTAMP "
        "WHERE cookbook_id = ? AND user_id = ?",
        (cookbook_id, me),
    )
    conn.commit()
    conn.close()
    return {"status": "accepted"}


@router.post("/invitations/{cookbook_id}/decline", include_in_schema=False, status_code=204)
async def decline_invitation(
    cookbook_id: int,
    current_user: User = Depends(get_current_user),  # noqa: B008
):
    """Decline a pending cookbook invitation (removes it)."""
    me = _require_me(current_user)
    conn = get_db_connection()
    cursor = conn.cursor()
    if _pending_invite(cursor, cookbook_id, me) is None:
        conn.close()
        raise HTTPException(status_code=404, detail="Invitation not found")
    cursor.execute(
        "DELETE FROM cookbook_members WHERE cookbook_id = ? AND user_id = ?",
        (cookbook_id, me),
    )
    conn.commit()
    conn.close()
    return None


@router.get("/{cookbook_id}", include_in_schema=False)
async def get_cookbook(
    cookbook_id: int,
    current_user: User = Depends(get_current_user),  # noqa: B008
):
    """Return a cookbook with its recipes. Readable by the owner or any accepted
    member; 404 otherwise. The response ``role`` lets the client gate controls."""
    me = _require_me(current_user)
    conn = get_db_connection()
    cursor = conn.cursor()
    role = cookbook_role(cursor, me, cookbook_id)
    if not role_at_least(role, "viewer"):
        conn.close()
        raise HTTPException(status_code=404, detail="Cookbook not found")
    cb = cursor.execute("SELECT id, name FROM cookbooks WHERE id = ?", (cookbook_id,)).fetchone()

    rows = cursor.execute(
        "SELECT r.uuid, r.title, r.recipe_json, r.created_at, r.updated_at, r.is_public, "
        "r.has_image FROM cookbook_recipes cr JOIN recipes r ON r.uuid = cr.recipe_uuid "
        "WHERE cr.cookbook_id = ? ORDER BY cr.added_at DESC",
        (cookbook_id,),
    ).fetchall()
    tag_map = _tags_for(cursor, [row["uuid"] for row in rows])
    conn.close()

    items = [_list_item(row, tag_map) for row in rows]
    return {
        "id": cb["id"],
        "name": cb["name"],
        "recipe_count": len(items),
        "recipes": items,
        "role": role,
    }


@router.patch("/{cookbook_id}", include_in_schema=False)
async def rename_cookbook(
    cookbook_id: int,
    body: CookbookRename,
    current_user: User = Depends(get_current_user),  # noqa: B008
):
    """Rename a cookbook (owner or a manager member)."""
    me = _require_me(current_user)
    name = _clean_name(body.name)
    if not name:
        raise HTTPException(status_code=422, detail="Cookbook name cannot be empty")
    conn = get_db_connection()
    cursor = conn.cursor()
    if not role_at_least(cookbook_role(cursor, me, cookbook_id), "manager"):
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
    if not role_at_least(cookbook_role(cursor, me, cookbook_id), "manager"):
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
    if not role_at_least(cookbook_role(cursor, me, cookbook_id), "manager"):
        conn.close()
        raise HTTPException(status_code=404, detail="Cookbook not found")
    if not role_at_least(effective_role(cursor, me, body.recipe_uuid), "viewer"):
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
    if not role_at_least(cookbook_role(cursor, me, cookbook_id), "manager"):
        conn.close()
        raise HTTPException(status_code=404, detail="Cookbook not found")
    cursor.execute(
        "DELETE FROM cookbook_recipes WHERE cookbook_id = ? AND recipe_uuid = ?",
        (cookbook_id, recipe_uuid),
    )
    conn.commit()
    conn.close()
    return None


# --- Members (sharing a cookbook with friends) ---


@router.get("/{cookbook_id}/members", include_in_schema=False)
async def list_members(
    cookbook_id: int,
    current_user: User = Depends(get_current_user),  # noqa: B008
):
    """List a cookbook's owner and members. Visible to the owner and any member."""
    me = _require_me(current_user)
    conn = get_db_connection()
    cursor = conn.cursor()
    if not role_at_least(cookbook_role(cursor, me, cookbook_id), "viewer"):
        conn.close()
        raise HTTPException(status_code=404, detail="Cookbook not found")
    owner = cursor.execute(
        "SELECT u.id AS id, u.email AS email FROM cookbooks c "
        "JOIN users u ON u.id = c.owner_id WHERE c.id = ?",
        (cookbook_id,),
    ).fetchone()
    members = cursor.execute(
        "SELECT m.user_id AS user_id, u.email AS email, m.role AS role, m.status AS status "
        "FROM cookbook_members m JOIN users u ON u.id = m.user_id "
        "WHERE m.cookbook_id = ? ORDER BY u.email COLLATE NOCASE",
        (cookbook_id,),
    ).fetchall()
    conn.close()
    return {
        "owner": {"user_id": owner["id"], "email": owner["email"]},
        "members": [
            {"user_id": m["user_id"], "email": m["email"], "role": m["role"], "status": m["status"]}
            for m in members
        ],
    }


@router.post("/{cookbook_id}/members", include_in_schema=False)
async def invite_member(
    cookbook_id: int,
    body: InviteBody,
    current_user: User = Depends(get_current_user),  # noqa: B008
):
    """Invite a friend to a cookbook at a role (owner/manager only, friends only)."""
    me = _require_me(current_user)
    if body.role not in VALID_ROLES:
        raise HTTPException(status_code=422, detail="Invalid role")
    conn = get_db_connection()
    cursor = conn.cursor()
    cb = cursor.execute("SELECT owner_id FROM cookbooks WHERE id = ?", (cookbook_id,)).fetchone()
    if cb is None or not role_at_least(cookbook_role(cursor, me, cookbook_id), "manager"):
        conn.close()
        raise HTTPException(status_code=404, detail="Cookbook not found")
    if body.friend_id == cb["owner_id"]:
        conn.close()
        raise HTTPException(status_code=422, detail="The owner is already on this cookbook")
    if not _are_friends(cursor, me, body.friend_id):
        conn.close()
        raise HTTPException(status_code=403, detail="You can only share with friends")

    # New invite → pending; existing member → just update the role.
    cursor.execute(
        "INSERT INTO cookbook_members (cookbook_id, user_id, role, status, invited_by) "
        "VALUES (?, ?, ?, 'pending', ?) "
        "ON CONFLICT(cookbook_id, user_id) DO UPDATE SET role = excluded.role",
        (cookbook_id, body.friend_id, body.role, me),
    )
    conn.commit()
    conn.close()
    return {"ok": True}


@router.patch("/{cookbook_id}/members/{user_id}", include_in_schema=False)
async def update_member_role(
    cookbook_id: int,
    user_id: int,
    body: RoleBody,
    current_user: User = Depends(get_current_user),  # noqa: B008
):
    """Change a member's role (owner/manager only)."""
    me = _require_me(current_user)
    if body.role not in VALID_ROLES:
        raise HTTPException(status_code=422, detail="Invalid role")
    conn = get_db_connection()
    cursor = conn.cursor()
    if not role_at_least(cookbook_role(cursor, me, cookbook_id), "manager"):
        conn.close()
        raise HTTPException(status_code=404, detail="Cookbook not found")
    row = cursor.execute(
        "SELECT 1 FROM cookbook_members WHERE cookbook_id = ? AND user_id = ?",
        (cookbook_id, user_id),
    ).fetchone()
    if row is None:
        conn.close()
        raise HTTPException(status_code=404, detail="Member not found")
    cursor.execute(
        "UPDATE cookbook_members SET role = ? WHERE cookbook_id = ? AND user_id = ?",
        (body.role, cookbook_id, user_id),
    )
    conn.commit()
    conn.close()
    return {"ok": True}


@router.delete("/{cookbook_id}/members/{user_id}", include_in_schema=False, status_code=204)
async def remove_member(
    cookbook_id: int,
    user_id: int,
    current_user: User = Depends(get_current_user),  # noqa: B008
):
    """Remove a member (owner/manager), or leave a cookbook yourself."""
    me = _require_me(current_user)
    conn = get_db_connection()
    cursor = conn.cursor()
    is_manager = role_at_least(cookbook_role(cursor, me, cookbook_id), "manager")
    if not is_manager and user_id != me:
        conn.close()
        raise HTTPException(status_code=404, detail="Cookbook not found")
    cursor.execute(
        "DELETE FROM cookbook_members WHERE cookbook_id = ? AND user_id = ?",
        (cookbook_id, user_id),
    )
    conn.commit()
    conn.close()
    return None

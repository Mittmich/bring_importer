"""Admin control plane — every route requires ``users.is_admin`` (403 otherwise).

- ``GET    /admin/users`` — all users with usage stats.
- ``PATCH  /admin/users/{id}`` — ``{is_admin?, disabled?}``.
- ``POST   /admin/users/{id}/logout`` — revoke every session of a user.
- ``POST   /admin/users/{id}/reset-link`` — one-time password-reset link (24 h).
- ``DELETE /admin/users/{id}?confirm=<email>`` — delete a user and all their data.
- ``GET    /admin/invites`` / ``POST /admin/invites`` / ``DELETE /admin/invites/{id}``
  — sign-up links.
- ``GET    /admin/friendships`` / ``POST /admin/friendships`` /
  ``DELETE /admin/friendships/{id}`` — the friend graph; removing a friendship
  revokes every share between the pair.
- ``GET    /admin/shares`` / ``POST /admin/shares`` /
  ``PATCH|DELETE /admin/shares/{type}/{resource_id}/{user_id}`` — menu and
  cookbook shares of every user. Admin-made shares and friendships are accepted
  at once; shares stay friends-only (``ensure_friends`` connects the pair).
- ``GET    /admin/users/{id}/resources?type=`` — a user's menus or cookbooks.

Guard rails: an admin can't demote, disable or delete themselves, and the last
admin can't be demoted. Link tokens are returned only by the create calls.
"""

from datetime import timedelta
from typing import Any, Dict, List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from api import auth_links, recipe_images
from api.access import MENU_ROLES, are_friends, revoke_shares_between
from api.auth import bump_token_version, get_current_admin, utc_now
from api.db import get_db_connection
from api.models import UserInDB

router = APIRouter(prefix="/admin", tags=["admin"], include_in_schema=False)


def _target(cursor, user_id: int):
    row = cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="User not found")
    return row


def _admin_count(cursor) -> int:
    return int(cursor.execute("SELECT COUNT(*) FROM users WHERE is_admin = 1").fetchone()[0])


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------


@router.get("/users")
async def list_users(admin: UserInDB = Depends(get_current_admin)):  # noqa: B008
    conn = get_db_connection()
    try:
        rows = conn.execute(
            """
            SELECT u.id, u.email, u.display_name, u.is_admin, u.disabled, u.created_at,
                   u.last_login_at, inv.email AS invited_by_email,
                   (SELECT COUNT(*) FROM recipes r WHERE r.user_id = u.id) AS recipe_count
            FROM users u LEFT JOIN users inv ON inv.id = u.invited_by
            ORDER BY u.email COLLATE NOCASE
            """
        ).fetchall()
    finally:
        conn.close()
    return [
        {
            "id": r["id"],
            "email": r["email"],
            "display_name": r["display_name"] or "",
            "is_admin": bool(r["is_admin"]),
            "disabled": bool(r["disabled"]),
            "created_at": r["created_at"],
            "last_login_at": r["last_login_at"],
            "invited_by": r["invited_by_email"],
            "recipe_count": r["recipe_count"],
            "is_self": r["id"] == admin.id,
        }
        for r in rows
    ]


class UserPatch(BaseModel):
    is_admin: Optional[bool] = None
    disabled: Optional[bool] = None


@router.patch("/users/{user_id}", status_code=204)
async def update_user(
    user_id: int,
    body: UserPatch,
    admin: UserInDB = Depends(get_current_admin),  # noqa: B008
):
    if user_id == admin.id and (body.is_admin is False or body.disabled is True):
        raise HTTPException(status_code=422, detail="You can't demote or disable yourself.")
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        target = _target(cursor, user_id)
        if body.is_admin is False and target["is_admin"] and _admin_count(cursor) <= 1:
            raise HTTPException(status_code=422, detail="There must be at least one admin.")
        if body.is_admin is not None:
            cursor.execute(
                "UPDATE users SET is_admin = ? WHERE id = ?", (int(body.is_admin), user_id)
            )
        if body.disabled is not None:
            cursor.execute(
                "UPDATE users SET disabled = ? WHERE id = ?", (int(body.disabled), user_id)
            )
            if body.disabled:
                bump_token_version(cursor, user_id)
        conn.commit()
    finally:
        conn.close()
    return None


@router.post("/users/{user_id}/logout", status_code=204)
async def logout_everywhere(
    user_id: int,
    admin: UserInDB = Depends(get_current_admin),  # noqa: B008
):
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        _target(cursor, user_id)
        bump_token_version(cursor, user_id)
        conn.commit()
    finally:
        conn.close()
    return None


@router.post("/users/{user_id}/reset-link")
async def create_reset_link(
    user_id: int,
    admin: UserInDB = Depends(get_current_admin),  # noqa: B008
):
    """A fresh 24 h reset link; earlier unused reset links for the user are revoked."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        target = _target(cursor, user_id)
        if target["disabled"]:
            raise HTTPException(status_code=422, detail="Enable the account first.")
        cursor.execute(
            "UPDATE auth_links SET revoked_at = ? WHERE kind = 'reset' AND user_id = ? "
            "AND used_at IS NULL AND revoked_at IS NULL",
            (utc_now(), user_id),
        )
        link = auth_links.create_link(
            cursor,
            "reset",
            created_by=admin.id,
            lifetime=timedelta(hours=auth_links.RESET_HOURS),
            user_id=user_id,
        )
        conn.commit()
    finally:
        conn.close()
    return {"token": link["token"], "expires_at": link["expires_at"], "email": target["email"]}


def _delete_user_data(cursor, user_id: int) -> List[str]:
    """Delete a user and everything they own; return their recipe uuids (for images)."""
    uuids = [
        r["uuid"] for r in cursor.execute("SELECT uuid FROM recipes WHERE user_id = ?", (user_id,))
    ]
    if uuids:
        marks = ",".join("?" * len(uuids))
        # Their recipes, wherever they're referenced (incl. other users' cookbooks/plans).
        cursor.execute(f"DELETE FROM recipe_tags WHERE recipe_uuid IN ({marks})", uuids)
        cursor.execute(f"DELETE FROM cookbook_recipes WHERE recipe_uuid IN ({marks})", uuids)
        cursor.execute(f"DELETE FROM meal_plan_entries WHERE recipe_uuid IN ({marks})", uuids)
        doomed_courses = f"SELECT id FROM menu_courses WHERE recipe_uuid IN ({marks})"
        cursor.execute(f"DELETE FROM menu_steps WHERE course_id IN ({doomed_courses})", uuids)
        cursor.execute(f"DELETE FROM menu_courses WHERE recipe_uuid IN ({marks})", uuids)
        cursor.execute(f"DELETE FROM recipes WHERE uuid IN ({marks})", uuids)

    owned_books = "SELECT id FROM cookbooks WHERE owner_id = ?"
    cursor.execute(f"DELETE FROM cookbook_recipes WHERE cookbook_id IN ({owned_books})", (user_id,))
    cursor.execute(f"DELETE FROM cookbook_members WHERE cookbook_id IN ({owned_books})", (user_id,))
    cursor.execute("DELETE FROM cookbooks WHERE owner_id = ?", (user_id,))
    cursor.execute("DELETE FROM cookbook_members WHERE user_id = ?", (user_id,))

    tag_ids = "SELECT id FROM tags WHERE user_id = ?"
    cursor.execute(f"DELETE FROM recipe_tags WHERE tag_id IN ({tag_ids})", (user_id,))
    cursor.execute("DELETE FROM tags WHERE user_id = ?", (user_id,))
    cursor.execute("DELETE FROM meal_plan_entries WHERE user_id = ?", (user_id,))
    owned_menus = "SELECT id FROM menus WHERE user_id = ?"
    cursor.execute(f"DELETE FROM menu_members WHERE menu_id IN ({owned_menus})", (user_id,))
    cursor.execute("DELETE FROM menu_members WHERE user_id = ?", (user_id,))
    cursor.execute(f"DELETE FROM menu_steps WHERE menu_id IN ({owned_menus})", (user_id,))
    cursor.execute(f"DELETE FROM menu_courses WHERE menu_id IN ({owned_menus})", (user_id,))
    cursor.execute("DELETE FROM menus WHERE user_id = ?", (user_id,))
    cursor.execute("DELETE FROM shopping_lists WHERE user_id = ?", (user_id,))
    cursor.execute(
        "DELETE FROM friendships WHERE requester_id = ? OR addressee_id = ?", (user_id, user_id)
    )
    cursor.execute("DELETE FROM google_integrations WHERE user_id = ?", (user_id,))
    cursor.execute("DELETE FROM auth_links WHERE user_id = ?", (user_id,))

    # Keep other people's rows, just forget who did it.
    cursor.execute("UPDATE cookbook_recipes SET added_by = NULL WHERE added_by = ?", (user_id,))
    cursor.execute("UPDATE cookbook_members SET invited_by = NULL WHERE invited_by = ?", (user_id,))
    cursor.execute("UPDATE menu_members SET invited_by = NULL WHERE invited_by = ?", (user_id,))
    cursor.execute("UPDATE users SET invited_by = NULL WHERE invited_by = ?", (user_id,))
    cursor.execute("UPDATE auth_links SET created_by = NULL WHERE created_by = ?", (user_id,))
    cursor.execute("UPDATE auth_links SET used_by = NULL WHERE used_by = ?", (user_id,))

    cursor.execute("DELETE FROM users WHERE id = ?", (user_id,))
    return uuids


@router.delete("/users/{user_id}", status_code=204)
async def delete_user(
    user_id: int,
    confirm: str = Query(..., description="The user's email, typed to confirm"),
    admin: UserInDB = Depends(get_current_admin),  # noqa: B008
):
    if user_id == admin.id:
        raise HTTPException(status_code=422, detail="You can't delete your own account.")
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        target = _target(cursor, user_id)
        if confirm.strip().lower() != target["email"].lower():
            raise HTTPException(status_code=422, detail="The confirmation doesn't match the email.")
        uuids = _delete_user_data(cursor, user_id)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    for recipe_uuid in uuids:
        recipe_images.delete_image(recipe_uuid)
    return None


# ---------------------------------------------------------------------------
# Sign-up links
# ---------------------------------------------------------------------------


def _invite_json(row) -> Dict[str, Any]:
    return {
        "id": row["id"],
        "email": row["email"],
        "note": row["note"] or "",
        "created_at": row["created_at"],
        "expires_at": row["expires_at"],
        "created_by": row["created_by_email"],
        "used_by": row["used_by_email"],
        "used_at": row["used_at"],
        "status": auth_links.link_status(row),
    }


@router.get("/invites")
async def list_invites(admin: UserInDB = Depends(get_current_admin)):  # noqa: B008
    conn = get_db_connection()
    try:
        rows = conn.execute(
            """
            SELECT l.*, c.email AS created_by_email, u.email AS used_by_email
            FROM auth_links l
            LEFT JOIN users c ON c.id = l.created_by
            LEFT JOIN users u ON u.id = l.used_by
            WHERE l.kind = 'signup'
            ORDER BY l.created_at DESC
            """
        ).fetchall()
    finally:
        conn.close()
    return [_invite_json(r) for r in rows]


class InviteCreate(BaseModel):
    email: Optional[str] = None
    note: Optional[str] = None
    expires_in_days: int = auth_links.SIGNUP_DEFAULT_DAYS


@router.post("/invites")
async def create_invite(
    body: InviteCreate,
    admin: UserInDB = Depends(get_current_admin),  # noqa: B008
):
    """A sign-up link, optionally locked to one email. The token is only returned here."""
    if not 1 <= body.expires_in_days <= auth_links.SIGNUP_MAX_DAYS:
        raise HTTPException(
            status_code=422,
            detail=f"Validity must be between 1 and {auth_links.SIGNUP_MAX_DAYS} days",
        )
    email = (body.email or "").strip().lower() or None
    if email and ("@" not in email or " " in email):
        raise HTTPException(status_code=422, detail="Enter a valid email address")
    note = (body.note or "").strip()[:200] or None
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        if (
            email
            and cursor.execute(
                "SELECT 1 FROM users WHERE email = ? COLLATE NOCASE", (email,)
            ).fetchone()
        ):
            raise HTTPException(status_code=409, detail="A user with this email already exists.")
        link = auth_links.create_link(
            cursor,
            "signup",
            created_by=admin.id,
            lifetime=timedelta(days=body.expires_in_days),
            email=email,
            note=note,
        )
        conn.commit()
        row = cursor.execute(
            "SELECT l.*, ? AS created_by_email, NULL AS used_by_email FROM auth_links l "
            "WHERE l.id = ?",
            (admin.email, link["id"]),
        ).fetchone()
    finally:
        conn.close()
    return {**_invite_json(row), "token": link["token"]}


@router.delete("/invites/{invite_id}", status_code=204)
async def revoke_invite(
    invite_id: int,
    admin: UserInDB = Depends(get_current_admin),  # noqa: B008
):
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE auth_links SET revoked_at = COALESCE(revoked_at, ?) "
            "WHERE id = ? AND kind = 'signup'",
            (utc_now(), invite_id),
        )
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Link not found")
        conn.commit()
    finally:
        conn.close()
    return None


# ---------------------------------------------------------------------------
# Friendships
# ---------------------------------------------------------------------------


def _person(row, prefix: str) -> Dict[str, Any]:
    return {
        "user_id": row[f"{prefix}_id"],
        "email": row[f"{prefix}_email"],
        "display_name": row[f"{prefix}_name"] or "",
    }


@router.get("/friendships")
async def list_friendships(
    user_id: Optional[int] = Query(None),
    status: Optional[str] = Query(None),
    admin: UserInDB = Depends(get_current_admin),  # noqa: B008
):
    """Every friendship or pending request, optionally for one user / status."""
    where, params = [], []
    if user_id is not None:
        where.append("(f.requester_id = ? OR f.addressee_id = ?)")
        params += [user_id, user_id]
    if status is not None:
        where.append("f.status = ?")
        params.append(status)
    conn = get_db_connection()
    try:
        rows = conn.execute(
            "SELECT f.id, f.status, f.created_at, f.responded_at, "
            "a.id AS a_id, a.email AS a_email, a.display_name AS a_name, "
            "b.id AS b_id, b.email AS b_email, b.display_name AS b_name "
            "FROM friendships f JOIN users a ON a.id = f.requester_id "
            "JOIN users b ON b.id = f.addressee_id "
            + ("WHERE " + " AND ".join(where) + " " if where else "")
            + "ORDER BY a.email COLLATE NOCASE, b.email COLLATE NOCASE",
            params,
        ).fetchall()
    finally:
        conn.close()
    return [
        {
            "id": r["id"],
            "status": r["status"],
            "created_at": r["created_at"],
            "responded_at": r["responded_at"],
            "requester": _person(r, "a"),
            "addressee": _person(r, "b"),
        }
        for r in rows
    ]


class FriendshipCreate(BaseModel):
    user_a: int
    user_b: int


def _connect(cursor, a: int, b: int) -> bool:
    """Make ``a`` and ``b`` friends (accepting a pending request). False if they already were."""
    row = cursor.execute(
        "SELECT id, status FROM friendships WHERE "
        "(requester_id = ? AND addressee_id = ?) OR (requester_id = ? AND addressee_id = ?)",
        (a, b, b, a),
    ).fetchone()
    if row is not None and row["status"] == "accepted":
        return False
    if row is not None:
        cursor.execute(
            "UPDATE friendships SET status = 'accepted', responded_at = CURRENT_TIMESTAMP "
            "WHERE id = ?",
            (row["id"],),
        )
    else:
        cursor.execute(
            "INSERT INTO friendships (requester_id, addressee_id, status, responded_at) "
            "VALUES (?, ?, 'accepted', CURRENT_TIMESTAMP)",
            (a, b),
        )
    return True


@router.post("/friendships", status_code=201)
async def create_friendship(
    body: FriendshipCreate,
    admin: UserInDB = Depends(get_current_admin),  # noqa: B008
):
    """Make two users friends right away (or accept a pending request between them)."""
    if body.user_a == body.user_b:
        raise HTTPException(status_code=422, detail="Pick two different users")
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        _target(cursor, body.user_a)
        _target(cursor, body.user_b)
        if not _connect(cursor, body.user_a, body.user_b):
            raise HTTPException(status_code=409, detail="They're already friends")
        conn.commit()
    finally:
        conn.close()
    return {"ok": True}


@router.delete("/friendships/{friendship_id}", status_code=204)
async def delete_friendship(
    friendship_id: int,
    admin: UserInDB = Depends(get_current_admin),  # noqa: B008
):
    """Remove a friendship or request, and every share between the two users."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        row = cursor.execute(
            "SELECT requester_id, addressee_id FROM friendships WHERE id = ?", (friendship_id,)
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Friendship not found")
        cursor.execute("DELETE FROM friendships WHERE id = ?", (friendship_id,))
        revoke_shares_between(cursor, row["requester_id"], row["addressee_id"])
        conn.commit()
    finally:
        conn.close()
    return None


# ---------------------------------------------------------------------------
# Shares (menus + cookbooks)
# ---------------------------------------------------------------------------

ShareType = Literal["menu", "cookbook"]
COOKBOOK_ROLES = ("viewer", "editor", "manager")

# Per type: (members table, resource table, member's resource column, owner column).
_SHARE_TABLES = {
    "menu": ("menu_members", "menus", "menu_id", "user_id"),
    "cookbook": ("cookbook_members", "cookbooks", "cookbook_id", "owner_id"),
}


def _valid_role(type_: str, role: str) -> None:
    if role not in (MENU_ROLES if type_ == "menu" else COOKBOOK_ROLES):
        raise HTTPException(status_code=422, detail="Invalid role for this share")


def _resource_owner(cursor, type_: str, resource_id: int) -> int:
    _, table, _, owner_col = _SHARE_TABLES[type_]
    row = cursor.execute(
        f"SELECT {owner_col} AS owner_id FROM {table} WHERE id = ?", (resource_id,)
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Not found")
    return row["owner_id"]


_SHARES_SQL = """
SELECT 'menu' AS type, m.id AS resource_id, m.title AS resource_name, NULL AS kind,
       mm.role, mm.status, mm.created_at,
       o.id AS o_id, o.email AS o_email, o.display_name AS o_name,
       g.id AS g_id, g.email AS g_email, g.display_name AS g_name
FROM menu_members mm JOIN menus m ON m.id = mm.menu_id
JOIN users o ON o.id = m.user_id JOIN users g ON g.id = mm.user_id
UNION ALL
SELECT 'cookbook', c.id, c.name, c.kind, cm.role, cm.status, cm.created_at,
       o.id, o.email, o.display_name, g.id, g.email, g.display_name
FROM cookbook_members cm JOIN cookbooks c ON c.id = cm.cookbook_id
JOIN users o ON o.id = c.owner_id JOIN users g ON g.id = cm.user_id
"""


@router.get("/shares")
async def list_shares(
    user_id: Optional[int] = Query(None),
    type: Optional[ShareType] = Query(None),  # noqa: A002, B008
    admin: UserInDB = Depends(get_current_admin),  # noqa: B008
):
    """Every menu and cookbook share (pending or accepted), optionally narrowed to
    one user (as owner or grantee) and one type."""
    where, params = [], []
    if user_id is not None:
        where.append("(o_id = ? OR g_id = ?)")
        params += [user_id, user_id]
    if type is not None:
        where.append("type = ?")
        params.append(type)
    conn = get_db_connection()
    try:
        rows = conn.execute(
            f"SELECT * FROM ({_SHARES_SQL}) "
            + ("WHERE " + " AND ".join(where) + " " if where else "")
            + "ORDER BY o_email COLLATE NOCASE, resource_name COLLATE NOCASE, g_email",
            params,
        ).fetchall()
    finally:
        conn.close()
    return [
        {
            "type": r["type"],
            "resource_id": r["resource_id"],
            "resource_name": r["resource_name"],
            "cookbook_kind": r["kind"],
            "role": r["role"],
            "status": r["status"],
            "created_at": r["created_at"],
            "owner": _person(r, "o"),
            "grantee": _person(r, "g"),
        }
        for r in rows
    ]


class ShareCreate(BaseModel):
    type: ShareType
    resource_id: int
    user_id: int
    role: str
    ensure_friends: bool = False


@router.post("/shares", status_code=201)
async def create_share(
    body: ShareCreate,
    admin: UserInDB = Depends(get_current_admin),  # noqa: B008
):
    """Share a user's menu or cookbook with another user, accepted at once.

    The two must be friends (409 otherwise) unless ``ensure_friends`` is set,
    which connects them in the same transaction. An existing share gets the new
    role and is accepted.
    """
    _valid_role(body.type, body.role)
    members, _, col, _ = _SHARE_TABLES[body.type]
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        owner_id = _resource_owner(cursor, body.type, body.resource_id)
        _target(cursor, body.user_id)
        if body.user_id == owner_id:
            raise HTTPException(status_code=422, detail="That user owns it")
        if not are_friends(cursor, owner_id, body.user_id):
            if not body.ensure_friends:
                raise HTTPException(status_code=409, detail="They aren't friends")
            _connect(cursor, owner_id, body.user_id)
        cursor.execute(
            f"INSERT INTO {members} ({col}, user_id, role, status, invited_by, responded_at) "
            "VALUES (?, ?, ?, 'accepted', ?, CURRENT_TIMESTAMP) "
            f"ON CONFLICT({col}, user_id) DO UPDATE SET role = excluded.role, "
            "status = 'accepted', responded_at = CURRENT_TIMESTAMP",
            (body.resource_id, body.user_id, body.role, admin.id),
        )
        conn.commit()
    finally:
        conn.close()
    return {"ok": True}


class ShareRole(BaseModel):
    role: str


@router.patch("/shares/{type}/{resource_id}/{user_id}", status_code=204)
async def update_share(
    type: ShareType,  # noqa: A002
    resource_id: int,
    user_id: int,
    body: ShareRole,
    admin: UserInDB = Depends(get_current_admin),  # noqa: B008
):
    _valid_role(type, body.role)
    members, _, col, _ = _SHARE_TABLES[type]
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            f"UPDATE {members} SET role = ? WHERE {col} = ? AND user_id = ?",
            (body.role, resource_id, user_id),
        )
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Share not found")
        conn.commit()
    finally:
        conn.close()
    return None


@router.delete("/shares/{type}/{resource_id}/{user_id}", status_code=204)
async def delete_share(
    type: ShareType,  # noqa: A002
    resource_id: int,
    user_id: int,
    admin: UserInDB = Depends(get_current_admin),  # noqa: B008
):
    members, _, col, _ = _SHARE_TABLES[type]
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            f"DELETE FROM {members} WHERE {col} = ? AND user_id = ?", (resource_id, user_id)
        )
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Share not found")
        conn.commit()
    finally:
        conn.close()
    return None


@router.get("/users/{user_id}/resources")
async def list_user_resources(
    user_id: int,
    type: ShareType = Query(...),  # noqa: A002, B008
    admin: UserInDB = Depends(get_current_admin),  # noqa: B008
):
    """A user's own menus or cookbooks, for picking what to share."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        _target(cursor, user_id)
        if type == "menu":
            rows = cursor.execute(
                "SELECT id, title AS name, date AS detail FROM menus WHERE user_id = ? "
                "ORDER BY COALESCE(date, '9999-12-31') DESC, id DESC",
                (user_id,),
            ).fetchall()
        else:
            rows = cursor.execute(
                "SELECT id, name, kind AS detail FROM cookbooks WHERE owner_id = ? "
                "ORDER BY name COLLATE NOCASE",
                (user_id,),
            ).fetchall()
    finally:
        conn.close()
    return [{"id": r["id"], "name": r["name"], "detail": r["detail"]} for r in rows]

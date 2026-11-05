"""Admin control plane — every route requires ``users.is_admin`` (403 otherwise).

- ``GET    /admin/users`` — all users with usage stats.
- ``PATCH  /admin/users/{id}`` — ``{is_admin?, disabled?}``.
- ``POST   /admin/users/{id}/logout`` — revoke every session of a user.
- ``POST   /admin/users/{id}/reset-link`` — one-time password-reset link (24 h).
- ``DELETE /admin/users/{id}?confirm=<email>`` — delete a user and all their data.
- ``GET    /admin/invites`` / ``POST /admin/invites`` / ``DELETE /admin/invites/{id}``
  — sign-up links.

Guard rails: an admin can't demote, disable or delete themselves, and the last
admin can't be demoted. Link tokens are returned only by the create calls.
"""

from datetime import timedelta
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from api import auth_links, recipe_images
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
    cursor.execute("DELETE FROM shopping_lists WHERE user_id = ?", (user_id,))
    cursor.execute(
        "DELETE FROM friendships WHERE requester_id = ? OR addressee_id = ?", (user_id, user_id)
    )
    cursor.execute("DELETE FROM google_integrations WHERE user_id = ?", (user_id,))
    cursor.execute("DELETE FROM auth_links WHERE user_id = ?", (user_id,))

    # Keep other people's rows, just forget who did it.
    cursor.execute("UPDATE cookbook_recipes SET added_by = NULL WHERE added_by = ?", (user_id,))
    cursor.execute("UPDATE cookbook_members SET invited_by = NULL WHERE invited_by = ?", (user_id,))
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

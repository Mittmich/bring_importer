"""Friend graph endpoints — Phase 1 of recipe sharing.

Friendships are the gate for all sharing: you can only share with an accepted
friend. One canonical ``friendships`` row per pair (requester -> addressee); a
``pending`` row is an outstanding request, ``accepted`` is a friendship. See
``.claude/plans/friends-cookbooks-sharing.md``.
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, EmailStr

from api.auth import get_current_user, get_user_id
from api.db import get_db_connection
from api.models import User

router = APIRouter(prefix="/friends", tags=["friends"])


class FriendRequestBody(BaseModel):
    email: EmailStr


def _require_me(current_user: User) -> int:
    uid = get_user_id(current_user.email)
    if uid is None:
        raise HTTPException(status_code=401, detail="Unknown user")
    return uid


@router.post("/requests", include_in_schema=False)
async def send_friend_request(
    body: FriendRequestBody,
    current_user: User = Depends(get_current_user),  # noqa: B008
):
    """Send a friend request to a user by email.

    If that person has *already* sent you a pending request, this accepts it
    (mutual intent → instant friendship).
    """
    me = _require_me(current_user)
    conn = get_db_connection()
    cursor = conn.cursor()

    target = cursor.execute(
        "SELECT id, email FROM users WHERE email = ? COLLATE NOCASE", (body.email,)
    ).fetchone()
    if target is None:
        conn.close()
        raise HTTPException(status_code=404, detail="No user with that email")
    other = target["id"]
    if other == me:
        conn.close()
        raise HTTPException(status_code=422, detail="You can't add yourself")

    existing = cursor.execute(
        "SELECT id, requester_id, status FROM friendships "
        "WHERE (requester_id = ? AND addressee_id = ?) OR (requester_id = ? AND addressee_id = ?)",
        (me, other, other, me),
    ).fetchone()

    if existing is not None:
        if existing["status"] == "accepted":
            conn.close()
            raise HTTPException(status_code=409, detail="You're already friends")
        if existing["status"] == "pending":
            if existing["requester_id"] == other:
                # They already asked you — accept it.
                cursor.execute(
                    "UPDATE friendships SET status = 'accepted', "
                    "responded_at = CURRENT_TIMESTAMP WHERE id = ?",
                    (existing["id"],),
                )
                conn.commit()
                conn.close()
                return {"status": "accepted", "user": {"id": other, "email": target["email"]}}
            conn.close()
            raise HTTPException(status_code=409, detail="Request already sent")
        conn.close()
        raise HTTPException(status_code=409, detail="Can't send a request to this user")

    cursor.execute(
        "INSERT INTO friendships (requester_id, addressee_id, status) VALUES (?, ?, 'pending')",
        (me, other),
    )
    conn.commit()
    conn.close()
    return {"status": "pending", "user": {"id": other, "email": target["email"]}}


@router.get("", include_in_schema=False)
async def list_friends(current_user: User = Depends(get_current_user)):  # noqa: B008
    """List the current user's accepted friends."""
    me = _require_me(current_user)
    conn = get_db_connection()
    cursor = conn.cursor()
    rows = cursor.execute(
        "SELECT u.id AS user_id, u.email AS email FROM friendships f "
        "JOIN users u ON u.id = CASE WHEN f.requester_id = ? THEN f.addressee_id "
        "ELSE f.requester_id END "
        "WHERE f.status = 'accepted' AND (f.requester_id = ? OR f.addressee_id = ?) "
        "ORDER BY u.email COLLATE NOCASE",
        (me, me, me),
    ).fetchall()
    conn.close()
    return [{"user_id": r["user_id"], "email": r["email"]} for r in rows]


@router.get("/requests", include_in_schema=False)
async def list_requests(
    direction: str = Query("incoming"),
    current_user: User = Depends(get_current_user),  # noqa: B008
):
    """List pending friend requests — ``direction=incoming`` (default) or ``outgoing``."""
    me = _require_me(current_user)
    if direction not in ("incoming", "outgoing"):
        raise HTTPException(status_code=422, detail="direction must be incoming or outgoing")

    conn = get_db_connection()
    cursor = conn.cursor()
    if direction == "incoming":
        rows = cursor.execute(
            "SELECT f.id AS id, u.id AS user_id, u.email AS email, f.created_at AS created_at "
            "FROM friendships f JOIN users u ON u.id = f.requester_id "
            "WHERE f.addressee_id = ? AND f.status = 'pending' ORDER BY f.created_at DESC",
            (me,),
        ).fetchall()
    else:
        rows = cursor.execute(
            "SELECT f.id AS id, u.id AS user_id, u.email AS email, f.created_at AS created_at "
            "FROM friendships f JOIN users u ON u.id = f.addressee_id "
            "WHERE f.requester_id = ? AND f.status = 'pending' ORDER BY f.created_at DESC",
            (me,),
        ).fetchall()
    conn.close()
    return [
        {
            "id": r["id"],
            "user_id": r["user_id"],
            "email": r["email"],
            "direction": direction,
            "created_at": r["created_at"],
        }
        for r in rows
    ]


def _pending_addressed_to(cursor, req_id: int, me: int) -> Optional[dict]:
    """Return the pending request row iff it exists and is addressed to ``me``."""
    row = cursor.execute(
        "SELECT id, addressee_id, status FROM friendships WHERE id = ?", (req_id,)
    ).fetchone()
    if row is None or row["addressee_id"] != me or row["status"] != "pending":
        return None
    return row


@router.post("/requests/{req_id}/accept", include_in_schema=False)
async def accept_request(
    req_id: int,
    current_user: User = Depends(get_current_user),  # noqa: B008
):
    """Accept an incoming friend request. 404 (not 403) if it isn't yours to accept."""
    me = _require_me(current_user)
    conn = get_db_connection()
    cursor = conn.cursor()
    if _pending_addressed_to(cursor, req_id, me) is None:
        conn.close()
        raise HTTPException(status_code=404, detail="Request not found")
    cursor.execute(
        "UPDATE friendships SET status = 'accepted', responded_at = CURRENT_TIMESTAMP WHERE id = ?",
        (req_id,),
    )
    conn.commit()
    conn.close()
    return {"status": "accepted"}


@router.post("/requests/{req_id}/decline", include_in_schema=False, status_code=204)
async def decline_request(
    req_id: int,
    current_user: User = Depends(get_current_user),  # noqa: B008
):
    """Decline an incoming friend request (deletes it, so it can be re-sent later)."""
    me = _require_me(current_user)
    conn = get_db_connection()
    cursor = conn.cursor()
    if _pending_addressed_to(cursor, req_id, me) is None:
        conn.close()
        raise HTTPException(status_code=404, detail="Request not found")
    cursor.execute("DELETE FROM friendships WHERE id = ?", (req_id,))
    conn.commit()
    conn.close()
    return None


@router.delete("/{user_id}", include_in_schema=False, status_code=204)
async def unfriend(
    user_id: int,
    current_user: User = Depends(get_current_user),  # noqa: B008
):
    """Remove any friendship or pending request between the current user and ``user_id``.

    Also cancels an outgoing request and **revokes all cookbook shares between the
    two users, in both directions** — unfriending is a clean cutoff.
    """
    me = _require_me(current_user)
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "DELETE FROM friendships "
        "WHERE (requester_id = ? AND addressee_id = ?) OR (requester_id = ? AND addressee_id = ?)",
        (me, user_id, user_id, me),
    )
    # Revoke shares in both directions: the other user's membership in my
    # cookbooks, and my membership in theirs.
    cursor.execute(
        "DELETE FROM cookbook_members WHERE "
        "(user_id = ? AND cookbook_id IN (SELECT id FROM cookbooks WHERE owner_id = ?)) OR "
        "(user_id = ? AND cookbook_id IN (SELECT id FROM cookbooks WHERE owner_id = ?))",
        (user_id, me, me, user_id),
    )
    conn.commit()
    conn.close()
    return None

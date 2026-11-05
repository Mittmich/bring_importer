"""One-time links: admin-issued sign-up invites and password resets.

A link is ``<origin>/signup/<token>`` or ``<origin>/reset/<token>``. The token
is 32 random bytes (URL-safe base64) and is only ever returned once, when the
link is created; the database stores its SHA-256, so a leaked DB yields no
usable links. A link is usable while it is unused, unrevoked and unexpired.
"""

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

SIGNUP_DEFAULT_DAYS = 7
SIGNUP_MAX_DAYS = 30
RESET_HOURS = 24


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def create_link(
    cursor,
    kind: str,
    created_by: Optional[int],
    lifetime: timedelta,
    email: Optional[str] = None,
    user_id: Optional[int] = None,
    note: Optional[str] = None,
) -> Dict[str, Any]:
    """Insert a link and return ``{id, token, expires_at}`` (the token only here)."""
    token = secrets.token_urlsafe(32)
    now = _now()
    expires = now + lifetime
    cursor.execute(
        "INSERT INTO auth_links "
        "(kind, token_hash, email, user_id, note, created_by, created_at, expires_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            kind,
            _hash(token),
            email,
            user_id,
            note,
            created_by,
            now.isoformat(),
            expires.isoformat(),
        ),
    )
    return {"id": cursor.lastrowid, "token": token, "expires_at": expires.isoformat()}


def link_status(row) -> str:
    """``active`` | ``used`` | ``revoked`` | ``expired`` for an ``auth_links`` row."""
    if row["used_at"]:
        return "used"
    if row["revoked_at"]:
        return "revoked"
    if datetime.fromisoformat(row["expires_at"]) <= _now():
        return "expired"
    return "active"


def find_usable(cursor, token: str, kind: Optional[str] = None):
    """The ``auth_links`` row for a usable ``token`` (optionally of ``kind``), else None."""
    if not token or len(token) > 200:
        return None
    row = cursor.execute(
        "SELECT * FROM auth_links WHERE token_hash = ?", (_hash(token),)
    ).fetchone()
    if row is None or (kind and row["kind"] != kind) or link_status(row) != "active":
        return None
    return row


def mark_used(cursor, link_id: int, user_id: int) -> bool:
    """Consume a link; False if it was consumed concurrently (single use)."""
    cursor.execute(
        "UPDATE auth_links SET used_at = ?, used_by = ? WHERE id = ? AND used_at IS NULL",
        (_now().isoformat(), user_id, link_id),
    )
    return cursor.rowcount == 1

"""Authentication helpers: password hashing, JWT, current-user resolution.

The router in ``api/routers/auth.py`` exposes ``POST /token`` (login).
The dependency ``get_current_user`` is reused by ``api/routers/recipes.py``
to gate mutating endpoints; ``get_current_admin`` gates ``api/routers/admin.py``.

Sessions are revocable: every JWT carries the user's ``token_version`` as
``ver``. Bumping the version (password reset, disable, "log out everywhere")
invalidates every token issued before. Tokens without ``ver`` (issued before
this existed) count as version 0, so they stay valid until the first bump.
"""

from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt
import passlib.exc
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from passlib.context import CryptContext

from api.config import ACCESS_TOKEN_EXPIRE_MINUTES, ALGORITHM, SECRET_KEY
from api.db import get_db_connection
from api.models import UserInDB

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")
oauth2_scheme_optional = OAuth2PasswordBearer(tokenUrl="token", auto_error=False)
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def verify_password(plain_password, hashed_password):
    """Return True iff ``plain_password`` matches ``hashed_password``.

    Tolerant of unknown hash formats: ``passlib.exc.UnknownHashError`` is
    caught and treated as "no match" so users migrated from a different
    auth system don't 500 the auth check just because their stored hash
    isn't a bcrypt.
    """
    try:
        return pwd_context.verify(plain_password, hashed_password)
    except passlib.exc.UnknownHashError:
        return False


def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)  # type: ignore[no-any-return]


def get_user(email: str) -> Optional[UserInDB]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE email = ?", (email,))
    user = cursor.fetchone()
    conn.close()

    if user:
        return UserInDB(
            email=user["email"],
            password="",
            hashed_password=user["hashed_password"],
            id=user["id"],
            is_admin=bool(user["is_admin"]),
            disabled=bool(user["disabled"]),
            token_version=int(user["token_version"] or 0),
        )
    return None


def authenticate_user(email: str, password: str):
    user = get_user(email)
    if not user:
        return False
    if not verify_password(password, user.hashed_password):
        return False
    return user


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def utc_now() -> str:
    """Current UTC time as an ISO-8601 string (the format stored in the DB)."""
    return datetime.now(timezone.utc).isoformat()


def issue_access_token(user: UserInDB) -> str:
    """A login JWT for ``user``, bound to their current ``token_version``."""
    return create_access_token(
        data={"sub": user.email, "ver": user.token_version},
        expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
    )


def _user_from_token(token: str) -> Optional[UserInDB]:
    """The active user a token belongs to, or None (bad/expired/revoked/disabled)."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except jwt.PyJWTError:
        return None
    email = payload.get("sub")
    if not email:
        return None
    user = get_user(email=email)
    if user is None or user.disabled:
        return None
    if int(payload.get("ver", 0)) != user.token_version:
        return None
    return user


async def get_current_user(token: str = Depends(oauth2_scheme)) -> UserInDB:
    user = _user_from_token(token)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


async def get_current_user_optional(
    token: Optional[str] = Depends(oauth2_scheme_optional),
) -> Optional[UserInDB]:
    """Like ``get_current_user`` but returns ``None`` instead of raising 401."""
    return _user_from_token(token) if token else None


async def get_current_admin(
    current_user: UserInDB = Depends(get_current_user),  # noqa: B008
) -> UserInDB:
    """``get_current_user`` restricted to admins (403 otherwise)."""
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admins only")
    return current_user


def record_login(user_id: int) -> None:
    conn = get_db_connection()
    conn.execute("UPDATE users SET last_login_at = ? WHERE id = ?", (utc_now(), user_id))
    conn.commit()
    conn.close()


def bump_token_version(cursor, user_id: int) -> None:
    """Revoke every session of ``user_id`` (within the caller's transaction)."""
    cursor.execute("UPDATE users SET token_version = token_version + 1 WHERE id = ?", (user_id,))


def update_password(email: str, new_password: str) -> None:
    """Set a new bcrypt-hashed password for the user with ``email``."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE users SET hashed_password = ? WHERE email = ?",
        (get_password_hash(new_password), email),
    )
    conn.commit()
    conn.close()


def get_profile(email: str) -> Optional[dict]:
    """Return ``{email, display_name, language, is_admin}`` for the user, or None."""
    conn = get_db_connection()
    cursor = conn.cursor()
    row = cursor.execute(
        "SELECT email, display_name, language, is_admin FROM users WHERE email = ?", (email,)
    ).fetchone()
    conn.close()
    if row is None:
        return None
    return {
        "email": row["email"],
        "display_name": row["display_name"] or "",
        "language": row["language"],
        "is_admin": bool(row["is_admin"]),
    }


def set_display_name(email: str, display_name: str) -> None:
    """Set (or clear) a user's display name."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET display_name = ? WHERE email = ?", (display_name, email))
    conn.commit()
    conn.close()


def set_language(email: str, language: Optional[str]) -> None:
    """Set (or clear, with ``None``) a user's preferred language code."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET language = ? WHERE email = ?", (language, email))
    conn.commit()
    conn.close()


def get_user_language(user_id: int) -> Optional[str]:
    """A user's stored preferred language code, or None."""
    conn = get_db_connection()
    row = conn.execute("SELECT language FROM users WHERE id = ?", (user_id,)).fetchone()
    conn.close()
    return row["language"] if row else None


def get_user_id(email: str) -> Optional[int]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM users WHERE email = ?", (email,))
    result = cursor.fetchone()
    conn.close()
    if result:
        return int(result["id"])
    return None

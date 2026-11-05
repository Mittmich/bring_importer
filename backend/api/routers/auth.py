"""Login, account self-service, and the public side of one-time links.

- ``POST /token`` — login (refuses disabled accounts).
- ``POST /account/password`` — self-service password change.
- ``GET/PUT /account/profile`` — display name, language (+ ``is_admin``).
- ``GET /auth/links/{token}`` — what a sign-up / reset link is for.
- ``POST /auth/signup`` — create an account from an invite link.
- ``POST /auth/reset`` — set a new password from a reset link.
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel

from api import auth_links
from api.auth import (
    authenticate_user,
    bump_token_version,
    get_current_user,
    get_password_hash,
    get_profile,
    get_user,
    issue_access_token,
    record_login,
    set_display_name,
    set_language,
    update_password,
    utc_now,
    verify_password,
)
from api.db import get_db_connection
from api.i18n import SUPPORTED_LANGUAGES, normalize_language
from api.models import Token, UserInDB

MAX_DISPLAY_NAME_LENGTH = 60

# Minimum length for a new password. Kept modest — this is a personal app.
MIN_PASSWORD_LENGTH = 8

router = APIRouter(tags=["auth"])


@router.post("/token", response_model=Token)
async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends()):  # noqa: B008
    user = authenticate_user(form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if user.disabled:
        raise HTTPException(status_code=403, detail="This account has been disabled.")
    record_login(user.id)
    return {"access_token": issue_access_token(user), "token_type": "bearer"}


class ChangePasswordBody(BaseModel):
    current_password: str
    new_password: str


@router.post("/account/password", include_in_schema=False, status_code=204)
async def change_password(
    body: ChangePasswordBody,
    current_user: UserInDB = Depends(get_current_user),  # noqa: B008
):
    """Change the current user's password after re-verifying the current one.

    No session invalidation: existing JWTs keep working until they expire.
    """
    if not verify_password(body.current_password, current_user.hashed_password):
        raise HTTPException(status_code=403, detail="Current password is incorrect")
    if len(body.new_password) < MIN_PASSWORD_LENGTH:
        raise HTTPException(
            status_code=422,
            detail=f"New password must be at least {MIN_PASSWORD_LENGTH} characters",
        )
    update_password(current_user.email, body.new_password)
    return None


class ProfileBody(BaseModel):
    """Partial profile update — omitted fields are left unchanged."""

    display_name: Optional[str] = None
    language: Optional[str] = None


@router.get("/account/profile", include_in_schema=False)
async def read_profile(current_user: UserInDB = Depends(get_current_user)):  # noqa: B008
    """Return the current user's ``{email, display_name, language}``."""
    return get_profile(current_user.email) or {
        "email": current_user.email,
        "display_name": "",
        "language": None,
        "is_admin": current_user.is_admin,
    }


@router.put("/account/profile", include_in_schema=False)
async def update_profile(
    body: ProfileBody,
    current_user: UserInDB = Depends(get_current_user),  # noqa: B008
):
    """Set (or clear) the current user's display name and/or preferred language."""
    if body.display_name is not None:
        name = " ".join(body.display_name.split())
        if len(name) > MAX_DISPLAY_NAME_LENGTH:
            raise HTTPException(
                status_code=422,
                detail=f"Display name must be {MAX_DISPLAY_NAME_LENGTH} characters or fewer",
            )
        set_display_name(current_user.email, name)
    if body.language is not None:
        if body.language not in SUPPORTED_LANGUAGES:
            raise HTTPException(status_code=422, detail="Unsupported language")
        set_language(current_user.email, body.language)
    return get_profile(current_user.email)


# ---------------------------------------------------------------------------
# One-time links (invites, resets). Every failure is the same vague 404 so a
# link can't be probed for *why* it doesn't work.
# ---------------------------------------------------------------------------

INVALID_LINK = "This link is invalid or has expired."


def _check_password(password: str) -> None:
    if len(password) < MIN_PASSWORD_LENGTH:
        raise HTTPException(
            status_code=422,
            detail=f"Password must be at least {MIN_PASSWORD_LENGTH} characters",
        )


@router.get("/auth/links/{token}", include_in_schema=False)
async def describe_link(token: str):
    """``{kind, email}`` for a usable link (email: the invite's locked address or
    the reset target), else 404."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        link = auth_links.find_usable(cursor, token)
        if link is None:
            raise HTTPException(status_code=404, detail=INVALID_LINK)
        email = link["email"]
        if link["kind"] == "reset":
            target = cursor.execute(
                "SELECT email FROM users WHERE id = ?", (link["user_id"],)
            ).fetchone()
            if target is None:
                raise HTTPException(status_code=404, detail=INVALID_LINK)
            email = target["email"]
        return {"kind": link["kind"], "email": email}
    finally:
        conn.close()


class SignupBody(BaseModel):
    token: str
    email: str
    password: str
    display_name: Optional[str] = None
    language: Optional[str] = None


@router.post("/auth/signup", response_model=Token, include_in_schema=False)
async def signup(body: SignupBody):
    """Create an account from an invite link and log it in."""
    email = body.email.strip().lower()
    if "@" not in email or len(email) > 254 or " " in email:
        raise HTTPException(status_code=422, detail="Enter a valid email address")
    _check_password(body.password)
    name = " ".join((body.display_name or "").split())[:MAX_DISPLAY_NAME_LENGTH]

    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        link = auth_links.find_usable(cursor, body.token, kind="signup")
        if link is None:
            raise HTTPException(status_code=404, detail=INVALID_LINK)
        if link["email"] and link["email"].lower() != email:
            raise HTTPException(
                status_code=422, detail="This invite is for a different email address"
            )
        if cursor.execute(
            "SELECT 1 FROM users WHERE email = ? COLLATE NOCASE", (email,)
        ).fetchone():
            raise HTTPException(
                status_code=409, detail="An account with this email already exists. Log in instead."
            )
        cursor.execute(
            "INSERT INTO users (email, hashed_password, display_name, language, created_at, "
            "invited_by) VALUES (?, ?, ?, ?, ?, ?)",
            (
                email,
                get_password_hash(body.password),
                name or None,
                normalize_language(body.language),
                utc_now(),
                link["created_by"],
            ),
        )
        user_id = cursor.lastrowid
        if not auth_links.mark_used(cursor, link["id"], user_id):
            conn.rollback()
            raise HTTPException(status_code=404, detail=INVALID_LINK)
        conn.commit()
    finally:
        conn.close()

    user = get_user(email)
    assert user is not None
    record_login(user.id)
    return {"access_token": issue_access_token(user), "token_type": "bearer"}


class ResetBody(BaseModel):
    token: str
    password: str


@router.post("/auth/reset", response_model=Token, include_in_schema=False)
async def reset_password(body: ResetBody):
    """Set a new password from a reset link; logs out every other session."""
    _check_password(body.password)
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        link = auth_links.find_usable(cursor, body.token, kind="reset")
        target = (
            cursor.execute(
                "SELECT email, disabled FROM users WHERE id = ?", (link["user_id"],)
            ).fetchone()
            if link
            else None
        )
        if link is None or target is None or target["disabled"]:
            raise HTTPException(status_code=404, detail=INVALID_LINK)
        if not auth_links.mark_used(cursor, link["id"], link["user_id"]):
            raise HTTPException(status_code=404, detail=INVALID_LINK)
        cursor.execute(
            "UPDATE users SET hashed_password = ? WHERE id = ?",
            (get_password_hash(body.password), link["user_id"]),
        )
        bump_token_version(cursor, link["user_id"])
        conn.commit()
        email = target["email"]
    finally:
        conn.close()

    user = get_user(email)
    assert user is not None
    record_login(user.id)
    return {"access_token": issue_access_token(user), "token_type": "bearer"}

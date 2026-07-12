"""``POST /token`` — login; ``POST /account/password`` — self-service password change."""

from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel

from api.auth import (
    authenticate_user,
    create_access_token,
    get_current_user,
    get_profile,
    set_display_name,
    update_password,
    verify_password,
)
from api.config import ACCESS_TOKEN_EXPIRE_MINUTES
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
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(data={"sub": user.email}, expires_delta=access_token_expires)
    return {"access_token": access_token, "token_type": "bearer"}


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
    display_name: str


@router.get("/account/profile", include_in_schema=False)
async def read_profile(current_user: UserInDB = Depends(get_current_user)):  # noqa: B008
    """Return the current user's ``{email, display_name}``."""
    return get_profile(current_user.email) or {"email": current_user.email, "display_name": ""}


@router.put("/account/profile", include_in_schema=False)
async def update_profile(
    body: ProfileBody,
    current_user: UserInDB = Depends(get_current_user),  # noqa: B008
):
    """Set (or clear) the current user's display name."""
    name = " ".join(body.display_name.split())
    if len(name) > MAX_DISPLAY_NAME_LENGTH:
        raise HTTPException(
            status_code=422,
            detail=f"Display name must be {MAX_DISPLAY_NAME_LENGTH} characters or fewer",
        )
    set_display_name(current_user.email, name)
    return {"email": current_user.email, "display_name": name}

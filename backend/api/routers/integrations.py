"""Google Calendar OAuth + integration management (server-side code flow).

- ``GET /integrations/google/connect`` — auth; returns the consent URL.
- ``GET /integrations/google/callback`` — public; stores the refresh token, redirects to the app.
- ``GET /integrations/google/status`` — auth; connected? + selected calendar.
- ``GET /integrations/google/calendars`` — auth; list the user's calendars.
- ``PUT /integrations/google/calendar`` — auth; set the target calendar.
- ``DELETE /integrations/google/connect`` — auth; disconnect.
"""

from datetime import datetime, timedelta
from typing import Optional

import jwt
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from api import google_calendar as gcal
from api.auth import get_current_user, get_user_id
from api.config import ALGORITHM, SECRET_KEY, app_origin, google_oauth_configured
from api.db import get_db_connection
from api.models import User

router = APIRouter(prefix="/integrations/google", tags=["integrations"])

_STATE_PURPOSE = "google_connect"


def _require_user_id(current_user: User) -> int:
    user_id = get_user_id(current_user.email)
    if user_id is None:
        raise HTTPException(status_code=401, detail="Unknown user")
    return user_id


def _encode_state(email: str) -> str:
    payload = {
        "sub": email,
        "purpose": _STATE_PURPOSE,
        "exp": datetime.utcnow() + timedelta(minutes=10),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def _decode_state(state: str) -> Optional[str]:
    try:
        payload = jwt.decode(state, SECRET_KEY, algorithms=[ALGORITHM])
    except jwt.PyJWTError:
        return None
    if payload.get("purpose") != _STATE_PURPOSE:
        return None
    return payload.get("sub")


@router.get("/connect")
async def connect(current_user: User = Depends(get_current_user)):  # noqa: B008
    """Return the Google consent URL for the current user to start the flow."""
    if not google_oauth_configured():
        raise HTTPException(status_code=503, detail="Google Calendar is not configured")
    _require_user_id(current_user)
    state = _encode_state(current_user.email)
    return {"url": gcal.build_auth_url(state)}


@router.get("/callback")
async def callback(
    code: Optional[str] = None,
    state: Optional[str] = None,
    error: Optional[str] = None,
):
    """OAuth redirect target: store the refresh token and bounce back to the app."""
    origin = app_origin()
    if error or not code or not state:
        return RedirectResponse(url=f"{origin}/plan?google=error")

    email = _decode_state(state)
    if email is None:
        return RedirectResponse(url=f"{origin}/plan?google=error")

    user_id = get_user_id(email)
    if user_id is None:
        return RedirectResponse(url=f"{origin}/plan?google=error")

    tokens = await gcal.exchange_code(code)
    refresh_token = tokens.get("refresh_token")
    if not refresh_token:
        # No refresh token (e.g. user previously consented without revoking).
        return RedirectResponse(url=f"{origin}/plan?google=error")

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO google_integrations (user_id, refresh_token, calendar_id, updated_at) "
        "VALUES (?, ?, 'primary', CURRENT_TIMESTAMP) "
        "ON CONFLICT(user_id) DO UPDATE SET refresh_token = excluded.refresh_token, "
        "updated_at = CURRENT_TIMESTAMP",
        (user_id, refresh_token),
    )
    conn.commit()
    conn.close()
    return RedirectResponse(url=f"{origin}/plan?google=connected")


@router.get("/status")
async def status(current_user: User = Depends(get_current_user)):  # noqa: B008
    """Whether the user has connected Google Calendar, and the chosen calendar."""
    user_id = _require_user_id(current_user)
    conn = get_db_connection()
    cursor = conn.cursor()
    row = cursor.execute(
        "SELECT calendar_id FROM google_integrations WHERE user_id = ?",
        (user_id,),
    ).fetchone()
    conn.close()
    return {
        "configured": google_oauth_configured(),
        "connected": row is not None,
        "calendar_id": row["calendar_id"] if row else None,
    }


async def _access_token_for(user_id: int) -> str:
    """Load the refresh token and mint an access token, or 400 if not connected."""
    conn = get_db_connection()
    cursor = conn.cursor()
    row = cursor.execute(
        "SELECT refresh_token FROM google_integrations WHERE user_id = ?",
        (user_id,),
    ).fetchone()
    conn.close()
    if row is None:
        raise HTTPException(status_code=400, detail="Google Calendar not connected")
    return await gcal.refresh_access_token(row["refresh_token"])


@router.get("/calendars")
async def calendars(current_user: User = Depends(get_current_user)):  # noqa: B008
    """List the user's Google calendars."""
    user_id = _require_user_id(current_user)
    token = await _access_token_for(user_id)
    return await gcal.list_calendars(token)


class CalendarSelect(BaseModel):
    calendar_id: str


@router.put("/calendar", status_code=204)
async def set_calendar(
    body: CalendarSelect,
    current_user: User = Depends(get_current_user),  # noqa: B008
):
    """Set the target calendar for meal-plan sync."""
    user_id = _require_user_id(current_user)
    conn = get_db_connection()
    cursor = conn.cursor()
    updated = cursor.execute(
        "UPDATE google_integrations SET calendar_id = ?, updated_at = CURRENT_TIMESTAMP "
        "WHERE user_id = ?",
        (body.calendar_id, user_id),
    ).rowcount
    conn.commit()
    conn.close()
    if not updated:
        raise HTTPException(status_code=400, detail="Google Calendar not connected")
    return None


@router.delete("/connect", status_code=204)
async def disconnect(current_user: User = Depends(get_current_user)):  # noqa: B008
    """Disconnect Google Calendar; clears stored event ids so a future connect re-syncs."""
    user_id = _require_user_id(current_user)
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM google_integrations WHERE user_id = ?", (user_id,))
    cursor.execute(
        "UPDATE meal_plan_entries SET google_event_id = NULL WHERE user_id = ?",
        (user_id,),
    )
    conn.commit()
    conn.close()
    return None

"""Google Calendar via the server-side OAuth code flow, using httpx directly.

Kept SDK-free to stay consistent with the rest of the backend and to avoid
pulling the google-api-python-client stack into the image. All network calls
are async so they can be awaited from the async routers without blocking.
"""

from datetime import datetime, timedelta
from typing import Any, Dict, List
from urllib.parse import urlencode

import httpx
from fastapi import HTTPException

from api.config import (
    GOOGLE_CLIENT_ID,
    GOOGLE_CLIENT_SECRET,
    GOOGLE_REDIRECT_URI,
)

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
CALENDAR_BASE = "https://www.googleapis.com/calendar/v3"
SCOPE = "https://www.googleapis.com/auth/calendar"

_TIMEOUT = 15.0


def build_auth_url(state: str) -> str:
    """Build the Google consent URL. ``access_type=offline`` + ``prompt=consent``
    so we receive a refresh token."""
    params = {
        "client_id": GOOGLE_CLIENT_ID,
        "redirect_uri": GOOGLE_REDIRECT_URI,
        "response_type": "code",
        "scope": SCOPE,
        "access_type": "offline",
        "prompt": "consent",
        "include_granted_scopes": "true",
        "state": state,
    }
    return f"{AUTH_URL}?{urlencode(params)}"


async def exchange_code(code: str) -> Dict[str, Any]:
    """Exchange an authorization code for tokens (incl. a refresh token)."""
    data = {
        "code": code,
        "client_id": GOOGLE_CLIENT_ID,
        "client_secret": GOOGLE_CLIENT_SECRET,
        "redirect_uri": GOOGLE_REDIRECT_URI,
        "grant_type": "authorization_code",
    }
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.post(TOKEN_URL, data=data)
    if resp.status_code != 200:
        raise HTTPException(status_code=400, detail="Google token exchange failed")
    return resp.json()


async def refresh_access_token(refresh_token: str) -> str:
    """Mint a fresh access token from a stored refresh token."""
    data = {
        "client_id": GOOGLE_CLIENT_ID,
        "client_secret": GOOGLE_CLIENT_SECRET,
        "refresh_token": refresh_token,
        "grant_type": "refresh_token",
    }
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.post(TOKEN_URL, data=data)
    if resp.status_code != 200:
        # 400 here usually means the refresh token was revoked. Deliberately
        # NOT 401: that status is reserved for the app's own session, and the
        # SPA logs the user out on any 401. A lapsed *Google* authorization
        # must not nuke the app session — surface it as 409 (reconnect needed).
        raise HTTPException(
            status_code=409, detail="Google authorization expired; reconnect needed"
        )
    token = resp.json().get("access_token")
    if not token:
        raise HTTPException(status_code=502, detail="Google returned no access token")
    return token


async def list_calendars(access_token: str) -> List[Dict[str, Any]]:
    """Return the user's calendars as ``[{id, summary, primary}]``."""
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.get(
            f"{CALENDAR_BASE}/users/me/calendarList",
            headers={"Authorization": f"Bearer {access_token}"},
        )
    if resp.status_code != 200:
        raise HTTPException(status_code=502, detail="Could not list Google calendars")
    return [
        {"id": c["id"], "summary": c.get("summary", c["id"]), "primary": bool(c.get("primary"))}
        for c in resp.json().get("items", [])
    ]


def _exclusive_end(day: str) -> str:
    """All-day events use an exclusive end date (the day after)."""
    d = datetime.strptime(day, "%Y-%m-%d").date()
    return (d + timedelta(days=1)).isoformat()


async def insert_event(
    access_token: str,
    calendar_id: str,
    summary: str,
    day: str,
    description: str,
) -> str:
    """Create an all-day event; return its id."""
    body = {
        "summary": summary,
        "description": description,
        "start": {"date": day},
        "end": {"date": _exclusive_end(day)},
    }
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.post(
            f"{CALENDAR_BASE}/calendars/{calendar_id}/events",
            headers={"Authorization": f"Bearer {access_token}"},
            json=body,
        )
    if resp.status_code not in (200, 201):
        raise HTTPException(status_code=502, detail="Could not create calendar event")
    return resp.json()["id"]


async def delete_event(access_token: str, calendar_id: str, event_id: str) -> None:
    """Delete an event. Treats 404/410 (already gone) as success."""
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.delete(
            f"{CALENDAR_BASE}/calendars/{calendar_id}/events/{event_id}",
            headers={"Authorization": f"Bearer {access_token}"},
        )
    if resp.status_code not in (200, 204, 404, 410):
        raise HTTPException(status_code=502, detail="Could not delete calendar event")


async def event_exists(access_token: str, calendar_id: str, event_id: str) -> bool:
    """Whether an event still exists (and isn't cancelled)."""
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.get(
            f"{CALENDAR_BASE}/calendars/{calendar_id}/events/{event_id}",
            headers={"Authorization": f"Bearer {access_token}"},
        )
    if resp.status_code == 200:
        return resp.json().get("status") != "cancelled"
    if resp.status_code in (404, 410):
        return False
    raise HTTPException(status_code=502, detail="Could not query calendar event")

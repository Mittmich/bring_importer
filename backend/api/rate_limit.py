"""A small in-memory limiter for failed login / link attempts (brute-force guard).

The backend runs as a single process, so a dict is enough; counts reset on
restart, which is fine for slowing down guessing. Keys are free-form strings,
e.g. ``"login-email:a@b.c"`` or ``"login-ip:203.0.113.9"``.
"""

import threading
import time
from collections import deque
from typing import Deque, Dict

from fastapi import HTTPException, Request

WINDOW_SECONDS = 15 * 60
# Failed logins allowed per account and per client address within the window.
LOGIN_FAILURES_PER_EMAIL = 10
LOGIN_FAILURES_PER_IP = 30
# Invalid sign-up / reset link attempts per client address within the window.
LINK_FAILURES_PER_IP = 30

_lock = threading.Lock()
_failures: Dict[str, Deque[float]] = {}


def _recent(key: str, now: float) -> Deque[float]:
    hits = _failures.setdefault(key, deque())
    while hits and hits[0] <= now - WINDOW_SECONDS:
        hits.popleft()
    return hits


def too_many(key: str, limit: int) -> bool:
    """True once ``key`` has ``limit`` failures inside the window."""
    with _lock:
        hits = _recent(key, time.monotonic())
        if not hits:
            _failures.pop(key, None)
        return len(hits) >= limit


def record_failure(key: str) -> None:
    with _lock:
        _recent(key, time.monotonic()).append(time.monotonic())


def clear(key: str) -> None:
    with _lock:
        _failures.pop(key, None)


def reset_all() -> None:
    """Forget everything (tests)."""
    with _lock:
        _failures.clear()


def client_ip(request: Request) -> str:
    """The caller's address: nginx's ``X-Real-IP``, else the socket peer."""
    forwarded = request.headers.get("x-real-ip", "").strip()
    if forwarded:
        return forwarded
    return request.client.host if request.client else "unknown"


def refuse_if_limited(*checks: tuple) -> None:
    """Raise 429 if any ``(key, limit)`` pair is over its limit."""
    for key, limit in checks:
        if too_many(key, limit):
            raise HTTPException(
                status_code=429,
                detail="Too many attempts. Please wait a few minutes and try again.",
                headers={"Retry-After": str(WINDOW_SECONDS)},
            )

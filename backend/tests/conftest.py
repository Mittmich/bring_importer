"""Shared pytest fixtures for the Recipe Parser API test suite.

DB fixture notes
-----------------
``api.get_db_connection()`` opens a fresh SQLite connection per call, and the
path is the relative literal ``'recipes.db'``. An in-memory db (``':memory:'``)
would NOT be shared across calls because each connection gets its own private
memory. The fixtures below use a ``tmp_path`` file-based db and monkeypatch
``api.get_db_connection`` to point at it. Do not "optimize" this to
``':memory:'`` — recipes and users would silently disappear between calls.
"""

from __future__ import annotations

import os
import sqlite3

import pytest
import responses as responses_lib
from fastapi.testclient import TestClient
from passlib.context import CryptContext

# Set deterministic env vars BEFORE importing ``api`` so module-level
# ``os.getenv(...)`` calls resolve to test values, not the developer's
# local .env file.
os.environ.setdefault("OPENAI_API_KEY", "test-openai-key-not-real")
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-jwt-signing-only")
os.environ.setdefault("USERS_FILE", "users.json")

import api  # noqa: E402  (env vars must be set first)
from api import auth as api_auth  # noqa: E402
from api import create_access_token  # noqa: E402
from api import db as api_db  # noqa: E402
from api.routers import recipes as api_recipes_router  # noqa: E402


def _make_get_db_connection(db_path):
    """Return a ``get_db_connection``-shaped callable bound to ``db_path``."""

    def _get_db_connection():
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        return conn

    return _get_db_connection


# Canonical recipe HTML returned by the mocked OpenAI endpoint. Kept as a
# module-level constant so individual tests can re-use or extend it.
CANONICAL_RECIPE_HTML = """\
<div itemscope itemtype="https://schema.org/Recipe">
  <h1 itemprop="name">Test Pancakes</h1>
  <span itemprop="recipeYield">4 servings</span>
  <p itemprop="description">Light and fluffy.</p>
  <ul>
    <li itemprop="recipeIngredient">1 cup flour</li>
    <li itemprop="recipeIngredient">2 eggs</li>
    <li itemprop="recipeIngredient">1 cup milk</li>
  </ul>
</div>
"""


@pytest.fixture
def tmp_db_path(tmp_path):
    """Path to a per-test SQLite db file."""
    return tmp_path / "recipes.db"


@pytest.fixture
def app(tmp_db_path, monkeypatch):
    """FastAPI app with ``get_db_connection`` bound to a per-test tmp db.

    Calls ``api.init_db()`` once so the schema is in place before any test
    code runs. ``init_db`` is idempotent (``CREATE TABLE IF NOT EXISTS``).

    The package split (comprehensive-recipe-management plan, step 1) moved
    ``get_db_connection`` into ``api.db``. Any module that does
    ``from api.db import get_db_connection`` creates its own binding in
    that module's namespace, so we must patch every module's binding —
    not just ``api.db`` and the ``api`` back-compat re-export.
    """
    bound = _make_get_db_connection(tmp_db_path)
    monkeypatch.setattr(api_db, "get_db_connection", bound)
    monkeypatch.setattr(api, "get_db_connection", bound)
    monkeypatch.setattr(api_auth, "get_db_connection", bound)
    monkeypatch.setattr(api_recipes_router, "get_db_connection", bound)
    api.init_db()
    return api.app


@pytest.fixture
def client(app):
    """FastAPI ``TestClient`` bound to the per-test app."""
    return TestClient(app)


@pytest.fixture
def seed_user(tmp_db_path):
    """Insert one user (test@example.com / 'correctpassword') into the tmp db."""
    pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
    conn = sqlite3.connect(str(tmp_db_path))
    try:
        conn.execute(
            "INSERT INTO users (email, hashed_password) VALUES (?, ?)",
            ("test@example.com", pwd_context.hash("correctpassword")),
        )
        conn.commit()
    finally:
        conn.close()
    return {"email": "test@example.com", "password": "correctpassword"}


@pytest.fixture
def auth_headers(seed_user):
    """``Authorization: Bearer <token>`` header for the seeded user."""
    token = create_access_token(data={"sub": seed_user["email"]})
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def mocked_openai():
    """Mock ``POST https://api.openai.com/v1/chat/completions`` with a canonical Recipe HTML payload."""  # noqa: E501
    with responses_lib.RequestsMock(assert_all_requests_are_fired=False) as rsps:
        rsps.add(
            responses_lib.POST,
            "https://api.openai.com/v1/chat/completions",
            json={"choices": [{"message": {"content": CANONICAL_RECIPE_HTML}}]},
            status=200,
        )
        yield rsps

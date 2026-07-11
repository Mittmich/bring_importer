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
from datetime import datetime
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from passlib.context import CryptContext

# Set deterministic env vars BEFORE importing ``api`` so module-level
# ``os.getenv(...)`` calls resolve to test values, not the developer's
# local .env file.
os.environ.setdefault("OPENAI_API_KEY", "test-openai-key-not-real")
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-jwt-signing-only")
os.environ.setdefault("USERS_FILE", "users.json")
# Google OAuth: deterministic test values so google_oauth_configured() is True
# and app_origin() resolves to a known host for recipe-link assertions.
os.environ.setdefault("GOOGLE_CLIENT_ID", "test-google-client-id")
os.environ.setdefault("GOOGLE_CLIENT_SECRET", "test-google-client-secret")
os.environ.setdefault("GOOGLE_REDIRECT_URI", "https://app.test/api/integrations/google/callback")

import api  # noqa: E402  (env vars must be set first)
from api import auth as api_auth  # noqa: E402
from api import create_access_token  # noqa: E402
from api import db as api_db  # noqa: E402
from api.models import Ingredient, InstructionStep, Recipe  # noqa: E402
from api.routers import friends as api_friends_router  # noqa: E402
from api.routers import integrations as api_integrations_router  # noqa: E402
from api.routers import meal_plan as api_meal_plan_router  # noqa: E402
from api.routers import recipes as api_recipes_router  # noqa: E402


def _make_get_db_connection(db_path):
    """Return a ``get_db_connection``-shaped callable bound to ``db_path``."""

    def _get_db_connection():
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        return conn

    return _get_db_connection


# Canonical recipe returned by all mocked extraction functions.
CANONICAL_RECIPE = Recipe(
    title="Test Pancakes",
    ingredients=[
        Ingredient(amount="1 cup", name="flour"),
        Ingredient(amount="2", name="eggs"),
        Ingredient(amount="1 cup", name="milk"),
    ],
    instructions=[
        InstructionStep(text="Mix dry ingredients.", ingredients=[0]),
        InstructionStep(text="Add eggs and milk, stir.", ingredients=[1, 2]),
    ],
    recipeYield="4 servings",
    description="Light and fluffy.",
    datePublished=datetime.now().strftime("%Y-%m-%d"),
)


@pytest.fixture
def tmp_db_path(tmp_path):
    """Path to a per-test SQLite db file."""
    return tmp_path / "recipes.db"


@pytest.fixture
def app(tmp_db_path, monkeypatch):
    """FastAPI app with ``get_db_connection`` bound to a per-test tmp db."""
    bound = _make_get_db_connection(tmp_db_path)
    monkeypatch.setattr(api_db, "get_db_connection", bound)
    monkeypatch.setattr(api, "get_db_connection", bound)
    monkeypatch.setattr(api_auth, "get_db_connection", bound)
    monkeypatch.setattr(api_recipes_router, "get_db_connection", bound)
    monkeypatch.setattr(api_meal_plan_router, "get_db_connection", bound)
    monkeypatch.setattr(api_integrations_router, "get_db_connection", bound)
    monkeypatch.setattr(api_friends_router, "get_db_connection", bound)
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
    """Patch all three high-level extraction functions to return CANONICAL_RECIPE.

    The extraction functions call the OpenAI SDK internally; patching at this
    level keeps tests independent of SDK internals and avoids real HTTP calls.

    We patch at both the source module (api.recipe_extraction) and the router
    module (api.routers.recipes) because Python's ``from X import Y`` binds the
    name locally — patching only the source module would leave the router's
    local binding pointing at the original function.
    """
    with (
        patch(
            "api.routers.recipes.parse_recipe_with_openai",
            return_value=CANONICAL_RECIPE,
        ) as mock_image,
        patch(
            "api.routers.recipes.extract_recipe_from_jsonld",
            return_value=CANONICAL_RECIPE,
        ) as mock_jsonld,
        patch(
            "api.routers.recipes.extract_recipe_from_html_text",
            return_value=CANONICAL_RECIPE,
        ) as mock_html,
    ):
        yield {
            "parse_image": mock_image,
            "jsonld": mock_jsonld,
            "html_text": mock_html,
        }

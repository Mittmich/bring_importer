"""Application configuration loaded from environment variables.

Loaded eagerly at import time via ``python-dotenv`` so other modules can
read module-level constants without ceremony.
"""

import logging
import os
import secrets
from urllib.parse import urlparse

from dotenv import load_dotenv

load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
# The placeholder older setups shipped with. It's public, so tokens signed with
# it could be forged by anyone; treat it like an unset key.
_PUBLIC_PLACEHOLDER_KEY = "please_change_this_to_a_random_key_in_production"
SECRET_KEY = os.getenv("SECRET_KEY", "")
if not SECRET_KEY or SECRET_KEY == _PUBLIC_PLACEHOLDER_KEY:
    # Never fall back to a known key. A random one keeps the app secure; logins
    # just don't survive a restart until SECRET_KEY is set.
    logging.getLogger(__name__).warning(
        "SECRET_KEY is not set (or is the public placeholder); using a random key for this "
        "process. Set SECRET_KEY so logins survive restarts."
    )
    SECRET_KEY = secrets.token_urlsafe(48)
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30000

# --- Training-data collection (opt-in, for the image-ingestion eval) ---
# When on, each image import persists the uploaded image + a snapshot of the
# raw model extraction so the user's later edits become ground-truth labels.
COLLECT_TRAINING_DATA = os.getenv("COLLECT_TRAINING_DATA", "").lower() in ("1", "true", "yes", "on")
TRAINING_DATA_DIR = os.getenv("TRAINING_DATA_DIR", "training_data")

# --- Recipe translation (see api/translation.py) ---
# Which LLM provider translates recipes between languages, and its model.
TRANSLATION_PROVIDER = os.getenv("TRANSLATION_PROVIDER", "openai").lower()
TRANSLATION_MODEL = os.getenv("TRANSLATION_MODEL", "gpt-5.4-mini")

# --- Feature flags (see api/features.py) ---
# Default for the "planner" flag until an admin sets it in the app: 'weekly'
# (the weekly meal plan) or 'menus' (menus with prep planning).
PLANNER_MODE = os.getenv("PLANNER_MODE", "weekly").strip().lower()

# --- Recipe hero images ---
# Optional user-uploaded photo shown at the top of a recipe. Stored on disk
# (one JPEG per recipe, keyed by uuid) rather than inline in the JSON so the
# recipe list/detail payloads stay small and thumbnails can be HTTP-cached.
RECIPE_IMAGES_DIR = os.getenv("RECIPE_IMAGES_DIR", "recipe_images")

# --- Google Calendar (server-side OAuth) ---
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")
# Must exactly match an Authorized redirect URI on the OAuth client, e.g.
# https://bring.vimi.run/api/integrations/google/callback
GOOGLE_REDIRECT_URI = os.getenv("GOOGLE_REDIRECT_URI", "")


# --- CORS ---
# Origins allowed to call the API from a browser. In production the SPA and the
# API share one origin (nginx proxies /api), so this only matters for local dev.
# Comma-separated; defaults to the Vite dev server.
CORS_ORIGINS = [
    o.strip()
    for o in os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",")
    if o.strip()
]


def google_oauth_configured() -> bool:
    """True when all three Google OAuth settings are present."""
    return bool(GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET and GOOGLE_REDIRECT_URI)


def app_origin() -> str:
    """The app's public origin, derived from the configured redirect URI.

    Used for the post-connect redirect back to the SPA and for recipe links
    embedded in calendar events. Falls back to localhost when unset.
    """
    if GOOGLE_REDIRECT_URI:
        parsed = urlparse(GOOGLE_REDIRECT_URI)
        if parsed.scheme and parsed.netloc:
            return f"{parsed.scheme}://{parsed.netloc}"
    return "http://localhost:5173"

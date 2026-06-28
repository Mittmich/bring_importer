"""Application configuration loaded from environment variables.

Loaded eagerly at import time via ``python-dotenv`` so other modules can
read module-level constants without ceremony.
"""

import os
from urllib.parse import urlparse

from dotenv import load_dotenv

load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
SECRET_KEY = os.getenv("SECRET_KEY", "please_change_this_to_a_random_key_in_production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30000

# --- Training-data collection (opt-in, for the image-ingestion eval) ---
# When on, each image import persists the uploaded image + a snapshot of the
# raw model extraction so the user's later edits become ground-truth labels.
COLLECT_TRAINING_DATA = os.getenv("COLLECT_TRAINING_DATA", "").lower() in ("1", "true", "yes", "on")
TRAINING_DATA_DIR = os.getenv("TRAINING_DATA_DIR", "training_data")

# --- Google Calendar (server-side OAuth) ---
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")
# Must exactly match an Authorized redirect URI on the OAuth client, e.g.
# https://bring.vimi.run/api/integrations/google/callback
GOOGLE_REDIRECT_URI = os.getenv("GOOGLE_REDIRECT_URI", "")


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

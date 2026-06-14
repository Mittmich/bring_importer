"""Application configuration loaded from environment variables.

Loaded eagerly at import time via ``python-dotenv`` so other modules can
read module-level constants without ceremony.
"""

import os

from dotenv import load_dotenv

load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
SECRET_KEY = os.getenv("SECRET_KEY", "please_change_this_to_a_random_key_in_production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30000

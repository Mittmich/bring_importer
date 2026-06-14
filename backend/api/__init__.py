"""Recipe Parser API package.

This package replaces the old flat ``backend/api.py`` module. The HTTP
surface is byte-for-byte identical to the pre-split version; the split
exists so each concern (config, db, models, auth, recipe extraction,
routers) lives in its own module and can be imported and tested in
isolation.

Back-compat re-exports
----------------------
The 64 tests shipped by the tests/CI plan import the following names
from ``api`` and monkeypatch them on the ``api`` module. They are
re-exported here so those tests keep working without modification:

  - ``app`` (used by ``run.py`` and the test ``TestClient``)
  - ``get_db_connection``, ``init_db``
  - ``get_password_hash``, ``verify_password``
  - ``get_user``, ``get_user_id``, ``authenticate_user``
  - ``get_current_user``, ``create_access_token``

New code should import from the focused modules directly:

  from api.auth import get_current_user
  from api.db import init_db
  from api.routers.recipes import router as recipes_router

The re-exports are intentionally not annotated ``__all__``; they exist
purely to keep the existing tests green during the refactor. A future
plan can drop them once the tests are re-pointed to the focused
modules.
"""

from api.auth import (
    authenticate_user,
    create_access_token,
    get_current_user,
    get_password_hash,
    get_user,
    get_user_id,
    verify_password,
)
from api.config import ALGORITHM, SECRET_KEY
from api.db import get_db_connection, init_db
from api.main import app
from api.recipe_extraction import _extract_recipe_from_html, parse_recipe_with_openai

__all__ = [
    "ALGORITHM",
    "SECRET_KEY",
    "app",
    "get_db_connection",
    "init_db",
    "get_password_hash",
    "verify_password",
    "get_user",
    "get_user_id",
    "authenticate_user",
    "get_current_user",
    "create_access_token",
    "_extract_recipe_from_html",
    "parse_recipe_with_openai",
]

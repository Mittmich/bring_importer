"""FastAPI application entry point.

Builds the ``app`` instance, wires CORS, runs the schema bootstrap on
startup, and includes the routers. Imported by ``api/__init__.py`` for
the back-compat ``from api import app`` re-export.
"""

import os
from contextlib import asynccontextmanager

# Install test-only request stubs if RECIPE_TEST_MOCKS=1. The
# ``api.testing`` module imports ``responses`` and ``httpx`` at the top,
# both of which are dev-only deps (or, in httpx's case, not always
# installed on a slim prod image). Gating the import on the env var
# keeps production deploys from pulling those into the import graph.
# In production (env var not set) this is a no-op.
if os.environ.get("RECIPE_TEST_MOCKS") == "1":
    from api import testing  # noqa: E402

    testing.install()

from fastapi import FastAPI  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402

from api.config import CORS_ORIGINS  # noqa: E402
from api.db import init_db  # noqa: E402
from api.routers import admin as admin_router_module  # noqa: E402
from api.routers import auth as auth_router_module  # noqa: E402
from api.routers import cookbooks as cookbooks_router_module  # noqa: E402
from api.routers import friends as friends_router_module  # noqa: E402
from api.routers import health as health_router_module  # noqa: E402
from api.routers import integrations as integrations_router_module  # noqa: E402
from api.routers import meal_plan as meal_plan_router_module  # noqa: E402
from api.routers import recipes as recipes_router_module  # noqa: E402


@asynccontextmanager
async def lifespan(_app):
    # Initialize the database (schema + migrations + seed users) on startup.
    init_db()
    yield


app = FastAPI(title="Recipe Parser API", lifespan=lifespan)

# CORS: only the configured origins (auth is a bearer header, not cookies, so
# credentials aren't needed). Same-origin requests through nginx don't use CORS.
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
    # Lets a cross-origin frontend (e.g. Vite dev server) read the PDF filename.
    expose_headers=["Content-Disposition"],
)


# Wire routers
app.include_router(auth_router_module.router)
app.include_router(recipes_router_module.router)
app.include_router(friends_router_module.router)
app.include_router(cookbooks_router_module.router)
app.include_router(meal_plan_router_module.router)
app.include_router(integrations_router_module.router)
app.include_router(health_router_module.router)
app.include_router(admin_router_module.router)

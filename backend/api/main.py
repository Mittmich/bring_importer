"""FastAPI application entry point.

Builds the ``app`` instance, wires CORS, runs the schema bootstrap on
startup, and includes the routers. Imported by ``api/__init__.py`` for
the back-compat ``from api import app`` re-export.
"""

# Install test-only request stubs if RECIPE_TEST_MOCKS=1. Must happen
# before any other api.* import that might call requests. No-op in
# production (env var not set).
from api import testing  # noqa: E402,F401

testing.install()

from fastapi import FastAPI  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402

from api.db import init_db  # noqa: E402
from api.routers import auth as auth_router_module  # noqa: E402
from api.routers import health as health_router_module  # noqa: E402
from api.routers import recipes as recipes_router_module  # noqa: E402

app = FastAPI(title="Recipe Parser API")

# Setup CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, change this to your frontend domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Initialize database and users on startup
@app.on_event("startup")
async def startup_event():
    init_db()


# Wire routers
app.include_router(auth_router_module.router)
app.include_router(recipes_router_module.router)
app.include_router(health_router_module.router)

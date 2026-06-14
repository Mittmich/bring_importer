#!/usr/bin/env bash
# ----------------------------------------------------------------------------
# Post-create setup for the Recipe to Bring Importer dev container.
# Runs once after the container is first built. Idempotent: safe to re-run.
#
# This script is baked into the dev container image at
# /usr/local/bin/devcontainer-post-create.sh by the Dockerfile's COPY
# step, and is invoked by devcontainer.json's `postCreateCommand`.
# It is therefore safe to assume the script is always reachable at
# the canonical in-image path, regardless of how (or whether) the
# host's `.devcontainer/` directory has been bind-mounted into the
# container.
# ----------------------------------------------------------------------------

set -euo pipefail

# When invoked from `devcontainer.json`'s postCreateCommand the caller
# passes `REPO_ROOT=${containerWorkspaceFolder}` (i.e. the project tree
# bind-mounted at /workspace). When invoked manually from a checkout of
# this repository, fall back to deriving the repo root from the script's
# own location.
REPO_ROOT="${REPO_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
BACKEND_DIR="${REPO_ROOT}/backend"

echo "==> Setting up Python virtual environment with uv"
cd "${BACKEND_DIR}"

if [ ! -d .venv ]; then
  uv venv
fi

# shellcheck source=/dev/null
source .venv/bin/activate

echo "==> Installing backend dependencies (incl. dev extras)"
uv pip install -e ".[dev]"

cat <<'EOF'

✅ Dev environment ready!

Useful commands:

  # Start the FastAPI backend on port 8001
  cd backend && source .venv/bin/activate && python run.py

  # Serve the static frontend on port 8000
  cd frontend && python -m http.server 8000

  # Code quality tools (configured in backend/pyproject.toml)
  ruff check backend
  black backend
  isort backend
  mypy backend

EOF

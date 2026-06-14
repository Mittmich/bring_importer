# Root Makefile for the Recipe to Bring Importer project.
#
# All targets operate on the backend/. The frontend is a static SPA served
# by nginx in production; there is no JS build step.

.PHONY: help install-dev test lint typecheck coverage hooks hooks-install ci clean

BACKEND := backend
PY      := .venv/bin

help:                   ## Show this help.
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
	  awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'

install-dev:            ## Install backend dev/test deps and pre-commit hooks.
	cd $(BACKEND) && uv pip install -e ".[dev]"
	cd $(BACKEND) && $(PY)/pre-commit install

test:                   ## Run the pytest suite (no coverage).
	cd $(BACKEND) && $(PY)/pytest

lint:                   ## Run ruff + black --check + isort --check-only.
	cd $(BACKEND) && $(PY)/ruff check .
	cd $(BACKEND) && $(PY)/black --check .
	cd $(BACKEND) && $(PY)/isort --check-only .

typecheck:              ## Run mypy (allowed to be noisy on first run; see plan notes).
	cd $(BACKEND) && $(PY)/mypy .

coverage:               ## Run pytest with coverage; fail under 80%.
	cd $(BACKEND) && $(PY)/pytest --cov=api --cov=manage_users --cov-fail-under=80

hooks:                  ## Run all pre-commit hooks against every file.
	cd $(BACKEND) && $(PY)/pre-commit run --all-files

hooks-install:          ## Install pre-commit hooks (idempotent).
	cd $(BACKEND) && $(PY)/pre-commit install

ci: lint typecheck test ## Run the same checks as the CI workflow, locally.

clean:                  ## Remove caches and build artifacts.
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .mypy_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .ruff_cache -exec rm -rf {} + 2>/dev/null || true
	rm -rf $(BACKEND)/.coverage $(BACKEND)/htmlcov $(BACKEND)/coverage.xml 2>/dev/null || true

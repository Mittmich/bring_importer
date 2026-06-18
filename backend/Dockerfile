FROM python:3.12-slim

WORKDIR /app

# Use uv from the official image — faster than pip install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Layer 1: install all deps from lock file, but NOT the project itself.
# This layer is only invalidated when pyproject.toml or uv.lock changes.
COPY pyproject.toml uv.lock ./
RUN uv sync --no-install-project

# Layer 2: copy source, then install just the project (deps already cached).
COPY . .
RUN uv sync

ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 8001
CMD ["python3", "run.py"]

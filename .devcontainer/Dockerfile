# Use the official Microsoft Python dev container base image.
# It already creates a non-root `vscode` user (UID 1000) with sudo,
# installs common build dependencies, and ships Python 3.12.
FROM mcr.microsoft.com/devcontainers/python:1-3.12-bookworm

# Install `uv`, the fast Python package manager used by this project.
# See: https://github.com/astral-sh/uv
RUN pip install --no-cache-dir uv

# Install nginx so the full production-like stack (backend + reverse
# proxy) can also be exercised from the dev container, matching the
# setup described in README.md and start.sh.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        nginx \
        gettext-base \
    && rm -rf /var/lib/apt/lists/*

# Drop privileges: run subsequent build steps (and the container itself)
# as the unprivileged `vscode` user that the base image provides.
USER vscode
WORKDIR /home/vscode/bring_importer

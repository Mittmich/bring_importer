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
#
# NOTE: the base image ships a `yarn.list` repo file pointing at
# `dl.yarnpkg.com/debian` whose GPG key (62D54FD4003F6525) has been
# rotated upstream. If left in place, `apt-get update` fails with
# "The repository ... is not signed" and exits 100, which aborts the
# build. The yarn repo is not needed for this Python project, so we
# drop it before refreshing the package indexes.
RUN rm -f /etc/apt/sources.list.d/yarn.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends \
        nginx \
        gettext-base \
    && rm -rf /var/lib/apt/lists/*

# Install Node.js 22 (LTS) and the `pi` coding-agent CLI globally.
# Node comes from NodeSource's apt repo (not nvm) so the binary lives
# in /usr/bin and is on PATH for the unprivileged `vscode` user
# without having to source nvm.sh in non-interactive shells. The
# yarn.list drop is repeated here because it would otherwise trip the
# same "Release file not signed" error on the second apt-get update.
RUN rm -f /etc/apt/sources.list.d/yarn.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        gnupg \
    && mkdir -p /etc/apt/keyrings \
    && curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key \
        | gpg --dearmor -o /etc/apt/keyrings/nodesource.gpg \
    && echo "deb [signed-by=/etc/apt/keyrings/nodesource.gpg] https://deb.nodesource.com/node_22.x nodistro main" \
        > /etc/apt/sources.list.d/nodesource.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends nodejs \
    && npm install -g @earendil-works/pi-coding-agent@latest \
    && rm -rf /var/lib/apt/lists/*

# Drop privileges: run subsequent build steps (and the container itself)
# as the unprivileged `vscode` user that the base image provides.
#
# The dev containers CLI will bind-mount the project tree on top of
# `/workspace` (matching `workspaceFolder` in devcontainer.json) at
# container-start time. We pre-create the directory here -- owned by
# `vscode` and matching the WORKDIR -- so the path always exists in
# the image, which prevents a transient race in VS Code's terminal
# integration that otherwise reports
#   "Starting directory (cwd) \"/workspace\" does not exist"
# on the first terminal open.
USER root
RUN mkdir -p /workspace && chown vscode:vscode /workspace

# Bake the post-create script into the image at a known path so the
# dev container's `postCreateCommand` can always find it, even if the
# workspace bind-mount does not surface the project's `.devcontainer/`
# directory at runtime (which is what was happening in this user's
# setup). The script is invoked by `devcontainer.json`'s
# `postCreateCommand` with `REPO_ROOT=${containerWorkspaceFolder}`
# passed in, so it still operates on the real project tree mounted
# at `/workspace`.
COPY --chown=root:root --chmod=0755 .devcontainer/post-create.sh \
     /usr/local/bin/devcontainer-post-create.sh

USER vscode
WORKDIR /workspace

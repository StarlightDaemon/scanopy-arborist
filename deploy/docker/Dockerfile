# syntax=docker/dockerfile:1
# Arborist — MCP server for Scanopy (§8.1 Docker distribution).
#
# Build from the REPO ROOT (the build context must contain pyproject.toml,
# uv.lock, and src/):
#
#   docker build -f deploy/docker/Dockerfile -t scanopy-arborist-mcp .
#
# Multi-stage uv build per current Astral guidance: dependencies are synced
# first (cache-friendly layer keyed only on pyproject.toml + uv.lock), then the
# project itself is installed --no-editable so the runtime stage only needs the
# virtualenv — no source tree, no uv binary.

FROM ghcr.io/astral-sh/uv:python3.12-trixie-slim AS builder

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_NO_DEV=1 \
    UV_PYTHON_DOWNLOADS=0

WORKDIR /app

# Dependency layer: only invalidated when the lockfile or project metadata
# changes, never by source edits.
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-install-project

# Project layer: copy the source (filtered by the repo-root .dockerignore) and
# install arborist itself into the venv as a regular, non-editable package so
# /app/.venv is self-contained.
COPY . /app
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-editable


FROM python:3.12-slim-trixie

# Non-root runtime user (fixed uid/gid 999 so bind mounts and logs have a
# predictable owner).
RUN groupadd --system --gid 999 arborist \
    && useradd --system --uid 999 --gid arborist --create-home \
       --home-dir /home/arborist arborist

# --no-editable means the venv carries the installed project; nothing else from
# the builder is needed.
COPY --from=builder --chown=arborist:arborist /app/.venv /app/.venv

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1

USER arborist
WORKDIR /app

EXPOSE 60074

# Inside the container the server must bind a non-loopback address or it would
# be unreachable through the port mapping; exposure control belongs to the
# publisher (compose publishes to host loopback only by default). §5.5 still
# applies: ARBORIST_AUTH_TOKEN, ARBORIST_TLS_POSTURE, and
# ARBORIST_ALLOWED_HOSTS are required for the HTTP transport on 0.0.0.0.
CMD ["arborist", "--transport", "http", "--host", "0.0.0.0", "--port", "60074"]

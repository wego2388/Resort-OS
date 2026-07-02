# syntax=docker/dockerfile:1
#
# Resort OS (El Kheima Beach) — backend image
# ─────────────────────────────────────────────────────────────────────────────
# `wego_core` (the shared WegoSharm infra kernel — auth, DB, cache, Celery
# factory, reports, health checks, ...) is NOT on PyPI and is NOT vendored
# into this repo. On the dev machine it lives at /home/wego/projects/wego-core
# and is installed editable (`-e /home/wego/projects/wego-core[...]` in
# requirements.txt). That path will not exist on any VPS, so this Dockerfile
# pulls the wego-core *source* in via a BuildKit named build context instead
# of assuming a fixed host path.
#
# This means the build context for this image is NOT just `backend/` (or even
# just `resort-os/`) — it needs a second, independent source tree: wego-core.
# BuildKit's `--build-context NAME=PATH` (Docker Buildx >= 0.8 / Docker CLI
# >= 23) lets you hand the Dockerfile a second, unrelated directory under a
# name, without requiring it to be a subdirectory of the main build context.
#
# See ../DEPLOYMENT.md for the full explanation and exact commands. Short
# version — from the parent directory containing both `resort-os/` and
# `wego-core/` as siblings:
#
#   DOCKER_BUILDKIT=1 docker build \
#     -f resort-os/backend/Dockerfile \
#     --build-context wego-core=./wego-core \
#     -t resort-os-backend:latest \
#     resort-os/backend
#
# Or via `docker compose -f docker-compose.prod.yml build backend` — the
# compose file wires the same named context up via `additional_contexts:`
# (Compose Spec, supported Docker Compose v2.17+), so no manual `docker
# build` invocation is needed in normal operation.
# ─────────────────────────────────────────────────────────────────────────────

# ── Stage 1: build wheels / install deps into a venv ──────────────────────────
FROM python:3.11-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# build-essential: some transitive deps (e.g. cryptography backends) may need
# to compile; removed again in the final stage so it never ships to prod.
RUN apt-get update && apt-get install -y --no-install-recommends \
      build-essential \
      libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Pull in the wego-core source tree from the named build context (see header
# comment above) at a fixed, predictable path — this is what
# `-e /wego-core[reports,worker,monitoring]` below resolves against, and it's
# also where the runtime stage expects to find it (editable installs are a
# path reference, not a copy — the source must exist at the same path in the
# final image too).
COPY --from=wego-core . /wego-core

WORKDIR /app
COPY requirements.txt .

# requirements.txt contains `-e /home/wego/projects/wego-core[reports,worker,monitoring]`.
# That exact host path does not exist in this image — sed it to /wego-core
# (the path we just COPY'd it to above) at build time. Nothing else in the
# file changes.
RUN sed -i 's#-e /home/wego/projects/wego-core#-e /wego-core#' requirements.txt

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
RUN pip install --upgrade pip && pip install -r requirements.txt


# ── Stage 2: runtime ───────────────────────────────────────────────────────────
FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    APP_ENV=production

# libpq5: runtime shared lib for psycopg (psycopg[binary] bundles its own
# libpq, so this is a safety net, not strictly required — kept small).
# curl: used by the container HEALTHCHECK below.
RUN apt-get update && apt-get install -y --no-install-recommends \
      libpq5 \
      curl \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --shell /usr/sbin/nologin resortos

COPY --from=builder /opt/venv /opt/venv
# wego_core is installed editable — the venv only has a path reference
# (an .egg-link / .pth pointing at /wego-core), so the source must be present
# at that same path in this stage too, not just in the builder stage.
COPY --from=wego-core . /wego-core

WORKDIR /app
COPY . /app

RUN chown -R resortos:resortos /app /wego-core /opt/venv
USER resortos

EXPOSE 8005

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=5 \
  CMD curl -fs http://127.0.0.1:8005/health || exit 1

# alembic upgrade head / app.seed are run once as one-off `docker compose exec`
# commands after the stack is up (see DEPLOYMENT.md) — not baked into the
# container's start command, so re-deploys never silently re-run migrations
# as a side effect of a container restart.
#
# --workers 4: gunicorn isn't in requirements.txt (only referenced by the
# Makefile's `prod-start` target, which predates this Dockerfile) — uvicorn's
# own multi-worker mode is used instead so no extra dependency is needed.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8005", "--workers", "4"]

# syntax=docker/dockerfile:1
#
# Resort OS (El Kheima Beach) — backend image
# ─────────────────────────────────────────────────────────────────────────────
# Self-contained: no external "shared kernel" package, no second build
# context. `backend/` alone is the entire build context — just
# `docker build -f backend/Dockerfile -t resort-os-backend:latest backend`
# or `docker compose build backend`. All auth/security/notification/report
# code lives in app/core/kernel/, owned directly by this repo.
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

WORKDIR /app
COPY requirements.txt .

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

WORKDIR /app
COPY . /app

RUN chown -R resortos:resortos /app /opt/venv
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

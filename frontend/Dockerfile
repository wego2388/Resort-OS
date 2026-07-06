# syntax=docker/dockerfile:1
#
# Resort OS (El Kheima Beach) — frontend app image
# ─────────────────────────────────────────────────────────────────────────────
# One shared, parameterized Dockerfile builds both frontend apps
# (el-kheima / public) rather than two near-identical copies — they're
# all part of the same pnpm workspace and share `packages/core` +
# `packages/ui`, so the build needs the *whole* `frontend/` directory as
# context regardless of which single app is being built (pnpm needs to see
# every workspace member to resolve `workspace:*` deps).
#
# Build context MUST be the `frontend/` directory (not `frontend/apps/<app>`),
# e.g. from the repo root:
#
#   docker build -f frontend/Dockerfile --build-arg APP_NAME=el-kheima \
#     -t resort-os-el-kheima:latest frontend
#   docker build -f frontend/Dockerfile --build-arg APP_NAME=public \
#     -t resort-os-public:latest frontend
#
# docker-compose.prod.yml builds both from this one file with different
# `build.args.APP_NAME` values — see that file + DEPLOYMENT.md.
# ─────────────────────────────────────────────────────────────────────────────

# ── Stage 1: install the full pnpm workspace ──────────────────────────────────
FROM node:20-slim AS deps

# Pin the pnpm version used in dev (see frontend/package.json's packageManager
# expectations / `pnpm --version` on the dev machine) for reproducible builds.
RUN corepack enable && corepack prepare pnpm@10.34.4 --activate

WORKDIR /workspace
COPY pnpm-workspace.yaml package.json pnpm-lock.yaml ./
COPY packages ./packages
COPY apps ./apps

# --frozen-lockfile: fail the build rather than silently drift from
# pnpm-lock.yaml, same guarantee CI would give.
RUN pnpm install --frozen-lockfile


# ── Stage 2: build the one app selected via APP_NAME ──────────────────────────
FROM deps AS build

ARG APP_NAME
RUN test -n "$APP_NAME" || (echo "APP_NAME build-arg is required (el-kheima|public)" && exit 1)

RUN pnpm --filter "${APP_NAME}" build


# ── Stage 3: serve the built static files via nginx ───────────────────────────
FROM nginx:1.27-alpine AS runtime

ARG APP_NAME
ENV APP_NAME=${APP_NAME}

COPY --from=build /workspace/apps/${APP_NAME}/dist /usr/share/nginx/html
COPY nginx.spa.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=5 \
  CMD wget -q -O- http://127.0.0.1:80/ >/dev/null || exit 1

CMD ["nginx", "-g", "daemon off;"]

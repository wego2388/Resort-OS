#!/usr/bin/env bash
# vps-init-first-branch.sh — run this ON THE VPS to create the first
# production branch and bind it to a named super-admin. Companion to
# vps-create-admin.sh/vps-recover-admin.sh for the same paste-fragility
# reason (this command needs TWO typed confirmations interactively).
#
# Usage (from the VPS shell, after `ssh resort-os-vps`):
#   bash vps-init-first-branch.sh <super-admin-email> <branch-code> "<branch name>" ["<Arabic branch name>"]
#
# Example:
#   bash vps-init-first-branch.sh theagaty@gmail.com ELK-001 "El Kheima Beach Resort"
set -euo pipefail

if [[ $# -lt 3 ]]; then
  echo "Usage: bash $0 <super-admin-email> <branch-code> \"<branch name>\" [\"<Arabic branch name>\"]" >&2
  exit 1
fi

EMAIL="$1"
CODE="$2"
NAME="$3"
NAME_AR="${4:-}"

RESORT_RELEASE_DIR="${RESORT_RELEASE_DIR:-$(docker inspect \
  resort-os-prod-backend-1 \
  --format '{{index .Config.Labels "com.docker.compose.project.working_dir"}}' \
  2>/dev/null || true)}"
if [[ -z "$RESORT_RELEASE_DIR" || ! -d "$RESORT_RELEASE_DIR" ]]; then
  echo "Active Resort OS release directory could not be resolved" >&2
  exit 1
fi
cd "$RESORT_RELEASE_DIR"

DATABASE_URL_VALUE=$(grep -E '^DATABASE_URL=' backend/.env.prod | head -1 | cut -d= -f2-)
DB_PASSWORD=$(RESORT_DATABASE_URL="$DATABASE_URL_VALUE" python3 -c '
import os
from urllib.parse import urlparse
url = os.environ["RESORT_DATABASE_URL"].replace("postgresql+psycopg://", "postgresql://", 1)
print(urlparse(url).password)
')
export DB_PASSWORD

TLS_CERT_PATH=/etc/letsencrypt/live/191.218.161.133/fullchain.pem
if [[ -f "$TLS_CERT_PATH" ]]; then
  OVERRIDE=docker-compose.prod.ip-tls.yml
else
  OVERRIDE=docker-compose.prod.ip-only.yml
fi

NAME_AR_ARGS=()
if [[ -n "$NAME_AR" ]]; then
  NAME_AR_ARGS=(--name-ar "$NAME_AR")
fi

sudo -E docker compose --env-file backend/.env.prod -f docker-compose.prod.yml -f "$OVERRIDE" exec -T backend \
  python -m app.admin_bootstrap init-first-branch --email "$EMAIL" --code "$CODE" --name "$NAME" "${NAME_AR_ARGS[@]}" <<STDIN_EOF
$EMAIL
$CODE
STDIN_EOF

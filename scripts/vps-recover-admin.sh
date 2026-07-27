#!/usr/bin/env bash
# vps-recover-admin.sh — run this ON THE VPS to rotate an existing account's
# temporary password + 2FA enrollment token (role is preserved exactly).
# Companion to vps-create-admin.sh for the same paste-fragility reason.
#
# Usage (from the VPS shell, after `ssh resort-os-vps`):
#   bash vps-recover-admin.sh <email>
set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "Usage: bash $0 <email>" >&2
  exit 1
fi

EMAIL="$1"

cd /opt/resort-os

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

sudo -E docker compose --env-file backend/.env.prod -f docker-compose.prod.yml -f "$OVERRIDE" exec -T backend \
  python -m app.admin_bootstrap recover --email "$EMAIL" <<STDIN_EOF
$EMAIL
STDIN_EOF

#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
#  Resort OS — Stop Dev Environment
#  Usage: bash stop.sh [--docker]
# ─────────────────────────────────────────────────────────────────────────────
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_DIR="/tmp"
PREFIX="resort-os"

GREEN="\033[0;32m"; YELLOW="\033[1;33m"; NC="\033[0m"

echo -e "${YELLOW}  🛑 Resort OS — Stopping...${NC}"

fuser -k 8005/tcp 2>/dev/null \
  && echo -e "${GREEN}  ✓ Backend stopped (8005)${NC}" \
  || echo "     Backend was not running"

declare -A APP_PORTS=(
  [el-kheima]=3001 [qr]=3005 [public]=3007
)
for app in "${!APP_PORTS[@]}"; do
  fuser -k "${APP_PORTS[$app]}/tcp" 2>/dev/null \
    && echo -e "${GREEN}  ✓ $app stopped (${APP_PORTS[$app]})${NC}" \
    || true
done

pkill -f "celery -A app.celery_app" 2>/dev/null \
  && echo -e "${GREEN}  ✓ Celery worker + beat stopped${NC}" \
  || echo "     Celery was not running"

rm -f "$LOG_DIR/$PREFIX"-*.pid

# ── Optionally stop Docker too ────────────────────────────────────────────────
if [[ "${1:-}" == "--docker" ]]; then
  echo "  → Stopping Docker services..."
  docker compose -f "$ROOT/docker-compose.yml" down
  echo -e "${GREEN}  ✓ Docker stopped${NC}"
else
  echo "     Docker DB+Redis left running (use: ./stop.sh --docker to stop)"
fi

echo -e "${GREEN}  ✓ Done${NC}"

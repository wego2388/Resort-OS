#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
#  Resort OS — Status of Dev Environment
#  Usage: bash status.sh
# ─────────────────────────────────────────────────────────────────────────────
GREEN="\033[0;32m"; RED="\033[0;31m"; CYAN="\033[0;36m"; NC="\033[0m"

echo -e "${CYAN}  Resort OS — Status${NC}\n"

check_port() {
  local name="$1" port="$2" url="${3:-}"
  if curl -s -o /dev/null --max-time 1 "http://127.0.0.1:${port}${url}" 2>/dev/null || \
     fuser "${port}/tcp" >/dev/null 2>&1; then
    echo -e "  ${GREEN}●${NC} ${name} — http://127.0.0.1:${port}${url}"
  else
    echo -e "  ${RED}○${NC} ${name} — not running (port ${port})"
  fi
}

echo "  ── Infrastructure ──"
docker ps --filter "name=resort-os" --format "    {{.Names}}: {{.Status}}" 2>/dev/null

echo -e "\n  ── Backend ──"
check_port "Backend " 8005 "/health"

echo -e "\n  ── Celery ──"
if pgrep -f "celery -A app.celery_app worker" >/dev/null; then
  echo -e "  ${GREEN}●${NC} Celery worker running"
else
  echo -e "  ${RED}○${NC} Celery worker not running"
fi
if pgrep -f "celery -A app.celery_app beat" >/dev/null; then
  echo -e "  ${GREEN}●${NC} Celery beat running"
else
  echo -e "  ${RED}○${NC} Celery beat not running"
fi

echo -e "\n  ── Frontend apps ──"
check_port "el-kheima" 3001
check_port "qr     " 3005
check_port "public " 3007
echo

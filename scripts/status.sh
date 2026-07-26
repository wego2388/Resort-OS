#!/usr/bin/env bash
# =============================================================================
#  Resort OS — Status Check
#  Shows live status of all services + HTTP health endpoints + demo accounts
# =============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(dirname "$SCRIPT_DIR")"
PID_DIR="$ROOT/.pids"

BOLD=$'\e[1m'; RESET=$'\e[0m'
CYAN=$'\e[36m'; GREEN=$'\e[32m'; RED=$'\e[31m'; YELLOW=$'\e[33m'; DIM=$'\e[2m'

echo
echo "${CYAN}${BOLD}  🏖️  Resort OS — Status${RESET}"
echo

pid_status() {
  local name="$1" pid_file="$PID_DIR/$2" url="${3:-}"
  printf "  %-20s" "$name"
  if [[ ! -f "$pid_file" ]]; then
    echo "${RED}○ stopped${RESET}  ${DIM}(no PID file)${RESET}"
    return
  fi
  local pid; pid=$(cat "$pid_file")
  if ! kill -0 "$pid" 2>/dev/null; then
    echo "${RED}○ stopped${RESET}  ${DIM}(PID $pid — not running)${RESET}"
    return
  fi
  if [[ -n "$url" ]]; then
    if curl -s -o /dev/null --max-time 1 "$url"; then
      echo "${GREEN}● running${RESET}  PID $pid  ·  $url"
    else
      echo "${YELLOW}● running${RESET}  PID $pid  ${DIM}(not responding yet on $url)${RESET}"
    fi
  else
    echo "${GREEN}● running${RESET}  PID $pid"
  fi
}

echo "  ── Infrastructure (Docker) ──"
docker ps --filter "name=resort-os" --format "    {{.Names}}: {{.Status}}" 2>/dev/null
[[ -z "$(docker ps --filter "name=resort-os" -q 2>/dev/null)" ]] && echo "    ${DIM}nothing running${RESET}"

echo
echo "  ── Backend ──"
pid_status "Backend" "backend.pid" "http://127.0.0.1:8005/health"
pid_status "Celery worker" "celery.pid"
pid_status "Celery beat" "celery_beat.pid"

echo
echo "  ── Frontend apps ──"
pid_status "el-kheima (staff)" "frontend-el-kheima.pid" "http://127.0.0.1:3001"
echo
echo "  ── الموقع العام الجديد (مستقل) ──"
if curl -s -o /dev/null --max-time 1 "http://127.0.0.1:5174"; then
  echo "  ${GREEN}● elkheima-marketing-website  http://127.0.0.1:5174  (شغّال)${RESET}"
else
  echo "  ${DIM}○ elkheima-marketing-website  http://127.0.0.1:5174  (متوقف)${RESET}"
  echo "    ${DIM}شغّله: cd /home/wego/projects/elkheima-marketing-website && npm run dev${RESET}"
fi

echo
echo "  ── Demo accounts (one per role, seeded automatically on first run) ──"
echo "    admin@resortos.local         super_admin   Admin@123456      ${DIM}(2FA required)${RESET}"
echo "    ${DIM}password for every account below: Demo@123456${RESET}"
echo "    branch_admin@resortos.local  admin"
echo "    accountant@resortos.local    accountant    ${DIM}(2FA required)${RESET}"
echo "    hr@resortos.local            hr_manager"
echo "    manager@resortos.local       manager"
echo "    supervisor@resortos.local    supervisor"
echo "    reception@resortos.local     receptionist"
echo "    cashier@resortos.local       cashier"
echo "    waiter@resortos.local        waiter"
echo "    chef@resortos.local          chef"
echo "    kitchen@resortos.local       kitchen"
echo "    employee@resortos.local      employee"
echo

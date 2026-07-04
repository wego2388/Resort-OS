#!/usr/bin/env bash
# =============================================================================
#  Resort OS — Live Log Viewer
#  Usage:
#    bash scripts/logs.sh                    → all logs interleaved
#    bash scripts/logs.sh api                → backend only
#    bash scripts/logs.sh celery             → Celery worker only
#    bash scripts/logs.sh beat               → Celery beat only
#    bash scripts/logs.sh frontend-el-kheima → one frontend app
# =============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(dirname "$SCRIPT_DIR")"
LOG_DIR="$ROOT/backend/logs"
mkdir -p "$LOG_DIR"

BOLD=$'\e[1m'; RESET=$'\e[0m'
CYAN=$'\e[36m'; DIM=$'\e[2m'

MODE="${1:-all}"

print_header() {
  echo
  echo "${CYAN}${BOLD}  🏖️  Resort OS — Live Logs${RESET}"
  echo "  ${DIM}Ctrl+C to exit${RESET}"
  echo
}

case "$MODE" in
  api)
    print_header
    echo "${CYAN}${BOLD}[ Backend ]${RESET}  $LOG_DIR/api.log"
    tail -f "$LOG_DIR/api.log"
    ;;
  celery|worker)
    print_header
    echo "${CYAN}${BOLD}[ Celery Worker ]${RESET}  $LOG_DIR/celery.log"
    tail -f "$LOG_DIR/celery.log"
    ;;
  beat)
    print_header
    echo "${CYAN}${BOLD}[ Celery Beat ]${RESET}  $LOG_DIR/celery_beat.log"
    tail -f "$LOG_DIR/celery_beat.log"
    ;;
  frontend-*)
    print_header
    f="$LOG_DIR/$MODE.log"
    echo "${CYAN}${BOLD}[ $MODE ]${RESET}  $f"
    tail -f "$f"
    ;;
  all|*)
    print_header
    for f in api celery celery_beat frontend-el-kheima frontend-qr frontend-public; do
      touch "$LOG_DIR/$f.log"
    done
    if command -v multitail >/dev/null 2>&1; then
      multitail -cS logfile -l "" \
        --label "[API]         " "$LOG_DIR/api.log" \
        --label "[CELERY]      " "$LOG_DIR/celery.log" \
        --label "[BEAT]        " "$LOG_DIR/celery_beat.log" \
        --label "[EL-KHEIMA]   " "$LOG_DIR/frontend-el-kheima.log" \
        --label "[QR]          " "$LOG_DIR/frontend-qr.log" \
        --label "[PUBLIC]      " "$LOG_DIR/frontend-public.log"
    else
      echo "  ${DIM}Tip: install multitail for a nicer interleaved view${RESET}"
      echo
      tail -f \
        "$LOG_DIR/api.log" "$LOG_DIR/celery.log" "$LOG_DIR/celery_beat.log" \
        "$LOG_DIR/frontend-el-kheima.log" "$LOG_DIR/frontend-qr.log" "$LOG_DIR/frontend-public.log" \
      | awk '
          /==> .*api\.log/ { src = "\033[32m[API       ]\033[0m"; next }
          /==> .*celery\.log/ { src = "\033[33m[CELERY    ]\033[0m"; next }
          /==> .*celery_beat\.log/ { src = "\033[35m[BEAT      ]\033[0m"; next }
          /==> .*frontend-el-kheima\.log/ { src = "\033[36m[EL-KHEIMA ]\033[0m"; next }
          /==> .*frontend-qr\.log/ { src = "\033[34m[QR        ]\033[0m"; next }
          /==> .*frontend-public\.log/ { src = "\033[37m[PUBLIC    ]\033[0m"; next }
          { if (src == "") src = "\033[37m[??????????]\033[0m"; printf "%s %s\n", src, $0 }
        '
    fi
    ;;
esac

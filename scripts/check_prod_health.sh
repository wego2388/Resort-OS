#!/usr/bin/env bash
# Read-only production health gate for the IP-only Resort OS deployment.
# Intended for resort-os-healthcheck.service; safe to run manually.
set -uo pipefail

RESORT_PUBLIC_IP="${RESORT_PUBLIC_IP:-191.218.161.133}"
RESORT_BACKUP_DIR="${RESORT_BACKUP_DIR:-/var/backups/resort-os}"
RESORT_BACKUP_MAX_AGE_MINUTES="${RESORT_BACKUP_MAX_AGE_MINUTES:-1560}"
RESORT_CERT_MIN_VALID_SECONDS="${RESORT_CERT_MIN_VALID_SECONDS:-172800}"
RESORT_DISK_WARN_PERCENT="${RESORT_DISK_WARN_PERCENT:-85}"

failures=()
passes=()

pass() {
  passes+=("$1")
}

fail() {
  failures+=("$1")
}

timestamp="$(date --iso-8601=seconds)"
echo "RESORT_HEALTHCHECK_START timestamp=$timestamp"

if health_payload=$(curl -fsS --max-time 8 "http://127.0.0.1:8005/health" 2>/dev/null); then
  if grep -Eq '"status"[[:space:]]*:[[:space:]]*"ok"' <<<"$health_payload" &&
     grep -Eq '"database"[[:space:]]*:[[:space:]]*\\{[^}]*"status"[[:space:]]*:[[:space:]]*"ok"' <<<"$health_payload" &&
     grep -Eq '"redis"[[:space:]]*:[[:space:]]*\\{[^}]*"status"[[:space:]]*:[[:space:]]*"ok"' <<<"$health_payload"; then
    pass "backend-db-redis"
  else
    fail "backend health payload is not fully healthy"
  fi
else
  fail "backend health endpoint is unreachable"
fi

staff_status=$(curl -fsS --max-time 10 -o /dev/null -w '%{http_code}' \
  "https://${RESORT_PUBLIC_IP}/" 2>/dev/null || true)
if [[ "$staff_status" == "200" ]]; then
  pass "staff-https"
else
  fail "staff HTTPS returned ${staff_status:-no-status}"
fi

marketing_status=$(curl -fsS --max-time 10 -o /dev/null -w '%{http_code}' \
  "https://${RESORT_PUBLIC_IP}:8443/" 2>/dev/null || true)
if [[ "$marketing_status" == "200" ]]; then
  pass "marketing-https"
else
  fail "marketing HTTPS returned ${marketing_status:-no-status}"
fi

required_containers=(
  resort-os-prod-backend-1
  resort-os-prod-celery_worker-1
  resort-os-prod-celery_beat-1
  resort-os-prod-db_postgres-1
  resort-os-prod-el_kheima-1
  resort-os-prod-marketing_site-1
  resort-os-prod-nginx-1
  resort-os-prod-redis_cache-1
)

for container in "${required_containers[@]}"; do
  if ! container_state=$(docker inspect \
    --format '{{.State.Status}}|{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}|{{.RestartCount}}' \
    "$container" 2>/dev/null); then
    fail "container missing: $container"
    continue
  fi

  IFS='|' read -r runtime_state health_state restart_count <<<"$container_state"
  if [[ "$runtime_state" != "running" ]]; then
    fail "container not running: $container ($runtime_state)"
  elif [[ "$health_state" != "none" && "$health_state" != "healthy" ]]; then
    fail "container health failed: $container ($health_state)"
  elif [[ ! "$restart_count" =~ ^[0-9]+$ ]]; then
    fail "container restart count unreadable: $container"
  else
    pass "container:$container"
  fi
done

if [[ ! -d "$RESORT_BACKUP_DIR" ]]; then
  fail "backup directory missing: $RESORT_BACKUP_DIR"
else
  fresh_backup=$(find "$RESORT_BACKUP_DIR" -maxdepth 1 -type f \
    -name 'resort_os_*.dump' -mmin "-${RESORT_BACKUP_MAX_AGE_MINUTES}" \
    -size +0c -print -quit 2>/dev/null || true)
  if [[ -n "$fresh_backup" ]]; then
    pass "backup-fresh"
  else
    fail "no non-empty database backup newer than ${RESORT_BACKUP_MAX_AGE_MINUTES} minutes"
  fi
fi

if certificate_chain=$(timeout 10 openssl s_client \
  -connect "127.0.0.1:443" \
  -servername "$RESORT_PUBLIC_IP" </dev/null 2>/dev/null); then
  if openssl x509 -noout -checkend "$RESORT_CERT_MIN_VALID_SECONDS" \
    <<<"$certificate_chain" >/dev/null 2>&1; then
    pass "tls-validity"
  else
    fail "TLS certificate expires within ${RESORT_CERT_MIN_VALID_SECONDS} seconds"
  fi
else
  fail "TLS certificate handshake failed"
fi

disk_used_percent=$(df -P / | awk 'NR == 2 {gsub("%", "", $5); print $5}')
if [[ "$disk_used_percent" =~ ^[0-9]+$ ]] &&
   (( disk_used_percent < RESORT_DISK_WARN_PERCENT )); then
  pass "disk-root"
else
  fail "root disk usage is ${disk_used_percent:-unknown}% (threshold ${RESORT_DISK_WARN_PERCENT}%)"
fi

if ((${#failures[@]} > 0)); then
  echo "RESORT_HEALTHCHECK_FAILED count=${#failures[@]} passes=${#passes[@]}"
  for item in "${failures[@]}"; do
    echo "FAIL: $item"
  done
  exit 1
fi

echo "RESORT_HEALTHCHECK_OK passes=${#passes[@]}"

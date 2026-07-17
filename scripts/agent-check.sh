#!/usr/bin/env bash
# Read-only repository baseline for Claude, Codex, and human reviewers.

set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
MODE="${1:---quick}"
FAILURES=0

if [[ "$MODE" != "--quick" && "$MODE" != "--full" ]]; then
  echo "Usage: bash scripts/agent-check.sh [--quick|--full]" >&2
  exit 2
fi

section() {
  printf '\n== %s ==\n' "$1"
}

run_check() {
  local label="$1"
  shift
  printf '\n[%s]\n' "$label"
  if "$@"; then
    printf '[PASS] %s\n' "$label"
  else
    printf '[FAIL] %s\n' "$label" >&2
    FAILURES=1
  fi
}

collect_tests() {
  local output
  if ! output="$(
    cd "$ROOT_DIR/backend"
    .venv/bin/pytest tests/ --collect-only -q -o addopts='' 2>&1
  )"; then
    printf '%s\n' "$output" >&2
    return 1
  fi
  printf '%s\n' "$output" | tail -n 1
}

check_backend_tools() {
  [[ -x "$ROOT_DIR/backend/.venv/bin/python" ]] || {
    echo "backend/.venv is missing; run the documented install first." >&2
    return 1
  }
  "$ROOT_DIR/backend/.venv/bin/python" --version
  "$ROOT_DIR/backend/.venv/bin/pytest" --version
  "$ROOT_DIR/backend/.venv/bin/alembic" --version
}

check_frontend_tools() {
  command -v node >/dev/null 2>&1 || {
    echo "node is not installed." >&2
    return 1
  }
  command -v pnpm >/dev/null 2>&1 || {
    echo "pnpm is not installed." >&2
    return 1
  }
  node --version
  pnpm --version
  [[ -d "$ROOT_DIR/frontend/node_modules" ]] || {
    echo "frontend/node_modules is missing; run pnpm install in frontend/." >&2
    return 1
  }
}

check_alembic_heads() {
  cd "$ROOT_DIR/backend"
  .venv/bin/alembic heads
}

check_compose_development() {
  cd "$ROOT_DIR"
  docker compose config --quiet
}

check_compose_production() {
  cd "$ROOT_DIR"
  docker compose -f docker-compose.prod.yml config --quiet
}

run_backend_tests() {
  cd "$ROOT_DIR/backend"
  .venv/bin/pytest tests/ -v
}

run_frontend_type_check() {
  cd "$ROOT_DIR/frontend"
  pnpm run type-check:all
}

run_frontend_build() {
  cd "$ROOT_DIR/frontend"
  pnpm run build:all
}

section "Repository"
cd "$ROOT_DIR"
printf 'Root: %s\n' "$ROOT_DIR"
printf 'Branch: %s\n' "$(git branch --show-current)"
printf 'HEAD: %s\n' "$(git rev-parse --short HEAD)"
git status --short --branch
printf '\nWorktrees:\n'
git worktree list

section "Environment"
run_check "Backend toolchain" check_backend_tools
run_check "Frontend toolchain" check_frontend_tools

section "Read-only project checks"
run_check "Alembic heads" check_alembic_heads
run_check "Pytest collection" collect_tests
run_check "Development Compose config" check_compose_development
run_check "Production Compose config" check_compose_production
run_check "Git whitespace check" git -C "$ROOT_DIR" diff --check

if [[ "$MODE" == "--full" ]]; then
  section "Full validation"
  run_check "Backend test suite" run_backend_tests
  run_check "Frontend type-check" run_frontend_type_check
  run_check "Frontend production builds" run_frontend_build
fi

section "Result"
if [[ "$FAILURES" -ne 0 ]]; then
  echo "One or more checks failed. Review the evidence above; do not report a clean baseline."
  exit 1
fi

if [[ "$MODE" == "--full" ]]; then
  echo "Full local validation completed successfully."
else
  echo "Quick read-only baseline completed successfully."
fi

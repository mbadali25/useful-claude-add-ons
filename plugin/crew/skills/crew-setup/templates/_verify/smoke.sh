#!/usr/bin/env bash
# _verify/smoke.sh - fast and shallow. Exit 0 = safe to merge/promote, 1 = stop.
# 5-9 checks, under 90 seconds total. Depth belongs in run-all.sh.
set -uo pipefail

ENV="${ENV:-dev}"
while [ $# -gt 0 ]; do
  case "$1" in
    --env) ENV="$2"; shift 2 ;;
    --env=*) ENV="${1#*=}"; shift ;;
    *) shift ;;
  esac
done

# Resolve the target and SAY IT. A suite that passes against the wrong
# environment is the most convincing wrong answer available.
case "$ENV" in
  dev|development) BASE="http://localhost:8080" ;;
  qa)              BASE="https://qa.example.internal" ;;
  prod|production) BASE="https://www.example.com" ;;
  *) echo "unknown env: $ENV" >&2; exit 1 ;;
esac
echo "SMOKE target: $ENV -> $BASE"

PASS=0; FAIL=0
check() { local n="$1"; shift
  if "$@" >/dev/null 2>&1; then echo "PASS $n"; PASS=$((PASS+1))
  else echo "FAIL $n: $*"; FAIL=$((FAIL+1)); fi; }

# setup (ephemeral, never prod)
# docker compose -f docker-compose.smoke.yml up -d --wait
# trap 'docker compose -f docker-compose.smoke.yml down -v' EXIT

# check "boots"           curl -fsS "$BASE/health"
# check "rejects-anon"    test "$(curl -s -o /dev/null -w '%{http_code}' "$BASE/api/me")" = "401"
# check "auth-works"      ./_verify/cases/login.sh --env "$ENV"
# check "read-path"       ./_verify/cases/read.sh --env "$ENV"
# check "write-roundtrip" ./_verify/cases/write-roundtrip.sh --env "$ENV"
# check "migrations"      ./_verify/cases/migrate-fresh.sh

echo "SMOKE: $PASS/$((PASS+FAIL)) passed against $ENV"
[ "$FAIL" -eq 0 ] || exit 1

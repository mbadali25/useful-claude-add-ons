#!/usr/bin/env bash
# scripts/smoke.sh — exit 0 = safe to merge, 1 = stop.
set -uo pipefail
PASS=0; FAIL=0
check() { local n="$1"; shift
  if "$@" >/dev/null 2>&1; then echo "PASS $n"; PASS=$((PASS+1))
  else echo "FAIL $n: $*"; FAIL=$((FAIL+1)); fi; }

# setup (ephemeral, never prod)
# docker compose -f docker-compose.smoke.yml up -d --wait
# trap 'docker compose -f docker-compose.smoke.yml down -v' EXIT

# 5-9 checks, under 90s total
# check "boots"           curl -fsS http://localhost:8080/health
# check "rejects-anon"    test "$(curl -s -o /dev/null -w '%{http_code}' localhost:8080/api/me)" = "401"
# check "auth-works"      ./scripts/_smoke/login.sh
# check "read-path"       ./scripts/_smoke/read.sh
# check "write-roundtrip" ./scripts/_smoke/write.sh
# check "migrations"      ./scripts/_smoke/migrate-fresh.sh

echo "SMOKE: $PASS/$((PASS+FAIL)) passed"
[ "$FAIL" -eq 0 ] || exit 1

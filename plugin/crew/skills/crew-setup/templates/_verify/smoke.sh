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

# A failing check prints its last 5 output lines under its FAIL line, so the
# cause is in the log. Exit 77 is SKIP (a missing tool or environment), not a
# failure - the same convention crew's verify gate uses. The output goes to a
# temp file, not a $(...) capture, so a background process the check leaves
# holding the pipe cannot hold the runner open. Each tail line starts
# `FAIL <name> |`: crew's verify gate relays only lines starting `FAIL` or
# `SMOKE:` from a failed smoke run, so an indented line would never reach it.
# The capture file of the check in progress is removed on every exit, a
# signal included (INT, TERM and HUP end the run through the EXIT trap).
# Add your own teardown to cleanup(): a second `trap ... EXIT` would replace
# this one.
CUR_OUT=""
cleanup() { [ -z "$CUR_OUT" ] || rm -f "$CUR_OUT"; }
trap cleanup EXIT
trap 'exit 130' INT; trap 'exit 143' TERM; trap 'exit 129' HUP
PASS=0; FAIL=0; SKIP=0
check() { local n="$1" out rc f; shift
  f="$(mktemp)" || { echo "FAIL $n: cannot create a temp file"; FAIL=$((FAIL+1)); return; }
  CUR_OUT="$f"
  "$@" >"$f" 2>&1; rc=$?
  out="$(tail -n 5 "$f")"; rm -f "$f"; CUR_OUT=""
  if [ "$rc" -eq 0 ]; then echo "PASS $n"; PASS=$((PASS+1))
  elif [ "$rc" -eq 77 ]; then echo "SKIP $n (exit 77: tool or environment absent)"; SKIP=$((SKIP+1))
  else echo "FAIL $n: $*"; [ -z "$out" ] || printf '%s\n' "$out" | while IFS= read -r l; do printf 'FAIL %s | %s\n' "$n" "$l"; done
    FAIL=$((FAIL+1)); fi; }

# setup (ephemeral, never prod)
# docker compose -f docker-compose.smoke.yml up -d --wait
# and put `docker compose -f docker-compose.smoke.yml down -v` in cleanup() above

# check "boots"           curl -fsS "$BASE/health"
# check "rejects-anon"    test "$(curl -s -o /dev/null -w '%{http_code}' "$BASE/api/me")" = "401"
# check "auth-works"      ./_verify/cases/login.sh --env "$ENV"
# check "read-path"       ./_verify/cases/read.sh --env "$ENV"
# check "write-roundtrip" ./_verify/cases/write-roundtrip.sh --env "$ENV"
# check "migrations"      ./_verify/cases/migrate-fresh.sh

echo "SMOKE: $PASS/$((PASS+FAIL)) passed, $SKIP skipped against $ENV"
[ "$FAIL" -eq 0 ] || exit 1

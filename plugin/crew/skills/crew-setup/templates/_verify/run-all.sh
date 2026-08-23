#!/usr/bin/env bash
# _verify/run-all.sh - the regression suite. Slow and broad, on purpose.
#
# smoke.sh answers "did the deploy land". This answers "does everything that
# worked yesterday still work". They are separate gates because a green smoke
# run says nothing about the module three directories over that just broke.
set -uo pipefail

ENV="${ENV:-dev}"
READONLY=0
while [ $# -gt 0 ]; do
  case "$1" in
    --env) ENV="$2"; shift 2 ;;
    --env=*) ENV="${1#*=}"; shift ;;
    --read-only) READONLY=1; shift ;;
    *) shift ;;
  esac
done

echo "REGRESSION target: $ENV${READONLY:+ (read-only)}"

# Production runs read-only or it does not run. This is not a preference.
if [ "$ENV" = "prod" ] || [ "$ENV" = "production" ]; then
  if [ "$READONLY" -ne 1 ]; then
    echo "FAIL refusing to run write checks against production. Pass --read-only." >&2
    exit 1
  fi
fi

PASS=0; FAIL=0; SKIP=0
run() { local n="$1"; shift
  if "$@" >/dev/null 2>&1; then echo "PASS $n"; PASS=$((PASS+1))
  else echo "FAIL $n: $*"; FAIL=$((FAIL+1)); fi; }
skip() { echo "SKIP $1 ($2)"; SKIP=$((SKIP+1)); }

# The language's own runner belongs here, not replaced by it.
# run "unit"     npm test
# run "unit"     pytest -q
# run "unit"     dotnet test --nologo

# Every case file, unless it is write-shaped and we are read-only.
# --read-only is an ALLOWLIST, not a denylist. A case runs only if it declares
# itself read-only; an unmarked case is assumed to write, because the cost of
# guessing wrong is a write against production.
for c in _verify/cases/*.sh; do
  [ -f "$c" ] || continue
  name=$(basename "$c" .sh)
  if [ "$READONLY" -eq 1 ] && ! grep -q '^# readonly: yes' "$c"; then
    skip "$name" "not declared '# readonly: yes'"
    continue
  fi
  run "$name" bash "$c" --env "$ENV"
done

echo "REGRESSION: $PASS passed, $FAIL failed, $SKIP skipped against $ENV"
[ "$FAIL" -eq 0 ] || exit 1

#!/usr/bin/env bash
#
# PreToolUse plan-approval + scope guard on Write|Edit|MultiEdit|NotebookEdit.
# Thin wrapper: the whole decision lives in scope_guard.py, so bash and
# PowerShell cannot drift -- same shape as role-write-guard.sh.
#
# Exit 0 allows, exit 2 refuses (stderr is the reason). scope_guard.py itself
# only ever exits 0 or 2. Any other status means python did not judge the
# call; that fails CLOSED where .crew/config.json sets `scope.mode` to block or auto
# (it opted in) and open elsewhere, where the guard is off by default.
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
. "$DIR/_common.sh"

INPUT=$(cat)

# `scope.mode` is block or auto in the repo config. Crude on purpose: it runs
# only when python could not, so it cannot use a JSON parser.
_scope_opted_in() {
  tr -d '\r\n' < "${CLAUDE_PROJECT_DIR:-$PWD}/.crew/config.json" 2>/dev/null \
    | grep -Eq '"scope"[[:space:]]*:[[:space:]]*\{[^}]*"mode"[[:space:]]*:[[:space:]]*"(block|auto)"'
}

PY=$(crew_py_strict) || {
  if _scope_opted_in; then
    echo "SCOPE GUARD: no usable python - cannot judge this write; failing closed because scope.mode is block or auto." >&2
    exit 2
  fi
  echo "scope-guard: no usable python - cannot judge this write, allowing it unjudged." >&2
  exit 0
}

printf '%s' "$INPUT" | PYTHONUTF8=1 PYTHONIOENCODING=utf-8 "$PY" "$DIR/scope_guard.py"
status=$?

if [ "$status" -ne 0 ] && [ "$status" -ne 2 ]; then
  if _scope_opted_in; then
    echo "SCOPE GUARD: scope_guard.py did not run to a decision (exit $status); failing closed because scope.mode is block or auto." >&2
    exit 2
  fi
  echo "scope-guard: scope_guard.py did not run to a decision (exit $status); allowing it unjudged." >&2
  exit 0
fi
exit "$status"

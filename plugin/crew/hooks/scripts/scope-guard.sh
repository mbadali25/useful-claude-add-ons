#!/usr/bin/env bash
#
# PreToolUse plan-approval + scope guard on Write|Edit|MultiEdit|NotebookEdit,
# and the approval-forgery check on Bash|PowerShell. Thin wrapper: the whole
# decision lives in scope_guard.py, so bash and PowerShell cannot drift --
# same shape as role-write-guard.sh.
#
# Exit 0 allows, exit 2 refuses (stderr is the reason). scope_guard.py itself
# only ever exits 0 or 2. Any other status, or no python at all, means nothing
# was judged; that fails CLOSED unless .crew/config.json PROVABLY sets
# `scope.mode` to off -- python resolves a corrupt config or an unknown mode
# to block, so a wrapper that recognised only literal block/auto would be the
# one place those shapes failed open.
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
. "$DIR/_common.sh"

INPUT=$(cat)

# BYTE-FOR-BYTE the copy in completion-audit.sh (asserted by the tests).
# True only when `.crew/config.json` PROVABLY leaves the scope hooks off: the
# file is absent, or it is one JSON object (crudely: starts `{`, ends `}`,
# braces balance) with exactly one "scope" key, whose object has exactly one
# "mode", and that mode is "off". Crude on purpose -- it runs only when python
# could not, so it cannot parse JSON -- and every shape it cannot prove is NOT
# off: corrupt, an unknown mode, report, auto, block, or no scope key at all.
_scope_provably_off() {
  local cfg="${CLAUDE_PROJECT_DIR:-$PWD}/.crew/config.json" text obj
  [ -e "$cfg" ] || [ -L "$cfg" ] || return 0
  { [ -f "$cfg" ] && [ -r "$cfg" ]; } || return 1
  text=$(tr -d '\r\n' < "$cfg") || return 1
  text=${text#$'\xef\xbb\xbf'}
  text=$(printf '%s' "$text" | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//')
  case "$text" in '{'*'}') ;; *) return 1 ;; esac
  [ "$(printf '%s' "$text" | tr -cd '{' | wc -c)" -eq \
    "$(printf '%s' "$text" | tr -cd '}' | wc -c)" ] || return 1
  [ "$(printf '%s' "$text" | grep -o '"scope"' | wc -l)" -eq 1 ] || return 1
  obj=$(printf '%s' "$text" | sed -n 's/.*"scope"[[:space:]]*:[[:space:]]*\({[^{}]*}\).*/\1/p')
  [ -n "$obj" ] || return 1
  [ "$(printf '%s' "$obj" | grep -o '"mode"' | wc -l)" -eq 1 ] || return 1
  printf '%s' "$obj" | grep -Eq '"mode"[[:space:]]*:[[:space:]]*"off"'
}

PY=$(crew_py_strict) || {
  if _scope_provably_off; then
    echo "scope-guard: no usable python - not judged (scope.mode is off)." >&2
    exit 0
  fi
  echo "SCOPE GUARD: no usable python - cannot judge this call; failing closed because .crew/config.json does not provably set scope.mode off." >&2
  exit 2
}

printf '%s' "$INPUT" | PYTHONUTF8=1 PYTHONIOENCODING=utf-8 "$PY" "$DIR/scope_guard.py"
status=$?

if [ "$status" -ne 0 ] && [ "$status" -ne 2 ]; then
  if _scope_provably_off; then
    echo "scope-guard: scope_guard.py did not run to a decision (exit $status); not judged (scope.mode is off)." >&2
    exit 0
  fi
  echo "SCOPE GUARD: scope_guard.py did not run to a decision (exit $status); failing closed because .crew/config.json does not provably set scope.mode off." >&2
  exit 2
fi
exit "$status"

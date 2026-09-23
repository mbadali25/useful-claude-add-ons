#!/usr/bin/env bash
#
# Stop-time completion scope audit. Thin wrapper: the decision lives in
# completion_audit.py (0 lines on pass, <= 6 on fail, exit 2 blocks the Stop).
# `stop_hook_active` is honoured in python, and here too, so a continuation
# the audit caused is never blocked again even if python is broken.
#
# Any python status other than 0 or 2 means nothing was audited; that blocks
# once where .crew/config.json sets `scope.mode` to block or auto, and is allowed
# (with a note) elsewhere, where the audit is off by default.
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
. "$DIR/_common.sh"

INPUT=$(cat)
case "$INPUT" in *'"stop_hook_active": true'*|*'"stop_hook_active":true'*) exit 0 ;; esac

# `scope.mode` is block or auto in the repo config. Crude on purpose: it runs
# only when python could not, so it cannot use a JSON parser.
_scope_opted_in() {
  tr -d '\r\n' < "${CLAUDE_PROJECT_DIR:-$PWD}/.crew/config.json" 2>/dev/null \
    | grep -Eq '"scope"[[:space:]]*:[[:space:]]*\{[^}]*"mode"[[:space:]]*:[[:space:]]*"(block|auto)"'
}

PY=$(crew_py_strict) || {
  if _scope_opted_in; then
    echo "COMPLETION AUDIT: no usable python - the tree was not audited against the ticket's scope." >&2
    exit 2
  fi
  echo "completion audit: no usable python - not audited." >&2
  exit 0
}

printf '%s' "$INPUT" | PYTHONUTF8=1 PYTHONIOENCODING=utf-8 "$PY" "$DIR/completion_audit.py"
status=$?

if [ "$status" -ne 0 ] && [ "$status" -ne 2 ]; then
  if _scope_opted_in; then
    echo "COMPLETION AUDIT: completion_audit.py did not run to a verdict (exit $status); nothing was audited." >&2
    exit 2
  fi
  echo "completion audit: completion_audit.py did not run to a verdict (exit $status)." >&2
  exit 0
fi
exit "$status"

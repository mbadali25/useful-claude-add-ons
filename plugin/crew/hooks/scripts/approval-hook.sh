#!/usr/bin/env bash
#
# UserPromptSubmit: record a plan approval when the user types
# `/crew:approve <id>`. Thin wrapper: the decision lives in approval_hook.py.
#
# Every prompt the user submits passes through here, so the common case must
# be cheap: a prompt that does not contain `crew:approve` exits 0 before any
# python is looked for. One that does and cannot be judged (no python, or
# python did not run to a decision) is BLOCKED with the reason: the user
# asked for an approval, and saying nothing would let them believe one was
# recorded.
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
. "$DIR/_common.sh"

INPUT=$(cat)
case "$INPUT" in *crew:approve*) ;; *) exit 0 ;; esac

PY=$(crew_py_strict) || {
  echo "crew: /crew:approve was NOT recorded -- no usable python to validate the plan." >&2
  exit 2
}

printf '%s' "$INPUT" | PYTHONUTF8=1 PYTHONIOENCODING=utf-8 "$PY" "$DIR/approval_hook.py"
status=$?

if [ "$status" -ne 0 ] && [ "$status" -ne 2 ]; then
  echo "crew: /crew:approve was NOT recorded -- approval_hook.py did not run to a decision (exit $status)." >&2
  exit 2
fi
exit "$status"

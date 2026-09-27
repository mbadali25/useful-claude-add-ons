#!/usr/bin/env bash
#
# UserPromptSubmit: record a plan approval when the user types
# `/crew:approve <id>` (or a group: several ids, a range, or the plain-text
# `approve T-1 through T-3`, then `/crew:approve --confirm`). Thin wrapper:
# the decision lives in approval_hook.py.
#
# Every prompt the user submits passes through here, so the common case must
# be cheap: a prompt that does not contain the word `approve` (any case)
# exits 0 before any python is looked for. With no usable python, only a
# prompt containing `crew:approve` is BLOCKED with the reason -- the user
# asked for an approval, and saying nothing would let them believe one was
# recorded. A plain-text "approve T-1" passes through unrecorded instead:
# blocking it would block every prompt that uses the word. Python that runs
# and does not reach a decision blocks, as before.
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
. "$DIR/_common.sh"

INPUT=$(cat)
case "$INPUT" in *[Aa][Pp][Pp][Rr][Oo][Vv][Ee]*) ;; *) exit 0 ;; esac

PY=$(crew_py_strict) || {
  case "$INPUT" in *crew:approve*) ;; *) exit 0 ;; esac
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

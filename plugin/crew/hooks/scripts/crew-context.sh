#!/usr/bin/env bash
# crew's context hook: SessionStart, UserPromptSubmit, PostToolUse and
# SubagentStart, for Claude Code (no arguments) and Codex (--harness codex).
# stdout is an additionalContext payload or nothing. NEVER blocks: every path
# exits 0 and nothing here or in crew_context.py prints a `decision`.
#
# Thin wrapper on purpose, like platform-sync.sh: the logic, the budgets and the
# one-flavour-per-event claim all live in crew_context.py, so the bash and
# PowerShell paths cannot drift.
#
# `crew_py_strict`, NOT `crew_py`: `crew_py`'s bare `command -v` accepts the
# Windows Store App Execution Alias stub, and `exec` would then launch a file
# that prints nothing -- read on a fresh session as "no context", not as a
# broken interpreter. The failure is named on stderr and the hook still
# exits 0.
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
. "$DIR/_common.sh"
PY=$(crew_py_strict) || { echo "crew context: no usable python (stub or unusable interpreter) - no code-map or recall context this event" >&2; exit 0; }
"$PY" "$DIR/crew_context.py" "$@"
exit 0

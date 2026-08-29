#!/usr/bin/env bash
# Stop hook. Re-engages the crew PM when the project state actually changed.
#
# Thin wrapper on purpose. The logic lives in pm_pulse.py so the bash and
# PowerShell paths cannot drift, and the de-duplication between the two
# flavours lives there too -- keyed on the state fingerprint rather than on
# the session, because unlike SessionStart this event fires every turn. See
# pm_pulse.py's module docstring for why hook_once is the wrong tool here.
#
# This hook can exit 2 to block. `exec` matters: without it the exit code is
# the subshell's, and a swallowed 2 reads to Claude Code as a non-blocking
# error, which means the PM's findings are dropped on the floor.
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY=$(command -v python3 || command -v python) || exit 0
exec "$PY" "$DIR/pm_pulse.py"

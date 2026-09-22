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
#
# `crew_py_strict`, NOT `crew_py`. Reported 2026-09-22, and the same defect
# role-write-guard.sh was fixed for three days earlier: the WindowsApps App
# Execution Alias is a real executable file, so `crew_py`'s bare `command -v`
# resolves it, the `||` below never fires, and `exec` replaces this shell with
# the stub. The stub writes nothing and exits nonzero, so the hook returns a
# status that is neither 0 nor 2 with an EMPTY stderr -- the PM's findings,
# blocking ones included, gone without the message on the next line ever
# printing. `pm-pulse.ps1` carries the hardened `Resolve-CrewPython` already,
# so until this change WHICH SHELL FLAVOUR Claude Code happened to invoke
# decided whether the PM spoke at all.
#
# `exec` leaves nothing behind that could notice and report the stub's exit
# code, which is why this one has to be resolved before the launch rather
# than checked after it.
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
. "$DIR/_common.sh"
PY=$(crew_py_strict) || { echo "crew pm-pulse: no usable python - the PM's findings, including blocking ones, will not run" >&2; exit 0; }
exec "$PY" "$DIR/pm_pulse.py"

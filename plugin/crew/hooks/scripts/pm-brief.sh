#!/usr/bin/env bash
# SessionStart hook. Prints the crew PM's brief; stdout is injected as context.
#
# Unlike handoff-read.sh this does NOT filter on source -- it must fire on
# `startup` too, which is the whole point: before this hook existed, crew said
# nothing at all when you opened a fresh session.
#
# Thin wrapper on purpose. The logic lives in pm_brief.py so the bash and
# PowerShell paths cannot drift, and the once-per-session claim lives in
# pm_brief.py too so both flavours share one implementation of it.
#
# `crew_py_strict`, NOT `crew_py`. The same defect reported against
# pm-pulse.sh and role-write-guard.sh applies here: `crew_py`'s bare
# `command -v` accepts the Windows Store App Execution Alias stub -- a real,
# executable file that produces no output -- and `exec` then launches it,
# leaving nothing behind that could notice the failure or report it. The
# brief silently never prints, which reads on a fresh session as "crew has
# nothing to say" rather than as a broken interpreter.
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
. "$DIR/_common.sh"
PY=$(crew_py_strict) || { echo "crew pm-brief: no usable python (stub or unusable interpreter) - the PM's brief will not print" >&2; exit 0; }
exec "$PY" "$DIR/pm_brief.py"

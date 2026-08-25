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
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY=$(command -v python3 || command -v python) || exit 0
exec "$PY" "$DIR/pm_brief.py"

#!/usr/bin/env bash
# SessionStart hook. Detects this machine and repairs .crew/config.json's
# platform block, which is committed and is therefore wrong for everybody who
# is not the person who ran /crew:init.
#
# Thin wrapper on purpose. The logic lives in crew_platform.py so the bash and
# PowerShell paths cannot drift, and the once-per-session claim lives there too
# so both flavours share one implementation of it. This matters more here than
# elsewhere: a hook that WRITES config must not have two implementations that
# disagree about what it writes.
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY=$(command -v python3 || command -v python) || exit 0
exec "$PY" "$DIR/crew_platform.py"

#!/usr/bin/env bash
# SessionStart hook. Thin wrapper - the logic lives in bridge_status.py so the
# bash and PowerShell paths cannot drift.
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY=$(command -v python3 || command -v python) || exit 0
exec "$PY" "$DIR/bridge_status.py"

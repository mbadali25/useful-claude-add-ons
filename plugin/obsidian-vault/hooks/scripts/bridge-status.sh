#!/usr/bin/env bash
# SessionStart hook. Thin wrapper - the logic lives in bridge_status.py so the
# bash and PowerShell paths cannot drift.
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY=$(command -v python3 || command -v python || command -v py)
if [ -z "$PY" ]; then
  echo "obsidian-vault bridge-status.sh: no python3/python/py interpreter found on PATH - bridge status cannot run this session." >&2
  exit 0
fi
exec "$PY" "$DIR/bridge_status.py"

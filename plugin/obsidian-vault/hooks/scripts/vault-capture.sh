#!/usr/bin/env bash
# SessionEnd / PreCompact hook. Thin wrapper - the logic lives in
# vault_capture.py so the bash and PowerShell paths cannot drift.
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY=$(command -v python3 || command -v python || command -v py)
if [ -z "$PY" ]; then
  echo "obsidian-vault vault-capture.sh: no python3/python/py interpreter found on PATH - session capture skipped." >&2
  exit 0
fi
exec "$PY" "$DIR/vault_capture.py" "$1"

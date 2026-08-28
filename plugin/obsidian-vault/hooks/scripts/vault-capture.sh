#!/usr/bin/env bash
# SessionEnd / PreCompact hook. Thin wrapper - the logic lives in
# vault_capture.py so the bash and PowerShell paths cannot drift.
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY=$(command -v python3 || command -v python) || exit 0
exec "$PY" "$DIR/vault_capture.py" "$1"

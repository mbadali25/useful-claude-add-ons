#!/usr/bin/env bash
# PostToolUse hook. Thin wrapper - the logic lives in vault_guard.py so the
# bash and PowerShell paths cannot drift.
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY=$(command -v python3 || command -v python) || exit 0
exec "$PY" "$DIR/vault_guard.py"

#!/usr/bin/env bash
# PostToolUse hook. Thin wrapper - the logic lives in vault_guard.py so the
# bash and PowerShell paths cannot drift.
#
# No interpreter found: stand down with exit 0 rather than fail closed (exit
# 2). Every check this guard enforces ships OFF by default until a vault's
# own CLAUDE.md turns one on, so a missing interpreter losing the guard is
# not a worse failure mode than the guard never being configured at all -
# but it must say so loudly rather than exiting silently.
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY=$(command -v python3 || command -v python || command -v py)
if [ -z "$PY" ]; then
  echo "obsidian-vault vault-guard.sh: no python3/python/py interpreter found on PATH - guard is standing down for this write (exit 0, not fail-closed; see script comment)." >&2
  exit 0
fi
exec "$PY" "$DIR/vault_guard.py"

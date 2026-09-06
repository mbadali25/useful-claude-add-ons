#!/usr/bin/env bash
# PostToolUse hook. Thin wrapper - the logic lives in vault_guard.py so the
# bash and PowerShell paths cannot drift.
#
# No interpreter found: stand down with exit 0 rather than fail closed (exit
# 2). The two contract rules - frontmatter and ASCII - ship OFF until a
# vault's own CLAUDE.md turns one on, so losing those is no worse than the
# guard never being configured. The canvas shape check does NOT: checkCanvas
# defaults ON (vault_guard.py:243), so a missing interpreter does drop one
# check that would otherwise be running. Still not worth failing closed on
# every edit - but it must say so loudly rather than exiting silently.
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY=$(command -v python3 || command -v python || command -v py)
if [ -z "$PY" ]; then
  echo "obsidian-vault vault-guard.sh: no python3/python/py interpreter found on PATH - guard is standing down for this write (exit 0, not fail-closed; see script comment)." >&2
  exit 0
fi
exec "$PY" "$DIR/vault_guard.py"

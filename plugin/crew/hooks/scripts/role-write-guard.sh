#!/usr/bin/env bash
#
# PreToolUse gate on Write/Edit, keyed on `agent_type`. Thin wrapper: the
# whole decision lives in role_write_guard.py so bash and PowerShell cannot
# drift -- same shape as pm-brief.sh -> pm_brief.py.
#
# Registered on matcher `Write|Edit`, not branched by tool_name the way
# promote-gate.sh branches on Bash vs PowerShell: Write and Edit are the same
# tool regardless of which shell is installed, so both flavours here are
# simply wired to the event, like verify-gate.sh/.ps1, and one is expected to
# be the flavour that actually runs on a given machine.
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
. "$DIR/_common.sh"

INPUT=$(cat)

PY=$(crew_py) || {
  echo "role-write-guard: no usable python - cannot judge this write, allowing it unjudged." >&2
  exit 0
}
printf '%s' "$INPUT" | "$PY" "$DIR/role_write_guard.py"
exit $?

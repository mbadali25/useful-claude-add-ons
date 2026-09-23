#!/usr/bin/env bash
#
# PreToolUse cloud/destructive guard on the Bash AND PowerShell tools. Thin
# wrapper: the whole decision lives in cloud_guard.py, which reads the payload's
# `tool_name` and parses the command as bash or as PowerShell accordingly --
# the branch is which TOOL ran, never which OS this is. So this flavour judges
# a PowerShell-tool command correctly too, and on a host where only bash runs
# hooks (Linux, macOS) that is the only judgement a PowerShell command gets.
#
# Off unless `guards.cloudGuard` is `report` or `block` (default `off`); see
# cloud_guard.py's docstring and plugin/crew/README.md "Cloud guard".
#
# Decisions travel as PreToolUse JSON on stdout with exit 0. The one exit 2
# here is the fallback below: python could not judge, and a config file says
# the guard is armed.
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
. "$DIR/_common.sh"

INPUT=$(cat)

# Whether a config layer arms the guard, read WITHOUT python -- only consulted
# when python could not run at all. Crude on purpose: any `cloudGuard` value
# other than "off", in the repo config or the machine-global one, counts as
# armed, so a value this cannot parse fails closed rather than open.
_cloud_guard_armed() {
  root="${CLAUDE_PROJECT_DIR:-.}"
  for cfg in "$root/.crew/config.json" "$HOME/.claude/crew/config.json"; do
    [ -f "$cfg" ] || continue
    value=$(grep -o '"cloudGuard"[[:space:]]*:[[:space:]]*[^,}]*' "$cfg" 2>/dev/null \
            | head -n 1 | sed -E 's/.*:[[:space:]]*//' | tr -d '"[:space:]\r')
    [ -z "$value" ] && continue
    [ "$value" = "off" ] || return 0
  done
  return 1
}

PY=$(crew_py_strict) || PY=""
if [ -z "$PY" ]; then
  if _cloud_guard_armed; then
    echo "cloud-guard: no usable python, and guards.cloudGuard is armed - refusing rather than letting this command through unjudged." >&2
    exit 2
  fi
  exit 0
fi

printf '%s' "$INPUT" | PYTHONUTF8=1 PYTHONIOENCODING=utf-8 "$PY" "$DIR/cloud_guard.py"
status=$?

if [ "$status" -ne 0 ]; then
  # cloud_guard.py only ever exits 0 -- its decisions are JSON -- so any other
  # status means it never finished judging. PreToolUse treats a status other
  # than 0 or 2 as NON-blocking, so passing it through would be an allow.
  if _cloud_guard_armed; then
    echo "cloud-guard: cloud_guard.py failed (exit $status) and guards.cloudGuard is armed - refusing." >&2
    exit 2
  fi
  echo "cloud-guard: cloud_guard.py failed (exit $status); the guard is not armed, so the command is not judged." >&2
fi
exit 0

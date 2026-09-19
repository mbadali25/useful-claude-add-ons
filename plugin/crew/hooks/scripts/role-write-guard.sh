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

# NOT plain `crew_py()`. That resolver is `command -v python3 || python ||
# py` with no filtering at all, shared by seven other hooks that all fail
# OPEN the same way on a WindowsApps App Execution Alias -- reported
# 2026-09-19: on a machine where a WindowsApps python3 stub sits ahead of a
# real interpreter on PATH, bash silently skipped enforcement (the stub
# produces no usable output and this script fell through the same way it
# does when no python exists at all) while role-write-guard.ps1's own
# hardened Resolve-CrewPython found the real interpreter and ran the check
# -- so which SHELL FLAVOUR Claude Code happened to invoke on a given turn
# decided whether `guards.roleWrites: block` did anything. Changing
# `crew_py()` in _common.sh would fix this hook by widening the blast
# radius to every hook that calls it for a bug specific to the one hook
# that can BLOCK a tool call, so this one carries its own narrower resolver
# instead -- the bash twin of `role-write-guard.ps1`'s
# `Resolve-CrewPython`, not a shared one.
_resolve_role_write_python() {
  for name in python3 python py; do
    candidate=$(command -v "$name" 2>/dev/null) || continue
    case "$candidate" in
      */WindowsApps/*|*\\WindowsApps\\*) continue ;;
    esac
    # `command -v` finding a name on PATH is not enough -- the WindowsApps
    # alias IS a real, executable file, so `command -v python3` resolves it
    # cleanly. Running it and reading back `sys.executable` is what
    # actually tells real python from the stub: the stub produces no
    # parseable stdout (it either does nothing or launches the Store, which
    # cannot happen in this non-interactive pipe) rather than a real
    # interpreter path.
    real=$("$candidate" -c 'import sys; print(sys.executable)' 2>/dev/null) || continue
    [ -n "$real" ] || continue
    case "$real" in
      */WindowsApps/*|*\\WindowsApps\\*) continue ;;
    esac
    # `sys.executable`, not `$candidate`: the PATH-found name may be a shim
    # that re-execs elsewhere, and the probe already paid the cost of
    # asking python where it actually lives.
    printf '%s\n' "$real"
    return 0
  done
  return 1
}

PY=$(_resolve_role_write_python) || {
  echo "role-write-guard: no usable python - cannot judge this write, allowing it unjudged." >&2
  exit 0
}
# PYTHONUTF8=1 / PYTHONIOENCODING=utf-8 in the CHILD's environment only --
# defense in depth alongside role_write_guard.py's own `sys.stdin.buffer`
# read (which does not depend on either), and the actual fix for that
# script's stdout/stderr writes of a non-ASCII path, which DO depend on the
# interpreter's text-mode default. Reported 2026-09-19 against the .ps1
# twin, where a caller's environment explicitly unsetting these could still
# reach python; set here too so neither flavour depends on the CALLER never
# having touched them.
printf '%s' "$INPUT" | PYTHONUTF8=1 PYTHONIOENCODING=utf-8 "$PY" "$DIR/role_write_guard.py"
exit $?

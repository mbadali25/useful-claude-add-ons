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

# Deny-list mirror of role_write_guard.py's `_DENY_ROLES`, plus `pm` (that
# module's other restricted role) -- used ONLY by the launch-failure
# fallback below, mirroring role-write-guard.ps1's own
# `$RestrictedRolesForFallback`. `tests/test_role_write_guard.py`'s parity
# test re-derives the python side from `agents/*.md` on every run and
# asserts this list matches it.
_role_write_is_restricted() {
  case "$1" in
    analyst|compliance-auditor|dba|explorer|infrastructure-architect| \
    kimi-consult|penetration-tester|planner|qa-researcher|qa-reviewer| \
    researcher|security|pm) return 0 ;;
    *) return 1 ;;
  esac
}

# Best-effort `agent_type` extraction from the raw JSON -- never fails, and
# a value this cannot find or parse answers empty (unrestricted). Mirrors
# role-write-guard.ps1's `Get-FallbackRole`: only consulted when python
# could not run at all, so there is no real decision to defer to and this
# never needs to be more than "good enough to fail closed for pm/deny".
_role_write_fallback_role() {
  role=$(printf '%s' "$1" | grep -o '"agent_type"[[:space:]]*:[[:space:]]*"[^"]*"' \
         | head -n 1 | sed -E 's/.*:[[:space:]]*"([^"]*)"/\1/')
  role=$(printf '%s' "$role" | tr '[:upper:]' '[:lower:]')
  case "$role" in
    crew:*) role="${role#crew:}" ;;
  esac
  printf '%s' "$role"
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
status=$?

if [ "$status" -ne 0 ] && [ "$status" -ne 2 ]; then
  # The interpreter did not actually judge this write -- role_write_guard.py
  # itself only ever exits 0 or 2 (hardened against its own exceptions), so
  # ANY other status means python never ran to completion: resolved
  # successfully by the probe above, then deleted, made unexecutable, or
  # otherwise failed to launch before this line (`bash: $PY: No such file
  # or directory` is exit 127; "found but not executable" is 126, but this
  # check does not special-case either -- any status outside {0, 2} is
  # equally "no real decision was reached"). `PreToolUse` treats any exit
  # code other than 0 or 2 as NON-BLOCKING, so without this check the write
  # went through unjudged with only a shell error on stderr -- role-write-
  # guard.ps1's own header already promised this hook fails closed for a
  # restricted role; this closes the same gap on the bash side. Reported
  # and fixed 2026-09-19.
  fallback_role=$(_role_write_fallback_role "$INPUT")
  if _role_write_is_restricted "$fallback_role"; then
    echo "role-write-guard: could not launch the python interpreter ($PY) to judge this write (exit $status); failing closed for role '$fallback_role'." >&2
    exit 2
  fi
  echo "role-write-guard: could not launch the python interpreter ($PY) to judge this write (exit $status); allowing it unjudged." >&2
  exit 0
fi

exit "$status"

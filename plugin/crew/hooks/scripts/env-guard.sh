#!/usr/bin/env bash
#
# PreToolUse environment-dump guard on the Bash AND PowerShell tools (L-0772).
# Thin wrapper: the whole decision lives in env_guard.py, which reads the
# payload's `tool_name` and reads the command as bash or as PowerShell
# accordingly -- the branch is which TOOL ran, never which OS this is.
#
# Off unless `guards.envGuard` is `report` or `block` (default `off`); see
# env_guard.py's docstring and plugin/crew/README.md "Environment guard".
#
# Decisions travel as PreToolUse JSON on stdout with exit 0. The one exit 2
# here is the fallback below: python could not judge, and a config file says
# the guard is armed. Nothing here prints the command or the environment.
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Flavour stand-down: by the TOOL, never by the OS. Both flavours are
# registered and on Windows both run, so each call must be judged by exactly
# one. This flavour judges EVERY Bash call -- nothing about the host (an `OS`
# value, a same-named executable on PATH) can stand it down for one -- and
# stands down for a PowerShell call only when the .ps1 twin will judge it.
# That decision needs `tool_name`, so it is made in env_guard.py
# (`stands_down`), told which flavour is asking through
# CREW_ENV_GUARD_FLAVOUR below. Without python, both flavours fail closed.

. "$DIR/_common.sh"

INPUT=$(cat)

# Whether a config layer arms the guard, read WITHOUT python -- only consulted
# when python could not run at all. Crude on purpose: any `envGuard` value
# other than "off", in the repo config or the machine-global one, counts as
# armed, so a value this cannot parse fails closed rather than open. The repo
# file is the resolved one (crew_repo_config_dir, T-0096): a lane with no config
# of its own reads the main checkout's, and when git cannot tell which that is
# (`unknown`) the guard counts as armed -- an absent own file is no proof of off.
# So does a resolver that is not there at all (`_common.sh` failed to source):
# that is "could not tell" too, and refused as it was before T-0096.
_env_guard_armed() {
  root="${CLAUDE_PROJECT_DIR:-.}"
  command -v crew_repo_config_dir >/dev/null 2>&1 || return 0
  crew_repo_config_dir "$root"
  [ "$CREW_CFG_SOURCE" = unknown ] && return 0
  for cfg in "$CREW_CFG_DIR/config.json" "$HOME/.claude/crew/config.json"; do
    [ -f "$cfg" ] || continue
    value=$(grep -o '"envGuard"[[:space:]]*:[[:space:]]*[^,}]*' "$cfg" 2>/dev/null \
            | head -n 1 | sed -E 's/.*:[[:space:]]*//' | tr -d '"[:space:]\r')
    [ -z "$value" ] && continue
    [ "$value" = "off" ] || return 0
  done
  return 1
}

PY=$(crew_py_strict) || PY=""
if [ -z "$PY" ]; then
  if _env_guard_armed; then
    echo "env-guard: no usable python, and guards.envGuard is armed - refusing rather than letting this command through unjudged." >&2
    exit 2
  fi
  exit 0
fi

printf '%s' "$INPUT" | CREW_ENV_GUARD_FLAVOUR=bash PYTHONUTF8=1 \
  PYTHONIOENCODING=utf-8 "$PY" "$DIR/env_guard.py"
status=$?

if [ "$status" -ne 0 ]; then
  # env_guard.py only ever exits 0 -- its decisions are JSON -- so any other
  # status means it never finished judging. PreToolUse treats a status other
  # than 0 or 2 as NON-blocking, so passing it through would be an allow.
  if _env_guard_armed; then
    echo "env-guard: env_guard.py failed (exit $status) and guards.envGuard is armed - refusing." >&2
    exit 2
  fi
  echo "env-guard: env_guard.py failed (exit $status); the guard is not armed, so the command is not judged." >&2
fi
exit 0

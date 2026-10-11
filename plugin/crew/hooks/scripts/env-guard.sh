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
# armed, so a value this cannot parse fails closed rather than open. EVERY
# `envGuard` in the file is read, not the first (an unrelated key of that name
# cannot hide the guard's), the file is read as one line (a value on the next
# line is still seen, and an empty one is armed), and a file that exists but
# cannot be read, is not one strict JSON object (`_env_guard_json_object`), or
# sits where this user cannot look (`_env_guard_absent`), is armed: python would
# call that layer corrupt, and a corrupt layer blocks. So is a file holding a
# `\u` escape, which could spell the key out of grep's sight, or a `guards`
# that is not an object. The repo
# file is the resolved one (crew_repo_config_dir, T-0096): a lane with no config
# of its own reads the main checkout's, and when git cannot tell which that is
# (`unknown`) the guard counts as armed -- an absent own file is no proof of off.
# So does a resolver that is not there at all (`_common.sh` failed to source):
# that is "could not tell" too, and refused as it was before T-0096.
# Whether "$1" holds one strict JSON object and nothing else (RFC 8259: no
# trailing comma, no comment, no bare word), read by awk because python is
# what is missing. `{"guards":{bad}}` looks like an object to a brace check
# and has no envGuard for grep to find; python calls that layer corrupt. No
# awk, or a file awk cannot read, is "could not tell": not valid.
_env_guard_json_object() {
  command -v awk >/dev/null 2>&1 || return 1
  awk '
    function ws() { while (pos <= n && index(" \t\r\n", substr(s, pos, 1))) pos++ }
    function str(   c, d) {
      pos++
      while (pos <= n) {
        c = substr(s, pos, 1)
        if (c == "\"") { pos++; return 1 }
        if (c == "\\") {
          d = substr(s, pos + 1, 1)
          if (d != "" && index("\"\\/bfnrt", d)) { pos += 2; continue }
          if (d == "u" && substr(s, pos + 2, 4) ~ /^[0-9A-Fa-f][0-9A-Fa-f][0-9A-Fa-f][0-9A-Fa-f]$/) { pos += 6; continue }
          return 0
        }
        if (index(ctl, c)) return 0
        pos++
      }
      return 0
    }
    function val(depth,   c, rest) {
      if (depth > 200) return 0
      ws()
      c = substr(s, pos, 1)
      if (c == "{") return obj(depth)
      if (c == "[") return arr(depth)
      if (c == "\"") return str()
      rest = substr(s, pos, 64)
      if (match(rest, /^-?(0|[1-9][0-9]*)(\.[0-9]+)?([eE][-+]?[0-9]+)?/)) { pos += RLENGTH; return 1 }
      if (substr(s, pos, 4) == "true") { pos += 4; return 1 }
      if (substr(s, pos, 5) == "false") { pos += 5; return 1 }
      if (substr(s, pos, 4) == "null") { pos += 4; return 1 }
      return 0
    }
    function obj(depth) {
      pos++; ws()
      if (substr(s, pos, 1) == "}") { pos++; return 1 }
      while (1) {
        ws()
        if (substr(s, pos, 1) != "\"" || !str()) return 0
        ws()
        if (substr(s, pos, 1) != ":") return 0
        pos++
        if (!val(depth + 1)) return 0
        ws()
        if (substr(s, pos, 1) == ",") { pos++; continue }
        if (substr(s, pos, 1) == "}") { pos++; return 1 }
        return 0
      }
    }
    function arr(depth) {
      pos++; ws()
      if (substr(s, pos, 1) == "]") { pos++; return 1 }
      while (1) {
        if (!val(depth + 1)) return 0
        ws()
        if (substr(s, pos, 1) == ",") { pos++; continue }
        if (substr(s, pos, 1) == "]") { pos++; return 1 }
        return 0
      }
    }
    BEGIN { for (i = 1; i < 32; i++) ctl = ctl sprintf("%c", i) }
    { s = s $0 "\n" }
    END {
      n = length(s); pos = 1; ws()
      if (substr(s, pos, 1) != "{" || !obj(0)) exit 1
      ws()
      exit (pos > n) ? 0 : 1
    }
  ' "$1" 2>/dev/null
}

# Whether "$1" can be said to be absent: nothing is there AND every directory
# above it down from the nearest one that exists can be searched. A config
# under a directory this user cannot enter looks absent to `[ -e ]` too.
_env_guard_absent() {
  [ -e "$1" ] || [ -L "$1" ] && return 1
  dir=$(dirname -- "$1")
  while [ ! -e "$dir" ] && [ ! -L "$dir" ]; do
    parent=$(dirname -- "$dir")
    [ "$parent" = "$dir" ] && break
    dir=$parent
  done
  [ -d "$dir" ] && [ -x "$dir" ]
}

_env_guard_armed() {
  root="${CLAUDE_PROJECT_DIR:-.}"
  command -v crew_repo_config_dir >/dev/null 2>&1 || return 0
  crew_repo_config_dir "$root"
  [ "$CREW_CFG_SOURCE" = unknown ] && return 0
  for cfg in "$CREW_CFG_DIR/config.json" "$HOME/.claude/crew/config.json"; do
    _env_guard_absent "$cfg" && continue
    [ -f "$cfg" ] && [ -r "$cfg" ] || return 0
    _env_guard_json_object "$cfg" || return 0
    flat=$(tr -d '\r\n' < "$cfg" 2>/dev/null) || return 0
    # A `\u` escape can spell the key (`"env\u0047uard"`) where grep cannot
    # see it; python decodes it. Could not tell, so armed.
    case "$flat" in
      *'\u'*) return 0 ;;
    esac
    # A `guards` that is not an object (`"guards": "off"`, `null`) is a
    # corrupt layer to python, so it arms here too.
    printf '%s' "$flat" \
      | grep -Eq '"guards"[[:space:]]*:[[:space:]]*[^{[:space:]]' 2>/dev/null \
      && return 0
    # The value is the whole JSON string (`"off,block"` is not `off`), or
    # the bare token up to the next `,` or `}`; only exactly "off" is off.
    values=$(printf '%s' "$flat" \
             | grep -oE '"envGuard"[[:space:]]*:[[:space:]]*("[^"]*"|[^,}]*)' 2>/dev/null \
             | sed -E 's/^"envGuard"[[:space:]]*:[[:space:]]*//; s/[[:space:]]+$//')
    printf '%s' "$flat" | grep -q '"envGuard"' 2>/dev/null || continue
    printf '%s\n' "$values" | while IFS= read -r value; do
      [ "$value" = '"off"' ] || exit 1
    done || return 0
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

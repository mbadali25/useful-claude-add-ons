#!/usr/bin/env bash
#
# crew-hook.sh <Event> [--harness codex]: the POSIX launcher behind every crew
# hook registration (L-0727). hooks.json registers this once per event; it runs
# crew_hook.py, which picks the event's hook scripts, runs them concurrently and
# merges their results (see crew_hook.py).
#
# This launcher SUPERVISES crew_hook.py, it does not `exec` it. Exit 0 and 2
# pass through. Anything else (an import error, a syntax error, a signal, the
# deadline) means the dispatcher never reached a decision, and PreToolUse,
# UserPromptSubmit and Stop are events where a hook may block: in an ARMED repo
# that is exit 2 with a named reason, otherwise exit 0 (spec A7, B8). One
# deadline, taken here and exported as CREW_HOOK_DEADLINE (epoch ms), covers the
# python probe, the stdin read, the children and the cleanup; it is the
# registration timeout in hooks.json minus 5 s, so the launcher refuses itself
# before the outer timeout turns a fault into an allow.
#
# On Windows the PowerShell launcher is the single path (crew-hook.ps1), so this
# one exits 0 there: `uname -s` MINGW*/MSYS*/CYGWIN* or $OS = Windows_NT. It
# dispatches only when both say "not Windows" or cannot be read.
#
# With no usable python it runs the event's `.sh` scripts directly from the
# static list in `_rows_for` below, in parallel, and combines them by exit code
# (any 2 -> 2) and stdout order. Each script's own no-python fallback then
# decides, exactly as it did when it was registered alone. The list is asserted
# equal to crew_hook.TABLE by tests/test_hooks_json_shape.py.
_src="${BASH_SOURCE[0]}"
case "$_src" in
  */*) DIR="$(cd "${_src%/*}" && pwd)" ;;
  *) DIR="$(pwd)" ;;
esac

EVENT="${1:-}"
HARNESS=claude
if [ "${2:-}" = "--harness" ]; then
  HARNESS="${3:-claude}"
fi

case "$(uname -s 2>/dev/null)" in
  MINGW*|MSYS*|CYGWIN*) exit 0 ;;
esac
[ "${OS:-}" = "Windows_NT" ] && exit 0

# Registration timeout (s) per event, from hooks.json: the largest hook in the
# event plus 10. A test asserts this equals crew_hook.event_timeout.
case "$EVENT" in
  SessionStart|UserPromptSubmit|PreToolUse) TIMEOUT=30 ;;
  PostToolUse) TIMEOUT=20 ;;
  SubagentStart|Notification) TIMEOUT=25 ;;
  PreCompact) TIMEOUT=40 ;;
  Stop) TIMEOUT=610 ;;
  *) exit 0 ;;
esac

# printf's %(...)T is a builtin (bash 4.2+); `date` is the fallback, a fork.
printf -v START_S '%(%s)T' -1 2>/dev/null || START_S=$(date +%s 2>/dev/null) || START_S=0
DEADLINE_MS=$(( (START_S + TIMEOUT - 5) * 1000 ))
# An inherited deadline may only bring the deadline forward (the fault tests).
case "${CREW_HOOK_DEADLINE:-}" in
  ''|*[!0-9]*) ;;
  *) [ "$CREW_HOOK_DEADLINE" -lt "$DEADLINE_MS" ] && DEADLINE_MS="$CREW_HOOK_DEADLINE" ;;
esac
export CREW_HOOK_DEADLINE="$DEADLINE_MS"

_blocking_event() {
  case "$EVENT" in PreToolUse|UserPromptSubmit|Stop) return 0 ;; esac
  return 1
}

# Exists, or cannot be told: a path that is absent while the nearest ancestor
# that does exist cannot be searched is "could not stat", which counts as there.
_present() {
  [ -e "$1" ] || [ -L "$1" ] && return 0
  local p
  p=$(dirname "$1")
  while [ ! -e "$p" ] && [ "$p" != "/" ] && [ "$p" != "." ]; do
    p=$(dirname "$p")
  done
  [ -d "$p" ] && [ -x "$p" ] && return 1
  return 0
}

# A superset of crew_hook.armed(): true when any crew config could govern this
# repo, or when that cannot be told. tests/test_crew_hook_faults.py asserts
# that every case armed() calls armed, this calls armed too.
_armed() {
  local root="${CLAUDE_PROJECT_DIR:-$PWD}"
  [ -n "$root" ] && [ -d "$root" ] || return 0
  local path
  for path in "$root/.crew/config.json" "$root/.crew/crew.json" "$root/.crew" "$root/.git" \
              "${HOME:-/nonexistent-home}/.claude/crew/config.json"; do
    case "$path" in
      */.git)
        # a directory .git is an ordinary repo; a FILE is a linked worktree (it
        # may inherit the main checkout's config), and an unreadable one is
        # "could not tell"
        [ -f "$path" ] && return 0
        [ -d "$path" ] && continue
        _present "$path" && return 0
        ;;
      *) _present "$path" && return 0 ;;
    esac
  done
  return 1
}

_fail() {
  if _blocking_event && _armed; then
    echo "crew-hook: $1; failing closed (armed repo)." >&2
    exit 2
  fi
  echo "crew-hook: $1; the repo is not armed, or this event cannot block, so nothing is blocked." >&2
  exit 0
}

# --- no python: the event's scripts, straight from a static list -------------
# script;extra args;matcher ("" = every payload, "@vault" = the obsidian/vault
# MCP tools, otherwise a |-separated tool list). One line per crew_hook.TABLE row.
_rows_for() {
  if [ "$HARNESS" = codex ]; then
    case "$EVENT" in
      SessionStart|UserPromptSubmit|SubagentStart) printf '%s\n' 'crew-context.sh;--harness codex;' ;;
      PostToolUse) printf '%s\n' 'crew-context.sh;--harness codex;apply_patch|Edit|Write' \
                                 'crew-context.sh;--harness codex;@vault' ;;
    esac
    return 0
  fi
  case "$EVENT" in
    SessionStart) printf '%s\n' 'handoff-read.sh;;' 'platform-sync.sh;;' 'crew-context.sh;;' ;;
    UserPromptSubmit) printf '%s\n' 'crew-context.sh;;' 'approval-hook.sh;;' ;;
    PreToolUse) printf '%s\n' 'promote-gate.sh;;Bash' 'role-write-guard.sh;;Write|Edit' \
                              'cloud-guard.sh;;Bash|PowerShell' 'env-guard.sh;;Bash|PowerShell' \
                              'scope-guard.sh;;Write|Edit|MultiEdit|NotebookEdit|Bash|PowerShell' ;;
    PostToolUse) printf '%s\n' 'crew-context.sh;;Read|Edit|Write|MultiEdit' 'crew-context.sh;;@vault' ;;
    SubagentStart) printf '%s\n' 'crew-context.sh;;' ;;
    PreCompact) printf '%s\n' 'handoff-write.sh;;' ;;
    Notification) printf '%s\n' 'notify.sh;hook;' ;;
    Stop) printf '%s\n' 'verify-gate.sh;;' 'context-watch.sh;;' 'completion-audit.sh;;' ;;
  esac
}

_tool_matches() {
  # $1 matcher, $2 tool ("" = could not tell: run the row)
  local matcher="$1" tool="$2" name
  [ -z "$matcher" ] && return 0
  [ -z "$tool" ] && return 0
  if [ "$matcher" = "@vault" ]; then
    case "$tool" in
      mcp__*obsidian*|mcp__*vault*|mcp__*basic-memory*|mcp__*basic_memory*) return 0 ;;
    esac
    return 1
  fi
  local IFS='|'
  for name in $matcher; do
    [ "$name" = "$tool" ] && return 0
  done
  return 1
}

_run_without_python() {
  local input tool tmp n=0 script extra matcher rc blocked=0
  input=$(cat <&3)
  tool=""
  # The tool name is read only from a payload that at least ends like a JSON
  # object and names it once; anything else runs every row of the event, as
  # crew_hook.py does for a payload that does not parse.
  if [ "$(printf '%s' "$input" | grep -o '"tool_name"' | wc -l | tr -d ' ')" = 1 ] \
     && [ "$(printf '%s' "$input" | tr -d '\r\n\t ' | tail -c 1)" = "}" ]; then
    tool=$(printf '%s' "$input" | tr -d '\r\n' \
           | sed -n 's/.*"tool_name"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -n 1)
  fi
  tmp=$(mktemp -d 2>/dev/null) || _fail "no temporary directory for the no-python path"
  while IFS=';' read -r script extra matcher; do
    [ -n "$script" ] || continue
    _tool_matches "$matcher" "$tool" || continue
    if [ ! -f "$DIR/$script" ]; then
      rm -rf "$tmp"
      _fail "$script is missing at $DIR/$script"
    fi
    n=$((n + 1))
    ( printf '%s' "$input" | CREW_HOOK_FLAVOUR=bash bash "$DIR/$script" $extra >"$tmp/$n.out" 2>"$tmp/$n.err"
      echo $? >"$tmp/$n.rc" ) &
  done < <(_rows_for)
  wait
  local i
  for i in $(seq 1 "$n"); do
    rc=$(cat "$tmp/$i.rc" 2>/dev/null || echo 2)
    if [ "$rc" = 2 ]; then
      blocked=1
      cat "$tmp/$i.err" >&2
    fi
  done
  if [ "$blocked" = 1 ]; then
    rm -rf "$tmp"
    exit 2
  fi
  for i in $(seq 1 "$n"); do
    cat "$tmp/$i.out"
    cat "$tmp/$i.err" >&2
  done
  rm -rf "$tmp"
  exit 0
}

exec 3<&0

# Run the dispatcher under `$1` and set STATUS. The launcher SUPERVISES it: a
# watchdog kills it 2 s AFTER the deadline, so the dispatcher's own deadline
# handling (which names the cause) wins the race; the watchdog is for a
# dispatcher that cannot run its own handling at all, and stays inside the outer
# timeout by 3 s.
_dispatch() {
  local now_s remaining
  printf -v now_s '%(%s)T' -1 2>/dev/null || now_s=$(date +%s 2>/dev/null) || now_s=0
  remaining=$(( DEADLINE_MS / 1000 - now_s ))
  [ "$remaining" -gt 0 ] || _fail "the python probe used the whole deadline"
  [ -f "$DIR/crew_hook.py" ] || _fail "crew_hook.py is missing at $DIR"
  local args=("$EVENT")
  [ "$HARNESS" = codex ] && args+=(--harness codex)
  PYTHONUTF8=1 PYTHONIOENCODING=utf-8 "$1" "$DIR/crew_hook.py" "${args[@]}" <&3 &
  local pypid=$!
  (
    sleep "$((remaining + 2))" &
    sleeper=$!
    trap 'kill "$sleeper" 2>/dev/null; exit 0' TERM
    wait "$sleeper"
    kill -KILL "$pypid" 2>/dev/null
  ) &
  local watchdog=$!
  wait "$pypid"
  STATUS=$?
  kill "$watchdog" 2>/dev/null
  wait "$watchdog" 2>/dev/null
}

# Fast path: the first python3 on PATH, run as it is. Resolving a python the
# slow, proven way (`crew_py_strict` runs a probe of its own, about 17 ms) is
# kept for when this one cannot run the dispatcher. Exit 0 and 2 are decisions.
# Exit 1, 126 and 127 mean the interpreter itself failed (a shim, a stub, a
# syntax or import error) before the dispatcher ran any hook -- crew_hook.py
# returns only 0 or 2 once it has started -- so nothing has been run twice if
# the slow resolution below tries again.
STATUS=
FAST=$(type -P python3 2>/dev/null) || FAST=""
if [ -n "$FAST" ]; then
  _dispatch "$FAST"
  case "$STATUS" in
    0|2) exit "$STATUS" ;;
    1|126|127) ;;
    *) _fail "crew_hook.py failed (exit $STATUS)" ;;
  esac
fi

# shellcheck source=_common.sh
. "$DIR/_common.sh" 2>/dev/null || _fail "_common.sh could not be loaded from $DIR"

PY=$(crew_py_strict </dev/null) || PY=""
if [ -z "$PY" ]; then
  _run_without_python
fi
_dispatch "$PY"
case "$STATUS" in
  0|2) exit "$STATUS" ;;
esac
_fail "crew_hook.py failed (exit $STATUS)"

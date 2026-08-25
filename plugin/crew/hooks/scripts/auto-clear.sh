#!/usr/bin/env bash
# EXPERIMENTAL. Sends "/clear" to the terminal that owns this session, once the
# handoff note is written.
#
# ## What this does NOT do
#
# It does not clear the conversation. A hook runs as a child process and cannot
# reset its parent's state - that part of the crew-context skill is still true,
# and nothing here contradicts it.
#
# What it does is drive the TERMINAL: it types `/clear` at the prompt the way a
# human would. That is a different mechanism with a different failure mode, and
# it is why this can work at all.
#
# ## Why that makes it experimental rather than a feature
#
# Typing into a terminal is only safe when you know which terminal, and every
# method below answers that question with a different amount of confidence:
#
#   tmux     exact. Targets $TMUX_PANE by id. No focus involved. Use this.
#   xdotool  finds a window by title and ACTIVATES it, stealing focus.
#   wtype    types into whatever has focus. Cannot verify anything.
#
# So: off by default, requires an explicit window title for anything but tmux,
# refuses outright rather than guessing, and every refusal is written to
# .crew/.autoclear.log because a Stop hook's stderr is invisible on exit 0.
#
# ## Usage
#
#   bash auto-clear.sh                 # apply the conditions, then send
#   bash auto-clear.sh --dry-run       # print the plan, send nothing
#   bash auto-clear.sh --force         # skip the handoff conditions (testing)
#
# Called from context-watch.sh on the turn after the handoff is written. Safe to
# run by hand from the repo root.
set -uo pipefail

DRY_RUN=0
FORCE=0
for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY_RUN=1 ;;
    --force)   FORCE=1 ;;
    *) echo "auto-clear: unknown argument '$arg'" >&2; exit 2 ;;
  esac
done

cd "${CLAUDE_PROJECT_DIR:-.}" 2>/dev/null || exit 0
[ -f .crew/config.json ] || exit 0

LOG=".crew/.autoclear.log"
SENT_MARKER=".crew/.autoclear-sent"

note() {  # one line to the log and to stderr; the log is the one anybody reads
  mkdir -p .crew 2>/dev/null
  printf '%s\t%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$1" >> "$LOG" 2>/dev/null
  echo "autoclear: $1" >&2
}

PY=$(command -v python3 2>/dev/null || command -v python 2>/dev/null || command -v py 2>/dev/null) || {
  note "refusing - no python to read .crew/config.json"; exit 0; }

CFG=$("$PY" - << 'PY' 2>/dev/null
import json
try:
    c = json.load(open(".crew/config.json", encoding="utf-8")).get("context", {})
except Exception:
    c = {}
a = c.get("autoClear") or {}
if not isinstance(a, dict):
    a = {}
def num(key, default):
    v = a.get(key, default)
    if isinstance(v, bool) or not isinstance(v, (int, float, str)):
        return default
    try:
        return int(v)
    except (TypeError, ValueError):
        return default
# ONE VALUE PER LINE, read below with mapfile. Not tab-separated and read with
# IFS=$'\t': tab is IFS *whitespace*, so bash collapses consecutive tabs, and an
# empty windowTitle - the default - silently shifted every later field left by
# one. Everything after it then read as garbage and the script exited without
# saying anything. mapfile -t preserves empty lines, which is the whole point.
for value in (
    "true" if a.get("enabled") is True else "false",
    str(a.get("method") or "auto"),
    str(num("delaySeconds", 3)),
    str(a.get("command") or "/clear"),
    str(a.get("windowTitle") or "").splitlines()[:1] and
    str(a.get("windowTitle") or "").splitlines()[0] or "",
    str(num("minHandoffLines", 5)),
    "true" if a.get("unsafeFocus") is True else "false",
    str(c.get("handoffPath") or ".work/HANDOFF.md"),
):
    print(value)
PY
)
[ -z "$CFG" ] && exit 0
# Strip CR before splitting. Python on Windows opens stdout in text mode and
# writes \r\n, so every value arrives with a trailing carriage return: ENABLED
# becomes "true\r", the `= "true"` test fails, and the script exits 0 having
# done nothing and said nothing. _common.sh carries crew_strip_cr for this exact
# reason; this script does not source it (it is run standalone as well as from
# the hook), so it does it inline.
CFG=$(printf '%s' "$CFG" | tr -d '\r')
mapfile -t CFG_LINES <<< "$CFG"
[ "${#CFG_LINES[@]}" -ge 8 ] || exit 0
ENABLED="${CFG_LINES[0]}"
METHOD="${CFG_LINES[1]}"
DELAY="${CFG_LINES[2]}"
COMMAND="${CFG_LINES[3]}"
WINDOW_TITLE="${CFG_LINES[4]}"
MIN_LINES="${CFG_LINES[5]}"
UNSAFE_FOCUS="${CFG_LINES[6]}"
HANDOFF="${CFG_LINES[7]}"

# Enabled is checked FIRST and silently: a repo that has not opted in must not
# even get a log file out of this.
[ "$ENABLED" = "true" ] || exit 0

if [ "$FORCE" -ne 1 ]; then
  # 1. The nag must have happened. context-watch writes this marker when it asks
  #    for the handoff, and SessionStart clears it.
  [ -f .crew/.handoff-requested ] || exit 0

  # 2. The handoff must exist, be NEWER than the request, and be more than a
  #    stub. Clearing on the strength of a three-line placeholder is how you
  #    lose a session's work and get a note that says "continue the work".
  [ -f "$HANDOFF" ] || exit 0
  [ "$HANDOFF" -nt .crew/.handoff-requested ] || exit 0
  LINES=$(grep -c '[^[:space:]]' "$HANDOFF" 2>/dev/null || echo 0)
  if [ "${LINES:-0}" -lt "$MIN_LINES" ]; then
    note "refusing - $HANDOFF has $LINES non-blank lines, minHandoffLines is $MIN_LINES"
    exit 0
  fi

  # The once-per-session claim is NOT taken here. It is taken immediately before
  # the send, after every refusal path has had its say - otherwise a
  # misconfiguration burns the session's one attempt, and correcting the config
  # mid-session appears to change nothing.
  :
fi

# --- Resolve a method ------------------------------------------------------
have() { command -v "$1" >/dev/null 2>&1; }

resolve() {
  case "$METHOD" in
    none)    echo "none";   return ;;
    tmux)    echo "tmux";   return ;;
    xdotool) echo "xdotool"; return ;;
    wtype)   echo "wtype";  return ;;
    auto) ;;
    *) echo "unknown"; return ;;
  esac
  # auto: most confident first. tmux targets a pane by id and never touches
  # focus, so it is the only one that is simply correct.
  if [ -n "${TMUX:-}" ] && have tmux; then echo "tmux"; return; fi
  if [ -n "${DISPLAY:-}" ] && have xdotool; then echo "xdotool"; return; fi
  if [ -n "${WAYLAND_DISPLAY:-}" ] && have wtype; then echo "wtype"; return; fi
  echo "none"
}
RESOLVED=$(resolve)

case "$RESOLVED" in
  unknown)
    note "refusing - unknown method '$METHOD' (tmux, xdotool, wtype, none, auto)"; exit 0 ;;
  none)
    note "refusing - no usable method. Inside tmux this works with no configuration; otherwise install xdotool (X11) or wtype (Wayland) and set context.autoClear.windowTitle"
    exit 0 ;;
  tmux)
    if [ -z "${TMUX:-}" ]; then note "refusing - method tmux but \$TMUX is unset, so this session is not in a tmux pane"; exit 0; fi
    have tmux || { note "refusing - method tmux but tmux is not on PATH"; exit 0; }
    TARGET="${TMUX_PANE:-}"
    [ -n "$TARGET" ] || { note "refusing - \$TMUX_PANE is unset, so there is no pane to target"; exit 0; }
    ;;
  xdotool|wtype)
    # Neither can prove it is typing into Claude Code. A title is the user
    # saying "I accept that risk, and here is how to recognise the window".
    if [ -z "$WINDOW_TITLE" ]; then
      note "refusing - method $RESOLVED cannot verify what it types into. Set context.autoClear.windowTitle to the terminal's title so this is deliberate"
      exit 0
    fi
    have "$RESOLVED" || { note "refusing - method $RESOLVED but $RESOLVED is not on PATH"; exit 0; }
    if [ "$RESOLVED" = "wtype" ] && [ "$UNSAFE_FOCUS" != "true" ]; then
      note "refusing - wtype types into whatever currently has focus and Wayland offers no way to check. Set context.autoClear.unsafeFocus to true if you accept that"
      exit 0
    fi
    TARGET="${WINDOW_TITLE}"
    ;;
esac

if [ "$DRY_RUN" -eq 1 ]; then
  # Deterministic, and the same shape the .ps1 prints. The test suite reads this.
  printf 'autoclear: would send\n  method: %s\n  target: %s\n  command: %s\n  delay: %ss\n' \
    "$RESOLVED" "${TARGET:-}" "$COMMAND" "$DELAY"
  exit 0
fi

# --- Send, after the turn has actually ended -------------------------------
#
# The delay and the detach are both load-bearing. This runs from a Stop hook,
# and the prompt does not exist yet: Claude Code is still finishing the turn.
# Sending now types into nothing. So the work is handed to a detached child that
# sleeps first, and THIS process exits 0 immediately so the turn can end.
#
# setsid/nohup because a hook's children are not guaranteed to outlive it.

# Claim the one-per-session attempt HERE, not with the conditions above: every
# refusal path has now had its say, so a misconfiguration no longer burns the
# session's only attempt and correcting the config mid-session actually retries.
# Atomic because both hook flavours run on the same Stop on Windows, and two
# /clear keystrokes means the second lands in the fresh session.
if [ "$FORCE" -ne 1 ]; then
  ( set -o noclobber; : > "$SENT_MARKER" ) 2>/dev/null || exit 0
fi

send_script=$(mktemp) || { note "refusing - could not create the sender script"; exit 0; }
{
  echo '#!/usr/bin/env bash'
  echo "sleep $DELAY"
  case "$RESOLVED" in
    tmux)
      # -l sends the string literally, so a command containing ; or " is safe.
      printf 'tmux send-keys -t %q -l %q\n' "$TARGET" "$COMMAND"
      printf 'tmux send-keys -t %q Enter\n' "$TARGET"
      ;;
    xdotool)
      printf 'id=$(xdotool search --name %q | head -n 1)\n' "$TARGET"
      echo '[ -n "$id" ] || exit 0'
      echo 'xdotool windowactivate --sync "$id"'
      printf 'xdotool type --clearmodifiers --delay 20 -- %q\n' "$COMMAND"
      echo 'xdotool key --clearmodifiers Return'
      ;;
    wtype)
      printf 'wtype -- %q\n' "$COMMAND"
      echo 'wtype -k Return'
      ;;
  esac
  printf 'rm -f -- %q\n' "$send_script"
} > "$send_script"
chmod +x "$send_script" 2>/dev/null

if command -v setsid >/dev/null 2>&1; then
  setsid bash "$send_script" >/dev/null 2>&1 &
else
  nohup bash "$send_script" >/dev/null 2>&1 &
fi
disown 2>/dev/null || true

note "sent - method $RESOLVED, target ${TARGET:-}, command '$COMMAND' in ${DELAY}s"
exit 0

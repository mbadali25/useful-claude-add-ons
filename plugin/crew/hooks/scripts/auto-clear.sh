#!/usr/bin/env bash
# Sends "/clear" to the terminal that owns this session, once this session's
# handoff note is written and verified. Opt-in per machine; off by default.
#
# ## What this does NOT do
#
# It does not clear the conversation. A hook runs as a child process and cannot
# reset its parent's state - that part of the crew-context skill is still true,
# and nothing here contradicts it.
#
# What it does is drive the TERMINAL: it types `/clear` at the prompt the way a
# human would. That is a different mechanism with a different failure mode, and
# it is why this can work at all -- except for method `notify`, which types
# nothing: it prints a systemMessage saying the handoff is written and it is
# safe to run the command yourself. `auto` resolves to `notify` on native
# Windows with no tmux pane (an owner decision, not a capability gap -- typing
# into a window this hook found itself is a risk `auto` does not get to accept
# on your behalf), and `notify` can also be requested by name on any platform.
#
# ## What has to be true before it types anything
#
# The decisions live in crew_autocycle.py (the .ps1 twin carries the same
# rules natively), and every one of them is a refusal:
#
#   - the MACHINE opted in: context.autoClear.enabled is true in
#     ~/.claude/crew/config.json. A repo may switch it off, never on.
#   - this session asked for a wrap-up (.crew/.handoff-requested-<session>),
#     and the context reading behind that request was trustworthy -- an
#     estimate, an unknown window, a pre-compaction reading or an empty marker
#     never clears.
#   - the handoff was written after that request, is not a stub, and is not
#     PreCompact's automatic skeleton.
#   - the target is uniquely identified: a tmux pane whose pid is an ancestor
#     of this hook, or exactly one X11 window owned by an ancestor (a
#     windowTitle is a fallback that refuses on zero or several matches).
#     wtype cannot identify anything and is refused.
#
# Every refusal is written to .crew/.autoclear.log, because a Stop hook's
# stderr is invisible on exit 0.
#
# ## Usage
#
#   bash auto-clear.sh --session ID            # apply the conditions, then send
#   bash auto-clear.sh --session ID --dry-run  # print the plan, send nothing
#   bash auto-clear.sh --force                 # skip the handoff conditions (testing)
#
# Called from context-watch.sh with this session's id and root.
set -uo pipefail

DRY_RUN=0
FORCE=0
SESSION=""
ROOT="${CLAUDE_PROJECT_DIR:-.}"
while [ $# -gt 0 ]; do
  case "$1" in
    --dry-run) DRY_RUN=1 ;;
    --force)   FORCE=1 ;;
    --session) shift; SESSION="${1:-}" ;;
    --root)    shift; ROOT="${1:-.}" ;;
    *) echo "auto-clear: unknown argument '$1'" >&2; exit 2 ;;
  esac
  shift
done

cd "$ROOT" 2>/dev/null || exit 0

# Gated on the `.crew/` DIRECTORY, not on `.crew/config.json`. OWNER DECISION
# (crew 1.0 F4, reversing the previous file-based gate -- see CONFIG.md sec
# 14): `context.autoClear` is a MACHINE-global switch (`crew_config.py`), so
# it must work in any crew repo without a per-repo config of its own -- and
# "crew repo" is read the same way both senders now agree: `.crew/` exists.
# `context-watch.sh`/`.ps1` gate their OWN handover to this script the same
# way, while their OWN context-window warnings keep requiring a real
# `.crew/config.json` underneath -- that is a separate question, unaffected
# here. A repo with NO `.crew/` at all -- a fresh checkout, since the
# directory itself is git-ignored in this very repo -- must stay completely
# silent and must NEVER get `.crew/` or `.crew/.autoclear.log` created as a
# side effect of this hook running, so this check runs before note() ever
# gets a chance to write anything.
[ -d .crew ] || exit 0
LOG=".crew/.autoclear.log"

note() {  # one line to the log and to stderr; the log is the one anybody reads
  # `.crew/` is guaranteed to exist by the gate above, which runs before this
  # function is ever called -- no mkdir needed, and none may run here: a
  # repo with no `.crew/` must never get one created as a side effect.
  printf '%s\t%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$1" >> "$LOG" 2>/dev/null
  echo "autoclear: $1" >&2
}

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
. "$DIR/_common.sh"
# Strict: the Windows Store stub prints nothing, which would read as "off".
# No python means nothing was checked, and nothing checked never clears.
PY=$(crew_py_strict)
[ -n "$PY" ] || exit 0

FORCE_ARG=()
[ "$FORCE" -eq 1 ] && FORCE_ARG=(--force)
# One value per line, read with mapfile: an empty field must stay a line (tab
# is IFS whitespace, and a tab-separated read once shifted every field after
# an empty windowTitle). CR stripped first -- python on Windows writes \r\n.
PLAN=$("$PY" "$DIR/crew_autocycle.py" plan --root "$PWD" --session "$SESSION" "${FORCE_ARG[@]}" 2>/dev/null | tr -d '\r')
mapfile -t P <<< "$PLAN"
if [ "${#P[@]}" -lt 8 ]; then
  note "refusing - could not read the plan from crew_autocycle.py"
  exit 0
fi
STATUS="${P[0]}"; REASON="${P[1]}"; RESOLVED="${P[2]}"; TARGET="${P[3]}"
LABEL="${P[4]}"; COMMAND="${P[5]}"; DELAY="${P[6]}"; KEY="${P[7]}"
SENT_MARKER=".crew/.autoclear-sent-${KEY}"

# Off is silent: a machine that has not opted in must not even get a log file.
[ "$STATUS" = "off" ] && exit 0
if [ "$STATUS" != "send" ]; then
  note "refusing - $REASON"
  exit 0
fi

if [ "$DRY_RUN" -eq 1 ]; then
  # Deterministic, and the same shape the .ps1 prints. The test suite reads this.
  # `notify` types nothing, so there is no delay to report -- printing the
  # configured number there (crew_autocycle.plan zeroes it, which is right for
  # ITS purpose but wrong to echo as if it were a real wait) would contradict
  # context.autoClear.delaySeconds in .crew/config.json for no reason a reader
  # could infer from the number alone. Decided by RESOLVED, the method that
  # actually ran, never by the numeric value of $DELAY itself: a keystroke
  # method configured with delaySeconds: 0 is a real (if instant) wait, not "no
  # delay applies here".
  DELAY_LINE="delay: ${DELAY}s"
  [ "$RESOLVED" = "notify" ] && DELAY_LINE="delay: n/a (notify sends no keystroke)"
  printf 'autoclear: would send\n  method: %s\n  target: %s\n  command: %s\n  %s\n' \
    "$RESOLVED" "$LABEL" "$COMMAND" "$DELAY_LINE"
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
# /clear keystrokes means the second lands in the fresh session. Keyed on the
# session, like the wrap-up marker, so one terminal's clear never uses up
# another's.
if [ "$FORCE" -ne 1 ]; then
  ( set -o noclobber; : > "$SENT_MARKER" ) 2>/dev/null || exit 0
fi

# `notify` types nothing anywhere, so none of the safety rules below apply to
# it -- there is no keyboard to keep a test suite off of, and no turn-ending
# race to wait out with a delay. Printed and logged synchronously, from THIS
# process, never a detached child. Never claims the handoff was cleared or
# compacted: only that it is safe to run the configured command yourself.
if [ "$RESOLVED" = "notify" ]; then
  MSG="crew: handoff written and verified for this session - it is safe to run ${COMMAND} now (auto-clear will not type it for you)."
  "$PY" -c 'import json,sys; print(json.dumps({"systemMessage": sys.argv[1]}))' "$MSG" 2>/dev/null
  note "sent - method notify, command '$COMMAND'"
  exit 0
fi

# A test suite must never drive the real keyboard. Checked HERE, immediately
# before the sender is built, and NOT earlier: every decision above is
# something the suite legitimately exercises, and an early exit made 20 cases
# assert the inhibit message instead of the refusal they were written for.
# Only the keystroke is suppressed. See the .ps1 twin.
if [ -n "${CREW_AUTOCLEAR_INHIBIT:-}" ]; then
  note "would have sent, but CREW_AUTOCLEAR_INHIBIT is set"
  exit 0
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
      # The window id resolved above, never a fresh title search: a search
      # here is exactly the "first of several matches" guess this refuses.
      # Re-checked after activation, so a window that vanished or would not
      # take focus gets nothing typed into whatever is in front instead.
      printf 'xdotool windowactivate --sync %q\n' "$TARGET"
      printf '[ "$(xdotool getactivewindow)" = %q ] || exit 0\n' "$TARGET"
      printf 'xdotool type --clearmodifiers --delay 20 -- %q\n' "$COMMAND"
      echo 'xdotool key --clearmodifiers Return'
      ;;
  esac
  printf 'rm -f -- %q\n' "$send_script"
} > "$send_script"
chmod +x "$send_script" 2>/dev/null

# `3>&-`: when context-watch.sh invoked this script, it dup'd its OWN stdout
# onto fd 3 first so this script's real stdout (fd 1) could be temporarily
# aimed at a capture pipe and handed back afterward -- see
# context-watch.sh:~120's `cw_run_auto_clear`. `>/dev/null 2>&1` only
# redirects fd 0/1/2 for this detached child; fd 3 is inherited unchanged
# from THIS process and stays open in the grandchild long after
# context-watch.sh has closed its own copy and exited, because closing a
# fd in a parent never closes the duplicate a forked child already holds.
# A long delaySeconds then held context-watch.sh's stdout pipe open for
# that whole wait, which is what let a slow /clear hit the hook's own 20s
# timeout even though context-watch.sh itself had long since finished.
# Closed here, explicitly, for the one process that must not inherit it.
if command -v setsid >/dev/null 2>&1; then
  setsid bash "$send_script" 3>&- >/dev/null 2>&1 &
else
  nohup bash "$send_script" 3>&- >/dev/null 2>&1 &
fi
disown 2>/dev/null || true

note "sent - method $RESOLVED, target $LABEL, command '$COMMAND' in ${DELAY}s"
exit 0

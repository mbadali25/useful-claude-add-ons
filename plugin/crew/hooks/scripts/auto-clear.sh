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
# it is why this can work at all.
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

# NOT a `[ -f .crew/config.json ] || exit 0` guard -- that used to sit here and
# stood this whole script down, silently, before note() even exists to be
# called, on the ONE thing that matters most to prove: a fresh checkout has no
# repo config at all (.crew/config.json is git-ignored in this very repo), and
# "only the machine may opt in" (test_only_the_machine_can_opt_in_and_a_repo_
# can_only_opt_out) already means a repo need not have ANY config to be armed
# by the machine's global enabled:true. crew_autocycle._load() already returns
# {} for a missing file -- the same value a present-but-empty repo config
# produces -- so settings()/plan() already treat "absent" and "empty" alike;
# only the guard that used to sit here treated them differently.
LOG=".crew/.autoclear.log"

note() {  # one line to the log and to stderr; the log is the one anybody reads
  mkdir -p .crew 2>/dev/null
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
  printf 'autoclear: would send\n  method: %s\n  target: %s\n  command: %s\n  delay: %ss\n' \
    "$RESOLVED" "$LABEL" "$COMMAND" "$DELAY"
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

if command -v setsid >/dev/null 2>&1; then
  setsid bash "$send_script" >/dev/null 2>&1 &
else
  nohup bash "$send_script" >/dev/null 2>&1 &
fi
disown 2>/dev/null || true

note "sent - method $RESOLVED, target $LABEL, command '$COMMAND' in ${DELAY}s"
exit 0

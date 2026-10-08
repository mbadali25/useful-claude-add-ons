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
#   - with context.autoClear.wrapUp armed (T-0017), the wrap-up's results
#     are on disk: the handoff's head: is HEAD, its branch: is the checkout,
#     no tracked file is modified, and its resume: line parses (or is
#     `resume: none`). This refusal is also printed as a systemMessage.
#   - this session is bound to its OWN process (T-0016): the nearest ancestor
#     named by a Claude Code session record (${CLAUDE_CONFIG_DIR:-~/.claude}/
#     sessions/<pid>.json) with this session's id and that process's start
#     time. A headless session (an sdk* entrypoint such as `claude -p`, or no
#     controlling terminal) types nothing: it gets one notice naming its
#     handoff and saying the process that started it must restart it. A
#     session that cannot be identified, or whose entrypoint nobody measured,
#     types nothing either; `auto` falls back to plain notify.
#   - the target is uniquely identified FROM THAT PROCESS: a tmux pane whose
#     pid is the session's process or an ancestor of it, or exactly one X11
#     window owned by an ancestor and hosting no other terminal (a
#     windowTitle is a fallback that refuses on zero or several matches, and
#     whenever another session is live). The walk refuses when it passes
#     through another Claude Code session. wtype cannot identify anything and
#     is refused.
#
# Every refusal is written to .crew/.autoclear.log, because a Stop hook's
# stderr is invisible on exit 0.
#
# ## Usage
#
#   bash auto-clear.sh --session ID            # apply the conditions, then send
#   bash auto-clear.sh --session ID --dry-run  # print the plan, send nothing
#   bash auto-clear.sh --force                 # skip the handoff conditions (testing)
#   bash auto-clear.sh --resume --session ID --source clear|compact [--dry-run]
#
# --force skips the handoff conditions AND the T-0017 wrap-up check. It is for
# testing by hand only: hooks.json and context-watch never pass it, and no
# repo or machine config key can turn it on.
#
# Called from context-watch.sh with this session's id and root. `--resume`
# (T-0013) is called from the context hook on SessionStart: see the resume
# block below, which exits before the /clear path is reached.
set -uo pipefail

DRY_RUN=0
FORCE=0
RESUME=0
SOURCE=""
SESSION=""
ROOT="${CLAUDE_PROJECT_DIR:-.}"
while [ $# -gt 0 ]; do
  case "$1" in
    --dry-run) DRY_RUN=1 ;;
    --force)   FORCE=1 ;;
    --resume)  RESUME=1 ;;
    --source)  shift; SOURCE="${1:-}" ;;
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

# --- Resume mode (T-0013) ----------------------------------------------------
#
# Types T-0006's rendered resume prompt into this session's own tmux pane
# after SessionStart(clear|compact). Started by the context hook, which reads
# the one `autoresume:` line this block prints on stdout and names it in the
# session's context. Self-contained: it exits before the /clear path below.
# Consent is `resume.auto` (crew_resume.settings), not autoClear.enabled;
# every decision is crew_autocycle.resume_plan's, and every refusal is
# logged. Order: plan -> claim the per-handoff marker LAST (after every
# refusal) -> record the run (a run the loop guard cannot see is never
# typed) -> detached sender: delay -> ready probe -> inhibit -> send-keys.
if [ "$RESUME" -eq 1 ]; then
  say() { printf 'autoresume: %s\n' "$1"; }
  refuse() { note "refusing - auto-resume: $1"; say "refused - $1"; exit 0; }
  PLAN=$("$PY" "$DIR/crew_autocycle.py" resume-plan --root "$PWD" --session "$SESSION" --source "$SOURCE" 2>/dev/null | tr -d '\r')
  mapfile -t P <<< "$PLAN"
  [ "${#P[@]}" -ge 12 ] || refuse "could not read the resume plan from crew_autocycle.py"
  STATUS="${P[0]}"; REASON="${P[1]}"; RESOLVED="${P[2]}"; TARGET="${P[3]}"
  LABEL="${P[4]}"; COMMAND="${P[5]}"; DELAY="${P[6]}"; TIMEOUT="${P[8]}"
  MARKER="${P[9]}"; DECISION="${P[10]}"
  # Off is silent, as for /clear: resume.auto is not on, or this session is
  # outside the machine's onlyRepos/onlySessions narrowing.
  [ "$STATUS" = "off" ] && exit 0
  [ "$STATUS" = "send" ] || refuse "$REASON"
  if [ "$DRY_RUN" -eq 1 ]; then
    if [ "$RESOLVED" = "notify" ]; then
      printf 'autoresume: would send\n  method: notify\n  command: %s\n  delay: n/a (notify types nothing)\n' "$COMMAND"
    else
      printf 'autoresume: would send\n  method: %s\n  target: %s\n  command: %s\n  delay: %ss\n  ready timeout: %ss\n' \
        "$RESOLVED" "$LABEL" "$COMMAND" "$DELAY" "$TIMEOUT"
    fi
    exit 0
  fi
  # notify types nothing, so it neither claims the handoff nor records a run:
  # the human starts the command, and decide still sees the note as unused.
  if [ "$RESOLVED" = "notify" ]; then
    note "auto-resume: method notify - run $COMMAND yourself (nothing typed)"
    say "notify - run $COMMAND yourself"
    exit 0
  fi
  [ "$RESOLVED" = "tmux" ] || refuse "method $RESOLVED cannot type a resume"
  mkdir -p "$(dirname "$MARKER")" 2>/dev/null
  ( set -o noclobber; : > "$MARKER" ) 2>/dev/null || refuse "this handoff was already typed once (marker $(basename "$MARKER") exists)"
  RECORD=$(printf '%s' "$DECISION" | "$PY" "$DIR/crew_resume.py" record --root "$PWD" --decision-json - 2>/dev/null | tr -d '\r')
  RECORDED=$("$PY" -c 'import json,sys
try:
    d = json.loads(sys.argv[1])
except ValueError:
    d = {}
print("ok" if isinstance(d, dict) and d.get("ok") is True else (isinstance(d, dict) and d.get("reason") or "no answer"))' "$RECORD" 2>/dev/null)
  [ "$RECORDED" = "ok" ] || refuse "could not record the run (${RECORDED:-no answer from crew_resume.py}) - nothing typed"
  send_script=$(mktemp) || refuse "could not create the sender script"
  {
    echo '#!/usr/bin/env bash'
    printf 'trap %q EXIT\n' "rm -f -- $(printf '%q' "$send_script")"
    printf 'LOG=%q; PY=%q; AC=%q; PANE=%q; TEXT=%q; TIMEOUT=%q\n' \
      "$PWD/$LOG" "$PY" "$DIR/crew_autocycle.py" "$TARGET" "$COMMAND" "$TIMEOUT"
    cat <<'SENDER'
note() { printf '%s\t%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "auto-resume: $1" >> "$LOG" 2>/dev/null; }
probe() { tmux capture-pane -p -e -t "$PANE" 2>/dev/null | "$PY" "$AC" probe 2>/dev/null | tr -d '\r'; }
SENDER
    printf 'sleep %q\n' "$DELAY"
    cat <<'SENDER'
# The ready gate. The spike (Claude Code 2.1.282) measured the input ready by
# 0.134 s, but on /compact it looks empty while SessionStart hooks still run,
# so ready also means no `esc to interrupt`. A non-empty line is a human
# typing: refuse at once. Anything else waits, up to TIMEOUT, then refuses.
deadline=$(( $(date +%s) + TIMEOUT ))
state=$(probe)
while [ "$state" != "ready" ]; do
  if [ "$state" = "nonempty" ]; then
    note "refusing - the input line of $PANE is not empty, so nothing was typed - run $TEXT yourself"
    exit 0
  fi
  if [ "$(date +%s)" -ge "$deadline" ]; then
    note "refusing - the input line of $PANE did not become ready within ${TIMEOUT}s (last probe: ${state:-no answer}), so nothing was typed - run $TEXT yourself"
    exit 0
  fi
  sleep 0.25
  state=$(probe)
done
# A test suite must never drive the real keyboard: checked after the probe,
# immediately before the keystroke, so the suite exercises every gate above.
if [ -n "${CREW_AUTOCLEAR_INHIBIT:-}" ]; then
  note "would have typed '$TEXT' into $PANE, but CREW_AUTOCLEAR_INHIBIT is set"
  exit 0
fi
# Text and Enter half a second apart: arriving in one read, a text over ~60
# characters plus its Enter is taken as a paste and the Enter becomes a
# newline (T-0013 spike; 0.3 s measured enough).
tmux send-keys -t "$PANE" -l "$TEXT"
sleep 0.5
tmux send-keys -t "$PANE" Enter
sleep 1
case "$(probe)" in
  ready|busy) note "typed '$TEXT' into $PANE" ;;
  *) note "typed '$TEXT' into $PANE but could not confirm it was submitted - check the input line and press Enter if it was not" ;;
esac
SENDER
  } > "$send_script"
  chmod +x "$send_script" 2>/dev/null
  # Detached, fd 3 closed and stdout/stderr dropped: the context hook waits
  # for THIS process only, and must not wait for the delay or the probe.
  if command -v setsid >/dev/null 2>&1; then
    setsid bash "$send_script" 3>&- >/dev/null 2>&1 < /dev/null &
  else
    nohup bash "$send_script" 3>&- >/dev/null 2>&1 < /dev/null &
  fi
  disown 2>/dev/null || true
  note "auto-resume: sent - method tmux, target $LABEL, command '$COMMAND' after ${DELAY}s and the ready probe (up to ${TIMEOUT}s)"
  say "typing $COMMAND in ${DELAY}s (method tmux)"
  exit 0
fi

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
  # T-0017: a wrap-up refusal is also SHOWN, on stdout, which context-watch
  # forwards: an armed session that is not cleared says why.
  case "$REASON" in
    "wrap-up: "*)
      "$PY" -c 'import json,sys; print(json.dumps({"systemMessage": "crew wrap-up: not clearing - " + sys.argv[1]}))' \
        "${REASON#wrap-up: }" 2>/dev/null ;;
  esac
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
  if [ "$RESOLVED" = "notify-headless" ]; then
    # T-0016: the notice travels in the plan's reason field.
    printf 'autoclear: would send\n  method: notify-headless\n  command: %s\n  delay: n/a (nothing is typed)\n  message: %s\n' \
      "$COMMAND" "$REASON"
    exit 0
  fi
  # PARITY: `notify` identifies no window, so LABEL is empty -- printing an
  # empty `target: ` line there said nothing a reader could use, and
  # auto-clear.ps1's own notify dry-run never prints one at all. Matched here
  # by omitting the line, rather than adding an empty one to the .ps1 twin.
  if [ -n "$LABEL" ]; then
    printf 'autoclear: would send\n  method: %s\n  target: %s\n  command: %s\n  %s\n' \
      "$RESOLVED" "$LABEL" "$COMMAND" "$DELAY_LINE"
  else
    printf 'autoclear: would send\n  method: %s\n  command: %s\n  %s\n' \
      "$RESOLVED" "$COMMAND" "$DELAY_LINE"
  fi
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
# T-0016: a headless session (no terminal of its own) gets its notice once,
# claimed like notify. Logged in full as well: a `claude -p` parent may never
# show the systemMessage, so the log is the durable copy.
if [ "$RESOLVED" = "notify-headless" ]; then
  "$PY" -c 'import json,sys; print(json.dumps({"systemMessage": sys.argv[1]}))' "$REASON" 2>/dev/null
  note "sent - method notify-headless: $REASON"
  exit 0
fi
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
#
# CREW_AUTOCLEAR_INHIBIT=spawn goes one step further and still builds and
# spawns the detached sender, which stops after its sleep, before any
# keystroke (the guard it carries below). The suite needs that for the
# spawn itself (fd 3, the sleep argument, the process-group reap), and the
# process/window stubs are honoured only while the inhibit is set, so this
# keeps "a stub never steers a keystroke" true for those cases too.
if [ -n "${CREW_AUTOCLEAR_INHIBIT:-}" ] && [ "${CREW_AUTOCLEAR_INHIBIT}" != "spawn" ]; then
  note "would have sent, but CREW_AUTOCLEAR_INHIBIT is set"
  exit 0
fi

send_script=$(mktemp) || { note "refusing - could not create the sender script"; exit 0; }
{
  echo '#!/usr/bin/env bash'
  # T-0065: the sender unlinks itself FIRST. bash keeps an open script
  # readable after unlink on POSIX, so a sender killed during its sleep
  # (even by SIGKILL) leaves nothing in $TMPDIR. The last-line rm below
  # stays as the fallback where an open file cannot be unlinked (Git Bash
  # on Windows); a second rm -f of a gone file is harmless.
  printf 'rm -f -- %q\n' "$send_script"
  echo "sleep $DELAY"
  printf '[ -n "${CREW_AUTOCLEAR_INHIBIT:-}" ] && { rm -f -- %q; exit 0; }\n' "$send_script"
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

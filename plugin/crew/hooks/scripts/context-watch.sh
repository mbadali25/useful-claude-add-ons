#!/usr/bin/env bash
# The script's directory without a subshell or `dirname` when the path is absolute
# (the dispatcher starts every hook by its full path): on Git Bash each fork is an
# MSYS process start (0.3-0.5s measured on the Windows host), and this hook's 20s
# budget is shared with every other Stop hook. A relative path falls back to `cd`.
case "${BASH_SOURCE[0]}" in
  /*|[A-Za-z]:/*) DIR=${BASH_SOURCE[0]%/*} ;;
  *) DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)" ;;
esac
. "$DIR/_common.sh"
# Stop hook. Reads how full the context window actually is and, once past the
# threshold, asks Claude to write a handoff note before ending the turn.
# Exit 2 sends control back to the model with the reason on stderr.
#
# NOTHING HERE RUNS until a repository at least has a `.crew/` directory -
# crew is per-repository and its hooks are inert until something (`/crew:init`
# or a worktree copy) has made that much true. That is deliberate (a gate that
# fires in every repo you open would be hostile), but it does mean installing
# the plugin is not enough on its own.
#
# Two gates below, not one, since crew 1.0 F4: this hook's own handover to
# auto-clear.sh (the forced-continuation branch, just past the `.crew/`
# check) reaches it on `.crew/` existing alone, matching auto-clear.sh's own
# directory gate - `context.autoClear` is a machine-global switch and must
# work in any crew repo (docs/crew/config-rationale.md). This hook's OWN context-window
# measurement and nagging, further down, is a separate question and keeps
# requiring a real `.crew/config.json` underneath, unchanged.
# Builtin read, not `$(cat)`: no subshell and no cat on a Git Bash fork budget.
IFS= read -r -d '' INPUT || true

# Loop safety, layer 1, checked FIRST -- before the config check, before
# python, before anything. Merged-branch review, 2026-09-22: the old
# ordering ran the no-python fail-closed branch (below) BEFORE this check,
# so a forced-continuation retry (stop_hook_active:true) could still hit the
# interpreter-failure branch and claim $MARKER with nothing measured. On
# Windows, where both hook flavours run, context-watch.ps1 (pure PowerShell,
# no python, so it never hits this failure mode itself) then saw that
# marker, stood down for the rest of the session, and auto-clear.ps1 could
# /clear once the model wrote the handoff the false alarm asked for -- a
# session cleared at LOW context, the opposite of what this hook exists to
# prevent. Same idiom verify-gate.sh:48 uses for the same reason, deliberately
# NOT a python-based read: it must work even when the interpreter that would
# parse the JSON properly is the very thing that is broken.
#
# stop_hook_active is also the ONE turn on which auto-clear matters: the block
# below sends Claude back to write the handoff, and the Stop that follows that
# forced continuation is the first moment the note exists. This hook used to
# exit here unconditionally, so auto-clear only ran on the NEXT user turn's
# Stop -- a cleared session needed the user to type something first, which is
# most of why the cycle "worked when it worked". So this turn hands over to
# auto-clear.sh (never blocks, never asks again) when THIS session has a
# wrap-up marker, and does nothing else.
STOP_ACTIVE=0
case "$INPUT" in *'"stop_hook_active": true'*|*'"stop_hook_active":true'*) STOP_ACTIVE=1 ;; esac

# The session this Stop belongs to. Every marker is keyed on it: the wrap-up
# marker used to be one `.crew/.handoff-requested` per REPOSITORY, so two
# terminals in one repo shared it -- the first to cross the threshold silenced
# the other, and either one's SessionStart re-armed both. Same cheap
# extraction as cwd below, for the same reason; the key keeps only
# [A-Za-z0-9_-], matching crew_autocycle.session_key and the .ps1 twins.
# Pure bash on purpose: nothing beyond grep/sed/awk may be needed before
# python is resolved (test_context_watch_python_resolver's coreutils-only PATH).
session_markers() {
  local key="${1//[^A-Za-z0-9_-]/_}"
  key="${key:0:100}"
  SESSION_KEY="${key:-nosession}"
  MARKER=".crew/.handoff-requested-${SESSION_KEY}"
  SENT_MARKER=".crew/.autoclear-sent-${SESSION_KEY}"
  ESCALATED=".crew/.wrapup-escalated-${SESSION_KEY}"  # T-0017
}
SESSION_ID=""
SESSION_RE='"session_id"[[:space:]]*:[[:space:]]*"([^"]*)"'
if [[ "$INPUT" =~ $SESSION_RE ]]; then
  SESSION_ID="${BASH_REMATCH[1]}"
fi
session_markers "$SESSION_ID"

# auto-clear.sh logs its own refusals/sends to .crew/.autoclear.log (see its
# own `note()`) and echoes the same line to ITS stderr -- but only on paths
# that reach that function. A crash before that point (an unbound variable,
# a missing interpreter that is not the *documented* no-python stand-down,
# anything that dies before `note` ever runs) used to vanish completely: both
# call sites below discarded the child's stderr and never looked at its exit
# code, so nothing anywhere recorded that auto-clear was even asked to run.
# `.crew/.autoclear.log` was reported to exist nowhere on the affected Windows
# host, which is what a total silence there looks like.
#
# This wraps every call instead: capture the child's exit code and stderr,
# and independently append a line to the SAME log whenever the child looks
# unhealthy, so this hook's own record of the attempt survives however badly
# the child behaved. Deliberately unconditional rather than trying to detect
# whether auto-clear ALREADY logged the same thing -- that would mean parsing
# its own log, which is exactly the kind of cleverness that breaks first. A
# duplicate line on an ordinary refusal costs nothing a human reading the log
# would notice; a MISSING line is the whole defect this exists to close.
#
# Must never throw and must never change this hook's own exit code or leak
# anything unexpected onto ITS OWN stdout, which Claude Code reads as the Stop
# hook's protocol -- the fallback, if the log itself cannot be written (an
# unwritable .crew/), is this hook's own stderr, never stdout.
cw_log_autoclear_trouble() {
  local msg
  msg=$(printf '%s' "$1" | tr '\n\r\t' '   ')
  if mkdir -p .crew 2>/dev/null &&
     printf '%s\t%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$msg" >> .crew/.autoclear.log 2>/dev/null
  then
    return 0
  fi
  echo "context-watch: $msg" >&2
}

cw_run_auto_clear() {
  local err rc
  # Stdout is forwarded, not discarded: `method notify` (and a `sendkeys`
  # decline that falls back to it) is the ONE real, non-dry-run path that
  # writes anything there -- a single line of JSON, `{"systemMessage": ...}`
  # -- and this hook never writes to its OWN stdout on any other path, so
  # there is nothing here for it to collide with. Every other auto-clear
  # path (a refusal, a tmux/xdotool/sendkeys send) still writes nothing to
  # stdout, exactly as before; only `notify`'s message is new here.
  #
  # Review (Codex FIX|context-watch.sh:~103): this used to capture stdout
  # through a `mktemp` file and, ONLY when mktemp failed, redirect that same
  # stdout to /dev/null -- silently dropping the notify JSON on the one path
  # where mktemp is unavailable. That was also unrecoverable: auto-clear.sh
  # had already claimed the one-per-session SENT_MARKER inside that same
  # call, so a retry would find its attempt already spent and refuse before
  # printing anything again. The fix removes the mktemp dependency (and
  # therefore its failure mode) entirely: fd 3 holds this hook's own real
  # stdout before auto-clear.sh's fd 1 is temporarily aimed at fd 2's
  # capture pipe by `2>&1`, then handed back to fd 1 by `1>&3` -- so
  # auto-clear.sh's stdout streams straight through to wherever THIS
  # process's stdout already goes (unconditionally, not behind a
  # mktemp-shaped maybe), and only its stderr lands in $err.
  exec 3>&1
  err=$(bash "$(dirname "${BASH_SOURCE[0]}")/auto-clear.sh" --root "$PWD" --session "$SESSION_ID" 2>&1 1>&3)
  rc=$?
  exec 3>&-
  if [ "$rc" -ne 0 ] || [ -n "$err" ]; then
    cw_log_autoclear_trouble "auto-clear exited $rc${err:+ - stderr: $err}"
  fi
}

# `.crew/`'s existence decides whether this hook does ANYTHING at all, so it
# is checked BEFORE resolving python, not after -- a non-crew repository must
# not pay for spinning up an interpreter (or, before the WindowsApps fix
# below, for launching a stub) to run a hook that was always going to exit 0.
#
# The JSON payload's own "cwd" -- NOT $CLAUDE_PROJECT_DIR -- is still the
# PRIMARY source, restoring the priority order this hook always used: a crew
# repo nested under the project root (input cwd=outer/inner,
# CLAUDE_PROJECT_DIR=outer) must be checked and nagged at outer/inner, not
# silently missed by looking only at outer. Extracted here with a bash-only
# grep/sed rather than python, because python is not resolved yet and must
# not be a prerequisite for finding out whether this is even a crew repo.
# This is an approximation of real JSON parsing -- an escaped `\"` or a
# backslash inside the path is not unescaped correctly -- matching the same
# cheap-extraction convention verify-gate.sh already uses for booleans
# (`case "$INPUT" in *'"stop_hook_active": true'*...`): accurate enough for
# what Claude Code actually sends, and python is not guaranteed available to
# do better at this point in the script.
CWD_RAW=""
CWD_RE='"cwd"[[:space:]]*:[[:space:]]*"([^"]*)"'
[[ "$INPUT" =~ $CWD_RE ]] && CWD_RAW="${BASH_REMATCH[1]}"
cd "${CWD_RAW:-${CLAUDE_PROJECT_DIR:-.}}" 2>/dev/null || exit 0
# crew 1.0 F4 reachability fix: this gate is `.crew/` the DIRECTORY, not
# `.crew/config.json` -- so the forced-continuation handover to auto-clear.sh
# just below is never blocked purely by a repo lacking a config.json, which
# would otherwise stand this hook down before auto-clear's own (now equally
# directory-gated) logic ever got a chance to run. See docs/crew/config-rationale.md.
[ -d .crew ] || exit 0

if [ "$STOP_ACTIVE" = 1 ]; then
  if [ -f "$MARKER" ]; then
    cw_run_auto_clear
  fi
  exit 0
fi

# From here down: this hook's OWN context-window measurement and nagging --
# as distinct from the auto-clear handover above, which needed only `.crew/`
# -- still requires a fully initialised crew repo. Unchanged from before F4:
# a `.crew/` directory with no config.json gets no warnings and writes no
# marker, exactly as a repo that never ran `/crew:init` always has.
# L-0680: "config.json" is the resolved one (crew_repo_config_dir, T-0096): a
# linked worktree with none of its own reads the main checkout's, own files win
# whole, `unknown` reads only the own .crew/. The marker stays in this .crew/.
# CFG_SHOWN is the name a message gives it: `.crew/config.json` when it is
# this checkout's own, the main checkout's full path when it is inherited.
crew_repo_config_dir .
CREW_CFG="$CREW_CFG_DIR/config.json"
CFG_SHOWN="${CREW_CFG#./}"
[ -f "$CREW_CFG" ] || exit 0

# Loop safety, layer 2: once per session per threshold crossing ($MARKER,
# keyed above), cleared by handoff-read.sh at this session's next
# SessionStart and re-armed below when a trustworthy reading drops back under
# the threshold. Owned entirely by the REAL over-threshold nag further down
# this file -- the no-python branch immediately below does NOT read or write
# it, on purpose; see its own header comment for why.

# `crew_py_strict`, NOT `crew_py`. `crew_py`'s bare `command -v` accepts the
# Windows Store App Execution Alias stub (a real, executable file that
# produces no output), which is what let this hook silently never fire on a
# machine where the stub sat ahead of a real interpreter on PATH.
#
# PM ruling 2026-09-22 (Windows audit wave 3 re-review): a resolver failure
# FAILS CLOSED rather than failing open. The original fail-open design
# reasoned that a stderr-only warning on exit 0 was still "loud"; it is not
# -- `auto-clear.sh:26` states the same fact about this exact hook's own
# stderr ("a Stop hook's stderr is invisible on exit 0"), and a message
# nobody reads is not a check that ran, it is CLAUDE.md's "unknown
# collapsing into the safe-looking value" wearing a slightly longer disguise.
#
# Merged-branch review, 2026-09-22 (second round): this branch used to ALSO
# read and claim $MARKER -- the SAME file the real over-threshold nag below
# uses, and the same file context-watch.ps1 and auto-clear.ps1 both read on
# Windows. That conflated "an interpreter error happened" with "the context
# window was actually measured and is over budget", and a zero-byte marker
# claimed here with nothing measured made the .ps1 flavour (which never
# touches python, so it never fails this way itself) stand down for the rest
# of the session and let auto-clear /clear on the strength of a handoff the
# false alarm itself asked for.
#
# Fixed by NOT touching $MARKER at all in this branch, in either direction.
# Two ways existed to bound the repeat: a SEPARATE marker file this branch
# owns alone, or relying on stop_hook_active (now checked first, above) to
# bound the retry Claude Code itself triggers after an exit-2 block to ONE
# forced continuation. Chose the latter -- verify-gate.sh:48 already applies
# the identical rule for the identical reason -- because a separate marker
# would need a THIRD place (handoff-read.sh, at SessionStart) taught to
# clear it or it would silence this branch forever, on every future session,
# the first time python ever glitched once; that is out of this file's
# scope and worse than the cost it avoids. The accepted cost: a session
# whose interpreter STAYS broken is asked for a precautionary handoff once
# per TURN, not once per session, until it is fixed -- correctly bounded,
# not silent, and no marker to falsely believe as a real measurement.
PY=$(crew_py_strict)
if [ -z "$PY" ]; then
  # context.enabled must still be honoured even without python -- a repo
  # that has explicitly turned this hook off must not be nagged just
  # because the interpreter that would normally have read that setting is
  # broken. That would be the same "unknown collapsing into the wrong
  # value" mistake pointed the other way: treating a KNOWN "off" as unknown.
  #
  # Scoped to the "context" block specifically, not a blind whole-file
  # grep -- .crew/config.json has OTHER "enabled" keys (pm.enabled, for
  # one) that must not be mistaken for this one. The awk pass below extracts
  # just the brace-balanced value of the "context" key; grep then runs only
  # against that substring.
  CTX_BLOCK=$(awk '
    { buf = buf $0 "\n" }
    END {
      i = index(buf, "\"context\"")
      if (!i) { exit }
      rest = substr(buf, i)
      b = index(rest, "{")
      if (!b) { exit }
      depth = 0
      for (j = b; j <= length(rest); j++) {
        c = substr(rest, j, 1)
        if (c == "{") depth++
        if (c == "}") depth--
        out = out c
        if (depth == 0) break
      }
      print out
    }
  ' "$CREW_CFG" 2>/dev/null)
  if printf '%s' "$CTX_BLOCK" | grep -q '"enabled"[[:space:]]*:[[:space:]]*false'; then
    exit 0
  fi
  # The handoff path is the fixed .work/HANDOFF.md (crew_state.CONTEXT_HANDOFF_PATH).
  HANDOFF_NOTE=".work/HANDOFF.md"
  # NOT `$MARKER` -- see the header comment above this branch. Nothing is
  # claimed here; `stop_hook_active`, checked first at the top of this
  # script, is what bounds the retry Claude Code triggers after this exit 2.
  cat >&2 << MSG
crew context-watch: no usable python (stub or unusable interpreter) - context
usage could not be measured this turn. This hook cannot tell you how full
the context window actually is right now, so treat it as if it might be
full: before ending this turn, write the handoff note to ${HANDOFF_NOTE}
per the crew-context skill, as a precaution. This is bounded to one forced
continuation for THIS turn, not suppressed for the rest of the session --
it will ask again on the next turn if the interpreter is still unusable
then.
MSG
  exit 2
fi

# ONE python start for everything this turn needs from the payload, the config
# and the transcript. It used to be five (three read_json calls, a config read
# and the transcript scan), and on Git Bash each python start is a process tree
# costing 0.3-0.7s on the Windows host; with the cygpath and tr forks around them
# a no-op turn took ~9s, against a 20s budget shared with the other Stop hooks.
# A non-ASCII character in the session id is sent as `?`: the key replaces it with
# `_` either way, one for one, and bash counts bytes where python counts characters.
# Output, one line each: CW1 (python ran), transcript_path, session_id,
# stop_hook_active, the config line (or MALFORMED_CONFIG_CONTEXT_BLOCK), and the
# reading. Python stops writing at the first line bash would exit on, in the same
# order bash used to check them. Config path: a relative one is native as it is;
# an inherited main-checkout one is converted.
# scan() below is the former standalone transcript read, unchanged in logic: the
# last assistant turn's message.usage is the real window occupancy (input +
# cache_read + cache_creation); sidechain lines are skipped; a size estimate is
# the fallback; the budget comes from a model table, corrected upward by the
# observed peak; the threshold is the LATER of warnAt*budget and budget-reserve
# (warnAt <= 0 stays "fire now"); `trusted` is true only for a measured reading
# of this window (never an estimate, an unknown model, a pre-compaction reading
# or an implausible one). The long comments were dropped to keep the -c argument
# small; `git log -p` on this file has them.
read -r -d '' CW_PY << 'PYSCRIPT' || true
import json, os, re, sys


def scan(path, warn_at, reserve):
    WINDOWS = (
        ("[1m]", 1_000_000),
        ("fable", 1_000_000),
        ("opus-5", 1_000_000),
        ("sonnet-5", 1_000_000),
        ("haiku", 200_000),
        ("opus", 200_000),
        ("sonnet", 200_000),
    )
    TIERS = (200_000, 500_000, 1_000_000, 2_000_000)
    SIDECHAIN = re.compile(r'"isSidechain"\s*:\s*true')
    BOUNDARY = re.compile(r'"compact_boundary"|"isCompactSummary"\s*:\s*true')
    last, model, peak, main_bytes = None, "", 0, 0
    last_at, boundary_at, lineno = -1, -1, 0
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                if SIDECHAIN.search(line):
                    continue
                lineno += 1
                main_bytes += len(line.encode("utf-8")) + 1
                if BOUNDARY.search(line):
                    boundary_at = lineno
                if '"usage"' not in line:
                    continue
                try:
                    rec = json.loads(line)
                except ValueError:
                    continue
                msg = rec.get("message") or {}
                usage = msg.get("usage")
                if not isinstance(usage, dict) or "cache_read_input_tokens" not in usage:
                    continue
                last, last_at = usage, lineno
                if msg.get("model") and not msg["model"].startswith("<"):
                    model = msg["model"]
                peak = max(peak, usage.get("input_tokens", 0)
                           + usage.get("cache_read_input_tokens", 0)
                           + usage.get("cache_creation_input_tokens", 0))
    except OSError:
        pass
    if last:
        used = (last.get("input_tokens", 0)
                + last.get("cache_read_input_tokens", 0)
                + last.get("cache_creation_input_tokens", 0))
        source = "exact"
    else:
        used, source = int(main_bytes / 4 * 0.75), "estimated"
    low = model.lower()
    known = any(key in low for key, _ in WINDOWS)
    budget = next((w for key, w in WINDOWS if key in low), 200_000)
    if peak > budget:
        budget = next((t for t in TIERS if t > peak * 1.05), peak * 2)
    if warn_at <= 0:
        threshold = 0
    else:
        threshold = budget * warn_at
        if reserve > 0:
            threshold = max(threshold, budget - reserve)
    threshold = int(threshold)
    over = 1 if budget > 0 and used >= threshold else 0
    pct = int(used / budget * 100) if budget > 0 else 0
    if source != "exact":
        why = "estimated-from-transcript-size"
    elif not known:
        why = "unknown-window"
    elif boundary_at > last_at:
        why = "stale-reading-before-compaction"
    elif used <= 0 or used > budget:
        why = "implausible-reading"
    else:
        why = "measured"
    trusted = 1 if why == "measured" else 0
    return " ".join(str(x) for x in (used, source, budget, over, pct, trusted, why))


out = sys.stdout
try:
    out.reconfigure(encoding="utf-8", newline="\n")
except Exception:
    pass
out.write("CW1\n")
try:
    d = json.load(sys.stdin)
    if not isinstance(d, dict):
        raise ValueError
except Exception:
    sys.exit(0)


def field(k):
    return str(d.get(k, "")).replace("\r", " ").replace("\n", " ")


tp, sid, sha = field("transcript_path"), field("session_id"), field("stop_hook_active")
sid = "".join(ch if ord(ch) < 128 else "?" for ch in sid)
out.write(tp + "\n" + sid + "\n" + sha + "\n")
if sha in ("True", "true") or not os.path.isfile(tp):
    sys.exit(0)
MALFORMED = "MALFORMED_CONFIG_CONTEXT_BLOCK"
try:
    raw = json.load(open(sys.argv[1]))
except Exception:
    raw = {}
c = raw.get("context", {}) if isinstance(raw, dict) else {}
if not isinstance(c, dict):
    out.write(MALFORMED + "\n")
    sys.exit(0)
try:
    reserve = max(0, int(c.get("reserveTokens", 0) or 0))
except (TypeError, ValueError):
    reserve = 100_000
warn = str(c.get("warnAt", 0.4))
enabled = str(c.get("enabled", True)).lower()
out.write(warn + " " + enabled + " " + str(reserve) + "\n")
if enabled == "false":
    sys.exit(0)
try:
    out.write(scan(tp, float(warn), reserve) + "\n")
except Exception:
    pass
PYSCRIPT
case "$CREW_CFG" in
  ./*) CFG_ARG="$CREW_CFG" ;;
  *) CFG_ARG=$(crew_native_path "$CREW_CFG") ;;
esac
CW_OUT=$("$PY" -c "$CW_PY" "$CFG_ARG" <<< "$INPUT" 2>/dev/null)
CW_OUT=${CW_OUT//$'\r'/}
case "$CW_OUT" in
  CW1*) ;;
  *)
    echo "crew context-watch: python resolved but produced no result (an unexpected interpreter failure, not a malformed config) - context warnings are OFF this turn" >&2
    exit 0
    ;;
esac
TRANSCRIPT="" PARSED_SESSION="" STOP_HOOK_ACTIVE="" CFG="" READ=""
{
  IFS= read -r _cw_skip; IFS= read -r TRANSCRIPT; IFS= read -r PARSED_SESSION
  IFS= read -r STOP_HOOK_ACTIVE; IFS= read -r CFG; IFS= read -r READ
} <<< "$CW_OUT" || true
# The properly-parsed id wins over the grep above for what is RECORDED in the
# marker; the key is recomputed from it so the two can never name different
# files.
if [ -n "$PARSED_SESSION" ]; then
  SESSION_ID="$PARSED_SESSION"
  session_markers "$SESSION_ID"
fi
[ -f "$TRANSCRIPT" ] || exit 0

# Loop safety, layer 1, re-checked here with python's own parsed value: the
# cheap string match at the top of this file already caught the common exact
# shapes Claude Code sends and is what protects the no-python branch above,
# which cannot reach this line at all; this is defense in depth for whatever
# that string match might not, now that python is proven available to parse
# it properly. Layer 2 is the once-per-session marker above. Layer 3 is
# Claude Code's own 8-consecutive-block backstop.
{ [ "$STOP_HOOK_ACTIVE" = "True" ] || [ "$STOP_HOOK_ACTIVE" = "true" ]; } && exit 0

# No hook_once claim here on purpose: Stop fires once per TURN against a
# stable session id, so a session-scoped claim taken on turn 1 would suppress
# the context nag for the rest of the session. $MARKER above is the real
# once-per-session gate for this hook, reset by handoff-read.sh at the next
# SessionStart -- that stays.

# A "context" VALUE that parses but is not an object (`null`, `"off"`) is a
# config problem, not an interpreter one, so it is not reported as "python is
# broken".
if [ "$CFG" = "MALFORMED_CONFIG_CONTEXT_BLOCK" ]; then
  echo "crew context-watch: ${CFG_SHOWN}'s \"context\" value is malformed (not an object, e.g. null) - context warnings are OFF until it is fixed" >&2
  exit 0
fi
# python ran (CW1) and the transcript exists, so an empty CFG is not a malformed
# config; name it distinctly rather than folding the two together.
if [ -z "$CFG" ]; then
  echo "crew context-watch: python resolved but produced no config read (an unexpected interpreter failure, not a malformed config) - context warnings are OFF this turn" >&2
  exit 0
fi
# The handoff path is the fixed .work/HANDOFF.md (crew_state.CONTEXT_HANDOFF_PATH).
HANDOFF=".work/HANDOFF.md"
read -r WARN_AT ENABLED RESERVE <<< "$CFG"
[ "$ENABLED" = "false" ] && exit 0

# The reading is the ACTUAL window occupancy (see scan() above): every assistant
# turn carries message.usage and the last one holds the real prompt size, which
# replaced a file-size heuristic that read 45% high. An empty reading (the scan
# failed) stands this hook down, as it always has.
[ -z "$READ" ] && exit 0
read -r USED SOURCE BUDGET OVER PCT_H TRUSTED WHY <<< "$READ"
[ -z "$USED" ] || [ -z "$BUDGET" ] && exit 0

if [ -f "$MARKER" ]; then
  if [ "${OVER:-0}" -eq 0 ] && [ "$SOURCE" = "exact" ]; then
    # A measured reading back under the threshold means the window shrank
    # (a compaction) since the wrap-up: that crossing is over, so re-arm for
    # the next one. Measured only -- an estimate must not re-arm a nag.
    rm -f "$MARKER" "$SENT_MARKER" "$ESCALATED"
    exit 0
  fi
  # T-0017: an armed wrap-up whose results are not on disk is fed back to
  # the model ONCE -- this is never the stop_hook_active turn (that exits
  # far above), so it always follows a human turn and adds no loop. The
  # noclobber claim makes exactly one flavour escalate when both run, and a
  # session whose clear was already sent is not nagged about it.
  if [ ! -f "$SENT_MARKER" ] &&
     [ "$("$PY" "$(crew_native_path "$DIR/crew_autocycle.py")" wrapup-armed --root "$(crew_native_path "$PWD")" --session "$SESSION_ID" 2>/dev/null | tr -d '\r')" = "on" ]; then
    WRAP_WHY=$("$PY" "$(crew_native_path "$DIR/crew_autocycle.py")" wrapup-check --root "$(crew_native_path "$PWD")" 2>/dev/null | tr -d '\r')
    if [ "$WRAP_WHY" != "ok" ] && ( set -o noclobber; : > "$ESCALATED" ) 2>/dev/null; then
      printf 'crew wrap-up incomplete: %s. Fix exactly that, run /crew:handoff --wrap-up again, end the turn.\n' \
        "${WRAP_WHY:-the wrap-up check gave no answer}" >&2
      exit 2
    fi
  fi
  # This crossing was already asked about. Never block twice for it; the
  # handoff may have been written since, which is all auto-clear wants to
  # know. It is off unless this machine opted in, and it decides for itself
  # whether the note and the reading are good enough to act on.
  cw_run_auto_clear
  exit 0
fi
[ "${OVER:-0}" -eq 0 ] && exit 0

# Claim the once-per-crossing gate ATOMICALLY. Both flavours are registered for
# Stop and, on Windows with Git Bash installed, both actually run - a
# test-then-touch would let both pass the check and emit the same warning
# twice. noclobber makes the create fail for whichever loses. The marker
# records WHICH session asked and the reading that caused it, so auto-clear
# can refuse a reading nobody should trust.
MARKER_JSON=$("$PY" -c 'import json,sys,time; print(json.dumps({"session_id": sys.argv[1], "requested_at": time.time(), "used": int(sys.argv[2]), "budget": int(sys.argv[3]), "source": sys.argv[4], "trusted": sys.argv[5] == "1", "why": sys.argv[6]}))' "$SESSION_ID" "$USED" "$BUDGET" "$SOURCE" "$TRUSTED" "$WHY" 2>/dev/null)
( set -o noclobber; printf '%s\n' "$MARKER_JSON" > "$MARKER" ) 2>/dev/null || exit 0

# T-0017: armed, the warning IS the wrap-up procedure, and supersedes the
# message below. Unarmed (or any error), crew_autocycle prints nothing and
# today's message goes out unchanged.
WRAP_MSG=$("$PY" "$(crew_native_path "$DIR/crew_autocycle.py")" wrapup-message --root "$(crew_native_path "$PWD")" --session "$SESSION_ID" --pct "$PCT_H" 2>/dev/null | tr -d '\r')
if [ -n "$WRAP_MSG" ]; then
  printf '%s\n' "$WRAP_MSG" >&2
  exit 2
fi

cat >&2 << MSG
You are at roughly ${PCT_H}% of the context budget. Reach a stopping point
now: finish or safely abandon the change in flight, write ${HANDOFF} per the
crew-context skill, update the ticket, then tell the user the session is
ready to clear. Do not start new work.
MSG
exit 2

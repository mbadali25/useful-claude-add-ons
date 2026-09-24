#!/usr/bin/env bash
. "$(dirname "${BASH_SOURCE[0]}")/_common.sh"
# Stop hook. Reads how full the context window actually is and, once past the
# threshold, asks Claude to write a handoff note before ending the turn.
# Exit 2 sends control back to the model with the reason on stderr.
#
# NOTHING HERE RUNS until a repository has .crew/config.json - crew is
# per-repository and its hooks are inert until `/crew:init`. That is deliberate
# (a gate that fires in every repo you open would be hostile), but it does mean
# installing the plugin is not enough on its own.
INPUT=$(cat)

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
}
SESSION_ID=""
SESSION_RE='"session_id"[[:space:]]*:[[:space:]]*"([^"]*)"'
if [[ "$INPUT" =~ $SESSION_RE ]]; then
  SESSION_ID="${BASH_REMATCH[1]}"
fi
session_markers "$SESSION_ID"

# `.crew/config.json`'s existence decides whether this hook does ANYTHING,
# so it is checked BEFORE resolving python, not after -- a non-crew
# repository must not pay for spinning up an interpreter (or, before the
# WindowsApps fix below, for launching a stub) to run a hook that was always
# going to exit 0.
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
CWD_RAW=$(printf '%s' "$INPUT" | grep -o '"cwd"[[:space:]]*:[[:space:]]*"[^"]*"' | sed -E 's/.*:[[:space:]]*"([^"]*)"/\1/')
cd "${CWD_RAW:-${CLAUDE_PROJECT_DIR:-.}}" 2>/dev/null || exit 0
[ -f .crew/config.json ] || exit 0

if [ "$STOP_ACTIVE" = 1 ]; then
  if [ -f "$MARKER" ]; then
    bash "$(dirname "${BASH_SOURCE[0]}")/auto-clear.sh" --root "$PWD" --session "$SESSION_ID" 2>/dev/null
  fi
  exit 0
fi

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
  ' .crew/config.json 2>/dev/null)
  if printf '%s' "$CTX_BLOCK" | grep -q '"enabled"[[:space:]]*:[[:space:]]*false'; then
    exit 0
  fi
  # handoffPath cannot be read precisely without python (see CTX_BLOCK's own
  # approximation above), so the message names WHERE to look rather than
  # hard-coding the shipped default as if it were certainly correct.
  HANDOFF_NOTE="the configured handoff path (context.handoffPath in .crew/config.json; .work/HANDOFF.md if unset)"
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

read_json() { "$PY" -c 'import sys,json;d=json.load(sys.stdin);print(d.get(sys.argv[1],""))' "$1" <<< "$INPUT" 2>/dev/null; }
TRANSCRIPT=$(read_json transcript_path)
# The properly-parsed id wins over the grep above for what is RECORDED in the
# marker; the key is recomputed from it so the two can never name different
# files.
PARSED_SESSION=$(read_json session_id | tr -d '\r')
if [ -n "$PARSED_SESSION" ]; then
  SESSION_ID="$PARSED_SESSION"
  session_markers "$SESSION_ID"
fi
STOP_HOOK_ACTIVE=$(read_json stop_hook_active)
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

CFG=$("$PY" - << 'PY' 2>/dev/null
import json
# An unparseable file (json.load raises) is treated as "no context settings",
# same as always -- the file's presence is already proven by bash above, and
# a fully broken file is caught by the outer try/except exactly as before.
# What that outer except did NOT cover, and what MALFORMED reports
# separately: a "context" VALUE that parses fine but is not an object at all
# (e.g. `"context": null` or `"context": "off"`) -- a config problem, not an
# interpreter one, so it must not be reported as "python is broken".
MALFORMED = "MALFORMED_CONFIG_CONTEXT_BLOCK"
try:
    raw = json.load(open(".crew/config.json"))
except Exception:
    raw = {}
c = raw.get("context", {}) if isinstance(raw, dict) else {}
if not isinstance(c, dict):
    # The actual reported bug: `"context": null` (or any non-object value)
    # makes `c` something other than a dict, and every `c.get(...)` call
    # below would raise AttributeError -- which the OLD single-line
    # `try: ... except Exception: c={}` did not cover, because that try only
    # wrapped the line that PRODUCES `c`, not the lines that USE it. Caught
    # here, explicitly, before any `.get()` call runs against it.
    print(MALFORMED)
else:
    # reserveTokens: absolute headroom floor, in tokens. Absent -> 100k. null
    # or <=0 -> off, i.e. the old pure-percentage behaviour. See the
    # threshold below.
    try: reserve = max(0, int(c.get("reserveTokens", 0) or 0))
    except (TypeError, ValueError): reserve = 100_000
    print(c.get("warnAt",0.5), c.get("budgetTokens") or 0, c.get("handoffPath",".work/HANDOFF.md"), str(c.get("enabled",True)).lower(), str(c.get("autoWrapUp",True)).lower(), reserve)
PY
)
if [ "$CFG" = "MALFORMED_CONFIG_CONTEXT_BLOCK" ]; then
  echo "crew context-watch: .crew/config.json's \"context\" value is malformed (not an object, e.g. null) - context warnings are OFF until it is fixed" >&2
  exit 0
fi
# By this point `.crew/config.json` is KNOWN to exist and parse as an object
# (checked in bash and in the heredoc above), and PY is a python
# `crew_py_strict` proved runs. The heredoc always prints either a config
# line or the MALFORMED sentinel on success, so an empty CFG here is neither
# of those -- it means the python PROCESS itself died or could not be
# reached after having already proved runnable (e.g. killed mid-write); name
# that distinctly from a malformed config rather than folding the two
# together.
if [ -z "$CFG" ]; then
  echo "crew context-watch: python resolved but produced no config read (an unexpected interpreter failure, not a malformed config) - context warnings are OFF this turn" >&2
  exit 0
fi
read -r WARN_AT BUDGET HANDOFF ENABLED AUTO_WRAP_UP RESERVE <<< "$CFG"
[ "$ENABLED" = "false" ] && exit 0

# Read the ACTUAL window occupancy, not a guess at it.
#
# Every assistant turn in the transcript carries message.usage, and the last one
# holds the real prompt size: input + cache_read + cache_creation. That IS the
# context window, measured by the thing that filled it.
#
# This replaced a file-size heuristic (bytes/4*0.75). The transcript is
# cumulative - it keeps every turn ever written, including ones a compaction
# already discarded - so file size measures how much a session has produced,
# not how full the window is. Measured on a real session the heuristic read 45%
# high (950k estimated against 654k actual), which on a 200k budget is the
# difference between "fire at 80%" and "fire on turn one, every turn".
READ=$("$PY" - "$TRANSCRIPT" "$BUDGET" "$WARN_AT" "$RESERVE" << 'PY' 2>/dev/null
import json, re, sys

path = sys.argv[1]
configured = int(sys.argv[2] or 0)
warn_at = float(sys.argv[3])
reserve = int(sys.argv[4])

# Known context windows, first match wins, so the specific keys sit above the
# generic ones. The Claude 5 family (fable, opus-5, sonnet-5) ships with 1M
# natively; the 4.x generation is 200k unless the id carries a "[1m]" suffix -
# and the transcript often records the base id without it, so this table is a
# starting point, not the last word. The observed high-water mark below
# corrects it. The mismatch that matters is the other way round: a 1M model
# read as 200k fires the gate at 160k, which is 16% of the real window.
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
# A compaction writes a boundary record; a usage record from before it
# describes a window that no longer exists. See `trusted` below.
BOUNDARY = re.compile(r'"compact_boundary"|"isCompactSummary"\s*:\s*true')
last, model, peak, main_bytes = None, "", 0, 0
last_at, boundary_at, lineno = -1, -1, 0
try:
    with open(path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            # Subagent turns are not main-window occupancy: the main window
            # only ever sees the agent's returned summary. Current builds keep
            # them in <session>/subagents/*.jsonl, which this never opens;
            # older builds wrote them inline flagged isSidechain. Skip those -
            # from the byte count too, so the size fallback below does not
            # count them either.
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

if configured > 0:
    budget, how, known = configured, "configured", True
else:
    low = model.lower()
    known = any(key in low for key, _ in WINDOWS)
    budget = next((w for key, w in WINDOWS if key in low), 200_000)
    how = f"auto:{model or 'unknown'}"

# Self-correct. If this session has already held more tokens than the budget
# claims the window is, the budget is wrong: a "[1m]" variant records its base
# id, and an older /crew:init pinned budgetTokens: 200000 into every config
# before the 1M models arrived. Observed usage cannot exceed the real window,
# so it is the better source - but ONLY a peak the window could not hold proves
# that. An earlier 95% margin bumped a correct 1M entry to the 2M tier once a
# session passed 950k, and the gate then never fired at all.
if peak > budget:
    budget = next((t for t in TIERS if t > peak * 1.05), peak * 2)
    how = f"{how}+observed"

# The threshold is the LATER of two rules, and the second one is why a 1M
# session is no longer cut short.
#
#   percentage: warnAt * budget      - what this always did
#   headroom:   budget - reserve     - never nag while this much is still free
#
# warnAt was tuned when every window was 200k, where 0.8 leaves 40k - about
# enough to finish a thought and write a handoff. The same 0.8 on a 1M window
# leaves 200k, a whole 200k session's worth of room, and asking for a handoff
# there throws away a fifth of the window. Taking the later of the two rules
# means the reserve can only ever push the warning LATER, never earlier: on a
# 200k window the percentage still wins (40k < 100k) and nothing changes, while
# on 1M the floor wins and the gate moves from 80% to 90%.
#
# warnAt <= 0 stays an unconditional "fire now" - it is the documented override
# and a floor that quietly outranked it would make it a lie.
if warn_at <= 0:
    threshold = 0
else:
    threshold = budget * warn_at
    if reserve > 0:
        threshold = max(threshold, budget - reserve)
threshold = int(threshold)

over = 1 if budget > 0 and used >= threshold else 0
pct = int(used / budget * 100) if budget > 0 else 0

# Whether this reading may license a /clear. It still drives the nag either
# way -- asking for a handoff on a doubtful reading costs a paragraph -- but
# auto-clear acts only on a reading that is a measurement of THIS window.
# Unknown is its own value here, never folded into "fine".
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
fmt = lambda n: format(int(n), ",d")  # noqa: E731  pylint: disable=unnecessary-lambda-assignment
print(used, source, budget, how, over, pct, fmt(used), fmt(budget),
      fmt(max(0, budget - used)), fmt(threshold), int(warn_at * 100),
      fmt(reserve), trusted, why)
PY
)
[ -z "$READ" ] && exit 0
read -r USED SOURCE BUDGET HOW OVER PCT_H USED_H BUDGET_H REMAIN_H THRESH_H WARN_PCT RESERVE_H TRUSTED WHY <<< "$READ"
[ -z "$USED" ] || [ -z "$BUDGET" ] && exit 0

if [ -f "$MARKER" ]; then
  if [ "${OVER:-0}" -eq 0 ] && [ "$SOURCE" = "exact" ]; then
    # A measured reading back under the threshold means the window shrank
    # (a compaction) since the wrap-up: that crossing is over, so re-arm for
    # the next one. Measured only -- an estimate must not re-arm a nag.
    rm -f "$MARKER" "$SENT_MARKER"
    exit 0
  fi
  # This crossing was already asked about. Never block twice for it; the
  # handoff may have been written since, which is all auto-clear wants to
  # know. It is off unless this machine opted in, and it decides for itself
  # whether the note and the reading are good enough to act on.
  bash "$(dirname "${BASH_SOURCE[0]}")/auto-clear.sh" --root "$PWD" --session "$SESSION_ID" 2>/dev/null
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

bash "$(dirname "$0")/notify.sh" waiting "context ${PCT_H}% - writing handoff" 2>/dev/null

# Report the absolute numbers, not only the percentage. A budgetTokens that does
# not match the model in use is otherwise invisible - it just makes the gate
# fire early forever, and a warning that is always on is one nobody reads.
BUDGET_NOTE=" Set context.budgetTokens in .crew/config.json to pin it."
case "$HOW" in
  configured+observed)
    BUDGET_NOTE=" context.budgetTokens in .crew/config.json says a smaller window,
but this session has already held more than that - and observed usage cannot
exceed the real window, so the larger figure wins. That pin is stale; set it to
null to let crew work the window out from the model." ;;
  auto:*+observed)
    BUDGET_NOTE=" The model's id said a smaller window, but this session has
already held more than that - and observed usage cannot exceed the real window,
so the larger figure wins. A 1M variant reports its base model id, which is why
the id alone is not trusted. Pin it with context.budgetTokens if you prefer." ;;
  configured)
    BUDGET_NOTE=" That came from .crew/config.json. Remove it to let crew work the
window out from the model and this session's own usage." ;;
esac

NOTE=""
if [ "$SOURCE" = "estimated" ]; then
  NOTE="
This figure is a fallback estimate from transcript size, not a measurement -
no usage record was found yet. It reads high after a compaction."
fi

# Name the rule that fired. A percentage alone cannot explain why an 800k
# reading on a 1M window said nothing and 900k did.
if [ "$RESERVE_H" = "0" ]; then
  THRESH_NOTE="Threshold: ${THRESH_H} tokens - warnAt ${WARN_PCT}% of the window.
context.reserveTokens is off, so no headroom floor applies."
else
  THRESH_NOTE="Threshold: ${THRESH_H} tokens - the later of warnAt ${WARN_PCT}% and the
last ${RESERVE_H} tokens (context.reserveTokens), so a large window is not cut
short by a percentage tuned for a small one."
fi

if [ "$AUTO_WRAP_UP" = "true" ]; then
cat >&2 << MSG
You are at roughly ${PCT_H}% of the context budget. Reach a stopping point
now: finish or safely abandon the change in flight, write ${HANDOFF} per the
crew-context skill, update the ticket, then tell the user the session is
ready to clear. Do not start new work.
MSG
else
cat >&2 << MSG
Context: ${USED_H} of ${BUDGET_H} tokens (${PCT_H}%), read from the transcript's
last usage record. Headroom left: ${REMAIN_H} tokens.${NOTE}

Budget source: ${HOW}.${BUDGET_NOTE}

${THRESH_NOTE}

Before ending this turn, write the handoff note to ${HANDOFF} following the
crew-context skill. Keep it to pointers and one short "next action" - do not
write a long narrative summary. A session this deep into its context is the
least reliable narrator of what it just did; the files are more trustworthy
than the recollection.

Then tell me the note is ready so I can /clear or /compact. Do not start new
work in this session.
MSG
fi
exit 2

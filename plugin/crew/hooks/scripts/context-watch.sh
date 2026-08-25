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

PY=$(crew_py) || { echo "crew context-watch: no usable python - context warnings are OFF" >&2; exit 0; }
read_json() { "$PY" -c 'import sys,json;d=json.load(sys.stdin);print(d.get(sys.argv[1],""))' "$1" <<< "$INPUT" 2>/dev/null; }
TRANSCRIPT=$(read_json transcript_path)
CWD=$(read_json cwd)
STOP_HOOK_ACTIVE=$(read_json stop_hook_active)
cd "${CWD:-${CLAUDE_PROJECT_DIR:-.}}" 2>/dev/null || exit 0
[ -f "$TRANSCRIPT" ] || exit 0
[ -f .crew/config.json ] || exit 0

# Loop safety, layer 1: Claude Code is already continuing because of a stop
# hook -- do not pile on more feedback. Layer 2 is the once-per-session
# marker below. Layer 3 is Claude Code's own 8-consecutive-block backstop.
{ [ "$STOP_HOOK_ACTIVE" = "True" ] || [ "$STOP_HOOK_ACTIVE" = "true" ]; } && exit 0

# No hook_once claim here on purpose: Stop fires once per TURN against a
# stable session id, so a session-scoped claim taken on turn 1 would suppress
# the context nag for the rest of the session. The existing
# .crew/.handoff-requested marker below is the real once-per-session gate for
# this hook, reset by handoff-read.sh at the next SessionStart -- that stays.

CFG=$("$PY" - << 'PY' 2>/dev/null
import json
try: c=json.load(open(".crew/config.json")).get("context",{})
except Exception: c={}
print(c.get("warnAt",0.8), c.get("budgetTokens") or 0, c.get("handoffPath",".work/HANDOFF.md"), str(c.get("enabled",True)).lower(), str(c.get("autoWrapUp",False)).lower())
PY
)
[ -z "$CFG" ] && exit 0
read -r WARN_AT BUDGET HANDOFF ENABLED AUTO_WRAP_UP <<< "$CFG"
[ "$ENABLED" = "false" ] && exit 0

# Loop safety: fire once per session until SessionStart clears the marker.
MARKER=".crew/.handoff-requested"
[ -f "$MARKER" ] && exit 0

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
READ=$("$PY" - "$TRANSCRIPT" "$BUDGET" << 'PY' 2>/dev/null
import json, re, sys

path = sys.argv[1]
configured = int(sys.argv[2] or 0)

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
last, model, peak, main_bytes = None, "", 0, 0
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
            main_bytes += len(line.encode("utf-8")) + 1
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
            last = usage
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
    budget, how = configured, "configured"
else:
    low = model.lower()
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

print(used, source, budget, how)
PY
)
[ -z "$READ" ] && exit 0
read -r USED SOURCE BUDGET HOW <<< "$READ"
[ -z "$USED" ] || [ -z "$BUDGET" ] && exit 0

OVER=$("$PY" -c "print(1 if $BUDGET > 0 and $USED/$BUDGET >= $WARN_AT else 0)" 2>/dev/null)
[ "${OVER:-0}" -eq 0 ] && exit 0

touch "$MARKER"
PCT_H=$("$PY" -c "print(int($USED/$BUDGET*100))")
USED_H=$("$PY" -c "print(format($USED, ',d'))")
BUDGET_H=$("$PY" -c "print(format(int($BUDGET), ',d'))")

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
last usage record.${NOTE}

Budget source: ${HOW}.${BUDGET_NOTE}

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

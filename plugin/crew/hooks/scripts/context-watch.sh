#!/usr/bin/env bash
# Stop hook. Estimates context usage from the transcript and, once past the
# threshold, asks Claude to write a handoff note before ending the turn.
# Exit 2 sends control back to the model with the reason on stderr.
INPUT=$(cat)
read_json() { python3 -c 'import sys,json;d=json.load(sys.stdin);print(d.get(sys.argv[1],""))' "$1" <<< "$INPUT" 2>/dev/null; }
TRANSCRIPT=$(read_json transcript_path)
CWD=$(read_json cwd)
cd "${CWD:-${CLAUDE_PROJECT_DIR:-.}}" 2>/dev/null || exit 0
[ -f "$TRANSCRIPT" ] || exit 0
[ -f .crew/config.json ] || exit 0

# No hook_once claim here on purpose: Stop fires once per TURN against a
# stable session id, so a session-scoped claim taken on turn 1 would suppress
# the context nag for the rest of the session. The existing
# .crew/.handoff-requested marker below is the real once-per-session gate for
# this hook, reset by handoff-read.sh at the next SessionStart -- that stays.

CFG=$(python3 - << 'PY' 2>/dev/null
import json
try: c=json.load(open(".crew/config.json")).get("context",{})
except Exception: c={}
print(c.get("warnAt",0.8), c.get("budgetTokens",200000), c.get("handoffPath",".work/HANDOFF.md"), str(c.get("enabled",True)).lower())
PY
)
[ -z "$CFG" ] && exit 0
read -r WARN_AT BUDGET HANDOFF ENABLED <<< "$CFG"
[ "$ENABLED" = "false" ] && exit 0

# Loop safety: fire once per session until SessionStart clears the marker.
MARKER=".crew/.handoff-requested"
[ -f "$MARKER" ] && exit 0

BYTES=$(wc -c < "$TRANSCRIPT" 2>/dev/null || echo 0)
# Rough proxy: JSONL transcript bytes -> tokens. ~4 chars/token, and the file
# carries JSON scaffolding the model never sees, so we discount it.
# This is an ESTIMATE. Calibrate against /context once and adjust budgetTokens.
EST=$(python3 -c "print(int($BYTES/4*0.75))")
PCT=$(python3 -c "print(round($EST/$BUDGET,3))")
OVER=$(python3 -c "print(1 if $PCT >= $WARN_AT else 0)")
[ "$OVER" -eq 0 ] && exit 0

touch "$MARKER"
PCT_H=$(python3 -c "print(int($PCT*100))")

bash "$(dirname "$0")/notify.sh" waiting "context ~${PCT_H}% - writing handoff" 2>/dev/null

cat >&2 << MSG
Context is at roughly ${PCT_H}% of budget (estimated from transcript size).

Before ending this turn, write the handoff note to ${HANDOFF} following the
crew-context skill. Keep it to pointers and one short "next action" - do not
write a long narrative summary. A session this deep into its context is the
least reliable narrator of what it just did; the files are more trustworthy
than the recollection.

Then tell me the note is ready so I can /clear or /compact. Do not start new
work in this session.
MSG
exit 2

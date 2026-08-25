#!/usr/bin/env bash
# SessionStart hook. On clear / compact / resume, prints the handoff note.
# stdout from SessionStart is injected into the new session's context.
INPUT=$(cat)
read_json() { python3 -c 'import sys,json;d=json.load(sys.stdin);print(d.get(sys.argv[1],""))' "$1" <<< "$INPUT" 2>/dev/null; }
SOURCE=$(read_json source); CWD=$(read_json cwd); SESSION=$(read_json session_id)
cd "${CWD:-${CLAUDE_PROJECT_DIR:-.}}" 2>/dev/null || exit 0

rm -f .crew/.handoff-requested   # reset the once-per-session gate

# SessionStart fires once per SOURCE EVENT (startup, clear, compact, resume,
# fork), not once per session -- claiming on session id alone would let the
# `startup` firing burn the claim, exit here on the filter having done
# nothing, and make the `clear` firing lose the race: the handoff would never
# be read after /clear, which is the entire point of this hook. So the claim
# comes AFTER the filter and is keyed on session+source together. Both
# flavours are registered here with no matcher, so both fire wherever both
# interpreters exist; only the winner of the claim does any work.
case "$SOURCE" in clear|compact|resume|fork) ;; *) exit 0 ;; esac
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY=$(command -v python3 || command -v python) || exit 0
"$PY" "$DIR/hook_once.py" handoff-read "${SESSION}-${SOURCE}" || exit 0

[ -f .crew/config.json ] || exit 0

# When context.autoResume is exactly true, pm_brief._resume_context() owns
# the handoff in this mode: it folds the same text plus the extracted next
# action into its additionalContext payload. Standing down here keeps the
# handoff to a single emitter -- printing it here too would inject it twice.
AUTO_RESUME=$(python3 -c 'import json;print(json.load(open(".crew/config.json")).get("context",{}).get("autoResume") is True)' 2>/dev/null)
[ "$AUTO_RESUME" = "True" ] && exit 0

HANDOFF=$(python3 -c 'import json;print(json.load(open(".crew/config.json")).get("context",{}).get("handoffPath",".work/HANDOFF.md"))' 2>/dev/null)
HANDOFF="${HANDOFF:-.work/HANDOFF.md}"
[ -f "$HANDOFF" ] || exit 0

# Plain text, phrased as project information rather than instructions:
# text framed as out-of-band commands trips prompt-injection defences and gets
# surfaced to the user instead of being treated as context.
echo "## Handoff from the previous session (${SOURCE})"
echo
cat "$HANDOFF"
echo
echo "The working tree is the source of truth. Verify the notes above against"
echo "git diff before acting on them."
exit 0

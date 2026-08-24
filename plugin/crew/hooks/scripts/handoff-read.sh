#!/usr/bin/env bash
# SessionStart hook. On clear / compact / resume, prints the handoff note.
# stdout from SessionStart is injected into the new session's context.
INPUT=$(cat)
read_json() { python3 -c 'import sys,json;d=json.load(sys.stdin);print(d.get(sys.argv[1],""))' "$1" <<< "$INPUT" 2>/dev/null; }
SOURCE=$(read_json source); CWD=$(read_json cwd); SESSION=$(read_json session_id)
cd "${CWD:-${CLAUDE_PROJECT_DIR:-.}}" 2>/dev/null || exit 0

# Both flavours of this hook are registered on SessionStart, which has no
# matcher, so both fire wherever both interpreters exist. Only the winner of
# this claim does any work; the loser exits quietly.
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY=$(command -v python3 || command -v python) || exit 0
"$PY" "$DIR/hook_once.py" handoff-read "$SESSION" || exit 0

rm -f .crew/.handoff-requested   # reset the once-per-session gate

case "$SOURCE" in clear|compact|resume) ;; *) exit 0 ;; esac
[ -f .crew/config.json ] || exit 0

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

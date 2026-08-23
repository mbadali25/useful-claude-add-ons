#!/usr/bin/env bash
. "$(dirname "${BASH_SOURCE[0]}")/_common.sh"
# SessionStart hook. On clear / compact / resume, prints the handoff note.
# stdout from SessionStart is injected into the new session's context.
INPUT=$(cat)
read_json() { crew_json_field "$INPUT" "$1"; }
SOURCE=$(read_json source); CWD=$(read_json cwd)
cd "${CWD:-${CLAUDE_PROJECT_DIR:-.}}" 2>/dev/null || exit 0

rm -f .crew/.handoff-requested   # reset the once-per-session gate
rm -f .crew/.deploy-in-flight    # a deploy from a dead session cannot be recorded now

case "$SOURCE" in clear|compact|resume) ;; *) exit 0 ;; esac
[ -f .crew/config.json ] || exit 0

PY=$(crew_py) && HANDOFF=$("$PY" -c 'import json;print(json.load(open(".crew/config.json")).get("context",{}).get("handoffPath",".work/HANDOFF.md"))' 2>/dev/null)
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

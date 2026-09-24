#!/usr/bin/env bash
. "$(dirname "${BASH_SOURCE[0]}")/_common.sh"
# SessionStart hook. On clear / compact / resume, prints the handoff note.
# stdout from SessionStart is injected into the new session's context.
INPUT=$(cat)
read_json() { crew_json_field "$INPUT" "$1"; }
SOURCE=$(read_json source); CWD=$(read_json cwd); SESSION=$(read_json session_id)
cd "${CWD:-${CLAUDE_PROJECT_DIR:-.}}" 2>/dev/null || exit 0

# Reset THIS session's wrap-up gate and auto-clear claim, and nobody else's.
# Both used to be one file per repository, so any terminal's SessionStart --
# a plain `startup` in a second window included -- re-armed every other
# session in the repo. Keyed exactly as context-watch.sh keys them. The
# unkeyed names are the pre-fix layout and are still removed, so a marker
# left by an older version cannot sit there forever.
KEY="${SESSION//[^A-Za-z0-9_-]/_}"
KEY="${KEY:0:100}"
KEY="${KEY:-nosession}"
rm -f ".crew/.handoff-requested-${KEY}" ".crew/.autoclear-sent-${KEY}"
rm -f .crew/.handoff-requested .crew/.autoclear-sent
# Another session's markers are never touched here, so the ones a cleared
# session leaves behind (its id is gone for good) are aged out instead.
find .crew -maxdepth 1 \( -name '.handoff-requested-*' -o -name '.autoclear-sent-*' \) -mtime +7 -exec rm -f {} + 2>/dev/null
rm -f .crew/.deploy-in-flight    # a deploy from a dead session cannot be recorded now

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
PY=$(crew_py) || { echo "crew handoff-read: no usable python - the handoff note will not print" >&2; exit 0; }
# `memory.inject` on (the default since 1.0.0) hands the handoff to
# crew-context.sh, which injects it inside its own SessionStart budget --
# printing it here too would put it in the session twice. Same reader as that hook (crew_context.inject_enabled).
# After the resets above, which other hooks' once-per-session gates rely on.
"$PY" -c 'import sys; sys.path.insert(0, sys.argv[1]); import crew_context as c; sys.exit(0 if c.inject_enabled(c.find_root(sys.argv[2])) else 1)' "$DIR" "$PWD" 2>/dev/null && exit 0
"$PY" "$DIR/hook_once.py" handoff-read "${SESSION}-${SOURCE}" || exit 0

[ -f .crew/config.json ] || exit 0

PY=$(crew_py) || exit 0

HANDOFF=$("$PY" -c 'import json;print(json.load(open(".crew/config.json")).get("context",{}).get("handoffPath",".work/HANDOFF.md"))' 2>/dev/null)
HANDOFF="${HANDOFF:-.work/HANDOFF.md}"
[ -f "$HANDOFF" ] || exit 0

# Stale-handoff check, right before this note would be injected as though it
# were current -- the concrete failure this exists to catch: a note still
# saying "at the spec-review gate" hours after the gate closed and more
# commits landed past it. Delegates to crew_state.archive_stale_handoff
# rather than reimplementing its signals in bash; see that function and
# crew_state.handoff_staleness for what each signal catches and why. Fails
# open: any error here (bad JSON, python raising, git absent) leaves
# ARCHIVED_PATH empty and falls through to printing the note unchanged,
# exactly like every session before this feature existed -- a hook that
# breaks startup over a staleness check is worse than one honestly-stale
# note.
VERDICT=$("$PY" "$DIR/crew_state.py" --archive-stale-handoff 2>/dev/null)
ARCHIVED_PATH=$(printf '%s' "$VERDICT" | "$PY" -c '
import json, sys
try:
    d = json.load(sys.stdin)
except Exception:
    d = {}
print(d.get("archivedPath", "") if d.get("archived") else "")' 2>/dev/null)
if [ -n "$ARCHIVED_PATH" ]; then
  echo "## Handoff from the previous session (${SOURCE})"
  echo
  echo "A handoff note was here, but it described a state this repository has"
  echo "since moved past. It has been archived, not deleted, at"
  echo "${ARCHIVED_PATH} for the record -- nothing from it is being treated"
  echo "as current this session."
  exit 0
fi

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

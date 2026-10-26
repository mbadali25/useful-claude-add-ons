#!/usr/bin/env bash
. "$(dirname "${BASH_SOURCE[0]}")/_common.sh"
# SessionStart hook. Resets this session's once-per-session markers; the
# handoff note is printed by crew-context.sh, not here.
INPUT=$(cat)
read_json() { crew_json_field "$INPUT" "$1"; }
CWD=$(read_json cwd); SESSION=$(read_json session_id)
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
rm -f ".crew/.wrapup-escalated-${KEY}"    # T-0017: session_id survives /compact
rm -f .crew/.handoff-requested .crew/.autoclear-sent
# Another session's markers are never touched here, so the ones a cleared
# session leaves behind (its id is gone for good) are aged out instead.
find .crew -maxdepth 1 \( -name '.handoff-requested-*' -o -name '.autoclear-sent-*' -o -name '.wrapup-escalated-*' \) -mtime +7 -exec rm -f {} + 2>/dev/null
rm -f .crew/.deploy-in-flight    # a deploy from a dead session cannot be recorded now

# The handoff itself is injected by crew-context.sh inside its own SessionStart
# budget (memory injection is always on); printing it here too would put it in
# the session twice. This hook only resets the markers above.
exit 0

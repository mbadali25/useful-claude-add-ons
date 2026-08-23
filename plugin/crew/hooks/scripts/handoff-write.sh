#!/usr/bin/env bash
# PreCompact hook. Snapshots the transcript and makes sure a handoff exists
# before compaction discards detail.
INPUT=$(cat)
read_json() { python3 -c 'import sys,json;d=json.load(sys.stdin);print(d.get(sys.argv[1],""))' "$1" <<< "$INPUT" 2>/dev/null; }
TRANSCRIPT=$(read_json transcript_path); TRIGGER=$(read_json trigger); CWD=$(read_json cwd)
cd "${CWD:-${CLAUDE_PROJECT_DIR:-.}}" 2>/dev/null || exit 0
[ -f .crew/config.json ] || exit 0

mkdir -p .crew/transcripts .work
if [ -f "$TRANSCRIPT" ]; then
  cp "$TRANSCRIPT" ".crew/transcripts/$(date +%Y%m%d-%H%M%S)-${TRIGGER:-auto}.jsonl" 2>/dev/null
  # keep the last 5 only
  ls -1t .crew/transcripts/*.jsonl 2>/dev/null | tail -n +6 | xargs -r rm -f
fi

HANDOFF=$(python3 -c 'import json;print(json.load(open(".crew/config.json")).get("context",{}).get("handoffPath",".work/HANDOFF.md"))' 2>/dev/null)
HANDOFF="${HANDOFF:-.work/HANDOFF.md}"

# If no handoff exists, write a factual skeleton from the repo, not from memory.
if [ ! -f "$HANDOFF" ]; then
  {
    echo "# Handoff"
    echo "written: $(date -u +%Y-%m-%dT%H:%M:%SZ) (auto, at ${TRIGGER:-auto} compact)"
    echo "branch: $(git branch --show-current 2>/dev/null)"
    echo "head: $(git rev-parse --short HEAD 2>/dev/null)"
    echo
    echo "## Changed files"
    git diff --name-only HEAD 2>/dev/null | head -30
    git ls-files --others --exclude-standard 2>/dev/null | head -10
    echo
    echo "## Open tickets"
    grep -m5 '| open |' .work/INDEX.md 2>/dev/null || echo "(none recorded)"
    echo
    echo "## Next action"
    echo "UNKNOWN - this skeleton was written automatically at compaction."
    echo "Verify against the diff before continuing."
  } > "$HANDOFF"
fi
exit 0

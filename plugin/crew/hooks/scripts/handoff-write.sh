#!/usr/bin/env bash
. "$(dirname "${BASH_SOURCE[0]}")/_common.sh"
# PreCompact hook. Snapshots the transcript and makes sure a handoff exists
# before compaction discards detail.
INPUT=$(cat)
read_json() { crew_json_field "$INPUT" "$1"; }
TRANSCRIPT=$(read_json transcript_path); TRIGGER=$(read_json trigger); CWD=$(read_json cwd)
cd "${CWD:-${CLAUDE_PROJECT_DIR:-.}}" 2>/dev/null || exit 0
# .crew/crew.json alone is enough for the T-0006 PreCompact record below
# (/crew:migrate may retire .crew/config.json); the transcript copy and the
# skeleton handoff further down still need .crew/config.json, as before.
[ -f .crew/config.json ] || [ -f .crew/crew.json ] || exit 0

# No hook_once claim here on purpose: PreCompact can fire more than once per
# session, and both writes below are idempotent (the transcript copy is
# timestamped, the handoff skeleton only gets written if one doesn't already
# exist) -- duplication is safe, suppression of the only handoff is not.
#
# The per-EVENT claim is a different thing: on Windows both flavours run for
# ONE PreCompact, and "idempotent" held only when they did not overlap -- two
# transcript copies in one second race one name, and two skeleton writers can
# both see no handoff. event_claim.py lets exactly one flavour write for this
# event, keyed on the payload, so the next compaction is a new event. Exit 10
# is the only "the other flavour has it"; anything else writes. A token back
# means this flavour holds the claim and reports "sent" once both writes are
# done; until then the twin waits, and takes over if this process dies.
CLAIM_TOKEN=""
CLAIM_SCRIPT="$(dirname "${BASH_SOURCE[0]}")/event_claim.py"
if CLAIM_PY=$(crew_py_strict); then
  CLAIM_TOKEN=$(printf '%s' "$INPUT" | "$CLAIM_PY" "$CLAIM_SCRIPT" handoff-write . sh); [ $? -eq 10 ] && exit 0
fi

# T-0006: record how this compaction started, keyed on the session, so a
# SessionStart `compact` may auto-resume only after a typed /compact (an
# automatic one can continue the in-flight turn). crew_resume.py writes it
# from the raw payload, so both flavours record the same thing. No python,
# no record -- and no record means the compact waits, which is the safe side.
# The previous record for this session is removed FIRST, in plain shell, so a
# compact whose own record never lands (no python, a failed write) cannot
# inherit an earlier `manual`. The session id is read with sed because python
# may be the thing that is missing; an unreadable one removes every record.
PRECOMPACT_SID=$(printf '%s' "$INPUT" | sed -n 's/.*"session_id"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -n 1)
PRECOMPACT_KEY="${PRECOMPACT_SID//[^A-Za-z0-9_-]/_}"
PRECOMPACT_KEY="${PRECOMPACT_KEY:0:100}"
PRECOMPACT_COMMON=$(git rev-parse --git-common-dir 2>/dev/null)
PRECOMPACT_DIR="${PRECOMPACT_COMMON:+$PRECOMPACT_COMMON/crew}"
PRECOMPACT_DIR="${PRECOMPACT_DIR:-.work/crew}"
if [ -n "$PRECOMPACT_KEY" ]; then
  rm -f "$PRECOMPACT_DIR/precompact-$PRECOMPACT_KEY.json" 2>/dev/null
else
  rm -f "$PRECOMPACT_DIR"/precompact-*.json 2>/dev/null
fi
if [ -n "${CLAIM_PY:-}" ]; then
  printf '%s' "$INPUT" | "$CLAIM_PY" "$(dirname "${BASH_SOURCE[0]}")/crew_resume.py" precompact --root . >/dev/null 2>&1
fi
if [ ! -f .crew/config.json ]; then
  # A crew.json-only repo: the record above is all this hook does there.
  [ -z "$CLAIM_TOKEN" ] || "$CLAIM_PY" "$CLAIM_SCRIPT" --sent "$CLAIM_TOKEN" >/dev/null 2>&1
  exit 0
fi

mkdir -p .crew/transcripts .work
# Whether either write below actually landed. Codex r1 finding 2: this used
# to mark the claim "sent" unconditionally, so a write that silently failed
# (a bad handoffPath, a full disk) suppressed the PowerShell twin's retry --
# the twin sees "sent", stands down, and the handoff is lost for good. A
# failure here must leave the claim unmarked so the twin (or a later run of
# this same flavour) can still take over and try again.
FAILED=0
if [ -f "$TRANSCRIPT" ]; then
  DEST=".crew/transcripts/$(date +%Y%m%d-%H%M%S)-${TRIGGER:-auto}.jsonl"
  cp "$TRANSCRIPT" "$DEST" 2>/dev/null
  [ -f "$DEST" ] || FAILED=1
  KEEP=5
  if PY=$(crew_py); then
    K=$("$PY" -c 'import json;print(json.load(open(".crew/config.json")).get("context",{}).get("keepTranscripts",5))' 2>/dev/null)
    case "$K" in ''|*[!0-9]*) ;; *) KEEP="$K" ;; esac
  fi
  ls -1t .crew/transcripts/*.jsonl 2>/dev/null | tail -n +$((KEEP+1)) | xargs -r rm -f
fi

PY=$(crew_py) && HANDOFF=$("$PY" -c 'import json;print(json.load(open(".crew/config.json")).get("context",{}).get("handoffPath",".work/HANDOFF.md"))' 2>/dev/null)
HANDOFF="${HANDOFF:-.work/HANDOFF.md}"

# If no handoff exists, write a factual skeleton from the repo, not from memory.
if [ ! -f "$HANDOFF" ]; then
  {
    echo "# Handoff"
    echo "written: $(date -u +%Y-%m-%dT%H:%M:%SZ) (auto, at ${TRIGGER:-auto} compact)"
    echo "branch: $(git rev-parse --abbrev-ref HEAD 2>/dev/null)"
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
  } > "$HANDOFF" 2>/dev/null
  [ -f "$HANDOFF" ] || FAILED=1
fi
[ -z "$CLAIM_TOKEN" ] || [ "$FAILED" = 1 ] || "$CLAIM_PY" "$CLAIM_SCRIPT" --sent "$CLAIM_TOKEN" >/dev/null 2>&1
exit 0

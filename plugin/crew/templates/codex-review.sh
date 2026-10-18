#!/usr/bin/env bash
# codex-review.sh - the Codex host wrapper, shipped by crew (L-0813).
#
#   codex-review.sh <prompt_file> <out_file> [repo_dir]
#
# Runs one read-only `codex exec` review of the prompt in <prompt_file> inside
# <repo_dir> (default: the current directory) and writes Codex's final message
# to <out_file>. Installed by `crew_codex_wrapper.py install` to
# ${CLAUDE_CONFIG_DIR:-$HOME/.claude}/hooks/codex-review.sh, where review
# harnesses that wrap Codex look for it.
#
# What it guarantees, in code rather than in a brief:
#   - stdin to codex is the prompt FILE, so it carries EOF (an inherited open
#     stdin hangs `codex exec` forever, looking like slow analysis)
#   - --skip-git-repo-check, so directory validation cannot stall the run
#   - each attempt is capped at CODEX_REVIEW_TIMEOUT seconds (default 1200,
#     20 minutes); a hung attempt is killed and restarted ONCE
#   - <out_file> is deleted before each attempt and must exist, be non-empty and
#     be at least as new as the attempt, so a stale file from an earlier run is
#     never read as this run's answer
#   - every attempt is logged to CODEX_REVIEW_LOG
#     (default ${CLAUDE_CONFIG_DIR:-$HOME/.claude}/codex-review.log)
#
# On success the last stderr line is
#   codex-review: OK - final message N bytes -> OUT (model: M, reasoning effort: E, attempt A)
# M and E are read from the header codex printed. When codex printed no header
# the parenthesis is left out: an unknown model is never filled in.
#
# Exit: 0 reviewed - 2 usage - 3 no usable review after both attempts.
#
# Optional environment: CODEX_BIN (default codex), CODEX_MODEL, CODEX_EFFORT,
# CODEX_PROFILE (passed as --profile), CODEX_REVIEW_TIMEOUT, CODEX_REVIEW_LOG.
set -u

die() { echo "codex-review: $*" >&2; exit 2; }

[ $# -ge 2 ] && [ $# -le 3 ] || die "usage: codex-review.sh <prompt_file> <out_file> [repo_dir]"
PROMPT=$1
OUT=$2
REPO=${3:-$PWD}

[ -f "$PROMPT" ] && [ -r "$PROMPT" ] || die "prompt file not readable: $PROMPT"
[ -s "$PROMPT" ] || die "prompt file is empty: $PROMPT"
[ -d "$REPO" ] || die "repo_dir is not a directory: $REPO"
case "$PROMPT" in /*) ;; *) PROMPT="$PWD/$PROMPT" ;; esac
case "$OUT" in /*) ;; *) OUT="$PWD/$OUT" ;; esac
mkdir -p "$(dirname "$OUT")" || die "cannot create the directory of $OUT"

CODEX=${CODEX_BIN:-codex}
command -v "$CODEX" >/dev/null 2>&1 || die "codex is not on PATH ($CODEX)"
CAP=${CODEX_REVIEW_TIMEOUT:-1200}
case "$CAP" in ''|*[!0-9]*) die "CODEX_REVIEW_TIMEOUT must be whole seconds, got '$CAP'" ;; esac
LOG=${CODEX_REVIEW_LOG:-${CLAUDE_CONFIG_DIR:-$HOME/.claude}/codex-review.log}
mkdir -p "$(dirname "$LOG")" 2>/dev/null || true

log() { printf '%s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*" >>"$LOG" 2>/dev/null || true; }

TIMEOUT=()
if command -v timeout >/dev/null 2>&1; then
  TIMEOUT=(timeout "$CAP")
else
  log "no timeout(1) on this host: the ${CAP}s cap is NOT enforced"
  echo "codex-review: WARNING no timeout(1) on this host; the ${CAP}s cap is not enforced" >&2
fi

ARGS=(exec --skip-git-repo-check --sandbox read-only -C "$REPO")
[ -n "${CODEX_PROFILE:-}" ] && ARGS+=(--profile "$CODEX_PROFILE")
[ -n "${CODEX_MODEL:-}" ] && ARGS+=(-m "$CODEX_MODEL")
[ -n "${CODEX_EFFORT:-}" ] && ARGS+=(-c "model_reasoning_effort=\"$CODEX_EFFORT\"")

RUN=$(mktemp -d "${TMPDIR:-/tmp}/codex-review-XXXXXX") || die "mktemp failed"
trap 'rm -rf "$RUN"' EXIT

attempt=0
while [ "$attempt" -lt 2 ]; do
  attempt=$((attempt + 1))
  rm -f "$OUT"
  START=$(date +%s)
  : >"$RUN/stamp"
  log "attempt $attempt: $CODEX exec in $REPO (prompt $PROMPT, cap ${CAP}s)"
  ${TIMEOUT[@]+"${TIMEOUT[@]}"} "$CODEX" "${ARGS[@]}" -o "$OUT" - <"$PROMPT" >"$RUN/stdout.$attempt" 2>"$RUN/stderr.$attempt"
  rc=$?
  cat "$RUN/stderr.$attempt" "$RUN/stdout.$attempt" >"$RUN/all.$attempt" 2>/dev/null
  if [ "$rc" -eq 124 ]; then
    log "attempt $attempt: killed after ${CAP}s (hung, not working)"
    echo "codex-review: attempt $attempt hit the ${CAP}s cap" >&2
    continue
  fi
  if [ "$rc" -ne 0 ]; then
    log "attempt $attempt: codex exited $rc: $(tail -n 3 "$RUN/all.$attempt" | tr '\n' ' ')"
    echo "codex-review: attempt $attempt: codex exited $rc" >&2
    continue
  fi
  if [ ! -s "$OUT" ]; then
    log "attempt $attempt: codex exited 0 but wrote no final message"
    echo "codex-review: attempt $attempt: exit 0 but no final message" >&2
    continue
  fi
  if [ "$OUT" -ot "$RUN/stamp" ]; then
    log "attempt $attempt: final message is older than the attempt (stale)"
    echo "codex-review: attempt $attempt: stale final message" >&2
    rm -f "$OUT"
    continue
  fi
  MODEL=$(sed -n 's/^model: *\([^ ]*\) *$/\1/p' "$RUN/all.$attempt" | tail -n 1)
  EFFORT=$(sed -n 's/^reasoning effort: *\([^ ]*\) *$/\1/p' "$RUN/all.$attempt" | tail -n 1)
  BYTES=$(wc -c <"$OUT" | tr -d ' ')
  DETAIL=""
  if [ -n "$MODEL" ] && [ -n "$EFFORT" ]; then
    DETAIL=" (model: $MODEL, reasoning effort: $EFFORT, attempt $attempt)"
  fi
  log "attempt $attempt: OK $BYTES bytes in $(( $(date +%s) - START ))s${DETAIL}"
  echo "codex-review: OK - final message $BYTES bytes -> $OUT$DETAIL" >&2
  exit 0
done

rm -f "$OUT"
log "FAILED after $attempt attempts"
echo "codex-review: FAILED - no usable review after $attempt attempts (log: $LOG)" >&2
exit 3

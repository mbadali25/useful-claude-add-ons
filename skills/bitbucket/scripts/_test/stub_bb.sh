#!/usr/bin/env bash
# Fixture transport that stands in for bb.sh. No network, no credentials, no
# config - merge_gate.sh calls whatever BB_CMD names, so pointing it here runs
# the real decision logic against canned responses.
#
# Environment:
#   STUB_DIR - holds the canned responses
#   STUB_LOG - every call is appended as: METHOD<TAB>path<TAB>body
#
# Response lookup for call number N (1-based, counted in $STUB_DIR/.n):
#   body:   $STUB_DIR/N.body   -> $STUB_DIR/<METHOD>.body   -> '{}'
#   status: $STUB_DIR/N.status -> $STUB_DIR/<METHOD>.status -> 200
# A status >= 400 prints `HTTP <code>` on stderr and exits 1, which is what
# bb.sh does.
set -uo pipefail

: "${STUB_DIR:?stub_bb.sh needs STUB_DIR}"
: "${STUB_LOG:?stub_bb.sh needs STUB_LOG}"

METHOD="${1:?stub_bb.sh METHOD path [body]}"
REQ_PATH="${2:?stub_bb.sh METHOD path [body]}"
REQ_BODY="${3:-}"

N_FILE="$STUB_DIR/.n"
n=0
[ -f "$N_FILE" ] && n="$(cat "$N_FILE")"
n=$((n + 1))
printf '%s' "$n" > "$N_FILE"

printf '%s\t%s\t%s\n' "$METHOD" "$REQ_PATH" "$REQ_BODY" >> "$STUB_LOG"

pick() { # <suffix> -> the file to use, or empty
  if [ -f "$STUB_DIR/$n.$1" ]; then printf '%s' "$STUB_DIR/$n.$1"
  elif [ -f "$STUB_DIR/$METHOD.$1" ]; then printf '%s' "$STUB_DIR/$METHOD.$1"
  fi
}

body_file="$(pick body)"
if [ -n "$body_file" ]; then cat "$body_file"; else echo '{}'; fi

status=200
status_file="$(pick status)"
[ -n "$status_file" ] && status="$(cat "$status_file")"

if [ "$status" -ge 400 ]; then
  echo "HTTP $status" >&2
  exit 1
fi
exit 0

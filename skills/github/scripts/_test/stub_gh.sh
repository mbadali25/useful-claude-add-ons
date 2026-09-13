#!/usr/bin/env bash
# Fixture transport that stands in for the `gh` CLI. No network, no credentials,
# no config - merge_gate.sh calls whatever GH_CMD names, so pointing it here runs
# the real decision logic against canned responses.
#
# It is invoked exactly as merge_gate.sh invokes gh:
#   gh api -i -X METHOD -H ... [--input -] <path>
# so the method and the path are recovered from argv, and a request body is read
# from stdin. Anything that changes how merge_gate.sh shells out to gh breaks
# this parse loudly rather than silently passing.
#
# Environment:
#   STUB_DIR - holds the canned responses
#   STUB_LOG - every call is appended as: METHOD<TAB>path<TAB>body
#
# Response lookup for call number N (1-based, counted in $STUB_DIR/.n):
#   body:    $STUB_DIR/N.body    -> $STUB_DIR/<METHOD>.body    -> '{}'
#   status:  $STUB_DIR/N.status  -> $STUB_DIR/<METHOD>.status  -> 200
#   headers: $STUB_DIR/N.headers -> $STUB_DIR/<METHOD>.headers -> none
# Output mimics `gh api -i`: a status line, headers, a blank line, then the body.
# A status >= 400 also exits 1, which is what gh does.
set -uo pipefail

: "${STUB_DIR:?stub_gh.sh needs STUB_DIR}"
: "${STUB_LOG:?stub_gh.sh needs STUB_LOG}"

METHOD="GET"
REQ_PATH=""
WANT_INPUT=0
saw_api=0

while [ "$#" -gt 0 ]; do
  case "$1" in
    api) saw_api=1; shift ;;
    -i|--include) shift ;;
    -X|--method) METHOD="${2:?-X needs a value}"; shift 2 ;;
    -H|--header) shift 2 ;;
    --input) WANT_INPUT=1; shift 2 ;;
    -*) shift ;;
    *) REQ_PATH="$1"; shift ;;
  esac
done

[ "$saw_api" -eq 1 ] || { echo "stub_gh.sh: expected 'gh api ...', got something else" >&2; exit 64; }
[ -n "$REQ_PATH" ] || { echo "stub_gh.sh: no path in argv" >&2; exit 64; }

REQ_BODY=""
[ "$WANT_INPUT" -eq 1 ] && REQ_BODY="$(cat)"

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

status=200
status_file="$(pick status)"
[ -n "$status_file" ] && status="$(cat "$status_file")"

printf 'HTTP/2.0 %s Stub\r\n' "$status"
printf 'Content-Type: application/json; charset=utf-8\r\n'
headers_file="$(pick headers)"
[ -n "$headers_file" ] && cat "$headers_file"
printf '\r\n'

body_file="$(pick body)"
if [ -n "$body_file" ]; then cat "$body_file"; else echo '{}'; fi

[ "$status" -ge 400 ] && exit 1
exit 0

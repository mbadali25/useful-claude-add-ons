#!/usr/bin/env bash
#
# Stop-time completion scope audit. Thin wrapper: the decision lives in
# completion_audit.py (0 lines on pass, <= 6 on fail, exit 2 blocks the Stop).
# `stop_hook_active` is honoured in python, and here too, so a continuation
# the audit caused is never blocked again even if python is broken.
#
# Any python status other than 0 or 2, or no python at all, means nothing was
# audited. That blocks unless .crew/config.json PROVABLY sets `scope.mode` to
# off -- and blocks at most ONCE IN A ROW per session and project (a marker
# file, below), so a python that stays broken can never loop the Stop.
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
. "$DIR/_common.sh"

INPUT=$(cat)
# BYTE-FOR-BYTE the copy in scope-guard.sh (asserted by the tests).
# True only when `.crew/config.json` PROVABLY leaves the scope hooks off: the
# file is absent, or it is one JSON object (crudely: starts `{`, ends `}`,
# braces balance) with exactly one "scope" key, whose object has exactly one
# "mode", and that mode is "off". Crude on purpose -- it runs only when python
# could not, so it cannot parse JSON -- and every shape it cannot prove is NOT
# off: corrupt, an unknown mode, report, auto, block, or no scope key at all.
_scope_provably_off() {
  local cfg="${CLAUDE_PROJECT_DIR:-$PWD}/.crew/config.json" text obj
  [ -e "$cfg" ] || [ -L "$cfg" ] || return 0
  { [ -f "$cfg" ] && [ -r "$cfg" ]; } || return 1
  text=$(tr -d '\r\n' < "$cfg") || return 1
  text=${text#$'\xef\xbb\xbf'}
  text=$(printf '%s' "$text" | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//')
  case "$text" in '{'*'}') ;; *) return 1 ;; esac
  [ "$(printf '%s' "$text" | tr -cd '{' | wc -c)" -eq \
    "$(printf '%s' "$text" | tr -cd '}' | wc -c)" ] || return 1
  [ "$(printf '%s' "$text" | grep -o '"scope"' | wc -l)" -eq 1 ] || return 1
  obj=$(printf '%s' "$text" | sed -n 's/.*"scope"[[:space:]]*:[[:space:]]*\({[^{}]*}\).*/\1/p')
  [ -n "$obj" ] || return 1
  [ "$(printf '%s' "$obj" | grep -o '"mode"' | wc -l)" -eq 1 ] || return 1
  printf '%s' "$obj" | grep -Eq '"mode"[[:space:]]*:[[:space:]]*"off"'
}

# One marker per session and project, in the temp directory. Its presence
# means the previous Stop was blocked because nothing could be audited.
_marker() {
  local sid proj
  sid=$(printf '%s' "$INPUT" | tr -d '\r\n' \
    | sed -n 's/.*"session_id"[[:space:]]*:[[:space:]]*"\([A-Za-z0-9._-]\{1,128\}\)".*/\1/p')
  proj=$(printf '%s' "${CLAUDE_PROJECT_DIR:-$PWD}" | cksum | cut -d' ' -f1)
  printf '%s/crew-completion-audit.%s-%s' "${TMPDIR:-/tmp}" "${sid:-nosession}" "$proj"
}

# Block this Stop -- unless the previous one was already blocked for the same
# reason, or the marker cannot be written (then a block could repeat forever).
_block_once() {
  local marker
  marker=$(_marker)
  if [ -e "$marker" ]; then
    rm -f "$marker"
    echo "completion audit: $1 Not blocking again: the previous stop was already blocked for this." >&2
    exit 0
  fi
  if ! : > "$marker" 2>/dev/null; then
    echo "completion audit: $1 Not blocking: no marker could be written, so a block could loop." >&2
    exit 0
  fi
  echo "COMPLETION AUDIT: $1" >&2
  exit 2
}

# Any JSON whitespace around the colon, newlines included: collapse line
# breaks first, then allow spaces and tabs. A continuation is never blocked,
# and it ends the "blocked once" count, so the next real turn is audited.
if printf '%s' "$INPUT" | tr -d '\r\n' \
    | grep -Eq '"stop_hook_active"[[:space:]]*:[[:space:]]*true'; then
  rm -f "$(_marker)" 2>/dev/null
  exit 0
fi

PY=$(crew_py_strict) || {
  if _scope_provably_off; then
    echo "completion audit: no usable python - not audited (scope.mode is off)." >&2
    exit 0
  fi
  _block_once "no usable python - the tree was not audited against the ticket's scope."
}

printf '%s' "$INPUT" | PYTHONUTF8=1 PYTHONIOENCODING=utf-8 "$PY" "$DIR/completion_audit.py"
status=$?

if [ "$status" -ne 0 ] && [ "$status" -ne 2 ]; then
  if _scope_provably_off; then
    echo "completion audit: completion_audit.py did not run to a verdict (exit $status); not audited (scope.mode is off)." >&2
    exit 0
  fi
  _block_once "completion_audit.py did not run to a verdict (exit $status); nothing was audited."
fi
# Python reached a verdict, so the next failure to run starts a fresh count.
rm -f "$(_marker)" 2>/dev/null
exit "$status"

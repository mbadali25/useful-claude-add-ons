#!/usr/bin/env bash
. "$(dirname "${BASH_SOURCE[0]}")/_common.sh"
# Outbound-only notifier. Never reads from chat, never accepts instructions.
# A thin wrapper: every rule (config layering, the event filter, dedupe,
# Telegram/Teams, the message line) lives in crew_notify.py, once for both
# shells. Kept here: the one-sender election between this and notify.ps1.
# Usage: notify.sh hook                      (the Notification hook; payload on stdin)
#        notify.sh <event> <reason> [--outcome pass|fail]   (a direct call)
#   events: deploy | question; blocker is reserved until T-0060. The pre-1.0
#   names (gate, waiting, phase, review, done) are mapped by crew_notify.py.
cd "${CLAUDE_PROJECT_DIR:-.}" || exit 0
MODE="${1:-}"
CREW_PY=$(crew_py) || exit 0
[ -n "$CREW_PY" ] || exit 0
NOTIFY_PY="$(dirname "${BASH_SOURCE[0]}")/crew_notify.py"

if [ "$MODE" != "hook" ]; then
  # A command calling this by hand passes no payload, is not a hook event and
  # has no twin to race: no claim.
  [ -n "$MODE" ] || exit 0
  EVENT="$1"; REASON="${2:-}"; shift 2 2>/dev/null || shift $#
  "$CREW_PY" "$NOTIFY_PY" send --root . --event "$EVENT" --reason "$REASON" "$@" </dev/null
  exit 0
fi

# The payload is kept as BYTES in a file, never a shell variable: event_claim.py
# hashes it, the PowerShell twin hands it the bytes as received, and $(cat)
# would drop trailing newlines and make the twins disagree about the event.
[ -t 0 ] && exit 0
PAYLOAD_FILE=$(mktemp 2>/dev/null) || exit 0
trap 'rm -f "$PAYLOAD_FILE"' EXIT
cat > "$PAYLOAD_FILE"

# No hook_once claim here on purpose: Notification can fire many times per
# session. The per-EVENT claim is a different thing: on Windows both flavours
# of this hook run for one Notification, and event_claim.py lets exactly one
# of them send it (keyed on the payload, so the next Notification is new).
# Exit 10 is the only "the other flavour has it"; anything else sends.
CLAIM_TOKEN=""
CLAIM_SCRIPT="$(dirname "${BASH_SOURCE[0]}")/event_claim.py"
if [ -s "$PAYLOAD_FILE" ] && CLAIM_PY=$(crew_py_strict); then
  CLAIM_TOKEN=$("$CLAIM_PY" "$CLAIM_SCRIPT" notify . sh < "$PAYLOAD_FILE"); [ $? -eq 10 ] && exit 0
fi
claim_sent() { [ -z "$CLAIM_TOKEN" ] || "$CLAIM_PY" "$CLAIM_SCRIPT" --sent "$CLAIM_TOKEN" >/dev/null 2>&1; }

# crew_notify.py owns retries and its own dedupe, so the claim is reported
# "sent" whatever it answered: a claim left open only makes the twin re-send.
"$CREW_PY" "$NOTIFY_PY" hook --root . < "$PAYLOAD_FILE"
claim_sent
exit 0

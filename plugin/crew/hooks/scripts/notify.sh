#!/usr/bin/env bash
# Outbound-only notifier. Never reads from chat, never accepts instructions.
# Usage: notify.sh <event> <one-line message>
#   events: phase | gate | review | waiting | done
cd "${CLAUDE_PROJECT_DIR:-.}" || exit 0
EVENT="${1:-info}"; shift 2>/dev/null; MSG="$*"
[ -f .crew/config.json ] || exit 0

# No hook_once claim here on purpose: Notification can fire many times per
# session, and a duplicate ping is a safe failure -- a suppressed one is not.

read_cfg() { python3 - "$1" << 'PY' 2>/dev/null
import json,sys
try: c=json.load(open(".crew/config.json")).get("notify",{})
except Exception: sys.exit(0)
k=sys.argv[1]
v=c
for part in k.split("."):
    if not isinstance(v,dict): sys.exit(0)
    v=v.get(part)
if isinstance(v,list): print(",".join(map(str,v)))
elif v is not None: print(v)
PY
}

PROVIDER=$(read_cfg provider); [ -z "$PROVIDER" ] || [ "$PROVIDER" = "none" ] && exit 0
EVENTS=$(read_cfg events)
case ",$EVENTS," in *",$EVENT,"*) ;; *) [ -n "$EVENTS" ] && exit 0 ;; esac

REPO=$(basename "$(git rev-parse --show-toplevel 2>/dev/null || pwd)")
BRANCH=$(git branch --show-current 2>/dev/null)

# One line. No diffs, no findings text, no ticket bodies, no secrets.
# A chat channel is a less controlled place than the repo; keep payloads dull.
TEXT="[$REPO${BRANCH:+/$BRANCH}] $EVENT: ${MSG:0:280}"

case "$PROVIDER" in
  teams)
    URL_ENV=$(read_cfg urlEnv); URL="${!URL_ENV}"
    [ -z "$URL" ] && { echo "notify: \$$URL_ENV not set" >&2; exit 0; }
    curl -sS -m 10 -X POST "$URL" -H 'Content-Type: application/json' \
      -d "$(python3 -c 'import json,sys;print(json.dumps({"type":"message","attachments":[{"contentType":"application/vnd.microsoft.card.adaptive","content":{"type":"AdaptiveCard","version":"1.4","body":[{"type":"TextBlock","text":sys.argv[1],"wrap":True}]}}]}))' "$TEXT")" >/dev/null
    ;;
  telegram)
    TOK_ENV=$(read_cfg tokenEnv); TOK="${!TOK_ENV}"
    CHAT=$(read_cfg chatId)
    [ -z "$TOK" ] || [ -z "$CHAT" ] && { echo "notify: telegram token or chatId missing" >&2; exit 0; }
    curl -sS -m 10 -X POST "https://api.telegram.org/bot${TOK}/sendMessage" \
      --data-urlencode "chat_id=${CHAT}" --data-urlencode "text=${TEXT}" \
      --data-urlencode "disable_notification=$([ "$EVENT" = "waiting" ] && echo false || echo true)" >/dev/null
    ;;
esac
exit 0

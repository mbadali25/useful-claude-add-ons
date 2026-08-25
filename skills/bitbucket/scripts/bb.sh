#!/usr/bin/env bash
# bb.sh - minimal Bitbucket Cloud REST API 2.0 wrapper
# Usage:
#   bb.sh GET  "repositories/{workspace}/{repo}/pullrequests?state=OPEN"
#   bb.sh POST "repositories/{workspace}/{repo}/pullrequests" '{"title":"..."}'
#   bb.sh PUT|DELETE <path> [json-body]
#
# Auth: Basic auth with Atlassian account email + API token (scoped).
# Requires: BITBUCKET_EMAIL, BITBUCKET_API_TOKEN
set -euo pipefail

if [[ -z "${BITBUCKET_EMAIL:-}" || -z "${BITBUCKET_API_TOKEN:-}" ]]; then
  echo "ERROR: set BITBUCKET_EMAIL and BITBUCKET_API_TOKEN first." >&2
  echo "Create a token: Atlassian account settings > Security > Create API token with scopes (app: Bitbucket)." >&2
  exit 1
fi

METHOD="${1:?usage: bb.sh METHOD path [json-body]}"
PATH_PART="${2:?usage: bb.sh METHOD path [json-body]}"
BODY="${3:-}"

BASE="https://api.bitbucket.org/2.0"
URL="${BASE}/${PATH_PART#/}"

ARGS=(
  --silent --show-error
  --write-out '\n%{http_code}'
  --request "$METHOD"
  --user "${BITBUCKET_EMAIL}:${BITBUCKET_API_TOKEN}"
  --header "Accept: application/json"
)

if [[ -n "$BODY" ]]; then
  ARGS+=(--header "Content-Type: application/json" --data "$BODY")
fi

RESPONSE="$(curl "${ARGS[@]}" "$URL")"
HTTP_CODE="$(tail -n1 <<<"$RESPONSE")"
JSON="$(sed '$d' <<<"$RESPONSE")"

if command -v jq >/dev/null 2>&1 && [[ -n "$JSON" ]]; then
  echo "$JSON" | jq . 2>/dev/null || echo "$JSON"
else
  echo "$JSON"
fi

if [[ "$HTTP_CODE" -ge 400 ]]; then
  echo "HTTP $HTTP_CODE" >&2
  case "$HTTP_CODE" in
    401) echo "Hint: check BITBUCKET_EMAIL (must be Atlassian account email, not username) and token validity/expiry." >&2 ;;
    403) echo "Hint: token likely missing a required scope for this endpoint." >&2 ;;
    410) echo "Hint: app-password era credential - replace with an API token." >&2 ;;
  esac
  exit 1
fi

#!/usr/bin/env bash

# Native Windows (no POSIX layer) runs the .ps1 twin instead; stand down here.
case "$(uname -s 2>/dev/null)" in MINGW*|MSYS*|CYGWIN*) exit 0 ;; esac

# Deterministic command guard. Exit 2 blocks and returns the message to Claude.
INPUT=$(cat)
if command -v jq >/dev/null 2>&1; then
  CMD=$(echo "$INPUT" | jq -r '.tool_input.command // empty' 2>/dev/null)
else
  CMD=$(echo "$INPUT" | python3 -c 'import sys,json;print(json.load(sys.stdin).get("tool_input",{}).get("command",""))' 2>/dev/null)
fi
[ -z "$CMD" ] && exit 0
block() { echo "BLOCKED: $1" >&2; exit 2; }

# --- destructive operations ----------------------------------------------
echo "$CMD" | grep -qE '\bterraform[[:space:]]+(apply|destroy)' && block "terraform apply/destroy is manual. Run plan and show it."
echo "$CMD" | grep -qiE '\b(DROP|TRUNCATE)[[:space:]]+(TABLE|DATABASE|SCHEMA)' && block "destructive DDL. Write a migration with a rollback."
echo "$CMD" | grep -qE '\bgit[[:space:]]+push\b.*(--force|-f)\b' && block "force push."
echo "$CMD" | grep -qE '\bgit[[:space:]]+(reset[[:space:]]+--hard|clean[[:space:]]+-[a-z]*f)' && block "destroys uncommitted work."
echo "$CMD" | grep -qE '\brm[[:space:]]+-[a-z]*rf?[[:space:]]+/' && block "recursive delete from root."
if echo "$CMD" | grep -qiE '(prod|production)'; then
  echo "$CMD" | grep -qiE '\b(psql|mysql|sqlcmd|mongo|az |aws |gcloud )' && block "command targets production."
fi

# --- secrets: never let VALUES reach the transcript -----------------------
# Retrieving a secret is fine. Printing it is not: the value lands in context,
# in the on-disk session transcript, and in every later summary of it.
SECRET_READ='(secretsmanager[[:space:]]+get-secret-value|ssm[[:space:]]+get-parameter|keyvault[[:space:]]+secret[[:space:]]+show|vault[[:space:]]+kv[[:space:]]+get|kubectl[[:space:]]+get[[:space:]]+secret)'
if echo "$CMD" | grep -qiE "$SECRET_READ"; then
  if ! echo "$CMD" | grep -qE '(^|[[:space:]])(export|env)[[:space:]]|>[[:space:]]*[^|&]|\|[[:space:]]*(tee|xargs)'; then
    block "this prints a secret value into the transcript. Capture it instead, e.g. export DB_PASS=\$(aws secretsmanager get-secret-value --secret-id NAME --query SecretString --output text)"
  fi
fi
echo "$CMD" | grep -qiE '\b(cat|echo|printf|less|more|head|tail)\b[^|]*\.env(\.[a-z]+)?([[:space:]]|$)' && block "prints a .env file. Reference variable names, never values."
exit 0

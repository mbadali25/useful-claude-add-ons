#!/usr/bin/env bash

. "$(dirname "${BASH_SOURCE[0]}")/_common.sh"

# Deterministic command guard. Exit 2 blocks and returns the message to Claude.
INPUT=$(cat)
crew_tool_dispatch guard.ps1 "$INPUT"   # PowerShell tool -> PowerShell rules
if command -v jq >/dev/null 2>&1; then
  CMD=$(echo "$INPUT" | jq -r '.tool_input.command // empty' 2>/dev/null)
elif PY=$(crew_py); then
  CMD=$(echo "$INPUT" | "$PY" -c 'import sys,json;print(json.load(sys.stdin).get("tool_input",{}).get("command",""))' 2>/dev/null)
else
  echo "crew guard: no jq and no python - the command guard cannot run" >&2
  exit 0
fi
CMD=$(crew_strip_cr "$CMD")
[ -z "$CMD" ] && exit 0
block() { echo "BLOCKED: $1" >&2; exit 2; }

# --- destructive operations ----------------------------------------------
echo "$CMD" | grep -qE '\bterraform[[:space:]]+(apply|destroy)' && block "terraform apply/destroy is manual. Run plan and show it."
echo "$CMD" | grep -qiE '\b(DROP|TRUNCATE)[[:space:]]+(TABLE|DATABASE|SCHEMA)' && block "destructive DDL. Write a migration with a rollback."
echo "$CMD" | grep -qE '\bgit[[:space:]]+push\b.*(--force|-f)\b' && block "force push."
echo "$CMD" | grep -qE '\bgit[[:space:]]+(reset[[:space:]]+--hard|clean[[:space:]]+-[a-z]*f)' && block "destroys uncommitted work."
echo "$CMD" | grep -qE '\brm[[:space:]]+-[a-z]*rf?[[:space:]]+/' && block "recursive delete from root."
# Whole-token match. A substring match blocks "s3://my-product-images",
# "reproducible-builds" and "select * from products", which trains you to
# work around the guard - and a guard people route around is not a guard.
if echo "$CMD" | grep -qiE '(^|[^[:alnum:]])(prod|production)([^[:alnum:]]|$)'; then
  echo "$CMD" | grep -qiE '(^|[^[:alnum:]])(psql|mysql|sqlcmd|mongo|az|aws|gcloud)([^[:alnum:]]|$)' \
    && block "command targets production. If this is not production, rename the argument or run it yourself."
fi

# --- secrets: never let VALUES reach the transcript -----------------------
# Retrieving a secret is fine. Printing it is not: the value lands in context,
# in the on-disk session transcript, and in every later summary of it.
SECRET_READ='(secretsmanager[[:space:]]+get-secret-value|ssm[[:space:]]+get-parameter|keyvault[[:space:]]+secret[[:space:]]+show|vault[[:space:]]+kv[[:space:]]+get|kubectl[[:space:]]+get[[:space:]]+secret)'
if echo "$CMD" | grep -qiE "$SECRET_READ"; then
  # Writing a secret to a file is worse than printing one, not an exemption:
  # the transcript can at least be deleted, a file on disk gets committed.
  echo "$CMD" | grep -qE '>[[:space:]]*[^|&[:space:]]' \
    && block "this writes a secret value to a file. Capture it into a variable instead: DB_PASS=\$(...)"
  echo "$CMD" | grep -qE '\|[[:space:]]*(tee|xargs)' \
    && block "this pipes a secret value to tee/xargs, which both prints and persists it. Capture it into a variable instead: DB_PASS=\$(...)"

  # The one safe shape: assign the output to a shell variable, so the value
  # is never rendered. VAR=$(...) or export VAR=$(...).
  if ! echo "$CMD" | grep -qE '(^|[[:space:]]|;)(export[[:space:]]+)?[A-Za-z_][A-Za-z0-9_]*=["]?([$][(]|[`])'; then
    block "this prints a secret value into the transcript. Capture it instead, e.g. DB_PASS=\$(aws secretsmanager get-secret-value --secret-id NAME --query SecretString --output text)"
  fi
fi
echo "$CMD" | grep -qiE '\b(cat|echo|printf|less|more|head|tail)\b[^|]*\.env(\.[a-z]+)?([[:space:]]|$)' && block "prints a .env file. Reference variable names, never values."
exit 0

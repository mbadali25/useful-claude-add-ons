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
# TF_PRE is GIT_PRE's reason applied to the neighbour that never got it:
# `terraform -chdir=infra apply` sailed through a rule that required `apply` to
# sit immediately after `terraform`, while the git rules eleven lines below had
# already been fixed for exactly that shape. Re-review the fix to a guard as
# hard as the guard: the sibling rule was the one still broken.
TF_PRE='\bterraform([[:space:]]+-[^[:space:]]+)*[[:space:]]+'
echo "$CMD" | grep -qE "${TF_PRE}(apply|destroy)" && block "terraform apply/destroy is manual. Run plan and show it."
echo "$CMD" | grep -qiE '\b(DROP|TRUNCATE)[[:space:]]+(TABLE|DATABASE|SCHEMA)' && block "destructive DDL. Write a migration with a rollback."
# The git rules used to require the subcommand to sit immediately after `git`,
# so every one of them was bypassed by the option forms people actually use in
# a worktree-per-agent setup: `git -C /path push --force`, `git -c a=b push -f`,
# `git --git-dir=... reset --hard`. GIT_PRE swallows any run of leading git
# options (each optionally followed by its value token) between `git` and the
# subcommand, so the rule matches the command rather than one spelling of it.
GIT_PRE='\bgit[[:space:]]+(-[^[:space:]]+[[:space:]]+([^-][^[:space:]]*[[:space:]]+)?)*'
# `[^;&|]*`, not `.*`: the greedy any-char form spanned command separators, so
# an unrelated `-f` later in a compound command blocked a perfectly ordinary
# push. Observed: `git push -q origin branch; echo done; [ -f "$x" ] && ...`
# was blocked as a force push because the `.*` reached the `-f` in the shell
# test three commands later. The leading-plus check below already scoped
# itself this way; this line simply did not.
# ...and `[^;&|]*` is why `git push 2>&1 --force origin main` passed: `2>&1`
# CONTAINS an `&`, so the scan stopped before `--force` was ever reached. The
# narrowing above is correct and the bypass is its direct consequence - which
# is the sharpest example this repo has of re-reviewing a guard fix as hard as
# the guard. ARG allows `&` only when it is part of a redirection (`&` followed
# by a digit), so `2>&1` is crossed while `&&`, a trailing `&` and `|` still
# stop the scan exactly as before.
ARG='([^;&|]|&[0-9])*'
echo "$CMD" | grep -qE "${GIT_PRE}push\b${ARG}(--force|-f)\b" && block "force push."
# `git push origin +main` is a force push with no --force token in it.
echo "$CMD" | grep -qE "${GIT_PRE}push\b${ARG}[[:space:]]\+[^[:space:];&|]" && block "force push (leading-plus refspec)."
# `git reset HEAD --hard` required `--hard` to follow `reset` immediately, so
# naming the ref bypassed it. Allow non-separator argument tokens in between;
# `--soft HEAD~1` still does not match, because it has no `--hard` to find.
echo "$CMD" | grep -qE "${GIT_PRE}(reset([[:space:]]+[^[:space:];&|]+)*[[:space:]]+--hard|clean[[:space:]]+-[a-z]*f)" && block "destroys uncommitted work."
echo "$CMD" | grep -qE '\brm[[:space:]]+-[a-z]*rf?[[:space:]]+/' && block "recursive delete from root."
# Argument-position match, not substring presence. The old check matched
# "prod"/"production" as a whole word ANYWHERE in the command text, plus one
# of a handful of infra CLI names ANYWHERE in that same text - so it blocked
# `gh pr comment ... --body "...the prod outage..."` (both words were just
# prose, "gh" is not an infra CLI) and `aws events describe-rule --name
# thd-prod-inventory-created` (an unrelated resource name that happens to
# have "prod" as a middle segment). It was also trivially dodged: quote the
# argument differently and the substring match still fires, or wrap the same
# command in a script and it silently stops firing - noisy and ineffective.
#
# Fix: tokenize the command for real. The infra CLI must be the actual
# program invoked (not a word anywhere in the text). The environment name
# must be the whole argument, or the first/last hyphen-joined segment of one
# - never a value handed to a message-type flag (-m, --body, ...), a web URL,
# or any token carrying whitespace (which can only be a quoted string).
ENV_PY=$(crew_py) || ENV_PY=""
if [ -n "$ENV_PY" ]; then
  ENVHIT=$("$ENV_PY" - "$CMD" <<'PYEOF'
import re, shlex, sys

cmd = sys.argv[1]
TOOLS = {"psql", "mysql", "sqlcmd", "mongo", "az", "aws", "gcloud"}
ENVS = {"prod", "production"}
PROSE_FLAGS = {"-m", "--message", "--body", "--comment", "--title",
               "--description", "--subject", "-F"}


def segments(tok):
    return [s for s in re.split(r"[^A-Za-z0-9]+", tok) if s]


def strip_scheme(tok):
    m = re.match(r"^[A-Za-z][A-Za-z0-9+.-]*://(.*)$", tok)
    return m.group(1) if m else tok


hit = False
for part in re.split(r"&&|\|\||[|;]", cmd):
    part = part.strip()
    if not part:
        continue
    try:
        toks = shlex.split(part)
    except ValueError:
        toks = part.split()
    if not toks:
        continue
    prog = toks[0].rsplit("/", 1)[-1].lower()
    if prog not in TOOLS:
        continue
    skip_next = False
    for tok in toks[1:]:
        if skip_next:
            skip_next = False
            continue
        if tok in PROSE_FLAGS:
            skip_next = True
            continue
        if re.match(r"(?i)^https?://", tok):
            continue
        if any(ch.isspace() for ch in tok):
            continue
        segs = segments(strip_scheme(tok))
        if segs and (segs[0].lower() in ENVS or segs[-1].lower() in ENVS):
            hit = True
            break
    if hit:
        break

print("1" if hit else "0")
PYEOF
)
else
  # No python: fall back to the old, cruder whole-word check rather than
  # silently disabling this rule.
  if echo "$CMD" | grep -qiE '(^|[^[:alnum:]])(prod|production)([^[:alnum:]]|$)' \
     && echo "$CMD" | grep -qiE '(^|[^[:alnum:]])(psql|mysql|sqlcmd|mongo|az|aws|gcloud)([^[:alnum:]]|$)'; then
    ENVHIT=1
  else
    ENVHIT=0
  fi
fi
[ "$ENVHIT" = "1" ] && block "command targets production. If this is not production, rename the argument or run it yourself."

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
  # The assignment must capture THIS read. The old test asked only whether an
  # assignment appeared anywhere in the command, so `X=$(date); aws
  # secretsmanager get-secret-value ...` satisfied it and printed the secret:
  # an unrelated capture was accepted as evidence that the dangerous half was
  # captured. Requiring the secret read to sit INSIDE the substitution, with no
  # command separator between, is the difference between "a capture happened"
  # and "this was captured".
  if ! echo "$CMD" | grep -qiE "(^|[[:space:]]|;)(export[[:space:]]+)?[A-Za-z_][A-Za-z0-9_]*=[\"]?([$][(]|\`)[^;&|]*${SECRET_READ}"; then
    block "this prints a secret value into the transcript. Capture it instead, e.g. DB_PASS=\$(aws secretsmanager get-secret-value --secret-id NAME --query SecretString --output text)"
  fi
fi
echo "$CMD" | grep -qiE '\b(cat|echo|printf|less|more|head|tail)\b[^|]*\.env(\.[a-z]+)?([[:space:]]|$)' && block "prints a .env file. Reference variable names, never values."
exit 0

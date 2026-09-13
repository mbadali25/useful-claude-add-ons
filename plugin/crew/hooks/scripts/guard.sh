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

# --- configurable guardrails ----------------------------------------------
#
# Three of the rules below are no longer a fixed refusal: `guards.terraformApply`
# `guards.forcePush` and `guards.adminMerge` each resolve to `block`, `ask` or
# `allow`. The DEFAULT is `block`, so a machine with no config behaves exactly
# as this script did before.
#
# The policy is resolved by `crew_config.py --guard`, never here, and the
# PowerShell twin calls the same CLI. Config layering is the last thing that
# should exist twice: these two files drift independently -- three bypasses
# fixed in #132 were open in both -- and the layering rule whose entire point
# is that a cloned repo cannot widen it would then have two implementations,
# either of which could be the one that forgets to ratchet. `Test-EnvArgHit` is
# a reimplementation on purpose (it is a tokenizer, and a subprocess per
# command would be a per-command cost); this is not that.
#
# FAIL CLOSED, loudly. No python, a crew_config that raises, a line this script
# cannot parse -- every one of them is `block` with the reason said out loud.
# "Could not check" is its own outcome and never collapses into "checked, and
# fine": the config is the only source for these values and there is no cruder
# form of reading it, unlike the `prod` rule below which has a real regex
# fallback.
GUARD_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

guarded() {  # $1 = guard name, $2 = the refusal message
  local py out decision policy marker target reason access
  py=$(crew_py) \
    || block "$2 [guards.$1 stays \`block\`: no python to read the config]"
  out=$("$py" "$GUARD_DIR/crew_config.py" \
        --root "${CLAUDE_PROJECT_DIR:-.}" \
        --guard "$1" --command "$CMD" --record 2>/dev/null) \
    || block "$2 [guards.$1 stays \`block\`: crew could not read it]"
  out=$(crew_strip_cr "$out")
  IFS=$'\t' read -r decision policy marker target reason access <<<"$out"
  # `-` is the producer's spelling of an empty field. It has to be: TAB is IFS
  # WHITESPACE, so `IFS=$'\t' read` collapses a run of tabs and every field
  # after an empty one shifts left. See the note beside the print in
  # crew_config.py's --guard branch.
  [ "$target" = "-" ] && target=""
  [ "$reason" = "-" ] && reason=""
  case "$decision" in
    allow)
      # Under `allow` nothing is silent. The row in .crew/guard.log is the
      # durable half (crew_config.py --record wrote it); this is the half the
      # user sees in the moment.
      printf 'crew guard: guards.%s is `%s` - ALLOWED: %s\n' \
             "$1" "$policy" "$reason" >&2
      printf '  command: %s\n' "$CMD" >&2
      [ -n "$target" ] && printf '  target branch: %s\n' "$target" >&2
      return 0
      ;;
    ask)
      # A PreToolUse hook has no interactive stdin, so "stop for a yes at that
      # moment" is a refusal that names the file which approves THIS command.
      # The marker is keyed on a digest of the command, so approving one force
      # push does not approve the next one.
      printf 'BLOCKED (guards.%s = ask): %s\n' "$1" "$2" >&2
      printf 'The exact command:\n  %s\n' "$CMD" >&2
      [ -n "$target" ] && printf 'Target branch: %s\n' "$target" >&2
      printf 'To approve THIS command and nothing else, then re-run it:\n' >&2
      printf '  touch %s\n' "$marker" >&2
      # The window, and whether a marker already there has fallen outside it,
      # come from `reason` rather than being spelled here: the bound is
      # GUARD_APPROVAL_TTL in crew_guards.py, and a number restated in two
      # shells is a number that will disagree with itself.
      [ -n "$reason" ] && printf '%s\n' "$reason" >&2
      exit 2
      ;;
    block)
      block "$2"
      ;;
    *)
      block "$2 [guards.$1 stays \`block\`: unreadable decision from crew_config]"
      ;;
  esac
}

# `guards.prodDatabase` / `guards.prodServer`. A separate wrapper from
# `guarded`, for one reason worth stating: these two fire on ORDINARY commands.
# Every `ssh` and every `psql` reaches them, and most of those aim at nothing
# anybody declared as production. `guarded` prints a line on every `allow`,
# which is right when the guard only sees dangerous commands and wrong here --
# it would put a crew banner above every remote shell in the session, which is
# how a guard becomes noise people switch off.
#
# So: SILENT when no declared pattern matched (PROD_TARGET stays empty), and
# loud on every decision that a declared pattern actually produced. The log
# row is written either way by crew_config.py --record, so "nothing is silent"
# still holds where it means anything.
PROD_TARGET=""
prod_guarded() {  # $1 = guard name, $2 = the refusal message
  local py out decision policy marker target reason access
  PROD_TARGET=""
  # NO PYTHON is a stand-down; a FAILED RESOLVER is a refusal, and the two are
  # not the same event. Without python crew cannot read any config, so every
  # repo on the machine would have every `ssh` refused -- the guard people
  # switch off -- and the unconfigurable `prod` rule further down still blocks
  # on its own regex with no python at all, so the floor does not move. A
  # python that IS here and then fails is crew broken, on a question whose
  # answer decides whether a production write runs. That one blocks, loudly.
  py=$(crew_py) || return 0
  out=$("$py" "$GUARD_DIR/crew_config.py" \
        --root "${CLAUDE_PROJECT_DIR:-.}" \
        --guard "$1" --command "$CMD" --record 2>/dev/null) \
    || block "$2 [guards.$1: crew could not read it, and could not tell whether this targets production]"
  out=$(crew_strip_cr "$out")
  IFS=$'\t' read -r decision policy marker target reason access <<<"$out"
  [ "$target" = "-" ] && target=""
  [ "$reason" = "-" ] && reason=""
  [ "$access" = "-" ] && access=""
  # An empty target means NO DECLARED PATTERN MATCHED -- not that the guard
  # passed. Returning silently here is what keeps `ssh` to an undeclared host
  # exactly as quiet as it was before schema 6.
  [ -z "$target" ] && return 0
  PROD_TARGET="$target"
  case "$decision" in
    allow)
      printf 'crew guard: guards.%s is `%s` - ALLOWED: %s\n' \
             "$1" "$policy" "$reason" >&2
      printf '  command: %s\n' "$CMD" >&2
      [ -n "$access" ] && printf '  classified as: %s\n' "$access" >&2
      return 0
      ;;
    block)
      block "$2 [$reason]"
      ;;
    *)
      block "$2 [guards.$1 stays \`none\`: unreadable decision from crew_config]"
      ;;
  esac
}

# --- destructive operations ----------------------------------------------
# TF_PRE is GIT_PRE's reason applied to the neighbour that never got it:
# `terraform -chdir=infra apply` sailed through a rule that required `apply` to
# sit immediately after `terraform`, while the git rules eleven lines below had
# already been fixed for exactly that shape. Re-review the fix to a guard as
# hard as the guard: the sibling rule was the one still broken.
# `tofu` is here because OpenTofu is terraform's drop-in fork: same
# subcommands, same blast radius, a different binary name. The rule named one
# of the two and refused nothing when the other was installed, which is a
# bypass the moment a repo switches. This is a NEW refusal, not a preserved
# one -- see the schema 6 note in crew_upgrade.py, which says so out loud
# rather than letting "the default is block, so nothing changed" cover it.
TF_PRE='\b(terraform|tofu)([[:space:]]+-[^[:space:]]+)*[[:space:]]+'
echo "$CMD" | grep -qE "${TF_PRE}(apply|destroy)" && guarded terraformApply "terraform/tofu apply/destroy is manual. Run plan and show it."
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
echo "$CMD" | grep -qE "${GIT_PRE}push\b${ARG}(--force|-f)\b" && guarded forcePush "force push."
# `git push origin +main` is a force push with no --force token in it.
echo "$CMD" | grep -qE "${GIT_PRE}push\b${ARG}[[:space:]]\+[^[:space:];&|]" && guarded forcePush "force push (leading-plus refspec)."
# `gh pr merge --admin` merges PAST a branch protection rule that the
# repository's owner put there. No crew guard refused it before schema 6, so
# `guards.adminMerge` arriving at `block` is a NEW refusal and the upgrade
# report says so.
#
# Scope, stated rather than implied: this matches `gh pr merge` carrying
# `--admin`, in any argument position. It does NOT match a hand-rolled
# `gh api -X PUT .../pulls/N/merge`, which reaches the same endpoint without
# the flag. That is a real gap and it is left open deliberately -- a rule wide
# enough to catch every `gh api` call to a merge URL is wide enough to block
# reading one, and a guard that fires on reads is a guard people switch off.
GH_MERGE='\bgh[[:space:]]+pr[[:space:]]+merge\b'
echo "$CMD" | grep -qE "${GH_MERGE}${ARG}--admin\b" && guarded adminMerge "gh pr merge --admin merges past the repo's branch protection."
# --- production access ----------------------------------------------------
# Which TOOLS could be aimed at production; whether they ARE is decided by
# `production.databases` / `production.hosts`, in the repo config, by
# crew_config.py. This regex is deliberately the crude half: a tool that is not
# listed here never reaches the resolver, so the list errs wide, and a match
# here costs one python call and prints nothing unless a pattern matched.
DB_TOOLS='(^|[[:space:];&|])(psql|mysql|mariadb|sqlcmd|mongosh|mongo|redis-cli|cqlsh)\b|\baws[[:space:]]+(rds|redshift|dynamodb|docdb)\b'
SRV_TOOLS='(^|[[:space:];&|])(ssh|scp|plink|rsync)\b|\baws[[:space:]]+(ssm|ec2)\b'
PROD_HIT=0
if echo "$CMD" | grep -qE "$DB_TOOLS"; then
  prod_guarded prodDatabase "this targets a database declared in production.databases."
  [ -n "$PROD_TARGET" ] && PROD_HIT=1
fi
if echo "$CMD" | grep -qE "$SRV_TOOLS"; then
  prod_guarded prodServer "this targets a host declared in production.hosts."
  [ -n "$PROD_TARGET" ] && PROD_HIT=1
fi
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
# acme-prod-inventory-created` (an unrelated resource name that happens to
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
# The unconfigurable `prod`/`production`-in-an-argument rule, which predates
# the two keys above and stays. It is skipped ONLY when a declared
# `production.*` pattern already matched this command, because then the
# configured level has answered the same question with better information --
# leaving both in would mean `guards.prodDatabase: full` still refused
# `prod-db-1`, which is a key that reads as configurable and is not.
#
# With nothing declared, `PROD_HIT` is 0 and this line behaves exactly as it
# did before schema 6. That is what makes the new default behaviour-preserving
# rather than merely behaviour-neutral-sounding.
[ "$ENVHIT" = "1" ] && [ "$PROD_HIT" = "0" ] && block "command targets production. If this is not production, rename the argument or run it yourself."

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

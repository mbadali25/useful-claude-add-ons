#!/usr/bin/env bash
# Regression suite for crew's hook scripts.
#
# guard.sh has had two real regressions in two review passes - a substring
# "prod" match that blocked `s3://my-product-images`, and a secret rule that
# exempted `> file` so writing a secret to disk passed while printing one
# blocked. Both were found by running the thing, not by reading it. This file
# exists so the next edit has a safety net.
#
#   bash hooks/scripts/_test/run-tests.sh
#
# Exit 0 = all pass. Exit 1 = something regressed.
#
# SABOTAGE-TEST THIS SUITE before trusting it: break a rule in guard.sh on
# purpose, run this, and confirm it goes red. A check that has never failed has
# never been shown to be able to fail.
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
SCRIPTS="$(cd "$HERE/.." && pwd)"
PLUGIN="$(cd "$SCRIPTS/../.." && pwd)"

PASS=0; FAIL=0
fail() { printf '  FAIL  %s\n' "$1"; FAIL=$((FAIL+1)); }
pass() { PASS=$((PASS+1)); }

# Resolve a python for building JSON payloads.
PY=$(command -v python3 || command -v python || command -v py) || {
  echo "SKIP: no python available to build test payloads" >&2; exit 0; }

json_cmd() {  # $1 = tool_name, $2 = command
  "$PY" - "$1" "$2" <<'PYEOF'
import sys, json
print(json.dumps({"tool_name": sys.argv[1], "tool_input": {"command": sys.argv[2]}}))
PYEOF
}

guard() {  # $1 = command -> echoes exit code
  json_cmd Bash "$1" | bash "$SCRIPTS/guard.sh" >/dev/null 2>&1
  echo $?
}

expect() {  # $1 = wanted exit, $2 = command
  local got; got=$(guard "$2")
  if [ "$got" = "$1" ]; then pass; else fail "want=$1 got=$got  $2"; fi
}

echo "== guard.sh: must BLOCK (exit 2) =="
expect 2 'terraform apply -auto-approve'
expect 2 'terraform destroy'
expect 2 'git push --force origin main'
expect 2 'git push -f origin main'
expect 2 'git reset --hard HEAD~3'
expect 2 'git clean -fd'
expect 2 'DROP TABLE users'
expect 2 'TRUNCATE TABLE audit_log'
expect 2 'psql -h prod-db.internal -c "select 1"'
expect 2 'aws s3 rm s3://bucket/key --profile prod'
expect 2 'az sql db show --resource-group prod-rg'
# D5 true positive: the environment name as the leading segment of an actual
# resource argument to a real infra CLI - must still block.
expect 2 'aws s3 rm s3://prod-backups/2026-08-24.tar.gz --recursive'
# secrets: printing, persisting, and the tee variant all block
expect 2 'vault kv get secret/db'
expect 2 'vault kv get secret/db > /tmp/s.txt'
expect 2 'vault kv get secret/db >> /tmp/s.txt'
expect 2 'vault kv get secret/db | tee /tmp/s.txt'
expect 2 'aws secretsmanager get-secret-value --secret-id db --query SecretString --output text'
expect 2 'aws ssm get-parameter --name /db/pass --with-decryption'
expect 2 'kubectl get secret db -o yaml'
expect 2 'cat .env'
expect 2 'cat .env.production'

echo "== guard.sh: must ALLOW (exit 0) =="
expect 0 'terraform plan'
expect 0 'terraform fmt -recursive -check'
expect 0 'terraform validate'
expect 0 'git push origin feature/x'
expect 0 'git status'
# "prod" as a substring of an ordinary word is not production
expect 0 'aws s3 ls s3://anew-product-images'
expect 0 'aws s3 ls s3://reproducible-builds'
expect 0 'psql -c "select * from products"'
expect 0 'grep -r productivity src/'
# D5 false positives: the environment name in a quoted value, a commit
# message, a -m argument, a URL, and prose must NOT trigger the guard - only
# an actual argument position on a real infra CLI does.
expect 0 'aws s3 cp notes.txt "s3://bucket/prod team meeting notes.txt"'
expect 0 'git commit -m "redeploy prod after aws outage"'
expect 0 'aws sns publish --topic-arn arn:aws:sns:us-east-1:123:t -m prod-status-update'
expect 0 'aws ssm put-parameter --name /docs/link --value https://runbooks.example.com/prod --type String'
expect 0 'gh pr comment 42 --body "This fixes the prod outage from yesterday, see aws docs for details"'
# the sanctioned way to handle a secret: capture, never render
expect 0 'DB_PASS=$(aws secretsmanager get-secret-value --secret-id db --query SecretString --output text)'
expect 0 'export DB_PASS=$(vault kv get -field=pass secret/db)'
expect 0 'npm test'
expect 0 'grep -r TODO src/'
expect 0 'cat README.md'

echo "== verify-gate.sh =="
D=$(mktemp -d) || exit 1
(
  cd "$D" || exit 1
  git init -q .
  mkdir -p .crew sql
  echo '{}' > .crew/config.json
  cat > .crew/verify.json <<'EOF'
{"version":1,
 "rules":[{"paths":["**/*.tf"],"run":["true"]},
          {"paths":["**/*.py"],"run":["true"]},
          {"paths":["sql/**"],"run":["true"]}],
 "always":[],"default":[],"unmapped":"fail"}
EOF
  touch main.tf handler.py sql/proc.sql README.md
)
export CLAUDE_PROJECT_DIR="$D"

# Root-level main.tf must match "**/*.tf". fnmatch's * spans '/', so an
# unpatched gate silently skips every file that is not in a subdirectory.
echo '{}' | bash "$SCRIPTS/verify-gate.sh" >/dev/null 2>&1
[ "$?" = "2" ] && pass || fail "verify-gate: unmapped README.md should fail the turn (root-level globs may not be matching)"

# A blocking Stop hook re-fires; without this check it blocks its own retry.
echo '{"stop_hook_active":true}' | bash "$SCRIPTS/verify-gate.sh" >/dev/null 2>&1
[ "$?" = "0" ] && pass || fail "verify-gate: stop_hook_active must exit 0 or the session wedges"

unset CLAUDE_PROJECT_DIR

echo "== promote-gate.sh =="
PD=$(mktemp -d) || exit 1
trap 'rm -rf "$D" "$PD"' EXIT
(
  cd "$PD" || exit 1
  git init -q .
  git config user.email t@example.com
  git config user.name t
  mkdir -p .crew .work docs/runbooks scripts
  # .crew/ and .work/ are gitignored in a real repo. They must be, or the gate's
  # own marker file dirties the tree and blocks the next deploy.
  printf '.crew/\n.work/\n' > .gitignore
  cat > .crew/verify.json <<'EOF'
{"version":1,"rules":[],"always":[],"default":[],"unmapped":"warn",
 "environments":{
   "qa":{"deploy":["./scripts/deploy.sh qa"],"smoke":["true"],
         "rollback":"none","rollbackReason":"qa is rebuilt on every push","promotesTo":"production"},
   "staging":{"deploy":["./scripts/deploy.sh staging"],"smoke":["true"]},
   "production":{"requires":["qa"],"deploy":["./scripts/deploy.sh prod"],
                 "rollback":"docs/runbooks/rollback.md","requireHuman":true}}}
EOF
  echo '{}' > .crew/config.json
  printf '#!/bin/sh\necho deployed\n' > scripts/deploy.sh
  git add -A && git commit -qm init
)
export CLAUDE_PROJECT_DIR="$PD"
SHA=$(git -C "$PD" rev-parse --short HEAD)
RB="$PD/docs/runbooks/rollback.md"
ROW="$PD/.work/PROMOTIONS.md"

pgate() {
  json_cmd Bash "$1" | bash "$SCRIPTS/promote-gate.sh" >/dev/null 2>&1
  echo $?
}
pexpect() {
  local got; got=$(pgate "$2")
  if [ "$got" = "$1" ]; then pass; else fail "promote-gate want=$1 got=$got  $3"; fi
}
qa_row() {  # write an all-pass qa row for $1
  printf '| when | env | sha | smoke | regression | verify | by |\n|---|---|---|---|---|---|---|\n| now | qa | %s | pass | pass | pass | tester |\n' "$1" > "$ROW"
}

pexpect 0 'npm test'                 'an unrelated command must pass straight through'
pexpect 0 './scripts/deploy.sh qa'   'qa has no requires and an explicit rollback:none+reason - allowed'
rm -f "$PD/.crew/.deploy-in-flight"

# D1: an absent 'rollback' key must fail CLOSED, not open. "staging" declares
# no rollback key at all.
pexpect 2 './scripts/deploy.sh staging' 'no rollback key at all - must block, not silently allow'

# D1: rollback:"none" with no rollbackReason is still not an opt-out.
"$PY" - "$PD/.crew/verify.json" <<'PY'
import json, sys
p = sys.argv[1]
cfg = json.load(open(p))
cfg["environments"]["staging"]["rollback"] = "none"
json.dump(cfg, open(p, "w"))
PY
pexpect 2 './scripts/deploy.sh staging' 'rollback:none with no rollbackReason - must still block'

# D1: rollback:"none" plus a stated rollbackReason IS a valid opt-out.
"$PY" - "$PD/.crew/verify.json" <<'PY'
import json, sys
p = sys.argv[1]
cfg = json.load(open(p))
cfg["environments"]["staging"]["rollbackReason"] = "staging has no user traffic; redeploying dev is the rollback"
json.dump(cfg, open(p, "w"))
PY
pexpect 0 './scripts/deploy.sh staging' 'rollback:none with a stated rollbackReason - allowed'
rm -f "$PD/.crew/.deploy-in-flight"

# Each precondition proven in isolation: start from all-satisfied, break one.
printf 'last verified: %s\n' "$(date +%Y-%m-%d)" > "$RB"
( cd "$PD" && git add -A && git commit -qm runbook >/dev/null )
SHA=$(git -C "$PD" rev-parse --short HEAD)
qa_row "$SHA"
touch "$PD/.crew/.approved-production-$SHA"
rm -f "$PD/.crew/.deploy-in-flight"

pexpect 0 './scripts/deploy.sh prod' 'all preconditions satisfied - must ALLOW'
[ -f "$PD/.crew/.deploy-in-flight" ] && pass || fail "promote-gate: an allowed deploy must write .crew/.deploy-in-flight"

# break: no qa pass row for this sha
rm -f "$PD/.crew/.deploy-in-flight"; rm -f "$ROW"
pexpect 2 './scripts/deploy.sh prod' 'no qa all-pass row for this sha - must block'
qa_row "$SHA"

# break: qa row exists but a gate in it failed
rm -f "$PD/.crew/.deploy-in-flight"
printf '| when | env | sha | smoke | regression | verify | by |\n|---|---|---|---|---|---|---|\n| now | qa | %s | pass | FAIL | pass | tester |\n' "$SHA" > "$ROW"
pexpect 2 './scripts/deploy.sh prod' 'qa row records a FAILED gate - must block'
qa_row "$SHA"

# break: rollback runbook older than 90 days
rm -f "$PD/.crew/.deploy-in-flight"
printf 'last verified: 2020-01-01\n' > "$RB"
pexpect 2 './scripts/deploy.sh prod' 'rollback runbook verified over 90 days ago - must block'
printf 'last verified: %s\n' "$(date +%Y-%m-%d)" > "$RB"

# break: rollback runbook missing entirely
rm -f "$PD/.crew/.deploy-in-flight"; mv "$RB" "$RB.bak"
pexpect 2 './scripts/deploy.sh prod' 'rollback runbook missing - must block'
mv "$RB.bak" "$RB"

# break: no human approval marker
rm -f "$PD/.crew/.deploy-in-flight"; rm -f "$PD/.crew/.approved-production-$SHA"
pexpect 2 './scripts/deploy.sh prod' 'requireHuman with no approval marker - must block'
touch "$PD/.crew/.approved-production-$SHA"

# break: dirty working tree
rm -f "$PD/.crew/.deploy-in-flight"; echo "uncommitted" > "$PD/scratch.txt"
pexpect 2 './scripts/deploy.sh prod' 'dirty working tree - must block'
rm -f "$PD/scratch.txt"

echo "== verify-gate.sh: a deploy must be recorded =="
printf 'production %s\n' "$SHA" > "$PD/.crew/.deploy-in-flight"
rm -f "$ROW"
echo '{}' | bash "$SCRIPTS/verify-gate.sh" >/dev/null 2>&1
[ "$?" = "2" ] && pass || fail "verify-gate: a deploy with no PROMOTIONS row must not end the turn"

printf '| when | env | sha | smoke | regression | verify | by |\n|---|---|---|---|---|---|---|\n| now | production | %s | pass | pass | pass | tester |\n' "$SHA" > "$ROW"
echo '{}' | bash "$SCRIPTS/verify-gate.sh" >/dev/null 2>&1
[ ! -f "$PD/.crew/.deploy-in-flight" ] && pass || fail "verify-gate: a recorded deploy must clear .deploy-in-flight"

unset CLAUDE_PROJECT_DIR

echo "== claude-md-audit.sh =="
A="$PLUGIN/skills/crew-setup/scripts/claude-md-audit.sh"
if [ -f "$A" ]; then
  OUT=$(bash "$A" "$PLUGIN/skills/crew-setup/repo-claude-template.md" 2>&1)
  case "$OUT" in *"all template sections present"*) pass ;;
    *) fail "claude-md-audit: template should report all sections present" ;; esac

  L=$(mktemp -d); printf '# legacy\n\n## Commands\nx\n' > "$L/CLAUDE.md"
  OUT=$(bash "$A" "$L/CLAUDE.md" 2>&1); rm -rf "$L"
  case "$OUT" in *"MISSING  ## Promotion"*) pass ;;
    *) fail "claude-md-audit: a legacy file should report the Promotion section missing" ;; esac
fi

echo "== resolve-tools.sh: bash <script> resolution =="
RD=$(mktemp -d) || exit 1
(
  cd "$RD" || exit 1
  mkdir -p .crew _verify
  # Three call shapes the ticket named: bash script.sh, bash -x script.sh, and
  # a quoted path. Each script shells out to a tool that is invisible unless
  # resolve-tools.sh looks inside it.
  printf '#!/bin/sh\nterraform validate\nruff check .\n' > _verify/smoke.sh
  printf '#!/bin/sh\nsqlcmd -Q "select 1"\n' > "_verify/has space.sh"
  cat > .crew/verify.json <<'EOF'
{"version":1,"rules":[
  {"paths":["**/*.tf"],"run":["bash _verify/smoke.sh"],"why":"smoke wraps terraform+ruff"},
  {"paths":["sql/**"],"run":["bash -x \"_verify/has space.sh\""],"why":"quoted, flagged"}
 ],"always":[],"default":[],"unmapped":"warn"}
EOF
)
export CLAUDE_PROJECT_DIR="$RD"
OUT=$(bash "$PLUGIN/skills/crew-setup/scripts/resolve-tools.sh" 2>&1)
unset CLAUDE_PROJECT_DIR
echo "$OUT" | grep -qE '^terraform ' && pass || fail "resolve-tools: bash _verify/smoke.sh should surface terraform  ($OUT)"
echo "$OUT" | grep -qE '^ruff '      && pass || fail "resolve-tools: bash _verify/smoke.sh should surface ruff      ($OUT)"
echo "$OUT" | grep -qE '^sqlcmd '    && pass || fail "resolve-tools: bash -x \"quoted path\" should surface sqlcmd  ($OUT)"
rm -rf "$RD"

echo
echo "RESULT: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ] || exit 1
exit 0

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

echo "== emergency lane: the gates stand down, the guard does not =="
# Writes .crew/incident.json expiring $1 seconds from now. Negative = expired.
# The gates read expiresAtEpoch and nothing else; see crew_incident.py.
inc() {
  "$PY" - "$PD/.crew/incident.json" "$1" <<'PYEOF'
import json, sys, time
json.dump({"id": "INC-TEST", "summary": "suite", "standDown": True,
           "expiresAtEpoch": int(time.time()) + int(sys.argv[2])},
          open(sys.argv[1], "w"))
PYEOF
}
SKIPS="$PD/.crew/incident-skips.log"

# An incident must NOT make the guard permissive. It is the hook that refuses
# force pushes, history rewrites and secret reads - and an incident is exactly
# when someone is tired enough to need it. Standing down the checks that say a
# change is wrong is a trade; standing down the ones that stop it being
# unrecoverable is not.
inc 3600
expect 2 'git push --force origin main'
expect 2 'git reset --hard HEAD~3'
expect 2 'terraform destroy'
expect 2 'cat .env'

# promote-gate: a deploy that must block with no incident is allowed with one,
# and every unmet precondition is written down instead.
rm -f "$PD/.crew/.deploy-in-flight" "$SKIPS" "$ROW"
pexpect 0 './scripts/deploy.sh prod' 'incident open: a deploy with no qa row must be ALLOWED'
grep -q 'promote' "$SKIPS" 2>/dev/null && pass \
  || fail "emergency: an allowed-but-ungated deploy must be recorded in incident-skips.log"
grep -q 'no all-pass row' "$SKIPS" 2>/dev/null && pass \
  || fail "emergency: the skip row must name the precondition that was unmet, not just the gate"

# verify-gate: the deploy-record check stands down too - an incident is exactly
# when a deploy goes out ahead of its paperwork - and records what is owed.
printf 'production %s\n' "$SHA" > "$PD/.crew/.deploy-in-flight"
rm -f "$ROW"
echo '{}' | bash "$SCRIPTS/verify-gate.sh" >/dev/null 2>&1
[ "$?" = "0" ] && pass || fail "emergency: an open incident must not block the turn"
grep -q 'no row in .work/PROMOTIONS.md' "$SKIPS" 2>/dev/null && pass \
  || fail "emergency: an unrecorded deploy must be logged as owed"

# One turn, one row. Both flavours of the hook run on the same Stop on Windows,
# and Stop fires every turn, so an immediate repeat has to be dropped or a
# ten-turn incident reports twenty skipped gates.
BEFORE=$(wc -l < "$SKIPS")
echo '{}' | bash "$SCRIPTS/verify-gate.sh" >/dev/null 2>&1
AFTER=$(wc -l < "$SKIPS")
[ "$BEFORE" = "$AFTER" ] && pass \
  || fail "emergency: an identical consecutive skip must not be logged twice ($BEFORE -> $AFTER)"

# THE safety property. An expired incident is inert: no command is run and no
# file is touched to re-gate, the clock alone does it. Forgetting to close an
# incident is the realistic failure mode, and it must not leave a repository
# permanently ungated.
inc -60
echo '{}' | bash "$SCRIPTS/verify-gate.sh" >/dev/null 2>&1
[ "$?" = "2" ] && pass || fail "emergency: an EXPIRED incident must gate again"
pexpect 2 './scripts/deploy.sh prod' 'expired incident: promote-gate must block again'

# A repo can forbid stand-downs outright: the incident is still declared, still
# recorded, still briefed - and the gates still gate.
inc 3600
printf '{"emergency":{"standDown":false}}\n' > "$PD/.crew/config.json"
echo '{}' | bash "$SCRIPTS/verify-gate.sh" >/dev/null 2>&1
[ "$?" = "2" ] && pass || fail "emergency: standDown false must keep the verify gate blocking"
pexpect 2 './scripts/deploy.sh prod' 'standDown false: promote-gate must block anyway'

# A malformed state file must fail CLOSED. A gate that cannot read its own
# state and assumes an incident is a gate that can be switched off with a typo.
printf '{ not json\n' > "$PD/.crew/incident.json"
echo '{}' > "$PD/.crew/config.json"
echo '{}' | bash "$SCRIPTS/verify-gate.sh" >/dev/null 2>&1
[ "$?" = "2" ] && pass || fail "emergency: an unparseable incident file must gate, not stand down"

# The same, with a FUTURE EPOCH inside the garbage. This is the case a grep or
# sed for the number gets wrong and ConvertFrom-Json gets right, so the two
# flavours disagreed and the bash one stood every gate down for a file that is
# not an incident at all. Codex review finding.
printf '{ not json "expiresAtEpoch": 9999999999 \n' > "$PD/.crew/incident.json"
echo '{}' | bash "$SCRIPTS/verify-gate.sh" >/dev/null 2>&1
[ "$?" = "2" ] && pass || fail "emergency: a future epoch inside INVALID json must not stand a gate down"
pexpect 2 './scripts/deploy.sh prod' 'a future epoch inside invalid json must not allow a deploy'

# Valid JSON, but the epoch is a string rather than a number. int() of "abc"
# must not throw its way into standing the gate down either.
printf '{"id":"INC-X","expiresAtEpoch":"not-a-number"}\n' > "$PD/.crew/incident.json"
echo '{}' | bash "$SCRIPTS/verify-gate.sh" >/dev/null 2>&1
[ "$?" = "2" ] && pass || fail "emergency: a non-numeric expiry must gate"

# A detail carrying a newline must not forge a second row in the skip log.
inc 3600
rm -f "$SKIPS"
"$PY" - "$PD/.crew/verify.json" <<'PYEOF'
import json, sys
cfg = json.load(open(sys.argv[1]))
cfg["environments"]["production"]["rollback"] = "none"
cfg["environments"]["production"]["rollbackReason"] = ""
json.dump(cfg, open(sys.argv[1], "w"))
PYEOF
pexpect 0 './scripts/deploy.sh prod' 'incident open: still allowed with a broken rollback declaration'
ROWS=$(wc -l < "$SKIPS")
FIELDS=$(awk -F'\t' 'NF!=3 {c++} END {print c+0}' "$SKIPS")
[ "$FIELDS" = "0" ] && pass \
  || fail "emergency: every skip row must have exactly 3 tab-separated fields (got $ROWS rows, $FIELDS malformed)"

rm -f "$PD/.crew/incident.json" "$SKIPS" "$PD/.crew/.deploy-in-flight"

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

# ---------------------------------------------------------------------------
# pm_pulse.py -- a BLOCKING Stop hook, so it owes must-block/must-allow cases.
#
# The failure that matters most is not a missed finding, it is a LOOP: a Stop
# hook that blocks unconditionally never lets a turn end, and the user cannot
# fix it from inside the session. stop_hook_active is tested first for that
# reason.
#
# SABOTAGE-TEST: delete the `if payload.get("stop_hook_active")` guard in
# pm_pulse.py and confirm the first case below goes red.
# ---------------------------------------------------------------------------
echo "== pm_pulse.py: Stop hook =="

pulse_payload() {  # $1 = cwd, $2 = session id, $3 = stop_hook_active (true/false)
  "$PY" - "$1" "$2" "$3" <<'PYEOF'
import sys, json
print(json.dumps({
    "cwd": sys.argv[1],
    "session_id": sys.argv[2],
    "stop_hook_active": sys.argv[3] == "true",
}))
PYEOF
}

pulse() {  # $1 = cwd, $2 = session, $3 = active -> echoes exit code
  pulse_payload "$1" "$2" "$3" | "$PY" "$SCRIPTS/pm_pulse.py" >/dev/null 2>&1
  echo $?
}

expect_pulse() {  # $1 = wanted exit, $2..$4 = cwd session active, $5 = label
  local got; got=$(pulse "$2" "$3" "$4")
  if [ "$got" = "$1" ]; then pass; else fail "pm_pulse: want=$1 got=$got  $5"; fi
}

PD=$(mktemp -d) || exit 1
mkdir -p "$PD/.crew"
# schema 2 keeps upgradeNeeded quiet; the absent graph is what fires graphStale,
# which is a real, non-quiet trigger and therefore a legitimate reason to block.
printf '{"schema":2,"tier":1,"roles":["explorer"]}\n' > "$PD/.crew/config.json"

# MUST ALLOW: the loop guard. Same state that blocks below, but on a turn that
# only exists because a Stop hook already blocked -- blocking again never ends.
expect_pulse 0 "$PD" sess-loop true "stop_hook_active must never block"

# MUST BLOCK: a crew repo with a real finding, first time this state is seen.
expect_pulse 2 "$PD" sess-a false "graphStale should block once"

# MUST ALLOW: the identical state a second time. This is the state-change gate
# AND the cross-flavour de-duplicator -- .sh and .ps1 both fire on Stop, and
# exactly one of them may speak per changed state.
expect_pulse 0 "$PD" sess-a false "unchanged state must not block twice"

# MUST ALLOW: not a crew repo at all. Every plain git checkout on the machine
# would otherwise block on graphStale, because there is genuinely no graph.
ND=$(mktemp -d) || exit 1
expect_pulse 0 "$ND" sess-b false "non-crew directory must not block"
rm -rf "$ND"

# MUST ALLOW: the PM switched off in config. An off switch that still blocks
# the end of every turn is not an off switch.
DD=$(mktemp -d) || exit 1
mkdir -p "$DD/.crew"
printf '{"schema":2,"pm":{"enabled":false}}\n' > "$DD/.crew/config.json"
expect_pulse 0 "$DD" sess-c false "pm.enabled false must not block"
rm -rf "$DD"

# MUST ALLOW: no session id. claim() fails CLOSED here (unlike hook_once), so
# an unkeyable pulse stays silent rather than blocking every turn forever.
expect_pulse 0 "$PD" "" false "missing session id must not block"

# A block with empty stderr is a block that says nothing: the turn fails and
# the model is told to continue with no reason. Exit code alone cannot catch
# that, so assert the content -- through the WRAPPER, which is the path
# hooks.json actually uses and the only one that proves `exec` propagates the 2.
PERR="$PD/pulse-stderr.txt"
pulse_payload "$PD" sess-stderr false | bash "$SCRIPTS/pm-pulse.sh" \
  >/dev/null 2>"$PERR"
PRC=$?
[ "$PRC" = 2 ] && pass || fail "pm_pulse: wrapper must propagate exit 2 (got $PRC)"
grep -q 'Crew PM' "$PERR" && pass || fail "pm_pulse: blocking stderr must name the PM"
grep -q 'priorit' "$PERR" && pass \
  || fail "pm_pulse: stderr must carry the user-priority override"
grep -q 'graph' "$PERR" && pass \
  || fail "pm_pulse: stderr must carry the actual finding, not just the directive"

# The cap is a backstop against a repo whose state oscillates every turn. If
# `pulses_taken`'s marker prefix ever drifts it silently returns 0 forever and
# the cap stops existing -- which is invisible without a test.
"$PY" - "$SCRIPTS" "$PD" <<'PYEOF' && pass || fail "pm_pulse: session cap"
import os, sys
sys.path.insert(0, sys.argv[1])
root = sys.argv[2]
import pm_pulse

before = pm_pulse.pulses_taken(root, "cap-sess")
for i in range(3):
    pm_pulse.claim(root, "cap-sess", f"{i:016x}")
after = pm_pulse.pulses_taken(root, "cap-sess")
if before != 0 or after != 3:
    print(f"  unit FAIL: pulses_taken {before} -> {after}, want 0 -> 3")
    sys.exit(1)
# A marker for a different session must not be counted against this one.
pm_pulse.claim(root, "other-sess", "ffffffffffffffff")
if pm_pulse.pulses_taken(root, "cap-sess") != 3:
    print("  unit FAIL: another session's markers leaked into the count")
    sys.exit(1)
# The same digest twice is one pulse, not two -- this is the de-duplicator.
if pm_pulse.claim(root, "cap-sess", "0000000000000000"):
    print("  unit FAIL: re-claiming the same digest must return False")
    sys.exit(1)
sys.exit(0)
PYEOF

# Pure-function cases: cheaper and sharper than driving the hook for each.
"$PY" - "$SCRIPTS" <<'PYEOF' && pass || fail "pm_pulse: unit cases"
import sys
sys.path.insert(0, sys.argv[1])
import pm_pulse

ok = True

def check(cond, label):
    global ok
    if not cond:
        print(f"  unit FAIL: {label}")
        ok = False

# A finding that is a standing condition is not worth interrupting a turn for.
check(not pm_pulse.should_pulse({
    "isCrew": True, "triggers": ["ticketsTooLarge", "reviewNotWorking"]}),
    "quiet-only triggers must not pulse")
# ...but a real one alongside them is.
check(pm_pulse.should_pulse({
    "isCrew": True, "triggers": ["ticketsTooLarge", "graphStale"]}),
    "a real trigger alongside quiet ones must pulse")
# A healthy crew says nothing.
check(not pm_pulse.should_pulse({"isCrew": True, "triggers": []}),
    "no triggers must not pulse")

# The fingerprint is the state-change gate: equal states must agree, and a
# changed trigger set must not. If this stops holding, the hook either never
# fires again or fires every turn.
a = {"isCrew": True, "triggers": ["graphStale"],
     "work": {"ticket": "T-1"}, "health": {"verdict": "ok"}}
b = dict(a, triggers=["graphStale", "diagramsStale"])
c = dict(a, work={"ticket": "T-2"})
check(pm_pulse.fingerprint(a) == pm_pulse.fingerprint(dict(a)),
      "same state must fingerprint equal")
check(pm_pulse.fingerprint(a) != pm_pulse.fingerprint(b),
      "changed triggers must fingerprint differently")
check(pm_pulse.fingerprint(a) != pm_pulse.fingerprint(c),
      "changed ticket must fingerprint differently")
# health.rate deliberately excluded -- it moves on every review and would fire
# the hook on changes nobody asked to hear about.
check(pm_pulse.fingerprint(a) == pm_pulse.fingerprint(
      dict(a, health={"verdict": "ok", "rate": 1.7})),
      "health.rate must not move the fingerprint")

sys.exit(0 if ok else 1)
PYEOF
rm -rf "$PD"

# ---------------------------------------------------------------------------
# crew_state.py -- diagram freshness. Anchor-based, never mtime-based.
# ---------------------------------------------------------------------------
echo "== crew_state.py: diagrams =="
"$PY" - "$SCRIPTS" <<'PYEOF' && pass || fail "crew_state: diagram cases"
import os, subprocess, sys, tempfile
sys.path.insert(0, sys.argv[1])
import crew_state

ok = True

def check(cond, label):
    global ok
    if not cond:
        print(f"  unit FAIL: {label}")
        ok = False

root = tempfile.mkdtemp()
run = lambda *a: subprocess.run(a, cwd=root, capture_output=True, text=True)
run("git", "init", "-q")
run("git", "config", "user.email", "t@t")
run("git", "config", "user.name", "t")
os.makedirs(os.path.join(root, "docs", "diagrams"))
open(os.path.join(root, "seed.txt"), "w").write("x")
run("git", "add", "-A")
run("git", "commit", "-qm", "seed")
head = run("git", "rev-parse", "--short=7", "HEAD").stdout.strip()

d = os.path.join(root, "docs", "diagrams")
# Current: anchored at HEAD, in the exact header crew-diagrams documents. A
# bare `anchor:` line is invalid Mermaid, so this is the form that must work.
open(os.path.join(d, "architecture.mmd"), "w").write(
    f"%% Generated from myrepo@{head} on 2026-08-27. Verify before trusting.\n"
    "%% Anchors: src/api/orders.ts\ngraph TD\n")
# Behind: anchored at something else. Hand-written `%% anchor:` form, which is
# accepted on purpose -- provenance that is right there in the text must not
# read as absent.
open(os.path.join(d, "data-flow-orders.mmd"), "w").write(
    "%% anchor: 0000000\ngraph TD\n")
# Unanchored counts as behind -- unknown provenance resolves to stale.
open(os.path.join(d, "process-refund.mmd"), "w").write("graph TD\n")

got = crew_state.read_diagrams(root, {})
check(got["total"] == 3, f"total should be 3, got {got['total']}")
check("architecture" not in got["behind"], "anchored-at-HEAD must not be behind")
check("data-flow-orders" in got["behind"], "wrong anchor must be behind")
check("process-refund" in got["behind"], "missing anchor must be behind")
# Prefix matching: data-flow-orders.mmd satisfies the data-flow KIND.
check(got["missing"] == [], f"all three kinds present, got missing={got['missing']}")

# A directory with no diagrams at all reports every kind missing, and must not
# raise on the absent directory.
empty = crew_state.read_diagrams(tempfile.mkdtemp(), {})
check(empty["total"] == 0, "absent diagrams dir must read as zero, not raise")
check(set(empty["missing"]) == set(crew_state.DIAGRAM_KINDS),
      f"absent dir must report all kinds missing, got {empty['missing']}")

# diagramsMissing must stay quiet until there is a codemap to draw from --
# otherwise every fresh setup is nagged about three diagrams on session one.
check("diagramsMissing" not in crew_state.evaluate_triggers({
    "isCrew": True, "knowledge": {"subsystems": 0},
    "diagrams": {"missing": ["architecture"]}}),
    "diagramsMissing must not fire without a codemap")
check("diagramsMissing" in crew_state.evaluate_triggers({
    "isCrew": True, "knowledge": {"subsystems": 3},
    "diagrams": {"missing": ["architecture"]}}),
    "diagramsMissing must fire once subsystems are mapped")
check("diagramsStale" in crew_state.evaluate_triggers({
    "isCrew": True, "diagrams": {"behind": ["architecture"]}}),
    "diagramsStale must fire on a behind anchor")
# Wrong-typed config must not raise -- this runs from SessionStart.
check(crew_state.read_diagrams(root, {"docs": "nonsense"})["total"] == 3,
      "wrong-typed docs config must fall back, not raise")

sys.exit(0 if ok else 1)
PYEOF

echo
echo "RESULT: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ] || exit 1
exit 0

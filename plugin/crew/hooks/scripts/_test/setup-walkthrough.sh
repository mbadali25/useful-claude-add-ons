#!/usr/bin/env bash
# Setup walkthrough: build a realistic mixed-stack scratch repo and run every
# SCRIPT that setup phases 0-8 invoke against it, asserting what each produced.
#
#   bash hooks/scripts/_test/setup-walkthrough.sh
#
# This proves the MECHANISM end to end - detection, scaffolding, the CLAUDE.md
# audit, the smoke and regression runners, tool resolution, and all three gates.
# It does NOT prove the prompts: the 16 commands and 9 agents are instructions
# to a model, and only a live session exercises those. validate-prompts.py
# checks their structure; nothing here checks their judgement.
set -uo pipefail

P="$(cd "$(dirname "$0")/../../.." && pwd)"
S="$P/skills/crew-setup/scripts"
H="$P/hooks/scripts"
R=$(mktemp -d)/demo-app
mkdir -p "$R"; cd "$R" || exit 1
export CLAUDE_PROJECT_DIR="$R"
export CLAUDE_PLUGIN_ROOT="$P"

OK=0; BAD=0
ok()  { printf '  ok    %s\n' "$1"; OK=$((OK+1)); }
bad() { printf '  FAIL  %s\n' "$1"; BAD=$((BAD+1)); }
has() { [ -e "$1" ] && ok "$2" || bad "$2 (expected $1)"; }

# ---------- a realistic mixed-stack repo ----------
git init -q .; git config user.email t@example.com; git config user.name tester
mkdir -p src/api sql migrations terraform src/components
cat > terraform/main.tf <<'EOF'
/**
 * Demo module.
 */
variable "name" { description = "the name"; type = string }
output "id" { description = "the id"; value = var.name }
EOF
cat > src/api/orders.py <<'EOF'
def ship(order_id: str) -> dict:
    """POST /api/orders/{id}/ship"""
    return {"shipmentId": order_id}
EOF
echo "CREATE TABLE orders (id int);" > sql/schema.sql
echo "ALTER TABLE orders ADD sku varchar(50);" > migrations/001_sku.sql
echo "body { color: red }" > src/components/app.css
printf '{"name":"demo","scripts":{"test":"echo unit-ok"}}' > package.json
printf 'requirements\n' > requirements.txt
git add -A && git commit -qm "initial demo app"

echo "############ PHASE 0 - platform + toolchain ############"
OUT=$(bash "$S/platform.sh" 2>&1)
echo "$OUT" | grep -q '"os"' && ok "platform.sh emits JSON" || bad "platform.sh JSON"
printf '%s' "$OUT" | python3 -c 'import sys,json; d=json.load(sys.stdin); print("       os=%s wsl=%s fs=%s crlf=%s"%(d["os"],d["wsl"],d["repoFilesystem"],d["crlfDetected"]))' 2>/dev/null \
  && ok "platform.sh JSON parses" || bad "platform.sh JSON parses"
bash "$S/resolve-tools.sh" terraform tflint ruff python3 >/dev/null 2>&1 && ok "resolve-tools.sh runs with explicit tools" || bad "resolve-tools.sh explicit"

echo "############ PHASE 1 - detect + scaffold + CLAUDE.md ############"
D=$(bash "$S/detect.sh" 2>&1)
echo "$D" | grep -q 'stack:' && ok "detect.sh reports a stack" || bad "detect.sh stack"
echo "$D" | grep -qE 'stack:.*(python|terraform|node)' && ok "detect.sh found python/terraform/node" \
  || { bad "detect.sh stack detection"; echo "$D" | sed -n '1p' | sed 's/^/       /'; }
echo "$D" | grep -q 'branch: *main\|branch: *master' && ok "detect.sh branch works (git portability)" \
  || { bad "detect.sh branch"; echo "$D" | grep branch | sed 's/^/       /'; }

mkdir -p .crew .work docs/adr docs/runbooks
printf '.crew/\n.work/\n' > .gitignore
cp "$P/skills/crew-setup/repo-claude-template.md" CLAUDE.md
cp -r "$P/skills/crew-setup/templates/_verify" ./_verify
mkdir -p _verify/cases
has _verify/smoke.sh    "_verify/smoke.sh scaffolded"
has _verify/run-all.sh  "_verify/run-all.sh scaffolded"
has _verify/README.md   "_verify/README.md scaffolded"

A=$(bash "$S/claude-md-audit.sh" 2>&1)
echo "$A" | grep -q "all template sections present" && ok "claude-md-audit: fresh template is complete" || bad "claude-md-audit fresh"
echo "$A" | grep -q "placeholders" && ok "claude-md-audit flags unfilled placeholders" || bad "claude-md-audit placeholders"
# and against a legacy file
printf '# legacy\n\n## Commands\nmake\n\n## Gotchas\ncron\n' > /tmp/legacy-CLAUDE.md
L=$(bash "$S/claude-md-audit.sh" /tmp/legacy-CLAUDE.md 2>&1)
echo "$L" | grep -q "MISSING  ## Promotion" && ok "claude-md-audit: legacy file misses Promotion" || bad "claude-md-audit legacy"
echo "$L" | grep -q "extra    ## gotchas" && ok "claude-md-audit: reports the repo's own extra sections" || bad "claude-md-audit extras"

echo "############ PHASE 2 - providers ############"
bash "$S/providers.sh" >/dev/null 2>&1 && ok "providers.sh runs" || bad "providers.sh"

echo "############ PHASE 3 - smoke harness ############"
sed -i 's|^# check "boots".*|check "unit" npm test|' _verify/smoke.sh 2>/dev/null
OUT=$(bash _verify/smoke.sh --env dev 2>&1); RC=$?
echo "$OUT" | grep -q "SMOKE target: dev" && ok "smoke.sh prints the resolved target" || bad "smoke.sh target line"
echo "$OUT" | grep -q "SMOKE:" && ok "smoke.sh prints a pass count" || bad "smoke.sh count"
[ "$RC" = "0" ] && ok "smoke.sh exits 0 when green" || bad "smoke.sh exit ($RC)"
printf '# readonly: yes\nexit 0\n' > _verify/cases/read-orders.sh
printf 'exit 0\n' > _verify/cases/write-order.sh
OUT=$(bash _verify/run-all.sh --env prod --read-only 2>&1)
echo "$OUT" | grep -q "PASS read-orders"  && ok "run-all --read-only RUNS a declared read-only case" || bad "run-all readonly runs"
echo "$OUT" | grep -q "SKIP write-order" && ok "run-all --read-only SKIPS an undeclared case" || bad "run-all readonly skips"
bash _verify/run-all.sh --env prod >/dev/null 2>&1; [ "$?" = "1" ] && ok "run-all refuses writes against prod without --read-only" || bad "run-all prod refusal"

echo "############ PHASE 4 - code map ############"
mkdir -p .crew/codemap
printf '# orders\nanchor: demo@%s\n' "$(git rev-parse --short HEAD)" > .crew/codemap/orders.md
printf '| orders | order lifecycle | %s |\n' "$(git rev-parse --short HEAD)" > .crew/codemap/INDEX.md
M=$(bash "$S/map-audit.sh" 2>&1); [ -n "$M" ] && ok "map-audit.sh runs and reports" || bad "map-audit.sh"

echo "############ PHASE 5 - verification map ############"
cat > .crew/verify.json <<'EOF'
{"version":1,
 "rules":[
  {"paths":["**/*.tf"],"run":["terraform fmt -recursive -check"],"agents":["security"],"why":"terraform"},
  {"paths":["**/*.py"],"run":["ruff check ."],"why":"python"},
  {"paths":["sql/**","migrations/**"],"run":["true"],"agents":["dba"],"why":"schema"},
  {"paths":["**/*.css","src/components/**"],"run":["true"],"why":"visual"},
  {"paths":["CLAUDE.md","_verify/**",".gitignore","package.json","requirements.txt"],"run":[],"why":"docs/config"}],
 "always":[],"default":["true"],"unmapped":"fail",
 "environments":{
  "qa":{"deploy":["./deploy.sh qa"],"smoke":["true"],
        "rollback":"none","rollbackReason":"qa is disposable, rebuilt on every push",
        "promotesTo":"production"},
  "production":{"requires":["qa"],"deploy":["./deploy.sh prod"],
                "rollback":"docs/runbooks/rollback.md","requireHuman":true}}}
EOF
T=$(bash "$S/resolve-tools.sh" 2>&1)
echo "$T" | grep -q "TOOL" && ok "resolve-tools.sh reads the map with no arguments" || bad "resolve-tools map read"
echo "$T" | grep -qE '^terraform ' && ok "resolve-tools extracted terraform from the map" || bad "resolve-tools extract terraform"
echo "$T" | grep -qE '^ruff ' && ok "resolve-tools extracted ruff from the map" || bad "resolve-tools extract ruff"
echo "$T" | grep -q "WSL" && ok "resolve-tools reports WSL reachability" || bad "resolve-tools wsl line"

echo "############ PHASE 7 - a real ticket, through the hooks ############"
# the guard sees an ordinary edit command
echo '{"tool_name":"Bash","tool_input":{"command":"python3 -m pytest"}}' | bash "$H/guard.sh" >/dev/null 2>&1
[ "$?" = "0" ] && ok "guard allows an ordinary test command" || bad "guard false positive on pytest"
# root-level main.tf equivalent: terraform/main.tf must map
python3 - <<'PY'
import json
c=json.load(open(".crew/verify.json"))
for r in c["rules"]: r["run"]=["true"] if r["run"] else []
json.dump(c,open(".crew/verify.json","w"),indent=1)
PY
echo "x" >> terraform/main.tf
echo '{}' | bash "$H/verify-gate.sh" >/dev/null 2>&1
[ "$?" = "0" ] && ok "gate passes: every changed file maps to a rule" || bad "gate on mapped change"
# an unmapped file must fail the turn
echo "junk" > UNMAPPED.txt
echo '{}' | bash "$H/verify-gate.sh" >/dev/null 2>&1
[ "$?" = "2" ] && ok "gate FAILS the turn on an unmapped file" || bad "gate on unmapped file"
rm -f UNMAPPED.txt
git add -A && git commit -qm "ticket work" >/dev/null

echo "############ PHASE 8 - promotion ############"
SHA=$(git rev-parse --short HEAD)
echo '{"tool_name":"Bash","tool_input":{"command":"./deploy.sh prod"}}' | bash "$H/promote-gate.sh" >/dev/null 2>&1
[ "$?" = "2" ] && ok "promote-gate blocks prod with no qa row / no runbook / no approval" || bad "promote-gate initial block"
printf 'last verified: %s\n' "$(date +%Y-%m-%d)" > docs/runbooks/rollback.md
git add -A && git commit -qm runbook >/dev/null; SHA=$(git rev-parse --short HEAD)
printf '| when | env | sha | smoke | regression | verify | by |\n|---|---|---|---|---|---|---|\n| now | qa | %s | pass | pass | pass | tester |\n' "$SHA" > .work/PROMOTIONS.md
touch ".crew/.approved-production-$SHA"
echo '{"tool_name":"Bash","tool_input":{"command":"./deploy.sh prod"}}' | bash "$H/promote-gate.sh" >/dev/null 2>&1
[ "$?" = "0" ] && ok "promote-gate ALLOWS prod once every gate is satisfied" || bad "promote-gate allow"
has .crew/.deploy-in-flight "deploy marker written for the Stop gate"
rm -f .work/PROMOTIONS.md
echo '{}' | bash "$H/verify-gate.sh" >/dev/null 2>&1
[ "$?" = "2" ] && ok "Stop gate refuses to end a turn after an unrecorded deploy" || bad "unrecorded deploy"

echo
echo "SCRIPT PHASES: $OK passed, $BAD failed"
echo "repo left at: $R"
[ "$BAD" -eq 0 ] || exit 1

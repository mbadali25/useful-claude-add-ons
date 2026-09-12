#!/usr/bin/env bash
# Dry-run checks for scripts/merge_gate.sh.
#
# No network, no credentials, no real config: merge_gate.sh resolves its
# transport through BB_CMD, so every test points that at _test/stub_bb.sh and
# feeds it canned responses. bb.sh is never executed, which is also why
# BITBUCKET_EMAIL / BITBUCKET_API_TOKEN are not needed and must not be read.
#
# What is under test is the part that cannot be checked by reading the code:
# which objects the scope resolver decides cover a branch under BOTH
# branch_match_kind schemes, that a failed export validation deletes nothing,
# that a restore never reuses a recorded id, and that a plan-limited write is
# reported as its own state instead of collapsing into "applied" or "failed".
#
# Creates nothing outside its own mktemp -d.
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
GATE="$HERE/../merge_gate.sh"
STUB="$HERE/stub_bb.sh"
PASS=0
FAIL=0

pass() { PASS=$((PASS + 1)); printf '  PASS  %s\n' "$1"; }
fail() { FAIL=$((FAIL + 1)); printf '  FAIL  %s\n' "$1"; }

command -v jq >/dev/null 2>&1 || { echo "FAIL: jq is not on PATH - cannot run these checks" >&2; exit 1; }
[ -f "$GATE" ] || { echo "FAIL: cannot find merge_gate.sh at $GATE" >&2; exit 1; }

TMP="$(mktemp -d)" || exit 1
trap 'rm -rf "$TMP"' EXIT

CASE=0
CASE_DIR=""
OUT=""
ERR=""
RC=0
LOG=""

# A mixed collection: both scope schemes, a write-protection kind, a kind that
# is not in the documented enum at all, and patterns that do and do not match.
RESTRICTIONS='{"pagelen":100,"page":1,"size":7,"values":[
  {"id":101,"kind":"require_approvals_to_merge","value":2,"branch_match_kind":"glob","pattern":"main"},
  {"id":102,"kind":"require_passing_builds_to_merge","value":1,"branch_match_kind":"glob","pattern":"*"},
  {"id":103,"kind":"require_tasks_to_be_completed","branch_match_kind":"glob","pattern":"release/*"},
  {"id":104,"kind":"enforce_merge_checks","branch_match_kind":"branching_model","branch_type":"production"},
  {"id":105,"kind":"push","branch_match_kind":"glob","pattern":"main"},
  {"id":106,"kind":"some_kind_added_after_this_script","branch_match_kind":"glob","pattern":"main"},
  {"id":107,"kind":"require_commits_behind","value":3,"branch_match_kind":"branching_model","branch_type":"development"}
]}'

new_case() {
  CASE=$((CASE + 1))
  CASE_DIR="$TMP/case$CASE"
  mkdir -p "$CASE_DIR/stub"
  LOG="$CASE_DIR/calls.log"
  : > "$LOG"
}

run_gate() {
  RC=0
  STUB_DIR="$CASE_DIR/stub" STUB_LOG="$LOG" BB_CMD="$STUB" \
    bash "$GATE" "$@" >"$CASE_DIR/out" 2>"$CASE_DIR/err" || RC=$?
  OUT="$(cat "$CASE_DIR/out")"
  ERR="$(cat "$CASE_DIR/err")"
}

calls_of() {
  local n
  n="$(grep -c "^$1$(printf '\t')" "$LOG" 2>/dev/null)" || n=0
  printf '%s' "$n"
}

want_count() {
  if [ "$2" = "$3" ]; then pass "$1 ($2)"; else fail "$1: got '$2', expected '$3'"; fi
}

want_nonzero_rc() {
  if [ "$RC" -ne 0 ]; then pass "$1 (rc=$RC)"; else fail "$1: exited 0"; fi
}

want_contains() {
  case "$2" in *"$3"*) pass "$1" ;; *) fail "$1: output does not contain '$3'" ;; esac
}

want_missing() {
  case "$2" in *"$3"*) fail "$1: output unexpectedly contains '$3'" ;; *) pass "$1" ;; esac
}

echo "== scope: a branching_model object is never resolved by guessing =="
new_case
printf '%s' "$RESTRICTIONS" > "$CASE_DIR/stub/1.body"
run_gate disable ws repo --branch main --export-to "$CASE_DIR/backup.json"
want_count "exits 3 when a scope is undetermined" "$RC" "3"
want_count "no DELETE was issued" "$(calls_of DELETE)" "0"
want_contains "names the undetermined production object" "$OUT" "UNDETERMINED id=104"
want_contains "names the undetermined development object" "$OUT" "UNDETERMINED id=107"
want_contains "tells the user how to resolve it" "$ERR" "--branch-type"
if [ -f "$CASE_DIR/backup.json" ] && [ "$(jq '.values | length' "$CASE_DIR/backup.json" 2>/dev/null)" = "7" ]; then
  pass "the export is still written and complete before the refusal"
else
  fail "the export should be complete even when the plan is refused"
fi

echo "== scope: --branch-type none decides every branching_model object =="
new_case
printf '%s' "$RESTRICTIONS" > "$CASE_DIR/stub/1.body"
run_gate disable ws repo --branch main --branch-type none --export-to "$CASE_DIR/backup.json"
want_count "exits 0" "$RC" "0"
want_count "deletes only the two covering merge-gate globs" "$(calls_of DELETE)" "2"
want_contains "deleted id=101 (glob 'main')" "$(cat "$LOG")" "branch-restrictions/101"
want_contains "deleted id=102 (glob '*' matches main)" "$(cat "$LOG")" "branch-restrictions/102"
want_missing "did not delete id=103 (release/* does not match main)" "$(cat "$LOG")" "branch-restrictions/103"
want_missing "did not delete id=105 (push is write protection, not a merge check)" "$(cat "$LOG")" "branch-restrictions/105"
want_missing "did not delete id=106 (kind outside the documented enum)" "$(cat "$LOG")" "branch-restrictions/106"
want_contains "prints a reason for the skipped write-protection kind" "$OUT" "branch write protection"
want_contains "prints a reason for the unknown kind" "$OUT" "not exhaustive"
want_contains "scopes its claim to the kinds it manages" "$OUT" "merge-gate kinds this script"

echo "== scope: a declared branch type is deleted under the other scheme =="
new_case
printf '%s' "$RESTRICTIONS" > "$CASE_DIR/stub/1.body"
run_gate disable ws repo --branch main --branch-type production,release --export-to "$CASE_DIR/backup.json"
want_count "exits 0" "$RC" "0"
want_count "deletes the branching_model object too" "$(calls_of DELETE)" "3"
want_contains "deleted id=104 (branch_type production)" "$(cat "$LOG")" "branch-restrictions/104"
want_missing "did not delete id=107 (development was not declared)" "$(cat "$LOG")" "branch-restrictions/107"

echo "== export validation: a short export blocks every delete =="
new_case
printf '%s' '{"pagelen":100,"page":1,"size":7,"values":[
  {"id":201,"kind":"require_approvals_to_merge","value":1,"branch_match_kind":"glob","pattern":"main"},
  {"id":202,"kind":"require_tasks_to_be_completed","branch_match_kind":"glob","pattern":"main"}]}' \
  > "$CASE_DIR/stub/1.body"
run_gate disable ws repo --branch main --export-to "$CASE_DIR/backup.json"
want_nonzero_rc "exits non-zero on a short export"
want_count "no DELETE was issued" "$(calls_of DELETE)" "0"
want_contains "says nothing was deleted" "$ERR" "nothing was deleted"
if [ -f "$CASE_DIR/backup.json" ]; then
  fail "the unvalidated export must not be moved into place"
else
  pass "the destination file was never created"
fi

echo "== export validation: pagination with no size cannot be verified =="
new_case
printf '%s' '{"pagelen":1,"page":1,"values":[{"id":301,"kind":"push","branch_match_kind":"glob","pattern":"main"}],
  "next":"https://api.bitbucket.org/2.0/repositories/ws/repo/branch-restrictions?page=2"}' \
  > "$CASE_DIR/stub/1.body"
printf '%s' '{"pagelen":1,"page":2,"values":[{"id":302,"kind":"force","branch_match_kind":"glob","pattern":"main"}]}' \
  > "$CASE_DIR/stub/2.body"
run_gate disable ws repo --branch main --export-to "$CASE_DIR/backup.json"
want_nonzero_rc "exits non-zero when completeness cannot be checked"
want_count "no DELETE was issued" "$(calls_of DELETE)" "0"

echo "== export: follows pagination and keeps every kind and scope =="
new_case
printf '%s' '{"pagelen":2,"page":1,"size":3,"values":[
  {"id":401,"kind":"require_approvals_to_merge","value":1,"branch_match_kind":"glob","pattern":"main"},
  {"id":402,"kind":"enforce_merge_checks","branch_match_kind":"branching_model","branch_type":"production"}],
  "next":"https://api.bitbucket.org/2.0/repositories/ws/repo/branch-restrictions?page=2"}' \
  > "$CASE_DIR/stub/1.body"
printf '%s' '{"pagelen":2,"page":2,"size":3,"values":[
  {"id":403,"kind":"push","branch_match_kind":"glob","pattern":"main"}]}' \
  > "$CASE_DIR/stub/2.body"
run_gate export ws repo "$CASE_DIR/all.json"
want_count "exits 0" "$RC" "0"
want_count "second page was requested" "$(calls_of GET)" "2"
want_count "every object landed in the file" "$(jq '.values | length' "$CASE_DIR/all.json" 2>/dev/null)" "3"
want_contains "kept the branching_model scope" "$(cat "$CASE_DIR/all.json" 2>/dev/null)" '"branch_type": "production"'
want_contains "kept the write-protection kind an unfiltered export must carry" "$(cat "$CASE_DIR/all.json" 2>/dev/null)" '"push"'

echo "== restore: POSTs fresh objects and never reuses a recorded id =="
new_case
cat > "$CASE_DIR/export.json" <<'JSON'
{"tool":"merge_gate.sh","format":1,"workspace":"ws","repository":"repo","count":2,
 "values":[
  {"id":999001,"kind":"require_approvals_to_merge","value":2,"branch_match_kind":"glob","pattern":"main"},
  {"id":999002,"kind":"enforce_merge_checks","branch_match_kind":"branching_model","branch_type":"production"}]}
JSON
printf '%s' '{"pagelen":100,"page":1,"size":0,"values":[]}' > "$CASE_DIR/stub/1.body"
run_gate enable ws repo --from-export "$CASE_DIR/export.json"
want_count "exits 0" "$RC" "0"
want_count "one POST per object" "$(calls_of POST)" "2"
want_count "no PUT by recorded id" "$(calls_of PUT)" "0"
want_missing "no recorded id reaches the wire" "$(cat "$LOG")" "999001"
want_contains "rebuilt the glob scope" "$(cat "$LOG")" '"branch_match_kind":"glob","pattern":"main"'
want_contains "rebuilt the branching_model scope" "$(cat "$LOG")" '"branch_type":"production"'
want_contains "carried the integer value" "$(cat "$LOG")" '"value":2'

echo "== premium: a plan-limited write is its own state =="
new_case
printf '%s' '{"pagelen":100,"page":1,"size":0,"values":[]}' > "$CASE_DIR/stub/1.body"
# Calls 2-5 are the four preset POSTs; the last one is enforce_merge_checks.
printf '%s' '{"error":{"message":"This feature requires a Premium plan."}}' > "$CASE_DIR/stub/5.body"
echo 400 > "$CASE_DIR/stub/5.status"
run_gate enable ws repo --branch main
want_count "a plan limitation does not fail the run" "$RC" "0"
want_contains "reports the third state" "$OUT" "not-available-on-this-plan"
want_contains "the state survives into the summary" "$OUT" "not-available-on-this-plan 1"
want_contains "three applied" "$OUT" "applied 3"
want_contains "zero failed" "$OUT" "failed 0"
want_contains "quotes what the API said" "$OUT" "requires a Premium plan"
want_contains "names the premium-only kinds" "$OUT" "enforce_merge_checks"

echo "== an unclassifiable error is failed, not quietly a plan limit =="
new_case
printf '%s' '{"pagelen":100,"page":1,"size":0,"values":[]}' > "$CASE_DIR/stub/1.body"
printf '%s' '{"error":{"message":"branchrestriction already exists"}}' > "$CASE_DIR/stub/2.body"
echo 400 > "$CASE_DIR/stub/2.status"
run_gate enable ws repo --branch main
want_nonzero_rc "exits non-zero when a write failed"
want_contains "counted as failed" "$OUT" "failed 1"
want_contains "not counted as a plan limitation" "$OUT" "not-available-on-this-plan 0"

echo "== enable is idempotent: existing objects are reported, not re-POSTed =="
new_case
printf '%s' '{"pagelen":100,"page":1,"size":4,"values":[
  {"id":501,"kind":"require_approvals_to_merge","value":1,"branch_match_kind":"glob","pattern":"main"},
  {"id":502,"kind":"require_tasks_to_be_completed","branch_match_kind":"glob","pattern":"main"},
  {"id":503,"kind":"require_passing_builds_to_merge","value":1,"branch_match_kind":"glob","pattern":"main"},
  {"id":504,"kind":"enforce_merge_checks","branch_match_kind":"glob","pattern":"main"}]}' \
  > "$CASE_DIR/stub/1.body"
run_gate enable ws repo --branch main
want_count "exits 0" "$RC" "0"
want_count "no POST" "$(calls_of POST)" "0"
want_contains "all four already present" "$OUT" "already-present 4"

echo "== a wrong value is corrected with PUT, not reported as applied-as-is =="
new_case
printf '%s' '{"pagelen":100,"page":1,"size":1,"values":[
  {"id":601,"kind":"require_approvals_to_merge","value":5,"branch_match_kind":"glob","pattern":"main"}]}' \
  > "$CASE_DIR/stub/1.body"
run_gate enable ws repo --branch main
want_count "exits 0" "$RC" "0"
want_count "one PUT for the value change" "$(calls_of PUT)" "1"
want_contains "PUT carries only a value" "$(cat "$LOG")" '{"value":1}'
want_contains "PUT targets the live id" "$(cat "$LOG")" "branch-restrictions/601"
want_contains "says what the value was" "$OUT" "(was 5)"

echo "== an incomplete export entry fails instead of restoring something else =="
new_case
cat > "$CASE_DIR/export.json" <<'JSON'
{"tool":"merge_gate.sh","format":1,"count":3,
 "values":[
  {"id":801,"kind":"require_approvals_to_merge","value":1,"branch_match_kind":"glob"},
  {"id":802,"kind":"require_passing_builds_to_merge","branch_match_kind":"glob","pattern":"main"},
  {"id":803,"kind":"enforce_merge_checks","branch_match_kind":"branching_model"}]}
JSON
# A live object that is itself malformed - no scope at all. Nothing in the
# desired set may be matched against it.
printf '%s' '{"pagelen":100,"page":1,"size":1,"values":[
  {"id":804,"kind":"require_approvals_to_merge","value":9}]}' > "$CASE_DIR/stub/1.body"
run_gate enable ws repo --from-export "$CASE_DIR/export.json"
want_nonzero_rc "exits non-zero when an entry cannot be restored"
want_count "all three are failed" "$(printf '%s' "$OUT" | grep -c 'failed 3')" "1"
want_count "nothing was POSTed" "$(calls_of POST)" "0"
want_count "nothing was PUT" "$(calls_of PUT)" "0"
want_contains "a glob entry with no pattern is failed" "$ERR" "glob scope with no pattern"
want_contains "a branching_model entry with no branch_type is failed" "$ERR" "no branch_type"
want_contains "a value kind with no value is failed" "$ERR" "nothing to restore it to"
want_missing "the malformed live object was not adopted as already-present" "$OUT" "already-present 1"

echo "== main-branch resolution when --branch is omitted =="
new_case
printf '%s' '{"name":"repo","mainbranch":{"name":"trunk"}}' > "$CASE_DIR/stub/1.body"
printf '%s' '{"pagelen":100,"page":1,"size":1,"values":[
  {"id":701,"kind":"require_tasks_to_be_completed","branch_match_kind":"glob","pattern":"trunk"}]}' \
  > "$CASE_DIR/stub/2.body"
run_gate disable ws repo --branch-type none --export-to "$CASE_DIR/backup.json"
want_count "exits 0" "$RC" "0"
want_contains "resolved the main branch from the repo" "$OUT" "target branch: trunk"
want_count "deleted the object covering it" "$(calls_of DELETE)" "1"

echo "== restore: users and groups survive the export-to-restore round trip =="
new_case
cat > "$CASE_DIR/export.json" <<'JSON'
{"tool":"merge_gate.sh","format":1,"workspace":"ws","repository":"repo","count":1,
 "values":[
  {"id":901,"kind":"restrict_merges","branch_match_kind":"glob","pattern":"main",
   "users":[{"uuid":"{user-1}","display_name":"Ann"}],
   "groups":[{"slug":"leads","name":"Leads"}]}]}
JSON
printf '%s' '{"pagelen":100,"page":1,"size":0,"values":[]}' > "$CASE_DIR/stub/1.body"
run_gate enable ws repo --from-export "$CASE_DIR/export.json"
want_count "exits 0" "$RC" "0"
want_count "one POST for the restriction" "$(calls_of POST)" "1"
want_contains "carried the users array" "$(cat "$LOG")" '"uuid":"{user-1}"'
want_contains "carried the groups array" "$(cat "$LOG")" '"slug":"leads"'

echo "== restore: an export with no .values key fails instead of restoring nothing =="
new_case
printf '%s' '{}' > "$CASE_DIR/export.json"
run_gate enable ws repo --from-export "$CASE_DIR/export.json"
want_nonzero_rc "exits non-zero on a values-less export"
want_count "no POST was issued" "$(calls_of POST)" "0"
want_contains "names the missing .values array" "$ERR" "no top-level .values array"

echo "== restore: a foreign export warns but still restores =="
new_case
cat > "$CASE_DIR/export.json" <<'JSON'
{"tool":"merge_gate.sh","format":1,"workspace":"other-ws","repository":"other-repo","count":0,
 "values":[]}
JSON
printf '%s' '{"pagelen":100,"page":1,"size":0,"values":[]}' > "$CASE_DIR/stub/1.body"
run_gate enable ws repo --from-export "$CASE_DIR/export.json"
want_count "exits 0 - a cross-repo export is a warning, not a failure" "$RC" "0"
want_contains "warns about the mismatched origin" "$ERR" "WARNING"
want_contains "names where the export came from" "$ERR" "other-ws/other-repo"
want_contains "names the intended target" "$ERR" "not the target ws/repo"

printf '\n%s passed, %s failed\n' "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ] || exit 1

#!/usr/bin/env bash
# Offline checks for scripts/merge_gate.sh.
#
# No network, no credentials, no real config: merge_gate.sh resolves its
# transport through GH_CMD, so every test points that at _test/stub_gh.sh and
# feeds it canned responses. The real `gh` is never executed, which is also why
# no GitHub auth is needed and none must be read.
#
# What is under test is the part that cannot be checked by reading the code:
# that --dry-run really sends nothing, that an export captures BOTH gate
# surfaces including the rules the list endpoint omits, that "could not read"
# never collapses into "nothing configured", that enable has no preset to fall
# back on, and that the two failure exits (3 = nothing deleted, 4 = partial
# writes) fire where they should and name what landed.
#
# Creates nothing outside its own mktemp -d.
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
GATE="$HERE/../merge_gate.sh"
STUB="$HERE/stub_gh.sh"
PASS=0
FAIL=0

pass() { PASS=$((PASS + 1)); printf '  PASS  %s\n' "$1"; }
fail() { FAIL=$((FAIL + 1)); printf '  FAIL  %s\n' "$1"; }

command -v jq >/dev/null 2>&1 || { echo "FAIL: jq is not on PATH - cannot run these checks" >&2; exit 1; }
[ -f "$GATE" ] || { echo "FAIL: cannot find merge_gate.sh at $GATE" >&2; exit 1; }
[ -f "$STUB" ] || { echo "FAIL: cannot find stub_gh.sh at $STUB" >&2; exit 1; }

TMP="$(mktemp -d)" || exit 1
trap 'rm -rf "$TMP"' EXIT

CASE=0
CASE_DIR=""
OUT=""
ERR=""
RC=0
LOG=""

REPO_BODY='{"name":"repo","default_branch":"main"}'
NOT_PROTECTED='{"message":"Branch not protected","documentation_url":"https://docs.github.com/rest","status":"404"}'
# The load-bearing fixture. Reading a protected branch without admin answers
# 404 with THIS message, not 403 - verified against repos/cli/cli, whose trunk
# is protected. Only the "Branch not protected" body means absent.
NO_ACCESS='{"message":"Not Found","documentation_url":"https://docs.github.com/rest","status":"404"}'
SIGNATURES='{"url":"https://api.github.com/x","enabled":false}'

# A classic protection document in the shape GET returns it: actors as objects,
# every toggle wrapped in {enabled: ...}, plus url keys PUT rejects.
CLASSIC='{
  "url":"https://api.github.com/repos/o/r/branches/main/protection",
  "required_status_checks":{"url":"https://api.github.com/x","strict":true,
    "contexts":["ci/build"],"checks":[{"context":"ci/build","app_id":4567}],
    "contexts_url":"https://api.github.com/y"},
  "required_pull_request_reviews":{"url":"https://api.github.com/z",
    "dismiss_stale_reviews":true,"require_code_owner_reviews":true,
    "required_approving_review_count":2,"require_last_push_approval":false,
    "dismissal_restrictions":{"url":"https://api.github.com/d",
      "users":[{"login":"ann","id":11,"type":"User"}],
      "teams":[{"slug":"leads","id":22}],"apps":[]}},
  "restrictions":{"url":"https://api.github.com/s",
    "users":[{"login":"bob","id":33,"type":"User"}],
    "teams":[{"slug":"release","id":44}],
    "apps":[{"slug":"my-app","id":55}]},
  "enforce_admins":{"url":"https://api.github.com/e","enabled":true},
  "required_linear_history":{"enabled":true},
  "allow_force_pushes":{"enabled":false},
  "allow_deletions":{"enabled":false},
  "required_conversation_resolution":{"enabled":true},
  "lock_branch":{"enabled":false},
  "allow_fork_syncing":{"enabled":true}
}'

# The list endpoint's rows: no `rules`, no `conditions`. Verified live against
# repos/facebook/react/rulesets. An export built from these alone restores an
# empty ruleset carrying only a name.
LIST_TWO='[
  {"id":11,"name":"Main gate","target":"branch","source_type":"Repository","source":"o/r","enforcement":"active"},
  {"id":22,"name":"Release gate","target":"branch","source_type":"Repository","source":"o/r","enforcement":"active"}
]'
DETAIL_11='{"id":11,"name":"Main gate","target":"branch","source_type":"Repository","source":"o/r",
  "enforcement":"active","node_id":"RRS_x","created_at":"2026-01-01T00:00:00Z","updated_at":"2026-01-02T00:00:00Z",
  "current_user_can_bypass":"never","_links":{"self":{"href":"https://api.github.com/rs/11"}},
  "conditions":{"ref_name":{"include":["refs/heads/main"],"exclude":[]}},
  "bypass_actors":[{"actor_id":5,"actor_type":"Team","bypass_mode":"pull_request"}],
  "rules":[{"type":"deletion"},{"type":"pull_request","parameters":{"required_approving_review_count":2}}]}'
DETAIL_22='{"id":22,"name":"Release gate","target":"branch","source_type":"Repository","source":"o/r",
  "enforcement":"active","node_id":"RRS_y",
  "conditions":{"ref_name":{"include":["refs/heads/release/*"],"exclude":[]}},
  "rules":[{"type":"non_fast_forward"}]}'

new_case() {
  CASE=$((CASE + 1))
  CASE_DIR="$TMP/case$CASE"
  mkdir -p "$CASE_DIR/stub"
  LOG="$CASE_DIR/calls.log"
  : > "$LOG"
}

stub() { # <n> <body-json>
  printf '%s' "$2" > "$CASE_DIR/stub/$1.body"
}
stub_status() { # <n> <code>
  printf '%s' "$2" > "$CASE_DIR/stub/$1.status"
}

run_gate() {
  RC=0
  STUB_DIR="$CASE_DIR/stub" STUB_LOG="$LOG" GH_CMD="$STUB" \
    bash "$GATE" "$@" >"$CASE_DIR/out" 2>"$CASE_DIR/err" || RC=$?
  OUT="$(cat "$CASE_DIR/out")"
  ERR="$(cat "$CASE_DIR/err")"
}

run_gate_with() { # <extra env assignment> <args...>
  local env_pair="$1"; shift
  RC=0
  env STUB_DIR="$CASE_DIR/stub" STUB_LOG="$LOG" GH_CMD="$STUB" "$env_pair" \
    bash "$GATE" "$@" >"$CASE_DIR/out" 2>"$CASE_DIR/err" || RC=$?
  OUT="$(cat "$CASE_DIR/out")"
  ERR="$(cat "$CASE_DIR/err")"
}

calls_of() {
  local n
  n="$(grep -c "^$1$(printf '\t')" "$LOG" 2>/dev/null)" || n=0
  printf '%s' "$n"
}
total_calls() {
  local n
  n="$(grep -c . "$LOG" 2>/dev/null)" || n=0
  printf '%s' "$n"
}
# Only the DELETE lines. Asserting against the whole log cannot tell a delete
# from the read that found the object - every id that is deleted was fetched
# first, so "the log mentions ruleset 22" is true either way.
deletes() { grep "^DELETE$(printf '\t')" "$LOG" 2>/dev/null || true; }
writes() { grep -E "^(DELETE|PUT|POST)$(printf '\t')" "$LOG" 2>/dev/null || true; }

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
want_no_file() {
  if [ -e "$2" ]; then fail "$1: $2 exists"; else pass "$1"; fi
}

echo "== dry run: sends nothing, writes nothing, and says so =="
new_case
# Every canned response is present, so a run that DID call would succeed and
# leave a file behind. Nothing may be logged and nothing may be created.
stub 1 "$REPO_BODY"
stub 2 "$CLASSIC"
stub 3 "$SIGNATURES"
stub 4 "$LIST_TWO"
run_gate disable o r --branch main --export-to "$CASE_DIR/backup.json" --dry-run
want_count "exits 0" "$RC" "0"
want_count "not one request was sent" "$(total_calls)" "0"
want_no_file "the export was not written either" "$CASE_DIR/backup.json"
want_contains "says plainly that nothing ran" "$OUT" "no request was sent and no file was written"
want_contains "names the calls it would make" "$OUT" "repos/o/r/rulesets?includes_parents=true"
want_contains "names the deletes it would make" "$OUT" "DELETE repos/o/r/branches/main/protection"

echo "== dry run: still runs nothing when the transport cannot run at all =="
new_case
RC=0
STUB_DIR="$CASE_DIR/stub" STUB_LOG="$LOG" GH_CMD=false \
  bash "$GATE" disable o r --branch main --export-to "$CASE_DIR/backup.json" --dry-run \
  >"$CASE_DIR/out" 2>"$CASE_DIR/err" || RC=$?
OUT="$(cat "$CASE_DIR/out")"
want_count "exits 0 with GH_CMD=false" "$RC" "0"
want_no_file "no export with GH_CMD=false" "$CASE_DIR/backup.json"

echo "== export: captures BOTH gate surfaces in one document =="
new_case
stub 1 "$REPO_BODY"
stub 2 "$CLASSIC"
stub 3 "$SIGNATURES"
stub 4 "$LIST_TWO"
stub 5 "$DETAIL_11"
stub 6 "$DETAIL_22"
run_gate export o r "$CASE_DIR/all.json" --branch main
want_count "exits 0" "$RC" "0"
want_count "classic is recorded present" "$(jq -r '.classic.state' "$CASE_DIR/all.json" 2>/dev/null)" "present"
want_count "the classic document is kept whole" \
  "$(jq -r '.classic.protection.required_pull_request_reviews.required_approving_review_count' "$CASE_DIR/all.json" 2>/dev/null)" "2"
want_count "rulesets are recorded read" "$(jq -r '.rulesets.state' "$CASE_DIR/all.json" 2>/dev/null)" "read"
want_count "both rulesets landed" "$(jq '.rulesets.values | length' "$CASE_DIR/all.json" 2>/dev/null)" "2"
# The list endpoint answers without `rules`; only a per-id GET has them.
want_count "each ruleset was fetched by id, not taken from the list" "$(calls_of GET)" "6"
want_count "the rules the list omits are in the export" \
  "$(jq '[.rulesets.values[].rules | length] | add' "$CASE_DIR/all.json" 2>/dev/null)" "3"
want_contains "bypass actors survive" "$(cat "$CASE_DIR/all.json" 2>/dev/null)" '"actor_type": "Team"'
want_contains "required signed commits are their own recorded fact" \
  "$(cat "$CASE_DIR/all.json" 2>/dev/null)" '"state": "read"'

echo "== export: an absent classic surface is absent, and rulesets still land =="
new_case
stub 1 "$REPO_BODY"
stub 2 "$NOT_PROTECTED"; stub_status 2 404
stub 3 "$LIST_TWO"
stub 4 "$DETAIL_11"
stub 5 "$DETAIL_22"
run_gate export o r "$CASE_DIR/all.json" --branch main
want_count "exits 0" "$RC" "0"
want_count "classic is absent, not unreadable" "$(jq -r '.classic.state' "$CASE_DIR/all.json" 2>/dev/null)" "absent"
want_count "the rulesets were still captured" "$(jq '.rulesets.values | length' "$CASE_DIR/all.json" 2>/dev/null)" "2"
want_contains "says why it calls it absent" "$(jq -r '.classic.detail' "$CASE_DIR/all.json" 2>/dev/null)" "Branch not protected"

echo "== exit 3: a classic surface it could not read is never 'none configured' =="
new_case
stub 1 "$REPO_BODY"
# 404 "Not Found" - the same status as an unprotected branch, a different body.
stub 2 "$NO_ACCESS"; stub_status 2 404
stub 3 "$LIST_TWO"
stub 4 "$DETAIL_11"
stub 5 "$DETAIL_22"
run_gate disable o r --branch main --export-to "$CASE_DIR/backup.json"
want_count "exits 3" "$RC" "3"
want_count "no DELETE was issued" "$(calls_of DELETE)" "0"
want_contains "names the surface it could not read" "$OUT" "UNREADABLE   classic"
want_contains "refuses to guess" "$ERR" "An unreadable surface is not an"
want_count "the export records it as unreadable" "$(jq -r '.classic.state' "$CASE_DIR/backup.json" 2>/dev/null)" "unreadable"
want_contains "and the export is still written as evidence" "$(jq -r '.classic.detail' "$CASE_DIR/backup.json" 2>/dev/null)" "Not Found"

echo "== exit 3: a 403 on the classic read blocks the same way =="
new_case
stub 1 "$REPO_BODY"
stub 2 '{"message":"Must have admin rights to Repository."}'; stub_status 2 403
stub 3 '[]'
run_gate disable o r --branch main --export-to "$CASE_DIR/backup.json"
want_count "exits 3" "$RC" "3"
want_count "no DELETE was issued" "$(calls_of DELETE)" "0"
want_contains "quotes what the API said" "$(jq -r '.classic.detail' "$CASE_DIR/backup.json" 2>/dev/null)" "admin rights"

echo "== the export is refused if classic says present but carries no object =="
# A 200 whose body is valid JSON but not a protection document. `jq -e .` accepts
# it, so the state becomes "present" while `.protection` holds nothing that can be
# PUT back. Validating only the ruleset count lets that through, the delete lands,
# and the file only fails hours later at restore time. Catch it before the delete.
new_case
stub 1 "$REPO_BODY"
stub 2 '[]'
stub 3 "$SIGNATURES"
stub 4 '[]'
run_gate disable o r --branch main --export-to "$CASE_DIR/backup.json"
want_nonzero_rc "refuses the run"
want_count "nothing was deleted" "$(calls_of DELETE)" "0"
want_contains "names the contradiction" "$ERR" "present but holds no protection object"
want_contains "says nothing landed" "$ERR" "nothing was written and nothing was deleted"
want_no_file "and no export was left behind" "$CASE_DIR/backup.json"

echo "== exit 3: a ruleset listed but unreadable blocks every delete =="
new_case
stub 1 "$REPO_BODY"
stub 2 "$NOT_PROTECTED"; stub_status 2 404
stub 3 "$LIST_TWO"
stub 4 "$DETAIL_11"
stub 5 '{"message":"Server Error"}'; stub_status 5 500
run_gate disable o r --branch main --export-to "$CASE_DIR/backup.json"
want_count "exits 3" "$RC" "3"
want_count "no DELETE was issued" "$(calls_of DELETE)" "0"
want_count "the unreadable one is recorded by id, not dropped" \
  "$(jq -r '.rulesets.unreadable[0].id' "$CASE_DIR/backup.json" 2>/dev/null)" "22"
want_count "the readable one is still recorded" "$(jq '.rulesets.values | length' "$CASE_DIR/backup.json" 2>/dev/null)" "1"

echo "== exit 3: an organization ruleset the repo endpoint cannot delete =="
new_case
stub 1 "$REPO_BODY"
stub 2 "$NOT_PROTECTED"; stub_status 2 404
stub 3 '[{"id":77,"name":"Org gate","target":"branch","source_type":"Organization","source":"acme","enforcement":"active"}]'
stub 4 '{"id":77,"name":"Org gate","target":"branch","source_type":"Organization","source":"acme","enforcement":"active",
  "conditions":{"ref_name":{"include":["~ALL"],"exclude":[]}},"rules":[{"type":"pull_request","parameters":{}}]}'
run_gate disable o r --branch main --export-to "$CASE_DIR/backup.json"
want_count "exits 3" "$RC" "3"
want_count "nothing was deleted" "$(calls_of DELETE)" "0"
want_contains "marks it inherited rather than skipping it silently" "$OUT" "INHERITED    id=77"
want_contains "explains that success would be a lie" "$ERR" "would still leave the merge"
want_contains "offers the escape hatch" "$ERR" "--allow-inherited"

echo "== --allow-inherited proceeds with what the repo does own, and says what stays =="
new_case
stub 1 "$REPO_BODY"
stub 2 "$NOT_PROTECTED"; stub_status 2 404
stub 3 '[{"id":77,"name":"Org gate","target":"branch","source_type":"Organization","source":"acme","enforcement":"active"},
  {"id":11,"name":"Main gate","target":"branch","source_type":"Repository","source":"o/r","enforcement":"active"}]'
stub 4 '{"id":77,"name":"Org gate","target":"branch","source_type":"Organization","source":"acme","enforcement":"active",
  "conditions":{"ref_name":{"include":["~ALL"],"exclude":[]}},"rules":[{"type":"pull_request","parameters":{}}]}'
stub 5 "$DETAIL_11"
run_gate disable o r --branch main --allow-inherited --export-to "$CASE_DIR/backup.json"
want_count "exits 0" "$RC" "0"
want_count "only the repo-level ruleset was deleted" "$(calls_of DELETE)" "1"
want_contains "and it was the right one" "$(deletes)" "repos/o/r/rulesets/11"
want_missing "the org ruleset was left alone" "$(deletes)" "repos/o/r/rulesets/77"
want_contains "the summary counts what stayed" "$OUT" "inherited-and-left 1"
# The exit code now says success on a branch that is still gated, and a caller
# that checks only the status is the normal case. The caveat has to reach stderr
# as well, or "--allow-inherited" silently means "gate off" forever after.
want_contains "warns on stderr that the gate is not off" "$ERR" "merge gate is NOT fully off"
want_contains "and names how many stand" "$ERR" "1 inherited ruleset(s) still gate main"

echo "== exit 3: a ref condition this script cannot evaluate =="
new_case
stub 1 "$REPO_BODY"
stub 2 "$NOT_PROTECTED"; stub_status 2 404
stub 3 '[{"id":33,"name":"Future gate","target":"branch","source_type":"Repository","source":"o/r","enforcement":"active"}]'
stub 4 '{"id":33,"name":"Future gate","target":"branch","source_type":"Repository","source":"o/r","enforcement":"active",
  "conditions":{"ref_name":{"include":["~SOME_SELECTOR_ADDED_LATER"],"exclude":[]}},"rules":[{"type":"deletion"}]}'
run_gate disable o r --branch main --export-to "$CASE_DIR/backup.json"
want_count "exits 3" "$RC" "3"
want_count "nothing was deleted" "$(calls_of DELETE)" "0"
want_contains "names the object it could not resolve" "$OUT" "UNDETERMINED id=33"
want_contains "refuses to guess" "$ERR" "will not guess whether they gate"

echo "== scope: a non-covering ruleset is skipped, a covering one goes =="
new_case
stub 1 "$REPO_BODY"
stub 2 "$NOT_PROTECTED"; stub_status 2 404
stub 3 "$LIST_TWO"
stub 4 "$DETAIL_11"
stub 5 "$DETAIL_22"
run_gate disable o r --branch main --export-to "$CASE_DIR/backup.json"
want_count "exits 0" "$RC" "0"
want_count "one delete" "$(calls_of DELETE)" "1"
want_contains "deleted the ruleset scoped to main" "$(deletes)" "repos/o/r/rulesets/11"
want_missing "left the release/* ruleset alone" "$(deletes)" "repos/o/r/rulesets/22"
want_contains "says why it skipped it" "$OUT" "does not match 'main'"

echo "== scope: target, enforcement and exclude each stand the ruleset down =="
new_case
stub 1 "$REPO_BODY"
stub 2 "$NOT_PROTECTED"; stub_status 2 404
stub 3 '[{"id":41,"name":"Push rules","target":"push","source_type":"Repository","source":"o/r","enforcement":"active"},
  {"id":42,"name":"Off","target":"branch","source_type":"Repository","source":"o/r","enforcement":"disabled"},
  {"id":43,"name":"Dry","target":"branch","source_type":"Repository","source":"o/r","enforcement":"evaluate"},
  {"id":44,"name":"Excluded","target":"branch","source_type":"Repository","source":"o/r","enforcement":"active"}]'
stub 4 '{"id":41,"name":"Push rules","target":"push","source_type":"Repository","enforcement":"active",
  "conditions":{"ref_name":{"include":["~ALL"],"exclude":[]}},"rules":[{"type":"file_path_restriction"}]}'
stub 5 '{"id":42,"name":"Off","target":"branch","source_type":"Repository","enforcement":"disabled",
  "conditions":{"ref_name":{"include":["~ALL"],"exclude":[]}},"rules":[{"type":"deletion"}]}'
stub 6 '{"id":43,"name":"Dry","target":"branch","source_type":"Repository","enforcement":"evaluate",
  "conditions":{"ref_name":{"include":["~ALL"],"exclude":[]}},"rules":[{"type":"deletion"}]}'
stub 7 '{"id":44,"name":"Excluded","target":"branch","source_type":"Repository","enforcement":"active",
  "conditions":{"ref_name":{"include":["~ALL"],"exclude":["refs/heads/main"]}},"rules":[{"type":"deletion"}]}'
run_gate disable o r --branch main --export-to "$CASE_DIR/backup.json"
want_count "exits 0" "$RC" "0"
want_count "nothing was deleted" "$(calls_of DELETE)" "0"
want_contains "a push ruleset is not a merge gate" "$OUT" "is not a branch gate"
want_contains "an already-disabled ruleset is left alone" "$OUT" "already 'disabled'"
want_contains "'evaluate' does not block a merge" "$OUT" "does not block a merge"
want_contains "an exclude match wins over ~ALL" "$OUT" "exclude matches 'main'"
want_count "all four were exported anyway" "$(jq '.rulesets.values | length' "$CASE_DIR/backup.json" 2>/dev/null)" "4"

echo "== ~DEFAULT_BRANCH is judged against the resolved default branch =="
new_case
stub 1 '{"name":"repo","default_branch":"trunk"}'
stub 2 "$NOT_PROTECTED"; stub_status 2 404
stub 3 '[{"id":51,"name":"Default gate","target":"branch","source_type":"Repository","source":"o/r","enforcement":"active"}]'
stub 4 '{"id":51,"name":"Default gate","target":"branch","source_type":"Repository","enforcement":"active",
  "conditions":{"ref_name":{"include":["~DEFAULT_BRANCH"],"exclude":[]}},"rules":[{"type":"deletion"}]}'
run_gate disable o r --export-to "$CASE_DIR/backup.json"
want_count "exits 0" "$RC" "0"
want_contains "resolved the default branch from the API" "$OUT" "target branch: trunk"
want_count "deleted the ruleset that gates it" "$(calls_of DELETE)" "1"

echo "== an unresolvable default branch dies asking for --branch =="
new_case
stub 1 '{"name":"repo"}'
run_gate disable o r --export-to "$CASE_DIR/backup.json"
want_nonzero_rc "exits non-zero"
want_count "nothing was deleted" "$(calls_of DELETE)" "0"
want_contains "asks for --branch by name" "$ERR" "pass --branch explicitly"
want_no_file "no export was written" "$CASE_DIR/backup.json"

echo "== exit 4: a partial delete names exactly what landed =="
new_case
stub 1 "$REPO_BODY"
stub 2 "$CLASSIC"
stub 3 "$SIGNATURES"
stub 4 "$LIST_TWO"
stub 5 "$DETAIL_11"
stub 6 "$DETAIL_22"
# 7 = DELETE the classic protection (succeeds), 8 = DELETE ruleset 11 (fails).
stub 8 '{"message":"Resource not accessible by integration"}'; stub_status 8 403
run_gate disable o r --branch main --export-to "$CASE_DIR/backup.json"
want_count "exits 4" "$RC" "4"
want_count "both deletes were attempted" "$(calls_of DELETE)" "2"
want_contains "the classic delete landed" "$(deletes)" "repos/o/r/branches/main/protection"
want_contains "names what landed" "$ERR" "What actually landed"
want_contains "and says which object it was" "$ERR" "deleted classic"
want_contains "quotes the failure verbatim" "$ERR" "Resource not accessible by integration"
want_contains "the summary counts the failure" "$OUT" "failed 1"

echo "== exit 4: when every delete fails, it says nothing landed =="
new_case
stub 1 "$REPO_BODY"
stub 2 "$NOT_PROTECTED"; stub_status 2 404
stub 3 "$LIST_TWO"
stub 4 "$DETAIL_11"
stub 5 "$DETAIL_22"
stub 6 '{"message":"nope"}'; stub_status 6 403
run_gate disable o r --branch main --export-to "$CASE_DIR/backup.json"
want_count "exits 4" "$RC" "4"
want_contains "does not imply a partial success" "$ERR" "nothing - every planned delete failed"

echo "== enable refuses without --from-export, and has no preset to fall back on =="
new_case
run_gate enable o r
want_count "exits 2 (usage)" "$RC" "2"
want_count "not one request was sent" "$(total_calls)" "0"
want_contains "names the missing flag" "$ERR" "requires --from-export"
want_contains "says there is no preset" "$ERR" "no preset and will not invent a merge gate"
want_contains "says nothing changed" "$ERR" "Nothing was changed"

echo "== enable refuses --branch: the export carries each object's own scope =="
new_case
run_gate enable o r --branch main --from-export /nonexistent.json
want_count "exits 2 (usage)" "$RC" "2"
want_count "not one request was sent" "$(total_calls)" "0"
want_contains "explains why" "$ERR" "every exported object carries its own scope"

echo "== enable refuses an export that records a surface it could not read =="
new_case
cat > "$CASE_DIR/export.json" <<'JSON'
{"tool":"merge_gate.sh","format":1,"owner":"o","repository":"r","branch":"main",
 "classic":{"state":"unreadable","detail":"HTTP 404: Not Found","protection":null,"required_signatures":null},
 "rulesets":{"state":"read","detail":"","declared":0,"count":0,"values":[],"unreadable":[]}}
JSON
run_gate enable o r --from-export "$CASE_DIR/export.json"
want_nonzero_rc "exits non-zero"
want_count "not one request was sent" "$(total_calls)" "0"
want_contains "names the surface" "$ERR" "records a gate surface it could not read"
want_contains "says what restoring it would do" "$ERR" "partial gate and report success"

echo "== enable refuses an export with no .rulesets.values key =="
new_case
printf '%s' '{"tool":"merge_gate.sh","format":1,"classic":{"state":"absent"},"rulesets":{"state":"read"}}' \
  > "$CASE_DIR/export.json"
run_gate enable o r --from-export "$CASE_DIR/export.json"
want_nonzero_rc "exits non-zero"
want_count "not one request was sent" "$(total_calls)" "0"
want_contains "refuses to restore nothing quietly" "$ERR" "refusing to silently restore nothing"

echo "== restore: the PUT body is the PUT shape, not the GET body echoed back =="
new_case
cat > "$CASE_DIR/export.json" <<JSON
{"tool":"merge_gate.sh","format":1,"owner":"o","repository":"r","branch":"main",
 "classic":{"state":"present","detail":"","protection":$CLASSIC,
            "required_signatures":{"state":"read","enabled":true,"detail":""}},
 "rulesets":{"state":"read","detail":"","declared":1,"count":1,
             "values":[$DETAIL_11],"unreadable":[]}}
JSON
stub 1 '[]'
run_gate enable o r --from-export "$CASE_DIR/export.json"
want_count "exits 0" "$RC" "0"
want_count "one PUT for the classic protection" "$(calls_of PUT)" "1"
want_contains "actors are logins and slugs, not the GET's objects" "$(cat "$LOG")" '"users":["bob"]'
want_contains "team slugs too" "$(cat "$LOG")" '"teams":["release"]'
want_contains "dismissal restrictions are converted as well" "$(cat "$LOG")" '"users":["ann"]'
want_missing "no numeric actor id reaches the wire" "$(cat "$LOG")" '"id":33'
want_missing "the GET-only url keys are dropped" "$(cat "$LOG")" 'contexts_url'
want_contains "enforce_admins is flattened to a bare bool" "$(cat "$LOG")" '"enforce_admins":true'
want_contains "so are the toggle objects" "$(cat "$LOG")" '"required_linear_history":true'
want_contains "required status checks keep their app-scoped checks" "$(cat "$LOG")" '"app_id":4567'
want_contains "signed commits are restored through their own endpoint" "$(cat "$LOG")" "protection/required_signatures"
want_count "and that is a POST" "$(calls_of POST)" "2"

echo "== restore: a ruleset is POSTed fresh and never carries its recorded id =="
new_case
cat > "$CASE_DIR/export.json" <<JSON
{"tool":"merge_gate.sh","format":1,"owner":"o","repository":"r","branch":"main",
 "classic":{"state":"absent","detail":"","protection":null,"required_signatures":null},
 "rulesets":{"state":"read","detail":"","declared":1,"count":1,
             "values":[$DETAIL_11],"unreadable":[]}}
JSON
stub 1 '[]'
stub 2 '{"id":9001,"name":"Main gate"}'
run_gate enable o r --from-export "$CASE_DIR/export.json"
want_count "exits 0" "$RC" "0"
want_count "one POST for the ruleset" "$(calls_of POST)" "1"
want_count "no PUT: nothing is restored by recorded id" "$(calls_of PUT)" "0"
want_missing "the recorded id never reaches the wire" "$(cat "$LOG")" '"id":11'
want_missing "server-owned fields are stripped" "$(cat "$LOG")" 'node_id'
want_missing "and so are the timestamps" "$(cat "$LOG")" 'created_at'
want_contains "the rules the gate is made of survive" "$(cat "$LOG")" '"type":"pull_request"'
want_contains "so do the conditions" "$(cat "$LOG")" '"include":["refs/heads/main"]'
want_contains "so do the bypass actors" "$(cat "$LOG")" '"bypass_mode":"pull_request"'
want_contains "reports the new id rather than the old one" "$OUT" "new id 9001"
want_contains "warns that the id changed" "$OUT" "not stable across delete/recreate"

echo "== restore: a list-shaped entry with no .rules is failed, not recreated empty =="
new_case
cat > "$CASE_DIR/export.json" <<'JSON'
{"tool":"merge_gate.sh","format":1,"owner":"o","repository":"r","branch":"main",
 "classic":{"state":"absent","detail":"","protection":null,"required_signatures":null},
 "rulesets":{"state":"read","detail":"","declared":1,"count":1,
             "values":[{"id":11,"name":"Main gate","target":"branch","source_type":"Repository","enforcement":"active"}],
             "unreadable":[]}}
JSON
stub 1 '[]'
run_gate enable o r --from-export "$CASE_DIR/export.json"
want_count "exits 4" "$RC" "4"
want_count "nothing was POSTed" "$(calls_of POST)" "0"
want_contains "names why it cannot be rebuilt" "$ERR" "carries no .rules"
want_contains "and says nothing landed" "$ERR" "nothing - every restore failed"

echo "== restore is idempotent: a ruleset already there is not duplicated =="
new_case
cat > "$CASE_DIR/export.json" <<JSON
{"tool":"merge_gate.sh","format":1,"owner":"o","repository":"r","branch":"main",
 "classic":{"state":"absent","detail":"","protection":null,"required_signatures":null},
 "rulesets":{"state":"read","detail":"","declared":1,"count":1,
             "values":[$DETAIL_11],"unreadable":[]}}
JSON
stub 1 '[{"id":88,"name":"Main gate","target":"branch","source_type":"Repository","enforcement":"active"}]'
run_gate enable o r --from-export "$CASE_DIR/export.json"
want_count "exits 0" "$RC" "0"
want_count "no POST" "$(calls_of POST)" "0"
want_contains "reports it as already present" "$OUT" "already-present"

echo "== restore: a foreign export warns but still restores =="
new_case
cat > "$CASE_DIR/export.json" <<'JSON'
{"tool":"merge_gate.sh","format":1,"owner":"other","repository":"elsewhere","branch":"main",
 "classic":{"state":"absent","detail":"","protection":null,"required_signatures":null},
 "rulesets":{"state":"read","detail":"","declared":0,"count":0,"values":[],"unreadable":[]}}
JSON
stub 1 '[]'
run_gate enable o r --from-export "$CASE_DIR/export.json"
want_count "exits 0 - a cross-repo export is a warning, not a failure" "$RC" "0"
want_contains "names where the export came from" "$ERR" "other/elsewhere"
want_contains "names the intended target" "$ERR" "not the target o/r"

echo "== restore: it will not write when it cannot read what is already there =="
new_case
cat > "$CASE_DIR/export.json" <<JSON
{"tool":"merge_gate.sh","format":1,"owner":"o","repository":"r","branch":"main",
 "classic":{"state":"present","detail":"","protection":$CLASSIC,
            "required_signatures":{"state":"read","enabled":false,"detail":""}},
 "rulesets":{"state":"read","detail":"","declared":0,"count":0,"values":[],"unreadable":[]}}
JSON
stub 1 '{"message":"Must have admin rights to Repository."}'; stub_status 1 403
run_gate enable o r --from-export "$CASE_DIR/export.json"
want_nonzero_rc "exits non-zero"
want_count "no PUT was issued" "$(calls_of PUT)" "0"
want_count "no POST was issued" "$(calls_of POST)" "0"
want_contains "says nothing changed" "$ERR" "Nothing was changed"

echo "== pagination: the Link header is followed, and a cycle is caught =="
new_case
stub 1 "$REPO_BODY"
stub 2 "$NOT_PROTECTED"; stub_status 2 404
stub 3 '[{"id":11,"name":"Main gate","target":"branch","source_type":"Repository","enforcement":"active"}]'
printf 'Link: <https://api.github.com/repos/o/r/rulesets?includes_parents=true&per_page=100&page=2>; rel="next"\r\n' \
  > "$CASE_DIR/stub/3.headers"
stub 4 '[{"id":22,"name":"Release gate","target":"branch","source_type":"Repository","enforcement":"active"}]'
stub 5 "$DETAIL_11"
stub 6 "$DETAIL_22"
run_gate export o r "$CASE_DIR/all.json" --branch main
want_count "exits 0" "$RC" "0"
want_count "the second page was requested" "$(calls_of GET)" "6"
want_count "both pages landed in the export" "$(jq '.rulesets.values | length' "$CASE_DIR/all.json" 2>/dev/null)" "2"

new_case
stub 1 "$REPO_BODY"
stub 2 "$NOT_PROTECTED"; stub_status 2 404
stub 3 '[{"id":11,"name":"Main gate","target":"branch","source_type":"Repository","enforcement":"active"}]'
# The 'next' points back at the URL just fetched; every unstubbed GET repeats it.
printf 'Link: <https://api.github.com/repos/o/r/rulesets?includes_parents=true&per_page=100>; rel="next"\r\n' \
  > "$CASE_DIR/stub/3.headers"
run_gate export o r "$CASE_DIR/all.json" --branch main
want_count "exits 3: the ruleset surface could not be read to the end" "$RC" "3"
want_count "rulesets are recorded unreadable, not as an empty list" \
  "$(jq -r '.rulesets.state' "$CASE_DIR/all.json" 2>/dev/null)" "unreadable"
want_contains "names the loop as the cause" "$(jq -r '.rulesets.detail' "$CASE_DIR/all.json" 2>/dev/null)" "cyclic"
want_contains "warns that enable will refuse this export" "$ERR" "will refuse it"

echo "== pagination: a long non-cyclic chain is capped, not followed forever =="
new_case
stub 1 "$REPO_BODY"
stub 2 "$NOT_PROTECTED"; stub_status 2 404
i=3
while [ "$i" -le 9 ]; do
  printf '[{"id":%d,"name":"g%d","target":"branch","source_type":"Repository","enforcement":"active"}]' "$i" "$i" \
    > "$CASE_DIR/stub/$i.body"
  printf 'Link: <https://api.github.com/repos/o/r/rulesets?includes_parents=true&per_page=100&page=%d>; rel="next"\r\n' "$i" \
    > "$CASE_DIR/stub/$i.headers"
  i=$((i + 1))
done
RC=0
env STUB_DIR="$CASE_DIR/stub" STUB_LOG="$LOG" GH_CMD="$STUB" MERGE_GATE_MAX_PAGES=4 \
  bash "$GATE" export o r "$CASE_DIR/all.json" --branch main >"$CASE_DIR/out" 2>"$CASE_DIR/err" || RC=$?
OUT="$(cat "$CASE_DIR/out")"
ERR="$(cat "$CASE_DIR/err")"
want_count "exits 3 once the page cap is exceeded" "$RC" "3"
want_count "stopped after MAX_PAGES list fetches, not before and not after" "$(calls_of GET)" "6"
want_contains "names the page cap as the cause" "$(jq -r '.rulesets.detail' "$CASE_DIR/all.json" 2>/dev/null)" "exceeded 4 page"

echo "== status: reports both surfaces and exits 3 when one is unreadable =="
new_case
stub 1 "$REPO_BODY"
stub 2 "$CLASSIC"
stub 3 "$SIGNATURES"
stub 4 "$LIST_TWO"
stub 5 "$DETAIL_11"
stub 6 "$DETAIL_22"
run_gate status o r --branch main
want_count "exits 0" "$RC" "0"
want_count "wrote nothing" "$(calls_of DELETE)" "0"
want_contains "reports classic" "$OUT" "classic branch protection: present"
want_contains "reports rulesets" "$OUT" "rulesets: read"
want_contains "classifies the covering ruleset as covering" "$OUT" "id=11"
want_contains "and the non-covering one as not" "$OUT" "does not match 'main'"

new_case
stub 1 "$REPO_BODY"
stub 2 "$NO_ACCESS"; stub_status 2 404
stub 3 '[]'
run_gate status o r --branch main
want_count "exits 3 when a surface is unreadable" "$RC" "3"
want_contains "says so rather than reporting an empty gate" "$ERR" 'not "nothing configured"'

printf '\n%s passed, %s failed\n' "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ] || exit 1

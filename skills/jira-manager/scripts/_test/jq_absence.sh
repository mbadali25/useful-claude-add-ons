#!/usr/bin/env bash
# Regression suite for jira-api.sh's behaviour when jq cannot be resolved.
#
# WHY THIS ASSERTS ON WHAT WAS SENT, NOT ON AN EXIT CODE.
# This defect shipped three times. Each round fixed the jq call sites known at
# the time and each round missed some, and every round an exit-code-only check
# would have stayed green: the broken functions exited 0. Measured on the
# unfixed file, jira_transition PROJ-123 31 with jq off PATH sent
#
#   curl -sS --fail-with-body -u <auth> -X POST -H 'Accept: application/json' \
#        https://<site>/rest/api/3/issue//transitions
#
# - no -d, no Content-Type, an empty path segment where the issue key belongs -
# and printed "(no content on success = 204)" with status 0. So the assertions
# below are on the recorded curl argv and on stdout, and the exit code is
# checked only as a secondary signal.
#
# HERMETIC. curl is a recording stub that contacts nothing; jq is either a
# symlink to the real binary or genuinely absent from PATH. Every JIRA_*
# variable is unset and replaced with a fixture value before anything is
# sourced - the machine this was written on had a real JIRA_API_TOKEN and a
# real JIRA_BASE_URL exported, and the first draft of the reproduction picked
# the real site up out of the ambient environment. Nothing is installed and
# nothing is written outside one mktemp -d.
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
API="$HERE/../jira-api.sh"
PASS=0
FAIL=0

pass() { PASS=$((PASS + 1)); printf '  PASS  %s\n' "$1"; }
fail() { FAIL=$((FAIL + 1)); printf '  FAIL  %s\n' "$1"; }

[ -f "$API" ] || { echo "FAIL: cannot find jira-api.sh at $API" >&2; exit 1; }

REAL_JQ="$(command -v jq 2>/dev/null)"
[ -n "$REAL_JQ" ] || { echo "TOOL MISSING: jq is not on PATH, so this suite DID NOT RUN. This is a missing tool, not a failed check. Install jq." >&2; exit 77; }

TMP="$(mktemp -d)" || exit 1
trap 'rm -rf "$TMP"' EXIT

# --- fixture PATHs -----------------------------------------------------------
# NOJQ holds only the recording curl stub, so jq is genuinely absent rather
# than shadowed. WITHJQ adds a symlink to the real jq. Neither contains any
# other binary, which is why everything below sticks to bash builtins.
#
# _jira_jq() (jira-api.sh:48-55) does not stop at PATH: after `jq`/`jq.exe` it
# also tries `${HOME}/scoop/shims/jq.exe` and three Chocolatey/Program-Files
# absolute paths, by `[[ -x "$c" ]]`, which reads the filesystem directly and
# is NOT affected by stripping PATH. So on a Windows/Git-Bash host with jq
# installed via Scoop, "nojq" mode with only PATH scrubbed would still find
# the real jq.exe through $HOME and silently defeat this suite's own
# hermeticity claim. `drive()` below repoints HOME for nojq mode to a fresh
# empty directory under $TMP to close that one; it CANNOT close the
# Chocolatey/Program-Files candidates the same way, because those are
# absolute system paths with no HOME-relative component to redirect - on a
# host where jq is installed via Chocolatey (not Scoop), "nojq" mode is not
# actually hermetic and this suite's jq-absent cases would silently exercise
# the real jq instead of the TOOL-MISSING path. That gap is not closed here.
mkdir -p "$TMP/nojq" "$TMP/nojq/home" "$TMP/withjq"
cat >"$TMP/nojq/curl" <<'STUB'
#!/bin/bash
# Recording stub. Never contacts anything. One arg per line into $CURL_LOG.
{ printf 'CALL\n'; for a in "$@"; do printf '%s\n' "$a"; done; printf 'ENDCALL\n'; } >>"$CURL_LOG"
printf '{"stub":"ok"}'
exit 0
STUB
chmod +x "$TMP/nojq/curl"
cp "$TMP/nojq/curl" "$TMP/withjq/curl"
ln -s "$REAL_JQ" "$TMP/withjq/jq"

# --- driver ------------------------------------------------------------------
# Runs one jira-api.sh function in a child bash with a controlled PATH and a
# scrubbed environment, and leaves the recorded argv in $LOG.
LOG=""
OUT=""
ERR=""
RC=0

drive() {
  local mode="$1"; shift
  local n=$((PASS + FAIL))
  LOG="$TMP/calls.$mode.$n.log"
  : >"$LOG"
  local errf="$TMP/err.$mode.$n"
  # The 2> belongs INSIDE the command substitution. Written as
  # `OUT=$( ... ) 2>"$errf"` it redirects the assignment, not the subshell, and
  # every stderr assertion below then reads an empty string and passes for the
  # wrong reason. That is the shape this whole suite exists to catch, so it is
  # worth not repeating in the suite itself.
  OUT=$( {
    unset JIRA_EMAIL JIRA_API_TOKEN JIRA_WORKSPACE JIRA_BASE_URL JIRA_CLOUD_ID
    export CURL_LOG="$LOG"
    export JIRA_EMAIL="fixture@example.invalid"
    export JIRA_API_TOKEN="fixture-token-not-real"
    export JIRA_BASE_URL="https://fixture.example.invalid"
    export PATH="$TMP/$mode"
    # HOME is repointed too, not just PATH - see the comment above the
    # fixture setup: _jira_jq()'s Scoop candidate is HOME-relative, and a
    # real jq under the ambient $HOME/scoop/shims would otherwise resolve
    # even with PATH scrubbed.
    [ "$mode" = nojq ] && export HOME="$TMP/nojq/home"
    # shellcheck disable=SC1090
    source "$API" && "$@"
  } 2>"$errf" )
  RC=$?
  ERR=$(<"$errf")
}

sent_urls() { grep -c '^ENDCALL$' "$LOG"; }
log_has()   { grep -qF -- "$1" "$LOG"; }

echo "jira-api.sh — jq absence regression suite"
echo

# --- 0. the fixture itself ---------------------------------------------------
drive nojq jira_whoami
if [ -n "$ERR" ] && [[ "$ERR" == *"fixture.example.invalid"* ]]; then
  fail "fixture leaks a real site into stderr"
elif log_has "https://fixture.example.invalid/rest/api/3/myself"; then
  pass "fixture is hermetic: a jq-free function still reaches the stub at the fixture host"
else
  fail "fixture is hermetic: expected the fixture host in the recorded call"
fi

# --- 1. MUST-FAIL CASE: jq absent must send NOTHING --------------------------
# This is the case the defect failed. Asserted on the recorded argv.
for fn_args in \
  "jira_transition PROJ-123 31" \
  "jira_edit_issue PROJ-123 {\"summary\":\"x\"}" \
  "jira_assign PROJ-123 5b10a2844" \
  "jira_add_comment PROJ-123 hello" \
  "jira_add_worklog PROJ-123 2h" \
  "jira_create_issue PROJ Task Summary" \
  "jira_link_issues PROJ-1 PROJ-2 Blocks" \
  "jira_search project=PROJ" \
  "jira_get_transitions PROJ-123" \
  "jira_delete_issue PROJ-123" \
  "jira_get_issue PROJ-123" \
  "jira_project_issue_types PROJ" \
  "jira_find_account_id someone@example.invalid" \
; do
  # shellcheck disable=SC2086
  drive nojq $fn_args
  fn="${fn_args%% *}"
  n=$(sent_urls)
  if [ "$n" -ne 0 ]; then
    fail "jq absent: $fn sent $n request(s) — must send none. Recorded: $(tr '\n' ' ' <"$LOG")"
  elif [[ "$ERR" != *"TOOL MISSING"* ]]; then
    fail "jq absent: $fn sent nothing but did not say TOOL MISSING. stderr=[$ERR]"
  elif [ "$RC" -eq 0 ]; then
    fail "jq absent: $fn exited 0"
  else
    pass "jq absent: $fn sends no request and reports TOOL MISSING (exit $RC)"
  fi
done

# --- 2. no empty path segment, ever ------------------------------------------
# The literal shape the defect produced. Checked across every recorded call.
drive nojq jira_transition PROJ-123 31
if log_has "/rest/api/3/issue//transitions"; then
  fail "jq absent: sent a URL with an empty path segment (/issue//transitions)"
else
  pass "jq absent: no URL with an empty path segment was sent"
fi

# --- 3. no false success on stdout -------------------------------------------
for fn_args in "jira_transition PROJ-123 31" "jira_edit_issue PROJ-123 {\"a\":1}" \
               "jira_assign PROJ-123 abc" "jira_delete_issue PROJ-123"; do
  # shellcheck disable=SC2086
  drive nojq $fn_args
  fn="${fn_args%% *}"
  if [[ "$OUT" == *"no content on success"* ]]; then
    fail "jq absent: $fn printed a success line. stdout=[$OUT]"
  else
    pass "jq absent: $fn prints no success line"
  fi
done

# --- 4. MUST-ALLOW: with jq present the right request is still sent ----------
drive withjq jira_transition PROJ-123 31
if ! log_has "https://fixture.example.invalid/rest/api/3/issue/PROJ-123/transitions"; then
  fail "jq present: jira_transition URL wrong. Recorded: $(tr '\n' ' ' <"$LOG")"
elif ! log_has 'Content-Type: application/json'; then
  fail "jq present: jira_transition sent no Content-Type"
elif ! log_has '{"transition":{"id":"31"}}' && ! log_has '"transition"'; then
  fail "jq present: jira_transition sent no transition payload"
elif ! log_has '-d'; then
  fail "jq present: jira_transition sent no -d payload flag"
else
  pass "jq present: jira_transition sends the keyed URL, Content-Type and a body"
fi

drive withjq jira_add_comment PROJ-123 "hello there"
if log_has "/issue/PROJ-123/comment" && log_has 'Content-Type: application/json' && log_has '-d'; then
  pass "jq present: jira_add_comment sends the keyed URL, Content-Type and a body"
else
  fail "jq present: jira_add_comment request wrong. Recorded: $(tr '\n' ' ' <"$LOG")"
fi

drive withjq jira_get_issue PROJ-123
if log_has "/issue/PROJ-123?fields=summary"; then
  pass "jq present: jira_get_issue sends the keyed URL"
else
  fail "jq present: jira_get_issue URL wrong. Recorded: $(tr '\n' ' ' <"$LOG")"
fi

# A key needing percent-encoding must still be encoded, not interpolated raw.
drive withjq jira_get_issue 'PROJ-1?expand=changelog'
if log_has "/issue/PROJ-1%3Fexpand%3Dchangelog?fields=summary"; then
  pass "jq present: a key containing ? and = is percent-encoded, not interpolated"
else
  fail "jq present: key was not percent-encoded. Recorded: $(tr '\n' ' ' <"$LOG")"
fi

# --- 5. the _jira_curl backstop, exercised directly --------------------------
# This is the guard that does not depend on any particular call site being
# remembered, so it is tested on its own rather than only through one.
drive withjq _jira_curl POST "/issue//transitions" '{"a":1}'
if [ "$(sent_urls)" -eq 0 ] && [[ "$ERR" == *"REQUEST NOT SENT"* ]]; then
  pass "backstop: a path with an empty segment is refused, not sent"
else
  fail "backstop: malformed path was sent. n=$(sent_urls) stderr=[$ERR]"
fi

drive withjq _jira_curl PUT "/issue/" '{"a":1}'
if [ "$(sent_urls)" -eq 0 ] && [[ "$ERR" == *"REQUEST NOT SENT"* ]]; then
  pass "backstop: a path with a trailing slash is refused, not sent"
else
  fail "backstop: trailing-slash path was sent. n=$(sent_urls) stderr=[$ERR]"
fi

drive withjq _jira_curl POST "/issue/PROJ-123/comment" ""
if [ "$(sent_urls)" -eq 0 ] && [[ "$ERR" == *"REQUEST NOT SENT"* ]]; then
  pass "backstop: a POST with an empty body is refused, not sent"
else
  fail "backstop: payload-less POST was sent. n=$(sent_urls) stderr=[$ERR]"
fi

drive withjq _jira_curl GET "/myself" ""
if [ "$(sent_urls)" -eq 1 ]; then
  pass "backstop: a bodyless GET is still allowed through"
else
  fail "backstop: a legitimate GET was blocked. n=$(sent_urls) stderr=[$ERR]"
fi

drive withjq _jira_curl DELETE "/issue/PROJ-123" ""
if [ "$(sent_urls)" -eq 1 ]; then
  pass "backstop: a bodyless DELETE is still allowed through"
else
  fail "backstop: a legitimate DELETE was blocked. n=$(sent_urls) stderr=[$ERR]"
fi

# --- 6. the neighbouring case: the one jq site NOT behind _jira_curl ---------
# jira_get_cloud_id pipes curl into jq directly, so neither the backstop nor
# any _jira_uri guard covers it. It is the documented first step of scoped-token
# onboarding, so a silent empty result here sends someone to configure a Cloud
# ID they never actually got.
drive nojq jira_get_cloud_id acme
if [ "$RC" -eq 0 ]; then
  fail "jq absent: jira_get_cloud_id exited 0. stdout=[$OUT]"
elif [[ "$ERR" != *"TOOL MISSING"* ]]; then
  fail "jq absent: jira_get_cloud_id did not say TOOL MISSING. stderr=[$ERR]"
elif [ -n "$OUT" ]; then
  fail "jq absent: jira_get_cloud_id printed something that could pass for a cloud id. stdout=[$OUT]"
else
  pass "jq absent: jira_get_cloud_id returns empty AND non-zero with TOOL MISSING (exit $RC)"
fi

drive withjq jira_get_cloud_id acme
if log_has "https://acme.atlassian.net/_edge/tenant_info"; then
  pass "jq present: jira_get_cloud_id still queries the tenant_info endpoint"
else
  fail "jq present: jira_get_cloud_id URL wrong. Recorded: $(tr '\n' ' ' <"$LOG")"
fi

# --- 7. no bare jq invocation survives in the source -------------------------
# Structural, so a call site added later without the resolver is caught by the
# suite rather than by a user on Windows.
BARE=$(grep -nE '(^|[^_[:alnum:]])jq[[:space:]]+-' "$API" | grep -v '_jira_jq' | grep -vE '^[0-9]+:[[:space:]]*#' || true)
if [ -n "$BARE" ]; then
  fail "source: bare jq invocation(s) bypass the resolver:"$'\n'"$BARE"
else
  pass "source: every jq invocation goes through _jira_jq"
fi

echo
echo "  $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]

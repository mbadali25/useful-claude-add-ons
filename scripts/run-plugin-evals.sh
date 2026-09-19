#!/usr/bin/env bash
# Runs the crew plugin's `claude plugin eval` suite under plugin/crew/evals/.
#
# One case at a time, not one combined invocation, because `--case <glob>`
# is a single-value filter (no documented comma-list or brace-expansion, and
# no "exclude" filter exists) - see https://code.claude.com/docs/en/plugin-evals.
# Per-case invocation sidesteps that entirely and is what was actually tested
# while writing this suite.
#
# Split into two groups for a second reason: one case
# (developer-runs-command-in-foreground) needs a Bash grant, and granting
# Bash requires the OS sandbox backend (bubblewrap+socat on Linux/WSL2).
# There is no backend on native Windows, so Claude Code refuses the run
# rather than running it unconfined - confirmed here, verbatim:
#   "sandbox required but unavailable: sandbox is enabled but the Windows
#    sandbox is not active on this session (feature gate off)"
# The other four cases only need Write/Edit, which needs no sandbox, so they
# run on any platform including native Windows.
#
# pm-does-not-write-code is a KNOWN, CURRENTLY FAILING case, not a bug in the
# case: run directly (see plugin/crew/README.md#evals and the CHANGELOG
# entry for this suite), the PM still edits the tempting one-line fix itself
# instead of dispatching a developer. The case format has no expected-fail /
# xfail field (checked against every prompt.md and case.yaml field this
# script's own doc-reading pass found), so this script tracks it by name in
# EXPECTED_FAIL_CASES instead: it always runs and always reports, but never
# flips this script's exit code for the ONE way it is meant to fail. Two
# things it does NOT swallow, both review-found:
#   - EXPECTED_FAIL_CASES is comma-separated (EVAL_EXPECTED_FAIL_CASES=
#     "case-one,case-two"), matching the .ps1 twin's `-split ","` exactly -
#     it used to be space-separated here, which meant the same env var value
#     matched on Windows and matched nothing at all under bash, silently
#     dropping the exemption (and the KNOWN failure then failed the gate for
#     real, on this platform only).
#   - An xfail-listed case that PASSES still fails this script (with a
#     "retire the xfail" message) rather than passing quietly - an exemption
#     nobody is ever told to remove can outlive the defect it was for and
#     mask a real regression the next time the case goes red.
#   - The exemption applies to exactly ONE shape: exit code 1 (the
#     documented "a case scored below the threshold" code) with a scored
#     result THIS invocation actually wrote (a non-empty "cases" array in
#     the json this run just produced, not a leftover from a previous run -
#     the file is deleted before every invocation for exactly that reason).
#     Exit 1 is overloaded (it also covers "no cases found" and "a case
#     file failed to load", neither of which produces scored data), and
#     every OTHER exit code (2, 127, 130, 143, ...) means something else
#     happened entirely - a cost ceiling, a missing CLI, an interruption.
#     None of those are "the case scored below threshold", so none of them
#     are ever exempted, xfail-listed or not. An exit-0 "pass" with no
#     scored result (an empty `cases` array - e.g. a --case filter that
#     matched nothing) is caught the same way and treated as a failure.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PLUGIN_DIR="$REPO_ROOT/plugin/crew"
THRESHOLD="${EVAL_THRESHOLD:-1.0}"
MAX_COST_USD="${EVAL_MAX_COST_USD:-15}"
OUT_DIR="${EVAL_OUTPUT_DIR:-$REPO_ROOT/.work/plugin-evals}"
EXPECTED_FAIL_CASES="${EVAL_EXPECTED_FAIL_CASES:-pm-does-not-write-code}"

GROUP_A_CASES=(
  pm-does-not-write-code
  qa-reviewer-stays-read-only
  developer-defers-unrelated-bug
  pm-answers-status-mid-pass
)
GROUP_B_CASE="developer-runs-command-in-foreground"

command -v claude >/dev/null 2>&1 || { echo "claude CLI not found on PATH" >&2; exit 127; }

mkdir -p "$OUT_DIR"
status=0
declare -a RESULT_FILES=()

is_expected_fail() {
  # Comma-separated, matching the .ps1 twin's `-split ","` - see the header
  # comment for why a mismatched separator here silently drops the exemption.
  local target="$1" name
  local IFS=','
  local -a fails
  read -ra fails <<< "$EXPECTED_FAIL_CASES"
  for name in "${fails[@]}"; do
    [ "$name" = "$target" ] && return 0
  done
  return 1
}

has_scored_result() {
  # True only when $1 is a non-empty file holding a real aggregate-result.json
  # ("cases" present, AND no individual run in it recorded an error) - i.e.
  # claude plugin eval actually evaluated the case cleanly, as opposed to
  # either erroring out before producing anything to score, or producing a
  # non-empty "cases" array from a run that itself errored (a rate limit, a
  # timeout - "a run that started but ended badly is still graded on what it
  # produced", per the docs, so a non-empty result with an error inside it
  # is NOT the same thing as a genuine scored failure).
  local f="$1"
  [ -s "$f" ] || return 1
  python3 -c '
import json, sys
try:
    with open(sys.argv[1], encoding="utf-8") as fh:
        doc = json.load(fh)
except Exception:
    sys.exit(1)
cases = doc.get("cases")
if not cases:
    sys.exit(1)
for c in cases:
    arms = c.get("arms", {}) or {}
    for arm_name in ("with", "without"):
        for run in (arms.get(arm_name) or []):
            if run.get("error"):
                sys.exit(1)
sys.exit(0)
' "$f" 2>/dev/null
}

run_case() {
  local case_name="$1"; shift
  local out_json="$OUT_DIR/$case_name.json"
  # Never let a result file from a PREVIOUS run count as evidence for THIS
  # one - a run that errors out without writing anything must not inherit a
  # stale pass or a stale scored-failure sitting there from last time.
  rm -f "$out_json"
  echo "== $case_name =="
  if claude plugin eval "$PLUGIN_DIR" \
      --case "$case_name" \
      --trust-plugin \
      --threshold "$THRESHOLD" \
      --max-cost-usd "$MAX_COST_USD" \
      --no-publish \
      --json "$out_json" \
      "$@"; then
    RESULT_FILES+=("$out_json")
    if ! has_scored_result "$out_json"; then
      echo "   $case_name exited 0 but produced no scored result (empty or missing 'cases') - a runner error (e.g. a --case filter that matched nothing), not a pass." >&2
      status=1
      return 0
    fi
    if is_expected_fail "$case_name"; then
      echo "   $case_name is listed in EXPECTED_FAIL_CASES but PASSED - retire the xfail (drop it from EVAL_EXPECTED_FAIL_CASES / this script's default) so a future regression is caught again instead of staying silently exempted." >&2
      status=1
    fi
    return 0
  else
    local code=$?
    RESULT_FILES+=("$out_json")
    # The exemption covers exactly ONE documented shape: exit 1 ("a case
    # scored below the threshold") with a result file THIS run actually
    # wrote, holding real scored case data. Exit 1 is overloaded (it also
    # covers "no cases found" / "a case file failed to load" / "a run
    # couldn't be started" - none of which produce scored data), which is
    # why has_scored_result is still required even at exit 1; any exit code
    # OTHER than 1 (2 = cost ceiling / partial, 127 = CLI missing, 130 =
    # interrupted, 143 = terminated, ...) is a runner error full stop, never
    # exempted regardless of what a leftover json happens to contain - which
    # is exactly why the file was deleted before this invocation ran.
    if [ "$code" -eq 1 ] && is_expected_fail "$case_name" && has_scored_result "$out_json"; then
      echo "   exit 1, but $case_name is in EXPECTED_FAIL_CASES and produced a real (scored) result from THIS run - not failing the gate." >&2
    else
      local extra=""
      if [ "$code" -ne 1 ]; then
        extra=" (exit $code is not the documented 'case scored below threshold' code - a runner error, never exempted regardless of xfail listing)"
      elif is_expected_fail "$case_name"; then
        extra=" (in EXPECTED_FAIL_CASES, but no scored result was produced by this run - a runner error is never exempted)"
      fi
      echo "   claude plugin eval exited $code for $case_name$extra" >&2
      status=1
    fi
    return 0
  fi
}

echo "== Group A: Write/Edit only, no sandbox needed =="
for c in "${GROUP_A_CASES[@]}"; do
  case "$c" in
    pm-does-not-write-code|developer-defers-unrelated-bug)
      run_case "$c" --scaffold --allow-tools Write Edit ;;
    *)
      run_case "$c" --allow-tools Write Edit ;;
  esac
done

echo
if command -v bwrap >/dev/null 2>&1 && command -v socat >/dev/null 2>&1; then
  echo "== Group B: $GROUP_B_CASE (needs Bash + sandbox; backend present) =="
  run_case "$GROUP_B_CASE" --allow-tools Bash
else
  echo "== Group B SKIPPED: $GROUP_B_CASE needs Bash, which needs the OS sandbox" >&2
  echo "   (bubblewrap + socat). Neither is on PATH here. Native Windows has no" >&2
  echo "   backend at all; run this under WSL2 or the Linux CI job instead." >&2
  echo "   Not a pass, not a fail - unverified on this machine." >&2
fi

echo
echo "== Delta table =="
printf '%-38s %6s %6s %7s  %s\n' "CASE" "WITH" "W/OUT" "D" "COST"
for f in "${RESULT_FILES[@]}"; do
  [ -f "$f" ] || { printf '%-38s %6s %6s %7s\n' "$(basename "$f" .json)" "n/a" "n/a" "n/a"; continue; }
  python3 - "$f" <<'PYEOF'
import json, sys
with open(sys.argv[1], encoding="utf-8") as fh:
    doc = json.load(fh)
for c in doc.get("cases", []):
    agg = c.get("aggregates", {})
    score = agg.get("score")
    delta = agg.get("delta")
    without = (score - delta) if (score is not None and delta is not None) else None
    cost = sum(r.get("costUsd", 0) or 0 for r in c.get("arms", {}).get("with", []) + c.get("arms", {}).get("without", []))
    fmt = lambda v: f"{v:.2f}" if v is not None else "n/a"
    dfmt = f"{delta:+.2f}" if delta is not None else "n/a"
    print(f"{c['name']:<38} {fmt(score):>6} {fmt(without):>6} {dfmt:>7}  ${cost:.2f}")
PYEOF
done

exit $status

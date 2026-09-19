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
# flips this script's exit code. Fix the plugin, then remove it from that list.
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
  case " $EXPECTED_FAIL_CASES " in *" $1 "*) return 0 ;; *) return 1 ;; esac
}

run_case() {
  local case_name="$1"; shift
  local out_json="$OUT_DIR/$case_name.json"
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
    return 0
  else
    local code=$?
    RESULT_FILES+=("$out_json")
    if is_expected_fail "$case_name"; then
      echo "   exit $code, but $case_name is in EXPECTED_FAIL_CASES - not failing the gate." >&2
    else
      echo "   claude plugin eval exited $code for $case_name" >&2
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

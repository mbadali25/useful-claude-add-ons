#!/usr/bin/env bash
# Runs the crew plugin's `claude plugin eval` suite under plugin/crew/evals/.
# Matched pair of scripts/run-plugin-evals.ps1 - change one, change the other.
#
# The cases are DISCOVERED, not listed here (L-0713): every folder under
# plugin/crew/evals/ holding a case.yaml, in name order. A list kept in this
# script still named five cases for roles crew 1.0 deleted, long after they
# stopped describing a shipped agent. With no case at all the script says
# "no eval cases" and exits 0 before it looks for the claude CLI: nothing ran,
# and it says so rather than reporting a pass.
#
# One case at a time, not one combined invocation, because `--case <glob>`
# is a single-value filter (no documented comma-list or brace-expansion, and
# no "exclude" filter exists) - see https://code.claude.com/docs/en/plugin-evals.
# Each case is granted Write and Edit (the point is that the role does not use
# a tool it HAS), plus `--scaffold` when its case.yaml names a scaffold_script.
#
# A case passes only with a scored result THIS invocation wrote: the result
# file is deleted before every invocation, an exit-0 run with an empty or
# errored "cases" array fails, and every non-zero exit fails.
#
# EVAL_PLUGIN_DIR points the runner at another plugin directory (its suite,
# scripts/_test/plugin-evals-runner.py, uses it); the default is plugin/crew.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PLUGIN_DIR="${EVAL_PLUGIN_DIR:-$REPO_ROOT/plugin/crew}"
THRESHOLD="${EVAL_THRESHOLD:-1.0}"
MAX_COST_USD="${EVAL_MAX_COST_USD:-15}"
OUT_DIR="${EVAL_OUTPUT_DIR:-$REPO_ROOT/.work/plugin-evals}"

CASES=()
for case_yaml in "$PLUGIN_DIR"/evals/*/case.yaml; do
  [ -f "$case_yaml" ] || continue
  CASES+=("$(basename "$(dirname "$case_yaml")")")
done
if [ "${#CASES[@]}" -eq 0 ]; then
  echo "no eval cases under $PLUGIN_DIR/evals/ - nothing ran (not a pass)"
  exit 0
fi

command -v claude >/dev/null 2>&1 || { echo "claude CLI not found on PATH" >&2; exit 127; }

mkdir -p "$OUT_DIR"
status=0
declare -a RESULT_FILES=()

has_scored_result() {
  # True only when $1 is a non-empty file holding a real aggregate-result.json
  # ("cases" present, AND no individual run in it recorded an error) - i.e.
  # claude plugin eval actually evaluated the case cleanly, as opposed to
  # either erroring out before producing anything to score, or producing a
  # non-empty "cases" array from a run that itself errored (a rate limit, a
  # timeout - "a run that started but ended badly is still graded on what it
  # produced", per the docs, so a non-empty result with an error inside it
  # is NOT the same thing as a genuine scored result).
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
  # stale pass sitting there from last time.
  rm -f "$out_json"
  echo "== $case_name =="
  local code=0
  claude plugin eval "$PLUGIN_DIR" \
      --case "$case_name" \
      --trust-plugin \
      --threshold "$THRESHOLD" \
      --max-cost-usd "$MAX_COST_USD" \
      --no-publish \
      --json "$out_json" \
      "$@" || code=$?
  RESULT_FILES+=("$out_json")
  if [ "$code" -ne 0 ]; then
    echo "   claude plugin eval exited $code for $case_name" >&2
    status=1
  elif ! has_scored_result "$out_json"; then
    echo "   $case_name exited 0 but produced no scored result (empty or missing 'cases') - a runner error (e.g. a --case filter that matched nothing), not a pass." >&2
    status=1
  fi
}

for c in "${CASES[@]}"; do
  if grep -q '^[[:space:]]*scaffold_script:' "$PLUGIN_DIR/evals/$c/case.yaml"; then
    run_case "$c" --scaffold --allow-tools Write Edit
  else
    run_case "$c" --allow-tools Write Edit
  fi
done

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

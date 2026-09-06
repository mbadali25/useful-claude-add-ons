#!/usr/bin/env bash
# _verify/ci-status.sh - assert the Marketplace workflow SUCCEEDED for a given sha.
#
# This exists because the obvious one-liner is vacuous three ways, all confirmed:
#
#   gh run list --limit 1 --json conclusion,headSha,workflowName
#
#   1. `gh run list` is a LISTING command. It exits 0 whether the run passed or
#      failed. `--status failure --limit 1` printed {"conclusion":"failure"} and
#      still exited 0.
#   2. `--limit 1` returns the most recent run of ANY workflow. In this repo that
#      was "MCP servers (Microsoft)" - not the Marketplace workflow that actually
#      gates registration.
#   3. Its headSha was a different commit from local HEAD, and nothing compared
#      the two. A gate can pass on a green run for code nobody is promoting.
#
# So: name the workflow, pin the sha, and fail on anything that is not success -
# including the case where no run exists yet, which must NOT read as a pass.
set -uo pipefail

cd "$(dirname "$0")/.." || exit 1

WORKFLOW="marketplace.yml"
SHA="${1:-$(git rev-parse HEAD)}"

command -v gh >/dev/null 2>&1 || { echo "FAIL: gh is not on PATH - cannot check CI"; exit 1; }

echo "CI check: $WORKFLOW @ ${SHA:0:12}"

RAW="$(gh run list --workflow="$WORKFLOW" --commit "$SHA" --limit 1 \
        --json conclusion,status,databaseId,headSha 2>&1)" || {
  echo "FAIL: gh call failed:"; echo "$RAW" | sed 's/^/       /'; exit 1; }

CONCLUSION="$(printf '%s' "$RAW" | python3 -c 'import json,sys
try: rows = json.load(sys.stdin)
except Exception: print("BAD-JSON"); raise SystemExit
print(rows[0]["conclusion"] or rows[0]["status"] if rows else "NO-RUN")' 2>/dev/null)"

case "$CONCLUSION" in
  success)
    echo "PASS: $WORKFLOW succeeded for ${SHA:0:12}"
    exit 0 ;;
  NO-RUN)
    # Deliberately a failure. "No run yet" means the sha is unproven, which is
    # exactly what this gate is supposed to catch - not something to wave through.
    echo "FAIL: no $WORKFLOW run exists for ${SHA:0:12} - the sha is unproven, not clean"
    exit 1 ;;
  BAD-JSON)
    echo "FAIL: could not parse gh output:"; echo "$RAW" | head -5 | sed 's/^/       /'; exit 1 ;;
  *)
    echo "FAIL: $WORKFLOW for ${SHA:0:12} is '$CONCLUSION', not success"
    exit 1 ;;
esac

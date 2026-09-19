#!/usr/bin/env bash
# Bisection script to find which test creates unwanted files/state
# Usage: ./find-polluter.sh <file_or_dir_to_check> <test_pattern>
# Example: ./find-polluter.sh '.git' 'src/**/*.test.ts'
#
# Modified from upstream superpowers 6.3.0 find-polluter.sh:
# - Iterate test files through a `while read` loop instead of unquoted word
#   splitting, so a filename containing whitespace is one argument to
#   `npm test`, not several.
# - Give the runner its own stdin (`< /dev/null`) instead of letting it
#   inherit the loop's, which is the here-string driving `read` below. A
#   runner that reads stdin to EOF would otherwise drain the remaining test
#   list and silently end the loop early -- the same landmine verify-gate.sh
#   documents for its own `while read` loop over a here-string.
# - Distinguish a runner that could not even complete (exit 126 or 127 --
#   missing binary, bad interpreter) from an ordinary failing test (any
#   other non-zero exit). Only the former aborts the investigation as
#   "RUNNER FAILED"; the pollution case IS a test that exits non-zero, so a
#   blanket "any non-zero is a runner failure" reported FOUND POLLUTER as
#   RUNNER FAILED and aborted before the pollution check ran. The pollution
#   check itself runs FIRST, before any exit-code classification at all --
#   a marker on disk is a polluter found regardless of exit code, including
#   126/127, so a test that pollutes and then hits a missing runner command
#   must still be reported as FOUND POLLUTER, not RUNNER FAILED.
# - An ordinary test failure that produced no pollution is recorded and the
#   bisection continues to the next candidate, instead of the runner's exit
#   status being swallowed entirely; the final verdict says "N tests failed
#   without pollution" and is not reported as clean.
# - Track how many tests actually ran; if none did (pattern matched nothing,
#   or every candidate was skipped because the pollution check already
#   existed before the first test), report "NO TESTS RAN" and exit
#   non-zero instead of a false-positive clean verdict.
# - Refuse a pattern with more than one '**' up front ("UNSUPPORTED
#   PATTERN") instead of translating it wrong. This is a crew-introduced
#   defect, not an upstream one: the second `-o -path` alternative below
#   (which crew added, to also match a file directly under the base
#   directory -- upstream's single form misses those) collapses '**/' to
#   nothing, so with a SECOND '**' the collapsed form and the uncollapsed
#   form both fail to match a file nested under it, and it is silently
#   never discovered.
# - Capture find's own exit status out of the `find | sort` discovery
#   pipeline (`sort`'s success otherwise masks a failing `find`, e.g. an
#   unreadable subtree) and refuse with "DISCOVERY FAILED" instead of
#   proceeding with a silently incomplete test list.
# - Set `pipefail` unconditionally rather than relying on the caller's
#   shell options. Without it, a caller who runs this script under their
#   own `bash -o pipefail` changes ITS behaviour too: `grep -o` exits 1 on
#   no match, and under a caller's pipefail that non-zero pipeline status
#   reaches the bare `VAR=$(...)` assignment and `set -e` aborts the
#   script silently, before discovery even runs, with no diagnostic. A
#   script's correctness must not depend on flags it did not itself set.

set -e
set -o pipefail

if [ $# -ne 2 ]; then
  echo "Usage: $0 <file_to_check> <test_pattern>"
  echo "Example: $0 '.git' 'src/**/*.test.ts'"
  exit 1
fi

POLLUTION_CHECK="$1"
TEST_PATTERN="$2"

echo "🔍 Searching for test that creates: $POLLUTION_CHECK"
echo "Test pattern: $TEST_PATTERN"
echo ""

# Get list of test files (find . emits ./-prefixed paths, so accept the
# pattern written with or without a leading ./)
TEST_PATTERN="${TEST_PATTERN#./}"

# The find translation below understands exactly one '**': it is matched
# two ways (against '**/x' for arbitrary depth, and with '**/' collapsed
# for zero depth -- the second alternative is crew's own addition, not
# upstream's) to cover both cases from a single occurrence. A SECOND
# '**' cannot be translated correctly by either variant and would silently
# match a narrower set than the pattern implies -- the exact false-clean
# bug class this script exists to prevent. Refuse rather than guess.
#
# Counted via parameter expansion rather than `grep -o | wc -l`: `grep`
# exits 1 on zero matches (a normal, expected pattern -- most test
# patterns have exactly one '**' and NEVER take this branch), and that
# non-zero status, on a bare `VAR=$(...)` assignment under `set -e`,
# aborted the script here with no output at all. The expansion form has
# no pipeline and nothing in it can signal "no match" as failure.
_STARSTAR_STRIPPED="${TEST_PATTERN//\*\*/}"
STARSTAR_COUNT=$(( (${#TEST_PATTERN} - ${#_STARSTAR_STRIPPED}) / 2 ))
if [ "$STARSTAR_COUNT" -gt 1 ]; then
  echo "🚫 UNSUPPORTED PATTERN: more than one ** — split the search or use a single ** prefix"
  echo "   Pattern: $TEST_PATTERN"
  exit 1
fi

# find -path can't match '**/' against zero directory levels, so a pattern
# like src/**/*.test.ts would skip src/top.test.ts; also try the pattern
# with '**/' collapsed to cover files directly under the base directory.
#
# `find | sort` inside a bare `VAR=$(...)` assignment would otherwise
# discard find's own exit status -- sort's success masks it, so an
# unreadable subtree (find exits 1) silently trims the test list and the
# script could report "all tests clean" over an incomplete run. `pipefail`
# (set unconditionally above) makes the pipeline's exit status the first
# non-zero of find/sort rather than sort's; `set +e` here stops `set -e`
# from aborting the script before the custom DISCOVERY FAILED message
# below can print.
set +e
TEST_FILES=$(find . \( -path "./$TEST_PATTERN" -o -path "./${TEST_PATTERN//\*\*\//}" \) | sort -u)
FIND_STATUS=$?
set -e
if [ "$FIND_STATUS" -ne 0 ]; then
  echo ""
  echo "🚫 DISCOVERY FAILED (find exit $FIND_STATUS) — test list is incomplete, cannot conclude clean"
  exit 1
fi

if [ -z "$TEST_FILES" ]; then
  TOTAL=0
else
  TOTAL=$(printf '%s\n' "$TEST_FILES" | wc -l | tr -d ' ')
fi

echo "Found $TOTAL test files"
echo ""

COUNT=0
RAN=0
FAILED=0
FAILED_FILES=""
while IFS= read -r TEST_FILE; do
  [ -z "$TEST_FILE" ] && continue
  COUNT=$((COUNT + 1))

  # Skip if pollution already exists
  if [ -e "$POLLUTION_CHECK" ]; then
    echo "⚠️  Pollution already exists before test $COUNT/$TOTAL"
    echo "   Skipping: $TEST_FILE"
    continue
  fi

  echo "[$COUNT/$TOTAL] Testing: $TEST_FILE"

  # Run the test. `< /dev/null`: the runner must not inherit this loop's
  # stdin (the here-string driving `read` above) -- a runner that reads
  # stdin to EOF would otherwise drain the remaining test list and end the
  # loop early. A failing assertion inside the test is not a runner
  # failure and must not be conflated with one -- but a runner that could
  # not even complete (missing binary, bad interpreter: exit 126 or 127)
  # must not be read as "ran clean" either, so capture and check its exit
  # status rather than discarding it with `|| true`.
  set +e
  npm test "$TEST_FILE" > /dev/null 2>&1 < /dev/null
  RUNNER_EXIT=$?
  set -e
  RAN=$((RAN + 1))

  # Check if pollution appeared FIRST, before any exit-code classification.
  # A marker on disk is a polluter found, whatever the exit code was --
  # including 126/127. A test that touches the marker and then hits a
  # missing or non-executable runner command still polluted; reporting
  # RUNNER FAILED instead of FOUND POLLUTER here would hide it.
  if [ -e "$POLLUTION_CHECK" ]; then
    echo ""
    echo "🎯 FOUND POLLUTER!"
    echo "   Test: $TEST_FILE"
    echo "   Created: $POLLUTION_CHECK"
    echo ""
    echo "Pollution details:"
    ls -la "$POLLUTION_CHECK"
    echo ""
    echo "To investigate:"
    echo "  npm test $TEST_FILE    # Run just this test"
    echo "  cat $TEST_FILE         # Review test code"
    exit 1
  fi

  if [ "$RUNNER_EXIT" -eq 126 ] || [ "$RUNNER_EXIT" -eq 127 ]; then
    echo ""
    echo "💥 RUNNER FAILED (exit $RUNNER_EXIT)"
    echo "   Test: $TEST_FILE"
    echo "   The runner did not complete, so pollution results for this and"
    echo "   any remaining files cannot be trusted. Fix the runner and rerun."
    exit 1
  fi

  # No pollution, but the test itself failed. That is not a runner
  # failure and not a polluter -- record it and keep bisecting the
  # remaining candidates rather than aborting on an unrelated failure.
  if [ "$RUNNER_EXIT" -ne 0 ]; then
    echo "   (exit $RUNNER_EXIT, no pollution -- continuing)"
    FAILED=$((FAILED + 1))
    FAILED_FILES="${FAILED_FILES}${TEST_FILE} (exit ${RUNNER_EXIT})
"
  fi
done <<< "$TEST_FILES"

if [ "$RAN" -eq 0 ]; then
  echo ""
  echo "🚫 NO TESTS RAN — cannot conclude clean"
  echo "   $TOTAL file(s) matched but none were exercised: either the"
  echo "   pattern matched nothing, or every candidate was skipped because"
  echo "   the pollution check already existed before the first test."
  exit 1
fi

if [ "$FAILED" -gt 0 ]; then
  echo ""
  echo "⚠️  $FAILED test(s) failed without producing pollution — investigation inconclusive"
  printf '%s' "$FAILED_FILES"
  exit 1
fi

echo ""
echo "✅ No polluter found - all tests clean!"
exit 0

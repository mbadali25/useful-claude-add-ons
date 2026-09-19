#!/usr/bin/env bash
# Bisection script to find which test creates unwanted files/state
# Usage: ./find-polluter.sh <file_or_dir_to_check> <test_pattern>
# Example: ./find-polluter.sh '.git' 'src/**/*.test.ts'
#
# Modified from upstream superpowers 6.3.0 find-polluter.sh:
# - Iterate test files through a `while read` loop instead of unquoted word
#   splitting, so a filename containing whitespace is one argument to
#   `npm test`, not several.
# - Do not swallow the runner's exit status: a non-zero exit from `npm test`
#   is reported as "RUNNER FAILED (exit N)" and the script exits non-zero,
#   instead of being silently treated as a clean run.
# - Track how many tests actually ran; if none did (pattern matched nothing,
#   or every candidate was skipped because the pollution check already
#   existed before the first test), report "NO TESTS RAN" and exit
#   non-zero instead of a false-positive clean verdict.

set -e

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
# find -path can't match '**/' against zero directory levels, so a pattern
# like src/**/*.test.ts would skip src/top.test.ts; also try the pattern
# with '**/' collapsed to cover files directly under the base directory.
TEST_FILES=$(find . \( -path "./$TEST_PATTERN" -o -path "./${TEST_PATTERN//\*\*\//}" \) | sort -u)
if [ -z "$TEST_FILES" ]; then
  TOTAL=0
else
  TOTAL=$(printf '%s\n' "$TEST_FILES" | wc -l | tr -d ' ')
fi

echo "Found $TOTAL test files"
echo ""

COUNT=0
RAN=0
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

  # Run the test. A failing assertion inside the test is not a runner
  # failure and must not be conflated with one -- but a runner that could
  # not even complete (missing binary, bad interpreter, crash) must not be
  # read as "ran clean" either, so capture and check its exit status rather
  # than discarding it with `|| true`.
  set +e
  npm test "$TEST_FILE" > /dev/null 2>&1
  RUNNER_EXIT=$?
  set -e
  RAN=$((RAN + 1))
  if [ "$RUNNER_EXIT" -ne 0 ]; then
    echo ""
    echo "💥 RUNNER FAILED (exit $RUNNER_EXIT)"
    echo "   Test: $TEST_FILE"
    echo "   The runner did not complete, so pollution results for this and"
    echo "   any remaining files cannot be trusted. Fix the runner and rerun."
    exit 1
  fi

  # Check if pollution appeared
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
done <<< "$TEST_FILES"

if [ "$RAN" -eq 0 ]; then
  echo ""
  echo "🚫 NO TESTS RAN — cannot conclude clean"
  echo "   $TOTAL file(s) matched but none were exercised: either the"
  echo "   pattern matched nothing, or every candidate was skipped because"
  echo "   the pollution check already existed before the first test."
  exit 1
fi

echo ""
echo "✅ No polluter found - all tests clean!"
exit 0

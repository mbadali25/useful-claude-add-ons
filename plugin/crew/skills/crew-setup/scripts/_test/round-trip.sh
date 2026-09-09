#!/usr/bin/env bash
# Round-trip test for claude-md-audit.sh.
#
# label() tells the user the canonical heading for a concern; canon() decides
# whether a heading in a real CLAUDE.md maps back to that concern. The two are a
# contract. This test feeds every label() output back through canon() and asserts
# it resolves to the concern it came from.
#
# Without this, the audit can confidently recommend a heading it will then reject,
# and the failure reads as the user's mistake rather than the tool's - which is
# exactly what shipped: canon()'s `commands` arm had no trailing wildcard while
# every sibling did, so `## Commands - build, test, verify, regression, promote`
# was reported MISSING and `extra` at the same time.
#
# Read-only. Touches no repo state and creates no files outside its own mktemp.
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
AUDIT="$HERE/../claude-md-audit.sh"

[ -f "$AUDIT" ] || { echo "FAIL: cannot find claude-md-audit.sh at $AUDIT"; exit 1; }

# Source only the two functions. The script body resolves $TARGET and exits when
# no CLAUDE.md is present, so it cannot simply be sourced.
FN=$(mktemp)
trap 'rm -f "$FN"' EXIT
sed -n '/^canon()/,/^}/p;/^label()/,/^}/p' "$AUDIT" > "$FN"
# shellcheck disable=SC1090
. "$FN"

for f in canon label; do
  declare -F "$f" >/dev/null || { echo "FAIL: could not extract $f() from claude-md-audit.sh"; exit 1; }
done

CONCERNS="commands where-things-are scope stop-and-ask promotion documentation reporting memory"

fails=0
checked=0
for concern in $CONCERNS; do
  heading=$(label "$concern")
  [ -n "$heading" ] || { echo "FAIL  $concern: label() returned nothing"; fails=$((fails+1)); continue; }

  # Normalise exactly as the audit's own reader does: strip '## ', lowercase,
  # drop trailing whitespace. If this drifts from the reader, the test is lying.
  key=$(printf '%s\n' "$heading" | sed 's/^## //' | tr '[:upper:]' '[:lower:]' | sed 's/[[:space:]]*$//')
  got=$(canon "$key")
  checked=$((checked+1))

  if [ "$got" = "$concern" ]; then
    echo "ok    $concern  <-  $heading"
  else
    echo "FAIL  $concern: label() recommends \"$heading\""
    echo "         canon() resolves it to \"$got\" instead of \"$concern\""
    fails=$((fails+1))
  fi
done

# A silently-empty loop must not pass. If the concern list or the extraction
# breaks, this catches it rather than reporting a green run over zero cases.
# Derived from CONCERNS rather than hardcoded. The count was literally `7` and
# adding an eighth concern failed here with "the extraction or list is broken" -
# a message that accuses the extraction when the list is what moved. A count
# that has to be edited in two places to add one concern is a tripwire on the
# maintainer, not on the contract.
EXPECTED=$(printf '%s
' $CONCERNS | grep -c .)
# An empty CONCERNS gives EXPECTED=0 and checked=0, and `0 -ne 0` is false -
# so the suite would report PASS having exercised nothing. Deriving the count
# fixed a hardcoded tripwire and introduced a vacuous pass; this closes it.
if [ "$EXPECTED" -eq 0 ]; then
  echo "FAIL: CONCERNS is empty, so this suite would pass having checked nothing"
  exit 1
fi
if [ "$checked" -ne "$EXPECTED" ]; then
  echo "FAIL: CONCERNS lists $EXPECTED, checked $checked - label() is missing an arm, or the extraction is broken"
  exit 1
fi

echo
if [ "$fails" -eq 0 ]; then
  echo "PASS: all $checked label() headings round-trip through canon()"
  exit 0
fi
echo "FAIL: $fails of $checked headings do not round-trip"
exit 1

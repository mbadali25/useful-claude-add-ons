#!/usr/bin/env bash
# Run the skill's own pre-ship checklist against a report the builder actually
# emitted.
#
# The checklist in references/word-traps.md is prose, and prose checks nothing.
# This runs the greppable half of it against a real artifact, which is the only
# way to catch the case that already happened once: the builder's own CSS
# COMMENT said ":nth-child does nothing here", so every report it emitted
# contained the literal string a reader is told to grep for. Functionally inert
# -- Word ignores CSS comments -- and indistinguishable from the real defect to
# the check the skill itself recommends. A check that cannot tell a violation
# from a mention of the violation is not a check.
#
# Read-only apart from its own mktemp. Creates nothing in the repo.
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
BUILD="$HERE/../build_report.py"
PASS=0
FAIL=0

pass() { PASS=$((PASS+1)); printf '  PASS  %s\n' "$1"; }
fail() { FAIL=$((FAIL+1)); printf '  FAIL  %s\n' "$1"; }

PY=""
for c in python3 python py; do command -v "$c" >/dev/null 2>&1 && { PY="$c"; break; }; done
[ -n "$PY" ] || { echo "FAIL: no python on PATH - cannot run the builder" >&2; exit 1; }
[ -f "$BUILD" ] || { echo "FAIL: cannot find build_report.py at $BUILD" >&2; exit 1; }

TMP=$(mktemp -d) || exit 1
trap 'rm -rf "$TMP"' EXIT

"$PY" "$BUILD" --example > "$TMP/report.json" 2>"$TMP/err" || {
  echo "FAIL: --example did not run:"; cat "$TMP/err"; exit 1; }
"$PY" "$BUILD" --data "$TMP/report.json" --out "$TMP/out" >/dev/null 2>"$TMP/err" || {
  echo "FAIL: build did not run:"; cat "$TMP/err"; exit 1; }

DOC=$(ls "$TMP/out"/*.html 2>/dev/null | head -1)
[ -n "$DOC" ] || { echo "FAIL: the builder wrote no .html"; exit 1; }

echo "== emitted artifact must not contain what Word silently drops =="
# Checklist items 1, 2 and 4 from references/word-traps.md. Each is a literal
# substring, so a mention inside a comment fails too -- deliberately, see above.
for pat in 'var(--' ':nth-child' ':first-child' ':last-of-type' '::before' '::after' ':hover' 'display:flex' 'display:grid'; do
  if grep -qF -- "$pat" "$DOC"; then
    fail "emitted report contains '$pat'"
  else
    pass "no '$pat'"
  fi
done

echo "== checklist item 3: no element carries two class names =="
# `class="a b"` applies NEITHER rule in Word. Grouped selectors in the
# stylesheet are fine and are not what this looks at - this is elements only.
if grep -oE 'class="[A-Za-z0-9_-]+[[:space:]]+[A-Za-z0-9_-]+' "$DOC" | grep -q .; then
  fail "an element carries two class names"
else
  pass "every element carries at most one class"
fi

echo "== checklist item 5: every table has a thead and a border =="
NT=$(grep -c '<table' "$DOC")
NH=$(grep -c '<thead>' "$DOC")
# The masthead, meta and cards tables are layout, not data; only data tables
# carry a thead. Assert the data table has one rather than asserting a count
# that changes whenever the furniture does.
if grep -q '<table class="data">' "$DOC" && [ "$NH" -ge 1 ]; then
  pass "the data table has a thead ($NT tables, $NH thead)"
else
  fail "the data table has no thead ($NT tables, $NH thead)"
fi
if grep -q 'border:1px solid' "$DOC"; then
  pass "tables carry a visible border"
else
  fail "no table border in the stylesheet"
fi

echo "== checklist item 6: zebra rows are an explicit class =="
if [ "$(grep -c 'class="alt"' "$DOC")" -ge 1 ]; then
  pass "alternating rows carry class=\"alt\""
else
  fail "no row carries class=\"alt\" - zebra will not render"
fi

echo "== checklist item 7: every severity colour carries its word =="
# A red cell means nothing in greyscale or to a colour-blind reader. Each chip
# must contain text, not just a fill.
if grep -oE '<span class="chip-[a-z]+">[^<]+</span>' "$DOC" | grep -q .; then
  EMPTY=$(grep -oE '<span class="chip-[a-z]+"></span>' "$DOC" | wc -l)
  if [ "$EMPTY" -eq 0 ]; then
    pass "every chip carries a word"
  else
    fail "$EMPTY chip(s) render colour with no word"
  fi
else
  fail "no severity chips found in a report whose example data has six"
fi

echo "== unverified is its own severity, not folded into pass =="
if grep -q 'chip-unverified' "$DOC"; then
  pass "unverified renders distinctly"
else
  fail "unverified is missing - a check that could not run must not read as pass"
fi

echo
if [ "$FAIL" -eq 0 ]; then
  echo "$PASS passed, 0 failed"
  exit 0
fi
echo "$PASS passed, $FAIL FAILED"
exit 1

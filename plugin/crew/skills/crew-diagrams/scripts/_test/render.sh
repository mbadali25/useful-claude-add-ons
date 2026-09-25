#!/usr/bin/env bash
# Regression test for render.sh: the puppeteer-config path (cases 1-2), a
# guard on its pre-existing exit-code behaviour (case 3), and the actual
# regression fixes from the flag-parsing and artifact-checking rework
# (cases 4-12).
#
# Cases 1-2 (puppeteer config): render.sh writes its puppeteer config with
# mktemp, which on Git Bash/MSYS gives a POSIX /tmp path. mmdc is a Windows
# Node program there and cannot resolve it, but only when MSYS_NO_PATHCONV=1
# is set in the caller's environment - MSYS otherwise rewrites the argument
# for us, which is why the bug went unnoticed until a caller with that
# variable set (a common workaround for MSYS mangling *other* arguments) hit
# it. render.sh's own exit code was always correct here: mmdc exits 1 and
# prints "Configuration file ... doesn't exist" to stderr, and that 1
# propagates to render.sh's exit code without help from anything in this
# file. What was never loud is the *directory*: render.sh still creates it
# and prints a summary line regardless of the failure, so a check based on
# the output directory's existence (or on a summary line's mere presence,
# without reading it) would have passed the broken script even though the
# exit code did not lie. These two cases assert on the actual output file's
# byte size instead, for exactly that reason.
#
# Case 3 is a guard, not a regression test: render.sh has taken a failed
# render's exit code into its own exit code since before this file existed
# (`FAILED=1` / `exit $FAILED`, present since commit 9338e89d). Nothing here
# changed that behaviour; case 3 exists so a future change cannot quietly
# drop it.
#
# Cases 4-12 are the actual fixes: flag parsing is position-independent and
# rejects anything it does not recognize - including a bare single-dash
# token - instead of silently treating it as the directory (cases 4-6, 11);
# pointing render.sh at an empty directory is treated as a wrong path, not a
# no-op (case 7); a stale file left over from an earlier render cannot be
# mistaken for a fresh success when mmdc reports 0 without actually writing
# one, and - separately - a render that genuinely fails must not delete that
# last good file either, since render.sh now renders to a temp file and
# moves it onto the real path only on success (case 8 covers both); the
# final count line separates ok, skipped and failed rather than folding
# skips into "ok" (case 9); --png-only combined with --svg-only - which used
# to render nothing, create out/, and exit 0 - is now a loud error (case
# 10); and "--" ends option parsing so a directory whose *name itself*
# starts with a dash (not merely a path that happens to contain one) is both
# reachable and safe to hand to mkdir/rm/mmdc, none of which would otherwise
# read a leading "-" as one of their own options (case 12).
#
# Needs: bash, mmdc (npm install -g @mermaid-js/mermaid-cli). Skips, not fails,
# if mmdc is not on PATH - it is an optional tool for this skill, same as
# render.sh's own check. The skip is on exit 77, this repo's SKIP convention
# (.crew/verify.json's ruff/pylint/mcp-servers rules; verify-gate.sh:1499
# reads it as rc="skip77", never as a pass) rather than exit 0 - CI runners
# do not carry mmdc, and exit 0 would have the Stop-gate record a rule that
# never ran as a check that passed.
#     ./plugin/crew/skills/crew-diagrams/scripts/_test/render.sh
# Exit status is 0 when every case passes, 1 otherwise, 77 when mmdc is absent.

set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RENDER="$HERE/../render.sh"
PASS=0
FAIL=0
red()   { printf '\033[31m%s\033[0m\n' "$1"; }
green() { printf '\033[32m%s\033[0m\n' "$1"; }

[ -f "$RENDER" ] || { echo "FAIL: cannot find render.sh at $RENDER"; exit 1; }
command -v mmdc >/dev/null 2>&1 || { echo "TOOL MISSING: mmdc is not on PATH, so this suite DID NOT RUN. This is a missing tool, not a passing check and not a failing one. Install @mermaid-js/mermaid-cli to check locally; CI runners do not carry it either." >&2; exit 77; }

# A relative dir under $HERE, not an absolute /tmp (or /c/...) path: real
# callers pass render.sh a relative dir like "docs/diagrams", so -i/-o only
# ever need to resolve a relative path. The bug is specifically about the
# absolute /tmp path render.sh's own mktemp gives its puppeteer config - an
# absolute fixture dir would make -i and -o fail the same way under
# MSYS_NO_PATHCONV=1 and mask which argument the fix actually has to cover.
cd "$HERE"
TMP="$(mktemp -d -p .)"
trap 'rm -rf "$TMP"' EXIT
mkdir -p "$TMP/diagrams"
cat > "$TMP/diagrams/smoke.mmd" <<'EOF'
graph TD
  A[Start] --> B[End]
EOF

nonzero_svg() {
  # $1 label. Renders into a fresh out/ each time so a stale file from a
  # previous case can't make a broken run look like it produced something.
  local label="$1"; shift
  rm -rf "$TMP/diagrams/out"
  local out
  out="$("$@" bash "$RENDER" "$TMP/diagrams" --svg-only --force 2>&1)"
  local status=$?
  local dst="$TMP/diagrams/out/smoke.svg"
  local size=0
  [ -f "$dst" ] && size="$(wc -c < "$dst" | tr -d ' ')"
  if [ "$status" -eq 0 ] && [ "$size" -gt 0 ]; then
    green "  PASS  $label (exit 0, ${size} bytes)"; PASS=$((PASS+1))
  else
    red "  FAIL  $label (exit $status, ${size} bytes)"
    printf '%s\n' "$out" | sed 's/^/        /'
    FAIL=$((FAIL+1))
  fi
}

echo "1. plain invocation renders a non-empty SVG"
nonzero_svg "no env override" env

echo "2. MSYS_NO_PATHCONV=1 - the setting that turned off MSYS's automatic"
echo "   /tmp rewrite and made mmdc fail on this repo on 2026-09-05"
nonzero_svg "MSYS_NO_PATHCONV=1" env MSYS_NO_PATHCONV=1

# --- case 3: guard on pre-existing exit-code behaviour ------------------

expect_nonzero() {
  # $1 label, remaining args passed verbatim to render.sh
  local label="$1"; shift
  local out status
  out="$(bash "$RENDER" "$@" 2>&1)"; status=$?
  if [ "$status" -ne 0 ]; then
    green "  PASS  $label (exit $status)"; PASS=$((PASS+1))
  else
    red "  FAIL  $label (exit $status, expected nonzero)"
    printf '%s\n' "$out" | sed 's/^/        /'
    FAIL=$((FAIL+1))
  fi
}

echo "3. [guard, not a regression fix] a diagram with a parse error (bare %%"
echo "   line, then garbage) fails and the script exits non-zero - this has"
echo "   been true since before this file existed"
mkdir -p "$TMP/badsyntax"
cat > "$TMP/badsyntax/broken.mmd" <<'EOF'
%%
this is not valid mermaid @@@@ ((()))
EOF
expect_nonzero "parse error" "$TMP/badsyntax" --svg-only --force

# --- cases 4-12: the actual flag-parsing / artifact-checking fixes ------

echo "4. an unrecognized flag is rejected with a usage error, not silently"
echo "   ignored"
OUT4="$(bash "$RENDER" --bogus-flag "$TMP/diagrams" 2>&1)"; STATUS4=$?
if [ "$STATUS4" -ne 0 ] && printf '%s' "$OUT4" | grep -qi usage; then
  green "  PASS  unknown flag rejected (exit $STATUS4)"; PASS=$((PASS+1))
else
  red "  FAIL  unknown flag rejected (exit $STATUS4)"
  printf '%s\n' "$OUT4" | sed 's/^/        /'
  FAIL=$((FAIL+1))
fi

echo "5. --force with no directory argument does not eat the flag as the"
echo "   directory (used to run mkdir on a dir literally named --force, then"
echo "   report \"no .mmd files\" and exit 0)"
DEFDIR="$TMP/defaultcwd"
mkdir -p "$DEFDIR/docs/diagrams"
cp "$TMP/diagrams/smoke.mmd" "$DEFDIR/docs/diagrams/smoke.mmd"
OUT5="$(cd "$DEFDIR" && bash "$RENDER" --force 2>&1)"; STATUS5=$?
DST5="$DEFDIR/docs/diagrams/out/smoke.svg"
SIZE5=0; [ -f "$DST5" ] && SIZE5="$(wc -c < "$DST5" | tr -d ' ')"
if [ "$STATUS5" -eq 0 ] && [ "$SIZE5" -gt 0 ]; then
  green "  PASS  --force with no dir uses the default (exit 0, ${SIZE5} bytes)"
  PASS=$((PASS+1))
else
  red "  FAIL  --force with no dir (exit $STATUS5, ${SIZE5} bytes)"
  printf '%s\n' "$OUT5" | sed 's/^/        /'
  FAIL=$((FAIL+1))
fi

echo "6. flags before the directory parse the same as flags after it"
rm -rf "$TMP/diagrams/out"
OUT6="$(bash "$RENDER" --svg-only --force "$TMP/diagrams" 2>&1)"; STATUS6=$?
DST6="$TMP/diagrams/out/smoke.svg"
SIZE6=0; [ -f "$DST6" ] && SIZE6="$(wc -c < "$DST6" | tr -d ' ')"
if [ "$STATUS6" -eq 0 ] && [ "$SIZE6" -gt 0 ]; then
  green "  PASS  flag-first invocation (exit 0, ${SIZE6} bytes)"; PASS=$((PASS+1))
else
  red "  FAIL  flag-first invocation (exit $STATUS6, ${SIZE6} bytes)"
  printf '%s\n' "$OUT6" | sed 's/^/        /'
  FAIL=$((FAIL+1))
fi

echo "7. an empty directory (no .mmd sources) exits non-zero and does not"
echo "   create out/ - a caller pointed at nothing is almost always a wrong"
echo "   path, so this fails loudly rather than succeeding on doing nothing"
EMPTYDIR="$TMP/empty"
mkdir -p "$EMPTYDIR"
OUT7="$(bash "$RENDER" "$EMPTYDIR" 2>&1)"; STATUS7=$?
if [ "$STATUS7" -ne 0 ] && [ ! -d "$EMPTYDIR/out" ]; then
  green "  PASS  empty dir (exit $STATUS7, no out/ created)"; PASS=$((PASS+1))
else
  red "  FAIL  empty dir (exit $STATUS7, out/ exists: $([ -d "$EMPTYDIR/out" ] && echo yes || echo no))"
  printf '%s\n' "$OUT7" | sed 's/^/        /'
  FAIL=$((FAIL+1))
fi

echo "8. a fake mmdc that exits 0 without writing a fresh file does not get"
echo "   credit for a stale SVG left over from an earlier real render - and"
echo "   that stale (still genuinely last-good) file survives the failure"
echo "   untouched, because render.sh renders to a temp file and only moves"
echo "   it onto the real path on success"
STALEDIR="$TMP/stale"
mkdir -p "$STALEDIR"
cp "$TMP/diagrams/smoke.mmd" "$STALEDIR/smoke.mmd"
# A genuine first render, with the real mmdc, to populate out/smoke.svg.
bash "$RENDER" "$STALEDIR" --svg-only >/dev/null 2>&1
STALE_BEFORE=0
[ -f "$STALEDIR/out/smoke.svg" ] && STALE_BEFORE="$(wc -c < "$STALEDIR/out/smoke.svg" | tr -d ' ')"
FAKEBIN="$TMP/fakebin"
mkdir -p "$FAKEBIN"
cat > "$FAKEBIN/mmdc" <<'EOF'
#!/bin/sh
exit 0
EOF
chmod +x "$FAKEBIN/mmdc"
OUT8="$(PATH="$FAKEBIN:$PATH" bash "$RENDER" "$STALEDIR" --svg-only --force 2>&1)"; STATUS8=$?
STALE_AFTER=0
[ -f "$STALEDIR/out/smoke.svg" ] && STALE_AFTER="$(wc -c < "$STALEDIR/out/smoke.svg" | tr -d ' ')"
if [ "$STATUS8" -ne 0 ] && [ "$STALE_BEFORE" -gt 0 ] && [ "$STALE_AFTER" -eq "$STALE_BEFORE" ]; then
  green "  PASS  fake mmdc does not inherit a stale render, and the stale file survives (exit $STATUS8, ${STALE_AFTER} bytes preserved)"; PASS=$((PASS+1))
else
  red "  FAIL  fake mmdc does not inherit a stale render (exit $STATUS8, before ${STALE_BEFORE} bytes, after ${STALE_AFTER} bytes)"
  printf '%s\n' "$OUT8" | sed 's/^/        /'
  FAIL=$((FAIL+1))
fi

echo "9. the final count line reports ok, skipped and failed separately -"
echo "   a skipped (unchanged) render must not be folded into \"ok\""
rm -rf "$TMP/diagrams/out"
bash "$RENDER" "$TMP/diagrams" --svg-only --force >/dev/null 2>&1
OUT9="$(bash "$RENDER" "$TMP/diagrams" --svg-only 2>&1)"; STATUS9=$?
if [ "$STATUS9" -eq 0 ] && printf '%s' "$OUT9" | grep -q "done: 0 ok, 1 skipped, 0 failed"; then
  green "  PASS  count line separates skipped from ok"; PASS=$((PASS+1))
else
  red "  FAIL  count line separates skipped from ok"
  printf '%s\n' "$OUT9" | sed 's/^/        /'
  FAIL=$((FAIL+1))
fi

echo "10. --png-only combined with --svg-only (nothing left to render) is a"
echo "    loud error, not a silent no-op that still exits 0"
expect_nonzero "--png-only + --svg-only" "$TMP/diagrams" --png-only --svg-only

echo "11. a single-dash unknown flag (-x) is rejected by name, not silently"
echo "    read as the directory"
OUT11="$(bash "$RENDER" -x "$TMP/diagrams" 2>&1)"; STATUS11=$?
if [ "$STATUS11" -ne 0 ] && printf '%s' "$OUT11" | grep -q -- '-x'; then
  green "  PASS  -x rejected by name (exit $STATUS11)"; PASS=$((PASS+1))
else
  red "  FAIL  -x rejected by name (exit $STATUS11)"
  printf '%s\n' "$OUT11" | sed 's/^/        /'
  FAIL=$((FAIL+1))
fi

echo "12. \"--\" ends option parsing, so a directory *named* with a leading"
echo "    dash - passed bare, not nested under another path - is reachable"
echo "    and safe to hand to mkdir/rm/mmdc, none of which would otherwise"
echo "    read a leading \"-\" as one of their own options"
# Deliberately NOT under $TMP: $TMP itself is "./tmp.XXXX", so "$TMP/-dashdir"
# as a whole argument starts with "." and would reach render.sh's DIR slot
# without needing "--" at all, proving nothing about the dash case. This has
# to be a bare, top-level name so the argument string itself starts with "-".
# render.sh is handed that bare name directly, to exercise its own arg
# parser and its "./" normalization; this test's own mkdir/cp/rm calls use a
# "./"-prefixed form throughout, because a bare leading-dash argument is
# exactly as unsafe to hand to *this script's* coreutils as it is inside
# render.sh, and that is not what this case is testing.
DASHDIR="-dashdir.$$"
mkdir -p "./$DASHDIR"
cp "$TMP/diagrams/smoke.mmd" "./$DASHDIR/smoke.mmd"
OUT12="$(bash "$RENDER" --svg-only --force -- "$DASHDIR" 2>&1)"; STATUS12=$?
DST12="./$DASHDIR/out/smoke.svg"
SIZE12=0; [ -f "$DST12" ] && SIZE12="$(wc -c < "$DST12" | tr -d ' ')"
rm -rf "./$DASHDIR"
if [ "$STATUS12" -eq 0 ] && [ "$SIZE12" -gt 0 ]; then
  green "  PASS  -- reaches a dash-prefixed dir (exit 0, ${SIZE12} bytes)"; PASS=$((PASS+1))
else
  red "  FAIL  -- reaches a dash-prefixed dir (exit $STATUS12, ${SIZE12} bytes)"
  printf '%s\n' "$OUT12" | sed 's/^/        /'
  FAIL=$((FAIL+1))
fi

echo
if [ "$FAIL" -eq 0 ]; then green "$PASS passed, 0 failed"; exit 0; fi
red "$PASS passed, $FAIL FAILED"
exit 1

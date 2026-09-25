#!/usr/bin/env bash
# Regression suite for a defect the OTHER .ps1 suites in this directory could
# not have caught, because none of them force
# `$PSNativeCommandArgumentPassing = 'Legacy'`: on Windows PowerShell 5.1,
# and on pwsh 7.2 and earlier (also on newer pwsh explicitly switched to
# Legacy mode, which is how this is reproduced without a Windows machine),
# native command arguments are reconstructed the legacy way, and an embedded
# DOUBLE quote inside an argument is silently stripped before the native
# process ever sees it.
#
# THE DEFECT, shipped in vault-guard.ps1, bridge-status.ps1 and
# vault-capture.ps1 until this fix:
#
#   $output = & $cmd.Source -c 'import sys; sys.stdout.write("vault-guard-python:" + sys.executable)'
#
# Under legacy argument passing, python received
# `sys.stdout.write(vault-guard-python: + sys.executable)` - a SyntaxError,
# exit 1, and every real interpreter on the machine was rejected as "did not
# answer the interpreter probe". Reproduced here, exactly:
#
#   $PSNativeCommandArgumentPassing = 'Legacy'
#   & python3 -c 'import sys; sys.stdout.write("x:" + sys.executable)'
#   ->   File "<string>", line 1
#          import sys; sys.stdout.write(x: + sys.executable)
#        SyntaxError: invalid syntax
#
# THE FIX: the python string literal is single-quoted, not double-quoted,
# escaped for PowerShell's own outer single-quoted argument as `''...''`
# (PowerShell's escape for a literal single quote inside a single-quoted
# string). Legacy argument passing has nothing to strip - there is no double
# quote left in the argument at all.
#
# Sabotage-tested: each of the three targets is tested twice, against the
# real (fixed) script and against a THROWAWAY COPY with the double-quoted
# probe put back - never against the tracked file itself, matching
# test_vault_guard_sh.sh's own rule after its interrupted-sabotage defect.
# Run: bash plugin/obsidian-vault/hooks/scripts/_test/test_ps1_legacy_args.sh
set -uo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

PY=""
for cand in python3 python py; do
  if command -v "$cand" >/dev/null 2>&1; then PY="$(command -v "$cand")"; break; fi
done
if [ -z "$PY" ]; then
  echo "FATAL: no Python interpreter found. Tried python3, python, py on PATH." >&2
  exit 1
fi

PWSH="$(command -v pwsh 2>/dev/null || true)"

PASS=0
FAIL=0
SKIP=0
ok() { PASS=$((PASS+1)); }
bad() { FAIL=$((FAIL+1)); echo "FAIL: $1"; }

if [ -z "$PWSH" ]; then
  SKIP=$((SKIP+1))
  echo "SKIP: test_ps1_legacy_args.sh - no pwsh on PATH (3 targets not run)"
  echo
  echo "RESULT: $PASS passed, $FAIL failed, $SKIP skipped"
  exit 0
fi

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

# ps_quote: wrap a path for embedding into a PowerShell single-quoted
# argument inside a -Command STRING - doubling any literal single quote, the
# same escape the fix itself relies on. Repo paths on a real machine can
# contain spaces or, in principle, a quote; this suite's own paths must not
# assume they never will.
ps_quote() { printf "%s" "$1" | sed "s/'/''/g"; }

home="$work/home"
mkdir -p "$home"
tmpdir="$work/tmp"
mkdir -p "$tmpdir"

RC=0
OUT=""
ERR=""
run_legacy() {
  # $1 = target .ps1 path, $2 = the rest of the PowerShell command line to
  # append after it (may be empty). Stdin is /dev/null unless the caller
  # redirects otherwise (bridge/capture read a JSON payload from stdin; the
  # -PrintPython probe seam does not read stdin at all).
  local target="$1" rest="$2" outf="$work/.out" errf="$work/.err"
  local cmd="\$PSNativeCommandArgumentPassing = 'Legacy'; & '$(ps_quote "$target")' $rest"
  OS="Windows_NT" HOME="$home" TMPDIR="$tmpdir" \
    "$PWSH" -NoProfile -Command "$cmd" > "$outf" 2> "$errf"
  RC=$?
  OUT="$(cat "$outf")"
  ERR="$(cat "$errf")"
}

run_legacy_stdin() {
  # Same as run_legacy, but $3 is a payload piped on stdin.
  local target="$1" rest="$2" payload="$3" outf="$work/.out" errf="$work/.err"
  local cmd="\$PSNativeCommandArgumentPassing = 'Legacy'; & '$(ps_quote "$target")' $rest"
  OS="Windows_NT" HOME="$home" TMPDIR="$tmpdir" \
    "$PWSH" -NoProfile -Command "$cmd" < "$payload" > "$outf" 2> "$errf"
  RC=$?
  OUT="$(cat "$outf")"
  ERR="$(cat "$errf")"
}

# A sabotaged COPY with the double-quoted probe put back, one per target -
# NEVER the tracked file. $marker is the token each script's probe writes
# (vault-guard-python:, bridge-status-python:, vault-capture-python:).
sabotage_copy() {
  local src="$1" marker="$2" dst="$3"
  cp "$src" "$dst"
  "$PY" - "$dst" "$marker" <<'PYEOF'
import re, sys
path, marker = sys.argv[1], sys.argv[2]
text = open(path, encoding="utf-8").read()
# Since the '%d:%d:%s:' % (...) form was replaced with str(...) concatenation
# (cmd.exe expands a literal '%' when a .cmd/.bat candidate is routed through
# it, and the old form put three of them in this exact string), the fixed
# text this fixture targets no longer contains '%' either. Only the marker
# varies between the three targets.
fixed = ("sys.stdout.write(''%s'' + str(v[0]) + '':'' + str(v[1]) + '':'' + "
         "sys.implementation.name + '':'' + sys.executable)") % marker
broken = ('sys.stdout.write("%s" + str(v[0]) + ":" + str(v[1]) + ":" + '
          'sys.implementation.name + ":" + sys.executable)') % marker
assert fixed in text, "fixture assumption broken: the fixed probe text moved (%s)" % path
text = text.replace(fixed, broken)
open(path, "w", encoding="utf-8").write(text)
PYEOF
}

# =============================================================== vault-guard.ps1
echo "== vault-guard.ps1 -PrintPython under Legacy argument passing =="

run_legacy "$DIR/vault-guard.ps1" "-PrintPython"
if [ "$RC" -eq 0 ] && [ -n "$OUT" ] && [ -x "$OUT" ]; then ok
else bad "fixed vault-guard.ps1 should resolve a real interpreter under Legacy mode (exit $RC, output: [$OUT], stderr: [$ERR])"
fi

vg_sabotaged="$work/vault-guard-sabotaged.ps1"
sabotage_copy "$DIR/vault-guard.ps1" "vault-guard-python:" "$vg_sabotaged"
run_legacy "$vg_sabotaged" "-PrintPython"
if [ "$RC" -eq 0 ] && [ -z "$OUT" ]; then ok
else bad "sabotaged (double-quoted) probe should resolve NOTHING under Legacy mode, but got exit $RC, output: [$OUT]"
fi

# =============================================================== bridge-status.ps1
echo "== bridge-status.ps1 under Legacy argument passing =="

sid="legacy-test-$$"
payload="$work/payload.json"
printf '{"session_id": "%s"}' "$sid" > "$payload"
marker="$tmpdir/obsidian-vault-bridge-status-$sid.claim"
rm -f "$marker"
run_legacy_stdin "$DIR/bridge-status.ps1" "" "$payload"
if [ "$RC" -eq 0 ] && [ -f "$marker" ]; then ok
else bad "fixed bridge-status.ps1 should resolve python and run under Legacy mode (claim marker missing; exit $RC, stderr: [$ERR])"
fi

bs_sabotaged="$work/bridge-status-sabotaged.ps1"
sabotage_copy "$DIR/bridge-status.ps1" "bridge-status-python:" "$bs_sabotaged"
rm -f "$marker"
run_legacy_stdin "$bs_sabotaged" "" "$payload"
if [ "$RC" -eq 0 ] && [ ! -f "$marker" ]; then ok
else bad "sabotaged bridge-status.ps1 should NOT resolve python under Legacy mode (claim marker was written anyway; exit $RC)"
fi
case "$ERR" in
  *"no candidate is a usable interpreter"*) ok ;;
  *) bad "sabotaged bridge-status.ps1 should report refusal on stderr (stderr: [$ERR])" ;;
esac

# =============================================================== vault-capture.ps1
echo "== vault-capture.ps1 under Legacy argument passing =="

run_legacy "$DIR/vault-capture.ps1" "-Trigger '--selftest'"
case "$ERR" in
  *"no vault resolved"*) ok ;;
  *) bad "fixed vault-capture.ps1 --selftest should run python and report 'no vault resolved' (exit $RC, stderr: [$ERR])" ;;
esac

vc_sabotaged="$work/vault-capture-sabotaged.ps1"
sabotage_copy "$DIR/vault-capture.ps1" "vault-capture-python:" "$vc_sabotaged"
run_legacy "$vc_sabotaged" "-Trigger '--selftest'"
case "$ERR" in
  *"no vault resolved"*) bad "sabotaged vault-capture.ps1 should NOT have run python far enough to resolve a vault (stderr: [$ERR])" ;;
  *"no candidate is a usable interpreter"*) ok ;;
  *) bad "sabotaged vault-capture.ps1 should report refusal on stderr (stderr: [$ERR])" ;;
esac

echo
echo "RESULT: $PASS passed, $FAIL failed, $SKIP skipped"
[ "$FAIL" -eq 0 ]

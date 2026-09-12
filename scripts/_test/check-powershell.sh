#!/usr/bin/env bash
# Regression suite for the path scoping in scripts/check-powershell.ps1.
#
# $externallyProvided exempts a cmdlet name from "PowerShell cannot resolve this".
# The 23 Exchange/AD names are only unresolvable *inside the Exchange skills*; left
# global they exempt the same names everywhere, so a typo'd Get-ADUser in an
# unrelated script sails through the one check that exists to catch it. These cases
# pin both halves: out-of-scope files do NOT get the exemption, and in-scope files do
# not get laxer as a result.
#
# Needs: bash and pwsh, and runs on the Linux CI runner as well as on Windows, so it
# resolves pwsh in three steps rather than trusting either PATH or a fixed location.
# On the runner only PATH works - there is no C:/Program Files. Under Git Bash, PATH
# is not something to rely on: it resolved to /c/Program Files/PowerShell/7/pwsh in
# the shell this was written in, and CLAUDE.md records a bare `pwsh` failing as
# "command not found" here, which a harness reports as a FAILED CHECK rather than a
# missing tool. Both branches were exercised on Windows; the fallback by re-running
# with PATH=/usr/bin:/bin. Set PWSH to override.
#
# Installs nothing and touches no real config: every fixture is written into a temp
# directory that is removed on exit, and the checker only parses, never executes.
#     ./scripts/_test/check-powershell.sh
# Exit status is 0 when every case passes, 1 otherwise.

set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
CHECKER="$REPO/scripts/check-powershell.ps1"
# An explicit PWSH wins; then PATH, which is how the runner has it; then the Windows
# install location, which is how this box has it. Same order as _verify/run-all.sh,
# minus the PATH step it does not need.
PWSH="${PWSH:-}"
if [ -z "$PWSH" ]; then
  PWSH="$(command -v pwsh 2>/dev/null || true)"
  [ -n "$PWSH" ] || PWSH="C:/Program Files/PowerShell/7/pwsh.exe"
fi
PASS=0
FAIL=0
red()   { printf '\033[31m%s\033[0m\n' "$1"; }
green() { printf '\033[32m%s\033[0m\n' "$1"; }

check() {
  # $1 label, $2 expected, $3 actual
  if [ "$2" = "$3" ]; then
    green "  PASS  $1"; PASS=$((PASS+1))
  else
    red "  FAIL  $1"; red "        wanted: $2"; red "        got:    $3"; FAIL=$((FAIL+1))
  fi
}

if [ ! -x "$PWSH" ]; then
  red "pwsh not found at '$PWSH' (not on PATH either) - this is a missing tool, not a failed check."
  red "Set PWSH=/absolute/path/to/pwsh and re-run."
  exit 2
fi

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

# Under Git Bash, pwsh.exe is a native Windows process: it cannot open the POSIX path
# mktemp hands back, so every path crossing into it goes through `cygpath -m` (mixed
# form, C:/like/this - no backslashes to re-escape through bash). On the Linux runner
# there is no cygpath and nothing to convert, so this is the identity - resolved once
# here rather than per call, and by probing for the tool rather than sniffing the OS.
if command -v cygpath >/dev/null 2>&1; then
  win() { cygpath -m "$1"; }
else
  win() { printf '%s\n' "$1"; }
fi

OUT=""
STATUS=0
run_check() {
  # $1 fixture path (POSIX). Leaves the checker's combined output in $OUT and its
  # exit status in $STATUS.
  OUT="$("$PWSH" -NoProfile -File "$(win "$CHECKER")" -Path "$(win "$1")" 2>&1)"
  STATUS=$?
}

blocked() { [ "$STATUS" -ne 0 ] && echo nonzero || echo zero; }
says()    { case "$OUT" in *"$1"*) echo yes ;; *) echo no ;; esac; }

fixture() {
  # $1 path under $TMP, $2.. the body lines. Echoes back the full path.
  local rel="$1"; shift
  mkdir -p "$TMP/$(dirname "$rel")"
  printf '%s\n' "$@" > "$TMP/$rel"
  echo "$TMP/$rel"
}

# --- preconditions ------------------------------------------------------------
# Each allow case below is only meaningful if the name it uses does NOT resolve
# natively on this machine; if it does, the case would pass with the exemption
# removed and prove nothing. Get-ScheduledTask, for one, resolves on any Windows
# box - which is why the global-exemption case uses Update-SessionEnvironment.
echo "0. the names under test are genuinely unresolvable here"
for n in Get-ADUser Get-Mailbox Get-Mailboxx Update-SessionEnvironment; do
  got="$("$PWSH" -NoProfile -Command \
    "if (Get-Command '$n' -ErrorAction SilentlyContinue) { 'resolves' } else { 'unresolvable' }" 2>&1)"
  check "$n is unresolvable (else its case is vacuous)" unresolvable "$got"
done

# --- must block ---------------------------------------------------------------
echo "1. MUST BLOCK: an out-of-scope file gets no Exchange/AD exemption"
f="$(fixture 'plugin/somewhere/audit.ps1' \
  'param([string]$Who)' \
  '$u = Get-ADUser -Identity $Who' \
  'Write-Host $u')"
run_check "$f"
check "out-of-scope Get-ADUser exits non-zero" nonzero "$(blocked)"
check "and the message names Get-ADUser"       yes     "$(says "calls 'Get-ADUser'")"

echo "2. MUST BLOCK: an in-scope file is not made laxer by the scoping"
f="$(fixture 'skills/exchange-mailbox-cleanup/scripts/typo.ps1' \
  '$m = Get-Mailboxx -Identity "a@b.test"' \
  'Write-Host $m')"
run_check "$f"
check "in-scope typo exits non-zero"           nonzero "$(blocked)"
check "and the message names Get-Mailboxx"     yes     "$(says "calls 'Get-Mailboxx'")"

# --- must allow ---------------------------------------------------------------
# Assert on the clean line too, not just exit 0: a checker that silently stopped
# checking anything also exits 0.
CLEAN="every Verb-Noun call resolves"

echo "3. MUST ALLOW: the real name in the scope it was added for"
f="$(fixture 'skills/exchange-mailbox-cleanup/scripts/vendored/hold.ps1' \
  '$m = Get-Mailbox -Identity "a@b.test"' \
  'Write-Host $m')"
run_check "$f"
check "in-scope Get-Mailbox exits 0"           zero "$(blocked)"
check "and the checker reports it clean"       yes  "$(says "$CLEAN")"

echo "3b. MUST ALLOW: the same, under the other Exchange skill"
f="$(fixture 'skills/exchange-mailbox-restore/scripts/exo_preflight.ps1' \
  '$g = Get-RoleGroup -Identity "eDiscovery Manager"' \
  'Write-Host $g')"
run_check "$f"
check "restore-side Get-RoleGroup exits 0"     zero "$(blocked)"
check "and the checker reports it clean"       yes  "$(says "$CLEAN")"

echo "4. MUST ALLOW: a genuinely universal exemption stays universal"
# Update-SessionEnvironment predates the Exchange entries and is deliberately NOT
# path-scoped. This fixture sits nowhere near the Exchange skills.
f="$(fixture 'scripts/bootstrap-env.ps1' \
  'try { Update-SessionEnvironment } catch { Write-Host "choco profile absent" }')"
run_check "$f"
check "global exemption applies anywhere"      zero "$(blocked)"
check "and the checker reports it clean"       yes  "$(says "$CLEAN")"

echo "5. MUST ALLOW: an ordinary script calling an ordinary cmdlet"
f="$(fixture 'scripts/list-things.ps1' \
  'function Show-Things { Get-ChildItem -Path $PSScriptRoot | ForEach-Object { $_.Name } }' \
  'Show-Things')"
run_check "$f"
check "Get-ChildItem exits 0"                  zero "$(blocked)"
check "and the checker reports it clean"       yes  "$(says "$CLEAN")"

echo
if [ "$FAIL" -eq 0 ]; then green "$PASS passed, 0 failed"; exit 0; fi
red "$PASS passed, $FAIL FAILED"
exit 1

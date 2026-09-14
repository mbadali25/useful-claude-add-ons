#!/usr/bin/env bash
# Regression suite for the KEY HANDLING in scripts/install-prerequisites.ps1.
#
# scripts/_test/menu-groups.sh pins the same behaviour on the .sh side. This file
# exists because the two are a matched pair and nothing committed ran the .ps1 half:
# the Perplexity row was verified by hand once, in the session that wrote it, which
# is exactly the kind of check that does not survive the session. Two defects on that
# row were Windows-only - the binder printing a key given as '-PerplexityApiKey=<key>',
# and the already-registered path returning before the note the .sh prints.
#
# Needs: Windows and pwsh. The installer is Windows-only end to end (it evaluates
# Test-Admin, i.e. [Security.Principal.WindowsIdentity], at top level), so on any
# other platform this SKIPS loudly rather than pretending to check - the same
# decision plugin/crew/tests/test_gates_powershell.py makes. Set PWSH to override
# the interpreter.
#
# Installs nothing and touches no real config: CLAUDE_CONFIG_DIR points at a temp
# directory and 'claude' is a stub on PATH that records its arguments in a FILE.
# It records to a file rather than to stdout on purpose: these cases assert the key
# never reaches the script's OUTPUT, and a stub that echoed its arguments would make
# that assertion pass or fail for the wrong reason.
#     ./scripts/_test/ps-install-keys.sh
# Exit status is 0 when every case passes (or the platform is not Windows), 1 when a
# case fails, 2 when pwsh is missing on a machine where these cases should have run.

set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SCRIPT="$REPO/scripts/install-prerequisites.ps1"
PASS=0
FAIL=0
red()   { printf '\033[31m%s\033[0m\n' "$1"; }
green() { printf '\033[32m%s\033[0m\n' "$1"; }
grey()  { printf '\033[90m%s\033[0m\n' "$1"; }

check() {
  # $1 label, $2 expected, $3 actual
  if [ "$2" = "$3" ]; then
    green "  PASS  $1"; PASS=$((PASS+1))
  else
    red "  FAIL  $1"; red "        wanted: $2"; red "        got:    $3"; FAIL=$((FAIL+1))
  fi
}

case "$(uname -s 2>/dev/null || echo unknown)" in
  MINGW*|MSYS*|CYGWIN*|Windows*) ;;
  *)
    grey "SKIPPED: install-prerequisites.ps1 is the native-Windows flavour and cannot"
    grey "         run here (Test-Admin is evaluated at top level). Needs Windows + pwsh."
    exit 0
    ;;
esac

PWSH="${PWSH:-}"
if [ -z "$PWSH" ]; then
  PWSH="$(command -v pwsh 2>/dev/null || true)"
  [ -n "$PWSH" ] || PWSH="C:/Program Files/PowerShell/7/pwsh.exe"
fi
if [ ! -x "$PWSH" ]; then
  red "pwsh not found at '$PWSH' (not on PATH either) - this is a missing tool, not a failed check."
  red "Set PWSH=/absolute/path/to/pwsh and re-run."
  exit 2
fi

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
mkdir -p "$TMP/bin" "$TMP/cfg"

# pwsh.exe is a native Windows process: every path crossing into it goes through
# 'cygpath -m' (C:/like/this - no backslashes to re-escape through bash).
win() { cygpath -m "$1"; }
WCFG="$(win "$TMP/cfg")"; WBIN="$(win "$TMP/bin")"
WLOG="$(win "$TMP/calls.log")"; WSCRIPT="$(win "$SCRIPT")"
LOG="$TMP/calls.log"

# A .cmd, because that is what PowerShell resolves off PATH for a bare 'claude'.
cat > "$TMP/bin/claude.cmd" <<'STUB'
@echo off
>>"%CLAUDE_STUB_LOG%" echo %*
if "%~1"=="mcp" if "%~2"=="list" if not "%CLAUDE_STUB_MCP_LIST%"=="" echo %CLAUDE_STUB_MCP_LIST%
exit /b 0
STUB

SENTINEL='PPLX-SENTINEL-DO-NOT-PRINT'
MCP_LIST=""
OUT=""
run_case() {
  # $1 the value for $env:PERPLEXITY_API_KEY ('-' for empty); the rest is appended to
  # the script's command line verbatim. Leaves the run's output in $OUT and the stub's
  # calls in $LOG.
  local envkey="$1"; shift
  local key=""
  [ "$envkey" = "-" ] || key="$envkey"
  : > "$LOG"
  OUT="$("$PWSH" -NoProfile -Command "
    \$env:CLAUDE_CONFIG_DIR='$WCFG'
    \$env:CLAUDE_STUB_LOG='$WLOG'
    \$env:CLAUDE_STUB_MCP_LIST='$MCP_LIST'
    \$env:PERPLEXITY_API_KEY='$key'
    \$env:PATH='$WBIN;' + \$env:PATH
    & '$WSCRIPT' -Select perplexity-mcp $*" 2>&1)"
}
saw()    { case "$OUT" in *"$1"*) echo yes ;; *) echo no ;; esac; }
logged() { grep -qF -e "$1" "$LOG" && echo yes || echo no; }

echo "1. no key: the row explains and skips, and registers nothing"
run_case -
check "the row skips"              yes "$(saw 'no -PerplexityApiKey given')"
check "and says where to get one"  yes "$(saw 'docs.perplexity.ai')"
check "and registers nothing"      no  "$(logged 'mcp add')"

echo "2. a whitespace-only key counts as no key"
# -z would accept this; the .sh and the .ps1 both have to treat it as absent, or the
# row registers a server that looks installed and can never authenticate.
run_case '   '
check "whitespace is not a key"    yes "$(saw 'no -PerplexityApiKey given')"
check "and registers nothing"      no  "$(logged 'mcp add')"

echo "3. -PerplexityApiKey registers the server, and is never printed"
run_case - "-PerplexityApiKey $SENTINEL"
check "registers with the key" yes \
  "$(logged "mcp add --scope user perplexity --env PERPLEXITY_API_KEY=$SENTINEL -- npx -y @perplexity-ai/mcp-server")"
check "and the key is NOWHERE in the output" no "$(saw "$SENTINEL")"

echo "4. the -Flag=value spelling works, and is not echoed by the binder"
# PowerShell does not bind '-Name=value'; before ValueFromRemainingArguments captured
# it, the binder failed with "a parameter cannot be found that matches parameter name
# 'PerplexityApiKey=<key>'" - the key, on the terminal, from PowerShell itself.
run_case - "-PerplexityApiKey=$SENTINEL"
check "the = spelling registers"   yes "$(logged "--env PERPLEXITY_API_KEY=$SENTINEL")"
check "and does not print the key" no  "$(saw "$SENTINEL")"

echo "5. \$env:PERPLEXITY_API_KEY is the fallback"
run_case "$SENTINEL"
check "the environment is used"    yes "$(logged "--env PERPLEXITY_API_KEY=$SENTINEL")"
check "and is not printed either"  no  "$(saw "$SENTINEL")"

echo "6. an unknown option is reported by name, with any value redacted"
run_case - "-NotARealFlag=$SENTINEL -PerplexityApiKey $SENTINEL"
check "the name is reported"       yes "$(saw 'Unknown option: -NotARealFlag=<redacted>')"
check "the value is not"           no  "$(saw "$SENTINEL")"
check "and the run carries on"     yes "$(logged 'mcp add')"
run_case - "-NotARealFlag $SENTINEL -PerplexityApiKey $SENTINEL"
check "a bare value is redacted"   yes "$(saw 'Unknown option: <redacted value>')"
check "and is not printed"         no  "$(saw "$SENTINEL")"

echo "7. an already-registered server: skipped, not re-added, note still printed"
# The note is the matched-pair case. menu-groups.sh asserts the .sh prints it on this
# same path; the .ps1 passed it as -Note, which Add-McpServer emits only when it
# actually registered, so Windows printed the SKIP and nothing else.
MCP_LIST="perplexity: npx -y @perplexity-ai/mcp-server - Connected"
run_case - "-PerplexityApiKey $SENTINEL"
check "reported as already registered" yes "$(saw "MCP server 'perplexity' already registered")"
check "and not re-added"                no "$(logged 'mcp add')"
check "and the note is printed anyway" yes "$(saw 'Backs the web-research skill')"
MCP_LIST=""

echo
if [ "$FAIL" -eq 0 ]; then green "$PASS passed, 0 failed"; exit 0; fi
red "$PASS passed, $FAIL FAILED"
exit 1

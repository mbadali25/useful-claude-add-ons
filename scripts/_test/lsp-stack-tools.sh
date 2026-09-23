#!/usr/bin/env bash
# Regression suite for T11's LSP-plugin and stack-tool install steps, in BOTH halves
# of the matched pair: install_lsp_binary/install_csharp_ls_binary/install_pyright_binary/
# install_typescript_lsp_binary/install_angular_language_server/install_tflint/
# install_ruff/install_sqlfluff/install_shellcheck/install_psscriptanalyzer in
# scripts/install-prerequisites.sh, and their Install-LspBinary/tflint/ruff/sqlfluff/
# shellcheck/PSScriptAnalyzer equivalents in scripts/install-prerequisites.ps1.
#
# Idempotency is the point (CLAUDE.md: "both install scripts are idempotent - a new
# step needs a detection branch reporting 'already installed'"), so every function
# below gets at least one already-installed case and one absent case. Neither
# script is run as a whole - only the specific functions are lifted out (by awk,
# the same technique scripts/_test/uv-install.sh uses) and exercised with every
# tool they call stubbed in a throwaway PATH, so nothing here installs anything
# for real.
#
# Needs: bash, coreutils. pwsh is optional - without it the .ps1 cases SKIP loudly
# rather than passing for a reason that isn't real.
#     ./scripts/_test/lsp-stack-tools.sh
# Exit status is 0 when every case passes, 1 otherwise.

set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SCRIPT="$REPO/scripts/install-prerequisites.sh"
PS1SCRIPT="$REPO/scripts/install-prerequisites.ps1"
# Resolved from the AMBIENT PATH, before any case below restricts PATH to a stub
# directory - the last .sh case to run stubs a fake 'pwsh' of its own, and by the
# time the .ps1 half runs, 'command -v pwsh' against a restricted PATH would find
# that stub instead of the real interpreter.
REAL_PWSH="${PWSH:-}"
if [ -z "$REAL_PWSH" ]; then
  REAL_PWSH="$(command -v pwsh 2>/dev/null || true)"
  [ -n "$REAL_PWSH" ] || REAL_PWSH="C:/Program Files/PowerShell/7/pwsh.exe"
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

TMP="$(mktemp -d)" && [ -n "$TMP" ] && [ -d "$TMP" ] || {
  echo "FATAL: mktemp -d failed to produce a directory - refusing to run" >&2
  exit 2
}
trap 'rm -rf "$TMP"' EXIT
# Same TMPDIR pin as uv-install.sh, for the same reason: every case below does
# 'rm -rf "$STUBS"' style cleanup, and TMPDIR is caller-controlled.
_tmpdir="${TMPDIR:-/tmp}"
while [ "$_tmpdir" != "/" ] && [ "${_tmpdir: -1}" = "/" ]; do _tmpdir="${_tmpdir%/}"; done
case "$TMP" in
  "$_tmpdir"/*) ;;
  *)
    echo "FATAL: \$TMP ($TMP) is not under \${TMPDIR:-/tmp} ($_tmpdir) - refusing to run" >&2
    exit 2
    ;;
esac

# --- Lift the real functions out of install-prerequisites.sh -----------------
# Same helpers uv-install.sh lifts (step/ok/warn/skip/run_step/as_root/have), the
# real ensure_uv chain (ruff/sqlfluff route through it, same as graphify), and
# this task's own new block.
eval "$(awk '/^step\(\)/,/^have\(\) \{/' "$SCRIPT")"
eval "$(awk '/^# --- uv, under PEP 668/,/^# --- JSON helper/' "$SCRIPT" | sed '$d')"
# is_selected is a stand-in for the real menu-selection function: the extracted
# range below still carries its own 'if is_selected ...; then ... fi' gates
# (harmless at the top level, never exercised - every case here calls the
# functions directly), and without a stub for it eval fails loudly on both.
is_selected() { return 1; }
eval "$(awk '/^# --- 22\. LSP plugins/,/^# --- Summary/' "$SCRIPT" | sed '$d')"

FAILED_STEPS=()
COUNT_INSTALLED=0
COUNT_UPDATED=0
COUNT_SKIPPED=0

# A curated real-tool copy, built ONCE while PATH is still the ambient one - never
# npm/dotnet/uv/brew/apt-get/pwsh/tflint/shellcheck/ruff/sqlfluff or any other tool
# a function under test might actually reach for, only the handful of coreutils
# the harness itself and the stub scripts need at runtime (mkdir/chmod to build a
# stub, dirname/id/grep because the real functions or their sh stubs call them).
# Every case's PATH is this directory plus a fresh, otherwise-empty stub dir - NOT
# the host's /usr/bin or /bin - so a case testing "tool absent" can never silently
# resolve the real one and install something for real. This is exactly the
# mistake this suite tripped over while it was being written: an early draft
# fell back to "$STUBS:/usr/bin:/bin", and the "no npm" cases found the host's
# real npm and ran real 'npm install -g' commands before this was caught.
REALTOOLS="$TMP/realtools"
mkdir -p "$REALTOOLS"
for _t in mkdir chmod dirname id grep cat touch cp rm stat; do
  _src="$(command -v "$_t" 2>/dev/null)" || continue
  [ -n "$_src" ] && cp "$_src" "$REALTOOLS/$_t"
done
unset _t _src

STUBS=""
newstubs() {
  STUBS="$TMP/stubs-$RANDOM"
  "$REALTOOLS/mkdir" -p "$STUBS"
  export PATH="$STUBS:$REALTOOLS"
}
stub() {
  # $1 name, $2.. body lines - a real new file in $STUBS, never a symlink (same
  # rationale as uv-install.sh's stub(): a stub PATH entry must never resolve back
  # onto a real host tool through a link).
  local name="$1"; shift
  printf '#!/bin/sh\n%s\n' "$*" > "$STUBS/$name"
  "$REALTOOLS/chmod" +x "$STUBS/$name"
}
# HOME under $TMP too: ensure_uv's uv_home_is_safe reads it, and nothing here
# should touch the real one.
export HOME="$TMP/home"
mkdir -p "$HOME"
UV_ENSURED=""

echo "=== install_lsp_binary (the shared helper) ==="
newstubs
stub ngserver 'exit 0'
COUNT_INSTALLED=0; COUNT_SKIPPED=0
out="$(install_lsp_binary "Angular language server (ngserver)" "ngserver" true 2>&1)"; rc=$?
check "already-installed: exits 0"         0 "$rc"
check "already-installed: says SKIP"       yes "$(case "$out" in *SKIP*) echo yes;; *) echo no;; esac)"
check "already-installed: does not count as installed" 0 "$COUNT_INSTALLED"

newstubs
COUNT_INSTALLED=0
install_lsp_binary "Angular language server (ngserver)" "ngserver" true >/dev/null 2>&1; rc=$?
check "absent, install succeeds but leaves nothing on PATH: exits 1" 1 "$rc"

newstubs
stub ngserver 'exit 0'
# ngserver already present, so the install command (a guaranteed failure) is never
# reached - this is the "already installed" branch, not a false pass on the "the
# install command failed" branch.
COUNT_INSTALLED=0
install_lsp_binary "Angular language server (ngserver)" "ngserver" false >/dev/null 2>&1; rc=$?
check "already-installed short-circuits before the install command" 0 "$rc"

newstubs
# The install command itself "succeeds" (exit 0) and creates the probe binary,
# simulating a real 'npm install -g @angular/language-server'.
cat > "$STUBS/fake-installer" <<'EOF'
#!/bin/sh
printf '#!/bin/sh\nexit 0\n' > "$FAKE_PROBE_TARGET"
chmod +x "$FAKE_PROBE_TARGET"
EOF
chmod +x "$STUBS/fake-installer"
export FAKE_PROBE_TARGET="$STUBS/ngserver"
COUNT_INSTALLED=0
install_lsp_binary "Angular language server (ngserver)" "ngserver" fake-installer >/dev/null 2>&1; rc=$?
check "absent, install produces the binary: exits 0"          0 "$rc"
check "absent, install produces the binary: counted installed" 1 "$COUNT_INSTALLED"
unset FAKE_PROBE_TARGET

echo "=== install_csharp_ls_binary / install_pyright_binary / install_typescript_lsp_binary / install_angular_language_server ==="
newstubs
out="$(install_csharp_ls_binary 2>&1)"; rc=$?
check "csharp-ls: no dotnet on PATH -> warns and fails" 1 "$rc"
check "csharp-ls: names dotnet"                          yes "$(case "$out" in *dotnet*) echo yes;; *) echo no;; esac)"

newstubs
stub dotnet 'exit 0'
stub csharp-ls 'exit 0'
COUNT_SKIPPED=0
install_csharp_ls_binary >/dev/null 2>&1; rc=$?
check "csharp-ls: already installed -> exits 0"     0 "$rc"
check "csharp-ls: already installed -> counted skip" 1 "$COUNT_SKIPPED"

newstubs
out="$(install_pyright_binary 2>&1)"; rc=$?
check "pyright-langserver: no npm -> warns and fails" 1 "$rc"
check "pyright-langserver: names npm"                  yes "$(case "$out" in *npm*) echo yes;; *) echo no;; esac)"

newstubs
stub npm 'exit 0'
stub pyright-langserver 'exit 0'
COUNT_SKIPPED=0
install_pyright_binary >/dev/null 2>&1; rc=$?
check "pyright-langserver: already installed -> exits 0"     0 "$rc"
check "pyright-langserver: already installed -> counted skip" 1 "$COUNT_SKIPPED"

newstubs
out="$(install_typescript_lsp_binary 2>&1)"; rc=$?
check "typescript-language-server: no npm -> warns and fails" 1 "$rc"

newstubs
stub npm 'exit 0'
stub typescript-language-server 'exit 0'
COUNT_SKIPPED=0
install_typescript_lsp_binary >/dev/null 2>&1; rc=$?
check "typescript-language-server: already installed -> exits 0"     0 "$rc"
check "typescript-language-server: already installed -> counted skip" 1 "$COUNT_SKIPPED"

newstubs
out="$(install_angular_language_server 2>&1)"; rc=$?
check "ngserver: no npm -> warns and fails" 1 "$rc"

newstubs
stub npm 'exit 0'
stub ngserver 'exit 0'
COUNT_SKIPPED=0
install_angular_language_server >/dev/null 2>&1; rc=$?
check "ngserver: already installed -> exits 0"     0 "$rc"
check "ngserver: already installed -> counted skip" 1 "$COUNT_SKIPPED"

echo "=== install_tflint ==="
newstubs
stub tflint 'exit 0'
COUNT_SKIPPED=0
install_tflint >/dev/null 2>&1; rc=$?
check "tflint: already installed -> exits 0"     0 "$rc"
check "tflint: already installed -> counted skip" 1 "$COUNT_SKIPPED"

newstubs
out="$(install_tflint 2>&1)"; rc=$?
check "tflint: no brew -> warns and fails" 1 "$rc"
check "tflint: names the manual install URL" yes "$(case "$out" in *terraform-linters/tflint*) echo yes;; *) echo no;; esac)"

newstubs
cat > "$STUBS/brew" <<'EOF'
#!/bin/sh
printf '#!/bin/sh\nexit 0\n' > "$(dirname "$0")/tflint"
chmod +x "$(dirname "$0")/tflint"
EOF
chmod +x "$STUBS/brew"
COUNT_INSTALLED=0
install_tflint >/dev/null 2>&1; rc=$?
check "tflint: brew present, installs -> exits 0"     0 "$rc"
check "tflint: brew present, installs -> counted"     1 "$COUNT_INSTALLED"

echo "=== install_ruff / install_sqlfluff (via ensure_uv, same chain graphify uses) ==="
newstubs
stub ruff 'exit 0'
COUNT_SKIPPED=0; UV_ENSURED=""
install_ruff >/dev/null 2>&1; rc=$?
check "ruff: already installed -> exits 0"     0 "$rc"
check "ruff: already installed -> counted skip" 1 "$COUNT_SKIPPED"

newstubs
# $0 inside a PATH-resolved script is the bare command name, not its path - so the
# stub cannot find its own directory via 'dirname "$0"' and instead writes into a
# location named by an env var the test sets, the same technique the LSP-binary
# 'fake-installer' stub above uses.
export STUB_UV_TARGET_DIR="$STUBS"
stub uv 'if [ "$1" = "tool" ] && [ "$2" = "install" ]; then printf "#!/bin/sh\nexit 0\n" > "$STUB_UV_TARGET_DIR/$3"; chmod +x "$STUB_UV_TARGET_DIR/$3"; fi; exit 0'
COUNT_INSTALLED=0; UV_ENSURED=""
install_ruff >/dev/null 2>&1; rc=$?
check "ruff: absent, uv present -> installs, exits 0" 0 "$rc"
check "ruff: absent, uv present -> counted installed" 1 "$COUNT_INSTALLED"

newstubs
stub sqlfluff 'exit 0'
COUNT_SKIPPED=0; UV_ENSURED=""
install_sqlfluff >/dev/null 2>&1; rc=$?
check "sqlfluff: already installed -> exits 0"     0 "$rc"
check "sqlfluff: already installed -> counted skip" 1 "$COUNT_SKIPPED"

newstubs
export STUB_UV_TARGET_DIR="$STUBS"
stub uv 'if [ "$1" = "tool" ] && [ "$2" = "install" ]; then printf "#!/bin/sh\nexit 0\n" > "$STUB_UV_TARGET_DIR/$3"; chmod +x "$STUB_UV_TARGET_DIR/$3"; fi; exit 0'
COUNT_INSTALLED=0; UV_ENSURED=""
install_sqlfluff >/dev/null 2>&1; rc=$?
check "sqlfluff: absent, uv present -> installs, exits 0" 0 "$rc"
check "sqlfluff: absent, uv present -> counted installed" 1 "$COUNT_INSTALLED"
unset STUB_UV_TARGET_DIR

echo "=== install_shellcheck ==="
newstubs
stub shellcheck 'exit 0'
COUNT_SKIPPED=0
install_shellcheck >/dev/null 2>&1; rc=$?
check "shellcheck: already installed -> exits 0"     0 "$rc"
check "shellcheck: already installed -> counted skip" 1 "$COUNT_SKIPPED"

newstubs
out="$(install_shellcheck 2>&1)"; rc=$?
check "shellcheck: no package manager -> warns and fails" 1 "$rc"

newstubs
stub apt-get 'if [ "$1" = "install" ]; then printf "#!/bin/sh\nexit 0\n" > "$(dirname "$0")/shellcheck"; chmod +x "$(dirname "$0")/shellcheck"; fi; exit 0'
COUNT_INSTALLED=0
install_shellcheck >/dev/null 2>&1; rc=$?
check "shellcheck: apt-get present -> installs, exits 0" 0 "$rc"
check "shellcheck: apt-get present -> counted installed" 1 "$COUNT_INSTALLED"

echo "=== install_psscriptanalyzer (pwsh, if present) ==="
newstubs
out="$(install_psscriptanalyzer 2>&1)"; rc=$?
check "PSScriptAnalyzer: no pwsh -> warns and fails" 1 "$rc"
check "PSScriptAnalyzer: names pwsh"                  yes "$(case "$out" in *pwsh*) echo yes;; *) echo no;; esac)"

newstubs
stub pwsh 'case "$*" in *Get-Module*) echo PSScriptAnalyzer ;; esac; exit 0'
COUNT_SKIPPED=0
install_psscriptanalyzer >/dev/null 2>&1; rc=$?
check "PSScriptAnalyzer: pwsh present, module already there -> exits 0"      0 "$rc"
check "PSScriptAnalyzer: pwsh present, module already there -> counted skip" 1 "$COUNT_SKIPPED"

newstubs
MARK="$TMP/psa-installed"
cat > "$STUBS/pwsh" <<EOF
#!/bin/sh
case "\$*" in
  *Get-Module*) [ -f "$MARK" ] && echo PSScriptAnalyzer ;;
  *Install-Module*) touch "$MARK" ;;
esac
exit 0
EOF
chmod +x "$STUBS/pwsh"
COUNT_INSTALLED=0
install_psscriptanalyzer >/dev/null 2>&1; rc=$?
check "PSScriptAnalyzer: pwsh present, module absent -> installs, exits 0" 0 "$rc"
check "PSScriptAnalyzer: pwsh present, module absent -> counted installed" 1 "$COUNT_INSTALLED"

# --- The .ps1 half -------------------------------------------------------------
echo "=== .ps1: Install-LspBinary + stack-tools detection branches ==="
PWSH="$REAL_PWSH"
if [ ! -x "$PWSH" ]; then
  echo "SKIPPED: pwsh not found - install-prerequisites.ps1's half of this suite went unverified in this run."
else
  if command -v cygpath >/dev/null 2>&1; then
    win() { cygpath -m "$1"; }
  else
    win() { printf '%s\n' "$1"; }
  fi
  PSHARNESS="$TMP/harness.ps1"
  cat > "$PSHARNESS" <<'PS1EOF'
$ErrorActionPreference = 'Stop'
$src = Get-Content -Raw -Path $env:PS1SCRIPT
function Get-Block([string]$StartPattern, [string]$EndPattern) {
    $lines = $src -split "`n"
    $out = @(); $on = $false
    foreach ($l in $lines) {
        if ($l -match $StartPattern) { $on = $true }
        if ($on) { $out += $l }
        if ($on -and $l -match $EndPattern) { break }
    }
    return ($out -join "`n")
}
# Lift Write-Step/Write-Ok/Write-Warn2/Write-Skip, Sync-SessionEnvironment, and this
# task's own new functions - never the whole script, which would run the picker.
Invoke-Expression (Get-Block '^function Write-Step' '^function Write-Skip')
Invoke-Expression (Get-Block '^function Sync-SessionEnvironment' '^\}')
$script:Summary = @{ Installed = 0; Updated = 0; Skipped = 0 }
Invoke-Expression (Get-Block '^function Install-LspBinary' '^\}')

$results = @()
# Windows uses ';' and .cmd/.exe extension resolution; Linux pwsh (this box) uses
# ':' and a plain +x file. PathSeparator and a real executable script - rather
# than a hardcoded '.cmd' - keep this harness meaningful on both.
$sep = [System.IO.Path]::PathSeparator
$basePath = $env:PATH

# Case 1: already installed -> Write-Skip, no install attempted.
$stub = Join-Path $env:TESTTMP 'stub1'; New-Item -ItemType Directory -Path $stub -Force | Out-Null
$probe1 = Join-Path $stub 'ngserver'
Set-Content -Path $probe1 -Value "#!/bin/sh`nexit 0`n" -NoNewline
& chmod +x $probe1
$env:PATH = "$stub$sep$basePath"
$script:Summary.Installed = 0
Install-LspBinary -Label 'Angular language server' -Probe 'ngserver' -Install { $global:LASTEXITCODE = 1 }
$results += "already-installed:installed=$($script:Summary.Installed)"

# Case 2: absent, install script "succeeds" by creating the probe. A FRESH stub
# dir on a PATH rebuilt from $basePath - not appended to case 1's $env:PATH -
# because case 1's probe would otherwise still be findable and this case would
# skip for the wrong reason.
$stub2 = Join-Path $env:TESTTMP 'stub2'; New-Item -ItemType Directory -Path $stub2 -Force | Out-Null
$env:PATH = "$stub2$sep$basePath"
$script:Summary.Installed = 0
$probeFile = Join-Path $stub2 'ngserver'
# $Install is invoked directly ('& $Install'), never through Invoke-Command/a job,
# so it is a plain closure over this scope - '$using:' is for remoting and is not
# what makes $probeFile visible here.
Install-LspBinary -Label 'Angular language server' -Probe 'ngserver' -Install {
    Set-Content -Path $probeFile -Value "#!/bin/sh`nexit 0`n" -NoNewline
    & chmod +x $probeFile
    $global:LASTEXITCODE = 0
}
$results += "absent-then-installed:installed=$($script:Summary.Installed)"

$results -join "`n"
PS1EOF
  export PS1SCRIPT="$(win "$PS1SCRIPT")"
  export TESTTMP="$(win "$TMP")"
  out="$("$PWSH" -NoProfile -File "$(win "$PSHARNESS")" 2>&1)"
  check ".ps1 Install-LspBinary: already-installed counts nothing"   "yes" "$(case "$out" in *"already-installed:installed=0"*) echo yes;; *) echo no;; esac)"
  check ".ps1 Install-LspBinary: absent-then-installed counts one"   "yes" "$(case "$out" in *"absent-then-installed:installed=1"*) echo yes;; *) echo no;; esac)"
  unset PS1SCRIPT TESTTMP
fi

echo
if [ "$FAIL" -eq 0 ]; then green "$PASS passed, 0 failed"; exit 0; fi
red "$PASS passed, $FAIL FAILED"
exit 1

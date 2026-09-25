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
# Only uvx on PATH, never uv: ensure_uv is satisfied by either, but
# 'uv tool install ruff' needs uv specifically - the fix under test.
stub uvx 'exit 0'
COUNT_INSTALLED=0; UV_ENSURED=""
out="$(install_ruff 2>&1)"; rc=$?
check "ruff: uvx-only -> fails (needs uv, not uvx)" 1 "$rc"
check "ruff: uvx-only -> names uv"                  yes "$(case "$out" in *"uv still not found"*) echo yes;; *) echo no;; esac)"
check "ruff: uvx-only -> does not count as installed" 0 "$COUNT_INSTALLED"

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

newstubs
stub uvx 'exit 0'
COUNT_INSTALLED=0; UV_ENSURED=""
out="$(install_sqlfluff 2>&1)"; rc=$?
check "sqlfluff: uvx-only -> fails (needs uv, not uvx)" 1 "$rc"
check "sqlfluff: uvx-only -> names uv"                  yes "$(case "$out" in *"uv still not found"*) echo yes;; *) echo no;; esac)"
check "sqlfluff: uvx-only -> does not count as installed" 0 "$COUNT_INSTALLED"

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
# as_root shells out to the REAL 'id -u' (copied into REALTOOLS), so this case
# passed only when the suite itself happened to run as root - stub id/sudo so
# it deterministically exercises the "not root, but sudo works" path instead of
# depending on whoever runs the suite.
stub id 'echo 1000'
stub sudo 'exec "$@"'
stub apt-get 'if [ "$1" = "install" ]; then printf "#!/bin/sh\nexit 0\n" > "$(dirname "$0")/shellcheck"; chmod +x "$(dirname "$0")/shellcheck"; fi; exit 0'
COUNT_INSTALLED=0
install_shellcheck >/dev/null 2>&1; rc=$?
check "shellcheck: apt-get present -> installs, exits 0" 0 "$rc"
check "shellcheck: apt-get present -> counted installed" 1 "$COUNT_INSTALLED"

newstubs
# Regression for the pacman fix: never 'pacman -Sy <pkg>' (a partial upgrade) -
# assert '--needed' is passed and '-Sy' never is.
stub id 'echo 1000'
stub sudo 'exec "$@"'
PACMAN_ARGS="$TMP/pacman-args"
: > "$PACMAN_ARGS"
export PACMAN_ARGS_FILE="$PACMAN_ARGS"
cat > "$STUBS/pacman" <<'EOF'
#!/bin/sh
echo "$@" >> "$PACMAN_ARGS_FILE"
if [ "$1" = "-S" ]; then
  printf '#!/bin/sh\nexit 0\n' > "$(dirname "$0")/shellcheck"
  chmod +x "$(dirname "$0")/shellcheck"
fi
exit 0
EOF
chmod +x "$STUBS/pacman"
COUNT_INSTALLED=0
install_shellcheck >/dev/null 2>&1; rc=$?
check "shellcheck: pacman present -> installs, exits 0"        0  "$rc"
check "shellcheck: pacman present -> counted installed"        1  "$COUNT_INSTALLED"
check "shellcheck: pacman never runs a bare -Sy (partial upgrade)" no "$(case "$(cat "$PACMAN_ARGS")" in *-Sy*) echo yes;; *) echo no;; esac)"
check "shellcheck: pacman uses --needed"                        yes "$(case "$(cat "$PACMAN_ARGS")" in *--needed*) echo yes;; *) echo no;; esac)"
unset PACMAN_ARGS_FILE

newstubs
stub id 'echo 1000'
stub sudo 'exec "$@"'
stub pacman 'exit 1'
out="$(install_shellcheck 2>&1)"; rc=$?
check "shellcheck: pacman failure -> exits 1" 1 "$rc"
check "shellcheck: pacman failure names 'pacman -Syu' guidance" yes "$(case "$out" in *"pacman -Syu"*) echo yes;; *) echo no;; esac)"

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
# Lift Write-Step/Write-Ok/Write-Warn2/Write-Skip, the uv chain (ruff/sqlfluff
# route through it, same as graphify) and this task's own new functions - never
# the whole script, which would run the picker.
Invoke-Expression (Get-Block '^function Write-Step' '^function Write-Skip')
# Sync-SessionEnvironment is FUNCTION-MOCKED, not lifted: the real one replays
# Machine/User scope onto $env:PATH, which erases the synthetic PATH every case
# below builds - the exact way a just-installed probe went missing before this
# was a stub. Real refresh behaviour is exercised by the .sh half via 'source'.
function Sync-SessionEnvironment { }
$script:Summary = @{ Installed = 0; Updated = 0; Skipped = 0 }
Invoke-Expression (Get-Block '^function Install-LspBinary' '^\}')
$script:UvEnsured = $null
Invoke-Expression (Get-Block '^function Install-Uv \{' '^\}')
Invoke-Expression (Get-Block '^function Get-UvCommand' '^\}')
Invoke-Expression (Get-Block '^function Install-UvOnce' '^\}')
Invoke-Expression (Get-Block '^function Install-Tflint' '^\}')
Invoke-Expression (Get-Block '^function Install-Ruff' '^\}')
Invoke-Expression (Get-Block '^function Install-Sqlfluff' '^\}')
Invoke-Expression (Get-Block '^function Install-Shellcheck' '^\}')
Invoke-Expression (Get-Block '^function Install-PSScriptAnalyzer' '^\}')

# Extensionless chmod+x files are real, invokable files on Linux/macOS pwsh
# (this suite's usual host) but Get-Command cannot resolve them by bare name on
# native Windows, which resolves through $env:PATHEXT instead - branch on the
# platform the harness itself is running on rather than assume either shape.
function Get-ProbePath { param([string]$Dir, [string]$Name)
    if ($IsWindows) { Join-Path $Dir "$Name.cmd" } else { Join-Path $Dir $Name }
}
function Write-ProbeStub { param([string]$Path)
    if ($IsWindows) {
        Set-Content -Path $Path -Value "@echo off`r`nexit /b 0`r`n" -NoNewline
    } else {
        Set-Content -Path $Path -Value "#!/bin/sh`nexit 0`n" -NoNewline
        & chmod +x $Path
    }
}

$results = @()
# Windows uses ';' and .cmd/.exe extension resolution; Linux pwsh (this box) uses
# ':' and a plain +x file. PathSeparator and a real executable script - rather
# than a hardcoded '.cmd' - keep this harness meaningful on both.
$sep = [System.IO.Path]::PathSeparator
$basePath = $env:PATH

# Case 1: already installed -> Write-Skip, no install attempted.
$stub = Join-Path $env:TESTTMP 'stub1'; New-Item -ItemType Directory -Path $stub -Force | Out-Null
$probe1 = Get-ProbePath $stub 'ngserver'
Write-ProbeStub $probe1
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
$probeFile = Get-ProbePath $stub2 'ngserver'
# $Install is invoked directly ('& $Install'), never through Invoke-Command/a job,
# so it is a plain closure over this scope - '$using:' is for remoting and is not
# what makes $probeFile visible here.
Install-LspBinary -Label 'Angular language server' -Probe 'ngserver' -Install {
    Write-ProbeStub $probeFile
    $global:LASTEXITCODE = 0
}
$results += "absent-then-installed:installed=$($script:Summary.Installed)"

# --- tflint --------------------------------------------------------------
$stubT1 = Join-Path $env:TESTTMP 'tflint-installed'; New-Item -ItemType Directory -Path $stubT1 -Force | Out-Null
Write-ProbeStub (Get-ProbePath $stubT1 'tflint')
$env:PATH = "$stubT1$sep$basePath"
$script:Summary.Installed = 0
Install-Tflint
$results += "tflint-already-installed:installed=$($script:Summary.Installed)"

$stubT2 = Join-Path $env:TESTTMP 'tflint-none'; New-Item -ItemType Directory -Path $stubT2 -Force | Out-Null
$env:PATH = "$stubT2$sep$basePath"
$threw = $false
try { Install-Tflint } catch { $threw = ($_.Exception.Message -match 'Chocolatey or winget') }
$results += "tflint-no-manager-throws:$threw"

$stubT3 = Join-Path $env:TESTTMP 'tflint-winget'; New-Item -ItemType Directory -Path $stubT3 -Force | Out-Null
$tflintOut = Get-ProbePath $stubT3 'tflint'
$wingetScript = (@'
#!/bin/sh
printf '#!/bin/sh\nexit 0\n' > "TFLINT_OUT"
chmod +x "TFLINT_OUT"
exit 0
'@).Replace('TFLINT_OUT', $tflintOut)
$wingetPath = Join-Path $stubT3 'winget'
Set-Content -Path $wingetPath -Value $wingetScript -NoNewline
& chmod +x $wingetPath
$env:PATH = "$stubT3$sep$basePath"
$script:Summary.Installed = 0
Install-Tflint
$results += "tflint-winget-installs:installed=$($script:Summary.Installed)"

# --- ruff / sqlfluff (via the shared uv chain) ----------------------------
$stubR1 = Join-Path $env:TESTTMP 'ruff-installed'; New-Item -ItemType Directory -Path $stubR1 -Force | Out-Null
Write-ProbeStub (Get-ProbePath $stubR1 'ruff')
$env:PATH = "$stubR1$sep$basePath"
$script:Summary.Installed = 0
Install-Ruff
$results += "ruff-already-installed:installed=$($script:Summary.Installed)"

$stubR2 = Join-Path $env:TESTTMP 'ruff-uv'; New-Item -ItemType Directory -Path $stubR2 -Force | Out-Null
$ruffOut = Get-ProbePath $stubR2 'ruff'
$uvScript = (@'
#!/bin/sh
if [ "$1" = "tool" ] && [ "$2" = "install" ]; then
  printf '#!/bin/sh\nexit 0\n' > "RUFF_OUT"
  chmod +x "RUFF_OUT"
fi
exit 0
'@).Replace('RUFF_OUT', $ruffOut)
$uvPath = Join-Path $stubR2 'uv'
Set-Content -Path $uvPath -Value $uvScript -NoNewline
& chmod +x $uvPath
$env:PATH = "$stubR2$sep$basePath"
$script:Summary.Installed = 0
$script:UvEnsured = $null
Install-Ruff
$results += "ruff-uv-installs:installed=$($script:Summary.Installed)"

# Only uvx on PATH, never uv itself: ensure_uv/Install-Uv is satisfied by
# either, but 'uv tool install ruff' needs uv specifically - this is the
# fix under test, not a restatement of the case above.
$stubR3 = Join-Path $env:TESTTMP 'ruff-uvx-only'; New-Item -ItemType Directory -Path $stubR3 -Force | Out-Null
Write-ProbeStub (Get-ProbePath $stubR3 'uvx')
$env:PATH = "$stubR3$sep$basePath"
$script:UvEnsured = $null
$threw = $false
try { Install-Ruff } catch { $threw = ($_.Exception.Message -match 'uv still not found') }
$results += "ruff-uvx-only-throws:$threw"

$stubQ1 = Join-Path $env:TESTTMP 'sqlfluff-installed'; New-Item -ItemType Directory -Path $stubQ1 -Force | Out-Null
Write-ProbeStub (Get-ProbePath $stubQ1 'sqlfluff')
$env:PATH = "$stubQ1$sep$basePath"
$script:Summary.Installed = 0
Install-Sqlfluff
$results += "sqlfluff-already-installed:installed=$($script:Summary.Installed)"

$stubQ2 = Join-Path $env:TESTTMP 'sqlfluff-uv'; New-Item -ItemType Directory -Path $stubQ2 -Force | Out-Null
$sqlfluffOut = Get-ProbePath $stubQ2 'sqlfluff'
$uvScript2 = (@'
#!/bin/sh
if [ "$1" = "tool" ] && [ "$2" = "install" ]; then
  printf '#!/bin/sh\nexit 0\n' > "SQLFLUFF_OUT"
  chmod +x "SQLFLUFF_OUT"
fi
exit 0
'@).Replace('SQLFLUFF_OUT', $sqlfluffOut)
$uvPath2 = Join-Path $stubQ2 'uv'
Set-Content -Path $uvPath2 -Value $uvScript2 -NoNewline
& chmod +x $uvPath2
$env:PATH = "$stubQ2$sep$basePath"
$script:Summary.Installed = 0
$script:UvEnsured = $null
Install-Sqlfluff
$results += "sqlfluff-uv-installs:installed=$($script:Summary.Installed)"

# --- shellcheck ------------------------------------------------------------
$stubS1 = Join-Path $env:TESTTMP 'shellcheck-installed'; New-Item -ItemType Directory -Path $stubS1 -Force | Out-Null
Write-ProbeStub (Get-ProbePath $stubS1 'shellcheck')
$env:PATH = "$stubS1$sep$basePath"
$script:Summary.Installed = 0
Install-Shellcheck
$results += "shellcheck-already-installed:installed=$($script:Summary.Installed)"

$stubS2 = Join-Path $env:TESTTMP 'shellcheck-none'; New-Item -ItemType Directory -Path $stubS2 -Force | Out-Null
$env:PATH = "$stubS2$sep$basePath"
$threw = $false
try { Install-Shellcheck } catch { $threw = ($_.Exception.Message -match 'Chocolatey or winget') }
$results += "shellcheck-no-manager-throws:$threw"

# winget "succeeds" (exit 0) but never produces the binary - the regression
# case for the missing post-install verification this task fixed.
$stubS3 = Join-Path $env:TESTTMP 'shellcheck-winget-noop'; New-Item -ItemType Directory -Path $stubS3 -Force | Out-Null
Write-ProbeStub (Join-Path $stubS3 'winget')
$env:PATH = "$stubS3$sep$basePath"
$threw = $false
try { Install-Shellcheck } catch { $threw = ($_.Exception.Message -match 'not resolvable') }
$results += "shellcheck-winget-unverified-throws:$threw"

$stubS4 = Join-Path $env:TESTTMP 'shellcheck-winget'; New-Item -ItemType Directory -Path $stubS4 -Force | Out-Null
$shellcheckOut = Get-ProbePath $stubS4 'shellcheck'
$wingetScript2 = (@'
#!/bin/sh
printf '#!/bin/sh\nexit 0\n' > "SHELLCHECK_OUT"
chmod +x "SHELLCHECK_OUT"
exit 0
'@).Replace('SHELLCHECK_OUT', $shellcheckOut)
$wingetPath2 = Join-Path $stubS4 'winget'
Set-Content -Path $wingetPath2 -Value $wingetScript2 -NoNewline
& chmod +x $wingetPath2
$env:PATH = "$stubS4$sep$basePath"
$script:Summary.Installed = 0
Install-Shellcheck
$results += "shellcheck-winget-installs:installed=$($script:Summary.Installed)"

# --- PSScriptAnalyzer --------------------------------------------------------
$stubP1 = Join-Path $env:TESTTMP 'psa-none'; New-Item -ItemType Directory -Path $stubP1 -Force | Out-Null
$env:PATH = "$stubP1$sep$basePath"
$threw = $false
try { Install-PSScriptAnalyzer } catch { $threw = ($_.Exception.Message -match 'powershell.exe') }
$results += "psa-no-hosts-throws:$threw"

$stubP2 = Join-Path $env:TESTTMP 'psa-host'; New-Item -ItemType Directory -Path $stubP2 -Force | Out-Null
$markerPath = Join-Path $env:TESTTMP 'psa-installed-marker'
$psaScript = (@'
#!/bin/sh
case "$*" in
  *Get-Module*) [ -f "MARKER" ] && echo yes ;;
  *Install-Module*) touch "MARKER" ;;
esac
exit 0
'@).Replace('MARKER', $markerPath)
$psaHostPath = Join-Path $stubP2 'pwsh.exe'
Set-Content -Path $psaHostPath -Value $psaScript -NoNewline
& chmod +x $psaHostPath
$env:PATH = "$stubP2$sep$basePath"
$script:Summary.Installed = 0
Install-PSScriptAnalyzer
$results += "psa-one-host-installs:installed=$($script:Summary.Installed)"

$results -join "`n"
PS1EOF
  export PS1SCRIPT="$(win "$PS1SCRIPT")"
  export TESTTMP="$(win "$TMP")"
  out="$("$PWSH" -NoProfile -File "$(win "$PSHARNESS")" 2>&1)"
  check ".ps1 Install-LspBinary: already-installed counts nothing"   "yes" "$(case "$out" in *"already-installed:installed=0"*) echo yes;; *) echo no;; esac)"
  check ".ps1 Install-LspBinary: absent-then-installed counts one"   "yes" "$(case "$out" in *"absent-then-installed:installed=1"*) echo yes;; *) echo no;; esac)"
  check ".ps1 Install-Tflint: already-installed counts nothing"      "yes" "$(case "$out" in *"tflint-already-installed:installed=0"*) echo yes;; *) echo no;; esac)"
  check ".ps1 Install-Tflint: no manager throws"                     "yes" "$(case "$out" in *"tflint-no-manager-throws:True"*) echo yes;; *) echo no;; esac)"
  check ".ps1 Install-Tflint: winget installs and verifies"          "yes" "$(case "$out" in *"tflint-winget-installs:installed=1"*) echo yes;; *) echo no;; esac)"
  check ".ps1 Install-Ruff: already-installed counts nothing"        "yes" "$(case "$out" in *"ruff-already-installed:installed=0"*) echo yes;; *) echo no;; esac)"
  check ".ps1 Install-Ruff: uv present installs"                     "yes" "$(case "$out" in *"ruff-uv-installs:installed=1"*) echo yes;; *) echo no;; esac)"
  check ".ps1 Install-Ruff: uvx-only throws (needs uv, not uvx)"     "yes" "$(case "$out" in *"ruff-uvx-only-throws:True"*) echo yes;; *) echo no;; esac)"
  check ".ps1 Install-Sqlfluff: already-installed counts nothing"    "yes" "$(case "$out" in *"sqlfluff-already-installed:installed=0"*) echo yes;; *) echo no;; esac)"
  check ".ps1 Install-Sqlfluff: uv present installs"                 "yes" "$(case "$out" in *"sqlfluff-uv-installs:installed=1"*) echo yes;; *) echo no;; esac)"
  check ".ps1 Install-Shellcheck: already-installed counts nothing"  "yes" "$(case "$out" in *"shellcheck-already-installed:installed=0"*) echo yes;; *) echo no;; esac)"
  check ".ps1 Install-Shellcheck: no manager throws"                 "yes" "$(case "$out" in *"shellcheck-no-manager-throws:True"*) echo yes;; *) echo no;; esac)"
  check ".ps1 Install-Shellcheck: winget success w/o binary throws"  "yes" "$(case "$out" in *"shellcheck-winget-unverified-throws:True"*) echo yes;; *) echo no;; esac)"
  check ".ps1 Install-Shellcheck: winget installs and verifies"      "yes" "$(case "$out" in *"shellcheck-winget-installs:installed=1"*) echo yes;; *) echo no;; esac)"
  check ".ps1 Install-PSScriptAnalyzer: no hosts throws"             "yes" "$(case "$out" in *"psa-no-hosts-throws:True"*) echo yes;; *) echo no;; esac)"
  check ".ps1 Install-PSScriptAnalyzer: one host installs"           "yes" "$(case "$out" in *"psa-one-host-installs:installed=1"*) echo yes;; *) echo no;; esac)"
  unset PS1SCRIPT TESTTMP
fi

echo
if [ "$FAIL" -eq 0 ]; then green "$PASS passed, 0 failed"; exit 0; fi
red "$PASS passed, $FAIL FAILED"
exit 1

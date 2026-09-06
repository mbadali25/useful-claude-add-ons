<#
    Run the localgpu test suites with the interpreter the bootstrap built.

    Both suites go into ONE pytest invocation on purpose. mcp\_test and cli\_test
    are each outside any package, so a conftest.py in either imports as the same
    top-level module name and silently shadows the other's fixtures. That only
    shows up when the two are collected together - running them one at a time
    hides exactly the regression this script exists to catch. -Mcp and -Cli are
    for narrowing a red run, not for the run that decides whether it is green.

    Matched pair with run-tests.sh: same steps, same order, same flags.

    Usage:
      pwsh -NoProfile -File run-tests.ps1 [-Mcp | -Cli] [extra pytest args]

      -Mcp      only mcp\_test (narrowing; skips the conftest-collision check)
      -Cli      only cli\_test (same caveat)
      -Help     print this and exit

    The interpreter is $LOCALGPU_HOME\venv, where LOCALGPU_HOME defaults to
    %LOCALAPPDATA%\localgpu on Windows and ~/.local/share/localgpu elsewhere.
    The system python is not enough: the mcp suite needs numpy.

    Exits with pytest's exit code, or 1 if there is no venv to run it with.
#>

[CmdletBinding()]
param(
    [switch]$Mcp,     # only mcp\_test
    [switch]$Cli,     # only cli\_test
    [switch]$Help,    # print the usage banner and exit
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$PytestArgs = @()
)

$script:PreviousErrorActionPreference = $ErrorActionPreference
$ErrorActionPreference = 'Stop'

$script:ScriptDir = if ($PSScriptRoot) { $PSScriptRoot } else { (Get-Location).Path }

# Everything that ends the run goes to the error stream, and the process exits 1.
# A failure that only ever reached stdout is a failure nobody sees when this is
# driven from CI or from another script.
function Stop-Runner {
    param([string]$Message, [string[]]$Detail = @())
    [Console]::Error.WriteLine("FAIL: $Message")
    foreach ($line in $Detail) { [Console]::Error.WriteLine("      $line") }
    $ErrorActionPreference = $script:PreviousErrorActionPreference
    exit 1
}

function Show-RunnerUsage {
    # The header comment block, verbatim and de-indented.
    $text = (Get-Content -LiteralPath $PSCommandPath -Raw)
    $body = [regex]::Match($text, '(?s)<\#(.*?)\#>').Groups[1].Value
    foreach ($line in $body -split "`r?`n") { Write-Host ($line -replace '^    ', '') }
}

if ($Help) { Show-RunnerUsage; exit 0 }
if ($Mcp -and $Cli) { Stop-Runner '-Mcp and -Cli are mutually exclusive.' @('Pass neither to run both suites together, which is the run that counts.') }

# --- Interpreter --------------------------------------------------------------
# A venv built by a Windows python puts its interpreter in Scripts\; one built by
# a POSIX python on the same tree puts it in bin\. Resolve rather than assume -
# the same order bootstrap.ps1 uses.
function Get-VenvPythonIn {
    param([string]$VenvDir)
    foreach ($rel in 'Scripts\python.exe', 'bin\python.exe', 'bin\python') {
        $candidate = Join-Path $VenvDir $rel
        if (Test-Path -LiteralPath $candidate) { return $candidate }
    }
    return $null
}

$candidates = @()
if ($env:LOCALGPU_HOME) {
    $candidates += $env:LOCALGPU_HOME
} else {
    # PowerShell 7 runs on macOS and Linux too, where there is no LOCALAPPDATA
    # and the bootstrap that ran was the .sh.
    if ($env:LOCALAPPDATA) { $candidates += (Join-Path $env:LOCALAPPDATA 'localgpu') }
    if ($env:HOME) { $candidates += (Join-Path $env:HOME '.local/share/localgpu') }
    elseif ($env:USERPROFILE) { $candidates += (Join-Path $env:USERPROFILE '.local/share/localgpu') }
}

$python = $null
$homeUsed = $null
foreach ($candidate in $candidates) {
    $found = Get-VenvPythonIn (Join-Path $candidate 'venv')
    if ($found) { $python = $found; $homeUsed = $candidate; break }
}

if (-not $python) {
    $detail = @('Looked in:')
    foreach ($candidate in $candidates) { $detail += "  $(Join-Path $candidate 'venv')" }
    $detail += ''
    $detail += 'Build it with the bootstrap:'
    $detail += "  pwsh -NoProfile -File $(Join-Path $script:ScriptDir 'bootstrap.ps1')"
    $detail += 'or on POSIX:'
    $detail += "  $(Join-Path $script:ScriptDir 'bootstrap.sh')"
    $detail += ''
    $detail += 'Set LOCALGPU_HOME to point at an install somewhere else.'
    Stop-Runner 'run-tests: no localgpu venv found.' $detail
}

# --- Suites -------------------------------------------------------------------
# [string[]] is load-bearing: PowerShell unwraps a one-element array back to a
# bare string, and splatting a string with @ enumerates its *characters* - the
# single-suite runs then ask pytest for a file called 'c'.
[string[]]$targets = if ($Mcp) { @('mcp/_test') } elseif ($Cli) { @('cli/_test') } else { @('mcp/_test', 'cli/_test') }

if ($Mcp -or $Cli) {
    $only = if ($Mcp) { 'mcp' } else { 'cli' }
    [Console]::Error.WriteLine("run-tests: only $only/_test - this run cannot catch a conftest collision.")
}

Write-Host "run-tests: $python"
Write-Host "run-tests: install root $homeUsed"

# PowerShell 7.3+ turns a non-zero native exit into a terminating error when
# $ErrorActionPreference is 'Stop'. A red pytest run has to come back as an exit
# code, not as an exception with a stack trace on top of the failure report.
if (Get-Variable -Name PSNativeCommandUseErrorActionPreference -Scope Global -ErrorAction SilentlyContinue) {
    $PSNativeCommandUseErrorActionPreference = $false
}

Push-Location $script:ScriptDir
try {
    & $python -m pytest @targets @PytestArgs
    $code = $LASTEXITCODE
} finally {
    Pop-Location
}

$ErrorActionPreference = $script:PreviousErrorActionPreference
exit $code

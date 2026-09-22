# SessionEnd / PreCompact hook. PowerShell twin of vault-capture.sh -- both
# delegate to vault_capture.py so neither can drift from the other.
param([string]$Trigger = 'unknown')

# Flavour guard. Both flavours are registered for every event, so on a host
# that has BOTH interpreters both would otherwise run. Stand down only when
# we can positively prove this is not Windows.
#
# $env:OS is 'Windows_NT' on BOTH Windows PowerShell 5.1 and PowerShell 7,
# and unset on Linux/macOS. A bare `if (-not $IsWindows)` is WRONG: $IsWindows
# does not exist in 5.1, so it is $null there, `-not $null` is $true, and the
# hook stands down on the one platform it exists for. crew has already shipped
# that bug once - the guard stood down on Windows and blocked nothing there.
if ($env:OS -ne 'Windows_NT') { exit 0 }

$ErrorActionPreference = 'SilentlyContinue'
$dir = Split-Path -Parent $MyInvocation.MyCommand.Path
$py = (Get-Command python3, python, py -ErrorAction SilentlyContinue |
       Select-Object -First 1).Source
if (-not $py) {
    [Console]::Error.WriteLine("obsidian-vault vault-capture.ps1: no python3/python/py interpreter found on PATH - session capture skipped.")
    exit 0
}
& $py (Join-Path $dir 'vault_capture.py') $Trigger
exit 0

# SessionEnd / PreCompact hook. PowerShell twin of vault-capture.sh -- both
# delegate to vault_capture.py so neither can drift from the other.
param([string]$Trigger = 'unknown')
$ErrorActionPreference = 'SilentlyContinue'
$dir = Split-Path -Parent $MyInvocation.MyCommand.Path
$py = (Get-Command python3, python -ErrorAction SilentlyContinue |
       Select-Object -First 1).Source
if (-not $py) { exit 0 }
& $py (Join-Path $dir 'vault_capture.py') $Trigger
exit 0

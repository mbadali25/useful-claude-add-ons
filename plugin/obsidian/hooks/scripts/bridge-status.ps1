# SessionStart hook. PowerShell twin of bridge-status.sh -- both delegate to
# bridge_status.py so neither can drift from the other.
$ErrorActionPreference = 'SilentlyContinue'
$dir = Split-Path -Parent $MyInvocation.MyCommand.Path
$py = (Get-Command python3, python -ErrorAction SilentlyContinue |
       Select-Object -First 1).Source
if (-not $py) { exit 0 }
& $py (Join-Path $dir 'bridge_status.py')
exit 0

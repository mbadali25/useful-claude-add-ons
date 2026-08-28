# PostToolUse hook. PowerShell twin of vault-guard.sh -- both delegate to
# vault_guard.py so neither can drift from the other. This hook can BLOCK
# (exit 2), so unlike bridge-status.ps1 the exit code is not silenced.
$dir = Split-Path -Parent $MyInvocation.MyCommand.Path
$py = (Get-Command python3, python -ErrorAction SilentlyContinue |
       Select-Object -First 1).Source
if (-not $py) { exit 0 }
& $py (Join-Path $dir 'vault_guard.py')
exit $LASTEXITCODE

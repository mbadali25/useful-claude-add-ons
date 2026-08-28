# PostToolUse hook. PowerShell twin of vault-guard.sh -- both delegate to
# vault_guard.py so neither can drift from the other. This hook can BLOCK
# (exit 2), so unlike bridge-status.ps1 the exit code is not silenced.
#
# No interpreter found: stand down with exit 0 rather than fail closed (exit
# 2). Every check this guard enforces ships OFF by default until a vault's
# own CLAUDE.md turns one on, so losing the guard here is not a worse failure
# mode than the guard never being configured - but it must say so loudly.
$dir = Split-Path -Parent $MyInvocation.MyCommand.Path
$py = (Get-Command python3, python, py -ErrorAction SilentlyContinue |
       Select-Object -First 1).Source
if (-not $py) {
    [Console]::Error.WriteLine("obsidian-vault vault-guard.ps1: no python3/python/py interpreter found on PATH - guard is standing down for this write (exit 0, not fail-closed; see script comment).")
    exit 0
}
& $py (Join-Path $dir 'vault_guard.py')
exit $LASTEXITCODE

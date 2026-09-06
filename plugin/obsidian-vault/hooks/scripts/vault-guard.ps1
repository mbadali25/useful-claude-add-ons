# PostToolUse hook. PowerShell twin of vault-guard.sh -- both delegate to
# vault_guard.py so neither can drift from the other. This hook can BLOCK
# (exit 2), so unlike bridge-status.ps1 the exit code is not silenced.
#
# No interpreter found: stand down with exit 0 rather than fail closed (exit
# 2). The two contract rules - frontmatter and ASCII - ship OFF until a
# vault's own CLAUDE.md turns one on, so losing those is no worse than the
# guard never being configured. The canvas shape check does NOT: checkCanvas
# defaults ON (vault_guard.py:243), so a missing interpreter does drop one
# check that would otherwise be running - it must say so loudly.
$dir = Split-Path -Parent $MyInvocation.MyCommand.Path
$py = (Get-Command python3, python, py -ErrorAction SilentlyContinue |
       Select-Object -First 1).Source
if (-not $py) {
    [Console]::Error.WriteLine("obsidian-vault vault-guard.ps1: no python3/python/py interpreter found on PATH - guard is standing down for this write (exit 0, not fail-closed; see script comment).")
    exit 0
}
& $py (Join-Path $dir 'vault_guard.py')
exit $LASTEXITCODE

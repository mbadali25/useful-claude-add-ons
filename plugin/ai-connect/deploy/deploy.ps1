# deploy: one-command Bridge / peer setup for AI-Connect. All logic lives in deploy.py,
# so this script and deploy.sh run the same steps in the same order with the same text.
#   deploy.ps1 bridge [--peer NAME ...] [--dry-run]
#   deploy.ps1 peer --name NAME --bridge IP --token-file F --auth-key-file F [--dry-run]
#   deploy.ps1 status
#   deploy.ps1 uninstall --yes [--purge] [--dry-run]
# Run bridge and uninstall from an elevated PowerShell: the scheduled task and the
# firewall rule need administrator rights.
# Self-contained on purpose: scripts/check-powershell.ps1 cannot follow a dot-source.
# Every PATH match of python3/python/py is tried: a WindowsApps python3 stub can sit
# ahead of a real interpreter and fail on launch.
$ErrorActionPreference = 'Stop'
$deploy = Join-Path $PSScriptRoot 'deploy.py'
$probe = 'import sys; sys.exit(0 if sys.version_info >= (3, 8) else 1)'
foreach ($name in 'python3', 'python', 'py') {
    foreach ($cmd in @(Get-Command $name -CommandType Application -All -ErrorAction SilentlyContinue)) {
        & $cmd.Source -c $probe *> $null
        if ($LASTEXITCODE -eq 0) {
            & $cmd.Source $deploy @args
            exit $LASTEXITCODE
        }
    }
}
[Console]::Error.WriteLine('ai-connect deploy: no working Python 3 found on PATH (tried python3, python, py)')
exit 1
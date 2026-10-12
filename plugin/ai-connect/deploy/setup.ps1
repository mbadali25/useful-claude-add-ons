# setup: from "plugin installed" to a working AI-Connect peer in one run. All logic lives in
# peer_setup.py, so this script and setup.sh take the same options in the same order and print the same text.
# Without --apply it prints the plan and changes nothing.
#   setup.ps1 bridge [--peer NAME ...] [--enrol NAME=SHA256 ...] [--register-mcp] [--apply]
#   setup.ps1 peer --name NAME --bridge IP [--token-file F | --invite-file F] [--register-mcp] [--apply]
#   setup.ps1 session --name NAME [--apply]
# It never runs `deploy tailnet-setup` (the owner's step: it replaces the tailnet policy).
# Run `bridge --apply` from an elevated PowerShell: the scheduled task and the firewall rule need
# administrator rights.
# Self-contained on purpose: scripts/check-powershell.ps1 cannot follow a dot-source.
# Every PATH match of python3/python/py is tried: a WindowsApps python3 stub can sit
# ahead of a real interpreter and fail on launch.
$ErrorActionPreference = 'Stop'
$setup = Join-Path $PSScriptRoot 'peer_setup.py'
$probe = 'import sys; sys.exit(0 if sys.version_info >= (3, 8) else 1)'
foreach ($name in 'python3', 'python', 'py') {
    foreach ($cmd in @(Get-Command $name -CommandType Application -All -ErrorAction SilentlyContinue)) {
        & $cmd.Source -c $probe *> $null
        if ($LASTEXITCODE -eq 0) {
            & $cmd.Source $setup @args
            exit $LASTEXITCODE
        }
    }
}
[Console]::Error.WriteLine('ai-connect setup: no working Python 3 found on PATH (tried python3, python, py)')
exit 1

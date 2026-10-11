# mint-key: see README.md. All logic lives in tsadmin.py.
# Self-contained on purpose: scripts/check-powershell.ps1 cannot follow a dot-source,
# so each shim carries this loop rather than sharing a helper file.
# Every PATH match of python3/python/py is tried: a WindowsApps python3 stub can sit
# ahead of a real interpreter and fail on launch.
$ErrorActionPreference = 'Stop'
$tsadmin = Join-Path $PSScriptRoot 'tsadmin.py'
$probe = 'import sys; sys.exit(0 if sys.version_info >= (3, 8) else 1)'
foreach ($name in 'python3', 'python', 'py') {
    foreach ($cmd in @(Get-Command $name -CommandType Application -All -ErrorAction SilentlyContinue)) {
        & $cmd.Source -c $probe *> $null
        if ($LASTEXITCODE -eq 0) {
            & $cmd.Source $tsadmin mint-key @args
            exit $LASTEXITCODE
        }
    }
}
[Console]::Error.WriteLine('ai-connect vpn: no working Python 3.8+ found on PATH (tried python3, python, py)')
exit 1

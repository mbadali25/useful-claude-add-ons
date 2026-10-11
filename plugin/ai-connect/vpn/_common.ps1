# Dot-sourced by the vpn shims: find a python that actually RUNS and hand it tsadmin.py.
# Every PATH match of python3/python/py is tried: a WindowsApps python3 stub can sit
# ahead of a real interpreter and fail on launch.

function Invoke-VpnTsadmin {
    param([string[]]$Arguments)
    $script = Join-Path $PSScriptRoot 'tsadmin.py'
    $probe = 'import sys; sys.exit(0 if sys.version_info >= (3, 8) else 1)'
    foreach ($name in 'python3', 'python', 'py') {
        foreach ($cmd in @(Get-Command $name -CommandType Application -All -ErrorAction SilentlyContinue)) {
            & $cmd.Source -c $probe *> $null
            if ($LASTEXITCODE -eq 0) {
                & $cmd.Source $script @Arguments
                exit $LASTEXITCODE
            }
        }
    }
    [Console]::Error.WriteLine('ai-connect vpn: no working Python 3.8+ found on PATH (tried python3, python, py)')
    exit 1
}

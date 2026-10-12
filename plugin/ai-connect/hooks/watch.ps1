# SessionStart / Stop asyncRewake hook: PowerShell twin of watch.sh. Runs the
# AI-Connect message watcher with this plugin's venv. Exit 2 wakes the session
# (a message arrived), 0 = another watcher already runs, 1 = error (reason on
# stderr). hooks.json re-raises the exit code with '; exit $LASTEXITCODE',
# without which PowerShell's -Command would turn the 2 into a 1.

# Flavour guard. Both flavours are registered for every event; stand down
# unless this is provably Windows, where watch.sh stands down instead.
# $env:OS is 'Windows_NT' on both Windows PowerShell 5.1 and PowerShell 7 and
# unset elsewhere. Do not use $IsWindows: it does not exist in 5.1.
if ($env:OS -ne 'Windows_NT') { exit 0 }

$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$python = Join-Path $root 'venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) {
    # The plugin cache directory changes on every plugin update, and the venv
    # lives inside it, so an update leaves the new directory without one.
    [Console]::Error.WriteLine("ai-connect watch.ps1: no venv at $(Join-Path $root 'venv') - run $(Join-Path $root 'install.cmd') -Client (again after each plugin update)")
    exit 1
}
& $python (Join-Path $root 'integrations\claude-code\aiconnect_watch.py')
exit $LASTEXITCODE

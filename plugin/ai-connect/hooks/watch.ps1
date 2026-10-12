# SessionStart / Stop asyncRewake hook: PowerShell twin of watch.sh. Runs the
# AI-Connect message watcher with this plugin's venv. Exit 2 wakes the session
# (a message arrived), 0 = another watcher already runs or AI-Connect was never
# set up on this machine, 1 = error (reason on stderr). hooks.json re-raises the exit code with '; exit $LASTEXITCODE',
# without which PowerShell's -Command would turn the 2 into a 1.

# Flavour guard. Both flavours are registered for every event; stand down
# unless this is provably Windows, where watch.sh stands down instead.
# $env:OS is 'Windows_NT' on both Windows PowerShell 5.1 and PowerShell 7 and
# unset elsewhere. Do not use $IsWindows: it does not exist in 5.1.
if ($env:OS -ne 'Windows_NT') { exit 0 }

$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$python = Join-Path $root 'venv\Scripts\python.exe'
# The installer writes this outside the plugin directory (config_loader.py's
# CONFIG_PATH: Path.home(), which is USERPROFILE on Windows), so it survives a
# plugin update and tells "never set up" from "set up, then the venv went with
# the old plugin directory".
$userHome = if ($env:USERPROFILE) { $env:USERPROFILE } else { $HOME }
$config = Join-Path (Join-Path (Join-Path $userHome '.config') 'ai-connect') 'config.yaml'
if (-not (Test-Path -LiteralPath $python)) {
    if (-not (Test-Path -LiteralPath $config)) {
        # Never set up: the plugin is installed but its installer has not run.
        # Nothing to watch and nothing to report: say nothing on every event.
        exit 0
    }
    # The plugin cache directory changes on every plugin update, and the venv
    # lives inside it, so an update leaves the new directory without one.
    [Console]::Error.WriteLine("ai-connect watch.ps1: no venv at $(Join-Path $root 'venv') - run $(Join-Path $root 'install.cmd') -Client (again after each plugin update)")
    exit 1
}
& $python (Join-Path $root 'integrations\claude-code\aiconnect_watch.py')
exit $LASTEXITCODE

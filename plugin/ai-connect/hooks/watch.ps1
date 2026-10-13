# SessionStart / Stop asyncRewake hook: PowerShell twin of watch.sh. Runs the
# AI-Connect message watcher with the venv this machine was set up with. Exit 2
# wakes the session (a message arrived), 0 = another watcher already runs or
# AI-Connect was never set up on this machine, 1 = error (reason on stderr).
# hooks.json re-raises the exit code with '; exit $LASTEXITCODE',
# without which PowerShell's -Command would turn the 2 into a 1.

# Flavour guard. Both flavours are registered for every event; stand down
# unless this is provably Windows, where watch.sh stands down instead.
# $env:OS is 'Windows_NT' on both Windows PowerShell 5.1 and PowerShell 7 and
# unset elsewhere. Do not use $IsWindows: it does not exist in 5.1.
if ($env:OS -ne 'Windows_NT') { exit 0 }

$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$watcher = 'integrations\claude-code\aiconnect_watch.py'
# The installer writes this outside the plugin directory (config_loader.py's
# CONFIG_PATH: Path.home(), which is USERPROFILE on Windows), so it survives a
# plugin update and tells "never set up" from "set up, then the venv went with
# the old plugin directory".
$userHome = if ($env:USERPROFILE) { $env:USERPROFILE } else { $HOME }
$config = Join-Path (Join-Path (Join-Path $userHome '.config') 'ai-connect') 'config.yaml'

# Where deploy\deploy.py (deploy.ps1, setup.ps1) installs: deploy_core.py's
# APP_HOME, with the venv in it and a copy of the plugin beside that. On
# Windows that is Path.home() joined with AppData\Local, not %LOCALAPPDATA%.
if ($env:AI_CONNECT_HOME) {
    $deployHome = $env:AI_CONNECT_HOME
} else {
    $deployHome = Join-Path (Join-Path (Join-Path $userHome 'AppData') 'Local') 'ai-connect'
}

# The first venv that is there, in this order. watch.sh has the same three.
#   1. AI_CONNECT_VENV, the variable deploy_core.py reads for its venv
#   2. the plugin directory's own venv, where install.cmd creates it
#   3. deploy's venv
# $app is the directory the watcher script is run from. With deploy's venv it
# is deploy's copy of the plugin when that holds the watcher (`deploy bridge`,
# `deploy peer --register-mcp`): the MCP server of this machine runs from that
# copy, with that venv. `deploy peer --install-hooks` alone makes the venv and
# no copy, and then the watcher is this plugin's own.
$python = $null
$app = $root
$envPython = if ($env:AI_CONNECT_VENV) { Join-Path $env:AI_CONNECT_VENV 'Scripts\python.exe' } else { $null }
$ownPython = Join-Path $root 'venv\Scripts\python.exe'
$deployPython = Join-Path $deployHome 'venv\Scripts\python.exe'
if ($envPython -and (Test-Path -LiteralPath $envPython -PathType Leaf)) {
    $python = $envPython
} elseif (Test-Path -LiteralPath $ownPython -PathType Leaf) {
    $python = $ownPython
} elseif (Test-Path -LiteralPath $deployPython -PathType Leaf) {
    $python = $deployPython
    $deployApp = Join-Path $deployHome 'app'
    if (Test-Path -LiteralPath (Join-Path $deployApp $watcher) -PathType Leaf) {
        $app = $deployApp
    }
}

if (-not $python) {
    if (-not (Test-Path -LiteralPath $config)) {
        # Never set up: the plugin is installed but no installer has run.
        # Nothing to watch and nothing to report: say nothing on every event.
        exit 0
    }
    # Set up, and no venv anywhere it is looked for. The plugin cache directory
    # changes on every plugin update, so a venv install.cmd made inside it does
    # not come along; deploy's lives outside it and does.
    $looked = "$(Join-Path $root 'venv') or $(Join-Path $deployHome 'venv')"
    if ($env:AI_CONNECT_VENV) { $looked = "$($env:AI_CONNECT_VENV) (AI_CONNECT_VENV) or $looked" }
    [Console]::Error.WriteLine("ai-connect watch.ps1: no venv at $looked - run $(Join-Path $root 'install.cmd') -Client (again after each plugin update), or $(Join-Path (Join-Path $root 'deploy') 'deploy.ps1') peer once")
    exit 1
}
& $python (Join-Path $app $watcher)
exit $LASTEXITCODE

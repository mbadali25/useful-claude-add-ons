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
# USERPROFILE comes from the environment, which a project's settings can set. On Windows, where
# the OS names the profile directory, a USERPROFILE that is not that directory and lies inside
# the project the session runs in is replaced by the OS's answer.
$userHome = if ($env:USERPROFILE) { $env:USERPROFILE } else { $HOME }
$acctHome = [Environment]::GetFolderPath('UserProfile')
if ($acctHome -and ([Environment]::OSVersion.Platform -eq 'Win32NT') `
        -and ($userHome.TrimEnd('\', '/') -ne $acctHome.TrimEnd('\', '/'))) {
    foreach ($project in @($env:CLAUDE_PROJECT_DIR, (Get-Location).ProviderPath)) {
        if (-not $project) { continue }
        $prefix = $project.TrimEnd('\', '/') + '\'
        if (($userHome.TrimEnd('\', '/') + '\').StartsWith($prefix, [StringComparison]::OrdinalIgnoreCase)) {
            $userHome = $acctHome
        }
    }
}
$config = Join-Path (Join-Path (Join-Path $userHome '.config') 'ai-connect') 'config.yaml'

# AI_CONNECT_VENV and AI_CONNECT_HOME choose which interpreter this hook starts on every
# SessionStart and Stop, and a project's settings.json can set environment variables. So a
# value is used only when it names a directory that is an absolute path with no '..', that
# lies under the user's own home, and that is not inside the project the session runs in
# (the current directory, CLAUDE_PROJECT_DIR): a repository cannot plant the interpreter
# this hook runs. A value that fails is ignored, as if unset. Paths are compared as text
# after Resolve-Path (it does not follow links): this is not a defence against an
# attacker who can already write under the user's home.
$isWin = [Environment]::OSVersion.Platform -eq 'Win32NT'
$cmp = if ($isWin) { [StringComparison]::OrdinalIgnoreCase } else { [StringComparison]::Ordinal }
$sepChar = [IO.Path]::DirectorySeparatorChar
function Resolve-Real([string]$dir) {
    try { return (Resolve-Path -LiteralPath $dir -ErrorAction Stop).ProviderPath.TrimEnd('\', '/') } catch { return $null }
}
function Test-Under([string]$child, [string]$parent) {
    return ($child + $sepChar).StartsWith(($parent + $sepChar), $cmp)
}
function Test-TrustedDir([string]$dir) {
    if (-not $dir) { return $false }
    if (-not [IO.Path]::IsPathRooted($dir)) { return $false }
    if ($dir -match '(^|[\\/])\.\.([\\/]|$)') { return $false }
    $real = Resolve-Real $dir
    $homeReal = Resolve-Real $userHome
    if (-not $real -or -not $homeReal) { return $false }
    if (-not (Test-Under $real $homeReal)) { return $false }
    foreach ($project in @($env:CLAUDE_PROJECT_DIR, (Get-Location).ProviderPath)) {
        if (-not $project) { continue }
        $projectReal = Resolve-Real $project
        if (-not $projectReal) { continue }
        # A project directory that is the home or above it holds everything under the home
        if (Test-Under $homeReal $projectReal) { continue }
        if (Test-Under $real $projectReal) { return $false }
    }
    return $true
}

# Where deploy\deploy.py (deploy.ps1, setup.ps1) installs: deploy_core.py's
# APP_HOME, with the venv in it and a copy of the plugin beside that. On
# Windows that is Path.home() joined with AppData\Local, not %LOCALAPPDATA%.
$defaultHome = Join-Path (Join-Path (Join-Path $userHome 'AppData') 'Local') 'ai-connect'
$deployHome = $defaultHome
if ($env:AI_CONNECT_HOME -and (Test-TrustedDir $env:AI_CONNECT_HOME)) {
    $deployHome = $env:AI_CONNECT_HOME
}
$hasConfig = Test-Path -LiteralPath $config

# The first venv that is there, in this order. watch.sh has the same three.
#   1. AI_CONNECT_VENV, the variable deploy_core.py reads for its venv (trusted, see above)
#   2. the plugin directory's own venv, where install.cmd creates it
#   3. deploy's venv
# $app is the directory the watcher script is run from. With deploy's venv it
# is deploy's copy of the plugin when that holds the watcher (`deploy bridge`,
# `deploy peer --register-mcp`): the MCP server of this machine runs from that
# copy, with that venv. `deploy peer --install-hooks` alone makes the venv and
# no copy, and then the watcher is this plugin's own.
# Anything chosen through a variable needs the config too: a machine that was never set
# up stays silent whatever the variables say.
$python = $null
$app = $root
$envPython = if ($env:AI_CONNECT_VENV) { Join-Path $env:AI_CONNECT_VENV 'Scripts\python.exe' } else { $null }
$ownPython = Join-Path $root 'venv\Scripts\python.exe'
$deployPython = Join-Path $deployHome 'venv\Scripts\python.exe'
if ($hasConfig -and $envPython -and (Test-TrustedDir $env:AI_CONNECT_VENV) -and (Test-Path -LiteralPath $envPython -PathType Leaf)) {
    $python = $envPython
} elseif (Test-Path -LiteralPath $ownPython -PathType Leaf) {
    $python = $ownPython
} elseif ((Test-Path -LiteralPath $deployPython -PathType Leaf) -and ($hasConfig -or $deployHome -eq $defaultHome)) {
    $python = $deployPython
    $deployApp = Join-Path $deployHome 'app'
    if (Test-Path -LiteralPath (Join-Path $deployApp $watcher) -PathType Leaf) {
        $app = $deployApp
    }
}

if (-not $python) {
    if (-not $hasConfig) {
        # Never set up: the plugin is installed but no installer has run.
        # Nothing to watch and nothing to report: say nothing on every event.
        exit 0
    }
    # Set up, and no venv anywhere it is looked for. The plugin cache directory
    # changes on every plugin update, so a venv install.cmd made inside it does
    # not come along; deploy's lives outside it and does. The message names
    # places, not the values of the variables.
    [Console]::Error.WriteLine("ai-connect watch.ps1: no venv found (looked in $(Join-Path $root 'venv'), in deploy's %USERPROFILE%\AppData\Local\ai-connect\venv or under AI_CONNECT_HOME, and at AI_CONNECT_VENV; a variable that is not an absolute path under your home, outside the project, is ignored) - run $(Join-Path $root 'install.cmd') -Client (again after each plugin update), or $(Join-Path (Join-Path $root 'deploy') 'deploy.ps1') peer once")
    exit 1
}
# A project's settings can set PYTHONPATH and friends, which would make a trusted interpreter
# import the repository's code
foreach ($name in 'PYTHONPATH', 'PYTHONHOME', 'PYTHONSTARTUP', 'PYTHONINSPECT', 'PYTHONUSERBASE', 'PYTHONEXECUTABLE') {
    Remove-Item -LiteralPath "Env:$name" -ErrorAction SilentlyContinue
}
& $python (Join-Path $app $watcher)
exit $LASTEXITCODE

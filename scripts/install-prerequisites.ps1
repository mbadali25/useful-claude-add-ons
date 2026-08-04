#Requires -Version 5.1
<#
Bootstraps a Windows machine for this repo's skills: Chocolatey, git/awscli/nodejs/python,
the Claude Code CLI itself (with its path exported to the user PATH), and the team's
standard Claude Code plugin marketplaces. Idempotent - safe to re-run.

Everything is chosen from a menu up front, then installed unattended. The menu replaced
a linear run of ~15 yes/no prompts, which meant you had to sit through the whole script
to decline three things near the end. Every interactive answer (menu selection, Headroom
mode) is collected before the first install starts.

Everything is also detected before it is installed:
  * Chocolatey packages   - skipped when the package is already present (or its
                            command already resolves, e.g. git installed outside choco)
  * Marketplaces          - skipped when already registered (matched by name or repo)
  * Plugins               - skipped when already installed; optionally updated

Marketplaces and plugins are installed with the native 'claude plugin marketplace add'
and 'claude plugin install' commands - no 'npx claudepluginhub' wrapper. The wrapper
synthesized a local directory-backed marketplace per repo, which failed on Windows and
produced marketplace names ('cpd-<repo>-user') that this script's detection could not
match, so already-installed plugins were reinstalled on every run.

Run from an elevated (Administrator) PowerShell prompt for the full setup:
    .\scripts\install-prerequisites.ps1

If run from a non-elevated prompt, Chocolatey and the Chocolatey packages
(git/awscli/nodejs/python) are skipped - everything else still runs.

Common switches:
    -All                select every menu item, no prompt
    -Select '1,3,7-9'   select these menu items, no prompt (also accepts keys:
                        -Select 'headroom,claude-mem')
    -NonInteractive     select the default set, no prompt (CI/unattended)
    -HeadroomMode       deploy|wrap|proxy|library|skip - skips the Headroom mode prompt
    -NoUpdate           never update an already-installed plugin, only report it
    -SkipBootstrap      narrow the selection to prerequisites + the Claude Code CLI
    -InstallScope       scope for marketplace/plugin installs: user (default), project, local
                        (accepts -PluginHubScope as an alias for backward compatibility)
#>

[CmdletBinding()]
param(
    [switch]$SkipBootstrap,   # narrow the selection to prerequisites + CLI
    [switch]$NonInteractive,  # take the default selection, no menu
    [switch]$NoUpdate,        # don't update already-installed plugins
    [switch]$All,             # select every menu item, no menu
    [string]$Select,          # explicit selection, no menu: '1,3,7-9' or 'headroom,gsd'
    [ValidateSet('deploy', 'wrap', 'proxy', 'library', 'skip')]
    [string]$HeadroomMode,    # answer the Headroom mode prompt up front
    [Alias('PluginHubScope')]
    [ValidateSet('user', 'project', 'local')]
    [string]$InstallScope = 'user'  # machine-wide by default, not per-project
)

$ErrorActionPreference = 'Stop'
$script:FailedSteps = @()
$script:Summary = [ordered]@{ Installed = 0; Updated = 0; Skipped = 0 }

function Write-Step { param([string]$Message) Write-Host "`n==> $Message" -ForegroundColor Cyan }
function Write-Ok   { param([string]$Message) Write-Host "    OK: $Message" -ForegroundColor Green }
function Write-Warn2 { param([string]$Message) Write-Host "    WARN: $Message" -ForegroundColor Yellow }
function Write-Skip { param([string]$Message) Write-Host "    SKIP: $Message" -ForegroundColor DarkGray; $script:Summary.Skipped++ }

function Test-Admin {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Sync-SessionEnvironment {
    # Chocolatey/npm installers write to the registry environment but never touch this
    # running process. git is the worst offender: it adds its own PATH entries *and*
    # GIT_INSTALL_ROOT, both of which later steps (git clone, Git Bash) depend on.
    # Refresh the whole environment, not just PATH, so those steps don't fail.
    # Prefer Chocolatey's own refreshenv implementation when it's available.
    $chocoProfile = if ($env:ChocolateyInstall) {
        Join-Path $env:ChocolateyInstall 'helpers\chocolateyProfile.psm1'
    } else { $null }

    if ($chocoProfile -and (Test-Path $chocoProfile)) {
        try {
            Import-Module $chocoProfile -DisableNameChecking -Force -ErrorAction Stop
            Update-SessionEnvironment
            return
        } catch {
            Write-Warn2 "Chocolatey refreshenv unavailable ($($_.Exception.Message)) - falling back to a manual refresh."
        }
    }

    # Manual fallback: replay Machine then User scope onto the process, leaving the
    # vars that are process-owned by nature alone.
    $preserve = @('USERNAME', 'COMPUTERNAME', 'PROCESSOR_ARCHITECTURE', 'PSModulePath', 'Path')
    foreach ($scope in 'Machine', 'User') {
        $vars = [Environment]::GetEnvironmentVariables($scope)
        foreach ($name in $vars.Keys) {
            if ($preserve -contains $name) { continue }
            [Environment]::SetEnvironmentVariable($name, $vars[$name], 'Process')
        }
    }
    $machinePath = [Environment]::GetEnvironmentVariable('Path', 'Machine')
    $userPath = [Environment]::GetEnvironmentVariable('Path', 'User')
    $env:Path = (@($machinePath, $userPath) | Where-Object { $_ }) -join ';'
}

function Invoke-Step {
    param([string]$Name, [scriptblock]$Action)
    Write-Step $Name
    try {
        & $Action
    } catch {
        Write-Warn2 "$Name failed: $($_.Exception.Message)"
        $script:FailedSteps += $Name
    }
}

# --- Detection helpers -------------------------------------------------------

function Test-ClaudeAvailable {
    return [bool](Get-Command claude -ErrorAction SilentlyContinue)
}

function Get-ClaudeConfigRoot {
    if ($env:CLAUDE_CONFIG_DIR) { return $env:CLAUDE_CONFIG_DIR }
    return (Join-Path $env:USERPROFILE '.claude')
}

$script:ChocoCache = $null
function Get-ChocoInstalled {
    # name -> version for every locally installed Chocolatey package.
    # 'choco list' is local-only in v2+; v1 needed --local-only, which v2 rejects.
    param([switch]$Refresh)
    if ($script:ChocoCache -and -not $Refresh) { return $script:ChocoCache }
    $map = @{}
    if (Get-Command choco -ErrorAction SilentlyContinue) {
        # Not $args - that's an automatic variable inside a function.
        $chocoArgs = @('list', '--limit-output')
        $major = 0
        try { $major = [int](([string](choco --version)).Split('.')[0]) } catch { $major = 0 }
        if ($major -lt 2) { $chocoArgs += '--local-only' }
        try {
            foreach ($line in (& choco @chocoArgs)) {
                $parts = "$line".Split('|')
                if ($parts.Count -ge 2 -and $parts[0]) { $map[$parts[0].Trim().ToLower()] = $parts[1].Trim() }
            }
        } catch {
            Write-Warn2 "Could not enumerate Chocolatey packages: $($_.Exception.Message)"
        }
    }
    $script:ChocoCache = $map
    return $map
}

function Test-ChocoPackageInstalled {
    # A package counts as present if Chocolatey knows about it under its own name or
    # the '.install' variant (nodejs installs as nodejs.install), or - importantly -
    # if the command it provides already resolves, since plenty of machines have git
    # or python installed outside Chocolatey and reinstalling would be wrong.
    param([string]$Package, [string]$Probe)
    $installed = Get-ChocoInstalled
    $key = $Package.ToLower()
    foreach ($candidate in @($key, "$key.install")) {
        if ($installed.ContainsKey($candidate)) {
            return [pscustomobject]@{ Present = $true; How = "choco package '$candidate' $($installed[$candidate])" }
        }
    }
    if ($Probe) {
        $cmd = Get-Command $Probe -ErrorAction SilentlyContinue
        if ($cmd) {
            return [pscustomobject]@{ Present = $true; How = "'$Probe' already resolves at $($cmd.Source)" }
        }
    }
    return [pscustomobject]@{ Present = $false; How = $null }
}

$script:MarketplaceCache = $null
function Get-ClaudeMarketplaces {
    param([switch]$Refresh)
    if ($null -ne $script:MarketplaceCache -and -not $Refresh) { return $script:MarketplaceCache }
    $list = @()
    if (Test-ClaudeAvailable) {
        try {
            $raw = claude plugin marketplace list --json
            if ($raw) { $list = @($raw | ConvertFrom-Json) }
        } catch {
            Write-Warn2 "Could not read marketplace list: $($_.Exception.Message)"
        }
    }
    $script:MarketplaceCache = $list
    return $list
}

function Test-MarketplaceInstalled {
    # Accepts either a marketplace name ('superpowers-marketplace') or the GitHub
    # 'owner/repo' it was added from - the JSON carries both, and callers have one
    # or the other depending on which command registered it.
    param([string]$Identifier)
    foreach ($m in (Get-ClaudeMarketplaces)) {
        if ($m.name -and $m.name -eq $Identifier) { return $true }
        if ($m.repo -and $m.repo -eq $Identifier) { return $true }
        # 'owner/repo' also matches a marketplace named after just the repo half
        if ($Identifier -match '/' -and $m.name -eq $Identifier.Split('/')[-1]) { return $true }
    }
    return $false
}

$script:PluginCache = $null
function Get-ClaudePlugins {
    # name -> version, keyed on the bare plugin name (ids are 'name@marketplace').
    param([switch]$Refresh)
    if ($null -ne $script:PluginCache -and -not $Refresh) { return $script:PluginCache }
    $map = @{}
    if (Test-ClaudeAvailable) {
        try {
            $raw = claude plugin list --json
            if ($raw) {
                foreach ($p in @($raw | ConvertFrom-Json)) {
                    if (-not $p.id) { continue }
                    $name = "$($p.id)".Split('@')[0]
                    $map[$name] = [pscustomobject]@{ Id = $p.id; Version = $p.version; Enabled = $p.enabled }
                }
            }
        } catch {
            Write-Warn2 "Could not read plugin list: $($_.Exception.Message)"
        }
    }
    $script:PluginCache = $map
    return $map
}

function Get-ClaudeSkillsDir {
    # Some things (the 'skills' CLI, task-observer) install as plain user-level skills
    # rather than as Claude Code plugins, so they never show up in 'claude plugin list' -
    # detection for those is a filesystem check against the user-level skills directory.
    return (Join-Path (Get-ClaudeConfigRoot) 'skills')
}

function Test-UserSkillInstalled {
    param([string]$Name)
    return (Test-Path (Join-Path (Join-Path (Get-ClaudeSkillsDir) $Name) 'SKILL.md'))
}

# --- Install wrappers (detect, then act) -------------------------------------

function Add-ClaudeMarketplace {
    param([string]$Source, [string]$Name)
    $probe = if ($Name) { $Name } else { $Source }
    if (Test-MarketplaceInstalled $probe) {
        Write-Skip "marketplace '$probe' already registered"
        if (-not $NoUpdate) {
            $mp = (Get-ClaudeMarketplaces) | Where-Object { $_.name -eq $probe -or $_.repo -eq $probe } | Select-Object -First 1
            if ($mp -and $mp.name) {
                claude plugin marketplace update $mp.name | Out-Null
                Write-Ok "refreshed marketplace metadata for '$($mp.name)'"
            }
        }
        return
    }
    claude plugin marketplace add $Source --scope $InstallScope
    Get-ClaudeMarketplaces -Refresh | Out-Null
    $script:Summary.Installed++
    Write-Ok "added marketplace '$Source'"
}

function Install-ClaudePlugin {
    # $Spec is 'name@marketplace'. Detection is on the bare name, so a plugin already
    # installed from a *different* marketplace counts as present and is not duplicated.
    param([string]$Spec)
    $name = $Spec.Split('@')[0]
    $existing = (Get-ClaudePlugins)[$name]
    if ($existing) {
        if ($NoUpdate) {
            Write-Skip "plugin '$name' already installed ($($existing.Id), version $($existing.Version))"
            return
        }
        $before = $existing.Version
        claude plugin update $name | Out-Null
        $after = (Get-ClaudePlugins -Refresh)[$name].Version
        if ($after -ne $before) {
            $script:Summary.Updated++
            Write-Ok "plugin '$name' updated $before -> $after"
        } else {
            Write-Skip "plugin '$name' already current (version $after)"
        }
        return
    }
    claude plugin install $Spec --scope $InstallScope
    Get-ClaudePlugins -Refresh | Out-Null
    $script:Summary.Installed++
    Write-Ok "installed plugin '$Spec'"
}

# --- Install catalog and menu -------------------------------------------------
# One ordered entry per selectable item. 'Key' is what the rest of the script tests
# with Test-Selected; 'Default' is what [D] (and -NonInteractive) picks, chosen to
# match the prompt defaults this script used before it had a menu.
$script:Catalog = @(
    [pscustomobject]@{ Key = 'prereqs';           Default = $true;  Name = 'Prerequisites: Chocolatey + git, awscli, nodejs, python (needs Administrator)' }
    [pscustomobject]@{ Key = 'cli';               Default = $true;  Name = 'Claude Code CLI (@anthropic-ai/claude-code) + PATH export' }
    [pscustomobject]@{ Key = 'own-skills';        Default = $true;  Name = "This repo's marketplace + its 19 skills" }
    [pscustomobject]@{ Key = 'team';              Default = $true;  Name = 'Team plugins: superpowers, frontend-design, excalidraw-generator' }
    [pscustomobject]@{ Key = 'find-skills';       Default = $true;  Name = 'find-skills skill (vercel-labs/skills)' }
    [pscustomobject]@{ Key = 'community';         Default = $true;  Name = 'Community marketplaces + plugins (adhd-output-style, azure-tools, ppt-master, ...)' }
    [pscustomobject]@{ Key = 'claude-code-setup'; Default = $true;  Name = 'claude-code-setup plugin (anthropics/claude-plugins-official)' }
    [pscustomobject]@{ Key = 'task-observer';     Default = $true;  Name = 'task-observer skill (rebelytics/one-skill-to-rule-them-all)' }
    [pscustomobject]@{ Key = 'claude-mem';        Default = $true;  Name = 'claude-mem memory plugin + CLAUDE_MEM_WORKER_PORT in settings.json' }
    [pscustomobject]@{ Key = 'gsd';               Default = $true;  Name = 'GSD (@opengsd/gsd-core)' }
    [pscustomobject]@{ Key = 'voltagent';         Default = $true;  Name = 'VoltAgent subagents (10 plugins, 154 agents)' }
    [pscustomobject]@{ Key = 'aws-mcp';           Default = $false; Name = 'AWS MCP server (awslabs.aws-api-mcp-server)' }
    [pscustomobject]@{ Key = 'azure-mcp';         Default = $false; Name = 'Azure MCP server (@azure/mcp)' }
    [pscustomobject]@{ Key = 'headroom';          Default = $false; Name = 'Headroom: pipx + headroom-ai[all] + mode setup + doctor' }
)

$script:Selected = @{}
function Test-Selected { param([string]$Key) return [bool]$script:Selected[$Key] }

function Expand-SelectionSpec {
    # '1,3,7-9' -> the matching catalog keys. Item keys are accepted too, so
    # -Select 'headroom,claude-mem' works without counting rows in the menu.
    param([string]$Spec)
    $keys = @()
    foreach ($token in ($Spec -split '[,\s]+' | Where-Object { $_ })) {
        if ($token -match '^(\d+)\s*-\s*(\d+)$') {
            foreach ($n in [int]$Matches[1]..[int]$Matches[2]) {
                if ($n -ge 1 -and $n -le $script:Catalog.Count) { $keys += $script:Catalog[$n - 1].Key }
            }
        } elseif ($token -match '^\d+$') {
            $n = [int]$token
            if ($n -ge 1 -and $n -le $script:Catalog.Count) {
                $keys += $script:Catalog[$n - 1].Key
            } else {
                Write-Warn2 "ignoring out-of-range menu number '$token'"
            }
        } else {
            $hit = $script:Catalog | Where-Object { $_.Key -eq $token.ToLower() } | Select-Object -First 1
            if ($hit) { $keys += $hit.Key } else { Write-Warn2 "ignoring unknown menu item '$token'" }
        }
    }
    return $keys
}

function Show-InstallMenu {
    Write-Host ""
    Write-Host "  Select what to install" -ForegroundColor Cyan
    Write-Host "  ----------------------" -ForegroundColor Cyan
    for ($i = 0; $i -lt $script:Catalog.Count; $i++) {
        $item = $script:Catalog[$i]
        $mark = if ($item.Default) { 'x' } else { ' ' }
        Write-Host ("  {0,2}  [{1}]  {2}" -f ($i + 1), $mark, $item.Name)
    }
    Write-Host ""
    Write-Host "  [x] marks the default set." -ForegroundColor DarkGray
    Write-Host "  A = all   D = defaults   N = none   or numbers like 1,3,7-9" -ForegroundColor DarkGray
}

function Select-InstallItems {
    $defaults = @($script:Catalog | Where-Object { $_.Default } | ForEach-Object { $_.Key })
    $everything = @($script:Catalog | ForEach-Object { $_.Key })

    $keys = @()
    if ($All) {
        $keys = $everything
        Write-Host "Selecting every item (-All)." -ForegroundColor DarkGray
    } elseif ($Select) {
        $keys = Expand-SelectionSpec $Select
        Write-Host "Selecting from -Select '$Select'." -ForegroundColor DarkGray
    } elseif ($NonInteractive) {
        $keys = $defaults
        Write-Host "Selecting the default set (-NonInteractive)." -ForegroundColor DarkGray
    } else {
        Show-InstallMenu
        $answer = "$(Read-Host '  Select [D]')".Trim()
        if ([string]::IsNullOrWhiteSpace($answer)) { $answer = 'D' }
        switch -Regex ($answer) {
            '^(?i)a(ll)?$'       { $keys = $everything; break }
            '^(?i)d(efaults?)?$' { $keys = $defaults;   break }
            '^(?i)n(one)?$'      { $keys = @();         break }
            default              { $keys = Expand-SelectionSpec $answer }
        }
    }

    $script:Selected = @{}
    foreach ($k in $keys) { $script:Selected[$k] = $true }

    if ($SkipBootstrap) {
        # -SkipBootstrap predates the menu, where it meant "prerequisites and the CLI
        # only". Keep that meaning by intersecting the selection rather than replacing it.
        foreach ($item in $script:Catalog) {
            if ($item.Key -ne 'prereqs' -and $item.Key -ne 'cli') { $script:Selected.Remove($item.Key) }
        }
        Write-Host "Narrowed to prerequisites + CLI (-SkipBootstrap)." -ForegroundColor DarkGray
    }
}

function Show-Selection {
    $chosen = @($script:Catalog | Where-Object { Test-Selected $_.Key })
    Write-Host ""
    if ($chosen.Count -eq 0) {
        Write-Host "  Nothing selected." -ForegroundColor Yellow
        return
    }
    Write-Host "  Will install ($($chosen.Count) item(s)):" -ForegroundColor Cyan
    foreach ($item in $chosen) { Write-Host "    - $($item.Name)" }
}

function Select-HeadroomMode {
    # Asked up front, alongside the menu, so the install run itself stays unattended.
    if ($HeadroomMode) { return $HeadroomMode }
    if ($NonInteractive -or $All -or $Select) { return 'deploy' }
    Write-Host ""
    Write-Host "  Headroom mode" -ForegroundColor Cyan
    Write-Host "    1  deploy   turnkey local deployment + agent config  (recommended)"
    Write-Host "    2  wrap     wrap the claude coding agent"
    Write-Host "    3  proxy    drop-in proxy on port 8787, zero code changes"
    Write-Host "    4  library  no CLI wiring; use 'from headroom import compress'"
    Write-Host "    5  skip     install only, configure later"
    $answer = "$(Read-Host '  Mode [1]')".Trim()
    switch ($answer) {
        '2' { return 'wrap' }
        '3' { return 'proxy' }
        '4' { return 'library' }
        '5' { return 'skip' }
        default { return 'deploy' }
    }
}

# --- Python / pipx helpers (Headroom) ----------------------------------------

function Get-PythonLauncher {
    # 'py' first: the Windows launcher is what makes '-3.14' style version selection work.
    foreach ($candidate in 'py', 'python', 'python3') {
        if (Get-Command $candidate -ErrorAction SilentlyContinue) { return $candidate }
    }
    return $null
}

function Add-UserScriptsToPath {
    # 'pip install --user' drops console scripts in the per-user Scripts directory,
    # which is not on PATH until 'pipx ensurepath' runs *and* a new shell starts.
    # Put it on the process PATH so the very next pipx call in this run resolves.
    param([string]$PythonCmd)
    try {
        $userBase = "$(& $PythonCmd -m site --user-base 2>$null | Select-Object -First 1)".Trim()
    } catch {
        return $null
    }
    if (-not $userBase) { return $null }
    $scripts = Join-Path $userBase 'Scripts'
    if ((Test-Path $scripts) -and $env:Path -notlike "*$scripts*") {
        $env:Path = "$scripts;$env:Path"
    }
    return $scripts
}

function Get-PipxPythonArgs {
    # pipx needs a *resolvable* interpreter. 'python3.14' is a real command on Linux
    # but almost never on Windows, where the py launcher answers '-3.14' instead and
    # pipx accepts the bare version string. Fall back to the default interpreter.
    if (Get-Command python3.14 -ErrorAction SilentlyContinue) {
        return @('--python', 'python3.14')
    }
    if (Get-Command py -ErrorAction SilentlyContinue) {
        try {
            & py -3.14 --version 2>&1 | Out-Null
            if ($LASTEXITCODE -eq 0) { return @('--python', '3.14') }
        } catch { }
    }
    Write-Warn2 "Python 3.14 not found - installing headroom against the default interpreter."
    return @()
}

# --- claude-mem settings.json patch ------------------------------------------

function Set-ClaudeMemWorkerPort {
    # claude-mem's own bootstrap writes CLAUDE_MEM_PROVIDER but not the worker port,
    # and the worker silently picks a different port without it. Patch the text rather
    # than round-tripping through ConvertTo-Json, which reformats the entire file.
    param([string]$Port = '37790')

    $settings = Join-Path (Get-ClaudeConfigRoot) 'settings.json'
    if (-not (Test-Path $settings)) {
        Write-Warn2 "no settings.json at $settings yet - claude-mem writes it on first run; re-run this script afterwards to set CLAUDE_MEM_WORKER_PORT."
        return
    }

    $raw = Get-Content -Path $settings -Raw -Encoding UTF8
    if ($raw -match '"CLAUDE_MEM_WORKER_PORT"') {
        Write-Skip "CLAUDE_MEM_WORKER_PORT already present in $settings"
        return
    }

    $backup = "$settings.bak"
    Copy-Item -Path $settings -Destination $backup -Force

    $updated = $null
    $providerLine = '(?m)^([ \t]*)"CLAUDE_MEM_PROVIDER"[ \t]*:[ \t]*"[^"]*"[ \t]*(,?)[ \t]*\r?$'
    if ($raw -match $providerLine) {
        $updated = [regex]::Replace($raw, $providerLine, {
            param($m)
            $indent = $m.Groups[1].Value
            $line = $m.Value.TrimEnd()
            if ($m.Groups[2].Value -eq ',') {
                # Provider already has a trailing comma, so the new key needs one too.
                "$line`r`n$indent`"CLAUDE_MEM_WORKER_PORT`": `"$Port`","
            } else {
                # Provider was the last key in its object - give it the comma instead.
                "$line,`r`n$indent`"CLAUDE_MEM_WORKER_PORT`": `"$Port`""
            }
        }, 1)
    } else {
        # No provider key to anchor to. Fall back to a structural edit of the env block,
        # writing both keys so the file ends up in the documented shape either way.
        try {
            $json = $raw | ConvertFrom-Json
        } catch {
            Write-Warn2 "could not parse $settings as JSON ($($_.Exception.Message)) - left it untouched. Add `"CLAUDE_MEM_WORKER_PORT`": `"$Port`" by hand."
            Remove-Item $backup -Force -ErrorAction SilentlyContinue
            return
        }
        if (-not $json.PSObject.Properties['env']) {
            $json | Add-Member -NotePropertyName 'env' -NotePropertyValue ([pscustomobject]@{})
        }
        if (-not $json.env.PSObject.Properties['CLAUDE_MEM_PROVIDER']) {
            $json.env | Add-Member -NotePropertyName 'CLAUDE_MEM_PROVIDER' -NotePropertyValue 'claude' -Force
        }
        $json.env | Add-Member -NotePropertyName 'CLAUDE_MEM_WORKER_PORT' -NotePropertyValue $Port -Force
        $updated = $json | ConvertTo-Json -Depth 100
        Write-Warn2 "CLAUDE_MEM_PROVIDER was not in $settings - rewrote the file to add the env block (formatting may change; backup at $backup)."
    }

    # Never leave a half-written settings.json behind: validate, then restore on failure.
    try {
        $updated | ConvertFrom-Json | Out-Null
    } catch {
        Write-Warn2 "the patched settings.json did not parse ($($_.Exception.Message)) - restoring $backup."
        Copy-Item -Path $backup -Destination $settings -Force
        return
    }

    Set-Content -Path $settings -Value $updated -Encoding UTF8 -NoNewline
    $script:Summary.Installed++
    Write-Ok "set CLAUDE_MEM_WORKER_PORT=$Port in $settings (backup: $backup)"
}

# --- Selection ----------------------------------------------------------------

$script:IsElevated = Test-Admin

Select-InstallItems
Show-Selection

$chosenCount = @($script:Catalog | Where-Object { Test-Selected $_.Key }).Count
if ($chosenCount -eq 0) {
    Write-Host "`nNothing to do." -ForegroundColor Yellow
    return
}

$script:HeadroomModeChoice = if (Test-Selected 'headroom') { Select-HeadroomMode } else { 'skip' }

if ((Test-Selected 'prereqs') -and -not $script:IsElevated) {
    Write-Step "Not running as Administrator"
    Write-Warn2 "Skipping Chocolatey and Chocolatey packages (git/awscli/nodejs/python)."
    Write-Warn2 "Re-run from an elevated prompt to install those. Every other selected item still runs."
}

# --- 1. Chocolatey + packages -------------------------------------------------
if ((Test-Selected 'prereqs') -and $script:IsElevated) {
    Invoke-Step "Install Chocolatey package manager" {
        if (Get-Command choco -ErrorAction SilentlyContinue) {
            Write-Skip "Chocolatey already installed ($(choco --version))"
            return
        }
        Set-ExecutionPolicy Bypass -Scope Process -Force
        [System.Net.ServicePointManager]::SecurityProtocol = [System.Net.ServicePointManager]::SecurityProtocol -bor 3072
        Invoke-Expression ((New-Object System.Net.WebClient).DownloadString('https://community.chocolatey.org/install.ps1'))
        Sync-SessionEnvironment
        $script:Summary.Installed++
        Write-Ok "Chocolatey installed"
    }

    $chocoPackages = @('git', 'awscli', 'nodejs', 'python')
    $packageProbe = @{ git = 'git'; awscli = 'aws'; nodejs = 'npm'; python = 'python' }
    foreach ($pkg in $chocoPackages) {
        $probe = $packageProbe[$pkg]
        Invoke-Step "Chocolatey package: $pkg" {
            $state = Test-ChocoPackageInstalled -Package $pkg -Probe $probe
            if ($state.Present) {
                Write-Skip "$pkg already installed - $($state.How)"
                return
            }
            choco install $pkg -y --no-progress
            # Refresh before the next package so this session picks up the new PATH
            # entries and vars - git especially, since later steps shell out to it.
            Sync-SessionEnvironment
            Get-ChocoInstalled -Refresh | Out-Null
            if ($probe -and -not (Get-Command $probe -ErrorAction SilentlyContinue)) {
                Write-Warn2 "$pkg installed but '$probe' is still not resolvable in this session - you may need a new shell."
            } else {
                Write-Ok "$pkg installed ('$probe' resolved)"
            }
            $script:Summary.Installed++
        }
    }
}

# --- 2. Claude Code CLI ------------------------------------------------------
if (Test-Selected 'cli') {
    Invoke-Step "Install Claude Code CLI" {
        Sync-SessionEnvironment
        $existing = Get-Command claude -ErrorAction SilentlyContinue
        if ($existing) {
            $version = try { (claude --version) } catch { 'version unknown' }
            Write-Skip "claude already installed at $($existing.Source) ($version)"
            return
        }
        if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
            throw "npm not found on PATH after installing nodejs - open a new shell and re-run this script."
        }
        npm install -g @anthropic-ai/claude-code
        Sync-SessionEnvironment
        $script:Summary.Installed++
    }

    Invoke-Step "Export Claude Code CLI path to PATH" {
        $npmPrefix = (npm config get prefix).Trim()
        if (-not $npmPrefix) {
            throw "Could not resolve npm global prefix."
        }
        $userPath = [Environment]::GetEnvironmentVariable('Path', 'User')
        if ($userPath -notlike "*$npmPrefix*") {
            $newPath = if ([string]::IsNullOrEmpty($userPath)) { $npmPrefix } else { "$userPath;$npmPrefix" }
            [Environment]::SetEnvironmentVariable('Path', $newPath, 'User')
            Write-Ok "Added '$npmPrefix' to the User PATH (persists across sessions)."
        } else {
            Write-Skip "'$npmPrefix' is already on the User PATH."
        }
        [Environment]::SetEnvironmentVariable('CLAUDE_CODE_HOME', $npmPrefix, 'User')
        Sync-SessionEnvironment

        $claudeCmd = Get-Command claude -ErrorAction SilentlyContinue
        if ($claudeCmd) {
            Write-Ok "claude resolved at $($claudeCmd.Source)"
        } else {
            Write-Warn2 "claude not found on PATH in this session - open a new shell for the PATH change to take effect."
        }
    }
}

# Everything from here to the MCP servers needs the claude CLI on PATH.
$claudeItems = @('own-skills', 'team', 'find-skills', 'community', 'claude-code-setup', 'claude-mem', 'gsd', 'voltagent')
$needsClaude = @($claudeItems | Where-Object { Test-Selected $_ }).Count -gt 0

if ($needsClaude -and -not (Test-ClaudeAvailable)) {
    Write-Step "Skipping marketplace/plugin items"
    Write-Warn2 "claude is not on PATH in this session - open a new shell and re-run to install them."
    foreach ($key in $claudeItems) { $script:Selected.Remove($key) }
}

# --- 3. This repo's own marketplace and skills -------------------------------
if (Test-Selected 'own-skills') {
    Invoke-Step "Add this repo as a Claude Code marketplace" {
        Add-ClaudeMarketplace -Source 'mbadali25/useful-claude-add-ons' -Name 'useful-claude-add-ons'
    }

    # Keep in sync with .claude-plugin/marketplace.json.
    $ownPlugins = @(
        'aws-opensearch',
        'bitbucket',
        'checkpoint-email',
        'cisco-meraki',
        'claude-code-defaults',
        'cloudflare',
        'drata',
        'i-have-adhd',
        'infra-work-ticketing',
        'intune-graph',
        'mermaid-svg-bitbucket',
        'repo-docs',
        'shipstation',
        'sophos-central',
        'terraform-docs-readme',
        'visio-diagrams',
        'wazuh-onprem',
        'web-testing-playwright',
        'work-log-reporter'
    )
    foreach ($plugin in $ownPlugins) {
        Invoke-Step "Plugin: $plugin@useful-claude-add-ons" {
            Install-ClaudePlugin "$plugin@useful-claude-add-ons"
        }
    }
}

# --- 4. Team marketplaces and plugins ----------------------------------------
if (Test-Selected 'team') {
    $teamMarketplaces = @(
        @{ Source = 'obra/superpowers-marketplace';        Name = 'superpowers-marketplace' },
        @{ Source = 'anthropics/claude-code';              Name = 'claude-code-plugins' },
        @{ Source = 'lexiaoyao20/excalidraw-generator';    Name = 'excalidraw-generator' }
    )
    foreach ($mp in $teamMarketplaces) {
        Invoke-Step "Marketplace: $($mp.Source)" {
            Add-ClaudeMarketplace -Source $mp.Source -Name $mp.Name
        }
    }

    $teamPlugins = @(
        'superpowers@superpowers-marketplace',
        'frontend-design@claude-code-plugins',
        'excalidraw-generator@excalidraw-generator'
    )
    foreach ($spec in $teamPlugins) {
        Invoke-Step "Plugin: $spec" {
            Install-ClaudePlugin $spec
        }
    }
}

# --- 5. find-skills ----------------------------------------------------------
if (Test-Selected 'find-skills') {
    Invoke-Step "Skill: find-skills (vercel-labs/skills)" {
        # find-skills is installed by the 'skills' CLI as a user-level skill, not as a
        # Claude Code plugin, so it is detected on disk rather than via 'claude plugin list'.
        $findSkillsDir = Join-Path (Get-ClaudeSkillsDir) 'find-skills'
        $present = Test-UserSkillInstalled 'find-skills'
        if ($present -and $NoUpdate) {
            Write-Skip "find-skills already installed at $findSkillsDir (-NoUpdate set)"
            return
        }
        npx -y skills add vercel-labs/skills --skill find-skills --agent claude-code
        if (-not (Test-UserSkillInstalled 'find-skills')) {
            throw "the installer finished but '$findSkillsDir\SKILL.md' was not created - see the output above."
        }
        if ($present) {
            Write-Ok "find-skills re-installed (now current)"
        } else {
            $script:Summary.Installed++
            Write-Ok "installed find-skills to $findSkillsDir"
        }
    }
}

# --- 6. Community marketplaces (from claudepluginhub.com) --------------------
# Installed with native 'claude plugin' commands. Source repo -> marketplace name
# is *not* mechanical: fcakyon/claude-codex-settings publishes itself as
# 'claude-settings'. Each Name below is the "name" field in that repo's own
# .claude-plugin/marketplace.json, which is what 'plugin@marketplace' must match.
if (Test-Selected 'community') {
    $communityMarketplaces = @(
        @{ Source = 'anthropics/claude-plugins-official'; Name = 'claude-plugins-official' },
        @{ Source = 'vercel-labs/agent-browser';          Name = 'agent-browser' },
        @{ Source = 'fcakyon/claude-codex-settings';      Name = 'claude-settings' },
        @{ Source = 'hugohe3/ppt-master';                 Name = 'ppt-master' }
    )
    foreach ($mp in $communityMarketplaces) {
        Invoke-Step "Marketplace: $($mp.Source)" {
            Add-ClaudeMarketplace -Source $mp.Source -Name $mp.Name
        }
    }

    $communityPlugins = @(
        'adhd-output-style@claude-settings',
        'azure-tools@claude-settings',
        'anthropic-office-skills@claude-settings',
        'agent-browser@agent-browser',
        'ppt-master@ppt-master'
    )
    foreach ($spec in $communityPlugins) {
        Invoke-Step "Plugin: $spec" { Install-ClaudePlugin $spec }
    }
}

# --- 7. claude-code-setup ----------------------------------------------------
# Ships inside anthropics/claude-plugins-official, which the community item also
# registers - Add-ClaudeMarketplace is a no-op when it is already there, so this
# item works whether or not item 6 was selected.
if (Test-Selected 'claude-code-setup') {
    Invoke-Step "Marketplace: anthropics/claude-plugins-official" {
        Add-ClaudeMarketplace -Source 'anthropics/claude-plugins-official' -Name 'claude-plugins-official'
    }
    Invoke-Step "Plugin: claude-code-setup@claude-plugins-official" {
        Install-ClaudePlugin 'claude-code-setup@claude-plugins-official'
    }
}

# --- 8. task-observer --------------------------------------------------------
if (Test-Selected 'task-observer') {
    Invoke-Step "Skill: task-observer (rebelytics/one-skill-to-rule-them-all)" {
        # This repo publishes no marketplace.json, so there is nothing for
        # 'claude plugin install' to consume - it is a plain skill directory.
        # SKILL.md and references/ are the whole skill; the README, USER-GUIDE and
        # two 1.5 MB PNGs in the repo are not part of it and are deliberately not copied.
        $dest = Join-Path (Get-ClaudeSkillsDir) 'task-observer'
        $present = Test-UserSkillInstalled 'task-observer'
        if ($present -and $NoUpdate) {
            Write-Skip "task-observer already installed at $dest (-NoUpdate set)"
            return
        }
        if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
            throw "git not found on PATH - select the prerequisites item (or install git) and re-run."
        }
        $tmp = Join-Path ([IO.Path]::GetTempPath()) ("task-observer-" + [guid]::NewGuid().ToString('N'))
        try {
            git clone --depth 1 --quiet https://github.com/rebelytics/one-skill-to-rule-them-all.git $tmp
            if (-not (Test-Path (Join-Path $tmp 'SKILL.md'))) {
                throw "clone succeeded but SKILL.md was not found in $tmp - the upstream layout may have changed."
            }
            New-Item -ItemType Directory -Force -Path $dest | Out-Null
            Copy-Item -Path (Join-Path $tmp 'SKILL.md') -Destination $dest -Force
            Copy-Item -Path (Join-Path $tmp 'references') -Destination $dest -Recurse -Force
        } finally {
            if (Test-Path $tmp) { Remove-Item -Path $tmp -Recurse -Force -ErrorAction SilentlyContinue }
        }
        if ($present) {
            Write-Ok "task-observer re-installed (now current) at $dest"
        } else {
            $script:Summary.Installed++
            Write-Ok "installed task-observer to $dest"
        }
    }
}

# --- 9. claude-mem -----------------------------------------------------------
if (Test-Selected 'claude-mem') {
    # claude-mem supports the plugin-marketplace path as a first-class alternative to
    # its 'npx claude-mem install' bootstrapper (see its README) - the plugin's own
    # hooks handle worker/dependency setup on first run.
    Invoke-Step "Marketplace: thedotmack/claude-mem" {
        Add-ClaudeMarketplace -Source 'thedotmack/claude-mem' -Name 'thedotmack'
    }
    Invoke-Step "Plugin: claude-mem@thedotmack" {
        Install-ClaudePlugin 'claude-mem@thedotmack'
    }
    Invoke-Step "Configure claude-mem worker port" {
        Set-ClaudeMemWorkerPort -Port '37790'
    }
}

# --- 10. GSD -----------------------------------------------------------------
if (Test-Selected 'gsd') {
    Invoke-Step "Install GSD core" {
        $gsdState = Join-Path (Get-ClaudeConfigRoot) 'gsd-install-state.json'
        if ((Test-Path $gsdState) -and $NoUpdate) {
            Write-Skip "GSD already installed ($gsdState present; -NoUpdate set)"
            return
        }
        if (Test-Path $gsdState) {
            Write-Ok "GSD already installed - running the installer again to pick up updates"
        }
        npx -y @opengsd/gsd-core@latest
        if (-not (Test-Path $gsdState)) { $script:Summary.Installed++ }
    }
}

# --- 11. VoltAgent subagents -------------------------------------------------
# The repo publishes itself as the 'voltagent-subagents' marketplace, with its
# 154 subagents split across ten category plugins. Installing them as plugins
# replaces the old 'git clone + bash install-agents.sh' path, which needed Git
# Bash on Windows (and failed outright when the script ran non-elevated, since
# Chocolatey - and therefore git - was skipped).
if (Test-Selected 'voltagent') {
    Invoke-Step "Marketplace: VoltAgent/awesome-claude-code-subagents" {
        Add-ClaudeMarketplace -Source 'VoltAgent/awesome-claude-code-subagents' -Name 'voltagent-subagents'
    }

    $voltAgentPlugins = @(
        'voltagent-core-dev',
        'voltagent-lang',
        'voltagent-infra',
        'voltagent-qa-sec',
        'voltagent-data-ai',
        'voltagent-dev-exp',
        'voltagent-domains',
        'voltagent-biz',
        'voltagent-meta',
        'voltagent-research'
    )
    foreach ($plugin in $voltAgentPlugins) {
        Invoke-Step "Plugin: $plugin@voltagent-subagents" {
            Install-ClaudePlugin "$plugin@voltagent-subagents"
        }
    }
}

# --- 12/13. Optional MCP servers ---------------------------------------------
if (Test-Selected 'aws-mcp') {
    Invoke-Step "Install AWS MCP server" {
        if (-not (Get-Command uv -ErrorAction SilentlyContinue) -and -not (Get-Command uvx -ErrorAction SilentlyContinue)) {
            if (-not (Get-Command pip -ErrorAction SilentlyContinue)) {
                throw "pip not found - install Python first (choco install python), then re-run to install uv."
            }
            pip install --user uv
            Sync-SessionEnvironment
        }
        if (-not (Test-ClaudeAvailable)) {
            throw "claude not found on PATH in this session - open a new shell and re-run this script."
        }
        claude mcp add aws-api -- uvx awslabs.aws-api-mcp-server@latest
        Write-Ok "Added aws-api MCP server. Make sure AWS credentials are configured (aws configure)."
    }
}

if (Test-Selected 'azure-mcp') {
    Invoke-Step "Install Azure MCP server" {
        if (-not (Test-ClaudeAvailable)) {
            throw "claude not found on PATH in this session - open a new shell and re-run this script."
        }
        claude mcp add azure -- npx -y '@azure/mcp@latest' server start
        Write-Ok "Added azure MCP server. Make sure you have run 'az login' before using it."
    }
}

# --- 14. Headroom ------------------------------------------------------------
if (Test-Selected 'headroom') {
    Invoke-Step "Install pipx (required for headroom)" {
        if (Get-Command pipx -ErrorAction SilentlyContinue) {
            Write-Skip "pipx already installed ($((Get-Command pipx).Source))"
            return
        }
        $py = Get-PythonLauncher
        if (-not $py) {
            throw "no Python launcher found ('py'/'python'/'python3') - select the prerequisites item (or install Python) and re-run."
        }
        & $py -m pip install --user pipx
        if ($LASTEXITCODE -ne 0) { throw "'$py -m pip install --user pipx' failed - see the output above." }
        Add-UserScriptsToPath -PythonCmd $py | Out-Null
        # ensurepath writes the persistent User PATH entries (per-user Scripts and
        # ~\.local\bin); Sync-SessionEnvironment then pulls them into this session.
        & $py -m pipx ensurepath
        Sync-SessionEnvironment
        Add-UserScriptsToPath -PythonCmd $py | Out-Null
        $pipxBin = Join-Path $env:USERPROFILE '.local\bin'
        if ((Test-Path $pipxBin) -and $env:Path -notlike "*$pipxBin*") { $env:Path = "$pipxBin;$env:Path" }

        if (Get-Command pipx -ErrorAction SilentlyContinue) {
            $script:Summary.Installed++
            Write-Ok "pipx installed at $((Get-Command pipx).Source)"
        } else {
            throw "pipx installed but is still not resolvable in this session - open a new shell and re-run."
        }
    }

    Invoke-Step "Install headroom-ai" {
        if (Get-Command headroom -ErrorAction SilentlyContinue) {
            $ver = try { (headroom --version) } catch { 'version unknown' }
            Write-Skip "headroom already installed ($ver)"
            return
        }
        $pipxArgs = @('install') + (Get-PipxPythonArgs) + @('headroom-ai[all]')
        & pipx @pipxArgs
        if ($LASTEXITCODE -ne 0) {
            Write-Warn2 "pipx install failed - falling back to 'npm install -g headroom-ai'."
            npm install -g headroom-ai
            if ($LASTEXITCODE -ne 0) { throw "both the pipx and npm installs of headroom failed." }
        }
        Sync-SessionEnvironment
        $pipxBin = Join-Path $env:USERPROFILE '.local\bin'
        if ((Test-Path $pipxBin) -and $env:Path -notlike "*$pipxBin*") { $env:Path = "$pipxBin;$env:Path" }
        if (-not (Get-Command headroom -ErrorAction SilentlyContinue)) {
            throw "headroom installed but is still not resolvable in this session - open a new shell and re-run."
        }
        $script:Summary.Installed++
        Write-Ok "headroom installed at $((Get-Command headroom).Source)"
    }

    Invoke-Step "Configure headroom ($script:HeadroomModeChoice mode)" {
        if (-not (Get-Command headroom -ErrorAction SilentlyContinue)) {
            throw "headroom is not on PATH - open a new shell and run the mode command by hand."
        }
        # Only 'deploy' is safe to run here. 'wrap' launches the agent and 'proxy'
        # blocks in the foreground serving requests, so both would hang the install.
        switch ($script:HeadroomModeChoice) {
            'deploy'  { headroom deploy; Write-Ok "ran 'headroom deploy'" }
            'wrap'    { Write-Ok "wrap mode selected - start your agent with: headroom wrap claude" }
            'proxy'   { Write-Ok "proxy mode selected - start the proxy with: headroom proxy --port 8787" }
            'library' { Write-Ok "library mode selected - use 'from headroom import compress' in your code" }
            default   { Write-Skip "headroom mode configuration (skip selected)" }
        }
    }

    Invoke-Step "Verify headroom (doctor + perf)" {
        if (-not (Get-Command headroom -ErrorAction SilentlyContinue)) {
            throw "headroom is not on PATH - open a new shell and run 'headroom doctor'."
        }
        headroom doctor
        headroom perf
        Write-Ok "live savings dashboard: headroom dashboard (needs the proxy running)"
    }
}

# --- Summary -----------------------------------------------------------------
Write-Host ""
Write-Host ("Installed: {0}   Updated: {1}   Already present: {2}" -f `
    $script:Summary.Installed, $script:Summary.Updated, $script:Summary.Skipped) -ForegroundColor Cyan
if ($script:FailedSteps.Count -eq 0) {
    Write-Host "All steps completed. Open a new shell if 'claude' is not yet recognized." -ForegroundColor Green
} else {
    Write-Host "Completed with $($script:FailedSteps.Count) failed step(s):" -ForegroundColor Yellow
    $script:FailedSteps | ForEach-Object { Write-Host "  - $_" -ForegroundColor Yellow }
    Write-Host "Re-run this script after resolving the above; earlier successful steps are safe to repeat." -ForegroundColor Yellow
}

#Requires -Version 5.1
<#
Bootstraps a Windows machine for this repo's skills: Chocolatey, git/awscli/nodejs/python,
the Claude Code CLI itself (with its path exported to the user PATH), and the team's
standard Claude Code plugin marketplaces. Idempotent - safe to re-run.

Everything is detected before it is installed:
  * Chocolatey packages   - skipped when the package is already present (or its
                            command already resolves, e.g. git installed outside choco)
  * Marketplaces          - skipped when already registered (matched by name or repo)
  * Plugins               - skipped when already installed; optionally updated
  * ClaudePluginHub items - same detection, since they register through Claude Code

Run from an elevated (Administrator) PowerShell prompt for the full setup:
    .\scripts\install-prerequisites.ps1

If run from a non-elevated prompt, Chocolatey and the Chocolatey packages
(git/awscli/nodejs/python) are skipped - only the Claude Code CLI check,
marketplace registration, and plugin bootstrap steps run.

Common switches:
    -NonInteractive     accept the default answer for every prompt (CI/unattended)
    -NoUpdate           never update an already-installed plugin, only report it
    -SkipBootstrap      skip all marketplace/plugin/optional bootstrap steps
#>

[CmdletBinding()]
param(
    [switch]$SkipBootstrap,   # skip marketplace/plugin/optional bootstrap entirely
    [switch]$NonInteractive,  # take the default for every prompt
    [switch]$NoUpdate,        # don't update already-installed plugins
    [ValidateSet('user', 'project', 'local')]
    [string]$PluginHubScope = 'user'  # claudepluginhub defaults to 'project'; we want machine-wide
)

$ErrorActionPreference = 'Stop'
$script:FailedSteps = @()
$script:Summary = [ordered]@{ Installed = 0; Updated = 0; Skipped = 0 }

function Write-Step { param([string]$Message) Write-Host "`n==> $Message" -ForegroundColor Cyan }
function Write-Ok   { param([string]$Message) Write-Host "    OK: $Message" -ForegroundColor Green }
function Write-Warn2 { param([string]$Message) Write-Host "    WARN: $Message" -ForegroundColor Yellow }
function Write-Skip { param([string]$Message) Write-Host "    SKIP: $Message" -ForegroundColor DarkGray; $script:Summary.Skipped++ }

function Read-YesNo {
    param([string]$Prompt, [string]$Default = 'N')
    $suffix = if ($Default -eq 'Y') { '[Y/n]' } else { '[y/N]' }
    if ($NonInteractive) {
        Write-Host "$Prompt $suffix -> $Default (non-interactive)" -ForegroundColor DarkGray
        return $Default -eq 'Y'
    }
    $answer = Read-Host "$Prompt $suffix"
    if ([string]::IsNullOrWhiteSpace($answer)) { $answer = $Default }
    return $answer -match '^(?i)y(es)?$'
}

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

function Resolve-GitRoot {
    # Find Git for Windows' install root so we can wire up bash. Try, in order:
    # the var Chocolatey's git package sets, the location of git.exe on PATH, then
    # the usual install locations. A candidate only counts if bin\bash.exe is under it.
    if ($env:GIT_INSTALL_ROOT -and (Test-Path (Join-Path $env:GIT_INSTALL_ROOT 'bin\bash.exe'))) {
        return $env:GIT_INSTALL_ROOT
    }
    $gitCmd = Get-Command git.exe -ErrorAction SilentlyContinue
    if ($gitCmd) {
        # git.exe lives in <root>\cmd or <root>\bin
        $candidate = Split-Path (Split-Path $gitCmd.Source -Parent) -Parent
        if (Test-Path (Join-Path $candidate 'bin\bash.exe')) { return $candidate }
    }
    foreach ($candidate in @("$env:ProgramFiles\Git", "${env:ProgramFiles(x86)}\Git", "$env:LOCALAPPDATA\Programs\Git")) {
        if ($candidate -and (Test-Path (Join-Path $candidate 'bin\bash.exe'))) { return $candidate }
    }
    return $null
}

function Register-GitBash {
    # Make 'bash' resolvable in this session and in future ones. Two separate things:
    #   <root>\bin\bash.exe  - the real shell; this is what scripts must be run with,
    #                          because git-bash.exe is a GUI launcher that opens its own
    #                          window, detaches, and returns before the script finishes.
    #   <root>\git-bash.exe  - the interactive launcher; recorded as GIT_BASH for anything
    #                          that wants to pop a terminal.
    # Returns the path to the real bash.exe, or $null if Git isn't installed.
    $gitRoot = Resolve-GitRoot
    if (-not $gitRoot) { return $null }

    $bashExe = Join-Path $gitRoot 'bin\bash.exe'
    if (-not (Test-Path $bashExe)) { return $null }
    $binDir = Join-Path $gitRoot 'bin'

    $userPath = [Environment]::GetEnvironmentVariable('Path', 'User')
    if ($userPath -notlike "*$binDir*") {
        $newPath = if ([string]::IsNullOrEmpty($userPath)) { $binDir } else { "$userPath;$binDir" }
        [Environment]::SetEnvironmentVariable('Path', $newPath, 'User')
        Write-Ok "Added '$binDir' to the User PATH so 'bash' resolves (persists across sessions)."
    }

    [Environment]::SetEnvironmentVariable('GIT_INSTALL_ROOT', $gitRoot, 'User')
    $gitBashLauncher = Join-Path $gitRoot 'git-bash.exe'
    if (Test-Path $gitBashLauncher) {
        [Environment]::SetEnvironmentVariable('GIT_BASH', $gitBashLauncher, 'User')
    }

    # Pick up the PATH/GIT_* entries just written, so 'bash' works below without a new shell.
    Sync-SessionEnvironment
    return $bashExe
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

function Test-PluginInstalled {
    param([string]$Name)
    return (Get-ClaudePlugins).ContainsKey($Name)
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
    claude plugin marketplace add $Source
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
    claude plugin install $Spec
    Get-ClaudePlugins -Refresh | Out-Null
    $script:Summary.Installed++
    Write-Ok "installed plugin '$Spec'"
}

function Invoke-PluginHub {
    # claudepluginhub registers through Claude Code, so the same marketplace/plugin
    # detection applies. Its default scope is 'project'; we pass an explicit scope so
    # a machine bootstrap lands where the rest of this script puts things.
    param([string]$Repo, [string]$Plugin)
    if ($Plugin) {
        if (Test-PluginInstalled $Plugin) {
            $existing = (Get-ClaudePlugins)[$Plugin]
            if ($NoUpdate) {
                Write-Skip "plugin '$Plugin' already installed ($($existing.Id))"
                return
            }
            $before = $existing.Version
            claude plugin update $Plugin | Out-Null
            $after = (Get-ClaudePlugins -Refresh)[$Plugin].Version
            if ($after -ne $before) {
                $script:Summary.Updated++
                Write-Ok "plugin '$Plugin' updated $before -> $after"
            } else {
                Write-Skip "plugin '$Plugin' already current (version $after)"
            }
            return
        }
        npx -y claudepluginhub $Repo --plugin $Plugin --yes --scope $PluginHubScope
        Get-ClaudePlugins -Refresh | Out-Null
        $script:Summary.Installed++
        Write-Ok "installed '$Plugin' from $Repo"
    } else {
        if (Test-MarketplaceInstalled $Repo) {
            Write-Skip "marketplace '$Repo' already registered"
            return
        }
        npx -y claudepluginhub $Repo --yes --scope $PluginHubScope
        Get-ClaudeMarketplaces -Refresh | Out-Null
        $script:Summary.Installed++
        Write-Ok "registered '$Repo'"
    }
}

$script:IsElevated = Test-Admin

if (-not $script:IsElevated) {
    Write-Step "Not running as Administrator"
    Write-Warn2 "Skipping Chocolatey and Chocolatey packages (git/awscli/nodejs/python)."
    Write-Warn2 "Re-run from an elevated prompt to install those. Continuing with Claude Code CLI, marketplaces, and plugins."
}

# --- 1. Chocolatey -----------------------------------------------------------
if ($script:IsElevated) {
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

    # --- 2. Chocolatey packages ---------------------------------------------
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

# --- 3. Claude Code CLI ------------------------------------------------------
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

if ($SkipBootstrap) {
    Write-Step "Skipping all marketplace/plugin bootstrap (-SkipBootstrap)"
} elseif (-not (Test-ClaudeAvailable)) {
    Write-Step "Skipping marketplace/plugin bootstrap"
    Write-Warn2 "claude is not on PATH in this session - open a new shell and re-run to install marketplaces and plugins."
} else {

    # --- 4. This repo's own marketplace and skills ---------------------------
    Invoke-Step "Add this repo as a Claude Code marketplace" {
        Add-ClaudeMarketplace -Source 'mbadali25/useful-claude-add-ons' -Name 'useful-claude-add-ons'
    }

    # Keep in sync with .claude-plugin/marketplace.json.
    $ownPlugins = @(
        'aws-opensearch',
        'bitbucket',
        'checkpoint-email',
        'cisco-meraki',
        'cloudflare',
        'drata',
        'i-have-adhd',
        'infra-work-ticketing',
        'intune-graph',
        'mermaid-svg-bitbucket',
        'repo-docs',
        'shipstation',
        'sophos-central',
        'wazuh-onprem',
        'web-testing-playwright',
        'work-log-reporter'
    )
    foreach ($plugin in $ownPlugins) {
        Invoke-Step "Plugin: $plugin@useful-claude-add-ons" {
            Install-ClaudePlugin "$plugin@useful-claude-add-ons"
        }
    }

    # --- 5. Team marketplaces and plugins ------------------------------------
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

    Invoke-Step "Skill: find-skills (vercel-labs/skills)" {
        npx -y skills add vercel-labs/skills --skill find-skills --agent claude-code
    }

    # --- 6. ClaudePluginHub --------------------------------------------------
    if (Read-YesNo "Install the ClaudePluginHub marketplaces and plugins?" 'Y') {
        $hubMarketplaces = @(
            'anthropics/claude-plugins-official',
            'obra/superpowers-marketplace',
            'aiskillstore/marketplace',
            'vercel-labs/agent-browser',
            'fcakyon/claude-codex-settings'
        )
        foreach ($repo in $hubMarketplaces) {
            Invoke-Step "ClaudePluginHub: $repo" { Invoke-PluginHub -Repo $repo }
        }

        $hubPlugins = @(
            @{ Repo = 'fcakyon/claude-codex-settings'; Plugin = 'adhd-output-style' },
            @{ Repo = 'fcakyon/claude-codex-settings'; Plugin = 'agent-browser' },
            @{ Repo = 'fcakyon/claude-codex-settings'; Plugin = 'azure-tools' },
            @{ Repo = 'hugohe3/ppt-master';            Plugin = 'ppt-master' },
            @{ Repo = 'aiskillstore/marketplace';      Plugin = 'xlsx' },
            @{ Repo = 'aiskillstore/marketplace';      Plugin = 'mcp-integration' }
        )
        foreach ($hp in $hubPlugins) {
            Invoke-Step "ClaudePluginHub: $($hp.Plugin) from $($hp.Repo)" {
                Invoke-PluginHub -Repo $hp.Repo -Plugin $hp.Plugin
            }
        }
    } else {
        Write-Skip "ClaudePluginHub marketplaces and plugins"
    }

    # --- 7. Optional tooling -------------------------------------------------
    if (Read-YesNo "Install claude-mem (persistent cross-session memory)?" 'Y') {
        Invoke-Step "Install claude-mem" {
            if ((Test-MarketplaceInstalled 'thedotmack') -or (Test-PluginInstalled 'claude-mem')) {
                Write-Skip "claude-mem already present (marketplace 'thedotmack' or plugin 'claude-mem')"
                if (-not $NoUpdate) { npx -y claude-mem install }
                return
            }
            npx -y claude-mem install
            Get-ClaudeMarketplaces -Refresh | Out-Null
            Get-ClaudePlugins -Refresh | Out-Null
            $script:Summary.Installed++
        }
    } else {
        Write-Skip "claude-mem"
    }

    if (Read-YesNo "Install GSD (@opengsd/gsd-core)?" 'Y') {
        Invoke-Step "Install GSD core" {
            $gsdState = Join-Path $env:USERPROFILE '.claude\gsd-install-state.json'
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
    } else {
        Write-Skip "GSD"
    }

    if (Read-YesNo "Install the VoltAgent awesome-claude-code-subagents collection?" 'Y') {
        Invoke-Step "Clone and install awesome-claude-code-subagents" {
            # Map 'bash' to Git Bash and refresh the environment before using it - a fresh
            # git install puts bash.exe on the registry PATH, not on this process's PATH.
            $bashExe = Register-GitBash
            if (-not $bashExe) {
                $onPath = Get-Command bash -ErrorAction SilentlyContinue
                if ($onPath) {
                    $bashExe = $onPath.Source
                    Write-Warn2 "Git for Windows not located; falling back to 'bash' on PATH ($bashExe)."
                } else {
                    throw "bash (Git Bash) not found - install Git for Windows (choco install git) and re-run, or run this step manually."
                }
            } else {
                Write-Ok "Using Git Bash at $bashExe"
            }
            $repoRoot = 'C:\repos'
            if (-not (Test-Path $repoRoot)) {
                New-Item -ItemType Directory -Path $repoRoot -Force | Out-Null
            }
            $repoDir = Join-Path $repoRoot 'awesome-claude-code-subagents'
            if (Test-Path (Join-Path $repoDir '.git')) {
                if ($NoUpdate) {
                    Write-Skip "already cloned at $repoDir (-NoUpdate set)"
                } else {
                    Write-Ok "Repository already cloned at $repoDir - pulling latest"
                    git -C $repoDir pull --ff-only
                }
            } else {
                git clone https://github.com/VoltAgent/awesome-claude-code-subagents.git $repoDir
                $script:Summary.Installed++
            }
            Push-Location $repoDir
            try {
                & $bashExe install-agents.sh
            } finally {
                Pop-Location
            }
        }
    } else {
        Write-Skip "VoltAgent awesome-claude-code-subagents"
    }
}

# --- 8. Optional MCP servers -------------------------------------------------
if (Read-YesNo "Install the AWS MCP server (awslabs.aws-api-mcp-server) and register it with Claude Code?") {
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

if (Read-YesNo "Install the Azure MCP server (@azure/mcp) and register it with Claude Code?") {
    Invoke-Step "Install Azure MCP server" {
        if (-not (Test-ClaudeAvailable)) {
            throw "claude not found on PATH in this session - open a new shell and re-run this script."
        }
        claude mcp add azure -- npx -y '@azure/mcp@latest' server start
        Write-Ok "Added azure MCP server. Make sure you have run 'az login' before using it."
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

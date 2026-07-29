#Requires -Version 5.1
<#
Bootstraps a Windows machine for this repo's skills: Chocolatey, git/awscli/nodejs/python,
the Claude Code CLI itself (with its path exported to the user PATH), and the team's
standard Claude Code plugin marketplaces. Idempotent - safe to re-run.

Run from an elevated (Administrator) PowerShell prompt for the full setup:
    .\scripts\install-prerequisites.ps1

If run from a non-elevated prompt, Chocolatey and the Chocolatey packages
(git/awscli/nodejs/python) are skipped - only the Claude Code CLI check,
marketplace registration, and plugin bootstrap steps run.
#>

[CmdletBinding()]
param(
    [switch]$SkipBootstrap  # skip claude/npx bootstrap commands (marketplaces, skills add, gsd-core, claude-mem)
)

$ErrorActionPreference = 'Stop'
$script:FailedSteps = @()

function Write-Step { param([string]$Message) Write-Host "`n==> $Message" -ForegroundColor Cyan }
function Write-Ok   { param([string]$Message) Write-Host "    OK: $Message" -ForegroundColor Green }
function Write-Warn2 { param([string]$Message) Write-Host "    WARN: $Message" -ForegroundColor Yellow }

function Read-YesNo {
    param([string]$Prompt, [string]$Default = 'N')
    $suffix = if ($Default -eq 'Y') { '[Y/n]' } else { '[y/N]' }
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

$script:IsElevated = Test-Admin

if (-not $script:IsElevated) {
    Write-Step "Not running as Administrator"
    Write-Warn2 "Skipping Chocolatey and Chocolatey packages (git/awscli/nodejs/python)."
    Write-Warn2 "Re-run from an elevated prompt to install those. Continuing with Claude Code CLI, marketplaces, and plugins."
}

# --- 1. Chocolatey ---------------------------------------------------------
if ($script:IsElevated) {
    Invoke-Step "Install Chocolatey package manager" {
        if (Get-Command choco -ErrorAction SilentlyContinue) {
            Write-Ok "Chocolatey already installed ($(choco --version))"
            return
        }
        Set-ExecutionPolicy Bypass -Scope Process -Force
        [System.Net.ServicePointManager]::SecurityProtocol = [System.Net.ServicePointManager]::SecurityProtocol -bor 3072
        Invoke-Expression ((New-Object System.Net.WebClient).DownloadString('https://community.chocolatey.org/install.ps1'))
        Sync-SessionEnvironment
        Write-Ok "Chocolatey installed"
    }

    # --- 2. Chocolatey packages -----------------------------------------------
    $chocoPackages = @('git', 'awscli', 'nodejs', 'python')
    $packageProbe = @{ git = 'git'; awscli = 'aws'; nodejs = 'npm'; python = 'python' }
    foreach ($pkg in $chocoPackages) {
        Invoke-Step "choco install $pkg" {
            choco install $pkg -y --no-progress
            # Refresh before the next package so this session picks up the new PATH
            # entries and vars - git especially, since later steps shell out to it.
            Sync-SessionEnvironment
            $probe = $packageProbe[$pkg]
            if ($probe -and -not (Get-Command $probe -ErrorAction SilentlyContinue)) {
                Write-Warn2 "$pkg installed but '$probe' is still not resolvable in this session - you may need a new shell."
            } else {
                Write-Ok "$pkg installed ('$probe' resolved)"
            }
        }
    }
}

# --- 3. Claude Code CLI ------------------------------------------------------
Invoke-Step "Install Claude Code CLI" {
    Sync-SessionEnvironment
    $existing = Get-Command claude -ErrorAction SilentlyContinue
    if ($existing) {
        $version = try { (claude --version) } catch { 'version unknown' }
        Write-Ok "claude already installed at $($existing.Source) ($version)"
        return
    }
    if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
        throw "npm not found on PATH after installing nodejs - open a new shell and re-run this script."
    }
    npm install -g @anthropic-ai/claude-code
    Sync-SessionEnvironment
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
        Write-Ok "'$npmPrefix' is already on the User PATH."
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

Invoke-Step "Add this repo as a Claude Code marketplace" {
    if (-not (Get-Command claude -ErrorAction SilentlyContinue)) {
        throw "claude not found on PATH in this session - open a new shell and re-run this script to add the marketplace."
    }
    claude plugin marketplace add mbadali25/useful-claude-add-ons
}

# --- 4. Install all plugins from this repo's marketplace --------------------
$ownPlugins = @(
    'aws-opensearch',
    'bitbucket',
    'checkpoint-email',
    'cloudflare',
    'drata',
    'i-have-adhd',
    'intune-graph',
    'mermaid-svg-bitbucket',
    'sophos-central',
    'wazuh-onprem'
)
foreach ($plugin in $ownPlugins) {
    Invoke-Step "claude plugin install $plugin@useful-claude-add-ons" {
        claude plugin install "$plugin@useful-claude-add-ons"
    }
}

# --- 5. Team plugin/marketplace bootstrap -----------------------------------
if ($SkipBootstrap) {
    Write-Step "Skipping plugin/marketplace bootstrap (-SkipBootstrap)"
} else {
    $bootstrapCommands = @(
        'claude plugin marketplace add obra/superpowers-marketplace',
        'claude plugin install superpowers@superpowers-marketplace',
        'npx -y skills add vercel-labs/skills --skill find-skills --agent claude-code',
        'npx @opengsd/gsd-core@latest',
        'npx claude-mem install',
        'claude plugin marketplace add anthropics/claude-code',
        'claude plugin install frontend-design@claude-code-plugins',
        'claude plugin marketplace add lexiaoyao20/excalidraw-generator',
        'claude plugin install excalidraw-generator@excalidraw-generator',
        'claude plugin marketplace add obra/superpowers-marketplace',
        'claude plugin install superpowers@superpowers-marketplace'
    )
    foreach ($cmd in $bootstrapCommands) {
        Invoke-Step $cmd {
            Invoke-Expression $cmd
        }
    }
}

# --- 6. Optional MCP servers -------------------------------------------------
if (Read-YesNo "Install the AWS MCP server (awslabs.aws-api-mcp-server) and register it with Claude Code?") {
    Invoke-Step "Install AWS MCP server" {
        if (-not (Get-Command uv -ErrorAction SilentlyContinue) -and -not (Get-Command uvx -ErrorAction SilentlyContinue)) {
            if (-not (Get-Command pip -ErrorAction SilentlyContinue)) {
                throw "pip not found - install Python first (choco install python), then re-run to install uv."
            }
            pip install --user uv
            Sync-SessionEnvironment
        }
        if (-not (Get-Command claude -ErrorAction SilentlyContinue)) {
            throw "claude not found on PATH in this session - open a new shell and re-run this script."
        }
        claude mcp add aws-api -- uvx awslabs.aws-api-mcp-server@latest
        Write-Ok "Added aws-api MCP server. Make sure AWS credentials are configured (aws configure)."
    }
}

if (Read-YesNo "Install the Azure MCP server (@azure/mcp) and register it with Claude Code?") {
    Invoke-Step "Install Azure MCP server" {
        if (-not (Get-Command claude -ErrorAction SilentlyContinue)) {
            throw "claude not found on PATH in this session - open a new shell and re-run this script."
        }
        claude mcp add azure -- npx -y '@azure/mcp@latest' server start
        Write-Ok "Added azure MCP server. Make sure you have run 'az login' before using it."
    }
}

# --- 7. Awesome Claude Code Subagents ----------------------------------------
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
        Write-Ok "Repository already cloned at $repoDir - pulling latest"
        git -C $repoDir pull --ff-only
    } else {
        git clone https://github.com/VoltAgent/awesome-claude-code-subagents.git $repoDir
    }
    Push-Location $repoDir
    try {
        & $bashExe install-agents.sh
    } finally {
        Pop-Location
    }
}

# --- Summary -----------------------------------------------------------------
Write-Host ""
if ($script:FailedSteps.Count -eq 0) {
    Write-Host "All steps completed. Open a new shell if 'claude' is not yet recognized." -ForegroundColor Green
} else {
    Write-Host "Completed with $($script:FailedSteps.Count) failed step(s):" -ForegroundColor Yellow
    $script:FailedSteps | ForEach-Object { Write-Host "  - $_" -ForegroundColor Yellow }
    Write-Host "Re-run this script after resolving the above; earlier successful steps are safe to repeat." -ForegroundColor Yellow
}

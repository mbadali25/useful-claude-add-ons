#Requires -Version 5.1
<#
Bootstraps a Windows machine for this repo's skills: Chocolatey, git/awscli/nodejs/python,
the Claude Code CLI itself (with its path exported to the user PATH), and the team's
standard Claude Code plugin marketplaces. Idempotent - safe to re-run.

Run from an elevated (Administrator) PowerShell prompt:
    .\scripts\install-prerequisites.ps1
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

function Test-Admin {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Update-SessionPath {
    # Chocolatey/npm installs update the registry PATH but not this running process.
    # Rebuild $env:Path from Machine + User so later steps in this same script can find new binaries.
    $machine = [Environment]::GetEnvironmentVariable('Path', 'Machine')
    $user = [Environment]::GetEnvironmentVariable('Path', 'User')
    $env:Path = "$machine;$user"
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

if (-not (Test-Admin)) {
    throw "Run this script from an elevated (Administrator) PowerShell prompt - Chocolatey and system-wide PATH changes require it."
}

# --- 1. Chocolatey ---------------------------------------------------------
Invoke-Step "Install Chocolatey package manager" {
    if (Get-Command choco -ErrorAction SilentlyContinue) {
        Write-Ok "Chocolatey already installed ($(choco --version))"
        return
    }
    Set-ExecutionPolicy Bypass -Scope Process -Force
    [System.Net.ServicePointManager]::SecurityProtocol = [System.Net.ServicePointManager]::SecurityProtocol -bor 3072
    Invoke-Expression ((New-Object System.Net.WebClient).DownloadString('https://community.chocolatey.org/install.ps1'))
    Update-SessionPath
    Write-Ok "Chocolatey installed"
}

# --- 2. Chocolatey packages -------------------------------------------------
$chocoPackages = @('git', 'awscli', 'nodejs', 'python')
foreach ($pkg in $chocoPackages) {
    Invoke-Step "choco install $pkg" {
        choco install $pkg -y --no-progress
        Update-SessionPath
    }
}

# --- 3. Claude Code CLI ------------------------------------------------------
Invoke-Step "Install Claude Code CLI" {
    Update-SessionPath
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
    Update-SessionPath
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
    Update-SessionPath

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

# --- 4. Team plugin/marketplace bootstrap -----------------------------------
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
        'claude plugin install superpowers@claude-plugins-official'
    )
    foreach ($cmd in $bootstrapCommands) {
        Invoke-Step $cmd {
            Invoke-Expression $cmd
        }
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

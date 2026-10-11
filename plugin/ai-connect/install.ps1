# AI-Connect installation for Windows (Linux: install.sh)
#
# Usage (or double-click install.cmd for the interactive installation):
#   install.cmd -Client          # Client: venv, config, Claude Code (no service, no admin)
#   install.cmd -Server          # Server: Bridge task + firewall rule + everything the client gets (admin, via UAC)
#   install.cmd -Server -VpnSubnet 10.0.0.0/24  # firewall remote scope, default is Tailscale's 100.64.0.0/10
#   install.cmd -Client -Http    # also the HTTP/SSE task for other MCP clients
#   install.cmd -Update          # Update; detects what is installed
#   install.cmd -Status          # Show status
#   install.cmd -Uninstall       # Uninstall
#
# Config and the Claude Code registration are platform independent and live
# in installer.py; this script does the Windows part: venv, scheduled tasks
# (started at logon, restarted on failure) and the firewall rule. Tasks and
# firewall need administrator rights; the script then restarts itself
# elevated, but the tasks run as the user without elevation.
# ASCII only: Windows PowerShell 5.1 misreads UTF-8 files without a BOM.

param(
    [switch]$Server,
    [switch]$Client,
    [switch]$Http,
    [switch]$Update,
    [switch]$Status,
    [switch]$Uninstall,
    # -Server's firewall rule allows only remote addresses in this range, not
    # the whole Private profile; default is Tailscale's CGNAT range. Set this
    # to your VPN's own subnet if it differs (e.g. WireGuard's 10.0.0.0/24)
    [string]$VpnSubnet = '100.64.0.0/10',
    # Set by Restart-Elevated: keep the elevated window open at the end
    [switch]$Elevated,
    # Set by Restart-Elevated: the account the tasks run as, from before elevation
    [string]$TaskUser
)

$ErrorActionPreference = 'Stop'
# On any error: show it, and keep an elevated window open so it can be read
trap {
    Write-Host "Error: $_" -ForegroundColor Red
    if ($Elevated) { Read-Host 'Press Enter to close this window' | Out-Null }
    exit 1
}
$Repo = $PSScriptRoot
$Python = Join-Path $Repo 'venv\Scripts\python.exe'
# pythonw.exe runs without a console window
$PythonW = Join-Path $Repo 'venv\Scripts\pythonw.exe'
$ConfigFile = Join-Path $HOME '.config\ai-connect\config.yaml'
$BridgeTask = 'AI-Connect Bridge'
$HttpTask = 'AI-Connect MCP HTTP'
$FirewallRule = 'AI-Connect Bridge'
$BridgePort = 9999
$HttpPort = 9998
# Fully qualified (MACHINE\user): a bare name such as "mp" is read by the
# task scheduler as an SDDL abbreviation (MP = an integrity level), not an
# account. Taken before elevation, so it is the user, not the admin who
# confirmed UAC.
if (-not $TaskUser) { $TaskUser = [Security.Principal.WindowsIdentity]::GetCurrent().Name }

function Invoke-Native {
    # Windows PowerShell does not stop on a failing native command by itself
    param([string]$Command, [string[]]$Arguments)
    & $Command @Arguments
    if ($LASTEXITCODE -ne 0) { throw "$Command $($Arguments -join ' ') failed (exit code $LASTEXITCODE)" }
}

function Test-Task([string]$Name) {
    return [bool](Get-ScheduledTask -TaskName $Name -ErrorAction SilentlyContinue)
}

function Test-Admin {
    $Identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    return (New-Object Security.Principal.WindowsPrincipal $Identity).IsInRole(
        [Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Restart-Elevated([string[]]$Switches) {
    # Logon tasks and firewall rules need administrator rights, even for the
    # own user; Windows asks once through UAC, then this script runs again
    Write-Host 'Tasks and firewall need administrator rights; Windows asks for them now...'
    $Arguments = @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', "`"$PSCommandPath`"") + $Switches +
        @('-Elevated', '-TaskUser', "`"$TaskUser`"")
    $Run = Start-Process powershell -Verb RunAs -Wait -PassThru -ArgumentList $Arguments
    exit $Run.ExitCode
}

function Show-Status {
    Write-Host ''
    Write-Host '=== AI-Connect status ===' -ForegroundColor Blue
    foreach ($Task in @($BridgeTask, $HttpTask)) {
        if (Test-Task $Task) {
            Write-Host "  ${Task}: $((Get-ScheduledTask -TaskName $Task).State)"
        }
    }
    $Rule = Get-NetFirewallRule -DisplayName $FirewallRule -ErrorAction SilentlyContinue
    if ($Rule) {
        $Scope = (Get-NetFirewallAddressFilter -AssociatedNetFirewallRule $Rule).RemoteAddress -join ', '
        Write-Host "  Firewall: port $BridgePort open for $Scope"
    }
    if (Test-Path $ConfigFile) {
        Write-Host "  Config: $ConfigFile" -ForegroundColor Green
    } else {
        Write-Host '  Config: missing' -ForegroundColor Red
    }
    Write-Host ''
}

function Install-Task([string]$Name, [string]$Module) {
    $Action = New-ScheduledTaskAction -Execute $PythonW -Argument "-m $Module" -WorkingDirectory $Repo
    $Trigger = New-ScheduledTaskTrigger -AtLogOn -User $TaskUser
    # Runs as the user without elevation, although registered from an elevated shell
    $Principal = New-ScheduledTaskPrincipal -UserId $TaskUser -LogonType Interactive -RunLevel Limited
    $Settings = New-ScheduledTaskSettingsSet -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) `
        -ExecutionTimeLimit ([TimeSpan]::Zero) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
    Register-ScheduledTask -TaskName $Name -Action $Action -Trigger $Trigger -Principal $Principal -Settings $Settings -Force | Out-Null
    Stop-ScheduledTask -TaskName $Name
    Start-ScheduledTask -TaskName $Name
    Write-Host "  $Name running" -ForegroundColor Green
}

function Uninstall-AIConnect {
    # Asked before elevating, so an abort does not close the elevated window unseen
    if (-not $Elevated) {
        $Confirm = Read-Host 'Really uninstall AI-Connect? [y/N]'
        if ($Confirm -notmatch '^[yY]$') { Write-Host 'Aborted.'; exit 0 }
    }
    # Tasks and the firewall rule need administrator rights to remove; a
    # broken task may even be invisible to the user, so any trace counts
    $NeedsAdmin = (Test-Task $BridgeTask) -or (Test-Task $HttpTask) -or
        [bool](Get-NetFirewallRule -DisplayName $FirewallRule -ErrorAction SilentlyContinue)
    if ($NeedsAdmin -and -not (Test-Admin)) {
        Restart-Elevated @('-Uninstall')
    }

    foreach ($Task in @($HttpTask, $BridgeTask)) {
        if (Test-Task $Task) {
            Stop-ScheduledTask -TaskName $Task
            Unregister-ScheduledTask -TaskName $Task -Confirm:$false
            Write-Host "  $Task removed" -ForegroundColor Green
        }
    }
    if (Get-NetFirewallRule -DisplayName $FirewallRule -ErrorAction SilentlyContinue) {
        Remove-NetFirewallRule -DisplayName $FirewallRule
        Write-Host '  Firewall rule removed' -ForegroundColor Green
    }
    if (Test-Path $Python) {
        Invoke-Native $Python @((Join-Path $Repo 'installer.py'), 'unregister')
    }
    $ConfigDir = Split-Path $ConfigFile
    $DeleteConfig = Read-Host "Delete $ConfigDir with everything in it (config, token, logs, message history)? [y/N]"
    if ($DeleteConfig -match '^[yY]$') {
        # One by one: a running Claude Code session keeps its MCP client's
        # log open, and Windows does not delete open files
        $Locked = @()
        foreach ($Item in Get-ChildItem $ConfigDir -Recurse -File) {
            try { Remove-Item $Item.FullName -Force } catch { $Locked += $Item.FullName }
        }
        if ($Locked) {
            Write-Host '  In use, delete after closing Claude Code:' -ForegroundColor Yellow
            $Locked | ForEach-Object { Write-Host "    $_" }
        } else {
            Remove-Item -Recurse -Force $ConfigDir
            Write-Host '  Config deleted' -ForegroundColor Green
        }
    }
    Write-Host ''
    Write-Host "The venv stays; remove it with: Remove-Item -Recurse $(Join-Path $Repo 'venv')"
    if ($Elevated) { Read-Host 'Done. Press Enter to close this window' | Out-Null }
    exit 0
}

if ($Uninstall) { Uninstall-AIConnect }
if ($Status) { Show-Status; exit 0 }

$Mode = ''
if ($Server) { $Mode = 'server' }
if ($Client) { $Mode = 'client' }

# An update keeps what is installed: the tasks tell server and HTTP, the
# config tells a plain client
if ($Update) {
    if (Test-Task $BridgeTask) { $Mode = 'server' } else { $Mode = 'client' }
    if (Test-Task $HttpTask) { $Http = $true }
    if ($Mode -eq 'client' -and -not (Test-Path $ConfigFile)) {
        Write-Host 'No installation found. Install first.' -ForegroundColor Red
        exit 1
    }
}

if (-not $Mode) {
    Write-Host 'Which installation?'
    Write-Host '  1) Client - joins a Bridge running elsewhere'
    Write-Host '  2) Server - this machine runs the Bridge (includes the client)'
    switch (Read-Host 'Choice [1/2]') {
        '1' { $Mode = 'client' }
        '2' { $Mode = 'server' }
        default { Write-Host 'Invalid choice. Aborted.' -ForegroundColor Red; exit 1 }
    }
    if ((Read-Host 'Also the HTTP/SSE task for other MCP clients (VS Code, Cursor, ...)? [y/N]') -match '^[yY]$') {
        $Http = $true
    }
}

if (($Mode -eq 'server' -or $Http) -and -not (Test-Admin)) {
    $Switches = @("-$Mode")
    if ($Http) { $Switches += '-Http' }
    # -VpnSubnet has a default, so it must be forwarded explicitly even when
    # the caller did not pass it -- otherwise the elevated relaunch silently
    # drops whatever value the caller set
    if ($Mode -eq 'server') { $Switches += @('-VpnSubnet', $VpnSubnet) }
    Restart-Elevated $Switches
}

Write-Host ''
Write-Host "=== AI-Connect $Mode installation ===" -ForegroundColor Blue

Write-Host '[1/4] Python venv and dependencies...' -ForegroundColor Yellow
# Python from python.org brings the launcher "py", the Microsoft Store
# version only "python"
if (Get-Command py -ErrorAction SilentlyContinue) {
    $BasePython = @('py', '-3')
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
    $BasePython = @('python')
} else {
    Write-Host 'Python was not found (neither "py" nor "python"). Install Python 3.10 or newer.' -ForegroundColor Red
    exit 1
}
$BaseArgs = @($BasePython | Select-Object -Skip 1)
& $BasePython[0] @BaseArgs -c 'import sys; sys.exit(sys.version_info < (3, 10))'
if ($LASTEXITCODE -ne 0) {
    Write-Host "$($BasePython -join ' ') is not Python 3.10 or newer. Install a current Python." -ForegroundColor Red
    exit 1
}
if (-not (Test-Path $Python)) {
    Invoke-Native $BasePython[0] ($BaseArgs + @('-m', 'venv', (Join-Path $Repo 'venv')))
}
Invoke-Native $Python @('-m', 'pip', 'install', '-q', '--upgrade', 'pip')
Invoke-Native $Python @('-m', 'pip', 'install', '-q', '--upgrade', '-r', (Join-Path $Repo 'requirements.txt'))
Write-Host '  Dependencies up to date' -ForegroundColor Green

Write-Host '[2/4] Configuration...' -ForegroundColor Yellow
Invoke-Native $Python @((Join-Path $Repo 'installer.py'), 'config', "--$Mode")

Write-Host '[3/4] Claude Code...' -ForegroundColor Yellow
Invoke-Native $Python @((Join-Path $Repo 'installer.py'), 'claude')

Write-Host '[4/4] Services...' -ForegroundColor Yellow
if ($Mode -eq 'server') {
    Install-Task $BridgeTask 'server.main'
    if (-not (Get-NetFirewallRule -DisplayName $FirewallRule -ErrorAction SilentlyContinue)) {
        # Scoped to the VPN subnet, not the whole Private profile: anything
        # else on the same LAN/profile must not be able to reach this port
        New-NetFirewallRule -DisplayName $FirewallRule -Direction Inbound -Protocol TCP `
            -LocalPort $BridgePort -RemoteAddress $VpnSubnet -Action Allow -Profile Private | Out-Null
        Write-Host "  Firewall: port $BridgePort open for $VpnSubnet (private networks)" -ForegroundColor Green
    }
}
if ($Http) {
    $Listener = Get-NetTCPConnection -LocalPort $HttpPort -State Listen -ErrorAction SilentlyContinue
    if ($Listener -and -not (Test-Task $HttpTask)) {
        Write-Host "  Port $HttpPort is taken (process $($Listener[0].OwningProcess)); HTTP task not installed" -ForegroundColor Red
    } else {
        Install-Task $HttpTask 'client.http_server'
    }
}
if ($Mode -eq 'client' -and -not $Http) {
    Write-Host '  None needed for a client (Claude Code starts its own MCP client per session)'
}

Show-Status
if ($Mode -eq 'server') {
    Write-Host "Each other machine needs its own peer token: & `"$Python`" `"$(Join-Path $Repo 'installer.py')`" add-peer <name>"
    Write-Host '  (on that machine, put the printed token in client.token and <name> in client.name)'
}
Write-Host 'Behaviour rules for Claude Code: add this line to ~/.claude/CLAUDE.md'
Write-Host "  @$((Join-Path $Repo 'integrations\claude-code\CLAUDE.md') -replace '\\', '/')"
if ($Http) {
    Write-Host ''
    Write-Host 'Other MCP clients connect to http://127.0.0.1:9998/sse'
}
Write-Host ''
if ($Elevated) { Read-Host 'Done. Press Enter to close this window' | Out-Null }

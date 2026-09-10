#Requires -PSEdition Desktop
# ^ Windows PowerShell 5.1 only, deliberately.
#   Run under pwsh this fails immediately and self-explains, which is the point:
#     'The script cannot be run because it contained a "#requires" statement for
#      PowerShell editions 'Desktop'.'
#   5.1 is in-box on both the operator's PC and AWSPRDINFAAD01, so there is one
#   icon to recognise. ExchangeOnlineManagement 3.10.1 also raised its PowerShell 7
#   floor to 7.6 -- a version an operator can silently fail. 5.1 has no such floor.

<#
.SYNOPSIS
    Preflight for the exchange-mailbox-cleanup and exchange-mailbox-restore skills.

.DESCRIPTION
    Three modes, each honest about what it touches:

    -Check   (default) Read-only. Reports engine version, TLS 1.2, module presence and
             version, the report and log directories, TCP reachability of the three
             service endpoints, and a notice if the legacy C:\scripts\log path still has
             content. Changes nothing.

    -Install After ONE confirmation from the operator: sets TLS 1.2, bootstraps the NuGet
             provider, installs each missing module with Install-Module -Scope CurrentUser
             -Force -AllowClobber (three Graph sub-modules, not the Microsoft.Graph meta-
             module), verifies what landed and where, and creates C:\scripts\reports and
             C:\scripts\logs. Never machine-wide, never elevated, never touches the
             PSGallery repository policy. Stops on the first failure with the verbatim
             error - no retry loop, no machine-wide fallback. Reports if the CurrentUser
             module path is OneDrive-redirected (a known cause of slow or flaky imports)
             but does not try to fix it.

    -Roles   Must run IN THE OPERATOR'S ALREADY-CONNECTED WINDOW (dot-source or & it; a
             new powershell.exe has no sessions). Reads Get-ConnectionInformation and
             Get-MgContext, names any missing Graph scope, reads the signed-in user's
             Entra directory roles, and resolves the eDiscovery Manager role group by
             lookup (Name 'eDiscoveryManager' OR DisplayName 'eDiscovery Manager' -
             never a literal) and lists whether the operator is a member. Never connects
             and never grants anything.

    The sibling skill check runs first in every mode: exchange-mailbox-restore reads this
    skill's references by relative path, so both must be installed. A missing sibling is
    the named error SiblingSkillMissing (exit 2), not a file-not-found later.

    Windows PowerShell 5.1 only, enforced by the edition directive on line 1. No 7-only
    syntax anywhere. Writes are -Encoding UTF8. Installs are -Scope CurrentUser only -
    never machine-wide, never elevated.

.PARAMETER Check
    Read-only report. Default when no other switch is given.

.PARAMETER Install
    Install missing modules and create the two directories. Ask the operator first.

.PARAMETER Roles
    Check roles and scopes against the live sessions in this window.

.PARAMETER AdminUpn
    The operator's admin UPN, for -Roles. Defaults to the Graph context account.

.PARAMETER ReportPath
    Where to write the report copy. Defaults to C:\scripts\reports when it exists.

.EXAMPLE
    powershell.exe -NoProfile -File .\exo_preflight.ps1 -Check

.EXAMPLE
    powershell.exe -NoProfile -File .\exo_preflight.ps1 -Install

.EXAMPLE
    & .\exo_preflight.ps1 -Roles -AdminUpn admin@contoso.com     # in the connected window

.OUTPUTS
    PASS / WARN / FAIL / NOTICE lines on stdout; a UTF-8 copy under C:\scripts\reports.
    Exit 0 all pass, 1 at least one FAIL, 2 SiblingSkillMissing, 3 -Roles with no session.

.NOTES
    Version: 1.0   Author: Infrastructure Team   Date: 2026-09-10
    Never installs without -Install. Never connects. Never grants.
#>
[CmdletBinding(DefaultParameterSetName = 'Check')]
param(
    [Parameter(ParameterSetName = 'Check')]
    [switch]$Check,

    [Parameter(ParameterSetName = 'Install')]
    [switch]$Install,

    [Parameter(ParameterSetName = 'Roles')]
    [switch]$Roles,

    [Parameter(ParameterSetName = 'Roles')]
    [string]$AdminUpn,

    [string]$ReportPath = 'C:\scripts\reports'
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'

#region Configuration Variables
$ReportDir = 'C:\scripts\reports'
$LogDir = 'C:\scripts\logs'
$LegacyLogDir = 'C:\scripts\log'
$SiblingName = 'exchange-mailbox-restore'
$RequiredModule = @(
    @{
        Name = 'ExchangeOnlineManagement'
        Minimum = [version]'3.9.0'
        Why = 'Connect-IPPSSession -EnableSearchOnlySession (Test-MailboxPreservation -RunComplianceSearch)'
    }
    @{
        Name = 'Microsoft.Graph.Authentication'
        Minimum = [version]'2.0.0'
        Why = 'Connect-MgGraph, Get-MgContext'
    }
    @{
        Name = 'Microsoft.Graph.Users'
        Minimum = [version]'2.0.0'
        Why = 'Get-MgUser, Remove-MgUser, Get-MgUserLicenseDetail'
    }
    @{
        Name = 'Microsoft.Graph.Identity.DirectoryManagement'
        Minimum = [version]'2.0.0'
        Why = 'Get-MgSubscribedSku, Get-MgDirectoryDeletedItemAsUser, Restore-MgDirectoryDeletedItem'
    }
)
$RequiredScope = @('Organization.Read.All', 'User.ReadWrite.All', 'Directory.AccessAsUser.All', 'User.RevokeSessions.All')
$ExchangeAdminRole = @('Global Administrator', 'Exchange Administrator')
$UserAdminRole = @('Global Administrator', 'User Administrator')
$EDiscoveryGroupName = 'eDiscoveryManager'
$EDiscoveryGroupDisplayName = 'eDiscovery Manager'
$Endpoint = @(
    @{ Host = 'outlook.office365.com'; Port = 443; Why = 'Connect-ExchangeOnline' }
    @{ Host = 'login.microsoftonline.com'; Port = 443; Why = 'modern auth' }
    @{ Host = 'graph.microsoft.com'; Port = 443; Why = 'Connect-MgGraph' }
    @{ Host = 'www.powershellgallery.com'; Port = 443; Why = 'Install-Module' }
)
#endregion Configuration Variables

$script:Result = New-Object System.Collections.ArrayList
$script:FailCount = 0

function Add-Result {
    param(
        [ValidateSet('PASS', 'WARN', 'FAIL', 'NOTICE')]
        [string]$Status,
        [string]$Label,
        [string]$Detail = ''
    )
    $line = ('{0,-6} {1,-34} {2}' -f $Status, $Label, $Detail)
    [void]$script:Result.Add($line)
    if ($Status -eq 'FAIL') { $script:FailCount++ }
    Write-Information -MessageData $line -InformationAction Continue
}

function Write-Report {
    param([string]$Mode)
    $dir = $ReportPath
    if (-not (Test-Path -LiteralPath $dir -PathType Container)) { return }
    $stamp = Get-Date -Format 'yyyyMMddHHmm'
    $file = Join-Path $dir "exo-preflight-$Mode-$stamp.txt"
    $header = @(
        "exo_preflight.ps1 -$Mode  $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')  host=$env:COMPUTERNAME  user=$env:USERNAME"
        "PowerShell $($PSVersionTable.PSVersion)"
        ''
    )
    try {
        ($header + $script:Result) | Out-File -LiteralPath $file -Encoding UTF8
        Write-Information -MessageData "Report written: $file" -InformationAction Continue
    } catch {
        Write-Information -MessageData "Could not write report to $file : $($_.Exception.Message)" -InformationAction Continue
    }
}

function Test-Sibling {
    # $PSScriptRoot = <skills>\exchange-mailbox-cleanup\scripts
    $skillRoot = Split-Path -Parent $PSScriptRoot
    $skillsDir = Split-Path -Parent $skillRoot
    $sibling = Join-Path $skillsDir "$SiblingName\SKILL.md"
    if (Test-Path -LiteralPath $sibling -PathType Leaf) {
        Add-Result -Status PASS -Label 'sibling skill' -Detail "$SiblingName found at $(Split-Path -Parent $sibling)"
        return $true
    }
    Add-Result -Status FAIL -Label 'SiblingSkillMissing' -Detail "$SiblingName is not installed beside $(Split-Path -Leaf $skillRoot). Both skills install together - see SKILL.md. Looked for: $sibling"
    return $false
}

function Test-Engine {
    # The line-1 edition directive already refused pwsh before we got here; this line is the
    # positive record for the report. PSEdition is absent on PowerShell < 5.1, hence the guard.
    $v = $PSVersionTable.PSVersion
    $edition = 'Desktop'
    if ($PSVersionTable.ContainsKey('PSEdition')) { $edition = $PSVersionTable.PSEdition }
    if ($edition -eq 'Desktop' -and $v.Major -eq 5 -and $v.Minor -ge 1) {
        Add-Result -Status PASS -Label 'engine' -Detail "Windows PowerShell $v ($edition)"
    } else {
        Add-Result -Status FAIL -Label 'engine' -Detail "PowerShell $v ($edition). Windows PowerShell 5.1 is required - the blue icon whose title bar says 'Windows PowerShell'."
    }
    $proto = [Net.ServicePointManager]::SecurityProtocol
    if ($proto -band [Net.SecurityProtocolType]::Tls12) {
        Add-Result -Status PASS -Label 'TLS 1.2' -Detail "enabled ($proto)"
    } elseif ("$proto" -eq 'SystemDefault') {
        Add-Result -Status WARN -Label 'TLS 1.2' -Detail 'SystemDefault - usually negotiates 1.2 on Windows 10+, but Install-Module on 5.1 is the classic casualty when it does not. -Install sets it explicitly.'
    } else {
        Add-Result -Status WARN -Label 'TLS 1.2' -Detail "not enabled ($proto). Install-Module will fail against the Gallery until it is. -Install sets it; the connect block does not need it."
    }
}

function Get-InstalledModuleVersion {
    param([string]$Name)
    $available = @(Get-Module -ListAvailable -Name $Name -ErrorAction SilentlyContinue | Sort-Object Version -Descending)
    $found = $available | Select-Object -First 1
    if ($found) { return $found.Version }
    return $null
}

function Test-Module {
    $missing = @()
    foreach ($m in $RequiredModule) {
        $have = Get-InstalledModuleVersion -Name $m.Name
        if (-not $have) {
            Add-Result -Status FAIL -Label $m.Name -Detail "not installed. Needed for: $($m.Why)"
            $missing += $m
        } elseif ($have -lt $m.Minimum) {
            Add-Result -Status FAIL -Label $m.Name -Detail "$have installed, $($m.Minimum) or later required. Needed for: $($m.Why)"
            $missing += $m
        } else {
            Add-Result -Status PASS -Label $m.Name -Detail "$have"
        }
    }
    return $missing
}

function Test-Directory {
    foreach ($d in @($ReportDir, $LogDir)) {
        if (Test-Path -LiteralPath $d -PathType Container) {
            Add-Result -Status PASS -Label 'directory' -Detail $d
        } else {
            Add-Result -Status FAIL -Label 'directory' -Detail "$d does not exist. -Install creates it."
        }
    }
    if (Test-Path -LiteralPath $LegacyLogDir -PathType Container) {
        $count = @(Get-ChildItem -LiteralPath $LegacyLogDir -File -ErrorAction SilentlyContinue).Count
        if ($count -gt 0) {
            Add-Result -Status NOTICE -Label 'legacy log path' -Detail "$LegacyLogDir holds $count file(s) from runs before this skill. New logs go to $LogDir because every call passes -LogPath explicitly. Nothing is moved."
        }
    }
}

function Test-Endpoint {
    foreach ($e in $Endpoint) {
        $client = New-Object System.Net.Sockets.TcpClient
        try {
            $async = $client.BeginConnect($e.Host, $e.Port, $null, $null)
            if ($async.AsyncWaitHandle.WaitOne(4000, $false) -and $client.Connected) {
                Add-Result -Status PASS -Label "tcp $($e.Host):$($e.Port)" -Detail $e.Why
            } else {
                Add-Result -Status WARN -Label "tcp $($e.Host):$($e.Port)" -Detail "no connection within 4 s ($($e.Why)). A proxy may still allow it; the connect step will tell."
            }
        } catch {
            Add-Result -Status WARN -Label "tcp $($e.Host):$($e.Port)" -Detail "$($_.Exception.Message) ($($e.Why))"
        } finally {
            $client.Close()
        }
    }
}

function Test-ModulePath {
    # -Scope CurrentUser resolves under Documents\WindowsPowerShell\Modules. OneDrive Known
    # Folder Move often redirects Documents, and a redirected module path makes imports slow
    # or intermittently fail in ways that look nothing like an install problem. Report only.
    $documents = [Environment]::GetFolderPath('MyDocuments')
    $modulePath = Join-Path $documents 'WindowsPowerShell\Modules'
    $oneDrive = $env:OneDrive
    if ($oneDrive -and $documents.StartsWith($oneDrive, [System.StringComparison]::OrdinalIgnoreCase)) {
        Add-Result -Status NOTICE -Label 'CurrentUser module path' -Detail "$modulePath is under OneDrive ($oneDrive). Imports may be slow or intermittent. Not changed - raise it if Import-Module misbehaves."
    } elseif ($documents -match 'OneDrive') {
        Add-Result -Status NOTICE -Label 'CurrentUser module path' -Detail "$modulePath looks OneDrive-redirected. Imports may be slow or intermittent. Not changed."
    } else {
        Add-Result -Status PASS -Label 'CurrentUser module path' -Detail $modulePath
    }
}

function Invoke-Install {
    param([array]$Missing)
    [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
    Add-Result -Status PASS -Label 'TLS 1.2' -Detail 'enabled for this session'
    Test-ModulePath

    foreach ($d in @($ReportDir, $LogDir)) {
        if (-not (Test-Path -LiteralPath $d -PathType Container)) {
            try {
                New-Item -ItemType Directory -Path $d -Force | Out-Null
                Add-Result -Status PASS -Label 'directory created' -Detail $d
            } catch {
                Add-Result -Status FAIL -Label 'directory' -Detail "could not create $d : $($_.Exception.Message)"
            }
        }
    }

    if ($Missing.Count -eq 0) {
        Add-Result -Status PASS -Label 'modules' -Detail 'nothing to install'
        return
    }

    try {
        $nugetAll = @(Get-PackageProvider -Name NuGet -ListAvailable -ErrorAction SilentlyContinue)
        $nuget = @($nugetAll | Where-Object { $_.Version -ge [version]'2.8.5.201' })
        if ($nuget.Count -eq 0) {
            Install-PackageProvider -Name NuGet -MinimumVersion 2.8.5.201 -Scope CurrentUser -Force | Out-Null
            Add-Result -Status PASS -Label 'NuGet provider' -Detail 'installed'
        } else {
            Add-Result -Status PASS -Label 'NuGet provider' -Detail "$($nuget[0].Version)"
        }
    } catch {
        Add-Result -Status FAIL -Label 'NuGet provider' -Detail $_.Exception.Message
        return
    }

    Write-Information -MessageData "Installing $($Missing.Count) module(s) under your user profile (-Scope CurrentUser). No admin prompt. The Graph sub-modules take a few minutes each - a long pause here is normal, not a hang." -InformationAction Continue
    foreach ($m in $Missing) {
        try {
            # -Force covers the untrusted-repository prompt per call; the PSGallery
            # InstallationPolicy is deliberately left alone (persistent, profile-wide change).
            Install-Module -Name $m.Name -MinimumVersion $m.Minimum.ToString() -Scope CurrentUser -Force -AllowClobber -ErrorAction Stop
        } catch {
            Add-Result -Status FAIL -Label "$($m.Name) install" -Detail "$($_.Exception.Message) -- stopped. Not retried, not attempted machine-wide."
            return
        }
        # Verify what landed and where; never assume Install-Module's silence meant success.
        $landed = @(Get-Module -ListAvailable -Name $m.Name -ErrorAction SilentlyContinue | Sort-Object Version -Descending)
        if ($landed.Count -gt 0 -and $landed[0].Version -ge $m.Minimum) {
            Add-Result -Status PASS -Label "$($m.Name) installed" -Detail "$($landed[0].Version) at $($landed[0].ModuleBase)"
        } else {
            Add-Result -Status FAIL -Label "$($m.Name) verify" -Detail 'Install-Module returned but Get-Module -ListAvailable does not show the required version. Stopped.'
            return
        }
    }
}

function Test-Role {
    param([string]$Upn)

    # --- sessions present? ------------------------------------------------
    $exoCmd = Get-Command Get-ConnectionInformation -ErrorAction SilentlyContinue
    $mgCmd = Get-Command Get-MgContext -ErrorAction SilentlyContinue
    if (-not $exoCmd -and -not $mgCmd) {
        Add-Result -Status FAIL -Label 'sessions' -Detail 'neither ExchangeOnlineManagement nor Microsoft.Graph is loaded in this window. -Roles must run in the window where Connect-* was run: & .\exo_preflight.ps1 -Roles'
        return 3
    }

    $exoConn = @()
    $ippsConn = @()
    if ($exoCmd) {
        $all = @(Get-ConnectionInformation -ErrorAction SilentlyContinue)
        $exoConn = @($all | Where-Object { $_.ConnectionUri -like '*outlook.office365.com*' -and $_.State -eq 'Connected' })
        $ippsConn = @($all | Where-Object { $_.ConnectionUri -like '*compliance.protection.outlook.com*' -and $_.State -eq 'Connected' })
    }
    if ($exoConn.Count -gt 0) {
        Add-Result -Status PASS -Label 'Exchange Online session' -Detail "$($exoConn[0].UserPrincipalName)"
    } else {
        Add-Result -Status FAIL -Label 'Exchange Online session' -Detail 'not connected. Run Connect-ExchangeOnline -UserPrincipalName $Admin first.'
    }
    if ($ippsConn.Count -gt 0) {
        Add-Result -Status PASS -Label 'Security & Compliance session' -Detail "$($ippsConn[0].UserPrincipalName)"
    } else {
        Add-Result -Status WARN -Label 'Security & Compliance session' -Detail 'not connected. Needed for eDiscovery work (cleanup Steps 13, 21, 37). Run Connect-IPPSSession -UserPrincipalName $Admin.'
    }

    $ctx = $null
    if ($mgCmd) { $ctx = Get-MgContext -ErrorAction SilentlyContinue }
    if ($ctx) {
        Add-Result -Status PASS -Label 'Graph session' -Detail "$($ctx.Account)"
        $missingScope = @($RequiredScope | Where-Object { $ctx.Scopes -notcontains $_ })
        if ($missingScope.Count -eq 0) {
            Add-Result -Status PASS -Label 'Graph scopes' -Detail ($RequiredScope -join ', ')
        } else {
            Add-Result -Status FAIL -Label 'Graph scopes' -Detail "missing: $($missingScope -join ', '). Re-run Connect-MgGraph -Scopes with the full union (see connect-and-preflight.md)."
        }
        if (-not $Upn) { $Upn = $ctx.Account }
    } else {
        Add-Result -Status FAIL -Label 'Graph session' -Detail 'not connected. Run Connect-MgGraph -Scopes ... first.'
    }

    if ($exoConn.Count -eq 0 -and -not $ctx) { return 3 }

    if (-not $Upn) {
        Add-Result -Status FAIL -Label 'AdminUpn' -Detail 'not supplied and no Graph context to infer it from. Pass -AdminUpn.'
        return 1
    }

    # --- Entra directory roles via Graph ---------------------------------
    if ($ctx) {
        try {
            $memberOf = @(Get-MgUserMemberOf -UserId $Upn -All -ErrorAction Stop)
            $directoryRole = @($memberOf | Where-Object { $_.AdditionalProperties['@odata.type'] -eq '#microsoft.graph.directoryRole' })
            $roleName = @($directoryRole | ForEach-Object { $_.AdditionalProperties['displayName'] })
            if ($roleName.Count -eq 0) {
                Add-Result -Status WARN -Label 'Entra directory roles' -Detail 'none returned. Either no roles, or roles are PIM-eligible and not yet activated. Activate before Phase C.'
            } else {
                Add-Result -Status PASS -Label 'Entra directory roles' -Detail ($roleName -join ', ')
            }
            $hasExoAdmin = @($roleName | Where-Object { $ExchangeAdminRole -contains $_ }).Count -gt 0
            $hasUserAdmin = @($roleName | Where-Object { $UserAdminRole -contains $_ }).Count -gt 0
            if ($hasExoAdmin) {
                Add-Result -Status PASS -Label 'Exchange Administrator' -Detail 'present (or Global Administrator)'
            } else {
                Add-Result -Status FAIL -Label 'Exchange Administrator' -Detail 'missing. Set-Mailbox, New-Mailbox and -InactiveMailboxOnly will be denied. This skill cannot grant it; route to a Global Administrator.'
            }
            if ($hasUserAdmin) {
                Add-Result -Status PASS -Label 'User Administrator' -Detail 'present (or Global Administrator)'
            } else {
                Add-Result -Status WARN -Label 'User Administrator' -Detail 'missing. Needed only for Remove-MgUser (cleanup Step 30) and Restore-MgDirectoryDeletedItem (restore Path 4).'
            }
        } catch {
            Add-Result -Status WARN -Label 'Entra directory roles' -Detail "could not read: $($_.Exception.Message). Roles will surface as access-denied at the first mutating cmdlet instead."
        }
    }

    # --- eDiscovery Manager, resolved by lookup in the Purview session ----
    if ($ippsConn.Count -gt 0) {
        try {
            $allGroup = @(Get-RoleGroup -ResultSize Unlimited -ErrorAction Stop)
            $groups = @($allGroup | Where-Object { $_.Name -eq $EDiscoveryGroupName -or $_.DisplayName -eq $EDiscoveryGroupDisplayName })
            if ($groups.Count -ne 1) {
                Add-Result -Status WARN -Label 'eDiscovery Manager group' -Detail "lookup on Name '$EDiscoveryGroupName' / DisplayName '$EDiscoveryGroupDisplayName' returned $($groups.Count) group(s). If Exchange Online was connected AFTER Purview, Get-RoleGroup resolved to Exchange - run Connect-IPPSSession again and re-check."
            } else {
                $g = $groups[0]
                $members = @(Get-RoleGroupMember -Identity $g.Name -ResultSize Unlimited -ErrorAction Stop)
                $matching = @($members | Where-Object { ("$($_.PrimarySmtpAddress)" -ieq $Upn) -or ("$($_.WindowsLiveID)" -ieq $Upn) -or ("$($_.Name)" -ieq $Upn) })
                $isMember = $matching.Count -gt 0
                if ($isMember) {
                    Add-Result -Status PASS -Label 'eDiscovery Manager' -Detail "$Upn is a member of '$($g.Name)' ($($g.DisplayName)). Propagation to the search back end still takes 30-60 min after a fresh grant."
                } else {
                    Add-Result -Status FAIL -Label 'eDiscovery Manager' -Detail "$Upn is NOT a member of '$($g.Name)' ($($g.DisplayName)). Compliance searches return zero with no error until this is granted and propagated - cleanup Step 13."
                }
            }
        } catch {
            Add-Result -Status WARN -Label 'eDiscovery Manager' -Detail "could not read Purview role groups: $($_.Exception.Message)"
        }
    } else {
        Add-Result -Status WARN -Label 'eDiscovery Manager' -Detail 'not checked - no Security & Compliance session in this window.'
    }
    return 0
}

# ---------------------------------------------------------------------------
$mode = $PSCmdlet.ParameterSetName
Write-Information -MessageData "exo_preflight.ps1 -$mode  ($(Get-Date -Format 'yyyy-MM-dd HH:mm'))" -InformationAction Continue
Write-Information -MessageData '' -InformationAction Continue

if (-not (Test-Sibling)) {
    Write-Report -Mode $mode
    exit 2
}

$exitCode = 0
switch ($mode) {
    'Check' {
        Test-Engine
        [void](Test-Module)
        Test-Directory
        Test-Endpoint
    }
    'Install' {
        Test-Engine
        $missing = Test-Module
        Invoke-Install -Missing @($missing)
        Test-Directory
    }
    'Roles' {
        $exitCode = Test-Role -Upn $AdminUpn
    }
}

Write-Information -MessageData '' -InformationAction Continue
if ($script:FailCount -gt 0 -and $exitCode -eq 0) { $exitCode = 1 }
if ($exitCode -eq 0) {
    Write-Information -MessageData 'READY  every check passed' -InformationAction Continue
} elseif ($exitCode -eq 3) {
    Write-Information -MessageData 'BLOCKED  no live session - connect first, then re-run -Roles in the same window' -InformationAction Continue
} else {
    Write-Information -MessageData "BLOCKED  $($script:FailCount) FAIL line(s) above" -InformationAction Continue
}
Write-Report -Mode $mode
exit $exitCode

<#
.SYNOPSIS
    Stage 2 of Microsoft 365 offboarding.  Read-only report of held mailboxes that
    are past the handover window and ready for account deletion and licence reclaim.

.DESCRIPTION
    This script makes no changes.  It reports state and produces the sign-off list
    the team acts on manually.

    It answers three questions:

    1. Which terminated users are safely preserved and past the handover window,
       so their account can now be deleted and the licence recovered?
    2. Which terminated users are NOT safely preserved, meaning removing their
       licence or deleting their account would destroy mail permanently?
    3. Which mailboxes are already inactive, and is their hold configured with the
       duration the retention schedule expects?

    How the clock works:

    The handover window is measured from LitigationHoldDate, the timestamp Exchange
    stamps on the mailbox when the hold is applied.  Using the native stamp means
    there is no separate state file to keep in sync, and the report stays correct
    even if it is run from a different host than the one that applied the hold.

    Caveat: if a mailbox was already under a hold applied earlier for an unrelated
    reason, LitigationHoldDate reflects that earlier date, so the account will
    appear eligible immediately.  Use the DaysOnHold and RetentionComment columns
    to spot these before signing off.

    Deliberately read-only:

    Deletion is a manual step by design.  HR reversing a termination, or disabling
    the wrong account, is common enough that automatic deletion is not worth the
    risk.  This report is the paper trail for the human decision.

    Correct order of operations, which this report enforces:

        1. Hold applied and verified   <- Invoke-M365OffboardingHold.ps1
        2. Handover window elapses     <- tracked by this report
        3. Delete the AD account       <- manual, after sign-off
        4. Mailbox becomes inactive and the licence releases itself

    Never remove a licence as a separate step.  Removing a licence disconnects the
    mailbox and it is permanently unrecoverable after 30 days, whether or not a hold
    is in place.  A hold only produces a preserved inactive mailbox when the user
    ACCOUNT is deleted.  The SafeToRemoveLicense column exists to make that
    impossible to forget.

.PARAMETER HandoverWindowDay
    Days that must elapse between the hold being applied and the account becoming
    eligible for deletion.  Defaults to 30.

.PARAMETER ExpectedHoldDurationDay
    The LitigationHoldDuration the retention schedule expects, in days.  Defaults
    to 2555 (seven years).  Any mailbox whose hold duration differs is flagged with
    a HoldDurationMismatch finding, which catches mailboxes accidentally set to
    Unlimited or to a shorter duration than policy requires.

.PARAMETER IncludeInactiveMailbox
    Also enumerate inactive mailboxes (accounts already deleted) and audit their
    hold configuration.  Adds runtime on large tenants.  Enabled by default.

.PARAMETER AuthMode
    How to authenticate to Exchange Online and Microsoft Graph.

    ManagedIdentity - Azure Automation.  Requires -Organization.  No secrets.
    Certificate     - Unattended on a Windows host.  Requires -Organization,
                      -AppId, -CertificateThumbprint, and -TenantId.
    Interactive     - Prompts for sign-in.  Requires -AdminUpn.

    Defaults to Interactive.

.PARAMETER Organization
    The tenant's primary or onmicrosoft.com domain.  Required for ManagedIdentity
    and Certificate modes.

.PARAMETER AppId
    Application (client) ID of the Entra ID app registration used for certificate
    app-only authentication.

.PARAMETER CertificateThumbprint
    Thumbprint of the authentication certificate held in the executing account's
    certificate store.

.PARAMETER TenantId
    Directory (tenant) ID.  Used by Microsoft Graph in Certificate mode.

.PARAMETER AdminUpn
    The administrator UPN to sign in as when -AuthMode is Interactive.

.PARAMETER UseDeviceCode
    Sign in to Microsoft Graph with a device code instead of an interactive browser
    window.  Use this when the browser sign-in fails or never appears: Graph warns
    that on Windows the sign-in window can open behind other windows, and the local
    WAM token broker fails intermittently on the same host and account.  The device
    code flow prints a code to sign in with and bypasses the local broker entirely.
    Affects Microsoft Graph only; the Exchange Online connection is unchanged.

.PARAMETER ExcludeUpn
    Addresses to omit from the report, such as shared or service accounts that are
    intentionally left sign-in blocked.

.PARAMETER LogPath
    Directory for the log file and CSV output.  Defaults to C:\scripts\log, falling
    back to the sandbox temp directory in Azure Automation.

.PARAMETER SmtpServer
    SMTP relay for the report email.  When omitted, no email is sent.

.PARAMETER MailFrom
    From address for the report email.

.PARAMETER MailTo
    One or more recipients for the report email.

.EXAMPLE
    .\Get-M365OffboardingStatus.ps1 -AdminUpn "admin@contoso.com"

    Interactive report using the default 30 day handover window.

.EXAMPLE
    .\Get-M365OffboardingStatus.ps1 -AdminUpn "admin@contoso.com" | Where-Object Stage2Ready -eq $true | Format-Table UserPrincipalName, DaysOnHold, LicenseSkus

    Show only the accounts cleared for deletion, with the licences that will be
    recovered.

.EXAMPLE
    .\Get-M365OffboardingStatus.ps1 -AdminUpn "admin@contoso.com" | Where-Object { $_.SafeToRemoveLicense -eq 'No' -and $_.BlockingIssue -like '*not preserved*' }

    Surface the dangerous cases first: terminated users whose mail is NOT preserved.

.EXAMPLE
    .\Get-M365OffboardingStatus.ps1 -AuthMode ManagedIdentity -Organization "contoso.onmicrosoft.com" -SmtpServer "smtp.contoso.com" -MailFrom "automation@contoso.com" -MailTo "helpdesk@contoso.com"

    Scheduled Azure Automation run that emails the weekly sign-off report.

.EXAMPLE
    .\Get-M365OffboardingStatus.ps1 -AuthMode Certificate -Organization "contoso.onmicrosoft.com" -AppId "00000000-0000-0000-0000-000000000000" -CertificateThumbprint "ABC123..." -TenantId "11111111-1111-1111-1111-111111111111" -HandoverWindowDay 60

    Unattended Windows Server scheduled task using a 60 day handover window.

.INPUTS
    None. This script does not accept pipeline input.

.OUTPUTS
    System.Management.Automation.PSCustomObject
    One object per terminated user with properties: UserPrincipalName, DisplayName,
    MailboxState, AccountEnabled, LitigationHoldEnabled, LitigationHoldDate,
    LitigationHoldDuration, DaysOnHold, MailboxSizeGB, ArchiveStatus, LicenseSkus,
    Stage2Ready, SafeToRemoveLicense, BlockingIssue, RecommendedAction.

    CSV exported to {LogPath}\M365OffboardingStatus-{timestamp}.csv
    Log written to  {LogPath}\Get-M365OffboardingStatus-{yyyyMMdd}.log

.NOTES
    Version:        1.1
    Author:         Infrastructure Team
    Creation Date:  2026-07-26

    Change History:
    Date        Author                  Description
    ----------  ----------------------  -------------------------------------------
    2026-07-26  Infrastructure Team     Initial release
    2026-08-12  Infrastructure Team     Install missing required modules from the
                                        PowerShell Gallery on demand (CurrentUser
                                        scope) instead of throwing, and import
                                        Microsoft.Graph.* before
                                        ExchangeOnlineManagement to avoid the PS 5.1
                                        GetTokenAsync assembly-load conflict.
    2026-08-14  Infrastructure Team     Fixed Get-HoldDurationInDay, which killed the
                                        whole script on PowerShell 7 with "Cannot find
                                        an overload for TryParse and the argument
                                        count: 2".  .NET Core adds
                                        TryParse(ReadOnlySpan[char], out TimeSpan)
                                        beside the string overload, so an untyped
                                        [ref] leaves overload resolution with nothing
                                        to discriminate on; the [ref] target is now
                                        declared [TimeSpan].  Windows PowerShell 5.1
                                        has only the string overload, which is why it
                                        went unnoticed.  Also mirrored the Graph
                                        connection hardening from
                                        Invoke-M365OffboardingHold.ps1: stop when a
                                        Graph submodule was installed in this session,
                                        flatten the exception chain, retry, and add
                                        -UseDeviceCode.

    Required PowerShell modules:
    - ExchangeOnlineManagement 3.0.0 or later
    - Microsoft.Graph.Users

    Required permissions (read-only):

    Exchange Online, app-only (Certificate or ManagedIdentity):
    - Office 365 Exchange Online -> Exchange.ManageAsApp application permission
    - The service principal must hold the Exchange Recipient Reader or Exchange
      Administrator directory role

    Microsoft Graph application permissions:
    - User.Read.All
    - Organization.Read.All

    This script makes no changes of any kind.  It is safe to run at any time.

    Related documentation in this directory:
    - O365-Offboarding-Runbook.md
    - Litigation-Hold-Access-Guide.md
    - Litigation-Hold-7-Year-Retention.md
#>

[CmdletBinding()]
param(
    [Parameter(HelpMessage = "Days between hold application and deletion eligibility (default 30)")]
    [ValidateRange(0, 3650)]
    [int]$HandoverWindowDay = 30,

    [Parameter(HelpMessage = "Hold duration the retention schedule expects, in days (default 2555)")]
    [ValidateRange(1, 36500)]
    [int]$ExpectedHoldDurationDay = 2555,

    [Parameter(HelpMessage = "Also audit inactive mailboxes (accounts already deleted)")]
    [bool]$IncludeInactiveMailbox = $true,

    [Parameter(HelpMessage = "Authentication model: Interactive, Certificate, or ManagedIdentity")]
    [ValidateSet('Interactive', 'Certificate', 'ManagedIdentity')]
    [string]$AuthMode = 'Interactive',

    [Parameter(HelpMessage = "Tenant primary or onmicrosoft.com domain")]
    [ValidateNotNullOrEmpty()]
    [string]$Organization,

    [Parameter(HelpMessage = "Entra ID app registration client ID for certificate auth")]
    [ValidateNotNullOrEmpty()]
    [string]$AppId,

    [Parameter(HelpMessage = "Authentication certificate thumbprint")]
    [ValidateNotNullOrEmpty()]
    [string]$CertificateThumbprint,

    [Parameter(HelpMessage = "Directory (tenant) ID for Microsoft Graph certificate auth")]
    [ValidateNotNullOrEmpty()]
    [string]$TenantId,

    [Parameter(HelpMessage = "Administrator UPN for interactive sign-in")]
    [ValidateNotNullOrEmpty()]
    [string]$AdminUpn,

    [Parameter(HelpMessage = "Sign in to Microsoft Graph with a device code instead of a browser window (use when the browser sign-in fails or never appears)")]
    [switch]$UseDeviceCode,

    [Parameter(HelpMessage = "Addresses to omit from the report")]
    [string[]]$ExcludeUpn = @(),

    [Parameter(HelpMessage = "Directory for log and CSV output")]
    [ValidateNotNullOrEmpty()]
    [string]$LogPath = 'C:\scripts\log',

    [Parameter(HelpMessage = "SMTP relay for the report email")]
    [ValidateNotNullOrEmpty()]
    [string]$SmtpServer,

    [Parameter(HelpMessage = "From address for the report email")]
    [ValidateNotNullOrEmpty()]
    [string]$MailFrom,

    [Parameter(HelpMessage = "Recipients for the report email")]
    [string[]]$MailTo = @()
)

begin {
    #region Configuration Variables
    $ScriptName = 'Get-M365OffboardingStatus'
    $Timestamp = Get-Date -Format 'yyyyMMddHHmm'
    #endregion Configuration Variables

    #region Helper Functions
    function Write-Log {
        param(
            [Parameter(Mandatory)]
            [string]$Message,
            [ValidateSet('INFO', 'WARNING', 'ERROR', 'VERBOSE')]
            [string]$Level = 'INFO'
        )

        $stamp = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
        $logEntry = "[$stamp] [$Level] $Message"

        if ($script:ResolvedLogPath) {
            $logFile = Join-Path $script:ResolvedLogPath "$ScriptName-$(Get-Date -Format 'yyyyMMdd').log"
            Add-Content -Path $logFile -Value $logEntry -ErrorAction SilentlyContinue
        }

        switch ($Level) {
            'ERROR' { Write-Error $Message -ErrorAction Continue }
            'WARNING' { Write-Warning $Message }
            'VERBOSE' { Write-Verbose $Message }
            default { Write-Output $Message }
        }
    }

    function Resolve-LogDirectory {
        param(
            [Parameter(Mandatory)]
            [string]$Preferred
        )

        try {
            if (-not (Test-Path $Preferred)) {
                New-Item -ItemType Directory -Path $Preferred -Force -ErrorAction Stop | Out-Null
            }
            return $Preferred
        } catch {
            $fallback = Join-Path $env:TEMP 'M365Offboarding'
            if (-not (Test-Path $fallback)) {
                New-Item -ItemType Directory -Path $fallback -Force -ErrorAction SilentlyContinue | Out-Null
            }
            Write-Warning "Log path '$Preferred' is not writable. Falling back to '$fallback'."
            return $fallback
        }
    }

    function Initialize-RequiredModule {
        <#
            Ensure each required module is present -- installing it from the
            PowerShell Gallery when it is missing -- then import it, in the order
            supplied.

            Import order is load-bearing.  Under Windows PowerShell 5.1 the whole
            session shares one .NET Framework AppDomain with no assembly isolation,
            and ExchangeOnlineManagement and the Microsoft.Graph.* modules ship
            different builds of the same dependency assemblies.  Whichever imports
            first wins the binding.  Import EXO first and Graph then fails to load
            with "Method 'GetTokenAsync' ... does not have an implementation" (a
            TypeLoadException); import the Graph modules first and both coexist.
            Callers must therefore pass the Microsoft.Graph.* modules ahead of
            ExchangeOnlineManagement.
        #>
        param(
            [Parameter(Mandatory)]
            [string[]]$Name,

            [ValidateSet('CurrentUser', 'AllUsers')]
            [string]$Scope = 'CurrentUser'
        )

        # PowerShellGet talks to the Gallery over TLS 1.2; 5.1 negotiates an older
        # protocol by default and the request is rejected before any download.
        if ([System.Net.ServicePointManager]::SecurityProtocol -notmatch 'Tls12') {
            [System.Net.ServicePointManager]::SecurityProtocol =
            [System.Net.ServicePointManager]::SecurityProtocol -bor [System.Net.SecurityProtocolType]::Tls12
        }

        $installed = @()

        foreach ($moduleName in $Name) {
            if (-not (Get-Module -Name $moduleName -ListAvailable)) {
                Write-Log -Message "Module '$moduleName' is not installed; installing from the PowerShell Gallery (scope $Scope)..." -Level 'WARNING'

                if (-not (Get-PackageProvider -Name NuGet -ListAvailable -ErrorAction SilentlyContinue)) {
                    Install-PackageProvider -Name NuGet -MinimumVersion '2.8.5.201' -Scope $Scope -Force -ErrorAction Stop | Out-Null
                }

                try {
                    Install-Module -Name $moduleName -Scope $Scope -Force -AllowClobber -ErrorAction Stop
                } catch {
                    throw "Failed to install required module '$moduleName' from the PowerShell Gallery: $($_.Exception.Message). Install it manually with: Install-Module $moduleName -Scope $Scope"
                }

                Write-Log -Message "Module '$moduleName' installed." -Level 'INFO'
                $installed += $moduleName
            }

            # Import eagerly and in order so the shared assemblies bind correctly,
            # rather than leaving it to command autoloading.
            Import-Module -Name $moduleName -ErrorAction Stop
        }

        # A Microsoft.Graph submodule installed during THIS session cannot be used in
        # it.  Every submodule shares the assemblies owned by
        # Microsoft.Graph.Authentication; once that module has been imported, the
        # Gallery cannot replace it -- which is the "The version 'x' of module
        # 'Microsoft.Graph.Authentication' is currently in use" warning -- so a
        # submodule written to disk afterwards binds against a dependency graph that
        # was already resolved without it.  Connect-MgGraph then fails with an opaque
        # "InteractiveBrowserCredential authentication failed:" and no inner detail,
        # which reads like a credential or permissions problem and is neither.
        #
        # Stop here rather than continuing into that failure.  The modules are now on
        # disk and correct, so the same command in a new session installs nothing and
        # connects normally.
        $graphInstalled = @($installed | Where-Object { $_ -like 'Microsoft.Graph*' })
        if ($graphInstalled.Count -gt 0) {
            throw ("Installed {0} during this session, so this session cannot connect to Microsoft Graph.`n`n" -f ($graphInstalled -join ', ')) +
            "Microsoft Graph submodules share the assemblies loaded by Microsoft.Graph.Authentication. That module was " +
            "already imported before the others were installed, so it could not be updated, and Connect-MgGraph would " +
            "now fail with an unexplained authentication error rather than a useful one.`n`n" +
            "This script is read-only, so nothing has been changed anywhere.`n`n" +
            "Close this PowerShell session, open a new one, and re-run exactly the same command. The modules are " +
            "installed now, so no install step will run and the connection will proceed."
        }
    }

    function Resolve-ExceptionDetail {
        <#
            Flatten an exception chain into one readable string.

            Azure.Identity raises AuthenticationFailedException with a message that
            ends at "InteractiveBrowserCredential authentication failed:" and puts
            the actual cause -- MSAL error code, WAM broker fault, a cancelled or
            never-displayed sign-in window, no network -- in InnerException.
            Reporting only $_.Exception.Message therefore prints a colon followed by
            nothing, which is what made the original failure impossible to diagnose.
        #>
        param($ErrorRecord)

        $part = @()
        $current = $ErrorRecord.Exception
        $depth = 0

        while ($null -ne $current -and $depth -lt 8) {
            $message = ($current.Message | Out-String).Trim()
            if ($message) { $part += "[$($current.GetType().Name)] $message" }
            $current = $current.InnerException
            $depth++
        }

        if ($part.Count -eq 0) { return $ErrorRecord.ToString() }
        return ($part -join "`n  -> ")
    }

    function Connect-GraphInteractive {
        <#
            Connect to Microsoft Graph, retrying a transient failure and reporting a
            non-transient one in full.  Mirrors Invoke-M365OffboardingHold.ps1 so both
            halves of the offboarding workflow fail the same way and read the same way.
        #>
        param(
            [Parameter(Mandatory)]
            [hashtable]$Parameter
        )

        $maxAttempt = 3
        $attempt = 0
        $flow = if ($Parameter.ContainsKey('UseDeviceCode')) { 'device code' } else { 'interactive browser' }

        while ($true) {
            $attempt++

            try {
                Write-Log -Message "Connecting to Microsoft Graph via $flow (attempt $attempt of $maxAttempt)..."
                Connect-MgGraph @Parameter -ErrorAction Stop

                $context = Get-MgContext
                if (-not $context -or -not $context.Account) {
                    throw "Connect-MgGraph returned without error but no Graph context is present."
                }

                Write-Log -Message "Connected to Microsoft Graph as $($context.Account)." -Level 'VERBOSE'
                return
            } catch {
                $detail = Resolve-ExceptionDetail -ErrorRecord $_

                if ($attempt -ge $maxAttempt) {
                    $hint = if ($Parameter.ContainsKey('UseDeviceCode')) {
                        "Device-code sign-in also failed, so the local browser and token broker are not the cause. " +
                        "Check network access to login.microsoftonline.com, and that this account may consent to the " +
                        "scopes listed above."
                    } else {
                        "If no sign-in window ever appeared, it may have opened behind another window -- Graph warns " +
                        "about exactly this on Windows. Re-run with -UseDeviceCode to sign in with a code instead of a " +
                        "browser window, which bypasses the local broker entirely."
                    }

                    throw "Could not connect to Microsoft Graph after $attempt attempt(s).`n`n$detail`n`n$hint"
                }

                Write-Log -Message "Graph connection failed on attempt $attempt of ${maxAttempt}:`n  $detail" -Level 'WARNING'
                Write-Log -Message "Retrying in 20 seconds. Interactive sign-in through the local token broker fails intermittently; a second attempt commonly clears it." -Level 'WARNING'
                Start-Sleep -Seconds 20
            }
        }
    }

    function Connect-OffboardingService {
        param(
            [Parameter(Mandatory)]
            [string]$Mode
        )

        switch ($Mode) {
            'ManagedIdentity' {
                if (-not $Organization) {
                    throw "-Organization is required when -AuthMode is ManagedIdentity."
                }

                Write-Log -Message "Connecting to Exchange Online using Managed Identity ($Organization)..."
                Connect-ExchangeOnline -ManagedIdentity -Organization $Organization -ShowBanner:$false -ErrorAction Stop

                Write-Log -Message "Connecting to Microsoft Graph using Managed Identity..."
                Connect-MgGraph -Identity -NoWelcome -ErrorAction Stop
            }

            'Certificate' {
                foreach ($required in @('Organization', 'AppId', 'CertificateThumbprint', 'TenantId')) {
                    if (-not (Get-Variable -Name $required -ValueOnly -ErrorAction SilentlyContinue)) {
                        throw "-$required is required when -AuthMode is Certificate."
                    }
                }

                Write-Log -Message "Connecting to Exchange Online using certificate app-only auth ($Organization)..."
                Connect-ExchangeOnline -AppId $AppId -CertificateThumbprint $CertificateThumbprint `
                    -Organization $Organization -ShowBanner:$false -ErrorAction Stop

                Write-Log -Message "Connecting to Microsoft Graph using certificate app-only auth..."
                Connect-MgGraph -ClientId $AppId -TenantId $TenantId `
                    -CertificateThumbprint $CertificateThumbprint -NoWelcome -ErrorAction Stop
            }

            'Interactive' {
                if (-not $AdminUpn) {
                    throw "-AdminUpn is required when -AuthMode is Interactive."
                }

                Write-Log -Message "Connecting to Exchange Online interactively as $AdminUpn..."
                Connect-ExchangeOnline -UserPrincipalName $AdminUpn -ShowBanner:$false -ErrorAction Stop

                # Splatted rather than written inline so -UseDeviceCode is genuinely
                # absent when not requested; passing -UseDeviceCode:$false is not the
                # same thing to Connect-MgGraph.
                $graphParam = @{
                    Scopes = @('User.Read.All', 'Organization.Read.All')
                    NoWelcome = $true
                }
                if ($UseDeviceCode) { $graphParam['UseDeviceCode'] = $true }

                Connect-GraphInteractive -Parameter $graphParam
            }
        }
    }

    function Resolve-SkuPartNumber {
        param(
            [AllowNull()]
            $AssignedLicense
        )

        if (-not $AssignedLicense -or $AssignedLicense.Count -eq 0) {
            return 'None'
        }

        if (-not $script:SkuLookup) {
            $script:SkuLookup = @{}
            try {
                Get-MgSubscribedSku -ErrorAction Stop | ForEach-Object {
                    $script:SkuLookup[$_.SkuId] = $_.SkuPartNumber
                }
            } catch {
                Write-Log -Message "Could not read subscribed SKUs, licence names will show as GUIDs: $($_.Exception.Message)" -Level 'WARNING'
            }
        }

        $partNumber = $AssignedLicense | ForEach-Object {
            if ($script:SkuLookup.ContainsKey($_.SkuId)) { $script:SkuLookup[$_.SkuId] } else { $_.SkuId }
        }

        return ($partNumber -join '; ')
    }

    function Get-MailboxSizeInGb {
        param(
            [Parameter(Mandatory)]
            [string]$Identity,
            [switch]$InactiveMailbox
        )

        try {
            $statParam = @{ Identity = $Identity; ErrorAction = 'Stop' }
            if ($InactiveMailbox) { $statParam['IncludeSoftDeletedRecipients'] = $true }

            $stats = Get-MailboxStatistics @statParam
            if ($stats.TotalItemSize) {
                $byteText = [regex]::Match($stats.TotalItemSize.ToString(), '\(([\d,]+) bytes\)')
                if ($byteText.Success) {
                    return [math]::Round(([double]($byteText.Groups[1].Value -replace ',', '')) / 1GB, 2)
                }
            }
        } catch {
            Write-Log -Message "Could not read statistics for $Identity`: $($_.Exception.Message)" -Level 'VERBOSE'
        }

        return $null
    }

    function Get-HoldDurationInDay {
        <#
            LitigationHoldDuration comes back as either the string 'Unlimited' or a
            timespan-like value.  Normalise to an integer day count, or $null when
            the hold is unlimited.
        #>
        param(
            [AllowNull()]
            $Duration
        )

        if ($null -eq $Duration) { return $null }

        $text = $Duration.ToString()
        if ($text -match 'Unlimited') { return $null }

        if ($Duration -is [TimeSpan]) { return [int]$Duration.TotalDays }

        $asInt = $text -as [int]
        if ($asInt) { return $asInt }

        # $parsed must be declared [TimeSpan] rather than left as $null.  .NET Core
        # added TryParse(ReadOnlySpan[char], out TimeSpan) alongside the original
        # TryParse(string, out TimeSpan), so PowerShell 7 sees two two-argument
        # candidates.  An untyped [ref] gives overload resolution nothing to
        # discriminate on and the call fails outright with "Cannot find an overload
        # for TryParse and the argument count: 2" -- not a parse failure, so the
        # $null return below is never reached and the whole script dies here.
        # Windows PowerShell 5.1 has only the string overload, which is why this
        # went unnoticed until the script was run on 7.x.
        [TimeSpan]$parsed = [TimeSpan]::Zero
        if ([TimeSpan]::TryParse($text, [ref]$parsed)) { return [int]$parsed.TotalDays }

        return $null
    }

    function Send-StatusReport {
        param(
            [Parameter(Mandatory)]
            [AllowEmptyCollection()]
            [array]$Result,
            [Parameter(Mandatory)]
            [string]$CsvPath
        )

        if (-not $SmtpServer -or -not $MailFrom -or $MailTo.Count -eq 0) {
            Write-Log -Message "Email report skipped (SmtpServer, MailFrom, or MailTo not supplied)." -Level 'VERBOSE'
            return
        }

        $ready = @($Result | Where-Object { $_.Stage2Ready })
        $atRisk = @($Result | Where-Object { -not $_.LitigationHoldEnabled -and $_.MailboxState -eq 'Active' })
        $waiting = @($Result | Where-Object { $_.LitigationHoldEnabled -and -not $_.Stage2Ready -and $_.MailboxState -eq 'Active' })

        $subject = "M365 Offboarding Stage 2 - $($ready.Count) ready for deletion, $($atRisk.Count) NOT preserved"

        $readyRow = if ($ready.Count -gt 0) {
            ($ready | ForEach-Object {
                "<tr><td>$($_.UserPrincipalName)</td><td>$($_.DaysOnHold)</td><td>$($_.MailboxSizeGB)</td><td>$($_.LicenseSkus)</td></tr>"
            }) -join "`n"
        } else {
            '<tr><td colspan="4">None</td></tr>'
        }

        $riskRow = if ($atRisk.Count -gt 0) {
            ($atRisk | ForEach-Object {
                "<tr><td>$($_.UserPrincipalName)</td><td>$($_.BlockingIssue)</td><td>$($_.LicenseSkus)</td></tr>"
            }) -join "`n"
        } else {
            '<tr><td colspan="3">None</td></tr>'
        }

        $body = @"
<p><b>Microsoft 365 Offboarding - Stage 2 Sign-Off Report</b></p>
<p>Handover window: $HandoverWindowDay days. This report changes nothing.</p>

<h3>Ready for account deletion ($($ready.Count))</h3>
<p>Delete the on-premises AD account. The mailbox becomes an inactive mailbox and
the licence releases itself. Do not remove the licence as a separate step.</p>
<table border="1" cellpadding="4" cellspacing="0">
<tr><th>User</th><th>Days on hold</th><th>Mailbox GB</th><th>Licences to recover</th></tr>
$readyRow
</table>

<h3 style="color:#b00020;">NOT preserved - do not delete or unlicense ($($atRisk.Count))</h3>
<p>These terminated users have no Litigation Hold. Deleting the account or removing
the licence will destroy their mail permanently. Run Invoke-M365OffboardingHold.ps1
against them first.</p>
<table border="1" cellpadding="4" cellspacing="0">
<tr><th>User</th><th>Issue</th><th>Licences</th></tr>
$riskRow
</table>

<h3>Still within the handover window ($($waiting.Count))</h3>
<p>Preserved and waiting out the $HandoverWindowDay day window. No action needed.</p>

<p>Full CSV: $CsvPath</p>
"@

        try {
            Send-MailMessage -SmtpServer $SmtpServer -From $MailFrom -To $MailTo `
                -Subject $subject -Body $body -BodyAsHtml -ErrorAction Stop
            Write-Log -Message "Report email sent to $($MailTo -join ', ')."
        } catch {
            Write-Log -Message "Failed to send report email: $($_.Exception.Message)" -Level 'WARNING'
        }
    }
    #endregion Helper Functions

    $script:ResolvedLogPath = Resolve-LogDirectory -Preferred $LogPath
    $script:SkuLookup = $null
    $startTime = Get-Date

    Write-Log -Message "========================================"
    Write-Log -Message "$ScriptName started"
    Write-Log -Message "========================================"
    Write-Log -Message "AuthMode              : $AuthMode"
    Write-Log -Message "RunAs                 : $env:USERDOMAIN\$env:USERNAME"
    Write-Log -Message "Host                  : $env:COMPUTERNAME"
    Write-Log -Message "Handover window       : $HandoverWindowDay day(s)"
    Write-Log -Message "Expected hold duration: $ExpectedHoldDurationDay day(s)"
    Write-Log -Message "Include inactive      : $IncludeInactiveMailbox"
    Write-Log -Message "Log directory         : $script:ResolvedLogPath"
    Write-Log -Message "This script is read-only. It changes nothing."

    # Graph before EXO: under PS 5.1 they share dependency assemblies and importing
    # EXO first makes Graph fail to load (GetTokenAsync TypeLoadException).
    Initialize-RequiredModule -Name @('Microsoft.Graph.Users', 'ExchangeOnlineManagement')
    Connect-OffboardingService -Mode $AuthMode
}

process {
    $result = @()

    try {
        #region Enumerate Sign-In Blocked Accounts
        Write-Log -Message "Querying Entra ID for sign-in-blocked member accounts..."

        $selectProperty = @('id', 'userPrincipalName', 'displayName', 'accountEnabled', 'assignedLicenses', 'onPremisesSyncEnabled')
        $blockedUser = Get-MgUser -Filter "accountEnabled eq false and userType eq 'Member'" `
            -Property $selectProperty -All -ErrorAction Stop

        if ($ExcludeUpn.Count -gt 0) {
            $blockedUser = $blockedUser | Where-Object { $_.UserPrincipalName -notin $ExcludeUpn }
        }

        $blockedUser = @($blockedUser)
        Write-Log -Message "$($blockedUser.Count) sign-in-blocked account(s) to evaluate."
        #endregion Enumerate Sign-In Blocked Accounts

        #region Evaluate Active Mailboxes
        foreach ($user in $blockedUser) {
            $upn = $user.UserPrincipalName
            Write-Log -Message "Evaluating $upn..." -Level 'VERBOSE'

            $record = [PSCustomObject]@{
                UserPrincipalName = $upn
                DisplayName = $user.DisplayName
                MailboxState = 'NoMailbox'
                AccountEnabled = $user.AccountEnabled
                SyncedFromOnPrem = [bool]$user.OnPremisesSyncEnabled
                LitigationHoldEnabled = $false
                LitigationHoldDate = $null
                LitigationHoldOwner = $null
                LitigationHoldDuration = $null
                DaysOnHold = $null
                MailboxSizeGB = $null
                ArchiveStatus = $null
                RetentionComment = $null
                LicenseSkus = (Resolve-SkuPartNumber -AssignedLicense $user.AssignedLicenses)
                Stage2Ready = $false
                SafeToRemoveLicense = 'No'
                BlockingIssue = ''
                RecommendedAction = ''
            }

            $mailbox = $null
            try {
                $mailbox = Get-Mailbox -Identity $upn -ErrorAction Stop
            } catch {
                $record.BlockingIssue = 'No mailbox in Exchange Online'
                $record.RecommendedAction = 'No mail to preserve. Account can be deleted once other offboarding steps are complete.'
                $record.SafeToRemoveLicense = 'N/A (no mailbox)'
                $result += $record
                continue
            }

            $record.MailboxState = 'Active'
            $record.LitigationHoldEnabled = [bool]$mailbox.LitigationHoldEnabled
            $record.LitigationHoldDate = $mailbox.LitigationHoldDate
            $record.LitigationHoldOwner = $mailbox.LitigationHoldOwner
            $record.LitigationHoldDuration = $mailbox.LitigationHoldDuration
            $record.RetentionComment = $mailbox.RetentionComment
            $record.ArchiveStatus = $mailbox.ArchiveStatus
            $record.MailboxSizeGB = Get-MailboxSizeInGb -Identity $upn

            if (-not $record.LitigationHoldEnabled) {
                $record.BlockingIssue = 'Mailbox is NOT preserved - no Litigation Hold applied'
                $record.RecommendedAction = 'Run Invoke-M365OffboardingHold.ps1 for this user BEFORE deleting the account or touching the licence. Deleting now destroys the mail.'
                $record.SafeToRemoveLicense = 'No - mail would be lost'
                $result += $record
                continue
            }

            if ($mailbox.LitigationHoldDate) {
                $record.DaysOnHold = [int]((Get-Date) - $mailbox.LitigationHoldDate).TotalDays
            }

            # Flag holds that do not match the retention schedule.
            $durationDay = Get-HoldDurationInDay -Duration $mailbox.LitigationHoldDuration
            $finding = @()

            if ($null -eq $durationDay) {
                if ($ExpectedHoldDurationDay -gt 0) {
                    $finding += "HoldDurationMismatch: duration is Unlimited but policy expects $ExpectedHoldDurationDay days, so items will never age out"
                }
            } elseif ($durationDay -ne $ExpectedHoldDurationDay) {
                $finding += "HoldDurationMismatch: duration is $durationDay days but policy expects $ExpectedHoldDurationDay days"
            }

            if ($null -eq $record.DaysOnHold) {
                $finding += 'LitigationHoldDate is empty, so the handover window cannot be calculated'
                $record.RecommendedAction = 'Re-apply the hold so a LitigationHoldDate is stamped, then re-run this report.'
            } elseif ($record.DaysOnHold -ge $HandoverWindowDay) {
                $record.Stage2Ready = $true
                $record.RecommendedAction = "Cleared for Stage 2. Delete the on-premises AD account; the mailbox becomes inactive and the licence ($($record.LicenseSkus)) releases automatically. Do NOT remove the licence as a separate step."
                $record.SafeToRemoveLicense = 'No - delete the account instead, the licence releases itself'
            } else {
                $remaining = $HandoverWindowDay - $record.DaysOnHold
                $finding += "Within handover window: $($record.DaysOnHold) of $HandoverWindowDay days elapsed, $remaining remaining"
                $record.RecommendedAction = 'Preserved and waiting. No action needed.'
                $record.SafeToRemoveLicense = 'No - still within handover window'
            }

            $record.BlockingIssue = ($finding -join '; ')
            $result += $record
        }
        #endregion Evaluate Active Mailboxes

        #region Audit Inactive Mailboxes
        if ($IncludeInactiveMailbox) {
            Write-Log -Message "Enumerating inactive mailboxes (accounts already deleted)..."

            try {
                $inactive = @(Get-Mailbox -InactiveMailboxOnly -ResultSize Unlimited -ErrorAction Stop)
                Write-Log -Message "$($inactive.Count) inactive mailbox(es) found."

                foreach ($box in $inactive) {
                    $durationDay = Get-HoldDurationInDay -Duration $box.LitigationHoldDuration
                    $finding = @()

                    if ($null -eq $durationDay) {
                        if ($ExpectedHoldDurationDay -gt 0) {
                            $finding += "HoldDurationMismatch: duration is Unlimited but policy expects $ExpectedHoldDurationDay days, so this mailbox is retained forever"
                        }
                    } elseif ($durationDay -ne $ExpectedHoldDurationDay) {
                        $finding += "HoldDurationMismatch: duration is $durationDay days but policy expects $ExpectedHoldDurationDay days"
                    }

                    if (-not $box.LitigationHoldEnabled) {
                        $finding += 'Inactive mailbox with no Litigation Hold - verify a Purview retention policy covers it, otherwise it may be purged'
                    }

                    $result += [PSCustomObject]@{
                        UserPrincipalName = $box.UserPrincipalName
                        DisplayName = $box.DisplayName
                        MailboxState = 'Inactive'
                        AccountEnabled = $false
                        SyncedFromOnPrem = $null
                        LitigationHoldEnabled = [bool]$box.LitigationHoldEnabled
                        LitigationHoldDate = $box.LitigationHoldDate
                        LitigationHoldOwner = $box.LitigationHoldOwner
                        LitigationHoldDuration = $box.LitigationHoldDuration
                        DaysOnHold = if ($box.LitigationHoldDate) { [int]((Get-Date) - $box.LitigationHoldDate).TotalDays } else { $null }
                        MailboxSizeGB = (Get-MailboxSizeInGb -Identity $box.ExchangeGuid.ToString() -InactiveMailbox)
                        ArchiveStatus = $box.ArchiveStatus
                        RetentionComment = $box.RetentionComment
                        LicenseSkus = 'None (inactive mailbox consumes no licence)'
                        Stage2Ready = $false
                        SafeToRemoveLicense = 'N/A (already released)'
                        BlockingIssue = ($finding -join '; ')
                        RecommendedAction = 'Offboarding complete. Mail is searchable through Purview eDiscovery. See Litigation-Hold-Access-Guide.md.'
                    }
                }
            } catch {
                Write-Log -Message "Could not enumerate inactive mailboxes: $($_.Exception.Message)" -Level 'WARNING'
            }
        }
        #endregion Audit Inactive Mailboxes

        #region Report
        Write-Log -Message "========================================"
        Write-Log -Message "=== STAGE 2 SUMMARY ==="

        $ready = @($result | Where-Object { $_.Stage2Ready })
        $atRisk = @($result | Where-Object { -not $_.LitigationHoldEnabled -and $_.MailboxState -eq 'Active' })
        $waiting = @($result | Where-Object { $_.LitigationHoldEnabled -and -not $_.Stage2Ready -and $_.MailboxState -eq 'Active' })
        $inactiveCount = @($result | Where-Object { $_.MailboxState -eq 'Inactive' }).Count
        $mismatch = @($result | Where-Object { $_.BlockingIssue -like '*HoldDurationMismatch*' })

        Write-Log -Message "  Ready for account deletion      : $($ready.Count)"
        Write-Log -Message "  NOT preserved (at risk)         : $($atRisk.Count)"
        Write-Log -Message "  Within handover window          : $($waiting.Count)"
        Write-Log -Message "  Already inactive                : $inactiveCount"
        Write-Log -Message "  Hold duration mismatches        : $($mismatch.Count)"

        if ($ready.Count -gt 0) {
            Write-Log -Message "=== READY FOR DELETION (licences recoverable) ==="
            foreach ($item in $ready) {
                Write-Log -Message "  $($item.UserPrincipalName) - $($item.DaysOnHold) days on hold - $($item.MailboxSizeGB) GB - $($item.LicenseSkus)"
            }
        }

        if ($atRisk.Count -gt 0) {
            Write-Log -Message "=== NOT PRESERVED - DO NOT DELETE OR UNLICENSE ===" -Level 'WARNING'
            foreach ($item in $atRisk) {
                Write-Log -Message "  $($item.UserPrincipalName) - $($item.BlockingIssue)" -Level 'WARNING'
            }
            Write-Log -Message "Run Invoke-M365OffboardingHold.ps1 against the accounts above before any deletion or licence change." -Level 'WARNING'
        }

        if ($mismatch.Count -gt 0) {
            Write-Log -Message "=== HOLD DURATION MISMATCHES ===" -Level 'WARNING'
            foreach ($item in $mismatch) {
                Write-Log -Message "  $($item.UserPrincipalName) - $($item.BlockingIssue)" -Level 'WARNING'
            }
        }

        $csvPath = Join-Path $script:ResolvedLogPath "M365OffboardingStatus-$Timestamp.csv"
        if ($result.Count -gt 0) {
            $result | Export-Csv -Path $csvPath -NoTypeInformation -Encoding UTF8
            Write-Log -Message "Report exported to: $csvPath"
            Send-StatusReport -Result $result -CsvPath $csvPath
        } else {
            Write-Log -Message "No terminated users found. Nothing to report."
        }
        #endregion Report
    } finally {
        #region Disconnect
        try {
            Disconnect-ExchangeOnline -Confirm:$false -ErrorAction SilentlyContinue
            Write-Log -Message "Disconnected from Exchange Online." -Level 'VERBOSE'
        } catch {
            Write-Log -Message "Exchange Online disconnect reported: $($_.Exception.Message)" -Level 'VERBOSE'
        }

        try {
            $null = Disconnect-MgGraph -ErrorAction SilentlyContinue
            Write-Log -Message "Disconnected from Microsoft Graph." -Level 'VERBOSE'
        } catch {
            Write-Log -Message "Microsoft Graph disconnect reported: $($_.Exception.Message)" -Level 'VERBOSE'
        }
        #endregion Disconnect

        $duration = (Get-Date) - $startTime
        Write-Log -Message "========================================"
        Write-Log -Message "$ScriptName completed"
        Write-Log -Message "Duration : $($duration.ToString('hh\:mm\:ss'))"
        Write-Log -Message "========================================"
    }

    return $result
}

<#
.SYNOPSIS
    Inventories Exchange Online mailboxes by type, the accounts behind them, and
    every delegate who can open or send from them.

.DESCRIPTION
    Read-only discovery script for the mailbox cleanup project.  By default it
    covers every mailbox type in the tenant - user, shared, room, and equipment -
    and reports the type as its own column, because Microsoft Graph cannot
    distinguish them and the type decides what may safely be cleaned up.  A room
    mailbox that looks idle is still a bookable resource.

    It answers three questions for each mailbox:

      1. Is the underlying user account inactive?  The script does not guess at a
         single definition of "inactive".  It emits every available signal as its
         own column - AccountDisabled, SkuAssigned (licensed or not), and
         DaysSinceLastUserAction - so the reviewer can filter on the definition
         that matters to them.  The Markdown summary defaults to counting a
         mailbox as inactive when the account is disabled.

      2. Who has access?  Access is granted through three independent mechanisms
         in Exchange Online and no single cmdlet returns all of them:

           FullAccess     Get-EXOMailboxPermission
           SendAs         Get-EXORecipientPermission
           SendOnBehalf   the GrantSendOnBehalfTo property of the mailbox

         All three are collected.  Inherited entries, NT AUTHORITY principals,
         orphaned raw SIDs, and the built-in administrative role groups are
         filtered out, because they are present on every mailbox and are not a
         business grant of access.

         Each grant records the trustee's recipient type.  A grant to a
         mail-enabled security group is a single row that represents many
         people; without the type column the report silently understates who can
         read the mailbox.  Use -ExpandGroupMember to resolve those groups to
         their members.

      3. When was it last touched?  Both the directory timestamps
         (WhenChangedUTC on the user object and on the mailbox) and the activity
         timestamps (LastLogonTime, LastUserActionTime from mailbox statistics)
         are captured.  See the NOTES section for why the directory timestamps
         are the weaker of the two for this project.

    Three files are written to the output directory:

      Mailbox-Inventory-<timestamp>.csv   one row per mailbox
      Mailbox-Access-<timestamp>.csv      one row per access grant
      Mailbox-Inventory-<timestamp>.md    summary report and caveats

    The script changes nothing.  It issues only Get- cmdlets.

.PARAMETER AuthMode
    How to authenticate to Exchange Online.  Matches the pattern used by
    Invoke-M365OffboardingHold.ps1 in this folder.

    Interactive     - Manual run from an admin workstation.  Requires -AdminUpn.
    Certificate     - Unattended on a Windows host.  Requires -Organization,
                      -AppId, and -CertificateThumbprint.
    ManagedIdentity - Azure Automation.  Requires -Organization.  No secrets.

.PARAMETER AdminUpn
    The administrator UPN to sign in with when -AuthMode is Interactive.

.PARAMETER Organization
    The tenant onmicrosoft.com domain, for example contoso.onmicrosoft.com.
    Required for Certificate and ManagedIdentity authentication.

.PARAMETER AppId
    The application (client) ID of the Entra ID app registration used for
    certificate authentication.

.PARAMETER CertificateThumbprint
    Thumbprint of the certificate in the local certificate store that matches the
    app registration used for certificate authentication.

.PARAMETER MailboxType
    Which mailbox types to inventory.  Defaults to all four - UserMailbox,
    SharedMailbox, RoomMailbox, and EquipmentMailbox - so the report answers
    "what kind of mailbox is this" for the whole tenant rather than assuming the
    answer up front.  Narrow it to shorten a run: passing only SharedMailbox
    reproduces the original scope of this script.

.PARAMETER OutputPath
    Directory the CSV and Markdown files are written to.  Defaults to the
    cleanup-project folder beside this script.

.PARAMETER InactiveDayThreshold
    Number of days without user action after which a mailbox is flagged as stale
    in the summary report.  Defaults to 180.

.PARAMETER MaxMailboxCount
    Stop after this many mailboxes.  Use for a quick sample run against a large
    tenant before committing to a full pass.  Zero, the default, means no limit.

.PARAMETER ExpandGroupMember
    Resolve access grants made to a group into one row per group member in the
    access CSV.  The original group row is retained and the expanded rows are
    marked with the group they came from.  Off by default because it can
    multiply the row count considerably.

.PARAMETER SkipStatistic
    Skip the per-mailbox Get-EXOMailboxStatistics call.  Much faster, but
    LastLogonTime, LastUserActionTime, item count, and mailbox size are left
    empty.  Not recommended - those are the most useful columns for scoping.

.EXAMPLE
    .\Get-SharedMailboxInventory.ps1 -AuthMode Interactive -AdminUpn "admin@contoso.com"

    Signs in interactively and writes a full inventory to the cleanup-project
    folder.

.EXAMPLE
    .\Get-SharedMailboxInventory.ps1 -AuthMode Interactive -AdminUpn "admin@contoso.com" -MaxMailboxCount 25 -Verbose

    Samples the first 25 shared mailboxes with progress detail, to confirm the
    output shape before running against the whole tenant.

.EXAMPLE
    .\Get-SharedMailboxInventory.ps1 -AuthMode Certificate -Organization "contoso.onmicrosoft.com" -AppId "00000000-0000-0000-0000-000000000000" -CertificateThumbprint "ABC123"

    Unattended run from a scheduled task on a Windows host.

.EXAMPLE
    .\Get-SharedMailboxInventory.ps1 -AuthMode Interactive -AdminUpn "admin@contoso.com" -ExpandGroupMember

    Resolves group-based access grants down to individual members.

.INPUTS
    None.  This script does not accept pipeline input.

.OUTPUTS
    System.Management.Automation.PSCustomObject

    One object per shared mailbox is written to the pipeline, carrying the same
    properties as the inventory CSV.

.NOTES
    Name:    Get-SharedMailboxInventory.ps1
    Version: 1.3.0
    Author:  Infrastructure Team
    Purpose: Mailbox cleanup project - scoping pass

    Change history
    1.3.0 - Install the ExchangeOnlineManagement module from the PowerShell Gallery
            on demand (CurrentUser scope) instead of throwing when it is missing.
    1.2.0 - Fixed a Windows PowerShell 5.1 runtime failure: a bare (if ...) in an
            argument position parses as a call to a command named 'if'.
          - Stopped reporting missing data as a finding. StatisticsState and
            AccessDataState distinguish a failed call from a genuine absence, and
            anything not fully collected is excluded from the counts and from the
            cleanup candidate list.
          - Added LastActivityTime and ActivitySource. Exchange Online returns no
            LastUserActionTime for shared mailboxes, so scoping on it alone
            reported every shared mailbox in the tenant as never opened.
          - Excluded room and equipment mailboxes from the cleanup candidate set
            and gave them their own section.
    1.1.0 - Added -MailboxType and widened the default scope to every mailbox
            type. Mailbox type is now reported and broken out in the summary,
            because Microsoft Graph cannot distinguish shared from room or
            equipment mailboxes and treating a bookable resource as an idle
            shared mailbox is the expensive mistake in this project.
    1.0.0 - Initial release.

    Requirements
      ExchangeOnlineManagement 3.2.0 or later (3.10.1 tested)
      Exchange Online role: View-Only Recipients, or Global Reader
      Windows PowerShell 5.1 or PowerShell 7

    Reading the timestamps

      WhenChangedUTC is the directory's last-write timestamp.  If this tenant has
      run Invoke-M365OffboardingHold.ps1 over these mailboxes then that script's
      own writes bumped WhenChangedUTC on every account it touched, and the
      column will make long-dormant mailboxes look recently modified.  It is
      reported because it was asked for, but LastUserActionTime is the column to
      scope on.

      LastLogonTime and LastUserActionTime on a shared mailbox reflect access by
      a delegate, not by the departed employee.  A shared mailbox with recent
      activity is in active use by whoever holds the FullAccess grant.

      An empty LastUserActionTime usually means the mailbox has never been opened
      since it was converted, which is the strongest possible cleanup signal.

    Shared and inactive are different states

      A shared mailbox has a live user account with sign-in normally blocked.  An
      inactive mailbox is one held for compliance after its user account was
      deleted; it has no account at all and cannot be a shared mailbox.  The two
      states are mutually exclusive.  Both are captured, and the
      IsInactiveMailbox column distinguishes them.
#>

[CmdletBinding()]
param (
    [Parameter(Mandatory = $false)]
    [ValidateSet('Interactive', 'Certificate', 'ManagedIdentity')]
    [string]$AuthMode = 'Interactive',

    [Parameter(Mandatory = $false)]
    [ValidateNotNullOrEmpty()]
    [string]$AdminUpn,

    [Parameter(Mandatory = $false)]
    [ValidateNotNullOrEmpty()]
    [string]$Organization,

    [Parameter(Mandatory = $false)]
    [ValidateNotNullOrEmpty()]
    [string]$AppId,

    [Parameter(Mandatory = $false)]
    [ValidateNotNullOrEmpty()]
    [string]$CertificateThumbprint,

    [Parameter(Mandatory = $false)]
    [ValidateSet('UserMailbox', 'SharedMailbox', 'RoomMailbox', 'EquipmentMailbox')]
    [string[]]$MailboxType = @('UserMailbox', 'SharedMailbox', 'RoomMailbox', 'EquipmentMailbox'),

    [Parameter(Mandatory = $false)]
    [ValidateNotNullOrEmpty()]
    # $PSScriptRoot is empty when the script is launched with -File and a relative
    # path under Windows PowerShell 5.1, so fall back to the working directory.
    [string]$OutputPath = (Join-Path -Path $(if ($PSScriptRoot) { $PSScriptRoot } else { (Get-Location).Path }) -ChildPath 'cleanup-project'),

    [Parameter(Mandatory = $false)]
    [ValidateRange(1, 3650)]
    [int]$InactiveDayThreshold = 180,

    [Parameter(Mandatory = $false)]
    [ValidateRange(0, 100000)]
    [int]$MaxMailboxCount = 0,

    [Parameter(Mandatory = $false)]
    [switch]$ExpandGroupMember,

    [Parameter(Mandatory = $false)]
    [switch]$SkipStatistic
)

begin {
    $ErrorActionPreference = 'Stop'
    $script:Timestamp = Get-Date -Format 'yyyyMMddHHmm'
    $script:ConnectedHere = $false

    #region Configuration Variables

    # Principals that appear on every mailbox and never represent a business
    # grant of access.  Compared case-insensitively against the trustee string.
    $script:ExcludedTrustee = @(
        'NT AUTHORITY\SELF',
        'NT AUTHORITY\SYSTEM',
        'NT AUTHORITY\NETWORK SERVICE',
        'NT AUTHORITY\LOCAL SERVICE',
        'NT AUTHORITY\ANONYMOUS LOGON',
        'NT AUTHORITY\BATCH',
        'NT AUTHORITY\INTERACTIVE',
        'NT AUTHORITY\Authenticated Users',
        'Everyone'
    )

    # Built-in Exchange Online administrative role groups.  Their membership is
    # an administrative fact, not a delegate relationship for this mailbox.
    $script:ExcludedRoleGroup = @(
        'Organization Management',
        'Exchange Servers',
        'Exchange Trusted Subsystem',
        'Managed Availability Servers',
        'Public Folder Management',
        'Discovery Management',
        'Delegated Setup',
        'Domain Admins',
        'Enterprise Admins',
        'Administrator'
    )

    # Recipient types treated as a group, meaning one grant covers many people.
    $script:GroupRecipientType = @(
        'MailUniversalSecurityGroup',
        'MailUniversalDistributionGroup',
        'MailNonUniversalGroup',
        'DynamicDistributionGroup',
        'GroupMailbox',
        'RoleGroup'
    )

    #endregion Configuration Variables

    function Write-Log {
        <#
        .SYNOPSIS
            Emits a timestamped log line on the appropriate PowerShell stream.

        .DESCRIPTION
            Routes INFO to the information stream, WARNING to the warning stream,
            ERROR to the error stream, and VERBOSE to the verbose stream, so the
            caller controls visibility with the standard preference variables and
            nothing is written directly to the host.

        .PARAMETER Message
            The text to log.

        .PARAMETER Level
            Severity of the message.  INFO, WARNING, ERROR, or VERBOSE.

        .EXAMPLE
            Write-Log -Message 'Connected to Exchange Online.' -Level 'INFO'

        .INPUTS
            None.

        .OUTPUTS
            None.
        #>
        [CmdletBinding()]
        param (
            [Parameter(Mandatory = $true)]
            [ValidateNotNullOrEmpty()]
            [string]$Message,

            [Parameter(Mandatory = $false)]
            [ValidateSet('INFO', 'WARNING', 'ERROR', 'VERBOSE')]
            [string]$Level = 'INFO'
        )

        $line = '[{0}] [{1}] {2}' -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $Level, $Message

        switch ($Level) {
            'ERROR' {
                Write-Error -Message $line -ErrorAction Continue
            }
            'WARNING' {
                Write-Warning -Message $line
            }
            'VERBOSE' {
                Write-Verbose -Message $line
            }
            default {
                Write-Information -MessageData $line -InformationAction Continue
            }
        }
    }

    function Initialize-RequiredModule {
        <#
        .SYNOPSIS
            Ensures each required module is installed, then imports it.

        .DESCRIPTION
            Installs any missing module from the PowerShell Gallery in the
            CurrentUser scope, then imports it in the order supplied, so a fresh
            host can run the script unattended without a manual Install-Module
            step first.

        .PARAMETER Name
            One or more module names to ensure are present and imported.

        .PARAMETER Scope
            Install scope. CurrentUser by default.

        .EXAMPLE
            Initialize-RequiredModule -Name 'ExchangeOnlineManagement'

        .INPUTS
            None.

        .OUTPUTS
            None.
        #>
        [CmdletBinding()]
        param (
            [Parameter(Mandatory = $true)]
            [string[]]$Name,

            [Parameter(Mandatory = $false)]
            [ValidateSet('CurrentUser', 'AllUsers')]
            [string]$Scope = 'CurrentUser'
        )

        # PowerShellGet talks to the Gallery over TLS 1.2; 5.1 negotiates an older
        # protocol by default and the request is rejected before any download.
        if ([System.Net.ServicePointManager]::SecurityProtocol -notmatch 'Tls12') {
            [System.Net.ServicePointManager]::SecurityProtocol =
            [System.Net.ServicePointManager]::SecurityProtocol -bor [System.Net.SecurityProtocolType]::Tls12
        }

        foreach ($moduleName in $Name) {
            if (-not (Get-Module -Name $moduleName -ListAvailable)) {
                Write-Log -Message ("Module '{0}' is not installed; installing from the PowerShell Gallery (scope {1})." -f $moduleName, $Scope) -Level 'WARNING'

                if (-not (Get-PackageProvider -Name NuGet -ListAvailable -ErrorAction SilentlyContinue)) {
                    Install-PackageProvider -Name NuGet -MinimumVersion '2.8.5.201' -Scope $Scope -Force -ErrorAction Stop | Out-Null
                }

                try {
                    Install-Module -Name $moduleName -Scope $Scope -Force -AllowClobber -ErrorAction Stop
                } catch {
                    throw ("Failed to install required module '{0}' from the PowerShell Gallery: {1}. Install it manually with: Install-Module {0} -Scope {2}" -f $moduleName, $_.Exception.Message, $Scope)
                }

                Write-Log -Message ("Module '{0}' installed." -f $moduleName) -Level 'INFO'
            }

            Import-Module -Name $moduleName -ErrorAction Stop
        }
    }

    function Connect-InventorySession {
        <#
        .SYNOPSIS
            Opens an Exchange Online session using the selected authentication mode.

        .DESCRIPTION
            Reuses an existing connected session when one is present, so repeated
            runs in the same shell do not trigger another sign-in prompt.  Returns
            $true when this call created the connection, so the caller knows
            whether it owns the disconnect.

        .PARAMETER Mode
            Interactive, Certificate, or ManagedIdentity.

        .PARAMETER UserPrincipalName
            Administrator UPN for interactive sign-in.

        .PARAMETER TenantDomain
            The onmicrosoft.com organization domain.

        .PARAMETER ApplicationId
            App registration client ID for certificate authentication.

        .PARAMETER Thumbprint
            Certificate thumbprint for certificate authentication.

        .EXAMPLE
            Connect-InventorySession -Mode 'Interactive' -UserPrincipalName 'admin@contoso.com'

        .INPUTS
            None.

        .OUTPUTS
            System.Boolean
        #>
        [CmdletBinding()]
        [OutputType([bool])]
        param (
            [Parameter(Mandatory = $true)]
            [ValidateSet('Interactive', 'Certificate', 'ManagedIdentity')]
            [string]$Mode,

            [Parameter(Mandatory = $false)]
            [string]$UserPrincipalName,

            [Parameter(Mandatory = $false)]
            [string]$TenantDomain,

            [Parameter(Mandatory = $false)]
            [string]$ApplicationId,

            [Parameter(Mandatory = $false)]
            [string]$Thumbprint
        )

        $existing = Get-ConnectionInformation -ErrorAction SilentlyContinue |
            Where-Object { $_.State -eq 'Connected' }

        if ($existing) {
            Write-Log -Message ('Reusing existing Exchange Online session for {0}.' -f $existing[0].UserPrincipalName) -Level 'INFO'
            return $false
        }

        switch ($Mode) {
            'ManagedIdentity' {
                if (-not $TenantDomain) {
                    throw '-Organization is required when -AuthMode is ManagedIdentity.'
                }

                Write-Log -Message 'Connecting to Exchange Online with a managed identity.' -Level 'INFO'
                Connect-ExchangeOnline -ManagedIdentity -Organization $TenantDomain -ShowBanner:$false
            }
            'Certificate' {
                foreach ($required in @('TenantDomain', 'ApplicationId', 'Thumbprint')) {
                    if (-not (Get-Variable -Name $required -ValueOnly -ErrorAction SilentlyContinue)) {
                        throw ('-Organization, -AppId, and -CertificateThumbprint are all required when -AuthMode is Certificate. Missing: {0}.' -f $required)
                    }
                }

                Write-Log -Message 'Connecting to Exchange Online with certificate authentication.' -Level 'INFO'
                Connect-ExchangeOnline -AppId $ApplicationId -CertificateThumbprint $Thumbprint `
                    -Organization $TenantDomain -ShowBanner:$false
            }
            default {
                if (-not $UserPrincipalName) {
                    throw '-AdminUpn is required when -AuthMode is Interactive.'
                }

                Write-Log -Message ('Connecting to Exchange Online interactively as {0}.' -f $UserPrincipalName) -Level 'INFO'
                Connect-ExchangeOnline -UserPrincipalName $UserPrincipalName -ShowBanner:$false
            }
        }

        return $true
    }

    function Invoke-WithRetry {
        <#
        .SYNOPSIS
            Runs a script block, retrying on transient Exchange Online throttling.

        .DESCRIPTION
            Exchange Online throttles per-mailbox cmdlets over long runs.  This
            wrapper retries with a linear backoff and returns $null after the
            final attempt so a single bad mailbox never aborts the whole
            inventory.

        .PARAMETER ScriptBlock
            The code to execute.

        .PARAMETER Description
            Text used in the warning message when every attempt fails.

        .PARAMETER MaxAttempt
            Total number of attempts, including the first.

        .EXAMPLE
            Invoke-WithRetry -ScriptBlock { Get-EXOMailboxPermission -Identity $id } -Description 'permissions'

        .INPUTS
            None.

        .OUTPUTS
            System.Object
        #>
        [CmdletBinding()]
        [OutputType([object])]
        param (
            [Parameter(Mandatory = $true)]
            [scriptblock]$ScriptBlock,

            [Parameter(Mandatory = $true)]
            [string]$Description,

            [Parameter(Mandatory = $false)]
            [ValidateRange(1, 10)]
            [int]$MaxAttempt = 3
        )

        for ($attempt = 1; $attempt -le $MaxAttempt; $attempt++) {
            try {
                return & $ScriptBlock
            } catch {
                if ($attempt -eq $MaxAttempt) {
                    Write-Log -Message ('Gave up on {0} after {1} attempts: {2}' -f $Description, $MaxAttempt, $_.Exception.Message) -Level 'WARNING'
                    return $null
                }

                Start-Sleep -Seconds (5 * $attempt)
            }
        }
    }

    function Get-TrusteeDetail {
        <#
        .SYNOPSIS
            Resolves a trustee string to its recipient type, with caching.

        .DESCRIPTION
            Permission cmdlets return a trustee as a display name, UPN, or SMTP
            address with no type information.  This looks the trustee up once and
            caches the answer, so a delegate that appears on fifty mailboxes costs
            one lookup rather than fifty.

        .PARAMETER Trustee
            The trustee string as returned by the permission cmdlet.

        .PARAMETER Cache
            Hashtable used to memoise lookups across calls.

        .EXAMPLE
            Get-TrusteeDetail -Trustee 'helpdesk@contoso.com' -Cache $lookup

        .INPUTS
            None.

        .OUTPUTS
            System.Management.Automation.PSCustomObject
        #>
        [CmdletBinding()]
        [OutputType([PSCustomObject])]
        param (
            [Parameter(Mandatory = $true)]
            [string]$Trustee,

            [Parameter(Mandatory = $true)]
            [hashtable]$Cache
        )

        $key = $Trustee.ToLowerInvariant()

        if ($Cache.ContainsKey($key)) {
            return $Cache[$key]
        }

        $recipient = Invoke-WithRetry -Description ('recipient lookup for {0}' -f $Trustee) -ScriptBlock {
            Get-EXORecipient -Identity $Trustee -ErrorAction Stop |
                Select-Object -First 1
        }

        if ($recipient) {
            $detail = [PSCustomObject]@{
                Trustee = $Trustee
                TrusteeDisplayName = $recipient.DisplayName
                TrusteeSmtp = [string]$recipient.PrimarySmtpAddress
                TrusteeType = [string]$recipient.RecipientTypeDetails
                TrusteeIsGroup = ($script:GroupRecipientType -contains [string]$recipient.RecipientTypeDetails)
                Resolved = $true
            }
        } else {
            $detail = [PSCustomObject]@{
                Trustee = $Trustee
                TrusteeDisplayName = $Trustee
                TrusteeSmtp = ''
                TrusteeType = 'Unresolved'
                TrusteeIsGroup = $false
                Resolved = $false
            }
        }

        $Cache[$key] = $detail
        return $detail
    }

    function Test-TrusteeRelevant {
        <#
        .SYNOPSIS
            Decides whether a trustee represents a real grant of access.

        .DESCRIPTION
            Filters out the service principals, orphaned raw SIDs, and built-in
            administrative role groups that appear on every mailbox.  Without this
            filter the access report is dominated by rows that mean nothing.

        .PARAMETER Trustee
            The trustee string to evaluate.

        .EXAMPLE
            Test-TrusteeRelevant -Trustee 'NT AUTHORITY\SELF'

        .INPUTS
            None.

        .OUTPUTS
            System.Boolean
        #>
        [CmdletBinding()]
        [OutputType([bool])]
        param (
            [Parameter(Mandatory = $true)]
            [AllowEmptyString()]
            [string]$Trustee
        )

        if ([string]::IsNullOrWhiteSpace($Trustee)) {
            return $false
        }

        if ($script:ExcludedTrustee -contains $Trustee) {
            return $false
        }

        foreach ($group in $script:ExcludedRoleGroup) {
            if ($Trustee -eq $group -or $Trustee -like ('*\{0}' -f $group)) {
                return $false
            }
        }

        # Orphaned grants left behind by a deleted principal show up as a raw SID.
        if ($Trustee -match '^S-1-5-') {
            return $false
        }

        if ($Trustee -like 'NT AUTHORITY\*') {
            return $false
        }

        return $true
    }

    function ConvertTo-Megabyte {
        <#
        .SYNOPSIS
            Converts an Exchange Online size string to a number of megabytes.

        .DESCRIPTION
            TotalItemSize is returned as text such as "1.523 GB (1,635,281,408
            bytes)".  This extracts the byte count and converts it, returning
            $null when the value cannot be parsed so an unknown size is never
            reported as zero.

        .PARAMETER SizeText
            The raw size string from Get-EXOMailboxStatistics.

        .EXAMPLE
            ConvertTo-Megabyte -SizeText '1.523 GB (1,635,281,408 bytes)'

        .INPUTS
            None.

        .OUTPUTS
            System.Nullable[System.Double]
        #>
        [CmdletBinding()]
        [OutputType([double])]
        param (
            [Parameter(Mandatory = $false)]
            [AllowNull()]
            [AllowEmptyString()]
            [string]$SizeText
        )

        if ([string]::IsNullOrWhiteSpace($SizeText)) {
            return $null
        }

        if ($SizeText -match '\(([\d,\.]+)\s*bytes\)') {
            $digits = $Matches[1] -replace '[,\.]', ''
            $bytes = 0L

            if ([long]::TryParse($digits, [ref]$bytes)) {
                return [math]::Round($bytes / 1MB, 2)
            }
        }

        return $null
    }

    function Get-DaySince {
        <#
        .SYNOPSIS
            Returns whole days elapsed since a timestamp.

        .DESCRIPTION
            Returns $null rather than a misleading zero when the timestamp is
            absent, so "never used" and "used today" are distinguishable in the
            report.

        .PARAMETER Timestamp
            The point in time to measure from.

        .EXAMPLE
            Get-DaySince -Timestamp $mailbox.WhenChangedUTC

        .INPUTS
            None.

        .OUTPUTS
            System.Nullable[System.Int32]
        #>
        [CmdletBinding()]
        [OutputType([int])]
        param (
            [Parameter(Mandatory = $false)]
            [AllowNull()]
            [object]$Timestamp
        )

        if ($null -eq $Timestamp -or $Timestamp -eq '') {
            return $null
        }

        try {
            $parsed = [datetime]$Timestamp
        } catch {
            return $null
        }

        return [int]([datetime]::UtcNow - $parsed.ToUniversalTime()).TotalDays
    }
}

process {
    try {
        Initialize-RequiredModule -Name 'ExchangeOnlineManagement'

        if (-not (Test-Path -Path $OutputPath)) {
            New-Item -Path $OutputPath -ItemType Directory -Force | Out-Null
            Write-Log -Message ('Created output directory {0}.' -f $OutputPath) -Level 'INFO'
        }

        $script:ConnectedHere = Connect-InventorySession -Mode $AuthMode -UserPrincipalName $AdminUpn `
            -TenantDomain $Organization -ApplicationId $AppId -Thumbprint $CertificateThumbprint

        #region Collect mailboxes

        $mailboxProperty = @(
            'DisplayName', 'UserPrincipalName', 'PrimarySmtpAddress', 'Alias',
            'RecipientTypeDetails', 'ExchangeGuid', 'ExternalDirectoryObjectId',
            'WhenCreatedUTC', 'WhenChangedUTC', 'IsInactiveMailbox', 'IsDirSynced',
            'LitigationHoldEnabled', 'LitigationHoldDate', 'LitigationHoldDuration',
            'LitigationHoldOwner', 'InPlaceHolds', 'RetentionPolicy',
            'ArchiveStatus', 'ArchiveGuid', 'HiddenFromAddressListsEnabled',
            'GrantSendOnBehalfTo', 'ForwardingAddress', 'ForwardingSmtpAddress',
            'DeliverToMailboxAndForward', 'AccountDisabled'
        )

        Write-Log -Message ('Enumerating mailboxes of type: {0}.' -f ($MailboxType -join ', ')) -Level 'INFO'

        $sharedMailbox = @(Get-EXOMailbox -RecipientTypeDetails $MailboxType -ResultSize Unlimited -Properties $mailboxProperty)
        Write-Log -Message ('Found {0} mailboxes.' -f $sharedMailbox.Count) -Level 'INFO'

        Write-Log -Message 'Enumerating inactive mailboxes (accounts already deleted, retained on hold).' -Level 'INFO'

        $inactiveMailbox = @(Invoke-WithRetry -Description 'inactive mailbox enumeration' -ScriptBlock {
                Get-EXOMailbox -InactiveMailboxOnly -ResultSize Unlimited -Properties $mailboxProperty -ErrorAction Stop
            })

        Write-Log -Message ('Found {0} inactive mailboxes.' -f $inactiveMailbox.Count) -Level 'INFO'

        $allMailbox = @($sharedMailbox) + @($inactiveMailbox) | Where-Object { $null -ne $_ }

        if ($MaxMailboxCount -gt 0 -and $allMailbox.Count -gt $MaxMailboxCount) {
            Write-Log -Message ('Limiting this run to the first {0} of {1} mailboxes.' -f $MaxMailboxCount, $allMailbox.Count) -Level 'WARNING'
            $allMailbox = $allMailbox | Select-Object -First $MaxMailboxCount
        }

        if ($allMailbox.Count -eq 0) {
            Write-Log -Message 'No shared or inactive mailboxes found. Nothing to report.' -Level 'WARNING'
            return
        }

        #endregion Collect mailboxes

        #region Collect directory state in bulk

        # One bulk call rather than one call per mailbox.  Get-User carries the
        # account state and licence assignment that Get-EXOMailbox does not.
        Write-Log -Message 'Retrieving user account state in bulk.' -Level 'INFO'

        $userLookup = @{}

        $userProperty = @(
            'UserPrincipalName', 'ExternalDirectoryObjectId', 'AccountDisabled',
            'SkuAssigned', 'WhenChangedUTC', 'WhenCreatedUTC', 'Department', 'Title', 'Company'
        )

        # Scoped to the same mailbox types being inventoried rather than the whole
        # directory. An inactive mailbox has no user object at all, so nothing is
        # lost by the filter.
        $bulkUser = Invoke-WithRetry -Description 'bulk user enumeration' -ScriptBlock {
            Get-User -ResultSize Unlimited -RecipientTypeDetails $MailboxType -ErrorAction Stop |
                Select-Object -Property $userProperty
        }

        foreach ($user in @($bulkUser)) {
            if ($user.ExternalDirectoryObjectId) {
                $userLookup[[string]$user.ExternalDirectoryObjectId] = $user
            }

            if ($user.UserPrincipalName) {
                $userLookup[([string]$user.UserPrincipalName).ToLowerInvariant()] = $user
            }
        }

        Write-Log -Message ('Cached directory state for {0} accounts.' -f @($bulkUser).Count) -Level 'INFO'

        #endregion Collect directory state in bulk

        #region Per-mailbox detail

        $trusteeCache = @{}
        $accessRecord = New-Object -TypeName System.Collections.Generic.List[PSObject]
        $inventoryRecord = New-Object -TypeName System.Collections.Generic.List[PSObject]
        $index = 0

        foreach ($mailbox in $allMailbox) {
            $index++
            $identity = [string]$mailbox.ExchangeGuid

            if ([string]::IsNullOrWhiteSpace($identity) -or $identity -eq '00000000-0000-0000-0000-000000000000') {
                $identity = [string]$mailbox.PrimarySmtpAddress
            }

            $percent = [int](($index / $allMailbox.Count) * 100)
            Write-Progress -Activity 'Shared mailbox inventory' `
                -Status ('{0} of {1}: {2}' -f $index, $allMailbox.Count, $mailbox.PrimarySmtpAddress) `
                -PercentComplete $percent

            # Directory state
            $user = $null

            if ($mailbox.ExternalDirectoryObjectId -and $userLookup.ContainsKey([string]$mailbox.ExternalDirectoryObjectId)) {
                $user = $userLookup[[string]$mailbox.ExternalDirectoryObjectId]
            } elseif ($mailbox.UserPrincipalName -and $userLookup.ContainsKey(([string]$mailbox.UserPrincipalName).ToLowerInvariant())) {
                $user = $userLookup[([string]$mailbox.UserPrincipalName).ToLowerInvariant()]
            }

            # Mailbox statistics.  The collection state is tracked separately from
            # the values, because "we did not ask", "the call failed", and "Exchange
            # returned nothing" are three different facts and only the third one
            # says anything about the mailbox.
            $statistic = $null
            $statisticState = 'Collected'

            if ($SkipStatistic) {
                $statisticState = 'NotCollected'
            } else {
                $statistic = Invoke-WithRetry -Description ('statistics for {0}' -f $mailbox.PrimarySmtpAddress) -ScriptBlock {
                    Get-EXOMailboxStatistics -Identity $identity -Properties LastLogonTime, LastUserActionTime -ErrorAction Stop
                }

                if ($null -eq $statistic) {
                    $statisticState = 'CollectionFailed'
                }
            }

            # FullAccess.  Every mailbox carries at least NT AUTHORITY\SELF, so a
            # null return means the call failed rather than that no grant exists.
            $fullAccess = @()
            $accessState = 'Collected'

            $rawFullAccess = Invoke-WithRetry -Description ('FullAccess permissions for {0}' -f $mailbox.PrimarySmtpAddress) -ScriptBlock {
                Get-EXOMailboxPermission -Identity $identity -ErrorAction Stop
            }

            if ($null -eq $rawFullAccess) {
                $accessState = 'CollectionFailed'
            }

            foreach ($entry in @($rawFullAccess)) {
                if ($null -eq $entry) {
                    continue
                }

                if ($entry.IsInherited) {
                    continue
                }

                if ($entry.Deny) {
                    continue
                }

                if (-not (Test-TrusteeRelevant -Trustee ([string]$entry.User))) {
                    continue
                }

                if (($entry.AccessRights -join ',') -notmatch 'FullAccess') {
                    continue
                }

                $fullAccess += [PSCustomObject]@{
                    Trustee = [string]$entry.User
                    Rights = ($entry.AccessRights -join ';')
                }
            }

            # SendAs
            $sendAs = @()

            $rawSendAs = Invoke-WithRetry -Description ('SendAs permissions for {0}' -f $mailbox.PrimarySmtpAddress) -ScriptBlock {
                Get-EXORecipientPermission -Identity $identity -ErrorAction Stop
            }

            if ($null -eq $rawSendAs) {
                $accessState = 'CollectionFailed'
            }

            foreach ($entry in @($rawSendAs)) {
                if ($null -eq $entry) {
                    continue
                }

                if ($entry.IsInherited) {
                    continue
                }

                if ([string]$entry.AccessControlType -eq 'Deny') {
                    continue
                }

                if (-not (Test-TrusteeRelevant -Trustee ([string]$entry.Trustee))) {
                    continue
                }

                $sendAs += [PSCustomObject]@{
                    Trustee = [string]$entry.Trustee
                    Rights = ($entry.AccessRights -join ';')
                }
            }

            # SendOnBehalf
            $sendOnBehalf = @()

            foreach ($entry in @($mailbox.GrantSendOnBehalfTo)) {
                if ($null -eq $entry) {
                    continue
                }

                $name = [string]$entry

                # The directory returns this as a distinguished name; the leaf is
                # the only part a reader can act on.
                if ($name -match '/cn=([^/]+)$') {
                    $name = $Matches[1]
                }

                if (-not (Test-TrusteeRelevant -Trustee $name)) {
                    continue
                }

                $sendOnBehalf += [PSCustomObject]@{
                    Trustee = $name
                    Rights = 'SendOnBehalf'
                }
            }

            # Flatten every grant into the access list
            $grantSet = @(
                [PSCustomObject]@{ Type = 'FullAccess'; Items = $fullAccess },
                [PSCustomObject]@{ Type = 'SendAs'; Items = $sendAs },
                [PSCustomObject]@{ Type = 'SendOnBehalf'; Items = $sendOnBehalf }
            )

            foreach ($set in $grantSet) {
                foreach ($grant in $set.Items) {
                    $detail = Get-TrusteeDetail -Trustee $grant.Trustee -Cache $trusteeCache

                    $accessRecord.Add([PSCustomObject]@{
                            MailboxDisplayName = [string]$mailbox.DisplayName
                            MailboxUserPrincipalName = [string]$mailbox.UserPrincipalName
                            MailboxPrimarySmtpAddress = [string]$mailbox.PrimarySmtpAddress
                            MailboxType = [string]$mailbox.RecipientTypeDetails
                            AccessType = $set.Type
                            Trustee = $grant.Trustee
                            TrusteeDisplayName = $detail.TrusteeDisplayName
                            TrusteeSmtpAddress = $detail.TrusteeSmtp
                            TrusteeRecipientType = $detail.TrusteeType
                            TrusteeIsGroup = $detail.TrusteeIsGroup
                            AccessRights = $grant.Rights
                            ExpandedFromGroup = ''
                        })

                    if ($ExpandGroupMember -and $detail.TrusteeIsGroup) {
                        $member = Invoke-WithRetry -Description ('group expansion for {0}' -f $grant.Trustee) -ScriptBlock {
                            Get-DistributionGroupMember -Identity $grant.Trustee -ResultSize Unlimited -ErrorAction Stop
                        }

                        foreach ($person in @($member)) {
                            if ($null -eq $person) {
                                continue
                            }

                            $accessRecord.Add([PSCustomObject]@{
                                    MailboxDisplayName = [string]$mailbox.DisplayName
                                    MailboxUserPrincipalName = [string]$mailbox.UserPrincipalName
                                    MailboxPrimarySmtpAddress = [string]$mailbox.PrimarySmtpAddress
                                    MailboxType = [string]$mailbox.RecipientTypeDetails
                                    AccessType = $set.Type
                                    Trustee = [string]$person.PrimarySmtpAddress
                                    TrusteeDisplayName = [string]$person.DisplayName
                                    TrusteeSmtpAddress = [string]$person.PrimarySmtpAddress
                                    TrusteeRecipientType = [string]$person.RecipientTypeDetails
                                    TrusteeIsGroup = $false
                                    AccessRights = $grant.Rights
                                    ExpandedFromGroup = $grant.Trustee
                                })
                        }
                    }
                }
            }

            # Build the inventory row
            $lastUserAction = $null
            $lastLogon = $null
            $itemCount = $null
            $sizeMb = $null

            if ($statistic) {
                $lastUserAction = $statistic.LastUserActionTime
                $lastLogon = $statistic.LastLogonTime
                $itemCount = $statistic.ItemCount
                $sizeMb = ConvertTo-Megabyte -SizeText ([string]$statistic.TotalItemSize)
            }

            # Exchange Online does not populate LastUserActionTime for shared
            # mailboxes - it comes back empty on every one of them - and Microsoft
            # documents the property as deprecated for Exchange Online.  Scoping on
            # it alone reports every shared mailbox as never opened, including ones
            # with gigabytes of mail and a delegate who logged in yesterday.
            # LastLogonTime is the fallback.  It is the weaker signal, because
            # background mailbox assistants can advance it, so the column that
            # produced the answer is recorded alongside it.
            $lastActivity = $null
            $activitySource = 'None'

            if ($lastUserAction) {
                $lastActivity = $lastUserAction
                $activitySource = 'LastUserActionTime'
            } elseif ($lastLogon) {
                $lastActivity = $lastLogon
                $activitySource = 'LastLogonTime'
            } elseif ($statisticState -ne 'Collected') {
                $activitySource = $statisticState
            }

            $accountDisabled = $null

            if ($user) {
                $accountDisabled = $user.AccountDisabled
            } elseif ($null -ne $mailbox.AccountDisabled) {
                $accountDisabled = $mailbox.AccountDisabled
            }

            # Precomputed rather than inlined. Windows PowerShell 5.1 treats a bare
            # (if ...) in an argument position as a call to a command named 'if',
            # which parses cleanly and then fails at runtime.
            $userWhenChanged = $null

            if ($user) {
                $userWhenChanged = $user.WhenChangedUTC
            }

            $row = [PSCustomObject]@{
                DisplayName = [string]$mailbox.DisplayName
                UserPrincipalName = [string]$mailbox.UserPrincipalName
                PrimarySmtpAddress = [string]$mailbox.PrimarySmtpAddress
                Alias = [string]$mailbox.Alias
                RecipientTypeDetails = [string]$mailbox.RecipientTypeDetails
                IsInactiveMailbox = [bool]$mailbox.IsInactiveMailbox
                AccountDisabled = $accountDisabled
                SkuAssigned = if ($user) { $user.SkuAssigned } else { $null }
                Department = if ($user) { [string]$user.Department } else { '' }
                Title = if ($user) { [string]$user.Title } else { '' }
                UserWhenChangedUTC = if ($user) { $user.WhenChangedUTC } else { $null }
                UserWhenCreatedUTC = if ($user) { $user.WhenCreatedUTC } else { $null }
                MailboxWhenChangedUTC = $mailbox.WhenChangedUTC
                MailboxWhenCreatedUTC = $mailbox.WhenCreatedUTC
                DaysSinceUserChanged = Get-DaySince -Timestamp $userWhenChanged
                LastLogonTime = $lastLogon
                LastUserActionTime = $lastUserAction
                DaysSinceLastUserAction = Get-DaySince -Timestamp $lastUserAction
                LastActivityTime = $lastActivity
                DaysSinceLastActivity = Get-DaySince -Timestamp $lastActivity
                ActivitySource = $activitySource
                StatisticsState = $statisticState
                AccessDataState = $accessState
                ItemCount = $itemCount
                TotalItemSizeMB = $sizeMb
                LitigationHoldEnabled = [bool]$mailbox.LitigationHoldEnabled
                LitigationHoldDate = $mailbox.LitigationHoldDate
                LitigationHoldDuration = [string]$mailbox.LitigationHoldDuration
                InPlaceHoldCount = @($mailbox.InPlaceHolds).Count
                RetentionPolicy = [string]$mailbox.RetentionPolicy
                ArchiveStatus = [string]$mailbox.ArchiveStatus
                HiddenFromAddressLists = [bool]$mailbox.HiddenFromAddressListsEnabled
                IsDirSynced = [bool]$mailbox.IsDirSynced
                ForwardingSmtpAddress = [string]$mailbox.ForwardingSmtpAddress
                DeliverToMailboxAndForward = [bool]$mailbox.DeliverToMailboxAndForward
                FullAccessCount = @($fullAccess).Count
                SendAsCount = @($sendAs).Count
                SendOnBehalfCount = @($sendOnBehalf).Count
                TotalDelegateCount = @($fullAccess).Count + @($sendAs).Count + @($sendOnBehalf).Count
                FullAccessTrustees = (@($fullAccess) | ForEach-Object { $_.Trustee }) -join '; '
                SendAsTrustees = (@($sendAs) | ForEach-Object { $_.Trustee }) -join '; '
                SendOnBehalfTrustees = (@($sendOnBehalf) | ForEach-Object { $_.Trustee }) -join '; '
            }

            $inventoryRecord.Add($row)
            Write-Output -InputObject $row
        }

        Write-Progress -Activity 'Shared mailbox inventory' -Completed

        #endregion Per-mailbox detail

        #region Write output

        $inventoryCsv = Join-Path -Path $OutputPath -ChildPath ('Mailbox-Inventory-{0}.csv' -f $script:Timestamp)
        $accessCsv = Join-Path -Path $OutputPath -ChildPath ('Mailbox-Access-{0}.csv' -f $script:Timestamp)
        $reportMd = Join-Path -Path $OutputPath -ChildPath ('Mailbox-Inventory-{0}.md' -f $script:Timestamp)

        $inventoryRecord | Export-Csv -Path $inventoryCsv -NoTypeInformation -Encoding UTF8
        Write-Log -Message ('Wrote {0} mailbox rows to {1}.' -f $inventoryRecord.Count, $inventoryCsv) -Level 'INFO'

        if ($accessRecord.Count -gt 0) {
            $accessRecord | Export-Csv -Path $accessCsv -NoTypeInformation -Encoding UTF8
        } else {
            # Still write the file, with headers only, so downstream tooling and
            # the reader can tell "no delegates" from "the script never ran".
            '"MailboxDisplayName","MailboxUserPrincipalName","MailboxPrimarySmtpAddress","MailboxType","AccessType","Trustee","TrusteeDisplayName","TrusteeSmtpAddress","TrusteeRecipientType","TrusteeIsGroup","AccessRights","ExpandedFromGroup"' |
                Set-Content -Path $accessCsv -Encoding UTF8
        }

        Write-Log -Message ('Wrote {0} access rows to {1}.' -f $accessRecord.Count, $accessCsv) -Level 'INFO'

        # Summary figures
        $sharedCount = @($inventoryRecord | Where-Object { -not $_.IsInactiveMailbox }).Count
        $inactiveCount = @($inventoryRecord | Where-Object { $_.IsInactiveMailbox }).Count
        $disabledCount = @($inventoryRecord | Where-Object { $_.AccountDisabled -eq $true }).Count
        $licensedCount = @($inventoryRecord | Where-Object { $_.SkuAssigned -eq $true }).Count
        $noDelegateCount = @($inventoryRecord | Where-Object { $_.TotalDelegateCount -eq 0 -and $_.AccessDataState -eq 'Collected' }).Count
        $neverUsedCount = @($inventoryRecord | Where-Object { $null -eq $_.LastActivityTime -and $_.StatisticsState -eq 'Collected' }).Count
        $holdCount = @($inventoryRecord | Where-Object { $_.LitigationHoldEnabled }).Count
        $groupGrantCount = @($accessRecord | Where-Object { $_.TrusteeIsGroup -eq $true -and $_.ExpandedFromGroup -eq '' }).Count

        # A room or equipment mailbox is a bookable resource. Idle is its normal
        # state and deleting one because nobody booked it this quarter is the
        # expensive mistake this project can make, so they are held out of the
        # candidate set entirely and reported on their own.
        $resourceType = @('RoomMailbox', 'EquipmentMailbox')
        $resourceMailbox = @($inventoryRecord | Where-Object { $resourceType -contains $_.RecipientTypeDetails })

        # Rows whose permission or statistics collection failed cannot be judged.
        # Counting them as "no delegate, never opened" is how a live mailbox ends
        # up on a deletion list because Exchange throttled one call.
        $incompleteMailbox = @($inventoryRecord | Where-Object {
                $_.AccessDataState -ne 'Collected' -or $_.StatisticsState -ne 'Collected'
            })

        $judgeable = @($inventoryRecord | Where-Object {
                $resourceType -notcontains $_.RecipientTypeDetails -and
                $_.AccessDataState -eq 'Collected' -and
                $_.StatisticsState -eq 'Collected'
            })

        $staleMailbox = @($judgeable | Where-Object {
                $null -eq $_.LastActivityTime -or $_.DaysSinceLastActivity -ge $InactiveDayThreshold
            })

        $cleanupCandidate = @($staleMailbox | Where-Object { $_.TotalDelegateCount -eq 0 })

        $totalSizeMb = ($inventoryRecord | Measure-Object -Property TotalItemSizeMB -Sum).Sum
        $candidateSizeMb = ($cleanupCandidate | Measure-Object -Property TotalItemSizeMB -Sum).Sum

        $markdown = New-Object -TypeName System.Text.StringBuilder

        [void]$markdown.AppendLine('# Mailbox Inventory and Access')
        [void]$markdown.AppendLine()
        [void]$markdown.AppendLine(('Generated {0} UTC by `Get-SharedMailboxInventory.ps1` v1.1.0.' -f (Get-Date -Format 'yyyy-MM-dd HH:mm')))
        [void]$markdown.AppendLine()
        [void]$markdown.AppendLine(('Mailbox types covered: {0}.' -f ($MailboxType -join ', ')))
        [void]$markdown.AppendLine()
        [void]$markdown.AppendLine('Scoping pass for the mailbox cleanup project. Read-only; nothing was changed.')
        [void]$markdown.AppendLine()

        [void]$markdown.AppendLine('## Mailboxes by type')
        [void]$markdown.AppendLine()
        [void]$markdown.AppendLine('This is Exchange Online''s own classification, not an inference. A room or')
        [void]$markdown.AppendLine('equipment mailbox is a bookable resource: idle is its normal state and it is')
        [void]$markdown.AppendLine('not a cleanup candidate on that basis alone.')
        [void]$markdown.AppendLine()
        [void]$markdown.AppendLine('| Type | Count | With delegates | No activity ever | Activity source |')
        [void]$markdown.AppendLine('|------|-------|----------------|------------------|-----------------|')

        foreach ($typeGroup in ($inventoryRecord | Group-Object -Property RecipientTypeDetails | Sort-Object -Property Count -Descending)) {
            $groupDelegated = @($typeGroup.Group | Where-Object { $_.TotalDelegateCount -gt 0 }).Count
            $groupNeverUsed = @($typeGroup.Group | Where-Object { $null -eq $_.LastActivityTime }).Count

            $groupSource = (@($typeGroup.Group | Group-Object -Property ActivitySource |
                        Sort-Object -Property Count -Descending |
                        ForEach-Object { '{0} ({1})' -f $_.Name, $_.Count }) -join ', ')

            [void]$markdown.AppendLine(('| {0} | {1} | {2} | {3} | {4} |' -f
                    $typeGroup.Name, $typeGroup.Count, $groupDelegated, $groupNeverUsed, $groupSource))
        }

        [void]$markdown.AppendLine()

        [void]$markdown.AppendLine('## Totals')
        [void]$markdown.AppendLine()
        [void]$markdown.AppendLine('| Measure | Count |')
        [void]$markdown.AppendLine('|---------|-------|')
        [void]$markdown.AppendLine(('| Mailboxes with a live user account | {0} |' -f $sharedCount))
        [void]$markdown.AppendLine(('| Inactive mailboxes (account already deleted) | {0} |' -f $inactiveCount))
        [void]$markdown.AppendLine(('| Backing account disabled | {0} |' -f $disabledCount))
        [void]$markdown.AppendLine(('| Still holding a licence | {0} |' -f $licensedCount))
        [void]$markdown.AppendLine(('| Litigation Hold enabled | {0} |' -f $holdCount))
        [void]$markdown.AppendLine(('| No delegate of any kind | {0} |' -f $noDelegateCount))
        [void]$markdown.AppendLine(('| No recorded activity of any kind | {0} |' -f $neverUsedCount))
        [void]$markdown.AppendLine(('| Room and equipment mailboxes, held out of the candidate set | {0} |' -f $resourceMailbox.Count))
        [void]$markdown.AppendLine(('| Incomplete collection, cannot be judged | {0} |' -f $incompleteMailbox.Count))
        [void]$markdown.AppendLine(('| Judgeable mailboxes | {0} |' -f $judgeable.Count))
        [void]$markdown.AppendLine(('| Idle {0}+ days or no activity | {1} |' -f $InactiveDayThreshold, $staleMailbox.Count))
        [void]$markdown.AppendLine(('| **Idle and nobody has access** | **{0}** |' -f $cleanupCandidate.Count))
        [void]$markdown.AppendLine(('| Access grants recorded | {0} |' -f $accessRecord.Count))
        [void]$markdown.AppendLine(('| Grants made to a group rather than a person | {0} |' -f $groupGrantCount))

        if ($null -ne $totalSizeMb) {
            [void]$markdown.AppendLine(('| Total mailbox data | {0} GB |' -f [math]::Round($totalSizeMb / 1024, 2)))
        }

        if ($null -ne $candidateSizeMb) {
            [void]$markdown.AppendLine(('| Data held by cleanup candidates | {0} GB |' -f [math]::Round($candidateSizeMb / 1024, 2)))
        }

        [void]$markdown.AppendLine()

        [void]$markdown.AppendLine('## Start here: idle with no delegate')
        [void]$markdown.AppendLine()
        [void]$markdown.AppendLine(('Nobody holds FullAccess, SendAs, or SendOnBehalf, and there has been no recorded activity for {0} days or more. Room and equipment mailboxes are excluded, and so is any mailbox whose data could not be collected in full. These are the safest mailboxes to review first - review, not delete.' -f $InactiveDayThreshold))
        [void]$markdown.AppendLine()

        if ($cleanupCandidate.Count -gt 0) {
            [void]$markdown.AppendLine('| Display name | Address | Type | Account disabled | Licensed | Last activity | Source | Size MB | Hold |')
            [void]$markdown.AppendLine('|---|---|---|---|---|---|---|---|---|')

            foreach ($item in ($cleanupCandidate | Sort-Object -Property @{ Expression = 'DaysSinceLastActivity'; Descending = $true } | Select-Object -First 50)) {
                $lastAction = if ($item.LastActivityTime) { ([datetime]$item.LastActivityTime).ToString('yyyy-MM-dd') } else { 'none recorded' }

                [void]$markdown.AppendLine(('| {0} | {1} | {2} | {3} | {4} | {5} | {6} | {7} | {8} |' -f
                        $item.DisplayName, $item.PrimarySmtpAddress, $item.RecipientTypeDetails, $item.AccountDisabled,
                        $item.SkuAssigned, $lastAction, $item.ActivitySource, $item.TotalItemSizeMB, $item.LitigationHoldEnabled))
            }

            if ($cleanupCandidate.Count -gt 50) {
                [void]$markdown.AppendLine()
                [void]$markdown.AppendLine(('Showing the 50 longest-idle of {0}. The full set is in the inventory CSV.' -f $cleanupCandidate.Count))
            }
        } else {
            [void]$markdown.AppendLine('None. Every idle mailbox still has at least one delegate.')
        }

        [void]$markdown.AppendLine()

        [void]$markdown.AppendLine('## Mailboxes with delegates')
        [void]$markdown.AppendLine()
        [void]$markdown.AppendLine('Someone is still using these. Each needs an owner conversation before any change.')
        [void]$markdown.AppendLine()

        $withDelegate = @($inventoryRecord | Where-Object { $_.TotalDelegateCount -gt 0 } |
                Sort-Object -Property @{ Expression = 'TotalDelegateCount'; Descending = $true })

        if ($withDelegate.Count -gt 0) {
            [void]$markdown.AppendLine('| Display name | Address | Type | FullAccess | SendAs | OnBehalf | Last activity | Who |')
            [void]$markdown.AppendLine('|---|---|---|---|---|---|---|---|')

            foreach ($item in ($withDelegate | Select-Object -First 50)) {
                $lastAction = if ($item.LastActivityTime) { ([datetime]$item.LastActivityTime).ToString('yyyy-MM-dd') } else { 'none recorded' }

                $who = @($item.FullAccessTrustees, $item.SendAsTrustees, $item.SendOnBehalfTrustees |
                        Where-Object { -not [string]::IsNullOrWhiteSpace($_) }) -join '; '

                if ($who.Length -gt 120) {
                    $who = $who.Substring(0, 117) + '...'
                }

                [void]$markdown.AppendLine(('| {0} | {1} | {2} | {3} | {4} | {5} | {6} | {7} |' -f
                        $item.DisplayName, $item.PrimarySmtpAddress, $item.RecipientTypeDetails, $item.FullAccessCount,
                        $item.SendAsCount, $item.SendOnBehalfCount, $lastAction, $who))
            }

            if ($withDelegate.Count -gt 50) {
                [void]$markdown.AppendLine()
                [void]$markdown.AppendLine(('Showing the 50 most-delegated of {0}. Per-grant detail is in the access CSV.' -f $withDelegate.Count))
            }
        } else {
            [void]$markdown.AppendLine('None.')
        }

        [void]$markdown.AppendLine()

        [void]$markdown.AppendLine('## Resource mailboxes')
        [void]$markdown.AppendLine()
        [void]$markdown.AppendLine('Rooms and equipment. Held out of the candidate set above on purpose: a meeting room with no bookings this quarter is an idle mailbox and a live business resource at the same time. Listed here so they are reviewed by someone who knows the sites, not by an activity threshold.')
        [void]$markdown.AppendLine()

        if ($resourceMailbox.Count -gt 0) {
            [void]$markdown.AppendLine('| Display name | Address | Type | Last activity | Source | Delegates |')
            [void]$markdown.AppendLine('|---|---|---|---|---|---|')

            foreach ($item in ($resourceMailbox | Sort-Object -Property DisplayName)) {
                $lastAction = if ($item.LastActivityTime) { ([datetime]$item.LastActivityTime).ToString('yyyy-MM-dd') } else { 'none recorded' }

                [void]$markdown.AppendLine(('| {0} | {1} | {2} | {3} | {4} | {5} |' -f
                        $item.DisplayName, $item.PrimarySmtpAddress, $item.RecipientTypeDetails,
                        $lastAction, $item.ActivitySource, $item.TotalDelegateCount))
            }
        } else {
            [void]$markdown.AppendLine('None in scope.')
        }

        [void]$markdown.AppendLine()

        [void]$markdown.AppendLine('## Incomplete collection')
        [void]$markdown.AppendLine()

        if ($incompleteMailbox.Count -gt 0) {
            [void]$markdown.AppendLine(('{0} mailboxes had a permission or statistics call fail after every retry. They are excluded from every count above, because an empty result from a failed call is indistinguishable from a genuine absence of delegates or activity. Re-run to pick them up.' -f $incompleteMailbox.Count))
            [void]$markdown.AppendLine()
            [void]$markdown.AppendLine('| Display name | Address | Type | Access data | Statistics |')
            [void]$markdown.AppendLine('|---|---|---|---|---|')

            foreach ($item in ($incompleteMailbox | Sort-Object -Property DisplayName | Select-Object -First 50)) {
                [void]$markdown.AppendLine(('| {0} | {1} | {2} | {3} | {4} |' -f
                        $item.DisplayName, $item.PrimarySmtpAddress, $item.RecipientTypeDetails,
                        $item.AccessDataState, $item.StatisticsState))
            }
        } else {
            [void]$markdown.AppendLine('None. Every mailbox in scope returned both its permissions and its statistics.')
        }

        [void]$markdown.AppendLine()

        [void]$markdown.AppendLine('## How to read this')
        [void]$markdown.AppendLine()
        [void]$markdown.AppendLine('**"Inactive" is not pre-filtered.** The request could mean sign-in blocked, licence removed, or no activity for a period, so all three are reported as separate columns - `AccountDisabled`, `SkuAssigned`, `DaysSinceLastUserAction` - and nothing was excluded on their basis. Filter the CSV on whichever definition applies.')
        [void]$markdown.AppendLine()
        [void]$markdown.AppendLine('**`UserWhenChangedUTC` is the weakest column here.** It is the directory''s last-write timestamp, and any administrative action against the account updates it. If the offboarding automation in this folder has run over these mailboxes, it bumped this value on every account it touched, which makes long-dormant mailboxes look recently modified. `LastUserActionTime` is the column to scope on.')
        [void]$markdown.AppendLine()
        [void]$markdown.AppendLine('**`LastUserActionTime` is empty on every shared mailbox, and that is not a finding.** Exchange Online does not populate it for shared mailboxes, and Microsoft documents the property as deprecated for Exchange Online. Reading an empty value as "never opened" reports every shared mailbox in the tenant as dormant, including ones holding gigabytes of mail whose delegate signed in yesterday. `LastActivityTime` is therefore `LastUserActionTime` where it exists and `LastLogonTime` otherwise, and `ActivitySource` records which one produced the value. `LastLogonTime` is the weaker signal because background mailbox assistants can advance it, so a mailbox that looks active on `LastLogonTime` alone deserves a second look before anyone assumes a human is using it.')
        [void]$markdown.AppendLine()
        [void]$markdown.AppendLine('**Activity on a shared mailbox is delegate activity.** It records whoever holds the FullAccess grant opening the mailbox, not the departed employee.')
        [void]$markdown.AppendLine()
        [void]$markdown.AppendLine('**A failed call is not an empty result.** `StatisticsState` and `AccessDataState` are `Collected`, `CollectionFailed`, or `NotCollected` per mailbox. Anything other than `Collected` is excluded from the counts and from the candidate list, because Exchange throttling that swallows a permissions call would otherwise present a busy mailbox as having no delegates at all.')
        [void]$markdown.AppendLine()
        [void]$markdown.AppendLine('**Shared and inactive are mutually exclusive.** A shared mailbox still has a user account, normally with sign-in blocked. An inactive mailbox is preserved on hold after its account was deleted and has no account at all. `IsInactiveMailbox` tells them apart.')
        [void]$markdown.AppendLine()
        [void]$markdown.AppendLine('**Access was collected from three separate places.** FullAccess from `Get-EXOMailboxPermission`, SendAs from `Get-EXORecipientPermission`, and Send on Behalf from the mailbox''s `GrantSendOnBehalfTo` property. No single cmdlet returns all three; reading only the first would have understated access.')
        [void]$markdown.AppendLine()
        [void]$markdown.AppendLine(('**A group grant is one row covering many people.** {0} grants were made to a group rather than an individual. `TrusteeIsGroup` marks them. Re-run with `-ExpandGroupMember` to resolve those to named members before treating a delegate count as a headcount.' -f $groupGrantCount))
        [void]$markdown.AppendLine()
        [void]$markdown.AppendLine('**Inherited and built-in entries were filtered out.** `NT AUTHORITY\SELF`, orphaned raw SIDs, and administrative role groups such as Organization Management and Discovery Management appear on every mailbox and are not a business grant of access.')
        [void]$markdown.AppendLine()
        [void]$markdown.AppendLine('**A mailbox on Litigation Hold cannot simply be deleted.** Check `LitigationHoldEnabled` and `InPlaceHoldCount` before proposing any removal, and read `Litigation-Hold-7-Year-Retention.md` in the parent folder.')
        [void]$markdown.AppendLine()

        [void]$markdown.AppendLine('## Files')
        [void]$markdown.AppendLine()
        [void]$markdown.AppendLine('| File | Contents |')
        [void]$markdown.AppendLine('|------|----------|')
        [void]$markdown.AppendLine(('| `{0}` | One row per mailbox with directory state, activity, hold status, and a delegate summary. |' -f (Split-Path -Path $inventoryCsv -Leaf)))
        [void]$markdown.AppendLine(('| `{0}` | One row per access grant, with trustee type. |' -f (Split-Path -Path $accessCsv -Leaf)))
        [void]$markdown.AppendLine(('| `{0}` | This report. |' -f (Split-Path -Path $reportMd -Leaf)))
        [void]$markdown.AppendLine()

        [void]$markdown.AppendLine('## Reproducing this run')
        [void]$markdown.AppendLine()
        [void]$markdown.AppendLine('```powershell')
        [void]$markdown.AppendLine(('.\Get-SharedMailboxInventory.ps1 -AuthMode {0} -InactiveDayThreshold {1}{2}' -f
                $AuthMode, $InactiveDayThreshold, $(if ($ExpandGroupMember) { ' -ExpandGroupMember' } else { '' })))
        [void]$markdown.AppendLine('```')

        Set-Content -Path $reportMd -Value $markdown.ToString() -Encoding UTF8
        Write-Log -Message ('Wrote summary report to {0}.' -f $reportMd) -Level 'INFO'

        #endregion Write output
    } catch {
        Write-Log -Message ('Inventory failed: {0}' -f $_.Exception.Message) -Level 'ERROR'
        throw
    }
}

end {
    if ($script:ConnectedHere) {
        Disconnect-ExchangeOnline -Confirm:$false -ErrorAction SilentlyContinue
        Write-Log -Message 'Disconnected from Exchange Online.' -Level 'INFO'
    }
}

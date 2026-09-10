<#
.SYNOPSIS
    Proves whether a mailbox is genuinely preserved before its user account is
    deleted, and optionally proves the mail is still reachable afterwards.

.DESCRIPTION
    Answers the one question that has to be settled before a terminated user's
    account is deleted and their licence reclaimed:

        "If I delete this account now, does the mail survive and can I still get
         to it?"

    The script reads state and reports a verdict.  Everything except the optional
    -RunComplianceSearch is read-only.

    It looks for the mailbox in three places, in order, because the answer is
    different in each and the difference is what matters:

        Active         The user account still exists.  This is the state to be in
                       BEFORE deletion.  A hold here is what makes deletion safe.
        Inactive       The account has been deleted and a hold was in place, so
                       the mailbox was preserved.  This is the state to confirm
                       AFTER deletion.
        Soft-deleted   The account was deleted with NO hold in place.  The mailbox
                       is recoverable for 30 days from WhenSoftDeleted and is then
                       purged permanently.  This is the failure case, and it is
                       the one that looks fine in a portal list until the clock
                       runs out.

    Why LitigationHoldEnabled alone is not the whole answer:

    A mailbox can be held by several mechanisms at once, and Litigation Hold is
    only one of them.  A Purview retention policy, an eDiscovery case hold, or a
    delay hold all appear in the InPlaceHolds array and all preserve content, but
    none of them set LitigationHoldEnabled.  Reading only LitigationHoldEnabled
    reports a mailbox held by a retention policy as unprotected.  The script reads
    both and reports which mechanism is doing the work.

    Why an empty search result is not proof of anything:

    An eDiscovery search run by an account that lacks the Compliance Search role,
    or whose role assignment has not finished propagating, returns zero items
    rather than an error.  That is indistinguishable from a mailbox that genuinely
    holds no mail.  -RunComplianceSearch therefore reports the search status and
    the per-location statistics alongside the count, and the verdict says
    "unproven" rather than "empty" when the search returned nothing.  Run it
    against the mailbox while the account still exists to establish a baseline
    item count, then again after deletion and compare.

.PARAMETER Identity
    One or more mailboxes to check.  Accepts a user principal name, primary SMTP
    address, display name, or ExchangeGuid.

    Prefer the ExchangeGuid for an inactive mailbox.  An inactive mailbox can share
    an SMTP address with a live mailbox, in which case the address is ambiguous and
    only the ExchangeGuid or DistinguishedName identifies it uniquely.

.PARAMETER RunComplianceSearch
    Also create and run a Security & Compliance search against each mailbox and
    report the item count and size.  This is the step that proves the mail is
    actually reachable rather than merely flagged as held.

    Requires membership of the eDiscovery Manager role group -- see
    New-EDiscoveryAccessGroup.ps1.  Creating a search is a change, so it honours
    -WhatIf.

.PARAMETER ContentMatchQuery
    KQL query to scope the search.  Omit it to count everything in the mailbox,
    which is what a baseline before deletion wants.

.PARAMETER SearchNamePrefix
    Prefix for the generated search name.  The full name is
    {Prefix}-{alias}-{yyyyMMddHHmm}, which keeps repeated runs distinguishable in
    the Purview portal.  Defaults to 'MailboxPreservation'.

.PARAMETER SearchTimeoutSecond
    How long to wait for each search to complete before giving up and reporting it
    as still running.  Defaults to 900 (15 minutes).  A large mailbox takes longer;
    the search continues in Purview regardless and can be read later.

.PARAMETER RemoveSearchWhenDone
    Delete each generated compliance search after reading its statistics.  Off by
    default, because the search is the evidence that the check was performed and is
    worth keeping until the deletion is signed off.

.PARAMETER AuthMode
    Interactive prompts for sign-in and requires -AdminUpn.  Certificate is
    unattended and requires -Organization, -AppId, -CertificateThumbprint and
    -TenantId.

    There is no ManagedIdentity option: Connect-IPPSSession does not support it, so
    -RunComplianceSearch cannot run from an Azure Automation Managed Identity.

.PARAMETER Organization
    The tenant's primary or onmicrosoft.com domain.  Required for Certificate mode.

.PARAMETER AppId
    Application (client) ID of the Entra ID app registration for certificate auth.

.PARAMETER CertificateThumbprint
    Thumbprint of the authentication certificate in the executing account's store.

.PARAMETER TenantId
    Directory (tenant) ID.  Used with -AuthMode Certificate.

.PARAMETER AdminUpn
    Administrator UPN to sign in as when -AuthMode is Interactive.

.PARAMETER LogPath
    Directory for the log file and CSV output.  Defaults to C:\scripts\log, falling
    back to the user temp directory when that is not writable.

.EXAMPLE
    .\Test-MailboxPreservation.ps1 -Identity "satish@solomoninsight.com" -AdminUpn "adminmab@solomoninsight.com"

    The pre-deletion check.  Reports whether the hold is actually stamped, which
    mechanism is holding the mailbox, how large it is, and whether the account is
    safe to delete.  Read-only.

.EXAMPLE
    .\Test-MailboxPreservation.ps1 -Identity "satish@solomoninsight.com" -AdminUpn "adminmab@solomoninsight.com" -RunComplianceSearch

    The same check plus a baseline item count from an eDiscovery search, so the
    same search can be re-run after deletion and the numbers compared. Record the
    ItemCount before deleting the account.

.EXAMPLE
    .\Test-MailboxPreservation.ps1 -Identity "satish@solomoninsight.com" -AdminUpn "adminmab@solomoninsight.com" -RunComplianceSearch -Verbose

    The post-deletion confirmation.  The mailbox is now found as Inactive, and the
    search automatically targets it with the leading-period form that inactive
    mailboxes require.

.EXAMPLE
    .\Test-MailboxPreservation.ps1 -Identity "satish@solomoninsight.com","jsmith@solomoninsight.com" -AdminUpn "adminmab@solomoninsight.com" | Where-Object { -not $_.SafeToDeleteAccount }

    Check a batch and show only the accounts that are NOT safe to delete.

.INPUTS
    System.String[]
    Accepts mailbox identities through the -Identity parameter.

.OUTPUTS
    System.Management.Automation.PSCustomObject
    One object per identity with properties: Identity, DisplayName,
    PrimarySmtpAddress, MailboxState, RecipientTypeDetails, ExchangeGuid,
    DistinguishedName, WhenSoftDeleted, LitigationHoldEnabled, LitigationHoldDate,
    LitigationHoldDuration, LitigationHoldOwner, RetentionComment, InPlaceHolds,
    HoldMechanism, Preserved, ArchiveStatus, MailboxSizeGB, ItemCount,
    SearchName, SearchStatus, SearchItemCount, SearchSizeGB,
    SafeToDeleteAccount, Verdict, Detail.

    CSV exported to {LogPath}\MailboxPreservation-{timestamp}.csv
    Log written to  {LogPath}\Test-MailboxPreservation-{yyyyMMdd}.log

.NOTES
    Version:        1.0
    Author:         Infrastructure Team
    Creation Date:  2026-08-12

    Change History:
    Date        Author                  Description
    ----------  ----------------------  -------------------------------------------
    2026-08-12  Infrastructure Team     Initial release.  Written because the first
                                        live Litigation Hold left no way to confirm
                                        the mail was reachable before deleting the
                                        account and reclaiming the licence.
    2026-08-13  Infrastructure Team     Suggest near-matches when an identity
                                        resolves to nothing.  A leaver checked as
                                        first@domain in a tenant using
                                        first.last@domain returned NotFound with
                                        every hold column false, which reads exactly
                                        like an unprotected mailbox.
    2026-08-13  Infrastructure Team     Request a SEARCH-ONLY Security & Compliance
                                        session.  From ExchangeOnlineManagement
                                        3.9.0, New-ComplianceSearch fails at
                                        initialisation without
                                        -EnableSearchOnlySession, and the message
                                        ("Please close the current PowerShell session
                                        and open a new session ...") reads like
                                        neither a permissions nor a preservation
                                        problem.  The old catch block guessed "lacks
                                        the Compliance Search role", which was
                                        actively wrong here; the hint is now derived
                                        from the error text, and the log states
                                        explicitly that a failed search says nothing
                                        about whether the mailbox is preserved.
                                        Connecting is also retried three times with a
                                        20 s pause: Connect-IPPSSession intermittently
                                        fails with MSAL 0x80070002 right after
                                        Disconnect-ExchangeOnline, observed both
                                        succeeding and failing on the same host and
                                        account minutes apart, with and without
                                        -DisableWAM.

    Required PowerShell modules:
    - ExchangeOnlineManagement 3.9.0 or later when using -RunComplianceSearch
      (-EnableSearchOnlySession is required by the compliance search back end and
      does not exist before 3.9.0).  3.0.0 or later is sufficient for the
      read-only mailbox inspection.

    Required permissions:
    - Exchange Online: View-Only Recipients (View-Only Organization Management
      supplies it) to read hold properties and enumerate inactive mailboxes.
    - Purview, only for -RunComplianceSearch: the Compliance Search role, which
      membership of the eDiscovery Manager role group supplies.

    Both are granted together by New-EDiscoveryAccessGroup.ps1.

    The order that makes deletion safe:
    1. Apply the hold                      Invoke-M365OffboardingHold.ps1
    2. Confirm it stuck                    THIS SCRIPT, before deletion
    3. Delete the USER ACCOUNT             manual
    4. Confirm the mailbox went inactive   THIS SCRIPT, after deletion

    Never remove the licence as a step of its own.  Removing a licence from an
    account that still exists disconnects the mailbox and destroys it after 30
    days, hold or no hold.  Deleting the account is what releases the licence and
    converts the mailbox to an inactive mailbox.

    Related documentation in this directory:
    - Litigation-Hold-Access-Guide.md
    - Termination-Litigation-Hold-Process.md
    - New-EDiscoveryAccessGroup.ps1
#>

[CmdletBinding(SupportsShouldProcess)]
param(
    [Parameter(Mandatory, Position = 0, ValueFromPipeline = $true,
        HelpMessage = "Mailbox UPN, SMTP address, display name, or ExchangeGuid")]
    [ValidateNotNullOrEmpty()]
    [string[]]$Identity,

    [Parameter(HelpMessage = "Also run an eDiscovery search to prove the mail is reachable")]
    [switch]$RunComplianceSearch,

    [Parameter(HelpMessage = "KQL query to scope the search; omit to count everything")]
    [ValidateNotNullOrEmpty()]
    [string]$ContentMatchQuery,

    [Parameter(HelpMessage = "Prefix for generated compliance search names")]
    [ValidateNotNullOrEmpty()]
    [string]$SearchNamePrefix = 'MailboxPreservation',

    [Parameter(HelpMessage = "Seconds to wait for each search to complete (default 900)")]
    [ValidateRange(60, 7200)]
    [int]$SearchTimeoutSecond = 900,

    [Parameter(HelpMessage = "Delete each generated search after reading its statistics")]
    [switch]$RemoveSearchWhenDone,

    [Parameter(HelpMessage = "Authentication model: Interactive or Certificate")]
    [ValidateSet('Interactive', 'Certificate')]
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

    [Parameter(HelpMessage = "Directory (tenant) ID for certificate auth")]
    [ValidateNotNullOrEmpty()]
    [string]$TenantId,

    [Parameter(HelpMessage = "Administrator UPN for interactive sign-in")]
    [ValidateNotNullOrEmpty()]
    [string]$AdminUpn,

    [Parameter(HelpMessage = "Directory for log and CSV output")]
    [ValidateNotNullOrEmpty()]
    [string]$LogPath = 'C:\scripts\log'
)

begin {
    #region Configuration Variables
    $ScriptName = 'Test-MailboxPreservation'
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
            $fallback = Join-Path $env:TEMP 'MailboxPreservation'
            if (-not (Test-Path $fallback)) {
                New-Item -ItemType Directory -Path $fallback -Force -ErrorAction SilentlyContinue | Out-Null
            }
            Write-Warning "Log path '$Preferred' is not writable. Falling back to '$fallback'."
            return $fallback
        }
    }

    function Initialize-RequiredModule {
        param(
            [Parameter(Mandatory)]
            [string[]]$Name,

            [ValidateSet('CurrentUser', 'AllUsers')]
            [string]$Scope = 'CurrentUser'
        )

        # PowerShellGet talks to the Gallery over TLS 1.2; Windows PowerShell 5.1
        # negotiates an older protocol by default and the request is rejected.
        if ([System.Net.ServicePointManager]::SecurityProtocol -notmatch 'Tls12') {
            [System.Net.ServicePointManager]::SecurityProtocol =
            [System.Net.ServicePointManager]::SecurityProtocol -bor [System.Net.SecurityProtocolType]::Tls12
        }

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
            }

            Import-Module -Name $moduleName -ErrorAction Stop
        }
    }

    function Connect-PreservationService {
        <#
            Connect to one service at a time.

            Exchange Online and Security & Compliance PowerShell ship in the same
            module and export overlapping cmdlets.  Held open together the second
            connection shadows the first, so a command intended for one service
            silently runs against the other.  The mailbox read finishes and
            disconnects before the search phase connects.
        #>
        param(
            [Parameter(Mandatory)]
            [ValidateSet('ExchangeOnline', 'SecurityAndCompliance')]
            [string]$Service
        )

        # Compliance search requires a SEARCH-ONLY Security & Compliance session
        # from ExchangeOnlineManagement 3.9.0 onwards.  Without the flag,
        # New-ComplianceSearch fails at initialisation with "Please close the
        # current PowerShell session and open a new session using
        # Connect-IPPSSession with the -EnableSearchOnlySession flag" -- which is
        # a session-shape problem, not a permissions problem, and reads nothing
        # like one.  This script only ever uses the Security & Compliance session
        # for search, so the flag is safe to set unconditionally here.  Do NOT
        # copy it into tooling that also calls Add-RoleGroupMember: a search-only
        # session does not carry the administrative cmdlets.
        $searchOnly = @{}
        if ($Service -eq 'SecurityAndCompliance') { $searchOnly['EnableSearchOnlySession'] = $true }

        # Connecting is retried.  Connect-IPPSSession intermittently fails with
        # MSAL 0x80070002 immediately after Disconnect-ExchangeOnline has torn the
        # previous session down -- observed succeeding and failing on the same host
        # and account minutes apart, with and without -DisableWAM.  A short pause
        # and a second attempt clears it, so the two-phase design does not turn a
        # transient local fault into a half-finished run.
        $maxAttempt = 3
        $attempt = 0

        while ($true) {
            $attempt++

            try {
                switch ($AuthMode) {
                    'Certificate' {
                        foreach ($required in @('Organization', 'AppId', 'CertificateThumbprint', 'TenantId')) {
                            if (-not (Get-Variable -Name $required -ValueOnly -ErrorAction SilentlyContinue)) {
                                throw "-$required is required when -AuthMode is Certificate."
                            }
                        }

                        if ($Service -eq 'ExchangeOnline') {
                            Write-Log -Message "Connecting to Exchange Online using certificate app-only auth ($Organization)..."
                            Connect-ExchangeOnline -AppId $AppId -CertificateThumbprint $CertificateThumbprint `
                                -Organization $Organization -ShowBanner:$false -ErrorAction Stop
                        } else {
                            Write-Log -Message "Connecting to Security & Compliance PowerShell using certificate app-only auth ($Organization)..."
                            Connect-IPPSSession -AppId $AppId -CertificateThumbprint $CertificateThumbprint `
                                -Organization $Organization @searchOnly -ErrorAction Stop
                        }
                    }

                    'Interactive' {
                        if (-not $AdminUpn) {
                            throw "-AdminUpn is required when -AuthMode is Interactive."
                        }

                        if ($Service -eq 'ExchangeOnline') {
                            Write-Log -Message "Connecting to Exchange Online interactively as $AdminUpn..."
                            Connect-ExchangeOnline -UserPrincipalName $AdminUpn -ShowBanner:$false -ErrorAction Stop
                        } else {
                            Write-Log -Message "Connecting to Security & Compliance PowerShell interactively as $AdminUpn (search-only session)..."
                            Connect-IPPSSession -UserPrincipalName $AdminUpn @searchOnly -ErrorAction Stop
                        }
                    }
                }

                return
            } catch {
                $text = $_.Exception.Message

                # A missing required parameter is a caller error; retrying is pointless.
                if ($text -match 'is required when -AuthMode') { throw }

                if ($attempt -ge $maxAttempt) {
                    throw "Could not connect to $Service after $attempt attempt(s): $text"
                }

                Write-Log -Message "Connection to $Service failed on attempt $attempt of ${maxAttempt}: $text" -Level 'WARNING'
                Write-Log -Message "Retrying in 20 seconds. This is commonly a transient local token-broker fault rather than a tenant problem." -Level 'WARNING'
                Start-Sleep -Seconds 20
            }
        }
    }

    function Disconnect-PreservationService {
        try {
            Disconnect-ExchangeOnline -Confirm:$false -ErrorAction SilentlyContinue
            Write-Log -Message "Disconnected." -Level 'VERBOSE'
        } catch {
            Write-Log -Message "Disconnect reported: $($_.Exception.Message)" -Level 'VERBOSE'
        }
    }

    function Find-MailboxCandidate {
        <#
            Suggest near-matches when an identity resolves to nothing.

            "No mailbox found" is nearly always a wrong address rather than a
            missing mailbox, and the two are indistinguishable from the message
            alone -- which is exactly the moment someone concludes the mail is gone
            and stops looking.  A first name, or a guessed address of the form
            first@domain in a tenant that uses first.last@domain, produces it every
            time.

            Search on the LOCAL PART of the supplied address.  Ambiguous name
            resolution matches display names and aliases, so 'satish' finds
            'Satish Kumar' while the full non-existent SMTP address matches
            nothing.  All three states are searched, because a leaver is most
            likely to be in the last two.
        #>
        param(
            [Parameter(Mandatory)]
            [string]$MailboxIdentity
        )

        # 'satish@solomoninsight.com' -> 'satish'.  An identity with no @ is
        # already a name or alias and is used as supplied.
        $term = ($MailboxIdentity -split '@')[0].Trim()
        if ([string]::IsNullOrWhiteSpace($term)) { return @() }

        $candidate = @()
        $lookup = @(
            @{ Label = 'Active'; Param = @{ Anr = $term } }
            @{ Label = 'Inactive'; Param = @{ Anr = $term; InactiveMailboxOnly = $true } }
            @{ Label = 'SoftDeleted'; Param = @{ Anr = $term; SoftDeletedMailbox = $true } }
        )

        foreach ($item in $lookup) {
            try {
                # Assigned to its own variable first: @($item.Param) is array
                # syntax, not splatting, and would pass the hashtable positionally.
                $lookupParam = $item.Param
                $found = @(Get-Mailbox @lookupParam -ResultSize 20 -ErrorAction Stop)
                foreach ($box in $found) {
                    $candidate += [PSCustomObject]@{
                        State = $item.Label
                        DisplayName = $box.DisplayName
                        UserPrincipalName = $box.UserPrincipalName
                        PrimarySmtpAddress = $box.PrimarySmtpAddress
                        ExchangeGuid = $box.ExchangeGuid
                        LitigationHoldEnabled = [bool]$box.LitigationHoldEnabled
                        WhenSoftDeleted = $box.WhenSoftDeleted
                    }
                }
            } catch {
                Write-Log -Message "Candidate lookup ($($item.Label)) for '$term' reported: $($_.Exception.Message)" -Level 'VERBOSE'
            }
        }

        return $candidate
    }

    function Get-MailboxInAnyState {
        <#
            Find the mailbox as active, then inactive, then soft-deleted.

            The order matters.  An inactive mailbox can share an SMTP address with a
            live one, and looking in the inactive set first would return the wrong
            object for a user who still exists.  Returns the mailbox plus the state
            it was found in, or $null.
        #>
        param(
            [Parameter(Mandatory)]
            [string]$MailboxIdentity
        )

        try {
            $active = Get-Mailbox -Identity $MailboxIdentity -ErrorAction Stop
            return [PSCustomObject]@{ Mailbox = $active; State = 'Active' }
        } catch {
            Write-Log -Message "'$MailboxIdentity' is not an active mailbox: $($_.Exception.Message)" -Level 'VERBOSE'
        }

        try {
            $inactive = Get-Mailbox -InactiveMailboxOnly -Identity $MailboxIdentity -ErrorAction Stop
            if ($inactive) {
                return [PSCustomObject]@{ Mailbox = @($inactive)[0]; State = 'Inactive' }
            }
        } catch {
            Write-Log -Message "'$MailboxIdentity' is not an inactive mailbox: $($_.Exception.Message)" -Level 'VERBOSE'
        }

        # Soft-deleted but NOT inactive means the account was deleted with no hold
        # in place.  Recoverable for 30 days from WhenSoftDeleted, then purged.
        try {
            $soft = Get-Mailbox -SoftDeletedMailbox -Identity $MailboxIdentity -ErrorAction Stop
            if ($soft) {
                return [PSCustomObject]@{ Mailbox = @($soft)[0]; State = 'SoftDeleted' }
            }
        } catch {
            Write-Log -Message "'$MailboxIdentity' is not a soft-deleted mailbox: $($_.Exception.Message)" -Level 'VERBOSE'
        }

        return $null
    }

    function Get-MailboxSizeInGb {
        param(
            [Parameter(Mandatory)]
            [string]$StatisticsIdentity,
            [switch]$IncludeSoftDeleted
        )

        try {
            $statParam = @{ Identity = $StatisticsIdentity; ErrorAction = 'Stop' }
            if ($IncludeSoftDeleted) { $statParam['IncludeSoftDeletedRecipients'] = $true }

            $stats = Get-MailboxStatistics @statParam

            $sizeGb = $null
            if ($stats.TotalItemSize) {
                $byteText = [regex]::Match($stats.TotalItemSize.ToString(), '\(([\d,]+) bytes\)')
                if ($byteText.Success) {
                    $sizeGb = [math]::Round(([double]($byteText.Groups[1].Value -replace ',', '')) / 1GB, 2)
                }
            }

            return [PSCustomObject]@{
                SizeGB = $sizeGb
                ItemCount = $stats.ItemCount
            }
        } catch {
            Write-Log -Message "Could not read statistics for ${StatisticsIdentity}: $($_.Exception.Message)" -Level 'VERBOSE'
            return [PSCustomObject]@{ SizeGB = $null; ItemCount = $null }
        }
    }

    function Get-HoldMechanism {
        <#
            Name every mechanism currently preserving the mailbox.

            Litigation Hold is only one of them.  A Purview retention policy, an
            eDiscovery case hold, or a delay hold all preserve content and none of
            them set LitigationHoldEnabled, so a check that reads only that property
            reports a properly protected mailbox as unprotected.  InPlaceHolds
            encodes the rest by prefix.
        #>
        param(
            [Parameter(Mandatory)]
            [AllowNull()]
            $Mailbox
        )

        $mechanism = @()

        if ($Mailbox.LitigationHoldEnabled) {
            $mechanism += 'LitigationHold'
        }

        foreach ($hold in @($Mailbox.InPlaceHolds)) {
            if ([string]::IsNullOrWhiteSpace($hold)) { continue }

            switch -Regex ($hold) {
                '^-mbx' { $mechanism += "ExcludedFromOrgRetentionPolicy($hold)"; break }
                '^mbx' { $mechanism += "PurviewRetentionPolicy($hold)"; break }
                '^skp' { $mechanism += "SkypeRetentionPolicy($hold)"; break }
                '^UniH' { $mechanism += "eDiscoveryCaseHold($hold)"; break }
                '^grp' { $mechanism += "GroupHold($hold)"; break }
                default { $mechanism += "UnknownHold($hold)" }
            }
        }

        if ($Mailbox.DelayHoldApplied) { $mechanism += 'DelayHold' }
        if ($Mailbox.DelayReleaseHoldApplied) { $mechanism += 'DelayReleaseHold' }

        return $mechanism
    }

    function Invoke-PreservationSearch {
        <#
            Create, start, and read back a compliance search for one mailbox.

            An inactive mailbox is addressed by prepending a period to its SMTP
            address.  Without the period the search targets the live recipient of
            that address -- which may not exist, in which case the search returns
            zero items and completes successfully.

            -AllowNotFoundExchangeLocationsEnabled is required for both inactive and
            recently deleted mailboxes, whose addresses no longer resolve to a live
            recipient.  Without it the search fails to create at all.
        #>
        param(
            [Parameter(Mandatory)]
            [string]$SearchName,
            [Parameter(Mandatory)]
            [string]$ExchangeLocation,
            [Parameter(Mandatory)]
            [int]$TimeoutSecond,
            [string]$Query
        )

        $searchParam = @{
            Name = $SearchName
            ExchangeLocation = $ExchangeLocation
            AllowNotFoundExchangeLocationsEnabled = $true
            ErrorAction = 'Stop'
        }

        if ($Query) { $searchParam['ContentMatchQuery'] = $Query }

        New-ComplianceSearch @searchParam | Out-Null
        Start-ComplianceSearch -Identity $SearchName -ErrorAction Stop
        Write-Log -Message "Compliance search '$SearchName' started against $ExchangeLocation."

        $deadline = (Get-Date).AddSeconds($TimeoutSecond)
        $search = $null

        while ((Get-Date) -lt $deadline) {
            Start-Sleep -Seconds 15
            $search = Get-ComplianceSearch -Identity $SearchName -ErrorAction Stop

            if ($search.Status -in @('Completed', 'Failed')) { break }
            Write-Log -Message "Search '$SearchName' status: $($search.Status)" -Level 'VERBOSE'
        }

        if (-not $search) {
            $search = Get-ComplianceSearch -Identity $SearchName -ErrorAction SilentlyContinue
        }

        $sizeGb = $null
        if ($search.Size) {
            $sizeGb = [math]::Round(([double]$search.Size) / 1GB, 2)
        }

        return [PSCustomObject]@{
            Name = $SearchName
            Status = $search.Status
            Items = $search.Items
            SizeGB = $sizeGb
            Statistics = $search.SearchStatistics
        }
    }
    #endregion Helper Functions

    $script:ResolvedLogPath = Resolve-LogDirectory -Preferred $LogPath
    $script:PipelineIdentity = @()
    $startTime = Get-Date

    Write-Log -Message "========================================"
    Write-Log -Message "$ScriptName started"
    Write-Log -Message "========================================"
    Write-Log -Message "AuthMode          : $AuthMode"
    Write-Log -Message "RunAs             : $env:USERDOMAIN\$env:USERNAME"
    Write-Log -Message "Host              : $env:COMPUTERNAME"
    Write-Log -Message "Compliance search : $($RunComplianceSearch.IsPresent)"
    Write-Log -Message "Log directory     : $script:ResolvedLogPath"
    Write-Log -Message "Mailbox inspection is read-only. Only -RunComplianceSearch changes anything."

    Initialize-RequiredModule -Name @('ExchangeOnlineManagement')
}

process {
    # Collect pipeline input; the work runs once in end{} so the two service
    # connections are each made exactly once rather than per input object.
    $script:PipelineIdentity += $Identity
}

end {
    $result = @()
    $target = @($script:PipelineIdentity | Select-Object -Unique)

    Write-Log -Message "Checking $($target.Count) mailbox(es)."

    #region Phase 1 - Read Mailbox State
    try {
        Connect-PreservationService -Service 'ExchangeOnline'

        foreach ($item in $target) {
            Write-Log -Message "----------------------------------------"
            Write-Log -Message "Checking $item"

            $record = [PSCustomObject]@{
                Identity = $item
                DisplayName = $null
                PrimarySmtpAddress = $null
                MailboxState = 'NotFound'
                RecipientTypeDetails = $null
                ExchangeGuid = $null
                DistinguishedName = $null
                WhenSoftDeleted = $null
                LitigationHoldEnabled = $false
                LitigationHoldDate = $null
                LitigationHoldDuration = $null
                LitigationHoldOwner = $null
                RetentionComment = $null
                InPlaceHolds = $null
                HoldMechanism = $null
                Preserved = $false
                ArchiveStatus = $null
                MailboxSizeGB = $null
                ItemCount = $null
                SearchName = $null
                SearchStatus = $null
                SearchItemCount = $null
                SearchSizeGB = $null
                SafeToDeleteAccount = $false
                Verdict = 'NotFound'
                Detail = ''
            }

            $found = Get-MailboxInAnyState -MailboxIdentity $item

            if (-not $found) {
                # Not found is nearly always a wrong address, not a missing
                # mailbox -- so look for near-matches rather than leaving the
                # operator to conclude the mail is gone.
                Write-Log -Message "$item - no mailbox found in any state. Searching for near-matches..." -Level 'WARNING'
                $candidate = @(Find-MailboxCandidate -MailboxIdentity $item)

                if ($candidate.Count -gt 0) {
                    $record.Verdict = 'NotFoundWithSuggestions'
                    Write-Log -Message "Found $($candidate.Count) possible match(es) for '$item'. This identity is almost certainly the wrong address rather than a missing mailbox:" -Level 'WARNING'

                    foreach ($match in $candidate) {
                        Write-Log -Message "  [$($match.State)] $($match.DisplayName) | $($match.UserPrincipalName) | $($match.PrimarySmtpAddress) | LitigationHold=$($match.LitigationHoldEnabled)$(if ($match.WhenSoftDeleted) { " | softDeleted=$($match.WhenSoftDeleted)" })" -Level 'WARNING'
                    }

                    $summary = ($candidate | ForEach-Object {
                            "[$($_.State)] $($_.DisplayName) <$($_.PrimarySmtpAddress)> hold=$($_.LitigationHoldEnabled)"
                        }) -join ' ; '

                    $record.Detail = "No mailbox matched '$item', but $($candidate.Count) similar mailbox(es) exist: $summary. Re-run with the correct address, or with the ExchangeGuid for an inactive mailbox."
                    Write-Log -Message "Re-run this script with the correct address from the list above." -Level 'WARNING'
                } else {
                    $record.Detail = "No active, inactive, or soft-deleted mailbox matched '$item', and no similar mailbox was found either. Confirm the person's real address (the tenant may use a first.last form), or supply the ExchangeGuid. This is NOT evidence that mail has been lost -- an identity that does not resolve and a mailbox that does not exist look identical here."
                }

                $result += $record
                continue
            }

            $mailbox = $found.Mailbox
            $record.MailboxState = $found.State
            $record.DisplayName = $mailbox.DisplayName
            $record.PrimarySmtpAddress = $mailbox.PrimarySmtpAddress
            $record.RecipientTypeDetails = $mailbox.RecipientTypeDetails
            $record.ExchangeGuid = $mailbox.ExchangeGuid
            $record.DistinguishedName = $mailbox.DistinguishedName
            $record.WhenSoftDeleted = $mailbox.WhenSoftDeleted
            $record.LitigationHoldEnabled = [bool]$mailbox.LitigationHoldEnabled
            $record.LitigationHoldDate = $mailbox.LitigationHoldDate
            $record.LitigationHoldDuration = $mailbox.LitigationHoldDuration
            $record.LitigationHoldOwner = $mailbox.LitigationHoldOwner
            $record.RetentionComment = $mailbox.RetentionComment
            $record.ArchiveStatus = $mailbox.ArchiveStatus
            $record.InPlaceHolds = (@($mailbox.InPlaceHolds) -join '; ')

            $mechanism = Get-HoldMechanism -Mailbox $mailbox
            $record.HoldMechanism = ($mechanism -join '; ')
            $record.Preserved = @($mechanism | Where-Object { $_ -notmatch '^ExcludedFrom' }).Count -gt 0

            $stats = Get-MailboxSizeInGb -StatisticsIdentity $mailbox.ExchangeGuid.ToString() `
                -IncludeSoftDeleted:($found.State -ne 'Active')
            $record.MailboxSizeGB = $stats.SizeGB
            $record.ItemCount = $stats.ItemCount

            #region Verdict
            switch ($found.State) {
                'Active' {
                    if ($record.Preserved) {
                        $record.SafeToDeleteAccount = $true
                        $record.Verdict = 'PreservedReadyToDelete'
                        $record.Detail = "Held by: $($record.HoldMechanism). Deleting the USER ACCOUNT converts this to an inactive mailbox and releases the licence. Do NOT remove the licence as a separate step."
                    } else {
                        $record.Verdict = 'NotPreserved'
                        $record.Detail = 'No hold of any kind is in place. Deleting the account or removing the licence destroys this mail permanently after 30 days. Run Invoke-M365OffboardingHold.ps1 against this user first.'
                    }
                }

                'Inactive' {
                    $record.SafeToDeleteAccount = $false
                    $record.Verdict = 'InactivePreserved'
                    $record.Detail = "Offboarding complete. The account is deleted, the mailbox is preserved by: $($record.HoldMechanism), it consumes no licence, and it is searchable through Purview eDiscovery. Identify it by ExchangeGuid $($record.ExchangeGuid) - an SMTP address can be ambiguous."
                }

                'SoftDeleted' {
                    $record.Verdict = 'SoftDeletedAtRisk'
                    $purgeDate = if ($mailbox.WhenSoftDeleted) {
                        ([datetime]$mailbox.WhenSoftDeleted).AddDays(30).ToString('yyyy-MM-dd')
                    } else {
                        'unknown'
                    }
                    $record.Detail = "The account was deleted with NO hold in place, so the mailbox is soft-deleted rather than inactive. It is recoverable until approximately $purgeDate and is then purged permanently. Restore the user account NOW if this mail matters."
                }
            }
            #endregion Verdict

            Write-Log -Message "$item - state $($record.MailboxState), preserved $($record.Preserved), verdict $($record.Verdict)."
            if ($record.HoldMechanism) {
                Write-Log -Message "  Hold mechanism: $($record.HoldMechanism)"
            }
            if ($record.Verdict -in @('NotPreserved', 'SoftDeletedAtRisk')) {
                Write-Log -Message "  $($record.Detail)" -Level 'WARNING'
            }

            $result += $record
        }
    } finally {
        Disconnect-PreservationService
    }
    #endregion Phase 1 - Read Mailbox State

    #region Phase 2 - Compliance Search
    if ($RunComplianceSearch -and $result.Count -gt 0) {
        try {
            Connect-PreservationService -Service 'SecurityAndCompliance'

            foreach ($record in $result) {
                if ($record.MailboxState -eq 'NotFound') { continue }

                # An inactive mailbox is targeted by prepending a period to the
                # address. Without it the search resolves the live recipient of that
                # address, finds nothing, and completes successfully.
                $location = if ($record.MailboxState -eq 'Active') {
                    $record.PrimarySmtpAddress.ToString()
                } else {
                    ".$($record.PrimarySmtpAddress)"
                }

                $aliasPart = ($record.PrimarySmtpAddress.ToString() -split '@')[0] -replace '[^\p{L}\p{Nd}]', ''
                $searchName = "$SearchNamePrefix-$aliasPart-$Timestamp"

                if (-not $PSCmdlet.ShouldProcess($record.PrimarySmtpAddress, "Create and run compliance search '$searchName' against $location")) {
                    $record.SearchName = $searchName
                    $record.SearchStatus = 'WhatIf'
                    $record.Detail = "$($record.Detail) Would run compliance search '$searchName' against $location."
                    continue
                }

                try {
                    $search = Invoke-PreservationSearch -SearchName $searchName -ExchangeLocation $location `
                        -TimeoutSecond $SearchTimeoutSecond -Query $ContentMatchQuery

                    $record.SearchName = $search.Name
                    $record.SearchStatus = $search.Status
                    $record.SearchItemCount = $search.Items
                    $record.SearchSizeGB = $search.SizeGB

                    Write-Log -Message "$($record.PrimarySmtpAddress) - search '$($search.Name)' $($search.Status), $($search.Items) item(s), $($search.SizeGB) GB."

                    if ($search.Status -eq 'Completed' -and [int]($search.Items) -gt 0) {
                        $record.Detail = "$($record.Detail) PROVEN REACHABLE: eDiscovery returned $($search.Items) item(s), $($search.SizeGB) GB, from $location."
                    } elseif ($search.Status -eq 'Completed') {
                        # Zero items is not proof of an empty mailbox. A missing role
                        # or an unpropagated role assignment returns zero, not an error.
                        $record.Detail = "$($record.Detail) UNPROVEN: the search completed but returned 0 items. That is NOT proof the mailbox is empty - a missing or still-propagating Compliance Search role returns 0 rather than an error. Confirm with the eDiscovery RBAC Check diagnostic (Purview portal > Help > Diag:edisRBACdiag) before concluding anything, and compare with the mailbox item count of $($record.ItemCount)."
                        Write-Log -Message "$($record.PrimarySmtpAddress) - search returned 0 items. Mailbox statistics report $($record.ItemCount) item(s). Do not read this as an empty mailbox until the RBAC diagnostic is clean." -Level 'WARNING'
                    } else {
                        $record.Detail = "$($record.Detail) Search did not complete within $SearchTimeoutSecond second(s); status $($search.Status). It continues in Purview - re-read it with Get-ComplianceSearch -Identity '$($search.Name)'."
                    }

                    if ($RemoveSearchWhenDone) {
                        Remove-ComplianceSearch -Identity $searchName -Confirm:$false -ErrorAction SilentlyContinue
                        Write-Log -Message "Removed compliance search '$searchName'." -Level 'VERBOSE'
                    }
                } catch {
                    $searchError = $_.Exception.Message

                    # Distinguish the two causes, because they need opposite
                    # responses and the raw message reads like neither.
                    $hint = if ($searchError -match 'EnableSearchOnlySession') {
                        ' The Security & Compliance session was not a search-only session. That is a session-shape problem, NOT a permissions problem, and it says nothing about whether the mailbox is preserved. Re-run this script; it now requests a search-only session.'
                    } elseif ($searchError -match 'denied|Access|permission|role|unauthoriz') {
                        ' The account appears to lack the Compliance Search role - see New-EDiscoveryAccessGroup.ps1.'
                    } else {
                        ' Cause unclear from the message. This does NOT indicate anything about whether the mailbox is preserved - read the LitigationHoldEnabled and HoldMechanism columns for that.'
                    }

                    $record.SearchStatus = 'Failed'
                    $record.Detail = "$($record.Detail) Compliance search failed: $searchError$hint"
                    Write-Log -Message "Compliance search for $($record.PrimarySmtpAddress) failed: $searchError$hint" -Level 'ERROR'
                    Write-Log -Message "The preservation verdict above is unaffected - it comes from the mailbox properties, not from the search." -Level 'WARNING'
                }
            }
        } finally {
            Disconnect-PreservationService
        }
    }
    #endregion Phase 2 - Compliance Search

    #region Report
    Write-Log -Message "========================================"
    Write-Log -Message "=== PRESERVATION SUMMARY ==="

    $readyToDelete = @($result | Where-Object { $_.SafeToDeleteAccount })
    $atRisk = @($result | Where-Object { $_.Verdict -in @('NotPreserved', 'SoftDeletedAtRisk') })
    $done = @($result | Where-Object { $_.Verdict -eq 'InactivePreserved' })

    Write-Log -Message "  Preserved, account ready to delete : $($readyToDelete.Count)"
    Write-Log -Message "  Already inactive, offboarded       : $($done.Count)"
    Write-Log -Message "  AT RISK                            : $($atRisk.Count)"

    foreach ($item in $readyToDelete) {
        Write-Log -Message "  READY: $($item.PrimarySmtpAddress) - $($item.HoldMechanism) - $($item.MailboxSizeGB) GB, $($item.ItemCount) items"
    }

    if ($atRisk.Count -gt 0) {
        Write-Log -Message "=== DO NOT DELETE OR UNLICENSE ===" -Level 'WARNING'
        foreach ($item in $atRisk) {
            Write-Log -Message "  $($item.PrimarySmtpAddress) - $($item.Verdict) - $($item.Detail)" -Level 'WARNING'
        }
    }

    $csvPath = Join-Path $script:ResolvedLogPath "MailboxPreservation-$Timestamp.csv"
    if ($result.Count -gt 0) {
        $result | Export-Csv -Path $csvPath -NoTypeInformation -Encoding UTF8
        Write-Log -Message "Results exported to: $csvPath"
    }

    $duration = (Get-Date) - $startTime
    Write-Log -Message "$ScriptName completed in $($duration.ToString('hh\:mm\:ss'))"
    #endregion Report

    return $result
}

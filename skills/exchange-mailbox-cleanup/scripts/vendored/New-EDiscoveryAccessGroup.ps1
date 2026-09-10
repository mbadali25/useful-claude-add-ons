<#
.SYNOPSIS
    Creates the mail-enabled security group that grants eDiscovery access to
    Litigation Hold and inactive mailboxes, and assigns it the required roles.

.DESCRIPTION
    Standing up "who is allowed to view, search, and export a held mailbox" is a
    three-layer job, and the layers live in three different services.  This script
    does all three and verifies each one by reading it back.

        Layer 1  Exchange Online   Create a MAIL-ENABLED SECURITY GROUP.
        Layer 2  Purview           Add that group to the eDiscovery Manager role
                                   group, which carries Compliance Search, Preview,
                                   Export, RMS Decrypt, Case Management, Hold,
                                   Review and Manage review set tags.
        Layer 3  Exchange Online   Optionally add the group to View-Only
                                   Organization Management so members can read
                                   LitigationHoldEnabled and list inactive
                                   mailboxes in PowerShell.

    Why a mail-enabled security group and not an Entra ID security group:

    Microsoft Purview role groups accept only mail-enabled security groups.  An
    ordinary Entra ID security group, a distribution group, and a Microsoft 365
    Group are all rejected.  A mail-enabled security group cannot be created in
    the Entra ID portal at all -- New-DistributionGroup -Type Security in Exchange
    Online PowerShell is the only supported way to make one.  It does then appear
    in Entra ID and can be managed there, which is what makes the "just create an
    Azure group" instinct look correct right up until Add-RoleGroupMember refuses
    it.

    What a group CANNOT be granted:

    eDiscovery Administrator is a subgroup of the eDiscovery Manager role group,
    not a role group of its own, and Microsoft permits only individual users in it.
    Add-eDiscoveryCaseAdmin rejects a group.  -EDiscoveryAdministrator therefore
    takes a list of named users and assigns them one at a time.  Keep that list
    short: an eDiscovery Administrator can open every case in the tenant and read
    the results of every search in it.

    Two connections, never at the same time:

    Exchange Online and Security & Compliance PowerShell both export
    Add-RoleGroupMember and Get-RoleGroupMember from the same module.  Held open
    together they collide, and whichever connected last silently wins -- so an
    Exchange role assignment can be sent to Purview, or the reverse, and report
    success.  This script connects to one service, finishes with it, disconnects,
    and only then connects to the other.

    Propagation is not instant:

    A newly created mail-enabled security group takes up to 60 minutes to replicate
    into the Security & Compliance directory, and a role assignment takes a further
    30 to 60 minutes to reach the search and export back ends.  Until it does, a
    search returns no results rather than an error, which is indistinguishable from
    a mailbox that genuinely holds nothing.

    The first delay is waited out by retrying the real Add-RoleGroupMember call in
    the Purview session -- see Add-RoleGroupMemberWithRetry.  Nothing else can test
    it: Exchange Online resolves the group it just created instantly, so a check in
    that session succeeds immediately and proves nothing.  The second delay cannot
    be waited out at all and is stated in the run summary instead.

    The script is idempotent.  An existing group is reused rather than recreated, a
    member already present is left alone, and a role already assigned is reported
    and skipped, so it is safe to re-run while waiting for propagation.

.PARAMETER GroupName
    Display name of the mail-enabled security group.  Defaults to
    'sg-eDiscovery-Managers'.  Reused if it already exists.

.PARAMETER GroupAlias
    Mail alias for the group.  Defaults to the group name with non-alphanumeric
    characters removed.  Exchange rejects an alias containing spaces or most
    punctuation, which is the usual cause of a failed first run.

.PARAMETER GroupPrimarySmtpAddress
    Primary SMTP address for the group.  Required when creating a new group,
    because a mail-enabled security group must be mail-enabled to be accepted by
    Purview.  The address never receives mail from outside the organisation --
    the group exists to be a permission holder, not a mailing list.

.PARAMETER Member
    User principal names to place in the group.  These are the people who will be
    able to search and export held and inactive mailboxes.  Members can be added
    later through the Exchange admin center without re-running this script.

.PARAMETER EDiscoveryAdministrator
    User principal names to additionally make eDiscovery Administrators.  Assigned
    individually because Microsoft does not permit a group here.  An eDiscovery
    Administrator can access every case in the tenant, so this should be one or two
    people, not the whole team.

    Requires the Case Management role, which membership of the eDiscovery Manager
    role group already supplies -- so list people who are also in -Member, or who
    are already eDiscovery Managers.

.PARAMETER GrantExchangeViewOnlyRecipient
    Also add the group to the Exchange Online View-Only Organization Management
    role group.

    eDiscovery permissions govern the Purview portal.  They do not let anyone run
    Get-Mailbox, so without this a member can search a held mailbox but cannot
    confirm from PowerShell that the hold is actually set, and cannot run
    Get-Mailbox -InactiveMailboxOnly to find a deleted user's mailbox.  Grant it
    unless a separate Exchange role already covers the same people.

.PARAMETER GroupWaitSeconds
    How long to keep retrying the Purview role assignment while Purview still
    cannot see a newly created group.  Defaults to 3600 (60 minutes), which is the
    worst case Microsoft documents for a mail-enabled security group to replicate
    into the Security & Compliance directory.

    The retry drives the real Add-RoleGroupMember call, one attempt a minute, and
    stops the moment it succeeds -- so a group that replicates in five minutes
    costs five minutes, not sixty.  Only the not-found signature is retried; any
    other error fails immediately rather than being retried for an hour.

    Set to 0 to attempt the assignment exactly once and do it in a second run
    instead.  That is the right choice for an unattended or scheduled invocation,
    where blocking for an hour is worse than re-running.

.PARAMETER AuthMode
    How to authenticate.  Interactive prompts for sign-in and requires -AdminUpn.
    Certificate is unattended and requires -Organization, -AppId,
    -CertificateThumbprint and -TenantId.

    There is no ManagedIdentity option here, unlike the offboarding scripts.
    Connect-IPPSSession does not support managed identity, so this script cannot
    run as an Azure Automation runbook against a Managed Identity.

.PARAMETER DisableWAM
    Bypass the Windows Web Account Manager broker when signing in interactively.

    ExchangeOnlineManagement 3.x brokers interactive sign-in through WAM by
    default on Windows.  When the local broker is unhealthy it fails inside MSAL
    before any request reaches Microsoft 365, and the errors name Windows rather
    than the tenant:

        Unknown Status: Unexpected  Error: 0x80070002     (ERROR_FILE_NOT_FOUND)
        WAM Error  Error Code: 3399680404  Message: NoNetwork

    Neither is a permissions problem, a network problem, or a fault in this
    script, and re-running without changing anything reproduces them.  -DisableWAM
    routes the sign-in through the ordinary browser flow instead, which does not
    involve the broker.

    The failure is worth bypassing rather than ignoring because of WHERE it
    lands.  Connecting to Security & Compliance is the second of two connections,
    so a broker fault leaves the Exchange Online half applied and the Purview half
    untouched -- a half-provisioned group whose members have inherited nothing.
    Re-running with this switch completes the outstanding half; the script is
    idempotent and skips what already succeeded.

.PARAMETER Organization
    The tenant's primary or onmicrosoft.com domain.  Required for Certificate mode.

.PARAMETER AppId
    Application (client) ID of the Entra ID app registration used for certificate
    app-only authentication.

.PARAMETER CertificateThumbprint
    Thumbprint of the authentication certificate held in the executing account's
    certificate store.

.PARAMETER TenantId
    Directory (tenant) ID.  Used with -AuthMode Certificate.

.PARAMETER AdminUpn
    The administrator UPN to sign in as when -AuthMode is Interactive.  Must hold
    the Organization Management role group or the Role Management role in Purview,
    which is what permits assigning eDiscovery permissions at all.

.PARAMETER LogPath
    Directory for the log file and CSV output.  Defaults to C:\scripts\log, falling
    back to the user temp directory when that is not writable.

.EXAMPLE
    .\New-EDiscoveryAccessGroup.ps1 -AdminUpn "adminmab@solomoninsight.com" -GroupPrimarySmtpAddress "sg-ediscovery-managers@solomoninsight.com" -Member "adminmab@solomoninsight.com" -GrantExchangeViewOnlyRecipient -WhatIf

    Dry run.  Shows the group that would be created, the role groups it would be
    added to, and the members that would go in it.  Changes nothing.  Run this
    first.

.EXAMPLE
    .\New-EDiscoveryAccessGroup.ps1 -AdminUpn "adminmab@solomoninsight.com" -GroupPrimarySmtpAddress "sg-ediscovery-managers@solomoninsight.com" -Member "adminmab@solomoninsight.com" -EDiscoveryAdministrator "adminmab@solomoninsight.com" -GrantExchangeViewOnlyRecipient

    The real run for this tenant.  Creates sg-eDiscovery-Managers, puts the admin
    account in it, grants the group eDiscovery Manager and Exchange View-Only
    Organization Management, and makes the admin account an eDiscovery
    Administrator so it can see every case rather than only its own.

.EXAMPLE
    .\New-EDiscoveryAccessGroup.ps1 -AdminUpn "adminmab@solomoninsight.com" -Member "newstarter@solomoninsight.com"

    Later run, adding a person to the existing group.  The group and its role
    assignments are found, reported, and left alone.

.EXAMPLE
    .\New-EDiscoveryAccessGroup.ps1 -AuthMode Certificate -Organization "solomoninsight.onmicrosoft.com" -AppId "00000000-0000-0000-0000-000000000000" -CertificateThumbprint "ABC123..." -TenantId "11111111-1111-1111-1111-111111111111" -GroupWaitSeconds 0

    Unattended run that creates the group and attempts the Purview assignment once
    rather than blocking for an hour, leaving the assignment for a second run once
    the group has replicated.

.EXAMPLE
    .\New-EDiscoveryAccessGroup.ps1 -AdminUpn "adminmab@solomoninsight.com" -EDiscoveryAdministrator "adminmab@solomoninsight.com"

    Recovery run after the Purview step failed on replication lag.  The group and
    its members are found and left alone, and only the outstanding Purview
    assignments are retried.  -GroupPrimarySmtpAddress is not needed, because the
    group already exists.

.EXAMPLE
    .\New-EDiscoveryAccessGroup.ps1 -AdminUpn "adminmab@solomoninsight.com" -DisableWAM

    Recovery run after the Security & Compliance connection failed with
    0x80070002 or a WAM NoNetwork error.  Bypasses the Windows authentication
    broker, reconciles the Exchange side (finding everything already done), and
    completes the outstanding Purview assignment.

.INPUTS
    None. This script does not accept pipeline input.

.OUTPUTS
    System.Management.Automation.PSCustomObject
    One object per action with properties: Layer, Target, Action, Result, Detail.

    CSV exported to {LogPath}\EDiscoveryAccessGroup-{timestamp}.csv
    Log written to  {LogPath}\New-EDiscoveryAccessGroup-{yyyyMMdd}.log

.NOTES
    Version:        1.0
    Author:         Infrastructure Team
    Creation Date:  2026-08-12

    Change History:
    Date        Author                  Description
    ----------  ----------------------  -------------------------------------------
    2026-08-12  Infrastructure Team     Initial release.  Written to make the
                                        eDiscovery grant repeatable after the first
                                        Litigation Hold was applied to a live
                                        mailbox and nobody could confirm the mail
                                        was reachable.
    2026-08-13  Infrastructure Team     Fixed the propagation wait, which tested the
                                        wrong service.  Wait-GroupVisibility polled
                                        Get-Recipient in the EXCHANGE session, where
                                        a just-created group resolves instantly, so
                                        it returned on the first poll and the
                                        Purview assignment still failed with
                                        ManagementObjectNotFoundException.  Replaced
                                        with Add-RoleGroupMemberWithRetry, which
                                        retries the real call in the Purview session
                                        and therefore actually waits.  Default
                                        -GroupWaitSeconds raised 900 -> 3600 to
                                        cover Microsoft's documented worst case.
                                        Found on the first live run.
    2026-08-13  Infrastructure Team     Added -DisableWAM.  The Windows WAM broker
                                        on the admin workstation failed interactive
                                        sign-in three times across two runs
                                        (0x80070002, and NoNetwork), each time
                                        inside MSAL before any request reached
                                        Microsoft 365.  Because Security &
                                        Compliance is the SECOND connection, a
                                        broker fault there leaves the Exchange half
                                        applied and the Purview half untouched.  A
                                        broker failure is now detected and rethrown
                                        naming the cause and the switch, instead of
                                        surfacing a raw Windows error code that
                                        reads like a permissions or network fault.

    Required PowerShell modules:
    - ExchangeOnlineManagement 3.0.0 or later (supplies both Connect-ExchangeOnline
      and Connect-IPPSSession)

    Required permissions to RUN this script:
    - Purview: Organization Management role group, or the Role Management role.
      Global Administrator alone is NOT sufficient to assign eDiscovery permissions
      and is not automatically an eDiscovery Manager.
    - Exchange Online: Organization Management, to create the group and to assign
      View-Only Organization Management.

    What the resulting group grants its members:
    - Case Management, Communication, Compliance Search, Custodian, Export, Hold,
      Manage review set tags, Preview, Review, RMS Decrypt.
    - NOT Search And Purge, which lives only in the Organization Management role
      group and permits bulk deletion of matching mail.

    Licensing:
    - Searching, previewing and exporting a held or inactive mailbox is available
      with Microsoft 365 E3.  Premium eDiscovery analysis (review sets, analytics)
      requires E5 or the Purview Suite / eDiscovery and Audit add-on for the person
      doing the analysis.
    - The mailbox being searched needs no licence once it is inactive.

    Related documentation in this directory:
    - Litigation-Hold-Access-Guide.md            (how to actually run the search)
    - Termination-Litigation-Hold-Process.md     (the process this supports)
    - Test-MailboxPreservation.ps1               (prove a mailbox is preserved)
#>

[CmdletBinding(SupportsShouldProcess)]
param(
    [Parameter(HelpMessage = "Display name of the mail-enabled security group")]
    [ValidateNotNullOrEmpty()]
    [string]$GroupName = 'sg-eDiscovery-Managers',

    [Parameter(HelpMessage = "Mail alias for the group; defaults to the name stripped of punctuation")]
    [ValidateNotNullOrEmpty()]
    [string]$GroupAlias,

    [Parameter(HelpMessage = "Primary SMTP address for the group; required when creating it")]
    [ValidateNotNullOrEmpty()]
    [string]$GroupPrimarySmtpAddress,

    [Parameter(HelpMessage = "User principal names to place in the group")]
    [string[]]$Member = @(),

    [Parameter(HelpMessage = "Users to additionally make eDiscovery Administrators (individuals only)")]
    [string[]]$EDiscoveryAdministrator = @(),

    [Parameter(HelpMessage = "Also grant Exchange View-Only Organization Management for Get-Mailbox access")]
    [switch]$GrantExchangeViewOnlyRecipient,

    [Parameter(HelpMessage = "Seconds to keep retrying the Purview role assignment while the group replicates (default 3600)")]
    [ValidateRange(0, 7200)]
    [int]$GroupWaitSeconds = 3600,

    [Parameter(HelpMessage = "Authentication model: Interactive or Certificate")]
    [ValidateSet('Interactive', 'Certificate')]
    [string]$AuthMode = 'Interactive',

    [Parameter(HelpMessage = "Bypass the Windows WAM broker on interactive sign-in (use after a 0x80070002 or NoNetwork WAM error)")]
    [switch]$DisableWAM,

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
    $ScriptName = 'New-EDiscoveryAccessGroup'
    $Timestamp = Get-Date -Format 'yyyyMMddHHmm'

    # The Purview role group that carries Compliance Search, Preview, Export and
    # RMS Decrypt.  Its Name is 'eDiscoveryManager' and its DisplayName is
    # 'eDiscovery Manager'; Microsoft's own documentation uses both spellings on
    # different pages.  Both candidates are tried and the one the tenant actually
    # returns is used, so a rename or a spelling difference does not present as
    # "role group not found".
    $EDiscoveryRoleGroupCandidate = @('eDiscoveryManager', 'eDiscovery Manager')

    # Exchange Online role group holding View-Only Recipients and View-Only
    # Configuration, which is what permits Get-Mailbox and
    # Get-Mailbox -InactiveMailboxOnly without granting any write.
    $ExchangeReadRoleGroup = 'View-Only Organization Management'
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
            $fallback = Join-Path $env:TEMP 'EDiscoveryAccess'
            if (-not (Test-Path $fallback)) {
                New-Item -ItemType Directory -Path $fallback -Force -ErrorAction SilentlyContinue | Out-Null
            }
            Write-Warning "Log path '$Preferred' is not writable. Falling back to '$fallback'."
            return $fallback
        }
    }

    function Initialize-RequiredModule {
        <#
            Install the module from the PowerShell Gallery when it is missing, then
            import it.  Only ExchangeOnlineManagement is needed here -- it supplies
            Connect-ExchangeOnline and Connect-IPPSSession both -- so the Graph
            import-order problem the offboarding scripts carry does not apply.
        #>
        param(
            [Parameter(Mandatory)]
            [string[]]$Name,

            [ValidateSet('CurrentUser', 'AllUsers')]
            [string]$Scope = 'CurrentUser'
        )

        # PowerShellGet talks to the Gallery over TLS 1.2; Windows PowerShell 5.1
        # negotiates an older protocol by default and the request is rejected
        # before any download.
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

                Write-Log -Message "Module '$moduleName' installed." -Level 'INFO'
            }

            Import-Module -Name $moduleName -ErrorAction Stop
        }
    }

    function Connect-ComplianceService {
        <#
            Connect to exactly one of the two services.

            Never hold both open at once.  Exchange Online and Security & Compliance
            PowerShell export Add-RoleGroupMember and Get-RoleGroupMember from the
            same module with identical signatures, so the second connection shadows
            the first and a role assignment silently reaches the wrong service and
            reports success.  Callers connect, finish, and disconnect.
        #>
        param(
            [Parameter(Mandatory)]
            [ValidateSet('ExchangeOnline', 'SecurityAndCompliance')]
            [string]$Service
        )

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
                        -Organization $Organization -ErrorAction Stop
                }
            }

            'Interactive' {
                if (-not $AdminUpn) {
                    throw "-AdminUpn is required when -AuthMode is Interactive."
                }

                # -DisableWAM is splatted rather than written inline so the switch
                # is genuinely absent when not requested.  Passing -DisableWAM:$false
                # explicitly is not the same as omitting it on every module build.
                $wamParam = @{}
                if ($DisableWAM) { $wamParam['DisableWAM'] = $true }

                try {
                    if ($Service -eq 'ExchangeOnline') {
                        Write-Log -Message "Connecting to Exchange Online interactively as $AdminUpn$(if ($DisableWAM) { ' (WAM broker bypassed)' })..."
                        Connect-ExchangeOnline -UserPrincipalName $AdminUpn -ShowBanner:$false @wamParam -ErrorAction Stop
                    } else {
                        Write-Log -Message "Connecting to Security & Compliance PowerShell interactively as $AdminUpn$(if ($DisableWAM) { ' (WAM broker bypassed)' })..."
                        Connect-IPPSSession -UserPrincipalName $AdminUpn @wamParam -ErrorAction Stop
                    }
                } catch {
                    # A broker fault fails inside MSAL before any request reaches
                    # Microsoft 365, and reports a Windows error rather than a
                    # tenant one -- so the message sends people looking at
                    # permissions or connectivity, neither of which is involved.
                    $text = $_.Exception.Message
                    $brokerSignature = @('0x80070002', 'WAM Error', 'MsalServiceException', 'Unknown Status: Unexpected')

                    $looksLikeBroker = $false
                    foreach ($signature in $brokerSignature) {
                        if ($text -match [regex]::Escape($signature)) { $looksLikeBroker = $true }
                    }

                    if ($looksLikeBroker -and -not $DisableWAM) {
                        throw "Interactive sign-in to $Service failed in the Windows WAM broker, not in Microsoft 365: $text`n`nThis is a local authentication-broker fault. It is not a permissions problem and not a fault in this script, and re-running unchanged will reproduce it. Re-run with -DisableWAM to use the browser sign-in flow instead. The script is idempotent, so it will skip whatever already succeeded."
                    }

                    throw
                }
            }
        }
    }

    function Disconnect-ComplianceService {
        <#
            Disconnect-ExchangeOnline tears down every session the module owns,
            including a Security & Compliance one, which is exactly what is wanted
            between the two phases.
        #>
        try {
            Disconnect-ExchangeOnline -Confirm:$false -ErrorAction SilentlyContinue
            Write-Log -Message "Disconnected." -Level 'VERBOSE'
        } catch {
            Write-Log -Message "Disconnect reported: $($_.Exception.Message)" -Level 'VERBOSE'
        }
    }

    function Get-ResultRecord {
        param(
            [Parameter(Mandatory)]
            [string]$Layer,
            [Parameter(Mandatory)]
            [string]$Target,
            [Parameter(Mandatory)]
            [string]$Action,
            [Parameter(Mandatory)]
            [string]$Result,
            [string]$Detail = ''
        )

        return [PSCustomObject]@{
            Layer = $Layer
            Target = $Target
            Action = $Action
            Result = $Result
            Detail = $Detail
        }
    }

    function Get-SafeAlias {
        <#
            Exchange rejects an alias containing spaces or most punctuation, and the
            error names the alias rather than the rule, so derive a legal one from
            the display name rather than letting the caller discover it the hard way.
        #>
        param(
            [Parameter(Mandatory)]
            [string]$Name
        )

        $safe = $Name -replace '[^\p{L}\p{Nd}\-_]', ''
        if ([string]::IsNullOrWhiteSpace($safe)) { $safe = 'sgeDiscoveryManagers' }
        if ($safe.Length -gt 64) { $safe = $safe.Substring(0, 64) }
        return $safe
    }

    function Resolve-RoleGroupIdentity {
        <#
            Return the identity the tenant actually answers to, from a list of
            candidate spellings.

            Add-RoleGroupMember resolves Name, DisplayName or DN, but a candidate
            that does not resolve fails with the same "not found" error as a group
            that is genuinely absent -- so the spelling is established here, once,
            rather than being guessed at the point of assignment.
        #>
        param(
            [Parameter(Mandatory)]
            [string[]]$Candidate
        )

        foreach ($name in $Candidate) {
            try {
                $roleGroup = Get-RoleGroup -Identity $name -ErrorAction Stop
                if ($roleGroup) {
                    Write-Log -Message "Role group resolved as '$($roleGroup.Name)' (display name '$($roleGroup.DisplayName)')." -Level 'VERBOSE'
                    return $roleGroup.Name
                }
            } catch {
                Write-Log -Message "Role group candidate '$name' did not resolve: $($_.Exception.Message)" -Level 'VERBOSE'
            }
        }

        throw "None of the role group names [$($Candidate -join ', ')] resolved in this tenant. Run Get-RoleGroup in Security & Compliance PowerShell to see what is present, and confirm the account running this script holds the Organization Management role group or the Role Management role."
    }

    function Add-RoleGroupMemberWithRetry {
        <#
            Add the group to a Purview role group, retrying while Purview still
            cannot see it.

            A newly created mail-enabled security group takes up to 60 minutes to
            replicate into the Security & Compliance directory.  Until it does,
            Add-RoleGroupMember fails with ManagementObjectNotFoundException --
            "Couldn't find object <name>. Please make sure that it was spelled
            correctly" -- which is indistinguishable from a typo and sends people
            looking in the wrong place.

            The retry deliberately drives the REAL operation rather than polling a
            proxy for it.  An earlier version polled Get-Recipient before switching
            sessions, which proved nothing: that ran in the Exchange Online session,
            where the group had just been created and therefore resolved instantly.
            Only a call in the Security & Compliance session tests the thing that
            actually has to be true.

            Any error that is NOT the not-found signature is a real failure and is
            rethrown immediately -- retrying a permissions error for an hour helps
            nobody.
        #>
        param(
            [Parameter(Mandatory)]
            [string]$RoleGroup,
            [Parameter(Mandatory)]
            [string]$MemberIdentity,
            [Parameter(Mandatory)]
            [int]$TimeoutSecond
        )

        $deadline = (Get-Date).AddSeconds($TimeoutSecond)
        $interval = 60
        $attempt = 0

        while ($true) {
            $attempt++

            try {
                Add-RoleGroupMember -Identity $RoleGroup -Member $MemberIdentity -ErrorAction Stop
                Write-Log -Message "Added '$MemberIdentity' to '$RoleGroup' on attempt $attempt."
                return $true
            } catch {
                $message = $_.Exception.Message

                $notVisiblePattern = @(
                    'ManagementObjectNotFoundException'
                    "Couldn't find object"
                    'could not be found'
                )
                $isNotYetVisible = $false
                foreach ($pattern in $notVisiblePattern) {
                    if ($message -match $pattern) { $isNotYetVisible = $true }
                }

                if (-not $isNotYetVisible) {
                    throw
                }

                if ((Get-Date) -ge $deadline) {
                    Write-Log -Message "'$MemberIdentity' is still not visible to Purview after $TimeoutSecond second(s) and $attempt attempt(s). This is replication lag, not a spelling error -- Microsoft documents up to 60 minutes. Re-run this script with the same parameters once it has caught up; it is idempotent and will skip everything already done." -Level 'WARNING'
                    return $false
                }

                $remaining = [int]($deadline - (Get-Date)).TotalSeconds
                Write-Log -Message "Purview cannot see '$MemberIdentity' yet (attempt $attempt). This is expected for a newly created group. Retrying in $interval s; giving up in $remaining s."
                Start-Sleep -Seconds $interval
            }
        }
    }
    #endregion Helper Functions

    $script:ResolvedLogPath = Resolve-LogDirectory -Preferred $LogPath
    $startTime = Get-Date

    if (-not $GroupAlias) {
        $GroupAlias = Get-SafeAlias -Name $GroupName
    }

    Write-Log -Message "========================================"
    Write-Log -Message "$ScriptName started"
    Write-Log -Message "========================================"
    Write-Log -Message "AuthMode          : $AuthMode"
    Write-Log -Message "RunAs             : $env:USERDOMAIN\$env:USERNAME"
    Write-Log -Message "Host              : $env:COMPUTERNAME"
    Write-Log -Message "Group             : $GroupName (alias $GroupAlias)"
    Write-Log -Message "Group SMTP        : $(if ($GroupPrimarySmtpAddress) { $GroupPrimarySmtpAddress } else { 'not supplied - required only if the group must be created' })"
    Write-Log -Message "Members           : $(if ($Member.Count -gt 0) { $Member -join ', ' } else { 'none supplied' })"
    Write-Log -Message "eDiscovery admins : $(if ($EDiscoveryAdministrator.Count -gt 0) { $EDiscoveryAdministrator -join ', ' } else { 'none supplied' })"
    Write-Log -Message "Exchange read role: $($GrantExchangeViewOnlyRecipient.IsPresent)"
    Write-Log -Message "Log directory     : $script:ResolvedLogPath"

    Initialize-RequiredModule -Name @('ExchangeOnlineManagement')
}

process {
    $result = @()
    $groupCreated = $false

    #region Phase 1 - Exchange Online
    try {
        Connect-ComplianceService -Service 'ExchangeOnline'

        #region Create or Find the Group
        $group = $null
        try {
            $group = Get-DistributionGroup -Identity $GroupName -ErrorAction Stop
        } catch {
            Write-Log -Message "Group '$GroupName' does not exist yet." -Level 'VERBOSE'
        }

        if ($group) {
            # A distribution group that is not -Type Security is silently useless
            # here: Purview accepts only mail-enabled SECURITY groups, and rejects
            # a plain distribution group with the same "not found" style error as a
            # missing group.
            $isSecurity = $group.RecipientTypeDetails -match 'MailUniversalSecurityGroup'

            if ($isSecurity) {
                Write-Log -Message "Group '$GroupName' already exists as a mail-enabled security group ($($group.PrimarySmtpAddress)). Reusing it."
                $result += Get-ResultRecord -Layer 'Exchange Online' -Target $GroupName -Action 'Create group' `
                    -Result 'AlreadyExists' -Detail "$($group.RecipientTypeDetails), $($group.PrimarySmtpAddress)"
            } else {
                throw "'$GroupName' exists but is a $($group.RecipientTypeDetails), not a mail-enabled security group. Purview role groups accept only MailUniversalSecurityGroup. Rename or remove it, or pass a different -GroupName."
            }
        } else {
            if (-not $GroupPrimarySmtpAddress) {
                throw "-GroupPrimarySmtpAddress is required to create '$GroupName'. A Purview role group will not accept a group that is not mail-enabled."
            }

            if ($PSCmdlet.ShouldProcess($GroupName, "Create mail-enabled security group ($GroupPrimarySmtpAddress)")) {
                $newGroupParam = @{
                    Name = $GroupName
                    DisplayName = $GroupName
                    Alias = $GroupAlias
                    PrimarySmtpAddress = $GroupPrimarySmtpAddress
                    Type = 'Security'
                    MemberJoinRestriction = 'Closed'
                    MemberDepartRestriction = 'Closed'
                    ErrorAction = 'Stop'
                }

                $group = New-DistributionGroup @newGroupParam
                $groupCreated = $true
                Write-Log -Message "Created mail-enabled security group '$GroupName' ($GroupPrimarySmtpAddress)."

                # A permission-holding group has no business in the address book,
                # and hiding it stops someone mailing it expecting a human.
                try {
                    Set-DistributionGroup -Identity $GroupName -HiddenFromAddressListsEnabled $true `
                        -RequireSenderAuthenticationEnabled $true -ErrorAction Stop
                    Write-Log -Message "Group hidden from address lists and closed to external senders."
                } catch {
                    Write-Log -Message "Group created but could not be hidden from address lists: $($_.Exception.Message)" -Level 'WARNING'
                }

                $result += Get-ResultRecord -Layer 'Exchange Online' -Target $GroupName -Action 'Create group' `
                    -Result 'Created' -Detail "MailUniversalSecurityGroup, $GroupPrimarySmtpAddress"
            } else {
                $result += Get-ResultRecord -Layer 'Exchange Online' -Target $GroupName -Action 'Create group' `
                    -Result 'WhatIf' -Detail "Would create a mail-enabled security group at $GroupPrimarySmtpAddress"
            }
        }
        #endregion Create or Find the Group

        #region Add Members
        $existingMember = @()
        if ($group) {
            try {
                $existingMember = @(Get-DistributionGroupMember -Identity $GroupName -ResultSize Unlimited -ErrorAction Stop |
                        ForEach-Object { $_.PrimarySmtpAddress.ToString().ToLower() })
            } catch {
                Write-Log -Message "Could not read current members of '$GroupName': $($_.Exception.Message)" -Level 'WARNING'
            }
        }

        foreach ($upn in $Member) {
            if ($existingMember -contains $upn.ToLower()) {
                Write-Log -Message "$upn is already a member of '$GroupName'. Skipping."
                $result += Get-ResultRecord -Layer 'Exchange Online' -Target $upn -Action 'Add group member' `
                    -Result 'AlreadyMember' -Detail $GroupName
                continue
            }

            if ($PSCmdlet.ShouldProcess($upn, "Add to group $GroupName")) {
                try {
                    Add-DistributionGroupMember -Identity $GroupName -Member $upn -ErrorAction Stop
                    Write-Log -Message "$upn added to '$GroupName'."
                    $result += Get-ResultRecord -Layer 'Exchange Online' -Target $upn -Action 'Add group member' `
                        -Result 'Added' -Detail $GroupName
                } catch {
                    Write-Log -Message "Failed to add $upn to '${GroupName}': $($_.Exception.Message)" -Level 'ERROR'
                    $result += Get-ResultRecord -Layer 'Exchange Online' -Target $upn -Action 'Add group member' `
                        -Result 'Failed' -Detail $_.Exception.Message
                }
            } else {
                $result += Get-ResultRecord -Layer 'Exchange Online' -Target $upn -Action 'Add group member' `
                    -Result 'WhatIf' -Detail "Would add to $GroupName"
            }
        }
        #endregion Add Members

        #region Exchange Read Role
        # Without this the group can search a held mailbox in Purview but cannot run
        # Get-Mailbox, so nobody in it can confirm from PowerShell that a hold is
        # actually set or list inactive mailboxes.
        if ($GrantExchangeViewOnlyRecipient) {
            $alreadyInExchangeRole = $false
            try {
                $current = @(Get-RoleGroupMember -Identity $ExchangeReadRoleGroup -ResultSize Unlimited -ErrorAction Stop |
                        ForEach-Object { $_.Name })
                $alreadyInExchangeRole = $current -contains $GroupName
            } catch {
                Write-Log -Message "Could not read members of '$ExchangeReadRoleGroup': $($_.Exception.Message)" -Level 'WARNING'
            }

            if ($alreadyInExchangeRole) {
                Write-Log -Message "'$GroupName' is already a member of '$ExchangeReadRoleGroup'."
                $result += Get-ResultRecord -Layer 'Exchange Online' -Target $GroupName -Action "Add to $ExchangeReadRoleGroup" `
                    -Result 'AlreadyAssigned' -Detail 'View-Only Recipients and View-Only Configuration'
            } elseif ($PSCmdlet.ShouldProcess($GroupName, "Add to Exchange role group $ExchangeReadRoleGroup")) {
                try {
                    Add-RoleGroupMember -Identity $ExchangeReadRoleGroup -Member $GroupName -ErrorAction Stop

                    # Verify rather than assume: read the membership back.
                    $verify = @(Get-RoleGroupMember -Identity $ExchangeReadRoleGroup -ResultSize Unlimited -ErrorAction Stop |
                            ForEach-Object { $_.Name })

                    if ($verify -contains $GroupName) {
                        Write-Log -Message "'$GroupName' added to '$ExchangeReadRoleGroup' and verified."
                        $result += Get-ResultRecord -Layer 'Exchange Online' -Target $GroupName -Action "Add to $ExchangeReadRoleGroup" `
                            -Result 'Assigned' -Detail 'View-Only Recipients and View-Only Configuration'
                    } else {
                        Write-Log -Message "Add-RoleGroupMember reported success but '$GroupName' is not in '$ExchangeReadRoleGroup'." -Level 'ERROR'
                        $result += Get-ResultRecord -Layer 'Exchange Online' -Target $GroupName -Action "Add to $ExchangeReadRoleGroup" `
                            -Result 'FailedVerification' -Detail 'Command succeeded but membership did not stick'
                    }
                } catch {
                    Write-Log -Message "Failed to add '$GroupName' to '${ExchangeReadRoleGroup}': $($_.Exception.Message)" -Level 'ERROR'
                    $result += Get-ResultRecord -Layer 'Exchange Online' -Target $GroupName -Action "Add to $ExchangeReadRoleGroup" `
                        -Result 'Failed' -Detail $_.Exception.Message
                }
            } else {
                $result += Get-ResultRecord -Layer 'Exchange Online' -Target $GroupName -Action "Add to $ExchangeReadRoleGroup" `
                    -Result 'WhatIf' -Detail 'Would grant View-Only Recipients and View-Only Configuration'
            }
        }
        #endregion Exchange Read Role

        # No visibility wait here on purpose.  Exchange Online resolves the group it
        # has just created instantly, so a poll in this session would return true
        # immediately and prove nothing about Purview.  The wait belongs in phase 2,
        # driving the real Add-RoleGroupMember call.
    } finally {
        Disconnect-ComplianceService
    }
    #endregion Phase 1 - Exchange Online

    #region Phase 2 - Security and Compliance
    # Deliberately a separate connection. See Connect-ComplianceService for why the
    # two services must never be held open together.
    try {
        Connect-ComplianceService -Service 'SecurityAndCompliance'

        # Establish the spelling this tenant answers to before assigning anything.
        $EDiscoveryRoleGroup = Resolve-RoleGroupIdentity -Candidate $EDiscoveryRoleGroupCandidate

        #region eDiscovery Manager Role Group
        $alreadyEDiscovery = $false
        try {
            $currentRoleMember = @(Get-RoleGroupMember -Identity $EDiscoveryRoleGroup -ResultSize Unlimited -ErrorAction Stop |
                    ForEach-Object { $_.Name })
            $alreadyEDiscovery = $currentRoleMember -contains $GroupName
        } catch {
            Write-Log -Message "Could not read members of the '$EDiscoveryRoleGroup' role group: $($_.Exception.Message)" -Level 'WARNING'
        }

        if ($alreadyEDiscovery) {
            Write-Log -Message "'$GroupName' is already a member of the '$EDiscoveryRoleGroup' role group."
            $result += Get-ResultRecord -Layer 'Purview' -Target $GroupName -Action "Add to $EDiscoveryRoleGroup" `
                -Result 'AlreadyAssigned' -Detail 'Compliance Search, Preview, Export, RMS Decrypt, Case Management, Hold, Review'
        } elseif ($PSCmdlet.ShouldProcess($GroupName, "Add to Purview role group $EDiscoveryRoleGroup")) {
            try {
                # Retries while Purview has not yet replicated the group. This is the
                # only place the propagation delay can actually be waited out, because
                # it is the only call that exercises the Security & Compliance
                # directory.
                $added = Add-RoleGroupMemberWithRetry -RoleGroup $EDiscoveryRoleGroup `
                    -MemberIdentity $GroupName -TimeoutSecond $GroupWaitSeconds

                if (-not $added) {
                    $result += Get-ResultRecord -Layer 'Purview' -Target $GroupName -Action "Add to $EDiscoveryRoleGroup" `
                        -Result 'FailedNotYetReplicated' `
                        -Detail "Purview still cannot see the group after waiting $GroupWaitSeconds second(s). This is replication lag, not a spelling error. Re-run this script with the same parameters once it catches up (Microsoft documents up to 60 minutes); it is idempotent."
                } else {
                    $verifyRoleMember = @(Get-RoleGroupMember -Identity $EDiscoveryRoleGroup -ResultSize Unlimited -ErrorAction Stop |
                            ForEach-Object { $_.Name })

                    if ($verifyRoleMember -contains $GroupName) {
                        Write-Log -Message "'$GroupName' added to the '$EDiscoveryRoleGroup' role group and verified."
                        $result += Get-ResultRecord -Layer 'Purview' -Target $GroupName -Action "Add to $EDiscoveryRoleGroup" `
                            -Result 'Assigned' -Detail 'Compliance Search, Preview, Export, RMS Decrypt, Case Management, Hold, Review'
                    } else {
                        Write-Log -Message "Add-RoleGroupMember reported success but '$GroupName' is not in '$EDiscoveryRoleGroup'." -Level 'ERROR'
                        $result += Get-ResultRecord -Layer 'Purview' -Target $GroupName -Action "Add to $EDiscoveryRoleGroup" `
                            -Result 'FailedVerification' -Detail 'Command succeeded but membership did not stick'
                    }
                }
            } catch {
                $detail = $_.Exception.Message
                Write-Log -Message "Failed to add '$GroupName' to '${EDiscoveryRoleGroup}': $detail" -Level 'ERROR'
                $result += Get-ResultRecord -Layer 'Purview' -Target $GroupName -Action "Add to $EDiscoveryRoleGroup" `
                    -Result 'Failed' -Detail $detail
            }
        } else {
            $result += Get-ResultRecord -Layer 'Purview' -Target $GroupName -Action "Add to $EDiscoveryRoleGroup" `
                -Result 'WhatIf' -Detail 'Would grant Compliance Search, Preview, Export, RMS Decrypt, Case Management, Hold, Review'
        }
        #endregion eDiscovery Manager Role Group

        #region eDiscovery Administrators
        # Individuals only. Microsoft does not permit a mail-enabled security group
        # in the eDiscovery Administrators subgroup, and Add-eDiscoveryCaseAdmin
        # rejects one.
        foreach ($upn in $EDiscoveryAdministrator) {
            if ($PSCmdlet.ShouldProcess($upn, 'Make eDiscovery Administrator')) {
                try {
                    Add-eDiscoveryCaseAdmin -User $upn -ErrorAction Stop | Out-Null
                    Write-Log -Message "$upn is now an eDiscovery Administrator."
                    $result += Get-ResultRecord -Layer 'Purview' -Target $upn -Action 'Make eDiscovery Administrator' `
                        -Result 'Assigned' -Detail 'Can access every eDiscovery case in the tenant'
                } catch {
                    $detail = $_.Exception.Message
                    $hint = if ($detail -match 'already') {
                        ' Already an eDiscovery Administrator.'
                    } else {
                        ' Requires the Case Management role first, which membership of the eDiscovery Manager role group supplies. If the group assignment has not propagated, wait and re-run.'
                    }
                    Write-Log -Message "Could not make $upn an eDiscovery Administrator: $detail$hint" -Level 'WARNING'
                    $result += Get-ResultRecord -Layer 'Purview' -Target $upn -Action 'Make eDiscovery Administrator' `
                        -Result 'Failed' -Detail "$detail$hint"
                }
            } else {
                $result += Get-ResultRecord -Layer 'Purview' -Target $upn -Action 'Make eDiscovery Administrator' `
                    -Result 'WhatIf' -Detail 'Would grant access to every eDiscovery case in the tenant'
            }
        }
        #endregion eDiscovery Administrators
    } finally {
        Disconnect-ComplianceService
    }
    #endregion Phase 2 - Security and Compliance

    #region Report
    Write-Log -Message "========================================"
    Write-Log -Message "=== RUN SUMMARY ==="

    $result | Group-Object Result | Sort-Object Count -Descending | ForEach-Object {
        Write-Log -Message "  $($_.Name) - $($_.Count) action(s)"
    }

    if ($groupCreated) {
        Write-Log -Message "The group was created during THIS run, so both propagation delays are still ahead of it. A group created minutes ago is not yet usable for search or export." -Level 'WARNING'
    }

    $failure = @($result | Where-Object { $_.Result -like 'Failed*' })
    if ($failure.Count -gt 0) {
        Write-Log -Message "=== FAILURES REQUIRING ATTENTION ==="
        foreach ($item in $failure) {
            Write-Log -Message "  [$($item.Layer)] $($item.Target) - $($item.Action) - $($item.Detail)" -Level 'WARNING'
        }
    }

    $csvPath = Join-Path $script:ResolvedLogPath "EDiscoveryAccessGroup-$Timestamp.csv"
    if ($result.Count -gt 0) {
        $result | Export-Csv -Path $csvPath -NoTypeInformation -Encoding UTF8
        Write-Log -Message "Results exported to: $csvPath"
    }

    Write-Log -Message "========================================"
    Write-Log -Message "NEXT: role assignments take 30-60 minutes to reach the search and export back ends."
    Write-Log -Message "Until they do, an eDiscovery search returns NO RESULTS rather than an error, which"
    Write-Log -Message "looks identical to a mailbox that genuinely holds nothing. Do not conclude a mailbox"
    Write-Log -Message "is empty during that window."
    Write-Log -Message "Verify with the eDiscovery RBAC Check diagnostic in the Purview portal:"
    Write-Log -Message "  Help > search 'Diag:edisRBACdiag' > enter the UPN > Run Tests"
    Write-Log -Message "Then confirm a specific mailbox is preserved with Test-MailboxPreservation.ps1."
    #endregion Report

    $duration = (Get-Date) - $startTime
    Write-Log -Message "$ScriptName completed in $($duration.ToString('hh\:mm\:ss'))"

    return $result
}

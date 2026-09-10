<#
.SYNOPSIS
    Stage 1 of Microsoft 365 offboarding.  Places terminated users' mailboxes on
    Litigation Hold so the mail data survives licence reclaim and account deletion.

.DESCRIPTION
    This script performs the non-destructive half of the offboarding process.  It
    finds terminated users, preserves their mailbox contents, and cuts off their
    access.  It deliberately does NOT remove licences and does NOT delete accounts.

    Why the order matters:

    Litigation Hold requires an Exchange Online Plan 2 entitlement (E3, E5, or the
    Exchange Online Archiving add-on) at the moment the hold is applied.  If the
    licence is stripped before the hold is set, the hold can no longer be applied,
    the mailbox is soft-deleted, and it is permanently unrecoverable after 30 days.
    The only safe sequence is:

        1. Apply the hold          <- this script
        2. Delete the AD account   <- manual, after sign-off (see Stage 2 report)
        3. The licence frees itself as the mailbox becomes an inactive mailbox

    An inactive mailbox is preserved for the hold duration, remains fully
    searchable through Microsoft Purview eDiscovery, and consumes no licence.

    Actions performed per user:
    - Confirms the user has a mailbox in Exchange Online.
    - Applies Litigation Hold with the configured duration and owner.
    - Re-reads the mailbox to verify the hold actually stamped (never assumes the
      Set-Mailbox call succeeded).
    - Revokes all sign-in sessions and refresh tokens through Microsoft Graph.
    - Records the currently assigned licence SKUs for the Stage 2 report.
    - Optionally disables the on-premises Active Directory account.
    - Optionally configures mail forwarding, a full-access delegate, and an
      automatic reply for handover.

    Three discovery modes:
    - Discover   : sweeps Entra ID for every sign-in-blocked account that has a
                   mailbox not yet on hold.  Intended for scheduled runs.
    - UserList   : processes an explicit list of addresses, or a CSV / text file of
                   addresses.  Intended for catching up on historical leavers.
    - Terminated : the steady-state termination sweep.  Matches only accounts that
                   are sign-in blocked AND own a user mailbox (never shared, room,
                   or equipment) AND carry no enabled Exchange Online service plan.
                   This is the fingerprint left behind by the termination runbook,
                   which strips the Exchange licence as the account is closed.

    The script is idempotent.  Mailboxes already on hold are reported and skipped,
    so it is safe to re-run on the same population repeatedly.

    The licence paradox, and how -TemporaryLicenseSku resolves it:

    Litigation Hold requires an Exchange Online Plan 2 entitlement at the moment the
    hold is applied, but the termination process removes exactly that entitlement.
    A mailbox found by -Terminated therefore cannot be held as it stands.

    -TemporaryLicenseSku closes the gap.  For each unlicensed mailbox the script
    assigns the nominated SKU, waits for Exchange to observe the new entitlement,
    applies and verifies the hold, and records that the mailbox is now holding a
    licence it did not previously consume.

    That licence is released by DELETING the account, not by removing the licence.
    Removing a licence from a live account soft-deletes the mailbox and destroys it
    after 30 days, hold or no hold.  Deleting the account converts the mailbox to an
    inactive mailbox, which is preserved for the hold duration and consumes nothing.
    The script never removes a licence and never deletes an account; it reports
    which accounts are ready for deletion so that step stays a human decision.

    Runtime support:
    - Azure Automation runbook using a Managed Identity (-AuthMode ManagedIdentity)
    - Windows Server scheduled task using certificate app-only auth (-AuthMode Certificate)
    - Manual run from a Windows Server or admin workstation (-AuthMode Interactive)

    Hybrid identity note:
    In a hybrid (Entra Connect synced) directory, accountEnabled flows from
    on-premises Active Directory to the cloud.  Disabling the cloud user is
    reverted at the next sync cycle, so -DisableAccount acts against on-premises
    AD and therefore requires a domain-joined host with the ActiveDirectory
    module.  It is unavailable in Azure Automation unless run on a Hybrid
    Runbook Worker.

.PARAMETER Discover
    Sweep Entra ID for all sign-in-blocked (accountEnabled = false) member accounts
    and process any whose mailbox is not already on Litigation Hold.  This is the
    default parameter set and the intended mode for scheduled runs.

.PARAMETER UserList
    An explicit list of user addresses to process, or the path to a single CSV or
    text file containing them.  A CSV must have a UserPrincipalName, EmailAddress,
    Email, or PrimarySmtpAddress column.  A text file is read one address per line.
    Use this mode to catch up on users terminated before the automation existed.

    A CSV is processed exactly as supplied.  The recipient-type and licence filters
    that -Terminated applies are deliberately NOT applied here, because a curated
    backlog list is already the product of human review.  The cleanup-project audit
    reports are the intended input: their UserPrincipalName column is picked up
    automatically.

.PARAMETER Terminated
    The steady-state termination sweep.  Selects accounts that satisfy all three
    conditions simultaneously:

      1. Sign-in blocked in Entra ID (accountEnabled = false)
      2. Mailbox RecipientTypeDetails is UserMailbox
         (SharedMailbox, RoomMailbox, EquipmentMailbox, and DiscoveryMailbox are
         all excluded - idle is their normal state and they are not leavers)
      3. No enabled Exchange Online service plan on the account

    Condition 3 is what makes this the termination signal rather than a generic
    disabled-account sweep, because licence removal is the deliberate last step of
    the termination runbook.

    Mailboxes matched this way cannot be held without an entitlement.  Supply
    -TemporaryLicenseSku to have the script assign one, or omit it to have the run
    report the population and stop without changing anything.

.PARAMETER TemporaryLicenseSku
    SKU part number to assign to an unlicensed mailbox so that Litigation Hold can
    be applied.  Must carry an Exchange Online Plan 2 entitlement - EXCHANGEARCHIVE_ADDON
    (Exchange Online Archiving) is the cheapest SKU that qualifies, but this tenant does
    not carry it; SPE_E3 (Microsoft 365 E3) is the SKU that is actually present here.
    Run Get-MgSubscribedSku -All to confirm what a given tenant holds before choosing.

    Before processing anything the script resolves the SKU against the tenant and
    confirms enough seats are free for the whole matched population.  A run that
    would exhaust the pool fails up front rather than half way through.

    The assignment is not undone by this script.  The licence is released when the
    account is deleted and the mailbox becomes inactive.  Every mailbox that
    received a temporary licence is listed in the run summary under "awaiting
    account deletion" so the seat is not left consumed indefinitely.

.PARAMETER LicenseWaitSeconds
    How long to wait for Exchange Online to observe a newly assigned licence before
    attempting the hold.  Defaults to 300 seconds.  Directory replication to the
    Exchange service is not instant, and applying the hold too early fails with the
    same error as having no licence at all.

.PARAMETER HoldTagSuffix
    Trailing token of the generated hold tag.  Defaults to 'Termination', producing
    a RetentionComment of the form:

        {DisplayName}-{yyyy-MM-dd}-Termination

    Litigation Hold has no name property in Exchange Online.  RetentionComment is
    the writable free-text field, it is visible in the Exchange admin center, and it
    is returned by Get-Mailbox, so the tag is stamped there.  LitigationHoldOwner is
    left holding the actual requesting administrator, which is what an auditor
    expects to find.

    Passing -RetentionComment explicitly overrides tag generation entirely.

.PARAMETER AuthMode
    How to authenticate to Exchange Online and Microsoft Graph.

    ManagedIdentity - Azure Automation.  Requires -Organization.  No secrets.
    Certificate     - Unattended on a Windows host.  Requires -Organization,
                      -AppId, -CertificateThumbprint, and -TenantId.
    Interactive     - Prompts for sign-in.  Requires -AdminUpn.

    Defaults to Interactive.

.PARAMETER Organization
    The tenant's primary or onmicrosoft.com domain, for example
    contoso.onmicrosoft.com.  Required for ManagedIdentity and Certificate modes.

.PARAMETER AppId
    Application (client) ID of the Entra ID app registration used for certificate
    app-only authentication.

.PARAMETER CertificateThumbprint
    Thumbprint of the authentication certificate held in the executing account's
    certificate store.  Used with -AuthMode Certificate.

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

.PARAMETER LitigationHoldDuration
    How long items are held, in days, or the string Unlimited.

    Defaults to 2555 days, which is seven years.  The duration is measured from the
    date each item was received or created, NOT from the date the hold was applied,
    so a 2555 day duration means items age out of the hold once they are seven
    years old.  Set to Unlimited only if the data must be preserved forever, and be
    aware that Unlimited defeats any seven-year fall-off requirement.

    See Litigation-Hold-7-Year-Retention.md in this directory.

.PARAMETER HoldOwner
    Value written to the mailbox LitigationHoldOwner property, recording who
    requested the hold.  Defaults to the executing account.

.PARAMETER RetentionComment
    Free-text comment stamped on the mailbox RetentionComment property explaining
    why the hold exists.  Visible to administrators in the Exchange admin center.

    When this parameter is not supplied the script generates a per-mailbox hold tag
    instead - see -HoldTagSuffix.  Supplying it pins the same literal comment on
    every mailbox in the run and disables tag generation.

.PARAMETER DisableAccount
    Also disable the user's on-premises Active Directory account.  Requires a
    domain-joined host and the ActiveDirectory module.  The script verifies both
    before attempting anything and fails clearly if they are missing rather than
    silently skipping.

.PARAMETER ForwardingAddress
    Forward incoming mail to this address and keep a copy in the original mailbox.
    Only permitted when the run resolves to a single user, to prevent a sweep from
    pointing every leaver's mail at one inbox.

.PARAMETER GrantFullAccessTo
    Grant this user Full Access to the mailbox for handover, without automapping it
    into their Outlook profile.  Only permitted when the run resolves to a single
    user.

.PARAMETER AutoReplyMessage
    Enable an external and internal automatic reply with this message.  Only
    permitted when the run resolves to a single user.

.PARAMETER MaxUser
    Safety cap on how many users a single run will act against.  Defaults to 50.
    A first Discover run against a tenant with years of untouched leavers can match
    hundreds of accounts, so the cap forces a deliberate decision before a large
    batch.  Raise it once the population is understood.

.PARAMETER ExcludeUpn
    Addresses to skip.  Use for shared or service accounts that are intentionally
    left sign-in blocked and must not be held.

.PARAMETER LogPath
    Directory for the log file and CSV output.  Defaults to C:\scripts\log.  In
    Azure Automation this falls back to the sandbox temp directory automatically,
    because C:\scripts is not writable there.

.PARAMETER SmtpServer
    SMTP relay for the run summary email.  When omitted, no email is sent.

.PARAMETER MailFrom
    From address for the run summary email.

.PARAMETER MailTo
    One or more recipients for the run summary email.  Defaults to
    infrastructure@solomoninsight.com.

.EXAMPLE
    .\Invoke-M365OffboardingHold.ps1 -Terminated -WhatIf -AdminUpn "admin@solomoninsight.com"

    Dry run of the steady-state termination sweep.  Lists every disabled, unlicensed
    user mailbox that would be held, and changes nothing.  Run this first, every time.

.EXAMPLE
    .\Invoke-M365OffboardingHold.ps1 -Terminated -TemporaryLicenseSku "SPE_E3" -SmtpServer "smtp.solomoninsight.com" -MailFrom "noreply@solomoninsight.com" -AdminUpn "admin@solomoninsight.com"

    The real termination run.  Assigns a Microsoft 365 E3 licence to each
    unlicensed mailbox, applies and verifies a seven-year hold tagged
    {DisplayName}-{yyyy-MM-dd}-Termination, and emails the HTML summary to
    infrastructure@solomoninsight.com.

.EXAMPLE
    .\Invoke-M365OffboardingHold.ps1 -UserList ".\cleanup-project\Report5-Disabled-UserMailboxes-No-Delegates-202608060137.csv" -AdminUpn "admin@solomoninsight.com" -MaxUser 30 -WhatIf

    Phase 1 of the backlog.  Reads the UserPrincipalName column of the Report 5
    audit CSV - the 27 disabled mailboxes with no delegates attached.

.EXAMPLE
    .\Invoke-M365OffboardingHold.ps1 -UserList ".\cleanup-project\Report4-Disabled-UserMailboxes-With-Delegates-202608060137.csv" -TemporaryLicenseSku "SPE_E3" -AdminUpn "admin@solomoninsight.com" -MaxUser 25

    Phase 2 of the backlog, run only after delegate sign-off.  See
    Report4-Delegate-Outreach-202608060137.md in cleanup-project for the contact list.

.EXAMPLE
    .\Invoke-M365OffboardingHold.ps1 -WhatIf

    Interactive dry run.  Shows every mailbox that would be placed on hold without
    changing anything.  Always do this first.

.EXAMPLE
    .\Invoke-M365OffboardingHold.ps1 -AuthMode Interactive -AdminUpn "admin@contoso.com"

    Manual run from a Windows Server.  Discovers sign-in-blocked accounts and places
    their mailboxes on a seven-year Litigation Hold.

.EXAMPLE
    .\Invoke-M365OffboardingHold.ps1 -UserList "jsmith@contoso.com","bjones@contoso.com" -AdminUpn "admin@contoso.com"

    Catch-up run against two named leavers.

.EXAMPLE
    .\Invoke-M365OffboardingHold.ps1 -UserList "C:\scripts\terminated-users.csv" -AdminUpn "admin@contoso.com" -MaxUser 200

    Catch-up run from a CSV of historical leavers, with the safety cap raised.

.EXAMPLE
    .\Invoke-M365OffboardingHold.ps1 -AuthMode ManagedIdentity -Organization "contoso.onmicrosoft.com"

    Unattended Azure Automation runbook using the Automation account's Managed
    Identity.  No credentials or certificates are stored anywhere.

.EXAMPLE
    .\Invoke-M365OffboardingHold.ps1 -AuthMode Certificate -Organization "contoso.onmicrosoft.com" -AppId "00000000-0000-0000-0000-000000000000" -CertificateThumbprint "ABC123..." -TenantId "11111111-1111-1111-1111-111111111111" -DisableAccount

    Unattended Windows Server scheduled task.  Places holds and disables the
    matching on-premises AD accounts.

.EXAMPLE
    .\Invoke-M365OffboardingHold.ps1 -UserList "jsmith@contoso.com" -AdminUpn "admin@contoso.com" -ForwardingAddress "manager@contoso.com" -GrantFullAccessTo "manager@contoso.com"

    Single-user termination with handover.  Places the hold, forwards new mail to
    the manager, and grants the manager access to the mailbox.

.INPUTS
    System.String[]
    Accepts user addresses through the -UserList parameter.

.OUTPUTS
    System.Management.Automation.PSCustomObject
    One result object per user with properties: UserPrincipalName, DisplayName,
    RecipientTypeDetails, ExchangeLicensed, MailboxFound, AlreadyOnHold,
    HoldApplied, HoldTag, LitigationHoldDate, LitigationHoldDuration,
    TemporaryLicenseAssigned, TemporaryLicenseSku, AwaitingAccountDeletion,
    SessionsRevoked, AccountDisabled, LicenseSkus, MailboxSizeGB, Status, Detail.

    CSV exported to {LogPath}\M365OffboardingHold-{timestamp}.csv
    Log written to  {LogPath}\Invoke-M365OffboardingHold-{yyyyMMdd}.log

.NOTES
    Version:        1.3
    Author:         Infrastructure Team
    Creation Date:  2026-07-26

    Change History:
    Date        Author                  Description
    ----------  ----------------------  -------------------------------------------
    2026-07-26  Infrastructure Team     Initial release.  Supersedes
                                        Export-Terminated-Mailbox-to-PST.ps1
    2026-08-06  Infrastructure Team     Added -Terminated discovery mode (disabled +
                                        user mailbox + no Exchange licence),
                                        -TemporaryLicenseSku to make the hold
                                        possible on an unlicensed mailbox, generated
                                        per-mailbox hold tags, and an HTML run
                                        summary defaulting to the infrastructure
                                        mailbox.
    2026-08-12  Infrastructure Team     Install missing required modules from the
                                        PowerShell Gallery on demand, and import the
                                        Microsoft.Graph.* modules before
                                        ExchangeOnlineManagement to avoid the 5.1
                                        assembly-load conflict that produced a
                                        "GetTokenAsync ... does not have an
                                        implementation" TypeLoadException.
    2026-08-12  Infrastructure Team     Corrected -TemporaryLicenseSku examples and hint
                                        text from EXCHANGEARCHIVE_ADDON to SPE_E3.  Live
                                        run against this tenant confirmed via
                                        Get-MgSubscribedSku that EXCHANGEARCHIVE_ADDON is
                                        not a purchased SKU here; SPE_E3 (Microsoft 365
                                        E3) is the SKU actually present that carries an
                                        Exchange Online Plan 2 entitlement.
    2026-08-14  Infrastructure Team     Stop the run when a Microsoft.Graph submodule was
                                        installed during this session instead of carrying
                                        on into an unexplained Connect-MgGraph failure.
                                        Observed on a host with no Graph SDK: the four
                                        submodules installed at 09:29-09:31, the Gallery
                                        warned that Microsoft.Graph.Authentication was
                                        already in use, and Connect-MgGraph then failed
                                        with "InteractiveBrowserCredential authentication
                                        failed:" and nothing after the colon.  Also
                                        flatten the exception chain so the real MSAL or
                                        broker cause is printed rather than that empty
                                        message, retry the Graph connection three times,
                                        and add -UseDeviceCode to bypass the browser and
                                        WAM broker entirely.

    Required PowerShell modules:
    - ExchangeOnlineManagement 3.0.0 or later
    - Microsoft.Graph.Authentication                2.39.0 exactly
    - Microsoft.Graph.Users                         2.39.0 exactly
    - Microsoft.Graph.Users.Actions                 2.39.0 exactly
    - Microsoft.Graph.Identity.DirectoryManagement  2.39.0 exactly  (SKU lookup)
    - ActiveDirectory  (only when using -DisableAccount)

    The Microsoft.Graph.* modules must all be the SAME version, which is why the
    script installs and imports them at one pinned build rather than taking the
    highest of each.  A submodule holds no copy of the shared assemblies; it binds
    by strong name to the exact Microsoft.Graph.Authentication build already in the
    AppDomain.  Update one submodule on its own and the next run fails with

        Get-MgSubscribedSku : Could not load file or assembly
        'Microsoft.Graph.Authentication, Version=2.38.1.0, Culture=neutral,
        PublicKeyToken=31bf3856ad364e35' or one of its dependencies.
        The system cannot find the file specified.

    The file is on disk.  This is a binding failure reported as a missing file, so
    it reads as a corrupt install and is not one -- reinstalling the Graph SDK does
    not fix it, aligning the versions does.  To move the pin, change
    $GraphModuleVersion in the Configuration Variables region.

    Required permissions:

    Exchange Online, app-only (Certificate or ManagedIdentity):
    - Office 365 Exchange Online -> Exchange.ManageAsApp application permission
    - The service principal must hold the Exchange Administrator directory role

    Microsoft Graph application permissions:
    - User.Read.All             (discovery and licence detail)
    - Organization.Read.All     (resolving SKU part numbers)
    - User.RevokeSessions.All   (revoking sign-in sessions)
    - User.ReadWrite.All        (only when using -TemporaryLicenseSku)

    Interactive mode requires an account with the Exchange Administrator role, or
    the Exchange Online Mail Recipients and Legal Hold roles.

    Deliberate non-goals:
    - This script never removes a licence.  Licence removal before account
      deletion destroys the mailbox.  -TemporaryLicenseSku only ever adds.
    - This script never deletes an account.  See Get-M365OffboardingStatus.ps1
      for the Stage 2 sign-off report.
    - This script does not export PST files.  New-MailboxExportRequest has never
      worked against Exchange Online, and New-ComplianceSearchAction -Export was
      retired on 26 May 2025.  See O365-Offboarding-Runbook.md.

    Related documentation in this directory:
    - Termination-Litigation-Hold-Process.md   (the end-to-end process this serves)
    - O365-Offboarding-Runbook.md
    - Litigation-Hold-Access-Guide.md
    - Litigation-Hold-7-Year-Retention.md
    - cleanup-project\Report4-Delegate-Outreach-202608060137.md
#>

[CmdletBinding(SupportsShouldProcess, DefaultParameterSetName = 'Discover')]
param(
    [Parameter(ParameterSetName = 'Discover', HelpMessage = "Sweep Entra ID for sign-in-blocked accounts")]
    [switch]$Discover,

    [Parameter(Mandatory, ParameterSetName = 'UserList', Position = 0, ValueFromPipeline = $true,
        HelpMessage = "Addresses to process, or the path to a CSV or text file of addresses")]
    [ValidateNotNullOrEmpty()]
    [string[]]$UserList,

    [Parameter(Mandatory, ParameterSetName = 'Terminated',
        HelpMessage = "Sweep for disabled user mailboxes that carry no Exchange licence")]
    [switch]$Terminated,

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

    [Parameter(HelpMessage = "Hold duration in days, or 'Unlimited'. Default 2555 (seven years)")]
    [ValidateScript({
            if ($_ -eq 'Unlimited' -or (($_ -as [int]) -and [int]$_ -gt 0)) { $true }
            else { throw "LitigationHoldDuration must be a positive number of days or the string 'Unlimited'." }
        })]
    [string]$LitigationHoldDuration = '2555',

    [Parameter(HelpMessage = "Recorded as the owner of the hold")]
    [ValidateNotNullOrEmpty()]
    [string]$HoldOwner = "$env:USERDOMAIN\$env:USERNAME",

    [Parameter(HelpMessage = "Comment stamped on the mailbox explaining the hold")]
    [ValidateNotNullOrEmpty()]
    [string]$RetentionComment = 'Employee offboarding - mailbox preserved for retention. Do not remove the licence before the account is deleted.',

    [Parameter(HelpMessage = "SKU part number to assign so an unlicensed mailbox can be held")]
    [ValidateNotNullOrEmpty()]
    [string]$TemporaryLicenseSku,

    [Parameter(HelpMessage = "Seconds to wait for Exchange to observe a new licence (default 300)")]
    [ValidateRange(0, 1800)]
    [int]$LicenseWaitSeconds = 300,

    [Parameter(HelpMessage = "Trailing token of the generated hold tag (default 'Termination')")]
    [ValidateNotNullOrEmpty()]
    [string]$HoldTagSuffix = 'Termination',

    [Parameter(HelpMessage = "Also disable the on-premises AD account (requires domain-joined host)")]
    [switch]$DisableAccount,

    [Parameter(HelpMessage = "Forward incoming mail here and keep a copy (single-user runs only)")]
    [ValidateNotNullOrEmpty()]
    [string]$ForwardingAddress,

    [Parameter(HelpMessage = "Grant this user Full Access for handover (single-user runs only)")]
    [ValidateNotNullOrEmpty()]
    [string]$GrantFullAccessTo,

    [Parameter(HelpMessage = "Enable an automatic reply with this message (single-user runs only)")]
    [ValidateNotNullOrEmpty()]
    [string]$AutoReplyMessage,

    [Parameter(HelpMessage = "Maximum users a single run will act against (default 50)")]
    [ValidateRange(1, 10000)]
    [int]$MaxUser = 50,

    [Parameter(HelpMessage = "Addresses to skip, such as shared or service accounts")]
    [string[]]$ExcludeUpn = @(),

    [Parameter(HelpMessage = "Directory for log and CSV output")]
    [ValidateNotNullOrEmpty()]
    [string]$LogPath = 'C:\scripts\log',

    [Parameter(HelpMessage = "SMTP relay for the run summary email")]
    [ValidateNotNullOrEmpty()]
    [string]$SmtpServer,

    [Parameter(HelpMessage = "From address for the run summary email")]
    [ValidateNotNullOrEmpty()]
    [string]$MailFrom,

    [Parameter(HelpMessage = "Recipients for the run summary email")]
    [string[]]$MailTo = @('infrastructure@solomoninsight.com')
)

begin {
    #region Configuration Variables
    $ScriptName = 'Invoke-M365OffboardingHold'
    $Timestamp = Get-Date -Format 'yyyyMMddHHmm'

    # Every Microsoft.Graph.* submodule is pinned to this one version.
    #
    # The submodules do not carry their own copy of the shared assemblies; they
    # bind to the exact build that Microsoft.Graph.Authentication has already put
    # in the AppDomain, by strong name.  Import-Module with no version picks the
    # highest build of each module independently, so a box that has, say,
    # Microsoft.Graph.Users 2.39.0 and Microsoft.Graph.Identity.DirectoryManagement
    # 2.38.1 loads Authentication 2.39.0 first and then every DirectoryManagement
    # cmdlet -- Get-MgSubscribedSku among them -- fails with
    #
    #   Could not load file or assembly 'Microsoft.Graph.Authentication,
    #   Version=2.38.1.0 ...'. The system cannot find the file specified.
    #
    # The file is on disk.  It is a binding failure reported as a missing file,
    # which is why it reads like a broken install and is not one.  Pinning is the
    # fix, not "reinstall the Graph SDK": versions drift apart again the next time
    # any one submodule is updated on its own.
    #
    # To move the pin, bump this string and confirm every module in $needed
    # publishes that version (Find-Module <name> -RequiredVersion <version>).
    $GraphModuleVersion = '2.39.0'

    # Substrings that identify an insufficient-licence failure from Set-Mailbox.
    $LicenseErrorSignature = @(
        'Plan 2'
        'not licensed'
        'no license'
        'ExchangeOnlineEnterprise'
        'ArchiveAddOn'
        'requires a license'
    )

    # PersistedCapabilities values that indicate Litigation Hold eligibility.
    $HoldCapableCapability = @('BPOS_S_Enterprise', 'BPOS_S_ArchiveAddOn', 'BPOS_S_EnterprisePremium')
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
        <#
            Azure Automation sandboxes cannot write to C:\scripts.  Fall back to the
            sandbox temp directory so logging never becomes the reason a run fails.
        #>
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
            different builds of the same dependency assemblies (Azure.*,
            Microsoft.Identity*, the JWT stack).  Whichever imports first wins the
            binding.  Import EXO first and Graph then fails to load with
            "Method 'GetTokenAsync' ... does not have an implementation"
            (a TypeLoadException); import the Graph modules first and both coexist.
            Callers must therefore pass the Microsoft.Graph.* modules ahead of
            ExchangeOnlineManagement.

            Version alignment is load-bearing for the same reason.  Every
            Microsoft.Graph.* module named here is installed and imported at
            -GraphVersion exactly; mixed builds bind against different
            Microsoft.Graph.Authentication assemblies and fail as a missing file.
            ExchangeOnlineManagement is not pinned -- it owns its own assemblies
            and tracks its own release cadence.
        #>
        param(
            [Parameter(Mandatory)]
            [string[]]$Name,

            [Parameter(Mandatory)]
            [string]$GraphVersion,

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
            # A Graph submodule is satisfied only by the pinned version.  Testing
            # presence alone would skip the install for a box that already has some
            # other build on disk, and the pinned Import-Module below would then
            # fail with a bare "The specified module was not loaded".
            $isGraph = $moduleName -like 'Microsoft.Graph.*'
            $wanted = if ($isGraph) { $GraphVersion } else { $null }

            $present = if ($isGraph) {
                @(Get-Module -Name $moduleName -ListAvailable |
                        Where-Object { $_.Version.ToString() -eq $wanted }).Count -gt 0
            } else {
                @(Get-Module -Name $moduleName -ListAvailable).Count -gt 0
            }

            if (-not $present) {
                $label = if ($isGraph) { "$moduleName $wanted" } else { $moduleName }
                Write-Log -Message "Module '$label' is not installed; installing from the PowerShell Gallery (scope $Scope)..." -Level 'WARNING'

                if (-not (Get-PackageProvider -Name NuGet -ListAvailable -ErrorAction SilentlyContinue)) {
                    Install-PackageProvider -Name NuGet -MinimumVersion '2.8.5.201' -Scope $Scope -Force -ErrorAction Stop | Out-Null
                }

                $installArgs = @{
                    Name = $moduleName
                    Scope = $Scope
                    Force = $true
                    AllowClobber = $true
                    ErrorAction = 'Stop'
                }
                if ($isGraph) { $installArgs['RequiredVersion'] = $wanted }

                try {
                    Install-Module @installArgs
                } catch {
                    $manual = if ($isGraph) {
                        "Install-Module $moduleName -RequiredVersion $wanted -Scope $Scope -Force -AllowClobber"
                    } else {
                        "Install-Module $moduleName -Scope $Scope"
                    }
                    throw "Failed to install required module '$label' from the PowerShell Gallery: $($_.Exception.Message). Install it manually with: $manual"
                }

                Write-Log -Message "Module '$label' installed." -Level 'INFO'
                $installed += $moduleName
            }

            # Import eagerly and in order so the shared assemblies bind correctly,
            # rather than leaving it to command autoloading, which loads whichever
            # module is touched first (Connect-ExchangeOnline, in this script).
            if ($isGraph) {
                Import-Module -Name $moduleName -RequiredVersion $wanted -ErrorAction Stop
            } else {
                Import-Module -Name $moduleName -ErrorAction Stop
            }
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
            throw ("Installed {0} at version {1} during this session, so this session cannot connect to Microsoft Graph.`n`n" -f ($graphInstalled -join ', '), $GraphVersion) +
            "Microsoft Graph submodules share the assemblies loaded by Microsoft.Graph.Authentication. That module was " +
            "already imported before the others were installed, so it could not be updated, and Connect-MgGraph would " +
            "now fail with an unexplained authentication error rather than a useful one.`n`n" +
            "NOTHING HAS BEEN CHANGED IN THE TENANT. No mailbox was touched.`n`n" +
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
            non-transient one in full.

            Retried for the same reason Test-MailboxPreservation.ps1 retries its
            Exchange connection: interactive sign-in through the local token broker
            fails intermittently on the same host and account minutes apart.  What is
            different here is the reporting -- a bare Connect-MgGraph failure is
            unreadable, so the exception chain is flattened and a concrete next step
            is attached.
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

                # Connect-MgGraph has been observed returning without throwing while
                # leaving no usable context, which then fails much later inside an
                # unrelated Graph call.  Assert the context here instead.
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
        <#
            Establish Exchange Online and Microsoft Graph sessions using the
            selected authentication model.  Parameter completeness is validated
            here so an unattended run fails immediately with an actionable message.
        #>
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
                    Scopes = @('User.Read.All', 'Organization.Read.All', 'User.RevokeSessions.All')
                    NoWelcome = $true
                }
                if ($UseDeviceCode) { $graphParam['UseDeviceCode'] = $true }

                Connect-GraphInteractive -Parameter $graphParam
            }
        }
    }

    function Get-AddressFromFile {
        <#
            Read addresses from a CSV (any recognised address column) or a plain
            text file, one per line.  Returns a de-duplicated array.
        #>
        param(
            [Parameter(Mandatory)]
            [string]$Path
        )

        $addressColumn = @('UserPrincipalName', 'EmailAddress', 'Email', 'PrimarySmtpAddress', 'Mail', 'UPN')
        $collected = @()

        if ($Path -match '\.csv$') {
            $rows = Import-Csv -Path $Path -ErrorAction Stop
            if (-not $rows) {
                throw "CSV '$Path' contained no rows."
            }

            $columnName = $addressColumn | Where-Object { $_ -in $rows[0].PSObject.Properties.Name } | Select-Object -First 1
            if (-not $columnName) {
                throw "CSV '$Path' has no recognised address column. Expected one of: $($addressColumn -join ', ')"
            }

            Write-Log -Message "Reading addresses from CSV column '$columnName'." -Level 'VERBOSE'
            $collected = $rows | ForEach-Object { $_.$columnName }
        } else {
            $collected = Get-Content -Path $Path -ErrorAction Stop
        }

        $cleaned = $collected |
            ForEach-Object { if ($_) { $_.ToString().Trim() } } |
            Where-Object { $_ -and $_ -match '@' } |
            Select-Object -Unique

        if (-not $cleaned) {
            throw "No valid addresses found in '$Path'."
        }

        return @($cleaned)
    }

    function Get-OffboardingCandidate {
        <#
            Resolve the population to act against.

            Discover   - every sign-in-blocked member account.
            UserList   - each supplied address, processed exactly as given.  No
                         recipient-type or licence filter is applied, because a
                         curated backlog list is already the product of review.
            Terminated - sign-in blocked AND owns a user mailbox AND carries no
                         enabled Exchange entitlement.  All three conditions
                         together are the fingerprint of the termination runbook.

            Returns objects with UserPrincipalName, DisplayName, GraphId,
            AccountEnabled, SyncedFromOnPrem, ExchangeLicensed, and LicenseSkus.
        #>
        param(
            [Parameter(Mandatory)]
            [string]$Mode,
            [string[]]$Address
        )

        $selectProperty = @('id', 'userPrincipalName', 'displayName', 'accountEnabled', 'mail',
            'assignedLicenses', 'assignedPlans', 'onPremisesSyncEnabled')
        $found = @()

        if ($Mode -eq 'UserList') {
            foreach ($item in $Address) {
                try {
                    $graphUser = Get-MgUser -UserId $item -Property $selectProperty -ErrorAction Stop
                    $found += $graphUser
                } catch {
                    Write-Log -Message "Could not resolve '$item' in Entra ID: $($_.Exception.Message)" -Level 'WARNING'
                    $script:UnresolvedAddress += $item
                }
            }
            Write-Log -Message "Resolved $($found.Count) of $($Address.Count) supplied address(es)."
        } else {
            Write-Log -Message "Querying Entra ID for sign-in-blocked member accounts..."
            $found = @(Get-MgUser -Filter "accountEnabled eq false and userType eq 'Member'" `
                    -Property $selectProperty -All -ErrorAction Stop)
            Write-Log -Message "Entra ID returned $($found.Count) sign-in-blocked member account(s)."

            if ($Mode -eq 'Terminated') {
                $beforeLicence = $found.Count
                $found = @($found | Where-Object { -not (Test-ExchangeLicense -AssignedPlan $_.AssignedPlans) })
                Write-Log -Message "$($beforeLicence - $found.Count) account(s) still carry an enabled Exchange entitlement and are not yet terminated. $($found.Count) remain."

                if ($found.Count -gt 0) {
                    # One bulk Exchange call rather than a Get-Mailbox per candidate.
                    # Room, equipment, and shared mailboxes are excluded here: idle is
                    # their normal state and none of them represent a leaver.
                    Write-Log -Message "Reading user mailboxes from Exchange Online to exclude shared, room, and equipment mailboxes..."
                    $userMailboxUpn = @{}
                    Get-Mailbox -RecipientTypeDetails UserMailbox -ResultSize Unlimited -ErrorAction Stop |
                        ForEach-Object {
                            if ($_.UserPrincipalName) { $userMailboxUpn[$_.UserPrincipalName.ToLower()] = $true }
                        }
                    Write-Log -Message "Exchange reports $($userMailboxUpn.Count) user mailbox(es) in the tenant."

                    $beforeType = $found.Count
                    $found = @($found | Where-Object {
                            $_.UserPrincipalName -and $userMailboxUpn.ContainsKey($_.UserPrincipalName.ToLower())
                        })
                    Write-Log -Message "$($beforeType - $found.Count) account(s) excluded for having no user mailbox. $($found.Count) match all termination criteria."
                }
            }
        }

        return $found | ForEach-Object {
            [PSCustomObject]@{
                UserPrincipalName = $_.UserPrincipalName
                DisplayName = $_.DisplayName
                GraphId = $_.Id
                AccountEnabled = $_.AccountEnabled
                SyncedFromOnPrem = [bool]$_.OnPremisesSyncEnabled
                ExchangeLicensed = (Test-ExchangeLicense -AssignedPlan $_.AssignedPlans)
                LicenseSkus = (Resolve-SkuPartNumber -AssignedLicense $_.AssignedLicenses)
            }
        }
    }

    function Resolve-SkuPartNumber {
        <#
            Translate assigned licence SKU GUIDs into readable part numbers using a
            cached tenant subscription lookup.  Returns a semicolon-delimited
            string, or 'None' when no licence is assigned.
        #>
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

    function Test-ExchangeLicense {
        <#
            Decide whether an account currently carries an Exchange Online
            entitlement, which is the signal the termination runbook removes.

            Graph keeps historical assignedPlans entries after a licence is taken
            away and marks them capabilityStatus 'Deleted', so an unfiltered look at
            the collection reports every past leaver as still licensed.  Only
            'Enabled' counts.
        #>
        param(
            [AllowNull()]
            $AssignedPlan
        )

        if (-not $AssignedPlan) { return $false }

        foreach ($plan in $AssignedPlan) {
            if ($plan.Service -eq 'exchange' -and $plan.CapabilityStatus -eq 'Enabled') {
                return $true
            }
        }

        return $false
    }

    function Get-HoldTag {
        <#
            Build the per-mailbox hold tag stamped into RetentionComment:

                {DisplayName}-{yyyy-MM-dd}-{Suffix}

            Litigation Hold has no name property in Exchange Online.
            RetentionComment is the writable free-text field, so the tag lives
            there.  Characters that would make the tag hard to search for are
            folded to a hyphen, and runs of hyphens are collapsed.
        #>
        param(
            [Parameter(Mandatory)]
            [AllowEmptyString()]
            [string]$Name,
            [Parameter(Mandatory)]
            [string]$Suffix
        )

        $safeName = if ([string]::IsNullOrWhiteSpace($Name)) { 'UnknownUser' } else { $Name }
        $safeName = ($safeName -replace '[^\p{L}\p{Nd}]+', '-').Trim('-')
        if (-not $safeName) { $safeName = 'UnknownUser' }

        return "$safeName-$(Get-Date -Format 'yyyy-MM-dd')-$Suffix"
    }

    function Resolve-TemporaryLicenseSku {
        <#
            Resolve a SKU part number to its GUID and confirm the tenant has enough
            free seats for the whole matched population.

            Checked once, before any mailbox is touched.  A run that would exhaust
            the pool half way through leaves some mailboxes held and others not,
            which is the worst possible outcome to unpick by hand.
        #>
        param(
            [Parameter(Mandatory)]
            [string]$PartNumber,
            [Parameter(Mandatory)]
            [int]$RequiredSeat
        )

        $sku = Get-MgSubscribedSku -All -ErrorAction Stop |
            Where-Object { $_.SkuPartNumber -eq $PartNumber } |
            Select-Object -First 1

        if (-not $sku) {
            $available = (Get-MgSubscribedSku -All -ErrorAction SilentlyContinue |
                    Select-Object -ExpandProperty SkuPartNumber) -join ', '
            throw "SKU '$PartNumber' is not present in this tenant. Available SKUs: $available"
        }

        $free = [int]$sku.PrepaidUnits.Enabled - [int]$sku.ConsumedUnits

        Write-Log -Message "SKU $PartNumber resolved to $($sku.SkuId). Seats: $($sku.PrepaidUnits.Enabled) purchased, $($sku.ConsumedUnits) consumed, $free free. $RequiredSeat required."

        if ($free -lt $RequiredSeat) {
            throw "SKU '$PartNumber' has $free free seat(s) but $RequiredSeat mailbox(es) need one. Buy more seats, or lower -MaxUser and work through the population in batches."
        }

        return [PSCustomObject]@{
            SkuId = $sku.SkuId
            PartNumber = $sku.SkuPartNumber
            FreeSeat = $free
        }
    }

    function Set-TemporaryLicense {
        <#
            Assign a licence so that Litigation Hold becomes possible on a mailbox
            the termination process has already stripped.

            This only ever adds.  The licence is released later by DELETING the
            account, which converts the mailbox to an inactive mailbox.  Removing
            the licence from a live account instead would soft-delete the mailbox
            and destroy it 30 days later, hold or no hold.
        #>
        [CmdletBinding(SupportsShouldProcess)]
        param(
            [Parameter(Mandatory)]
            [string]$GraphId,
            [Parameter(Mandatory)]
            [string]$Upn,
            [Parameter(Mandatory)]
            [string]$SkuId
        )

        if (-not $PSCmdlet.ShouldProcess($Upn, "Assign licence $SkuId to make Litigation Hold possible")) {
            return $false
        }

        Set-MgUserLicense -UserId $GraphId `
            -AddLicenses @(@{ SkuId = $SkuId }) -RemoveLicenses @() -ErrorAction Stop | Out-Null

        Write-Log -Message "Licence $SkuId assigned to $Upn."
        return $true
    }

    function Wait-ExchangeLicense {
        <#
            Block until Exchange Online observes a newly assigned licence.

            Directory replication into the Exchange service is not instant.  Calling
            Set-Mailbox too early fails with the identical error to having no
            licence at all, so an impatient run looks like a licensing problem
            rather than a timing one.
        #>
        param(
            [Parameter(Mandatory)]
            [string]$Upn,
            [Parameter(Mandatory)]
            [int]$TimeoutSecond,
            [Parameter(Mandatory)]
            [string[]]$CapableCapability
        )

        if ($TimeoutSecond -le 0) { return $false }

        $deadline = (Get-Date).AddSeconds($TimeoutSecond)
        $interval = 15

        Write-Log -Message "Waiting up to $TimeoutSecond second(s) for Exchange to observe the licence on $Upn..."

        while ((Get-Date) -lt $deadline) {
            Start-Sleep -Seconds $interval

            try {
                $current = Get-Mailbox -Identity $Upn -ErrorAction Stop
                foreach ($cap in @($current.PersistedCapabilities)) {
                    if ($cap -in $CapableCapability) {
                        Write-Log -Message "Exchange now reports $Upn as hold capable ($cap)."
                        return $true
                    }
                }
            } catch {
                Write-Log -Message "Capability poll for ${Upn} reported: $($_.Exception.Message)" -Level 'VERBOSE'
            }
        }

        Write-Log -Message "Timed out waiting for the licence to reach Exchange for $Upn. Attempting the hold anyway." -Level 'WARNING'
        return $false
    }

    function Test-OnPremCapability {
        <#
            Confirm the host can act against on-premises AD before -DisableAccount
            is honoured.  Fails loudly rather than silently skipping, because a
            silent skip would leave an account enabled that an operator believes
            was disabled.
        #>
        if (-not (Get-Module -Name ActiveDirectory -ListAvailable)) {
            throw "-DisableAccount requires the ActiveDirectory module, which is not installed on this host. Run from a domain-joined server with RSAT, or omit -DisableAccount and disable the account manually."
        }

        Import-Module ActiveDirectory -ErrorAction Stop

        try {
            $null = Get-ADDomain -ErrorAction Stop
        } catch {
            throw "-DisableAccount requires a reachable Active Directory domain. This host cannot contact a domain controller: $($_.Exception.Message)"
        }

        Write-Log -Message "On-premises AD capability confirmed." -Level 'VERBOSE'
    }

    function Test-LicenseError {
        param(
            [Parameter(Mandatory)]
            [string]$Message
        )

        foreach ($signature in $LicenseErrorSignature) {
            if ($Message -match [regex]::Escape($signature)) { return $true }
        }
        return $false
    }

    function ConvertTo-HtmlSafeText {
        <#
            Escape values that land inside the HTML summary.  Display names are
            free text from the directory and routinely contain ampersands, which
            silently break the surrounding markup if passed through raw.
        #>
        param(
            [AllowNull()]
            $Value
        )

        if ($null -eq $Value) { return '' }

        return [System.Net.WebUtility]::HtmlEncode([string]$Value)
    }

    function Send-RunSummary {
        <#
            Build and send the HTML run summary.

            Structured by what the reader has to DO rather than by what the script
            did: anything needing human follow-up appears above anything that
            completed cleanly, so a scan of the first screen is enough to know
            whether the run needs attention.
        #>
        param(
            [Parameter(Mandatory)]
            [AllowEmptyCollection()]
            [array]$Result,
            [Parameter(Mandatory)]
            [string]$CsvPath,
            [Parameter(Mandatory)]
            [string]$Mode
        )

        if (-not $SmtpServer -or -not $MailFrom -or $MailTo.Count -eq 0) {
            Write-Log -Message "Email summary skipped (SmtpServer, MailFrom, or MailTo not supplied)." -Level 'VERBOSE'
            return
        }

        $applied = @($Result | Where-Object { $_.Status -eq 'HoldApplied' })
        $already = @($Result | Where-Object { $_.Status -eq 'AlreadyOnHold' })
        $failed = @($Result | Where-Object { $_.Status -like 'Failed*' })
        $other = @($Result | Where-Object {
                $_.Status -notin @('HoldApplied', 'AlreadyOnHold') -and $_.Status -notlike 'Failed*'
            })
        $awaiting = @($Result | Where-Object { $_.AwaitingAccountDeletion })

        $subject = "M365 Litigation Hold - $($applied.Count) held, $($failed.Count) failed, $($awaiting.Count) awaiting account deletion"

        $tableStyle = 'border-collapse:collapse;font-family:Segoe UI,Arial,sans-serif;font-size:13px;width:100%;'
        $thStyle = 'background:#1f3864;color:#ffffff;text-align:left;padding:6px 8px;border:1px solid #c9c9c9;'
        $tdStyle = 'padding:6px 8px;border:1px solid #c9c9c9;vertical-align:top;'

        function Get-ReportSection {
            param(
                [string]$Title,
                [string]$Intro,
                [array]$Row,
                [string[]]$Header,
                [string]$Accent = '#1f3864'
            )

            if ($Row.Count -eq 0) { return '' }

            $headHtml = ($Header | ForEach-Object { "<th style=`"$thStyle`">$_</th>" }) -join ''
            $bodyHtml = ($Row -join "`n")

            return @"
<h3 style="font-family:Segoe UI,Arial,sans-serif;color:$Accent;margin:22px 0 4px 0;">$Title</h3>
<p style="font-family:Segoe UI,Arial,sans-serif;font-size:13px;color:#444;margin:0 0 8px 0;">$Intro</p>
<table style="$tableStyle"><tr>$headHtml</tr>
$bodyHtml
</table>
"@
        }

        $failedRow = $failed | ForEach-Object {
            "<tr><td style=`"$tdStyle`">$(ConvertTo-HtmlSafeText $_.DisplayName)</td><td style=`"$tdStyle`">$(ConvertTo-HtmlSafeText $_.UserPrincipalName)</td><td style=`"$tdStyle`">$(ConvertTo-HtmlSafeText $_.Status)</td><td style=`"$tdStyle`">$(ConvertTo-HtmlSafeText $_.Detail)</td></tr>"
        }

        $awaitingRow = $awaiting | ForEach-Object {
            "<tr><td style=`"$tdStyle`">$(ConvertTo-HtmlSafeText $_.DisplayName)</td><td style=`"$tdStyle`">$(ConvertTo-HtmlSafeText $_.UserPrincipalName)</td><td style=`"$tdStyle`">$(ConvertTo-HtmlSafeText $_.TemporaryLicenseSku)</td><td style=`"$tdStyle`">$(ConvertTo-HtmlSafeText $_.HoldTag)</td></tr>"
        }

        $appliedRow = $applied | ForEach-Object {
            "<tr><td style=`"$tdStyle`">$(ConvertTo-HtmlSafeText $_.DisplayName)</td><td style=`"$tdStyle`">$(ConvertTo-HtmlSafeText $_.UserPrincipalName)</td><td style=`"$tdStyle`">$(ConvertTo-HtmlSafeText $_.HoldTag)</td><td style=`"$tdStyle`">$(ConvertTo-HtmlSafeText $_.LitigationHoldDuration)</td><td style=`"$tdStyle`">$(ConvertTo-HtmlSafeText $_.MailboxSizeGB)</td></tr>"
        }

        $otherRow = $other | ForEach-Object {
            "<tr><td style=`"$tdStyle`">$(ConvertTo-HtmlSafeText $_.DisplayName)</td><td style=`"$tdStyle`">$(ConvertTo-HtmlSafeText $_.UserPrincipalName)</td><td style=`"$tdStyle`">$(ConvertTo-HtmlSafeText $_.Status)</td><td style=`"$tdStyle`">$(ConvertTo-HtmlSafeText $_.Detail)</td></tr>"
        }

        $alreadyRow = $already | ForEach-Object {
            "<tr><td style=`"$tdStyle`">$(ConvertTo-HtmlSafeText $_.DisplayName)</td><td style=`"$tdStyle`">$(ConvertTo-HtmlSafeText $_.UserPrincipalName)</td><td style=`"$tdStyle`">$(ConvertTo-HtmlSafeText $_.LitigationHoldDate)</td><td style=`"$tdStyle`">$(ConvertTo-HtmlSafeText $_.LitigationHoldDuration)</td></tr>"
        }

        $section = @()
        $section += Get-ReportSection -Title "Failed - action required" -Accent '#b00020' `
            -Intro 'These mailboxes are NOT preserved. Do not delete these accounts and do not remove their licences until the hold succeeds.' `
            -Header @('Name', 'Address', 'Status', 'Detail') -Row $failedRow

        $section += Get-ReportSection -Title "Held, awaiting account deletion" -Accent '#a15c00' `
            -Intro 'A licence was assigned to these mailboxes so the hold could be applied, and they are consuming that licence now. Deleting the account releases it and converts the mailbox to an inactive mailbox. Removing the licence instead destroys the mailbox after 30 days.' `
            -Header @('Name', 'Address', 'Licence assigned', 'Hold tag') -Row $awaitingRow

        $section += Get-ReportSection -Title "Litigation Hold applied" `
            -Intro 'Verified by re-reading the mailbox after the change. Contents are preserved and searchable through Microsoft Purview eDiscovery.' `
            -Header @('Name', 'Address', 'Hold tag', 'Duration (days)', 'Size (GB)') -Row $appliedRow

        $section += Get-ReportSection -Title "Skipped or not processed" -Accent '#555555' `
            -Intro 'No mailbox, excluded, or reported by a -WhatIf run.' `
            -Header @('Name', 'Address', 'Status', 'Detail') -Row $otherRow

        $section += Get-ReportSection -Title "Already on hold" -Accent '#555555' `
            -Intro 'Left untouched. This script is idempotent and safe to re-run.' `
            -Header @('Name', 'Address', 'Hold date', 'Duration (days)') -Row $alreadyRow

        $sectionHtml = ($section | Where-Object { $_ }) -join "`n"

        $body = @"
<div style="font-family:Segoe UI,Arial,sans-serif;color:#222;">
<h2 style="color:#1f3864;margin:0 0 2px 0;">Microsoft 365 Termination - Litigation Hold</h2>
<p style="margin:0 0 14px 0;color:#666;font-size:12px;">
Run $(Get-Date -Format 'yyyy-MM-dd HH:mm') &nbsp;|&nbsp; Mode $Mode &nbsp;|&nbsp; Host $env:COMPUTERNAME
</p>

<table style="border-collapse:collapse;font-size:13px;margin-bottom:6px;">
<tr>
<td style="padding:8px 16px;border:1px solid #c9c9c9;background:#eef3fa;"><b style="font-size:20px;">$($applied.Count)</b><br>held</td>
<td style="padding:8px 16px;border:1px solid #c9c9c9;background:#fdf1e6;"><b style="font-size:20px;">$($awaiting.Count)</b><br>awaiting deletion</td>
<td style="padding:8px 16px;border:1px solid #c9c9c9;background:#f7f7f7;"><b style="font-size:20px;">$($already.Count)</b><br>already held</td>
<td style="padding:8px 16px;border:1px solid #c9c9c9;background:$(if ($failed.Count -gt 0) { '#fbe3e6' } else { '#f7f7f7' });"><b style="font-size:20px;">$($failed.Count)</b><br>failed</td>
</tr>
</table>

$sectionHtml

<h3 style="color:#1f3864;margin:22px 0 4px 0;">What this run did not do</h3>
<ul style="font-size:13px;margin:0 0 8px 0;">
<li>No licence was removed from any account.</li>
<li>No account was deleted.</li>
<li>No delegate permission was changed.</li>
</ul>
<p style="font-size:13px;">
Deleting the account is the step that releases the licence and turns the mailbox into an
inactive mailbox. It is deliberately manual. Run <code>Get-M365OffboardingStatus.ps1</code>
for the Stage 2 sign-off report before deleting anything.
</p>
<p style="font-size:12px;color:#666;margin-top:18px;">
Full results: $(ConvertTo-HtmlSafeText $CsvPath)<br>
Generated by Invoke-M365OffboardingHold.ps1 on $env:COMPUTERNAME
</p>
</div>
"@

        try {
            Send-MailMessage -SmtpServer $SmtpServer -From $MailFrom -To $MailTo `
                -Subject $subject -Body $body -BodyAsHtml -Encoding ([System.Text.Encoding]::UTF8) -ErrorAction Stop
            Write-Log -Message "Summary email sent to $($MailTo -join ', ')."
        } catch {
            Write-Log -Message "Failed to send summary email: $($_.Exception.Message)" -Level 'WARNING'
        }
    }
    #endregion Helper Functions

    $script:ResolvedLogPath = Resolve-LogDirectory -Preferred $LogPath
    $script:SkuLookup = $null
    $script:UnresolvedAddress = @()
    $script:PipelineAddress = @()
    $startTime = Get-Date

    Write-Log -Message "========================================"
    Write-Log -Message "$ScriptName started"
    Write-Log -Message "========================================"
    Write-Log -Message "Mode              : $($PSCmdlet.ParameterSetName)"
    Write-Log -Message "AuthMode          : $AuthMode"
    Write-Log -Message "RunAs             : $env:USERDOMAIN\$env:USERNAME"
    Write-Log -Message "Host              : $env:COMPUTERNAME"
    Write-Log -Message "Hold duration     : $LitigationHoldDuration $(if ($LitigationHoldDuration -ne 'Unlimited') { 'day(s)' })"
    Write-Log -Message "Disable AD account: $($DisableAccount.IsPresent)"
    Write-Log -Message "Max users         : $MaxUser"
    Write-Log -Message "Hold tag          : $(if ($PSBoundParameters.ContainsKey('RetentionComment')) { "fixed - $RetentionComment" } else { "{DisplayName}-$(Get-Date -Format 'yyyy-MM-dd')-$HoldTagSuffix" })"
    Write-Log -Message "Temporary licence : $(if ($TemporaryLicenseSku) { "$TemporaryLicenseSku (wait up to $LicenseWaitSeconds s)" } else { 'not supplied' })"
    Write-Log -Message "Log directory     : $script:ResolvedLogPath"

    if ($LitigationHoldDuration -eq 'Unlimited') {
        Write-Log -Message "Hold duration is Unlimited. Items will never age out of the hold, which defeats a seven-year fall-off requirement. See Litigation-Hold-7-Year-Retention.md." -Level 'WARNING'
    }

    # Ensure and import the required modules up front, installing any that are
    # missing.  Order matters: the Microsoft.Graph.* modules must import before
    # ExchangeOnlineManagement or Graph fails to load (see Initialize-RequiredModule).
    # Microsoft.Graph.Identity.DirectoryManagement supplies Get-MgSubscribedSku, used
    # both to translate SKU GUIDs for the report and to reserve temporary seats.
    # Every Microsoft.Graph.* module here is pinned to $GraphModuleVersion; mixing
    # builds is what produces the "Could not load file or assembly
    # 'Microsoft.Graph.Authentication, Version=...'" failure on Get-MgSubscribedSku.
    $needed = @('Microsoft.Graph.Authentication', 'Microsoft.Graph.Users',
        'Microsoft.Graph.Users.Actions', 'Microsoft.Graph.Identity.DirectoryManagement',
        'ExchangeOnlineManagement')
    Initialize-RequiredModule -Name $needed -GraphVersion $GraphModuleVersion

    if ($DisableAccount) {
        Test-OnPremCapability
    }

    Connect-OffboardingService -Mode $AuthMode
}

process {
    # Collect pipeline input; the real work happens once in end{} so that
    # single-user guards can evaluate the complete population.
    if ($PSCmdlet.ParameterSetName -eq 'UserList') {
        $script:PipelineAddress += $UserList
    }
}

end {
    $result = @()

    try {
        #region Resolve Population
        $address = @()

        if ($PSCmdlet.ParameterSetName -eq 'UserList') {
            $supplied = @($script:PipelineAddress | Select-Object -Unique)

            # A single element that resolves to a file is treated as a list file.
            if ($supplied.Count -eq 1 -and $supplied[0] -notmatch '@' -and (Test-Path -Path $supplied[0] -PathType Leaf)) {
                Write-Log -Message "Treating '$($supplied[0])' as an address list file."
                $address = Get-AddressFromFile -Path $supplied[0]
            } else {
                $address = $supplied
            }

            Write-Log -Message "$($address.Count) address(es) supplied for processing."
        }

        $candidate = Get-OffboardingCandidate -Mode $PSCmdlet.ParameterSetName -Address $address

        if ($ExcludeUpn.Count -gt 0) {
            $before = @($candidate).Count
            $candidate = $candidate | Where-Object { $_.UserPrincipalName -notin $ExcludeUpn }
            $excluded = $before - @($candidate).Count
            if ($excluded -gt 0) {
                Write-Log -Message "Excluded $excluded account(s) by -ExcludeUpn."
            }
        }

        $candidate = @($candidate)

        if ($candidate.Count -eq 0) {
            Write-Log -Message "No accounts matched. Nothing to do." -Level 'WARNING'
            return
        }

        if ($candidate.Count -gt $MaxUser) {
            throw "$($candidate.Count) accounts matched but -MaxUser is $MaxUser. Review the population first, then re-run with a higher -MaxUser. This cap exists to stop an unreviewed first sweep acting on hundreds of accounts."
        }

        # Handover options act on a mailbox individually and must never be applied
        # across a sweep, which would point every leaver's mail at one inbox.
        $handoverOption = @()
        if ($ForwardingAddress) { $handoverOption += '-ForwardingAddress' }
        if ($GrantFullAccessTo) { $handoverOption += '-GrantFullAccessTo' }
        if ($AutoReplyMessage) { $handoverOption += '-AutoReplyMessage' }

        if ($handoverOption.Count -gt 0 -and $candidate.Count -gt 1) {
            throw "$($handoverOption -join ', ') may only be used when the run resolves to a single user, but $($candidate.Count) accounts matched. Applying handover settings across a batch would forward every leaver's mail to the same recipient."
        }

        Write-Log -Message "Processing $($candidate.Count) account(s)."
        #endregion Resolve Population

        #region Reserve Temporary Licences
        # Litigation Hold needs an Exchange Plan 2 entitlement at the moment it is
        # applied, but the termination runbook removes exactly that.  Resolve and
        # reserve the seats up front: a pool that runs dry half way through leaves
        # some mailboxes held and others not, which is the worst state to unpick.
        $unlicensed = @($candidate | Where-Object { -not $_.ExchangeLicensed })
        $temporarySku = $null

        if ($unlicensed.Count -gt 0) {
            Write-Log -Message "$($unlicensed.Count) of $($candidate.Count) matched account(s) carry no enabled Exchange entitlement."

            if ($TemporaryLicenseSku) {
                $temporarySku = Resolve-TemporaryLicenseSku -PartNumber $TemporaryLicenseSku -RequiredSeat $unlicensed.Count
                Write-Log -Message "Each unlicensed mailbox will receive $($temporarySku.PartNumber) so the hold can be applied. The licence is released when the account is deleted, NOT by removing it."
            } else {
                Write-Log -Message "No -TemporaryLicenseSku supplied. Litigation Hold will be attempted anyway and is expected to fail on these $($unlicensed.Count) mailbox(es). Re-run with -TemporaryLicenseSku (for example SPE_E3 -- run Get-MgSubscribedSku -All to confirm what this tenant actually holds) to have the script license them itself." -Level 'WARNING'
            }
        }
        #endregion Reserve Temporary Licences

        #region Apply Holds
        foreach ($user in $candidate) {
            $upn = $user.UserPrincipalName
            Write-Log -Message "----------------------------------------"
            Write-Log -Message "Processing $upn ($($user.DisplayName))"

            # The hold tag is generated per mailbox unless the caller pinned a
            # literal -RetentionComment for the whole run.
            $holdComment = if ($PSBoundParameters.ContainsKey('RetentionComment')) {
                $RetentionComment
            } else {
                Get-HoldTag -Name $user.DisplayName -Suffix $HoldTagSuffix
            }

            $record = [PSCustomObject]@{
                UserPrincipalName = $upn
                DisplayName = $user.DisplayName
                RecipientTypeDetails = $null
                ExchangeLicensed = $user.ExchangeLicensed
                MailboxFound = $false
                AlreadyOnHold = $false
                HoldApplied = $false
                HoldTag = $holdComment
                LitigationHoldDate = $null
                LitigationHoldDuration = $null
                TemporaryLicenseAssigned = $false
                TemporaryLicenseSku = $null
                AwaitingAccountDeletion = $false
                SessionsRevoked = $false
                AccountDisabled = $false
                LicenseSkus = $user.LicenseSkus
                MailboxSizeGB = $null
                Status = 'NotProcessed'
                Detail = ''
            }

            #region Locate Mailbox
            $mailbox = $null
            try {
                $mailbox = Get-Mailbox -Identity $upn -ErrorAction Stop
                $record.MailboxFound = $true
                $record.RecipientTypeDetails = $mailbox.RecipientTypeDetails
            } catch {
                Write-Log -Message "No mailbox found for $upn. Skipping." -Level 'WARNING'
                $record.Status = 'NoMailbox'
                $record.Detail = $_.Exception.Message
                $result += $record
                continue
            }

            try {
                $stats = Get-MailboxStatistics -Identity $upn -ErrorAction Stop
                if ($stats.TotalItemSize) {
                    $byteText = [regex]::Match($stats.TotalItemSize.ToString(), '\(([\d,]+) bytes\)')
                    if ($byteText.Success) {
                        $record.MailboxSizeGB = [math]::Round(([double]($byteText.Groups[1].Value -replace ',', '')) / 1GB, 2)
                    }
                }
            } catch {
                Write-Log -Message "Could not read mailbox statistics for ${upn}: $($_.Exception.Message)" -Level 'VERBOSE'
            }
            #endregion Locate Mailbox

            #region Idempotency Check
            if ($mailbox.LitigationHoldEnabled) {
                Write-Log -Message "$upn is already on Litigation Hold (applied $($mailbox.LitigationHoldDate), duration $($mailbox.LitigationHoldDuration)). Skipping hold."
                $record.AlreadyOnHold = $true
                $record.LitigationHoldDate = $mailbox.LitigationHoldDate
                $record.LitigationHoldDuration = $mailbox.LitigationHoldDuration
                $record.Status = 'AlreadyOnHold'
            } else {
                # Best-effort licence pre-check.  Informational only: the authoritative
                # answer is whether Set-Mailbox succeeds, so a heuristic miss must not
                # block a mailbox that would actually have held successfully.
                $capability = @($mailbox.PersistedCapabilities)
                $looksHoldCapable = $false
                foreach ($cap in $capability) {
                    if ($cap -in $HoldCapableCapability) { $looksHoldCapable = $true }
                }

                #region Temporary Licence
                # A mailbox the termination runbook has already stripped cannot be
                # held as it stands.  Assign the nominated SKU, wait for Exchange to
                # observe it, then continue.  Only ever adds a licence - the seat is
                # released later by deleting the account, which converts the mailbox
                # to an inactive mailbox.
                if (-not $looksHoldCapable -and $temporarySku) {
                    Write-Log -Message "$upn is not hold capable (capabilities: $($capability -join ', ')). Assigning $($temporarySku.PartNumber)."

                    try {
                        $assigned = Set-TemporaryLicense -GraphId $user.GraphId -Upn $upn -SkuId $temporarySku.SkuId

                        if ($assigned) {
                            $record.TemporaryLicenseAssigned = $true
                            $record.TemporaryLicenseSku = $temporarySku.PartNumber
                            $null = Wait-ExchangeLicense -Upn $upn -TimeoutSecond $LicenseWaitSeconds `
                                -CapableCapability $HoldCapableCapability
                        }
                    } catch {
                        $record.Status = 'FailedLicenseAssignment'
                        $record.Detail = "Could not assign $($temporarySku.PartNumber): $($_.Exception.Message)"
                        Write-Log -Message "Failed to assign $($temporarySku.PartNumber) to ${upn}: $($_.Exception.Message)" -Level 'ERROR'
                        $result += $record
                        continue
                    }
                } elseif (-not $looksHoldCapable) {
                    Write-Log -Message "$upn does not appear to carry an Exchange Plan 2 entitlement (capabilities: $($capability -join ', ')). Attempting the hold anyway." -Level 'WARNING'
                }
                #endregion Temporary Licence

                if ($PSCmdlet.ShouldProcess($upn, "Apply Litigation Hold (duration $LitigationHoldDuration, tag $holdComment)")) {
                    try {
                        $holdParam = @{
                            Identity = $upn
                            LitigationHoldEnabled = $true
                            LitigationHoldOwner = $HoldOwner
                            RetentionComment = $holdComment
                            LitigationHoldDuration = $LitigationHoldDuration
                            ErrorAction = 'Stop'
                        }

                        Set-Mailbox @holdParam

                        # Verify rather than assume.  Re-read the mailbox and confirm the
                        # hold actually stamped before reporting success.
                        $verify = Get-Mailbox -Identity $upn -ErrorAction Stop

                        if ($verify.LitigationHoldEnabled) {
                            $record.HoldApplied = $true
                            $record.LitigationHoldDate = $verify.LitigationHoldDate
                            $record.LitigationHoldDuration = $verify.LitigationHoldDuration
                            $record.HoldTag = $verify.RetentionComment
                            $record.Status = 'HoldApplied'

                            # A seat assigned by this run stays consumed until the
                            # account is deleted.  Flag it so the summary can chase it
                            # rather than leaving the licence quietly spent.
                            if ($record.TemporaryLicenseAssigned) {
                                $record.AwaitingAccountDeletion = $true
                                Write-Log -Message "$upn now holds $($record.TemporaryLicenseSku). Delete the account to release it and convert the mailbox to an inactive mailbox." -Level 'WARNING'
                            }

                            Write-Log -Message "Litigation Hold applied and verified for $upn (tag '$($verify.RetentionComment)', date $($verify.LitigationHoldDate), duration $($verify.LitigationHoldDuration))."
                        } else {
                            $record.Status = 'FailedVerification'
                            $record.Detail = 'Set-Mailbox reported success but LitigationHoldEnabled is still false.'
                            Write-Log -Message "Hold verification FAILED for $upn. Set-Mailbox reported success but the hold is not set. Do not remove this licence." -Level 'ERROR'
                        }
                    } catch {
                        $errorText = $_.Exception.Message
                        if (Test-LicenseError -Message $errorText) {
                            $record.Status = 'FailedLicenseRequired'
                            $record.Detail = "Exchange Online Plan 2 entitlement required to apply Litigation Hold. $errorText"
                            $hint = if ($record.TemporaryLicenseAssigned) {
                                "The licence was assigned but Exchange had not observed it within $LicenseWaitSeconds second(s). Re-run for this mailbox; the seat is already in place."
                            } else {
                                'Re-run with -TemporaryLicenseSku (for example SPE_E3 -- run Get-MgSubscribedSku -All to confirm what this tenant actually holds) to have the script license the mailbox itself.'
                            }
                            Write-Log -Message "Cannot hold $upn - Plan 2 entitlement required. $hint $errorText" -Level 'ERROR'
                        } else {
                            $record.Status = 'FailedHold'
                            $record.Detail = $errorText
                            Write-Log -Message "Failed to apply hold for ${upn}: $errorText" -Level 'ERROR'
                        }
                    }
                } else {
                    $record.Status = 'WhatIf'
                    $licenceNote = if (-not $looksHoldCapable -and $temporarySku) {
                        " Would first assign $($temporarySku.PartNumber), which the mailbox would then consume until the account is deleted."
                    } elseif (-not $looksHoldCapable) {
                        ' Mailbox is not hold capable and no -TemporaryLicenseSku was supplied, so this would fail.'
                    } else {
                        ''
                    }
                    $record.Detail = "Would apply Litigation Hold with duration $LitigationHoldDuration and tag '$holdComment'.$licenceNote"
                }
            }
            #endregion Idempotency Check

            # Everything below is access removal and handover.  Only proceed when the
            # mailbox is genuinely preserved, so a failed hold cannot be followed by
            # actions that make the failure look like a completed offboarding.
            $preserved = $record.HoldApplied -or $record.AlreadyOnHold

            #region Revoke Sessions
            if ($preserved -and $PSCmdlet.ShouldProcess($upn, 'Revoke sign-in sessions and refresh tokens')) {
                try {
                    $null = Revoke-MgUserSignInSession -UserId $user.GraphId -ErrorAction Stop
                    $record.SessionsRevoked = $true
                    Write-Log -Message "Sign-in sessions revoked for $upn."
                } catch {
                    Write-Log -Message "Failed to revoke sessions for ${upn}: $($_.Exception.Message)" -Level 'WARNING'
                    $record.Detail = ("$($record.Detail) Session revoke failed: $($_.Exception.Message)").Trim()
                }
            }
            #endregion Revoke Sessions

            #region Handover Settings
            if ($preserved -and $ForwardingAddress -and $PSCmdlet.ShouldProcess($upn, "Forward mail to $ForwardingAddress")) {
                try {
                    Set-Mailbox -Identity $upn -ForwardingSmtpAddress $ForwardingAddress `
                        -DeliverToMailboxAndForward $true -ErrorAction Stop
                    Write-Log -Message "Mail forwarding set to $ForwardingAddress (copy retained in mailbox)."
                } catch {
                    Write-Log -Message "Failed to set forwarding for ${upn}: $($_.Exception.Message)" -Level 'WARNING'
                }
            }

            if ($preserved -and $GrantFullAccessTo -and $PSCmdlet.ShouldProcess($upn, "Grant Full Access to $GrantFullAccessTo")) {
                try {
                    $null = Add-MailboxPermission -Identity $upn -User $GrantFullAccessTo `
                        -AccessRights FullAccess -AutoMapping:$false -ErrorAction Stop
                    Write-Log -Message "Full Access granted to $GrantFullAccessTo (automapping disabled)."
                } catch {
                    Write-Log -Message "Failed to grant Full Access on ${upn}: $($_.Exception.Message)" -Level 'WARNING'
                }
            }

            if ($preserved -and $AutoReplyMessage -and $PSCmdlet.ShouldProcess($upn, 'Enable automatic reply')) {
                try {
                    Set-MailboxAutoReplyConfiguration -Identity $upn -AutoReplyState Enabled `
                        -InternalMessage $AutoReplyMessage -ExternalMessage $AutoReplyMessage `
                        -ExternalAudience All -ErrorAction Stop
                    Write-Log -Message "Automatic reply enabled for $upn."
                } catch {
                    Write-Log -Message "Failed to set automatic reply for ${upn}: $($_.Exception.Message)" -Level 'WARNING'
                }
            }
            #endregion Handover Settings

            #region Disable On-Premises Account
            if ($preserved -and $DisableAccount) {
                if ($PSCmdlet.ShouldProcess($upn, 'Disable on-premises Active Directory account')) {
                    try {
                        $adUser = Get-ADUser -Filter "UserPrincipalName -eq '$upn'" -Properties Enabled, Description -ErrorAction Stop

                        if (-not $adUser) {
                            Write-Log -Message "No on-premises AD account found for $upn. It may be a cloud-only user." -Level 'WARNING'
                        } elseif (-not $adUser.Enabled) {
                            Write-Log -Message "On-premises account for $upn is already disabled."
                            $record.AccountDisabled = $true
                        } else {
                            Disable-ADAccount -Identity $adUser.DistinguishedName -ErrorAction Stop
                            Set-ADUser -Identity $adUser.DistinguishedName `
                                -Description "Offboarded $(Get-Date -Format 'yyyy-MM-dd') - mailbox on Litigation Hold" -ErrorAction Stop
                            $record.AccountDisabled = $true
                            Write-Log -Message "On-premises AD account disabled for $upn."
                        }
                    } catch {
                        Write-Log -Message "Failed to disable on-premises account for ${upn}: $($_.Exception.Message)" -Level 'ERROR'
                        $record.Detail = ("$($record.Detail) AD disable failed: $($_.Exception.Message)").Trim()
                    }
                }
            } elseif ($preserved -and -not $user.AccountEnabled) {
                # Discovered population is already sign-in blocked.
                $record.AccountDisabled = $true
            }
            #endregion Disable On-Premises Account

            $result += $record
        }
        #endregion Apply Holds

        #region Report
        Write-Log -Message "========================================"
        Write-Log -Message "=== RUN SUMMARY ==="

        $result | Group-Object Status | Sort-Object Count -Descending | ForEach-Object {
            Write-Log -Message "  $($_.Name) - $($_.Count) account(s)"
        }

        $failure = @($result | Where-Object { $_.Status -like 'Failed*' })
        if ($failure.Count -gt 0) {
            Write-Log -Message "=== FAILURES REQUIRING ATTENTION ==="
            foreach ($item in $failure) {
                Write-Log -Message "  $($item.UserPrincipalName) - $($item.Status) - $($item.Detail)" -Level 'WARNING'
            }
            Write-Log -Message "Do NOT remove licences for the accounts above. Their mailboxes are not preserved." -Level 'WARNING'
        }

        $awaitingDeletion = @($result | Where-Object { $_.AwaitingAccountDeletion })
        if ($awaitingDeletion.Count -gt 0) {
            Write-Log -Message "=== AWAITING ACCOUNT DELETION ==="
            Write-Log -Message "$($awaitingDeletion.Count) mailbox(es) received a licence so the hold could be applied and are consuming it now." -Level 'WARNING'
            foreach ($item in $awaitingDeletion) {
                Write-Log -Message "  $($item.UserPrincipalName) - holding $($item.TemporaryLicenseSku)" -Level 'WARNING'
            }
            Write-Log -Message "Delete these accounts to release the seats. Deleting converts the mailbox to an inactive mailbox, which is preserved for the hold duration at no licence cost. Do NOT remove the licence instead - that soft-deletes the mailbox and destroys it after 30 days." -Level 'WARNING'
        }

        if ($script:UnresolvedAddress.Count -gt 0) {
            Write-Log -Message "=== UNRESOLVED ADDRESSES ==="
            foreach ($item in $script:UnresolvedAddress) {
                Write-Log -Message "  $item - not found in Entra ID" -Level 'WARNING'
            }
        }

        $csvPath = Join-Path $script:ResolvedLogPath "M365OffboardingHold-$Timestamp.csv"
        if ($result.Count -gt 0) {
            $result | Export-Csv -Path $csvPath -NoTypeInformation -Encoding UTF8
            Write-Log -Message "Results exported to: $csvPath"
            Send-RunSummary -Result $result -CsvPath $csvPath -Mode $PSCmdlet.ParameterSetName
        }

        Write-Log -Message "REMINDER: no licences were removed and no accounts were deleted."
        Write-Log -Message "Licences must stay assigned until the account is deleted and the mailbox becomes inactive."
        Write-Log -Message "Run Get-M365OffboardingStatus.ps1 for the Stage 2 sign-off report."
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

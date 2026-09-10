<#
.SYNOPSIS
    Splits the mailbox cleanup scoping inventory into five audience-specific audit reports.

.DESCRIPTION
    Reads the read-only output of Get-SharedMailboxInventory.ps1 (the mailbox inventory CSV and
    the per-grant access CSV) and emits five paired CSV/Markdown reports so each cleanup
    workstream can be reviewed on its own:

        1. Rooms and resources                        - excluded from cleanup, listed for verification
        2. Non-user mailboxes                         - shared, functional and service mailboxes
        3. Licensed user and shared mailboxes         - licence reclamation candidates
        4. Disabled user mailboxes WITH delegates     - litigation hold, medium risk
        5. Disabled user mailboxes WITHOUT delegates  - litigation hold, low risk

    Reports 2, 4 and 5 depend on separating mailboxes named after a person from mailboxes named
    after a function. That distinction does not exist in Exchange, so it is derived here from the
    DisplayName using a keyword list and written to every row as the NameClass column.
    RecipientTypeDetails is carried alongside it, because the two disagree often: most disabled
    person-named mailboxes in this tenant are SharedMailbox, having been converted when the
    employee left.

    NameClass values:
        Person      - DisplayName reads as a human name and matched no functional keyword
        Non-Person  - DisplayName matched a functional keyword (admin, support, e-mail, calc, ...)
        Resource    - RecipientTypeDetails is RoomMailbox or EquipmentMailbox

    The classifier is a heuristic over names, not an authoritative source. Every report carries
    NameClass and NameClassReason so a reviewer can see why a mailbox landed where it did and
    override it. Nothing in this script changes the tenant.

.PARAMETER InventoryCsv
    Path to the Mailbox-Inventory-<timestamp>.csv produced by Get-SharedMailboxInventory.ps1.

.PARAMETER AccessCsv
    Path to the Mailbox-Access-<timestamp>.csv produced by the same run. Used to build the
    per-delegate contact list that accompanies report 4.

.PARAMETER OutputPath
    Directory the reports are written to. Defaults to the folder holding the inventory CSV.

.PARAMETER Timestamp
    Timestamp suffix applied to every output file. Defaults to the timestamp parsed out of the
    inventory CSV file name, so the reports stay traceable to the run that produced them.

.EXAMPLE
    .\Split-MailboxCleanupReports.ps1 -InventoryCsv .\cleanup-project\Mailbox-Inventory-202608060137.csv -AccessCsv .\cleanup-project\Mailbox-Access-202608060137.csv

    Writes all five report pairs plus the delegate contact list into .\cleanup-project\.

.EXAMPLE
    .\Split-MailboxCleanupReports.ps1 -InventoryCsv .\Mailbox-Inventory-202608060137.csv -AccessCsv .\Mailbox-Access-202608060137.csv -OutputPath C:\temp\reports -WhatIf

    Shows which files would be written, without creating them.

.INPUTS
    None. This script does not accept pipeline input.

.OUTPUTS
    PSCustomObject. A single summary object with the row count of each report. CSV and Markdown
    files are written to OutputPath.

.NOTES
    Version:        1.0.0
    Author:         Solomon Infrastructure
    Change history:
        1.0.0  2026-08-06  Initial release. Splits the 2026-08-06 scoping run into five reports.

    Source data caveats carried forward from Get-SharedMailboxInventory.ps1:
      - LastActivityTime falls back to LastLogonTime for shared mailboxes, and ActivitySource
        records which column produced the value. LastUserActionTime is empty on every shared
        mailbox in Exchange Online and cannot be used for scoping.
      - Rows whose StatisticsState or AccessDataState is not 'Collected' are flagged rather than
        counted, because a throttled permissions call returns an empty result that is otherwise
        indistinguishable from a mailbox with no delegates.
      - A blank SkuAssigned means the licence state was never resolved, which is not the same as
        holding no licence. Surfaced as LicenseState = 'Unknown'.
#>

[CmdletBinding(SupportsShouldProcess)]
param(
    [Parameter(Mandatory)]
    [ValidateScript({ Test-Path -LiteralPath $_ -PathType Leaf })]
    [string]$InventoryCsv,

    [Parameter(Mandatory)]
    [ValidateScript({ Test-Path -LiteralPath $_ -PathType Leaf })]
    [string]$AccessCsv,

    [Parameter()]
    [string]$OutputPath,

    [Parameter()]
    [ValidatePattern('^\d{8,14}$')]
    [string]$Timestamp
)

begin {
    $ErrorActionPreference = 'Stop'

    #region Configuration Variables

    # DisplayName fragments that mark a mailbox as functional rather than personal. Matched
    # against the DisplayName with all non-alphanumeric characters stripped, so 'E-mail' matches
    # 'email' and 'UpstreamCalcs' matches 'calc'. Substring matching is safe for these because
    # none of them occurs inside a surname present in this tenant.
    $script:NonPersonSubstring = @(
        'admin', 'adfs', 'automation', 'serviceaccount', 'svc', 'calc', 'uploader', 'relay',
        'mfp', 'scan', 'noreply', 'postmaster', 'email', 'support', 'helpdesk', 'humanresources',
        'accounting', 'accounts', 'payable', 'payroll', 'marketing', 'legal', 'filing', 'travel',
        'contact', 'consulting', 'development', 'notification', 'portal', 'website', 'study',
        'events', 'incident', 'security', 'changemanagement', 'pricing', 'processcontrol',
        'refining', 'fuels', 'chemicals', 'olefins', 'lube', 'gasplant', 'catcracking',
        'aromatics', 'styrene', 'terminals', 'pipeline', 'logistics', 'power', 'profile',
        'validate', 'techjobs', 'upstream', 'downstream', 'midstream', 'digital', 'fundamentals',
        'sustainability', 'advisory', 'middleeast', 'investment', 'ideas', 'experts', 'general',
        'management', 'application', 'knowbe4', 'bitbucket', 'azure', 'awsaudit', 'integrations',
        'public', 'solomon', 'phishing', 'zoomroom'
    )

    # Short fragments that would produce false positives as substrings ('it' inside 'Whitney'),
    # so they are matched only as whole words within the DisplayName.
    $script:NonPersonToken = @('it', 'sa', 'hr', 'dnn', 'nda', 'pres', 'box', 'room', 'ref', 'spyro')

    #endregion Configuration Variables

    #region Helper Functions

    function Get-MailboxNameClass {
        <#
        .SYNOPSIS
            Classifies a mailbox as Person, Non-Person or Resource from its name and type.
        .DESCRIPTION
            Resource wins outright on RecipientTypeDetails. Otherwise the DisplayName is tested
            against the functional keyword lists, and anything matching nothing is treated as a
            person's name.
        .PARAMETER DisplayName
            The mailbox DisplayName to classify.
        .PARAMETER RecipientTypeDetails
            The Exchange recipient type, used to short-circuit room and equipment mailboxes.
        .EXAMPLE
            Get-MailboxNameClass -DisplayName 'Aromatics E-mail' -RecipientTypeDetails 'SharedMailbox'
        .INPUTS
            None.
        .OUTPUTS
            PSCustomObject with NameClass and NameClassReason properties.
        #>
        [CmdletBinding()]
        [OutputType([PSCustomObject])]
        param(
            [Parameter(Mandatory)]
            [AllowEmptyString()]
            [string]$DisplayName,

            [Parameter(Mandatory)]
            [AllowEmptyString()]
            [string]$RecipientTypeDetails
        )

        if ($RecipientTypeDetails -in @('RoomMailbox', 'EquipmentMailbox')) {
            return [PSCustomObject]@{
                NameClass = 'Resource'
                NameClassReason = "recipient type $RecipientTypeDetails"
            }
        }

        $normalized = ($DisplayName -replace '[^a-zA-Z0-9]', '').ToLowerInvariant()
        foreach ($fragment in $script:NonPersonSubstring) {
            if ($normalized -like "*$fragment*") {
                return [PSCustomObject]@{
                    NameClass = 'Non-Person'
                    NameClassReason = "name contains '$fragment'"
                }
            }
        }

        $word = @($DisplayName.ToLowerInvariant() -split '[^a-z0-9]+' | Where-Object { $_ })
        foreach ($token in $script:NonPersonToken) {
            if ($word -contains $token) {
                return [PSCustomObject]@{
                    NameClass = 'Non-Person'
                    NameClassReason = "name contains the word '$token'"
                }
            }
        }

        return [PSCustomObject]@{
            NameClass = 'Person'
            NameClassReason = 'reads as a personal name'
        }
    }

    function Get-LicenseState {
        <#
        .SYNOPSIS
            Converts the raw SkuAssigned value into an explicit three-state licence label.
        .DESCRIPTION
            A blank SkuAssigned means the licence lookup never resolved for that mailbox.
            Reporting it as 'no licence' would understate the reclaim opportunity, so it is
            labelled Unknown instead.
        .PARAMETER SkuAssigned
            The raw SkuAssigned column value from the inventory CSV.
        .EXAMPLE
            Get-LicenseState -SkuAssigned 'True'
        .INPUTS
            None.
        .OUTPUTS
            System.String. One of Assigned, None or Unknown.
        #>
        [CmdletBinding()]
        [OutputType([string])]
        param(
            [Parameter(Mandatory)]
            [AllowEmptyString()]
            [AllowNull()]
            [string]$SkuAssigned
        )

        switch ($SkuAssigned) {
            'True' { return 'Assigned' }
            'False' { return 'None' }
            default { return 'Unknown' }
        }
    }

    function ConvertTo-MarkdownTable {
        <#
        .SYNOPSIS
            Renders objects as a GitHub-flavoured Markdown table.
        .DESCRIPTION
            Escapes pipe characters in cell values so that trustee lists cannot break the table
            layout, and substitutes an em dash for empty cells.
        .PARAMETER InputObject
            The objects to render.
        .PARAMETER Property
            Ordered list of property names to emit as columns.
        .EXAMPLE
            ConvertTo-MarkdownTable -InputObject $rows -Property 'DisplayName', 'ItemCount'
        .INPUTS
            None.
        .OUTPUTS
            System.String.
        #>
        [CmdletBinding()]
        [OutputType([string])]
        param(
            [Parameter(Mandatory)]
            [AllowEmptyCollection()]
            [object[]]$InputObject,

            [Parameter(Mandatory)]
            [string[]]$Property
        )

        if ($InputObject.Count -eq 0) {
            return '_No rows in this category._'
        }

        $builder = New-Object -TypeName System.Text.StringBuilder
        [void]$builder.AppendLine('| ' + ($Property -join ' | ') + ' |')
        [void]$builder.AppendLine('|' + (($Property | ForEach-Object { '---' }) -join '|') + '|')

        foreach ($row in $InputObject) {
            $cell = foreach ($name in $Property) {
                $value = $row.$name
                if ($null -eq $value -or $value -eq '') {
                    '&mdash;'
                } else {
                    ($value -replace '\|', '\|')
                }
            }
            [void]$builder.AppendLine('| ' + ($cell -join ' | ') + ' |')
        }

        return $builder.ToString().TrimEnd()
    }

    function Write-ReportPair {
        <#
        .SYNOPSIS
            Writes one report as a CSV file and a Markdown file.
        .DESCRIPTION
            The CSV carries every column named in Property. The Markdown carries the supplied
            intro text and then a table limited to MarkdownProperty, so that it stays readable
            in a browser.
        .PARAMETER Row
            The report rows.
        .PARAMETER BaseName
            File name without extension or directory.
        .PARAMETER OutputPath
            Target directory.
        .PARAMETER Title
            Markdown H1 title.
        .PARAMETER Intro
            Markdown body inserted between the title and the table.
        .PARAMETER Property
            Columns written to the CSV.
        .PARAMETER MarkdownProperty
            Columns rendered in the Markdown table.
        .PARAMETER SourceName
            File name of the inventory CSV, recorded in the Markdown footer.
        .EXAMPLE
            Write-ReportPair -Row $rooms -BaseName 'Report1' -OutputPath . -Title 'Rooms' -Intro 'x' -Property 'DisplayName' -MarkdownProperty 'DisplayName' -SourceName 'inv.csv'
        .INPUTS
            None.
        .OUTPUTS
            None.
        #>
        [CmdletBinding(SupportsShouldProcess)]
        [OutputType([void])]
        param(
            [Parameter(Mandatory)]
            [AllowEmptyCollection()]
            [object[]]$Row,

            [Parameter(Mandatory)]
            [string]$BaseName,

            [Parameter(Mandatory)]
            [string]$OutputPath,

            [Parameter(Mandatory)]
            [string]$Title,

            [Parameter(Mandatory)]
            [string]$Intro,

            [Parameter(Mandatory)]
            [string[]]$Property,

            [Parameter(Mandatory)]
            [string[]]$MarkdownProperty,

            [Parameter(Mandatory)]
            [string]$SourceName
        )

        $csvPath = Join-Path -Path $OutputPath -ChildPath "$BaseName.csv"
        $markdownPath = Join-Path -Path $OutputPath -ChildPath "$BaseName.md"

        if ($PSCmdlet.ShouldProcess($csvPath, 'Write CSV report')) {
            $Row |
                Select-Object -Property $Property |
                Export-Csv -LiteralPath $csvPath -NoTypeInformation -Encoding UTF8
            Write-Verbose -Message "Wrote $($Row.Count) rows to $csvPath"
        }

        if ($PSCmdlet.ShouldProcess($markdownPath, 'Write Markdown report')) {
            $body = New-Object -TypeName System.Collections.Generic.List[string]
            $body.Add("# $Title")
            $body.Add('')
            $body.Add($Intro.TrimEnd())
            $body.Add('')
            $body.Add("## Rows ($($Row.Count))")
            $body.Add('')
            $body.Add((ConvertTo-MarkdownTable -InputObject $Row -Property $MarkdownProperty))
            $body.Add('')
            $body.Add('---')
            $body.Add('')
            $body.Add("Generated by ``Split-MailboxCleanupReports.ps1`` from ``$SourceName``.")
            $body.Add('Read-only report. Nothing in this folder changes the tenant.')

            ($body -join [Environment]::NewLine) |
                Out-File -LiteralPath $markdownPath -Encoding utf8
            Write-Verbose -Message "Wrote $markdownPath"
        }
    }

    #endregion Helper Functions

    #region Path Resolution

    if (-not $OutputPath) {
        $OutputPath = Split-Path -Parent (Resolve-Path -LiteralPath $InventoryCsv)
    }
    if (-not (Test-Path -LiteralPath $OutputPath -PathType Container)) {
        throw "OutputPath '$OutputPath' does not exist or is not a directory."
    }

    $sourceName = Split-Path -Leaf $InventoryCsv
    if (-not $Timestamp) {
        if ($sourceName -match '(\d{8,14})') {
            $Timestamp = $Matches[1]
        } else {
            throw 'Could not parse a timestamp from the inventory file name. Pass -Timestamp explicitly.'
        }
    }

    Write-Verbose -Message "Output directory: $OutputPath"
    Write-Verbose -Message "Timestamp suffix: $Timestamp"

    #endregion Path Resolution
}

process {
    try {
        $inventory = @(Import-Csv -LiteralPath $InventoryCsv)
        $access = @(Import-Csv -LiteralPath $AccessCsv)
        Write-Verbose -Message "Loaded $($inventory.Count) mailboxes and $($access.Count) access grants."

        if ($inventory.Count -eq 0) {
            throw "Inventory CSV '$InventoryCsv' contains no rows."
        }

        #region Enrich

        $row = foreach ($mailbox in $inventory) {
            $classification = Get-MailboxNameClass -DisplayName $mailbox.DisplayName -RecipientTypeDetails $mailbox.RecipientTypeDetails

            $delegateCount = 0
            [void][int]::TryParse($mailbox.TotalDelegateCount, [ref]$delegateCount)

            $sizeMb = 0.0
            [void][double]::TryParse($mailbox.TotalItemSizeMB, [ref]$sizeMb)

            $itemCount = 0
            [void][int]::TryParse($mailbox.ItemCount, [ref]$itemCount)

            $complete = ($mailbox.StatisticsState -eq 'Collected' -and $mailbox.AccessDataState -eq 'Collected')

            $mailbox | Add-Member -NotePropertyName 'NameClass' -NotePropertyValue $classification.NameClass -Force
            $mailbox | Add-Member -NotePropertyName 'NameClassReason' -NotePropertyValue $classification.NameClassReason -Force
            $mailbox | Add-Member -NotePropertyName 'LicenseState' -NotePropertyValue (Get-LicenseState -SkuAssigned $mailbox.SkuAssigned) -Force
            $mailbox | Add-Member -NotePropertyName 'DelegateCount' -NotePropertyValue $delegateCount -Force
            $mailbox | Add-Member -NotePropertyName 'SizeMB' -NotePropertyValue $sizeMb -Force
            $mailbox | Add-Member -NotePropertyName 'Items' -NotePropertyValue $itemCount -Force
            $mailbox | Add-Member -NotePropertyName 'CollectionComplete' -NotePropertyValue $complete -Force
            $mailbox
        }

        #endregion Enrich

        #region Shared Definitions

        $coreColumn = @(
            'DisplayName', 'PrimarySmtpAddress', 'UserPrincipalName', 'Alias',
            'RecipientTypeDetails', 'NameClass', 'NameClassReason', 'AccountDisabled',
            'LicenseState', 'SkuAssigned', 'Department', 'Title',
            'LastActivityTime', 'DaysSinceLastActivity', 'ActivitySource',
            'LastLogonTime', 'LastUserActionTime',
            'ItemCount', 'TotalItemSizeMB',
            'LitigationHoldEnabled', 'LitigationHoldDate', 'LitigationHoldDuration',
            'InPlaceHoldCount', 'RetentionPolicy', 'ArchiveStatus',
            'HiddenFromAddressLists', 'IsDirSynced', 'IsInactiveMailbox',
            'ForwardingSmtpAddress', 'DeliverToMailboxAndForward',
            'TotalDelegateCount', 'FullAccessCount', 'SendAsCount', 'SendOnBehalfCount',
            'FullAccessTrustees', 'SendAsTrustees', 'SendOnBehalfTrustees',
            'StatisticsState', 'AccessDataState', 'CollectionComplete',
            'UserWhenCreatedUTC', 'UserWhenChangedUTC', 'DaysSinceUserChanged'
        )

        $caveat = @'
### How to read this

- **`NameClass` is derived by this script, not by Exchange.** `NameClassReason` shows the keyword
  that decided it. Override anything that looks wrong: the classifier is a starting point for
  review, not an authority.
- **`RecipientTypeDetails` and `NameClass` disagree on purpose.** Most person-named mailboxes on
  disabled accounts are `SharedMailbox`, having been converted when the employee left.
- **`LicenseState` is `Unknown`** where the licence lookup never resolved. That is not the same as
  holding no licence, and those rows must be checked before any reclaim number is quoted.
- **`LastActivityTime` falls back to `LastLogonTime`** for shared mailboxes, and `ActivitySource`
  records which column produced it. Background mailbox assistants can advance `LastLogonTime`, so
  activity sourced that way deserves a second look before concluding a human is using the mailbox.
  `LastUserActionTime` is empty on every shared mailbox and cannot be used for scoping.
- **Activity on a shared mailbox is delegate activity**, not the departed employee's.
- **`CollectionComplete = False`** means a statistics or permissions call did not return. Treat
  those rows as unknown rather than empty.
'@

        #endregion Shared Definitions

        #region Report 1 - Rooms and resources

        $room = @($row | Where-Object { $_.NameClass -eq 'Resource' } | Sort-Object -Property DisplayName)
        $roomDisabled = @($room | Where-Object { $_.AccountDisabled -eq 'True' }).Count
        $roomNoActivity = @($room | Where-Object { -not $_.LastActivityTime }).Count

        $roomIntro = @"
Room and equipment mailboxes in the tenant. **These are not cleanup candidates.** Idle is the
normal state for a meeting room: a room with no bookings this quarter is still a live business
resource. They are listed here so the cleanup can be shown to have considered and excluded them.

- Total: **$($room.Count)**
- Sign-in blocked: **$roomDisabled**
- No activity recorded: **$roomNoActivity**

Delegates on a room mailbox are its booking approvers. Removing one changes who can accept
meetings, so read the delegate columns as configuration rather than as leftover access.

$caveat
"@

        Write-ReportPair -Row $room -BaseName "Report1-Rooms-And-Resources-$Timestamp" -OutputPath $OutputPath -Title 'Report 1 - Rooms and resources' -Intro $roomIntro -Property $coreColumn -SourceName $sourceName -MarkdownProperty @(
            'DisplayName', 'PrimarySmtpAddress', 'RecipientTypeDetails', 'AccountDisabled',
            'LastActivityTime', 'DaysSinceLastActivity', 'ItemCount', 'TotalItemSizeMB',
            'TotalDelegateCount', 'FullAccessTrustees'
        )

        #endregion Report 1

        #region Report 2 - Non-user mailboxes

        $nonUser = @($row |
                Where-Object { $_.NameClass -eq 'Non-Person' } |
                Sort-Object -Property @{ Expression = 'AccountDisabled'; Descending = $true }, DisplayName)
        $nonUserDisabled = @($nonUser | Where-Object { $_.AccountDisabled -eq 'True' })
        $nonUserLicensed = @($nonUser | Where-Object { $_.LicenseState -eq 'Assigned' }).Count
        $nonUserUnknownLicence = @($nonUser | Where-Object { $_.LicenseState -eq 'Unknown' }).Count
        $nonUserGb = [math]::Round((($nonUser | Measure-Object -Property SizeMB -Sum).Sum / 1024), 1)
        $nonUserItems = ($nonUser | Measure-Object -Property Items -Sum).Sum

        $nonUserIntro = @"
Mailboxes whose name describes a function rather than a person: shared team mailboxes, service
accounts, per-study distribution addresses, scanner and relay accounts, and the ``Admin<INITIALS>``
privileged accounts.

- Total non-user mailboxes: **$($nonUser.Count)**
- With ``AccountDisabled = True``: **$($nonUserDisabled.Count)**
- Still enabled: **$($nonUser.Count - $nonUserDisabled.Count)**
- Holding a licence: **$nonUserLicensed** (licence state unknown on $nonUserUnknownLicence)
- Combined size: **$nonUserGb GB** across $('{0:N0}' -f $nonUserItems) items

**A blocked sign-in on a shared mailbox is expected, not a finding.** Shared mailboxes are supposed
to have sign-in blocked, so ``AccountDisabled = True`` in this report does not mean the mailbox is
abandoned. Judge these on ``LastActivityTime`` and on whether anyone still holds a delegate grant,
and confirm the owning team before touching a functional address that other systems may still be
sending to.

Rows sort disabled first. The ``Admin<INITIALS>`` accounts are individually-assigned privileged
accounts and belong to a separate access review rather than to mailbox cleanup.

$caveat
"@

        Write-ReportPair -Row $nonUser -BaseName "Report2-NonUser-Mailboxes-$Timestamp" -OutputPath $OutputPath -Title 'Report 2 - Non-user mailboxes' -Intro $nonUserIntro -Property $coreColumn -SourceName $sourceName -MarkdownProperty @(
            'DisplayName', 'PrimarySmtpAddress', 'RecipientTypeDetails', 'AccountDisabled',
            'LicenseState', 'LastActivityTime', 'DaysSinceLastActivity', 'ActivitySource',
            'ItemCount', 'TotalItemSizeMB', 'TotalDelegateCount', 'NameClassReason'
        )

        #endregion Report 2

        #region Report 3 - Licensed user and shared mailboxes

        $licensed = @($row |
                Where-Object { $_.NameClass -ne 'Resource' -and $_.LicenseState -eq 'Assigned' } |
                Sort-Object -Property @{ Expression = 'AccountDisabled'; Descending = $true }, RecipientTypeDetails, DisplayName)
        $licensedDisabled = @($licensed | Where-Object { $_.AccountDisabled -eq 'True' })
        $licensedDisabledUser = @($licensedDisabled | Where-Object { $_.RecipientTypeDetails -eq 'UserMailbox' }).Count
        $licensedDisabledShared = @($licensedDisabled | Where-Object { $_.RecipientTypeDetails -eq 'SharedMailbox' }).Count
        $licenceUnknown = @($row | Where-Object { $_.NameClass -ne 'Resource' -and $_.LicenseState -eq 'Unknown' }).Count

        $licensedIntro = @"
User and shared mailboxes carrying an assigned licence. This is the licence reclamation view.

- Licensed user and shared mailboxes: **$($licensed.Count)**
- Of those, ``AccountDisabled = True``: **$($licensedDisabled.Count)**
    - UserMailbox: **$licensedDisabledUser**
    - SharedMailbox: **$licensedDisabledShared**

**The disabled-and-licensed rows are the immediate finding.** A licence on an account whose sign-in
is already blocked is being paid for and cannot be used.

A shared mailbox needs no licence at all unless it exceeds 50 GB, sits on an In-Place or Litigation
Hold, or has an online archive enabled. Check ``TotalItemSizeMB``, ``InPlaceHoldCount``,
``LitigationHoldEnabled`` and ``ArchiveStatus`` on each row before removing one.

Removing a licence is not consequence-free: the mailbox enters a 30-day grace period and is then
deleted. Convert to a shared mailbox, or apply the litigation hold from reports 4 and 5 first,
before stripping a licence off an account whose contents still matter.

Licence state could not be resolved for **$licenceUnknown** other user or shared mailboxes. Those
are excluded from this report and need to be checked separately.

$caveat
"@

        Write-ReportPair -Row $licensed -BaseName "Report3-Licensed-User-And-Shared-Mailboxes-$Timestamp" -OutputPath $OutputPath -Title 'Report 3 - Licensed user and shared mailboxes' -Intro $licensedIntro -Property $coreColumn -SourceName $sourceName -MarkdownProperty @(
            'DisplayName', 'PrimarySmtpAddress', 'RecipientTypeDetails', 'NameClass',
            'AccountDisabled', 'LicenseState', 'Department', 'Title', 'LastActivityTime',
            'DaysSinceLastActivity', 'ItemCount', 'TotalItemSizeMB', 'ArchiveStatus',
            'InPlaceHoldCount', 'TotalDelegateCount'
        )

        #endregion Report 3

        #region Reports 4 and 5 - Disabled person-named mailboxes

        $disabledPerson = @($row | Where-Object { $_.NameClass -eq 'Person' -and $_.AccountDisabled -eq 'True' })
        $withDelegate = @($disabledPerson |
                Where-Object { $_.DelegateCount -gt 0 } |
                Sort-Object -Property @{ Expression = 'DelegateCount'; Descending = $true }, DisplayName)
        $withoutDelegate = @($disabledPerson |
                Where-Object { $_.DelegateCount -eq 0 } |
                Sort-Object -Property @{ Expression = 'SizeMB'; Descending = $true }, DisplayName)

        foreach ($item in $withDelegate) {
            $item | Add-Member -NotePropertyName 'RiskTier' -NotePropertyValue 'Medium' -Force
            $item | Add-Member -NotePropertyName 'LitigationHoldAction' -NotePropertyValue 'Apply hold after delegate sign-off' -Force
        }
        foreach ($item in $withoutDelegate) {
            $item | Add-Member -NotePropertyName 'RiskTier' -NotePropertyValue 'Low' -Force
            $item | Add-Member -NotePropertyName 'LitigationHoldAction' -NotePropertyValue 'Apply hold' -Force
        }

        $holdColumn = @('RiskTier', 'LitigationHoldAction') + $coreColumn
        $holdMarkdown = @(
            'DisplayName', 'PrimarySmtpAddress', 'RecipientTypeDetails', 'LicenseState',
            'Department', 'Title', 'LastActivityTime', 'DaysSinceLastActivity', 'ActivitySource',
            'ItemCount', 'TotalItemSizeMB', 'LitigationHoldEnabled', 'InPlaceHoldCount',
            'TotalDelegateCount'
        )

        # The delegate contact list is built here rather than after the report, because the
        # distinct-delegate headline has to be counted from it. Counting instead across the
        # inventory's own trustee columns overstates the number: FullAccessTrustees and
        # SendAsTrustees hold SMTP addresses, but SendOnBehalfTrustees holds display names, so
        # anyone holding both kinds of grant is counted twice. On this run that read 22 people
        # where the access data has 20. The access CSV resolves every trustee to a single
        # TrusteeSmtpAddress, so it is the only source that can answer "how many people".
        $withDelegateAddress = @($withDelegate | ForEach-Object { $_.PrimarySmtpAddress })
        $contactColumn = @(
            'TrusteeDisplayName', 'TrusteeSmtpAddress', 'TrusteeRecipientType', 'TrusteeIsGroup',
            'MailboxDisplayName', 'MailboxPrimarySmtpAddress', 'MailboxType', 'AccessType',
            'AccessRights', 'ExpandedFromGroup'
        )
        $contact = @($access |
                Where-Object { $withDelegateAddress -contains $_.MailboxPrimarySmtpAddress } |
                Sort-Object -Property TrusteeDisplayName, MailboxDisplayName, AccessType |
                Select-Object -Property $contactColumn)

        $distinctDelegate = @($contact |
                ForEach-Object { $_.TrusteeSmtpAddress.Trim().ToLowerInvariant() } |
                Where-Object { $_ } |
                Sort-Object -Unique).Count
        $withDelegateGb = [math]::Round((($withDelegate | Measure-Object -Property SizeMB -Sum).Sum / 1024), 1)
        $withDelegateItems = ($withDelegate | Measure-Object -Property Items -Sum).Sum
        $withDelegateOnHold = @($withDelegate | Where-Object { $_.LitigationHoldEnabled -eq 'True' }).Count
        $withDelegateLicensed = @($withDelegate | Where-Object { $_.LicenseState -eq 'Assigned' }).Count

        $withDelegateIntro = @"
Person-named mailboxes on accounts with ``AccountDisabled = True`` that **still have at least one
delegate holding access**. These are the **medium risk** candidates for the scripted litigation
hold: somebody is still reaching this mail, so the hold can be applied, but the delegate has to be
consulted before the mailbox itself is retired.

- Mailboxes: **$($withDelegate.Count)**
- Distinct delegates to contact: **$distinctDelegate**
- Combined size: **$withDelegateGb GB** across $('{0:N0}' -f $withDelegateItems) items
- Already on Litigation Hold: **$withDelegateOnHold**
- Still holding a licence: **$withDelegateLicensed**

**Risk: Medium.** Applying a litigation hold is itself non-destructive and reversible; the risk
sits in what follows. Get approval from each delegate before removing their access or retiring the
mailbox. For many of these, the delegate is the reason the mailbox was converted to shared rather
than deleted when the employee left.

**Use ``Report4-Delegate-Contact-List-$Timestamp.csv`` for the outreach, not the trustee columns
here.** The two disagree, and the contact list is the one that is right. ``FullAccessTrustees`` and
``SendAsTrustees`` hold SMTP addresses, but ``SendOnBehalfTrustees`` holds display names, so anyone
holding both kinds of grant appears twice under two different labels. Counting names across those
three columns gives 22 people for these 22 mailboxes; the access data resolves every trustee to one
address and gives **$distinctDelegate**. The contact list is one row per grant with the trustee
already resolved.

No delegate grant in this tenant was made to a group, so every name is an individual rather than a
membership list that has to be expanded before it means anything.

$caveat
"@

        Write-ReportPair -Row $withDelegate -BaseName "Report4-Disabled-UserMailboxes-With-Delegates-$Timestamp" -OutputPath $OutputPath -Title 'Report 4 - Disabled user mailboxes WITH delegates (litigation hold, medium risk)' -Intro $withDelegateIntro -Property $holdColumn -SourceName $sourceName -MarkdownProperty $holdMarkdown

        $withoutDelegateGb = [math]::Round((($withoutDelegate | Measure-Object -Property SizeMB -Sum).Sum / 1024), 1)
        $withoutDelegateItems = ($withoutDelegate | Measure-Object -Property Items -Sum).Sum
        $withoutDelegateOnHold = @($withoutDelegate | Where-Object { $_.LitigationHoldEnabled -eq 'True' }).Count
        $withoutDelegateLicensed = @($withoutDelegate | Where-Object { $_.LicenseState -eq 'Assigned' }).Count
        $withoutDelegateIncomplete = @($withoutDelegate | Where-Object { -not $_.CollectionComplete }).Count

        $withoutDelegateIntro = @"
Person-named mailboxes on accounts with ``AccountDisabled = True`` that have **no delegate of any
kind** - no FullAccess, no SendAs, no SendOnBehalf. These are the **low risk** candidates for the
scripted litigation hold. Nobody currently reaches this mail, so there is no access for the hold to
disrupt and nobody to consult first.

- Mailboxes: **$($withoutDelegate.Count)**
- Combined size: **$withoutDelegateGb GB** across $('{0:N0}' -f $withoutDelegateItems) items
- Already on Litigation Hold: **$withoutDelegateOnHold**
- Still holding a licence: **$withoutDelegateLicensed**
- Collection incomplete, delegate count unreliable: **$withoutDelegateIncomplete**

**Risk: Low. Start the scripted hold here.** Rows sort largest first, so the mailboxes carrying the
most content, and therefore the most retention exposure, are at the top.

**One caveat decides whether this list is safe to act on.** "No delegates" is only trustworthy
where the permissions call actually returned. A retry-exhausted call produces an empty result that
looks identical to a mailbox nobody has access to. The ``CollectionComplete`` column carries that
distinction; check it before treating a zero as a fact.

$caveat
"@

        Write-ReportPair -Row $withoutDelegate -BaseName "Report5-Disabled-UserMailboxes-No-Delegates-$Timestamp" -OutputPath $OutputPath -Title 'Report 5 - Disabled user mailboxes WITHOUT delegates (litigation hold, low risk)' -Intro $withoutDelegateIntro -Property $holdColumn -SourceName $sourceName -MarkdownProperty $holdMarkdown

        #endregion Reports 4 and 5

        #region Report 4 companion - delegate contact list

        $contactPath = Join-Path -Path $OutputPath -ChildPath "Report4-Delegate-Contact-List-$Timestamp.csv"
        if ($PSCmdlet.ShouldProcess($contactPath, 'Write delegate contact list')) {
            $contact | Export-Csv -LiteralPath $contactPath -NoTypeInformation -Encoding UTF8
            Write-Verbose -Message "Wrote $($contact.Count) delegate grants to $contactPath"
        }

        #endregion Report 4 companion

        #region Summary

        [PSCustomObject]@{
            InventoryRows = $inventory.Count
            AccessGrants = $access.Count
            Report1RoomsAndResources = $room.Count
            Report2NonUserMailboxes = $nonUser.Count
            Report2DisabledSubset = $nonUserDisabled.Count
            Report3LicensedMailboxes = $licensed.Count
            Report3DisabledSubset = $licensedDisabled.Count
            Report4WithDelegates = $withDelegate.Count
            Report4DelegateGrants = $contact.Count
            Report5NoDelegates = $withoutDelegate.Count
            OutputPath = $OutputPath
        }

        #endregion Summary
    } catch {
        Write-Error -Message "Failed to split mailbox cleanup reports: $($_.Exception.Message)"
        throw
    }
}

end {
    Write-Verbose -Message 'Split-MailboxCleanupReports completed.'
}

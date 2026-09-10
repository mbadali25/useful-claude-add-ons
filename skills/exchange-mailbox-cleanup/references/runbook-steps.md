# Mailbox Cleanup - the 41 steps

Work these **in order, one per turn**. Every command is printed for the operator's Windows
PowerShell 5.1 window unless the step says otherwise. `$Admin`, `$Repo`, `$Csv`, `$Sku` are set at
Step 6 and reused. Reads of `C:\scripts\logs\*.csv` and `C:\scripts\reports\*` are done by the skill
with the Read tool.

Ordering differs from the printed runbook on purpose - the eDiscovery grant (runbook Step 14) is
brought forward to Step 13 here so the baseline search at Step 21 has a propagated role behind it.
See "Six runbook defects" in `SKILL.md`.

Legend: **Proves** - what the operator learns. **Good** - what the artifact must show before
advancing. **Read** - the artifact the skill reads back.

**Reading artifacts back.** The scripts' `*.csv` files are UTF-8 with a BOM and read cleanly. Their
`*.log` files are written with `Add-Content` and no `-Encoding`, so under 5.1 they are cp1252 - read
them through `python "$SkillDir\scripts\read_log.py" <file> [--tail N] [--grep TEXT]`, which decodes
defensively and says which encoding won. Never print `>` or `Out-File` for the operator: on 5.1 they
write UTF-16LE. Every ad hoc export is `... | Export-Csv -Path 'C:\scripts\reports\<name>.csv'
-NoTypeInformation -Encoding UTF8`.

---

## Phase A - Setup (Steps 1-12) - reversible

### Step 1 - Confirm the request

Ask one question: *"Who is being offboarded - one address, or do you have a list?"* Accept a single
UPN or a file path. Validate: one `@`, no spaces, a dot in the domain; or the path exists. Do not ask
about the ticket, the SKU or anything else in the same message.

### Step 2 - Normalise the input

Skill runs (not the operator):

```powershell
python "$SkillDir\scripts\parse_user_input.py" "<address-or-path>" --out C:\scripts\reports\holdlist.csv --json
```

**Proves** the list is what the operator thinks it is. **Good**: exit 0, `count` matches their
expectation, every address echoed back. Exit 3: show `rejected` rows with their reasons and ask
*"Proceed with the {n} valid rows, or fix the file?"* Exit 1/2: stop, quote the error.

If `C:\scripts\reports` does not exist yet, write to `%TEMP%\holdlist.csv` for now and move it at
Step 5.

Say the count back: *"3 mailboxes: a, b, c. Correct?"* Wait for yes.

### Step 3 - The ticket

Ask once: *"Do you have a ServiceDesk Plus ticket for this offboarding, or should I open one?"*
Use the `infra-work-ticketing` skill. If opening one: title `M365 offboarding - mailbox cleanup -
{N} user(s) - {yyyy-MM-dd}`, description listing the UPNs and "Litigation Hold, account deletion,
inactive-mailbox validation, eDiscovery export". **Never create without the operator confirming the
title and list.** Before any `sdp_create` / `sdp_add_note`:

```powershell
python <infra-work-ticketing>\scripts\ticketctl.py redact-check --body-file note.md --emit > note.clean.md
```

That line is run by the **skill in its Bash tool**, never printed for the operator: in a 5.1 window
`>` writes UTF-16LE and the scrubbed note would arrive in the ticket as garbage.

Record the ticket number; every later note goes to it.

### Step 4 - Preflight, read-only

Skill runs:

```powershell
powershell.exe -NoProfile -File "$SkillDir\scripts\exo_preflight.ps1" -Check
```

**Proves** the workstation can do this. **Good**: exit 0. Exit 2 = `SiblingSkillMissing` - install
`exchange-mailbox-restore` beside this skill and re-run. Exit 1: list every `FAIL` line to the
operator in plain words ("ExchangeOnlineManagement is missing", "C:\scripts\logs does not exist").
Note any `NOTICE` about content in the old `C:\scripts\log` path.

### Step 5 - Install what is missing (confirm once, then install and verify)

Only if Step 4 reported a missing module or directory. A non-technical operator handed a list of
prerequisites is stuck, so the skill installs them - **under the user profile, never machine-wide,
no admin prompt**. Say exactly what will be installed (the three Graph sub-modules and
ExchangeOnlineManagement take a few minutes each) and ask once: *"Shall I install these under your
user profile?"* On yes, skill runs:

```powershell
powershell.exe -NoProfile -File "$SkillDir\scripts\exo_preflight.ps1" -Install
```

The script sets TLS 1.2, bootstraps NuGet, runs `Install-Module -Scope CurrentUser -Force
-AllowClobber` per module, then shows `Name, Version, ModuleBase` for what landed. It stops on the
first failure with the verbatim error - quote it to the operator, do not retry, do not suggest an
elevated window. A `NOTICE` about a OneDrive-redirected module path is reported, not fixed. Then
re-run `-Check` and require exit 0.

### Step 6 - Open the operator's window and set session variables

The first thing printed, before anything else, is the edition check:

```powershell
$PSVersionTable.PSEdition
```

**Good**: `Desktop`. If it prints `Core`, say exactly: *"Close this window. Open the Start menu, type
Windows PowerShell, and open the blue icon whose title bar says Windows PowerShell - not the one that
says PowerShell 7."* Do not look for `pwsh`; the skill never needs it. Then:

```powershell
# Blue "Windows PowerShell" window. Run as yourself, not elevated.
$Admin = "admin@contoso.com"        # <- your admin UPN
$Repo  = "C:\repos\solomon\infrastructure-scripts\Powershell\Exchange"
$Csv   = "C:\scripts\reports\holdlist.csv"
$Sku   = "SPE_E3"                   # the only SKU in this tenant that grants Litigation Hold
$LogDir = "C:\scripts\logs"
Set-Location $Repo
```

Ask for `$Admin` if not already known. Tell the operator once, here: *"Every step runs in a blue
Windows PowerShell window - on your own PC for everything except the sync step, which you run in the
same kind of window on the server AWSPRDINFAAD01 after connecting with Remote Desktop, and then you
come back."*

### Step 7 - Import modules and connect to Exchange Online

```powershell
Import-Module Microsoft.Graph.Authentication
Import-Module Microsoft.Graph.Users
Import-Module Microsoft.Graph.Identity.DirectoryManagement
Import-Module ExchangeOnlineManagement          # AFTER Graph - the other order breaks Graph on 5.1

Connect-ExchangeOnline -UserPrincipalName $Admin -ShowBanner:$false
Get-Mailbox -ResultSize 1 | Select-Object DisplayName
```

**Good**: one mailbox row, no red. On `0x80070002` / WAM error: add `-DisableWAM`.

### Step 8 - Connect to Microsoft Graph with the union of scopes

```powershell
Connect-MgGraph -Scopes 'Organization.Read.All','User.ReadWrite.All','Directory.AccessAsUser.All','User.RevokeSessions.All' -NoWelcome
Get-MgContext | Select-Object Account, @{n='Scopes';e={$_.Scopes -join ', '}}
```

**Good**: `Account = $Admin`, all four scopes listed. If the browser never appears:
`Connect-MgGraph -UseDeviceCode -Scopes ...`.

### Step 9 - Connect to Security & Compliance (Purview)

```powershell
Connect-IPPSSession -UserPrincipalName $Admin
Get-ConnectionInformation | Select-Object ConnectionUri, State, UserPrincipalName
```

**Good**: two rows, both `Connected` - one `outlook.office365.com`, one `*.compliance.protection.outlook.com`.
Connect IPPS **last** so role-group cmdlets resolve to Purview.

### Step 10 - Role check, in the operator's window

`-Roles` reads the live sessions, so it must run **in the same window** the operator connected in.
`powershell.exe -File` would start a fresh process with no sessions and report exit 3. Print:

```powershell
$SkillDir = "C:\repos\personal\useful-claude-add-ons\skills\exchange-mailbox-cleanup"   # or the ~\.claude\skills path
& "$SkillDir\scripts\exo_preflight.ps1" -Roles -AdminUpn $Admin
```

**Proves** the missing role is named before it costs an hour. **Good**: `PASS` for Exchange
Administrator (or Global Administrator) and for eDiscovery Manager membership. A `FAIL eDiscovery
Manager` here is expected on a first run - Step 13 fixes it. A `FAIL Exchange Administrator` is
not fixable by this skill; stop and route to whoever holds Global Administrator.

**Read**: `C:\scripts\reports\exo-preflight-*.txt`.

### Step 11 - Validate the CSV the way the script will read it

```powershell
Import-Csv $Csv | Select-Object UserPrincipalName
(Import-Csv $Csv).Count
```

**Good**: the header is exactly `UserPrincipalName`, the rows match Step 2, the count matches. The
hold script accepts `UserPrincipalName`, `EmailAddress`, `Email` or `PrimarySmtpAddress`, but the
normalised file uses the first. A CSV is processed **exactly as supplied** - recipient-type and
licence filters are skipped because a curated list is already the product of human review. That is
why a shared mailbox named after a person is held here but skipped by the automatic sweep.

### Step 12 - Confirm licence seats

```powershell
Get-MgSubscribedSku -All |
    Where-Object SkuPartNumber -eq $Sku |
    Select-Object SkuPartNumber, ConsumedUnits, @{n='Purchased';e={$_.PrepaidUnits.Enabled}}
```

**Proves** the hold can be applied. Litigation Hold needs Exchange Online Plan 2 *at the moment it
is applied*; this tenant has no archiving add-on, so it costs a full E3 seat per unlicensed mailbox
until the account is deleted. **Good**: `Purchased - ConsumedUnits >= row count`. If not, stop; the
script refuses to start rather than half-complete a batch.

Phase boundary report: ticket number, N mailboxes, seats available, modules and roles state.

---

## Phase B - Preserve (Steps 13-23) - reversible

### Step 13 - Grant eDiscovery Manager (moved forward from runbook Step 14 - defect 1)

Resolve the role group by lookup, never by literal (defect 5):

```powershell
Connect-IPPSSession -UserPrincipalName $Admin      # again, so Get-RoleGroup resolves to Purview
$rg = Get-RoleGroup -ResultSize Unlimited | Where-Object { $_.Name -eq 'eDiscoveryManager' -or $_.DisplayName -eq 'eDiscovery Manager' }
$rg | Select-Object Name, DisplayName
Add-RoleGroupMember -Identity $rg.Name -Member $Admin
```

Confirm before printing `Add-RoleGroupMember` (reversible, but stated count - see
`operator-safety.md`). Optionally, for one or two people only:

```powershell
Add-eDiscoveryCaseAdmin -User $Admin     # there is NO role group named "eDiscovery Administrator"
```

**Good**: `$rg` returns exactly one row; `Add-RoleGroupMember` returns silently. If the member is
already present it says so - that is fine.

### Step 14 - Verify the grant and start the propagation clock

```powershell
Get-RoleGroupMember -Identity $rg.Name -ResultSize Unlimited | Select-Object Name, PrimarySmtpAddress
Get-Date -Format 'yyyy-MM-dd HH:mm'          # write this down
```

**Good**: `$Admin` in the list. Tell the operator: *"Propagation takes 30-60 minutes. Until then
every search returns zero with no error. The clock started at {time}; we will not run the baseline
before {time + 60 min}. There is nothing to debug in that window."* Portal check: Purview > Help >
`Diag:edisRBACdiag` > UPN > Run Tests.

Use the wait: Steps 15-19 do not need the role.

### Step 15 - Pre-hold state: check all four holds on every mailbox

```powershell
Import-Csv $Csv | ForEach-Object {
    Get-Mailbox -Identity $_.UserPrincipalName |
        Select-Object DisplayName, RecipientTypeDetails, LitigationHoldEnabled, LitigationHoldDuration,
                      RetentionComment, InPlaceHolds, ComplianceTagHoldApplied, DelayHoldApplied
} | Format-List
```

**Proves** the starting state and catches surprises. Decode `InPlaceHolds` with
`hold-and-mailbox-states.md`. **Good**: `LitigationHoldEnabled = False` is *expected* here. A `UniH`
entry means an eDiscovery case already holds this mailbox - note it in the ticket; it does not block
the process. `RecipientTypeDetails` of `RoomMailbox`/`EquipmentMailbox` means the list is wrong -
stop and ask.

### Step 16 - Dry-run the hold

```powershell
.\Invoke-M365OffboardingHold.ps1 -UserList $Csv -TemporaryLicenseSku $Sku -AdminUpn $Admin -MaxUser 30 -LogPath $LogDir -WhatIf
```

**Never skip this.** **Good**: every address appears, each as "would apply hold" or "already on
hold - skipped". No unexpected names. `-MaxUser 30` is the safety cap; if the CSV has more rows the
script stops and says so rather than processing the first 30.

### Step 17 - Apply the hold

State: *"This applies a seven-year hold to {N} mailboxes and assigns a temporary {Sku} seat to any
that lack one. Reversible. Continue?"* On yes:

```powershell
.\Invoke-M365OffboardingHold.ps1 -UserList $Csv -TemporaryLicenseSku $Sku -AdminUpn $Admin -MaxUser 30 -LogPath $LogDir
```

The script polls up to 300 s for a new licence to reach Exchange (`-LicenseWaitSeconds`). Applying
too early fails with the same error as having no licence. Let it wait. Safe to re-run; held mailboxes
are skipped.

**Read**: `C:\scripts\logs\M365OffboardingHold-{timestamp}.csv` - columns `UserPrincipalName`,
`HoldApplied`, `HoldTag`, `LitigationHoldDuration`, `TemporaryLicenseAssigned`, `MailboxSizeGB`,
`Status`, `Detail`. **Good**: `Status` success for every row, `HoldTag` ends `-Termination`.

### Step 18 - Reconnect (the script disconnected you - defect 2)

```powershell
Connect-ExchangeOnline -UserPrincipalName $Admin -ShowBanner:$false
Connect-IPPSSession -UserPrincipalName $Admin
Get-Mailbox -ResultSize 1 | Select-Object DisplayName
```

### Step 19 - Verify the hold actually stamped

`Set-Mailbox` reporting success does not mean the hold landed. Re-read:

```powershell
Import-Csv $Csv | ForEach-Object {
    Get-Mailbox -Identity $_.UserPrincipalName |
        Select-Object DisplayName, LitigationHoldEnabled, LitigationHoldDate, LitigationHoldDuration, LitigationHoldOwner, RetentionComment
} | Format-Table -AutoSize
```

**Good**: `LitigationHoldEnabled = True`, `LitigationHoldDuration = 2555`, `RetentionComment` ends
`-Termination`, on **every** row. Any row not `True`: stop, re-run Step 17 for that identity. Do not
carry a `False` into Phase C.

### Step 20 - Wait out propagation

Compare `Get-Date` with the time from Step 14 + 60 min. If not yet, say so and stop the turn. The
operator can do other work; you cannot. Do not "just try" the search early - a zero result now
teaches the operator that zero is normal.

### Step 21 - Baseline: prove the mail exists and is reachable

```powershell
Import-Csv $Csv | ForEach-Object {
    .\Test-MailboxPreservation.ps1 -Identity $_.UserPrincipalName -AdminUpn $Admin -RunComplianceSearch -LogPath $LogDir
} | Format-Table Identity, MailboxState, LitigationHoldEnabled, ItemCount, MailboxSizeGB, SearchItemCount, SafeToDeleteAccount
```

**Read**: `C:\scripts\logs\MailboxPreservation-{timestamp}.csv`. Read **`MailboxSizeGB`** and
**`ItemCount`** (defect 3 - there is no `TotalItemSizeMB`). **Good**: `MailboxState = Active`,
`Verdict = PreservedReadyToDelete`, `SafeToDeleteAccount = True`, `ItemCount > 0`,
`SearchItemCount` in the same order of magnitude as `ItemCount`.

`SearchItemCount = 0` with `ItemCount` in the thousands is the propagation false negative. Wait
longer and re-run; do not proceed on it. Write down `ItemCount` per mailbox - it is the number
Step 34 compares against.

### Step 22 - Reconnect

Same block as Step 18.

### Step 23 - Record the baseline in the ticket

Write `note.md`: per mailbox UPN, `ItemCount`, `MailboxSizeGB`, `HoldTag`, `LitigationHoldDate`;
plus the paths of the two CSVs. `redact-check --emit`, then `sdp_add_note ... public=false`.

Phase boundary report: N held and verified, baseline counts, file paths.

---

## Phase C - Delete (Steps 24-31) - **irreversible**

### Step 24 - Stage 2 sign-off report

```powershell
.\Get-M365OffboardingStatus.ps1 -AdminUpn $Admin -LogPath $LogDir |
    Format-Table UserPrincipalName, DaysOnHold, Stage2Ready, LicenseSkus, SafeToRemoveLicense, BlockingIssue
```

**Read**: `C:\scripts\logs\M365OffboardingStatus-{timestamp}.csv`. The handover window defaults to
30 days on hold (`-HandoverWindowDay`); in a training run against a fresh hold `Stage2Ready` will be
`False` with `BlockingIssue` naming the window - that is the report working, not failing. Ask the
operator whether this is a training run before suggesting `-HandoverWindowDay 0`, and record the
answer in the ticket.

`SafeToRemoveLicense` always says `No`. It exists to stop the licence mistake. Ignore the licence;
delete the account.

### Step 25 - Reconnect

Same block as Step 18.

### Step 26 - Gate on `Stage2Ready`

For each UPN in the CSV: `Stage2Ready = True` and `BlockingIssue` empty. Any other row is excluded
from this batch. Say which are in and which are out, and why. If none are in, Phase C ends here.

### Step 27 - Where is each account mastered?

```powershell
Import-Csv $Csv | ForEach-Object {
    Get-MgUser -UserId $_.UserPrincipalName -Property Id, UserPrincipalName, OnPremisesSyncEnabled |
        Select-Object UserPrincipalName, Id, OnPremisesSyncEnabled
} | Format-Table -AutoSize
```

| `OnPremisesSyncEnabled` | Delete it in |
|---|---|
| `True` | **On-premises AD**, then a delta sync on `AWSPRDINFAAD01`. Deleting the cloud object is reverted at the next sync cycle |
| `False` or empty | Entra ID - portal or `Remove-MgUser` |

Record the answer per UPN. Most of this tenant is synced.

### Step 28 - Sign-off

Write `note.md`: the Stage 2 CSV path, the list cleared for deletion, the on-prem/cloud decision
per UPN, and *who approved deletion*. Ask for the approver's name. `redact-check --emit`,
`sdp_add_note`. Do not proceed until the note is on the ticket.

### Step 29 - The gate

Run **Gate 1** from `operator-safety.md` verbatim: state N, what is kept, what is lost, the on-prem
split, and require the typed phrase `DELETE {N}`. Anything else stops.

### Step 30 - Delete - one account first

For the **first** identity only:

Cloud-only:

```powershell
Remove-MgUser -UserId "first.last@contoso.com" -Confirm
```

On-prem synced - on a domain-joined admin host with RSAT:

```powershell
Get-ADUser -Identity "first.last" -Properties UserPrincipalName, Enabled | Format-List
Remove-ADUser -Identity "first.last" -Confirm
```

then the sync. Say it in these words: *"This one step runs on the server AWSPRDINFAAD01. Connect
with Remote Desktop, open the same blue Windows PowerShell window there, run these two lines, then
come back to your own PC."* `ADSync` has no PowerShell 7 build - it only loads in Windows PowerShell:

```powershell
Import-Module ADSync
Start-ADSyncSyncCycle -PolicyType Delta
```

Take this one identity through Phase D (Steps 32-34) before returning here for the rest. The
remainder is a second batch with its own `DELETE {N-1}` gate.

### Step 31 - Confirm the cloud object is gone

```powershell
Get-MgUser -UserId "first.last@contoso.com" -ErrorAction SilentlyContinue; $?
Get-MgDirectoryDeletedItemAsUser -All | Where-Object UserPrincipalName -like "first.last*" | Select-Object UserPrincipalName, DeletedDateTime
```

**Good**: first line `False` (not found), second shows the object in the recycle bin with today's
date. For a synced account this can take a full sync cycle (~30 min); if it still exists after
that, the AD delete did not happen - check the AD side, do not delete in Entra.

---

## Phase D - Validate (Steps 32-36) - read-only

Allow up to a few hours for the mailbox to convert. Deletion is not instant.

### Step 32 - Confirm the mailbox is now inactive

```powershell
Get-Mailbox -InactiveMailboxOnly -ResultSize Unlimited |
    Format-Table DisplayName, PrimarySmtpAddress, WhenSoftDeleted, LitigationHoldEnabled, LitigationHoldDuration, ExchangeGuid
```

**Good**: the mailbox is listed, `LitigationHoldEnabled = True`. **Record `ExchangeGuid`** - from
here it is the only unambiguous identifier. If the mailbox is not in the list yet, wait; if it
appears under `Get-Mailbox -SoftDeletedMailbox` instead, the hold was not in place at deletion -
this is the failure case and the 30-day clock is running. Go to `exchange-mailbox-restore` Path 4.

### Step 33 - Confirm the hold survived deletion (the key check)

```powershell
Get-Mailbox -InactiveMailboxOnly -Identity "<ExchangeGuid>" |
    Format-List DisplayName, PrimarySmtpAddress, ExchangeGuid, WhenSoftDeleted, LitigationHoldEnabled,
                LitigationHoldDate, LitigationHoldDuration, LitigationHoldOwner, RetentionComment, InPlaceHolds
```

**Good**: `LitigationHoldEnabled = True`, `LitigationHoldDuration = 2555`, `RetentionComment` intact.

### Step 34 - Post-deletion count against the baseline

```powershell
.\Test-MailboxPreservation.ps1 -Identity "<ExchangeGuid>" -AdminUpn $Admin -RunComplianceSearch -LogPath $LogDir -Verbose
```

**Read**: the new `MailboxPreservation-*.csv`. **Good**: `MailboxState = Inactive`,
`Verdict = InactivePreserved` (this is *success*, not a warning), `ItemCount` and `SearchItemCount`
match or exceed the Step 21 baseline. Then **reconnect** (Step 18 block).

If `MailboxState = SoftDeleted` / `Verdict = SoftDeletedAtRisk`: stop everything, `restore` Path 4.

### Step 35 - The three confirmation lookups

```powershell
# 1. Everything THIS process holds, by tag (active + still licensed)
Get-Mailbox -ResultSize Unlimited | Where-Object { $_.RetentionComment -like '*-Termination' } |
    Select-Object DisplayName, PrimarySmtpAddress, RetentionComment, LitigationHoldDate, LitigationHoldDuration | Format-Table -AutoSize

# 2. Every inactive mailbox and its hold state (post-deletion)
Get-Mailbox -InactiveMailboxOnly -ResultSize Unlimited |
    Select-Object DisplayName, PrimarySmtpAddress, WhenSoftDeleted, LitigationHoldEnabled, LitigationHoldDuration, ExchangeGuid | Format-Table -AutoSize

# 3. Every mailbox in the tenant on Litigation Hold, exported for the record
Get-Mailbox -ResultSize Unlimited | Where-Object { $_.LitigationHoldEnabled } |
    Select-Object DisplayName, PrimarySmtpAddress, LitigationHoldDate, LitigationHoldDuration, LitigationHoldOwner, RetentionComment, InPlaceHolds |
    Export-Csv "C:\scripts\reports\LitigationHold-Confirmation-$(Get-Date -Format yyyyMMddHHmm).csv" -NoTypeInformation -Encoding UTF8
```

A hold can come from somewhere other than Litigation Hold (retention policy, case hold, delay hold)
- all appear in `InPlaceHolds`, none set `LitigationHoldEnabled`. Report both columns.

### Step 36 - Confirm the seat came back

```powershell
Get-MgSubscribedSku -All | Where-Object SkuPartNumber -eq $Sku |
    Select-Object SkuPartNumber, ConsumedUnits, @{n='Purchased';e={$_.PrepaidUnits.Enabled}}
```

**Good**: `ConsumedUnits` dropped by the number deleted. An inactive mailbox consumes no seat.

Phase boundary report: table of UPN, `ExchangeGuid`, state, hold, baseline vs post count, seat delta.
If a batch remainder is waiting from Step 30, return to Step 29 now.

---

## Phase E - eDiscovery and export (Steps 37-41) - reversible

### Step 37 - Prove the deleted mailbox is still searchable (IPPS session)

```powershell
New-ComplianceSearch -Name "Cleanup-<alias>-Review-$(Get-Date -Format yyyyMMdd)" `
    -ExchangeLocation "first.last@contoso.com" -AllowNotFoundExchangeLocationsEnabled $true
Start-ComplianceSearch -Identity "Cleanup-<alias>-Review-<date>"
Get-ComplianceSearch -Identity "Cleanup-<alias>-Review-<date>" | Format-List Name, Status, Items, Size
(Get-ComplianceSearch -Identity "Cleanup-<alias>-Review-<date>").SearchStatistics
```

`-AllowNotFoundExchangeLocationsEnabled $true` is **mandatory**: an inactive mailbox's address no
longer resolves to a live recipient and without it the search silently targets nothing. **Good**:
`Status = Completed`, `Items` roughly the Step 21 baseline, against an account that no longer exists.
That is the whole process proven.

### Step 38 - Portal search and review (the only way to read bodies)

Purview > eDiscovery > create a case > create a search > Add locations > tick **include inactive
mailboxes** or add the address explicitly > KQL (or blank for everything) > Run > **Review sample**.
Inactive mailboxes are not always included by default.

### Step 39 - Export, if it is genuinely needed

`New-ComplianceSearchAction -Export` was retired 26 May 2025. There is no PowerShell one-liner.
`Export-Terminated-Mailbox-to-PST.ps1` is deprecated and throws - never offer it.

Portal: case > search > **Add results to a review set** > **Export** from the review set > download
with the export tool. The load-file manifest is what makes the export defensible; a bare PST is not.
Store on a restricted share; record requester, approver, reason and a deletion date.

**Prefer not exporting.** If a manager just wants to read the mail, that is
`exchange-mailbox-restore` Path 2 - a copy into a shared mailbox with proper access control. An
export is a liability the moment it exists.

### Step 40 - Chain of custody in the ticket

If an export was made: who requested, who approved, why, where it is, when it is deleted.
`redact-check --emit`, `sdp_add_note`.

### Step 41 - Close out

Final note: per mailbox `ExchangeGuid`, state, hold, baseline vs post count; seat delta; every CSV
and log path under `C:\scripts\logs` and `C:\scripts\reports`; what was **not** verified. Ask before
closing the ticket (`sdp_close`) - it is the operator's to close.

---

## Quick reference

| # | Step | Command |
|---|---|---|
| 2 | Parse input | `parse_user_input.py <addr-or-csv> --out C:\scripts\reports\holdlist.csv` |
| 4 | Preflight | `exo_preflight.ps1 -Check` |
| 7-9 | Connect | `Connect-ExchangeOnline` / `Connect-MgGraph -Scopes <union>` / `Connect-IPPSSession` |
| 10 | Roles | `& exo_preflight.ps1 -Roles -AdminUpn $Admin` (same window) |
| 12 | Seats | `Get-MgSubscribedSku -All \| ? SkuPartNumber -eq $Sku` |
| 13 | eDiscovery grant | `Get-RoleGroup \| ? { Name -eq 'eDiscoveryManager' -or DisplayName -eq 'eDiscovery Manager' }` then `Add-RoleGroupMember` |
| 16 | Dry run | `Invoke-M365OffboardingHold.ps1 -UserList $Csv -TemporaryLicenseSku $Sku -AdminUpn $Admin -LogPath $LogDir -WhatIf` |
| 17 | Apply | same, no `-WhatIf` |
| 19 | Verify | `Get-Mailbox X \| FL *Hold*, RetentionComment` |
| 21 | Baseline | `Test-MailboxPreservation.ps1 -Identity X -AdminUpn $Admin -RunComplianceSearch -LogPath $LogDir` |
| 24 | Sign-off report | `Get-M365OffboardingStatus.ps1 -AdminUpn $Admin -LogPath $LogDir` |
| 27 | Mastered where? | `Get-MgUser -UserId X -Property OnPremisesSyncEnabled` |
| 30 | Delete | `Remove-ADUser` + `Start-ADSyncSyncCycle -PolicyType Delta` on AWSPRDINFAAD01 (5.1), or `Remove-MgUser -UserId X -Confirm` |
| 32 | Inactive? | `Get-Mailbox -InactiveMailboxOnly -ResultSize Unlimited` |
| 33 | Hold survived? | `Get-Mailbox -InactiveMailboxOnly -Identity <Guid> \| FL *Hold*, InPlaceHolds` |
| 36 | Seat back? | `Get-MgSubscribedSku -All \| ? SkuPartNumber -eq $Sku` |
| 37 | Search | `New-ComplianceSearch -ExchangeLocation X -AllowNotFoundExchangeLocationsEnabled $true` |
| 39 | Export | Purview portal > case > review set > export |

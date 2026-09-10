# Mailbox Restore and Hold Removal - setup, triage, five paths

Work **setup**, then **Step 0**, then **exactly one path**, one step per turn. Every command is
printed for the operator's Windows PowerShell 5.1 window. `$Admin`, `$Repo`, `$User`, `$LogDir`
are set at S3. Shared references live in `../exchange-mailbox-cleanup/references/`; the step
numbers below refer to this file.

Legend: **Proves** - what the operator learns. **Good** - what the artifact must show before
advancing. **Read** - the file the skill reads back.

---

## Setup (S1-S6)

### S1 - Confirm the request

Ask one question: *"Which mailbox, and what does the requester want to happen?"* Take the UPN and a
one-line want. Validate the UPN (one `@`, no spaces, dotted domain). Do not ask about tickets or
roles yet. Normalise with the shared helper if it arrived as a file:

```powershell
python "$CleanupDir\scripts\parse_user_input.py" "<address-or-path>" --json
```

### S2 - The ticket

*"Do you have a ServiceDesk Plus ticket for this, or should I open one?"* Via `infra-work-ticketing`.
Title `M365 mailbox restore - {UPN} - {want}`. Never create without confirmation.
`ticketctl.py redact-check --body-file note.md --emit > note.clean.md` before every `sdp_*` write -
run by the skill in its Bash tool, never printed for the operator (`>` in a 5.1 window is UTF-16LE).

### S3 - Preflight and session variables

Skill runs `exo_preflight.ps1 -Check` (read-only). If anything is missing, confirm once and run
`-Install` - it installs under the user profile (`-Scope CurrentUser`), never machine-wide, and
verifies what landed. Then the edition check comes first:

```powershell
$PSVersionTable.PSEdition
```

**Good**: `Desktop`. If `Core`: *"Close this window. Open the Start menu, type Windows PowerShell, and
open the blue icon whose title bar says Windows PowerShell - not the one that says PowerShell 7."*
Then:

```powershell
# Blue "Windows PowerShell" window, as yourself, not elevated
$Admin  = "admin@contoso.com"
$Repo   = "C:\repos\solomon\infrastructure-scripts\Powershell\Exchange"
$User   = "first.last@contoso.com"
$LogDir = "C:\scripts\logs"
Set-Location $Repo
```

Read `*.log` files back through `python "$CleanupDir\scripts\read_log.py" <file>` - they are cp1252
under 5.1; the `*.csv` files are UTF-8 with a BOM and read directly.

### S4 - Import and connect (Graph first, IPPS last)

```powershell
Import-Module Microsoft.Graph.Authentication
Import-Module Microsoft.Graph.Users
Import-Module Microsoft.Graph.Identity.DirectoryManagement
Import-Module ExchangeOnlineManagement

Connect-ExchangeOnline -UserPrincipalName $Admin -ShowBanner:$false
Connect-MgGraph -Scopes 'Organization.Read.All','User.ReadWrite.All','Directory.AccessAsUser.All','User.RevokeSessions.All' -NoWelcome
Connect-IPPSSession -UserPrincipalName $Admin
Get-Mailbox -ResultSize 1 | Select-Object DisplayName
Get-MgContext | Select-Object Account
```

The scope list is the union of both runbooks (cleanup defect 4). Path 4 needs
`Directory.AccessAsUser.All`; the others need `User.ReadWrite.All`. **Good**: no red, one mailbox row,
`Account = $Admin`.

### S5 - Roles, in the same window

```powershell
& "$CleanupDir\scripts\exo_preflight.ps1" -Roles -AdminUpn $Admin
```

**Good**: `PASS` Exchange Administrator. eDiscovery Manager is only needed if Step 0 will run a
compliance search (it does not by default) - a `FAIL` there does not block restore work.

### S6 - Roles by path

| Path | Needs | Session |
|---|---|---|
| 1, 5 | Exchange Administrator (`Set-Mailbox`) | EXO |
| 2 | Exchange Administrator (`New-Mailbox`, `New-MailboxRestoreRequest`, `Add-MailboxPermission`) | EXO |
| 3 | Exchange Administrator (`New-Mailbox -InactiveMailbox`) + a licence to assign | EXO + Graph |
| 4 | User Administrator or Global Administrator (`Restore-MgDirectoryDeletedItem`) | Graph |

---

## Step 0 - Triage: what state is the mailbox actually in?

```powershell
.\Test-MailboxPreservation.ps1 -Identity $User -AdminUpn $Admin -LogPath $LogDir |
    Format-List Identity, MailboxState, LitigationHoldEnabled, HoldMechanism, InPlaceHolds, ExchangeGuid, WhenSoftDeleted, ItemCount, MailboxSizeGB, Verdict, Detail
```

**Read**: `C:\scripts\logs\MailboxPreservation-{timestamp}.csv`. Then **reconnect** - the script
disconnected the operator:

```powershell
Connect-ExchangeOnline -UserPrincipalName $Admin -ShowBanner:$false
Connect-IPPSSession -UserPrincipalName $Admin
```

Record `ExchangeGuid` immediately. It is the identity for every later command on an inactive
mailbox.

| `MailboxState` | Meaning | Go to |
|---|---|---|
| `Active` | Account exists, nothing deleted | Path 1 |
| `Inactive` | Account deleted, hold preserved the mailbox | Path 2 (read the mail) or Path 3 (person returning) |
| `SoftDeleted` | Deleted **with no hold**. Recoverable 30 days from `WhenSoftDeleted`, then purged | Path 4 - **print `DaysLeft` in this turn** |
| `NotFound` | Past 30 days, or purged, or a wrong identity | Read `Detail` for near-matches (`first@` vs `first.last@`). If still nothing, escalate. No path |

Then map the requester's want:

| Want | Path | Operation |
|---|---|---|
| "Held by mistake / they're staying" | 1 | Remove Litigation Hold from an active mailbox |
| "Manager needs to read the ex-employee's mail" | 2 | Restore into a shared mailbox - **most common** |
| "They're coming back and want their mailbox" | 3 | Recover the inactive mailbox - **destroys the preserved copy** |
| "We deleted them by mistake, days ago" | 4 | Undelete the account - 30-day window |
| "Retention expired, destroy it - authorised in writing" | 5 | Remove the last hold - **permanent** |

State the path and the reason in two sentences. If state and want conflict (e.g. `Inactive` but
"deleted by mistake, bring them back"), explain that Path 3 is what brings the *person* back and
Path 2 keeps the evidence, and ask which. Do not guess.

---

## Path 1 - Remove hold from an ACTIVE mailbox (reversible)

Nothing is deleted. You are clearing a flag - but items past their MRM age become deletable on the
next pass, so say so.

### 1.1 - Record what is there now

```powershell
Get-Mailbox -Identity $User |
    Format-List DisplayName, LitigationHoldEnabled, LitigationHoldDate, LitigationHoldDuration, LitigationHoldOwner,
                RetentionComment, RetentionPolicy, InPlaceHolds, ComplianceTagHoldApplied, DelayHoldApplied
```

Decode `InPlaceHolds` with the shared `hold-and-mailbox-states.md`: `mbx` retention policy, `-mbx`
excluded, `UniH` eDiscovery case, `grp` group, `skp` Skype. **Tell the operator which of the four
holds are present.** Removing Litigation Hold releases the mailbox only if it is the only one.

### 1.2 - Remove the hold and clear the tag

State: *"This removes Litigation Hold from {User}. `InPlaceHolds` shows {decoded}. Continue?"* On yes:

```powershell
Set-Mailbox -Identity $User -LitigationHoldEnabled $false
Set-Mailbox -Identity $User -RetentionComment $null     # or it keeps appearing in the -Termination confirmation report
```

### 1.3 - Verify

```powershell
Get-Mailbox -Identity $User | Format-List LitigationHoldEnabled, RetentionComment, InPlaceHolds, DelayHoldApplied
```

**Good**: `LitigationHoldEnabled = False`, `RetentionComment` empty. `DelayHoldApplied = True` is
normal for ~30 days and is not a failure.

### 1.4 - The temporary licence (a read, not a change)

```powershell
Get-MgUserLicenseDetail -UserId $User | Select-Object SkuPartNumber
```

If the cleanup assigned a temporary `SPE_E3` seat purely to enable the hold and the person is
staying, the seat is theirs to keep or hand back **through normal licensing** - not through this
skill. **Do not print a licence-removal command.** If any hold remained at 1.3, say the licence must
stay; removing it soft-deletes a live mailbox and purges it in 30 days.

### 1.5 - Ticket note and close

Before/after hold state, decoded `InPlaceHolds`, licence state. Ask before `sdp_close`.

---

## Path 2 - Restore an INACTIVE mailbox into a shared mailbox (non-destructive)

The right answer to "we need their old email". Copies; the inactive mailbox stays on hold. You
cannot grant permissions on an inactive mailbox - `Add-MailboxPermission` has nothing to grant
against once the account is gone - which is why the mail is copied somewhere permissions do work.

### 2.1 - Find the inactive mailbox and record its ExchangeGuid

```powershell
Get-Mailbox -InactiveMailboxOnly -ResultSize Unlimited |
    Format-Table DisplayName, PrimarySmtpAddress, WhenSoftDeleted, ExchangeGuid

Get-Mailbox -InactiveMailboxOnly -Identity $User |
    Format-List DisplayName, PrimarySmtpAddress, ExchangeGuid, DistinguishedName, WhenSoftDeleted, LitigationHoldEnabled, ArchiveStatus

$Guid = "00000000-0000-0000-0000-000000000000"     # <- paste the ExchangeGuid
```

**Use the GUID, not the address, from here on.** An inactive mailbox can share an SMTP address with
a live one and the address resolves to the wrong mailbox without error. **Good**: exactly one row
for `$User`; `LitigationHoldEnabled = True`. Note `ArchiveStatus` - `Active` means a second restore
for the archive at 2.3.

### 2.2 - Create the target shared mailbox

Ask *who* needs access and *what to call it*. A shared mailbox under 50 GB needs no licence.

```powershell
New-Mailbox -Shared -Name "Archive-first.last" -DisplayName "Archive - First Last" -PrimarySmtpAddress "archive-first.last@contoso.com"
```

**Good**: one row returned, `RecipientTypeDetails = SharedMailbox`.

### 2.3 - Start the restore

State: *"This copies {ItemCount} items into `archive-first.last`. The inactive mailbox is untouched.
Continue?"* On yes:

```powershell
New-MailboxRestoreRequest -SourceMailbox $Guid -TargetMailbox "archive-first.last@contoso.com" `
    -TargetRootFolder "First Last - Archive" -AllowLegacyDNMismatch
```

| Parameter | Why |
|---|---|
| `-AllowLegacyDNMismatch` | **Required** whenever source and target are different people - every handover. Without it the request fails outright |
| `-TargetRootFolder` | Puts everything in one subfolder instead of merging into the target's Inbox. **Always** |

If `ArchiveStatus` was `Active`, the online archive is a separate request:

```powershell
New-MailboxRestoreRequest -SourceMailbox $Guid -SourceIsArchive -TargetMailbox "archive-first.last@contoso.com" -TargetIsArchive `
    -TargetRootFolder "First Last - Archive" -AllowLegacyDNMismatch
```

### 2.4 - Monitor to completion

```powershell
Get-MailboxRestoreRequest | Get-MailboxRestoreRequestStatistics |
    Format-Table Name, Status, PercentComplete, BytesTransferred, ItemsTransferred
```

**Good**: `Status = Completed`, `PercentComplete = 100`. A large mailbox takes hours; `InProgress` is
not a failure. `Failed`: `Get-MailboxRestoreRequestStatistics -IncludeReport | Select -Expand Report`
and quote it verbatim.

### 2.5 - Grant access to the SHARED mailbox

```powershell
Add-MailboxPermission -Identity "archive-first.last@contoso.com" -User "manager@contoso.com" -AccessRights FullAccess -AutoMapping:$false
```

`-AutoMapping:$false` is deliberate - automapping a large archive slows Outlook noticeably. The
manager adds it as a secondary mailbox by hand. Print the two-line Outlook instruction for them.

### 2.6 - Confirm the source is still preserved, then tidy up

```powershell
Get-Mailbox -InactiveMailboxOnly -Identity $Guid | Format-List DisplayName, LitigationHoldEnabled, LitigationHoldDuration

# Scope the tidy-up to THIS target mailbox. Review the list before removing anything.
Get-MailboxRestoreRequest -TargetMailbox "archive-first.last@contoso.com" -Status Completed
Get-MailboxRestoreRequest -TargetMailbox "archive-first.last@contoso.com" -Status Completed | Remove-MailboxRestoreRequest -Confirm:$false
```

**Two things about that last line, both deliberate.**

`-TargetMailbox` is not optional here. `Get-MailboxRestoreRequest -Status Completed` on its own
returns every completed restore request **in the tenant**, so piping the unscoped form into a bulk
remove erases other people's record of what was restored and when. It destroys no mail, which is
exactly what makes it easy to run without noticing. Always scope it, and run the plain `Get-` line
first so the operator sees what is about to go.

`-Confirm:$false` is the one place this skill prints it, against the rule in
`operator-safety.md`. The exemption is narrow and it is on purpose: a *completed* restore request
is a bookkeeping record, not mail — the messages it moved are already in the target mailbox and
are untouched by removing it. Microsoft's own guidance is to clear them, because completed
requests count against a per-mailbox limit and a full queue blocks the next restore. Nowhere else
in either skill does a printed command suppress a confirmation.

**Good**: the manager can read the mail **and** the inactive mailbox still shows
`LitigationHoldEnabled = True`. Both at once. Nothing was given up. Ticket note; ask before close.

---

## Path 3 - RECOVER an inactive mailbox (returning employee) - **destroys the preserved copy**

After recovery it is a normal licensed mailbox and the inactive copy no longer exists, so the
preservation ends. If anyone might still need the preserved copy for legal or HR, **Path 2 instead**,
or export from eDiscovery first.

### 3.1 - Identifiers

```powershell
Get-Mailbox -InactiveMailboxOnly -Identity $User |
    Format-List Name, DisplayName, ExchangeGuid, DistinguishedName, PrimarySmtpAddress, LitigationHoldEnabled, ItemCount
$Guid = "<ExchangeGuid>"
```

### 3.2 - Decide where the new account lives - before running anything

In a hybrid directory recovery interacts with sync and a mismatch is painful to unpick. Ask: *"Will
this person be created in on-premises AD (and synced), or cloud-only?"* Most of this tenant is
synced, so the usual answer is: create the AD user on-premises first, let the delta sync run,
confirm `Get-MgUser -UserId $User -Property OnPremisesSyncEnabled` shows `True`, **then** recover
onto it. The sync is the one step on another machine - say so: *"Connect to AWSPRDINFAAD01 with
Remote Desktop, open the same blue Windows PowerShell window there, run these two lines, then come
back."* `ADSync` has no PowerShell 7 build.

```powershell
Import-Module ADSync
Start-ADSyncSyncCycle -PolicyType Delta
```

Record the decision in the ticket.

### 3.3 - The gate, then recover

Run **Gate 2** from the shared `operator-safety.md`: what is lost, Path 2 still available, typed
`RECOVER 1`. On exactly that:

```powershell
New-Mailbox -InactiveMailbox $Guid -Name "First Last" -FirstName First -LastName Last -DisplayName "First Last" `
    -MicrosoftOnlineServicesID $User -Password (Read-Host -AsSecureString "New password")
```

### 3.4 - Assign a licence and verify

Recovery consumes a seat. Assign the licence through normal licensing (portal or the standard
process - this skill does not print a licence assignment). Then:

```powershell
Get-Mailbox -Identity $User | Format-List DisplayName, RecipientTypeDetails, PrimarySmtpAddress, LitigationHoldEnabled, IsInactiveMailbox
Get-Mailbox -InactiveMailboxOnly -ResultSize Unlimited | Where-Object PrimarySmtpAddress -eq $User     # should return nothing
```

**Good**: a `UserMailbox` exists, `IsInactiveMailbox = False`, and the inactive list no longer
contains them. Ticket note: the gate (who typed it, when), the directory decision, the result.

---

## Path 4 - UNDELETE the account (30-day window, deleted by mistake)

Time-boxed. A deleted Entra account sits in the recycle bin for 30 days; a mailbox soft-deleted by
licence removal is likewise recoverable for 30 days from `WhenSoftDeleted`. After that, both are
purged with no support path. **Check the clock first and say the number in the first reply.**

### 4.1 - How long do you have?

```powershell
Get-Mailbox -SoftDeletedMailbox -ResultSize Unlimited |
    Select-Object DisplayName, PrimarySmtpAddress, WhenSoftDeleted, ExchangeGuid,
                  @{n='DaysLeft';e={30 - ((Get-Date) - $_.WhenSoftDeleted).Days}} | Format-Table -AutoSize
```

Print `DaysLeft` for `$User` back to the operator immediately. Under 3 days: say so, and do not
spend a turn on the ticket until 4.3 is done - log it afterwards.

### 4.2 - Find the account in the Entra recycle bin (Graph)

```powershell
Get-MgDirectoryDeletedItemAsUser -All | Select-Object Id, UserPrincipalName, DisplayName, DeletedDateTime | Format-Table -AutoSize
```

**Good**: `$User` listed. Record `Id`. Not listed and `DaysLeft > 0`: the *mailbox* is soft-deleted
but the *user* is not in the bin - the account was probably de-licensed, not deleted. Re-licensing
the existing user reattaches the mailbox; skip 4.3.

### 4.3 - Restore it

State: *"This restores the Entra account {UPN}. Reversible (it can be deleted again). Continue?"*

```powershell
Restore-MgDirectoryDeletedItem -DirectoryObjectId "<Id from 4.2>"
```

Portal equivalent: entra.microsoft.com > Users > Deleted users > select > Restore user.

If the account was on-prem synced, the AD object must be restored on-premises too (AD Recycle Bin,
`Restore-ADObject`) and a delta sync run, or the next sync deletes it again.

### 4.4 - Re-license, then verify the mailbox came back

Licence through normal licensing. Then:

```powershell
Get-Mailbox -Identity $User | Format-List DisplayName, RecipientTypeDetails, IsInactiveMailbox, LitigationHoldEnabled
Get-MailboxStatistics -Identity $User | Select-Object ItemCount, TotalItemSize
```

The mailbox does not reattach instantly. Allow hours after restoring and re-licensing before
concluding the mail is gone. **Say plainly in the report that reattachment was not verified** if it
was not.

### 4.5 - Ticket note

`DaysLeft` at start, the `Id` restored, the licence, what is and is not yet verified.

---

## Path 5 - PERMANENT destruction (retention expired) - **irreversible**

No undo, no support path. Only with written authorisation, only once the retention obligation has
genuinely ended. Record who authorised it, when, and against which retention schedule, in the ticket
**before** any command.

### 5.1 - Confirm every hold, not just Litigation Hold

```powershell
Get-Mailbox -InactiveMailboxOnly -Identity $Guid |
    Format-List DisplayName, LitigationHoldEnabled, LitigationHoldDate, LitigationHoldDuration, InPlaceHolds,
                ComplianceTagHoldApplied, DelayHoldApplied, DelayReleaseHoldApplied
```

(For an active mailbox drop `-InactiveMailboxOnly` and use `$User`.) Exchange purges only once the
**last** hold is removed. If `InPlaceHolds` still lists `UniH` or `mbx`, removing Litigation Hold
changes nothing - a safety feature, not a fault. **Stop** and say which hold remains and who owns
its release (the case owner; the retention policy admin). Do not proceed until 5.1 shows Litigation
Hold as the only hold.

### 5.2 - The gate, then remove the hold

Run **Gate 3** from the shared `operator-safety.md`: authorisation reference on file, what is lost,
typed `DESTROY 1`. On exactly that:

```powershell
# Inactive mailbox - by ExchangeGuid
Set-Mailbox -InactiveMailbox -Identity $Guid -LitigationHoldEnabled $false

# Active mailbox
Set-Mailbox -Identity $User -LitigationHoldEnabled $false
```

Print only the one that applies.

### 5.3 - Clear the delay hold (verify against Microsoft Learn first)

Exchange applies a delay hold for ~30 days after the last hold is removed. If the intent is genuine
destruction, clear it explicitly - **after** confirming both parameters still exist on current
Microsoft Learn (`Set-Mailbox` reference) in this session:

```powershell
Set-Mailbox -Identity $User -RemoveDelayHoldApplied
Set-Mailbox -Identity $User -RemoveDelayReleaseHoldApplied
```

Being wrong here is unrecoverable in one direction and merely embarrassing in the other.

### 5.4 - Record the outcome

```powershell
Get-Mailbox -ResultSize Unlimited | Where-Object { $_.LitigationHoldEnabled } |
    Select-Object DisplayName, PrimarySmtpAddress, LitigationHoldDate, LitigationHoldDuration, LitigationHoldOwner, RetentionComment |
    Export-Csv "C:\scripts\reports\LitigationHold-AfterRemoval-$(Get-Date -Format yyyyMMddHHmm).csv" -NoTypeInformation -Encoding UTF8
```

Keep that CSV with the written authorisation. Ticket note: the authorisation reference, the gate
(who typed it, when), the 5.1 output, the CSV path.

---

## Quick reference

| Path | Situation | Key command |
|---|---|---|
| 0 | What state is it in? | `Test-MailboxPreservation.ps1 -Identity $User -AdminUpn $Admin -LogPath $LogDir` |
| 1 | Held by mistake, still active | `Set-Mailbox -Identity $User -LitigationHoldEnabled $false` |
| 2 | Manager needs to read the mail | `New-MailboxRestoreRequest -SourceMailbox $Guid -TargetMailbox X -TargetRootFolder Y -AllowLegacyDNMismatch` |
| 3 | Employee returning | `New-Mailbox -InactiveMailbox $Guid -MicrosoftOnlineServicesID $User -Password ...` - **gated** |
| 4 | Deleted by mistake, < 30 days | `Restore-MgDirectoryDeletedItem -DirectoryObjectId <Id>` |
| 5 | Retention expired, authorised | `Set-Mailbox -InactiveMailbox -Identity $Guid -LitigationHoldEnabled $false` - **gated** |
| - | Find the ExchangeGuid | `Get-Mailbox -InactiveMailboxOnly -Identity $User \| FL ExchangeGuid` |
| - | Monitor a restore | `Get-MailboxRestoreRequest \| Get-MailboxRestoreRequestStatistics` |

## The six traps (each a confident wrong answer, not an error)

| Trap | What actually happens |
|---|---|
| Recovering when you meant to restore | Inactive mailbox consumed; preserved copy gone. Restore copies; recover reactivates |
| Identifying an inactive mailbox by SMTP address | Collides with a live mailbox and resolves to the wrong one silently. Use `ExchangeGuid` |
| Removing a licence to "release" a mailbox | Soft-deletes it; purged in 30 days. Deletion, not de-licensing, makes a mailbox inactive |
| Reading only `LitigationHoldEnabled` | Misses retention-policy, case and delay holds in `InPlaceHolds`. Mailbox stays preserved and it looks like the removal failed |
| Omitting `-AllowLegacyDNMismatch` | Restore fails whenever source and target are different people - every handover |
| Omitting `-TargetRootFolder` | The leaver's mail merges into the target's Inbox and is painful to separate |

## Verify before relying on this

Purview and Exchange Online change frequently. Before acting on a legal or HR request, confirm
against current Microsoft Learn: *Manage inactive mailboxes*, *Restore an inactive mailbox*,
*Recover an inactive mailbox*, and the `New-MailboxRestoreRequest` / `Set-Mailbox` cmdlet
references.

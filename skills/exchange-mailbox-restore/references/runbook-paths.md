# Mailbox Restore and Hold Removal - setup, triage, five paths

Work **setup**, then **Step 0**, then **exactly one path**, one step per turn. Every command is
printed for the operator's blue Windows PowerShell window **already filled in** - no session
variables, no directory change. Braces (`{Admin}`, `{User}`, `{ExchangeGuid}`, `{Repo}`,
`{SkillDir}`) are values the skill substitutes before printing; the operator never sees one. The
shared references (`connect-and-preflight.md`, `hold-and-mailbox-states.md`, `operator-safety.md`)
are this skill's own copies under `references/`; the step numbers below refer to this file.

Legend: **Proves** - what the operator learns. **Good** - what the artifact must show before
advancing. **Read** - the file the skill reads back.

---

## Setup (S1-S6)

### S1 - Confirm the request

Ask one question: *"Which mailbox, and what does the requester want to happen?"* Take the UPN and a
one-line want. Validate the UPN (one `@`, no spaces, dotted domain). Do not ask about tickets or
roles yet. Normalise with the shared helper if it arrived as a file:

```powershell
powershell.exe -NoProfile -File "{SkillDir}\scripts\Resolve-OperatorInput.ps1" -Value "{AddressOrPath}" -AsJson
```

### S2 - The ticket (advisory - never a blocker)

*"Do you have a ServiceDesk Plus ticket for this, or should I open one?"* Via `infra-work-ticketing`.
Title `M365 mailbox restore - {UPN} - {want}`. Never create without confirmation.
`ticketctl.py redact-check --body-file note.md --emit > note.clean.md` before every `sdp_*` write -
run by the skill in its Bash tool, never printed for the operator (`>` in a 5.1 window is UTF-16LE).

If the `sdp_*` tools are not loaded, or S3's preflight reports `TicketingUnavailable`, say once -
*"Ticketing is not reachable from here, so I will keep the record in the closing report instead."* -
and skip every later ticket note. The restore never waits on a ticket. Path 5's written
authorisation is still required; it goes in the closing report if there is no ticket.

### S3 - Preflight, edition check, admin UPN

Skill runs `exo_preflight.ps1 -Check` (read-only). If anything is missing, say what and offer to fix
it in the same message; on one yes, run `-Install` - it installs under the user profile
(`-Scope CurrentUser`), never machine-wide, creates the two directories, and verifies what landed.
Then the edition check comes first:

```powershell
$PSVersionTable.PSEdition
```

**Good**: `Desktop`. If `Core`: *"Close this window. Open the Start menu, type Windows PowerShell, and
open the blue icon whose title bar says Windows PowerShell - not the one that says PowerShell 7."*
Then ask for the one value the skill cannot know - *"Which account do you sign in to Microsoft 365
admin with? Paste the full address."* - validate it, and use it as `{Admin}` everywhere. Never print
a sample address for them to replace.

Read `*.log` files back through
`powershell.exe -NoProfile -File "{SkillDir}\scripts\Read-ScriptLog.ps1" -Path {File}` - they are
cp1252 under 5.1; the `*.csv` files are UTF-8 with a BOM and read directly.

### S4 - Import and connect (Graph first, IPPS last)

```powershell
Import-Module Microsoft.Graph.Authentication -RequiredVersion 2.39.0
Import-Module Microsoft.Graph.Users -RequiredVersion 2.39.0
Import-Module Microsoft.Graph.Users.Actions -RequiredVersion 2.39.0
Import-Module Microsoft.Graph.Identity.DirectoryManagement -RequiredVersion 2.39.0
Import-Module ExchangeOnlineManagement

Connect-ExchangeOnline -UserPrincipalName '{Admin}' -ShowBanner:$false
Connect-MgGraph -Scopes 'Organization.Read.All','User.ReadWrite.All','Directory.AccessAsUser.All','User.RevokeSessions.All' -NoWelcome
Connect-IPPSSession -UserPrincipalName '{Admin}'
Get-Mailbox -ResultSize 1 | Select-Object DisplayName
Get-MgContext | Select-Object Account
```

The scope list is the union of both runbooks (cleanup defect 4). Path 4 needs
`Directory.AccessAsUser.All`; the others need `User.ReadWrite.All`. `-RequiredVersion 2.39.0` is the
version the upstream driver scripts import; keeping the operator's imports on it means
no driver can demand a restart after the logins. **Good**: no red, one mailbox row, `Account = {Admin}`.

### S5 - Roles, in the same window

```powershell
& "{SkillDir}\scripts\exo_preflight.ps1" -Roles -AdminUpn '{Admin}'
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
& "{Repo}\Test-MailboxPreservation.ps1" -Identity '{User}' -AdminUpn '{Admin}' -LogPath 'C:\scripts\logs' |
    Format-List Identity, MailboxState, LitigationHoldEnabled, HoldMechanism, InPlaceHolds, ExchangeGuid, WhenSoftDeleted, ItemCount, MailboxSizeGB, Verdict, Detail
```

**Read**: `C:\scripts\logs\MailboxPreservation-{timestamp}.csv`. Then **reconnect** - the script
disconnected the operator's Exchange sessions, and the other upstream drivers also drop Graph, so
restore all three every time:

```powershell
Connect-ExchangeOnline -UserPrincipalName '{Admin}' -ShowBanner:$false
Connect-IPPSSession -UserPrincipalName '{Admin}'
Connect-MgGraph -Scopes 'Organization.Read.All','User.ReadWrite.All','Directory.AccessAsUser.All','User.RevokeSessions.All' -NoWelcome
```

Record `ExchangeGuid` immediately. It is the identity for every later command on an inactive
mailbox. Two more facts decide the path and come from one extra read:

```powershell
Get-Mailbox -InactiveMailboxOnly -Identity '{User}' | Format-List ExchangeGuid, ExternalDirectoryObjectId, AutoExpandingArchiveEnabled, ArchiveStatus, LegacyExchangeDN
```

- `ExternalDirectoryObjectId` **has a value** -> the account was deleted less than 30 days ago and
  Microsoft Learn says "you can't use the New-Mailbox -InactiveMailbox command to recover it. You
  need to recover it by restoring the corresponding user account" - that is Path 4, even when the
  requester says "recover".
- `AutoExpandingArchiveEnabled = True` -> Learn: "You can't recover or restore an inactive mailbox
  that's configured with an auto-expanding archive." Neither Path 2 nor Path 3 will work; the
  content is reachable only through a Purview content search export. Say so and stop.

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
| "Retention expired, destroy it - authorised in writing" | 5 | Remove the last hold from an **inactive** mailbox - **permanent** |

State the path and the reason in two sentences. If state and want conflict (e.g. `Inactive` but
"deleted by mistake, bring them back"), explain that Path 3 is what brings the *person* back and
Path 2 keeps the evidence, and ask which. Do not guess.

---

## Path 1 - Remove hold from an ACTIVE mailbox (reversible)

Nothing is deleted. You are clearing a flag - but items past their MRM age become deletable on the
next pass, so say so.

### 1.1 - Record what is there now

```powershell
Get-Mailbox -Identity '{User}' |
    Format-List DisplayName, LitigationHoldEnabled, LitigationHoldDate, LitigationHoldDuration, LitigationHoldOwner,
                RetentionComment, RetentionPolicy, InPlaceHolds, ComplianceTagHoldApplied, DelayHoldApplied
```

Decode `InPlaceHolds` with the shared `hold-and-mailbox-states.md`: `mbx` retention policy, `-mbx`
excluded, `UniH` eDiscovery case, `grp` group, `skp` Skype. **Tell the operator which of the four
holds are present.** Removing Litigation Hold releases the mailbox only if it is the only one.

### 1.2 - Remove the hold and clear the tag

State: *"This removes Litigation Hold from {User}. `InPlaceHolds` shows {decoded}. Continue?"* On yes:

```powershell
Set-Mailbox -Identity '{User}' -LitigationHoldEnabled $false
Set-Mailbox -Identity '{User}' -RetentionComment $null     # or it keeps appearing in the -Termination confirmation report
```

### 1.3 - Verify

```powershell
Get-Mailbox -Identity '{User}' | Format-List LitigationHoldEnabled, RetentionComment, InPlaceHolds, DelayHoldApplied
```

**Good**: `LitigationHoldEnabled = False`, `RetentionComment` empty. `DelayHoldApplied = True` is
normal for ~30 days and is not a failure.

### 1.4 - The temporary licence (a read, not a change)

```powershell
Get-MgUserLicenseDetail -UserId '{User}' | Select-Object SkuPartNumber
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

Get-Mailbox -InactiveMailboxOnly -Identity '{User}' |
    Format-List DisplayName, PrimarySmtpAddress, ExchangeGuid, DistinguishedName, WhenSoftDeleted, LitigationHoldEnabled, ArchiveStatus

```

**Use the GUID, not the address, from here on.** An inactive mailbox can share an SMTP address with
a live one and the address resolves to the wrong mailbox without error. **Good**: exactly one row
for `'{User}'`; `LitigationHoldEnabled = True`. Note `ArchiveStatus` - `Active` means a second restore
for the archive at 2.3.

### 2.2 - Create the target shared mailbox

Ask *who* needs access and *what to call it*. A shared mailbox under 50 GB needs no licence.

```powershell
New-Mailbox -Shared -Name '{ArchiveName}' -DisplayName '{ArchiveDisplayName}' -PrimarySmtpAddress '{ArchiveAddress}'
```

**Good**: one row returned, `RecipientTypeDetails = SharedMailbox`, `ArchiveStatus = None`. **A new
shared mailbox has no archive.** If Step 0 showed the source `ArchiveStatus = Active`, decide now
where its archive goes - see 2.3.

### 2.3 - Start the restore

State: *"This copies {ItemCount} items into `archive-first.last`. The inactive mailbox is untouched.
Continue?"* On yes:

```powershell
New-MailboxRestoreRequest -SourceMailbox '{ExchangeGuid}' -TargetMailbox '{ArchiveAddress}' `
    -TargetRootFolder '{ArchiveFolder}' -AllowLegacyDNMismatch
```

| Parameter | Why |
|---|---|
| `-AllowLegacyDNMismatch` | **Required** whenever source and target are different people - every handover. Without it the request fails outright |
| `-TargetRootFolder` | Puts everything in one subfolder instead of merging into the target's Inbox. **Always** |

`-AllowLegacyDNMismatch` is the cmdlet's documented way past the `LegacyExchangeDN` check. Microsoft
Learn's *Restore an inactive mailbox* page takes the other route - "add the LegacyExchangeDN of the
inactive mailbox to the target mailbox, as an X500 proxy address" - which also works and leaves a
trace on the target; either is acceptable, use one.

If the source `ArchiveStatus` was `Active`, the online archive is a separate request, and **the
target created at 2.2 has no archive**, so `-TargetIsArchive` would fail. Learn shows the form that
needs none: "you can run this command to restore the archive from the inactive mailbox into the
primary mailbox of the target mailbox" -

```powershell
New-MailboxRestoreRequest -SourceMailbox '{ExchangeGuid}' -SourceIsArchive -TargetMailbox '{ArchiveAddress}' `
    -TargetRootFolder '{ArchiveFolder} (Online Archive)' -AllowLegacyDNMismatch
```

Use that by default. Only if primary + archive would exceed the shared mailbox's 50 GB does the target
need its own archive - `Enable-Mailbox -Identity '{ArchiveAddress}' -Archive`, which on a shared
mailbox requires an Exchange Online Plan 2 or Exchange Online Archiving licence assigned to it first -
and then the `-TargetIsArchive` form. Check the sizes before choosing:
`Get-MailboxStatistics -Identity '{ExchangeGuid}' -IncludeSoftDeletedRecipients | Select TotalItemSize` and
the same with `-Archive`.

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
Add-MailboxPermission -Identity '{ArchiveAddress}' -User '{ManagerUpn}' -AccessRights FullAccess -AutoMapping:$false
```

`-AutoMapping:$false` is deliberate - automapping a large archive slows Outlook noticeably. The
manager adds it as a secondary mailbox by hand. Print the two-line Outlook instruction for them.

### 2.6 - Confirm the source is still preserved, then tidy up

```powershell
Get-Mailbox -InactiveMailboxOnly -Identity '{ExchangeGuid}' | Format-List DisplayName, LitigationHoldEnabled, LitigationHoldDuration

# Scope the tidy-up to THIS target mailbox. Review the list before removing anything.
Get-MailboxRestoreRequest -TargetMailbox '{ArchiveAddress}' -Status Completed
Get-MailboxRestoreRequest -TargetMailbox '{ArchiveAddress}' -Status Completed | Remove-MailboxRestoreRequest -Confirm:$false
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

**Path 3 applies only when both are true**, per Microsoft Learn (*Recover an inactive mailbox*):

1. The 30-day soft-delete window has passed - `ExternalDirectoryObjectId` is **empty** (Step 0).
   "If an inactive mailbox was soft-deleted less than 30 days ago, you can't use the New-Mailbox
   -InactiveMailbox command to recover it. You need to recover it by restoring the corresponding
   user account." Inside the window this is **Path 4**, whatever the requester called it.
2. The returning person will be **cloud-only**. `New-Mailbox -InactiveMailbox` creates a *new* user:
   "Be sure that the values specified for the Name and MicrosoftOnlineServicesID parameters are
   unique within your organization." It cannot recover onto an account that already exists - so it
   cannot target a user created on-premises and synced. In this tenant most accounts are synced,
   so the usual answer for a returning employee is: create the on-prem user, sync, licence (a new
   empty mailbox appears), then run **Path 2** targeting that mailbox - Learn lists "that employee
   returns to your organization" as a *restore* use case too. The preserved copy then survives,
   which is the better outcome anyway.

### 3.1 - Identifiers

```powershell
Get-Mailbox -InactiveMailboxOnly -Identity '{User}' |
    Format-List Name, DisplayName, ExchangeGuid, DistinguishedName, PrimarySmtpAddress, LitigationHoldEnabled, ItemCount
```

Record `ExchangeGuid`; it is `{ExchangeGuid}` in every later command on this path.

### 3.2 - Decide where the new account lives - before running anything

Ask: *"Will this person be created in on-premises AD (and synced), or cloud-only?"*

| Answer | Route |
|---|---|
| On-premises, synced (the usual case here) | **Not Path 3.** Create the AD user on-premises, run the delta sync, licence the new cloud user so an empty mailbox appears, then run **Path 2** with that mailbox as the target. `New-Mailbox -InactiveMailbox` cannot attach to an existing account |
| Cloud-only | Continue to 3.3. Confirm `Get-MgUser -UserId '{User}'` returns nothing (`Request_ResourceNotFound`) - the `MicrosoftOnlineServicesID` must not already exist |

The sync is the one step on another machine - say so: *"Connect to AWSPRDINFAAD01 with Remote
Desktop, open the same blue Windows PowerShell window there, run these two lines, then come back."*
`ADSync` has no PowerShell 7 build.

```powershell
Import-Module ADSync
Start-ADSyncSyncCycle -PolicyType Delta
```

Record the decision in the ticket.

### 3.3 - The gate, then recover

Run **Gate 2** from the shared `operator-safety.md`: what is lost, Path 2 still available, typed
`RECOVER 1`. On exactly that:

```powershell
New-Mailbox -InactiveMailbox '{ExchangeGuid}' -Name '{DisplayName}' -FirstName '{FirstName}' -LastName '{LastName}' -DisplayName '{DisplayName}' `
    -MicrosoftOnlineServicesID '{User}' -Password (Read-Host -AsSecureString "New password") -ResetPasswordOnNextLogon $true
```

`-Name` and `-MicrosoftOnlineServicesID` must both be unique in the tenant (Learn). Recovery
creates the user; the licence is assigned afterwards (3.4). Learn also notes the recovered mailbox
gets a 30-day retention hold and 30-day single-item recovery, and suggests enabling an archive.

### 3.4 - Assign a licence and verify

Recovery consumes a seat. Assign the licence through normal licensing (portal or the standard
process - this skill does not print a licence assignment). Then:

```powershell
Get-Mailbox -Identity '{User}' | Format-List DisplayName, RecipientTypeDetails, PrimarySmtpAddress, LitigationHoldEnabled, IsInactiveMailbox
Get-Mailbox -InactiveMailboxOnly -ResultSize Unlimited | Where-Object PrimarySmtpAddress -eq '{User}'     # should return nothing
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

Print `DaysLeft` for `'{User}'` back to the operator immediately. Under 3 days: say so, and do not
spend a turn on the ticket until 4.3 is done - log it afterwards.

### 4.2 - Find the account in the Entra recycle bin (Graph)

```powershell
Get-MgDirectoryDeletedItemAsUser -All | Select-Object Id, UserPrincipalName, DisplayName, DeletedDateTime | Format-Table -AutoSize
```

**Good**: `'{User}'` listed. Record `Id`. Not listed and `DaysLeft > 0`: the *mailbox* is soft-deleted
but the *user* is not in the bin - the account was probably de-licensed, not deleted. Re-licensing
the existing user reattaches the mailbox; skip 4.3.

### 4.3 - Restore it

State: *"This restores the Entra account {UPN}. Reversible (it can be deleted again). Continue?"*

```powershell
Restore-MgDirectoryDeletedItem -DirectoryObjectId '{DeletedItemId}'
```

Portal equivalent: entra.microsoft.com > Users > Deleted users > select > Restore user.

If the account was on-prem synced, the AD object must be restored on-premises too (AD Recycle Bin,
`Restore-ADObject`) and a delta sync run, or the next sync deletes it again.

### 4.4 - Re-license, then verify the mailbox came back

Licence through normal licensing. Then:

```powershell
Get-Mailbox -Identity '{User}' | Format-List DisplayName, RecipientTypeDetails, IsInactiveMailbox, LitigationHoldEnabled
Get-MailboxStatistics -Identity '{User}' | Select-Object ItemCount, TotalItemSize
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

Path 5 is for **inactive** mailboxes only. Every command below names the target as
`-InactiveMailbox -Identity '{ExchangeGuid}'` - Microsoft Learn's own form in *Delete an inactive
mailbox* - and never by address. Learn: "the best way to do this is by using its Distinguished Name
or Exchange GUID value. Using one of these values instead of the SMTP address helps prevent
accidentally specifying the wrong mailbox." With a reused address, `Set-Mailbox -Identity '{User}'`
modifies the **live** mailbox - outside anything `DESTROY 1` authorised.

### 5.0 - Resolve the target and check for an address collision

```powershell
# Is there a LIVE mailbox at this address? (expect: nothing)
Get-Mailbox -Identity '{User}' -ErrorAction SilentlyContinue |
    Format-List RecipientTypeDetails, PrimarySmtpAddress, ExchangeGuid, IsInactiveMailbox, WhenCreated

# The INACTIVE mailbox the authorisation is about
Get-Mailbox -InactiveMailboxOnly -Identity '{User}' -ErrorAction SilentlyContinue |
    Format-List RecipientTypeDetails, PrimarySmtpAddress, ExchangeGuid, DistinguishedName, IsInactiveMailbox, WhenSoftDeleted
```

Show the operator both results and say which one is the target, in words: *"The inactive mailbox
is {ExchangeGuid}, deleted {WhenSoftDeleted}. That is the only thing the next commands touch."*

| First command returned | Second command returned | Do |
|---|---|---|
| nothing | one mailbox | Proceed. `{ExchangeGuid}` is the second result's |
| **a live mailbox** | one mailbox | **The address has been reused.** Refuse unless the written authorisation names the `ExchangeGuid` itself. If it names only the address, stop: *"A live mailbox now has this address. I will not proceed on an address alone - the authorisation needs to name the inactive mailbox's ExchangeGuid {ExchangeGuid}."* If it does name it, proceed, and tell the operator the live mailbox ({ActiveExchangeGuid}) will not be touched |
| anything | nothing | Not inactive. Either `SoftDeleted` (Path 4 clock) or already purged. Path 5 does not apply |
| anything | **more than one** | Two inactive mailboxes share the address. Pick by `WhenSoftDeleted` against the authorisation, and name the GUID in the ticket before going on |

### 5.1 - Confirm every hold, not just Litigation Hold

```powershell
Get-Mailbox -InactiveMailboxOnly -Identity '{ExchangeGuid}' |
    Format-List DisplayName, LitigationHoldEnabled, LitigationHoldDate, LitigationHoldDuration, InPlaceHolds,
                ComplianceTagHoldApplied, DelayHoldApplied, DelayReleaseHoldApplied
```

Exchange purges only once the **last** hold is removed. If `InPlaceHolds` still lists `UniH` or
`mbx`, removing Litigation Hold changes nothing - a safety feature, not a fault. **Stop** and say
which hold remains and who owns its release (the case owner; the retention policy admin). Learn adds
one hard stop: "if the inactive mailbox has one or more retention labels configured to retain items
... you can't remove the hold" - `ComplianceTagHoldApplied = True` ends Path 5 here. Do not proceed
until 5.1 shows Litigation Hold as the only hold.

### 5.2 - The gate, then remove the hold

Run **Gate 3** from `references/operator-safety.md`: authorisation reference on file, 5.0 collision
result stated, what is lost, typed `DESTROY 1`. On exactly that:

```powershell
Set-Mailbox -InactiveMailbox -Identity '{ExchangeGuid}' -LitigationHoldEnabled $false
```

That is Learn's verbatim form ("Remove a Litigation hold from an inactive mailbox"). Nothing on this
path ever takes `'{User}'`.

### 5.3 - Clear the delay hold

Learn: "After you remove any other type of hold, Microsoft 365 automatically applies a delay hold so
that content isn't purged immediately ... A delay hold expires automatically after 30 days. To remove
it sooner, run one or both of the following commands, depending on which property is set to True."
Read first, then remove only what is set:

```powershell
Get-Mailbox -InactiveMailbox -Identity '{ExchangeGuid}' | Format-List *Delay*

Set-Mailbox -InactiveMailbox -Identity '{ExchangeGuid}' -RemoveDelayHoldApplied
Set-Mailbox -InactiveMailbox -Identity '{ExchangeGuid}' -RemoveDelayReleaseHoldApplied
```

The `-InactiveMailbox` targeting is supported by the cmdlet itself, not inferred: the `Set-Mailbox`
reference says of **both** switches, "You can use this switch with the GroupMailbox or
InactiveMailbox switch to remove delay holds from group mailboxes or inactive mailboxes", and of
`-InactiveMailbox`: "use the DistinguishedName or ExchangeGuid property values for the Identity
parameter (values guaranteed to be unique)". Learn: "You must be assigned the Legal Hold role in
Exchange Online to use the RemoveDelayHoldApplied or RemoveDelayReleaseHoldApplied parameters" - an
access-denied here is that role, not a wrong identity. And: "Removing the delay hold also recalculates the hold status of the mailbox. If no
other holds remain, the mailbox stops being an inactive mailbox and becomes a soft-deleted mailbox"
- purged 30 days later. Being wrong here is unrecoverable in one direction and merely embarrassing
in the other.

### 5.4 - Confirm the transition and record the outcome

```powershell
# It should now be soft-deleted, no longer inactive, with a retire time set
Get-Mailbox -SoftDeletedMailbox -Identity '{ExchangeGuid}' |
    Format-List Name, PrimarySmtpAddress, ExchangeGuid, LitigationHoldEnabled, InPlaceHolds, IsInactiveMailbox, WasInactiveMailbox, InactiveMailboxRetireTime

# Tenant-wide record of what is still held
Get-Mailbox -ResultSize Unlimited | Where-Object { $_.LitigationHoldEnabled } |
    Select-Object DisplayName, PrimarySmtpAddress, LitigationHoldDate, LitigationHoldDuration, LitigationHoldOwner, RetentionComment |
    Export-Csv "C:\scripts\reports\LitigationHold-AfterRemoval-$(Get-Date -Format yyyyMMddHHmm).csv" -NoTypeInformation -Encoding UTF8
```

**Good**: `IsInactiveMailbox = False`, `WasInactiveMailbox = True`, `InactiveMailboxRetireTime` set
(purge is 30 days after it). If it still reads `IsInactiveMailbox = True`, a hold remains - go back to
5.1; Learn: "Recalculating the hold status doesn't remove a hold." Keep the CSV with the written
authorisation. Ticket note (or closing report): the authorisation reference, the 5.0 collision
result, the gate (who typed it, when), the 5.1 output, the 5.4 output, the CSV path.

---

## Quick reference

| Path | Situation | Key command |
|---|---|---|
| 0 | What state is it in? | `Test-MailboxPreservation.ps1 -Identity '{User}' -AdminUpn '{Admin}' -LogPath 'C:\scripts\logs'` |
| 1 | Held by mistake, still active | `Set-Mailbox -Identity '{User}' -LitigationHoldEnabled $false` |
| 2 | Manager needs to read the mail | `New-MailboxRestoreRequest -SourceMailbox '{ExchangeGuid}' -TargetMailbox X -TargetRootFolder Y -AllowLegacyDNMismatch` |
| 3 | Employee returning, cloud-only, > 30 days deleted | `New-Mailbox -InactiveMailbox '{ExchangeGuid}' -MicrosoftOnlineServicesID '{User}' -Password ...` - **gated**. Synced tenant or < 30 days: Path 2 / Path 4 |
| 4 | Deleted by mistake, < 30 days | `Restore-MgDirectoryDeletedItem -DirectoryObjectId '{DeletedItemId}'` |
| 5 | Retention expired, authorised, **inactive only** | 5.0 collision check, then `Set-Mailbox -InactiveMailbox -Identity '{ExchangeGuid}' -LitigationHoldEnabled $false` - **gated** |
| - | Find the ExchangeGuid | `Get-Mailbox -InactiveMailboxOnly -Identity '{User}' \| FL ExchangeGuid, WhenSoftDeleted` - the address is how you *find* the GUID, and it is ambiguous if reused: confirm `WhenSoftDeleted` matches the person before using the GUID |
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

---
name: exchange-mailbox-restore
description: >
  Walk a non-technical operator, one step at a time, through the Exchange Online Mailbox
  Restore and Hold Removal runbook - triage what state a mailbox is really in (active,
  inactive, soft-deleted, gone) with Test-MailboxPreservation.ps1, then take exactly one of
  five paths: remove a Litigation Hold from an active mailbox, restore an inactive mailbox's
  mail into a shared mailbox with New-MailboxRestoreRequest so a manager can read it,
  recover an inactive mailbox for a returning employee with New-Mailbox -InactiveMailbox,
  undelete an account inside the 30-day window with Restore-MgDirectoryDeletedItem, or
  remove the last hold for authorised permanent destruction. Prints every command for the
  operator to paste; never runs Connect-ExchangeOnline itself. Use this skill whenever the
  user mentions restoring, recovering or undeleting a mailbox or user, "bring back their
  email", "the manager needs to read the ex-employee's mail", "take this user off hold",
  "remove the litigation hold", "release the hold", "we deleted someone by mistake", a
  returning employee or rehire, an inactive or soft-deleted mailbox, New-MailboxRestoreRequest,
  Get-MailboxRestoreRequest, "retention expired - purge it", or the Entra deleted-users
  recycle bin - even if they never say Exchange or PowerShell. Do NOT use it to put a leaver
  on hold, delete an account or run the offboarding cleanup - that is `exchange-mailbox-cleanup`,
  which also owns the shared preflight and safety references this skill reads.
---

# Exchange Mailbox Restore and Hold Removal (operator walkthrough)

Drives the *Mailbox Restore & Hold Removal - Manual Runbook*
(`Powershell/Exchange/Mailbox-Restore-And-Hold-Removal-Runbook.html` in `infrastructure-scripts`):
the reverse of the cleanup. One triage step, then **exactly one** of five paths. Two of the five
destroy something.

## Installs together with `exchange-mailbox-cleanup`

This skill has no `scripts/` and only one reference of its own. Everything else is read from the
sibling by relative path:

| Needed for | Path |
|---|---|
| Connect block, module order, TLS, Graph scope union, roles, reconnect, directories | `../exchange-mailbox-cleanup/references/connect-and-preflight.md` |
| Four hold types, `InPlaceHolds` decoding, the three mailbox states, verdicts | `../exchange-mailbox-cleanup/references/hold-and-mailbox-states.md` |
| The typed-confirmation scripts for Path 3 and Path 5, the licence refusal | `../exchange-mailbox-cleanup/references/operator-safety.md` |
| Preflight and input parsing | `../exchange-mailbox-cleanup/scripts/exo_preflight.ps1`, `parse_user_input.py` |

**Install both or neither.** If `../exchange-mailbox-cleanup/SKILL.md` does not exist beside this
file, stop and tell the user the install is incomplete - do not improvise the missing content.

## Which skill?

| The user wants to | Skill |
|---|---|
| Undo, read back, bring back, or destroy something the cleanup preserved | **this one** |
| Put a leaver on hold, delete the account, reclaim the seat, export from eDiscovery | `exchange-mailbox-cleanup` |

## Restore is not recover

"Restore the mailbox back" is two different operations and the operator will not know which they
mean. Settle it before anything else:

| Word | What it does | The preserved copy | Path |
|---|---|---|---|
| **Restore** | *Copies* mail from the inactive mailbox into another mailbox | Untouched, still on hold | 2 |
| **Recover** | *Reactivates* the inactive mailbox for a returning person | **Ceases to exist**, hold goes with it | 3 |

Pick the wrong one and you have destroyed the preserved copy while thinking you helped a manager
read old mail. Path 2 is the answer to most requests.

## The contract: the skill prints, the operator runs

Identical to `exchange-mailbox-cleanup`. Print exact commands for the operator's **blue "Windows
PowerShell" window** (5.1, `PSEdition = Desktop` - the first thing printed is
`$PSVersionTable.PSEdition`, and on `Core` the operator is told to close it and open the blue icon
whose title bar says Windows PowerShell). Wait for the output or the file, read `*.csv` back
directly and `*.log` through `../exchange-mailbox-cleanup/scripts/read_log.py` (5.1 writes them in
cp1252), then advance. Never call `Connect-*`, `Set-Mailbox`, `New-Mailbox`,
`New-MailboxRestoreRequest` or `Restore-MgDirectoryDeletedItem` from a tool call. Never print `>`
or `Out-File`; every export is `Export-Csv ... -NoTypeInformation -Encoding UTF8`. Every printed
command stays in the 5.1 subset (no ternary, `??`, `&&`/`||`, `-Parallel`, `-AsHashtable`).

## Resolving paths

```powershell
$SkillDir   = "$env:USERPROFILE\.claude\skills\exchange-mailbox-restore"
$SkillDir   = "C:\repos\personal\useful-claude-add-ons\skills\exchange-mailbox-restore"
$CleanupDir = Join-Path (Split-Path $SkillDir) 'exchange-mailbox-cleanup'
$Repo       = "C:\repos\solomon\infrastructure-scripts\Powershell\Exchange"
```

## How to run the walkthrough

Read `references/runbook-paths.md` and follow it. The shape is fixed:

1. **Setup** - ticket, preflight, connect (steps S1-S6). Reuses the cleanup's Steps 3-10 verbatim.
2. **Step 0 - triage.** Run `Test-MailboxPreservation.ps1` once. `MailboxState` decides the path.
   Do not let the requester's wording decide it; a manager who says "restore his mailbox" about a
   *soft-deleted* mailbox is on Path 4 with a clock running, whatever they said.
3. **Ask what the requester actually wants**, then map state + want to **one** path. Say which and
   why in two sentences before the first command of that path.
4. **Work that path only**, one step per turn, "good looks like" before each command, artifact read
   back after.

Ask for one thing at a time. Restate "Path 2, step 2.3 of 2.6" every turn.

### Triage table

| `MailboxState` | Requester wants | Path |
|---|---|---|
| `Active` | "Held by mistake / the person is staying" | **1** - remove the hold |
| `Inactive` | "A manager needs to read the mail" | **2** - restore a copy into a shared mailbox |
| `Inactive` | "They are coming back and want their mailbox" | **3** - recover (destroys the preserved copy) |
| `SoftDeleted` | Anything | **4** - undelete the account, 30-day window, hurry |
| `Inactive` or `Active` | "Retention expired, destroy it - authorised in writing" | **5** - remove the last hold |
| `NotFound` | Anything | No path. Read `Detail` for near-matches, then escalate |

### Preflight and input

Same helpers as the cleanup, same rules - `-Check` is read-only; `-Install` runs after one
confirmation and installs under the user profile only (`-Scope CurrentUser`, never elevated),
verifying what landed; `-Roles` runs in the operator's connected window:

```powershell
powershell.exe -NoProfile -File "$CleanupDir\scripts\exo_preflight.ps1" -Check
powershell.exe -NoProfile -File "$CleanupDir\scripts\exo_preflight.ps1" -Roles -AdminUpn admin@contoso.com
python "$CleanupDir\scripts\parse_user_input.py" "first.last@contoso.com" --json
```

Restore work is almost always one identity. If a CSV arrives, parse it, then triage **each**
identity separately - a list can contain an `Active`, an `Inactive` and a `SoftDeleted` mailbox and
they are on three different paths.

Pass `-LogPath 'C:\scripts\logs'` on every `Test-MailboxPreservation.ps1` call and print the
reconnect block after it - the script disconnects the operator's session on exit.

## Safety rails

The full scripts are in the shared `operator-safety.md`. What applies here:

- **Path 3 (recover) is gated by typing `RECOVER 1`** after being told the preserved copy ceases to
  exist and that Path 2 is still available. Never reachable from a default.
- **Path 5 (destruction) is gated by typing `DESTROY 1`**, only after the written authorisation
  reference is in the ticket and the four-way hold check shows Litigation Hold is the *last* hold.
  If `InPlaceHolds` still has a `UniH` or `mbx` entry, removing Litigation Hold changes nothing,
  and the skill says so instead of printing a command.
- **Identify an inactive mailbox by `ExchangeGuid`**, never by SMTP address - an inactive and a live
  mailbox can share one, and the address silently resolves to the wrong mailbox.
- **Licence removal is a refusal, not a step.** Path 1 step 1.4 is a *read* of
  `Get-MgUserLicenseDetail` and a sentence about normal licensing - after and only after step 1.3
  shows no hold of any kind remains.
- **`-AllowLegacyDNMismatch` and `-TargetRootFolder` are mandatory** on every
  `New-MailboxRestoreRequest` between different people. Without the first, the request fails
  outright; without the second, the leaver's mail merges into the target's Inbox.
- **`-AutoMapping:$false`** on the `Add-MailboxPermission` grant, or a large archive automaps into
  the manager's Outlook and slows it noticeably.
- **Path 4 has a clock.** Print `DaysLeft` (Path 4 step 4.1) in the first reply and do not spend a
  turn on anything else until the operator has seen it.
- **SDP ticket first.** Same as the cleanup: ask once, never create without confirmation,
  `ticketctl.py redact-check --emit` before every `sdp_*` write.
- **`-ResultSize Unlimited`** on every `Get-Mailbox -InactiveMailboxOnly` / `-SoftDeletedMailbox`.
- **Verify `-RemoveDelayHoldApplied` / `-RemoveDelayReleaseHoldApplied` against Microsoft Learn**
  in the session before printing them (Path 5 step 5.3). Hold behaviour changes.

## Reference map

| Read | When |
|---|---|
| `references/runbook-paths.md` | Every run. Setup, triage, and the five paths with commands and "good looks like" |
| `../exchange-mailbox-cleanup/references/connect-and-preflight.md` | Setup, any `Connect-*` failure, "cmdlet not found", reconnect after a script |
| `../exchange-mailbox-cleanup/references/hold-and-mailbox-states.md` | Step 0, Path 1 step 1.1, Path 5 step 5.1 - interpreting hold columns and states |
| `../exchange-mailbox-cleanup/references/operator-safety.md` | Before the first command of Path 3 or Path 5, and whenever a licence removal is requested |

## Report back to the operator

At the end of the path:

1. **One line** - "Restore complete: 4,812 items copied into `archive-first.last`; inactive mailbox
   still on hold."
2. **A table** - source `ExchangeGuid`, target, `Status`, `ItemsTransferred`, hold state after.
3. **File paths** - the `MailboxPreservation-*.csv` before and after, and any export in
   `C:\scripts\reports`.
4. **What was not verified** - say it. On Path 4 in particular, "the mailbox reattached" is not
   verifiable for some hours after re-licensing.

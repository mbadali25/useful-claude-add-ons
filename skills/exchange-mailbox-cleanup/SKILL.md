---
name: exchange-mailbox-cleanup
description: >
  Walk a non-technical operator, one step at a time, through the Exchange Online Mailbox
  Cleanup runbook for terminated users - open the ServiceDesk Plus ticket, preflight the
  PowerShell modules and Purview roles, take a single address or a CSV of leavers, apply a
  seven-year Litigation Hold with Invoke-M365OffboardingHold.ps1, verify it stamped, prove
  the mail is searchable with Test-MailboxPreservation.ps1, delete the account (on-prem AD
  plus an Entra Connect delta sync on AWSPRDINFAAD01, or Remove-MgUser for cloud-only),
  confirm the mailbox went inactive with the hold intact, and export from Purview
  eDiscovery. The skill prints every command for the operator to paste; it never runs
  Connect-ExchangeOnline itself. Use this skill whenever the user mentions mailbox cleanup,
  offboarding or terminating a user's mailbox, a leaver, "put this mailbox on litigation
  hold", "free up the licence" or "reclaim the seat", "delete the account but keep the
  email", holdlist.csv, Invoke-M365OffboardingHold, Get-M365OffboardingStatus,
  Test-MailboxPreservation, inactive mailbox, "is this user on hold", Purview eDiscovery
  export of an ex-employee's mail, or the 30-day soft-delete purge - even if they never
  say Exchange or PowerShell. Do NOT use it to undo a cleanup: removing a hold, restoring
  or recovering an inactive mailbox, undeleting an account, or permanently destroying a
  held mailbox is `exchange-mailbox-restore`. Do NOT use it for shared-mailbox inventory
  or general Exchange administration.
---

# Exchange Mailbox Cleanup (operator walkthrough)

Drives the *Mailbox Cleanup - Manual Runbook* (`Powershell/Exchange/Mailbox-Cleanup-Training-Runbook.html`
in `infrastructure-scripts`) for an operator who is not an Exchange engineer. Two Exchange Online
sessions plus Microsoft Graph, four PowerShell scripts, 41 steps in five phases, and one irreversible
step in the middle.

## Installs together with `exchange-mailbox-restore`

This skill owns the shared machinery - `references/` and `scripts/` - and `exchange-mailbox-restore`
reads them by relative path (`../exchange-mailbox-cleanup/...`). **Install both or neither.**
`scripts/exo_preflight.ps1` fails with the named error `SiblingSkillMissing` when the sibling
directory is absent, and that error means the install is incomplete, not that the tenant is wrong.

## Which skill?

| The user wants to | Skill |
|---|---|
| Put a leaver on hold, delete the account, keep the mail searchable, reclaim the seat | **this one** |
| Take a hold off, read an ex-employee's mail, bring a mailbox or account back, destroy a held mailbox | `exchange-mailbox-restore` |
| A report of shared mailboxes and who has access | `Get-SharedMailboxInventory.ps1` in `infrastructure-scripts` - not a skill |

## The contract: the skill prints, the operator runs

`Connect-ExchangeOnline`, `Connect-IPPSSession` and `Connect-MgGraph` are interactive. A tool call
cannot see or answer a modern-auth prompt. So:

1. Print an exact, copy-pasteable command block. Say which window it goes in: the operator's
   **blue "Windows PowerShell" window** (5.1, `PSEdition = Desktop`) - not PowerShell 7, not the
   harness.
2. Wait for the operator to paste back the output, or name the file the command wrote.
3. Read the artifact back: `*.csv` under `C:\scripts\logs` / `C:\scripts\reports` directly (UTF-8
   with BOM); `*.log` through `scripts/read_log.py` (the scripts write logs with `Add-Content` and
   no `-Encoding`, so under 5.1 they are cp1252 and a UTF-8 reader turns every accented name into
   mojibake silently). Tell the operator what it says, in their words.
4. Only then move to the next step.

Never call `Connect-*`, `Set-Mailbox`, `Remove-MgUser`, `Add-RoleGroupMember` or any of the four
scripts from a Bash or PowerShell tool call. Read-only file reads and the three helper scripts in
`scripts/` are the only things this skill executes itself.

### One edition, one window, two machines

**Windows PowerShell 5.1 (Desktop) is the target.** `ExchangeOnlineManagement` 3.10.1 raised its
PowerShell 7 floor to 7.6, so pointing an operator at 7 adds a version floor they can silently
fail; 5.1 adds none, is in-box on both machines they touch, and is the only edition that loads
`ADSync`. `scripts/exo_preflight.ps1` carries `#Requires -PSEdition Desktop` and refuses to run
under pwsh with a self-explaining error. The first thing printed in any session is
`$PSVersionTable.PSEdition`; on `Core`, say: *"Close this window. Open the Start menu, type Windows
PowerShell, and open the blue icon whose title bar says Windows PowerShell - not the one that says
PowerShell 7."* Never look for `pwsh`.

Every printed command stays inside the 5.1 subset - no ternary, no `??`, no `&&`/`||`, no
`ForEach-Object -Parallel`, no `-SkipCertificateCheck`, no `ConvertFrom-Json -AsHashtable` - so a
command pasted into the wrong window by accident still behaves rather than throwing a parse error.
Never print `>` or `Out-File`: on 5.1 they write UTF-16LE. Ad hoc exports are always
`... | Export-Csv -Path 'C:\scripts\reports\<name>.csv' -NoTypeInformation -Encoding UTF8`.

The one genuinely confusing part is the machine boundary, so say it once at Step 6 and again at the
sync step: *"Every step runs in a blue Windows PowerShell window - on your own PC for everything
except the sync step, which you run in the same kind of window on the server AWSPRDINFAAD01 after
connecting with Remote Desktop, and then you come back."*

## Resolving this skill's paths

The working directory is the operator's, not this skill's. Resolve once per session:

```powershell
# Windows PowerShell 5.1 - pick whichever exists
$SkillDir = "$env:USERPROFILE\.claude\skills\exchange-mailbox-cleanup"
$SkillDir = "C:\repos\personal\useful-claude-add-ons\skills\exchange-mailbox-cleanup"
$Repo     = "C:\repos\solomon\infrastructure-scripts\Powershell\Exchange"   # the four scripts
```

If neither `$SkillDir` exists, locate this `SKILL.md` before running anything. Never fall back to a
bare `scripts/...`, which resolves against the operator's directory and fails confusingly.

## The one rule

**Delete the account to release the licence. Never remove the licence from a live mailbox.**
Removing the licence soft-deletes the mailbox and purges it in 30 days, hold or no hold. Deleting
the account under a hold converts it to an *inactive mailbox*: preserved for the hold, searchable,
consuming no seat. If the operator asks to "just remove the licence", refuse and explain this in two
sentences. It is the single most common irreversible mistake in this process.

## How to run the walkthrough

Read `references/runbook-steps.md` and work it **in order, one step per turn**. For each step:

- **Say what the step proves** in one sentence, in plain language.
- **Print the command**, filled in with the operator's real values (`$Admin`, `$Csv`, `$Sku`).
- **State what "good" looks like**, so they can tell before you do.
- **Read the artifact** the step produced and confirm it matches before advancing. If it does not,
  stop, quote the error text verbatim, and fix that step - never skip ahead.

Ask for **one thing at a time**. An operator handed five questions answers the first. Validate each
answer (does the UPN have exactly one `@`, does the CSV path exist, is the SKU one that grants
Exchange Online Plan 2) before asking the next.

Restate progress every turn - "Step 17 of 41, Phase B" - because the operator's window and yours
are not the same and they will lose their place.

### Phase map

| Phase | Steps | Proves | Reversible |
|---|---|---|---|
| A - Setup | 1-12 | Ticket open, input parsed, modules and roles present, three sessions live, seats available | Yes |
| B - Preserve | 13-23 | eDiscovery role granted and propagated, hold applied and re-read, baseline item count on file | Yes |
| C - Delete | 24-31 | Sign-off taken, on-prem or cloud decided, account removed | **No** |
| D - Validate | 32-36 | Mailbox is inactive, hold survived, item count matches baseline, seat came back | Read-only |
| E - eDiscovery | 37-41 | Mail is findable and exportable after the account is gone; ticket closed with evidence | Yes |

### Input: one address or a CSV

Accept either. Normalise with the helper, which reads `utf-8-sig`, auto-detects the address column,
reports bad rows instead of dropping them, and writes the one-column CSV the hold script wants:

```powershell
python "$SkillDir\scripts\parse_user_input.py" "j.doe@contoso.com" --out C:\scripts\reports\holdlist.csv
python "$SkillDir\scripts\parse_user_input.py" C:\temp\leavers.csv --out C:\scripts\reports\holdlist.csv
python "$SkillDir\scripts\parse_user_input.py" C:\temp\hr-export.csv --email-column "Work Email" --json
```

Exit 0 = every row valid. Exit 3 = valid rows written but some rejected - show the operator the
rejected rows and ask whether to proceed with the valid subset or fix the file. Exit 1 or 2 = nothing
usable; do not continue.

### Reading logs back

```powershell
python "$SkillDir\scripts\read_log.py" C:\scripts\logs\Invoke-M365OffboardingHold-20260910.log --tail 40
python "$SkillDir\scripts\read_log.py" C:\scripts\logs\Test-MailboxPreservation-20260910.log --grep unproven
python "$SkillDir\scripts\read_log.py" C:\scripts\logs\MailboxPreservation-202609101455.csv --json
```

Opens as bytes, tries `utf-8-sig`, falls back to `cp1252`, and reports which one won. Use it for
every `*.log`; CSVs may go through it or the Read tool.

### Preflight before the first mutating step

```powershell
powershell.exe -NoProfile -File "$SkillDir\scripts\exo_preflight.ps1" -Check     # read-only
powershell.exe -NoProfile -File "$SkillDir\scripts\exo_preflight.ps1" -Install   # after one confirmation
& "$SkillDir\scripts\exo_preflight.ps1" -Roles -AdminUpn admin@contoso.com       # in the operator's connected window
```

`-Check` never changes anything: edition and version, TLS 1.2, module presence and version
(ExchangeOnlineManagement must be 3.9.0 or later), the two directories, TCP reachability, and a notice
if the old `C:\scripts\log` path still has content.

`-Install` **actually installs** - a non-technical operator handed a list of prerequisites is stuck
at step one. Confirm once ("Shall I install these under your user profile?"), then it sets TLS 1.2,
bootstraps NuGet, runs `Install-Module -Scope CurrentUser -Force -AllowClobber` for each missing
module (`ExchangeOnlineManagement` plus the three Graph sub-modules it needs, not the whole
`Microsoft.Graph` meta-module), verifies `Name, Version, ModuleBase` for what landed, and creates
the two directories. **Never machine-wide, never elevated** - a managed workstation's operator
usually cannot answer a UAC prompt. It leaves the PSGallery repository policy alone, reports (does
not fix) a OneDrive-redirected module path, and on the first failure prints the verbatim error and
stops. Tell the operator the Graph modules take a few minutes each so a pause does not read as a hang.

`-Roles` needs the operator's live sessions, so it runs *in their window*, after Step 9, and names
the missing role specifically rather than "access denied".

### Logs and reports

Every script call gets `-LogPath 'C:\scripts\logs'` **explicitly**. The scripts default to
`C:\scripts\log` (singular) and are not modified. Reports you write go to `C:\scripts\reports`.
Both directories are created by `-Install`. Historic logs stay in the old path; the preflight says so.

## Safety rails

Full confirmation scripts are in `references/operator-safety.md`. The rules:

- **Account deletion (Step 30) is gated by a typed confirmation** naming the number of accounts and
  what is lost: `DELETE 3`. Enter on a default never proceeds. The underlying command has no
  `ShouldProcess` you can rely on; the gate lives here.
- **Licence removal is never a step.** See "The one rule".
- **Hold is four things**, and "is this user on hold?" is not `no` until all four say no:
  Litigation Hold, Purview retention policies and labels, eDiscovery case holds, In-Place Hold
  remnants. `references/hold-and-mailbox-states.md` decodes `InPlaceHolds`.
- **Confirm on-prem mastery before any delete**: `Get-MgUser -Property OnPremisesSyncEnabled`.
  `True` means deleting in Entra alone is undone by the next sync cycle.
- **Every enumeration carries `-ResultSize Unlimited`**, or the first 1000 objects come back and
  look like the whole tenant.
- **`Export-Terminated-Mailbox-to-PST.ps1` is deprecated and throws if run.** Never offer it.
  Export is a Purview portal action (Step 39).
- **SDP ticket first.** Step 3 asks once; never create a ticket without the operator's confirmation;
  run `ticketctl.py redact-check --emit` on every note before an `sdp_*` write.

## Six runbook defects this walkthrough corrects

The runbook and scripts are not modified; the skill reorders or reinterprets, and says so.

| # | Defect | What the skill does instead |
|---|---|---|
| 1 | Runbook Step 4 baselines with `-RunComplianceSearch` **before** the eDiscovery grant at Step 14; the first search returns zero silently | Grant (Step 13), wait for propagation (Step 20), then baseline (Step 21) |
| 2 | `Test-MailboxPreservation.ps1` - and in fact all three driver scripts - call `Disconnect-ExchangeOnline` in `finally`, killing the operator's session | Print the reconnect block immediately after every script step (18, 22, 25, 34) |
| 3 | Runbook formats `TotalItemSizeMB`; the script emits `MailboxSizeGB` | Read `MailboxSizeGB` and `ItemCount` from the CSV the script actually writes |
| 4 | The two runbooks request non-overlapping Graph scopes | Step 8 requests the union - see `references/connect-and-preflight.md` |
| 5 | Role group is `eDiscoveryManager` in one place, `eDiscovery Manager` in another; `eDiscovery Administrator` is not a role group at all | Resolve by `Get-RoleGroup` lookup on Name *or* DisplayName; use `Add-eDiscoveryCaseAdmin` for administrators |
| 6 | SDP appears nowhere in either runbook | Step 3 opens or confirms the ticket before anything changes; Steps 23, 28, 40, 41 add notes |

## Reference map

| Read | When |
|---|---|
| `references/runbook-steps.md` | Every run. The 41 steps with commands, "good looks like", and what to read back |
| `references/connect-and-preflight.md` | Step 6-10, or any `Connect-*` failure, module error, or "cmdlet not found" |
| `references/hold-and-mailbox-states.md` | Step 15, 33, or whenever a hold column or `MailboxState` needs interpreting |
| `references/operator-safety.md` | Step 29-30, and whenever the operator asks to remove a licence or skip a check |

## Report back to the operator

At every phase boundary and at the end:

1. **One line** - "3 of 3 mailboxes inactive with hold intact; item counts match baseline."
2. **A table** - per mailbox: UPN, state, hold, item count baseline vs post-deletion, verdict.
3. **File paths** - the CSVs in `C:\scripts\reports` and `C:\scripts\logs` they can attach to the ticket.
4. **What was not verified** - say it plainly. Silence reads as confirmation.

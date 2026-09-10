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

Drives the *Mailbox Cleanup - Manual Runbook* (upstream: `Powershell/Exchange/Mailbox-Cleanup-Training-Runbook.html`
in `infrastructure-scripts`) for an operator who is not an Exchange engineer. Two Exchange Online
sessions plus Microsoft Graph, six PowerShell scripts vendored under `scripts/vendored/` (four the
walkthrough drives, two for the scoping pass), 41 steps in five phases, and one irreversible step in
the middle. Self-contained: no repository clone, no Python, nothing but Windows PowerShell 5.1.

## Standalone

This skill depends on nothing outside its own folder - no repo clone, no Python, no other skill.
`exchange-mailbox-restore` is a separate, equally standalone skill for the reverse operations; it
carries its own copies of `references/connect-and-preflight.md`, `hold-and-mailbox-states.md`,
`operator-safety.md`, the three helper scripts and the driver script it uses. The marketplace
installs each plugin into its own versioned cache, so a `../sibling` path never resolves even when
both are installed; duplication is the accepted cost. When one copy of a shared file changes, change
the other.

## Which skill?

| The user wants to | Skill |
|---|---|
| Put a leaver on hold, delete the account, keep the mail searchable, reclaim the seat | **this one** |
| Take a hold off, read an ex-employee's mail, bring a mailbox or account back, destroy a held mailbox | `exchange-mailbox-restore` |
| A report of shared mailboxes and who has access | `scripts\vendored\Get-SharedMailboxInventory.ps1` - bundled, but not walked by either skill |

## The contract: the skill prints, the operator runs

`Connect-ExchangeOnline`, `Connect-IPPSSession` and `Connect-MgGraph` are interactive. A tool call
cannot see or answer a modern-auth prompt. So:

1. Print an exact, copy-pasteable command block. Say which window it goes in: the operator's
   **blue "Windows PowerShell" window** (5.1, `PSEdition = Desktop`) - not PowerShell 7, not the
   harness.
2. Wait for the operator to paste back the output, or name the file the command wrote.
3. Read the artifact back: `*.csv` under `C:\scripts\logs` / `C:\scripts\reports` directly (UTF-8
   with BOM); `*.log` through `scripts/Read-ScriptLog.ps1` (the scripts write logs with `Add-Content`
   and no `-Encoding`, so under 5.1 they are cp1252 and a UTF-8 reader turns every accented name
   into mojibake silently). Tell the operator what it says, in their words.
4. Only then move to the next step.

Never call `Connect-*`, `Set-Mailbox`, `Remove-MgUser`, `Add-RoleGroupMember` or any of the four
scripts from a Bash or PowerShell tool call. Read-only file reads and the helper scripts in
`scripts/` (`exo_preflight.ps1`, `Resolve-OperatorInput.ps1`, `Read-ScriptLog.ps1` - all Windows
PowerShell 5.1, no Python) are the only things this skill executes itself. `parse_user_input.py` and
`read_log.py` remain as reference implementations; nothing depends on them.

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
`... | Export-Csv -Path 'C:\scripts\reports\{Name}.csv' -NoTypeInformation -Encoding UTF8`.

The one genuinely confusing part is the machine boundary, so say it once at Step 6 and again at the
sync step: *"Every step runs in a blue Windows PowerShell window - on your own PC for everything
except the sync step, which you run in the same kind of window on the server AWSPRDINFAAD01 after
connecting with Remote Desktop, and then you come back."*

## Resolving this skill's paths - all-in-one, no repo clone

Everything the walkthrough runs ships inside this skill. The six driver scripts are vendored
byte-for-byte in `scripts/vendored/` (provenance, upstream commit and SHA-256 per file in
`scripts/vendored/PROVENANCE.md`); `exo_preflight.ps1 -Check` fails with the named error
`DriverScriptMissing` if any is absent and reports `DriverScriptModified` if a hash drifts. The
operator needs **no clone of `infrastructure-scripts`**, and no printed command may contain a path to
one.

**Zero setup for the operator.** The skill resolves its own location and prints every command
already filled in. Nothing is assigned to a variable, nothing is `cd`'d into, nothing is edited before
pasting. Three values are substituted for braces before a command is printed:

| Brace | Filled with | How the skill knows |
|---|---|---|
| `{SkillDir}` | The folder holding this `SKILL.md` | Its own location - personal install `$env:USERPROFILE\.claude\skills\exchange-mailbox-cleanup`, or the project `.claude\skills\` folder. Locate it; never guess |
| `{Repo}` | `{SkillDir}\scripts\vendored` | Computed from the above |
| `{Admin}` | The operator's own admin UPN | The **one** question the skill asks at Step 6. Never print a sample address for them to replace |

Everything else - `C:\scripts\reports\holdlist.csv`, `C:\scripts\logs`, `SPE_E3` - is a fixed literal
in the printed command. Later braces (`{User}`, `{ExchangeGuid}`, `{DeletedItemId}`) are read from an
earlier step's artifact. The operator never sees a brace. Invocations are fully qualified
(`& "{Repo}\Invoke-M365OffboardingHold.ps1" ...`), so the operator's current directory is irrelevant.

## The one rule

**Delete the account to release the licence. Never remove the licence from a live mailbox.**
Removing the licence soft-deletes the mailbox and purges it in 30 days, hold or no hold. Deleting
the account under a hold converts it to an *inactive mailbox*: preserved for the hold, searchable,
consuming no seat. If the operator asks to "just remove the licence", refuse and explain this in two
sentences. It is the single most common irreversible mistake in this process.

## How to run the walkthrough

Read `references/runbook-steps.md` and work it **in order, one step per turn**. For each step:

- **Say what the step proves** in one sentence, in plain language.
- **Print the command already filled in** - `{Admin}`, `{Repo}`, `{User}` and every other brace replaced with the real value. No variables to set, no directory to change into, no sample value to find and replace.
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
powershell.exe -NoProfile -File "{SkillDir}\scripts\Resolve-OperatorInput.ps1" -Value "{User}" -OutPath 'C:\scripts\reports\holdlist.csv'
powershell.exe -NoProfile -File "{SkillDir}\scripts\Resolve-OperatorInput.ps1" -Value C:\temp\leavers.csv -OutPath 'C:\scripts\reports\holdlist.csv'
powershell.exe -NoProfile -File "{SkillDir}\scripts\Resolve-OperatorInput.ps1" -Value C:\temp\hr-export.csv -EmailColumn "Work Email" -AsJson
```

Exit 0 = every row valid. Exit 3 = valid rows written but some rejected - show the operator the
rejected rows and ask whether to proceed with the valid subset or fix the file. Exit 1 or 2 = nothing
usable; do not continue.

### Reading logs back

```powershell
powershell.exe -NoProfile -File "{SkillDir}\scripts\Read-ScriptLog.ps1" -Path C:\scripts\logs\Invoke-M365OffboardingHold-20260910.log -Tail 40
powershell.exe -NoProfile -File "{SkillDir}\scripts\Read-ScriptLog.ps1" -Path C:\scripts\logs\Test-MailboxPreservation-20260910.log -Grep unproven
powershell.exe -NoProfile -File "{SkillDir}\scripts\Read-ScriptLog.ps1" -Path C:\scripts\logs\MailboxPreservation-202609101455.csv -AsJson
```

Reads bytes, tries UTF-16 BOM, strict UTF-8, BOM-less UTF-16, then `cp1252`, and reports which one
won. Use it for every `*.log`; CSVs may go through it or the Read tool.

### Preflight before the first mutating step

```powershell
powershell.exe -NoProfile -File "{SkillDir}\scripts\exo_preflight.ps1" -Check     # read-only
powershell.exe -NoProfile -File "{SkillDir}\scripts\exo_preflight.ps1" -Install   # after one confirmation
& "{SkillDir}\scripts\exo_preflight.ps1" -Roles -AdminUpn '{Admin}'       # in the operator's connected window
```

`-Check` never changes anything: bundled driver scripts and their hashes, ticketing availability
(advisory), edition, TLS 1.2, module presence and version - `ExchangeOnlineManagement` 3.9.0 or later,
and the **four** Graph sub-modules (`Authentication`, `Users`, `Users.Actions`,
`Identity.DirectoryManagement`) at **exactly 2.39.0**, the version the driver scripts import with
`-RequiredVersion`; a newer-only install is a `FAIL` - the two directories, TCP reachability, and a
notice if the old `C:\scripts\log` path still has content.

`-Install` **actually installs** - a non-technical operator handed a list of prerequisites is stuck
at step one. Confirm once ("Shall I install these under your user profile?"), then it sets TLS 1.2,
bootstraps NuGet, runs `Install-Module -Scope CurrentUser -Force -AllowClobber` for each missing
module (`ExchangeOnlineManagement`, plus the four Graph sub-modules at `-RequiredVersion 2.39.0` -
never the whole `Microsoft.Graph` meta-module), verifies `Name, Version, ModuleBase` for what landed,
and creates the two directories. **It runs before any login** (Step 5, ahead of Steps 7-9): if a
Graph version change means a fresh window, the preflight says so in the operator's words and it costs
nothing, because nothing has been signed into yet. Done later by the driver it costs three logins. **Never machine-wide, never elevated** - a managed workstation's operator
usually cannot answer a UAC prompt. It leaves the PSGallery repository policy alone, reports (does
not fix) a OneDrive-redirected module path, and on the first failure prints the verbatim error and
stops. Tell the operator the Graph modules take a few minutes each so a pause does not read as a hang.

`-Roles` needs the operator's live sessions, so it runs *in their window*, after Step 9, and names
the missing role specifically rather than "access denied".

### Logs and reports

Every script call gets `-LogPath 'C:\scripts\logs'` **explicitly**. The scripts default to
`C:\scripts\log` (singular) and are not modified. Reports you write go to `C:\scripts\reports`.
Both directories are created by `-Install`. Historic logs stay in the old path; the preflight says so.

## Two bundled scripts this walkthrough never calls: the scoping pass

`scripts\vendored\Get-SharedMailboxInventory.ps1` and `scripts\vendored\Split-MailboxCleanupReports.ps1`
are bundled on purpose and **no step in the 41 calls them**. They belong to the *scoping* track that
runs before any of this: deciding **who** the cleanup candidates are. The inventory writes two CSVs
(`Mailbox-Inventory-{timestamp}.csv`, `Mailbox-Access-{timestamp}.csv`: every mailbox by type, its
account state, and every FullAccess / SendAs / SendOnBehalf delegate); the splitter divides them into
five audience reports plus a delegate contact list. Someone reviews those and hands this skill a
list. If the operator arrives with a `holdlist.csv`, the scoping pass already happened and these two
are not needed.

For the person who has to produce that list, the pair runs like this (same connect rules, same
reconnect-after; pass `-OutputPath` explicitly or the inventory writes into the skill's own folder):

```powershell
& "{Repo}\Get-SharedMailboxInventory.ps1" -AuthMode Interactive -AdminUpn '{Admin}' -OutputPath 'C:\scripts\reports\cleanup-project'
& "{Repo}\Split-MailboxCleanupReports.ps1" -InventoryCsv 'C:\scripts\reports\cleanup-project\Mailbox-Inventory-{timestamp}.csv' -AccessCsv 'C:\scripts\reports\cleanup-project\Mailbox-Access-{timestamp}.csv' -OutputPath 'C:\scripts\reports\cleanup-project' -WhatIf
```

Drop `-WhatIf` once the file list looks right. Room and equipment mailboxes appear in the inventory
and are **never** cleanup candidates - idle is their normal state; `RecipientTypeDetails` is the
column to filter on. The inventory's own traps (`LastUserActionTime` is empty on every shared
mailbox; a throttled permissions call is not an empty result) are documented in its comment-based
help - read it before interpreting the CSVs.

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
- **SDP ticket first, but advisory.** Step 3 asks once; never create a ticket without the
  operator's confirmation; run `ticketctl.py redact-check --emit` on every note before an `sdp_*`
  write. If the `infra-work-ticketing` skill is not loaded, or the SDP connector is unavailable
  (preflight `TicketingUnavailable`), say so once and continue - the record goes in the closing report. The
  approver's name at Step 28 is still required; where it is written is not.

## Six runbook defects this walkthrough corrects

The runbook and scripts are not modified; the skill reorders or reinterprets, and says so.

| # | Defect | What the skill does instead |
|---|---|---|
| 1 | Runbook Step 4 baselines with `-RunComplianceSearch` **before** the eDiscovery grant at Step 14; the first search returns zero silently | Grant (Step 13), wait for propagation (Step 20), then baseline (Step 21) |
| 2 | `Test-MailboxPreservation.ps1` - and in fact all three driver scripts - call `Disconnect-ExchangeOnline` in `finally`, and two of them `Disconnect-MgGraph` too, killing all of the operator's sessions | Print the reconnect block - EXO, IPPS **and** `Connect-MgGraph` - immediately after every script step (18, 22, 25, 34) |
| 3 | Runbook formats `TotalItemSizeMB`; the script emits `MailboxSizeGB` | Read `MailboxSizeGB` and `ItemCount` from the CSV the script actually writes |
| 4 | The two runbooks request non-overlapping Graph scopes | Step 8 requests the union - see `references/connect-and-preflight.md` |
| 4b | Neither runbook names `Microsoft.Graph.Users.Actions` or the exact Graph pin (`2.39.0`) the drivers import with `-RequiredVersion`; the driver installs it mid-run and throws "close this session", after the three logins | Preflight pins all four Graph sub-modules to 2.39.0 and installs **before** any login (Step 5); the operator's own imports carry `-RequiredVersion 2.39.0` |
| 5 | Role group is `eDiscoveryManager` in one place, `eDiscovery Manager` in another; `eDiscovery Administrator` is not a role group at all | Resolve by `Get-RoleGroup` lookup on Name *or* DisplayName; use `Add-eDiscoveryCaseAdmin` for administrators |
| 6 | SDP appears nowhere in either runbook | Step 3 opens or confirms the ticket before anything changes; Steps 23, 28, 40, 41 add notes |

## Reference map

| Read | When |
|---|---|
| `docs/` | The operator guide (PDF) ships here, inside the skill. Point the operator at it; nothing external |
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

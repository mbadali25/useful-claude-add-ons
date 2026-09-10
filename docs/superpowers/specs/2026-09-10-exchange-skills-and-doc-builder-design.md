# Exchange operator skills, and a merged document builder

Date: 2026-09-10
Status: awaiting review
Repos touched: `useful-claude-add-ons` (all new code), `infrastructure-scripts` (read-only source)

## What this builds

Four registered skills, from three implementations:

| Skill | Kind | Purpose |
|---|---|---|
| `exchange-mailbox-cleanup` | new | Walks a non-technical operator through the Mailbox Cleanup runbook. Owns the shared preflight, CSV and safety machinery. |
| `exchange-mailbox-restore` | new | Walks the same operator through the Restore & Hold Removal runbook. Consumes the shared machinery above. |
| `doc-builder` | merged | `report-builder` + `solomon-sop-maker`, generic and unbranded. Owns every script and reference. |
| `solomon-doc-builder` | brand pack | Thin skill: Solomon palette, template and footer. No logic of its own. |

## Decisions already taken

Settled by the user on 2026-09-10:

1. **Two Exchange skills, not one and not three.** They map 1:1 to the two runbooks, which keeps each trigger description sharp.
2. **The skill prints commands; the operator runs them.** No interactive login is ever driven from a tool call.
3. **One merged document skill with two rendering paths**, generic by default, brand as a swappable pack.
4. **Generic is the source; Solomon is a brand pack.** One codebase, no drift.

---

## Part 1 — The two Exchange skills

### PowerShell edition: 5.1, in the 7.6-safe subset

Settled 2026-09-10 by `powershell-5.1-expert` and `powershell-7-expert` arguing opposite sides. **Both concluded 5.1**, and the strongest single fact came from the advocate arguing against it.

**`ExchangeOnlineManagement` 3.10.1 raised its PowerShell 7 floor to 7.6.** Its manifest states verbatim: *"Starting with this version of the module, the minimum required version of PowerShell 7 is now 7.6. Windows PowerShell 5.1 is not affected."* Pointing a non-technical operator at PowerShell 7 therefore adds a version floor they can silently fail — and this repo's own CI runs `mcr.microsoft.com/powershell:7.4-ubuntu-22.04`, already below it. Windows PowerShell 5.1 adds no such floor.

Supporting reasons: 5.1 is in-box on both machines the operator touches, so there is one icon to recognise; `ADSync` on `AWSPRDINFAAD01` is Framework-only regardless; and 7 is the less-exercised path here — the only 7-specific bug in the tree (`Get-M365OffboardingStatus.ps1`, `Cannot find an overload for TryParse and the argument count: 2`) was found late, in August 2026.

Two rules, applied together:

1. `exo_preflight.ps1` carries **`#Requires -PSEdition Desktop`**. Under pwsh this fails loudly and self-explains, which is what a non-technical operator needs.
2. Every printed command stays inside the **5.1-compatible subset** — no ternary, `??`, `&&`/`||` chains, `-Parallel`, `-SkipCertificateCheck` or `-AsHashtable`. That subset also runs on 7.6+, so a command pasted into the wrong window behaves rather than throwing a parse error.

The skill prints `$PSVersionTable.PSEdition` first and expects `Desktop`. It does **not** check for `pwsh` at all — the skill never needs it, and looking creates a decision the operator can get wrong.

**Findings that survived the debate and are not opinion:**

- `PSScriptAnalyzerSettings.psd1` pins **no** edition — no `PSUseCompatibleCmdlets`, `PSUseCompatibleSyntax` or `TargetVersion`. The merge gate does not decide this.
- All five Exchange scripts **parse cleanly on both editions** (`Parser::ParseFile` against 7.6.5 and 5.1.26100.9168). None carries `#Requires` or `CompatiblePSEditions`.
- Every `Export-Csv` in those scripts already passes `-Encoding UTF8` — BOM on 5.1, which `utf-8-sig` reads correctly. The read-back CSVs are safe.
- **The `.log` files are not.** All five write with `Add-Content` and no `-Encoding`, so on 5.1 they are cp1252. No printed parameter fixes this. The skill's log reader must open bytes and try `utf-8-sig`, falling back to `cp1252`.
- The EXO manifest declares no `CompatiblePSEditions`; it branches `RootModule` on `$PSEdition` between `netCore` and `netFramework` builds.

**Not verified:** nothing was executed against a live tenant on either edition, and Graph/EXO coexistence on 7 was never tested by actually loading both. Graph-first import ordering is kept on both editions because it costs nothing.

### Why the operator runs the commands

`Connect-ExchangeOnline` and `Connect-IPPSSession` are interactive. A tool call cannot see or answer a modern-auth prompt, and the `power-automate-api` skill in this repo already records this as a hard constraint. So the contract is:

- The skill **prints** an exact, copy-pasteable command.
- The operator pastes it into their own PowerShell window.
- The skill **reads back** the CSV or log the command wrote, from `C:\scripts\reports` or `C:\scripts\logs`.

This makes every step auditable, leaves the credential entirely outside the agent, and means a failed step is visible to the operator rather than swallowed.

### Requirement coverage

| Requirement | How it is met |
|---|---|
| Single email **or** CSV | One `-Identity` prompt or a CSV path. CSV parsing follows `knowbe4-admin/kb4.py`: `utf-8-sig` encoding, auto-detect the email column, report bad rows rather than skipping silently. |
| PowerShell modules present, install if missing | `scripts/exo_preflight.ps1` detects and, after one confirmation, **installs** — reporting a gap is not sufficient. All installs are `-Scope CurrentUser`. Sets TLS 1.2 first, because `Install-Module` on PS 5.1 fails on the Gallery without it. See "Installing prerequisites" below. |
| Correct permissions in M365 | Preflight resolves the connected identity's roles and names the *missing* one specifically, not "access denied". Checks Exchange Administrator / Compliance Administrator and eDiscovery Manager membership. |
| Prompt to create an SDP ticket | Delegates to `infra-work-ticketing`, which wraps the ServiceDesk Plus MCP connector. Runs `ticketctl.py redact-check --emit` before any write — the connector does not scrub. Never creates a ticket without confirmation. |
| Confirm the user is deleted on-premises | `Get-MgUser -Property OnPremisesSyncEnabled`. `True` means the object is still mastered on-prem and deleting in Entra alone will be undone by the next sync. |
| Azure AD Connect delta sync | Printed for the operator to run **on `AWSPRDINFAAD01`**: `Import-Module ADSync; Start-ADSyncSyncCycle -PolicyType Delta`. Windows PowerShell 5.1 only — `ADSync` has no PowerShell 7 build. |
| Reports and logs, directories created | Reports `C:\scripts\reports`, logs `C:\scripts\logs`, both created if absent. **See the log-path conflict below.** |
| Litigation Hold already configured? | Checked before any change, and checked as four separate things — see "Hold is not one feature" below. |
| Walk through every step of both runbooks | One step at a time, validated before advancing. 41 steps in Cleanup (Phases A–E); triage plus 5 exclusive paths in Restore. |

### Installing prerequisites

**The skills install what the operator is missing, rather than handing back a list of prerequisites.** A non-technical operator given a list is stuck at step one. Confirm once, install, verify, report what landed and where.

**Everything installs under the user profile.** `Install-Module -Scope CurrentUser` and `Install-PackageProvider -Scope CurrentUser` for PowerShell; `pip install --user` or an owned virtual environment for Python. The reason is local administrator rights: on a managed corporate workstation a machine-wide install raises an elevation prompt the operator often cannot answer, while a per-user install needs none and affects nobody else.

Order in `exo_preflight.ps1`:

```powershell
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
Install-PackageProvider -Name NuGet -MinimumVersion 2.8.5.201 -Scope CurrentUser -Force
Install-Module ExchangeOnlineManagement -Scope CurrentUser -Force -AllowClobber
Install-Module Microsoft.Graph -Scope CurrentUser -Force -AllowClobber
```

Details that decide whether this works:

- **TLS 1.2 comes first, always.** Without it, `Install-Module` fails with "Unable to resolve package source", which reads like a network outage and is not.
- **Prefer `-Force` per install over `Set-PSRepository -InstallationPolicy Trusted`.** The latter is a persistent, machine-visible change to the operator's profile; the former is the smaller footprint.
- **`Microsoft.Graph` is a large meta-module** and takes minutes. Warn the operator, or install only the required sub-modules — a long silent pause reads as a hang.
- **Check the `CurrentUser` module path for OneDrive redirection.** It resolves under `Documents`, which Known Folder Move frequently redirects; a redirected path makes imports slow or intermittently fail in ways that look nothing like an install problem. Report it, do not try to fix it.
- **Verify after installing** with `Get-Module -ListAvailable`. On failure, print the verbatim error and stop — no retry loop, and never a machine-wide fallback.

`doc-builder` follows the same rule for `python-docx`, `pywin32`, `PyMuPDF` and `Pillow`, and ships a `requirements.txt` so the set is declared as well as installable. Three of its dependencies are **not** pip-installable and are reported rather than fixed: Microsoft Word must be present for the HTML→Word COM path (pandoc, LibreOffice and poppler are not available here), Word COM cannot run against a PDF that is open in a viewer, and `numpy` needs confirming as a real dependency rather than a stale import.

### The log-path conflict, and how it is resolved

You specified `C:\scripts\logs`. Every existing script in `Powershell/Exchange/` defaults to **`C:\scripts\log`** (singular) — `Invoke-M365OffboardingHold.ps1:532`, `Get-M365OffboardingStatus.ps1:256`.

The skills will pass `-LogPath 'C:\scripts\logs'` explicitly on every invocation rather than relying on the default, and will create both directories. The existing scripts are not modified. Consequence: historic logs stay in `C:\scripts\log` and new ones land in `C:\scripts\logs`, so the preflight prints a one-line notice when it finds content in the old path.

### Runbook defects to fix in the walkthrough

The research pass found six real defects. These are runbook and script bugs, not skill bugs, so the skills work around them and say so:

1. **Ordering bug — the baseline runs before the grant that makes it work.** Cleanup Step 4 runs `Test-MailboxPreservation.ps1 -RunComplianceSearch`, but the eDiscovery role grant and its 30–60 minute propagation are Step 14. The first compliance search therefore returns zero, silently, and looks like "nothing to preserve". **Fix:** the skill runs the eDiscovery grant first, waits, then takes the baseline.
2. **A helper tears down the operator's session.** `Test-MailboxPreservation.ps1` calls `Disconnect-ExchangeOnline` in a `finally` block, killing the session the rest of the runbook depends on. **Fix:** the skill expects this and prints the reconnect command immediately after that step.
3. **Field-name mismatch.** The runbook formats `TotalItemSizeMB`; the script emits `MailboxSizeGB`. **Fix:** the skill reads the field the script actually writes.
4. **Non-overlapping Graph scopes** between the two runbooks. **Fix:** the preflight requests the union.
5. **Role-group name drift** — `eDiscoveryManager` in one place, `eDiscovery Manager` / `eDiscovery Administrator` in another. **Fix:** the skill resolves the role group by lookup rather than by literal.
6. **SDP appears nowhere in either runbook.** **Fix:** the ticket step is added at the start, before any change.

### Safety model

Irreversible steps, each gated by typed confirmation naming the count and what is lost:

| Step | Why it is irreversible |
|---|---|
| Account deletion (Cleanup, Phase C) | No script covers this; it is portal or `Remove-MgUser`. Under an active hold it produces a preserved inactive mailbox; without one it starts a 30-day destruction clock. |
| Restore Path 3 — recover | Destroys the preserved copy. |
| Restore Path 5 — permanent destruction | Exactly what it says. |

None of these have `ShouldProcess` in the underlying scripts, so the gate has to live in the skill. **Licence removal is never a separate step from the hold** — removing it disconnects the mailbox permanently after 30 days regardless of hold state.

Hold is checked as four separate things, because "is this user on hold?" cannot be answered `no` until all four say no: Litigation Hold, retention policies and labels in Purview, eDiscovery holds, and In-Place Hold remnants.

### Shared machinery

`exchange-mailbox-cleanup` owns `references/` and `scripts/`; `exchange-mailbox-restore` reads them by relative path and both SKILL.md files state they install together.

**This is the one compromise in the design.** The repo standard forbids nesting and every directory under `skills/` is expected to have a `SKILL.md`, so there is no natural home for a shared, skill-less directory. The alternative — duplicating both reference files — trades a fragile path for guaranteed drift. Flagged for review.

Shared files:

- `references/connect-and-preflight.md` — the two-session split (`Connect-ExchangeOnline` vs `Connect-IPPSSession`), module order (Graph **before** ExchangeOnlineManagement on PS 5.1 — load-bearing), auth modes.
- `references/hold-and-mailbox-states.md` — hold types, and Active / Inactive / Soft-deleted as three distinct states.
- `references/operator-safety.md` — the confirmation script for each irreversible step.
- `scripts/exo_preflight.ps1` — modules, roles, directories, connectivity.
- `scripts/parse_user_input.py` — one address or a CSV, stdlib only.

---

## Part 2 — The merged document builder

### What is wrong with the current pair

`solomon-sop-maker` is **not shippable as it stands**:

- Untracked (`?? skills/solomon-sop-maker/`), and contains a **nested `.git/`** which would vendor as an empty gitlink.
- Its quick start points at `C:\repos\solomon_sop_maker_skill\scripts`, which does not exist here, so `sop_paths.py` resolves to nothing and **every documented command fails as installed**.
- Depends on `Build-SopPdfs.ps1` from a repo that is not present.
- `numpy` undeclared; stray `__pycache__` committed.
- Overwrites production masters with no dry-run.
- Its description is path-bound to `C:\repos\OnboardingSOPs`, so it cannot fire anywhere else.
- Missing from `skills/README.md`, `.claude-plugin/marketplace.json` and `CHANGELOG.md`.

`report-builder` is broadly conformant, with four gaps: `pywin32` undeclared, zero example invocations (the standard asks for 3–6), `scripts/_test/checklist.sh` invisible in `SKILL.md`, and no disambiguation callout.

**Neither currently fires on "write an SOP."** `report-builder` contains no SOP, procedure or how-to wording at all. That alone defeats the auto-trigger requirement.

### The merge

One implementation, `doc-builder`, with a routing rule at the top:

| Content | Path | Why |
|---|---|---|
| Findings, tables, severity, executive summary | HTML → Word COM (`report-builder`'s pipeline) | Word's HTML parser is the constraint; the trap list is already measured against it. |
| Step-by-step procedure with screenshots | python-docx OOXML (`solomon-sop-maker`'s pipeline) | Only this path handles bordered screenshots and the `wp:effectExtent` defect. `add_picture()` writes neither `a:ln` nor `effectExtent`, so Word clips the border. |

Both pipelines are kept because neither can do the other's job. The routing rule is stated once, in `SKILL.md`, so the model picks before it starts writing.

Conflicts and their resolutions:

| Conflict | Resolution |
|---|---|
| Segoe UI vs Franklin Gothic Book / Georgia | Brand pack decides. Neutral pack uses a system stack. |
| `#1F4E79`/`#4A90C2` vs `0E2841`/`EF483D` | Brand pack decides. |
| report-builder forbids a hardcoded org name; sop-maker's conformance gate *asserts* one | Gate is inverted: it asserts the org name **matches the active brand pack**, whatever that is. |
| Output to gitignored `reports/` vs a committed sibling repo | Reports → `reports/` (gitignored, dated). SOPs → wherever the operator says, defaulting to the brand pack's configured masters directory. A report is not documentation. |

### Auto-firing on documentation, SOPs and reports

One description covering all three, carrying the words a real person types: report, assessment, audit write-up, findings document, executive summary, SOP, standard operating procedure, runbook, work instruction, how-to, quick reference guide, training guide, "write this up", "make it look professional", "send this to the client", "document this process", "make a PDF".

`solomon-doc-builder` gets a narrow description that names Solomon explicitly and defers to `doc-builder` for everything else, so the two do not compete.

### The generic / Solomon split

```
skills/doc-builder/            # everything: scripts, references, both pipelines
  assets/brands/neutral/       # default palette, template, footer
skills/solomon-doc-builder/    # SKILL.md + assets/brands/solomon/ only
```

`solomon-doc-builder` invokes `doc-builder`'s scripts with `--brand solomon`. No logic is duplicated, so a fix lands once. This is what makes "two copies" and "no drift" both true.

### Brand resolution is configuration, not a trigger

**A brand pack that is installed is applied.** `doc-builder` resolves its brand at runtime rather than waiting to be asked:

1. An explicit `--brand <name>` always wins.
2. Otherwise `scripts/resolve_brand.py` scans sibling skill directories for `assets/brand.json`. Exactly one found → that brand is the default for every document, SOP and report.
3. More than one found → the skill asks which, naming them.
4. None found → the neutral pack.

This matters for two reasons. First, it means an operator at Solomon never has to remember to ask for Solomon styling, and the document they forget to ask about is still correct. Second — and this is the structural point — it takes `solomon-doc-builder` out of the trigger space entirely. It is a data directory with a marker file, not a skill competing with `doc-builder` for the words "write a report". Its `description` says only that it supplies the Solomon brand pack and that `doc-builder` should be used for the actual work.

`resolve_brand.py` prints which brand it resolved and why, so a surprising result is diagnosable rather than mysterious.

## Models

Design and build roles run on **Fable 5.1** (`claude-fable-5-1`), pinned in `.crew/config.json` under `dev.roles` for `skill-author`, `exchange-online-specialist`, `powershell-5.1-expert`, `powershell-7-expert` and `developer`. Review stays independent of the author's model per the crew's QA rule.

## Verification

Every skill: frontmatter parses, `name` matches directory, description tested against three realistic phrasings, every referenced file exists, every script runs and returns an exit code.

The Exchange skills cannot be exercised end to end without a live tenant and a real terminated user. **That will be stated plainly rather than implied.** What can be tested: preflight against a real connection, CSV parsing against fixtures, and every printed command checked for syntax without running it.

## Resolved questions

Decided by the user on 2026-09-10. No open questions remain.

### 1. Shared references — cleanup owns them

`exchange-mailbox-cleanup` holds the single copy of `references/` and `scripts/`. `exchange-mailbox-restore` reads them by relative path, and both `SKILL.md` files state plainly that the two skills install together.

Accepted cost: installing only one of the two breaks the reference path. Mitigation: each `SKILL.md` names its sibling as a hard dependency in the first section, and `exo_preflight.ps1` fails with a named error rather than a missing-file traceback if the sibling is absent.

### 2. Old skills — deprecated stubs, not deletions

`report-builder` and `solomon-sop-maker` both stay as directories with a short `SKILL.md` pointing at `doc-builder`. Nothing referencing the old names breaks.

Accepted cost: three descriptions now sit in the documentation trigger space. Both stubs therefore carry an explicit **"Do NOT use this skill — use `doc-builder`"** clause as the first line of their description, so the model routes past them rather than treating them as candidates.

### 3. Nested `.git/` — bundle first, then remove

Inspected 2026-09-10: a **real repository, not a gitlink file**, with **2 commits** on `main` — `af1f182` ("Initial commit: Solomon SOP maker skill and build toolchain") and `93c1aa7` ("Express hyperlinks and italic captions; gate both; add the spec extractor") — and **no remote and no upstream**. That history exists in exactly one place.

Procedure: `git bundle create --all` from inside it, store the bundle at `docs/archive/solomon-sop-maker-history.bundle` so it is version-controlled and genuinely preserved, verify the bundle, then remove the nested `.git/`. Authorship survives; the skill vendors correctly.

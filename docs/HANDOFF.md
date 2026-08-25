# Handoff notes

Rolling notes for whoever picks this repo up next. Newest first. Each entry says
what changed, why it was done that way, and what is still open — the reasoning
that does not survive in a diff.

---

## 2026-08-23 — crew 0.2.0 and a full QA pass over `skills/` (PRs #28, #29, #30)

### What changed

Three PRs, ~45 defects. The through-line: almost none of these were visible by
reading the code. They were found by running it, on Windows, with real inputs.

**PR #28 — `plugin/crew` 0.2.0.** The Windows hooks had never run. `guard.sh` and
`verify-gate.sh` exited 0 on MSYS/MINGW to "defer" to `.ps1` twins that
`hooks.json` registered with a `shell: powershell` field Claude Code does not
read. So on Windows the command guard blocked nothing and the `Stop` gate ran
nothing — silently. Also fixed: the verify map skipped every root-level file
(`fnmatch`'s `*` spans `/`, so `**/*.tf` never matched `main.tf`); a failing
`Stop` check could pin the session; `python3` was a hard dependency of six
scripts with every call suppressed. Added `/crew:promote` with a `PreToolUse`
gate that refuses a deploy without an upstream all-pass row **for that sha**,
`/crew:reference`, `_verify/` as the canonical check directory, and three
committed sabotage-tested suites (50 hook cases, 32 setup-script cases, 91
structural checks).

**PR #29 — `skills/` QA.** Two live-infrastructure BLOCKs: `cisco-meraki`'s
`batch_commit` could destroy config with no confirmation while the module
docstring promised snapshot→diff→confirm as "control flow, not a rule someone
has to remember"; `intune-graph` exposed device wipe from a one-liner with no
guard of any kind. Plus a secret-redaction denylist that missed every Meraki
pre-shared-key field name, an SMTP path that mailed the password in cleartext on
a `security: "tls"` typo, and `work-log-reporter` being unable to render at all
on Windows (`strftime("%-I")` is glibc-only and raises rather than degrading).

**PR #30 — the deferred items.** `notify`'s inbox lost messages under
concurrency; the daemon could run twice against one bot token.

### Why this way

**The guard branches on `tool_name`, not the OS.** The first fix branched on the
OS, which made Windows *worse*: a `Bash` tool call is bash syntax even on
Windows, so `guard.ps1` judged it with PowerShell rules — blocking the correct
secret-capture form (`DB_PASS=$(...)`) while allowing `vault kv get > file`. A
guard that is wrong is more dangerous than one that is absent, because it gets
trusted. Only the `PreToolUse` guards branch at all now; the other hooks judge no
command, are reached through `bash`, and a `.ps1` beside them would be
unreachable code.

**Secret redaction is substring, not exact-match.** An exact list only redacts
the names someone thought of. The bias is set deliberately: over-redaction costs
detail in a diff, under-redaction publishes a credential into a diff, a ticket,
and a snapshot file on disk.

**`--read-only` is an allowlist.** A case runs under `run-all.sh --read-only`
only if it declares `# readonly: yes`. It was a denylist, where an unmarked case
ran against production. The cost of guessing wrong is asymmetric.

**The context watch reads `message.usage`, not file size.** The transcript is
cumulative — it keeps every turn ever written, including ones a compaction
discarded — so file size measures what a session produced, not what the window
holds. It read 45% high (950k against 654k actual). `budgetTokens` now defaults
to `null` and derives itself from the model id **corrected by observed peak
usage**, because a 1M variant reports its base id (`claude-opus-5[1m]` records as
`claude-opus-5`). Observed usage cannot exceed the real window, so 668k of held
tokens proves the window is not 200k.

**Every gate that can block now has a committed, sabotage-tested suite.** Not
"tests exist" — tests that were *verified to go red* when the bug is
reintroduced. `guard.sh` shipped two real regressions in two review passes, both
caught only by running it.

### What was verified

- 137 tests passing (133 `cisco-meraki`, 4 new `notify` concurrency)
- crew: 50/50 hook cases, 91/91 structural checks, 32/32 setup-script cases
- pylint exit 0 with zero messages across the repo; zero non-ASCII in any script
- The inbox race, reproduced and fixed: 4 of 240 messages lost per run before,
  0 of 240 across 8 runs after
- `az` resolution, the Meraki redaction, the Intune gate, the Visio overwrite
  refusal, and the email render all exercised against real inputs on Windows

### Still open

- **The crew prompts are unproven.** 16 commands and 9 agents. Their *structure*
  is validated — frontmatter parses, tools exist, referenced agents and paths
  resolve, read-only agents hold no write tools. Their *judgement* is not, and no
  test can close that. It needs `/crew:init` in a real repository and one ticket
  run end to end, which is setup Phase 7.
- **crew's hooks are inert until `/crew:init` runs in a repo.** This is
  deliberate and now documented in three places, but it is the first thing to
  check when someone reports a gate not firing. `ls .crew/` before debugging.
- **`/crew:promote` is only partly enforceable.** The pre-deploy conditions are
  hook-enforced. That smoke, regression and verify actually ran *after* the
  deploy is a claim in `.work/PROMOTIONS.md`, not a measurement — a hook fires
  before a command and after a turn, never during. Documented as such rather than
  implied as coverage.
- **`platform.sh` detects but does not adapt.** `resolve-tools.sh` now reports a
  tool as native, WSL-only, or missing, but nothing auto-wraps a command in
  `wsl.exe -e`. Resolution is written into the map at setup, by hand.
- `/reload-plugins` reported 55 load errors on this machine. Unexamined — run
  `/plugin` to see them.

---

## 2026-08-15 — `vault-automation/`: the vault that feeds itself

### What changed

New sibling component to `claude-obsidian-setup/`. Where that one CREATES a vault,
this one AUTOMATES an existing vault: capture hooks (SessionEnd/PreCompact →
`~/.claude/hooks/vault-capture.py` → `inbox/pending-reflect.md`), a nightly
headless-Claude gardener (scheduled task, 5-sessions/night cap, 80-turn/2h limits),
a Dataview `HOME.md` dashboard, the five community plugins, and an OPTIONAL git
layer. Built live on the primary machine first (vault `C:\repos\claude-memories`),
then extracted here as parameterized, dry-run-by-default, idempotent scripts.

### Why this way

- **Obsidian Sync is the source of truth for sync/backup** — the vault owner uses
  Sync, so git is strictly additive (history/rollback) and everything degrades
  gracefully without it. The gardener probes `.git`/origin at runtime and adjusts
  its own prompt. Do not "fix" this by making git mandatory.
- The settings.json hook merge is done in embedded Python, not PowerShell — PS 5.1's
  ConvertFrom-Json round-trip mangles deep hook arrays.
- Hook script fails silent by design: a capture miss must never break a session.
- Gardener uses `--dangerously-skip-permissions` because headless sessions cannot
  answer permission prompts; scope is bounded (own vault, turn/time caps).

### Still open

- First real gardener run happens tonight on the primary machine — its log
  (`<vault>\.claude\gardener-logs\`) will show whether the 5-session cap and the
  giant-transcript case (a 100+-turn infra session is queued) behave.
- SessionStart digest injection (surface yesterday's daily note at session start)
  was deliberately deferred — startup context cost needs measuring first.
- No Linux/WSL variant of the setup script yet (Task Scheduler → cron/systemd).

## 2026-08-14 — Obsidian vault setup: menu item 19 + `claude-obsidian-setup/`

### What changed

**Menu item 19 installs Obsidian and its two Claude plugins.** Off by default, added
to both installers as a matched pair. The app comes from a package manager
(Chocolatey → winget on Windows, flatpak → snap on Linux) because Obsidian ships no
npm/pip package and distro repos generally don't carry it. Then two marketplaces:
`AgriciDaniel/claude-obsidian` for the vault engine, and
[`kepano/obsidian-skills`](https://github.com/kepano/obsidian-skills) for Obsidian's
own upstream syntax references.

**`claude-obsidian-setup/` creates and verifies the vault.** Two scripts plus a
README, dry-run by default, ending in the product's own `doctor` and `lint`.

### Why it was done this way

**Item 19 stops at the app and the plugins, on purpose.** Creating a vault is a
filesystem write governed by a reviewed transaction — you read a plan, you get back an
`approved_plan_sha256`, and you pass that exact hash to apply it. Folding that into an
unattended bootstrap run would mean applying a plan nobody reviewed, which is precisely
the thing the product's contract exists to prevent. So the item prints the next step and
the dedicated scripts perform it.

**One root, one switch.** `-RepoRoot` / `--repo-root` (default `C:\repos`, `~/repos`)
moves the vault *and* the product checkout together, because the two are almost always
kept side by side. Either half can still be overridden alone. The vault's internal
layout is fully relative — `.claude-obsidian.json` stores `"vault": "."` and the source
ledger uses vault-relative locators — so the absolute path genuinely doesn't matter,
which is what makes a single switch safe.

**Most of the Windows script is scar tissue.** Four failure modes, each of which
presents as something unrelated:

- Native Windows can't write to a vault at all. Mutation safety needs POSIX directory
  descriptors and `fcntl.flock`; native Python has no `fcntl`. Reads and dry-runs work,
  writes are refused with `UNSUPPORTED_PLATFORM`. Hence creating the vault inside WSL.
- `python3` on Windows resolves to the Microsoft Store App Execution Alias, which prints
  an install advert to stdout instead of running Python. That silently breaks the
  plugin's `SessionStart`/`Stop` hooks — a `SessionStart` hook that "succeeds" while
  emitting that advert injects it as session context. A hard link
  `python3.exe → python.exe` fixes it globally, and is preferable to hardcoding an
  interpreter path into the plugin's `hooks.json`, which would create a permanent local
  diff against an upstream checkout.
- `/mnt/c` mounts without the `metadata` option, so `chmod` returns `EPERM` and every
  apply dies with `CORRUPT_RUNTIME_STATE: cannot write confined bundle copy`. A live
  remount does **not** fix this — the option only takes effect at mount time, so it needs
  `/etc/wsl.conf` plus `wsl --shutdown`.
- `git config --global` does not cross the Windows/WSL boundary, and `checkpoint` runs in
  WSL, so it fails `GIT_FAILED: Author identity unknown` even when Windows git is fully
  configured. Setting identity repo-locally satisfies both.

### What was verified

- Both installers parse clean (`bash -n`, PowerShell AST parser).
- Catalog parity checked mechanically: 19 keys, 19 default flags, 19 labels, identical
  key order and default flags across the pair, `obsidian` last and opt-in on both, and
  all four marketplace/plugin identifiers present in both scripts.
- `claude-obsidian-setup` scripts dry-run clean on Windows and under WSL.
- A full `--apply` run against a throwaway vault created the expected 14-file layout and
  finished `doctor ok` / `lint 0 issues`; a second `--apply` reported
  `already initialised` and changed nothing.
- **Reviewed by `codex exec review --base main`** (codex-cli 0.147.0), which found three
  real defects, all fixed before merge:
  1. The Windows script reported a missing WSL `python3` as "will install" but never
     queued it — the presence loop only covered `git` and `curl`, so `-Apply` left the
     distro without Python and every vault write still refused. Introduced while removing
     a cosmetic duplicate check id; the version probe now feeds `$needPkgs` directly, and
     the `fcntl` probe reports "unknown until python3 is installed" instead of a bare
     failure.
  2. The Linux script ran the Debian NodeSource bootstrap on *any* distro, so Node install
     failed on the Fedora and Arch paths it otherwise claims to support. Node now installs
     per package manager: NodeSource for apt, the distro's own `nodejs`/`npm` for
     dnf/pacman.
  3. The Linux script ran `mkdir -p` before checking `--apply`, so a dry-run created
     directories — breaking the guarantee the whole script is built on. Moved inside the
     apply branch and verified: a dry-run against a nonexistent nested root now creates
     nothing.

  Worth repeating the lesson from (1): the cosmetic fix and the functional break were the
  same edit. Removing an item from a presence-check loop silently removed its install.

- **A second `codex exec review --base main` pass** found two more real defects and one
  false positive:
  1. *Real.* The `/etc/wsl.conf` guard was `grep -q '^\[automount\]' || append`, which is
     a silent no-op on the **most likely** machine: one that already has an `[automount]`
     section but no `metadata` option. It would shut WSL down and still leave writes
     broken. Now handled with awk across all three shapes — no file/section, a section
     with an `options` line to rewrite, and a section with no `options` line — preserving
     sibling keys like `enabled = true` and backing the original up. Verified against six
     synthetic configs including idempotency and the mid-file-section case.
  2. *Real.* On Linux an absent `python3` called `fail`, which latches `FAILED=1`. Since
     the same run then installs it, a fully successful setup still exited 1. Repairable
     conditions now report `FIX`, and the `fcntl` probe reports "unknown until python3 is
     installed" rather than a failure that cannot be true yet.
  3. *False positive.* It claimed `git clone` cannot create missing parent directories, so
     a fresh `~/repos` would break the clone. Tested directly: `git clone` into
     `/tmp/a/deep/nested/repo` creates every parent. No change made.

  Both rounds are a good argument for running the reviewer: rounds one and two each found
  a defect that only appears on a machine unlike the one being developed on — no python3
  in WSL, a non-Debian distro, or a pre-existing `[automount]` section.

- **A third pass** raised the Python **floor** (3.11), all three findings genuine:
  1. *Fixed.* The Windows script version-checked `python.exe` nowhere before aliasing it,
     so on a 3.10 machine it would create `python3.exe → python.exe` and report the alias
     "repaired" while every hook it exists for stayed broken. It now version-gates first
     and refuses to alias an interpreter below the floor.
  2. *Deliberately not auto-repaired* (both scripts). An existing `python3` below 3.11 —
     Ubuntu 22.04 ships 3.10 — is reported with the concrete remedy rather than fixed,
     because reaching 3.11+ there means adding a third-party repository (deadsnakes) and
     possibly moving `update-alternatives`. That is too invasive to do behind a single
     `--apply` on someone's machine. What was fixed is the *consequence*: the vault step
     now refuses with `blocked: python3 3.11+ is required` instead of proceeding and
     failing obscurely somewhere inside the core.

  Stopped reviewing after three rounds. Rounds one and two were straight defects; round
  three was one real bug plus a scope decision. Further passes were returning judgment
  calls rather than faults.

### Follow-up: both deferred findings resolved

The two items originally left alone were revisited and closed:

- **The Python floor is now genuinely repaired, not just reported.** The first judgement —
  "too invasive to fix" — was too broad. It is only true of the *last* resort. Both
  scripts now, in order: use a newer versioned interpreter that is already installed;
  else install one (`python3.13`/`3.12`/`3.11`) from the repositories **already configured
  on the machine** and use it alongside the untouched system `python3`; else stop with the
  concrete remedy. `update-alternatives` is never touched and no third-party repository is
  ever added, so the original objection still holds for the case it actually applied to.

  Every downstream call now runs through a `$PY` / `$script:WslPy` variable rather than a
  hardcoded `python3`, which is what makes "use a different interpreter" possible at all.

  Verified by faking it: a stub `python3` reporting 3.10 was put first on `PATH`, and the
  script located the real `python3.12`, used it, and built a complete 14-file vault with
  `doctor ok` and `lint 0 issues`, exiting 0. That path had never executed before.

- **The `git clone` parent directory was made explicit** even though the finding was a
  false positive. `git clone` does create missing parents — verified directly — so nothing
  was broken; the `mkdir -p` simply removes the dependency on that behaviour and keeps the
  failure obvious if the root is not writable. Recorded here so nobody "fixes" it back on
  the strength of the same incorrect claim.

### What is still open

- **Item 19 is untested end-to-end on a machine without Obsidian.** The install branches
  (choco, winget, flatpak, snap) are written from upstream's documented package ids but
  were not exercised — this machine already had Obsidian. The detection branch and the
  plugin half were exercised.
- **Four post-install steps stay manual** and are printed rather than automated: the
  Templates folder, the Daily-notes folder and date format, the optional Obsidian CLI
  toggle, and opening the vault. This is not laziness — the product refuses to write
  arbitrary `.obsidian` config, and its non-wiki allowlist is only five paths
  (`app.json`, `appearance.json`, `graph.json`, `snippets/vault-colors.css`,
  `.claude-obsidian.json`). `daily-notes.json` and `templates.json` are not on it, and
  bypassing that with a host write would defeat the contract.
- **Obsidian re-serialises `.base` files it opens**, rewriting content and permissions.
  That makes an exact per-operation `checkpoint` fail with `COMMITTED_MODE_MISMATCH` if
  Obsidian is running. Checkpoint immediately after an operation, or close Obsidian first.

---

## 2026-08-07 — Cursor-driven install menu, per-skill selection, SDP connector routing

### What changed

**Both installers got a cursor picker.** `scripts/install-prerequisites.sh` and
`scripts/install-prerequisites.ps1` now draw a checkbox list you drive with the
arrow keys: ↑/↓ move, Space toggles, Enter starts, `A`/`N`/`D` set all/none/
defaults, `Q` or Escape cancels. The old numbered prompt was not deleted — it is
the fallback, and the scripts choose it automatically when raw key input is not
available.

**The repo's own row opens a sub-picker.** → on `This repo's marketplace + N of
19 skills` lists every skill in this repo so you can install three instead of all
nineteen. `--skills cloudflare,drata` / `-Skills 'cloudflare,drata'` does the same
without the UI, and also takes `all`, `none`, and positions (`1,4-6`).

**`infra-work-ticketing` learned where to send ticket writes.** An `mcp` block in
its config file records the "Solomon Service Desk Plus" connector as the preferred
transport and `ticketctl.py` as the fallback.

### Why it is built this way

**The picker had to be optional, not universal.** This repo's advertised install
path is `curl -fsSL … | bash` and `irm … | iex`. Under the bash one-liner the
script arrives on stdin, so the terminal is read through a separate file
descriptor (fd 3) — that was already true for the numbered prompt and the picker
inherits it. But plenty of real environments cannot do raw key input at all: no
`stty`, `TERM=dumb` in a CI log, PowerShell ISE, a redirected console, a six-line
tmux pane. Every one of those falls back to the numbered prompt rather than
failing. `picker_supported` (bash) and `Test-PickerSupported` (PowerShell) are the
gates; both run *before* anything is drawn.

**Line clipping is load-bearing, not cosmetic.** The redraw works by moving the
cursor up N lines and repainting. If any printed line wraps, N is wrong and the
next repaint smears the menu over whatever was above it. So every line — title,
rows, scroll indicator, both hint lines — goes through `pick_fit` /
`Format-PickerLine` first, and the key hint collapses to a short form under 84
columns.

**The terminal state is restored from a trap.** Bash saves `stty -g` and restores
it from an `EXIT`/`INT`/`TERM` trap. Without that, Ctrl-C in the menu leaves the
user's shell with echo off and the cursor hidden, which reads as "the installer
broke my terminal" and is much worse than the bug it would be masking.

**Enter does not open the sub-picker; → does.** Enter always means "start
installing". Making it context-dependent would mean a user who arrows down to the
repo row and presses Enter expecting a sub-menu kicks off a twenty-item install
instead. The `>` at the end of the row and the footer hint are the affordance.

**Opening the sub-picker ticks the parent row.** Otherwise a careful nineteen-item
sub-selection could be silently discarded because the parent was unticked. If you
tick the parent but zero skills, the marketplace is still registered and the script
warns and names the fix (`--skills all`) rather than doing nothing quietly.

**The skill catalog is now the single source.** `SKILL_KEYS`/`SKILL_NAME` (bash)
and `$script:SkillCatalog` (PowerShell) feed both the picker rows and the install
loop. The old `own_plugins` / `$ownPlugins` arrays were a second copy of the same
list and are gone.

**The `mcp` block holds no credentials.** The connector authenticates each person
separately through Claude Code — that per-person identity is the entire reason to
prefer MCP over `ticketctl.py`, because SDP's audit trail then names a person
rather than a shared service account. A token in the config would duplicate a
secret that already lives somewhere safer. `ticketctl.py` cannot call MCP tools at
all; it owns and reports the routing decision so the skill and the script cannot
disagree.

### How it was verified

- `bash -n` and `[Parser]::ParseFile` on both scripts.
- Bash: skill-spec expansion (names, positions, ranges, `all`, `none`, unknown
  tokens), live label counts, and one rendered frame at 30×100, 16×60, 16×50,
  40×200 and 10×40 — row count, viewport clamping, scroll indicator, and no line
  exceeding the window width.
- PowerShell: the same spec expansion, plus the draw loop driven by a scripted key
  queue through the `Get-PickerConsole` / `Set-PickerCursor` / `Read-PickerKey`
  seams — arrows, Space, `A`/`N`/`D`, Enter, `Q`, Escape, ←, → gated to flagged
  rows, and viewport clamping at 12×100 and 20×50.
- Catalog ↔ `marketplace.json` parity asserted programmatically: 19 = 19, no diff.
- `ticketctl.py doctor` routing output against the live connector `/health`, which
  returned `writes_enabled: true` and `asset_writes_enabled: true`.

**Not verified:** neither picker has been driven by a human at a real keyboard.
The PowerShell draw loop was exercised through the console seams, not against a
real console — colour handling, `Clear-Host` on buffer overflow, and window resize
mid-menu are the untested edges. Worth one manual run of each before relying on it
on a fresh machine.

### `ticketctl.py update` / `close`, and why there is no category admin

Added after the menu work, in the same session. `update` and `close` now exist on
both providers, so the API fallback is no longer missing two of the four write
verbs.

**The category question has two readings and only one is buildable.** Setting the
category *on a ticket* works from both paths. Administering the *taxonomy* —
adding "Backup/Restore" as a new category — has no API: the SDP Cloud v3 docs list
48 admin collections (project_type, closure_code, product…) and category is not
among them, `admin/category.html` 404s, and the connector's `sdp_list_metadata` is
read-only. Writing that code would have meant guessing an endpoint and shipping it
against a live production desk. It is documented as an SDP admin-UI job instead.

**SDP close is not a clean fallback.** There is no `/requests/{id}/close`
sub-resource in the cloud v3 API — the scrape of the request docs turns up exactly
three paths and seven operations, none of them a close. So `ticketctl.py close`
PUTs a terminal status plus `closure_info` to the edit endpoint, which means the
desk's mandatory-closure rules are enforced server-side and can reject it, where
`sdp_close` applies them itself. The routing table says so explicitly rather than
letting the two look interchangeable.

**Jira has no category.** `--category` maps to a component, the nearest analogue.
Called out in SKILL.md so nobody reads it as parity.

**A pre-existing queue gap surfaced while testing.** `cmd_note` queued only around
the *send*, but `build_note` resolves `#40219` to an internal id — an API call. A
service desk that is down therefore failed during planning, outside the guard, and
the note text was lost: exactly the case the queue exists for. Planning is now
inside the guarded region for `note`, `update` and `close`, and `--dry-run` never
queues.

Verified with `--dry-run` on all four verbs for both providers (no credentials
needed — `resolve()` takes an `offline` path so the promise in the CLI epilog now
actually holds for ticket-scoped verbs), redaction confirmed on closure comments,
and a fault-injection round trip proving all three verbs queue on a planning
failure and replay to a byte-identical payload. **Not verified against the live
desk** — there are no ServiceDesk Plus credentials on this machine, so every write
path is doc-verified and dry-run-verified only.

### Open items

- **Menu positions are not stable.** `--select 12` means something different once
  an item is inserted. Scripted runs should use keys (`--select chrome-mcp`), and
  the README says so, but nothing enforces it.
- **The one-liner URLs are SHA-pinned** and must be re-pinned after every merge
  that touches `scripts/install-prerequisites.*`. `git rev-parse HEAD`, then swap
  it into both URLs in `README.md`.
- **Neither picker has been driven by a human.** The fallback-on-failure path is
  covered by fault injection in both scripts, but colour rendering, `Clear-Host` on
  buffer overflow, and a live window resize mid-menu are still untested by hand.

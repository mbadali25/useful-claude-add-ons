# Handoff notes

Rolling notes for whoever picks this repo up next. Newest first. Each entry says
what changed, why it was done that way, and what is still open — the reasoning
that does not survive in a diff.

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

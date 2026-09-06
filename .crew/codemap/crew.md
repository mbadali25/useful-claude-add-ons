anchor: useful-claude-add-ons@b56d41f

# crew

The `crew` plugin: a virtual dev team of context-isolated agents, slash
commands, bundled skills, and deterministic hooks. Registered in
`.claude-plugin/marketplace.json` (name `crew`, source `./plugin/crew`) at
version `0.16.12`, matching `plugin/crew/.claude-plugin/plugin.json:2-3`.
(Was `0.16.10` at the previous anchor; `0.16.11` bumped for the pylint and jq
CI fixes, `0.16.12` for the scrub rewrite described below. Both sites move
together — `check_versions` compares "has the directory changed since the
version was set", which `_verify/smoke.sh` does not run.)

## Inventory — and a stale description found while checking it

**DERIVED**, counted directly rather than trusted from any one description:

| | Count | How counted |
|---|---|---|
| Agents | 17 | `ls plugin/crew/agents/*.md` |
| Commands | 24 | `ls plugin/crew/commands/*.md` |
| Skills | 17 | subdirectories of `plugin/crew/skills/` (`find-skills` plus 16 `crew-*` skills) |

`.claude-plugin/marketplace.json`'s own `crew` entry describes it as "17
context-isolated agents (14 tiered, 3 domain specialists), 24 slash commands,
17 bundled skills" — this agrees exactly with the counts above. The three new
names are `agents/node-developer.md`, `agents/power-automate-specialist.md`
and `agents/sharepoint-developer.md`; each sits off the tier ladder in
`crew_state.SPECIALIST_ROLES` (`crew_state.py:656-659`) rather than being
granted by `roles_for_tier`, and is onboarded per repo with
`/crew:pm onboard <role>` rather than by scaling. See
`plugin/PLUGINS.md`'s specialist paragraph (added in this same diff) for why:
"this repo does SharePoint" is a fact about one checkout, not a defect class
every repo can have, so no tier ever grants one automatically.

**A real, currently-shipping discrepancy, found by cross-checking rather than
assumed — now wider than it was:** both install scripts describe the same
plugin differently. `scripts/install-prerequisites.sh:859` and
`scripts/install-prerequisites.ps1:843` both read *"crew - Virtual dev team:
11 agents, 21 commands, safety hooks"* — unchanged since the last refresh, so
now six fewer agents and three fewer commands than both the marketplace entry
and the actual directory contents (it was three and three before the three
specialists shipped). This is stale menu-label text, not a registration
failure (nothing in `check-marketplace.py` or `_verify/smoke.sh` checks that
a catalog *label's prose* matches a directory count — only that catalog *rows
exist*, per `check_docs`, documented in `marketplace-registration.md`). **Not
fixed here** — this is a documentation task with no code or content changes
in scope; recorded so the widened gap does not get re-discovered as new.

## Hooks

`plugin/crew/hooks/hooks.json` registers four events:
`SessionStart`, `PreToolUse`, `PreCompact`, `Notification`, `Stop`
(read via `python -c "json.load(...)['hooks'].keys()"`, five keys returned:
`SessionStart, PreToolUse, PreCompact, Notification, Stop`). Every bash
`command` entry has a `shell: "powershell"` sibling for the same event
(`plugin/crew/hooks/hooks.json:1-19` shows the `SessionStart` pairing:
`handoff-read.sh`/`.ps1`, `pm-brief.sh`/`.ps1`, `platform-sync.sh`/`.ps1`),
matching the "branch on the tool, not the OS" and "register each event once
per flavour" rules already stated in `CLAUDE.md` — not restated here beyond
confirming the current file actually does it.

## The 0.16.7 guard defects, and the dispatch.d rewrite that fixed the largest one

`plugin/crew/hooks/scripts/crew_state.py` gained 926 lines between the old
anchor and this one (`git diff --stat 2b0972d..HEAD -- plugin/crew` —
matches the brief's "roughly 900" closely enough to confirm rather than
round further), with smaller additions to `crew_config.py` (+153/-…),
`crew_platform.py` (+101/-…) and `pm_brief.py` (+8/-…). All four files
changed in commit `875c9c6f`, "crew 0.16.7: three domain specialists, and
four guard defects that failed open" (merged into this branch at `27832d4f`).
Read against the commit body rather than summarised from memory, the four
defects were:

1. **A later dispatch cleared the actual author.** `dispatch.json` held one
   `dev` slot; a second, unrelated dispatch on the same branch overwrote it,
   so review could read the wrong author, bar the wrong family, and clear
   the one that actually wrote the diff.
2. **The dispatch write was not atomic.** A concurrent reader could see a
   truncated file, `read_dispatch` collapsed the malformed JSON to `{}`, and
   the guard fell back to config describing the *next* run.
3. **A config of `{}` switched crew off permanently** — it parses, so
   `heal_config` treated it as healthy, and `/crew:upgrade` reported
   "already current" forever with no way out.
4. **`/crew:model` printed `eligible` for a family it could not name** — an
   unpinned `copilot` was reported eligible instead of `CANNOT PROVE
   INDEPENDENCE`.

The substantive fix for (1) and (2) is the rewrite this codemap's earlier
paragraph describes only briefly: `dispatch.json` (one shared, mutable file)
is replaced by `.work/dispatch.d/`, one immutable file per dispatch
(`crew_state.py:1006-1026`, `DISPATCH_DIR = (".work", "dispatch.d")`), with
the legacy single file still read as a lower-priority fallback
(`crew_state.py:1348-1350`) so an older record is not silently discarded.
Anyone who gitignores crew's working files by hand needs to add
`.work/dispatch.d/`, not just `dispatch.json` — `/crew:init` does both.

**Separately, on this branch, not touched by 875c9c6f:** two defects in the
`.sh` hook layer rather than the `.py` layer, both predating this refresh's
diff window (they landed before the *previous* anchor, `2b0972d`, so they are
not part of what changed since last time — recorded here because the old
crew.md never mentioned them). `hooks/scripts/_test/run-tests.sh`'s PATH
scrub used to end every `PATH` entry in a trailing colon, which every POSIX
shell reads as "also search the current directory" — fixed in `0bf0c2f3`.
And `pm-brief.sh`, `pm-pulse.sh`, `platform-sync.sh` and `handoff-read.sh`
used to resolve Python with `command -v python3 || command -v python`,
skipping the `py` launcher and exiting 0 with nothing on stderr when neither
resolved — fixed in `0131d0f0` to use the shared `crew_py()` in `_common.sh`
and to print to stderr on failure instead of failing silently.

**DERIVED (`run-tests.sh:74-135`, verified at `b56d41f`): that PATH scrub was
fixed twice more after `0bf0c2f3`, and the reason is worth carrying — CI was
red for both.** It compared `PATH` entries as *strings*, so on a merged-`/usr`
Linux — every GitHub runner — dropping the literal `/usr/bin` left `/bin`
behind pointing at the same directory, jq stayed reachable, and the suite
FATAL'd rather than run. Fixed by resolving each entry with `cd … && pwd -P`
before comparing. That exposed the real problem: the scrub removed jq's whole
*directory*, because `PATH` has directory granularity while the thing being
hidden is one file — and on Linux that directory is `/usr/bin`, holding
`python3` and `sh`, the interpreter the no-jq fallback runs on. It now
**substitutes** rather than subtracts: mirrors the directory into a temp dir as
symlinks minus every spelling of jq (`jq`, `jq.exe`, `jq.bat`, …; the bare name
alone was not enough on Windows, where the binary is `jq.exe` plus a chocolatey
`jq.bat` shim), and puts the mirror at the same `PATH` position. The mirror
proves itself — if `command -v jq` still resolves under it the suite FATALs and
names the cause, because a scrub that silently does nothing is the exact false
green this section exists to prevent.

**Known open issue, not fixed, recorded in `TODO.md` (repo root) rather than
here:** `crew_py()` (`plugin/crew/hooks/scripts/_common.sh:38-43`) returns
the first of `python3`/`python`/`py` that `command -v` *resolves*, not the
first that actually *runs*. On Windows, `command -v python3` can resolve the
`WindowsApps` App Execution Alias stub, which opens the Microsoft Store and
produces no output — so a guard fed that stub sees an empty result and
stands down silently, on exactly the platform where a guard has already
shipped broken once before. `TODO.md` records this as reproduced (128→77
passed with the real interpreter removed from `PATH`) and gives the fix
shape (execute each candidate, don't just resolve it) for whoever picks it
up; it is out of scope here on the same "not introduced by this branch,
needs its own must-block regression case" grounds `TODO.md` itself gives.

## `crew_state.py` and this very directory

`plugin/crew/hooks/scripts/crew_state.py` is what reads `.crew/codemap/` and
turns it into `knowledge.subsystems` for the PM's SessionStart brief. This
matters directly to the writer of any codemap file, so it is recorded here
rather than assumed:

- `read_knowledge()` (`crew_state.py:399-428`) lists every file directly
  under `.crew/codemap/`. A file counts as a subsystem if its name ends in
  `.md` **and** is not in `_NOT_SUBSYSTEMS`
  (`crew_state.py:225`: `frozenset({"INDEX.md", "UPGRADE.md", "MIGRATION.md"})`).
  This codemap therefore contributes 4 subsystems: `marketplace-registration.md`,
  `localgpu.md`, `crew.md` (this file), `verification-harness.md`. `INDEX.md`
  is deliberately excluded by name.
- Each counted file is checked for an anchor line matching
  `_ANCHOR_RE` (`crew_state.py:220-222`):
  `^anchor:\s*(?:\S*@)?([0-9a-f]{7,40})\s*$`, case-insensitive, matched
  anywhere in the file (`re.MULTILINE`). If the captured hash's first 7 chars
  do not equal the current HEAD's first 7 chars, the file's stem is added to
  `knowledge.behind` — surfaced later as the `knowledgeBehind` trigger
  (`crew_state.py:2015`). Every file in this codemap opens with
  `anchor: useful-claude-add-ons@<short-hash>` for exactly this reason. **The
  line numbers in this section moved by roughly +900 between the old anchor
  and this one** because `crew_state.py` grew that much (see above) —
  reconfirmed against the current file rather than carried forward from the
  previous refresh, which is exactly the kind of citation that silently rots
  when a file this central gets a 900-line change.
- `diagramsMissing` only fires once `knowledge.subsystems` is truthy
  (`crew_state.py:2017-2022`, comment: *"A repo with no codemap has not
  decided what its subsystems ARE yet"*) — so writing this codemap is also
  what turns on the future nag for missing per-subsystem diagrams. That is a
  second-order effect of this task worth naming, not something this task
  was asked to act on.

## What this file does not cover

Agent role definitions, command bodies, and the config precedence for which
model backs each role (`dev.roles`, `dev.provider`, `dev.fallback` —
referenced by the harness that dispatched this very task) were not traced
here; the brief scoped this codemap to marketplace/registration, `localgpu`,
`crew`, and the verification harness at the level of "what subsystems exist
and how they're wired," not a full per-agent reference. `crew:reference` or
`crew:roster` are the existing tools for that finer grain and were not
re-derived here.

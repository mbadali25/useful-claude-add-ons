# Design: crew Project Manager, graph-backed onboarding, and v1 upgrade path

date: 2026-08-24
branch: `feat/crew-plugin`
plugin: `plugin/crew` (0.2.0 -> 0.3.0)

## Problem

Three complaints, plus one consequence of fixing them.

1. **No manager.** The crew has nine specialist agents and no coordinator. The
   user believes one exists; it does not. `agents/planner.md` is the closest
   name and the furthest thing from it — a second-opinion design consultant
   explicitly forbidden from reading the codebase ("You work from a **brief**,
   not from the codebase"). Nothing in the plugin holds crew state, notices the
   map has rotted, or knows a role should be added or dropped.

2. **Nothing speaks at session start.** `hooks/scripts/handoff-read.sh:11`
   filters `case "$SOURCE" in clear|compact|resume)`. The `startup` source is
   dropped, so on a fresh session crew is silent. This is the literal cause of
   "doesn't load unless I tell it to."

3. **`find-skills` competes with crew's own skills.** Three copies exist —
   global `~/.claude/skills/`, project `.claude/skills/`, and vendored
   `plugin/crew/skills/`. The plugin's own `skills/find-skills/BUNDLING-NOTE.md`
   diagnoses the cause as description breadth ("asks how do I do X" is close to
   any question), not duplication. Deduplication alone does not fix it.

4. **Existing setups must not be stranded.** Any repo already carrying a
   hand-built `.crew/codemap/` predates all of the above. `.crew/config.json`
   has no version field, so there is currently no way to even detect one.

## Non-goals

- Making the PM a subagent that "loads automatically". Agents in `agents/*.md`
  run only when something calls the Agent tool. There is no auto-load. Any
  design that relies on one is the bug being fixed.
- Broadening any skill description to make it fire more often. That is problem 3.
- Vendoring graphify. It is a PyPI package (`graphifyy`, double-y, CLI
  `graphify`), not a plugin, and cannot go in `marketplace.json`.
- Replacing the codemap with the graph. An AST parser cannot produce
  `## Landmines`.

## Decisions taken

| Decision | Choice | Why |
|---|---|---|
| PM mechanism | SessionStart brief + narrow skill + `crew:pm` agent | Only SessionStart stdout and `CLAUDE.md` fire with no user turn |
| Brief size | Adaptive | Quiet when healthy, expands only on a finding |
| PM authority | Report and recommend only | Matches `/crew:scale`'s existing "Add nothing without asking" |
| Obsidian target | Subfolder of the existing vault, **gated on explicit approval** | User asked to be consulted before anything writes there |
| graphify seam | New `crew-graph` skill; `/crew:onboard` consumes it | Graph gives mechanics; explorers give judgment |
| find-skills | Narrow the vendored description; detect-and-offer for the global copy | Fixes the actual cause, does not delete user config silently |
| Upgrade command name | `/crew:upgrade`, not `/crew:migrate` | "migration" already means database migrations here — `agents/dba.md`, and `scripts/detect.sh:21` greps for migration directories |
| Sequencing | A–E in one plan | User choice; E included in full |
| Review | Codex reviews and QAs every change before merge | User requirement; `codex-cli 0.146.0` verified present |
| Delivery | PR from `feat/crew-plugin`, merged to `main` after QA | User instruction — see "Delivery" below for what that merge actually includes |

---

## A. The Project Manager

Four components. The brains live in injected context; the muscle lives in an
agent.

### A1. `hooks/scripts/pm-brief.sh` + `pm-brief.ps1`

New SessionStart hook, **both flavours wired in `hooks.json`**. Fires on every
source including `startup` — unlike `handoff-read`, which keeps its existing
`clear|compact|resume` filter. Both hooks run; they are separate entries and
compose. `pm-brief` runs second so the handoff appears above the state summary.

Reads, all optional and all failing soft to silence:

- `.crew/config.json` — `tier`, `roles`, `tracker`, `schema`, `pm`, `graph`
- `.crew/metrics.md` — BLOCK+FIX counts over the last 10 tickets
- `.work/INDEX.md` — the open ticket
- `.work/HANDOFF.md` — presence only; `handoff-read` prints the content
- `.crew/codemap/INDEX.md` — subsystem list and `anchor:` shas
- `graphify-out/graph.json` — mtime and the commit it was built at

**Adaptive output.** Quiet mode is the default and caps at
`pm.quietLines` (8):

```
## crew — tier 1, 4 roles, tracker files
health: 0.8 BLOCK+FIX per ticket (last 10) — healthy
work: T-0042 in progress, no handoff pending
knowledge: 6 subsystems mapped, all anchors current; graph built at a1b2c3d (HEAD)
```

Expanded mode triggers when any of these is true:

| Trigger | Condition |
|---|---|
| Upgrade needed | `schema` absent or `< 2` |
| Stale knowledge | any codemap `anchor:` behind HEAD for its own paths |
| Graph stale or absent | `graph.json` missing, or the sha it was built at is not HEAD |
| Review not working | BLOCK+FIX per ticket `< 0.3` |
| Tickets too big | BLOCK+FIX per ticket `> 2.0` |
| Handoff pending | `.work/HANDOFF.md` exists |

Expanded mode adds, per fired trigger, the finding and **one** concrete next
action, plus the PM's standing rules (report-only; ask before any role, tier, or
deletion change). Hard cap `pm.maxLines` (40) even fully expanded; on overflow it
truncates to a pointer at `/crew:pm`.

**Framing.** Plain text, phrased as project information rather than as
instructions, exactly as `handoff-read.sh:18-20` already documents. Text framed
as out-of-band commands trips prompt-injection defences and gets surfaced to the
user instead of treated as context.

**Loop safety.** Nudges that would otherwise repeat every session write a
once-per-session marker under `.crew/`, cleared on the next SessionStart — the
same gate `context-watch.sh` uses via `.crew/.handoff-requested`. A SessionStart
hook cannot trap a session the way a `Stop` hook returning exit 2 can, but
repeating an identical nudge every session trains the user to ignore it.

**Cost.** This runs on every session in every crew repo. Quiet mode must stay
under ~120 tokens. If it cannot, the feature is a context tax and the cap wins
over the content.

### A2. `skills/crew-pm/SKILL.md`

Narrow description. It names the manager's own vocabulary — onboard a repo,
onboard a role, offboard a role, crew status, who should be on this crew, is the
crew the right size, session is filling up — and explicitly not general "how do
I" phrasing. Broadening this to make it fire more often would reproduce
problem 3.

Owns:

- Reading and explaining crew state (the same inputs the hook reads, in depth)
- **Onboarding**: a new repo (delegates to `crew-setup`), or a new role
- **Offboarding**: removing a role — new capability, see A4
- Session-context management, delegating to `crew-context`
- When to escalate to `/crew:scale` rather than deciding alone

Deep procedures go in sidecar files (`onboarding.md`, `offboarding.md`) loaded on
demand, per `Skill-Authoring-Standard.md`.

### A3. `agents/pm.md` (`crew:pm`)

For analysis that should not burn main-session context: correlating defect
classes across the full metrics history, auditing every codemap anchor,
proposing a tier change with the numbers behind it.

`tools: Read, Grep, Glob, Bash`. Writes only under `.crew/`. `model: inherit`.
Returns a report under 200 words plus a recommendation — never an applied change,
per the report-only decision.

### A4. `commands/pm.md` (`/crew:pm`)

- `/crew:pm` — full state report and recommendations
- `/crew:pm onboard <role>` — add a role, with its cost stated
- `/crew:pm offboard <role>` — **new capability**

`/crew:scale` today only adds. Offboarding must: remove the role from
`config.json.roles`, recompute `tier`, record the removal and its reason in
`.crew/metrics.md`, clean role-specific artifacts, and state plainly which
failure mode is now uncovered. A role removed without naming what it was
catching is a silent coverage regression.

### A5. `config.json` additions

```json
"schema": 2,
"pm": {
  "enabled": true,
  "mode": "adaptive",
  "quietLines": 8,
  "maxLines": 40,
  "authority": "report-only"
}
```

---

## B. find-skills

Three separate deliverables; only the first changes shipped behaviour.

1. **Narrow the vendored description.** Apply the replacement `description:`
   line already written in `skills/find-skills/BUNDLING-NOTE.md:30` to
   `plugin/crew/skills/find-skills/SKILL.md`. Update the note to record that it
   has been applied, so the next reader does not apply it twice or assume it is
   still open.

2. **Detect and offer, in `crew-setup` and both install scripts.** A global
   `~/.claude/skills/find-skills/` is reported with what it is, why it collides,
   and an offer to remove it. Never a silent deletion — it is the user's own
   global config, and a bootstrap script that quietly deletes from `~/.claude`
   is worse than the collision it fixes.

3. **This machine.** Remove `~/.claude/skills/find-skills/` after showing its
   contents. Confirmed present alongside the project and vendored copies.

Out of scope by explicit choice: `.claude/skills/find-skills/` in this
repository stays. It carries the same broad description and will keep competing
inside this repo; that is a known, accepted condition rather than an oversight.

---

## C. graphify and Obsidian

### C1. `skills/crew-graph/SKILL.md`

Owns graphify end to end.

**Install detection.** `command -v graphify`. If absent, the install line is
`uv tool install graphifyy` — note the double-y package name against the CLI
name `graphify`; other `graphify*` packages on PyPI are unaffiliated. Never
auto-install; report and offer.

**Build.** Default `graphify . --no-viz`, code-only. Code corpora need **no API
key**; docs, PDFs, and images require an LLM call, so they are opt-in and the
key requirement is stated at the point of choice. `--no-viz` by default because
the HTML is unopenable past ~5000 nodes and is not what an agent consumes.

**Query.** `graphify query`, `graphify path`, `graphify explain`. The MCP server
(`python -m graphify.serve`) is documented as optional for repeated tool-call
access, off by default — it is another always-on surface and should be a
deliberate choice.

**Freshness.** `graphify hook install` rebuilds the graph on every git commit
and installs a union merge driver for `graph.json`. This is the mechanism that
addresses the rot problem `commands/onboard.md` already worries about, and the
merge driver is why `graph.json` is **committed** rather than ignored.
`.gitignore` gets the HTML, the wiki, and any vault export.

**Obsidian — hard gate.** `--obsidian --obsidian-dir`. Target is
`<vault>/codegraphs/<repo>/`, default vault `C:\repos\claude-memories`.

Two conditions, both required before anything writes there:

1. `graph.obsidian.confirmed` is `true` in `.crew/config.json`, set only by
   explicit in-session user approval. Absent or false, the skill refuses and
   asks.
2. The first export in any environment runs against a scratch directory and its
   effect is inspected. Upstream documents that `--obsidian-dir` never
   overwrites your own notes or `.obsidian` config; that claim is verified once
   rather than trusted against a vault the user cares about.

### C2. `/crew:onboard` rewrite

Order changes; the artifacts do not.

1. Build or refresh the graph (`crew-graph`).
2. Derive the subsystem list from the graph's detected communities rather than
   guessing. Keeps the existing cap of 6 per run.
   *Implementation note: the exact community key in `graph.json` is unverified —
   read the file before relying on a field name.*
3. Fill the mechanical sections from the graph: `## Entry points`,
   `## Owns data`, `## Calls out to`.
4. Spawn `crew:explorer` **only** for the judgment sections — `## Does`,
   `## Landmines`, `## Unverified`. This is where the cost reduction comes from:
   explorers stop re-deriving what an AST parser already knows.
5. Anchor-sha freshness rule unchanged. A graph rots the same way a map does.

`/crew:onboard --refresh <subsystem>` routes through the same reconciliation
code path as `/crew:upgrade` (section D) rather than duplicating the logic.

### C3. `graph` config block

```json
"graph": {
  "enabled": true,
  "tool": "graphify",
  "out": "graphify-out",
  "mode": "code-only",
  "commitHook": false,
  "obsidian": { "enabled": false, "dir": null, "confirmed": false }
}
```

---

## D. `/crew:upgrade` — the v1 backfill

For any repo whose `.crew/` predates this change. Idempotent, detect-then-act,
matching the repo convention that a step reports "already done" rather than
redoing itself.

**Detection.** `.crew/config.json` with no `schema` key is v1. `schema: 2` is
current; `/crew:upgrade` on a current repo reports and exits unless `--force`.

**Steps.**

1. **Back up.** Copy `.crew/codemap/` to `.crew/codemap.v1.bak/` before touching
   anything. Nothing else in the command is destructive, but the backup is what
   makes that claim cheap to verify.

2. **Config.** Add the `pm` and `graph` blocks with defaults, set `schema: 2`.
   Preserve every existing key including unrecognised ones — a config written by
   a newer crew than the one running must not be silently pruned.

3. **Build the graph** if absent, code-only, keyless.

4. **Reconcile each `.crew/codemap/<subsystem>.md`:**

   | Section | Treatment |
   |---|---|
   | `## Does` | Keep verbatim — human judgment |
   | `## Entry points` | Re-derive from graph |
   | `## Owns data` | Re-derive from graph |
   | `## Calls out to` | Re-derive from graph |
   | `## Landmines` | Keep verbatim, never touched |
   | `## Unverified` | Keep; entries the graph now answers move to a review list rather than being deleted |

   Re-derivation **adds and reports**; it does not overwrite a contradiction. A
   v1 claim the graph disagrees with is preserved and flagged, because the graph
   can be wrong too (generated call sites, reflection, dynamic dispatch).

5. **Anchors.** Bump `anchor:` only on sections actually re-verified this run. A
   section left alone keeps its old anchor. Claiming false freshness is strictly
   worse than admitting staleness — the whole freshness rule depends on the
   anchor being honest.

6. **Report** to `.crew/codemap/UPGRADE.md`, for human review, never
   auto-applied:

   ```
   # Upgrade report
   upgraded: <iso timestamp>
   from schema: 1 -> 2
   graph: <sha>

   ## Contradictions — v1 map disagrees with the graph
   - <subsystem> / <section>: map says X, graph says Y — <file:line>

   ## Added by the graph
   - <subsystem>: <n> entry points the v1 map did not list

   ## Communities with no map file
   - <community> — run /crew:onboard --refresh

   ## Resolved from Unverified
   - <subsystem>: "<old unverified claim>" — graph confirms/denies

   ## Still needs a human
   - <missing .crew/verify.json | .crew/secrets.md | e2e/>
   ```

7. **Report missing executables.** `commands/onboard.md` already argues a
   codemap alone is the least useful of its four artifacts; the upgrade says
   which of `verify.json`, `secrets.md`, and `e2e/` are absent.

**PM integration.** The `schema` check is one of the expanded-brief triggers
(A1), so a v1 repo is told to upgrade at session start without the user
remembering to ask. That coupling is the point of doing A and D together.

---

## E. Windows hook parity — separable

Not requested; surfaced while editing `hooks.json`. Cut this without affecting
A–D.

Current state against the repo's own rule ("Ship every hook script in both
flavours ... and **wire both in `hooks.json`**"):

| Script | On disk | Wired |
|---|---|---|
| `guard.ps1` | yes | yes |
| `context-watch.ps1` | yes | **no** |
| `handoff-read.ps1` | yes | **no** |
| `verify-gate.ps1` | yes | **no** |
| `handoff-write.ps1` | **no** | no |
| `notify.ps1` | **no** | no |

Three `.ps1` files are dead code by that rule. On this machine the `.sh`
versions do run — Git Bash and `python3` are both present and verified — but
that is luck, not design; a Windows box without a POSIX layer gets a silently
inert verify gate, which reads as "the gate passed" rather than "the gate never
ran".

Proposed: wire the three existing `.ps1` files, and write `handoff-write.ps1`
and `notify.ps1`.

---

## Testing

No test harness exists for the plugin's shell scripts; `.github/workflows/pylint.yml`
covers Python only. Verification is therefore behavioural and must be done, not
asserted:

1. **Hooks, both shells.** Feed `pm-brief.sh` and `pm-brief.ps1` a synthetic
   SessionStart JSON payload on stdin for each source (`startup`, `clear`,
   `compact`, `resume`) and confirm identical output between the two.
2. **Fail-soft.** Run both against: no `.crew/`, empty `config.json`, malformed
   JSON, missing `metrics.md`. Every case must exit 0 and print nothing. A
   SessionStart hook that errors on a non-crew repo breaks every session in it.
3. **Line caps.** Assert quiet output is `<= quietLines` and expanded output is
   `<= maxLines` with every trigger fired at once.
4. **Adaptive triggers.** One fixture repo per trigger; confirm each fires
   alone and that a healthy repo stays quiet.
5. **Upgrade, on a copy.** Build a v1 fixture (`config.json` with no `schema`,
   a hand-written codemap with known-wrong `## Calls out to`). Confirm:
   `Landmines` verbatim, the contradiction reported in `UPGRADE.md` rather than
   overwritten, the untouched section's anchor unchanged, `schema: 2` written,
   unknown config keys preserved, and a second run reporting "already current".
6. **graphify.** Verify against this repository, code-only, keyless. Confirm
   `graph.json` exists and `graphify query` answers before wiring onboard to it.
7. **Obsidian.** Scratch directory first. Inspect what appeared and what did not
   change. Only then ask about `claude-memories`.
8. **find-skills.** Narrow the description, restart a session, confirm crew
   skills still fire on their own phrasing.

## Documentation

Mandated by `CLAUDE.md` and part of the work, not a follow-up:

- `.claude-plugin/marketplace.json` — crew 0.2.0 -> 0.3.0
- `plugin/README.md` — row updated
- `plugin/PLUGINS.md` — full component breakdown: `/crew:pm`, `/crew:upgrade`,
  `crew:pm` agent, `crew-pm` and `crew-graph` skills, the `pm-brief` hook, and
  what starts running the moment the plugin is enabled
- `README.md` — same row inside the `<!-- BEGIN plugin/README.md -->` block,
  plus any count that appears as a number
- `scripts/install-prerequisites.sh` and `.ps1` — graphify item and the
  find-skills detection, as a **matched pair**: identical menu keys, order, and
  default flags, or `--select` means different things per platform
- `README.md` menu table, "What each item actually installs" table, switch table
- `INSTALLATION.md`
- `CHANGELOG.md`
- `plugin/crew/README.md` — the plugin's own documentation

Re-pin both one-liner install URLs to a fresh SHA after this merges to `main`.

## Delivery

Sections A–E ship as one plan. Codex reviews and QAs every change before the PR
merges; `codex-cli 0.146.0` is present.

**What the merge actually includes — read this before approving it.**
`feat/crew-plugin` is **28 commits and 96 files** ahead of `main`, with no
divergence in the other direction (nothing to rebase). The work in this spec is a
fraction of that. Merging the PR also ships, for the first time:

- `plugin/crew/` — the entire plugin, currently unreviewed and unmerged
- `claude-obsidian-setup/` — Obsidian bootstrap scripts
- `vault-automation/` — vault capture and gardener automation
- `.claude/skills/find-skills/` — the project-scoped copy discussed in section B
- install-script and documentation changes already on the branch

So "merge after QA" means QA covers the branch, not only the new work. Codex
reviews this spec's changes closely and the pre-existing branch content at least
well enough to say whether it should ship — if that second part turns up
something significant, it gets raised rather than merged past.

Post-merge, required by `CLAUDE.md`: `git rev-parse HEAD` on `main` and re-pin
both one-liner install URLs in `README.md`, because the install scripts change in
sections B and C.

## Risks

| Risk | Mitigation |
|---|---|
| The brief becomes a context tax | Hard line caps; quiet mode is the default and the common case |
| `crew-pm` gets broadened later to fire more often | The spec and the skill both record why it is narrow; this is problem 3 recurring |
| The graph is trusted over the code | Anchors and the freshness rule stay; contradictions are reported, never auto-applied |
| Obsidian export damages the vault | Scratch-dir proof plus an explicit `confirmed` gate |
| Upgrade loses hand-written judgment | `Landmines`/`Does` verbatim; full backup before any write |
| Two knowledge systems drift | `graphify hook install` rebuilds on commit; anchors catch the map |
| Hook depends on `python3` | Already true of existing hooks; verified present. Fail-soft to silence, never to error |

# repo-docs
anchor: useful-claude-add-ons@8cabe586
verified: 2026-09-27

## Re-derive provenance

Re-derived from source at `6c497a14` (crew 1.0.25, PR #225), not re-pointed
from the previous `5d1fc5fd` anchor. Every claim below was read directly
against the committed file at HEAD.

Per-path check against this note's previous 32-path tracked pathspec (the
list its own last provenance section enumerates):

```
git diff --name-only 5d1fc5fd..6c497a14 -- .crew/verify.json CHANGELOG.md \
  INSTALLATION.md README.md TODO.md docs/diagrams/data-flow-crew-config.mmd \
  docs/diagrams/process-crew-brief.mmd docs/remaining-setup.md plugin/PLUGINS.md \
  plugin/README.md plugin/crew/README.md plugin/crew/agents/scribe.md \
  plugin/crew/hooks/scripts/_test/run-tests.sh plugin/crew/hooks/scripts/crew_state.py \
  scripts/check-marketplace.py skills/README.md CLAUDE.md docs/HANDOFF.md \
  docs/adr/0001-promote-stays-unarmed.md docs/diagrams/architecture.mmd \
  docs/guides/Running-a-Mailbox-Job.json docs/runbooks/rollback.md \
  plugin/crew/commands/handoff.md plugin/crew/hooks/scripts/crew_freshness.py \
  plugin/crew/skills/crew-context/SKILL.md plugin/crew/skills/crew-diagrams/SKILL.md \
  plugin/crew/skills/crew-diagrams/scripts/_test/render.sh \
  plugin/crew/skills/crew-diagrams/scripts/render.sh plugin/crew/skills/crew-docs/SKILL.md \
  plugin/crew/skills/crew-runbooks/SKILL.md scripts/_test/self-claims.py scripts/sync-updates.py
```

**Two of the 32 tracked paths no longer exist**, checked individually with
`git cat-file -e 6c497a14:<path>`: `plugin/crew/agents/scribe.md` (the crew
1.0 roster cut — see `install-scripts.md` — removed the `scribe` agent along
with the PM, and `pm-brief`/`crew-scaling`; the four surviving agents are
`explorer`, `researcher`, `reviewer`, `security`) and
`docs/guides/Running-a-Mailbox-Job.json` (moved by a `git mv`, still tracked
under its PR #215 destination,
`docs/guides/exchange-mailbox/Running-a-Mailbox-Job.json` — this note's own
previous version already carried that move as a header note; it is repeated
here rather than re-discovered). Of the remaining **30** existing paths,
**21 changed, 9 did not**:

```
git diff --name-only 5d1fc5fd..6c497a14 -- <the 30 existing paths>
```
```
.crew/verify.json
CHANGELOG.md
INSTALLATION.md
README.md
TODO.md
docs/diagrams/data-flow-crew-config.mmd
docs/diagrams/process-crew-brief.mmd
docs/runbooks/rollback.md
plugin/PLUGINS.md
plugin/README.md
plugin/crew/README.md
plugin/crew/hooks/scripts/_test/run-tests.sh
plugin/crew/hooks/scripts/crew_freshness.py
plugin/crew/hooks/scripts/crew_state.py
plugin/crew/skills/crew-context/SKILL.md
plugin/crew/skills/crew-diagrams/SKILL.md
plugin/crew/skills/crew-diagrams/scripts/_test/render.sh
plugin/crew/skills/crew-docs/SKILL.md
scripts/_test/self-claims.py
scripts/check-marketplace.py
skills/README.md
```

Unchanged, and closed by that result (9 of the 30 existing paths):
`docs/remaining-setup.md`, `plugin/crew/commands/handoff.md`,
`docs/adr/0001-promote-stays-unarmed.md`, `docs/diagrams/architecture.mmd`,
`docs/HANDOFF.md`, `plugin/crew/skills/crew-diagrams/scripts/render.sh` (the
render script itself, as opposed to its `_test/` sibling, which did change),
`plugin/crew/skills/crew-runbooks/SKILL.md`, `scripts/sync-updates.py`.
`docs/runbooks/rollback.md` is in the 21-changed set, not this list; its
only change is a path-rename fix (see Landmines). **`README.md` is also in
the 21-changed set, and its own change history inside this range matters
more than the fact of the diff** — see the install-URL-pin landmine below:
it was re-pinned and had its counts corrected early in this range (the very
next commit after the previous anchor), then left untouched through the
rest of the range's much larger script changes, which is what makes its pin
stale again at `6c497a14` despite the file having changed at all.

**This note was told, before this pass, to expect "21 of 31 moved, 8 gone."**
The "21 moved" figure matches exactly what the command above measured (21 of
30 existing paths, or 21 of 32 total if the denominator counts differently).
The "8 gone" figure does not: this pass found exactly **2** tracked paths
that no longer exist, not 8, checked individually rather than assumed. That
gap is not resolved here — every file this note cites was confirmed to exist
or not, one at a time, and the result is 2. See "Unverified" for what a
count of 8 could still mean that this pass did not check (a stricter
per-construct definition of "gone," rather than file-existence).

## Does
Holds the repo's hand-written documentation — Mermaid diagram sources under
`docs/diagrams/`, planning artifacts under `docs/superpowers/`, review notes
under `docs/review/`, ADRs under `docs/adr/` (three, unchanged from the
previous anchor), rendered per-topic guides under `docs/guides/*/` (see
below — restructured in this range), one operational runbook, handoff notes,
and the top-level `CHANGELOG.md`. Nothing under `docs/` is generated except
the rendered diagram images (`docs/diagrams/out/`) and the rendered guide
documents under `docs/guides/*/*.{html,docx,pdf}` (see below). JUDGEMENT,
unchanged: "prose is never auto-refreshed" is inferred from there being no
writer, not stated as a rule.

**`docs/guides/` is now organised by subject, one directory per plugin/skill,
each with a `src/` of Markdown sources and a `build.py`.** DERIVED:
`docs/guides/crew/`, `docs/guides/gizmoduck/`, `docs/guides/obsidian/`,
`docs/guides/rule-of-two/` and `docs/guides/exchange-mailbox/` each hold
rendered `.html`/`.docx`/`.pdf` guides at the top of the directory;
`docs/guides/crew/src/` holds the Markdown sources (`quickstart.md`,
`daily-workflow.md`, `troubleshooting.md`, `working-with-codex.md`,
`memory-and-obsidian.md`, plus two non-published planning files,
`daily-workflow-scope.md` and `memory-recall-proof.md`) and
`docs/guides/crew/src/build.py`, the generator; `docs/guides/crew/archive/`
holds superseded dated reports. Not read for build.py's own mechanism at this
pass — flagged in Unverified. This is new since `5d1fc5fd`, but none of the
`docs/guides/*` paths were in this note's previous tracked pathspec, so no
per-path check closes or opens this claim; it is a fresh observation from
listing the directory.

## Entry points

- `docs/diagrams/architecture.mmd:1-2`, `data-flow.mmd:1-2`, `process.mmd:1-2`
  — still the `%% anchor: useful-claude-add-ons@1f97e51c` / `%% Anchors: ...`
  form, still well behind `6c497a14` (re-read directly, unchanged from the
  previous anchor — `docs/diagrams/architecture.mmd` is confirmed unchanged
  by the per-path check; the other two are not in this note's tracked
  pathspec, so their unchanged status is read directly rather than closed by
  diff). Both provenance shapes are still accepted by `_DIAGRAM_ANCHOR_RE`.
- `docs/diagrams/data-flow-crew-config.mmd:1-2`, `process-crew-brief.mmd:1`
  and `process-crew-lifecycle.mmd:1` - the three crew diagrams, each on the
  `%% Generated from <repo>@<sha> on <date>.` form, all at `d276b268` after
  T-0021 (which added `crew_tracker.py` to each one's `%% Anchors:` line and
  drew the tracker calls into the lifecycle). `data-flow-crew-config` was redrawn for crew 1.0 at `6c497a14`
  (`5e937837`, the refresh branch) and re-anchored, its `%% Anchors:` paths
  unchanged in `6c497a14..f2bb919b`. `process-crew-brief` was **redrawn**:
  at `6c497a14` it still drew the 0.20 PM brief through `pm_brief.py` /
  `pm-brief.sh`, both deleted in 1.0, and now draws the three SessionStart
  hooks and `/crew:status`. `process-crew-lifecycle` is **new**: brainstorm ->
  spec -> plan -> approve -> implement -> review -> done, drawn from
  `plugin/crew/commands/`. `process-bitbucket-svg.mmd` stays at `60c79407`;
  its `%% Anchors:` paths are all under `skills/mermaid-svg-bitbucket/`,
  untouched since. Both provenance shapes are still accepted by
  `_DIAGRAM_ANCHOR_RE`.
- `plugin/crew/skills/crew-diagrams/scripts/render.sh:74-75` — unchanged
  (closed by the per-path check): `shopt -s nullglob; FILES=("$DIR"/*.mmd)`,
  a glob over the whole directory. `git ls-files docs/diagrams/` returns
  **seven** `.mmd` sources after T-0015 (six at `6c497a14`; the new one is
  `process-crew-lifecycle.mmd`).
- `scripts/sync-updates.py:147` — module entry point (`main()`), unchanged
  file, closed by the per-path check, position not re-read.

## Owns data

- `docs/diagrams/out/*.svg`/`*.png` — six names × two formats at `6c497a14`,
  seven names once `render.sh` is re-run after T-0015 (not re-rendered by it;
  `out/` is machine-local), produced by `render.sh`. Unchanged file, closed by the per-path check;
  `docs/diagrams/out/` is still gitignored (`.gitignore`, not re-read this
  pass, previously confirmed at `:409` and not itself a tracked path here).
- `docs/superpowers/` — `plans/` and `specs/`, hand-written. Unchanged,
  confirmed present, not re-counted file by file.
- `docs/review/` — nine files (`01-field-comparison-and-pain-points.md`
  through `07-web-testing-research.md`, plus `README.md` and `04a`/`04b`/`04c`
  sub-documents) recording the crew 1.0 redesign's own review process:
  field comparison, memory/injection design, a Codex review round, the
  redesign proposal and three independent cross-reviews of it, a setup audit,
  and web-testing research. Not in this note's previous tracked pathspec —
  newly observed by listing the directory, not diffed against the old
  anchor. **These are themselves a record of decisions made during the crew
  1.0 redesign** (e.g. `docs/review/04c-cross-reviews.md`'s "Obsidian
  retirement" row, disputing and then resolving what to retire from the
  marketplace) — worth flagging back for `crew:scribe`: several read like
  ADR material that was never filed as one. Not read beyond their titles and
  the one quoted row above; see Unverified.
- **The self-stated skill/hook/agent counts are now internally consistent
  everywhere this note checked, for the first time across this note's
  history.** `README.md:46`/`:154` (`<!-- claim: skills-count -->`) states
  **34** skills; `python3 scripts/check-marketplace.py` confirms `marketplace:
  34 skills, 5 plugins / all checks passed`. `plugin/README.md:414`'s crew row
  (`<!-- claim: plugin-skills:crew -->`), `plugin/PLUGINS.md:17`, the
  `.claude-plugin/marketplace.json` `crew` description, and both install
  scripts' `PLUGIN_NAME` crew rows all read **4 agents, 36 commands, 29
  skills, 34 hook entries (13 scripts × `.sh`/`.ps1`) across 8 events** at
  `e95e5964` (34 commands until T-0004 added `commands/autopilot.md`, 35
  until T-0075 added `commands/config-setup.md`; every site listed here was
  bumped in `ecf69e43` and again in `a77a42d6`, and `README.md:168`/`:874`
  carry the same 36) —
  independently re-derived from the filesystem (`ls plugin/crew/agents/*.md`
  = 4, `commands/*.md` = 36, `skills/*/` = 29) and from `hooks.json` (parsed
  with `json.load`: 34 entries, 8 distinct event names, 26 unique `command`
  strings), not cross-quoted from any one of the docs. This is the same
  five/six-site figure this note's previous anchors repeatedly found
  disagreeing (see `install-scripts.md`'s "Corrected at this anchor"
  history); at `6c497a14` it does not disagree anywhere this note checked.
  **At `07ca3972` one site disagrees again:** `INSTALLATION.md:252` (a file
  unchanged since `a0c0847e`) still reads "34 slash commands" for crew. Its
  `<!-- claim: plugin-skills:crew -->` marker binds the skills figure (29,
  correct), not the command count, so `check_self_claims` does not catch it.
- `SKILL_KEYS` dropped **36 -> 34**: `claude-memories-canvas` and
  `claude-memories-vault` removed from both install scripts' catalogs and
  from `skills/`. `skills/README.md` lost the two corresponding table rows in
  this range (confirmed by diff — pure deletions, not moves). `README.md:736`
  (outside this note's tracked pathspec, read directly) explains the
  replacement: `obsidian-vault`'s portable `obsidian-memory-contract`
  profiles.
- `skills/README.md:15` — `<!-- BEGIN skills/UPDATE.md -->` block, generated
  from `skills/UPDATE.md` by `scripts/sync-updates.py`, still reads "Nine new
  skills, taking the marketplace from 25 to 34" under an `### Unreleased`
  heading. This line was **not** touched by the diff in this range (the
  file's changes are the two row deletions above) — it predates `5d1fc5fd`
  and this note has not previously flagged it. Carries no `claim:` marker, so
  `check_self_claims` does not see it. Not independently verified against
  git history whether "25 to 34" describes a real, still-open unreleased
  batch or is itself stale prose that should have been cut into a dated
  release note by now; flagged rather than asserted either way.

## Calls out to

- `mmdc` (mermaid-cli), at `render.sh:126`/`:133` — unchanged file, closed by
  the per-path check.
- `raw.githubusercontent.com` at the pinned sha — **see the Landmines entry
  below; the pin is stale at this anchor.**

## Landmines

- **`INSTALLATION.md`'s "Eight MCP servers" section describes a menu row that
  no longer exists, and this is new at this anchor — not carried forward
  from a previous pass.** `INSTALLATION.md:213-224` (under `### Optional: MCP
  servers`, `:211`) still reads: "Eight MCP servers are menu rows, all off by
  default" followed by bullets for AWS, Azure, **"Playwright — runs `claude
  mcp add playwright -- npx @playwright/mcp@latest`"**, AWS Knowledge, AWS
  Pricing, Microsoft Learn, the Obsidian vault server, and Perplexity. The
  `playwright-mcp` menu key that bullet describes was **removed** in this
  range — merged with the separate `playwright-cli` row into a single
  `web-testing` row (see `install-scripts.md`'s Landmines) that installs
  `@playwright/test`+`@axe-core/playwright` as project devDependencies (not
  a global MCP-only registration), requires Node >= 20.19, probes
  passwordless sudo before attempting `--with-deps`, scaffolds Playwright
  Test Agents for both `claude` and `codex` loops, and registers **two** MCP
  servers (`playwright` **and** `chrome-devtools`) at project scope with
  `--isolated --headless --caps testing` — none of which this passage
  mentions. **This section was NOT touched by the diff in this range** (the
  only change to `INSTALLATION.md` in the whole `5d1fc5fd..6c497a14` range is
  the crew agent/command count bump, confirmed by reading the full diff), so
  it is not merely lagging a recent edit — it has described a non-existent
  row since the row was removed. `grep -n "web-testing"` over
  `INSTALLATION.md` returns exactly one hit, at `:174`, which names the
  unrelated `web-testing-playwright` **skill** (a different thing — see
  `SKILL_KEYS` above), not this menu row. The "Eight" count is also now
  arguably wrong regardless of the Playwright bullet's content, since the
  live `MENU_KEYS` list carries ten single-MCP-server rows
  (`aws-mcp`, `azure-mcp`, `obsidian-mcp`, `supabase`, `context7`, `ms-mcp`,
  `aws-docs-mcp`, `aws-pricing-mcp`, `ms-learn-mcp`, `perplexity-mcp`) of
  which `supabase` and `context7` are explicitly described elsewhere in the
  same document as "None of them are MCP servers" (`:228`), and `ms-mcp` is
  covered under its own heading (`### Optional: Microsoft MCP servers`,
  `:305`) rather than folded into this bullet list — so the "eight" in this
  passage is doing real, narrower work than "every MCP-server-only row," but
  whatever that narrower rule is, it no longer includes an accurate
  description of the row occupying the position the old `playwright-mcp` row
  held. Not fixed here — outside this note's write scope; reported so the
  fix targets the right passage.

- **`README.md`'s install-URL pin is stale again at this anchor, as its
  history said it would be.** `README.md:12`/`:18` still read
  `6c497a14fc06612732241d2b13eee4fea41996f5` at `07ca3972` (re-read), set by
  #226 (`86931b29`); it was current through `a0c0847e`, but `git log
  --oneline 6c497a14..07ca3972 -- scripts/install-prerequisites.sh
  scripts/install-prerequisites.ps1` now returns `ecf69e43` (T-0004: the
  `PLUGIN_NAME`/`PluginCatalog` crew row, 34 -> 35 commands, in both scripts).
  Per CLAUDE.md the re-pin happens after that change merges to `main`, so
  this is expected on the branch, not a defect of it. At `6c497a14` this
  bullet recorded the pin at `5d1fc5fd8b08...`,
  current only for the moment after `7f83c812` re-pinned it and stale again
  once both install scripts kept changing through the rest of that range -
  the pattern's third or fourth documented recurrence. `install-scripts.md`
  owns the re-pin mechanics; re-run the `git log` above against the live
  HEAD rather than trusting "current".
  `docs/guides/exchange-mailbox/Running-a-Mailbox-Job.json:18` (the renamed
  destination of the site this note has tracked since discovering it) was
  **not** independently re-checked against the current pin at this pass —
  flagged in Unverified rather than repeated from the previous anchor's
  figure, which would now be wrong regardless (the reference point it was
  computed against, `d541ee57`, is itself several re-pins behind
  `5d1fc5fd`).

- **`docs/runbooks/rollback.md`'s only change in this range is a path-rename
  fix, and it is correct.** The diff is a single hunk: its "Find every
  tracked site" step now names
  `docs/guides/exchange-mailbox/Running-a-Mailbox-Job.json` instead of the
  pre-PR-#215 path. `docs/runbooks/rollback.md:3` still reads
  `last verified: 2026-09-05` — now **20 days** stale against this note's own
  `verified: 2026-09-25` date, and this note cannot refresh that date since
  it does not own the runbook.
- `docs/HANDOFF.md` — unchanged file, closed by the per-path check. Newest
  entry still dated 2026-08-23 — **33 days** behind this anchor's verified
  date (2026-09-25), up from 30 at the previous anchor. Re-measured each pass
  because the figure is stale the instant it is written.
- **`docs/runbooks/INDEX.md` still does not exist.** `docs/runbooks/`
  contains `rollback.md` alone (re-confirmed by `ls`).
  `plugin/crew/skills/crew-runbooks/SKILL.md:80` and
  `plugin/crew/README.md:2169` (on T-0075's merge of `d2fbd408`; `:2075` at `d2fbd408`, `:1812` on T-0024's branch at `45345812`, `:2161` on T-0075's branch at `763eaeff`, `:2127` at `764f6018`, `:2067` at `67caa4b8`, `:2102` on T-0075's `f7163410`, `:2052` at `bebbb97f`, `:2079` on T-0075's `e95e5964`, `:2044` on T-0018's first landing merge at `fbc27b49`, `:2029` at `db14619c`, `:1959` on T-0018's branch at `e6b696fb`, `:1953` at T-0023's `a1acd9b7`, `:2015` at T-0021's `74f52fae`, `:2006` at `c2ae46ab`, `:1944` at T-0042's `f0b12ee6`, `:1930` at `2b18f7ab`, `:1794` at T-0021's `bcb77ce2`, `:1804` at `07ca3972`, `:1759` at `a0c0847e`, `:1730` at `8ebbdedc`, `:1757` at T-0006's `2bb92f32`, `:1728` at `c35edda5`; on T-0005's branch `:1854` at `a26ad8c0`, `:1810` at `aa7f9841`, `:1795` at `1e210476`, `:1788` at `3a57b2d2`, `:1767` at `2170d72e`, `:1728` at `8d447a7d`; `:1725` at `f2bb919b`, `:1604` before that,
  that file having changed in each range — re-grepped, not offset) both still describe
  `docs/runbooks/INDEX.md` as a symptom-keyed index that would live there.
  JUDGEMENT, unchanged: costs nothing with one runbook, becomes a real gap at
  the second.

- **`/crew:handoff` still does not write `docs/HANDOFF.md`; unrelated to it.**
  `plugin/crew/commands/handoff.md:7` — the file changed for T-0006 and
  T-0042 below this line, `:7` re-read at `068db4ff` — still reads "Write `.work/HANDOFF.md` following the
  `crew-context` skill." `plugin/crew/skills/crew-context/SKILL.md:69` (moved
  from `:62` — the file changed substantially in this range, re-grepped: the
  session-start mechanism it describes was rewritten from `pm_brief`-driven
  to a plain context-hook injection, and the handoff-marker file is now
  keyed per session rather than per repository — see Unverified for what of
  that rewrite this note did and did not read) still says the same thing.
  `.crew/config.json` (machine-local, gitignored) is absent from this fresh
  worktree, so its `handoffPath` value could not be re-read here; the
  fallback default is confirmed instead, directly in code:
  `plugin/crew/hooks/scripts/crew_autocycle.py:180` returns
  `".work/HANDOFF.md"` when no config value is set. `docs/HANDOFF.md` is
  human-authored; the two files remain unrelated despite the shared
  basename.

- **`docs/adr/` still exists, unchanged in count (three) since it was first
  found.** `docs/adr/0001-promote-stays-unarmed.md` (unchanged, closed by the
  per-path check), `0002-no-chatgpt-mcp-server.md` (accepted 2026-09-14) and
  `0003-crew-departs-from-three-community-best-practices.md` (accepted
  2026-09-17) — the latter two were already present at the previous anchor
  and are not new in this range. `CLAUDE.md:147` still reads "Decisions in
  `docs/adr/`" at `adf8d1dd` (re-grepped; `CLAUDE.md` changed in
  `f2bb919b..adf8d1dd`, but only its `crew_freshness.py` line citations).
- **`docs/review/`'s existence is itself a mild instance of the same gap
  `docs/adr/` used to be.** Several of its documents record accepted
  decisions (see "Owns data" above) that were never promoted into a numbered
  ADR. JUDGEMENT: worth a line back to `crew:scribe`, not a fix made here —
  this note documents what the code/docs are, not what should be filed as a
  decision.

- **The diagram anchor-freshness mechanism is unchanged in logic, only in
  line numbers, confirmed by direct re-read rather than assumed.**
  `_DIAGRAM_ANCHOR_RE` now at `plugin/crew/hooks/scripts/crew_freshness.py:127`
  (was `:128-132`), `_DIAGRAM_ANCHORS_RE` at `:224`, `_diagram_paths` at
  `:273`, `read_diagrams` at `:472`, the `sha[:7] == head[:7]` comparisons at
  `:429` and `:512`, and the `_diagram_paths` call site inside `read_diagrams`
  at `:518` (was `:522`). Re-exported through
  `plugin/crew/hooks/scripts/crew_state.py:132`/`:136`/`:139`/`:142`
  (`_ANCHOR_RE`, `_DIAGRAM_ANCHOR_RE`, `_NOT_SUBSYSTEMS`, `_diagram_paths`).
  A diagram with no anchor header, or one whose anchor is old AND whose
  `%% Anchors:` paths have moved, still counts as `behind`; unknown still
  resolves to stale.

- **`TODO.md`'s `render.sh` entry is still open, still un-CLOSED, re-located
  rather than assumed at its old line.** Now at `TODO.md:1201` (`:1190` at
  `1e0706ac`, `:1122` at
  `f2bb919b`, `:1092` at `6c497a14`, `:1061` before that; the file grew 3645 -> 4714 lines, +1069,
  in the `5d1fc5fd..6c497a14` range, and 30 more lines landed after its
  `:16` by `f2bb919b`, and this note's own
  standing rule treats any `TODO.md` citation as provisional the moment the
  file is known to have grown). The heading, content (six-for-six failure on
  2026-09-05, the same three sources rendering cleanly when `mmdc` is invoked
  directly, the `cygpath -w` fix shape) and its still-missing `CLOSED` marker
  are all unchanged in substance — re-read directly, not diffed by offset.
  The fix has still landed in `render.sh` itself
  (`plugin/crew/skills/crew-diagrams/scripts/render.sh:93-99` for the
  `MSYS_NO_PATHCONV=1` diagnosis, `:100-104` for the `cygpath -w` branch) —
  that file is unchanged in this range, closed by the per-path check. The
  regression test for it moved: `plugin/crew/skills/crew-diagrams/scripts/
  _test/render.sh` grew 279 -> 283 lines in this range; its
  `MSYS_NO_PATHCONV=1` case is now at `:106`/`:108` (was `:104`/harness
  invocation).

- **`crew-docs/SKILL.md`'s CHANGELOG rule is unchanged; its surrounding
  prose lost every reference to retired roles.** The rule itself —
  "Behaviour users or callers can observe changed" gates a CHANGELOG entry,
  not a version bump — is still at `plugin/crew/skills/crew-docs/SKILL.md:26`
  (position unchanged despite the file being in this range's changed set;
  the edits landed nearby, not on this line). What changed around it: "the
  PM refreshes [diagrams] itself" -> "`/crew:diagram` refreshes [them]" (no
  PM role in the 1.0 roster), and "`/crew:work` step 12 asks this question"
  -> "`/crew:implement` asks this question" (both `/crew:work` and
  `/crew:ticket` are retired in 1.0, per this repo's own command listing —
  `/crew:spec` and `/crew:implement` replace them), and a reference to
  "`crew:docs-writer`" (a retired role) was removed. None of these were
  independently re-verified against `crew.md`'s command inventory at this
  pass — flagged in Unverified, since `crew.md` is the note that owns the
  command/role map.

- **`.crew/verify.json` changed substantively in this range, not merely in
  wording — corrected from what would otherwise be assumed by analogy to a
  previous pass's finding about a different range.** Two things read
  directly: the whole-suite timing rule was re-priced twice on 2026-09-24,
  from 185s (itself a five-run midpoint the file's own comment now says was
  "partial or otherwise not the full serial suite") to a measured
  full-serial 1928s, then re-priced again the same day to 377s on a
  documented host (Linux, 20 CPUs, lightly loaded); and one `paths` list lost
  `plugin/crew/hooks/scripts/pm_brief.py`, `pm_pulse.py` and
  `plugin/crew/tests/test_pm_brief.py` — the PM module and its test are
  gone, matching the roster cut. `.crew/verify.json` is on this repo's
  tracked allow-list (`.crew/*` is gitignored except `.crew/codemap/`,
  `.crew/endpoints.json` and `.crew/verify.json` — CLAUDE.md's own gitignore
  policy, not re-verified again at this pass) and is present in this fresh
  worktree. `verification-harness.md` owns this file's full contents; this
  note only records what changed in its own tracked citations. Since
  `6c497a14` one rule was appended (`:263` on the T-0005 landing merge, where T-0026's rule and
  T-0005's cloud-guard rule both sit above it; `:251` after T-0026 inserted a rule above it,
  `:256` after T-0005 did the same and Step 8 added a path; `:244` after T-0008's review round 3
  added a path above it; `:243` when #228 added it): `.claude/rules/**` and
  `.crew/codemap/**` now run `crew_instructions.py rules --root . --check`.
  Since `f2bb919b` another follows it (`:264-280`, T-0008): changes to
  `plugin/crew/hooks/scripts/crew_refresh_check.py`, its tests,
  `plugin/crew/commands/implement.md` or `plugin/crew/commands/done.md` -
  and since review round 3 `scope_guard.py`, `completion_audit.py`,
  `crew_freshness.py` and `scope_base.py` - run the three refresh-artifact
  pytest files plus `test_scope_guard.py`, `test_completion_audit.py` and
  `test_scope_base.py`. Since `c35edda5` a third was inserted mid-list
  (`:179-184` on the T-0005 landing merge, `:167-172` when T-0026 added it):
  `plugin/crew/hooks/scripts/crew_ticket.py` and
  `plugin/crew/tests/test_approval_digest.py` run that test file and
  `test_crew_ticket.py`. T-0005 inserted another mid-list (`:117-127`, the cloud-guard suites).
  Since `a0c0847e` T-0006's rule sits at `:282-292` (`:270-280` before T-0005 merged)
  and T-0004 appended a last one (`:293-301` since T-0018 widened it; `:293-300` on main before that,
  `:281-288` before T-0005 merged): `crew_autopilot.py`, `commands/autopilot.md`,
  `test_crew_autopilot.py`, `test_crew_autopilot_status.py` (T-0018) and
  `sabotage_autopilot.py` run `test_crew_autopilot.py`, `test_crew_autopilot_status.py` and
  `test_lifecycle_commands.py`. T-0021's merge of main put its rule after it
  (`:302-309` since T-0018 landed; `:301-308` before that, `:262-269` on its branch before the merge): `crew_tracker.py`,
  `test_crew_tracker.py`, `sabotage_tracker.py` and the board fixtures run
  `test_crew_tracker.py`. T-0023 appended rule 29 last (`:310-318` since T-0018 landed, `:309-317`
  before): `crew_route.py`, `crew_context.py`, their two test files and `sabotage_route.py` run
  `test_crew_route.py`, `test_crew_route_hook.py` and `test_crew_context.py`.
  T-0024 appended rule 30 last (`:320-327` since its landing merge; rule 27 at `:290-297` on its
  branch): `approval_hook.py`, both approval-hook wrappers, `crew_ticket.py`,
  `test_approval_hook.py`, `test_approval_group.py` and `sabotage_approval.py` run
  `test_approval_hook.py`, `test_approval_group.py` and `test_crew_ticket.py`. The rules above it
  did not move.

## Unverified

- **The "8 gone" figure this note was told to expect could not be
  reproduced.** This pass found 2 non-existent paths among the 32 previously
  tracked, checked by file existence. If "gone" means something narrower —
  e.g. a specific historical `path:line` citation whose *line* no longer
  contains the construct it once named, even though the file survives — that
  check was not performed exhaustively over every citation in the pre-1.0
  version of this note, only over the citations this rewrite makes fresh
  use of.
- `docs/guides/crew/src/build.py`'s actual rendering mechanism (how it
  produces `.html`/`.docx`/`.pdf` from the `src/` Markdown, and whether it
  relates to the `doc-builder` skill's own pipeline) was not read — only the
  directory structure was observed.
- `docs/review/*`'s nine documents were not read beyond their titles and the
  one quoted cross-review row; whether other rows record further
  never-filed decisions was not checked file by file.
- `CLAUDE.md` beyond its `:147` "Decisions in `docs/adr/`" line (re-confirmed
  at `adf8d1dd`) was not re-derived end to end; this note's business with it
  is narrow.
- `crew-docs/SKILL.md`'s retired-role references (`/crew:work`,
  `/crew:ticket`, `crew:docs-writer`) were read in this file alone, not
  cross-checked against `crew.md`'s own command/role inventory for
  consistency.
- Whether `render.sh` succeeds end to end on this machine was not tested;
  the committed regression test is evidence the `cygpath` path is exercised
  in principle, not that it passes here.
- `scripts/sync-updates.py`'s `splice` duplicate-marker guard (previously
  cited around `:114-125`) was not re-read at this pass; the file is
  unchanged, closed by the per-path check, so the previous anchor's reading
  is assumed rather than re-verified line by line.
- `docs/guides/exchange-mailbox/Running-a-Mailbox-Job.json:18`'s pinned sha
  was not re-read at this pass; this note does not repeat the previous
  anchor's specific figure for it, since the reference point that figure was
  computed against is itself stale.
- The bodies of `plugin/crew/hooks/scripts/crew_state.py` and
  `scripts/check-marketplace.py` beyond the specific citations this note
  makes were not read; both changed substantially in this range and
  `crew.md`/`marketplace-registration.md`/`verification-harness.md` own
  them.

## Re-anchor provenance - `6c497a14` -> `f2bb919b`, 2026-09-25 (T-0015)

`git diff --name-only 6c497a14 f2bb919b -- <the 39 tracked paths this note cites>` returns seven:
`.claude-plugin/marketplace.json`, `.crew/verify.json`, `CHANGELOG.md`, `README.md`, `TODO.md`,
`plugin/PLUGINS.md`, `plugin/crew/README.md`. Nothing under `docs/` changed on main in that range;
the diagram changes recorded above are this ticket's own. Each changed file:

- `README.md` - the two install-URL pins (`:12`, `:18`) only; the pin landmine is rewritten.
  `:46`, `:52`, `:154`, `:168` and `:736` did not move.
- `TODO.md` - the `render.sh` entry moved `:1092` -> `:1122` (re-read: same heading, still no
  CLOSED marker). The refresh's own follow-up (f), that `process-crew-brief` drew the removed PM
  flow, is resolved by T-0015's redraw.
- `.crew/verify.json` - rule 22 appended, noted above.
- `CHANGELOG.md` - crew 1.0.26-1.0.28 and #227/#228 entries added at the top (`:9` onward, +59
  lines). This note cites the file without a line number.
- `plugin/crew/README.md` - one cell at `:2145`; `:1725` (the `docs/runbooks/INDEX.md` mention) is
  unchanged.
- `plugin/PLUGINS.md` - crew's version row `:14`; `:17`'s counts are unchanged.
- `.claude-plugin/marketplace.json` - crew `version` only; the description is unchanged.

`docs/HANDOFF.md`'s age and `docs/runbooks/rollback.md`'s `last verified` are not re-measured; both
figures above are as of the 2026-09-25 re-derivation, the same day.

Re-verified per-path from `f2bb919b` to `adf8d1dd` for T-0008: of the cited paths, the changed ones were
re-grepped at HEAD and only `TODO.md`, `plugin/crew/README.md` and `.crew/verify.json` citations needed
updating; `CLAUDE.md:147` was re-confirmed in passing.

Re-verified per-path from `adf8d1dd` to `8d447a7d` for T-0008's review round 3: of the cited paths,
`.crew/verify.json` (one path added to rule 7, so rule 22 moved `:243` -> `:244` and rule 23 grew to
`:245-261`; corrected above), `plugin/crew/README.md` (two lines reworded in place; `:1728` did not
move), `TODO.md` (two version strings at `:5000-5001`; the `render.sh` entry at `:1183` did not
move), `CHANGELOG.md` (cited without a line) and
`plugin/crew/hooks/scripts/crew_refresh_check.py` (cited by name only) changed.

Re-verified per-path from `8d447a7d` to `c35edda5` for T-0034. `8d447a7d` was rebase-merged to `main` as `95120430`; `git diff --name-only 8d447a7d 768a747a`
returns only code-map, diagram, rule and graph files plus the crew 1.0.37 release bookkeeping, so
`768a747a` stands in for it. `git diff --name-only 768a747a c35edda5` returns
`.claude-plugin/marketplace.json`, `.gitattributes`, `CHANGELOG.md`, `plugin/PLUGINS.md`,
`plugin/crew/.claude-plugin/plugin.json`, `plugin/crew/hooks/scripts/crew_refresh_check.py` and
`plugin/crew/tests/test_completion_audit.py`. Of those this note cites
`marketplace.json` (crew `version` only; the description is unchanged), `plugin/PLUGINS.md` (`:14`
version row; `:17`'s Registers row unchanged and still `:17`), `CHANGELOG.md` (a 1.0.38 entry
added under `[Unreleased]`; cited without a line) and `crew_refresh_check.py` (cited by name
only). `test_completion_audit.py` is cited by name only, as a rule 23 test file, and still is one.
`.gitattributes` is not cited. No citation moved.

Re-verified per-path from `c35edda5` to `8ebbdedc` for T-0026's landing (`8ebbdedc` is the crew
1.0.39 bump on top of the merge `563f54c3`). Of the paths this note cites, `git diff --name-only
c35edda5 8ebbdedc` returns `.claude-plugin/marketplace.json`, `.crew/verify.json`, `CHANGELOG.md`,
`TODO.md`, `plugin/PLUGINS.md`, `plugin/crew/README.md`, `plugin/crew/commands/done.md` and
`plugin/crew/commands/implement.md`. `plugin/crew/README.md` gained two lines above `:1728` (one
approval-table cell reworded in place, and a new "The status edit keeps the approval" paragraph),
so the `docs/runbooks/INDEX.md` mention moved `:1728` -> `:1730`, re-grepped. `.crew/verify.json`
gained T-0026's rule at `:167-172`, moving the two rules cited above by seven lines; corrected
above. `marketplace.json` and `plugin/PLUGINS.md` changed at crew's `version` only (1.0.39; `:17`
unchanged). `TODO.md` changed at one entry (`:5018`, closed by T-0026); the `render.sh` entry at
`:1183` did not move. `CHANGELOG.md`, `done.md` and `implement.md` are cited by name only.
Re-verified per-path from `8d447a7d` to `6d35ef8c` for T-0006 (`8d447a7d` is T-0008's pre-rebase
commit, tree-identical to `origin/main` `768a747a` for these paths): of the cited paths,
`.crew/verify.json` (rule 24 appended last; `:244` and `:245-261` hold), `plugin/crew/README.md`
(auto-resume prose added, so the `docs/runbooks/INDEX.md` mention moved `:1728` -> `:1756`,
re-read), `TODO.md` (one entry added at the top, so the `render.sh` entry moved `:1183` -> `:1190`,
re-read, same heading), `plugin/crew/commands/handoff.md` (a `resume:` step added as item 5;
`:7` still reads "Write `.work/HANDOFF.md` following the `crew-context` skill.", so the
"unchanged file" remark above is true of its own pass, not of this one),
`plugin/crew/skills/crew-context/SKILL.md` (the `resume:` line and the auto-resume paragraph added;
`:69` still says to write `.work/HANDOFF.md`), `plugin/crew/hooks/scripts/crew_state.py`
(`RESUME_DEFAULTS` inserted at `:684`; the `:129`-`:139` re-exports are above it and hold),
`docs/guides/crew/src/auto-cycle.md` and `CHANGELOG.md` (cited without a line) changed.

Re-verified per-path from `6d35ef8c` to `2bb92f32` for T-0006's review round 3: of the cited
paths, `.crew/verify.json` (rule 24's `seconds` and `why` only), `plugin/crew/README.md` (one line
added in the auto-resume reasons, so the `docs/runbooks/INDEX.md` line moved `:1756` -> `:1757`,
re-grepped), `plugin/crew/skills/crew-context/SKILL.md` (the auto-resume reasons gained the
unreadable-state wait; `:69` still says to write `.work/HANDOFF.md`),
`docs/guides/crew/src/auto-cycle.md` (the refusal list now names the stale-and-not-archived and
unreadable-state waits) and `CHANGELOG.md` (cited without a line) changed. The two diagrams this
note cites are refreshed in the same commit as this note.

Re-verified per-path to `a0c0847e` for T-0006's landing (`a0c0847e` is the crew 1.0.40 bump on top of
`1cec9572`, the merge of T-0006 `cb125d51` into main `d3844c76`, joining this note's `8ebbdedc`
and `2bb92f32` lines). Of the cited paths, those changed on both sides were re-read at `a0c0847e`:
`plugin/crew/README.md` (the `docs/runbooks/INDEX.md` mention is at `:1759`, main's two lines and
T-0006's auto-resume prose both above it; corrected above), `.crew/verify.json` (rule 23 `:251`
and rule 24 `:252-268` hold; T-0006's rule is rule 25 at `:270-280`), `TODO.md` (the `render.sh`
entry still at `:1190`, same heading) and `CHANGELOG.md` (T-0006's 1.0.40 entry now sits above
main's 1.0.39 and 1.0.38 entries; cited without a line). Files changed on one side only keep that
side's re-verified citations.

Re-verified per-path from `a0c0847e` to `07ca3972` for T-0004 (`/crew:autopilot`, crew 1.0.41). Of the
cited paths, `git diff --name-only a0c0847e..07ca3972` returns `.claude-plugin/marketplace.json` (crew
`version` and description, 34 -> 35 slash commands), `.crew/verify.json` (rule 26 appended at
`:281-288`; `:167-172`, `:251`, `:252-268`, `:270-280` hold), `CHANGELOG.md` (1.0.41 entry at the top;
cited without a line), `README.md` (`:168` and `:874` command counts only; `:12`/`:18`, `:46`, `:154`
did not move, and the pin is now stale - landmine rewritten), `TODO.md` (an autopilot note at `:4143`;
the `render.sh` entry still at `:1190`, same heading), `plugin/PLUGINS.md` (`:14` version, `:17` count
35), `plugin/README.md` (`:414` count 35), `plugin/crew/README.md` (the `docs/runbooks/INDEX.md`
mention moved `:1759` -> `:1804`, re-grepped), `plugin/crew/hooks/scripts/crew_state.py`
(`AUTOPILOT_DEFAULTS` added at `:1087`, below the `:129`-`:139` re-exports, which hold),
`plugin/crew/hooks/scripts/crew_ticket.py` (cited by name only, as a rule's path) and both install
scripts (crew catalog row count). `python3 scripts/check-marketplace.py` re-run at `07ca3972`:
`marketplace: 34 skills, 5 plugins` / `all checks passed`.

Re-verified per-path from `8d447a7d` to `fc54def6` for T-0005 (`8d447a7d` is T-0008's pre-rebase
commit; T-0008 landed as `95120430`/`768a747a`). Of the cited paths T-0005 changed
`.crew/verify.json` (a cloud-guard rule inserted at index 6, `:117-126`, so the `.claude/rules/`
rule moved `:244` -> `:255` and the refresh-check rule `:245-261` -> `:256-272`; corrected above),
`plugin/crew/README.md` (the cloud-guard environments section, 39 lines added above the runbooks
section, so the `docs/runbooks/INDEX.md` mention moved `:1728` -> `:1767`, re-read), `crew_state.py`
(three import lines, so the four re-exports moved `:129`/`:133`/`:136`/`:139` ->
`:132`/`:136`/`:139`/`:142`, re-read), `TODO.md` (lines appended at the end; the `render.sh` entry
at `:1183` did not move), `CHANGELOG.md` (cited without a line) and the version files.

## Re-anchor provenance - `fc54def6` -> `2170d72e`, 2026-09-26 (T-0005 review round 2)

`git diff --name-only fc54def6 2170d72e -- <the paths this note cites>` returns only what round 2
changed: `plugin/crew/README.md` (one row rewritten in place at `:971`; `:1767` holds, re-read) and
`CHANGELOG.md` (the 1.0.41 entry gained round 2's bullets; cited by name only).

## Re-anchor provenance - `2170d72e` -> `3a57b2d2`, 2026-09-26 (T-0005 rounds 3-4 and Step 8)

`git diff --name-only 2170d72e 3a57b2d2 -- <the paths this note cites>` returns
`plugin/crew/README.md` (the allowlist paragraph and two sentences above the runbooks section, so
the `docs/runbooks/INDEX.md` mention moved `:1767` -> `:1788`, re-read), `.crew/verify.json`
(`crew_guards.py` added to the cloud-guard rule, so the `.claude/rules/` rule moved `:255` ->
`:256` and the refresh-check rule `:256-272` -> `:257-273`; corrected above) and `CHANGELOG.md`
(the 1.0.41 entry gained the allowlist bullet; cited by name only).

## Re-anchor provenance - `3a57b2d2` -> `1e210476`, 2026-09-26 (T-0005 Step 9)

`git diff --name-only 3a57b2d2 1e210476 -- <the paths this note cites>` returns
`plugin/crew/README.md` (the allowlist paragraph rewritten for Step 9, seven lines longer, so the
`docs/runbooks/INDEX.md` mention moved `:1788` -> `:1795`, re-read; corrected above) and
`CHANGELOG.md` (the 1.0.41 entry gained the Step 9 bullet; cited by name only). `.crew/verify.json`
did not change.

## Re-anchor provenance - `1e210476` -> `aa7f9841`, 2026-09-26 (T-0005 review round 5)

`git diff --name-only 1e210476 aa7f9841 -- <the paths this note cites>` returns
`plugin/crew/README.md` (fifteen lines added to the cloud-guard section, so the
`docs/runbooks/INDEX.md` mention moved `:1795` -> `:1810`, re-read, same text; corrected above;
`:12`, `:15`, `:46`, `:414` and `:736` are above the hunk and hold) and `CHANGELOG.md` (the 1.0.41
entry gained the round-5 bullet and its Tests bullet was corrected; cited by name only).
`.crew/verify.json` did not change.

## Re-anchor provenance - `aa7f9841` -> `a26ad8c0`, 2026-09-26 (T-0005 Step 10)

`git diff --name-only aa7f9841 a26ad8c0 -- <the paths this note cites>` returns
`plugin/crew/README.md` (the cloud-guard section rewritten in part and a "What the guard does not
catch" subsection added, 44 lines net, so the `docs/runbooks/INDEX.md` mention moved `:1810` ->
`:1854`, re-read, same text; corrected above; `:12`, `:15`, `:46`, `:414` and `:736` are above the
first hunk and hold) and `CHANGELOG.md` (the 1.0.41 entry gained the Step 10 bullet; cited by
name only). `.crew/verify.json` did not change.

Re-verified per-path to `2b18f7ab` for T-0005's landing (the crew 1.0.42 bump on top of `4ed4b763`,
the merge of T-0005 `4e0abc8f` into main `1e0706ac`, joining this note's `6f96e627` and `a26ad8c0`
lines). Of the cited paths, those changed on both sides were re-read on the merged tree:
`plugin/crew/README.md` (the `docs/runbooks/INDEX.md` mention is at `:1930`, both sides' additions
above it; corrected above), `.crew/verify.json` (T-0005's cloud-guard rule `:117-127` and T-0026's
approval-digest rule `:179-184` both sit above the `.claude/rules/` check, now `:263`, and the
refresh-check rule `:264-280`; T-0006's rule `:282-292` and T-0004's `:293-300` follow; corrected
above), `TODO.md` (the `render.sh` entry still at `:1190`, same heading; T-0005's lines are
appended at the end), `plugin/crew/hooks/scripts/crew_state.py` (T-0005's three import lines at `:74` and `:102-103`
sit above the four re-exports, which are at `:132`/`:136`/`:139`/`:142` as T-0005's text above
says, re-read on the merge; main's `RESUME_DEFAULTS`/`AUTOPILOT_DEFAULTS` are below them) and `CHANGELOG.md`
(T-0005's 1.0.42 entry sits above T-0004's 1.0.41; cited without a line). The two diagrams this
note cites are refreshed in the same commit as this note. Nothing was executed.

## Re-anchor provenance - T-0042's branch line, `6f96e627` -> `068db4ff` -> `07eefac5`, 2026-09-26

Re-verified per-path from `6f96e627` to `068db4ff` for T-0042 (auto-resume round 4, crew 1.0.42).
`6f96e627` is T-0004's landing and `git diff --name-only 6f96e627 1e0706ac` returns refresh
artifacts only. Of the cited paths, `git diff --name-only 1e0706ac 068db4ff` returns
`plugin/crew/README.md` (auto-resume prose added above it, so the `docs/runbooks/INDEX.md` mention
moved `:1804` -> `:1818`, re-grepped; corrected above), `plugin/crew/commands/handoff.md` (how a
note binds to its session added below `:7`, which holds), `plugin/crew/skills/crew-context/SKILL.md`
(every wait reason named; `:69` holds, re-read), `docs/guides/crew/src/auto-cycle.md` (the same
wait reasons; cited by name only), `TODO.md` (eleven lines inserted above the `render.sh` entry,
`:1190` -> `:1201`, same heading; corrected above), `CHANGELOG.md` (the 1.0.42 entry at the top;
cited without a line), `.crew/verify.json` (rule 25's `seconds` and `why` in place; `:167-172`,
`:251`, `:252-268`, `:270-280`, `:281-288` hold), `plugin/PLUGINS.md` (`:14` version only; `:17`
unchanged), `.claude-plugin/marketplace.json` and `plugin/crew/.claude-plugin/plugin.json`
(crew `version` only, 1.0.42). `README.md`, `plugin/README.md`, `INSTALLATION.md`, `skills/README.md`
and `docs/runbooks/` did not change, so their citations stand and the README pin is as stale as it
was at `6f96e627`.

Re-verified per-path from `068db4ff` to `07eefac5` for T-0042 review round 1. Of the cited paths,
`git diff --name-only 068db4ff 07eefac5` returns `.crew/verify.json` (rule 25's `seconds` and `why`
in place, `:277` and `:280`; 293 lines, so `:167-172`, `:251`, `:252-268`, `:270-280` and `:281-288` hold) and `CHANGELOG.md` (seven lines inside
the 1.0.42 entry; cited without a line). The version files were stepped to 1.0.41 and back and
diff empty against `068db4ff`. `python3 scripts/check-marketplace.py` at `07eefac5`:
`marketplace: 34 skills, 5 plugins`, `all checks passed`.

## Re-anchor provenance - `2b18f7ab` + `07eefac5` -> `53f5482c`, 2026-09-27 (T-0042 merges main)

`53f5482c` is T-0042's rule-26 re-measure on top of the merge of origin/main `502cb137` into its
branch (`b7727a88`). Of the cited paths changed on both sides, each re-read on the merged tree:
`plugin/crew/README.md` (T-0042's auto-resume prose at `:1747` sits above the runbooks mention,
so main's `:1930` is `:1944`; set in the merge, re-read), `TODO.md` (the `render.sh` entry at
`:1201`, main's `:1190` plus T-0042's eleven lines; T-0005's lines are appended at the end),
`.crew/verify.json` (rule 26's `seconds` and `why` in place; `:167-172`, `:263`, `:264-280`,
`:282-292` hold) and `CHANGELOG.md` (T-0042's 1.0.43 entry above T-0005's 1.0.42; cited without
a line). `plugin/crew/commands/handoff.md:7` and `plugin/crew/skills/crew-context/SKILL.md:69`
changed on T-0042 only and hold. The two diagrams this note cites are refreshed in the same
commit as this note. Nothing was executed for this note.

Re-verified per-path from `c35edda5` to `7b667587` for T-0021. `git diff --name-only c35edda5
7b667587` returns T-0034's refresh (`5c59395d`: code maps, `.claude/rules/`, the lifecycle
diagram, `graphify-out/`) and T-0021's code, prose and release files. Of those this note cites
`plugin/crew/README.md` (section 13c rewritten, +34 lines, so the runbook-index citation moved
`:1728` -> `:1762`, re-grepped), the three crew diagrams (re-anchored to `7b667587`, above),
`.crew/verify.json` (one rule appended; cited without a line), `CHANGELOG.md` (a 1.0.46 entry
under `[Unreleased]`), `TODO.md` (T-0021 follow-ups appended at the end; `:1183` holds),
`plugin/PLUGINS.md` (`:14` version row; `:17` unchanged) and `marketplace.json` (crew `version`
only). The root `README.md` citations (`:12`, `:46`, `:736`) are to a file not in the diff.

Re-verified per-path from `7b667587` to `385eadd5` for T-0021's review round 1. `git diff --name-only 7b667587 385eadd5` returns T-0021's refresh (`bc6432b1`), the version step-back (`764c2244`) and review round 1's fix commit (`385eadd5`): `CHANGELOG.md`, `TODO.md`, `plugin/crew/BUDGETS.md`, `plugin/crew/README.md`, `brainstorm.md`, `obsidian-sync.md`, `crew_tracker.py` and three test files, plus the refresh's own artifacts. The version files net to no change (1.0.46 stepped back and re-set).
Of those this note cites `plugin/crew/README.md` (the tracker paragraph grew by 7 lines, so the
runbook-index citation moved `:1762` -> `:1769`, re-grepped), the three crew diagrams
(re-anchored to `385eadd5`), `CHANGELOG.md` (a round-1 paragraph inside the 1.0.46 entry),
`TODO.md` (the brainstorm follow-up struck and one `obsidian.columns` item added, both at the end
of the T-0021 block; `:1183` holds). The root `README.md` citations are to a file not in the diff.

Re-verified per-path from `385eadd5` to `bcb77ce2` for T-0021's review round 2. `git diff --name-only 385eadd5 bcb77ce2` returns the round-1 refresh (`59de6d56`), the version step-back (`f11c72d0`) and review round 2's fix commit (`bcb77ce2`): `CHANGELOG.md`, `plugin/crew/BUDGETS.md`, `plugin/crew/README.md`, `fix.md`, `implement.md`, `jira-sync.md`, `sdp-sync.md`, `crew_tracker.py` and three test files, plus the refresh's own artifacts. The version files net to no change (1.0.46 stepped back and re-set).
Of the cited paths only `plugin/crew/README.md` changed (section 13c grew by 25 lines, so the
runbook-index citation moved `:1769` -> `:1794`, re-grepped) and `implement.md` (cited by name
only); the three crew diagrams were re-anchored to `bcb77ce2` in the same refresh. The root
`README.md`, `plugin/README.md` and `skills/README.md` did not change, so their citations stand.

## Re-anchor provenance - `2b18f7ab` + `bcb77ce2` -> `c2ae46ab`, 2026-09-27 (T-0021 review round 3 and its merge of main)

The merge `86ea912f` joins main's `2b18f7ab` with T-0021's `bcb77ce2`; review round 3's fix commit
`629fb518` sits under it and the crew 1.0.43 bump `c2ae46ab` on top. `git diff --name-only 2b18f7ab
c2ae46ab` returns only T-0021's files (its code, commands, tests, fixtures, release files,
`.crew/verify.json`, `CHANGELOG.md`, `TODO.md`). Every citation in this note's body into those files
was re-mapped from the side of the merge its line came from (`git blame`: main's lines against
`2b18f7ab`, T-0021's against `bcb77ce2`) with a line diff, and each one whose line moved or changed
was re-read at `c2ae46ab`. Corrected here: the `docs/runbooks/INDEX.md` sentence in
`plugin/crew/README.md` is `:2006`; the tracker rule is recorded at `.crew/verify.json:301-308`. No
command or suite was executed for this note.

## Re-anchor provenance - `c2ae46ab` -> `d276b268`, 2026-09-27 (T-0021 review round 4)

`git diff --name-only c2ae46ab d276b268` returns T-0021's test-escape and round-4 files:
`crew_tracker.py`, `brainstorm.md`, `fix.md`, three test files, `plugin/crew/README.md`,
`CHANGELOG.md`, `TODO.md` (one follow-up appended at `:5080`), two crew guides with their built
outputs, and the version files (stepped to 1.0.42 and re-set to 1.0.43 twice, net unchanged, so
crew's `version` at `.claude-plugin/marketplace.json:218` and `plugin/PLUGINS.md:14` still read
1.0.43). Corrected here: the `docs/runbooks/INDEX.md` sentence in `plugin/crew/README.md` is
`:2015` (section 13c grew by 9 lines above it, re-grepped), and the three crew diagrams now carry
`d276b268`. `TODO.md:1190` sits above the appended line and holds. `docs/guides/crew/src/`
gained a ticket-board section in `memory-and-obsidian.md` and an `id taken` entry in
`troubleshooting.md`; only those two guides were rebuilt. The root `README.md`, `plugin/README.md`
and `skills/README.md` did not change. No command or suite was executed for this note.

## Re-anchor provenance - `f0b12ee6` + `74f52fae` -> `12682e41`, 2026-09-27 (T-0021 lands on T-0042's main)

`6df1231a` merges T-0021's reviewed head `74f52fae` into main `f0b12ee6` (T-0042 landed as crew
1.0.43, PR #242), and `12682e41` bumps crew to 1.0.44. The two sides share no source file: the
paths both changed since `502cb137` are `CHANGELOG.md`, `TODO.md`, `.crew/verify.json`,
`plugin/crew/README.md`, `plugin/crew/CONFIG.md`, `plugin/crew/BUDGETS.md`, the version files and
the refresh artifacts. The conflicting provenance sections keep both sides, T-0042's first. Every
`path:N` citation in the body, and every bare `:N` that follows a path, was mapped from the side
its line came from onto the merged tree with a line diff (`git show <side>:<path>` against the
merge); each one that moved was re-read with `sed -n` on the merge and corrected: the runbooks
mention in `plugin/crew/README.md` is `:2029` (`:2015` on T-0021's side, `:1944` on T-0042's).
`TODO.md:1201` holds (T-0021's lines are appended at the end of the file). `CHANGELOG.md` and
`.crew/verify.json` are cited without a line here. `handoff.md`, `crew-context/SKILL.md` and the
guide sources changed on one side only. The diagrams this note cites are re-anchored in the same
commit as this note. Nothing was executed for this note.

## Re-anchor provenance - `6f96e627` -> `eba11657`, 2026-09-26 (T-0023)

Re-verified per-path from `6f96e627` to `eba11657` for T-0023 (plain-text lifecycle routing, crew
1.0.42); `6f96e627` -> `1e0706ac` touched only refresh artifacts. Of the cited paths,
`git diff --name-only 1e0706ac eba11657` returns `.claude-plugin/marketplace.json` (crew `version`
only), `.crew/verify.json` (rule 27 appended at `:289-297`; `:167-172`, `:251`, `:252-268`,
`:270-280` and `:281-288` hold), `CHANGELOG.md` (the 1.0.42 entry at the top; cited without a line),
`plugin/PLUGINS.md` (`:14` version; `:17` count unchanged) and `plugin/crew/README.md` (a 23-line
"Plain-text lifecycle" subsection above "Measuring 1.0", so the `docs/runbooks/INDEX.md` mention
moved `:1804` -> `:1827`, re-grepped). Nothing under `docs/` and neither `README.md`, `TODO.md` nor
`plugin/README.md` changed. `python3 scripts/check-marketplace.py` at `eba11657`: `marketplace: 34
skills, 5 plugins` and one problem, `plugin/crew/BUDGETS.md:10: claims 18,176 plugin/crew Markdown
lines, but plugin/crew/*.md currently totals 18239` - BUDGETS.md is outside T-0023's Touch.

## Re-anchor provenance - `2b18f7ab` + `488053fc` -> `a1acd9b7`, 2026-09-27 (T-0023 merge of main)

`3c968175` merges main at `502cb137` (T-0005 landed, its notes anchored `2b18f7ab`) into T-0023 at
`488053fc` (review round 1's fixes); `f6abe8c1` re-sets crew to 1.0.43 and `a1acd9b7` re-prices
`.crew/verify.json` rule 28 in place. Both lines' provenance is above. A citation can only be
wrong at the merge when its file changed on both sides, or when a line from one side cites a file
the other side changed. Each line of this note was classified by origin (main's text or
T-0023's), its citations into such files re-mapped with a line diff from that side's revision to
the merged tree (`502cb137` or `fa4d8cd5`), and each moved one re-read by content with
`grep -n`/`sed -n`; citations the line diff attributed to the wrong file were discarded, not
applied. Of the paths this note cites, `plugin/crew/README.md` changed on both sides (the `docs/runbooks/INDEX.md` mention is at `:1953`, re-grepped), `.crew/verify.json` has 29 rules with T-0023's routing rule appended last at `:301-309` (every earlier line holds), and `CHANGELOG.md`, the version files and `PLUGINS.md` are cited by name or at lines that did not move. Nothing under `docs/` changed except the two refreshed diagrams.

## Re-anchor provenance - `db14619c` + `ad74ed35` -> `e463ca53`, 2026-09-27 (T-0023 lands on T-0021's main)

`c68b40bd` merges origin/main `db14619c` (T-0042 landed as crew 1.0.43, PR #242; T-0021 as
1.0.45, PR #243) into T-0023's `ad74ed35`, and `e463ca53` bumps crew to 1.0.46. The files both
sides changed since `502cb137` are `CHANGELOG.md`, `.crew/verify.json`, `plugin/crew/README.md`,
`plugin/crew/CONFIG.md`, `plugin/crew/BUDGETS.md`, `plugin/crew/hooks/scripts/crew_context.py`,
`plugin/crew/tests/sabotage.py`, the version files and the refresh artifacts. The conflicting
provenance sections keep both sides, main's first. Every `path:N` citation in the body, and every
bare `:N` that follows a path, was mapped from the side its line came from onto the merged tree
with a line diff (`git show <side>:<path>` against the merge); each one that moved was re-read
with `sed -n` and corrected, and hits the diff attributed to the wrong file (a bare `:N` after
an unrelated path) were discarded rather than applied: the runbooks
mention in `plugin/crew/README.md` is `:2052` (`:2029` on main's side, `:1953` on T-0023's).
`TODO.md` is byte-identical to main's (`:1201` holds). `CHANGELOG.md` and `.crew/verify.json`
are cited without a line here. The diagrams this note cites are re-anchored in the same commit
as this note. Nothing was executed for this note.

Re-verified per-path from `6f96e627` to `5536c2c8` for T-0018 (`/crew:autopilot status`, crew
1.0.42). Of the cited paths, `git diff --name-only 6f96e627..5536c2c8` returns
`.claude-plugin/marketplace.json` (crew `version` only), `.crew/verify.json` (rule 26 gained one
path, `:281-288` -> `:281-289`; `:167-172`, `:251`, `:252-268`, `:270-280` hold), `CHANGELOG.md`
(1.0.42 entry at the top; cited without a line), `plugin/PLUGINS.md` (`:14` version) and
`plugin/crew/README.md` (14 lines added in the autopilot section, so the `docs/runbooks/INDEX.md`
mention moved `:1804` -> `:1818`, re-grepped). `README.md`, `TODO.md`, `plugin/README.md` and both
install scripts did not change, so the README pin is no staler than at `6f96e627`.
`python3 scripts/check-marketplace.py` re-run at `5536c2c8`: `marketplace: 34 skills, 5 plugins` /
`all checks passed`.

Re-verified per-path from `5536c2c8` to `4ff7e764` (T-0018 review round 1). Of the cited paths,
`git diff --name-only 5536c2c8..4ff7e764` returns `CHANGELOG.md` (the 1.0.42 entry gained its round-1
paragraph; cited without a line) and `plugin/crew/README.md` (two lines edited in place, none added,
so the `docs/runbooks/INDEX.md` mention holds at `:1818`, re-grepped). `README.md`, `TODO.md`,
`plugin/README.md` and both install scripts did not change. `python3 scripts/check-marketplace.py`
at `4ff7e764`: `marketplace: 34 skills, 5 plugins` / `all checks passed`.

Re-verified per-path from `4ff7e764` to `29a987b0` (T-0018 review round 2). Of the cited paths,
`git diff --name-only 4ff7e764..29a987b0` returns `.crew/verify.json` (rule 26's `seconds` and
`why` changed in place; no line moved, so every `.crew/verify.json:<n>` citation here holds) and
`CHANGELOG.md` (the 1.0.42 entry gained its round-2 paragraph; cited without a line).
`plugin/crew/README.md`, `README.md`, `TODO.md`, `plugin/README.md` and both install scripts did
not change.

Re-verified per-path from `29a987b0` to `c87ac3f4` (T-0018 review round 3). Of the cited paths,
`git diff --name-only 29a987b0 c87ac3f4` returns `.crew/verify.json` (rule 26's `seconds` and
`why` changed in place; no line moved, so every `.crew/verify.json:<n>` citation here holds) and
`CHANGELOG.md` (the 1.0.42 entry gained its round-3 paragraph; cited without a line).
`plugin/crew/README.md`, `README.md`, `TODO.md`, `plugin/README.md` and both install scripts did
not change.

Re-verified per-path from `2b18f7ab` (main) and `c87ac3f4` (the T-0018 branch) to `b1ae1500`, the
T-0018 round-4 fixes, the merge of main `502cb137` (crew 1.0.42) and the crew 1.0.43 bump: of the
cited paths, `plugin/crew/README.md` (T-0018's 15 autopilot lines on top of main's and one table
row edited in place, so the `docs/runbooks/INDEX.md` sentence moved `:1930` -> `:1945`, re-grepped),
`.crew/verify.json` (the autopilot rule widened in place to `:293-301`; every earlier rule is at
main's lines), `CHANGELOG.md`, `plugin/PLUGINS.md` (`:14` 1.0.43; `:17` unchanged) and
`.claude-plugin/marketplace.json` (`:218` 1.0.43; `:217` unchanged) changed. `README.md`,
`plugin/README.md`, `INSTALLATION.md`, `docs/runbooks/` and
`plugin/crew/skills/crew-runbooks/SKILL.md` did not. `check-marketplace.py` passed at `b1ae1500`
(`marketplace: 34 skills, 5 plugins`).

Re-verified per-path from `b1ae1500` to `89f73d79` (T-0018 review round 5, the version step-back
and re-set). Of the cited paths, `plugin/crew/README.md` changed on one line in place (the
`status` paragraph), so the `docs/runbooks/INDEX.md` sentence is still `:1945` (re-grepped), and
`CHANGELOG.md` gained the round-5 paragraph in the 1.0.43 entry (cited without a line). The
version files are byte-identical to `b1ae1500`'s; `.crew/verify.json`, `README.md`,
`plugin/README.md`, `INSTALLATION.md`, `docs/runbooks/` and
`plugin/crew/skills/crew-runbooks/SKILL.md` did not change. `check-marketplace.py` passed at
`89f73d79` (`marketplace: 34 skills, 5 plugins`).

## Re-anchor provenance - main's `53f5482c` -> `0c7f6b84`, 2026-09-27 (T-0018, merge of origin/main `f0b12ee6`)

`crew_refresh_check.py --root . --ticket T-0018` named this note after `11e8afe3` merged origin/main
`f0b12ee6` (T-0042, crew 1.0.43) into T-0018-router and `0c7f6b84` set crew 1.0.44 last. The merge
took main's anchor, so the check measured T-0018's own paths against it. The two sides changed no
source file in common. The files both sides changed are `.crew/verify.json`, `plugin/crew/README.md`,
`CHANGELOG.md`, `plugin/crew/BUDGETS.md` and the three version files. Every `path:line` citation into
them in this note was compared with the same line on each side and at `0c7f6b84`:

- `.crew/verify.json` - 28 rules, 306 lines. Against T-0018's side nothing moved (main's rule 26
  `seconds` and `why` changed in place), so rule 27 is still `:293-301`. Against main's side the
  autopilot rule adds one line after `:295`.
- `plugin/crew/README.md` - main added 14 lines at `:1762`, and T-0018 added 15 lines after `:790`.
  The only citation that moved, the runbook-index line, was recomputed in the merge (`:1959`).
- `CHANGELOG.md` - cited by name, apart from one historical citation that was already recorded as
  out of scope. `plugin/crew/BUDGETS.md:11` is 18,566 over 121 files, re-measured in the merge.
- Version files - `.claude-plugin/marketplace.json:218`, `plugin/crew/.claude-plugin/plugin.json`
  and `plugin/PLUGINS.md:14` read 1.0.44 at `0c7f6b84`. They were 1.0.43 on both sides of the merge.

No suite was run by this note.

## Re-anchor provenance - `db14619c` + `e6b696fb` -> `fbc27b49`, 2026-09-27 (T-0018 lands on T-0021's main)

`515346b1` merges T-0018's reviewed head `e6b696fb` (review round 6 CLEAN) into main `db14619c`
(T-0021 landed as crew 1.0.44 and 1.0.45, PR #243), and `fbc27b49` bumps crew to 1.0.46. The two
sides share no source file: the paths both changed since `f0b12ee6` are `CHANGELOG.md`,
`.crew/verify.json`, `plugin/crew/README.md`, `plugin/crew/BUDGETS.md`,
`plugin/crew/tests/test_lifecycle_commands.py` (merged cleanly), the version files and the refresh
artifacts. The conflicting provenance sections keep both sides, main's (T-0021's) first. Every
`path:N` citation in the body, and every bare `:N` that follows a path, was mapped from the side
its line came from onto the merged tree with a line diff (`git show <side>:<path>` against the
merge); each one that moved was re-read with `sed -n` on `fbc27b49` and corrected.
Corrected here: the `docs/runbooks/INDEX.md` mention in `plugin/crew/README.md` is `:2044`;
`.crew/verify.json` rule 27 is `:293-301` and rule 28 `:302-309`. Nothing was executed for this
note.

## Re-anchor provenance - `55f59b04` + `bebbb97f` -> `65bb3330`, 2026-09-27 (T-0018 lands on T-0023's main)

`f458e752` merges main `bebbb97f` (T-0023 landed as crew 1.0.46, PR #244) into T-0018-land,
which had merged T-0018's reviewed head `e6b696fb` into `db14619c` and been refreshed at
`55f59b04`; `65bb3330` re-bumps crew to 1.0.47. The two sides share no source file: T-0023
changed `crew_route.py`, `crew_context.py`, `crew_config.py`, `sabotage.py` and their tests, T-0018
`crew_autopilot.py`, `autopilot.md` and theirs; both changed `CHANGELOG.md`, `.crew/verify.json`
(merged cleanly: 30 rules, 323 lines), `plugin/crew/README.md` (merged cleanly),
`plugin/crew/BUDGETS.md`, the version files and the refresh artifacts. The conflicting provenance
sections keep both sides, main's (T-0023's) first. Every `path:N` citation in the body was mapped
from the side its line came from onto the merged tree with a line diff, and each one that moved was
re-read with `sed -n` on `65bb3330` and corrected.
Corrected here: the `docs/runbooks/INDEX.md` mention in `plugin/crew/README.md` is `:2067`;
`.crew/verify.json` rules 27, 28 and 29 are `:293-301`, `:302-309` and `:310-318`, and the rule
paragraph now names T-0023's rule 29, which main's text had not. Nothing was executed for this
note.

Re-verified per-path from `6f96e627` to `a2802526` for T-0024 (group approval, crew 1.0.42). Of the
cited paths, `git diff --name-only 6f96e627..a2802526` returns `.claude-plugin/marketplace.json`
(crew `version` only), `.crew/verify.json` (rule 27 appended at `:290-297`; `:167-172`, `:251`,
`:252-268`, `:270-280`, `:281-288` hold), `CHANGELOG.md` (1.0.42 entry at the top; cited without a
line), `plugin/PLUGINS.md` (`:14` version only), `plugin/crew/README.md` ("Scope and approval"
gained the group forms, so the `docs/runbooks/INDEX.md` mention moved `:1804` -> `:1812`,
re-grepped) and `plugin/crew/hooks/scripts/crew_ticket.py` (cited by name only, as a rule's path).
`README.md`, `TODO.md`, `plugin/README.md` and both install scripts did not change.
`python3 scripts/check-marketplace.py` re-run at `a2802526`: `marketplace: 34 skills, 5 plugins` /
`all checks passed`.

Re-verified per-path from `a2802526` to `f8671fdc` for T-0024's review round 1 and successor step 6.
Of the cited paths, `.claude-plugin/marketplace.json` (version only, 1.0.44), `CHANGELOG.md` (1.0.43
and 1.0.44 entries at the top; cited without a line), `plugin/PLUGINS.md` (`:14` only),
`plugin/crew/README.md` (group-approval prose only; the `docs/runbooks/INDEX.md` mention still at
`:1812`, re-grepped) and `plugin/crew/hooks/scripts/crew_ticket.py` (cited by name only, as a rule's
path) changed. `.crew/verify.json`, `README.md`, `TODO.md` and both install scripts did not.

Re-verified per-path from `f8671fdc` to `45345812` for T-0024's review round 3. Of the cited paths,
`.claude-plugin/marketplace.json` (version only, 1.0.45), `CHANGELOG.md` (1.0.45 entry at the top;
cited without a line), `plugin/PLUGINS.md` (`:14` only), `plugin/crew/README.md` (two sentences in
place; `docs/runbooks/INDEX.md` still at `:1812`) and `crew_ticket.py` (by name only) changed.

## Re-anchor provenance - `65bb3330` + `474aea8b` -> `8de3c669`, 2026-09-27 (T-0024 lands on T-0018's main)

`affa22a5` merges T-0024's reviewed head `474aea8b` (review round 4 FINDINGS, owner-accepted) into
main `67caa4b8` (T-0018 landed as crew 1.0.47, PR #245), and `8de3c669` bumps crew to 1.0.48.
The two sides share no source file: T-0024 changed `approval_hook.py`, both approval-hook wrappers,
`crew_ticket.py`, `commands/approve.md` and their tests; both sides changed `CHANGELOG.md`,
`.crew/verify.json`, `plugin/crew/README.md` (merged cleanly), `plugin/crew/tests/sabotage.py`,
`plugin/crew/BUDGETS.md`, the version files and the refresh artifacts. The conflicting provenance
sections keep both sides, main's first.
Corrected here: the `docs/runbooks/INDEX.md` sentence is `plugin/crew/README.md:2075` (T-0024's
group-approval paragraph added eight lines above it); `.crew/verify.json` gains T-0024's rule 30 at
`:320-327`, after T-0023's rule 29 `:310-318`, whose last line gained only a trailing comma. Rules
above it did not move. No test suite was executed for this note.

## Re-anchor provenance - `8de3c669` -> `a6e81869`, 2026-09-27 (T-0079 on its branch)

`T-0079-read` was cut from `67caa4b8`, merged main `d2fbd408` (T-0024 landed; its refresh `fdc54ce9`
changed refresh artifacts only) in `f034ef5c`, and carries T-0079's commits through `a6e81869`
(crew 1.0.49). `git diff --name-only 8de3c669 a6e81869`, refresh artifacts aside, returns T-0079's
files only: `review_verdict.py`, `review_prompt.py`, `review_run.py`, their tests and
`sabotage_review.py`, `agents/reviewer.md`, `plugin/crew/README.md` (line-neutral), `CHANGELOG.md`
and the three version files. Every body citation into those files was compared by script between
`8de3c669` and `a6e81869` at the same line.
Of the cited paths, `.claude-plugin/marketplace.json` (`:218` 1.0.49, in place),
`plugin/PLUGINS.md` (`:14` 1.0.49, in place) and `CHANGELOG.md` (T-0079's entry at the top; cited
without a line here) changed; no citation moved. No test suite was executed for this note.

## Re-anchor provenance - `a6e81869` -> `81685adf`, 2026-09-27 (T-0079 merges main, Step 7, re-bump)

`T-0079-read` gained T-0079's Step 7 (`8f7c62dd`, one `find` string in
`plugin/crew/tests/sabotage_webtest.py`), merged main `f96e9ec9` (T-0077 landed, crew 1.0.49) in
`548ee44e`, and re-bumped crew to 1.0.50 in `81685adf`. `git diff --name-only a6e81869 81685adf`,
refresh artifacts aside, returns that `sabotage_webtest.py`, T-0077's files (`crew_tracker.py`,
`crew_autopilot.py`, `sabotage_tracker.py`, `sabotage_autopilot.py`, `test_crew_tracker.py`,
`test_crew_autopilot.py`, `test_crew_autopilot_status.py`), `plugin/crew/README.md` (line-neutral
on both sides), `CHANGELOG.md` and the three version files. Every body citation of the form
`path:line` into those files was compared by script between `a6e81869` and `81685adf`.
`plugin/crew/README.md:2075` still holds the `docs/runbooks/INDEX.md` sentence; no citation moved.
Nothing was executed for this note.

## Re-anchor provenance - `12682e41` + `d2444be9` -> `e95e5964`, 2026-09-27 (T-0075 merges main)

`e95e5964` is T-0075's crew 1.0.46 bump on top of `e94ce6ce`, the merge of origin/main `db14619c`
(T-0021 landed as 1.0.45) into T-0075's branch; the merge took main's copy of this note and
T-0075's edits were re-applied. Of the cited paths, `git diff --name-only 12682e41 e95e5964`
returns `plugin/crew/README.md` (T-0075's `/crew:config` menu subsection above the runbooks
mention, so `:2029` -> `:2079`, re-read), `README.md`, `plugin/README.md`, `plugin/PLUGINS.md`,
`.claude-plugin/marketplace.json` and both install scripts (the crew count 35 -> 36 in place, no
line moved; corrected above; `:14`/`:218` now 1.0.46), `.crew/verify.json` (rule 7 +3 lines;
`:167-172` holds, the tracker rule `:301-308` -> `:304-311`, cited here only in provenance),
`CHANGELOG.md` (T-0075's entry above T-0021's; cited without a line) and
`docs/guides/crew/src/auto-cycle.md` / `troubleshooting.md` (the menu and alias named; the
troubleshooting guide's HTML, DOCX and PDF rebuilt from the merged sources by `build.py --guide
troubleshooting` in the merge commit `e94ce6ce`). `docs/diagrams/data-flow-crew-config.mmd` is
refreshed in the same commit as this note and keeps its `:1-2` header form. Nothing was executed
for this note beyond `check-marketplace.py` (passed at `e95e5964`).

## Re-anchor provenance - `e95e5964` + `e463ca53` -> `f7163410`, 2026-09-27 (T-0075 merges T-0023's main)

`96b7e59c` merges origin/main `bebbb97f` (T-0023 landed as crew 1.0.46, PR #244; its notes anchored
`e463ca53`) into T-0075's branch at `0c6b5ecb` (notes anchored `e95e5964`), and `f7163410` bumps
crew to 1.0.47. The source files both sides changed since `db14619c` are `CHANGELOG.md`,
`.crew/verify.json`, `plugin/PLUGINS.md`, `plugin/crew/README.md`, `plugin/crew/CONFIG.md`,
`plugin/crew/BUDGETS.md`, `plugin/crew/hooks/scripts/crew_config.py`,
`plugin/crew/skills/crew-setup/SKILL.md`, `plugin/crew/tests/sabotage.py`,
`plugin/crew/tests/test_crew_config.py` and the version files. The conflicting provenance sections
keep both sides, main's first. Each body line was classified by origin (in T-0075's copy only, in
main's only, or in both), its `path:N` citations - and bare `:N` after a path in the same
paragraph - into files the other side changed were mapped with a line diff (`git show
<side>:<path>` against the merged tree), each moved one re-read with `sed -n`, and hits the diff
attributed to the wrong file (a bare `:N` after an unrelated path, a same-named file elsewhere)
discarded rather than applied. The runbooks mention in `plugin/crew/README.md` is `:2102` (`:2052` on main's side,
`:2079` on T-0075's). `CHANGELOG.md` and `.crew/verify.json` are cited without a line here.
`docs/guides/crew/src/*` changed on T-0075's side only. The diagram this note cites
(`docs/diagrams/data-flow-crew-config.mmd`) is re-anchored to `f7163410` in the same commit as this
note: its T-0075 nodes' `crew_config.py` lines moved +11 as above. Nothing was executed for this
note beyond `check-marketplace.py`.

## Re-anchor provenance - `f7163410` + `65bb3330` -> `23371afb`, 2026-09-27 (T-0075 merges T-0018's main)

`34b5f368` merges origin/main `67caa4b8` (T-0018 landed as crew 1.0.47, PR #245; its notes anchored
`65bb3330`) into T-0075's branch at `b5ef35df` (notes anchored `f7163410`), and `23371afb` bumps crew
to 1.0.48. The source files both sides changed since `bebbb97f` are `CHANGELOG.md`,
`.crew/verify.json`, `plugin/crew/README.md`, `plugin/crew/BUDGETS.md` and the version files;
`crew_autopilot.py`, `commands/autopilot.md` and the autopilot tests changed on main's side only,
`crew_config.py`, `crew_config_menu.py`, `CONFIG.md` and `sabotage.py` on T-0075's only. The
conflicting provenance sections keep both sides, main's first; each body citation into a file both
sides changed was mapped from the side its line came from onto the merged tree and re-read with
`sed -n`/`grep -n`. The runbooks mention in `plugin/crew/README.md` is `:2117` (`:2067` on main's side, `:2102` on
T-0075's). `CHANGELOG.md` and `.crew/verify.json` are cited without a line here; `:167-172` (rule 9)
holds. `docs/guides/crew/src/*` and `docs/diagrams/` changed on neither side of this merge, and
`crew_refresh_check.py` reads `docs/diagrams/data-flow-crew-config.mmd` fresh at `f7163410`. Nothing
was executed for this note beyond `check-marketplace.py`.

## Re-anchor provenance - `23371afb` -> `764f6018`, 2026-09-27 (T-0075 review round 1)

`764f6018` fixes T-0075's review round 1. `git diff --name-only 23371afb 764f6018` is `CHANGELOG.md`,
`plugin/crew/BUDGETS.md`, `plugin/crew/CONFIG.md`, `plugin/crew/README.md`,
`plugin/crew/hooks/scripts/crew_config.py`, `plugin/crew/hooks/scripts/crew_config_menu.py`,
`plugin/crew/skills/crew-setup/config-menu.md` and three crew test files. Each citation into one
of them was mapped with a line diff from `87627d86` (the tree `23371afb` describes for those
files) and re-read with `sed -n`/`grep -n`. `plugin/crew/README.md` gained lines in the `/crew:config` menu section, so
`plugin/crew/README.md:2117` became `:2127` (same text, re-read); every other README citation here is
above that section or by name. Nothing was executed for this note.

## Re-anchor provenance - `764f6018` + `8de3c669` -> `7d217751`, 2026-09-27 (T-0075 successor build, merges T-0024's main)

`7d217751` is T-0075's crew 1.0.49 bump. Between `764f6018` (T-0075 review round 1, this note's
last anchor) and it: the successor build's steps 1-9 (`4911b896`..`763eaeff`: `crew_config_files.py`
new, `crew_config.py` and `crew_config_menu.py` redesigned, their tests and sabotage entries, the
menu procedure, `commands/config.md`, `config-setup.md`, `global-config.md`, `plugin/crew/README.md`,
`CONFIG.md`, the troubleshooting guide and `CHANGELOG.md`), `748a823d` merging origin/main `d2fbd408`
(T-0024 landed as 1.0.48, notes anchored `8de3c669`), `af1ee7ef` adding two paths to
`.crew/verify.json` rule 7, `cb67a6ef` rebuilding the troubleshooting guide, `plugin/crew/BUDGETS.md`
re-measured (19,280 lines across 128 files) and the bump. The merge's provenance sections keep both
sides, main's first. Each citation into a path `git diff --name-only 764f6018 7d217751` names was
checked against the tree it was written for (`git blame` on this note gives the commit) and re-read
at `7d217751` with `sed -n`/`grep -n`; `plugin/crew/README.md:2169` (`docs/runbooks/INDEX.md`) holds from the merge;
the troubleshooting guide's source changed (`docs/guides/crew/src/troubleshooting.md`, the
`/crew:config` delete sentence) and its HTML, DOCX and PDF were rebuilt at `cb67a6ef`;
`CHANGELOG.md` carries T-0075's successor entry first. `docs/diagrams/data-flow-crew-config.mmd` is
refreshed in the same change. Nothing was executed for this note.

## Re-anchor provenance - `7d217751` + `f96e9ec9` -> `8cabe586`, 2026-09-27 (T-0075 post-merge fixes, merges T-0077's main)

`8cabe586` is T-0075's crew 1.0.50 bump. Between `7d217751` and it: `ed7cb36c` (the stray line
step 6 left in `crew_config_menu.py:940`, a restore-line test's assertion, and the widening-warning
mutation re-anchored in `sabotage.py`, each found by the first full suite run after the build), a
1.0.48/1.0.49 step-back and re-set (`b80db8e1`, `81ed193c`), `3ebddc74` merging origin/main
`f96e9ec9` (T-0077 landed as 1.0.49: Windows directory handles in `crew_tracker.py`,
`crew_autopilot._rel`, their tests and mutations, three `plugin/crew/README.md` lines and its
`CHANGELOG.md` entry; main's notes were not refreshed for it) and the bump. Citations into the
paths `git diff --name-only 7d217751 8cabe586` names were mapped with `git diff -U0` and each
moved one checked by content at `8cabe586`; `plugin/crew/README.md:2169` holds (T-0077's three README lines are above it and
net zero); `CHANGELOG.md` gained T-0077's entry after T-0075's and T-0024's. The three crew
diagrams were re-anchored to `8cabe586` in the same change. Nothing was executed for this note.

# repo-docs
anchor: useful-claude-add-ons@c35edda5
verified: 2026-09-25

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
  `%% Generated from <repo>@<sha> on <date>.` form, all at `f2bb919b` after
  T-0015. `data-flow-crew-config` was redrawn for crew 1.0 at `6c497a14`
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
  scripts' `PLUGIN_NAME` crew rows all read **4 agents, 34 commands, 29
  skills, 34 hook entries (13 scripts × `.sh`/`.ps1`) across 8 events** —
  independently re-derived from the filesystem (`ls plugin/crew/agents/*.md`
  = 4, `commands/*.md` = 34, `skills/*/` = 29) and from `hooks.json` (parsed
  with `json.load`: 34 entries, 8 distinct event names, 26 unique `command`
  strings), not cross-quoted from any one of the docs. This is the same
  five/six-site figure this note's previous anchors repeatedly found
  disagreeing (see `install-scripts.md`'s "Corrected at this anchor"
  history); at `6c497a14` it does not disagree anywhere this note checked.
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

- **`README.md`'s install-URL pin is current at this anchor; it was stale
  at `6c497a14`, and its history says it will be again.** `README.md:12`/`:18`
  read `6c497a14fc06612732241d2b13eee4fea41996f5` at `f2bb919b` (re-read), set
  by #226 (`86931b29`), and `git log --oneline 6c497a14..f2bb919b --
  scripts/install-prerequisites.sh scripts/install-prerequisites.ps1` is
  empty. At `6c497a14` this bullet recorded the pin at `5d1fc5fd8b08...`,
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
  `plugin/crew/README.md:1728` (`:1725` at `f2bb919b`, `:1604` before that,
  that file having changed in each range — re-grepped, not offset) both still describe
  `docs/runbooks/INDEX.md` as a symptom-keyed index that would live there.
  JUDGEMENT, unchanged: costs nothing with one runbook, becomes a real gap at
  the second.

- **`/crew:handoff` still does not write `docs/HANDOFF.md`; unrelated to it.**
  `plugin/crew/commands/handoff.md:7` — unchanged file, closed by the
  per-path check — still reads "Write `.work/HANDOFF.md` following the
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
  `plugin/crew/hooks/scripts/crew_state.py:129`/`:133`/`:136`/`:139`
  (`_ANCHOR_RE`, `_DIAGRAM_ANCHOR_RE`, `_NOT_SUBSYSTEMS`, `_diagram_paths`).
  A diagram with no anchor header, or one whose anchor is old AND whose
  `%% Anchors:` paths have moved, still counts as `behind`; unknown still
  resolves to stale.

- **`TODO.md`'s `render.sh` entry is still open, still un-CLOSED, re-located
  rather than assumed at its old line.** Now at `TODO.md:1183` (`:1122` at
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
  `6c497a14` one rule was appended (`:244` since T-0008's review round 3
  added a path above it; `:243` when #228 added it): `.claude/rules/**` and
  `.crew/codemap/**` now run `crew_instructions.py rules --root . --check`.
  Since `f2bb919b` another follows it (`:245-261`, T-0008): changes to
  `plugin/crew/hooks/scripts/crew_refresh_check.py`, its tests,
  `plugin/crew/commands/implement.md` or `plugin/crew/commands/done.md` -
  and since review round 3 `scope_guard.py`, `completion_audit.py`,
  `crew_freshness.py` and `scope_base.py` - run the three refresh-artifact
  pytest files plus `test_scope_guard.py`, `test_completion_audit.py` and
  `test_scope_base.py`.

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

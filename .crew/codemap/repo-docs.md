# repo-docs
anchor: useful-claude-add-ons@f4c94e1d
verified: 2026-10-01

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
under `docs/review/`, ADRs under `docs/adr/` (four: T-0085 added
`0004-build-time-development-standards.md`; re-checked with `ls docs/adr/`), rendered per-topic guides under `docs/guides/*/` (see
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
  **35** skills since L-0561 registered `skills/mailgun` (34 before); `python3
  scripts/check-marketplace.py` confirms `marketplace: 35 skills, 5 plugins / all checks passed`. `plugin/README.md:414`'s crew row
  (`<!-- claim: plugin-skills:crew -->`), `plugin/PLUGINS.md:17`, the
  `.claude-plugin/marketplace.json` `crew` description, and both install
  scripts' `PLUGIN_NAME` crew rows all read **4 agents, 36 commands, 29
  skills (30 at `22399a9c`, where T-0085 added `crew-standards` and moved
  `plugin/PLUGINS.md:17`, `README.md:168`/`:874` and the description to 30
  while `plugin/README.md:414` and `INSTALLATION.md:252`, outside its Touch,
  still read 29 and fail `check_self_claims`; both read 30
  from `b82035e6`, the Touch amendment), 34 hook entries (13 scripts × `.sh`/`.ps1`) across 8 events** at
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

- **`README.md`'s install-URL pin is current at this anchor.** `README.md:12`/`:18`
  read `e878cc31e00a7acb480fc17dd8afdcaf40c91f2d` at `ea764992` (re-read), set by
  `17d057db` after T-0075 merged, and no install-script commit follows it
  (`install-scripts.md` owns the mechanics). What the bullet said at earlier
  anchors, when it was stale again as its history said it would be:
  `README.md:12`/`:18` still read
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
  `plugin/crew/README.md:2308` (on T-0040-land's merge of main `66651b69`; `:2274` on L-0520 PR 1's merge of main `844bfc36`; `:2272` on L-0520 PR 1 at `8bf710ed` and on T-0040-land at `a54ca704`; `:2261` on main at T-0028's landing `844bfc36`; on T-0085's landing merge of main `a61a6f38`; `:2227` on T-0085's merge of main `8ab733d7`; `:2222` on T-0085's merge of main `2693d0fa`; `:2098` on T-0085's branch at `8abf7ffe`; `:2209` on T-0010-solo's merge of `e878cc31`; `:2085` on T-0010-solo at `d7c7c75c`, `:2077` at `c817782f`, `:2074` at `89c9ee9a`, `:2063` at `50e67586`; `:2204` at `3648f59a`, T-0075's round-5 docs after its merge of `6387ab49`; `:2201` at `938e3b11`, T-0075's round-4 docs after its merge of `f54af3fa`; `:2192` at `3724731b`, T-0075 after its merge of `e6e10432`; `:2174` on T-0075's merge of `d2fbd408`; `:2080` at `d2fbd408`, `:1817` on T-0024's branch at `45345812`, `:2166` on T-0075's branch at `763eaeff`, `:2132` at `764f6018`, `:2072` at `67caa4b8`, `:2107` on T-0075's `f7163410`, `:2057` at `bebbb97f`, `:2084` on T-0075's `e95e5964`, `:2049` on T-0018's first landing merge at `fbc27b49`, `:2034` at `db14619c`, `:1964` on T-0018's branch at `e6b696fb`, `:1990` at T-0023's `a1acd9b7`, `:2052` at T-0021's `74f52fae`, `:2011` at `c2ae46ab`, `:1981` at T-0042's `f0b12ee6`, `:1935` at `2b18f7ab`, `:1831` at T-0021's `bcb77ce2`, `:1809` at `07ca3972`, `:1764` at `a0c0847e`, `:1735` at `8ebbdedc`, `:1794` at T-0006's `2bb92f32`, `:1733` at `c35edda5`; on T-0005's branch `:1859` at `a26ad8c0`, `:1815` at `aa7f9841`, `:1800` at `1e210476`, `:1793` at `3a57b2d2`, `:1772` at `2170d72e`, `:1733` at `8d447a7d`; `:1730` at `f2bb919b`, `:1609` before that,
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
  `plugin/crew/hooks/scripts/crew_autocycle.py:182` returns
  `".work/HANDOFF.md"` when no config value is set. `docs/HANDOFF.md` is
  human-authored; the two files remain unrelated despite the shared
  basename.

- **`docs/adr/` still exists and holds four ADRs, the fourth T-0085's.**
  `docs/adr/0001-promote-stays-unarmed.md` (unchanged, closed by the
  per-path check), `0002-no-chatgpt-mcp-server.md` (accepted 2026-09-14),
  `0003-crew-departs-from-three-community-best-practices.md` (accepted
  2026-09-17) and `0004-build-time-development-standards.md` (T-0085, the
  build-time development standards); re-checked with `ls docs/adr/`. `CLAUDE.md:103` still reads "Decisions in
  `docs/adr/`" (re-grepped at L-0513's `fe524012`, two lines down from `:101` after L-0513's Commands pointer; `:101` at `adf8d1dd`, re-grepped then; `CLAUDE.md` changed in
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
  `plugin/crew/hooks/scripts/crew_state.py:133`/`:137`/`:140`/`:143`
  (`_ANCHOR_RE`, `_DIAGRAM_ANCHOR_RE`, `_NOT_SUBSYSTEMS`, `_diagram_paths`).
  A diagram with no anchor header, or one whose anchor is old AND whose
  `%% Anchors:` paths have moved, still counts as `behind`; unknown still
  resolves to stale.

- **`TODO.md`'s `render.sh` entry is still open, still un-CLOSED, re-located
  rather than assumed at its old line.** Now at `TODO.md:1230` (`:1190` at
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
  `6c497a14` one rule was appended (`:266` on the T-0005 landing merge, where T-0026's rule and
  T-0005's cloud-guard rule both sit above it; `:254` after T-0026 inserted a rule above it,
  `:259` after T-0005 did the same and Step 8 added a path; `:247` after T-0008's review round 3
  added a path above it; `:246` when #228 added it): `.claude/rules/**` and
  `.crew/codemap/**` now run `crew_instructions.py rules --root . --check`.
  Since `f2bb919b` another follows it (`:265-281`, T-0008): changes to
  `plugin/crew/hooks/scripts/crew_refresh_check.py`, its tests,
  `plugin/crew/commands/implement.md` or `plugin/crew/commands/done.md` -
  since review round 3 `scope_guard.py`, `completion_audit.py`,
  `crew_freshness.py` and `scope_base.py`, and since T-0094
  `crew_instructions.py` - run the three refresh-artifact pytest files and
  T-0094's `test_refresh_admission.py` plus `test_scope_guard.py`, `test_completion_audit.py` and
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
  `test_lifecycle_commands.py`. T-0010's rule 28 follows it (`:302-308` since T-0010-solo merged
  `67caa4b8`; `:301-306` on its branch): `crew_autopilot.py`, `commands/autopilot.md` (since review
  round 2) and `test_crew_autopilot_policy.py` run that file plus `test_scope_guard.py`. T-0021's
  merge of main put its rule after those (`:309-316` since T-0010's merge; `:302-309` after T-0018
  landed, `:301-308` before that, `:262-269` on its branch before the merge): `crew_tracker.py`,
  `test_crew_tracker.py`, `sabotage_tracker.py` and the board fixtures run
  `test_crew_tracker.py`. T-0023 appended rule 30 last (`:317-325` since T-0010's rule 28 went in
  above it; `:310-318` on main since T-0018 landed, `:309-317` before): `crew_route.py`,
  `crew_context.py`, their two test files and `sabotage_route.py` run `test_crew_route.py`,
  `test_crew_route_hook.py` and `test_crew_context.py`.
  T-0024 appended rule 31 last (`:327-334` since T-0010's merge of `6387ab49`, `:342-349` after its
  merge of `f96e9ec9`; `:320-327` on main; rule 27 at `:290-297` on its branch): `approval_hook.py`, both approval-hook
  wrappers, `crew_ticket.py`, `test_approval_hook.py`, `test_approval_group.py` and
  `sabotage_approval.py` run `test_approval_hook.py`, `test_approval_group.py` and
  `test_crew_ticket.py`. The rules above it did not move.

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
- `CLAUDE.md` beyond its `:156` "Decisions in `docs/adr/`" line (re-confirmed
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

## Re-anchor provenance - T-0010-solo's branch line, `2b18f7ab` -> `50e67586`, 2026-09-27 (crew 1.0.43 on its branch)

T-0010's code commit was cherry-picked off `origin/main` (`502cb137`) as `0fc5b069`, apart from
T-0018 and T-0024, and the version set in `50e67586`. Every `path:line` citation this note makes into
a path T-0010 changed was mapped from the `2b18f7ab` tree with `difflib`; each one that moved
was re-pointed and compared line for line with the anchor tree at `50e67586`.

Of the cited paths `plugin/crew/README.md` (the `docs/runbooks/INDEX.md` mention `:1930` ->
`:1933`, re-grepped), `.crew/verify.json` (rule 28 appended at `:301-306`; every earlier rule
holds), `CHANGELOG.md` (T-0010's entry under Added; cited without a line), `TODO.md` (the
T-0010 line in the autopilot note reworded in place), the version files and `crew_state.py`/
`crew_ticket.py` (cited by name only) changed. `README.md`, `plugin/README.md` and both install
scripts did not.

## Re-anchor provenance - `53f5482c` + `50e67586` -> `89c9ee9a`, 2026-09-27 (T-0010-solo merges main, crew 1.0.44)

`89c9ee9a` is T-0010's crew 1.0.44 version commit on top of `132c1758`, the merge of origin/main
`f0b12ee6` (T-0042 landed at 1.0.43) into T-0010-solo. Both lines' provenance is above. Main-side
citations were mapped through `git diff origin/main 89c9ee9a`, the branch-side ones through
`git diff 708db116 89c9ee9a`, with `difflib` over every repo-relative `path:line` citation, and
every moved or merge-set one re-read with `sed -n` at `89c9ee9a`:

Of the cited paths changed on both sides, each re-read at `89c9ee9a`: `plugin/crew/README.md`
(T-0042's auto-resume prose and T-0010's three lines both sit above the runbooks mention, so it
is `:1947`; set in the merge, corrected above), `TODO.md` (the `render.sh` entry holds at
`:1201`; T-0010's autopilot line reworded in place), `.crew/verify.json` (29 rules, 311 lines;
`:167-172`, `:263`, `:264-280`, `:282-292` hold and T-0010's rule 28 is `:301-306`) and
`CHANGELOG.md` (T-0010's 1.0.44 entry above T-0042's 1.0.43; cited without a line). The two
diagrams this note cites are refreshed in the same commit as this note. Nothing was executed for
this note.

## Re-anchor provenance - `89c9ee9a` -> `8314d670`, 2026-09-27 (T-0010 review round 1 fixes)

`8314d670` fixes the four FIX findings of T-0010's review round 1. Its citations were checked
per path through `git diff 89c9ee9a 8314d670`, every moved one re-read with `grep -n`/`sed -n`
at `8314d670`:

`plugin/crew/README.md` changed one line in place, above none of the cited lines' positions
(`:12`, `:15`, `:46`, `:168`, `:414`, `:736`, `:1947` hold); `CHANGELOG.md` is cited without a
line. No other cited path changed. Nothing was executed for this note.

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
Corrected here: the `docs/runbooks/INDEX.md` sentence is `plugin/crew/README.md:2093` (T-0024's
group-approval paragraph added eight lines above it); `.crew/verify.json` gains T-0024's rule 30 at
`:320-327`, after T-0023's rule 29 `:310-318`, whose last line gained only a trailing comma. Rules
above it did not move. No test suite was executed for this note.

**Re-anchored `53f5482c` -> `d3a1c77e` on 2026-09-27 (T-0072, crew 1.0.44).** `d3a1c77e` is T-0072's version commit on `T-0072-build`, after it merged origin/main `f0b12ee6` (T-0042's landing) with a merge commit. `git diff --name-only 53f5482c d3a1c77e` over the cited paths returns only T-0072's changes and the version files. T-0072 edited in place, with no line added or removed, `crew_state.py` (`:1084-1090`, the `AUTOPILOT_DEFAULTS` comment and value), `plugin/crew/README.md` (the autopilot Settings paragraph), `plugin/crew/commands/autopilot.md` (`:19-20`), `plugin/crew/BUDGETS.md` (`:11`, now 18,612 lines across 121 files), `plugin/PLUGINS.md` (`:14` 1.0.44, the `/crew:autopilot` row), `.claude-plugin/marketplace.json` (`:218` 1.0.44), `plugin/crew/.claude-plugin/plugin.json` (`:3`) and `.crew/verify.json` (rule 27 `:293-300`, same lines). It added lines to `crew_autopilot.py` (the `deploy-allowed` docstring section and functions, 694 -> 837 lines), `CONFIG.md` (+1 at the leaf paragraph, +1 in the key table, +1 in §20's table, a closing §20 section), `CHANGELOG.md` (+32 at the top) and the autopilot tests. Of the paths this note cites, `.crew/verify.json` (rule 27 in place, `:293-300`), `plugin/crew/README.md` (the autopilot Settings paragraph, in place), `crew_state.py` (line-neutral; `:132` holds), `plugin/PLUGINS.md` (`:14` 1.0.44 and the `/crew:autopilot` row, in place; `:17` holds) and `CHANGELOG.md` (T-0072's 1.0.44 entry above T-0042's 1.0.43; cited without a line) changed. `docs/guides/crew/src/*.md` did not change: none mentions autopilot.

**Re-anchored `d3a1c77e` -> `e30af7f9` on 2026-09-27 (T-0072 review round 1).** `e30af7f9` is T-0072's review-round-1 fix commit on `T-0072-build`. `git diff --name-only d3a1c77e e30af7f9` returns `.crew/verify.json` (rule 27's `why` re-measured in place, still `:293-300`), `CHANGELOG.md` (the 1.0.44 entry, four lines reworded, cited without a line), `plugin/crew/BUDGETS.md` (`:11`, now 18,615 lines across 121 files; `check-marketplace.py` prints `all checks passed`), `plugin/crew/CONFIG.md` (+3 lines in §20's closing section, at `:2317`; nothing cited above it moved, `:2251-2258` holds), `plugin/crew/hooks/scripts/crew_autopilot.py` (+24 lines: the docstring gains a line at `:88`, `_deploy_verdict` moves its `cloud_guard` import below the incident check, `_safe_text` and `_crash_reason` are new), `plugin/crew/tests/sabotage_autopilot.py` (+32: `CLOUD` at `:18`, six mutations) and `plugin/crew/tests/test_crew_autopilot_deploy.py`, plus the refresh artifacts of the previous pass. No crew version change (1.0.44). Of the paths this note cites, only `.crew/verify.json` changed, in place inside rule 27's `why`; every line it cites holds. Nothing else this note cites changed.

**Re-anchored `e463ca53` -> `715a8c2f` on 2026-09-27 (T-0072 merged onto `bebbb97f`, crew 1.0.47).** `715a8c2f` is T-0072's crew 1.0.47 version commit on `T-0072-build`, on top of `e658bb04`, its merge of origin/main `bebbb97f` (T-0021 and T-0023 landed; this note was anchored at T-0023's `e463ca53`). `git diff --name-only e463ca53 715a8c2f` over the cited paths returns only T-0072's changes, the neighbour test T-0072 added after the merge, and the version files. Against main, T-0072 edits in place, with no line added or removed, `crew_state.py` (`:1086-1090`, the `AUTOPILOT_DEFAULTS` comment and value), `plugin/crew/README.md` (`:843`, the autopilot Settings paragraph), `plugin/crew/commands/autopilot.md` (`:19-20`), `plugin/crew/BUDGETS.md` (`:11`, now 18,910 lines across 126 files), `plugin/PLUGINS.md` (`:14` 1.0.47, `:128` the `/crew:autopilot` row), `plugin/crew/skills/crew-setup/SKILL.md` (`:170`), `.claude-plugin/marketplace.json` (`:218` 1.0.47), `plugin/crew/.claude-plugin/plugin.json` (`:3`) and `.crew/verify.json` (rule 27 `:293-300`, same lines). It adds lines to `crew_autopilot.py` (694 -> 861), `CONFIG.md` (+3 at the leaf paragraph `:130`, +1 at `:803`, +1 at `:2282`, and the closing §20 section at `:2297`, 41 lines, with T-0023's §21 after it), `CHANGELOG.md` (+31 at `:7`, T-0072's entry above T-0023's), `config.template.json` (+1 at `:205`), `test_crew_config.py` (+3; the count assertion is `:282`, 123), `test_crew_autopilot.py` (+2), `sabotage_autopilot.py` (+140) and the new `test_crew_autopilot_deploy.py`. Of the paths this note cites, `.crew/verify.json` (rule 27 in place, `:293-300`; T-0021's rule 28 `:301-308` holds), `plugin/crew/README.md` (in place at `:825`), `crew_state.py` (line-neutral; `:132` holds), `plugin/PLUGINS.md` (`:14` 1.0.47 and the `/crew:autopilot` row `:128`, in place; `:17` holds), `.claude-plugin/marketplace.json` (`:218` 1.0.47) and `CHANGELOG.md` (T-0072's entry above T-0023's; cited without a line) changed. No `docs/guides/crew/src/*.md` changed: none mentions `autopilot.deploy`.

**Re-anchored `65bb3330` -> `21429244` on 2026-09-27 (T-0072 merged onto `67caa4b8`, crew 1.0.48).** `21429244` is T-0072's crew 1.0.48 version commit on `T-0072-build`, on top of `80d4073b`, its merge of origin/main `67caa4b8` (T-0018 landed; this note was anchored at T-0018's `65bb3330`, and nothing outside the refresh artifacts changed between `65bb3330` and `67caa4b8`). Main's side of this note was taken in the merge and T-0072's earlier refresh replayed on top (`git apply --3way` of `bebbb97f..b1ec6877`); every citation into a file either side changed was mapped with a line diff (main -> merged for main's text, `b1ec6877` -> merged for T-0072's) and each one that moved was re-read with `sed -n`. `git diff --name-only 65bb3330 21429244`, outside the refresh artifacts, returns only T-0072's files: `crew_autopilot.py` (1063 -> 1230 lines: the `deploy-allowed` docstring section and functions, and its parser at `:1140`), `CONFIG.md` (+56), `CHANGELOG.md` (+31 at the top), `commands/autopilot.md` (the settings sentence rewrapped at `:44-47`, still 100 lines), `crew_state.py` (line-neutral at `:1086-1090`), `config.template.json`, `crew-setup/SKILL.md` (`:170`), `.crew/verify.json` (rule 27 `:293-301`, same lines: `test_crew_autopilot_deploy.py` joins its paths and run), the version files (1.0.48 at `.claude-plugin/marketplace.json:218`, `plugin/crew/.claude-plugin/plugin.json:3`, `plugin/PLUGINS.md:14`), `plugin/crew/BUDGETS.md:11` (18,905 lines across 126 files, re-measured on the merge), and the autopilot tests. `CHANGELOG.md` gained T-0072's 1.0.48 entry above T-0018's (cited by name); the `docs/runbooks/INDEX.md` mention in `plugin/crew/README.md` is still `:2067`; `.crew/verify.json` rules 27, 28 and 29 are still `:293-301`, `:302-309` and `:310-318`. Nothing was executed for this note.

**Re-anchored `21429244` -> `53855ea5` on 2026-09-27 (T-0072 review round 3).** `53855ea5` is T-0072's review-round-3 fix commit on `T-0072-build`. `git diff --name-only 21429244 53855ea5`, outside the refresh artifacts, returns only T-0072's files: `.crew/verify.json` (rule 27's `seconds` 16 -> 20 and its `why`, in place, still `:293-301`), `CHANGELOG.md` (T-0072's 1.0.48 entry, +4 lines, cited without a line), `plugin/crew/BUDGETS.md` (`:11`, in place: 18,908 lines across 126 files, which `check-marketplace.py` verifies), `plugin/crew/CONFIG.md` (one §20 table row edited in place at `:2309`, +3 lines after `:2327`), `plugin/crew/hooks/scripts/crew_autopilot.py` (1230 -> 1252 lines: +2 in the docstring at `:90-97`, `_cannot_exclude` and `_incident(root)` at `:702-718`, `_cli_value` at `:1132`, the `deploy-allowed` printing at `:1214-1219`), `plugin/crew/tests/sabotage_autopilot.py` (+36 at `:300-335`: eight `DEPLOY_MUTATIONS`; one re-anchored in place at `:256`) and `plugin/crew/tests/test_crew_autopilot_deploy.py`. No crew version change (1.0.48). Of the paths this note cites, `CHANGELOG.md` (T-0072's entry, cited by name), `.crew/verify.json` (rule 27 in place, `:293-301`) and `plugin/crew/BUDGETS.md:11` (in place) changed. `docs/` did not. Nothing was executed for this note.

**Re-anchored `8de3c669` -> `80326b1d` on 2026-09-27 (T-0072 merged onto `d2fbd408`, then review round 4's redesign, crew 1.0.49).** `ba7d5c52` merged origin/main `d2fbd408` (T-0024 landed as crew 1.0.48 at `8de3c669`) into `T-0072-build` and took main's side of every code map; T-0072's earlier refresh (`git diff 67caa4b8 2fa75f79 -- .crew/codemap/`) was replayed on top with `git apply --3way`, conflicting provenance sections keeping both sides, main's first. `80326b1d` is T-0072's crew 1.0.49 version commit, after the redesign `35733d76` (one root per answer, a tri-state path probe, a two-stage CLI fallback), its sabotage `fa4c8397`, its docs `8a40dd2c` and the rule-27 re-price `37fa7c97`. `git diff --name-only 8de3c669 80326b1d`, outside the refresh artifacts, returns only T-0072's files: `.claude-plugin/marketplace.json` (`:218` 1.0.49), `.crew/verify.json` (rule 27 in place, `:293-301`, `seconds` 16), `CHANGELOG.md` (T-0072's entry, +45 at the top), `plugin/PLUGINS.md` (`:14` 1.0.49, `:128` the `/crew:autopilot` row in place), `plugin/crew/.claude-plugin/plugin.json` (`:3`), `plugin/crew/BUDGETS.md` (`:11`, 18,939 lines across 126 files, which `check-marketplace.py` verifies), `plugin/crew/CONFIG.md` (2328 -> 2382 lines: the leaf paragraph `:130`, the key table `:803`, the `prodUnattended` row `:1261`, `:2282`, and section 20's closing "Production without asking" block from `:2297`), `plugin/crew/README.md` (`:866` in place), `plugin/crew/commands/autopilot.md` (`:45-48` in place, 100 lines), `crew_autopilot.py` (1312 lines), `crew_state.py` (line-neutral at `:1086-1090`), `crew-setup/SKILL.md` and `config.template.json` (the leaf), `test_crew_config.py` (`:282` asserts 123), `sabotage_autopilot.py`, `test_crew_autopilot.py` and `test_crew_autopilot_deploy.py`. `plugin/crew/README.md` changed in place at `:848` only; the README lines this note cites did not move. `CHANGELOG.md` gained T-0072's entry at the top (+45), which this note cites without a line. No citation moved. Nothing was executed for this note.

**Re-anchored `80326b1d` -> `1b5b6560` on 2026-09-27 (T-0072 test fix).** `git diff --name-only 80326b1d 1b5b6560`, outside the refresh artifacts, returns only `plugin/crew/tests/test_crew_autopilot_deploy.py` (the layer_state repro now patches `crew_config.layer_state`, not `crew_state.read_text`, which `test_module_split.py` forbids) and the three version files, stepped back to 1.0.48 and re-set to 1.0.49 so the version stays the last `plugin/crew/` commit (same content as at `80326b1d`). This note cites that test file by name only. No citation moved. Nothing was executed for this note.

**Re-anchored `1b5b6560` -> `a4eb2f55` on 2026-09-28 (T-0072 merged onto `5050ea3b`, crew 1.0.50).** `a4eb2f55` is T-0072's crew 1.0.50 version commit on top of its merge of origin/main `5050ea3b` (T-0077 landed as crew 1.0.49 at `fc289446`; shipstation 1.1.1). The merge was clean. `git diff --name-only 1b5b6560 a4eb2f55`, outside the refresh artifacts, returns main's T-0077 and shipstation files - `crew_tracker.py` (+123: Windows now holds a vault write's directories by handle, `_hold_dirs` / `_held_check` replace `_parent_check`), `crew_autopilot.py` (`_rel` +6 at `:170`, so every later line moves by 6), `sabotage_autopilot.py` (+5 inside `STATUS_MUTATIONS`; the `+=` append moved `:639` -> `:644`), `sabotage_tracker.py` (87 `TRACKER_MUTATIONS`, was 81), `plugin/crew/README.md` (`:1511-1513` in place), `test_crew_tracker.py`, `test_crew_autopilot.py`, `test_crew_autopilot_status.py`, `skills/shipstation/*` - and the version files (1.0.50 at `.claude-plugin/marketplace.json:218`, `plugin/crew/.claude-plugin/plugin.json:3`, `plugin/PLUGINS.md:14`) and `CHANGELOG.md` (T-0077's and shipstation's entries under T-0072's). `plugin/crew/README.md` changed in place at `:1493-1495` only, which this note does not cite; `CHANGELOG.md` is cited without a line. No citation moved. Nothing was executed for this note.

**Re-anchored `a4eb2f55` -> `0f488706` on 2026-09-28 (T-0072 review round 5).** `0f488706` is T-0072's review-round-5 fix commit. `git diff --name-only a4eb2f55 0f488706`, outside the refresh artifacts (`0282cb5c`, `37fa2322`), returns only T-0072's files: `plugin/crew/hooks/scripts/crew_autopilot.py` (`_resolve_root` +4 at `:729`, refusing a root that is not text, so every line after it moves by 4: `_layer_problem` `:744`, `_decide` `:759`, `deploy_allowed` `:836`, `_failure` `:1170`, `_cli_deploy` `:1194`, `main` `:1225`; `--json` dumps without indent, in place; the module docstring re-worded in place, `:87-104`), `plugin/crew/tests/sabotage_autopilot.py` (+30 inside `DEPLOY_MUTATIONS`, 64 entries by `len()`: the `AUTOPILOT_MUTATIONS + DEPLOY_MUTATIONS` append moved `:443` -> `:473`, `STATUS_MUTATIONS`' `:644` -> `:674`), `plugin/crew/tests/test_crew_autopilot_deploy.py`, `plugin/crew/CONFIG.md` (one sentence in section 20 re-worded in place, `:2331-2333`, no line added) and `CHANGELOG.md`. This note cites those files by name or at lines above the change; no citation moved. No suite was executed for this note.

## Re-anchor provenance - `65bb3330` + `8314d670` -> `c817782f`, 2026-09-27 (T-0010-solo merges `67caa4b8`)

`c817782f` is T-0010's crew 1.0.48 version commit on top of `d1e119d2`, T-0010-solo's merge of
origin/main `67caa4b8` (T-0018 landed as 1.0.47; its code maps anchored `65bb3330`), and
`3e2c9962`, the reconciliation under the owner's approve carve-out. Main's side of this note was
mapped from `65bb3330`, T-0010's side from its own anchor (`8314d670`), to `c817782f` with `difflib`
over every cited file, a bare `:N` taken as the last path named in its section; sections headed
provenance (and localgpu's re-derivation record) were left as written. The two mapped texts were
then merged three-way from `f0b12ee6`. Between `65bb3330` and `c817782f` the cited paths that
changed are T-0010's: `crew_autopilot.py`, `crew_ticket.py`, `scope_guard.py`, `crew_state.py`
(four `AUTOPILOT_DEFAULTS` lines at `:1094`, so every later line moved by 4), `commands/autopilot.md`,
the version files, `BUDGETS.md`, README, CONFIG.md, the tests and sabotage modules, and
`.crew/verify.json` (rule 28 inserted at `:302-308`, so rules 29 and 30 moved down by 7).

The verify rules this note lists were renumbered by hand (T-0010's rule 28 at
`.crew/verify.json:302-308`, tracker `:309-316`, routing `:317-325`); `plugin/crew/README.md:2090`
is unmoved. The two rebuilt guides (daily-workflow, troubleshooting) are T-0010's approve-exception
sentences, rebuilt with `docs/guides/crew/src/build.py`.

## Re-anchor provenance - `c817782f` -> `926443d8`, 2026-09-27 (T-0010 review round 3 fixes)

`git diff --name-only c817782f 926443d8` is T-0010's round-3 fix (`caabb005`), the BUDGETS.md
count, the version step-back and re-set, and this refresh. Of the paths this note cites, `plugin/crew/README.md`, `plugin/crew/CONFIG.md` and
`plugin/crew/BUDGETS.md` changed: README two lines rewritten in place (`:792`, `:818`),
CONFIG.md's §20 one-writer paragraph grew six lines, and `BUDGETS.md:11`'s count moved
18,917 -> 18,923 on the same line. No citation this note makes moved (checked with `difflib`
over every cited path). Nothing was executed.

## Re-anchor provenance - `926443d8` + `8de3c669` -> `50a275ea`, 2026-09-28 (T-0010's successor merges `f96e9ec9`)

`ab85880b` merges origin/main `f96e9ec9` (T-0024 landed as crew 1.0.48, its code maps anchored
`8de3c669`; T-0077 as 1.0.49) into T-0010-solo `216ee85f`; `a2f4db76` fixes review round 4's
three FIXes; `3438dc9a` merges `5050ea3b` (shipstation only); `48b2820d` re-measures
`plugin/crew/BUDGETS.md` and `50a275ea` sets crew 1.0.50. The merge took main's side of this
note; it was then re-merged three-way from `67caa4b8`, T-0010's side at `216ee85f` (anchor
`926443d8`) and main's at `f96e9ec9` (anchor `8de3c669`), both sides' provenance kept, main's
first. Every body citation into a file changed since its side's own anchor was mapped with
`difflib` (a bare `:N` taken as the last path named in its section) and each one that moved was
re-read at `50a275ea`.

The verify rules this note lists were renumbered by hand: T-0010's rule 28 (`:302-308`),
tracker 29 (`:309-316`), routing 30 (`:317-325`) and T-0024's approval rule 31 (`:327-334`, rule
30 on main). `plugin/crew/README.md:2098` (`:2093` on main) was re-found by its text. No guide
source changed, so the daily-workflow and troubleshooting builds were not re-run.

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
`plugin/crew/README.md:2093` still holds the `docs/runbooks/INDEX.md` sentence; no citation moved.
Nothing was executed for this note.

**Re-anchored `0f488706` -> `9631c707` on 2026-09-28 (T-0072 landing, crew 1.0.51).** `9631c707` is T-0072's landing bump on `T-0072-land`, after `34af80ef` merged the reviewed `T-0072-build` (`a0978df6`) onto main `e6e10432` (T-0079 landed as crew 1.0.50) and `bf0c513a` re-priced verify rule 27. `git diff --name-only 0f488706 9631c707`, refresh artifacts aside, returns T-0079's files, the three version files, `CHANGELOG.md` and `.crew/verify.json`. The two this note's citations reach changed in place: `.crew/verify.json` `:298` and `:301` (rule 27's `seconds` 16 -> 18 and its `why`, still `:293-301`) and `plugin/crew/README.md` `:738` and `:742` (T-0079's verdict table, line-neutral); no citation moved. The version sentence moves to 1.0.51. No suite was executed for this note.

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
`plugin/crew/README.md:2135` became `:2145` (same text, re-read); every other README citation here is
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
at `7d217751` with `sed -n`/`grep -n`; `plugin/crew/README.md:2210` (`docs/runbooks/INDEX.md`) holds from the merge;
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
moved one checked by content at `8cabe586`; `plugin/crew/README.md:2210` holds (T-0077's three README lines are above it and
net zero); `CHANGELOG.md` gained T-0077's entry after T-0075's and T-0024's. The three crew
diagrams were re-anchored to `8cabe586` in the same change. Nothing was executed for this note.

## Re-anchor provenance - `8cabe586` + `81685adf` -> `3724731b`, 2026-09-28 (T-0075 review round 3, merge of `e6e10432`)

`3036dc02` is T-0075's review-round-3 fix (`crew_config.py`, `crew_config_files.py`,
`crew_config_menu.py`, their three test files, `sabotage_config.py`, and `README.md`, `CONFIG.md`,
`commands/config.md`, `config-menu.md`, `global-config.md`, `CHANGELOG.md`); `6d5f0b61` merges
origin/main `e6e10432` (T-0079 landed as crew 1.0.50: `review_prompt.py`, `review_run.py`,
`review_verdict.py`, `agents/reviewer.md`, their tests, `sabotage_review.py`,
`sabotage_webtest.py`, `test_webtest_guard.py`, `README.md`, `CHANGELOG.md`; its notes anchored
`81685adf`); `3724731b` re-bumps crew to 1.0.51 (`plugin.json`, `marketplace.json`,
`plugin/PLUGINS.md`, `plugin/crew/BUDGETS.md`, `CHANGELOG.md`). The merge's conflicting provenance
sections kept both sides, main's first; anchor lines kept T-0075's and are replaced here.

`plugin/crew/README.md`'s `docs/runbooks/INDEX.md` sentence moves `:2169` -> `:2187` (T-0079's and
round 3's README lines above it); re-read with `sed -n`. No other citation moved (script over every
explicit `path:N`). The three crew diagrams are re-anchored in the same change. Nothing was executed.

## Re-anchor provenance - `3724731b` + `9631c707` -> `938e3b11`, 2026-09-28 (T-0075 review round 4, merge of `f54af3fa`)

`7d473f24` merges origin/main `f54af3fa` (T-0072 landed as crew 1.0.51: `crew_autopilot.py`,
`commands/autopilot.md`, `crew_state.py`'s line-neutral `AUTOPILOT_DEFAULTS` hunk at `:1086-1090`,
`templates/config.template.json`, `skills/crew-setup/SKILL.md`, `CONFIG.md` §20, `README.md`, its
tests, `sabotage_autopilot.py`, `.crew/verify.json` rule 27's `seconds` and `why`; its notes
anchored `9631c707`); `07354a39`, `df419a55`, `7a206c8e`, `4112498e`, `1b31ed2f` and `7ef3c4f1` are
T-0075's review-round-4 steps 11-16 (`crew_config.py`, `crew_config_files.py`,
`crew_config_menu.py`, their three test files, `sabotage_config.py`, `README.md`, `CONFIG.md`,
`skills/crew-setup/config-menu.md`, `CHANGELOG.md`, `plugin/crew/BUDGETS.md`); `938e3b11` re-bumps
crew to 1.0.52 (`plugin.json`, `marketplace.json`, `plugin/PLUGINS.md`, `CHANGELOG.md`). The merge's
conflicting provenance kept both sides; anchor lines kept T-0075's and are replaced here.

`plugin/crew/README.md`'s runbook-index sentence moves `:2187` -> `:2196` (the round-4 delete and
restore bullets in §11 sit above it). No other citation moved.

Checked by a script mapping every `path:N` citation outside provenance sections, and every bare `:N`
carried from the last path named in its paragraph, from both `3724731b` and `9631c707` to the tree
at `938e3b11` (difflib equal blocks); every citation neither base maps to itself was read with `sed
-n` / `grep -n`. The script attributes some bare `:N` to the wrong file (a `crew_autopilot.py`
citation after an `autopilot.md` mention, a `plugin.json:3` in another plugin); those were read and
hold. Nothing else was executed for this note.

**Re-anchored `9631c707` -> `b5c37635` on 2026-09-28 (T-0087, crew 1.0.52).** `b5c37635` is T-0087's crew 1.0.52 bump on `T-0087-build`, after `d05727af` merged main `f54af3fa` (T-0072 landed as crew 1.0.51). `git diff --name-only 9631c707 b5c37635`, refresh artifacts aside, returns T-0087's files (the review/gate harness, its tests, the golden corpus, `scripts/check-tooling-pr.py`, rule 31 in `.crew/verify.json`, `CLAUDE.md`'s tooling-alone bullet, the docs and guides) plus the three version files and `CHANGELOG.md`. Every body citation into `plugin/crew/README.md` below the refund paragraph moved +5 (re-mapped by script and re-read), and `CLAUDE.md:147` -> `:154`; citations inside provenance sections are history and were not touched. Its citations of the three version lines (`.claude-plugin/marketplace.json:218`, `plugin/crew/.claude-plugin/plugin.json:3`, `plugin/PLUGINS.md:14`) changed in place and now read 1.0.52. Nothing was executed for this note.

**Re-anchored `b5c37635` -> `1da1233d` on 2026-09-28 (T-0087, crew 1.0.52).** `1da1233d` is T-0087's crew 1.0.52 bump re-set after two reflow commits: `4648581a` rewrapped `plugin/crew/commands/review.md` to its 551-line allowance and `plugin/crew/commands/autopilot.md` to its 100-line budget, and `4304a9da` kept the sabotage anchor "are the human's. Go back" on one line (no rule changed in either). `git diff --name-only b5c37635 1da1233d`, refresh artifacts aside, returns those two command files and the three version files, which read 1.0.52 on both sides. This note cites neither file by line. Nothing was executed for this note.

**Re-anchored `1da1233d` -> `0d331967` on 2026-09-28 (T-0087, crew 1.0.52).** `0d331967` adds `plugin/crew/BUDGETS.md` to `scripts/check-tooling-pr.py`'s `ALONGSIDE` (its line count moves with every crew doc edit, and the checker refused this branch's own re-measure) and the `harness+budgets` must-allow case to `scripts/_test/tooling-pr.py`, red first (7 passed, 1 failed), then 8 passed. `git diff --name-only 1da1233d 0d331967`, refresh artifacts aside, returns those two scripts and `CHANGELOG.md`, plus the 1da1233d..08ed88a5 changes (`plugin/crew/BUDGETS.md`, `plugin/crew/tests/sabotage_refresh.py`, version files unchanged net). This note cites neither script by line. Nothing was executed for this note.

**Re-anchored `0d331967` -> `c8cc69ec` on 2026-09-28 (T-0087, now crew 1.0.53).** Main moved: `c426c018` (T-0076, the crew suite on native Windows) landed as crew 1.0.52, so T-0087 merged it with a merge commit (no conflict) and re-bumped to 1.0.53 at `c8cc69ec`. `git diff --name-only 0d331967 c8cc69ec`, refresh artifacts aside, returns T-0076's files (`plugin/crew/hooks/scripts/crew_context.py` +4 at `:1086`, where `emit` now forces LF stdout; `plugin/crew/tests/crew_fixtures.py`, `review_fixtures.py`, `sabotage_context.py` and nine test files; `scripts/_test/uv-install.sh`; one `plugin/crew/README.md` table cell; its `CHANGELOG.md` entry), the README refund paragraph's version text, and the three version files. Every body `path:N` citation into those files was mapped by script (difflib over the two blobs) and every bare `:N` after one of their names was listed and read: none moved. Nothing was executed for this note.
**Re-anchored `9631c707` -> `22399a9c` on 2026-09-28 (T-0085, crew 1.0.52).** `22399a9c` is T-0085's version commit on `T-0085-build` (the change is `d02fe008`, from origin/main `f54af3fa`). T-0085 adds `docs/adr/0004-build-time-development-standards.md`, edits `docs/guides/crew/src/daily-workflow.md` and `working-with-codex.md` and rebuilds their HTML, DOCX and PDF (`docs/guides/crew/src/build.py`, LibreOffice on this host), re-draws `docs/diagrams/process-crew-lifecycle.mmd` (a self-check node and the review's exit-2 edge) and re-anchors `data-flow-crew-config.mmd`, adds 18 lines to `plugin/crew/README.md` (the self-check paragraph after `:712` and a "Development standards" section at `:752`), and edits the skills figure in `README.md`, `plugin/PLUGINS.md` and the marketplace description. Every body citation into a changed file was compared by script at both commits; the runbook-index line moved `:2075` -> `:2093`, and the skills figure is annotated above. Nothing was executed for this note.

**Re-anchored `22399a9c` -> `2aa49bb8` on 2026-09-28 (T-0085 merged onto main `c426c018`, crew 1.0.53).** `c49f3aca` merged origin/main `c426c018` (T-0076 landed as crew 1.0.52) into `T-0085-build`, one mechanical conflict (the crew description's skills count in `.claude-plugin/marketplace.json`, kept at 30), and `2aa49bb8` bumped crew to 1.0.53. `git diff --name-only 22399a9c 2aa49bb8`, refresh artifacts aside, returns T-0076's files (`plugin/crew/hooks/scripts/crew_context.py`, four lines added inside `emit()` at `:1086-1089`; `plugin/crew/README.md`, one line in place; `scripts/_test/uv-install.sh`; eleven test files) and the version files. Every body citation into a changed file was compared by script at both commits; none moved; the two re-anchored diagram headers keep the `%% Generated from <repo>@<sha> on <date>.` form. No suite was executed for this note.

**Re-anchored `9631c707` -> `051f9e85` on 2026-09-28 (T-0091).** `051f9e85` is T-0091's one commit on `T-0091-build`, off main `f54af3fa`. `git diff --name-only 9631c707 f54af3fa -- <every tracked path this note cites>` is empty; `f54af3fa..051f9e85` changes only `CLAUDE.md` (the Landmines truncating-`open` entry's measurement paragraph, now `:185-212`, +28/-18, so every later line moves +10) and `TODO.md` (one entry closed at `:4473`, three lines appended at `:4480-4482`). This note's `CLAUDE.md:147` ("Decisions in `docs/adr/`") sits above the changed paragraph and holds (re-read); its `TODO.md` citations (`:1190`, `:1201`) sit above `:4473` and hold. No claim moved. Nothing was executed.

**Re-anchored `051f9e85` -> `c192b83d` on 2026-09-28 (T-0091 review round 1).** `c192b83d` is T-0091's review-round-1 fix on `T-0091-build`. `git diff --name-only 051f9e85 c192b83d` returns only `CLAUDE.md`: the same Landmines truncating-`open` measurement paragraph, now `:185-219` (+16/-9, so every later line moves +7; lines above `:192` are byte-identical). This note's `CLAUDE.md:147` sits above the paragraph and holds (re-read). No claim moved. Nothing was executed.

**Re-anchored `9631c707` -> `c99e31f6` on 2026-09-28 (T-0092, crew 1.0.52).** `c99e31f6` is T-0092's crew 1.0.52 version commit on `T-0092-build`, cut from main `f54af3fa` (T-0072's landing merge, whose only commit past `9631c707` is the refresh `f1f118de`). `git diff --name-only 9631c707 c99e31f6`, refresh artifacts aside, returns T-0092's files: `plugin/crew/hooks/scripts/review_patch.py` (+8: the docstring paragraph on `graphify-out/` and one comment line; `EXCLUDED` / `_EXCLUDE_SPEC` now at `:104-105`), `plugin/crew/hooks/scripts/review_prompt.py` (+4: one docstring line and the `excluded` line at `:89-91`, so `:84` -> `:85` and `:239` -> `:243`), `test_review_patch.py`, `test_review_prompt.py`, `sabotage_review.py`, line-neutral edits to `plugin/crew/README.md` (`:726`, `:860`), `plugin/crew/commands/review.md` (`:328-332` reflowed in place), `crew_autopilot.py` (`:55-56`), `completion_audit.py` (`:74-75`) and `TODO.md` (`:5048`), `CHANGELOG.md` (+26 at the top) and the three version files (1.0.52 at `.claude-plugin/marketplace.json:218`, `plugin/crew/.claude-plugin/plugin.json:3`, `plugin/PLUGINS.md:14`). Every body citation of the form `path:line` into those files was compared by script between `9631c707` and `c99e31f6`. The only differing citations are the version-file lines, changed in place, which the provenance notes cite with the value at their own commit. No citation moved. Nothing was executed for this note.

**Re-anchored `c99e31f6` -> `3c4f1a68` on 2026-09-28 (T-0092 merged onto `c426c018`, crew 1.0.53).** `95cc12cf` merged origin/main `c426c018` (T-0076 landed as crew 1.0.52 at `e329eb8f`) into `T-0092-build`; the merge was clean (both sides had set the version files to 1.0.52). `3c4f1a68` re-bumps crew to 1.0.53 and moves T-0092's four `1.0.52` mentions (`review_patch.py`'s docstring, `plugin/crew/README.md:860`, `TODO.md:5048`, the two test-file comments) to 1.0.53, all in place. `git diff --name-only c99e31f6 3c4f1a68`, refresh artifacts aside, returns T-0076's files - `plugin/crew/hooks/scripts/crew_context.py` (+4 inside `emit`, so `sys.stdout.write` moves `:1086` -> `:1090`), `plugin/crew/README.md` (`:1691` in place), `scripts/_test/uv-install.sh` and twelve test files - plus `CHANGELOG.md` (T-0076's entry merged below T-0092's) and the version files. Every body citation of the form `path:line` into those files was compared by script between `c99e31f6` and `3c4f1a68`: the only differences are version-file lines changed in place and `CHANGELOG.md` lines inside dated provenance notes, left as history; nothing here cites `crew_context.py` at or below `:1104`. Nothing was executed for this note.

**Re-anchored `c192b83d` / `3c4f1a68` -> `25d2de63` on 2026-09-28 (T-0092 merged onto `f8b6c8d7`, T-0091, crew 1.0.53).** `25d2de63` merges origin/main `f8b6c8d7` (T-0091 landed at `c192b83d`: `CLAUDE.md`'s Landmines paragraph and a `TODO.md` entry, no plugin bumped) into `T-0092-build`. The code-map, INDEX, rules, diagram and graph conflicts were resolved mechanically - both sides' provenance notes kept, main's first; the anchor taken from this note. Every body citation of the form `path:line` was compared by script twice: `c192b83d` -> `25d2de63` differs only on T-0092's own lines (the exclusion, the re-pointed `review_prompt.py` lines, `plugin/crew/README.md:860` in place, the version lines), and `3c4f1a68` -> `25d2de63` only on T-0091's `CLAUDE.md` lines, which T-0091's own notes above cite at `c192b83d`, and on `TODO.md:5048`, cited in T-0092's notes above as that commit's line: T-0091's three added lines move the bullet to `:5051`. Nothing was executed for this note.

**Re-anchored `25d2de63` -> `136f4b33` on 2026-09-28 (T-0092 merged onto `ff59160f`, T-0089, crew 1.0.54).** `e2220836` merges origin/main `ff59160f` (T-0089 landed as crew 1.0.53 at `0f526a8c`: `plugin/crew/tests/test_role_write_guard.py` fixtures and a `CHANGELOG.md` entry) into `T-0092-build`; the merge was clean. `136f4b33` re-bumps crew to 1.0.54 and moves T-0092's `1.0.53` mentions (`review_patch.py`'s docstring, `plugin/crew/README.md:860`, `TODO.md:5051`, the two test-file comments, its `CHANGELOG.md` heading) to 1.0.54, all in place. Every body citation of the form `path:line` into a file changed between `25d2de63` and `136f4b33` was compared by script: the only differences are version-file lines changed in place, `plugin/crew/README.md:860` in place, and lines cited inside dated provenance notes (`CHANGELOG.md`, which T-0089's entry shifts by 12 lines below `:80`, and `TODO.md:5048`), left as history at their own commit. No citation into `test_role_write_guard.py` exists here. Nothing was executed for this note.

## Re-anchor provenance - `938e3b11` + `136f4b33` -> `3648f59a`, 2026-09-28 (T-0075 review round 5, merge of `6387ab49`)

`9420bc16` merges origin/main `6387ab49` into `T-0075-build`: T-0076 (crew 1.0.52, `crew_context.py`'s byte-exact LF), T-0091 (`CLAUDE.md`'s Landmines paragraph, a `TODO.md` entry), T-0089 (crew 1.0.53, `test_role_write_guard.py` fixtures), T-0090 (mcp-servers 0.2.1, `SECURITY.md`) and T-0092 (crew 1.0.54: `review_patch.py` / `review_prompt.py` leave `graphify-out/` out of the review bundle), whose notes above are anchored `136f4b33`, `2442d367`, `c192b83d` or `b2553d26`. `faf4b0db`, `e7825a0e`, `04e3a01c`, `517628b9` and `d1460d77` are T-0075's review-round-5 steps 18-22 (`crew_config.py`, `crew_config_files.py`, their three test files, `sabotage_config.py`, `README.md`, `CONFIG.md`, `CHANGELOG.md`, `plugin/crew/BUDGETS.md`); `3648f59a` re-bumps crew to 1.0.55 (`plugin.json`, `marketplace.json`, `plugin/PLUGINS.md`, `CHANGELOG.md`). The merge's conflicting provenance kept both sides, T-0075's `## Re-anchor provenance` sections first and main's `**Re-anchored ...**` paragraphs after them; the anchor line kept T-0075's and is replaced here.

`plugin/crew/README.md`'s runbook-index sentence moves `:2196` -> `:2199` (round 5's three README lines above it), added at the head of its per-commit list. No other body citation moved.

Checked by a script mapping every `path:N` citation outside provenance sections, and every bare `:N` carried from the last path named in its paragraph, from `938e3b11` for a line in T-0075's copy of this note and from `6387ab49` for a line only in main's, to the tree at `3648f59a` (difflib equal blocks); every citation that did not map to itself was read with `sed -n` / `grep -n`. The script attributes some bare `:N` to the wrong file (a `.crew/verify.json` range after a test-file mention, a `check-marketplace.py` range after a `PLUGINS.md` mention, a `SKILL.md` in another skill); those were read and hold. A citation inside a list of per-commit positions keeps its commit's line; only the current position is added. Nothing else was executed for this note.

## Re-anchor provenance - `50a275ea` + `81685adf` -> `360c4029`, 2026-09-28 (T-0010-solo merges T-0079's `e6e10432`)

`c312702b` merges origin/main `e6e10432` (T-0079 landed as crew 1.0.50, its code maps anchored
`81685adf`) into T-0010-solo `ac0b5151`; `360c4029` sets crew 1.0.51. The artifact conflicts were
anchor, version and provenance lines only: T-0010's side kept for anchors and body (its
`crew_autopilot.py` and `commands/autopilot.md` line numbers are this tree's), both sides'
provenance kept. `git diff --name-only 50a275ea 360c4029`, refresh artifacts aside, is T-0079's files
(`review_verdict.py`, `review_prompt.py`, `review_run.py`, `agents/reviewer.md`, their tests and
sabotage modules, identical to origin/main's), `plugin/crew/README.md` (two lines rewritten in
place, `:735` and `:739`, line-neutral), `CHANGELOG.md` and the version files. Every citation into
T-0079's files equals main's note at `81685adf` (compared by script). No test was run by this note.

## Re-anchor provenance - `360c4029` + `136f4b33` -> `d7c7c75c`, 2026-09-28 (T-0010-solo merges `6387ab49`)

`597a62b0` merges origin/main `6387ab49` into T-0010-solo `dbb22712`: T-0072 landed as crew
1.0.51, T-0076 as 1.0.52, T-0089 as 1.0.53 and T-0092 as 1.0.54, with T-0090 (mcp-servers 0.2.1)
and T-0091 (`CLAUDE.md`) beside them; main's code maps were anchored `136f4b33`. After it,
`bd066a97` moves `settings`' two policies to a second text line (T-0072's
`test_settings_line_names_deploy` pins the first line exactly), `ab85fed0` puts `deploy-allowed`
in T-0010's only-writer test, `250c6df7` rewraps one docstring line in place, `130bf67e` re-sets
crew 1.0.55 and `d7c7c75c` re-prices `.crew/verify.json` rule 29 in place (20 -> 21). The merge
took main's side of this note; it was then re-merged three-way from `e6e10432`, T-0010's side at
`dbb22712` (anchor `360c4029`) and main's at `6387ab49`, both sides' provenance kept, main's
first. Every body `path:line` citation into a file changed since its side's commit was mapped to
`d7c7c75c` with `difflib` (a bare `:N` taken as the last file named earlier in its paragraph);
a citation followed by `at <sha>`, `before` or `->`, and every provenance section, was left as
written. A citation inside a changed hunk cannot be mapped that way and was left as written unless
this section names it.

The `.crew/verify.json` rules paragraph was resolved by hand: T-0010's policy rule is at
`:302-308`, the tracker rule `:309-316`, T-0023's route rule `:317-325` and T-0024's approval rule
`:327-334`, each re-read with `sed -n`. Nothing was executed for this note.

## Re-anchor provenance - `d7c7c75c` + `3648f59a` -> `cd106b8b`, 2026-09-28 (T-0010-solo merges T-0075's `e878cc31`)

`acbb0fb2` merges origin/main `e878cc31` into T-0010-solo `07032fc7`: T-0075 (`/crew:config` menu mode and
`/crew:config-setup`) landed as crew 1.0.59, its code maps anchored `3648f59a`. `92e0717a` re-measures
`plugin/crew/BUDGETS.md` (19,494 lines across 128 files) and rebuilds the troubleshooting guide's DOCX and
PDF; `cd106b8b` re-sets crew 1.0.60, one past main. The code merged without a conflict (T-0010 and T-0075 change
disjoint scripts); the conflicts were this note's anchor, provenance and a few cited lines. Both sides'
provenance was kept, main's first. Every body `path:N` citation was traced to the side whose copy of this
note carries its line (`07032fc7` or `e878cc31`) and mapped to `cd106b8b` through a `difflib` line diff
(`/root/crew-tmp/t-0010/citemap.py`, machine-local); each line that did not map to itself was read with
`sed -n` / `grep -n`. The script takes a bare `:N` as the last path named on its line, so some flags were
that misattribution (a `crew_ticket.py` or `review_ledger.py` line after another file's mention) and hold.

`plugin/crew/README.md:2245` (the runbooks-index sentence) was re-read with `grep -n`; the
troubleshooting guide's sources (`troubleshooting.md`, `auto-cycle.md`) merged both sides and
`docs/guides/crew/src/build.py --guide troubleshooting` reproduced the merged HTML byte-identically.
Nothing else was executed for this note.

## Re-anchor provenance - `cd106b8b` -> `bbd9a66d`, 2026-09-29 (T-0010 landing branch)

`T-0010-land` merges T-0010-solo `6b89c1df` into origin/main `2693d0fa` (README re-pin only past `e878cc31`,
so the merged tree is `6b89c1df` plus that README change). `08eeaa3e` adds the ruff fix-at-land lint fixes
(owner standing rule 2026-09-28; owner decision 2026-09-29 "Fix at land"): ISC004 parentheses in
`plugin/crew/hooks/scripts/crew_autopilot.py`, `plugin/crew/tests/sabotage_autopilot.py` and
`plugin/crew/tests/test_scope_guard.py`; `# noqa: BLE001` on five fail-closed broad excepts in
`plugin/crew/hooks/scripts/crew_autopilot.py`, `plugin/crew/hooks/scripts/crew_ticket.py` and
`plugin/crew/hooks/scripts/scope_guard.py`; an I001/RUF100/C0207 fix in
`plugin/crew/tests/test_crew_autopilot_policy.py`. `bbd9a66d` re-sets crew 1.0.61. Each edited line kept its
number (the parentheses and comments were added in place) except in `test_crew_autopilot_policy.py`, whose
import block lost one line; no note cites that file by line. Re-anchor only; nothing was executed for this note.

**Re-anchored `c8cc69ec` -> `c0768d0e` on 2026-09-28 (T-0087, crew 1.0.53).** `c0768d0e` is T-0087's merge of main `f8b6c8d7` (T-0091, no plugin version change) into `T-0087-build`; crew stays 1.0.53, one past main's 1.0.52, and `c8cc69ec` is still the last `plugin/crew` commit. `git diff --name-only c8cc69ec c0768d0e`, refresh artifacts aside, returns `CLAUDE.md` (T-0091's Landmines truncating-`open` measurement paragraph, +35/-18 at `:189`, so every later line moves +17) and `TODO.md`. Every other body `CLAUDE.md:N` citation here is at or above `:189`, or sits inside a dated re-anchor note that states the coordinates of its own commit, so none moved. Nothing was executed for this note.

**Re-anchored `136f4b33` / `c0768d0e` -> `379ab5e6` on 2026-09-28 (T-0087 merged onto `6387ab49`, crew 1.0.55).** `01dd3854` merges origin/main `6387ab49` into `T-0087-build`: T-0089 (crew 1.0.53, `plugin/crew/tests/test_role_write_guard.py`), T-0090 (mcp-servers 0.2.1: `SECURITY.md`, ten files under `mcp-servers/`) and T-0092 (crew 1.0.54: `graphify-out/` left out of review bundles - `review_patch.py`, `review_prompt.py`, `completion_audit.py`'s comment, `crew_autopilot.py`'s docstring, `commands/review.md`, `plugin/crew/README.md`, `TODO.md`, three test files). `379ab5e6` re-bumps crew to 1.0.55, one past main's 1.0.54, and moves T-0087's `1.0.53` mentions (`plugin/crew/README.md:743`, its `CHANGELOG.md` entry) to 1.0.55 in place. The code-map, INDEX, diagram, rules and graph conflicts were resolved mechanically - both sides' provenance notes kept, main's first; the version sentence, `.claude/rules/` and `graphify-out/` taken from main and then refreshed. Every body citation of the form `path:line` was re-mapped by script (difflib over each cited file, from the anchor of the side `git blame` puts the note line on, both anchors for a line common to both, never guessed): none moved in this map. Citations the script could not map, or where the two sides' anchors disagree on a line common to both, were not re-read here and are unchanged; they predate this merge (for example `CHANGELOG.md`'s "117 -> 119" is cited at `:654-655` on both sides and sits at `:909-910`), and this pass only re-anchors.

**Re-anchored `379ab5e6` -> `17fa035e` on 2026-09-28 (T-0087 review round 1, crew 1.0.55 unchanged - not yet released).** `bbe68e85` fixes review round 1: autopilot lets a refunded round's `/crew:review` rerun past its no-progress stop, rule 31 triggers on its suites and seam consumers, `scripts/check-tooling-pr.py` admits no production code or prompt alongside the harness (a `SEAM` consumer only with a `Tooling-seam:` trailer), `golden_build.redact` bounds both sides of a match, a malformed `successors` loads as corrupt, `review_run.py`'s summary line counts charged rounds, a worktree rename is parsed, and the guides stop calling a post-refund rerun free; `17fa035e` re-prices rule 31. `git diff --name-only 379ab5e6 17fa035e`, refresh artifacts aside, returns those scripts, their tests, one golden fixture, `.crew/verify.json`, `CLAUDE.md`, `CHANGELOG.md`, `plugin/crew/README.md`, `plugin/crew/BUDGETS.md`, `commands/autopilot.md`, `commands/review.md` and the troubleshooting guide. Body citations of the form `path:line` into those files were re-mapped by script (difflib over each cited file from `379ab5e6` to `bbe68e85`, only for note lines committed before this pass, never guessed): seven moved, all `CLAUDE.md` citations below the tooling-alone bullet (+2: `:154` twice, `:243`, `:244`, `:251`, `:256`, `:263`). Nothing else here moved.

## Re-anchor provenance - `bbd9a66d` + `17fa035e` -> `9e38a891`, 2026-09-29 (`T-0087-build` merges T-0010's `8ab733d7`)

`0fc7f609` merges origin/main `8ab733d7` (T-0010 landed as crew 1.0.61, its code maps anchored
`bbd9a66d`) into `T-0087-build` `674bc4e5` (T-0087's Windows-portability successor plan, Steps 1-5
built; its maps anchored `17fa035e`). After it, `ae448309` renames T-0087's harness rule to rule 32
in text and re-measures `plugin/crew/BUDGETS.md` (19,666 lines across 129 files), `167f69a0` says
the refund ships in 1.0.62 (README, CHANGELOG), `e537e4ce` re-sets crew 1.0.62, one past main, and
`9e38a891` rebuilds the daily-workflow and troubleshooting guides from their merged sources. The code
conflicts were `crew_autopilot.next_phase` (main's `policy` argument plus T-0087's refunded-rerun
pop), `sabotage.py`'s `MUTATIONS +=` line and `test_crew_autopilot.py` (both sides kept) and the
README's Stops line (main's text plus T-0087's refunded-review clause). The artifact conflicts took
main's side for body text and kept both sides' provenance, main's first. Every body `path:N`
citation was traced to the side whose copy of this note carries its line (`674bc4e5` or
`8ab733d7`) and mapped to this tree with a `difflib` line diff (`/root/crew-tmp/t-0010/citemap.py`
and `/root/crew-tmp/t-0087/citeapply.py`, machine-local). The script takes a bare `:N` as the last
path on its line; each misattribution it produced (a `crew_autopilot.py` line after a
`review_ledger.py` or `commands/autopilot.md` mention, a `.crew/verify.json` range after a
`sabotage.py` one, a historical `at <sha>` README line) was reverted or re-read by symbol with
`grep -n`. `crew_autopilot.py` is 1751 lines: T-0087's refund hunks add 16 lines from `:522`, so
main's citations at or past `:522` moved by 6 to 16 (`next_phase` `:556`, `settings` `:745`,
`deploy_allowed` `:943`, `main` `:1648`) and nothing above it moved. T-0087's `sabotage_tooling`
import at `plugin/crew/tests/sabotage.py:82` puts the `MUTATIONS +=` statement at `:3054-3057`
(refresh `:3054`; resume, autopilot, tracker and route `:3055`; policy, approval, config and tooling
`:3056`). `.crew/verify.json` is 33 rules and 370 lines: T-0087's harness rule is rule 32 at
`:340-365`, after T-0024's rule 31 at `:332-339`. Nothing was executed for this note; the suites ran
with the build.

In this note: the runbook-index README citation is `plugin/crew/README.md:2250` on this tree.

## Re-anchor provenance - `9e38a891` -> `78b7080a`, 2026-09-30 (`T-0087-build` merges T-0088's main `a61a6f38`)

`f702cb24` merges origin/main `a61a6f38` (T-0088 landed as crew 1.0.69, after #263-#267: crew 1.0.62-1.0.68's CI ruff and xdist changes, gate-first review, the steward skill and `crew-qa-standards`) into `T-0087-build`, with a merge commit; its conflicts were mechanical and both sides were kept. `a9bc8877` moves T-0087's version text to 1.0.70 and its harness rule to `.crew/verify.json` rule 35, `90b71bbf` re-sets crew 1.0.70, one past main's 1.0.69, and `78b7080a` rebuilds two guides. Every body citation of the form `path:line` was re-mapped by script (difflib over each cited file, from T-0087's `cb9b79b1` for a note line both parents carry and from `a61a6f38` for a line only main carries, to this tree; a bare `:N` binds to the last path named on its line, with or without a line number): 11 moved in this map and were set to this tree's lines. Citations the script could not attribute to a file that has that line (a bare `:N` after a different file's name, or a short name with no directory) predate this merge and were left unchanged. Re-anchor only: no other claim moved and nothing was executed for this note.

## Re-anchor provenance - `78b7080a` -> `b142d8e3`, 2026-09-30 (T-0087 review round 4 fixes)

`dc412c5c` limits the refunded-rerun marker to the `review` phase in `crew_autopilot._review_phase` (+2 lines, so every `crew_autopilot.py` line from `_toward_review` on moves by 2), with a must-block test and sabotage entry (ac); `b5f87132` re-maps `plugin/crew/docs/external-tool-formats.md`'s citations and adds a test that pins them; `af7eccbe` re-times `.crew/verify.json` rule 35 in place (no line moved); `b142d8e3` corrects a CHANGELOG figure. Every body citation of the form `path:line` was re-mapped by script (difflib from `78b7080a` to `b142d8e3`; a bare `:N` binds to the last path named on its line), and the `crew_autopilot.py` citations whose path is on the line above were re-mapped by hand. Citations the script could not attribute predate this change and were left unchanged. Re-anchor only: no other claim moved and nothing was executed for this note.
**Re-anchored `2aa49bb8` -> `b82035e6` on 2026-09-28 (T-0085 merges main `f8b6c8d7`, T-0091).** `17b70570` merged origin/main `f8b6c8d7` into `T-0085-build` (mechanical conflicts only: anchors, provenance paragraphs, INDEX history cells, generated rules and graph); `b82035e6` moves the crew skills claim at `plugin/README.md:414` and `INSTALLATION.md:252` from 29 to 30 (spec Touch amendment). Of the paths this note cites, `git diff --name-only 2aa49bb8 b82035e6` returns `CLAUDE.md`, `INSTALLATION.md` and `plugin/README.md`. `CLAUDE.md`'s change is T-0091's Landmines truncating-`open` paragraph, whose citations were moved on main's side and merged in, plus T-0085's four-line ignore-policy reflow, which shifts no line. Every `CLAUDE.md:N`, `INSTALLATION.md:N` and `plugin/README.md:N` citation was compared by script against its text at `2aa49bb8`, `c192b83d` and HEAD; the parenthesis saying both still read 29 is corrected in place. No suite was executed for this note.

**Re-anchored `136f4b33` -> `8a084c6c` on 2026-09-28 (T-0085 merges main `6387ab49`, T-0089, T-0090, T-0092; crew 1.0.55).** `f97219dc` merged origin/main `6387ab49` into `T-0085-build` (mechanical conflicts only: crew version lines, CHANGELOG, anchors, provenance paragraphs, INDEX history cells, diagram headers, generated rules and graph); `8a084c6c` re-bumps crew to 1.0.55, one past main's 1.0.54. Each side had already re-verified its own changes (main's line to `136f4b33`/`2442d367`/`b2553d26`, T-0085's to `b82035e6`), so this pass checks the files BOTH sides changed: the crew version lines (`.claude-plugin/marketplace.json:218`, `plugin/crew/.claude-plugin/plugin.json:3`, `plugin/PLUGINS.md:14`, value only, same line), `CHANGELOG.md` (both sections kept; release bookkeeping), `plugin/crew/README.md` and `plugin/crew/commands/review.md` (main's T-0092 edits are in place and line-neutral: 2883 and 551 lines, as on T-0085's side), `plugin/crew/hooks/scripts/review_prompt.py` (main's docstring line split in two at `:6-7` and three `excluded` lines added at `:96-98` shift T-0085's lines below them by 4) and `plugin/crew/tests/test_review_prompt.py`. Every `path:N` citation into those files was compared by script against its text on the side that wrote it (`f3ad630b` or `6387ab49`) and at the merged tree; none moved. Paragraphs dated before this one describe the tree at their own anchor and were not rewritten. No suite was executed for this note.

**Re-anchored `8a084c6c` -> `07bcaf3b` on 2026-09-28 (T-0085 review round 1 fixes).** `07bcaf3b` changes `plugin/crew/hooks/scripts/crew_standards.py` (`gate_applies`, `checklist_block`, `stamp`, `_plugin_sets`, the module docstring), its tests and sabotage entries, `.crew/standards.md` (REPO-03's rule text), `.crew/verify.json` (rule 31 gains two test files; its `seconds` and `why`), `CHANGELOG.md` (T-0085's bump bullet, two lines to three), `plugin/crew/BUDGETS.md:10-11` (the count, in place), `plugin/crew/README.md` (three table rows, in place), `plugin/crew/commands/implement.md` (two lines reflowed in place; still 120 lines), `plugin/crew/commands/review.md` (step 6's reviewer-cell line becomes three, so lines below `:530` move by 2), `plugin/crew/skills/crew-standards/SKILL.md`, ADR 0004 and the working-with-codex guide. Every `path:N` citation in this note into those files was compared by script between `8a084c6c` and `07bcaf3b`: every hit is a `plugin/crew/BUDGETS.md:11` citation inside an earlier dated provenance paragraph, left as history; no body claim moved. Paragraphs dated before this one describe the tree at their own anchor and were not rewritten. No suite was executed for this note.

**Re-anchored `07bcaf3b` -> `8abf7ffe` on 2026-09-28 (T-0085 provisional re-bump, crew 1.0.56).** `8abf7ffe` moves crew's version 1.0.55 -> 1.0.56 in place (`.claude-plugin/marketplace.json:218`, `plugin/crew/.claude-plugin/plugin.json:3`, `plugin/PLUGINS.md:14`), because the round-1 fixes changed `plugin/crew/` after 1.0.55 was set and `scripts/check-marketplace.py`'s version-drift check failed on it; it also rewords `.crew/standards.md` REPO-03 (the provisional bump) and T-0085's `CHANGELOG.md` heading and bump bullet (three lines to four). Every `path:N` citation in this note into those files was compared by script between `07bcaf3b` and `8abf7ffe`: the version-file citations hold (value changed in place, same line) and every hit sits inside an earlier dated provenance paragraph, left as history; no body claim states the version. Paragraphs dated before this one describe the tree at their own anchor and were not rewritten. No suite was executed for this note.

**Re-anchored `3648f59a` / `8abf7ffe` -> `e3f5fa49` on 2026-09-29 (T-0085 merges main `2693d0fa`, T-0075 landed as crew 1.0.59, and applies the owner-accepted round-1 standards amendments).** `0fd1bdf8` reverts T-0085's provisional crew 1.0.56 bump (`8abf7ffe`); `0fd92334` merges origin/main `2693d0fa` into `T-0085-build` (mechanical conflicts only: crew version lines take main's 1.0.59, crew counts take main's 36 commands with T-0085's 30 skills, `plugin/crew/tests/sabotage.py` registers both `CONFIG_MENU_MUTATIONS` and `STANDARDS_MUTATIONS`, anchors, provenance paragraphs, INDEX history cells, diagram notes, generated rules and graph); `e3f5fa49` amends GEN-01 and GEN-04 in `plugin/crew/skills/crew-standards/references/generic.md` and REPO-03 in `.crew/standards.md`, drops the version from T-0085's `CHANGELOG.md` heading and re-measures `plugin/crew/BUDGETS.md`. The build branch now declares main's 1.0.59 and carries no bump of its own (REPO-03 as amended). Every `path:N` citation outside provenance was mapped by script (difflib equal blocks; a same-size in-place replacement counts as the same line) from the side that wrote it - `3648f59a` for a line in main's copy of this note, `0fd1bdf8` for a line only in T-0085's - to `e3f5fa49`, and every line that did not map to itself was read with `sed -n` / `grep -n`; the script attributes some bare `:N` to the wrong file, and those were read and hold. `plugin/crew/README.md`'s runbook-index sentence moves `:2199` -> `:2217` (T-0085's README rows above it), added at the head of its per-commit list; the crew count sentence reads 36 commands with T-0085's 30-skill history. No other body citation moved. Paragraphs dated before this one describe the tree at their own anchor and were not rewritten. No suite was executed for this note.

**Re-anchored `e3f5fa49` -> `001f8a78` on 2026-09-29 (T-0085 successor plan, review round 2's fixes).** `bc3602df`..`001f8a78` change `plugin/crew/hooks/scripts/crew_standards.py` (`_scope` gains the merge-base fallback for a kept but unusable scope record, `_has_scope_entry` and `_noted` are new, so every definition from `_scope` down moves by +8 to +30 lines), its tests (`test_crew_standards.py`, `test_review_run_standards.py`, `test_lifecycle_commands.py`) and `plugin/crew/tests/sabotage_standards.py` (nineteen new entries; `STANDARDS_MUTATIONS` moves `:21` -> `:35`), `plugin/crew/skills/crew-standards/SKILL.md` (step 3, +5 lines), `plugin/crew/README.md` (one table row, in place), `CHANGELOG.md` (one bullet in T-0085's section, so every line below it moves +8) and `plugin/crew/BUDGETS.md:11` (the count, in place). Every `path:N` citation in this note into those files was mapped by script (difflib equal blocks; a same-size in-place replacement counts as the same line) from `e3f5fa49` to `001f8a78`; none moved. Two body claims were corrected, not re-anchored (review round 2 FIX 5): `docs/adr/` holds four ADRs, the fourth T-0085's `0004-build-time-development-standards.md` (re-checked with `ls docs/adr/`), where the note said three. Paragraphs dated before this one describe the tree at their own anchor and were not rewritten. No suite was executed for this note.

**Re-anchored `001f8a78` / `bbd9a66d` -> `a7f9c5e4` on 2026-09-29 (T-0085 merges main `8ab733d7`, T-0010 landed as crew 1.0.61).** `a7f9c5e4` merges origin/main `8ab733d7` (T-0010 landed as crew 1.0.61) into `T-0085-build` after T-0085's review round 3 fixes (`33521aa4`), with mechanical conflicts only: crew version lines take main's 1.0.61 with T-0085's 30 skills (the build branch carries no bump, REPO-03 as amended), `plugin/crew/tests/sabotage.py` registers `POLICY_MUTATIONS`, `APPROVAL_MUTATIONS`, `CONFIG_MENU_MUTATIONS` and `STANDARDS_MUTATIONS` on `:3056`, anchors, provenance (both sides kept, main's first), INDEX history cells, version sentences, diagram headers, generated rules and graph. Every body `path:N` citation was traced to the side whose copy of this note carries its line (`33521aa4` or `8ab733d7`) and mapped from that side's anchor to `a7f9c5e4` through a difflib line diff (`/root/crew-tmp/t-0085/citemap.py`, machine-local; only cited files that changed; a bare file name resolved when unique in `git ls-files`); each citation that did not map to itself was read with `sed -n` / `grep -n`, and the script's misattributed bare `:N` (a `sabotage_autopilot.py` or `crew_ticket.py` line after another file's name, a history list's earlier positions) were read and hold. `plugin/crew/README.md:2227` (the runbooks `INDEX.md` sentence) was set at the merge with `grep -n`; `plugin/README.md:414` and `INSTALLATION.md:252` changed in place on T-0085's side (29 -> 30 skills) and hold. The other `plugin/crew/README.md` hits on that history line are earlier positions, left as history. Paragraphs dated before this one describe the tree at their own anchor and were not rewritten. No suite was executed for this note.

**Re-anchored `a7f9c5e4` / `b4f39fd3` -> `69c7edbd` on 2026-09-30 (T-0085's landing merge of main `a61a6f38`, crew 1.0.70).** `69c7edbd` merges T-0085's build head `0c6f01e0` (round 4, owner-accepted) onto origin/main `a61a6f38` (crew 1.0.69: #263-#267 and T-0088) on `T-0085-land`, and sets crew 1.0.70. Every body `path:N` citation was mapped by script (`difflib` equal blocks, from the anchor of whichever side's copy of this note carries the line - `a7f9c5e4` for T-0085's, main's own anchor for main's - to `69c7edbd`); each that mapped to one new line was moved, and each that did not map, or mapped differently from the two sides, was read with `sed -n` / `grep -n`. The script attributes a bare `:N` to the last path cited with a line number, so a bare `:N` after a path named without one (`.crew/verify.json` rule ranges, `crew_tfplan.py`, `sabotage_autopilot.py`, `crew_ticket.py`, `crew_standards.py`) was read against its real file and put back where the script moved it wrongly; `.crew/verify.json` lines up to `:339` did not move, and T-0085's rule is now `:361-373`, the last. A bare `review.md` citation is ambiguous since #267 added `crew-qa-standards/references/review.md`, so the script skipped those; `plugin/crew/commands/review.md` moved only below `:543` (+1, +3), and its cited lines above that were re-read. In this note `plugin/crew/README.md:2259`, `crew_autocycle.py:182`, `crew_state.py:133`/`:137`/`:140`/`:143` and `CLAUDE.md:101` (main's CLAUDE.md is 150 lines) moved; the two diagrams it cites at `:1` were re-anchored with this note. Paragraphs dated before this one describe the tree at their own anchor and were not rewritten. No suite was executed for this note.

**Re-anchored `69c7edbd` -> `7c86bd13` on 2026-09-30 (T-0085 landing: one sabotage anchor re-taken).** `git diff --name-only 69c7edbd 7c86bd13`, refresh artifacts aside, returns only `plugin/crew/tests/sabotage_standards.py`: the find and replace text of "review.md loses the self-check refusal" now end at `rebuild.` / `provider.`, because the merge joined main's exit-5 sentence onto that line. No line was added or removed; no citation moved. No suite was executed for this note.

**Re-anchored `7c86bd13` (`obsidian-vault`: `69c7edbd`) -> `c04dd2ef` on 2026-09-30 (T-0085 landing: `commands/review.md` rewrapped to its 551-line allowance, crew 1.0.71 then 1.0.72).** `git diff --name-only 7c86bd13 c04dd2ef`, refresh artifacts aside, returns the crew version files, `CHANGELOG.md`, `plugin/crew/BUDGETS.md` (20,707 lines, in place) and `plugin/crew/commands/review.md`: step 3's item 3 gains its last line on `:511`, item 4 and its `gh pr comment` paragraph and steps 8-9 are rewrapped at 100 columns, and the closing sentence is joined, taking the file from 557 to 551 lines with no text changed. Every line this note cites in `review.md` is at or above `:511` and holds; the version this note states now reads 1.0.72. No suite was executed for this note.

**Re-anchored `c04dd2ef` -> `8a89a596` on 2026-09-30 (T-0085 landing: catch-up merge of main `6813749b`, #268 T-0097, crew 1.0.70; T-0085 now 1.0.73).** `git diff --name-only 54192270 8a89a596` returns the crew version files, `CHANGELOG.md` (T-0097's entry below T-0085's), the 11 `.ps1` hook carriers (one `Resolve-CrewPython` line each: an empty probe answer is no longer piped into `ConvertFrom-Json`), `plugin/crew/tests/sabotage_scope.py` and `plugin/crew/tests/test_ps1_python_probe.py`. Citations into those files were moved by a line diff (`/root/crew-tmp/t-0085/remap_merge.py`, 11 moved, 0 unmapped); version-line citations (`marketplace.json:218`, `plugin.json:3`, `PLUGINS.md:14`) hold by line and now read 1.0.73. The `Resolve-CrewPython` copies stay byte-identical across all 11 carriers, so the copy-list claims hold. No suite was executed for this note.

**Re-anchored `8a89a596` -> `9b6b0da7` on 2026-09-30 (T-0085 landing: Windows fail-open fix, crew 1.0.74).** `git diff --name-only 58431f49 9b6b0da7` returns the crew version files, `CHANGELOG.md`, `plugin/crew/hooks/scripts/crew_standards.py` (`import stat`, new `_ancestor_problem` before `gate_applies`, which now proves a receipt absent only when the nearest existing ancestor is a directory), `plugin/crew/tests/test_crew_standards.py` (new `test_gate_applies_when_a_file_parent_is_reported_as_not_found`) and `plugin/crew/tests/sabotage_standards.py` (one entry). Path-qualified citations into those files were moved by a line diff (`/root/crew-tmp/t-0085/remap_merge.py`, 10 moved, 0 unmapped); `crew.md`'s bare `crew_standards.py` citations in its standards section were moved by the same diff (27). No suite was executed for this note.

**Re-anchored `9b6b0da7` -> `5c9a9db2` on 2026-09-30 (T-0085 landing: sabotage entry re-targeted, crew 1.0.75).** `git diff --name-only 33da9c91 5c9a9db2` returns the crew version files, `CHANGELOG.md` and `plugin/crew/tests/sabotage_standards.py` (the "receipt that cannot be looked up" entry now flips `gate_applies`' `OSError` verdict). Path-qualified citations into those files were moved by a line diff (`/root/crew-tmp/t-0085/remap_merge.py`, 9 moved, 0 unmapped). No suite was executed for this note.

## Re-anchor provenance - `b142d8e3` / main `5c9a9db2`-`37f4e807` -> `2697bf67`, 2026-09-30 (T-0087 review round 5 successor, merge of main `9af34e57`)

`4e97588e` (golden leak check) and `2de03e41` (review ledger successors path) fix review round 5; `7b62e321` adds their sabotage entries. `7ccff1db` merges origin/main `9af34e57` (T-0085 landed as crew 1.0.75, with #268, #276, #277, #279) into `T-0087-build` with a merge commit, and `2697bf67` re-sets crew 1.0.76. The merge's map conflicts were mechanical: a hunk that differed only in numbers or in the anchor took main's side, and a provenance hunk kept both. Every body citation of the form `path:line` was then re-mapped by script (difflib from the parent the line came from - T-0087's `7b62e321` for a line T-0087 carries, main's `9af34e57` otherwise - to this tree; a bare `:N` binds to the last path named on its line). `.crew/verify.json` now holds T-0085's standards rule as rule 35 (`:361-373`) and T-0087's harness rule as rule 36 (`:374-399`); those descriptions were re-read by hand. Citations the script could not attribute predate this change and were left unchanged. Re-anchor only: no other claim moved and nothing was executed for this note.

## Re-anchor provenance - `2697bf67` -> `45f32c3c`, 2026-09-30 (T-0087, after merging main `9af34e57`)

`5f52ba61` re-maps `plugin/crew/docs/external-tool-formats.md`'s `review_run.py` and `review.md` citations to the merged tree (in place; no line moved), and `2b7e7a05`/`45f32c3c` step crew back and re-set 1.0.76 as the last `plugin/crew` commit. No citation in this note points into a line that moved. Re-anchor only: no claim moved and nothing was executed for this note.

## Re-anchor provenance - `45f32c3c` -> `7c88bf3d`, 2026-09-30 (T-0087 review round 6 fix)

`cff30f72` makes the committed-corpus test in `plugin/crew/tests/test_review_golden.py` run `golden_build.leak` on every fixture (host name included), adds `test_corpus_leak_check_refuses_a_planted_host_name`, and adds sabotage entries (ah)-(ai) to `plugin/crew/tests/sabotage_tooling.py`; its CHANGELOG bullet moved later CHANGELOG lines by 4, and the CHANGELOG citations above were re-mapped by script (difflib `45f32c3c` -> `7c88bf3d`). `49ed9a29` / `7c88bf3d` step crew back and re-set 1.0.76. No other cited line moved. Re-anchor only: nothing was executed for this note.

**Re-anchored `5c9a9db2` -> `06cb9b51` on 2026-09-30 (T-0086 slice 1: the Python standards set, on main `301e478a`).** `git diff --name-only 5c9a9db2 06cb9b51` over this note's paths returns T-0086's files - `plugin/crew/skills/crew-standards/references/python.md` (new, set PYTHON), `plugin/crew/skills/crew-standards/SKILL.md`, `plugin/crew/skills/stack-python/SKILL.md`, `plugin/crew/tests/test_crew_standards.py` (four new tests), `plugin/crew/tests/sabotage_standards.py` (three entries), `plugin/crew/README.md`, `plugin/PLUGINS.md` (rows only), `plugin/crew/BUDGETS.md` (count only) and `CHANGELOG.md` (T-0086's entry on top) - plus main's own commits since `5c9a9db2`. Path-qualified citations into changed files were moved by a line diff (`/root/crew-tmp/t-0086/remap.py`, 9 moved); `plugin/crew/BUDGETS.md:10-11` citations stay on the claim line, whose number changed in place. No suite was executed for this note.
**Re-anchored `06cb9b51` -> `35100955` on 2026-09-30 (T-0086's merge of main `9af34e57`, #279: CI triggers, concurrency, PR CI on Python 3.12 only).** `git diff --name-only 06cb9b51 35100955` returns, outside refresh artifacts, only `.github/workflows/*.yml`, `AGENTS.md` and `.crew/verify.json` (one line rewritten in place, line count unchanged). No `AGENTS.md:NN` citation exists in any map, and no claim outside verification-harness.md states the CI trigger shape (checked by grep for `push, pull_request`, `six workflows`, `three Python versions`, `windows-latest`), so no citation moved. No suite was executed for this note.

**Re-anchored `35100955` -> `fb292689` on 2026-09-30 (T-0086 review round 1's FIX: PYTHON-07's finding count).** `git diff --name-only 35100955 fb292689` returns only `plugin/crew/skills/crew-standards/references/python.md` (PYTHON-07's Why, `6` -> `7` in place, line count unchanged), `plugin/crew/tests/test_crew_standards.py` (two tests and a pinned table inserted after `:302`) and `plugin/crew/tests/sabotage_standards.py` (four docstring lines after `:43`, two entries at the end; `STANDARDS_MUTATIONS` `:54` -> `:57`, 49 entries by `len()`). Every `path:N` citation into those files sits inside an earlier dated provenance paragraph, left as history. No suite was executed for this note.

**Re-anchored `fb292689` -> `f2cf0508` on 2026-09-30 (T-0086's merge of main `b601d450`, #280 L-0521: opt-in self-hosted runners).** `git diff --name-only fb292689 f2cf0508` returns, outside refresh artifacts, only `.github/workflows/pytest-crew.yml` (the `test` and `crew-shell-matrix` `runs-on` expressions) and `AGENTS.md` (one inserted paragraph after `:50`). No map cites `AGENTS.md:NN` or `.github/workflows/pytest-crew.yml:NN`; the one claim about those jobs' runner placement is verification-harness.md's, which main's own L-0521 commit already updated and the merge carries. No citation moved. No suite was executed for this note.

**Re-anchored `f2cf0508` -> `38b220cf` on 2026-09-30 (T-0086 review round 2's FIXes, merge of main `a7524aac` (T-0087, crew 1.0.76) as `142421d0`, crew 1.0.77).** `27387d83` fixes round 2: `plugin/crew/skills/crew-standards/references/python.md` (PYTHON-01's EncodingWarning quote whole, +1 line; PYTHON-03's splitlines table escapes U+2028/U+2029), `plugin/crew/tests/test_crew_standards.py` (two tests before `test_python_set_applies_to_python_files_only`), `plugin/crew/tests/sabotage_standards.py` (four docstring lines, two entries; `STANDARDS_MUTATIONS` `:57` -> `:61`, 51 by `len()`), `plugin/crew/BUDGETS.md` and `CHANGELOG.md`. `142421d0` merges main's T-0087 with a merge commit; its map conflicts were mechanical: anchors took T-0086's side, provenance hunks kept both (main's first), and one-line hunks differing only in numbers took theirs plus T-0086's own shift (ours + theirs - base, per number); INDEX rows keep main's history cell plus T-0086's additions; `sabotage.py`'s import `:84` -> `:85` and append `:3061` -> `:3062` were set in the body. `38b220cf` sets crew 1.0.77 (`plugin/crew/.claude-plugin/plugin.json:3`, `.claude-plugin/marketplace.json:218`, `plugin/PLUGINS.md:14`). BUDGETS.md re-measured at 21,421 lines across 136 files. No suite was executed for this note.

## Re-anchor provenance - `3648f59a` -> `ea764992`, 2026-09-29 (T-0094)

T-0094 is built on origin/main `2693d0fa`: `3648f59a` plus T-0075's landing branch (crew 1.0.56-1.0.59) and `17d057db`, which re-pinned `README.md:12`/`:18` to `e878cc31`. T-0094's commits `be023596`..`ea764992` change `plugin/crew/README.md` (three sentences on the refresh-artifact admission, each rewritten in place, so `:2199` holds), `plugin/crew/commands/implement.md` step 6 and `done.md` check 3, `docs/guides/crew/src/daily-workflow-scope.md` with the rebuilt daily-workflow HTML, DOCX and PDF (the guide set and its build are unchanged), `.crew/verify.json` rule 25 (three more paths and a new test file; later rules move down three lines), `CHANGELOG.md` and the version files. Corrected here: the install-URL pin bullet (current at `ea764992`) and the rule-25 sentence (T-0094's module and suite).

Checked by a script mapping every `path:N` citation outside provenance sections, and every bare `:N` carried from the last path named in its paragraph, from `3648f59a` to the tree at `ea764992` (difflib equal blocks); the only non-self mappings were `README.md:12` and `:18`, changed in place by the re-pin, read with `sed -n`. Nothing else was executed for this note.

## Re-anchor provenance - `ea764992` -> `50061215`, 2026-09-29 (T-0094 lint)

`50061215` is T-0094's lint commit: `scope_guard.py`'s rule-6 docstring rewrapped (one line longer, pylint C0301), the two could-not-tell `except Exception` lines in `crew_refresh_check.py` marked `noqa: BLE001` in place, one `sabotage_refresh.py` replace string parenthesised in place (ISC004), and `test_refresh_admission.py`'s imports sorted (I001). No body citation moved. Checked by the same citation-mapping script, `ea764992` -> `50061215`. Nothing else was executed for this note.

## Re-anchor provenance - `50061215` -> `f79e9f58`, 2026-09-29 (T-0094 review round 1)

`f79e9f58` ends T-0094's review-round-1 fixes (`abe87bc2`..`f79e9f58`). Of the paths this map cites, `.crew/verify.json` (rule 25's `seconds` and `why`, in place), `plugin/crew/README.md` (one refresh-admission paragraph reworded in place), `plugin/crew/commands/implement.md` step 6 and `docs/guides/crew/src/daily-workflow-scope.md` (one phrase each, in place) and the rebuilt daily-workflow guide changed; no citation here moved (checked by script, every `path:N` compared line by line from `50061215` to `f79e9f58`, then the hits read). No claim changed.

## Re-anchor provenance - `bbd9a66d` + `f79e9f58` -> `6375524b`, 2026-09-29 (T-0094 merges `8ab733d7`; review round 2's successor)

`f050cd47` merges origin/main `8ab733d7` (T-0010 landed as crew 1.0.61, its code maps anchored `bbd9a66d`) into T-0094-build at `ca5b1f35` (T-0094's side anchored `f79e9f58`, plus review round 2's FIX 1 `da1532d6` and FIX 2 `ca5b1f35`). The artifact conflicts were anchor, version, provenance and cited-line text only: both sides' provenance kept, main's first; INDEX history columns joined; body hunks resolved to main's lines except T-0094's own refresh-admission paragraph and refresh-check entry point. After it, `157237c2` splits `.crew/verify.json` rule 25 (the admission suite is rule 32 at `:342-349`, rule 25 `:269-287`, every later rule moves by the merged and split lengths), restates the sabotage counts in `plugin/crew/tests/sabotage_refresh.py`, and edits `plugin/crew/README.md` and `docs/guides/crew/src/daily-workflow-scope.md` in place; `ef5b4c89` re-measures `plugin/crew/BUDGETS.md` (19,500 lines across 128 files); `fc348c89` sets crew 1.0.62; `6375524b` rebuilds the daily-workflow guide. `git diff --name-only bbd9a66d 6375524b`, refresh artifacts aside, is T-0094's files only: `.claude-plugin/marketplace.json`, `.crew/verify.json`, `CHANGELOG.md`, the daily-workflow guide and its source, `plugin/PLUGINS.md`, `plugin/crew/.claude-plugin/plugin.json`, `plugin/crew/BUDGETS.md`, `plugin/crew/README.md`, `commands/done.md`, `commands/implement.md`, `completion_audit.py`, `crew_refresh_check.py`, `scope_guard.py` and T-0094's five test files. Every body `path:N` citation was traced to the side whose copy of this note carries its line (`8ab733d7` or `ca5b1f35`) and mapped to HEAD with a `difflib` line diff (`/root/crew-tmp/t-0094/cite_map_merge.py`, machine-local); each that did not map to itself was read with `sed -n` / `grep -n`. The script takes a bare `:N` as the last path named on its line, so some flags were that misattribution and hold; a history position ("before", "at <sha>", "since ...") was left as written. No body citation moved (the flags were bare `:N` misattributions); the daily-workflow guide was rebuilt from its merged source with `docs/guides/crew/src/build.py --guide daily-workflow` (LibreOffice 26.2.5.2, not Word). Nothing else was executed for this note.

## Re-anchor provenance - `6375524b` -> `f5d0f1b1`, 2026-09-30 (T-0094 merges `a61a6f38`, crew 1.0.70)

`0cd952b2` merges origin/main `a61a6f38` (T-0088 landed as crew 1.0.69, after #263-#267: crew 1.0.62-1.0.68, the review gate `review_gate.py`, the `crew-qa-standards` skill, parallel CI and `CLAUDE.md`'s evidence moved to `docs/claude-md-evidence.md`) into T-0094-build at `d331c192`. Its conflicts were the version lines, `CHANGELOG.md` (both entries kept, T-0094's first), `.crew/verify.json` (T-0094's rule 32 kept, main's three new rules after it as 33-35), `crew_refresh_check.py`'s imports (both kept) and `plugin/crew/BUDGETS.md` (re-measured, 19,921 lines across 132 files); no code map, diagram or rule file conflicted (main's maps were still at `bbd9a66d`, but for `obsidian-vault.md`). `f5d0f1b1` sets crew 1.0.70, one past main's 1.0.69. Per-path: `git diff --name-only 6375524b f5d0f1b1 -- <the 73 tracked paths this note cites>` returns `.claude-plugin/marketplace.json`, `.crew/verify.json`, `CHANGELOG.md`, `CLAUDE.md`, `INSTALLATION.md`, `README.md`, `docs/guides/crew/src/troubleshooting.md`, `plugin/PLUGINS.md`, `plugin/README.md`, `plugin/crew/.claude-plugin/plugin.json`, `plugin/crew/BUDGETS.md`, `plugin/crew/CONFIG.md`, `plugin/crew/README.md`, `plugin/crew/commands/review.md`, `plugin/crew/hooks/scripts/crew_autocycle.py`, `plugin/crew/hooks/scripts/crew_autopilot.py`, `plugin/crew/hooks/scripts/crew_config.py`, `plugin/crew/hooks/scripts/crew_context.py`, `plugin/crew/hooks/scripts/crew_refresh_check.py`, `plugin/crew/hooks/scripts/crew_state.py`, `plugin/crew/hooks/scripts/crew_ticket.py`, `plugin/crew/tests/sabotage.py`, `plugin/crew/tests/sabotage_autopilot.py`. Citations were re-mapped by a `difflib` line diff from each cited file's copy at the old anchor to `f5d0f1b1` (`/root/crew-tmp/t-0094/cite_apply2.py`, `cite_ident.py`, `cite_explicit.py`, machine-local): an explicit `path:N`, and a bare `:N` whose file is the one named before it in the paragraph, or the one whose old line carries the identifier beside the citation; every mapped line is text-identical at both ends. History positions ("at <sha>", "before", "on <branch>", "it was") and the provenance sections were left as written; a bare `:N` the scripts attributed to the wrong file was found by that identifier check and put back. Main restructured `CLAUDE.md` (150 lines; the Lessons evidence moved to the new `docs/claude-md-evidence.md`) and added `.claude/skills/steward/SKILL.md`; neither is described by this note beyond the citations it already carried, and the `CLAUDE.md:147` lines dated `adf8d1dd` are left as written. No doc under `docs/` other than the new evidence file and the crew guide sources changed. Nothing was executed for this note.

**Re-anchored `f5d0f1b1` -> `2255fb4d` on 2026-09-30 (T-0094 review round 3).** `2255fb4d` is T-0094's review-round-3 fix commit (Codex round 3 on `e0ccd3f7`: 0 BLOCK / 4 FIX). `git diff --name-only f5d0f1b1 2255fb4d` returns `.crew/codemap/crew.md`, `CHANGELOG.md`, `plugin/crew/hooks/scripts/crew_refresh_check.py`, `plugin/crew/tests/sabotage_refresh.py` and `plugin/crew/tests/test_refresh_admission.py`; the two commits after `f5d0f1b1` before it are refresh artifacts only. This note cites those files by name or in its provenance only; no body citation moved.

**Re-anchored `2255fb4d` -> `0c19512c` on 2026-09-30 (T-0094 crew 1.0.71).** `0c19512c` sets crew 1.0.71 (review round 3's fixes changed `plugin/crew/` after 1.0.70 was set, and origin/main is 1.0.70 too, T-0097 #268). Per-path: `git diff --name-only 2255fb4d 0c19512c` over this note's cited paths returns only `plugin/crew/README.md` (two in-place "since 1.0.70" -> "since 1.0.71" edits, line count unchanged), beside the version files and `CHANGELOG.md` (release bookkeeping). No body citation moved.

**Re-anchored `0c19512c` (T-0094) / `5c9a9db2` (main) -> `1b9e4bfe` on 2026-09-30 (T-0094 merges main `9af34e57`, T-0085 landed as crew 1.0.75; review round 4's successor, crew 1.0.76).** `e1144866` merges origin/main `9af34e57` into T-0094-build at `7c261a19`; this map conflicted on anchor, version, provenance and cited-line text only (both sides' provenance kept, main's first; body hunks resolved to main's lines for files T-0094 does not change, T-0094's for its own). `c815bed8` and `f3fe692f` are the successor's code steps (`crew_refresh_check.py`: `_names_no_commit` new before `_moved_from`, `_rendered_verdict` pairs its source case-folded; `completion_audit.py`: `_default_artifacts` new after `_verdicts`; their tests, fixtures and sabotage entries), and `1b9e4bfe` sets crew 1.0.76 with the README, CHANGELOG and daily-workflow guide text. Per-path, `git diff --name-only 5c9a9db2..1b9e4bfe` over this note's 73 cited, existing paths returns `.claude-plugin/marketplace.json`, `.crew/verify.json`, `docs/guides/crew/src/daily-workflow-scope.md`, `plugin/PLUGINS.md`, `plugin/crew/.claude-plugin/plugin.json`, `plugin/crew/BUDGETS.md`, `plugin/crew/README.md`, `plugin/crew/commands/done.md`, `plugin/crew/commands/implement.md`, `plugin/crew/hooks/scripts/crew_refresh_check.py`, `plugin/crew/hooks/scripts/scope_guard.py`, `plugin/crew/tests/sabotage_refresh.py`, `plugin/crew/tests/test_refresh_admission.py`; from T-0094's side, `0c19512c..1b9e4bfe` adds `.crew/standards.md`, `docs/adr/0004-build-time-development-standards.md`, `docs/guides/crew/src/daily-workflow.md`, `plugin/README.md`, `plugin/crew/commands/review.md`, `plugin/crew/hooks/scripts/crew_standards.py`, `plugin/crew/hooks/scripts/review_prompt.py`, `plugin/crew/skills/crew-setup/SKILL.md`, `plugin/crew/skills/crew-standards/SKILL.md`, `plugin/crew/skills/crew-standards/references/generic.md`, `plugin/crew/tests/sabotage.py`, `plugin/crew/tests/sabotage_scope.py`, `plugin/crew/tests/sabotage_standards.py`, `plugin/crew/tests/test_crew_standards.py`, `plugin/crew/tests/test_lifecycle_commands.py`, `plugin/crew/tests/test_ps1_python_probe.py`, `plugin/crew/tests/test_review_prompt.py` (main's T-0085, T-0097 and CI changes). Every body `path:N` citation was mapped by `/root/crew-tmp/t-0094/cite_map_merge.py` (difflib equal blocks, from the anchor of whichever side's copy carries the line; `MAIN_REV=origin/main`, `OURS_REV=7c261a19`) and each one it reported was read at HEAD. No body citation moved. No suite was executed for this note.

**Re-anchored `1b9e4bfe` -> `8a15557b` on 2026-09-30 (T-0094: `implement.md` step 6 rewrapped to its 120-line budget).** `git diff --name-only 1b9e4bfe 8a15557b`, refresh artifacts aside, returns `plugin/crew/BUDGETS.md` (the count, in place: 20,711 lines) and `plugin/crew/commands/implement.md`: the merged step-6 paragraph (T-0094's admission sentence beside main's self-check paragraph) was 122 lines, over `test_lifecycle_commands.py`'s 120-line command budget, and is rewrapped to 104 columns with its wording unchanged, so every line from the self-check paragraph down sits where main has it again (tracker `:112`, step 7 `:116`); the refresh check is still `:93`. No other body citation moved. No suite was executed for this note beyond `test_lifecycle_commands.py`.

**Re-anchored `8a15557b` -> `a0c171c7` on 2026-09-30 (T-0094 review round 5).** `git diff --name-only 8a15557b a0c171c7` over this note's cited paths, refresh artifacts and release bookkeeping aside, returns `docs/guides/crew/src/daily-workflow-scope.md` (one could-not-tell sentence extended, +1 line at `:104-106`), `plugin/crew/README.md` (one sentence extended in place, line count unchanged), `plugin/crew/hooks/scripts/crew_refresh_check.py` (`_present` new at `:327`, everything below it +19 to +25 lines), `plugin/crew/tests/sabotage_refresh.py` (+4 docstring lines, five entries appended after the round-5 marker), `plugin/crew/tests/test_refresh_admission.py` (+1 import line, the round-5 tests appended). No body citation of this note names a moved line of those files. Citations checked with `/root/crew-tmp/t-0094/cite_apply3.py` (DRY, machine-local) and `grep -n`. No suite was executed for this note.

**Re-anchored `a0c171c7` (T-0094) / main -> `a0db0703` on 2026-09-30 (T-0094 merges origin/main `a7524aac`, T-0087 landed as crew 1.0.76, #281, and L-0521, #280; crew 1.0.77, before review round 6).** `f6f2c2f0` merges `a7524aac` into T-0094-build at `75565970`; `a0db0703` re-sets the version one past main's 1.0.76 (plugin.json, marketplace.json, `plugin/PLUGINS.md:14`, two README sentences, the CHANGELOG heading). The code maps conflicted on anchor, version, provenance and cited-line text only: both sides' provenance kept, main's first. In body hunks a citation into a file only one side changed takes that side's number (`crew_autopilot.py`, `review_ledger.py`, `sabotage.py` and `CLAUDE.md` main's; `crew_refresh_check.py` T-0094's); positions in files both sides changed (`.crew/verify.json`, `plugin/crew/tests/sabotage_refresh.py`) were re-measured on the merged tree: T-0087's harness rule is rule 37 at `.crew/verify.json:384-409`, after T-0094's rule 32; `REFRESH_MUTATIONS` is at `plugin/crew/tests/sabotage_refresh.py:119`; the CLAUDE.md Lessons line is `:144`. Checked by a script mapping every `path:N` citation outside provenance sections, and every bare `:N` carried from the last path named in its paragraph, from each side's anchor (`a0c171c7` and main's own) to `a0db0703` (difflib equal blocks): no citation outside those re-measured positions fails both mappings. Carried as main has them, not corrected here: main's own `crew_autopilot.py` body citations in `crew.md` that already lag main's tree by a few lines (e.g. `next_phase` `:556`, the def is at `:559`) - outside T-0094's change.

**Re-anchored `a0db0703` (T-0094) / `38b220cf` (main) -> `65abeb8d` on 2026-09-30 (T-0094 merges origin/main `549cda24`, T-0086 landed as crew 1.0.77, #282, as `44407f8e`; the owner's split moves the harness half to L-0540 at `c974f997`; review round 6's successor `6ecb6403`..`b17266ed`; crew 1.0.78 at `65abeb8d`).** Per-path, `git diff --name-only a0db0703 65abeb8d` over this note's 94 cited, tracked paths returns `.claude-plugin/marketplace.json`, `.crew/codemap/crew.md`, `CHANGELOG.md`, `docs/diagrams/process-crew-lifecycle.mmd`, `docs/guides/crew/src/daily-workflow-scope.md`, `plugin/PLUGINS.md`, `plugin/crew/.claude-plugin/plugin.json`, `plugin/crew/BUDGETS.md`, `plugin/crew/README.md`, `plugin/crew/hooks/scripts/crew_refresh_check.py`, `plugin/crew/hooks/scripts/scope_guard.py`, `plugin/crew/skills/crew-standards/SKILL.md`, `plugin/crew/skills/crew-standards/references/python.md`, `plugin/crew/skills/stack-python/SKILL.md`, `plugin/crew/tests/sabotage_refresh.py`, `plugin/crew/tests/sabotage_standards.py`, `plugin/crew/tests/test_crew_standards.py`, `plugin/crew/tests/test_refresh_admission.py`; from main's side, `git diff --name-only 38b220cf 65abeb8d` over the same paths returns `.claude-plugin/marketplace.json`, `.crew/codemap/crew.md`, `.crew/verify.json`, `CHANGELOG.md`, `docs/diagrams/process-crew-lifecycle.mmd`, `docs/guides/crew/src/daily-workflow-scope.md`, `plugin/PLUGINS.md`, `plugin/crew/.claude-plugin/plugin.json`, `plugin/crew/BUDGETS.md`, `plugin/crew/README.md`, `plugin/crew/commands/done.md`, `plugin/crew/commands/implement.md`, `plugin/crew/hooks/scripts/crew_refresh_check.py`, `plugin/crew/tests/test_refresh_admission.py`. The merge's conflicts in this map were the anchor and provenance only (both kept, main's first). No body citation in this map names a line the successor or the merge moved (checked with `/root/crew-tmp/t-0094/cite_map_merge.py`, `MAIN_REV=origin/main`, `OURS_REV=b4d87187`, machine-local). No suite was executed for this note.

**Re-anchored `65abeb8d` -> `1f21f73b` on 2026-09-30 (T-0094 review round 7: `902fb96a`..`91da43bc` code and tests, docs, guide rebuilt, crew 1.0.78 un-set and re-set as `1f21f73b`).** `git diff --name-only 65abeb8d 1f21f73b` returns `CHANGELOG.md`, `docs/guides/crew/crew-1.0-daily-workflow.docx`, `docs/guides/crew/crew-1.0-daily-workflow.html`, `docs/guides/crew/crew-1.0-daily-workflow.pdf`, `docs/guides/crew/src/daily-workflow-scope.md`, `plugin/crew/README.md`, `plugin/crew/hooks/scripts/crew_refresh_check.py`, `plugin/crew/tests/test_refresh_admission.py`. No body citation in this map names a line that moved. No suite was executed for this note.

**Re-anchored `1f21f73b` (T-0094) / main -> `17d0b1d2` on 2026-09-30 (T-0094 merges origin/main `d1462bbd`, L-0529 landed as crew 1.0.80 (#283), and re-sets crew 1.0.81 in the merge commit).** `git diff --name-only 79ef56c4 17d0b1d2`, refresh artifacts aside, returns `.claude-plugin/marketplace.json`, `CHANGELOG.md`, `plugin/PLUGINS.md`, `plugin/crew/.claude-plugin/plugin.json`, `plugin/crew/README.md`, `plugin/crew/tests/crew_fixtures.py`, `plugin/crew/tests/test_context_watch_python_resolver.py`, `plugin/crew/tests/test_event_claim_crash_safety.py`, `plugin/crew/tests/test_path_link_farm.py`, `plugin/crew/tests/test_ps1_python_probe.py`, `plugin/obsidian-vault/.claude-plugin/plugin.json`, `plugin/obsidian-vault/hooks/scripts/_test/test_python_probe_proof.py`: main's L-0529 files plus the version statements. The merge's conflicts were version lines and the generated rules' stamps; main's body lines kept. No body citation moved (checked with `/root/crew-tmp/t-0094/cite_map_merge.py`, `MAIN_REV=origin/main`, `OURS_REV=79ef56c4`; its only flags are history positions in verification-harness.md's per-commit lists, left as written). No suite was executed for this note.

## Re-anchor provenance - main `6a8c60b1` -> `c43a54c1`, 2026-09-30 (T-0028, feature half, crew 1.0.84)

T-0028 (the Kimi Code provider, feature half after the owner's split; the review launch is L-0527)
merged origin/main `6a8c60b1` (L-0531 #284 and T-0099 #278, crew 1.0.83) with rerere disabled, taking main's code
maps. The branch differs from main only in the Kimi provider's feature files (`crew_state.py`,
`crew_config.py` with the launch gate, `kimi_probe.py`, the templates, provider docs and tests,
`.crew/verify.json`, the release files). This note is main's copy; every body citation into a
changed file was mapped by a `difflib` line diff from `6a8c60b1` to `c43a54c1` with
`/root/crew-tmp/t-0028/refresh/reanchor2.py` (machine-local), each moved citation landing on the
same line text. T-0028's earlier branch provenance is in git history. Re-anchor
only (owner refresh-artifact standing rule, 2026-09-28); no test suite was executed for this note.

## Re-anchor provenance - `c43a54c1` -> `f4adf923`, 2026-09-30 (T-0028 re-sets crew 1.0.85)

`f4adf923` changes only the release files (crew 1.0.84 -> 1.0.85: `plugin.json`, `marketplace.json`,
`PLUGINS.md`, the README's version mention and the CHANGELOG heading), because T-0505 targets
1.0.84. No cited line moved; the version sentences were re-read. Re-anchor only (owner
refresh-artifact standing rule, 2026-09-28); no test suite was executed for this note.

## Re-anchor provenance - `f4adf923` -> `328fdf4a`, 2026-09-30 (T-0028 round-7 fixes, crew 1.0.85 re-set)

`233701d5` fixes review round 7's four FIXes in `kimi_probe.py` (the owner accepted round 7 and
ordered the fixes); `328fdf4a` re-sets crew 1.0.85. Body citations were mapped by `difflib` from
`ea90a4e4` to `328fdf4a` with `/root/crew-tmp/t-0028/refresh/reanchor2.py` (machine-local), each moved
citation landing on the same line text. Re-anchor only (owner refresh-artifact
standing rule, 2026-09-28); no test suite was executed for this note.

**Re-anchored `17d0b1d2` -> `c4e2eb98` on 2026-09-30 (L-0520 PR 1, the merge train CLI, after merging main 42d5ef58 (T-0094)).** `git diff --name-only 17d0b1d2 c4e2eb98` adds L-0520's PR 1 outside refresh artifacts (crew_train.py, done.md, README, two guides, CHANGELOG, TODO, BUDGETS.md in place, verify.json, two tests); path-qualified citations outside dated provenance were moved by a line diff (`/root/crew-tmp/l-0520/tools/l0520_remap.py`, machine-local). No suite was executed for this note.

**Re-anchored `c4e2eb98` -> `0be97503` on 2026-09-30 (L-0520 PR 1 merges main 42af3fb7 (L-0531)).** `git diff --name-only c4e2eb98 0be97503` returns, outside refresh artifacts, only L-0531's `plugin/crew/tests/sabotage_qa.py`, `.crew/verify.json` and release bookkeeping; path-qualified citations were moved by a line diff (`/root/crew-tmp/l-0520/tools/l0520_remap.py`). No suite was executed for this note.

**Re-anchored `0be97503` -> `14bb59ef` on 2026-09-30 (L-0520 PR 1 merges main 6a8c60b1 (T-0099)).** `git diff --name-only 0be97503 14bb59ef` returns, outside refresh artifacts, T-0099's `review_prompt.py`, `sabotage_review.py`, `test_review_prompt.py` and release bookkeeping; path-qualified citations were moved by a line diff (`/root/crew-tmp/l-0520/tools/l0520_remap.py`). No suite was executed for this note.

**Re-anchored `14bb59ef` -> `8bf710ed` on 2026-09-30 (L-0520 PR 1 review round 1 fixes).** `git diff --name-only 14bb59ef 8bf710ed` returns crew_train.py, done.md and README.md (edits in place), BUDGETS.md, two tests and the version files; path-qualified citations outside dated provenance were moved by a line diff (`/root/crew-tmp/l-0520/tools/l0520_remap.py`). No suite was executed for this note.

**Re-anchored `8bf710ed` -> `14b52c91` on 2026-09-30 (L-0520 PR 1 merges main bd4b2f30 (T-0028 #288, crew 1.0.85, and the mailgun skill), crew 1.0.86).**  No suite was executed for this note.

**Re-anchored `14b52c91` -> `0c3508e9` on 2026-09-30 (L-0520 PR 1 merges main f7caa37d (L-0561 #289: mailgun registered as skills/mailgun 1.0.1, both install scripts, README, INSTALLATION.md), crew stays 1.0.86).**  No suite was executed for this note.

**Re-anchored `0c3508e9` -> `fe524012` on 2026-09-30 (L-0513, the shared gate runner `scripts/gate-runner.py`; repository tooling, no plugin version, crew stays 1.0.86).** `git diff --name-only 0c3508e9 fe524012` returns, outside refresh artifacts, `.crew/verify.json` (rule 22's `run`, `seconds` and `why` in place, and rule 40 appended after T-0028's Kimi rule 39 at `:426-430`), `CLAUDE.md` (a two-line gate-runner pointer in Commands, so every line from the old `:14` moved down 2), `CHANGELOG.md`, `README.md` (main's re-pin `767fa3ef`, in place), `scripts/gate-runner.py` and `scripts/_test/gate-runner.py`; no `plugin/crew` path. Every `CLAUDE.md:N` and `.crew/verify.json:N` body citation in this note was re-read with `grep -n`/`sed -n`. `CLAUDE.md:101` -> `:103` ("Decisions in `docs/adr/`", re-grepped). No suite was executed for this note.

**Re-anchored `fe524012` -> `4eacfacf` on 2026-09-30 (L-0513 step 6 fix: the inner gate runner exits 128+signum after a signal).** `git diff --name-only fe524012 4eacfacf` returns, outside refresh artifacts, `scripts/gate-runner.py`, `scripts/_test/gate-runner.py` and `.crew/verify.json` (rules 22 and 40: `why` text only, in place; line count unchanged, rule 40 still `:426-430`). No body citation in this note moved. No suite was executed for this note.

**Re-anchored `4eacfacf` -> `3437cbdd` on 2026-10-01 (L-0513 Fix phase: review round 1's 2 BLOCK and 6 FIX; repository tooling, no plugin version, crew stays 1.0.86).** `git diff --name-only 4eacfacf 3437cbdd` returns, outside refresh artifacts, `scripts/gate-runner.py`, `scripts/_test/gate-runner.py`, `CHANGELOG.md` (the L-0513 Unreleased entry, +9 lines) and `.crew/verify.json` (rules 22 and 40: `seconds` 12 -> 20 and `why` text, in place; line count unchanged, rule 40 still `:426-430`). No body citation of this map points into those files' changed lines. No suite was executed for this note.

**Re-anchored `3437cbdd` -> `e41bc6fd` on 2026-10-01 (L-0513 successor plan: review round 2's six fixes, after `git -c rerere.enabled=false merge origin/main` at `1899c370`; repository tooling, no plugin version of its own, crew is main's 1.0.89).** `git diff --name-only 3437cbdd e41bc6fd` returns, outside refresh artifacts, `scripts/gate-runner.py`, `scripts/_test/gate-runner.py`, `.crew/verify.json` (rules 22 and 40: `seconds` 20 -> 41, in place, line count unchanged), and from main's merge `.github/workflows/runner-autostart.yml`, `CHANGELOG.md` (+22 lines at `:31`, W-0116's entry), `plugin/PLUGINS.md:14`, `.claude-plugin/marketplace.json:224` and `plugin/crew/.claude-plugin/plugin.json:3` (crew 1.0.86 -> 1.0.89, in place), `plugin/crew/hooks/scripts/crew_refresh_check.py` (+43 lines, inserted after `:686`, `:694` and `:713`) and `plugin/crew/tests/test_refresh_admission.py`. No body citation of this map points into a moved line of those files. No suite was executed for this note.

**Re-anchored `e41bc6fd` -> `4a48f594` on 2026-10-01 (L-0513 Fix phase: review round 3's BLOCK, five FIX and the NIT; repository tooling, no plugin version of its own, crew is main's 1.0.89).** `git diff --name-only e41bc6fd 4a48f594` returns, outside refresh artifacts, `scripts/gate-runner.py`, `scripts/_test/gate-runner.py`, `.crew/verify.json` (rules 22 and 40: `seconds` 41 -> 55 and their `why` text, in place, line count unchanged) and `CHANGELOG.md` (+7 lines inserted after `:29`, inside L-0513's own entry). No map cites a `scripts/gate-runner.py` line. The `CHANGELOG.md:N` figures inside earlier re-anchor notes describe the file at those notes' own anchors and are left as written; none is a body citation of current content. No suite was executed for this note.

**Re-anchored `0c3508e9` -> `6e581365` on 2026-09-30 (T-0505 merges main 64b04c6b: W-0116 crew 1.0.89, runner auto-start #294; crew 1.0.91).** `git diff --name-only 0c3508e9 6e581365` outside the refresh artifacts returns W-0116's `plugin/crew/hooks/scripts/crew_refresh_check.py` and `plugin/crew/tests/test_refresh_admission.py`, `.github/workflows/runner-autostart.yml` (#294), the repo README, and T-0505's files: `promote-gate.sh`/`.ps1`, the new `_promote_tree.py`, `test_promote_gate_effective_tree.py`, `promote_tree_mutations.py`, `promote.md`, crew README, CONFIG.md (+2 lines in section 16), the crew-verification SKILL, INSTALLATION.md, `.crew/verify.json` (rule 4 path), the troubleshooting guide and its builds, the cloud handoff note and README, CHANGELOG.md and the version files (crew 1.0.91, past main's 1.0.89). A difflib re-map of every path-qualified `path:line` citation in the eight maps (history sections skipped) moved four: `crew_refresh_check.py:970` -> `:1013` (W-0116) and three `plugin/crew/CONFIG.md:2410-2417` -> `:2412-2419` (T-0505's sentence); none was unmapped. Re-applied by hand in `crew.md`: `promote-gate.sh:79` is the plain `crew_py()` call (re-read with `grep -n`), and `promote-gate.sh` is not a `crew_config.py` user (no `crew_config` import or `.crew/config.json` read in either flavour). Bare `:N` continuations and `CHANGELOG.md` citations in history sections were left as written. No suite was executed for this note.

**Re-anchored `6e581365` -> `9580571e` on 2026-10-01 (T-0505 raises promote.md's line ceiling in .budget-allowance.json, crew 1.0.91).** `git diff --name-only 6e581365 9580571e` outside the refresh artifacts returns only `plugin/crew/.budget-allowance.json`: promote.md's entry edited in place (`lines` 335 -> 380, reason `T8: to trim` -> a `raised:` reason), line count unchanged. No note cites a line of that file; a difflib re-map of every path-qualified citation moved none. No suite was executed for this note.

**Re-anchored `17d0b1d2` -> `3bb32980` on 2026-09-30 (T-0040-land: T-0040 merged into origin/main `6a8c60b1` at `b6ae7c61`, review round 2's fixes at `3bb32980`).** T-0040's `plugin/crew/README.md` section moved the body citation `plugin/crew/README.md:2259` -> `:2270` (mapped through `git diff -U0 origin/main`, re-read with `sed -n`). No other body citation in this map names a line the landing moved. No suite was executed for this note.

**Merged `3bb32980` (T-0040-land) + `328fdf4a` (main) on T-0040-land, 2026-09-30 (merge of origin/main `844bfc36`, T-0028 landed as crew 1.0.85).** Both sides' provenance kept, main's first; the body citation both sides moved was re-read by content on the merged tree (see the body). No suite was executed for this note.

**Re-anchored `328fdf4a` (main) / `3bb32980` (T-0040-land) -> `a54ca704` on 2026-09-30 (T-0040-land's merge of origin/main `844bfc36`, T-0028 landed as crew 1.0.85).** The merge note above names every citation the merge re-took; nothing else moved. No suite was executed for this note beyond the merge's.

**Merged `0c3508e9` (main) + `a54ca704` (T-0040-land) on T-0040-land, 2026-10-01 (merge of origin/main `66651b69`: L-0520 PR 1 #287, the merge train, landed as crew 1.0.86; anchored at that main tip).** Three hunks of this file conflicted: the anchor, the runbooks-index README citation and the provenance tail. Both sides' provenance is kept, main's first. The runbooks-index sentence (`docs/runbooks/INDEX.md` lists symptom ...) is `plugin/crew/README.md:2308` on the merged tree, re-found with `grep -n` (main's L-0520 section and T-0040's section both sit above it). Every other `plugin/crew/README.md` line number this map carries outside that sentence is inside a dated note, as of its own commit. No suite was executed for this note.

**Merged `9580571e` (main) + `66651b69` (T-0040-land) on T-0040-land, 2026-10-01 (merge of origin/main `44d3dbc6`: runner auto-start #294, T-0505 #296 and T-0110 #297, crew 1.0.97, with rerere off; anchored at that main tip).** Two hunks of this file conflicted: the anchor and the provenance tail. Both sides' provenance is kept, main's first. Every `path:line` either side added into a file the other side changed was mapped through a line diff onto the merged tree, and every citation into a file both sides changed was compared by text. No suite was executed for this note.

**Re-anchored `0c3508e9` -> `bf7ce780` on 2026-09-30 (L-0558: L-0520 round-2 fixes and the rerere rule, crew 1.0.87).**  No suite was executed for this note.

**Re-anchored `bf7ce780` -> `dbad6519` on 2026-09-30 (L-0558 self-review fixes, crew 1.0.87).** `git diff --name-only bf7ce780 dbad6519` touches only crew_train.py, its tests and CHANGELOG.md's top entry; nothing this map cites by line moved. No suite was executed for this note.

**Re-anchored `dbad6519` -> `c8118baf` on 2026-09-30 (L-0558 lint fix and version re-set).** `git diff --name-only dbad6519 c8118baf` returns, outside refresh artifacts, `plugin/crew/tests/test_crew_train.py` (one trailing blank line dropped) and the three version files (stepped back and re-set to 1.0.87 on the same lines); nothing any map cites by line moved. No suite was executed for this note.

**Re-anchored `c8118baf` -> `afd976ee` on 2026-09-30 (L-0558 review round 1 fix).** `git diff --name-only c8118baf afd976ee` returns, outside refresh artifacts: CHANGELOG.md plugin/crew/README.md plugin/crew/hooks/scripts/crew_train.py plugin/crew/tests/test_crew_train.py - see the merge-train section for crew_train.py citations, re-mapped by definition name; no other cited line moved. No suite was executed for this note.

**Re-anchored `afd976ee` -> `d21fa82d` on 2026-09-30 (L-0558 round-2 fixes and main merge, crew 1.0.95).** `git diff --name-only afd976ee d21fa82d` returns, outside refresh artifacts: .claude-plugin/marketplace.json CHANGELOG.md plugin/PLUGINS.md plugin/crew/.claude-plugin/plugin.json plugin/crew/README.md plugin/crew/hooks/scripts/crew_refresh_check.py plugin/crew/hooks/scripts/crew_train.py plugin/crew/tests/test_crew_train.py plugin/crew/tests/test_refresh_admission.py - crew_train.py citations in the merge-train section were re-mapped by definition name; W-0116's crew_refresh_check.py and test_refresh_admission.py are main's (merged with rerere disabled at 8935fc25), and no line this map cites in them is relied on here without re-reading; the version files moved value, not line. No suite was executed for this note.

**Re-anchored `9580571e` -> `b0ac0e1a` on 2026-09-30 (L-0558 merges main 6fe0e0db (T-0505), crew 1.0.95).** Both histories are kept above: main's T-0505 chain to 9580571e and L-0558's chain to d21fa82d, merged at f7118a04 with rerere disabled. `git diff --name-only 9580571e b0ac0e1a` outside refresh artifacts is L-0558's change (crew_train.py, test_crew_train.py, plugin/crew/README.md, the two guide sources and their outputs, CHANGELOG.md, .crew/verify.json rule 37, the version files) plus main's W-0116 files already in 9580571e's ancestry; the merge-train section's crew_train.py citations were re-mapped at d21fa82d and crew_train.py has not changed since; no other cited line moved. No suite was executed for this note.

**Re-anchored `44d3dbc6` (main) and `b0ac0e1a` (L-0558) -> `89ebda03` on 2026-10-01 (L-0558 merges main 52489039: T-0110 #297, T-0040 #290; crew 1.0.102).** Both histories are kept above; the merge (c481ada4) ran with rerere disabled. `git diff --name-only 44d3dbc6 89ebda03` outside refresh artifacts is 35 paths: L-0558's change (crew_train.py, test_crew_train.py, plugin/crew/README.md, two guide sources and outputs, CHANGELOG.md, .crew/verify.json rule 37, the version files) plus main's commits since 44d3dbc6; the merge-train section's crew_train.py citations hold (crew_train.py unchanged since 7a71faff); no other line this map cites was re-checked beyond the merge. No suite was executed for this note.

**Re-anchored `0c3508e9` -> `5ab63076` on 2026-09-30 (L-0516: deadline polls replace fixed sleeps in the flaky crew tests, crew 1.0.89; verify.json gains rule 10 so later rules shift by one and six lines).**  No suite was executed for this note.

**Re-anchored `5ab63076` -> `805b0a25` on 2026-09-30 (L-0516 split per the tooling-PR rule: sabotage_qa.py back to main's copy, its four entries move to L-0563; verify.json rule 10's why and CHANGELOG reworded in place).**  No suite was executed for this note.

**Re-anchored `805b0a25` -> `7ecbdc7f` on 2026-09-30 (L-0516 re-bumps crew to 1.0.91 after the split; version files, CHANGELOG heading and the two version sentences only).**  No suite was executed for this note.

**Re-anchored `7ecbdc7f` -> `a9c0d9ab` on 2026-09-30 (L-0516: pylint R1732 fix in test_poll_fixtures.py (with-blocks, no line this map cites moves) and crew re-bumped to 1.0.92; version files, CHANGELOG heading and the two version sentences in place).**  No suite was executed for this note.

**Re-anchored `a9c0d9ab` -> `083cda66` on 2026-10-01 (L-0516 merges main `64b04c6b` (W-0116 #292: `crew_refresh_check.py` gains the Windows `_FINAL_PATH` check, `test_refresh_admission.py` two Windows premises; runner-autostart.yml) and crew re-bumped to 1.0.93; version files, CHANGELOG heading and the two version sentences in place).** `git diff --name-only a9c0d9ab 083cda66` over this map's cited paths: no cited line moved.  No suite was executed for this note.

**Re-anchored `083cda66` -> `908c03af` on 2026-10-01 (L-0516 review round 1 fixes: `poll_until` reads the clock before each probe after the first, `test_poll_fixtures.py` reaps its children with `wait(timeout=10)`, CHANGELOG corrected; crew re-bumped to 1.0.97; version files, CHANGELOG heading and the two version sentences in place).** `git diff --name-only 083cda66 908c03af` over this map's cited paths: no cited line moved.  No suite was executed for this note.

**Re-anchored `908c03af` -> `11f476a2` on 2026-10-01 (L-0516 merges main `6fe0e0db` (T-0505 #296: promote-gate judges the deploy's tree, crew 1.0.92) without rerere and re-bumps crew to 1.0.98).** Conflicts were refresh artifacts, CHANGELOG, BUDGETS.md and the version files only; each map keeps both branches' history notes (main's first). `git diff --name-only 908c03af 11f476a2` outside the refresh artifacts returns T-0505's files (`promote-gate.sh`/`.ps1`, `_promote_tree.py`, `test_promote_gate_effective_tree.py`, `promote_tree_mutations.py`, `promote.md`, crew README, CONFIG.md, `.budget-allowance.json`, the crew-verification SKILL, INSTALLATION.md, `.crew/verify.json` rule 4's path, the troubleshooting guide and its builds, the cloud handoff note and README), CHANGELOG.md, BUDGETS.md (21,621 lines, still `:11`) and the version files. Main's own re-maps of those files (`CONFIG.md:2412-2419`, `promote-gate.sh:79`) arrived with the merge; a difflib re-map of every path-qualified citation from `908c03af` to `11f476a2` moved none outside history sections, where `CHANGELOG.md` and `CONFIG.md` citations are left as written. `crew_refresh_check.py`'s `main()` `:1406` and `artifact_verdicts` `:1013` keep this branch's values (re-read with `grep -n`; main's map still read `:1363`/`:970`). No suite was executed for this note.

**Re-anchored `11f476a2` -> `1390bb23` on 2026-10-01 (L-0516 merges main `52489039` (T-0110 #297 at crew 1.0.97, T-0040 #290 at 1.0.98) without rerere and re-bumps crew to 1.0.100).** Main moved while this lane's suites ran. Conflicts were refresh artifacts, CHANGELOG and BUDGETS.md only; maps, diagram notes and INDEX keep both histories (main's first). A citation re-map that follows each line's origin (this branch's lines from `e9375690`, main's from `52489039`, each to `1390bb23`; history skipped) moved nothing: main's own lines already carry T-0040's moves (`CONFIG.md`, `crew_config.py`, crew README). Re-read by hand: `crew.md`'s W-0116 `_FINAL_PATH` sentence keeps this branch's text (`crew_refresh_check.py:716`); `verification-harness.md`'s verify.json paragraph now reads 42 rules / 443 lines (T-0040's rule 42 at `.crew/verify.json:433-439`, `default` `:441`, `unmapped` `:442`), and rule 39 `:418-431` is unchanged. No suite was executed for this note.

**Re-anchored `1390bb23` -> `0027f794` on 2026-10-01 (L-0516 merges main `05a679bf` (L-0558 #293 at crew 1.0.102) without rerere and re-bumps crew to 1.0.103).** Main moved while this lane's required checks ran. Conflicts were refresh artifacts, CHANGELOG and the version files only; maps, diagram notes and INDEX keep both histories (main's first). Main's change outside refresh artifacts is `crew_train.py`, `test_crew_train.py`, crew README, the daily-workflow and troubleshooting guides, CHANGELOG, the version files and `.crew/verify.json` rule 37's line rewritten in place (443 lines at both `1390bb23` and `0027f794`, so no `.crew/verify.json:N` citation moves). Main's own lines already carry L-0558's `crew_train.py` moves; no line this branch added cites `crew_train.py`, `test_crew_train.py`, the crew README or either guide by line. `crew.md`'s version sentence names 1.0.103 in place. No suite was executed for this note.

**Re-anchored `9580571e` (main's side of the merge) and `4a48f594` (L-0513's side) -> `de32cb87` on 2026-10-01 (L-0513 merges origin/main `44d3dbc6` at `293b78a1` with `git -c rerere.enabled=false`, bringing T-0110 #297 and crew 1.0.97, then review round 4's five fixes; repository tooling, no plugin version of its own).** The merge's conflicts in this map were the anchor header and these history notes only; both sides' notes are kept above. `git diff --name-only 9580571e de32cb87` outside refresh artifacts returns L-0513's `scripts/gate-runner.py`, `scripts/_test/gate-runner.py`, `.crew/verify.json` (rules 22 and 40: `seconds` 55 -> 57 and their `why`, in place, line count unchanged), `CLAUDE.md` (L-0513's two-line pointer in Commands) and `CHANGELOG.md`, and main's T-0110 files: `.github/workflows/pytest-crew.yml`, `AGENTS.md`, eight files under `plugin/crew/tests/` (`crew_fixtures.py`, `test_msys_tmp_pin.py` and six others) and the version files `.claude-plugin/marketplace.json`, `plugin/PLUGINS.md:14` and `plugin/crew/.claude-plugin/plugin.json:3` (crew 1.0.97, in place). A difflib re-map of every path-qualified `path:line` citation in the eight maps and two diagrams (history notes skipped), from each merge parent's anchor to `de32cb87`, found every one mapping onto itself from at least one parent, except the in-place version lines and `CHANGELOG.md:N` figures inside history notes, left as written; `crew.md`'s version sentence now reads 1.0.97. No suite was executed for this note.

**Re-anchored `de32cb87` -> `f23b01b4` on 2026-10-01 (L-0513 Fix phase: review round 5's two FIX findings; repository tooling, no plugin version of its own, crew is main's 1.0.97).** `git diff --name-only de32cb87 f23b01b4` outside refresh artifacts returns `scripts/gate-runner.py` (`_valid_result` now takes the table step, requires phase/group/argv/cwd/timeout, and refuses a FAIL whose rc `classify()` would not call FAIL), `scripts/_test/gate-runner.py` (two new cases, `part_row`), `.crew/verify.json` (rules 22 and 40: `seconds` 57 -> 58 and their `why`, in place, line count unchanged) and `CHANGELOG.md` (+3 lines inside L-0513's entry, at :30-36). A difflib re-map of every path-qualified `path:line` citation in the eight maps and two diagrams (history notes skipped) from `de32cb87` found every one mapping onto itself except nine `CHANGELOG.md:N` citations in `crew.md`, shifted +3 to the lines they cited, and the in-place `.crew/verify.json:260`/`:430` lines. No suite was executed for this note.

**Re-anchored `f23b01b4` (L-0513's side) and main's side -> `71038cb9` on 2026-10-01 (L-0513 owner amendment for review round 6's BLOCK at `fbd48532`, then `git -c rerere.enabled=false merge origin/main` `52489039` (T-0040 #290, crew 1.0.98) at `74130bbd`, then rules 22 and 40 repriced at `71038cb9`; repository tooling, no plugin version of its own).** `git diff --name-only f23b01b4 71038cb9` outside refresh artifacts returns L-0513's `scripts/gate-runner.py` and `scripts/_test/gate-runner.py` (the BLOCK fix: no process-group signal once the leader is reaped, and its two cases), `CHANGELOG.md` (L-0513's entry +3 lines; T-0040's 1.0.98 entry now sits below it) and `.crew/verify.json` (rules 22 and 40 `seconds` 58 -> 60 and `why`, in place; T-0040's shell-route rule appended as rule 41 at `:432-437`), and T-0040's own paths, which main's side of this map already describes. Where the merge conflicted here it was the anchor header and these provenance notes: both sides kept, main's first. The `CHANGELOG.md:N` citations in older provenance notes name lines at the commits those notes name and were not shifted. Refresh artifacts per owner rule 2026-09-28; no test suite was executed for this note.

**Re-anchored `71038cb9` (L-0513's side) and `89ebda03` (main's side) -> `0d159692` on 2026-10-01 (L-0513 merges origin/main `05a679bf` - L-0558 #293, crew 1.0.102 - at `0d159692` with `git -c rerere.enabled=false`; repository tooling, no plugin version of its own).** The merge's conflicts in this map were the anchor header and these history notes only; both sides' notes are kept, main's first. `git diff --name-only 71038cb9 0d159692` outside refresh artifacts is main's L-0558 change only: `plugin/crew/hooks/scripts/crew_train.py`, `plugin/crew/tests/test_crew_train.py`, `plugin/crew/README.md`, the daily-workflow and troubleshooting guide sources and their six builds, `.crew/verify.json`, `CHANGELOG.md` and the three version files (crew 1.0.102). A difflib re-map of every path-qualified `path:line` citation in the eight maps and two diagrams (history notes skipped), from each merge parent's anchor to `0d159692`, found every one mapping onto itself from at least one parent except three `CHANGELOG.md:N` citations in `crew.md` from L-0513's side, moved to the lines they cited (`:485-486` -> `:519-520`, `:645-646` -> `:679-680`, `:274` -> `:308`); `crew.md`'s version sentence now reads 1.0.102. No suite was executed for this note.

**Re-anchored `0027f794` (L-0516's side) and `0d159692` (main's side) -> `ec95c8aa` on 2026-10-01 (L-0516 merges origin/main `cacf7ff0` - L-0513 #301, the gate runner; crew stays 1.0.102 on main - with `git -c rerere.enabled=false`; crew 1.0.104, re-bumped at `1f2114bc` past 1.0.103, which L-0510's worktree claimed first).** Conflicts were refresh artifacts and CHANGELOG only; each map keeps both re-anchor histories. `git diff --name-only 0027f794 ec95c8aa` outside refresh artifacts returns main's L-0513 paths (`.crew/verify.json` rule 22 rewritten in place at `:262-266` and its gate-runner rule appended at `:432-436`, `CLAUDE.md`, `scripts/gate-runner.py`, `scripts/_test/gate-runner.py`) and the three version files plus CHANGELOG; `git diff --name-only 0d159692 ec95c8aa` returns L-0516's own paths. A difflib re-map of every path-qualified `path:line` citation in the eight maps and two diagrams (history notes skipped), from each merge parent's anchor, found every one mapping onto itself from at least one parent except the version lines (changed in place) and nine `CHANGELOG.md:N` citations in `crew.md` from main's side, which L-0516's CHANGELOG entry above them moved by 35 (`:519-520` -> `:554-555`, `:679-680` -> `:714-715`, `:308` -> `:343`, `:676-677` -> `:711-712`, `:887-888` -> `:922-923`, `:898-899` -> `:933-934`, `:1114-1115` -> `:1149-1150`, `:1238` -> `:1273`, `:1134` -> `:1169`). `verification-harness.md`'s verify.json section now reads the merged tree (448 lines, 43 rules). No suite was executed for this note.

**Re-anchored `ec95c8aa` -> `5ffffbe3` on 2026-10-01 (L-0516 merges origin/main `ddcbf90d` - W-0115 #299, T-0040's shell-route sabotage mutations, crew 1.0.106 - with `git -c rerere.enabled=false` and re-bumps crew to 1.0.110, skipping 1.0.105 (L-0557), 1.0.107 (T-0504), 1.0.108 (L-0510) and 1.0.109 (T-0501)).** Conflicts were the three version files and CHANGELOG only. `git diff --name-only ec95c8aa 5ffffbe3` outside refresh artifacts returns W-0115's paths (`plugin/crew/tests/sabotage.py`, `plugin/crew/tests/sabotage_shell.py`, `.crew/verify.json`'s last rule gaining one path line) plus the version files and CHANGELOG. A difflib re-map of every path-qualified citation (history notes skipped) moved two `plugin/crew/tests/sabotage.py` citations in `crew.md` by +2 (`:3055` -> `:3057`, `:3056` -> `:3058`; W-0115 adds an import at `:86` and a comment line at `:3055`), the nine main-side `CHANGELOG.md` citations in `crew.md` by +15 for W-0115's entry, and `verification-harness.md`'s verify.json header to 449 lines; every other citation maps onto itself. No suite was executed for this note.

**Re-anchored `5ffffbe3` -> `f4c94e1d` on 2026-10-01 (L-0555 PR 1: the diagnostic CI verify-gate receipt - `plugin/crew/hooks/scripts/ci_receipt.py`, `.github/workflows/verify-gate.yml`, `plugin/crew/tests/test_ci_receipt.py` - after merging origin/main `2906dcbd` (L-0516 #298, crew 1.0.110), crew bumped to 1.0.116, skipping 1.0.111-1.0.115 claimed by other lanes).** `git diff --name-only 5ffffbe3 f4c94e1d` outside refresh artifacts returns L-0555's paths only: the three new files, `.crew/verify.json` (one rule appended as rule 43, `default`/`unmapped` moved down one line), `CHANGELOG.md` (+16 lines at the top), `plugin/crew/README.md` (+23 lines at its section 17), `scripts/gate-runner.py` (+2 lines in EXCLUDED_WORKFLOWS), `plugin/crew/BUDGETS.md` (count only) and the version files. A difflib re-map of every path-qualified citation into those files (history notes skipped) moved nine `CHANGELOG.md` citations in `crew.md` by +16 and six `plugin/crew/README.md` citations in `repo-docs.md` by +23; every other citation maps onto itself. No suite was executed for this note.

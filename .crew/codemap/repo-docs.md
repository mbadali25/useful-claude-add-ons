# repo-docs
anchor: useful-claude-add-ons@5d1fc5fd
verified: 2026-09-22
**This pass (`03b19262` -> `5d1fc5fd`) is a per-path diff and a re-read of
every citation into a changed file — see the bottom-most provenance section
for the command and output. Its headline is `## Corrected at 5d1fc5fd`
(just before `## Landmines`): every "not yet reflected in this file's
`03b19262` anchor" caveat this note carried is now resolved, because the
rework those caveats were waiting on landed in this range.**

The `ea8a014 -> 84976536` section immediately below is retained as the record
of that earlier full per-path re-verification and was not redone at this pass.
Full per-path re-verification of every claim resting on a file the path diff
named as changed; claims resting on unchanged files are closed by that result
and were not re-read. See the provenance section immediately below for the
command, its output, and the explicit list of what was NOT re-read. Claims
resting on machine-local files absent from this checkout are marked
UNVERIFIABLE HERE at the claim, not in a preamble.

## Re-anchor provenance — ea8a014 -> 84976536, 2026-09-22

Per-path check, run rather than skipped. The command, verbatim:

```
git diff --name-only ea8a014..HEAD -- <the 30 tracked paths this note cites>
```

**Sixteen changed**: `.crew/verify.json`, `CHANGELOG.md`, `INSTALLATION.md`,
`README.md`, `TODO.md`, `docs/diagrams/data-flow-crew-config.mmd`,
`docs/diagrams/process-crew-brief.mmd`, `docs/remaining-setup.md`,
`plugin/PLUGINS.md`, `plugin/README.md`, `plugin/crew/README.md`,
`plugin/crew/agents/scribe.md`, `plugin/crew/hooks/scripts/_test/run-tests.sh`,
`plugin/crew/hooks/scripts/crew_state.py`, `scripts/check-marketplace.py`,
`skills/README.md`.

**Sixteen did not**, and every citation into them that survives
byte-identical is closed by that result: `CLAUDE.md`, `docs/HANDOFF.md`,
`docs/adr/0001-promote-stays-unarmed.md`, `docs/diagrams/architecture.mmd`,
`docs/guides/Running-a-Mailbox-Job.json`, `docs/runbooks/rollback.md`,
`plugin/crew/commands/handoff.md`, `plugin/crew/hooks/scripts/crew_freshness.py`,
`plugin/crew/skills/crew-context/SKILL.md`,
`plugin/crew/skills/crew-diagrams/SKILL.md`,
`plugin/crew/skills/crew-diagrams/scripts/_test/render.sh`,
`plugin/crew/skills/crew-diagrams/scripts/render.sh`,
`plugin/crew/skills/crew-docs/SKILL.md`, `plugin/crew/skills/crew-runbooks/SKILL.md`,
`scripts/_test/self-claims.py`, `scripts/sync-updates.py`.

**Read this before the diff-by-diff detail — three findings, one of which is
live and actionable:**

1. **The install-URL pin finding below is RESOLVED for `README.md`, and still
   open for the guide — corrected at the 2026-09-22 re-anchor to `2b337296`.**
   This bullet previously read "The install-URL pin is STALE," citing
   `0a2d49b069bd178092e75a8cfd1a1c9df6690cd3` and four commits ahead of it on
   both install scripts. Re-verified at `2b337296`: `README.md:12` and `:18`
   now pin `d541ee5708481fbf18c3a5fda050c9e40a40a2d9` (re-pinned by `2cc73a1e`,
   PR #206), and `git diff --name-only d541ee57..HEAD -- scripts/install-prerequisites.sh
   scripts/install-prerequisites.ps1` is empty — both re-verified directly.
   **`docs/guides/Running-a-Mailbox-Job.json:18` was NOT part of that re-pin**
   and still reads the older `0a2d49b069bd178092e75a8cfd1a1c9df6690cd3` — one
   re-pin event (`2cc73a1e`) behind, but **59 commits** behind `d541ee57` in raw
   git history (`git log --oneline 0a2d49b0..d541ee57 | wc -l` = 59; corrected
   from "one commit behind" in an earlier version of this bullet, which
   conflated the single re-pin commit with git-history distance) — re-verified
   by grep at this pass. Not fixed here; that file is outside this note's
   write scope.
   `install-scripts.md` carries the corresponding correction to its own pin
   bullet.
2. **The open `.mmd`-count question from the previous pass is RESOLVED, and the
   answer is "stale", not "scoped to a subset".** The previous pass found six
   `.mmd` files against this note's "three" and explicitly declined to decide
   which reading was right, saying it needed a read of `render.sh`'s actual
   invocation site. That read is done:
   `plugin/crew/skills/crew-diagrams/scripts/render.sh:75` is
   `FILES=("$DIR"/*.mmd)` — a glob over the whole directory, under
   `shopt -s nullglob` at `:74`, with no hardcoded list anywhere in the file.
   (At the `03b19262` anchor this was re-pointed against a flag-parsing and
   artifact-check rework then still uncommitted on this branch. **That rework
   has since landed, in the `03b19262 -> 5d1fc5fd` range, and it is now part
   of this note's own anchor** — re-read directly at `5d1fc5fd`, `:74` and
   `:75` are byte-identical to what was described then, so the citation needed
   no repointing, only this note saying so.)
   So `render.sh` renders **all six**, and both "three `.mmd` sources" and
   "six files, three names x two formats" were simply out of date. Corrected in
   place below.
3. **A count is wrong in three of the four catalog docs that state it, the gate
   is green, and it is not the skills count this time.** Measured from
   `plugin/crew/hooks/hooks.json` via `json.load`: **20 hook entries, 10
   scripts x `.sh`/`.ps1`, across 5 events.** `plugin/PLUGINS.md:17` says
   exactly that and is correct. `README.md:168`, `plugin/README.md:414` and
   `INSTALLATION.md:252` all say **18** (and `README.md:168` adds "9 scripts").
   None of the four carries a `claim:` marker for the hook figure — the
   `plugin-skills:crew` marker on the same lines covers only the skills number —
   so `check_self_claims` cannot see this and `python3
   scripts/check-marketplace.py` passes. Reported, not fixed; those four files
   are outside this note's write scope. `marketplace-registration.md` owns the
   catalog-count table and carries the same finding.

**Not re-read this pass**, and not claimed as fresh: the bodies of
`plugin/crew/hooks/scripts/crew_state.py` and `scripts/check-marketplace.py`
beyond the specific citations this note makes into them (both files changed
substantially; `crew.md` and `verification-harness.md` own them), the contents
of `docs/superpowers/plans/` and `specs/` beyond their filenames, the two
`.mmd` files the diff named as changed beyond confirming they exist and are
globbed by `render.sh`, and `CHANGELOG.md`'s history below the `[Unreleased]`
region. The older provenance sections below are retained as history and were
not re-checked.

## Re-anchor provenance — 975480b7 -> f9bb78a6, 2026-09-14

Narrow pass: this pass did not diff the 13 repo paths this note's per-path
check tracks against `f9bb78a6` — `plugin/README.md` has never been one of
them; the note cites it separately, in the "self-stated counts" claim below,
without folding it into the tracked-path list. `f9bb78a6`'s own changed-file
set — `README.md`, `INSTALLATION.md`, `plugin/PLUGINS.md`,
`plugin/README.md`, `scripts/check-marketplace.py`,
`scripts/_test/self-claims.py` — touches none of the 13 either. This pass
re-read only `plugin/README.md:414` (below), because `f9bb78a6` is known to
have added a claim marker there. The rest of this note, including the
`0a9d8937 -> 975480b7` section immediately below, is retained as history and
was not re-checked.

## Re-anchor provenance — 0a9d8937 -> 975480b7, 2026-09-14

Narrow pass: this pass did not diff the 13 repo paths this note cites against
`975480b7`. It re-read only the "self-stated counts on the front page" claim
(below) because `f12003e2` (#166) is known to have changed
`plugin/README.md:414`'s skill count since `0a9d8937`, and it separately
flagged (found, not fixed) a stale-looking `.mmd`-count claim noticed while
in the file — see "Owns data" below. The rest of this note, including the
`7b0d8f3a -> 0a9d8937` section immediately below, is retained as history and
was not re-checked.

## Re-anchor provenance — 7b0d8f3a -> 0a9d8937, 2026-09-14

`git diff --name-only 7b0d8f3a..HEAD -- <the 13 repo paths this note cites>`
returns five: `plugin/crew/README.md`,
`plugin/crew/hooks/scripts/_test/run-tests.sh`,
`plugin/crew/skills/crew-docs/SKILL.md`,
`plugin/crew/skills/crew-runbooks/SKILL.md` and `scripts/sync-updates.py`.
The other eight — `docs/diagrams/*.mmd`, `docs/HANDOFF.md`,
`docs/remaining-setup.md`, `docs/runbooks/rollback.md`, `CHANGELOG.md`,
`README.md`, `TODO.md` and `.gitignore` — are closed by that result for any
citation that survives byte-identical; two of them (`CHANGELOG.md`, `TODO.md`)
still needed their *line numbers* re-taken because both files grew a great
deal in this range even though the passages this note cites did not change in
substance.

**The two changes that matter most from this pass are not line-number drift —
read these even if you skip the rest of the diff-by-diff detail:**

1. **`docs/adr/` now exists.** The previous four versions of this note carried
   a landmine titled "`docs/adr/` does not exist, and three documents about
   *this* repo say otherwise." That is no longer true. `docs/adr/0001-promote-
   stays-unarmed.md` was added in crew 0.19.33 (`dd96981d`, within this diff
   range), recording the `/crew:promote` "stays unarmed" decision. DERIVED:
   `ls docs/adr/` returns exactly that one file; `git log --diff-filter=A --
   'docs/adr/*'` shows one add, that commit. `CLAUDE.md:147`'s "Decisions in
   `docs/adr/`." is therefore now a TRUE claim, not a false one — the opposite
   correction from every previous pass over this landmine. See "docs/adr/ now
   exists" below for what replaces the old entry.
2. **The diagram provenance claim inverted.** The previous version said
   `%% Anchors: <paths>` — the second header line in each `.mmd` — "is read by
   **no code** in this repo," citing only a skill doc and a test fixture as
   uses. At this anchor `_DIAGRAM_ANCHORS_RE` and `_diagram_paths` are real
   functions in `plugin/crew/hooks/scripts/crew_freshness.py`, and
   `read_diagrams` calls `_diagram_paths` at
   `plugin/crew/hooks/scripts/crew_freshness.py:522` specifically to get the
   path list `_moved_since` diffs against. This is not new code introduced in
   this range — it predates this note's previous anchor — so the earlier
   claim was wrong when it was written, not made wrong by a later change.
   Found while cross-checking `crew.md`'s citations into the same module for
   this pass; see "The machine-read diagram header" below for the corrected
   account.

## Does
Holds the repo's hand-written documentation — Mermaid diagram sources under
`docs/diagrams/`, planning artifacts under `docs/superpowers/`, one
operational runbook, handoff notes, `docs/adr/` (new — see above), and the
top-level `CHANGELOG.md`. Nothing under `docs/` is generated except the
rendered diagram images in `docs/diagrams/out/`. (JUDGEMENT: "prose is never
auto-refreshed" is not written down as a rule; it is inferred from there being
no writer. `scripts/sync-updates.py` — changed in this range, re-read rather
than carried — mirrors README sections between locations and gained a new
guard this pass, `splice`'s duplicate-marker check at `:114-125`: a second
`BEGIN`/`END` pair for the same marker used to update silently only the
first occurrence and report "already current," which is how `skills/README.md`
carried a stale count through CI for four days. It still does not write
`CHANGELOG.md` — DERIVED, the same citations as before, `:20` and `:73`,
unchanged position despite the file's other changes.)

## Entry points

- DERIVED `docs/diagrams/architecture.mmd:1-2` — and
  `docs/diagrams/data-flow.mmd:1-2`, `docs/diagrams/process.mmd:1-2` alongside
  it (written repo-relative here rather than as bare basenames, so all three
  paste into the path diff). Line 1 is
  `%% anchor: useful-claude-add-ons@<sha>`, line 2 is
  `%% Anchors: <paths>`. Those three still read `1f97e51c`, **behind** this
  anchor — confirmed by direct read, at the `2b337296 -> 03b19262` provenance
  section below (this bullet's own line 1 claim was carried forward unread at
  the `84976536 -> 2b337296` pass, and is only closed by that later read).

  **The directory now holds two provenance shapes, and this entry only ever
  described one.** At the `84976536 -> 2b337296` pass, only the three
  `%% Generated from...`-style diagrams were freshly re-read (the other three,
  `%% anchor:`-style, were carried forward and only confirmed later — see
  above): `docs/diagrams/data-flow-crew-config.mmd`,
  `docs/diagrams/process-crew-brief.mmd` and
  `docs/diagrams/process-bitbucket-svg.mmd` use the
  `%% Generated from <repo>@<sha> on <date>. Verify before trusting.` form,
  and **all three were re-derived in commit `2b337296`** ("diagrams:
  re-derive data-flow-crew-config, process-bitbucket-svg, process-crew-brief"):
  at that pass all three read line 1 `%% Generated from
  useful-claude-add-ons@84976536 on 2026-09-22. Verify before trusting.` and
  carry a `%% Anchors:` line 2 naming the source files each diagram covers — a
  correction from the previous version of this entry, which cited these three
  at `ea8a0143`, `ea8a0143` and `a573ca24` respectively. Those three sha
  citations were stale by **one** re-derivation (`ea8a0143`/`a573ca24` ->
  `84976536`), corrected from a previous version of this bullet that
  miscounted it as two. `03b19262` (the commit immediately after `2b337296`)
  changed only bare `%%` comment lines in the body of these three diagrams to
  fix a Mermaid parse failure — line 1 and line 2 of all three are
  byte-identical across that commit, confirmed at the `2b337296 -> 03b19262`
  section below, so it does not add a further re-derivation.
  Both forms are accepted by `_DIAGRAM_ANCHOR_RE` (see `INDEX.md`, which owns
  the contract), so this is two supported spellings rather than broken files.
- DERIVED `docs/adr/` — **three** ADRs at this anchor, not the one the
  previous pass recorded: `0001-promote-stays-unarmed.md` (unchanged file,
  closed by the per-path check), plus `0002-no-chatgpt-mcp-server.md` and
  `0003-crew-departs-from-three-community-best-practices.md`, both added since
  `ea8a014`. Re-measured with `ls docs/adr/` rather than carried forward. The
  series the previous pass described as just-started is now being kept; see
  "docs/adr/ now exists" below, whose account of `0001` still stands.
- DERIVED `docs/HANDOFF.md:1-9` — rolling handoff notes, newest first.
  Maintained by hand; see the landmine below, it is **not** what
  `/crew:handoff` writes. File unchanged in this range (closed by the
  per-path check); its newest entry is still dated 2026-08-23 — **30 days**
  behind this anchor, up from 22 at the previous anchor, 20 before that and 14
  before that.
  Re-measured each pass because a "days behind" figure is stale the day after
  it is written.
- DERIVED `docs/remaining-setup.md:1-6` — the ordered manual checklist for the
  four workstreams needing credentials, consent, or a decision no script can
  make. Unchanged file, not re-read beyond confirming it still exists.
- DERIVED `docs/runbooks/rollback.md:9-14` — the "When to use this" list.
  Unchanged file (closed by the per-path check); still carries
  `last verified: 2026-09-05` at `:3`, now **17 days** stale by the same
  re-measurement logic as `HANDOFF.md`, and this note cannot refresh that date
  since it is not the runbook's owner.
- DERIVED `CHANGELOG.md:5` — the `## [Unreleased]` heading. Position unchanged
  again, despite the file reaching **7885 lines** (`wc -l`, re-measured this
  pass; it was 7875 at the previous anchor — a doc-builder 1.5.3 entry added 10
  lines at line 9, below the heading). Re-read directly; `:5` is still the
  heading.
- `README.md:12` and `:18` — the bootstrap one-liners, **re-pinned again since
  the previous anchor: `9ea10e21` -> `1b19e5d8` -> `0a2d49b069bd178092e75a8cfd1a1c9df6690cd3`
  (both moves 2026-09-14) -> `d541ee5708481fbf18c3a5fda050c9e40a40a2d9`
  (`2cc73a1e`, "README: re-pin install URLs to d541ee57 after PR #205 changed
  both install scripts (#206)", 2026-09-22)** — the **third** move in that
  chain (`9ea10e21`->`1b19e5d8`, `1b19e5d8`->`0a2d49b0`, `0a2d49b0`->`d541ee57`:
  three arrows, corrected from "the fourth move" in a previous version of this
  bullet, which miscounted), because PR #205 (`d541ee57`) changed the Linux
  install path, the community marketplace and the `uv` install chain in both
  install scripts, which left `0a2d49b0` serving a version with none of that.
  Re-verified directly at this pass, not carried: `README.md:12` and `:18` now
  read `d541ee57...`, and
  `git log --oneline d541ee57..HEAD -- scripts/install-prerequisites.sh
  scripts/install-prerequisites.ps1` is empty — the pin is current.
  **This 2026-09-22 move was one commit, not two — but "two moves in one day"
  is common in this file's history, not a single instance, and a previous
  version of this bullet was wrong in that direction too.** Verified with
  `git log --format='%h %ad %s' --date=short -L12,12:README.md`, the full
  commit history of the pinned-URL line: 2026-09-22 shows exactly one commit
  (`2cc73a1e`). But 2026-09-14 shows **two** (`d13ea445`, `8c8353f5`) and
  2026-09-13 shows **four** (`819bf382`, `91a7aab1`, `2ce6b4e8`, `a4a48456`) —
  and multi-commit days recur throughout the file's history back to 2026-07-28
  (2026-08-28, 2026-08-11 and 2026-08-04 each show four; 2026-08-23 shows
  three). So the pattern is not "observed once, on 2026-09-14" as a previous
  version of this bullet said — it is the ordinary rate this file re-pins at
  whenever several install-script-touching changes land close together. What
  still holds: any change registering a marketplace entry or touching either
  install script edits both scripts in one commit, so the pin goes stale on
  essentially every such entry, and a recent re-pin is no evidence the pin
  will still be fresh next week.
  **A third site carries an install-URL SHA and was NOT part of this
  re-pin.** `docs/guides/Running-a-Mailbox-Job.json:18` embeds the PowerShell
  one-liner inside a JSON step string; re-checked at this pass, it still reads
  `0a2d49b069bd178092e75a8cfd1a1c9df6690cd3` — one re-pin event (`2cc73a1e`)
  behind the README, but **59 commits** behind in raw git history
  (`git log --oneline 0a2d49b0..d541ee57 | wc -l` = 59, re-measured this
  pass — "one commit behind" in a previous version of this bullet was wrong;
  a single re-pin commit does not mean the two SHAs are adjacent commits).
  `docs/runbooks/rollback.md:55`, which says to replace
  the SHA in "BOTH raw.githubusercontent.com URLs in README.md," is still an
  undercount by this same site, and following it literally now leaves that
  guide installing a script older than the one shipped by PR #205. Not fixed
  here — outside this note's write scope. Re-measure with
  `grep -rn <old-sha> --include='*.md' --include='*.json' .` rather than
  trusting this list; `.claude/worktrees/` copies are agent worktrees and are
  not tracked sites.
  **The re-pinned URL was not fetched live at this pass** (the previous
  anchor's HTTP-200 fetch check was not repeated) — flagged as unverified
  rather than carried forward as still true.
- `TODO.md` — re-resolved rather than trusted at its old line numbers, per
  this note's own standing rule that `TODO.md` is edited often. The render.sh
  entry moved from `:870-899` to `:1061-1091`; see "TODO.md's render.sh entry"
  below.
- `scripts/sync-updates.py:147` — module entry point (`main()`), from the graph

## Owns data

- DERIVED `docs/diagrams/out/*.svg` and `*.png` — **twelve files, six names x
  two formats**, corrected this pass from the "six files, three names" this
  note carried for five anchors. Produced by
  `plugin/crew/skills/crew-diagrams/scripts/render.sh` — output dir created at
  `:88`, `mmdc` invoked at `:126` and again at `:133` on the failure path. All
  three were pointed, at the `03b19262` anchor, at line numbers that did not
  yet exist there — the file committed at `03b19262` was 63 lines, not the 151
  these numbers assume. That gap has closed by different mechanisms per line,
  checked individually rather than assumed uniform: `:88`
  (`OUT="$DIR/out"; mkdir -p "$OUT"`) is content that already existed at
  `03b19262` (at `:20` there) and simply moved down, unchanged, because the
  flag-parsing rework inserted lines above it; `:126` and `:133` are content
  that is genuinely new — the temp-file-and-`[ -s "$tmp" ]` check is absent
  from the `03b19262` file entirely (confirmed by diff, not by line-number
  absence alone). Either way, all three now match the committed file at
  `5d1fc5fd` — see "Calls out to" below for the `:126`/`:133` confirmation.
  `docs/diagrams/out/` itself is gitignored at
  `.gitignore:409` — unchanged, and `.gitignore` is not in this range's changed
  set. `git ls-files docs/diagrams/` returns **six** `.mmd` sources:
  `architecture.mmd`, `data-flow-crew-config.mmd`, `data-flow.mmd`,
  `process-bitbucket-svg.mmd`, `process-crew-brief.mmd`, `process.mmd`.

  **The previous pass's open question is now answered, and the answer is the
  less flattering of the two it offered.** That pass found six `.mmd` files
  against this note's "three", and left open whether the note was stale or
  whether "three" had always been correctly scoped to a subset `render.sh`
  targets — deferring it as needing a read of `render.sh`'s invocation site.
  That read is done. DERIVED
  `plugin/crew/skills/crew-diagrams/scripts/render.sh:74-75` (re-confirmed
  byte-identical at `5d1fc5fd`, same as the "Owns data" citation above):
  `shopt -s nullglob` then `FILES=("$DIR"/*.mmd)`. It is a glob over the whole
  directory; there is no hardcoded source list anywhere in the file. So
  `render.sh` renders every `.mmd` present, the count was **stale**, and the
  "scoped to a subset" reading — the one that would have made the old number
  correct — is refuted rather than merely unconfirmed. Recorded this way
  because the previous pass was right to refuse to guess, and the value of that
  refusal is only realised if the next pass actually does the read.
- DERIVED `docs/superpowers/` is hand-written: `plans/` and `specs/`.
  Unchanged; not re-counted file-by-file this pass, only confirmed present.
- **The self-stated counts on the front page have moved and are now partly
  machine-checked.** `README.md:46` and `:154` (moved from `:52` and `:152`)
  state **36 skills** — `python3 scripts/check-marketplace.py`, run at this
  anchor, reports "marketplace: 36 skills, 5 plugins", so 36 is current. The
  one entry added since `ea8a014` is `web-research` (set difference over
  `marketplace.json`'s `plugins` array between `f9bb78a6` and HEAD: one added,
  none removed). `README.md:154` carries
  `<!-- claim: skills-count -->`, so this number is no longer "checked by
  nothing": `check_self_claims`
  (`scripts/check-marketplace.py:649-830`, moved from `:579-722` at the
  `03b19262` anchor, and from `:430` and `:412` before that — re-taken by
  grepping the function definition directly at this pass, because
  `check-marketplace.py` gained two more whole checks
  (`check_description_claims`, `check_catalog_claims`) between `03b19262` and
  `5d1fc5fd` and the insertion is not evenly spaced; see
  `marketplace-registration.md`'s `## Corrected at 5d1fc5fd` for what those two
  check)
  verifies marked numbers against `marketplace.json`, and this repo's own
  `CLAUDE.md` documents the convention (`CLAUDE.md:29`; `CLAUDE.md` changed
  between `03b19262` and `5d1fc5fd`, but the edit landed entirely in the
  `render.sh` regression-test citation further down the file — `:29` is
  byte-identical at both revisions, re-confirmed by direct read rather than
  assumed). `plugin/README.md:414`'s agent count is also no
  longer stale — as of `f12003e2` (#166, "fix three stale self-describing
  counts") it read "54 agents, 26 commands, 18 skills, 20 hook entries."
  **That quotation is superseded at this anchor**: the live line now reads 54 /
  28 / 20, re-measured from disk this pass (`ls plugin/crew/agents/*.md`,
  `commands/*.md`, `skills/*/`) and agreeing. **Re-read at this
  anchor:** `f9bb78a6` (#169) did not change that number again — it added a
  `<!-- claim: plugin-skills:crew -->` marker to the same line instead,
  using a new claim type `check_self_claims` gained specifically to check a
  plugin's own bundled-skill count (`skills-count` only ever checked the
  marketplace-wide total, which is why crew's bundle count had drifted
  uncaught in the first place); its counting helper is `count_plugin_skills`
  (`scripts/check-marketplace.py:563-577`, moved from `:562-576`, and from
  `:413-427` before that). The line
  still reads "54 agents, 28 commands, 20 skills<!-- claim:
  plugin-skills:crew -->, 18 hook entries" verbatim — re-read at this anchor,
  and `plugin/README.md:414` has not moved. On-disk inventory re-measured this
  pass and the marked figures agree: 54 agents, 28 commands, 20 skills.
  **The unmarked figure on that same line does not**: 18 hook entries is
  wrong, the real count is 20 — see finding 3 in this pass's provenance.
  **That quotation tracks the live figures rather than freezing at this
  note's anchor**, and it has to: the marker inside it is a real claim, so
  `check_self_claims` binds it to `plugin/crew/skills/`'s actual count and
  fails the gate when the two diverge. It did exactly that on crew 0.19.66,
  which is a sixth site nobody had listed alongside the five in
  `verification-harness.md` - a codemap note quoting a doc is indistinguishable
  from the doc, to a checker that scans every tracked `*.md`. Update the
  numbers here whenever the five move.
  **Not re-verified this pass:**
  whether `7 of 4
  marketplaces` (community count) and `Seven MCP servers`
  (`INSTALLATION.md:213`) are still accurate — neither carries a
  `claim:` marker, so `check_self_claims` does not cover them, and this note
  did not independently re-count the community marketplace list or the MCP
  server rows. Flagged as unverified rather than repeated as fact.

## Calls out to

- DERIVED `mmdc` (mermaid-cli), at
  `plugin/crew/skills/crew-diagrams/scripts/render.sh:126` (`-s 2`, silenced)
  and `:133` (the retry that prints the last five lines of stderr on FAIL).
  These were pointed at an uncommitted working-tree rework at `03b19262`; that
  rework landed by `5d1fc5fd` and both lines are confirmed against the
  committed file at this anchor, not carried over unread. The `-s 2` call
  renders to a temp file (`$tmp`, checked with
  `[ -s "$tmp" ]`) and only `mv`s it onto the real output path on success, so
  a failed re-render can no longer delete the last good render — different
  in substance from the previous anchor, not just moved.
- `raw.githubusercontent.com` at the pinned sha — unchanged and re-verified
  above under "Entry points."

## docs/adr/ now exists — replaces the previous "does not exist" landmine

**This entire entry is new; it replaces four prior passes' worth of a landmine
that no longer applies.** `docs/adr/0001-promote-stays-unarmed.md` was added
by crew 0.19.33 (`dd96981d0b`, "tests for reportTracked and anchor truncation,
both found by mutation," which folded in the ADR as an incidental part of a
different change — the commit message says so directly: "CLAUDE.md names
`docs/adr/` and the directory did not exist yet ... this starts the numbered
series the project file already calls for").

The ADR itself (`docs/adr/0001-promote-stays-unarmed.md:1-10`) records that
`/crew:promote production --dry-run` and `--status` both stop immediately in
this repo because `.crew/verify.json` declares no `environments` block — a
deliberate, accepted decision (2026-09-13) to leave production promotion
unconfigured here rather than wire it to a real environment. Its own opening
line explains why it is a numbered ADR rather than a fourth flat document
under `docs/`: the design records already there (`change-requests.md`,
`guard-overrides.md`, `rule-of-two.md`) are specifications, not decisions.

**Every previous claim this note made about `docs/adr/` is now the wrong way
round, and is corrected rather than merely deleted so the reversal is
visible:**

- `CLAUDE.md:147` — "Decisions in `docs/adr/`." — is now TRUE. (Previously
  cited as a false claim alongside two others.)
- `CHANGELOG.md:5412` (moved from `:5402`, from `:3429-3430`, and from
  `:2057-2058` before that; re-located by grepping the string at this pass,
  confirming the +10 shift from the doc-builder 1.5.3 entry inserted at line 9
  — not assumed from the offset) — "It also stops
  claiming `docs/adr/`, which is now `scribe`'s" — was always true of *authorship*
  (crew:scribe owns ADRs, not this note) and remains true; what changed is
  only that the directory it discusses now has content.
- `.crew/STATUS.md:39`'s claim that `docs/adr/` was "scaffolded" — **the
  citation is now dangling, and the previous "absent from this checkout"
  wording is also wrong.** At this anchor `ls .crew/` returns `STATUS.md`,
  `codemap/`, `config.json`, `guard.log`, `handoffs/` and `verify.json`:
  `STATUS.md` *is* present on this machine. It is 15 lines long, so there is no
  `:39` to read, and `grep -n adr .crew/STATUS.md` returns nothing — the file
  was rewritten (its own `updated:` field reads 2026-09-22) and no longer says
  anything about `docs/adr/`. **It remains UNVERIFIABLE HERE in the sense that
  matters**: `git ls-files .crew/` does not list it, so it is machine-local and
  no cloner can check any claim about it, including this one. Recorded rather
  than deleted because "absent" and "present but rewritten" are different
  facts, and the earlier wording would send a reader looking for a missing
  file instead of a changed one.

JUDGEMENT: the many `docs/adr/` references under `plugin/crew/` —
`plugin/crew/agents/scribe.md`, `plugin/crew/skills/crew-docs/SKILL.md`,
`plugin/crew/README.md`, and others — are the crew plugin instructing *any*
repo it is installed into, not claims about this one. Not re-enumerated this
pass; the previous pass's citations into them were not re-verified and should
not be trusted without a fresh read if they are needed again.

## Corrected at 5d1fc5fd

**The `render.sh` / `_test/render.sh` "not yet reflected in this file's `03b19262`
anchor" caveats, scattered through this note above, all resolve the same way:
the rework landed in `30173e99`'s sibling commits (part of PR #208, crew
0.20.11) and is now committed history, not a working-tree draft.** Measured
directly rather than assumed:

- `plugin/crew/skills/crew-diagrams/scripts/render.sh` — **63 lines at
  `03b19262`, 151 at `5d1fc5fd`** (`git show 03b19262:... | wc -l` vs `wc -l`
  on the checkout). The file also gained the executable bit
  (`100644` -> `100755`) in this range. Every citation this note makes into it
  (`:74-75`, `:88`, `:93-99`, `:100-104`, `:126`, `:133`) was re-read directly
  against the committed file at `5d1fc5fd` and matches exactly.
- `plugin/crew/skills/crew-diagrams/scripts/_test/render.sh` — **79 lines at
  `03b19262` (case 2 at `:74`, 2 cases total — `git show
  03b19262:plugin/crew/skills/crew-diagrams/scripts/_test/render.sh` shows
  only "1. plain invocation..." and "2. MSYS_NO_PATHCONV=1..."), 279 lines at
  `5d1fc5fd` (case 2 at `:104`, 12 cases total, per the file's own header
  comment: "cases 1-2 ... case 3 ... cases 4-12")**. `CLAUDE.md`'s own
  citation into this file moved the same way, corrected there and
  cross-checked here.
- `CHANGELOG.md` gained a 44-line bullet inserted at line 9, immediately after
  the existing `### Fixed` heading — that heading already existed at `:7` in
  the `03b19262` file (`git show 03b19262:CHANGELOG.md`, confirmed by direct
  read), so this is a new entry inside an existing section, not a new
  section. The `## [Unreleased]` heading at `:5` is unaffected either way.
  The new bullet documents both the `render.sh` rework and the
  `check_description_claims`/`check_catalog_claims` fix
  `marketplace-registration.md` and `install-scripts.md` both cover in full.
  File is now **7929** lines (was 7885).
- `TODO.md` grew +81/-5 lines but not at its `:634-761` (agent-count, CLOSED)
  or `:1061-1091` (render.sh, still open) entries — both re-confirmed at their
  existing line numbers by grepping their headings, unmoved.
- `plugin/crew/README.md:2097` — this is the file that actually changed in
  this range (27 -> 28 commands, now marker-carrying), part of the
  fifth-inversion fix `marketplace-registration.md` and `install-scripts.md`
  both cover in full; not the `plugin/README.md:414` catalog row this note's
  `## Owns data` section cites, which was **not** touched in the
  `03b19262 -> 5d1fc5fd` range (confirmed absent from the changed-file list
  above) — its commands figure already read 28 at `03b19262`, and its
  hook-entry figure is still wrong (18, not 20) and still unmarked, unchanged
  from the `03b19262` finding. Do not conflate the two `README.md` files —
  `plugin/README.md` is the top-level catalog table, `plugin/crew/README.md`
  is crew's own bundled doc.
- `.crew/verify.json` and `plugin/crew/hooks/scripts/_test/run-tests.sh` also
  changed in this range. The former is wording-only in unrelated `why` fields
  (confirmed by diff, not cited by line number in this note). The latter
  hardens a test fixture's own stub scripts against a gap a review round
  found; not cited by line number in this note and not read beyond confirming
  the changed-file result.

## Landmines

- **The machine-read diagram header is line 1, and line 2 is also read, by
  code that exists but was previously missed.** Corrected this pass — see the
  top of this note. Staleness is decided by `_DIAGRAM_ANCHOR_RE`
  (`plugin/crew/hooks/scripts/crew_freshness.py:128-132`, the reasoning
  comment at `:116-127`), matching `%% Generated from <repo>@<sha>` or
  `%% anchor: <sha>`, applied in `read_diagrams`
  (`plugin/crew/hooks/scripts/crew_freshness.py:473-524`) where
  `sha[:7] == head[:7]` (`:513`) decides `current` vs not. A diagram whose
  anchor is old is only marked `behind`, though, once `_moved_since(root, sha,
  head, _diagram_paths(root, body))` is not `False` (`:522`) — and
  `_diagram_paths` is exactly the function that reads the `%% Anchors:` line
  this note previously said nothing consumed. `_DIAGRAM_ANCHORS_RE` (the
  plural-name regex for that second line) and `_diagram_paths` both live in
  `crew_freshness.py`, re-exported through
  `plugin/crew/hooks/scripts/crew_state.py:120` and `:127`.
  So: line 1 makes a diagram machine-checkable at all; line 2 is what narrows
  "the anchor is old" down to "and something it actually cites moved" —
  **not** merely a hand-re-verification aid the way the previous version of
  this note described it. Losing line 2 now costs more than a manual check:
  without it, `_diagram_paths` falls back to the whole-tree deny-list diff
  (documented in `read_diagrams`'s own docstring,
  `plugin/crew/hooks/scripts/crew_freshness.py:481-486`), which will report
  `behind` far more readily than a correctly-scoped one would.
  DERIVED `plugin/crew/skills/crew-diagrams/SKILL.md:37-43` (unchanged,
  content and line range both re-confirmed): a source with no parseable
  provenance still counts as `behind` outright — unknown resolves to stale.

- **`/crew:handoff` does not write `docs/HANDOFF.md`.** Unchanged from the
  previous anchor; re-confirmed rather than re-derived since none of the
  files this claim rests on are in the changed set. DERIVED
  `plugin/crew/commands/handoff.md:7` — "Write `.work/HANDOFF.md` following
  the `crew-context` skill" — and `.crew/config.json:5`,
  `"handoffPath": ".work/HANDOFF.md"` (machine-local and gitignored; present
  in this checkout and re-read, but not checkable by anyone cloning the
  repo). `plugin/crew/skills/crew-context/SKILL.md:62` says the same
  ("Write it to `.work/HANDOFF.md`"), unchanged position, re-confirmed.
  `docs/HANDOFF.md` is human-authored; the two files are unrelated
  despite the shared basename. **Corrected this pass:** the previous version
  said `docs/HANDOFF.md` is "reached from `README.md:730`." `README.md`
  changed in this range (17 lines) and no longer mentions `HANDOFF` anywhere —
  grepped for both the full path and the bare word, zero hits. Whatever linked
  to it before this range does not now; not investigated further, since
  `README.md` is outside this note's five changed files and finding where the
  link went would mean reading the whole diff rather than the cited line.

- **`TODO.md`'s `render.sh` entry is still at `TODO.md:1061`** — re-located by
  grepping the heading at this anchor and found not to have moved, even though
  `TODO.md` is in this range's changed set; the edits landed elsewhere in the
  file. It is still **not** marked CLOSED. (Previously re-resolved from the old
  `:870-899`, which no longer points at this section — `TODO.md` grew by
  roughly 1400 lines in this range even though it is not in the 5-file
  changed set the per-path check names, which means it changed in ways that
  did not touch any of the *other* passages this note cites, not that it was
  untouched). The section heading, "`render.sh` cannot render a diagram on
  Windows — it hands `mmdc` a `/tmp` path," is still **not** marked CLOSED,
  unlike its now-numerous neighbours that are (`TODO.md:634`, `:1093`, `:2037`,
  `:2116`, `:2161`, and others). Its content is unchanged in substance: six
  failures for six on 2026-09-05, the same three sources rendering cleanly
  when `mmdc` is invoked directly, and the same proposed fix
  (`cygpath -w`), which has since landed —
  `plugin/crew/skills/crew-diagrams/scripts/render.sh:100-104` sets
  `PCFG_ARG` from `cygpath -w "$PCFG"` when `cygpath` exists, re-read at
  `5d1fc5fd`. `plugin/crew/skills/crew-diagrams/scripts/render.sh:93-99` still
  names the real trigger: `MSYS_NO_PATHCONV=1` set in the caller's
  environment, not a Mermaid problem. **Correction to a claim this note briefly
  carried between the previous pass and this one: this block is NOT part of
  the flag-parsing/artifact-check rework and was NOT missing at `03b19262` —
  it had the cygpath handling already**, at `:25-36` in the file committed
  there (`git show 03b19262:plugin/crew/skills/crew-diagrams/scripts/render.sh`,
  confirmed by direct read; `PCFG_ARG="$PCFG"` at `:32`, the `cygpath` branch
  at `:33-36`). Diffed against the current `:100-104`/`:93-99` content
  directly (not by line-number offset): the two are the same text. What moved
  is only the line number, because the flag-parsing rework inserted ~70 lines
  *above* this block, between `03b19262` and `5d1fc5fd` — this specific
  passage's content did not change in that range at all.

- **The regression test for that fix is no longer misdocumented — this
  landmine is resolved, not carried forward.** Four previous versions of this
  note recorded that `CLAUDE.md` cited the wrong path for the `render.sh`
  regression test (`scripts/_test/render.sh`, which does not exist, instead
  of `plugin/crew/skills/crew-diagrams/scripts/_test/render.sh`, which does).
  At this anchor, `CLAUDE.md:280-282` (case citation at `:282`) correctly names
  `plugin/crew/skills/crew-diagrams/scripts/_test/render.sh` and its case 2
  (`MSYS_NO_PATHCONV=1`), which asserts a non-zero-sized output file rather
  than exit 0, exactly as `CLAUDE.md` now says.
  **Neither this note nor `CLAUDE.md` states the file's total line count
  any more** — a self-referential count changes itself every time this note
  or that file is next edited, per this note's own "A self-referential count
  changes itself" landmine below. Cite the case by name and its own line
  instead: `nonzero_svg "MSYS_NO_PATHCONV=1"` is invoked at
  `plugin/crew/skills/crew-diagrams/scripts/_test/render.sh:104` at
  `5d1fc5fd`, re-confirmed by direct read. **This was NOT yet true at this
  note's own `03b19262` anchor** — at that commit the file was 79 lines and
  the case sat at `:74` (`git show 03b19262:plugin/crew/skills/crew-diagrams/scripts/_test/render.sh
  | wc -l` = 79); the `:104` citation in the previous version of this bullet
  was pointed at an in-progress rework on the working branch, not at anything
  committed at `03b19262`. That rework — 12 cases instead of 2, 279 lines —
  landed in the `03b19262 -> 5d1fc5fd` range (see `## Corrected at 5d1fc5fd`
  above), and `:104` is correct now that it has.
  `CLAUDE.md` itself records the correction date as 2026-09-12. Kept as an
  entry here, rather than silently dropped, because a landmine repeated four
  times and then fixed is worth one line saying so — the next reader who
  remembers the old warning should not go looking for a bug that is gone.

- **`docs/runbooks/INDEX.md` does not exist — unchanged.** DERIVED:
  `docs/runbooks/` still contains `rollback.md` alone (re-confirmed this
  pass), while `plugin/crew/skills/crew-runbooks/SKILL.md:80` (unchanged
  position despite the file being in this range's changed set — the edit was
  elsewhere) and `plugin/crew/README.md:1604` (moved from `:1549`) both still
  describe `docs/runbooks/INDEX.md` as the symptom-keyed index. JUDGEMENT:
  with one runbook this costs nothing; it becomes a real gap at the second.

- **A count written into a file under `docs/` changes that count.** JUDGEMENT,
  unchanged. This note is under `.crew/codemap/`, so its own counts are not
  self-referential; they are still only true at this anchor.

## Unverified
- Whether `render.sh` succeeds end to end on this machine. Not run this pass
  either. The committed regression test (above) is evidence the `cygpath`
  path is covered in principle; that it *passes* here is still unmeasured.
- The two unmarked self-counts both **moved** in this range, which is itself
  the finding — an unmarked number that changes is exactly what no check sees.
  `INSTALLATION.md:213` now reads "**Eight** MCP servers are menu rows, all off
  by default" (it said *Seven* at the previous anchor). `README.md:157` now
  reads "4 marketplaces" beside a seven-plugin community list. **That one is
  wrong**: `COMMUNITY_KEYS` (`scripts/install-prerequisites.sh:1379-1382`) holds
  **eight** keys — the seven listed plus `eli5` — and `eli5` comes from a fifth
  marketplace, `claude-community`, so the row undercounts both the plugins and
  the marketplaces. Neither line carries a `claim:` marker, so
  `check_self_claims` covers neither and the gate is green over both. The row
  count itself was not independently re-derived against the live external
  marketplaces; only the repo-local catalog it is supposed to mirror was read.
- Whether `CHANGELOG.md` entries are strictly one per plugin-version bump
  throughout. Only the opening `[Unreleased]` region was read this pass; the
  now much larger history (**7885 lines**) was not read back. The rule
  actually written down remains `plugin/crew/skills/crew-docs/SKILL.md:26`
  (position unchanged, re-confirmed), gating an entry on "Behaviour users or
  callers can observe changed," not on a version bump.
- The contents of `docs/superpowers/plans/` and `specs/` beyond their
  filenames.
- Whether the community counts this note has never independently verified
  reflect the current state of those external marketplaces at all — out of
  scope for a repo-local codemap regardless. What *was* checked this pass is
  narrower and stated above: the repo-local catalog arrays the README row is
  supposed to mirror.
- The bodies of the two `.mmd` files the path diff named as changed
  (`data-flow-crew-config.mmd`, `process-crew-brief.mmd`). Confirmed present and
  confirmed to be globbed by `render.sh`; their contents and their own
  `%% anchor:` lines were not re-read. The diagrams carry their own provenance
  contract and `INDEX.md` owns it.

## Older provenance, kept as an account of process rather than a current claim

Five prior re-anchors are on record: `1f97e51c` (initial), then `3167721f`,
`b56d41f`, `d61342c3` (unresolvable — a squash merge discarded the branch
commit the writer recorded, fixed by crew 0.19.13's anchor-writer change), and
`7b0d8f3a`. Each corrected at least one claim the previous version got wrong —
a `CHANGELOG.md` range that pointed at the wrong topic, three landmines not
written repo-relative, a `TODO.md` citation off by roughly 320 lines, and the
diagram-header reader misattribution corrected at the top of this pass. The
lesson each one reinforced, kept here rather than repeated at every citation:
`TODO.md` and `CHANGELOG.md` are edited often enough that a line-number
citation into either should be treated as provisional the moment either file
is known to have grown, and this note is mixed-base by nature — its citations
into files that changed in this range are re-derived, and its citations into
files that did not are closed by the per-path check, and the two are not
interchangeable evidence.

## Re-anchor provenance — 84976536 -> 2b337296, 2026-09-22

**Corrected at the 2b337296 -> 03b19262 pass, below: this section previously
said "30 tracked paths" and "Five changed," neither of which matched what was
actually run.** The 32-path list this note's own `ea8a014 -> 84976536` section
enumerates (16 changed + 16 unchanged, listed above) is the pathspec actually
usable here, run verbatim:

```
git diff --name-only 84976536..HEAD -- .crew/verify.json CHANGELOG.md \
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

Output, verbatim:

```
CHANGELOG.md
README.md
docs/diagrams/data-flow-crew-config.mmd
docs/diagrams/process-crew-brief.mmd
```

**Four changed, not five.** `docs/diagrams/process-bitbucket-svg.mmd` is
**not** in this 32-path list at all — confirmed by grep over the `ea8a014 ->
84976536` section's own two file lists above, neither of which names it. That
is itself a gap worth recording: the "Entry points" section below discusses
all six `.mmd` files by name, including `process-bitbucket-svg.mmd`, but this
note's tracked-path list only ever covered two of the three
`%% Generated from...`-style diagrams. It was still re-read at this pass
(confirmed changed by a separate, wider check —
`git diff --name-only 84976536..2b337296` over the whole repo lists it), so
the claim made about its contents below is not wrong, but citing it as part of
"the 30 tracked paths" was.

All four files actually returned by the pathspec above (`CHANGELOG.md`,
`README.md`, `data-flow-crew-config.mmd`, `process-crew-brief.mmd`), plus
`docs/diagrams/process-bitbucket-svg.mmd` (checked separately, as just
explained, since the pathspec cannot return it), re-read directly, not
offset:

- `CHANGELOG.md` gained 10 lines at line 9 (a doc-builder 1.5.3 entry), now
  **7885** lines (`wc -l`, was 7875). `CHANGELOG.md:5` — the `## [Unreleased]`
  heading — is unaffected (the insertion is below it). `CHANGELOG.md:5402`
  moved to `:5412`, re-located by grepping the string and confirming the +10
  shift rather than assuming it.
- `README.md:12` and `:18` re-pinned `0a2d49b069bd178092e75a8cfd1a1c9df6690cd3`
  -> `d541ee5708481fbf18c3a5fda050c9e40a40a2d9` (`2cc73a1e`, PR #206). Both
  re-verified directly; `git log --oneline d541ee57..HEAD -- scripts/install-prerequisites.sh
  scripts/install-prerequisites.ps1` is empty, so the pin is current. This
  resolves finding 1 from the previous pass ("the install-URL pin is STALE")
  for `README.md` specifically — `docs/guides/Running-a-Mailbox-Job.json:18`
  was checked separately (it is a cited path, unchanged in this diff) and
  still reads the older `0a2d49b0` SHA, now one re-pin further behind (the
  "one commit" wording this bullet previously used was never true — 59 commits
  separate `0a2d49b0` from `d541ee57`; corrected where this note first
  measured that, above).
- The three `%% Generated from ...` diagrams were re-derived by `2b337296`
  ("diagrams: re-derive data-flow-crew-config, process-bitbucket-svg,
  process-crew-brief"). All three now read line 1 `%% Generated from
  useful-claude-add-ons@84976536 on 2026-09-22. Verify before trusting.` and
  carry a `%% Anchors:` line 2. This note's previous citation of them at
  `ea8a0143`/`ea8a0143`/`a573ca24` is corrected in place, above.

**Not re-read at this specific pass**: everything else in this note. The
three `%% anchor:` diagrams (`architecture.mmd`, `data-flow.mmd`, `process.mmd`)
were not re-opened here. `docs/diagrams/architecture.mmd` IS in the 32-path
pathspec (it is named in the verbatim command above), and the diff returned
nothing for it, so it is unchanged in this range; `data-flow.mmd` and
`process.mmd` are not in that pathspec, so for those two the diff says
nothing either way. All three were carried forward, stated to still read
`1f97e51c` on the strength of the previous pass's reading rather than a fresh
one at this point. **They were
subsequently re-opened and confirmed** at the `2b337296 -> 03b19262` section
immediately below, which is a later pass, not this one; that confirmation
does not retroactively make this section's own claim about them a fresh read.
`docs/adr/`'s three-file inventory, `HANDOFF.md`'s staleness count and every
other DERIVED claim not listed above are carried forward on the per-path
check alone.

## Re-anchor provenance — 2b337296 -> 03b19262, 2026-09-22

HEAD advanced while the pass above was in flight: `03b19262` ("diagrams: no
bare %% lines") landed on this branch. **This section previously said the
check below ran over "the tracked paths this note cites" — it did not; that
pathspec is the 32-path list above, which (per the gap already recorded in
the `84976536 -> 2b337296` section) omits `process-bitbucket-svg.mmd`,
`data-flow.mmd` and `process.mmd` entirely, so it cannot return
`process-bitbucket-svg.mmd` the way the output below does.** The command
actually run, and its actual output:

```
git diff --name-only 2b337296..03b19262
```
```
docs/diagrams/data-flow-crew-config.mmd
docs/diagrams/process-bitbucket-svg.mmd
docs/diagrams/process-crew-brief.mmd
```

No pathspec — the whole-repo diff between these two commits, which happens to
return exactly the three diagrams `03b19262`'s commit message says it touched.
Re-read the diff itself: every changed line is a bare `%%` comment line
replaced by `%% -` (mermaid does not strip an empty `%%`, so they piled onto
the `flowchart` keyword and failed to parse). Lines 1-2 of all three are
byte-identical before and after, and no claim in this note rests on the
body lines that changed. Re-anchor only.

Also re-read at this anchor, correcting the "not re-opened" caveat in the
entry above: line 1 of `docs/diagrams/architecture.mmd`,
`docs/diagrams/data-flow.mmd` and `docs/diagrams/process.mmd` each reads
`%% anchor: useful-claude-add-ons@1f97e51c`. DERIVED.

The render gate, which earlier entries record as never run for want of
`mmdc`, was run by the commit author for `03b19262` with mmdc 11.17.0
(`render.sh --force`: 3 FAIL before the fix, 12 ok after). That is the
commit message's claim; this note did not re-run it.

## Re-anchor provenance — 03b19262 -> 5d1fc5fd, 2026-09-22

Per-path check, run over the same pathspec the `ea8a014 -> 84976536` section
above enumerates as "30 tracked paths" — that figure is corrected below to 32,
counted directly rather than carried forward:

```
git diff --name-only 03b19262..5d1fc5fd -- .crew/verify.json CHANGELOG.md \
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
```
.crew/verify.json
CHANGELOG.md
CLAUDE.md
TODO.md
plugin/PLUGINS.md
plugin/crew/README.md
plugin/crew/hooks/scripts/_test/run-tests.sh
plugin/crew/skills/crew-diagrams/scripts/_test/render.sh
plugin/crew/skills/crew-diagrams/scripts/render.sh
scripts/_test/self-claims.py
scripts/check-marketplace.py
```

**The pathspec has thirty-two entries, not the thirty a previous pass of this
note claimed** (re-counted directly by listing them into `wc -l` rather than
trusting the earlier figure — this is the same class of self-referential
miscount `INDEX.md` warns about). **Eleven changed, twenty-one did not.** The
twenty-one unchanged: `INSTALLATION.md`,
`README.md`, `docs/diagrams/data-flow-crew-config.mmd`,
`docs/diagrams/process-crew-brief.mmd`, `docs/remaining-setup.md`,
`plugin/README.md`, `plugin/crew/agents/scribe.md`,
`plugin/crew/hooks/scripts/crew_state.py`, `skills/README.md`,
`docs/HANDOFF.md`, `docs/adr/0001-promote-stays-unarmed.md`,
`docs/diagrams/architecture.mmd`, `docs/guides/Running-a-Mailbox-Job.json`,
`docs/runbooks/rollback.md`, `plugin/crew/commands/handoff.md`,
`plugin/crew/hooks/scripts/crew_freshness.py`,
`plugin/crew/skills/crew-context/SKILL.md`,
`plugin/crew/skills/crew-diagrams/SKILL.md`,
`plugin/crew/skills/crew-docs/SKILL.md`,
`plugin/crew/skills/crew-runbooks/SKILL.md`, `scripts/sync-updates.py` — close
citations into them by that result alone.

**Seven of the eleven changed files are covered by `## Corrected at 5d1fc5fd`**
above: `.crew/verify.json`, `CHANGELOG.md`, `TODO.md`,
`plugin/crew/README.md`, `plugin/crew/hooks/scripts/_test/run-tests.sh`, and
both `render.sh` files (two files, counted separately). `CLAUDE.md`'s change is covered where this note cites
`CLAUDE.md:29` (confirmed unaffected — the edit landed in the `render.sh`
regression-test passage, not near the marker-convention text). `plugin/PLUGINS.md`
carries the crew version bump (`0.20.10` -> `0.20.11`) already covered under the
`plugin/README.md:414` bullet's cross-reference. `scripts/_test/self-claims.py`
grew from 344 to 1382 lines and is not cited by line number in this note.
`scripts/check-marketplace.py` grew from 1233 to 1627 lines; its
`check_self_claims` and `count_plugin_skills` citations are corrected above,
and `marketplace-registration.md` owns the rest of that file's function map.

**Not re-executed at this pass**: `render.sh` itself, `python3
scripts/check-marketplace.py`, and every suite under `scripts/_test/` or
`plugin/crew/hooks/scripts/_test/`. Not re-read beyond confirming the
changed-file result and the specific citations corrected above:
`plugin/crew/hooks/scripts/_test/run-tests.sh`'s body, `.crew/verify.json`'s
body beyond the two `why`-field diffs already characterised in
`marketplace-registration.md`, and `CHANGELOG.md`'s history below the new
`### Fixed` entry.

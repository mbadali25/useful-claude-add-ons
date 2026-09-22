# repo-docs
anchor: useful-claude-add-ons@84976536
verified: 2026-09-22
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

1. **The install-URL pin is STALE, and this note's own re-pin command says so.**
   `git log --oneline 0a2d49b069bd178092e75a8cfd1a1c9df6690cd3..HEAD --
   scripts/install-prerequisites.sh scripts/install-prerequisites.ps1` returns
   **four commits** (`91669bf1`, `77279034`, `3cca6482`, `f5ddb7dc`), where at
   the previous anchor it returned nothing. So all three sites carrying that
   SHA — `README.md:12`, `README.md:18` and
   `docs/guides/Running-a-Mailbox-Job.json:18` — are serving a script that no
   longer matches the repo. **Not fixed here**: re-pinning is a change to
   `README.md` and a tracked guide, outside this note's write scope, and
   `CLAUDE.md`'s promotion section already assigns the re-pin to whoever merges
   an install-script change. Recorded as a finding, with the measurement, so it
   is not rediscovered from scratch.
2. **The open `.mmd`-count question from the previous pass is RESOLVED, and the
   answer is "stale", not "scoped to a subset".** The previous pass found six
   `.mmd` files against this note's "three" and explicitly declined to decide
   which reading was right, saying it needed a read of `render.sh`'s actual
   invocation site. That read is done:
   `plugin/crew/skills/crew-diagrams/scripts/render.sh:56` is
   `FILES=("$DIR"/*.mmd)` — a glob over the whole directory, under
   `shopt -s nullglob` at `:55`, with no hardcoded list anywhere in the file.
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
  anchor — re-measured at HEAD, not carried forward.

  **The directory now holds two provenance shapes, and this entry only ever
  described one.** Re-measured by reading line 1 of all six: the three above
  use `%% anchor: <sha>`, while `docs/diagrams/data-flow-crew-config.mmd`,
  `docs/diagrams/process-crew-brief.mmd` and
  `docs/diagrams/process-bitbucket-svg.mmd` use the
  `%% Generated from <repo>@<sha> on <date>.` form instead — at `ea8a0143`,
  `ea8a0143` and `a573ca24` respectively. Both forms are accepted by
  `_DIAGRAM_ANCHOR_RE` (see `INDEX.md`, which owns the contract), so this is
  two supported spellings rather than three broken files. Recorded because the
  previous wording said "all three" of a directory that has held six for two
  anchors, which reads as a complete inventory and is not one.
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
  again, despite the file reaching **7875 lines** (it was "over 5800" at the
  previous anchor). Re-read directly; `:5` is the heading.
- `README.md:12` and `:18` — the bootstrap one-liners, **re-pinned
  `9ea10e21` -> `1b19e5d8` -> `0a2d49b069bd178092e75a8cfd1a1c9df6690cd3`,
  both moves on 2026-09-14** — first because `1b19e5d8` registered the
  `web-research` skill, then because `0a2d49b0` added menu item 25, the
  Perplexity MCP server. Re-pin by running the same check the old pin passed:
  `git log --oneline <pinned-sha>..HEAD -- scripts/install-prerequisites.sh
  scripts/install-prerequisites.ps1`. Empty output means the pin is current;
  any commit listed means both URLs are serving a script that no longer
  matches the repo, and the pin must move. That command now returns nothing
  at `0a2d49b0`.
  **Two pin moves in one day is the rate to expect, not an anomaly.** Any
  change registering a marketplace entry edits both install scripts, because
  registration means touching both in the same commit. So the pin goes stale
  on essentially every entry that ships. Treat the re-pin as part of merging
  such a change rather than as periodic maintenance, and do not read a recent
  move as evidence the pin is fresh.
  **A third site carries the same SHA and the runbook does not mention it.**
  `docs/guides/Running-a-Mailbox-Job.json:18` embeds the PowerShell one-liner
  inside a JSON step string, so `docs/runbooks/rollback.md:55` — which says to
  replace the SHA in "BOTH raw.githubusercontent.com URLs in README.md" — is
  an undercount, and following it literally leaves that guide installing an
  older script with no error anywhere. It was re-pinned here too. Re-measure
  with `grep -rn <old-sha> --include='*.md' --include='*.json' .` rather than
  trusting this list; `.claude/worktrees/` copies are agent worktrees and are
  not tracked sites.
  Both re-pinned URLs were fetched at this pass: each returns HTTP 200 and the
  served bodies contain the `web-research` entry (2 occurrences in the `.sh`,
  1 in the `.ps1`), so the pin is known good rather than merely plausible.
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
  `:20`, `mmdc` invoked at `:45` and again at `:49` on the failure path (file
  unchanged in this range, closed by the per-path check; all three line numbers
  re-read and identical). `docs/diagrams/out/` itself is gitignored at
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
  `plugin/crew/skills/crew-diagrams/scripts/render.sh:55-56`:
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
  (`scripts/check-marketplace.py:579-722`, moved from `:430`, and from `:412`
  before that — re-taken by parsing the function definitions out of the file
  with `ast` rather than by offsetting, because `check-marketplace.py` gained
  four whole checks in this range and the insertions are not evenly spaced)
  verifies marked numbers against `marketplace.json`, and this repo's own
  `CLAUDE.md` documents the convention (`CLAUDE.md:29`; that file is unchanged
  in this range). `plugin/README.md:414`'s agent count is also no
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
  (`scripts/check-marketplace.py:562-576`, moved from `:413-427`). The line
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
  `plugin/crew/skills/crew-diagrams/scripts/render.sh:45` (`-s 2`, silenced)
  and `:49` (the retry that prints the last five lines of stderr on FAIL).
  File unchanged in this range; both line numbers re-read and confirmed
  identical to the previous anchor.
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
- `CHANGELOG.md:5402` (moved from `:3429-3430`, and from `:2057-2058` before
  that; re-located by grepping the string, not by offset) — "It also stops
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
  `plugin/crew/skills/crew-diagrams/scripts/render.sh:32-35` sets `PCFG_ARG`
  from `cygpath -w "$PCFG"` when `cygpath` exists, re-read this pass and
  unchanged from the previous anchor.
  `plugin/crew/skills/crew-diagrams/scripts/render.sh:27-31` still names the
  real trigger: `MSYS_NO_PATHCONV=1` set in the caller's environment, not a
  Mermaid problem.

- **The regression test for that fix is no longer misdocumented — this
  landmine is resolved, not carried forward.** Four previous versions of this
  note recorded that `CLAUDE.md` cited the wrong path for the `render.sh`
  regression test (`scripts/_test/render.sh`, which does not exist, instead
  of `plugin/crew/skills/crew-diagrams/scripts/_test/render.sh`, which does).
  At this anchor, `CLAUDE.md:280-281` correctly names
  `plugin/crew/skills/crew-diagrams/scripts/_test/render.sh` and its
  `MSYS_NO_PATHCONV=1` case at `:74` — verified directly: the file is 79
  lines, case 2 (`MSYS_NO_PATHCONV=1`) runs at line 74, and it asserts a
  non-zero output file rather than exit 0, exactly as `CLAUDE.md` now says.
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
  now much larger history (**7875 lines**) was not read back. The rule
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

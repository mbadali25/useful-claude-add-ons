# repo-docs
anchor: useful-claude-add-ons@d61342c3
verified: 2026-09-06

## Does
Holds the repo's hand-written documentation - the Mermaid diagram sources under `docs/diagrams/`,
planning artifacts under `docs/superpowers/`, one operational runbook, handoff notes, and the
top-level `CHANGELOG.md`. Nothing under `docs/` is generated except the rendered diagram images in
`docs/diagrams/out/`. (JUDGEMENT: the "prose is never auto-refreshed" rule is not written down
anywhere as a rule; it is inferred from there being no writer. The one script that names
`CHANGELOG.md`, `scripts/sync-updates.py:20` and `:73`, only discusses relative links inside
mirrored README sections and does not write it - DERIVED.)

## Entry points

- DERIVED `docs/diagrams/architecture.mmd:1-2` - and `data-flow.mmd:1-2`, `process.mmd:1-2`
  alongside it. Line 1 is `%% anchor: useful-claude-add-ons@<sha>`, line 2 is `%% Anchors: <paths>`.
  All three currently read `1f97e51c`, i.e. HEAD - they are not behind at this anchor.
- DERIVED `docs/HANDOFF.md:1-5` - rolling handoff notes, newest first. Maintained by hand; see the
  landmine below, it is **not** what `/crew:handoff` writes.
- DERIVED `docs/remaining-setup.md:1-6` - the ordered manual checklist for the four workstreams
  needing credentials, consent, or a decision no script can make.
- DERIVED `docs/runbooks/rollback.md:9-14` - the "When to use this" list: `check-marketplace.py`
  fails on `main`, a plugin ships with a broken `version`, or an install-script change breaks a
  fresh machine. Carries `last verified: 2026-09-05` at `:3`.
- DERIVED `CHANGELOG.md:5` - the `## [Unreleased]` heading, exactly at line 5.
- `README.md:12` and `:18` — the bootstrap one-liners, pinned to a commit SHA. They must be re-pinned after any change to either install script, or the documented command installs the previous script.
- `TODO.md` — 8 Codex findings inside `pa.py` and `jira-api.sh`, each with its repro, plus the recorded decision NOT to rewrite the published tenant snapshot.

## Owns data

- DERIVED `docs/diagrams/out/*.svg` and `*.png` (six files, three names x two formats), produced by
  `plugin/crew/skills/crew-diagrams/scripts/render.sh` - output dir created at `:20`, `mmdc`
  invoked at `:45` and again at `:49` on the failure path. **`out/` is gitignored**
  (`.gitignore:357`); `git ls-files docs/diagrams/` returns only the three `.mmd` sources. Never
  hand-edit anything under `out/` - it is regenerated wholesale.
- DERIVED `docs/superpowers/` is hand-written: `plans/` (2 files) and `specs/` (5 files). Nothing
  in the repo reads either directory back at runtime - a repo-wide grep for `docs/superpowers`
  outside `docs/` itself and this codemap returns nothing.
- Counts that drift silently and are checked by nothing: `28 skills` (README, INSTALLATION), `50 agents` (plugin/README.md), community `7 of 4 marketplaces`, `Seven MCP servers` (INSTALLATION.md).

## Calls out to

- DERIVED `mmdc` (mermaid-cli), at `plugin/crew/skills/crew-diagrams/scripts/render.sh:45`
  (`-s 2`, silenced) and `:49` (the retry that prints the last five lines of stderr on FAIL).
- `raw.githubusercontent.com` at the pinned sha. Verified after the merge rather than assumed: the `.ps1` returns 200 and the `.sh` at that sha contains the new menu keys.

## Landmines
- **`docs/adr/` does not exist, and three documents about *this* repo say otherwise.** DERIVED:
  the directory is absent from the working tree, is not in `.gitignore`, and
  `git log --all --diff-filter=A -- 'docs/adr/*'` is empty - no ADR has ever been committed. The
  three claims are `CLAUDE.md:78` ("Decisions in `docs/adr/`"), `CHANGELOG.md:1423` ("It also stops
  claiming `docs/adr/`, which is now `scribe`'s"), and `.crew/STATUS.md:39`, which records
  `docs/adr/` as **scaffolded**. That last one is the trap: it reads as a completed step.
  (A prior version of this note cited `CHANGELOG.md:1195-1196` for the scribe/ADR assignment. That
  range is about `obsidian-vault` doctor vault-collision labelling and has nothing to do with ADRs;
  the scribe passage is at `CHANGELOG.md:1396-1397`. Corrected 2026-09-06 by reading both ranges.)
  JUDGEMENT: the many other `docs/adr/` references under `plugin/crew/` - `agents/scribe.md:38`,
  `skills/crew-docs/SKILL.md:30`, `README.md:1501`, and others - are the crew plugin instructing
  *any* repo it is installed into, not claims about this one. Do not count them.

- **`/crew:handoff` does not write `docs/HANDOFF.md`.** DERIVED
  `plugin/crew/commands/handoff.md:7` - "Write `.work/HANDOFF.md` following the `crew-context`
  skill" - and `.crew/config.json:5`, `"handoffPath": ".work/HANDOFF.md"`.
  `plugin/crew/skills/crew-context/SKILL.md:62` says the same. `docs/HANDOFF.md` is human-authored
  and reached from `README.md:629`; the two files are unrelated despite the shared basename.
  DERIVED: its newest entry is `docs/HANDOFF.md:9`, dated 2026-08-23 - fourteen days behind this
  anchor. The newest-first ordering it claims at `:3-4` does hold across all four entries
  (`:9`, `:108`, `:141`, `:305`).
  (A prior version said `/crew:handoff` writes this file. False, and false in the direction that
  makes a stale document look maintained. Corrected 2026-09-06.)

- **The machine-read diagram header is line 1, not `%% Anchors:`.** DERIVED: staleness is decided
  by `_DIAGRAM_ANCHOR_RE` at `plugin/crew/hooks/scripts/crew_state.py:293-297`, which matches
  `%% Generated from <repo>@<sha>` or `%% anchor: <sha>`, and is applied at `:464-468` where
  `found.group(1)[:7] != head[:7]` marks a diagram behind. `%% Anchors:` - the source-path list -
  is read by **no code in this repo**: grep finds it only at
  `plugin/crew/skills/crew-diagrams/SKILL.md:31` (the documented example) and
  `plugin/crew/hooks/scripts/_test/run-tests.sh:865` (a fixture). So the two headers do different
  jobs: line 1 makes a diagram *machine*-checkable, line 2 makes it *hand*-re-verifiable via
  `git diff --name-only <anchor>..HEAD -- <the listed paths>`. Losing line 2 costs the hand
  re-check and nothing else; the PM will still report the diagram as current.
  DERIVED `plugin/crew/skills/crew-diagrams/SKILL.md:37-43`: a source with no parseable provenance
  counts as *behind*, deliberately - unknown resolves to stale.
  (A prior version said `%% Anchors:` was "the only thing making a diagram falsifiable" and that
  both headers are "read by the `crew-diagrams` skill". Both wrong: wrong header, wrong reader.
  Corrected 2026-09-06 by reading the regex and its call site.)

- **`TODO.md`'s `render.sh` entry is at `:687-716`, and it is stale in one specific way.** DERIVED:
  the section heading is `TODO.md:687`, "`render.sh` cannot render a diagram on Windows - it hands
  `mmdc` a `/tmp` path". Its symptom report is accurate history - six failures for six on
  2026-09-05 (`TODO.md:697-698`), and its own proposed fix at `TODO.md:708` is "resolve the temp
  path through `cygpath -w`". That fix has since landed:
  `plugin/crew/skills/crew-diagrams/scripts/render.sh:32-35` sets `PCFG_ARG` from
  `cygpath -w "$PCFG"` when `cygpath` exists. What is stale is only that the heading is not marked
  CLOSED, unlike its neighbours at `TODO.md:487`, `:603` and `:719` which carry
  "- CLOSED 2026-09-06".
  DERIVED `render.sh:27-31` names the real trigger: a caller with `MSYS_NO_PATHCONV=1` set, which
  turns off MSYS's own argument rewrite. Without that variable the same command renders. The
  Mermaid sources were never the problem.
  (A prior version cited this as `TODO.md:361-391` - off by roughly 320 lines, and landing inside
  an unrelated section. `TODO.md` is edited often; re-resolve any line citation into it rather
  than trusting one. Corrected 2026-09-06.)

- **The regression test for that fix is not where `CLAUDE.md` says it is.** DERIVED
  `CLAUDE.md:201` states the check "lives in `scripts/_test/render.sh`". That file does not exist -
  `scripts/_test/` holds `drift-detection.sh` and `menu-groups.sh` and nothing else. The real path
  is `plugin/crew/skills/crew-diagrams/scripts/_test/render.sh` (79 lines), whose header at
  `:2-14` states the `MSYS_NO_PATHCONV=1` trigger and whose case 2 at `:72-74` runs
  `env MSYS_NO_PATHCONV=1` and asserts a **non-zero output file**, not exit 0 - because the broken
  script still created `out/` and printed a summary line. Not fixed here: this note may only edit
  itself.

- **`docs/runbooks/INDEX.md` does not exist.** DERIVED: `docs/runbooks/` contains `rollback.md`
  alone, while `plugin/crew/commands/runbook.md:22` ("Add the symptom row to
  `docs/runbooks/INDEX.md`"), `plugin/crew/skills/crew-runbooks/SKILL.md:80` and
  `plugin/crew/README.md:1549` all describe it as the symptom-keyed index.
  JUDGEMENT: with one runbook this costs nothing; it becomes a real gap at the second.

- **A count written into a file under `docs/` changes that count.** JUDGEMENT. Recording "N
  diagrams" or "N ADRs" *there* is self-referential. State the invariant and how to re-measure -
  `ls docs/diagrams/*.mmd` and read line 1 of each - rather than a total that looks measured and is
  wrong by one. This note is under `.crew/codemap/`, so its own counts are not self-referential;
  they are still only true at this anchor.

## Unverified
- Whether `render.sh` succeeds end to end on this machine. Not run - the harness for this refresh
  was told not to, and CLAUDE.md records that its failure output is misleading here. The committed
  regression test above is the evidence that the `cygpath` path is covered; that the test *passes*
  on this machine is **unknown**, it was read and not executed.
- Whether `CHANGELOG.md` entries are strictly one per plugin-version bump throughout. Only the
  opening `[Unreleased]` entries were read (`CHANGELOG.md:5-10`), and the rule actually written
  down is different: `plugin/crew/skills/crew-docs/SKILL.md:26` gates an entry on "Behaviour users
  or callers can observe changed", not on a version bump. The 3896-line history was not read back.
- The contents of `docs/superpowers/plans/` and `specs/` beyond their filenames.
- Why `.crew/STATUS.md:39` records `docs/adr/` as scaffolded when it has never been committed.
  Most likely git not tracking an empty directory, but that is a guess and was not confirmed.

## Re-anchor provenance
Re-read on 2026-09-06 at HEAD `1f97e51c`, moving the anchor from `a02331ee`. Every `path:line`
below was resolved by reading the line, not by grep alone.

- Read in full or in the cited range: `docs/HANDOFF.md` (`:1-12`, all `^## ` headings, 443 lines
  total), `docs/remaining-setup.md:1-12`, `docs/runbooks/rollback.md:1-22`, `CHANGELOG.md:1-10`,
  `:1190-1200`, `:1392-1428`, `TODO.md:687-720` plus all `^## ` headings,
  `plugin/crew/skills/crew-diagrams/scripts/render.sh` (63 lines, `:1-60` read),
  `plugin/crew/skills/crew-diagrams/scripts/_test/render.sh` (79 lines, header and case list),
  `plugin/crew/hooks/scripts/crew_state.py:281-300` and `:455-478`,
  `plugin/crew/skills/crew-diagrams/SKILL.md:20-45`,
  `plugin/crew/hooks/scripts/_test/run-tests.sh:858-875`, `.crew/STATUS.md:36-42`, `CLAUDE.md:78`
  and `:201`, `.crew/config.json:5`, `.gitignore:357`.
- Commands run: `ls` over `docs/`, `docs/diagrams/`, `docs/diagrams/out/`, `docs/runbooks/`,
  `docs/superpowers/{plans,specs}/`, `scripts/_test/`; `git ls-files docs/diagrams/`;
  `git log --all --diff-filter=A -- 'docs/adr/*'` (empty); `git log --all --name-only -- docs/adr`
  (empty); repo-wide greps for `docs/adr`, `cygpath`, `Anchors:`, `CHANGELOG` under
  `plugin/crew/hooks/` and `scripts/`.
- Not run: `render.sh`, per instruction. Not edited: `TODO.md`, `CLAUDE.md`, and everything else -
  only this file changed.
- Five claims were corrected as false (`CHANGELOG.md:1195-1196`, the `/crew:handoff` writer, the
  `%% Anchors:` falsifiability claim and its reader, the `TODO.md:361-391` range, and the
  now-obsolete "run render.sh to verify" instruction); two were added (`CLAUDE.md`'s wrong test
  path, the missing `docs/runbooks/INDEX.md`); one undercount was fixed (two documents citing
  `docs/adr/`, actually three). The `docs/adr/` absence, the three anchored diagrams, `CHANGELOG.md:5`,
  the `cygpath` fix and the `mmdc` call site were confirmed.
- Two citations were right about the file and wrong about the line, and were shifted rather than
  dropped: the `cygpath` block is `plugin/crew/skills/crew-diagrams/scripts/render.sh:32-35`, not
  `:33-36`; and `docs/diagrams/out/` is produced at `plugin/crew/skills/crew-diagrams/scripts/render.sh:20`
  and `:45`, not at `:1`, which is the shebang. Written repo-relative because TWO files are
  named `render.sh` — this one and `plugin/crew/skills/crew-diagrams/scripts/_test/render.sh` —
  so the bare form is ambiguous as well as unpasteable into `git diff -- <path>`.

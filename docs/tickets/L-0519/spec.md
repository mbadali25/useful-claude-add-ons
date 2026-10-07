# L-0519: reconcile crew-standards with crew-qa-standards: one source per kind of rule, RF derived from the standards          status: spec   risk: low
T-0085 follow-up (owner 2026-09-30, "follow-up for crew-qa-standards overlap"). Written against origin/main
`a555ff37` (crew 1.1.0). Re-find every line by content at implement time.

## Intent
State and enforce which skill owns which rule. `crew-standards` (GEN, stack sets, the `.crew/standards.md` overlay)
is the one source for code-level rules: what a change's code must do, answered in the self-check. `crew-qa-standards`
owns the repository's machinery: harness (H1-H11), review process (R1-R12), gate rules and environments (G1-G5,
E1-E7). Its `recurring-findings.md` (RF-01..07) is a derived, path-keyed probe index over the standards: every RF
section's `seen:` line names at least one standard id, every id it names exists, and where an RF probe and its
standard disagree the standard wins and the probe is corrected. A new test enforces the ids. RF-07, the one section
that cites no standard, is re-pointed at GEN-09 and this repository's REPO-03. The three process rules that restate
a code standard (R10, H8, R12) each name it. Both SKILL.md files, the README's "Development standards" section and
`plugin/PLUGINS.md` (which has no `crew-qa-standards` row today) describe the split. Nothing the implementer or
reviewer sees changes order or shape: the review prompt keeps both blocks, the self-check keeps its rows.

## Exclusions
- No harness path: no edit to `review_prompt.py`, `review_run.py`, `commands/review.md` or `plugin/crew/tests/sabotage*.py`
  (`scripts/check-tooling-pr.py` `HARNESS`). The review prompt keeps `checklist_block` then `review_block`
  (`review_prompt.py:377-378`). Dropping the second block is direction Option 2, deferred.
- No change to `crew_standards.py` (loader, gate, stamp, checklist) or to any standard's Rule, Self-check, Earned by or
  Change sets in `generic.md`, `python.md` or `.crew/standards.md`.
- No change to `recurring_findings.py`'s parser, matcher, cap (`MAX_LINES = 60`) or headers, and no RF section added,
  removed, renamed or re-ranked (`test_shipped_checklist_pins_the_seven_classes`,
  `test_shipped_sections_are_ranked_by_their_count`). Only `seen:` text and, where a probe contradicts its standard,
  that probe's wording.
- No change to `qa_audit.py`, `qa_audit_env.py`, `qa_doc.py` or what the audit reports; no H/R/G/E rule text moves.
- No move of marketplace-specific RF sections into a per-repository file (a recurring_findings feature; follow-up).
- No hook, no config key: `plugin/crew/CONFIG.md` unchanged. No version bump on the build branch (REPO-03).

## Evidence
origin/main `a555ff37`:
- crew-standards: `plugin/crew/skills/crew-standards/SKILL.md:13-33` (sets and format), `:53-79` (self-check),
  `:95-98` (checklist in the review prompt, answers withheld). Ids: `references/generic.md` GEN-01 `:18` ... GEN-12
  `:604`; `references/python.md` PYTHON-01/03/04/06/07/08/10/11/13; `.crew/standards.md` REPO-01 `:15`, REPO-02
  `:45`, REPO-03 `:73`. Id grammar `crew_standards.py:83` `^[A-Z]{2,6}-\d{2}$`; `crew_standards.effective_set`
  and `parse_set` expose every shipped id.
- crew-qa-standards: `plugin/crew/skills/crew-qa-standards/SKILL.md:8-21` lists harness.md, review.md,
  environments.md, steward-template.md, recurring-findings.md; never mentions crew-standards. `references/harness.md`
  H8 `:100`, H10 `:129`; `references/review.md` R10 `:75`, R12 `:89`.
- RF data: `plugin/crew/skills/crew-qa-standards/references/recurring-findings.md` `seen:` lines `:17` (GEN-02,
  PYTHON-07), `:24` (GEN-09), `:31` (GEN-04, GEN-12), `:39` (GEN-01, GEN-05, PYTHON-10, PYTHON-11), `:47` (GEN-08),
  `:54` (GEN-05, GEN-06), `:60` (`CLAUDE.md "Stop and ask"`, no id); provenance `:64-72` ("Classes are keyword
  matches ... the probes are JUDGEMENT").
- RF printers: `plugin/crew/hooks/scripts/recurring_findings.py:5` (`DATA_REL`, `:62`), `parse` `:119` (keeps `seen`
  as one string), `REVIEW_HEADER` `:345-350`, `review_block` `:353`; `/crew:implement` step 2
  (`plugin/crew/commands/implement.md:39-42`); the printed line shows `seen:` with its ids (run
  `python3 plugin/crew/hooks/scripts/recurring_findings.py --root . --paths plugin/crew/hooks/scripts/x.py`).
- Suites: `plugin/crew/tests/test_recurring_findings.py:55` (shipped data parses and fits), `:79` (seven classes
  pinned), `:256` (ranked by count). `.crew/verify.json:600-610` maps the RF files to
  `test_recurring_findings.py` and `test_review_prompt.py`; `:475` maps `crew-qa-standards/**` to `test_qa_audit.py`
  et al.; `:483-484` maps `crew-standards/**` to the standards rule.
- Docs that describe one or both: `plugin/crew/README.md:732` (recurring-findings checklist), `:793-795`
  ("Development standards and the pre-review self-check"); `plugin/PLUGINS.md:217` (crew-standards row; no
  crew-qa-standards row anywhere); `docs/guides/crew/src/daily-workflow.md:60`, `:69-78`;
  `docs/guides/crew/src/working-with-codex.md:70-90`; `.crew/codemap/crew.md:1824-1831`, `:1876-1877`.

## Unknowns
- **A probe that contradicts its standard.** None found at brainstorm (RF probes read as concrete instances of the
  GEN self-checks they cite). The implementer reads each of the 21 probes against the cited standards' Self-check
  and records "agrees" or the edit in the PR body. Default: no probe edit.
- **Overlay ids in a plugin-shipped file.** RF-07 cites `REPO-03`, which exists only in this repository's overlay.
  Default: the new test accepts an id from the shipped plugin sets or from this repository's `.crew/standards.md`,
  and RF-07's `seen:` says "this repository's REPO-03". Its marketplace-only scope stays a known limit (follow-up).
- **Ids from later stack sets** (L-0532..L-0538, e.g. `NG-07`): the test reads the sets as shipped, so a probe may
  cite one once it lands. No coordination needed.
- Next free crew patch version set at land.

## Size and split
0 production lines. About 10 lines changed in `recurring-findings.md` (`seen:` text), about 25 lines across the two
SKILL.md files and three reference lines in `harness.md`/`review.md`, one new test (~25 lines), doc rows. No harness
path. No further split.

## Touch
- `plugin/crew/skills/crew-qa-standards/references/recurring-findings.md` - intro states RF is derived and the standard wins; RF-07 `seen:`
- `plugin/crew/skills/crew-qa-standards/references/harness.md` - H8: "Code-level standard: GEN-01"
- `plugin/crew/skills/crew-qa-standards/references/review.md` - R10: GEN-04; R12: GEN-12
- `plugin/crew/skills/crew-qa-standards/SKILL.md` - scope paragraph and pointer to crew-standards
- `plugin/crew/skills/crew-standards/SKILL.md` - scope paragraph and pointer to crew-qa-standards / RF
- `plugin/crew/tests/test_recurring_findings.py` - the id cross-reference test
- `plugin/crew/README.md` - "Development standards" section: one paragraph on the split
- `plugin/PLUGINS.md` - add the missing `crew-qa-standards` row; adjust the `crew-standards` row; version line at land
- `docs/guides/crew/src/working-with-codex.md` - the recurring-findings paragraph says each class names its standard
- `docs/guides/crew/**` - HTML, DOCX and PDF rebuilt by `docs/guides/crew/src/build.py`
- `.crew/codemap/crew.md` (the two checklist blocks) and `.crew/codemap/**` re-anchor
- `CHANGELOG.md`
- `plugin/crew/BUDGETS.md`
- `plugin/crew/.claude-plugin/plugin.json` - version, at land only
- `.claude-plugin/marketplace.json` - version, at land only
- `.claude/rules/**` regenerate only; `graphify-out/**` `graphify update .` only
- `docs/tickets/L-0519/` (removed in the final PR)

Not in Touch: `review_prompt.py`, `review_run.py`, `commands/review.md`, `sabotage*.py` (HARNESS);
`recurring_findings.py`, `crew_standards.py`, `qa_audit*.py`, `qa_doc.py` (no code change);
`plugin/crew/commands/implement.md` (step 2 and the self-check text stay true); `.crew/verify.json` (the new test is in
an already-mapped file); `docs/guides/crew/src/daily-workflow.md` (`:60` and `:69-78` stay true; say so in the PR);
`docs/diagrams/**` (no box or edge changes); `plugin/crew/CONFIG.md` (no key).

## Acceptance checks
Commands from the repo root. `R` is `plugin/crew/tests/test_recurring_findings.py`.
- [ ] New `test_every_class_names_a_standard_that_exists`: for each shipped RF section, the ids in its `seen:` line
  (regex `\b[A-Z]{2,6}-\d{2}\b`) are non-empty and each is a standard id in `crew-standards/references/*.md` or in this
  repository's `.crew/standards.md`, read through `crew_standards.parse_set`. Fails today on RF-07 (no id), passes after.
  `python3 plugin/crew/tests/pytest_rule.py R -q -k test_every_class_names_a_standard_that_exists`
- [ ] The same test goes red when a cited id is renamed to one that does not exist (checked by hand: change `GEN-09` to
  `GEN-99` on RF-02's `seen:` line, run, see it fail naming RF-02 and GEN-99, restore with `git checkout --`).
  Recorded in the PR body (the sabotage entry is a follow-up tooling ticket, HARNESS).
- [ ] Existing RF and prompt suites pass, with the seven classes, their order and the 60-line cap unchanged:
  `python3 plugin/crew/tests/pytest_rule.py R plugin/crew/tests/test_review_prompt.py -q`
- [ ] crew-standards and QA-audit suites pass unchanged:
  `python3 plugin/crew/tests/pytest_rule.py plugin/crew/tests/test_crew_standards.py plugin/crew/tests/test_qa_audit.py plugin/crew/tests/test_qa_audit_env.py plugin/crew/tests/test_qa_doc.py -q`
- [ ] The two SKILL.md files each name the other and state the split in the same words (code-level rules and the
  self-check: crew-standards; harness, review-process, gate and environment rules: crew-qa-standards; RF derived, the
  standard wins): `grep -n "crew-qa-standards" plugin/crew/skills/crew-standards/SKILL.md` and
  `grep -n "crew-standards" plugin/crew/skills/crew-qa-standards/SKILL.md` each print at least one line.
- [ ] `grep -n "GEN-04" plugin/crew/skills/crew-qa-standards/references/review.md`,
  `grep -n "GEN-01" plugin/crew/skills/crew-qa-standards/references/harness.md` print the new reference lines.
- [ ] `grep -n "crew-qa-standards" plugin/PLUGINS.md` prints the new row.
- [ ] `python3 scripts/check-tooling-pr.py` prints `tooling-pr: OK`.
- [ ] Docs: README, PLUGINS.md, the codex guide and `.crew/codemap/crew.md` describe the split; guides rebuilt
  (`python3 docs/guides/crew/src/build.py`); CHANGELOG entry; BUDGETS.md re-measured; crew bumped at land;
  `python3 scripts/check-marketplace.py` passes after the commit.

## Dependencies
- T-0085 (#269), T-0086 (#282), L-0575/L-0592/L-0601 (RF data and both printers): merged.
- L-0518 (T-0085 round-4 follow-up) edits `crew-standards/SKILL.md:99-104` (the proposals paragraph). Different
  lines; whichever lands second merges main.
- L-0532..L-0538 (stack slices) edit `crew-standards/SKILL.md:18-22` and the README paragraph. Same merge-train rule.
- Follow-ups (not minted here): a sabotage entry for the new test (tooling-only); moving marketplace-specific RF
  sections to a per-repository data file; direction Option 2 if the owner wants one review block.

## Approval
Direction and spec approved for cloud hand-off by the orchestrator under the owner's standing self-approve
authority, 2026-10-05. Plan: to be written by the implementing session.

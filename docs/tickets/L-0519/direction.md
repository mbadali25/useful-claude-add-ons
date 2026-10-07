# L-0519 direction - reconcile crew-standards with crew-qa-standards

Status: approved 2026-10-05 for cloud hand-off (was: seed).

Owner decision 2026-09-30 (T-0085 land decisions: "follow-up for crew-qa-standards overlap"). T-0085 (#269, df3cdf17) added the crew-standards skill (GEN-01..GEN-12 build-time standards, .crew/standards.md overlay, pre-review self-check); main had meanwhile added crew-qa-standards (#263-#267). crew now bundles 31 skills with both. Decide one source of truth: where the two overlap or disagree, which rule wins, whether one references the other, and how the review prompt checklist and the self-check use them. Output: a direction with options (recommended first), then spec.

## Ask
crew ships two skills that both state "what review keeps finding" and both feed the implementer and the reviewer,
and neither names the other. Decide one source of truth for each kind of rule, which wins on a conflict, how they
reference each other, and what the review prompt and the self-check take from each.

Facts found at brainstorm (origin/main `a555ff37`, 2026-10-05):
- `crew-standards` (T-0085, #269; Python set T-0086, #282): GEN-01..12 (`references/generic.md`), stack sets
  (`references/python.md`), the repo overlay `.crew/standards.md` (REPO-01..03, Supplements). Applied at
  `/crew:plan` (Standards: line), `/crew:implement` (required self-check, stamped), `/crew:review` (gate, checklist
  block, proposals). Earned by 224 classified findings, three-change-set bar.
- `crew-qa-standards` (#263-#267, L-0618): H1-H11 (`harness.md`), R1-R12 (`review.md`), G1-G5/E1-E7
  (`environments.md`), audited by `qa_audit.py`; and since L-0575 (2026-10-01) `references/recurring-findings.md`,
  RF-01..07, path-keyed, printed by `hooks/scripts/recurring_findings.py` at `/crew:implement` step 2 and as a second
  checklist block in the review prompt (`review_prompt.py:377-378`, `crew_standards.checklist_block` then
  `recurring_findings.review_block`). RF counts are keyword matches over 539 findings, "approximate", probes JUDGEMENT.
- The overlap is RF against GEN: each RF section's `seen:` line already names the GEN/PYTHON ids it echoes (RF-01
  GEN-02/PYTHON-07, RF-02 GEN-09, RF-03 GEN-04/GEN-12, RF-04 GEN-01/GEN-05/PYTHON-10/PYTHON-11, RF-05 GEN-08,
  RF-06 GEN-05/GEN-06), except RF-07, which cites `CLAUDE.md "Stop and ask"` and restates this repository's REPO-03.
  Nothing checks that those ids exist or that RF probes agree with the standards they name.
- Smaller overlaps: R10 (must-block/must-allow/sabotage) is GEN-04's process form; H8 (missing tool exits 77) is a
  case of GEN-01; R12/H10 sit beside GEN-12. Neither skill's SKILL.md, nor `plugin/crew/README.md` "Development
  standards", mentions the other. `plugin/PLUGINS.md` has a `crew-standards` row (`:217`) and **no
  `crew-qa-standards` row**.
- RF data is marketplace-specific (RF-07's globs `plugin/**`, `**/marketplace.json`; its intro says "this
  marketplace's crew changes") but ships in the plugin, while crew-standards keeps repo-specific rules in the overlay.

## Options
1. **Split by kind; crew-standards is the source for code-level rules; RF is a derived probe index that must
   name standards that exist (recommended).** crew-standards owns every rule about what a change's code must do,
   with the self-check. crew-qa-standards owns harness, review-process and environment rules (H/R/G/E), which are
   about the repo's machinery, not a change's code. RF stays as it is mechanically (path-keyed probes, both
   printers, no harness change) but is declared derived: every section's `seen:` names at least one standard id,
   each id must exist in the shipped sets, and where a probe and its standard disagree the standard wins and the
   probe is edited. A test enforces the ids. Both SKILL.md files, the README and PLUGINS.md say this. Cost: two lists
   still reach the reviewer, and a probe can still say more than its standard (allowed: probes are concrete checks).
2. **Fold RF into crew-standards and drop the second block.** Move the probes into the standards' self-checks
   (or a non-gated `probes` file under crew-standards), point `/crew:implement` step 2 at `crew_standards.py sets`,
   remove `recurring_findings.review_block` from the prompt, retire `recurring_findings.py` (412 lines) and its suite.
   One list. Cost: `review_prompt.py` is HARNESS (a separate tooling-only PR), GEN has no path globs so RF's
   path scoping is lost or must be added to the loader, and the RF counts (539 findings) are newer than GEN's (224).
3. **Document only.** A paragraph in each SKILL.md stating scope and precedence. Cheapest. Cost: nothing stops the
   two drifting (a renumbered GEN id, a probe that contradicts its standard), which is the defect class GEN-09 names.

## Recommendation
Option 1. One source per kind of rule, a mechanical cross-reference check, no change to the review prompt's
blocks, the self-check or any harness path.

## Open questions (default taken)
- Which wins on a conflict: the crew-standards standard (it carries the self-check and the change-set bar); the RF
  probe is corrected in the same PR that finds the conflict. Default taken.
- RF-07 (version and registration): it cites `REPO-03` (this repository's overlay) and GEN-09, and its
  marketplace-only scope is recorded as a known limit; moving marketplace-specific RF sections into a repo-level
  data file is a follow-up, not this ticket. Default taken.
- Whether the review prompt keeps both blocks: yes. Removing one is a harness change (`review_prompt.py`) and is
  Option 2's, deferred. Default taken.
- Overlapping H/R rules (R10, H8, R12/H10): each gets one "Code-level standard: GEN-nn (crew-standards)" line;
  no rule text moves. Default taken.
- The missing `crew-qa-standards` row in `plugin/PLUGINS.md` is added here, since this ticket changes how the skill
  is described. Default taken.

## Approval
Direction approved 2026-10-05 for cloud hand-off, by the orchestrator under the owner's standing self-approve
authority (2026-09-26, reaffirmed 2026-09-27 and 2026-10-05).

# L-0536 plan: Terraform standards, T-0086 slice (as built)

Written by the implementing session, 2026-10-05, on `rush/g7-standards` (release/1.2.0 lane).

## Outcome

As the spec expected, no gated set ships. The spec's re-count put no rule above two
reviewed change sets. The PR review threads that might lift TERRAFORM-11 or -12 are in
private repositories, which this session could not reach, so those counts stay as the
spec gives them: an unknown is not counted. A cloud research pass found public
change sets for TERRAFORM-03 (4) and TERRAFORM-P1 (2). The owner decided on 2026-10-05
that public change sets do not count, so both are candidates. The set id, when a rule
is earned, is `TF` (owner, 2026-10-05). The spec's `TERRAFORM` is nine letters, and the
loader refuses any name outside 2-6 capitals.

## Steps

1. Machine-local evidence files: `.work/tickets/L-0536/changesets-terraform.txt` (a copy
   of the research) and `quote-check-terraform.txt` (4 of 4 HashiCorp sentences found in
   the raw pages, plus the `for_each`-in-`import` line under "1.7.0" in the raw
   `v1.7/CHANGELOG.md`).
2. Write `stack-terraform/references/candidates.md` with TERRAFORM-03, TERRAFORM-P1,
   TERRAFORM-12 and the three settled questions. The spec's per-rule counts for -01..-19
   are given in one line. The rule text for the rest was not available, so they are not
   written as candidates. The spec's check that all 19 ids appear therefore does not
   pass. That is a reported deviation, with no placeholders added.
3. `stack-terraform/SKILL.md`: add `## Standards` (no gated set, the set id `TF`, and a
   link to the candidates) and a pointer from the secrets pitfall.
4. Docs: `plugin/crew/README.md`, the `plugin/PLUGINS.md` row, CHANGELOG, and a
   re-measured BUDGETS.md.
5. Tests: `test_stack_skills.py`, `test_crew_standards.py`, `test_lifecycle_commands.py`.
   Checks: check-tooling-pr, check-marketplace.

Standards: none - Markdown only.

# L-0538 plan: Angular 2+ standards, T-0086 slice (as built)

Written by the implementing session, 2026-10-05, on `rush/g7-standards` (release/1.2.0 lane).

## Outcome

No `references/angular.md` ships. The spec's one admitted rule, NG-07, rests on the
coordinator's private count. Its Why, Earned by and Change sets text had to be supplied
by the coordinator in a publishable form, and was not. The spec names this as blocking
for a cloud session. A cloud research pass found public change sets: NG-07's read half
has 3 and its write half 1, NG-P1 (no `bypassSecurityTrust*` on authored content) has 5,
and NG-P2 (interceptor credentials to allow-listed origins) has 1. The owner decided on
2026-10-05 that public change sets do not count, so all three are candidates. That is
the direction's Option 3: candidates only.

## Steps

1. Machine-local evidence files: `.work/tickets/L-0538/changesets-angular.txt` (a copy of
   the research) and `quote-check-angular.txt` (4 of 4 angular.dev sentences found in the
   raw pages). The quote check is kept under `.work/` rather than at the
   `docs/tickets/L-0538/` path the spec names, because no set ships and the file is
   machine-local evidence.
2. Write `stack-angular/references/candidates.md` with NG-07 (the spec's publishable
   rule, Applies when and Self-check text, plus the public evidence), NG-P1 and NG-P2. The
   other research ids are not listed one by one, because their titles and counts are
   private. That is a reported deviation from the acceptance item that wants all
   seventeen listed.
3. `stack-angular/SKILL.md`: add `## Standards`, add pitfall pointers (NG-P1, and a
   failed-read bullet for NG-07), and narrow the description. The AngularJS section is
   unchanged.
4. Docs: `plugin/crew/README.md`, the `plugin/PLUGINS.md` row, CHANGELOG, and a
   re-measured BUDGETS.md.
5. Tests: `test_stack_skills.py`, `test_crew_standards.py`, `test_lifecycle_commands.py`.

Standards: none - Markdown only.

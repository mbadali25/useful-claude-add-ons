# L-0534 plan: PowerShell standards set (PWSH), T-0086 slice 4 (as built)

Written by the implementing session, 2026-10-05, on `rush/g7-standards` (release/1.2.0 lane).

## Outcome

One standard ships: PWSH-16, the command-resolution half, in
`crew-standards/references/powershell.md`, set `PWSH`. It rests on three of this
repository's own reviews, read from the CHANGELOG and the commits:
- crew 0.19.69, commit `fe8187e9`, "Two findings from a security review".
- crew 0.19.92, PR #200, the PowerShell-security-hardening review's FIX.
- crew 1.0.23, BLOCK B2, commits `9e57868d` and `735c225d`. Here the CHANGELOG entry is the
  review record; the commit message itself names no review.

Owner decision, 2026-10-05: public change sets do not count. PWSH-16's command-resolution
half is the one exception the owner named for admission. Every other rule is a candidate.
The research text was not available, so PWSH-16's id rests on the spec's description of
"the command-resolution half of PWSH-16".

## Steps

1. Machine-local evidence files under `.work/tickets/L-0534/`:
   - `changesets-pwsh.txt`: the research copy plus this build's verification line.
   - `quote-check-pwsh.txt`: every Source sentence and every Earned-by quote found in the
     raw page, the CHANGELOG or the commit message.
   - `notes.md`: the hand-run mutations.
2. `references/powershell.md`: PWSH-16 with Rule, Why ("4 findings across 3 change
   sets"), Change sets, Applies when, Self-check, Earned by and Source. There is no
   StrictMode clause.
3. Tests in `test_crew_standards.py`: `_ADMITTED_PWSH`, `_PWSH_FINDINGS`, and four new
   tests (parse, finding count, no elision, applies-to). Each was proven red by a hand-run
   mutation and restored byte-identical. The red runs are in `notes.md`, and the
   mutations are the tooling-only follow-up's `STANDARDS_MUTATIONS`.
4. `stack-powershell/SKILL.md`: add `## Standards` (pointer, admitted id, `PWSH-NN` =
   `POWERSHELL-NN`) and a description line, at 120 lines exactly. New
   `references/candidates.md` lists PWSH-P1, -P2, -P3, -04, the StrictMode half
   (documentation only) and PWSH-20 (overlay material). The other research ids are not
   listed one by one, because their text was not available. That is a reported deviation.
5. Docs: the `crew-standards/SKILL.md` stack-sets bullet (kept at 120 lines),
   `plugin/crew/README.md`, the `plugin/PLUGINS.md` rows, `.crew/codemap/crew.md` with the
   rules regenerated, CHANGELOG with a Behaviour change line, and BUDGETS.md.
6. The crew-standards verify rule's suites, `test_stack_skills.py`,
   `test_recurring_findings.py`, smoke and check-tooling-pr.

Standards: GEN-04 (each new test proven red by a mutation), GEN-01 (could-not-tell kept
as could-not-tell in the candidate counts).

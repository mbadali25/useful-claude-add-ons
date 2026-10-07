# L-0535 direction - .NET development standards set (T-0086 slice)

Status: approved direction, inherited from T-0086. Owner 2026-09-30 ~11:20: "File 7 tickets now" - the remaining T-0086 language slices each get their own ticket, spec, review budget and PR. T-0086 closes as the Python slice.

Carry over unchanged from `.work/tickets/T-0086/direction.md`: the one-set-per-stack format on T-0085's wiring (`plugin/crew/skills/crew-standards/references/dotnet.md`, `applies-to` globs), the admission bar (findings from at least three distinct reviewed change sets; an official doc is the Source, not a change set; rules below the bar are listed as candidates in the stack skill, not shipped), Earned-by citations re-read from the raw sources, a change-set count for every rule, and the self-check wiring. Follow T-0086's Python slice as the worked example: its spec, plan, tests (test_crew_standards.py count and quote checks) and sabotage_standards.py entries.

Research: `.work/tickets/T-0086/research/dotnet.md` (and README.md, "Recommended next step").
Stack skill: extend stack-dotnet; must agree with the owner's global CLAUDE.md (.NET rules; always var; NSubstitute+FluentAssertions for new test projects; Result<TValue,TError> decided in spec, closed enum accepted per DOTNET-13).
Order in T-0086's direction: Python (T-0086), SQL (L-0532), PHP (L-0533), PowerShell (L-0534), .NET (L-0535), Terraform (L-0536), Node.js (L-0537), Angular 2+ (L-0538). The slices are independent files, but each touches crew-standards/SKILL.md and BUDGETS.md, so they land through the merge train one at a time.
Depends on: T-0086 (Python) landing first, which sets the pattern and the test and sabotage scaffolding. Also L-0539 (the check-tooling-pr.py fix), else each slice needs the same rule-36 waiver T-0086 got.

## Ask
Ship the .NET / C# slice of T-0086: `plugin/crew/skills/crew-standards/references/dotnet.md`, set `DOTNET`, on
T-0085's loader unchanged, holding only the research rules (`.work/tickets/T-0086/research/dotnet.md`, DOTNET-01 to
-20) that findings from at least three distinct reviewed change sets earn, with raw-verified Microsoft Learn
quotes as Source. The rest become candidates in `stack-dotnet`. The stack guidance must agree with the owner's
global CLAUDE.md .NET rules.

## Options
1. **Follow the Python slice exactly: the set file, tests in `test_crew_standards.py`, stack-dotnet pointer and
   candidates, docs and version; the sabotage entries go in a separate tooling-only PR (recommended).** The
   Python pattern was reviewed twice and landed. `plugin/crew/tests/sabotage*.py` is a HARNESS path
   (`scripts/check-tooling-pr.py:79`), and L-0539 (the checker fix that would let a feature's own sabotage
   entries ride along) has not merged, so putting the entries in this PR would need T-0086's rule-36 waiver
   again. Cost: two PRs, and the new tests' sabotage proof is done by hand in the feature PR (recorded in the PR
   body) until the tooling PR commits it.
2. **Wait for L-0539, then one PR with the sabotage entries.** One PR. Cost: blocked on a high-risk ticket that
   is still at `direction`, with no date.
3. **Ship all twenty rules, counting SRL/Vault CLAUDE.md lines, security-findings docs and vault notes as change
   sets.** A fuller set. Cost: breaks the landed admission bar (`crew-standards/SKILL.md:16-17`) and T-0086's
   counting rule; the stack test (`test_every_stack_standard_names_and_cites_three_change_sets`) would have to be
   weakened.

## Recommendation
Option 1. The provisional re-count (spec Evidence) admits three rules, DOTNET-08, -13 and -15. The implementing
session re-counts from `git show` before writing the file; the set ships whatever passes, with at least one rule.
If L-0539 has merged by implement time, the sabotage entries ride along in this PR instead (L-0539's rule).

## Open questions (default taken)
- **`var`.** The owner's global CLAUDE.md now says only "Always use `var`" (the contradiction the research saw is
  gone, re-read 2026-10-05). Default taken: a convention, not a standard. It is stated once in stack-dotnet's
  conventions list, with no id and no self-check row, because no review finding earned it.
- **Test framework.** Default taken: new test projects use xUnit + NSubstitute + FluentAssertions (owner rule);
  an existing project keeps its framework (SRL's Moq, Vault's hand-rolled fakes) until the owner approves a
  switch for that repository. Stated in stack-dotnet guidance, not as a gated rule.
- **`Result<TValue, TError>` type.** Default taken: no package is named. DOTNET-13 accepts the repository's own
  `Result<TValue, TError>` or a closed outcome enum, so the rule does not depend on a library neither SRL nor
  Vault has.
- **What counts as a change set for .NET evidence.** Default taken: T-0086's counting rule as shipped in
  `python.md`'s lead. A fix commit counts when its own message records a review round or finding; commits of one
  ticket (SRL-NNN) or one pull request count once; a commit whose PR cannot be told counts with its same-day
  siblings once (GEN-01: unknown does not collapse into the generous answer). CLAUDE.md lines, `docs/*FINDINGS*`
  files, vault notes and the owner's global rules are not change sets.
- **`applies-to`.** Default taken: `["**/*.cs", "**/*.cshtml", "**/*.razor"]` (C# source, including Razor).
  `.csproj`/`.sln` changes do not draw the set: none of the admitted rules is about project files.

## Approval
Approved 2026-10-05 for cloud hand-off by the orchestrator under the owner's standing self-approve authority.

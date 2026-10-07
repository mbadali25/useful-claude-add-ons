# L-0535 plan: .NET standards, T-0086 slice (as built)

Written by the implementing session, 2026-10-05, on `rush/g7-standards` (release/1.2.0 lane).

## What changed from the spec, and why

- **No `references/dotnet.md` ships.** The spec's admitted rules, DOTNET-08, -13 and -15,
  rest on the owner's research text and private SRL/Vault commits. Neither was available
  to this session, so the rules cannot be written. A cloud research pass produced two
  public-evidence rules instead, DOTNET-P1 and DOTNET-P2.
- **Owner decision, 2026-10-05.** Public change sets do not count toward the bar. P1 and
  P2 are therefore candidates, following L-0536's "candidates now, a set when earned"
  model. The new tests, the hand-run mutations and the sabotage follow-up apply only to a
  shipped set, so none are added.

## Steps

1. `.work/tickets/L-0535/changesets-dotnet.txt` (research copy, machine-local) and
   `quote-check-dotnet.txt` (3 of 3 Source sentences found in the raw pages).
2. `stack-dotnet/references/candidates.md`: P1 and P2 with change sets, verdict and Source;
   the spec's per-rule counts for DOTNET-01..20 without their text; the conventions with
   no id.
3. `stack-dotnet/SKILL.md`: a `## Standards` section (why no set ships, and the
   test-framework and `Result` defaults), plus pointers from the async and `HttpClient`
   pitfalls. Stays within 120 lines.
4. Docs: `plugin/crew/README.md`, `plugin/PLUGINS.md` (stack-dotnet row), CHANGELOG, and a
   re-measured BUDGETS.md.
5. Tests: `test_stack_skills.py`, `test_crew_standards.py`, `test_lifecycle_commands.py`.
   Checks: check-tooling-pr, check-marketplace, smoke, self-claims.

Standards: none - Markdown only.

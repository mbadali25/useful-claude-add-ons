# Cloud handoff: L-0535

**.NET development standards set (DOTNET), T-0086 slice**

Handed to a cloud session on 2026-10-05 by owner instruction. Do not pick up locally.

- **Role:** slice of T-0086 (done, PR #282); the .NET stack in the direction's order.
- **INDEX status:** spec (direction and spec approved for hand-off 2026-10-05; plan to be written by the implementing session)
- **Branch:** `L-0535-build`, new from origin/main `a555ff37`; docs only, no implementation yet
- **Files here:** `docs/tickets/L-0535/direction.md`, `docs/tickets/L-0535/spec.md`
- **Size:** 0 production lines. One new set file (`crew-standards/references/dotnet.md`, about 150-250 lines for the three provisionally admitted rules), about 60 test lines, about 15 lines in `stack-dotnet/SKILL.md` plus a new `stack-dotnet/references/candidates.md` (stack skills are capped at 120 lines), doc rows.
- **Harness:** no. `plugin/crew/tests/sabotage*.py` is a harness path and is kept out; the DOTNET sabotage entries go in a separate tooling-only PR (or ride along if L-0539 has merged first).

## Dependencies and work order

| Ticket | State | Why |
|---|---|---|
| T-0086 | done, merged (#282) | The pattern: `python.md`, the stack tests, the sabotage scaffolding. |
| L-0539 | direction, not merged | Would let this PR carry its own sabotage entries. Not a blocker. |
| L-0532, L-0533, L-0534 | direction / spec | Earlier siblings; same doc lines. Land one at a time, merge main between. |
| (unminted) | to file | Tooling-only follow-up: the DOTNET sabotage entries. |

## Read before writing code

- The spec's evidence is at origin/main `a555ff37`. Re-find every line by content.
- The research is `.work/tickets/T-0086/research/dotnet.md` on the owner's host (not in git). If the cloud session cannot read it, ask the coordinator for a copy before starting; the rule text and citations come from it.
- The admitted list (DOTNET-08, -13, -15) is a provisional re-count from commit messages in the private SRL and Vault repos. Re-count from `git show` before writing the file; ship what passes, record it in `.work/tickets/L-0535/changesets-dotnet.txt`.
- Re-fetch every Microsoft Learn quote raw with `curl` and string-match it; no `[...]` elisions (the research has them).
- No production code, loader, gate or prompt edit. If something in the loader looks wrong, that is a new ticket.
- Hand-sabotage each new test once and record the mutation and the red test in the PR body.

## Open questions for the owner (recommended option taken)

- `var` and the other style rules: conventions in stack-dotnet, no id, no self-check row.
- Test framework: NSubstitute + FluentAssertions for new test projects; existing projects keep theirs.
- `Result<TValue, TError>`: no package named; DOTNET-13 accepts the repo's own Result type or a closed outcome enum.
- Change-set counting: a commit counts only when its message records a review; one SRL ticket or Vault PR counts once; commits whose PR cannot be told count once together.
- `applies-to`: `**/*.cs`, `**/*.cshtml`, `**/*.razor`.

## Before landing

Merge origin/main, take a crew version above main's from the coordinator, follow the repo's CLAUDE.md (scope discipline, doc updates for `plugin/crew` changes, tooling-PR rule), flag the behaviour change in CHANGELOG and the PR body (C# changes now answer DOTNET rows; in-flight stamps go stale), and remove `docs/tickets/L-0535/` in the final PR unless the owner wants it kept.

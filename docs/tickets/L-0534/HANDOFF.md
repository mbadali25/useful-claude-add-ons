# Cloud handoff: L-0534

**PowerShell development standards set (PWSH), T-0086 slice 4**

Handed to a cloud session on 2026-10-05 by owner instruction. Do not pick up locally.

- **Role:** child of T-0086 (done, #282), language slice 4 of 8.
- **INDEX status:** spec (direction and spec written and approved for hand-off 2026-10-05; plan to be written by the implementing session)
- **Branch:** `L-0534-build`, new from origin/main `a555ff37` (crew 1.1.0); docs only, no implementation yet
- **Files here:** `docs/tickets/L-0534/direction.md`, `docs/tickets/L-0534/spec.md`
- **Size:** 0 production lines. One new Markdown set (`references/powershell.md`, 300-600 lines), about 13 net lines in `stack-powershell/SKILL.md` (107 of 120 now; a small `references/candidates.md` if it does not fit), four tests and a findings table in `test_crew_standards.py`, doc rows.
- **Harness:** no. `sabotage_standards.py` is a harness path and stays out; its four entries go in a follow-up tooling-only PR unless L-0539 merged first.
- **Risk:** medium. On the research's own citations no rule clearly reaches three reviewed change sets, and a PWSH set applies to every hook-pair change in this repository (44 `.ps1` files).

## Dependencies and work order

| Ticket | State | Why |
|---|---|---|
| T-0086 | merged (#282) | Set format, tests to mirror, counting rule. |
| L-0539 | direction, no PR | Decides only where the sabotage entries go. Not blocking. |
| L-0532 (SQL), L-0533 (PHP) | spec | Sibling slices on the same shared lines; one at a time through the merge train. |
| L-0535..L-0538 | direction | Later slices. |

This ticket blocks nothing.

## Read before writing code

- The set is `PWSH`, not `POWERSHELL`: the loader allows 2-6 capitals for set names and id prefixes (`crew_standards.py:83-84`, `:131-133`). Ids `PWSH-NN` keep the research numbers.
- The first plan step is the evidence step. Count this repository's own PowerShell reviews and CHANGELOG review entries first, then the owner's private repos (research held by the coordinator, `.work/tickets/T-0086/research/powershell.md`, not published). Commits of one review series count once.
- This repository is public. No published file may name a private repository or client, or carry its shas, commit subjects, ticket or PR ids. Private change sets are cited generically under opaque labels; the mapping stays machine-local.
- POWERSHELL-20 stays out of the set (its code is `.py`); StrictMode is a doc-only candidate; BOM is required only for non-ASCII source.
- `stack-powershell/SKILL.md` must stay at or under 120 lines, and its verify rules (run for real by `test_stack_skills.py`) are not touched.
- Do not edit `sabotage*.py`, rename any existing test, touch `crew_standards.py`, or change any `.ps1`.

## Open questions for the owner (recommended option taken)

- Set `PWSH` over widening the loader's id regex or using `PS`.
- `applies-to` is `["**/*.ps1", "**/*.psm1", "**/*.psd1"]`.
- StrictMode dropped from the gated set (no owner change set); listed as a candidate.
- UTF-8 with BOM when a `.ps1` holds non-ASCII; ASCII-only source meets the rule.
- POWERSHELL-20 is overlay material for this repository, not written here.
- If no rule is admitted, no `powershell.md` ships; every rule becomes a candidate.

## Before landing

Merge origin/main (merge commit, never rebase), take a crew version above main's from the coordinator, follow the repo's CLAUDE.md (doc updates for `plugin/crew` changes, the tooling-PR rule, `check-marketplace.py` after commit), state `Docs: none - <why>` for the guides, CONFIG.md and diagrams, and remove `docs/tickets/L-0534/` in the final PR unless the owner wants it kept.

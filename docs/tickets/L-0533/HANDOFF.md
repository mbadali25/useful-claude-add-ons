# Cloud handoff: L-0533

**PHP development standards set and a new stack-php skill, T-0086 slice 3**

Handed to a cloud session on 2026-10-05 by owner instruction. Do not pick up locally.

- **Role:** child of T-0086 (done, #282), language slice 3 of 8.
- **INDEX status:** spec (direction and spec written and approved for hand-off 2026-10-05; plan to be written by the implementing session)
- **Branch:** `L-0533-build`, new from origin/main `a555ff37` (crew 1.1.0); docs only, no implementation yet
- **Files here:** `docs/tickets/L-0533/direction.md`, `docs/tickets/L-0533/spec.md`
- **Size:** 0 production lines. One new Markdown set (`references/php.md`, 300-600 lines), one new skill (`stack-php/SKILL.md`, at most 120 lines), four tests and a findings table in `test_crew_standards.py`, two lines in `test_stack_skills.py`, the crew skill count 31 -> 32 in five checked claims plus unmarked mentions, doc rows.
- **Harness:** no. `sabotage_standards.py` is a harness path and stays out; its four entries go in a follow-up tooling-only PR unless L-0539 merged first.
- **Risk:** medium. Every PHP rule is earned in one private repository, and on the research's own citations at most two rules reach three reviewed change sets, so the slice depends on an evidence step.

## Dependencies and work order

| Ticket | State | Why |
|---|---|---|
| T-0086 | merged (#282) | Set format, tests to mirror, counting rule. |
| L-0539 | direction, no PR | Decides only where the sabotage entries go. Not blocking. |
| L-0532 (SQL) | spec | PHP-01 supplements the SQL parameterisation rule: name SQL-01 if L-0532 landed with it, else `stack-sql`'s line. Shared lines go through the merge train. |
| L-0534, L-0535..L-0538 | spec / direction | Sibling slices on the same shared lines; one at a time. |

This ticket blocks nothing.

## Read before writing code

- The first plan step is the evidence step. The evidence is research held by the coordinator (`.work/tickets/T-0086/research/php.md`, not published) and one of the owner's private repos. A session without them must stop and say so.
- This repository is public. No published file, `php.md` included, may name the private repository or client, or carry its shas, commit subjects, ticket or PR ids, review-file names or finding ids. Change-set names are opaque labels; the mapping stays machine-local.
- Shipped sets may not contain `\bF\d{3}\b` (`test_crew_standards.py:250`).
- `stack-php` must satisfy `test_stack_skills.py`: add it to `STACK_NAMES` and `_TRIGGER_TERMS`, at most 120 lines, a description of at least 80 characters naming PHP, and a fenced ```json verify rule whose command has an exit-77 `TOOL MISSING` branch (model: `stack-sql/SKILL.md:71-86`).
- Every `<!-- claim: plugin-skills:crew -->` line moves 31 -> 32; `check-marketplace.py` checks them after commit. Also fix the unmarked mentions in `marketplace.json`'s crew description and the code maps.
- Do not edit `sabotage*.py`, rename any existing test, or touch `crew_standards.py` or the install scripts.

## Open questions for the owner (recommended option taken)

- `applies-to` is `["**/*.php", "**/*.phtml"]`; `composer.json`, `php.ini` and pool configs left out.
- Three reviewed change sets in one repository meet the bar.
- Framework specifics stay out of the plugin set.
- Private evidence is cited generically under opaque change-set labels.
- `stack-php`'s verify rule is `php -l` with the exit-77 branch; no installer change.
- If no rule is admitted, `stack-php` ships with every rule as a candidate and no `php.md`.

## Before landing

Merge origin/main (merge commit, never rebase), take a crew version above main's from the coordinator, follow the repo's CLAUDE.md (registration in every place in one commit, doc updates for `plugin/crew` changes, the tooling-PR rule, `check-marketplace.py` after commit), state `Docs: none - <why>` for the guides, CONFIG.md and diagrams, and remove `docs/tickets/L-0533/` in the final PR unless the owner wants it kept.

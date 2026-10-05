# Cloud handoff: L-0532

**SQL development standards set (MySQL/MariaDB, SQL Server, PostgreSQL), T-0086 slice 2**

Handed to a cloud session on 2026-10-05 by owner instruction. Do not pick up locally.

- **Role:** child of T-0086 (done, #282), language slice 2 of 8 (Python, SQL, PHP, PowerShell, .NET, Terraform, Node.js, Angular 2+).
- **INDEX status:** spec (direction and spec written and approved for hand-off 2026-10-05; plan to be written by the implementing session)
- **Branch:** `L-0532-build`, new from origin/main `a555ff37` (crew 1.1.0); docs only, no implementation yet
- **Files here:** `docs/tickets/L-0532/direction.md`, `docs/tickets/L-0532/spec.md`
- **Size:** 0 production lines. One new Markdown set file (`references/sql.md`, 300-600 lines depending on how many rules ship), about 40 lines in `stack-sql/SKILL.md`, four tests and a findings table in `test_crew_standards.py`, doc rows.
- **Harness:** no. `plugin/crew/tests/sabotage_standards.py` is a harness path and is deliberately out of this PR; its four entries go in a follow-up tooling-only PR unless L-0539 has merged first.
- **Risk:** medium. The research's own citations earn no rule under the counting rule T-0086 shipped, so the slice depends on an evidence step whose outcome is not known yet.

## Dependencies and work order

| Ticket | State | Why |
|---|---|---|
| T-0086 | merged (#282) | Sets the set format, the tests this slice mirrors and the counting rule in `python.md`'s lead. |
| L-0539 | direction, no PR | Only decides where the sabotage entries go: here if it has merged, else a follow-up tooling-only PR. Not blocking. |
| L-0533, L-0534, L-0535..L-0538 | spec / direction | Sibling slices. Each edits the same shared lines (`crew-standards/SKILL.md`, `README.md:795`, `PLUGINS.md:217`, `crew.md`'s stack-set sentence, `test_crew_standards.py`, BUDGETS, CHANGELOG). They land one at a time through the merge train; the later one merges main and re-words the shared lines. |

This ticket blocks nothing.

## Read before writing code

- The first plan step is the evidence step, not code. Open every commit `research/sql.md` cites (`git -C /repos/anew/<repo> show <sha>`), then search the four owner repositories (SRL, TheSelectSource, TheHomeDepot, Vault) for review-recorded fix commits per rule, open each lead, and write `.work/tickets/L-0532/changesets-sql.txt`. The spec's Evidence has the pre-count (none reach three on the strict reading) and the leads. A commit inside a ticket counts as that ticket once; vault notes, CLAUDE.md lines and FINDINGS.md never count.
- The research is machine-local: `.work/tickets/T-0086/research/sql.md` in the owner's main checkout. A cloud session without it, or without `/repos/anew/*`, cannot do the evidence step and must stop and say so rather than ship on the research text.
- Follow the Python slice exactly: `references/python.md` (lead paragraph, field order, Earned-by bullet forms, `**Change sets.** N: a, b, c`), `stack-python/SKILL.md:46-86`, and T-0086's spec and plan.
- The loader refuses any `## ` heading that is not a standard. Engine sections are expressed in each heading name (`## SQL-17 SQL Server: ...`), never as a `##` or `###` section line.
- Every doc quote was summarised by WebFetch. Re-read each from the raw page and record the match in `quote-check-sql.txt`; a miss is replaced or dropped, never paraphrased.
- `stack-sql/SKILL.md` must stay at or under 120 lines (`test_stack_skills.py:142`); it is 90 now.
- Do not edit `sabotage*.py`, do not rename any existing test (sabotage entries name tests by node id), and do not touch `crew_standards.py`.

## Open questions for the owner (recommended option taken)

- `applies-to` is `["**/*.sql"]` only; SQL in PHP or C# strings is the host language set's job.
- One file; engine-specific rules name the engine in their heading; ids keep the research numbers.
- A rule earned by three reviewed change sets in one repository counts.
- Sabotage entries go to a follow-up tooling-only PR unless L-0539 merged first.
- If the evidence step admits no rule, no `sql.md` ships; every rule becomes a `stack-sql` candidate and the ticket closes with the count recorded.

## Before landing

Merge origin/main (merge commit, never rebase), take a crew version above main's from the coordinator, follow the repo's CLAUDE.md (scope discipline, doc updates for `plugin/crew` changes, the tooling-PR rule, `check-marketplace.py` after commit), state `Docs: none - <why>` for the guides, CONFIG.md and diagrams in the PR body, and remove `docs/tickets/L-0532/` in the final PR unless the owner wants it kept.

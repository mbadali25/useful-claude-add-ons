# Cloud handoff: L-0532

**SQL development standards set (MySQL/MariaDB, SQL Server, PostgreSQL), T-0086 slice 2**

Handed to a cloud session on 2026-10-05 by owner instruction. Do not pick up locally.

- **Role:** child of T-0086 (done, #282), language slice 2 of 8 (Python, SQL, PHP, PowerShell, .NET, Terraform, Node.js, Angular 2+).
- **INDEX status:** spec (direction and spec written and approved for hand-off 2026-10-05; plan to be written by the implementing session)
- **Branch:** `L-0532-build`, new from origin/main `a555ff37` (crew 1.1.0); docs only, no implementation yet
- **Files here:** `docs/tickets/L-0532/direction.md`, `docs/tickets/L-0532/spec.md`
- **Size:** 0 production lines. One new Markdown set (`references/sql.md`, 300-600 lines), about 40 lines in `stack-sql/SKILL.md`, four tests and a findings table in `test_crew_standards.py`, doc rows.
- **Harness:** no. `sabotage_standards.py` is a harness path and stays out; its four entries go in a follow-up tooling-only PR unless L-0539 merged first.
- **Risk:** medium. The research's own citations earn no rule under T-0086's counting rule, so the slice depends on an evidence step whose outcome is not known yet.

## Dependencies and work order

| Ticket | State | Why |
|---|---|---|
| T-0086 | merged (#282) | Set format, tests to mirror, counting rule in `python.md`'s lead. |
| L-0539 | direction, no PR | Decides only where the sabotage entries go. Not blocking. |
| L-0533, L-0534, L-0535..L-0538 | spec / direction | Sibling slices on the same shared lines; they land one at a time, the later one merges main and re-words the shared lines. |

This ticket blocks nothing.

## Read before writing code

- The first plan step is the evidence step, not code. The evidence is research held by the coordinator (`.work/tickets/T-0086/research/sql.md`, not published) and the owner's private repos. A session without them must stop and say so rather than ship on the research text.
- This repository is public. No published file, `sql.md` included, may name a private repository or client, or carry a private sha, commit subject, ticket or PR id or review-file name. Change-set names in `sql.md` are opaque labels; the mapping stays machine-local.
- Follow the Python slice: `references/python.md`, `stack-python/SKILL.md:46-86`, and T-0086's spec and plan.
- Engine sections go in each heading name (`## SQL-17 SQL Server: ...`), never as a `##` or `###` section line.
- Re-read every doc quote from the raw page; a miss is replaced or dropped, never paraphrased.
- `stack-sql/SKILL.md` stays at or under 120 lines (90 now).
- Do not edit `sabotage*.py`, rename any existing test, or touch `crew_standards.py`.

## Open questions for the owner (recommended option taken)

- `applies-to` is `["**/*.sql"]` only.
- One file; engine-specific rules name the engine in their heading; ids keep the research numbers.
- Three reviewed change sets in one repository count.
- Private evidence is cited generically under opaque change-set labels.
- Sabotage entries go to a follow-up tooling-only PR unless L-0539 merged first.
- If no rule is admitted, no `sql.md` ships; every rule becomes a `stack-sql` candidate.

## Before landing

Merge origin/main (merge commit, never rebase), take a crew version above main's from the coordinator, follow the repo's CLAUDE.md (scope discipline, doc updates for `plugin/crew` changes, the tooling-PR rule, `check-marketplace.py` after commit), state `Docs: none - <why>` for the guides, CONFIG.md and diagrams, and remove `docs/tickets/L-0532/` in the final PR unless the owner wants it kept.

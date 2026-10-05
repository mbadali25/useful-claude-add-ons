# L-0532 direction - SQL (MySQL/MariaDB, MSSQL, PostgreSQL sections) development standards set (T-0086 slice)

Status: approved direction, inherited from T-0086. Owner 2026-09-30 ~11:20: "File 7 tickets now" - the remaining T-0086 language slices each get their own ticket, spec, review budget and PR. T-0086 closes as the Python slice.

Carry over unchanged from `.work/tickets/T-0086/direction.md`: the one-set-per-stack format on T-0085's wiring (`plugin/crew/skills/crew-standards/references/sql.md`, `applies-to` globs), the admission bar (findings from at least three distinct reviewed change sets; an official doc is the Source, not a change set; rules below the bar are listed as candidates in the stack skill, not shipped), Earned-by citations re-read from the raw sources, a change-set count for every rule, and the self-check wiring. Follow T-0086's Python slice as the worked example: its spec, plan, tests (test_crew_standards.py count and quote checks) and sabotage_standards.py entries.

Research: `.work/tickets/T-0086/research/sql.md` (and README.md, "Recommended next step").
Stack skill: extend stack-sql.
Order in T-0086's direction: Python (T-0086), SQL (L-0532), PHP (L-0533), PowerShell (L-0534), .NET (L-0535), Terraform (L-0536), Node.js (L-0537), Angular 2+ (L-0538). The slices are independent files, but each touches crew-standards/SKILL.md and BUDGETS.md, so they land through the merge train one at a time.
Depends on: T-0086 (Python) landing first, which sets the pattern and the test and sabotage scaffolding. Also L-0539 (the check-tooling-pr.py fix), else each slice needs the same rule-36 waiver T-0086 got.

## Ask
Owner, 2026-09-28 (T-0086): general development standards for SQL (MySQL, MSSQL, Postgres) "so that other repos could benefit". Owner, 2026-09-30: each remaining T-0086 language slice gets its own ticket, spec, review budget and PR. This is the SQL slice: `plugin/crew/skills/crew-standards/references/sql.md` on T-0085's loader, unchanged, with the rules that meet the landed admission bar, and `stack-sql` pointing at it and listing the rest as candidates.

## Facts found at origin/main `a555ff37` (2026-10-05)
- T-0086 (Python) is merged (#282, `549cda24`). `references/` holds `generic.md` and `python.md`. No SQL set exists; no PR or commit names L-0532.
- L-0539 (check-tooling-pr fix) is still at `direction` and has no PR. `HARNESS` in `scripts/check-tooling-pr.py:58-87` still lists `plugin/crew/tests/sabotage*.py`, so a sabotage entry in this PR would make it a harness change carrying feature work.
- The loader takes ids matching `^[A-Z]{2,6}-\d{2}$` (`crew_standards.py:83`) and refuses any `## ` heading that is not a standard (`:175-199`), so per-engine sections cannot be `##` headings, and a `###` line would be read as continuation text of the previous field.
- On the research's own citations, no SQL rule reaches three reviewed change sets under the counting rule T-0086 shipped (`python.md` lead: a crew review, or a fix commit whose message records that a review found the defect; a commit inside a ticket counts as that ticket once; vault notes, CLAUDE.md lines and FINDINGS.md are not change sets). The research cites 25 commits in SRL, TheSelectSource, TheHomeDepot and Vault; most rules rest on one or two tickets plus vault notes (spec Evidence has the per-rule count).
- The owner repos hold far more review-recorded fix commits than the research read: `git log --all --no-merges` subjects matching `codex|gate r[0-9]|round|BLOCK|FIX` number 1624 in SRL, 2999 in TheSelectSource, 488 in TheHomeDepot and 94 in Vault (measured 2026-10-05). A keyword pass per rule finds candidate further tickets for most rules (for example SQL-06: SRL-1458, SRL-1535, SRL-1443; SQL-12: SRL-1632, SRL-1587). None of those was opened; they are leads, not counts.

## Options
1. **Mine, then admit (recommended).** Implement starts with a bounded evidence step: every research citation opened with `git show`, plus a per-rule search of the four owner repos' review-recorded fix commits, each candidate opened and classified. A rule ships when three distinct reviewed change sets earn it; the rest are candidates in `stack-sql`. One `sql.md` with engine-specific rules named in their headings. Cost: the evidence step is real work (an afternoon of reading), and the admitted count is not known until it is done.
2. **Ship on the research as written.** Fast, but by the shipped counting rule it admits nothing, so the slice would ship an empty set file, which the loader refuses (`defines no standard`, `crew_standards.py:222`).
3. **Ask the owner to let an official doc count as a change set for stack sets.** Would admit most rules at once. Cost: overturns a settled direction decision (T-0086 direction, "Admission bar"), and this brief forbids asking; not taken.

## Recommendation
Option 1, with these defaults, approved 2026-10-05 for cloud hand-off under the owner's standing self-approve authority.

## Open questions (default taken)
- **applies-to.** Default: `["**/*.sql"]`. SQL embedded in PHP or C# strings is covered by those stacks' sets (PHP-01 is written as a supplement to the SQL parameterisation rule), so a PHP change does not also answer up to 20 SQL rows. Alternative rejected: adding `**/*.php`, `**/*.cs`, `**/migrations/**`, which would make every PHP or .NET change answer the SQL set.
- **Engine sections.** Default: one file, set `SQL`, ids `SQL-NN` keeping the research numbers; engine-specific rules carry the engine at the start of the heading name (`## SQL-17 SQL Server: session SET options are part of the change`) and in **Applies when**. The lead paragraph lists which ids are general and which belong to MySQL/MariaDB, SQL Server and PostgreSQL. No per-engine file, since a `.sql` glob cannot tell engines apart.
- **Sabotage entries.** Default: not in this PR. `sabotage_standards.py` is a harness path and L-0539 has not landed, so the three mutations go in a follow-up tooling-only PR (owner's standing rule "split, do not ask", 2026-09-30); the feature PR proves each new test red by a hand-run mutation recorded in the ticket notes. If L-0539 has merged before this lands, the entries ride in this PR instead.
- **A rule with exactly three change sets in one repository.** Default: counts. The bar is distinct reviewed change sets, not distinct repositories (T-0086 shipped PYTHON rules earned inside this one repository).
- **Private-repository citations.** Default: cited as `<repo> commit <sha> (<ticket> <round>)` with the subject quoted, as `python.md` cites TheHomeDepot; no local path, vault note or `.work/` file.
- **The anti-pattern about an ORM's cached table metadata** (`research/sql.md` anti-pattern 19) is PHP-side and stays out of this set.
- **If the evidence step admits fewer than three rules.** Default: ship them anyway (one is enough for the loader); if it admits none, ship no `sql.md`, put every rule in `stack-sql`'s candidate list, and close the ticket with the count recorded. No owner question is raised either way.

## Approval
Direction approved 2026-10-05 for cloud hand-off by the orchestrator under the owner's standing self-approve authority. Next: spec (`docs/tickets/L-0532/spec.md`).

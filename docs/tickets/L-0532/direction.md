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
- L-0539 (check-tooling-pr fix) is still at `direction` with no PR. `HARNESS` in `scripts/check-tooling-pr.py:58-87` still lists `plugin/crew/tests/sabotage*.py` (`:79`), so a sabotage entry in this PR would make it a harness change carrying feature work.
- The loader takes ids matching `^[A-Z]{2,6}-\d{2}$` (`crew_standards.py:83`) and refuses any `## ` heading that is not a standard (`:175-199`), so per-engine sections cannot be `##` headings, and a `###` line would be read as continuation text of the previous field.
- The evidence behind every rule is research held by the coordinator (`.work/tickets/T-0086/research/sql.md`, not published), drawn from the owner's private repos. A pre-count by the orchestrator on 2026-10-05, applying the counting rule T-0086 shipped (`python.md` lead: a crew review, or a fix commit whose message records that a review found the defect; a commit inside a ticket counts as that ticket once; session notes and repository instruction files are not change sets), found that **no SQL rule reaches three reviewed change sets on the research's own citations**; most rest on one or two.
- The owner's private repos hold many more review-recorded fix commits than the research read, and a keyword pass found candidate further change sets for most rules. They are leads, not counts; none was opened.

## Options
1. **Mine, then admit (recommended).** Implement starts with a bounded evidence step: every research citation opened, plus a per-rule search of the owner's private repos for review-recorded fix commits, each candidate opened and classified. A rule ships when three distinct reviewed change sets earn it; the rest are candidates in `stack-sql`. One `sql.md` with engine-specific rules named in their headings. Cost: real reading work, and the admitted count is not known until it is done.
2. **Ship on the research as written.** By the shipped counting rule it admits nothing, so the slice would ship an empty set file, which the loader refuses (`defines no standard`, `crew_standards.py:222`).
3. **Ask the owner to let an official doc count as a change set for stack sets.** Overturns a settled direction decision (T-0086 direction, "Admission bar"); not taken.

## Recommendation
Option 1, with these defaults, approved 2026-10-05 for cloud hand-off under the owner's standing self-approve authority.

## Open questions (default taken)
- **applies-to.** `["**/*.sql"]`. SQL embedded in PHP or C# strings is covered by those stacks' sets (PHP-01 supplements the SQL parameterisation rule), so a PHP change does not also answer up to 20 SQL rows.
- **Engine sections.** One file, set `SQL`, ids `SQL-NN` keeping the research numbers; engine-specific rules carry the engine at the start of the heading name (`## SQL-17 SQL Server: session SET options are part of the change`) and in **Applies when**. The lead paragraph lists which ids are general and which belong to MySQL/MariaDB, SQL Server and PostgreSQL.
- **Sabotage entries.** Not in this PR: `sabotage_standards.py` is a harness path and L-0539 has not landed, so the mutations go in a follow-up tooling-only PR (owner's standing rule "split, do not ask", 2026-09-30). The feature PR proves each new test red by a hand-run mutation recorded in the ticket notes. If L-0539 has merged first, the entries ride here.
- **Three change sets in one repository** count: the bar is distinct reviewed change sets, not distinct repositories.
- **Citations of private-repo evidence in the shipped set.** Shipped `sql.md` is public. Default: each Earned-by line describes the defect and the review round generically ("a private client repository, review round 2 BLOCK: ..."), quoting the finding text only when it carries no client name, path, ticket id or other identifying detail. The full mapping (repository, ticket, sha) stays in the coordinator's machine-local change-set file.
- **If the evidence step admits fewer than three rules**, ship them; if none, ship no `sql.md`, list every rule as a `stack-sql` candidate, and close with the count recorded.

## Approval
Direction approved 2026-10-05 for cloud hand-off by the orchestrator under the owner's standing self-approve authority. Next: spec (`docs/tickets/L-0532/spec.md`).

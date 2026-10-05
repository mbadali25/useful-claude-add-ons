# L-0532 plan: SQL standards, T-0086 slice 2 (as built)

Written by the implementing session, 2026-10-05, on `rush/g7-standards` (release/1.2.0 lane).

## What changed from the spec, and why

- **Evidence step.** The spec's evidence step mines the owner's private repos and reads
  the coordinator's research (SQL-01..SQL-20). Neither was available to this session. A
  cloud research pass produced a public-evidence substitute: public GitHub commits whose
  own message records a review finding, and raw-verified official docs.
- **Owner decision, 2026-10-05.** Public change sets do not count toward the
  three-reviewed-change-sets bar. Every public-evidence rule is therefore a candidate,
  documented with its sources and verdict, and nothing is loaded or enforced. SQL and PHP
  state the private-evidence gap: owner-private evidence not consulted; re-check tracked
  as C-0020.
- **Result: no `references/sql.md` ships** (direction: "if none, ship no `sql.md`, list
  every rule as a `stack-sql` candidate"). The four new tests and their hand-run mutations
  belong to a shipped set, so none are added, and there are no sabotage entries to hand off.
- **Candidates go in `stack-sql/references/candidates.md`**, the L-0536 model, so
  `stack-sql/SKILL.md` gains only a `## Standards` section and a link (within 120 lines).

## Steps

1. Copy the research's change-set file to `.work/tickets/L-0532/changesets-sql.txt`, which
   is machine-local. Its SQL-01..SQL-20 lines stay commented `NOT ASSESSED`, so
   `grep -c '^SQL-'` counts only real rows. That acceptance check cannot pass honestly,
   and it is reported as a spec deviation.
2. Raw-fetch every Source page and string-match each quote into
   `.work/tickets/L-0532/quote-check-sql.txt` (7 of 7 found). The MySQL docs site failed
   during the research, so no MySQL quote is used.
3. Write `stack-sql/references/candidates.md`: SQL-P1 (PostgreSQL SECURITY DEFINER, 6
   public), SQL-P2 (PostgreSQL CONCURRENTLY, 2 public in `.sql` plus 1 Alembic), SQL-17
   (SQL Server SET options, 0 public). Each entry gives its change sets, verdict and
   Source. SQL-01..-16 and -18..-20 are listed as not assessed.
4. `stack-sql/SKILL.md`: add `## Standards` (no gated SQL set yet, and why) and a link to
   the candidates. Point to the candidates from the PostgreSQL locking bullet.
5. Docs: `plugin/crew/README.md` (stacks paragraph), `plugin/PLUGINS.md` (stack-sql row),
   `CHANGELOG.md` `[Unreleased]`, and a re-measured `plugin/crew/BUDGETS.md`.
6. Tests: `test_stack_skills.py`, `test_crew_standards.py`, `test_lifecycle_commands.py`.
   Checks: `check-tooling-pr.py`, `check-marketplace.py`.

Standards: none - Markdown only, no code path changes.

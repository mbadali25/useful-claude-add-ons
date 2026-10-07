# L-0532: SQL development standards set (MySQL/MariaDB, SQL Server, PostgreSQL), T-0086 slice 2          status: spec   risk: medium
Written against origin/main `a555ff37` (crew 1.1.0). Every `path:line` below is at that commit.

## Intent
Ship the second per-language standards set on T-0085's mechanism, unchanged:
`plugin/crew/skills/crew-standards/references/sql.md`, set `SQL`, `applies-to: ["**/*.sql"]`, holding the SQL
standards from the coordinator's research (`.work/tickets/T-0086/research/sql.md`, not published) that findings from
at least three distinct reviewed change sets earn, counted the way `python.md`'s lead paragraph counts them. Because
the research's own citations earn no rule on that count, the slice starts with a bounded evidence step in the
owner's private repos. Each shipped standard keeps an official-doc Source re-read from the raw page, and Earned by
lines that carry no private identifying detail. Rules that fall short are listed as candidates in `stack-sql`,
which also points at the set. One file covers every engine; engine-specific rules name their engine in the heading.

## Exclusions
- No change to the loader, gate, stamp or checklist: `crew_standards.py`, `review_run.py`, `review_prompt.py` and
  `crew_ticket.py` are not touched. A stack set is a new file in `references/` (`crew_standards.py:236-262`).
- **No edit to `plugin/crew/tests/sabotage*.py`.** It is a `HARNESS` path (`scripts/check-tooling-pr.py:79`) and
  L-0539 has not landed. The mutations listed under Acceptance go in a follow-up tooling-only PR (the coordinator
  mints its id), unless L-0539 merged first. This PR proves each new test red by a hand-run mutation.
- No rename of an existing test: sabotage entries name tests by node id, so a rename is a harness change.
- No other stack, and no PHP or C# glob in `applies-to`.
- No candidate standard in `sql.md` or in `.crew/standards.md`.
- **No private identifying detail in any published file**, `sql.md` included: no private repository or client
  name, path, commit sha, commit subject, ticket or PR id, or review-file name. Earned by lines describe the defect
  and the round generically. Also none of what the existing tests refuse: no `.work/` path, no `\bF\d{3}\b` token,
  no `/repos/` path, session note or auto-memory reference (`test_crew_standards.py:247-255`, `:381-390`).
- No `.crew/verify.json` change: `plugin/crew/skills/crew-standards/**` and `test_crew_standards.py` are already in
  the crew-standards rule (`.crew/verify.json:484-485`, run `:494`).
- No hook and no config key (`plugin/crew/CONFIG.md` unchanged; Docs: none there). No guide change: the guides say
  "any per-language set a changed file matches" and name no set (Docs: none there). No ADR, no diagram.
- No `/crew:implement` edit: `implement.md:77` already loads `stack-sql` for migration and schema work.
- No version bump on the build branch (REPO-03 in `.crew/standards.md`).

## Evidence
- Direction: `docs/tickets/L-0532/direction.md`; T-0086's approved direction (held by the coordinator,
  `.work/tickets/T-0086/direction.md`): a doc is Source, not a change set; each slice counts change sets per rule.
- Worked example, landed in #282 (`549cda24`): `plugin/crew/skills/crew-standards/references/python.md` (lead
  paragraph and counting rule, field order, `**Change sets.** N: a, b, c`), `plugin/crew/skills/stack-python/SKILL.md:46-86`
  (`## Standards`, `## Candidate standards (not gated)`), `CHANGELOG.md:3815`.
- Loader: `plugin/crew/hooks/scripts/crew_standards.py:76` `PLUGIN_FIELDS`; `:83` `_ID_RE` (`SQL-01` valid);
  `:175-199` a stray `## ` heading is a problem; `:222` an empty set is a problem; `:229` `_applies` through
  `crew_ticket.glob_match` (`crew_ticket.py:393`); `:236` `_plugin_sets`; `:263` `effective_set`.
- Tests that cover `sql.md` with no edit (`_STACK_SETS`, `test_crew_standards.py:261`): `:292` (N >= 3, N equals the
  names, no repeat, three cited in Earned by as `- <name> ` or `` `<name>` ``), `:307` (Why states
  `N findings across M change sets`), `:349` (line counts agree). Python-only tests to mirror: `:264`, `:336`
  (`_PYTHON_FINDINGS` `:330`), `:359`, `:372`.
- Sabotage pattern for the follow-up: `plugin/crew/tests/sabotage_standards.py:59` `PYTHON_SET`, `:61`
  `STANDARDS_MUTATIONS`, the PYTHON entries at `:434-489`.
- Harness: `scripts/check-tooling-pr.py:58-87`; L-0539 is `direction`, no PR (2026-10-05).
- Research (held by the coordinator, `.work/tickets/T-0086/research/sql.md`, not published): 20 rules, SQL-01..-14
  general, SQL-15/-16 MySQL/MariaDB, SQL-17/-18 SQL Server, SQL-19/-20 PostgreSQL. Its doc quotes came through
  summarising fetches and were never checked raw. The orchestrator's pre-count (2026-10-05) under the strict
  counting rule: no rule reaches three on the research's citations; counting every cited ticket regardless of
  whether its message records a review, five rules would. Further candidate change sets exist in the owner's private
  repos (leads only).
- Stack skill: `plugin/crew/skills/stack-sql/SKILL.md`, 90 lines; `## When this applies` `:12`, `## Pitfalls that
  cost time (all three engines)` `:20`, `## Per-engine locking and isolation` `:35`, `## Verification` `:64`,
  `## verify.json rule to propose` `:71`, `## LSP` `:88`. Cap 120 lines (`plugin/crew/tests/test_stack_skills.py:142`).
- Docs that describe the sets: `plugin/crew/skills/crew-standards/SKILL.md:17-21`; `plugin/crew/README.md:795`;
  `plugin/PLUGINS.md:217` (crew-standards, "(Python so far)") and `:223` (stack-sql); `.crew/codemap/crew.md:1830-1831`;
  `plugin/crew/BUDGETS.md:10-11` (`crew-markdown-lines` claim); `CHANGELOG.md:10` `[Unreleased]`.

## Unknowns
- **Which rules ship.** Decided by the evidence step. Resolved at implement: the plan's first step writes a
  machine-local change-set file (`.work/tickets/L-0532/changesets-sql.txt`, never committed) with one line per
  counted change set and per rejected lead. The admitted list in the tests is copied from it.
- **Change-set names in a public file.** The tests need each standard's `Change sets` names to appear in its Earned
  by. Default: opaque labels (for example `pr-a`, `pr-b`), each Earned by bullet describing its defect and round
  without identifying detail; the label-to-source mapping stays in the machine-local file. The reviewer is told.
- **What counts as review-recorded.** `python.md`'s rule, read strictly: a fix commit inside a reviewed ticket whose
  message does not record that a review found this defect is not counted; an unreadable body is `unknown`.
- **Doc quotes.** Resolved at implement: every Source URL fetched raw, tags stripped, whitespace collapsed, each
  quoted sentence string-matched, recorded in `.work/tickets/L-0532/quote-check-sql.txt` with the version banner.
  A miss is replaced by the page's current sentence or dropped, never paraphrased.
- **In-flight tickets with `.sql` changes** get a stale stamp after merging main and add the SQL rows by hand.
  Accepted; flagged in CHANGELOG and the PR body.
- **A cloud session without the research or the private repos** cannot do the evidence step and must stop and say so.

## Size and split
One new Markdown set (estimate 300-600 lines), about 40 lines in `stack-sql` (at most 120), four new tests and one
findings table in `test_crew_standards.py`, doc rows. No production code. Sabotage entries split out. No further split.

## Touch
- `plugin/crew/skills/crew-standards/references/sql.md` - new, the SQL set
- `plugin/crew/skills/crew-standards/SKILL.md` - the stack-sets bullet names the SQL set
- `plugin/crew/skills/stack-sql/SKILL.md` - `## Standards` pointer, `## Candidate standards (not gated)`, description
- `plugin/crew/tests/test_crew_standards.py`
- `plugin/crew/README.md`
- `plugin/PLUGINS.md` - crew-standards and stack-sql rows; the version row at land
- `plugin/crew/BUDGETS.md`
- `CHANGELOG.md`
- `plugin/crew/.claude-plugin/plugin.json` - version, land branch only
- `.claude-plugin/marketplace.json` - version, land branch only
- `.crew/codemap/crew.md` - the stack-set sentence; re-anchor
- `.crew/codemap/**` - re-anchor only
- `.claude/rules/**` - regenerate only
- `graphify-out/**` - `graphify update .` only
- `docs/diagrams/**` - re-anchor only if made stale
- `docs/tickets/L-0532/` - removed in the final PR unless the owner wants it kept

Not in Touch: `plugin/crew/tests/sabotage_standards.py`, `.crew/verify.json`, `crew_standards.py`,
`docs/guides/crew/**`, `plugin/crew/commands/implement.md`.

## Acceptance checks
Commands from the repo root; pytest through `/root/crew-tmp/heavy-run` on a memory-bound host.
`T` is `plugin/crew/tests/test_crew_standards.py`.
- [ ] The machine-local `.work/tickets/L-0532/changesets-sql.txt` covers SQL-01..SQL-20 (counted change sets and
  rejected leads): `grep -c '^SQL-' .work/tickets/L-0532/changesets-sql.txt` is at least 20.
- [ ] `references/sql.md` parses with no problems, set `SQL`, `applies-to` `["**/*.sql"]`, ids exactly the admitted
  list, in id order. New `test_sql_set_parses_with_every_field`:
  `python3 plugin/crew/tests/pytest_rule.py T -q -k test_sql_set_parses_with_every_field`
- [ ] Every SQL standard names and cites three change sets and its Why states the count (existing tests):
  `python3 plugin/crew/tests/pytest_rule.py T -q -k "stack_standard and sql.md"`
- [ ] Why finding counts match a hand-counted `_SQL_FINDINGS` table. New
  `test_sql_why_finding_counts_match_their_enumerations`: `python3 plugin/crew/tests/pytest_rule.py T -q -k test_sql_why_finding_counts`
- [ ] No Source quote elided with `[...]`. New `test_sql_sources_quote_whole_spans_without_elision`:
  `python3 plugin/crew/tests/pytest_rule.py T -q -k test_sql_sources_quote`
- [ ] The set applies to `.sql` files only: `SQL` in `effective_set(<root>, [f])["sets"]` for
  `db/migrations/0001_init.sql` and `schema.sql`, not for `README.md`, `app/Repo.cs`, `lib/Orders.php` or
  `data.sqlite`. New `test_sql_set_applies_to_sql_files_only`: `python3 plugin/crew/tests/pytest_rule.py T -q -k test_sql_set_applies`
- [ ] Engine-specific standards name their engine first:
  `grep -nE '^## SQL-(1[5-9]|20) (MySQL/MariaDB|SQL Server|PostgreSQL):' plugin/crew/skills/crew-standards/references/sql.md`
  lists every shipped id from SQL-15 to SQL-20.
- [ ] Nothing machine-local is cited (existing tests): `python3 plugin/crew/tests/pytest_rule.py T -q -k "cite_nothing_local or machine_local"`
- [ ] No private identifying detail in any changed file: a grep of `git diff origin/main...HEAD` for the private
  repository and client names the coordinator holds returns nothing (the coordinator supplies the pattern).
- [ ] `.work/tickets/L-0532/quote-check-sql.txt` shows every Source quote found verbatim in the raw page.
- [ ] Each new test proven red by hand, one mutation at a time on `sql.md`, file restored byte-identical (`cmp`),
  recorded in `.work/tickets/L-0532/notes.md`; these four become the follow-up's `STANDARDS_MUTATIONS`: `applies-to`
  narrowed to `["**/*.psql"]` (red `test_sql_set_applies_to_sql_files_only`); a Change sets line cut to two names
  (red `test_every_stack_standard_names_and_cites_three_change_sets[sql.md]`); a candidate id in place of an
  admitted heading (red `test_sql_set_parses_with_every_field`); a Why count off by one (red
  `test_sql_why_finding_counts_match_their_enumerations`).
- [ ] `stack-sql/SKILL.md` names `crew-standards/references/sql.md`, lists the admitted ids, lists every other SQL-NN
  as a candidate with its change-set count and "promoted when a third reviewed change set earns it", within budget:
  `python3 plugin/crew/tests/pytest_rule.py plugin/crew/tests/test_stack_skills.py -q`
- [ ] Docs in the same PR: `crew-standards/SKILL.md`, `plugin/crew/README.md:795`, `plugin/PLUGINS.md` rows,
  `.crew/codemap/crew.md`, `CHANGELOG.md` `[Unreleased]` entry with a **Behaviour change** line, `BUDGETS.md`
  re-measured. `python3 scripts/check-marketplace.py` exits 0 after commit.
- [ ] The crew-standards verify rule passes:
  `python3 plugin/crew/tests/pytest_rule.py plugin/crew/tests/test_crew_standards.py plugin/crew/tests/test_review_run_standards.py plugin/crew/tests/test_review_prompt.py plugin/crew/tests/test_review_run_launch.py plugin/crew/tests/test_review_ledger.py plugin/crew/tests/test_lifecycle_commands.py plugin/crew/tests/test_review_receipt.py plugin/crew/tests/test_webtest_guard.py -q`
- [ ] `python3 scripts/check-tooling-pr.py` exits 0 ("no harness path changed").
- [ ] Refresh artifacts fresh: `python3 plugin/crew/hooks/scripts/crew_instructions.py rules --root . --check` and
  `python3 plugin/crew/hooks/scripts/crew_refresh_check.py --root . --ticket L-0532` pass.
- [ ] Full crew suite and lint: `python3 plugin/crew/tests/pytest_rule.py plugin/crew/tests/ -q`,
  `python3 -m pylint -j 4 $(git ls-files "*.py")`, `python3 /root/crew-tmp/ruff-no-new.py <worktree>` exit 0.
- [ ] L-0532's own self-check: `crew_standards.py init` then `stamp --root . --ticket L-0532` exit 0.
- [ ] At land: crew version one past origin/main's in `plugin/crew/.claude-plugin/plugin.json`,
  `.claude-plugin/marketplace.json`, `plugin/PLUGINS.md` and the CHANGELOG heading.

## Dependencies
- T-0086 (Python): merged (#282). Done.
- L-0539: not merged; decides only whether the sabotage entries ride here or in the follow-up.
- Merge train: L-0533, L-0534 and L-0535..L-0538 edit the same shared lines (`crew-standards/SKILL.md`,
  `README.md:795`, `PLUGINS.md:217`, `crew.md`, `test_crew_standards.py`, BUDGETS, CHANGELOG); one at a time.
- Follow-up: a tooling-only ticket for the four sabotage entries (unless L-0539 first).

## Approval
Direction and spec approved for cloud hand-off by the orchestrator under the owner's standing self-approve authority, 2026-10-05. Plan: to be written by the implementing session.

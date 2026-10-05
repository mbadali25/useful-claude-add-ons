# L-0532: SQL development standards set (MySQL/MariaDB, SQL Server, PostgreSQL), T-0086 slice 2          status: spec   risk: medium
Written against origin/main `a555ff37` (crew 1.1.0). Every `path:line` below is at that commit unless it names a branch.

## Intent
Ship the second per-language standards set on T-0085's mechanism, unchanged:
`plugin/crew/skills/crew-standards/references/sql.md`, set `SQL`, `applies-to: ["**/*.sql"]`, holding the SQL
standards from `.work/tickets/T-0086/research/sql.md` that findings from at least three distinct reviewed change
sets earn, counted the way `python.md`'s lead paragraph counts them. Because the research's own citations earn no
rule on that count, the slice starts with a bounded evidence step: every cited commit opened, plus a per-rule search
of the owner repositories' review-recorded fix commits, each classified by hand. Each shipped standard keeps its
Earned by citations and its official-doc Source, re-read from the raw page. Rules that fall short are listed as
candidates in `stack-sql`, which also points at the set. One file covers every engine; engine-specific rules name
their engine in the heading.

## Exclusions
- No change to the loader, gate, stamp or checklist: `crew_standards.py`, `review_run.py`, `review_prompt.py` and
  `crew_ticket.py` are not touched. A stack set is a new file in `references/` (`crew_standards.py:236-262`).
- **No edit to `plugin/crew/tests/sabotage*.py`.** It is a `HARNESS` path (`scripts/check-tooling-pr.py:79`) and
  L-0539, which would let a feature's own sabotage entries ride along, has not landed. The mutations listed under
  Acceptance go in a follow-up tooling-only PR (the coordinator mints its id), unless L-0539 has merged first, in
  which case they ride here and the PR says so. This PR proves each new test red by a hand-run mutation.
- No rename of an existing test. Sabotage entries name tests by node id (`sabotage_standards.py:61` onwards), so a
  rename is a harness change.
- No other stack, and no PHP or C# glob in `applies-to` (direction, "applies-to").
- No candidate standard in `sql.md` or in this repository's `.crew/standards.md` overlay.
- No machine-local citation in the shipped set: no `.work/` path, no `Fnnn` id, no vault note, no auto-memory, no
  `/repos/` path, no `TheSelectSource/.work/FINDINGS.md` line, no repository `CLAUDE.md` line
  (`test_shipped_sets_cite_nothing_local_only` `plugin/crew/tests/test_crew_standards.py:247`,
  `test_shipped_sets_cite_no_machine_local_note` `:381`).
- No `.crew/verify.json` change: `plugin/crew/skills/crew-standards/**` and `test_crew_standards.py` are already in
  the crew-standards rule (rule 41 by position, paths `.crew/verify.json:484-485`, run `:494`).
- No hook and no config key, so `plugin/crew/CONFIG.md` is unchanged. Docs: none there.
- No guide change (`docs/guides/crew/src/*.md` and the built HTML, DOCX, PDF): they say "any per-language set a
  changed file matches" and name no set. Docs: none there, for that reason. No ADR (ADR 0004 decision 3 already
  covers further set files). No diagram: no process or node changes.
- No `/crew:implement` edit: `implement.md:77` already loads `stack-sql` for migration and schema work.
- No version bump on the build branch (REPO-03 in `.crew/standards.md`): the version is set on the land branch.

## Evidence
- Direction: `docs/tickets/L-0532/direction.md` (this branch) and T-0086's approved direction,
  `.work/tickets/T-0086/direction.md` ("Admission bar": a doc is Source, not a change set; "Each slice must count
  change sets for every rule").
- The worked example, landed in #282 (`549cda24`): `plugin/crew/skills/crew-standards/references/python.md`
  (lead paragraph states the counting rule; nine standards; `**Change sets.** 3: main(T1-T4), crew-1.0.13, T-0002`
  is the line shape), `plugin/crew/skills/stack-python/SKILL.md:46-86` (`## Standards`, `## Candidate standards
  (not gated)`), `CHANGELOG.md:3815` (its entry), T-0086's spec and plan in `.work/tickets/T-0086/`.
- Loader: `plugin/crew/hooks/scripts/crew_standards.py:76` `PLUGIN_FIELDS` (Rule, Why, Applies when, Self-check,
  Earned by, Change sets); `:83` `_ID_RE` `^[A-Z]{2,6}-\d{2}$` (so `SQL-01` is valid); `:175-199` a `## ` line that
  is neither a standard nor Supplements is a problem; `:222` a file with no standard is a problem; `:229` `_applies`
  through `crew_ticket.glob_match` (`crew_ticket.py:393`); `:236` `_plugin_sets` reads every `references/*.md`;
  `:263` `effective_set`.
- Existing tests that will cover `sql.md` with no edit, because they parametrize over every non-generic set
  (`_STACK_SETS`, `test_crew_standards.py:261`): `test_every_stack_standard_names_and_cites_three_change_sets`
  `:292` (N >= 3, N equals the names, no repeat, three cited in Earned by as `- <name> ` or `` `<name>` ``),
  `test_every_stack_standard_why_states_its_change_set_count` `:307` (Why says `N findings across M change sets`),
  `test_every_stack_set_line_count_is_the_same_by_newline_and_splitlines` `:349`. Python-only tests to mirror:
  `test_python_set_parses_with_every_field` `:264`, `test_python_why_finding_counts_match_their_enumerations`
  `:336` (table `_PYTHON_FINDINGS` `:330`), `test_python_sources_quote_whole_spans_without_elision` `:359`,
  `test_python_set_applies_to_python_files_only` `:372`.
- Sabotage pattern (for the follow-up): `plugin/crew/tests/sabotage_standards.py:59` `PYTHON_SET`, `:61`
  `STANDARDS_MUTATIONS`, the PYTHON entries at `:434-489`.
- Harness: `scripts/check-tooling-pr.py:58-87` `HARNESS` includes `plugin/crew/tests/sabotage*.py` (`:79`). L-0539
  is `direction` in `.work/INDEX.md`; `gh pr list --search L-0539` shows no PR (2026-10-05).
- Research: `.work/tickets/T-0086/research/sql.md`, 20 rules: general SQL-01 `:42` to SQL-14 `:427`; MySQL/MariaDB
  SQL-15 `:455`, -16 `:483`; SQL Server SQL-17 `:513`, -18 `:546`; PostgreSQL SQL-19 `:579`, -20 `:608`. Owner
  evidence per rule is the `- Owner:` line under each `**Evidence:**` tag. Its admission note `:724-731` counted
  vault notes and FINDINGS.md lines. Doc quotes came through WebFetch or Microsoft Learn search excerpts and were
  never checked raw (`:709-711`).
- **Pre-count on the research's citations (2026-10-05, subjects read with `git -C /repos/anew/<repo> show -s`).**
  Y = the commit's message records a review round or finding; N = it does not; ? = the body needs reading.
  A ticket counts once. Vault notes, `CLAUDE.md` lines and FINDINGS.md are not counted.
  SQL-01: TSS-143 (`9297b408` ?), SRL-1448 (`5ba1a11b` Y "close Codex round-2 BLOCK") = at most 2.
  SQL-02: TSS PR #552 (`417a9649` Y "round 9") = 1. SQL-03: TSS-143 (`a9619a50` Y "codex round 3") = 1.
  SQL-04: THDDEV-1140 (`63e7dbbb` ?), SRL-1302 (`292c7b6b` N), TSS PR #587 (`c1cdf5d3` N, a release commit) = 0-3.
  SQL-05: SRL-1293 (`b52959f3` N) = 0-1. SQL-06: SRL-1449 (`62377ba4`, `650e4ecb` Y, one ticket) = 1.
  SQL-07: SRL-1449 (`943593f7` Y) = 1. SQL-08: THDDEV-1169 (`ccd31e8e` ?, cites a DBA review doc) = 0-1.
  SQL-09: SRL-1464 (`cf153022` Y), SRL-1491 (`27bf22ff` N), Vault (`e315d61` Y "Codex merge-gate BLOCK") = 2-3.
  SQL-10: SRL-1437 (`08691f7b` N) = 0-1. SQL-11: SRL-1302 (N), THDDEV-1140 (`417b7372` Y), Vault (`096aa90` N) = 1-3.
  SQL-12: Vault (`e315d61` Y) = 1. SQL-13: Vault (`096aa90` N), SRL-1302 (N), SRL-1293 (`01fcc742` Y) = 1-3.
  SQL-14: SRL-1293 (`604d410d`, `8a1f2fed` Y) = 1. SQL-15: TSS migration 039 (`67753934` ?) = 0-1. SQL-16: 0.
  SQL-17: SRL-1293 (Y), SRL-1491 (N) = 1-2. SQL-18: SRL-1437 (N), SRL-1302 (N), SRL-1449 (Y) = 1-3.
  SQL-19: THDDEV-1169 (?) = 0-1. SQL-20: Vault (`4be4ff6` N feat, `a21523c` N feat, `e315d61` Y) = 1.
  On the strict reading no rule reaches three; counting every cited ticket, SQL-04, -09, -11, -13 and -18 reach three.
- **Leads for the evidence step (not counted).** Review-recorded fix-commit subjects (`git log --all --no-merges`
  matching `codex|gate r[0-9]|round|BLOCK|FIX`): 1624 in SRL, 2999 in TheSelectSource, 488 in TheHomeDepot, 94 in
  Vault. A keyword pass per rule found, for example, SQL-01: SRL-887, SRL-1292, SRL-1491; SQL-02: SRL-1350,
  SRL-1220, SRL-933; SQL-06: SRL-1458, SRL-1535, SRL-1443, SRL-1585; SQL-10: SRL-1361, SRL-941; SQL-11: SRL-1443,
  SRL-941, SRL-715, SRL-565; SQL-12: SRL-1632, SRL-1587; SQL-15: SRL-1392, SRL-1443, SRL-941; SQL-19: SRL-1443,
  SRL-581. None was opened. Keyword hits include unrelated commits.
- Stack skill: `plugin/crew/skills/stack-sql/SKILL.md` is 90 lines; sections `## When this applies` `:12`,
  `## Pitfalls that cost time (all three engines)` `:20`, `## Per-engine locking and isolation` `:35`,
  `## Verification` `:64`, `## verify.json rule to propose` `:71`, `## LSP` `:88`. Stack skills are capped at 120
  lines (`plugin/crew/tests/test_stack_skills.py:142`).
- Docs that describe the sets: `plugin/crew/skills/crew-standards/SKILL.md:17-21` ("The first is
  `references/python.md` ... the other stacks follow"); `plugin/crew/README.md:795` ("The other stacks (SQL, PHP,
  ...) follow as further files"); `plugin/PLUGINS.md:217` (crew-standards row, "(Python so far)") and `:223`
  (stack-sql row); `.crew/codemap/crew.md:1830-1831` ("The first stack set is ... python.md"); `plugin/crew/BUDGETS.md:10-11`
  (`crew-markdown-lines` claim, checked by `check_self_claims`); `CHANGELOG.md:10` `[Unreleased]`.

## Unknowns
- **Which rules ship.** Decided by the evidence step, not here. The pre-count says none on the research alone; the
  leads say several rules probably reach three once their commits are opened. Resolved at implement: the plan's
  first step writes `.work/tickets/L-0532/changesets-sql.txt`, one line per counted change set (rule, repository,
  ticket or PR, round, sha, quoted subject, why it counts) and one line per rejected lead (why not). The admitted
  list in the tests is copied from it.
- **What counts as review-recorded.** Taken from `python.md`'s lead: a crew review, or a fix commit whose message (or
  the repository's changelog entry for it) records that a review found the defect. A fix commit inside a ticket that
  had review rounds, whose own message does not say a review found this defect, is not counted. Accepted as the
  strict reading; the reviewer is told. A body that cannot be read is `unknown` and not counted.
- **Private repositories.** SRL, TheSelectSource, TheHomeDepot and Vault are private. Citations name the repository,
  the ticket or PR, the round and the sha, and quote the subject, as `python.md` cites TheHomeDepot. Accepted.
- **Vault commits have no ticket id.** A Vault commit counts as its own change set only when its message names a
  distinct review round (for example `e315d61` "Task 10b, fix round 2 (Codex merge-gate BLOCK, ruling R30)"); two
  rounds of the same task count once.
- **Doc quotes.** All were summarised. Resolved at implement: every Source URL is fetched raw (`curl -sL`), tags
  stripped, whitespace collapsed, and every quoted sentence string-matched, recorded in
  `.work/tickets/L-0532/quote-check-sql.txt` with the page's version banner. A miss is replaced by the page's
  current sentence or the Source line is dropped, never paraphrased. Microsoft Learn pages that render the sentence
  only client-side are fetched through the Learn MCP `microsoft_docs_fetch` and say so.
- **In-flight tickets with `.sql` changes** get a new digest after merging main, so their stamp goes stale and the
  SQL rows are added by hand (`init` never overwrites). Accepted; flagged in CHANGELOG and the PR body.

## Size and split
One new Markdown set (estimate 300-600 lines, depending on how many rules ship), about 40 lines in `stack-sql`
(kept at or under 120), four new tests and one findings table in `test_crew_standards.py`, doc rows. No production
code. The sabotage entries are split out to a tooling-only follow-up (Exclusions). No further split: one stack, one
reviewable file.

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
- `docs/diagrams/**` - re-anchor only if this change made one stale
- `docs/tickets/L-0532/` - removed in the final PR unless the owner wants it kept

Not in Touch: `plugin/crew/tests/sabotage_standards.py` (harness; follow-up), `.crew/verify.json`, `crew_standards.py`,
`docs/guides/crew/**`, `plugin/crew/commands/implement.md`.

## Acceptance checks
Commands from the repo root; pytest through `/root/crew-tmp/heavy-run` on a memory-bound host.
`T` is `plugin/crew/tests/test_crew_standards.py`.
- [ ] `.work/tickets/L-0532/changesets-sql.txt` exists and, for every one of SQL-01..SQL-20, lists each counted
  change set with repository, ticket or PR, round, sha and quoted subject, and each rejected lead with the reason.
  `grep -c '^SQL-' .work/tickets/L-0532/changesets-sql.txt` is at least 20.
- [ ] `references/sql.md` parses with no problems, set `SQL`, `applies-to` `["**/*.sql"]`, ids exactly the admitted
  list from `changesets-sql.txt`, in id order. New `test_sql_set_parses_with_every_field`:
  `python3 plugin/crew/tests/pytest_rule.py T -q -k test_sql_set_parses_with_every_field`
- [ ] Every SQL standard names at least three change sets and cites three in Earned by, and its Why states
  `N findings across M change sets` with M equal to its Change sets count (existing parametrized tests, no edit):
  `python3 plugin/crew/tests/pytest_rule.py T -q -k "stack_standard and sql.md"`
- [ ] The Why finding counts match a hand-counted table `_SQL_FINDINGS`. New
  `test_sql_why_finding_counts_match_their_enumerations`:
  `python3 plugin/crew/tests/pytest_rule.py T -q -k test_sql_why_finding_counts`
- [ ] No Source quote is elided with `[...]`. New `test_sql_sources_quote_whole_spans_without_elision`:
  `python3 plugin/crew/tests/pytest_rule.py T -q -k test_sql_sources_quote`
- [ ] The set applies to `.sql` files only: `effective_set(<root>, [f])["sets"]` contains `SQL` for
  `db/migrations/0001_init.sql` and `schema.sql`, and not for `README.md`, `app/Repo.cs`, `lib/Listings.php` or
  `data.sqlite`. New `test_sql_set_applies_to_sql_files_only`:
  `python3 plugin/crew/tests/pytest_rule.py T -q -k test_sql_set_applies`
- [ ] Engine-specific standards name their engine first in the heading (`MySQL/MariaDB:`, `SQL Server:`,
  `PostgreSQL:`), and the lead paragraph lists the ids per engine:
  `grep -nE '^## SQL-(1[5-9]|20) (MySQL/MariaDB|SQL Server|PostgreSQL):' plugin/crew/skills/crew-standards/references/sql.md`
  lists every shipped id from SQL-15 to SQL-20.
- [ ] Nothing machine-local is cited (existing tests): `python3 plugin/crew/tests/pytest_rule.py T -q -k "cite_nothing_local or machine_local"`
- [ ] `.work/tickets/L-0532/quote-check-sql.txt` shows every Source quote in `sql.md` found verbatim
  (whitespace-normalised) in the raw page, with the page's version banner.
- [ ] Each new test is proven red by hand: the four mutations below, applied one at a time to `sql.md`, turn their
  named test red, and the file is restored byte-identical (`cmp` against a copy). Recorded in
  `.work/tickets/L-0532/notes.md`; the same four are the follow-up tooling ticket's `STANDARDS_MUTATIONS` entries:
  `applies-to` narrowed to `["**/*.psql"]` (red `test_sql_set_applies_to_sql_files_only`); one standard's Change
  sets cut to two names (red `test_every_stack_standard_names_and_cites_three_change_sets[sql.md]`); a candidate id
  in place of an admitted heading (red `test_sql_set_parses_with_every_field`); one Why's finding count off by one
  (red `test_sql_why_finding_counts_match_their_enumerations`).
- [ ] `stack-sql/SKILL.md` names `crew-standards/references/sql.md`, lists the admitted ids one line each, lists
  every other SQL-NN as a candidate with its change-set count and "promoted when a third reviewed change set earns
  it", and stays within budget: `python3 plugin/crew/tests/pytest_rule.py plugin/crew/tests/test_stack_skills.py -q`
- [ ] Docs in the same PR: `crew-standards/SKILL.md` stack-sets bullet, `plugin/crew/README.md:795`,
  `plugin/PLUGINS.md` rows, `.crew/codemap/crew.md` stack-set sentence, `CHANGELOG.md` `[Unreleased]` entry with a
  **Behaviour change** line (a change touching a `.sql` file now answers the SQL rows; in-flight stamps go stale),
  `BUDGETS.md` re-measured. `python3 scripts/check-marketplace.py` exits 0 after commit.
- [ ] The crew-standards verify rule passes:
  `python3 plugin/crew/tests/pytest_rule.py plugin/crew/tests/test_crew_standards.py plugin/crew/tests/test_review_run_standards.py plugin/crew/tests/test_review_prompt.py plugin/crew/tests/test_review_run_launch.py plugin/crew/tests/test_review_ledger.py plugin/crew/tests/test_lifecycle_commands.py plugin/crew/tests/test_review_receipt.py plugin/crew/tests/test_webtest_guard.py -q`
- [ ] `python3 scripts/check-tooling-pr.py` exits 0 ("no harness path changed").
- [ ] Refresh artifacts fresh: `python3 plugin/crew/hooks/scripts/crew_instructions.py rules --root . --check` and
  `python3 plugin/crew/hooks/scripts/crew_refresh_check.py --root . --ticket L-0532` pass.
- [ ] Full crew suite and lint: `python3 plugin/crew/tests/pytest_rule.py plugin/crew/tests/ -q`,
  `python3 -m pylint -j 4 $(git ls-files "*.py")`, `python3 /root/crew-tmp/ruff-no-new.py <worktree>` exit 0.
- [ ] L-0532's own self-check: `crew_standards.py init` then `stamp --root . --ticket L-0532` exit 0, every row
  answered (the change touches `.py` tests, so PYTHON rows apply; no `.sql` file changes, so SQL rows do not).
- [ ] At land: crew version one past origin/main's in `plugin/crew/.claude-plugin/plugin.json`,
  `.claude-plugin/marketplace.json` and `plugin/PLUGINS.md`, and in the CHANGELOG heading.

## Dependencies
- T-0086 (Python slice): merged (#282). Sets the format, tests and counting rule. Done.
- L-0539 (check-tooling-pr): not merged. Not blocking; it decides only whether the sabotage entries ride here or in
  the follow-up tooling-only PR.
- Merge train: L-0533 (PHP), L-0534 (PowerShell) and L-0535..L-0538 each edit `crew-standards/SKILL.md`,
  `test_crew_standards.py`, `README.md:795`, `PLUGINS.md:217`, `crew.md`'s stack-set sentence, BUDGETS.md and
  CHANGELOG. They land one at a time; whichever lands second merges main and re-words those shared lines.
- Follow-up: a tooling-only ticket for the four sabotage entries, minted by the coordinator after this lands (unless
  L-0539 merged first).

## Approval
Direction and spec approved for cloud hand-off by the orchestrator under the owner's standing self-approve authority, 2026-10-05. Plan: to be written by the implementing session.

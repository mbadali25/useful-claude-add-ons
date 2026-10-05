# L-0533: PHP development standards set and a new stack-php skill, T-0086 slice 3          status: spec   risk: medium
Written against origin/main `a555ff37` (crew 1.1.0). Every `path:line` below is at that commit unless it names
another repository. TheSelectSource (TSS) lines are at its local HEAD `b853583a`.

## Intent
Ship the PHP per-language standards set on T-0085's mechanism, unchanged:
`plugin/crew/skills/crew-standards/references/php.md`, set `PHP`, `applies-to: ["**/*.php", "**/*.phtml"]`,
holding the standards from `.work/tickets/T-0086/research/php.md` that findings from at least three distinct
reviewed change sets earn, counted the way `python.md`'s lead paragraph counts them. The research leaned on vault
notes, so the slice starts with an evidence step that opens every cited commit and verdict and mines TSS's review
records per rule. Each shipped standard keeps its Earned by citations and an official-doc Source re-read from the
raw page. Add a new, short `stack-php` skill (pitfalls the set does not gate, a pointer to the set, the candidates,
a `php -l` verify rule), registered in every place a crew skill or skill count is stated.

## Exclusions
- No change to `crew_standards.py`, `review_run.py`, `review_prompt.py` or `crew_ticket.py`.
- **No edit to `plugin/crew/tests/sabotage*.py`** (`HARNESS`, `scripts/check-tooling-pr.py:79`; L-0539 not landed).
  The mutations under Acceptance go in a follow-up tooling-only PR, unless L-0539 merged first. No rename of any
  existing test (sabotage entries name tests by node id).
- No framework-specific rule in the plugin set (Cube `mods/` precedence, `_prepareData` metadata cache,
  `Cube\View::__call`, the Cube paginator's 0, TSS paths): those belong in TSS's own overlay, not written here.
- No candidate standard in `php.md` or in this repository's `.crew/standards.md`.
- No machine-local or forbidden citation in the shipped set: no `.work/` path, no `\bF\d{3}\b` token (so no
  `F551-A`, `F556`, `F575`; cite the PR, ticket and sha), no vault note, no `/repos/` path, no TSS `CLAUDE.md` line,
  no untracked file (`test_crew_standards.py:247-255`, `:381`).
- No install-script change: `stack-php`'s verify rule exits 77 when `php` is missing, so neither
  `scripts/install-prerequisites.sh` nor `.ps1` installs PHP or a PHP linter. The pair stays untouched.
- No `marketplace.json` entry for the skill: crew-bundled skills are not registered separately; only the crew
  entry's description count changes.
- No `/crew:implement` edit; no hook; no config key (CONFIG.md unchanged; Docs: none there). No guide change: the
  guides name no set and no stack skill list (Docs: none there). No ADR. No diagram.
- No `.crew/verify.json` change: `plugin/crew/skills/**` is already in the validate-prompts rule
  (`.crew/verify.json:275`) and `crew-standards/**` in the crew-standards rule (`:484-485`).
- No version bump on the build branch (REPO-03); set on the land branch.

## Evidence
- Direction: `docs/tickets/L-0533/direction.md`; T-0086's approved direction `.work/tickets/T-0086/direction.md`
  ("Admission bar"; "Stack skill: new stack-php").
- Worked example (#282): `references/python.md` (lead paragraph and counting rule, field order, Earned-by forms),
  `plugin/crew/skills/stack-python/SKILL.md:46-86`, `CHANGELOG.md:3815`.
- Loader: `crew_standards.py:76` `PLUGIN_FIELDS`; `:83` `_ID_RE` (`PHP-01` valid); `:175-199` stray `## ` is a
  problem; `:222` empty set is a problem; `:229` `_applies`; `:236` `_plugin_sets`; `:263` `effective_set`.
- Tests that cover `php.md` with no edit (`_STACK_SETS` `test_crew_standards.py:261`): `:292`, `:307`, `:349`;
  forbidden tokens `:250` (`\.work/|\bF\d{3}\b`) and `:381-390`. Python-only tests to mirror: `:264`, `:336`
  (`_PYTHON_FINDINGS` `:330`), `:359`, `:372`.
- Stack-skill contract: `plugin/crew/tests/test_stack_skills.py:62-71` `STACK_NAMES`, `:79-88` `_TRIGGER_TERMS` (one lowercased term per skill), `:74` `MIN_DESCRIPTION_LEN` 80,
  `:128` every listed skill exists, `:133` no unlisted `stack-*` directory, `:142` at most 120 lines, `:151`
  front matter `name` and a `description` naming the stack, `:175-203` at least one fenced ```json rule with `paths`
  and `run` lists, `:205` every command carries `exit 77` and `TOOL MISSING`, `:288` each command really exits 77
  with only `sh`/`bash` on `PATH`. Model rule: `plugin/crew/skills/stack-sql/SKILL.md:71-86` (sqlfluff).
- Crew skill count 31, checked by `check_self_claims` (`scripts/check-marketplace.py:761`) at each
  `<!-- claim: plugin-skills:crew -->`: `README.md:168`, `README.md:399`, `INSTALLATION.md:253`,
  `plugin/README.md:414`, `plugin/PLUGINS.md:17`. Unmarked mentions: `.claude-plugin/marketplace.json:223` (crew
  description "31 bundled skills"), `.crew/codemap/crew.md:58` and its stack-skill list `:78-81`,
  `.crew/codemap/marketplace-registration.md:61`, `:68`, `.crew/codemap/install-scripts.md:237`.
- Rows to add or change: `plugin/PLUGINS.md:217` (crew-standards, "(Python so far)"); a new `stack-php` row between
  `stack-dotnet` `:220` and `stack-powershell` `:221`. `plugin/crew/README.md:795` ("The other stacks (SQL, PHP, ...)
  follow"); `plugin/crew/skills/crew-standards/SKILL.md:17-21`; `.crew/codemap/crew.md:1830-1831`;
  `plugin/crew/BUDGETS.md:10-11` (`crew-markdown-lines`, a new `.md` file moves both numbers); `CHANGELOG.md:10`.
- Harness: `scripts/check-tooling-pr.py:58-87`; L-0539 `direction`, no PR (2026-10-05).
- Research: `.work/tickets/T-0086/research/php.md`, 20 rules, PHP-01 `:61` to PHP-20 `:932`; overlap with stack-sql
  `:17-24`; left-out candidates `:1028-1038`; `applies-to` proposal `:1042`; docs fetched through WebFetch, never
  checked raw (`:1050`, `:1089-1090`).
- **Pre-count on the research's citations (2026-10-05).** A citation counts when it is a review record of a finding
  (a TSS verdict file's BLOCK or FIX, or a commit whose subject or body records the review round) for a distinct
  ticket or PR. Not counted: vault notes (they name tickets, which are leads), TSS `CLAUDE.md` lines, clean audits
  that found nothing (`pr-278.md:147`, `pr-193-2.md:27`), and docs commits.
  PHP-01: 0 (leads TSS-143, TSS-171). PHP-02: PR #590 adversarial FIX, PR #283 r2, `bdcabf64` post-#562 security
  record (docs commit, ?) = 2-3. PHP-03: 0 (leads TSS-128, TSS-149, TSS-25). PHP-04: checkout mass-assignment
  investigation verdict = 1 (lead TSS-78). PHP-05: `016c5daf` TSS-345 / PR #385 (?), `pr-189-2.md:31` (?) = 0-2.
  PHP-06: `22caa57b` PR for ShipStation rates, "BLOCK" in body = 1 (leads TSS-40, TSS-104). PHP-07: PR #632
  adversarial, `59b82d70` and `85136cc8` (both TSS-523, rounds 3 and 5, one ticket) = 2. PHP-08: `37c75812` (PR
  #542 release, ?) = 0-1 (leads TSS-78 PR #70, PR #115). PHP-09: `f303a335` (round 2, PR #552) = 1. PHP-10: 0
  (lead TSS-116 PR #118). PHP-11: 0 (leads TSS-26, TSS-27). PHP-12: 0. PHP-13: PR #382 BLOCK = 1 (leads TSS-149,
  TSS-345). PHP-14: `f303a335` = 1. PHP-15: `81a965d7` is a docs(todo) commit = 0. PHP-16: `22caa57b`, PR #381 FIX =
  2. PHP-17: PR #393 FIX = 1. PHP-18: PR #187 blocking = 1. PHP-19: 0. PHP-20: PR #481 FIX, PR #414 FIX, PR #601
  merge `ab4e2a9f` (?) = 2-3. So on the research alone at most PHP-02 and PHP-20 reach three.
- Three cited verdict files are untracked in TSS (`git ls-files` empty, present on disk):
  `pr-590-24950f0c-codex-adversarial.md`, `pr-632-5b26e731-codex-adversarial.md`,
  `pr-481-0ffbe635-standard.md`. TSS tracks 645 verdict files under `.codex-verdicts/` at `b853583a`.
- Leads: 2999 TSS non-merge commits whose subject matches `codex|gate r[0-9]|round|BLOCK|FIX` (2026-10-05).

## Unknowns
- **Which rules ship.** Decided by the evidence step. Resolved at implement: the plan's first step writes
  `.work/tickets/L-0533/changesets-php.txt` (rule, ticket or PR, round, sha or verdict path, quoted line, why it
  counts; and each rejected lead with the reason). The tests' admitted list is copied from it.
- **Untracked verdict files.** A review recorded only in an untracked file is still a review of that PR. Default: it
  counts, cited as `TheSelectSource PR #590 (Codex adversarial review)` with the quote, never by its path. If the
  same finding is in a tracked verdict or a commit, cite that instead. Accepted as risk; the reviewer is told.
- **What counts as review-recorded** is `python.md`'s rule (see L-0532's spec for the strict reading); a TSS ticket
  with review rounds counts once however many commits it has.
- **One repository.** All counted change sets are TSS. Accepted (direction); the lead paragraph says so.
- **Doc quotes.** All came through WebFetch. Resolved at implement: raw fetch and string match per quote, recorded
  in `.work/tickets/L-0533/quote-check-php.txt` with the php.net page's last-updated line; misses replaced or
  dropped, never paraphrased. The OWASP File Upload quotes are known to be paraphrased (`research/php.md:1090`).
- **`php -l` on the test host.** `test_missing_tool_branch_actually_exits_77_for_real` runs the rule with `PATH`
  stripped, so it passes whether or not PHP is installed. Whether the rule passes on real PHP is measured only if
  `php` is on the implementing host; the PR says which.
- **In-flight tickets with `.php` changes** get stale stamps after merging main. Accepted; CHANGELOG and PR body say so.

## Size and split
One new Markdown set (estimate 300-600 lines), one new skill of at most 120 lines, four new tests and a findings
table in `test_crew_standards.py`, two lines in `test_stack_skills.py`, five checked count claims plus the
unmarked mentions, doc rows. No production code. Sabotage entries split out (Exclusions). No further split: the
skill and the set describe one stack, and the skill's candidate list cannot be written without the set's count.

## Touch
- `plugin/crew/skills/crew-standards/references/php.md` - new, the PHP set
- `plugin/crew/skills/stack-php/SKILL.md` - new skill
- `plugin/crew/skills/crew-standards/SKILL.md` - the stack-sets bullet names the PHP set
- `plugin/crew/tests/test_crew_standards.py`
- `plugin/crew/tests/test_stack_skills.py` - `STACK_NAMES` and `_TRIGGER_TERMS` gain `stack-php`
- `plugin/crew/README.md`
- `plugin/PLUGINS.md` - crew-standards row, new stack-php row, skill count `:17`; the version row at land
- `README.md` - skill count `:168`, `:399`
- `INSTALLATION.md` - skill count `:253`
- `plugin/README.md` - skill count `:414`
- `.claude-plugin/marketplace.json` - crew description's skill count; the version at land
- `plugin/crew/BUDGETS.md`
- `CHANGELOG.md`
- `plugin/crew/.claude-plugin/plugin.json` - version, land branch only
- `.crew/codemap/crew.md` - skill count, the stack-skill list, the stack-set sentence; re-anchor
- `.crew/codemap/marketplace-registration.md`, `.crew/codemap/install-scripts.md` - skill count; re-anchor
- `.crew/codemap/**` - re-anchor only
- `.claude/rules/**` - regenerate only
- `graphify-out/**` - `graphify update .` only
- `docs/diagrams/**` - re-anchor only if made stale
- `docs/tickets/L-0533/` - removed in the final PR unless the owner wants it kept

Not in Touch: `plugin/crew/tests/sabotage_standards.py`, `scripts/install-prerequisites.{sh,ps1}`,
`.crew/verify.json`, `crew_standards.py`, `docs/guides/crew/**`, `plugin/crew/commands/implement.md`.

## Acceptance checks
Commands from the repo root; pytest through `/root/crew-tmp/heavy-run` on a memory-bound host.
`T` is `plugin/crew/tests/test_crew_standards.py`, `S` is `plugin/crew/tests/test_stack_skills.py`.
- [ ] `.work/tickets/L-0533/changesets-php.txt` lists, for each of PHP-01..PHP-20, every counted change set and
  every rejected lead with its reason. `grep -c '^PHP-' .work/tickets/L-0533/changesets-php.txt` is at least 20.
- [ ] `references/php.md` parses with no problems, set `PHP`, `applies-to` `["**/*.php", "**/*.phtml"]`, ids
  exactly the admitted list, in id order. New `test_php_set_parses_with_every_field`:
  `python3 plugin/crew/tests/pytest_rule.py T -q -k test_php_set_parses_with_every_field`
- [ ] Every PHP standard names and cites at least three change sets and its Why states the count (existing
  parametrized tests): `python3 plugin/crew/tests/pytest_rule.py T -q -k "stack_standard and php.md"`
- [ ] Why finding counts match a hand-counted `_PHP_FINDINGS` table. New
  `test_php_why_finding_counts_match_their_enumerations`: `python3 plugin/crew/tests/pytest_rule.py T -q -k test_php_why_finding_counts`
- [ ] No Source quote elided with `[...]`. New `test_php_sources_quote_whole_spans_without_elision`:
  `python3 plugin/crew/tests/pytest_rule.py T -q -k test_php_sources_quote`
- [ ] The set applies to PHP sources only: `PHP` in `effective_set(<root>, [f])["sets"]` for
  `TSSwebsite/library/Ppb/Service/Listings.php` and `app/views/sale.phtml`, not for `composer.json`, `README.md`,
  `db/001.sql` or `x.php.bak`. New `test_php_set_applies_to_php_files_only`:
  `python3 plugin/crew/tests/pytest_rule.py T -q -k test_php_set_applies`
- [ ] Nothing machine-local or `F`-numbered is cited (existing tests):
  `python3 plugin/crew/tests/pytest_rule.py T -q -k "cite_nothing_local or machine_local"`
- [ ] `.work/tickets/L-0533/quote-check-php.txt` shows every Source quote found verbatim (whitespace-normalised)
  in the raw page.
- [ ] Each new test proven red by hand, one mutation at a time on `php.md`, file restored byte-identical (`cmp`),
  recorded in `.work/tickets/L-0533/notes.md`; these four become the follow-up's `STANDARDS_MUTATIONS`:
  `applies-to` narrowed to `["**/*.phtml"]` (red `test_php_set_applies_to_php_files_only`); a Change sets line cut
  to two names (red `test_every_stack_standard_names_and_cites_three_change_sets[php.md]`); a candidate id in place
  of an admitted heading (red `test_php_set_parses_with_every_field`); a Why count off by one (red
  `test_php_why_finding_counts_match_their_enumerations`).
- [ ] `stack-php` meets the stack-skill contract: `python3 plugin/crew/tests/pytest_rule.py S -q` passes with
  `stack-php` in `STACK_NAMES` and `_TRIGGER_TERMS` (`"php"`), and fails before the skill exists (`test_all_seven_stack_skills_exist`
  red with `stack-php` listed and no directory). Its verify rule's command contains `exit 77` and `TOOL MISSING`
  and exits 77 with `PATH` stripped.
- [ ] `stack-php/SKILL.md` names `crew-standards/references/php.md`, lists the admitted ids one line each, lists
  every other PHP-NN (and the research's left-out `unserialize` item) as a candidate with its change-set count and
  "promoted when a third reviewed change set earns it": `grep -c 'PHP-[0-9][0-9]' plugin/crew/skills/stack-php/SKILL.md` is at least 20.
- [ ] Skill counts read 32 everywhere: `python3 scripts/check-marketplace.py` exits 0 after commit (checks the five
  `plugin-skills:crew` claims), and `grep -rn "31 bundled skills\|31 skills" README.md INSTALLATION.md plugin/README.md plugin/PLUGINS.md .claude-plugin/marketplace.json .crew/codemap/crew.md`
  returns nothing outside dated provenance paragraphs.
- [ ] Docs in the same PR: `crew-standards/SKILL.md` stack-sets bullet, `plugin/crew/README.md:795`,
  `plugin/PLUGINS.md` rows, `.crew/codemap/crew.md`, `CHANGELOG.md` `[Unreleased]` entry with a **Behaviour change**
  line (a `.php`/`.phtml` change now answers the PHP rows; in-flight stamps go stale), `BUDGETS.md` re-measured.
- [ ] The crew-standards verify rule passes:
  `python3 plugin/crew/tests/pytest_rule.py plugin/crew/tests/test_crew_standards.py plugin/crew/tests/test_review_run_standards.py plugin/crew/tests/test_review_prompt.py plugin/crew/tests/test_review_run_launch.py plugin/crew/tests/test_review_ledger.py plugin/crew/tests/test_lifecycle_commands.py plugin/crew/tests/test_review_receipt.py plugin/crew/tests/test_webtest_guard.py -q`
  and validate-prompts: `(cd plugin/crew && python3 hooks/scripts/_test/validate-prompts.py)`.
- [ ] `python3 scripts/check-tooling-pr.py` exits 0 ("no harness path changed").
- [ ] Refresh artifacts fresh: `python3 plugin/crew/hooks/scripts/crew_instructions.py rules --root . --check` and
  `python3 plugin/crew/hooks/scripts/crew_refresh_check.py --root . --ticket L-0533` pass.
- [ ] Full crew suite and lint: `python3 plugin/crew/tests/pytest_rule.py plugin/crew/tests/ -q`,
  `python3 -m pylint -j 4 $(git ls-files "*.py")`, `python3 /root/crew-tmp/ruff-no-new.py <worktree>` exit 0.
- [ ] L-0533's own self-check: `crew_standards.py init` then `stamp --root . --ticket L-0533` exit 0.
- [ ] At land: crew version one past origin/main's in `plugin/crew/.claude-plugin/plugin.json`,
  `.claude-plugin/marketplace.json`, `plugin/PLUGINS.md` and the CHANGELOG heading.

## Dependencies
- T-0086: merged (#282). Done.
- L-0539: not merged; decides only where the sabotage entries go.
- L-0532 (SQL): independent content, but PHP-01 is written as a supplement to the SQL parameterisation rule. If
  L-0532 has landed and ships SQL-01, PHP-01's Rule names SQL-01; otherwise it names `stack-sql`'s
  parameterisation line. Shared lines (`crew-standards/SKILL.md`, `README.md:795`, `PLUGINS.md:217`,
  `crew.md`, `test_crew_standards.py`, BUDGETS, CHANGELOG) go through the merge train, one slice at a time.
- Follow-up: a tooling-only ticket for the four sabotage entries, minted by the coordinator (unless L-0539 first).

## Approval
Direction and spec approved for cloud hand-off by the orchestrator under the owner's standing self-approve authority, 2026-10-05. Plan: to be written by the implementing session.

# L-0533: PHP development standards set and a new stack-php skill, T-0086 slice 3          status: spec   risk: medium
Written against origin/main `a555ff37` (crew 1.1.0). Every `path:line` below is at that commit.

## Intent
Ship the PHP per-language standards set on T-0085's mechanism, unchanged:
`plugin/crew/skills/crew-standards/references/php.md`, set `PHP`, `applies-to: ["**/*.php", "**/*.phtml"]`,
holding the standards from the coordinator's research (`.work/tickets/T-0086/research/php.md`, not published) that
findings from at least three distinct reviewed change sets earn, counted as `python.md`'s lead paragraph counts them.
The slice starts with an evidence step in the owner's private repo. Each shipped standard keeps an official-doc Source
re-read from the raw page and Earned by lines with no private identifying detail. Add a new, short `stack-php` skill
(pitfalls the set does not gate, a pointer to the set, the candidates, a `php -l` verify rule), registered in every
place a crew skill or skill count is stated.

## Exclusions
- No change to `crew_standards.py`, `review_run.py`, `review_prompt.py` or `crew_ticket.py`.
- **No edit to `plugin/crew/tests/sabotage*.py`** (`HARNESS`, `scripts/check-tooling-pr.py:79`; L-0539 not landed);
  follow-up tooling-only PR unless L-0539 merged first. No rename of any existing test.
- No framework-specific rule in the plugin set.
- No candidate standard in `php.md` or in `.crew/standards.md`.
- **No private identifying detail in any published file**, `php.md` included: no private repository or client name,
  path, sha, commit subject, ticket or PR id, review-file name or finding id. Also nothing the existing tests refuse
  (`.work/`, `\bF\d{3}\b`, `/repos/`, session notes; `test_crew_standards.py:247-255`, `:381-390`).
- No install-script change: `stack-php`'s verify rule exits 77 when `php` is missing; the install pair is untouched.
- No separate `marketplace.json` entry for the skill: crew-bundled skills are not registered separately; only the
  crew entry's description count changes.
- No `/crew:implement` edit; no hook; no config key (CONFIG.md unchanged; Docs: none there). No guide change (they
  name no set and no stack skill list; Docs: none there). No ADR. No diagram.
- No `.crew/verify.json` change: `plugin/crew/skills/**` is in the validate-prompts rule (`.crew/verify.json:275`) and
  `crew-standards/**` in the crew-standards rule (`:484-485`).
- No version bump on the build branch (REPO-03).

## Evidence
- Direction: `docs/tickets/L-0533/direction.md`; T-0086's approved direction (held by the coordinator): admission
  bar; "Stack skill: new stack-php".
- Worked example (#282): `references/python.md`, `plugin/crew/skills/stack-python/SKILL.md:46-86`, `CHANGELOG.md:3815`.
- Loader: `crew_standards.py:76` `PLUGIN_FIELDS`; `:83` `_ID_RE` (`PHP-01` valid); `:175-199` stray `## ` is a problem;
  `:222` empty set is a problem; `:229` `_applies`; `:236` `_plugin_sets`; `:263` `effective_set`.
- Tests covering `php.md` with no edit (`_STACK_SETS` `test_crew_standards.py:261`): `:292`, `:307`, `:349`; refused
  tokens `:250` (`\.work/|\bF\d{3}\b`) and `:381-390`. Python-only tests to mirror: `:264`, `:336` (`_PYTHON_FINDINGS`
  `:330`), `:359`, `:372`.
- Stack-skill contract: `plugin/crew/tests/test_stack_skills.py:62-71` `STACK_NAMES`, `:79-88` `_TRIGGER_TERMS`, `:74`
  `MIN_DESCRIPTION_LEN` 80, `:128` every listed skill exists, `:133` no unlisted `stack-*` directory, `:142` at most 120
  lines, `:151` front matter, `:175-203` a fenced ```json rule with `paths` and `run` lists, `:205` every command carries
  `exit 77` and `TOOL MISSING`, `:288` each command exits 77 with only `sh`/`bash` on `PATH`. Model rule:
  `plugin/crew/skills/stack-sql/SKILL.md:71-86`.
- Crew skill count 31, checked by `check_self_claims` (`scripts/check-marketplace.py:761`) at each
  `<!-- claim: plugin-skills:crew -->`: `README.md:168`, `README.md:399`, `INSTALLATION.md:253`, `plugin/README.md:414`,
  `plugin/PLUGINS.md:17`. Unmarked: `.claude-plugin/marketplace.json:223` ("31 bundled skills"), `.crew/codemap/crew.md:58`
  and its stack-skill list `:78-81`, `.crew/codemap/marketplace-registration.md:61`, `:68`, `.crew/codemap/install-scripts.md:237`.
- Rows: `plugin/PLUGINS.md:217` (crew-standards, "(Python so far)"); a new `stack-php` row between `stack-dotnet` `:220`
  and `stack-powershell` `:221`. Also `plugin/crew/README.md:795`, `plugin/crew/skills/crew-standards/SKILL.md:17-21`,
  `.crew/codemap/crew.md:1830-1831`, `plugin/crew/BUDGETS.md:10-11` (a new `.md` file moves both numbers), `CHANGELOG.md:10`.
- Harness: `scripts/check-tooling-pr.py:58-87`; L-0539 `direction`, no PR (2026-10-05).
- Research (held by the coordinator, not published): 20 rules, PHP-01..PHP-20, and a short list of left-out
  candidates (an untrusted-input `unserialize` rule among them). Doc quotes came through a summarising fetch and were
  never checked raw; some are known to be paraphrased. The orchestrator's pre-count (2026-10-05): on the strict rule
  at most two rules reach three; the rest are leads to mine.

## Unknowns
- **Which rules ship.** Decided by the evidence step, recorded in the machine-local
  `.work/tickets/L-0533/changesets-php.txt` (never committed). The tests' admitted list is copied from it.
- **Change-set names in a public file.** Opaque labels, each Earned by bullet describing its defect and round
  without identifying detail; the mapping stays machine-local. The reviewer is told.
- **Review records held only in an untracked file** still count as that review, cited generically. Accepted as risk.
- **One repository.** All counted change sets come from one private repo. Accepted (direction).
- **Doc quotes.** Raw fetch and string match per quote, recorded in `.work/tickets/L-0533/quote-check-php.txt`;
  misses replaced or dropped, never paraphrased.
- **`php -l` on the test host.** `test_missing_tool_branch_actually_exits_77_for_real` passes whether or not PHP is
  installed; whether the rule passes on real PHP is measured only if `php` is on the implementing host. The PR says which.
- **In-flight tickets with `.php` changes** get stale stamps after merging main. Accepted; CHANGELOG and PR body say so.
- **A cloud session without the research or the private repo** cannot do the evidence step and must stop and say so.

## Size and split
One new Markdown set (estimate 300-600 lines), one new skill of at most 120 lines, four new tests and a findings
table in `test_crew_standards.py`, two lines in `test_stack_skills.py`, five checked count claims plus unmarked
mentions, doc rows. No production code. Sabotage entries split out. No further split.

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
- `.crew/codemap/crew.md` - skill count, stack-skill list, stack-set sentence; re-anchor
- `.crew/codemap/marketplace-registration.md`, `.crew/codemap/install-scripts.md` - skill count; re-anchor
- `.crew/codemap/**` - re-anchor only
- `.claude/rules/**` - regenerate only
- `graphify-out/**` - `graphify update .` only
- `docs/diagrams/**` - re-anchor only if made stale
- `docs/tickets/L-0533/` - removed in the final PR unless the owner wants it kept

Not in Touch: `plugin/crew/tests/sabotage_standards.py`, `scripts/install-prerequisites.{sh,ps1}`, `.crew/verify.json`,
`crew_standards.py`, `docs/guides/crew/**`, `plugin/crew/commands/implement.md`.

## Acceptance checks
Commands from the repo root; pytest through `/root/crew-tmp/heavy-run` on a memory-bound host.
`T` is `plugin/crew/tests/test_crew_standards.py`, `S` is `plugin/crew/tests/test_stack_skills.py`.
- [ ] The machine-local `.work/tickets/L-0533/changesets-php.txt` covers PHP-01..PHP-20:
  `grep -c '^PHP-' .work/tickets/L-0533/changesets-php.txt` is at least 20.
- [ ] `references/php.md` parses with no problems, set `PHP`, `applies-to` `["**/*.php", "**/*.phtml"]`, ids exactly
  the admitted list in id order. New `test_php_set_parses_with_every_field`:
  `python3 plugin/crew/tests/pytest_rule.py T -q -k test_php_set_parses_with_every_field`
- [ ] Every PHP standard names and cites three change sets and its Why states the count (existing tests):
  `python3 plugin/crew/tests/pytest_rule.py T -q -k "stack_standard and php.md"`
- [ ] Why counts match a hand-counted `_PHP_FINDINGS` table. New `test_php_why_finding_counts_match_their_enumerations`:
  `python3 plugin/crew/tests/pytest_rule.py T -q -k test_php_why_finding_counts`
- [ ] No Source quote elided. New `test_php_sources_quote_whole_spans_without_elision`:
  `python3 plugin/crew/tests/pytest_rule.py T -q -k test_php_sources_quote`
- [ ] The set applies to PHP sources only: `PHP` in `effective_set(<root>, [f])["sets"]` for
  `src/Service/Orders.php` and `views/sale.phtml`, not for `composer.json`, `README.md`, `db/001.sql` or `x.php.bak`.
  New `test_php_set_applies_to_php_files_only`: `python3 plugin/crew/tests/pytest_rule.py T -q -k test_php_set_applies`
- [ ] Nothing machine-local or `F`-numbered is cited: `python3 plugin/crew/tests/pytest_rule.py T -q -k "cite_nothing_local or machine_local"`
- [ ] No private identifying detail in any changed file: a grep of `git diff origin/main...HEAD` for the private
  repository and client names the coordinator holds returns nothing (the coordinator supplies the pattern).
- [ ] `.work/tickets/L-0533/quote-check-php.txt` shows every Source quote found verbatim in the raw page.
- [ ] Each new test proven red by hand, one mutation at a time on `php.md`, restored byte-identical (`cmp`), recorded
  in `.work/tickets/L-0533/notes.md`; these four become the follow-up's `STANDARDS_MUTATIONS`: `applies-to` narrowed
  to `["**/*.phtml"]` (red `test_php_set_applies_to_php_files_only`); a Change sets line cut to two names (red
  `test_every_stack_standard_names_and_cites_three_change_sets[php.md]`); a candidate id in place of an admitted
  heading (red `test_php_set_parses_with_every_field`); a Why count off by one (red
  `test_php_why_finding_counts_match_their_enumerations`).
- [ ] `stack-php` meets the stack-skill contract: `python3 plugin/crew/tests/pytest_rule.py S -q` passes with
  `stack-php` in `STACK_NAMES` and `_TRIGGER_TERMS` (`"php"`), and is red before the skill exists. Its verify rule's
  command contains `exit 77` and `TOOL MISSING` and exits 77 with `PATH` stripped.
- [ ] `stack-php/SKILL.md` names `crew-standards/references/php.md`, lists the admitted ids, lists every other PHP-NN
  and the left-out `unserialize` item as candidates with change-set counts and "promoted when a third reviewed change
  set earns it": `grep -c 'PHP-[0-9][0-9]' plugin/crew/skills/stack-php/SKILL.md` is at least 20.
- [ ] Skill counts read 32: `python3 scripts/check-marketplace.py` exits 0 after commit, and
  `grep -rn "31 bundled skills\|31 skills" README.md INSTALLATION.md plugin/README.md plugin/PLUGINS.md .claude-plugin/marketplace.json .crew/codemap/crew.md`
  returns nothing outside dated provenance paragraphs.
- [ ] Docs in the same PR: `crew-standards/SKILL.md`, `plugin/crew/README.md:795`, `plugin/PLUGINS.md` rows,
  `.crew/codemap/crew.md`, `CHANGELOG.md` `[Unreleased]` entry with a **Behaviour change** line, `BUDGETS.md` re-measured.
- [ ] The crew-standards verify rule passes:
  `python3 plugin/crew/tests/pytest_rule.py plugin/crew/tests/test_crew_standards.py plugin/crew/tests/test_review_run_standards.py plugin/crew/tests/test_review_prompt.py plugin/crew/tests/test_review_run_launch.py plugin/crew/tests/test_review_ledger.py plugin/crew/tests/test_lifecycle_commands.py plugin/crew/tests/test_review_receipt.py plugin/crew/tests/test_webtest_guard.py -q`
  and `(cd plugin/crew && python3 hooks/scripts/_test/validate-prompts.py)`.
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
- L-0532 (SQL): PHP-01 supplements the SQL parameterisation rule. If L-0532 has landed with SQL-01, PHP-01 names it;
  otherwise it names `stack-sql`'s parameterisation line. Shared lines go through the merge train.
- Follow-up: a tooling-only ticket for the four sabotage entries (unless L-0539 first).

## Approval
Direction and spec approved for cloud hand-off by the orchestrator under the owner's standing self-approve authority, 2026-10-05. Plan: to be written by the implementing session.

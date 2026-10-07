# L-0534: PowerShell development standards set (PWSH), T-0086 slice 4          status: spec   risk: medium
Written against origin/main `a555ff37` (crew 1.1.0). Every `path:line` below is at that commit.

## Intent
Ship the PowerShell per-language standards set on T-0085's mechanism, unchanged:
`plugin/crew/skills/crew-standards/references/powershell.md`, set `PWSH` (the loader's limit is six capitals),
`applies-to: ["**/*.ps1", "**/*.psm1", "**/*.psd1"]`, holding the standards from
the coordinator's research (`.work/tickets/T-0086/research/powershell.md`, not published) that findings from at least three distinct reviewed change sets earn,
counted as `python.md`'s lead paragraph counts them. Ids are `PWSH-NN` with the research's numbers. The slice starts
with an evidence step: this repository's own PowerShell reviews and CHANGELOG first, then the owner's private repos.
Each shipped standard keeps its Earned by citations and a Microsoft Learn Source re-read from the raw page.
`stack-powershell` points at the set and lists the rest as candidates, within its 120-line budget. The research's
three open questions are settled as the direction records: no StrictMode clause in the gated set, BOM-when-non-ASCII,
and POWERSHELL-20 left out of the plugin set.

## Exclusions
- No change to `crew_standards.py` (no widening of `_ID_RE`/`_SET_RE`), `review_run.py`, `review_prompt.py` or
  `crew_ticket.py`.
- **No edit to `plugin/crew/tests/sabotage*.py`** (`HARNESS`, `scripts/check-tooling-pr.py:79`; L-0539 not landed);
  follow-up tooling-only PR, unless L-0539 merged first. No rename of any existing test.
- **POWERSHELL-20 is not in `powershell.md`** and not written to `.crew/standards.md`: its code is `.py`, so a `.ps1`
  glob never applies it, and the overlay takes a standard only after the owner approves a proposal
  (`.crew/standards.md:8-12`). It is listed in `stack-powershell` as overlay material.
- **No `Set-StrictMode` requirement** in any gated rule: that half of POWERSHELL-16 has no owner change set
  (research held by the coordinator). It is a doc-only candidate in `stack-powershell`.
- No change to any `.ps1` in this repository, and no change to `stack-powershell`'s verify.json rules
  (`stack-powershell/SKILL.md:68-104`), which `test_stack_skills.py:266-400` runs for real.
- No private identifying detail in any published file (no private repository or client name, path, sha, commit
  subject, ticket or PR id); private change sets are cited generically under opaque labels. No machine-local or
  forbidden citation in the shipped set: no `.work/` path (so a crew review is cited as
  `T-0009 r3 @<head>, BLOCK \`path:line\`: "quote"`, never by its `out.txt` path), no `\bF\d{3}\b`, no session note,
  no `/repos/` path, no `CLAUDE.md` line (`test_crew_standards.py:247-255`, `:381-390`).
- No other stack. No hook, config key, guide, ADR or diagram change (Docs: none - the guides name no set; CONFIG.md
  has no key for this). No `.crew/verify.json` change. No install-script change.
- No version bump on the build branch (REPO-03).

## Evidence
- Direction: `docs/tickets/L-0534/direction.md`; T-0086's direction (held by the coordinator) ("Per-stack
  questions ... PowerShell StrictMode, BOM-vs-ASCII, POWERSHELL-20 placement ...: the slice spec takes the lane's
  draft position and flags any it cannot cite").
- Worked example (#282): `references/python.md`, `plugin/crew/skills/stack-python/SKILL.md:46-86`, `CHANGELOG.md:3815`.
- Loader limits: `plugin/crew/hooks/scripts/crew_standards.py:83` `_ID_RE` and `:84` `_STANDARD_RE` take
  `[A-Z]{2,6}-\d{2}`; `:131-133` a set name that is not 2-6 capitals is a problem; `:188-190` an id whose prefix is
  not the file's set is a problem; `:175-199` a stray `## ` heading is a problem; `:222` an empty set is a problem;
  `:229` `_applies`; `:263` `effective_set`.
- Tests covering any new set with no edit (`_STACK_SETS` `test_crew_standards.py:261`): `:292`, `:307`, `:349`;
  Python-only tests to mirror: `:264`, `:336` (`_PYTHON_FINDINGS` `:330`), `:359`, `:372`.
- Stack skill: `plugin/crew/skills/stack-powershell/SKILL.md`, 107 lines; `## Pitfalls that cost time - 5.1` `:28`
  (encoding `:30-33`), `## Pitfalls that cost time - 7` `:43` (UTF-8 no BOM `:53`), `## Security hardening` `:56`,
  `## Verification` `:62`, `## verify.json rules to propose` `:68`, `## LSP` `:105`. Cap: `test_stack_skills.py:142`
  (`MAX_LINES = 120`, `:73`). Its rules are executed by `:288`, `:337`, `:371`.
- This repository's `.ps1`/`.psm1`: 44 tracked, all ASCII-only (2026-10-05, `grep -P '[^\x00-\x7F]'` empty).
- Harness: `scripts/check-tooling-pr.py:58-87`; L-0539 `direction`, no PR (2026-10-05).
- Research (held by the coordinator, `.work/tickets/T-0086/research/powershell.md`, not published): 20 rules,
  POWERSHELL-01..-20, a table relating them to the existing skill's pitfall lines, three open questions, and a
  not-verified list (docs summarised or search excerpts; the 5.1 redirection-encoding pages contradict each other).
  It did not assess the admission rule.
- **Pre-count (orchestrator, 2026-10-05).** Counted: a crew ticket review round, or a commit whose message records a
  review finding; one count per ticket, PR or review series. Not counted: session notes, instruction-file lines, a
  positive-pattern code citation. On the research's own citations no rule clearly reaches three; the best-supported
  (PWSH-07, -10, -11, -19) reach two or, if commits of one series count separately, three.
- Leads: this repository's `CHANGELOG.md` has 430 lines naming PowerShell, many inside review-round entries (for
  example `CHANGELOG.md:1641` "Second review of #347", `:1655` "Third review of #347"), and this repository's git log
  has PowerShell review-fix commits the research did not cite; the owner's private repos hold more.
- Docs that describe the sets: `plugin/crew/skills/crew-standards/SKILL.md:17-21`, `plugin/crew/README.md:795`,
  `plugin/PLUGINS.md:217` and `:221` (stack-powershell row), `.crew/codemap/crew.md:1830-1831`,
  `plugin/crew/BUDGETS.md:10-11`, `CHANGELOG.md:10`.

## Unknowns
- **Which rules ship.** Decided by the evidence step: the machine-local `.work/tickets/L-0534/changesets-pwsh.txt`, never committed (rule, ticket/PR/
  review series, round, sha, quoted line, why it counts; rejected leads with reasons). The tests' admitted list is
  copied from it.
- **Review series without a ticket id.** Several crew commits predate ticket ids (2026-08) or sit in the crew-1.0
  review series. Default: commits of one branch review or one named review series count once, identified by the
  name `python.md` uses for that series where one exists (for example `crew-1.0.13`); otherwise by PR number. Two
  commits whose series cannot be told apart are `unknown` and count once together. The reviewer is told.
- **Doc quotes.** Summarised or search excerpts. Resolved at implement: raw fetch of each Microsoft Learn URL (or
  `microsoft_docs_fetch`), string match per quote, recorded in `.work/tickets/L-0534/quote-check-pwsh.txt` with the
  page's `view=` and date. The 5.1 redirection-encoding contradiction (research not-verified list) is not
  quoted in either direction unless a 5.1 host measurement is recorded; PWSH-04 states the consumer-encoding rule
  without asserting 5.1's default.
- **Overlap with the existing pitfalls.** Where an admitted standard covers a pitfall line (for example PWSH-04 and
  `:30-33`), the pitfall line shrinks to a pointer; the content is not deleted without a standard covering it.
- **A cloud session without the research or the private repos** can still count this repository's own change sets,
  but must say which rules it could not count rather than admit them.
- **In-flight tickets with `.ps1` changes**, which in this repository are common (44 hook scripts), get stale stamps
  after merging main and must add the PWSH rows by hand. Accepted; CHANGELOG and the PR body flag it.

## Size and split
One new Markdown set (estimate 300-600 lines), about 13 net lines in `stack-powershell` (or a small
`references/candidates.md` if it does not fit), four tests and a findings table in `test_crew_standards.py`, doc rows.
No production code. Sabotage entries split out. No further split.

## Touch
- `plugin/crew/skills/crew-standards/references/powershell.md` - new, set PWSH
- `plugin/crew/skills/crew-standards/SKILL.md` - the stack-sets bullet names the PWSH set
- `plugin/crew/skills/stack-powershell/SKILL.md` - `## Standards` pointer, candidates, description, pitfall pointers
- `plugin/crew/skills/stack-powershell/references/candidates.md` - only if the skill would exceed 120 lines
- `plugin/crew/tests/test_crew_standards.py`
- `plugin/crew/README.md`
- `plugin/PLUGINS.md` - crew-standards and stack-powershell rows; the version row at land
- `plugin/crew/BUDGETS.md`
- `CHANGELOG.md`
- `plugin/crew/.claude-plugin/plugin.json` - version, land branch only
- `.claude-plugin/marketplace.json` - version, land branch only
- `.crew/codemap/crew.md` - the stack-set sentence; re-anchor
- `.crew/codemap/**` - re-anchor only
- `.claude/rules/**` - regenerate only
- `graphify-out/**` - `graphify update .` only
- `docs/diagrams/**` - re-anchor only if made stale
- `docs/tickets/L-0534/` - removed in the final PR unless the owner wants it kept

Not in Touch: `plugin/crew/tests/sabotage_standards.py`, `.crew/standards.md`, `crew_standards.py`, any `.ps1`,
`.crew/verify.json`, `docs/guides/crew/**`, `plugin/crew/tests/test_stack_skills.py`.

## Acceptance checks
Commands from the repo root; pytest through `/root/crew-tmp/heavy-run` on a memory-bound host.
`T` is `plugin/crew/tests/test_crew_standards.py`.
- [ ] `.work/tickets/L-0534/changesets-pwsh.txt` lists, for each of PWSH-01..PWSH-20, every counted change set and
  every rejected lead with its reason. `grep -c '^PWSH-' .work/tickets/L-0534/changesets-pwsh.txt` is at least 20.
- [ ] `references/powershell.md` parses with no problems, set `PWSH`, `applies-to`
  `["**/*.ps1", "**/*.psm1", "**/*.psd1"]`, ids exactly the admitted list in id order, and `PWSH-20` absent. New
  `test_pwsh_set_parses_with_every_field`: `python3 plugin/crew/tests/pytest_rule.py T -q -k test_pwsh_set_parses_with_every_field`
- [ ] Every PWSH standard names and cites at least three change sets and its Why states the count (existing
  parametrized tests): `python3 plugin/crew/tests/pytest_rule.py T -q -k "stack_standard and powershell.md"`
- [ ] Why finding counts match a hand-counted `_PWSH_FINDINGS` table. New
  `test_pwsh_why_finding_counts_match_their_enumerations`: `python3 plugin/crew/tests/pytest_rule.py T -q -k test_pwsh_why_finding_counts`
- [ ] No Source quote elided. New `test_pwsh_sources_quote_whole_spans_without_elision`:
  `python3 plugin/crew/tests/pytest_rule.py T -q -k test_pwsh_sources_quote`
- [ ] The set applies to PowerShell files only: `PWSH` in `effective_set(<root>, [f])["sets"]` for
  `plugin/crew/hooks/scripts/verify-gate.ps1`, `Mod/Mod.psm1` and `Mod/Mod.psd1`; not for
  `plugin/crew/hooks/scripts/crew_guards.py`, `README.md` or `x.ps1xml`. New `test_pwsh_set_applies_to_powershell_files_only`:
  `python3 plugin/crew/tests/pytest_rule.py T -q -k test_pwsh_set_applies`
- [ ] No gated rule requires StrictMode: `grep -n "StrictMode" plugin/crew/skills/crew-standards/references/powershell.md`
  returns nothing, and `stack-powershell` lists it as a candidate with 0 change sets.
- [ ] PWSH-03 (if admitted) requires UTF-8 with BOM only when a `.ps1` holds a non-ASCII byte, and its Self-check
  passes this repository's 44 ASCII-only scripts as they are.
- [ ] Nothing machine-local or `F`-numbered is cited:
  `python3 plugin/crew/tests/pytest_rule.py T -q -k "cite_nothing_local or machine_local"`
- [ ] No private identifying detail in any changed file: a grep of `git diff origin/main...HEAD` for the private
  repository and client names the coordinator holds returns nothing (the coordinator supplies the pattern).
- [ ] `.work/tickets/L-0534/quote-check-pwsh.txt` shows every Source quote found verbatim (whitespace-normalised)
  in the raw page.
- [ ] Each new test proven red by hand, one mutation at a time on `powershell.md`, restored byte-identical (`cmp`),
  recorded in `.work/tickets/L-0534/notes.md`; these four become the follow-up's `STANDARDS_MUTATIONS`:
  `applies-to` narrowed to `["**/*.psm1"]` (red `test_pwsh_set_applies_to_powershell_files_only`); a Change sets
  line cut to two names (red `test_every_stack_standard_names_and_cites_three_change_sets[powershell.md]`); a
  candidate id in place of an admitted heading (red `test_pwsh_set_parses_with_every_field`); a Why count off by one
  (red `test_pwsh_why_finding_counts_match_their_enumerations`).
- [ ] `stack-powershell` names `crew-standards/references/powershell.md` and set `PWSH`, says `PWSH-NN` is research
  `POWERSHELL-NN`, lists the admitted ids, lists every other id (PWSH-20 marked "overlay material", the StrictMode
  clause marked doc-only) with its change-set count, and keeps its rules and budget:
  `python3 plugin/crew/tests/pytest_rule.py plugin/crew/tests/test_stack_skills.py -q`
- [ ] Docs in the same PR: `crew-standards/SKILL.md` stack-sets bullet, `plugin/crew/README.md:795`,
  `plugin/PLUGINS.md` rows, `.crew/codemap/crew.md`, `CHANGELOG.md` `[Unreleased]` entry with a **Behaviour change**
  line (a change touching a `.ps1`/`.psm1`/`.psd1` now answers the PWSH rows, which in this repository includes every
  hook-pair change; in-flight stamps go stale), `BUDGETS.md` re-measured. `python3 scripts/check-marketplace.py`
  exits 0 after commit.
- [ ] The crew-standards verify rule passes:
  `python3 plugin/crew/tests/pytest_rule.py plugin/crew/tests/test_crew_standards.py plugin/crew/tests/test_review_run_standards.py plugin/crew/tests/test_review_prompt.py plugin/crew/tests/test_review_run_launch.py plugin/crew/tests/test_review_ledger.py plugin/crew/tests/test_lifecycle_commands.py plugin/crew/tests/test_review_receipt.py plugin/crew/tests/test_webtest_guard.py -q`
- [ ] `python3 scripts/check-tooling-pr.py` exits 0 ("no harness path changed").
- [ ] Refresh artifacts fresh: `python3 plugin/crew/hooks/scripts/crew_instructions.py rules --root . --check` and
  `python3 plugin/crew/hooks/scripts/crew_refresh_check.py --root . --ticket L-0534` pass.
- [ ] Full crew suite and lint: `python3 plugin/crew/tests/pytest_rule.py plugin/crew/tests/ -q`,
  `python3 -m pylint -j 4 $(git ls-files "*.py")`, `python3 /root/crew-tmp/ruff-no-new.py <worktree>` exit 0.
- [ ] L-0534's own self-check: `crew_standards.py init` then `stamp --root . --ticket L-0534` exit 0.
- [ ] At land: crew version one past origin/main's in `plugin/crew/.claude-plugin/plugin.json`,
  `.claude-plugin/marketplace.json`, `plugin/PLUGINS.md` and the CHANGELOG heading.

## Dependencies
- T-0086: merged (#282). Done.
- L-0539: not merged; decides only where the sabotage entries go.
- L-0532 (SQL, PR #524) and L-0533 (PHP, PR #532): independent content; shared lines (`crew-standards/SKILL.md`,
  `README.md:795`, `PLUGINS.md:217`, `crew.md`, `test_crew_standards.py`, BUDGETS, CHANGELOG) go through the merge
  train, one slice at a time.
- Possible follow-ups, not filed here: a tooling-only ticket for the four sabotage entries (unless L-0539 first); an
  overlay proposal for POWERSHELL-20 in this repository's `.crew/standards.md`, through the owner-approved proposals
  loop.

## Approval
Direction and spec approved for cloud hand-off by the orchestrator under the owner's standing self-approve authority, 2026-10-05. Plan: to be written by the implementing session.

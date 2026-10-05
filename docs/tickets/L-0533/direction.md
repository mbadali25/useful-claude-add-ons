# L-0533 direction - PHP development standards set (T-0086 slice)

Status: approved direction, inherited from T-0086. Owner 2026-09-30 ~11:20: "File 7 tickets now" - the remaining T-0086 language slices each get their own ticket, spec, review budget and PR. T-0086 closes as the Python slice.

Carry over unchanged from `.work/tickets/T-0086/direction.md`: the one-set-per-stack format on T-0085's wiring (`plugin/crew/skills/crew-standards/references/php.md`, `applies-to` globs), the admission bar (findings from at least three distinct reviewed change sets; an official doc is the Source, not a change set; rules below the bar are listed as candidates in the stack skill, not shipped), Earned-by citations re-read from the raw sources, a change-set count for every rule, and the self-check wiring. Follow T-0086's Python slice as the worked example: its spec, plan, tests (test_crew_standards.py count and quote checks) and sabotage_standards.py entries.

Research: `.work/tickets/T-0086/research/php.md` (and README.md, "Recommended next step").
Stack skill: new stack-php skill (registration in every place: marketplace/catalog if a skill is registered separately; it is a crew-bundled skill, so crew's README/PLUGINS.md).
Order in T-0086's direction: Python (T-0086), SQL (L-0532), PHP (L-0533), PowerShell (L-0534), .NET (L-0535), Terraform (L-0536), Node.js (L-0537), Angular 2+ (L-0538). The slices are independent files, but each touches crew-standards/SKILL.md and BUDGETS.md, so they land through the merge train one at a time.
Depends on: T-0086 (Python) landing first, which sets the pattern and the test and sabotage scaffolding. Also L-0539 (the check-tooling-pr.py fix), else each slice needs the same rule-36 waiver T-0086 got.

## Ask
Owner, 2026-09-28 (T-0086): general development standards for PHP "so that other repos could benefit". Owner, 2026-09-30: each remaining T-0086 language slice gets its own ticket, spec, review budget and PR. This is the PHP slice: `plugin/crew/skills/crew-standards/references/php.md` on T-0085's loader, unchanged, with the rules that meet the landed admission bar, and a new `stack-php` skill that points at it and lists the rest as candidates.

## Facts found at origin/main `a555ff37` (2026-10-05)
- T-0086 (Python) is merged (#282). `references/` holds `generic.md` and `python.md`. There is no `stack-php` (`plugin/crew/skills/` has 31 skills, eight `stack-*`). No PR or commit names L-0533.
- L-0539 is still at `direction`, no PR. `HARNESS` (`scripts/check-tooling-pr.py:79`) still lists `plugin/crew/tests/sabotage*.py`.
- All PHP evidence is in one repository, TheSelectSource (TSS). It tracks 645 review verdict files under `.codex-verdicts/` and has 2999 non-merge commits whose subject records a review round or finding (`codex|gate r[0-9]|round|BLOCK|FIX`), measured 2026-10-05. The research read a sample of them.
- On the research's own citations, under the counting rule T-0086 shipped (a crew-style review, or a fix commit whose message records that a review found the defect; a ticket counts once; vault notes and CLAUDE.md lines never count), only PHP-02, -07 and -20 may reach three; most rules rest on vault notes that name TSS tickets (spec Evidence has the per-rule pre-count). The research's own "18 of 20 pass" counted vault notes, an audit and CLAUDE.md lines.
- The shipped-set test refuses any `\bF\d{3}\b` token (`test_crew_standards.py:250`), and the research names TSS findings as `F551-A`, `F556`, `F575`. Those citations must be by PR, ticket and sha instead.
- A new `stack-*` skill must be added to `STACK_NAMES` and `_TRIGGER_TERMS` in `plugin/crew/tests/test_stack_skills.py:62-88`, stay at or under 120 lines, and propose a `verify.json` rule whose every command has an exit-77 `TOOL MISSING` branch that really exits 77 with `PATH` stripped (`:205`, `:288`). The crew skill count (31) is a checked claim in five places (`<!-- claim: plugin-skills:crew -->`).

## Options
1. **Mine, then admit, and add a lean `stack-php` (recommended).** As the SQL slice: an evidence step opens every cited commit and verdict, then mines TSS's verdict files and review-round commits per rule, and a rule ships at three reviewed change sets. `stack-php` is new, short (pitfalls the set does not gate, the pointer, the candidates, a `php -l` verify rule, LSP note), registered everywhere a crew skill count is stated. Cost: the evidence step, and one skill-count bump across five checked claims.
2. **Ship the set without a `stack-php` skill**, pointing from `stack-sql`. Avoids registration. Cost: the candidates have nowhere to live, and the direction names a new `stack-php`.
3. **Ship on the research's counts.** Fast; ships rules earned only by vault notes, which the bar excludes.

## Recommendation
Option 1, with these defaults, approved 2026-10-05 for cloud hand-off under the owner's standing self-approve authority.

## Open questions (default taken)
- **applies-to.** Default `["**/*.php", "**/*.phtml"]`. The research also proposed `composer.json`, `php.ini` and `**/pool.d/*.conf`; left out, because a dependency bump or a pool config edit would then answer every PHP row. Config-shaped rules (PHP-11) say in **Applies when** that they also apply when those files change, and the author answers them by hand.
- **One repository.** Default: three distinct reviewed TSS change sets (tickets or PRs) meet the bar; the bar is change sets, not repositories. The lead paragraph says the set was earned in one PHP 8.3 / MariaDB codebase.
- **Framework-specific items** (Cube `mods/` precedence, `_prepareData` metadata cache, `View::__call`, paginator 0) stay out of the plugin set; they belong in TSS's own `.crew/standards.md` overlay, which this ticket does not write.
- **Sabotage entries.** Not in this PR (harness path, L-0539 not landed); a follow-up tooling-only PR carries them, unless L-0539 merged first. Each new test is proven red by a hand-run mutation.
- **`stack-php`'s verify rule.** Default: `php -l` over tracked `.php` files, with the exit-77 branch; PHPStan or Psalm only as a commented alternative, since neither is installed by this repo's installers. No install-script change.
- **`/crew:implement` loading.** Default: no edit to `implement.md`; the skill loads by its description, as stack-python does.
- **If the evidence step admits no rule.** Ship `stack-php` with every rule as a candidate and no `php.md`; close with the count recorded.

## Approval
Direction approved 2026-10-05 for cloud hand-off by the orchestrator under the owner's standing self-approve authority. Next: spec (`docs/tickets/L-0533/spec.md`).

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
- The evidence is research held by the coordinator (`.work/tickets/T-0086/research/php.md`, not published). All of it comes from one of the owner's private repos, which keeps a large tracked set of review verdicts and many review-round fix commits; the research read a sample.
- An orchestrator pre-count on 2026-10-05, under the counting rule T-0086 shipped (a review, or a fix commit whose message records that a review found the defect; a ticket counts once; session notes and repository instruction files never count; a clean audit that found nothing is not a finding), found that **at most two PHP rules reach three on the research's own citations**. The research's own higher pass count included session notes, an audit and instruction-file lines.
- The shipped-set test refuses any `\bF\d{3}\b` token (`test_crew_standards.py:250`), and the research names some findings that way, so those citations must be reworded.
- A new `stack-*` skill must be added to `STACK_NAMES` and `_TRIGGER_TERMS` in `plugin/crew/tests/test_stack_skills.py:62-88`, stay at or under 120 lines, and propose a `verify.json` rule whose every command has an exit-77 `TOOL MISSING` branch that really exits 77 with `PATH` stripped (`:205`, `:288`). The crew skill count (31) is a checked claim in five places (`<!-- claim: plugin-skills:crew -->`).

## Options
1. **Mine, then admit, and add a lean `stack-php` (recommended).** An evidence step opens every cited source and mines the private repo's review records per rule; a rule ships at three reviewed change sets. `stack-php` is new and short (pitfalls the set does not gate, the pointer, the candidates, a `php -l` verify rule, LSP note), registered everywhere a crew skill count is stated. Cost: the evidence step, and a skill-count bump across five checked claims.
2. **Ship the set without a `stack-php` skill**, pointing from `stack-sql`. Cost: the candidates have nowhere to live, and the direction names a new `stack-php`.
3. **Ship on the research's counts.** Ships rules earned only by session notes, which the bar excludes.

## Recommendation
Option 1, with these defaults, approved 2026-10-05 for cloud hand-off under the owner's standing self-approve authority.

## Open questions (default taken)
- **applies-to.** `["**/*.php", "**/*.phtml"]`. `composer.json`, `php.ini` and FPM pool configs are left out, so a dependency bump or a pool edit does not answer every PHP row; config-shaped rules say in **Applies when** that they also apply to those files.
- **One repository.** Three distinct reviewed change sets there meet the bar; the lead paragraph says the set was earned in one PHP 8.3 / MariaDB codebase, without naming it.
- **Framework-specific items** stay out of the plugin set; they belong in that repository's own overlay, not written here.
- **Private evidence in a public file.** Earned by lines describe the defect and the round generically under opaque change-set labels; the mapping stays machine-local.
- **Sabotage entries.** Not in this PR (harness, L-0539 not landed); a follow-up tooling-only PR, unless L-0539 merged first. Each new test is proven red by a hand-run mutation.
- **`stack-php`'s verify rule.** `php -l` over tracked `.php` files, with the exit-77 branch; PHPStan or Psalm only as a mentioned alternative. No install-script change.
- **`/crew:implement` loading.** No edit to `implement.md`; the skill loads by its description.
- **If no rule is admitted**, ship `stack-php` with every rule as a candidate and no `php.md`.

## Approval
Direction approved 2026-10-05 for cloud hand-off by the orchestrator under the owner's standing self-approve authority. Next: spec (`docs/tickets/L-0533/spec.md`).

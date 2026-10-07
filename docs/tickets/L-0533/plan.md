# L-0533 plan: PHP standards and a new stack-php skill, T-0086 slice 3 (as built)

Written by the implementing session, 2026-10-05, on `rush/g7-standards` (release/1.2.0 lane).

## Outcome

No `references/php.md` ships. The spec's evidence step mines the owner's private PHP
repository and reads the coordinator's research. Neither was available. A cloud
research pass found public change sets: PHP-01 (inferred) 3, PHP-P1 4, PHP-P2 2 and
PHP-P3 0. The owner decided on 2026-10-05 that public change sets do not count. This
took the direction's fallback, "ship `stack-php` with every rule as a candidate and no
`php.md`". The owner-private gap is stated, and its re-check is C-0020. The four new
set tests and their mutations belong to a shipped set, so none are added.

## Steps

1. Machine-local evidence files: `.work/tickets/L-0533/changesets-php.txt` (a copy of
   the research; PHP-02..20 not assessed, and left so) and `quote-check-php.txt` (3 of 3
   php.net sentences found in the raw pages).
2. `stack-php/SKILL.md` (new): when it applies, pitfalls, `## Standards`, verification,
   the `php -l` verify rule with its exit-77 branch, and LSP. Each pitfall claim was
   checked on PHP 8.3.6. The rule was run on real PHP: exit 0 on a clean file, nonzero on
   a parse error.
3. `stack-php/references/candidates.md` (new): PHP-01, PHP-P1, PHP-P2 and PHP-P3, each
   with change sets, verdict and Source.
4. Registration: `test_stack_skills.py` gets `STACK_NAMES` and `_TRIGGER_TERMS`. The
   crew skill count goes from 31 to 32 at every marked claim, in `marketplace.json`'s crew
   description and in the code maps (`crew.md`, `marketplace-registration.md`,
   `install-scripts.md`). The `plugin/PLUGINS.md` row is added.
5. Docs: `plugin/crew/README.md`, CHANGELOG, and a re-measured BUDGETS.md.
6. Tests: `test_stack_skills.py` (red before the skill existed, because `STACK_NAMES`
   was edited first), `test_crew_standards.py` and `test_lifecycle_commands.py`.
   Checks: check-marketplace (skill claims), smoke and validate-prompts.

Standards: none - Markdown and a test list only.

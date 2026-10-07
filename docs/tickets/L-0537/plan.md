# L-0537 plan: Node.js standards and a new stack-node skill, T-0086 slice (as built)

Written by the implementing session, 2026-10-05, on `rush/g7-standards` (release/1.2.0 lane).

## Outcome

No `references/node.md` ships. NODE-08 reaches four in the spec's re-count: one change set
in this repository (`c80c68c8`) and three in the owner's private AMS repository. Those three
cannot be cited, because their text was not available to this session. The owner decided on
2026-10-05 that public change sets do not count, and named PWSH-16 as the only rule to admit.
NODE-08 is therefore a candidate, marked as at the bar privately. NODE-P1, -P2 and -P3 come
from a cloud research pass and are candidates too.

## Steps

1. Machine-local evidence files: `.work/tickets/L-0537/changesets-node.txt` (a copy of the
   research) and `quote-check-node.txt` (4 of 4 sentences found in the raw pages). This
   repository's `c80c68c8` was re-read for NODE-08 and NODE-P2.
2. `stack-node/SKILL.md` (new): when it applies, pitfalls, `## Standards`, verification, two
   verify commands with exit-77 branches, and LSP. Each runtime claim was checked on Node
   22.22.0. The missing-tool branches were run with a stripped PATH. The real-tool path of
   either command was not run here.
3. `stack-node/references/candidates.md` (new): NODE-08, NODE-P1, NODE-P2 and NODE-P3. It
   also gives the spec's counts for the other research ids, without their text.
4. Registration: `test_stack_skills.py` gets `STACK_NAMES` and `_TRIGGER_TERMS`. The crew
   skill count goes from 32 to 33 at every marked claim, in `marketplace.json`'s description
   and in the code maps. The `plugin/PLUGINS.md` row is added.
5. Docs: `plugin/crew/README.md`, CHANGELOG, and a re-measured BUDGETS.md. The rules are
   regenerated.
6. Tests: `test_stack_skills.py`, `test_crew_standards.py` and `test_lifecycle_commands.py`.
   Checks: check-marketplace, smoke and validate-prompts.

Standards: none - Markdown and a test list only.

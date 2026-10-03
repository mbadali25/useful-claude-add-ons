# T-0059 plan ## PR slices: a cohesive-but-large ticket ships as ordered slice PRs through T-0011, each slice with its own review budget (3 of 3; depends on T-0011, T-0037, T-0052)          status: spec   risk: high
depends-on: T-0011, T-0037, T-0052
## Intent
A ticket that holds together but is large stays one ticket, and its plan carries a `## PR slices` section that groups the steps into 2-5 ordered slices. `crew_ticket.validate` checks the section when it is present. Each slice runs implement, review, done and T-0011's ship in order, as its own PR, independent off the default branch where its files share nothing with an unmerged earlier slice and stacked on that slice otherwise. Each slice gets its own review budget through `review_ledger`'s successor pattern, and only the last slice closes the ticket.
## Exclusions
- Split from T-0052 (decided 2026-09-26, standing authorization). The rulebook and `/crew:split` are T-0052's; autopilot's size check and its `slices` decision are T-0058's. A plan with a valid `## PR slices` section runs sliced whether or not a `split.md` said `slices`.
- No re-slicing of a finished diff, and no slice added mid-implement. Slices are fixed in the approved plan before any code exists; changing them is a plan edit, which stales the approval.
- No change to `ship_decision` (T-0011). `ship` gains the per-slice base and order; the merge stays `merge_argv`'s merge commit only (D-028).
- No new ticket status. A non-final slice leaves the header at `in-progress`, and only the last slice's `/crew:done` sets `done`.
- No shared review budget across slices, and no refund of rounds: rounds spent on earlier slices stay in the ledger.
## Evidence
Anchors are on origin/main 1e0706ac (crew 1.0.41) unless marked. Branch-only anchors are on `T-0011-build` b5bffe4e (`/repos/personal/uca-t-0011`). Spec-only anchors are in `.work/tickets/<id>/spec.md` or `plan.md`, for tickets that have no branch yet (T-0037, T-0052).
- T-0011 (branch-only, b5bffe4e): `ship_decision` `crew_autopilot.py:194`, `merge_argv` `:256` (merge commit only), `_push` `:292`, `read_pr` `:303`, `_branch` `:384`, `_ship_phase` `:429`, and `ship` `:473-540`, which pushes the current branch, opens exactly one PR with `gh pr create --head <branch> --fill` (`:499`), then polls and merges. One PR per ticket today.
- The review budget is `BUDGET = 2` rounds (`plugin/crew/hooks/scripts/review_ledger.py:80`), not four. A successor plan opens a fresh budget counted from its row (`:57-64`), and `_spent` counts rounds since the latest successor (`:196-200`). That is the pattern a per-slice budget reuses.
- `crew_ticket.validate` (`plugin/crew/hooks/scripts/crew_ticket.py:455-495`) parses only `Files`, `Test` and `Risk` labels (`_LABEL_RE` `:159-161`), so a `## PR slices` section with `Steps:` and `Base:` lines passes today unchecked.
- Autopilot's phase table: the plan validation stop is `plugin/crew/hooks/scripts/crew_autopilot.py:365-371`, and `done` closes a ticket on the spec header `status: done` (`:349-352`, set by `plugin/crew/commands/done.md:61`).
- T-0052 (spec-only): `crew_split.py`, `test_crew_split.py` and `sabotage_split.py` with its `SPLIT_MUTATIONS` list are created there (`.work/tickets/T-0052/plan.md` steps 1 and 5). Its `check_proposal` already accepts a `slices` decision.
- T-0037 (spec-only): the status vocabulary and which header edits stale an approval (`.work/tickets/T-0037/spec.md:9` and `:30`). `STATUS_VALUES` is `plugin/crew/hooks/scripts/crew_ticket.py:143` on main.
- Review ledgers measured 2026-09-26 (T-0052's Evidence): plan steps correlate r = 0.73 with findings and 0.55 with rounds, and no ticket with 8 steps or fewer went past 4 rounds. Slices bound a review to fewer steps.
## Unknowns
- **PR slices: stacked or independent.** Decided, following the recommendation (T-0052's direction). Slices run one lifecycle at a time. Under `ship: merge`, slice k+1 branches from the default branch after slice k merges (independent). Under `ship: pr`, or while slice k is unmerged, slice k+1 branches off the default branch when its steps' Files share nothing with any unmerged earlier slice, and off that slice's branch otherwise (stacked, with the PR base set to it). Every slice merges with `merge_argv`'s merge commit (D-028).
- **Review budget per slice (the direction gave no recommendation).** Decided: each slice gets its own `BUDGET` rounds. A ticket's budget is 2 rounds (measured, not four), and sequential slices each need at least one review, so a shared budget would make a 3-slice ticket unreviewable. The mechanism is the successor pattern: `review_ledger.open_slice` appends a `slices` row and `_spent` counts from the latest successor or slice row. Rounds spent on earlier slices stay in the ledger.
- **Why T-0037.** Named as a dependency at the split (2026-09-26). It redefines `STATUS_VALUES` and which header edits keep an approval, and `/crew:done`'s non-final-slice edit (`in-progress`, not `done`) must use that vocabulary without staling the approval. Re-read before step 2.
- **Why T-0052.** Added at the split: `parse_slices`, `SLICES_MIN`/`SLICES_MAX` and the slice mutations go into the `crew_split.py`, `test_crew_split.py` and `sabotage_split.py` T-0052 creates.
- **Shared file with T-0058.** Both edit `next_phase` in `crew_autopilot.py`. Neither depends on the other; whichever lands second rebases.
- **Depends on three unmerged tickets.** Every T-0011, T-0037 and T-0052 anchor above is re-read on main before step 1.
- Codex is out until 2026-10-01, so the review may be same-family. Accepted as risk and announced.
## Touch
- `plugin/crew/hooks/scripts/crew_split.py`
- `plugin/crew/hooks/scripts/crew_ticket.py`
- `plugin/crew/hooks/scripts/crew_autopilot.py`
- `plugin/crew/hooks/scripts/review_ledger.py`
- `plugin/crew/commands/plan.md`
- `plugin/crew/commands/implement.md`
- `plugin/crew/commands/done.md`
- `plugin/crew/skills/crew-plan/SKILL.md`
- `plugin/crew/tests/test_crew_split.py`
- `plugin/crew/tests/test_crew_ticket.py`
- `plugin/crew/tests/test_crew_autopilot_slices.py`
- `plugin/crew/tests/test_crew_autopilot_ship.py`
- `plugin/crew/tests/test_review_ledger.py`
- `plugin/crew/tests/sabotage_split.py`
- `plugin/crew/README.md`
- `plugin/crew/.claude-plugin/plugin.json`
- `plugin/PLUGINS.md`
- `.claude-plugin/marketplace.json`
- `.crew/verify.json`
- `CHANGELOG.md`
## Acceptance checks
- [ ] PR slices in the plan: `crew_split.parse_slices(plan_text)` reads `## PR slices` -> `### Slice N: <name>` with `Steps:` and `Base: main|slice <k>`. `crew_ticket.validate` reports, when the section is present: 2-5 slices; steps partitioned into contiguous ascending runs covering every step exactly once; `Base: main` only when the slice's Files share nothing with any earlier slice; `Base: slice <k>` only for an earlier k. No section is still valid (tests in `test_crew_ticket.py` and `test_crew_split.py`)
- [ ] slices run in order: `<common>/crew/tickets/<id>/slices.json` records the current slice and each shipped slice's PR and merge sha. `next` names `implement` with the current slice's steps. After slice k ships and more remain, it opens the next slice: `review_ledger.open_slice` (a fresh `BUDGET`, counted by `_spent` from the latest successor or slice row) and the branch per the base rule. `/crew:done` on a non-final slice leaves the header at `in-progress`, and only the last slice sets `done` (tests in `test_crew_autopilot_slices.py` and `test_review_ledger.py`)
- [ ] T-0011's `ship` (and its branch-only `test_crew_autopilot_ship.py`) on a sliced ticket opens one PR per slice, in order. The PR base is the default branch, or the stacked predecessor's branch. Each merges only through `merge_argv`, and slice k+1 never ships before slice k is merged, or opened under `pr` (tests in `test_crew_autopilot_ship.py` with the stubbed gh adapter)
- [ ] sabotage: four mutations appended to T-0052's `SPLIT_MUTATIONS` in `sabotage_split.py`, each red on a named test: a slice with `Base: main` sharing Files accepted; a non-contiguous slice accepted; slice k+1 shipped before slice k merged; `_spent` ignoring slice rows. A run shows each one red, and the earlier tickets' mutations stay red
- [ ] `.crew/verify.json`'s `crew_split` rule gains `test_crew_autopilot_slices.py`, `test_crew_ticket.py` and `test_review_ledger.py`. README documents PR slices, the base rule and the per-slice review budget. The crew version is one patch past main at merge, in `plugin.json`, `marketplace.json` and PLUGINS.md, with a CHANGELOG entry. `python3 scripts/check-marketplace.py` passes

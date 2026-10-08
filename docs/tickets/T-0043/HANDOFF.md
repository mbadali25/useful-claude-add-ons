# Cloud handoff: T-0043

**T-0004 follow-up: the FINDINGS stop names the refresh; an accepted FINDINGS round is not called INCOMPLETE; `_settles` control; INSTALLATION count**

Handed to a cloud session on 2026-10-04 by owner instruction. Do not pick up locally.

- **Role:** parent of a three-ticket family. Children: L-0642, L-0643. This ticket is narrowed to the first slice (FIX 1, FIX 2, the `_settles` failing control, and the INSTALLATION count with its marker).
- **INDEX status:** ready, priority med (spec refreshed and approved for hand-off 2026-10-04; plan to be written by the implementing session)
- **Branch:** `T-0043-handoff`, new from origin/main `ce235468`; docs only, no implementation yet. The branch is not named `T-0043-build` on purpose: an old, local-only branch `T-0043-build` exists (14 commits, from the crew 1.0.43 era, never pushed) and is not published. Do not look for it on the remote and do not rebase onto it; the direction check says it carries a rejected design and predates L-0510, T-0010 and T-0087.
- **Files here:** `docs/tickets/T-0043/direction.md`, `docs/tickets/T-0043/spec.md`
- **Size:** about 15 production lines in `plugin/crew/hooks/scripts/crew_autopilot.py`, plus about 60 lines of tests and 6 of docs. No harness path. `crew_autopilot.py` and `commands/autopilot.md` are seam paths, which count as feature work here; every `sabotage_autopilot.py` edit is split out to L-0643.

## Dependencies and work order

Must land first (all already on main):

| Ticket | State | Why |
|---|---|---|
| T-0004 | merged | The autopilot `next` this ticket corrects. |
| T-0008 | merged | `crew_refresh_check.py`, the refresh the FINDINGS stop will name. |
| T-0010 | merged | The policy plumbing in `next_phase` that the tests run through. |
| L-0510 | done | `receipt_stands` and the auto-accept clause at the front of the FINDINGS reason. |
| T-0087 | merged | The tooling-PR rule that forces the sabotage mutations into a separate PR. |

Nothing unmerged blocks this ticket. It can be worked at any time.

Touches the same stop, no ordering required: T-0067 (ready) and its child L-0666 rework stop messages and add a contract test for them; T-0073 (direction) touches the same accept-review stop. If T-0067 lands first, re-read the FINDINGS stop before editing and keep its contract.

This ticket blocks: L-0643 (needs this ticket's branch and tests on main), and by ordering L-0642 (independent in content, but it edits the same two files; land this ticket first, then L-0642 merges main in).

Family order:

1. **T-0043** (this ticket): FIX 1, FIX 2, `_settles` control, INSTALLATION count. Feature PR.
2. **L-0642**: code fences in Open-questions sections. Feature PR. After T-0043.
3. **L-0643**: sabotage mutations for 1 and 2. Tooling-only PR, lands alone. After both.

## Read before writing code

- The spec's `path:line` evidence was checked at origin/main `155fe6d8`. Main has moved since (this branch starts at `ce235468`); re-check each anchor.
- A plan.md exists locally and is **not published**. It is stale: the 2026-09-27 plan for the old single-PR shape, written against older line numbers. The implementing session writes a fresh plan. The spec says its steps 1 to 3 and the INSTALLATION half of step 6 would be a usable outline; since the file is not here, plan from the spec.
- No review ledger travels with this hand-off. A fresh clone starts at round 1 under the new plan.
- The line `    if latest.get("verdict") != "CLEAN" and not ok:` stays byte-identical and occurs exactly once. FIX 2 is a new branch placed above it, not a rewrite. It is the unique anchor of an existing sabotage mutation.
- `next` still stops at an un-accepted FINDINGS round. Only the tail of its reason changes. No new stop ids.
- The FIX 1 docs check joins lines before grepping, because the sentence in `autopilot.md` wraps across two lines; a line-wise grep passes vacuously.
- `commands/autopilot.md` has a 120-line budget.
- Sabotage evidence for this PR is by hand, in a scratch copy made with `git archive`, never the worktree, and quoted in the PR body. The committed mutations wait for L-0643.
- The codemap NIT from the original direction is dropped: already fixed on main.
- direction.md's first lines name a local review folder and a follow-ups file from the earlier build. Neither is published; the findings they held are restated in the spec.
- direction.md carries two owner decisions from 2026-09-30 (catch up with main by merge, never rebase; run the suites under the heavy-run wrapper with 4 workers). The wrapper path is local and is redacted as `<local-tmp>/`.
- Nothing was executed when the spec was refreshed: no pytest, sabotage or gate runs. The repros are from reading code and are re-run by the first plan step. The child specs' evidence was spot-checked only, not re-verified line by line.

## Open questions for the owner (recommended option taken)

1. FIX 2 sends an accepted FINDINGS round with a stale receipt to refresh and then `/crew:review` unattended, spending the next round, the same as a stale CLEAN receipt. Alternative: make it a human stop.
2. The codemap NIT is dropped as already fixed on main.
3. Sabotage mutations land in one tooling PR (L-0643) after both feature PRs, so the feature PRs carry hand-run sabotage evidence in the PR body only. Alternative: one tooling PR per feature PR.
4. L-0642: under `autopilot.questions: self`, a could-not-tell fence item goes through the same policy route as a real question, so autopilot may rewrite the fence itself. Allowed. Alternative: always a person's.
5. L-0643: if L-0642 is delayed, L-0643 waits with it. Alternative: land T-0043's three mutations first and file the fence mutations separately.
6. Publication check: direction.md's owner-decision sections (2026-09-30) held the owner's name and a local path. Both are redacted in this published copy; nothing else in them was changed.
7. The task text for the refresh said origin/main was crew 1.0.154 or later; `plugin.json` at `155fe6d8` says 1.0.322. The specs use 1.0.322.

## Before landing

Merge origin/main, take a crew version above main's from the coordinator, follow the repo's CLAUDE.md (scope discipline, doc updates for `plugin/crew` changes, tooling-PR rule), and remove `docs/tickets/T-0043/` in the final PR unless the owner wants it kept.

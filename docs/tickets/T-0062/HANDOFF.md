# Cloud handoff: T-0062

**promote-gate treats a workflow dispatch of a declared deploy workflow as that deploy, in either spelling (shared reader and the Bash flavour)**

Handed to a cloud session on 2026-10-04 by owner instruction. Do not pick up locally.

Blocked: not buildable until T-0009 (PR #336, open on 2026-10-04) is merged. The dispatch reader it needs is not on main.

- **Role:** parent of a split family. T-0062 itself is now slice 1 only (the shared reader and `promote-gate.sh`). Its children are L-0664 (PowerShell twin) and L-0665 (first-row fix), each published on its own branch (`<id>-build`) with its own draft PR. The spec's `children/` folder is not published.
- **INDEX status:** ready (spec written and approved for hand-off 2026-10-04; plan to be written by the implementing session). Priority high.
- **Branch:** `T-0062-build`, new from origin/main `ce235468`; docs only, no implementation yet
- **Files here:** `docs/tickets/T-0062/direction.md`, `docs/tickets/T-0062/spec.md`
- **Size:** about 235 production lines (`_promote_dispatch.py` about 170, `crew_guards.py` about 30, `promote-gate.sh` about 35). One new fail-closed matcher. No harness path: `promote-gate.*`, `_promote_*.py`, `crew_guards.py` and `promote_tree_mutations.py` are not in `HARNESS`.

## Dependencies and work order

| Ticket | State | Why |
|---|---|---|
| T-0009 | in progress (PR #336, open on 2026-10-04, not on main) | Hard blocker. Supplies the dispatch reader in `crew_guards.py` (`dispatch_trigger`, `dispatch_scopes`). |
| T-0505 | merged (PR #296) | The effective-tree promote-gate this builds on. It already delivered the tree half of the original ask. |
| T-0005 | merged | Base of T-0009's guard grammar. |

Related, not blocking: L-0564 (direction) touches the same files (`promote-gate.sh`, `promote-gate.ps1`, `_promote_tree.py`). L-0614 and L-0615 (direction) are T-0009 follow-ups with no overlap.

**This ticket blocks:** L-0664, and L-0648 (split from T-0045, draft PR #445), which edits the same two gate files and lands after this one.

The facts file and this spec also list T-0045 as blocked by this ticket. T-0045's own refreshed spec (draft PR #407) says its slice 1 has no unmerged dependency, because `check` dispatches nothing; inside the T-0045 family only L-0648 waits on this ticket. The two specs disagree; for T-0045 slice 1, T-0045's spec is the one that describes it, so it is not held here.

**Order of the family:**

1. L-0665 (first-row fix): independent. Needs nothing unmerged; it can land now.
2. T-0062 (shared reader and the Bash flavour): after T-0009 (PR #336) merges.
3. L-0664 (PowerShell twin): after T-0062.

All three edit `promote-gate.sh` or `promote-gate.ps1`, as do L-0564 (direction) and L-0648 (split from T-0045, draft PR #445, lands after T-0062). Whichever lands second merges main and re-checks its anchors.

## Read before writing code

- The spec's `path:line` evidence was checked at origin/main `155fe6d8`. Main has moved since (the branch base is `ce235468`); re-check each anchor.
- Evidence lines marked `T-0009@f08ae7fb` were read from T-0009's branch, not from main. Re-read them after PR #336 merges. If the names moved, `dispatch_read` keeps the contract in Unknowns U1.
- There is no plan.md for this ticket. The implementing session writes the plan.
- No second parser: promote-gate reads a dispatch only through T-0009's reader. The acceptance check that greps for `_DISPATCH_RE` and `/dispatches` pins it.
- This is a hook that can block. CLAUDE.md requires a committed regression suite with must-block and must-allow cases, sabotage-tested.
- U5 was not measured: whether `_promote_tree.py` emits a `hex` record for a sha inside a single-quoted `'inputs[ref]=<sha>'`. An acceptance check pins it; if it fails, the fix is in `_promote_tree.py`, which is in Touch.
- New mutations go in `promote_tree_mutations.py`, which is not harness. Do not edit `plugin/crew/tests/sabotage*.py`.
- `promote.md` is 380 lines against a ceiling of 380. Touch allows raising the ceiling in `.budget-allowance.json` only if the paragraph does not fit.
- T-0009's suites stay green with no assertion edited or loosened.
- direction.md's older sections named another repository, its local path, its workflow file and inputs, and commit shas from it. Those were replaced with generic wording and placeholders (`<sha A>`, `<sha B>`, `<deploy workflow>`) for publication; nothing else in the text was changed. The intake note the direction cites is local and not published.
- The direction's two "Owner decision 2026-09-30" sections describe the owner's local host (a wrapper script, a worker cap). A cloud session follows the merge-not-rebase rule and the repo's own `.crew/verify.json` commands; the local wrapper does not exist there.
- No tests were run when the spec was written.
- Touch includes `docs/guides/crew/**` rebuilt outputs (HTML, DOCX, PDF). Whether the cloud environment can rebuild DOCX and PDF: could not tell.

## Open questions for the owner (recommended option taken)

1. U4: block every unreadable dispatch-shaped line when the map declares a dispatch deploy (taken), or only lines whose text names a declared workflow file? The taken option also blocks an unrelated `gh workflow run ci.yml --ref "$B"` in such repos.
2. Symbolic refs stay unresolved, as T-0505 decided (taken), or resolve `inputs[ref]=<branch>` in the deploy's tree and compare with HEAD?
3. Split order: Bash first with the PowerShell twin as L-0664 (taken), or one PR of about 330 lines for both flavours?
4. L-0664: with no python on the PowerShell side, block dispatch-looking commands (taken) or stand down as the Bash flavour does at `promote-gate.sh:79`?
5. L-0665: the newest PROMOTIONS row decides (taken), or any all-pass row admits?

## Before landing

Merge origin/main, take a crew version above main's from the coordinator, follow the repo's CLAUDE.md (scope discipline, doc updates for `plugin/crew` changes, tooling-PR rule), and remove `docs/tickets/T-0062/` in the final PR unless the owner wants it kept.

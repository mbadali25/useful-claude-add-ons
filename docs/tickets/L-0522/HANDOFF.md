# Cloud handoff: L-0522 (PR 2 of 3)

**Delta gate: a catch-up merge that adds none of the ticket's own code keeps the review receipt (tooling-only; ships fail-closed until the merge train is armed)**

Handed to a cloud session on 2026-10-05 by owner instruction. Do not pick up locally. The local lane was paused
by the owner; this PR publishes the built branch plus a reconstructed direction and spec.

- **Role:** parent ticket, slice 2 of 3. PR 1 merged (#377, "one landing order on check-land's catch-up
  refusals", crew 1.0.326). PR 3 not started.
- **INDEX status:** in-progress (spec reconstructed and approved for hand-off 2026-10-05; plan to be written by
  the implementing session).
- **Branch:** `L-0522-tooling` at `ddd9b2a7` plus this docs commit. Forked from `f691c54c` (PR 1's branch);
  about 1594 commits behind origin/main `a555ff37`. **Not merged with main yet.**
- **Own commits (6):** `44641776` the delta gate (`review_delta.py`, `check_receipt` consults it, preflight,
  autopilot routing, tests, 33 sabotage entries; carries `Tooling-seam: plugin/crew/hooks/scripts/crew_autopilot.py`),
  `d1f48de1` lint fixes, `0c9b970a` check E judges the index, `71e32af7` merge of `L-0522-build`, `e9897d4f`
  code maps, `ddd9b2a7` fail-closed wording (owner decision 2026-10-03).
- **Files here:** `docs/tickets/L-0522/direction.md`, `spec.md`, `HANDOFF.md`.
- **Size:** about 2120 lines over 14 files (711 production in `review_delta.py`, about 1300 tests and sabotage).
- **Harness:** yes. `review_*.py`, `sabotage*.py` and `commands/review.md` are `HARNESS` paths, so PR 2 lands
  alone as a tooling-only PR. `crew_autopilot.py` is a `SEAM` path, declared by trailer. Tests, docs, version
  files, code maps and the graph may ride along; feature code may not.

## Review ledger and receipt

`review_ledger.py --ticket L-0522 --status`: state `ACCEPTED`, rounds used 2 of 2, rounds_left 0, receipt round 2
CLEAN (2026-10-03, base `8123fe74`, bundle `c584eb7171e7`). **That receipt is PR 1's**: round 2's head `f691c54c`
and round 1's `5dd0511c` are both ancestors of #377's head `3a1d0e75`. PR 2's code has **never been reviewed**,
and on this branch `--check-receipt` must read stale. A review of PR 2 needs a fresh budget: approve the
published spec and plan with `crew_ticket.py approve` and confirm it registered a successor; if it did not, ask
the owner for a budget rather than reviewing on a spent ledger.

## Fail-closed decision (owner, 2026-10-03)

The gate binds its integration base to this ticket's merge-train entry (`review_delta.integration_ref`, called
on every judge). Where the train is not armed (the main clone today: `crew_train.py status` -> `armed: no`), every
catch-up reads `delta gate: could not tell: no train entry binds the integration ref` and needs a re-review, by
design. No fallback to a guessed ref.

## Dependencies and work order

| Ticket | State | Why |
|---|---|---|
| L-0522 PR 1 (#377) | merged | Landing order on check-land's refusals. |
| T-0100 (#371) | merged on main, not on this branch | Bundle diffs from a synthetic merged-main base; PR 2's step-2 rebuild must adopt it (spec Intent). |
| T-0087 | merged | Tooling PRs land alone. |
| L-0520 (merge train) | on main, not armed here | The gate keeps nothing until `crew_train.py arm`. |
| T-0033 (#527) | blocked by PR 2 | Close as superseded: its version-only case is PR 2's manifest allowlist. |
| L-0511 PR 2 (#528) | blocked by PR 2 | Bump and refresh once at land need the version and anchor exemptions. |
| L-0620 | direction, follow-up | Fast path vs a catch-up resolved back to reviewed bytes over main's edit to a ticket file. |
| L-0522 PR 3 | next slice, after PR 2 | New branch `L-0522-docs` from main: `/crew:done` check 1, README receipt text, `check_land` passes its fetched sha. Feature/docs, so its own PR. |

## Read before writing code

- **Merge origin/main first: merge, not rebase, no force-push.** Rerere off. Expect conflicts in
  `crew_autopilot.py` (+1720 lines on main), `plugin/crew/README.md`, `.crew/verify.json`, code maps,
  `test_crew_autopilot.py`, `sabotage_review.py`. Main has two more `check_receipt` callers in
  `crew_autopilot.py` (`:452`, `:1271` at `a555ff37`); judge what the delta gate means for each.
- **Known defect after the merge:** `review_delta.tree_bundle_sha256` rebuilds the bundle as a plain
  `git diff`, which is pre-T-0100. Re-derive judge step 2 through `review_patch`'s tree logic and add the
  test and sabotage entry the spec names. Until then the gate is fail-closed and useless, not unsafe.
- Remove the two claims that `check_land` passes its fetched sha (`review_delta.py:30`, `review_ledger.py:840`);
  PR 3 does the wiring in `crew_train.py`, which cannot ride in a tooling-only PR.
- The spec's evidence was checked at origin/main `a555ff37`; re-find every anchor by content after the merge.
- No plan.md is published. The implementing session writes it, then approves spec and plan.
- A harness change runs the harness rule's suites (rule 44: the tooling checker, its suite, golden replay, seam
  contracts, canary review) plus rule 39.

## Open questions for the owner (recommended option taken)

1. Fail-closed until armed: taken (owner decision 2026-10-03).
2. `check_land` sha wiring in PR 3, not PR 2: taken (production code).
3. Re-derive step 2 on T-0100's bundle rather than drop it: taken.
4. Review budget via a successor on approve; ask the owner if none is registered: taken.
5. Remove `docs/tickets/L-0522/` before landing: taken unless the owner says keep.

## Before landing

Merge origin/main (merge commit), take a crew version one above main's from the coordinator (bump in
`plugin.json`, `marketplace.json`, `PLUGINS.md`, `CHANGELOG.md`), rebuild the crew guide outputs for
`troubleshooting.md`, refresh code maps, diagrams, rules and the graph (`graphify update .`), re-measure
`BUDGETS.md`, gate the merged head, get PR 2 reviewed (fresh budget), run `python3 scripts/check-tooling-pr.py`
and `python3 scripts/check-marketplace.py` after committing, then `crew_train.py check-land` if the train is armed.
Land with `gh pr merge --merge`. Follow the repo's CLAUDE.md (scope discipline, crew doc set, tooling-PR rule).
After PR 2 merges: close T-0033 (#527) as superseded, unblock L-0511 PR 2 (#528), start PR 3 on `L-0522-docs`.

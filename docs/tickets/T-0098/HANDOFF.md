# Cloud handoff: T-0098

**review_ledger has no way to correct accepted_by (a peer recorded an owner decision under its own name); add an append-only `--correct-acceptance` with reason and timestamp**

Handed to a cloud session on 2026-10-04 by owner instruction. Do not pick up locally.

- **Role:** standalone ticket (no split children).
- **INDEX status:** direction (spec written and approved for hand-off 2026-10-04; plan to be written by the implementing session)
- **Branch:** `T-0098-build`, new from origin/main `ce235468`; docs only, no implementation yet
- **Files here:** `docs/tickets/T-0098/direction.md`, `docs/tickets/T-0098/spec.md`
- **Size:** about 70 added production lines, all in `plugin/crew/hooks/scripts/review_ledger.py` (the function about 40, the CLI about 15, `summary` 1, the docstring about 12).
- **Harness:** yes. `review_ledger.py`, `plugin/crew/tests/sabotage_review.py` and `plugin/crew/commands/review.md` are review/gate harness paths, so this lands alone as a tooling-only PR. Every other Touch path is in `ALONGSIDE`.

## Dependencies and work order

| Ticket | State | Why |
|---|---|---|
| L-0510 | done, on origin/main | Added the `auto-accepted` receipt kind and the reserved `auto:` prefix. The new verb must refuse both. |
| T-0100 | INDEX says approved; its build is on origin/main as crew 1.0.322 | Last change to `review_ledger.py`. The spec's line numbers were read after it. |
| T-0087 | merged | The tooling-PRs-land-alone rule this PR follows. |

Nothing open blocks this ticket. It can be worked at any time.

It blocks nothing by id. T-0029 (in progress; the subagent never-list for accept and reject) should add `--correct-acceptance` once both exist.

Related, same file, no forced order: T-0109 (direction; `--reject` on an accepted receipt), L-0569, L-0565, L-0596 and L-0580 (all direction), L-0522 (in progress; edits `check_receipt`, which this ticket does not touch), T-0033 (spec, on hold). Whichever lands second merges main and re-reads `main()`'s action group.

## Read before writing code

- The spec's `path:line` evidence was checked at origin/main `155fe6d8`. Main has moved since (the branch base is `ce235468`); re-check each anchor.
- No plan.md is published. The implementing session writes the plan.
- The ticket had no folder before 2026-10-04: direction.md and spec.md were both written from the INDEX row. No tests or gates were run when they were written.
- The verb must never touch the state, the rounds, the bundle hash, the base or `accepted_at`, and must not call `_current_hash`. `--check-receipt` gives the same answer before and after.
- Only an `owner-accepted` receipt can be corrected. An `auto-accepted` receipt has a fixed `accepted_by` that `receipt_stands` compares; changing it would make the receipt stop standing.
- `_load` is not changed. Only the correction verb refuses a malformed `acceptance_corrections`.
- No edit to `plugin/crew/tests/sabotage.py` (at the pylint module-line limit). The six mutations go in `sabotage_review.py`.
- The acceptance checks say pytest and sabotage go through "the repo's heavy-run wrapper". That wrapper is a local tool of the owner's machine and is not in the repo; whether a cloud session needs an equivalent could not be told.
- If T-0109 or L-0569 lands first and keeps the old receipt under another key, that copy is not corrected by this verb (spec, Unknowns).

## Open questions for the owner (recommended option taken)

1. Rewrite `accepted_by` and keep the old value in the history. Alternative: leave `accepted_by` as first written and have readers compute the effective name.
2. Keep the history on a top-level list that survives a successor plan. Alternative: on the receipt itself.
3. No separate field for who ran the correction; `--reason` is required and carries it, because the ledger cannot authenticate a caller.
4. Allow the verb in every ledger state, since it never changes the state. Alternative: only while ACCEPTED.
5. The verb does not reach a rejected row's `by`, or a receipt a successor plan already cleared. Out of scope.

## Before landing

Merge origin/main, take a crew version above main's from the coordinator, follow the repo's CLAUDE.md (scope discipline, doc updates for `plugin/crew` changes, tooling-PR rule), and remove `docs/tickets/T-0098/` in the final PR unless the owner wants it kept.

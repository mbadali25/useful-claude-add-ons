# Cloud handoff: T-0109

**review_ledger: an owner-attributed rejection supersedes an accepted receipt (`--reject --by <who> --supersede-accepted`)**

Handed to a cloud session on 2026-10-04 by owner instruction. Do not pick up locally.

- **Role:** standalone ticket (no split children).
- **INDEX status:** direction (spec written and approved for hand-off 2026-10-04; plan to be written by the implementing session). Spec risk: high.
- **Branch:** `T-0109-build`, new from origin/main `ce235468`; docs only, no implementation yet
- **Files here:** `docs/tickets/T-0109/direction.md`, `docs/tickets/T-0109/spec.md`
- **Size:** about 45 added production lines, all in `plugin/crew/hooks/scripts/review_ledger.py` (the guard in `reject` about 30, `summary` 2, `main` and argparse about 8, docstring about 6). `sabotage_review.py` gains about 45 lines; it is a test path.
- **Harness:** yes. `review_ledger.py`, `plugin/crew/tests/sabotage_review.py` and `plugin/crew/commands/review.md` are review/gate harness paths, so this lands alone as a tooling-only PR. Every other Touch path is in `ALONGSIDE`.

## Dependencies and work order

| Ticket | State | Why |
|---|---|---|
| T-0087 | merged | The tooling-PRs-land-alone rule this PR follows, and the ticket where the gap was found. |
| L-0510 | done | Added the `auto-accepted` receipt kind and the `auto:` prefix rule the guard reuses. Also the second incident (a hand-edited ledger). |
| T-0026 | merged | The approval receipt that `continue_with_successor_plan` reads after the override. Unchanged here. |

Nothing open blocks this ticket. It can be worked at any time.

This ticket blocks:

- L-0569 (direction): it cannot be scoped until this verb exists or is refused. T-0109 covers its options 1 and 2; only its `--rounds N` grant remains, and that part builds on the `superseded` row.
- T-0074 (direction): autopilot's out-of-rounds handling needs to know that an unattended `auto:` name can reject a REVIEWED ticket and can never supersede an accepted one.

Same file, no forced order; the second to land merges main and re-reads `reject` and `main()`'s argument group:

- T-0098 (direction, also handed to cloud on branch `T-0098-build`): the `accepted_by` correction verb.
- L-0565, L-0596, L-0580 (all direction): ledger hardening.
- L-0522 (in progress): edits `check_receipt`, which this ticket does not touch.
- T-0033 (on hold): receipt hash normalisation; touches `accept`, `auto_accept`, `check_receipt`, not `reject`.

## Read before writing code

- The spec's `path:line` evidence was checked at origin/main `155fe6d8`. Main has moved since (the branch base is `ce235468`); re-check each anchor.
- No plan.md is published. The implementing session writes the plan.
- The spec's "Design" section says "for the owner to confirm at approval". The defaults were taken without the owner; see the open questions.
- Plain `--reject` must keep refusing an ACCEPTED ticket. The existing test `test_reject_is_refused_and_changes_nothing[accepted]` still refuses; only its refusal-text assertion may be adjusted.
- Every refusal leaves the ledger file byte-identical. The tests compare bytes, not `status()`.
- The flag never falls back to a plain rejection: on any state but ACCEPTED it refuses.
- The override does not rebuild or compare the bundle hash.
- What the guard does not promise: the ledger cannot authenticate a caller, and `--reserve` already voids an acceptance with no name recorded (measured in the spec). The seed's "a non-owner cannot void an owner acceptance" is not something this ticket makes true. The docs must say `--by` is a recorded name, not a check of who is calling.
- `plugin/crew/commands/review.md` must not grow (548 lines against an allowance of 551). The edit rewrites line 509 in place.
- No edit to `plugin/crew/tests/sabotage.py` (at the pylint module-line limit). The eight mutations go in `sabotage_review.py`, and the existing entry anchored on the `reject` refusal line is re-anchored if its line moved.
- No migration or repair of ledgers already edited by hand.
- The two "Owner decision 2026-09-30" sections in direction.md were written for local lanes. Merge, never rebase, still applies. The heavy-run wrapper is a local tool and is not in the repo; whether a cloud session needs an equivalent could not be told.
- No tests or gates were run when the spec was written.

## Open questions for the owner (recommended option taken)

1. Flag or no flag: `--supersede-accepted` is required on `--reject`. Alternative: plain `--reject --by` overrides an ACCEPTED ticket, as the INDEX title reads.
2. Receipt kinds: all three known kinds (`clean`, `owner-accepted`, `auto-accepted`) can be superseded. Alternative: only `owner-accepted`.
3. Attribution: a required `--by` name plus the `auto:` refusal is taken as enough, given the ledger cannot authenticate a caller and `--reserve` already voids an acceptance unattended. Alternative: an owner-typed marker, which would need a new hook and its own ticket.
4. Should L-0569 be narrowed to its `--rounds N` grant once this lands? Assumed: yes. Neither L-0569 nor INDEX was edited.

## Before landing

Merge origin/main, take a crew version above main's from the coordinator, follow the repo's CLAUDE.md (scope discipline, doc updates for `plugin/crew` changes, tooling-PR rule), and remove `docs/tickets/T-0109/` in the final PR unless the owner wants it kept.

# Cloud handoff: T-0053

**autopilot sleep mode, slice 1: a schedule overlays `approval` and `questions`**

Handed to a cloud session on 2026-10-04 by owner instruction. Do not pick up locally.

- **Role:** parent of a split family. Children: L-0651, L-0652, L-0653, L-0654, L-0655, L-0656. This ticket is slice 1 only (the schedule, the resolver, the `approval` and `questions` overrides).
- **INDEX status:** ready (spec written and approved for hand-off 2026-10-04; plan to be written by the implementing session)
- **Branch:** `T-0053-build`, new from origin/main `ce235468`; docs only, no implementation yet
- **Files here:** `docs/tickets/T-0053/direction.md`, `docs/tickets/T-0053/spec.md`
- **Size:** about 175 production lines: a new `plugin/crew/hooks/scripts/crew_sleep.py` (about 110), `crew_autopilot.py` (about 50), `crew_state.py` (about 8), `crew_config_menu.py` (about 5), the config template (2). No harness path: this is an ordinary feature PR, and `python3 scripts/check-tooling-pr.py` must exit 0 on the branch.

## Dependencies and work order

Everything this ticket needs first is already on main, so it can be worked now.

| Ticket | State | Why |
|---|---|---|
| T-0010 | merged (PR #261) | Defines `autopilot.approval` and `autopilot.questions`, the two policies this slice overlays. |
| T-0072 | merged (PR #250) | `autopilot.deploy` and `deploy_allowed` read the same settings; this slice must leave them unchanged. |
| T-0018 | merged | The subcommand router and `status`, unchanged here. |
| T-0087 | merged | The tooling-PRs-land-alone rule that forces the sabotage mutations into separate PRs (L-0651, L-0655). |
| L-0510 | done | Review auto-accept of a 0-BLOCK round already runs at every hour, so no sleep review override is needed. |

Coordinates with, no order forced:

- T-0050 and T-0070 (both spec): a machine-global `autopilot` layer. Until either lands, sleep is repo-only.
- T-0019 / L-0611 (in-progress / direction), T-0012 (approved), T-0020 (approved): they edit `crew_autopilot.py` and `autopilot.md` too. Merge main before review; whichever lands second re-checks its anchors.

This ticket blocks: L-0651, L-0652, L-0653, L-0654, L-0655, L-0656, T-0057 (plain-text routing for `sleep` / `wake`, which needs L-0652), T-0054 (the autopilot guide's sleep section), T-0056 (a resumed goal re-checks sleep before its first decision; T-0056's own spec lists this as "coordinates, does not block"), T-0073 (its text assumes sleep auto-accepts only CLEAN rounds).

Family order:

1. T-0053 (this ticket): the schedule, the resolver, the `approval` / `questions` overrides.
2. After T-0053, in any order: L-0651 (sabotage mutations for slice 1, tooling-only PR), L-0652 (manual `sleep` and `wake`), L-0654 (the `deploy` override).
3. L-0653 (sleep log and morning summary): after T-0053 and L-0652.
4. L-0655 (sabotage mutations for L-0652 to L-0654, tooling-only PR): after L-0651, L-0652, L-0653 and L-0654.
5. L-0656 (overrides for keys that do not exist yet): BLOCKED until T-0029 or T-0067 (review half) and T-0051 (notify half) merge; also needs L-0653.

## Read before writing code

- The spec's `path:line` evidence was checked at origin/main `155fe6d8`. Main has moved since (the branch base is `ce235468`); re-check each anchor.
- No plan.md is published. The implementing session writes the plan.
- No edit to any harness path: `crew_ticket.py`, `scope_guard.py`, `review_*.py`, `plugin/crew/tests/sabotage*.py`. Sabotage mutations for this slice are L-0651.
- No clock override by environment variable or CLI flag. Tests pass `now` to `resolve` or monkeypatch in-process.
- Fail closed: anything that cannot be told (the schedule, an override value, the clock, a raising `resolve`) leaves the day values in force with a `warning:` line that names the key.
- `plugin/crew/commands/autopilot.md` is 109 lines against a tested budget of 110. At most one line may be added here.
- CONFIG.md leaf counts are re-measured by running `leaf_paths(default_config())`, not by arithmetic.
- direction.md carries two owner decisions of 2026-09-30 that still bind: catch up with main by merge (never rebase, force-push or squash), and the parallel suite shape. The wrapper path in that note is local to the owner's machine and is redacted.
- The config shape in the spec differs from the 2026-09-26 direction: overrides are direct keys of `autopilot.sleep`, with no `overrides` sub-object. The spec wins.

## Open questions for the owner (recommended option taken)

1. Morning re-ask: a plan self-approved under the night value stops standing when the window ends. Taken: keep it, pinned by a test. Alternative: a receipt written asleep stands until the ticket closes, which needs a `crew_ticket.py` change in its own tooling PR.
2. One window for every day (a single `HH:MM-HH:MM` string). Taken: yes. Alternative: per-weekday windows, a later ticket.
3. Manual `sleep` gating (L-0652). Taken: honoured only where `scope.allowCliApproval` is exactly `true`; `wake` is always allowed.
4. A manual `sleep` with no schedule configured (L-0652). Taken: it ends after 12 hours or at `wake`.
5. Should sleep be stricter than day about review findings? Taken: sleep leaves L-0510's 0-BLOCK auto-accept alone. The 2026-09-26 guardrail "never accept a review with any finding asleep" would need a harness change in `review_ledger.py`.
6. `autopilot.md`'s 110-line budget (L-0652 and L-0653). Taken: reword inside the budget and put the detail in command output. Alternative: raise the budget.
7. Config shape: overrides are direct keys (`autopilot.sleep.approval`, `autopilot.sleep.questions`), every default a scalar `null` leaf. Confirm.
8. L-0656 is blocked. Whether a held ping is dropped and counted (taken) or queued depends on T-0051's design.

## Before landing

Merge origin/main, take a crew version above main's from the coordinator, follow the repo's CLAUDE.md (scope discipline, doc updates for `plugin/crew` changes, tooling-PR rule), and remove `docs/tickets/T-0053/` in the final PR unless the owner wants it kept.

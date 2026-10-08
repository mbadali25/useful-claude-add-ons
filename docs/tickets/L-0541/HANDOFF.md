# Cloud handoff: L-0541

**autopilot goals: mint the approved split, drive the tickets in dependency order (`mode: backlog`), per-ticket approval, run caps, `--goal` resume**

Handed to a cloud session on 2026-10-05 by owner instruction. Do not pick up locally.

**Not buildable yet.** T-0012 (PR #354, branch `T-0012-build`) must merge first: this ticket replaces its
`MINT_PENDING` and `GOAL_RESUME_ARRIVES = "L-0541"` stubs and consumes its `split_approved`.

- **Role:** child, split from T-0012 (the part from "After the split approval" on, and T-0012 plan Step 3).
- **INDEX status:** spec (direction and spec approved for hand-off 2026-10-05; plan to be written by the implementing session)
- **Branch:** `L-0541-build`, new from origin/main `5c40ffa7`; docs only, no implementation yet
- **Files here:** `docs/tickets/L-0541/direction.md`, `docs/tickets/L-0541/spec.md`
- **Risk:** high (unattended picker; `backlog` widens where `approve` can run)
- **Size:** about 220 production lines, ~15 tests. No harness path.

## Dependencies and work order

| Ticket | State | Why |
|---|---|---|
| T-0012 | PR #354 draft, not merged | Goal file, proposal, split approval. Must merge first. Its branch is from `d67098ad`, far behind main. |
| T-0019, T-0010, T-0006 | merged | `crew_ticket.mint`, `settings`/`approve`, resume grammar. |

Blocks: T-0056 (#459), then L-0658 (#463) and L-0659 (#469), then L-0660 (#472).

## Read before writing code

- Evidence was checked at origin/main `5c40ffa7` and T-0012-build `ab1bb915`. Re-find every anchor by content after T-0012 merges.
- `crew_ticket.mint` has **no `risk` parameter**; do not add one. Risk goes in the minted direction body and stays in `tickets[].risk`.
- The two cap keys and `backlog` are `COMING` rows in `plugin/crew/hooks/scripts/crew_keys.py:524-530`; landing them moves those rows out.
- Token cap is input + output only, via a new `fields=` keyword on `crew_metrics.transcript_tokens` (default unchanged).
- No `plugin/crew/tests/sabotage*.py` edits here (harness, T-0087). File a follow-up tooling-only ticket for the picker/cap/approval mutations when this lands.

## Open questions for the owner (recommended option taken)

In direction.md: input + output token fields; minted ids use whatever `mint` returns (`T-####`); sabotage as a follow-up ticket.

## Before landing

Merge origin/main, take a crew version above main's from the coordinator, follow the repo's CLAUDE.md (scope
discipline, doc updates for `plugin/crew` changes, tooling-PR rule), and remove `docs/tickets/L-0541/` in the final PR unless the owner wants it kept.

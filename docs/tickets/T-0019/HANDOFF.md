# Cloud handoff: T-0019

**crew_ticket mint and assign (the autopilot assign route moved to L-0611)**

Handed to a cloud session on 2026-10-03 by owner instruction. The local lane died on the weekly usage limit. Do not pick up locally.

- **Branch:** `T-0019-assign` at `f922f487`, crew **1.0.157** set as the last plugin commit, origin/main `f808e5f0` merged.
- **Gates at f922f487:** `verify-gate --all` passed, the full crew suite passed, the 27 ASSIGN sabotage mutations all went red, `check-tooling-pr.py` OK. The full `sabotage.py` fails on the known main-wide L-0621 entries.
- **Review ledger:** round 2 of 2 used, REVIEWED, **not accepted**: 1 BLOCK, 5 FIX (Codex gpt-6-sol). Full output: `docs/tickets/T-0019/review-r2-out.txt`.
- **Owner decision (2026-10-03):** fix the BLOCK test-first, then run **round 3** under the owner's standing cap of 3. Record the grant with `review_ledger.py --reject --by "<owner grant ...>"`, then open a budget through an amended successor plan approved by `crew_ticket.py approve`, as T-0049 did.

## Round 2 findings
- **BLOCK** `crew_ticket.py:1225`: an Obsidian board failure after the INDEX move makes mint report `direction` while the row is `ready`, so autopilot can go past the promised stop.
- **FIX** `:1161`: a failed Obsidian card creation is treated as a successful mint.
- **FIX** `:1245`: a lock error leaves the claimed folder and direction behind.
- **FIX** `:1255`: a failed INDEX write leaves the vault note behind.
- **FIX** `:1377`: assign can hang on a FIFO at the staged path.
- **FIX** `:1439`: assign silently ignores `--title`.

Fix the FIX findings in the same pass where cheap, or put them in a follow-up ticket (ask the coordinator for the next free ID).

## Before landing
Merge origin/main (merge, not rebase). Take a crew version above main's from the coordinator: 1.0.157 is claimed for T-0019, so keep it if main is still below it. Refresh the code maps, diagrams and graph, run the gates, then round 3, then land with `gh pr merge --merge` and `/crew:done`. Follow the repo's CLAUDE.md. L-0611 (autopilot router, branch `L-0611-assign-router`) follows after this merges. Remove `docs/tickets/T-0019/` in the final PR unless the owner wants it kept.

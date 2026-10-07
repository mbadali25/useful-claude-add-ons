# L-0644: crew_ghdeploy.py prepare - refuse or snapshot before a GitHub Actions dispatch          status: direction   risk: high   priority: high

Split from T-0045 on 2026-10-04 (T-0045 direction.md, "Direction check 2026-10-04", option 1).

## Problem
`gh workflow run` prints no run id. To find the run a dispatch created, crew has to know what existed just before it: who the actor is, which runs of that workflow on that ref were already there, and that the sha it is about to deploy exists on the remote. Nothing records that today, so the only way to find the run afterwards is to guess from a list.

## Decision (kept from the owner's 2026-09-26 direction and plan.md "Design")
`crew_ghdeploy.py prepare --root . --env <E> [--index N]` runs before the dispatch. It refuses (exit 2, nothing written) on any problem, in a fixed order. Otherwise it writes a state file `.crew/.ghdeploy/<env>-<N>.json` and prints the literal dispatch command as its last line before `result=`. The session then runs that command as its own Bash call, so T-0009's guard and promote-gate both judge it. The helper never dispatches.

## Options considered
1. **Snapshot of run ids plus a timestamp (recommended, kept).** A new run is one whose id was not in the snapshot. No dependence on clock agreement alone.
2. Timestamp only. Fails when the local clock and GitHub's differ, and cannot tell a run queued one second earlier by someone else.
3. Require a correlation input in every workflow. Needs a change in each consumer repository; kept as an optional extra (`correlationInput`), not a requirement.

## Depends on
T-0045 (the entry and `check`), T-0009 (the dispatch classifier, PR #336 open on 2026-10-04), T-0005 (merged).

## Open questions for the owner
- If T-0009 has not merged when this is picked up: wait (default), or land `prepare` without the two classification refusals and add them in a follow-up.

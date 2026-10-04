# L-0672 direction: sabotage mutations for crew_tracker's per-component identity check          status: direction   risk: low
Split from T-0081 on 2026-10-04.
## Ask
T-0081 makes the vault walk match every directory's identity, on POSIX and on Windows. Its guard branches need committed mutations in `plugin/crew/tests/sabotage_tracker.py`, as every other `crew_tracker.py` guard branch has. That file is a review/gate harness path (`HARNESS` in `scripts/check-tooling-pr.py`), and a harness change may not share a PR with production code, so the mutations are their own tooling-only PR.
## Options
1. **Recommended, taken: one tooling-only PR after T-0081 merges**, adding one mutation per new guard branch, each aimed at the one test that sees that branch alone.
2. Leave the branches without committed mutations and rely on T-0081's by-hand sabotage. Rejected: `sabotage_tracker.py`'s own header says every guard branch gets one, and a by-hand check does not run again.
3. Land the mutations first. Not possible: an anchor must occur exactly once in `crew_tracker.py`, and the lines do not exist until T-0081 merges.
## Approval
Status `direction`. The owner was not available on 2026-10-04; option 1 is the default taken. Depends on T-0081 landing.
## Open questions for the owner
None beyond T-0081's question 2 (accepting the guard-first order).

# Cloud handoff: T-0080

**sabotage harness bounds memory: two cloud_guard entries read without bound and OOM-killed the session (sabotage_cloud.py:544, :564)**

Handed to a cloud session on 2026-10-04 by owner instruction. Do not pick up locally.

- **Role:** standalone ticket (no split children).
- **INDEX status:** direction (spec written and approved for hand-off 2026-10-04; plan to be written by the implementing session). Priority med.
- **Branch:** `T-0080-build`, new from origin/main `ce235468`; docs only, no implementation yet
- **Files here:** `docs/tickets/T-0080/direction.md`, `docs/tickets/T-0080/spec.md`
- **Size:** about 120 lines of harness code in a new `plugin/crew/tests/sabotage_bound.py`, and a net change of zero or less in `plugin/crew/tests/sabotage.py`. Nothing is added under `plugin/crew/hooks/`, `scripts/` or `skills/`.
- **Harness:** yes. `plugin/crew/tests/sabotage*.py` is a review/gate harness path, so this lands alone as a tooling-only PR. Tests, docs, version files, the code map and `.crew/verify.json` may ride along.

## Dependencies and work order

Must land first: none open.

| Ticket | State | Why |
|---|---|---|
| T-0087 | merged (PR #281) | The tooling-PR rule and the harness rule this change lands under. |
| L-0513 | done | The gate runner runs the sabotage step and already treats a timed-out or killed step as could-not-tell. This ticket adds the per-entry bound beneath it. |

The ticket facts and the spec agree.

Nothing blocks this ticket. It can be worked now.

This ticket blocks L-0525 (direction): its acceptance needs one uninterrupted full sabotage run, which needs this bound.

Related, not blocking: T-0082 (the verify gate's killed-rule handling; separate code, but it also adds entries to `sabotage_tooling.py`), L-0570 (gate-runner fixes; separate file), L-0676 and L-0679 (add entries to `sabotage_context.py`). Whichever lands second merges main and re-checks its anchors.

## Read before writing code

- The spec's `path:line` evidence was checked at origin/main `155fe6d8`. Main has moved since (the branch base is `ce235468`); re-check each anchor.
- A stale plan.md is not published. No plan.md existed for this ticket; the implementing session writes the plan.
- Measure first. The original report blamed the entry at `sabotage_cloud.py:544` for the 19.6 and 20.1 GB dumps, but by the code only the azureProfile entry (`:565`; the ticket title says `:564`) reads without bound. That was not re-measured. The spec's first step is to run each of the two entries alone, under a memory cap, and record peak memory. If `:544` does grow, tighten the plan-dev-zero test as the spec's Design says.
- An unbounded sabotage run can take the machine down. Run the two entries inside a memory-capped wrapper or container the first time. The local host uses a 6G cgroup wrapper for this; what a cloud session has in its place: could not tell.
- `plugin/crew/tests/sabotage.py` is at the pylint limit (3400 lines at the spec's base). It may not grow; new code goes in `sabotage_bound.py`, and lines are freed inside `sabotage.py`.
- `run_test` keeps its signature: `test_sabotage_harness.py` monkeypatches it.
- No new outcome that counts as a pass. A timeout is `RED BUT UNPROVEN` and fails the suite. An unreadable limit refuses to run; it never means the default or no cap.
- The cap must not make an unmutated test fail: pwsh starts under a 4 GiB address-space cap and dies under 2 GiB (measured on a Linux host). The spec requires the crew suite to give the same pass and skip counts with and without the cap. If it does not, raise the default or try `RLIMIT_DATA`; if neither is clean, stop and ask the owner. Do not exempt single tests.
- The full run still reports FAIL afterwards because of L-0525's 14 entries. That is L-0525's, not this ticket's.
- The two mutations themselves are kept unchanged; no change to `cloud_guard.py` or `scripts/gate-runner.py`.
- The direction file carries two older owner decisions that still apply: catch up with main by merge, never rebase; and run the suites with `-n 4` through the heavy-run wrapper.

## Open questions for the owner (recommended option taken)

1. Is a real-assertion RED under the memory cap acceptable in place of a separate `RED BY LIMIT` outcome that counts as a pass? Taken: yes, no pass-by-limit outcome.
2. Defaults of 4096 MiB per process and 600 s per entry, overridable by `CREW_SABOTAGE_MEM_MB` and `CREW_SABOTAGE_TIMEOUT_S`, with an unreadable value refusing to run? Taken: yes.
3. Windows and macOS get the timeout only, with the memory cap reported as absent, and no Windows job object. Taken: yes; a follow-up ticket if a Windows sabotage run is ever wanted.
4. Which entry grows memory (`:544` or only `:565`) was not re-measured. The spec makes the implementer measure both first.
5. Confirm that no single test may be exempted from the cap if an unmutated test fails under it.

## Before landing

Merge origin/main, take a crew version above main's from the coordinator, follow the repo's CLAUDE.md (scope discipline, doc updates for `plugin/crew` changes, tooling-PR rule), and remove `docs/tickets/T-0080/` in the final PR unless the owner wants it kept.

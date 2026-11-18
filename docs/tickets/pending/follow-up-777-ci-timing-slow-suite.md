# #777 (Stop audit runs natively on Windows): read CI, measure Stop-path timing, finish the slow suite

Priority: unassigned (owner to set).
Status: needs ticket (no T-/L-/C- id yet). Recorded 2026-11-17. A read-and-measure agent is running on this; this ticket tracks whatever remains after it reports.
Siblings: `follow-up-780-full-suite-and-unidentified-failure.md`.

## Problem

#777 moves the Stop completion audit (`completion-audit.sh`) to native Python on Windows through `crew_hook.DIRECT`. Three things are still open on its head.

## Evidence

VERIFIED by `gh pr view 777` on 2026-11-17: head `19892aa8e`, draft, base `main`, DIRTY (conflicts with main), last PR update 2026-11-16T11:09Z. Rollup: 25 SUCCESS, 5 FAILURE: `check-draft (version bump pending at land)`, `test (3.12)`, `crew-shell-matrix (ubuntu-latest)`, `crew-windows-default (5/6)`, `crew-shell-matrix (windows-latest)`. Crew 1.3.132 per the owner; the PR body's last round names 1.3.131.

1. CI on the head is unread. An earlier ubuntu failure, `test_the_marker_name_is_the_one_the_wrapper_writes`, was not reproduced; whether it is a flake or a defect is UNDETERMINED. (The PR body says the test's inner cap was raised from 300 s to 900 s because it took 287 s.)
2. Stop-path timing is not measured after the change. The PR body says `verify-gate.sh` and `context-watch.sh` are not touched and "still start Git Bash on Stop (follow-up)". Its before/after figures cover only the completion audit (wrapper 39 to 49 s, native 0.2 to 0.6 s, the whole audit dispatch 1.5 s, all from the PR body, not re-run here).
3. The slow Git Bash suite (`-m slow`) timed out at 1700 s, exit 124, on a heavily loaded host: one pass, one skip, the rest never ran (PR body, last review round). Fast set: 39 passed.

## Recommended next step

Read each failing job's log on `19892aa8e`; classify the ubuntu failure as flake or defect by re-running that job and by reading the test. Measure the whole Stop path (all three Stop hooks) before and after on an unloaded host. Run the slow set in shards with per-case time bounds, or in CI, so it can finish. Decide whether `verify-gate.sh` and `context-watch.sh` get the same native route (separate ticket).

## Acceptance criteria

- Each of the five failing checks has a named cause (VERIFIED) or is shown to pass on rerun.
- The marker-name test is classified, with the run that shows it.
- Stop-path wall time is reported per hook with the host, load and layer (`.crew/config.json` or `~/.claude/crew/config.json`) stated.
- The slow suite completes, or the cases that cannot are listed with a reason.

## Owner questions

1. Is a flake with one passing rerun enough, or must the marker-name test be root-caused?
2. Is the follow-up to move `verify-gate.sh` and `context-watch.sh` native in scope here or a new ticket?

## Out of scope

Merging (approved order puts #777 first; the owner decides); changing the Stop-row timeout or config keys.

## Related

#777 (`fix/stop-audit-native-python`), `plugin/crew/hooks/scripts/crew_hook.py`, `plugin/crew/tests/test_crew_hook_stop_native.py`, `sabotage_crew_hook.py`, `verify-gate.sh`, `context-watch.sh`. PR #777 is a harness PR and lands alone.

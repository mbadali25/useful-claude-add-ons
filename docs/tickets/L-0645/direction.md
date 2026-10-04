# L-0645: crew_ghdeploy.py identify - exactly one new workflow run, or could-not-tell          status: direction   risk: high   priority: high

Split from T-0045 on 2026-10-04 (T-0045 direction.md, "Direction check 2026-10-04", option 1).

## Problem
After the session runs the dispatch, crew must name the run it created. `gh workflow run` prints no id, and `gh run list` shows every run of that workflow. A guess here means watching and recording someone else's run as this deploy.

## Decision (kept from the owner's 2026-09-26 direction: "more than one candidate, or none within a timeout, is could-not-tell: stop, never guess")
`crew_ghdeploy.py identify --root . --env <E> [--index N]` reads L-0644's state file and polls `gh run list` with the same filters. A candidate is a run whose id was not in the snapshot, with event `workflow_dispatch`, on the entry's ref, created no earlier than `t0` minus 30 seconds. When a correlation id was sent, the run's display title must contain it, with no fallback to the time rule. One candidate is the run and its id is written into the state file. Anything else is could-not-tell (exit 3).

## Options considered
1. **Snapshot difference, then the correlation id when configured (recommended, kept).**
2. Newest run wins. Simple and wrong under two concurrent dispatches.
3. Read the run id from the dispatch's own output. gh 2.46.0 documents none.

## Depends on
L-0644 (the state file).

## Open questions for the owner
- None new. `identifySeconds` default 120 is carried from 2026-09-26.

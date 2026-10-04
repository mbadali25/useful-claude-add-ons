# L-0651: sabotage mutations for the sleep schedule overlay (tooling-only PR)

Split from T-0053. Written 2026-10-04 against origin/main `155fe6d8`.

## Ask
T-0053 adds a schedule parser and a fail-closed resolver that can turn `approval: risk` into
`self`. Its tests have to be shown able to fail. The mutations that prove it live in
`plugin/crew/tests/sabotage_autopilot.py`, a harness path, so they cannot ride in T-0053's PR.

## What exists
- `plugin/crew/tests/sabotage*.py` is in `HARNESS` (`scripts/check-tooling-pr.py:79`). A branch
  that changes one may carry only `ALONGSIDE` paths: tests, docs, version files, code map, graph.
- `sabotage_autopilot.py` holds `AUTOPILOT_MUTATIONS`, with `DEPLOY_MUTATIONS` and
  `STATUS_MUTATIONS` appended to it (`:28`, `:473`, `:674`). `sabotage.py` already registers
  `AUTOPILOT_MUTATIONS`, so a new tuple appended there needs no edit to `sabotage.py`, which is at
  the 3400-line pylint limit.
- The standing owner rule (2026-09-30): when the tooling-PR check refuses, land the feature PR,
  then the tooling PR, without asking.

## Options
1. **A tooling-only PR after T-0053 merges (recommended).** `SLEEP_MUTATIONS` appended to
   `AUTOPILOT_MUTATIONS`, one mutation per must-block branch, each red on a named test.
2. Put the mutations in a new non-harness file. Refused: `sabotage*.py` is a glob, and a renamed
   file to dodge it is the thing the rule exists to stop.
3. Skip sabotage for sleep. Refused: the resolver grants approval authority.

## Recommendation
Option 1.

## Depends on
T-0053 (the code the mutations edit). T-0087 (merged) for the rule.

## Approval
Not yet approved. Prepared for hand-off on 2026-10-04 under the owner's go for T-0053.

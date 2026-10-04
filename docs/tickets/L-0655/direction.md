# L-0655: sabotage mutations for manual sleep, the sleep log and the deploy override (tooling-only PR)

Split from T-0053. Written 2026-10-04 against origin/main `155fe6d8`.

## Ask
L-0652, L-0653 and L-0654 each add branches that must refuse: a state file that cannot be trusted, a log
line that could forge an entry, a production deploy asleep. Their tests have to be shown able to
fail, and the mutations live in a harness path.

## What exists
The same facts as L-0651: `plugin/crew/tests/sabotage*.py` is `HARNESS`
(`scripts/check-tooling-pr.py:79`), `AUTOPILOT_MUTATIONS` in `sabotage_autopilot.py` is already
registered, and the standing rule is feature PR first, tooling PR after.

## Options
1. **One tooling-only PR after L-0652 to L-0654 have merged (recommended).** One review round for
   three small mutation sets.
2. One tooling PR per child. Three PRs, three harness runs, for the same lines.
3. Fold these into L-0651. Refused: L-0651 can land right after T-0053; this cannot.

## Recommendation
Option 1. If one of L-0652 to L-0654 is cut or delayed, land this for the ones that merged and say
so in the PR body.

## Depends on
L-0652, L-0653 and L-0654. L-0651 first, so `SLEEP_MUTATIONS` exists.

## Approval
Not yet approved. Prepared for hand-off on 2026-10-04 under the owner's go for T-0053.

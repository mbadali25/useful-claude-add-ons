# L-0646: crew_ghdeploy.py watch - pass, fail or unknown from the run and its deploy job          status: direction   risk: high   priority: high

Split from T-0045 on 2026-10-04 (T-0045 direction.md, "Direction check 2026-10-04", option 1).

## Problem
A green workflow run is not a deploy. A run whose deploy job was skipped by a condition reports success having shipped nothing, `gh run watch` has no timeout, and a watch that could not run looks the same as one that never finished. promote.md already says "check the job, not the run"; nothing does it.

## Decision (kept from the owner's 2026-09-26 direction and plan.md "Design")
`crew_ghdeploy.py watch --root . --env <E> [--index N]` watches the identified run in slices that fit the Bash tool's limit and then reads the run itself. The watch command's exit code is recorded and never decides. The verdict comes from `gh run view --json`: pass needs conclusion `success`, a matching deploy job that itself succeeded when `deployJob` is set, and the right head sha when no sha input was sent. Anything unreadable, or still running at the deadline, is `unknown`. The run is never cancelled.

## Options considered
1. **Watch in slices, then classify from the run view (recommended, kept).**
2. Trust `gh run watch --exit-status`. It cannot see a skipped deploy job and has no timeout.
3. Poll `gh run view` only. Works, but loses the live progress the owner asked for ("watches it with gh run watch").

## Depends on
L-0645 (the run id in the state file).

## Open questions for the owner
- `watchMinutes` default 60, carried from 2026-09-26.
- When `deployJob` is not configured: pass with the detail "deploy job not checked" (default, kept), or refuse to call it a pass.

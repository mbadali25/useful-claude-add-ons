# L-0649: autopilot's deploy phase - promote to the first nonProd GitHub environment after the merge          status: direction   risk: high   priority: high

Split from T-0045 on 2026-10-04 (T-0045 direction.md, "Direction check 2026-10-04", option 1).

## Problem
Autopilot stops when the ticket closes. `autopilot.deploy` (T-0072, merged) already says where a deploy may run without asking, and `deploy_allowed` already answers per environment, but nothing asks it: `settings` warns that the key is inert and names T-0045 as the consumer.

## Decision (owner, 2026-09-26, adjusted to what T-0072 merged)
After T-0011's ship phase reports the PR merged, `crew_autopilot.py next` names a `deploy` phase whose command is `/crew:promote <env>` for the first environment in `.crew/verify.json` that has a `github` entry and that `deploy_allowed` allows. Anything it cannot tell stops with `deploy-target`. A recorded row for that environment and sha that is not all-pass stops with `failed-deploy`; autopilot never re-deploys and never rolls back. The session still runs promote's full sequence, so T-0009's guard and promote-gate decide every dispatch.

## Options considered
1. **`next` names the phase; promote does the work (recommended, kept).** One deploy path, attended or not.
2. Autopilot calls `crew_ghdeploy.py` directly. A second sequence that skips promote's gates 3 to 5.
3. A separate `/crew:autopilot deploy` subcommand. More surface for the same decision.

## Depends on
T-0011 (ship phase, approved, not built on main), T-0009 (the classifier and the guard, PR #336 open), T-0072 (merged), T-0045 and L-0644 to L-0648.

## Open questions for the owner
- T-0072's `all` can allow production. The 2026-09-26 direction said autopilot never deploys to production. Default: follow `deploy_allowed` exactly and proceed only on `allow`, so production needs T-0072's opt-in in both config layers. Alternative: hard-code nonProd only in this phase.
- `autopilot.md` has one line left under its tested cap of 110. Default: reword section 4's existing "No deploy" sentence in place; all detail goes in `crew_autopilot.py` output.
- Which sha: the reviewed HEAD, which must equal the merged PR's head. Carried from 2026-09-26.

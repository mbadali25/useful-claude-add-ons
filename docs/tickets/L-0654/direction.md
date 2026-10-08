# L-0654: sleep deploy override, nonprod only

Split from T-0053. Written 2026-10-04 against origin/main `155fe6d8`.

## Ask
Owner, 2026-09-26: while asleep autopilot "runs non-production deploys; production always waits".

## What exists
- `autopilot.deploy` is `none|nonprod|all` and `deploy_allowed` answers `allow|ask|refuse` for one
  environment (T-0072, merged; `crew_autopilot.py:162`, `:957`). `all` allows production only with
  `environments.prodUnattended` true in both config layers and `guards.cloudGuard: block`.
- Nothing dispatches a deploy yet: T-0045 is at `direction`. `settings` warns about that
  (`crew_autopilot.py:811`).
- After T-0053, an `autopilot.sleep.deploy` key is reported as "not available in this crew
  version".

## Options
1. **`autopilot.sleep.deploy` accepts only `nonprod`; and while asleep `all` reads as `nonprod`
   (recommended).** Both rules sit in the one place `deploy_allowed` reads its settings.
2. Accept any `DEPLOY_VALUES` value as the override. Refused: `sleep.deploy: all` would be
   unattended production at night, the opposite of the ask.
3. Wait for T-0045. The policy can be built and tested now through `deploy-allowed`; waiting only
   delays it.

## Recommendation
Option 1. It is inert until T-0045 consumes `deploy_allowed`, and says so.

## Depends on
T-0053. T-0072 (merged). T-0045 consumes it later.

## Approval
Not yet approved. Prepared for hand-off on 2026-10-04 under the owner's go for T-0053.

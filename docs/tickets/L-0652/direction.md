# L-0652: manual /crew:autopilot sleep and wake

Split from T-0053. Written 2026-10-04 against origin/main `155fe6d8`.

## Ask
Owner, 2026-09-26: sleep mode is entered "based on time of day or setting". T-0053 builds the time
of day. This is the setting: `/crew:autopilot sleep` when leaving early, `/crew:autopilot wake`
when back before the window ends.

## What exists
- After T-0053: `crew_sleep.resolve(block, now)` answers `off|awake|asleep|unknown` from the
  schedule alone, and `_settings_at` applies the overrides when it says `asleep`.
- `crew_autopilot.SUBCOMMANDS` is `("status", "run", "assign", "goal", "focus")`; `route` refuses
  any other first word (`crew_autopilot.py:224`, `:1299`).
- `crew_autopilot.py` is read-only except `approve`, and a test holds that
  (`test_crew_autopilot_policy.py:682`). README.md:859 states it as a design rule.
- `autopilot.md` has a tested 110-line budget.

## Options
1. **A state file under `<git-common-dir>/crew/`, written only by `sleep` and `wake`
   (recommended).** It records the state, who set it, when, and when it ends. It beats the
   schedule until its `until` time, which is the next window edge. `sleep` is honoured only where
   `scope.allowCliApproval` is exactly `true`; `wake` always is.
2. A config edit (`autopilot.sleep.manual: "asleep"`). No new file, but the command would rewrite
   `.crew/config.json`, a tracked file, and leave a diff on every use.
3. An environment variable. Refused: the session can set it, nothing records it, and it does not
   survive `/clear`.

## Recommendation
Option 1. The state lives beside `approval.json`, is shared by every worktree of the repo like
the config is, and is a file a test can corrupt.

## Guardrails
- Could not tell wakes: a state file that is unreadable, not an object, missing a field, has an
  `until` in the past or more than 24 hours ahead, or an `at` in the future reads as "no manual
  state" with a warning.
- `sleep` grants only what `autopilot.sleep.*` already configures. With no override configured it
  says so and changes nothing.
- `wake` during a scheduled window holds until that window's end; it never extends past it.

## Open questions
- Gating of a session-run `sleep`. Recommendation taken: `scope.allowCliApproval: true`.
- No schedule configured. Recommendation taken: the manual sleep ends after 12 hours.
- The 110-line budget. Recommendation taken: reword inside it; the detail is printed by the CLI.

## Depends on
T-0053. L-0651 is not required first.

## Approval
Not yet approved. Prepared for hand-off on 2026-10-04 under the owner's go for T-0053.

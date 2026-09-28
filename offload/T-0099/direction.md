# T-0099 direction          status: new   risk: low
## Ask
Owner, 2026-09-28 ~12:17 CDT, accepted T-0092's review round 2 ("Accept, fix at land") and had its two NITs filed as tickets. This is NIT (a).
## Facts
T-0092 round 2 (Claude reviewer, same family; Codex out until Oct 3; bundle 3f3be3f2d187 at 68d34203; ledger "review-ledger: round 2 FINDINGS accepted by Matthew Badali at 2026-09-28T17:17:01+00:00"), verbatim NIT: "plugin/crew/hooks/scripts/review_prompt.py:90|A manifest that records `"excluded": []` (nothing was left out, a known answer) prints `excluded: none recorded`, which is the same line a manifest with no `excluded` key gets (unknown). The two states collapse into one line. It cannot happen today because `EXCLUDED` is a non-empty literal, but the test pins only the missing-key case." Evidence given: "`rp.build(root, "T9", dict(MANIFEST, excluded=[]))` gives `  excluded: none recorded`, the same as `rp.build(root, "T9", MANIFEST)`."
This is the project CLAUDE.md "unknown collapsing into the safe-looking value" pattern: a known-empty list and a missing key must print different lines. Landed with T-0092 (PR #257, crew 1.0.54).
## Options
1. **Print a distinct line for each state (recommended):** `excluded (never in the bundle): none` for `[]`, `excluded: not recorded by this manifest (unknown)` for a missing key; a test for each, plus a sabotage entry that collapses them.
2. Leave it: unreachable while `EXCLUDED` is a non-empty literal. Cheaper, but the next change to `EXCLUDED` inherits the collapse silently.
## Recommendation
Option 1, small /crew:fix; one crew version past origin/main at land.
## Open questions
none.
## Approval
Status `new`.

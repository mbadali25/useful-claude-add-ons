# L-0641 direction - sabotage mutations for the ticket-state module

Split from T-0037 on 2026-10-04. Not yet approved by the owner.

## Why a separate ticket
`plugin/crew/tests/sabotage*.py` is a `HARNESS` path in `scripts/check-tooling-pr.py` (origin/main 155fe6d8). The owner's standing rule for a tooling-PR refusal is: feature PR first, then the tooling PR. L-0639 and L-0640 are the feature PRs; this is the tooling PR that proves their must-block tests go red when the rule they guard is removed.

## Facts
- `plugin/crew/tests/sabotage.py` is 3400 lines, exactly `.pylintrc`'s `max-module-lines=3400`. Its sibling lists are imported at `:67-88` and concatenated at `:3064-3071`.
- The mutation tuple shape is `(label, target, find, replace, test)` (`sabotage.py:3365`).
- Approved T-0037 plan Step 7 listed these mutations under `sabotage_ticket_state.py`.

## Recommendation
A new sibling `sabotage_ticket_state.py`, registered with a net-zero line change in `sabotage.py`. No production file changes.

## Depends on
L-0639 and L-0640.

## Open questions for the owner
- L-0550 and L-0551 will need the same feature-then-tooling pairing for their own mutations. Default taken: they append to `sabotage_ticket_state.py` in their own tooling PRs; not in scope here.

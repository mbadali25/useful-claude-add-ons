# L-0686 direction - sabotage mutations for autopilot's hold, landing, needs-owner, closed and blocked stops

Status: seed (not yet approved). Split from L-0550 on 2026-10-04. Checked against origin/main `155fe6d8`.

## Why this is its own ticket
L-0550 adds five must-stop branches to `crew_autopilot._phase`. Crew's rule for that file is one mutation per must-stop branch, each proven red on a named test (`.crew/verify.json:359`, the autopilot rule's `why`). The mutations live in `plugin/crew/tests/sabotage_autopilot.py`, which matches `plugin/crew/tests/sabotage*.py` in `HARNESS` of `scripts/check-tooling-pr.py` (`:58-87`). A harness change lands alone (owner rule 2026-09-28, T-0087): `crew_autopilot.py` and `commands/autopilot.md` are not in `ALONGSIDE`, so L-0550's feature PR cannot carry them. This ticket is the tooling PR that follows it.

## Facts
- `sabotage_autopilot.py` is 1118 lines against `.pylintrc:140` `max-module-lines=3400`. Its tuples are `(label, target, find, replace, test)` (`:1-14`).
- `AUTOPILOT_MUTATIONS` is already imported by `plugin/crew/tests/sabotage.py:77` and concatenated at `:3066`. A tuple appended to it inside `sabotage_autopilot.py` (as `STATUS_MUTATIONS` is at `:674` and `ASSIGN_MUTATIONS` at `:1118`) runs with no edit to `sabotage.py`, which is at its 3400-line limit.
- `test_every_autopilot_sabotage_anchor_is_present_exactly_once` (`plugin/crew/tests/test_crew_autopilot.py:1336`) already walks `AUTOPILOT_MUTATIONS`, so new entries are anchor-checked without a new test.
- Existing anchors that L-0550 must not break: `"    if status in INDEX_DONE:\n"` (`sabotage_autopilot.py:126`), `"    if status not in DIRECTION_APPROVED:\n"` (`:122`), and the `_closed` anchor (`:616`).

## Options
1. **(Recommended, taken) A `GATE_MUTATIONS` tuple in `sabotage_autopilot.py`, appended to `AUTOPILOT_MUTATIONS`.** No `sabotage.py` edit, no new file, no dependency on L-0641.
2. Put them in L-0641's `sabotage_ticket_state.py`, as that spec suggests. Keeps ticket-state mutations in one file, but makes this ticket wait on L-0641 and targets a different module than the file's name says.

## Recommendation
Option 1.

## Open questions for the owner
- Option 1 or 2 above. Taken: option 1.

## Next
/crew:spec is done (spec.md beside this file). /crew:plan once L-0550 has merged, because the `find` strings are taken from its merged code.

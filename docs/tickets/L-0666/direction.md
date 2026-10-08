# L-0666: autopilot stop messages name only owner decisions (a contract test over every stop)

Split from T-0067 on 2026-10-04. Status: direction, recommended option taken (owner not available). Risk: med.

## Ask
Owner, 2026-09-27, on an autopilot stop that told him to run a graph build and start the next review round: "It shouldn't be asking me these questions on auto pilot". T-0067 (the parent) makes autopilot do the round-1 fix itself. This slice makes the rule checkable for every stop: a stop may ask the owner for a decision, never for a mechanical step.

## Measured (origin/main `155fe6d8`, crew 1.0.322)
- `plugin/crew/hooks/scripts/crew_autopilot.py` has 18 `answer(<phase>, True, ...)` stop sites in `_phase`, `_review_phase` and `_toward_review` (:421-562), three guard stops in `next_phase` (:588, :594, :598), and the `stopped(...)` sites in `resume_target` (:668-727).
- Stops that hand the owner a mechanical step today:
  - :519-521 "run review_ledger.py --auto-accept --follow-up <id> (/crew:review step 3)";
  - :524-525 "or fixes then /crew:review";
  - :591 "run crew_autopilot.py resume";
  - :368-371 an unsettled-artifact stop lists `(refresh: <command>)` for each artifact a refresh would settle.
- `next_phase`'s docstring (:570-571) already says a stop's `command` "is what the HUMAN types". Nothing tests it.
- `stops()` (:1283) lists stop ids and texts. No field says what the owner is being asked to decide.

## Options
1. **A closed list of owner decisions, a closed list of mechanical command shapes, and a test that walks every stop (recommended).** Every stop carries a `decision` id. Its `command` is empty or the one command registered for that decision. Its reason contains no mechanical command shape. A completeness test counts the stop sites in the source, so a new stop cannot be added without a case.
2. **Reword the four messages and add no contract.** Smaller, and the next stop added repeats the problem.
3. **A lint over the reason strings only.** No `decision` field. Cheaper, but a stop whose `command` is a raw tool would pass.

## Recommendation
Option 1.

## Open questions for the owner (recommendation applies)
- When the auto-accept guard passes but no receipt was written, the stop names only the owner's accept (recommended), or autopilot finishes the auto-accept itself (that is acceptance policy, T-0073's).
- Re-pointing the worktree at another ticket (`crew_ticket.py activate`) stays an owner decision (recommended: it changes which approval governs the edits), or autopilot does it.

## Depends on
T-0067 (the parent slice; same function, and its `fix` phase is what the FINDINGS stop refers to). Blocks L-0668.

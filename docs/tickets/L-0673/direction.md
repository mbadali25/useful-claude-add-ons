# L-0673: the CI receipt's per-command list never reads a missing failure line as PASS; verify.md documents "could not tell"
Split from T-0082. status: direction   risk: low

## Ask
`ci_receipt.parse_log` builds the per-command list in the CI receipt and its job summary from the gate log. A command is PASS when its elapsed line has no `VERIFY FAILED` or SKIP line before it (plugin/crew/hooks/scripts/ci_receipt.py:199, `pending.pop(cmd, "PASS")`). The list is informative only; acceptance rests on `review_gate.gate_state`. It is still the shape T-0082 was filed against: a pass for want of a failure line. After T-0082 the gate prints `verify-gate: COULD NOT TELL (<reason>): <cmd>`, and the list should show it.

`plugin/crew/commands/verify.md` describes rule outcomes ("Exit 77 is SKIP", :220) and needs the new outcome. Both files are outside the harness list, so they cannot ride in T-0082's tooling PR.

## Options
1. (Recommended) Add an UNKNOWN state read from the `COULD NOT TELL` line, and mark a command UNKNOWN, not PASS, when the gate's exit status was not 0 and the log ends without the total line (the gate died mid-run). Document in verify.md.
2. Docs only. Leaves the list wrong for a killed gate.

## Recommendation
Option 1. Owner not available 2026-10-04; taken as the default.

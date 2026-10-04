# L-0674: the verify gate ends a hung rule itself and reports it FAILED (could not tell)
Split from T-0082. status: direction   risk: high

## Ask
T-0082 makes a killed or unrecorded rule fail. It does not bound a rule that never ends. Today the gate waits for as long as the rule runs (plugin/crew/hooks/scripts/verify-gate.sh:2054). In Stop mode the hook's own 600 second timeout (plugin/crew/hooks/hooks.json:58-59) then ends the gate from outside. The turn is not blocked by a hook that timed out, and the log names no rule. The original report was a rule that sat idle for about 25 minutes per case.

## What is already decided
Per-rule process-group tracking and kill-on-signal shipped once and was descoped in crew 1.0.21 after five review rounds each found the fix one case short (verify-gate.sh:1834-1843, plugin/crew/CONFIG.md:2576). Any design here must not bring that back.

## Options
1. (Recommended) A whole-run deadline in Stop mode only, fixed under the hook timeout, with no group kill. When the deadline passes while a rule runs, the gate stops waiting, sends TERM then KILL to its own direct wrapper child only, prints `VERIFY FAILED` and `COULD NOT TELL (the gate's deadline passed while this command was running)`, marks every command not yet run as not run, and exits 2. Anything the rule left behind is covered by the existing documented limitation. `--all` and `--ci` stay unbounded: the caller (gate-runner, the CI job's timeout) bounds them and already reads their death as could-not-tell.
2. A per-rule timeout from a new config key or from each rule's declared `seconds`. More precise, but a new config surface (a feature path mixed with harness paths) and a false failure whenever a host is slow.
3. Do nothing: rely on the marker not advancing. The turn still ends unblocked after a hang.

## Recommendation
Option 1, but HELD: it reopens ground the owner closed in 1.0.21, so it needs an owner go before it is planned. Owner not available 2026-10-04.

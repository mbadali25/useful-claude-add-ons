# T-0082 verify gate: a rule passes only on a completion record; killed or unrecorded is FAILED (could not tell)          status: spec   risk: high
## Refreshed 2026-10-04
First spec for this ticket; written against origin/main `155fe6d8` (crew 1.0.322). See direction.md "Direction check 2026-10-04". No plan.md exists. The ticket was split: this spec is the first slice, L-0673 and L-0674 are in `children/`.

## Intent
A rule command in `verify-gate.sh` and `verify-gate.ps1` counts as passed only when its wrapper ended with status 0 and left a completion record that says the rule exited 0. A rule that was killed, signalled, could not be started, or left no readable record is FAILED with the reason "could not tell". That state is printed, counted in the summary, written to the command log with its own status, and never advances the marker or the fingerprint.

## Design (taken as the default; owner to confirm)
- **Completion record.** Before each rule the gate makes a second temp file path beside the output-capture file and removes the file, so absence means "not written". The wrapper writes the rule's exit status to it after the rule ends:
  - bash: `( ( eval "$c" ); printf '%s\n' "$?" > "$RULE_DONE_FILE" ) >"$RULE_OUT_FILE" 2>&1 </dev/null &`. The inner subshell keeps the isolation a rule's own `exit N` needs. Measured 2026-10-04: with this shape `wait` returns 0 and the record holds 0, 3, 137 or 143 for a rule that passed, exited 3, or was ended by KILL or TERM; killing the outer wrapper gives `wait` 137 and no record.
  - PowerShell: the same line inside the existing `bash -c` wrapper script, the record path handed over in `CREW_VERIFY_RULE_DONE` and unset before `eval`, as `CREW_VERIFY_RULE_OUT` is today.
- **One decision table, the same in both flavours, evaluated in this order:**

  | Fact | Status | Reason printed |
  |---|---|---|
  | no usable bash, or no capture or record file could be made | unknown | the existing refusal text |
  | the wrapper could not be started (PowerShell: `$rc` is still `$null`) | unknown | `the rule's shell could not be started` |
  | wrapper status is not 0 | unknown | `the rule's runner ended with status N before it recorded a result` |
  | record missing, empty, not 1-3 digits, or above 255 | unknown | `no completion record` |
  | record above 128 | unknown | `exit status N: ended by signal N-128, or the rule's own status` |
  | record is 77 | skip77 | unchanged |
  | record is 0 | pass | |
  | anything else | fail | unchanged |

- **What "unknown" prints.** `VERIFY FAILED: <cmd>` first (so every reader of that line still sees a failure), then `verify-gate: COULD NOT TELL (<reason>): <cmd>`, then the last 25 output lines. It sets `FAILED`, so the run exits 2 and neither marker advances.
- **Command log.** The status is the string `unknown`. `verify_record._sync` already leaves the record untouched for a status that is not pass, covered, fail or skip77 (verify_record.py:987-994); `passes-save` and coverage credit accept only `pass`. The code path does not change; the comment and docstring that call it unreachable do.
- **Summary.** After the total line: `verify-gate: N rule command(s) COULD NOT BE JUDGED - counted as FAILED`, printed only when N is above 0.
- **PowerShell.** `$rc = $null` at the top of every rule, and `$global:LASTEXITCODE` is no longer preset to 0 as the answer. A launch failure leaves `$rc` `$null`.
- **Signalled bash gate.** The TERM, INT and HUP traps print `VERIFY FAILED: <cmd>` and `verify-gate: COULD NOT TELL (the gate received <SIG> while this command was running): <cmd>` when a rule is in flight, before the cleanup and the unchanged `exit 128+N`. Printed from the trap itself, because the cleanup dispatcher discards its functions' stderr (verify-gate.sh:774-779).

## Exclusions
- No timeout, deadline or watchdog. The gate still waits for a rule as long as it runs. That is L-0674.
- No process-group tracking and no kill of anything a rule leaves behind. The crew 1.0.21 descope and CONFIG.md's limitation stand.
- No change to `ci_receipt.py` or `commands/verify.md`: both are outside the harness list, so they are L-0673.
- No change to what a plain failure, a SKIP (77), a deferral, coverage credit or the tree-pass cache does. No change to exit codes: a failed run exits 2, a signalled gate exits 128+N.
- No "could not tell" line from a PowerShell gate that is itself killed: PowerShell has no signal trap. The marker not advancing is what covers that case, as today.
- No persisted "unknown" entry in `.crew/.verify-gate.record.json`, for the reason `_sync` gives for not persisting a failure (verify_record.py:953-977).
- No fix to `scripts/_test/uv-install.sh` (T-0076, done) and no change to `scripts/gate-runner.py` (L-0513, done).
- No edit to `plugin/crew/tests/sabotage.py` (3400 lines, at the pylint module limit).
- No new hook and no new config key.

## Evidence
All read at origin/main `155fe6d8` on 2026-10-04.
- plugin/crew/hooks/scripts/verify-gate.sh:2012-2015 the capture file (`mktemp`, then `.crew/`). :2053-2055 `( eval "$c" ) >"$RULE_OUT_FILE" 2>&1 </dev/null &`, `wait`, `RC=$?`. :2108-2116 the refusal when no capture file can be made (`RC=1`). :2121-2134 the three-way branch: 77, non-zero, else `CMD_STATUS="pass"`. :2135 `STATUS_AT`. :2138 the elapsed line. :2144 the command-log line. :2157 the total line.
- plugin/crew/hooks/scripts/verify-gate.sh:774-779 `_crew_gate_run_cleanup` runs each function with `2>/dev/null`. :791-794 the TERM, INT, HUP and EXIT traps.
- plugin/crew/hooks/scripts/verify-gate.sh:1834-1843 the note that per-rule process-group kill was descoped.
- plugin/crew/hooks/scripts/verify-gate.ps1:1944 `$global:LASTEXITCODE = 0`. :2029 `$rc = 1` (no bash). :2054-2056 the wrapper script, the call, `$rc = $LASTEXITCODE`. :2153 `$rc = 1` (no capture file). :2162-2173 `$cmdStatus = "pass"` then the 77 and non-zero tests. `$rc` is assigned nowhere else, and the rule loop starts at :1867.
- Measured 2026-10-04, pwsh on Linux: `$null | & '/nonexistent/bash' -c 'exit 3'` inside `try { } finally { }` prints the error, skips the following assignment and continues after the block with the script exiting 0.
- Measured 2026-10-04, bash on Linux, the nested-subshell wrapper: see Design.
- plugin/crew/hooks/scripts/verify_record.py:827 the `cmd_log` status list in the docstring. :899-907 `status_by_cmd`. :953 the fail branch. :987-994 the branch for any other status. :689 `passes-save` takes `"pass"` only.
- plugin/crew/hooks/scripts/ci_receipt.py:117-119 the three log patterns; :199 `pending.pop(cmd, "PASS")`. :97-99 `GATE_IMPL` includes `verify-gate.sh` and `verify_record.py`.
- plugin/crew/hooks/scripts/review_gate.py:10-21 the gate is judged from the marker and fingerprint, not from its exit status.
- plugin/crew/hooks/hooks.json:58-59 both Stop hooks, timeout 600.
- scripts/check-tooling-pr.py:58-87 `HARNESS` lists `verify-gate.sh`, `verify-gate.ps1`, `verify_record.py` and `plugin/crew/tests/sabotage*.py`. :99-118 `ALONGSIDE` lists `plugin/crew/tests/**`, README.md, CONFIG.md, BUDGETS.md, the version files, CHANGELOG.md, `docs/**`, `.crew/codemap/**`, `.crew/verify.json`, `graphify-out/**`. `plugin/crew/commands/verify.md` and `ci_receipt.py` are in neither.
- plugin/crew/tests/sabotage_tooling.py:287-288 `GATE_SH`, `GATE_PS1`; :290 onward the gate mutations, the `.ps1` ones appended only where pwsh exists. 1055 lines. plugin/crew/tests/sabotage.py:82 and :3069 already import and register `TOOLING_MUTATIONS`.
- plugin/crew/tests/test_verify_gate_rule_framing.py:36-58 the fixture conventions for a gate test: `crew_fixtures.resolve_bash()`, `shutil.which("pwsh")`, `crew_fixtures.GATE_SUBPROCESS_TIMEOUT_S`.
- .crew/verify.json:122-137 the gate's own rule; `run` at :135 names its test files one by one, so a new file must be added there.
- Docs that describe the rule outcome: plugin/crew/CONFIG.md:2576-2577 (the background-process limitation), plugin/crew/README.md:2859 (the hook table row), docs/guides/crew/src/troubleshooting.md:79, .crew/codemap/verification-harness.md.
- Nothing on main implements this: `git grep -n "COULD NOT TELL\|RULE_DONE" origin/main -- plugin/crew/hooks/scripts/verify-gate.sh plugin/crew/hooks/scripts/verify-gate.ps1` prints nothing.

## Unknowns
- What the 2026-09-27 Windows run actually returned. Not reproducible on Linux. Resolved before review: run the new test file natively on the Windows box (the pre-push matrix), and add the case "the rule's process is ended by a native kill" there. If a native kill of the wrapper yields `wait` 0, the missing record is what fails it; the test pins that.
- Whether a rule's own exit status above 128 exists in any shipped map (it would now print "could not tell" instead of a plain failure; it fails either way). Resolved at implement: `git grep -n "exit 1[3-9][0-9]\|exit 2[0-9][0-9]" -- .crew/verify.json plugin/crew/skills`.
- Git Bash `mktemp` and a second temp file per rule: cost and cleanup on every exit path. Resolved at implement: the record file is removed where the capture file is, and the tests assert no `.verify-rule-*` file is left in `.crew/`.
- Tests that pin the gate's stderr exactly may see the new lines. They only appear on an unknown outcome, so none should change; resolved by running the gate's rule (.crew/verify.json:122).
- `ci_receipt.check` refuses a CI receipt for a branch that changes `verify-gate.sh` or `verify_record.py` (GATE_IMPL), so this branch must pass the gate locally. Accepted.
- The next free crew patch version is set at implement time.

## Touch
- plugin/crew/hooks/scripts/verify-gate.sh
- plugin/crew/hooks/scripts/verify-gate.ps1
- `plugin/crew/hooks/scripts/verify_record.py` - the comment at :987 and the docstring at :827 only
- plugin/crew/tests/test_verify_gate_rule_completion.py
- plugin/crew/tests/sabotage_tooling.py
- plugin/crew/README.md
- plugin/crew/CONFIG.md
- plugin/crew/BUDGETS.md
- docs/guides/crew/src/troubleshooting.md
- `docs/guides/crew/**` - the HTML, DOCX and PDF rebuilt by the guide build script
- .crew/codemap/verification-harness.md
- .crew/codemap/crew.md
- .crew/verify.json
- CHANGELOG.md
- plugin/crew/.claude-plugin/plugin.json
- plugin/PLUGINS.md
- .claude-plugin/marketplace.json

Not in Touch, stated: `plugin/crew/commands/verify.md` and `plugin/crew/hooks/scripts/ci_receipt.py` (L-0673; outside the harness and ride-along lists); `plugin/crew/tests/sabotage.py` (at the line limit; nothing to register); `docs/diagrams/` (no box or edge changes; a regenerated anchor is a refresh artifact).

## Acceptance checks
Commands run from the repo root, through the heavy-run wrapper on a memory-bound host. Each test below is parametrised `[sh]` and `[ps1]` unless it says otherwise; the `[ps1]` cases skip without pwsh. All are in `plugin/crew/tests/test_verify_gate_rule_completion.py`, run as `python3 -m pytest plugin/crew/tests/test_verify_gate_rule_completion.py -q -k <name>`.
- [ ] Must-allow: a rule that exits 0 passes, the run exits 0, the marker advances, and stderr has no `COULD NOT TELL`. `-k test_a_rule_that_exits_0_passes`
- [ ] Must-allow: a rule that exits 1 prints `VERIFY FAILED` and no `COULD NOT TELL`; a rule that exits 77 is still SKIP. `-k test_plain_failure_and_skip_are_unchanged`
- [ ] Must-allow: a rule whose text calls `exit 0`, and one that sets its own `trap ... EXIT`, still pass. `-k test_a_rule_with_its_own_exit_or_trap_passes`
- [ ] Must-block: a rule ended by SIGKILL mid-run exits the gate 2 with `COULD NOT TELL` naming the status. `-k test_a_rule_killed_mid_run_could_not_tell`
- [ ] Must-block: the wrapper is killed before it writes the record (the rule kills its wrapper; the fixture finds that pid per flavour and never signals `$$` or `$PPID` under `[sh]`, which are the gate and the test). The gate exits 2 with `no completion record` or the runner-status reason. `-k test_no_completion_record_could_not_tell`
- [ ] Must-block: a record that is empty, non-numeric or above 255 is could-not-tell. The record path is a plain shell variable the rule can see, so the fixture rule overwrites it from a background job that outlives the rule (one case per bad value). `-k test_unreadable_record_could_not_tell`
- [ ] Must-block, `[ps1]` only: the first rule passes, the second rule's bash cannot be started (the resolved bash is removed by the first rule). The second reads could-not-tell, not a pass. `-k test_ps1_launch_failure_does_not_inherit_the_previous_status`
- [ ] Must-block: an external timeout that kills the rule's process (`timeout -s KILL 1 ...` around the rule's child, and the same from outside on the wrapper) reads failed in both shapes. `-k test_a_rule_timed_out_from_outside_is_failed`
- [ ] Must-block: after an unknown outcome the marker and the fingerprint are not written, later rules still run, and the summary line gives the count. `-k test_unknown_never_advances_the_marker`
- [ ] The command log carries `"status": "unknown"`, `verify_record` sync leaves the rule's prior record entry as it was, and `passes-save` does not store it. `-k test_unknown_status_is_never_recorded_clean`
- [ ] `[sh]` only: TERM sent to the gate while a rule runs gives exit 143 and both lines naming the command; with no rule in flight it prints neither. `-k test_a_signalled_gate_names_the_command_in_flight`
- [ ] No `.verify-rule-*` file and no temp record file is left after pass, fail, unknown and a signalled gate. `-k test_no_record_file_is_left_behind`
- [ ] Sabotage, each mutation in `sabotage_tooling.py` turning its named test red through `python3 plugin/crew/tests/sabotage.py`:
  - (a) sh: pass on wrapper status alone (record not read)
  - (b) sh: pass on the record alone (wrapper status not read)
  - (c) sh: a missing record reads as 0
  - (d) sh: status above 128 reads as a plain failure
  - (e) sh: `unknown` logged as `pass`
  - (f) sh: the trap's in-flight lines removed
  - (g) ps1: `$rc` not reset per rule
  - (h) ps1: the record not read
  - (i) ps1: `unknown` does not set `$failed`
- [ ] Every new sabotage anchor is present exactly once: `python3 -m pytest plugin/crew/tests/test_sabotage_harness.py -q`.
- [ ] The gate's own rule passes with the new file added to its `run` list: run the command at .crew/verify.json:135 exactly as written there.
- [ ] Windows: the new file passes natively in the crew shell matrix job, both flavours.
- [ ] Tooling-only: `python3 scripts/check-tooling-pr.py` prints `tooling-pr: OK`.
- [ ] Docs: CONFIG.md and README.md state the completion-record rule and the "could not tell" outcome; troubleshooting.md has an entry for the `COULD NOT TELL` line with each reason; the guide outputs are rebuilt; both code maps describe the record. Crew is bumped to the next free patch with a CHANGELOG entry, and `python3 scripts/check-marketplace.py` passes after the commit.

## Size and split
- This slice: about 150 added production lines (`verify-gate.sh` about 70, `verify-gate.ps1` about 75, `verify_record.py` about 5). One fail-closed state machine (the completion-record decision), written twice, once per flavour. Every production path is in `HARNESS`: a tooling-only PR.
- L-0673 (`children/1`): `ci_receipt.parse_log` stops reading a missing failure line as PASS, and `commands/verify.md` documents the outcome. Feature paths, about 30 lines. Lands after this ticket.
- L-0674 (`children/2`): a gate-owned deadline for a hung rule. A second state machine, harness paths, about 180 lines. Held for an owner decision.

## Dependencies
Must land first (all have):
- T-0087 (merged): the tooling-PRs-land-alone rule and the harness list this ticket lands under.
- L-0513 (done): `scripts/gate-runner.py` already treats the gate's own death as COULD-NOT-TELL; this ticket does not touch it.
- L-0572 (done): coverage credit reads `STATUS_AT` and accepts only `pass`; `unknown` relies on that.
- T-0076 (done): the `uv-install.sh` hang that produced the report.
- T-0077 (merged): the lane that reported it.

Related, same files, no order forced: T-0068 (spec; crew's own bookkeeping writes, including gate records), T-0095 (direction; the gate's ruff rule message), T-0080 (direction; sabotage memory bound), L-0618 (direction; QA-environment practice, whose standard 23 names this ticket as the gate twin).

Blocks: L-0673 and L-0674. L-0618's standard 23 ("a runner never PASSes an aborted run") cites this ticket for the gate.

## Open questions for the owner
1. Design: positive completion record (taken) or label-only? Default taken: completion record.
2. A rule's own exit status above 128 is printed as "could not tell". Accept, or keep it a plain failure and call only a missing record unknown? Default taken: could not tell.
3. Should a signalled gate exit 2 instead of 128+N so a Stop hook blocks the turn? Default taken: keep 128+N; the marker not advancing covers it.
4. Build L-0674 (the deadline) at all, given the 1.0.21 descope? Default taken: hold.

## Split
- L-0673 (child 1 of T-0082, filed 2026-10-04): the CI receipt's per-command list never reads a missing failure line as PASS; verify.md documents "could not tell"
- L-0674 (child 2 of T-0082, filed 2026-10-04): the verify gate ends a hung rule itself and reports it FAILED (could not tell) - HOLD, needs owner go

## Approval
Spec approved for cloud hand-off by the orchestrator under the owner's standing authority, 2026-10-04. Plan: to be written by the implementing session.

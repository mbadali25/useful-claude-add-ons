# L-0674: the verify gate ends a hung rule itself and reports it FAILED (could not tell)          status: spec   risk: high
Split from T-0082. Written 2026-10-04 against origin/main `155fe6d8`. **HOLD: needs an owner go** (direction.md, option 1 against option 3). Build only after T-0082 has merged; re-read the line numbers then.

## Intent
In Stop mode the gate gives itself a deadline shorter than the hook's timeout. A rule still running at the deadline is reported FAILED as "could not tell", the gate exits 2 and names the rule, and no marker advances. The turn is blocked by the gate's own answer and not ended by the hook being killed.

## Exclusions
- No process-group tracking, no session or pgid proof, no kill of anything but the gate's own direct wrapper child. What a rule leaves running stays the documented limitation.
- No deadline under `--all` or `--ci`.
- No config key. The deadline is a constant derived from the hook timeout, with a test-only environment override in the style of `CREW_VERIFY_GATE_TEST_RULE_OUT_CAP`.
- No change to the Stop budget's choice of which rules to run, to deferral, or to T-0082's decision table other than one new reason.
- No change to `hooks.json`.

## Evidence
Read at origin/main `155fe6d8`.
- plugin/crew/hooks/scripts/verify-gate.sh:2053-2055 the backgrounded wrapper and the unbounded `wait`. :791-794 the signal traps. :1834-1843 the descope note.
- plugin/crew/hooks/scripts/verify-gate.ps1:2054-2056 the synchronous `& $bashExe -c` call: PowerShell cannot stop waiting on it, so this flavour must start the wrapper as a process object and wait with a bound, as `Resolve-CrewPython` does at :297-306.
- plugin/crew/hooks/hooks.json:58-59 timeout 600 for both flavours.
- plugin/crew/CONFIG.md:2576-2577 the limitation text.
- plugin/crew/tests/test_verify_gate_stop_budget.py: the Stop budget tests; test_verify_gate_stop_gate_record.py:2239 `test_run_gate_kills_the_whole_group_on_timeout_not_just_the_direct_child` is the test helper's own timeout, not the gate's.
- scripts/check-tooling-pr.py:58-87: both gate scripts and `sabotage*.py` are harness paths.

## Unknowns
- How the host ends a hook at its timeout (which signal, whether to the group). Resolved before plan: read the current hooks documentation and measure with a rule that sleeps past a short test timeout.
- The deadline value. Default: 540 seconds (the hook's 600 less a margin for the record sync and lock release). Resolved at plan by timing the post-loop work on the largest map.
- Bash has no bounded `wait` before 4.3's `wait -n` and no timeout on `wait <pid>`. Resolved at plan: a sleeper child that signals the gate with a trapped signal at the deadline (the `wait` builtin returns at once on a trapped signal, verify-gate.sh:2035-2038), with the sleeper reaped on every exit path. This is the part most likely to cost review rounds.
- Git Bash: whether TERM to a wrapper started from Git Bash ends it. Resolved on the Windows box before review.
- Starting the wrapper as a process object in PowerShell changes how its environment and stdin are passed. Resolved at implement against the existing env-leak and stdin tests.

## Touch
- plugin/crew/hooks/scripts/verify-gate.sh
- plugin/crew/hooks/scripts/verify-gate.ps1
- plugin/crew/tests/test_verify_gate_rule_deadline.py
- plugin/crew/tests/sabotage_tooling.py
- plugin/crew/README.md
- plugin/crew/CONFIG.md
- plugin/crew/BUDGETS.md
- docs/guides/crew/src/troubleshooting.md
- `docs/guides/crew/**` - the rebuilt HTML, DOCX and PDF
- .crew/codemap/verification-harness.md
- .crew/verify.json
- CHANGELOG.md
- plugin/crew/.claude-plugin/plugin.json
- plugin/PLUGINS.md
- .claude-plugin/marketplace.json

## Acceptance checks
All in `plugin/crew/tests/test_verify_gate_rule_deadline.py`, parametrised `[sh]` and `[ps1]`, marked `wallclock`, run as `python3 -m pytest plugin/crew/tests/test_verify_gate_rule_deadline.py -q -m wallclock -k <name>`. The deadline is shortened through the test-only override.
- [ ] Must-block: a rule that sleeps past the deadline in Stop mode: the gate exits 2 within the deadline plus a stated margin, prints `VERIFY FAILED` and the deadline reason naming the rule, and writes no marker or fingerprint. `-k test_a_hung_rule_ends_at_the_deadline_as_could_not_tell`
- [ ] Must-block: commands after the hung one are reported as not run, never as passed, and their record entries are left as they were. `-k test_commands_after_the_deadline_are_not_run`
- [ ] Must-allow: a run that finishes before the deadline is unchanged, and no sleeper process is left. `-k test_a_run_inside_the_deadline_is_unchanged`
- [ ] Must-allow: `--all` and `--ci` run a rule longer than the Stop deadline to completion. `-k test_all_and_ci_have_no_deadline`
- [ ] The override is ignored unless it is 1 to 3 digits and no larger than the default. `-k test_the_deadline_override_is_bounded`
- [ ] No sleeper, wrapper or temp file is left after: pass, deadline, and a gate signalled before the deadline. `-k test_nothing_is_left_behind`
- [ ] Sabotage in `sabotage_tooling.py`, each red through `python3 plugin/crew/tests/sabotage.py`: (a) sh: the deadline never fires; (b) sh: a deadline reads as a pass; (c) sh: the deadline applies under `--all`; (d) ps1: the bounded wait replaced by an unbounded one; (e) ps1: a deadline does not set `$failed`.
- [ ] The existing gate rule passes: the command at .crew/verify.json:135 with the new file added.
- [ ] Windows: the new file passes natively in the crew shell matrix job.
- [ ] `python3 scripts/check-tooling-pr.py` prints `tooling-pr: OK`.
- [ ] Docs: CONFIG.md states the deadline beside the limitation and says plainly that left-behind processes are still not reaped; README.md and troubleshooting.md name the new reason; guides rebuilt; code map updated. Crew bumped with a CHANGELOG entry; `python3 scripts/check-marketplace.py` passes after the commit.

## Size
About 180 added production lines (`verify-gate.sh` about 70, `verify-gate.ps1` about 110). One fail-closed state machine (the deadline). Tooling-only PR.

## Dependencies
- T-0082 (direction, spec-ready): must merge first; this adds one reason to its decision table and reuses its lines.
- Owner decision (open): whether to build this at all.
- T-0087 (merged): tooling PRs land alone.
Related: L-0513 (done) bounds `--all` runs from outside already.
Blocks: nothing.

## Approval
Spec approved for cloud hand-off by the orchestrator under the owner's standing authority, 2026-10-04. Plan: to be written by the implementing session.

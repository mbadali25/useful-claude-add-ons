# L-0673: the CI receipt's per-command list never reads a missing failure line as PASS; verify.md documents "could not tell"          status: spec   risk: low
Split from T-0082. Written 2026-10-04 against origin/main `155fe6d8`. Build only after T-0082 has merged; re-read the line numbers then.

## Intent
The per-command list in the CI receipt shows UNKNOWN for a command the gate could not judge, and for a command whose outcome the log does not carry because the gate died. `commands/verify.md` states the completion-record rule and the "could not tell" outcome. Acceptance of a receipt does not change.

## Exclusions
- No change to what `ci_receipt.build` or `check` accept: `pass`, the gate state, the gate rc, outstanding entries and the clean-tree test stay as they are.
- No change to `verify-gate.sh`, `verify-gate.ps1`, `verify_record.py`, `review_gate.py` or the workflow file.
- No new receipt schema version: `commands[].state` gains one value, and nothing reads that field for a decision.

## Evidence
Read at origin/main `155fe6d8`.
- plugin/crew/hooks/scripts/ci_receipt.py:117-119 `_ELAPSED_RE`, `_SKIP_RE`, `_FAILED_RE`. :184-200 `parse_log`; :199 the PASS default. :255 `build(root, gate_rc, gate_log, ...)` has the gate's exit status beside the log.
- plugin/crew/tests/test_ci_receipt.py:75 `test_parse_log_reads_pass_fail_and_skip_and_ignores_the_total_line`.
- .crew/verify.json:516 the rule for `ci_receipt.py` and its test.
- plugin/crew/commands/verify.md:220-226 "Exit 77 is SKIP".
- scripts/check-tooling-pr.py:58-87: neither path is in `HARNESS`.
- T-0082's spec: the `COULD NOT TELL` line format and the `verify-gate: <N>s total across` line.

## Unknowns
- The exact `COULD NOT TELL` line text is fixed by T-0082's merged code, not by its spec. Resolved at implement: read it from origin/main and pin it with a fixture log captured from a real run of the merged gate.
- Whether the job summary writer truncates or colours states. Resolved at implement by reading `build`'s `--summary` path.

## Touch
- plugin/crew/hooks/scripts/ci_receipt.py
- plugin/crew/tests/test_ci_receipt.py
- plugin/crew/commands/verify.md
- plugin/crew/README.md
- plugin/crew/BUDGETS.md
- docs/guides/crew/src/troubleshooting.md
- `docs/guides/crew/**` - the rebuilt HTML, DOCX and PDF
- .crew/codemap/verification-harness.md
- CHANGELOG.md
- plugin/crew/.claude-plugin/plugin.json
- plugin/PLUGINS.md
- .claude-plugin/marketplace.json

## Acceptance checks
Run as `python3 -m pytest plugin/crew/tests/test_ci_receipt.py -q -k <name>`; the rule is .crew/verify.json:516.
- [ ] A log with `VERIFY FAILED: c`, `verify-gate: COULD NOT TELL (...): c` and the elapsed line gives `c` the state UNKNOWN. `-k test_parse_log_reads_could_not_tell_as_unknown`
- [ ] A log that ends without the total line: every command with an elapsed line keeps its parsed state, and the receipt records `log_complete: false`; with a gate rc other than 0 the summary says the list is partial. `-k test_parse_log_marks_a_log_without_the_total_line_incomplete`
- [ ] The existing pass, fail and skip parse is unchanged. `-k test_parse_log_reads_pass_fail_and_skip_and_ignores_the_total_line`
- [ ] `check` still accepts and refuses exactly what it did: the whole file passes, `python3 -m pytest plugin/crew/tests/test_ci_receipt.py -q`.
- [ ] Sabotage-tested by hand and stated in the PR: restore `pending.pop(cmd, "PASS")` for the unknown case and the first test goes red. No sabotage module is edited (those are harness paths).
- [ ] `python3 scripts/check-tooling-pr.py` passes for a feature PR (no harness path in the diff).
- [ ] verify.md has a section beside "Exit 77 is SKIP" stating: a rule passes only on a completion record; the reasons a rule reads "could not tell"; that it fails the turn and never advances the marker. Crew is bumped with a CHANGELOG entry; `python3 scripts/check-marketplace.py` passes after the commit.

## Size
About 30 added production lines, all in `ci_receipt.py`. No new parser or state machine: one more pattern in an existing one. Feature PR.

## Dependencies
- T-0082 (direction, spec-ready): must merge first; it creates the line this reads.
- L-0555 (done; the CI receipt): the module being changed.
Blocks: nothing.

## Approval
Spec approved for cloud hand-off by the orchestrator under the owner's standing authority, 2026-10-04. Plan: to be written by the implementing session.

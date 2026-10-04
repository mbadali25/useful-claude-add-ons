# T-0082 direction          status: direction   risk: high
## Ask
Filed 2026-09-27 ~22:45 CDT by owner decision ("File ticket"). Reported by a Windows machine running `verify-gate.sh --all` natively for T-0077: the rule for `scripts/_test/uv-install.sh` hung (each pwsh harness case sat idle ~25 minutes, no child process, empty calls file); the runner was killed at 2108s, and the gate then recorded NO `VERIFY FAILED` for that rule - only its duration. A killed or hung rule reads as a pass.

That is the repo's recurring bug shape (project CLAUDE.md, Lessons): an unknown collapsing into the safe-looking value. The gate decides pass/fail from the absence of a failure line instead of from a positive completion signal.

Direction to settle at brainstorm: a rule passes only on a positive completion record (exit status captured, runner finished); a rule killed, timed out, signalled, or with no completion record is FAILED as "could not tell", and that state survives into the gate record, the marker logic and every summary line (bash and PowerShell gates alike). Tests: a rule killed mid-run, a rule timing out, a rule whose runner exits without output - each must read failed; sabotage entries for each. The uv-install.sh pwsh hang itself belongs to T-0076.
## Options
none yet - to be settled at /crew:brainstorm.
## Approval
Status `direction`. Risk high: it is the merge gate.

## Owner decision 2026-09-30 - catch up with main by MERGE, never rebase
the owner, 2026-09-30, verbatim choice "Merge main in (Recommended)", after "rebase alot fo these before merge we did 4-5 prs outside of here that merged to main". origin/main has moved (it was a61a6f38 when this note was written: T-0088 #262, the QA fixes #263-#267, crew 1.0.69).
- Before your NEXT Review round and again right before Land: `git fetch origin && git merge origin/main` (a merge commit; mechanical conflicts only - a behavioural conflict is a STOP to the owner). Never `git rebase`, never force-push, never squash.
- After each merge: version one patch past origin/main's, refresh the artifacts until fresh and committed, re-run the suites serially under heavy-run, and state the merged origin/main sha in the phase evidence.
- A review receipt that went stale ONLY because of such a merge follows the existing merge-only rule; anything else needs a new round.

## Owner decision 2026-09-30 - run the suites in parallel (pytest-xdist installed, capped at 4)
the owner, 2026-09-30, verbatim choice "Install + cap at -n 4 (Recommended)". pytest-xdist 3.8.0 is now installed (apt python3-pytest-xdist); <local-tmp>/heavy-run exports PYTEST_XDIST_AUTO_NUM_WORKERS=4, so `-n auto` means 4 workers inside the wrapper.
- Full crew suite, always through heavy-run: `python3 -m pytest plugin/crew/tests/ -q -n 4 -m "not wallclock"`, then `python3 -m pytest plugin/crew/tests/ -q -m wallclock` serially (both must pass). This is main's own .crew/verify.json rule with the worker count pinned. Other pytest suites: same shape.
- pylint as CI runs it: `python3 -m pylint -j 4 $(git ls-files "*.py")`.
- Quote the new timing in the evidence (the serial full suite took ~700-900s here; #263 measured ~230s at -n 4).
- A test that passes serially and fails only under -n 4 is a real finding (shared-state race, as #267's d3cf73c3), not something to paper over: report it, never skip it.

## Direction check 2026-10-04
Checked against origin/main `155fe6d8` (crew 1.0.322). Owner not available; the recommended option is taken and the questions are listed in spec.md.

**Still true**
- No ticket or commit on origin/main changes how `verify-gate.sh` or `verify-gate.ps1` decides a rule passed. `git log origin/main --grep T-0082` finds nothing; the only T-0082 mentions are cross-references (CHANGELOG.md:1894, scripts/gate-runner.py:494 and :870, docs/review/09-qa-standards-crew.md:191 and :262).
- Both gates still call a rule a pass from one number and nothing else. Bash: `wait` then `RC=$?` (verify-gate.sh:2054-2055), pass at :2133. PowerShell: `$rc = $LASTEXITCODE` (verify-gate.ps1:2056), `$cmdStatus = "pass"` set before the test (:2162). There is no record written by the rule's runner that says "I finished, with this status".
- A PowerShell hole, measured 2026-10-04 with pwsh on Linux: when the resolved bash cannot be started, `& $bashExe` raises inside the `try`, the `$rc = $LASTEXITCODE` line is skipped, and execution continues after `finally`. `$rc` is never reset per rule (assigned only at verify-gate.ps1:2029, :2056, :2153), so it still holds the PREVIOUS rule's value. If that rule passed, this one reads as a pass. `$global:LASTEXITCODE = 0` at :1944 has the same direction: the unknown starts as the safe-looking value.
- A killed rule and a rule that ran and failed print the same thing (`VERIFY FAILED: <cmd>`). Nothing says "could not tell".
- A gate that is itself signalled (TERM, INT, HUP) releases its lock and exits 128+N (verify-gate.sh:791-793) without naming the command that was running. The log then holds no `VERIFY FAILED` line for it.
- `ci_receipt.parse_log` reads a command as PASS when its elapsed line has no `VERIFY FAILED` or SKIP line before it (ci_receipt.py:199, `pending.pop(cmd, "PASS")`). It is labelled informative only, but it is the exact shape the ticket names.

**Changed since 2026-09-27**
- L-0513 (done) added `scripts/gate-runner.py`, which already treats timeout, signal death, could-not-start and a missing result as COULD-NOT-TELL for the lane suites. That covers the runner around the gate, not the gate's own per-rule decision.
- T-0087 (merged) did the review-side twin and made `verify-gate.*` harness paths, so this ticket lands as a tooling-only PR.
- `review_gate.gate_state` and `ci_receipt` judge the gate from what a clean pass leaves behind (the marker and fingerprint), not from its exit status or log. A killed gate leaves neither, so the consumers that matter already read it as UNVERIFIED. The remaining gap is inside the gate and in the log.
- On Linux bash a killed rule already fails: measured 2026-10-04, a rule ended by SIGKILL or SIGTERM gives a non-zero `wait` status. The 2026-09-27 Windows report (a pass after a native kill) was not reproduced here and cannot be on this host. A native Windows kill that ends the process with exit code 0 would explain it; that is a hypothesis, not a measurement.
- T-0076 (done) owns the `uv-install.sh` hang itself.

**Options**
1. (Recommended, taken) Positive completion record. The rule's wrapper writes the rule's exit status to a record file after the rule ends. A rule passes only when the wrapper ended 0 AND the record exists AND it says 0. Anything else that is not a clean exit status is FAILED as "could not tell", printed with its reason, counted in the summary and logged with its own status. Fix the PowerShell stale `$rc`. A signalled bash gate names the command it was running. Both flavours, one tooling PR.
2. Label only: keep the exit-status decision, print "could not tell" when the status is above 128. Cheaper, but a kill that reports 0 still passes, and the PowerShell hole stays.
3. Option 1 plus a gate-owned per-rule deadline that ends a hung rule. A second fail-closed state machine, and it reopens the process kill that crew 1.0.21 descoped after five review rounds. Split out as L-0674, held for an owner decision.

**Split**
- This ticket: option 1 (harness paths only).
- L-0673: `ci_receipt.parse_log` and `commands/verify.md` (feature paths, cannot ride in a tooling PR).
- L-0674: the gate-owned deadline (option 3's extra half).

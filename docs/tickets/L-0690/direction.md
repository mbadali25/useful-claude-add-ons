# L-0690 direction - a timed-out python probe must not read as "no python"

Status: direction, written 2026-10-04 against origin/main 86d96fa1 (crew 1.0.328). The owner filed the ticket on 2026-10-04 and was not available for the brainstorm; every choice below took the recommended option and is listed under "Open questions for the owner".

## Ask
Reported on 2026-10-04 by a session working in another repository on a Windows machine, against crew 1.0.256.

crew's Stop hook `plugin/crew/hooks/scripts/completion-audit.ps1` printed, twice that day:

    COMPLETION AUDIT: no usable python - the tree was not audited against the ticket's scope.

Python was present. Three `python3` are on PATH, `python` and `py` also resolve, and `completion-audit.ps1 -PrintPython` run by hand returned the first one every time (for example `C:\Python\python3.exe`), in about 255 ms on a quiet machine and 467 to 1223 ms under load. Both failures happened while a full test suite was running (CPU at 99%, about 100 other processes).

The reporter asks for four things:
1. Tell "the probe timed out" from "no python found" in the message. A timeout must say so.
2. On a failed probe, write which candidate was tried and how long each took, to stderr or a log file.
3. Consider caching the resolved interpreter across hook runs in a session, or giving the first PATH hit a longer budget before giving up: the audit is skipped exactly when the machine is busiest.
4. Consider whether a skipped audit should be a visible WARN and not look like a hard failure of the stop.

The reporter can run a diagnostic build on that machine.

## Cause: an inference, not a finding
The hook logs nothing about the probe, so the cause is not proven. The likely one: `Resolve-CrewPython` has an 8000 ms total budget and a 3000 ms bound per candidate; under load the budget ran out, the function returned `''`, and the caller printed the sentence it prints for "python is not installed". Reading the function at origin/main shows five different ways a present, working python ends as `''`, and the caller cannot tell any of them apart:

- the candidate was killed at its wait bound (completion-audit.ps1:146-155);
- the overall budget was spent before a candidate was launched (:107-112);
- the candidate exited 0 but its stdout was not read within 1000 ms (:156, the `$outTask.Wait(1000)` half of the condition);
- `Process.Start` threw, for any reason (:171-173);
- the candidate answered and was refused (exit status, JSON, implementation, version, or the printed path is not a file: :156-169, :175-176).

Only the last is "no usable python". The first three are "could not tell". The repo's own rule (CLAUDE.md, Lessons): "An unknown must not collapse into the safe-looking value. Where a probe can fail, could-not-tell is its own value and survives into every line derived from it." Here the unknown collapses into a definite, wrong statement.

The fix in this ticket does not depend on which of the five it was. It makes the hook say which, so the reporter's next run answers the question.

## What was found on origin/main 86d96fa1
- The function is carried inline, byte for byte, in 11 PowerShell hooks (169 lines each, one hash): approval-hook.ps1:21, cloud-guard.ps1:22, completion-audit.ps1:17, crew-context.ps1:23, handoff-read.ps1:16, handoff-write.ps1:16, notify.ps1:22, platform-sync.ps1:26, role-write-guard.ps1:26, scope-guard.ps1:19, verify-gate.ps1:168. `plugin/crew/tests/test_ps1_python_probe.py:176-178` pins all 11 to role-write-guard.ps1's copy; four other test files pin subsets.
- Every caller reads only "empty or not". Their words for empty: completion audit and scope guard "no usable python"; approval hook "no usable python to validate the plan"; role-write guard "no usable python found"; crew-context and platform-sync "no usable python (stub or unusable interpreter)"; verify gate "no python available", "(no python; scope not checked)" and "python3, python and py all fail to resolve to a PROVED working interpreter"; cloud guard "cannot run cloud_guard.py"; handoff-read, handoff-write and notify say nothing.
- The bash twins have the same collapse. `crew_py_strict` (`_common.sh:141`) and its byte-for-byte copy `_resolve_role_write_python` (`role-write-guard.sh:43`) `continue` past a candidate killed at 3 s (`_common.sh:207`), `break` when the 8 s budget is spent (:174) and `return 1` (:312); the callers print the same "no usable python" sentences. No report exists for the bash side.
- Four of the 11 carriers are review/gate harness paths (`scripts/check-tooling-pr.py:58-87`): approval-hook.ps1, completion-audit.ps1, scope-guard.ps1 and verify-gate.ps1. The other seven are not, and are not in `ALONGSIDE` or `SEAM` either. So one PR that changes the function in all 11 is refused by `check-tooling-pr.py` (seven files "outside tooling"), and the byte-parity tests refuse a PR that changes it in fewer than 11. The repo's two rules meet here; see open question 1.
- The 3000 ms line `$crewPythonWaitMs = [Math]::Min(3000, $crewPythonRemainingMs)` is a sabotage anchor (`sabotage_context.py:44`, against crew-context.ps1), and `$proc.Kill($true)` is another (`sabotage_qa.py:114`, against completion-audit.ps1). Both must stay byte for byte.
- The Stop hook's own timeout is 60 s (`hooks.json:63`). The 8 s budget is not sized for this hook: the function's comment sizes it for the shortest hook timeout that uses the probe, 10 s.

## Options considered

### How the function reports its outcome
A (recommended). The function keeps returning the path or `''`, and also records, in script scope, an outcome (`found`, `not-found`, `rejected`, `timed-out`) and one line per candidate (name, path, milliseconds, verdict). Callers that print a message read the outcome; the lines go to stderr only when the probe did not find python. The evidence is kept where it is dropped: inside the function.

B. Leave the function alone. The caller times the call and lists the PATH candidates itself, and says "timed out" when the call took about 8 s. No byte-pinned code changes, so no rule conflict; but it cannot give per-candidate times, cannot tell a kill from a slow refusal, and guesses the outcome from a duration. It does not meet ask 2.

C. The function returns an object. Every one of the 20-odd call sites and every `-PrintPython` test changes. Too wide.

### Where the diagnostics go
A (recommended). stderr, a summary line and one line per candidate, capped. It is what the reporter and the model already see, needs no file, and works for `-PrintPython` by hand.
B. A log file in the temp directory. Survives the session, but nobody reads it unless told to, and it is a second place to bound and clean.

### How to land a change to a function pinned in 11 files, four of them harness
A (recommended). Split by the harness boundary, harness first, because the reported hook is harness. This ticket is a tooling-only PR: the new body in the four harness carriers, their messages, tests, docs. The parity tests pin two groups for the time between the two PRs (the four to each other, the seven to role-write-guard.ps1 as today). A follow-up feature PR moves the seven and restores one group. This follows the owner's standing rule for a `check-tooling-pr.py` refusal (feature PR and tooling PR, separately).
B. One PR with all 11, with the owner waiving the tooling-alone rule once. One probe at every moment, but a harness change then rides with seven production files.
C. Teach `check-tooling-pr.py` that the byte-pinned function may move in the non-harness carriers alongside a harness change. A change to the rule itself; the owner's call.

### Asks 3 and 4
Not built here. Ask 3 (cache across hook runs, or a longer budget) changes the probe's safety argument: a cached path skips the execute-before-believe proof, and a longer budget must still fit a 10 s hook. It needs the numbers the diagnostics of this ticket will produce. Ask 4 changes when a Stop is blocked; that is the owner's decision.

## Recommendation
Narrow L-0690 to asks 1 and 2 for the four harness carriers, as one tooling-only PR:

- `Resolve-CrewPython` records an outcome and a per-candidate trail. `timed-out` is its own value: no candidate was accepted and at least one candidate was killed at its bound, had its output read run out, or was not tried because the budget was spent.
- completion-audit.ps1, scope-guard.ps1, approval-hook.ps1 and verify-gate.ps1 say "the python probe timed out" for that outcome, never "no usable python". Exit codes and the block-once behaviour do not change.
- On any outcome other than `found`, the trail goes to stderr. `-PrintPython` still prints only the path on stdout, and prints the trail on stderr when the path is empty.
- The first test reproduces the timeout with a fake slow interpreter on PATH.

About 190 added production lines, no new parser, guard or state machine. The rest is recorded as follow-ups, not filed.

## Open questions for the owner
Each took the recommended option on 2026-10-04.
1. Landing shape. Taken: split at the harness boundary, harness carriers first, two pinned groups until the follow-up lands. Alternatives: one 11-file PR with a one-off waiver; or change `check-tooling-pr.py`.
2. Messages. Taken: only `timed-out` gets a new sentence; `not-found` and `rejected` keep today's "no usable python" sentence byte for byte, and the trail lines carry the difference. Alternative: three sentences ("no python on PATH", "python found but refused", "probe timed out").
3. Diagnostics. Taken: stderr. Alternative: a log file in the temp directory, or both.
4. A timed-out probe still blocks the Stop once, as an unaudited tree does today. Alternative (ask 4): a visible warning and exit 0.
5. No retry, no cache, no longer budget in this ticket (ask 3). Alternative: build one now, without the reporter's numbers.
6. The bash twins are left as they are. Alternative: fix both flavours in one family of PRs now.

## Follow-ups (not filed)
- The seven non-harness carriers (cloud-guard, crew-context, handoff-read, handoff-write, notify, platform-sync, role-write-guard) take the same function body, and their callers' messages tell a timeout from a missing python. A feature PR; it restores the single parity group. It should land soon after this ticket: until it does, the repo holds two versions of a function it calls "one probe".
- The bash side: `crew_py_strict` and `_resolve_role_write_python` report a timeout apart from "none" (a distinct exit status, since they run in a `$(...)` subshell), as a feature PR; then the harness callers (completion-audit.sh, scope-guard.sh, approval-hook.sh, verify-gate.sh) say so, as a tooling PR.
- Ask 3: with the trail from the reporter's machine, decide between a per-hook budget (the Stop hook has 60 s, not 10), one retry of the first PATH hit, or a session cache that is re-proved before use. The 3000 ms line is a sabotage anchor.
- Ask 4: should "could not audit" block the Stop at all, or warn. Owner decision.
- The obsidian-vault plugin's three PowerShell hooks (bridge-status, vault-capture, vault-guard) carry their own probe with the same 8000 and 3000 ms bounds. Whether their callers collapse a timeout the same way was not read.

# Cloud handoff: L-0690

**A timed-out python probe says so, and a failed probe shows what it tried (the four harness PowerShell hooks)**

Handed to a cloud session on 2026-10-04 by owner instruction. Do not pick up locally.

- **Role:** standalone ticket (no split children). Narrowed on 2026-10-04 from the filed title to its first slice; the rest is listed under "Follow-ups (not filed)" in the spec, with no ticket ids.
- **INDEX status:** direction (spec written and approved for hand-off 2026-10-04; plan to be written by the implementing session)
- **Branch:** `L-0690-build`, new from origin/main `86d96fa1`; docs only, no implementation yet
- **Files here:** `docs/tickets/L-0690/direction.md`, `docs/tickets/L-0690/spec.md`
- **Size:** about 190 production lines across `completion-audit.ps1`, `scope-guard.ps1`, `approval-hook.ps1` and `verify-gate.ps1` (all under `plugin/crew/hooks/scripts/`).
- **Harness:** yes. All four production files are review/gate harness paths, so this lands alone as a tooling-only PR: tests, docs, version files, code map and graph may ride along, nothing else.

## What it is

A Windows machine reported crew's Stop hook printing "COMPLETION AUDIT: no usable python" twice while python was installed and the machine was under heavy load. `Resolve-CrewPython` returns `''` both when no python exists and when its time budget runs out, and every caller prints the "no python" sentence for both. This ticket makes a timeout its own outcome with its own sentence, and prints which candidates were tried and how long each took whenever the probe does not find python. The cause of the reported failures is an inference, not proven; the spec does not rely on it.

## Dependencies and work order

| Ticket | State | Why |
|---|---|---|
| (none) | - | Nothing must land first. |

It blocks nothing that is filed. The spec's follow-ups (the seven other PowerShell carriers, the bash twins, caching or a longer budget, warn-versus-block) wait on it and have no ticket ids yet.

Related, no ordering (whichever lands second merges main and re-checks its anchors):

| Ticket | State | Overlap |
|---|---|---|
| L-0681 | direction, PR #406, tooling PR | Edits `completion-audit.ps1`, `scope-guard.ps1` and `verify-gate.ps1`, including the same no-python branch. Expect a textual conflict. |
| L-0664 | direction, PR #471 | Adds a twelfth copy of `Resolve-CrewPython` to `promote-gate.ps1` and requires it byte-identical to the others. After this ticket its copy belongs to the unchanged group. |
| L-0680 | direction, PR #400 | Edits `notify.ps1`, `handoff-read.ps1`, `handoff-write.ps1`: carriers this ticket does not touch. |
| T-0096 | direction, PR #398 | Edits `_common.sh`, where the bash resolver lives. Not touched here. |
| L-0609 | direction, not published | The wallclock flake in `test_ps1_python_probe.py`. New tests must not assert an upper bound on elapsed time. |

L-0581 (parked, runner infrastructure) was checked and has no relation.

## Read before writing code

- The spec's `path:line` evidence was checked at origin/main `86d96fa1`, which is also the branch base. Re-check each anchor if main has moved.
- The function is byte-identical in 11 hooks and tests pin that. Four carriers are harness and seven are not, so one PR cannot change all 11: `scripts/check-tooling-pr.py` refuses the seven. This ticket changes only the four and re-pins the parity tests as two groups (the four to each other, the seven to `role-write-guard.ps1`, unchanged). Do not edit the seven, any `.sh` file, or anything under `plugin/crew/commands/` or `plugin/crew/skills/`.
- Keep three lines byte for byte; they are sabotage anchors: `      $crewPythonWaitMs = [Math]::Min(3000, $crewPythonRemainingMs)`, `            $proc.Kill($true)`, and `    $fpPy = Resolve-CrewPython` in `verify-gate.ps1`.
- No exit code changes. `not-found` and `rejected` keep today's sentences byte for byte; existing tests assert them and must pass unedited.
- `-PrintPython` stdout stays exactly the path or an empty line.
- The new tests need pwsh. A run that skips them proves nothing: check for pwsh first and say in the PR which suites ran and which did not. Windows PowerShell 5.1 could not be checked from Linux.
- Never name the reporting repository, machine, user or its paths. Use "a Windows machine" and generic paths such as `C:\Python\python3.exe`.
- No plan.md is published; the implementing session writes the plan.

## Open questions for the owner (recommended option taken)

1. Landing shape: split at the harness boundary, the four harness carriers first, two pinned groups until the follow-up. Alternatives: one 11-file PR under a one-off waiver of the tooling-alone rule; or change `check-tooling-pr.py`.
2. Only a timeout gets a new sentence; "not found" and "refused" keep today's text and the trail tells them apart. Alternative: a sentence for each.
3. Diagnostics go to stderr. Alternative: a log file in the temp directory, or both.
4. A timed-out probe still blocks the Stop once (fail closed, as today). Alternative: warn and exit 0.
5. No cache, retry or longer budget here, so the audit can still be skipped under load; it now says why. Alternative: build one now, without the reporter's numbers.
6. The trail prints PATH entries as found, to the local session's stderr only. Alternative: file name and PATH position only.
7. The bash twins are a follow-up. Alternative: both flavours now.

Could not tell: which of the probe's silent ends happened on the reporting machine; how many stderr lines a blocked Stop shows before truncation; whether the obsidian-vault plugin's own probes collapse a timeout the same way.

## Before landing

Merge origin/main, take a crew version above main's from the coordinator, follow the repo's CLAUDE.md (scope discipline, doc updates for `plugin/crew` changes, tooling-PR rule), and remove `docs/tickets/L-0690/` in the final PR unless the owner wants it kept.

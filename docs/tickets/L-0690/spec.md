# L-0690 a timed-out python probe says so, and a failed probe shows what it tried (the four harness PowerShell hooks)          status: spec   risk: high
## Written 2026-10-04
First spec for this ticket (no earlier spec.md, no plan.md). Written against origin/main 86d96fa1, crew 1.0.328. The owner filed the ticket and was not available for the brainstorm; every choice that would have been a question took the recommended option and is listed under "Open questions for the owner". Nothing was run: no tests, no gate.

Risk is high because the four files are blocking hooks and review/gate harness. No exit code changes.

## Intent
When `Resolve-CrewPython` gives up because time ran out, the hook says "the python probe timed out" and not "no usable python", and whenever the probe does not find python the hook writes to stderr which candidates it tried, how long each took and what happened to each. This ticket does that for the four PowerShell hooks that are review/gate harness (completion-audit.ps1, scope-guard.ps1, approval-hook.ps1, verify-gate.ps1), as one tooling-only PR. It covers asks 1 and 2 of the report; asks 3 and 4, the other seven carriers and the bash twins are follow-ups.

The cause of the reported failures is an inference (the hook logged nothing). This spec does not assume it: the change reports every way the probe can end, and the reporter's next run on that machine shows which one it was.

## Design (taken as recommended, 2026-10-04)
- `Resolve-CrewPython` still returns the interpreter path or `''`, and is still memoized per process. On every return path it also sets, in script scope and memoized with the result:
  - an outcome, one of `found`, `not-found`, `rejected`, `timed-out`;
  - the lines of a trail, ready to print: one summary line, then one line per candidate considered, in PATH order.
- Outcome rules, in this precedence:
  - `found`: a candidate was accepted.
  - `timed-out`: none accepted, and at least one of: a candidate was killed at its wait bound; a candidate exited 0 but its stdout was not read within the existing 1000 ms; the overall budget was spent with a candidate still untried (including before the first launch). This is "could not tell".
  - `rejected`: none accepted, at least one candidate was launched or failed to launch, and every one ended inside its bound with an answer that was refused.
  - `not-found`: no candidate reached a launch attempt (nothing on PATH for `python3`, `python`, `py`, or only entries the extension gate skips).
- Verdict words in the trail, one per candidate: `accepted`, `skipped-extension`, `killed-at-bound`, `output-read-timeout`, `exit-nonzero`, `not-python-proof` (the answer did not parse, or names another implementation or a version below 3.8), `exe-missing`, `start-failed`, `not-tried-budget-spent`. The walk still stops at the first `not-tried-budget-spent`; candidates after it are not enumerated.
- Trail shape (exact text is the implementer's, these parts are required): the summary line starts `python probe: ` and carries the outcome, the total elapsed milliseconds and the two bounds (8000 and 3000); each candidate line starts `python probe:   ` and carries the name, the path as PATH gave it, the elapsed milliseconds and the verdict (with the exit code for `exit-nonzero` and the bound for `killed-at-bound`). At most 8 candidate lines, then one `python probe:   (+N more)` line.
- The function itself writes nothing to stderr or stdout. Callers print.
- The 8000 ms and 3000 ms bounds, the probe command, the kill, the acceptance proof and the candidate order do not change. Two lines stay byte for byte because sabotage mutations anchor on them: `      $crewPythonWaitMs = [Math]::Min(3000, $crewPythonRemainingMs)` and `            $proc.Kill($true)`. In verify-gate.ps1 the text `    $fpPy = Resolve-CrewPython` stays as it is.
- Works on Windows PowerShell 5.1 and PowerShell 7 (no syntax newer than 5.1).
- Callers, exit codes unchanged:
  - completion-audit.ps1: on `timed-out` the sentence is "the python probe timed out - could not tell whether python is usable, so the tree was not audited against the ticket's scope." through `Exit-BlockOnce` (so `COMPLETION AUDIT: ` in front, and the two "Not blocking" variants as today), and "completion audit: the python probe timed out - not audited (scope.mode is off)." on the provably-off branch. On `not-found` and `rejected` today's two sentences stay byte for byte.
  - scope-guard.ps1: on `timed-out`, "SCOPE GUARD: the python probe timed out - could not tell whether python is usable; failing closed because .crew/config.json does not provably set scope.mode off." and "scope-guard: the python probe timed out - not judged (scope.mode is off)." Otherwise today's sentences.
  - approval-hook.ps1: on `timed-out`, "crew: /crew:approve was NOT recorded -- the python probe timed out, so the plan could not be validated." Otherwise today's sentence. The early `exit 0` for a prompt without `crew:approve` stays silent.
  - verify-gate.ps1: the three sites that print say so on `timed-out`: `-Price` ("verify-gate -Price: the python probe timed out"), the scope report ("outside-scope: (python probe timed out; scope not checked)") and the python3 shim note (it must no longer claim that all three names "fail to resolve to a PROVED working interpreter" when the probe ran out of time). The sites that are silent today stay silent.
  - In all four, when the outcome is not `found` and the hook prints a message about it, the trail lines follow on stderr, once per process.
  - `-PrintPython`: stdout is exactly what it is today (the path, or an empty line); exit 0. When the path is empty the trail goes to stderr.
- A hook that finds python prints nothing new.
- Tests pin two groups until the follow-up lands: the four harness carriers are byte-identical to each other, the seven others are byte-identical to role-write-guard.ps1 and unchanged from origin/main. The test that does this says why and names the follow-up.

## Exclusions
- No change to any non-harness hook: not cloud-guard.ps1, crew-context.ps1, handoff-read.ps1, handoff-write.ps1, notify.ps1, platform-sync.ps1, role-write-guard.ps1, and no `.sh` file. `scripts/check-tooling-pr.py` refuses a harness change that carries them.
- No change to `plugin/crew/commands/**` or `plugin/crew/skills/**` (not in `ALONGSIDE`), and none to `scripts/check-tooling-pr.py`.
- No change to exit codes, to the block-once marker, to `Test-ScopeProvablyOff`, or to when a Stop is blocked (ask 4).
- No cache across hook runs, no retry, no longer or per-hook budget (ask 3).
- No change to the probe's bounds, command, kill, proof or candidate order.
- No log file. No new config key. No new hook.
- No change to the bash resolvers or their callers' messages.
- No change to the obsidian-vault plugin's probes.
- The reporting repository, machine, user and paths are not named anywhere: say "a Windows machine" and use generic paths such as `C:\Python\python3.exe`.

## Evidence
All at origin/main 86d96fa1, read on 2026-10-04 with `git show` and `git grep`.
- plugin/crew/hooks/scripts/completion-audit.ps1:17-185 `Resolve-CrewPython`. `:89` the stopwatch starts before the first `Get-Command`. `:107-112` budget spent before a launch: memo and `return ''`. `:113` the 3000 ms line. `:146-155` kill at the bound, then nothing is recorded. `:156` `ExitCode -eq 0 -and $outTask.Wait(1000)`: a non-zero exit and an unread stdout both fall through silently. `:171-173` any exception sets `$real = $null`. `:175-176` empty answer or a missing file: `continue`. `:181-184` end of walk: memo and `return ''`. `:97` the only diagnostic, a `Write-Verbose` for the extension skip.
- plugin/crew/hooks/scripts/completion-audit.ps1:187-190 `-PrintPython` prints the result and exits 0. `:267-282` `Exit-BlockOnce`: marker present, exit 0 with "Not blocking again"; marker unwritable, exit 0; else `COMPLETION AUDIT: <message>` and exit 2. `:293-300` the caller: `if (-not $py)`, provably off prints "completion audit: no usable python - not audited (scope.mode is off)." and exits 0, else `Exit-BlockOnce "no usable python - the tree was not audited against the ticket's scope."`.
- The 11 carriers, one function each, 169 lines, one SHA-1 over the function text (checked with awk and sha1sum): approval-hook.ps1:21, cloud-guard.ps1:22, completion-audit.ps1:17, crew-context.ps1:23, handoff-read.ps1:16, handoff-write.ps1:16, notify.ps1:22, platform-sync.ps1:26, role-write-guard.ps1:26, scope-guard.ps1:19, verify-gate.ps1:168 (all under plugin/crew/hooks/scripts/). auto-clear.ps1 is handed an interpreter by its caller; context-watch.ps1 and promote-gate.ps1 run no python.
- Callers and their words for an empty result: scope-guard.ps1:252-260; approval-hook.ps1:216-221; verify-gate.ps1:362-366 (`-Price`), :908-917 (scope report), :1714-1716 (shim note), and silent at :629, :769, :1177, :2280; cloud-guard.ps1:220-228 ("cannot run cloud_guard.py"); crew-context.ps1:212-216; handoff-read.ps1:216-217 (silent exit 0); handoff-write.ps1:241-242 and :336-337 (silent); notify.ps1:247-248 (silent); platform-sync.ps1:211-217; role-write-guard.ps1:341-347 ("no usable python found", through `Resolve-RoleWriteFallback` at :322-339).
- Parity pins: plugin/crew/tests/test_ps1_python_probe.py:52-54 `_CARRIERS` (all 11) and :176-178 `test_every_ps1_carries_the_one_probe_byte_for_byte` (each against role-write-guard); plugin/crew/tests/test_completion_audit.py:408 and :417-420 (scope-guard and completion-audit against role-write-guard); plugin/crew/tests/test_approval_hook.py:219-221; plugin/crew/tests/test_role_write_guard.py:2410-2417 (role-write-guard against verify-gate, code lines); plugin/crew/tests/test_platform_sync.py:753-757 and plugin/crew/tests/test_crew_context_wrappers.py:170-176 (non-harness pairs, untouched here).
- Fixtures to reuse: plugin/crew/tests/test_ps1_python_probe.py:107-110 `_hung` (a candidate that sleeps 60 s), :131-142 `_print_python_run` and `_print_python`, :392-409 `_stop_audit` (a Stop through completion-audit.ps1 with only broken candidates on PATH; its PATH is fixed to `_broken` today), :443-455 `_many_hung`. Existing assertions on today's text: :413-416 `"COMPLETION AUDIT: no usable python" in err` with exit 2, :420-423 the provably-off sentence with exit 0. Wallclock-marked tests at :458 and :515.
- Sabotage anchors inside what this ticket edits: plugin/crew/tests/sabotage_qa.py:113-116 (`            $proc.Kill($true)\n` in completion-audit.ps1); plugin/crew/tests/sabotage_tooling.py:976-977 (`$fpPy = Resolve-CrewPython` in verify-gate.ps1); plugin/crew/tests/sabotage_context.py:43-46 (the 3000 ms line, against crew-context.ps1, which this ticket does not edit but must not diverge from in the follow-up). The runner is plugin/crew/tests/sabotage.py (sabotage_qa.py:1-4).
- scripts/check-tooling-pr.py:58-87 `HARNESS` holds approval-hook.ps1, scope-guard.ps1, completion-audit.ps1, verify-gate.ps1, completion-audit.sh and `plugin/crew/tests/sabotage*.py`. `:99-118` `ALONGSIDE` holds `plugin/crew/tests/**`, README.md, CONFIG.md, BUDGETS.md, plugin.json, marketplace.json, `.claude/rules/**`, plugin/PLUGINS.md, CHANGELOG.md, TODO.md, `docs/**`, `.crew/codemap/**`, `.crew/verify.json`, `graphify-out/**`. The seven other carriers, `_common.sh`, role-write-guard.sh and `plugin/crew/commands/**` are in neither list nor in `SEAM` (:89-95). `judge` (:185-202) returns 1 for any changed path outside those lists when a harness path changed.
- plugin/crew/hooks/hooks.json:63 the Stop registration of completion-audit.ps1, timeout 60. Shortest timeout among the PowerShell hooks that carry the probe: role-write-guard.ps1 and two crew-context.ps1 registrations, 10.
- Bash twins, for the follow-up: plugin/crew/hooks/scripts/_common.sh:141-313 `crew_py_strict` (:165 the 8 s budget, :174 `break`, :207 `|| continue` after a kill, :312 `return 1`); plugin/crew/hooks/scripts/role-write-guard.sh:43 the pinned copy; plugin/crew/hooks/scripts/completion-audit.sh:66-73 the caller prints the same two sentences.
- Docs that state the behaviour: docs/guides/crew/src/troubleshooting.md:303-311 ("No-python fail-closed, and why it is not a bug", quotes "no usable python ... failing closed"); plugin/crew/README.md:834 (approval hook with no usable python), :2855 (the hook table row); .crew/codemap/crew.md:1021-1025 ("hand-copied ... across all 11 .ps1 hooks"). plugin/crew/CONFIG.md:1518-1523 is the cloud guard's no-python rule and is not this ticket's.
- Version-bearing lines: plugin/crew/.claude-plugin/plugin.json:3 (1.0.328), .claude-plugin/marketplace.json:224, plugin/PLUGINS.md:14, CHANGELOG.md:7.
- .crew/verify.json (54 rules, zero-indexed): rule 39 is the harness rule (runs `scripts/check-tooling-pr.py`, its suite and the review replay); rule 26 runs test_completion_audit.py; rule 15 runs scripts/check-powershell.ps1; rule 3 runs scripts/check-marketplace.py.
- completion-audit.ps1's last content change is commit 306487c3 (2026-09-28), so the file the reporter ran at crew 1.0.256 has this function.

## Unknowns
- Which of the five silent ends happened on the reporter's machine. Not resolved before implement, and not needed: after landing, the reporter runs the build under the same load and the trail says. That result decides the ask-3 follow-up.
- Whether pwsh is installed in the implementing session. The new tests are `needs_pwsh`; a skipped run proves nothing. Resolved at implement: run `pwsh -NoProfile -Command '$PSVersionTable.PSVersion'` first; if it is absent, say so in the PR and take the result from the CI shell matrix, never from a local run that skipped.
- Whether Windows PowerShell 5.1 runs the new lines. No 5.1 host is available to a Linux session. Resolved by scripts/check-powershell.ps1 (static) and the Windows CI legs; if neither covers 5.1, say "not verified on 5.1" in the PR.
- How many stderr lines a blocked Stop shows the model before truncation: could not tell. The cap of 8 candidate lines is a guess at a safe size; accepted as risk.
- Whether `Get-Command` under load is itself slow enough to spend the budget before the first launch. The trail's `not-tried-budget-spent` on the first candidate would show it. Accepted until the reporter's run.
- How to run one sabotage mutation alone: read plugin/crew/tests/sabotage.py's header at implement.
- Which docs besides the ones in Touch quote the sentences. Resolved at implement: `git grep -n "no usable python" -- plugin/crew docs .crew/codemap TODO.md` and update each hit that describes one of the four hooks.
- The next free crew patch version is chosen at implement time; other lanes hold versions above 1.0.328.
- Refresh artifacts (`.crew/codemap/` re-anchor, `.claude/rules/**`, `graphify-out/**`, `docs/diagrams/**`) are in scope without a Touch line by the owner's standing rule; they are listed where their text changes.

## Touch
- `plugin/crew/hooks/scripts/completion-audit.ps1` - the function body, the caller at the end, the PrintPython seam
- `plugin/crew/hooks/scripts/scope-guard.ps1` - the same body, its caller, its PrintPython seam
- `plugin/crew/hooks/scripts/approval-hook.ps1` - the same body, its caller, its PrintPython seam
- `plugin/crew/hooks/scripts/verify-gate.ps1` - the same body, the three printing call sites, its PrintPython seam
- `plugin/crew/tests/test_ps1_python_probe.py` - the new tests and the two-group parity pin
- `plugin/crew/tests/test_completion_audit.py` - its parity test compares the two wrappers to each other
- `plugin/crew/tests/test_approval_hook.py` - its parity test compares against completion-audit.ps1
- `plugin/crew/tests/test_role_write_guard.py` - the verify-gate comparison near line 2410 follows the two groups
- `plugin/crew/tests/test_verify_gate_python_resolver.py` - only if a message it asserts changes
- `plugin/crew/tests/sabotage_qa.py` - one new mutation, a timed-out probe reported as no python
- `plugin/crew/README.md` - the approval paragraph near line 834 and the hook table row near line 2855
- `plugin/crew/BUDGETS.md` - the markdown line count, if a crew .md file changes size
- `docs/guides/crew/src/troubleshooting.md` - the no-python entry near line 303 gains the timed-out case and the trail
- `docs/guides/crew/crew-1.0-troubleshooting.html` - rebuilt
- `docs/guides/crew/crew-1.0-troubleshooting.docx` - rebuilt
- `docs/guides/crew/crew-1.0-troubleshooting.pdf` - rebuilt
- `.crew/codemap/crew.md` - the hand-copied paragraph near line 1021 states the two groups, re-anchored
- `.crew/codemap/INDEX.md` - anchor only
- `.claude/rules/**` - regenerated
- `graphify-out/**` - by graphify update only
- `CHANGELOG.md`
- `plugin/crew/.claude-plugin/plugin.json` - version
- `.claude-plugin/marketplace.json` - version
- `plugin/PLUGINS.md` - the version cell on line 14 only
- `docs/tickets/L-0690/**` - removed in the final PR unless the owner wants it kept

Docs checked and not touched: plugin/crew/CONFIG.md (states no sentence of these four hooks), `plugin/crew/commands/**` and `plugin/crew/skills/**` (none quotes the sentences, and they may not ride in a tooling PR), `docs/diagrams/**` (the one no-python diagram is role-write-guard.sh's). If the grep under Unknowns finds otherwise, amend this list first.

## Acceptance checks
Run the suites one at a time (under the host's heavy-run wrapper where it exists). Rule numbers are `.crew/verify.json`'s zero-indexed positions at 86d96fa1. Every pytest line below must report the named tests as passed, not skipped.
- [ ] Reproduces the timeout, red first. `test_a_timed_out_probe_says_so_and_never_no_python` in test_ps1_python_probe.py: PATH holds one fake slow interpreter (`_hung`, a `python3` that sleeps 60 s) and nothing else that is python, `.crew/config.json` is `{"scope": {"mode": "block"}}`, and a Stop payload goes through completion-audit.ps1. Expect exit 2; stderr contains `COMPLETION AUDIT: the python probe timed out`; stderr does not contain `no usable python`; stderr has a `python probe:` summary line with `timed-out` and a candidate line with the fake's path, `killed-at-bound` and a time of at least 3000 ms. Committed failing before the production change (on 86d96fa1 it prints "no usable python"). `python3 -m pytest plugin/crew/tests/test_ps1_python_probe.py -q -k test_a_timed_out_probe_says_so_and_never_no_python`
- [ ] `test_a_spent_budget_is_timed_out_and_names_the_untried_candidate` (wallclock): four hung `python3` and a working one after them (`_many_hung`). `-PrintPython` exits 0 with empty stdout; stderr's trail ends in a `not-tried-budget-spent` line and its summary says `timed-out`. `python3 -m pytest plugin/crew/tests/test_ps1_python_probe.py -q -m wallclock -k test_a_spent_budget_is_timed_out`
- [ ] `test_a_refused_candidate_is_still_no_usable_python`: only `_broken` candidates. completion-audit.ps1 exits 2 with today's sentence byte for byte, the summary says `rejected`, and no line says `timed out`. `test_no_python_on_path_is_not_found`: no candidate at all; today's sentence, summary `not-found`, no candidate line. `python3 -m pytest plugin/crew/tests/test_ps1_python_probe.py -q -k "refused_candidate or not_found"`
- [ ] The existing tests pass with no edit to them: `test_no_python_fails_the_completion_audit_closed_when_scope_is_armed`, `test_no_python_lets_the_stop_through_when_scope_is_provably_off`, `test_a_hung_candidate_is_killed_and_the_next_one_is_tried`, `test_an_overall_deadline_bounds_several_hung_candidates`, `test_near_deadline_candidates_then_a_hang_stay_within_the_hook_timeout`. `python3 -m pytest plugin/crew/tests/test_ps1_python_probe.py -q -m "not wallclock"` then `python3 -m pytest plugin/crew/tests/test_ps1_python_probe.py -q -m wallclock`
- [ ] `test_a_found_python_prints_no_probe_line` (parametrised over the four hooks): with a working python on PATH, `-PrintPython` prints exactly the path on stdout and nothing on stderr. Same file, `-k found_python_prints_no_probe_line`.
- [ ] `test_block_once_and_scope_off_keep_their_exit_codes_on_a_timeout`: with the hung fixture, the first Stop exits 2, the second Stop of the same session exits 0 and says "Not blocking again" with the timed-out sentence; with no `.crew/config.json` the Stop exits 0 with "the python probe timed out - not audited (scope.mode is off)". Same file, `-k block_once_and_scope_off`.
- [ ] `test_each_harness_hook_names_a_timeout` (parametrised: scope-guard.ps1 exit 2 and `SCOPE GUARD: the python probe timed out`; approval-hook.ps1 on a prompt containing `crew:approve`, exit 2 and `the python probe timed out`; verify-gate.ps1 `-Price`, exit 1 and `the python probe timed out`): each prints the trail and none prints `no usable python` or `no python available`. Same file, `-k each_harness_hook_names_a_timeout`.
- [ ] Parity, two groups. `test_the_harness_carriers_share_one_probe` (the four are byte-identical to each other) and `test_the_other_carriers_still_match_role_write_guard` (the seven), with a comment naming the follow-up that rejoins them. `python3 -m pytest plugin/crew/tests/test_ps1_python_probe.py plugin/crew/tests/test_completion_audit.py plugin/crew/tests/test_approval_hook.py plugin/crew/tests/test_role_write_guard.py -q -k "probe or resolver"`
- [ ] Only the four hooks changed under hooks/scripts: `git diff --name-only origin/main...HEAD -- plugin/crew/hooks/scripts/` prints exactly approval-hook.ps1, completion-audit.ps1, scope-guard.ps1 and verify-gate.ps1.
- [ ] Sabotage anchors still occur: `grep -c '            $proc.Kill($true)' plugin/crew/hooks/scripts/completion-audit.ps1` prints 1; `grep -c '      $crewPythonWaitMs = \[Math\]::Min(3000, $crewPythonRemainingMs)' plugin/crew/hooks/scripts/completion-audit.ps1` prints 1; `grep -c '    $fpPy = Resolve-CrewPython' plugin/crew/hooks/scripts/verify-gate.ps1` prints 1.
- [ ] The new sabotage mutation (completion-audit.ps1 reports a `timed-out` outcome with the no-python sentence) turns `test_a_timed_out_probe_says_so_and_never_no_python` red and the file is restored: run it through plugin/crew/tests/sabotage.py and quote the line it prints for that mutation.
- [ ] Tooling-only: `python3 scripts/check-tooling-pr.py` exits 0 and prints `tooling-pr: OK - ` with nothing outside tooling (rule 39).
- [ ] The whole of rule 26 passes (its run line names test_completion_audit.py), and rule 15 passes: the static PowerShell check on the four files, with pwsh named absolutely if it is not on PATH.
- [ ] Reproduction by hand, quoted in the PR: on a PATH with the hung fixture first and a real python after it, `pwsh -NoProfile -File plugin/crew/hooks/scripts/completion-audit.ps1 -PrintPython` (with `OS=Windows_NT` on Linux) prints the real path, and nothing on stderr; with only the hung fixture it prints an empty line and the trail.
- [ ] Docs: troubleshooting.md's no-python entry describes the timed-out sentence and the trail, and its HTML, DOCX and PDF are rebuilt with `python3 docs/guides/crew/src/build.py`; README.md's two places agree; `.crew/codemap/crew.md` states the two groups with current anchors; the PR body lists each doc in the repo CLAUDE.md's crew set as changed or "none - why".
- [ ] Crew is bumped to the next free patch in plugin.json, marketplace.json and plugin/PLUGINS.md:14, with a CHANGELOG entry that says the other seven carriers and the bash twins are not yet changed; after committing, `python3 scripts/check-marketplace.py` passes (rule 3).
- [ ] The PR body says which suites ran and which did not, quotes any failure verbatim, and states that `scripts/_test/drift-detection.sh` was not run.

## Dependencies
Must land first: nothing.

Related, no ordering required (whichever lands second merges main and re-checks its anchors):
- L-0681 (direction, tooling PR, published as PR #406; child 2 of T-0096): edits completion-audit.ps1, scope-guard.ps1 and verify-gate.ps1, including the same no-python branch (`Test-ScopeProvablyOff` and the lines around the `if (-not $py)` block). Expect a textual conflict there. Its must-block check "no python ... exit 2" stays true under this ticket: no exit code changes.
- L-0664 (direction, PR #471): adds a twelfth copy of `Resolve-CrewPython` to promote-gate.ps1, a non-harness file, and requires it to be byte-identical to the others. If it lands after this ticket, its copy belongs to the role-write-guard group and the follow-up moves it with the other seven.
- L-0680 (direction, PR #400) and T-0096 (direction, PR #398): edit notify, handoff-read, handoff-write and `_common.sh`. Not touched here; they matter to the follow-ups.
- L-0609 (direction): the wallclock flake in test_ps1_python_probe.py. The new tests assert on the outcome text and on a lower bound of elapsed time, never on an upper bound, so they do not add to that flake. No order.
- L-0581 (parked): runner infrastructure. No relation found.

Blocks: nothing filed. The follow-ups below wait on this ticket.

## Size
About 190 added production lines: about 30 in each of the four copies of the function (120), about 14 in completion-audit.ps1's caller and seam, 12 in scope-guard.ps1, 8 in approval-hook.ps1, 18 in verify-gate.ps1, the rest in the PrintPython seams. No new parser, guard or state machine. All four production files are harness paths, so this is a tooling-only PR. Narrowed from the filed title: asks 3 and 4, the seven other carriers and the bash side are not in it.

## Follow-ups (not filed)
- The seven non-harness carriers (cloud-guard, crew-context, handoff-read, handoff-write, notify, platform-sync, role-write-guard, plus promote-gate if L-0664 has landed) take the same function body; the ones that print (crew-context, platform-sync, role-write-guard, cloud-guard) tell a timeout from a missing python; the parity tests go back to one group. A feature PR, about 250 added lines. It should follow this ticket closely: until it lands the repo holds two versions of the function.
- Bash: `crew_py_strict` (`_common.sh`) and `_resolve_role_write_python` (role-write-guard.sh) return a distinct status for a timeout and write a trail to stderr, as a feature PR; then completion-audit.sh, scope-guard.sh, approval-hook.sh and verify-gate.sh say so, as a tooling PR.
- Ask 3: decide, with the reporter's trail, between a per-hook budget (the Stop hook has 60 s), one retry of the first PATH hit, and a session cache that is re-proved before use. The 3000 ms line is a sabotage anchor, and crew-context.ps1 is non-harness while sabotage_context.py is harness, so that change also needs the split.
- Ask 4: whether "could not audit" should block the Stop or warn. Owner decision.
- The obsidian-vault plugin's three PowerShell probes (bridge-status, vault-capture, vault-guard): same bounds; their callers were not read.

## Open questions for the owner
Each took the recommended option on 2026-10-04; say so if you want another.
1. Landing shape. Taken: split at the harness boundary, the four harness carriers first as a tooling-only PR, with the parity tests pinning two groups until the follow-up. Alternatives: one PR with all 11 carriers under a one-off waiver of the tooling-alone rule; or a change to `check-tooling-pr.py` that lets the pinned function move in the other carriers.
2. Messages. Taken: only `timed-out` gets a new sentence; `not-found` and `rejected` keep today's "no usable python" text, and the trail tells them apart. Alternative: a sentence for each.
3. Diagnostics go to stderr. Alternative: a log file in the temp directory, or both.
4. A timed-out probe still blocks the Stop once (fail closed, as today). Alternative, ask 4: warn and exit 0.
5. No cache, retry or longer budget here (ask 3), so the audit can still be skipped under load; it now says why. Alternative: build one now without the reporter's numbers.
6. The trail prints PATH entries as found, which can include a user's home directory, to the local session's stderr only. Alternative: print only the file name and its position on PATH.
7. Bash twins are a follow-up. Alternative: both flavours now.

## Approval
Spec approved for cloud hand-off by the orchestrator under the owner's standing authority, 2026-10-04. Plan: to be written by the implementing session.

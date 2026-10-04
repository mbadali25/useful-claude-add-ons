# T-0016 plan            spec: docs/tickets/T-0016/spec.md

Owner approves direction, spec and plan (risk: high; reconstructed, see HANDOFF.md).

Preconditions: none. T-0013 (#355) is on main; T-0006's `crew_resume` is on main. T-0017 waits for this ticket.

Version: none on the build branch. At land, one patch above origin/main's crew version then (`.crew/standards.md` REPO-03).

Safety rules for every step:
- Unknown is never `terminal` and never `headless`; it is its own value to the end of every message.
- Nothing types before the binding passes; the binding runs before the sent-marker claim.
- No test reads the real `~/.claude/sessions`, the real process table's other sessions, or a real window, or sends a keystroke.

Two PRs: the feature (steps 1-6) and, after it merges, a tooling PR (step 7) with the sabotage entries alone (T-0087; `plugin/crew/tests/sabotage*.py` is HARNESS).

### Step 1: spike, committed; fixtures
Files: docs/tickets/T-0016/spike.md, plugin/crew/tests/crew_fixtures.py
Test: python3 -m pytest plugin/crew/tests/test_autoclear_binding.py -q -k fixture
Risk: med. A fixture that does not match the real record shape tests a fiction (GEN-10).
- [ ] Measure on Linux with the installed Claude Code (record the version): an interactive session in tmux; `claude -p "..."` started from that session's Bash tool; `script -qc claude` from the same; `sessionId` before and after `/clear`; the record path with `CLAUDE_CONFIG_DIR=/tmp/x`. For each: the record's `kind`, `entrypoint`, `procStart`, and `/proc/<pid>/stat` fields 7 (`tty_nr`) and 22. Commit as `spike.md`; list macOS and Windows as unmeasured. Scratch HOME/config only; no real repo is cleared.
- [ ] If the spike contradicts the spec (e.g. `-p` writes no record, or `kind` is not `interactive` for a tmux session), STOP and report to the owner before step 2.
- [ ] `crew_fixtures.py` gains, mirroring the measured shape:
  - `write_session_record(config_dir, session_id, pid, *, kind="interactive", entrypoint="cli", proc_start=None, name=None)`;
  - `bind_session(home, session_id, pid, *, tty=..., kind=..., entrypoint=..., config_dir=None)` = a record plus a process-stub entry;
  - `proc_stub(tmp_path, table)` -> `{"CREW_AUTOCLEAR_PROC_STUB": path}`, a JSON `{pid: {ppid, tty, start, comm}}` read instead of `/proc`/`ps`/`Get-Process`, the same standing as `CREW_AUTOCLEAR_WINDOW_STUB`.
  T-0017 imports these (contract rows 4, 8).

### Step 2: owner binding and classification in `crew_autocycle.py` (tests first)
Files: plugin/crew/hooks/scripts/crew_autocycle.py, plugin/crew/tests/test_autoclear_binding.py
Where: beside `ancestors` `crew_autocycle.py:374-380`; config dir beside `global_config_path` `:99-100`.
Test: python3 -m pytest plugin/crew/tests/test_autoclear_binding.py -q -k "owner or classify"
Risk: high. This decides "headless" versus "terminal"; a fallback to the safe-looking value is the bug r1 found at `:519`.
- [ ] Write the failing tests first: `test_owner_found_by_record_and_session_id`, `test_owner_honours_claude_config_dir`, `test_owner_unknown_without_record`, `test_owner_unknown_on_session_id_mismatch`, `test_owner_unknown_on_proc_start_mismatch`, `test_owner_unknown_on_unreadable_record`, `test_classify_terminal_requires_allowlist_and_tty`, `test_classify_headless_on_sdk_entrypoint`, `test_classify_headless_on_no_tty`, `test_classify_unknown_entrypoint_is_unknown_not_headless`.
- [ ] `claude_config_dir()` = `$CLAUDE_CONFIG_DIR` if set and non-empty, else `~/.claude`.
- [ ] `_proc(pid)` -> `{ppid, tty, start, comm}` or None, from the stub, else `/proc/<pid>/stat`, else `ps -o ppid=,tty=,comm= -p` (OWNER CHECK macOS). `ancestors()` and `_ppid` read through it, unchanged in result for real processes.
- [ ] `session_owner(session_id)` -> `{"pid", "record", "how"}` or `{"unknown": reason}`: walk `ancestors()`; the first pid with a JSON-object record at `<config>/sessions/<pid>.json` whose `sessionId == session_id` and whose `procStart` equals `str(start)` where `start` is readable. A record for that pid with another `sessionId` -> unknown ("the record for pid N names another session"). Walk exhausted or truncated at `_ANCESTOR_LIMIT` -> unknown.
- [ ] `classify(owner)` -> `("terminal" | "headless" | "unknown", evidence)` per the spec's allowlist rule. `HEADLESS_ENTRYPOINT_PREFIX = "sdk"`, `TERMINAL_ENTRYPOINTS = frozenset({"cli"})`, each with its spike citation in a comment.

### Step 3: target proof from the owner, and the headless notify, in `plan` and `resume_plan`
Files: plugin/crew/hooks/scripts/crew_autocycle.py, plugin/crew/hooks/scripts/auto-clear.sh, plugin/crew/tests/test_autoclear_binding.py, plugin/crew/tests/test_auto_cycle.py
Where: `resolve_method` `crew_autocycle.py:458-529` (tmux `:499-512`, xdotool `:514-524`), `resolve_target` `:414-446`, `plan` `:532-567`, `resume_plan` `:598-657`; sh sender `auto-clear.sh:224-239`, notify `:292-297`, resume notify `:140-144`.
Test: python3 -m pytest plugin/crew/tests/test_autoclear_binding.py plugin/crew/tests/test_auto_cycle.py plugin/crew/tests/test_auto_clear.py plugin/crew/tests/test_auto_clear_review_fixes.py plugin/crew/tests/test_resume_typing.py -q
Risk: high. Every must-block row in the spec lives here.
- [ ] Failing tests first, sh flavour, one per spec acceptance check 2-8 (names: `test_tmux_own_pane_sends`, `test_xdotool_window_on_strict_ancestor_sends`, `test_headless_child_in_parent_pane_types_nothing`, `test_headless_notify_names_handoff_resume_and_restart`, `test_headless_notify_fires_once`, `test_walk_through_another_session_refuses`, `test_shared_window_other_tty_refuses` (parametrized: sibling record, reparented tmux client, plain shell, failed scan), `test_window_without_pid_refuses_with_sibling` and its control `test_window_without_pid_unchanged_without_sibling`, `test_title_fallback_refuses_with_sibling`, `test_truncated_chain_refuses`, `test_unknown_owner_auto_is_plain_notify`, `test_unknown_owner_never_says_headless`, `test_resume_headless_child_types_nothing`, `test_binding_refusal_leaves_sent_marker_unclaimed`, `test_unarmed_reads_no_record`).
- [ ] `plan`: after `resolve_method` resolves a method and before returning `send`: `session_owner` -> `classify`.
  - `headless` -> `status=send, method=notify-headless` (any configured method), delay 0, label empty, and a `notice` field carrying the headless text (handoff path from `cfg["handoffPath"]`, the `resume:` line read as text, not parsed).
  - `unknown` -> `auto`: plain `notify`; explicit typing method: refuse "could not identify this session's process (<reason>)".
  - `terminal` -> tmux: `pane_pid` must be in `ancestors(owner)` and no pid between owner and pane pid may be a `claude`-comm process or a live record's pid; xdotool: `resolve_target(ancestors(owner)[1:] ...)` with the same through-another-session refusal, then the sibling-tty scan over the window owner's descendants (`/proc/*/stat`, stub-aware; any failure refuses); `pid <= 1` and title-fallback windows refuse when another live record exists.
  - The plan's printed fields stay eight lines; `notify-headless` is a new method value, and its text travels in `reason` (empty for `send` today), so the line count does not change. T-0017's refusal path is untouched.
- [ ] `resume_plan` (OWNER CHECK scope): the same owner/class gate before `resolve_method`; headless or unknown -> refuse "auto-resume types only into this session's own terminal: <why>".
- [ ] `auto-clear.sh`: `notify-headless` branch beside `notify` (`:292-297`): print `{"systemMessage": <reason>}`, log "sent - method notify-headless", after the sent-marker claim. Dry-run prints `method: notify-headless`.
- [ ] `test_auto_cycle.py`'s `_sendable` and `_tmux_env` bind the fixture session to the test process (stub tty non-zero, entrypoint `cli`) so every existing must-fire case still sends; no assertion is edited. Same for any other suite step 3's Test line turns red only for want of a binding (list each in the PR body).

### Step 4: the ps1 twin
Files: plugin/crew/hooks/scripts/auto-clear.ps1, plugin/crew/tests/test_autoclear_binding.py
Where: after the handoff checks `auto-clear.ps1:507-544` and the method switch `:552-559`, before the notify claim `:595-600`; the ancestor walk `:660-665` and window pick `:671-694`; resume flavour before its claim `:880`.
Test: python3 -m pytest plugin/crew/tests/test_autoclear_binding.py plugin/crew/tests/test_auto_cycle.py plugin/crew/tests/test_auto_clear.py plugin/crew/tests/test_auto_clear_review_fixes.py plugin/crew/tests/test_auto_clear_child_tab_recheck_structure.py plugin/crew/tests/test_resume_typing.py -q
Risk: high. ps1 has no tty: `terminal` rests on kind + allowlist (r1 FIX `auto-clear.ps1:733`).
- [ ] Native PowerShell `Get-CrewSessionOwner` / `Get-CrewSessionClass`, reading `$env:CLAUDE_CONFIG_DIR` or `$userHome/.claude`, `CREW_AUTOCLEAR_PROC_STUB` honoured; `$ancestors` walks from the owner; through-another-session refusal; window owned by another record's chain refuses; `Pid -le 1` and title fallback refuse with a live sibling record.
- [ ] Headless -> the same text as sh as a `systemMessage` (parity test `test_headless_notify_parity`), claimed with `CreateNew` like notify.
- [ ] ps1 variants of every sh test in step 3 that applies (no tmux/xdotool cases); skip without pwsh, saying so.

### Step 5: verify rule
Files: .crew/verify.json
Test: python3 scripts/check-marketplace.py (after commit)
Risk: low.
- [ ] Add `plugin/crew/tests/test_autoclear_binding.py` and `plugin/crew/tests/crew_fixtures.py` (if not already mapped) to the auto-clear rule's `paths` and its `run` line; re-measure and update its `seconds` and `why`.

### Step 6: docs, CHANGELOG, TODO
Files: plugin/crew/CONFIG.md, plugin/crew/README.md, plugin/crew/skills/crew-context/SKILL.md, docs/guides/crew/src/auto-cycle.md, plugin/crew/hooks/scripts/auto-clear.sh (header only), plugin/crew/hooks/scripts/crew_autocycle.py (docstring only), CHANGELOG.md, TODO.md, plugin/crew/BUDGETS.md
Test: python3 scripts/check_instructions.py; python3 scripts/check-marketplace.py; grep -rn "ancestor of the hook\|ancestor of this hook\|nearest ancestor process" plugin/crew docs/guides/crew (every hit updated or deliberately kept, listed in the PR body)
Risk: med. Docs that promise more than the code are findings (r1 FIX `:786`, r2 NIT `CHANGELOG.md:57`).
- [ ] Describe: the owner binding (record + session id + start time; `CLAUDE_CONFIG_DIR`), the three classes and the allowlist, the headless notify and its once-per-session rule, the refusals (through another session, shared window, truncated chain, pid-less window, title fallback with a sibling), and the stated limits (Windows entrypoint unmeasured; macOS per the OWNER CHECK; a sibling invisible to every check is the reason shared windows refuse). Add the chain T-0017 wrap-up -> T-0016 target proof -> clear -> T-0006 decide -> T-0013 typing (contract row 6). Fix `auto-cycle.md`'s `sendkeys` row (r1 NIT `:134`).
- [ ] New refusal reasons in `auto-cycle.md`'s refusal table (`:166` area).
- [ ] CHANGELOG entry under a new section (never rename a heading). Only claims a test proves.
- [ ] TODO.md: measure `entrypoint`/`kind` on native Windows and macOS; a live end-to-end `-p` child run in tmux.
- [ ] Full serial check before review: `python3 -m pytest plugin/crew/tests/ -q -n 4 -m "not wallclock"`, then `-m wallclock`; `bash plugin/crew/hooks/scripts/_test/run-tests.sh`; `python3 -m pylint -j 4 $(git ls-files "*.py")`. Name what did not run.

### Step 7 (separate tooling PR, after the feature merges): sabotage
Files: plugin/crew/tests/sabotage_autoclear_binding.py, plugin/crew/tests/sabotage.py
Where: the registry tuple beside `AUTOCYCLE_MUTATIONS` (`plugin/crew/tests/sabotage.py:72`, `:3065`); `sabotage.py` is at max-module-lines, so the mutations live in the sibling module.
Test: python3 plugin/crew/tests/sabotage.py restricted to the binding mutations (each red on its named test, tree restored byte-identical)
Risk: med. A drifted anchor tests nothing; `test_every_binding_sabotage_anchor_is_present_exactly_once` holds it.
- [ ] The nine mutations of spec acceptance 10, each paired with its test; record red/green per mutation in the PR body; any green is a finding.

## Self-review
- Spec coverage: 1 -> step 1; 2-8 -> steps 3-4; 9 -> step 3 (fixture binding) and step 6 (full run); 10 -> step 7; 11 -> steps 5-6.
- Contract coverage: rows 2-3 step 3 (headless notify), rows 4/8 step 1, row 5 steps 3-4 (order test), row 6 step 6, rows 7/9 the file names here.
- Touch coverage: every Files: entry is in spec Touch; version files are touched at land only.
- Not verified while planning: any `-p` record (step 1 measures it); Windows and macOS behaviour; whether existing suites beyond `test_auto_cycle.py` need the fixture binding.
- Size: about 14 files; roughly +250 lines python, +200 PowerShell, +30 bash, +600 tests and fixtures, +150 docs, +120 sabotage (tooling PR).

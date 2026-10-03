# T-0013 plan            spec: .work/tickets/T-0013/spec.md

Owner approves (risk: high). Precondition: T-0006 merged (`crew_resume.py decide --json` / `record`). Crew version for this ticket: 1.0.39. Five steps; step 1 is a measurement and gates the default in step 3.

### Step 1: measure when the session is ready to take keys after SessionStart
Files: .work/tickets/T-0013/ready-measure.md
Where: nothing tracked is modified; a throwaway repo under the session scratchpad with a project `.claude/settings.json` SessionStart hook that appends `{source, t_hook_exit}` to a log; deleted afterwards
Test: the recorded table and the derived default; at least 20 `/clear` and 10 `/compact` runs, Claude Code version noted
Risk: med - a default that is too short types into a redraw; too long only delays the resume
- [ ] do NOT rely on "no `.crew/` keeps crew silent" (T-0006 spike side finding): run the scratch claude with `HOME` pointed at a scratch home that has no crew plugin installed, and check afterwards that the scratch repo has no `.crew/`
- [ ] for each run: `tmux send-keys -l /clear` + `Enter`; after the hook logs its exit, send a unique sentinel line `echo-<n>` (no Enter) at offsets 0, 250, 500, 1000, 2000, 3000 ms in separate runs; `tmux capture-pane -p` 2 s later; record whether the sentinel is in the input line intact
- [ ] record the earliest offset that landed intact in every run (`t_ready_max`) and the input-line glyph of an empty prompt (the probe pattern)
- [ ] default `resume.typeDelaySeconds` = ceil(2 x `t_ready_max`), floor 2; write the table, the default, the glyph and the stated limit (a delay is not a proof; Windows has no probe) into `ready-measure.md`
- [ ] clear the input line and kill the tmux session; delete the scratch repo and scratch home

### Step 2: the resume plan - T-0006's decision, auto-clear's target rules
Files: plugin/crew/hooks/scripts/crew_autocycle.py, plugin/crew/tests/test_resume_typing.py
Where: new `resume_plan(root, session_id, source, global_path=None, env=None)` beside `plan` `crew_autocycle.py:526`; reuses `settings` `:137`, `in_scope` `:281`, `resolve_method` `:452`
Test: python3 -m pytest plugin/crew/tests/test_resume_typing.py -q -k plan
Risk: high - this decides whether anything is typed
- [ ] `resume_plan` returns the same line format `plan` prints (status off|refuse|send, reason, method, target, label, command, delay, key) so both senders read it unchanged; `command` = `decide`'s rendered prompt; `key` = handoff sha256[:16]
- [ ] order, first failure wins: `crew_resume.decide` (imported; import failure -> refuse) not `run` -> `off` when its action is `off`, else refuse with its reason; `in_scope` false -> off; `resolve_method` not ok -> refuse with its reason; `notify` -> status send, method notify (types nothing)
- [ ] the machine's `context.autoClear.enabled` is NOT required (consent is `resume.auto`), but `method`, `windowTitle`, `unsafeFocus`, `onlyRepos`, `onlySessions` are read exactly as `settings` reads them
- [ ] CLI `crew_autocycle.py resume-plan --root R --session S --source clear|compact`
- [ ] tests: `test_resume_plan_send_on_tmux_ancestor_pane`, `test_resume_plan_off_when_decide_off`, `test_resume_plan_refuses_on_decide_wait`, `test_resume_plan_refuses_without_tmux`, `test_resume_plan_refuses_non_ancestor_pane`, `test_resume_plan_off_outside_only_repos`, `test_resume_plan_refuses_wtype`, `test_resume_plan_auto_on_windows_is_notify`, `test_resume_plan_command_is_rendered_prompt`

### Step 3: resume mode in both senders, with the marker, the record and the ready gate
Files: plugin/crew/hooks/scripts/auto-clear.sh, plugin/crew/hooks/scripts/auto-clear.ps1, plugin/crew/hooks/scripts/crew_state.py, plugin/crew/hooks/scripts/crew_config.py, plugin/crew/templates/global.template.json, plugin/crew/tests/test_resume_typing.py, plugin/crew/tests/test_resume_typing_structure.py, plugin/crew/tests/test_crew_config.py
Where: sh: argument loop `auto-clear.sh:51-60` gains `--resume --source S`; the plan call `:103` switches to `resume-plan`; the marker `:111` becomes `<git-common-dir>/crew/resume-typed-<key>` in resume mode; claim `:163`; inhibit `:183-186`; sender `:188-208`. ps1: `param()` `:55` gains `-Resume` and `-Source`; the marker `:466`, `:543`; child `:829-1015` gains the delay only (no probe on Windows); `Start-Process` `:1131`. Defaults: `RESUME_DEFAULTS` (T-0006, near `crew_state.py:654`) gains `typeDelaySeconds` (step 1's value) and `readyTimeoutSeconds: 15`; `default_global_config` `crew_config.py:367`
Test: python3 -m pytest plugin/crew/tests/test_resume_typing.py plugin/crew/tests/test_resume_typing_structure.py plugin/crew/tests/test_crew_config.py -q; then the existing `python3 -m pytest plugin/crew/tests/test_auto_clear.py plugin/crew/tests/test_auto_clear_order.py plugin/crew/tests/test_auto_clear_review_fixes.py plugin/crew/tests/test_auto_cycle.py -q` unchanged
Risk: high - this is the keystroke; a wrong marker types twice, a missing record bypasses the loop guard
- [ ] after every refusal (the same "claim last" place `:155-164` states), claim the per-handoff marker (`noclobber` in sh, `CreateNew` in ps1); then `python3 crew_resume.py record --decision-json -`; non-zero or `ok: false` -> log "refusing - could not record the run" and type nothing
- [ ] sh sender (tmux): replace the fixed sleep with the ready gate - poll `tmux capture-pane -p -t <pane>` every 250 ms up to `readyTimeoutSeconds` for the step-1 empty-prompt pattern on the input line, starting no sooner than `typeDelaySeconds`; not matched -> log and exit without typing; matched -> `send-keys -l <command>` then `Enter`
- [ ] ps1 child (sendkeys): `Start-Sleep -Seconds typeDelaySeconds`, then the existing foreground check `:980` and tab recheck `:990`, then `SendWait` of the escaped command `:1013-1015`; the child's inhibit check `:1007` stays where it is
- [ ] the Stop-hook `/clear` path is byte-for-byte unchanged outside the `--resume` / `-Resume` branches
- [ ] `test_resume_typing.py` (sh; ps1 cases on pwsh with `OS=Windows_NT` and `CREW_AUTOCLEAR_WINDOW_STUB`; every case with `CREW_AUTOCLEAR_INHIBIT` and HOME at the fixture; tmux stubbed on PATH, recording its argv instead of typing): `test_types_rendered_prompt_via_tmux_stub`, `test_second_run_same_handoff_types_nothing`, `test_both_flavours_type_at_most_once`, `test_refusing_flavour_leaves_marker_unclaimed`, `test_record_failure_types_nothing`, `test_nonempty_input_line_refuses`, `test_probe_timeout_refuses`, `test_sendkeys_focus_lost_refuses`, `test_sendkeys_tab_mismatch_refuses`, `test_off_is_silent_no_log`
- [ ] `test_resume_typing_structure.py` (static source text, no execution): in the sh sender, probe loop < `send-keys`; in the ps1 child, `Start-Sleep` < foreground check < tab recheck guard < inhibit < `SendWait`; in both, marker claim < `crew_resume.py record` < sender spawn
- [ ] leaf counts re-measured at `test_crew_config.py:271` and the global-settable test

### Step 4: start resume mode from the context hook
Files: plugin/crew/hooks/scripts/crew_context.py, plugin/crew/hooks/scripts/crew-context.sh, plugin/crew/hooks/scripts/crew-context.ps1, plugin/crew/tests/test_resume_typing.py
Where: `crew_context.run` `crew_context.py:830`, BEFORE the flavour claim at `:843`; `main`'s argparse `:1003-1010` gains `--flavour sh|ps1`; the sh wrapper's python call `crew-context.sh:19`; the ps1 wrapper's argv `crew-context.ps1:229`
Test: python3 -m pytest plugin/crew/tests/test_resume_typing.py plugin/crew/tests/test_crew_context_wrappers.py plugin/crew/tests/test_crew_resume_hook.py -q
Risk: high - the entry point; it must run in each flavour independently of the context claim, and never delay or break the context emit
- [ ] on SessionStart with source `clear`/`compact`: run this flavour's sender in resume mode synchronously with a 10 s timeout (`bash auto-clear.sh --resume --session S --source X --root R`, or `powershell -NoProfile -File auto-clear.ps1 -Resume -Session S -Source X -Root R`); the sender itself returns after spawning its detached child; any failure is logged and swallowed (the hook's never-raise rule, `crew_context.py:1036`)
- [ ] T-0006's context line changes from "press Enter ... or let T-0013 type it" to name what happened: `typing <prompt> in <n>s (method <m>)`, or the refusal reason from the sender's plan
- [ ] tests: `test_context_hook_starts_resume_mode_on_clear`, `test_context_hook_never_starts_resume_mode_on_startup`, `test_resume_mode_runs_in_each_flavour_despite_claim`, `test_resume_mode_failure_keeps_context_output`

### Step 5: sabotage, verify rule, docs, version
Files: plugin/crew/tests/sabotage_resume_typing.py, plugin/crew/tests/sabotage.py, .crew/verify.json, plugin/crew/CONFIG.md, plugin/crew/README.md, plugin/crew/skills/crew-context/SKILL.md, docs/guides/crew/src/auto-cycle.md, plugin/crew/BUDGETS.md, plugin/crew/.claude-plugin/plugin.json, plugin/PLUGINS.md, .claude-plugin/marketplace.json, CHANGELOG.md, TODO.md
Where: registry `plugin/crew/tests/sabotage.py:2927`
Test: python3 plugin/crew/tests/sabotage.py restricted to the RESUME_TYPING mutations (each red on its named test, tree restored byte-identical); python3 -m pytest plugin/crew/tests/ -q serially; bash plugin/crew/hooks/scripts/_test/run-tests.sh; python3 scripts/check-marketplace.py; python3 scripts/check_instructions.py
Risk: med - a mutation whose anchor drifts tests nothing; held by an anchor-presence test
- [ ] mutations: type on `wait` -> `test_resume_plan_refuses_on_decide_wait`; drop the per-handoff marker -> `test_second_run_same_handoff_types_nothing`; claim the marker before the method check -> `test_refusing_flavour_leaves_marker_unclaimed`; skip the probe -> `test_nonempty_input_line_refuses`; ignore a `record` failure -> `test_record_failure_types_nothing`; type the raw handoff line -> `test_resume_plan_command_is_rendered_prompt`; `auto` -> sendkeys on Windows -> `test_resume_plan_auto_on_windows_is_notify`; move the ps1 inhibit check after `SendWait` -> the structure test
- [ ] `test_every_resume_typing_sabotage_anchor_is_present_exactly_once`; run all, record which went red in the PR body; any green is a finding
- [ ] `.crew/verify.json` rule per the spec; README, CONFIG.md, SKILL.md and `auto-cycle.md`: the typing path, every refusal, `typeDelaySeconds` with step 1's measurement and its limit, `readyTimeoutSeconds`, and that Windows types only under `method: sendkeys`
- [ ] bump crew to 1.0.39 (assigned; lanes must not collide) in plugin.json, marketplace.json, PLUGINS.md; CHANGELOG; BUDGETS.md if flagged; TODO.md: a probe for Windows as a not-done follow-up

## Self-review
- Spec coverage: ready measurement -> 1; must-fire/must-not-fire -> 2 and 3; racing flavours and marker -> 3; no keystroke and structural order -> 3; existing suites unchanged -> 3; entry point -> 4; sabotage, config keys, verify rule, docs, version -> 3 and 5.
- Touch coverage: every Files: entry is in the spec's Touch. `test_auto_clear*.py`, `test_auto_cycle.py`, `test_crew_context_wrappers.py` and `test_crew_resume_hook.py` are run, not modified.
- Interfaces: `resume_plan` (2) prints `plan`'s line format, which both senders (3) already parse; the senders call T-0006's `crew_resume.py record`; step 4 calls the senders.
- Not verified while planning: the empty-prompt glyph and latency (step 1 measures them); `test_sendkeys_structural_gate.py` exists on main since T-0002 landed (f2bb919b); extend `plugin/crew/tests/test_sendkeys_structural_gate.py`'s inhibit-ordering test rather than duplicating it, so the structure test here does not import it.

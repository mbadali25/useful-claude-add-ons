# T-0017 plan            spec: .work/tickets/T-0017/spec.md

Owner approves (risk: high).

Preconditions:
- T-0006 merged: `crew_resume.parse_resume`, and `handoff.md` step 5.
- T-0016 merged: the session-record binding and its test fixtures.

T-0013 is not required. Without it, the cleared session shows the handoff and waits for Enter.

Assigned crew version: 1.0.41. Recheck for collisions at implement time; lanes must not collide.

The plan has five steps. Safety rules:
- A hook never commits.
- "Could not tell" never clears.
- `stop_hook_active` never blocks.
- `CREW_AUTOCLEAR_INHIBIT` and the claim-last sent marker are untouched.

### Step 1: the key and the wrap-up check in `crew_autocycle.py`
Files: plugin/crew/hooks/scripts/crew_autocycle.py, plugin/crew/hooks/scripts/crew_state.py, plugin/crew/hooks/scripts/crew_config.py, plugin/crew/templates/global.template.json, plugin/crew/templates/config.template.json, plugin/crew/tests/test_wrapup.py, plugin/crew/tests/test_crew_config.py
Where:
- `AUTOCLEAR_DEFAULTS` `crew_state.py:654-695` gains `"wrapUp": None`. The global layer picks it up through `crew_config.py:488-492` with no edit there unless the consent-key filter needs one.
- `_RECOGNIZED_AUTOCLEAR_KEYS` `crew_autocycle.py:81-82`.
- `settings` `:137-182`: `out["wrapUp"]` uses the same rule as `enabled` at `:175`.
- `plan` `:526-561`: call `wrapup_check` after `verify_handoff` (`:546-550`) and before `resolve_method` (`:551`).
- CLI `main` `:564-583` gains `wrapup-armed` and `wrapup-check`.
- Leaf counts: `test_crew_config.py:271` and the global-settable test.

Test: python3 -m pytest plugin/crew/tests/test_wrapup.py plugin/crew/tests/test_crew_config.py -q -k "armed or check or leaf"
Risk: high. This check is the only enforcement a hook has; a check that passes on "could not tell" clears an unfinished session.
- [ ] `wrapup_armed(cfg, root, session_id)` = `cfg["enabled"] and cfg["wrapUp"] and in_scope(cfg, root, session_id)`. `cfg["wrapUp"]` = `machine.get("wrapUp") is True and repo.get("wrapUp") is not False`.
- [ ] `wrapup_check(root, cfg)` returns `(ok, reason)`. Checks run in this order, and the first failure wins:
  1. Read the handoff at `cfg["handoffPath"]`, contained, the same as `verify_handoff` `:333-344`.
  2. Import `crew_resume` from the script directory. `ImportError` -> "T-0006's crew_resume is not installed".
  3. `parse_resume(text)`: `ok`, or `reason == "resume: none"`, passes; anything else -> "resume line: <reason>".
  4. `_HANDOFF_BRANCH_RE` must match and equal `git rev-parse --abbrev-ref HEAD`.
  5. `_HANDOFF_HEAD_RE` must match and be a prefix of `git rev-parse HEAD`. Otherwise -> "the handoff's head: is not HEAD - commit first, then rewrite the handoff".
  6. `git status --porcelain --untracked-files=no` must be empty. Otherwise -> "N tracked files are modified - the step was not committed".
  7. Any git error or timeout -> refuse naming it.
- [ ] `plan` runs it only when `wrapup_armed`. When it is unarmed, `plan`'s output is byte-identical to today's (test).
- [ ] CLI:
  - `wrapup-armed --root R --session S` prints `on` or `off` and never raises (error -> `off`).
  - `wrapup-check --root R` prints `ok` or the reason on one line (error -> the reason).
- [ ] Templates declare `"wrapUp": null` in both `context.autoClear` blocks. `null` does not veto (the `null_shadows` note at `crew_state.py:655-663`).
- [ ] Tests:
  - `test_wrapup_unarmed_without_machine_true` (null and the string `"true"` as parametrized cases)
  - `test_wrapup_repo_true_alone_arms_nothing`
  - `test_wrapup_repo_false_vetoes`
  - `test_wrapup_needs_autoclear_enabled`
  - `test_check_passes_committed_fresh_handoff`
  - `test_check_passes_resume_none`
  - `test_check_refuses_head_mismatch`
  - `test_check_refuses_missing_head`
  - `test_check_refuses_branch_mismatch`
  - `test_check_refuses_tracked_dirty`
  - `test_check_ignores_untracked`
  - `test_check_refuses_missing_resume`
  - `test_check_refuses_two_resume_lines`
  - `test_check_refuses_excluded_command`
  - `test_check_refuses_when_crew_resume_missing`
  - `test_check_refuses_on_git_error`
  - `test_plan_unarmed_is_byte_identical`

  Each builds its own git fixture repo with HOME redirected.

### Step 2: context-watch sends the procedure, and escalates once
Files: plugin/crew/hooks/scripts/context-watch.sh, plugin/crew/hooks/scripts/context-watch.ps1, plugin/crew/hooks/scripts/handoff-read.sh, plugin/crew/hooks/scripts/handoff-read.ps1, plugin/crew/tests/test_wrapup.py
Where:
- sh:
  - the message choice `context-watch.sh:579-604` gains a first branch when `crew_autocycle.py wrapup-armed` prints `on`;
  - the marker branch `:513-527` gains the escalation before `cw_run_auto_clear`;
  - the `stop_hook_active` branch `:162-167` is NOT changed.
- ps1:
  - the message choice `context-watch.ps1:399-424`;
  - the marker branch around `:310`;
  - python is resolved as `crew-context.ps1` does, and none -> unarmed.

Test: python3 -m pytest plugin/crew/tests/test_wrapup.py plugin/crew/tests/test_context_watch.py plugin/crew/tests/test_context_watch_autoclear_visibility.py plugin/crew/tests/test_context_watch_python_resolver.py -q
Risk: high. A block in the wrong branch is a Stop-hook loop, and a changed unarmed message breaks every repo.
- [ ] The armed message is one fixed text in both flavours:
  - "crew wrap-up (context.autoClear.wrapUp) - context at N%."
  - "Do not start a new step."
  - The active ticket, from `crew_ticket.py active`, or "no active ticket - the step is the tracked diff".
  - Numbered steps: run the step's `Test:` command; commit only if it passes; if it cannot pass, do not commit and write `resume: none` with the reason under Verify first; run `/crew:handoff --wrap-up`; end the turn.
  - The four clear conditions.
- [ ] Escalation: in the marker branch, when armed, run `wrapup-check`; on anything but `ok`:
  - `noclobber`-create `.crew/.wrapup-escalated-<key>` (ps1: `CreateNew`);
  - if the create succeeded, exit 2 with "crew wrap-up incomplete: <reason>. Fix exactly that, run /crew:handoff --wrap-up again, end the turn.";
  - if it failed, fall through to `cw_run_auto_clear` as today.
- [ ] The SessionStart reset also removes `.wrapup-escalated-<key>`, beside the two markers it already names:
  - sh: `handoff-read.sh:19`, with the 7-day sweep at `:23`;
  - ps1: `handoff-read.ps1:195`, with the sweep at `:201`.

  `session_id` survives `/compact`, so without the reset a compacted session could never escalate again.
- [ ] Tests:
  - `test_armed_message_is_the_procedure` (sh and ps1)
  - `test_armed_message_parity`
  - `test_unarmed_messages_unchanged_for_both_autowrapup_values`
  - `test_escalates_once_on_refusal`
  - `test_never_escalates_on_stop_hook_active`
  - `test_both_flavours_escalate_once`
  - `test_ps1_without_python_reads_unarmed`
  - `test_session_start_resets_escalation_marker`

### Step 3: auto-clear shows a wrap-up refusal, and the ps1 twin runs the check
Files: plugin/crew/hooks/scripts/auto-clear.sh, plugin/crew/hooks/scripts/auto-clear.ps1, plugin/crew/tests/test_wrapup.py
Where:
- sh: the refusal branch `auto-clear.sh:115-118`. When the plan's reason starts with the wrap-up prefix `wrap-up:`, also print `{"systemMessage": "crew wrap-up: not clearing - <reason>"}`. The same one-line JSON path that notify uses at `:171-176` reaches the user through `cw_run_auto_clear`'s stdout (`context-watch.sh:126-129`).
- ps1: after the handoff checks `auto-clear.ps1:495-504` and before the method switch `:513`:
  - read `wrapUp` beside `enabled` (`:139-147`);
  - when armed, run `crew_autocycle.py wrapup-check` through the resolved python;
  - no python, or not `ok` -> `Stop-CrewAutoClear` with the reason, plus the same systemMessage.

Test: python3 -m pytest plugin/crew/tests/test_wrapup.py plugin/crew/tests/test_auto_clear.py plugin/crew/tests/test_auto_clear_order.py plugin/crew/tests/test_auto_cycle.py plugin/crew/tests/test_autoclear_binding.py -q
Risk: high. The check must run before the sent marker is claimed (`auto-clear.sh:155-164`, `auto-clear.ps1:543`); a refusal after the claim burns the session's one clear.
- [ ] Order holds in both flavours: handoff checks -> wrap-up check -> method -> (T-0016 binding) -> claim -> inhibit -> send.
- [ ] The existing order tests keep passing. `test_auto_clear_order.py` is extended only if it pins the position of every check; if so, it is added to Touch first.
- [ ] Tests:
  - `test_refusal_prints_system_message`
  - `test_refusal_leaves_sent_marker_unclaimed`
  - `test_ps1_runs_wrapup_check_when_armed`
  - `test_ps1_no_python_refuses_armed_clear`
  - `test_dry_run_send_when_wrapup_passes`

  The sh cases run through `auto-clear.sh --dry-run`. Every case sets `CREW_AUTOCLEAR_INHIBIT`.

### Step 4: one wrap-up path - `/crew:handoff --wrap-up`, and autopilot calls it
Files: plugin/crew/commands/handoff.md, plugin/crew/commands/autopilot.md, plugin/crew/tests/test_wrapup.py
Where:
- `handoff.md`: the frontmatter `argument-hint` `:3` becomes `[--clear | --wrap-up]`. A `--wrap-up` paragraph goes after T-0006's step 5 (branch T-0006-resume `:17-20`) and before `--clear` (`:29-31`).
- `autopilot.md`: only when it exists at implement time (T-0004). It is its context-watch bullet.

Test: python3 -m pytest plugin/crew/tests/test_wrapup.py -q -k "handoff or autopilot"; python3 plugin/crew/hooks/scripts/_test/validate-prompts.py
Risk: med. Prose is the driver. A procedure that says "commit" without "only if the step's Test: passes" commits broken work.
- [ ] `--wrap-up` says:
  1. Run `git status --porcelain --untracked-files=no` first.
  2. If it is clean: take `branch:` and `head:` from `git rev-parse` now, which is after the commit, and write `resume:` per step 5.
  3. If it is dirty: write `resume: none`, and list the modified files under **Verify first** with why the step could not be finished.
  4. Keep the file under 40 lines.
  5. Then stop and end the turn. Do not tell the user to `/clear`: auto-clear does it when the four conditions hold, or says why it did not.
- [ ] The file stays within 120 lines.
- [ ] `autopilot.md`'s context-watch bullet reads "run `/crew:handoff --wrap-up` (the resume line is `/crew:autopilot <ticket>`), then stop". It carries no commit or clear instructions of its own. If `autopilot.md` does not exist, nothing is created: the owner is told to amend T-0004 step 6.
- [ ] Tests:
  - `test_handoff_documents_wrap_up_mode`
  - `test_wrap_up_mode_commits_only_on_passing_test`
  - `test_armed_message_names_handoff_wrap_up`
  - `test_autopilot_uses_the_same_wrap_up` (skips when `autopilot.md` is absent)

### Step 5: sabotage, verify rule, docs, version
Files: plugin/crew/tests/sabotage_wrapup.py, plugin/crew/tests/sabotage.py, .crew/verify.json, plugin/crew/CONFIG.md, plugin/crew/README.md, plugin/crew/skills/crew-context/SKILL.md, docs/guides/crew/src/auto-cycle.md, plugin/crew/BUDGETS.md, plugin/crew/.claude-plugin/plugin.json, plugin/PLUGINS.md, .claude-plugin/marketplace.json, CHANGELOG.md, TODO.md
Where: registry `plugin/crew/tests/sabotage.py:2927`; CONFIG.md §14 and the `autoWrapUp` row `:763`; SKILL.md `:188`, `:204-205`
Test: python3 plugin/crew/tests/sabotage.py restricted to the WRAPUP mutations (each red on its named test, tree restored byte-identical); python3 -m pytest plugin/crew/tests/ -q serially; bash plugin/crew/hooks/scripts/_test/run-tests.sh; python3 scripts/check-marketplace.py; python3 scripts/check_instructions.py
Risk: med. A mutation whose anchor drifts tests nothing; held by an anchor-presence test.
- [ ] Mutations, each paired with the test it must turn red:

  | Mutation | Test that must turn red |
  |---|---|
  | arm on repo `true` | `test_wrapup_repo_true_alone_arms_nothing` |
  | drop the head match | `test_check_refuses_head_mismatch` |
  | drop the dirty check | `test_check_refuses_tracked_dirty` |
  | count untracked as dirty | `test_check_ignores_untracked` |
  | accept an unparseable resume line | `test_check_refuses_missing_resume` |
  | `ImportError` passes | `test_check_refuses_when_crew_resume_missing` |
  | escalate on `stop_hook_active` | `test_never_escalates_on_stop_hook_active` |
  | drop the escalation marker | `test_escalates_once_on_refusal` |
  | run the check after the sent-marker claim | `test_refusal_leaves_sent_marker_unclaimed` |

- [ ] `test_every_wrapup_sabotage_anchor_is_present_exactly_once`. Record which mutations went red in the PR body; any green is a finding.
- [ ] Docs cover:
  - the procedure;
  - the four clear conditions;
  - the limit: the commit is checked, the test is not (verify-gate stands down on `stop_hook_active`);
  - the Windows python requirement;
  - `wrapUp` versus `autoWrapUp`;
  - the chain end to end: T-0017 wrap-up -> T-0016 target proof -> clear -> T-0006 decide -> T-0013 typing.

  Correct SKILL.md's "`autoWrapUp` is off by default" to `true`.
- [ ] Bump crew to 1.0.41 in plugin.json, marketplace.json and PLUGINS.md.
- [ ] CHANGELOG entry.
- [ ] BUDGETS.md, if flagged.
- [ ] TODO.md: a follow-up for a real `-p` end-to-end run of the wrap-up.

## Self-review
- Spec coverage:
  - arming, check, must-fire and must-not-fire -> 1 and 3
  - armed message, parity and escalation -> 2
  - one path -> 4
  - existing suites unchanged -> 2 and 3
  - sabotage, config, docs, verify and version -> 1 and 5
- Touch coverage: every Files: entry is in the spec's Touch. `test_context_watch*.py`, `test_auto_clear*.py`, `test_auto_cycle.py` and `test_autoclear_binding.py` are run, not modified.
- Interfaces:
  - `wrapup_check` (1) is called by `plan` for sh and by the CLI for ps1 and context-watch (2, 3).
  - `/crew:handoff --wrap-up` (4) is named by context-watch's message (2) and by autopilot.
  - It consumes T-0006's `parse_resume` only.
- Not verified while planning:
  - a live `-p` or interactive run of the full chain;
  - the Windows python resolution path in context-watch.ps1.

# T-0029 plan            spec: .work/tickets/T-0029/spec.md

Preconditions: built on branch T-0029-wave (merge 1f54089e: T-0010-policies abd4f29b, which carries
T-0024 32223b8a and T-0018 355b4d3a, plus T-0018-router d9fafa0a). Every anchor below was re-read
there on 2026-09-26 with `git grep -n` of the named symbol. Re-read them again after each dependency
lands on main. T-0024's group line and T-0010's `questions.md` format are available on this base.
Amended 2026-09-26 with the owner's answers to the build lane's two STOPs (spec, Decisions).

### Step 1: Spike - do crew's PreToolUse hooks fire in lane agents, and with what `agent_type`?
Files: .work/tickets/T-0029/spike.md
The scratch fixture lives in the session scratchpad, not in this repo.
Test: the recorded payloads themselves. The step passes when `spike.md` states, for each engine, "fired: yes|no" and the verbatim `agent_type` value (or "absent").
Risk: high. Steps 7 and 9 depend on this answer.
- [x] DONE 2026-09-26 (spike.md). Main thread: fired, `agent_type` absent. `Agent` + `isolation: worktree`: fired, `agent_type` `general-purpose`, payload `cwd` the isolated worktree. `Agent` with no isolation: fired, payload `cwd` the main checkout. Workflow: not run (needs the owner's opt-in), so disabled.
- [x] Decision applied: Step 7 proceeds; lanes are `Agent` with `isolation: worktree` only (owner, 2026-09-26).

### Step 2: Wave settings, the scope precondition and the set file
Files: plugin/crew/hooks/scripts/crew_state.py, plugin/crew/hooks/scripts/crew_wave.py, plugin/crew/tests/test_crew_wave.py, plugin/crew/tests/test_crew_config.py, plugin/crew/tests/test_crew_autopilot.py, plugin/crew/templates/config.template.json, plugin/crew/skills/crew-setup/SKILL.md, plugin/crew/CONFIG.md
Anchors: AUTOPILOT_DEFAULTS crew_state.py:1091; PM_DEFAULTS maxDispatches :1113, coerced by int_or :3014; crew_config.default_config autopilot block crew_config.py:374; crew_autopilot.settings :653; crew_ticket.effective_mode, configured_mode.
Test: `python3 -m pytest plugin/crew/tests/test_crew_wave.py -q -k "settings or set_file or scope" && python3 -m pytest plugin/crew/tests/test_crew_config.py plugin/crew/tests/test_crew_autopilot.py -q`
Risk: med. A bad default silently widens concurrency or arms autonomy; a scope check that reads "unknown" as enforcing launches unguarded lanes.
- [ ] Write the failing tests first:
  - `test_settings_defaults_max_lanes_to_max_dispatches`
  - `test_settings_caps_max_lanes_at_max_dispatches_with_warning`
  - `test_settings_invalid_review_policy_warns_and_uses_stop`
  - `test_set_file_round_trips`
  - `test_set_slug_outside_grammar_is_refused` (slug grammar `[a-z0-9][a-z0-9-]{0,63}`, T-0012 spec:20)
  - `test_unreadable_set_file_is_unknown_not_empty`
  - `test_scope_not_enforcing_stops_the_wave`, parametrized: `off`, `report`, `auto` inside its report ramp, a config that does not parse, no config. Each stops with id `scope-not-enforcing` and names `scope.mode: block`.
  - `test_scope_block_lets_the_wave_run`
- [ ] Add `"maxLanes": None, "reviewPolicy": "stop"` to `AUTOPILOT_DEFAULTS`, and the same two keys to `config.template.json`, crew-setup SKILL.md's inline copy and CONFIG.md's autopilot table. Update `test_crew_config.py`'s declared count 121 -> 123 (with the comment line naming T-0029) and `test_crew_autopilot.py::test_autopilot_defaults_are_the_config_block`'s expected dict.
- [ ] In `crew_wave.py`:
  - `settings(root)` reads `crew_config.resolve_config(top)` the way `crew_autopilot.settings` does. It returns `{"maxLanes", "reviewPolicy", "warnings"}`.
  - `maxLanes` is `min(configured or maxDispatches, maxDispatches)`, with `maxDispatches` from the resolved `pm` block through `crew_state.int_or`. A non-positive or non-int value warns and uses `maxDispatches`.
  - `reviewPolicy` must be one of `stop|clean-only|fix-and-rereview`; anything else gives `stop` plus a warning.
  - `scope_enforcing(root, tickets)` returns `(ok, reason)`: ok only when `crew_ticket.effective_mode(root, id)` is `block` for every ticket. Anything else, or an exception, is not ok, with the fix named.
- [ ] `write_set(root, slug, tickets)` writes `.work/autopilot/<slug>.json` with `{"schema": 1, "set": slug, "tickets": [{"id": ..., "deps": [...]}]}` through a temp file and `os.replace`. The text is computed before the file is opened (CLAUDE.md, the `open(p, "w")` landmine).
- [ ] `read_set` returns `(data, "ok"|"missing"|"corrupt")`. It never returns `{}` for a corrupt set file.
- [ ] CLI: `crew_wave.py set --slug <s> --tickets <id>... [--deps <id>=<id>,<id>]`.
- [ ] Add `("scope-not-enforcing", ...)` to the stops `crew_autopilot.py stops` prints.

### Step 3: `crew_wave.py plan` - eligibility, overlap, landing order (read-only)
Files: plugin/crew/hooks/scripts/crew_wave.py, plugin/crew/tests/test_crew_wave.py
Anchors: crew_ticket.accepted :670 (status :589); crew_state._TICKET_RE :193, _TABLE_DONE_WORDS :234, _table_status; crew_ticket.glob_match :377, path_matches :399; scope_guard's accepted call :354.
Test: `python3 -m pytest plugin/crew/tests/test_crew_wave.py -q -k plan`
Risk: high. This is the picker. A false `eligible` starts an unapproved ticket, or two lanes that collide.
- [ ] Failing tests first, one per refusal reason:
  - `test_plan_refuses_ticket_without_current_approval`
  - `test_plan_refuses_direction_status_ticket`
  - `test_plan_refuses_closed_ticket`
  - `test_plan_refuses_open_dependency`
  - `test_plan_refuses_unknown_dependencies`
  - `test_plan_refuses_overlapping_touch`
  - `test_plan_refuses_lanes_over_max`
- [ ] Also: `test_plan_orders_landing_by_provisional_version` and `test_plan_writes_nothing`. The last one snapshots the fixture's tree, `.work/`, `<git-common-dir>/crew/` and the `.git/index` mtime before and after.
- [ ] `plan` runs Step 2's `scope_enforcing` first and prints `stop: scope-not-enforcing` with the fix when it fails.
- [ ] Approval comes from `crew_ticket.accepted(root, id)`, the call the scope guard makes, which demotes a non-user-prompt receipt. Only `approved` is eligible. `stale`, `unaccepted`, `none` and an exception are each refused with their own reason.
- [ ] INDEX status comes from `crew_state` INDEX parsing. `direction`, and anything in `crew_state._TABLE_DONE_WORDS`, is refused.
- [ ] Dependencies:
  - Take them from the set file.
  - Otherwise parse the INDEX row's `(depends on T-a, T-b)` text.
  - If neither parses, deps are `unknown` and the ticket is refused.
  - A dependency is closed only when its INDEX row is in `_TABLE_DONE_WORDS`.
- [ ] Touch overlap:
  - For each pair of eligible tickets, compare the `touch` list that `accepted()` returned (hashed from the same bytes as the approval; `touch_for` :965 is display-only).
  - Two entries overlap when either is covered by the other under `crew_ticket.glob_match` / `path_matches`, or when both contain a wildcard and their literal prefixes are prefix-related.
  - Any pair the rule cannot decide counts as overlap.
  - Tickets that overlap go to later waves in set order, and are never run concurrently.
- [ ] Landing order:
  - Base is `git show origin/main:plugin/crew/.claude-plugin/plugin.json`'s version.
  - Each lane that touches `plugin/crew/**` gets the next patch in set order.
  - Print `land order: T-a 1.0.N+1, T-b 1.0.N+2`.
- [ ] Output: one line per ticket (`eligible` / `refused: <reason>`), then `wave 1: ...`, `later: ...`, then the land order. `--json` gives the same data as JSON.

### Step 4: `crew_wave.py start` and `lane-init` - one isolated worktree per lane, relaunch safely
Files: plugin/crew/hooks/scripts/crew_wave.py, plugin/crew/tests/test_crew_wave.py
Anchors: crew_ticket.accepted :670, activate :864, resolve_active :885, effective_mode; review_ledger.status :455.
Test: `python3 -m pytest plugin/crew/tests/test_crew_wave.py -q -k "start or lane_init or relaunch"`
Risk: high. A lane on an unapproved contract, a lane whose guard reads `off`, two lanes on one worktree or branch, or a replay that spends a review round twice.
- [ ] Failing tests first:
  - `test_start_writes_pending_lane_files_with_base_commit`
  - `test_start_prints_isolated_agent_launch_per_lane` (`isolation: worktree`, never another form)
  - `test_start_refuses_when_scope_not_enforcing`
  - `test_lane_init_refuses_main_checkout`
  - `test_lane_init_refuses_worktree_outside_claude_worktrees`
  - `test_lane_init_refuses_worktree_another_lane_names`
  - `test_lane_init_refuses_branch_checked_out_elsewhere`
  - `test_lane_init_copies_ticket_folder_and_config_byte_identical_and_activates`
  - `test_lane_init_refuses_when_not_accepted_in_worktree` (a copy whose spec or plan no longer matches the receipt reads `stale` through `accepted`, the T-0026 digest)
  - `test_lane_init_refuses_when_worktree_scope_not_block`
  - `test_relaunch_resumes_reserved_round_without_new_reservation`
  - `test_relaunch_skips_terminal_lanes`
  - `test_relaunch_refuses_lane_whose_old_worktree_holds_the_branch`
  - `test_relaunch_after_crash_at_each_step`: parametrized over pending, initialised, activated, reserved and recorded.
- [ ] `start --set <slug>`: run `scope_enforcing` and `plan`; record `base` (`git rev-parse HEAD` of the main checkout); write `.work/autopilot/<slug>/lanes/<id>.json` = `{"set", "ticket", "state": "pending", "base", "version", "worktree": null, "step": "pending"}` through a temp file and `os.replace`; print, per lane, the launch: `Agent`, `subagent_type: general-purpose`, `isolation: worktree`, prompt = `crew_wave.py lane-prompt --set <slug> --ticket <id>`. It places no worktree and launches nothing itself: the command file does that (Step 9).
- [ ] `lane-init --root . --main <main checkout> --set <slug> --ticket <id>`, run by the lane as its first command. Every check comes before any write into the worktree:
  - (a) Refuse when `toplevel(.)` is the main checkout, is not under `<main>/.claude/worktrees/` (the path the spike measured), or is the `worktree` of another lane file.
  - (b) Refuse when `T-<id>-wave` is checked out in any other worktree (`git worktree list --porcelain`). Otherwise check it out, or create it at `base`.
  - (c) Copy `<main>/.work/tickets/<id>/` and `<main>/.crew/config.json` into the worktree with `shutil.copy2`, and compare bytes with the source.
  - (d) Require `crew_ticket.accepted(<wt>, <id>)["status"] == "approved"` and `crew_ticket.effective_mode(<wt>, <id>)[0] == "block"`. On failure, stop and remove nothing.
  - (e) Run `crew_ticket.activate(<wt>, <id>)`, then set the lane file `running`, `worktree`, `step: activated`.
- [ ] Relaunch (`start` on an existing set):
  - Read each lane file, the worktree list and `review_ledger.status(<main>, id)`.
  - Terminal states (`clean|findings|question|failed`) are skipped.
  - A reserved but unrecorded round is handed to the lane prompt as `resume round N`. It is never re-reserved.
  - A lane whose recorded worktree still exists and holds `T-<id>-wave` is not relaunched: `start` prints that worktree and says the owner removes it (after checking it is clean) or resumes there by hand.
  - A lane file that is unreadable reads `unknown` and blocks relaunch of that lane, with the reason printed.

### Step 5: `crew_wave.py lane-prompt` and `lane-done` - the one prompt every lane uses
Files: plugin/crew/hooks/scripts/crew_wave.py, plugin/crew/tests/test_crew_wave.py
Anchors: completion_audit.py `--check` args :284-286; review_run.py `--reserve-only` / `--round` (review.md:461-467).
Test: `python3 -m pytest plugin/crew/tests/test_crew_wave.py -q -k "lane_prompt or lane_done"`
Risk: med. The prompt is the lane's only instruction, so a missing step or a forbidden command in it is a defect every lane inherits.
- [ ] Failing tests first:
  - `test_lane_prompt_names_every_step_in_order`
  - `test_lane_prompt_starts_with_lane_init`
  - `test_lane_prompt_contains_no_forbidden_command`: no `--accept`, `--reject`, `crew_ticket.py approve`, `--admin`, `gh pr merge`, and no abbreviation of `--accept`/`--reject`.
  - `test_lane_prompt_uses_absolute_script_paths`
  - `test_lane_prompt_review_policy_variants`: the three policies each render their own branch.
  - `test_lane_prompt_resume_round_names_the_round`
  - `test_lane_done_refuses_state_outside_the_four`
- [ ] The prompt, rendered for `--set <slug> --ticket <id>`, covers:
  - First run `crew_wave.py lane-init`; on any refusal, `lane-done --state failed` with its reason and stop.
  - Work only in this worktree (`--root .`); never write to another checkout's path.
  - Follow `/crew:implement <id>`, then run the refresh step.
  - Run `/crew:review <id>`, reserving and recording rounds through `review_run.py` only.
  - Run `completion_audit.py --check --ticket <id> --root .`.
  - Bump crew to `<version>` in `plugin/crew/.claude-plugin/plugin.json` and `.claude-plugin/marketplace.json`.
  - On any open question: research with crew:explorer / crew:researcher, write it to `.work/tickets/<id>/questions.md` (T-0010 format: 2-4 options, recommendation first, cost each), set `question`, and stop.
  - Finish with `crew_wave.py lane-done --main <main> --set <slug> --ticket <id> --state clean|findings|question|failed --reason <text>`.
  - Script paths are absolute, taken from `crew_wave.py`'s own location: `${CLAUDE_PLUGIN_ROOT}` is a command-file substitution, not a variable a lane's Bash has.
- [ ] Review policy:
  - `stop`: FINDINGS gives `findings`.
  - `clean-only`: CLEAN continues to done checks; FINDINGS gives `findings`.
  - `fix-and-rereview`: fix and re-review while `rounds_left > 0`; at 0, `findings`.
- [ ] `lane-done` writes the lane file under `<main>/.work/autopilot/<slug>/lanes/` through a temp file and `os.replace`. It refuses a state outside the four.

### Step 6: `crew_wave.py collect` - one batch for the owner
Files: plugin/crew/hooks/scripts/crew_wave.py, plugin/crew/tests/test_crew_wave.py
Test: `python3 -m pytest plugin/crew/tests/test_crew_wave.py -q -k collect`
Risk: med. An unknown reading as `clean` hides a failed lane: the CLAUDE.md "unknown collapsing into the safe-looking value" case.
- [ ] Failing tests first:
  - `test_collect_missing_lane_file_reads_unknown`
  - `test_collect_corrupt_lane_file_reads_unknown`
  - `test_collect_lists_questions_recommendation_first` (read from each lane's worktree `.work/tickets/<id>/questions.md`; a missing worktree reads `unknown`)
  - `test_collect_prints_exact_approve_lines`: T-0024's group line (`/crew:approve T-a T-b`, then `/crew:approve --confirm`) for several tickets, one line for one.
  - `test_collect_prints_land_order_for_clean_lanes_only`
  - `test_collect_flags_owner_accepted_receipt_written_during_lane`: compare the ledger at `start` against `collect`; any new `owner-accepted` receipt marks the lane `failed: accepted without the owner`.
- [ ] Output, in this order:
  - per-lane state lines, with each lane's worktree path;
  - `Questions (N):`, each with its options, recommendation first;
  - `Approvals to type:`, the exact lines;
  - `Land order (clean):`, the lanes with versions;
  - `Later waves:`.
- [ ] Read-only: add the same snapshot assertion as `test_plan_writes_nothing`.

### Step 7: Scope guard refuses the never-list from a subagent; review_ledger stops abbreviating
Files: plugin/crew/hooks/scripts/scope_guard.py, plugin/crew/hooks/scripts/review_ledger.py, plugin/crew/tests/test_scope_guard_wave.py
Anchors: shell_refusal scope_guard.py:249-269, _APPROVE_RE :112, decide :307, _log :272; review_ledger.main :468 (parser :469).
Test: `python3 -m pytest plugin/crew/tests/test_scope_guard_wave.py plugin/crew/tests/test_scope_guard.py plugin/crew/tests/test_review_ledger.py -q`
Risk: high. This is a blocking hook. Too wide, and it blocks the owner's own accept path (`review.md:508`). Too narrow, and a lane accepts anyway.
- [ ] Step 1 found `agent_type` present in `Agent` lanes, so this step proceeds.
- [ ] Failing tests first. Each runs through the real hook entry with a payload carrying `agent_type: general-purpose` and `cwd` an isolated lane worktree with its own `.crew/config.json` at `scope.mode: block`, in both flavours (`flavour` fixture as in `test_scope_guard.py:37`).
  - Must-block:
    - `test_subagent_review_ledger_accept_is_refused`
    - `test_subagent_review_ledger_reject_is_refused`
    - `test_subagent_accept_reject_abbreviation_is_refused`, one row per `--a --ac --acc --acce --accep --rej --reje --rejec`
    - `test_subagent_crew_ticket_approve_is_refused`: already refused for everyone; kept as a regression.
    - `test_subagent_gh_pr_merge_admin_is_refused`
    - Spelling variants: `python3 /abs/path/review_ledger.py`, `py -3 ...`, `a && review_ledger.py --accept`, and PowerShell `& python ...`.
  - Must-allow:
    - `test_main_session_review_ledger_accept_is_allowed` (no `agent_type`)
    - `test_subagent_review_ledger_status_reserve_allowed` (`--status`, `--reserve`; `--r`/`--re` are not matched)
    - `test_subagent_review_run_reserve_and_record_allowed`
    - `test_subagent_gh_pr_merge_without_admin_allowed`
    - `test_subagent_write_inside_own_worktree_touch_allowed`
    - `test_subagent_write_outside_own_worktree_touch_refused`: two active-ticket entries, two isolated worktrees, each payload's `cwd` its own worktree.
  - `test_review_ledger_abbreviated_accept_is_an_argparse_error`: `review_ledger.py --ticket T-1 --acc` exits 2 and the ledger file is unchanged.
- [ ] Add `_ACCEPT_RE = re.compile(r"review_ledger(?:\.py)?\b[^\n;&|]*--(?:a(?:c(?:c(?:e(?:pt?)?)?)?)?|rej(?:e(?:ct?)?)?)(?![\w-])", re.I)` and `_ADMIN_MERGE_RE = re.compile(r"\bgh\b[^\n;&|]*\bpr\b[^\n;&|]*\bmerge\b[^\n;&|]*--admin\b", re.I)`.
- [ ] Pass `data.get("agent_type")` into `shell_refusal`. When it is a non-empty string and either regex matches, refuse with the text "a lane may not accept, reject or admin-merge; that is the owner's, from the main session".
- [ ] The main-thread path (no `agent_type`) is unchanged.
- [ ] Log each refusal through `_log` with reason `lane-never-list`.
- [ ] `review_ledger.py`: `argparse.ArgumentParser(..., allow_abbrev=False)`. Nothing else in the file changes.

### Step 8: Sabotage suite
Files: plugin/crew/tests/sabotage_wave.py, plugin/crew/tests/sabotage.py
Anchors: imports sabotage.py:71-78; append to MUTATIONS at :3049; tuple shape SCOPE_MUTATIONS sabotage_scope.py:32.
Test: `python3 plugin/crew/tests/sabotage.py`. Every WAVE mutation reports RED. Then confirm by hand that reverting one mutation's target makes its named test fail.
Risk: med. A mutation that stays green means its test is vacuous.
- [ ] Define `WAVE_MUTATIONS` with the same tuple shape as `SCOPE_MUTATIONS`:
  - drop the Touch-overlap check -> `test_plan_refuses_overlapping_touch`;
  - read `unknown` deps as `[]` -> `test_plan_refuses_unknown_dependencies`;
  - allow `direction` status -> `test_plan_refuses_direction_status_ticket`;
  - `reserve` on relaunch -> `test_relaunch_resumes_reserved_round_without_new_reservation`;
  - a missing lane file reads as `clean` -> `test_collect_missing_lane_file_reads_unknown`;
  - drop the `agent_type` branch -> `test_subagent_review_ledger_accept_is_refused`;
  - widen the guard to all sessions -> `test_main_session_review_ledger_accept_is_allowed`;
  - `scope_enforcing` accepts `report` -> `test_scope_not_enforcing_stops_the_wave`;
  - drop lane-init's isolated-worktree check -> `test_lane_init_refuses_main_checkout`;
  - drop lane-init's worktree mode check -> `test_lane_init_refuses_when_worktree_scope_not_block`;
  - drop the `--acc` prefix from `_ACCEPT_RE` -> `test_subagent_accept_reject_abbreviation_is_refused`;
  - `allow_abbrev=True` -> `test_review_ledger_abbreviated_accept_is_an_argparse_error`.
- [ ] Register the mutations and run the suite. All 12 must report RED.

### Step 9: `/crew:autopilot wave` in the router and the command file
Files: plugin/crew/commands/autopilot.md, plugin/crew/hooks/scripts/crew_autopilot.py, plugin/crew/tests/test_lifecycle_commands.py, plugin/crew/tests/test_crew_wave.py
Anchors: SUBCOMMANDS crew_autopilot.py:181, AVAILABLE :182, ARRIVES :183, route :973, route_args :1002; AUTOPILOT_MAX_LINES test_lifecycle_commands.py:107.
Test: `python3 -m pytest plugin/crew/tests/test_lifecycle_commands.py plugin/crew/tests/test_crew_wave.py plugin/crew/tests/test_crew_autopilot_status.py -q -k "wave or route or autopilot" && python3 plugin/crew/hooks/scripts/_test/validate-prompts.py`
Risk: med. It has a 100-line cap, and the router must not read `wave` as a ticket id or read `--set` as a ticket.
- [ ] Failing tests first (in `test_crew_wave.py`, since T-0018's `test_crew_autopilot_status.py` is not in Touch):
  - `test_route_wave`: `route --first wave` gives `wave`, not a stop.
  - `test_route_args_wave_set`: `wave --set my-set` gives `sub=wave`, `set=my-set`.
  - `test_route_args_wave_tickets`: `wave T-1 T-2` gives `sub=wave`, `tickets=T-1 T-2`.
  - `test_route_args_wave_refuses_bad_arguments`: a slug outside the grammar, `--set` with no slug, a non-ticket word, `--set` mixed with ids.
  - `test_autopilot_md_names_wave_cli_strings` (in `test_lifecycle_commands.py`): pins `crew_wave.py plan`, `start`, `lane-prompt`, `collect` and `isolation: worktree`.
- [ ] `crew_autopilot.py`: append `wave` to `SUBCOMMANDS` (last, so T-0018's `status|run|assign|goal|focus` substring tests still hold) and to `AVAILABLE`; give `route_args` a `wave` branch that parses `--set <slug>` or one or more ticket ids and prints them.
- [ ] Add a `wave` section of at most 5 lines to `autopilot.md`, rewrapping elsewhere only if needed to stay at 100:
  - Design in this session: `/crew:brainstorm`, `/crew:spec`, `/crew:plan` per ticket, then `crew_wave.py set`. Print the approval lines and stop.
  - On the next run, `crew_wave.py plan`, then `start`; a `scope-not-enforcing` stop is printed with its fix.
  - For each lane `start` prints, launch one `Agent` with `isolation: worktree` and the prompt from `crew_wave.py lane-prompt`, never any other way, all in one message.
  - When all lanes return, run `crew_wave.py collect` and show its output verbatim.
- [ ] Keep `autopilot.md` at 100 lines or fewer.

### Step 10: Release bookkeeping and the gate
Files: .crew/verify.json, plugin/crew/.claude-plugin/plugin.json, .claude-plugin/marketplace.json, plugin/crew/README.md, plugin/PLUGINS.md, CHANGELOG.md, plugin/crew/BUDGETS.md
Test: `python3 scripts/check-marketplace.py` exits 0. `python3 -m pytest plugin/crew/tests -q` passes, and so does the full slow suite (`--run-slow`) before review.
Risk: low. The known traps are a version bump missing from one of the two files, and the BUDGETS.md markdown-lines claim, both of which the checker fails.
- [ ] Map `test_crew_wave.py` and `test_scope_guard_wave.py` in `.crew/verify.json` next to the existing crew test rules; add `review_ledger.py` to the never-list rule's paths.
- [ ] Bump crew one patch past main in both `plugin.json` and `marketplace.json` (at landing, in version order, when the build lane is told to set no version).
- [ ] Add a CHANGELOG entry that names the behaviour changes: a subagent can no longer accept, reject or admin-merge; `review_ledger.py` no longer accepts abbreviated flags; `wave` refuses to run unless `scope.mode` is enforcing.
- [ ] README: document `wave`, `autopilot.maxLanes` and `autopilot.reviewPolicy`. `PLUGINS.md`: update crew's line if its summary changes. Re-measure BUDGETS.md's crew-markdown-lines figure.
- [ ] Run the checker and the suites. Quote failures verbatim. State that `drift-detection.sh` was not run, because this change does not touch the plugin update path.

### Step 11: clean up merged lanes' worktrees (owner, 2026-09-26)
Files: plugin/crew/hooks/scripts/crew_wave.py, plugin/crew/tests/test_crew_wave.py, plugin/crew/tests/sabotage_wave.py, plugin/crew/README.md
Test: python3 -m pytest plugin/crew/tests/test_crew_wave.py -q -k cleanup; the new mutation RED under sabotage.py
Risk: high - removing a worktree that holds unmerged or uncommitted work destroys it
- [ ] `crew_wave.py cleanup --set <slug>`, also run by the wave after each lane's merge is recorded: for each lane marked merged, fetch, then require `git merge-base --is-ancestor <lane head> origin/<default>`, a clean `git status --porcelain` (untracked counts), and no commits outside the default branch. Only then `git worktree remove <path>` (no `--force`), `git branch -d <branch>` (no `-D`), and finally `git worktree prune`.
- [ ] Anything else is kept and reported as one line per lane with the reason: not merged, dirty, untracked, unpushed commits, or could-not-tell (a fetch or git failure). The wave's final report lists removed and kept lanes.
- [ ] Tests (a throwaway repo with a bare origin): a merged clean lane is removed with its branch deleted (must-allow); a dirty one, one with untracked files, one with an unmerged commit, and one after a failed fetch are each kept (must-block); an unmerged lane is never touched.
- [ ] Sabotage: drop the porcelain check (the dirty lane is removed; its test goes red); use `branch -D` (the unmerged-branch test goes red).
- [ ] README: the wave removes merged lanes' worktrees and says what it keeps and why.

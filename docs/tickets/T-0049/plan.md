# T-0049 plan            spec: docs/tickets/T-0049/spec.md (reconstructed; the owner's .work copy wins if it exists)

Owner approves (risk: high). Reconstructed 2026-10-04; nothing below is approved until the owner says so.

Preconditions: none merged first. T-0060 (#363) waits on this ticket's merge. Re-grep every anchor in the spec on main before step 1 and stop if `crew_autopilot.next_phase`, `FIXED_STOPS`, `AUTONOMOUS_STOPS`, `AUTOPILOT_MAX_LINES` or `HARNESS`/`SEAM` moved in shape (line numbers alone may move).

Crew version: one patch past main at merge, set in the last commit. Merge commits only (never rebase). No step registers a hook.

Safety rules for every step:
- Unknown is its own answer; nothing that cannot be read becomes `free`, `mine` or `gone`.
- `holds()` and `next` write nothing. Only `claim`, `release`, `clear` and `beat-loop` write, and only under `<git-common-dir>/crew/inflight/`.
- Nothing clears a marker by age. Autopilot never runs `clear`.
- Tests build throwaway git fixtures; nothing touches real config.

### Step 1: measure the environment before any code (spike, no commit of production code)
Files: none committed but a note in the PR body
Test: by hand, recorded in the PR body with the Claude Code version and OS
Risk: high. Every later step rests on these three facts.
- [ ] Does a detached child (`start_new_session=True` on POSIX, `DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP` on Windows) started from a Bash tool call outlive the call, with the sandbox on and off? Record 2+ minutes of beats in a scratch file
- [ ] Which identity the Bash environment exposes: `CLAUDE_CODE_SESSION_ID`, `CLAUDECODE`, the ancestor chain to the Claude Code process, `/proc/self/ns/pid` vs the host's, `/proc/sys/kernel/random/boot_id`
- [ ] Does `os.kill(<claude pid>, 0)` from inside the sandbox succeed? (T-0030's BLOCK says no on Linux)
- [ ] If the child does not survive, or no stable holder identity exists: stop and ask (spec Unknowns: the PostToolUse fallback). Do not start step 2 on a guess. OWNER CHECK

### Step 2: `crew_inflight.py` read path: the marker, `holds()` and the state table
Files: plugin/crew/hooks/scripts/crew_inflight.py, plugin/crew/tests/test_crew_inflight.py
Test: python3 -m pytest plugin/crew/tests/test_crew_inflight.py -q -k "holds or state or probe"
Risk: high. This is the guard's decision.
- [ ] tests first, red: one test per must-block and must-allow row of acceptance 2, named for the row (`test_holds_unreadable_marker_is_unknown`, `test_holds_dead_pid_same_ns_is_stale`, `test_holds_other_pidns_is_unmeasured_not_gone`, `test_holds_zombie_is_stale`, `test_holds_pid_reused_is_stale`, `test_holds_future_heartbeat_is_unknown`, `test_holds_session_alone_is_not_mine`, `test_holds_other_worktree_fresh_is_elsewhere`, `test_holds_absent_dir_is_free`, `test_holds_inflight_path_is_a_file_is_unknown`, `test_holds_duplicate_keys_is_unknown`, `test_holds_u2028_in_runner_is_single_line`, ...), plus `test_holds_writes_nothing` (mtime snapshot of the worktree and git dir) and `test_holds_two_arg_call` (T-0060's call shape)
- [ ] `_marker_path(root, ticket)` via `crew_ticket.state_dir`; `crew_ticket.check_ticket` for the id; strict JSON (duplicate keys refused) with a shape check of every field; `lstat` first so a symlink, directory or FIFO is `unknown` without opening it
- [ ] the probe returns `alive`, `gone` or `unmeasured`. `gone` only when host, boot_id and pidns all match and the pid is missing, a zombie (`/proc/<pid>/stat` state `Z`), or its start time differs. Windows: `OpenProcess` + `GetExitCodeProcess` + creation time via ctypes; any failure `unmeasured`
- [ ] the state table, in this order: unreadable/invalid -> `unknown`; future heartbeat -> `unknown`; heartbeat older than `TTL_SECONDS` or probe `gone` -> `stale`; holder identity matches -> `mine`; other worktree -> `elsewhere`; else `live`. `clear` set for `stale` and `unknown`

### Step 3: write path: `claim`, `release`, `clear`, `beat-loop`, CLI
Files: plugin/crew/hooks/scripts/crew_inflight.py, plugin/crew/tests/test_crew_inflight.py
Test: python3 -m pytest plugin/crew/tests/test_crew_inflight.py -q
Risk: high. A race here is two holders.
- [ ] tests first: `test_claim_publishes_with_link_and_refuses_a_second`, `test_claim_race_two_processes_one_wins`, `test_claim_by_holder_refreshes`, `test_release_by_non_holder_refuses`, `test_clear_refuses_live_and_mine`, `test_clear_needs_by_and_reason`, `test_clear_logs_event`, `test_beat_loop_keyed_by_token` (an old loop never blocks a new holder's), `test_beat_loop_exits_on_token_change`, `test_beat_interval_is_min_600_ttl_third`, `test_cli_holds_unknown_exits_0`, `test_cli_values_reject_control_chars`
- [ ] `claim`: refuses unless `holds()` is `free` or `mine`; publishes with `os.link` from a complete temp file; starts `beat-loop` detached with the token; prints `claimed` / `refreshed` / `refused: <state> <who> since <t>`
- [ ] `release` and `clear` under the per-ticket lock (crew_train `_Lock` shape, never removed for age); `clear` re-reads the state under the lock and refuses anything but `stale`/`unknown`
- [ ] every write is temp + `os.replace` (CLAUDE.md, Landmines: `open(p, "w")`); `newline="\n"` everywhere

### Step 4: autopilot reads it
Files: plugin/crew/hooks/scripts/crew_autopilot.py, plugin/crew/hooks/scripts/crew_state.py, plugin/crew/tests/test_crew_autopilot.py
Test: the commands of the `.crew/verify.json` rules whose paths hold `crew_autopilot.py` and `crew_state.py` (28, 29 and 8 today; find them by path)
Risk: high. A stop that passes on an exception is the fail-open.
- [ ] tests first: `test_next_runner_live_stops_in_flight`, `test_next_runner_stale_names_clear`, `test_next_runner_unknown_stops`, `test_next_runner_elsewhere_stops_handover`, `test_next_runner_import_error_stops`, `test_next_runner_free_and_mine_match_plain_next`, `test_next_without_runner_is_unchanged` (every existing `next` fixture, byte-identical), `test_next_runner_writes_nothing`
- [ ] `next_phase(..., runner=None)`: after `_phase` and before the ticket-mismatch check, when `runner` is set, lazy-import `crew_inflight` and call `holds(root, ticket, runner=runner)`; any exception is phase `in-flight` naming it. CLI `--runner` with `choices=crew_inflight.RUNNERS` resolved lazily (an unknown runner is exit 2)
- [ ] `FIXED_STOPS` gains `in-flight` and `handover-elsewhere`; module docstring's `next` section names them
- [ ] `AUTONOMOUS_STOPS` gains `clear-inflight`; condense one comment in `crew_state.py` by the same line count so it stays at 3400 (`.pylintrc:140`). L-0582 expects no other `crew_state.py` change

### Step 5: the command
Files: plugin/crew/commands/autopilot.md, plugin/crew/tests/test_lifecycle_commands.py, plugin/crew/tests/test_crew_autopilot.py
Test: python3 -m pytest plugin/crew/tests/test_lifecycle_commands.py plugin/crew/tests/test_crew_autopilot.py -q; python3 plugin/crew/hooks/scripts/_test/validate-prompts.py (the rule whose paths hold `plugin/crew/commands/**`)
Risk: medium. Prose the model follows; the decision itself is in code.
- [ ] section 2: after `resume`/`activate`, `crew_inflight.py claim --root . --ticket <ticket> --runner autopilot`; `refused:` prints and stops
- [ ] section 3: `next` gains `--runner autopilot` on its existing continuation line
- [ ] section 4: `in-flight` and `handover-elsewhere` join the `next enforces` list; `- \`clear-inflight\` - clearing another runner's in-flight marker.` joins the explicit-yes list
- [ ] section 5: release at the report (`crew_inflight.py release --root . --ticket <ticket>`), also when stopping for a handoff
- [ ] all of it by rewording in place: target 109 lines (net 0) so T-0060 keeps its line; at most 110. If it does not fit, stop and ask; never raise `AUTOPILOT_MAX_LINES`. OWNER CHECK
- [ ] `EXPECTED_CLI["autopilot.md"]` gains `crew_inflight.py claim --root .` and `crew_inflight.py release --root .`
- [ ] each commit touching `crew_autopilot.py` or `autopilot.md` carries `Tooling-seam: <path>`

### Step 6: `/crew:status`
Files: plugin/crew/hooks/scripts/crew_status.py, plugin/crew/tests/test_status.py
Test: the command of the `.crew/verify.json` rule whose paths hold `crew_status.py`
Risk: medium.
- [ ] tests first: `test_status_inflight_lines`, `test_status_inflight_unknown_dir`, `test_status_inflight_caps_at_five`, `test_status_output_fits_forty` and `test_status_is_read_only` stay green with markers present
- [ ] one `_inflight_lines(root)` section; `Tooling-seam: plugin/crew/hooks/scripts/crew_status.py` trailer

### Step 7: sabotage, and the tooling-PR split
Files: plugin/crew/tests/sabotage_inflight.py, plugin/crew/tests/sabotage.py
Test: python3 plugin/crew/tests/sabotage.py (filtered to INFLIGHT_MUTATIONS if it supports a filter); python3 scripts/check-tooling-pr.py
Risk: medium. The QA analysis's repeat finding was exactly this file's placement.
- [ ] write `INFLIGHT_MUTATIONS` (acceptance 9's ten rows, the `sabotage_autopilot.py` tuple shape); run each by hand on the feature branch and paste the red table in the PR body
- [ ] if `check-tooling-pr.py` on main still classes `sabotage*.py` as harness: the feature PR does NOT carry `sabotage_inflight.py` or the `sabotage.py` registration; they land in a separate harness-only PR right after the feature merges (the pattern `pending-tickets.md` records for T-0013, T-0048, T-0063). Agree this with the owner and record acceptance 9 as DEFERRED with that PR's reference before reserving review round 1. OWNER CHECK
- [ ] if a feature-owned `sabotage_<area>.py` is a test on main by then: it rides in the feature PR and only the `sabotage.py` registration is split, or nothing is, per the rule then in force

### Step 8: docs, refresh, version (version last)
Files: .crew/verify.json, plugin/crew/README.md, plugin/crew/BUDGETS.md, .crew/codemap/crew.md, .crew/codemap/INDEX.md, docs/diagrams/process-crew-lifecycle.mmd, CHANGELOG.md, plugin/PLUGINS.md, plugin/crew/.claude-plugin/plugin.json, .claude-plugin/marketplace.json
Test: python3 scripts/check-marketplace.py (after committing); python3 scripts/gate-runner.py
Risk: low.
- [ ] `.crew/verify.json`: a rule for `crew_inflight.py`, `test_crew_inflight.py` (and `sabotage_inflight.py` when it lands), with a measured `seconds` and `why`
- [ ] README: the autopilot section (claim, `--runner`, the two stops, `clear-inflight`), the status section (`in-flight:` lines), and a short "In-flight markers" passage: path, fields, states, TTL and heartbeat, never cleared by age, the clear command, out of scope across clones
- [ ] `.crew/codemap/crew.md` + `INDEX.md` row and the lifecycle diagram, or `Docs: none - <why>` in the PR body; `graphify update .` only
- [ ] `BUDGETS.md` claim-marked total re-measured
- [ ] CHANGELOG entry; then, last commit, the crew version one patch past main in `plugin.json`, `marketplace.json` and PLUGINS.md
- [ ] PR body: step 1's measurements; the sabotage table; which suites ran and which did not (`drift-detection.sh` not run: this ticket does not touch the update path); each `Tooling-seam:` path; the split decision of step 7

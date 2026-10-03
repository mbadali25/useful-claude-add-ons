# T-0060 plan            spec: .work/tickets/T-0060/spec.md

Owner approves (risk: high), or T-0010's policy path once it lands. Preconditions: T-0051 is merged, and T-0049 is merged before step 4 (spec Unknowns). Re-read every spec-only anchor in the spec on main before step 1, and stop if `crew_notify.py`'s `send`, `SUBJECTS`, `RESERVED` or `NOTIFY_MUTATIONS`, or `crew_inflight.holds()`, landed with a different contract. Crew version: one patch past main at merge. Merge commit (D-028). No step registers a new hook.

Split from T-0051 on 2026-09-26 by owner decision. This is the `blocker` share of `.work/tickets/T-0051/plan.pre-split.md`: step 6, the `blocker` parts of steps 2, 3 and 5, and the blocker share of steps 7 and 8. Step 4 (the lane reason) is new at the split.

### Step 1: `blocker` joins the vocabulary
Files: plugin/crew/hooks/scripts/crew_notify.py, plugin/crew/tests/test_crew_notify.py
Test: python3 -m pytest plugin/crew/tests/test_crew_notify.py -q -k "blocker or subject or reserved"
Risk: med. A blocker left reserved is every ping in this ticket silently filtered.
- [ ] `EVENTS = ("blocker", "deploy", "question")`, `RESERVED = ()`. `KINDS = ("approval", "rounds", "lane", "lane-unknown", "gate")`. `SUBJECTS` gains `("blocker", "approval"): "Approval waiting"`, `("blocker", "rounds"): "Review out of rounds"`, `("blocker", "lane"): "Lane stalled"`, `("blocker", "lane-unknown"): "Lane state unknown"`, `("blocker", "gate"): "Stop gate refused"`, and `("blocker", None): "Blocked"` for no or an unknown kind
- [ ] `send(root, event, reason, ticket=None, unblock=None, outcome=None, kind=None)`: loud for `blocker`. The CLI `send` gains `--kind`. The fingerprint stays `event|ticket|reason`
- [ ] T-0051's `test_reserved_blocker_sends_nothing_and_names_t0060` is replaced by `test_blocker_sends_loud`, and its sabotage row is removed from `NOTIFY_MUTATIONS` in step 6
- [ ] tests: `test_blocker_sends_loud`, `test_blocker_subject_per_kind` (parametrised over `KINDS`), `test_blocker_without_kind_is_blocked`, `test_legacy_review_enables_blocker`

### Step 2: out of review rounds
Files: plugin/crew/hooks/scripts/review_ledger.py, plugin/crew/tests/test_crew_notify_hooks.py
Test: python3 -m pytest plugin/crew/tests/test_crew_notify_hooks.py -q -k rounds
Risk: med. A notify call inside the ledger's lock, or one that raises, could stall or break the review record.
- [ ] `review_ledger.py`: after `_mutate` in `record` (`:238-286`) returns, when the new state is `REVIEWED`, `_spent(data) >= BUDGET` and `counts["BLOCK"] > 0`, call `crew_notify.send(root, "blocker", f"out of review rounds, {n} BLOCK open", ticket=ticket, unblock=f"/crew:plan {ticket}", kind="rounds")` inside `try/except Exception` that only writes to stderr. The import is lazy, inside that branch. The lock is released before any network call
- [ ] tests: `test_out_of_rounds_with_block_sends_blocker`, `test_non_final_round_with_block_sends_nothing`, `test_final_round_clean_or_fix_only_sends_nothing`, `test_record_succeeds_when_notify_raises`

### Step 3: approval waiting, through `run-stop`
Files: plugin/crew/hooks/scripts/crew_notify.py, plugin/crew/commands/autopilot.md, plugin/crew/tests/test_crew_notify_hooks.py, plugin/crew/tests/test_crew_autopilot.py, plugin/crew/tests/test_lifecycle_commands.py
Test: python3 -m pytest plugin/crew/tests/test_crew_notify_hooks.py plugin/crew/tests/test_crew_autopilot.py plugin/crew/tests/test_lifecycle_commands.py -q; (cd plugin/crew && python3 hooks/scripts/_test/validate-prompts.py)
Risk: med. A decision left in prose is untested, and a line over budget fails the lifecycle tests.
- [ ] `run_stop(root, ticket, phase, reason)` and CLI `run-stop --root . --ticket <id> --phase <phase> --reason <text>`: phase `approve` sends `blocker` kind `approval` (reason `plan waiting on approval`, unblock `/crew:approve <ticket>`). Every phase not named in this ticket returns `filtered`. Exit 0 always, printing the result word
- [ ] `autopilot.md` section 6 (`:117-120`): one line, at every stop, `python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/crew_notify.py run-stop --root . --ticket <ticket> --phase <next's phase> --reason "<next's reason>"`, once per run. Re-read the line budget on main first (`plugin/crew/tests/test_lifecycle_commands.py:26`, `:60`); if the line does not fit by rewording section 6, stop and ask (spec Unknowns)
- [ ] `EXPECTED_CLI["autopilot.md"]` (`plugin/crew/tests/test_lifecycle_commands.py:88-90`) gains `crew_notify.py run-stop --root .`. If T-0018's line pin has landed by then, it moves by exactly the lines added, and the PR says so
- [ ] tests: `test_run_stop_approve_sends_blocker`, `test_run_stop_other_phases_send_nothing` (parametrised over the stop slugs on main that this ticket does not name), `test_autopilot_report_calls_run_stop` (in `test_crew_autopilot.py`), `test_command_never_types_approve` stays green

### Step 4: lane died or stalled (needs T-0049 on main)
Files: plugin/crew/hooks/scripts/crew_notify.py, plugin/crew/tests/test_crew_notify_hooks.py
Test: python3 -m pytest plugin/crew/tests/test_crew_notify_hooks.py -q -k lane
Risk: high. A holder state that cannot be read and is taken as quiet is the fail-open this repo keeps shipping.
- [ ] re-read on main first: `crew_inflight.holds()`'s signature and return, the marker fields that name the runner and `since`, and the `clear` command `status` prints. If T-0049 is not on main, stop (spec Unknowns)
- [ ] `run_stop` for phase `in-flight`: lazily import `crew_inflight` and call `holds(root, ticket)`. `stale` sends `blocker` kind `lane`, reason `lane stalled: <runner> since <t>`, unblock the `clear` command. `unknown`, `ImportError` or any exception sends kind `lane-unknown`, reason `lane state unknown: <why>`, unblock `/crew:status`. `live`, `mine`, `free` and `elsewhere` return `filtered`. Nothing is written under `<git-common-dir>/crew/inflight`
- [ ] tests (`holds` stubbed): `test_lane_stale_sends_blocker`, `test_lane_unknown_sends_lane_unknown`, `test_lane_import_error_sends_lane_unknown`, `test_lane_live_mine_free_elsewhere_send_nothing`, `test_lane_same_stale_marker_sends_once_per_window`, `test_run_stop_writes_nothing_under_inflight`

### Step 5: the Stop refusal blocker
Files: plugin/crew/hooks/scripts/crew_notify.py, plugin/crew/hooks/scripts/verify-gate.sh, plugin/crew/hooks/scripts/verify-gate.ps1, plugin/crew/hooks/scripts/completion_audit.py, plugin/crew/tests/test_crew_notify_hooks.py
Test: python3 -m pytest plugin/crew/tests/test_crew_notify_hooks.py -q -k stop; the .crew/verify.json commands of the verify-gate twins rule and of the rule whose paths include completion_audit.py (0-based 4 and 25 at 502cb137; find them by path)
Risk: high. verify-gate is the repo's own gate. A slow or failing call placed before its `exit 2` could change its verdict or time it out.
- [ ] `stop_outcome(root, gate, refused, payload_bytes)`: the identity is `prompt_id` when present, else the sha256 of `event_claim.normalise(payload)`. The ticket comes from `crew_ticket.resolve_active(root)`, or `no-ticket`. `<state>/stops.json` maps `(gate, session_id, ticket)` -> the list of refusal identities since the last pass, under the same lock and `os.replace` as `sent.json`. A pass clears the key. A refusal whose identity is already listed is a twin, and nothing changes. A refusal that makes the list two or more distinct identities sends `blocker` (kind `gate`, reason `<gate> gate refused twice`, unblock `/crew:status`), deduped as usual
- [ ] CLI `stop --root . --gate verify|audit --refused|--passed` (payload on stdin), printing its result word and exiting 0
- [ ] `verify-gate.sh`: immediately before `:1844`, when `FAILED` is non-zero, run `printf '%s' "$INPUT" | timeout 12 "$PY" "$FP_DIR/crew_notify.py" stop --root . --gate verify --refused >/dev/null 2>&1 || true`; before the final `exit 0` (`:1863`) the same with `--passed`. `FP_DIR` is the script directory set at `plugin/crew/hooks/scripts/verify-gate.sh:373`. The exit status of the gate is unchanged
- [ ] `verify-gate.ps1`: the same two calls before `:1920` and `:1956`, through the existing process helper with a 12 s wait, errors swallowed
- [ ] `completion_audit.py` `stop_hook`: before `return 2` at `:273` call `crew_notify.stop_outcome(root, "audit", True, raw)` and on the `ok` return call it with `False`, each in `try/except Exception` writing only to stderr. `stop_hook` gains the raw bytes from `_payload`, and its return values are unchanged
- [ ] tests: `test_first_refusal_sends_nothing`, `test_second_refusal_sends_one_blocker`, `test_pass_between_refusals_resets`, `test_twin_flavours_count_one_refusal` (the same payload twice), `test_no_prompt_id_uses_payload_digest`, `test_gate_exit_code_unchanged_when_notify_fails` (verify-gate.sh with `crew_notify.py` replaced by a script exiting 1 still exits 2 on a failing rule), `test_completion_audit_return_unchanged_when_notify_raises`

### Step 6: the sabotage rows
Files: plugin/crew/tests/sabotage_notify.py, plugin/crew/tests/test_crew_notify_hooks.py
Test: python3 plugin/crew/tests/sabotage_notify.py (every mutation red on its named test, tree restored byte-identical)
Risk: low. An anchor that drifts makes its mutation test nothing, so the anchor-presence test holds each one.
- [ ] append to `NOTIFY_MUTATIONS`: `_spent >= BUDGET` dropped (`test_non_final_round_with_block_sends_nothing`); refusal threshold 2 -> 1 (`test_first_refusal_sends_nothing`); refusal identity check removed (`test_twin_flavours_count_one_refusal`); the `approve` branch of `run_stop` removed (`test_run_stop_approve_sends_blocker`); `run_stop`'s default made to send (`test_run_stop_other_phases_send_nothing`); `stale` handled as `live` (`test_lane_stale_sends_blocker`); the `unknown` branch returning `filtered` (`test_lane_unknown_sends_lane_unknown`); `"blocker"` put back in `RESERVED` (`test_blocker_sends_loud`). Remove T-0051's reserved-blocker row (step 1)
- [ ] `test_every_notify_sabotage_anchor_is_present_exactly_once` covers the new rows
- [ ] run the suite and record, in the PR body, every mutation with the test that went red. A mutation still green is a finding, not a pass

### Step 7: docs, verify map, version
Files: plugin/crew/skills/crew-notify/SKILL.md, plugin/crew/CONFIG.md, plugin/crew/README.md, .crew/verify.json, plugin/crew/.claude-plugin/plugin.json, plugin/PLUGINS.md, .claude-plugin/marketplace.json, CHANGELOG.md, plugin/crew/BUDGETS.md, .crew/codemap/crew.md, .crew/codemap/INDEX.md, docs/diagrams/process-crew-lifecycle.mmd, docs/guides/crew/src/daily-workflow-scope.md, docs/guides/crew/src/troubleshooting.md, docs/guides/crew/crew-1.0-daily-workflow.html, docs/guides/crew/crew-1.0-daily-workflow.docx, docs/guides/crew/crew-1.0-daily-workflow.pdf, docs/guides/crew/crew-1.0-troubleshooting.html, docs/guides/crew/crew-1.0-troubleshooting.docx, docs/guides/crew/crew-1.0-troubleshooting.pdf
Test: python3 scripts/check-marketplace.py; python3 scripts/_test/self-claims.py; python3 -m pytest plugin/crew/tests/ -q (serially)
Risk: low. A missed version bump leaves every installed machine without the blocker pings.
- [ ] crew-notify SKILL.md, CONFIG.md's notify section and README: the `blocker` event, its kinds and subjects, where each fires (ledger, `run-stop` at autopilot's report, the Stop gates), that the lane reason reads T-0049's markers and TTL, and that `reserved` is gone
- [ ] guides: `docs/guides/crew/src/daily-workflow-scope.md` ("After two review rounds") and `troubleshooting.md` (the review-rounds passage) say the last round with a BLOCK sends the `Review out of rounds` ping; `troubleshooting.md` also names `Stop gate refused` and `Lane stalled` where it covers the gates and autopilot. Rebuild with `python3 docs/guides/crew/src/build.py` and read the renderer it names
- [ ] `.crew/codemap/crew.md` (hook table and the notify paragraph) and its `INDEX.md` row, via `/crew:onboard --refresh crew`; `docs/diagrams/process-crew-lifecycle.mmd`'s Stop hooks node and anchors via `/crew:diagram`. Each one left unchanged gets `Docs: none - <why>` in the PR body
- [ ] `plugin/crew/BUDGETS.md`: re-measure the `crew-markdown-lines` claim after every Markdown edit above (`git ls-files 'plugin/crew/*.md' | xargs cat | wc -l`), last
- [ ] `.crew/verify.json`: T-0051's notify rule gains `plugin/crew/hooks/scripts/review_ledger.py` in its paths
- [ ] bump crew one patch past main at merge in `plugin/crew/.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json` and PLUGINS.md's claim line. A CHANGELOG entry names the four reasons and their subjects
- [ ] PR body: the sabotage table; which T-0049 and T-0051 anchors moved; that `test_gates_powershell.py` ran on Linux pwsh, not native Windows; and that `drift-detection.sh` was not run, unless it was

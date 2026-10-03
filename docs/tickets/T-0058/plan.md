# T-0058 plan            spec: .work/tickets/T-0058/spec.md

Owner approves (risk: high), or T-0010's policy path once it lands. Preconditions: T-0052, T-0012 and T-0019 are merged (and T-0037, through T-0052). Re-read every spec-only anchor in the spec on main before step 1, and stop if `crew_split`, `mint`, `split_policy` or `superseded` landed with a different contract. Crew version: one patch past main at merge. Merge commit (D-028).

Split from T-0052 on 2026-09-26 under the owner's standing authorization. This is group B of `.work/tickets/T-0052/plan.pre-split.md`: step 5, step 3's policy half, and group B's share of steps 9-10.

### Step 1: the ticket split policy and apply via autopilot
Files: plugin/crew/hooks/scripts/crew_split.py, plugin/crew/hooks/scripts/crew_autopilot.py, plugin/crew/tests/test_crew_split.py
Test: python3 -m pytest plugin/crew/tests/test_crew_split.py -q -k "apply or policy"
Risk: high. This is the path that creates tickets with no human yes, so a policy that allows on an unknown is an unattended split nobody approved.
- [ ] `ticket_split_policy(top, ticket)` in `crew_split.py` returns `{allow, policy, risk, known, reason}`. `jira` -> refuse ("the owner runs /crew:split <KEY>"). `sdp` -> refuse ("SDP is a service desk, not where this work gets decomposed"). Otherwise, T-0012's split rule applied to the parent's spec risk (unknown reads `high`): call the slug-free core if T-0012 exposes one; if not, factor `_split_rule(cfg, risk, known)` out of `split_policy` in `crew_autopilot.py`, with `split_policy`'s behaviour and T-0012's tests unchanged
- [ ] `apply(top, ticket, via)` gains `via="autopilot"`: refused unless `ticket_split_policy` allows, asked at this moment and never read from a record. The policy is its approval, so T-0052's human-turn `confirm` applies to `via="command"` only. Everything after (pre-split copy, mint order, parent status last) is T-0052's unchanged
- [ ] CLI `crew_split.py apply --via command|autopilot`
- [ ] tests (must-block): `test_policy_refuses_jira_even_under_self` (calls `ticket_split_policy` directly, so `apply`'s own jira refusal cannot mask it), `test_policy_refuses_sdp`, `test_policy_refuses_human`, `test_policy_refuses_risk_not_low` (`med`, `high`, unknown), `test_policy_refuses_without_allow_cli_approval`, `test_policy_refuses_unarmed`, `test_policy_reasked_at_apply` (the policy flipped to `human` between check and apply -> refused)
- [ ] tests (must-allow): `test_apply_self_files_mode_mints_children` (children folders, direction bodies carry the verbatim criteria, INDEX rows `ready`, parent `superseded` with `split-into`), `test_apply_risk_low_obsidian_mode`, `test_apply_via_command_needs_no_policy`

### Step 2: autopilot's size check, the `split` subcommand and the report
Files: plugin/crew/hooks/scripts/crew_autopilot.py, plugin/crew/commands/autopilot.md, plugin/crew/tests/test_crew_autopilot_split.py, plugin/crew/tests/test_crew_autopilot.py, plugin/crew/tests/test_lifecycle_commands.py
Test: python3 -m pytest plugin/crew/tests/test_crew_autopilot_split.py plugin/crew/tests/test_crew_autopilot.py plugin/crew/tests/test_lifecycle_commands.py -q
Risk: high. A check that always fires stalls every run, and one that never fires is the check the owner asked for, missing.
- [ ] `next_phase`: after `spec_only` passes (`crew_autopilot.py:358-364`) call `_split_gate(top, ticket, "spec")`, and after `problems` is empty (`:365-371`) call it with `"plan"`. `_split_gate` reads `crew_split.triggers(measure(...), stage)`. With nothing fired, it continues. With an `unknown:*`, it stops as `split-check-unknown`, naming the measure. With a fired trigger it reads `split.md`: missing, or its `answered:` set lacks a fired trigger -> `split-check` (not a stop, command `/crew:autopilot split <id>`). `not-too-big` -> continue. `slices` -> continue at `spec`, and at `plan` only when `crew_split.parse_slices` validates (T-0059), else `plan` with the slice problems; when `parse_slices` does not exist, stop as `split-check-unknown` naming T-0059. `split` not applied -> `split-approval` (stop). Parent `superseded` -> `closed`
- [ ] `split` subcommand: `crew_autopilot.py split --root . --ticket <id>` prints the measures and triggers; `--check` runs `check_proposal`; `--apply` runs `crew_split.apply(..., via="autopilot")`. Add `split` to the router's available list, or to the argparse choices if the router has not landed
- [ ] `autopilot.md`: section 2 gains `split-check` (dispatch crew:explorer for boundaries, write `split.md` per the rulebook format, run `split --check`, go back through `next`) and `split-approval` (run `split --apply`; on a refusal stop with `/crew:split <id>` as the last line, and, when `crew_notify.py` exists, send T-0051's `blocker --reason "split waiting on approval" --unblock "/crew:split <id>"`). Section 4's stops list names `split-approval` and `split-check-unknown`
- [ ] tests: `test_no_trigger_goes_straight_to_plan`, `test_acceptance_trigger_after_spec_names_split_check`, `test_plan_steps_trigger_after_plan_names_split_check`, `test_not_too_big_continues`, `test_new_trigger_after_plan_restales_spec_decision`, `test_unknown_measure_stops`, `test_slices_without_parse_slices_stops_unknown`, `test_split_decision_stops_at_split_approval`, `test_superseded_parent_is_closed`, `test_split_subcommand_check_and_apply` (self/files -> children; human -> exit non-zero naming `/crew:split <id>`); `EXPECTED_CLI["autopilot.md"]` gains `crew_autopilot.py split --root .`; `test_command_never_types_approve` stays green; new `test_autopilot_never_runs_crew_split`

### Step 3: sabotage
Files: plugin/crew/tests/sabotage_split.py, plugin/crew/tests/test_crew_split.py
Test: python3 plugin/crew/tests/sabotage_split.py (every mutation red on its named test, tree restored byte-identical)
Risk: low. An anchor that drifts makes its mutation test nothing, so the anchor-presence test holds each one.
- [ ] append to `SPLIT_MUTATIONS`: jira refusal removed from `ticket_split_policy` (`test_policy_refuses_jira_even_under_self`); policy re-ask replaced by the value recorded at check (`test_policy_reasked_at_apply`). `test_every_split_sabotage_anchor_is_present_exactly_once` covers both
- [ ] run it and record every mutation, T-0052's included, with its red test in the PR body. A mutation still green is a finding

### Step 4: verify map, docs, version
Files: .crew/verify.json, plugin/crew/README.md, plugin/crew/.claude-plugin/plugin.json, plugin/PLUGINS.md, .claude-plugin/marketplace.json, CHANGELOG.md
Test: python3 scripts/check-marketplace.py; python3 scripts/_test/self-claims.py; python3 -m pytest plugin/crew/tests/ -q (serially)
Risk: low. A missed version bump leaves every installed machine without the size check.
- [ ] `.crew/verify.json`: T-0052's `crew_split` rule gains the path and run entry for `plugin/crew/tests/test_crew_autopilot_split.py`
- [ ] README: autopilot's size check after spec and after plan and "a trigger means look, never split"; `split-check`, `split-approval` and `split-check-unknown`; the approval policy; Jira always the owner's `/crew:split`; SDP stop
- [ ] bump crew one patch past main at merge in `plugin/crew/.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json` and PLUGINS.md's claim, with a CHANGELOG entry
- [ ] PR body: which dependency anchors moved; that `drift-detection.sh` was not run, unless it was

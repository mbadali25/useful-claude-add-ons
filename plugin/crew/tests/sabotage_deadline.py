"""The crew 1.2.117 mutations: the Stop gate's hook deadline, its persistence
during a run, its diff base and its stale-lock reclaim. Same tuple shape as
`sabotage.py`'s MUTATIONS -- (label, target, find, replace, test) -- and
appended to it there. Run `sabotage.py`, not this file.

Each mutation reintroduces one of the four defects measured on 2026-11-07 (an
862s Stop against a 600s hook limit), or the unknown-into-safe-value collapse
its fix could fall into. Every target is a case in
`test_verify_gate_deadline.py`.
"""
import os

CREW = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SH = os.path.join(CREW, "hooks", "scripts", "verify-gate.sh")
_T = "tests/test_verify_gate_deadline.py::"

DEADLINE_MUTATIONS = (
    ("deadline: rules run with no clock again (defect 1)", SH,
     "  if deadline_defers \"$OWN_RI\" \"$OWN_PRICE\" \"$c\"; then\n",
     "  if false; then\n",
     _T + "test_a_rule_that_would_pass_the_hook_deadline_is_deferred_by_name"),
    ("deadline: a rule deferred for the deadline still verifies the tree", SH,
     "&& [ \"${DEADLINE_DEFER_N:-0}\" -eq 0 ]; }",
     "; }",
     _T + "test_a_rule_that_would_pass_the_hook_deadline_is_deferred_by_name"),
    ("deadline: an unpriced rule is treated as free", SH,
     "      elif [ -z \"$_dd_price\" ] && [ \"$_dd_left\" -gt 0 ]; then\n",
     "      elif [ -z \"$_dd_price\" ]; then\n",
     _T + "test_an_unpriced_rule_with_no_time_left_is_deferred_not_treated_as_free"),
    ("persistence: timings and the in-flight command written only at the end (defect 2)", SH,
     "  gate_progress \"$IDENT\" \"$(date +%s)\" \"$GATE_DEADLINE_S\"\n",
     "  :\n",
     _T + "test_timings_and_the_in_flight_command_are_on_disk_before_the_run_ends"),
    ("persistence: the quiet log written only at the end (defect 2)", SH,
     "  if [ \"${CREW_GATE_QUIET:-0}\" -eq 1 ] && [ \"$CREW_GATE_MAY_LOG\" -eq 1 ] && [ -f \"$CREW_GATE_BUF\" ] \\\n",
     "  if false && [ \"$CREW_GATE_MAY_LOG\" -eq 1 ] && [ -f \"$CREW_GATE_BUF\" ] \\\n",
     _T + "test_the_quiet_log_is_written_while_the_run_goes"),
    ("persistence: a run killed at the deadline is never priced (defect 2)", SH,
     "  \"$PY\" \"$FP_DIR/verify_record.py\" inflight-settle 2>&1 | tr -d '\\r' >&2 || true\n",
     "  :\n",
     _T + "test_a_run_killed_at_the_deadline_prices_its_rule_for_the_next_stop"),
    ("base: the diff base is the local main again (defect 3)", SH,
     "  if git rev-parse --verify -q \"refs/remotes/origin/$DEF^{commit}\" >/dev/null 2>&1; then\n",
     "  if false; then\n",
     _T + "test_the_base_is_origin_main_not_a_stale_local_main"),
    ("lock: a dead holder's lock backs the gate off again (defect 4)", SH,
     "      if [ \"$OWNER_STATE\" = dead ]; then\n",
     "      if false; then\n",
     _T + "test_a_lock_whose_holder_is_dead_is_reclaimed_at_once"),
    ("lock: an owner beside another run's token is trusted", SH,
     "  [ \"$_os_token\" = \"$(tr -d '\\r\\n' < \"$LOCK/token\" 2>/dev/null)\" ] || { echo unknown; return; }\n",
     "  :\n",
     _T + "test_an_owner_that_cannot_be_trusted_keeps_the_old_rules[mismatched-token]"),
)

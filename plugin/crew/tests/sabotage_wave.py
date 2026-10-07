"""The T-0029 mutations: `/crew:autopilot wave` (crew_wave.py), the scope
guard's subagent never-list and `review_ledger.py`'s `allow_abbrev=False`.
Same tuple shape as `sabotage.py`'s MUTATIONS -- (label, target, find,
replace, test) -- and appended to it there; `sabotage.py` sits near
`.pylintrc`'s max-module-lines, so this list lives apart. Run `sabotage.py`,
not this file.

Each one is a way a wave could start the wrong lane, run it unguarded, spend
a review round twice, read an unknown as a pass, let a lane accept its own
review, or remove a worktree that still holds work.
"""
import os

CREW = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_S = os.path.join(CREW, "hooks", "scripts")
WAVE = os.path.join(_S, "crew_wave.py")
GUARD = os.path.join(_S, "scope_guard.py")
LEDGER = os.path.join(_S, "review_ledger.py")

_W = "tests/test_crew_wave.py::"
_G = "tests/test_scope_guard_wave.py::"

WAVE_MUTATIONS = (
    ("WAVE: plan drops the Touch-overlap check", WAVE,
     '        clash = next((w["ticket"] for w in wave if touch_overlaps(row["touch"], w["touch"])), '
     'None)\n',
     "        clash = None\n",
     _W + "test_plan_refuses_overlapping_touch[second0]"),
    ("WAVE: unknown dependencies read as none", WAVE,
     "    if not found:\n        return None\n    ids = _ID_RE.findall(found.group(1))\n",
     "    if not found:\n        return []\n    ids = _ID_RE.findall(found.group(1))\n",
     _W + "test_plan_refuses_unknown_dependencies[title]"),
    ("WAVE: a direction-status ticket is eligible", WAVE,
     '    if status == "direction":\n',
     "    if False:\n",
     _W + "test_plan_refuses_direction_status_ticket"),
    ("WAVE: a relaunch reserves a fresh review round", WAVE,
     "        lines.append(_launch(top, slug, ticket, _reserved_round(top, ticket)))\n",
     '        lines.append(_launch(top, slug, ticket, review_ledger.reserve(top, ticket, "claude")[1]))\n',
     _W + "test_relaunch_resumes_reserved_round_without_new_reservation"),
    ("WAVE: collect reads a missing lane file as clean", WAVE,
     '        return dict(row, reason=f"its lane file is {state}")\n',
     '        return dict(row, state="clean", reason=f"its lane file is {state}")\n',
     _W + "test_collect_missing_lane_file_reads_unknown"),
    ("WAVE: the guard drops its agent_type branch", GUARD,
     "    if isinstance(agent_type, str) and agent_type.strip() and (\n",
     "    if False and (\n",
     _G + "test_subagent_review_ledger_accept_is_refused[module]"),
    ("WAVE: the guard's never-list reaches the main session", GUARD,
     "    if isinstance(agent_type, str) and agent_type.strip() and (\n",
     "    if (\n",
     _G + "test_main_session_review_ledger_accept_is_allowed[module]"),
    ("WAVE: scope_enforcing accepts report (auto in its ramp)", WAVE,
     '        if mode != "block":\n',
     '        if mode not in ("block", "report"):\n',
     _W + "test_scope_not_enforcing_stops_the_wave[config2]"),
    ("WAVE: lane-init runs in the main checkout", WAVE,
     "    if os.path.normcase(top) == os.path.normcase(main_top):\n",
     "    if False:\n",
     _W + "test_lane_init_refuses_main_checkout"),
    ("WAVE: lane-init skips the worktree's scope mode", WAVE,
     "    ok, why = scope_enforcing(top, [ticket])\n    if not ok:\n        return False, why\n"
     "    crew_ticket.activate(top, ticket)\n",
     '    ok, why = True, ""\n    if not ok:\n        return False, why\n'
     "    crew_ticket.activate(top, ticket)\n",
     _W + "test_lane_init_refuses_when_worktree_scope_not_block[off]"),
    ("WAVE: the guard's pattern misses --acc", GUARD,
     '--(?:a(?:c(?:c(?:e(?:pt?)?)?)?)?"',
     '--(?:a(?:c(?:ce(?:pt?)?)?)?)?"',
     _G + "test_subagent_accept_reject_abbreviation_is_refused[--acc]"),
    ("WAVE: review_ledger.py abbreviates again", LEDGER,
     "allow_abbrev=False)",
     "allow_abbrev=True)",
     _G + "test_review_ledger_abbreviated_accept_is_an_argparse_error[--acc]"),
    ("WAVE: cleanup drops the porcelain check", WAVE,
     "        if dirt:\n            return False, f\"{dirt} in {worktree}\"\n",
     "        if False:\n            return False, f\"{dirt} in {worktree}\"\n",
     _W + "test_cleanup_keeps_a_dirty_lane"),
    ("WAVE: cleanup force-deletes the branch", WAVE,
     '    if _git(top, "branch", "-d", branch)[0] != 0:\n',
     '    if _git(top, "branch", "-D", branch)[0] != 0:\n',
     _W + "test_cleanup_never_force_deletes_a_branch"),
    ("WAVE: scope_enforcing reads only the worktree's own config", WAVE,
     "    data, state = _read_json(crew_common.repo_config_file(top))\n",
     '    data, state = _read_json(os.path.join(top, ".crew", "config.json"))\n',
     _W + "test_scope_enforcing_in_a_linked_worktree_reads_the_main_checkout_config"),
)

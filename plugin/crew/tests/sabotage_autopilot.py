"""The T-0004 mutations: `crew_autopilot.py`, `crew_ticket.parse_risk` and
`commands/autopilot.md`. Same tuple shape as `sabotage.py`'s MUTATIONS --
(label, target, find, replace, test) -- and appended to it there;
`sabotage.py` sits near `.pylintrc`'s max-module-lines, so this list lives
apart. Run `sabotage.py`, not this file.

Each one is a way autopilot could drive past a person, guess a ticket, or
write where it must not.
"""
import os

CREW = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(CREW, "hooks", "scripts")
AUTOPILOT = os.path.join(SCRIPTS, "crew_autopilot.py")
TICKET = os.path.join(SCRIPTS, "crew_ticket.py")
COMMAND = os.path.join(CREW, "commands", "autopilot.md")
_T = "tests/test_crew_autopilot.py::"

AUTOPILOT_MUTATIONS = (
    ("an unknown spec risk reads as low", TICKET,
     '    return {"risk": "high", "known": False}\n',
     '    return {"risk": "low", "known": False}\n',
     _T + "test_risk_absent_reads_high"),
    ("plan approval stops nothing", AUTOPILOT,
     '        return answer("approve", True, ',
     '        return answer("approve", False, ',
     _T + "test_next_never_returns_approve_without_stop"),
    ("T-0008 missing reads as fresh artifacts", AUTOPILOT,
     '        return {"state": UNAVAILABLE, "command": "", "reason": REFRESH_UNAVAILABLE}\n',
     '        return {"state": FRESH, "command": "", "reason": REFRESH_UNAVAILABLE}\n',
     _T + "test_refresh_unavailable_stops"),
    ("the INDEX fallback takes the first of several open tickets", AUTOPILOT,
     "            if len(candidates) > 1:\n",
     "            if False:\n",
     _T + "test_resume_several_open_tickets_stops"),
    ("the command drops an AUTONOMOUS_STOPS id", COMMAND,
     "- `git-destruction` - ",
     "- ",
     _T + "test_command_names_every_autonomous_stop"),
    ("a mode typo arms autopilot", AUTOPILOT,
     '    armed = mode == "plan"\n',
     '    armed = str(mode).strip().lower() == "plan"\n',
     _T + "test_mode_typo_is_off"),
    # ---- round 1 (T-0004-02ixAb), one per new stop
    ("BLOCK: a spent budget with no receipt still reviews (writes NEEDS_REPLAN)", AUTOPILOT,
     "    if not ok and (not isinstance(left, int) or left < 1):\n",
     "    if False:\n",
     _T + "test_next_budget_spent_without_a_receipt_stops"),
    ("an INCOMPLETE round is rerun unattended", AUTOPILOT,
     '    if latest.get("verdict") != "CLEAN" and not ok:\n',
     "    if False:\n",
     _T + "test_next_incomplete_round_stops"),
    ("BLOCK: the command lets a review phase fix and rerun", COMMAND,
     "never fix and rerun inside the phase",
     "fix and rerun inside the phase",
     _T + "test_command_ends_the_review_phase_at_the_verdict"),
    ("the post-implement approval stop loses its header-only reason", AUTOPILOT,
     "                return was\n",
     "                return None\n",
     _T + "test_next_post_implement_approval_stop_names_the_header_edit"),
    ("no INDEX row reads as an approved direction", AUTOPILOT,
     "    if status is None:\n",
     "    if False:\n",
     _T + "test_next_direction_approval_unknown_stops"),
    ("open questions do not stop", AUTOPILOT,
     "    if questions:\n",
     "    if False:\n",
     _T + "test_next_open_questions_stop"),
    ("any unknown artifact is refreshed", AUTOPILOT,
     '    return (artifact.get("status") == UNKNOWN and artifact.get("refreshable") is True\n'
     "            and ORPHANED_ANCHOR in reason)\n",
     '    return artifact.get("status") == UNKNOWN\n',
     _T + "test_refresh_unknown_other_cause_stops"),
    ("one settled artifact carries an unsettled one", AUTOPILOT,
     "            or not all(_settles(a) for a in pending):\n",
     "            or not any(_settles(a) for a in pending):\n",
     _T + "test_refresh_one_unsettled_artifact_stops_the_rest"),
    ("an answer-level unknown is refreshed through a stale artifact", AUTOPILOT,
     '    overall_unknown = status == UNKNOWN and not any(a.get("status") == UNKNOWN '
     "for a in pending)\n",
     "    overall_unknown = False\n",
     _T + "test_refresh_overall_unknown_over_stale_artifacts_stops"),
    ("a refresh check that raised reads as fresh", AUTOPILOT,
     '        return {"state": UNSETTLED, "command": "",\n'
     '                "reason": f"the refresh check could not run',
     '        return {"state": FRESH, "command": "",\n'
     '                "reason": f"the refresh check could not run',
     _T + "test_refresh_check_that_raises_stops"),
    ("the handoff's ticket folder is not checked", AUTOPILOT,
     "    if not os.path.isdir(crew_ticket.ticket_dir(top, arg)):\n",
     "    if False:\n",
     _T + "test_resume_handoff_ticket_without_a_folder_falls_through"),
    ("a ticket other than the active one is driven", AUTOPILOT,
     '    if where == "active-ticket" and active != ticket:\n',
     "    if False:\n",
     _T + "test_resume_handoff_disagreeing_with_the_active_pointer_stops"),
    ("the driven ticket is never activated", AUTOPILOT,
     '"activate": where != "active-ticket"}',
     '"activate": False}',
     _T + "test_resume_from_handoff_line"),
    ("the command never activates the ticket", COMMAND,
     "`activate=1` (no pointer is set)",
     "(no pointer is set)",
     _T + "test_command_activates_the_ticket_only_without_a_pointer"),
    ("stale-after-review writes crew state", AUTOPILOT,
     "        return answer(\"stale-after-review\", True, ",
     "        os.close(os.open(os.path.join(crew_ticket.state_dir(top), \"x\"), "
     "os.O_CREAT | os.O_WRONLY))\n"
     "        return answer(\"stale-after-review\", True, ",
     _T + "test_next_stale_after_review_stops_without_writing"),
)

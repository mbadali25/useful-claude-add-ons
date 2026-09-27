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
    ("a pre-T-0026 approval stop loses its header-only reason", AUTOPILOT,
     "                return was\n",
     "                return None\n",
     _T + "test_next_legacy_receipt_header_edit_names_the_header_edit"),
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
    # ---- round-2 fixes: human-stop bypasses found after round 1
    ("a blank or unknown INDEX status reads as an approved direction", AUTOPILOT,
     "    if status not in DIRECTION_APPROVED:\n",
     "    if False:\n",
     _T + "test_next_index_status_that_does_not_say_approved_stops"),
    ("an INDEX done row is re-driven", AUTOPILOT,
     "    if status in INDEX_DONE:\n",
     "    if False:\n",
     _T + "test_next_index_status_done_stops_as_closed"),
    ("an open question starting with `none` reads as answered", AUTOPILOT,
     '_ANSWERED = re.compile(r"^(?:(?:none|n/a)(?:$|\\s*[-:,(\\u2013\\u2014])|\\[x\\]|~~|-$)")\n',
     '_ANSWERED = re.compile(r"^(?:none|n/a|\\[x\\]|~~|-$)")\n',
     _T + "test_next_open_question_that_only_looks_answered_stops"),
    ("a sub-heading ends the open questions section", AUTOPILOT,
     "            if depth and level > depth:\n                continue\n",
     "            if False:\n                continue\n",
     _T + "test_next_open_question_that_only_looks_answered_stops"),
    ("next drives a ticket the scope guard does not judge by", AUTOPILOT,
     "    if broken or active != ticket:\n",
     "    if broken:\n",
     _T + "test_next_stops_when_another_ticket_is_active"),
    ("next drives when no pointer and INDEX names another ticket", AUTOPILOT,
     "    if broken or active != ticket:\n",
     "    if broken or (where == \"active-ticket\" and active != ticket):\n",
     _T + "test_next_stops_when_the_scope_guard_would_judge_another_ticket"),
    ("a crash in next prints no stop", AUTOPILOT,
     "        except Exception as exc:  # pylint: disable=broad-except\n"
     "            # A crash cannot tell the phase",
     "        except crew_ticket.TicketError as exc:  # pylint: disable=broad-except\n"
     "            # A crash cannot tell the phase",
     _T + "test_cli_that_raises_prints_a_stop"),
    ("a crash in resume prints no stop", AUTOPILOT,
     "        except Exception as exc:  # pylint: disable=broad-except\n"
     "            # A crash cannot tell which ticket",
     "        except crew_ticket.TicketError as exc:  # pylint: disable=broad-except\n"
     "            # A crash cannot tell which ticket",
     _T + "test_cli_that_raises_prints_a_stop"),
    ("the command lets autopilot accept or post a review", COMMAND,
     "are the human's. Go back",
     "are autopilot's. Go back",
     _T + "test_command_leaves_accept_and_pr_review_to_the_human"),
    ("the command reads a crash or no output as permission", COMMAND,
     "Anything but a\n`stop=0` line - no output, a traceback, a non-zero exit - is a stop.",
     "",
     _T + "test_command_reads_no_answer_as_a_stop"),
)

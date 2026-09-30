"""The T-0049 mutations: `crew_inflight.py`, `crew_holder.processes_in` and the
in-flight check in `crew_autopilot.next_phase`. Same tuple shape as
`sabotage.py`'s MUTATIONS -- (label, target, find, replace, test) -- and
appended to it there. Run `sabotage.py`, not this file.

Each refusing branch has one mutation that reads an in-flight ticket as free
(or lets a non-owner act); each must turn its named test red. The last three
are must-allow non-vacuity checks: a guard that refuses everything would pass
every must-block test, so breaking the allow path must turn an allow test red.
"""
import os

CREW = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(CREW, "hooks", "scripts")
INFLIGHT = os.path.join(SCRIPTS, "crew_inflight.py")
HOLDER = os.path.join(SCRIPTS, "crew_holder.py")
AUTOPILOT = os.path.join(SCRIPTS, "crew_autopilot.py")
_I = "tests/test_crew_inflight.py::"
_H = "tests/test_crew_holder.py::"
_A = "tests/test_crew_autopilot_inflight.py::"

_MINE = 'if runner is not None and record["runner"] == runner and crew_holder.same_holder(me, holder):'

INFLIGHT_MUTATIONS = (
    ("a stale heartbeat reads fresh", INFLIGHT,
     "    if age is None or age > TTL_MINUTES * 60:\n",
     "    if False:\n",
     _I + "test_begin_refuses_stale_marker_and_prints_clear_command"),
    ("a live marker reads free", INFLIGHT,
     "return _answer(LIVE, ticket, f\"{record['runner']} holds it",
     "return _answer(FREE, ticket, f\"{record['runner']} holds it",
     _I + "test_begin_refuses_live_marker"),
    ("a provably gone pid is adopted", INFLIGHT,
     '    if crew_holder.probe_holder(holder).state == "gone":\n',
     "    if False:\n",
     _I + "test_begin_refuses_dead_pid_marker_as_stale"),
    ("an unreadable marker reads as no marker", INFLIGHT,
     "        return _answer(UNKNOWN, ticket, why)\n",
     "        return _answer(FREE, ticket, why)\n",
     _I + "test_begin_refuses_unreadable_marker"),
    ("the same session with another runner reads as mine", INFLIGHT,
     _MINE,
     "if runner is not None and crew_holder.same_holder(me, holder):",
     _I + "test_begin_refuses_same_session_other_runner"),
    ("a missing session id reads as mine or free", INFLIGHT,
     '    if me is None and answer["state"] in GO:\n',
     "    if False:\n",
     _A + "test_next_without_session_stops"),
    ("the reserved-round signal is skipped", INFLIGHT,
     "            ledger = _ledger_signal(top, ticket, record)\n",
     '            ledger = _answer(FREE, ticket, "skipped")\n',
     _I + "test_reserved_round_without_marker_is_unknown"),
    ("a round release is honoured without its timestamp", INFLIGHT,
     "    return released is not None and reserved is not None and released >= reserved\n",
     "    return True\n",
     _I + "test_reserved_round_released_by_older_clear_is_still_unknown"),
    ("the dirty-worktree signal is skipped", INFLIGHT,
     "                trees = _worktree_signal(top, ticket, marker)\n",
     '                trees = _answer(FREE, ticket, "skipped")\n',
     _I + "test_dirty_worktree_live_pid_is_live"),
    ("processes that cannot be told read as none", INFLIGHT,
     '        if seen == "none":\n',
     '        if seen != "live":\n',
     _I + "test_dirty_worktree_cannot_tell_is_unknown"),
    ("a runner that ended elsewhere reads free", INFLIGHT,
     "            return _answer(ELSEWHERE, ticket, f\"{record['runner']} ended in another checkout",
     "            return _answer(FREE, ticket, f\"{record['runner']} ended in another checkout",
     _I + "test_ended_elsewhere_is_elsewhere"),
    ("clear runs without the owner signal", INFLIGHT,
     "    if not crew_holder.owner_signal():\n",
     "    if False:\n",
     _I + "test_clear_refused_with_claudecode"),
    ("a non-holder beats the marker", INFLIGHT,
     '                or not crew_holder.same_holder(me, record["holder"])):\n',
     "                or False):\n",
     _I + "test_beat_by_non_holder_refused"),
    ("pick takes an unknown ticket", INFLIGHT,
     '        if held["state"] in GO:\n            return {"ticket": held["ticket"]',
     '        if held["state"] in GO + (UNKNOWN,):\n            return {"ticket": held["ticket"]',
     _I + "test_pick_never_takes_unknown"),
    ("processes_in trusts a scan its own pid is invisible to", HOLDER,
     '    if probe_pid(own).state != "alive":\n',
     "    if False:\n",
     _H + "test_processes_in_unknown_when_own_pid_is_invisible"),
    ("next_phase skips the in-flight check", AUTOPILOT,
     "    result = _in_flight(root, ticket, result, runner)\n",
     "    result = dict(result)\n",
     _A + "test_next_stops_on_live_marker"),
    ("a crash inside holds returns the phase", AUTOPILOT,
     '        held = {"state": crew_inflight.UNKNOWN, "reason": f"could not tell ({_failure(exc)})",',
     '        held = {"state": crew_inflight.FREE, "reason": f"could not tell ({_failure(exc)})",',
     _A + "test_next_crash_in_holds_stops"),
    # must-allow non-vacuity
    ("the own runner and holder never read as mine", INFLIGHT,
     _MINE,
     "if False:",
     _I + "test_begin_again_by_same_runner_refreshes"),
    ("the caller's own worktree is judged as another's", INFLIGHT,
     "        if real in own or not os.path.isdir(path):\n",
     "        if not os.path.isdir(path):\n",
     _I + "test_own_dirty_worktree_is_ignored"),
    ("a clean worktree for the ticket reads in flight", INFLIGHT,
     "        if not dirty:\n            continue\n",
     "        if False:\n            continue\n",
     _I + "test_clean_other_worktree_is_ignored"),
)

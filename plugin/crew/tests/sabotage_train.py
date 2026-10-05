"""The merge-train mutations: the train itself (`crew_train.py`, L-0520) and,
from L-0526, the gate round taking it (`review_run.py`) and the reviewer's
brief listing its replays (`review_prompt.py`). Same tuple shape as
`sabotage.py`'s MUTATIONS -- (label, target, find, replace, test) -- and
appended to it there. Run `sabotage.py`, not this file.

Each one is a way two overlapping lanes could both reach gate+land, a land
could go ahead on a verdict for a different tree, or a replayed resolution
could reach the reviewer unseen. S1-S12 are L-0520's acceptance rows; S13-S15
cover its GEN-01/02/07 hardening. R1-R6 and P1-P5 are L-0526's: the gate
round's refusals (R) and the reviewer's catch-up block (P). S16-S19 (L-0520's
PYTHON-set fixes) are not here: their draft was machine-local and did not
reach this branch.
"""
import os

CREW = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(CREW, "hooks", "scripts")
TRAIN = os.path.join(SCRIPTS, "crew_train.py")
RUN = os.path.join(SCRIPTS, "review_run.py")
PROMPT = os.path.join(SCRIPTS, "review_prompt.py")
_T = "tests/test_crew_train.py::"
_R = "tests/test_review_run_train.py::"
_P = "tests/test_review_prompt.py::"

TRAIN_MUTATIONS = (
    ("S1 the hold decision ignores overlap", TRAIN,
     "        if pairs:\n            found.append((other, pairs))\n",
     "        if pairs and False:\n            found.append((other, pairs))\n",
     _T + "test_second_overlapping_acquire_waits"),
    ("S2 an undeclared Touch overlaps nothing", TRAIN,
     "    if mine is None or theirs is None:\n",
     "    if mine is None or theirs is None:\n        return []\n",
     _T + "test_undeclared_touch_overlaps_everything"),
    ("S3 check-land skips the moved-in-Touch check", TRAIN,
     '    in_touch = [p for p in moved if meets_touch(p, entry.get("touch"))]\n',
     "    in_touch = []\n",
     _T + "test_check_land_refuses_base_moved_in_touch"),
    ("S4 check-land skips the receipt check", TRAIN,
     "    ok, message = review_ledger.check_receipt(top, ticket)\n",
     '    ok, message = True, "skipped"\n',
     _T + "test_check_land_requires_receipt_on_merged_head"),
    ("S5 the wait event is written without its paths", TRAIN,
     '                                         "paths": [list(p) for p in pairs]}',
     "                                         }",
     _T + "test_overlap_decision_logged_with_paths"),
    ("S6 review_run skips the train step", RUN,
     "    return train_gate(args)\n",
     "    return None\n",
     _R + "test_second_overlapping_gate_round_is_refused_unspent"),
    ("S7 catch-up does not set rerere.enabled", TRAIN,
     '    _git_ok(top, "config", scope, "rerere.enabled", "true")\n',
     '    _git_ok(top, "config", scope, "rerere.enabled", "false")\n',
     _T + "test_catch_up_replays_rerere_resolution_into_merge_log"),
    ("S8 an unreadable train state reads as not armed", TRAIN,
     '        return None, "could not tell", f"{path} cannot be read: {exc}"\n',
     '        return None, "absent", f"{path} cannot be read: {exc}"\n',
     _T + "test_unreadable_state_is_could_not_tell"),
    ("S9 earlier overlapping waiters are ignored", TRAIN,
     '        earlier = other.get("state") == "waiting" and other.get("order", 0) < '
     'entry.get("order", 0)\n',
     "        earlier = False\n",
     _T + "test_earlier_overlapping_waiter_goes_first"),
    ("S10 an old lock is removed", TRAIN,
     "                if time.monotonic() > deadline:\n",
     "                if time.time() - os.path.getmtime(self.path) > 3600:\n"
     "                    os.remove(self.path)\n"
     "                    continue\n"
     "                if time.monotonic() > deadline:\n",
     _T + "test_lock_is_never_broken_by_age"),
    ("S11 acquire drops a stale-looking holder", TRAIN,
     "        lines = _notices(root, state, entry)\n",
     '        state["entries"] = [o for o in state["entries"] if o is entry or '
     "not _stale(top, o)]\n"
     "        lines = _notices(root, state, entry)\n",
     _T + "test_stale_holder_is_reported_never_released"),
    ("S12 a merge-tree conflict (exit 1) reads as clean", TRAIN,
     "    if code == 0:\n        return []\n    if code == 1:\n",
     "    if code in (0, 1):\n        return []\n    if code == 1:\n",
     _T + "test_check_land_refuses_merge_tree_conflict"),
    ("S13 the lock is removed without checking its owner", TRAIN,
     "            if mine:\n                os.remove(self.path)\n",
     "            if mine or True:\n                os.remove(self.path)\n",
     _T + "test_lock_release_verifies_its_owner"),
    ("S14 a lookup under a non-directory proves the state absent", TRAIN,
     "        if not stat.S_ISDIR(mode):\n",
     "        if False:\n",
     _T + "test_windows_style_not_found_under_a_file_is_could_not_tell"),
    ("S15 a malformed train entry reads as ok", TRAIN,
     "        problem = _entry_problem(entry)\n",
     "        problem = None\n",
     _T + "test_malformed_entry_is_could_not_tell"),
    ("R1 an unreadable train reads as unarmed at the gate round", RUN,
     '        if where == "absent":\n            return None\n',
     '        if where != "ok":\n            return None\n',
     _R + "test_unreadable_train_refuses_the_round"),
    ("R2 a crash in the train step lets the round be reserved", RUN,
     '             "no round reserved\\n")\n        return EXIT_TRAIN\n',
     '             "no round reserved\\n")\n        return None\n',
     _R + "test_train_crash_refuses_never_reserves"),
    ("R3 a waiting ticket goes on to reserve", RUN,
     "    if code != crew_train.EXIT_OK:\n",
     "    if False:\n",
     _R + "test_second_overlapping_gate_round_is_refused_unspent"),
    ("R4 a spent budget still takes the train", RUN,
     "    if _budget_spent(args):\n        return None\n    return train_gate(args)\n",
     "    return train_gate(args)\n",
     _R + "test_a_spent_budget_is_refused_without_taking_the_train"),
    ("R5 the train is taken after the pre-review checks", RUN,
     "    return train_gate(args)\n",
     "    return prereview_gate(args) or train_gate(args)\n",
     _R + "test_the_train_answers_before_the_pre_review_checks"),
    ("R6 the train is taken after the standards self-check", RUN,
     "    return train_gate(args)\n",
     "    return standards_gate(args) or train_gate(args)\n",
     _R + "test_the_train_answers_before_the_standards_self_check"),
    ("P1 the reviewer's brief drops the catch-up block", PROMPT,
     "                  _catch_up_block(root, ticket),\n",
     "",
     _P + "test_prompt_lists_rerere_replayed_files"),
    ("P2 an unreadable merge log is silent", PROMPT,
     '    if where == "could not tell":\n        return [CATCH_UP_TITLE,',
     '    if where == "could not tell":\n        return None\n        return [CATCH_UP_TITLE,',
     _P + "test_prompt_marks_an_unreadable_merge_log"),
    ("P3 a merge-log read that raises takes the brief down", PROMPT,
     "        rows, where, why = crew_train.read_merge_log(root, ticket)\n"
     "    except Exception as exc:",
     "        rows, where, why = crew_train.read_merge_log(root, ticket)\n"
     "    except ValueError as exc:",
     _P + "test_a_merge_log_that_raises_is_unknown_never_silent"),
    ("P4 a malformed replayed list is iterated as paths", PROMPT,
     "        if not isinstance(replayed, list) or not all(isinstance(p, str) for p in replayed):\n",
     "        if False:\n",
     _P + "test_a_malformed_replayed_list_is_unknown_never_dropped"),
    ("P5 a replayed path reaches the brief unescaped", PROMPT,
     "        out += [f\"  {review_checks.one_line(path)} ({base})",
     "        out += [f\"  {path} ({base})",
     _P + "test_a_replayed_path_with_a_newline_stays_one_prompt_line"),
)

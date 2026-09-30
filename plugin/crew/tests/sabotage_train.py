"""The L-0520 mutations: the merge train (`crew_train.py`) and the gate round
taking it (`review_run.py`). Same tuple shape as `sabotage.py`'s MUTATIONS --
(label, target, find, replace, test) -- and appended to it there. Run
`sabotage.py`, not this file.

Each one is a way two overlapping lanes could both reach gate+land, a land
could go ahead on a verdict for a different tree, or a replayed resolution
could reach the reviewer unseen. S1-S12 are the spec's acceptance rows.
"""
import os

CREW = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(CREW, "hooks", "scripts")
TRAIN = os.path.join(SCRIPTS, "crew_train.py")
RUN = os.path.join(SCRIPTS, "review_run.py")
_T = "tests/test_crew_train.py::"
_R = "tests/test_review_run_train.py::"

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
    ("S6 review_run.run skips the train step", RUN,
     "    waiting = train_gate(args)\n",
     "    waiting = None\n",
     _R + "test_second_overlapping_gate_round_is_refused_unspent"),
    ("S7 catch-up does not set rerere.enabled", TRAIN,
     '    for key in ("rerere.enabled", "rerere.autoupdate"):\n',
     '    for key in ("rerere.autoupdate",):\n',
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
)

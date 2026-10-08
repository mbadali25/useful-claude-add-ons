"""The L-0638 mutations: one per fail-closed decision in `crew_bridge.py`
(T-0032's cross-session doorbell, L-0636's `pending`, L-0637's hub rule), plus
C-0051's L-0637 review-round 4-6 cases. Same tuple shape as `sabotage.py`'s
MUTATIONS -- (label, target, find, replace, test) -- and appended to it
there. Run `sabotage.py`, not this file.

Each one puts back a way a message from another session is believed without
the record behind it, a ring is lost or read as answered, or a lane rings a
peer -- the unknown collapsing into the safe-looking value -- and names the
must-block case that has to go red.
"""
import os

CREW = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BRIDGE = os.path.join(CREW, "hooks", "scripts", "crew_bridge.py")
_B = "tests/test_crew_bridge.py::"
_P = "tests/test_crew_bridge_pending.py::"
_H = "tests/test_crew_bridge_hub.py::"

BRIDGE_MUTATIONS = (
    # --- receive (T-0032) ------------------------------------------------------------
    ("bridge receive: a prefix match passes for the doorbell", BRIDGE,
     "    found = DOORBELL_RE.fullmatch(body)\n",
     "    found = DOORBELL_RE.match(body)\n",
     _B + "test_trailing_extra_field_is_not_a_doorbell"),
    ("bridge receive: any crew-doorbell/<n> version accepted", BRIDGE,
     '    r"crew-doorbell/1 channel=(?P<channel>',
     '    r"crew-doorbell/[0-9]+ channel=(?P<channel>',
     _B + "test_unknown_version_is_not_a_doorbell"),
    ("bridge receive: the channel comparison skipped", BRIDGE,
     '    if fields is None or fields["channel"] != chan.channel:\n',
     "    if fields is None:\n",
     _B + "test_other_channel_is_not_a_doorbell"),
    ("bridge receive: a failed fetch reads as re-read the record", BRIDGE,
     '    if state == "failed":\n        return f"could not fetch {chan.ref}: {why}"\n',
     '    if state == "failed":\n        return None\n',
     _B + "test_receive_failed_fetch_could_not_tell"),
    ("bridge receive: a non-ancestor tip reads as confirmed", BRIDGE,
     "    if probe.code == 0:\n        return None\n",
     "    if probe.code in (0, 1):\n        return None\n",
     _B + "test_receive_not_an_ancestor_could_not_tell"),
    ("bridge receive: a non-doorbell printed without safe", BRIDGE,
     '        print(crew_coord.peer(f"message: {crew_coord.safe(text)}"))\n',
     '        print(crew_coord.peer(f"message: {text}"))\n',
     _B + "test_a_non_doorbell_is_printed_only_as_safe_peer_data"),

    # --- ring and pending (T-0032, L-0636) ------------------------------------------
    ("bridge ring: a doorbell after a failed fetch", BRIDGE,
     '    tip, state, why = chan.fetch()\n    if state == "failed":\n'
     '        print(f"unknown - could not fetch {chan.ref} from {crew_coord.safe(chan.remote, 80)}: {why}")\n'
     '        return crew_coord.EXIT_UNKNOWN\n    if state == "absent":\n        print(f"refused - ',
     '    tip, state, why = chan.fetch()\n    if False:\n'
     '        print(f"unknown - could not fetch {chan.ref} from {crew_coord.safe(chan.remote, 80)}: {why}")\n'
     '        return crew_coord.EXIT_UNKNOWN\n    if state == "absent":\n        print(f"refused - ',
     _B + "test_ring_failed_fetch_is_unknown_exit_3"),
    ("bridge pending: a failed fetch reads as no pending doorbells", BRIDGE,
     '        print(f"unknown - could not fetch {chan.ref} from {crew_coord.safe(chan.remote, 80)}: {why}")\n'
     '        return crew_coord.EXIT_UNKNOWN\n    if state == "absent":\n        print(f"unknown - ',
     '        print("no pending doorbells")\n'
     '        return crew_coord.EXIT_OK\n    if state == "absent":\n        print(f"unknown - ',
     _P + "test_failed_fetch_is_unknown_never_none_pending"),
    ("bridge pending: this holder's own later line clears its ring", BRIDGE,
     '        quiet = {entry["holder"], session}\n',
     "        quiet = set()\n",
     _P + "test_own_later_lines_keep_the_ring_pending"),
    ("bridge pending: a corrupt log line skipped", BRIDGE,
     "        except ValueError:\n"
     '            return None, f"log.jsonl line {number} is not JSON"\n',
     "        except ValueError:\n            continue\n",
     _P + "test_corrupt_log_line_is_unknown_never_skipped"),

    # --- the hub rule (L-0637) --------------------------------------------------------
    ("bridge hub: ring in a lane allowed", BRIDGE,
     '        if where == "lane":\n            print(HUB_REFUSAL)\n',
     "        if False:\n            print(HUB_REFUSAL)\n",
     _H + "test_ring_in_a_lane_is_refused"),
    ("bridge hub: ring with an unreadable lane marker allowed", BRIDGE,
     '        if where == "unknown":\n'
     '            print(f"unknown - whether this worktree is a wave lane cannot be told: {why}; ',
     "        if False:\n"
     '            print(f"unknown - whether this worktree is a wave lane cannot be told: {why}; ',
     _H + "test_ring_where_the_lane_marker_is_corrupt_is_unknown"),
    # C-0051: L-0637's review rounds 4-6.
    ("bridge hub r4: only the primary checkout's lane files read", BRIDGE,
     "    for tree in trees:\n        state, why = _lane_in(crew_wave, tree, here)\n",
     "    for tree in list(trees)[:1]:\n        state, why = _lane_in(crew_wave, tree, here)\n",
     _H + "test_ring_in_a_lane_of_a_wave_started_from_a_linked_worktree_is_refused"),
    ("bridge hub r5: a started lane whose file is gone reads as no lane", BRIDGE,
     "        gone = _started_without_a_file(crew_wave, main, slug, names)\n",
     "        gone = None\n",
     _H + "test_a_started_lane_whose_file_is_gone_is_unknown"),
    ("bridge hub r6: a lane file that is not UTF-8 read with replacements", BRIDGE,
     '            if state == "ok" and not _strict_utf8(os.path.join(lanes, name)):\n',
     "            if False:\n",
     _H + "test_a_lane_file_that_is_not_utf8_is_unknown"),
)

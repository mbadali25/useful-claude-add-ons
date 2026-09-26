"""Mutations for crew_coord.py (T-0030: cross-session claims) -- a module of
its own, same tuple shape as sabotage_scope.py's SCOPE_MUTATIONS
(label, target, find, replace, test), appended to MUTATIONS by sabotage.py,
which sits at `.pylintrc`'s max-module-lines. Run `sabotage.py`, not this file.

The first eight are the spec's Acceptance list, in its order. The last two
cover the retry and the identity-file check, which the list does not name but
which the claim and recovery guarantees rest on.
"""
import os

CREW = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
COORD = os.path.join(CREW, "hooks", "scripts", "crew_coord.py")
_T = "tests/test_crew_coord.py::"

COORD_MUTATIONS = (
    ("crew_coord pushes with --force-with-lease", COORD,
     '        return ["push", self.remote, f"{sha}:{self.ref}"]\n',
     '        return ["push", "--force-with-lease", self.remote, f"{sha}:{self.ref}"]\n',
     _T + "test_push_argv_never_forces"),
    ("crew_coord reads a stale claim as free", COORD,
     '    return claim["state"] == "working" and heartbeat_age(claim) > ttl_minutes * 60\n',
     "    return False\n",
     _T + "test_stale_working_claim_reads_owner_unknown_and_blocks_claim"),
    ("crew_coord status skips a corrupt claim", COORD,
     ("        if claim is None:\n"
      '            lines.append(f"{safe(key)} unknown (corrupt claim file: {why}) [peer-written]")\n'
      "            code = EXIT_UNKNOWN\n"),
     ("        if claim is None:\n"
      "            continue\n"),
     _T + "test_corrupt_claim_reads_unknown_not_skipped[{not json]"),
    ("crew_coord accepts a claim when the fetch failed", COORD,
     ('            if state == "failed":\n'
      '                return Result("unknown", f"unknown - could not fetch'),
     ("            if False:\n"
      '                return Result("unknown", f"unknown - could not fetch'),
     _T + "test_claim_when_fetch_failed_is_refused_unknown"),
    ("crew_coord lets a non-holder release", COORD,
     ('        if claim["holder"]["session"] != me["session"]:\n'
      '            return "refused", f"refused: only the holder may'),
     ("        if False:\n"
      '            return "refused", f"refused: only the holder may'),
     _T + "test_release_done_heartbeat_by_non_holder_refused[release]"),
    ("crew_coord adopts a claim from another machine", COORD,
     '    if old["machine"] != machine():\n',
     "    if False:\n",
     _T + "test_recover_refuses_other_machine"),
    ("crew_coord adopts while the old PID is alive", COORD,
     ('    if probe.state == "alive":\n'
      '        return False, f"pid {pid} is alive, so the old session may still be running"\n'),
     ('    if probe.state == "alive":\n'
      '        probe = PidProbe("gone", probe.start, probe.measured)\n'),
     _T + "test_recover_refuses_live_pid"),
    ("crew_coord reads an unreadable PID check as dead", COORD,
     '    if probe.state != "gone" or not probe.measured:\n',
     "    if False:\n",
     _T + "test_recover_refuses_when_pid_check_cannot_tell"),
    ("crew_coord gives up on the first rejected push", COORD,
     "        for _ in range(1 + MAX_RETRIES):\n",
     "        for _ in range(1):\n",
     _T + "test_two_sessions_claim_different_tickets_concurrently"),
    ("crew_coord recovers without the identity file naming the holder", COORD,
     "    if not named:\n",
     "    if False:\n",
     _T + "test_recover_refuses_identity_file_naming_another_holder"),
)

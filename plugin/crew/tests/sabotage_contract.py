"""The L-0635 mutations: every fail-closed branch T-0031 (`crew_contract.py`,
versioned contracts on the coordination channel), L-0633 (cross-session
dependencies in `crew_wave.py`) and L-0634 (`check_bindings` and the wave's
refusal) added. Same tuple shape as `sabotage.py`'s MUTATIONS -- (label,
target, find, replace, test) -- and appended to it there. Run `sabotage.py`,
not this file.

Each one puts back a way a contract or a peer's claim that cannot be told, or
that changed, reads as current, closed or absent -- the unknown collapsing
into the safe-looking value -- and names the must-block case that has to go
red.
"""
import os

CREW = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(CREW, "hooks", "scripts")
CONTRACT = os.path.join(SCRIPTS, "crew_contract.py")
COORD = os.path.join(SCRIPTS, "crew_coord.py")
WAVE = os.path.join(SCRIPTS, "crew_wave.py")
_C = "tests/test_crew_contract.py::"
_V = "tests/test_crew_contract_verify.py::"
_D = "tests/test_crew_wave_coord_deps.py::"

CONTRACT_MUTATIONS = (
    # --- T-0031: the contract record ---------------------------------------------
    ("contract: put overwrites a built-against version", CONTRACT,
     '            if record and record["status"] == FROZEN:\n',
     "            if False:\n",
     _C + "test_put_on_a_frozen_version_is_refused"),
    ("contract: build-against runs without an approved ticket", CONTRACT,
     '    if approval["status"] != "approved":\n',
     "    if False:\n",
     _C + "test_build_against_refuses_an_unapproved_ticket"),
    ("contract: build-against skips the body-hash comparison", CONTRACT,
     '        actual = body_hash(found[version][1])\n        if actual != record["hash"]:\n',
     "        actual = body_hash(found[version][1])\n        if False:\n",
     _C + "test_build_against_refuses_a_body_that_does_not_match_its_hash"),
    ("contract: a corrupt earlier version reads as absent", CONTRACT,
     "        if record is None:\n"
     '            raise Unknown(crew_coord.peer(f"contract {name} v{number} has a corrupt record '
     '({why})"))\n',
     "        if record is None:\n            continue\n",
     _C + "test_a_corrupt_earlier_version_stops_every_write[put]"),
    ("contract: build-against reads a corrupt record as absent", CONTRACT,
     '            return "unknown", crew_coord.peer(f"unknown - contract {name} v{version} has a '
     'corrupt record "\n',
     '            return "refused", crew_coord.peer(f"refused: contract {name} v{version} does not '
     'exist "\n',
     _C + "test_build_against_reads_a_corrupt_record_as_unknown[not-json]"),
    ("contract: the channel push gains --force-with-lease", COORD,
     '        return ["push", "--no-verify", "--", PUSH_REMOTE, f"{sha}:{self.ref}"]\n',
     '        return ["push", "--force-with-lease", "--no-verify", "--", PUSH_REMOTE, f"{sha}:{self.ref}"]\n',
     _C + "test_push_argv_never_forces"),
    ("contract: put --new-version supersedes a draft", CONTRACT,
     '            if record["status"] != FROZEN:\n'
     '                return "refused", (f"refused: contract {name} v{latest} is still a {DRAFT}; ',
     "            if False:\n"
     '                return "refused", (f"refused: contract {name} v{latest} is still a {DRAFT}; ',
     _C + "test_new_version_needs_a_frozen_predecessor_and_a_ticket"),

    # --- L-0633: cross-session dependencies --------------------------------------
    ("cross dep: a missing peer claim reads as closed", WAVE,
     '        return f"{unknown}: no claim for {ticket} on crew-coord/{channel}"\n',
     "        return None\n",
     _D + "test_missing_peer_claim_is_unknown"),
    ("cross dep: a working peer claim reads as closed", WAVE,
     '    if claim["state"] == "done":\n        return None\n',
     '    if claim["state"] in ("done", "working"):\n        return None\n',
     _D + "test_working_peer_claim_is_not_closed"),
    ("cross dep: a released peer claim reads as closed", WAVE,
     '    if claim["state"] == "done":\n        return None\n',
     '    if claim["state"] in ("done", "released"):\n        return None\n',
     _D + "test_released_peer_claim_is_not_closed"),
    ("cross dep: a failed fetch reads as closed", WAVE,
     '    files, why = _channel_files(top, channel, channels)\n    if files is None:\n'
     '        return f"{unknown}: {why}"\n',
     "    files, why = _channel_files(top, channel, channels)\n    if files is None:\n"
     "        return None\n",
     _D + "test_failed_fetch_is_unknown"),
    ("cross dep: the first of two same-id claims taken", WAVE,
     "    if len(keys) > 1:\n",
     "    if False:\n",
     _D + "test_two_repositories_with_the_id_refuse_the_short_form"),
    ("cross dep: a malformed cross dependency reads as no dependency", WAVE,
     "    except crew_ticket.TicketError:\n        return None\n    local = ",
     "    except crew_ticket.TicketError:\n        return []\n    local = ",
     _D + "test_index_row_malformed_cross_dep_refuses_as_unknown"),

    # --- L-0634: the hash refusal --------------------------------------------------
    ("contract check: the record-hash comparison dropped", CONTRACT,
     '    if record["hash"] != binding["hash"]:\n',
     "    if False:\n",
     _V + "test_a_changed_contract_is_a_mismatch[record-hash]"),
    ("contract check: the body-hash comparison dropped", CONTRACT,
     '    if body_hash(found[version][1]) != record["hash"]:\n        return "mismatch", ',
     '    if False:\n        return "mismatch", ',
     _V + "test_a_changed_contract_is_a_mismatch[body]"),
    ("contract check: a corrupt bindings file reads as no bindings", CONTRACT,
     '        return {"status": "unknown", "reason": f"contract bindings unknown ({why})", "lines": []}\n',
     '        return {"status": "ok", "reason": "", "lines": []}\n',
     _V + "test_what_cannot_be_checked_is_unknown[bindings-not-json]"),
    ("contract check: a failed fetch reads as a pass", CONTRACT,
     '        state, why, newer = ("unknown", why, []) if files is None else ',
     '        state, why, newer = ("ok", why, []) if files is None else ',
     _V + "test_what_cannot_be_checked_is_unknown[fetch-fails]"),
    ("contract check: the wave never calls check_bindings", WAVE,
     "    refusal = _dep_refusal(top, deps, channels) or _contract_refusal(top, ticket, channels)\n",
     "    refusal = _dep_refusal(top, deps, channels)\n",
     _V + "test_wave_refuses_a_contract_mismatch"),
)

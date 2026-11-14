"""The `guards.enabled` key/writer-half mutations (crew 1.3.93), in `sabotage.py`'s tuple shape:
(label, target, find, replace, test).

Each puts back one way the master switch could be set, kept or reported wrongly, and names the case in
`tests/test_guards_master_key.py` that has to go red. NOT wired into `sabotage.py`: `sabotage*.py` is review
harness (`scripts/check-tooling-pr.py` `HARNESS`), so a feature PR may not edit it. The harness half's mutations
(`sabotage_guards_master.py`) ARE wired. Until a harness-only PR wires this table in too, run it alone with
sabotage.py's own machinery:

    cd plugin/crew/tests && python3 -c "import sabotage, guards_master_key_mutations as m; \
        sabotage.MUTATIONS = m.MASTER_KEY_MUTATIONS; raise SystemExit(sabotage.main())"

`test_every_mutation_anchor_is_present_exactly_once` keeps the anchors honest in the meantime.
"""
import os

CREW = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SCRIPTS = os.path.join(CREW, "hooks", "scripts")
HO = os.path.join(_SCRIPTS, "crew_humanonly.py")
CC = os.path.join(_SCRIPTS, "crew_confirm_config.py")
CFG = os.path.join(_SCRIPTS, "crew_config.py")
MIG = os.path.join(_SCRIPTS, "crew_migrate.py")
STATUS = os.path.join(_SCRIPTS, "crew_status.py")
_K = "tests/test_guards_master_key.py::"

MASTER_KEY_MUTATIONS = (
    ("the writer takes a plain `false` (no double confirmation)", HO,
     '        return MASTER_REFUSAL if value is False else None\n',
     '        return None\n',
     _K + "test_the_machine_writer_takes_true_and_refuses_false_and_the_rest"),
    ("propose takes the master key at the repo layer", CC,
     '    if dotted == crew_humanonly.MASTER_KEY and layer != "machine":\n',
     '    if False:\n',
     _K + "test_propose_refuses_the_repo_layer_and_a_key_that_needs_none"),
    ("propose takes any key", CC,
     '    if not crew_humanonly.is_confirmed_path(dotted):\n',
     '    if False:\n',
     _K + "test_propose_refuses_the_repo_layer_and_a_key_that_needs_none"),
    ("the proposal drops the warning the agent relays", CC,
     '               if record["key"] == crew_humanonly.MASTER_KEY else [])\n',
     '               if False else [])\n',
     _K + "test_the_proposal_prints_a_warning_the_agent_relays"),
    ("the confirmed writer takes the master key at the repo layer", CFG,
     '    if dotted == crew_humanonly.MASTER_KEY and layer != "machine":\n        raise ValueError(',
     '    if False:\n        raise ValueError(',
     _K + "test_apply_confirmed_optout_takes_the_machine_switch_only"),
    ("a write back to true does not revoke the receipt", CFG,
     '        if crew_humanonly.is_confirmed_path(change.get("path")):\n',
     '        if crew_humanonly.is_path(change.get("path")):\n',
     _K + "test_a_crew_write_back_to_true_revokes_the_receipt"),
    ("--rebuild does not judge the master switch", CFG,
     '    master = master_switch_problem(target, layer, current)\n',
     '    master = None\n',
     _K + "test_rebuild_refuses_a_saved_repo_profile_carrying_a_bad_switch"),
    ("--restore does not judge the master switch", CFG,
     '        master = master_switch_problem(restored, layer, current)\n',
     '        master = None\n',
     _K + "test_restore_refuses_a_repo_backup_carrying_a_bad_switch"),
    ("/crew:migrate does not judge the master switch", MIG,
     '    master = crew_config.master_switch_problem(out, "machine", cfg)\n',
     '    master = None\n',
     _K + "test_migrate_refuses_to_carry_a_bad_switch_through"),
    ("the planners accept a `false` (repo and machine)", CFG,
     '    if value is _MISSING or value is True:\n',
     '    if value is _MISSING or value is True or value is False:\n',
     _K + "test_rebuild_refuses_a_saved_repo_profile_carrying_a_bad_switch"),
    ("the planners accept a machine null", CFG,
     '    if value is not False:\n        return f"guards.enabled = {value!r} is not true or false; the machine file takes only those"\n',
     '    if value is None:\n        return None\n'
     '    if value is not False:\n        return f"guards.enabled = {value!r} is not true or false; the machine file takes only those"\n',
     _K + "test_rebuild_refuses_a_saved_machine_profile_carrying_a_bad_switch"),
    ("a machine `false` the file did not hold is introduced", CFG,
     '    if _dig(current, ("guards", "enabled")) is False:\n        return None\n',
     '    if True:\n        return None\n',
     _K + "test_restore_refuses_a_machine_backup_carrying_a_bad_switch"),
    ("--inert drops a repo null", CFG,
     '    return value is not None or dotted in _REPO_REPORTS_NULL\n',
     '    return value is not None\n',
     _K + "test_inert_and_explain_report_every_repo_value_but_the_default"),
    ("--explain drops a repo null", CFG,
     '            if dotted in _REPO_REPORTS_NULL:\n                # Any repo value but',
     '            if False:\n                # Any repo value but',
     _K + "test_explain_reports_a_repo_null_even_when_the_machine_file_holds_the_key"),
    ("--explain prints Python's False", CFG,
     '        asked, forced = (json.dumps(v) if isinstance(v, bool) or v is None else v\n',
     '        asked, forced = (v if True else v\n',
     _K + "test_explain_prints_the_ignored_repo_value_as_json"),
    ("--explain gives the master switch the auto-clear text", CFG,
     '        if row["path"] == "guards.enabled":\n',
     '        if False:\n',
     _K + "test_explain_prints_the_ignored_repo_value_as_json"),
    ("--explain does not flag an unconfirmed false", CFG,
     '                row["unconfirmed"] = True  # false in the file, but no applied double confirmation backs it\n',
     '                pass\n',
     _K + "test_explain_says_an_unconfirmed_machine_false_is_not_in_effect"),
    ("status does not say an unconfirmed false is not in effect", STATUS,
     '        elif crew_hook.machine_switch_unconfirmed(root):\n',
     '        elif False:\n',
     _K + "test_status_says_unconfirmed_not_disabled_for_a_machine_false_nobody_confirmed"),
    ("status does not say a repo false is ignored", STATUS,
     '        if crew_hook.repo_switch_ignored(root):\n',
     '        if False:\n',
     _K + "test_status_says_a_repo_false_is_ignored"),
)

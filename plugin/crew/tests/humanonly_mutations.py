"""crew 1.3.9 human-only opt-out mutations, in `sabotage.py`'s tuple shape.

Each puts back one way the opt-out could take effect when it must not (or a
write could slip past the double confirmation), and names the must-block or
must-allow case in `test_crew_humanonly.py` that has to go red.

Wired into `sabotage.py`'s MUTATIONS since crew 1.3.33, the harness change that
made the hooks read `humanOnly` (`sabotage*.py` is review harness,
`scripts/check-tooling-pr.py` `HARNESS`). To run it alone, with sabotage.py's
own machinery:

    cd plugin/crew/tests && python3 -c "import sabotage, humanonly_mutations as m; \
        sabotage.MUTATIONS = m.HUMANONLY_MUTATIONS; raise SystemExit(sabotage.main())"
"""
import os

CREW = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SCRIPTS = os.path.join(CREW, "hooks", "scripts")
HO = os.path.join(_SCRIPTS, "crew_humanonly.py")
CC = os.path.join(_SCRIPTS, "crew_confirm_config.py")
CFG = os.path.join(_SCRIPTS, "crew_config.py")
TICKET = os.path.join(_SCRIPTS, "crew_ticket.py")
HOOK = os.path.join(_SCRIPTS, "approval_hook.py")
WRAP = os.path.join(_SCRIPTS, "approval-hook.sh")
SCOPE = os.path.join(_SCRIPTS, "scope_guard.py")
_T = "tests/test_crew_humanonly.py::"
_L = "tests/test_humanonly_live.py::"

HUMANONLY_MUTATIONS = (
    ("humanOnly: could-not-tell reads as untracked", HO,
     "                if state != UNTRACKED:\n",
     "                if state == TRACKED:\n",
     _T + "test_a_tracked_or_unknown_repo_file_never_opts_out[could not tell]"),
    ("humanOnly: a true in the other layer no longer vetoes", HO,
     "    if opt_out and not strict:\n",
     "    if opt_out:\n",
     _T + "test_a_repo_true_vetoes_a_confirmed_machine_false"),
    ("humanOnly: a false needs no double-confirmation receipt", HO,
     "                if not backed:\n",
     "                if False:\n",
     _T + "test_a_machine_false_with_no_receipt_is_human_only"),
    ("humanOnly: any applied receipt counts, a newer revocation ignored", HO,
     '    if newest.get("state") == APPLIED and newest.get("value") is False:\n',
     '    if any(r.get("state") == APPLIED for r in settled):\n',
     _T + "test_a_revocation_newer_than_the_receipt_wins"),
    ("humanOnly: the string 'false' opts out", HO,
     "        elif value is not False:\n",
     '        elif value not in (False, "false"):\n',
     _T + "test_a_malformed_value_reads_as_human_only[false]"),
    ("humanOnly: git's exit 128 (not a repo) reads as untracked", HO,
     "    if proc.returncode == 1:\n",
     "    if proc.returncode != 0:\n",
     _T + "test_tracking_outside_a_repository_is_could_not_tell"),
    ("humanOnly: the writers accept a false", HO,
     "    if value is False:\n        return SENSITIVE_REFUSAL\n",
     "    if value is False:\n        return None\n",
     _T + "test_the_writers_refuse_a_change_that_lifts_a_human_step[machine-False]"),
    ("humanOnly: a repo may drop its veto through a writer", HO,
     '        return None if layer == "machine" else REPO_UNVETO_REFUSAL\n',
     "        return None\n",
     _T + "test_the_repo_writer_refuses_removing_a_veto"),
    ("confirm-config: a confirmation from outside a user prompt counts", CC,
     "    if via != crew_humanonly.USER_PROMPT:\n",
     "    if False:\n",
     _T + "test_confirm_refuses_anything_but_a_user_prompt"),
    ("confirm-config: one prompt may confirm twice", CC,
     "    if prompt_id in seen:\n",
     "    if False:\n",
     _T + "test_one_prompt_confirms_once"),
    ("confirm-config: one confirmation applies the change", CC,
     '    if len(record["confirmations"]) < 2:\n',
     '    if len(record["confirmations"]) < 1:\n',
     _T + "test_a_single_confirmation_writes_nothing"),
    ("confirm-config: a proposal never expires", CC,
     '    if record.get("state") == crew_humanonly.PENDING and now > record.get("expires", 0):\n',
     '    if False:\n',
     _T + "test_an_expired_proposal_cannot_be_confirmed"),
    ("confirm-config: propose accepts a tracked repo file", CC,
     "        if state != crew_humanonly.UNTRACKED:\n            raise Refused(",
     "        if False:\n            raise Refused(",
     _T + "test_propose_refuses_a_tracked_or_unknown_repo_file[tracked]"),
    ("confirm-config: the repo file is not re-checked at the second confirmation", CC,
     "        if state != crew_humanonly.UNTRACKED:\n            return _settle(",
     "        if False:\n            return _settle(",
     _T + "test_a_repo_file_tracked_before_the_second_confirmation_is_refused"),
    ("confirm-config: the write is not bound to the proposed file's digest", CC,
     '        writer(record["layer"], record["key"], record["path"], record["targetDigest"],\n',
     '        writer(record["layer"], record["key"], record["path"], None,\n',
     _T + "test_a_file_changed_since_the_proposal_is_stale"),
    ("crew_config: a write back to true does not revoke the receipt", CFG,
     '    _revoke_human_only("machine", real_path, out["plan"][1], path)\n',
     "    pass\n",
     _T + "test_a_crew_write_back_to_true_revokes_the_receipt"),
    # --- crew 1.3.33: the hooks read the opt-out -----------------------------------
    ("humanOnly live: the opt-out never relaxes a cli approval", TICKET,
     "    return human_only_approve_opted_out(top)\n",
     "    return False\n",
     _L + "test_a_double_confirmed_machine_false_lets_a_cli_approval_count"),
    ("humanOnly live: a resolver that raises reads as an opt-out", TICKET,
     "    except Exception:  # noqa: BLE001  # pylint: disable=broad-except\n"
     "        return False\n    return isinstance(answer, dict)",
     "    except Exception:  # noqa: BLE001  # pylint: disable=broad-except\n"
     "        return True\n    return isinstance(answer, dict)",
     _L + "test_an_unreadable_or_odd_resolver_answer_is_human_only[answer0]"),
    ("humanOnly live: anything but True reads as an opt-out", TICKET,
     '    return isinstance(answer, dict) and answer.get("humanOnly") is False\n',
     '    return isinstance(answer, dict) and answer.get("humanOnly") is not True\n',
     _L + "test_an_unreadable_or_odd_resolver_answer_is_human_only[answer3]"),
    ("humanOnly live: approve reads the promoteMarker key", TICKET,
     'answer = crew_humanonly.resolve(top, "approve")',
     'answer = crew_humanonly.resolve(top, "promoteMarker")',
     _L + "test_a_confirmed_promote_marker_opt_out_does_not_relax_approve"),
    ("humanOnly live: a hook confirmation is recorded as not from a prompt", HOOK,
     "            args, via=crew_confirm_config.crew_humanonly.USER_PROMPT,\n",
     '            args, via="cli",\n',
     _L + "test_a_double_confirmed_machine_false_lets_a_cli_approval_count"),
    ("humanOnly live: a command quoted mid-sentence is a command", HOOK,
     '    raw = re.match(r"^\\s*/" + re.escape(name)',
     '    raw = re.search(r"\\s*/" + re.escape(name)',
     _L + "test_a_quoted_or_padded_confirmation_records_nothing"
          "[please run /crew:confirm-config cc-0123abcd for me]"),
    ("humanOnly live: the wrapper drops a confirm-config prompt", WRAP,
     "[Aa][Pp][Pp][Rr][Oo][Vv][Ee]*|*crew:confirm-config*) ;;",
     "[Aa][Pp][Pp][Rr][Oo][Vv][Ee]*) ;;",
     _L + "test_the_wrapper_passes_a_confirm_config_prompt_to_python"),
    ("confirm-config: propose no longer tells the agent the exact command to relay", CC,
     '        f"  To apply it, type /crew:confirm-config {record[\'change_id\']} as its own prompt, "\n',
     '        "  To apply it, the owner types the confirm command, "\n',
     _T + "test_propose_prints_the_lines_to_relay_to_the_owner"),
    # crew 1.3.69: /crew:confirm-config with no usable id lists the proposals.
    ("confirm-config list: a bare command confirms the only pending proposal", HOOK,
     '    if not args:\n        return _refuse_confirm(',
     '    if not args:\n        import crew_humanonly as _h  # sabotage\n'
     '        args = _h.all_records(_h.store_dir())[0][0]["change_id"]\n'
     '    if not args:\n        return _refuse_confirm(',
     _L + "test_no_id_never_records_even_with_exactly_one_pending"),
    ("confirm-config list: the refusal shows no proposals", HOOK,
     "        listing = _proposals_text()\n",
     '        listing = ""\n',
     _L + "test_no_id_lists_the_pending_proposal_with_its_change"),
    ("confirm-config list: an expired proposal is offered as pending", HOOK,
     'record.get("state") == crew_humanonly.PENDING and stamp <= record["expires"]:',
     'record.get("state") == crew_humanonly.PENDING:',
     _L + "test_the_listing_settles_nothing_and_does_not_offer_an_expired_one"),
    ("confirm-config list: an unreadable store reads as none pending", HOOK,
     "    elif problems:\n",
     "    elif False:\n",
     _L + "test_an_unreadable_store_is_could_not_tell_not_none_pending"),
    ("confirm-config list: a record with any key is listed", HOOK,
     '                or record.get("key") not in crew_humanonly.PATHS + (MASTER_KEY,)\n',
     "",
     _L + "test_a_forged_record_is_not_listed"),
    ("confirm-config list: a record's text reaches the screen raw", HOOK,
     '    text = _UNPRINTABLE_RE.sub("?", _one_line(value))\n',
     "    text = str(value)\n",
     _L + "test_a_listed_path_cannot_draw_on_the_owners_screen"),
    ("confirm-config list: a listing failure blocks nothing", HOOK,
     "    except Exception as exc:  # pylint: disable=broad-except\n"
     "        listing = (f\"Could not tell",
     "    except Exception as exc:  # pylint: disable=broad-except\n"
     "        raise\n        listing = (f\"Could not tell",
     _L + "test_a_listing_that_raises_still_refuses_and_says_so"),
    ("humanOnly live: Write/Edit may write the confirmation store", SCOPE,
     "        if _owner_path(path):\n            return True\n",
     "",
     _L + "test_the_session_cannot_write_the_confirmation_store"),
    ("humanOnly live: a shell command may write the confirmation store", SCOPE,
     '    for target in seg.targets:\n        if _hit(target, shell, "file"):\n',
     '    for target in seg.targets:\n        if False and _hit(target, shell, "file"):\n',
     _L + "test_the_session_cannot_write_the_confirmation_store"),
)

"""The T-0075 mutations: the config writers in `crew_config.py`, the file
layer in `crew_config_files.py` and the `/crew:config` menu in
`crew_config_menu.py`. Same tuple shape as `sabotage.py`'s MUTATIONS --
(label, target, find, replace, test) -- and appended to it there;
`sabotage.py` sits near `.pylintrc`'s max-module-lines, so this list lives
apart. Run `sabotage.py`, not this file.

Each one is a way the menu could disarm a guard, write before it validated,
merge over another writer, or delete the only copy of a config.

Review round 2's BLOCK 1, round 3's first BLOCK and round 4's BLOCK 1 (the
verify gate's record) have no code path, so they have no entry here: their
proof is the `verify_record.py report` quoted in the review context.

Round 6 (L-0682, after T-0103): the two leaf-shape branches no entry reached,
`os_error_text` at each of its three call sites (red on every OS through a
backslash filename, which `str(exc)` repr()s), and T-0103's delete messages
and repo-null widening note.
"""
import os

CREW = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(CREW, "hooks", "scripts")
CONFIG = os.path.join(SCRIPTS, "crew_config.py")
FILES = os.path.join(SCRIPTS, "crew_config_files.py")
MENU = os.path.join(SCRIPTS, "crew_config_menu.py")
_C = "tests/test_crew_config.py::"
_F = "tests/test_config_files.py::"
_M = "tests/test_config_menu.py::"

_REPO_PLAN = ('            crew_config.plan_repo_write(root, updates, global_path, '
              'snapshot=snap,\n'
              '                                        machine=machine)\n')
_GLOBAL_PLAN = ('            crew_config.plan_global_write(updates, global_path, '
                'snapshot=snap)\n')


def _value_only(layer, error):
    """A planner closure replaced by the per-value rule alone."""
    return ("            for key, val in updates.items():\n"
            f"                if crew_config.value_allowed(key, \"{layer}\", val):\n"
            f"                    raise crew_config.{error}(\n"
            f"                        crew_config.value_allowed(key, \"{layer}\", val))\n")


CONFIG_MENU_MUTATIONS = (
    # T-0075 landing: a probe closed over `exc`, which the except block unbinds.
    ("menu repo probe closes over the unbound exc", MENU,
     '            reason = str(exc)\n            return (lambda _d, _v: reason), None, reason\n'
     '        machine = crew_config.machine_view(global_path)\n',
     '            return (lambda _d, _v: str(exc)), None, str(exc)\n'
     '        machine = crew_config.machine_view(global_path)\n',
     _M + "test_a_refused_snapshot_probe_names_the_refusal[repo]"),
    ("menu machine probe closes over the unbound exc", MENU,
     '            reason = str(exc)\n            return (lambda _d, _v: reason), None, reason\n\n'
     '        def plan(updates):\n            crew_config.plan_global_write(',
     '            return (lambda _d, _v: str(exc)), None, str(exc)\n\n'
     '        def plan(updates):\n            crew_config.plan_global_write(',
     _M + "test_a_refused_snapshot_probe_names_the_refusal[machine]"),
    ("repo writer admits scope.allowCliApproval", CONFIG,
     '    "scope.allowCliApproval": "decides which approvals the scope guard "\n'
     '                              "accepts; a hand edit by the owner only",\n',
     '',
     _C + "test_repo_writer_refuses[scope.allowCliApproval-True]"),
    ("repo writer admits platform", CONFIG,
     '    "platform": "written only by platform-sync, which repairs it every "\n'
     '                "SessionStart",\n',
     '',
     _C + "test_repo_writer_refuses[platform.os-linux]"),
    ("repo arms auto-clear", CONFIG,
     'REPO_VETO_ONLY = {"context.autoClear.enabled", "resume.auto"}\n',
     'REPO_VETO_ONLY = set()\n',
     _C + "test_repo_writer_refuses[context.autoClear.enabled-True]"),
    # Re-anchored (successor; again in round 5, `shape` bound once): a block is refused twice, by the leaf-path rule
    # (`is_repo_path`) and by `value_allowed`'s shape rule, so removing either
    # alone is equivalent and the test stays green. Both go, in one span.
    ("repo writer accepts a whole block", CONFIG,
     '    if reason is None and not is_repo_path(dotted):\n'
     '        reason = ("not a settable leaf of .crew/config.json (a block is set "\n'
     '                  "one key at a time; unknown keys are refused)")\n'
     '    if reason is None and dotted in REPO_VETO_ONLY and not is_repo_veto(value):\n'
     '        reason = _VETO_ONLY\n'
     '    return reason\n'
     '\n'
     '\n'
     'def value_allowed(dotted, layer, value):\n'
     '    """None when `layer` accepts `value` at the LEAF `dotted`, else why not:\n'
     "    the layer's path rule, a block emptied or replaced by a scalar, the null\n"
     '    rule, then `enum_values` membership. Both planners and the menu use it."""\n'
     '    reason = _layer_path_refusal(dotted, layer, value)\n'
     '    if reason is not None:\n'
     '        return f"{dotted} - {reason}"\n'
     '    shape = _shape(dotted)\n'
     '    if shape == "under":\n'
     '        return f"{dotted} - under a key that takes a value, not keys; set that key to one of its values"\n'
     '    if shape == "block":\n',
     '    if reason is None and not (is_repo_path(dotted) or _shape(dotted) == "block"):\n'
     '        reason = ("not a settable leaf of .crew/config.json (a block is set "\n'
     '                  "one key at a time; unknown keys are refused)")\n'
     '    if reason is None and dotted in REPO_VETO_ONLY and not is_repo_veto(value):\n'
     '        reason = _VETO_ONLY\n'
     '    return reason\n'
     '\n'
     '\n'
     'def value_allowed(dotted, layer, value):\n'
     '    """None when `layer` accepts `value` at the LEAF `dotted`, else why not:\n'
     "    the layer's path rule, a block emptied or replaced by a scalar, the null\n"
     '    rule, then `enum_values` membership. Both planners and the menu use it."""\n'
     '    reason = _layer_path_refusal(dotted, layer, value)\n'
     '    if reason is not None:\n'
     '        return f"{dotted} - {reason}"\n'
     '    shape = _shape(dotted)\n'
     '    if shape == "under":\n'
     '        return f"{dotted} - under a key that takes a value, not keys; set that key to one of its values"\n'
     '    if False:\n',
     _C + "test_repo_writer_refuses_a_whole_block"),
    # Re-anchored (successor): the enum branch now lives in `value_allowed`.
    ("enum check removed", CONFIG,
     '    if allowed is not None and not _in_values(value, allowed):\n',
     '    if False:\n',
     _C + "test_enum_key_outside_its_values_is_refused"),
    ("repo ratchet widening unmarked", CONFIG,
     '        out["widens"] = rank(now) > rank(was)\n',
     '        out["widens"] = False\n',
     _C + "test_repo_ratchet_widening_is_marked"),
    # Re-anchored (successor): the planner-backed probe also refuses every
    # candidate of a refused row, so skipping `choices` alone leaves the row
    # read-only; the row's own `writable` flag is what offers it.
    ("menu offers a refused key", MENU,
     '            "writable": reason is None,\n',
     '            "writable": True,\n',
     _M + "test_refused_rows_offer_no_choices_and_name_a_reason"),
    ("empty choice list", MENU,
     '    return out, (None if out else refusal)\n',
     '    return (out if (table or crew_config.enum_values(dotted)\n'
     '                    or dotted in ctx["known"]) else []), (None if out else refusal)\n',
     _M + "test_every_writable_setting_offers_a_selectable_value"),
    # Re-anchored (round 3): both plans are built in `_plan_both`.
    ("save writes before validating", MENU,
     '        merged, plans["machine"] = crew_config.plan_global_write(\n'
     '            machine, global_path, snapshot=snap)\n',
     '        merged, plans["machine"] = crew_config.write_global_config(\n'
     '            machine, global_path)\n',
     _M + "test_save_validates_both_layers_before_writing_either"),
    # Re-anchored (successor): the backup is now the move itself.
    ("delete removes before the backup", MENU,
     '            got = crew_config_files.move_aside(path, backup)\n',
     '            os.remove(path)\n'
     '            got = crew_config_files.move_aside(path, backup)\n',
     _M + "test_delete_writes_backup_first"),
    ("delete ignores confirmation", MENU,
     '    if confirm != plan["name"]:\n        why =',
     '    if False:\n        why =',
     _M + "test_delete_refuses_without_confirmation"),
    ("delete preview hides the scope guard", CONFIG,
     '    ("scope.mode", "off"): (\n',
     '    ("scope.mode", "never"): (\n',
     _M + "test_delete_preview_names_what_changes"),
    # Review round 1 (T-0075): each fix, reverted. Re-anchored where the
    # successor moved the code; none dropped.
    ("restore command keeps POSIX quoting on Windows", MENU,
     '        "cmd": " ".join(\'"\' + part.replace("\\\\", "/") + \'"\' for part in parts),\n',
     '        "cmd": " ".join(shlex.quote(part) for part in parts),\n',
     _M + "test_restore_command_forms"),
    ("repo veto judged by equality", CONFIG,
     '    return value is False or value is None\n',
     '    return value in (False, None)\n',
     _C + "test_repo_writer_refuses[context.autoClear.enabled-0]"),
    ("menu offers a held 0 as a veto", MENU,
     '        except refused as exc:\n            return str(exc)\n',
     '        except refused as exc:\n'
     '            return None if value == 0 else str(exc)\n',
     _M + "test_repo_veto_rows_never_offer_a_held_zero"),
    ("repo rows writable over an unreadable config", MENU,
     '        except crew_config.RepoWriteRefused as exc:\n'
     '            reason = str(exc)\n            return (lambda _d, _v: reason), None, reason\n',
     '        except crew_config.RepoWriteRefused as exc:\n'
     '            return (lambda _d, _v: None), None, None\n',
     _M + "test_repo_rows_are_read_only_without_a_readable_config[missing]"),
    ("role row hides the global contribution", MENU,
     '    if from_repo and from_global and isinstance(value, dict):\n'
     '        return "repo+global"\n',
     '',
     _M + "test_role_row_names_both_layers_it_merges"
     "[repo_pin0-global_pin0-repo+global]"),
    ("save lets a write-time refusal escape", MENU,
     '        except (OSError, crew_config.GlobalWriteRefused,\n'
     '                crew_config.RepoWriteRefused, crew_config.ProviderError) as exc:\n'
     '            # Validated',
     '        except OSError as exc:\n'
     '            # Validated',
     _M + "test_save_reports_a_partial_refusal"),
    ("machine menu hides platform and schema", MENU,
     '    if layer == "machine":\n        paths.extend(',
     '    if False:\n        paths.extend(',
     _M + "test_machine_menu_shows_platform_and_schema_read_only"),
    ("delete preview drops a guard the ratchet holds", MENU,
     '            if holder is not None:\n',
     '            if False:\n',
     _M + "test_delete_preview_names_a_guard_the_ratchet_holds[allow-True]"),
    ("delete preview resets platform leaves to null", MENU,
     '        if dotted in redetected:\n',
     '        if False:\n',
     _M + "test_delete_preview_names_platform_as_re_detected"),
    ("typed delete name is the root's basename", MENU,
     '    return os.path.basename(top or os.path.realpath(root))\n',
     '    return os.path.basename(os.path.realpath(root))\n',
     _M + "test_repo_name_is_the_git_toplevel_basename"),

    # --- Review round 2 (T-0075 successor): one per finding, one per
    # neighbouring case. ---
    # B2: delete accepted a config restore refuses.
    ("delete skips the restorable check", MENU,
     '        parsed, held = crew_config_files.read_restorable(path)\n',
     '        parsed, held = {}, open(path, "rb").read()\n',
     _M + "test_delete_refuses_a_config_restore_would_refuse[notjson]"),
    # Re-anchored (round 3): restore reads through `read_restorable` too.
    ("restore accepts what delete refuses", MENU,
     '        return None, crew_config_files.read_restorable(backup)[1]\n',
     '        return None, open(backup, "rb").read()\n',
     _M + "test_delete_and_restore_share_one_predicate"),
    ("restore rewrites the line ending", MENU,
     '            crew_config_files.create_bytes(path, data)\n',
     '            crew_config_files.replace_text(\n'
     '                path, data.decode("utf-8-sig").replace("\\r\\n", "\\n"), b"")\n',
     _M + "test_delete_then_restore_is_byte_identical_with_bom_and_crlf"),
    # B3: a replacement after the backup was deleted unbacked.
    ("delete compares nothing after the rename", MENU,
     '            if got != plan["held"]:\n',
     '            if False:\n',
     _M + "test_delete_refuses_when_the_file_changed_after_the_plan"),
    ("delete copies then removes", MENU,
     '            got = crew_config_files.move_aside(path, backup)\n',
     '            __import__("shutil").copy2(path, backup)\n'
     '            os.remove(path)\n'
     '            got = plan["held"]\n',
     _M + "test_delete_backs_up_by_rename"),
    ("delete takes no lock", MENU,
     '                crew_config_files.Lock(path):\n',
     '                open(os.devnull, encoding="utf-8"):\n',
     _M + "test_delete_refuses_while_the_lock_is_held"),
    # F1: a whole-block value judged by its block path.
    ("machine planner judges the block path, not its leaves", CONFIG,
     '    problems = _leaf_problems(updates, "machine")\n',
     '    problems = [p for d, v in updates.items()\n'
     '                for p in [value_allowed(d, "machine", v)] if p]\n',
     _C + "test_global_writer_judges_each_leaf_of_a_block"
     "[context-value0-context.autoClear.unsafeFocus]"),
    ("repo planner judges the block path", CONFIG,
     '    problems = _leaf_problems(updates, "repo")\n',
     '    problems = [p for d, v in updates.items()\n'
     '                for p in [value_allowed(d, "repo", v)] if p]\n',
     _C + "test_repo_writer_judges_each_leaf_of_a_block"
     "[context-value0-context.autoClear.enabled]"),
    ("leaf expansion stops at one level", CONFIG,
     '            out.extend(leaf_updates(\n'
     '                {f"{dotted}.{key}": inner for key, inner in value.items()}))\n',
     '            out.extend((f"{dotted}.{key}", inner)\n'
     '                       for key, inner in value.items())\n',
     _C + "test_leaf_expansion_is_recursive"),
    # F2: null walked past the enum check.
    ("null skips the enum check", CONFIG,
     '    reason = _layer_path_refusal(dotted, layer, value)\n',
     '    if value is None:\n'
     '        return None\n'
     '    reason = _layer_path_refusal(dotted, layer, value)\n',
     _C + "test_null_is_refused_for_an_enum_key_at_the_machine_layer[pm.authority]"),
    ("machine null given the repo's inherit meaning", CONFIG,
     '    if layer == "repo":\n'
     '        if dotted in REPO_VETO_ONLY:\n',
     '    if True:\n'
     '        if layer == "repo" and dotted in REPO_VETO_ONLY:\n',
     _C + "test_null_is_refused_for_an_enum_key_at_the_machine_layer[pm.authority]"),
    ("repo null refused for a machine-settable enum key", CONFIG,
     '        if is_global_path(dotted):\n'
     '            return "inherits the machine-global value"\n',
     '',
     _C + "test_null_at_the_repo_layer_means_inherit_or_clear"),
    # F3: a later writer merged over an earlier one's key.
    ("repo writer ignores the expected digest", CONFIG,
     '        crew_config_files.update_json(real_path, _mutate, expect=expect)\n',
     '        crew_config_files.update_json(real_path, _mutate, expect=None)\n',
     _C + "test_repo_write_conflict_keeps_the_other_writers_key"),
    ("repo writer takes no lock", FILES,
     '    with Lock(path, wait):\n',
     '    with open(os.devnull, encoding="utf-8"):\n',
     _C + "test_repo_write_refuses_while_the_lock_is_held"),
    ("machine writer ignores the expected digest", CONFIG,
     '        crew_config_files.update_json(real_path, _mutate, expect=expect,\n',
     '        crew_config_files.update_json(real_path, _mutate, expect=None,\n',
     _C + "test_global_write_conflict_and_merge[True]"),
    ("machine writer takes no lock", FILES,
     '    with Lock(path, wait):\n',
     '    with open(os.devnull, encoding="utf-8"):\n',
     _C + "test_global_write_refuses_while_the_lock_is_held"),
    ("update_json compares nothing", FILES,
     '        if expect is not None and expect != current:\n',
     '        if False:\n',
     _F + "test_update_json_refuses_when_the_digest_changed"),
    # F4: choices judged by the value, not the file Save validates.
    ("choices judged by the value alone", MENU,
     _REPO_PLAN, _value_only("repo", "RepoWriteRefused"),
     _M + "test_choices_are_filtered_through_the_merged_file[repo]"),
    ("pending set ignored by spec", MENU,
     '            plan({**pending_layer, dotted: value})\n',
     '            plan({dotted: value})\n',
     _M + "test_pending_set_unblocks_rows"),
    ("machine layer choices judged by the value alone", MENU,
     _GLOBAL_PLAN, _value_only("machine", "GlobalWriteRefused"),
     _M + "test_choices_are_filtered_through_the_merged_file[machine]"),
    # F5: the delete preview omitted what the delete removes.
    ("delete preview walks the defaults, not the file", MENU,
     '    for dotted in known + _file_leaves(parsed, known_set):\n',
     '    for dotted in known:\n',
     _M + "test_delete_preview_lists_every_leaf_of_the_file[x-local]"),
    ("preview drops a nested unknown leaf", MENU,
     '    for dotted in crew_config.leaf_paths(parsed):\n',
     '    for dotted in [k for k in parsed if not isinstance(parsed[k], dict)]:\n',
     _M + "test_delete_preview_lists_every_leaf_of_the_file[foo.bar]"),
    ("platform rows silently skipped", MENU,
     '            if held is not crew_config._MISSING:  # pylint: disable=protected-access\n'
     '                rows.append({"path": dotted, "before": held, "after": held,\n',
     '            if False:\n'
     '                rows.append({"path": dotted, "before": held, "after": held,\n',
     _M + "test_delete_preview_names_platform_as_re_detected"),
    # F6: a malformed CLI shape reached a traceback.
    ("save shape check dropped", MENU,
     '        changes, problem = _json_arg(args.changes, "--changes")\n',
     '        changes, problem = json.loads(args.changes), None\n',
     _M + "test_cli_refuses_malformed_input_with_exit_2[save-machine-1]"),
    ("pending shape check dropped", MENU,
     '            pending, problem = _json_arg(args.pending, "--pending")\n',
     '            pending, problem = json.loads(args.pending), None\n',
     _M + "test_cli_refuses_malformed_input_with_exit_2[spec-pending-1]"),
    # Re-anchored (round 3): the one dotted-path rule is the file layer's.
    ("dotted-path check dropped", FILES,
     '_DOTTED_RE = re.compile(r"^[A-Za-z0-9_-]+(\\.[A-Za-z0-9_-]+)*$")\n',
     '_DOTTED_RE = re.compile(r".*")\n',
     _M + "test_cli_refuses_malformed_input_with_exit_2[save-a..b]"),
    # The restore forms.
    ("PowerShell form double-quoted", MENU,
     '        "powershell": "& " + " ".join("\'" + part.replace("\'", "\'\'") + "\'"\n',
     '        "powershell": "& " + " ".join(\'"\' + part + \'"\'\n',
     _M + "test_restore_command_forms"),
    ("sh form on Windows", MENU,
     '    lines = [f"restore (sh): {forms[\'sh\']}", f"restore (cmd): {forms[\'cmd\']}"]\n',
     '    lines = [f"restore (sh): {forms[\'sh\']}", f"restore (cmd): {forms[\'sh\']}"]\n',
     _M + "test_delete_prints_all_three_restore_lines"),

    # --- Review round 3 (T-0075): one per finding, one per neighbouring
    # case. The gate-record BLOCK has no code path (see the docstring). ---
    # BLOCK: a block value was judged by leaf but assigned whole.
    ("planner assigns the block, not its leaves", CONFIG,
     '    units = assignments(updates)\n',
     '    units = list(updates.items())\n',
     _C + "test_a_repo_block_write_marks_its_leaf_widening"),
    ("assignment keeps blocks whole", CONFIG,
     '                _shape(dotted) == "block" or _is_open_table(dotted)):\n',
     '                _is_open_table(dotted)):\n',
     _C + "test_a_block_write_keeps_its_untouched_siblings[machine]"),
    ("assignment expansion stops at one level", CONFIG,
     '            out.extend(assignments(\n'
     '                {f"{dotted}.{key}": inner for key, inner in value.items()}))\n',
     '            out.extend((f"{dotted}.{key}", inner)\n'
     '                       for key, inner in value.items())\n',
     _C + "test_a_block_write_keeps_its_untouched_siblings[repo]"),
    ("role table assigned whole", CONFIG,
     '                _shape(dotted) == "block" or _is_open_table(dotted)):\n',
     '                _shape(dotted) == "block"):\n',
     _C + "test_a_role_table_write_keeps_the_other_pins[machine]"),
    # FIX: the merged file was judged on enums and providers only.
    ("merged machine file keeps a consent key", CONFIG,
     '    if layer == "machine" and _consent_refusal(dotted):\n',
     '    if False:\n',
     _C + "test_merged_file_refuses_a_pre_existing_leaf_forbidden_at_its_layer"
     "[machine-unsafeFocus]"),
    ("merged repo file keeps an armed veto key", CONFIG,
     '    if layer == "repo" and dotted in REPO_VETO_ONLY and not is_repo_veto(value):\n'
     '        return _VETO_ONLY\n',
     '',
     _C + "test_merged_file_refuses_a_pre_existing_leaf_forbidden_at_its_layer"
     "[repo-armed-autoclear]"),
    ("a repo-only key in the machine file blocks a write", CONFIG,
     '    if shape == "unknown":\n        return None\n'
     '    if layer == "repo" and dotted in REPO_VETO_ONLY',
     '    if shape == "unknown":\n        return None\n'
     '    if layer == "machine" and not is_global_path(dotted):\n'
     '        return "repo-only"\n'
     '    if layer == "repo" and dotted in REPO_VETO_ONLY',
     _C + "test_a_repo_only_key_in_the_machine_file_does_not_block_a_write"),
    # FIX: an absent file had no digest to compare against.
    ("an absent machine file digests as None", CONFIG,
     '            return {}, None, crew_config_files.ABSENT\n',
     '            return {}, None, None\n',
     _M + "test_save_dry_run_names_an_absent_machine_file[machine]"),
    ("update_json cannot compare against absence", FILES,
     '        current = state_digest(raw)\n',
     '        current = None if raw is None else digest(raw)\n',
     _F + "test_update_json_compares_against_absence[absent-as-planned]"),
    ("machine writer not passed the expectation", MENU,
     '                crew_config.write_global_config(machine, global_path,\n'
     '                                                expect=expect.get("machine"))\n',
     '                crew_config.write_global_config(machine, global_path,\n'
     '                                                expect=None)\n',
     _M + "test_save_passes_an_absent_expectation_to_the_machine_writer"),
    ("--expect refuses absent", FILES,
     '    return value == ABSENT or (',
     '    return (',
     _C + "test_set_cli_takes_absent_for_a_first_machine_write"),
    # BLOCK: a repo-only Save did not bind the machine file it judged against.
    ("repo-only save records no machine digest", MENU,
     '        if layer in plans or (plans and layer == "machine"):\n',
     '        if layer in plans:\n',
     _M + "test_repo_only_save_prints_the_machine_digest"),
    ("repo write not bound to the machine digest", MENU,
     '                                              expect_global=bound)\n',
     '                                              expect_global=None)\n',
     _M + "test_repo_only_save_passes_the_machine_digest_to_the_writer"),
    ("repo writer ignores expect_global", CONFIG,
     '        if expect_global is not None and expect_global != machine:\n',
     '        if False:\n',
     _C + "test_repo_write_refuses_when_the_machine_file_changed"),
    ("two-layer save binds the repo to the pre-save machine", MENU,
     '                         else _machine_as_written(global_path, after))\n',
     '                         else expect.get("machine"))\n',
     _M + "test_two_layer_save_binds_the_repo_write_to_the_machine_it_wrote"),
    ("repo plan judged against the pre-save machine", MENU,
     '        view = (after, None)\n',
     '        view = crew_config.machine_view(global_path)\n',
     _M + "test_two_layer_save_judges_the_repo_against_the_saved_machine"),
    ("--set --repo prints no machine digest", CONFIG,
     '        print(f"machine digest: {machine[1]}")\n',
     '        pass\n',
     _C + "test_set_repo_cli_prints_and_takes_the_machine_digest"),
    # BLOCK: the typed confirmation was not bound to the reviewed preview.
    ("delete apply skips the preview digests", MENU,
     '    problem = _unbound(plan, expect)\n',
     '    problem = None\n',
     _M + "test_delete_apply_is_bound_to_the_preview[stale-repo]"),
    ("delete binds the repo digest only", MENU,
     '    for layer, have in (("repo", plan["digest"]), ("machine", plan["machine"])):\n',
     '    for layer, have in (("repo", plan["digest"]),):\n',
     _M + "test_delete_apply_is_bound_to_the_preview[stale-machine]"),
    ("delete apply without digests allowed", MENU,
     '        if expect.get(layer) is None:\n            return (',
     '        if expect.get(layer) is None:\n            continue\n            return (',
     _M + "test_delete_apply_is_bound_to_the_preview[None]"),
    ("delete CLI drops --expect-repo", MENU,
     '                                      "repo": args.expect_repo,\n',
     '                                      "repo": None,\n',
     _M + "test_delete_cli_apply_needs_the_preview_digests"),
    # BLOCK: a destination refusal was check-then-replace.
    ("move checks the destination, then replaces", FILES,
     '        os.link(src, dest, follow_symlinks=False)\n        try:\n',
     '        if os.path.lexists(dest):\n'
     '            raise FileExistsError(dest)\n'
     '        os.replace(src, dest)\n'
     '        return\n'
     '        try:\n',
     _F + "test_move_aside_never_replaces_a_destination_created_after_a_check"),
    ("create_bytes replaces an existing file", FILES,
     '        move_no_clobber(tmp, path)\n',
     '        os.replace(tmp, path)\n',
     _F + "test_create_bytes_never_replaces_an_existing_file"),
    ("move removes a file that replaced the source", FILES,
     '        same = os.path.samestat(os.lstat(parked), os.lstat(dest))\n',
     '        same = True\n',
     _F + "test_move_aside_puts_back_a_file_that_replaced_the_source"),
    # BLOCK: the mismatch rollback checked, then replaced.
    ("rollback overwrites a file saved in the gap", MENU,
     '                    crew_config_files.move_no_clobber(backup, path)\n',
     '                    os.replace(backup, path)\n',
     _M + "test_delete_rollback_never_replaces_a_file_saved_in_the_gap"),
    ("restore replaces a file that appeared after the move-aside", MENU,
     '            crew_config_files.create_bytes(path, data)\n',
     '            crew_config_files.replace_bytes(path, data)\n',
     _M + "test_restore_never_replaces_a_file_that_appears_after_the_move_aside"),
    # BLOCK: delete moved a symlink into a backup restore then refused.
    ("delete follows a symlinked config", MENU,
     '        parsed, held = crew_config_files.read_restorable(path)\n',
     '        parsed, held = crew_config_files.read_strict(path)\n',
     _M + "test_delete_refuses_a_symlinked_config"),
    ("restore follows a symlinked backup", MENU,
     '        return None, crew_config_files.read_restorable(backup)[1]\n',
     '        return None, crew_config_files.read_strict(backup)[1]\n',
     _M + "test_restore_refuses_a_symlinked_backup"),
    ("read_restorable reads a FIFO", FILES,
     '        if not stat.S_ISREG(os.fstat(fd).st_mode):\n',
     '        if False:\n',
     _F + "test_restorable_file_refuses_what_is_not_a_regular_file[fifo]"),
    # FIX: an explicitly empty value skipped validation.
    ("empty --pending skips validation", MENU,
     '        if args.pending is not None:\n',
     '        if args.pending:\n',
     _M + "test_cli_refuses_an_explicitly_empty_value[pending-empty]"),
    ("empty --area skips validation", MENU,
     '        if args.area is not None:\n',
     '        if args.area:\n',
     _M + "test_cli_refuses_an_explicitly_empty_value[area-empty]"),
    # Review round 4, BLOCK 2: a move unlinked a name that may be a foreign
    # file's last.
    ("move unlinks the parked foreign file after putting it back", FILES,
     '    raise Displaced(\n'
     '        f"a file replaced {src} during the move; it is back at {src}, and a "\n',
     '    os.remove(parked)\n'
     '    return\n'
     '    raise Displaced(\n'
     '        f"a file replaced {src} during the move; it is back at {src}, and a "\n',
     _F + "test_move_aside_keeps_a_foreign_file_through_a_second_replacement"),
    ("undo unlinks the backup after the source moved", FILES,
     '        except Displaced:\n'
     '            raise\n'
     '        except BaseException:\n',
     '        except BaseException:\n',
     _F + "test_move_aside_keeps_the_backup_when_the_put_back_fails"),
    ("restore reports a displaced file as a plain refusal", MENU,
     '    except crew_config_files.Displaced as exc:\n'
     '        print(f"{exc}; nothing is lost, check {path}", file=sys.stderr)\n'
     '        return 1\n',
     '',
     _M + "test_restore_reports_a_foreign_file_kept_during_its_move_aside"),
    ("delete's displaced report omits the backup", MENU,
     '        print(f"refused: {exc}; nothing is lost: the original is at {backup}, "\n',
     '        print(f"refused: {exc}; nothing is lost, "\n',
     _M + "test_delete_reports_a_foreign_file_kept_during_the_move"),
    # Review round 4, BLOCK 3: delete checked the machine file outside the
    # locks and took only the repo lock.
    ("delete re-checks nothing inside the locks", MENU,
     '            if now_machine != plan["machine"]:\n',
     '            if False:\n',
     _M + "test_delete_rechecks_the_machine_file_inside_the_locks"),
    ("delete takes only the repo lock", MENU,
     '        with crew_config_files.machine_lock(plan["machinePath"]), \\\n'
     '                crew_config_files.Lock(path):\n',
     '        with crew_config_files.Lock(path):\n',
     _M + "test_delete_refuses_while_the_machine_lock_is_held"),
    ("delete nests the repo lock outside the machine lock", MENU,
     '        with crew_config_files.machine_lock(plan["machinePath"]), \\\n'
     '                crew_config_files.Lock(path):\n',
     '        with crew_config_files.Lock(path), \\\n'
     '                crew_config_files.machine_lock(plan["machinePath"]):\n',
     _M + "test_delete_takes_the_machine_lock_before_the_repo_lock"),
    ("machine lock skipped when its directory is absent", FILES,
     '    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)\n'
     '    return Lock(path, wait)\n',
     '    if not os.path.isdir(os.path.dirname(os.path.abspath(path))):\n'
     '        return open(os.devnull, encoding="utf-8")\n'
     '    return Lock(path, wait)\n',
     _M + "test_delete_takes_the_machine_lock_when_its_directory_is_absent"),
    ("repo writer skips the machine lock", CONFIG,
     '        with crew_config_files.machine_lock(_global_label(global_path)):\n',
     '        with open(os.devnull, encoding="utf-8"):\n',
     _C + "test_repo_write_takes_the_machine_lock_when_its_directory_is_absent"),
    # Review round 4, FIX: a non-list qa.order raised a TypeError.
    ("qa.order shape check dropped (update)", CONFIG,
     '    if order is not None and not isinstance(order, list):\n',
     '    if False:\n',
     _C + "test_qa_order_must_be_a_list[machine-1]"),
    ("qa.order shape check dropped (pre-existing file)", CONFIG,
     '    if order is not None and not isinstance(order, list):\n',
     '    if False:\n',
     _C + "test_a_pre_existing_non_list_qa_order_is_named_not_a_traceback[repo]"),
    ("qa.order shape check dropped (menu)", CONFIG,
     '    if order is not None and not isinstance(order, list):\n',
     '    if False:\n',
     _M + "test_menu_spec_reads_a_non_list_qa_order[repo]"),
    ("qa.order shape check accepts any iterable", CONFIG,
     '    if order is not None and not isinstance(order, list):\n',
     '    if order is not None and not hasattr(order, "__iter__"):\n',
     _C + "test_qa_order_must_be_a_list[repo-codex]"),
    ("qa.order shape check judges only an int", CONFIG,
     '    if order is not None and not isinstance(order, list):\n',
     '    if order is not None and isinstance(order, int):\n',
     _C + "test_qa_order_must_be_a_list[machine-1.5]"),
    # Review round 4, FIX: every platform.* leaf was promised re-detected.
    ("platform prefix marks every leaf re-detected", MENU,
     '        if dotted in redetected:\n',
     '        if dotted.split(".", 1)[0] == "platform":\n',
     _M + "test_delete_preview_platform_rows_follow_the_sync_writer[x-local]"),
    ("re-detected judged by the defaults' platform leaves", MENU,
     '    return frozenset("platform." + key for key in crew_platform.DERIVED_KEYS)\n',
     '    return frozenset(p for p in crew_config.leaf_paths(crew_config.default_config())\n'
     '                     if p.startswith("platform."))\n',
     _M + "test_delete_preview_platform_rows_follow_the_sync_writer[distro]"),
    ("re-detected header promises a value", MENU,
     '        print("re-detected by platform-sync at the next SessionStart (from "\n'
     '              "this machine; a key it finds no value for is left unset):")\n',
     '        print("re-detected by platform-sync at the next SessionStart "\n'
     '              "(written back from this machine, not reset):")\n',
     _M + "test_delete_preview_redetected_header_does_not_promise_a_value"),
    # Review round 5, FIX 1: an object at a leaf, or a path through one, was
    # written at the machine layer and tolerated in either file.
    ("a path under a leaf is accepted", CONFIG,
     '            return "under"\n',
     '            return "unknown"\n',
     _C + "test_a_path_through_a_leaf_is_refused[machine-pm.authority.a]"),
    ("an object at a leaf is accepted", CONFIG,
     '    if shape == "leaf" and isinstance(value, dict):\n'
     '        return f"{dotted} = {value!r} is an object',
     '    if False:\n'
     '        return f"{dotted} = {value!r} is an object',
     _C + "test_an_object_at_a_leaf_is_refused[machine-notify.chatId-{}]"),
    ("a pre-existing object at a leaf is tolerated", CONFIG,
     '    if shape == "under":\n        return f"= {value!r} sits under',
     '    if False:\n        return f"= {value!r} sits under',
     _C + "test_a_pre_existing_object_at_a_leaf_is_named_not_tolerated[machine]"),
    ("an object at a leaf accepted (menu)", CONFIG,
     '            return "under"\n',
     '            return "unknown"\n',
     _M + "test_save_refuses_an_object_at_a_leaf"),
    # Review round 5, FIX 2: a non-object role table or pin was written and
    # then ignored on read, so `qa.roles=1` wiped every pin.
    ("open table shape check dropped", CONFIG,
     '        if table is not None and not isinstance(table, dict):\n',
     '        if False:\n',
     _C + "test_an_open_table_must_be_an_object[repo-qa.roles-1]"),
    ("open table entry shape check dropped", CONFIG,
     '            if pin is not None and not isinstance(pin, dict):\n',
     '            if False:\n',
     _C + "test_an_open_table_must_be_an_object[repo-qa.roles.review-codex]"),
    ("open table shape check accepts any iterable", CONFIG,
     '        if table is not None and not isinstance(table, dict):\n',
     '        if table is not None and not hasattr(table, "__iter__"):\n',
     _C + "test_an_open_table_must_be_an_object[machine-qa.roles-codex]"),
    ("open table shape check dropped (pre-existing file)", CONFIG,
     '        if table is not None and not isinstance(table, dict):\n',
     '        if False:\n',
     _C + "test_a_pre_existing_non_object_in_an_open_table_is_named[machine]"),
    ("open table shape check dropped (menu)", CONFIG,
     '            if pin is not None and not isinstance(pin, dict):\n',
     '            if False:\n',
     _M + "test_menu_spec_reads_a_non_object_open_table[repo]"),
    ("open table wipe reaches the file", CONFIG,
     '        if table is not None and not isinstance(table, dict):\n',
     '        if False:\n',
     _C + "test_a_wiped_pin_table_never_reaches_the_file"),
    # Review round 5, FIX 3: an OS error from a lock or the machine directory
    # escaped both writers as a traceback.
    ("repo writer lets an OS error escape", CONFIG,
     '    except OSError as exc:\n'
     '        raise RepoWriteRefused(f"{crew_config_files.os_error_text(exc)}; nothing written (the machine-global "\n'
     '                               "directory, a lock or the write failed at the OS)") from exc\n',
     '',
     _C + "test_repo_write_refuses_when_the_machine_directory_cannot_be_made[permission]"),
    ("machine writer lets an OS error escape", CONFIG,
     '    except OSError as exc:\n'
     '        raise GlobalWriteRefused(f"{real_path}: {crew_config_files.os_error_text(exc)}; nothing written (its "\n'
     '                                 "directory, its lock or the write itself failed at the OS; check the "\n'
     '                                 "directory)") from exc\n',
     '',
     _C + "test_global_write_refuses_when_its_directory_cannot_be_made[permission]"),
    ("repo writer catches only PermissionError", CONFIG,
     '    except OSError as exc:\n        raise RepoWriteRefused(',
     '    except PermissionError as exc:\n        raise RepoWriteRefused(',
     _C + "test_repo_write_refuses_when_the_machine_directory_cannot_be_made[file]"),
    ("lock file left behind when the PID write fails", FILES,
     '                os.close(fd)\n                try:\n                    os.remove(self.path)\n',
     '                os.close(fd)\n                try:\n                    pass\n',
     _F + "test_lock_removes_its_file_when_the_pid_write_fails"),
    ("a delete-pending lock name refuses instead of waiting", FILES,
     '            except PermissionError as exc:\n',
     '            except PermissionError as exc:\n                raise\n',
     _F + "test_lock_waits_out_a_delete_pending_name_instead_of_failing"),
    ("a lock file never seen present still ends in Busy", FILES,
     '                    seen_held = seen_held or state == _PRESENT\n',
     '                    seen_held = True\n',
     _F + "test_lock_a_stat_that_cannot_tell_waits_then_is_the_real_error"),
    ("a stat error that is not about a lock is waited on", FILES,
     '                if state == _NOT_A_LOCK:\n                    raise\n',
     '',
     _F + "test_lock_a_stat_that_is_not_about_a_lock_raises_at_once"),
    # Round 6 (L-0682): the leaf-shape branches the round-5 entries never reached.
    ("an object at a leaf in the repo file is tolerated", CONFIG,
     '    if shape == "leaf" and isinstance(value, dict):\n'
     '        return f"= {value!r} is an object where a value belongs',
     '    if False:\n'
     '        return f"= {value!r} is an object where a value belongs',
     _C + "test_a_pre_existing_object_at_a_leaf_is_named_not_tolerated[repo]"),
    ("value_allowed lets a path through a leaf be set", CONFIG,
     '    if shape == "under":\n        return f"{dotted} - under a key that takes a value',
     '    if False:\n        return f"{dotted} - under a key that takes a value',
     _C + "test_a_path_through_a_leaf_is_refused[machine-pm.authority.a]"),
    # Round 6 (L-0682): os_error_text at each call site.
    ("the machine writer names an OS error's path repr()'d", CONFIG,
     'raise GlobalWriteRefused(f"{real_path}: {crew_config_files.os_error_text(exc)}; nothing',
     'raise GlobalWriteRefused(f"{real_path}: {exc}; nothing',
     _F + "test_a_refused_machine_write_names_a_backslash_path_as_written"),
    ("the repo writer names an OS error's path repr()'d", CONFIG,
     'raise RepoWriteRefused(f"{crew_config_files.os_error_text(exc)}; nothing written',
     'raise RepoWriteRefused(f"{exc}; nothing written',
     _F + "test_a_refused_repo_write_names_a_backslash_path_as_written"),
    ("the delete handler names an OS error's path repr()'d", MENU,
     "    why = crew_config_files.os_error_text(exc)\n",
     "    why = str(exc)\n",
     _M + "test_a_refused_delete_names_a_backslash_path_as_written"),
    # T-0103: an OS error inside apply_delete names where the file is.
    ("a delete error after the move says left in place again", MENU,
     '    why = crew_config_files.os_error_text(exc)\n    if stage == "before":\n',
     '    why = crew_config_files.os_error_text(exc)\n    if True:\n',
     _M + "test_delete_failure_after_the_move_names_the_backup[fsync]"),
    ("a lock failure before the move says the backup move failed again", MENU,
     '        print(f"refused: {why}; {path} left in place", file=sys.stderr)\n',
     '        print(f"refused: {path} could not be moved to a backup ({why}); "\n'
     '              "left in place", file=sys.stderr)\n',
     _M + "test_delete_lock_failure_is_not_reported_as_a_backup_failure"),
    ("a delete that cannot tell where the file is says left in place", MENU,
     '    print(f"refused: {why}; could not tell where the file is: check {path} "\n'
     '          f"and {backup}", file=sys.stderr)\n    return 1\n',
     '    print(f"refused: {why}; {path} left in place", file=sys.stderr)\n    return 2\n',
     _M + "test_delete_reports_both_paths_when_it_cannot_tell"),
    ("a repo null that widens is described by the written null, not the value in force", CONFIG,
     '                  + widening_note(change["path"], change["inForce"]))\n',
     '                  + widening_note(change["path"], change["after"]))\n',
     _C + "test_a_repo_null_that_widens_is_described_by_the_value_in_force"),
    # C-0028: T-0103's identity checks. A name is trusted as the config only
    # when it IS the config's inode, taken before the move.
    ("a delete error trusts the backup name because something is there", MENU,
     "    at_backup = _same(backup, ident) if moved else (None if moved is None else False)\n",
     "    at_backup = True if moved else (None if moved is None else False)\n",
     _M + "test_delete_backup_name_taken_and_config_gone_is_not_called_the_original"),
    ("a delete error trusts the config path because something is there", MENU,
     "    here = _same(path, ident) if there else (None if there is None else False)\n",
     "    here = True if there else (None if there is None else False)\n",
     _M + "test_delete_replaced_config_and_taken_backup_name_is_not_left_in_place"),
    ("_same calls any file at a name the config's inode", MENU,
     "    return None if now is None else os.path.samestat(now, ident)\n",
     "    return None if now is None else True\n",
     _M + "test_delete_backup_name_taken_before_the_move_is_not_called_the_original"),
    ("a displaced move back says moved back without checking the inode", MENU,
     '            where = ("was moved back there" if _same(path, ident) else\n',
     '            where = ("was moved back there" if True else\n',
     _M + "test_delete_move_back_displaced_by_a_replaced_path_does_not_say_moved_back"),
)

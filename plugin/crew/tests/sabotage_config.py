"""The T-0075 mutations: the config writers in `crew_config.py`, the file
layer in `crew_config_files.py` and the `/crew:config` menu in
`crew_config_menu.py`. Same tuple shape as `sabotage.py`'s MUTATIONS --
(label, target, find, replace, test) -- and appended to it there;
`sabotage.py` sits near `.pylintrc`'s max-module-lines, so this list lives
apart. Run `sabotage.py`, not this file.

Each one is a way the menu could disarm a guard, write before it validated,
merge over another writer, or delete the only copy of a config.

Review round 2's BLOCK 1 (the verify gate's record) has no code path, so it
has no entry here: its proof is the `verify_record.py report` quoted in the
review context.
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
              'snapshot=snap)\n')
_GLOBAL_PLAN = ('            crew_config.plan_global_write(updates, global_path, '
                'snapshot=snap)\n')


def _value_only(layer, error):
    """A planner closure replaced by the per-value rule alone."""
    return ("            for key, val in updates.items():\n"
            f"                if crew_config.value_allowed(key, \"{layer}\", val):\n"
            f"                    raise crew_config.{error}(\n"
            f"                        crew_config.value_allowed(key, \"{layer}\", val))\n")


CONFIG_MENU_MUTATIONS = (
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
    ("repo writer accepts a whole block", CONFIG,
     '    return not (isinstance(node, dict) and node)\n',
     '    return True\n',
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
    ("save writes before validating", MENU,
     '            plans["machine"] = crew_config.plan_global_write(\n'
     '                machine, global_path, snapshot=snap)[1]\n',
     '            plans["machine"] = (crew_config.write_global_config if apply else\n'
     '                                crew_config.plan_global_write)(machine, global_path)[1]\n',
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
     '            return (lambda _d, _v: str(exc)), None, str(exc)\n',
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
     '        if dotted.split(".", 1)[0] == "platform":\n',
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
     '        parsed, held = crew_config_files.read_strict(path)\n',
     '        parsed, held = {}, open(path, "rb").read()\n',
     _M + "test_delete_refuses_a_config_restore_would_refuse[notjson]"),
    ("restore accepts what delete refuses", MENU,
     '    problem = crew_config_files.restorable(data)\n',
     '    problem = None\n',
     _M + "test_delete_and_restore_share_one_predicate"),
    ("restore rewrites the line ending", MENU,
     '            crew_config_files.replace_bytes(path, data)\n',
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
     '        with crew_config_files.Lock(path):\n'
     '            backup = _free_backup(root, now)\n',
     '        with open(os.devnull, encoding="utf-8"):\n'
     '            backup = _free_backup(root, now)\n',
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
    ("dotted-path check dropped", MENU,
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
)

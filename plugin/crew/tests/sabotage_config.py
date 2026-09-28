"""The T-0075 mutations: the repo config writer in `crew_config.py` and the
`/crew:config` menu in `crew_config_menu.py`. Same tuple shape as
`sabotage.py`'s MUTATIONS -- (label, target, find, replace, test) -- and
appended to it there; `sabotage.py` sits near `.pylintrc`'s max-module-lines,
so this list lives apart. Run `sabotage.py`, not this file.

Each one is a way the menu could disarm a guard, write before it validated,
or delete the only copy of a config.
"""
import os

CREW = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(CREW, "hooks", "scripts")
CONFIG = os.path.join(SCRIPTS, "crew_config.py")
MENU = os.path.join(SCRIPTS, "crew_config_menu.py")
_C = "tests/test_crew_config.py::"
_M = "tests/test_config_menu.py::"

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
    ("enum check removed", CONFIG,
     '        if allowed is None or value is None:\n',
     '        if True:\n',
     _C + "test_enum_key_outside_its_values_is_refused"),
    ("repo ratchet widening unmarked", CONFIG,
     '        out["widens"] = rank(now) > rank(was)\n',
     '        out["widens"] = False\n',
     _C + "test_repo_ratchet_widening_is_marked"),
    ("menu offers a refused key", MENU,
     '        if reason is None:\n            row["choices"] = choices(',
     '        if True:\n            row["choices"] = choices(',
     _M + "test_refused_rows_offer_no_choices_and_name_a_reason"),
    ("empty choice list", MENU,
     '        entry["label"] = (f"{label} ({\', \'.join(entry[\'tags\'])})"\n'
     '                          if entry["tags"] else label)\n'
     '    return out\n',
     '        entry["label"] = (f"{label} ({\', \'.join(entry[\'tags\'])})"\n'
     '                          if entry["tags"] else label)\n'
     '    return out if (table or crew_config.enum_values(dotted)\n'
     '                   or dotted in ctx["known"]) else []\n',
     _M + "test_every_writable_setting_offers_a_selectable_value"),
    ("save writes before validating", MENU,
     '            plans["machine"] = crew_config.plan_global_write(machine, global_path)[1]\n',
     '            plans["machine"] = (crew_config.write_global_config if apply else\n'
     '                                crew_config.plan_global_write)(machine, global_path)[1]\n',
     _M + "test_save_validates_both_layers_before_writing_either"),
    ("delete removes before the backup", MENU,
     '    try:\n        _backup(path, backup)\n',
     '    os.remove(path)\n    try:\n        _backup(path, backup)\n',
     _M + "test_delete_writes_backup_first"),
    ("delete ignores confirmation", MENU,
     '    if confirm != name:\n',
     '    if False:\n',
     _M + "test_delete_refuses_without_confirmation"),
    ("delete preview hides the scope guard", CONFIG,
     '    ("scope.mode", "off"): (\n',
     '    ("scope.mode", "never"): (\n',
     _M + "test_delete_preview_names_what_changes"),
    # Review round 1 (T-0075): each fix, reverted.
    ("restore command keeps POSIX quoting on Windows", MENU,
     '    if windows:\n        return " ".join(\'"\' + part',
     '    if False:\n        return " ".join(\'"\' + part',
     _M + "test_windows_restore_command_is_cmd_safe"),
    ("repo veto judged by equality", CONFIG,
     '    return value is False or value is None\n',
     '    return value in (False, None)\n',
     _C + "test_repo_writer_refuses[context.autoClear.enabled-0]"),
    ("menu offers a held 0 as a veto", MENU,
     '            not crew_config.is_repo_veto(value):\n        return False',
     '            value not in (False, None):\n        return False',
     _M + "test_repo_veto_rows_never_offer_a_held_zero"),
    ("repo rows writable over an unreadable config", MENU,
     '            reason = crew_config._repo_refusal(dotted) or unwritable  #',
     '            reason = crew_config._repo_refusal(dotted)  #',
     _M + "test_repo_rows_are_read_only_without_a_readable_config[missing]"),
    ("role row hides the global contribution", MENU,
     '    if from_repo and from_global and isinstance(value, dict):\n'
     '        return "repo+global"\n',
     '',
     _M + "test_role_row_names_both_layers_it_merges"
     "[repo_pin0-global_pin0-repo+global]"),
    ("save lets a write-time refusal escape", MENU,
     '        except (OSError, crew_config.GlobalWriteRefused,\n'
     '                crew_config.RepoWriteRefused, crew_config.ProviderError) as exc:\n',
     '        except OSError as exc:\n',
     _M + "test_save_reports_a_partial_refusal"),
    ("machine menu hides platform and schema", MENU,
     '    if layer == "machine":\n        paths.extend(',
     '    if False:\n        paths.extend(',
     _M + "test_machine_menu_shows_platform_and_schema_read_only"),
    ("delete preview drops a guard the ratchet holds", MENU,
     '            if held is not None:\n',
     '            if False:\n',
     _M + "test_delete_preview_names_a_guard_the_ratchet_holds[allow-True]"),
    ("delete preview resets platform leaves to null", MENU,
     '        if dotted.split(".", 1)[0] == "platform":\n',
     '        if False:\n',
     _M + "test_delete_preview_skips_platform_owned_leaves"),
    ("typed delete name is the root's basename", MENU,
     '    return os.path.basename(top or os.path.realpath(root))\n',
     '    return os.path.basename(os.path.realpath(root))\n',
     _M + "test_repo_name_is_the_git_toplevel_basename"),
)

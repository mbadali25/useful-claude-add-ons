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
)

"""The `guards.enabled` master-switch mutations (crew 1.3.89). Same tuple shape as `sabotage.py`'s
MUTATIONS -- (label, target, find, replace, test) -- appended to it there. Run `sabotage.py`, not this file.

The switch is the one key that turns EVERY guard off, so a slip in it either leaves a guard running that the
owner switched off (the thing it exists for) or, worse, switches the guards off on a value that was never
`false`. Each entry reintroduces one such slip into `crew_hook.py`; every target is a case in
`tests/test_guards_master.py`, and each label says what its mutation trips.
"""
import os

CREW = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOOK = os.path.join(CREW, "hooks", "scripts", "crew_hook.py")
_G = "tests/test_guards_master.py::"

GUARDS_MASTER_MUTATIONS = (
    ("the machine layer's false is not read", HOOK,
     '        if _layer_says_off(os.path.join(home, GLOBAL_CONFIG)):\n',
     '        if False and _layer_says_off(os.path.join(home, GLOBAL_CONFIG)):\n',
     _G + "test_must_allow_with_the_switch_off_in_the_machine_layer[cloud-guard]"),
    ("the string \"false\" switches the guards off", HOOK,
     '    return isinstance(guards, dict) and guards.get("enabled") is False\n',
     '    return isinstance(guards, dict) and guards.get("enabled") in (False, "false")\n',
     _G + "test_only_the_json_literal_false_switches_them_off"),
    ("any falsy value (null, 0) switches the guards off", HOOK,
     '    return isinstance(guards, dict) and guards.get("enabled") is False\n',
     '    return isinstance(guards, dict) and "enabled" in guards and not guards["enabled"]\n',
     _G + "test_only_the_json_literal_false_switches_them_off"),
    ("an unreadable layer reads as off", HOOK,
     '    except (OSError, ValueError):\n        return False\n    guards = parsed.get("guards")',
     '    except (OSError, ValueError):\n        return True\n    guards = parsed.get("guards")',
     _G + "test_only_the_json_literal_false_switches_them_off"),
    ("a failure to look reads as off", HOOK,
     '    except Exception:  # noqa: BLE001  pylint: disable=broad-exception-caught\n        return None\n    return None\n',
     '    except Exception:  # noqa: BLE001  pylint: disable=broad-exception-caught\n        return "repo"\n    return None\n',
     _G + "test_a_lookup_that_raises_leaves_the_guards_on"),
    ("the approval recorder is stood down with the guards", HOOK,
     'GUARDS_KEPT = frozenset({"approval-hook.sh"})\n',
     'GUARDS_KEPT = frozenset()\n',
     _G + "test_the_approval_hook_still_runs_with_the_guards_off"),
    ("a guard row is kept when the switch is off", HOOK,
     '    return [(row, argv) for row, argv in chosen if not row.guard or row.script in GUARDS_KEPT]\n',
     '    return [(row, argv) for row, argv in chosen if not row.guard or row.script in GUARDS_KEPT\n'
     '            or row.script == "scope-guard.sh"]\n',
     _G + "test_must_allow_with_the_switch_off_in_the_machine_layer[scope-guard]"),
    ("the switch is never consulted by dispatch", HOOK,
     '    if chosen and _guards_off(root):\n',
     '    if False and chosen and _guards_off(root):\n',
     _G + "test_must_allow_with_the_switch_off_in_the_machine_layer[env-guard]"),
    ("the Stop guards ignore the switch", HOOK,
     '    return [(row, argv) for row, argv in chosen if not row.guard or row.script in GUARDS_KEPT]\n',
     '    return [(row, argv) for row, argv in chosen if not row.guard or row.script in GUARDS_KEPT\n'
     '            or row.event == "Stop"]\n',
     _G + "test_a_stop_and_a_user_prompt_are_not_refused_by_a_guard_either"),
    ("a dispatcher fault still fails closed with the switch off", HOOK,
     '    if event in BLOCKING_EVENTS and armed(root) and not _guards_off(root):\n',
     '    if event in BLOCKING_EVENTS and armed(root):\n',
     _G + "test_a_dispatcher_fault_does_not_fail_closed_with_the_guards_off"),
    ("the repo layer counts (a repo false stands the guards down)", HOOK,
     '            return "machine"\n    except Exception:  # noqa: BLE001  pylint: disable=broad-exception-caught\n        return None\n    return None\n',
     '            return "machine"\n        if repo_switch_ignored(root):\n            return "repo"\n'
     '    except Exception:  # noqa: BLE001  pylint: disable=broad-exception-caught\n        return None\n    return None\n',
     _G + "test_must_block_when_only_the_repo_layer_says_false[cloud-guard]"),
    ("the repo layer counts when the machine layer is silent or true", HOOK,
     '        if _layer_says_off(os.path.join(home, GLOBAL_CONFIG)):\n',
     '        if _layer_says_off(os.path.join(home, GLOBAL_CONFIG)) or repo_switch_ignored(root):\n',
     _G + "test_must_block_when_the_repo_says_false_and_the_machine_does_not[cloud-guard-machine0]"),
    ("a repo-layer true overrides the machine layer's false", HOOK,
     '        if _layer_says_off(os.path.join(home, GLOBAL_CONFIG)):\n',
     '        if _layer_says_off(os.path.join(home, GLOBAL_CONFIG)) and not os.path.exists(\n'
     '                os.path.join(root or "", ".crew", "config.json")):\n',
     _G + "test_a_true_in_the_repo_layer_cannot_switch_back_on_a_machine_false"),
)

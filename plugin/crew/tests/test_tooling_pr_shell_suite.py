"""`scripts/check-tooling-pr.py` and the shell suite beside the hooks (L-0888).

`plugin/crew/hooks/scripts/_test/**` is ALONGSIDE: run-tests.sh runs the gate in
fixture repos, so a gate change has to be able to move it. MUST-ALLOW: a
harness path with a file under that directory. MUST-BLOCK: a harness path with
a production script beside it, and with a directory whose name only resembles
it.
"""
import importlib.util
import os

import context  # noqa: F401  pylint: disable=unused-import

_CHECKER = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))))), "scripts", "check-tooling-pr.py")
_SPEC = importlib.util.spec_from_file_location("check_tooling_pr_l0888", _CHECKER)
tooling = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(tooling)

_HARNESS = "plugin/crew/hooks/scripts/verify-gate.sh"


def test_judge_a_harness_path_with_the_shell_suite_is_tooling_only():
    code, _ = tooling.judge([_HARNESS, "plugin/crew/hooks/scripts/_test/run-tests.sh"], set())

    assert code == 0


def test_judge_a_harness_path_with_a_production_script_is_feature_work():
    code, lines = tooling.judge([_HARNESS, "plugin/crew/hooks/scripts/crew_tracker.py"], set())

    assert code == 1
    assert "plugin/crew/hooks/scripts/crew_tracker.py" in "\n".join(lines)


def test_judge_a_harness_path_with_a_look_alike_directory_is_feature_work():
    code, _ = tooling.judge([_HARNESS, "plugin/crew/hooks/scripts/_tests/run-tests.sh"], set())

    assert code == 1

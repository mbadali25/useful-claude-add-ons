"""crew-qa-standards' audit: one must-GAP and one must-PASS case per check,
plus the N/A and UNKNOWN cases that keep "could not tell" from reading as a
pass. Every repo here is a throwaway directory under tmp_path."""
import json
import os
import subprocess
import sys

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import qa_audit

_SCRIPT = os.path.join(context._ROOT, "skills", "crew-qa-standards",  # pylint: disable=protected-access
                       "scripts", "qa_audit.py")


def _write(root, rel, text):
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _tests(root, count=250, body="    assert True\n"):
    _write(root, "tests/test_big.py",
           "".join(f"def test_{i}():\n{body}" for i in range(count)))


def _ci(root, *runs):
    _write(root, ".github/workflows/ci.yml",
           "jobs:\n  t:\n    steps:\n    - name: Run pytest\n"
           + "".join(f"      run: {r}\n" for r in runs))


def _status(root, rule):
    return next(r for r in qa_audit.audit(str(root)) if r["rule"] == rule)


# --- H2 parallel runner -----------------------------------------------------------------

def test_h2_a_large_serial_suite_is_a_gap(tmp_path):
    _tests(tmp_path)
    _ci(tmp_path, "pytest tests/ -v")
    row = _status(tmp_path, "H2")
    assert row["status"] == qa_audit.GAP and "250 tests" in row["evidence"]


def test_h2_a_parallel_suite_passes(tmp_path):
    _tests(tmp_path)
    _ci(tmp_path, "pytest tests/ -n auto")
    assert _status(tmp_path, "H2")["status"] == qa_audit.PASS


def test_h2_a_small_serial_suite_is_not_a_gap(tmp_path):
    _tests(tmp_path, count=30)
    _ci(tmp_path, "pytest tests/ -v")
    row = _status(tmp_path, "H2")
    assert row["status"] == qa_audit.PASS and "small enough" in row["evidence"]


def test_h2_a_step_name_mentioning_pytest_is_not_an_invocation(tmp_path):
    _tests(tmp_path)
    _ci(tmp_path, "pytest tests/ -n auto")  # the fixture's "- name: Run pytest" must not count
    assert _status(tmp_path, "H2")["status"] == qa_audit.PASS


def test_h2_a_wrapper_it_cannot_follow_is_unknown_not_pass(tmp_path):
    _tests(tmp_path)
    _ci(tmp_path, "make test")
    assert _status(tmp_path, "H2")["status"] == qa_audit.UNKNOWN


def test_h2_no_ci_is_unknown_and_no_tests_is_na(tmp_path):
    _tests(tmp_path)
    assert _status(tmp_path, "H2")["status"] == qa_audit.UNKNOWN
    empty = tmp_path / "empty"
    empty.mkdir()
    assert _status(empty, "H2")["status"] == qa_audit.NA


def test_h2_a_commented_out_invocation_does_not_count(tmp_path):
    _tests(tmp_path)
    _ci(tmp_path, "make test")
    _write(tmp_path, ".github/workflows/old.yml", "# run: pytest tests/ -n auto\n")
    assert _status(tmp_path, "H2")["status"] == qa_audit.UNKNOWN


# --- H3 wall-clock tests serial --------------------------------------------------------

_BOUNDED = "    elapsed = 1\n    assert elapsed < 10\n"


def test_h3_parallel_with_bounded_tests_and_no_split_is_a_gap(tmp_path):
    _tests(tmp_path, body=_BOUNDED)
    _ci(tmp_path, "pytest tests/ -n auto")
    assert _status(tmp_path, "H3")["status"] == qa_audit.GAP


def test_h3_the_marker_split_passes(tmp_path):
    _tests(tmp_path, body=_BOUNDED)
    _ci(tmp_path, 'pytest tests/ -n auto -m "not wallclock"', "pytest tests/ -m wallclock")
    assert _status(tmp_path, "H3")["status"] == qa_audit.PASS


def test_h3_python_dash_m_pytest_is_not_a_marker_selection(tmp_path):
    """The bug the audit shipped with for one run: `python -m pytest` read as
    `-m pytest`, a marker subset, so a real gap was reported as not judged."""
    _tests(tmp_path, body=_BOUNDED)
    _ci(tmp_path, "python -m pytest tests/ -n auto")
    assert _status(tmp_path, "H3")["status"] == qa_audit.GAP


def test_h3_a_marker_subset_is_named_not_passed_silently(tmp_path):
    _tests(tmp_path, body=_BOUNDED)
    _ci(tmp_path, "pytest tests/ -m slow -n auto")
    row = _status(tmp_path, "H3")
    assert "not judged" in row["evidence"]


def test_h3_no_parallel_run_is_na(tmp_path):
    _tests(tmp_path, body=_BOUNDED)
    _ci(tmp_path, "pytest tests/")
    assert _status(tmp_path, "H3")["status"] == qa_audit.NA


# --- H4 fixture git isolation ----------------------------------------------------------

_COMMITS = 'import subprocess\n\ndef test_c():\n    subprocess.run(["git", "commit", "-m", "x"])\n'


def test_h4_commits_without_pins_are_a_gap(tmp_path):
    _write(tmp_path, "tests/test_c.py", _COMMITS)
    row = _status(tmp_path, "H4")
    assert row["status"] == qa_audit.GAP and "maintenance.auto" in row["evidence"]


def test_h4_signing_pin_alone_still_names_maintenance(tmp_path):
    _write(tmp_path, "tests/test_c.py", _COMMITS)
    _write(tmp_path, "tests/conftest.py", 'PINS = [("commit.gpgsign", "false")]\n')
    row = _status(tmp_path, "H4")
    assert row["status"] == qa_audit.GAP
    assert "maintenance.auto" in row["evidence"] and "commit.gpgsign" not in row["evidence"]


def test_h4_both_pins_in_a_fixture_module_pass(tmp_path):
    _write(tmp_path, "tests/test_c.py", _COMMITS)
    _write(tmp_path, "tests/repo_fixtures.py",
           'PINS = [("commit.gpgsign", "false"), ("maintenance.auto", "false")]\n')
    assert _status(tmp_path, "H4")["status"] == qa_audit.PASS


def test_h4_no_commits_is_na(tmp_path):
    _tests(tmp_path, count=1)
    assert _status(tmp_path, "H4")["status"] == qa_audit.NA


# --- H5 pylint jobs --------------------------------------------------------------------

@pytest.mark.parametrize("run,status", [
    ("pylint $(git ls-files '*.py')", qa_audit.GAP),
    ("pylint -j 0 src/", qa_audit.GAP),
    ("pylint -j \"$(python -c 'import os; print(os.cpu_count() or 1)')\" src/", qa_audit.PASS),
    ("pylint --version", qa_audit.NA),
])
def test_h5_pylint_job_count(tmp_path, run, status):
    _ci(tmp_path, run)
    assert _status(tmp_path, "H5")["status"] == status


# --- H6 / H7 ruff -----------------------------------------------------------------------

def test_h6_no_select_and_unpinned_install_are_both_named(tmp_path):
    _write(tmp_path, "ruff.toml", "line-length = 100\n")
    _ci(tmp_path, "pip install ruff", "ruff check .")
    row = _status(tmp_path, "H6")
    assert row["status"] == qa_audit.GAP
    assert "no `select`" in row["evidence"] and "unpinned" in row["evidence"]


def test_h6_named_rules_and_a_pinned_install_pass(tmp_path):
    _write(tmp_path, "ruff.toml", '[lint]\nselect = ["E", "F"]\n')
    _ci(tmp_path, "pip install 'ruff~=0.16.0'", "ruff check .")
    assert _status(tmp_path, "H6")["status"] == qa_audit.PASS


def test_h6_pyproject_ruff_config_is_read(tmp_path):
    _write(tmp_path, "pyproject.toml", '[tool.ruff.lint]\nselect = ["E"]\n')
    _ci(tmp_path, "ruff check .")
    assert _status(tmp_path, "H6")["status"] == qa_audit.PASS


def test_h7_configured_but_never_run_in_ci_is_a_gap(tmp_path):
    _write(tmp_path, "ruff.toml", '[lint]\nselect = ["E"]\n')
    _ci(tmp_path, "pytest -n auto")
    assert _status(tmp_path, "H7")["status"] == qa_audit.GAP


def test_h7_ruff_version_alone_is_not_running_it(tmp_path):
    _write(tmp_path, "ruff.toml", '[lint]\nselect = ["E"]\n')
    _ci(tmp_path, "ruff --version")
    assert _status(tmp_path, "H7")["status"] == qa_audit.GAP


# --- R9 / R11 -------------------------------------------------------------------------

def test_r9_a_large_claude_md_is_a_gap_and_says_its_size(tmp_path):
    _write(tmp_path, "CLAUDE.md", "x" * (qa_audit.CLAUDE_MD_LIMIT + 1))
    row = _status(tmp_path, "R9")
    assert row["status"] == qa_audit.GAP and str(qa_audit.CLAUDE_MD_LIMIT + 1) in row["evidence"]


def test_r9_a_small_claude_md_passes(tmp_path):
    _write(tmp_path, "CLAUDE.md", "# rules\n")
    assert _status(tmp_path, "R9")["status"] == qa_audit.PASS


def test_r11_ci_without_a_steward_skill_is_a_gap_and_with_one_passes(tmp_path):
    _ci(tmp_path, "true")
    assert _status(tmp_path, "R11")["status"] == qa_audit.GAP
    _write(tmp_path, ".claude/skills/steward/SKILL.md", "---\nname: steward\n---\n")
    assert _status(tmp_path, "R11")["status"] == qa_audit.PASS


# --- the CLI ----------------------------------------------------------------------------

def _cli(root, *args):
    return subprocess.run([sys.executable, _SCRIPT, "--root", str(root), *args],
                          capture_output=True, text=True, check=False)


def test_cli_prints_gaps_first_and_exits_0_without_strict(tmp_path):
    _tests(tmp_path)
    _ci(tmp_path, "pytest tests/")
    run = _cli(tmp_path)
    assert run.returncode == 0, run.stderr
    rows = [l for l in run.stdout.splitlines() if l.startswith("| ") and "Rule" not in l]
    assert rows[0].split("|")[2].strip() == qa_audit.GAP


def test_cli_strict_fails_on_a_gap_or_unknown(tmp_path):
    _tests(tmp_path)
    assert _cli(tmp_path, "--strict").returncode == 1  # no CI: UNKNOWN


def test_cli_json_is_one_row_per_check(tmp_path):
    run = _cli(tmp_path, "--json")
    rows = json.loads(run.stdout)
    assert len(rows) == len(qa_audit.CHECKS)
    assert {r["status"] for r in rows} <= {qa_audit.PASS, qa_audit.GAP, qa_audit.NA,
                                           qa_audit.UNKNOWN}


def test_a_check_that_raises_is_unknown_not_dropped(tmp_path, monkeypatch):
    def broken(*_):
        raise RuntimeError("boom")
    monkeypatch.setattr(qa_audit, "CHECKS", (broken,))
    rows = qa_audit.audit(str(tmp_path))
    assert rows[0]["status"] == qa_audit.UNKNOWN and "boom" in rows[0]["evidence"]

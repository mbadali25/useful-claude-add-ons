"""`crew_setup_status.py`: which `done` setup phases `/crew:init` must re-verify.

Item 13 of the aws-ops follow-up report (T-0500): a `.crew/STATUS.md` written
under crew 0.20 marked all nine phases `done`, so after `/crew:migrate`
`/crew:init` had nothing to resume - 1.0's Phase 6 web-scaffold step was never
offered, and Phase 2 stayed `done` although its own note recorded notify
broken since 2026-08-27 (`notify.provider none`).

Three invariants these tests hold the checker to:

- it writes nothing - measured with a stat snapshot of the fixture around a
  subprocess run of the real script, not assumed;
- an unknown stamp is could-not-tell, never current - a file with no `crew:`
  line flags every `done` row, and a phase heading with no marker is exit 3;
- only `done` rows are flagged - a `partial` row already says it is not done.

Sabotage (`sabotage_setup_status.py`), each entry and the test it reds:
(a) a missing stamp read as the current version ->
    test_no_crew_line_flags_every_done_row_as_could_not_tell;
(b) versions compared as strings -> test_version_compare_is_numeric_not_lexical;
(c) an empty breakage list -> test_done_row_whose_note_records_a_breakage_is_flagged;
(d) a heading without a marker skipped ->
    test_a_phase_heading_without_a_rev_marker_is_could_not_tell_exit_3;
(e) exit 0 whatever was flagged -> test_the_reporters_file_is_flagged_ten_times;
(f) the script appending to STATUS.md -> test_it_writes_nothing.

    python3 -m pytest plugin/crew/tests/test_setup_status.py -q
"""
import json
import os
import re
import shlex
import shutil
import subprocess
import sys

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import crew_setup_status as css

SCRIPT = os.path.join(os.path.dirname(css.__file__), "crew_setup_status.py")
TESTS = os.path.dirname(os.path.abspath(__file__))
CREW = os.path.dirname(TESTS)
PHASES = os.path.join(CREW, "skills", "crew-setup", "phases.md")
PLUGIN_JSON = os.path.join(CREW, ".claude-plugin", "plugin.json")
INIT_MD = os.path.join(CREW, "commands", "init.md")
MIGRATE_MD = os.path.join(CREW, "commands", "migrate.md")
SKILL_MD = os.path.join(CREW, "skills", "crew-setup", "SKILL.md")

NAMES = ("Platform", "Config+context", "Providers+notify", "Smoke harness", "Code map",
         "Verification map", "Browser tests", "First ticket", "Promotion gates")
INITIAL_MARKERS = {0: "1.0.25", 1: "1.0.43", 2: "1.0.25", 3: "1.0.25", 4: "1.0.25",
                   5: "1.0.66", 6: "1.0.25", 7: "1.0.25", 8: "1.0.25"}
BREAKAGE_NOTE = "notify broken since 2026-08-27 (notify.provider none)"


def _read(path):
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def _version():
    return json.loads(_read(PLUGIN_JSON))["version"]


def _status(crew, states, notes=None):
    notes = notes or {}
    head = ["# crew setup status", "repo: fixture", "updated: 2026-08-28"]
    if crew is not None:
        head.append(f"crew: {crew}")
    rows = [f"| {n} | {NAMES[n]} | {state} | {notes.get(n, '')} |" for n, state in enumerate(states)]
    return "\n".join(head + ["", "| # | Phase | State | Notes |", "|---|-------|-------|-------|"]
                     + rows) + "\n"


def _repo(tmp_path, status):
    root = tmp_path / "repo"
    (root / ".crew").mkdir(parents=True)
    if status is not None:
        (root / ".crew" / "STATUS.md").write_text(status, encoding="utf-8")
    return root


def _run(root, *args, script=SCRIPT):
    done = subprocess.run([sys.executable, script, "--root", str(root), *args],
                          capture_output=True, text=True, check=False)
    return done.returncode, done.stdout.splitlines()


def _stat_tree(root):
    out = {}
    for base, dirs, files in os.walk(root):
        for name in dirs + files:
            path = os.path.join(base, name)
            stat = os.lstat(path)
            out[os.path.relpath(path, root)] = (stat.st_mtime_ns, stat.st_size)
    return out


def _phases_copy(tmp_path, edit):
    path = tmp_path / "phases.md"
    path.write_text(edit(_read(PHASES)), encoding="utf-8")
    return str(path)


def _set_marker(n, value):
    def edit(text):
        lines = text.splitlines(keepends=True)
        start = next(i for i, line in enumerate(lines) if line.startswith(f"## Phase {n} "))
        for i in range(start + 1, start + 4):
            if "<!-- phase-rev:" in lines[i]:
                lines[i] = "" if value is None else f"<!-- phase-rev: {value} -->\n"
                return "".join(lines)
        raise AssertionError(f"Phase {n} has no marker to edit")
    return edit


def _rows(lines):
    return [line for line in lines if line.startswith("phase ")]


REPORTER = _status(None, ["done"] * 9, {2: BREAKAGE_NOTE})
CLEAN_NOTES = {n: "checked 2026-09-30" for n in range(9)}


def test_no_status_file_exits_0_and_says_start_at_phase_0(tmp_path):
    code, lines = _run(_repo(tmp_path, None))

    assert code == 0
    assert lines[0] == "setup status: no .crew/STATUS.md - nothing marked; /crew:init starts at Phase 0"
    assert lines[-1].startswith("current crew: 1.0.") and "write `crew: " in lines[-1]


def test_stamped_current_file_with_clean_notes_flags_nothing(tmp_path):
    ver = _version()
    root = _repo(tmp_path, _status(ver, ["done"] * 9, CLEAN_NOTES))

    code, lines = _run(root)

    assert code == 0
    assert lines == [f"setup status  .crew/STATUS.md  marked against crew {ver}",
                     "re-verify: none",
                     f"current crew: {ver} - write `crew: {ver}` when rewriting .crew/STATUS.md"]


def test_done_row_marked_before_its_phase_rev_is_flagged(tmp_path):
    root = _repo(tmp_path, _status("1.0.30", ["done"] * 9, CLEAN_NOTES))

    code, lines = _run(root)

    assert code == 1
    assert _rows(lines) == [
        "phase 1  Config+context  done  definition changed since marked (marked 1.0.30 < phase-rev 1.0.43)"
        " - re-verify",
        "phase 5  Verification map  done  definition changed since marked (marked 1.0.30 < phase-rev 1.0.66)"
        " - re-verify",
    ]
    assert "re-verify: phases 1, 5" in lines


def test_version_compare_is_numeric_not_lexical(tmp_path):
    older = _phases_copy(tmp_path, _set_marker(0, "1.0.10"))
    root = _repo(tmp_path, _status("1.0.9", ["done"] + ["todo"] * 8, CLEAN_NOTES))

    _, flagged = _run(root, "--phases", older)

    (tmp_path / "newer").mkdir()
    newer = _phases_copy(tmp_path / "newer", _set_marker(0, "1.0.9"))
    (root / ".crew" / "STATUS.md").write_text(_status("1.0.10", ["done"] + ["todo"] * 8, CLEAN_NOTES),
                                              encoding="utf-8")
    code, clean = _run(root, "--phases", newer)

    assert _rows(flagged) == ["phase 0  Platform  done  definition changed since marked "
                              "(marked 1.0.9 < phase-rev 1.0.10) - re-verify"]
    assert (code, _rows(clean)) == (0, [])


def test_no_crew_line_flags_every_done_row_as_could_not_tell(tmp_path):
    root = _repo(tmp_path, _status(None, ["done"] * 9, CLEAN_NOTES))
    partial = _repo(tmp_path / "p", _status(None, ["done"] * 4 + ["todo"] * 5, CLEAN_NOTES))

    code, lines = _run(root)
    _, four = _run(partial)

    assert code == 1
    assert lines[0] == "setup status  .crew/STATUS.md  no crew: line - could not tell when any row was marked"
    assert _rows(lines) == [f"phase {n}  {NAMES[n]}  done  could not tell when marked (no crew: line) - re-verify"
                            for n in range(9)]
    assert len(_rows(four)) == 4


@pytest.mark.parametrize("word", ["broken", "failing", "not working", "provider none", "unreachable",
                                  "never arrived", "timed out", "no longer"])
def test_done_row_whose_note_records_a_breakage_is_flagged(tmp_path, word):
    ver = _version()
    note = f"telegram {word.upper()} since tuesday"
    root = _repo(tmp_path, _status(ver, ["done"] * 9, {**CLEAN_NOTES, 2: note}))

    code, lines = _run(root)

    assert code == 1
    assert _rows(lines) == [f'phase 2  Providers+notify  done  note may record a breakage ("{note}") - re-verify']


def test_breakage_check_looks_only_at_done_rows(tmp_path):
    states = ["done"] * 9
    states[2] = "partial"
    root = _repo(tmp_path, _status(_version(), states, {**CLEAN_NOTES, 2: BREAKAGE_NOTE}))

    code, lines = _run(root)

    assert (code, _rows(lines)) == (0, [])


def test_the_reporters_file_is_flagged_ten_times(tmp_path):
    code, lines = _run(_repo(tmp_path, REPORTER))

    rows = _rows(lines)
    assert code == 1
    assert len(rows) == 10
    assert [row for row in rows if row.startswith("phase 2  ")] == [
        "phase 2  Providers+notify  done  could not tell when marked (no crew: line) - re-verify",
        f'phase 2  Providers+notify  done  note may record a breakage ("{BREAKAGE_NOTE}") - re-verify',
    ]
    assert "re-verify: phases 0, 1, 2, 3, 4, 5, 6, 7, 8" in lines


def test_a_phase_heading_without_a_rev_marker_is_could_not_tell_exit_3(tmp_path):
    phases = _phases_copy(tmp_path, _set_marker(4, None))

    code, lines = _run(_repo(tmp_path, REPORTER), "--phases", phases)

    assert code == 3
    assert len(lines) == 1
    assert lines[0].startswith('setup status: could not tell - phases.md: "## Phase 4')
    assert "has no <!-- phase-rev: X.Y.Z --> within 3 lines" in lines[0]


def test_a_status_file_without_a_table_is_could_not_tell_exit_3(tmp_path):
    root = _repo(tmp_path, "# crew setup status\nrepo: fixture\n")

    code, lines = _run(root)

    assert code == 3
    assert lines[0].startswith("setup status: could not tell - .crew/STATUS.md: no | # | Phase | State | Notes | table")


def test_an_unknown_state_is_could_not_tell_exit_3(tmp_path):
    root = _repo(tmp_path, _status(_version(), ["finished"] + ["done"] * 8))

    code, lines = _run(root)

    assert code == 3
    assert lines == ['setup status: could not tell - .crew/STATUS.md: row 0 state "finished" is not one of '
                     'todo, in progress, partial, blocked, done, n/a']


def test_current_crew_is_could_not_tell_when_plugin_json_is_unreadable(tmp_path):
    missing = str(tmp_path / "absent" / "plugin.json")

    code, lines = _run(_repo(tmp_path, REPORTER), "--plugin-json", missing)

    assert code == 1
    assert lines[-1] == (f"current crew: could not tell (plugin.json unreadable at {missing})"
                         " - write the installed crew version as crew: <version>")


def test_it_writes_nothing(tmp_path):
    root = _repo(tmp_path, REPORTER)
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    copy = str(scripts / "crew_setup_status.py")
    shutil.copy(SCRIPT, copy)
    before = _stat_tree(root)

    code, _ = _run(root, "--phases", PHASES, "--plugin-json", PLUGIN_JSON, script=copy)

    assert (code, _stat_tree(root)) == (1, before)
    assert sorted(os.listdir(scripts)) == ["crew_setup_status.py"]


def test_every_phase_section_carries_one_parsable_rev_marker_not_past_the_plugin_version():
    revs = css.phase_revs(PHASES)
    plugin = css._vtuple(_version())  # pylint: disable=protected-access

    assert sorted(revs) == list(range(9))
    for value in revs.values():
        parsed = css._vtuple(value)  # pylint: disable=protected-access
        assert parsed is not None and (1, 0, 25) <= parsed <= plugin, value


def test_initial_markers_match_the_spec():
    assert css.phase_revs(PHASES) == INITIAL_MARKERS


def test_status_format_in_phases_md_carries_the_crew_line():
    text = _read(PHASES)
    block = text.split("After every phase, rewrite `.crew/STATUS.md`:", 1)[1].split("```", 2)[1]
    lines = block.splitlines()
    repo = next(i for i, line in enumerate(lines) if line.startswith("repo:"))
    table = next(i for i, line in enumerate(lines) if line.startswith("| # |"))

    assert any(re.match(r"^crew: \d+\.\d+\.\d+$", line) for line in lines[repo:table])


def _fenced_commands(text):
    """Every line inside a ```bash fence, in document order."""
    out, inside = [], False
    for line in text.splitlines():
        if line.startswith("```"):
            inside = line.strip() == "```bash" if not inside else False
            continue
        if inside and line.strip():
            out.append(line.strip())
    return out


def _checker_calls(path):
    return [c for c in _fenced_commands(_read(path)) if "crew_setup_status.py" in c]


def test_init_migrate_skill_and_phases_name_the_checker():
    init = _read(INIT_MD)
    migrate = _read(MIGRATE_MD)
    how = _read(PHASES).split("## How this works", 1)[1].split("\n---\n", 1)[0]
    after = migrate.split("## After", 1)[1]

    assert len(_checker_calls(INIT_MD)) == 1
    for phrase in ("--status", "before choosing where to resume", "re-verify", "crew:"):
        assert phrase in init, phrase
    assert len(_checker_calls(MIGRATE_MD)) == 1
    assert "crew_setup_status.py" in migrate.split("## Step 2", 1)[0]
    assert "/crew:init" in after and "could not tell" in after
    assert "a `done` row whose note records a breakage is not `done`" in how
    assert "crew_setup_status.py" in how
    assert "crew_setup_status.py" in _read(SKILL_MD)


@pytest.mark.parametrize("path", [INIT_MD, MIGRATE_MD], ids=["init", "migrate"])
def test_fenced_checker_commands_in_init_and_migrate_run(tmp_path, path):
    root = _repo(tmp_path, REPORTER)
    (command,) = _checker_calls(path)
    argv = shlex.split(command.replace("${CLAUDE_PLUGIN_ROOT}", CREW))
    assert argv[0] == "python3"

    done = subprocess.run([sys.executable, *argv[1:]], cwd=str(root), capture_output=True, text=True,
                          check=False)

    assert done.returncode == 1, done.stdout + done.stderr
    assert len(_rows(done.stdout.splitlines())) == 10

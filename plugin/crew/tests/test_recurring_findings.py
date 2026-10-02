"""The recurring-findings checklist (L-0575): curated, tracked, keyed by path
globs, printed for the implementer from the spec's Touch list and for the
reviewer from the bundle's changed files. Every way the data or the scope
can be unknown is stated, never turned into an empty list."""
import os
import re
import subprocess
import sys

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import recurring_findings as rf

SCRIPT = os.path.join(os.path.dirname(os.path.abspath(rf.__file__)), "recurring_findings.py")
EMPTY = {"committed_files": [], "staged_files": [], "unstaged_files": [], "untracked_files": []}
NONE_KEYED = "No recurring-finding class is keyed to these paths."


def _manifest(*files):
    return dict(EMPTY, committed_files=list(files))


def _ids(lines):
    return [line.split(" ", 1)[0] for line in lines if line.startswith("RF-")]


def _section(sid, globs='["**/*.py"]', probes=1, seen="seen: 3 of 9"):
    body = "".join(f"- probe {sid} {n}\n" for n in range(probes))
    return f"## {sid} Title {sid}\napplies-to: {globs}\n{seen}\n{body}\n"


def _data(tmp_path, text, name="data.md"):
    path = tmp_path / name
    path.write_text(text, encoding="utf-8", newline="\n")
    return str(path)


def _spec(root, ticket, touch_lines):
    folder = root / ".work" / "tickets" / ticket
    folder.mkdir(parents=True)
    (folder / "spec.md").write_text(
        "# T\n\n## Intent\nx\n\n## Touch\n" + "".join(f"{line}\n" for line in touch_lines),
        encoding="utf-8")


def _cli(*args):
    return subprocess.run([sys.executable, SCRIPT, *args], capture_output=True, text=True,
                          check=False, timeout=60, stdin=subprocess.DEVNULL)


# ---- the shipped data -------------------------------------------------------------

def test_shipped_checklist_parses_and_fits():
    entries, problems = rf.parse(rf.data_path())
    lines = rf.render(rf.REVIEW_HEADER, entries)
    text = "\n".join(lines)

    with open(rf.data_path(), encoding="utf-8") as fh:
        headed = re.findall(r"^## (RF-\d{2}) ", fh.read(), re.M)

    assert problems == []
    assert [e["id"] for e in entries] == headed
    assert len(entries) >= 5
    assert all(1 <= len(e["probes"]) <= rf.MAX_PROBES and e["seen"] and e["applies_to"]
               for e in entries)
    assert _ids(lines) == [e["id"] for e in entries]
    assert all(probe in text for e in entries for probe in e["probes"])
    assert "TRUNCATED" not in text
    assert len(lines) <= rf.MAX_LINES


def test_shipped_checklist_covers_the_five_target_classes():
    titles = " ".join(e["title"].lower() for e in rf.parse(rf.data_path())[0])

    for word in ("unknown", "test", "says", "powershell", "version"):
        assert word in titles, word


# ---- path scoping -----------------------------------------------------------------

@pytest.mark.parametrize("path,expected", [
    ("plugin/crew/hooks/scripts/verify-gate.ps1", True),
    ("scripts/install-prerequisites.sh", True),
    ("plugin\\crew\\hooks\\scripts\\verify-gate.ps1", True),
    ("plugin/crew/README.md", False),
    ("plugin/crew/hooks/scripts/review_prompt.py", False),
])
def test_select_parity_entry_by_changed_path(path, expected):
    entries = rf.parse(rf.data_path())[0]
    parity = [e for e in entries if "powershell" in e["title"].lower()]

    assert len(parity) == 1
    assert (parity[0] in rf.select(entries, [path])) is expected


@pytest.mark.parametrize("touch,glob,expected", [
    ("plugin/crew/hooks/scripts/*.py", "**/*.py", True),
    ("plugin/crew/hooks/scripts/*.py", "**/*.ps1", False),
    ("docs/guides/crew/**", "**/*.md", True),
    ("plugin/crew/docs", "**/*.md", True),
    ("plugin/crew/README.md", "**/*.py", False),
    ("plugin/crew/hooks/scripts/role-write-guard.ps1", "**/*guard*", True),
    ("plugin/crew/hooks/scripts/crew_state.py", "**/*guard*", False),
    ("CHANGELOG.md", "plugin/**", False),
])
def test_select_by_touch_entry(touch, glob, expected):
    assert rf.matches(touch, glob, touch=True) is expected


def test_select_keeps_file_order_and_drops_unkeyed(tmp_path):
    data = _data(tmp_path, _section("RF-01", '["**/*.ps1"]') + _section("RF-02")
                 + _section("RF-03", '["**/*.md"]'))
    entries, _ = rf.parse(data)

    assert [e["id"] for e in rf.select(entries, ["a/b.md", "x.py"])] == ["RF-02", "RF-03"]


# ---- the data can be unknown -------------------------------------------------------

@pytest.mark.parametrize("text,expect", [
    ("## RF-1 bad id\n", "is not '## RF-NN <title>'"),
    (_section("RF-01", globs="**/*.py"), "applies-to is not a JSON list"),
    (_section("RF-01", globs="[]"), "applies-to is not a JSON list"),
    (_section("RF-01", seen=""), "no seen line"),
    ("## RF-01 t\napplies-to: [\"**\"]\nseen: x\n", "0 probes"),
    (_section("RF-01", probes=5), "5 probes"),
    (_section("RF-01") + _section("RF-01"), "RF-01 is defined twice"),
    (_section("RF-01").replace("applies-to", "Applies-to"), "is not applies-to, seen or a"),
    (_section("RF-01").replace("- probe", "* probe"), "is not applies-to, seen or a"),
    (_section("RF-01") .replace("seen: 3 of 9", "seen: 3\nseen: 4"), "repeats seen"),
])
def test_data_problem_is_named_and_never_reads_as_no_match(tmp_path, text, expect):
    data = _data(tmp_path, text + _section("RF-09", '["**/*.md"]'))
    entries, problems = rf.parse(data)
    lines = rf.review_block(str(tmp_path), _manifest("a.py"), data=data)

    assert any(expect in p for p in problems), problems
    assert any(line.startswith(("PROBLEM:", "UNREADABLE:")) for line in lines)
    assert "RF-09" in [e["id"] for e in entries]
    assert NONE_KEYED not in lines


@pytest.mark.parametrize("make", ["missing", "undecodable"])
def test_data_unreadable_file(tmp_path, make):
    path = tmp_path / "data.md"
    if make == "undecodable":
        path.write_bytes(b"## RF-01 \xff\xfe\n")
    lines = rf.review_block(str(tmp_path), _manifest("a.py"), data=str(path))

    assert lines[len(rf.REVIEW_HEADER)].startswith("UNREADABLE:")
    assert NONE_KEYED not in lines
    assert any("class could be read" in line for line in lines)


@pytest.mark.parametrize("text", ["", "# Intro\n\nprose only\n", "## Provenance\nx\n"])
def test_data_without_a_section_is_a_problem(tmp_path, text):
    data = _data(tmp_path, text)
    entries, problems = rf.parse(data)
    lines = rf.review_block(str(tmp_path), _manifest("a.py"), data=data)

    assert entries == []
    assert any("no valid '## RF-NN' section" in p for p in problems)
    assert NONE_KEYED not in lines


def test_data_problem_makes_the_cli_exit_1(tmp_path):
    data = _data(tmp_path, _section("RF-01", probes=5))
    result = _cli("--root", str(tmp_path), "--paths", "a.py", "--data", data)

    assert result.returncode == 1
    assert "PROBLEM:" in result.stdout


# ---- the scope can be unknown ------------------------------------------------------

@pytest.mark.parametrize("touch_lines", [
    None,
    [],
    ["- `plugin/a.md`", "- not one path but several words"],
])
def test_scope_unknown_touch_lists_every_section(tmp_path, touch_lines):
    data = _data(tmp_path, _section("RF-01", '["**/*.ps1"]') + _section("RF-02", '["**/*.md"]'))
    if touch_lines is not None:
        _spec(tmp_path, "L-0001", touch_lines)
    lines, complete = rf.implementer_block(str(tmp_path), "L-0001", data=data)

    assert complete is False
    assert any(line.startswith("UNKNOWN:") for line in lines)
    assert _ids(lines) == ["RF-01", "RF-02"]


@pytest.mark.parametrize("manifest", [
    {},
    dict(EMPTY, staged_files=None),
    dict(EMPTY, committed_files=["a.md", 7]),
    dict(EMPTY, committed_files=["a.md", "  "]),
    "not a mapping",
])
def test_scope_unknown_manifest_lists_every_section(tmp_path, manifest):
    data = _data(tmp_path, _section("RF-01", '["**/*.ps1"]') + _section("RF-02", '["**/*.md"]'))
    lines = rf.review_block(str(tmp_path), manifest, data=data)

    assert any(line.startswith("UNKNOWN:") for line in lines)
    assert _ids(lines) == ["RF-01", "RF-02"]


def test_known_empty_match_says_so(tmp_path):
    data = _data(tmp_path, _section("RF-01", '["**/*.ps1"]'))
    lines = rf.review_block(str(tmp_path), _manifest("a.md"), data=data)

    assert lines[len(rf.REVIEW_HEADER):] == [NONE_KEYED]


# ---- the cap -----------------------------------------------------------------------

def test_cap_drops_whole_entries_and_says_which(tmp_path):
    data = _data(tmp_path, "".join(_section(f"RF-{n:02d}", probes=4) for n in range(1, 21)))
    entries, _ = rf.parse(data)
    lines = rf.render(rf.REVIEW_HEADER, entries)
    shown = _ids(lines)
    cut = lines[-1]

    assert len(lines) <= rf.MAX_LINES
    assert shown == [f"RF-{n:02d}" for n in range(1, len(shown) + 1)]
    assert cut.startswith(f"[TRUNCATED at {rf.MAX_LINES} lines: ")
    assert all(f"RF-{n:02d}" in cut for n in range(len(shown) + 1, 21))
    assert lines[-2].startswith("  - ")


# ---- the two readers ---------------------------------------------------------------

def test_review_block_is_scoped_to_the_manifest(tmp_path):
    data = _data(tmp_path, _section("RF-01", '["**/*.ps1"]') + _section("RF-02", '["**/*.md"]'))
    lines = rf.review_block(str(tmp_path), dict(EMPTY, untracked_files=["x/y.ps1"]), data=data)

    assert lines[:len(rf.REVIEW_HEADER)] == list(rf.REVIEW_HEADER)
    assert _ids(lines) == ["RF-01"]
    assert "does not bound the review" in "\n".join(lines)


def test_implementer_block_unions_touch_and_paths(tmp_path):
    data = _data(tmp_path, _section("RF-01", '["**/*.ps1"]') + _section("RF-02", '["**/*.md"]')
                 + _section("RF-03", '["**/*.py"]'))
    _spec(tmp_path, "L-0001", ["- `plugin/x/*.ps1`"])
    lines, complete = rf.implementer_block(str(tmp_path), "L-0001", ["docs/a.md"], data=data)

    assert complete is True
    assert _ids(lines) == ["RF-01", "RF-02"]


def test_cli_ticket_prints_the_block_and_exits_0(tmp_path):
    _spec(tmp_path, "L-0001", ["- `plugin/crew/hooks/scripts/verify-gate.ps1`"])
    result = _cli("--root", str(tmp_path), "--ticket", "L-0001")

    assert result.returncode == 0, result.stderr
    assert "PowerShell" in result.stdout


def test_cli_without_ticket_or_paths_is_usage():
    assert _cli().returncode == 2


def test_cli_unknown_scope_exits_1(tmp_path):
    result = _cli("--root", str(tmp_path), "--ticket", "L-0001")

    assert result.returncode == 1
    assert "UNKNOWN:" in result.stdout


def test_data_comes_from_the_plugin_not_the_root(tmp_path):
    consumer = tmp_path / "consumer"
    consumer.mkdir()
    subprocess.run(["git", "init", "-q", str(consumer)], check=True, timeout=60,
                   stdin=subprocess.DEVNULL)
    shipped = [e["id"] for e in rf.parse(rf.data_path())[0]]
    result = _cli("--root", str(consumer), "--paths", "src/a.py", "src/b.ps1", "src/c.md")
    lines = rf.review_block(str(consumer), _manifest("src/a.py", "src/b.ps1", "src/c.md"))

    assert result.returncode == 0, result.stdout + result.stderr
    assert _ids(result.stdout.splitlines()) and set(_ids(result.stdout.splitlines())) <= set(shipped)
    assert _ids(lines) == _ids(result.stdout.splitlines())

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
REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, os.pardir, os.pardir))


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


def _cli(*args, timeout=60):
    return subprocess.run([sys.executable, SCRIPT, *args], capture_output=True, text=True,
                          check=False, timeout=timeout, stdin=subprocess.DEVNULL)


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


SEVEN_CLASSES = (("RF-01", "race"), ("RF-02", "not true"), ("RF-03", "test"),
                 ("RF-04", "unknown"), ("RF-05", "powershell"), ("RF-06", "guard"),
                 ("RF-07", "version"))


def test_shipped_checklist_pins_the_seven_classes():
    """L-0592 (L-0575 round 2): every curated class is pinned by id and by its
    keyword, so deleting or renaming any one of them goes red."""
    entries = rf.parse(rf.data_path())[0]

    assert [e["id"] for e in entries] == [sid for sid, _ in SEVEN_CLASSES]
    assert all(word in e["title"].lower() for e, (_, word) in zip(entries, SEVEN_CLASSES)), \
        [e["title"] for e in entries]


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
    ("docs/v1.0", "docs/v1.0/**/*.md", True),
    ("src/[ab].py", "src/[bc].py", True),
    ("src/[ab].py", "src/*.ps1", False),
    ("plugin/crew/hooks/scripts/role-write-guard.ps1", "**/*guard*", True),
    ("plugin/crew/hooks/scripts/crew_state.py", "**/*guard*", False),
    ("CHANGELOG.md", "plugin/**", False),
])
def test_select_by_touch_entry(touch, glob, expected):
    assert rf.matches(touch, glob, touch=True, root=REPO) is expected


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
    (_section("RF-01").replace("- probe RF-01 0", "- "), "an empty probe"),
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


def test_cap_holds_when_notes_alone_would_overflow(tmp_path):
    data = _data(tmp_path, _section("RF-01", probes=4))
    entries, _ = rf.parse(data)
    notes = [f"PROBLEM: x{n}" for n in range(70)]
    empty = rf.render(["header"], [], notes)
    full = rf.render(["header"], entries, notes)

    assert len(empty) <= rf.MAX_LINES and len(full) <= rf.MAX_LINES
    assert any("more notes not shown" in line for line in empty)
    assert full[-1].startswith("[TRUNCATED") and "RF-01" in full[-1]


def test_shipped_sections_are_ranked_by_their_count():
    counts = [int(re.search(r"about (\d+) of", e["seen"]).group(1))
              for e in rf.parse(rf.data_path())[0]]

    assert counts == sorted(counts, reverse=True)


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


# ---- L-0592: the L-0575 round-2 fixes ----------------------------------------------

SCRIPTS = os.path.dirname(os.path.abspath(rf.__file__))
NEEDS_FIFO = pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="os.mkfifo is absent here")
NEEDS_DEVICE = pytest.mark.skipif(os.name == "nt", reason="no POSIX character device to link to")
NON_REGULAR = [pytest.param("fifo", marks=NEEDS_FIFO),
               pytest.param("symlink-to-fifo", marks=NEEDS_FIFO),
               "directory",
               pytest.param("symlink-to-device", marks=NEEDS_DEVICE)]
# os.open of a directory raises PermissionError on Windows before any fstat, so
# there only "cannot be read" is asserted for that one kind.
WINDOWS_DIRECTORY = os.name == "nt"


def _non_regular(folder, kind, name):
    target = folder / name
    if kind == "fifo":
        os.mkfifo(target)
    elif kind == "symlink-to-fifo":
        os.mkfifo(folder / f"{name}.fifo")
        os.symlink(folder / f"{name}.fifo", target)
    elif kind == "directory":
        target.mkdir()
    else:
        os.symlink(os.devnull, target)
    return target


def _says_not_regular(line, kind):
    return (WINDOWS_DIRECTORY and kind == "directory") or "not a regular file" in line


@pytest.mark.parametrize("kind", NON_REGULAR)
def test_scope_unknown_spec_not_a_regular_file(tmp_path, kind):
    """A spec.md that is a FIFO used to hang the implementer in open(). Now it
    is a scope UNKNOWN that names why, within a bound, and lists every class."""
    folder = tmp_path / ".work" / "tickets" / "L-0001"
    folder.mkdir(parents=True)
    _non_regular(folder, kind, "spec.md")
    shipped = [e["id"] for e in rf.parse(rf.data_path())[0]]
    result = _cli("--root", str(tmp_path), "--ticket", "L-0001", timeout=20)
    unknown = [line for line in result.stdout.splitlines() if line.startswith("UNKNOWN:")]

    assert result.returncode == 1, result.stdout + result.stderr
    assert len(unknown) == 1 and "cannot be read" in unknown[0], unknown
    assert _says_not_regular(unknown[0], kind), unknown
    assert _ids(result.stdout.splitlines()) == shipped


@pytest.mark.parametrize("kind", NON_REGULAR)
def test_data_not_a_regular_file(tmp_path, kind):
    data = _non_regular(tmp_path, kind, "data.md")
    result = _cli("--root", str(tmp_path), "--paths", "a.py", "--data", str(data), timeout=20)
    unreadable = [line for line in result.stdout.splitlines() if line.startswith("UNREADABLE:")]

    assert result.returncode == 1, result.stdout + result.stderr
    assert len(unreadable) == 1 and _says_not_regular(unreadable[0], kind), result.stdout
    assert NONE_KEYED not in result.stdout


@pytest.mark.parametrize("kind", NON_REGULAR)
def test_read_regular_never_opens_a_non_regular_file(tmp_path, kind, monkeypatch):
    """Layer 1: the type is checked by path before anything is opened, so a
    device that blocks on open is never reached."""
    target = _non_regular(tmp_path, kind, "x.md")

    def no_open(*_args, **_kwargs):
        raise AssertionError(f"os.open was called for a {kind}")

    monkeypatch.setattr(rf.os, "open", no_open)
    with pytest.raises(OSError, match="not a regular file"):
        rf._read_regular(str(target))  # pylint: disable=protected-access


SWAP = r"""
import os, sys
sys.path.insert(0, sys.argv[1])
import recurring_findings as rf
fifo, regular = sys.argv[2], os.stat(sys.argv[3])
real_stat = os.stat
def swapped(path, *args, **kwargs):
    return regular if os.fspath(path) == fifo else real_stat(path, *args, **kwargs)
os.stat = swapped
try:
    text = rf._read_regular(fifo)
except OSError as exc:
    print("REFUSED", exc)
    sys.exit(0)
print("READ", repr(text))
sys.exit(3)
"""


@NEEDS_FIFO
def test_read_regular_refuses_a_fifo_swapped_in_after_stat(tmp_path):
    """Layer 2: a FIFO swapped in between the stat and the open (simulated by
    a stat that reports a regular file) is opened non-blocking and refused by
    fstat. In a child process with a bound: a blocking open is a timeout."""
    fifo = tmp_path / "swap.md"
    os.mkfifo(fifo)
    regular = tmp_path / "regular.md"
    regular.write_text("x", encoding="utf-8")
    result = subprocess.run([sys.executable, "-c", SWAP, SCRIPTS, str(fifo), str(regular)],
                            capture_output=True, text=True, check=False, timeout=20,
                            stdin=subprocess.DEVNULL)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "not a regular file" in result.stdout


def test_select_touch_file_does_not_cover_descendants(tmp_path):
    (tmp_path / "plugin" / "crew" / "docs").mkdir(parents=True)
    (tmp_path / "plugin" / "crew" / "README.md").write_text("x", encoding="utf-8")
    data = _data(tmp_path, _section("RF-01", '["plugin/crew/README.md/*.py"]')
                 + _section("RF-02", '["plugin/crew/docs/*.py"]')
                 + _section("RF-03", '["plugin/crew/new/*.py"]'))
    entries, _ = rf.parse(data)
    touch = ["plugin/crew/README.md", "plugin/crew/docs", "plugin/crew/new"]
    chosen = rf.select(entries, touch, touch=True, root=str(tmp_path))

    assert [e["id"] for e in chosen] == ["RF-02", "RF-03"]


@pytest.mark.parametrize("root", [None, ""])
@pytest.mark.parametrize("call", ["matches", "select", "select-no-entries", "select-no-paths"])
def test_select_touch_needs_a_root(tmp_path, call, root):
    """Without a root a Touch entry cannot be told file from directory: the
    call refuses, even when there is nothing to iterate, rather than answer."""
    entries, _ = rf.parse(_data(tmp_path, _section("RF-01")))
    calls = {
        "matches": lambda: rf.matches("a/b", "**/*.py", touch=True, root=root),
        "select": lambda: rf.select(entries, ["a/b"], touch=True, root=root),
        "select-no-entries": lambda: rf.select([], ["a/b"], touch=True, root=root),
        "select-no-paths": lambda: rf.select(entries, [], touch=True, root=root),
    }

    with pytest.raises(ValueError, match="needs the root"):
        calls[call]()


def test_implementer_block_reads_a_touch_file_as_a_file(tmp_path):
    (tmp_path / "plugin" / "crew").mkdir(parents=True)
    (tmp_path / "plugin" / "crew" / "README.md").write_text("x", encoding="utf-8")
    data = _data(tmp_path, _section("RF-01", '["plugin/crew/README.md/*.py"]')
                 + _section("RF-02", '["**/*.md"]'))
    _spec(tmp_path, "L-0001", ["- `plugin/crew/README.md`"])
    lines, complete = rf.implementer_block(str(tmp_path), "L-0001", data=data)

    assert complete is True
    assert _ids(lines) == ["RF-02"]


def _many_bad(count):
    return "".join(f"## bad heading {n}\n" for n in range(count)) + _section("RF-01")


@pytest.mark.parametrize("reader", ["review", "implementer"])
def test_scope_unknown_survives_note_truncation(tmp_path, reader):
    data = _data(tmp_path, _many_bad(70))
    if reader == "review":
        lines = rf.review_block(str(tmp_path), dict(EMPTY, staged_files=None), data=data)
    else:
        _spec(tmp_path, "L-0001", [])
        lines, _ = rf.implementer_block(str(tmp_path), "L-0001", data=data)

    assert any(line.startswith("UNKNOWN:") for line in lines)
    assert any("more notes not shown" in line for line in lines)
    assert len(lines) <= rf.MAX_LINES


def test_render_header_bound():
    two = ["UNKNOWN: a", "UNKNOWN: b"]

    assert len(rf.render(["h"] * (rf.MAX_LINES - 1), [])) == rf.MAX_LINES
    assert len(rf.render(["h"] * (rf.MAX_LINES - 3), [], two)) <= rf.MAX_LINES
    for header, notes in ((rf.MAX_LINES, []), (61, []),
                          (rf.MAX_LINES - 3, two + ["PROBLEM: x"])):
        with pytest.raises(ValueError, match="cannot fit"):
            rf.render(["h"] * header, [], notes)


@pytest.mark.parametrize("with_entry", [False, True])
@pytest.mark.parametrize("data", [0, 1, 56, 200])
@pytest.mark.parametrize("scope", [0, 1, 3])
@pytest.mark.parametrize("header", [1, 3, 10])
def test_render_required_lines_table(tmp_path, header, scope, data, with_entry):
    entries = rf.parse(_data(tmp_path, _section("RF-01", probes=4)))[0] if with_entry else []
    notes = [f"PROBLEM: d{n}" for n in range(data)] + [f"UNKNOWN: s{n}" for n in range(scope)]
    lines = rf.render(["h"] * header, entries, notes)

    assert len(lines) <= rf.MAX_LINES
    assert all(f"UNKNOWN: s{n}" in lines for n in range(scope))
    assert (not data) or any(line.startswith("PROBLEM:") or "more notes" in line
                             for line in lines)


@pytest.mark.parametrize("bad", [0, 1, 70, 200])
@pytest.mark.parametrize("scope_unknown", [False, True])
@pytest.mark.parametrize("reader", ["review", "implementer"])
def test_readers_never_exceed_the_cap(tmp_path, reader, scope_unknown, bad):
    data = _data(tmp_path, _many_bad(bad))
    if reader == "review":
        lines = rf.review_block(str(tmp_path), {} if scope_unknown else _manifest("a.py"),
                                data=data)
    else:
        _spec(tmp_path, "L-0001", [] if scope_unknown else ["- `a.py`"])
        lines, _ = rf.implementer_block(str(tmp_path), "L-0001", data=data)

    assert len(lines) <= rf.MAX_LINES
    assert any(line.startswith("UNKNOWN:") for line in lines) is scope_unknown

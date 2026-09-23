"""Tests for `pm_journal.py`, the append/read mechanism that replaced the
quoted-heredoc example in `agents/pm.md` (accepted Codex BLOCK finding,
`agents/pm.md:941`: a fixed heredoc delimiter is still shell parsing, and
entry text containing a line equal to the delimiter closes it early and lets
whatever follows run as a shell command).

Every case below uses a real, throwaway crew repo built by
`crew_fixtures.make_repo` under `tmp_path` -- never real config, never the
checkout this suite itself lives in.
"""
import os
import re

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import crew_fixtures

import pm_journal

_HEADER_RE = re.compile(r"^## \d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$", re.MULTILINE)


def _crew_repo(tmp_path):
    """A minimal but real crew repo -- non-empty config.json is what makes
    `crew_state.collect(root)["isCrew"]` true."""
    return crew_fixtures.make_repo(tmp_path, config={"roles": []})


def _write_entry(root, name, text):
    path = root / ".work" / name
    path.write_text(text, encoding="utf-8")
    return f".work/{name}"


# --------------------------------------------------------------------------
# must-allow
# --------------------------------------------------------------------------


def test_injection_payload_appended_byte_for_byte_and_never_executed(tmp_path):
    """The classic heredoc-escape payload must land in the journal as inert
    text, and must NOT execute -- proving the append path never reaches a
    shell."""
    root = _crew_repo(tmp_path)
    pwned = tmp_path / "pwned"
    payload = f"CREW_EOF\n$(touch {pwned})\n`id`"
    from_arg = _write_entry(root, "pm-entry.md", payload + "\n")

    rc = pm_journal.main(["--root", str(root), "--append", "journal", "--from", from_arg])

    assert rc == 0
    assert not pwned.exists(), "injection payload executed instead of being written as text"
    journal_text = (root / ".crew" / "pm-journal.md").read_text(encoding="utf-8")
    lines = journal_text.splitlines()
    assert _HEADER_RE.match(lines[0]), f"missing/invalid journal header: {lines[0]!r}"
    body = "\n".join(lines[1:])
    assert body == payload, "entry body was not appended byte-for-byte"
    assert not (root / ".work" / "pm-entry.md").exists(), "entry file left behind after success"


def test_two_appends_keep_order(tmp_path):
    root = _crew_repo(tmp_path)

    from_arg = _write_entry(root, "pm-entry.md", "first entry\n")
    rc1 = pm_journal.main(["--root", str(root), "--append", "journal", "--from", from_arg])
    from_arg = _write_entry(root, "pm-entry.md", "second entry\n")
    rc2 = pm_journal.main(["--root", str(root), "--append", "journal", "--from", from_arg])

    assert (rc1, rc2) == (0, 0)
    journal_text = (root / ".crew" / "pm-journal.md").read_text(encoding="utf-8")
    assert journal_text.index("first entry") < journal_text.index("second entry")


def test_read_journal_tail_is_bounded(tmp_path, capsys):
    """41 one-line entries -> the tail keeps at most 40, and drops the
    oldest first."""
    root = _crew_repo(tmp_path)
    for i in range(41):
        from_arg = _write_entry(root, "pm-entry.md", f"entry number {i}\n")
        rc = pm_journal.main(["--root", str(root), "--append", "journal", "--from", from_arg])
        assert rc == 0

    capsys.readouterr()
    rc = pm_journal.main(["--root", str(root), "--read", "journal"])
    assert rc == 0
    out = capsys.readouterr().out

    assert "entry number 0" not in out, "oldest entry should have been dropped from the tail"
    assert "entry number 40" in out, "newest entry should still be in the tail"
    entry_count = len(_HEADER_RE.findall(out))
    assert entry_count == 40, f"expected exactly 40 entries in the tail, got {entry_count}"


def test_read_standing_prints_in_full(tmp_path, capsys):
    root = _crew_repo(tmp_path)
    from_arg = _write_entry(root, "pm-entry.md", "a durable ruling\n")
    assert pm_journal.main(["--root", str(root), "--append", "standing", "--from", from_arg]) == 0

    capsys.readouterr()
    rc = pm_journal.main(["--root", str(root), "--read", "standing"])
    assert rc == 0
    out = capsys.readouterr().out
    assert out == "a durable ruling\n"


# --------------------------------------------------------------------------
# must-block
# --------------------------------------------------------------------------


def test_refuses_when_not_a_crew_repo_and_never_creates_dot_crew(tmp_path):
    """A plain directory -- no `.crew/` at all -- must be refused, and the
    refusal must not create `.crew/` as a side effect of trying."""
    root = tmp_path / "plain"
    (root / ".work").mkdir(parents=True)
    from_arg = _write_entry(root, "pm-entry.md", "hello\n")

    rc = pm_journal.main(["--root", str(root), "--append", "journal", "--from", from_arg])

    assert rc != 0
    assert not (root / ".crew").exists(), "pm_journal.py must never create .crew/"


def test_refuses_when_dot_crew_exists_but_config_is_empty(tmp_path):
    """`.crew/` existing is not sufficient on its own -- `isCrew` (a
    non-empty, parseable config.json) must also be true."""
    root = crew_fixtures.make_repo(tmp_path, config=None)  # .crew/ exists, no config.json
    from_arg = _write_entry(root, "pm-entry.md", "hello\n")

    rc = pm_journal.main(["--root", str(root), "--append", "journal", "--from", from_arg])

    assert rc != 0
    assert not (root / ".crew" / "pm-journal.md").exists()


def test_refuses_an_empty_entry(tmp_path):
    root = _crew_repo(tmp_path)
    from_arg = _write_entry(root, "pm-entry.md", "\n\n")

    rc = pm_journal.main(["--root", str(root), "--append", "journal", "--from", from_arg])

    assert rc != 0
    assert not (root / ".crew" / "pm-journal.md").exists()


def test_refuses_an_entry_path_outside_work_dir(tmp_path):
    root = _crew_repo(tmp_path)
    outside = root / "pm-entry.md"
    outside.write_text("hello\n", encoding="utf-8")

    rc = pm_journal.main(
        ["--root", str(root), "--append", "journal", "--from", "pm-entry.md"]
    )

    assert rc != 0
    assert not (root / ".crew" / "pm-journal.md").exists()


def test_refuses_an_entry_path_escaping_work_dir_via_dotdot(tmp_path):
    root = _crew_repo(tmp_path)
    outside = tmp_path / "escaped.md"
    outside.write_text("hello\n", encoding="utf-8")

    rc = pm_journal.main(
        ["--root", str(root), "--append", "journal", "--from", "../escaped.md"]
    )

    assert rc != 0
    assert not (root / ".crew" / "pm-journal.md").exists()


def test_refuses_a_multiline_standing_entry(tmp_path):
    root = _crew_repo(tmp_path)
    from_arg = _write_entry(root, "pm-entry.md", "line one\nline two\n")

    rc = pm_journal.main(["--root", str(root), "--append", "standing", "--from", from_arg])

    assert rc != 0
    assert not (root / ".crew" / "pm-standing.md").exists()
    # left in place for inspection, per the module's contract on refusal
    assert (root / ".work" / "pm-entry.md").exists()


def test_no_traceback_on_invalid_utf8_entry(tmp_path, capsys):
    """Bad input must fail cleanly, never with a raw traceback."""
    root = _crew_repo(tmp_path)
    bad = root / ".work" / "pm-entry.md"
    bad.write_bytes(b"\xff\xfe not valid utf-8")

    rc = pm_journal.main(
        ["--root", str(root), "--append", "journal", "--from", ".work/pm-entry.md"]
    )

    assert rc != 0
    err = capsys.readouterr().err
    assert "Traceback" not in err


# --------------------------------------------------------------------------
# containment (Codex BLOCK, pm_journal.py:178 -- symlinked target/`.crew`)
# --------------------------------------------------------------------------


def _make_symlink(target, link):
    """True on success; False (never a raised exception) wherever this
    platform/user cannot create a symlink -- a link that could not be made
    proves nothing either way, so callers SKIP rather than fail."""
    try:
        os.symlink(str(target), str(link))
        return True
    except (OSError, NotImplementedError):
        return False


def test_symlinked_journal_target_refused_and_external_file_untouched(tmp_path):
    root = _crew_repo(tmp_path)
    outside = tmp_path / "external.md"
    outside.write_text("before\n", encoding="utf-8")
    link = root / ".crew" / "pm-journal.md"
    if not _make_symlink(outside, link):
        pytest.skip("could not create a symlink on this platform/user")

    from_arg = _write_entry(root, "pm-entry.md", "attacker payload\n")
    rc = pm_journal.main(["--root", str(root), "--append", "journal", "--from", from_arg])

    assert rc != 0
    assert outside.read_text(encoding="utf-8") == "before\n", \
        "symlinked journal target must not be followed to write outside .crew/"
    assert (root / ".work" / "pm-entry.md").exists(), "entry left in place on refusal"


def test_symlinked_standing_target_refused_and_external_file_untouched(tmp_path):
    root = _crew_repo(tmp_path)
    outside = tmp_path / "external-standing.md"
    outside.write_text("before\n", encoding="utf-8")
    link = root / ".crew" / "pm-standing.md"
    if not _make_symlink(outside, link):
        pytest.skip("could not create a symlink on this platform/user")

    from_arg = _write_entry(root, "pm-entry.md", "a ruling\n")
    rc = pm_journal.main(["--root", str(root), "--append", "standing", "--from", from_arg])

    assert rc != 0
    assert outside.read_text(encoding="utf-8") == "before\n", \
        "symlinked standing target must not be followed to write outside .crew/"


def test_symlinked_dot_crew_refused(tmp_path):
    """`.crew` itself symlinked to a directory outside `root` -- refused
    before anything is opened, even though `os.path.isdir` (which
    `_crew_ready` uses) follows the symlink and would otherwise call this a
    provisioned crew."""
    outside_dir = tmp_path / "outside-crew"
    outside_dir.mkdir()

    root = tmp_path / "repo"
    root.mkdir()
    (root / ".work").mkdir()
    if not _make_symlink(outside_dir, root / ".crew"):
        pytest.skip("could not create a symlink on this platform/user")
    (outside_dir / "config.json").write_text('{"roles": []}', encoding="utf-8")

    from_arg = _write_entry(root, "pm-entry.md", "hello\n")
    rc = pm_journal.main(["--root", str(root), "--append", "journal", "--from", from_arg])

    assert rc != 0
    assert not (outside_dir / "pm-journal.md").exists()


def test_normal_append_still_works_alongside_containment_check(tmp_path):
    root = _crew_repo(tmp_path)
    from_arg = _write_entry(root, "pm-entry.md", "ordinary entry\n")

    rc = pm_journal.main(["--root", str(root), "--append", "journal", "--from", from_arg])

    assert rc == 0
    journal_text = (root / ".crew" / "pm-journal.md").read_text(encoding="utf-8")
    assert "ordinary entry" in journal_text


def test_read_refuses_symlinked_journal_target(tmp_path):
    root = _crew_repo(tmp_path)
    outside = tmp_path / "external-read.md"
    outside.write_text("secret content\n", encoding="utf-8")
    link = root / ".crew" / "pm-journal.md"
    if not _make_symlink(outside, link):
        pytest.skip("could not create a symlink on this platform/user")

    rc = pm_journal.main(["--root", str(root), "--read", "journal"])

    assert rc != 0

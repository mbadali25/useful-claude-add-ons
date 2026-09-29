"""The ticket-contract block of the review prompt: every piece is either
present or stated as MISSING, never silently omitted."""
import pytest

import context  # noqa: F401  pylint: disable=unused-import
import review_prompt as rp
import review_verdict
from review_fixtures import git, init_repo

MANIFEST = {"parts": [{"name": "part-001-of-001.patch", "path": "/s/part-001-of-001.patch"}],
            "patch_bytes": 10, "bundle_sha256": "f" * 64, "dirty": True,
            "renames": ["new.txt"], "binary_files": ["b.bin"]}


@pytest.fixture(name="repo")
def _repo(tmp_path):
    return init_repo(tmp_path / "r")


def test_build_states_every_missing_piece(repo):
    text = rp.build(str(repo), "T9", MANIFEST)

    assert "MISSING: no spec at" in text
    assert "MISSING: no plan at" in text
    assert "MISSING: no .crew/.verify-verified-at" in text
    assert "MISSING: no .crew/.verify-gate.record.json" in text


def test_build_includes_spec_sections_plan_and_receipts(repo):
    ticket = repo / ".work" / "tickets" / "T9"
    ticket.mkdir(parents=True)
    (ticket / "spec.md").write_text(
        "# T9\n\n## Intent\nmake x\n\n## Exclusions\nnot y\n\n## Evidence\nsrc/a.py:3\n\n"
        "## Acceptance checks\n- test passes\n", encoding="utf-8")
    (ticket / "plan.md").write_text("1. edit a.py\n", encoding="utf-8")
    (repo / ".crew").mkdir()
    (repo / ".crew" / ".verify-verified-at").write_text(git(repo, "rev-parse", "HEAD") + "\n",
                                                        encoding="utf-8")
    (repo / ".crew" / ".verify-gate.record.json").write_text(
        '{"rules": {"k": {"label": "smoke", "reason": "over budget"}}}', encoding="utf-8")

    text = rp.build(str(repo), "T9", MANIFEST)

    for expected in ("make x", "not y", "src/a.py:3", "- test passes", "1. edit a.py",
                     "-- Unknowns -- MISSING", "NOT VERIFIED: smoke: over budget",
                     "/s/part-001-of-001.patch", "renamed: new.txt"):
        assert expected in text, expected


def test_build_names_the_excluded_paths(repo):
    """T-0092: a reviewer is told what the bundle left out, and a manifest
    that cannot say is stated, not silent."""
    text = rp.build(str(repo), "T9", dict(MANIFEST, excluded=[".work/", "graphify-out/"]))
    bare = rp.build(str(repo), "T9", MANIFEST)

    assert "  excluded (never in the bundle): .work/, graphify-out/" in text
    assert text.index("excluded (never in the bundle)") < text.index("Manifest (file categories")
    assert "  excluded: none recorded" in bare


def test_build_states_the_read_form_the_parser_accepts(repo):
    """The prompt quotes the parser's own READ form: asking for a bare name
    while listing full paths is how honest rounds read as INCOMPLETE (T-0079)."""
    text = rp.build(str(repo), "T9", MANIFEST)

    assert (review_verdict.READ_FORM in text, "READ|<its file name>" in text) == (True, False)


def test_build_falls_back_to_the_files_mode_ticket(repo):
    tickets = repo / ".work" / "tickets"
    tickets.mkdir(parents=True)
    (tickets / "T9.md").write_text("## Intent\nfrom the ticket file\n", encoding="utf-8")

    text = rp.build(str(repo), "T9", MANIFEST)

    assert "from the ticket file" in text and "(from .work/tickets/T9.md)" in text


def test_relpath_is_forward_slash_even_when_os_sep_is_a_backslash(monkeypatch):
    # Host-independent: real ntpath.relpath semantics can't be exercised on a
    # POSIX runner, so the Windows shape is modelled directly -- a relpath
    # that already came back with backslashes (what ntpath.relpath returns),
    # with os.sep forced to match so `_relpath`'s conversion step is the one
    # under test, not `os.path.relpath` itself.
    monkeypatch.setattr(rp.os.path, "relpath", lambda path, root: "tickets\\T9.md")
    monkeypatch.setattr(rp.os, "sep", "\\")

    assert rp._relpath("root\\tickets\\T9.md", "root") == "tickets/T9.md"


def test_sections_keeps_nested_headings_inside_their_parent():
    found = rp.sections("# T\n## Intent\nfoo\n### detail\nbar\n## Exclusions\nnone\n")

    assert found["intent"] == "foo\n### detail\nbar"

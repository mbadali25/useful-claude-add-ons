"""The ticket-contract block of the review prompt: every piece is either
present or stated as MISSING, never silently omitted."""
import json
import os
import re

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import crew_train
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


# ---- the development standards checklist (T-0085) ----------------------------------

LISTED = dict(MANIFEST, committed_files=["a.py"], staged_files=[], unstaged_files=[],
              untracked_files=[])
WITHHELD = ("The author ran these as a self-check; the answers are withheld so you judge "
            "applicability yourself.")
UNBOUNDED = "This list does not bound the review: report a defect outside it the same way."


def test_prompt_carries_the_standards_checklist(repo):
    text = rp.build(str(repo), "T9", LISTED)

    block = text[text.index("== Development standards checklist (appendix) =="):]
    ids = re.findall(r"^(GEN-\d\d) ", block, flags=re.M)
    assert (text.index("== Test receipts (verify gate) ==") < text.index(block[:20]),
            ids, WITHHELD in block, UNBOUNDED in block,
            "Where a probe, read, parse, import or subprocess can fail" in block,
            "For every `except`, fallback and default in the diff" in block) == (
        True, [f"GEN-{n:02d}" for n in range(1, 13)], True, True, True, True)


def test_prompt_never_carries_selfcheck_answers(repo):
    ticket = repo / ".work" / "tickets" / "T9"
    ticket.mkdir(parents=True)
    (ticket / "selfcheck.md").write_text(
        "# T9 self-check\n\n| ID | Status | Evidence or reason |\n|---|---|---|\n"
        "| GEN-01 | addressed | SELFCHECK-ANSWER-7f3a |\n", encoding="utf-8")

    text = rp.build(str(repo), "T9", LISTED)

    assert "SELFCHECK-ANSWER-7f3a" not in text


def test_prompt_says_unreadable_overlay(repo):
    (repo / ".crew").mkdir(exist_ok=True)
    (repo / ".crew" / "standards.md").write_bytes(b"\xff\xfe not utf-8")

    text = rp.build(str(repo), "T9", LISTED)

    block = text[text.index("== Development standards checklist (appendix) =="):]
    assert (bool(re.search(r"^UNREADABLE: \.crew/standards\.md", block, flags=re.M)),
            "GEN-01 " in block) == (True, True)


def test_prompt_lists_the_overlay_and_its_supplements(repo):
    (repo / ".crew").mkdir(exist_ok=True)
    (repo / ".crew" / "standards.md").write_text(
        '---\nset: REPO\napplies-to: ["**"]\n---\n\n## REPO-01 Local rule\n\n**Rule.** local r\n\n'
        "**Self-check.** local s\n\n## Supplements GEN-01\n\nLOCAL-SUPPLEMENT-TEXT\n",
        encoding="utf-8")

    text = rp.build(str(repo), "T9", LISTED)

    assert ("REPO-01 Local rule" in text, "LOCAL-SUPPLEMENT-TEXT" in text) == (True, True)


def _merge_log(repo, rows=None, raw=None):
    path = crew_train.merge_log_path(str(repo), "T9")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    text = raw if raw is not None else "".join(json.dumps(r) + "\n" for r in rows)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
    return path


def test_prompt_lists_rerere_replayed_files(repo):
    _merge_log(repo, [
        {"outcome": "merged", "base": "main", "base_sha": "a" * 40, "rerere_replayed": []},
        {"outcome": "rerere-resolved", "base": "main", "base_sha": "b" * 40,
         "rerere_replayed": ["src/x.py", "src/y.py"]}])

    text = rp.build(str(repo), "T9", MANIFEST)

    assert "== Catch-up merges (rerere) ==" in text
    assert "  src/x.py (main@bbbbbbbbbbbb): replayed by rerere" in text
    assert "  src/y.py (main@bbbbbbbbbbbb): replayed by rerere" in text
    assert "review it as a change in this diff" in text


def test_prompt_has_no_catch_up_block_without_a_log(repo):
    text = rp.build(str(repo), "T9", MANIFEST)

    assert "Catch-up merges" not in text


def test_prompt_marks_an_unreadable_merge_log(repo):
    path = _merge_log(repo, raw="{not json\n")

    text = rp.build(str(repo), "T9", MANIFEST)

    assert "== Catch-up merges (rerere) ==" in text
    assert f"UNREADABLE: {path}:1 does not parse" in text

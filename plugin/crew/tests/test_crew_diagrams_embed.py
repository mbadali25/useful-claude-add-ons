"""T-0035: crew_diagrams.py embeds each diagram as a generated, marker-delimited
```mermaid block in the README nearest its anchors, and `check` fails when an
embed differs from its source. Fixture trees under tmp_path only."""
import os
import subprocess

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import crew_diagrams
import diagram_doc

BEGIN = crew_diagrams.BEGIN
END = crew_diagrams.END


def _write(root, rel, text):
    path = os.path.join(str(root), *rel.split("/"))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    return path


def _read(root, rel):
    with open(os.path.join(str(root), *rel.split("/")), encoding="utf-8", newline="") as fh:
        return fh.read()


def _source(anchors, purpose="How a request reaches the store.", extra="", body=None):
    text = "%% Generated from repo@abc1234 on 2026-10-04. Verify before trusting.\n"
    if anchors is not None:
        text += "%% Anchors: " + ", ".join(anchors) + "\n"
    if purpose:
        text += f"%% Purpose: {purpose}\n"
    text += extra
    text += body or "flowchart LR\n  a -->|request| b\n"
    return text


def _tree(tmp_path, readme="# Plugin x\n\nHand-written prose.\n"):
    root = tmp_path / "repo"
    _write(root, "README.md", "# root\n")
    _write(root, "plugin/x/README.md", readme)
    _write(root, "plugin/x/mcp/a.py", "print('a')\n")
    _write(root, "docs/diagrams/data-flow-x.mmd", _source(["plugin/x/mcp/a.py"]))
    return root


def _embed(root):
    return crew_diagrams.main(["embed", "--root", str(root)])


def _check(root):
    return crew_diagrams.main(["check", "--root", str(root)])


# --- embed --------------------------------------------------------------------

def test_embed_targets_nearest_readme(tmp_path):
    root = _tree(tmp_path)
    assert _embed(root) == 0
    text = _read(root, "plugin/x/README.md")
    assert BEGIN in text and END in text
    assert "```mermaid\nflowchart LR\n  a -->|request| b\n```" in text
    assert _read(root, "README.md") == "# root\n"  # the repo-root README is never a target


def test_embed_is_idempotent(tmp_path):
    root = _tree(tmp_path)
    assert _embed(root) == 0
    first = _read(root, "plugin/x/README.md")
    assert _embed(root) == 0
    assert _read(root, "plugin/x/README.md") == first
    assert _check(root) == 0


def test_prose_outside_markers_untouched(tmp_path):
    root = _tree(tmp_path, readme="# Plugin x\n\nBefore.\n\n" + BEGIN + "\nold\n" + END
                 + "\n\nAfter, hand-written.\n")
    before = _read(root, "plugin/x/README.md")
    assert _embed(root) == 0
    after = _read(root, "plugin/x/README.md")
    assert crew_diagrams.outside_markers(after) == crew_diagrams.outside_markers(before)
    assert after.startswith("# Plugin x\n\nBefore.\n\n" + BEGIN)
    assert after.endswith(END + "\n\nAfter, hand-written.\n")


def test_appended_section_changes_nothing_outside_the_markers(tmp_path):
    """The first embed appends; the heading lives inside the markers, so the
    text outside them is what it was (the future completion-audit allowance
    compares exactly this)."""
    root = _tree(tmp_path)
    before = _read(root, "plugin/x/README.md")
    assert _embed(root) == 0
    after = _read(root, "plugin/x/README.md")
    assert crew_diagrams.outside_markers(after) == crew_diagrams.outside_markers(before)
    assert "## Diagrams" in after.split(BEGIN)[1]


def test_summary_rendered_above_block(tmp_path):
    root = _tree(tmp_path)
    assert _embed(root) == 0
    section = _read(root, "plugin/x/README.md").split(BEGIN)[1]
    assert section.index("How a request reaches the store.") < section.index("```mermaid")


def test_embed_strips_comment_lines(tmp_path):
    root = _tree(tmp_path)
    assert _embed(root) == 0
    section = _read(root, "plugin/x/README.md").split(BEGIN)[1].split(END)[0]
    block = section.split("```mermaid")[1].split("```")[0]
    assert "%%" not in block
    # the provenance stays in the source, and the embed links to it
    assert "](../../docs/diagrams/data-flow-x.mmd)" in section


def test_embed_body_and_purpose_match_the_diagrams_page(tmp_path):
    """One source, two pages: the README embed carries the same purpose and
    body diagram_doc.py puts on docs/diagrams/README.md."""
    root = _tree(tmp_path)
    path = os.path.join(str(root), "docs", "diagrams", "data-flow-x.mmd")
    title, purpose, anchors, body = diagram_doc.read_source(path)
    got = crew_diagrams.read_source(path)
    assert (got["title"], got["purpose"], got["anchors"], got["body"]) == (title, purpose, anchors, body)


def test_every_repo_diagram_reads_as_the_diagrams_page_reads_it():
    top = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, os.pardir, os.pardir))
    d = os.path.join(top, "docs", "diagrams")
    names = [n for n in sorted(os.listdir(d)) if n.endswith((".mmd", ".mermaid"))]
    assert names, "no diagram in this repo to compare"
    for name in names:
        path = os.path.join(d, name)
        got = crew_diagrams.read_source(path)
        assert (got["title"], got["purpose"], got["anchors"], got["body"]) == \
            diagram_doc.read_source(path), name


def test_embed_override_header(tmp_path):
    root = _tree(tmp_path)
    _write(root, "docs/guide/README.md", "# guide\n")
    _write(root, "docs/diagrams/process-y.mmd",
           _source(["plugin/x/mcp/a.py"], extra="%% Embed: docs/guide/README.md\n"))
    _write(root, "docs/diagrams/process-z.mmd",
           _source(["plugin/x/mcp/a.py"], extra="%% Embed: none\n",
                   body="flowchart LR\n  z1 -->|zz| z2\n"))
    assert _embed(root) == 0
    assert "Process y" in _read(root, "docs/guide/README.md")
    assert "Process y" not in _read(root, "plugin/x/README.md")
    assert "z1 -->|zz| z2" not in _read(root, "plugin/x/README.md")


def test_override_naming_a_missing_or_non_readme_file_is_refused(tmp_path):
    root = _tree(tmp_path)
    _write(root, "docs/diagrams/process-y.mmd",
           _source(["plugin/x/mcp/a.py"], extra="%% Embed: plugin/x/NOTES.md\n"))
    before = _read(root, "plugin/x/README.md")
    assert _embed(root) == 1
    assert _read(root, "plugin/x/README.md") == before  # nothing written


def test_no_readme_means_index_only(tmp_path):
    root = tmp_path / "repo"
    _write(root, "README.md", "# root\n")
    _write(root, "skills/s/scripts/run.sh", "echo\n")
    _write(root, "docs/diagrams/process-s.mmd", _source(["skills/s/scripts/run.sh"]))
    result = crew_diagrams.check(str(root))
    assert result["targets"] == {}
    assert _embed(root) == 0
    assert _read(root, "README.md") == "# root\n"


def test_skill_md_never_a_target(tmp_path):
    root = tmp_path / "repo"
    _write(root, "README.md", "# root\n")
    _write(root, "skills/s/SKILL.md", "---\nname: s\n---\n")
    _write(root, "docs/diagrams/process-s.mmd", _source(["skills/s/SKILL.md"]))
    assert _embed(root) == 0
    assert _read(root, "skills/s/SKILL.md") == "---\nname: s\n---\n"
    _write(root, "docs/diagrams/process-t.mmd",
           _source(["skills/s/SKILL.md"], extra="%% Embed: skills/s/SKILL.md\n"))
    assert _embed(root) == 1  # an override cannot make one a target either


def test_a_readme_another_generator_owns_is_never_a_target(tmp_path):
    """docs/qa/README.md (qa_doc.py) and docs/diagrams/README.md (diagram_doc.py)
    are regenerated wholesale; a section written into them would be lost."""
    root = _tree(tmp_path)
    _write(root, "docs/qa/README.md", "<!-- generated by crew qa_doc.py; edit the inputs -->\n# QA\n")
    _write(root, "docs/qa/inputs.json", "{}\n")
    _write(root, "docs/diagrams/process-qa.mmd", _source(["docs/qa/inputs.json"]))
    assert _embed(root) == 0
    assert BEGIN not in _read(root, "docs/qa/README.md")
    assert crew_diagrams.check(str(root))["skipped"]


def test_unbalanced_markers_refused(tmp_path):
    for broken in (BEGIN + "\nno end\n", "x\n" + END + "\n" + BEGIN + "\n",
                   BEGIN + "\n" + BEGIN + "\n" + END + "\n",
                   BEGIN + "\n" + END + "\n" + BEGIN + "\n" + END + "\n"):
        root = _tree(tmp_path / str(abs(hash(broken))), readme="# x\n" + broken)
        before = _read(root, "plugin/x/README.md")
        assert _embed(root) == 1, broken
        assert _read(root, "plugin/x/README.md") == before
        assert _check(root) == 1
        assert crew_diagrams.outside_markers(before) is None


def test_a_marker_quoted_in_prose_is_not_a_marker(tmp_path):
    """crew's own README documents the markers in backticks; that prose is
    neither a section nor a malformed one."""
    prose = (f"# x\n\nThe section sits between `{BEGIN}` and `{END}`.\n"
             f"    {BEGIN} indented in a code block\n")
    root = _tree(tmp_path, readme=prose)
    assert crew_diagrams.outside_markers(prose) == prose.rstrip()
    assert _embed(root) == 0
    text = _read(root, "plugin/x/README.md")
    assert text.startswith(prose) and text.count(BEGIN) == 3
    assert _check(root) == 0


def test_check_detects_drift(tmp_path, capsys):
    root = _tree(tmp_path)
    assert _embed(root) == 0
    path = os.path.join(str(root), "plugin", "x", "README.md")
    text = _read(root, "plugin/x/README.md")
    _write(root, "plugin/x/README.md", text.replace("a -->|request| b", "a -->|hand edit| b"))
    capsys.readouterr()
    assert _check(root) == 1
    err = capsys.readouterr()
    assert "plugin/x/README.md" in err.out + err.err and "data-flow-x" in err.out + err.err
    assert os.path.isfile(path)


def test_check_detects_a_source_change_not_yet_embedded(tmp_path):
    root = _tree(tmp_path)
    assert _embed(root) == 0
    _write(root, "docs/diagrams/data-flow-x.mmd",
           _source(["plugin/x/mcp/a.py"], body="flowchart LR\n  a -->|request| c\n"))
    result = crew_diagrams.check(str(root))
    assert result["status"] == crew_diagrams.STALE
    assert [d["readme"] for d in result["drift"]] == ["plugin/x/README.md"]
    assert result["drift"][0]["diagrams"] == ["data-flow-x"]


def test_section_no_diagram_targets_any_more_is_drift_and_embed_removes_it(tmp_path):
    root = _tree(tmp_path)
    assert _embed(root) == 0
    os.remove(os.path.join(str(root), "docs", "diagrams", "data-flow-x.mmd"))
    assert crew_diagrams.check(str(root))["status"] == crew_diagrams.STALE
    assert _embed(root) == 0
    assert BEGIN not in _read(root, "plugin/x/README.md")
    assert _read(root, "plugin/x/README.md") == "# Plugin x\n\nHand-written prose.\n"
    assert _check(root) == 0


def test_a_readme_not_yet_embedded_is_pending_not_drift(tmp_path):
    """Adoption is one `embed` run: until a README has the markers, check
    names it as pending and passes, so installing this crew version does not
    refuse /crew:done in every repo that has diagrams."""
    root = _tree(tmp_path)
    result = crew_diagrams.check(str(root))
    assert result["status"] == crew_diagrams.FRESH
    assert result["pending"] == [{"readme": "plugin/x/README.md", "diagrams": ["data-flow-x"]}]


def test_an_unreadable_source_is_unknown_not_fresh(tmp_path):
    root = _tree(tmp_path)
    _write(root, "docs/diagrams/bad.mmd", "")
    with open(os.path.join(str(root), "docs", "diagrams", "bad.mmd"), "wb") as fh:
        fh.write(b"\xff\xfe\x00bad utf-8 \xc3")
    result = crew_diagrams.check(str(root))
    assert result["status"] == crew_diagrams.UNKNOWN
    assert any("bad.mmd" in u for u in result["unknown"])


@pytest.mark.skipif(os.name == "nt" or (hasattr(os, "geteuid") and os.geteuid() == 0),
                    reason="chmod 000 does not deny a listing on Windows or to root")
def test_an_unlistable_diagrams_dir_is_unknown(tmp_path):
    root = _tree(tmp_path)
    d = os.path.join(str(root), "docs", "diagrams")
    os.chmod(d, 0)
    try:
        assert crew_diagrams.check(str(root))["status"] == crew_diagrams.UNKNOWN
    finally:
        os.chmod(d, 0o755)


def test_an_unlistable_diagrams_dir_is_unknown_injected(tmp_path, monkeypatch):
    """The same could-not-tell, injected, so it runs as root and on Windows."""
    root = _tree(tmp_path)
    real = os.listdir

    def denied(path):
        if os.path.normpath(str(path)).endswith(os.path.join("docs", "diagrams")):
            raise PermissionError(13, "Permission denied")
        return real(path)
    monkeypatch.setattr(crew_diagrams.os, "listdir", denied)
    result = crew_diagrams.check(str(root))
    assert result["status"] == crew_diagrams.UNKNOWN
    assert _embed(root) == 1


def test_a_missing_diagrams_dir_is_fresh_with_nothing_to_embed(tmp_path):
    root = tmp_path / "repo"
    _write(root, "README.md", "# root\n")
    assert crew_diagrams.check(str(root))["status"] == crew_diagrams.FRESH


def test_configured_diagrams_dir_is_honoured(tmp_path):
    root = tmp_path / "repo"
    _write(root, "README.md", "# root\n")
    _write(root, ".crew/config.json", '{"docs": {"diagramsDir": "design/charts"}}\n')
    _write(root, "plugin/x/README.md", "# x\n")
    _write(root, "plugin/x/a.py", "a\n")
    _write(root, "design/charts/process-x.mmd", _source(["plugin/x/a.py"]))
    assert _embed(root) == 0
    assert "](../../design/charts/process-x.mmd)" in _read(root, "plugin/x/README.md")


def test_crlf_readme_keeps_crlf_and_reads_clean(tmp_path):
    root = _tree(tmp_path)
    path = os.path.join(str(root), "plugin", "x", "README.md")
    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write("# Plugin x\r\n\r\nProse.\r\n")
    assert _embed(root) == 0
    text = _read(root, "plugin/x/README.md")
    assert "\r\n" in text and "\n" not in text.replace("\r\n", "")
    assert _check(root) == 0


def test_directory_anchor_reaches_the_readme_in_it(tmp_path):
    root = _tree(tmp_path)
    _write(root, "docs/diagrams/data-flow-x.mmd", _source(["plugin/x/mcp"]))
    assert _embed(root) == 0
    assert BEGIN in _read(root, "plugin/x/README.md")


def test_anchor_escaping_the_repo_is_ignored(tmp_path):
    root = _tree(tmp_path)
    _write(tmp_path, "outside/README.md", "# outside\n")
    _write(root, "docs/diagrams/data-flow-x.mmd", _source(["../outside/a.py", "/etc/passwd"]))
    assert _embed(root) == 0
    assert _read(tmp_path, "outside/README.md") == "# outside\n"


# --- Bitbucket ------------------------------------------------------------------

def _git(root, *args):
    return subprocess.run(("git",) + args, cwd=str(root), capture_output=True, text=True,
                          stdin=subprocess.DEVNULL, timeout=30, check=False)


def _bitbucket(tmp_path, ignore_out):
    root = _tree(tmp_path)
    _git(root, "init", "-q")
    _git(root, "remote", "add", "origin", "git@bitbucket.org:x/y.git")
    if ignore_out:
        _write(root, ".gitignore", "docs/diagrams/out/\n")
    return root


def test_bitbucket_origin_embeds_svg_link(tmp_path):
    root = _bitbucket(tmp_path, ignore_out=False)
    assert _embed(root) == 0
    section = _read(root, "plugin/x/README.md").split(BEGIN)[1]
    assert "![Data flow x](../../docs/diagrams/out/data-flow-x.svg)" in section
    assert "<details>" in section and "```mermaid" in section.split("<details>")[1]
    assert _check(root) == 0


def test_bitbucket_warns_when_svg_ignored(tmp_path, capsys):
    root = _bitbucket(tmp_path, ignore_out=True)
    assert _embed(root) == 0
    err = capsys.readouterr().err
    assert "docs/diagrams/out/data-flow-x.svg" in err and "ignored" in err


def test_github_origin_embeds_the_fenced_block(tmp_path):
    root = _tree(tmp_path)
    _git(root, "init", "-q")
    _git(root, "remote", "add", "origin", "https://github.com/x/y.git")
    assert _embed(root) == 0
    section = _read(root, "plugin/x/README.md").split(BEGIN)[1]
    assert "<details>" not in section and "![" not in section


# --- outside_markers ------------------------------------------------------------

@pytest.mark.parametrize("text,expected", [
    ("a\n", "a"),
    ("a\n\n" + BEGIN + "\nx\n" + END + "\n", "a"),
    ("a\n" + BEGIN + "\nx\n" + END + "\nb\n", "a\nb"),
    ("a\n" + BEGIN + "\n" + END + "\n", "a"),
])
def test_outside_markers(text, expected):
    assert crew_diagrams.outside_markers(text) == expected


def test_outside_markers_sees_an_edit_outside(tmp_path):
    base = "a\n" + BEGIN + "\nx\n" + END + "\nb\n"
    assert crew_diagrams.outside_markers(base) != crew_diagrams.outside_markers(
        base.replace("\nb\n", "\nB\n"))

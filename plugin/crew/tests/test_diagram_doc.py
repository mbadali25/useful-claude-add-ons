"""crew-diagrams' companion page: every diagram embedded beside its purpose,
sources and readability; the verdict comes from a render, never a guess; a
hand-written README is refused."""
import os
import shutil

import context  # noqa: F401  pylint: disable=unused-import
import diagram_doc

FIX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "diagrams")
SOURCE = """%% Generated from repo@abc1234 on 2026-10-03. Verify before trusting.
%% Anchors: src/a.py, src/b.py
%% Purpose: How a change reaches merge.
flowchart TD
  a --> b
"""


def _dir(tmp_path, rendered=None):
    d = tmp_path / "docs" / "diagrams"
    d.mkdir(parents=True)
    (d / "process-merge.mmd").write_text(SOURCE, encoding="utf-8")
    if rendered:
        (d / "out").mkdir()
        shutil.copy(os.path.join(FIX, rendered), d / "out" / "process-merge.svg")
    return d


def test_dry_run_writes_nothing(tmp_path, capsys):
    d = _dir(tmp_path)
    assert diagram_doc.main(["--dir", str(d)]) == 0
    assert "dry run" in capsys.readouterr().out and not (d / "README.md").exists()


def test_the_page_embeds_the_diagram_with_its_purpose_and_sources(tmp_path):
    d = _dir(tmp_path)
    assert diagram_doc.main(["--dir", str(d), "--write"]) == 0
    md = (d / "README.md").read_text(encoding="utf-8")
    assert "```mermaid\nflowchart TD\n  a --> b\n```" in md
    assert "How a change reaches merge." in md and "`src/a.py`" in md
    assert "%%" not in md.split("```mermaid")[1]  # provenance stays in the source
    page = (d / "index.html").read_text(encoding="utf-8")
    assert '<pre class="mermaid">' in page and "How a change reaches merge." in page


def test_an_unrendered_diagram_is_not_called_readable(tmp_path):
    d = _dir(tmp_path)
    diagram_doc.main(["--dir", str(d), "--write"])
    assert "not rendered" in (d / "README.md").read_text(encoding="utf-8")


def test_the_verdict_comes_from_the_render(tmp_path):
    d = _dir(tmp_path, rendered="crossing.svg")
    diagram_doc.main(["--dir", str(d), "--write"])
    assert "FAIL: 1 crossing(s)" in (d / "README.md").read_text(encoding="utf-8")


def test_a_hand_written_readme_is_refused_and_kept(tmp_path, capsys):
    d = _dir(tmp_path)
    (d / "README.md").write_text("# ours\n", encoding="utf-8")
    assert diagram_doc.main(["--dir", str(d), "--write"]) == 1
    assert (d / "README.md").read_text(encoding="utf-8") == "# ours\n"
    assert "REFUSED" in capsys.readouterr().err


def test_without_a_purpose_line_the_first_plain_comment_is_used(tmp_path):
    d = _dir(tmp_path)
    (d / "process-merge.mmd").write_text(SOURCE.replace("%% Purpose: ", "%% "), encoding="utf-8")
    _, purpose, _, _ = diagram_doc.read_source(str(d / "process-merge.mmd"))
    assert purpose == ["How a change reaches merge."]


def test_box_details_come_from_note_lines_and_stay_out_of_the_drawing(tmp_path):
    d = _dir(tmp_path)
    (d / "process-merge.mmd").write_text(SOURCE.replace(
        "flowchart TD", "%% Note a: reads verify.json at verify-gate.sh:803,\n%%    then stamps the marker\n"
        "flowchart TD"), encoding="utf-8")
    diagram_doc.main(["--dir", str(d), "--write"])
    md = (d / "README.md").read_text(encoding="utf-8")
    assert "| `a` | reads verify.json at verify-gate.sh:803, then stamps the marker |" in md
    assert "verify-gate.sh:803" not in md.split("```mermaid")[1].split("```")[0]
    assert "<td><code>a</code></td>" in (d / "index.html").read_text(encoding="utf-8")


def test_note_markup_from_a_mermaid_label_reads_as_plain_text():
    assert diagram_doc.plain('"<b>merged</b> file<br/>is #quot;ok#quot; &lt;3"') == 'merged file is "ok" <3'


def test_text_that_only_looks_like_a_tag_is_kept():
    """`<repo>` and `</svg>` are what a note is about, not markup (found by a splitting agent)."""
    assert diagram_doc.plain("clone <repo>, ends </svg> in <i>out</i>") == "clone <repo>, ends </svg> in out"


def test_an_edge_note_is_read_by_its_src_dst_id(tmp_path):
    d = _dir(tmp_path)
    (d / "process-merge.mmd").write_text(SOURCE.replace(
        "flowchart TD", "%% Note a->b: the full edge wording\nflowchart TD"), encoding="utf-8")
    assert diagram_doc.read_notes(str(d / "process-merge.mmd")) == [("a->b", "the full edge wording")]

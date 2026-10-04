"""crew-diagrams' companion page: every diagram embedded beside its purpose,
sources and readability; the verdict comes from a render, never a guess; a
hand-written README is refused."""
import os
import shutil
import subprocess

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import crew_fixtures
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
        _age(d / "process-merge.mmd", 60)  # the render is newer than its source
        # what render.sh records beside the SVG: the sha256 of the source it rendered
        (d / "out" / "process-merge.svg.src").write_text(
            diagram_doc.source_hash(str(d / "process-merge.mmd")) + "\n", encoding="utf-8")
    return d


def _age(path, seconds):
    st = os.stat(path)
    os.utime(path, ns=(st.st_atime_ns, st.st_mtime_ns - seconds * 10 ** 9))


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


# --- review of PR #375 ------------------------------------------------------

def test_a_render_older_than_its_source_is_out_of_date_not_pass(tmp_path):
    """No .src beside the render: file times are the only evidence."""
    d = _dir(tmp_path, rendered="clean.svg")
    (d / "out" / "process-merge.svg.src").unlink()
    assert diagram_doc.verdict(str(d), "process-merge.mmd").startswith("PASS (freshness by mtime only): ")
    _age(d / "out" / "process-merge.svg", 120)  # the source was edited after the render
    diagram_doc.main(["--dir", str(d), "--write"])
    md = (d / "README.md").read_text(encoding="utf-8")
    assert "render out of date (run render.sh" in md and "PASS" not in md


def test_tag_like_note_text_is_escaped_in_the_markdown_table(tmp_path):
    d = _dir(tmp_path)
    (d / "process-merge.mmd").write_text(SOURCE.replace(
        "flowchart TD", "%% Note a: clone <repo> & run a|b\nflowchart TD"), encoding="utf-8")
    diagram_doc.main(["--dir", str(d), "--write"])
    assert "| `a` | clone &lt;repo&gt; &amp; run a/b |" in (d / "README.md").read_text(encoding="utf-8")


def test_a_file_quoting_the_marker_below_its_head_is_still_refused(tmp_path):
    d = _dir(tmp_path)
    own = "# ours\n\nThis page is not " + diagram_doc.GENERATED + ".\n"
    (d / "README.md").write_text(own, encoding="utf-8")
    assert diagram_doc.main(["--dir", str(d), "--write"]) == 1
    assert (d / "README.md").read_text(encoding="utf-8") == own


# --- review of PR #375, round 2: freshness by source hash -------------------

def test_a_matching_source_hash_is_a_plain_pass_whatever_the_file_times(tmp_path):
    d = _dir(tmp_path, rendered="clean.svg")
    _age(d / "out" / "process-merge.svg", 600)  # a checkout touched the source after the render
    assert diagram_doc.verdict(str(d), "process-merge.mmd") == (
        "PASS: 8 nodes, no crossings, nothing drawn through a node")


def test_a_different_source_hash_is_out_of_date_even_when_the_render_is_newer(tmp_path):
    d = _dir(tmp_path, rendered="clean.svg")
    (d / "process-merge.mmd").write_text(SOURCE + "  b --> c\n", encoding="utf-8")
    _age(d / "process-merge.mmd", 600)  # the edit keeps an older time (a checkout, a copy)
    assert diagram_doc.verdict(str(d), "process-merge.mmd").startswith("render out of date")


RENDER_SH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "skills", "crew-diagrams",
                         "scripts", "render.sh")
FAKE_MMDC = """#!/usr/bin/env bash
# stands in for mermaid-cli: writes a small file at -o, logs each call
out=""; while [ $# -gt 0 ]; do [ "$1" = -o ] && out="$2"; shift; done
echo "<svg/>" > "$out"; echo "$out" >> "$MMDC_LOG"
"""


# Not shutil.which("bash"): on a Windows runner that is WSL's launcher, which
# exits 1 when no distribution is installed. resolve_bash() proves a bash can
# run a script at a Windows path, and the sha256 tool is looked for by that
# bash, since render.sh is what calls it.
_BASH = crew_fixtures.resolve_bash()


def _bash_has_sha256():
    if _BASH is None:
        return False
    probe = subprocess.run([_BASH, "-c", "command -v sha256sum || command -v shasum"],
                           capture_output=True, check=False)
    return probe.returncode == 0


@pytest.mark.skipif(not _bash_has_sha256(), reason="needs a bash that runs scripts here and a sha256 tool")
def test_render_sh_records_the_source_hash_and_rerenders_on_a_new_one(tmp_path):
    d = _dir(tmp_path)
    tools = tmp_path / "bin"
    tools.mkdir()
    (tools / "mmdc").write_text(FAKE_MMDC, encoding="utf-8", newline="\n")
    os.chmod(tools / "mmdc", 0o755)
    env = dict(os.environ, PATH=f"{tools}{os.pathsep}{os.environ['PATH']}", MMDC_LOG=str(tmp_path / "log"))

    def render():
        subprocess.run([_BASH, RENDER_SH.replace("\\", "/"), str(d).replace("\\", "/"), "--svg-only"],
                       env=env, check=True, capture_output=True)
        return (tmp_path / "log").read_text(encoding="utf-8").count("process-merge")

    assert render() == 1
    src = d / "out" / "process-merge.svg.src"
    assert src.read_text(encoding="utf-8").strip() == diagram_doc.source_hash(str(d / "process-merge.mmd"))
    assert render() == 1  # same hash: skipped
    (d / "process-merge.mmd").write_text(SOURCE + "  b --> c\n", encoding="utf-8")
    _age(d / "process-merge.mmd", 600)  # older than the SVG, so the time rule alone would skip it
    assert render() == 2
    assert src.read_text(encoding="utf-8").strip() == diagram_doc.source_hash(str(d / "process-merge.mmd"))

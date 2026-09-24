"""Two properties CLAUDE.md documents as load-bearing that nothing tested.

Both were found by mutation rather than by reading: each change below left the
ENTIRE crew suite green, exit 0, so the suite could not tell the working code
from the broken code.

1. `reportTracked`. `pm_brief` (deleted in crew 1.0) read it to decide which graph-refresh command
   to recommend, and this repo's CLAUDE.md says the two are NOT interchangeable
   -- `graphify . --no-viz --code-only` skips `GRAPH_REPORT.md`, so in a repo
   that tracks the pair it leaves the two tracked files describing different
   builds. Renaming the key in `crew_state._read_graph` degraded the pulse to
   the form CLAUDE.md forbids and no test noticed, because the only tests
   touching it hand-build a `graph` dict and call `pm_brief.render` -- they
   exercise the CONSUMER and never the PRODUCER.

2. Anchor truncation. CLAUDE.md states that anchor length does not matter
   because BOTH sides are truncated to 7, so 8- and 40-character anchors match
   as exactly as 7-character ones. That sentence is load-bearing: it is what
   tells a reader not to go rewriting correct anchors. The file previously
   claimed the opposite, and was corrected by reading the comparison. Changing
   every `[:7]` to `[:40]` left the whole suite green.

Put the check where the evidence is dropped: these call the producers against
real fixture repos, not the renderers against a literal.
"""

import os
import subprocess
import sys

import context  # noqa: F401  pylint: disable=unused-import
import crew_fixtures
import crew_state


def _git(root, *args):
    return subprocess.run(("git", *args), cwd=root, check=True,
                          capture_output=True, text=True,
                          stdin=subprocess.DEVNULL).stdout.strip()


# --------------------------------------------------------------- reportTracked

def test_report_tracked_is_true_when_the_report_is_tracked(tmp_path):
    """The repo shape CLAUDE.md describes: graph.json and GRAPH_REPORT.md both
    tracked, so the refresh command has to be the one that writes both."""
    root = crew_fixtures.make_repo(tmp_path, graph=True)
    report = os.path.join(root, "graphify-out", "GRAPH_REPORT.md")
    with open(report, "w", encoding="utf-8", newline="\n") as handle:
        handle.write("# Graph report\n")
    _git(root, "add", "graphify-out/GRAPH_REPORT.md")
    _git(root, "commit", "-q", "-m", "track the report")

    graph = crew_state._read_graph(str(root), {})
    assert graph["reportTracked"] is True


def test_report_tracked_is_false_when_there_is_no_report(tmp_path):
    root = crew_fixtures.make_repo(tmp_path, graph=True)
    graph = crew_state._read_graph(str(root), {})
    assert graph["reportTracked"] is False


def test_an_untracked_report_on_disk_does_not_count(tmp_path):
    """The distinction the code comment calls out explicitly: the question is
    asked of git, not of the filesystem.

    An untracked `GRAPH_REPORT.md` is a local artefact somebody's hand-run left
    behind. It does not make maintaining the pair a property of the REPO, and
    if it counted, one stray file would flip crew's recommendation for everyone
    who cloned. This is the case a filesystem check passes and a git check
    fails, so it is the one that pins which of the two is implemented.
    """
    root = crew_fixtures.make_repo(tmp_path, graph=True)
    report = os.path.join(root, "graphify-out", "GRAPH_REPORT.md")
    with open(report, "w", encoding="utf-8", newline="\n") as handle:
        handle.write("# Not committed\n")

    assert os.path.isfile(report)  # present on disk...
    graph = crew_state._read_graph(str(root), {})
    assert graph["reportTracked"] is False  # ...and still not tracked


# ------------------------------------------------------------ anchor truncation

_LENGTHS = (7, 8, 40)


def test_codemap_anchors_match_at_any_length(tmp_path):
    """7, 8 and 40-character anchors all match a HEAD that IS that commit.

    Change either `[:7]` in `read_knowledge` to `[:40]` and the 7 and 8 cases
    still pass while 40 reports behind -- because `head` is read with
    `--short=7`, so truncating to 40 leaves a 7-character string on one side
    and a 40-character one on the other. This is the assertion CLAUDE.md's
    "anchor length does not matter" rests on.
    """
    for length in _LENGTHS:
        root = crew_fixtures.make_repo(tmp_path / f"len{length}", codemap={})
        sha = crew_fixtures.head_sha(root, length=length)
        mapdir = os.path.join(root, ".crew", "codemap")
        with open(os.path.join(mapdir, "sub.md"), "w",
                  encoding="utf-8", newline="\n") as handle:
            handle.write(f"anchor: repo@{sha}\n\n# sub\n")

        knowledge = crew_state.read_knowledge(str(root), {})
        assert "sub" not in knowledge["behind"], (
            f"a {length}-character anchor naming HEAD reported behind; both "
            "sides of the comparison must be truncated to 7"
        )
        assert "sub" not in knowledge["unresolvable"]


def test_codemap_anchor_for_another_commit_is_still_behind(tmp_path):
    """The control. Without this the test above passes on a comparison that
    always returns equal, which would be a worse bug than the one it guards."""
    root = crew_fixtures.make_repo(tmp_path, codemap={})
    first = crew_fixtures.head_sha(root, length=40)
    with open(os.path.join(root, "second.txt"), "w",
              encoding="utf-8", newline="\n") as handle:
        handle.write("move head\n")
    crew_fixtures.commit_file(str(root), "second.txt")

    mapdir = os.path.join(root, ".crew", "codemap")
    with open(os.path.join(mapdir, "sub.md"), "w",
              encoding="utf-8", newline="\n") as handle:
        handle.write(f"anchor: repo@{first}\n\n# sub\n")

    knowledge = crew_state.read_knowledge(str(root), {})
    assert "sub" in knowledge["behind"]


def test_diagram_anchors_match_at_any_length(tmp_path):
    """The same truncation, at the second site.

    `read_diagrams` carries its own copy of the comparison -- CLAUDE.md says to
    grep the expression rather than trust a line number, because both moved
    when `crew_state.py` was split. Two copies means a fix applied to one and
    not the other, so each gets its own case.
    """
    for length in _LENGTHS:
        root = crew_fixtures.make_repo(tmp_path / f"diag{length}")
        sha = crew_fixtures.head_sha(root, length=length)
        diagrams = os.path.join(root, "docs", "diagrams")
        os.makedirs(diagrams, exist_ok=True)
        with open(os.path.join(diagrams, "architecture.mmd"), "w",
                  encoding="utf-8", newline="\n") as handle:
            handle.write(f"%% generated from repo@{sha}\ngraph TD\n  a-->b\n")

        diag = crew_state.read_diagrams(str(root), {})
        assert "architecture" not in diag["behind"], (
            f"a {length}-character diagram anchor naming HEAD reported behind"
        )


def test_diagram_anchor_for_another_commit_is_still_behind(tmp_path):
    """Control for the diagram site, same reason as the codemap one."""
    root = crew_fixtures.make_repo(tmp_path)
    first = crew_fixtures.head_sha(root, length=40)
    with open(os.path.join(root, "second.txt"), "w",
              encoding="utf-8", newline="\n") as handle:
        handle.write("move head\n")
    crew_fixtures.commit_file(str(root), "second.txt")

    diagrams = os.path.join(root, "docs", "diagrams")
    os.makedirs(diagrams, exist_ok=True)
    with open(os.path.join(diagrams, "architecture.mmd"), "w",
              encoding="utf-8", newline="\n") as handle:
        handle.write(f"%% generated from repo@{first}\ngraph TD\n  a-->b\n")

    diag = crew_state.read_diagrams(str(root), {})
    assert "architecture" in diag["behind"]


def test_the_graph_site_is_documented_as_unpinned(tmp_path):
    """The third `[:7]` pair, and the honest result: it is NOT pinned here.

    `_read_graph`'s fast path is `built[:7] == head[:7]`. Change it to `[:40]`
    and a fresh graph does not report stale -- it falls through to the
    deny-list diff, finds nothing changed, and returns `current: True` anyway.
    The mutation costs one git call and changes no output, so no behavioural
    test can catch it, and writing one that appeared to would be worse than
    leaving it uncovered.

    This case therefore asserts only what is true -- a 40-character
    `built_at_commit` at HEAD reads current, by whichever path -- and exists so
    the gap is recorded where someone editing the comparison will see it,
    rather than implied by an absence.
    """
    root = crew_fixtures.make_repo(tmp_path, graph=True, graph_sha="head")
    built = crew_state._read_graph(str(root), {})
    assert len(built["builtAt"]) == 40  # graphify records the full sha
    assert built["current"] is True


def test_module_is_importable_standalone():
    """conftest puts the hook scripts on sys.path; if that stops being true
    these tests would error rather than fail, which reads as infrastructure
    trouble instead of a regression."""
    assert crew_state.__name__ == "crew_state"
    assert any("hooks" in entry for entry in sys.path)

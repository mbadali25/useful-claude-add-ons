"""`knowledgeBehind` and `diagramsStale` had no fixpoint.

Both compared `anchor == HEAD` and nothing else. `.crew/codemap/` and
`docs/diagrams/` are TRACKED, so recording a refresh takes a commit and that
commit moves HEAD past the sha the refresh just wrote -- the map was behind
again the instant it was saved. Refreshing could not clear either trigger, ever,
which is why this repo sat at 10 subsystems behind and 6 diagrams stale no
matter what anyone did about them.

`_read_graph` already had the fix and names the failure in its own comment
("treating it that way gave this trigger NO FIXPOINT"). It was applied to the
graph trigger only; the other two kept the bug.

The tests here are written as BEFORE/AFTER pairs on purpose. A test that only
asserts "current after a refresh" would also pass against a comparison that
returned current for everything, so each case is paired with one proving the
trigger still fires on a real code change. Termination and sensitivity are two
properties and a fix can trade one for the other.
"""

import os
import pathlib
import subprocess

import context  # noqa: F401  pylint: disable=unused-import
import crew_fixtures
import crew_state


def _git(root, *args):
    return subprocess.run(("git", *args), cwd=root, check=True,
                          capture_output=True, text=True,
                          stdin=subprocess.DEVNULL).stdout.strip()


def _write(path, text):
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)


def _refresh_codemap(root, stem="sub"):
    """Write a codemap anchored at HEAD and commit it, as a refresh would."""
    mapdir = os.path.join(root, ".crew", "codemap")
    os.makedirs(mapdir, exist_ok=True)
    head = crew_fixtures.head_sha(root, length=40)
    _write(os.path.join(mapdir, f"{stem}.md"), f"anchor: repo@{head}\n\n# {stem}\n")
    # -f because .crew/ is ignored in the shipping repo; codemap/ is the
    # deliberate exception and is tracked there.
    _git(root, "add", "-f", f".crew/codemap/{stem}.md")
    _git(root, "commit", "-q", "-m", f"refresh {stem}.md")


# ------------------------------------------------------------------- codemaps

def test_committing_a_refresh_does_not_immediately_unrefresh_it(tmp_path):
    """The fixpoint. This is the case that used to be impossible to reach."""
    root = crew_fixtures.make_repo(tmp_path, codemap={})
    _refresh_codemap(root)
    knowledge = crew_state.read_knowledge(str(root), {})
    assert knowledge["behind"] == [], (
        "a codemap anchored at the commit it was verified against reported "
        "behind as soon as the refresh was committed - the trigger has no "
        "fixpoint and refreshing can never clear it"
    )


def test_a_real_code_change_still_reports_behind(tmp_path):
    """Sensitivity. Without this the fix above could be 'always current'."""
    root = crew_fixtures.make_repo(tmp_path, codemap={})
    _refresh_codemap(root)
    _write(os.path.join(root, "app.py"), "value = 1\n")
    crew_fixtures.commit_file(str(root), "app.py")

    knowledge = crew_state.read_knowledge(str(root), {})
    assert knowledge["behind"] == ["sub"]


def test_a_change_only_under_the_deny_list_does_not_stale_a_map(tmp_path):
    """`docs/**`, `.crew/**` and `.work/**` cannot move what a map describes.

    This is what makes the fixpoint hold rather than being a coincidence of
    the previous test: a second commit touching only excluded paths must also
    leave the map current.
    """
    root = crew_fixtures.make_repo(tmp_path, codemap={})
    _refresh_codemap(root)
    os.makedirs(os.path.join(root, "docs"), exist_ok=True)
    _write(os.path.join(root, "docs", "notes.md"), "prose\n")
    crew_fixtures.commit_file(str(root), "docs/notes.md")

    assert crew_state.read_knowledge(str(root), {})["behind"] == []


def test_a_map_is_measured_against_the_paths_it_cites(tmp_path):
    """The narrowing the docstring always described and the code never did.

    A map citing only `owned.py` must not go behind because an unrelated file
    moved. Without this, every map staled on every commit anywhere in the repo,
    which is the same as no signal at all.
    """
    root = crew_fixtures.make_repo(tmp_path, codemap={})
    _write(os.path.join(root, "owned.py"), "value = 1\n")
    _write(os.path.join(root, "unrelated.py"), "value = 1\n")
    crew_fixtures.commit_file(str(root), "owned.py")
    crew_fixtures.commit_file(str(root), "unrelated.py")

    mapdir = os.path.join(root, ".crew", "codemap")
    os.makedirs(mapdir, exist_ok=True)
    head = crew_fixtures.head_sha(root, length=40)
    _write(os.path.join(mapdir, "sub.md"),
           f"anchor: repo@{head}\n\n# sub\n\n## Entry points\n- `owned.py:1`\n")
    _git(root, "add", "-f", ".crew/codemap/sub.md")
    _git(root, "commit", "-q", "-m", "refresh")

    _write(os.path.join(root, "unrelated.py"), "value = 2\n")
    crew_fixtures.commit_file(str(root), "unrelated.py")
    assert crew_state.read_knowledge(str(root), {})["behind"] == [], (
        "a map citing only owned.py went behind because unrelated.py moved"
    )

    _write(os.path.join(root, "owned.py"), "value = 3\n")
    crew_fixtures.commit_file(str(root), "owned.py")
    assert crew_state.read_knowledge(str(root), {})["behind"] == ["sub"], (
        "a map citing owned.py did NOT go behind when owned.py moved"
    )


def test_an_unresolvable_anchor_is_still_its_own_answer(tmp_path):
    """The third value must survive the change.

    `unresolvable` is exclusive of `behind` and decides whether the reader
    re-checks or re-derives. Folding it into `behind` is this repo's named bug,
    so the narrowing must not quietly absorb it.
    """
    root = crew_fixtures.make_repo(tmp_path, codemap={})
    mapdir = os.path.join(root, ".crew", "codemap")
    _write(os.path.join(mapdir, "sub.md"), "anchor: repo@" + "d" * 40 + "\n\n# sub\n")

    knowledge = crew_state.read_knowledge(str(root), {})
    assert knowledge["unresolvable"] == ["sub"]
    assert knowledge["behind"] == []


# ------------------------------------------------------------------- diagrams

def _refresh_diagram(root, stem="architecture"):
    diagrams = os.path.join(root, "docs", "diagrams")
    os.makedirs(diagrams, exist_ok=True)
    head = crew_fixtures.head_sha(root, length=40)
    _write(os.path.join(diagrams, f"{stem}.mmd"),
           f"%% generated from repo@{head}\ngraph TD\n  a-->b\n")
    crew_fixtures.commit_file(str(root), f"docs/diagrams/{stem}.mmd")


def test_committing_a_refreshed_diagram_leaves_it_current(tmp_path):
    """Same fixpoint, second trigger. `docs/**` is in the deny-list precisely
    so saving the re-anchored .mmd does not stale it again."""
    root = crew_fixtures.make_repo(tmp_path)
    _refresh_diagram(root)
    assert crew_state.read_diagrams(str(root), {})["behind"] == []


def test_a_diagram_goes_behind_when_code_moves(tmp_path):
    """Sensitivity for the diagram trigger."""
    root = crew_fixtures.make_repo(tmp_path)
    _refresh_diagram(root)
    _write(os.path.join(root, "app.py"), "value = 1\n")
    crew_fixtures.commit_file(str(root), "app.py")

    assert crew_state.read_diagrams(str(root), {})["behind"] == ["architecture"]


def test_a_diagram_with_no_anchor_is_behind(tmp_path):
    """Unchanged behaviour, asserted so the rewrite cannot drop it. A diagram
    that records nothing cannot be shown current by any comparison."""
    root = crew_fixtures.make_repo(tmp_path)
    diagrams = os.path.join(root, "docs", "diagrams")
    os.makedirs(diagrams, exist_ok=True)
    _write(os.path.join(diagrams, "architecture.mmd"), "graph TD\n  a-->b\n")

    assert crew_state.read_diagrams(str(root), {})["behind"] == ["architecture"]


def test_moved_since_reports_none_rather_than_false_when_it_cannot_tell(tmp_path):
    """`None` is not `False`, and every caller must resolve it to stale.

    An anchor that resolved when written and was later squash-merged away is
    the real case: `git diff` fails outright. If that returned False the map
    would read current forever on the strength of a command that never ran.
    """
    root = crew_fixtures.make_repo(tmp_path)
    head = crew_fixtures.head_sha(root, length=40)
    assert crew_state._moved_since(str(root), "e" * 40, head) is None
    assert crew_state._moved_since(str(root), head, head) is False


def test_cited_paths_ignores_citations_that_no_longer_exist(tmp_path):
    """A rotted citation must narrow nothing.

    If a deleted file stayed in the pathspec, `git diff -- <gone>` reports no
    changes and the map would read current *because* its citation broke -- the
    worst direction, since a broken citation is evidence the map needs work.
    Dropping it falls back to the wider comparison instead.
    """
    root = crew_fixtures.make_repo(tmp_path)
    _write(os.path.join(root, "here.py"), "value = 1\n")
    body = "anchor: repo@" + "f" * 40 + "\n- `here.py:1`\n- `gone.py:9`\n"
    assert crew_state._cited_paths(str(root), body) == ["here.py"]


def test_pathlib_is_not_needed_for_these(tmp_path):
    """Guard against the fixture helpers drifting under these tests."""
    root = crew_fixtures.make_repo(tmp_path)
    assert pathlib.Path(root, ".crew").is_dir()

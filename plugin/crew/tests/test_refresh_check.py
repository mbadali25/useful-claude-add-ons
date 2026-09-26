"""T-0008: the artifacts a ticket's changes reach stay current before done.

    python3 -m pytest plugin/crew/tests/test_refresh_check.py -q

`crew_refresh_check.ticket_freshness` answers, per code map, diagram and code
graph, `fresh`, `stale` or `unknown` -- scoped to the paths THIS ticket changed
(its scope base against the working tree plus untracked files), never to a raw
anchor lag. Each case below builds a real git repository, because the question
is what git answers: whether a cited path moved since an anchor, including an
edit nobody committed yet.

The must-refuse cases (`stale`, `unknown`) and the must-allow case (an anchor
lag caused only by commits outside the cited paths) are both here, and
`sabotage_refresh.py` mutates the check three ways to prove the must-refuse
ones can fail.
"""
import hashlib
import json
import os
import subprocess
import sys

import pytest

import context  # noqa: F401  pylint: disable=unused-import
from crew_fixtures import commit_file, head_sha, make_repo

import crew_refresh_check
import scope_base

_ROOT = context._ROOT  # pylint: disable=protected-access
_CHECK_PY = os.path.join(_ROOT, "hooks", "scripts", "crew_refresh_check.py")
_COMMANDS = os.path.join(_ROOT, "commands")
TICKET = "T-0001"


def _git(root, *args):
    return subprocess.run(("git",) + args, cwd=root, check=True, capture_output=True,
                          text=True, stdin=subprocess.DEVNULL, timeout=30).stdout.strip()


def _write(root, rel, text):
    path = os.path.join(str(root), *rel.split("/"))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)


def _commit(root, rel, text):
    _write(root, rel, text)
    commit_file(root, rel)


def _graphify(_name):
    return "/opt/fake/bin/graphify"


def _no_graphify(_name):
    return None


def _repo(tmp_path):
    """A repo with two source files, a scope base for TICKET at HEAD, and
    nothing refreshed yet. Returns (root, start sha)."""
    root = make_repo(tmp_path)
    _commit(root, "src/app.py", "print('app')\n")
    _commit(root, "src/other.py", "print('other')\n")
    start = head_sha(root, length=40)
    scope_base.record(str(root), TICKET)
    return root, start


def _codemap(root, name, anchor, cites):
    body = f"# {name}\nanchor: {anchor}\n\n" + "".join(f"- `{c}:1` - cited\n" for c in cites)
    _commit(root, f".crew/codemap/{name}.md", body)


def _diagram(root, name, anchor, anchors=None):
    body = f"%% Generated from repo@{anchor} on 2026-09-25.\n"
    if anchors is not None:
        body += "%% Anchors: " + ", ".join(anchors) + "\n"
    body += "flowchart LR\n  a --> b\n"
    _commit(root, f"docs/diagrams/{name}.mmd", body)


def _graph(root, built):
    _write(root, "graphify-out/GRAPH_REPORT.md", "# report\n")
    commit_file(root, "graphify-out/GRAPH_REPORT.md")
    _commit(root, "graphify-out/graph.json",
            json.dumps({"nodes": [], "links": [], "built_at_commit": built}))


def _artifact(result, kind, name):
    for item in result["artifacts"]:
        if item["kind"] == kind and item["name"] == name:
            return item
    raise AssertionError(f"no {kind} {name!r} in {result['artifacts']}")


def _check(root, which=_graphify):
    return crew_refresh_check.ticket_freshness(str(root), TICKET, which=which)


def test_codemap_citing_changed_path_behind_is_stale(tmp_path):
    root, start = _repo(tmp_path)
    _codemap(root, "app", start, ["src/app.py"])
    _commit(root, "src/app.py", "print('changed')\n")

    result = _check(root)

    assert result["status"] == "stale"
    assert _artifact(result, "codemap", "app")["command"] == "/crew:onboard --refresh app"


def test_codemap_refreshed_is_fresh(tmp_path):
    root, start = _repo(tmp_path)
    _codemap(root, "app", start, ["src/app.py"])
    _commit(root, "src/app.py", "print('changed')\n")
    _codemap(root, "app", head_sha(root, length=40), ["src/app.py"])

    result = _check(root)

    assert (result["status"], _artifact(result, "codemap", "app")["status"]) == ("fresh", "fresh")


def test_anchor_lag_outside_cited_paths_is_fresh(tmp_path):
    root, _start = _repo(tmp_path)
    _commit(root, "src/app.py", "print('changed')\n")
    _codemap(root, "app", head_sha(root, length=40), ["src/app.py"])
    _commit(root, "src/other.py", "print('a version bump, say')\n")
    _commit(root, "src/third.py", "print('and another')\n")

    result = _check(root)

    assert result["status"] == "fresh", result


def test_uncommitted_edit_in_cited_path_is_stale(tmp_path):
    root, _start = _repo(tmp_path)
    _commit(root, "src/app.py", "print('changed')\n")
    _codemap(root, "app", head_sha(root, length=40), ["src/app.py"])
    _write(root, "src/app.py", "print('edited, not committed')\n")

    item = _artifact(_check(root), "codemap", "app")

    assert (item["status"], "commit, then refresh" in item["reason"]) == ("stale", True), item


def test_deleted_cited_path_is_stale(tmp_path):
    root, start = _repo(tmp_path)
    _codemap(root, "app", start, ["src/app.py", "src/other.py"])
    _git(root, "rm", "-q", "src/app.py")
    _git(root, "commit", "-q", "-m", "remove app")

    assert _artifact(_check(root), "codemap", "app")["status"] == "stale"


def test_unresolvable_anchor_is_unknown(tmp_path):
    root, _start = _repo(tmp_path)
    _codemap(root, "app", "deadbeef", ["src/app.py"])
    _commit(root, "src/app.py", "print('changed')\n")

    result = _check(root)

    assert (result["status"], _artifact(result, "codemap", "app")["status"]) == ("unknown", "unknown")


def test_codemap_not_citing_a_changed_path_is_out_of_scope(tmp_path):
    root, start = _repo(tmp_path)
    _codemap(root, "app", start, ["src/app.py"])
    _commit(root, "src/other.py", "print('changed')\n")

    result = _check(root)

    assert [a for a in result["artifacts"] if a["kind"] == "codemap"] == []


def test_diagram_behind_is_stale(tmp_path):
    root, start = _repo(tmp_path)
    _diagram(root, "architecture", start[:8], ["src/app.py"])
    _commit(root, "src/app.py", "print('changed')\n")

    item = _artifact(_check(root), "diagram", "architecture")

    assert (item["status"], item["command"]) == ("stale", "/crew:diagram refresh")


def test_diagram_without_anchors_line_in_scope(tmp_path):
    root, start = _repo(tmp_path)
    _diagram(root, "process", start[:8])
    _commit(root, "src/other.py", "print('changed')\n")

    assert _artifact(_check(root), "diagram", "process")["status"] == "stale"


def test_graph_behind_is_stale(tmp_path):
    root, start = _repo(tmp_path)
    _graph(root, start)
    _commit(root, "src/app.py", "print('changed')\n")

    item = _artifact(_check(root), "graph", "graphify-out")

    assert (item["status"], item["command"]) == ("stale", "graphify update .")


def test_graph_rebuilt_after_the_change_is_fresh(tmp_path):
    root, _start = _repo(tmp_path)
    _commit(root, "src/app.py", "print('changed')\n")
    _graph(root, head_sha(root, length=40))

    assert _artifact(_check(root), "graph", "graphify-out")["status"] == "fresh"


def test_graphify_missing_is_unknown(tmp_path):
    root, _start = _repo(tmp_path)
    _commit(root, "src/app.py", "print('changed')\n")
    _graph(root, head_sha(root, length=40))

    item = _artifact(_check(root, which=_no_graphify), "graph", "graphify-out")

    assert (item["status"], "graphify missing" in item["reason"]) == ("unknown", True), item


def test_no_graph_file_is_not_applicable(tmp_path):
    root, _start = _repo(tmp_path)
    _commit(root, "src/app.py", "print('changed')\n")

    assert _artifact(_check(root), "graph", "graphify-out")["status"] == "not applicable"


def test_no_scope_base_is_unknown(tmp_path):
    root = make_repo(tmp_path, git=False)

    result = _check(root)

    assert (result["status"], "no scope base" in result["reason"]) == ("unknown", True), result


def test_documents_never_fresh(tmp_path):
    root, _start = _repo(tmp_path)

    result = _check(root)

    assert (result["status"], result["documents"]) == ("fresh", "not measured")


# --- review round 1 (T-0008-tG6OPn) ---------------------------------------------

def _codemap_body(root, name, anchor, lines):
    _commit(root, f".crew/codemap/{name}.md", f"# {name}\nanchor: {anchor}\n\n" + "".join(lines))


def test_codemap_line_range_citation_is_in_scope(tmp_path):
    root, start = _repo(tmp_path)
    _codemap_body(root, "app", start, ["- `src/app.py:1-3` - cited as a range\n"])
    _commit(root, "src/app.py", "print('changed')\n")

    assert _artifact(_check(root), "codemap", "app")["status"] == "stale"


def test_codemap_dot_directory_citation_is_in_scope(tmp_path):
    root, start = _repo(tmp_path)
    _commit(root, ".github/wf.yml", "on: push\n")
    _codemap_body(root, "ci", start, ["- `.github/wf.yml:1` - the workflow\n"])
    _commit(root, ".github/wf.yml", "on: pull_request\n")

    assert _artifact(_check(root), "codemap", "ci")["status"] == "stale"


def test_a_trailing_slash_prose_mention_is_not_a_citation(tmp_path):
    root, start = _repo(tmp_path)
    _codemap_body(root, "other", start, ["- `src/` is the prefix this map is about\n",
                                         "- `src/other.py:1` - cited\n"])
    _commit(root, "src/app.py", "print('changed')\n")

    assert [a for a in _check(root)["artifacts"] if a["kind"] == "codemap"] == []


def test_codemap_with_no_parseable_citation_is_unknown(tmp_path):
    root, start = _repo(tmp_path)
    _codemap_body(root, "prose", start, ["The app is judged, not cited.\n"])
    _commit(root, "src/app.py", "print('changed')\n")

    item = _artifact(_check(root), "codemap", "prose")

    assert (item["status"], item["refreshable"]) == ("unknown", True), item


def test_fallback_scope_base_on_the_default_branch_is_unknown(tmp_path):
    root = make_repo(tmp_path)
    _git(root, "branch", "-M", "main")
    start = head_sha(root, length=40)
    _codemap(root, "app", start, ["src/app.py"])
    _commit(root, "src/app.py", "print('changed')\n")

    result = _check(root)

    assert (result["status"], "(fallback)" in result["reason"]) == ("unknown", True), result


def test_fallback_base_on_a_branch_ahead_of_main_is_judged_and_marked(tmp_path):
    root = make_repo(tmp_path)
    _git(root, "branch", "-M", "main")
    _commit(root, "src/app.py", "print('app')\n")
    _codemap(root, "app", head_sha(root, length=40), ["src/app.py"])
    _git(root, "checkout", "-q", "-b", "feature")
    _commit(root, "src/app.py", "print('changed on the branch')\n")

    result = _check(root)
    item = _artifact(result, "codemap", "app")

    assert (result["status"], item["status"], item["reason"].endswith("[fallback base]")) == (
        "stale", "stale", True), result


def test_a_library_call_never_rewrites_the_index(tmp_path, monkeypatch):
    root, start = _repo(tmp_path)
    _codemap(root, "app", start, ["src/app.py"])
    _commit(root, "src/app.py", "print('changed')\n")
    app = os.path.join(str(root), "src", "app.py")
    later = os.stat(app).st_mtime + 5
    os.utime(app, (later, later))
    index = os.path.join(str(root), ".git", "index")
    before = (os.stat(index).st_mtime_ns, _sha(index))
    monkeypatch.delenv("GIT_OPTIONAL_LOCKS", raising=False)

    _check(root)

    assert (os.stat(index).st_mtime_ns, _sha(index)) == before


def _sha(path):
    with open(path, "rb") as handle:
        return hashlib.sha256(handle.read()).hexdigest()


def test_untracked_cited_file_is_stale(tmp_path):
    root, start = _repo(tmp_path)
    _codemap(root, "app", start, ["src/app.py", "src/new.py"])
    _write(root, "src/new.py", "print('new, never added')\n")

    item = _artifact(_check(root), "codemap", "app")

    assert (item["status"], "commit, then refresh" in item["reason"]) == ("stale", True), item


def test_diagram_refreshed_is_fresh(tmp_path):
    root, start = _repo(tmp_path)
    _diagram(root, "architecture", start[:8], ["src/app.py"])
    _commit(root, "src/app.py", "print('changed')\n")
    _diagram(root, "architecture", head_sha(root, length=8), ["src/app.py"])

    assert _artifact(_check(root), "diagram", "architecture")["status"] == "fresh"


def test_release_bookkeeping_alone_stales_nothing(tmp_path):
    root, _start = _repo(tmp_path)
    _commit(root, "CHANGELOG.md", "# Changelog\n")
    _commit(root, "plugin/x/.claude-plugin/plugin.json", '{"version": "1.0.0"}\n')
    base = head_sha(root, length=40)
    _codemap(root, "release", base, ["CHANGELOG.md", "plugin/x/.claude-plugin/plugin.json"])
    _graph(root, base)
    scope_base.record(str(root), "T-0002")
    _commit(root, "CHANGELOG.md", "# Changelog\n\n## 1.0.1\n")
    _commit(root, "plugin/x/.claude-plugin/plugin.json", '{"version": "1.0.1"}\n')

    result = crew_refresh_check.ticket_freshness(str(root), "T-0002", which=_graphify)

    assert (result["status"], result["artifacts"]) == ("fresh", []), result


def test_diagram_anchors_naming_a_directory_reach_files_under_it(tmp_path):
    root, start = _repo(tmp_path)
    _diagram(root, "arch", start[:8], ["src/"])
    _commit(root, "src/app.py", "print('changed')\n")

    assert _artifact(_check(root), "diagram", "arch")["status"] == "stale"


def test_graph_without_a_tracked_report_names_the_code_only_build(tmp_path):
    root, start = _repo(tmp_path)
    _commit(root, "graphify-out/graph.json",
            json.dumps({"nodes": [], "links": [], "built_at_commit": start}))
    _commit(root, "src/app.py", "print('changed')\n")

    item = _artifact(_check(root), "graph", "graphify-out")

    assert item["command"] == "graphify . --no-viz --code-only", item


def test_an_anchor_naming_no_commit_is_refreshable(tmp_path):
    root, _start = _repo(tmp_path)
    _codemap(root, "app", "deadbeef", ["src/app.py"])
    _commit(root, "src/app.py", "print('changed')\n")

    done = _run_cli(root, "--ticket", TICKET)

    assert "refresh with /crew:onboard --refresh app" in done.stdout, done.stdout


def test_graphify_missing_is_a_stop_not_a_refresh(tmp_path):
    root, _start = _repo(tmp_path)
    _commit(root, "src/app.py", "print('changed')\n")
    _graph(root, head_sha(root, length=40))
    result = _check(root, which=_no_graphify)

    line = [x for x in crew_refresh_check._render(TICKET, result).splitlines()  # pylint: disable=protected-access
            if x.startswith("  graph ")][0]

    assert ("refresh with" in line, "stop" in line) == (False, True), line


def _approved_paths(root, cfg=None):
    if cfg is not None:
        _write(root, ".crew/config.json", json.dumps(cfg))
    return crew_refresh_check.refresh_artifact_paths(str(root))


def test_refresh_artifact_paths_default_to_the_four_documented_dirs(tmp_path):
    root, _start = _repo(tmp_path)

    assert _approved_paths(root) == [".crew/codemap", "docs/diagrams", "graphify-out",
                                     ".claude/rules"]


def test_refresh_artifact_paths_follow_the_configured_dirs(tmp_path):
    root, _start = _repo(tmp_path)

    paths = _approved_paths(root, {"docs": {"diagramsDir": "design/mmd"},
                                   "graph": {"out": "out/graph"}})

    assert paths == [".crew/codemap", "design/mmd", "out/graph", ".claude/rules"]


def test_a_configured_dir_naming_the_repo_root_is_never_an_artifact_dir(tmp_path):
    root, _start = _repo(tmp_path)

    paths = _approved_paths(root, {"docs": {"diagramsDir": "."}, "graph": {"out": "./"}})

    assert paths == [".crew/codemap", ".claude/rules"]


def test_an_artifact_dir_reached_through_a_link_is_dropped(tmp_path):
    root, _start = _repo(tmp_path)
    os.makedirs(os.path.join(str(root), ".crew"), exist_ok=True)
    os.symlink(os.path.join(str(root), "src"), os.path.join(str(root), ".crew", "codemap"))

    paths = _approved_paths(root)

    assert (".crew/codemap" in paths, "src" in paths) == (False, False), paths


@pytest.mark.parametrize("rel,expected", [
    (".crew/codemap/crew.md", True),
    ("docs/diagrams/sub/a.mmd", True),
    (".crew/codemapX/crew.md", False),
    ("docs/diagrams-old/a.mmd", False),
    ("other/.crew/codemap/crew.md", False),
    (".crew/codemap/../config.json", False),
    (".crew/codemap/../../src/app.py", False),
    (".crew/codemap", False),
    ("src/app.py", False),
    (".CREW/codemap/crew.md", os.path.normcase("A") == "a"),
])
def test_is_refresh_artifact_matches_whole_segments_only(rel, expected):
    dirs = [".crew/codemap", "docs/diagrams", "graphify-out", ".claude/rules", "**"]

    assert crew_refresh_check.is_refresh_artifact(rel, dirs) is expected


def test_implement_runs_a_refreshable_unknown_and_stops_on_the_rest():
    step = _section(_read("implement.md"), "## 6.")

    assert ("names no commit" in step, "An `unknown` line is a stop" in step,
            "missing tool" in step) == (True, False, True)


def _run_cli(root, *extra):
    env = dict(os.environ, PATH=os.environ.get("PATH", ""), PYTHONDONTWRITEBYTECODE="1")
    return subprocess.run([sys.executable, _CHECK_PY, "--root", str(root), *extra],
                          capture_output=True, text=True, check=False, env=env,
                          stdin=subprocess.DEVNULL, timeout=60)


def _tree_digest(root):
    digest = {}
    for folder, _dirs, files in os.walk(str(root)):
        for name in files:
            path = os.path.join(folder, name)
            with open(path, "rb") as handle:
                digest[os.path.relpath(path, str(root))] = hashlib.sha256(handle.read()).hexdigest()
    return digest


def test_check_writes_nothing(tmp_path):
    root, start = _repo(tmp_path)
    _codemap(root, "app", start, ["src/app.py"])
    _write(root, "src/app.py", "print('edited, not committed')\n")
    before = _tree_digest(root)

    done = _run_cli(root, "--ticket", TICKET, "--json")

    assert (done.returncode, _tree_digest(root)) == (1, before), done.stderr


def test_cli_names_the_stale_artifact_and_its_command(tmp_path):
    root, start = _repo(tmp_path)
    _codemap(root, "app", start, ["src/app.py"])
    _commit(root, "src/app.py", "print('changed')\n")

    done = _run_cli(root, "--ticket", TICKET)

    assert (done.returncode, "/crew:onboard --refresh app" in done.stdout) == (1, True), done.stdout


def test_cli_fresh_exits_zero_and_reports_documents_not_measured(tmp_path):
    root, _start = _repo(tmp_path)

    done = _run_cli(root, "--ticket", TICKET)

    assert (done.returncode, "documents: not measured" in done.stdout) == (0, True), done.stdout


def test_cli_usage_error_exits_two(tmp_path):
    root, _start = _repo(tmp_path)

    assert _run_cli(root, "--ticket", "../escape").returncode == 2


def _read(name):
    with open(os.path.join(_COMMANDS, name), encoding="utf-8") as handle:
        return handle.read()


def _section(text, heading):
    start = text.index(heading)
    end = text.find("\n## ", start + len(heading))
    return text[start:] if end == -1 else text[start:end]


def test_implement_refreshes_between_docs_and_review():
    step = _section(_read("implement.md"), "## 6.")
    marks = ["/crew:docs", "crew_refresh_check.py --root . --ticket $1", "/crew:review $1"]

    positions = [step.find(mark) for mark in marks]

    assert -1 not in positions and positions == sorted(positions), dict(zip(marks, positions))


_REFRESH_COMMANDS = ("/crew:onboard", "/crew:diagram", "graphify")


def _fenced(text):
    return "".join(text.split("```")[1::2])


def test_done_check_4_never_runs_a_refresh_command():
    check = _section(_read("done.md"), "## Check 4")

    ran = [c for c in _REFRESH_COMMANDS if c in _fenced(check)]

    assert ("crew_refresh_check.py --root . --ticket \"$1\"" in _fenced(check),
            "do not run the refresh here" in check.lower(), ran) == (True, True, [])


def test_every_refresh_sabotage_anchor_is_present_exactly_once():
    """An edit that moves a line a mutation aims at would otherwise leave that
    mutation testing nothing until somebody paid for a full sabotage run."""
    import sabotage_refresh  # pylint: disable=import-outside-toplevel

    lost = []
    for label, target, find, _replace, _test in sabotage_refresh.REFRESH_MUTATIONS:
        with open(target, encoding="utf-8", newline="") as handle:
            if handle.read().count(find) != 1:
                lost.append(label)

    assert not lost, lost


# --- review round 2 (T-0008-TPCCYg) ---------------------------------------------

def _on_main_with_a_map(tmp_path):
    """A repo on `main`, no scope record, with a code map for src/app.py
    anchored at the commit that added it. Returns (root, anchor)."""
    root = make_repo(tmp_path)
    _git(root, "branch", "-M", "main")
    _commit(root, "src/app.py", "print('app')\n")
    anchor = head_sha(root, length=40)
    _codemap(root, "app", anchor, ["src/app.py"])
    return root, anchor


def test_fallback_on_main_with_pushed_commits_is_unknown(tmp_path):
    root, _anchor = _on_main_with_a_map(tmp_path)
    _commit(root, "src/app.py", "print('changed')\n")
    _git(root, "update-ref", "refs/remotes/origin/main", "HEAD")
    _commit(root, "src/other.py", "print('unrelated')\n")

    result = _check(root)

    assert (result["status"], f"may hide {TICKET}'s commits" in result["reason"]) == (
        "unknown", True), result


def test_fallback_after_a_fast_forward_into_main_is_unknown(tmp_path):
    root, _anchor = _on_main_with_a_map(tmp_path)
    _git(root, "checkout", "-q", "-b", "feature")
    _write(root, "src/app.py", "print('changed')\n")
    commit_file(root, "src/app.py", f"{TICKET}: change the app")
    _git(root, "branch", "-f", "main", "feature")
    _commit(root, "src/other.py", "print('a follow-up')\n")

    result = _check(root)

    assert (result["status"], f"may hide {TICKET}'s commits" in result["reason"]) == (
        "unknown", True), result


def test_fallback_on_a_branch_whose_ticket_commits_are_ahead_of_main_is_judged(tmp_path):
    root, _anchor = _on_main_with_a_map(tmp_path)
    _write(root, "README.md", "fixture, amended\n")
    commit_file(root, "README.md", "T-00012: another ticket, behind the base")
    _git(root, "checkout", "-q", "-b", "feature")
    _write(root, "src/app.py", "print('changed')\n")
    commit_file(root, "src/app.py", f"{TICKET}: change the app")

    result = _check(root)

    assert (result["status"], result["base_source"],
            _artifact(result, "codemap", "app")["reason"].endswith("[fallback base]")) == (
        "stale", "merge-base", True), result


def test_a_recorded_base_says_so_in_the_result(tmp_path):
    root, _start = _repo(tmp_path)

    done = _run_cli(root, "--ticket", TICKET, "--json")

    assert json.loads(done.stdout)["base_source"] == "record", done.stdout


def test_fallback_with_a_detached_head_is_unknown(tmp_path):
    root, _anchor = _on_main_with_a_map(tmp_path)
    _git(root, "checkout", "-q", "-b", "feature")
    _commit(root, "src/app.py", "print('changed')\n")
    _git(root, "checkout", "-q", "--detach")

    assert _check(root)["status"] == "unknown"


def test_hides_case_renders_a_stop_on_the_top_line(tmp_path):
    root, _anchor = _on_main_with_a_map(tmp_path)
    _commit(root, "src/app.py", "print('changed')\n")
    result = _check(root)

    top = crew_refresh_check._render(TICKET, result).splitlines()[0]  # pylint: disable=protected-access

    assert top == f"refresh-check {TICKET}: unknown - {result['reason']}; stop - {result['stop']}", top


def test_nothing_measured_renders_not_measured_and_a_stop(tmp_path):
    root = make_repo(tmp_path, git=False)
    result = _check(root)

    lines = crew_refresh_check._render(TICKET, result).splitlines()  # pylint: disable=protected-access

    assert lines == [
        f"refresh-check {TICKET}: unknown - {result['reason']}; stop - no scope base",
        "  not measured - no scope base",
        "  documents: not measured - /crew:docs is judgement",
    ], lines


@pytest.mark.parametrize("status,shown", [("fresh", True), ("stale", True), ("unknown", False)])
def test_no_codemap_cites_line_only_when_fresh_or_stale(status, shown):
    result = {"status": status, "reason": "r", "artifacts": [], "documents": "not measured",
              "stop": "s" if status == "unknown" else None}

    text = crew_refresh_check._render(TICKET, result)  # pylint: disable=protected-access

    assert ("no codemap, diagram or graph cites" in text) is shown, text


def _todo_map(tmp_path):
    root, _start = _repo(tmp_path)
    _commit(root, "TODO.md", "# TODO\n")
    base = head_sha(root, length=40)
    _codemap(root, "todo", base, ["TODO.md", "src/app.py"])
    scope_base.record(str(root), "T-0002")
    return root


def test_filing_a_todo_item_alone_stales_nothing(tmp_path):
    root = _todo_map(tmp_path)
    _commit(root, "TODO.md", "# TODO\n\n- a finding\n")

    result = crew_refresh_check.ticket_freshness(str(root), "T-0002", which=_graphify)

    assert (result["status"], [a for a in result["artifacts"] if a["kind"] == "codemap"]) == (
        "fresh", []), result


def test_a_code_change_cited_beside_todo_still_stales_the_map(tmp_path):
    root = _todo_map(tmp_path)
    _commit(root, "TODO.md", "# TODO\n\n- a finding\n")
    _commit(root, "src/app.py", "print('changed')\n")

    item = _artifact(crew_refresh_check.ticket_freshness(str(root), "T-0002", which=_graphify),
                     "codemap", "todo")

    assert (item["status"], item["reason"].startswith("src/app.py changed")) == ("stale", True), item


@pytest.mark.skipif(os.name == "nt", reason='Windows forbids `"` in a file name')
def test_an_untracked_file_git_would_quote_stales_the_graph(tmp_path):
    root, start = _repo(tmp_path)
    _graph(root, start)
    _write(root, 'src/we"ird.py', "print('untracked')\n")

    item = _artifact(_check(root), "graph", "graphify-out")

    assert item["status"] == "stale", item


def _unlistable(monkeypatch, root, rel):
    target = os.path.normcase(os.path.join(str(root), *rel.split("/")))
    real = os.listdir

    def listdir(path="."):
        if os.path.normcase(str(path)) == target:
            raise PermissionError(13, "Permission denied", str(path))
        return real(path)

    monkeypatch.setattr(crew_refresh_check.os, "listdir", listdir)


@pytest.mark.parametrize("kind,rel", [("codemap", ".crew/codemap"), ("diagram", "docs/diagrams")])
def test_an_unlistable_artifact_dir_is_unknown(tmp_path, monkeypatch, kind, rel):
    root, start = _repo(tmp_path)
    _codemap(root, "app", start, ["src/app.py"])
    _diagram(root, "arch", start[:8], ["src/app.py"])
    _commit(root, "src/app.py", "print('changed')\n")
    _unlistable(monkeypatch, root, rel)

    result = _check(root)
    item = _artifact(result, kind, rel)

    assert (result["status"], item["status"], item["refreshable"]) == (
        "unknown", "unknown", False), result


@pytest.mark.skipif(os.name == "nt", reason="chmod 000 does not deny a directory listing on Windows")
@pytest.mark.skipif(getattr(os, "geteuid", lambda: 1)() == 0,
                    reason="root reads a chmod 000 directory anyway, so nothing is denied")
def test_a_chmod_000_codemap_dir_is_unknown(tmp_path):
    root, start = _repo(tmp_path)
    _codemap(root, "app", start, ["src/app.py"])
    _commit(root, "src/app.py", "print('changed')\n")
    mapdir = os.path.join(str(root), ".crew", "codemap")
    os.chmod(mapdir, 0)
    try:
        result = _check(root)
    finally:
        os.chmod(mapdir, 0o755)

    assert result["status"] == "unknown", result


def test_an_unreadable_codemap_is_unknown(tmp_path, monkeypatch):
    root, start = _repo(tmp_path)
    _codemap(root, "app", start, ["src/app.py"])
    _commit(root, "src/app.py", "print('changed')\n")
    real = crew_refresh_check.read_text
    monkeypatch.setattr(crew_refresh_check, "read_text",
                        lambda p: None if p.endswith("app.md") else real(p))

    item = _artifact(_check(root), "codemap", "app")

    assert (item["status"], item["refreshable"]) == ("unknown", False), item


@pytest.mark.parametrize("name,text", [
    ("crew.json", '{"docs": {"diagramsDir": "design"'),
    ("config.json", '{"docs": {"diagramsDir": "design"'),
    ("crew.json", '["docs"]'),
], ids=["crew-json-truncated", "config-json-truncated", "crew-json-not-an-object"])
def test_a_corrupt_config_is_unknown_not_the_defaults(tmp_path, name, text):
    root, start = _repo(tmp_path)
    _commit(root, f".crew/{name}", json.dumps({"docs": {"diagramsDir": "design"}}))
    _commit(root, "design/arch.mmd", f"%% Generated from repo@{start[:8]} on 2026-09-25.\n"
            "%% Anchors: src/app.py\nflowchart LR\n  a --> b\n")
    _commit(root, "src/app.py", "print('changed')\n")
    _write(root, f".crew/{name}", text)

    result = _check(root)

    assert (result["status"], "config unreadable" in result["reason"]) == ("unknown", True), result


def test_an_unreadable_config_is_not_skipped_for_the_next_one(tmp_path, monkeypatch):
    root, _start = _repo(tmp_path)
    _commit(root, ".crew/crew.json", json.dumps({"docs": {"diagramsDir": "design"}}))
    real = crew_refresh_check.read_text
    monkeypatch.setattr(crew_refresh_check, "read_text",
                        lambda p: None if p.endswith("crew.json") else real(p))

    assert _check(root)["status"] == "unknown"


def test_implement_commits_the_refresh_before_review_and_stops_on_the_top_line():
    step = " ".join(_section(_read("implement.md"), "## 6.").split())

    assert ("Commit the refresh before `/crew:review $1` builds its bundle" in step,
            "on the top line" in step) == (True, True), step


def test_fallback_equal_to_head_on_a_fresh_branch_is_unknown(tmp_path):
    root, _anchor = _on_main_with_a_map(tmp_path)
    _commit(root, "src/app.py", "print('changed')\n")
    _git(root, "checkout", "-q", "-b", "feature")

    result = _check(root)

    assert (result["status"], result["stop"]) == (
        "unknown", "the fallback scope base hides the change"), result

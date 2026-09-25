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

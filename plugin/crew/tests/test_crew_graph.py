"""L-0667: `/crew:graph` - one-line status, the sanctioned refresh, the pair check.

    python3 -m pytest plugin/crew/tests/test_crew_graph.py -q

`crew_graph.py status` is read-only. `crew_graph.py refresh` refuses before it
builds (graphify missing, a denylisted file uncovered or uncertain), runs the
sanctioned graphify line, and then proves the tracked pair agrees: a mismatch
is a failure (exit 1) and anything it cannot read is could-not-tell (exit 2),
never agree. Every case builds a throwaway repository under tmp_path, and the
graphify run is a stand-in that writes a fixture graph and report: no case runs
the real tool or touches this repository's `graphify-out/`.
"""
import hashlib
import json
import os
import subprocess
import sys

import pytest

import context  # noqa: F401  pylint: disable=unused-import
from crew_fixtures import commit_file, head_sha, make_repo

import crew_graph

_SCRIPT = os.path.join(context._ROOT, "hooks", "scripts",  # pylint: disable=protected-access
                       "crew_graph.py")
# graphify's own line, copied from a real GRAPH_REPORT.md.
_SUMMARY = "- {n} nodes \u00b7 {e} edges \u00b7 3 communities (3 shown, 0 thin omitted)"


def _git(root, *args):
    return subprocess.run(("git",) + args, cwd=root, check=True, capture_output=True,
                          text=True, stdin=subprocess.DEVNULL, timeout=30).stdout


def _write(root, rel, text):
    path = os.path.join(str(root), *rel.split("/"))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)


def _report(nodes, edges, summary=True):
    body = "# Graph Report\n\n## Corpus Check\n- 2 files\n\n"
    if summary:
        body += "## Summary\n" + _SUMMARY.format(n=nodes, e=edges) + "\n- Extraction: 100%\n\n"
    return body + "## God Nodes\n- app\n"


def _graph_json(nodes, links, built, key="links"):
    graph = {"nodes": [{"id": f"n{i}"} for i in range(nodes)],
             key: [{"source": "n0", "target": "n0"} for _ in range(links)]}
    if built:
        graph["built_at_commit"] = built
    return json.dumps(graph)


def _repo(tmp_path, graph=True, tracked=True):
    """A repo with code and, optionally, a graph pair built at the code's
    commit (fresh, agreeing) - the report committed when `tracked`."""
    root = make_repo(tmp_path)
    _write(root, "src/app.py", "print('app')\n")
    commit_file(root, "src/app.py")
    if graph:
        _write(root, "graphify-out/graph.json", _graph_json(3, 2, head_sha(root, length=40)))
        _write(root, "graphify-out/GRAPH_REPORT.md", _report(3, 2))
        commit_file(root, "graphify-out/graph.json")
        if tracked:
            commit_file(root, "graphify-out/GRAPH_REPORT.md")
    return str(root)


class _Tool:
    """A stand-in graphify run: records each command and writes the pair it
    is told to, then exits with `code` and prints `output`."""

    def __init__(self, nodes=4, links=3, report=(4, 3), built=True, code=0, output="",
                 graph_text=None, summary=True, key="links"):
        self.calls = []
        self.spec = dict(nodes=nodes, links=links, report=report, built=built, code=code,
                         output=output, graph_text=graph_text, summary=summary, key=key)

    def __call__(self, command, top):
        self.calls.append(command)
        spec = self.spec
        if spec["code"] == 0:
            built = (spec["built"] if isinstance(spec["built"], str)
                     else head_sha(top, length=40) if spec["built"] else None)
            text = spec["graph_text"] if spec["graph_text"] is not None else _graph_json(
                spec["nodes"], spec["links"], built, spec["key"])
            _write(top, "graphify-out/graph.json", text)
            _write(top, "graphify-out/GRAPH_REPORT.md", _report(*spec["report"], spec["summary"]))
        return spec["code"], spec["output"]


def _graphify(_name):
    return "/opt/fake/bin/graphify"


def _refresh(root, tool, which=_graphify):
    lines = []
    code = crew_graph.refresh(root, which=which, run=tool, out=lines.append)
    return code, "\n".join(lines)


def _status(root, capsys):
    code = crew_graph.main(["status", "--root", root])
    return code, capsys.readouterr().out


def _porcelain(root):
    return _git(root, "status", "--porcelain", "--untracked-files=all")


# --- status ---------------------------------------------------------------------------

def test_status_is_one_line_and_read_only(tmp_path, capsys):
    root = _repo(tmp_path)
    built = _git(root, "rev-parse", "HEAD~2").strip()[:12]  # the pair is committed on top
    before = _porcelain(root)

    code, out = _status(root, capsys)

    assert (code, out, _porcelain(root)) == (
        0, f"graph=fresh built_at={built} pair=agree ignore=covered command=graphify update .\n",
        before)


def test_status_absent_and_untracked(tmp_path, capsys):
    absent = _repo(tmp_path / "a", graph=False)
    untracked = _repo(tmp_path / "b", tracked=False)

    first = _status(absent, capsys)[1]
    second = _status(untracked, capsys)[1]

    assert ("graph=absent" in first, "pair=untracked" in second,
            second.rstrip("\n").endswith("command=graphify . --no-viz --code-only")) == \
        (True, True, True), (first, second)


def test_status_names_a_disagreeing_pair(tmp_path, capsys):
    root = _repo(tmp_path)
    _write(root, "graphify-out/GRAPH_REPORT.md", _report(10, 2))

    assert "pair=disagree" in _status(root, capsys)[1]


def _manifest(root, rel):
    """graphify's manifest.json recording `rel`'s current bytes, git-ignored
    through .git/info/exclude as the refresh check's tests do."""
    with open(os.path.join(root, ".git", "info", "exclude"), "a", encoding="utf-8") as handle:
        handle.write("graphify-out/manifest.json\n")
    with open(os.path.join(root, *rel.split("/")), "rb") as handle:
        digest = hashlib.md5(handle.read(), usedforsecurity=False).hexdigest()
    _write(root, "graphify-out/manifest.json", json.dumps(
        {rel: {"mtime": 0, "seen": 0, "ast_hash": digest, "semantic_hash": ""}}))


def test_status_is_fresh_when_the_manifest_confirms_an_unchanged_topology(tmp_path, capsys):
    """Review round 1: graphify leaves graph.json and its sha alone when the
    topology did not change; status reads the refresh check's manifest rule."""
    root = _repo(tmp_path)
    _write(root, "src/app.py", "print('same topology')\n")
    commit_file(root, "src/app.py")
    stale = _status(root, capsys)[1]
    _manifest(root, "src/app.py")

    assert ("graph=stale" in stale, "graph=fresh" in _status(root, capsys)[1]) == (True, True)


def test_status_reads_a_report_git_cannot_list_as_unknown(tmp_path, capsys, monkeypatch):
    """`_read_graph` reads a failed `ls-files` as untracked; status must not."""
    root = _repo(tmp_path)
    real = crew_graph._git  # pylint: disable=protected-access

    def failing(cwd, *args):
        return None if args[:1] == ("ls-files",) else real(cwd, *args)

    monkeypatch.setattr(crew_graph, "_git", failing)
    line = _status(root, capsys)[1]

    assert ("pair=unknown" in line, line.rstrip("\n").endswith("command=unknown")) == \
        (True, True), line


# --- refresh: must-allow ----------------------------------------------------------------

def test_refresh_runs_the_sanctioned_command_and_verifies(tmp_path):
    root = _repo(tmp_path)
    head = head_sha(root, length=40)
    tool = _Tool()

    code, out = _refresh(root, tool)

    assert (code, tool.calls, head_sha(root, length=40)) == (0, ["graphify update ."], head), out
    assert "pair=agree" in out and "changed: graphify-out/graph.json" in out \
        and "changed: graphify-out/GRAPH_REPORT.md" in out and "not committed" in out, out


def test_refresh_without_a_tracked_report_runs_the_code_only_build(tmp_path):
    root = _repo(tmp_path, tracked=False)
    tool = _Tool(report=(99, 99))  # an untracked report is not compared

    code, out = _refresh(root, tool)

    assert (code, tool.calls) == (0, ["graphify . --no-viz --code-only"]), out
    assert "pair=untracked" in out, out


# --- refresh: must-block ----------------------------------------------------------------

def test_refresh_graphify_missing_exits_2(tmp_path):
    root = _repo(tmp_path)
    tool = _Tool()

    code, out = _refresh(root, tool, which=lambda _name: None)

    assert (code, tool.calls, "graphify missing" in out) == (2, [], True), out


def test_refresh_uncovered_denylisted_file_exits_1(tmp_path):
    root = _repo(tmp_path)
    _write(root, ".env", "PASSWORD=x\n")
    commit_file(root, ".env")
    tool = _Tool()

    code, out = _refresh(root, tool)

    assert (code, tool.calls, ".env" in out, "crew_graph_ignore.py --write" in out) == \
        (1, [], True, True), out


def test_refresh_unknown_coverage_exits_2(tmp_path):
    root = _repo(tmp_path)
    _write(root, "sub/.graphifyignore", "!.env\n")  # a nested ignore file is unknown
    commit_file(root, "sub/.graphifyignore")
    tool = _Tool()

    code, out = _refresh(root, tool)

    assert (code, tool.calls, "coverage could not be told" in out) == (2, [], True), out


def test_refresh_tool_failure_exits_1_with_its_output(tmp_path):
    root = _repo(tmp_path)
    tool = _Tool(code=3, output="graphify: boom\nsecond line\n")

    code, out = _refresh(root, tool)

    assert (code, len(tool.calls), "graphify: boom\nsecond line" in out) == (1, 1, True), out


def test_refresh_graph_without_built_at_commit_exits_2(tmp_path):
    root = _repo(tmp_path)
    tool = _Tool(built=False)

    code, out = _refresh(root, tool)

    assert (code, len(tool.calls), "built_at_commit" in out) == (2, 1, True), out


def test_refresh_that_leaves_the_graph_stale_exits_2(tmp_path):
    """Review round 4: graphify exiting 0 over a graph that still predates the
    code (a no-op) is not a refresh."""
    root = _repo(tmp_path)
    old = _git(root, "rev-parse", "HEAD~2").strip()
    _write(root, "src/app.py", "print('changed')\n")
    commit_file(root, "src/app.py")
    tool = _Tool(built=old)

    code, out = _refresh(root, tool)

    assert (code, len(tool.calls), "the graph is stale" in out) == (2, 1, True), out


def test_refresh_node_count_disagreement_exits_1(tmp_path):
    root = _repo(tmp_path)
    tool = _Tool(nodes=9, links=3, report=(10, 3))

    code, out = _refresh(root, tool)

    assert (code, len(tool.calls), "pair=disagree" in out) == (1, 1, True), out
    assert "report 10 nodes / 3 edges, graph.json 9 nodes / 3 links" in out, out


def test_refresh_link_count_disagreement_exits_1(tmp_path):
    root = _repo(tmp_path)
    tool = _Tool(nodes=4, links=3, report=(4, 5))

    code, out = _refresh(root, tool)

    assert (code, "pair=disagree" in out) == (1, True), out


def test_refresh_report_without_summary_line_exits_2(tmp_path):
    root = _repo(tmp_path)
    tool = _Tool(summary=False)

    code, out = _refresh(root, tool)

    assert (code, "pair=unknown" in out) == (2, True), out


def test_refresh_graph_that_is_not_json_exits_2(tmp_path):
    root = _repo(tmp_path)
    tool = _Tool(graph_text='{"nodes": [], "built_at_commit": "0123456789abcdef0123'
                            '456789abcdef01234567", ')

    code, out = _refresh(root, tool)

    assert (code, "pair=unknown" in out or "built_at_commit" in out) == (2, True), out


def test_refresh_graph_with_edges_and_no_links_exits_2(tmp_path):
    root = _repo(tmp_path)
    tool = _Tool(key="edges", report=(4, 0))  # zero links would "agree" with 0 edges

    code, out = _refresh(root, tool)

    assert (code, "no 'links' list" in out) == (2, True), out


def test_refresh_report_git_cannot_list_exits_2(tmp_path, monkeypatch):
    root = _repo(tmp_path)
    tool = _Tool(report=(99, 99))
    real = crew_graph._git  # pylint: disable=protected-access

    def failing(cwd, *args):
        return None if args[:1] == ("ls-files",) else real(cwd, *args)

    monkeypatch.setattr(crew_graph, "_git", failing)

    code, out = _refresh(root, tool)

    assert (code, tool.calls, "nothing built" in out) == (2, [], True), out


def test_refresh_on_windows_reads_a_missing_graphify_from_the_route(tmp_path):
    """Review round 2: the job may run in WSL, whose PATH is not the host's,
    so the host's `which` is not asked; the route's exit 127 is graphify missing."""
    root = _repo(tmp_path)
    tool = _Tool(code=127, output="bash: line 1: graphify: command not found\n")
    lines = []

    code = crew_graph.refresh(root, which=lambda _name: None, run=tool, out=lines.append,
                              windows=True)

    assert (code, len(tool.calls), "graphify missing" in "\n".join(lines)) == (2, 1, True), lines


def test_refresh_on_windows_runs_graphify_only_the_route_has(tmp_path):
    root = _repo(tmp_path)
    tool = _Tool()
    lines = []

    code = crew_graph.refresh(root, which=lambda _name: None, run=tool, out=lines.append,
                              windows=True)

    assert (code, tool.calls) == (0, ["graphify update ."]), lines


def test_refresh_never_stages_or_commits(tmp_path):
    root = _repo(tmp_path)
    head, staged = head_sha(root, length=40), _git(root, "diff", "--cached", "--name-only")

    _refresh(root, _Tool())

    assert (head_sha(root, length=40), _git(root, "diff", "--cached", "--name-only")) == \
        (head, staged)


@pytest.mark.skipif(os.name == "nt", reason="off Windows crew_shell.run is bash -c; "
                    "on it the route depends on shellRoute and the host")
def test_refresh_cli_runs_graphify_from_path_through_bash(tmp_path):
    """The default runner, end to end: a fake `graphify` on PATH is run from
    the repository root with the sanctioned arguments."""
    root = _repo(tmp_path / "r")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    log = tmp_path / "calls.log"
    fake = bin_dir / "graphify"
    fake.write_text(
        "#!" + sys.executable + "\n"
        "import json, os, subprocess, sys\n"
        f"open({str(log)!r}, 'a').write(os.getcwd() + ' ' + ' '.join(sys.argv[1:]) + '\\n')\n"
        "sha = subprocess.run(['git', 'rev-parse', 'HEAD'], capture_output=True, text=True)"
        ".stdout.strip()\n"
        "open('graphify-out/graph.json', 'w').write(json.dumps({'nodes': [{}, {}], "
        "'links': [{}], 'built_at_commit': sha}))\n"
        "open('graphify-out/GRAPH_REPORT.md', 'w', encoding='utf-8').write("
        f"{_report(2, 1)!r})\n", encoding="utf-8")
    fake.chmod(0o755)
    env = dict(os.environ, PATH=str(bin_dir) + os.pathsep + os.environ.get("PATH", ""))

    done = subprocess.run([sys.executable, _SCRIPT, "refresh", "--root", root], env=env,
                          capture_output=True, text=True, stdin=subprocess.DEVNULL,
                          timeout=120, check=False)

    assert (done.returncode, log.read_text(encoding="utf-8")) == \
        (0, os.path.realpath(root) + " update .\n"), done.stdout + done.stderr


def test_git_env_does_not_redirect_status_to_another_worktree(tmp_path):
    """Review round 3: GIT_DIR / GIT_WORK_TREE from the caller are dropped."""
    root = _repo(tmp_path / "r")
    other = _repo(tmp_path / "o", graph=False)
    env = dict(os.environ, GIT_DIR=os.path.join(other, ".git"), GIT_WORK_TREE=str(tmp_path))

    done = subprocess.run([sys.executable, _SCRIPT, "status", "--root", root], env=env,
                          capture_output=True, text=True, stdin=subprocess.DEVNULL,
                          timeout=120, check=False)

    assert (done.returncode, done.stdout.startswith("graph=fresh "),
            done.stdout.rstrip("\n").endswith("pair=agree ignore=covered command=graphify update .")) \
        == (0, True, True), done.stdout + done.stderr


def test_refresh_built_at_commit_only_nested_exits_2(tmp_path):
    """Review round 3: provenance is graph.json's top-level field, not a
    match anywhere in its bytes."""
    root = _repo(tmp_path)
    built = head_sha(root, length=40)
    text = json.dumps({"nodes": [{}, {}, {}, {}], "links": [{}, {}, {}],
                       "metadata": {"built_at_commit": built}})
    tool = _Tool(graph_text=text)

    code, out = _refresh(root, tool)

    assert (code, "built_at_commit" in out) == (2, True), out


def test_a_crash_is_could_not_tell(tmp_path, monkeypatch, capsys):
    root = _repo(tmp_path)

    def boom(*_args, **_kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(crew_graph, "status", boom)

    assert (crew_graph.main(["status", "--root", root]),
            "crew-graph: unknown - RuntimeError: boom" in capsys.readouterr().out) == (2, True)

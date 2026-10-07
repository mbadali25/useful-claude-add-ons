"""`/crew:graph`: the code graph's status, its sanctioned refresh, and the pair check (L-0667).

    python3 crew_graph.py status  --root . [--json]
    python3 crew_graph.py refresh --root .

`status` is read-only and prints one line:
`graph=<fresh|stale|unknown|absent> built_at=<sha|none> pair=<agree|disagree|unknown|untracked>
ignore=<covered|uncovered|unknown> command=<the graphify line refresh would run>`.
Freshness is `crew_freshness._read_graph`'s answer and the command
`crew_refresh_check.graph_command`'s, so this script holds no second copy of
either rule.

`refresh` stops at the first step that fails: graphify missing (exit 2); T-0064's
`crew_graph_ignore.coverage` uncovered (exit 1) or unknown (exit 2), before
anything is built; the sanctioned command, run from the repository root through
`crew_shell.run` (exactly `bash -c` off Windows, the configured route on it),
exiting non-zero (exit 1, its output verbatim); the built graph carrying no
`built_at_commit` (exit 2); and, where the report is tracked, the pair check:
the first `- <N> nodes · <M> edges` line under the report's `## Summary` must
equal `len(graph["nodes"])` and `len(graph["links"])`. A mismatch is exit 1
(`pair=disagree`, all four numbers); a report with no such line, a graph that
does not parse, or a graph with no `links` list (an `edges` key is not one) is
exit 2 (`pair=unknown`), never agree and never zero links. Then it prints the
changed paths under the graph directory and exits 0. It never installs, writes
`.graphifyignore`, stages, commits or pushes: the phase that called it commits.

Exit codes: 0 done (and verified), 1 refused or failed, 2 could not tell.
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys

sys.dont_write_bytecode = True

import crew_freshness  # noqa: E402  pylint: disable=wrong-import-position
import crew_graph_ignore  # noqa: E402  pylint: disable=wrong-import-position
import crew_refresh_check  # noqa: E402  pylint: disable=wrong-import-position
import crew_shell  # noqa: E402  pylint: disable=wrong-import-position

DONE, REFUSED, UNKNOWN = 0, 1, 2
AGREE, DISAGREE, PAIR_UNKNOWN, UNTRACKED = "agree", "disagree", "unknown", "untracked"
# graphify's report line, copied from a real GRAPH_REPORT.md:
# `- 25610 nodes · 55448 edges · 1044 communities (848 shown, 196 thin omitted)`.
_SUMMARY_LINE = re.compile(r"^- (\d+) nodes · (\d+) edges(?: ·|$)")
_TIMEOUT = 3600


def _git(cwd, *args):
    """git's raw stdout, or None on any failure (git missing, a non-zero exit,
    a timeout). Never stripped: a porcelain line starts with a space."""
    try:
        done = subprocess.run(("git",) + args, cwd=cwd, capture_output=True, check=False,
                              stdin=subprocess.DEVNULL, timeout=60,
                              env=dict(os.environ, GIT_OPTIONAL_LOCKS="0"))
    except (OSError, subprocess.SubprocessError):
        return None
    if done.returncode != 0:
        return None
    return done.stdout.decode("utf-8", "surrogateescape")


def _top(root):
    top = _git(root, "rev-parse", "--show-toplevel")
    top = top.rstrip("\n") if top else ""
    return os.path.abspath(top) if top else None


def _report_tracked(top, info):
    """True / False from git, or None when git cannot say or disagrees with
    `_read_graph`, which reads a failed listing as untracked: an unknown
    never becomes `pair=untracked`, which would skip the pair check."""
    report = os.path.join(os.path.dirname(info["path"]), "GRAPH_REPORT.md")
    rel = os.path.relpath(report, top).replace("\\", "/")
    listed = _git(top, "ls-files", "-z", "--", rel)
    if listed is None:
        return None
    tracked = bool(listed.strip("\0"))
    return tracked if tracked == bool(info["reportTracked"]) else None


def _graph_info(top):
    """(`_read_graph`'s info, None) or (None, why)."""
    cfg, unreadable = crew_refresh_check._read_config(top)  # pylint: disable=protected-access
    if cfg is None:
        return None, f"crew config unreadable ({unreadable}), so graph.out cannot be told"
    return crew_freshness._read_graph(top, cfg), None  # pylint: disable=protected-access


def graph_state(info):
    """absent, fresh (built at a commit no code moved since), unknown (no
    `built_at_commit`) or stale (anything else `_read_graph` did not call
    current, an unresolvable sha included)."""
    if not info["present"]:
        return "absent"
    if not info["builtAt"]:
        return "unknown"
    return "fresh" if info["current"] else "stale"


def _summary_counts(report_path):
    """(nodes, edges) from the first summary line under `## Summary`, or
    (None, why)."""
    try:
        with open(report_path, encoding="utf-8") as handle:
            lines = handle.read().splitlines()
    except (OSError, UnicodeDecodeError) as exc:
        return None, f"GRAPH_REPORT.md unreadable ({type(exc).__name__})"
    inside = False
    for line in lines:
        if line.startswith("## "):
            if inside:
                break
            inside = line.rstrip() == "## Summary"
            continue
        match = _SUMMARY_LINE.match(line) if inside else None
        if match:
            return (int(match.group(1)), int(match.group(2))), None
    return None, "GRAPH_REPORT.md has no '- <N> nodes · <M> edges' line under '## Summary'"


def _graph_counts(graph_path):
    """(nodes, links) from graph.json parsed whole, or (None, why). A graph
    with no `links` list is unknown, never zero links."""
    try:
        with open(graph_path, encoding="utf-8") as handle:
            graph = json.load(handle)
    except (OSError, ValueError) as exc:
        return None, f"graph.json does not parse ({type(exc).__name__})"
    if not isinstance(graph, dict):
        return None, "graph.json is not an object"
    nodes, links = graph.get("nodes"), graph.get("links")
    if not isinstance(nodes, list):
        return None, "graph.json has no 'nodes' list"
    if not isinstance(links, list):
        extra = " (it has 'edges', which is not the key graphify writes)" if "edges" in graph else ""
        return None, f"graph.json has no 'links' list{extra}"
    return (len(nodes), len(links)), None


def pair_state(top, info):
    """(state, detail). `untracked` when git says the repo tracks no report
    beside the graph; else agree / disagree / unknown, unknown whenever
    either side, or whether the report is tracked, cannot be read."""
    tracked = _report_tracked(top, info)
    if tracked is None:
        return PAIR_UNKNOWN, "git could not say whether GRAPH_REPORT.md is tracked"
    if not tracked:
        return UNTRACKED, ""
    if not info["present"]:
        return PAIR_UNKNOWN, "no graph.json"
    graph, why = _graph_counts(info["path"])
    if graph is None:
        return PAIR_UNKNOWN, why
    report, why = _summary_counts(os.path.join(os.path.dirname(info["path"]), "GRAPH_REPORT.md"))
    if report is None:
        return PAIR_UNKNOWN, why
    detail = (f"report {report[0]} nodes / {report[1]} edges, "
              f"graph.json {graph[0]} nodes / {graph[1]} links")
    return (AGREE if report == graph else DISAGREE), detail


def status(root):
    """`{"graph", "built_at", "pair", "ignore", "command", "reasons"}`, or
    None with a reason when the repository or its config cannot be read."""
    top = _top(root)
    if not top:
        return None, "not inside a git repository (git rev-parse --show-toplevel failed)"
    info, why = _graph_info(top)
    if info is None:
        return None, why
    pair, pair_why = pair_state(top, info)
    cover = crew_graph_ignore.coverage(top)
    reasons = [r for r in (pair_why if pair in (DISAGREE, PAIR_UNKNOWN) else "",
                           cover["reason"] or "") if r]
    return {"graph": graph_state(info), "built_at": (info["builtAt"] or "none")[:12],
            "pair": pair, "ignore": cover["status"],
            "command": crew_refresh_check.graph_command(info), "reasons": reasons}, None


def render_status(result):
    return (f"graph={result['graph']} built_at={result['built_at']} pair={result['pair']} "
            f"ignore={result['ignore']} command={result['command']}")


def _run_graphify(command, top):
    """(exit code, combined output). Off Windows `crew_shell.run` is exactly
    `bash -c <command>`; on it, the route `shellRoute` picks."""
    captured = {}

    def execute(argv, cwd):
        try:
            done = subprocess.run(argv, cwd=cwd, check=False, capture_output=True,
                                  stdin=subprocess.DEVNULL, timeout=_TIMEOUT)
        except subprocess.TimeoutExpired:
            captured["out"] = f"timed out after {_TIMEOUT}s"
            return 124
        captured["out"] = crew_shell.decode(done.stdout) + crew_shell.decode(done.stderr)
        return done.returncode

    code = crew_shell.run(command, root=top, execute=execute)
    return code, captured.get("out", "")


def _changed(top, graph_dir):
    """Paths under the graph directory that differ from HEAD, untracked
    included, or None when git cannot say."""
    rel = os.path.relpath(graph_dir, top).replace("\\", "/")
    out = _git(top, "status", "--porcelain", "-z", "--untracked-files=all", "--", rel)
    if out is None:
        return None
    entries, paths = out.split("\0"), []
    while entries:
        entry = entries.pop(0)
        if len(entry) > 3:
            paths.append(entry[3:])
            if entry[0] in "RC" and entries:
                entries.pop(0)  # a rename's source path follows its entry
    return paths


def refresh(root, which=shutil.which, run=_run_graphify, out=print):
    """The refusal chain in the module docstring. Returns the exit code."""
    if not which("graphify"):
        out("crew-graph: graphify missing - nothing built; the crew-graph skill "
            "says how to install it (package graphifyy)")
        return UNKNOWN
    top = _top(root)
    if not top:
        out("crew-graph: unknown - not inside a git repository")
        return UNKNOWN
    info, why = _graph_info(top)
    if info is None:
        out(f"crew-graph: unknown - {why}")
        return UNKNOWN
    cover = crew_graph_ignore.coverage(top)
    if cover["status"] == crew_graph_ignore.UNCOVERED:
        out("crew-graph: refused - " + crew_graph_ignore.render(cover) + "; nothing built")
        return REFUSED
    if cover["status"] != crew_graph_ignore.COVERED:
        out(f"crew-graph: unknown - denylist coverage could not be told: {cover['reason']}; "
            "nothing built")
        return UNKNOWN
    command = crew_refresh_check.graph_command(info)
    code, output = run(command, top)
    if code != 0:
        out(f"crew-graph: failed - `{command}` exited {code}; its output:")
        out(output.rstrip("\n"))
        return REFUSED
    return _verify(top, command, out)


def _verify(top, command, out):
    info, why = _graph_info(top)
    if info is None:
        out(f"crew-graph: unknown - {why}")
        return UNKNOWN
    if not info["present"]:
        out(f"crew-graph: unknown - `{command}` exited 0 but wrote no "
            f"{os.path.relpath(info['path'], top)}")
        return UNKNOWN
    counts, why = _graph_counts(info["path"])
    if counts is None:
        out(f"crew-graph: unknown - pair=unknown: {why}")
        return UNKNOWN
    if not info["builtAt"]:
        out("crew-graph: unknown - the built graph.json carries no built_at_commit, "
            "so its provenance cannot be told")
        return UNKNOWN
    pair, detail = pair_state(top, info)
    if pair == DISAGREE:
        out(f"crew-graph: failed - pair=disagree: {detail}")
        return REFUSED
    if pair == PAIR_UNKNOWN:
        out(f"crew-graph: unknown - pair=unknown: {detail}")
        return UNKNOWN
    changed = _changed(top, os.path.dirname(info["path"]))
    if changed is None:
        out("crew-graph: unknown - built and verified, but git could not list what changed")
        return UNKNOWN
    out(f"crew-graph: refreshed with `{command}`, built_at={info['builtAt'][:12]}, "
        f"pair={pair}" + (f" ({detail})" if detail else "") + "; not committed")
    for path in changed:
        out(f"  changed: {crew_graph_ignore.shown(path)}")
    if not changed:
        out("  changed: nothing")
    return DONE


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    one = sub.add_parser("status")
    one.add_argument("--root", default=".")
    one.add_argument("--json", action="store_true")
    two = sub.add_parser("refresh")
    two.add_argument("--root", default=".")
    args = parser.parse_args(argv)
    try:
        sys.stdout.reconfigure(errors="backslashreplace")
    except (AttributeError, OSError, ValueError):
        pass
    try:
        if args.cmd == "refresh":
            return refresh(args.root)
        result, why = status(args.root)
    except Exception as exc:  # pylint: disable=broad-exception-caught
        # A crash proves nothing, so it is could-not-tell, never done.
        print(f"crew-graph: unknown - {type(exc).__name__}: {exc}")
        return UNKNOWN
    if result is None:
        print(f"crew-graph: unknown - {why}")
        return UNKNOWN
    print(json.dumps(result, indent=2) if args.json else render_status(result))
    return DONE


if __name__ == "__main__":
    sys.exit(main())

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

import crew_common  # noqa: E402  pylint: disable=wrong-import-position
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
# bash's "command not found"; the code a job route reports when graphify is absent there.
MISSING = 127


# git's variables that choose WHICH repository or work tree a command reads:
# from the caller they would point every git question, and graphify's own, at
# another repository than `--root` (review round 3). Config variables stay.
GIT_LOCATION = ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_COMMON_DIR",
                "GIT_OBJECT_DIRECTORY", "GIT_ALTERNATE_OBJECT_DIRECTORIES",
                "GIT_CEILING_DIRECTORIES", "GIT_DISCOVERY_ACROSS_FILESYSTEM",
                "GIT_NAMESPACE", "GIT_PREFIX")


def _without_git_env(environ):
    return {k: v for k, v in environ.items() if k.upper() not in GIT_LOCATION}


def _git(cwd, *args):
    """git's raw stdout, or None on any failure (git missing, a non-zero exit,
    a timeout). Never stripped: a porcelain line starts with a space."""
    try:
        done = subprocess.run((crew_common.require_tool("git"),) + args, cwd=cwd, capture_output=True, check=False,
                              stdin=subprocess.DEVNULL, timeout=60,
                              env=dict(_without_git_env(os.environ), GIT_OPTIONAL_LOCKS="0"))
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


def graph_state(top, info):
    """absent, fresh (built at a commit no code moved since, or T-0063's case:
    graphify's manifest records the current bytes of every committed code
    path that moved, because it leaves graph.json and its sha alone when the
    topology did not change), unknown (no `built_at_commit`) or stale
    (anything else, an unresolvable sha included)."""
    if not info["present"]:
        return "absent"
    if not info["builtAt"]:
        return "unknown"
    if info["current"]:
        return "fresh"
    return "fresh" if _manifest_current(top, info) else "stale"


def _manifest_current(top, info):
    """The refresh check's manifest rule (`_committed_moves`,
    `_manifest_confirms`) over every code path moved since the graph's sha;
    False whenever git cannot say."""
    graph_dir = os.path.dirname(info["path"])
    out = os.path.relpath(graph_dir, top).replace("\\", "/").rstrip("/")
    excludes = [f":(exclude){out}/**"] + [f":(exclude){g}" for g in
                                          crew_freshness.GRAPH_NONCODE_PATHS]
    listed = _git(top, "diff", "--name-only", "-z", f"{info['builtAt']}..HEAD", "--", ".",
                  *excludes)
    moved = [p for p in (listed or "").split("\0") if p]
    if not moved:
        return False
    committed = crew_refresh_check._committed_moves(  # pylint: disable=protected-access
        top, info["builtAt"], moved, set())
    if not committed:
        return False
    return crew_refresh_check._manifest_confirms(  # pylint: disable=protected-access
        top, graph_dir, committed)[0]


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
    """(nodes, links, top-level built_at_commit or None) from graph.json
    parsed whole, or (None, why). A graph with no `links` list is unknown,
    never zero links."""
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
    built = graph.get("built_at_commit")
    return (len(nodes), len(links), built if isinstance(built, str) else None), None


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
    return (AGREE if report == graph[:2] else DISAGREE), detail


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
    # The command depends on whether the report is tracked; when git cannot
    # say, refresh refuses, so no command is named (review round 2).
    command = (crew_refresh_check.graph_command(info) if _report_tracked(top, info) is not None
               else "unknown")
    return {"graph": graph_state(top, info), "built_at": (info["builtAt"] or "none")[:12],
            "pair": pair, "ignore": cover["status"], "command": command,
            "reasons": reasons}, None


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
        except OSError as exc:  # the route's program itself could not start
            captured["out"] = f"{argv[0]} could not start ({type(exc).__name__}: {exc})"
            return MISSING
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


def refresh(root, which=shutil.which, run=_run_graphify, out=print, windows=None):
    """The refusal chain in the module docstring. Returns the exit code. On
    native Windows the job may run in WSL, whose PATH is not this one, so
    graphify's absence is read from the route's exit 127 instead of
    `which` (review round 2)."""
    windows = crew_shell.on_windows() if windows is None else windows
    if not windows and not which("graphify"):
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
    if _report_tracked(top, info) is None:
        # `_read_graph` reads a failed listing as untracked, which would pick the
        # code-only build and leave a tracked report behind its graph.
        out("crew-graph: unknown - git could not say whether GRAPH_REPORT.md is tracked, so "
            "which command to run cannot be told; nothing built")
        return UNKNOWN
    command = crew_refresh_check.graph_command(info)
    code, output = run(command, top)
    if code == MISSING and (windows or not which("graphify")):
        out(f"crew-graph: graphify missing where `{command}` ran (exit {MISSING}) - nothing "
            "built; the crew-graph skill says how to install it (package graphifyy)")
        out(output.rstrip("\n"))
        return UNKNOWN
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
    # `builtAt` is a regex over the file's bytes; the parsed graph's own
    # top-level field must say the same (review round 3).
    if not info["builtAt"] or counts[2] != info["builtAt"]:
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
    state = graph_state(top, info)
    if state != "fresh":
        # graphify exited 0 and the pair agrees, but the graph does not cover the
        # code at HEAD (a no-op run over a stale graph): not refreshed (review round 4).
        out(f"crew-graph: unknown - `{command}` exited 0 but the graph is {state} "
            f"(built_at={info['builtAt'][:12]}): code moved since it and graphify's manifest "
            "does not confirm it; nothing is verified")
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
    # Every git call below -- crew_freshness's, the denylist check's, and
    # graphify's own -- then judges `--root`, never a GIT_DIR from the caller;
    # restored afterwards for an in-process caller.
    # crew_graph_ignore snapshotted the environment at import, so its copy too.
    saved = [(env, {k: env.pop(k) for k in list(env) if k.upper() in GIT_LOCATION})
             for env in (os.environ, crew_graph_ignore._GIT_ENV)]  # pylint: disable=protected-access
    try:
        return _main(args)
    finally:
        for env, values in saved:
            env.update(values)


def _main(args):
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

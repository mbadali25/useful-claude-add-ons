"""Are the artifacts this ticket's changes reach still current? Read-only.

    python3 crew_refresh_check.py --root . --ticket <id> [--json]

T-0008. `/crew:implement` runs it after `/crew:docs` and before
`/crew:review`, then runs the refresh command it names for each stale
artifact; `/crew:done` runs it again as its fourth check and refuses on
anything but `fresh`, WITHOUT refreshing -- a write there would change the
tree check 1's review receipt was taken over. T-0004's autopilot imports
`ticket_freshness` for the same phase.

## What is judged, and against what

Three artifact kinds, each with the question `crew_freshness.py` already
asks of it for the status line, narrowed here to THIS ticket:

  codemap  `.crew/codemap/<subsystem>.md`, in scope when a path it cites is
           one the ticket changed. Refresh: `/crew:onboard --refresh <name>`.
  diagram  the Mermaid sources under `docs.diagramsDir`, in scope when a path
           in its `%% Anchors:` line is one the ticket changed -- or, with no
           Anchors line, when the ticket changed any code path at all (the
           same widening `read_diagrams` does). Refresh: `/crew:diagram refresh`.
  graph    `<graph.out>/graph.json`, in scope when the ticket changed a code
           path (anything outside `GRAPH_NONCODE_PATHS` and `graph.out`).
           Refresh: `graphify update .` where the repo tracks GRAPH_REPORT.md
           beside the graph, else `graphify . --no-viz --code-only` -- the
           choice `_read_graph`'s `reportTracked` already encodes.

"The ticket changed" is `scope_base.resolve` then
`completion_audit.changed_paths`: the base against the WORKING TREE plus
untracked files -- the same set `/crew:done`'s completion audit judges. The
freshness diff is then `git diff --name-only <anchor> -- <reached paths>`,
also against the working tree. `crew_freshness` diffs `<anchor>..HEAD`,
which cannot see an uncommitted edit; a refresh taken while the code it
describes is uncommitted records an anchor that predates it, so an
uncommitted change among the reached paths is `stale` with "commit, then
refresh", never `fresh`.

A raw anchor lag is NOT staleness. A repo-wide version bump moves every
anchor without invalidating a word (root CLAUDE.md), so only the paths this
ticket changed AND the artifact cites are asked about.

## Four values, and the unknowns stay unknown

`fresh`, `stale`, `unknown`, and `not applicable` for a repo with no graph
file. An anchor that is absent (codemap) or names no commit here, a diff git
could not run, a graph with no `built_at_commit`, graphify missing on this
machine, or no scope base at all are each `unknown` -- its own value, which
refuses exactly as `stale` does. Folding any of them into `fresh` is the
recurring defect named in root CLAUDE.md's Lessons. A diagram with no
provenance header is `stale`, as `read_diagrams` treats it.

Documents (README, CHANGELOG, ...) are `not measured`: whether a change
"should" touch one is `/crew:docs`'s judgement, and nothing here can check a
judgement. They are never reported `fresh`.

## Fixpoint

The artifacts' own directories (`.crew/codemap/`, the diagrams dir,
`graph.out`) and `.work/` are dropped from the changed set before anything is
matched, so the commit that records a refresh cannot stale the artifact it
refreshed or another one. Code-path tests use `GRAPH_NONCODE_PATHS`, the
deny-list `crew_freshness` uses for the same purpose.

Never writes a file. Standard library only.
"""
import argparse
import fnmatch
import json
import os
import shutil
import sys

import completion_audit
import crew_ticket
import scope_base
from crew_common import git_out, read_text
from crew_freshness import (
    DIAGRAMS_DIR_DEFAULT,
    GRAPH_NONCODE_PATHS,
    _ANCHOR_RE,
    _CITED_PATH_RE,
    _DIAGRAM_ANCHOR_RE,
    _DIAGRAM_ANCHORS_RE,
    _DIAGRAM_EXTS,
    _NOT_SUBSYSTEMS,
    _diagrams_dir,
    _read_graph,
    contained_path,
)

FRESH = "fresh"
STALE = "stale"
UNKNOWN = "unknown"
NOT_APPLICABLE = "not applicable"
NOT_MEASURED = "not measured"

_FEW = 4


def _few(paths):
    shown = ", ".join(paths[:_FEW])
    return shown + (f" (+{len(paths) - _FEW} more)" if len(paths) > _FEW else "")


def _entry(kind, name, status, reason, command):
    return {"kind": kind, "name": name, "status": status, "reason": reason,
            "command": command}


def _config(root):
    """`.crew/crew.json` (1.0), else `.crew/config.json`, else {} -- the order
    `crew_status` reads them in. Unreadable is {}: every key used here has a
    default, and a default is the documented layout."""
    for name in ("crew.json", "config.json"):
        text = read_text(os.path.join(root, ".crew", name))
        if text is None:
            continue
        try:
            data = json.loads(text)
        except ValueError:
            return {}
        return data if isinstance(data, dict) else {}
    return {}


def _git_lines(root, *args):
    out = git_out(root, "--literal-pathspecs", "-c", "core.quotePath=false", *args)
    if out is None:
        return None
    return [line for line in out.splitlines() if line.strip()]


def _moved_in_tree(root, sha, paths):
    """Which of `paths` differ between `sha` and the WORKING TREE, or None
    when git could not answer."""
    return _git_lines(root, "diff", "--name-only", sha, "--", *paths)


def _judge(root, sha, reached, untracked):
    """(status, reason) for an artifact anchored at `sha`, over `reached`: the
    ticket's changed paths this artifact cites."""
    if git_out(root, "cat-file", "-e", sha + "^{commit}") is None:
        return UNKNOWN, f"anchor {sha} names no commit in this repository"
    moved = _moved_in_tree(root, sha, reached)
    if moved is None:
        return UNKNOWN, f"git could not diff {sha[:12]} against the working tree"
    new = [p for p in reached if p in untracked]
    if not moved and not new:
        return FRESH, f"nothing it cites moved since {sha[:12]}"
    dirty = (_git_lines(root, "diff", "--name-only", "HEAD", "--", *moved)
             if moved else []) or []
    pending = sorted(set(new) | set(dirty))
    if pending:
        return STALE, f"uncommitted changes in {_few(pending)}: commit, then refresh"
    return STALE, f"{_few(sorted(moved))} changed since its anchor {sha[:12]}"


def _under(path, prefixes):
    return any(path == p.rstrip("/") or path.startswith(p) for p in prefixes)


def _is_noncode(path, graph_out):
    globs = list(GRAPH_NONCODE_PATHS) + [graph_out.rstrip("/") + "/**"]
    return any(fnmatch.fnmatchcase(path, g) for g in globs)


def _codemaps(root, changed, untracked):
    mapdir = os.path.join(root, ".crew", "codemap")
    try:
        names = sorted(os.listdir(mapdir))
    except OSError:
        return []
    found = []
    for name in names:
        if not name.endswith(".md") or name in _NOT_SUBSYSTEMS:
            continue
        stem = name[: -len(".md")]
        body = read_text(os.path.join(mapdir, name)) or ""
        # Every path-shaped citation, NOT `_cited_paths`: that one drops a
        # citation whose file no longer exists, and a ticket that deletes a
        # cited file is exactly the change that stales the map.
        reached = sorted(set(_CITED_PATH_RE.findall(body)) & changed)
        if not reached:
            continue
        command = f"/crew:onboard --refresh {stem}"
        anchor = _ANCHOR_RE.search(body)
        if not anchor:
            found.append(_entry("codemap", stem, UNKNOWN,
                                "no `anchor:` line, so nothing about it can be checked",
                                command))
            continue
        status, reason = _judge(root, anchor.group(1), reached, untracked)
        found.append(_entry("codemap", stem, status, reason, command))
    return found


def _declared(body):
    """The paths a diagram's `%% Anchors:` line names, existing or not, or
    None when it has no such line."""
    line = _DIAGRAM_ANCHORS_RE.search(body)
    if not line:
        return None
    return [p for p in (raw.strip().strip("`") for raw in line.group(1).split(",")) if p]


def _diagrams(root, dirpath, changed, code, untracked):
    try:
        names = sorted(os.listdir(dirpath))
    except OSError:
        return []
    found = []
    for name in names:
        stem, ext = os.path.splitext(name)
        if ext.lower() not in _DIAGRAM_EXTS:
            continue
        body = read_text(os.path.join(dirpath, name)) or ""
        declared = _declared(body)
        reached = code if declared is None else sorted(set(declared) & changed)
        if not reached:
            continue
        command = "/crew:diagram refresh"
        anchor = _DIAGRAM_ANCHOR_RE.search(body)
        if not anchor:
            found.append(_entry("diagram", stem, STALE,
                                "no provenance header (`%% Generated from <repo>@<sha>`)",
                                command))
            continue
        status, reason = _judge(root, anchor.group(1), reached, untracked)
        found.append(_entry("diagram", stem, status, reason, command))
    return found


def _graph(root, info, graph_out, code, untracked, which):
    command = ("graphify update ." if info["reportTracked"]
               else "graphify . --no-viz --code-only")
    if not info["present"]:
        return _entry("graph", graph_out, NOT_APPLICABLE,
                      f"no graph file at {graph_out}/graph.json", command)
    if not code:
        return None
    if not which("graphify"):
        return _entry("graph", graph_out, UNKNOWN,
                      "graphify missing on this machine, so the graph can be "
                      "neither rebuilt nor confirmed current", command)
    if not info["builtAt"]:
        return _entry("graph", graph_out, UNKNOWN,
                      "graph.json carries no built_at_commit, so its provenance is unknown",
                      command)
    status, reason = _judge(root, info["builtAt"], code, untracked)
    return _entry("graph", graph_out, status, reason, command)


def _relative(root, path):
    return os.path.relpath(path, root).replace("\\", "/")


def ticket_freshness(root, ticket, which=shutil.which):
    """`{"status", "reason", "artifacts": [{"kind", "name", "status", "reason",
    "command"}], "documents": "not measured"}`.

    `status` is `unknown` if any artifact is unknown, else `stale` if any is
    stale, else `fresh`. `which` finds graphify; injectable so a test can say
    "missing" without editing PATH."""
    top = crew_ticket.toplevel(root)
    base, _source, why = scope_base.resolve(top or root, ticket)
    if not top or not base:
        return {"status": UNKNOWN, "reason": f"no scope base for {ticket} ({why})",
                "artifacts": [], "documents": NOT_MEASURED}
    try:
        every = set(completion_audit.changed_paths(top, base))
    except RuntimeError as exc:
        return {"status": UNKNOWN, "reason": f"could not list {ticket}'s changes: {exc}",
                "artifacts": [], "documents": NOT_MEASURED}
    untracked = _git_lines(top, "ls-files", "--others", "--exclude-standard")
    if untracked is None:
        return {"status": UNKNOWN, "reason": "git could not list untracked files",
                "artifacts": [], "documents": NOT_MEASURED}

    cfg = _config(top)
    info = _read_graph(top, cfg)
    graph_out = _relative(top, os.path.dirname(info["path"]))
    diagrams = contained_path(top, _diagrams_dir(cfg), DIAGRAMS_DIR_DEFAULT)
    own = [".crew/codemap/", ".work/", _relative(top, diagrams) + "/", graph_out + "/"]
    changed = {p for p in every if not _under(p, own)}
    code = sorted(p for p in changed if not _is_noncode(p, graph_out))

    artifacts = _codemaps(top, changed, set(untracked))
    artifacts += _diagrams(top, diagrams, changed, code, set(untracked))
    graph = _graph(top, info, graph_out, code, set(untracked), which)
    if graph:
        artifacts.append(graph)

    statuses = {a["status"] for a in artifacts}
    overall = UNKNOWN if UNKNOWN in statuses else STALE if STALE in statuses else FRESH
    return {"status": overall, "reason": f"scope base {base[:12]} ({why})",
            "artifacts": artifacts, "documents": NOT_MEASURED}


def _render(ticket, result):
    lines = [f"refresh-check {ticket}: {result['status']} - {result['reason']}"]
    for item in result["artifacts"]:
        line = f"  {item['kind']} {item['name']}: {item['status']} - {item['reason']}"
        if item["status"] in (STALE, UNKNOWN):
            line += f"; refresh with {item['command']}"
        lines.append(line)
    if not result["artifacts"]:
        lines.append("  no codemap, diagram or graph cites a path this ticket changed")
    lines.append("  documents: not measured - /crew:docs is judgement")
    return "\n".join(lines) + "\n"


def main(argv):
    """Exit 0 fresh, 1 stale or unknown, 2 usage error."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", default=".")
    parser.add_argument("--ticket", required=True)
    parser.add_argument("--json", action="store_true")
    try:
        args = parser.parse_args(argv)
        crew_ticket.check_ticket(args.ticket)
    except SystemExit as exc:
        return 0 if exc.code == 0 else 2
    except crew_ticket.TicketError as exc:
        sys.stderr.write(f"refresh-check: {exc}\n")
        return 2
    # A read-only check must not refresh the index's stat cache either.
    os.environ["GIT_OPTIONAL_LOCKS"] = "0"
    result = ticket_freshness(os.path.abspath(args.root), args.ticket)
    sys.stdout.write(json.dumps(result, indent=2) + "\n" if args.json
                     else _render(args.ticket, result))
    return 0 if result["status"] == FRESH else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

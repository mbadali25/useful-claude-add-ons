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
           one the ticket changed. Citations are backticked paths with an
           optional `:line` or `:start-end`, dot-directories included
           (`.claude-plugin/`, `.github/`); a cited directory (`a/b`, not the
           prose form `a/b/`) reaches every path under it, as a git pathspec
           would. A map that cites no path at
           all is `unknown`, never out of scope -- `read_knowledge` widens to
           the whole tree for the same map. Refresh: `/crew:onboard --refresh
           <name>`.
  diagram  the Mermaid sources under `docs.diagramsDir`, in scope when a path
           in its `%% Anchors:` line is, or is under, one the ticket changed
           -- or, with no Anchors line, when the ticket changed any code path
           at all (the same widening `read_diagrams` does). Refresh:
           `/crew:diagram refresh`.
  graph    `<graph.out>/graph.json`, in scope when the ticket changed a code
           path (anything outside `GRAPH_NONCODE_PATHS` and `graph.out`).
           Refresh: `graphify update .` where the repo tracks GRAPH_REPORT.md
           beside the graph, else `graphify . --no-viz --code-only` -- the
           choice `_read_graph`'s `reportTracked` already encodes.

"The ticket changed" is `scope_base.resolve` then
`completion_audit.changed_paths`: the base against the WORKING TREE plus
untracked files -- the same set `/crew:done`'s completion audit judges --
minus RELEASE_BOOKKEEPING (CHANGELOG.md, TODO.md, PLUGINS.md, the
marketplace and plugin manifests, BUDGETS.md), which every release -- or, for
TODO.md, every ticket filing its findings -- moves without invalidating a
word of any map (the spec's Exclusions). The
freshness diff is then `git diff --name-only <anchor> -- <reached paths>`,
also against the working tree. `crew_freshness` diffs `<anchor>..HEAD`,
which cannot see an uncommitted edit; a refresh taken while the code it
describes is uncommitted records an anchor that predates it, so an
uncommitted change among the reached paths is `stale` with "commit, then
refresh", never `fresh`.

A raw anchor lag is NOT staleness. A repo-wide version bump moves every
anchor without invalidating a word (root CLAUDE.md), so only the paths this
ticket changed AND the artifact cites are asked about.

A scope base that HIDES the change cannot confirm anything: no base at
all, or a fallback equal to HEAD (on the default branch the merge-base IS
HEAD, so every committed change vanishes). Either makes the overall answer
`unknown`. Any other fallback -- the merge-base with the default branch, or a
`record-fallback` entry -- shows at least what the ticket changed (MORE, as
`scope_base` says), so it is used; every artifact line derived from it says
`[fallback base]`, so the reassuring line and the uninformative one never
look the same (owner-delegated narrowing, 2026-09-25: "any fallback reads
unknown" made check 4 refuse every ticket whose start was not recorded).

That "shows at least" holds only while none of the ticket's commits is
behind the fallback base, which is false once they reach the default branch:
work done on it and pushed, or a branch fast-forwarded into it and given one
more commit (review round 2). So a fallback is trusted only when HEAD is on
a branch that is not the default one AND no commit reachable from the base
names the ticket in its subject; otherwise, or when git cannot answer
either question, the answer is `unknown` with `fallback base <sha> may hide
<ticket>'s commits`. A ticket whose commits reached the default branch under
a subject that does not name it is not caught -- the limit of reading
subjects. `--json` carries `base_source`, so a caller need not parse prose
to tell a recorded base from a fallback.

## Four values, and the unknowns stay unknown

`fresh`, `stale`, `unknown`, and `not applicable` for a repo with no graph
file. An anchor that is absent (codemap) or names no commit here, a map that
cites no path, a diff git could not run, a graph with no `built_at_commit`,
graphify missing on this machine, a scope base that hides or may hide the
change, an artifact dir that cannot be listed, an artifact that cannot be read,
or a crew config that exists and does not parse are each
`unknown` -- its own value, which refuses exactly as `stale` does. Folding any
of them into `fresh` is the recurring defect named in root CLAUDE.md's
Lessons. A diagram with no provenance header is `stale`, as `read_diagrams`
treats it.

Some unknowns a refresh settles and some it cannot, and each artifact says
which (`refreshable`). An anchor that is absent or names no commit -- the
usual cause is a squash merge, which drops the branch commit a refresh
anchored to -- a map citing no path, and a graph with no `built_at_commit`
are settled by the refresh that re-anchors them, so their line names the
command. graphify missing, a diff git could not run, an unreadable dir, file
or config, and a scope base that hides or may hide the change are not: their
line says stop -- for the scope base and the config, the TOP line, since no
artifact is to blame. When nothing was measured at all the renderer says
`not measured - <why>`, never the "no codemap ... cites" line, which is a
claim about artifacts that were judged.

Documents (README, CHANGELOG, ...) are `not measured`: whether a change
"should" touch one is `/crew:docs`'s judgement, and nothing here can check a
judgement. They are never reported `fresh`.

## Refresh-artifact paths, and the fixpoint

REFRESH_ARTIFACT_PATHS is what the refreshes write: the code map, the
diagrams dir, `graph.out` and `.claude/rules/` (generated from the code map).
It is defined here and nowhere else. `scope_guard.py` and
`completion_audit.py` read it through `refresh_artifact_paths` /
`is_refresh_artifact` to let an APPROVED ticket write those paths without
naming them in Touch -- the refresh `/crew:implement` step 6 demands would
otherwise be refused by both. And the same paths, plus `.work/`, are dropped
from the changed set here before anything is matched, so the commit that
records a refresh cannot stale the artifact it refreshed or another one.
Code-path tests use `GRAPH_NONCODE_PATHS`, the deny-list `crew_freshness`
uses for the same purpose.

Never writes a file, the index included, for a library caller (T-0004
imports `ticket_freshness`) as much as for main(): the working-tree diffs go
through `completion_audit.worktree_changes` (`git diff-index` plus a hash of
any stat-dirty file), because `git diff` rewrites .git/index for a stat-dirty
file even under `--no-optional-locks`. Standard library only.
"""
import argparse
import fnmatch
import json
import os
import re
import shutil
import sys

import completion_audit
import crew_ticket
import scope_base
from crew_common import dict_or_empty, git_out, read_text
from crew_freshness import (
    DIAGRAMS_DIR_DEFAULT,
    GRAPH_NONCODE_PATHS,
    GRAPH_OUT_DEFAULT,
    _ANCHOR_RE,
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

# What `/crew:implement` step 6's refreshes write, as (config key, default):
# `/crew:onboard --refresh` writes the code map and the `.claude/rules/` file
# generated from it, `/crew:diagram` the diagrams dir, graphify `graph.out`.
# The ONE definition (module docstring): the scope guard and the completion
# audit let an approved ticket write these without naming them in Touch.
# A keyed entry is read from crew config exactly as `crew_freshness` reads it
# (`_diagrams_dir`, `_read_graph`: a wrong-typed or empty value is the
# default, and `contained_path` keeps it inside the repository).
REFRESH_ARTIFACT_PATHS = (
    (None, ".crew/codemap"),
    ("docs.diagramsDir", DIAGRAMS_DIR_DEFAULT),
    ("graph.out", GRAPH_OUT_DEFAULT),
    (None, ".claude/rules"),
)

# Moved by every release, whatever the ticket: a version bump invalidates no
# map, diagram or graph (the spec's Exclusions), so these never stale one on
# their own. TODO.md is here for the same reason: `/crew:done` check 3 has
# every ticket file its findings there, and most maps cite it, so filing one
# item used to stale every map citing it. A code path cited beside it still
# stales the map. Segment globs, `crew_ticket.glob_match`'s dialect.
RELEASE_BOOKKEEPING = (
    "CHANGELOG.md",
    "TODO.md",
    "plugin/PLUGINS.md",
    ".claude-plugin/marketplace.json",
    "**/.claude-plugin/plugin.json",
    "plugin/*/BUDGETS.md",
)

# A backticked, path-shaped citation in a code map: an optional leading dot
# (`.claude-plugin/`, `.crew/`, `.github/` -- `crew_freshness._CITED_PATH_RE`
# cannot start with one), then an optional `:line` or `:start-end`.
# `_CITED_PATH_RE` is left alone: it also feeds the status line, and it drops
# a citation whose file is gone, where a ticket deleting a cited file is
# exactly the change that stales a map. A trailing-slash form (`plugin/`) is
# not a citation, as it is not one to `_CITED_PATH_RE` either: in a map it is
# prose about a prefix, and reading it as a directory put every crew change
# in scope of the localgpu map. A cited path with no slash that names a
# directory still reaches what is under it, as git's pathspec does for
# `read_knowledge`.
_CITATION_RE = re.compile(
    r"`(\.?[A-Za-z0-9_][A-Za-z0-9_.@+-]*(?:/[A-Za-z0-9_.@+-]+)*)(?::\d+(?:-\d+)?)?`"
)


def _few(paths):
    shown = ", ".join(paths[:_FEW])
    return shown + (f" (+{len(paths) - _FEW} more)" if len(paths) > _FEW else "")


def _entry(kind, name, status, reason, command, refreshable=None):
    """One artifact. `refreshable` says whether running `command` settles it:
    always for `stale`, never for `fresh` / `not applicable`, and per cause
    for `unknown` (module docstring)."""
    if refreshable is None:
        refreshable = status == STALE
    return {"kind": kind, "name": name, "status": status, "reason": reason,
            "command": command, "refreshable": refreshable}


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


def _read_config(root):
    """`(config, None)`, or `(None, reason)` when `.crew/crew.json` or, absent
    it, `.crew/config.json` EXISTS but is not a readable JSON object. Unlike
    `_config`, an unreadable file is not the defaults: the defaults name a
    diagrams dir and a graph dir, and judging those when the config names
    others reads the real ones as out of scope -- `fresh` from nothing
    measured. The scope guard fails closed on the same file."""
    for name in ("crew.json", "config.json"):
        path = os.path.join(root, ".crew", name)
        if not os.path.lexists(path):
            continue
        text = read_text(path)
        if text is None:
            return None, f".crew/{name} could not be read"
        try:
            data = json.loads(text)
        except ValueError:
            return None, f".crew/{name} is not valid JSON"
        if not isinstance(data, dict):
            return None, f".crew/{name} is not a JSON object"
        return data, None
    return {}, None


def _listing(dirpath):
    """`(names, None)` -- `[]` for a dir that does not exist, which holds no
    artifact -- or `(None, reason)` when it exists and cannot be listed: a
    denied listing hides every artifact in it, and "none found" would then
    read as `fresh`."""
    try:
        return sorted(os.listdir(dirpath)), None
    except FileNotFoundError:
        return [], None
    except OSError as exc:
        return None, exc.strerror or type(exc).__name__


def _git_lines(root, *args):
    # `--no-optional-locks` on every call, though only `rev-parse`,
    # `cat-file`, `symbolic-ref` and `log` go through here: none writes the
    # index today, and a read-only check should not depend on that staying
    # true. Newline-split, so never for a list of file names (see the
    # untracked listing in `ticket_freshness`).
    out = git_out(root, "--no-optional-locks", "--literal-pathspecs",
                  "-c", "core.quotePath=false", *args)
    if out is None:
        return None
    return [line for line in out.splitlines() if line.strip()]


def _git_head(root):
    """HEAD's full sha, or None -- compared with a fallback base, never
    trusted as one."""
    lines = _git_lines(root, "rev-parse", "--verify", "HEAD^{commit}")
    return lines[0] if lines else None


def _moved_in_tree(root, sha, paths):
    """Which of `paths` differ between `sha` and the WORKING TREE, or None
    when git could not answer. `completion_audit.worktree_changes`, not
    `git diff`: the porcelain rewrites .git/index for a stat-dirty file even
    under `--no-optional-locks` (measured, git 2.53). No paths is no
    question: an empty pathspec would ask it of the whole tree."""
    if not paths:
        return []
    try:
        return sorted(completion_audit.worktree_changes(root, sha, list(paths), literal=True))
    except RuntimeError:
        return None


def _judge(root, sha, reached, untracked):
    """(status, reason, refreshable) for an artifact anchored at `sha`, over
    `reached`: the ticket's changed paths this artifact cites."""
    if _git_lines(root, "cat-file", "-e", sha + "^{commit}") is None:
        return UNKNOWN, (f"anchor {sha} names no commit in this repository (a "
                         "squash-merged or rebased branch?); a refresh re-anchors it"), True
    moved = _moved_in_tree(root, sha, reached)
    if moved is None:
        return UNKNOWN, f"git could not diff {sha[:12]} against the working tree", False
    new = [p for p in reached if p in untracked]
    if not moved and not new:
        return FRESH, f"nothing it cites moved since {sha[:12]}", False
    dirty = (_moved_in_tree(root, "HEAD", moved) if moved else []) or []
    pending = sorted(set(new) | set(dirty))
    if pending:
        return STALE, f"uncommitted changes in {_few(pending)}: commit, then refresh", True
    return STALE, f"{_few(sorted(moved))} changed since its anchor {sha[:12]}", True


def _reaches(entry, path):
    """`entry` (a citation or an Anchors path) names `path`, or a directory
    `path` is under -- a git pathspec's reading, which is how
    `read_knowledge` and `read_diagrams` pass the same entries to git."""
    entry = entry.rstrip("/")
    return bool(entry) and (path == entry or path.startswith(entry + "/"))


def _reached(entries, changed):
    return sorted(p for p in changed if any(_reaches(e, p) for e in entries))


def refresh_artifact_paths(root, cfg=None):
    """REFRESH_ARTIFACT_PATHS resolved for the repository at `root`:
    repo-relative, `/`-separated, no trailing slash, in declaration order.

    A dir is DROPPED rather than returned when it resolves to the repository
    root or into `.git` -- `docs.diagramsDir: "."` would otherwise make every
    path an artifact, and the allowance is for artifacts, not the tree -- or
    when a symlink or junction anywhere along it makes the real directory
    differ from the one named: `.crew/codemap -> ../src` would otherwise put
    `src` itself on the list. `cfg` defaults to this repo's crew config."""
    top = os.path.realpath(root)
    cfg = _config(top) if cfg is None else cfg
    found = []
    for key, default in REFRESH_ARTIFACT_PATHS:
        value = default
        if key:
            section, name = key.split(".")
            raw = dict_or_empty(cfg.get(section)).get(name)
            value = raw if isinstance(raw, str) and raw else default
        real = contained_path(top, value, default)
        named = {os.path.normcase(os.path.normpath(os.path.join(top, v))) for v in (value, default)}
        if os.path.normcase(real) not in named:
            continue
        rel = _relative(top, real)
        first = os.path.normcase(rel.split("/", maxsplit=1)[0])
        if rel in ("", ".") or first in ("..", os.path.normcase(".git")):
            continue
        if rel not in found:
            found.append(rel)
    return found


def is_refresh_artifact(rel, dirs):
    """True when repo-relative `rel` lies strictly UNDER one of `dirs`,
    compared whole segment by whole segment -- `.crew/codemapX/a.md` is not
    under `.crew/codemap`, and a dir named `**` is a literal name, never a
    glob. Case folds only where the filesystem does (`os.path.normcase`).

    `rel` must already be normalised (`/`-separated, `..` collapsed); an
    empty, `.` or `..` segment, or an absolute path, is never an artifact,
    because an unnormalised path is no evidence of where a write lands."""
    if not isinstance(rel, str) or not rel or rel.startswith("/") or os.path.isabs(rel):
        return False
    parts = rel.split("/")
    if any(p in ("", ".", "..") for p in parts):
        return False
    folded = [os.path.normcase(p) for p in parts]
    for directory in dirs:
        stem = [os.path.normcase(p) for p in directory.split("/")]
        if len(folded) > len(stem) and folded[:len(stem)] == stem:
            return True
    return False


def _bookkeeping(path):
    return any(crew_ticket.glob_match(path, glob) for glob in RELEASE_BOOKKEEPING)


def _is_noncode(path, graph_out):
    globs = list(GRAPH_NONCODE_PATHS) + [graph_out.rstrip("/") + "/**"]
    return any(fnmatch.fnmatchcase(path, g) for g in globs)


def _codemaps(root, changed, untracked):
    mapdir = os.path.join(root, ".crew", "codemap")
    names, denied = _listing(mapdir)
    if names is None:
        return [_entry("codemap", ".crew/codemap", UNKNOWN,
                       f"the directory could not be listed ({denied}), so no map in it "
                       "can be judged", "/crew:onboard", refreshable=False)]
    found = []
    for name in names:
        if not name.endswith(".md") or name in _NOT_SUBSYSTEMS:
            continue
        stem = name[: -len(".md")]
        body = read_text(os.path.join(mapdir, name))
        command = f"/crew:onboard --refresh {stem}"
        if body is None:
            if changed:
                found.append(_entry("codemap", stem, UNKNOWN,
                                    "the map could not be read, so what it cites cannot "
                                    "be told", command, refreshable=False))
            continue
        # Every path-shaped citation, NOT `_cited_paths`: that one drops a
        # citation whose file no longer exists, and a ticket that deletes a
        # cited file is exactly the change that stales the map.
        cited = [c for c in dict.fromkeys(_CITATION_RE.findall(body)) if "/" in c or "." in c]
        if not cited:
            if changed:
                found.append(_entry("codemap", stem, UNKNOWN,
                                    "cites no path, so which changes reach it cannot "
                                    "be told", command, refreshable=True))
            continue
        reached = _reached(cited, changed)
        if not reached:
            continue
        anchor = _ANCHOR_RE.search(body)
        if not anchor:
            found.append(_entry("codemap", stem, UNKNOWN,
                                "no `anchor:` line, so nothing about it can be checked",
                                command, refreshable=True))
            continue
        status, reason, refreshable = _judge(root, anchor.group(1), reached, untracked)
        found.append(_entry("codemap", stem, status, reason, command, refreshable))
    return found


def _declared(body):
    """The paths a diagram's `%% Anchors:` line names, existing or not, or
    None when it has no such line."""
    line = _DIAGRAM_ANCHORS_RE.search(body)
    if not line:
        return None
    return [p for p in (raw.strip().strip("`") for raw in line.group(1).split(",")) if p]


def _diagrams(root, dirpath, changed, code, untracked):
    command = "/crew:diagram refresh"
    names, denied = _listing(dirpath)
    if names is None:
        return [_entry("diagram", _relative(root, dirpath), UNKNOWN,
                       f"the directory could not be listed ({denied}), so no diagram in "
                       "it can be judged", command, refreshable=False)]
    found = []
    for name in names:
        stem, ext = os.path.splitext(name)
        if ext.lower() not in _DIAGRAM_EXTS:
            continue
        body = read_text(os.path.join(dirpath, name))
        if body is None:
            if changed:
                found.append(_entry("diagram", stem, UNKNOWN,
                                    "the diagram could not be read, so what it cites "
                                    "cannot be told", command, refreshable=False))
            continue
        declared = _declared(body)
        reached = code if declared is None else _reached(declared, changed)
        if not reached:
            continue
        anchor = _DIAGRAM_ANCHOR_RE.search(body)
        if not anchor:
            found.append(_entry("diagram", stem, STALE,
                                "no provenance header (`%% Generated from <repo>@<sha>`)",
                                command))
            continue
        status, reason, refreshable = _judge(root, anchor.group(1), reached, untracked)
        found.append(_entry("diagram", stem, status, reason, command, refreshable))
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
                      "neither rebuilt nor confirmed current", command, refreshable=False)
    if not info["builtAt"]:
        return _entry("graph", graph_out, UNKNOWN,
                      "graph.json carries no built_at_commit, so its provenance is unknown",
                      command, refreshable=True)
    status, reason, refreshable = _judge(root, info["builtAt"], code, untracked)
    return _entry("graph", graph_out, status, reason, command, refreshable)


def _relative(root, path):
    return os.path.relpath(path, root).replace("\\", "/")


_ID_EDGE = r"(?<![A-Za-z0-9]){}(?![A-Za-z0-9])"


def _fallback_hides(top, base, ticket):
    """Why a fallback base (neither `hides` case) may still hide the ticket's
    commits, or None when it cannot. The merge-base with the default branch
    shows the ticket's change only while none of its commits is behind it,
    and that is false once they reach the default branch: work done on it
    and pushed, or a branch fast-forwarded into it and then given one more
    commit. So the base is trusted only when HEAD is on a branch that is not
    the default one AND no commit reachable from the base names the ticket
    in its subject. A question git cannot answer is a reason, never a pass."""
    branch = _git_lines(top, "symbolic-ref", "--quiet", "--short", "HEAD")
    if not branch:
        return "HEAD is on no branch, so which branch the work is on cannot be told"
    default = scope_base._default_ref(top)  # pylint: disable=protected-access
    if not default:
        return "no default branch to compare HEAD's branch with"
    name = default.split("/", 1)[1] if default.startswith("origin/") else default
    if branch[0] in (name, default):
        return f"HEAD is on the default branch {branch[0]}"
    return _named_behind(top, base, ticket)


def _named_behind(top, base, ticket):
    """Why commits naming `ticket` sit behind `base`, or None. Asked of a
    RECORDED base too (review round 3): `scope_base.py --record` writes HEAD
    when HEAD is the merge-base, which is exactly the successor checkout
    whose earlier commits already reached the default branch, and HEAD's
    branch says nothing about that. A record is still trusted on the default
    branch or a detached HEAD -- it names the start, not a guess from them."""
    subjects = _git_lines(top, "log", "--format=%s", base)
    if subjects is None:
        return f"git could not read the history behind {base[:12]}"
    mention = re.compile(_ID_EDGE.format(re.escape(ticket)), re.IGNORECASE)
    named = [s for s in subjects if mention.search(s)]
    if named:
        return f"{len(named)} commit(s) behind it name {ticket}, e.g. \"{named[0][:60]}\""
    return None


def _unconfirmed(result, stop, reason):
    """`result` as `unknown` for a base that hides or may hide the change --
    and every artifact measured against that base with it (review round 3):
    a `fresh` or `stale` line under an unknown top line is a measurement of
    the wrong diff, and a caller reading `artifacts[]` alone would take it
    as one of the right diff. Each carries the top line's stop as its
    reason; an artifact already unknown keeps its own, and a missing graph
    file stays not applicable -- no base changes either."""
    for item in result["artifacts"]:
        if item["status"] in (FRESH, STALE):
            item.update(status=UNKNOWN, refreshable=False,
                        reason=f"{stop} - measured {item['status']} against it, "
                               "which confirms nothing")
    result.update(status=UNKNOWN, stop=stop, reason=reason)
    return result


def _unmeasured(reason, stop, source):
    return {"status": UNKNOWN, "reason": reason, "stop": stop, "base_source": source,
            "artifacts": [], "documents": NOT_MEASURED}


def ticket_freshness(root, ticket, which=shutil.which):
    """`{"status", "reason", "stop", "base_source", "artifacts": [{"kind",
    "name", "status", "reason", "command", "refreshable"}], "documents": "not
    measured"}`.

    `status` is `unknown` if any artifact is unknown, else `stale` if any is
    stale, else `fresh` -- unless the scope base cannot be trusted, which is
    `unknown` whatever the artifacts say, and then so is every artifact that
    was measured against it. A recorded base is doubted as a fallback is when
    a commit behind it names the ticket. `stop` is None, or the short reason
    no refresh can settle the answer (no base, a base that hides or may hide
    the change, a listing git could not give, an unreadable config).
    `base_source` is `scope_base.resolve`'s source: `record`, or a fallback
    (`merge-base`, `record-fallback`, `head`). `which` finds graphify;
    injectable so a test can say "missing" without editing PATH."""
    top = crew_ticket.toplevel(root)
    base, source, why = scope_base.resolve(top or root, ticket)
    if not top or not base:
        return _unmeasured(f"no scope base for {ticket} ({why})", "no scope base", source)
    try:
        every = set(completion_audit.changed_paths(top, base))
    except RuntimeError as exc:
        return _unmeasured(f"could not list {ticket}'s changes: {exc}",
                           f"git could not list {ticket}'s changes", source)
    try:
        # NUL-separated, decoded as `changed_paths` decodes: a newline-split
        # listing C-quotes a name holding `"`, `\\`, a tab or a newline even
        # under core.quotePath=false, and a quoted name never matches.
        untracked = {p for p in completion_audit._git_fields(  # pylint: disable=protected-access
            top, ["ls-files", "-z", "--others", "--exclude-standard"]) if p}
    except RuntimeError:
        return _unmeasured("git could not list untracked files",
                           "git could not list untracked files", source)
    cfg, unreadable = _read_config(top)
    if cfg is None:
        return _unmeasured(f"config unreadable: {unreadable}, so which diagrams and graph "
                           "to judge cannot be told", "config unreadable", source)

    info = _read_graph(top, cfg)
    graph_out = _relative(top, os.path.dirname(info["path"]))
    diagrams = contained_path(top, _diagrams_dir(cfg), DIAGRAMS_DIR_DEFAULT)
    own = refresh_artifact_paths(top, cfg) + [".work"]
    changed = {p for p in every
               if not _bookkeeping(p) and not any(_reaches(o, p) for o in own)}
    code = sorted(p for p in changed if not _is_noncode(p, graph_out))

    artifacts = _codemaps(top, changed, untracked)
    artifacts += _diagrams(top, diagrams, changed, code, untracked)
    graph = _graph(top, info, graph_out, code, untracked, which)
    if graph:
        artifacts.append(graph)

    statuses = {a["status"] for a in artifacts}
    overall = UNKNOWN if UNKNOWN in statuses else STALE if STALE in statuses else FRESH
    result = {"status": overall, "reason": f"scope base {base[:12]} ({why})", "stop": None,
              "base_source": source, "artifacts": artifacts, "documents": NOT_MEASURED}
    if source == scope_base.RECORDED:
        doubt = _named_behind(top, base, ticket)
        if doubt:
            stop = f"recorded base {base[:12]} may hide {ticket}'s commits"
            return _unconfirmed(result, stop, f"{stop}: {doubt} ({why})")
        return result
    for item in artifacts:
        item["reason"] += " [fallback base]"
    head = _git_head(top)
    hides = head is None or base == head
    if hides:
        what = ("is HEAD itself" if head else
                "could not be compared with HEAD, which git could not read")
        return _unconfirmed(result, "the fallback scope base hides the change",
                            f"scope base {base[:12]} {what}, a fallback ({why}); "
                            "it can hide every committed change, so nothing here "
                            "is confirmed")
    doubt = _fallback_hides(top, base, ticket)
    if doubt:
        stop = f"fallback base {base[:12]} may hide {ticket}'s commits"
        return _unconfirmed(result, stop, f"{stop}: {doubt} ({why})")
    return result

def _render(ticket, result):
    top = f"refresh-check {ticket}: {result['status']} - {result['reason']}"
    if result.get("stop"):
        top += f"; stop - {result['stop']}"
    lines = [top]
    for item in result["artifacts"]:
        line = f"  {item['kind']} {item['name']}: {item['status']} - {item['reason']}"
        if item["refreshable"]:
            line += f"; refresh with {item['command']}"
        elif item["status"] == UNKNOWN:
            line += "; stop - a refresh cannot settle this, report it"
        lines.append(line)
    if not result["artifacts"]:
        if result["status"] in (FRESH, STALE):
            lines.append("  no codemap, diagram or graph cites a path this ticket changed")
        else:
            lines.append(f"  not measured - {result.get('stop') or result['reason']}")
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
    result = ticket_freshness(os.path.abspath(args.root), args.ticket)
    sys.stdout.write(json.dumps(result, indent=2) + "\n" if args.json
                     else _render(args.ticket, result))
    return 0 if result["status"] == FRESH else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

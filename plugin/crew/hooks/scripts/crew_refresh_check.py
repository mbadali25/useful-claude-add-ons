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
           choice `_read_graph`'s `reportTracked` already encodes. While
           graphify would read a secrets-denylisted path the root
           `.graphifyignore` does not exclude, or that cannot be told, the
           graph is `unknown` and not refreshable, whatever its anchor says
           (T-0064, `crew_graph_ignore.coverage`): no command is named.

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

## What is admitted without Touch (T-0094)

The guard's allowance is a path test; the completion audit's is narrower.
`artifact_verdicts` judges each changed artifact of an approved ticket, and
`completion_audit.audit` admits it without Touch only on `True` -- wired by
L-0540, the harness half the owner split from T-0094 on 2026-09-30 (a
tooling change lands alone); until it lands the audit admits the whole dirs
as since 1.0.36. Two questions, each with an observable answer: did a path
the ticket changed REACH it, and is the edit a RE-ANCHOR or a REGENERATION.

Every kind that reads or admits a working-tree file first asks `_on_disk`
(review round 6): the file must be a regular file, with no symlink at its
path or along its dirs, whose mode git sees unchanged from the base copy
and that git does not stage as a link (120000) or gitlink (160000); a
deleted one is never a re-anchor or a regeneration. The kind comes from
the MOST SPECIFIC artifact dir holding the path; two equally specific dirs
are could-not-tell.

  map       `.crew/codemap/<name>.md` (not INDEX, UPGRADE or MIGRATION): in
            the base tree and on disk, a citation in the BASE copy reaches a
            changed path (an edit cannot cite its way in), and `anchor:`
            moved forward from the base's value to a commit that is HEAD or
            behind it (a base anchor that names no commit, or one off HEAD's
            history -- a squash merge -- is moved from by any qualifying
            one; an unchanged anchor text never moved, and nothing moved
            from a base copy with no anchor at all).
            Claims, `path:line` numbers and prose may change with it: that is
            what a refresh writes (`8bbb26d9`); an edit whose anchor did not
            move is not.
  INDEX.md  every line git's diff against the base shows changed (its
            terminator included, so a CR, a BOM or a dropped final newline
            counts) is the row of a map admitted in the same call; a mode
            change is refused.
  diagram   a source (`.mmd`, `.mermaid`) under `docs.diagramsDir`: reached
            through its base copy's `%% Anchors:` line (none: any code
            path), and its provenance sha moved as a map's anchor must. A
            rendered file is admitted beside a same-stem source admitted in
            the same call.
  rule      `.claude/rules/<name>.md` whose bytes equal
            `crew_instructions.expected_rules`, or whose blob git would store
            (clean filters applied: a CRLF checkout under core.autocrlf)
            equals that text's -- regeneration, whatever the
            map did -- or one removed that carried the generated marker and
            that no map expects any more.
  graph     anything under `graph.out`, when the ticket changed a code path.

Anything else under those dirs is `False`: judged against Touch like any
other path. The reach is every path changed since the scope base, merged-in
main paths included, and of RELEASE_BOOKKEEPING only ADMISSION_BOOKKEEPING --
a plugin manifest's version bump reaches the map citing it; CHANGELOG.md,
marketplace.json and the rest change on every release and would reach nearly
every map. The graph's "code change" is read from the whole reach. `None`
is could-not-tell (git could not run or could not answer, a base copy or the
config unreadable, the rule renderer raised): its own value, judged against
Touch, never collapsed into admitted, and its reason says so.

It judges shape and reach, never truth: a re-anchored map may still carry a
wrong claim, and that stays the reviewer's (the maps stay in the review
bundle). The PreToolUse guard keeps admitting the whole dirs, because a
write-time check sees one Edit of a multi-Edit refresh -- claims first,
`anchor:` last -- and would refuse the legitimate intermediate state; the
tree-level audit is where reach and shape are judged.

Never writes a file, the index included, for a library caller (T-0004
imports `ticket_freshness`) as much as for main(): the working-tree diffs go
through `completion_audit.worktree_changes` (`git diff-index` plus a hash of
any stat-dirty file), because `git diff` rewrites .git/index for a stat-dirty
file even under `--no-optional-locks`. Standard library only.
"""
import argparse
import errno
import fnmatch
import io
import json
import os
import re
import shutil
import stat
import subprocess
import sys

import completion_audit
import crew_graph_ignore
import crew_ticket
import scope_base
import crew_common
from crew_common import GIT_TIMEOUT, dict_or_empty, git_out, read_text
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
# stales the map. Segment globs, `crew_ticket.glob_match`'s dialect. Of these
# only ADMISSION_BOOKKEEPING stays in `artifact_verdicts`' admission reach,
# so a version bump admits the re-anchored map citing plugin.json (T-0094).
RELEASE_BOOKKEEPING = (
    "CHANGELOG.md",
    "TODO.md",
    "plugin/PLUGINS.md",
    ".claude-plugin/marketplace.json",
    "**/.claude-plugin/plugin.json",
    "plugin/*/BUDGETS.md",
)
# The one piece of RELEASE_BOOKKEEPING a map's admission reach keeps
# (T-0094 review round 1): a plugin manifest's version bump reaches the map
# citing it. The rest -- CHANGELOG.md, TODO.md, PLUGINS.md, BUDGETS.md, the
# marketplace manifest -- changes on every release and most maps cite one,
# so keeping them would make nearly every map reached by every ticket.
ADMISSION_BOOKKEEPING = ("**/.claude-plugin/plugin.json",)

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
        text = read_text(crew_common.repo_config_file(root, name))
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
        path = crew_common.repo_config_file(root, name)
        present, why = _present(path)
        if present is None:
            return None, f"could not tell whether .crew/{name} exists: {why}"
        if not present:
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


def _present(path):
    """`(True, "")` or `(False, "")` when lstat proves `path` is there or is
    not -- ENOENT, or ENOTDIR for a parent that is not a directory -- and
    `(None, reason)` for any other failure. `os.path.lexists` answers False
    for every failure, so a parent the hook user cannot search read as
    absent: a config naming other artifact dirs became the defaults, and a
    rule still on disk became a removed one (review round 5)."""
    try:
        os.lstat(path)
    except (FileNotFoundError, NotADirectoryError):
        return False, ""
    except (OSError, ValueError) as exc:
        return None, getattr(exc, "strerror", None) or type(exc).__name__
    return True, ""


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


# --------------------------------------------------------------------------
# What is admitted without Touch (T-0094; module docstring)

COULD_NOT_TELL = "could not tell"

# `crew_context.index_covers`'s row regex, the origin: the INDEX.md row of
# `<name>.md`. Only the name is captured here; a re-anchor rewrites the row's
# anchor and Last pass cells, so the whole row is the line that differs.
_INDEX_ROW_RE = re.compile(r"^\|\s*\[`?([A-Za-z0-9_.-]+)\.md`?\]\([^)]*\)\s*\|")


def _git_rc(root, *args):
    """git's return code, or None when git could not run at all."""
    try:
        return subprocess.run(
            ["git", "-C", root, "--no-optional-locks", "--literal-pathspecs", *args],
            capture_output=True, stdin=subprocess.DEVNULL, timeout=GIT_TIMEOUT,
            check=False).returncode
    except (OSError, subprocess.SubprocessError):
        return None


def _git_out(root, *args, data=None):
    """(return code, stdout bytes), or (None, b"") when git could not run.
    `data`, when given, is git's stdin."""
    feed = {"input": data} if data is not None else {"stdin": subprocess.DEVNULL}
    try:
        done = subprocess.run(
            ["git", "-C", root, "--no-optional-locks", "--literal-pathspecs", *args],
            capture_output=True, timeout=GIT_TIMEOUT, check=False, **feed)
    except (OSError, subprocess.SubprocessError):
        return None, b""
    return done.returncode, done.stdout


def _is_ancestor(root, sha, of="HEAD"):
    """True / False / None: `merge-base --is-ancestor` exits 0 when `sha` is
    `of` or behind it, 1 when not, anything else on an error -- which is
    could-not-tell, never "no" (git-merge-base(1))."""
    return {0: True, 1: False}.get(_git_rc(root, "merge-base", "--is-ancestor", sha, of))


def _base_text(root, base, rel):
    """(text, "ok"), (None, "absent") when `rel` is not in `base`'s tree, or
    (None, "error: <why>"). `git_out` returns None on ANY failure, so the
    tree is asked first: absent and unreadable are different answers.
    Review round 7: `cat-file -e <base>:<rel>` exits 128 for a missing path
    AND for a base git cannot read, so the path is looked up in the base's
    listing instead: `ls-tree` exits 0 with no entry for a missing path and
    non-zero for a base it cannot read."""
    spec = f"{base}:{rel}"
    code, out = _git_out(root, "ls-tree", "-z", base, "--", rel)
    if code != 0:
        why = "could not run" if code is None else f"exited {code}"
        return None, f"error: git ls-tree {why}"
    if not out.strip(b"\0"):
        return None, "absent"
    try:
        done = subprocess.run(["git", "-C", root, "--no-optional-locks", "show", spec],
                              capture_output=True, stdin=subprocess.DEVNULL,
                              timeout=GIT_TIMEOUT, check=False)
    except (OSError, subprocess.SubprocessError):
        return None, "error: could not read"
    if done.returncode != 0:
        return None, "error: could not read"
    # Decoded as `read_text` decodes the working copy: a BOM is stripped.
    return done.stdout.decode("utf-8-sig", errors="replace"), "ok"


def _sha_moved(root, old, new):
    """(True | False | None, reason): `new` names a commit, that commit is
    HEAD or behind it, and it is a move FORWARD from the commit `old` names
    (`_moved_from`). An anchor whose text did not change has not moved,
    whatever git can or cannot say about it."""
    if not new:
        return False, "no anchor: line"
    if old == new:
        return False, "anchor did not move"
    if not old:
        # Review round 3: an anchor ADDED is a content edit, not a re-anchor.
        return False, "the base copy has no anchor, so nothing moved from it"
    code = _git_rc(root, "cat-file", "-e", new + "^{commit}")
    if code is None:
        return None, f"{COULD_NOT_TELL}: git could not run"
    if code == 128:
        # Review round 7: 128 is also a short anchor two commits share, as
        # for the base anchor (`_names_no_commit`).
        missing = _names_no_commit(root, new)
        if missing is None:
            return None, f"{COULD_NOT_TELL}: git could not say whether {new[:12]} names a commit"
        if not missing:
            return None, f"{COULD_NOT_TELL}: anchor {new[:12]} is ambiguous"
        return False, f"anchor {new} names no commit"
    if code != 0:
        return None, f"{COULD_NOT_TELL}: git exited {code} reading anchor {new}"
    ancestor = _is_ancestor(root, new)
    if ancestor is None:
        return None, f"{COULD_NOT_TELL}: git could not say whether {new[:12]} is behind HEAD"
    if not ancestor:
        return False, f"anchor {new[:12]} is not reachable from HEAD"
    now = _git_lines(root, "rev-parse", "--verify", new + "^{commit}")
    if not now:
        return None, f"{COULD_NOT_TELL}: git could not resolve {new[:12]}"
    return _moved_from(root, old, now[0])


def _names_no_commit(root, old):
    """Did `cat-file -e <old>^{commit}`'s exit 128 mean the anchor names no
    commit? Git exits 128 for a missing name AND for a short one two
    commit-ish objects share (review round 4), so this is True only when
    proven: `git rev-parse --disambiguate=<old>` lists no object that
    `git cat-file -t` types as commit or tag. Every length is asked, not only
    short ones: 40 hex is a prefix in a sha256 repository. None
    (could-not-tell) when git cannot answer; False when a commit or tag IS
    listed (ambiguous, or it resolves after all)."""
    listed = _git_lines(root, "rev-parse", "--disambiguate=" + old)
    if listed is None:
        return None
    for oid in listed:
        kind = _git_lines(root, "cat-file", "-t", oid)
        if not kind:
            return None
        if kind[0] in ("commit", "tag"):
            return False
    return True


def _moved_from(root, old, now):
    """Has the anchor moved forward from `old` to the resolved commit `now`?
    Three-valued like everything here: a git that cannot say is
    could-not-tell, never "moved" (review round 1). An `old` proven to name
    no commit (`_names_no_commit`: an ambiguous short one is could-not-tell,
    review round 4), or one off HEAD's history, cannot be behind anything, so any
    qualifying `now` has moved (a squash merge drops, or strands, the commit
    a refresh anchored to). An `old` on HEAD's history must be behind `now`:
    no refresh anchors backwards."""
    code = _git_rc(root, "cat-file", "-e", old + "^{commit}")
    if code == 128:
        missing = _names_no_commit(root, old)
        if missing is None:
            return None, f"{COULD_NOT_TELL}: git could not say whether {old[:12]} names a commit"
        if missing:
            return True, "re-anchored"
        return None, f"{COULD_NOT_TELL}: base anchor {old[:12]} is ambiguous"
    if code != 0:
        return None, f"{COULD_NOT_TELL}: git could not read the base anchor {old[:12]}"
    was = _git_lines(root, "rev-parse", "--verify", old + "^{commit}")
    if not was:
        return None, f"{COULD_NOT_TELL}: git could not resolve the base anchor {old[:12]}"
    if was[0] == now:
        return False, "anchor did not move"
    behind_head = _is_ancestor(root, was[0])
    if behind_head is None:
        return None, f"{COULD_NOT_TELL}: git could not say whether {old[:12]} is behind HEAD"
    if not behind_head:
        return True, "re-anchored"
    forward = _is_ancestor(root, was[0], now)
    if forward is None:
        return None, f"{COULD_NOT_TELL}: git could not say whether {now[:12]} follows {old[:12]}"
    if not forward:
        return False, f"anchor moved from {old[:12]} to {now[:12]}, not forward"
    return True, "re-anchored"


def _graph_out(top, cfg):
    """`graph.out` resolved as `crew_freshness._read_graph` resolves it,
    without reading the graph."""
    out = dict_or_empty(cfg.get("graph")).get("out")
    if not isinstance(out, str) or not out:
        out = GRAPH_OUT_DEFAULT
    return _relative(top, contained_path(top, out, GRAPH_OUT_DEFAULT))


def _cited(text):
    """Every path-shaped citation in a map (`_codemaps`'s filter)."""
    return [c for c in dict.fromkeys(_CITATION_RE.findall(text or ""))
            if "/" in c or "." in c]


def _texts(top, base, rel):
    """(base_text, work_text, None), or (None, None, (verdict, reason)) when
    the pair cannot be a re-anchor or cannot be read."""
    before, state = _base_text(top, base, rel)
    if state == "absent":
        return None, None, (False, "new file, not a re-anchor")
    if state != "ok":
        return None, None, (None, f"{COULD_NOT_TELL}: base copy {state}")
    early, data = _on_disk(top, base, rel, "deleted, not a re-anchor")
    if early:
        return None, None, early
    # The bytes `_on_disk` read from the file it proved regular (review round
    # 7), decoded as `read_text` decodes: utf-8-sig, universal newlines.
    after = io.TextIOWrapper(io.BytesIO(data), encoding="utf-8-sig", errors="replace").read()
    return before, after, None


_LINK_MODES = ("120000", "160000")


def _win_final_path(fd):
    """The drive or UNC path of the file open on `fd`, every link and
    junction along it resolved (GetFinalPathNameByHandleW), or None when
    Windows will not say or says it in another form (a volume GUID path)."""
    try:
        import ctypes  # pylint: disable=import-outside-toplevel
        import msvcrt  # pylint: disable=import-outside-toplevel
        from ctypes import wintypes  # pylint: disable=import-outside-toplevel
        final = ctypes.WinDLL("kernel32", use_last_error=True).GetFinalPathNameByHandleW
        final.restype = wintypes.DWORD
        final.argtypes = [wintypes.HANDLE, wintypes.LPWSTR, wintypes.DWORD, wintypes.DWORD]
        handle = msvcrt.get_osfhandle(fd)
        size = final(handle, None, 0, 0)
        buf = ctypes.create_unicode_buffer(size + 1)
        got = final(handle, buf, size + 1, 0)
    except (ImportError, AttributeError, OSError):
        return None
    if not size or not got or got > size:
        return None
    path = buf.value
    if path.startswith("\\\\?\\UNC\\"):
        return "\\\\" + path[8:]
    if path.startswith("\\\\?\\") and path[5:6] == ":":
        return path[4:]
    return None


# Where the file open on a descriptor really is. Only the no-dir_fd branch of
# `_read_regular` asks, and only Windows answers; tests stub it (W-0116).
_FINAL_PATH = _win_final_path if os.name == "nt" else None


def _read_regular(top, rel):
    """(bytes, None), or (None, "symlink" | "absent" | "not regular" | a
    reason). The file is opened WITHOUT following a link at any component:
    on POSIX each directory is opened relative to its parent with
    O_NOFOLLOW, so a link swapped in anywhere after the lstat and realpath
    checks fails the open instead of being read (review round 7). Where
    `os.open` takes no dir_fd (Windows), the path is opened directly and the
    descriptor's file must be the one lstat names, AND the descriptor's own
    final path must be the path the checks proved: lstat follows a directory
    swapped to a link along the path, so it names the same outside file the
    descriptor holds (W-0116). A final path Windows will not give is a
    reason, never a pass."""
    parts = rel.split("/")
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NONBLOCK", 0)
    fds = []
    try:
        if os.open in os.supports_dir_fd and nofollow:
            directory = getattr(os, "O_DIRECTORY", 0)
            fds.append(os.open(os.path.realpath(top), os.O_RDONLY | directory))
            for part in parts[:-1]:
                fds.append(os.open(part, os.O_RDONLY | directory | nofollow, dir_fd=fds[-1]))
            fd = os.open(parts[-1], flags | nofollow, dir_fd=fds[-1])
        else:
            path = os.path.join(top, *parts)
            fd = os.open(path, flags | nofollow)
            fds.append(fd)
            named, opened = os.lstat(path), os.fstat(fd)
            if stat.S_ISLNK(named.st_mode) or (named.st_dev, named.st_ino) != (
                    opened.st_dev, opened.st_ino):
                return None, "symlink"
            if _FINAL_PATH is not None:
                where = _FINAL_PATH(fd)
                if where is None:
                    return None, "Windows did not say where the opened file is"
                expected = os.path.join(os.path.realpath(top), *parts)
                if os.path.normcase(where) != os.path.normcase(expected):
                    return None, "symlink"
        fds.append(fd)
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            return None, "not regular"
        chunks = []
        while True:
            chunk = os.read(fd, 1 << 16)
            if not chunk:
                break
            chunks.append(chunk)
        return b"".join(chunks), None
    except OSError as exc:
        if exc.errno in (errno.ELOOP, errno.ENOTDIR, getattr(errno, "EMLINK", -1)):
            return None, "symlink"
        if exc.errno == errno.ENOENT:
            return None, "absent"
        reason = exc.strerror or type(exc).__name__
        return None, reason
    finally:
        for handle in dict.fromkeys(fds):
            try:
                os.close(handle)
            except OSError:
                pass


_UNREAD = {"symlink": (False, "a symlink, which no refresh writes"),
           "not regular": (False, "not a regular file, which no refresh writes")}


def _on_disk(top, base, rel, deleted):
    """(None, bytes) when `rel` is a regular file reached with no symlink
    along its path and git sees the mode its base copy had -- the bytes are
    that file's, read once through a descriptor opened without following a
    link, before git is asked anything, and they are what the caller judges
    (review round 7: a check-then-open by path read whatever a swap put
    there). Otherwise ((verdict, reason), None). Review round 6: `read_text`
    followed a symlink, so a map replaced by a link to external re-anchored
    text was admitted while git stores only the link, and nothing asked
    whether a rendered diagram or a graph file still existed. A refresh
    writes regular files in place: a link at the path or along it, a changed
    mode, or a missing file is not one. `deleted` is the reason for a file
    lstat proves absent."""
    path = os.path.join(top, *rel.split("/"))
    try:
        info = os.lstat(path)
    except (FileNotFoundError, NotADirectoryError):
        return (False, deleted), None
    except (OSError, ValueError) as exc:
        why = getattr(exc, "strerror", None) or type(exc).__name__
        return (None, f"{COULD_NOT_TELL}: whether {rel} exists: {why}"), None
    if stat.S_ISLNK(info.st_mode):
        return _UNREAD["symlink"], None
    if not stat.S_ISREG(info.st_mode):
        return _UNREAD["not regular"], None
    named = os.path.normcase(os.path.join(os.path.realpath(top), *rel.split("/")))
    if os.path.normcase(os.path.realpath(path)) != named:
        return (False, "reached through a symlink, which no refresh writes"), None
    data, why = _read_regular(top, rel)
    if data is None:
        if why in _UNREAD:
            return _UNREAD[why], None
        if why == "absent":
            return (False, deleted), None
        return (None, f"{COULD_NOT_TELL}: could not read {rel}: {why}"), None
    # The mode git sees against the base in the working tree, then in the
    # index, which is what `git commit` records: under core.fileMode=true the
    # worktree diff reads the mode from the disk, so a mode staged with
    # `update-index --chmod=+x` while the file stayed 644 reached only the
    # index and was admitted (W-0117). Then the mode it stages: a
    # `core.symlinks=false` checkout leaves a link as a regular file that git
    # stores as 120000.
    for cached in ((), ("--cached",)):
        code, out = _git_out(top, "diff", "--no-ext-diff", "--raw", "--no-renames", "-z",
                             *cached, base, "--", rel)
        if code != 0:
            why = "could not run" if code is None else f"exited {code}"
            name = " ".join(("git diff --raw",) + cached)
            return (None, f"{COULD_NOT_TELL}: {name} of {rel} {why}"), None
        for record in out.split(b"\0"):
            if record.startswith(b":"):
                old, new = record[1:].decode("ascii", "replace").split(" ")[:2]
                if "000000" not in (old, new) and old != new:
                    return (False, f"mode changed from {old} to {new}, which no refresh does"), None
    code, out = _git_out(top, "ls-files", "-s", "-z", "--", rel)
    if code != 0:
        why = "could not run" if code is None else f"exited {code}"
        return (None, f"{COULD_NOT_TELL}: git ls-files of {rel} {why}"), None
    for record in out.split(b"\0"):
        mode = record.decode("ascii", "replace").split(" ", 1)[0]
        if mode in _LINK_MODES:
            return (False, f"stored as {mode}, which no refresh writes"), None
    return None, data


def _map_verdict(top, base, rel, reach):
    before, after, early = _texts(top, base, rel)
    if early:
        return early
    # The BASE copy's citations only: an edit cannot cite its way into reach.
    if not _reached(_cited(before), reach):
        return False, "no changed path reaches it"
    was, now = _ANCHOR_RE.search(before), _ANCHOR_RE.search(after)
    return _sha_moved(top, was.group(1) if was else None, now.group(1) if now else None)


_HUNK_RE = re.compile(rb"^@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@")


def _diff_lines(out):
    """(lines, mode) from a `git diff -U0` of one path: every added line as
    ("line <n>", text) then every removed one as ("base line <n>", text),
    each with its terminator (a CR survives; a missing final newline makes
    the last line differ), and whether the diff changes the file's mode."""
    added, removed, mode, old, new = [], [], False, 0, 0
    hunk = None
    for raw in out.split(b"\n"):
        head = _HUNK_RE.match(raw)
        if head:
            hunk, old, new = True, int(head.group(1)), int(head.group(2))
        elif hunk is None:
            mode = mode or raw.startswith((b"old mode ", b"new mode "))
        elif raw.startswith(b"+"):
            added.append((f"line {new}", raw[1:].decode("utf-8", "surrogateescape")))
            new += 1
        elif raw.startswith(b"-"):
            # Both sides: a pure deletion has no new-side line at all.
            removed.append((f"base line {old}", raw[1:].decode("utf-8", "surrogateescape")))
            old += 1
    return added + removed, mode


def _index_verdict(top, base, rel, admitted):
    _before, _after, early = _texts(top, base, rel)
    if early:
        return early
    # The lines git sees change, from git's own diff of the base against the
    # working tree with its filters applied -- not a diff of decoded text,
    # which `read_text` strips of CRs, a BOM and the final newline (review
    # round 3), so a byte-only edit differed on no line and was admitted.
    code, out = _git_out(top, "diff", "--no-ext-diff", "--no-textconv", "--no-color",
                         "--no-renames", "--text", "-U0", base, "--", rel)
    if code != 0:
        why = "could not run" if code is None else f"exited {code}"
        return None, f"{COULD_NOT_TELL}: git diff of {rel} {why}"
    # A mode change is refused before this, by `_on_disk` in `_texts`
    # (review round 6 made that check every kind's; this branch was then
    # unreachable, and its sabotage entry went green).
    lines, _mode = _diff_lines(out)
    for where, line in lines:
        row = _INDEX_ROW_RE.match(line)
        if not row or row.group(1) not in admitted:
            return False, f"INDEX.md {where} is not the row of a re-anchored map"
    return True, "rows of re-anchored maps only"


def _diagram_verdict(top, base, rel, reach, code):
    before, after, early = _texts(top, base, rel)
    if early:
        return early
    # The BASE copy's `%% Anchors:` only, as for a map's citations.
    declared = _declared(before)
    if declared is None:
        reached = code
    else:
        reached = _reached(declared, reach)
    if not reached:
        return False, "no changed path reaches it"
    now = _DIAGRAM_ANCHOR_RE.search(after)
    if not now:
        return False, "no provenance line"
    was = _DIAGRAM_ANCHOR_RE.search(before)
    return _sha_moved(top, was.group(1) if was else None, now.group(1))


def _rule_verdict(top, base, rel, expected):
    path = os.path.join(top, *rel.split("/"))
    key = os.path.normcase(os.path.normpath(path))
    present, why = _present(path)
    if present is None:
        return None, f"{COULD_NOT_TELL}: whether {rel} exists: {why}"
    if present:
        # Read once, by `_on_disk`, and an unreadable file is could-not-tell
        # BEFORE any comparison: an unreadable rule no map expects compared
        # None == None and was admitted as regenerated (review round 2).
        early, data = _on_disk(top, base, rel, "deleted, not a regeneration")
        if early:
            return early
        want = expected.get(key)
        if want is not None:
            # BYTES, as `crew_instructions._write` writes them: decoded text
            # hid a CRLF and a BOM (review round 3).
            want = want.encode("utf-8")
            if data == want:
                return True, "regenerated"
            # ...and as git stores them, so a CRLF checkout under
            # core.autocrlf is still the regenerated rule.
            got, wanted = _stored_blob(top, rel, data), _stored_blob(top, rel, want)
            if got is None or wanted is None:
                return None, f"{COULD_NOT_TELL}: git could not hash {rel}"
            if got == wanted:
                return True, "regenerated (as git stores it)"
        return False, ("bytes differ from expected_rules (regenerate with "
                       "crew_instructions.py rules)")
    if key in expected:
        return False, "removed, but a map still expects it"
    import crew_instructions  # pylint: disable=import-outside-toplevel
    before, state = _base_text(top, base, rel)
    if state == "ok" and crew_instructions.MARKER in before[:2000]:
        return True, "a generated rule no map expects, removed"
    if state in ("ok", "absent"):
        return False, "removed, but it was not generated"
    return None, f"{COULD_NOT_TELL}: base copy {state}"


def _stored_blob(top, rel, data):
    """The object id git would store for `data` at `rel`, its clean filters
    (core.autocrlf, eol attributes) applied, or None. Hashes only: no object
    is written."""
    code, out = _git_out(top, "hash-object", f"--path={rel}", "--stdin", data=data)
    oid = out.decode("ascii", "replace").strip()
    return oid if code == 0 and oid else None


_CODEMAP_DIR, _RULES_DIR = REFRESH_ARTIFACT_PATHS[0][1], REFRESH_ARTIFACT_PATHS[3][1]


def _claims(rel, dirs, diagrams, graph_out):
    """[(dir, owner)] for every artifact dir in `dirs` that holds `rel`,
    the most specific (most path segments) first."""
    owners = ((_CODEMAP_DIR, "codemap"), (diagrams, "diagrams"), (_RULES_DIR, "rules"),
              (graph_out, "graph"))
    held = [(d, o) for d, o in owners if d and d in dirs and d != rel and _reaches(d, rel)]
    return sorted(held, key=lambda claim: -len(claim[0].split("/")))


def _kind(rel, dirs, diagrams, graph_out):
    """Which admission rule judges `rel`: map, index, not-subsystem, diagram,
    rendered, rule, graph, overlap, or other. The MOST SPECIFIC artifact dir
    holding `rel` decides (review round 6: branch order classified graph
    files under a nested `graph.out` as rendered diagrams); two equally
    specific dirs are "overlap", which is could-not-tell."""
    held = _claims(rel, dirs, diagrams, graph_out)
    if not held:
        return "other"
    if len(held) > 1 and len(held[0][0].split("/")) == len(held[1][0].split("/")):
        return "overlap"
    owner = held[0][1]
    parts = rel.split("/")
    parent, name = "/".join(parts[:-1]), parts[-1]
    if owner == "codemap":
        if parent != _CODEMAP_DIR or not name.endswith(".md"):
            return "other"
        if name == "INDEX.md":
            return "index"
        return "not-subsystem" if name in _NOT_SUBSYSTEMS else "map"
    if owner == "diagrams":
        return "diagram" if os.path.splitext(name)[1].lower() in _DIAGRAM_EXTS else "rendered"
    if owner == "rules":
        return "rule" if parent == _RULES_DIR and name.endswith(".md") else "other"
    return "graph"


def artifact_verdicts(top, base, reach, artifacts, cfg=None):
    """{rel: (verdict, reason)} for every path in `artifacts` (changed paths
    `is_refresh_artifact` accepts). verdict True = admitted without Touch,
    False = judged against Touch, None = could not tell (judged against
    Touch; the reason starts with COULD_NOT_TELL). `reach` is every path
    changed since `base`; the artifact dirs and `.work` are removed from it
    here, and so is RELEASE_BOOKKEEPING except ADMISSION_BOOKKEEPING for
    maps and diagrams (module docstring). `cfg` defaults
    to this repo's crew config; one that exists and cannot be read leaves
    every artifact could-not-tell, as it does `ticket_freshness`."""
    artifacts = list(dict.fromkeys(artifacts))
    if cfg is None:
        cfg, unreadable = _read_config(top)
        if cfg is None:
            return {p: (None, f"{COULD_NOT_TELL}: config unreadable: {unreadable}")
                    for p in artifacts}
    dirs = refresh_artifact_paths(top, cfg)
    own = dirs + [".work"]
    reach = sorted(p for p in dict.fromkeys(reach) if not any(_reaches(o, p) for o in own))
    graph_out = _graph_out(top, cfg)
    diagrams = _relative(top, contained_path(top, _diagrams_dir(cfg), DIAGRAMS_DIR_DEFAULT))
    diagrams = diagrams if diagrams in dirs else None
    # The graph: any code path, bookkeeping included (graphify rebuilds on
    # every commit). Maps and diagrams: a manifest bump reaches the map
    # citing it, the rest of the bookkeeping reaches nothing.
    graph_code = [p for p in reach if not _is_noncode(p, graph_out)]
    reach = [p for p in reach if _in_admission_reach(p)]
    code = [p for p in graph_code if p in reach]
    kinds = {p: _kind(p, dirs, diagrams, graph_out) for p in artifacts}
    out = {}

    def judge(kind, fn):
        for rel in [p for p in artifacts if kinds[p] == kind]:
            try:
                out[rel] = fn(rel)
            except Exception as exc:  # noqa: BLE001  pylint: disable=broad-except
                out[rel] = (None, f"{COULD_NOT_TELL}: {type(exc).__name__} while judging it")

    judge("map", lambda rel: _map_verdict(top, base, rel, reach))
    admitted = {p.rsplit("/", 1)[1][:-len(".md")] for p in artifacts
                if kinds[p] == "map" and out[p][0] is True}
    judge("index", lambda rel: _index_verdict(top, base, rel, admitted))
    judge("not-subsystem", lambda rel: (False, "not a subsystem map"))
    judge("diagram", lambda rel: _diagram_verdict(top, base, rel, reach, code))
    judge("rendered", lambda rel: _rendered_verdict(top, base, rel, kinds, out))
    if any(kinds[p] == "rule" for p in artifacts):
        expected = _expected_rules(top)
        if isinstance(expected, str):
            judge("rule", lambda rel: (None, f"{COULD_NOT_TELL}: {expected}"))
        else:
            judge("rule", lambda rel: _rule_verdict(top, base, rel, expected))
    judge("graph", lambda rel: _graph_verdict(top, base, rel, graph_code))
    judge("overlap", lambda rel: (None, f"{COULD_NOT_TELL}: artifact dirs " + " and ".join(
        f"{d} ({o})" for d, o in _claims(rel, dirs, diagrams, graph_out)[:2])
        + " are equally specific and both hold it"))
    judge("other", lambda rel: (False, "not a refresh artifact of a kind the audit admits"))
    return out


def _rendered_verdict(top, base, rel, kinds, out):
    """A rendered diagram is admitted beside its same-stem source, in the same
    dir (the source's extension compared case-folded), when that source
    changed and was admitted -- and it is still a regular file on disk
    (review round 6: a `git rm` of it was admitted). A new one, with no base
    copy, may be what the regeneration wrote."""
    early, _data = _on_disk(top, base, rel, "deleted, not a regeneration")
    if early:
        return early
    stem = os.path.splitext(rel)[0]
    # Paired as `_kind` classifies a source: by stem, the extension
    # case-folded (review round 4: `flow.MMD` is a source, so is its pair).
    sources = [p for p, k in kinds.items() if k == "diagram"
               and os.path.splitext(p)[0] == stem
               and os.path.splitext(p)[1].lower() in _DIAGRAM_EXTS]
    for source in sources:
        if out.get(source, (False,))[0] is True:
            return True, f"rendered beside the re-anchored {source.rsplit('/', 1)[-1]}"
    name = stem.rsplit("/", 1)[-1]
    return False, f"rendered file whose source {name}.mmd was not re-anchored"


def _graph_verdict(top, base, rel, graph_code):
    """Anything under `graph.out` is admitted when the ticket changed a code
    path and the file is still a regular file on disk (review round 6, the
    rendered diagram's neighbour: a deleted graph file was admitted)."""
    early, _data = _on_disk(top, base, rel, "deleted, not a regeneration")
    if early:
        return early
    if graph_code:
        return True, "rebuilt after a code change"
    return False, "graph changed with no code change since the base"


def _expected_rules(top):
    """`crew_instructions.expected_rules`, keyed by normalised absolute path,
    or a string saying why it could not be rendered."""
    try:
        import crew_instructions  # pylint: disable=import-outside-toplevel
        rendered = crew_instructions.expected_rules(top)
    except Exception as exc:  # noqa: BLE001  pylint: disable=broad-except
        return f"expected_rules raised {type(exc).__name__}"
    return {os.path.normcase(os.path.normpath(k)): v for k, v in rendered.items()}


def _bookkeeping(path):
    return any(crew_ticket.glob_match(path, glob) for glob in RELEASE_BOOKKEEPING)


def _in_admission_reach(path):
    """Can a change to `path` reach a map or a diagram in `artifact_verdicts`?"""
    return not _bookkeeping(path) or any(crew_ticket.glob_match(path, glob)
                                         for glob in ADMISSION_BOOKKEEPING)


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


def _graph_ignore_refusal(root, graph_out, command):
    """A non-refreshable `unknown` graph entry while graphify would read a
    secrets-denylisted path (T-0064), else None. Running `command` then
    would put the secret in the graph, so no refresh may be named; the fix
    is `crew_graph_ignore.py --write`, which this check never runs: it is
    read-only, and that write is outside the ticket's Touch."""
    cover = crew_graph_ignore.coverage(root)
    if cover["status"] == crew_graph_ignore.UNCOVERED:
        paths = cover["uncovered"]
        shown = crew_graph_ignore.listed(paths, 3)
        return _entry("graph", graph_out, UNKNOWN,
                      f"graphify would read {len(paths)} secrets-denylisted path(s) "
                      f".graphifyignore does not exclude: {shown}; run "
                      f"{crew_graph_ignore.FIX}, and if a graph was built before, see "
                      "crew-graph SKILL 'Tainted graph'", command, refreshable=False)
    if cover["status"] != crew_graph_ignore.COVERED:
        return _entry("graph", graph_out, UNKNOWN,
                      f"denylist coverage unknown: {cover['reason']}", command,
                      refreshable=False)
    return None


def _graph(root, info, graph_out, code, untracked, which):
    command = ("graphify update ." if info["reportTracked"]
               else "graphify . --no-viz --code-only")
    if not info["present"]:
        return _entry("graph", graph_out, NOT_APPLICABLE,
                      f"no graph file at {graph_out}/graph.json", command)
    if not code:
        return None
    refused = _graph_ignore_refusal(root, graph_out, command)
    if refused:
        return refused
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

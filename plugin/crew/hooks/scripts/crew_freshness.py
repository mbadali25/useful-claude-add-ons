"""Is the recorded knowledge still current: codemaps, the graph, diagrams.

Split out of `crew_state.py` on 2026-09-14, and NOT because the file was
untidy. `.pylintrc` raised `max-module-lines` to 3300 for the endpoint ledger
and wrote the terms of the next raise into the comment beside it: "If this
line needs raising a third time, split the module instead." `crew_guards` was
the split taken rather than that raise; this is the next one. `crew_state.py`
had settled at 3299 against the 3300 ceiling, one line under it, and had been
bought room three times by shaving comments -- which trades the reasoning a
reader needs for a number a linter reads, and leaves the module exactly as
large as it was.

The seam is the one this slice already had. Every name here answers one
question -- "has the thing this artefact was derived from moved since the
artefact recorded it" -- and answers it by comparing a recorded commit sha
against HEAD, never an mtime. Three artefacts ask it: the codemaps under
`.crew/codemap/` (`read_knowledge`), graphify's `graph.json` (`_read_graph`),
and the Mermaid sources under `docs/diagrams/` (`read_diagrams`).

What all three share is `GRAPH_NONCODE_PATHS`, the deny-list that gives all
three a fixpoint: `.crew/**` and `docs/**` hold the artefacts themselves, so
the commit that RECORDS a refresh does not immediately un-refresh it.
`_moved_since` is shared by two of them, not three -- `read_knowledge` and
`read_diagrams` call it, and with it the two citation readers that narrow the
question to the paths each artefact actually names. `_read_graph` inlines the
same diff instead of calling it, because its exclusion set has to add the
configurable `graph.out` on top of the constant list, and a function taking a
deny-list as an argument would be a worse seam than one copy of three lines.

None of them touches the work log, the metrics table, the role
table, the provider resolution or the dispatch record that the rest of
`crew_state` is about. `crew_common`, `crew_endpoints` and `crew_guards` were
split off the same file on the same principle.

`contained_path` comes across rather than staying behind, and it is the one
name here that is not about freshness -- it is a containment check, and its
docstring says why it exists. Two of its three callers (`_read_graph` and
`read_diagrams`) are in this module, so leaving it in `crew_state` would make
this module import from the module that imports it. `crew_state` re-exports it
for the third caller, `handoff_path`, and for `pm_brief`, which already spells
it `crew_state.contained_path`.

**Nothing here imports `crew_state`, and nothing may.** `crew_state`
re-exports these names so its callers did not have to change, and an import in
the other direction would be a genuine cycle -- the same rule `crew_guards`'s
docstring states for itself, and `crew_config`'s before it.

A re-export is a SECOND BINDING, not an alias. `tests/test_module_split.py`
asserts every one of them resolves to the object THIS module defines, and that
nothing in the suite patches one through `crew_state` -- a string-keyed patch
there rebinds a copy the reading function never sees, which is a guard failing
open while wearing the label of a check that happened.

Standard library only, and every read fails soft, for the reason `crew_state`
does: this runs from a SessionStart hook, where an exception breaks every
session opened in the repository.
"""
import os
import re

from crew_common import dict_or_empty, git_out, read_text


_ANCHOR_RE = re.compile(
    r"^anchor:\s*(?:\S*@)?([0-9a-f]{7,40})\s*$", re.MULTILINE | re.IGNORECASE
)

# Files under .crew/codemap/ that describe the map rather than a subsystem.
_NOT_SUBSYSTEMS = frozenset({"INDEX.md", "UPGRADE.md", "MIGRATION.md"})

# Where the graph lives when config does not say. Defined here rather than in
# crew_upgrade because this module has to resolve it with no config at all.
def contained_path(root, value, default):
    """`root/value`, or `root/default` when `value` escapes the repository.

    Config is hand-edited and, in a cloned repo, is written by whoever wrote
    the repo. A relative path with `..`, an absolute path, or a UNC path all
    resolve outside `root` -- and these values are used to READ files that
    then reach the model's context (`context.handoffPath` under
    `context.autoResume` injects the whole file at session start). A repo that
    can name any file on the machine and have it read into a session is a repo
    that can exfiltrate through the next thing the session says.

    So: resolve, compare against the resolved root, and fall back to the
    default rather than raising. A hook that dies on a bad config value is a
    hook that stops every session in the repo; one that quietly reads the
    right file instead is the behaviour anyone would have wanted.

    `os.path.realpath` on both sides, so a symlink out of the tree is caught
    too, and `os.path.commonpath` rather than `startswith` -- `/repo-evil`
    starts with `/repo` and is not inside it.
    """
    if not isinstance(value, str) or not value.strip():
        value = default
    base = os.path.realpath(root)
    candidate = os.path.realpath(os.path.join(base, value))
    try:
        inside = os.path.commonpath([base, candidate]) == base
    except ValueError:
        inside = False          # different drives on Windows
    return candidate if inside else os.path.realpath(
        os.path.join(base, default))


GRAPH_OUT_DEFAULT = "graphify-out"

# Where committed Mermaid sources live when config does not say. Matches the
# layout crew-diagrams/SKILL.md documents.
DIAGRAMS_DIR_DEFAULT = "docs/diagrams"

# Mermaid sources this module treats as diagram coverage. `.mermaid` is the
# other extension in common use; both are plain text with the same provenance
# header, so both are read the same way.
_DIAGRAM_EXTS = (".mmd", ".mermaid")

# Diagrams cannot use _ANCHOR_RE. That one requires the line to START with
# `anchor:`, which is fine for a Markdown code map and impossible in a Mermaid
# source: a bare `anchor:` line there is a syntax error, so the provenance has
# to live inside a `%%` comment. Reusing the codemap regex here reads every
# correctly-anchored diagram as unanchored, and therefore as stale -- which
# looks like the feature working right up until nothing is ever current.
#
# The documented header is `%% Generated from <repo>@<short-sha> on <date>.`
# (crew-diagrams/SKILL.md). `%% anchor: <sha>` is accepted too because it is
# the obvious thing to hand-write, and rejecting it would fail closed on a file
# whose provenance is right there in the text. `%%` itself is optional for the
# same reason -- tolerance costs nothing, a false "stale" costs a redraw.
_DIAGRAM_ANCHOR_RE = re.compile(
    r"^\s*(?:%%\s*)?(?:generated\s+from|anchor:)\s*(?:\S*@)?"
    r"([0-9a-f]{7,40})\b",
    re.MULTILINE | re.IGNORECASE,
)

# The three views crew-diagrams names as the standing set: what the system is
# made of, how data moves through it, and how a process runs. A crew repo
# missing a whole kind is missing coverage, not merely out of date -- which is
# a different finding with a different fix, so they are tracked separately.
#
# Matching is on the FILENAME STEM, prefix-wise, because the skill's own layout
# is `architecture.mmd`, `data-flow-orders.mmd`, `process-refund.mmd` -- one
# architecture diagram but a data-flow and a process diagram PER AREA. Requiring
# an exact `data-flow.mmd` would report a repo with four of them as having none.
DIAGRAM_KINDS = ("architecture", "data-flow", "process")

# graphify writes the commit it built at into graph.json itself, as a
# top-level "built_at_commit" string field -- see _built_at_commit.
_BUILT_AT_RE = re.compile(rb'"built_at_commit"\s*:\s*"([0-9a-f]{7,40})"')

# The key sits near the end of the file (graphify writes metadata last), so a
# bounded tail read finds it in O(1) time regardless of graph size -- this
# runs on every session start, and a real graph is far bigger than a fixture.
_GRAPH_TAIL_BYTES = 65536


def _built_at_commit(path):
    """The full commit sha graphify stamped into graph.json, or None.

    Reads only the last _GRAPH_TAIL_BYTES of the file rather than parsing the
    whole thing -- measured at 0.12ms for a tail regex against 10.34ms for a
    full json.load on a 1.8MB graph, and this runs on every session start.
    Falls back to a whole-file scan when the file is bigger than the tail
    window and the key wasn't found in it, in case a differently-shaped
    graph.json puts the field somewhere else. Any read failure, or no key
    found anywhere, returns None -- unknown provenance is not freshness.
    """
    try:
        size = os.path.getsize(path)
        with open(path, "rb") as handle:
            if size > _GRAPH_TAIL_BYTES:
                handle.seek(-_GRAPH_TAIL_BYTES, os.SEEK_END)
            chunk = handle.read()
    except (OSError, ValueError):
        return None

    found = _BUILT_AT_RE.search(chunk)
    if found:
        return found.group(1).decode("ascii")
    if size <= _GRAPH_TAIL_BYTES:
        return None

    try:
        with open(path, "rb") as handle:
            whole = handle.read()
    except OSError:
        return None
    found = _BUILT_AT_RE.search(whole)
    return found.group(1).decode("ascii") if found else None


# Paths whose contents cannot invalidate a graph OF THE CODE, used by
# _read_graph to tell "HEAD moved" apart from "the code moved". Deliberately
# short and deliberately a DENY-list: anything not named here still counts as
# code, so a path nobody anticipated stales the graph rather than silently
# not doing so. The graph's own output directory is excluded separately by
# _read_graph, because it is configurable (`graph.out`) and so is not a
# constant.
GRAPH_NONCODE_PATHS = (
    "docs/**",
    ".crew/**",
    ".work/**",
)

# A repo-relative path cited in a codemap, with or without a `:line` suffix.
#
# NO EXTENSION ALLOWLIST, deliberately. This listed py|sh|ps1|ya?ml|json|md for
# one release -- the set THIS repo contains -- and crew ships elsewhere.
# Measured: a map citing `src/OrderService.cs:1` beside `appsettings.json`
# yielded only the json, so once the C# moved the map read `behind: []`. A
# .NET, TS, Go or Terraform repo got a freshness signal structurally unable to
# see its own source: this repo's named bug, one rung from the fix that
# introduced it. So match anything path-shaped (a `/` or a dot, which keeps
# prose and `--flags` out) and let existence in `_cited_paths` be the only
# gate. A rotted citation then narrows nothing and the caller widens instead.
_CITED_PATH_RE = re.compile(
    r"`([A-Za-z0-9_][A-Za-z0-9_.@+-]*(?:/[A-Za-z0-9_.@+-]+)*"
    r"(?:\.[A-Za-z0-9_+-]+)?)(?::\d+)?`"
)

# What a diagram declares it was drawn from: `%% Anchors: a/b.py, c/d.sh`.
# A diagram DOES cite paths. The first version of this code asserted the
# opposite -- "it draws nodes, not path:line" -- and used the whole-tree
# deny-list on that basis; measured here, 4 of 6 diagrams had ZERO changed
# files among their own anchors while the deny-list called all 6 stale. The
# wrong claim was also the reason the count would not come down.
_DIAGRAM_ANCHORS_RE = re.compile(
    r"^\s*%%\s*Anchors:\s*(.+)$", re.MULTILINE | re.IGNORECASE
)


def _moved_since(root, sha, head, paths=None):
    """Did anything the caller cares about change between `sha` and HEAD?

    Returns True (moved), False (nothing moved), or None (could not tell).
    None is NOT False: an unresolvable sha, a missing git, or a diff that
    fails lands there, and every caller resolves it to stale. An unknown must
    not collapse into the safe-looking value.

    With `paths`, the question is asked of exactly those. Without them it is
    asked of the whole tree MINUS what cannot change the artefact -- a
    deny-list, so a path nobody thought about still counts.

    That exclusion is what gives these triggers a FIXPOINT: `.crew/**` and
    `docs/**` hold the codemaps and diagrams, so the commit that RECORDS a
    refresh does not immediately un-refresh it. Without it, re-anchoring
    cleared the trigger and the commit saving the re-anchor fired it again,
    forever -- which is why `knowledgeBehind` sat at 10 no matter who
    refreshed what.
    """
    if not sha or not head:
        return None
    if paths:
        changed = git_out(root, "diff", "--name-only", f"{sha}..{head}",
                          "--", *paths)
    else:
        excludes = [f":(exclude){g}" for g in GRAPH_NONCODE_PATHS]
        changed = git_out(root, "diff", "--name-only", f"{sha}..{head}",
                          "--", ".", *excludes)
    if changed is None:
        return None
    return changed != ""


def _cited_paths(root, text):
    """Paths a map cites that still exist. Existence is the only filter, and a
    deleted citation is dropped so it cannot narrow to something unchangeable.
    """
    found = []
    for path in dict.fromkeys(_CITED_PATH_RE.findall(text or "")):
        if os.path.exists(os.path.join(root, path)):
            found.append(path)
    return found


def _diagram_paths(root, text):
    """The paths a diagram declares in its `%% Anchors:` line, if it has one."""
    found = _DIAGRAM_ANCHORS_RE.search(text or "")
    if not found:
        return []
    paths = []
    for raw in found.group(1).split(","):
        path = raw.strip().strip("`")
        if path and os.path.exists(os.path.join(root, path)):
            paths.append(path)
    return paths


def _read_graph(root, cfg):
    """Graph presence, and whether it was built at the current HEAD.

    Freshness is a recorded sha, never a timestamp. Comparing graph.json's
    mtime against HEAD's commit time looks reasonable and is wrong: `git pull`
    brings in commits authored earlier than the graph was built, so a graph
    that knows nothing about the pulled code reports itself current. That is
    the false-freshness failure this module exists to avoid.

    The sha comes from graphify's own `built_at_commit` field, written
    atomically with the graph -- see _built_at_commit. No such field means
    the graph was built outside crew, so its provenance is unknown -- and
    unknown resolves to stale, which is the honest direction.
    """
    out = dict_or_empty(cfg.get("graph")).get("out")
    # A well-shaped graph block can still carry a wrong-typed "out" -- a dict
    # passes dict_or_empty but `os.path.join` raises TypeError on a non-str.
    if not isinstance(out, str) or not out:
        out = GRAPH_OUT_DEFAULT
    out_dir = contained_path(root, out, GRAPH_OUT_DEFAULT)
    path = os.path.join(out_dir, "graph.json")

    # Which refresh command to recommend is a fact about THIS repo, not a
    # constant. A repo that tracks GRAPH_REPORT.md beside graph.json needs
    # `graphify update .`, which keeps the pair consistent; one that does not
    # wants `graphify . --no-viz --code-only`, where --no-viz skips the report
    # precisely because nothing stores it. Crew ships to many repos and used to
    # name the second unconditionally, so in a repo of the first kind its own
    # pulse recommended the command that repo's CLAUDE.md says not to use.
    # Asked of git, not of the filesystem: an untracked report is a local
    # artefact and does not make the pair a thing this repo maintains.
    report = os.path.join(out_dir, "GRAPH_REPORT.md")
    rel = os.path.relpath(report, root).replace("\\", "/")
    report_tracked = bool(git_out(root, "ls-files", "--", rel))

    if not os.path.exists(path):
        return {"present": False, "current": False, "builtAt": None,
                "path": path, "reportTracked": report_tracked}

    built = _built_at_commit(path)
    head = git_out(root, "rev-parse", "--short=7", "HEAD")
    if not built or not head:
        return {"present": True, "current": False, "builtAt": built,
                "path": path, "reportTracked": report_tracked}

    # Fast path, and the only one that needs no second git call.
    if built[:7] == head[:7]:
        return {"present": True, "current": True, "builtAt": built,
                "path": path, "reportTracked": report_tracked}

    # Not HEAD -- but "not HEAD" is not the same as "stale", and treating it
    # that way gave this trigger NO FIXPOINT. graphify-out/ is a TRACKED
    # artefact in the repos this runs in, so recording a rebuild takes a
    # commit, and that commit moves HEAD past the sha the rebuild just
    # stamped. Clearing graphStale therefore re-fired it, every time, forever.
    # Measured in AI-Software on 2026-09-13: cleared once, fired again on the
    # same action, taking that session's trigger count from four to five.
    #
    # The question this check actually wants answered is whether any CODE
    # moved since the graph was built. So ask git exactly that, over
    # everything EXCEPT the paths that cannot change a graph of the code: the
    # graph's own output directory, crew's own state, and docs.
    #
    # The exclusion list is a DENY-list on purpose. A path nobody thought
    # about still counts as code and still stales the graph, so the failure
    # direction stays honest -- the same reason a missing `built_at_commit`
    # sidecar resolves to stale rather than to fresh.
    #
    # This mirrors `read_knowledge` below -- its
    # `_moved_since(..., _cited_paths(root, body))` call measures each
    # subsystem against its OWN pathspec rather than against all of HEAD, and
    # reports current for trees this function used to call stale. It named
    # `verify-anchors.py` until 2026-09-14; no such file has ever existed in
    # this repo, and both functions were in `crew_state.py` when that was
    # written.
    trimmed = out.rstrip("/")
    excludes = [f":(exclude){trimmed}/**"]
    excludes += [f":(exclude){g}" for g in GRAPH_NONCODE_PATHS]
    changed = git_out(root, "diff", "--name-only", f"{built}..{head}",
                      "--", ".", *excludes)
    # None means the diff could not run at all -- an unresolvable `built` sha
    # (squash-merged, rebased away, or garbage-collected) lands here. Unknown
    # resolves to stale, the honest direction.
    current = changed is not None and changed == ""
    return {"present": True, "current": current, "builtAt": built,
            "path": path, "reportTracked": report_tracked}


def read_knowledge(root, cfg):
    """Codemap inventory plus graph freshness.

    `behind` names maps whose anchor RESOLVES to a commit and is not HEAD.
    That is not the same as wrong -- see the design note in the plan. Without
    git there is no HEAD to compare against, so nothing is claimed either way.

    `unresolvable` names maps whose anchor is absent, or names an object this
    repository does not contain. It is a THIRD value, exclusive of `behind`,
    and the distinction decides what the reader does next:

      behind        the anchor resolves, so `git diff --name-only
                    <anchor>..HEAD -- <the paths the map cites>` runs. Empty
                    output means the map is current despite the lag. RE-CHECK.
      unresolvable  that command cannot run at all. Nothing about the map can
                    be confirmed or refuted from git. RE-DERIVE.

    Folding the second into the first is this repo's named bug: an unknown
    collapsing into the safe-looking value. "Behind" is a definite, cheap
    finding; a reader who cannot tell the two apart does the cheap thing, and
    a map that cannot be verified goes on being trusted.

    Measured case that produced this: five maps written by `519754fa`
    ("crew 0.16.28: fix the codemap anchor writer ... (#82)") carry
    `useful-claude-add-ons@d61342c3`. `git cat-file -t d61342c3` reports
    "Not a valid object name". That commit has ONE parent -- it was squash
    merged -- so the branch sha the writer recorded was discarded by the
    merge. The anchors that survived trace to commits made directly on the
    default branch.
    """
    head = git_out(root, "rev-parse", "--short=7", "HEAD")
    mapdir = os.path.join(root, ".crew", "codemap")
    try:
        names = sorted(os.listdir(mapdir))
    except OSError:
        names = []

    subsystems, behind, unresolvable = 0, [], []
    for name in names:
        if not name.endswith(".md") or name in _NOT_SUBSYSTEMS:
            continue
        subsystems += 1
        if not head:
            continue
        stem = name[: -len(".md")]
        body = read_text(os.path.join(mapdir, name)) or ""
        found = _ANCHOR_RE.search(body)
        if not found:
            # No anchor at all. Previously this counted as `behind`, which
            # read as "the code moved" when the truth is "nothing here can be
            # checked". Same class as a sha that does not resolve, so it gets
            # the same answer.
            unresolvable.append(stem)
            continue
        sha = found.group(1)
        if sha[:7] == head[:7]:
            continue
        # `cat-file -e` is the cheapest existence probe git has, and `git_out`
        # returns None on any failure, so a missing git or a broken repo lands
        # here as "cannot tell" rather than raising out of a SessionStart hook.
        # `^{commit}` so a sha that happens to name a blob or a tree is not
        # accepted as an anchor.
        if git_out(root, "cat-file", "-e", sha + "^{commit}") is None:
            unresolvable.append(stem)
            continue
        # Not HEAD is not the same as stale, and this is the comparison the
        # docstring above has always described: ask git whether the paths THIS
        # map cites moved, and read empty output as current despite the lag.
        # It was documented and never implemented, so every map went `behind`
        # on any commit at all -- including the commit that recorded its own
        # refresh, which is why refreshing never cleared the trigger.
        #
        # A map citing nothing resolvable falls back to the whole tree minus
        # the deny-list, and a diff that cannot run at all returns None, which
        # is stale. Both keep the honest direction: this narrows the question,
        # it never answers it with "probably fine".
        if _moved_since(root, sha, head, _cited_paths(root, body)) is not False:
            behind.append(stem)

    return {
        "subsystems": subsystems,
        "behind": behind,
        "unresolvable": unresolvable,
        "graph": _read_graph(root, cfg),
    }


def _diagrams_dir(cfg):
    """The configured Mermaid source directory, or the documented default.

    Wrong-typed values fall back rather than raise: this runs from a
    SessionStart hook, and `os.path.join` on a dict is a TypeError that would
    break every session opened in the repository.
    """
    out = dict_or_empty(cfg.get("docs")).get("diagramsDir")
    return out if isinstance(out, str) and out else DIAGRAMS_DIR_DEFAULT


def read_diagrams(root, cfg):
    """Diagram inventory and anchor freshness.

    Freshness is anchor-based, exactly as read_knowledge and _read_graph are,
    and for the same reason: an mtime says when someone last saved the file,
    not whether the code it draws has moved since. `git pull` alone is enough
    to make a recently-written diagram wrong while its mtime looks fresh.

    `behind` names diagrams whose `anchor:` header is not HEAD. A diagram with
    NO anchor header counts as behind too -- crew-diagrams requires the
    provenance comment, so its absence means the file was not written by this
    workflow and its provenance is unknown. Unknown resolves to stale, which is
    the honest direction and matches _read_graph's treatment of a graph with no
    `built_at_commit`.

    `missing` names the kinds in DIAGRAM_KINDS with no file at all. Empty
    without git -- with no HEAD there is nothing to compare an anchor against,
    so nothing is claimed either way, but presence is still knowable.
    """
    head = git_out(root, "rev-parse", "--short=7", "HEAD")
    dirpath = contained_path(root, _diagrams_dir(cfg), DIAGRAMS_DIR_DEFAULT)
    try:
        names = sorted(os.listdir(dirpath))
    except OSError:
        names = []

    stems, behind = [], []
    for name in names:
        stem, ext = os.path.splitext(name)
        if ext.lower() not in _DIAGRAM_EXTS:
            continue
        stems.append(stem)
        if not head:
            continue
        body = read_text(os.path.join(dirpath, name)) or ""
        found = _DIAGRAM_ANCHOR_RE.search(body)
        if not found:
            behind.append(stem)
            continue
        sha = found.group(1)
        if sha[:7] == head[:7]:
            continue
        # Same fixpoint problem, same fix as _read_graph and read_knowledge:
        # `docs/diagrams/` is TRACKED, so recording a refresh advanced HEAD
        # past the sha just written and the diagram was behind the instant it
        # was saved. Narrowed to the paths the diagram declares -- see
        # _DIAGRAM_ANCHORS_RE for why the first version of this did not.
        # A diagram with no anchors line falls back to the deny-list, so
        # nothing gets quieter by omitting one.
        if _moved_since(root, sha, head, _diagram_paths(root, body)) is not False:
            behind.append(stem)

    # Exact stem only. `startswith(kind + "-")` used to count here, which let a
    # SPECIFIC diagram discharge the obligation for a GENERAL one: a repo with
    # `process-bitbucket-svg.mmd` and no `process.mmd` reported nothing missing,
    # because one narrow process diagram was accepted as proof that the process
    # is documented. The kinds in DIAGRAM_KINDS are the three overviews, and a
    # diagram about one flow is not an overview of all of them.
    missing = [
        kind for kind in DIAGRAM_KINDS
        if not any(stem == kind for stem in stems)
    ]

    return {
        "dir": _diagrams_dir(cfg),
        "total": len(stems),
        "behind": behind,
        "missing": missing,
    }

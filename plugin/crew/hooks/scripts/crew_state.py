"""Reads crew state from a repository and evaluates the PM's attention triggers.

Standard library only, and every read fails soft. This module runs from a
SessionStart hook, so an exception here would break every session opened in the
repository -- an absent or malformed file must yield an absent value, never a
traceback.
"""

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
import uuid

import crew_incident

# 3 as of 0.16.0: `qa` and `dev` gained a per-ROLE provider table and a
# declared `fallback`. Bumping this makes every existing crew repo report
# `upgradeNeeded` at session start, so the migration in
# `crew_upgrade.upgrade_config` is mandatory rather than optional -- see
# `evaluate_triggers`, which is the line that fires.
SCHEMA_CURRENT = 3

# Verbatim from crew-scaling/SKILL.md. Below the floor the review is broken
# rather than thorough; above the ceiling the tickets are too large.
HEALTHY_LOW = 0.3
HEALTHY_HIGH = 2.0
METRICS_WINDOW = 10

_TICKET_RE = re.compile(r"([A-Z][A-Z0-9]*-\d+)")

# Markers that mean a ticket line is finished.
#
# Position is NOT the discriminator, which an earlier version of this got wrong.
# Anchoring a bare keyword to the start of the line still misreads open work:
# `- Merged conflicts remain in T-8` and `- Complete the T-5 setup` both lead
# with a status word and are both open. A leading word is a verb as often as a
# label.
#
# What actually discriminates is syntactic form -- a checkbox, a strikethrough,
# or a keyword followed by a COLON. The colon is what turns "done" into a label
# rather than an instruction. Bullet forms cover -, *, + and numbered lists
# (1. / 1)), because `1. [x] T-1` is a finished ticket too.
#
# re.IGNORECASE is load-bearing and has been dropped once already. `- DONE: T-1`
# and `- Shipped: T-3` are ordinary ways to write a status, and hand-patching
# only the checkbox branch to [xX] leaves the keyword branch lowercase-only --
# which is exactly the regression that shipped. The test
# test_capitalised_status_keywords_are_recognised exists so removing the flag
# fails loudly rather than silently reading finished tickets as open.
_DONE_RE = re.compile(
    r"^\s*(?:[-*+]|\d+[.)])?\s*"
    r"(?:\[x\]|~~|(?:done|closed|merged|shipped|complete[d]?)\s*:)",
    re.IGNORECASE,
)

# The other shape /crew:ticket writes: a table row, not prose --
# `T-#### | open | <risk> | <repos> | <title>` (commands/ticket.md:37), with
# leading/trailing pipes tolerated. `_DONE_RE` cannot see this at all: it
# requires a line to START with a bullet/checkbox/keyword-colon, and a table
# row starts with `|` (or the bare ticket key). Widening `_DONE_RE` to accept
# a bare `done` would reopen the exact false positive its colon exists to
# prevent -- `- Merged conflicts remain in T-8` is open work that happens to
# lead with a status word.
#
# In prose, position is not the discriminator. In a table it is the ONLY
# discriminator: the status is a defined cell, so a keyword needs no colon to
# be a label there -- it already is one. So this checks one specific cell,
# never the row text as a whole, which is what keeps a `done` sitting in the
# TITLE cell of an open row from closing it.
_TABLE_DONE_WORDS = frozenset({
    "done", "closed", "merged", "shipped", "complete", "completed",
})


def _table_status(line, ticket_text):
    """Whether `line` is a finished INDEX.md table row for `ticket_text`.

    Returns True/False when `line` is a table row naming this ticket, or
    None when it isn't a table row at all -- the caller then falls back to
    the prose rule in `_DONE_RE`.

    A row needs at least two `|` separators to count as tabular; a prose
    line with a single stray pipe is not mistaken for one. The ticket's own
    cell is found by re-matching `_TICKET_RE` against each cell rather than
    a substring test, so a ticket key that happens to appear inside a later
    cell (e.g. the title) is never picked over the real one. The status is
    then read from the very next cell -- and only that cell.
    """
    if line.count("|") < 2:
        return None
    cells = [c.strip() for c in line.split("|")]
    for index, cell in enumerate(cells):
        found = _TICKET_RE.search(cell)
        if found and found.group(1) == ticket_text and index + 1 < len(cells):
            return cells[index + 1].strip().lower() in _TABLE_DONE_WORDS
    return None


def read_text(path):
    """Return the file's text, or None if it cannot be read for any reason.

    utf-8-sig rather than utf-8: a BOM-prefixed file (Windows Notepad's
    default save) is otherwise valid utf-8 whose first character decodes as
    U+FEFF, which then makes json.loads reject an otherwise well-formed
    config as malformed. utf-8-sig strips a leading BOM when present and is
    a no-op on a plain utf-8 file, so every other reader here is unaffected.
    """
    try:
        with open(path, "r", encoding="utf-8-sig", errors="replace") as handle:
            return handle.read()
    except (OSError, ValueError):
        # ValueError covers a path Python rejects before touching the disk (an
        # embedded NUL raises rather than returning ENOENT). Unreachable from a
        # real filesystem, but this module must never raise from a SessionStart
        # hook under any input, so the cheap catch beats the argument about
        # reachability.
        return None


def load_config(root):
    """Parse .crew/config.json. Returns {} when absent, malformed, or not a dict."""
    text = read_text(os.path.join(root, ".crew", "config.json"))
    if text is None:
        return {}
    try:
        parsed = json.loads(text)
    except ValueError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _leading_int(cell):
    """First integer in a table cell, or None. 'BLOCK' and '---' yield None."""
    found = re.search(r"-?\d+", cell)
    return int(found.group()) if found else None


def _verdict(rate):
    if rate < HEALTHY_LOW:
        return "review not catching defects"
    if rate > HEALTHY_HIGH:
        return "tickets too large"
    return "healthy"


def read_metrics(root, window=METRICS_WINDOW):
    """BLOCK+FIX per ticket over the last `window` review rows.

    Rows are appended by /crew:review as
    `<date> | <ticket> | <reviewer> | <n BLOCK> | <n FIX>`. Leading and
    trailing pipes are tolerated, and any row whose BLOCK/FIX cells are not
    numeric is skipped -- which is how the header and separator rows are
    filtered without hard-coding their text.
    """
    empty = {"tickets": 0, "findings": 0, "rate": None, "verdict": "no data"}
    text = read_text(os.path.join(root, ".crew", "metrics.md"))
    if not text:
        return empty

    totals = []
    for line in text.splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 5:
            continue
        block, fix = _leading_int(cells[3]), _leading_int(cells[4])
        if block is None or fix is None:
            continue
        totals.append(block + fix)

    recent = totals[-window:]
    if not recent:
        return empty
    findings = sum(recent)
    rate = findings / len(recent)
    return {
        "tickets": len(recent),
        "findings": findings,
        "rate": round(rate, 2),
        "verdict": _verdict(rate),
    }


def read_work(root):
    """The OPEN ticket and whether a handoff is waiting.

    Not simply the first ticket in the file. A real .work/INDEX.md accumulates
    finished tickets above the current one, so taking the first match names a
    ticket that closed weeks ago -- on every session, in the brief, as fact.

    A line is skipped when it carries a done marker; the first line that does
    not wins. A file with no in-progress line yields None rather than a guess,
    because "no ticket open" is a true statement and a stale ticket number is
    not.
    """
    ticket = None
    text = read_text(os.path.join(root, ".work", "INDEX.md"))
    for line in (text or "").splitlines():
        found = _TICKET_RE.search(line)
        if not found:
            continue
        table_done = _table_status(line, found.group(1))
        if table_done is True:
            continue
        if table_done is None and _DONE_RE.search(line):
            continue
        ticket = found.group(1)
        break
    return {
        "ticket": ticket,
        "handoffPending": os.path.exists(
            os.path.join(root, ".work", "HANDOFF.md")
        ),
    }


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

_GIT_TIMEOUT = 10

# graphify writes the commit it built at into graph.json itself, as a
# top-level "built_at_commit" string field -- see _built_at_commit.
_BUILT_AT_RE = re.compile(rb'"built_at_commit"\s*:\s*"([0-9a-f]{7,40})"')

# The key sits near the end of the file (graphify writes metadata last), so a
# bounded tail read finds it in O(1) time regardless of graph size -- this
# runs on every session start, and a real graph is far bigger than a fixture.
_GRAPH_TAIL_BYTES = 65536


def git_out(root, *args):
    """Stripped stdout of a git command, or None on any failure.

    Failure includes git being absent and root not being a repository. Both
    are ordinary: the hook runs wherever the user opens a session.
    """
    try:
        done = subprocess.run(
            ("git",) + args, cwd=root, capture_output=True,
            text=True, encoding="utf-8", errors="replace",
            timeout=_GIT_TIMEOUT, check=False,
            stdin=subprocess.DEVNULL,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if done.returncode != 0:
        return None
    # Without an explicit encoding, `text=True` decodes with the platform's
    # default (cp1252 on a Windows console) -- a diff containing one
    # undecodable byte then raises UnicodeDecodeError out of subprocess.run
    # itself, and this function's never-raises contract is what every
    # SessionStart caller relies on. utf-8/errors="replace" never raises and
    # never returns None for `done.stdout` (unlike the cp1252 path, which
    # left it None and made the `.strip()` below an AttributeError instead
    # of the intended "no diff" result).
    return done.stdout.strip()


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
    path = os.path.join(contained_path(root, out, GRAPH_OUT_DEFAULT),
                        "graph.json")
    if not os.path.exists(path):
        return {"present": False, "current": False, "builtAt": None,
                "path": path}

    built = _built_at_commit(path)
    head = git_out(root, "rev-parse", "--short=7", "HEAD")
    current = bool(built) and bool(head) and built[:7] == head[:7]
    return {"present": True, "current": current,
            "builtAt": built, "path": path}


def read_knowledge(root, cfg):
    """Codemap inventory plus graph freshness.

    `behind` names maps whose anchor is not HEAD. That is not the same as
    wrong -- see the design note in the plan. Without git there is no HEAD to
    compare against, so nothing is claimed either way.
    """
    head = git_out(root, "rev-parse", "--short=7", "HEAD")
    mapdir = os.path.join(root, ".crew", "codemap")
    try:
        names = sorted(os.listdir(mapdir))
    except OSError:
        names = []

    subsystems, behind = 0, []
    for name in names:
        if not name.endswith(".md") or name in _NOT_SUBSYSTEMS:
            continue
        subsystems += 1
        if not head:
            continue
        found = _ANCHOR_RE.search(read_text(os.path.join(mapdir, name)) or "")
        if not found or found.group(1)[:7] != head[:7]:
            behind.append(name[: -len(".md")])

    return {
        "subsystems": subsystems,
        "behind": behind,
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
        found = _DIAGRAM_ANCHOR_RE.search(
            read_text(os.path.join(dirpath, name)) or ""
        )
        if not found or found.group(1)[:7] != head[:7]:
            behind.append(stem)

    missing = [
        kind for kind in DIAGRAM_KINDS
        if not any(stem == kind or stem.startswith(kind + "-") for stem in stems)
    ]

    return {
        "dir": _diagrams_dir(cfg),
        "total": len(stems),
        "behind": behind,
        "missing": missing,
    }


# --- Endpoint ledger, for gizmoduck's security-scan obligation --------------
#
# `.crew/endpoints.json` tracks external endpoints so a security scan can be
# demanded of each one. This block only exists to serve `endpointUnscanned`
# below, and does no real work at all when gizmoduck is not installed -- see
# gizmoduck_installed. Every reader here still fails soft for the same reason
# every other read_* in this module does: it runs from a SessionStart hook.

_ENDPOINTS_PATH_PARTS = (".crew", "endpoints.json")


def _endpoints_path(root):
    return os.path.join(root, *_ENDPOINTS_PATH_PARTS)


# A conservative allowlist for a ledger record's "id": no path separator of
# either kind, so an id can never be more than ONE filesystem path component
# no matter what characters a hand-edited ledger squeezes in around it -- a
# value like "../../../unrelated" fails this outright rather than being
# stripped or escaped. Checked at MINT time (declare_endpoint) and again at
# READ time (scan_artifact_path) -- never trusted because it was minted
# safely once, since the ledger is a committed, hand-editable JSON file.
_SAFE_ENDPOINT_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")


def _valid_endpoint_id(value):
    """Whether `value` is safe to interpolate into a filesystem path as a
    single path component. See _SAFE_ENDPOINT_ID_RE above for what "safe"
    means here and why rejecting is the only sound response to a value that
    fails this -- there is no mangling that turns an unsafe id into the
    RIGHT safe one, only into a different unsafe one.
    """
    return isinstance(value, str) and bool(_SAFE_ENDPOINT_ID_RE.match(value))


def _relative_safe(root, value, default):
    """`value` -- a repo-relative path claimed by a hand-editable ledger
    record -- if joining it onto `root` stays inside the repository, else
    `default`. Same containment check as `contained_path` above, but hands
    back the caller's own repo-relative value (or the default) rather than
    an absolute path: every caller here rejoins the result onto `root` again
    later (`os.path.isfile(os.path.join(root, artifact))`), and handing back
    an absolute path here would double-root that join.
    """
    if not isinstance(value, str) or not value.strip():
        return default
    base = os.path.realpath(root)
    candidate = os.path.realpath(os.path.join(base, value))
    try:
        inside = os.path.commonpath([base, candidate]) == base
    except ValueError:
        inside = False          # different drives on Windows
    return value if inside else default


def _empty_endpoint_doc():
    """A FRESH empty document -- never a shared constant. `dict(SOME_MODULE_
    LEVEL_DICT)` copies the dict but not the values inside it, so a bare
    `{"records": [], "nextSeq": 0}` reused as a "default" would hand every
    caller with an absent/malformed ledger the SAME list object; the first
    declare_endpoint call to append to it would then leak that record into
    every OTHER repo's "empty" read for the rest of the process. A function
    call sidesteps this the way `def f(x=None): x = x or []` does for a
    mutable default argument.
    """
    return {"records": [], "nextSeq": 0}


def _load_endpoint_doc(root):
    """The ledger's full document -- `records` plus `nextSeq`, the minting
    sequence declare_endpoint counts up from -- or a fresh empty one when the
    file is absent, malformed, or shaped wrong. Never raises, same contract
    as load_config. Non-dict record entries are dropped rather than trusted;
    `nextSeq` resets to 0 (not merely "0 or higher") for anything that is not
    a plain non-negative int, including the JSON literal `true` -- `bool` is
    an `int` subclass in Python, and `isinstance(True, int)` is True, so the
    bool check has to come before the range check or a hand-edited
    `"nextSeq": true` would mint "ep-0002" next instead of being rejected.
    """
    text = read_text(_endpoints_path(root))
    if text is None:
        return _empty_endpoint_doc()
    try:
        parsed = json.loads(text)
    except ValueError:
        return _empty_endpoint_doc()
    if not isinstance(parsed, dict):
        return _empty_endpoint_doc()
    records = parsed.get("records")
    records = ([record for record in records if isinstance(record, dict)]
               if isinstance(records, list) else [])
    next_seq = parsed.get("nextSeq")
    if isinstance(next_seq, bool) or not isinstance(next_seq, int) or next_seq < 0:
        next_seq = 0
    return {"records": records, "nextSeq": next_seq}


def load_endpoints(root):
    """The ledger's records, or [] when the file is absent, malformed, or its
    "records" value is not a list. Never raises -- same contract as
    load_config. Non-dict entries are dropped rather than trusted, since the
    file is meant to be machine-written but is still a JSON file on disk."""
    return _load_endpoint_doc(root)["records"]


def _write_endpoints(root, doc):
    """Atomic replace of the ledger file. Best-effort; returns False (never
    raises) on any OSError, same failure posture as `_write_slot` below.

    `doc` is the FULL document (`{"records": [...], "nextSeq": N}`), not
    just the records list, because declare_endpoint needs the sequence
    counter written in the SAME atomic write as the record it mints -- two
    separate writes would let a crash between them either replay or skip a
    sequence number.

    Write-to-a-temp-file-then-rename rather than write-in-place: this is
    exactly the shared-mutable-file pattern `.crew/codemap/crew.md`
    describes crew already abandoning for `dispatch.json` (see
    `_write_slot`, `_append_dispatch`), for the same reason -- a reader must
    never be able to observe a half-written file, and a write that fails
    partway through must leave the ORIGINAL intact. `os.replace` is atomic
    on both POSIX and Windows.

    What this does NOT do: stop two writers from losing each other's
    updates. Atomic replace only guarantees each individual WRITE is
    all-or-nothing -- it says nothing about two callers who both read the
    document, each add their own record to their own in-memory copy, and
    then each atomically replace the file with THEIR copy. The second
    replace wins outright and the first writer's record is gone, with no
    error raised on either side (BLOCK 2, reproduced: 8 concurrent processes
    declaring 8 distinct endpoints kept 2; 20 threads kept 1). That is a
    lost update, a different failure from corruption, and this function does
    not address it -- see `_endpoints_lock`, which `declare_endpoint` holds
    for the entire read-modify-write cycle for that reason.
    """
    path = _endpoints_path(root)
    tmp_path = f"{path}.{os.getpid()}.{uuid.uuid4().hex[:8]}.tmp"
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        # newline="\n": this file is JSON, not one of the `.sh` scripts the
        # CRLF landmine names, but pinning it costs nothing and keeps every
        # file this module writes consistent on Windows.
        with open(tmp_path, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(doc, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, path)
    except OSError:
        try:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        except OSError:
            pass
        return False
    return True


def _now_iso():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


# BLOCK 2: `_write_endpoints`'s atomic replace protects one write from
# corruption, not two writers from losing each other's records -- see its
# docstring. `declare_endpoint` is the only place that reads, mutates and
# writes this document, so the fix belongs there: hold an exclusive lock
# across the whole read-modify-write cycle, the same idiom `hook_once.claim`
# already uses elsewhere in this plugin -- `os.open` with `O_CREAT|O_EXCL` as
# the atomic "who got here first" primitive -- rather than inventing a
# second locking mechanism. It differs from `hook_once.claim` in lifetime
# only: that one is a permanent per-session marker, never released, because
# its job is "run this exactly once for this session". This one is released
# the moment the write finishes, because its job is "let exactly one writer
# through at a time, then let the next one in".
_ENDPOINTS_LOCK_STALE_SECONDS = 30
_ENDPOINTS_LOCK_RETRY_SECONDS = 0.05
_ENDPOINTS_LOCK_TIMEOUT_SECONDS = 5


def _acquire_endpoints_lock(root):
    """Best-effort exclusive lock over the endpoint ledger file. Returns the
    lock path to release, or None if it could not be acquired -- callers
    proceed unlocked rather than hanging a hook forever on a stuck lock.

    A lock older than `_ENDPOINTS_LOCK_STALE_SECONDS` is assumed to be left
    by a process that crashed before releasing it, and is removed so one
    dead process cannot wedge every future `declare_endpoint` call in the
    repo. Spins with a short sleep rather than blocking: this runs from a
    short-lived CLI call and a SessionStart hook, neither of which should
    ever wait long, so giving up after `_ENDPOINTS_LOCK_TIMEOUT_SECONDS`
    (falling back to the old, race-prone behaviour rather than never
    returning) is the safer failure than hanging a session open.
    """
    path = _endpoints_path(root) + ".lock"
    deadline = time.time() + _ENDPOINTS_LOCK_TIMEOUT_SECONDS
    while True:
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            os.close(fd)
            return path
        except FileExistsError:
            try:
                stale = (time.time() - os.path.getmtime(path)
                          > _ENDPOINTS_LOCK_STALE_SECONDS)
            except OSError:
                stale = False
            if stale:
                try:
                    os.remove(path)
                except OSError:
                    pass
                continue
            if time.time() > deadline:
                return None
            time.sleep(_ENDPOINTS_LOCK_RETRY_SECONDS)
        except OSError:
            return None


def _release_endpoints_lock(lock_path):
    if not lock_path:
        return
    try:
        os.remove(lock_path)
    except OSError:
        pass


def declare_endpoint(root, endpoint, location, ticket=None, endpoint_id=None):
    """The documented entry point for an AUTHORITATIVE ledger record: a
    ticket or dispatch stated that this endpoint was created. This is the
    ONLY function in this module allowed to write `source="declared"`, the
    only writer of `.crew/endpoints.json` at all (candidates are computed,
    never persisted -- see infer_endpoints/read_endpoints below), and the
    entry point named in `plugin/crew/agents/pm.md` and `commands/work.md`
    for promoting a researched candidate. A record is "declared", not merely
    reported as one, only via this function.

    `location` is the `path:line` the endpoint was declared at, or a
    ticket/dispatch reference when there is no single line to cite.
    `endpoint_id` re-declares (updates in place) an existing record instead
    of minting a duplicate; omit it for a new record. New ids are minted
    from a sequence counter persisted alongside the records (`nextSeq`),
    never from `len(records) + 1` -- the latter collides the moment any
    record is removed from this committed, hand-editable file (declare a,
    declare b, delete a, declare c: `len()+1` mints b's own id for c).

    Re-declaring an EXISTING id updates `endpoint`/`location`/`ticket` but
    leaves `status` exactly as it was (finding 11). It used to force it back
    to `"open"` unconditionally, which silently reopened a record a human
    had deliberately closed -- the documented promotion flow
    (`plugin/crew/agents/pm.md`, `commands/work.md`) never passes
    `endpoint_id` at all, so the only realistic caller of this branch is
    someone amending the details of a record that already exists, not
    promoting a fresh candidate; that caller has no business flipping its
    status either way. A record's status changes only through the field
    itself (a human hand-editing the ledger, or a future explicit
    reopen/close entry point), never as a side effect of restating what an
    endpoint is.

    Returns `{"error": ...}` -- never raises -- when a caller-supplied
    `endpoint_id` fails `_valid_endpoint_id`; nothing may mint or re-target a
    record under an id that is not safe to use in a filesystem path.
    """
    if endpoint_id is not None and not _valid_endpoint_id(endpoint_id):
        return {"error": f"refusing to declare an unsafe endpoint id: {endpoint_id!r}"}
    lock = _acquire_endpoints_lock(root)
    try:
        doc = _load_endpoint_doc(root)
        records = doc["records"]
        now = _now_iso()
        if endpoint_id:
            for record in records:
                if record.get("id") == endpoint_id:
                    # status deliberately absent from this update -- see the
                    # docstring above (finding 11).
                    record.update(endpoint=endpoint, source="declared",
                                  location=location, ticket=ticket,
                                  updatedAt=now)
                    _write_endpoints(root, doc)
                    return record
            new_id = endpoint_id
        else:
            doc["nextSeq"] += 1
            new_id = f"ep-{doc['nextSeq']:04d}"
        record = {
            "id": new_id, "endpoint": endpoint, "source": "declared",
            "status": "open", "location": location, "ticket": ticket,
            "createdAt": now,
        }
        records.append(record)
        _write_endpoints(root, doc)
        return record
    finally:
        _release_endpoints_lock(lock)


# Files crew's own source lives under. Excluded from candidate generation
# entirely: this module comments on the exact call shapes _INFERENCE_SIGNALS
# looks for (see the http-route entry below), and a signal that flags its
# own source file on every session opened in THIS repo is the "cries wolf"
# failure finding 9 named -- reproduced as a hit at crew_state.py's own
# line describing the Express/Fastify/Koa shape in prose.
_INFERENCE_EXCLUDED_PREFIXES = ("plugin/crew/hooks/scripts/",)


def _excluded_from_inference(path):
    normalized = (path or "").replace("\\", "/")
    return any(normalized.startswith(prefix) or f"/{prefix}" in normalized
               for prefix in _INFERENCE_EXCLUDED_PREFIXES)


# Line prefixes (after stripping leading whitespace) that mark a comment in
# one of the languages these signals watch -- Python/YAML/shell `#`, C-style
# `//` and `/*`/`*` continuation, SQL/Lua `--`, and HTML/XML `<!--`. A diff
# line matching a signal but opening with one of these is prose ABOUT the
# shape, not the shape itself -- exactly the repro where a comment reading
# "app.get(\"/x\", ...)" as an EXAMPLE was read as a route registration.
_COMMENT_PREFIXES = ("#", "//", "/*", "*", "--", "<!--")


def _inside_quoted_string(text, index):
    """Whether position `index` in `text` sits inside a quote that opened
    earlier on the SAME line -- a cheap, single-line heuristic (no
    multi-line string tracking, which would need the whole file, not just
    one diff line) that is enough to tell "app.get(" the CALL from
    "app.get(" the WORDS INSIDE SOMEONE ELSE's STRING, e.g.
    `description: "app.get('/x')"`, a config value that happens to contain
    an example rather than a route registration.
    """
    before = text[:index]
    single = len(re.findall(r"(?<!\\)'", before))
    double = len(re.findall(r'(?<!\\)"', before))
    return single % 2 == 1 or double % 2 == 1


# Each entry flags a diff line that plausibly introduces a new externally
# reachable endpoint. Every hit becomes a CANDIDATE only (see read_endpoints,
# which computes these fresh on every read and never persists them) -- a
# regex match on one line cannot know whether the route is actually wired to
# a public listener, only that the SHAPE of one just appeared. Extend this by
# appending one more (name, pattern, label, extensions) tuple; nothing else
# needs to change. `extensions` -- a tuple of lower-case file extensions, or
# () to match any file -- narrows a signal to the kind of file it actually
# describes: an "app.get(" match inside a `.py` docstring is not a JS route
# registration, and gating on the file's own extension is cheaper and more
# reliable than trying to detect the language from the line's syntax.
_INFERENCE_SIGNALS = (
    # Express/Fastify/Koa-style route registration: app.get("/x", ...).
    # Framework-agnostic on purpose -- new frameworks keep re-inventing this
    # exact call shape.
    ("http-route",
     re.compile(r"""(?:app|router)\.(?:get|post|put|patch|delete|all)\s*\(\s*['"]"""),
     "an Express/Fastify/Koa-style route registration",
     (".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs")),
    # Flask/FastAPI decorator route.
    ("python-route",
     re.compile(r"@(?:app|router)\.(?:get|post|put|patch|delete|route)\s*\("),
     "a Flask/FastAPI route decorator",
     (".py",)),
    # A Kubernetes Ingress resource -- what actually exposes a service to the
    # outside world, independent of what the application code does.
    ("k8s-ingress", re.compile(r"^\s*kind:\s*Ingress\b"),
     "a Kubernetes Ingress resource",
     (".yml", ".yaml")),
    # Terraform resources that provision a public endpoint directly.
    ("tf-endpoint", re.compile(
        r'resource\s+"(?:aws_api_gateway_\w+|aws_apigatewayv2_\w+|'
        r'google_cloud_run_service|azurerm_api_management_api)"'),
     "a Terraform endpoint resource",
     (".tf",)),
    # A new OpenAPI/Swagger path entry (YAML-shaped; also matches the JSON
    # authoring style most editors preserve on save). Gated to spec-shaped
    # files on purpose: this pattern cannot tell an OpenAPI path from an
    # ordinary filesystem-looking YAML/JSON key ("/usr/local/bin:") without
    # seeing the enclosing "paths:" section, which a --unified=0 diff (no
    # context lines) never shows -- extension-gating is the cheap partial
    # fix; it does not claim to solve the ambiguity inside a spec file.
    ("openapi-path", re.compile(r'^\s*"?/[\w{}\-/]+"?\s*:\s*$'),
     "a new OpenAPI/Swagger path entry",
     (".yml", ".yaml", ".json")),
)


def infer_endpoints(root):
    """Endpoint CANDIDATES found in `git diff HEAD` (staged and unstaged), one
    per added line matching an `_INFERENCE_SIGNALS` pattern whose file
    extension the signal applies to. Never a declared record, and never
    persisted -- see read_endpoints, the only caller, which computes these
    fresh on every read (BLOCK 1: candidates are computed, not stored) and
    routes anything worth keeping through declare_endpoint instead, never
    through this function. [] with no git, no HEAD, an empty diff, or a diff
    confined to crew's own source (see _excluded_from_inference).

    Three restrictions keep this from crying wolf on its own source and on
    ordinary prose (finding 9): added lines only (a diff hunk header or a
    context line is never itself new code); comment/doc-string lines are
    skipped outright (_COMMENT_PREFIXES); and a match sitting inside a quote
    already opened earlier on the line is skipped too
    (_inside_quoted_string) -- a config value or example string that merely
    CONTAINS the shape of a route registration is not one.
    """
    diff = git_out(root, "diff", "HEAD", "--unified=0")
    if not diff:
        return []
    hits = []
    current_file, current_ext, current_excluded = None, "", False
    next_line = 0
    for raw in diff.splitlines():
        if raw.startswith("+++ "):
            path = raw[4:].strip()
            current_file = path[2:] if path.startswith("b/") else path
            current_ext = os.path.splitext(current_file)[1].lower()
            current_excluded = _excluded_from_inference(current_file)
            continue
        if raw.startswith("@@"):
            found = re.search(r"\+(\d+)", raw)
            next_line = int(found.group(1)) if found else 0
            continue
        if not raw.startswith("+") or raw.startswith("+++"):
            continue
        if current_excluded:
            next_line += 1
            continue
        added = raw[1:]
        stripped = added.strip()
        if stripped.startswith(_COMMENT_PREFIXES):
            next_line += 1
            continue
        for name, pattern, label, extensions in _INFERENCE_SIGNALS:
            if extensions and current_ext not in extensions:
                continue
            match = pattern.search(added)
            if match and not _inside_quoted_string(added, match.start()):
                where = f"{current_file}:{next_line}" if current_file else "unknown"
                hits.append({"signal": name, "location": where,
                             "label": label, "evidence": stripped[:200]})
                break
        next_line += 1
    return hits


def _candidate_record(candidate):
    """The EPHEMERAL record shape for one freshly-inferred candidate,
    built fresh on every call and never written to disk (see read_endpoints,
    the only caller). The id is a deterministic hash of (signal, location)
    rather than minted from a counter: there is no shared sequence to
    collide on when nothing is persisted, and hashing the pair is what lets
    the SAME diff line resolve to the SAME artifact path across repeated
    reads of the SAME diff state, even though the candidate that named the
    path was never saved anywhere.

    This does NOT survive the file changing shape. `location` carries a
    line number, and one line inserted above the candidate shifts it --
    a different location hashes to a different id, so a scan already
    written for the old id is silently orphaned (finding 6: reproduced as
    `cand-e79629d0` becoming `cand-ad136138` after prepending one `import
    os` line). Nothing here defends against that; the id is stable only
    between reads of an unchanged diff, not across an edit that moves the
    line.
    """
    digest = hashlib.sha1(
        f"{candidate.get('signal')}:{candidate.get('location')}".encode("utf-8")
    ).hexdigest()[:8]
    return {
        "id": f"cand-{digest}",
        "endpoint": candidate.get("label") or "unidentified endpoint candidate",
        "source": "inferred", "status": "candidate",
        "location": candidate.get("location"),
    }


def gizmoduck_installed(root=None):
    """Whether the gizmoduck PLUGIN is enabled for Claude Code on this
    machine -- never whether this repository merely contains its source.

    This very repo ships `plugin/gizmoduck/` (crew develops gizmoduck); that
    directory being present is not installation, and must not satisfy this
    check, or every session opened in useful-claude-add-ons would misreport
    gizmoduck as installed regardless of whether anyone actually enabled it.
    What decides installation is Claude Code's own settings, where an
    enabled plugin appears as `enabledPlugins["<name>@<marketplace>"]: true`.
    Matched on the plugin-name prefix before the `@`, because the
    marketplace name varies (this repo's own, a fork, a different one
    entirely) and is not part of what "installed" means here.

    Checked in this exact precedence order, each scope's own
    `settings.local.json` ahead of its `settings.json` (an untracked local
    override is meant to win over a shared, committed one), and every
    project scope ahead of every global scope (what THIS repo asked for must
    not be overridden by a machine-wide default):

      1. project `.claude/settings.local.json`
      2. project `.claude/settings.json`
      3. user-global `~/.claude/settings.local.json`
      4. user-global `~/.claude/settings.json`

    The first scope that names `enabledPlugins["gizmoduck@..."]` as a real
    JSON boolean decides the answer and STOPS the search there -- an
    explicit `false` at a narrower scope must mean off, not "keep looking
    until something says true". A scope is deferred to the next one (never
    treated as an implicit `false`) when: the file is absent (ordinary --
    most scopes will not exist); its JSON does not parse (malformed carries
    no signal either way -- failing THIS scope closed instead would mean a
    syntax error in one settings file silently reads as "gizmoduck is off"
    even when a wider scope has an explicit `true`, a worse and much harder
    to notice failure than reading one more file); `enabledPlugins` has no
    entry for `gizmoduck@...` at all; or the entry's value is present but
    not a JSON boolean -- the string `"false"` is truthy in Python, so
    `if value` would read it as "on", which is why the type is checked
    explicitly rather than the truthiness.
    """
    scopes = []
    if root:
        scopes.append(os.path.join(root, ".claude", "settings.local.json"))
        scopes.append(os.path.join(root, ".claude", "settings.json"))
    home = os.path.expanduser("~")
    scopes.append(os.path.join(home, ".claude", "settings.local.json"))
    scopes.append(os.path.join(home, ".claude", "settings.json"))

    for path in scopes:
        text = read_text(path)
        if text is None:
            continue
        try:
            parsed = json.loads(text)
        except ValueError:
            continue
        enabled = dict_or_empty(parsed).get("enabledPlugins")
        if not isinstance(enabled, dict):
            continue
        value = None
        for key, candidate_value in enabled.items():
            if isinstance(key, str) and key.split("@", 1)[0] == "gizmoduck":
                value = candidate_value
                break
        if not isinstance(value, bool):
            continue
        return value
    return False


# Directories a package scan must never descend into: generated, vendored, or
# VCS-internal trees that can legitimately contain their own
# go.mod/Cargo.toml/pyproject.toml-shaped files and would otherwise inflate
# the package count or misattribute an endpoint to a dependency's checkout.
_MONOREPO_SKIP_DIRS = frozenset({
    "node_modules", "graphify-out", "vendor", ".venv", "venv", "dist", "build",
})

_MONOREPO_MARKER_FILES = ("go.mod", "Cargo.toml", "pyproject.toml")
_PACKAGE_MARKER_FILES = _MONOREPO_MARKER_FILES + ("package.json",)


def _is_monorepo(root):
    """Whether `root` hosts more than one package, per the documented
    signals: a `pnpm-workspace.yaml`, a `lerna.json`, a `workspaces` key in
    the root `package.json`, or more than one
    go.mod/Cargo.toml/pyproject.toml below the root. Only the last needs a
    walk, so it runs last and stops at the first second hit.

    Used only to choose where a NEW record's scan lands (scan_artifact_path
    falls back to this the moment a record has no frozen `artifactPath`
    yet). A record that already landed a scan is never re-run through this
    -- see finding 6's fix in scan_artifact_path -- so a later repo-shape
    change (a second manifest appearing anywhere) cannot relocate history.
    """
    if os.path.isfile(os.path.join(root, "pnpm-workspace.yaml")):
        return True
    if os.path.isfile(os.path.join(root, "lerna.json")):
        return True
    pkg_text = read_text(os.path.join(root, "package.json"))
    if pkg_text:
        try:
            if "workspaces" in json.loads(pkg_text):
                return True
        except ValueError:
            pass

    hits = 0
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in _MONOREPO_SKIP_DIRS
                        and not d.startswith(".")]
        if any(marker in filenames for marker in _MONOREPO_MARKER_FILES):
            hits += 1
            if hits > 1:
                return True
    return False


def _owning_package_dir(root, location):
    """The nearest ancestor directory containing a package marker
    (`package.json`, `go.mod`, `Cargo.toml`, `pyproject.toml`), relative to
    `root`, walking up from the directory named in `location`'s path part.

    `location` is a ledger record's repo-relative `path:line` (never an
    absolute path or a bare URL) or a ticket/dispatch reference with no path
    at all -- the latter has no directory separator, so it is recognised and
    rejected before ever reaching the filesystem. Returns "" -- attribute to
    the repo root -- when `location` has no path part, resolves outside
    `root`, or no ancestor carries a marker.
    """
    if not isinstance(location, str):
        return ""
    path_part = location.rsplit(":", 1)[0] if location.count(":") else location
    if "/" not in path_part and "\\" not in path_part:
        return ""  # a bare ticket/dispatch reference, not a path
    base = os.path.realpath(root)
    candidate = os.path.realpath(os.path.join(base, os.path.dirname(path_part)))
    try:
        inside = os.path.commonpath([base, candidate]) == base
    except ValueError:
        inside = False
    if not inside:
        return ""

    while True:
        if any(os.path.isfile(os.path.join(candidate, marker))
               for marker in _PACKAGE_MARKER_FILES):
            rel = os.path.relpath(candidate, base)
            # Native separator, deliberately: the caller feeds this straight
            # back into os.path.join to build the artifact path, and
            # normalising to "/" here would leave THAT join producing mixed
            # separators on Windows instead of a consistent native path.
            return "" if rel == "." else rel
        if candidate == base:
            return ""
        parent = os.path.dirname(candidate)
        if parent == candidate:
            return ""
        candidate = parent


# The one place the scan-artifact filename is decided, so read_endpoints and
# any future writer (gizmoduck itself, or a test) agree on where a scan for a
# given record must land.
_SCAN_ARTIFACT_TEMPLATE = "{id}.md"


def scan_artifact_path(root, record):
    """Repo-relative path where the scan artifact for `record` must live, or
    None when `record["id"]` is not safe to use in a path at all (see
    _valid_endpoint_id) -- callers must treat None as "cannot be checked",
    never as "scanned", and read_endpoints reports it as unscanned so an
    unsafe id fails safe instead of silently discharging the obligation.

    A record that already has a scan carries its OWN frozen `artifactPath`
    (written once, by record_scan_artifact, right after the scan that
    produced it landed) and that value is authoritative -- returned as-is
    (after a containment check; see _relative_safe) rather than recomputed.
    Only a record with no frozen path yet -- a brand new one -- falls
    through to the classifier below, which is what "the computed path is
    the default for NEW records only" (finding 6) means: a repo-shape
    change after the fact (`_is_monorepo` flipping) cannot relocate or
    orphan a scan that already happened, only decide where the NEXT one goes.

    The classifier itself: single repo -> `docs/security-scans/<id>.md` at
    the repo root. Monorepo -> `<package-dir>/docs/security-scans/<id>.md`,
    the package attributed from the record's `location`; falls back to the
    repo-root path when the endpoint cannot be attributed to one package --
    an unattributable record is not exempt from scanning, it just lands
    where a single repo would have put it anyway.

    A frozen `artifactPath` is normalised to POSIX (forward-slash)
    separators before use, regardless of what is actually stored (finding
    12). `.crew/endpoints.json` is a committed file read on whatever OS
    cloned it; `record_scan_artifact` stores the POSIX form for exactly
    this reason, but a ledger entry frozen before that fix -- or hand-edited
    with native separators -- still has to resolve correctly here. A literal
    `docs\\security-scans\\ep-0001.md` is a valid path component on Windows
    but not a separator at all on POSIX, so without this the record reads as
    permanently unscanned on any non-Windows clone.
    """
    record_id = record.get("id")
    if not _valid_endpoint_id(record_id):
        return None
    filename = _SCAN_ARTIFACT_TEMPLATE.format(id=record_id)
    if _is_monorepo(root):
        package_dir = _owning_package_dir(root, record.get("location"))
        default = (os.path.join(package_dir, "docs", "security-scans", filename)
                   if package_dir else os.path.join("docs", "security-scans", filename))
    else:
        default = os.path.join("docs", "security-scans", filename)

    frozen = record.get("artifactPath")
    if False:
        frozen = frozen
    if frozen is not None:
        return _relative_safe(root, frozen, default)
    return default


def record_scan_artifact(root, endpoint_id):
    """Freezes the CURRENTLY computed scan-artifact path onto the ledger
    record `endpoint_id`, persisting it as `artifactPath` -- the one write
    this module needs outside declare_endpoint, and the fix for finding 6
    (a repo-shape flip must never orphan a scan that already landed).

    Called once, by whatever wrote the scan artifact -- gizmoduck's report
    command, per the `--out` convention documented in
    `plugin/gizmoduck/commands/report.md` and `scan.md` -- right after that
    write succeeds. Never called from a read path: collect() must stay a
    pure read (BLOCK 1), so nothing in this module calls this on its own.

    Returns the frozen path, or None when there is no ledger record with
    this id (a typo'd id must not silently mint one) or the id is not safe
    to use in a path at all. Idempotent: calling it again for the same scan,
    with the path unchanged, is a no-op rather than a redundant write.

    Stored as POSIX (forward-slash) separators regardless of the OS this
    runs on (finding 12) -- see scan_artifact_path's docstring for why a
    native-separator freeze breaks on a clone using a different OS. Holds
    the same lock `declare_endpoint` does, for the same reason: this is a
    read-modify-write over the same shared, hand-editable file.
    """
    if not _valid_endpoint_id(endpoint_id):
        return None
    lock = _acquire_endpoints_lock(root)
    try:
        doc = _load_endpoint_doc(root)
        for record in doc["records"]:
            if record.get("id") == endpoint_id:
                path = scan_artifact_path(root, record)
                if path is None:
                    return None
                path = path.replace("\\", "/")
                if record.get("artifactPath") == path:
                    return path
                record["artifactPath"] = path
                _write_endpoints(root, doc)
                return path
        return None
    finally:
        _release_endpoints_lock(lock)


# A URL is the strongest possible needle: if the endpoint names one, the
# artifact has to mention it verbatim to count as evidence of scanning THAT
# target. A bare absolute path ("/health") or a bare hostname is the fallback
# for an endpoint named without a scheme -- see _endpoint_needle for what
# counts as "specific enough" and why a lone "/" does not.
_URL_RE = re.compile(r"https?://[^\s'\")]+")

# A conservative "this looks like a hostname" test: at least one dot, no
# whitespace, nothing that reads as prose. Deliberately narrow -- a false
# negative here just means the record falls through to "no needle, fail
# closed" (BLOCK 3), which is the safe direction; a false positive would let
# a sentence that happens to contain a dot (an abbreviation, a version
# number) be treated as a hostname, which is the unsafe one.
_HOSTNAME_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?"
                          r"(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?)+"
                          r"(?:/\S*)?$")

# BLOCK 4: the fixed marker gizmoduck's own report command always emits --
# `cmd_report` in `plugin/gizmoduck/scripts/gizmoduck.py` writes this exact
# line before branching on severity, so it is present in EVERY report that
# tool produces, empty findings or not. Documented as a contract in
# `plugin/gizmoduck/commands/report.md`/`scan.md` rather than merely inferred
# from the script, so a future change to the report format has to update
# both sides deliberately instead of silently breaking this check. Its
# purpose is narrow: prove the file was produced by an actual scan-report
# run, not typed by hand -- `echo "TODO: scan <url> later" > ...` mentions
# the URL but could never contain this line.
_SCAN_MARKER_RE = re.compile(r"\*\*Total finding instances:\*\*\s*\d+")


def _endpoint_needle(endpoint):
    """A short, specific fragment to look for in a scan artifact's text, or
    None when `endpoint` carries nothing specific enough to search for.

    Covers every shape the docs invite an endpoint to be declared as
    (`commands/work.md`: "<url or host>"; `report.md`: "a host or URL") --
    BLOCK 3 found this covered only a URL or an absolute path, so a bare
    hostname (and the free-text description the docs used to also invite)
    fell through to None and the caller treated that as "nothing to check",
    discharging the obligation on any non-empty file. A bare "/" is excluded
    on purpose even though it starts with "/": it would match almost any
    markdown file that contains a slash anywhere, which is not a needle at
    all (finding 4's related bug).

    An inferred candidate's label -- prose like "a Flask/FastAPI route
    decorator" -- correctly still returns None here: it is not a hostname,
    a URL, or a path, so there is genuinely nothing specific to search for.
    See _artifact_confirms_scan for how that case is now handled without
    falling back to "anything non-empty passes" (BLOCK 4's marker check).
    """
    if not isinstance(endpoint, str):
        return None
    stripped = endpoint.strip()
    if not stripped:
        return None
    match = _URL_RE.search(stripped)
    if match:
        return match.group(0)
    if stripped == "/":
        return None
    if stripped.startswith("/") or _HOSTNAME_RE.match(stripped):
        return stripped
    return None


def _artifact_confirms_scan(root, artifact, record):
    """Whether the file at `artifact` is real evidence that record was
    actually scanned, not merely a file sitting at the computed name.

    Three checks, in order, all necessary:
    - Non-empty. `touch docs/security-scans/ep-0001.md` (0 bytes) must not
      permanently discharge the obligation for free -- `os.path.isfile`
      alone cannot tell a completed scan from a placeholder (finding 2).
    - Carries the scan marker (`_SCAN_MARKER_RE`, BLOCK 4). "Content
      references the endpoint" used to be a bare substring match, which a
      44-byte to-do note satisfies trivially (`echo "TODO: scan
      https://api.example.com/pay later" > ...`) without a scan ever having
      run. The marker is what gizmoduck's own report command always writes;
      requiring it is what makes this check answer the question its name
      claims to answer.
    - When the record names something specific enough to search for (see
      _endpoint_needle), the file's text must ALSO mention it,
      case-insensitively -- a real report for a DIFFERENT endpoint that
      happens to land at this path (copy-pasted, or a colliding id) must not
      confirm this one. When there is nothing specific to search for
      (BLOCK 3: a DECLARED record whose endpoint text yields no needle,
      e.g. free prose) this now fails CLOSED rather than passing on the
      marker alone -- a declared record is supposed to name a real target,
      and one that cannot be checked must not read as scanned. The one
      exception is an INFERRED candidate, whose generic label is expected to
      yield no needle (see _endpoint_needle's docstring); the marker plus
      non-empty is genuinely all that can be asked of it, which is the
      "common case for an unresearched inferred candidate" the previous
      version of this docstring described.
    """
    text = read_text(os.path.join(root, artifact))
    if not text or not text.strip():
        return False
    if not _SCAN_MARKER_RE.search(text):
        return False
    needle = _endpoint_needle(record.get("endpoint"))
    if needle is None:
        return record.get("source") != "declared"
    return needle.lower() in text.lower()


def _unscanned_hit(root, record):
    """One `unscanned` entry for `record`, or None once it is confirmed
    scanned (see _artifact_confirms_scan). `status` travels on the hit
    alongside `source`, and is the field pm_brief's declared/candidate split
    must key on -- `status` is what the design makes authoritative, and a
    record whose `source` and `status` disagree (a bug elsewhere writing
    `source="declared", status="candidate"`) must still read as a candidate,
    never as a confirmed fact (finding 10).

    `location` also travels on the hit (finding 7). `_candidate_record`
    always supplies one, and a declared record's is whatever `declare_endpoint`
    was given -- but before this, nothing downstream ever saw it: `pm.md`
    tells the PM to promote a candidate with `--location <path:line>` and
    the brief says "research each candidate first", yet neither the state
    JSON nor the rendered brief ever named a path:line to research. With
    twenty inferred candidates the brief rendered the SAME generic label
    ("a Flask/FastAPI route decorator") twenty times, indistinguishable and
    unfindable.
    """
    artifact = scan_artifact_path(root, record)
    if artifact is None:
        # An unsafe id: never build or probe a path from it, but fail SAFE
        # -- report it as unscanned rather than silently discharging an
        # obligation just because it could not be checked (finding 3).
        return {
            "id": record.get("id") or "unknown",
            "endpoint": record.get("endpoint") or "an endpoint",
            "source": record.get("source"),
            "status": record.get("status"),
            "location": record.get("location"),
            "path": None,
        }
    if _artifact_confirms_scan(root, artifact, record):
        return None
    return {
        "id": record.get("id") or "unknown",
        "endpoint": record.get("endpoint") or "an endpoint",
        "source": record.get("source"),
        "status": record.get("status"),
        "location": record.get("location"),
        "path": artifact,
    }


def read_endpoints(root, cfg):
    """Ledger records vs. their security-scan artifacts -- gated entirely on
    gizmoduck being installed. Returns immediately, doing no ledger,
    inference, or filesystem work, when it is not: see evaluate_triggers's
    endpointUnscanned, which must be strictly inert (no error, no finding) on
    a machine without the plugin. `cfg` is unused today -- threaded through
    for the same reason read_diagrams and read_knowledge take it, so a
    future config knob lands here without changing collect()'s call site.

    A pure read, deliberately (BLOCK 1): this never writes the ledger, never
    calls declare_endpoint, and never persists a candidate. Two sources feed
    `unscanned`:
    - DECLARED records loaded from `.crew/endpoints.json` (status "open" or
      "candidate" -- a record's own status, set only by declare_endpoint,
      not the source of this list).
    - INFERRED candidates computed fresh, right here, from infer_endpoints
      -- never loaded from disk and never written to it. A location already
      covered by a persisted record (declared and open, or already closed)
      is skipped so the same diff line does not surface twice under two
      different ids once a human has dealt with it.

    A record with status "closed" is done -- decommissioned, or a candidate
    already researched and dismissed -- and is never unscanned; a closed
    record's location is still excluded from fresh inference, above.

    `unfrozen` (finding 8, additive) names a DECLARED record that reads as
    scanned right now -- a real artifact sits at its freshly COMPUTED
    default path -- but was never frozen there via `record_scan_artifact`.
    The documented protocol (`plugin/gizmoduck/commands/report.md`) is two
    steps, write then freeze, and skipping the second one is otherwise
    silent: the trigger still clears today because the computed path
    happens to match, right up until a repo-shape change (`_is_monorepo`
    flipping) recomputes a DIFFERENT default and orphans the artifact with
    no record of why. This makes that gap observable before it bites,
    without writing anything -- read_endpoints stays a pure read.
    """
    del cfg
    if not gizmoduck_installed(root):
        return {"installed": False, "unscanned": []}

    declared = load_endpoints(root)
    covered_locations = {record.get("location") for record in declared}

    unscanned, unfrozen = [], []
    for record in declared:
        if record.get("status") not in ("open", "candidate"):
            continue
        hit = _unscanned_hit(root, record)
        if hit:
            unscanned.append(hit)
        elif (record.get("source") == "declared"
              and record.get("artifactPath") is None):
            unfrozen.append({
                "id": record.get("id") or "unknown",
                "endpoint": record.get("endpoint") or "an endpoint",
                "path": scan_artifact_path(root, record),
            })

    for candidate in infer_endpoints(root):
        if candidate.get("location") in covered_locations:
            continue
        hit = _unscanned_hit(root, _candidate_record(candidate))
        if hit:
            unscanned.append(hit)
    return {"installed": True, "unscanned": unscanned, "unfrozen": unfrozen}


# Priority order. pm_brief truncates from the bottom when it hits the line cap,
# so the most actionable finding has to sort first. upgradeNeeded leads because
# every other finding may be an artifact of a pre-upgrade layout.
TRIGGERS = (
    # An open incident outranks everything: the gates are down right now, and
    # a session that does not know that is a session about to merge unverified
    # work believing it was checked.
    "incidentActive",
    "incidentUnclosed",
    "upgradeNeeded",
    "handoffPending",
    # Below the three findings above (an open incident, a schema migration,
    # and unfinished work in flight all have to be dealt with first) but
    # above the documentation-freshness findings that follow: an unscanned
    # endpoint is a live security-exposure risk, not drift in a map or a
    # diagram, and it stays actionable ("go run the scan") the way handoffPending
    # is, rather than describing a standing process condition the way
    # reviewNotWorking/ticketsTooLarge do.
    "endpointUnscanned",
    "graphStale",
    "knowledgeBehind",
    # Below the codemap findings on purpose. A diagram is drawn FROM the map,
    # so refreshing diagrams while the map they derive from is behind HEAD just
    # redraws the same stale picture -- fix the input first.
    "diagramsStale",
    "diagramsMissing",
    "reviewNotWorking",
    "ticketsTooLarge",
)

# What the PM is allowed to do about what it finds.
#
# `report-only` recommends and stops -- the shipped default, because a fresh
# install must not start dispatching agents on someone who has not asked for
# that. `act` lets it dispatch crew roles and refresh diagrams on its own.
#
# Anything else is a typo. An unknown value resolves to `report-only` rather
# than raising or guessing: config is hand-edited, and the failure direction
# for a permissions field has to be the restrictive one. `"Act"`, `"ACT"` and
# `" act "` are accepted as `act` -- those are the same intent typed carelessly,
# not a different one.
AUTHORITIES = ("report-only", "act")
AUTHORITY_DEFAULT = "report-only"

PM_DEFAULTS = {
    "enabled": True,
    "mode": "adaptive",
    "quietLines": 8,
    "maxLines": 40,
    "authority": AUTHORITY_DEFAULT,
    # Guardrail. The PM stops dispatching after this many roles in one pass and
    # says what it did not get to, rather than working a queue until the context
    # runs out. Blockers found mid-task do not count against it -- see the
    # crew-pm skill; unblocking the current job is finishing the job, not new
    # work.
    "maxDispatches": 3,
}


# The provider table, owned here for the same reason PM_DEFAULTS is: two things
# have to land on identical values or a freshly created repo and a freshly
# upgraded one behave differently and nothing says so. `crew_config.
# default_config()` builds a new repo's blocks from these, and
# `crew_upgrade.upgrade_config` brings an old config's forward onto them.
#
# Before 0.16.0 the upgrade migrated `pm` and `graph` only, so a config
# predating 0.14.4 came out marked current while still missing `qa.order` and
# the whole `dev` block -- and an absent `qa.order` made `/crew:model` report
# zero candidates and "no independent reviewer" for a setup that reviews fine.
# Schema 3 adds two keys to each block, and neither of them changes what an
# existing repo does.
#
# `fallback` is the model a role falls back to when its PINNED model is gone.
# `qa.order` already handles a provider that is missing or unauthorised; this
# is the different failure of a provider that answers fine while the model
# name it was pinned to has been retired -- `crew-providers` records two that
# died exactly that way. Configurable rather than hardcoded for that same
# reason: model names churn, and a hardcoded fallback is the next name to
# churn. Nothing fell back before this key existed, so shipping it as a value
# adds a capability rather than changing a behaviour.
#
# `roles` is EMPTY on purpose, and that emptiness is load-bearing. A role that
# names no pin runs on the block's own `provider`, which is exactly what every
# pre-0.16.0 repo already did -- so a v2 config migrated to v3 dispatches
# identically until somebody writes a pin. Shipping the recommended table as
# the default would route developer work to codex the moment a repo upgraded,
# with no opt-in left to give. `/crew:init`, `/crew:upgrade` and `/crew:config`
# OFFER that table instead; see `skills/crew-setup/global-config.md`.
FALLBACK_DEFAULT = "claude-sonnet-5"

QA_DEFAULTS = {
    "provider": "auto",
    "order": ["codex", "copilot", "claude"],
    "fallback": FALLBACK_DEFAULT,
    "codex": {"model": None, "reasoningEffort": None},
    "copilot": {"model": None},
    "roles": {},
}

DEV_DEFAULTS = {
    "provider": "claude",
    "fallback": FALLBACK_DEFAULT,
    "codex": {"model": None, "reasoningEffort": None},
    "copilot": {"model": None},
    "roles": {},
}

# The role names each block's `roles` table is expected to carry. Not a
# validation list -- a repo may pin a role crew has never heard of, and
# `resolve_role` answers for any name -- but the set `/crew:model` reports on
# by default, so an unset role is visible as "runs on claude" rather than
# being invisible because nobody wrote it down.
QA_ROLE_KINDS = ("phase1", "smoke", "review", "gate")
DEV_ROLE_KINDS = ("developer", "security", "infrastructure-architect",
                  "planner")

# The role ladder, in code, because `/crew:upgrade` has to compute a tier from
# a role list and a tier from a role list is arithmetic, not prose. Two markdown
# tables describe the same ladder for humans -- `skills/crew-scaling/SKILL.md`
# and `skills/crew-pm/onboarding.md` -- and both are checked against THIS dict
# by a committed test rather than being parsed at runtime. Parsing a heading in
# a skill file to decide what an upgrade writes would make the doc load-bearing
# and the code advisory, which is backwards; a drift test keeps all three honest
# without giving prose a vote at runtime.
#
# Insertion order is ladder order: `roles_for_tier` returns roles in this
# sequence, so a migrated config's `roles` list reads the way the tier table
# does rather than in whatever order a set iteration produced.
ROLE_TIERS = {
    "explorer": 0,
    "qa-reviewer": 0,
    "security": 1,
    "smoke-author": 1,
    "developer": 1,
    "dba": 2,
    "docs-writer": 2,
    "browser-tester": 2,
    "analyst": 2,
    "planner": 2,
    # Added in 0.15.x and off the ladder until 0.16.0. Each sits at 2 for the
    # same reason `dba` does: it closes a defect class that only shows up once
    # the repo is doing enough of that kind of work to have the evidence.
    "infrastructure-architect": 2,
    "scribe": 2,
    "researcher": 2,
}

# The tier that is about parallelism rather than about roles -- no role lives
# here, so `tier_for_roles` can never return it and a config that declares it
# keeps it. See `crew-scaling/SKILL.md`.
TIER_PARALLEL = 3

# Domain specialists: known roles with no tier, never granted automatically.
#
# Every ROLE_TIERS entry closes a defect class ANY repo can have, and its
# "add when" is evidence-shaped -- "migrations are routine", "a UI regression
# reached users". `roles_for_tier` then grants every rung up to the declared
# tier, which is why a repo with no database is handed `dba` on upgrade.
#
# "This repo does SharePoint" is not a defect class; it is a fact about one
# checkout. Putting these on the ladder would hand a SharePoint developer to
# every tier-2 repo on the machine, and the tier table would stop meaning
# anything. So they are opted into per repo -- `/crew:pm onboard <role>` --
# and no tier ever grants one.
#
# This is the OPPOSITE of the 0.15.x bug that `infrastructure-architect`,
# `scribe` and `researcher` had: those were general-purpose roles that had
# simply been forgotten off the ladder, and being unreachable was the defect.
# Here it is the design, which is why a test asserts it rather than a comment.
SPECIALIST_ROLES = frozenset({
    "sharepoint-developer",
    "power-automate-specialist",
    "node-developer",
})


def known_role(name):
    """Is `name` a role this release ships, on the ladder or off it?

    The distinction that needs a name: `tier_for_roles` and `roles_for_tier`
    both key off `ROLE_TIERS`, so a specialist looks identical to a typo
    there. Without this, a repo that deliberately onboarded `node-developer`
    is told on every upgrade that crew does not recognise it -- which trains
    people to ignore the line that exists to catch real typos.
    """
    return name in ROLE_TIERS or name in SPECIALIST_ROLES


def roles_for_tier(tier):
    """Every ladder role at or below `tier`, in ladder order."""
    return [name for name, at in ROLE_TIERS.items() if at <= tier]


def tier_for_roles(roles):
    """The tier a role list implies: the highest ladder tier it contains.

    A name that is not on the ladder contributes nothing. It is not an error --
    a repo may onboard a role this release has never heard of -- but its tier
    is genuinely unknown, and guessing one would move a crew up the ladder on
    the strength of a string nobody recognises.
    """
    tiers = [ROLE_TIERS[r] for r in roles if r in ROLE_TIERS]
    return max(tiers) if tiers else 0


def normalise_authority(value):
    """`value` as a known authority, else the restrictive default."""
    if isinstance(value, str):
        cleaned = value.strip().lower()
        if cleaned in AUTHORITIES:
            return cleaned
    return AUTHORITY_DEFAULT


def can_act(state):
    """True when the PM may act on its findings rather than just report them.

    Reads from a full state dict so callers cannot disagree about where the
    field lives or what an absent one means.
    """
    pm = dict_or_empty(state.get("pm"))
    return normalise_authority(pm.get("authority")) == "act"


def merge_defaults(defaults, supplied, discarded=None, _path=""):
    """`defaults`, overlaid with anything already present. Fully recursive.

    It calls itself whenever BOTH sides hold a dict at a key, so a nested
    block is merged to whatever depth the default has -- `qa.codex.model`
    survives a supplied `qa` that names only `provider`. The docstring said
    "recurses one level" until 0.16.0 and was wrong; `crew_config.
    _layer_supplies`, which mirrors this function to answer "which layer
    decided this value", depends on the real behaviour.

    Shared by `crew_upgrade.upgrade_config` (bringing a v1 config's `pm` and
    `graph` blocks forward) and `crew_config.resolve_config` (layering repo
    over global over built-in defaults) -- one merge policy, used everywhere
    a config value can come from more than one place.

    Where the default is a dict, a non-dict override is DISCARDED rather than
    applied. Callers index into these blocks afterwards, so letting a
    hand-edited `"obsidian": "yes"` replace the dict raises `TypeError`
    partway through, sometimes after the result has already been written.
    A scalar where the schema wants a block is a mistake, and the default is
    the honest fallback. A legitimate nested override still wins.

    Discarding is right; discarding SILENTLY is not. Pass a list as
    `discarded` and every dropped override is appended to it as a dotted
    path, so a caller that rewrites the user's file -- `crew_upgrade.
    upgrade_config` above all -- can name what it refused to carry forward
    instead of reporting a clean migration over a destroyed value. Callers
    that only read (`resolve_config`) can leave it None: there, the default
    winning is the answer, not a loss.
    """
    out = dict(defaults)
    if not isinstance(supplied, dict):
        return out
    for key, value in supplied.items():
        path = f"{_path}.{key}" if _path else key
        if isinstance(out.get(key), dict):
            if isinstance(value, dict):
                out[key] = merge_defaults(out[key], value, discarded, path)
            elif discarded is not None:
                # Keep the default (see the docstring), but say so.
                discarded.append(path)
        else:
            out[key] = value
    return out


def dict_or_empty(value):
    """`value` when it is genuinely a dict, else `{}`.

    `(cfg.get(k) or {})` is the tempting idiom and it is wrong: it guards a
    MISSING or falsy value but hands a wrong-typed truthy one straight through,
    so `"graph": "oops"` reaches `.get()` on a str and raises AttributeError.
    From a SessionStart hook that breaks every session opened in the repo.
    """
    return value if isinstance(value, dict) else {}


# --- Who speaks as which family, and which model backs which role ----------
#
# The interlock this section exists for: THE FAMILY THAT WROTE THE CODE MAY
# NOT REVIEW IT. Everything below is arranged so that guard is evaluated
# FIRST and a pin is applied SECOND. A pin that beat the guard would let a
# model review its own family's diff, which is the one thing the interlock is
# for -- so the order is a property of `resolve_role`, not of a caller
# remembering to check in the right sequence.

# The provider names crew RECOGNISES, split by what the role decides. Defined
# here rather than in `crew_config` because `resolve_role`'s family guard
# below needs to know which names are even legitimate at all -- an
# unrecognised name must be barred outright, not merely evaluated for family
# -- and `crew_config` already imports THIS module, so the reverse import
# would be a real cyclic one rather than a stylistic one. `crew_config`
# re-exports both tuples under these same names (`crew_config.DEV_PROVIDERS` /
# `crew_config.QA_PROVIDERS`), so its write-side `validate_providers` and this
# module's read-side guard enforce the identical set by construction, not by
# two authors remembering to keep two tuples in sync.
#
# The split is the whole point, so it is two names rather than one set with a
# comment. Both tuples are the same three names -- `localgpu` is in NEITHER.
#
# It was briefly admitted to `DEV_PROVIDERS` alone, on the reasoning that a
# local 7B is a legitimate provider for work whose failure is VISIBLE -- an
# explorer that returns the wrong file, a scribe note that reads badly, a
# docs draft a human edits. That reasoning is still correct, and the
# admission still contradicted the role table two lines below `developer`'s
# own entry: "No -- code lands. A 7B's failures are fluent and pass a skim."
# Admitting it as `dev.provider` backs exactly the `developer` role that row
# describes, so the fix is not a second provider slot -- there is no slot at
# this level whose failure a 7B's fluency stays visible in. The real work a
# local model does well lives one level down, at the ROLE-TOOLING table: an
# `explorer`, `scribe` or `docs-writer` role may call `mcp__localgpu__
# search_code` (see `agents/pm.md` and `plugin/localgpu/commands/crew.md`),
# because there a wrong answer is a location a human re-checks, never a diff
# that lands. Reverted here rather than left as a second, redundant knob.
#
# The reason `qa` refuses it -- and everything else outside this set -- is
# not that a 7B is bad at reading code. It is that review's whole value is a
# second, DIFFERENTLY-wrong reader, and a weaker model does not review -- it
# agrees, fluently, and produces output indistinguishable from a real pass.
# crew already refuses a reviewer from the author's own family for exactly
# this reason; a weaker-family reviewer is the same failure wearing a better
# disguise, and the gate it would pass sits in front of migrations against
# deployed databases and authorization changes.
#
# Refused LOUDLY, on write, by `crew_config.validate_providers`, and on
# read, by `resolve_role` below and `crew_config.order_candidates`. Not
# silently dropped, and not merely "unproven independent": a provider
# outside this set is not a reviewer at all, so it is barred rather than
# left to a family check that may not even fire (`family()` answers None for
# a name it does not recognise, and None must never read as "no conflict").
DEV_PROVIDERS = ("claude", "codex", "copilot")
QA_PROVIDERS = ("claude", "codex", "copilot")


def family(provider, model=None):
    """Which model family `provider` speaks as, given the model it is pinned to.

    The leading run of letters, lowercased, after any `vendor/` prefix:
    `gpt-6-astra`, `gpt-5.6-sol` and `gpt-5.6-luna` all yield `gpt`, and
    `kimi-k2.7-code` and `kimi-k3` both yield `kimi`. No id is special-cased,
    deliberately -- model catalogs churn, and a lookup table of names is a
    lookup table that goes stale without failing.

    It was literally `model.split("-")[0]` until a QA sweep found the guard
    bypassable by SPELLING: `GPT-5` differs from `gpt-6-astra` only in case,
    produced `GPT`, compared unequal to `gpt`, and was therefore cleared to
    review GPT-authored work. `gpt5` and `openai/gpt-5` did the same by
    separator and by namespace. A guard a capital letter walks past is not a
    guard, so normalisation happens here rather than at each call site --
    there is no version of this that is safe to leave to the caller.

    `claude` is its own family whatever it is pinned to; it is an in-session
    subagent, not a separate CLI with a model flag. An unpinned `codex` is
    `gpt` because that is the only family the Codex CLI serves. An unpinned
    `copilot` is None -- Copilot hosts several families and an unset model
    genuinely does not say which. None, never a placeholder string: two unset
    Copilot models must not compare equal to each other and report BARRED when
    the real reason is "unset".
    """
    if provider == "claude":
        return "claude"
    if isinstance(model, str) and model.strip():
        # Namespace off first (`openai/gpt-5`), then the leading letters, so
        # every separator convention collapses to the same token: `-`, `_`,
        # `.`, and a bare digit boundary as in `gpt5`.
        bare = model.strip().lower().rsplit("/", 1)[-1]
        head = re.match(r"[a-z]+", bare)
        return head.group() if head else bare
    if provider == "codex":
        return "gpt"
    return None


# Human-facing names for the model ids in use. A DISPLAY map, never a
# validation list: an id that is not here renders as itself, so pinning a
# model this release has never heard of works exactly as it did before. The
# `/crew:model` rule that no allowlist may gate a write is unchanged -- GPT-5
# and Sonnet 4 are already retired, and a command that refuses a model because
# it shipped before that model existed is worse than no validation.
#
# `kimi-k2.7-code` is the entry that earns this table. The `-code` suffix is
# load-bearing: probed 2026-09-05, bare `kimi-k2.7` returns `Model
# "kimi-k2.7" from --model flag is not available` and only the suffixed id
# answers. The display name is "Kimi 2.7" either way, so writing the display
# name into a config would produce a model the CLI rejects -- which is exactly
# why the two are separated here rather than left for a reader to infer.
MODEL_DISPLAY = {
    "gpt-6-astra": "GPT-6 Astra",
    "gpt-5.6-sol": "GPT-5.6 Sol",
    "gpt-5.6-luna": "GPT-5.6 Luna",
    "kimi-k2.7-code": "Kimi 2.7",
    "kimi-k3": "Kimi 3",
}


def display_model(model):
    """`"Kimi 2.7 (kimi-k2.7-code)"` for a known id, else the id itself.

    Human-facing text says the name; the wire id rides alongside because it is
    a debugging detail people genuinely need when a pin stops answering, and
    because for `kimi-k2.7-code` the name and the id are not the same string.
    """
    if not isinstance(model, str) or not model.strip():
        return None
    model = model.strip()
    name = MODEL_DISPLAY.get(model)
    return f"{name} ({model})" if name else model


def _provider_block(block, provider):
    return dict_or_empty(block.get(provider)) if isinstance(provider, str) else {}


def resolve_role(cfg, kind, role, author=None, available=None):
    """What actually backs one role, and why. Pure.

    `kind` is `"qa"` or `"dev"`; `role` is a name in that block's `roles`
    table (`review`, `developer`, ...). `author` is the family that WROTE the
    diff under review, from `author_families` below -- a single family, an
    iterable of them, or None when that is genuinely unknown, never a guess.
    It is plural because a dispatch record from another branch strikes two:
    the family it names and the family the config names. `available(provider, model)` is an
    optional probe returning False when the pinned model is gone; with no
    probe, nothing falls back.

    Returns a dict rather than a printed line, so a caller can assert on the
    decision instead of on stdout:

        {"kind", "role", "provider", "model", "reasoningEffort", "family",
         "source", "barred", "barredBy", "fellBack", "fallback",
         "fallbackBarred", "announce"}

    `source` is `"role-pin"` when the `roles` table decided it and
    `"block-default"` when the block's own `provider` did. Order of
    evaluation, which is the contract and not an implementation detail:

      0. **Provider legitimacy, for QA only.** A `qa` provider outside
         `QA_PROVIDERS` is BARRED outright, before family is even asked
         about. This is not the family guard wearing a new name: `family()`
         answers None for a provider it does not recognise, and the family
         guard only fires on a NAMED match, so an unrecognised or
         dev-only name (`localgpu`, a typo, a provider crew has never heard
         of) walked past both checks and came back `barred: False` with an
         empty `announce` -- indistinguishable from a real, cleared
         reviewer. `dev` rows are exempt: the guard governs who may REVIEW,
         never who may write, so a `dev` role resolves whatever it is
         pointed at (`validate_providers` is what refuses it, loudly, on
         write).
      1. **The family guard.** If the resolved family is the author's, the
         role is BARRED and the pin does not save it.
      2. **The pin, and only then the fallback.** A pinned model that
         `available` says is gone falls back to `fallback` -- and the fallback
         is family-checked too, because a claude fallback on claude-authored
         work is the same-family review the guard exists to prevent.

    `announce` is never empty when something happened. A review that quietly
    ran on the fallback is indistinguishable from one that ran on the pin, and
    the difference matters most exactly when the pin was chosen to get a
    different family onto the diff.
    """
    # `author` is a single family, an iterable of them, or None. It is plural
    # because a STALE dispatch record strikes two: the family the record names
    # and the family the config names. See `author_families`.
    if author is None:
        authors = frozenset()
    elif isinstance(author, str):
        authors = frozenset([author])
    else:
        authors = frozenset(f for f in author if f)

    block = dict_or_empty(dict_or_empty(cfg).get(kind))
    pin = dict_or_empty(dict_or_empty(block.get("roles")).get(role))
    provider = pin.get("provider") or block.get("provider") or "claude"
    sub = _provider_block(block, provider)
    model = pin.get("model") or sub.get("model")
    effort = pin.get("reasoningEffort") or sub.get("reasoningEffort")
    fallback = block.get("fallback") or FALLBACK_DEFAULT

    out = {
        "kind": kind,
        "role": role,
        "provider": provider,
        "model": model,
        "reasoningEffort": effort,
        "family": family(provider, model),
        "source": "role-pin" if pin else "block-default",
        "barred": False,
        "barredBy": None,
        "fellBack": False,
        "fallback": fallback,
        "fallbackBarred": False,
        "announce": [],
    }

    # `auto` is not a provider -- it is an instruction to walk `qa.order` --
    # so there is no family to check and no model to fall back from. Say that
    # rather than reporting a family of "auto".
    if provider == "auto":
        out["family"] = None
        out["announce"].append(
            f"{kind}.{role}: no pin, and {kind}.provider is `auto` -- "
            f"the candidate that runs is whichever of {kind}.order probes clean"
        )
        return out

    # 0. Legitimacy, before family, QA only. See the docstring's item 0.
    if kind == "qa" and provider not in QA_PROVIDERS:
        out["barred"] = True
        out["announce"].append(
            f"{kind}.{role}: BARRED -- `{provider}` is not a provider QA "
            "recognises, so nothing here can be proven independent of the "
            "author. An unrecognised name is not merely unproven -- it is "
            "not a reviewer at all, and `family() is None` for it must "
            "never read as no conflict."
        )
        return out

    # 1. The family guard, BEFORE the pin. See the docstring.
    if out["family"] is not None and out["family"] in authors:
        out["barred"] = True
        out["barredBy"] = out["family"]
        out["announce"].append(
            f"{kind}.{role}: BARRED -- {provider} speaks as the "
            f"`{out['family']}` family, which wrote this diff, so it may not "
            "review it"
        )
        return out

    # 2. The pin, and only then the fallback.
    if model and available is not None and not available(provider, model):
        out["announce"].append(
            f"{kind}.{role}: FELL BACK -- pinned model `{model}` on "
            f"{provider} is unavailable; running `{fallback}` instead"
        )
        out["fellBack"] = True
        out["provider"] = "claude"
        out["model"] = fallback
        out["family"] = family("claude", fallback)
        out["reasoningEffort"] = None
        if out["family"] in authors:
            out["fallbackBarred"] = True
            out["announce"].append(
                f"{kind}.{role}: the fallback `{fallback}` is also the "
                f"`{out['family']}` family that wrote this diff -- this is "
                "not an independent review"
            )
    return out


# Where a dispatch is recorded. `.work/`, not `.crew/`: this is ephemeral
# state about the checkout in front of you, not configuration, and a committed
# copy would travel to another machine and describe a dispatch that never
# happened there. `crew-setup/SKILL.md` adds it to .gitignore during setup.
DISPATCH_PATH = (".work", "dispatch.json")

# Kinds that may be RECORDED, which is exactly the set something READS.
# `author_family` reads `dev`; nothing reads a `qa` slot, so nothing writes
# one. A `--record-dispatch qa` flag whose output no code ever consults is
# state written to nowhere -- the same failure as a reader with no writer,
# and just as invisible. Give a kind a reader and add it here, in one change.
DISPATCH_KINDS = ("dev",)

# How many distinct dispatches to remember. The guard reads the whole list, so
# this bounds both the file and the strike set. Ten is well past the number of
# FAMILIES anyone has -- and families are what it counts, which is the whole
# point: keying the bound on `(provider, model)` let one provider cycling
# through ten model ids fill the history by itself and evict the family that
# actually wrote the diff, spending ten slots to carry one bit.
DISPATCH_HISTORY_MAX = 10

# How many BRANCHES the history remembers, newest-dispatched first.
#
# There is deliberately no bound on families WITHIN a branch. Any such bound
# is the same defect: dispatch the family that writes the diff, then enough
# newer dispatches with distinct families, and the one that wrote the code is
# pushed out of its own branch's history -- after which the guard reports
# proven provenance with the author missing and hands that family its own
# work. Raising the number moves the input and keeps the failure. The
# family-keyed dedup is the only bound a branch needs, because a family
# appears at most once in one no matter how many model ids it walks through.
#
# Branches are the axis that actually grows, so branches are what is capped.
# Dropping the fifty-first-oldest branch is not silent: a checkout with no
# record falls through to `config` or `stale`, both of which say so.
DISPATCH_BRANCHES_MAX = 50

# One file per dispatch, under `.work/dispatch.d/`. THE store; everything
# below reads from here.
#
# `dispatch.json` was a single shared file that every dispatch read, modified
# and rewrote, and three review rounds went by trying to make that safe. It
# cannot be made safe portably. A lock has to be reclaimable or one killed
# dispatch wedges the repo forever, and a reclaimable lock is two `os` calls
# against a pathname that a rival can replace between them -- Windows has no
# inode to compare, so "remove this file only if it is still the one I looked
# at" cannot be said. Verify-and-republish did not close it either: it holds
# only for the writer that lands LAST, and a writer whose read predates a
# rival's successful write still erases that rival afterward. Three writers
# are enough to lose the middle one permanently, and if the lost one is the
# family that wrote the diff, the guard clears it to review its own work.
#
# So there is no read-modify-write left to race. A dispatch creates a file
# nothing else will ever write, under a name nothing else will ever pick, and
# the reader merges what it finds. Concurrency stops being a correctness
# question and a malformed file costs exactly one entry instead of all of
# them.
DISPATCH_DIR = (".work", "dispatch.d")

# How many entry files may accumulate before the oldest are pruned. The read
# bound is per kind and family-keyed, so this is only about not letting a
# directory grow without limit in a long-lived checkout; it is deliberately
# far above `DISPATCH_HISTORY_MAX` so pruning can never be what decides which
# family is remembered.
DISPATCH_FILES_MAX = 200


def _entry_sort_key(entry, mtime=None):
    """How recent an entry is. Newest sorts highest. Never raises.

    `at` is what the writer said, and the file's own mtime is a second witness
    to the same event. The larger of the two wins, which is what makes an
    entry with a missing, hand-edited or non-numeric `at` still sort by when
    it was actually written rather than falling to the bottom as a zero.

    It does NOT make the ordering clock-independent -- a system clock that
    steps backward moves `at` and mtime together, and nothing in a directory
    of files can see that. What bounds the damage is that the bound is
    family-keyed and per kind: it only ever bites once more than
    `DISPATCH_HISTORY_MAX` DISTINCT families have been dispatched on one
    branch, and over-keeping is the safe direction anyway.
    """
    stamps = [float_or(entry.get("at"), 0.0)]
    if mtime is not None:
        stamps.append(mtime)
    return max(stamps)


def _entry_rank(entry, key):
    """`(tier, sort key)`. Tier 1 is a record this store wrote itself.

    Tier 0 is everything whose timestamp came from outside it: the legacy
    `dispatch.json`, and any record ADOPTED out of it. Adoption copies the
    file's claim about when a dispatch happened, and a claim is exactly what
    the tier exists not to trust -- an adopted entry carrying a far-future
    `at` otherwise became the newest record in the repo and took the `<kind>`
    slot that decides whether provenance is proven.

    An adopted record predates the store by definition, so sorting it below
    everything in the store is not a safety margin, it is the truth.
    """
    return (0 if entry.get("adopted") else 1, key)


def _dispatch_entries(root, lost=None):
    """Every entry in `.work/dispatch.d/`, as `(sort key, kind, entry)`.

    Never raises, and a file it cannot read costs exactly that file. A
    half-written or hand-mangled entry is skipped and its neighbours survive
    -- the property the single shared file did not have, where one malformed
    byte collapsed the whole record to `{}` and the guard fell back to reading
    the config.

    `lost`, when a list is passed, collects the name of every file that was
    skipped. Surviving the neighbours is only half the answer: the skipped
    file may have been the ONLY record of the dispatch that wrote the diff,
    and a reader that cannot tell "there was no such record" from "there was
    one and it would not parse" reports the second as the first. The caller
    turns a non-empty `lost` into an `unknown` source rather than a
    provenance claim over evidence it could not read.
    """
    directory = os.path.join(root, *DISPATCH_DIR)
    try:
        names = os.listdir(directory)
    except OSError:
        # An unreadable directory is not an empty one. If it exists, the
        # store may hold records nobody can see, and saying nothing here is
        # what turns that into a confident answer further up.
        if lost is not None and os.path.isdir(directory):
            lost.append(os.path.join(*DISPATCH_DIR))
        return []
    out = []
    for name in names:
        if not name.endswith(".json"):
            # NOT a silent skip. `_append_dispatch` writes `<base>.tmp` and
            # renames it, so a `.tmp` still sitting here is a write that was
            # interrupted between the two -- a dispatch that may have landed
            # and may not, which is the definition of evidence this store
            # cannot read. Skipping it quietly let the next readable entry
            # answer `dispatch` over it, which is round 9's finding wearing a
            # different file extension.
            #
            # A dispatch running concurrently in another process shows up
            # here for the moment between its write and its rename, and a
            # reader that lands inside that window answers `unknown`. That is
            # correct rather than unfortunate: a dispatch is in flight, so
            # who wrote this branch is genuinely not settled yet.
            _note_lost(lost, name)
            continue
        path = os.path.join(directory, name)
        text = read_text(path)
        if text is None:
            _note_lost(lost, name)
            continue
        try:
            entry = json.loads(text)
        except ValueError:
            _note_lost(lost, name)
            continue
        if not isinstance(entry, dict) or not entry.get("kind"):
            _note_lost(lost, name)
            continue
        try:
            mtime = os.path.getmtime(path)
        except OSError:
            mtime = None
        entry["_file"] = name       # for `_prune_dispatch_dir` only
        out.append((_entry_sort_key(entry, mtime), entry.pop("kind"), entry))
    return out


def _note_lost(lost, name):
    """Record one piece of evidence that could not be read."""
    if lost is not None:
        lost.append(name)


def _read_record_file(root, lost=None):
    """`dispatch.json` parsed, or `{}`. Never raises.

    `lost` collects this file's name when it EXISTS and yields no dict --
    malformed from a killed write, truncated, or unreadable. `{}` is returned
    either way, because there is nothing to return; the point of `lost` is
    that `{}` means two different things and only one of them is "no dispatch
    was ever recorded here". A 0.16.6 record is the only trace its dispatch
    left, so reporting an unparseable one as an absent one hands the next
    dispatch on that branch a clean provenance claim it has not earned.
    """
    path = os.path.join(root, *DISPATCH_PATH)
    text = read_text(path)
    if text is None:
        # Missing and unreadable are not the same. `read_text` answers None
        # for both, so the file system is asked which one this is.
        if os.path.exists(path):
            _note_lost(lost, DISPATCH_PATH[-1])
        return {}
    try:
        parsed = json.loads(text)
    except ValueError:
        _note_lost(lost, DISPATCH_PATH[-1])
        return {}
    if not isinstance(parsed, dict):
        _note_lost(lost, DISPATCH_PATH[-1])
        return {}
    return parsed


def _history_items(record, by_kind, kind, lost=None):
    """The `(rank, entry)` input `_merge_history` takes, for one kind.

    Exists so that `read_dispatch` and `_prune_dispatch_dir` cannot disagree
    about what the history IS. They did: the pruner protected what the merge
    returned but fed it the store alone, while the reader fed it the store and
    the legacy `dispatch.json` together. A branch whose legacy record was
    newer than its store entries then ranked inside the branch cap for the
    reader and outside it for the pruner, which deleted every store file that
    branch had -- and checking it out afterwards left a legacy record naming a
    different family, reported as proven, with the family that wrote the diff
    gone.

    A pruner that has to be kept in agreement with a reader drifts the next
    time either one changes. One function, two callers.
    """
    items = [(_entry_rank(entry, key), entry)
             for key, entry in by_kind.get(kind) or []]

    # Every drop below is REPORTED. This function runs before
    # `_merge_history`, so anything it discards quietly is something the
    # merge's own reporting never gets to see -- which is how round 10's fix
    # came to be undone for the one record shape it was written for.
    raw = record.get(f"{kind}History")
    legacy = []
    if isinstance(raw, list):
        for entry in raw:
            if isinstance(entry, dict):
                legacy.append(entry)
            else:
                # A history whose members are not records is a mangled file,
                # not an empty history.
                _note_lost(lost, DISPATCH_PATH[-1])
    elif raw is not None:
        _note_lost(lost, DISPATCH_PATH[-1])

    if kind in record:
        slot = record.get(kind)
        if isinstance(slot, dict):
            # Passed through even with no provider, so `_merge_history` --
            # the one funnel -- makes that call and reports it. The test used
            # to be `slot.get("provider")` right here, which meant the legacy
            # slot took the only path round 10 did not cover.
            legacy.append(slot)
        else:
            # `_merge_history` cannot read a non-dict at all, so it is
            # reported here instead. `None` in the slot lands here too: a key
            # that is present and holds nothing is a record that was written
            # and lost, not a record that was never made.
            _note_lost(lost, DISPATCH_PATH[-1])

    items.extend(((0, _entry_sort_key(h)), h) for h in legacy)
    return items


def _merge_history(items, pin=None, lost=None):
    """Newest first, deduplicated on what the guard reads, bounded.

    `items` is `(rank, entry)`, and `rank` is `(tier, sort key)`. The tier is
    what makes the ordering independent of any clock: an entry from
    `.work/dispatch.d/` is tier 1 and one read out of the legacy
    `dispatch.json` is tier 0, so nothing written in the legacy file can
    outrank the store no matter what its `at` says. A `dispatch.json` carrying
    far-future timestamps -- a clock that ran ahead, a hand edit, a restored
    backup -- otherwise evicted the dispatch that had just happened, which is
    the same hazard the write path had and is why this is structural rather
    than a comparison between two wall-clock values that step together.

    The key is the FAMILY, not the model id,
    because the family is the only thing `author_families` ever compares.
    Keyed on the model, one provider walking through ten ids on one branch
    filled the whole history by itself and evicted the family that wrote the
    diff -- ten entries carrying one bit between them.

    An UNKNOWN family (an unpinned copilot) keeps the provider and model in
    its key instead: None must not compare equal to None here, or two
    genuinely different unpinned providers collapse into one and the second is
    dropped as a duplicate of the first.

    Two rules about what a slot may be spent ON, both of which exist because
    the bound evicting the wrong entry is the same failure as never recording
    it.

    **An entry with no `provider` spends nothing.** `author_families` skips
    those -- they name no author, so they cannot BE the author -- and ten of
    them ahead of a real dispatch emptied the history of the family that wrote
    the diff. A hand-edited file, a truncated write, a future field: none of
    them are evidence, and something that is not evidence must not displace
    something that is.

    **Nothing bounds the families within a branch, and nothing may.**
    `author_families` filters to the current checkout AFTER this merge, so a
    store-wide bound let other branches evict this one's only record -- and
    then a PER-BRANCH bound did the same thing from inside: dispatch the
    family that writes the diff, then enough newer dispatches with distinct
    families, and the author is pushed out of its own branch's history while
    the guard still reports proven provenance. Every finite cap has that
    input. The dedup is the bound a branch gets, and it is enough: a family
    appears at most once in one.

    **Branches are what is capped**, at `DISPATCH_BRANCHES_MAX`, ranked by
    each branch's newest entry. That is the axis that grows without limit,
    and dropping the oldest of fifty is fail-loud -- a checkout with no record
    reads as `config` or `stale`, and both say so out loud.

    `pin` is a zero-argument callable naming a branch that is never a
    candidate for eviction, and the caller passes one that resolves to the
    CURRENT checkout. Without it the cap could drop the branch the reviewer is
    standing on -- fifty branches dispatched more recently is all it takes,
    and that is the same defect as evicting the family that wrote the diff,
    one axis over. It is a callable and not a value because resolving it costs
    a `git rev-parse`, and the cap does not bite at all in a repository with
    fewer than fifty branches.
    """
    seen, kept, newest = set(), {}, {}
    for rank, entry in sorted(items, key=lambda pair: pair[0], reverse=True):
        if not entry.get("provider"):
            # Skipped, and REPORTED. It still must not spend a slot in the
            # bound -- something that is not evidence must not displace
            # something that is -- but it is not nothing either: an entry
            # that parses and carries a `kind` is a record whose author this
            # store cannot name, and dropping it in silence let the next
            # dispatch on the branch answer `dispatch` over it. A record of
            # someone unnameable is not a record of nobody.
            #
            # Here rather than in `_dispatch_entries` because this is the one
            # funnel both sources run through: entry files, the legacy
            # `<kind>History`, and the legacy slot. Noting it upstream would
            # have covered the store and left the legacy path silent.
            _note_lost(lost, entry.get("_file") or DISPATCH_PATH[-1])
            continue
        branch = entry.get("branch")
        fam = family(entry.get("provider"), entry.get("model"))
        key = ((fam, branch) if fam is not None
               else (None, entry.get("provider"), entry.get("model"), branch))
        if key in seen:
            continue
        seen.add(key)
        kept.setdefault(branch, []).append((rank, entry))
        # The branch's rank is set by the FIRST entry seen for it, which is
        # its newest -- the loop is already in newest-first order.
        newest.setdefault(branch, rank)

    ranked = sorted(newest, key=lambda name: newest[name], reverse=True)
    if len(ranked) > DISPATCH_BRANCHES_MAX:
        here = pin() if pin else None
        live = ranked[:DISPATCH_BRANCHES_MAX]
        if here is not None and here in kept and here not in live:
            live = live[:DISPATCH_BRANCHES_MAX - 1] + [here]
    else:
        live = ranked
    out = [pair for branch in live for pair in kept[branch]]
    # Newest-first overall, because that is the shape every reader has always
    # been handed -- and on the RANK, which carries the tier, not on `at`
    # alone. `read_dispatch` takes the `<kind>` slot from `out[0]` and
    # `author_families` reads that slot's branch to decide whether provenance
    # is proven, so re-sorting on the raw timestamp handed the slot to
    # whatever the legacy file claimed the largest one for.
    out.sort(key=lambda pair: pair[0], reverse=True)
    return [entry for _rank, entry in out]


def read_dispatch(root):
    """Every dispatch this checkout recorded, merged. Never raises.

    Returns the same shape it always did -- a `<kind>` slot holding the most
    recent dispatch and a `<kind>History` list, newest first -- so
    `author_families`, `/crew:review` and `/crew:model` did not have to change
    when the store underneath did.

    Three sources are unioned, in order of authority:

      1. `.work/dispatch.d/`, one immutable file per dispatch. Authoritative.
      2. `dispatch.json`'s `<kind>History`, if some older version wrote one.
      3. `dispatch.json`'s `<kind>` slot itself, which is all a 0.16.6 record
         has. A repo upgraded mid-branch must not lose the dispatch that is
         already recorded there, so it is folded in rather than replaced.

    A record that exists only in (2) or (3) is never rewritten into (1). It is
    read where it lies until the bound ages it out, which is what makes this
    an upgrade rather than a migration that can fail halfway.
    """
    lost = []
    record = _read_record_file(root, lost)

    by_kind = {}
    for key, kind, entry in _dispatch_entries(root, lost):
        by_kind.setdefault(kind, []).append((key, entry))

    # Resolved at most once per call, and only if the branch cap bites.
    cached = []

    def pin():
        if not cached:
            cached.append(current_branch(root))
        return cached[0]

    for kind in DISPATCH_KINDS:
        items = _history_items(record, by_kind, kind, lost)
        if not items:
            continue
        # `_file` is bookkeeping for the pruner and is not part of the
        # record any reader is handed.
        history = [{k: v for k, v in entry.items() if k != "_file"}
                   for entry in _merge_history(items, pin, lost)]
        record[f"{kind}History"] = history
        # The slot is the newest entry, recomputed rather than trusted: it is
        # written unlocked and best-effort, so a lost update there must cost
        # nothing. `report["dispatch"]` and `/crew:review`'s mtime test are
        # what still read the file itself.
        record[kind] = history[0]
    # Popped first, so a hand-edited file carrying this key cannot assert
    # something about a read it was not present for. Set only when true.
    record.pop("unreadable", None)
    if lost:
        # The NAMES, not a bare True. This condition is repo-wide, permanent,
        # and only a human can clear it -- nothing prunes below
        # `DISPATCH_FILES_MAX`, so one corrupt file makes every review in the
        # repo read `unknown` until someone deletes it. "Delete the
        # unparseable file" is not guidance if it does not say which one.
        # Still a truthy value, so every `if record.get("unreadable")`
        # already written keeps failing closed.
        record["unreadable"] = sorted(set(lost))
    return record


def current_branch(root):
    """The checked-out branch name, or None outside a repo / on a detached HEAD.

    `git rev-parse --abbrev-ref HEAD` answers `HEAD` when detached, which is
    not a branch and must not be recorded as one -- two unrelated detached
    checkouts would both say `HEAD` and compare equal, which is the false
    freshness this field exists to remove.
    """
    name = git_out(root, "rev-parse", "--abbrev-ref", "HEAD")
    return None if not name or name == "HEAD" else name


def in_git_repo(root):
    """True, False, or None when git could not answer.

    `current_branch` returns None for two states that are not remotely alike:
    a plain directory that has no branches, and a repository whose HEAD is
    detached or mid-rebase. Provenance can be trusted in the first and never
    in the second, so the branch value alone cannot decide it -- a dispatch
    recorded while detached stores `branch: null`, which would otherwise
    compare equal to the no-repo case and read as proof.

    The third state is what makes this tri-state rather than a bool. `git_out`
    answers None for git being absent, a timeout, a vanished `root`, and a
    non-repository alike, so collapsing it to a bool made every transient
    failure look like the SAFE "no repository here" case -- and the caller
    reads that as proof of provenance. A guard that fails open when its probe
    breaks is worse than one that has no probe, because it looks like it
    checked. None means "could not tell", and the caller treats it as unproven.
    """
    # Not `git_out`: it answers None for "git ran and said no" and for "git
    # could not be run" alike, and those are the two states this function
    # exists to separate. A non-zero exit IS an answer -- git ran, and this
    # is not a work tree. Only a failure to execute is unknown.
    try:
        done = subprocess.run(
            ("git", "rev-parse", "--is-inside-work-tree"), cwd=root,
            capture_output=True, text=True, timeout=_GIT_TIMEOUT,
            check=False, stdin=subprocess.DEVNULL,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if done.returncode != 0:
        return False
    return done.stdout.strip() == "true"


def record_dispatch(root, kind, role, provider, model=None, branch=None):
    """Record which role, provider and model actually ran. Returns the record.

    Written at dispatch, read by `author_family` -- the whole point being that
    the self-review guard judges what RAN rather than what the config happens
    to say now. A config read after the fact answers a different question: it
    describes the next dispatch, not the one that produced the diff in front
    of the reviewer.

    `branch` defaults to the checkout's current branch and is what makes the
    record falsifiable ACROSS branches. There is one file per checkout with
    one slot per kind, so a dispatch made on another branch overwrites this
    one and then reads as perfectly fresh: `/crew:review`'s mtime test
    compares the record against the diff's merge-base and cannot see a branch
    switch at all, because the record is genuinely newer. Recording the branch
    is the only thing that can tell those two states apart.

    `kind` must be one of `DISPATCH_KINDS`. Writing a kind nothing reads is
    the same inert-feature class as a reader with no writer, so the set is
    enforced here rather than left to the caller's discretion -- adding a
    reader means adding its kind to that tuple, in the same change.
    """
    if kind not in DISPATCH_KINDS:
        raise ValueError(
            f"no reader for dispatch kind {kind!r}; "
            f"recordable kinds are {', '.join(DISPATCH_KINDS)}")
    if branch is None:
        branch = current_branch(root)
    entry = {"role": role, "provider": provider, "model": model,
             "branch": branch, "at": time.time()}

    # One file, created once, never modified. There is nothing to race: no
    # reader is mutated, no writer is overwritten, and a writer that fails
    # takes only its own entry down with it. See `DISPATCH_DIR` for the three
    # review rounds that went into learning that.
    #
    # The answer is kept. Discarding it made a failed write INVISIBLE: this
    # dispatch left no trace, the next one on the same branch recorded a
    # different family, and `author_families` then returned that family
    # labelled `dispatch` with the one that actually wrote the diff absent.
    # There is no durable marker to leave instead -- the write that failed is
    # the store itself, and a marker file lands in the same directory that
    # just refused one -- so the fix is that the caller is told. `main` exits
    # non-zero on it; a dispatch that was not recorded is not a dispatch this
    # guard can judge later.
    stored = _append_dispatch(root, kind, entry)
    # The slot is only overwritten once whatever it held is safely in the
    # store. Making the adoption retryable does nothing on its own if the
    # record it retries FROM was destroyed by the same call that failed:
    # `_write_slot` would have replaced the pre-0.16.7 record with this
    # dispatch, and the next run would find an empty slot and nothing to
    # adopt. Skipping the slot write costs a stale display field and a stale
    # mtime for one dispatch, both of which `read_dispatch` recomputes from
    # the store anyway.
    if _adopt_slot(root, kind):
        _write_slot(root, kind, entry)
    record = read_dispatch(root)
    if not stored:
        # Present only when it is True, so no reader can mistake the key's
        # absence for a claim either way -- every existing caller that does
        # not look for it is unchanged, and one that does gets a fact rather
        # than a default.
        record["unrecorded"] = True
    return record


def _adopt_slot(root, kind):
    """Get the slot's own record into the store. True if the slot may now be
    overwritten. Never raises.

    `_write_slot` is about to overwrite that slot, and on a repo upgraded
    mid-branch it is the ONLY record of the family that wrote the code being
    reviewed. Overwriting it clears that family to review its own diff --
    the exact failure this whole subsystem exists to prevent, reintroduced by
    the release that was meant to close it.

    Runs whenever the slot's own record is not already in the store, which is
    both idempotent and RETRYABLE. The gate was "the store is empty for this
    kind" until round 4 found what that costs: the adoption's write fails
    transiently, the dispatch that follows lands and fills the store, and
    every later run then sees a non-empty store and declares there is nothing
    to adopt -- while `_write_slot` has already overwritten the slot it was
    supposed to save. One transient error and the family that wrote the branch
    is gone permanently.

    Idempotent by dedup rather than by coordination: two concurrent first
    dispatches can both pass the gate and both copy it, and `_merge_history`
    keys on the family, so the duplicate collapses. That is what makes it safe
    on a path with no lock.
    `adopted` marks where the entry came from, for anyone reading the
    directory; nothing branches on it.
    """
    # An unreadable file is NOT a file with nothing to lose, which is what
    # this said until the reader learned to distrust one. The unparseable
    # record is now the evidence: it is what makes `author_families` answer
    # `unknown` rather than certifying a family that may not have written the
    # diff. Overwrite it and the next read finds a well-formed record, sees
    # nothing lost, and reports proven provenance with the author gone -- the
    # finding this round closed, re-opened by the next dispatch that runs.
    #
    # So the slot is refused while it cannot be read. That costs a stale
    # display field and a stale mtime for as long as the bad file sits there,
    # both of which `read_dispatch` recomputes from the store, and it holds
    # the guard closed until a human deletes the file the report names.
    path = os.path.join(root, *DISPATCH_PATH)
    text = read_text(path)
    if text is None:
        # Missing means nothing to lose. Present-but-unopenable does not:
        # `read_text` answers None for both, so the file system is asked.
        return not os.path.exists(path)
    try:
        record = json.loads(text)
    except ValueError:
        return False                    # unreadable; overwriting loses the
                                        # only sign that anything was lost
    slot = dict_or_empty(record).get(kind)
    if not isinstance(slot, dict) or not slot.get("provider"):
        return True                     # no record in the slot
    # Is THIS record already in the store? Not "is the store non-empty" --
    # that gate closed permanently the first time the adoption's write failed
    # transiently, because the dispatch that followed filled the store and
    # every later run then declared there was nothing to adopt. The legacy
    # slot was overwritten in the meantime and the family that wrote the
    # branch was gone for good. Comparing the record itself makes the
    # adoption retry on the next dispatch, which is the only version of this
    # that survives a failure.
    for _key, entry_kind, entry in _dispatch_entries(root):
        if entry_kind != kind:
            continue
        if all(entry.get(field) == slot.get(field)
               for field in ("provider", "model", "branch")):
            return True                 # already in the store
    return _append_dispatch(root, kind, dict(slot, adopted=True))


def _append_dispatch(root, kind, entry):
    """Write `entry` as its own file. True if it landed. Never raises.

    A dispatch must not be aborted because its bookkeeping failed -- an
    unwritable `.work/`, a full disk, a permission change mid-run. The review
    that follows falls back to reading the config and SAYS so, which is a
    worse answer than a record but a far better outcome than refusing to do
    the work.

    Written to a temp name and renamed into place, so a reader never sees a
    half-written entry. The name carries the kind and the timestamp for a
    human reading the directory, and a random token because that is what makes
    it unique: two threads in one interpreter share a PID, and the timestamp
    alone can repeat at the clock's resolution.
    """
    directory = os.path.join(root, *DISPATCH_DIR)
    stamp = f"{entry.get('at') or 0.0:.6f}".replace(".", "")
    base = os.path.join(directory, f"{kind}-{stamp}-{uuid.uuid4().hex[:12]}")
    tmp_path = f"{base}.tmp"
    try:
        os.makedirs(directory, exist_ok=True)
        with open(tmp_path, "w", encoding="utf-8") as handle:
            json.dump(dict(entry, kind=kind), handle, indent=2,
                      sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, f"{base}.json")
    except OSError:
        try:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        except OSError:
            pass
        return False
    _prune_dispatch_dir(root)
    return True


def _write_slot(root, kind, entry):
    """Update `dispatch.json`'s `<kind>` slot. Best-effort. Never raises.

    Unlocked, and that is now fine: `read_dispatch` recomputes the slot from
    the directory, so losing this race costs a display field and a file mtime
    rather than a record. It is still written because two things read the file
    directly -- `/crew:review` takes its freshness from this file's mtime, and
    `/crew:model` prints the last dispatch from the slot.
    """
    path = os.path.join(root, *DISPATCH_PATH)
    record = {}
    text = read_text(path)
    if text is not None:
        try:
            parsed = json.loads(text)
        except ValueError:
            parsed = None
        if isinstance(parsed, dict):
            record = parsed
    record[kind] = entry
    tmp_path = f"{path}.{os.getpid()}.{uuid.uuid4().hex[:8]}.tmp"
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(tmp_path, "w", encoding="utf-8") as handle:
            json.dump(record, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, path)
    except OSError:
        try:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        except OSError:
            pass
        return False
    return True


def _prune_dispatch_dir(root):
    """Drop the oldest entry files once there are too many. Never raises.

    Nothing else deletes them, and a long-lived checkout dispatches for
    months. The bound is far above what the reader keeps, so this can never be
    what decides which family is remembered -- and a deletion that fails is
    ignored, because a directory that is larger than intended is not a
    correctness problem.
    """
    directory = os.path.join(root, *DISPATCH_DIR)
    try:
        names = [n for n in os.listdir(directory) if n.endswith(".json")]
    except OSError:
        return
    if len(names) <= DISPATCH_FILES_MAX:
        return

    # What the reader would keep, computed the same way the reader computes
    # it. Counting raw files instead let a busy repo's other branches push
    # this branch's ONLY record past the cap and delete it -- pruning
    # deciding which family is remembered, which is precisely what the cap
    # was documented as never doing.
    protected = set()
    cached = []

    def pin():
        if not cached:
            cached.append(current_branch(root))
        return cached[0]

    record = _read_record_file(root)
    by_kind = {}
    # Every file this pass could not read is protected too. A reader that
    # answers `unknown` over a malformed entry is undone by a pruner that
    # deletes it: the next read finds a clean directory, sets no
    # `unreadable`, and returns `dispatch` with whatever that file held gone
    # and nothing left to say it was ever there. The protection is stronger
    # than a live record's, not weaker -- a live record can be reconstructed
    # from the merged history, and this file is the only thing between a lost
    # dispatch and a confident answer about it. It leaves when a human
    # deletes it, which is why `read_dispatch` reports its name.
    lost = []
    for key, entry_kind, entry in _dispatch_entries(root, lost):
        by_kind.setdefault(entry_kind, []).append((key, entry))

    for kind in DISPATCH_KINDS:
        for entry in _merge_history(
                _history_items(record, by_kind, kind, lost), pin, lost):
            token = entry.get("_file")
            if token:
                protected.add(token)
    # After the merge, because the merge adds to `lost` too -- an entry that
    # parses and names no provider is reported there, and a file the report
    # names has to survive long enough for someone to delete it.
    protected.update(lost)

    aged = []
    for name in names:
        if name in protected:
            continue
        path = os.path.join(directory, name)
        try:
            aged.append((os.path.getmtime(path), path))
        except OSError:
            continue
    aged.sort(reverse=True)
    # The cap counts only what is NOT protected, so a repo whose live history
    # legitimately exceeds it keeps every live entry and prunes nothing. A
    # directory larger than intended is untidy; a missing author family is a
    # guard that passes a diff to the model that wrote it.
    #
    # `protected` cannot grow without limit, which is what makes that safe to
    # say: `_merge_history` keeps at most `DISPATCH_BRANCHES_MAX` branches and
    # at most one entry per family within each, so the live set is bounded by
    # the number of model families that exist. Everything outside it is
    # deletable, and `keep` reaching zero means every deletable file goes --
    # which is the correct answer, not a stall.
    keep = max(0, DISPATCH_FILES_MAX - len(protected))
    for _mtime, path in aged[keep:]:
        try:
            os.remove(path)
        except OSError:
            pass


def author_families(root, cfg, stale=False):
    """`(families, source)` -- who wrote the code here, and how we know.

    `families` is a frozenset because a stale record strikes TWO of them, and
    `source` is one of:

      * `"dispatch"` -- a record exists and its branch matches this checkout.
        The guard is judging what actually ran.
      * `"config"` -- no record, so `dev` was read out of the config. That
        describes the NEXT dispatch rather than the diff in front of the
        reviewer, and every caller has to say so rather than presenting a
        guess as a fact.
      * `"stale"` -- a record exists but names a DIFFERENT branch, so it
        cannot describe the commits under review. This **fails closed**: the
        recorded family and the config family are BOTH struck, matching what
        `commands/review.md` does with a record that predates the merge-base.
        Dropping the stale record and trusting config is the one direction
        that can under-bar -- if codex wrote the commits and the config has
        since been changed to `claude`, discarding the record clears codex to
        review its own work. Over-barring costs a rung; under-barring costs
        the entire point of the guard.

    Provenance is proven only when the checkout has a readable branch and the
    record names the same one -- or when this is not a repository at all and
    the record names none, the one case with no branches to confuse. A
    detached HEAD, a rebase in progress, or a record written while detached
    are all unprovable and fail closed.

    A record with no branch, read in a checkout that HAS one, is stale: it
    was written before 0.16.0's field existed and cannot prove which branch
    it came from, and trusting it strikes only its own family while leaving
    the configured one clear to review its own diff. A checkout with no
    branch at all is the exception -- nothing to switch between means none of
    the risk -- so a non-git repo is not barred forever for lacking git.

    `stale=True` is how a caller that CAN compare the record against the
    diff's merge-base reports that verdict; only `/crew:review` can make that
    comparison, and without a way to say so its answer never reached the
    resolved report that every later step reads.
    """
    dispatch = read_dispatch(root)
    # Something in `.work/` exists and would not parse. It may have been the
    # only record of the dispatch that wrote this diff -- a 0.16.6
    # `dispatch.json` left malformed by a killed write is exactly that -- so
    # no answer below this line may claim proven provenance, and the "no
    # record" fallback may not claim there was none. Not scoped to a branch,
    # because a file that will not parse cannot be attributed to one.
    unread = bool(dispatch.get("unreadable"))
    recorded = dict_or_empty(dispatch.get("dev"))
    decided = resolve_role(cfg, "dev", "developer")
    if recorded.get("provider"):
        here = current_branch(root)
        there = recorded.get("branch")
        # Every family dispatched on THE BRANCH IN FRONT OF THE REVIEWER,
        # not just the last one -- see record_dispatch for why one slot was
        # not enough. A record from another branch is excluded: it did not
        # write this diff, and barring it would over-bar permanently rather
        # than by a rung.
        #
        # `here`, NOT `there`. They are the same value in the proven path, so
        # filtering on the last record's branch looks equivalent -- and in
        # the STALE path, which is the one that matters, it is not: codex
        # writes the diff here, a claude dispatch on another branch
        # overwrites the slot, and filtering on `there` then keeps only that
        # claude record and forgets codex completely. That is the finding
        # this history exists to close, reintroduced one line further down.
        #
        # And when `here` is None, keep EVERYTHING. A None branch has two
        # completely different causes and only one of them is evidence: a
        # directory that provably is not a repository has no branches to
        # confuse, while a detached HEAD, a rebase in progress, or git failing
        # to answer means the branch is unknown. Filtering on `== None` in the
        # second case throws away every named-branch record -- so codex
        # dispatches on `feature`, claude takes the slot on `main`, the
        # reviewer opens the feature commit detached, and codex is handed its
        # own diff to review. The absence of evidence is the state this guard
        # fails closed on.
        in_repo = in_git_repo(root)
        keep_all = here is None and in_repo is not False
        recorded_families = {
            family(item.get("provider"), item.get("model"))
            for item in dispatch.get("devHistory") or []
            if isinstance(item, dict) and item.get("provider")
            and (keep_all or item.get("branch") == here)
        }
        # The slot itself is always struck, wherever it was recorded: it is
        # the one dispatch we know about with no history to corroborate it,
        # and a record written by a version before `devHistory` existed has
        # no history entry at all.
        recorded_families.add(family(recorded.get("provider"),
                                     recorded.get("model")))
        # Captured BEFORE the discard, because the discard is what destroys
        # it. See the `unnamed` return below.
        unnamed = None in recorded_families
        recorded_families.discard(None)
        # Strike BOTH unless the record positively proves it is about this
        # branch. Three states reach here and only one of them is evidence:
        #   * branches known and different -- stale, plainly.
        #   * `stale=True` -- the caller compared the record against the
        #     diff's merge-base and found it older. Only /crew:review can
        #     make that comparison, so it has to be able to say so; without
        #     this argument its verdict never reached the resolved report and
        #     the report kept saying `dispatch` with one family in it.
        #   * this checkout HAS a branch and the record does not name one --
        #     a record written before the `branch` field existed. Trusted
        #     until now on compatibility grounds, which was the wrong
        #     direction: it may have been written on another branch minutes
        #     ago, and trusting it strikes only its family while leaving the
        #     config's own clear to review its own diff. Over-barring costs a
        #     rung; under-barring costs the entire point of the guard. The
        #     cost is one over-barred review per repo, until the next
        #     dispatch records a branch.
        #
        # `is False`, not `not ...`: in_git_repo answers None when git could
        # not be asked, and `not None` is True, which would hand a broken
        # probe the same verdict as a proven non-repository.
        #
        # Three earlier versions of this test were wrong in three different
        # directions, which is why it is spelled out rather than clever.
        # `here and there != here` short-circuited on a None `here` and
        # trusted a detached HEAD. Plain `here != there` fixed that and then
        # trusted a record written WHILE detached, because that record stores
        # `branch: null` and None == None. Only repository presence separates
        # the harmless missing branch from the dangerous unreadable one.
        # Provenance is PROVEN in exactly two shapes, and trusted in no
        # other: a readable branch that matches the record's, or a directory
        # that is not a repository at all paired with a record that names no
        # branch. Everything else -- a detached HEAD, a rebase in progress, a
        # record written while detached, a branch the record does not name --
        # is unprovable, and unprovable fails closed.
        proven = ((here is not None and here == there)
                  or (there is None and in_repo is False))
        if stale or not proven:
            return frozenset(
                recorded_families | {decided["family"]}
            ) - {None}, "stale"
        # A dispatch we can place on this branch, whose family nobody can
        # name. An unpinned `copilot` is exactly this: Copilot hosts several
        # families and an unset model does not say which, so `family()`
        # answers None -- correctly, because None is the honest answer and a
        # placeholder string would compare equal to the next unset one.
        #
        # `discard(None)` then empties the set, and the old return handed
        # that back labelled `dispatch`: "the guard is judging what actually
        # ran". Nothing is struck, every reviewer reads as eligible, and the
        # report says the provenance was proven. That is this codebase's
        # recurring bug in its purest form -- an unknown collapsing into the
        # safe-looking value, wearing the label of a check that happened.
        #
        # There is no set to return here. Barring the config's family instead
        # would be a guess about who wrote the diff, and barring everything
        # would take a real reviewer off it on the strength of a value nobody
        # established. So the answer is the honest one: a dispatch happened,
        # its family is unknown, and NO reviewer can be proven independent of
        # it. `crew_config.model_report` turns that into
        # `independentReviewer: False`, which is what actually stops the
        # review from being certified.
        # `unnamed`, not `not known`. Round 3 closed the case where every
        # recorded family was unknown and left the MIXED case wide open: the
        # discard above ran first, so `{None, "gpt"}` arrived here as
        # `{"gpt"}` with nothing left to say a second dispatch had ever been
        # unreadable, and it was returned as `dispatch` -- proven provenance.
        # An unpinned Copilot serving Claude writes the diff, codex is
        # dispatched on the same branch after it, and the guard clears Claude
        # to review Claude's own work. Same bug as round 3, one instance
        # narrower: an unknown collapsing into the safe-looking value.
        #
        # The known families are still RETURNED, because they still ran and
        # still must be struck. Only the source changes, and that is what
        # withholds the certification: `crew_config.model_report` reads
        # `unknown` and sets `independentReviewer: False`. Striking what is
        # known while refusing to call the provenance proven is the honest
        # answer to "one of these dispatches has no name" -- the alternative,
        # dropping the known family to keep the empty-set shape, would clear
        # the one reviewer we have positive evidence against.
        #
        # `unnamed` alone, with no `not known` beside it: reaching here needs
        # a provider in the slot, and the slot's own family is added
        # unconditionally, so `recorded_families` is never empty and an empty
        # `known` means every member was None -- which is `unnamed`. Carrying
        # the second test would read as a guard over a case it cannot see,
        # and no mutation of it could ever go red.
        known = frozenset(recorded_families) - {None}
        return known, ("unknown" if unnamed or unread else "dispatch")
    # No record: read the config. `decided` above asked `resolve_role` for the
    # `developer` role rather than the `dev` block's own provider --
    # `dev.roles.developer` is a pin that OVERRIDES that default, so reading
    # the block alone reports the wrong family for exactly the config the role
    # table exists to express. A repo with `dev.provider: "claude"` and
    # `developer` pinned to codex would otherwise strike claude and clear
    # codex to review codex's diff. `developer` is the role that writes;
    # security and infrastructure-architect do not commit.
    #
    # frozenset, like every other branch: an unknowable family (an unset
    # Copilot model) is the EMPTY set, never `{None}` and never a bare None.
    # A caller that strikes what this returns must strike nothing in that
    # case, and a None leaking into the set would compare equal to another
    # unknown and bar a reviewer on the strength of two absences.
    #
    # `unknown` rather than `config` when something would not parse. The
    # config family is still returned and still struck -- it is the best
    # guess available and striking it costs a rung -- but `config` states
    # that no dispatch was recorded, and that is a claim this read cannot
    # make about a file it could not open.
    return (frozenset(f for f in (decided["family"],) if f),
            "unknown" if unread else "config")


def float_or(value, default):
    """`value` as a float, or `default`. Same contract as `int_or`.

    Timestamps come out of a hand-editable JSON file, so the type is whatever
    someone typed, and an unguarded comparison against one is a TypeError that
    takes out every session in the repository.
    """
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def int_or(value, default):
    """`value` as an int when it plausibly is one, else `default`.

    Config is hand-edited, so every numeric field arrives untrusted. A bool is
    rejected on purpose: `True` is an int in Python, and a config saying
    `"schema": true` means someone was confused, not that the schema is 1.
    """
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value.strip())
        except ValueError:
            return default
    return default


def evaluate_triggers(state):
    """Reasons the PM should speak up, in TRIGGERS order."""
    knowledge = state.get("knowledge") or {}
    graph = knowledge.get("graph") or {}
    health = state.get("health") or {}
    work = state.get("work") or {}
    diagrams = dict_or_empty(state.get("diagrams"))

    # `schema` is normalised by collect(), but evaluate_triggers is also called
    # directly by tests and by the crew:pm agent, so it must not assume that.
    # .get(key, default) substitutes the default only when the KEY IS ABSENT --
    # a present `"schema": null` returns None, and `None < 2` is a TypeError
    # that would break every session opened in the repo.
    schema = int_or(state.get("schema", 1), 1)
    incident = dict_or_empty(state.get("incident"))
    fired = {
        "incidentActive": bool(incident.get("active")),
        # Present but past its expiry. The gates are already back on -- that
        # part is automatic -- but the skipped checks are still owed, and
        # nothing else will ever mention them again.
        "incidentUnclosed": bool(incident.get("present"))
        and bool(incident.get("expired")),
        "upgradeNeeded": schema < SCHEMA_CURRENT,
        "handoffPending": bool(work.get("handoffPending")),
        # `endpoints.installed` is False whenever gizmoduck is absent (see
        # read_endpoints/gizmoduck_installed), which makes this the one line
        # that has to be inert on every machine that never installed it --
        # `unscanned` is [] in that case, and bool([]) is False regardless.
        "endpointUnscanned": bool(dict_or_empty(state.get("endpoints")).get("unscanned")),
        # An absent graph is stale by definition -- there is nothing to trust.
        "graphStale": not graph.get("present") or not graph.get("current"),
        "knowledgeBehind": bool(knowledge.get("behind")),
        "diagramsStale": bool(diagrams.get("behind")),
        # Only meaningful once there is something to draw from. A repo with no
        # codemap has not decided what its subsystems ARE yet, and demanding
        # three diagrams of it on every session start is noise on a fresh
        # setup -- the same reason reviewNotWorking waits for a first review.
        "diagramsMissing": bool(diagrams.get("missing"))
        and bool(knowledge.get("subsystems")),
        # `rate is None` means no reviews have run. A repo that has reviewed
        # nothing has not got a broken review, and saying so would be noise
        # on every fresh setup.
        "reviewNotWorking": health.get("rate") is not None
        and health["rate"] < HEALTHY_LOW,
        "ticketsTooLarge": health.get("rate") is not None
        and health["rate"] > HEALTHY_HIGH,
    }
    return [name for name in TRIGGERS if fired[name]]


def collect(root, cfg_override=None):
    """Full crew state for a repository. Never raises.

    `cfg_override`, when given, replaces the config used for every SETTING
    below -- `pm`, `tier`, `roles`, `tracker`, `knowledge`, `diagrams`,
    `endpoints` -- but never for `schema` or `isCrew`, both facts about the repo's own
    `.crew/config.json` that must not change depending on what is layered on
    top of it. Ignored entirely for a directory this function does not
    recognise as crew-managed: a plain git repo with no `.crew/` must not
    pick up crew-repo settings (a global `graph.out`, say) it never opted
    into, no matter what the caller passes.

    This module has no knowledge of where an override comes from. That is
    deliberate: `crew_config.layered_state` is what supplies one, built from
    `crew_config.resolve_config` (repo overrides global overrides built-in
    defaults) -- and `crew_config` already imports THIS module for
    `PM_DEFAULTS` and `SCHEMA_CURRENT`. If this function reached back into
    `crew_config` itself to build its own override, the two modules would
    import each other, which is a real cyclic import, not a stylistic one --
    pylint's `cyclic-import` check flags exactly this. Taking the override as
    a plain argument keeps the dependency one-directional.
    """
    raw_cfg = load_config(root)
    is_crew = bool(raw_cfg)
    cfg = cfg_override if (is_crew and cfg_override is not None) else raw_cfg
    pm = dict(PM_DEFAULTS)
    supplied = cfg.get("pm")
    if isinstance(supplied, dict):
        pm.update(supplied)

    # Coerce every numeric field once, here, so nothing downstream has to guess.
    # These come from a hand-edited JSON file: the types are whatever someone
    # typed, and an unguarded comparison against one is a TypeError that takes
    # out every session in the repo.
    for key, default in (("quietLines", 8), ("maxLines", 40),
                         ("maxDispatches", 3)):
        pm[key] = int_or(pm.get(key, default), default)
    # Normalised once, here, for the same reason as the numbers: every consumer
    # downstream then reads a value that is guaranteed to be one of AUTHORITIES,
    # and none of them has to re-decide what a typo means.
    pm["authority"] = normalise_authority(pm.get("authority"))

    tier = cfg.get("tier")
    roles = cfg.get("roles")

    state = {
        "isCrew": is_crew,
        # `schema` is a fact about the REPO FILE's own layout version, never
        # a setting to inherit -- resolve_config's built-in-defaults layer
        # always supplies the CURRENT schema number, so reading it from the
        # merged `cfg` would make an unmigrated v1 repo (no `schema` key at
        # all) read as current the moment any global config file exists.
        # Read from raw_cfg, exactly what /crew:upgrade itself reads.
        "schema": int_or(raw_cfg.get("schema", 1), 1) if raw_cfg else SCHEMA_CURRENT,
        "tier": tier if isinstance(tier, int) and not isinstance(tier, bool) else None,
        "roles": roles if isinstance(roles, list) else [],
        "tracker": cfg.get("tracker"),
        "pm": pm,
        "health": read_metrics(root),
        "work": read_work(root),
        "knowledge": read_knowledge(root, cfg),
        "diagrams": read_diagrams(root, cfg),
        # Gated on is_crew (nit 17): read_endpoints's OWN gate is
        # gizmoduck_installed, which also checks USER-GLOBAL settings and
        # therefore can answer True for a plain git repo with no .crew/ at
        # all. Calling it unconditionally meant every SessionStart in every
        # non-crew repo on a machine with gizmoduck enabled globally still
        # ran `git diff HEAD --unified=0` and buffered the whole diff, for a
        # finding that state["triggers"] below throws away anyway (isCrew is
        # False). A fresh empty dict per call, matching read_endpoints'
        # own inert shape, rather than a shared module-level constant --
        # `_empty_endpoint_doc`'s docstring names exactly why a reused dict
        # is the wrong economy here.
        "endpoints": read_endpoints(root, cfg) if is_crew
                    else {"installed": False, "unscanned": []},
        "incident": crew_incident.read_state(root, cfg),
    }
    # A directory with no crew has no findings. evaluate_triggers would
    # otherwise report graphStale for every plain git repo on the machine,
    # because _read_graph correctly finds no graph -- and /crew:pm and the
    # crew:pm agent call collect() directly, with no isCrew gate of their own.
    state["triggers"] = evaluate_triggers(state) if state["isCrew"] else []
    return state


def main(argv=None):
    """Print the state as JSON, record a dispatch, or manage the endpoint
    ledger. Exit code is always 0 for a bare invocation or a successful
    subcommand; a subcommand that could not do what it was asked returns
    non-zero (see each branch below) -- this module's never-raises contract
    covers not crashing the SessionStart hook, not masking a CLI misuse.

    Called with no arguments from `SessionStart` and from `/crew:upgrade`,
    which is why every flag is optional and a bare invocation still prints
    exactly what it always printed.
    """
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", default=None)
    parser.add_argument("--record-dispatch", metavar="KIND",
                        choices=DISPATCH_KINDS,
                        help="record which role/provider/model just ran")
    parser.add_argument("--role", default=None)
    parser.add_argument("--provider", default=None)
    parser.add_argument("--model", default=None)
    parser.add_argument("--branch", default=None,
                        help="branch the work was done on; defaults to the "
                             "checkout's current branch")
    parser.add_argument("--declare-endpoint", metavar="ENDPOINT", default=None,
                        help="record an AUTHORITATIVE endpoint ledger entry "
                             "(a ticket or dispatch stated it exists); "
                             "requires --location")
    parser.add_argument("--location", default=None,
                        help="path:line or ticket/dispatch reference, for "
                             "--declare-endpoint")
    parser.add_argument("--ticket", default=None,
                        help="ticket id, for --declare-endpoint (optional)")
    parser.add_argument("--endpoint-id", default=None,
                        help="re-declare an existing ledger record instead "
                             "of minting a new one, for --declare-endpoint")
    parser.add_argument("--scan-artifact-path", metavar="ID", default=None,
                        help="print the scan-artifact path for a declared "
                             "ledger record with this id -- gizmoduck's "
                             "--out convention reads this")
    parser.add_argument("--record-scan-artifact", metavar="ID", default=None,
                        help="freeze the current scan-artifact path onto a "
                             "ledger record, right after that scan lands")
    args = parser.parse_args(argv)

    root = args.root or os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
    if args.record_dispatch:
        if not args.role or not args.provider:
            # Loud, not silent. A dispatch recorded without a provider would
            # make author_family read `dispatch` and answer None, which is
            # worse than the honest config fallback it displaced.
            print("--record-dispatch needs --role and --provider",
                  file=sys.stderr)
            return 2
        record = record_dispatch(root, args.record_dispatch, args.role,
                                 args.provider, args.model, args.branch)
        print(json.dumps(record, indent=2, sort_keys=True))
        if record.get("unrecorded"):
            # Loud, and non-zero. The store could not take this dispatch, so
            # nothing later can prove who wrote the diff -- and the danger is
            # not the missing record on its own but the NEXT dispatch on this
            # branch, which will be reported as proven with this one absent.
            print(f"{args.provider} dispatch was NOT recorded: "
                  f"{os.path.join(*DISPATCH_DIR)} could not be written. "
                  "Provenance for this branch is now incomplete.",
                  file=sys.stderr)
            return 3
        return 0
    if args.declare_endpoint is not None:
        # `is not None`, not truthiness (nit 15): `--declare-endpoint ""`
        # is falsy, and a bare-truthiness check let it fall through to the
        # unconditional `print(json.dumps(collect(root), ...))` below --
        # printing full state and exiting 0 for a call that asked to
        # declare an endpoint and got silently ignored, the same way a
        # missing `--location` is not silently ignored.
        if not args.declare_endpoint:
            print("--declare-endpoint needs a non-empty value",
                  file=sys.stderr)
            return 2
        if not args.location:
            print("--declare-endpoint needs --location", file=sys.stderr)
            return 2
        record = declare_endpoint(root, args.declare_endpoint, args.location,
                                  ticket=args.ticket,
                                  endpoint_id=args.endpoint_id)
        print(json.dumps(record, indent=2, sort_keys=True))
        if record.get("error"):
            return 2
        return 0
    if args.scan_artifact_path:
        match = next((r for r in load_endpoints(root)
                     if r.get("id") == args.scan_artifact_path), None)
        if match is None:
            print(f"no ledger record with id {args.scan_artifact_path!r}",
                  file=sys.stderr)
            return 2
        path = scan_artifact_path(root, match)
        if path is None:
            print(f"record {args.scan_artifact_path!r} has an id that is "
                  "not safe to use in a path", file=sys.stderr)
            return 2
        print(path)
        return 0
    if args.record_scan_artifact:
        path = record_scan_artifact(root, args.record_scan_artifact)
        if path is None:
            print(f"no ledger record with id {args.record_scan_artifact!r}, "
                  "or its id is not safe to use in a path", file=sys.stderr)
            return 2
        print(path)
        return 0
    print(json.dumps(collect(root), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Reads crew state from a repository and evaluates the PM's attention triggers.

Standard library only, and every read fails soft. This module runs from a
SessionStart hook, so an exception here would break every session opened in the
repository -- an absent or malformed file must yield an absent value, never a
traceback.
"""

import json
import os
import re
import subprocess

import crew_incident

SCHEMA_CURRENT = 2

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
        if _DONE_RE.search(line):
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
            text=True, timeout=_GIT_TIMEOUT, check=False,
            stdin=subprocess.DEVNULL,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if done.returncode != 0:
        return None
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
    path = os.path.join(root, out, "graph.json")
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
    dirpath = os.path.join(root, _diagrams_dir(cfg))
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


def merge_defaults(defaults, supplied):
    """`defaults`, overlaid with anything already present. Recurses one level.

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
    """
    out = dict(defaults)
    if not isinstance(supplied, dict):
        return out
    for key, value in supplied.items():
        if isinstance(out.get(key), dict):
            if isinstance(value, dict):
                out[key] = merge_defaults(out[key], value)
            # else: keep the default; see the docstring.
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


def collect(root):
    """Full crew state for a repository. Never raises."""
    raw_cfg = load_config(root)
    is_crew = bool(raw_cfg)
    cfg = raw_cfg
    if is_crew:
        # Layer in a machine-global config, if any -- crew_config owns that
        # resolution (repo overrides global overrides built-in defaults).
        # Only for a repo that already has its own config: a global file
        # must never make a plain git repo with no .crew/ look crew-managed,
        # or apply crew-repo settings (a global graph.out, say) to one that
        # never opted in.
        #
        # Imported lazily rather than at module level to avoid a circular
        # import -- crew_config imports THIS module for PM_DEFAULTS and
        # SCHEMA_CURRENT -- and guarded because this module runs from a
        # SessionStart hook that must never raise: a broken global layer or
        # a broken import degrades to the repo file alone, never the session.
        try:
            import crew_config  # pylint: disable=import-outside-toplevel
            cfg = crew_config.resolve_config(root)
        except Exception:  # pylint: disable=broad-except
            cfg = raw_cfg
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
        "incident": crew_incident.read_state(root, cfg),
    }
    # A directory with no crew has no findings. evaluate_triggers would
    # otherwise report graphStale for every plain git repo on the machine,
    # because _read_graph correctly finds no graph -- and /crew:pm and the
    # crew:pm agent call collect() directly, with no isCrew gate of their own.
    state["triggers"] = evaluate_triggers(state) if state["isCrew"] else []
    return state


def main():
    """Print the state as JSON. Exit code is always 0."""
    root = os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
    print(json.dumps(collect(root), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

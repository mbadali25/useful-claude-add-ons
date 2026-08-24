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
    """Return the file's text, or None if it cannot be read for any reason."""
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as handle:
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

# Written by crew-graph at build time, holding the short HEAD sha the graph was
# built from. A sha, not a timestamp -- see _read_graph.
GRAPH_SHA_FILE = ".crew-graph-sha"

# Where the graph lives when config does not say. Defined here rather than in
# crew_upgrade because this module has to resolve it with no config at all.
GRAPH_OUT_DEFAULT = "graphify-out"

_GIT_TIMEOUT = 10


def git_out(root, *args):
    """Stripped stdout of a git command, or None on any failure.

    Failure includes git being absent and root not being a repository. Both
    are ordinary: the hook runs wherever the user opens a session.
    """
    try:
        done = subprocess.run(
            ("git",) + args, cwd=root, capture_output=True,
            text=True, timeout=_GIT_TIMEOUT, check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if done.returncode != 0:
        return None
    return done.stdout.strip()


def _read_graph(root, cfg):
    """Graph presence, and whether it was built at the current HEAD.

    Freshness is a recorded sha, never a timestamp. Comparing graph.json's
    mtime against HEAD's commit time looks reasonable and is wrong: `git pull`
    brings in commits authored earlier than the graph was built, so a graph
    that knows nothing about the pulled code reports itself current. That is
    the false-freshness failure this module exists to avoid.

    The sha comes from a sidecar that crew-graph writes at build time. No
    sidecar means the graph was built outside crew, so its provenance is
    unknown -- and unknown resolves to stale, which is the honest direction.
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

    built = (read_text(os.path.join(root, out, GRAPH_SHA_FILE)) or "").strip()
    head = git_out(root, "rev-parse", "--short=7", "HEAD")
    current = bool(built) and bool(head) and built[:7] == head[:7]
    return {"present": True, "current": current,
            "builtAt": built or None, "path": path}


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


# Priority order. pm_brief truncates from the bottom when it hits the line cap,
# so the most actionable finding has to sort first. upgradeNeeded leads because
# every other finding may be an artifact of a pre-upgrade layout.
TRIGGERS = (
    "upgradeNeeded",
    "handoffPending",
    "graphStale",
    "knowledgeBehind",
    "reviewNotWorking",
    "ticketsTooLarge",
)

PM_DEFAULTS = {
    "enabled": True,
    "mode": "adaptive",
    "quietLines": 8,
    "maxLines": 40,
    "authority": "report-only",
}


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

    # `schema` is normalised by collect(), but evaluate_triggers is also called
    # directly by tests and by the crew:pm agent, so it must not assume that.
    # .get(key, default) substitutes the default only when the KEY IS ABSENT --
    # a present `"schema": null` returns None, and `None < 2` is a TypeError
    # that would break every session opened in the repo.
    schema = int_or(state.get("schema", 1), 1)
    fired = {
        "upgradeNeeded": schema < SCHEMA_CURRENT,
        "handoffPending": bool(work.get("handoffPending")),
        # An absent graph is stale by definition -- there is nothing to trust.
        "graphStale": not graph.get("present") or not graph.get("current"),
        "knowledgeBehind": bool(knowledge.get("behind")),
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
    cfg = load_config(root)
    pm = dict(PM_DEFAULTS)
    supplied = cfg.get("pm")
    if isinstance(supplied, dict):
        pm.update(supplied)

    # Coerce every numeric field once, here, so nothing downstream has to guess.
    # These come from a hand-edited JSON file: the types are whatever someone
    # typed, and an unguarded comparison against one is a TypeError that takes
    # out every session in the repo.
    for key, default in (("quietLines", 8), ("maxLines", 40)):
        pm[key] = int_or(pm.get(key, default), default)

    tier = cfg.get("tier")
    roles = cfg.get("roles")

    state = {
        "isCrew": bool(cfg),
        # No `schema` key means a config written before schema tracking: v1.
        "schema": int_or(cfg.get("schema", 1), 1) if cfg else SCHEMA_CURRENT,
        "tier": tier if isinstance(tier, int) and not isinstance(tier, bool) else None,
        "roles": roles if isinstance(roles, list) else [],
        "tracker": cfg.get("tracker"),
        "pm": pm,
        "health": read_metrics(root),
        "work": read_work(root),
        "knowledge": read_knowledge(root, cfg),
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

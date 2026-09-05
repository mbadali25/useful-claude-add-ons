"""Reads crew state from a repository and evaluates the PM's attention triggers.

Standard library only, and every read fails soft. This module runs from a
SessionStart hook, so an exception here would break every session opened in the
repository -- an absent or malformed file must yield an absent value, never a
traceback.
"""

import argparse
import contextlib
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

# Serialises the read-modify-write above. `.work/`, beside the record itself.
DISPATCH_LOCK_PATH = (".work", "dispatch.lock")

# How long a lock may be held before the next writer takes it. A dispatch
# writes one small file, so anything still holding this after a minute is a
# process that died -- and a lock with no expiry is its own outage: one killed
# dispatch and every later one blocks forever on a holder that is gone.
# `verify-gate` applies the same rule to its own lock for the same reason.
DISPATCH_LOCK_TTL = 60.0


@contextlib.contextmanager
def _dispatch_lock(root):
    """Hold the dispatch lock, or proceed unlocked rather than lose the write.

    `O_CREAT|O_EXCL` is the atomic primitive -- the same one `hook_once.py`
    uses -- so exactly one writer creates the file and the rest wait.

    Two deliberate softnesses, both of which trade a rare wrong answer for a
    common one:

      * A lock older than `DISPATCH_LOCK_TTL` is reclaimed. A killed dispatch
        would otherwise wedge every later one permanently.
      * Failing to acquire it at all does NOT raise. A dispatch that cannot be
        recorded is a review with no record, which falls back to reading the
        config -- the guess this whole module exists to avoid. Recording it
        with a small chance of a lost concurrent update is strictly better
        than not recording it.
    """
    path = os.path.join(root, *DISPATCH_LOCK_PATH)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    held = False
    deadline = time.time() + 5.0
    while time.time() < deadline:
        try:
            handle = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            try:
                age = time.time() - os.path.getmtime(path)
            except OSError:
                age = 0.0
            if age > DISPATCH_LOCK_TTL:
                try:
                    os.remove(path)
                except OSError:
                    pass
                continue
            time.sleep(0.02)
            continue
        except OSError:
            break               # unwritable .work/; the write below will say so
        os.close(handle)
        held = True
        break
    try:
        yield held
    finally:
        if held:
            try:
                os.remove(path)
            except OSError:
                pass


def read_dispatch(root):
    """The last recorded dispatch, or `{}`. Never raises."""
    text = read_text(os.path.join(root, *DISPATCH_PATH))
    if text is None:
        return {}
    try:
        parsed = json.loads(text)
    except ValueError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


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
             "branch": branch}
    with _dispatch_lock(root):
        return _write_dispatch(root, kind, entry)


def _write_dispatch(root, kind, entry):
    """The read-modify-write itself. Call it holding `_dispatch_lock`.

    Separated so the lock has one obvious scope: the read AND the write are
    inside it. Writing the file atomically stops a torn read and does nothing
    at all about two dispatches both reading the same history and each
    publishing it plus itself -- whichever lands second erases the other, and
    if the erased one wrote the diff its family is never struck. The PM
    dispatches up to three roles at a time, so that is the ordinary case.
    """
    record = dict(read_dispatch(root))
    record[kind] = entry

    # ...and keep the earlier ones. A single slot meant a LATER dispatch
    # erased the family that actually wrote the diff: codex implements, a
    # claude dispatch runs afterwards on the same branch for something else,
    # and review then reads a matching branch, calls claude the author, and
    # clears CODEX to review codex's own work. Nothing binds a dispatch to
    # the commits it produced, so any family dispatched on this branch may
    # have written what is under review, and all of them are struck.
    # Newest FIRST, and the stored list is already in that order -- so the new
    # entry goes on the front. Appending it to the end instead (which this did
    # until the sabotage suite caught it) reverses a newest-first list on every
    # write: `reversed()` then promotes the oldest records and evicts
    # middle-aged ones, so which family survives the bound became a function of
    # how many dispatches had happened rather than of when they happened.
    history = [entry] + [h for h in record.get(f"{kind}History") or []
                         if isinstance(h, dict)]
    # Newest first, deduplicated on what the guard actually reads, and
    # bounded: this file is rewritten on every dispatch and nothing prunes it.
    #
    # The key is the FAMILY, not the model id, because the family is the only
    # thing `author_families` ever compares. Keyed on the model, one provider
    # walking through ten ids on one branch filled the whole history and
    # evicted the family that wrote the diff -- ten entries carrying one bit
    # between them. An UNKNOWN family (an unpinned copilot) keeps the provider
    # and model in its key instead: None must not compare equal to None here,
    # or two genuinely different unpinned providers collapse into one and the
    # second is dropped as a duplicate of the first.
    seen, trimmed = set(), []
    for item in history:
        fam = family(item.get("provider"), item.get("model"))
        key = ((fam, item.get("branch")) if fam is not None
               else (None, item.get("provider"), item.get("model"),
                     item.get("branch")))
        if key in seen:
            continue
        seen.add(key)
        trimmed.append(item)
        if len(trimmed) >= DISPATCH_HISTORY_MAX:
            break
    record[f"{kind}History"] = trimmed

    path = os.path.join(root, *DISPATCH_PATH)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    # Atomic, for the same reason the config writes are: opening the live
    # file "w" truncates it before the JSON is complete, and `read_dispatch`
    # collapses malformed JSON to `{}`. A concurrent reader therefore saw NO
    # dispatch and fell back to reading the config -- which describes the
    # next run, not the one being reviewed. The guard failing open during an
    # ordinary race is the worst version of this bug, because nothing about
    # it looks like a failure.
    # PID *and* a random token. The PID alone is not unique to a WRITER: two
    # threads in one interpreter share it, collide on this name, and
    # `os.replace` then fails on Windows because the sibling still holds the
    # file open. Found by running the concurrency test rather than by reading
    # it.
    tmp_path = f"{path}.{os.getpid()}.{uuid.uuid4().hex[:8]}.tmp"
    try:
        with open(tmp_path, "w", encoding="utf-8") as handle:
            json.dump(record, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, path)
    except BaseException:
        try:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        except OSError:
            pass
        raise
    return record


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
        return frozenset(recorded_families) - {None}, "dispatch"
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
    return frozenset(f for f in (decided["family"],) if f), "config"


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


def collect(root, cfg_override=None):
    """Full crew state for a repository. Never raises.

    `cfg_override`, when given, replaces the config used for every SETTING
    below -- `pm`, `tier`, `roles`, `tracker`, `knowledge`, `diagrams` -- but
    never for `schema` or `isCrew`, both facts about the repo's own
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
        "incident": crew_incident.read_state(root, cfg),
    }
    # A directory with no crew has no findings. evaluate_triggers would
    # otherwise report graphStale for every plain git repo on the machine,
    # because _read_graph correctly finds no graph -- and /crew:pm and the
    # crew:pm agent call collect() directly, with no isCrew gate of their own.
    state["triggers"] = evaluate_triggers(state) if state["isCrew"] else []
    return state


def main(argv=None):
    """Print the state as JSON, or record a dispatch. Exit code is always 0.

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
        return 0
    print(json.dumps(collect(root), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

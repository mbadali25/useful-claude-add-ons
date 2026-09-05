#!/usr/bin/env python3
"""What plugin set a vault should be running, and the evidence for saying so.

A vault is one of two things, and the difference decides everything else:

* **AUTHORED** - a person opens it, reads it, and edits it by hand. Rendering
  matters, so Dataview queries, Templater templates, Kanban boards and
  Breadcrumbs edges are all load-bearing, and a full-text index is worth
  building because a human types queries into it.
* **GENERATED** - nothing but Claude ever reads it, through the REST bridge or
  a plain `Grep`. A code-graph export is the type case. Every index-building
  plugin there costs disk, RAM and startup time to produce an index that no
  reader ever queries.

Installing and stripping are the same decision seen from two sides: "what does
this vault lack" and "what is this vault carrying that nothing here reads" are
answered from one list or they drift, and a drifted pair is how a vault ends up
being told to install the very plugin the other half of the tool told it to
remove. So there is exactly one definition of each profile in this module, and
both `vault_ops.py profile` and `vault_ops.py install-plugin` read it.

Three things this module deliberately does not do:

* **It never reads a "kind" flag out of config as the primary answer.** A
  hand-set flag is wrong the moment the vault changes and nobody notices; the
  verdict is derived from what is on disk. A configured override exists
  (`vaults.<name>.profile`), and it wins when set, but it is an override of a
  verdict that would have been reached anyway - `detect()` reports the derived
  kind alongside it so the two can be seen to disagree.
* **It never returns a verdict without its evidence.** Every classification
  carries the signals that produced it, in the order they were weighed, because
  the action it leads to writes into somebody's vault. "It is a graph vault"
  is not reviewable; "it declares layout org/repo, runs the code-graph plugin,
  and 0 of 40 sampled notes carry the memory contract's frontmatter" is.
* **It never enables or disables anything.** This module computes; vault_ops.py
  prints and, only under `--apply` and only for plugins named one at a time,
  writes.

The plugin IDs below are the real IDs read off this machine's own vaults from
their `.obsidian/community-plugins.json`, not the human names ("templater" is
`templater-obsidian`, "excalidraw" is `obsidian-excalidraw-plugin`, "git" is
`obsidian-git`). A guessed ID is not a typo that anything catches: Obsidian
ignores an unknown entry silently, so the plugin simply never turns on and the
tool reports success.
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import obsidian_common  # noqa: E402  pylint: disable=wrong-import-position
import vault_guard  # noqa: E402  pylint: disable=wrong-import-position

BRIDGE_PLUGIN_ID = "obsidian-local-rest-api"
CODE_GRAPH_PLUGIN_ID = "code-graph"

# The six frontmatter keys the memory contract requires. Taken from the guard
# rather than restated, so a vault whose contract this plugin enforces is the
# same contract detection looks for.
MEMORY_CONTRACT_KEYS = tuple(vault_guard.DEFAULT_SIX_KEYS)

# The note count past which a full-text index stops paying for itself. Not a
# number invented here: README.md, bridge_status.py and the
# obsidian-memory-contract skill all already say "past roughly 50,000 notes,
# prefer plain filesystem Read/Grep", and Omnisearch's index is precisely what
# gets slow there. Below it, an authored vault gets Omnisearch and
# text-extractor; at or above it, it does not.
OMNISEARCH_THRESHOLD = 50000

PROFILE_KINDS = ("bridge", "graph", "authored")

# --- The three profiles ------------------------------------------------------
#
# BRIDGE is the floor and is contained in both of the others. A vault without
# it is not a slow vault or a misconfigured one - it is invisible. Two vaults
# on the reference machine (claude-anew-thd-codegraph, 26,146 notes, and
# claude-anew-theselectsource, 18,402 notes) are in exactly that state: no
# community plugins at all, so nothing Claude can reach.
#
# GRAPH is copied from what claude-anew-codegraph actually runs (22,027 notes,
# exactly these two IDs enabled), not composed from what a graph vault sounds
# like it should want. What is deliberately ABSENT is the point of the profile:
# no omnisearch, no dataview, no text-extractor, no backlink indexing. Those
# build an index, and in a vault only Claude greps, nothing ever reads the
# index they build.
#
# AUTHORED is what claude-memories runs. The split between the always-on core
# and the two search plugins is the 50k rule above.

BRIDGE_PLUGINS = (BRIDGE_PLUGIN_ID,)

GRAPH_PLUGINS = (BRIDGE_PLUGIN_ID, CODE_GRAPH_PLUGIN_ID)

AUTHORED_CORE_PLUGINS = (
    BRIDGE_PLUGIN_ID,
    "dataview",
    "templater-obsidian",
    "periodic-notes",
    "obsidian-kanban",
    "obsidian-excalidraw-plugin",
    "breadcrumbs",
    "obsidian-linter",
    "metadata-menu",
    "obsidian-charts",
    "obsidian-git",
    "obsidian-advanced-uri",
    "auto-note-mover",
)

# Only below OMNISEARCH_THRESHOLD notes.
AUTHORED_SEARCH_PLUGINS = ("omnisearch", "text-extractor")

PLUGIN_PURPOSE = {
    BRIDGE_PLUGIN_ID: "the bridge itself - without it Claude cannot see this vault at all",
    CODE_GRAPH_PLUGIN_ID: "renders the graphify export's node/edge notes as a navigable graph",
    "dataview": "renders inline queries; a note that uses one shows an error block without it",
    "templater-obsidian": "runs the vault's note templates",
    "periodic-notes": "daily/weekly note creation and navigation",
    "obsidian-kanban": "board notes render as plain JSON without it",
    "obsidian-excalidraw-plugin": "drawing notes render as unreadable JSON without it",
    "breadcrumbs": "hierarchy edges between notes; views that use them go blank",
    "obsidian-linter": "formats notes on save to the vault's own conventions",
    "metadata-menu": "frontmatter field types, commonly called from Templater templates",
    "obsidian-charts": "chart code blocks render as raw text without it",
    "obsidian-git": "commits the vault on a schedule; disabling it stops backups silently",
    "obsidian-advanced-uri": "obsidian:// links from outside the app stop resolving",
    "auto-note-mover": "files new notes into folders by rule",
    "omnisearch": "full-text search; its index is the single largest cost on a big vault",
    "text-extractor": "OCR/PDF text for Omnisearch; pointless without a reader who searches",
}


def profile_plugins(kind, note_count=None):
    """The plugin IDs a vault of this kind should have enabled, bridge first.

    `note_count` only matters for the authored profile, where it decides
    whether the two index-building search plugins are included. Passing None
    for an authored vault means "count unknown": the search plugins are
    included, because the vault under discussion is far more often a small one
    and proposing an install is reversible, whereas proposing the removal of a
    plugin somebody's notes render through is not.
    """
    if kind == "bridge":
        return list(BRIDGE_PLUGINS)
    if kind == "graph":
        return list(GRAPH_PLUGINS)
    if kind == "authored":
        out = list(AUTHORED_CORE_PLUGINS)
        if note_count is None or note_count < OMNISEARCH_THRESHOLD:
            out.extend(AUTHORED_SEARCH_PLUGINS)
        return out
    raise ValueError(f"unknown profile kind {kind!r} (known: {', '.join(PROFILE_KINDS)})")


def threshold_note(kind, note_count):
    """One line explaining what the 50k rule did to this profile, or ''."""
    if kind != "authored":
        return ""
    names = ", ".join(AUTHORED_SEARCH_PLUGINS)
    if note_count is None:
        return (f"Note count unknown, so {names} are included by default - re-run once the "
                "count is known before proposing their removal.")
    if note_count < OMNISEARCH_THRESHOLD:
        return (f"{note_count:,} notes is under the ~{OMNISEARCH_THRESHOLD:,} mark this "
                f"plugin's docs already name, so {names} are in the set.")
    return (f"{note_count:,} notes is at or over the ~{OMNISEARCH_THRESHOLD:,} mark this "
            f"plugin's docs already name, so {names} are NOT in the set - their index is "
            "what gets slow at this size, and filesystem Read/Grep is the better tool here.")


# --- Reading a vault ---------------------------------------------------------

def enabled_plugins(vault_path):
    """(path to community-plugins.json, [ids] or None).

    None means the file is missing or is not a JSON list - which is NOT the
    same as `[]`. `[]` is "community plugins are on and nothing is enabled";
    missing is usually "this vault has never had Restricted Mode turned off",
    and only the second of those is something a human has to click through in
    Obsidian's own UI. Collapsing them sends the wrong instruction.
    """
    path = obsidian_common.community_plugins_path(vault_path)
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return path, None
    if not isinstance(data, list):
        return path, None
    return path, [p for p in data if isinstance(p, str)]


def _walk_notes(vault_path, limit=None):
    """Every `.md` path under the vault, dot-directories skipped.

    `.obsidian` in particular holds plugin caches that can contain Markdown,
    and counting those would inflate the number the 50k threshold is compared
    against.
    """
    count = 0
    for root, dirs, files in os.walk(vault_path):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        for name in files:
            if name.endswith(".md"):
                yield os.path.join(root, name)
                count += 1
                if limit is not None and count >= limit:
                    return


def count_notes(vault_path, limit=None):
    """(count, capped). `capped` is True when `limit` stopped the walk early.

    A code-graph vault runs to hundreds of thousands of notes and this walk is
    the most expensive thing in the module, so the count is taken once per
    command and passed around rather than recomputed.
    """
    count = 0
    for _ in _walk_notes(vault_path, limit):
        count += 1
    return count, limit is not None and count >= limit


FRONTMATTER_SAMPLE = 40


def frontmatter_signal(vault_path, sample=FRONTMATTER_SAMPLE):
    """How many of a sample of notes carry the memory contract's frontmatter.

    A sample, not a census: the answer this feeds is "is a human maintaining a
    contract here", and that is as visible in 40 notes as in 400,000. Notes are
    taken in walk order, which on a code-graph vault means the first repo's
    nodes - fine, since those are exactly the notes that would carry the
    contract if it were being applied.
    """
    checked = 0
    matched = 0
    for path in _walk_notes(vault_path, limit=sample):
        checked += 1
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as fh:
                head = fh.read(1200)
        except OSError:
            continue
        if not head.lstrip().startswith("---"):
            continue
        block = head.lstrip()[3:].split("\n---", 1)[0]
        keys = {line.split(":", 1)[0].strip()
                for line in block.splitlines() if ":" in line}
        if all(k in keys for k in MEMORY_CONTRACT_KEYS):
            matched += 1
    ratio = (matched / float(checked)) if checked else 0.0
    return {"checked": checked, "matched": matched, "ratio": ratio}


# A note carrying the contract in a fifth of a sample is a human's vault; a
# generated one carries it in none. The gap between those two is enormous, so
# the exact cut only has to sit somewhere inside it.
FRONTMATTER_AUTHORED_RATIO = 0.2

GRAPHIFY_MANIFESTS = (
    os.path.join("graphify-out", "graph.json"),
    os.path.join(".graphify", "manifest.json"),
    "graph.json",
)


def graphify_manifest(vault_path):
    """The graphify manifest inside the vault, or None.

    Only these exact locations, at the vault root. A recursive search for any
    `graph.json` would match a note attachment, a plugin cache, or an exported
    node in somebody's authored vault, and a false positive here reclassifies a
    human's vault as generated - which is the direction that proposes stripping
    twelve plugins out of it.
    """
    for rel in GRAPHIFY_MANIFESTS:
        candidate = os.path.join(vault_path, rel)
        if os.path.isfile(candidate):
            return candidate
    return None


# A vault laid out `<org>/<repo>/` is what `graphify export obsidian --dir
# <vault>/<org>/<repo>` produces. This is the SHALLOW probe: it asks only
# whether the shape is there, and stops two levels down. vault_ops.py's
# scan_graph_layout() is the deep one - it walks every note in every repo to
# count and date them, which is right for `graph-health` on demand and wrong
# for a detector that has to run on a 400,000-note vault before it says
# anything at all.

def graph_layout_signal(vault_path):
    """{"repos": n, "orgs": [...], "detail": str} - the <org>/<repo> shape."""
    orgs = []
    repos = 0
    try:
        top = sorted(os.listdir(vault_path))
    except OSError as e:
        return {"repos": 0, "orgs": [], "detail": f"cannot read {vault_path}: {e}"}
    for org in top:
        if org.startswith("."):
            continue
        org_path = os.path.join(vault_path, org)
        if not os.path.isdir(org_path):
            continue
        try:
            children = [c for c in sorted(os.listdir(org_path)) if not c.startswith(".")]
        except OSError:
            continue
        subdirs = [c for c in children if os.path.isdir(os.path.join(org_path, c))]
        if not subdirs or any(c.endswith(".md") for c in children):
            # Notes sitting directly under the top-level folder is the shape of
            # a hand-made section (wiki/, inbox/), not of an export.
            continue
        found = [r for r in subdirs
                 if _holds_notes(os.path.join(org_path, r))]
        if found:
            orgs.append(org)
            repos += len(found)
    if not repos:
        return {"repos": 0, "orgs": [], "detail": "no <org>/<repo> folder pairs at the root"}
    return {"repos": repos, "orgs": orgs,
            "detail": f"{repos} <org>/<repo> folder pair(s) under {', '.join(orgs)}"}


def _holds_notes(path, depth=2):
    """Is there a .md anywhere in the first `depth` levels under `path`?"""
    try:
        entries = sorted(os.listdir(path))
    except OSError:
        return False
    for name in entries:
        if name.endswith(".md"):
            return True
    if depth <= 1:
        return False
    for name in entries:
        child = os.path.join(path, name)
        if not name.startswith(".") and os.path.isdir(child) and _holds_notes(child, depth - 1):
            return True
    return False


# --- Evidence and verdict ----------------------------------------------------

def gather_evidence(vault_path, layout=None, note_count=None):
    """Everything detection is allowed to look at, gathered once.

    `layout` is the vault's configured `layout` string from
    ~/.claude/obsidian/config.json - "org/repo" there is a declaration by the
    user that this is a code-graph vault, and it is the cheapest and most
    reliable signal there is.
    """
    _, enabled = enabled_plugins(vault_path)
    if note_count is None:
        note_count, _capped = count_notes(vault_path)
    return {
        "path": vault_path,
        "notes": note_count,
        "layout": layout,
        "plugins": enabled,
        "plugin_count": 0 if not enabled else len(enabled),
        "has_code_graph": bool(enabled) and CODE_GRAPH_PLUGIN_ID in enabled,
        "has_bridge": bool(enabled) and BRIDGE_PLUGIN_ID in enabled,
        "manifest": graphify_manifest(vault_path),
        "graph_layout": graph_layout_signal(vault_path),
        "frontmatter": frontmatter_signal(vault_path),
    }


# Enough of the authored set to say a person curated this vault. Three is
# chosen so that a graph vault which happens to have picked up one extra
# plugin does not flip: claude-anew-codegraph runs smart-connections alongside
# its two, and one stray plugin must not reclassify it.
AUTHORED_PLUGIN_SIGNAL = 3

# Below this, an <org>/<repo> shape is not evidence of anything - a handful of
# folders two deep is what any vault looks like. The generated vaults on the
# reference machine hold 18,402 and 26,146 notes.
GRAPH_STRUCTURE_MIN_NOTES = 1000


def classify(evidence):
    """{"kind", "reasons": [...], "confident": bool} from gathered evidence.

    Pure: it touches no disk, so the whole decision table is testable against
    the measured numbers without building a 400,000-note fixture.

    The order below is the whole design. Declarations first (a `layout` in
    config, the code-graph plugin, a graphify manifest), because those are
    somebody stating the answer rather than the tool inferring it. Authored
    signals second, because a human's vault laid out `wiki/concepts/` looks
    structurally identical to `<org>/<repo>` from the outside and must not be
    reclassified by shape alone. Structural graph evidence third, and only in
    the absence of any authored signal. Anything left over is `bridge`.
    """
    reasons = []
    authored_extras = [p for p in (evidence["plugins"] or [])
                       if p in AUTHORED_CORE_PLUGINS + AUTHORED_SEARCH_PLUGINS
                       and p != BRIDGE_PLUGIN_ID]
    fm = evidence["frontmatter"]

    if evidence.get("layout") == "org/repo":
        reasons.append("config declares \"layout\": \"org/repo\" for this vault")
    if evidence["has_code_graph"]:
        reasons.append(f"the {CODE_GRAPH_PLUGIN_ID} plugin is enabled")
    if evidence["manifest"]:
        reasons.append(f"a graphify manifest is present at {evidence['manifest']}")
    if reasons:
        return {"kind": "graph", "reasons": reasons, "confident": True}

    if fm["checked"] and fm["ratio"] >= FRONTMATTER_AUTHORED_RATIO:
        reasons.append(f"{fm['matched']} of {fm['checked']} sampled notes carry the memory "
                       "contract's frontmatter (" + ", ".join(MEMORY_CONTRACT_KEYS) + ")")
    if len(authored_extras) >= AUTHORED_PLUGIN_SIGNAL:
        reasons.append(f"{len(authored_extras)} authored-set plugins are already enabled: "
                       + ", ".join(sorted(authored_extras)))
    if reasons:
        return {"kind": "authored", "reasons": reasons, "confident": True}

    layout = evidence["graph_layout"]
    if layout["repos"] and evidence["notes"] >= GRAPH_STRUCTURE_MIN_NOTES:
        # Report the counts, never assert zero. Reaching here only means both
        # signals fell UNDER their thresholds, and under is not none: a vault
        # with one authored plugin and a low frontmatter ratio was being told
        # nothing authored was enabled, after which `optimize` could propose
        # disabling the dataview that renders its notes.
        if fm["checked"]:
            fm_detail = (f"{fm['matched']} of {fm['checked']} sampled notes carry the "
                         f"memory contract's frontmatter, under the "
                         f"{FRONTMATTER_AUTHORED_RATIO:.0%} an authored vault shows")
        else:
            fm_detail = "no notes could be sampled for the memory contract's frontmatter"
        if authored_extras:
            plugin_detail = (f"{len(authored_extras)} authored-set plugin(s) enabled ("
                             + ", ".join(sorted(authored_extras)) +
                             f"), under the {AUTHORED_PLUGIN_SIGNAL} that would signal an "
                             "authored vault - check before disabling any of them")
        else:
            plugin_detail = "no plugin from the authored set is enabled"
        return {"kind": "graph", "confident": not authored_extras, "reasons": [
            layout["detail"] + f", holding {evidence['notes']:,} notes",
            fm_detail,
            plugin_detail,
        ]}

    return {"kind": "bridge", "confident": False, "reasons": [
        f"{evidence['notes']:,} notes, {evidence['plugin_count']} community plugin(s), "
        f"{fm['matched']} of {fm['checked']} sampled notes carrying the memory contract",
        "no declaration (no layout, no " + CODE_GRAPH_PLUGIN_ID + ", no graphify manifest) "
        "and no authored signal either",
        "falling back to the bridge floor rather than guessing: bridge is contained in both "
        "of the other profiles, so nothing proposed from it can be wrong in a way that has "
        "to be undone. Name the kind with --profile/--set if you know it.",
    ]}


# --- The configured override -------------------------------------------------

def configured_profile(vault_name):
    """`vaults.<name>.profile` from config, or None. Never guessed at."""
    if not vault_name:
        return None
    cfg = obsidian_common.read_config()
    raw = cfg.get("vaults")
    if not isinstance(raw, dict):
        return None
    entry = raw.get(vault_name)
    if not isinstance(entry, dict):
        return None
    kind = entry.get("profile")
    return kind if kind in PROFILE_KINDS else None


def plan_set_profile(vault_name, kind):
    """(config path, before, after) for writing an override. Writes nothing.

    `kind` of None clears the override and hands the vault back to detection.
    """
    cfg = obsidian_common.read_config()
    raw = cfg.get("vaults")
    if not isinstance(raw, dict) or vault_name not in raw:
        return obsidian_common.config_path(), None, None
    before = raw[vault_name].get("profile")
    after = kind
    return obsidian_common.config_path(), before, after


def apply_set_profile(vault_name, kind):
    """Write `vaults.<name>.profile`. Callers gate this behind --apply."""
    cfg = obsidian_common.read_config()
    raw = cfg.get("vaults")
    if not isinstance(raw, dict) or vault_name not in raw:
        raise ValueError(f"{vault_name} has no entry in {obsidian_common.config_path()} - "
                         "run /obsidian-vault:init to give it one first")
    if kind is None:
        raw[vault_name].pop("profile", None)
    else:
        raw[vault_name]["profile"] = kind
    obsidian_common.write_config(cfg)
    return obsidian_common.config_path()


def detect(vault_path, vault_name=None, layout=None, override=None, note_count=None):
    """The full verdict: derived kind, evidence, and whatever overrode it.

    The derived kind is reported even when an override wins, so the two can be
    seen to disagree. A stale override that nobody can see is the failure this
    whole module is written to avoid.
    """
    evidence = gather_evidence(vault_path, layout=layout, note_count=note_count)
    derived = classify(evidence)
    configured = configured_profile(vault_name)
    source = "detected"
    kind = derived["kind"]
    if override in PROFILE_KINDS:
        kind, source = override, "--profile on the command line"
    elif configured in PROFILE_KINDS:
        kind, source = configured, f"vaults.{vault_name}.profile in config"
    return {
        "vault": vault_name,
        "path": vault_path,
        "kind": kind,
        "source": source,
        "detected_kind": derived["kind"],
        "confident": derived["confident"],
        "reasons": derived["reasons"],
        "evidence": evidence,
    }


def compare(kind, note_count, enabled):
    """{"wanted", "missing", "unwanted"} - the install and strip sides at once.

    `enabled` of None (no readable community-plugins.json) yields the whole
    profile as missing and nothing as unwanted: a file that could not be read
    is not evidence that a plugin is absent, and proposing a removal from it
    would be proposing a removal from a list nobody has seen.
    """
    wanted = profile_plugins(kind, note_count)
    if enabled is None:
        return {"wanted": wanted, "missing": list(wanted), "unwanted": [], "known": False}
    return {
        "wanted": wanted,
        "missing": [p for p in wanted if p not in enabled],
        "unwanted": [p for p in enabled if p not in wanted],
        "known": True,
    }


# --- Splitting a vault: the last resort --------------------------------------
#
# The pressure to split comes from size, but size is not the limit - the
# index-building plugins are. Turning Omnisearch and text-extractor off buys
# more than a split does and costs nothing permanent, while a split breaks
# every wikilink that crossed the seam, forever, and Obsidian gives no warning
# when it happens: the link simply renders as an unresolved one.
#
# So a split is only ever a recommendation here, the seam is PROVENANCE
# (generated notes on one side, authored on the other) rather than size, and
# the recommendation is not made without the count of links it would break.

WIKILINK_RE = re.compile(r"!?\[\[([^\]|#^]+)")


def _link_target(raw):
    """The basename a wikilink resolves to, lowercased, extension stripped.

    A simplification, stated rather than hidden: Obsidian resolves a bare
    `[[name]]` by shortest unique path, which needs the whole vault index to
    reproduce exactly. Matching on basename over-counts (two `index.md` in
    different folders look like the same target) and never under-counts, so the
    number this produces is an upper bound on the damage - which is the safe
    direction for a figure that exists to talk somebody out of a split.
    """
    target = raw.strip().replace("\\", "/").rstrip("/")
    target = target.rsplit("/", 1)[-1]
    if target.lower().endswith(".md"):
        target = target[:-3]
    return target.lower()


def split_seam(vault_path, min_notes=0):
    """The generated/authored seam as top-level folder names.

    Generated side: the `<org>` folders the shallow layout probe found, which
    are the ones a graphify export writes into. Everything else at the root is
    authored until shown otherwise - erring towards "a human made this" is the
    direction that keeps a file from being moved.

    `min_notes` drops an `<org>` holding fewer notes than that. The shape alone
    is not enough: an authored vault's `Boards/<board>/note.md` is structurally
    identical to a one-repo export, and calling a human's folder "generated" is
    how a tool talks somebody into moving files that were never generated.
    """
    generated = {org for org in graph_layout_signal(vault_path)["orgs"]
                 if min_notes <= 0 or count_notes(os.path.join(vault_path, org),
                                                  limit=min_notes)[1]}
    authored = set()
    try:
        for name in os.listdir(vault_path):
            if name.startswith(".") or name in generated:
                continue
            authored.add(name)
    except OSError:
        pass
    return {"generated": sorted(generated), "authored": sorted(authored)}


def split_analysis(vault_path, seam=None, min_notes=GRAPH_STRUCTURE_MIN_NOTES):
    """How many wikilinks a provenance split would break. Walks every note.

    Deliberately not run by `profile` unless it is asked for: on a 400,000-note
    vault this reads every file, and a detector that takes minutes is one
    nobody runs.

    `min_notes` defaults to the same figure split_recommendation() uses, and
    that is load-bearing rather than tidy: the command that NAMES a seam and
    the command that counts the damage on it have to pick the same folders, or
    the number reported alongside an irreversible operation is a number for a
    different operation.
    """
    seam = seam or split_seam(vault_path, min_notes=min_notes)
    generated = set(seam["generated"])
    if not generated:
        return {"seam": seam, "crossing": 0, "links": 0, "notes": 0,
                "detail": "no generated <org>/<repo> folders, so there is no provenance seam "
                          "to split on - size alone is not one"}
    side_of = {}
    notes = []
    for path in _walk_notes(vault_path):
        rel = os.path.relpath(path, vault_path).replace("\\", "/")
        top = rel.split("/", 1)[0] if "/" in rel else ""
        side = "generated" if top in generated else "authored"
        notes.append((path, side))
        base = os.path.basename(path)
        side_of.setdefault(base[:-3].lower() if base.endswith(".md") else base.lower(),
                           set()).add(side)

    crossing = 0
    links = 0
    for path, side in notes:
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as fh:
                text = fh.read()
        except OSError:
            continue
        for match in WIKILINK_RE.finditer(text):
            target = _link_target(match.group(1))
            if not target:
                continue
            links += 1
            sides = side_of.get(target)
            if sides and sides != {side}:
                crossing += 1
    return {
        "seam": seam, "crossing": crossing, "links": links, "notes": len(notes),
        "detail": (f"{crossing:,} of {links:,} wikilinks in {len(notes):,} notes resolve "
                   f"across the seam and would break permanently. Generated side: "
                   f"{', '.join(seam['generated'])}. Authored side: "
                   f"{', '.join(seam['authored']) or '(nothing)'}."),
    }


def split_recommendation(kind, evidence, comparison):
    """Whether to even discuss a split, and what to do instead. Never moves a file.

    Below the threshold there is no size pressure, so the question does not
    arise and this says nothing further. Raising a seam on a 1,400-note vault
    is not caution, it is a proposal to break links for no reason.
    """
    if evidence["notes"] < OMNISEARCH_THRESHOLD:
        return [f"{evidence['notes']:,} notes is nowhere near the ~{OMNISEARCH_THRESHOLD:,} "
                "mark where size becomes the problem, so a split is not on the table here "
                "and no seam is proposed."]
    index_plugins = [p for p in (evidence["plugins"] or []) if p in AUTHORED_SEARCH_PLUGINS]
    lines = []
    if index_plugins:
        lines.append(
            f"{evidence['notes']:,} notes with {', '.join(index_plugins)} still enabled. The "
            "limit here is the index, not the note count: turning those off is reversible, "
            "buys more than a split does, and breaks no links. Confirm each one separately "
            "before disabling it - a Dataview query or a Templater template can be relying "
            "on it.")
    elif comparison["unwanted"]:
        lines.append(
            f"{evidence['notes']:,} notes carrying {len(comparison['unwanted'])} plugin(s) "
            f"the {kind} profile does not want. Work through those one at a time before "
            "any structural change is considered.")
    seam = split_seam(evidence["path"], min_notes=GRAPH_STRUCTURE_MIN_NOTES)
    if seam["generated"] and seam["authored"]:
        lines.append(
            "If a split is still warranted after that, the seam is PROVENANCE, not size: "
            f"generated {', '.join(seam['generated'])} on one side, authored "
            f"{', '.join(seam['authored'])} on the other. Get the breakage count first with "
            "`profile --vault <name> --split-analysis`; every wikilink crossing that seam "
            "breaks permanently and Obsidian will not warn you. Nothing here moves a file.")
    else:
        lines.append(
            "There is no provenance seam in this vault (its notes are all one side or the "
            "other), so a split would have to be made on size - which is the cut this tool "
            "will not recommend, because it breaks links to buy nothing the plugin set "
            "cannot buy more cheaply.")
    return lines

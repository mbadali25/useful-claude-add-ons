"""Brings an out-of-date crew setup up to the current schema.

Not "v1 -> v2", whatever this file used to say. That docstring was written for
one migration, never extended when 0.14.4 added the `qa`/`dev` provider table
or when 0.15.x added three roles, and was exactly what let `upgrade_config`
migrate two blocks while claiming to have migrated all of them. Every block a
release adds belongs in `CONFIG_BLOCKS`, and the docstring belongs with it.

Order matters and is not negotiable: back up, then upgrade config, then
reconcile, then report. The backup exists so that every later step can be
non-destructive in practice as well as in intent.

Rules this module exists to enforce:

  * A codemap `anchor:` is bumped only on a file this run actually re-verified.
    A false freshness claim is worse than an honest stale one, because the
    entire freshness rule depends on the anchor being true.
  * A conflict between the map and the graph is written to the report, never
    applied to the map.
  * `schema` is stamped current only when every block actually migrated and
    no dropped key holds a value nobody accepted losing, and the run says
    what it added and removed. Both are the same rule as the anchor one,
    applied to the config: never claim the work.
"""

import argparse
import copy
import json
import os
import re
import shutil
import stat
import subprocess
import sys

import graph_reconcile

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    os.pardir, os.pardir, os.pardir, "hooks", "scripts",
))
import crew_backup  # pylint: disable=wrong-import-position
import crew_common  # pylint: disable=wrong-import-position
import crew_dropped  # pylint: disable=wrong-import-position
import crew_guards  # pylint: disable=wrong-import-position
import crew_state  # pylint: disable=wrong-import-position

# Not a second copy of the PM defaults. crew_state owns them because the hook
# reads config on every session start; if an upgrade wrote defaults the hook
# disagreed with, a freshly upgraded repo would behave differently from a
# freshly created one and nothing would say so.
PM_BLOCK = crew_state.PM_DEFAULTS

GRAPH_BLOCK = {
    # crew_state owns this default too -- it has to resolve the same directory
    # when no config exists at all.
    "out": crew_state.GRAPH_OUT_DEFAULT,
    # There is deliberately no Obsidian export key here. The graph lives on
    # the filesystem as `graph.json` and nowhere else -- see crew-graph/
    # SKILL.md, "Why there is no Obsidian export". A config written before
    # 0.16.13 may still carry `graph.obsidian`; `upgrade_config` drops it and
    # names it in `notes["droppedKeys"]` rather than migrating it, because
    # there is no longer anything for it to mean.
}

# `/crew:change`'s block: the one key left in it. `requireForProduction` is
# read by `commands/promote.md` gate 1 and ratchets (a repo may turn it on,
# never off; see `crew_guards.CHANGE_REQUIREMENTS`). The other five keys of
# the block were dropped in L-0725 (`crew_dropped.DROPPED`).
CHANGE_BLOCK = {
    "requireForProduction": False,
}

# The sha group must run to END OF LINE, and the prefix must be LAZY. Both,
# not either.
#
# The previous form was `^(anchor:\s*\S*@?)([0-9a-f]{7,40})` with a greedy
# `\S*` and no end anchor, and `[0-9a-f]{7,40}` is satisfied by the LAST seven
# hex characters on the line. So the prefix ate everything before them and the
# rewrite left them attached:
#
#   anchor: repo@1f97e51c   (8 chars)  ->  anchor: repo@1d61342c
#   anchor: repo@<40 chars>            ->  anchor: repo@<first 33><new sha>
#
# A 7-character anchor was the ONLY length that survived, which is why this
# shipped: every anchor this repo wrote by hand was seven. The corrupted value
# still parses -- `crew_state._ANCHOR_RE` reads `1d61342c` as a perfectly
# well-formed sha -- it just names a commit that does not exist, so the
# freshness check reports the map behind HEAD forever and no amount of
# refreshing fixes it. Silent, permanent, and invisible in review.
#
# Note this does NOT contradict CLAUDE.md's "anchor length does not matter":
# that entry is about `crew_state._ANCHOR_RE`, the COMPARISON, which is
# correct and already end-anchored. This is the writer, and it is a different
# regex in a different file.
#
# `(?=\s*$)` is a lookahead so `sub` does not consume the trailing whitespace
# it matched; `\S*?` is lazy so the prefix stops at the earliest point where a
# run of hex reaches the end of the line.
_DERIVED_ANCHOR_RE = re.compile(r"^derived-anchor:.*$", re.M)
_ANCHOR_LINE_RE = re.compile(r"^(anchor:\s*\S*?@?)([0-9a-f]{7,40})(?=\s*$)",
                             re.MULTILINE | re.IGNORECASE)


# The merge policy itself moved to crew_state.merge_defaults so
# crew_config.resolve_config's global/repo layering uses the exact same
# rule as this module's v1->v2 upgrade does, rather than a second
# implementation that could quietly diverge. Kept as a module-level name
# here since both call sites below predate the move and read cleanly as-is.
_merged = crew_state.merge_defaults


_ABSENT = object()

# CONFIG_BLOCKS keys `~/.claude/crew/config.json` may set WHOLE -- every leaf
# of the block named here is one `crew_config.default_global_config()` copies
# verbatim from the SAME defaults object this module hands to `_merged`, per
# that function's own docstring. Mirrored here as a plain set rather than
# imported: `crew_config` imports THIS module (for these very block objects),
# so the reverse import would be the real cycle `crew_state.CONTEXT_DEFAULTS`'s
# own comment already documents for the same reason.
#
# `graph` and `production` are deliberately absent -- both are entirely
# repo-only, so they keep seeding every leaf regardless of what the repo
# supplied, exactly as before this fix. `context` is also absent: it is only
# PARTIALLY global (its `autoClear` subtree only), so it gets
# its own branch in `_prune_unsupplied_global_leaves` rather than a place in
# this set.
_GLOBAL_WHOLE_BLOCKS = frozenset((
    "pm", "qa", "dev", "install", "change",
))


def _leaf_paths(node, prefix=()):
    """Every dotted-tuple path to a non-dict value in `node`. An empty dict
    is itself a leaf -- `qa.roles`/`dev.roles` are open tables replaced
    wholesale, not blocks to descend into, matching `crew_config.leaf_paths`,
    which this mirrors for the reason `_GLOBAL_WHOLE_BLOCKS` gives."""
    out = []
    for key, value in node.items():
        here = prefix + (key,)
        if isinstance(value, dict) and value:
            out.extend(_leaf_paths(value, here))
        else:
            out.append(here)
    return out


def _dig(node, parts):
    cur = node
    for part in parts:
        if not isinstance(cur, dict) or part not in cur:
            return _ABSENT
        cur = cur[part]
    return cur


def _pop_path(node, parts):
    cur = node
    for part in parts[:-1]:
        cur = cur.get(part) if isinstance(cur, dict) else None
        if not isinstance(cur, dict):
            return
    if isinstance(cur, dict):
        cur.pop(parts[-1], None)


def _prune_unsupplied_global_leaves(block_key, merged, supplied):
    """`merged`, with every globally-settable leaf the repo never wrote
    dropped back out. Mutates and returns `merged`.

    THE FIX for the defect the PM measured at 8b8a4028: `crew_config.
    resolve_config` resolves an ordinary key by PRECEDENCE -- repo beats
    global beats built-in -- so a leaf this function seeded, even at the
    exact built-in default, outranks a value set in
    `~/.claude/crew/config.json` afterward, forever.
    `upgrade_config({"schema": 2, "pm": {"enabled": True}})` used to return
    `pm.authority: "report-only"` written to disk, and no global
    `pm.authority` could ever reach that repo again. A leaf the repo
    ACTUALLY wrote -- present in `supplied` at that same path, whatever its
    value -- is never touched; only a leaf this function was about to invent
    is removed.

    Safe for the ratcheted leaves too (`install.policy`, every `guards.*`),
    and provably a no-op for the ratchet mechanism itself: those resolve
    through `crew_state.effective_ratcheted` / `crew_config.
    resolve_ratcheted`, which read the RAW repo value directly rather than
    through `resolve_config`, and an absent key there normalises to the
    IDENTICAL floor value the merge would have written --
    `crew_guards.normalise_install_policy(None) == INSTALL_POLICY_DEFAULT`,
    and the same shape for every other `guards.*` reader, `roleWrites`
    included: its default IS what absent already means (see
    `crew_guards.normalise_role_writes`'s own docstring, which is explicit
    that this one is not the floor). Pruning them removes a value that was
    never doing anything either way.

    Repo-only blocks (`graph`, `production`, and every `context` leaf besides
    `autoClear`) are untouched -- see `_GLOBAL_WHOLE_BLOCKS`.
    """
    supplied = supplied if isinstance(supplied, dict) else {}
    if block_key == "context":
        auto = merged.get("autoClear")
        if not isinstance(auto, dict):
            return merged
        supplied_auto = supplied.get("autoClear")
        supplied_auto = (supplied_auto if isinstance(supplied_auto, dict)
                         else {})
        for parts in _leaf_paths(auto):
            if _dig(supplied_auto, parts) is _ABSENT:
                _pop_path(auto, parts)
        return merged
    if block_key not in _GLOBAL_WHOLE_BLOCKS:
        return merged
    for parts in _leaf_paths(merged):
        if _dig(supplied, parts) is _ABSENT:
            _pop_path(merged, parts)
    _strip_empty_dicts(merged)
    return merged


def _strip_empty_dicts(node):
    """Remove a nested dict `_pop_path` emptied out but did not remove --
    it only ever pops the LEAF, so a container two levels deep whose every
    leaf was pruned (`qa.codex` with both `model` and `reasoningEffort`
    absent) survives as a stray `{}`. Left in, `qa` would read `{"codex":
    {}, "copilot": {}}` for a repo that named neither -- harmless to
    `resolve_config` (an empty dict "supplies" nothing, same as absent) but
    noisy on disk, and inconsistent with the flat blocks (`pm`, `install`),
    which come out omitted entirely rather than as an empty shell. Mutates.
    """
    for key in list(node.keys()):
        value = node[key]
        if isinstance(value, dict):
            _strip_empty_dicts(value)
            if not value:
                del node[key]


# Every block an upgrade brings forward, and the defaults it brings it onto.
# `qa` and `dev` were missing from this list until 0.16.0, which is the whole
# of the bug: a config predating the 0.14.4 provider table was stamped current
# while still carrying neither.
def _without_tombstoned(block, supplied):
    """Drop defaults the operator removed ON PURPOSE, marked by a sibling Note.

    DEFECT 1, reported by a peer session: a repo had deleted `qa.copilot` and
    left `qa.copilotNote` beside it reading "Do not re-add it as null; pin a
    real model or omit the key." The upgrade put `{"model": null}` straight
    back, because a defaults-seeding pass cannot tell "never set" from
    "deliberately removed" -- both look like an absent key.

    So the repo gets to say which it meant. A sibling `<key>Note` is the
    convention that repo already used, and it is now honoured: the key is not
    re-seeded, and the report names it so the silence is not silent.

    This does NOT make removal generally expressible -- there is no tombstone
    for a key with no Note beside it, and adding `context` to CONFIG_BLOCKS
    (which is what this release does) widens the same door for anything under
    it. Treated as a narrowing of a known failure, not a fix for the class.
    """
    if not isinstance(supplied, dict):
        return block
    tomb = [k for k in block
            if f"{k}Note" in supplied and k not in supplied]
    if not tomb:
        return block
    out = {k: v for k, v in block.items() if k not in tomb}
    _TOMBSTONED.extend(tomb)
    return out


# Names skipped this run because a sibling `<key>Note` said so. Module level
# because `_merged` is called per block and the report is built once.
_TOMBSTONED = []

CONFIG_BLOCKS = (
    ("pm", PM_BLOCK),
    ("graph", GRAPH_BLOCK),
    ("qa", crew_state.QA_DEFAULTS),
    ("dev", crew_state.DEV_DEFAULTS),
    # ADDED 2026-09-17, after a user reported that a schema 3 -> 7
    # upgrade left context.autoClear / autoWrapUp / autoResume /
    # staleHandoff absent. They were absent because `context` was never
    # in this tuple: the migration adds exactly what is named here, and
    # nothing named it. This module's own docstring predicted the shape
    # of that failure for the qa/dev table; `context` is the one that
    # actually got missed.
    ("context", crew_state.CONTEXT_DEFAULTS),
    ("install", crew_state.INSTALL_DEFAULTS),
    # No `guards` row since L-0725: the twelve per-guard keys are rewritten
    # into `guards.profile` + `guards.overrides` by `rewrite_guards`, from the
    # incoming file, and never seeded from defaults.
    # Repo-only, one of the two blocks here that is. `default_global_config()`
    # does not carry it, so `filter_global` prunes a `production` block out
    # of a machine-global file and reports it: the level ratchets across
    # both layers, the patterns are a fact about this checkout.
    ("production", crew_state.PRODUCTION_DEFAULTS),
    # Repo-only for the same reason: the cloud guard's identity pins.
    ("cloud", crew_state.CLOUD_DEFAULTS),
    ("change", CHANGE_BLOCK),
)

# `{block_key: block_default}`, restricted to the whole-block globally
# settable ones -- the lookup `_pinned_at_default` walks. Built from
# `CONFIG_BLOCKS` itself rather than written out a second time, so a block
# added there is covered here automatically as soon as it is also added to
# `_GLOBAL_WHOLE_BLOCKS`.
_GLOBAL_BLOCK_DEFAULTS = {k: v for k, v in CONFIG_BLOCKS
                          if k in _GLOBAL_WHOLE_BLOCKS}


def _pinned_at_default(out):
    """Globally-settable leaves `out` still carries at exactly the built-in
    default -- named in the report, never touched here. See `notes
    ["pinnedAtDefault"]`'s own comment for why: most likely written by an
    upgrade that predates `_prune_unsupplied_global_leaves`, which is what
    made a leaf like this frozen against the global layer in the first
    place, and removing a value from a user's file still needs their yes.
    """
    found = []
    for key, default_block in _GLOBAL_BLOCK_DEFAULTS.items():
        node = out.get(key)
        if not isinstance(node, dict):
            continue
        for parts in _leaf_paths(default_block):
            actual = _dig(node, parts)
            if actual is _ABSENT:
                continue
            if actual == _dig(default_block, parts):
                found.append(key + "." + ".".join(parts))
    ctx = out.get("context")
    auto = ctx.get("autoClear") if isinstance(ctx, dict) else None
    if isinstance(auto, dict):
        for leaf_key, default_val in crew_state.AUTOCLEAR_DEFAULTS.items():
            if leaf_key in auto and auto[leaf_key] == default_val:
                found.append(f"context.autoClear.{leaf_key}")
    return sorted(found)

# The keys schema 3 introduced. Named here rather than diffed generically so
# the report can SAY what the 2 -> 3 migration added, in the words the user
# will search for. Both are behaviour-neutral on arrival -- `fallback` only
# fires when a pinned model is gone, which previously was an error and not a
# fallback at all, and an EMPTY `roles` table means every role keeps running
# on the block's own `provider`, exactly as it did before.
SCHEMA_3_KEYS = ("qa.fallback", "qa.roles", "dev.fallback", "dev.roles")

# The key schema 5 introduced. One key, deliberately: bumping SCHEMA_CURRENT
# makes every crew repo on every machine report `upgradeNeeded`, so this
# migration is mandatory and costs the same whether it carries one key or six.
# The user ruled on 2026-09-12 that it carries this one alone -- a key added
# ahead of a need has cost more to undo here than a second bump would cost to
# pay, and `docs.theme` is the worked example sitting one block above.
#
# Behaviour-neutral on arrival, which is the bar a mandatory migration has to
# clear: it lands as `manual`, and `manual` is what crew already did at schema
# 4, which is nothing. Nobody's machine starts running install commands because
# they upgraded.
SCHEMA_5_KEYS = ("install.policy",)

# The keys schema 6 introduces. Named here for the same reason the two lists
# above are: so the report can SAY what the 5 -> 6 migration added, in the
# words the user will search for.
#
# Six keys rather than schema 5's one, and the rule the user set on 2026-09-12
# ("a key added ahead of a need costs more to undo than a second bump costs to
# pay") is satisfied rather than broken: every one of these six has a consumer
# landing in the same change. The four `guards.*` are read by `guard.sh` and
# `guard.ps1` through `crew_config.py --guard`, and the two `github.mergeGate`
# keys are read by `commands/gate.md` and `commands/promote.md`. A seventh key
# with no consumer would still be wrong; these are not that.
#
# Behaviour-neutral on arrival for the two rules that already existed --
# `terraformApply` and `forcePush` land as `block`, which is what the guard
# already did. It is NOT behaviour-neutral overall, and the report says so:
# `adminMerge` refuses `gh pr merge --admin`, which no guard refused before,
# and `terraformApply` now also covers `tofu`. A migration that claimed
# neutrality it does not have would be the "unknown wearing the label of a
# check that happened" failure, one layer out.
# The two production guards arrive in the SAME schema 6 rather than a seventh
# bump, and they are behaviour-neutral on arrival in a way the other four are
# not: they land at `none`, but `production.databases` and `production.hosts`
# land EMPTY, and with no pattern declared the guard matches nothing. So the
# strictest possible level refuses the empty set until somebody says what
# production is. That is the property that let them ship at `none` by default,
# and it is stated in CONFIG.md rather than left to be rediscovered.
#
# L-0725: the `guards.<name>` keys left this tuple. They are no longer keys; a
# schema 8 migration rewrites whatever a file holds into `guards.profile` and
# `guards.overrides` (`rewrite_guards`), so reporting them as "added" would
# name keys nothing reads. The production patterns stay.
SCHEMA_6_KEYS = ("production.databases", "production.hosts")

# The keys schema 7 introduces: the whole `change` block, for `/crew:change`.
#
# Six keys and six consumers, all landing together -- see `CHANGE_BLOCK`. The
# rule from schema 5 ("a key added ahead of a need costs more to undo than a
# second bump costs to pay") is satisfied, not waived.
#
# Behaviour-neutral on arrival, and unlike schema 6 that claim has no exception
# to declare. `requireForProduction` lands `false`, which is what every repo
# already did: promote's gate 1 asks for no change request. The other five are
# null or a default template name, read by a command that has to be invoked
# before any of them is consulted. Nobody's promotion starts failing because
# they upgraded.
#
# The one thing that IS new and is worth saying out loud rather than hiding
# behind "neutral": the repo gains `/crew:change`, and gains the ability to turn
# `requireForProduction` on. Turning it on is a one-way ratchet across the two
# config layers (a repo may turn it ON, never off), so the report says which
# direction the key moves in before anybody sets it.
SCHEMA_7_KEYS = ("change.requireForProduction",)


# Schema 8 (L-0725). Two rewrites shared by the repo layer (`upgrade_config`)
# and the machine layer (`upgrade_global`), both pure.

# The tie order when two profiles need the same number of overrides: the
# default first, so a layer that sets nothing stays `off`.
_PROFILE_TIE_ORDER = ("off", "standard", "strict")

# `tier` and `roles`: read only for display, so they are removed even when set.
RETIRED_KEYS = tuple(key for key, (_default, what) in crew_dropped.DROPPED.items()
                     if what.startswith("retired:"))


def guard_layer_values(layer_cfg):
    """`{guard: tier}` for all twelve guards in ONE layer. A guard the layer
    does not set is its default, which is exactly what the ratchet reads an
    absent value as (`resolve_ratcheted` ranks `normalise(None)`), so the
    answer below is the value the ratchet sees. A legacy `guards.<name>`, a
    profile and an override are combined by `crew_guards.layer_guard_state`,
    the same function the resolver uses -- never a second reading of them."""
    values = {}
    for name in crew_guards.ALL_GUARD_NAMES:
        value = crew_guards.layer_guard_value(layer_cfg, name)
        values[name] = crew_guards.GUARD_DEFAULTS[name] if value is None else value
    return values


def choose_profile(values):
    """`(profile, overrides)` with the FEWEST overrides that reproduce
    `values` (`{guard: tier}`); a tie goes off, then standard, then strict.
    `overrides` holds only the guards whose value differs from the profile's."""
    candidates = []
    for profile in _PROFILE_TIE_ORDER:
        table = crew_guards.PROFILE_MAP[profile]
        candidates.append((profile, {name: values[name] for name in crew_guards.ALL_GUARD_NAMES
                                     if values[name] != table[name]}))
    # `min` keeps the first of equal lengths, which is the tie order.
    return min(candidates, key=lambda pair: len(pair[1]))


def rewrite_guards(out, unmigrated, unknown=None):
    """Rewrite `out["guards"]` in place to `{"profile", "overrides"}` and
    return `(profile, overrides)`, or `(None, {})` when there was nothing to
    rewrite. Every legacy `guards.<name>` key goes; any other key in the block
    is carried. A guard name this code does not know inside `overrides` is
    carried into the new table untouched and appended to `unknown` as
    `guards.overrides.<name>`: a migration never deletes what it cannot read.

    Anything the readers treat as corrupt is left exactly as written and named
    in `unmigrated` (which blocks the schema stamp), so the person fixes it by
    hand and a migration never turns it into a profile: a `guards` that is not
    an object, a `profile` that is present but not a profile name (JSON null
    included), and an `overrides` that is present but not an object (null
    included).

    The layer's value for each guard is the same before and after: the
    function reads the layer through `layer_guard_state` and the result is
    checked by the tests with the same call on the output."""
    block = out.get("guards", _ABSENT)
    if block is _ABSENT:
        return None, {}
    if not isinstance(block, dict):
        unmigrated.append("guards")
        return None, {}
    if "profile" in block and crew_guards.normalise_profile(block["profile"]) is None:
        unmigrated.append("guards.profile")
    overrides_raw = block.get("overrides")
    if "overrides" in block and not isinstance(overrides_raw, dict):
        unmigrated.append("guards.overrides")
    if "guards.profile" in unmigrated or "guards.overrides" in unmigrated:
        return None, {}
    legacy = [key for key in block if key in crew_guards.ALL_GUARD_NAMES]
    if not legacy and "profile" not in block and "overrides" not in block:
        return None, {}
    profile, overrides = choose_profile(guard_layer_values(out))
    carried = {name: value for name, value in (overrides_raw or {}).items()
               if name not in crew_guards.ALL_GUARD_NAMES}
    if unknown is not None:
        unknown.extend(f"guards.overrides.{name}" for name in carried)
    rewritten = {"profile": profile, "overrides": {**overrides, **carried}}
    for key, value in block.items():
        if key not in legacy and key not in rewritten:
            rewritten[key] = value
    out["guards"] = rewritten
    return profile, overrides


def _same_value(left, right):
    """Equal as JSON, so `False` is not `0` and `60` is not `60.0`: a value
    that only compares equal in Python is not "the default" for a migration
    that must never remove something a person set."""
    try:
        return (json.dumps(left, sort_keys=True)
                == json.dumps(right, sort_keys=True))
    except (TypeError, ValueError):
        return False


def _remove_path(node, parts):
    """Delete the leaf at `parts`, then every parent the removal left empty
    (a block that was already empty before is not touched)."""
    for depth in range(len(parts), 0, -1):
        parent = _dig(node, parts[:depth - 1]) if depth > 1 else node
        if not isinstance(parent, dict):
            return
        if depth == len(parts):
            parent.pop(parts[depth - 1], None)
        elif parent.get(parts[depth - 1]) == {}:
            parent.pop(parts[depth - 1], None)
        else:
            return


def drop_keys(out, notes, accept_dropped=(), machine=False):
    """Remove the 60 dropped keys from `out` in place, and fill `notes`.

    A key holding its default (`crew_dropped.DROPPED`; for the machine file
    `GLOBAL_DEFAULTS` first) is removed: `removedDefault`. `tier` and `roles`
    are removed whatever they hold: `retiredRemoved`. A key holding anything
    else is listed in `droppedNonDefault`; it is removed only when named in
    `accept_dropped` (`acceptedDropped`), and otherwise stays in `out` and is
    a conflict for the caller. A block the removals leave empty goes too."""
    accept = set(accept_dropped)
    for dotted, (default, _constant) in crew_dropped.DROPPED.items():
        if machine and dotted in crew_dropped.GLOBAL_DEFAULTS:
            default = crew_dropped.GLOBAL_DEFAULTS[dotted]
        parts = tuple(dotted.split("."))
        value = _dig(out, parts)
        if value is _ABSENT:
            continue
        if dotted in RETIRED_KEYS:
            _remove_path(out, parts)
            notes["retiredRemoved"].append(dotted)
        elif _same_value(value, default):
            _remove_path(out, parts)
            notes["removedDefault"].append(dotted)
        else:
            notes["droppedNonDefault"].append(dotted)
            if dotted in accept:
                _remove_path(out, parts)
                notes["acceptedDropped"].append(dotted)


def unacceptable_drops(accept_dropped):
    """The names in `accept_dropped` that are not a droppable key: not in
    `crew_dropped.DROPPED`, or retired (those never need accepting)."""
    return [key for key in accept_dropped
            if key not in crew_dropped.DROPPED or key in RETIRED_KEYS]


def refused_drops(notes):
    """`[(key, constant)]` for every non-default dropped key nobody accepted:
    the conflict list. Empty means the run may write."""
    return [(key, crew_dropped.DROPPED[key][1]) for key in notes["droppedNonDefault"]
            if key not in notes["acceptedDropped"]]


def upgrade_global(cfg, accept_dropped=()):
    """The machine file (`~/.claude/crew/config.json`) brought to the L-0725
    shape. Pure; returns `(out, notes)`. It has no schema and no blocks to
    seed, so it does only the two schema-8 rewrites: the guards into a profile
    plus overrides, and the dropped keys (with the machine defaults of
    `crew_dropped.GLOBAL_DEFAULTS`). Same notes keys as `upgrade_config` for
    those two, plus `unmigrated`."""
    out = copy.deepcopy(dict(cfg))
    notes = {"unmigrated": [], "unknown": [], "guardProfile": None, "guardOverrides": {},
             "removedDefault": [], "retiredRemoved": [],
             "droppedNonDefault": [], "acceptedDropped": []}
    notes["guardProfile"], notes["guardOverrides"] = rewrite_guards(
        out, notes["unmigrated"], notes["unknown"])
    drop_keys(out, notes, accept_dropped, machine=True)
    return out, notes


def upgrade_config(cfg, accept_dropped=()):
    """Bring a config up to the current schema. Pure.

    Returns `(out, notes)`. `out` preserves every key it does not know about;
    `notes` is what the run has to SAY, and is not optional decoration:

        {"unmigrated": [...], "schemaFrom": int,
         "providerKeysAdded": [...], "installKeysAdded": [...],
         "guardKeysAdded": [...], "schemaStamped": bool,
         "guardProfile": str | None, "guardOverrides": {...},
         "removedDefault": [...], "retiredRemoved": [...],
         "droppedNonDefault": [...], "acceptedDropped": [...]}

    Rules, each of which used to be wrong here:

      * **Every block moves forward, not just `pm` and `graph`.** See
        `CONFIG_BLOCKS`.
      * **Schema 3's per-role provider table arrives EMPTY.** `qa.roles` and
        `dev.roles` are added as `{}` and `fallback` as its default value, so
        a v2 config comes out of this dispatching to exactly the provider and
        model it dispatched to before. That is the whole design of the 2 -> 3
        migration: bumping `SCHEMA_CURRENT` makes every crew repo on the
        machine report `upgradeNeeded`, so this migration is mandatory, and a
        mandatory migration that silently re-routed someone's development work
        to a different model would be indefensible. `/crew:upgrade` OFFERS the
        pins afterwards; it never writes them here.
      * **Schema 8 (L-0725) rewrites `guards` and removes the 60 dropped keys.**
        The twelve per-guard keys become `guards.profile` plus the fewest
        `guards.overrides` that reproduce every guard's value in this layer
        (`rewrite_guards`). A dropped key (`crew_dropped.DROPPED`) holding its
        default is removed; one holding anything else is listed in
        `droppedNonDefault` and is a conflict -- nothing may be written, and
        `schema` is not stamped -- unless the caller names it in
        `accept_dropped`, which removes it (the caller's backup holds it) and
        records it in `acceptedDropped`. `tier` and `roles` are retired: always
        removed, never a conflict.
      * **`schema` is stamped only when everything migrated.** A block that
        arrived as the wrong type is left exactly as the user wrote it and
        named in `notes["unmigrated"]`; marking that config current would
        claim work that did not happen, and the next run would skip it.
    """
    # Private copies: `_merged` hands back nested dicts of `supplied` itself,
    # and the pruning and key removals below edit them in place. The caller's
    # dict is never touched.
    cfg = copy.deepcopy(dict(cfg))
    out = copy.deepcopy(cfg)
    notes = {"unmigrated": [], "unknown": [],
             "schemaFrom": crew_state.int_or(cfg.get("schema", 1), 1),
             "providerKeysAdded": [], "installKeysAdded": [],
             "guardKeysAdded": [], "changeKeysAdded": [],
             "schemaStamped": False,
             # Keys this upgrade removed outright. Distinct from
             # "unmigrated", which blocks the schema stamp: a dropped key is
             # a completed migration, not a failed one.
             "droppedKeys": [],
             # L-0725, schema 8. See `rewrite_guards` and `drop_keys`.
             "guardProfile": None, "guardOverrides": {},
             "removedDefault": [], "retiredRemoved": [],
             "droppedNonDefault": [], "acceptedDropped": [],
             # Globally-settable leaves this repo's config still carries at
             # exactly the built-in default -- most likely written by an
             # upgrade that predates `_prune_unsupplied_global_leaves`, which
             # is what made them frozen in the first place. Never removed
             # here: taking a value out of a user's file needs their yes, not
             # an upgrade's guess. Set at the end, from `out`.
             "pinnedAtDefault": [],
             # The two facts `_report`'s absent-global headline needs about
             # `pm.authority` specifically, computed here rather than by the
             # report builder reading `out` itself -- same contract as
             # `pinnedAtDefault`.
             "pmAuthorityAfter": None,
             "pmAuthorityLayer": "default"}

    for key, block in CONFIG_BLOCKS:
        supplied = cfg.get(key, _ABSENT)
        block = _without_tombstoned(block, supplied)
        if supplied is not _ABSENT and not isinstance(supplied, dict):
            # _merged would discard it and the user would never know. Leave
            # the value untouched and report it instead.
            notes["unmigrated"].append(key)
            continue
        # deepcopy first: with nothing supplied at a nested key, _merged hands
        # back the module-level default object itself, and a caller writing
        # through the result would mutate the shared default for every later
        # caller in the process.
        #
        # `dropped` catches the NESTED version of the check above: a scalar
        # where the schema wants a block, e.g. `qa.codex: "human"`. _merged
        # discards it on purpose -- callers index into these blocks -- but a
        # migration that rewrites the user's file must say which value it
        # refused to carry forward. Without this the config came back stamped
        # current with the value gone and `unmigrated` empty.
        dropped = []
        merged = _merged(copy.deepcopy(block),
                         None if supplied is _ABSENT else supplied,
                         dropped, key)
        if dropped:
            # Same contract as the top-level branch above: leave the block
            # EXACTLY as written and report it. Reporting the loss while
            # still writing the replacement would make the report itself a
            # lie -- it says "left exactly as written" -- and the value would
            # be gone from disk either way.
            notes["unmigrated"].extend(dropped)
            continue
        merged = _prune_unsupplied_global_leaves(
            key, merged, None if supplied is _ABSENT else supplied)
        # A block the repo never mentioned, once every globally-settable leaf
        # is pruned back out, can come back empty (`pm`, `install`, ...).
        # Writing `"pm": {}` into the file is functionally identical to
        # omitting the key -- `crew_config._layer_supplies` already treats an
        # empty dict as "mentions a key without deciding its value" -- but
        # omitting it is the honest statement of what this run actually
        # decided: nothing. A block the repo DID write (`supplied` a dict,
        # even `{}`) keeps its key regardless, so a deliberate empty block
        # survives exactly as written.
        if merged or supplied is not _ABSENT:
            out[key] = merged

    # What each schema bump actually added to THIS config, computed from the
    # incoming file rather than from the version number: a config hand-edited
    # to carry `dev.roles` or `install.policy` already must not be reported as
    # having just gained it.
    notes["providerKeysAdded"] = _keys_added(cfg, notes, SCHEMA_3_KEYS)
    notes["installKeysAdded"] = _keys_added(cfg, notes, SCHEMA_5_KEYS)
    notes["guardKeysAdded"] = _keys_added(cfg, notes, SCHEMA_6_KEYS)
    notes["changeKeysAdded"] = _keys_added(cfg, notes, SCHEMA_7_KEYS)

    # `graph.obsidian` was removed in 0.16.13. Drop it loudly rather than
    # carrying it forward: a key that survives an upgrade but no longer has a
    # consumer reads, to anyone inspecting the config, as a feature that is
    # merely switched off. Naming it is what tells them it is gone.
    # `out["graph"]` is only a dict when the supplied block was well-typed.
    # A wrong-typed block (`"graph": "oops"`) is kept VERBATIM and reported in
    # `unmigrated` -- popping a key off it raises AttributeError and takes the
    # whole migration down partway, after run() has already written the file.
    #
    # Only below schema 7, which is where this drop has always applied: a
    # schema 7 config was never rewritten by the upgrade, and the 7 -> 8 step
    # deletes nothing it was not told to (L-0725, "No unknown key is deleted
    # from a config file by migration"). There the key is carried untouched
    # and `crew_migrate` lists it as unknown.
    if isinstance(out.get("graph"), dict) and notes["schemaFrom"] < 7:
        if isinstance(crew_state.dict_or_empty(cfg.get("graph")).get("obsidian"),
                      dict):
            notes["droppedKeys"].append("graph.obsidian")
        out["graph"].pop("obsidian", None)

    notes["guardProfile"], notes["guardOverrides"] = rewrite_guards(
        out, notes["unmigrated"], notes["unknown"])
    drop_keys(out, notes, accept_dropped)

    conflicts = [key for key in notes["droppedNonDefault"]
                 if key not in notes["acceptedDropped"]]
    if not notes["unmigrated"] and not conflicts:
        out["schema"] = crew_state.SCHEMA_CURRENT
        notes["schemaStamped"] = True

    notes["pmAuthorityAfter"] = crew_state.normalise_authority(
        crew_state.dict_or_empty(out.get("pm")).get("authority"))
    notes["pmAuthorityLayer"] = (
        "repo" if "authority" in crew_state.dict_or_empty(out.get("pm"))
        else "default")

    notes["pinnedAtDefault"] = _pinned_at_default(out)

    return out, notes


def _keys_added(cfg, notes, dotted_keys):
    """Which of `dotted_keys` this migration is adding to `cfg`.

    One walk for every schema list, and it descends ARBITRARILY DEEP rather
    than unpacking two parts. The two-part form (`block_key, leaf =
    dotted.split(".")`) was correct for `qa.fallback` and `install.policy` and
    raises `ValueError` on `guards.overrides.forcePush` -- inside `upgrade_config`
    which `run()` calls BEFORE it writes anything, so the whole migration would
    have died at the first three-part key rather than shipping a wrong answer.
    Loud, but still a bug the second nested block was always going to hit.

    A key under a block that could not be migrated is skipped: `_block_untouched`
    says the block was left exactly as the user wrote it, so reporting a key as
    added to it would claim work that did not happen.

    Absent ANYWHERE along the path counts as added, including the case where an
    intermediate node is present but not a dict -- a `github: "oops"` is already
    in `unmigrated`, and anything else that is not a dict cannot be carrying the
    leaf.
    """
    out = []
    for dotted in dotted_keys:
        parts = dotted.split(".")
        if _block_untouched(notes, parts[0]):
            continue
        node = cfg
        for part in parts:
            if not isinstance(node, dict) or part not in node:
                out.append(dotted)
                break
            node = node[part]
    return out


def _block_untouched(notes, block_key):
    """Was `block_key` left un-migrated, whole or in part?

    `unmigrated` holds a bare block name when the block itself was the wrong
    type, and a dotted path (`qa.codex`) when a nested value was. Both mean
    the block was left exactly as the user wrote it, so anything that indexes
    into the migrated shape afterwards must skip it -- a plain `in` test sees
    only the first kind and walks straight into the second.
    """
    return any(entry == block_key or entry.startswith(block_key + ".")
               for entry in notes["unmigrated"])


def backup_codemap(root):
    """Copy .crew/codemap/ aside. Returns the path, or None if there is none."""
    src = os.path.join(root, ".crew", "codemap")
    if not os.path.isdir(src):
        return None
    dst = os.path.join(root, ".crew", "codemap.v1.bak")
    if os.path.exists(dst):
        return dst          # a previous run already took one; do not overwrite
    shutil.copytree(src, dst)
    return dst


def backup_config(root):
    """Copy .crew/config.json aside. Returns the path, or None if there is none.

    Same rule as backup_codemap: this is the file run() is about to
    overwrite, so it gets the same non-destructive backup, taken once.
    """
    src = os.path.join(root, ".crew", "config.json")
    if not os.path.isfile(src):
        return None
    dst = os.path.join(root, ".crew", "config.json.v1.bak")
    if os.path.exists(dst):
        return dst          # a previous run already took one; do not overwrite
    shutil.copy2(src, dst)
    return dst


def _read_config_strict(root):
    """Parse .crew/config.json, distinguishing "nothing to preserve" from
    "something here failed to parse".

    crew_state.load_config() collapses both cases to {} on purpose -- it
    backs a SessionStart hook that must never raise, so "malformed" and
    "absent" have to look the same to it. run() cannot afford that
    collapse: writing upgrade_config({}) over a config that merely failed to
    parse discards it, reported as success. Returns (cfg, ok); ok is False
    only when the file is present but did not yield a dict.
    """
    text = crew_state.read_text(os.path.join(root, ".crew", "config.json"))
    if text is None:
        return {}, True  # absent: nothing to preserve, nothing wrong
    try:
        parsed = json.loads(text)
    except ValueError:
        return {}, False
    if not isinstance(parsed, dict):
        return {}, False
    return parsed, True


def _head(root):
    try:
        done = subprocess.run(
            (crew_common.require_tool("git"), "rev-parse", "--short=7", "HEAD"), cwd=root,
            capture_output=True, text=True, timeout=10, check=False,
            stdin=subprocess.DEVNULL,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return done.stdout.strip() if done.returncode == 0 else None


def _bump_anchor(text, head):
    """Record a DERIVE-only re-verification WITHOUT touching `anchor:`.

    CHANGED 2026-09-17. This used to rewrite `anchor:` whenever the reconcile
    touched anything, and `touched` can only ever contain DERIVE headings --
    `graph_reconcile.reconcile` skips KEEP at the top of its loop, so `Does`,
    `Landmines` and `Unverified` are never read by this procedure at all.
    Adding two derived lines therefore stamped the WHOLE note current.

    Measured on this repo before the fix: `.crew/codemap/crew.md` was stamped
    f9bb78a6 -> ea8a014 on 12 added lines while 18 of its 40 cited files had
    moved. A peer session measured the same on two notes of its own, one with
    52 moved files and one with 58. `crew_state.knowledge.behind` and the PM
    pulse both trust `anchor:`, so the run converted a correct "behind" signal
    into a false "current" one on exactly the notes most in need of a human.

    `anchor:` keeps its old meaning -- this whole note was re-verified -- and
    the weaker fact gets its own key. A false freshness claim is worse than an
    honest stale one; that is reconcile.md's own argument, applied to the
    anchor it is about.
    """
    if not head:
        return text
    line = f"derived-anchor: {head}\n"
    if "derived-anchor:" in text:
        return _DERIVED_ANCHOR_RE.sub(line.rstrip("\n"), text, count=1)
    # Directly beneath `anchor:`, so the two are read together.
    found = _ANCHOR_LINE_RE.search(text)
    if not found:
        return text
    end = text.index("\n", found.start()) + 1
    return text[:end] + line + text[end:]


def schema8_lines(notes):
    """The report lines for the L-0725 rewrites: the guards profile, every key
    removed and why, and every dropped key nobody accepted losing. Shared by
    the repo report and by `crew_migrate --global`, whose notes carry only
    these keys."""
    lines = []
    if notes["guardProfile"] is not None:
        overrides = notes["guardOverrides"]
        if overrides:
            what = (f" with {len(overrides)} override(s): "
                    + ", ".join(f"{k}={v}" for k, v in sorted(overrides.items())))
        else:
            what = ", no overrides"
        lines.append(
            f"- guards: `guards.profile` {notes['guardProfile']}{what}. The "
            "twelve per-guard keys are gone from this file and every guard "
            "keeps the value it had here.")
    if notes["removedDefault"]:
        lines.append(
            "- removed (held their default, now a code constant): "
            + ", ".join(notes["removedDefault"]))
    if notes["retiredRemoved"]:
        lines.append(
            "- removed (retired, read only for display): "
            + ", ".join(notes["retiredRemoved"]) + ". The backup holds them.")
    if notes["acceptedDropped"]:
        lines.append(
            "- removed at your request (a non-default value, kept in the "
            "backup only): " + ", ".join(
                f"{key} (now {crew_dropped.DROPPED[key][1]})"
                for key in notes["acceptedDropped"]))
    refused = refused_drops(notes)
    if refused:
        lines.append(
            "- **REFUSED, nothing written**: a dropped key holds a non-default "
            "value and its setting no longer has any effect: "
            + ", ".join(f"{key} (now {const})" for key, const in refused)
            + ". Remove the key, or pass `--accept-dropped <key>` for each one "
            "to confirm it may go. Nothing was written.")
    return lines


def _config_lines(notes):
    """The config half of the report: what the migration changed, and what it
    could not. A crew that silently changes a file is the thing this report
    exists to catch, so the guard rewrite and every key removed are stated
    every run."""
    lines = ["## Config"] + schema8_lines(notes)
    if notes["droppedKeys"]:
        lines.append(
            "- removed, not migrated: " + ", ".join(notes["droppedKeys"])
            + ". The code graph lives on the filesystem as `graph.json`; the "
            "Obsidian export was withdrawn in 0.16.13 because exporting one "
            "note per node made vaults unusably slow. Nothing to re-enable, "
            "and no setting was silently switched off."
        )
    if notes["installKeysAdded"]:
        lines.append(
            "- schema "
            f"{notes['schemaFrom']} -> {crew_state.SCHEMA_CURRENT}, which "
            "added `install.policy`: what crew may do when a skill it needs "
            "is not installed. It arrives as `manual`, which is what crew "
            "already did — name the missing skill and the command, and run "
            "nothing. **Your machine did not start installing anything "
            "because you upgraded.** `ask` lets crew offer; `auto` lets it "
            "install without asking. Under every policy crew can only run a "
            "command from its own source, never one from a repo config or a "
            "skill file. Set it with `/crew:config` — nothing here chose "
            "anything but the floor for you."
        )
    if notes["guardKeysAdded"]:
        lines.append(
            "- schema "
            f"{notes['schemaFrom']} -> {crew_state.SCHEMA_CURRENT}, which "
            "added the production patterns: "
            + ", ".join(notes["guardKeysAdded"])
            + ". They arrive empty, so the production guards match nothing "
            "until you declare what production is with `/crew:config`."
        )
    if notes["changeKeysAdded"]:
        lines.append(
            "- schema "
            f"{notes['schemaFrom']} -> {crew_state.SCHEMA_CURRENT}, which "
            "added the `change` block for `/crew:change`: "
            + ", ".join(notes["changeKeysAdded"])
            + ". **This one IS behaviour-neutral, with no exception to "
            "declare.** `change.requireForProduction` arrives `false`, which "
            "is what every promotion already did — `/crew:promote production` "
            "asks for no change request, exactly as before. "
            "Note the direction `change.requireForProduction` ratchets, "
            "because it is the opposite of the other ratcheted keys and it is "
            "easier to read than to discover: a repo may turn the requirement "
            "ON and never off, so a machine-global `true` cannot be defeated "
            "by a `false` in a repo you cloned."
        )
    if notes["providerKeysAdded"]:
        lines.append(
            "- schema "
            f"{notes['schemaFrom']} -> {crew_state.SCHEMA_CURRENT}, which "
            "added the per-role provider table and a declared fallback: "
            + ", ".join(notes["providerKeysAdded"])
            + ". Both arrive NEUTRAL — `qa.roles` and `dev.roles` are empty, "
            "so every role still runs on its block's own `provider`, and "
            "`fallback` only fires when a pinned model has been retired, "
            "which used to be a plain error. This repo dispatches exactly as "
            "it did before the upgrade. To pin a model per role, run "
            "`/crew:model` — nothing here chose one for you."
        )
    if notes["unmigrated"]:
        lines.append(
            "- **NOT migrated** (present but the wrong type, left exactly as "
            "written): " + ", ".join(notes["unmigrated"])
            + ". `schema` was deliberately NOT stamped current, so this repo "
            "still reports an upgrade as needed. Fix the block by hand and "
            "run `/crew:migrate` again."
        )
    if notes["pinnedAtDefault"]:
        lines.append(
            "- may be pinned by an earlier /crew:upgrade; delete from "
            ".crew/config.json to let the global file decide: "
            + ", ".join(notes["pinnedAtDefault"])
        )
    lines.append("")
    return lines


# Marks a human has put on a contradiction line. Anything carrying one is
# carried forward verbatim rather than regenerated -- see `_carried_conflicts`.
# T-0065 (item 8): every run puts its report on top of UPGRADE.md and keeps
# the earlier file, byte for byte, below this line. Newest on top keeps
# `/crew:upgrade`'s "opens with" and `_carried_conflicts`'s first
# `## Contradictions` section true without either being rewritten.
UPGRADE_HISTORY_MARKER = ("<!-- crew_upgrade: earlier runs below, newest first; "
                          "nothing below this line is rewritten -->")

_ANNOTATED = ("RESOLVED", "WONTFIX", "VERIFIED", "~~", "FALSE POSITIVE")


def _carried_conflicts(root, conflicts):
    """(lines, carried_count) for the Contradictions section.

    DEFECT 2. This section used to be rebuilt from `conflicts` alone, so a
    human annotation on a previous run's line -- `RESOLVED 2026-09-15`, a
    strike-through, a WONTFIX -- vanished on the next run and the
    contradiction silently re-opened.

    Keyed on the conflict TEXT, not on position: the order of `conflicts`
    follows subsystem iteration and would reshuffle a positional match into
    nonsense. A carried line wins over a regenerated one for the same
    conflict, because the regenerated line is exactly the claim the human
    already answered.

    Nothing is invented: a carried line is text that was in the file, and an
    annotation for a conflict the graph no longer reports is kept too -- it
    records that somebody looked, which outlives the finding.
    """
    previous = []
    path = os.path.join(root, ".crew", "codemap", "UPGRADE.md")
    try:
        with open(path, encoding="utf-8") as fh:
            body = fh.read()
    except OSError:
        body = ""
    if body:
        inside = False
        for line in body.splitlines():
            # T-0065: earlier runs are kept below the marker. Only the newest
            # run is read; an annotation on an older run stays in that run's
            # history and is not carried into the new one.
            if line.strip() == UPGRADE_HISTORY_MARKER:
                break
            if line.startswith("## Contradictions"):
                inside = True
                continue
            if inside and line.startswith("## "):
                break
            if inside and line.strip().startswith("-"):
                previous.append(line)

    annotated = [ln for ln in previous
                 if any(mark in ln for mark in _ANNOTATED)]
    # An annotated line answers the conflict whose text it contains.
    answered = set()
    for ln in annotated:
        for c in conflicts:
            if c in ln:
                answered.add(c)

    out = list(annotated)
    out.extend(f"- {c}" for c in conflicts if c not in answered)
    return (out or ["- none"]), len(annotated)


def _absent_global_headline(notes):
    """The report's FIRST line when this machine has no global config at all.

    Mirrors `crew_config.inspect_global`'s `"absent"` finding -- same test
    (no file at `crew_state.GLOBAL_CONFIG_PATH`), same fact named
    (`pm.authority`'s effective value) -- without importing `crew_config`,
    which this module cannot: see `crew_state.CONTEXT_DEFAULTS`'s comment for
    why the dependency only runs the other way.

    Every OTHER `--check-global` finding (`unreadable`, `missing-keys`,
    `repo-keys`, `inert-schema`) lives in `/crew:config`, which runs
    `crew_config.py --check-global` directly (upgrade.md step 4b went when
    T-0038 folded `/crew:upgrade` into `/crew:migrate`). This is the one
    finding an upgrade run has a stake of its own in, because it is the run
    that just decided whether `pm.authority` survives in the repo file at all
    (see `_prune_unsupplied_global_leaves`) -- worth leading the report with,
    not left in a list a reader has to go to `/crew:config` to see. Returns
    None when a global file exists.
    """
    if crew_state.read_text(crew_state.GLOBAL_CONFIG_PATH) is not None:
        return None
    return (
        f"NO MACHINE-GLOBAL CONFIG at {crew_state.GLOBAL_CONFIG_PATH} -- "
        "every crew repo on this machine falls back to built-in defaults. "
        f"Effective pm.authority for THIS repo: {notes['pmAuthorityAfter']} "
        f"(from {notes['pmAuthorityLayer']}). Run /crew:config to set one."
    )


def _report(status, head, results, notes, root):
    schema_line = (
        f"to schema: {crew_state.SCHEMA_CURRENT}" if notes["schemaStamped"]
        else "schema: NOT stamped — see Config below"
    )
    lines = []
    headline = _absent_global_headline(notes)
    if headline:
        lines.append(headline)
        lines.append("")
    lines.extend([
        "# Upgrade report",
        f"status: {status}",
        schema_line,
        # NOT an `anchor:` line, and deliberately not shaped like one.
        # `_NOT_SUBSYSTEMS` excludes UPGRADE.md from `read_knowledge`, so a
        # line `_ANCHOR_RE` matched would be read by nothing while looking
        # machine-checked. That third state -- anchor-shaped, unreadable, and
        # eventually dead -- is worse than either honest one, and it is the
        # category 0.19.13 did not cover: it made `unresolvable` a reported
        # value of its own, but a line no regex matches cannot be reported at
        # all. This file is a report of one run, not a map that gets
        # re-verified, so it says which graph build it compared against and
        # says plainly that the sha is not an anchor.
        f"graph build compared against: {head or 'unknown'}",
        "  (not an anchor: this file is a one-time report, not a subsystem map,",
        "   and nothing re-verifies it. The sha records what this run read; it",
        "   may not resolve later, and a squash merge is enough to kill it.)",
        "",
        "Nothing below was applied automatically. Conflicts are the map and",
        "the graph disagreeing, and either can be wrong: the graph misses",
        "generated call sites, reflection, and dynamic dispatch.",
        "",
    ])
    lines.extend(_config_lines(notes))
    # `.get`, not `[...]`: `_report` must survive an entry that is not a
    # full result. The shape is fixed at the source above, and this is the
    # belt beside that brace -- a report that raises loses the whole record
    # of a migration that has ALREADY written the new schema.
    conflicts = [c for r in results.values() for c in r.get("conflicts", [])]
    lines.append("## Contradictions — kept in the map, verify by hand")
    # Not `f"- {c}" for c in conflicts or [...]`: that prefixes the fallback
    # too, rendering "- - none". `_carried_conflicts` builds finished lines,
    # including the fallback, and carries any human annotation forward.
    conflict_lines, carried = _carried_conflicts(root, conflicts)
    if carried:
        lines.append(
            f"{carried:d} annotated line(s) carried forward from the "
            "previous report - they are NOT re-derived findings.")
    lines.extend(conflict_lines)
    lines.append("")
    lines.append("## Added by the graph")
    added = [f"- {name}: {len(r['added'])} new line(s)"
             for name, r in sorted(results.items()) if r.get("added")]
    lines.extend(added or ["- none"])
    lines.append("")
    lines.append("## Anchors left stale on purpose")
    stale = [f"- {name} — not re-verified this run"
             for name, r in sorted(results.items()) if not r.get("touched")]
    lines.extend(stale or ["- none"])
    lines.append("")
    return "\n".join(lines) + "\n"


def _umask():
    """The process umask, read without leaving it changed."""
    mask = os.umask(0o022)
    os.umask(mask)
    return mask


def _write_upgrade_report(path, report):
    """Put `report` on top of `path`, keeping the earlier file below the marker.

    T-0065 (item 8): this used to `open(path, "w")` and write the report
    alone, so `--force` erased every earlier run, an unverified contradictions
    list included. The old bytes are read first and kept verbatim (binary, so
    not even a line ending is touched); the whole new file is built in memory,
    written to a pid-named sibling and renamed over the target, so an
    interruption leaves the old file or the new one, never half of either.
    The new report is LF-only on every platform, and keeps the earlier
    file's permission bits (review: the sibling would otherwise carry the
    umask's, widening a 0600 report on rerun)."""
    try:
        with open(path, "rb") as handle:
            old = handle.read()
            mode = os.stat(handle.fileno()).st_mode
    except FileNotFoundError:
        old, mode = b"", None
    data = report.encode("utf-8")
    if old:
        data += b"\n" + UPGRADE_HISTORY_MARKER.encode("utf-8") + b"\n\n" + old
    tmp_path = f"{path}.{os.getpid()}.tmp"
    try:
        # Created private (0600) and given the earlier report's bits before a
        # byte is written, so the old report is never readable through it.
        fd = os.open(tmp_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0),
                     0o600)
        with os.fdopen(fd, "wb") as handle:
            if mode is not None and hasattr(os, "fchmod"):
                os.fchmod(handle.fileno(), stat.S_IMODE(mode))
            elif mode is not None:
                os.chmod(tmp_path, stat.S_IMODE(mode))
            elif hasattr(os, "fchmod"):
                os.fchmod(handle.fileno(), 0o666 & ~_umask())
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, path)
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


def run(root, derived, force=False, accept_dropped=()):
    """Upgrade the repo at `root`. `derived` maps subsystem -> graph sections.

    A dropped key holding a non-default value that `accept_dropped` does not
    name refuses the run (`status` "refused: dropped keys"): nothing is backed
    up or written."""
    cfg_path = os.path.join(root, ".crew", "config.json")
    if not os.path.exists(cfg_path):
        return {"status": "not a crew repo", "report": "", "notes": None,
                "conflicts": []}

    cfg, ok = _read_config_strict(root)
    if not ok:
        # Present but unparseable. Change nothing -- see _read_config_strict.
        return {"status": "config unreadable", "report": "", "notes": None,
                "conflicts": []}
    if crew_state.int_or(cfg.get("schema", 1), 1) >= crew_state.SCHEMA_CURRENT \
            and not force:
        # Already current does not mean "nothing to say". `upgrade_config` is
        # pure, so running it here on a COPY costs nothing on disk -- no
        # write to config.json, no backup, no codemap touch -- and it is the
        # one place that already knows how to compute the absent-global
        # headline and the pinned-at-default list. Without this, a schema-
        # current repo with no machine-global config never heard about either,
        # because both were only ever computed on the write path below.
        _, notes = upgrade_config(copy.deepcopy(cfg), accept_dropped)
        lines = []
        headline = _absent_global_headline(notes)
        if headline:
            lines.append(headline)
            lines.append("")
        lines.extend(_config_lines(notes))
        report = "\n".join(lines) + "\n"
        return {"status": "already current", "report": report,
                "notes": notes, "conflicts": []}

    upgraded, notes = upgrade_config(cfg, accept_dropped)
    if refused_drops(notes):
        report = "\n".join(_config_lines(notes)) + "\n"
        return {"status": "refused: dropped keys", "report": report,
                "notes": notes, "conflicts": []}

    backup_codemap(root)
    backup_config(root)

    # Write a sibling and rename over the target. Opening the live config
    # "w" truncates it first, so an interruption -- a kill, a full disk, a
    # serialization error -- between truncate and the last byte leaves a
    # half-written file, and the NEXT run stops at "config unreadable"
    # rather than retrying. os.replace is atomic on POSIX and on Windows,
    # so the config on disk is only ever the old one or the new one.
    # PID in the name: a fixed `.tmp` races a second upgrade in another
    # session -- both write the same sibling, and the first os.replace
    # removes the shared pathname out from under the second.
    tmp_path = f"{cfg_path}.{os.getpid()}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as handle:
        json.dump(upgraded, handle, indent=2, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    # T-0050: the timestamped backup, beside the one-time `.v1.bak` above.
    # No backup, no write: the upgrade reports and stops with the file as it was.
    try:
        crew_backup.backup(cfg_path)
    except crew_backup.BackupError as exc:
        try:
            os.remove(tmp_path)
        except OSError:
            pass
        return {"status": "config backup failed", "report": f"{exc}\n",
                "notes": notes, "conflicts": []}
    os.replace(tmp_path, cfg_path)

    head = _head(root)
    mapdir = os.path.join(root, ".crew", "codemap")
    results = {}
    for name, sections in (derived or {}).items():
        # The keys come from a JSON file this script is handed, and they are
        # interpolated into a filename. `../../docs/target` as a key wrote
        # outside the codemap entirely, and an absolute Windows path escaped
        # in one hop. A subsystem name is a basename, always -- anything else
        # is skipped rather than sanitised, because a name that needed
        # sanitising was not a subsystem name in the first place.
        if name != os.path.basename(name) or name in ("", ".", ".."):
            # Same SHAPE as a real result, not just the skip reason. This entry
            # used to be `{"skipped": ...}` alone, and `_report` reads
            # `r["conflicts"]`, `r["added"]` and `r["touched"]` from every
            # entry -- so one hostile key raised `KeyError` *after* the schema
            # had already been stamped. The migration half-ran, wrote no
            # report, and a retry then said "already current": a partial
            # upgrade that reports as a finished one, which is strictly worse
            # than failing before it started.
            results[name] = {
                "skipped": "not a plain subsystem name",
                "conflicts": [],
                "added": [],
                "touched": False,
            }
            continue
        path = os.path.join(mapdir, f"{name}.md")
        text = crew_state.read_text(path)
        if text is None:
            continue
        out = graph_reconcile.reconcile(text, sections)
        body = _bump_anchor(out["body"], head) if out["touched"] else out["body"]
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(body)
        results[name] = out

    # A config with a block that could not be migrated is genuinely not
    # current, and `upgrade_config` refused to stamp it. Saying "upgraded"
    # here would be the report claiming work the config itself denies.
    status = ("upgraded with unmigrated blocks" if notes["unmigrated"]
              else "upgraded")
    report = _report(status, head, results, notes, root)
    if os.path.isdir(mapdir):
        _write_upgrade_report(os.path.join(mapdir, "UPGRADE.md"), report)

    return {
        "status": status,
        "report": report,
        "notes": notes,
        "conflicts": [c for r in results.values()
                      for c in r.get("conflicts", [])],
    }


def main(argv=None):
    """CLI entry point. `derived` arrives as a JSON file written by the skill."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", default=os.getcwd())
    parser.add_argument("--derived", help="path to a JSON file of graph facts")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--accept-dropped", action="append", default=[],
                        metavar="KEY",
                        help="let a dropped key that holds a non-default value "
                             "be removed (repeatable)")
    args = parser.parse_args(argv)
    bad = unacceptable_drops(args.accept_dropped)
    if bad:
        parser.error("not a droppable key: " + ", ".join(bad))

    derived = {}
    if args.derived:
        text = crew_state.read_text(args.derived)
        if text:
            try:
                derived = json.loads(text)
            except ValueError:
                derived = {}

    out = run(args.root, derived, force=args.force,
              accept_dropped=args.accept_dropped)
    print(out["status"])
    if out["status"] == "refused: dropped keys":
        print(out["report"], end="", file=sys.stderr)
        return 1
    if out["status"] == "config backup failed":
        print(out["report"], end="", file=sys.stderr)
        return 4
    if out["status"] == "already current":
        # No UPGRADE.md is written on this path (see run()) -- the report
        # exists only in `out`, so this is the only place either diagnostic
        # reaches the user.
        if out["report"]:
            print(out["report"], end="")
        return 0
    notes = out.get("notes")
    if notes:
        if notes["guardProfile"] is not None:
            print(f"guards: profile {notes['guardProfile']}"
                  + (", overrides " + ", ".join(
                      f"{k}={v}" for k, v in sorted(notes["guardOverrides"].items()))
                     if notes["guardOverrides"] else ", no overrides"))
        for label, key in (("removed (default)", "removedDefault"),
                           ("removed (retired)", "retiredRemoved"),
                           ("removed (accepted)", "acceptedDropped")):
            if notes[key]:
                print(f"{label}: " + ", ".join(notes[key]))
        if notes["installKeysAdded"]:
            # A key governing whether crew may RUN INSTALL COMMANDS is squarely
            # in the class the comment above describes, even arriving at its
            # floor. It reached UPGRADE.md and never the terminal, so the one
            # upgrade note a user would most want unprompted was the one they
            # had to go looking for.
            print(f"schema {notes['schemaFrom']} -> "
                  f"{crew_state.SCHEMA_CURRENT}: added "
                  + ", ".join(notes["installKeysAdded"])
                  + " (arrives as 'manual' - crew names a missing skill and its "
                    "command and runs nothing, exactly as before; "
                    "run /crew:config to allow more)")
        if notes["providerKeysAdded"]:
            print(f"schema {notes['schemaFrom']} -> "
                  f"{crew_state.SCHEMA_CURRENT}: added "
                  + ", ".join(notes["providerKeysAdded"])
                  + " (empty/neutral - dispatch is unchanged; "
                    "run /crew:model to pin a model per role)")
        # `installKeysAdded` had no line here at all: schema 5 added
        # `install.policy`, wrote its paragraph into UPGRADE.md, and printed
        # nothing at the CLI -- so a repo with no `.crew/codemap/` (where
        # UPGRADE.md is written) gained a key governing whether crew may run
        # commands on the machine, and said so nowhere the user would see. A
        # filed defect, fixed here rather than repeated for a second list.
        if notes["installKeysAdded"]:
            print(f"schema {notes['schemaFrom']} -> "
                  f"{crew_state.SCHEMA_CURRENT}: added "
                  + ", ".join(notes["installKeysAdded"])
                  + " (arrives as `manual` - crew installs nothing without "
                    "being told; run /crew:config to change it)")
        if notes["guardKeysAdded"]:
            print(f"schema {notes['schemaFrom']} -> "
                  f"{crew_state.SCHEMA_CURRENT}: added "
                  + ", ".join(notes["guardKeysAdded"])
                  + " (empty - the production guards match nothing until you "
                    "declare what production is; run /crew:config)")
        # At the CLI and not only in UPGRADE.md, for the reason the comment
        # above `installKeysAdded` records: a repo with no `.crew/codemap/`
        # writes no UPGRADE.md at all, so a key that decides whether a
        # production promotion can happen would arrive announced nowhere.
        if notes["changeKeysAdded"]:
            print(f"schema {notes['schemaFrom']} -> "
                  f"{crew_state.SCHEMA_CURRENT}: added "
                  + ", ".join(notes["changeKeysAdded"])
                  + " (change.requireForProduction arrives `false` - promote "
                    "asks for no change request, exactly as before. It "
                    "ratchets the OTHER way from the guards: a repo may turn "
                    "it ON, never off. Run /crew:config to set it)")
        if notes["unmigrated"]:
            print("NOT migrated (wrong type, left as written): "
                  + ", ".join(notes["unmigrated"]))
            print("schema was not stamped; fix these and re-run /crew:migrate")
    if out["conflicts"]:
        print(f"{len(out['conflicts'])} conflict(s) - see .crew/codemap/UPGRADE.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

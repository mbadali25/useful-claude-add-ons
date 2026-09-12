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
  * `schema` is stamped current only when every block actually migrated, and
    the run says what it added -- roles and tier included. Both are the same
    rule as the anchor one, applied to the config: never claim the work.
"""

import argparse
import copy
import json
import os
import re
import shutil
import subprocess
import sys

import graph_reconcile

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    os.pardir, os.pardir, os.pardir, "hooks", "scripts",
))
import crew_state  # pylint: disable=wrong-import-position

# Not a second copy of the PM defaults. crew_state owns them because the hook
# reads config on every session start; if an upgrade wrote defaults the hook
# disagreed with, a freshly upgraded repo would behave differently from a
# freshly created one and nothing would say so.
PM_BLOCK = crew_state.PM_DEFAULTS

GRAPH_BLOCK = {
    "enabled": True,
    "tool": "graphify",
    # crew_state owns this default too -- it has to resolve the same directory
    # when no config exists at all.
    "out": crew_state.GRAPH_OUT_DEFAULT,
    "mode": "code-only",
    "commitHook": False,
    # There is deliberately no Obsidian export key here. The graph lives on
    # the filesystem as `graph.json` and nowhere else -- see crew-graph/
    # SKILL.md, "Why there is no Obsidian export". A config written before
    # 0.16.13 may still carry `graph.obsidian`; `upgrade_config` drops it and
    # names it in `notes["droppedKeys"]` rather than migrating it, because
    # there is no longer anything for it to mean.
}

# Which doc-builder brand crew's generated documents are written in.
#
# Lives here rather than in `crew_config` for the same reason `GRAPH_BLOCK`
# does: `CONFIG_BLOCKS` below has to reference it, and `crew_config` imports
# THIS module -- the other direction is the cyclic import `crew_config.
# layered_state` documents.
#
# `theme` is a doc-builder theme-pack skill name. The INTENDED design is that
# it feeds doc-builder's existing selection point rather than a new one -- the
# resolved value passed as `--brand` (or `DOC_BUILDER_BRAND`), the second and
# third rung of `resolve_brand.py`'s precedence.
#
# NOT BUILT AS OF 0.17.0, and this comment claimed otherwise in the present
# tense until 2026-09-12. Nothing in crew reads either key: there is no call
# site, because no crew agent or command invokes doc-builder at all. See
# TODO.md, "Ticket B". Stated plainly here because a comment describing
# unbuilt wiring is why nobody looks for the bug.
#
# `theme` defaults to None, meaning "pass no `--brand` and let doc-builder
# resolve". It shipped as `"neutral"` through 0.17.1, justified by a comment
# claiming "the default resolves to exactly what doc-builder already falls
# back to". That was FALSE, and measurably so: doc-builder falls back to
# neutral only when NO pack is discovered, and with a pack installed it
# resolves THAT pack. On a checkout carrying solomon-doc-builder, default
# resolution returns `solomon`.
#
# So `"neutral"` was never the no-op its author intended. Once the wiring
# lands, passing it would be an explicit instruction that OVERRIDES an
# installed client pack -- an upgrade would silently de-brand a Solomon
# user's documents, with nothing in their config file changed to explain it.
# `None` is what actually implements "the default changes nothing": it only
# ever NARROWS from doc-builder's own behaviour, so pinning a brand becomes
# something the user opts into deliberately.
#
# Both keys' `None` now mean ONE thing -- "I have no answer, ask the next
# authority". For `reportTheme` that authority is `theme`; for `theme` it is
# doc-builder's own five-step resolution. One rule, not two.
#
# `reportTheme` is null meaning "follow `theme`" -- NOT "no theme". A report
# is the one artefact people routinely want in a different brand from the
# docs (a client-facing deliverable out of an internal repo), and spelling
# that as a second full default would make the common case -- one brand for
# everything -- take two settings to state and two to keep in step.
DOCS_BLOCK = {
    "theme": None,
    "reportTheme": None,
}

# The one value `upgrade_config` rewrites in place rather than preserving.
#
# Read the exception before copying it. The standing rule everywhere else in
# this module is that a user's value is carried forward untouched or reported
# as unmigrated -- `dropped`, `unmigrated` and the verbatim wrong-typed block
# all exist to enforce it. This is the single documented exception, and it is
# safe for a reason that does NOT generalise: `docs.theme` has never had a
# consumer. No crew code has ever read it, so no user has ever been able to
# set it and observe an effect, so no existing value can encode a considered
# preference. It is either inherited from a template nobody edited or typed
# with no observable result. There is no third case to preserve.
#
# That is why this is not a violation of the rule. Apply the same reasoning
# before ever adding a second entry here, and if the key in question ever had
# a working consumer, the answer is no.
#
# Residual cost, accepted deliberately: someone who typed `"neutral"` meaning
# it has to retype it once the key works. They get neutral anyway unless a
# pack is installed, so the window where it matters is narrow.
_DOCS_THEME_REWRITTEN_FROM = "neutral"

# The schema at which that rewrite stops. A config arriving at or above this
# has already been migrated once, so a `"neutral"` in it was typed on purpose
# after the fact and is the user's answer, not the old default. Keeping the
# rewrite one-shot is what lets the upgrade report honestly promise that
# setting neutral again will stick.
_DOCS_THEME_REWRITTEN_UNTIL_SCHEMA = 4

# Whether a Bitbucket pull request has to pass crew's merge gate.
#
# `enabled` is false because a gate that arrives switched on would start
# failing merges on a repo whose owner never asked for one; `/crew:promote`
# and the Bitbucket skill are what turn it on.
#
# `branch` is null meaning "ask the API which branch this repo calls main".
# Hardcoding `main` here would be wrong on every repo still on `master` or on
# a Gitflow `develop`, and wrong silently -- the gate would look configured
# and watch a branch nobody merges into.
BITBUCKET_BLOCK = {
    "mergeGate": {
        "enabled": False,
        "branch": None,
        "preset": "standard",
    },
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
_ANCHOR_LINE_RE = re.compile(r"^(anchor:\s*\S*?@?)([0-9a-f]{7,40})(?=\s*$)",
                             re.MULTILINE | re.IGNORECASE)


# The merge policy itself moved to crew_state.merge_defaults so
# crew_config.resolve_config's global/repo layering uses the exact same
# rule as this module's v1->v2 upgrade does, rather than a second
# implementation that could quietly diverge. Kept as a module-level name
# here since both call sites below predate the move and read cleanly as-is.
_merged = crew_state.merge_defaults


_ABSENT = object()

# Every block an upgrade brings forward, and the defaults it brings it onto.
# `qa` and `dev` were missing from this list until 0.16.0, which is the whole
# of the bug: a config predating the 0.14.4 provider table was stamped current
# while still carrying neither.
CONFIG_BLOCKS = (
    ("pm", PM_BLOCK),
    ("graph", GRAPH_BLOCK),
    ("qa", crew_state.QA_DEFAULTS),
    ("dev", crew_state.DEV_DEFAULTS),
    ("worktree", crew_state.WORKTREE_DEFAULTS),
    ("docs", DOCS_BLOCK),
    ("bitbucket", BITBUCKET_BLOCK),
)

# The keys schema 3 introduced. Named here rather than diffed generically so
# the report can SAY what the 2 -> 3 migration added, in the words the user
# will search for. Both are behaviour-neutral on arrival -- `fallback` only
# fires when a pinned model is gone, which previously was an error and not a
# fallback at all, and an EMPTY `roles` table means every role keeps running
# on the block's own `provider`, exactly as it did before.
SCHEMA_3_KEYS = ("qa.fallback", "qa.roles", "dev.fallback", "dev.roles")


def upgrade_config(cfg):
    """Bring a config up to the current schema. Pure.

    Returns `(out, notes)`. `out` preserves every key it does not know about;
    `notes` is what the run has to SAY, and is not optional decoration:

        {"unmigrated": [...], "rolesAdded": [...], "rolesUnknown": [...],
         "tierFrom": int, "tierTo": int, "schemaFrom": int,
         "providerKeysAdded": [...], "schemaStamped": bool}

    Four rules, each of which used to be wrong here:

      * **Every block moves forward, not just `pm` and `graph`.** See
        `CONFIG_BLOCKS`.
      * **`roles` moves forward too, by adding, not by reporting.** A config
        already at tier N gets every ladder role at or below N that it is
        missing -- the roles a later release added at a tier it already
        claimed. An upgrade that made the user re-derive that from a report
        would be the same "a default nobody chose" failure the guided-config
        work exists to close. It cannot grow a crew past the tier the config
        itself declares: a tier-0 repo gains nothing, and `/crew:scale` is
        still the only thing that moves a repo UP the ladder. Removal is not
        the mirror of this and never happens here -- `/crew:pm offboard` keeps
        its explicit-yes gate, because adding a role is reversible and
        removing one destroys the coverage that would have told you whether
        the removal was right.
      * **Schema 3's per-role provider table arrives EMPTY.** `qa.roles` and
        `dev.roles` are added as `{}` and `fallback` as its default value, so
        a v2 config comes out of this dispatching to exactly the provider and
        model it dispatched to before. That is the whole design of the 2 -> 3
        migration: bumping `SCHEMA_CURRENT` makes every crew repo on the
        machine report `upgradeNeeded`, so this migration is mandatory, and a
        mandatory migration that silently re-routed someone's development work
        to a different model would be indefensible. `/crew:upgrade` OFFERS the
        pins afterwards; it never writes them here.
      * **`schema` is stamped only when everything migrated.** A block that
        arrived as the wrong type is left exactly as the user wrote it and
        named in `notes["unmigrated"]`; marking that config current would
        claim work that did not happen, and the next run would skip it.
    """
    out = dict(cfg)
    notes = {"unmigrated": [], "rolesAdded": [], "rolesUnknown": [],
             "tierFrom": 0, "tierTo": 0,
             "schemaFrom": crew_state.int_or(cfg.get("schema", 1), 1),
             "providerKeysAdded": [], "schemaStamped": False,
             # Keys this upgrade removed outright. Distinct from
             # "unmigrated", which blocks the schema stamp: a dropped key is
             # a completed migration, not a failed one.
             "droppedKeys": [],
             # Keys whose VALUE this upgrade changed in place. Same contract
             # as droppedKeys -- a completed migration, announced -- but a
             # strictly heavier claim, because the key survives wearing a
             # value the user did not write. Everything in here must be
             # justified at its definition; see _DOCS_THEME_REWRITTEN_FROM.
             "rewrittenKeys": []}

    for key, block in CONFIG_BLOCKS:
        supplied = cfg.get(key, _ABSENT)
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
        out[key] = merged

    # What schema 3 actually added to THIS config, computed from the incoming
    # file rather than from the version number: a config hand-edited to carry
    # `dev.roles` already must not be reported as having just gained it.
    for dotted in SCHEMA_3_KEYS:
        block_key, leaf = dotted.split(".")
        if _block_untouched(notes, block_key):
            continue
        supplied = crew_state.dict_or_empty(cfg.get(block_key))
        if leaf not in supplied:
            notes["providerKeysAdded"].append(dotted)

    # `graph.obsidian` was removed in 0.16.13. Drop it loudly rather than
    # carrying it forward: a key that survives an upgrade but no longer has a
    # consumer reads, to anyone inspecting the config, as a feature that is
    # merely switched off. Naming it is what tells them it is gone.
    # `out["graph"]` is only a dict when the supplied block was well-typed.
    # A wrong-typed block (`"graph": "oops"`) is kept VERBATIM and reported in
    # `unmigrated` -- popping a key off it raises AttributeError and takes the
    # whole migration down partway, after run() has already written the file.
    if isinstance(out.get("graph"), dict):
        if isinstance(crew_state.dict_or_empty(cfg.get("graph")).get("obsidian"),
                      dict):
            notes["droppedKeys"].append("graph.obsidian")
        out["graph"].pop("obsidian", None)

    # `docs.theme` shipped as `"neutral"` through 0.17.1 on a false premise
    # (see DOCS_BLOCK). Move it to None, which is what "the default changes
    # nothing" actually means now that the key is about to acquire a consumer.
    # Leaving it would hand every upgraded repo an explicit `--brand neutral`
    # that overrides an installed pack -- a behaviour change nobody chose,
    # arriving in a config file that did not visibly change.
    #
    # Only the exact old default is touched. A theme the user actually named
    # (`"solomon"`, `"acme"`) is a value this migration has no business
    # second-guessing, and `None` is already correct.
    #
    # `dict_or_empty` is the type guard, and it is the only one needed. A
    # wrong-typed `docs` block (`docs: "oops"`) is kept VERBATIM and reported
    # in `unmigrated`; `dict_or_empty` turns it into `{}` here, so the
    # comparison is False and `out["docs"]` -- still the user's string -- is
    # never indexed into. Indexing it would raise partway through, after
    # run() had already written the file.
    #
    # Two guards were tried here and both turned out to be unreachable, which
    # is worth recording because the lesson repeated within one change.
    #
    # First an `isinstance(out.get("docs"), dict)` wrapper: sabotaging it left
    # the suite GREEN, because `dict_or_empty` already made it dead. Then
    # `dict_or_empty` itself became unreachable in turn, once `schemaStamped`
    # was added above -- a wrong-typed `docs` block cannot be stamped, so the
    # condition short-circuits before this line is ever evaluated, and
    # sabotaging it went green too.
    #
    # `schemaStamped` is the guard that actually holds, and it is the one the
    # suite mutates. `dict_or_empty` stays as the house idiom for reading a
    # config block, not as protection -- no test claims it, because none can.
    # A vacuous sabotage result is the only thing that told us either time.
    supplied_roles = cfg.get("roles", _ABSENT)
    if supplied_roles is not _ABSENT and not (
            isinstance(supplied_roles, list)
            and all(isinstance(r, str) for r in supplied_roles)):
        notes["unmigrated"].append("roles")
    else:
        current = [] if supplied_roles is _ABSENT else list(supplied_roles)
        declared = crew_state.int_or(cfg.get("tier"), 0)
        # The tier to grant from is the higher of what the config claims and
        # what its own role list already implies -- a config saying tier 0
        # while listing `planner` is at tier 2 whatever the number says.
        entitled = max(declared, crew_state.tier_for_roles(current))
        ladder = crew_state.roles_for_tier(entitled)
        notes["rolesAdded"] = [r for r in ladder if r not in current]
        # `known_role`, not `ROLE_TIERS`: a domain specialist has no tier on
        # purpose and is not an unrecognised name. Reporting it as one would
        # tell a repo that deliberately onboarded `node-developer` that crew
        # has never heard of it, on every single upgrade.
        notes["rolesUnknown"] = [r for r in current
                                 if not crew_state.known_role(r)]
        # Ladder order, then the roles that are not on it: domain specialists
        # this repo opted into, then names crew does not recognise. BOTH are
        # kept, for the same reason -- the user put them there.
        #
        # The specialist half is separate from `rolesUnknown` and easy to lose:
        # while specialists counted as "unknown" they rode along in that list,
        # and the moment they stopped being unknown this line silently dropped
        # every one of them on the next upgrade. A committed test covers it.
        kept_specialists = [r for r in current
                            if r in crew_state.SPECIALIST_ROLES]
        out["roles"] = ladder + kept_specialists + notes["rolesUnknown"]
        notes["tierFrom"] = declared
        notes["tierTo"] = entitled
        out["tier"] = entitled

    if not notes["unmigrated"]:
        out["schema"] = crew_state.SCHEMA_CURRENT
        notes["schemaStamped"] = True

    # The `docs.theme` rewrite, deliberately placed AFTER the stamp and gated
    # on it. Two conditions, and each closes a defect found in review.
    #
    # `schemaStamped` makes the rewrite ATOMIC with the migration it belongs
    # to. It sat above this block first, and then a partly-failed run -- one
    # wrong-typed block anywhere, say `qa: "oops"` -- rewrote the theme while
    # leaving `schema` at 3. The user repairs the block, sets neutral back
    # because they meant it, re-runs, and the rewrite fires a SECOND time on
    # the still-unbumped schema and erases it again. Half a migration that
    # keeps re-applying its own half is worse than one that did nothing.
    #
    # `schemaFrom` is what makes the rewrite one-shot, and what makes the
    # report's promise true. The report tells a user who did mean neutral to
    # set it again and says it will be honoured; without this the rewrite
    # matches on the VALUE, so the next `--force` erases the preference they
    # just restored, and so does every force after that. It costs no new
    # state: a config that has been through this migration is stamped 4, so
    # `"neutral"` seen at 4 can only have been typed deliberately afterwards,
    # which is exactly the value the promise protects.
    #
    # Both caught by Codex in QA review. `dict_or_empty` stays as the type
    # guard -- see the note at `_DOCS_THEME_REWRITTEN_FROM`.
    if (notes["schemaStamped"]
            and notes["schemaFrom"] < _DOCS_THEME_REWRITTEN_UNTIL_SCHEMA
            and crew_state.dict_or_empty(cfg.get("docs")).get("theme")
            == _DOCS_THEME_REWRITTEN_FROM):
        notes["rewrittenKeys"].append("docs.theme")
        out["docs"]["theme"] = None

    return out, notes


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
            ("git", "rev-parse", "--short=7", "HEAD"), cwd=root,
            capture_output=True, text=True, timeout=10, check=False,
            stdin=subprocess.DEVNULL,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return done.stdout.strip() if done.returncode == 0 else None


def _bump_anchor(text, head):
    if not head:
        return text
    return _ANCHOR_LINE_RE.sub(lambda m: m.group(1) + head, text, count=1)


def global_theme_defeats_migration():
    """True when the machine-global config still carries the old theme default.

    The repo migration is not enough on its own, and Codex caught why: repo
    null means "no answer, ask the next authority", and the next authority is
    the GLOBAL file. So a machine whose `~/.claude/crew/config.json` still says
    `docs.theme: "neutral"` resolves to neutral in every repo this migration
    has just "fixed" -- the effective value is unchanged and the repo config
    now looks correct, which is the worse of the two states.

    Reported, never rewritten. A per-repo `/crew:upgrade` silently editing a
    machine-global file would change every OTHER repo on the machine, none of
    which the user was upgrading. That is a cross-scope write nobody asked for,
    so this returns a fact and `_config_lines` tells them what to do with it.

    Best effort by design: a missing, unreadable or non-JSON global file simply
    means "no global answer", which is the same state as no file at all.
    """
    try:
        with open(crew_state.GLOBAL_CONFIG_PATH, encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return False
    return (crew_state.dict_or_empty(crew_state.dict_or_empty(data).get("docs"))
            .get("theme") == _DOCS_THEME_REWRITTEN_FROM)


def _config_lines(notes):
    """The config half of the report: what the migration changed, and what it
    could not. A crew that silently grows is the thing `/crew:scale` exists to
    catch, so the roles it added and the tier it moved are stated every run,
    including when the answer is "none"."""
    lines = ["## Config"]
    if notes["rolesAdded"]:
        lines.append("- roles added: " + ", ".join(notes["rolesAdded"]))
    else:
        lines.append("- roles added: none")
    if notes["tierFrom"] == notes["tierTo"]:
        lines.append(f"- tier: {notes['tierTo']} (unchanged)")
    else:
        lines.append(f"- tier: {notes['tierFrom']} -> {notes['tierTo']}")
    lines.append(
        "- roles are added only up to the tier this config already declares. "
        "Moving UP a tier is `/crew:scale`; removing a role is "
        "`/crew:pm offboard`, which still stops for an explicit yes."
    )
    if notes["droppedKeys"]:
        lines.append(
            "- removed, not migrated: " + ", ".join(notes["droppedKeys"])
            + ". The code graph lives on the filesystem as `graph.json`; the "
            "Obsidian export was withdrawn in 0.16.13 because exporting one "
            "note per node made vaults unusably slow. Nothing to re-enable, "
            "and no setting was silently switched off."
        )
    if global_theme_defeats_migration():
        lines.append(
            "- WARNING: your machine-global config "
            f"(`{crew_state.GLOBAL_CONFIG_PATH}`) still sets "
            "`docs.theme` to \"neutral\", and that is the value this repo now "
            "resolves to. Repo null means \"ask the next authority\", and the "
            "next authority is that file -- so the effective theme did NOT "
            "change here, while this repo's own config now reads as migrated. "
            "Clear it there too if you did not mean it. This upgrade will not "
            "edit it for you: it is machine-global, and every other repo on "
            "this machine would change with it."
        )
    if "docs.theme" in notes["rewrittenKeys"]:
        lines.append(
            "- `docs.theme` was `\"neutral\"` and is now null, which means "
            "\"pass no brand and let doc-builder resolve\". This is the one "
            "value this upgrade rewrites rather than preserving, and it is "
            "safe only because the key has never had a consumer -- no value "
            "in it can be a preference you formed by seeing it work. Had it "
            "been left, the wiring would send an explicit `--brand neutral` "
            "that OVERRIDES an installed brand pack, de-branding documents "
            "that are correctly branded today. If you did mean neutral, set "
            "it again and it will now be honoured."
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
    if notes["rolesUnknown"]:
        lines.append("- kept, not on this release's ladder: "
                     + ", ".join(notes["rolesUnknown"]))
    if notes["unmigrated"]:
        lines.append(
            "- **NOT migrated** (present but the wrong type, left exactly as "
            "written): " + ", ".join(notes["unmigrated"])
            + ". `schema` was deliberately NOT stamped current, so this repo "
            "still reports an upgrade as needed. Fix the block by hand and "
            "run `/crew:upgrade` again."
        )
    lines.append("")
    return lines


def _report(status, head, results, notes):
    schema_line = (
        f"to schema: {crew_state.SCHEMA_CURRENT}" if notes["schemaStamped"]
        else "schema: NOT stamped — see Config below"
    )
    lines = [
        "# Upgrade report",
        f"status: {status}",
        schema_line,
        f"graph anchor: {head or 'unknown'}",
        "",
        "Nothing below was applied automatically. Conflicts are the map and",
        "the graph disagreeing, and either can be wrong: the graph misses",
        "generated call sites, reflection, and dynamic dispatch.",
        "",
    ]
    lines.extend(_config_lines(notes))
    conflicts = [c for r in results.values() for c in r["conflicts"]]
    lines.append("## Contradictions — kept in the map, verify by hand")
    # Not `f"- {c}" for c in conflicts or [...]`: that prefixes the fallback
    # too, rendering "- - none". Build the fallback as the finished line.
    lines.extend((f"- {c}" for c in conflicts) if conflicts else ["- none"])
    lines.append("")
    lines.append("## Added by the graph")
    added = [f"- {name}: {len(r['added'])} new line(s)"
             for name, r in sorted(results.items()) if r["added"]]
    lines.extend(added or ["- none"])
    lines.append("")
    lines.append("## Anchors left stale on purpose")
    stale = [f"- {name} — not re-verified this run"
             for name, r in sorted(results.items()) if not r["touched"]]
    lines.extend(stale or ["- none"])
    lines.append("")
    return "\n".join(lines) + "\n"


def run(root, derived, force=False):
    """Upgrade the repo at `root`. `derived` maps subsystem -> graph sections."""
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
        return {"status": "already current", "report": "", "notes": None,
                "conflicts": []}

    backup_codemap(root)
    backup_config(root)

    upgraded, notes = upgrade_config(cfg)
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
            results[name] = {"skipped": "not a plain subsystem name"}
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
    report = _report(status, head, results, notes)
    if os.path.isdir(mapdir):
        with open(os.path.join(mapdir, "UPGRADE.md"), "w",
                  encoding="utf-8") as handle:
            handle.write(report)

    return {
        "status": status,
        "report": report,
        "notes": notes,
        "conflicts": [c for r in results.values() for c in r["conflicts"]],
    }


def main(argv=None):
    """CLI entry point. `derived` arrives as a JSON file written by the skill."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", default=os.getcwd())
    parser.add_argument("--derived", help="path to a JSON file of graph facts")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args(argv)

    derived = {}
    if args.derived:
        text = crew_state.read_text(args.derived)
        if text:
            try:
                derived = json.loads(text)
            except ValueError:
                derived = {}

    out = run(args.root, derived, force=args.force)
    print(out["status"])
    notes = out.get("notes")
    if notes:
        # Printed at the CLI, not only buried in UPGRADE.md: the roles an
        # upgrade added and the tier it moved are the two things a user must
        # not learn about later by noticing new agents in a dispatch.
        print("roles added: " + (", ".join(notes["rolesAdded"]) or "none"))
        print(f"tier: {notes['tierFrom']} -> {notes['tierTo']}")
        if notes["providerKeysAdded"]:
            print(f"schema {notes['schemaFrom']} -> "
                  f"{crew_state.SCHEMA_CURRENT}: added "
                  + ", ".join(notes["providerKeysAdded"])
                  + " (empty/neutral - dispatch is unchanged; "
                    "run /crew:model to pin a model per role)")
        if notes["unmigrated"]:
            print("NOT migrated (wrong type, left as written): "
                  + ", ".join(notes["unmigrated"]))
            print("schema was not stamped; fix these and re-run /crew:upgrade")
    if out["conflicts"]:
        print(f"{len(out['conflicts'])} conflict(s) - see .crew/codemap/UPGRADE.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

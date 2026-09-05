"""Owns the single definition of a fresh `.crew/config.json`.

Three things read this module and must never disagree with each other:

  * `templates/config.template.json`, the file `/crew:init` copies down when
    setting up a new repo. A committed test (`test_crew_config.py`) asserts
    the template equals `default_config()` byte-for-byte, so drift between
    "what setup writes" and "what this module produces" fails CI instead of
    surfacing months later on someone else's machine.
  * `crew_platform.heal_config`, which calls this when `.crew/` exists but
    `config.json` does not, or is not readable as a config.
  * `skills/crew-setup/SKILL.md`, whose inline JSON is prose for a human
    reading the skill and is a COPY of this module's output, not a second
    definition of it.

The `pm` and `graph` blocks are not hand-copied here either. `pm` comes from
`crew_state.PM_DEFAULTS` -- the same object the SessionStart brief merges a
config's `pm` block onto -- and `graph` comes from `crew_upgrade.GRAPH_BLOCK`,
the same object `/crew:upgrade` merges a v1 config's `graph` block onto. A
freshly created repo and a freshly upgraded one must land on identical
defaults; sourcing both blocks from the modules that already own them is what
makes that true by construction rather than by two authors remembering to
keep three copies in sync.

## Global + repo config layering

This module also owns `resolve_config`, the one place that answers "what is
the EFFECTIVE config" once a machine-global file enters the picture. Three
layers, lowest precedence first: `default_config()`, the machine-global file
at `GLOBAL_CONFIG_PATH` (`~/.claude/crew/config.json`), and the repo's own
`.crew/config.json` -- repo overrides global overrides built-in defaults,
merged recursively with `crew_state.merge_defaults`, the same policy
`crew_upgrade.upgrade_config` uses.

Since 0.16.0 the global layer is PRUNED before it is merged: `filter_global`
keeps only the keys `default_global_config()` models, so a repo-only key
sitting in `~/.claude/crew/config.json` takes effect nowhere. It used to be
inherited by every repo that did not override it, which made setting a vault
path or a `tracker` globally a reasonable-looking mistake that failed
silently. `inspect_global` reports what was dropped.

Only readers that want SETTINGS should call `resolve_config`; use
`crew_config.layered_state`, below, for a full crew-state read.

`schema` is exempted STRUCTURALLY inside `resolve_config` itself, not by
caller discipline -- see that function's docstring. It is a fact about the
repo file's own layout version, not a setting: merging it would make an
unmigrated v1 repo (no `schema` key at all) look current the moment any
global file exists, since both the built-in-defaults layer and a careless
global file can carry the current schema number.

`crew_platform.heal_config` and the `platform-sync` writer are the other
thing that bypasses this module's layering -- they touch only the repo file,
always. The global file is never read for a decision about what to WRITE.

## Writing the global file

`write_global_config` is the one place in crew that writes outside the
repository, and it is reached only from `/crew:config` -- a guided flow that
shows the plan first, because `~/.claude/crew/config.json` is the user's own
configuration and a setup tool that quietly reaches into `~/.claude` is worse
than the problem it fixes. Three properties it enforces in code rather than
in prose: it MERGES (an unknown key in an existing file survives), it refuses
any path outside `default_global_config()` (so a repo fact cannot be written
into a file every repo reads, and `graph.obsidian.confirmed` stays
un-grantable), and it marks a widening of `pm.authority` on both the dry run
and the write.

`explain_config` answers the question the incident behind this work could
not: for every globally-settable key, what is the effective value and WHICH
layer decided it. `inspect_global` is the reporting-only view `/crew:upgrade`
prints.

`model_report` is the third reporting view and the one `/crew:model` prints:
per ROLE, which provider and model back it, which family that speaks as,
whether the self-review guard is barring it, and which fallback is armed.
"""

import argparse
import copy
import json
import os
import shutil
import sys

import crew_state

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    os.pardir, os.pardir, "skills", "crew-graph", "scripts",
))
import crew_upgrade  # pylint: disable=wrong-import-position

# A module attribute, not a baked-in constant used directly everywhere, so a
# test can point it at a scratch file instead of the real machine-wide one.
GLOBAL_CONFIG_PATH = os.path.join(
    os.path.expanduser("~"), ".claude", "crew", "config.json")


def default_config():
    """A fresh, current `.crew/config.json`, as a plain dict.

    Every call builds a new object. A caller that goes on to `json.dump` it,
    or to stamp platform facts into it, must not be able to corrupt a shared
    default for the next caller in the same process -- the same rule
    `crew_upgrade.upgrade_config` follows for its own `GRAPH_BLOCK`.

    Key order matches `skills/crew-setup/SKILL.md`'s prose template, so a
    diff against the committed template file is a diff of VALUES, not of
    reordered keys.
    """
    return {
        "schema": crew_state.SCHEMA_CURRENT,
        "tier": 0,
        "roles": ["explorer", "qa-reviewer"],
        "qa": copy.deepcopy(crew_state.QA_DEFAULTS),
        "dev": copy.deepcopy(crew_state.DEV_DEFAULTS),
        "secondOpinion": {
            "provider": "none",
            "mode": "cli",
            "model": None,
            "keyEnv": "GEMINI_API_KEY",
            "sendsCode": False,
        },
        "tracker": "files",
        "jira": {"project": None},
        "sdp": {
            "portal": None,
            "noteVisibility": "private",
            "closeOnDone": False,
        },
        "obsidian": {
            "vaultPath": None,
            "boardDir": None,
            "board": "Board.md",
            "columns": {
                "backlog": "Backlog",
                "ready": "Ready",
                "inProgress": "In Progress",
                "review": "Review",
                "done": "Done",
            },
        },
        "memory": {"mode": "repo", "vaultPath": None},
        "verifyGate": True,
        "context": {
            "enabled": True,
            "warnAt": 0.8,
            "budgetTokens": None,
            "reserveTokens": 100000,
            "handoffPath": ".work/HANDOFF.md",
            "keepTranscripts": 5,
        },
        "emergency": {
            "standDown": True,
            "ttlMinutes": 120,
            "maxTtlMinutes": 480,
        },
        "notify": {
            "provider": "none",
            "urlEnv": None,
            "tokenEnv": None,
            "chatId": None,
            "events": ["phase", "gate", "waiting"],
        },
        # Left nulled deliberately -- the platform-sync SessionStart hook
        # fills these in on first run and repairs them on every later one.
        # Hand-writing a value here only means it gets overwritten.
        "platform": {
            "os": None,
            "wsl": None,
            "shell": None,
            "windowsHostIp": None,
        },
        "pm": copy.deepcopy(crew_state.PM_DEFAULTS),
        "graph": copy.deepcopy(crew_upgrade.GRAPH_BLOCK),
    }


def default_global_config():
    """A fresh `~/.claude/crew/config.json`, as a plain dict.

    Deliberately NOT `default_config()`, and since 0.16.0 this function is no
    longer only a template: it is the SHAPE the global layer is pruned to
    before it is merged, so anything absent here takes effect nowhere. See
    `filter_global`.

    A global file answers "what is true of this machine and this person"; a
    repo file answers "what is true of this project", and most of the repo
    shape is the second kind. `tracker`, `jira.project`, `obsidian.boardDir`,
    `graph.out`, `verify`, `tier`, `roles` and `platform.*` are facts about
    one checkout. They are omitted, and a global file that carries one anyway
    is now IGNORED rather than inherited -- `inspect_global` reports it,
    because a key that quietly does nothing is worse than one that is
    refused out loud.

    `schema` is omitted for a stronger reason: it is not a setting at all,
    and `resolve_config` exempts it structurally so a global file can never
    make an unmigrated repo look current. A template that shipped it would be
    handing every user the exact value that exemption exists to ignore, which
    reads as a bug in the exemption rather than as the no-op it actually is.
    The exemption stays even though the filter now also drops `schema`: two
    independent guards on the one value a wrong answer would hide.

    What is left is the set whose right answer really is a property of the
    machine or the person:

      * `pm` -- the WHOLE block, not just `authority`. `authority` is the key
        the guided-setup work exists for: a global file with no `pm` block
        silently resolved every repo to `report-only`, a default nobody
        chose. Its siblings are the same kind of fact. How many roles one
        pass may dispatch (`maxDispatches`) is a property of the machine
        doing the dispatching, and how chatty the PM is (`enabled`, `mode`,
        `quietLines`, `maxLines`) is a property of the person reading it --
        neither is a fact about a checkout. `maxDispatches` was inherited
        globally before 0.16.0 and a committed test said so; briefly
        filtering it out was a removal of working capability, and the user
        ruled on 2026-09-05 to put it back.
      * `qa` and `dev` -- which reviewer and which implementer CLI are
        installed here, which model each may use, the per-role pins and the
        declared `fallback`. Provider availability is a machine fact; a repo
        cannot know whether `codex` is on PATH. Global is the DEFAULT, not a
        lock: a repo that wants a different reviewer still overrides it.
      * `secondOpinion` -- same reasoning: a CLI and a key that live on this
        machine, plus `sendsCode`, which is a standing decision by the person
        rather than by the project.
      * `notify` -- the person's own chat, not the project's.
      * `memory` -- BOTH keys. `mode` is here alongside `vaultPath` because
        the user ruled in 2026-09-05's global/repo split that memory is a
        property of the person, not of the checkout: someone who keeps their
        memory in a vault keeps it there everywhere, and making them say so
        once per repo is the friction that produced the split. An earlier
        draft of this docstring argued the opposite and is gone rather than
        left contradicting the code.

    `qa.roles` and `dev.roles` are empty dicts, which `leaf_paths` treats as
    LEAVES -- so the whole per-role table is one settable path and a pin for
    a role this release has never heard of still resolves. That is deliberate:
    the role ladder is open, and a filter that only admitted four hardcoded
    role names would silently drop the fifth.

    Key order follows `default_config()` so a diff between the two templates
    reads as "what the global one leaves out" rather than as a reordering.
    """
    return {
        "qa": copy.deepcopy(crew_state.QA_DEFAULTS),
        "dev": copy.deepcopy(crew_state.DEV_DEFAULTS),
        "secondOpinion": {
            "provider": "none",
            "mode": "cli",
            "model": None,
            "keyEnv": "GEMINI_API_KEY",
            "sendsCode": False,
        },
        "memory": {"mode": "repo", "vaultPath": None},
        "notify": {
            "provider": "none",
            "urlEnv": None,
            "tokenEnv": None,
            "chatId": None,
            "events": ["phase", "gate", "waiting"],
        },
        "pm": copy.deepcopy(crew_state.PM_DEFAULTS),
    }


def leaf_paths(node, prefix=()):
    """Every dotted path to a non-dict value in `node`, in declaration order.

    A list is a leaf: `qa.order` and `notify.events` are single settings that
    are replaced wholesale, not blocks to descend into.
    """
    out = []
    for key, value in node.items():
        here = prefix + (key,)
        if isinstance(value, dict) and value:
            out.extend(leaf_paths(value, here))
        else:
            out.append(".".join(here))
    return out


def _prune(node, template, prefix=()):
    """`node` kept only where `template` has a matching key. Returns
    `(kept, ignored)`, `ignored` being the dotted paths that were dropped."""
    kept, ignored = {}, []
    for key, value in node.items():
        here = prefix + (key,)
        if not isinstance(template, dict) or key not in template:
            ignored.append(".".join(here))
            continue
        sub = template[key]
        if isinstance(sub, dict) and sub and isinstance(value, dict):
            inner, dropped = _prune(value, sub, here)
            kept[key] = inner
            ignored.extend(dropped)
        else:
            # A template LEAF -- including an empty dict such as `dev.roles`,
            # which is an open table whose keys crew does not enumerate. The
            # supplied subtree is kept verbatim. A scalar landing where the
            # defaults hold a block is kept too: `merge_defaults` discards it
            # and `_layer_supplies` already reports that correctly, so
            # dropping it here would only move the same no-op earlier and
            # report it as the wrong kind of mistake.
            kept[key] = value
    return kept, ignored


def filter_global(global_cfg):
    """The global layer, pruned to the keys a global file may actually set.

    Returns `(kept, ignored)`. This is the 2026-09-05 global/repo split, in
    code: **a repo-only key in the global file takes effect NOWHERE.** Before
    it, a global `tracker` or `graph.obsidian.dir` was inherited by every repo
    that did not override it, so setting a vault path once quietly gave every
    repository on the machine a board that did not describe it. That is a
    reasonable-looking mistake that failed silently, which is the worst
    combination available.

    The shape it prunes to is `default_global_config()` -- the same object
    `plan_global_write` refuses paths against, so the invariant holds in one
    sentence: **what the global file may WRITE is exactly what the global
    layer may SUPPLY.** Two rules, one definition.

    `ignored` is not decoration. `inspect_global` prints it, and
    `/crew:upgrade` and `/crew:config` read it out, because a key that
    silently does nothing is worse than one that is refused out loud.
    """
    return _prune(global_cfg, default_global_config())


def is_global_path(dotted):
    """True when `dotted` is a path a global file may set.

    Agrees with `filter_global` by construction, including on the open tables:
    a path stops being checked once it reaches a template LEAF, so
    `dev.roles.developer.provider` is allowed because `dev.roles` is one.
    """
    node = default_global_config()
    for part in dotted.split("."):
        if not isinstance(node, dict):
            return True          # already under a leaf; the rest is its business
        if not node:
            return True          # an open table, e.g. `dev.roles`
        if part not in node:
            return False
        node = node[part]
    return True


def read_global_config(path=None):
    """The machine-global crew config, or `{}` when absent, malformed, or not
    a JSON object.

    `path` defaults to `GLOBAL_CONFIG_PATH`; pass it explicitly in a test
    rather than monkeypatching the module attribute mid-call, since
    `resolve_config` reads the attribute itself and a stale local reference
    would not see a patch applied after import.

    Never raises. `resolve_config` is reached from a SessionStart hook by way
    of `crew_state.collect`, and a broken global file must look exactly like
    no global file at all -- the same reasoning `crew_upgrade.
    _read_config_strict` documents for "absent" on the repo side. Unlike the
    repo file, a broken global file is never backed up or rewritten here;
    nothing in this module ever writes it.
    """
    text = crew_state.read_text(GLOBAL_CONFIG_PATH if path is None else path)
    if text is None:
        return {}
    try:
        parsed = json.loads(text)
    except ValueError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def resolve_config(root):
    """The effective config for the repo at `root` -- see the module
    docstring's "Global + repo config layering" section for the precedence
    rule.

    The global layer is PRUNED by `filter_global` before it is merged, so a
    repo-only key sitting in the machine-global file takes effect nowhere
    rather than being inherited by every repo that does not override it. What
    survives the prune is still only a DEFAULT: the repo layer overrides it as
    it always did.

    `schema` is exempted STRUCTURALLY, not by caller discipline: it always
    comes from the repo file's own raw value, present or absent, exactly as
    `crew_state.load_config` reports it -- global can never supply it, and
    neither can the built-in-defaults layer, which otherwise always carries
    `SCHEMA_CURRENT`. Reading `schema` from an earlier draft of this
    function's result meant a global config carrying `{"schema": 2}` would
    leak into an unmigrated v1 repo's resolved config and hide the fact that
    it needs `/crew:upgrade` -- correct only for as long as every caller
    remembered to read the repo file directly instead. This function now
    enforces it once, here, so no caller can get it wrong.

    Never raises: `crew_state.load_config` and `read_global_config` each
    already collapse "malformed" to "absent" on their own, so a broken file
    at either layer contributes nothing to the merge rather than failing the
    whole resolution.
    """
    repo_cfg = crew_state.load_config(root)
    global_cfg, _ = filter_global(read_global_config())
    merged = crew_state.merge_defaults(default_config(), global_cfg)
    merged = crew_state.merge_defaults(merged, repo_cfg)
    if "schema" in repo_cfg:
        merged["schema"] = repo_cfg["schema"]
    else:
        merged.pop("schema", None)
    return merged


def layered_state(root):
    """`crew_state.collect(root)`, with settings layered per `resolve_config`
    wherever the repo is already crew-managed.

    Composing "what is the repo's raw state" (`crew_state.collect`, which
    this module already depends on for `PM_DEFAULTS` and `SCHEMA_CURRENT`)
    with "what is the effective config" (`resolve_config`, above) has to
    happen up here, not inside `crew_state.collect` itself -- `crew_state`
    must not import this module, or the two modules import each other, a
    real cyclic import rather than a stylistic one. `collect` takes the
    resolved config as a plain `cfg_override` argument instead; it ignores
    the override for anything it does not recognise as crew-managed, so
    computing `resolve_config` here unconditionally costs nothing on a plain
    repo and needs no `isCrew` check of its own.

    Every caller that wants a config-layered brief -- `pm_brief.py`, and
    anything else that would otherwise call `crew_state.collect` directly --
    should call this instead.
    """
    return crew_state.collect(root, cfg_override=resolve_config(root))


# --- Where did this value come from? ---------------------------------------


def _dig(node, parts):
    """`node` walked down `parts`, or `_MISSING` if the walk runs out."""
    for part in parts:
        if not isinstance(node, dict) or part not in node:
            return _MISSING
        node = node[part]
    return node


_MISSING = object()


def _layer_supplies(layer, parts, defaults):
    """True when `layer` is the one that decides the value at `parts`.

    Mirrors `crew_state.merge_defaults` rather than re-asking the merged
    result, because the merged result cannot tell you WHERE a value came
    from -- and "where is this coming from" is the question the `pm`
    incident could not answer. The one rule that is easy to get wrong is
    merge_defaults' discard: a scalar supplied where the default holds a
    dict is thrown away, so the layer did NOT supply it.
    """
    node_layer, node_def = layer, defaults
    for index, part in enumerate(parts):
        if not isinstance(node_layer, dict) or part not in node_layer:
            return False
        next_layer = node_layer[part]
        next_def = node_def.get(part) if isinstance(node_def, dict) else None
        if index == len(parts) - 1:
            # Last hop: a scalar over a dict default is discarded.
            return not (isinstance(next_def, dict) and not isinstance(next_layer, dict))
        if not isinstance(next_def, dict):
            # No dict default here, so the layer replaced the whole subtree.
            return True
        if not isinstance(next_layer, dict):
            return False        # discarded before we could reach the leaf
        node_layer, node_def = next_layer, next_def
    return False


def explain_config(root, path=None):
    """Every globally-settable key, with its effective value and its source.

    Returns a list of `{"path", "value", "source"}` in template order, where
    `source` is `"repo"`, `"global"` or `"default"`. Scoped to the keys
    `default_global_config()` covers on purpose: those are exactly the keys a
    walkthrough can offer to write, and a full dump of forty leaves would bury
    the four that anyone is actually asking about.

    The global layer is pruned by `filter_global` first, exactly as
    `resolve_config` prunes it. Explaining an effective value from a layer the
    resolver would have discarded is how a source column comes to name a key
    that does nothing.
    """
    defaults = default_config()
    repo_cfg = crew_state.load_config(root)
    global_cfg, _ = filter_global(read_global_config(path))
    resolved = crew_state.merge_defaults(
        crew_state.merge_defaults(defaults, global_cfg), repo_cfg)

    rows = []
    for dotted in leaf_paths(default_global_config()):
        parts = tuple(dotted.split("."))
        if _layer_supplies(repo_cfg, parts, defaults):
            source = "repo"
        elif _layer_supplies(global_cfg, parts, defaults):
            source = "global"
        else:
            source = "default"
        value = _dig(resolved, parts)
        rows.append({
            "path": dotted,
            "value": None if value is _MISSING else value,
            "source": source,
        })
    return rows


# --- What is wrong with the global file? -----------------------------------


def inspect_global(root, path=None):
    """Findings about the machine-global config, for `/crew:upgrade` to report.

    Reporting only. Nothing here writes, and nothing here decides -- `upgrade.
    md` §5 is "Report — do not resolve", and the global file is the user's own
    configuration outside the repo, which is the strongest version of that
    rule this plugin has.

    Returns `{"path", "exists", "readable", "findings": [...]}`, each finding
    a `{"kind", "detail"}`. Callers should print every finding; the list is
    ordered from "the file is not there" outwards.
    """
    real_path = GLOBAL_CONFIG_PATH if path is None else path
    raw = crew_state.read_text(real_path)
    global_cfg = read_global_config(real_path)
    findings = []

    if raw is None:
        findings.append({
            "kind": "absent",
            "detail": (
                f"no global config at {real_path} -- every crew repo on this "
                "machine falls back to built-in defaults, including "
                f"pm.authority: {crew_state.AUTHORITY_DEFAULT}"
            ),
        })
    elif not global_cfg:
        # Present but it did not parse as a JSON object, or it parsed as an
        # empty one. read_global_config already collapsed both to {}, which is
        # right for resolution and wrong to stay silent about here.
        findings.append({
            "kind": "unreadable",
            "detail": (
                f"{real_path} exists but did not read as a JSON object, so it "
                "contributes nothing -- exactly as if it were absent"
            ),
        })

    template = default_global_config()
    if raw is not None and global_cfg:
        missing = [p for p in leaf_paths(template)
                   if not _layer_supplies(global_cfg, tuple(p.split(".")),
                                          default_config())]
        if missing:
            findings.append({
                "kind": "missing-keys",
                "detail": "not set globally, so the built-in default applies: "
                          + ", ".join(missing),
            })
        # Every dropped path, not just the stray TOP-LEVEL keys an earlier
        # version listed: `graph.obsidian.dir` under an otherwise-plausible
        # `graph` block is the exact mistake this finding exists to name, and
        # a top-level diff cannot see it. `schema` has its own finding below
        # and is left out here so it is reported once rather than twice.
        _, ignored = filter_global(global_cfg)
        stray = sorted(p for p in ignored if p != "schema")
        if stray:
            findings.append({
                "kind": "repo-keys",
                "detail": (
                    "keys a global file may not set, mostly because they "
                    "describe a repository rather than this machine: "
                    + ", ".join(stray)
                    + " -- these are IGNORED. The global layer is filtered to "
                    "machine-and-person keys before it is merged, so nothing "
                    "here reaches any repo; set the repo ones in that repo's "
                    ".crew/config.json instead"
                ),
            })
        if "schema" in global_cfg:
            findings.append({
                "kind": "inert-schema",
                "detail": (
                    "carries `schema`, which never takes effect: it is read "
                    "from the repo file alone so a global value cannot make "
                    "an unmigrated repo look current"
                ),
            })

    authority = [r for r in explain_config(root, real_path)
                 if r["path"] == "pm.authority"]
    if authority:
        row = authority[0]
        findings.append({
            "kind": "authority",
            "detail": (
                f"effective pm.authority for this repo: {row['value']} "
                f"(from {row['source']})"
            ),
        })

    return {
        "path": real_path,
        "exists": raw is not None,
        "readable": bool(global_cfg),
        "findings": findings,
    }


# --- What actually backs each role -----------------------------------------


def order_candidates(cfg, author, which=None, probe=None):
    """Which of `qa.order` could actually review a diff `author` wrote. Pure.

    The per-role table answers "what is each role pinned to". It does NOT
    answer the question a reader with four BARRED rows in front of them
    actually has, which is *what runs instead*. `/crew:review` does not stop
    when a pin is barred -- it walks `qa.order` for a provider whose family is
    not the author's -- so a report that states the bar and omits the
    fall-through has told the reader the alarming half and withheld the
    useful one. The pre-0.16.0 command printed a `NO INDEPENDENT REVIEWER`
    line for exactly this; losing it to a prettier table would be a
    regression.

    One entry per provider in `qa.order`, in order, each
    `{"provider", "model", "family", "onPath", "eligible", "why"}`. `why` is
    None when the candidate is eligible and otherwise names the single reason
    it is not, in the order the walk itself would find them: absent from PATH,
    then family unknown, then same family as the author, then a failed probe.
    A `copilot` with no `qa.copilot.model` has NO knowable family -- that is
    why the walkthroughs insist on pinning it before Copilot may review at all.

    **Being on PATH is not being able to review.** An installed CLI that is
    logged out, rate-limited or disabled by policy resolves on PATH and then
    fails at the first call, so presence alone must never be reported as an
    independent reviewer. With no `probe`, this answers the question it can
    actually answer -- "is a differently-familied candidate installed" -- and
    `probed` on each row is False so a caller can say which it got.
    `probe(provider, model)` returning False marks the candidate ineligible;
    supply one wherever the answer is about to be trusted, as `/crew:review`
    does with its real round trip.
    """
    which = shutil.which if which is None else which
    # `author` is a single family, an iterable of them, or None -- plural
    # because a stale dispatch record strikes two. See
    # `crew_state.author_families`.
    if author is None:
        authors = frozenset()
    elif isinstance(author, str):
        authors = frozenset([author])
    else:
        authors = frozenset(f for f in author if f)
    block = crew_state.dict_or_empty(crew_state.dict_or_empty(cfg).get("qa"))
    out = []
    for provider in block.get("order") or []:
        sub = crew_state.dict_or_empty(block.get(provider))
        model = sub.get("model")
        fam = crew_state.family(provider, model)
        on_path = True if provider == "claude" else bool(which(provider))
        if not on_path:
            why = "not on PATH"
        elif fam is None:
            why = f"no `qa.{provider}.model` pinned, so its family is unknown"
        elif fam in authors:
            why = f"speaks as the `{fam}` family, which wrote this diff"
        elif probe is not None and not probe(provider, model):
            why = "on PATH but its probe failed -- installed, not usable"
        else:
            why = None
        out.append({"provider": provider, "model": model, "family": fam,
                    "onPath": on_path, "probed": probe is not None,
                    "eligible": why is None, "why": why})
    return out


def model_report(root, which=None):
    """Per-ROLE effective provider, model and family, for `/crew:model`.

    One row per role, not one row per block. `qa` used to be reported as a
    single line reading `auto / (cli default)`, which named neither the model
    that would run nor the candidates that would be passed over -- the one
    thing the reader came for. A per-role table is the same argument one level
    down: `qa.roles.review` and `qa.roles.smoke` can now be different models
    from different families, and a block-level row hides that entirely.

    Returns:

        {"authorFamily", "authorSource", "dispatch", "qaOrder", "onPath",
         "dev": [row, ...], "qa": [row, ...]}

    Each row is `crew_state.resolve_role`'s dict plus a `display` field. The
    `qa` rows are resolved WITH the author family, so the family guard is
    already applied to them -- guard first, pin second, exactly as
    `resolve_role` documents. The `dev` rows are resolved without one: the
    guard governs who may REVIEW, and barring an implementer from writing its
    own code would be a different rule nobody asked for.

    `which` defaults to `shutil.which`; a test passes its own. Presence on
    PATH is reported, never treated as working auth -- `/crew:model` step 1
    says to make one real call before anyone decides anything on it.
    """
    which = shutil.which if which is None else which
    cfg = resolve_config(root)
    authors, author_source = crew_state.author_families(root, cfg)

    def rows(kind, names, author_for_guard):
        block = crew_state.dict_or_empty(cfg.get(kind))
        pinned = crew_state.dict_or_empty(block.get("roles"))
        # Every role this release names, plus any the user pinned that it does
        # not -- a pin for a role crew has never heard of still resolves, and
        # leaving it out of the report is how it goes unnoticed.
        every = list(names) + [r for r in pinned if r not in names]
        out = []
        for role in every:
            row = crew_state.resolve_role(cfg, kind, role,
                                          author=author_for_guard)
            row["display"] = (crew_state.display_model(row["model"])
                              or ("n/a (subagent)" if row["provider"] == "claude"
                                  else "(cli default)"))
            out.append(row)
        return out

    candidates = order_candidates(cfg, authors, which)
    return {
        "authorFamily": ", ".join(sorted(authors)) or None,
        "authorFamilies": sorted(authors),
        "authorSource": author_source,
        "dispatch": crew_state.read_dispatch(root).get("dev"),
        "branch": crew_state.current_branch(root),
        "qaOrder": crew_state.dict_or_empty(cfg.get("qa")).get("order") or [],
        # The RESOLVED per-provider blocks, so a caller never has to reopen
        # .crew/config.json to find one. `qaFallThrough` only covers providers
        # named in `qa.order`, and `qa.provider` may name one that is not in
        # it -- reading the raw repo file to recover that was the bug this
        # whole key exists to remove, because that file is one layer of three.
        "qaProviders": {
            name: {
                "model": crew_state.dict_or_empty(
                    crew_state.dict_or_empty(cfg.get("qa")).get(name)
                ).get("model"),
                "reasoningEffort": crew_state.dict_or_empty(
                    crew_state.dict_or_empty(cfg.get("qa")).get(name)
                ).get("reasoningEffort"),
            }
            for name in ("codex", "copilot", "claude")
        },
        "onPath": {tool: bool(which(tool)) for tool in ("codex", "copilot")},
        "dev": rows("dev", crew_state.DEV_ROLE_KINDS, None),
        "qa": rows("qa", crew_state.QA_ROLE_KINDS, authors),
        "qaFallThrough": candidates,
        # The conclusion, not the evidence. False means every candidate in
        # `qa.order` is unreachable or same-family, which is the one state
        # `/crew:review` cannot fix by trying harder.
        #
        # True is the WEAKER claim of the two: with no probe supplied it means
        # "a differently-familied candidate is installed", not "a review can
        # run". `independentReviewerProbed` says which of those was measured,
        # so a caller never has to guess whether presence was mistaken for
        # capability.
        "independentReviewer": any(c["eligible"] for c in candidates),
        "independentReviewerProbed": all(c["probed"] for c in candidates)
                                     and bool(candidates),
    }


_ORIGINS = {
    "dispatch": "recorded at dispatch",
    "config": ("READ FROM CONFIG - no dispatch recorded, so this describes "
               "the NEXT run, not the diff in front of you"),
    # Fail closed, and say which two were struck. See
    # `crew_state.author_families` and `commands/review.md`.
    "stale": ("STALE RECORD - the dispatch was made on a different branch, "
              "so BOTH the recorded family and the config family are struck"),
}


def _print_models(report):
    origin = _ORIGINS.get(report["authorSource"], report["authorSource"])
    print(f"author family: {report['authorFamily'] or 'unknown'}  ({origin})")
    if report["dispatch"]:
        job = report["dispatch"]
        print(f"last dev dispatch: role={job.get('role')} "
              f"provider={job.get('provider')} model={job.get('model')} "
              f"branch={job.get('branch') or '(not recorded)'} "
              f"| current branch={report['branch'] or '(none)'}")
    print()
    for kind in ("dev", "qa"):
        print(f"{kind + ' role':<28}{'provider':<10}{'model':<32}"
              f"{'family':<9}{'source':<14}status")
        print("-" * 118)
        for row in report[kind]:
            status = "eligible"
            if row["barred"]:
                status = f"BARRED - same `{row['barredBy']}` family as the author"
            elif row["provider"] == "auto":
                status = "walks qa.order"
            print(f"{row['role']:<28}{row['provider']:<10}"
                  f"{str(row['display']):<32}{str(row['family'] or '-'):<9}"
                  f"{row['source']:<14}{status}")
            print(f"{'':<28}fallback armed: {row['fallback']}")
        print()
    # What runs when a pin above is barred. Never print the bars without
    # this: `/crew:review` walks `qa.order` rather than stopping, and a
    # report that names the bar and not the fall-through is the half the
    # reader cannot act on.
    print("qa.order fall-through -- what reviews a "
          f"`{report['authorFamily'] or 'unknown'}`-authored diff:")
    if not report["qaFallThrough"]:
        print("  (qa.order is empty)")
    for cand in report["qaFallThrough"]:
        verdict = "ELIGIBLE" if cand["eligible"] else f"no - {cand['why']}"
        print(f"  {cand['provider']:<10}"
              f"{str(crew_state.display_model(cand['model']) or '-'):<32}"
              f"{str(cand['family'] or '-'):<9}{verdict}")
    if report["independentReviewer"]:
        first = next(c for c in report["qaFallThrough"] if c["eligible"])
        print(f"  -> `{first['provider']}` answers for any role barred above.")
    else:
        print("\nNO INDEPENDENT REVIEWER -- every candidate is unreachable or "
              "speaks as the family that wrote the diff. /crew:review falls "
              "back to the qa-reviewer subagent and LABELS the result "
              "same-family. It runs; it does not count as an independent "
              "review.")
    print()
    for tool, found in report["onPath"].items():
        print(f"{tool:<10}{'on PATH' if found else 'NOT FOUND'}")
    print("\nPATH is not working auth. Make one real call per configured "
          "provider before deciding anything on this.")


# --- Writing the global file -----------------------------------------------


class GlobalWriteRefused(Exception):
    """A requested global write named a key the walkthrough may not set."""


def _set_path(target, parts, value):
    node = target
    for part in parts[:-1]:
        nxt = node.get(part)
        if not isinstance(nxt, dict):
            nxt = {}
            node[part] = nxt
        node = nxt
    node[parts[-1]] = value


def plan_global_write(updates, path=None):
    """What writing `updates` to the global file would change. Pure.

    `updates` is a flat `{"pm.authority": "act"}` mapping. Returns
    `(merged, changes)` where `changes` is a list of
    `{"path", "before", "after", "widens_authority"}` for the entries that
    would actually differ.

    Two rules enforced here rather than in prose:

      * **Merge, never replace.** The existing file is the base and every key
        it carries that `updates` does not name survives byte-for-byte,
        including keys this module has never heard of. A walkthrough that
        asks about six settings must not cost a user the seventh.
      * **Only globally-meaningful keys.** A path outside
        `default_global_config()` is refused by name, using the same
        `is_global_path` predicate `filter_global` prunes the READ layer with
        -- what the global file may write is exactly what the global layer may
        supply. That keeps `tracker`, `jira.project` and `graph.out` out of a
        file every repo reads, and it is what makes
        `graph.obsidian.confirmed` structurally un-grantable from here: it is
        consent to write into the user's own notes outside the repo, not a
        capability, so no guided flow can hand it over. Since 0.16.0 that flag
        is doubly un-grantable -- refused on the write path here, and dropped
        on the read path by `filter_global` even if some other tool wrote it.
    """
    refused = [p for p in updates if not is_global_path(p)]
    if refused:
        allowed = sorted(leaf_paths(default_global_config()))
        raise GlobalWriteRefused(
            "not settable in the machine-global config: "
            + ", ".join(sorted(refused))
            + f" (allowed: {', '.join(allowed)})"
        )

    merged = copy.deepcopy(read_global_config(path))
    changes = []
    for dotted, value in updates.items():
        parts = dotted.split(".")
        before = _dig(merged, parts)
        if before is not _MISSING and before == value:
            continue
        changes.append({
            "path": dotted,
            "before": None if before is _MISSING else before,
            "after": value,
            # Never silently. `pm.authority` is the one key whose wrong value
            # the user cannot recover from by noticing -- they either get
            # agents they did not ask for or a report where they expected
            # work -- so a widening is marked, printed on the dry run, and
            # printed again on the write.
            "widens_authority": (
                dotted == "pm.authority"
                and crew_state.normalise_authority(value) == "act"
                and crew_state.normalise_authority(
                    None if before is _MISSING else before) != "act"
            ),
        })
        _set_path(merged, parts, value)
    return merged, changes


def write_global_config(updates, path=None):
    """Apply `plan_global_write` to disk. Returns `(merged, changes)`.

    Creates `~/.claude/crew/` if it is not there. This is the ONLY function in
    crew that writes outside the repo, and it is reached only from a flow that
    has shown the user the plan and been told to go ahead -- see
    `commands/config.md`.
    """
    real_path = GLOBAL_CONFIG_PATH if path is None else path
    merged, changes = plan_global_write(updates, real_path)
    if not changes:
        return merged, changes
    parent = os.path.dirname(real_path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(real_path, "w", encoding="utf-8") as handle:
        json.dump(merged, handle, indent=2)
        handle.write("\n")
    return merged, changes


# --- CLI -------------------------------------------------------------------


def _print_explain(rows):
    width = max((len(r["path"]) for r in rows), default=4)
    print(f"{'key'.ljust(width)}  source    value")
    for row in rows:
        print(f"{row['path'].ljust(width)}  {row['source'].ljust(8)}  "
              f"{json.dumps(row['value'])}")
    # Say what this table is NOT, or it reads as the whole resolved config and
    # a reader concludes their `tracker` or `jira.project` is unset.
    print()
    print("These are the keys the global file may set, not the whole config: "
          "a repo")
    print("also sets tracker, jira, platform, graph, tier and roles in "
          ".crew/config.json.")


def main(argv=None):
    """Report the config layering, or write the global file.

    Reporting exits 0 even when it has findings: a machine with no global
    config is a normal machine, and `/crew:upgrade` reads this output rather
    than its status. Exit 2 is reserved for a usage error or a refused write.
    """
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", default=os.getcwd())
    parser.add_argument("--global-path", default=None,
                        help="override ~/.claude/crew/config.json (testing)")
    parser.add_argument("--explain", action="store_true",
                        help="every globally-settable key, value and source")
    parser.add_argument("--check-global", action="store_true",
                        help="findings about the machine-global config")
    parser.add_argument("--models", action="store_true",
                        help="per-role provider, model, family and fallback")
    parser.add_argument("--set", action="append", default=[], metavar="PATH=JSON",
                        help="a global key to set, e.g. pm.authority='\"act\"'")
    parser.add_argument("--apply", action="store_true",
                        help="actually write; without it --set is a dry run")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    if args.set:
        updates = {}
        for item in args.set:
            if "=" not in item:
                print(f"--set expects PATH=JSON, got: {item}", file=sys.stderr)
                return 2
            key, raw = item.split("=", 1)
            try:
                updates[key.strip()] = json.loads(raw)
            except ValueError:
                updates[key.strip()] = raw      # a bare string is fine
        try:
            if args.apply:
                _, changes = write_global_config(updates, args.global_path)
            else:
                _, changes = plan_global_write(updates, args.global_path)
        except GlobalWriteRefused as exc:
            print(str(exc), file=sys.stderr)
            return 2
        verb = "wrote" if args.apply else "would write (dry run)"
        target = GLOBAL_CONFIG_PATH if args.global_path is None else args.global_path
        print(f"{verb}: {target}")
        for change in changes or []:
            print(f"  {change['path']}: {json.dumps(change['before'])} -> "
                  f"{json.dumps(change['after'])}")
            if change["widens_authority"]:
                print("  ! pm.authority widens to `act`: the PM will dispatch "
                      "roles itself and report after. Removal, deletion and "
                      "offboarding still stop for an explicit yes.")
        if not changes:
            print("  nothing to change")
        return 0

    if args.models:
        report = model_report(args.root)
        if args.json:
            print(json.dumps(report, indent=2))
        else:
            _print_models(report)
        return 0

    if args.check_global:
        report = inspect_global(args.root, args.global_path)
        if args.json:
            print(json.dumps(report, indent=2))
        else:
            print(f"global config: {report['path']}")
            for finding in report["findings"]:
                print(f"- [{finding['kind']}] {finding['detail']}")
        return 0

    rows = explain_config(args.root, args.global_path)
    if args.json or not args.explain:
        print(json.dumps(rows, indent=2))
    else:
        _print_explain(rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

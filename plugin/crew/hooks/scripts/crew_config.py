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


# The provider names crew RECOGNISES, split by what the role decides.
#
# Canonical in `crew_state`, not here: `crew_state.resolve_role`'s read-side
# guard needs to know which names are legitimate, and `crew_state` must not
# import this module (see this module's own docstring), so the tuples live
# where the guard can see them and this module aliases them rather than
# keeping a second copy that could drift. See `crew_state`'s comment above
# `DEV_PROVIDERS` for the reasoning behind the split. Kept under these same
# names because `/crew:model`'s CLI, this module's own callers, and the test
# suite already spell it `crew_config.DEV_PROVIDERS` / `crew_config.
# QA_PROVIDERS`.
#
# Not silently dropped -- `validate_providers` raises and names the key,
# because crew's gates fail OPEN against a provider name nothing resolves,
# and an unrecognised name in `qa.order` is a rung the selector walks past
# without a word. `resolve_role` and `order_candidates` enforce the same
# refusal on the READ side, so a hand-edited config -- one `/crew:model`
# never wrote -- cannot reach the review gate through the one path
# `validate_providers` does not sit in front of.
DEV_PROVIDERS = crew_state.DEV_PROVIDERS
QA_PROVIDERS = crew_state.QA_PROVIDERS

# Providers that are a CLI on PATH, and so have a meaningful `which()` answer.
# `claude` is an in-session subagent, not a binary. `localgpu` is a binary but
# is deliberately NOT on PATH -- see `localgpu_which`.
PATH_PROVIDERS = ("codex", "copilot")


def localgpu_which(which=None):
    """Absolute path to the `localgpu` CLI, or None.

    Needed as its own resolver because a bare `which("localgpu")` answers
    False on a correctly installed machine. The bootstrap installs the console
    script into `$LOCALGPU_HOME/venv`, and nothing puts that directory on
    PATH -- by design, so the venv's Python is never shadowed.

    A plain PATH probe would therefore report the provider missing on exactly
    the machines where it works, and `order_candidates` would mark it
    ineligible with `NOT ON PATH` -- a fall-through that reads like a
    configuration error and is not one.

    PATH is still checked first: someone who has put it on PATH deliberately
    should not be overridden by a guess at the install root.
    """
    which = which or shutil.which
    found = which("localgpu")
    if found:
        return found
    home = os.environ.get("LOCALGPU_HOME")
    if not home:
        home = (os.path.join(os.environ.get("LOCALAPPDATA", ""), "localgpu")
                if os.name == "nt"
                else os.path.join(os.path.expanduser("~"), ".local", "share",
                                  "localgpu"))
    candidates = (
        os.path.join(home, "venv", "Scripts", "localgpu.exe"),
        os.path.join(home, "venv", "bin", "localgpu"),
    )
    for candidate in candidates:
        if os.path.isfile(candidate):
            return candidate
    return None


class ProviderError(ValueError):
    """A provider name is not usable where the config puts it."""


def validate_providers(cfg):
    """Raise if a config names a provider the role may not use.

    Returns the config unchanged when it is clean, so a caller can wrap a read
    in it. Raises `ProviderError` naming the offending key and why -- never
    warns and continues, and never silently rewrites the value.

    The QA checks are the load-bearing ones. `dev` is checked too, but a bad
    `dev.provider` degrades loudly at dispatch; a bad `qa.provider` degrades
    into a green light.
    """
    qa = crew_state.dict_or_empty(cfg.get("qa"))
    dev = crew_state.dict_or_empty(cfg.get("dev"))

    qa_provider = qa.get("provider")
    # Built once each: the accepted-name lists appear in five messages below,
    # and formatting them at each site is what made this block ten separate
    # pylint C0209 findings.
    qa_names = ", ".join(f"`{p}`" for p in QA_PROVIDERS)
    dev_names = ", ".join(f"`{p}`" for p in DEV_PROVIDERS)

    if qa_provider not in (None, "auto") and qa_provider not in QA_PROVIDERS:
        raise ProviderError(
            f"qa.provider = {qa_provider!r} is not a QA provider. QA accepts "
            f"{qa_names}. A weaker model does not review, it agrees, and its "
            "output is indistinguishable from a real pass -- that is refused "
            "here whether the name is a typo or a real provider crew simply "
            "does not dispatch a reviewer to.")

    for name in qa.get("order") or []:
        if name not in QA_PROVIDERS:
            raise ProviderError(
                f"qa.order contains {name!r}, which is not a QA provider. QA "
                f"accepts {qa_names}. A name here that nothing resolves is not "
                "an error at review time -- it is a rung the selector walks "
                "past in silence, leaving the gate reporting green.")

    dev_provider = dev.get("provider")
    if dev_provider is not None and dev_provider not in DEV_PROVIDERS:
        raise ProviderError(
            f"dev.provider = {dev_provider!r} is not a dev provider. "
            f"dev accepts {dev_names}.")

    for role, block in crew_state.dict_or_empty(dev.get("roles")).items():
        pin = crew_state.dict_or_empty(block).get("provider")
        if pin is not None and pin not in DEV_PROVIDERS:
            raise ProviderError(
                f"dev.roles.{role}.provider = {pin!r} is not a dev provider. "
                f"dev accepts {dev_names}.")

    for role, block in crew_state.dict_or_empty(qa.get("roles")).items():
        pin = crew_state.dict_or_empty(block).get("provider")
        if pin is not None and pin not in QA_PROVIDERS:
            raise ProviderError(
                f"qa.roles.{role}.provider = {pin!r} is not a QA provider. QA "
                f"accepts {qa_names}. A pin is evaluated AFTER the family "
                "guard, so a pin here would not merely add a reviewer -- it "
                "would name one.")

    return cfg


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
        "worktree": copy.deepcopy(crew_state.WORKTREE_DEFAULTS),
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
      * `worktree.root` -- which disk has room for a worktree, and which
        directory is not synced to cloud storage, are facts about the
        machine. Someone who keeps worktrees on a second drive keeps them
        there for every repo; making them say so once per checkout is the
        friction this layer exists to remove. A repo that genuinely needs
        its own answer still overrides it.
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
        "worktree": copy.deepcopy(crew_state.WORKTREE_DEFAULTS),
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


def null_shadows(repo_cfg, global_cfg, defaults=None):
    """Paths where the repo layer holds an explicit `null` over a global value.

    `/crew:init` writes `templates/config.template.json`, which spells out
    EVERY key including the ones whose default is `null`. `merge_defaults`
    treats that null as a supplied value, so it beat the machine-global layer
    and the global file did nothing for any repo that had been initialised --
    which is every managed repo. Measured on this template: `memory.vaultPath`,
    `qa.codex.model`, `notify.chatId`, `secondOpinion.model` and
    `worktree.root` all resolved to `None` with a global value set.

    That is `_layer_supplies`' own rule, one case wider: an empty dict
    "mentions a key without deciding its value", and so does a null. The
    docstring there already argues it for `{}`; this is the same argument for
    `None`.

    Deliberately NARROW -- only where the global layer actually supplies
    something. A repo null with no global value underneath is left alone, so
    `context.reserveTokens: null` still means "off" rather than silently
    becoming the 100000 default. That case is real and documented in the
    README, and a blanket "null means unset" would have broken it.

    Not fixed inside `merge_defaults`: `crew_upgrade.upgrade_config` shares
    that function, and changing null semantics there would rewrite users'
    files on migration rather than only resolving them for a read.
    """
    if defaults is None:
        defaults = default_config()
    out = []
    for dotted in leaf_paths(default_global_config()):
        parts = tuple(dotted.split("."))
        # The repo must actually hold the key, and hold it as null. `_MISSING`
        # means the key is absent, which already inherits and needs no help.
        if _dig(repo_cfg, parts) is not None:
            continue
        # And the global must decide a real value there -- `_layer_supplies`
        # rather than a bare `_dig`, so a scalar-over-dict or an empty dict is
        # judged by the same rules the merge itself applies.
        if not _layer_supplies(global_cfg, parts, defaults):
            continue
        if _dig(global_cfg, parts) in (None, _MISSING):
            continue
        out.append(dotted)
    return out


def without_null_shadows(repo_cfg, global_cfg, defaults=None):
    """`repo_cfg` with every `null_shadows` leaf removed. Does not mutate.

    Both `resolve_config` and the `/crew:config` source column run this, so
    the value the run uses and the layer the report names cannot disagree --
    the failure this module already carries scar tissue for.
    """
    shadows = null_shadows(repo_cfg, global_cfg, defaults)
    if not shadows:
        return repo_cfg
    out = copy.deepcopy(repo_cfg)
    for dotted in shadows:
        parts = dotted.split(".")
        node = out
        for part in parts[:-1]:
            node = node.get(part) if isinstance(node, dict) else None
            if not isinstance(node, dict):
                break
        if isinstance(node, dict):
            node.pop(parts[-1], None)
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


def provider_problems(cfg):
    """Provider problems in `cfg` as a list of strings. Never raises.

    The read-side counterpart to `validate_providers`. `resolve_config`
    promises never to raise -- a malformed config must not wedge the session
    hook -- so the read path reports and lets the caller decide how loud to
    be, while `plan_global_write` refuses outright.

    An empty list means clean. It is deliberately a list of the SAME messages
    the exception carries, so a user sees identical wording whether the
    problem was caught on the way in or noticed on the way out.

    Called from `model_report`, which is the actually-exercised read path --
    `/crew:model` and `commands/review.md` step 1 both run through it. A
    reporter with no caller is the same defect in a new coat: `resolve_role`
    now bars an illegitimate `qa` provider outright on its own, so this
    function's job is narrower than it was -- naming the config-level
    problem in one place, in `validate_providers`' own words, rather than
    leaving a reader to infer it from which rows came back BARRED.
    """
    try:
        validate_providers(cfg)
    except ProviderError as exc:
        return [str(exc)]
    return []


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
    # A repo null does not shadow a global value -- see `null_shadows`. The
    # /crew:init template spells out every nullable key, so without this the
    # machine-global layer was inert for every repo crew had ever set up.
    repo_cfg = without_null_shadows(repo_cfg, global_cfg)
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
    incident could not answer.

    Two rules are easy to get wrong, and both were:

    * A scalar supplied where the default holds a dict is DISCARDED by
      merge_defaults, so the layer did not supply it.
    * An EMPTY DICT supplies nothing either. merge_defaults iterates
      `supplied.items()`, so `{}` contributes no keys and whatever the layer
      below holds survives intact. This one shipped: `/crew:upgrade` writes
      `dev.roles: {}` into every repo it migrates, so every migrated repo
      MENTIONED the key while supplying none of it, and the column credited
      `repo` for pins that came from the machine-global file. Mentioning a
      key is not deciding its value.
    """
    node_layer, node_def = layer, defaults
    for index, part in enumerate(parts):
        if not isinstance(node_layer, dict) or part not in node_layer:
            return False
        next_layer = node_layer[part]
        next_def = node_def.get(part) if isinstance(node_def, dict) else None
        if index == len(parts) - 1:
            if isinstance(next_def, dict):
                # A scalar over a dict default is discarded; an empty dict
                # over one overlays nothing. Either way the layer below wins.
                return isinstance(next_layer, dict) and bool(next_layer)
            return True
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
    `source` is `"repo"`, `"global"`, `"repo+global"` or `"default"`.
    `repo+global` appears only for a dict-valued key both layers put keys
    into: their contents merge rather than one replacing the other, so
    naming a single layer would understate the other's contribution. Scoped to the keys
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
    # Same prune as `resolve_config`, for the same reason and from the same
    # helper: if the report applied a different rule from the run, the source
    # column would credit `repo` for a value the run took from `global`.
    repo_cfg = without_null_shadows(repo_cfg, global_cfg, defaults)
    resolved = crew_state.merge_defaults(
        crew_state.merge_defaults(defaults, global_cfg), repo_cfg)

    rows = []
    for dotted in leaf_paths(default_global_config()):
        parts = tuple(dotted.split("."))
        from_repo = _layer_supplies(repo_cfg, parts, defaults)
        from_global = _layer_supplies(global_cfg, parts, defaults)
        value = _dig(resolved, parts)
        if from_repo and from_global and isinstance(value, dict):
            # Merging two dicts is not a contest one of them wins -- the keys
            # combine, so both layers really are deciding part of the value.
            # Naming only the higher-precedence one hides the machine-global
            # file's contribution, which is the failure this column exists to
            # prevent. For a SCALAR the repo genuinely does win outright, and
            # `repo` is the whole truth.
            source = "repo+global"
        elif from_repo:
            source = "repo"
        elif from_global:
            source = "global"
        else:
            source = "default"
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
    it is not, in the order the walk itself would find them: not a provider
    QA recognises, then absent from PATH, then family unknown, then same
    family as the author, then a failed probe. A `copilot` with no
    `qa.copilot.model` has NO knowable family -- that is why the walkthroughs
    insist on pinning it before Copilot may review at all.

    The first check is not cosmetic. `qa.order` is a hand-editable list, and
    a name outside `QA_PROVIDERS` -- `localgpu`, a typo, a provider crew has
    never heard of -- must never be reported eligible on the strength of
    being on PATH and a different family: it is not a reviewer at all, so
    PATH and family are never even consulted for it.

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
        if provider == "claude":
            on_path = True          # in-session subagent, not a binary
        elif provider == "localgpu":
            on_path = bool(localgpu_which(which))
        else:
            on_path = bool(which(provider))
        if provider not in QA_PROVIDERS:
            why = f"`{provider}` is not a provider QA recognises"
        elif not on_path:
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


def model_report(root, which=None, stale=False):
    """Per-ROLE effective provider, model and family, for `/crew:model`.

    One row per role, not one row per block. `qa` used to be reported as a
    single line reading `auto / (cli default)`, which named neither the model
    that would run nor the candidates that would be passed over -- the one
    thing the reader came for. A per-role table is the same argument one level
    down: `qa.roles.review` and `qa.roles.smoke` can now be different models
    from different families, and a block-level row hides that entirely.

    Returns:

        {"providerProblems", "authorFamily", "authorSource", "dispatch",
         "qaOrder", "onPath", "dev": [row, ...], "qa": [row, ...]}

    `providerProblems` is `provider_problems(cfg)` -- the read-side check
    that a config `/crew:model` never wrote (hand-edited, or written by an
    older release) may still name a provider nothing resolves. An empty list
    means clean; a non-empty one is printed ahead of the table, not folded
    into it, because it is a fact about the CONFIG rather than about any one
    role's resolution.

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
    # `provider_problems` is the read-side counterpart to `validate_providers`
    # -- a config `/crew:model` never wrote (hand-edited, or written by an
    # older release) may name a provider `resolve_role` below will already
    # refuse per role, but a reader of THIS report deserves the same words
    # `validate_providers` would have raised on write, in one place, rather
    # than reconstructing them from which rows came back BARRED.
    provider_problems_found = provider_problems(cfg)
    authors, author_source = crew_state.author_families(root, cfg,
                                                       stale=stale)

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
            # `claude` is an in-session subagent, not a CLI to look for, so it
            # is always reachable; `auto` is an instruction rather than a
            # provider and `order_candidates` answers the PATH question for
            # the candidates it walks. Everything else is a real executable
            # and gets asked about, so `role_status` never has to guess -- the
            # guess is what made it disagree with the gate.
            row["providerOnPath"] = (
                True if row["provider"] in ("claude", "auto")
                else bool(localgpu_which(which))
                if row["provider"] == "localgpu"
                else bool(which(row["provider"])))
            out.append(row)
        return out

    candidates = order_candidates(cfg, authors, which)
    return {
        # Never empty means clean, exactly as `provider_problems` documents.
        "providerProblems": provider_problems_found,
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
            for name in QA_PROVIDERS
        },
        # `localgpu` is asked for by its own resolver, not by `which`: the
        # console script lives in the venv and is deliberately off PATH, so a
        # plain probe reports it missing on the machines where it works.
        "onPath": dict(
            [(tool, bool(which(tool))) for tool in PATH_PROVIDERS]
            + [("localgpu", bool(localgpu_which(which)))]),
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
        #
        # An `unknown` author source forces this False. Independence is a
        # claim ABOUT the author's family, so a candidate cannot be
        # independent of a family nobody named -- the unpinned provider that
        # wrote the diff may be serving the reviewer's own. `eligible` says
        # only "not struck", and with an empty author set nothing is struck,
        # so every candidate looked eligible and the report certified a review
        # it had no basis to certify.
        "independentReviewer": (author_source != "unknown"
                                and any(c["eligible"] for c in candidates)),
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
    # Whatever families COULD be named are still struck; the source is what
    # withholds the certification. See `crew_state.author_families`.
    "unknown": ("UNKNOWN - a dispatch on this branch has a family that "
                "cannot be determined (an unpinned provider that hosts "
                "several), or something in .work/ would not parse, so no "
                "reviewer can be proven independent of it - every family "
                "that COULD be named is still struck"),
}


def role_status(row):
    """The one-line verdict for a role row in `/crew:model`'s table. Pure.

    Four states, and the last one is why this is a function rather than three
    lines inside the printer:

      * `BARRED` -- the resolved family is one that wrote this diff, or the
        provider is not one QA recognises at all (`barredBy` is None in that
        second case -- there is no family to name, only a name nothing
        resolves).
      * `walks qa.order` -- `auto` is an instruction, not a provider; the
        guard is applied to the candidates rather than to this row.
      * `NOT ON PATH` -- the CLI that would run is not installed.
        `order_candidates` has always refused such a candidate; this said
        `eligible` at the same config, because it looked only at the family.
        A report that outranks the gate is the bug this function was written
        to fix, so getting it wrong in the other direction is not a fix.
        Being on PATH is still not working auth -- `/crew:model` says to make
        one real call before deciding anything on it -- so the positive
        answer stays the weaker claim.
      * `CANNOT PROVE INDEPENDENCE` -- the family is unknown, which is what an
        unpinned `copilot` is: Copilot hosts several families and an unset
        model does not say which, so it may be serving the author's own. This
        printed as the bare word `eligible` until a QA sweep read it beside
        `order_candidates`, which has always refused the same candidate with
        "no model pinned, so its family is unknown". Two readers of one config
        disagreeing is bad; the human-facing one being the optimistic half is
        the recurring bug this codebase keeps finding -- an unknown collapsing
        into the safe-looking value.
      * `eligible` -- a known family, and not the author's.

    `dev` rows never reach the guard at all: it governs who may REVIEW, and
    `model_report` resolves them with no author for exactly that reason. So
    they say `implements` rather than borrowing a word that would imply they
    passed a check nobody ran on them.
    """
    if row["kind"] == "dev":
        return "implements (the guard governs review, not authorship)"
    if row["barred"]:
        if row["barredBy"]:
            return f"BARRED - same `{row['barredBy']}` family as the author"
        return (f"BARRED - `{row['provider']}` is not a provider QA "
                "recognises")
    if row["provider"] == "auto":
        return "walks qa.order"
    if not row["providerOnPath"]:
        return f"NOT ON PATH - `{row['provider']}` is not installed here"
    if row["family"] is None:
        return (f"CANNOT PROVE INDEPENDENCE - no `{row['kind']}."
                f"{row['provider']}.model` pinned, so its family is unknown")
    return "eligible"


def _print_models(report):
    # A fact about the CONFIG, printed ahead of anything role-shaped -- a
    # hand-edited file naming a provider nothing resolves is a problem with
    # what was read, not with any one row's resolution.
    if report.get("providerProblems"):
        print("PROVIDER PROBLEMS in the resolved config:")
        for problem in report["providerProblems"]:
            print(f"  ! {problem}")
        print()
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
            status = role_status(row)
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

    # Refuse a bad provider HERE, at the boundary where the value enters,
    # rather than where it is read. `resolve_config` documents "never raises"
    # and that contract is load-bearing -- a malformed file must not wedge the
    # session hook. So a write that would put an unusable provider name into
    # the file is rejected outright, and the read path only ever REPORTS (see
    # `provider_problems`). Validating the MERGED result, not `updates`, so a
    # write is judged on the file it would produce.
    _probe = copy.deepcopy(merged)
    for dotted, value in updates.items():
        _set_path(_probe, dotted.split("."), value)
    validate_providers(_probe)

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
    # Sibling-then-rename, with the PID in the name. Two things go wrong with
    # the obvious version, and this is the ONE file crew writes outside the
    # repo, so both matter more here than anywhere else:
    #
    #   * opening the live file "w" truncates it before the JSON is complete,
    #     and every reader collapses malformed global config to `{}` -- so an
    #     interrupted write does not fail loudly, it silently drops every repo
    #     on the machine back to built-in defaults.
    #   * a fixed `.tmp` name races another `/crew:config` in a second
    #     session: both write the same sibling, and one publishes the other's
    #     bytes.
    tmp_path = f"{real_path}.{os.getpid()}.tmp"
    try:
        with open(tmp_path, "w", encoding="utf-8") as handle:
            json.dump(merged, handle, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, real_path)
    except BaseException:
        try:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        except OSError:
            pass                # a stray temp is the lesser problem
        raise
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
    parser.add_argument("--author-stale", action="store_true",
                        help="the caller compared the recorded dispatch "
                             "against the diff's merge-base and found it "
                             "older; strike the recorded AND the configured "
                             "family")
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
        report = model_report(args.root, stale=args.author_stale)
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

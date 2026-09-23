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
import collections
import copy
import hashlib
import json
import os
import re
import shutil
import sys
import time

import crew_state

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    os.pardir, os.pardir, "skills", "crew-graph", "scripts",
))
import crew_upgrade  # pylint: disable=wrong-import-position

# A module attribute, not a baked-in constant used directly everywhere, so a
# test can point it at a scratch file instead of the real machine-wide one.
# Re-exported, not redefined. Canonical in `crew_state` for the same reason the
# provider tuples below are: `crew_upgrade` needs the path and must not import
# this module. Two definitions of one path is how a migration ends up reading a
# different file from the one the resolver merges.
GLOBAL_CONFIG_PATH = crew_state.GLOBAL_CONFIG_PATH


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
        # `cloudId` is cached by `/crew:jira-sync` (commands/jira-sync.md:25)
        # and was read by nothing and declared by nothing until 0.19.10. An
        # undeclared key still WORKS -- `merge_defaults` carries a repo-layer
        # key it has never heard of straight through -- but it is invisible to
        # `leaf_paths`, so it appeared in no key listing, and `is_global_path`
        # returns False for any path absent from the global template, which
        # made it silently un-settable in the global layer. Declaring it is
        # what makes the key set the file's own answer rather than a guess.
        "jira": {"project": None, "cloudId": None},
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
        # `inject` and `recall` are the context hook's (crew_context.py,
        # crew_recall.py). Repo-only on purpose: that hook reads the repo's
        # file and nothing else, so a machine-global value would be accepted
        # and then do nothing. `inject` is off through 0.20.x; see
        # crew_context.run for why and for when that flips.
        "memory": {"mode": "repo", "vaultPath": None, "inject": False,
                   "recall": {"vaults": [], "maxChars": 800}},
        "verifyGate": True,
        "context": copy.deepcopy(crew_state.CONTEXT_DEFAULTS),
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
        "docs": copy.deepcopy(crew_upgrade.DOCS_BLOCK),
        "bitbucket": copy.deepcopy(crew_upgrade.BITBUCKET_BLOCK),
        "github": copy.deepcopy(crew_upgrade.GITHUB_BLOCK),
        # Present on BOTH sides. A repo may narrow what the machine allows --
        # see `crew_state.effective_ratcheted` -- and a key that exists only
        # globally would fail `is_global_path`'s rule that every
        # globally-settable key is a real repo key.
        "install": copy.deepcopy(crew_state.INSTALL_DEFAULTS),
        # Same rule, same ratchet, seven more keys (the six command/production
        # guards plus `roleWrites`). Both layers, because a repo
        # that may only NARROW still has to be able to say so.
        "guards": copy.deepcopy(crew_state.GUARD_DEFAULTS),
        # REPO ONLY, and the asymmetry is the design. `guards.prodDatabase`
        # and `guards.prodServer` say how much of production crew may reach,
        # which is a machine fact and ratchets; `production.databases` and
        # `production.hosts` say WHAT production IS, which is a fact about
        # this checkout. Absent from `default_global_config()`, so
        # `filter_global` prunes it out of a global file and reports it --
        # one repo's hostnames must never become every repo's.
        "production": copy.deepcopy(crew_state.PRODUCTION_DEFAULTS),
        # `/crew:change`. Both layers, like `install` and `guards` and for the
        # same two reasons: `requireForProduction` ratchets across them, and a
        # key that existed only globally would fail `is_global_path`'s rule
        # that every globally-settable key is a real repo key. The ratchet runs
        # the other way round here -- a repo may turn the requirement ON and
        # never off -- which is a property of the tier ORDER in
        # `crew_state.CHANGE_REQUIREMENTS`, not of a second mechanism.
        "change": copy.deepcopy(crew_upgrade.CHANGE_BLOCK),
        # crew 1.0 T3: the plan-approval + scope guard and the Stop-time
        # completion audit (scope_guard.py, completion_audit.py). `off` by
        # default -- a new blocking hook starts disarmed. `auto` is `report`
        # for the first ten tickets, then `block` (crew_ticket.effective_mode).
        # REPO ONLY: it is read from `.crew/config.json` and nothing else.
        "scope": {"mode": "off"},
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
      * `docs` -- which doc-builder brand this person's documents come out
        in. A theme is a standing answer about who is writing, the same shape
        of fact as `notify`'s chat: someone with a house brand wants it on
        every repo without saying so once per checkout. A repo with its own
        client brand still overrides it, which is why it is in both layers
        rather than only this one.
      * `bitbucket` -- whether a pull request has to pass the merge gate, and
        which preset. A person who works this way works this way everywhere;
        `mergeGate.branch` stays null in both layers because the branch is
        resolved from the API per repo, so a global value for it would be the
        one key here that genuinely IS a fact about a checkout.
      * `github` -- the same two keys for the GitHub twin, minus `preset`,
        which is not copied because it binds to nothing (CONFIG.md §8).
      * `guards` -- all four. The strongest machine fact on this list after
        `install`: it is the machine owner saying which dangerous commands
        crew may run HERE. Like `install.policy` and unlike everything else
        above, a repo cannot override these UPWARD -- see
        `crew_state.effective_ratcheted`, and `resolve_ratcheted` below.

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
        # `context.autoClear` and NOTHING ELSE under `context`. How a terminal
        # is driven to accept a keystroke is a fact about the machine, in the
        # same sense provider availability is: `crew_platform.py:384-393`
        # validates `method` against what THIS platform can actually deliver
        # and reports a method it cannot honour. Someone with two machines
        # would otherwise set it per repo forever, for every repo.
        #
        # The siblings stay repo-only and are refused by name, which is
        # measured rather than assumed -- see `test_autoclear_is_global_and_
        # its_siblings_are_not`. `_prune` and `is_global_path` both descend
        # structurally, so naming `context` here grants exactly the six
        # `autoClear` leaves and nothing beside them.
        "context": {"autoClear": {
            key: copy.deepcopy(value)
            for key, value in crew_state.AUTOCLEAR_DEFAULTS.items()
            if key not in crew_state.AUTOCLEAR_CONSENT_KEYS
        }},
        "docs": copy.deepcopy(crew_upgrade.DOCS_BLOCK),
        "bitbucket": copy.deepcopy(crew_upgrade.BITBUCKET_BLOCK),
        "github": copy.deepcopy(crew_upgrade.GITHUB_BLOCK),
        # How much crew may do about a skill it needs and cannot find. This is
        # a machine fact in the strongest sense on this list: it is the machine
        # owner saying how much they trust crew to run commands HERE. It was
        # the only key whose global value a repo cannot override upward --
        # see `crew_state.effective_ratcheted`.
        "install": copy.deepcopy(crew_state.INSTALL_DEFAULTS),
        # The seven guards, and the strongest case on this list for the
        # ratchet rather than precedence. `guards.forcePush` decides whether a
        # command that destroys history on a remote runs without a word,
        # `guards.prodDatabase` whether crew may write to a production
        # database, and `guards.roleWrites` whether a dispatched role may
        # write outside its declared scope; the repo file asking for any of
        # them arrived inside a clone written by someone else. Note what is
        # NOT here: `production.*`, the patterns the first two match against,
        # which is a repo fact.
        "guards": copy.deepcopy(crew_state.GUARD_DEFAULTS),
        # The whole `change` block, and every key in it earns the global layer
        # on its own terms. `requester` and `implementor` are the person:
        # somebody who files changes under one name files them under that name
        # in every repo. `sdpTemplate`, `jiraIssueType` and `category` are
        # facts about the DESK this person files into, which is per-machine and
        # per-organisation rather than per-checkout -- a repo with its own
        # category still overrides them, which is why they are in both layers
        # rather than only this one. `requireForProduction` is the machine
        # owner's standing answer about change control, and it is the one key
        # here whose two layers do not combine by precedence: see
        # `crew_state.CHANGE_REQUIREMENTS` and `resolve_ratcheted`.
        "change": copy.deepcopy(crew_upgrade.CHANGE_BLOCK),
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


def resolve_ratcheted(root, dotted, path=None):
    """The value in force at `dotted` for the repo at `root`, and its source.

    Returns `{"path", "effective", "repo", "global", "heldDownBy"}`.

    The one resolver for every ratcheted key -- `install.policy` and all four
    `guards.*`. There was one of these per key, and a second copy is how the
    two come to disagree: CLAUDE.md's lesson is that one mechanism can be wrong
    while two can disagree, and then only one of them gets fixed.

    **Deliberately NOT routed through `resolve_config`.** Every other key in
    crew resolves by precedence -- the repo answers and the global layer answers
    only where the repo is silent -- and that rule is wrong here, in the one
    direction that costs something. A repo config travels inside a clone written
    by someone else; the global file is this machine's owner. Under precedence a
    cloned repo carrying `install.policy: auto`, or `guards.forcePush: allow`,
    would override a machine owner who chose `manual` or `block` -- a repo
    author granting themselves the right to run commands, or to destroy history
    on a remote, on a stranger's machine.

    So the two layers are read raw and combined by
    `crew_state.effective_ratcheted`, which takes the LOWER rank. Neither layer
    can widen what the other allows.

    `heldDownBy` names the layer that is doing the narrowing, or None when both
    agree. It exists because of the rule `default_global_config` states for the
    keys it refuses: a value that quietly does nothing is worse than one refused
    out loud. A user who sets `auto` in a repo and sees crew keep asking needs to
    be told that their machine-global `manual` is why -- otherwise the key looks
    broken and the next step is to go looking for the bug.

    Raises `KeyError` for a key that does not ratchet, from
    `crew_state.effective_ratcheted`. Falling back to precedence would be the
    ratchet silently not happening, which is the failure it exists to prevent.
    """
    _tiers, normalise, rank = crew_state.ratchet_spec(dotted) or (
        None, None, None)
    parts = dotted.split(".")
    repo_value = _dig(crew_state.load_config(root), parts)
    global_cfg, _ = filter_global(read_global_config(path))
    global_value = _dig(global_cfg, parts)
    repo_value = None if repo_value is _MISSING else repo_value
    global_value = None if global_value is _MISSING else global_value

    effective = crew_state.effective_ratcheted(dotted, repo_value, global_value)

    held = None
    if rank(repo_value) > rank(effective):
        held = "global"
    elif rank(global_value) > rank(effective):
        held = "repo"
    return {
        "path": dotted,
        "effective": effective,
        "repo": normalise(repo_value),
        "global": normalise(global_value),
        "heldDownBy": held,
    }


def resolve_install_policy(root, path=None):
    """`resolve_ratcheted` for `install.policy`. Kept as its own name.

    A thin wrapper on purpose -- see `crew_state.effective_install_policy` for
    the same decision one layer down. The `"path"` key is dropped so the shape
    this function has always returned is byte-identical to what its callers and
    its tests already read.
    """
    row = resolve_ratcheted(root, "install.policy", path)
    return {key: value for key, value in row.items() if key != "path"}


def install_plan_for(root, name, path=None):
    """`crew_state.install_plan` for `name`, under the policy in force here.

    This is the function crew actually calls when a skill it routes to is not
    installed. It is the only place the two halves meet, and neither half can be
    skipped: the policy comes from `resolve_install_policy` (so a repo cannot
    widen it) and the command comes from `crew_state.INSTALLABLE` (so no config
    value can name one).
    """
    resolved = resolve_install_policy(root, path)
    plan = crew_state.install_plan(name, resolved["effective"])
    plan["heldDownBy"] = resolved["heldDownBy"]
    plan["repoPolicy"] = resolved["repo"]
    plan["globalPolicy"] = resolved["global"]
    return plan


def layer_state(path):
    """One config FILE, classified as `"absent"`, `"ok"` or `"corrupt"` --
    the one rule every caller that needs to distinguish "nobody set this"
    from "something here is unreadable" derives from, for EITHER config
    layer (the repo's `.crew/config.json`, or the machine-global file at
    `GLOBAL_CONFIG_PATH`).

    Deliberately NOT the same collapse `crew_state.load_config` /
    `read_global_config` make for every ratcheted key's ordinary read path
    -- `{}` for "absent, malformed, or not a dict" is right there, because
    those keys have always failed OPEN on a bad config file (see
    `read_global_config`'s own docstring, "a broken global file must look
    exactly like no global file at all"). `guards.roleWrites` cannot
    inherit that collapse: unlike those keys, it can BLOCK a tool call, and
    an armed role-write guard going silently permissive because the file
    that armed it got corrupted is CLAUDE.md's own named recurring bug --
    "the unknown collapsing into the safe-looking value" -- happening to
    the one guard in this file that can least afford it.

    Reported in three rounds, 2026-09-19, and this function is the single
    rule that now answers all of them instead of one bespoke check per
    round: (1) with no global override, replacing a repo's
    `guards.roleWrites: block` config with invalid JSON, or with
    `{"guards": 42}`, made the effective policy resolve as if the key had
    never been set; (2) a `.crew/config.json` that is a DIRECTORY (so it
    cannot even be opened) read the same as "absent" through the first
    fix's `text is None` check, because that check could not tell "no such
    file" from "a file that exists but cannot be read at all" apart; (3)
    `{"guards": null}` -- an EXPLICIT JSON null, not a missing key --
    reads as `parsed.get("guards") is None` exactly like a config that
    never mentioned `guards` at all, so the first fix's `guards is not
    None` test let a corrupt, explicit `null` through as if it were a
    clean, unset key.

    Classification, in order:
      * `"absent"` -- nothing at `path` at all (`read_text` returns `None`
        AND the path does not exist on disk in any form). Every repo or
        machine that has never set `guards.roleWrites` is here, and
        CLAUDE.md's new-hook rule requires that to stay permissive.
      * `"corrupt"` -- `path` exists in SOME form but is not the shape this
        key needs to trust: unreadable at all (a directory, a permissions
        error -- `read_text` returns `None` but the path DOES exist);
        readable but not valid JSON; valid JSON but not an object; or an
        object whose `guards` key IS PRESENT (`"guards" in parsed`, not
        `parsed.get("guards") is not None` -- the distinction that closes
        the explicit-`null` gap) and is not itself an object.
      * `"ok"` -- everything else: absent `guards` key, or a `guards`
        object (whatever VALUE `roleWrites` holds inside it -- a malformed
        VALUE there is `crew_guards.normalise_role_writes`'s job, not
        this function's; duplicating it here would be two mechanisms for
        one rule).

    Never touches `load_config`, `read_global_config`, `resolve_ratcheted`
    or any of the other eight ratcheted keys, which keep their existing
    fail-open behaviour on a bad file exactly as before -- this is a
    second, narrower read of the SAME file, not a change to the shared one.
    """
    text = crew_state.read_text(path)
    if text is None:
        if os.path.lexists(path):
            # Present in some form (a directory, a permissions error, an
            # embedded NUL Python rejects before touching disk, or a
            # DANGLING symlink -- see below) but `read_text` could not
            # read it as text at all -- "corrupt", not "absent".
            #
            # `os.path.lexists`, not `os.path.exists() or os.path.isdir()`
            # (the first draft of this fix): `exists` FOLLOWS a symlink to
            # check the TARGET, so a symlink at the config path whose
            # target has been moved or deleted -- a config the operator
            # once pointed somewhere, now pointing nowhere -- reports
            # `exists() == False` and `isdir() == False`, both of which
            # this check already asked, and both answered "absent". A
            # dangling link is not absent: something IS configured at
            # this path, and it cannot be read, which is exactly what
            # "corrupt" means. `lexists` checks the link itself, not what
            # it points at, so it is true for a dangling link the same as
            # for a real file or directory -- one check replaces both of
            # the first draft's. Reported and fixed 2026-09-19.
            return "corrupt"
        return "absent"
    try:
        parsed = json.loads(text)
    except ValueError:
        return "corrupt"
    if not isinstance(parsed, dict):
        return "corrupt"
    if "guards" in parsed and not isinstance(parsed["guards"], dict):
        return "corrupt"
    return "ok"


def resolve_guard(root, name, path=None):
    """`resolve_ratcheted` for one guard. `name` is a bare key, e.g. `forcePush`.

    Raises `KeyError` for a name that is not a guard, from
    `crew_state.effective_ratcheted`. Fail-closed is the CALLER's job and the
    CLI does it -- a raise here is a programming error, and swallowing it into
    `block` would hide a typo'd guard name forever behind a policy that looks
    deliberate.
    """
    return resolve_ratcheted(root, f"guards.{name}", path)


# Which branch a force push is aimed at, for the line `ask` and `allow` print
# before acting. The design note left this open and recommended honouring the
# configured value everywhere -- so `allow` really does allow `main` -- with
# the compensating requirement that the target is NAMED. That is this.
#
# `unknown` is its own answer and never collapses into a branch name. A refspec
# crew cannot parse is exactly the case where a reader most needs to be told
# that crew could not tell, and substituting a plausible-looking `main` is the
# "unknown wearing the label of a check that happened" failure this repo keeps
# rediscovering.
_PUSH_ARGS_RE = re.compile(r"\bgit\s+(?:-\S+\s+(?:[^-]\S*\s+)?)*push\b"
                           r"((?:[^;&|]|&[0-9])*)")


def push_target(command):
    """The branch a `git push` in `command` is aimed at, or `"unknown"`.

    Deliberately crude and deliberately honest. It reads the LAST non-flag
    token of the push, drops a leading `+` (a force refspec) and everything
    before a `:` (`local:remote` -- the remote side is the one being written),
    and answers `unknown` when there is no such token, which is the extremely
    common `git push --force` with the branch taken from the upstream config.
    """
    match = _PUSH_ARGS_RE.search(command)
    if match is None:
        return "unknown"
    tokens = [t for t in match.group(1).split() if not t.startswith("-")]
    # tokens[0] is the remote (`origin`); anything after it is a refspec.
    if len(tokens) < 2:
        return "unknown"
    ref = tokens[-1].lstrip("+")
    if ":" in ref:
        ref = ref.split(":", 1)[1]
    return ref or "unknown"


def guard_marker(root, name, command):
    """The one-shot approval marker path for THIS guard and THIS command.

    Keyed on a digest of the command, not on the guard alone, and that is the
    whole design. A PreToolUse hook has no interactive stdin, so "stop for a
    yes at that moment" can only be expressed as a file; a marker naming only
    the guard would be a standing grant -- approve one force push and every
    later one runs unasked, which is `allow` wearing `ask`'s label.

    Same shape and same directory as `promote-gate.sh:154`'s
    `.crew/.approved-<env>-<sha>`, because it is the same problem and the repo
    should not grow a second scheme for it.
    """
    digest = hashlib.sha256(command.encode("utf-8", "replace")).hexdigest()[:16]
    return os.path.join(
        root, ".crew", f"{crew_state.GUARD_APPROVAL_PREFIX}{name}-{digest}")


def _approval_age(marker):
    """Seconds since `marker` was created, or None when there is no approval.

    None covers absent, unreadable and every other OSError, because an approval
    crew cannot read is not an approval: this is the fail-closed direction, and
    the caller turns None back into `ask`.
    """
    try:
        return time.time() - os.path.getmtime(marker)
    except OSError:
        return None


def _approval_is_live(marker):
    """True when `marker` is an approval from THIS moment, not from some day.

    `abs()` is deliberate. A marker dated in the future is not a fresher
    approval; it is a clock that disagrees or a timestamp somebody set by hand,
    and either way crew cannot say when the yes was given. An approval that
    cannot be dated is not one, so it expires the same as a stale one.
    """
    age = _approval_age(marker)
    return age is not None and abs(age) <= crew_state.GUARD_APPROVAL_TTL


def _log_guard(root, row):
    """Append one tab-separated row to `.crew/guard.log`. Best effort.

    Never raises: a hook that dies because it could not write its own audit
    line would turn a logging failure into a blocked command, which is a worse
    outcome than a missing row. The caller has already printed to stderr.

    `.crew/` IS NEVER CREATED HERE, whatever the decision was. This is the
    line that used to call `os.makedirs` on it, and that is not a logging
    detail: the next SessionStart resolves its root from bare `.crew/`
    presence -- the "No candidate has a *readable* config" loop in
    `crew_platform.main` -- and `heal_config` then writes a full default
    `config.json` into it. So ONE allowed `ssh` in a plain repo adopted that
    repo into crew, and the opt-in promise `heal_config` states in capitals
    ("a directory with no `.crew/` is not a crew repository and must not be
    colonized") was gone before it was ever consulted.

    The caller used to skip only REFUSALS in a repo with no `.crew/`, which is
    the half that never fires: a refusal is rare, and an ordinary allowed
    command -- every `ssh` and every `psql` reaches the production guards -- is
    the one each session runs. The rule lives here now, at the creation site,
    and covers every decision: write into a `.crew/` that exists, never make
    one. An unmanaged repo loses the row, which is the cheaper loss of the two.
    """
    try:
        path = os.path.join(root, crew_state.GUARD_LOG_PATH)
        if not os.path.isdir(os.path.dirname(path)):
            return
        with open(path, "a", encoding="utf-8") as handle:
            handle.write("\t".join(row) + "\n")
    except OSError:
        pass


# Which `production` key each production guard reads. One mapping, because
# two copies of it is how a guard comes to read the other guard's key.
PROD_DECL_KEYS = {"prodDatabase": "databases", "prodServer": "hosts"}

# The five states a `production.<key>` declaration can be in. Four of them
# used to be one value -- `[]` -- and that collapse is what
# `production_declaration` exists to undo. Spelled as constants rather than
# bare strings so a caller comparing against a typo fails at the name.
PROD_DECL_DECLARED = "declared"      # a list with at least one usable glob
PROD_DECL_ABSENT = "absent"          # nobody said what production is
PROD_DECL_EMPTY = "empty"            # the empty set, declared on purpose
PROD_DECL_MALFORMED = "malformed"    # something is there and is not globs
PROD_DECL_UNREADABLE = "unreadable"  # the file is there and crew cannot read it

ProductionDeclaration = collections.namedtuple(
    "ProductionDeclaration", ("state", "patterns", "detail"))


def production_declaration(root, name):
    """WHAT this repo declared as production for one guard, in FIVE states.

    Returns `ProductionDeclaration(state, patterns, detail)`. `state` is one of
    the `PROD_DECL_*` constants above, `patterns` holds every usable glob found
    (so a malformed list carrying three good entries and one integer still
    matches its three), and `detail` is a phrase naming what could not be read,
    for the refusal message. `detail` is "" for the three states that are not a
    failure to read.

    Only `absent` and `empty` mean "no production target was declared".
    `malformed` and `unreadable` mean crew DOES NOT KNOW what this repo's
    production is -- and until this function existed all four answered `[]`,
    which `crew_guards.prod_decision` reads as "nothing declared, so nothing
    matches, so allow". `"hosts": "prod-web-*"` -- a string where a list
    belongs, the single most likely way to write this key wrong -- therefore
    disabled the host restriction completely, at every level including
    `prodServer: none`, while the config still read as though production had
    been declared. That is this repo's named bug class: an unknown collapsing
    into the safe-looking value, in the guard whose whole job is to refuse.

    The read is deliberately NOT `crew_state.load_config`, and not
    `crew_common.read_text` either. `load_config` returns `{}` for absent, for
    unparseable and for not-an-object alike; `read_text` returns None for both
    absent and unreadable, because it catches `OSError` wholesale. Building on
    either one would reimplement the collapse one layer down. Hence the open
    right here, with `FileNotFoundError` split from every other `OSError`.

    REPO LAYER ONLY, which is enforced by never reading the global layer at
    all rather than by a rule in prose: a `production` block in a
    machine-global file must reach no repo. `filter_global` already prunes it
    and reports it; this is what makes that report true.
    """
    key = PROD_DECL_KEYS[name]
    path = os.path.join(root, ".crew", "config.json")
    try:
        with open(path, encoding="utf-8-sig", errors="replace") as handle:
            raw = handle.read()
    except (FileNotFoundError, NotADirectoryError):
        # Absent, and `NotADirectoryError` belongs here rather than below
        # because it is `.crew` ITSELF not being a directory -- a plain file
        # named `.crew`, which is not a crew repo at all: `crew_platform.main`
        # resolves a root by looking for a `.crew/` DIRECTORY, so no config can
        # exist under that name and none ever did. Treating it as unreadable
        # would block every `ssh` in a repo that never opted in, which is the
        # false refusal `test_unmanaged_repo_is_left_untouched.py` exists to
        # prevent.
        #
        # Both names, because the two platforms raise DIFFERENT ones for the
        # same tree and only one of them was caught. Measured on this exact
        # fixture (`.crew` written as a file, then `open(".crew/config.json")`):
        # POSIX raises `NotADirectoryError`, Windows raises `FileNotFoundError`
        # -- so the guard allowed on Windows and blocked on Linux for one repo
        # state, and the local run was green while CI was red. A guard whose
        # answer depends on the OS has no answer.
        return ProductionDeclaration(PROD_DECL_ABSENT, [], "")
    except (OSError, ValueError) as exc:
        # Everything that is not "it is not there": a directory in place of the
        # config FILE (`PermissionError` on Windows, `IsADirectoryError` on
        # POSIX -- so the split is on the two names above, never on a subclass
        # of this side), a permissions denial, an unreadable mount.
        # `ValueError` covers a path python rejects before touching the disk
        # (an embedded NUL).
        return ProductionDeclaration(
            PROD_DECL_UNREADABLE, [],
            f"`.crew/config.json` exists and could not be read "
            f"({type(exc).__name__})")
    try:
        cfg = json.loads(raw)
    except ValueError as exc:
        return ProductionDeclaration(
            PROD_DECL_MALFORMED, [],
            f"`.crew/config.json` does not parse as JSON ({exc})")
    if not isinstance(cfg, dict):
        return ProductionDeclaration(
            PROD_DECL_MALFORMED, [],
            f"`.crew/config.json` holds a JSON {type(cfg).__name__}, not an "
            f"object")
    if "production" not in cfg:
        return ProductionDeclaration(PROD_DECL_ABSENT, [], "")
    block = cfg["production"]
    if not isinstance(block, dict):
        return ProductionDeclaration(
            PROD_DECL_MALFORMED, [],
            f"`production` is a {type(block).__name__}, not an object")
    if key not in block:
        return ProductionDeclaration(PROD_DECL_ABSENT, [], "")
    declared = block[key]
    if not isinstance(declared, list):
        return ProductionDeclaration(
            PROD_DECL_MALFORMED, [],
            f"`production.{key}` is a {type(declared).__name__}, not a list "
            f"of glob strings")
    patterns = [p for p in declared if isinstance(p, str) and p.strip()]
    if len(patterns) != len(declared):
        # A list that is PARTLY globs. The entries crew could read are kept
        # and still match, and the state is still `malformed`, because the
        # entries it could not read are each a production target that may or
        # may not be there -- exactly the thing a `block` level is about.
        return ProductionDeclaration(
            PROD_DECL_MALFORMED, patterns,
            f"{len(declared) - len(patterns)} of the {len(declared)} entries "
            f"in `production.{key}` are not glob strings")
    if not patterns:
        return ProductionDeclaration(PROD_DECL_EMPTY, [], "")
    return ProductionDeclaration(PROD_DECL_DECLARED, patterns, "")


def production_patterns(root, name):
    """The `production.*` globs for one production guard, REPO LAYER ONLY.

    The globs alone, for a caller that only needs to match against them.
    Anything DECIDING whether to refuse must use `production_declaration`
    instead: `[]` here is the answer for four different states, and three of
    them are not "nothing was declared".
    """
    return production_declaration(root, name).patterns


def _prod_undeclarable(name, policy, command, declared):
    """The production decision when crew CANNOT READ what production is.

    Returns the same `(decision, reason, target, access)` tuple
    `crew_guards.prod_decision` does, and exists because that function cannot
    be asked this question: it takes a pattern LIST, and the honest input here
    is "the list is unknown", which no list can spell. `[]` least of all --
    `[]` spells "the empty set was declared", which is a statement the repo
    made, and the collapse of the two is the defect.

    The LEVEL still decides, because at two of the three levels nothing turns
    on the unknown:

      full  every access to every declared target is permitted, so a target
            crew failed to read would have been allowed had it read it.
      read  a command crew can classify as read-only is permitted whether or
            not it matches a declared target, so again the answer is the same
            either way.

    Everything else blocks -- `none`, and `read` against anything not
    classified read-only -- and the refusal carries a NON-EMPTY `target`. That
    is load-bearing, not cosmetic. `guard.sh`'s `prod_guarded` and
    `guard.ps1`'s `Invoke-ProdGuard` both return silently when the target field
    is empty, correctly, because an empty target means no declared pattern
    matched; a `block` with an empty target is therefore a refusal both shells
    would swallow on their way to exit 0. "Could not tell" has to be its own
    value in the target field too, or the decision dies between this resolver
    and the hook that enforces it.

    The two ALLOW branches keep the target EMPTY on purpose, and that asymmetry
    is deliberate. An empty target is what keeps an ordinary `ssh` silent, and
    in `guard.sh` a non-empty one also sets `PROD_HIT=1`, which suppresses the
    crude "`prod` as an argument" fallback further down the same script.
    Filling it on an allow would remove that fallback in exactly the repo whose
    config crew could not read. Both allow branches still carry the unread
    declaration in `reason`, and every caller gets it in the row's
    `declaration` key, so the state survives into every value derived from it
    without weakening a check that still works.
    """
    level = crew_state.normalise_prod_level(policy)
    access = crew_state.classify_access(command)
    unread = f"crew could not read what production is: {declared.detail}"
    if level == "full":
        return ("allow",
                f"guards level is `full`, {access} access -- and {unread}",
                "", access)
    if level == "read" and access == "read":
        return ("allow",
                f"classified read-only, permitted by `read` -- and {unread}",
                "", access)
    return ("block",
            f"`{level}` cannot be applied because {unread}. Crew cannot tell "
            f"whether this command reaches production, and a check that could "
            f"not run is not a check that passed. Fix `.crew/config.json`.",
            f"<unread production.{PROD_DECL_KEYS[name]}>", access)


def _guard_row(name, policy, decision, reason, marker, target, resolved):
    """The dict every guard decision returns, built in ONE place.

    One constructor because two of them drifting is how a caller comes to read
    a key that one branch sets and the other does not, and the two branches
    here are exactly the shape that invites it.
    """
    return {
        "guard": name,
        "policy": policy,
        "decision": decision,
        "reason": reason,
        "marker": marker,
        "target": target,
        "heldDownBy": resolved["heldDownBy"],
        "repo": resolved["repo"],
        "global": resolved["global"],
    }


def _maybe_log(root, record, decision, name, policy, target, command):
    """Append the decision row. Every decision, allow and refusal alike.

    The "unless it is a refusal in a repo with no `.crew/`" rule that used to
    live here was half a fail-safe, and the wrong half: it read as "do not
    colonize a plain repo" while applying only to the decision that almost
    never happens there. `_log_guard` now enforces that rule for every
    decision, at the line that actually created the directory. See its
    docstring -- the reasoning belongs beside the `makedirs` it removed, not
    beside the caller that used to guess when to skip it.
    """
    if not record:
        return
    # Tabs and newlines in a command would forge a row. Same normalisation
    # `crew_incident_log` (`_common.sh:104`) applies, and for the same reason.
    flat = command
    for char in ("\t", "\r", "\n"):
        flat = flat.replace(char, " ")
    _log_guard(root, (str(int(time.time())), name, policy, decision,
                      target or "-", flat))


def guard_decision(root, name, command, path=None, record=False):
    """What crew's command guard must do about `command` under `guards.<name>`.

    Returns `{"guard", "policy", "decision", "reason", "marker", "target",
    "heldDownBy", "repo", "global", "access", "declaration"}` where `decision`
    is one of:

        "block"   refuse, exactly as the guard did before these keys existed
        "ask"     refuse, print the exact command, and name the marker that
                  approves THAT command and only that command, for the next
                  `GUARD_APPROVAL_TTL` seconds
        "allow"   let it through

    `policy` is the configured value and `decision` is what to DO, and they are
    separate keys because they differ in the case the whole `ask` design turns
    on: policy `ask` with a live marker present is decision `allow`. A
    caller that read one field would either re-ask forever or never ask at all.

    The marker is read through `_approval_is_live`, never with a bare
    `os.path.exists`. `.crew/` is gitignored and nothing prunes it, so an
    approval with no time bound is a standing per-command `allow` that outlives
    the session, the task and the person who gave it -- `ask` in the config and
    `allow` on disk, which is the label-without-the-behaviour failure the whole
    block exists to avoid.

    **Under `allow` nothing is silent.** `record=True` appends a row to
    `.crew/guard.log` for every decision, not only the permissive ones -- the
    log is then the record of what the guard did, rather than a record of the
    half somebody thought worth keeping. Consuming the marker is deliberately
    NOT done here: a `PreToolUse` hook can fire more than once for one command
    (both shell flavours are registered on Windows), and deleting the marker on
    the first read would refuse the second. The marker is one-shot in the sense
    that it names one command, and it is the user's to remove.
    """
    resolved = resolve_guard(root, name, path)
    policy = resolved["effective"]
    marker = guard_marker(root, name, command)
    target = push_target(command) if name == "forcePush" else ""

    if name in crew_state.PROD_GUARD_NAMES:
        # A different vocabulary and a different question, so a different
        # branch rather than three more cases bolted onto the policy chain.
        # The patterns come from the REPO layer alone -- `production_
        # declaration` is where that is enforced -- while `policy` above
        # already came through the ratchet, so the level narrows and the
        # patterns do not.
        #
        # THE STATE IS READ BEFORE THE PATTERNS ARE USED. A declaration crew
        # could not read is not handed to `prod_decision` at all: that function
        # answers "no declared production target matches" for an empty list,
        # which is the right answer for an empty list and the wrong one for an
        # unknown. Keeping the two apart here, rather than teaching
        # `prod_decision` a fourth argument, is what let this land without
        # changing `crew_guards.py`.
        declared = production_declaration(root, name)
        if declared.state in (PROD_DECL_MALFORMED, PROD_DECL_UNREADABLE):
            decision, reason, target, access = _prod_undeclarable(
                name, policy, command, declared)
        else:
            decision, reason, target, access = crew_state.prod_decision(
                policy, command, declared.patterns)
        # `ask` is not in this vocabulary, so there is nothing to approve and
        # naming a marker file would invite a user to create one that nothing
        # reads.
        out = _guard_row(name, policy, decision, reason, "", target, resolved)
        out["access"] = access
        out["declaration"] = declared.state
        _maybe_log(root, record, decision, name, policy, target, command)
        return out

    if policy == "allow":
        decision, reason = "allow", f"guards.{name} is `allow`"
    elif policy == "ask":
        if _approval_is_live(marker):
            decision, reason = "allow", f"approved for this command: {marker}"
        elif _approval_age(marker) is not None:
            decision, reason = "ask", (
                f"guards.{name} is `ask`: the approval at {marker} is outside "
                f"the {crew_state.GUARD_APPROVAL_TTL // 60}-minute window")
        else:
            decision, reason = "ask", (
                f"guards.{name} is `ask`: an approval is good for "
                f"{crew_state.GUARD_APPROVAL_TTL // 60} minutes, so it cannot "
                f"become a standing grant nobody revisits")
    else:
        decision, reason = "block", f"guards.{name} is `block`"

    out = _guard_row(name, policy, decision, reason, marker,
                     target, resolved)
    out["access"] = ""
    # Set in BOTH branches, exactly as `access` is: a key one branch defines
    # and the other does not is how a caller comes to read a missing key, which
    # is what `_guard_row`'s docstring is about. The four guards here read no
    # `production` block at all, so the honest value is "not applicable" rather
    # than any of the five declaration states.
    out["declaration"] = ""
    _maybe_log(root, record, decision, name, policy, target, command)
    return out


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
    naming a single layer would understate the other's contribution.

    A RATCHETED key (`install.policy`, every `guards.*`) carries three extra
    fields -- `"ratchet": True`, `"heldDownBy"` and the two raw layer values --
    and its `"value"` is the ratcheted effective one, NOT the merged one. It
    has to be: those keys do not resolve by precedence, so printing the merged
    result for them produced a table that contradicted the run. Scoped to the keys
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
        if crew_state.ratchet_spec(dotted) is not None:
            # A ratcheted key does not resolve by precedence, so the merged
            # result is the WRONG value to print for it. This table said
            # `install.policy  repo  "auto"` on a machine whose global file
            # said `manual` and whose crew therefore behaved as `manual` --
            # a report that contradicted the run, in the direction that reads
            # as "you have it", which is the worst direction for a key that
            # decides what crew may run. Measured before it was fixed, not
            # reasoned about.
            #
            # `heldDownBy` rides along rather than being folded into `source`,
            # because "which layer decided" and "which layer is holding it
            # down" are different questions and a single column can only
            # answer one. `_print_explain` renders both.
            ratchet = resolve_ratcheted(root, dotted, path)
            rows.append({
                "path": dotted,
                "value": ratchet["effective"],
                "source": ratchet["heldDownBy"] or (
                    "repo" if from_repo else "global" if from_global
                    else "default"),
                "ratchet": True,
                "heldDownBy": ratchet["heldDownBy"],
                "repo": ratchet["repo"],
                "global": ratchet["global"],
            })
            continue
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


# What each tier actually grants, for the `!` line on a widening. Keyed on
# every member of `AUTHORITIES` so a tier added without a note is a KeyError at
# the point of use rather than a warning that silently describes the wrong
# thing -- the failure mode that produced this table. `report-only` is present
# because the key set has to be total, not because it can ever be reached here:
# it is rank 0, so nothing widens INTO it.
_INSTALL_WIDENING_NOTES = {
    "manual": (
        "crew names the missing skill and the command and runs nothing. This "
        "is the narrowest policy and nothing widens into it."
    ),
    "ask": (
        "crew will offer to install a missing skill and run the command only "
        "after you say yes. The command is always one crew ships."
    ),
    "auto": (
        "crew will install a missing skill WITHOUT asking. It can only ever "
        "run a command from its own source (`crew_state.INSTALLABLE`), never a "
        "string from a skill file, a repo config, or anywhere a repo author "
        "controls - but it will run one without stopping to ask."
    ),
}

_WIDENING_NOTES = {
    "report-only": (
        "the PM reports and recommends only. This is the narrowest tier and "
        "nothing widens into it."
    ),
    "act": (
        "the PM will dispatch roles itself and report after. It still asks you "
        "to choose when a decision is open. Removal, deletion and offboarding "
        "still stop for an explicit yes."
    ),
    "autonomous": (
        "the PM will dispatch roles itself AND stop asking you to choose - "
        "where it would put a decision to you it takes the option it would "
        "have recommended and says which. Offboarding a role, deleting a "
        "codemap or diagram, rewriting .crew/metrics.md, and destroying git "
        "history or tracked work still stop for an explicit yes."
    ),
}


# Every key that ratchets, and the three things a ratchet needs: how to rank a
# value, how to normalise one for display, and what to SAY about the tier being
# granted. A registry rather than a second copy of the rule, because the comment
# on `widens` below is a record of what happens when a ratchet is written out by
# hand -- it was wrong in both directions at once. One mechanism can be wrong;
# two can disagree, and then only one of them gets fixed.
#
# Adding a key here is the whole cost of ratcheting it. Nothing else needs to
# know, and nothing else is permitted to compare these values.
def _widens(dotted, before, after):
    """Does setting `dotted` to `after` GRANT something it did not have?

    Rank, never equality, and that is the whole lesson here. This logic lived
    inline as `after == "act" and before != "act"`, which was correct only while
    `act` was the top tier. A third tier made it wrong in both directions at
    once: `act -> autonomous` computed False, so the widest grant crew offers
    would ship unannounced, and `autonomous -> act` computed True, so dialling
    DOWN warned about a widening. The second is the more corrosive -- a warning
    that fires on the safe direction is one users learn to click past, which
    costs the first case its only defence.

    Both ranks normalise first, so an unrecognised `before` ranks 0 and anything
    above it correctly reads as a widening. A key that does not ratchet never
    widens.
    """
    spec = _RATCHETED.get(dotted)
    if spec is None:
        return False
    rank = spec[0]
    return rank(after) > rank(None if before is _MISSING else before)


# What each guard actually governs, in the words the `! widens to` line reads
# out. Keyed on every member of `crew_state.GUARD_NAMES`, so a fifth guard
# added there is a KeyError below rather than a guard that widens with no note
# -- the same totality rule `_INSTALL_WIDENING_NOTES` carries, one level up.
_GUARD_ACTIONS = {
    "terraformApply": "terraform/tofu apply and destroy, -chdir forms included",
    "forcePush": "git push --force / -f / --force-with-lease, and a "
                 "leading-plus refspec",
    "adminMerge": "gh pr merge --admin, which merges past a branch protection "
                  "rule somebody put there",
    "mergeGate": "taking a live repository's merge gate down and putting it "
                 "back, through /crew:gate",
    "prodDatabase": "a database matching a `production.databases` pattern",
    "prodServer": "a host matching a `production.hosts` pattern",
    "roleWrites": "a Write or Edit outside the calling role's declared scope, "
                  "per the policy table in "
                  "hooks/scripts/role_write_guard.py",
}


def _guard_widening_notes(name, what):
    """The `! widens to` note for one guard, total over `GUARD_POLICIES`.

    Total on purpose, `block` included: the CLI does `notes[granted]`, and a
    missing key there is a `KeyError` at the point of use rather than a warning
    that silently describes the wrong tier. That is the failure mode that
    produced `_INSTALL_WIDENING_NOTES`' own totality, and softening it here
    would reintroduce it for four keys at once.
    """
    return {
        "block": (
            f"crew refuses {what}. This is the narrowest policy and nothing "
            "widens into it."
        ),
        "ask": (
            f"crew will print the exact {what} command it was about to run "
            "and refuse until you approve THAT command by creating the marker "
            "file it names. The approval covers one command, not the guard: "
            "the next one asks again."
        ),
        "allow": (
            f"crew will run {what} WITHOUT asking. It still writes a row to "
            f"`{crew_state.GUARD_LOG_PATH}` saying what it let through, so "
            "the record exists - but nothing stops it at the time."
        ),
    }


def _prod_widening_notes(name, what):
    """The `! widens to` note for one production guard, total over
    `PROD_LEVELS`.

    Total for the same reason `_guard_widening_notes` is: the CLI indexes this
    with the tier being granted, so a missing key is a `KeyError` where a
    reader is being told what they just bought, rather than a note describing
    the wrong tier.
    """
    del name
    return {
        "none": (
            f"crew refuses every command aimed at {what}. This is the "
            "narrowest level and nothing widens into it."
        ),
        "read": (
            f"crew may run commands against {what} that it can POSITIVELY "
            "classify as read-only. Anything it cannot classify - an "
            "interactive session, an unrecognised tool, a command it cannot "
            "parse - is treated as a write and refused."
        ),
        "full": (
            f"crew may run ANY command against {what}, writes and deletes "
            f"included. Every one is recorded in `{crew_state.GUARD_LOG_PATH}`, "
            "so the record exists - but nothing stops it at the time."
        ),
    }


def _role_write_widening_notes(name, what):
    """The `! widens to` note for `guards.roleWrites`, total over
    `crew_state.ROLE_WRITE_POLICIES`.

    Total for the same reason every other note table here is: the CLI does
    `notes[granted]`, and a missing key is a `KeyError` at the point of use
    rather than a note describing the wrong tier.

    Unlike `_guard_widening_notes` and `_prod_widening_notes`, the NARROWEST
    tier (`block`) is not this key's default -- `off` is, per CONFIG.md
    Sec18 and CLAUDE.md's rule that a hook which can block ships disabled.
    So the widening direction a reader most needs warned about is the same
    one every fresh repo already sits at: nothing narrows FROM `off`, because
    nothing narrower has been chosen yet.
    """
    del name
    return {
        "block": (
            f"crew refuses {what}. This is the narrowest policy and nothing "
            "widens into it."
        ),
        "report": (
            f"crew allows {what}, and appends a row to "
            f"`{crew_state.GUARD_LOG_PATH}` for every decision, not only "
            "the ones outside scope -- so the record exists, but nothing "
            "stops it at the time."
        ),
        "off": (
            f"crew's role-write guard does not run its policy check at all. "
            f"{what.capitalize()} is not refused and nothing is logged. "
            "This is the WIDEST tier and it is also the default -- every "
            "repo that has never set `guards.roleWrites` is already here."
        ),
    }


_RATCHETED = {
    "pm.authority": (
        crew_state.authority_rank,
        crew_state.normalise_authority,
        _WIDENING_NOTES,
    ),
    "install.policy": (
        crew_state.install_policy_rank,
        crew_state.normalise_install_policy,
        _INSTALL_WIDENING_NOTES,
    ),
}
# The four guards, from `crew_state.GUARDS` rather than written out again, so a
# fifth guard added there cannot arrive here with no widening note -- which
# would be a `KeyError` on the one line that exists to warn about a grant.
_RATCHETED.update({
    f"guards.{_name}": (
        crew_state.guard_policy_rank,
        crew_state.normalise_guard_policy,
        _guard_widening_notes(_name, _GUARD_ACTIONS[_name]),
    )
    for _name in crew_state.GUARD_NAMES
})
# The two production guards, whose vocabulary is `none`/`read`/`full` rather
# than `block`/`ask`/`allow`. They ratchet by the same table and warn on the
# same line; only the words differ, and they differ because reusing the other
# three tier names for a different meaning is how a reader comes to believe
# `read` stops at a prompt.
_RATCHETED.update({
    f"guards.{_name}": (
        crew_state.prod_level_rank,
        crew_state.normalise_prod_level,
        _prod_widening_notes(_name, _GUARD_ACTIONS[_name]),
    )
    for _name in crew_state.PROD_GUARD_NAMES
})
# The one role-write guard, whose vocabulary is `block`/`report`/`off` and
# whose DEFAULT (`off`) is not its floor (`block`) -- see
# `_role_write_widening_notes` for why that is not a bug in this table.
_RATCHETED.update({
    f"guards.{_name}": (
        crew_state.role_writes_rank,
        crew_state.normalise_role_writes,
        _role_write_widening_notes(_name, _GUARD_ACTIONS[_name]),
    )
    for _name in crew_state.ROLE_WRITE_GUARD_NAMES
})


# The `! widens to` notes for `change.requireForProduction`, total over
# `crew_state.CHANGE_REQUIREMENTS` for the same reason every other note table
# here is total: the CLI does `notes[granted]`, and a missing key is a
# `KeyError` at the point of use rather than a note describing the wrong value.
#
# Keyed on BOOLS, which is the first time that happens in this table and is why
# it is written out rather than generated. `False` is the widening direction --
# it removes a requirement -- so the `True` entry is the one that says nothing
# widens into it.
_CHANGE_WIDENING_NOTES = {
    True: (
        "`/crew:promote production` will require a change request in an "
        "APPROVED state for the sha being promoted, read from the tracker "
        "backend rather than from this session, and will refuse outside the "
        "change's scheduled window. This is the narrowest value and nothing "
        "widens into it: a repo may turn this ON, and may never turn it off."
    ),
    False: (
        "`/crew:promote production` will stop asking for a change request. "
        "This is a WIDENING even though it looks like a default, and it is "
        "the one direction the ratchet refuses from a repo file: setting it "
        "here, in the machine-global config, is the only place it can be set "
        "to false at all."
    ),
}

_RATCHETED["change.requireForProduction"] = (
    crew_state.require_change_rank,
    crew_state.normalise_require_for_production,
    _CHANGE_WIDENING_NOTES,
)


def plan_global_write(updates, path=None):
    """What writing `updates` to the global file would change. Pure.

    `updates` is a flat `{"pm.authority": "act"}` mapping. Returns
    `(merged, changes)` where `changes` is a list of
    `{"path", "before", "after", "widens"}` for the entries that
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
            # Never silently. These are the keys whose wrong value the user
            # cannot recover from by noticing -- `pm.authority` gives them
            # agents they did not ask for or a report where they expected
            # work, and `install.policy` runs commands on their machine -- so
            # a widening is marked, printed on the dry run, and printed again
            # on the write.
            #
            # RANK, never equality. This read
            # `after == "act" and before != "act"`, which was correct only
            # while "act" was the top tier. With a third tier it is wrong in
            # both directions at once: act -> autonomous computes False, so the
            # widest grant crew offers would ship unannounced; and
            # autonomous -> act computes True, so DIALLING DOWN warns about a
            # widening. The second is the more corrosive of the two -- a
            # warning that fires on the safe direction is a warning users learn
            # to click past, which costs the first case its only defence.
            # `authority_rank` normalises first, so an unrecognised `before`
            # ranks 0 and anything above it correctly reads as a widening.
            # Renamed from `widens_authority` when `install.policy` became the
            # second ratcheted key. The old name would have had to either lie
            # about install policy or spawn a sibling flag beside it, and a
            # sibling is how the two-mechanism failure starts.
            "widens": _widens(dotted, before, value),
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
    narrowed = []
    for row in rows:
        print(f"{row['path'].ljust(width)}  {row['source'].ljust(8)}  "
              f"{json.dumps(row['value'])}")
        if row.get("heldDownBy"):
            narrowed.append(row)
    # THE NARROWING SOURCE, named, on its own lines. A ratcheted key is the one
    # place in this table where the value shown is not the value either layer
    # asked for, and a `source` column alone cannot say so -- it has one slot
    # and there are two facts. Without this a user who set `allow` in a repo
    # and sees `block` has been told nothing about why, which is the state the
    # `heldDownBy` field was added to `resolve_install_policy` to prevent and
    # which this report then reproduced anyway by not printing it.
    for row in narrowed:
        print()
        print(f"! {row['path']}: repo asks `{row['repo']}`, machine-global "
              f"asks `{row['global']}` -> `{row['value']}`")
        print(f"  The {row['heldDownBy']} layer is holding this down. These "
              "keys take the NARROWER of the two")
        print("  layers, never the repo's: a cloned repo may ask for less "
              "than your machine allows")
        print("  and be obeyed, and may ask for more and be refused.")
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
    parser.add_argument("--install-plan", metavar="NAME", default=None,
                        help="what crew may do about NAME not being "
                             "installed, under install.policy")
    parser.add_argument("--guard", metavar="NAME", default=None,
                        help="what the command guard must do about NAME "
                             "(" + ", ".join(crew_state.ALL_GUARD_NAMES)
                             + ")")
    parser.add_argument("--command", default="",
                        help="the command being judged, for --guard")
    parser.add_argument("--record", action="store_true",
                        help="with --guard, append the decision to "
                             + crew_state.GUARD_LOG_PATH)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    if args.guard is not None:
        # ONE resolver for both shell flavours. `guard.sh` and `guard.ps1`
        # drift independently -- three bypasses fixed in #132 were open in
        # both -- and config layering is the last thing that should exist
        # twice: a PowerShell reimplementation of the ratchet would be a
        # second mechanism for the rule whose entire point is that a repo
        # cannot widen it. Both flavours shell out to this.
        if args.guard not in crew_state.ALL_GUARD_NAMES:
            # Exit 2, and the callers treat any non-zero as `block`. A typo'd
            # guard name must not resolve to a policy at all: `block` returned
            # quietly here would look like a deliberate setting forever.
            print(f"unknown guard: {args.guard} (known: "
                  + ", ".join(crew_state.ALL_GUARD_NAMES) + ")",
                  file=sys.stderr)
            return 2
        out = guard_decision(args.root, args.guard, args.command,
                             args.global_path, record=args.record)
        if args.json:
            print(json.dumps(out, indent=2, sort_keys=True))
            return 0
        # One tab-separated line, because the two consumers are a bash script
        # and a PowerShell script and both split it in one expression. Field
        # order is fixed and appended to, never reordered.
        #
        # `-` for an empty field, never the empty string, and this is not
        # cosmetic. TAB is IFS WHITESPACE in bash, so `IFS=$'\t' read -r a b c`
        # collapses a run of tabs into one delimiter and every field after an
        # empty one shifts left by a slot. Measured: `guards.terraformApply`
        # has no target branch, and guard.sh printed
        # `Target branch: guards.terraformApply is `ask`` -- the REASON, in the
        # target's slot. PowerShell's `-split` does not collapse, so the two
        # flavours disagreed about a line they read from the same producer,
        # which is the drift this shared CLI exists to prevent.
        #
        # `access` is the sixth field, APPENDED. Both flavours read
        # six names now: bash's `read` hands every leftover word to
        # the LAST variable, so a field appended without teaching the
        # reader about it would arrive silently glued onto `reason`.
        #
        # `declaration` -- which of the five `PROD_DECL_*` states the repo's
        # `production` block was in -- is deliberately NOT a seventh field, for
        # that exact reason: appending one here would glue it onto `access` in
        # bash while PowerShell ignored it, and the two flavours would disagree
        # about a line they read from the same producer. It reaches a shell
        # inside `reason`, which every flavour already prints, and reaches a
        # programmatic caller through `--json`.
        print("\t".join(field or "-" for field in
                        (out["decision"], out["policy"], out["marker"],
                         out["target"], out["reason"],
                         out.get("access", ""))))
        return 0

    if args.install_plan is not None:
        plan = install_plan_for(args.root, args.install_plan, args.global_path)
        if args.json:
            print(json.dumps(plan, indent=2, sort_keys=True))
            return 0
        print(f"{plan['name']}: {plan['action']}  ({plan['reason']})")
        if plan["command"] is None:
            # Say what WOULD make it installable. A bare "report" here reads as
            # a policy decision, and it is not one -- no policy can install a
            # name crew ships no command for.
            print("  no command: crew ships an install command only for "
                  + ", ".join(sorted(crew_state.INSTALLABLE)))
        else:
            print("  command: " + " ".join(plan["command"]))
        print(f"  policy: repo={plan['repoPolicy']} "
              f"global={plan['globalPolicy']} -> {plan['policy']}")
        if plan["heldDownBy"]:
            # Never let the narrowing be invisible. See resolve_install_policy.
            print(f"  ! the {plan['heldDownBy']} layer is holding this down to "
                  f"`{plan['policy']}`; the other layer asks for more and "
                  "cannot have it")
        return 0

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
            if change["widens"]:
                # Name the tier being GRANTED, not a hardcoded one. This said
                # "widens to `act`" whatever the target was, so setting
                # `autonomous` warned about the wrong tier and described only
                # what `act` does -- omitting the single thing `autonomous`
                # actually adds, which is that the PM stops asking you to
                # choose. A warning that under-describes the grant is the exact
                # failure this marker exists to prevent, so it is driven off
                # the value rather than written out once.
                _, normalise, notes = _RATCHETED[change["path"]]
                granted = normalise(change["after"])
                print(f"  ! {change['path']} widens to `{granted}`: "
                      + notes[granted])
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

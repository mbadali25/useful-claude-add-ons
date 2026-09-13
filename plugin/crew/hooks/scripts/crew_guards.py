"""What crew may do about the dangerous things: install policy and the guards.

Split out of `crew_state.py` on 2026-09-13, and NOT because the file was
untidy. `.pylintrc` raised `max-module-lines` to 3300 for the endpoint ledger
and wrote the terms of the next raise into the comment beside it: "If this line
needs raising a third time, split the module instead." Adding the `guards`
block took `crew_state.py` to 3341. This is that split, taken rather than the
raise.

The seam is the one this slice already had. Every name here answers one
question -- "may crew do this, and how much narrowing did the two config layers
agree on" -- and none of them touches the repo state, the work log, the
codemap, the graph or the dispatch record that the rest of `crew_state` is
about. `crew_common` and `crew_endpoints` were split off the same file on the
same principle.

**Nothing here imports `crew_state`, and nothing may.** `crew_state` re-exports
these names so its callers did not have to change, and an import in the other
direction would be a genuine cycle -- the same rule `crew_config`'s docstring
states for `crew_state`.

A re-export is a SECOND BINDING, not an alias. `tests/test_module_split.py`
asserts every one of them resolves to the object THIS module defines, and that
nothing in the suite patches one through `crew_state` -- a string-keyed patch
there rebinds a copy the reading function never sees, which is a guard failing
open while wearing the label of a check that happened.
"""
import os

# What crew may do when a skill it needs is NOT installed. Ordered least to most
# permissive and read only through `install_policy_rank`, the same contract
# `crew_state.AUTHORITIES` carries and for the same reason. Append only, never
# reorder.
#
#   manual  name the gap and the command; run nothing
#   ask     offer to run it, and run it only on an explicit yes
#   auto    run it without asking
#
# The default is `manual`, so a repo migrated to schema 5 behaves exactly as it
# did at schema 4: crew installs nothing it was not already installing, which is
# nothing. A mandatory migration that started running commands on other people's
# machines would be indefensible.
INSTALL_POLICIES = ("manual", "ask", "auto")
INSTALL_POLICY_DEFAULT = "manual"
INSTALL_DEFAULTS = {"policy": INSTALL_POLICY_DEFAULT}

# The ONLY commands `auto` can ever reach, as literal argv tuples keyed by the
# plugin name crew routes to.
#
# This table is the whole safety argument for `auto`, so it is worth stating
# plainly why it is a literal and not a lookup. crew reads config out of cloned
# repositories, and skills are files a repo author writes. If the command were
# assembled from a config value, read out of a skill file, or built by
# interpolating the name crew was handed, then `auto` plus one attacker-supplied
# string is arbitrary code execution on the machine of anyone who cloned that
# repo. So:
#
#   * the command is never built from the name -- it is looked up BY the name,
#     and a name absent here is not installable at any policy;
#   * the values are argv tuples, not strings, so nothing is ever handed to a
#     shell and quoting cannot be escaped out of;
#   * adding an entry is a crew source change that goes through review, which is
#     the property a runtime lookup would not have.
#
# Keyed on the names crew itself routes to. A skill crew does not route to has
# no business being installed on crew's say-so, even when it exists in the
# marketplace.
INSTALLABLE = {
    "doc-builder": (
        "claude", "plugin", "install", "doc-builder@useful-claude-add-ons"),
    "bitbucket": (
        "claude", "plugin", "install", "bitbucket@useful-claude-add-ons"),
    "mermaid-svg-bitbucket": (
        "claude", "plugin", "install",
        "mermaid-svg-bitbucket@useful-claude-add-ons"),
}


# --- Configurable guardrails ----------------------------------------------
#
# What crew's command guard does about each dangerous action it recognises:
# `block` refuses as before, `ask` prints the exact command and stops until a
# marker for THAT command exists, `allow` runs it and writes a row saying so.
# Ordered least to most permissive and read only through `guard_policy_rank`,
# the same contract `crew_state.AUTHORITIES` and `INSTALL_POLICIES` carry.
# Append only, never reorder. Full reasoning in CONFIG.md §16, including the
# part a default cannot paper over: `adminMerge` and the `tofu` spelling of
# `terraformApply` are NEW refusals, so `block` does not mean "nothing changed".
GUARD_POLICIES = ("block", "ask", "allow")
GUARD_POLICY_DEFAULT = "block"

# The guards. This tuple is the ORDER the keys are declared in, so
# `default_config()` and `default_global_config()` cannot drift into different
# orderings of the same block. What each governs is prose and lives with the
# prose that uses it -- `crew_config._GUARD_ACTIONS` and CONFIG.md §16.
#
# `mergeGate` is the odd one: it is read by `/crew:gate` rather than by the
# command guard, because "may crew take a live repo's merge gate down" is not a
# shape a regex over a command line can recognise. It lives here anyway so
# there is one guard block with one ratchet, rather than a fifth key somewhere
# else with its own layering rule.
GUARD_NAMES = ("terraformApply", "forcePush", "adminMerge", "mergeGate")

GUARD_DEFAULTS = {name: GUARD_POLICY_DEFAULT for name in GUARD_NAMES}

# The one-shot approval marker `ask` stops for, and where the guard writes what
# it let through. Both live under `.crew/` beside `.approved-<env>-<sha>`,
# which `promote-gate.sh` already uses for the same job: a PreToolUse hook has
# no interactive stdin, so "stop for a yes" can only mean "refuse, name the
# exact command, and name the file that approves THAT command".
GUARD_APPROVAL_PREFIX = ".approved-guard-"
GUARD_LOG_PATH = os.path.join(".crew", "guard.log")


def normalise_install_policy(value):
    """`value` as a known install policy, else the restrictive default.

    Authority's rule, not granularity's, and the distinction matters. An
    unrecognised granularity falls back to the documented default because no
    granularity is more permissive than another -- it only decides how the same
    work is filed. An install policy DOES buy a capability: `auto` runs commands
    without asking. So an unknown collapses to `manual`, the least permissive
    tier, and a typo in a hand-edited config costs capability rather than
    granting it.
    """
    if isinstance(value, str):
        cleaned = value.strip().lower()
        if cleaned in INSTALL_POLICIES:
            return cleaned
    return INSTALL_POLICY_DEFAULT


def install_policy_rank(value):
    """`value`'s position in `INSTALL_POLICIES`. Higher is more permissive.

    Routed through `normalise_install_policy` first, so an unknown ranks 0 and
    every comparison built on this is fail-safe by construction. This is the one
    function permitted to know that the policies are ordered; nothing else may
    compare install-policy strings, exactly as with `authority_rank`.
    """
    return INSTALL_POLICIES.index(normalise_install_policy(value))


def normalise_guard_policy(value):
    """`value` as a known guard policy, else the restrictive default.

    Authority's rule and install policy's rule, for the third time and for the
    third identical reason: a guard policy BUYS a capability -- `allow` runs a
    force push without asking -- so an unknown collapses to `block`, the least
    permissive tier. A typo costs capability rather than granting it.
    """
    if isinstance(value, str):
        cleaned = value.strip().lower()
        if cleaned in GUARD_POLICIES:
            return cleaned
    return GUARD_POLICY_DEFAULT


def guard_policy_rank(value):
    """`value`'s position in `GUARD_POLICIES`. Higher is more permissive.

    Routed through `normalise_guard_policy` first, so an unknown ranks 0 and
    every comparison built on this is fail-safe by construction. This is the
    one function permitted to know that the policies are ordered; nothing else
    may compare guard-policy strings, exactly as with `authority_rank` and
    `install_policy_rank`.
    """
    return GUARD_POLICIES.index(normalise_guard_policy(value))


# Every key whose two layers combine by RATCHET rather than by precedence, and
# the three things a ratchet needs: the ordered tier tuple, how to normalise a
# value, and how to rank one.
#
# A table, not five copies. `install.policy` shipped its ratchet as a bespoke
# `effective_install_policy` plus a bespoke `crew_config.resolve_install_policy`
# and four guards arriving beside it would have been four more pairs -- five
# mechanisms for one rule, which is what CLAUDE.md's "one mechanism can be
# wrong; two can disagree, and then only one of them gets fixed" is about.
# Adding a key here is the whole cost of ratcheting it.
#
# `pm.authority` is deliberately NOT here -- it ratchets for the WIDENING
# WARNING only (`crew_config._RATCHETED`), while its two layers still combine
# by ordinary precedence. See CONFIG.md §16 for why, and for why neither table
# is derived from the other.
RATCHETED_KEYS = {
    "install.policy": (INSTALL_POLICIES,
                       normalise_install_policy,
                       install_policy_rank),
}
RATCHETED_KEYS.update({
    f"guards.{_name}": (GUARD_POLICIES, normalise_guard_policy,
                        guard_policy_rank)
    for _name in GUARD_NAMES
})


def ratchet_spec(dotted):
    """The `(tiers, normalise, rank)` triple for `dotted`, or None.

    None means the key does not ratchet, which is not an error -- most keys do
    not. Callers that must have one raise on None rather than falling back to
    precedence: silently resolving a ratcheted key by precedence is the exact
    failure the ratchet exists to prevent, and it would look like a working
    feature while a cloned repo widened what the machine allows.
    """
    return RATCHETED_KEYS.get(dotted)


def effective_ratcheted(dotted, repo_value, global_value):
    """The value in force at `dotted` given both layers: the LOWER-ranked one.

    Narrowing-only, in the one direction that matters. Every other key in crew
    resolves by precedence -- the repo answers, and the global layer answers
    only where the repo is silent. That rule is wrong here, because the two
    layers are written by different people for different reasons: the global
    file is the machine owner saying how much they trust crew on THIS machine,
    and the repo file travels in a clone from someone else.

    Straight precedence would let a cloned repo's `install.policy: auto`, or its
    `guards.forcePush: allow`, override a machine owner who chose `manual` or
    `block` -- a repo author granting themselves a capability on a stranger's
    machine. Taking the lower rank means neither layer can widen what the other
    allows: a repo may ask for LESS than the machine permits and be obeyed, and
    may ask for more and be refused.

    Both sides are normalised BEFORE they are ranked, so an unknown value ranks
    0 on whichever layer carries it and can only ever narrow. Absent on either
    side is the default, and the default is the floor, so a missing value can
    never widen anything either.
    """
    spec = ratchet_spec(dotted)
    if spec is None:
        raise KeyError(f"{dotted} does not ratchet")
    tiers, _normalise, rank = spec
    return tiers[min(rank(repo_value), rank(global_value))]


def effective_install_policy(repo_value, global_value):
    """`effective_ratcheted` for `install.policy`. Kept as its own name.

    A thin wrapper on purpose: this was the ratchet's only implementation, its
    callers and its tests already spell it this way, and renaming them all to
    prove the generalisation happened would be churn with a chance of a missed
    call site. The rule itself now lives in exactly one place -- see
    `effective_ratcheted` and `RATCHETED_KEYS`.
    """
    return effective_ratcheted("install.policy", repo_value, global_value)


def install_plan(name, policy):
    """What crew may do about `name` not being installed, under `policy`.

    Returns `{"name", "policy", "action", "command", "reason"}` where `action`
    is one of:

        "report"   say it is missing and name the command; run nothing
        "ask"      offer to run it; run only on an explicit yes
        "run"      run it

    Two independent gates, and the first one does not consult the policy at all.
    A name absent from `INSTALLABLE` is `"report"` at EVERY policy including
    `auto` -- there is no command to run, and the absence of one is not a reason
    to construct one. That ordering is the point: it means no value of `policy`,
    and no value anywhere in any config file, can produce a command that is not
    already written in crew's own source.

    `command` is an argv tuple or None. It is never a string, so no caller can
    hand it to a shell without noticing.
    """
    resolved = normalise_install_policy(policy)
    command = INSTALLABLE.get(name)
    if command is None:
        return {
            "name": name,
            "policy": resolved,
            "action": "report",
            "command": None,
            "reason": ("not a plugin crew routes to, so crew ships no install "
                       "command for it"),
        }
    action = {"manual": "report", "ask": "ask", "auto": "run"}[resolved]
    return {
        "name": name,
        "policy": resolved,
        "action": action,
        "command": command,
        "reason": f"install.policy is `{resolved}`",
    }

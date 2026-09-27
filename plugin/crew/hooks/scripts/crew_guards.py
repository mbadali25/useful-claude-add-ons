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
import fnmatch
import json
import os
import re
import shlex

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
GUARD_NAMES = ("terraformApply", "forcePush", "adminMerge", "mergeGate",
               "cloudDestructive", "sqlDestructive", "deployWorkflow")

# The production-access guards, which live in the same `guards` block and
# ratchet by the same table, but have their OWN three-value vocabulary:
#
#   none   crew may not touch a declared production target at all
#   read   crew may run what the guard can positively classify as read-only
#   full   crew may run anything, and every run is logged
#
# `ask` is deliberately absent. The other four guards answer "may crew do this
# one dangerous thing", where a per-command yes is meaningful. These answer
# "how much of production may crew reach", which is a standing posture, not a
# per-command question -- and an `ask` here would mean a marker per distinct
# SQL string, which is a prompt nobody would read by the tenth query.
#
# Ordered least to most permissive, append only, read only through
# `prod_level_rank`. Note that `none` is BOTH the default and the floor, so an
# unknown value and an undeclared key resolve the same way.
PROD_LEVELS = ("none", "read", "full")
PROD_LEVEL_DEFAULT = "none"

PROD_GUARD_NAMES = ("prodDatabase", "prodServer")

# The third vocabulary in this block, and the second key (after
# `change.requireForProduction`) whose DEFAULT is deliberately not its FLOOR.
# See `ROLE_WRITE_DEFAULT` below for why, and CONFIG.md Sec18 for the full
# reasoning -- the short version is CLAUDE.md's own rule for a new hook:
# "a plugin registering one defaults to OFF in the menu". `off` here is what
# makes that true for `guards.roleWrites` without a second mechanism: the
# ratchet's existing "absent means default" already does the arming, the same
# way it does for every other guard.
#
#   off     the PreToolUse hook does not run its policy check at all -- every
#           Write/Edit is allowed, unconditionally
#   report  every write is allowed, and one goes to a row in
#           `.crew/guard.log` for every decision, not only the refusals
#   block   a write outside the calling role's declared scope is refused
#           (exit 2); a write inside scope is allowed and logged the same
#           way `report` logs it
#
# Ordered least to most permissive for the same reason every tier tuple in
# this module is: `block` is the narrowest, `off` the widest, and
# `role_writes_rank` is the one function permitted to know the order.
ROLE_WRITE_POLICIES = ("block", "report", "off")
ROLE_WRITE_GUARD_NAMES = ("roleWrites",)

# `off`, not `block`. Every OTHER guard's default equals its floor -- an
# absent key and an unknown value collapse to the same, narrowest tier. This
# one splits them on purpose, exactly as `CHANGE_REQUIREMENT_DEFAULT` does for
# `change.requireForProduction`, and for a mirror-image reason: that key's
# floor is the SAFEST value because requiring a change request only takes a
# capability away, so the default (permissive) and the floor (strict) differ
# in the direction of "a repo may not silently grant more caution than
# ordered". Here the floor being `block` and the default being `off` is
# required by CLAUDE.md itself: a hook that can block ships disabled until a
# human turns it on. An ABSENT key (or an explicit `null`) means nobody has
# opted in, and must resolve to `off`; a value that is not one of the three
# known strings is a typo in a hand-edited config, and "could not tell" must
# not wear the label of "opted out" -- so a malformed value collapses to
# `block`, the floor, same as every other guard's `normalise_*` function.
ROLE_WRITE_DEFAULT = "off"

# The cloud guard's own switch: whether the PreToolUse Bash/PowerShell hook
# (`cloud_guard.py`) judges commands at all. It is a SWITCH, not a policy --
# what each recognised command gets is still decided by `terraformApply`,
# `forcePush`, `adminMerge`, `cloudDestructive`, `sqlDestructive` and the two
# production guards. The first three existed, ratcheted and governed nothing
# from 0.19.52 (when the old command guard was removed for blocking ordinary
# work) until this hook; turning this on is what makes them mean something.
#
# Same vocabulary, same order and the same split default as `roleWrites`, for
# the same CLAUDE.md reason: a hook that can block ships disabled.
#
#   off     the hook reads nothing but this key and lets every command through
#   report  every decision the hook WOULD make goes to `.crew/guard.log`, and
#           nothing is refused or prompted -- the way to find out what `block`
#           would cost before paying it
#   block   the per-rule policies are enforced: `block` denies, `ask` prompts
#           (or denies, unattended), `allow` lets through and logs
#
# Absent means `off`; a malformed value means `block`, the floor, exactly as
# `normalise_role_writes` already does -- this key reuses that function rather
# than growing a second copy of it.
CLOUD_GUARD_NAMES = ("cloudGuard",)

# Every guard, in declaration order: the seven policy guards, the two
# production ones, the role-write guard, then the cloud guard's switch.
# `GUARD_DEFAULTS` is keyed off this, so a name that exists in none of the
# four tuples cannot reach the config block at all.
ALL_GUARD_NAMES = (GUARD_NAMES + PROD_GUARD_NAMES + ROLE_WRITE_GUARD_NAMES
                   + CLOUD_GUARD_NAMES)

GUARD_DEFAULTS = dict(
    [(name, GUARD_POLICY_DEFAULT) for name in GUARD_NAMES]
    + [(name, PROD_LEVEL_DEFAULT) for name in PROD_GUARD_NAMES]
    + [(name, ROLE_WRITE_DEFAULT) for name in ROLE_WRITE_GUARD_NAMES]
    + [(name, ROLE_WRITE_DEFAULT) for name in CLOUD_GUARD_NAMES])

# What counts as production, and it is a REPO-ONLY block on purpose.
#
# The LEVEL is a property of the machine and its owner -- "this laptop may read
# production" is the same sentence in every checkout. WHAT IS PRODUCTION is a
# property of the checkout: `prod-db-*` means one cluster in one repo and
# something else entirely in the next. A machine-global list would carry one
# repo's hostnames into every other repo on the machine, which is how a guard
# comes to refuse innocent commands (and, worse, to pass dangerous ones because
# the global list names the wrong estate).
#
# So `production.*` is absent from `default_global_config()`, `filter_global`
# prunes it out of a global file and reports it, and the level ratchets while
# the patterns do not.
#
# WITH NO PATTERNS DECLARED THE GUARD MATCHES NOTHING. That is what lets the
# default be `none` without changing anybody's behaviour at upgrade: an
# existing repo gains two keys whose combined effect is "refuse access to the
# empty set". Declaring a pattern is the act that turns them on.
PRODUCTION_DEFAULTS = {"databases": [], "hosts": []}

# Which cloud identities this checkout's commands are pinned to. REPO ONLY, for
# the reason `production` is: "this repo deploys as profile `acme-dev` in
# `eu-west-1`" is a fact about the checkout, and a machine-global pin would
# carry one repo's account into every other repo on the machine.
#
# Each list holds globs. An `aws` command is checked against the first two
# (profile from `--profile`, `AWS_PROFILE`, `AWS_DEFAULT_PROFILE`; region from
# `--region`, `AWS_REGION`, `AWS_DEFAULT_REGION`), an `az` command against the
# third (`--subscription`, `AZURE_SUBSCRIPTION_ID`, then the az CLI's own
# default in `azureProfile.json`, matched by id or by name).
#
# EMPTY MEANS UNPINNED, NOT "ANY". With nothing pinned a read-only cloud
# command runs unchecked, but a DESTRUCTIVE one has an identity nobody vouched
# for -- `cloud_guard.py` treats that as unknown, and an unknown identity is
# never allowed unattended.
CLOUD_DEFAULTS = {"awsProfiles": [], "awsRegions": [], "azureSubscriptions": []}

# Which target environments the cloud guard may let terraform write to with
# nobody attending (T-0005). Two keys, two layering rules:
#
#   nonProd         REPO ONLY, for `production`'s reason: `staging` names one
#                   workspace in one checkout. Globs, fnmatch, case-insensitive.
#   prodUnattended  RATCHETS, and is true only when BOTH layers say the JSON
#                   literal `true` -- see `normalise_prod_unattended`.
#   workflows       REPO ONLY (T-0009): `{workflow glob: source}`, where the
#                   source is `input:<name>` (the dispatch input that names the
#                   environment) or a fixed environment name. A `gh workflow
#                   run` or `gh api .../dispatches` whose workflow matches a key
#                   is a `guards.deployWorkflow` finding; one matching no key is
#                   not judged. It does NOT count toward the terraform layer's
#                   `engaged` (`cloud_guard.environments_config`).
#
# At these defaults nothing is nonProd, production is never unattended and no
# workflow is classified, so an upgraded repo decides every apply and every
# dispatch exactly as before.
ENVIRONMENTS_DEFAULTS = {"nonProd": [], "prodUnattended": False,
                         "workflows": {}}

# Least to most permissive, like every tier tuple here: letting production be
# written unattended is the capability, so `True` ranks above `False`.
PROD_UNATTENDED_TIERS = (False, True)


def normalise_prod_unattended(value):
    """`value` as a bool, where only the JSON literal `true` is true.

    `isinstance(value, bool)` rather than truthiness, for
    `normalise_require_for_production`'s reason in the opposite direction:
    here `True` is the WIDE value, so `"true"`, `1` and `null` must read as
    `False` -- a value crew cannot read never grants unattended production.
    """
    return value if isinstance(value, bool) else False


def prod_unattended_rank(value):
    """`value`'s position in `PROD_UNATTENDED_TIERS`; higher is wider."""
    return PROD_UNATTENDED_TIERS.index(normalise_prod_unattended(value))

# Whether promoting to production needs an APPROVED change request for the sha
# being promoted. `change.requireForProduction`, and it ratchets by the same
# table as every key above -- with one thing worth stating plainly, because it
# reads backwards at first glance.
#
# The tuple is ordered LEAST TO MOST PERMISSIVE, exactly like `INSTALL_POLICIES`
# and `GUARD_POLICIES`. Here the least permissive value is `True`: requiring a
# change request takes a capability AWAY from a promotion. So `True` ranks 0 and
# `False` ranks 1, `effective_ratcheted`'s existing `min` does the rest, and the
# rule the design note asked for falls out of the table rather than out of a
# second mechanism: **a repo may turn the requirement ON and never off.** A
# machine-global `true` cannot be defeated by a cloned repo's `false`; a repo's
# own `true` holds on a machine that said nothing.
#
# `ratchet` reads more naturally here than precedence for the same reason it
# does for `guards.*`: the global file is the machine owner's standing answer
# about change control, and the repo file arrives inside a clone somebody else
# wrote.
CHANGE_REQUIREMENTS = (True, False)

# The DEFAULT is `False`, and it is deliberately NOT the floor. Every other
# ratcheted key in crew has default == floor, so an absent key and an unknown
# value resolve identically; this one splits them on purpose, and both halves
# are load-bearing:
#
#   * **Absent (or an explicit `null`) means `False`** -- schema 7 arrives on
#     every existing repo and must change nobody's promotion behaviour. A key
#     nobody set is a requirement nobody asked for.
#   * **A value that is not a bool means `True`** -- fail closed. `"yes"`,
#     `"false"` as a string, `1`, a dict: crew cannot tell what was meant, and
#     "could not tell" must not wear the label of "not required". The promotion
#     stops and names the key, which is a refusal somebody notices in the next
#     minute rather than a gate that quietly was not there.
CHANGE_REQUIREMENT_DEFAULT = False


def normalise_require_for_production(value):
    """`value` as a bool: absent means the default, malformed means required.

    See `CHANGE_REQUIREMENTS` for why those two cases differ here when they
    are the same case for every other ratcheted key. The short version: the
    floor is `True` and the default is `False`, so collapsing an absent key to
    the floor would turn the requirement on for every repo that upgraded.

    `isinstance(value, bool)` and not a truthiness test, and not
    `isinstance(value, int)` either -- `True`/`False` are `int` subclasses in
    Python, so an `int` check would silently accept `0` as "not required",
    which is the one direction this function must never fail in.
    """
    if value is None:
        return CHANGE_REQUIREMENT_DEFAULT
    if isinstance(value, bool):
        return value
    return True


def require_change_rank(value):
    """`value`'s position in `CHANGE_REQUIREMENTS`. Higher is more permissive.

    Routed through `normalise_require_for_production` first, so a malformed
    value ranks 0 -- the same fail-safe-by-construction contract
    `install_policy_rank` and `guard_policy_rank` carry. The one function
    permitted to know that `True` is narrower than `False`.
    """
    return CHANGE_REQUIREMENTS.index(normalise_require_for_production(value))


# The one-shot approval marker `ask` stops for, and where the guard writes what
# it let through. Both live under `.crew/` beside `.approved-<env>-<sha>`,
# which `promote-gate.sh` already uses for the same job: a PreToolUse hook has
# no interactive stdin, so "stop for a yes" can only mean "refuse, name the
# exact command, and name the file that approves THAT command".
GUARD_APPROVAL_PREFIX = ".approved-guard-"
GUARD_LOG_PATH = os.path.join(".crew", "guard.log")

# How long an `ask` approval stays good for, in seconds.
#
# Without a bound, `ask` is a permanent per-command `allow`: the marker is a
# file under `.crew/`, which is gitignored and never cleaned, so a force push
# approved once is approved next week, in the next session, for the next agent
# working the same worktree -- with nothing on screen saying an approval from
# another day is what let it through. The design note asks `ask` to stop for a
# yes "at that moment", and a file with no time bound is not that moment.
#
# `promote-gate.sh`'s `.approved-<env>-<sha>` needs no TTL because its key is a
# commit sha, so the next commit invalidates it. Keying on the command text --
# which is what makes approving one force push not approve the next -- gives up
# that natural expiry, so the bound has to be explicit.
#
# 15 minutes: long enough to read the refusal, create the marker and re-run,
# and short enough that it cannot outlive the decision it records.
GUARD_APPROVAL_TTL = 900


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


def normalise_prod_level(value):
    """`value` as a known production-access level, else `none`.

    The fourth key to need this and the fourth identical reason: `read` and
    `full` each buy a capability against a live production system, so an
    unknown collapses to the least permissive tier. A typo in a hand-edited
    config costs crew access rather than granting it, and `none` against a
    declared production host is a refusal somebody notices immediately --
    which is the direction a mistake should fail in.
    """
    if isinstance(value, str):
        cleaned = value.strip().lower()
        if cleaned in PROD_LEVELS:
            return cleaned
    return PROD_LEVEL_DEFAULT


def prod_level_rank(value):
    """`value`'s position in `PROD_LEVELS`. Higher is more permissive.

    Routed through `normalise_prod_level` first, so an unknown ranks 0 and
    every comparison built on this is fail-safe by construction. The one
    function permitted to know the levels are ordered.
    """
    return PROD_LEVELS.index(normalise_prod_level(value))


def normalise_role_writes(value):
    """`value` as a known role-write policy, else the restrictive default.

    NOT the same collapse as `normalise_guard_policy` and
    `normalise_prod_level`, and the difference is the whole point of
    `ROLE_WRITE_DEFAULT` being distinct from the floor:

      * absent (`value is None`) is not a typo -- it is every repo that has
        never set this key, which by CLAUDE.md's rule must behave as if the
        hook were not installed. It resolves to `ROLE_WRITE_DEFAULT`
        (`"off"`), NOT to the floor.
      * anything else that fails to name one of `ROLE_WRITE_POLICIES` --
        a non-string, or a string that is not `block`/`report`/`off` -- IS a
        typo or a malformed write, and "could not tell what was meant" must
        not wear the label of "opted out". That collapses to `"block"`, the
        floor, same direction every other guard here fails in.
    """
    if value is None:
        return ROLE_WRITE_DEFAULT
    if isinstance(value, str):
        cleaned = value.strip().lower()
        if cleaned in ROLE_WRITE_POLICIES:
            return cleaned
    return ROLE_WRITE_POLICIES[0]


def role_writes_rank(value):
    """`value`'s position in `ROLE_WRITE_POLICIES`. Higher is more permissive.

    Routed through `normalise_role_writes` first -- same contract as
    `guard_policy_rank` and `prod_level_rank` -- so a malformed value ranks 0
    (the floor) and an absent one ranks at `ROLE_WRITE_DEFAULT`'s position,
    not necessarily 0. `effective_ratcheted`'s `min` still means what it says
    for this key: neither layer can widen past what the other allows, and a
    repo cloned with `guards.roleWrites: off` cannot override a machine-global
    `block`.
    """
    return ROLE_WRITE_POLICIES.index(normalise_role_writes(value))


def guard_tiers(name):
    """The `(tiers, normalise, rank)` triple a guard's VALUES obey.

    Three vocabularies in one block, so the vocabulary is looked up by name
    rather than assumed: `guards.forcePush` is `block`/`ask`/`allow`,
    `guards.prodServer` is `none`/`read`/`full`, and `guards.roleWrites` is
    `block`/`report`/`off`. A caller that assumed one of them would normalise
    every value of the others to that vocabulary's floor and then report a
    tier nobody set.
    """
    if name in PROD_GUARD_NAMES:
        return (PROD_LEVELS, normalise_prod_level, prod_level_rank)
    if name in ROLE_WRITE_GUARD_NAMES or name in CLOUD_GUARD_NAMES:
        return (ROLE_WRITE_POLICIES, normalise_role_writes, role_writes_rank)
    return (GUARD_POLICIES, normalise_guard_policy, guard_policy_rank)


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
    f"guards.{_name}": guard_tiers(_name) for _name in ALL_GUARD_NAMES
})
# The last key (`RATCHETED_KEYS` holds `install.policy`, every `guards.*`
# from `ALL_GUARD_NAMES`, and this one), and the first whose tiers
# are not strings. Registering it here is the WHOLE cost of ratcheting it:
# `effective_ratcheted`'s `min` already means "a repo may turn the requirement
# on and never off", and `sabotage.py`'s `min` -> `max` mutation already covers
# this key along with every other one. A bespoke `effective_change_requirement`
# would have been the fifth mechanism for one rule -- see this table's own
# comment.
RATCHETED_KEYS["change.requireForProduction"] = (
    CHANGE_REQUIREMENTS,
    normalise_require_for_production,
    require_change_rank,
)
# T-0005. Registering it is again the whole cost: `min` means production is
# unattended only when the repo AND the machine owner both said `true`.
RATCHETED_KEYS["environments.prodUnattended"] = (
    PROD_UNATTENDED_TIERS,
    normalise_prod_unattended,
    prod_unattended_rank,
)


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


# --- What is production, and what is a read of it ---------------------------
#
# Two questions, deliberately separate functions, because they fail in opposite
# directions. "Does this command touch production" over-matching costs a
# refusal somebody notices; under-matching costs a production write nobody
# does. "Is this command read-only" is the one that must never guess.

# The shell commands crew can positively classify as read-only over `ssh`.
# A LIST, not a pattern: a pattern saying "anything without a redirect" would
# clear a recursive delete and `systemctl stop`. Anything not named here is a
# WRITE -- see `classify_access` for why that is the only safe default.
PROD_READ_COMMANDS = frozenset((
    "cat", "head", "tail", "less", "more", "ls", "dir", "stat", "file",
    "grep", "egrep", "fgrep", "zgrep", "wc", "sort", "uniq", "cut", "awk",
    "sed", "df", "du", "free", "uptime", "uname", "hostname", "whoami", "id",
    "date", "ps", "top", "netstat", "ss", "journalctl", "dmesg", "echo",
    "true", "which", "printenv",
))

# `env` is NOT on that list, and its absence is the point. It is a WRAPPER:
# `env touch /tmp/x` runs `touch`, so a classifier that stopped at the
# executable name cleared every write on the machine behind four characters.
# It is handled in `_classify_segment` instead -- bare `env` prints the
# environment and is a read, `env FOO=bar <cmd>` is whatever `<cmd>` is, and
# `env` carrying an option is unclassifiable (`-i`, `-u`, `-S`, `--chdir` each
# change what runs or where).
#
# A frozenset rather than a special case in the function, because the shape
# recurs: `nohup`, `nice`, `timeout`, `stdbuf`, `xargs` and `sudo` are all
# wrappers. None of them is added here -- none is on the read list, so each
# already classifies as a write, which is the correct answer. Adding one would
# be a decision to look THROUGH it, and `env` is the only one this list ever
# looked through by accident.
PROD_WRAPPERS = frozenset(("env",))

# `sed` and `awk` are on that list and both can write (`sed -i`, or a
# redirect). The redirect check below catches the redirect; `-i` is caught
# here, by name, because it is the one in-place flag that does not look like
# one. The tools whose read/write split is a SUBCOMMAND get their own table:
# `systemctl status` is a read and `systemctl stop` is not, and a list keyed on
# the binary alone cannot tell those apart.
PROD_WRITE_FLAGS = frozenset(("-i", "--in-place"))
PROD_SUBCOMMAND_READS = {
    "systemctl": frozenset(("status", "show", "list-units", "list-unit-files",
                            "is-active", "is-enabled", "cat")),
    "docker": frozenset(("ps", "logs", "inspect", "images", "stats", "top",
                         "version", "info", "port", "diff", "history")),
    "kubectl": frozenset(("get", "describe", "logs", "top", "explain",
                          "api-resources", "version", "cluster-info")),
    "ip": frozenset(("addr", "a", "link", "l", "route", "r", "neigh")),
}

# The tools whose read/write split is a subcommand AND THEN AN ACTION. `ip
# link` names an OBJECT, not a verb: `ip link show` reads and `ip link set eth0
# down` takes the interface down, and a table keyed on the object alone cleared
# both. Same defect as `env`, one table further in.
#
# Keyed by tool so this is one mechanism rather than a special case: a tool
# absent here is judged on its subcommand alone, which is right for
# `systemctl`, `docker` and `kubectl` -- their subcommand IS the verb. `ip` is
# the only object-then-verb grammar crew recognises.
#
# The abbreviations `ip` itself accepts are deliberately NOT here. `ip link s`
# resolves to `set`, not `show`, so accepting `s` as a read would re-open the
# exact hole this table closes -- and `ip a s`, the common spelling of a read,
# is refused instead. That costs a refusal somebody notices; the other
# direction costs an interface nobody noticed going down.
PROD_SUBCOMMAND_ACTIONS = {
    "ip": frozenset(("show", "list", "lst", "get")),
}

# PowerShell's verb-noun grammar makes the read set nameable rather than
# listable: `Get-Service` and `Get-Content` are reads by construction.
PROD_READ_PS_VERBS = ("get-", "measure-", "test-", "show-", "find-",
                      "search-", "select-", "compare-", "format-", "out-")

# SQL statements crew can positively classify as read-only. `WITH` is
# deliberately absent: `WITH x AS (...) DELETE FROM ...` is a write that opens
# with a read-looking keyword, which is exactly the shape this list must not
# clear.
PROD_READ_SQL = ("select", "show", "explain", "describe", "desc", "analyze")

# The flags whose VALUE names a target, per tool. A value is a target even when
# it looks like an option, because `-h --prod` is a hostname called `--prod`
# and dropping it would be a silent miss.
PROD_TARGET_FLAGS = frozenset((
    "-h", "--host", "--hostname", "-S", "--server", "-d", "--dbname",
    "--database", "--db-instance-identifier", "--db-cluster-identifier",
    "--target", "--instance-id", "--cluster", "--endpoint", "--endpoint-url",
))

# The AWS CLI verbs that only read. Prefix-matched, so `describe-db-instances`
# and `list-clusters` are covered without an enumeration that goes stale on
# every AWS release -- and `start-session`, `modify-*`, `delete-*` and
# `reboot-*` are not on it, so they classify as writes.
PROD_READ_AWS_PREFIXES = ("describe-", "list-", "get-", "search-", "lookup-",
                          "batch-get-", "scan-")

_PROD_SPLIT = (";", "&&", "||", "|", "\n", "&")
_PROD_REDIRECTS = (">", "tee ")


def _prod_tokens(command):
    """`command` as argv, or None when it cannot be parsed.

    None is not an error the caller may ignore: an unbalanced quote means crew
    does not know what the command says, and a command crew cannot read is not
    a command crew can classify as a read.
    """
    try:
        return shlex.split(command, posix=True)
    except ValueError:
        return None


def production_targets(command):
    """Every host, instance or database name `command` could be aimed at.

    Deliberately generous. A candidate that matches nothing costs nothing,
    while a target crew failed to extract is a production system the guard
    does not know it is looking at. So: every non-option token, the host half
    of every `user@host`, the host out of every `scheme://user@host:port/path`
    connection string, and the value of every flag in `PROD_TARGET_FLAGS`
    whether or not that value looks like an option.
    """
    tokens = _prod_tokens(command)
    if tokens is None:
        # Unparseable: fall back to whitespace so a target inside a broken
        # quote is still offered to the matcher. `classify_access` refuses the
        # same command separately, and the two must not depend on each other.
        tokens = command.split()
    out = []
    expect_value = False
    for token in tokens:
        cleaned = token.strip().strip("'\"")
        if not cleaned:
            continue
        if expect_value:
            out.append(cleaned)
            expect_value = False
            continue
        flag, sep, inline = cleaned.partition("=")
        if flag.lower() in PROD_TARGET_FLAGS:
            if sep:
                out.append(inline)
            else:
                expect_value = True
            continue
        if cleaned.startswith("-"):
            continue
        out.append(cleaned)
        if "://" in cleaned:
            cleaned = cleaned.split("://", 1)[1].split("/", 1)[0]
            out.append(cleaned)
        if "@" in cleaned:
            cleaned = cleaned.rsplit("@", 1)[1]
            out.append(cleaned)
        if ":" in cleaned:
            out.append(cleaned.split(":", 1)[0])
    return [t for t in dict.fromkeys(out) if t]


def matches_production(command, patterns):
    """The first declared pattern `command` aims at, or None.

    None when `patterns` is empty, and that is the property the default rests
    on: with nothing declared the guard matches nothing, so `none` changes no
    behaviour until somebody says what production is.
    """
    for pattern in patterns or ():
        if not isinstance(pattern, str) or not pattern.strip():
            continue
        needle = pattern.strip().lower()
        for target in production_targets(command):
            if fnmatch.fnmatch(target.lower(), needle):
                return pattern.strip()
    return None


def _head_name(token):
    """`token` as the program it names: basename, lowered, `.exe` dropped.

    One function because three places asked the same question and a fourth
    would have asked it differently. `/usr/bin/ssh`, `C:\\tools\\ssh.exe` and
    `ssh` are one program, and a guard that answers differently for the three
    spellings is a guard bypassed by typing a path.
    """
    head = os.path.basename(token).lower()
    if head.endswith(".exe"):
        head = head[:-4]
    return head


def _unwrap(tokens):
    """`tokens` with every read-neutral wrapper stripped, or None.

    None means the wrapper cannot be read, which the caller turns into a
    write. `[]` means the wrapper ran nothing -- bare `env`, which prints the
    environment -- and the caller turns THAT into a read.

    Assignments are stripped with the wrapper (`env FOO=bar cmd` runs `cmd`).
    An OPTION is not stripped, it refuses: `env -i` clears the environment,
    `env -u` unsets, `env -S` re-splits the string into a different command
    line and `env --chdir` runs somewhere else. Each of those changes what
    runs, and "crew cannot tell" must never collapse into "read".
    """
    while tokens:
        if _head_name(tokens[0]) not in PROD_WRAPPERS:
            return tokens
        rest = tokens[1:]
        while rest and "=" in rest[0] and not rest[0].startswith("-"):
            rest = rest[1:]
        if rest and rest[0].startswith("-"):
            return None
        tokens = rest
    return tokens


def _classify_segment(segment):
    """One pipeline segment: `read` only when it is positively a read."""
    tokens = _prod_tokens(segment)
    if not tokens:
        return "write"
    tokens = _unwrap(tokens)
    if tokens is None:
        return "write"
    if not tokens:
        # Every wrapper stripped and nothing left to run: `env` on its own,
        # which prints the environment.
        return "read"
    head = _head_name(tokens[0])
    if any(flag in PROD_WRITE_FLAGS for flag in tokens[1:]):
        return "write"
    if any(head.startswith(verb) for verb in PROD_READ_PS_VERBS):
        return "read"
    if head in PROD_SUBCOMMAND_READS:
        rest = [t for t in tokens[1:] if not t.startswith("-")]
        if not rest or rest[0].lower() not in PROD_SUBCOMMAND_READS[head]:
            return "write"
        actions = PROD_SUBCOMMAND_ACTIONS.get(head)
        if (actions is not None and len(rest) > 1
                and rest[1].lower() not in actions):
            return "write"
        return "read"
    if head in PROD_READ_COMMANDS:
        return "read"
    return "write"


def _classify_shell(text):
    """A remote shell command line. EVERY segment must be a read."""
    if any(token in text for token in _PROD_REDIRECTS):
        return "write"
    remaining = [text]
    for sep in _PROD_SPLIT:
        nxt = []
        for chunk in remaining:
            nxt.extend(chunk.split(sep))
        remaining = nxt
    segments = [c.strip() for c in remaining if c.strip()]
    if not segments:
        return "write"
    if all(_classify_segment(seg) == "read" for seg in segments):
        return "read"
    return "write"


def _classify_sql(sql):
    """A SQL payload. Every statement must open with a read-only keyword."""
    statements = [s.strip() for s in sql.split(";") if s.strip()]
    if not statements:
        return "write"
    for statement in statements:
        words = statement.lower().replace("(", " ").split()
        if not words or words[0] not in PROD_READ_SQL:
            return "write"
        # `SELECT ... INTO` creates a table. A read-looking keyword opening a
        # write is the whole reason this is a list and not a prefix check.
        if "into" in words:
            return "write"
    return "read"


def _sql_payloads(tokens):
    """EVERY SQL payload a client was handed, in the order it was handed them.

    A LIST, and returning only the first was a bypass by spelling: `psql -h
    prod-db-1 -c 'select 1' -c 'delete from orders'` runs BOTH, and psql, mysql
    and sqlcmd all accept the flag more than once. One statement inspected out
    of two is a classifier answering a question nobody asked -- and the
    statement it reads is the one an author would put first.

    An EMPTY list means an interactive session (`psql prod-db`), which is
    unclassifiable by construction: nothing in the command line says what will
    be typed into it. The caller turns that into `write`.
    """
    flags = ("-c", "--command", "-e", "--execute", "-q", "-Q", "--query",
             "--eval")
    out = []
    index = 0
    while index < len(tokens):
        flag, sep, inline = tokens[index].partition("=")
        if flag in flags:
            if sep:
                out.append(inline)
            elif index + 1 < len(tokens):
                out.append(tokens[index + 1])
                index += 1
            else:
                # A flag with no value. `""` and not a skip: the payload is
                # MISSING, which `_classify_sql` calls a write, and dropping it
                # would make a truncated command line read as the statements
                # that came before it.
                out.append("")
        index += 1
    return out


def _classify_aws(tokens):
    """`aws <service> <verb>`: a read only on a known read-only verb prefix."""
    words = [t for t in tokens[1:] if not t.startswith("-")]
    if len(words) < 2:
        return "write"
    verb = words[1].lower()
    if any(verb.startswith(prefix) for prefix in PROD_READ_AWS_PREFIXES):
        return "read"
    return "write"


def _classify_ssh(tokens):
    """`ssh [opts] host [remote command]`. No remote command is a write.

    An interactive login is the unclassifiable case that matters most: the
    command line names a host and nothing else, so `read` would be crew
    deciding that whatever gets typed next will be harmless.
    """
    takes_value = ("-i", "-p", "-o", "-l", "-F", "-b", "-c", "-D", "-e", "-I",
                   "-J", "-L", "-m", "-O", "-Q", "-R", "-S", "-W", "-w")
    index, host = 1, None
    while index < len(tokens):
        token = tokens[index]
        if token in takes_value:
            index += 2
            continue
        if token.startswith("-"):
            index += 1
            continue
        host = token
        index += 1
        break
    if host is None or index >= len(tokens):
        return "write"
    return _classify_shell(" ".join(tokens[index:]))


def classify_access(command):
    """`read` when crew can PROVE `command` only reads, `write` otherwise.

    Unknown is a write. Not a hedge -- the whole value of `read` as a level is
    that it is a floor crew cannot fall through, and a classifier answering
    "probably fine" would make `read` a slower `full`. Every tool crew does not
    recognise, every unparseable quote, every interactive session and every
    command carrying a redirect lands here as a write, and the caller refuses
    it under `read` while naming what it could not classify.
    """
    tokens = _prod_tokens(command)
    if not tokens:
        return "write"
    head = _head_name(tokens[0])
    if head == "aws":
        return _classify_aws(tokens)
    if head in ("ssh", "plink"):
        return _classify_ssh(tokens)
    if head in ("psql", "mysql", "mariadb", "sqlcmd", "mongosh", "mongo",
                "redis-cli", "sqlite3", "cqlsh"):
        payloads = _sql_payloads(tokens)
        if not payloads:
            return "write"
        if all(_classify_sql(payload) == "read" for payload in payloads):
            return "read"
        return "write"
    return "write"


def prod_decision(level, command, patterns):
    """What `guards.prodDatabase` / `guards.prodServer` do about `command`.

    Returns `(decision, reason, target, access)`, `decision` being `allow` or
    `block` -- `ask` is not in this vocabulary. `target` is the declared
    pattern that matched, or "" when none did, and no match is an ALLOW that
    says so: a guard refusing commands aimed at nothing anybody declared would
    be refusing on a fact nobody stated.
    """
    resolved = normalise_prod_level(level)
    matched = matches_production(command, patterns)
    if matched is None:
        return ("allow", "no declared production target matches", "", "")
    access = classify_access(command)
    if resolved == "full":
        return ("allow",
                f"guards level is `full`, {access} access to `{matched}`",
                matched, access)
    if resolved == "read" and access == "read":
        return ("allow",
                f"classified read-only against `{matched}`, permitted by "
                "`read`", matched, access)
    if resolved == "read":
        return ("block",
                f"`read` permits only what crew can classify as read-only, "
                f"and this is not: `{matched}`", matched, access)
    return ("block", f"`none` permits no access to `{matched}`", matched,
            access)


# --- the literal-word allowlist (T-0005 Step 8) ------------------------------
#
# Here rather than in `cloud_guard.py`, which holds the only caller, because
# that module sits at `.pylintrc`'s max-module-lines; `_literal_gate` there
# turns these two answers into a finding.
#
# Four review rounds each found a bash quoting shape the lexer misread, and
# each turned a destroy into an allow. So a line naming terraform, terragrunt
# or tofu is judged only when every word on it is a plain literal, a shape
# the lexer cannot misread; anything else is "could not tell". Both checks
# read the RAW text, before the lexer: the name is looked for generously
# (quotes and escapes out, `$'...'` decoded, an expansion as a wildcard, brace
# lists expanded), the words are checked strictly.
_TF_NAMES = tuple(n + e for n in ("terraform", "terragrunt", "tofu")
                  for e in ("", ".exe", ".cmd", ".bat", ".ps1"))
_PLAIN_WORD_RE = re.compile(r"^[A-Za-z0-9_./:=@%+,-]+$")
# `<<`, `<<<`, `<(`, `<>`, `>|`, `<&`, `|&`, `;;` are not plain. PowerShell's
# all-streams `*>` is read as `>`.
_PLAIN_OPS = frozenset((";", "&&", "||", "|", "&", ">", ">>", ">&", "<",
                        "&>", "&>>"))
_NAME_SPLIT_RE = re.compile(r"[\s|&;()<>]+")
# An expansion, innermost first. Its value could be anything, empty included.
_EXPANSION_RE = re.compile(r"\$\{[^{}]*\}|\$\([^()]*\)|`[^`]*`"
                           r"|\$[A-Za-z_][A-Za-z0-9_]*|\$[0-9@*#?$!-]")
_SIMPLE_EXPANSION_RE = re.compile(r"\$\{[^{}]*\}|\$[A-Za-z_][A-Za-z0-9_]*"
                                  r"|\$[0-9@*#?$!-]")
# `${x:-word}` and its kin: the word after the operator may be the value.
_PARAM_OP_RE = re.compile(
    r"\$\{[#!]?[A-Za-z0-9_@*]*(?::?[-=+?]|##?|%%?|//?|\^\^?|,,?)?")
_ANSI_SPAN_RE = re.compile(r"\$'((?:[^'\\]|\\.)*)'?", re.DOTALL)
_ANSI_ESCAPE_RE = re.compile(r"\\(?:([abeEfnrtv\\'\"?])|x([0-9A-Fa-f]{1,2})"
                             r"|u([0-9A-Fa-f]{1,4})|U([0-9A-Fa-f]{1,8})"
                             r"|([0-7]{1,3})|c(.))", re.DOTALL)
_ANSI_SIMPLE = dict(zip("abeEfnrtv\\'\"?", "\a\b\x1b\x1b\f\n\r\t\v\\'\"?"))
_BRACE_SEQ_RE = re.compile(r"^(-?\d+|[A-Za-z])\.\.(-?\d+|[A-Za-z])"
                           r"(?:\.\.-?\d+)?$")
_BRACE_LIMIT = 4096


def _ansi_c_decode(body):
    """What a bash `$'...'` body stands for, `\\xHH`/`\\u`/octal/`\\cX`
    included."""
    def one(m):
        simple, hexa, uni, wide, octal, ctrl = m.groups()
        if simple:
            return _ANSI_SIMPLE[simple]
        if ctrl is not None:
            return chr(ord(ctrl) & 0x1f)
        value = int(octal, 8) if octal else int(hexa or uni or wide, 16)
        return chr(min(value, 0x10ffff))
    return _ANSI_ESCAPE_RE.sub(one, body)


def _brace_expand(word):
    """Every word bash's brace expansion could make of `word` (a numeric
    sequence stands for one digit), or None past `_BRACE_LIMIT` results."""
    out, todo = [], [word]
    while todo:
        current, found = todo.pop(), None
        start = current.find("{")
        while start != -1 and found is None:
            depth, cuts = 0, [start]
            for j in range(start, len(current)):
                depth += {"{": 1, "}": -1}.get(current[j], 0)
                if current[j] == "," and depth == 1:
                    cuts.append(j)
                if depth == 0:
                    seq = _BRACE_SEQ_RE.match(current[start + 1:j])
                    if len(cuts) > 1:
                        found = [current[a + 1:b]
                                 for a, b in zip(cuts, cuts[1:] + [j])]
                    elif seq and not seq.group(1).isalpha():
                        found = ["0"]
                    elif seq:
                        low, high = sorted(map(ord, seq.group(1, 2)))
                        found = [chr(k) for k in range(low, high + 1)]
                    break
            if found is not None:
                todo.extend(current[:start] + alt + current[j + 1:]
                            for alt in found)
            start = current.find("{", start + 1)
        if found is None:
            out.append(current)
        if len(out) + len(todo) > _BRACE_LIMIT:
            return None
    return out


def _names_tool(word):
    """True when `word` could be terraform/terragrunt/tofu: its last path
    part, lowered. A wildcard counts when it could match and keeps three
    literal letters (a bare `*` or `t*` does not -- WHAT IT CANNOT SEE)."""
    base = word.replace("\\", "/").rsplit("/", 1)[-1].lower()
    if not any(c in base for c in "*?["):
        return base in _TF_NAMES
    letters = re.sub(r"\[[^\]]*\]|[*?]", "", base)
    return sum(c.isalnum() for c in letters) >= 3 and any(
        fnmatch.fnmatchcase(name, base) for name in _TF_NAMES)


def _name_candidates(text, shell):
    """Every word `text` could make that might name a program: each
    expansion read as a wildcard, and again with its delimiters as blanks
    (`$(echo terraform)`, `${x:-terraform}`), quotes and escapes out, and an
    assignment's value too (`x=terraform; $x destroy`)."""
    if shell == "powershell":
        texts = [text.replace("`\n", "")]
    else:
        body = text.replace("\\\r\n", "").replace("\\\n", "")
        texts = [body, _ANSI_SPAN_RE.sub(
            lambda m: _ansi_c_decode(m.group(1)), body)]
    for source in texts:
        wild = source
        for _round in range(16):
            wild, count = _EXPANSION_RE.subn("*", wild)
            if not count:
                break
        opened = re.sub(r"[$(){}`]", " ", _PARAM_OP_RE.sub(" ", source))
        # And every simple expansion as empty: `"$x"terraform` inside
        # backquotes, which the two readings above both lose (Step 9).
        emptied = re.sub(r"[$(){}`]", " ", _SIMPLE_EXPANSION_RE.sub("", source))
        for chunk in _NAME_SPLIT_RE.split(" ".join((wild, opened, emptied))):
            if shell == "powershell":
                bares = (re.sub(r"[`'\"]", "", chunk),)
            else:
                bare = re.sub(r"\$(?=['\"])", "", chunk)
                bare = re.sub(r"['\"`]", "", bare)
                bares = (bare.replace("\\", ""), bare.replace("\\", "/"))
            for bare in bares:
                yield bare
                if "=" in bare:
                    yield bare.split("=", 1)[1]


def names_terraform(text, shell):
    """The first word `text` could make that names terraform, terragrunt or
    tofu, or None. PowerShell text arrives already normalised
    (`cloud_guard._ps_normalise`)."""
    for part in _name_candidates(text, shell):
        words = _brace_expand(part) if "{" in part \
            and shell != "powershell" else [part]
        if words is None or any(_names_tool(w) for w in words):
            return part
    return None


def first_non_literal(text, shell):
    """The first word or operator in `text` that is not plain, or None. In
    PowerShell a word opening with `@` splats a variable, so it is not."""
    for chunk in re.split(r"[ \t\n]+", text):
        if shell == "powershell":
            chunk = re.sub(r"\*(?=>)", "", chunk)
        for piece in re.findall(r"[;&|<>]+|[^;&|<>]+", chunk):
            if piece not in _PLAIN_OPS and not _PLAIN_WORD_RE.match(piece) \
                    or shell == "powershell" and piece.startswith("@"):
                return piece
    return None


# --- the command-word trigger (T-0005 Step 9) --------------------------------
#
# Step 8 gated a line when ANY word on it could name terraform, so
# `git commit -m "fix terraform apply"` was refused. The gate now fires when a
# COMMAND WORD could: `_GateReader` splits the raw text the way bash does,
# with its own quote, escape, substitution and heredoc reading -- never the
# lexer's, so a lexer bug still cannot turn a shape into an allow -- and every
# shape it does not read with certainty raises `_Unsure`, which falls back to
# the Step 8 trigger. Falling back can only widen the gate, never narrow it.

class _Unsure(Exception):
    """The trigger's reading met a shape it does not read with certainty."""


_HOLE = "\x00"  # a word part whose value is known only at run time
_GATE_DEPTH = 8
_GATE_CONTROL_RE = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")
_GATE_OPS = ("&>>", "<<<", "<<-", ";;&", "&&", "||", ";;", ";&", "|&", "<<",
             "<>", "<&", ">>", ">&", ">|", "&>", ";", "&", "|", "<", ">")
_GATE_PARAM_RE = re.compile(r"[A-Za-z0-9_#!@*?:%/=+^,.~\[\] -]*")
_FD_WORD_RE = re.compile(r"^(?:\d+|\{[A-Za-z_][A-Za-z0-9_]*\})$")
# A command word this far into a line runs terraform only through a script
# crew cannot split: the Step 8 trigger decides for the whole line.
_GATE_OPAQUE = frozenset((
    "source", ".", "ssh", "cmd", "wsl", "trap", "alias", "hash", "function",
    "flock", "script", ":::", "::::", "fish", "csh", "tcsh"))
_GATE_SHELLS = frozenset(("bash", "sh", "zsh", "dash", "ksh", "ash", "mksh",
                          "busybox"))
_GATE_PWSH = frozenset(("pwsh", "powershell", "pwsh-preview"))
_GATE_VERBS = frozenset(("destroy", "apply", "workspace"))


class _GateReader:
    """The simple commands of `text` as argv lists, bash's way: quotes and
    escapes removed, `$'...'` decoded, and `_HOLE` wherever a value is made
    at run time (an expansion, a substitution, a glob, a brace list). Every
    substitution's commands -- in a word, a double-quoted string, an
    unquoted heredoc body -- are read into the same `cmds`."""

    def __init__(self, text, depth, cmds, pending=None):
        if depth > _GATE_DEPTH:
            raise _Unsure("nested too deep")
        self.text, self.pos, self.depth, self.cmds = text, 0, depth, cmds
        self.nest = 0
        self.pending = [] if pending is None else pending

    def _peek(self, count=1):
        return self.text[self.pos:self.pos + count]

    def read(self, closer=None):
        """Read to the end, or past the `)` closing a `$(`/`(`/`<(`."""
        words, word = [], []
        state = {"word": False, "target": False, "brace": False,
                 "glob": False}

        def end_word():
            if state["word"]:
                value = "".join(word)
                if state["glob"] and value not in ("[", "[["):
                    value += _HOLE
                if state["brace"] and value not in ("{", "}", "{}"):
                    value += _HOLE
                if state["target"]:
                    state["target"] = False
                else:
                    words.append(value)
            word.clear()
            state.update(word=False, brace=False, glob=False)

        def end_command():
            end_word()
            if state["target"]:
                raise _Unsure("a redirection with no target")
            if words:
                self.cmds.append(list(words))
            words.clear()

        self.nest += 1
        if self.nest > 4 * _GATE_DEPTH:
            raise _Unsure("nested too deep")
        while self.pos < len(self.text):
            char = self.text[self.pos]
            if self._peek(2) == "\\\n":
                self.pos += 2
            elif char in " \t":
                end_word()
                self.pos += 1
            elif char == "\n":
                end_command()
                self.pos += 1
                self._bodies()
            elif char == "#" and not state["word"]:
                while self.pos < len(self.text) and self._peek() != "\n":
                    self.pos += 1
            elif char == ")":
                if closer != ")":
                    raise _Unsure("an unmatched )")
                end_command()
                self.pos += 1
                self.nest -= 1
                return
            elif char == "(":
                if state["word"] or words:
                    raise _Unsure("( inside a command")
                self.pos += 1
                self.read(")")
            elif char in "<>" and self._peek(2)[1:] == "(":
                self.pos += 2
                self.read(")")
                word.append(_HOLE)
                state["word"] = True
            elif char in ";&|<>":
                if state["word"] and char in "<>" and \
                        _FD_WORD_RE.match("".join(word)):
                    word.clear()
                    state["word"] = False
                self._operator(end_word, end_command, state)
            else:
                word.append(self._word_part(state))
                state["word"] = True
        if closer is not None:
            raise _Unsure("an unclosed (")
        end_command()
        if self.pending:
            raise _Unsure("a heredoc with no body")

    def _operator(self, end_word, end_command, state):
        op = next(o for o in _GATE_OPS if self.text.startswith(o, self.pos))
        self.pos += len(op)
        if op in (";;", ";&", ";;&"):
            raise _Unsure("a case arm")
        if op in (";", "&", "&&", "||", "|", "|&"):
            end_command()
            return
        end_word()
        if op in ("<<", "<<-"):
            self._delimiter(op == "<<-")
        else:
            state["target"] = True

    def _delimiter(self, strip):
        while self._peek() in (" ", "\t"):
            self.pos += 1
        raw = []
        while self.pos < len(self.text) and \
                self._peek() not in " \t\n;&|()<>":
            raw.append(self._peek())
            self.pos += 1
        raw = "".join(raw)
        # A backslash beside a quote is dequoted differently inside and
        # outside the quotes (`<<'E\OF'` ends at `E\OF`): not read.
        mixed = "\\" in raw and ("'" in raw or '"' in raw)
        odd = raw.count("'") % 2 or raw.count('"') % 2
        if not raw or odd or mixed or "$" in raw or "`" in raw:
            raise _Unsure("a heredoc delimiter crew cannot spell")
        quoted = any(c in raw for c in "'\"\\")
        delim = re.sub(r"\\(.)", r"\1", raw.replace("'", "").replace('"', ""))
        self.pending.append((delim, strip, quoted))

    def _bodies(self):
        pending, self.pending[:] = list(self.pending), []
        for delim, strip, quoted in pending:
            lines = []
            while True:
                if self.pos >= len(self.text):
                    raise _Unsure("a heredoc with no delimiter line")
                end = self.text.find("\n", self.pos)
                end = len(self.text) if end == -1 else end
                line = self.text[self.pos:end]
                self.pos = min(end + 1, len(self.text))
                if (line.lstrip("\t") if strip else line) == delim:
                    break
                lines.append(line)
            if not quoted:
                _GateReader("\n".join(lines), self.depth + 1,
                            self.cmds)._substitutions()

    def _substitutions(self):
        """An unquoted heredoc body: only its expansions are code."""
        while self.pos < len(self.text):
            char = self._peek()
            if char == "\\":
                self.pos += 2
            elif char in "$`":
                self._word_part({"word": True}, in_dq=True)
            else:
                self.pos += 1

    def _word_part(self, state, in_dq=False):
        """One character or quoted run of a word, as text or `_HOLE`."""
        char = self._peek()
        if char == "\\":
            self.pos += 2
            nxt = self.text[self.pos - 1:self.pos]
            if in_dq and nxt not in '$`"\\\n':
                return "\\" + nxt
            return "" if nxt == "\n" else nxt
        if char == "'" and not in_dq:
            end = self.text.find("'", self.pos + 1)
            if end == -1:
                raise _Unsure("an unclosed '")
            self._no_body_across(self.pos, end)
            part, self.pos = self.text[self.pos + 1:end], end + 1
            return part
        if char == '"' and not in_dq:
            self.pos += 1
            return self._double_quoted()
        if char == "$":
            return self._dollar(in_dq)
        if char == "`":
            return self._backquote(in_dq)
        self.pos += 1
        if not in_dq and char in "*?[":
            state["glob"] = True
        if not in_dq and char == "{":
            state["brace"] = True
        return char

    def _no_body_across(self, start, end):
        if self.pending and "\n" in self.text[start:end]:
            raise _Unsure("a quoted newline before a heredoc body")

    def _double_quoted(self):
        parts, start = [], self.pos
        while self._peek() != '"':
            if self.pos >= len(self.text):
                raise _Unsure('an unclosed "')
            parts.append(self._word_part({}, in_dq=True))
        self._no_body_across(start, self.pos)
        self.pos += 1
        return "".join(parts)

    def _dollar(self, in_dq):
        nxt = self.text[self.pos + 1:self.pos + 2]
        if self.text.startswith("$((", self.pos):
            end = self.text.find("))", self.pos)
            body = self.text[self.pos + 3:end]
            if end == -1 or re.search(r"[$`'\"\\()]", body):
                raise _Unsure("arithmetic crew does not read")
            self.pos = end + 2
            return _HOLE
        if nxt == "(":
            self.pos += 2
            self.read(")")
            return _HOLE
        if nxt == "{":
            end = self.text.find("}", self.pos)
            match = _GATE_PARAM_RE.fullmatch(self.text, self.pos + 2, end) \
                if end != -1 else None
            if match is None:
                raise _Unsure("a ${...} crew does not read")
            self.pos = end + 1
            return _HOLE
        if nxt == "'" and not in_dq:
            match = _ANSI_SPAN_RE.match(self.text, self.pos)
            if match.end() - match.start() != len(match.group(1)) + 3:
                raise _Unsure("an unclosed $'")
            self.pos = match.end()
            return _ansi_c_decode(match.group(1))
        if nxt == '"' and not in_dq:
            self.pos += 2
            return self._double_quoted()
        name = re.match(r"[A-Za-z_][A-Za-z0-9_]*|[0-9@*#?$!-]",
                        self.text[self.pos + 1:])
        if name:
            self.pos += 1 + name.end()
            return _HOLE
        self.pos += 1
        return "$"

    def _backquote(self, in_dq):
        body, self.pos = [], self.pos + 1
        while self._peek() != "`":
            if self.pos >= len(self.text):
                raise _Unsure("an unclosed `")
            char = self._peek()
            nxt = self.text[self.pos + 1:self.pos + 2]
            if char == "\\" and (nxt in "`$\\" or in_dq and nxt == '"') \
                    and nxt:
                body.append(nxt)
                self.pos += 2
                continue
            body.append(char)
            self.pos += 1
        self.pos += 1
        _GateReader("".join(body), self.depth + 1, self.cmds).read()
        return _HOLE


def _verb_on_line(top):
    """The Step 8 name, or a word dequoting to destroy/apply/workspace."""
    named = names_terraform(top, "bash")
    if named is not None:
        return named
    return next((c for c in _name_candidates(top, "bash")
                 if c.lower() in _GATE_VERBS), None)


# Subcommands that change no infrastructure, so a terraform or tofu line
# running one is not gated for its quoting (review round 5): the lexer judges
# it, as it did before Step 8. `workspace` and `state` are read-only only with
# the second words listed.
_TF_READ_ONLY = frozenset((
    "plan", "show", "output", "fmt", "validate", "version", "providers",
    "graph", "get", "init", "console", "metadata", "modules", "login",
    "logout"))
_TF_READ_ONLY_PAIRS = {"workspace": frozenset(("list", "show")),
                       "state": frozenset(("list", "show", "pull"))}
# Commands that can put terraform under another name for a later command on
# the same line (`ln -sf /usr/bin/terraform tf && ./tf destroy`).
_GATE_COPIERS = frozenset(("ln", "cp", "install", "link", "mv", "rsync"))
_FIND_EXEC = frozenset(("-exec", "-execdir", "-ok", "-okdir"))


# Options before a subcommand (terragrunt's, and after `run-all`/`run`) whose
# value may be any word, `apply` included: `--working-dir apply destroy`.
_TF_GLOBAL_VALUE_OPTS = frozenset((
    "working-dir", "terragrunt-working-dir", "terragrunt-config", "config",
    "chdir", "queue-exclude-dir", "queue-include-dir"))
_TF_OPS = frozenset(("apply", "destroy", "run-all", "run"))


def tf_skip_options(args, index):
    """The index of the first word from `index` that is not an option or its
    value; `--` ends the options. A known value option (`_TF_GLOBAL_VALUE_OPTS`)
    takes the next word. An unknown one takes it only when it is not an
    option, not an `_TF_OPS` word and not made at run time: the reading that
    finds the operation (`--some-option x destroy`, `--non-interactive
    --working-dir infra destroy`)."""
    while index < len(args) and args[index].startswith("-"):
        if args[index] == "--":
            return index + 1
        name, sep, _value = args[index].lstrip("-").partition("=")
        nxt = args[index + 1] if index + 1 < len(args) else None
        takes = not sep and nxt is not None and (
            name in _TF_GLOBAL_VALUE_OPTS or nxt not in _TF_OPS
            and not nxt.startswith("-") and _HOLE not in nxt)
        index += 2 if takes else 1
    return index


def skip_wrapper_options(args, takes):
    """`args` past a wrapper's own options, read as GNU getopt reads them:
    `--name=v`; `--name v` for a value option in `takes`, or a unique prefix
    of one (`--out L`); a short cluster whose first value letter takes the
    rest of the word, or the next word when it is last (`-rn 1`, `-vk 5`);
    `--` ends them, `-` is an operand."""
    shorts = {t[1] for t in takes if len(t) == 2}
    longs = [t for t in takes if t.startswith("--")]
    index = 0
    while index < len(args) and args[index].startswith("-") \
            and args[index] != "-":
        word, index = args[index], index + 1
        if word == "--":
            break
        if word.startswith("--"):
            match = [t for t in longs if t.startswith(word)]
            index += "=" not in word and len(match) == 1
            continue
        for pos, letter in enumerate(word[1:], 1):
            if letter in shorts:
                index += pos == len(word) - 1
                break
    return args[index:]


def _tf_read_only(argv, fed):
    """True when `argv` -- terraform, tofu or terragrunt and its arguments,
    as bash will run them -- runs a subcommand in `_TF_READ_ONLY`, spelled
    so it cannot be another one: a literal word, first after `-chdir=`
    options (terragrunt: after its options, read by `tf_skip_options`, and
    after `run-all`/`run` -- `--working-dir plan destroy` is a destroy), and
    not a placeholder an `xargs -I` replaces. `parallel` substitutes too
    many forms to be read here."""
    if any(head != "xargs" or any(r in word for r in reps for word in argv)
           for head, reps in fed):
        return False
    rest = argv[1:]
    if "terragrunt" not in _head_name(argv[0]):
        while rest and rest[0].startswith("-chdir="):
            rest = rest[1:]
    else:
        rest = rest[tf_skip_options(rest, 0):]
        if rest[:1] in (["run-all"], ["run"]):
            rest = rest[1:][tf_skip_options(rest[1:], 0):]
    if not rest or _HOLE in rest[0]:
        return False
    if rest[0] in _TF_READ_ONLY:
        return True
    pair = _TF_READ_ONLY_PAIRS.get(rest[0])
    return pair is not None and len(rest) > 1 and rest[1] in pair


def _zsh_names_tool(word):
    """zsh expands `=terraform` to terraform's path (`EQUALS`)."""
    return word.startswith("=") and _names_tool(word[1:])


def _arg_names_tool(word):
    """An argument that may be terraform: its name or zsh's `=terraform`."""
    return _names_tool(word) or _zsh_names_tool(word)


def _first_operand(args):
    return next((a for a in args if not a.startswith("-")), None)


class _TerraformTool:
    """What the command-word trigger asks about the program it gates, for
    terraform, terragrunt and tofu. T-0009 parametrised the trigger on this
    so the workflow-dispatch gate (`_DispatchTool`) reads a line with the same
    reader; every answer here is T-0005's, unchanged."""

    @staticmethod
    def on_line(text, shell="bash"):
        """The Step 8 read of `text`: the word naming the tool, or None."""
        return names_terraform(text, shell)

    @staticmethod
    def names(word):
        return _names_tool(word)

    @staticmethod
    def hole(_argv, top, shell="bash"):
        """`(word, True)` for a command word made at run time, when the line
        names one of the words a terraform line needs; else None."""
        named = _verb_on_line(top) if shell == "bash" else _ps_verb_on_line(top)
        return None if named is None else (named, True)

    @staticmethod
    def direct(argv, fed, _depth):
        """`(word, unseen)` or None when `argv`'s command word names the tool;
        False when it does not."""
        first = argv[0]
        if _zsh_names_tool(first):
            return first, True
        if _names_tool(first):
            return None if _tf_read_only(argv, fed) else (first, False)
        return False

    @staticmethod
    def copy_source(word):
        """An operand of `cp`/`ln`/... that puts the tool under another name."""
        return _HOLE not in word and _arg_names_tool(word)

    @staticmethod
    def copied(argv, top, shell="bash"):
        """`(word, True)` when a name the line copied the tool to is run with a
        verb, else None."""
        verb = _first_operand(argv[1:])
        if verb is not None and verb.lower() in _GATE_VERBS:
            named = names_terraform(top, shell)
            if named is not None:
                return named, True
        return None

    @staticmethod
    def opaque(args, top, launched=None, _typed=None):
        """The word naming the tool in a script crew cannot split, or None.
        `launched` is PowerShell's launcher values (`Start-Process X`)."""
        if launched is not None:
            return next((w for w in launched if _arg_names_tool(w)), None)
        return names_terraform(top if any(_HOLE in a for a in args)
                               else " ".join(args), "bash")

    @staticmethod
    def symbolic(argv, _words, _text):
        """A PowerShell argv as `direct`/`hole`/`copied` read it: as written."""
        return argv

    @staticmethod
    def ps_aliases(_cmds, _text):
        """Names a PowerShell line aliases the tool to: none followed."""
        return set()


_TF_TOOL = _TerraformTool()


def _find_exec_trigger(args, top, helpers, depth, line, tool=_TF_TOOL):
    """`find -exec CMD ... ;|+`: each command it runs, read as one."""
    for index, arg in enumerate(args):
        if arg not in _FIND_EXEC:
            continue
        sub = []
        for word in args[index + 1:]:
            if word in (";", "+"):
                break
            sub.append(word.replace("{}", _HOLE))  # a path found at run time
        found = _argv_trigger(sub, top, helpers, depth, line, tool)
        if found is not None:
            return found[0], True
    return None


def _argv_trigger(argv, top, helpers, depth, line, tool=_TF_TOOL):
    """`(word, unseen)` when this simple command runs the gated tool, or
    None. `unseen` means the lexer is not known to read that command (an
    alias, a wrapper it does not strip, a renamed binary): the line is then
    "could not tell" even when every word on it is plain. `line` is the
    reading of the whole line: `copies`, the names a command on it copies or
    links the tool to (`_copies_terraform`). `tool` is what is gated
    (`_TerraformTool`, or T-0009's `_DispatchTool`)."""
    unwrap, shell_args, pwsh_payload, ps_normalise, head_name, _lex = \
        helpers
    fed = []
    argv = unwrap(argv, {}, fed, {"cd": False})
    if not argv:
        return None
    first, args = argv[0], argv[1:]
    if _HOLE in first:
        # Could not tell which program runs: gated only when the line names
        # one of the words a line running the tool needs.
        return tool.hole(argv, top)
    direct = tool.direct(argv, fed, depth)
    if direct is not False:
        return direct
    if any(c in first for c in " \t\n"):
        # `watch "terraform destroy"`: the command word is itself a script.
        return _bash_trigger(" ".join(argv), top, helpers, depth + 1, line,
                             tool)
    head = head_name(first)
    if head == "busybox" and args and head_name(args[0]) in _GATE_SHELLS:
        head, args = head_name(args[0]), args[1:]
    if head in _GATE_SHELLS:
        has_c, positional = shell_args(args)
        if has_c and positional and _HOLE not in positional[0]:
            return _bash_trigger(positional[0], top, helpers, depth + 1,
                                 line, tool)
        if not has_c and positional and _HOLE not in positional[0] \
                and not tool.names(positional[0]):
            # `bash build.sh`: a script file, which crew does not read
            # (WHAT IT CANNOT SEE) -- not stdin, which the line may feed.
            return None
        named = tool.on_line(top, "bash")
        return None if named is None else (named, True)
    if head in _GATE_PWSH:
        payload = pwsh_payload(args)
        if payload is None or _HOLE in payload:
            named = tool.on_line(top, "bash")
            return None if named is None else (named, True)
        return ps_trigger(ps_normalise(payload)[0], helpers, depth + 1, tool)
    if head == "eval":
        # An expansion in the script is `_HOLE`, a control character, so the
        # reader gives up on it and the line-wide name decides.
        args = args[1:] if args[:1] == ["--"] else args  # `eval -- ...`
        return _bash_trigger(" ".join(args), top, helpers, depth + 1, line,
                             tool)
    if head == "find" and any(a in _FIND_EXEC for a in args):
        # What find runs is read as commands of their own; find runs
        # nothing else.
        return _find_exec_trigger(args, top, helpers, depth, line, tool)
    if head in _GATE_OPAQUE:
        # A script crew cannot split: its own words decide, or the whole
        # line's when a word is made at run time (`source <(...)`).
        own = tool.opaque(args, top)
        return None if own is None else (own, True)
    if head in line["copies"]:
        # `ln -sf /usr/bin/terraform tf && ./tf destroy`: the name the line
        # copied or linked the tool to, run with a verb. A line that only
        # mentions terraform (`cp -r terraform bk && git apply x.patch`,
        # `terraform fmt && kubectl apply -f k.yaml`) is not read this way,
        # and neither is a program crew does not know as a wrapper
        # (`strace`, `aws-vault exec`): Step 10, direct use only; README
        # "What the guard does not catch".
        return tool.copied(argv, top)
    return None


def _copies_terraform(cmds, head_name, copiers=_GATE_COPIERS,
                      source=_TF_TOOL.copy_source):
    """The names `cmds` copy or link the gated tool to: the last operand's
    basename, for a copier whose other operands name it (`source`)
    (`cp /usr/bin/terraform ./ls` -> `ls`)."""
    out = set()
    for argv in cmds:
        ops = [a for a in argv[1:] if not a.startswith("-")]
        if argv and head_name(argv[0]) in copiers and len(ops) > 1 \
                and any(source(a) for a in ops[:-1]):
            out.add(head_name(ops[-1].rstrip("/\\")))
    return out


def _bash_trigger(text, top, helpers, depth, line=None, tool=_TF_TOOL):
    """`(word, unseen)` for the first command in `text` that runs the gated
    tool, with `unseen` true when ANY such command is unseen. `line` is
    shared with every nested script, so a copy made inside `bash -c` still
    counts for the commands after it."""
    try:
        if _GATE_CONTROL_RE.search(text):
            raise _Unsure("a control character")
        cmds = []
        _GateReader(text, depth, cmds).read()
    except _Unsure:
        named = tool.on_line(text, "bash") or tool.on_line(top, "bash")
        return None if named is None else (named, True)
    line = {"copies": set()} if line is None else line
    line["copies"] |= _copies_terraform(cmds, helpers[4], _GATE_COPIERS,
                                        tool.copy_source)
    found, unseen = None, False
    for argv in cmds:
        hit = _argv_trigger(argv, top, helpers, depth, line, tool)
        if hit is not None:
            found = found or hit[0]
            unseen = unseen or hit[1]
    return None if found is None else (found, unseen)


# PowerShell commands that run a program an argument names, or give it another
# name (review round 5): `Start-Process terraform -ArgumentList destroy`,
# `Set-Alias tf terraform`. `Invoke-Expression` is read as the eval it is.
_PS_LAUNCHERS = frozenset((
    "set-alias", "sal", "new-alias", "nal", "import-alias", "ipal",
    "start-process", "saps", "start", "invoke-command", "icm", "start-job",
    "sajb", "start-threadjob", "invoke-item", "ii"))
_PS_EVAL = frozenset(("invoke-expression", "iex"))
_PS_COPIERS = frozenset(("copy-item", "copy", "cpi", "cp", "move-item", "move",
                         "mi", "mv", "new-item", "ni", "rename-item", "ren",
                         "rni"))
# A command word PowerShell runs as written: a name or a path, no `$`, `(`,
# `+` or quote left in it.
_PS_NAME_RE = re.compile(r"^[A-Za-z0-9_./\\:~-]+$")


def _ps_verb_on_line(normal):
    """`_verb_on_line` for normalised PowerShell."""
    named = names_terraform(normal, "powershell")
    if named is not None:
        return named
    return next((c for c in _name_candidates(normal, "powershell")
                 if c.lower() in _GATE_VERBS), None)


def _ps_argv_trigger(words, normal, helpers, depth, copies, tool=_TF_TOOL):
    """`(word, unseen)` when one PowerShell simple command -- the lexer's
    `words` -- runs the gated tool, or None: `_argv_trigger`'s rule, read the
    way PowerShell runs a line."""
    _unwrap, shell_args, pwsh_payload, ps_normalise, head_name, _lex = \
        helpers
    argv = [str(w) for w in words]
    if len(argv) > 2 and argv[0].startswith("$") and argv[1] in (
            "=", "+=", "-=", "*=", "/=", "??="):
        argv, words = argv[2:], words[2:]  # `$out = terraform destroy` runs
    if argv and argv[0] in ("&", "."):
        argv, words = argv[1:], words[1:]
    if not argv or len(argv) == 1 and (argv[0].startswith("$") or type(
            words[0]).__name__ != "_Bare"):
        # Nothing, or an expression PowerShell only prints: `$x`, a quoted
        # string (`$m = "terraform destroy"`, `('terraform destroy')`).
        return None
    first, args = argv[0], argv[1:]
    sym = tool.symbolic(argv, words, normal)
    if not _PS_NAME_RE.match(first):
        # `& $tf destroy`, `& ("terra"+"form") destroy`: which program runs is
        # made at run time. Gated only on a line naming one of the words a
        # line running the tool needs, as in bash.
        return tool.hole(sym, normal, "powershell")
    direct = tool.direct(sym, [], depth)
    if direct is not False:
        return direct
    head = head_name(first)
    if head in _GATE_PWSH:
        payload = pwsh_payload(args)
        if payload is not None and "$" not in payload:
            return ps_trigger(ps_normalise(payload)[0], helpers, depth + 1,
                              tool)
        named = tool.on_line(normal, "powershell")
        return None if named is None else (named, True)
    if head in _GATE_SHELLS:
        has_c, positional = shell_args(args)
        if has_c and positional:
            return _bash_trigger(positional[0], positional[0], helpers,
                                 depth + 1, None, tool)
        named = tool.on_line(" ".join(args), "powershell")
        return None if named is None else (named, True)
    if head in _PS_EVAL:
        script = " ".join(a for a in args if not a.startswith("-"))
        if not script:
            # `"terraform destroy" | iex`: the text arrives on the pipeline,
            # which this reads no further than the line's own words.
            named = tool.on_line(normal, "powershell")
            return None if named is None else (named, True)
        return ps_trigger(script, helpers, depth + 1, tool)
    opaque = head in _GATE_OPAQUE  # `cmd /c`, `wsl`, `ssh`: bash's rule
    # A parameter's value may be bound with a colon: `-FilePath:terraform`.
    values = [w.split(":", 1)[1] if w.startswith("-") and ":" in w else w
              for w in args]
    if opaque or head in _PS_LAUNCHERS or any(
            w.lower().startswith(("alias:", "function:")) for w in args):
        named = tool.on_line(" ".join(args), "powershell") if opaque \
            else tool.opaque(args, normal, values, words)
        return None if named is None else (named, True)
    if head in copies:
        # `Copy-Item terraform.exe ./tf; ./tf destroy`: the name the line
        # copied the tool to, run with a verb.
        return tool.copied(sym, normal, "powershell")
    return None


def ps_trigger(normal, helpers, depth=0, tool=_TF_TOOL):
    """`(word, unseen)` when normalised PowerShell `normal` RUNS terraform,
    terragrunt or tofu (or, with T-0009's `tool`, sends a workflow dispatch),
    else None -- the command-word rule bash has (`command_trigger`), with
    PowerShell's direct forms: `&` and `.`, `terraform.exe` or a path,
    `Start-Process terraform`, `pwsh -c`, `bash -c`, `Invoke-Expression`,
    `$(...)` and script blocks. A read-only subcommand is not counted, and a
    word that only mentions terraform (`git commit -m "fix terraform
    apply"`, `Select-String terraform *.md`) is data. `helpers` as for
    `command_trigger`."""
    if depth > _GATE_DEPTH:
        named = tool.on_line(normal, "powershell")
        return None if named is None else (named, True)
    cmds, subs = helpers[5](normal)
    argvs = [[str(w) for w in c.words] for c in cmds]
    copies = _copies_terraform(argvs, helpers[4], _PS_COPIERS,
                               tool.copy_source) | tool.ps_aliases(cmds, normal)
    hits = [ps_trigger(sub, helpers, depth + 1, tool) for sub in subs]
    hits += [_ps_argv_trigger(c.words, normal, helpers, depth, copies, tool)
             for c in cmds]
    hits = [h for h in hits if h is not None]
    if not hits:
        return None
    return hits[0][0], any(h[1] for h in hits)


def command_trigger(text, helpers):
    """`(word, unseen)` when bash `text` RUNS terraform, terragrunt or tofu
    -- as a command word, inside `bash -c`/`eval`/`pwsh -c`/a substitution,
    or behind a command word crew cannot read on a line naming terraform,
    destroy, apply or workspace -- else None. A read-only subcommand
    (`_tf_read_only`) is not counted. `unseen`: some such command is one the
    lexer is not known to read. `helpers` is cloud_guard's `(_unwrap,
    _shell_args, _pwsh_payload, _ps_normalise, _head_name, _lex_ps)`."""
    return _bash_trigger(text, text, helpers, 0)


def command_names_terraform(text, helpers):
    """The word `command_trigger` found, or None."""
    found = command_trigger(text, helpers)
    return None if found is None else found[0]


# --- workflow dispatches (T-0009) -------------------------------------------
#
# Two spellings of one act: `gh workflow run <wf>` and the REST call it makes,
# `gh api -X POST repos/<o>/<r>/actions/workflows/<wf>/dispatches`. It lives
# here rather than in `cloud_guard.py` for the reason the literal allowlist
# does: that module sits at `.pylintrc`'s max-module-lines, so it keeps only
# the call sites (`_literal_gate`, `_classify`'s `gh` branch, `_judge_one`).
#
# THE DISPATCH GRAMMAR (successor plan, 2026-09-27). Review rounds 1 and 2
# found nine ways past a parser that read what the lexer made of a line --
# stdin rewritten by a filter, a `<` or `0>&3` replacing it, a variable, a
# bracket glob, a script piped into bash -- each a shell construct the lexer
# read differently from bash. T-0005 met the same pattern and answered with
# the literal-word allowlist; this extends it to dispatches. A line the
# trigger (`dispatch_trigger`: T-0005's command-word reader, parametrised by
# `_DispatchTool`) finds sending a dispatch is judged only when
# `dispatch_first_non_literal` accepts every word and operator on it:
#
#     words      `_PLAIN_WORD_RE` words, or a whole single-quoted word `'...'`
#                with no `'` or control character inside (bash and PowerShell
#                both pass it verbatim). PowerShell also refuses `,` and a
#                leading `@`.
#     operators  `;` `&&` `||` `&` and newline between commands; `>` `>>`
#                `&>` `&>>` to a plain word; the exact token `2>&1`.
#
# Everything else -- `|` anywhere, every `<`-family operator, any other
# `N>&M`, `>|`, `<(`/`>(`, double quotes, `$'`, a backslash, `$`, a
# backquote, `*` `?` `[` `]` `{` `}` `~`, a tab or CR in a word, a control
# character -- and a dispatch the lexer is not known to read (inside `bash
# -c`/`eval`/`pwsh -c`, behind `xargs`/`parallel`/`find -exec`, an alias or a
# copy of gh made on the line, a command word made at run time), and gh
# reading its inputs from stdin or a file (`--json`, `--input`, `-F k=@f`),
# is "could not tell": `ENV_UNKNOWN` with `op: line-not-literal`, asked about
# and never allowed unattended. Stdin is never modelled. The grammar does not
# resolve; it recognises or refuses.
#
# A command word made at run time is read by its argv's SHAPE (`_hole_shape`),
# never by what the rest of the line mentions (review round 3): bash's `$X`
# (which may split into several words), an `xargs`/`parallel` placeholder,
# PowerShell's `& $x`, a `Start-Process` target (`_ps_values`) and a name an
# alias points at gh or a run-time value (`ps_aliases`); a PowerShell
# variable in gh's own argv is a hole too (`symbolic`). A malformed
# `environments` block in EITHER config layer is could-not-tell for every
# dispatch (`dispatchProblem`); the terraform layer keeps reading only the
# repo's.
#
# Once a line passes, the parser below reads it -- ONE flag parser
# (`_gh_words`) for both forms -- and `dispatch_environment` classifies it by
# the repo-only `environments.workflows` map (fnmatch, case-insensitive,
# against the argument as written). A workflow matching no key is not
# judged, as before. `dispatch_answer` is the one public road through all of
# it (T-0045, T-0072): the gate first, then the parser. `deploy_verdict` then
# applies T-0005's table with `guards.deployWorkflow` as the base policy,
# except that `allow` covers nonProd only. Not seen: an unlisted spelling of a
# deploy workflow (a display name or numeric id), the workflow YAML
# (`environment:` keys, `${{ inputs.* }}`), `gh run rerun`, `gh alias`, a
# `gh` copied or aliased by an earlier command, and a dispatch sent by `curl`.

DEPLOY_RULE = "deployWorkflow"

# The three environment classes. `cloud_guard` imports these, so the
# terraform layer and the dispatch layer cannot name a class differently.
# `unlisted` is the fourth answer `dispatch_answer` gives: nothing to judge.
ENV_NONPROD, ENV_PROD, ENV_UNKNOWN = "nonProd", "prod", "unknown"
ENV_UNLISTED = "unlisted"
_STATE_RANK = {ENV_UNLISTED: 0, ENV_NONPROD: 1, ENV_PROD: 2, ENV_UNKNOWN: 3}

# `cloud_guard.OP_UNREADABLE_LINE`'s value: a could-not-tell finding's `op`.
OP_LINE_NOT_LITERAL = "line-not-literal"

_GH_NAMES = ("gh", "gh.exe")
_DISPATCH_OPS = frozenset((";", "&&", "||", "&", "\n", ">", ">>", "&>", "&>>"))
_DISPATCH_REDIRECTS = frozenset((">", ">>", "&>", "&>>"))
_STDERR_TO_STDOUT = "2>&1"
_SINGLE_QUOTED_RE = re.compile(r"^'[^'\x00-\x1f\x7f]*'$")
_DISPATCH_WORD_ENDS = " \t\n;&|<>()"

# A word the parser still refuses to read as a value, though the grammar
# passed it: what a single quote kept verbatim (`'environment=$E'` sends the
# five characters `$E`) is a name no environment glob was written for, and
# a text `_classify` rebuilt from the lexer's words may carry what the lexer
# left unexpanded. Unknown, never a guess.
_DISPATCH_NON_LITERAL_RE = re.compile(r"[$`*?\[\]{}()<>|;&\s'\"\0]")
# A workflow NAME is a whole word, so a blank or a quote in it came from
# quoting (`gh workflow run 'Deploy Staging'`). Expansion and glob characters
# still make it unknown.
_WORKFLOW_NON_LITERAL_RE = re.compile(r"[$`*?\[\]{}~\0]")

# `gh` options that take a value, across both forms (`-R/--repo`, `-r/--ref`,
# the fields, and `gh api`'s own). A value is never a positional word. Every
# other short flag is a boolean (`-i`, `--paginate`); gh's flag parser
# (pflag) lets booleans cluster in front of a valued one: `-iX POST`.
_GH_VALUE_OPTS = frozenset((
    "-R", "--repo", "-r", "--ref", "-f", "--raw-field", "-F", "--field",
    "-X", "--method", "-H", "--header", "--input", "-q", "--jq", "-t",
    "--template", "-p", "--preview", "--hostname", "--cache"))
# `-f`/`--raw-field` send the value as written; `-F`/`--field` read a value
# starting with `@` from that file (`@-`: stdin).
_GH_FIELD_OPTS = {"-f": "raw", "--raw-field": "raw",
                  "-F": "typed", "--field": "typed"}
# gh prints help and runs nothing for either, standing alone before `--`
# (measured 2026-09-27, gh 2.46.0).
_GH_HELP = frozenset(("-h", "--help"))

# The REST dispatch endpoint, leading `/` or a full API URL allowed. The
# owner and repo may be gh's own `{owner}`/`{repo}` placeholders.
_DISPATCH_RE = re.compile(
    r"^(?:https?://[^/]+/)?/?repos/[^/]+/[^/]+/actions/workflows/([^/?#]+)"
    r"/dispatches/?(?:[?#].*)?$", re.IGNORECASE)
# A REST field naming a workflow input: `inputs[<name>]=<value>`.
_API_INPUT_RE = re.compile(r"^inputs\[([^\[\]]*)\]$")

# What an input occurrence is called when crew cannot tell its name: it may
# be any input, so it counts against every one.
_ANY_INPUT = "*"


def _gh_name(word):
    """True when `word` is gh as a command word: its last path part."""
    return word.replace("\\", "/").rsplit("/", 1)[-1].lower() in _GH_NAMES


def _dispatch_mentions(text, shell, wild=True):
    """`(gh, verb)` for the generous read of `text` (`_name_candidates`: quotes
    and escapes out, an expansion as a wildcard): the first word that could
    be gh -- a wildcard that could match it counts only when `wild` -- and
    whether any word is `workflow` or names a `dispatches` endpoint."""
    named, verb = None, False
    for part in _name_candidates(text, shell):
        words = _brace_expand(part) if "{" in part \
            and shell != "powershell" else [part]
        for word in words if words is not None else [part]:
            base = word.replace("\\", "/").rsplit("/", 1)[-1].lower()
            base = base[1:] if base.startswith("=") else base  # zsh's =gh
            could = wild and any(c in base for c in "*?[") and any(
                fnmatch.fnmatchcase(n, base) for n in _GH_NAMES)
            if named is None and (base in _GH_NAMES or could):
                named = part
            verb = verb or base == "workflow" or "dispatches" in word.lower()
    return named, verb


def _dispatch_shape(argv, fed=()):
    """True when `argv` -- gh, or a command word made at run time, and its
    arguments -- could send a dispatch: positionals that could be `workflow
    run ...` or `api <endpoint>` with the endpoint made at run time or
    matching `_DISPATCH_RE`. `_HOLE` stands for any words, and so does a
    word `xargs`/`parallel` (`fed`: `(via, placeholders)` pairs) fills in or
    appends. Other gh commands are never dispatch-shaped."""
    positionals, options, _help = _gh_words(_fed_args(argv[1:], fed))
    if any(_HOLE in name for name, _value in options):
        return True
    if not positionals:
        return False
    first = positionals[0]
    second = positionals[1] if len(positionals) > 1 else ""
    if _HOLE in first:
        return True
    if first == "workflow":
        return _HOLE in second or second == "run"
    if first == "api":
        return _HOLE in second or bool(_DISPATCH_RE.match(second))
    return False


def _fed_args(args, fed):
    """`args` with every word `xargs`/`parallel` (`fed`) fills in marked as
    `_HOLE`, and one more `_HOLE` for what they append."""
    reps = [r for _via, reps in fed for r in reps]
    args = [w + _HOLE if fed and ("{" in w or any(r in w for r in reps))
            else w for w in args]
    return args + [_HOLE] if fed else args


def _hole_shape(args, fed=(), split=True):
    """True when a command word made at run time, then `args`, could send a
    dispatch -- read from the argv's SHAPE, never from what the raw line
    mentions (review round 3: `$X $Y run deploy-prod.yml`, both words built
    at run time). The hole stands for any word; with `split` (bash splits an
    unquoted expansion, `parallel` runs a shell) for any WORDS, so it may
    hold `gh`, `gh workflow`, `gh workflow run [<wf>]` or `gh api
    [<endpoint>]`, and `args` need only be what could follow one of those:
    options and at most one positional, or `run ...`."""
    args = _fed_args(list(args), fed)
    if _dispatch_shape([_HOLE] + args):
        return True
    positionals = _gh_words(args)[0]
    return split and (len(positionals) <= 1 or positionals[0] == "run"
                      or bool(_DISPATCH_RE.match(positionals[0])))


# PowerShell parameters naming what a launcher runs or an alias stands for,
# and the commands that make an alias (`Set-Alias NAME VALUE`, in that order).
_PS_TARGET_PARAMS = ("-filepath", "-path", "-literalpath", "-value")
_PS_ALIASERS = frozenset(("set-alias", "sal", "new-alias", "nal"))


def _ps_runtime(word, text):
    """True when PowerShell makes `word`'s value at run time: a variable or a
    splat, or a word the lexer did not read bare that `text` does not hold
    quoted as written -- `(Get-X)`, whose value the lexer only guessed."""
    if "$" in word or word.startswith("@"):
        return True
    return type(word).__name__ != "_Bare" and not any(
        q + word + q in text for q in "'\"")


def _ps_values(words, text):
    """A PowerShell launcher's or alias's words as `(name, target, rest)`.
    For an alias (`Set-Alias NAME VALUE`, or `-Name`/`-Value`): its name and
    what it stands for. For a launcher: the value of `-FilePath`/`-Path`
    (else its first value) and every other value as the words it passes on
    -- `-ArgumentList 'workflow run x'` is three -- with a run-time value as
    `_HOLE`. Parameter names are dropped; a switch takes no value."""
    values, found, index = [], {}, 1
    while index < len(words):
        word, index = words[index], index + 1
        name, bound, value = str(word).partition(":")
        if type(word).__name__ != "_Bare" or not word.startswith("-"):
            values.append(word)
            continue
        if not bound and index < len(words) and not (type(
                words[index]).__name__ == "_Bare" and words[index].startswith("-")):
            value, index = words[index], index + 1
        if bound or value:
            found[name.lower()] = value
    target = next((found[p] for p in _PS_TARGET_PARAMS if p in found), None)
    if str(words[0]).lower() in _PS_ALIASERS:
        name = found.get("-name") or (values.pop(0) if values else None)
        return name, target or (values[0] if values else None), []
    if target is None and values:
        target = values.pop(0)
    values += [v for k, v in found.items() if k not in _PS_TARGET_PARAMS]
    rest = []
    for value in values:
        rest += [_HOLE] if "$" in value or value.startswith("@") or not \
            _ps_quoted(value, text) else re.split(r"[\s,]+", str(value))
    return None, target, [w for w in rest if w]


def _ps_quoted(word, text):
    """A value `text` spells literally: bare, or quoted as written."""
    return type(word).__name__ == "_Bare" or any(
        q + word + q in text for q in "'\"")


class _DispatchTool:
    """`_TerraformTool`'s questions, answered for a workflow dispatch. Every
    dispatch the lexer is not known to read as bash runs it is `unseen`: a
    nested script (`bash -c`, `eval`, `pwsh -c`), `xargs`/`parallel`, `find
    -exec`, zsh's `=gh`, a name the line copied or aliased gh to, a command
    word made at run time (read by `_hole_shape`). `fed` is
    `cloud_guard.scan`'s `(via, placeholders)` for a command `xargs` or
    `parallel` feeds, when the text is one the lexer already unwrapped."""

    def __init__(self, fed=()):
        self.fed = tuple(fed) if fed else ()

    @staticmethod
    def on_line(text, shell="bash"):
        named, verb = _dispatch_mentions(text, shell)
        return named if verb else None

    @staticmethod
    def names(word):
        return _gh_name(word)

    @staticmethod
    def hole(argv, top, shell="bash"):
        """A command word made at run time: gated when its argv's SHAPE could
        be a dispatch -- bash splits the word, PowerShell does not -- never
        by what the raw line mentions (review round 3)."""
        if not _hole_shape(argv[1:], (), shell != "powershell"):
            return None
        named = _dispatch_mentions(top, shell, wild=False)[0]
        return named or "a command word made at run time", True

    def direct(self, argv, fed, depth):
        first = argv[0]
        fed = list(fed) + ([self.fed] if self.fed else [])
        reps = [r for _via, reps in fed for r in reps]
        if fed and ("{" in first or any(r and r in first for r in reps)):
            # `xargs -I CMD CMD workflow run ...`: xargs or parallel fills the
            # command word in from input crew never reads -- a hole.
            return (first, True) if _hole_shape(argv[1:], fed) else None
        zsh = first.startswith("=") and _gh_name(first[1:])
        if not zsh and not _gh_name(first):
            return False
        if not _dispatch_shape(argv, fed):
            return None
        return first, bool(zsh or depth > 0 or fed)

    @staticmethod
    def copy_source(word):
        return _HOLE in word or _gh_name(word.lstrip("="))

    @staticmethod
    def copied(argv, _top, _shell="bash"):
        return (argv[0], True) if _dispatch_shape(argv) else None

    @staticmethod
    def opaque(args, top, launched=None, typed=None):
        shell = "bash" if launched is None else "powershell"
        if launched is not None:
            named = next((w for w in launched if _gh_name(w)), None)
            _alias, target, rest = _ps_values(typed, top)
            if target is not None and (_gh_name(str(target)) or _ps_runtime(
                    target, top)) and _dispatch_shape([_HOLE] + rest):
                # `Start-Process $x -ArgumentList 'workflow run x'`: what it
                # launches is gh or is made at run time, with a dispatch's
                # arguments (review round 3).
                return named or str(target)
        else:
            named, _verb = _dispatch_mentions(
                top if any(_HOLE in a for a in args) else " ".join(args), shell)
        return named if named and _dispatch_mentions(top, shell)[1] else None

    @staticmethod
    def symbolic(argv, words, text):
        """PowerShell's argv with every word it makes at run time as `_HOLE`
        (`gh $w run x`); the command word stays as written."""
        return argv[:1] + [_HOLE if _ps_runtime(w, text) else str(w)
                           for w in words[1:]]

    @staticmethod
    def ps_aliases(cmds, text):
        """The names the line points at gh or at a value made at run time --
        `Set-Alias`/`New-Alias`, or an `alias:`/`function:` provider path
        (`Set-Item alias:g $x`) -- each then run as a copy of gh would be."""
        out = set()
        for words in (list(c.words) for c in cmds if c.words):
            path = next((str(w) for w in words[1:] if str(w).lower().startswith(
                ("alias:", "function:"))), None)
            if str(words[0]).lower() in _PS_ALIASERS:
                name, target, _rest = _ps_values(words, text)
                targets = [target]
            elif path is not None:
                name, targets = path.split(":", 1)[1], [
                    w for w in words[1:] if str(w) != path
                    and not (type(w).__name__ == "_Bare" and w.startswith("-"))]
            else:
                continue
            if name and any(t is not None and (_gh_name(str(t)) or _ps_runtime(
                    t, text)) for t in targets):
                out.add(_head_name(str(name)))
        return out


def fed_dispatch(argv):
    """True when `argv` -- a command `xargs`/`parallel` feeds, whose command
    word they fill in -- literally continues as a dispatch (`CMD workflow run
    <wf>`, `CMD api <dispatches endpoint>`): only gh has that shape, so
    `cloud_guard.scan` leaves the line to the dispatch gate's could-not-tell
    finding when the gate made one (review round 3), instead of cloudGuard's
    unconditional "unreadable" refusal."""
    return _dispatch_shape(["gh"] + list(argv[1:]))


def dispatch_trigger(text, helpers, shell="bash", fed=()):
    """`(word, unseen)` when `text` sends a workflow dispatch -- gh as a
    command word with a dispatch's shape, read through `_unwrap`'s wrappers
    and into `bash -c`/`eval`/`pwsh -c`/substitutions, or behind a command
    word crew cannot read on a line naming gh, `workflow` or `dispatches` --
    else None. On a reading `_GateReader` gives up on, the generous raw-text
    read naming gh together with `workflow` or `dispatches` decides.
    `helpers` as for `command_trigger`."""
    tool = _DispatchTool(fed)
    if shell == "powershell":
        return ps_trigger(helpers[3](text)[0], helpers, 0, tool)
    return _bash_trigger(text, text, helpers, 0, None, tool)


def _dispatch_tokens(text):
    """`text` as `(kind, token, start, end)`: `word` (quotes kept) or `op` (a
    run of `;&|<>`, a paren, a newline). A single quote is read as bash reads
    it only when the word turns out to be one whole quoted word, which is all
    the grammar accepts."""
    tokens, pos = [], 0
    while pos < len(text):
        char = text[pos]
        if char in " \t":
            pos += 1
            continue
        end = pos + 1
        if char in ";&|<>":
            while end < len(text) and text[end] in ";&|<>":
                end += 1
            kind = "op"
        elif char in "()\n":
            kind = "op"
        else:
            end, quoted = pos, False
            while end < len(text) and (quoted or text[end] not in
                                       _DISPATCH_WORD_ENDS):
                quoted ^= text[end] == "'"
                end += 1
            kind = "word"
        tokens.append((kind, text[pos:end], pos, end))
        pos = end
    return tokens


def _dispatch_word_ok(word, shell):
    if shell == "powershell" and (word.startswith("@") or "," in word):
        return False  # a splat, or an array PowerShell passes as two words
    return bool(_PLAIN_WORD_RE.match(word) or _SINGLE_QUOTED_RE.match(word))


def _fd_redirect(tokens, index, text):
    """The text of an fd-numbered redirection starting at `tokens[index]`
    (`2>&1`, `0>&3`, `3<`, `2>log`) -- digits, then an operator and any
    word written against them -- or None when that token is not one."""
    kind, token, start, end = tokens[index]
    after = tokens[index + 1:index + 3] + [("end", "", -1, -1)] * 2
    oper, target = after[0], after[1]
    if kind != "word" or not token.isdigit() or oper[0] != "op" \
            or oper[2] != end or oper[1][0] not in "<>":
        return None
    return text[start:target[3] if target[2] == oper[3] else oper[3]]


def _dispatch_grammar(text, shell):
    """`(word, commands)`: the first token the dispatch grammar refuses, or
    None and the line's simple commands -- each a list of words, quotes
    removed, redirections dropped."""
    tokens = _dispatch_tokens(text) + [("end", "", -1, -1)]
    commands, words, index = [], [], 0
    while tokens[index][0] != "end":
        kind, token = tokens[index][:2]
        redirect = _fd_redirect(tokens, index, text)
        if redirect is not None:
            # An fd number: `2>&1` exactly, and nothing else.
            if redirect != _STDERR_TO_STDOUT:
                return redirect, []
            index += 3
            continue
        if kind == "word":
            if not _dispatch_word_ok(token, shell):
                return token, []
            words.append(token[1:-1] if token.startswith("'") else token)
        elif token in _DISPATCH_REDIRECTS:
            target = tokens[index + 1]
            if target[0] != "word" or not _PLAIN_WORD_RE.match(target[1]):
                return token, []
            index += 1  # its target, a plain word, is not an argument
        elif token in _DISPATCH_OPS:
            commands.append(words)
            words = []
        else:
            return token, []
        index += 1
    commands.append(words)
    return None, [c for c in commands if c]


def dispatch_first_non_literal(text, shell):
    """The first word or operator of `text` the dispatch grammar does not
    accept (THE DISPATCH GRAMMAR, above), or None when every one is."""
    return _dispatch_grammar(text, shell)[0]


def dispatch_text(argv):
    """`argv` -- words the lexer produced -- as a line the grammar reads back
    word for word: a plain word as it is, any other in single quotes, and one
    single quotes cannot hold (a `'` or a control character) left bare, so
    the grammar refuses it."""
    return " ".join(
        w if _PLAIN_WORD_RE.match(w) else
        w if "'" in w or _GATE_CONTROL_RE.search(w) or "\n" in w else
        f"'{w}'" for w in argv)


def _gh_words(args):
    """`(positionals, options, help)` for a `gh` command line -- THE parser
    for both dispatch forms: options in order as `(name, value)`, value None
    for a boolean flag. Split the way gh's flag parser (pflag) splits them:
    `--name=value`; a short cluster read one letter at a time, where the
    first letter that takes a value takes the rest of the cluster (`-iXPOST`,
    `-iX=POST`) or, if nothing is left, the next word (`-iX POST`); `--` ends
    the options. `help` is a standalone `-h`/`--help` before `--` that no
    valued option took as its value: gh prints help and sends nothing."""
    positionals, options, index, helped = [], [], 0, False
    while index < len(args):
        arg = args[index]
        if arg == "--":
            positionals.extend(args[index + 1:])
            break
        if arg in _GH_HELP:
            helped = True
        elif arg.startswith("--") and len(arg) > 2:
            name, sep, value = arg.partition("=")
            if not sep and name in _GH_VALUE_OPTS:
                value = args[index + 1] if index + 1 < len(args) else None
                index += 1
            options.append((name, value if sep or name in _GH_VALUE_OPTS
                            else None))
        elif arg.startswith("-") and len(arg) > 1:
            letters = arg[1:]
            while letters:
                name, letters = "-" + letters[0], letters[1:]
                if name not in _GH_VALUE_OPTS:
                    options.append((name, None))
                    continue
                if letters:
                    value = letters[1:] if letters.startswith("=") else letters
                else:
                    value = args[index + 1] if index + 1 < len(args) else None
                    index += 1
                options.append((name, value))
                break
        else:
            positionals.append(arg)
        index += 1
    return positionals, options, helped


def _dispatch_literal(value):
    return isinstance(value, str) and bool(value) \
        and not _DISPATCH_NON_LITERAL_RE.search(value)


def _workflow_literal(value):
    return isinstance(value, str) and bool(value.strip()) \
        and not _WORKFLOW_NON_LITERAL_RE.search(value)


def _field_input(raw, api):
    """`(name, value, why)` for one `-f`/`-F` field that is a workflow input,
    or None when it is not one. `value` None means crew cannot tell it.
    `gh workflow run` sends every field as an input; the REST body carries
    them as `inputs[<name>]`, and its top-level `ref` is the branch, never an
    input."""
    if raw is None:
        return None
    key, sep, value = raw.partition("=")
    if not sep:
        return None
    if api:
        match = _API_INPUT_RE.match(key)
        if match is None:
            if _dispatch_literal(key):
                return None
            return (_ANY_INPUT, None, f"the field `{raw}` names no literal "
                                      "key, so it may be any input")
        key = match.group(1)
    if not _dispatch_literal(key):
        return (_ANY_INPUT, None, f"the field `{raw}` names no literal input")
    if not _dispatch_literal(value):
        return (key, None, f"`{raw}` is not a literal value")
    return (key, value, "")


def _dispatch_reads(options):
    """The first option by which gh reads its inputs from stdin or a file --
    `--json`, `--input <any>`, a typed field `-F k=@...` -- or None. Crew
    never reads either, so a dispatch carrying one is could-not-tell."""
    for name, value in options:
        if name in ("--json", "--input"):
            return name if value is None else f"{name} {value}"
        if _GH_FIELD_OPTS.get(name) == "typed" and \
                (value or "").partition("=")[2].startswith("@"):
            return f"{name} {value}"
    return None


def _dispatch_endpoint(endpoint):
    """The `<wf>` of a REST dispatch endpoint; None when the endpoint is
    built at run time (so it may be one, naming a workflow crew cannot see);
    False when it is plainly some other endpoint."""
    match = _DISPATCH_RE.match(endpoint)
    if match:
        return match.group(1)
    if any(c in endpoint for c in ("$", "`", _HOLE)):
        return None
    return False


def _dispatch_from_run(rest, options):
    """`gh workflow run [<wf>] [-f|-F k=v]...`."""
    inputs = [f for f in (_field_input(v, api=False) for n, v in options
                          if n in _GH_FIELD_OPTS) if f is not None]
    return {"form": "workflow run", "workflow": rest[0] if rest else None,
            "extra": rest[1:], "inputs": inputs}


def _dispatch_from_api(rest, options):
    """`gh api [-X POST] repos/<o>/<r>/actions/workflows/<wf>/dispatches`, or
    None when the call is not a dispatch: another endpoint, or a method that
    is not POST. With no `-X`/`--method`, gh sends POST when any field or an
    `--input` body is given, and GET otherwise; a method that is not a
    literal may be POST."""
    if not rest:
        return None
    workflow = _dispatch_endpoint(rest[0])
    if workflow is False:
        return None
    methods = [v for n, v in options if n in ("-X", "--method")]
    fields = [v for n, v in options if n in _GH_FIELD_OPTS]
    if methods:
        method = methods[-1] or ""
        if _dispatch_literal(method) and method.upper() != "POST":
            return None
    elif not fields and not any(n == "--input" for n, _v in options):
        return None
    inputs = [f for f in (_field_input(v, api=True) for v in fields)
              if f is not None]
    return {"form": "api", "workflow": workflow, "extra": [],
            "inputs": inputs}


def dispatch_what(scope):
    """The finding's `what`: the command as crew read it."""
    workflow = scope.get("workflow")
    named = workflow if workflow is not None else "(no workflow named)"
    if scope.get("form") == "api":
        return f"gh api POST .../actions/workflows/{named}/dispatches"
    return f"gh workflow run {named}"


def dispatch_scopes(args):
    """The workflow dispatch gh's arguments `args` send, as a list of zero or
    one scope in the shape both forms share: `{"op": "deploy", "form",
    "workflow", "extra", "inputs": [(name, value-or-None, why)], "reads",
    "what"}`. None for a help request (`--help`) and for a `gh api` call
    that is not a dispatch. Read only after the grammar passed the line."""
    positionals, options, helped = _gh_words(args)
    scope = None
    if helped:
        return []
    if positionals[:2] == ["workflow", "run"]:
        scope = _dispatch_from_run(positionals[2:], options)
    elif positionals[:1] == ["api"]:
        scope = _dispatch_from_api(positionals[1:], options)
    if scope is None:
        return []
    scope.update(op="deploy", reads=_dispatch_reads(options))
    scope["what"] = dispatch_what(scope)
    return [scope]


def _dispatch_class(value, globs):
    return ENV_NONPROD if any(fnmatch.fnmatch(str(value).lower(), g.lower())
                              for g in globs) else ENV_PROD


def _dispatch_source(source, inputs, globs):
    """`(class, value, why)` for one `environments.workflows` value."""
    if not source.startswith("input:"):
        return _dispatch_class(source, globs), source, ""
    name = source[len("input:"):]
    seen = [o for o in inputs
            if o[0] == _ANY_INPUT or o[0].lower() == name.lower()]
    if not seen:
        return ENV_UNKNOWN, None, (f"no `{name}` input is given, and crew does "
                                   "not read the workflow's default")
    unknown = [why for _n, value, why in seen if value is None]
    if unknown:
        return ENV_UNKNOWN, None, "; ".join(unknown)
    values = sorted({value for _n, value, _w in seen})
    if len(values) > 1:
        return ENV_UNKNOWN, None, (f"the `{name}` input is given more than "
                                   "once, with different values: "
                                   + ", ".join(f"`{v}`" for v in values))
    return _dispatch_class(values[0], globs), values[0], ""


def dispatch_environment(scope, envs):
    """THE classifier for a workflow dispatch, whichever form it came in:
    `(class, value, why, key)`, or None when the dispatch is unclassified --
    `environments.workflows` is empty, or no workflow gh was given matches a
    key (fnmatch, case-insensitive, against the argument as written).

    Never None for what crew could not tell once a key may match: no
    workflow named (gh prompts), a workflow that is not a literal, a second
    workflow argument, and an input it cannot read are each `unknown`.
    `envs` is `cloud_guard.environments_config`'s dict."""
    workflows = envs.get("workflows") or {}
    if not workflows:
        return None
    named = [w for w in [scope.get("workflow")] + list(scope.get("extra", ()))
             if w is not None]
    keys = {w: [k for k in workflows if fnmatch.fnmatch(w.lower(), k.lower())]
            for w in named if _workflow_literal(w)}
    if named and len(keys) == len(named) and not any(keys.values()):
        return None
    if not named:
        return ENV_UNKNOWN, None, ("no workflow is named, so gh would prompt "
                                   "for one"), None
    odd = next((w for w in named if w not in keys), None)
    if odd is not None:
        return ENV_UNKNOWN, None, f"the workflow `{odd}` is not a literal", None
    if len(named) > 1:
        return ENV_UNKNOWN, None, ("gh takes one workflow, and this line names "
                                   + ", ".join(f"`{w}`" for w in named)), None
    workflow, matched = named[0], keys[named[0]]
    globs = envs.get("nonProd", [])
    results = {key: _dispatch_source(workflows[key], scope.get("inputs", []),
                                     globs) for key in matched}
    if len({(k, v) for k, v, _w in results.values()}) > 1:
        return ENV_UNKNOWN, None, (f"`{workflow}` matches keys that name "
                                   "different environments: "
                                   + ", ".join(sorted(matched))), None
    klass, value, why = results[matched[0]]
    return klass, value, why, matched[0]


def dispatch_engaged(envs):
    """True while the dispatch gate runs: `environments.workflows` lists a
    workflow, or the `environments` block cannot be read. A repo that never
    listed one sees no new refusal. Either config layer's malformed block
    counts (`dispatchProblem`, review round 3)."""
    return bool(envs.get("workflows") or _envs_problem(envs))


def _envs_problem(envs):
    """What makes `envs` unreadable for a dispatch: the repo block's problem,
    or the machine-global block's (`environments_config`'s
    `dispatchProblem`), else `""`."""
    return envs.get("problem") or envs.get("dispatchProblem") or ""


def _gate_helpers():
    """cloud_guard's reader helpers, for a caller that did not pass them.
    Imported at call time, never at load: cloud_guard imports this module."""
    import cloud_guard  # pylint: disable=import-outside-toplevel,cyclic-import
    return cloud_guard.GATE_HELPERS


def _not_literal(why, word, unseen):
    """`dispatch_answer`'s could-not-tell answer."""
    shown = word if word is None or len(word) <= 40 else word[:37] + "..."
    return ENV_UNKNOWN, why, {"op": OP_LINE_NOT_LITERAL, "word": shown,
                              "unseen": unseen,
                              "what": "a workflow-dispatch line"}


def dispatch_answer(text, shell, envs, fed=(), helpers=None):
    """THE one public road to a dispatch's environment (T-0045, T-0072):
    `(state, why, scope)` for the dispatches bash (or PowerShell, `shell`)
    would send running `text`, `state` in `nonProd | prod | unknown |
    unlisted`. Pure: `envs` is `cloud_guard.environments_config`'s dict.

    The grammar runs before any parsing, so no caller reaches the parser
    around it: a dispatch-shaped line with a word or operator the grammar
    refuses, a dispatch the lexer is not known to read, gh reading stdin or
    a file, or an `environments` block crew cannot read is `unknown` with
    `scope["op"] == "line-not-literal"` -- could not tell. Only then are the
    literal line's commands parsed and classified: `unlisted` when none is a
    dispatch of a listed workflow, else the most severe dispatch's state and
    scope, `scope["dispatches"]` holding every classified one. `fed` is
    `cloud_guard.scan`'s `(via, placeholders)` for a text the lexer already
    unwrapped from `xargs`/`parallel`."""
    if not dispatch_engaged(envs):
        return ENV_UNLISTED, "environments.workflows lists no workflow", None
    helpers = helpers or _gate_helpers()
    found = dispatch_trigger(text, helpers, shell, fed)
    if found is None:
        return ENV_UNLISTED, "the line sends no workflow dispatch", None
    word = dispatch_first_non_literal(text, shell)
    if word is not None:
        return _not_literal(f"`{word}` is not a plain literal", word, False)
    if found[1]:
        return _not_literal((
            f"it runs `{found[0]}` in a way crew does not follow -- a nested "
            "shell or eval, xargs, parallel or find -exec, another name for "
            "gh, or a command word made at run time"), None, True)
    if _envs_problem(envs):
        return _not_literal("the environments block cannot be read: "
                            f"{_envs_problem(envs)}", None, False)
    shaped, scopes = 0, []
    for argv in _dispatch_grammar(text, shell)[1]:
        argv = helpers[0](argv, {}, [], {"cd": False})
        if argv and _gh_name(argv[0]) and _dispatch_shape(argv):
            shaped += 1
            scopes += dispatch_scopes(argv[1:])
    reads = next((s["reads"] for s in scopes if s["reads"]), None)
    if reads is not None:
        return _not_literal(f"gh reads `{reads}` from stdin or a file, which "
                            "crew never reads", reads, False)
    if not shaped:
        # The reader found a dispatch the literal reading does not run as
        # one (`. gh ...` in PowerShell): the two disagree, so neither is
        # believed.
        return _not_literal("crew's two readings of this line disagree about "
                            "which command sends the dispatch", None, True)
    answers = []
    for scope in scopes:
        klass = dispatch_environment(scope, envs)
        if klass is not None:
            answers.append((klass[0], klass[2], dict(
                scope, value=klass[1], key=klass[3])))
    if not answers:
        return ENV_UNLISTED, "no dispatch on the line names a listed workflow", \
            None
    state, why, scope = max(answers, key=lambda a: _STATE_RANK[a[0]])
    return state, why, dict(scope, dispatches=answers)


def _dispatch_row(state, scope):
    return (state, scope.get("key"), scope.get("value"), scope.get("workflow"))


def dispatch_gate(text, shell, envs, lexed, helpers=None):
    """`cloud_guard.scan`'s check of the RAW line, once, at the top: the
    could-not-tell scope (`state` and `why` in it) that replaces every
    dispatch finding the lexer made, or None when those stand. `lexed` is
    their scopes. The line is could-not-tell when `dispatch_answer` says so
    for the raw text, and when its literal reading names other dispatches
    than the lexer's did -- a reading only one of the two made (`. gh` in
    PowerShell, which the lexer does not unwrap) is not judged by the other
    one's silence."""
    state, why, scope = dispatch_answer(text, shell, envs, (), helpers)
    if scope is not None and scope.get("op") == OP_LINE_NOT_LITERAL:
        return dict(scope, state=state, why=why)
    raw = sorted(_dispatch_row(st, s) for st, _w, s in
                 (scope or {}).get("dispatches", ()))
    if raw == sorted(_dispatch_row(s.get("state"), s) for s in lexed):
        return None
    _state, why, scope = _not_literal(
        "crew's two readings of this line disagree about what it dispatches",
        None, True)
    return dict(scope, state=ENV_UNKNOWN, why=why)


def dispatch_marker_key(text, scope):
    """What a dispatch's approval marker is keyed on: the whole command text,
    byte for byte -- never a subset of it, so a marker for one `<` path or
    one stdin cannot cover another -- and, for a classified dispatch, the
    workflow key and environment judged, so a config edit inside the TTL does
    not carry an approval across."""
    if scope.get("op") == OP_LINE_NOT_LITERAL:
        return text
    return text + "\n" + json.dumps(
        {"workflow": scope.get("key"),
         "environment": [scope.get("state"), scope.get("value")]},
        sort_keys=True)


def deploy_verdict(what, scope, out, envs, live):
    """`(decision, reason, policy, marker)` for a dispatch: T-0005's table
    with `guards.deployWorkflow` as the base policy, except that `allow`
    covers nonProd only (T-0009 amendment) -- a deploy never destroys, so
    T-0005's `allow` row would otherwise reach production and an unknown
    environment with nobody attending.

        block          deny, whatever the environment
        live marker    allow (the person approved this exact command)
        could not tell ask, naming the marker that approves this text
        nonProd        allow, logged (`ask` or `allow`)
        production     allow only under `prodUnattended` in both layers
                       (logged, and said on screen); otherwise ask
        unknown        ask

    `out` is `crew_config.guard_decision`'s dict, `live` the approval-marker
    test. `ask` becomes deny when nobody is attending (`cloud_guard.evaluate`).
    """
    klass, value, why = scope["state"], scope.get("value"), scope.get("why")
    base = f"[{DEPLOY_RULE}] {what}"
    policy, marker = out["policy"], out["marker"]
    if policy == "block":
        return "deny", f"{base}: {out['reason']}", "block", marker
    if live(marker):
        return "allow", f"{base}: approved for this command: {marker}", \
            policy, marker
    if scope.get("op") == OP_LINE_NOT_LITERAL:
        # The wording avoids the words other rows' reasons are checked for
        # (unknown, production), so this finding can never stand in for the
        # one a test expects the parser to make.
        return "ask", (f"{base} -- crew judges a workflow dispatch only when "
                       "every word on its line is a plain literal or a whole "
                       f"single-quoted word, so it could not tell where this "
                       f"line deploys: {why}. Such a line is asked about and "
                       "never allowed unattended; approve this exact text "
                       f"once with {marker}, or spell it with plain words "
                       "and `-f` fields to have it judged"), \
            "could-not-tell", marker
    head = f"{base}: guards.deployWorkflow is `{policy}`"
    if klass == ENV_NONPROD:
        return "allow", f"{head}; environment `{value}` is nonProd", \
            f"env:nonProd:{value}", marker
    if klass == ENV_PROD and envs.get("prodUnattended"):
        return "allow", (f"{head}; environment `{value}` is production and "
                         "environments.prodUnattended is true in both config "
                         "layers"), f"env:prod-unattended:{value}", marker
    if klass == ENV_PROD:
        return "ask", (f"{head}: environment `{value}` is production -- it "
                       "matches no environments.nonProd glob, and "
                       "environments.prodUnattended is not true in both "
                       "config layers (a deploy's `allow` covers nonProd "
                       "only)"), f"env:prod:{value}", marker
    return "ask", (f"{head}: environment unknown -- {why}. An environment "
                   "crew cannot identify is never allowed unattended"), \
        "env:unknown", marker


def judge_dispatch(scope, what, decide, text, envs, live):
    """`cloud_guard._judge_one`'s `(decision, reason, policy, marker,
    applies)` for a dispatch finding, whose scope carries `dispatch_answer`'s
    `state` and `why`. An unlisted dispatch is not judged at all, exactly as
    before T-0009 -- no row, no decision. `decide` is
    `crew_config.guard_decision` for this guard, handed
    `dispatch_marker_key`'s text; `text` is the whole command (`envs`'s
    `command` when `evaluate` set it)."""
    scope = scope or {}
    if scope.get("state") not in (ENV_NONPROD, ENV_PROD, ENV_UNKNOWN):
        return "allow", "", "", "", False
    out = decide(dispatch_marker_key(envs.get("command") or text, scope))
    return deploy_verdict(what, scope, out, envs, live) + (True,)

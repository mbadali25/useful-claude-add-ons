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
# pylint: disable=too-many-lines  # over 3400 after SRL-2308 r2; the split is owed (TODO.md)
import fnmatch
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

# The environment-dump guard's switch (L-0772): whether the PreToolUse
# Bash/PowerShell hook `env_guard.py` refuses a command whose own text prints
# the whole process environment, or a credential-named variable, into the
# agent's context. Unlike `cloudGuard` it is the policy as well as the switch:
# there are no per-rule keys behind it.
#
# `cloudGuard`'s vocabulary, order and split default, for the same CLAUDE.md
# reason: a hook that can block ships disabled.
#
#   off     the hook reads nothing but this key and lets every command through
#   report  every refusal the hook WOULD make goes to `.crew/guard.log` (rule,
#           form and decision, never the command text), and nothing is refused
#   block   the refusals are made
#
# Absent means `off`; a malformed value means `block`, the floor.
ENV_GUARD_NAMES = ("envGuard",)

# Every guard, in declaration order: the seven policy guards, the two
# production ones, the role-write guard, the cloud guard's switch, then the
# environment-dump guard's.
# `GUARD_DEFAULTS` is keyed off this, so a name that exists in none of the
# four tuples cannot reach the config block at all.
ALL_GUARD_NAMES = (GUARD_NAMES + PROD_GUARD_NAMES + ROLE_WRITE_GUARD_NAMES
                   + CLOUD_GUARD_NAMES + ENV_GUARD_NAMES)

GUARD_DEFAULTS = dict(
    [(name, GUARD_POLICY_DEFAULT) for name in GUARD_NAMES]
    + [(name, PROD_LEVEL_DEFAULT) for name in PROD_GUARD_NAMES]
    + [(name, ROLE_WRITE_DEFAULT) for name in ROLE_WRITE_GUARD_NAMES]
    + [(name, ROLE_WRITE_DEFAULT) for name in CLOUD_GUARD_NAMES]
    + [(name, ROLE_WRITE_DEFAULT) for name in ENV_GUARD_NAMES])

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
    if name in ROLE_WRITE_GUARD_NAMES or name in CLOUD_GUARD_NAMES \
            or name in ENV_GUARD_NAMES:
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


# T-0050. The owner's PERSONAL keys: settable in the machine-global file as a
# default for every repo, and combined per key by a rule of their own. A
# second table, not rows in `RATCHETED_KEYS`, because the rules differ in the
# one place that matters here: `effective_ratcheted` reads an ABSENT layer as
# the floor, so a global `autopilot.approval: self` over a repo that says
# nothing would resolve to the floor and could never carry a personal
# default. Here a layer that is silent imposes nothing.
#
# `kind` is `tiers` (order strictest first; exact match, so `1` is not
# `True`), `int-min` (a positive int, the smaller is stricter) or `value`
# (plain precedence, for a key that grants nothing). No key is in both tables.
#
# `scope.allowCliApproval` is NOT here yet. Its reader is
# `crew_ticket.cli_approval_allowed`, which reads the repo file alone, and
# that module is review harness (CLAUDE.md, T-0087), so its row lands with the
# reader change in a harness-only PR. A global value the guard does not read
# would be a report that contradicts the run.
PERSONAL_KEYS = {
    # L-0541: `backlog` works a goal's tickets past the first, so it ranks above `plan`.
    "autopilot.mode": ("tiers", ("off", "plan", "backlog")),
    "autopilot.maxPhases": ("int-min", None),
    "autopilot.deploy": ("tiers", ("none", "nonprod", "all")),
    "autopilot.approval": ("tiers", ("human", "risk", "self")),
    "autopilot.questions": ("tiers", ("human", "risk", "self")),
}

# Autopilot keys that are never global: read from `.crew/config.json` alone.
# Every key in `crew_state.AUTOPILOT_DEFAULTS` is a `PERSONAL_KEYS` row or a
# member here, and a test fails until a new key picks one. `maxAutoReplans`
# (T-0074) and `sleep` (T-0053) reached main after T-0050 was written and were
# repo-only there; they stay repo-only until a ticket decides how their two
# layers combine (`sleep` is a block, and `maxAutoReplans` 0 is a valid "off"
# that the `int-min` rule would read as unrecognised). T-0011's `ship`,
# `knownFailures` and `ciTimeoutMinutes` (batch 7) are repo-only by their spec:
# whether a checkout's PRs merge unattended, and which of its checks may fail,
# are facts about that checkout. T-0029's `maxLanes` and `reviewPolicy` (the wave) are repo-only too: how many lanes
# one checkout runs, and what its lanes do with a verdict, are that checkout's.
REPO_ONLY_AUTOPILOT = frozenset({"autopilot.maxAutoReplans", "autopilot.sleep", "autopilot.ship",
                                 "autopilot.knownFailures", "autopilot.ciTimeoutMinutes",
                                 "autopilot.maxLanes", "autopilot.reviewPolicy",
                                 # L-0541's caps: the spec's layer is `repo`.
                                 "autopilot.maxTicketsPerRun", "autopilot.maxTokensPerSession"})


def personal_rank(dotted, value):
    """The rank of `value` at the personal key `dotted`: its index in the
    tiers by exact match (type too), the int itself for `int-min`, and -1 for
    anything unrecognised -- BELOW the floor, so it can only narrow."""
    kind, order = PERSONAL_KEYS[dotted]
    if kind == "int-min":
        return value if _valid_phase_limit(value) else -1
    if kind != "tiers":
        return 0
    for index, allowed in enumerate(order):
        if value == allowed and type(value) is type(allowed):
            return index
    return -1


def _valid_phase_limit(value):
    return isinstance(value, int) and not isinstance(value, bool) and value >= 1


def effective_personal(dotted, repo_value, global_value, default):
    """`(value, held_down_by)` for a personal key, given both layers.

    A layer SETS the key when its value is not None (callers pass an absent
    key as None, and a `null` is silent too). Neither sets it: the default.
    One sets it: that value, whatever it is -- its reader validates it.

    Both set it:
      * `tiers` -- the LOWER rank wins, the repo's value on a tie. An
        unrecognised value ranks below the floor, so it wins and is returned
        RAW; the reader reads it as its floor and warns. `held_down_by` names
        the layer whose higher-ranked value lost.
      * `int-min` -- the smaller valid value. A layer whose value is not a
        positive int is ignored when the other is valid; neither valid
        returns the repo's raw value, which the reader warns about.
      * `value` -- the repo's.

    An unknown `dotted` raises KeyError: falling back to precedence would be
    the rule silently not happening.
    """
    kind, _order = PERSONAL_KEYS[dotted]
    if repo_value is None and global_value is None:
        return default, None
    if global_value is None:
        return repo_value, None
    if repo_value is None:
        return global_value, None
    if kind == "int-min" and not (_valid_phase_limit(repo_value)
                                  and _valid_phase_limit(global_value)):
        return (global_value if _valid_phase_limit(global_value)
                and not _valid_phase_limit(repo_value) else repo_value), None
    if kind in ("tiers", "int-min"):
        repo_rank = personal_rank(dotted, repo_value)
        global_rank = personal_rank(dotted, global_value)
        if global_rank < repo_rank:
            return global_value, "global"
        if repo_rank < global_rank:
            return repo_value, "repo"
    return repo_value, None


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
    "true", "which",
))

# `env` is NOT on that list, and its absence is the point. It is a WRAPPER:
# `env touch /tmp/x` runs `touch`, so a classifier that stopped at the
# executable name cleared every write on the machine behind four characters.
# It is handled in `_classify_segment` instead -- `env FOO=bar <cmd>` is
# whatever `<cmd>` is, and `env` carrying an option is unclassifiable (`-i`,
# `-u`, `-S`, `--chdir` each change what runs or where).
#
# Bare `env`, and `printenv` (dropped from the list above), are NOT reads
# (L-0772, BREAKING by narrowing): a production host's environment holds that
# host's credentials, and printing it into an agent's context is not what
# `prodServer: read` was meant to clear. `_classify_shell` also asks
# `env_guard.findings` first, so any environment dump the env guard recognises
# -- `cat /proc/1/environ`, `ps eww`, `echo $SOME_TOKEN` -- is a write here.
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
    environment -- and the caller turns that into a write too (L-0772).

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
        # which prints the host's environment, credentials included. Not a
        # read (L-0772).
        return "write"
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
    """A remote shell command line. EVERY segment must be a read, and no
    environment dump the env guard recognises may appear (L-0772)."""
    if any(token in text for token in _PROD_REDIRECTS):
        return "write"
    import env_guard  # pylint: disable=import-outside-toplevel
    if env_guard.findings(text, "bash"):
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
    # The three letters must be the name's own, not an extension's: `*.ps1`
    # or `*.exe` could match `terraform.ps1`, but so could every script on
    # the disk (SRL-2308).
    stem = re.sub(r"\.(?:exe|cmd|bat|ps1)$", "", base)
    letters = re.sub(r"\[[^\]]*\]|[*?]", "", stem)
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
# Command words after which bash may run text written earlier on the line
# (review round 5): a loop's next pass, a function body, a trap.
_GATE_DEFERS = frozenset(("for", "while", "until", "select", "function",
                          "trap", "coproc"))


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
        # outside the quotes (`<<'E\OF'` ends at `E\OF`), and so is a
        # delimiter quoted both ways (`<<"'END'"` ends at `'END'`; SRL-2308
        # r2): not read.
        mixed = "\\" in raw and ("'" in raw or '"' in raw)
        mixed = mixed or "'" in raw and '"' in raw
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
    """1.2.35's question for a command word made at run time, unchanged
    (SRL-2308 r3 put it back): the Step 8 name, or any word dequoting to
    destroy/apply/workspace. Such a word may be the tool, a shell or a
    wrapper whatever follows it (`$1 $2`, `$SHELL -c '...'`, `$0 <<< ...`),
    so the whole line decides."""
    named = names_terraform(top, "bash")
    if named is not None:
        return named
    return next((c for c in _name_candidates(top, "bash")
                 if c.lower() in _GATE_VERBS), None)


# --- the two fallbacks, read by command word (SRL-2308) ----------------------
#
# When `_GateReader` gives up on a line (`_Unsure`), or reads a lone
# assignment of a run-time value (`W=$S/x`, which runs nothing) or a program
# whose name is literal under a run-time directory (`$W/stub.sh apply`), the
# trigger used to fall back to "does any word on the line name terraform --
# or destroy, apply or workspace". A heredoc of Python, a `python3 -c` script
# or a `sed` range on a line with one `$VAR` in it then said "apply" and was
# refused. Those fallbacks now ask whether a COMMAND WORD could run
# terraform, terragrunt or tofu: directly, by path, behind a wrapper (`env`,
# `npx`, `sudo`, `timeout`, `xargs`, ...), or as a variable whose one literal
# value on the line is a path to a program that runs nothing else.
#
# FAIL-CLOSED (SRL-2308 r3). The narrowing only ever stops a mention from
# counting; it never decides that a command word crew cannot name is safe.
# Every command word made at run time -- `$1`, `"$@"`, `$0`, `$SHELL`,
# `${X:-y}`, `$(...)`, a backquote, a glob, a variable the line does not
# resolve, and a resolved one whose value is a bare name (an inherited
# function or alias may shadow it), a shell, an interpreter or a wrapper --
# is gated by 1.2.35's rule (`_verb_on_line`) whatever follows it. Quoted
# heredoc bodies and arguments are data only when fed to a program that is
# not a shell or an interpreter; a line that hands text to shell code
# (`bash`, `eval`, `ssh`, `source`, `parallel`, ...) keeps the mention rule
# (`names_terraform`) over the whole line, and interpreter code is judged by
# `_code_verdict`. If this reading cannot split the text either, it is the
# old name rule that decides.

# Verbs that change state, for a command word crew cannot resolve.
_FALLBACK_VERBS = frozenset((
    "apply", "destroy", "import", "state", "workspace", "taint", "untaint",
    "force-unlock", "run-all", "run", "refresh"))
# Command words that run the command named after them, possibly behind
# options and values crew does not parse here: any later word naming the tool
# counts. `ln`/`cp`/... put it under another name for a later command.
_FALLBACK_WRAPPERS = frozenset((
    "env", "npx", "bunx", "pnpx", "sudo", "doas", "command", "exec", "nohup",
    "nice", "ionice", "timeout", "stdbuf", "setsid", "time", "builtin",
    "unbuffer", "aws-vault", "chronic", "xargs", "chroot", "taskset",
    "caffeinate", "systemd-run", "strace", "ltrace", "gdb", "valgrind",
    "runuser", "su"))
# `npm exec terraform`, `pnpm dlx terraform`, `yarn dlx terraform`.
_FALLBACK_RUNNERS = {"npm": frozenset(("exec", "x")),
                     "pnpm": frozenset(("exec", "dlx")),
                     "yarn": frozenset(("exec", "dlx")),
                     "bun": frozenset(("x", "run"))}
# Command words whose arguments, stdin or heredoc are shell code crew does
# not split here: the whole line's mentions decide, as before SRL-2308.
_FALLBACK_SCRIPTS = (_GATE_SHELLS | _GATE_PWSH | _GATE_OPAQUE | frozenset((
    "eval", "watch", "parallel", "sem", "xonsh", "nu", "elvish", "rbash",
    "screen", "tmux", "nsenter", "unshare", "docker", "podman", "kubectl",
    "dtach", "expect")))
_FALLBACK_DECLARE = frozenset(("export", "declare", "local", "readonly",
                               "typeset"))
_FALLBACK_RESERVED = frozenset((
    "{", "}", "!", "if", "then", "else", "elif", "fi", "do", "done", "while",
    "until", "for", "in", "case", "esac", "select", "coproc", "[[", "]]"))
_FALLBACK_ASSIGN_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)(?:\[[^\]]*\])?"
                                 r"\+?=(.*)$", re.DOTALL)
# Reserved words that open and close a block whose body may run never, many
# times, or later (`f() { T=x; }`): an assignment inside one is not a value
# crew can rely on (SRL-2308 r2).
_FALLBACK_OPENERS = frozenset(("if", "while", "until", "for", "select",
                               "case", "{"))
_FALLBACK_CLOSERS = frozenset(("fi", "done", "esac", "}"))
# A variable as written: `$T` or `${T}`, nothing else (`${T/x/o}` is not).
_FALLBACK_REF_RE = re.compile(r"\$(?:\{([A-Za-z_][A-Za-z0-9_]*)\}"
                              r"|([A-Za-z_][A-Za-z0-9_]*))")
# Any other `$` (not `$'...'`/`$"..."`) or a backquote: made at run time.
_FALLBACK_LOOSE_RE = re.compile(r"`|\$(?!['\"])")
_FALLBACK_NAME_RE = re.compile(r"(?<![\w$])[A-Za-z_]\w*")
_FALLBACK_OPS = (";;&", ";;", ";&", "&&", "||", "|&", ";", "&", "|")
# Commands that set variables in ways this reading does not follow, and
# builtins that set the variable an argument names (`read "$N"` sets the
# one N names).
_FALLBACK_OPAQUE_SETTERS = frozenset(("source", ".", "eval"))
_FALLBACK_SETTERS = frozenset((
    "read", "mapfile", "readarray", "declare", "typeset", "local", "export",
    "readonly", "getopts", "let", "unset", "printf"))
# Wrappers whose options take no value (SRL-2308 r3): the program they run is
# the first word that is not an option, so once that is a literal program
# that runs nothing else, the words after it are its arguments, not command
# words (`nohup codex exec "$(cat prompt)"`). Behind any other wrapper every
# later word may be the command (`timeout 30 $T`, `sudo -u ops $T`).
_PLAIN_OPTION_WRAPPERS = frozenset(("nohup", "setsid", "command", "builtin"))


class _Line:  # pylint: disable=too-few-public-methods
    """What the fallback reads a command against: `text`, the code being
    split (a `bash -c` script, a substitution, or the line); `top`, the
    whole line, which 1.2.35's rule (`_verb_on_line`) reads."""

    def __init__(self, text, top):
        self.text, self.top = text, top


class _CommandSplitter:
    """`text` as simple commands of RAW words (quotes kept), bash's way only
    as far as word, command and heredoc boundaries go. Collects the bodies of
    `$(...)`, backquotes and `<(...)` -- code wherever they sit outside single
    quotes, an unquoted heredoc body included; a `$(...)`'s own commands are
    also among `commands`. `metas[i]` says where `commands[i]` sits: the
    operator `before` and `after` it, `nest` (1 at the top level, more in a
    subshell or a substitution), and the heredoc `bodies` (with whether each
    is quoted) and here-strings (`here`, raw) fed to it. Raises `_Unsure` on
    anything unclosed, and on what it does not follow (SRL-2308 r2): a
    substitution or a nested expansion inside `$((...))` or `${...}`, and a
    heredoc delimiter quoted both ways."""

    def __init__(self, text):
        self.text, self.pos = text, 0
        self.commands, self.metas, self.subs, self.pending = [], [], [], []
        self.depth = self.parens = 0

    def split(self):
        self._read(None)
        return self.commands, self.subs

    @staticmethod
    def _meta():
        return {"before": None, "after": None, "nest": 1, "bodies": [],
                "here": []}

    def _read(self, closer):  # pylint: disable=too-many-branches,too-many-statements
        cmd, word = [], []
        state = {"target": None, "before": None, "meta": self._meta(),
                 "parens": 0}
        self.depth += 1
        if self.depth > 4 * _GATE_DEPTH:
            raise _Unsure("nested too deep")

        def end_word():
            if word:
                if state["target"] == "here":
                    state["meta"]["here"].append("".join(word))
                if state["target"]:
                    state["target"] = None
                else:
                    cmd.append("".join(word))
            word.clear()

        def end_command(op):
            end_word()
            if cmd:
                state["meta"].update(before=state["before"], after=op,
                                     nest=self.depth + self.parens)
                self.commands.append(list(cmd))
                self.metas.append(state["meta"])
            cmd.clear()
            state["meta"], state["before"] = self._meta(), op

        def paren(step):
            state["parens"] += step
            self.parens += step

        text = self.text
        while self.pos < len(text):
            char = text[self.pos]
            if text.startswith("\\\n", self.pos):
                self.pos += 2
            elif char == "\\":
                word.append(text[self.pos:self.pos + 2])
                self.pos += 2
            elif char in " \t":
                end_word()
                self.pos += 1
            elif char == "\n":
                end_command("\n")
                self.pos += 1
                self._bodies()
            elif char == "#" and not word:
                while self.pos < len(text) and text[self.pos] != "\n":
                    self.pos += 1
            elif char == "(":
                end_command("(")
                self.pos += 1
                paren(1)
            elif char == ")" and state["parens"]:
                end_command(")")
                self.pos += 1
                paren(-1)
            elif char == ")" and closer == ")":
                end_command(")")
                self.pos += 1
                self.depth -= 1
                return
            elif char == ")":
                end_command(")")
                self.pos += 1
            elif char in "<>" and text[self.pos + 1:self.pos + 2] == "(":
                self.pos += 2
                start = self.pos
                self._read(")")
                self.subs.append(text[start:self.pos - 1])
                word.append("$(...)")
            elif text.startswith("<<<", self.pos):
                end_word()
                self.pos += 3
                state["target"] = "here"
            elif text.startswith("<<", self.pos):
                end_word()
                self.pos += 2
                strip = text[self.pos:self.pos + 1] == "-"
                self.pos += 1 if strip else 0
                self.pending.append(self._delimiter(strip) + (state["meta"],))
            elif char in "<>" or text.startswith("&>", self.pos):
                end_word()
                while self.pos < len(text) and text[self.pos] in "<>&|":
                    self.pos += 1
                state["target"] = "file"
            elif char in ";&|":
                op = next(o for o in _FALLBACK_OPS
                          if text.startswith(o, self.pos))
                end_command(op)
                self.pos += len(op)
            else:
                word.append(self._part())
        if closer is not None:
            raise _Unsure("an unclosed (")
        end_command(None)
        if self.pending and closer is None:
            raise _Unsure("a heredoc with no body")

    def _delimiter(self, strip):
        while self.text[self.pos:self.pos + 1] in (" ", "\t"):
            self.pos += 1
        start = self.pos
        while self.pos < len(self.text) and \
                self.text[self.pos] not in " \t\n;&|()<>":
            self.pos += 1
        raw = self.text[start:self.pos]
        # As `_GateReader._delimiter`: a spelling bash dequotes differently
        # from this reading is not read (`<<'E\\OF'` ends at `E\\OF`).
        # Quoted both ways (`<<"'END'"` ends at `'END'`): not read either.
        escaped_quote = "\\" in raw and ("'" in raw or '"' in raw)
        both = "'" in raw and '"' in raw
        odd = raw.count("'") % 2 or raw.count('"') % 2
        if not raw or escaped_quote or both or odd or \
                any(c in raw for c in "$`"):
            raise _Unsure("a heredoc delimiter crew cannot spell")
        quoted = any(c in raw for c in "'\"\\")
        delim = re.sub(r"\\(.)", r"\1", raw.replace("'", "").replace('"', ""))
        return delim, strip, quoted

    def _bodies(self):
        while self.pending:
            delim, strip, quoted, meta = self.pending.pop(0)
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
            meta["bodies"].append(("\n".join(lines), quoted))
            if not quoted:
                # Only an unquoted body's substitutions are code. A body fed
                # to a shell is the whole line's mention rule's (`script`);
                # one fed to an interpreter is its code (`_interpreter_names`).
                self.subs.extend(_unquoted_body_subs("\n".join(lines)))

    def _part(self):
        """One quoted run, substitution or character of a word, raw."""
        text, start = self.text, self.pos
        char = text[self.pos]
        if char == "'":
            end = text.find("'", self.pos + 1)
            if end == -1:
                raise _Unsure("an unclosed '")
            self.pos = end + 1
        elif char == '"':
            self.pos += 1
            while self.pos < len(text) and text[self.pos] != '"':
                if text[self.pos] == "\\":
                    self.pos += 2
                elif text[self.pos] in "$`":
                    self._dollar_or_tick()
                else:
                    self.pos += 1
            if self.pos >= len(text):
                raise _Unsure('an unclosed "')
            self.pos += 1
        elif char in "$`":
            self._dollar_or_tick()
        else:
            self.pos += 1
        if self.pending and "\n" in text[start:self.pos]:
            raise _Unsure("a quoted newline before a heredoc body")
        return text[start:self.pos]

    def _dollar_or_tick(self):
        text = self.text
        if text[self.pos] == "`":
            end = self.pos + 1
            while end < len(text) and text[end] != "`":
                end += 2 if text[end] == "\\" else 1
            if end >= len(text):
                raise _Unsure("an unclosed `")
            self.subs.append(text[self.pos + 1:end])
            self.pos = end + 1
        elif text.startswith("$((", self.pos):
            self.pos = _arithmetic_end(text, self.pos)
        elif text.startswith("$(", self.pos):
            self.pos += 2
            start = self.pos
            self._read(")")
            self.subs.append(text[start:self.pos - 1])
        elif text.startswith("${", self.pos):
            end = text.find("}", self.pos)
            if end == -1:
                raise _Unsure("an unclosed ${")
            if re.search(r"[`'\"\\{(]", text[self.pos + 2:end]):
                # `${X:-$(cmd)}`, `${X:-${Y}}`, `${X:-"}"}`: the first `}`
                # may not end it, and what is inside may run (SRL-2308 r2).
                raise _Unsure("a ${...} crew does not split")
            self.pos = end + 1
        elif text.startswith("$'", self.pos):
            match = _ANSI_SPAN_RE.match(text, self.pos)
            if match.end() - match.start() != len(match.group(1)) + 3:
                raise _Unsure("an unclosed $'")
            self.pos = match.end()
        else:
            self.pos += 1


def _arithmetic_end(text, pos):
    """Where the `$((...))` at `pos` ends. `_Unsure` when what is inside
    could run a command or end it elsewhere (`$(( $(cmd) + 1 ))`, a
    backquote, a paren or brace) -- this reading would skip it (SRL-2308
    r2)."""
    end = text.find("))", pos)
    if end == -1:
        raise _Unsure("an unclosed $((")
    if re.search(r"[`(){}]", text[pos + 3:end]):
        raise _Unsure("arithmetic crew does not split")
    return end + 2


def _unquoted_body_subs(body):
    """The `$(...)` and backquote bodies of an unquoted heredoc body: the
    only part of it that is code."""
    subs, pos = [], 0
    while pos < len(body):
        if body[pos] == "\\":
            pos += 2
        elif body.startswith("$((", pos):
            pos = _arithmetic_end(body, pos)
        elif body[pos] == "`" or body.startswith("$(", pos):
            splitter = _CommandSplitter(body)
            splitter.pos = pos
            splitter._dollar_or_tick()  # pylint: disable=protected-access
            subs.extend(splitter.subs)
            pos = splitter.pos
        else:
            pos += 1
    return subs


def _dequote(word):
    """A raw word without its quotes and escapes."""
    word = _ANSI_SPAN_RE.sub(lambda m: _ansi_c_decode(m.group(1)), word)
    word = re.sub(r"\\(.)", r"\1", word)
    return word.replace("'", "").replace('"', "")


def _shell_unquote(word):
    """Raw `word` after bash's quote removal: `'...'` as written, `"..."`
    with only its own escapes, `$'...'` decoded. Unlike `_dequote`, quotes
    inside a quoted run stay (`'print("x")'` is `print("x")`)."""
    out, pos = [], 0
    while pos < len(word):
        char = word[pos]
        if word.startswith("$'", pos):
            match = _ANSI_SPAN_RE.match(word, pos)
            out.append(_ansi_c_decode(match.group(1)))
            pos = match.end()
        elif char == "'":
            end = word.find("'", pos + 1)
            end = len(word) if end == -1 else end
            out.append(word[pos + 1:end])
            pos = end + 1
        elif char == '"':
            pos += 1
            while pos < len(word) and word[pos] != '"':
                if word[pos] == "\\" and word[pos + 1:pos + 2] in \
                        ("$", "`", '"', "\\", "\n"):
                    pos += 1
                out.append(word[pos:pos + 1])
                pos += 1
            pos += 1
        elif char == "\\":
            out.append(word[pos + 1:pos + 2])
            pos += 2
        else:
            out.append(char)
            pos += 1
    return "".join(out)


def _raw_expands(word):
    """True when raw `word` holds an expansion outside single quotes."""
    pos, in_dq = 0, False
    while pos < len(word):
        char = word[pos]
        if char == "\\":
            pos += 2
            continue
        if char == "'" and not in_dq:
            end = word.find("'", pos + 1)
            pos = len(word) if end == -1 else end + 1
            continue
        if char == '"':
            in_dq = not in_dq
        elif char == "`" or char == "$" and \
                re.match(r"[\w{(@*#?!$-]", word[pos + 1:pos + 2]):
            return True
        pos += 1
    return False


def _literal_value(raw):
    """The value of a raw assignment value `raw` when its program name is a
    plain literal, else None (SRL-2308 r2: `T=$X`, `T=$1`, `T=$(cat f)`,
    `T=/opt/tf/t*` are not values crew can read). Only a directory part may
    hold a variable (`S=$W/stub.sh` names `stub.sh`, as `$W/stub.sh` itself
    does); no substitution, glob, brace list, tilde or quote is left."""
    if any(c in _FALLBACK_REF_RE.sub("", raw) for c in "$`*?[]{}~()<>|;&!\n"):
        return None
    value = _dequote(raw)
    if any(c in value for c in "'\"\\") or \
            "$" in re.split(r"[/\\]", value)[-1]:
        return None
    return value


def _sets_unseen(words, rest):
    """True when command `words` (`rest`: after its leading reserved words)
    may set variables in a way `_resolved_vars` does not follow: it touches
    `IFS`, it is `source`/`.`/`eval` (behind a wrapper too), or a builtin
    that sets the variable an expansion names (`read "$N"`,
    `printf -v "$N"`) -- behind a wrapper too (SRL-2308 r4, r3-3:
    `command read "$N"`, `builtin mapfile "$N"`)."""
    if any("IFS" in w for w in words):
        return True
    heads = [_head_name(_dequote(w)) for w in rest
             if not _FALLBACK_ASSIGN_RE.match(w)]
    if not heads:
        return False
    wrapped = heads[0] in _FALLBACK_WRAPPERS
    if heads[0] in _FALLBACK_OPAQUE_SETTERS or \
            wrapped and set(heads) & _FALLBACK_OPAQUE_SETTERS:
        return True
    # Every setter the command may run: its head, or behind a wrapper any
    # later word (where the wrapped command starts is not parsed here, so
    # reading every word can only refuse more).
    setters = set(heads) & _FALLBACK_SETTERS if wrapped else \
        {heads[0]} & _FALLBACK_SETTERS
    if not setters or setters == {"printf"} and \
            not any(_dequote(w).startswith("-v") for w in rest[1:]):
        return False
    return any("$" in w or "`" in w for w in rest[1:])


def _resolved_vars(commands, metas):  # pylint: disable=too-many-branches
    """name -> the literal values bash may give it on this line, for each
    variable crew can rely on (SRL-2308 r2). A variable counts only when
    EVERY way the line sets it is a plain `NAME=literal` standing alone,
    or a `for NAME in` list of literals, at the top level and run
    unconditionally (not after `&&`/`||`/`|`, not in a pipeline, a
    subshell, a substitution, a block or a function body). Any other use of
    its name -- `read T`, `printf -vT`, `T+=x`, `declare -n`, `T=x cmd`,
    `${T:=x}`, `unset T`, `U=T` -- or a `source`/`.`/`eval`, an `IFS`, or a
    builtin that sets a variable named by an expansion (`read "$N"`)
    anywhere on the line, and it is not resolved: a command word made from
    it is decided at run time. Returns one map per command: a variable
    counts for a command only after its first assignment (`$T x; T=echo`
    runs the environment's T)."""
    values, first, tainted, depth = {}, {}, set(), 0
    scan = []  # (text, own name or None): every word, for other uses
    for index, (words, meta) in enumerate(zip(commands, metas)):
        lead, before = 0, depth
        while lead < len(words) and words[lead] in _FALLBACK_RESERVED:
            depth += (words[lead] in _FALLBACK_OPENERS) - \
                (words[lead] in _FALLBACK_CLOSERS)
            lead += 1
        if words[0] == "function":
            depth += words.count("{")  # `function g {`: a body follows
        rest = words[lead:]
        if depth < 0 or _sets_unseen(words, rest):
            return [{} for _ in commands]
        top = meta["nest"] == 1 and before == 0 and \
            meta["before"] in (None, ";", "\n")
        settled = top and depth == 0 and \
            meta["after"] in (None, ";", "\n", "&&", "||")
        if lead == 1 and words[0] in ("for", "select") and rest and \
                re.fullmatch(r"[A-Za-z_]\w*", rest[0]):
            found = [_literal_value(w) for w in rest[2:]] \
                if rest[1:2] == ["in"] else []
            scan.extend((w, None) for w in rest[1:])
            # `for f in LIST; do`: the `for` opened a block; its own
            # variable is set before the body runs, when the list is not
            # empty.
            if words[0] == "select" or not (top and depth == 1) or \
                    not found or None in found:
                tainted.add(rest[0])
            else:
                values.setdefault(rest[0], []).extend(found)
                first.setdefault(rest[0], index)
            continue
        if rest and all(_FALLBACK_ASSIGN_RE.match(w) for w in rest):
            for word in rest:
                name, raw = _FALLBACK_ASSIGN_RE.match(word).groups()
                scan.append((raw, name))
                value = _literal_value(raw) if re.match(
                    r"^[A-Za-z_]\w*=", word) else None
                if value is None or lead or not settled:
                    tainted.add(name)
                else:
                    values.setdefault(name, []).append(value)
                    first.setdefault(name, index)
            continue
        scan.extend((w, None) for w in words)
    for word, _own in scan:
        bare = _FALLBACK_REF_RE.sub(" ", word)
        tainted.update(n for n in values
                       if re.search(re.escape(n) + r"(?!\w)", bare))
    resolved = {n: v for n, v in values.items() if n not in tainted}
    while True:
        # A value naming another resolved variable (`S=$S/x`) is not
        # followed: every spelling's variables are then unresolved ones.
        loops = {n for n, vs in resolved.items() for v in vs
                 for m in _FALLBACK_REF_RE.finditer(v)
                 if (m.group(1) or m.group(2)) in resolved}
        if not loops:
            break
        for name in loops:
            del resolved[name]
    return [{n: v for n, v in resolved.items() if first[n] < index}
            for index in range(len(commands))]


def _resolve_word(word, resolved, limit=64):
    """Every spelling raw `word` takes once each `$NAME`/`${NAME}` in it is
    replaced by a value the line resolves it to (`_resolved_vars`): `[word]`
    when it holds no expansion, None when any expansion in it is not one
    crew resolves, or past `limit` spellings."""
    out, pos = [""], 0
    for match in _FALLBACK_REF_RE.finditer(word):
        literal = word[pos:match.start()]
        name = match.group(1) or match.group(2)
        if _FALLBACK_LOOSE_RE.search(literal) or name not in resolved:
            return None
        out = [o + literal + v for o in out for v in resolved[name]]
        if len(out) > limit:
            return None
        pos = match.end()
    if _FALLBACK_LOOSE_RE.search(word[pos:]):
        return None
    return [o + word[pos:] for o in out]


def _word_names_tool(word, resolved):
    """The word naming the tool that raw `word` could run as, or None: the
    word itself (`/usr/bin/terraform`, `te""rraform`, `$(which tofu)`,
    `${T:-terraform}`), or a spelling of it from the line's resolved
    variables that names one (`T=terraform; $T apply`,
    `T=terra; U=form; $T$U apply`)."""
    bare = _dequote(word).strip()
    if not bare or word[:1] in "'\"" and "$" not in word and \
            any(c.isspace() for c in bare):
        return None  # a quoted sentence is an argument, not a program
    named = names_terraform(word, "bash")
    if named is not None:
        return named
    spellings = _resolve_word(word, resolved)
    if spellings and spellings != [word] and any(
            names_terraform(s, "bash") is not None for s in spellings):
        return word
    return None


def _unresolved_head(word, resolved):
    """True when the program raw `word` runs is decided at run time in a
    way crew does not follow: a command substitution or a `${...}` with an
    operator anywhere in it (`$(cat f)`, `${T/x/o}`), a glob or brace list in
    its last path part (`/usr/bin/t*`, find's `{}`), or a variable there
    the line does not resolve (`$TF`, `$D/$TF`; SRL-2308 r2: `T=$X`,
    `for f in *.exe`). A literal last part is a name (`$T/stub`)."""
    if "`" in word or "$(" in word or \
            re.search(r"\$\{(?![A-Za-z_][A-Za-z0-9_]*\})", word):
        return True
    base = re.split(r"[/\\]", word)[-1]
    if re.search(r"[*?]|\[.*\]|\{.*\}", _FALLBACK_REF_RE.sub("", base)):
        # A glob or brace list; a `[` or `{` with no closer after it is
        # literal to bash (`[ -n "$X" ]` runs the test builtin, SRL-2308 r3).
        return True
    if "$" not in base:
        return False
    return _resolve_word(base, resolved) is None


def _runs_other(head):
    """True when program `head` runs something else that its arguments,
    stdin or environment name: a shell, an interpreter, a wrapper, a script
    runner, `eval`/`source`, `find`, a copier."""
    return (head in _FALLBACK_SCRIPTS or head in _FALLBACK_WRAPPERS
            or head in _FALLBACK_RUNNERS or head in _FALLBACK_DECLARE
            or head in _FALLBACK_OPAQUE_SETTERS or head in _GATE_COPIERS
            or head == "find" or _interp_family(head) is not None)


def _known_value(value):
    """True when a command word the line spells as `value` (one of its
    resolved variables' values) names a program crew can rely on (SRL-2308
    r3): one word, a PATH -- a bare name (`T=ls`) may be an inherited
    function or alias, so it is not -- whose program runs nothing else
    (`_runs_other`), or is the tool itself, which the caller then names."""
    if not value or any(c.isspace() for c in value) or \
            not re.search(r"[/\\]", value):
        return False
    base = re.split(r"[/\\]", value)[-1]
    return bool(base) and (_names_tool(base) or not _runs_other(
        _head_name(base)))


def _expand_known(text, resolved, heredoc=False):  # pylint: disable=too-many-branches
    """Raw `text` after bash's expansion and quote removal, when every
    expansion in it is a variable the line resolves to ONE literal value
    (`_resolved_vars`); None when any is not -- the text is then made at
    run time (SRL-2308 r3). `heredoc`: an unquoted heredoc body, where
    quotes are literal and only `\\$`, `` \\` ``, `\\\\` and a newline are
    escapes."""
    out, pos, quote = [], 0, None
    bare = not heredoc  # quotes are syntax only outside a heredoc body
    while pos < len(text):
        char, nxt = text[pos], text[pos + 1:pos + 2]
        if quote == "'":
            end = text.find("'", pos)
            end = len(text) if end == -1 else end
            out.append(text[pos:end])
            pos, quote = end + 1, None
        elif char == "\\":
            special = "$`\\\n" if heredoc else '$`"\\\n'
            if not nxt or (heredoc or quote) and nxt not in special:
                out.append("\\")
                pos += 1
            else:
                out.append("" if nxt == "\n" else nxt)
                pos += 2
        elif bare and quote is None and text.startswith("$'", pos):
            match = _ANSI_SPAN_RE.match(text, pos)
            out.append(_ansi_c_decode(match.group(1)))
            pos = match.end()
        elif bare and quote is None and text.startswith('$"', pos):
            pos += 1  # `$"..."`: the string, translated -- read as written
        elif bare and quote is None and char == "'":
            quote, pos = "'", pos + 1
        elif bare and char == '"':
            quote, pos = (None if quote == '"' else '"'), pos + 1
        elif char == "`":
            return None
        elif char == "$":
            ref = _FALLBACK_REF_RE.match(text, pos)
            if ref is not None:
                values = resolved.get(ref.group(1) or ref.group(2)) or []
                if len(values) != 1 or any(c in values[0] for c in "$`"):
                    return None
                out.append(values[0])
                pos = ref.end()
            elif nxt and re.match(r"[{(0-9@*#?!$-]", nxt):
                return None
            else:
                out.append("$")
                pos += 1
        else:
            out.append(char)
            pos += 1
    return "".join(out)


# Interpreters that run code given on their command line, or read from
# stdin when given no script (SRL-2308 r2). Per family: the option letters
# that take the code (`-c`, `-e`), that take a value (the rest of the word,
# or the next word), that take only the rest of the word, and that name a
# module or file to run instead (`python -m`, `php -f`); long options that
# take the code or a value; a subcommand that takes the code (`deno eval`);
# the family, whose code `_code_verdict` reads. Perl's `-M`/`-m` value is
# code too (`-M'5;system "x"'` runs `use 5;system "x";`).
_INTERPRETERS = (
    (re.compile(r"^(?:python|pypy|py)[0-9.]*$"),
     ("c", "WXQ", "", "m", (), (), None, "python")),
    (re.compile(r"^(?:node|nodejs|bun)$"),
     ("ep", "r", "", "", ("--eval", "--print"),
      ("--require", "--import", "--loader", "--experimental-loader"), None,
      "node")),
    (re.compile(r"^perl[0-9.]*$"),
     ("eEMm", "", "lI0ixCdDV", "", (), (), None, "perl")),
    (re.compile(r"^ruby[0-9.]*$"),
     ("e", "ICEr", "x0lKTWd", "", (), (), None, "ruby")),
    (re.compile(r"^php[0-9.]*$"),
     ("rBRE", "dczt", "", "f", (), (), None, "php")),
    (re.compile(r"^deno$"), ("", "", "", "", (), (), "eval", "node")),
)
# The tool named in interpreter code: a word or a path's last part, never a
# directory (`terraform/x`) or a dotted file (`terraform.tfstate`).
_CODE_MENTION_RE = re.compile(
    r"(?<![\w.-])(?:terraform|terragrunt|tofu)(?:\.(?:exe|cmd|bat|ps1))?"
    r"(?![\w.\\/-])", re.IGNORECASE)
# Names inert code may use: printing, and nothing that reaches a process,
# a module, an attribute crew does not know, or evaluation.
_INERT_NAMES = frozenset((
    "print", "puts", "p", "pp", "say", "echo", "printf", "console", "log",
    "info", "warn", "error", "debug", "sys", "stdout", "stderr", "write",
    "flush", "end", "sep", "STDOUT", "STDERR", "True", "False", "None",
    "true", "false", "null", "nil", "undefined"))
_INERT_PUNCT = frozenset(" \t\r\n()[],;:.+-*/%=<>!&|^~?0123456789")


def _interp_family(head):
    """The option table of interpreter `head`, or None."""
    return next((spec for regex, spec in _INTERPRETERS if regex.match(head)),
                None)


def _interp_codes(spec, words):  # pylint: disable=too-many-branches
    """`(codes, stdin)` for an interpreter's argument words (quotes
    removed): `codes` as `(index, text)`, the code an option gives and the
    word it is in; `stdin` true when it is given no code, script or module,
    so it runs what it reads from stdin."""
    code, value, rest, script_letters, long_code, long_value, sub = spec[:7]
    codes, script, index = [], False, 0
    while index < len(words) and not script:
        word = words[index]
        if word in ("-", "--"):
            break
        if word.startswith("--"):
            name, equals, given = word.partition("=")
            if name in long_code and equals:
                codes.append((index, given))
            elif name in long_code and index + 1 < len(words):
                index += 1
                codes.append((index, words[index]))
            elif name in long_value and not equals:
                index += 1
        elif word.startswith("-") and len(word) > 1:
            for pos in range(1, len(word)):
                letter, tail = word[pos], word[pos + 1:]
                if letter not in code and any(c in code for c in tail):
                    # A code letter later in the bundle may be one: `-lne`,
                    # `-pe`, `-i.bak -e` (SRL-2308 r3, fail closed: reading
                    # a value as code can only refuse more).
                    continue
                if letter in code + value + script_letters:
                    if not tail and index + 1 < len(words):
                        index += 1
                        tail = words[index]
                    elif not tail and letter in code:
                        # `xargs python3 -c`: the code comes from elsewhere
                        # on the line; read it as stdin's.
                        return codes, True
                    if letter in code:
                        codes.append((index, tail))
                    script = letter in script_letters
                    break
                if letter in rest:
                    break
        elif sub is not None and word == sub:
            codes.extend((i, w) for i, w in enumerate(words[index + 1:],
                                                       index + 1)
                         if not w.startswith("-"))
            return codes, False
        else:
            script = True
        index += 1
    return codes, not codes and not script


def _code_is_inert(code, hash_comments=False):
    """True when interpreter `code` can only print: outside its string
    literals it uses nothing but `_INERT_NAMES`, numbers and plain
    punctuation, and no string interpolates (`#{}`, `${}`, `{$`, `@{`, a
    backquote, an f-string's prefix is a name it does not allow).
    `hash_comments` (python, perl, ruby, php): a `#` after a blank, `;` or
    `)` starts a comment to the end of the line (SRL-2308 r3, r2-6) -- not
    ruby's `?#` (a character) nor PHP's `#[` (an attribute)."""
    pos = 0
    while pos < len(code):
        char = code[pos]
        if char == "#" and hash_comments and code[pos + 1:pos + 2] != "[" \
                and (pos == 0 or code[pos - 1] in " \t\r\n;)"):
            end = code.find("\n", pos)
            pos = len(code) if end == -1 else end
        elif char in "'\"":
            quote = code[pos:pos + 3] if code[pos:pos + 3] in ("'''", '"""') \
                else char
            end = pos + len(quote)
            while end < len(code) and not code.startswith(quote, end):
                end += 2 if code[end] == "\\" else 1
            if end >= len(code) or re.search(r"#\{|\$\{|\{\$|@\{|\$\(",
                                             code[pos:end]):
                return False
            pos = end + len(quote)
        elif char.isalpha() or char == "_":
            name = re.match(r"\w+", code[pos:]).group(0)
            if name not in _INERT_NAMES:
                return False
            pos += len(name)
        elif char in _INERT_PUNCT:
            pos += 1
        else:
            return False
    return True


# --- interpreter code (SRL-2308 r3, L-0871) ----------------------------------
#
# Python and node code is REFUSED when it can start a process AND the line
# or the code names the tool, or when it reaches a process AND builds the
# tool's name (`'ter'+'raform'`, `chr(`, a join, a format, an f-string, a
# decode). A process-reaching code that names nothing and builds nothing, and
# code that only reads its environment or imports a library (`import os`,
# `import requests`, `process.env`), passes: "could not tell what python does"
# is no longer a refusal on its own (L-0871). A command read from input, a
# file or an environment variable that the line never names is therefore not
# caught (README "What the guard does not catch"). perl, ruby, PHP and deno
# keep the older, wider reading: a process API or any way to reach one by a
# name the code computes. For Python, "reaches a process" is `_PY_REACH_RE`;
# for node, `_NODE_REACH_RE`. A shell expansion the line does not resolve
# makes the code run-time: 1.2.35's rule (`_verb_on_line`) decides first.

# Python names that reach a process, or reach one by a computed name: the
# process APIs, `os`/`posix`/`nt` themselves, attribute and frame access,
# evaluation, and PyYAML's unsafe loaders (`!!python/object/apply:`). Read
# over the code outside its plain string literals (`_py_without_text`): a
# placeholder such as `"__COUNTS__"` is text; an f-string is code.
_PY_REACH_RE = re.compile(
    r"system|popen|spawn|fork|exec|subprocess|\bpty\b|\bposix\b|\bnt\b"
    r"|getattr|setattr|delattr|__\w+__|\bvars\b|\bglobals\b|\blocals\b"
    r"|\beval\b|\bcompile\b|breakpoint|\bhelp\b|\bmodules\b|_getframe"
    r"|\bf_(?:globals|builtins|locals|back)\b|\b(?:tb|gi|cr|ag)_frame\b"
    r"|\byaml\s*\.\s*(?!(?:safe_load|safe_load_all|safe_dump|safe_dump_all"
    r"|dump|dump_all|YAMLError)\b)\w|\bfrom\s+yaml\s+import\b|Loader\b"
    r"|ctypes|cffi|importlib|runpy|startfile")
# The reach words and bare `os`: what the mention rule reads.
_PY_SPAWN_RE = re.compile(_PY_REACH_RE.pattern + r"|\bos\b")
# Modules Python code may import and still not start a process: pure data
# and text, none with a process API (every route from one of them to `os`
# goes through a name `_PY_SPAWN_RE` reads). Any other import may run code
# crew cannot see. Only what tonight's real rows import, plus their kin.
_PY_SAFE_MODULES = frozenset((
    "sys", "json", "re", "yaml", "math", "hashlib", "collections",
    "textwrap", "difflib", "csv", "datetime", "time", "string", "itertools",
    "pathlib"))
_PY_IMPORT_RE = re.compile(
    r"\bfrom\s+([\w.]+)\s+import\b"
    r"|\bimport\s+([\w.]+(?:\s+as\s+\w+)?(?:\s*,\s*[\w.]+(?:\s+as\s+\w+)?)*)")
# The only names a Python command can use and still be literal: imports, the
# process APIs, their plain keyword arguments, constants.
_PY_STATIC_NAMES = frozenset((
    "import", "from", "as", "os", "subprocess", "sys", "exit", "system",
    "popen", "run", "call", "check_call", "check_output", "Popen", "execv",
    "execvp", "execl", "execlp", "execve", "execvpe", "execle", "execlpe",
    "spawnv", "spawnvp", "spawnl", "spawnlp", "posix_spawn", "posix_spawnp",
    "P_WAIT", "shell", "check", "cwd", "text", "capture_output", "stdout",
    "stderr", "PIPE", "DEVNULL", "STDOUT", "True", "False", "None", "print",
    "timeout", "returncode", "wait"))
# A perl regex substitution with the `e` (evaluate) modifier.
_PERL_E_FLAG = r"|\bs\b.*[^\w\s][a-z]*e[a-z]*\s*(?:[;)}]|$)"
# Perl, ruby and node/deno: a process API, or any way to reach one by a name
# the code computes (perl's `&{...}`, `->$m`, `::`; ruby's `send`, `method`;
# node's `require`, `[...]` member access, `constructor`).
_FAMILY_SPAWN_RE = {
    "perl": re.compile(
        r"system|exec|\bqx\b|readpipe|`|\bopen|pipe|fork|syscall|eval|\bdo\b"
        r"|require|\buse\b|\bno\b|::|->|&|\*\s*\{|\bcan\b|\bsort\b|SIG"
        r"|AUTOLOAD|DESTROY|bless|\btie|goto|\$\^" + _PERL_E_FLAG,
        re.MULTILINE),
    "ruby": re.compile(
        r"system|exec|spawn|`|%x|popen|Open3|PTY|Process|fork|Kernel|\bopen"
        r"|send|method|const_get|eval|binding|syscall|\bload\b|require"
        r"|ObjectSpace|::|Object|Class|Module|instance_|define|\bcall\b"
        r"|to_proc|&|trap|at_exit|\bIO\b|Signal|__\w+__"),
    "node": re.compile(
        r"require|import|process|child|exec|spawn|fork|eval|Function"
        r"|constructor|prototype|__proto__|Reflect|global|\bvm\b|[Ww]orker"
        r"|Deno|Bun|binding|dlopen|module|\[|`|\bthis\b|\bself\b|\bwindow\b"
        r"|Proxy|setTimeout|setInterval|setImmediate|WebAssembly|\bwith\b"
        r"|arguments"),
}

# Node code that reaches a process, or a name it computes: the mention
# rule's list without the words that only read the environment or load a
# library (`process`, `require`, `import`, `global`; L-0871).
_NODE_REACH_RE = re.compile(
    r"child|exec|spawn|fork|eval|Function|constructor|prototype|__proto__"
    r"|Reflect|\bvm\b|[Ww]orker|Deno|Bun|binding|dlopen|module|\[|`"
    r"|\bthis\b|\bself\b|\bwindow\b|Proxy|setTimeout|setInterval"
    r"|setImmediate|WebAssembly|\bwith\b|arguments")
# Ways code assembles a name at run time (L-0871), read next to a reach word.
_PY_ASSEMBLY_RE = re.compile(
    r"chr\s*\(|\bbytes\b|\bbytearray\b|fromhex|unhexlify|base64|b64"
    r"|\bdecode\b|\[\s*:\s*:\s*-1\s*\]|\breversed\b|\.\s*join\b"
    r"|\.\s*format\b|\bord\b|\bmap\b|\bcodecs\b"
    # `%` formatting: after a string literal, or with a literal operand
    # (`'...' % x`, `fmt % ('a',)`), never plain arithmetic (`5 % 2`).
    r"|['\"]\s*%|%\s*['\"(\[{]"
    # An f-string or t-string, the prefix letters in either order and case.
    r"|\b(?:[rR][fFtT]|[fFtT][rR]?)(?=['\"])")
_NODE_ASSEMBLY_RE = re.compile(
    r"fromCharCode|fromCodePoint|Buffer|atob|\.\s*join\b|\.\s*concat\b"
    r"|\.\s*replace|\.\s*reverse|\.\s*split|\.\s*slice|\.\s*substr"
    r"|\.\s*repeat|\$\{|\bunescape\b|decodeURI")
# A string literal, its prefix letters (any order and case) included.
_LIT_RE = re.compile(
    r"""(?:[A-Za-z]{1,2}(?=['"`]))?"""
    r"""(\'\'\'(?:\\.|[^\\])*?\'\'\'|\"\"\"(?:\\.|[^\\])*?\"\"\""""
    r"""|'(?:\\.|[^'\\\n])*'|"(?:\\.|[^"\\\n])*"|`(?:\\.|[^`\\])*`)""",
    re.S)
# What may sit between two literals that are one name: blanks, `+`, commas,
# brackets, `*`, `.join`, a line continuation.
_RUN_GAP_RE = re.compile(
    r"(?:[\s+,\[\]()*.%]|join|\\\n|\#[^\n]*|//[^\n]*|/\*[\s\S]*?\*/)*\Z")
# A call that starts a process, and the shell expansion in its argument.
_PROC_CALL_RE = re.compile(
    r"\b(?:system|popen|spawn\w*|exec\w*|fork\w*|call|run|check_output"
    r"|check_call|Popen|getoutput|getstatusoutput|startfile)\s*\(")
_CODE_EXPANSION_RE = re.compile(r"[$`]")
_TOOL_SPELLINGS = ("terragrunt", "terraform", "tofu")


class InterpreterReason(str):
    """Why a line that runs interpreter code is refused: the second element
    `_argv_trigger` returns instead of `True` (L-0871), so the finding quotes
    the construct that caused it."""


class InterpreterHit(str):
    """The word naming why interpreter code may run the tool, with `why`: the
    construct, in words, for `InterpreterReason`. A `str` to every reader."""
    why = ""

    def __new__(cls, word, why):
        hit = super().__new__(cls, word)
        hit.why = why
        return hit


def _decode_escapes(text):
    """`text` with its hex, unicode and octal escapes decoded."""
    def one(match):
        digits = match.group(1) or match.group(2) or match.group(3)
        return chr(int(digits, 8 if match.group(3) else 16))
    return re.sub(r"\\x([0-9a-fA-F]{2})|\\u([0-9a-fA-F]{4})|\\([0-7]{1,3})",
                  one, text)


def _literal_runs(code):
    """The text of each run of string literals that are one name when joined
    (`'ter' 'raform'`, `'ter'+'raform'`, `"".join(["ter","raform"])`), with
    escapes decoded and every character but letters and digits dropped. A
    run ends at anything else: separate imports or statements never join."""
    runs, run, last = [], [], None
    for match in _LIT_RE.finditer(code):
        gap = None if last is None else code[last:match.start()]
        if run and not (gap is not None and _RUN_GAP_RE.match(gap)):
            runs.append("".join(run))
            run = []
        quote = 3 if match.group(1)[:3] in ("\'\'\'", '"""') else 1
        text = _decode_escapes(match.group(1)[quote:-quote])
        run.append(re.sub(r"[^a-z0-9]", "", text.lower()))
        last = match.end()
    if run:
        runs.append("".join(run))
    return runs


# Unclosed triple quotes and backticks make each literal scan run to the end
# of the code: more than this many and the code is refused unread.
_TRIPLE_OR_TICK_RE = re.compile(r"\'\'\'|\"\"\"|`")
_QUOTE_LIMIT = 300
_PROC_WORD_RE = re.compile(
    r"\b(?:system|popen|spawn\w*|exec\w*|fork\w*|call|run|check_output"
    r"|check_call|Popen|getoutput|getstatusoutput|startfile)\b")
_IMPORT_AS_RE = re.compile(r"\bimport\s+([^;\n]+)")


def _proc_aliases(code, assigned):
    """Names bound to a process-starting function (`s = os.system`,
    `from os import system as s`, `const e = require('child_process')
    .execSync`), so `s(...)` is read as the call it is."""
    found = set()
    for name, rows in assigned.items():
        if any(_PROC_WORD_RE.search(_LIT_RE.sub('""', rhs)) for _, rhs in rows):
            found.add(name)
    for clause in _IMPORT_AS_RE.finditer(code):
        for item in clause.group(1).split(","):
            parts = item.split()
            if len(parts) == 3 and parts[1] == "as" and \
                    _PROC_WORD_RE.search(parts[0]):
                found.add(parts[2])
    return found


def _call_args(code, aliases=()):
    """The argument text of each call to a process-starting function, or to
    a name bound to one (`aliases`)."""
    calls = list(_PROC_CALL_RE.finditer(code))
    if aliases:
        calls += re.finditer(r"\b(?:" + "|".join(map(re.escape, aliases))
                             + r")\s*\(", code)
    for call in sorted(calls, key=lambda found: found.start()):
        depth, pos = 1, call.end()
        while pos < len(code) and depth:
            lit = _LIT_RE.match(code, pos)
            if lit:
                pos = lit.end()
                continue
            depth += (code[pos] == "(") - (code[pos] == ")")
            pos += 1
        yield code[call.end():pos]


_ASSIGN_RE = re.compile(
    r"\s*(?:(?:const|let|var)\s+)?([A-Za-z_]\w*)\s*(?::[^=]*?)?(\+|:)?=(?!=)(.*)\Z",
    re.S)
_NAME_RE = re.compile(r"[A-Za-z_]\w*")


def _statements(code):
    """`code` split at `;` and newlines outside string literals."""
    out, start, pos = [], 0, 0
    while pos < len(code):
        lit = _LIT_RE.match(code, pos)
        if lit:
            pos = lit.end()
            continue
        if code[pos] in ";\n":
            out.append(code[start:pos])
            start = pos + 1
        pos += 1
    out.append(code[start:])
    return out


def _assignments(code):
    """name -> [(operator, right-hand side)] for each `name = ...`,
    `name += ...`, `name: T = ...` and `name := ...` statement, in order."""
    found = {}
    for statement in _statements(code):
        match = _ASSIGN_RE.match(statement)
        if match:
            found.setdefault(match.group(1), []).append(
                (match.group(2) or "", match.group(3)))
    return found


_SPELL_LIMIT = 4096


def _spelling(name, assigned, memo, seen=()):
    """(letters, why): the letters and digits of every string literal that
    went into `name` through assignments, however many names deep (`a = 'ter'`,
    `b = a + 'ra'`, `c = b + 'form'`), in order; `why` is a `$` or backtick
    in one of them, or `+` where a name is joined to another operand (also
    when the chain is too long to follow: it is refused, never read slowly).
    `memo` holds each finished name, so a chain that fans out is read once."""
    if name in memo:
        return memo[name]
    memo[name] = result = _spell(name, assigned, memo, seen)
    return result


def _spell(name, assigned, memo, seen):
    """`_spelling`, uncached."""
    spelled = ""
    for operator, rhs in assigned.get(name, ()):
        if len(spelled) > _SPELL_LIMIT:
            return spelled, "+"
        bare = _LIT_RE.sub('""', rhs)
        if operator == "+" and re.search(r"[\w)\]]|[(\[]", bare):
            return spelled, "+"
        if re.search(r"[\w)\]]\s*\+|\+\s*[\w(\[]", bare):
            return spelled, "+"
        for token in re.finditer(_LIT_RE.pattern + r"|[A-Za-z_]\w*", rhs, re.S):
            if token.group(1) is not None:
                found = _CODE_EXPANSION_RE.search(token.group(1))
                if found:
                    return spelled, found.group(0)
                quote = 3 if token.group(1)[:3] in ("'''", '"""') else 1
                spelled += re.sub(r"[^a-z0-9]", "", _decode_escapes(
                    token.group(1)[quote:-quote]).lower())
            elif token.group(0) in assigned and token.group(0) not in seen \
                    and token.group(0) != name:
                inner, why = _spelling(token.group(0), assigned, memo,
                                       seen + (name,))
                if why:
                    return spelled, why
                spelled += inner
                if len(spelled) > _SPELL_LIMIT:
                    return spelled[:_SPELL_LIMIT], "+"
    return spelled, None


def _expansion_in_call(code):
    """A `$` or backtick in a string literal that is (or names, through any
    chain of assignments) the argument of a process-starting call, a name
    that spells the tool out of the literals assigned along that chain, or a
    non-literal joined to another operand (`a + b`, also in an assignment of
    a name the call uses): the name is made at run time. Printed text with a
    `$` in it is not."""
    assigned = _assignments(code)
    memo = {}
    for args in _call_args(code, _proc_aliases(code, assigned)):
        for lit in _LIT_RE.finditer(args):
            found = _CODE_EXPANSION_RE.search(lit.group(1))
            if found:
                return found.group(0)
        bare = _LIT_RE.sub('""', args)
        if re.search(r"[\w)\]]\s*\+|\+\s*[\w(\[]", bare):
            return "+"
        for name in sorted(set(_NAME_RE.findall(bare))):
            spelled, why = _spelling(name, assigned, memo)
            if why:
                return why
            for tool in _TOOL_SPELLINGS:
                if tool in spelled:
                    return tool
    return None


def _built_name(code, scan, reach, assembly, label):
    """An `InterpreterHit` when `code` reaches a process (`reach`, its
    regex, read over `scan`: the code, or python's without its string text)
    and builds the tool's name: adjacent string literals join to the name, or
    it uses an `assembly` construct (also read over `scan`), or a shell
    expansion or a non-literal operand feeds a process call. None otherwise
    (L-0871)."""
    reached = reach.search(scan)
    if reached is None:
        return None
    if len(_TRIPLE_OR_TICK_RE.findall(code)) > _QUOTE_LIMIT:
        return InterpreterHit("quotes", (
            f"{label} code with more than {_QUOTE_LIMIT} triple quotes or "
            f"backticks next to {reached.group(0)!r}: too many to read"))
    for run in _literal_runs(code):
        for tool in _TOOL_SPELLINGS:
            if tool in run:
                return InterpreterHit(tool, (
                    f"{label} code that spells {tool!r} out of fragments "
                    f"next to {reached.group(0)!r}"))
    built = assembly.search(scan)
    built = built.group(0) if built else _expansion_in_call(code)
    if built is None:
        return None
    return InterpreterHit(built, (
        f"{label} code that builds a name at run time ({built!r}) "
        f"next to {reached.group(0)!r}, so it could spell the tool"))


def _code_mention(code, top):
    """The word naming the tool in interpreter `code` or anywhere on the
    line `top`, or None."""
    found = _CODE_MENTION_RE.search(code)
    if found:
        return found.group(0)
    return names_terraform(code, "bash") or names_terraform(top, "bash")


def _py_without_text(code):
    """Python `code` with the text of its plain string literals blanked,
    same length (SRL-2308 r3): a string is data until a name outside one
    -- `eval`, `exec`, `getattr`, `__import__`, a module -- makes it code,
    and `str.format` reaches attributes but calls nothing. An f-string or
    t-string runs what it interpolates, so it is kept; so is a comment, and
    anything after a string that does not close."""
    out, pos = list(code), 0
    while pos < len(code):
        char = code[pos]
        if char == "#":
            end = code.find("\n", pos)
            pos = len(code) if end == -1 else end
            continue
        if char not in "'\"":
            pos += 1
            continue
        prefix = re.search(r"\w*$", code[:pos]).group(0).lower()
        quote = code[pos:pos + 3] if code[pos:pos + 3] in ("'''", '"""') \
            else char
        end = pos + len(quote)
        while end < len(code) and not code.startswith(quote, end) and \
                (len(quote) == 3 or code[end] != "\n"):
            end += 2 if code[end] == "\\" else 1
        if end >= len(code) or not code.startswith(quote, end):
            break
        if not set(prefix) & set("ft"):
            for index in range(pos + len(quote), end):
                if out[index] != "\n":
                    out[index] = " "
        pos = end + len(quote)
    return "".join(out)


def _py_spawns(code, whole=False):
    """The word showing Python `code` may start a process, or None: a name
    `_PY_SPAWN_RE` reads, an import outside `_PY_SAFE_MODULES`, or any
    import that is not a top-level statement or follows a file write (it
    could load a module the code itself wrote, or run later than read).
    `whole`: `code` is a shell line read as the code (python reading a
    pipe), whose quoted words are the code itself, so no text is blanked."""
    if re.search(r"coding[:=]", code):
        return "coding"  # a source codec may turn string text into code
    bare = code if whole else _py_without_text(code)
    found = _PY_SPAWN_RE.search(bare)
    if found:
        return found.group(0)
    write = re.search(r"\bopen\b|\bwrite", code)
    for match in _PY_IMPORT_RE.finditer(bare):
        names = [match.group(1)] if match.group(1) else \
            [n.split()[0] for n in match.group(2).split(",")]
        for name in names:
            if name.split(".")[0] not in _PY_SAFE_MODULES:
                return "import " + name
        prefix = code[code.rfind("\n", 0, match.start()) + 1:match.start()]
        nested = bool(prefix) and (prefix[0].isspace() or ":" in prefix
                                   or not prefix.rstrip().endswith(";"))
        if nested or write and match.start() > write.start():
            return match.group(0)
    return None


def _py_static(code):  # pylint: disable=too-many-return-statements,too-many-branches
    """True when Python `code` builds nothing at run time: only
    `_PY_STATIC_NAMES`, plain string literals (no prefix, escape, `$`,
    backquote, brace or `%`; none next to another string, `[` or `.`),
    integers, comments and `.,()[]=;:` -- a list literal, never a
    subscript."""
    pos, prev = 0, ""
    while pos < len(code):
        char = code[pos]
        if char in "'\"":
            if pos and (code[pos - 1].isalnum() or code[pos - 1] == "_"):
                return False  # f"", b"", r"": a prefix
            quote = code[pos:pos + 3] if code[pos:pos + 3] in ("'''", '"""') \
                else char
            end = code.find(quote, pos + len(quote))
            if end == -1 or any(c in code[pos + len(quote):end]
                                for c in "\\$`{}%"):
                return False
            pos = end + len(quote)
            if code[pos:].lstrip(" \t")[:1] in ("'", '"', "[", "."):
                return False
            prev = "S"
        elif char == "#":
            end = code.find("\n", pos)
            pos = len(code) if end == -1 else end
        elif char.isalpha() or char == "_":
            name = re.match(r"\w+", code[pos:]).group(0)
            if name not in _PY_STATIC_NAMES:
                return False
            pos, prev = pos + len(name), name[-1]
        elif char.isdigit():
            number = re.match(r"\d+", code[pos:]).group(0)
            pos, prev = pos + len(number), "0"
            if code[pos:pos + 1].isalnum() or code[pos:pos + 1] in "._":
                return False
        elif char == "[" and (prev.isalnum() or prev in "_)]S"):
            return False  # a subscript
        elif char in " \t\r\n.,()[]=;:":
            prev = prev if char.isspace() else char
            pos += 1
        else:
            return False
    return True


def _code_verdict(code, spec, top, dynamic=False, whole=False):
    """The word naming why interpreter `code` (of `spec`'s family) may run
    the tool, or None: the rule in the section comment. An
    `InterpreterHit` for python and node, carrying the construct. `dynamic`
    is unused since L-0871 (1.2.35's rule has already run); `whole`: the code
    is a shell line (`_py_spawns`)."""
    del dynamic
    family = spec[7]
    if _code_is_inert(code, family != "node"):
        return None
    if family == "python":
        spawn = _py_spawns(code, whole)
        if spawn is None:
            return None
        named = _code_mention(code, top)
        if named is not None:
            return InterpreterHit(named, (
                f"python code that names {named!r} and may start a process "
                f"({spawn!r})"))
        bare = code if whole else _py_without_text(code)
        return _built_name(code, bare, _PY_REACH_RE, _PY_ASSEMBLY_RE, "python")
    if family == "php":
        return _code_mention(code, top) or "php"
    found = _FAMILY_SPAWN_RE[family].search(code)
    if found is None:
        return None
    named = _code_mention(code, top)
    if family == "node":
        if named is not None:
            return InterpreterHit(named, (
                f"node code that names {named!r} and may start a process "
                f"({found.group(0)!r})"))
        return _built_name(code, code, _NODE_REACH_RE, _NODE_ASSEMBLY_RE,
                           "node")
    return named or found.group(0)


def _judge_code(code, spec, top, runtime, whole=False):
    """`_code_verdict`, and first, for code made at run time, 1.2.35's
    rule over the line."""
    named = _verb_on_line(top) if runtime else None
    return named or _code_verdict(code, spec, top, runtime, whole)


def _perl_magic(spec, words, codes, unknown):
    """Perl's `-n`/`-p`/`-i` (or `<>` in its code) opens each operand with
    the two-argument `open`, which runs `cmd|` as a command: an operand that
    holds a `|` or is made at run time, or None."""
    if spec[7] != "perl" or not codes:
        return None
    first = codes[0][0]
    opts = [w for w in words[:first + 1] if w.startswith("-")
            and not w.startswith("--")]
    if not any(set(w[1:]) & set("npi") for w in opts) and \
            not any("<>" in c or "ARGV" in c for _i, c in codes):
        return None
    for index in range(codes[-1][0] + 1, len(words)):
        if index in unknown or "|" in words[index]:
            return words[index]
    return None


def _interpreter_names(spec, raw_words, meta, line, resolved):  # pylint: disable=too-many-locals
    """The word naming why an interpreter command may run the tool, or
    None: its `-c`/`-e`/... code, a heredoc or here-string fed to it, or --
    reading stdin with neither -- the whole line as its code. Each value is
    expanded with the line's `resolved` variables; one that holds anything
    else is made at run time (`_judge_code`)."""
    words, unknown = [], set()
    for index, raw in enumerate(raw_words):
        value = _expand_known(raw, resolved)
        if value is None:
            unknown.add(index)
            value = _shell_unquote(raw)
        words.append(value)
    codes, stdin = _interp_codes(spec, words)
    for index, code in codes:
        named = _judge_code(code, spec, line.top, index in unknown)
        if named is not None:
            return named
    named = _perl_magic(spec, words, codes, unknown)
    if named is not None:
        return named
    meta = meta or {"bodies": [], "here": []}
    feeds = []
    for body, quoted in meta["bodies"]:
        value = body if quoted else _expand_known(body, resolved, True)
        feeds.append((body, True) if value is None else (value, False))
    for raw in meta["here"]:
        value = _expand_known(raw, resolved)
        feeds.append((_shell_unquote(raw), True) if value is None
                     else (value, False))
    for body, runtime in feeds:
        named = _judge_code(body, spec, line.top, runtime)
        if named is not None:
            return named
    if stdin and not feeds:
        return _judge_code(line.text, spec, line.top,
                           bool(re.search(r"[$`]", line.text)), True)
    return None


def interpreted_on_line(text, stdin):
    """The precise path's question for an interpreter command (SRL-2308 r2):
    the word naming why an interpreter command in bash `text` may run the
    tool (`_interpreter_names`), or None. When `stdin` and no interpreter
    command is found at the top of `text` (it is nested in `bash -c`), the
    whole `text` is read as python's code."""
    if _GATE_CONTROL_RE.search(text):
        return names_terraform(text, "bash")
    splitter = _CommandSplitter(text)
    try:
        commands, _subs = splitter.split()
    except _Unsure:
        return names_terraform(text, "bash")
    line, found = _Line(text, text), False
    for words, meta, known in zip(commands, splitter.metas,
                                  _resolved_vars(commands, splitter.metas)):
        while words and (words[0] in _FALLBACK_RESERVED
                         or _FALLBACK_ASSIGN_RE.match(words[0])):
            words = words[1:]
        if not words:
            continue
        heads = range(len(words)) if _head_name(_dequote(
            words[0])) in _FALLBACK_WRAPPERS else range(1)
        for index in heads:
            spec = _interp_family(_head_name(_dequote(words[index])))
            if spec is None:
                continue
            found = True
            named = _interpreter_names(spec, words[index + 1:], meta, line,
                                       known)
            if named is not None:
                return named
    if stdin and not found:
        return _judge_code(text, _INTERPRETERS[0][1], text,
                           bool(re.search(r"[$`]", text)), True)
    return None


# --- awk and sed programs (SRL-2308 r4, r3-1) ---------------------------------
#
# awk's `system()`, its pipes to and from a command (`print | "cmd"`,
# `"cmd" | getline`, gawk's `|&`) and gawk's `@load`/`@include`, and sed's
# `e` command and `s///e` flag, start a process. On a fallback line they are
# read as interpreter code is: refused when the program can start a process,
# and the command it starts is always taken as built at run time (awk
# concatenates strings by juxtaposition, sed runs its pattern space), so the
# process construct alone refuses. An awk construct counts in its code, not
# in a string, regex constant or comment; an awk program crew cannot read
# that way counts on any `|`, `@` or `system` (SRL-2308 r5). A program crew cannot see (`awk -f f`,
# `sed -f f`, `gawk -l ext`) or one made at run time is decided by 1.2.35's
# rule over the line; a sed script made at run time is refused when the line
# names the tool (a value could add an `e` flag). On a cleanly readable line
# the precise reader still lets both through, as 1.2.35 did: a pre-existing
# limit (README, "What the guard does not catch").
_AWK_NAMES_RE = re.compile(r"^(?:[gmn]?awk|original-awk|goawk|onetrue-?awk)$")
_SED_NAMES_RE = re.compile(r"^g?sed$")
# Read over the program's CODE only (`_awk_code`: strings, regex constants
# and comments blanked, backslash-newline joined). awk has no bitwise or, so
# a lone `|` there is a pipe to or from a command (`print | "cmd"`, `"cmd" |
# getline`, `|&`); `@` is gawk's `@load`/`@include` or an indirect call
# (`f = "system"; @f(...)`). SRL-2308 r5 (r4-2, r4-3).
_AWK_SPAWN_RE = re.compile(r"\bsystem\s*\(|(?<!\|)\|(?!\|)|@")
# A program `_awk_code` cannot read cleanly is refused when it holds any of
# these anywhere, strings included (fail closed).
_AWK_RISK_RE = re.compile(r"[|@]|\bsystem\b")
# Where a `/` starts a regex constant rather than dividing: after one of
# these characters, or after `print`/`printf`/`return`. Anywhere else it is
# read as division, so the text after it is read as code (fail closed).
_AWK_REGEX_AFTER = frozenset("(,{};!~&|=<>?:[\n")
_AWK_REGEX_WORDS = frozenset(("print", "printf", "return"))
_AWK_VALUE_OPTS = frozenset(("-F", "-v", "--field-separator", "--assign"))
# A program, library or extension from a file; mawk's `-W` (`-W exec f`).
_AWK_HIDDEN_OPTS = frozenset(("-f", "--file", "-E", "--exec", "-l", "--load",
                              "-i", "--include", "-W"))
_AWK_CODE_OPTS = frozenset(("-e", "--source"))


def _awk_program(words):
    """`(codes, hidden)` for awk's argument words (quotes removed): `codes`
    as `(index, text)`, the program given on the line; `hidden` true when a
    program, library or extension comes from a file crew does not read."""
    codes, index = [], 0
    while index < len(words):
        word = words[index]
        if word == "--":
            index += 1
            break
        name, equals, given = word.partition("=") if word.startswith("--") \
            else (word[:2], word[2:] != "", word[2:])
        if not word.startswith("-") or word == "-":
            break
        if name in _AWK_HIDDEN_OPTS:
            return codes, True
        if name in _AWK_CODE_OPTS:
            if not equals:
                index += 1
            if index < len(words):
                codes.append((index, given if equals else words[index]))
        elif name in _AWK_VALUE_OPTS and not equals:
            index += 1
        index += 1
    if not codes and index < len(words):
        codes.append((index, words[index]))
    return codes, False


def _awk_literal_end(program, pos):  # pylint: disable=too-many-branches
    """The index after the string (`"`) or regex constant (`/`) opening at
    `pos` in awk `program`, or None when it is not read cleanly: no end, a
    newline before it, or in a regex a bracket expression holding a `/` or
    a newline (awks disagree on where such a regex ends)."""
    delim, size, bracket = program[pos], len(program), False
    pos += 1
    while pos < size:
        char = program[pos]
        if char == "\\":
            if pos + 1 >= size or delim == "/" and program[pos + 1] == "\n":
                return None
            pos += 2  # an escape; in a string `\` newline continues it
        elif char == "\n" or bracket and char == "/":
            return None
        elif bracket:
            if char == "[" and program[pos + 1:pos + 2] in (":", ".", "="):
                end = program.find(program[pos + 1] + "]", pos + 2)
                if end == -1 or re.search(r"[/\n]", program[pos:end]):
                    return None
                pos = end + 2  # `[:alpha:]` inside a bracket expression
                continue
            bracket = char != "]"
            pos += 1
        elif char == delim:
            return pos + 1
        elif delim == "/" and char == "[":
            pos += 1
            pos += program[pos:pos + 1] == "^"
            pos += program[pos:pos + 1] == "]"  # `[]a]`: a literal `]`
            bracket = True
        else:
            pos += 1
    return None


def _awk_code(program):
    """awk `program`'s code with each string read as `""`, each regex
    constant as `//`, comments dropped and backslash-newline joined (awk's
    line continuation); None when it is not read cleanly: a `\\` anywhere
    else, or a literal `_awk_literal_end` does not read. A `/` starts a
    regex only where `_AWK_REGEX_AFTER`/`_AWK_REGEX_WORDS` say."""
    out, pos, size = [], 0, len(program)
    while pos < size:
        char = program[pos]
        if char == "\\":
            step = 2 if program[pos + 1:pos + 2] == "\n" else \
                3 if program[pos + 1:pos + 3] == "\r\n" else 0
            if not step:
                return None
            pos += step
            continue
        if char == "#":
            end = program.find("\n", pos)
            pos = size if end == -1 else end
            continue
        if char == '"' or char == "/" and _awk_regex_here(out):
            end = _awk_literal_end(program, pos)
            if end is None:
                return None
            out.append(char * 2)
            pos = end
            continue
        out.append(char)
        pos += 1
    return "".join(out)


def _awk_regex_here(out):
    """True when a `/` after the code read so far (`out`, a list of
    pieces) starts a regex constant: rule in `_AWK_REGEX_AFTER`."""
    index = len(out) - 1
    while index >= 0 and out[index] in (" ", "\t", "\r"):
        index -= 1
    if index < 0 or out[index] in _AWK_REGEX_AFTER:
        return True
    start = index
    while start >= 0 and (out[start].isalnum() or out[start] == "_"):
        start -= 1
    return "".join(out[start + 1:index + 1]) in _AWK_REGEX_WORDS


def _awk_spawns(program):
    """The construct by which awk `program` may start a process, or None:
    `_AWK_SPAWN_RE` over its code (`_awk_code`), or, when the program is
    not read cleanly, `_AWK_RISK_RE` over all of it (SRL-2308 r5)."""
    code = _awk_code(program)
    found = _AWK_RISK_RE.search(program) if code is None \
        else _AWK_SPAWN_RE.search(code)
    return None if found is None else found.group(0)


def _sed_scripts(words):
    """`(scripts, hidden)` for sed's argument words (quotes removed), as
    `_awk_program` does: `-e`/`--expression`, else the first operand;
    `hidden` for `-f`/`--file`."""
    scripts, index, first = [], 0, None
    while index < len(words):
        word = words[index]
        if word == "--":
            first = index + 1 if first is None else first
            break
        if word.startswith("--"):
            name, equals, given = word.partition("=")
            if name == "--file":
                return scripts, True
            if name == "--expression":
                if not equals:
                    index += 1
                    given = words[index] if index < len(words) else ""
                scripts.append((index, given))
            elif name == "--line-length" and not equals:
                index += 1
        elif word.startswith("-") and len(word) > 1:
            for pos in range(1, len(word)):
                letter, tail = word[pos], word[pos + 1:]
                if letter == "f":
                    return scripts, True
                if letter in "el":
                    if not tail and index + 1 < len(words):
                        index += 1
                        tail = words[index]
                    if letter == "e":
                        scripts.append((index, tail))
                    break
                if letter == "i":
                    break  # `-i.bak`: the rest is a suffix
        elif first is None:
            first = index
        index += 1
    if not scripts and first is not None and first < len(words):
        scripts.append((first, words[first]))
    return scripts, False


def _sed_skip(script, pos, delim):
    """The index after the next unescaped `delim` in sed `script` from
    `pos`, or `len(script)`."""
    while pos < len(script):
        if script[pos] == "\\":
            pos += 2
        elif script[pos] == delim:
            return pos + 1
        else:
            pos += 1
    return len(script)


def _sed_runs(script):  # pylint: disable=too-many-branches
    """True when sed `script` may run a command: an `e` command or an `s`
    command with the `e` flag. Anything this reading does not know reads
    as one (fail closed)."""
    pos, size = 0, len(script)
    while pos < size:
        char = script[pos]
        if char in " \t\r\n;{}!,~+$" or char.isdigit():
            pos += 1  # separators, blocks, negation, line addresses
        elif char == "#":
            end = script.find("\n", pos)
            pos = size if end == -1 else end
        elif char in "/\\":
            if char == "\\":
                pos += 1
                if pos >= size:
                    return True
            pos = _sed_skip(script, pos + 1, script[pos])
            while pos < size and script[pos] in "IM":
                pos += 1
        elif char in "sy":
            if pos + 1 >= size or script[pos + 1] in "\\\n":
                return True
            delim = script[pos + 1]
            pos = _sed_skip(script, _sed_skip(script, pos + 2, delim), delim)
            while char == "s" and pos < size and script[pos] not in ";\n}#":
                if script[pos] == "e":
                    return True
                if script[pos] in "wW":
                    end = script.find("\n", pos)
                    pos = size if end == -1 else end
                    break
                pos += 1
        elif char in "aicrRwWbtT:v":
            # Text, a file name or a label, to the end of the line (a
            # label also to a `;`); a text line ending `\` continues.
            while pos < size and script[pos] != "\n" and not (
                    char in "btT:v" and script[pos] == ";"):
                pos += 2 if script[pos] == "\\" else 1
        elif char in "=dDgGhHnNpPxzFqQlL":
            pos += 1
        else:
            return True  # `e`, or a command this reading does not know
    return False


def _stream_editor_names(head, raw_words, line, resolved):
    """The word naming why an awk or sed command (`head`, its raw argument
    words; `busybox awk` too) may run the tool, or None: the rule in the
    section comment above."""
    if head == "busybox" and raw_words:
        head, raw_words = _head_name(_dequote(raw_words[0])), raw_words[1:]
    awk = bool(_AWK_NAMES_RE.match(head))
    if not awk and not _SED_NAMES_RE.match(head):
        return None
    words, unknown = [], set()
    for index, raw in enumerate(raw_words):
        value = _expand_known(raw, resolved)
        if value is None:
            unknown.add(index)
            value = _shell_unquote(raw)
        words.append(value)
    codes, hidden = _awk_program(words) if awk else _sed_scripts(words)
    if hidden:
        return _verb_on_line(line.top)
    for index, code in codes:
        if awk:
            named = _verb_on_line(line.top) if index in unknown else None
            found = _awk_spawns(code)
            if named is None and found is not None:
                named = _code_mention(code, line.top) or found
        else:
            named = names_terraform(line.top, "bash") \
                if index in unknown else None
            if named is None and _sed_runs(code):
                named = _code_mention(code, line.top) or head
        if named is not None:
            return named
    return None


def _run_time_word(line):
    """`(kind, word)` for a command word made at run time: 1.2.35's rule
    over the whole line, whatever follows the word (SRL-2308 r3)."""
    named = _verb_on_line(line.top)
    return (None, None) if named is None else ("tool", named)


def _made_at_run_time(word, resolved):
    """True when raw `word`, as a command word, names a program crew
    cannot rely on: `_unresolved_head`, or a resolved variable with a value
    `_known_value` does not accept."""
    spellings = _resolve_word(word, resolved)
    if spellings is not None and spellings != [word]:
        return not all(_known_value(s) for s in spellings)
    return _unresolved_head(word, resolved)


# --- a program by path under a run-time directory (SRL-2308 r4, r3-2) --------
#
# `$W/stub.sh`, `"$T/stub"`, `S=$W/stub.sh; $S` name their program by its
# literal last part, and stay trusted ONLY when (a) no operand is a changing
# terraform verb (`_FALLBACK_VERBS`, or `-destroy`) and (b) the same line
# writes, creates, copies, moves, links or chmods nothing into that
# directory or at that name. Otherwise the line is gated as 1.2.35 gated
# it (`_verb_on_line`): what such a program runs is not known.
_LINE_WRITERS = frozenset((
    "tee", "cp", "mv", "ln", "link", "install", "chmod", "chown", "touch",
    "rsync", "dd", "truncate", "mkfifo", "curl", "wget", "tar", "unzip",
    "patch", "sed"))
_REDIRECT_TARGET_RE = re.compile(
    r"(?:\d+|&)?>>?[|&]?\s*(\"[^\"]*\"|'[^']*'|[^\s;&|<>()]+)")
_LINE_WORD_RE = re.compile(r"\"(?:[^\"\\]|\\.)*\"|'[^']*'|[^\s\"']+")


def _refs(word):
    """The variable names `$NAME`/`${NAME}` in raw `word`."""
    return {m.group(1) or m.group(2) for m in _FALLBACK_REF_RE.finditer(word)}


def _last_part(word):
    return re.split(r"[/\\=]", _dequote(word).rstrip("/\\"))[-1]


def _line_writes_into(top, base, names):
    """True when line `top` may write, create, copy, move, link or chmod
    something at name `base` or into a directory the variables `names`
    spell: a redirection, or an operand of a `_LINE_WRITERS` command (`sed`
    with `-i`), naming either. With no `names`, any operand made at run
    time counts (fail closed)."""
    def touches(word):
        if _last_part(word) == base:
            return True
        return bool(_refs(word) & names) if names else \
            bool(re.search(r"[$`]", word))
    if any(touches(m.group(1)) for m in _REDIRECT_TARGET_RE.finditer(top)):
        return True
    for segment in re.split(r"[;&|\n(){}`]", top):
        words = _LINE_WORD_RE.findall(segment)
        while words and (_FALLBACK_ASSIGN_RE.match(words[0])
                         or _head_name(_dequote(words[0]))
                         in _FALLBACK_WRAPPERS):
            words = words[1:]
            while words and re.match(r"-|\d", words[0]):
                words = words[1:]  # the wrapper's options and duration
        head = _head_name(_dequote(words[0])) if words else ""
        if head not in _LINE_WRITERS or head == "sed" and not any(
                re.match(r"-[a-zA-Z]*i|--in-place", _dequote(w))
                for w in words[1:]):
            continue
        if any(touches(w) for w in words[1:]):
            return True
    return False


def _path_program_trusted(args, top, base, names=frozenset()):
    """True when a program by path `.../base` under a run-time directory,
    run with argument words `args`, keeps its literal name's trust: rules
    (a) and (b) in the section comment. `names`: the variables its own
    word spells; those spelling `.../base` elsewhere on `top` count too."""
    for arg in args:
        value = _dequote(arg).lower()
        if value in _FALLBACK_VERBS or value.startswith("-destroy"):
            return False
    names = set(names)
    for word in _LINE_WORD_RE.findall(top):
        if _last_part(word) == base:
            names |= _refs(word)
    return not _line_writes_into(top, base, names)


def _run_time_path(word, resolved):
    """`(bases, names)` when raw command `word` is a program by path whose
    directory holds an expansion (`$W/stub`, or `$S` with `S=$W/stub.sh` or
    `S=/opt/x/stub`), else None: the literal last part of each spelling,
    and the variables it and its values spell."""
    if not re.search(r"[$`]", word):
        return None
    spellings = _resolve_word(word, resolved)
    names = _refs(word)
    for spelling in spellings or ():
        names |= _refs(spelling)
    bases = {_last_part(s) for s in (spellings or [word])
             if re.search(r"[/\\]", _dequote(s))}
    return (bases, names) if bases else None


# --- a relative program after a directory change (SRL-2308 r5, r4-1) --------
#
# `cd "$T"; ./stub apply`: once the line may have changed directory, a
# command word by relative path (`./x`, `../x`, `x/y`, `$W/x`: not starting
# `/` or `~`) may name a program the line itself put there. A directory
# change is any word the line could make that is `cd`, `pushd`, `popd`
# (bare, `builtin cd`, `command cd`), `-C`/`-D` (`env -C`, `sudo -D`, also
# attached), `--chdir`, `--working-directory`, find's `-execdir`/`-okdir`,
# or `eval`/`source`/`.` (which may run a `cd` crew does not see): read over
# every word, so a quoted mention counts too (fail closed).
#
# When every change on the line is placed (`_dir_targets`: `cd`, `pushd`,
# `-C`, `-D`, `--chdir`, `--working-directory` to ONE literal absolute path,
# and no `eval`/`source`/`.`), read without its data-only heredoc bodies
# (`_without_data_heredocs`), the program is read as that literal path
# would be, as long as (a) none of
# its operands is a changing verb and (b) the line writes, creates, copies,
# links or chmods nothing at its name, into a placed directory, at a
# relative path (which lands in one) or at a path crew cannot spell
# (`_writes_near`). Otherwise -- any `popd`, a change to a run-time or
# relative place, `cd -`, a bare `cd` -- the line is decided by 1.2.35's
# rule over it (`_verb_on_line`).
_DIR_CHANGE_WORDS = frozenset(("cd", "pushd", "popd", "-C", "-D", "-execdir",
                               "-okdir", "eval", "source", "."))
_DIR_ANYWHERE_RE = re.compile(r"(?<![\w.-])(?:cd|pushd|popd)(?![\w-])")


def _relative_after_dir_change(word, top):
    """True when raw command `word` is a program by relative path and line
    `top` may change directory: the rule in the section comment above."""
    value = _dequote(word)
    if "/" not in value or value.startswith(("/", "~")):
        return False
    return any(c in _DIR_CHANGE_WORDS or c.startswith(("-C", "-D"))
               or c.startswith(("--chdir", "--working-directory"))
               for c in _name_candidates(top, "bash"))


def _without_data_heredocs(top):
    """Line `top` without the heredoc bodies that are data only: a quoted
    body fed to a bare `cat` at the top level whose output is not piped or
    substituted (`cat > $S/w.sh <<'EOF'`). Such a body runs nothing on this
    line. A body that occurs more than once, or a line the splitter does not
    read, is left in (fail closed)."""
    splitter = _CommandSplitter(top)
    try:
        commands, _subs = splitter.split()
    except _Unsure:
        return top
    for words, meta in zip(commands, splitter.metas):
        if words != ["cat"] or meta["nest"] != 1 or meta["after"] not in (
                None, ";", "\n", "&&", "||"):
            continue
        for body, quoted in meta["bodies"]:
            if quoted and body and top.count(body) == 1:
                top = top.replace(body, "")
    return top


def _literal_dir(raw):
    """The directory raw word `raw` names when it is one literal absolute
    path (no expansion, glob, brace, `~` or escape), else None."""
    if not raw or re.search(r"[$`*?\[{~\\]", raw):
        return None
    value = _dequote(raw)
    return (value.rstrip("/") or "/") if value.startswith("/") else None


def _dir_targets(top):  # pylint: disable=too-many-branches
    """The literal absolute directories line `top` changes into, or None
    when a change goes anywhere else or is not read here: the rule in the
    section comment above."""
    dirs = set()
    text = top.replace("\\\r\n", "").replace("\\\n", "")
    for segment in re.split(r"[;&|\n(){}`]", text):
        raws = _LINE_WORD_RE.findall(segment)
        values = [_dequote(w) for w in raws]
        for index, value in enumerate(values):
            nxt = index + 1
            if value in ("cd", "pushd"):
                while nxt < len(values) and re.fullmatch(r"-[LPe@]+|--",
                                                         values[nxt]):
                    nxt += 1
                operand = raws[nxt] if nxt < len(raws) else None
            elif value in ("-C", "-D", "--chdir", "--working-directory"):
                operand = raws[nxt] if nxt < len(raws) else None
            elif value.startswith(("--chdir=", "--working-directory=")):
                operand = raws[index].split("=", 1)[1]
            elif re.match(r"-[CD].", value):
                operand = raws[index][2:]
            elif value in ("popd", "-execdir", "-okdir", "eval", "source",
                           ".") or _DIR_ANYWHERE_RE.search(value):
                return None  # `x=cd`, `'cd "$T"'`, `{cd,"$T"}` too
            else:
                continue
            place = _literal_dir(operand)
            if place is None:
                return None
            dirs.add(place)
    return dirs or None


def _writes_near(top, base, dirs, resolved):
    """True when line `top` may write, create, copy, move, link or chmod
    something at name `base`, into one of `dirs`, at a relative path, or at
    a path crew cannot spell: rule (b) in the section comment above."""
    def touches(raw):
        if _last_part(raw) == base:
            return True
        for spelling in _resolve_word(raw, resolved) or [None]:
            if spelling is None or re.search(r"[$`*?\[{~]", spelling):
                return True
            value = _dequote(spelling)
            if not value.startswith("/") or any(
                    value == d or value.startswith(d.rstrip("/") + "/")
                    for d in dirs):
                return True
        return False
    for match in _REDIRECT_TARGET_RE.finditer(top):
        if ">&" in match.group(0) and re.fullmatch(r"\d+|-", match.group(1)):
            continue  # `2>&1`: a descriptor, not a file
        if touches(match.group(1)):
            return True
    for segment in re.split(r"[;&|\n(){}`]", top):
        words = _LINE_WORD_RE.findall(segment)
        while words and (_FALLBACK_ASSIGN_RE.match(words[0])
                         or _head_name(_dequote(words[0]))
                         in _FALLBACK_WRAPPERS):
            words = words[1:]
            while words and re.match(r"-|\d", words[0]):
                words = words[1:]
        head = _head_name(_dequote(words[0])) if words else ""
        if head not in _LINE_WRITERS or head == "sed" and not any(
                re.match(r"-[a-zA-Z]*i|--in-place", _dequote(w))
                for w in words[1:]):
            continue
        operands = [w for w in words[1:] if not re.match(r"[-+]", w)]
        if head in ("chmod", "chown"):
            operands = operands[1:]  # the mode or owner
        if any(touches(w) for w in operands):
            return True
    return False


def _relative_trusted(words, resolved, top):
    """True when the relative program `words[0]` keeps the trust a literal
    path has: every directory change on `top` placed, and rules (a) and (b)
    in the section comment above, read without its data heredocs."""
    top = _without_data_heredocs(top)
    dirs = _dir_targets(top)
    if dirs is None:
        return False
    for arg in words[1:]:
        value = _dequote(arg).lower()
        if value in _FALLBACK_VERBS or value.startswith("-destroy"):
            return False
    return not _writes_near(top, _last_part(words[0]), dirs, resolved)


def _fallback_command(words, resolved, line, wrapper=None, meta=None):  # pylint: disable=too-many-return-statements,too-many-branches
    """`(kind, word)` for one simple command of raw words: kind "tool" with
    the word naming terraform, "script" for an interpreter of shell code, or
    None for neither. `resolved` is `_resolved_vars`'s; `line` the `_Line`;
    `meta` the splitter's for this command, for an interpreter's code.
    `wrapper`: the wrapper whose own scan called this, which reads every
    later word itself, so a wrapper here does not scan again (a chain of
    wrappers stays linear)."""
    words = list(words)
    while words and (words[0] in _FALLBACK_RESERVED
                     or _FALLBACK_ASSIGN_RE.match(words[0])):
        words = words[1:]
    if not words:
        return None, None
    if _made_at_run_time(words[0], resolved):
        # `$1`, `"$@"`, `$0`, `$SHELL`, `${X:-y}`, `$(...)`, a glob, `$TF`;
        # and a resolved variable whose value is a bare name, a shell, an
        # interpreter or a wrapper, or not one word (`T=ls`, `T=bash`,
        # `T=sudo`, `T=`, `T='a b'`): SRL-2308 r3.
        return _run_time_word(line)
    if _relative_after_dir_change(words[0], line.top) and \
            not _relative_trusted(words, resolved, line.top):
        found = _run_time_word(line)  # `cd "$T"; ./stub apply` (r4-1)
        if found[0] is not None:
            return found
    found = _run_time_path(words[0], resolved)
    if found is not None and _word_names_tool(words[0], resolved) is None \
            and not all(_path_program_trusted(words[1:], line.top, base,
                                              found[1]) for base in found[0]):
        # `"$W/stub" apply`, `printf ... > "$T/stub"; "$T/stub"`: 1.2.35's
        # rule (SRL-2308 r4, r3-2).
        return _run_time_word(line)
    spellings = _resolve_word(words[0], resolved)
    if spellings is not None and spellings != [words[0]]:
        # Every value a path to a program that runs nothing else: read as
        # that program (`S=$W/stub.sh; $S apply`, `T=/opt/tf/terraform`).
        for spelling in spellings:
            found = _fallback_command([spelling] + words[1:], resolved, line,
                                      wrapper, meta)
            if found[0] is not None:
                return found
        return None, None
    head = _head_name(_dequote(words[0]))
    if head in _FALLBACK_DECLARE:
        return None, None
    named = _word_names_tool(words[0], resolved)
    if named is not None:
        # The tool and ONE read-only subcommand, nothing after it, is not
        # gated (`$S/bin/terraform version`). Any further word -- an option,
        # `-chdir=`, another verb -- keeps the line gated.
        if len(words) == 2 and _PLAIN_WORD_RE.match(words[1]) \
                and words[1] in _TF_READ_ONLY:
            return None, None
        return "tool", named
    rest = list(words[1:])
    named = _stream_editor_names(head, rest, line, resolved)
    if named is not None:
        return "tool", named  # awk/sed starting a process (SRL-2308 r4)
    spec = _interp_family(head)
    if spec is not None:
        # `python3 -c`, `node -e`, `perl -e`, a heredoc into `python3 -`:
        # code that may start a process and names the tool or builds its
        # command at run time (SRL-2308 r3, `_code_verdict`).
        named = _interpreter_names(spec, rest, meta, line, resolved)
        if named is not None:
            return "tool", named
    if spec is not None or head in _FALLBACK_SCRIPTS:
        # `for f in *.ps1; do pwsh -File $f apply; done`: a script crew
        # cannot name, run with a changing verb (SRL-2308 r2).
        for index, word in enumerate(rest):
            if not word.startswith("-") and _unresolved_head(word, resolved):
                verb = _first_operand([_dequote(w) for w in rest[index + 1:]])
                if verb is not None and verb.lower() in _FALLBACK_VERBS:
                    return "tool", word
    if head in _FALLBACK_SCRIPTS:
        return "script", _shell_codes(head, rest, meta)
    if head in _FALLBACK_RUNNERS and rest and \
            _dequote(rest[0]) in _FALLBACK_RUNNERS[head]:
        head, rest = "npx", rest[1:]
    if head == "find":
        return _fallback_find(words, rest, resolved, line, meta)
    if head == "command" and any(
            w[:1] == "-" and w[:2] != "--" and set(w[1:]) & set("vV")
            for w in rest):
        return None, None  # `command -v terraform`: a lookup
    if head in _GATE_COPIERS:
        # `ln -s "$(command -v terraform)" tf; ./tf apply`.
        named = next((n for n in (_word_names_tool(w, resolved) for w in rest)
                      if n is not None), None)
        return (None, None) if named is None else ("tool", named)
    if head == "env" and any(_dequote(w).startswith(("-S", "--split-string"))
                             for w in rest):
        return "script", words[0]  # `env -S'terraform apply'`
    if head in _FALLBACK_WRAPPERS and wrapper is None:
        # Where the wrapped command starts is not parsed here: from each
        # word on, read what follows as a command -- a run-time word too,
        # unless it follows the literal program a `_PLAIN_OPTION_WRAPPERS`
        # wrapper runs (its argument, not its command).
        program, starts = None, _wrapped_program(head, rest)
        for index, word in enumerate(rest):
            if word.startswith("-") or _FALLBACK_ASSIGN_RE.match(word):
                continue
            if program and _made_at_run_time(word, resolved):
                continue
            found = _fallback_command(rest[index:], resolved, line, head,
                                      meta)
            if found[0] is not None:
                return found
            if program is None and index == starts and \
                    not _made_at_run_time(word, resolved) and \
                    not _runs_other(_head_name(_dequote(word))):
                program = word
    return None, None


def _wrapped_program(head, rest):
    """The index in wrapper `head`'s raw `rest` of the program it runs, when
    crew reads its options exactly (SRL-2308 r3), else None: the first word
    that is not an option or assignment behind a `_PLAIN_OPTION_WRAPPERS`
    wrapper; the word after the duration behind `timeout` (`timeout -k 5
    1500 codex exec "$(cat p)"`). Any option crew does not know: None."""
    index = 0
    if head in _PLAIN_OPTION_WRAPPERS:
        while index < len(rest) and (rest[index].startswith("-") or
                                     _FALLBACK_ASSIGN_RE.match(rest[index])):
            index += 1
        return index
    if head != "timeout":
        return None
    while index < len(rest):
        word = rest[index]
        if word in ("--foreground", "--preserve-status", "-v", "--verbose"):
            index += 1
        elif word in ("-s", "-k", "--signal", "--kill-after"):
            index += 2
        elif re.fullmatch(r"-[sk][\w.]+|--(?:signal|kill-after)=[\w.]+",
                          word):
            index += 1
        elif word.startswith("-"):
            return None
        else:
            break
    if index < len(rest) and re.fullmatch(r"\d+(?:\.\d+)?[smhd]?",
                                          rest[index]):
        return index + 1
    return None


def _fallback_find(words, rest, resolved, line, meta):
    """`find ... -exec CMD ... ;`: each command it runs, read as one; the
    found path `{}` as the command word is the tool when find's own words
    name it (`find . -name terraform -exec {} destroy ';'`)."""
    for index, word in enumerate(rest):
        if _dequote(word) not in _FIND_EXEC:
            continue
        sub = []
        for arg in rest[index + 1:]:
            if _dequote(arg) in (";", "+"):
                break
            sub.append(arg)
        if sub and "{}" in sub[0]:
            named = next((n for n in (_word_names_tool(w, resolved)
                                      for w in words) if n is not None), None)
            if named is not None:
                return "tool", named
        found = _fallback_command(sub, resolved, line, None, meta)
        if found[0] is not None:
            return found
    return None, None


def command_word_names_tool(text, depth=0, top=None):
    """The word naming terraform, terragrunt or tofu at a command-word
    position of bash `text`, or None -- the fallbacks' question (SRL-2308).
    See the section comment above. `top`: the whole line `text` is part of,
    which 1.2.35's rule reads (`bash -c '$TF $1' _ apply`)."""
    top = text if top is None else top
    line = _Line(text, top)
    if depth > _GATE_DEPTH or _GATE_CONTROL_RE.search(text):
        # A CR or other control character: bash and the lexer split it
        # differently (`EOF\r` ends a heredoc to one of them only).
        return names_terraform(text, "bash")
    found = re.search(r"terraform|terragrunt|tofu", text, re.IGNORECASE)
    if found and _ifs_splits(text):
        # A line that makes IFS split on more than blanks splits words where
        # crew cannot see (`IFS=x; T=terraformxapply; $T`): any spelling
        # counts.
        return found.group(0)
    splitter = _CommandSplitter(text)
    try:
        commands, subs = splitter.split()
    except _Unsure:
        return names_terraform(text, "bash")
    if any(_changes_lookup(words) for words in commands):
        # A PATH or lookup change in this shell (`PATH=/opt/shim:$PATH; ls
        # apply`): a bare program name may now be anything, so 1.2.35's
        # rule decides (SRL-2308 r3).
        named = _verb_on_line(top)
        if named is not None:
            return named
    resolved = _resolved_vars(commands, splitter.metas)
    for words, meta, known in zip(commands, splitter.metas, resolved):
        kind, word = _fallback_command(words, known, line, meta=meta)
        if kind == "tool":
            return word
        if kind == "script":
            named = names_terraform(text, "bash")
            # And the shell code it runs, read the same way (SRL-2308 r2):
            # `bash -c '$TF apply'` is a command word made at run time.
            for code in word or ():
                named = named or command_word_names_tool(code, depth + 1, top)
            if named is not None:
                return named
    for sub in subs:
        named = command_word_names_tool(sub, depth + 1, top)
        if named is not None:
            return named
    return None


def _changes_lookup(words):
    """True when command `words` may change which program a bare name runs
    in this shell or for the command it prefixes (SRL-2308 r3): an
    assignment to PATH leading it (`PATH=x`, `PATH=x ls apply`), PATH
    named by `export`/`declare`/`local`/`readonly`/`typeset`, or `hash`
    or `enable`. `env PATH=x cmd` is env's operand, read as before."""
    words = [w for w in words if w not in _FALLBACK_RESERVED]
    lead = 0
    while lead < len(words) and _FALLBACK_ASSIGN_RE.match(words[lead]):
        if _FALLBACK_ASSIGN_RE.match(words[lead]).group(1) == "PATH":
            return True
        lead += 1
    head = _head_name(_dequote(words[lead])) if lead < len(words) else ""
    if head in ("hash", "enable"):
        return True
    return head in _FALLBACK_DECLARE and any(
        re.match(r"PATH(?:\+?=|$)", _dequote(w)) for w in words[lead + 1:])


def _ifs_splits(text):
    """True when bash `text` may make IFS split on something other than
    blanks: an `IFS=` whose value, quotes removed, is not only spaces, tabs
    and newlines (`IFS=x`, `IFS=$X`), or any other mention of the name
    (`read IFS`, `printf -v IFS`). `IFS= read -r` and `IFS=$'\\n'` do not."""
    for match in re.finditer(
            r"(?<![\w$])(?<!\$\{)IFS\b(\+?=((?:\$'(?:[^'\\]|\\.)*'|'[^']*'"
            r"|\"[^\"]*\"|[^\s;&|'\"])*))?", text):
        if match.group(1) is None:
            return True
        value = _shell_unquote(match.group(2))
        if any(c not in " \t\n" for c in value):
            return True
    return False


def _shell_codes(head, rest, meta):
    """The shell code a POSIX shell `head` is handed on this command: its
    `-c` script (`-c`, `-lc`, `-xc`), and the heredocs and here-strings fed
    to it. Empty for any other script runner (`eval`, `ssh`, ...), whose
    text the whole line's mention rule reads."""
    if head not in _GATE_SHELLS:
        return []
    codes = [_shell_unquote(w) for w, flag in zip(rest[1:], rest)
             if re.fullmatch(r"-[A-Za-z]*c[A-Za-z]*", _shell_unquote(flag))]
    meta = meta or {"bodies": [], "here": []}
    return codes + [body for body, _quoted in meta["bodies"]] + \
        [_shell_unquote(w) for w in meta["here"]]


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
# terragrunt's options that take no value (review round 8: `--non-interactive
# plan` is a plan), each marked boolean in the terragrunt CLI reference,
# https://terragrunt.gruntwork.io/docs/reference/cli-options/ (v0.72 names
# and the `terragrunt-` spellings they replaced). A valued option listed here
# would hide the subcommand, so an option goes here only when the reference
# says it takes no value; one missing keeps the over-block, never an allow.
_TF_GLOBAL_FLAG_OPTS = frozenset((
    "non-interactive", "terragrunt-non-interactive", "no-color",
    "terragrunt-no-color", "no-auto-init", "terragrunt-no-auto-init",
    "no-auto-retry", "terragrunt-no-auto-retry", "no-auto-approve",
    "terragrunt-no-auto-approve", "queue-ignore-errors",
    "terragrunt-ignore-dependency-errors", "queue-exclude-external",
    "terragrunt-ignore-external-dependencies", "queue-include-external",
    "terragrunt-include-external-dependencies", "queue-strict-include",
    "terragrunt-strict-include", "queue-ignore-dag-order",
    "terragrunt-ignore-dependency-order", "source-update",
    "terragrunt-source-update", "inputs-debug", "terragrunt-debug",
    "provider-cache", "terragrunt-provider-cache", "help", "version"))


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
        takes = not sep and nxt is not None \
            and name not in _TF_GLOBAL_FLAG_OPTS and (
            name in _TF_GLOBAL_VALUE_OPTS or nxt not in _TF_OPS
            and not nxt.startswith("-") and _HOLE not in nxt)
        index += 2 if takes else 1
    return index


def tg_other_op(head, args, index, judge):
    """terragrunt's other commands that run terraform's apply or destroy
    (review of #347), as `_terraform_destructive` names an operation:
    `apply-all`/`destroy-all` (the pre-`run-all` spellings), `stack [opts]
    run [opts] apply|destroy`, `graph apply|destroy` (the module and its
    dependents), and `backend delete` (the state itself, so a destroy).
    `exec` is a wrapper (`tg_exec_rest`), unwrapped before this runs. None
    for anything else; `judge` is kept for the caller's signature."""
    del judge
    sub = args[index] if head == "terragrunt" and index < len(args) else None
    if sub in ("apply-all", "destroy-all"):
        return f"terragrunt run-all {sub[:-4]}"
    nxt = tf_skip_options(args, index + 1)
    if sub in ("stack", "graph") and args[nxt:nxt + 1] == ["run"]:
        nxt = tf_skip_options(args, nxt + 1)
    if sub in ("stack", "graph") and args[nxt:nxt + 1] in (["apply"],
                                                         ["destroy"]):
        return f"terragrunt {sub} run {args[nxt]}"
    if sub == "backend" and args[nxt:nxt + 1] == ["delete"]:
        return "terragrunt backend delete, a destroy"
    return None


def tg_exec_rest(words, fed=None):
    """The argv `terragrunt [opts] exec [opts] [--] cmd...` runs, or None
    when `words` is not a terragrunt exec (review of #347, round 2): it is
    a wrapper, so what it runs goes back through every rule. An option
    before the command with no `--` to end them is one crew cannot place
    (`note_unknown`)."""
    if _head_name(words[0]) != "terragrunt":
        return None
    index = tf_skip_options(words, 1)
    if words[index:index + 1] != ["exec"]:
        return None
    start = tf_skip_options(words, index + 1)
    if "--" not in words[index + 1:start] and start > index + 1:
        note_unknown(fed, "terragrunt exec", words[index + 1])
    return words[start:]


def skip_wrapper_options(args, takes, optional=frozenset(), flags=None,
                         out=None, unknown=None):
    """`args` past a wrapper's own options, read as GNU getopt reads them:
    `--name=v`; `--name v` for a value option in `takes`, or a unique prefix
    of one (`--out L`); a short cluster whose first value letter takes the
    rest of the word, or the next word when it is last (`-rn 1`, `-vk 5`);
    `--` ends them, `-` is an operand.

    `flags` given means the wrapper's tables are complete (`WRAPPER_TABLES`,
    T-0047): a long name is read exactly or by a unique prefix of every long
    name the wrapper has (`--tag` is not `--tagstring`), an `optional` option
    takes only an attached value (`-iR`, `--replace=R`) and ends its cluster,
    and an option in none of the tables is appended to `unknown`. `out`
    collects the options read, each spelled in full, a value as the word
    after it (`-rn 1 -Iplan` -> `-r -n 1 -I plan`)."""
    shorts = {t[1] for t in takes if len(t) == 2}
    longs = [t for t in takes if t.startswith("--")]
    out = [] if out is None else out
    index = 0
    while index < len(args) and args[index].startswith("-") \
            and args[index] != "-":
        word, index = args[index], index + 1
        if word == "--":
            break
        if word.startswith("--"):
            match = [t for t in longs if t.startswith(word)]
            if flags is not None:
                match = _full_long(word, (takes, optional, flags), out,
                                   unknown)
            index += "=" not in word and len(match) == 1
            if "=" not in word and len(match) == 1:
                out.extend(args[index - 1:index])
            continue
        for pos, letter in enumerate(word[1:], 1):
            tail = word[pos + 1:]
            if flags is not None and "-" + letter in optional:
                out.append("-" + letter + tail)
                _strict_optional(optional, tail, word, unknown)
                break
            if letter in shorts:
                out.extend(["-" + letter] + ([tail] if tail
                                             else args[index:index + 1]))
                index += pos == len(word) - 1
                break
            if flags is not None and "-" + letter not in flags:
                _note(unknown, word)
            out.append("-" + letter)
    return args[index:]


def _note(unknown, word):
    if unknown is not None:
        unknown.append(word)


def _strict_optional(optional, value, word, unknown):
    """GNU `parallel` reads options with Perl's Getopt::Long, where an
    optional value with none attached may take the next word: where its
    command starts is then not known (`STRICT_OPTIONAL` in the table)."""
    if not value and STRICT_OPTIONAL in optional:
        _note(unknown, word)


def _full_long(word, tables, out, unknown):
    """`[name]` when long option `word` takes the next word as its value,
    else `[]`; its full spelling goes to `out`, and an unknown, ambiguous
    or misused one to `unknown`."""
    takes, optional, flags = tables
    name, sep, value = word.partition("=")
    names = [n for n in takes | optional | flags if n.startswith("--")]
    hits = [n for n in names if n.startswith(name)]
    full = name if name in names else hits[0] if len(hits) == 1 else None
    if full is None or full in flags and sep:
        _note(unknown, word)
    elif full in optional:
        _strict_optional(optional, sep, word, unknown)
    out.append(LONG_ALIASES.get(full, full or name) + sep + value)
    return [full] if full in takes and not sep else []


def getopt_tables(spec, strict=False):
    """`(value, optional, flag)` option sets from a spec in Getopt::Long's
    own notation: `names=type` takes a value, `names:type` an optional one,
    a bare `names` none; a one-letter name is `-x`, a longer one `--name`.
    `strict`: the optional values are Getopt::Long's (`_strict_optional`).
    Each long alias is recorded in `LONG_ALIASES` under the group's first
    long name (`--work-dir`, `--wd` -> `--workdir`)."""
    sets = {"=": set(), ":": {STRICT_OPTIONAL} if strict else set(), "": set()}
    for item in spec.split():
        names, kind = re.match(r"([^=:]+)([=:]?)", item).groups()
        spelled = [("-" if len(n) == 1 else "--") + n for n in names.split("|")]
        sets[kind].update(spelled)
        longs = [n for n in spelled if n.startswith("--")]
        LONG_ALIASES.update((n, longs[0]) for n in longs)
    return tuple(frozenset(sets[k]) for k in ("=", ":", ""))


STRICT_OPTIONAL = "\x00strict"
LONG_ALIASES = {}
# Every option of the wrappers whose tables are complete (T-0047, review round
# 8): an option in none of a wrapper's sets makes a line naming terraform could
# not tell (`note_unknown`), never a guess at where the command starts.
#
# xargs: GNU findutils `xargs --help` (4.10.0) and its getopt table, measured
# on 4.9.0 (2026-10-04: `echo a | xargs --max-lines echo x` runs `echo x a`),
# plus BSD's `-J`, `-R` and `-S` (FreeBSD xargs(1)). `-e`, `-i` and `-l` take
# a value only attached, `--eof`, `--replace` and `--max-lines` (which is
# `-l`, whatever `--help` prints beside `-L`) only after `=`.
_XARGS = ("null|0 arg-file|a=s delimiter|d=s E=s eof|e:s I=s replace|i:s "
          "L=s max-lines|l:s max-args|n=s open-tty|o max-procs|P=s "
          "interactive|p process-slot-var=s no-run-if-empty|r max-chars|s=s "
          "show-limits verbose|t exit|x help version J=s R=s S=s")
# GNU parallel: `options_hash` in src/parallel, version 20170423, as published
# at https://github.com/gitGNU/gnu_parallel/blob/master/src/parallel (read
# 2026-10-04), verbatim. It parses them with Getopt::Long under
# `bundling,require_order`. An option added since is unknown here: could not
# tell, never a guess.
_PARALLEL = (
    "debug|D=s xargs m X v sql=s sqlmaster=s sqlworker=s sqlandworker=s "
    "joblog|jl=s results|result|res=s resume resume-failed|resumefailed "
    "retry-failed|retryfailed silent keep-order|keeporder|k "
    "no-keep-order|nokeeporder|nok|no-k group g ungroup|u "
    "linebuffer|linebuffered|line-buffer|line-buffered|lb tmux tmuxpane "
    "null|0 quote|q parens=s rpl=s plus I=s extensionreplace|er=s U=s "
    "basenamereplace|bnr=s dirnamereplace|dnr=s "
    "basenameextensionreplace|bner=s seqreplace=s slotreplace=s jobs|j=s "
    "delay=f sshdelay=f load=s noswap max-line-length-allowed number-of-cpus "
    "number-of-cores use-cpus-instead-of-cores "
    "shellquote|shell_quote|shell-quote nice=i tag tagstring|tag-string=s "
    "onall nonall filter-hosts|filterhosts|filter-host sshlogin|S=s "
    "sshloginfile|slf=s controlmaster|M ssh=s "
    "transfer-file|transferfile|transfer-files|transferfiles|tf=s return=s "
    "trc=s transfer cleanup basefile|bf=s B=s ctrlc|ctrl-c "
    "noctrlc|no-ctrlc|no-ctrl-c workdir|work-dir|wd=s W=s tmpdir=s "
    "tempdir=s use-compress-program|compress-program=s "
    "use-decompress-program|decompress-program=s compress tty T H=i "
    "dry-run|dryrun progress eta bar shuf arg-sep|argsep=s "
    "arg-file-sep|argfilesep=s trim=s env=s recordenv|record-env plain "
    "profile|J=s pipe|spreadstdin robin|round-robin|roundrobin recstart=s "
    "recend=s regexp|regex remove-rec-sep|removerecsep|rrs "
    "files|output-as-files|outputasfiles block|block-size|blocksize=s tollef "
    "gnu link|xapply linkinputsource|xapplyinputsource=i bibtex|citation "
    "wc|willcite|will-cite|nn|nonotice|no-notice halt-on-error|halt=s "
    "memfree=s retries=s timeout=s termseq|term-seq=s max-procs|P=s "
    "delimiter|d=s max-chars|s=i arg-file|a=s no-run-if-empty|r "
    "replace|i:s E=s eof|e:s max-args|n=i max-replace-args|N=i "
    "colsep|col-sep|C=s help|h L=f max-lines|l:f interactive|p verbose|t "
    "version|V minversion|min-version=i show-limits|showlimits exit|x "
    "semaphore semaphoretimeout|st=i semaphorename|id=s fg bg wait "
    "shebang|hashbang internal-pipe-means-argfiles Y skip-first-line "
    "header=s cat fifo pipepart|pipe-part tee "
    "hgrp|hostgrp|hostgroup|hostgroups")
WRAPPER_TABLES = {"xargs": getopt_tables(_XARGS),
                  "parallel": getopt_tables(_PARALLEL, strict=True)}
WRAPPER_TABLES["sem"] = WRAPPER_TABLES["parallel"]  # `parallel --semaphore`


class GateFed(list):
    """`_unwrap`'s `fed` for the gate: also `unknown`, which names the first
    option a listed wrapper's complete tables do not know, and its wrapper:
    the could-not-tell reason says it."""
    unknown = None


def note_unknown(fed, head, option):
    if isinstance(fed, GateFed) and fed.unknown is None:
        fed.unknown = f"{head!r} with an option it does not know: {option!r}"


def wrapper_rest(head, args, takes, fed=None, env=None):
    """`skip_wrapper_options` for wrapper `head`, with its complete tables
    when it has them; an option they do not know is noted on `fed`. For
    `aws-vault` and `unbuffer`, what `unwrap_listed` reads (`env` as for
    `cloud_guard._unwrap`)."""
    if head in LISTED_WRAPPERS:
        return unwrap_listed(head, args, {} if env is None else env, fed)
    unknown = []
    _value, optional, flags = WRAPPER_TABLES.get(head, (None, frozenset(),
                                                        None))
    rest = skip_wrapper_options(args, takes, optional, flags, unknown=unknown)
    if unknown:
        note_unknown(fed, head, unknown[0])
    return rest


def option_words(head, args, takes):
    """The options in front of `args`, spelled in full, values as words."""
    out = []
    _value, optional, flags = WRAPPER_TABLES.get(head, (None, frozenset(),
                                                        None))
    skip_wrapper_options(args, takes, optional, flags, out=out)
    return out


# aws-vault v7: `cli/global.go` and `cli/exec.go` at
# https://github.com/99designs/aws-vault (master, read 2026-10-04), plus the
# flags kingpin adds itself. Kingpin reads a flag anywhere before `--`, so a
# flag after the profile is aws-vault's, not the command's.
_AWS_VAULT = getopt_tables(
    "backend=s prompt=s keychain=s secret-service-collection=s pass-dir=s "
    "pass-cmd=s pass-prefix=s file-dir=s debug help version help-long "
    "help-man duration|d=s region=s mfa-token|t=s no-session|n json|j "
    "server|s ec2-server ecs-server lazy stdout")
LISTED_WRAPPERS = frozenset(("aws-vault", "unbuffer"))


def unwrap_listed(head, args, env, fed=None):
    """The argv `aws-vault exec` or `unbuffer` runs, or `[]` when it runs
    none. `aws-vault exec [flags] <profile> [--] cmd...` puts temporary keys
    in the environment, so an `aws` it runs has an unnamed account (as with
    static `AWS_ACCESS_KEY_ID`). `unbuffer [-p] cmd...`: expect's script
    takes no other option."""
    if head == "unbuffer":
        args = args[1:] if args[:1] == ["-p"] else args
        if args and args[0].startswith("-"):
            note_unknown(fed, head, args[0])
        return list(args)
    takes, optional, flags = _AWS_VAULT
    positional, index = [], 0
    while index < len(args):
        if args[index] == "--":
            positional += args[index + 1:]
            break
        unknown = []
        rest = skip_wrapper_options(args[index:], takes, optional, flags,
                                    unknown=unknown)
        if unknown:
            note_unknown(fed, head, unknown[0])
        if index < len(args) - len(rest) and \
                args[len(args) - len(rest) - 1] == "--":
            positional += rest
            break
        index = len(args) - len(rest)
        if rest:
            positional.append(rest[0])
            index += 1
    if positional[:1] != ["exec"] or len(positional) < 3:
        return []
    env["AWS_ACCESS_KEY_ID"] = _HOLE + "aws-vault"
    return positional[2:]


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
    if rest[:2] == ["workspace", "select"]:
        return _selects_only(rest[2:])  # fed: `_argv_trigger`, unseen
    pair = _TF_READ_ONLY_PAIRS.get(rest[0])
    return pair is not None and len(rest) > 1 and rest[1] in pair


# Go's `strconv.ParseBool` false spellings: `-or-create=false` creates nothing.
_GO_FALSE = frozenset(("0", "f", "F", "false", "FALSE", "False"))


def _selects_only(args):
    """`workspace select` creates nothing (review round 8: a quoted name is
    still a select) unless an `-or-create` on it is anything but false --
    bare, `=true`, or made at run time: a bash word with `_HOLE`, a
    PowerShell variable or splat (`$flag`, `@args`). A group or an array
    (`@("-or-create","production")`, `-or-create,production`) is
    `_ps_backstop`'s."""
    for arg in args:
        if _HOLE in arg or "$" in arg or arg.startswith("@"):
            return False
        name, sep, value = arg.lstrip("-").partition("=")
        if arg.startswith("-") and name == "or-create" and (
                not sep or value not in _GO_FALSE):
            return False
    return True


def _zsh_names_tool(word):
    """zsh expands `=terraform` to terraform's path (`EQUALS`)."""
    return word.startswith("=") and _names_tool(word[1:])


def _arg_names_tool(word):
    """An argument that may be terraform: its name or zsh's `=terraform`."""
    return _names_tool(word) or _zsh_names_tool(word)


def _first_operand(args):
    return next((a for a in args if not a.startswith("-")), None)


def _hole_known(argv, top):
    """What the precise reader's `_HOLE` command word in `argv` (after its
    own unwrapping) really is, or False when it is a program made at run
    time -- 1.2.35's rule then decides (SRL-2308 r3). A lone assignment
    (`W=$S/x`) runs nothing: the line's command words decide
    (`command_word_names_tool`). A literal last part under a run-time
    directory (`$W/stub.sh apply`) names its program: the tool (gated but
    for one read-only subcommand), one that runs another (made at run time
    after all), or any other program -- not gated only while it keeps the
    trust `_path_program_trusted` allows (SRL-2308 r4, r3-2: no changing
    verb among its operands, and nothing written into its directory or at
    its name on the line); otherwise made at run time too."""
    first = argv[0]
    if len(argv) == 1 and _FALLBACK_ASSIGN_RE.match(first):
        named = command_word_names_tool(top)
        return None if named is None else (named, True)
    base = re.split(r"[/\\]", first)[-1]
    if base == first or not base or _HOLE in base:
        return False
    if _names_tool(base):
        if len(argv) == 2 and _PLAIN_WORD_RE.match(argv[1]) \
                and argv[1] in _TF_READ_ONLY:
            return None
        return base, True
    if _runs_other(_head_name(base)):
        return False
    return None if _path_program_trusted(argv[1:], top, base) else False


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
    def hole(argv, top, shell="bash"):
        """`(word, True)` for a command word made at run time when the line
        names one of the words a terraform line needs (1.2.35's rule, bash
        and PowerShell), else None. Bash, SRL-2308: a lone assignment runs
        nothing and a literal program under a run-time directory is named
        (`_hole_known`); those ask what the line's command words run."""
        if shell == "bash":
            known = _hole_known(argv, top)
            if known is not False:
                return known
        named = _verb_on_line(top) if shell == "bash" else _ps_verb_on_line(top)
        if named is None and shell == "bash" and _ifs_splits(top):
            # What 1.2.35's rule cannot see: IFS splitting a value
            # (`IFS=x; T=terraformxapply; $T`), the fallback's own check.
            named = command_word_names_tool(top)
        return None if named is None else (named, True)

    @staticmethod
    def direct(argv, fed, _depth):
        """`(word, unseen)` or None when `argv`'s command word names the tool;
        False when it does not."""
        first = argv[0]
        if _zsh_names_tool(first):
            return first, True
        if _names_tool(first) and fed and [w for w in argv[1:] if not
                                           w.startswith("-")][:2] == [
                                               "workspace", "select"]:
            # `xargs`/`parallel` may append `-or-create`: could not tell.
            return first, True
        if _names_tool(first):
            return None if _tf_read_only(argv, fed) else (first, False)
        return False

    @staticmethod
    def interpreted(head, args, top):
        """The word naming the tool that interpreter `head` (`python3`,
        `node`, `perl`, `ruby`, `php`, `deno`) runs as code, or None
        (SRL-2308 r2): its `-c`/`-e`/... code from `args` (`_HOLE` where an
        expansion is), then the line's own reading of it -- a heredoc or
        here-string fed to it, or the whole line when it reads stdin and
        crew cannot find it at the top of the line."""
        spec = _interp_family(head)
        if spec is None:
            return None
        codes, stdin = _interp_codes(spec, args)
        for _index, code in codes:
            # A `_HOLE` is a value made at run time (SRL-2308 r3): 1.2.35's
            # rule first, then the code with a `$` where it was.
            named = _judge_code(code.replace(_HOLE, "$_"), spec, top,
                                _HOLE in code)
            if named is not None:
                return named
        unknown = {i for i, a in enumerate(args) if _HOLE in a}
        named = _perl_magic(spec, args, codes, unknown)
        return named if named is not None else \
            interpreted_on_line(top, stdin)

    @staticmethod
    def verb_on_line(text, shell="bash"):
        """The word naming the tool on a line that also names a verb."""
        return _verb_on_line(text) if shell == "bash" else \
            _ps_verb_on_line(text)

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
    def opaque(args, top, launched=None, _typed=None, _copies=()):
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

    @staticmethod
    def bash_aliases(_cmds, _helpers=None):
        """Names a bash line aliases the tool to: none followed (T-0005's
        copies are `_copies_terraform`'s alone)."""
        return set()


class _UnreadableTerraform:
    """What the reader's give-up asks for terraform (SRL-2308): a command
    word that could run the tool, never a mention."""

    @staticmethod
    def on_line(text, _shell="bash"):
        return command_word_names_tool(text)


_TerraformTool.unreadable = _UnreadableTerraform()
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
    fed = GateFed()
    argv = unwrap(argv, {}, fed, {"cd": False})
    if fed.unknown is not None:
        # A listed wrapper's option its tables do not know: where the
        # command starts is not known (T-0047).
        named = tool.on_line(top, "bash")
        return None if named is None else (named, fed.unknown)
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
    interpreted = getattr(tool, "interpreted", None)
    named = None if interpreted is None else interpreted(head, args, top)
    if named is not None:
        # `python3 -c "import os; os.system('terraform apply')"`: code
        # that names the tool and does more than print (SRL-2308 r2). A
        # python or node hit carries the construct that caused it (L-0871).
        why = getattr(named, "why", "")
        return named, InterpreterReason(why) if why else True
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
        own = tool.opaque(args, top, _copies=line["copies"])
        return None if own is None else (own, True)
    if head in line["copies"]:
        # `ln -sf /usr/bin/terraform tf && ./tf destroy`: the name the line
        # copied or linked the tool to, run with a verb. A line that only
        # mentions terraform (`cp -r terraform bk && git apply x.patch`,
        # `terraform fmt && kubectl apply -f k.yaml`) is not read this way,
        # and neither is a program crew does not know as a wrapper
        # (`strace`, `systemd-run`): Step 10, direct use only; README
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
        # Terraform's give-up reads command words only (SRL-2308); T-0009's
        # dispatch tool, which has no `unreadable`, keeps its own line rule.
        tool = getattr(tool, "unreadable", tool)
        named = tool.on_line(text, "bash") or tool.on_line(top, "bash")
        return None if named is None else (named, True)
    line = {"copies": set()} if line is None else line
    line["copies"] |= _copies_terraform(cmds, helpers[4], _GATE_COPIERS,
                                        tool.copy_source)
    if any(argv and helpers[4](argv[0]) in _GATE_DEFERS for argv in cmds):
        # A loop, a function or a trap runs text written BEFORE an alias or
        # `hash -p` after it: every one on the line counts (review round 5).
        line["copies"] |= tool.bash_aliases(cmds, helpers)
    found, unseen = None, False
    for argv in cmds:
        hit = _argv_trigger(argv, top, helpers, depth, line, tool)
        if hit is not None:
            found = found or hit[0]
            unseen = unseen or hit[1]
            if isinstance(hit[1], InterpreterReason) and \
                    not isinstance(unseen, InterpreterReason):
                unseen = hit[1]  # the first interpreter's construct (L-0871)
        # An alias or `hash -p` names gh for the REST of the line only.
        line["copies"] |= tool.bash_aliases([argv], helpers)
    return None if found is None else (found, unseen)


# PowerShell commands that run a program an argument names, or give it another
# name (review round 5): `Start-Process terraform -ArgumentList destroy`,
# `Set-Alias tf terraform`. `Invoke-Expression` is read as the eval it is.
_PS_LAUNCHERS = frozenset((
    "set-alias", "sal", "new-alias", "nal", "import-alias", "ipal",
    "start-process", "saps", "start", "invoke-command", "icm", "start-job",
    "sajb", "start-threadjob", "invoke-item", "ii"))
_PS_EVAL = frozenset(("invoke-expression", "iex"))
_PS_ALIASERS = frozenset(("set-alias", "sal", "new-alias", "nal",
                          "import-alias", "ipal"))
_PS_ASSIGN_OPS = ("=", "+=", "-=", "*=", "/=", "??=")


def ps_head_slot(words):
    """True where a PowerShell command word may start: no word yet, or
    just after `$x =` (`$x = iex("...")`, `$x = & "terraform" destroy`)."""
    return not words or len(words) == 2 and str(words[0]).startswith("$") \
        and words[1] in _PS_ASSIGN_OPS


# A guarded tool named in raw PowerShell text: the guard's own names, any
# case, as a word or a path's last part (`C:\\tools\\terraform.exe`), never a
# directory (`terraform/main.tf`), a dotted file (`terraform.log`) or a
# hidden one (`.terraform`).
_PS_MENTION_RE = re.compile(
    r"(?<![\w.-])(?:" + "|".join(sorted({n.split(".")[0] for n in _TF_NAMES}))
    + r")(?:\.(?:exe|cmd|bat|ps1))?(?![\w.\\/-])", re.IGNORECASE)


def _ps_uncommented(text):
    """`text` without PowerShell comments (`# ...` starting a word, `<# #>`),
    outside quotes, as `_lex_ps` drops them."""
    out, i, quote = [], 0, None
    while i < len(text):
        char = text[i]
        if char == "`":
            out.append(text[i:i + 2])
            i += 2
            continue
        if quote:
            quote = None if char == quote else quote
        elif char in "'\"":
            quote = char
        elif text.startswith("<#", i):
            end = text.find("#>", i + 2)
            i = len(text) if end < 0 else end + 2
            continue
        elif char == "#" and (not out or out[-1][-1:] in " \t\n;{(|"):
            end = text.find("\n", i)
            i = len(text) if end < 0 else end
            continue
        out.append(char)
        i += 1
    return "".join(out)


def _ps_mentions(text):
    return len(_PS_MENTION_RE.findall(_ps_uncommented(text).replace("`", "")))


def _ps_layout(cmd):
    """`(words, start, called)`: the command word's index past `$x =` and
    `&`/`.`, and whether a call operator runs it."""
    words = [str(w) for w in cmd.words]
    start = 2 if len(words) > 2 and ps_head_slot(words[:2]) else 0
    called = getattr(cmd, "called", False)
    if words[start:start + 1] in (["&"], ["."]):
        called, start = True, start + 1
    return words, start, called


# Statement keywords that run what follows them as their own pipeline
# (`return terraform destroy`). Other statements are parsed into: an `if` or
# `foreach` condition is a group (a sub-expression the guard reads) and a
# block's commands are commands of their own.
_PS_RUNS_REST = frozenset(("return", "throw", "exit"))


def _ps_runner(cmd, head_name):
    """True when `cmd` may run something made at run time: a launcher, an
    eval, an alias definition, `return`/`throw`/`exit` (which run what
    follows), or a command word that is not a plain name (`$t`,
    `[Diagnostics.Process]::Start(...)`, `& (gcm x)`)."""
    words, start, called = _ps_layout(cmd)
    if start >= len(words) or start in getattr(cmd, "opens", ()) and \
            not called:
        return False
    plain = type(cmd.words[start]).__name__ == "_Bare" and \
        _PS_NAME_RE.match(words[start])
    return not plain or head_name(words[start]).lower() in (
        _PS_LAUNCHERS | _PS_EVAL | _PS_ALIASERS | _PS_RUNS_REST)


def _ps_cmd_accounted(cmd, runner, helpers, depth):
    """How many guarded-tool mentions in `cmd` the guard accounts for: its
    command word when that is the tool, run plainly; an Invoke-Expression
    whose script is a literal it reads (`_ps_accounted` of that script);
    and, only when no runner is on the line, the literal arguments of a
    plainly named command that is no runner (data:
    `git commit -m "terraform destroy"`, `Write-Output (...)`) and a string
    a command only prints or assigns (`$m = "terraform destroy"`). A word a
    group makes is its sub-expression's to account for."""
    words, start, called = _ps_layout(cmd)
    if start >= len(words):
        return 0
    groups, head_name = getattr(cmd, "groups", set()), helpers[4]
    data = sum(_ps_mentions(w) for i, w in enumerate(words)
               if i > start and i not in groups)
    if start in getattr(cmd, "opens", ()) and not called:
        return 0 if runner else data + _ps_mentions(words[start])
    head = head_name(words[start]).lower()
    if head in _PS_EVAL and not groups and _ps_runner(cmd, head_name) and \
            not any("$" in w or w.startswith("@") for w in words[start:]):
        script, sure = ps_eval_script(words[start + 1:])
        return _ps_accounted(script, helpers, depth + 1) if sure else 0
    if _ps_runner(cmd, head_name):
        return 0
    own = 1 if _names_tool(words[start]) else 0
    return own + (0 if runner and not own else data)


def _ps_accounted(normal, helpers, depth=0):
    """Every guarded-tool mention `_ps_cmd_accounted` accounts for in
    `normal` and its sub-expressions (not trusted on a line with a
    runner)."""
    if depth > _GATE_DEPTH:
        return 0
    cmds, subs = helpers[5](normal)
    runner = any(_ps_runner(c, helpers[4]) for c in cmds)
    total = sum(_ps_cmd_accounted(c, runner, helpers, depth) for c in cmds)
    if not runner:
        total += sum(_ps_accounted(s, helpers, depth + 1) for s in subs)
    return total


def _ps_tool_args(cmd, head_name):
    """A group or a bare array (`a,b`) among the tool's own arguments: values
    made at run time (`workspace select (gc f)`)."""
    words, start, _called = _ps_layout(cmd)
    groups = getattr(cmd, "groups", set())
    return start < len(words) and _names_tool(head_name(words[start])) and (
        any(i > start for i in groups) or any(
            "," in w and type(cmd.words[i]).__name__ == "_Bare"
            for i, w in enumerate(words) if i > start))


def _ps_backstop(cmds, normal, helpers):
    """The structural backstop (review of #347, rounds 2-3): on PowerShell
    text naming a guarded tool, every mention must be one the guard
    accounted for (`_ps_accounted`), and the tool's own arguments may hold
    no group or array. Anything else is could not tell."""
    mentions = _ps_mentions(normal)
    if not mentions:
        return []
    named = names_terraform(normal, "powershell") or \
        _PS_MENTION_RE.search(normal.replace("`", "")).group(0).lower()
    if _ps_accounted(normal, helpers) < mentions:
        return [(named, "a mention of it the guard does not account for")]
    if any(_ps_tool_args(c, helpers[4]) for c in cmds):
        return [(named, "a group or an array among its arguments")]
    return []


# Words that start a PowerShell statement, never a wrapper `_unwrap` strips.
_PS_KEYWORDS = frozenset(("if", "elseif", "else", "while", "do", "until",
                          "for", "foreach", "switch", "try", "trap", "{",
                          "}", "!", "return", "throw"))
_PS_COPIERS = frozenset(("copy-item", "copy", "cpi", "cp", "move-item", "move",
                         "mi", "mv", "new-item", "ni", "rename-item", "ren",
                         "rni"))
# A command word PowerShell runs as written: a name or a path, no `$`, `(`,
# `+` or quote left in it.
_PS_NAME_RE = re.compile(r"^[A-Za-z0-9_./\\:~-]+$")


# Invoke-Expression's parameters: `-Command` (position 0) and the common
# parameters (about_CommonParameters), each with its documented alias.
# PowerShell takes a unique prefix of a name; an alias only whole.
_PS_EVAL_PARAMS = {
    "command": "script", "verbose": "switch", "debug": "switch",
    "erroraction": "value", "warningaction": "value",
    "informationaction": "value", "errorvariable": "value",
    "warningvariable": "value", "informationvariable": "value",
    "outvariable": "value", "outbuffer": "value", "pipelinevariable": "value",
    "progressaction": "value"}
_PS_EVAL_ALIASES = {
    "vb": "switch", "db": "switch", "ea": "value", "wa": "value",
    "infa": "value", "ev": "value", "wv": "value", "iv": "value",
    "ov": "value", "ob": "value", "pv": "value", "proga": "value"}


def ps_eval_script(args):
    """`(script, sure)` for Invoke-Expression's arguments: the script its
    `-Command` binds (by name, `-Command:<v>`, or by position), with every
    common parameter and its value set aside (review of #347). `sure` is
    False for a parameter crew does not know, or one PowerShell would call
    ambiguous. A script that is not a literal string is `_ps_backstop`'s on
    a line naming a guarded tool, and the nested reading's elsewhere."""
    script, sure, index = [], True, 0
    while index < len(args):
        arg, index = args[index], index + 1
        if not arg.startswith("-") or arg == "-":
            script.append(arg)
            continue
        name, colon, value = arg[1:].partition(":")
        name = name.lower()
        hits = [k for n, k in _PS_EVAL_PARAMS.items() if n.startswith(name)]
        kind = _PS_EVAL_ALIASES.get(name) or (
            hits[0] if len(hits) == 1 and name else None)
        if kind is None:
            sure = False
        elif kind == "script":
            script.extend([value] if colon else args[index:index + 1])
            index += not colon
        elif kind == "value":
            index += not colon
    return " ".join(script), sure


def _ps_verb_on_line(normal):
    """`_verb_on_line` for normalised PowerShell."""
    named = names_terraform(normal, "powershell")
    if named is not None:
        return named
    return next((c for c in _name_candidates(normal, "powershell")
                 if c.lower() in _GATE_VERBS), None)


def _ps_argv_trigger(words, normal, helpers, depth, copies, cmd=None,
                     tool=_TF_TOOL):
    """`(word, unseen)` when one PowerShell simple command -- the lexer's
    `words` -- runs the gated tool, or None: `_argv_trigger`'s rule, read the
    way PowerShell runs a line. `cmd`, the lexer's command: whether `&` ran
    it and which words open with a quote or a group."""
    _unwrap, shell_args, pwsh_payload, ps_normalise, head_name, _lex = \
        helpers
    argv = [str(w) for w in words]
    if len(argv) > 2 and argv[0].startswith("$") and argv[1] in (
            "=", "+=", "-=", "*=", "/=", "??="):
        argv, words = argv[2:], words[2:]  # `$out = terraform destroy` runs
    called = getattr(cmd, "called", False) or argv[:1] in (["&"], ["."])
    if argv and argv[0] in ("&", "."):
        argv, words = argv[1:], words[1:]
    if not argv or len(argv) == 1 and (argv[0].startswith("$") or type(
            words[0]).__name__ != "_Bare"):
        # Nothing, or an expression PowerShell only prints: `$x`, a quoted
        # string (`$m = "terraform destroy"`, `('terraform destroy')`).
        return None
    if not called and len(cmd.words if cmd else words) - len(words) in \
            getattr(cmd, "opens", ()):
        # A quoted first word, no `&`/`.`: PowerShell's expression mode,
        # which prints (`"terraform", "destroy"`, `("terraform" + " x")`).
        return None
    if "=" not in argv[0] and argv[0].lower() not in _PS_KEYWORDS:
        # The wrappers bash strips, read the same way (review round 8).
        fed = GateFed()
        argv = _unwrap(argv, {}, fed, {"cd": False})
        if fed.unknown is not None:
            named = tool.on_line(normal, "powershell")
            return None if named is None else (named, fed.unknown)
        if not argv:
            return None
        tail = words[len(words) - len(argv):]
        if [str(w) for w in tail] == argv:
            # The words the wrapper left, so `symbolic` reads gh's own
            # arguments, not the wrapper's (T-0009 port review). When they do
            # not line up, the two readings disagree: could not tell.
            words = tail
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
        script, sure = ps_eval_script(args)
        if not sure:
            # A parameter crew does not know: could not tell.
            named = tool.verb_on_line(normal, "powershell")
            return None if named is None else (named, True)
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
    hits += [_ps_argv_trigger(c.words, normal, helpers, depth, copies, c,
                              tool)
             for c in cmds]
    if tool is _TF_TOOL:  # the backstop counts terraform mentions only
        hits += _ps_backstop(cmds, normal, helpers)
    hits = [h for h in hits if h is not None]
    if not hits:
        return None
    how = next((h[1] for h in hits if isinstance(h[1], str)), None)
    if how is not None:  # names the wrapper whose option is not known
        return hits[0][0], how
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

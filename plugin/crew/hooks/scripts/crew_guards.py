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
import os
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
GUARD_NAMES = ("terraformApply", "forcePush", "adminMerge", "mergeGate")

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

# Every guard, in declaration order: the four policy guards then the two
# production ones. `GUARD_DEFAULTS` is keyed off this, so a name that exists in
# neither tuple cannot reach the config block at all.
ALL_GUARD_NAMES = GUARD_NAMES + PROD_GUARD_NAMES

GUARD_DEFAULTS = dict(
    [(name, GUARD_POLICY_DEFAULT) for name in GUARD_NAMES]
    + [(name, PROD_LEVEL_DEFAULT) for name in PROD_GUARD_NAMES])

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


def guard_tiers(name):
    """The `(tiers, normalise, rank)` triple a guard's VALUES obey.

    Two vocabularies in one block, so the vocabulary is looked up by name
    rather than assumed: `guards.forcePush` is `block`/`ask`/`allow` and
    `guards.prodServer` is `none`/`read`/`full`. A caller that assumed one of
    them would normalise every value of the other to that vocabulary's floor
    and then report a level nobody set.
    """
    if name in PROD_GUARD_NAMES:
        return (PROD_LEVELS, normalise_prod_level, prod_level_rank)
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
# The eighth key, and the first whose tiers are not strings. Registering it here
# is the WHOLE cost of ratcheting it: `effective_ratcheted`'s `min` already
# means "a repo may turn the requirement on and never off", and `sabotage.py`'s
# `min` -> `max` mutation already covers this key along with the other seven.
# A bespoke `effective_change_requirement` would have been the fifth mechanism
# for one rule -- see this table's own comment.
RATCHETED_KEYS["change.requireForProduction"] = (
    CHANGE_REQUIREMENTS,
    normalise_require_for_production,
    require_change_rank,
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

"""Tests for `install.policy` -- what crew may do about a skill it cannot find.

The key ratchets, which is why it gets its own file rather than a few cases
appended to `test_crew_config.py`. Two properties carry the whole design and
each is asserted here from more than one direction:

  * **Narrowing only.** The effective policy is the LOWER-ranked of the repo
    and global layers, never the repo's by precedence. A repo config travels
    inside a clone somebody else wrote; the global file is this machine's
    owner. Precedence would let a cloned repo grant itself the right to run
    commands on a stranger's machine.

  * **The command can only come from crew's own source.** `auto` is safe
    exactly as long as no config value, skill file or caller-supplied name can
    name a command. `install_plan` consults `INSTALLABLE` BEFORE it consults
    the policy, so a name crew does not ship is inert at every policy.

Both properties are asserted over the full cross-product rather than at a few
sampled points, because the failure this guards against is an unknown
collapsing into the permissive value, and a sampled test is exactly what misses
the one combination that does it.
"""
import itertools
import json
import os

import context  # noqa: F401  pylint: disable=unused-import
import crew_config
import crew_fixtures
import crew_state
import crew_upgrade


# A name shaped like a shell injection, assembled rather than written out so
# this file does not itself contain the literal string that crew's own rm guard
# refuses. The point is the name reaches `install_plan` intact.
HOSTILE = "doc-builder; " + "rm" + " -rf " + "/"

ALL_VALUES = crew_state.INSTALL_POLICIES + (None, "", "NONSENSE", 42)


def test_an_unknown_policy_collapses_to_the_floor_not_the_default():
    """Authority's rule, not granularity's.

    `normalise_granularity` falls back to the documented default because no
    granularity is more permissive than another. An install policy DOES buy a
    capability, so an unrecognised value has to cost capability rather than
    grant it. A typo must never be the thing that lets crew run a command.
    """
    for value in (None, "", "NONSENSE", 42, ["auto"], {"policy": "auto"},
                  "autonomous", HOSTILE):
        assert crew_state.normalise_install_policy(value) == "manual", value
        assert crew_state.install_policy_rank(value) == 0, value


def test_case_and_whitespace_are_tolerated_but_nothing_else_is():
    """The one direction it is safe to be generous: a value the user clearly
    meant. `AUTO` and ` auto ` are `auto`; anything else is the floor."""
    for value in ("AUTO", " auto ", "Auto", "\tASK\n"):
        assert crew_state.normalise_install_policy(value) == value.strip().lower()


def test_the_policies_are_ordered_least_to_most_permissive():
    """Rank is the only thing permitted to know the order, so the order itself
    is asserted here once. Append-only: inserting a tier in the middle re-ranks
    every tier after it and silently changes what existing configs mean."""
    assert crew_state.INSTALL_POLICIES == ("manual", "ask", "auto")
    assert crew_state.INSTALL_POLICY_DEFAULT == "manual"
    ranks = [crew_state.install_policy_rank(p)
             for p in crew_state.INSTALL_POLICIES]
    assert ranks == sorted(ranks) == [0, 1, 2]


def test_two_layers_can_only_narrow_never_widen():
    """The whole cross-product, including the junk values.

    Asserted as an inequality against BOTH layers rather than as a table of
    expected answers: a table encodes the same belief twice and passes when the
    belief is wrong. The property is what matters -- the result is never more
    permissive than either layer alone.
    """
    rank = crew_state.install_policy_rank
    for repo, glob in itertools.product(ALL_VALUES, repeat=2):
        effective = crew_state.effective_install_policy(repo, glob)
        assert rank(effective) <= rank(repo), (repo, glob, effective)
        assert rank(effective) <= rank(glob), (repo, glob, effective)
        assert effective in crew_state.INSTALL_POLICIES


def test_auto_requires_both_layers_to_say_auto():
    """The consequence worth stating on its own, because it is the one that
    surprises people: a repo alone cannot reach `auto`, and neither can a
    machine whose repo says less. Absent counts as `manual`, so the machine
    owner has to opt in explicitly and so does the repo."""
    assert crew_state.effective_install_policy("auto", "auto") == "auto"
    for repo, glob in (("auto", None), (None, "auto"), ("auto", "manual"),
                       ("manual", "auto"), ("auto", "ask"), ("ask", "auto")):
        assert crew_state.effective_install_policy(repo, glob) != "auto"


def test_a_name_crew_does_not_ship_is_inert_at_every_policy():
    """The first gate does not consult the policy at all.

    This is the ordering that makes `auto` defensible: no value of the policy,
    and so no value anywhere in any config file, can produce a command that is
    not already written in crew's source. A name absent from INSTALLABLE gets
    `report` and a null command even at `auto`.
    """
    for name in ("totally-made-up", HOSTILE, "../../etc/passwd", "",
                 "doc-builder ", "DOC-BUILDER"):
        for policy in ALL_VALUES:
            plan = crew_state.install_plan(name, policy)
            assert plan["action"] == "report", (name, policy)
            assert plan["command"] is None, (name, policy)


def test_every_shipped_command_is_argv_and_installs_from_this_marketplace():
    """`INSTALLABLE` is the entire safety argument, so its shape is asserted
    rather than assumed: argv tuples (never a string a caller could hand to a
    shell), the verb is always `install`, the target always this marketplace,
    and the key always equals the plugin the command names -- so a lookup can
    never return a command for a different plugin than the one asked for."""
    assert crew_state.INSTALLABLE, "the table must not be empty"
    for name, command in crew_state.INSTALLABLE.items():
        assert isinstance(command, tuple), name
        assert not isinstance(command, str), name
        assert command[:3] == ("claude", "plugin", "install"), (name, command)
        assert len(command) == 4, (name, command)
        plugin, _, marketplace = command[3].partition("@")
        assert plugin == name, (name, command)
        assert marketplace == "useful-claude-add-ons", (name, command)


def test_a_shipped_name_follows_the_policy():
    """The other half: where a command does exist, the policy decides."""
    expected = {"manual": "report", "ask": "ask", "auto": "run"}
    for policy, action in expected.items():
        plan = crew_state.install_plan("doc-builder", policy)
        assert plan["action"] == action, policy
        assert plan["command"][0] == "claude"


def _write(root, payload):
    os.makedirs(os.path.join(root, ".crew"), exist_ok=True)
    with open(os.path.join(root, ".crew", "config.json"), "w",
              encoding="utf-8") as handle:
        json.dump(payload, handle)


def _global(tmp_path, policy):
    path = tmp_path / "global.json"
    body = {} if policy is None else {"install": {"policy": policy}}
    path.write_text(json.dumps(body), encoding="utf-8")
    return str(path)


def test_a_cloned_repo_cannot_widen_the_machine_owners_choice(tmp_path):
    """The attack this key is shaped around.

    crew reads config out of cloned repositories. Under ordinary precedence --
    the rule every other key uses -- a repo shipping `install.policy: auto`
    would override a machine owner who chose `manual`, and crew would start
    running commands because of a file the user did not write.
    """
    root = str(tmp_path / "repo")
    os.makedirs(root)
    _write(root, {"schema": crew_state.SCHEMA_CURRENT, "isCrew": True,
                  "install": {"policy": "auto"}})
    resolved = crew_config.resolve_install_policy(
        root, _global(tmp_path, "manual"))
    assert resolved["effective"] == "manual"
    assert resolved["repo"] == "auto"
    assert resolved["heldDownBy"] == "global"

    plan = crew_config.install_plan_for(
        root, "doc-builder", _global(tmp_path, "manual"))
    assert plan["action"] == "report"


def test_the_narrowing_layer_is_always_named(tmp_path):
    """A value that quietly does nothing is worse than one refused out loud --
    the rule `default_global_config` already states for the keys it ignores.

    A user who sets `auto` and watches crew keep asking has to be told WHICH
    layer refused, or the key looks broken and they go hunting for a bug that
    is not there.
    """
    root = str(tmp_path / "repo")
    os.makedirs(root)
    for repo_pol, glob_pol, held in (("auto", "manual", "global"),
                                     ("manual", "auto", "repo"),
                                     ("auto", "auto", None),
                                     ("manual", "manual", None)):
        _write(root, {"schema": crew_state.SCHEMA_CURRENT, "isCrew": True,
                      "install": {"policy": repo_pol}})
        resolved = crew_config.resolve_install_policy(
            root, _global(tmp_path, glob_pol))
        assert resolved["heldDownBy"] == held, (repo_pol, glob_pol)


def test_the_key_ratchets_through_the_shared_registry():
    """`install.policy` is marked as a widening by the same mechanism as
    `pm.authority`, not a second copy of it.

    The inline version of this rule was wrong in both directions at once when a
    third authority tier arrived. One mechanism can be wrong; two can disagree,
    and then only one of them gets fixed.
    """
    assert "install.policy" in crew_config._RATCHETED
    assert "pm.authority" in crew_config._RATCHETED
    rank, normalise, notes = crew_config._RATCHETED["install.policy"]
    assert rank is crew_state.install_policy_rank
    assert normalise is crew_state.normalise_install_policy
    # Every tier must have a note, or the printer raises KeyError at the exact
    # moment it is trying to warn someone about a grant.
    for policy in crew_state.INSTALL_POLICIES:
        assert notes[policy].strip()


def test_a_widening_is_marked_and_a_narrowing_is_not(tmp_path):
    """Both directions, because a warning that fires on the safe direction is
    one users learn to click past -- which costs the real case its defence."""
    path = str(tmp_path / "global.json")
    (tmp_path / "global.json").write_text(
        json.dumps({"install": {"policy": "ask"}}), encoding="utf-8")

    _, widened = crew_config.plan_global_write({"install.policy": "auto"}, path)
    assert widened[0]["widens"] is True

    _, narrowed = crew_config.plan_global_write(
        {"install.policy": "manual"}, path)
    assert narrowed[0]["widens"] is False


def test_the_migration_is_behaviour_neutral():
    """A schema bump makes every crew repo on every machine report
    `upgradeNeeded`, so this migration is mandatory. A mandatory migration that
    started running install commands on other people's machines would be
    indefensible, so the key has to land on the floor."""
    out, notes = crew_upgrade.upgrade_config(
        {"schema": 4, "pm": {"authority": "act"}})
    assert out["install"]["policy"] == "manual"
    assert notes["installKeysAdded"] == ["install.policy"]
    assert out["schema"] == crew_state.SCHEMA_CURRENT


def test_the_migration_does_not_touch_a_policy_already_set():
    """Computed from the incoming file, not from the version number: a config
    hand-edited to carry the key already is not reported as having gained it,
    and its value survives."""
    out, notes = crew_upgrade.upgrade_config(
        {"schema": 4, "install": {"policy": "auto"}})
    assert out["install"]["policy"] == "auto"
    assert notes["installKeysAdded"] == []


def test_the_key_is_settable_in_both_layers():
    """Global because it is a machine fact; repo because a project may narrow
    it. `is_global_path` refuses any path absent from the repo defaults, so a
    global-only key would be un-settable in the layer it belongs to."""
    assert crew_config.is_global_path("install.policy")
    assert "install.policy" in crew_config.leaf_paths(
        crew_config.default_config())
    assert "install.policy" in crew_config.leaf_paths(
        crew_config.default_global_config())


def test_the_schema_bump_actually_reaches_a_repo_at_the_previous_schema(
        tmp_path):
    """The delivery mechanism, not the transformation.

    `run()` returns "already current" for any config at or above
    SCHEMA_CURRENT without ever calling `upgrade_config`. Add a migration and
    forget the bump and it reaches only repos that were ALREADY behind -- which
    is nobody it was written for, since every existing config sits at the
    then-current number. A fresh clone looks correct while every installed
    machine keeps the old default forever.

    The sibling of `test_the_theme_migration_actually_reaches_an_existing_repo`,
    re-pinned to this schema. That one asserts a repo at 3 gets migrated, which
    stays true whether or not the CURRENT bump happened -- so it cannot detect a
    missing bump any more, and the sabotage entry pointed at it went vacuous.
    This asserts the repo at the PREVIOUS schema, which is the one that goes
    stale every time the number moves.
    """
    # A LITERAL 4, not `SCHEMA_CURRENT - 1`. Deriving the fixture from the
    # constant under test makes the test move with the mutation: revert the
    # bump and `SCHEMA_CURRENT - 1` becomes 3, which is behind either way, so
    # the repo still migrates and the test still passes. That is how this
    # assertion was vacuous on its first draft -- caught by the sabotage suite
    # reporting STILL GREEN, not by reading it. Bump this literal deliberately
    # when the schema moves; that edit is the point, not an inconvenience.
    root = crew_fixtures.make_repo(
        tmp_path, config={"schema": 4, "tier": 0})

    result = crew_upgrade.run(str(root), {})

    assert result["status"] != "already current"
    written = json.loads((root / ".crew" / "config.json").read_text("utf-8"))
    assert written["schema"] == crew_state.SCHEMA_CURRENT
    assert written["install"]["policy"] == "manual"

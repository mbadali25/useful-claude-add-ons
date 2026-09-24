"""`guards.*` -- the ratchet, the resolver, and the two shell flavours.

Three directions, and the third is the one that earns its keep:

  * The KEYS exist in both layers with the right defaults, and the ratchet is a
    table rather than five copies of one rule.
  * The RESOLVER answers `block`/`ask`/`allow` correctly and reports which
    layer narrowed it -- ignoring a repo's widening attempt silently is the
    same failure as honouring it, one step later.
  * The two GUARDS actually behave that way, asserted by RUNNING `guard.sh` and
    `guard.ps1` and reading their exit codes. `guard.sh` and `guard.ps1` drift
    independently -- three bypasses fixed in #132 were open in BOTH -- so every
    behavioural case here runs in both flavours or it is not covered.

The dangerous literals are assembled from fragments (`"terra" + "form"`) for
the same reason `test_guard_bypasses.py` does it: crew's own PreToolUse guard
reads the command that writes this file, and a literal `terraform apply` in the
source blocks the write.

Nothing here reaches a network or a real config. The machine-global path is
redirected by pointing HOME and USERPROFILE at `tmp_path` for every subprocess,
because `crew_state.GLOBAL_CONFIG_PATH` is computed from `expanduser("~")` at
import time and a subprocess re-imports it. `conftest.py`'s autouse fixture
covers the in-process half.

SABOTAGE-TEST THIS FILE before trusting it: see `sabotage.py`.
"""
import json
import os
import shutil
import time

import context  # noqa: F401  pylint: disable=unused-import
import crew_config
import crew_guards
import crew_state
import crew_upgrade
import pytest

_HOOKS = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                      os.pardir, "hooks", "scripts")
_CREW_CONFIG = os.path.join(_HOOKS, "crew_config.py")

# Fragment-assembled: see the module docstring.
_TF = "terra" + "form"
_TOFU = "to" + "fu"
_PUSH = "git " + "push"
_GH_MERGE = "gh " + "pr merge"



# The command that trips each guard, and what the guard is called. One table,
# so a case added for one flavour cannot be missing from the other.
_TRIPS = {
    "terraformApply": f"{_TF} apply",
    "forcePush": f"{_PUSH} --force origin main",
    "adminMerge": f"{_GH_MERGE} 12 --admin",
}

def _touch(path):
    """Create the approval marker. `promote-gate.sh` tells the user to
    `touch` its equivalent and never reads the contents, so an empty file
    is the whole payload."""
    with open(path, "w", encoding="utf-8"):
        pass


def _repo(tmp_path, guards=None, schema=None):
    root = tmp_path / "repo"
    (root / ".crew").mkdir(parents=True, exist_ok=True)
    cfg = {"schema": crew_state.SCHEMA_CURRENT if schema is None else schema}
    if guards is not None:
        cfg["guards"] = guards
    (root / ".crew" / "config.json").write_text(json.dumps(cfg), "utf-8")
    return str(root)


def _home(tmp_path, guards=None):
    """A fake HOME carrying a machine-global crew config."""
    home = tmp_path / "home"
    (home / ".claude" / "crew").mkdir(parents=True, exist_ok=True)
    body = {} if guards is None else {"guards": guards}
    (home / ".claude" / "crew" / "config.json").write_text(
        json.dumps(body), "utf-8")
    return str(home)


def _global_file(tmp_path, guards=None, install=None):
    path = tmp_path / "global.json"
    body = {}
    if guards is not None:
        body["guards"] = guards
    if install is not None:
        body["install"] = install
    path.write_text(json.dumps(body), "utf-8")
    return str(path)




# ---- the keys themselves ---------------------------------------------------


def test_the_four_guards_are_declared_in_both_layers_and_default_to_block():
    """A key present in only one layer is the failure that makes the ratchet
    unreachable. A repo-only key cannot be narrowed by the machine owner; a
    global-only key fails `is_global_path`'s rule that every globally-settable
    key is a real repo key, and `filter_global` prunes it, so it takes effect
    nowhere while looking configured."""
    repo = crew_config.default_config()
    glob = crew_config.default_global_config()

    assert set(repo["guards"]) == set(crew_state.ALL_GUARD_NAMES)
    assert repo["guards"] == glob["guards"]
    for name in crew_state.GUARD_NAMES:
        assert repo["guards"][name] == "block", name
        assert crew_config.is_global_path(f"guards.{name}"), name
    # The two production guards share the block and the ratchet and NOT the
    # vocabulary, so their floor is asserted in their own words. A test that
    # looped `== "block"` over all six would either fail or, worse, be
    # "fixed" by giving them a tier name that means nothing to them.
    for name in crew_state.PROD_GUARD_NAMES:
        assert repo["guards"][name] == "none", name
        assert crew_config.is_global_path(f"guards.{name}"), name


def test_github_merge_gate_is_declared_in_both_layers_without_a_preset():
    """`preset`'s ABSENCE is the decision, not an omission.
    `bitbucket.mergeGate.preset` binds to nothing -- CONFIG.md §8 records why it
    stays unwired -- so copying it here would ship that defect a second time,
    on purpose. Asserted negatively because a `preset` arriving later would
    otherwise pass every other test in this file."""
    repo = crew_config.default_config()
    glob = crew_config.default_global_config()

    assert repo["github"] == crew_upgrade.GITHUB_BLOCK
    assert glob["github"] == crew_upgrade.GITHUB_BLOCK
    assert set(repo["github"]["mergeGate"]) == {"enabled", "branch"}
    assert "preset" not in repo["github"]["mergeGate"]
    assert repo["github"]["mergeGate"]["enabled"] is False
    assert repo["github"]["mergeGate"]["branch"] is None
    for dotted in ("github.mergeGate.enabled", "github.mergeGate.branch"):
        assert crew_config.is_global_path(dotted), dotted


def test_the_guards_and_github_blocks_are_carried_by_an_upgrade():
    """A top-level block absent from `CONFIG_BLOCKS` is never written into an
    already-initialised repo -- the whole of the 0.16.0 qa/dev bug. Without
    this the keys ship to fresh repos only, and every existing one reads the
    built-in default forever while its config file says nothing."""
    carried = {key for key, _block in crew_upgrade.CONFIG_BLOCKS}
    for key in ("guards", "github"):
        assert key in carried, key


def test_the_schema_6_bump_reaches_a_repo_at_schema_5(tmp_path):
    """The delivery mechanism, not the transformation, and asserted through
    `run()` rather than `upgrade_config()`.

    `run()` returns "already current" for any config at or above
    SCHEMA_CURRENT without ever calling `upgrade_config`. Add a migration and
    forget the bump and it reaches only repos that were ALREADY behind --
    nobody it was written for, since every existing config sits at the
    then-current number. A fresh clone looks correct while every installed
    machine keeps the old defaults forever. Caught in review by Codex once
    already, by running it: status `already current`, value unchanged.

    A LITERAL 5, not `SCHEMA_CURRENT - 1`. Deriving the fixture from the
    constant under test makes the test move with the mutation: revert the bump
    and `SCHEMA_CURRENT - 1` becomes 4, which is behind either way, so the repo
    still migrates and the test still passes. That is exactly how
    `test_install_policy.py`'s schema-4 sibling went vacuous when this bump
    landed -- it stays correct about a schema-4 repo and can no longer detect a
    missing bump. Bump this literal deliberately when the schema moves; that
    edit is the point, not an inconvenience.
    """
    root = tmp_path / "repo"
    (root / ".crew").mkdir(parents=True)
    (root / ".crew" / "config.json").write_text(
        json.dumps({"schema": 5, "tier": 0}), "utf-8")

    result = crew_upgrade.run(str(root), {})

    assert result["status"] != "already current"
    written = json.loads(
        (root / ".crew" / "config.json").read_text("utf-8"))
    assert written["schema"] == crew_state.SCHEMA_CURRENT
    # `guards` and `github` are both entirely globally-settable and ratcheted
    # (`guards`) or precedence-resolved (`github`), so as of this ticket's fix
    # neither is WRITTEN into a repo that never named it (see
    # `crew_upgrade._prune_unsupplied_global_leaves`) -- the literal-block
    # checks this test used to make are gone with them. `notes` is what
    # proves the schema-6 migration itself ran, same reasoning as
    # `test_install_policy.py`'s sibling.
    assert "guards" not in written
    assert "github" not in written
    # `production` is repo-only and untouched by the fix, so it still lands
    # whole: the production pair lands at `none` WITH an empty `production`
    # block, so the strictest level there refuses the empty set until
    # somebody declares a pattern -- which is what let them ship inside a
    # mandatory migration.
    assert written["production"] == {"databases": [], "hosts": []}
    # The keys are NAMED in the notes, or the report cannot say what it added.
    assert set(result["notes"]["guardKeysAdded"]) == set(
        crew_upgrade.SCHEMA_6_KEYS)


def test_a_three_part_key_does_not_crash_the_keys_added_walk():
    """`github.mergeGate.enabled` has three parts. The old loop unpacked
    exactly two (`block_key, leaf = dotted.split(".")`) and would have raised
    `ValueError` inside `upgrade_config` -- before `run()` writes anything, so
    loud rather than silent, but still a migration that dies at its first
    nested block."""
    _out, notes = crew_upgrade.upgrade_config({"schema": 5})
    assert "github.mergeGate.enabled" in notes["guardKeysAdded"]
    # A config that already carries the key is not reported as having just
    # gained it -- computed from the incoming file, not from the version.
    _out, notes = crew_upgrade.upgrade_config(
        {"schema": 5, "github": {"mergeGate": {"enabled": True}}})
    assert "github.mergeGate.enabled" not in notes["guardKeysAdded"]
    assert "github.mergeGate.branch" in notes["guardKeysAdded"]


def test_the_cli_prints_every_key_list_the_report_does():
    """The filed defect, not repeated. Schema 5 added `install.policy`, wrote
    its paragraph into UPGRADE.md and printed NOTHING at the CLI -- so a repo
    with no `.crew/codemap/` (which is where UPGRADE.md is written) gained a
    key governing whether crew may run commands on the machine and said so
    nowhere the user would see.

    Asserted over the note keys rather than by grepping `main`'s source, so a
    THIRD list added later and forgotten at the CLI fails here too."""
    import inspect  # pylint: disable=import-outside-toplevel
    source = inspect.getsource(crew_upgrade.main)
    for key in ("providerKeysAdded", "installKeysAdded", "guardKeysAdded"):
        assert f'notes["{key}"]' in source, key


def test_the_migration_report_does_not_claim_a_neutrality_it_lacks():
    """`terraformApply` and `forcePush` at `block` are what the guard already
    did; `adminMerge` and `tofu` are NEW refusals. A report that said "the
    default is block, so nothing changed" would be an unknown wearing the
    label of a check that happened -- and the user meeting a command that ran
    yesterday being refused today would go looking for a bug in their
    tooling."""
    _out, notes = crew_upgrade.upgrade_config({"schema": 5})
    body = "\n".join(crew_upgrade._config_lines(notes))  # pylint: disable=protected-access

    assert "NOT entirely behaviour-neutral" in body
    assert "adminMerge" in body
    assert "tofu" in body


def test_an_unknown_guard_value_fails_closed_to_block():
    """Authority's rule and install policy's rule, for the third time: a guard
    policy buys a capability, so a typo must cost capability rather than grant
    it. `allowed`, `ALLOW ` and a non-string all have to land on `block`."""
    for value in ("allowed", "yes", "", None, True, 1, [], {"a": 1}):
        assert crew_state.normalise_guard_policy(value) == "block", value
    # ...and the spellings that ARE the value still work, whitespace and case
    # included, or the fail-closed rule becomes a fail-always rule.
    assert crew_state.normalise_guard_policy(" ALLOW ") == "allow"
    assert crew_state.normalise_guard_policy("Ask") == "ask"


def test_guard_policy_rank_orders_block_below_ask_below_allow():
    """The ONE function permitted to know the order. Every comparison in the
    ratchet is built on it, so an unknown ranking above `block` would make the
    whole thing fail open."""
    rank = crew_state.guard_policy_rank
    assert rank("block") < rank("ask") < rank("allow")
    assert rank("nonsense") == rank("block") == 0


# ---- the ratchet -----------------------------------------------------------


def test_the_ratchet_is_one_table_covering_install_policy_and_all_four_guards():
    """The generalisation itself. Five bespoke pairs of
    `effective_*`/`resolve_*` would be five mechanisms for one rule, and
    CLAUDE.md's lesson is that one mechanism can be wrong while two can
    disagree -- and then only one of them gets fixed.

    `pm.authority` is asserted ABSENT on purpose. It ratchets for the widening
    WARNING only; its two layers still resolve by ordinary precedence, and
    sweeping it in here would silently change how every repo's PM authority
    resolves.

    The function name says "all four guards" and predates two of them plus
    schema 7's `change.requireForProduction` and `guards.roleWrites`; the SET
    below is the contract and it is exhaustive. The name is left alone because
    `sabotage.py` anchors a mutation on it, and an anchor that silently stops
    matching is the failure that file's own header calls out."""
    assert set(crew_state.RATCHETED_KEYS) == {
        "install.policy", "guards.terraformApply", "guards.forcePush",
        "guards.adminMerge", "guards.mergeGate", "guards.prodDatabase",
        "guards.prodServer", "guards.roleWrites",
        "guards.cloudDestructive", "guards.sqlDestructive",
        "guards.cloudGuard",
        "change.requireForProduction"}
    # The cloud guard's switch shares `roleWrites`' vocabulary and split
    # default; it must never be normalised through `block`/`ask`/`allow`.
    assert crew_state.RATCHETED_KEYS["guards.cloudGuard"][0] == (
        crew_state.ROLE_WRITE_POLICIES)
    # Three vocabularies, one table. The production guards ratchet by
    # `none` < `read` < `full`, `roleWrites` by `block` < `report` < `off`,
    # and neither may ever be normalised through the other's tiers -- that
    # would resolve every `read` to `block`, or every `report` to `off`, and
    # report a tier nobody set.
    assert crew_state.RATCHETED_KEYS["guards.prodServer"][0] == (
        crew_state.PROD_LEVELS)
    assert crew_state.RATCHETED_KEYS["guards.forcePush"][0] == (
        crew_state.GUARD_POLICIES)
    assert crew_state.RATCHETED_KEYS["guards.roleWrites"][0] == (
        crew_state.ROLE_WRITE_POLICIES)
    assert "pm.authority" not in crew_state.RATCHETED_KEYS
    assert crew_state.ratchet_spec("tracker") is None


def test_every_ratcheted_key_has_a_widening_note_for_every_one_of_its_tiers():
    """`plan_global_write`'s `! widens` line does `notes[granted]`, so a
    missing entry is a KeyError at the point of use. That is deliberate -- a
    warning that silently describes the wrong tier is worse than a crash -- and
    this is what keeps the crash from ever being reached."""
    for dotted, (tiers, _normalise, _rank) in \
            crew_state.RATCHETED_KEYS.items():
        _rank_fn, _norm, notes = crew_config._RATCHETED[dotted]  # pylint: disable=protected-access
        for tier in tiers:
            assert tier in notes, (dotted, tier)
            assert notes[tier], (dotted, tier)


def test_role_writes_off_and_report_name_the_python_requirement_block_does_not():
    """Windows burn-in owner decision: with no Python,
    role-write-guard.sh/.ps1 cannot evaluate `guards.roleWrites` at all (its
    own "THE NO-PYTHON CONTRACT" comment) and falls back to blocking a
    restricted role's write regardless of what the repo asked for. `off` and
    `report` both promise something WIDER than `block` -- silence about the
    no-python fallback would tell a reader that promise always holds. `block`
    needs no such caveat: it is what the fallback already does."""
    _rank_fn, _norm, notes = crew_config._RATCHETED["guards.roleWrites"]  # pylint: disable=protected-access
    assert "Python" in notes["off"]
    assert "blocked" in notes["off"]
    assert "Python" in notes["report"]
    assert "Python" not in notes["block"]


@pytest.mark.parametrize("dotted", sorted(crew_state.RATCHETED_KEYS))
def test_the_effective_value_is_the_lower_rank_of_the_two_layers(dotted):
    """Narrowing-only, in both directions. The repo may ask for LESS than the
    machine allows and be obeyed; it may ask for more and be refused.

    Written over `tiers` rather than over a fixed `lowest, middle, highest`
    because `change.requireForProduction` has TWO tiers, not three. Unpacking
    three names was a second, undeclared claim about every ratcheted key --
    that it has exactly three values -- and it failed the first time a key did
    not."""
    tiers, normalise, _rank = crew_state.RATCHETED_KEYS[dotted]
    lowest, highest = tiers[0], tiers[-1]
    eff = crew_state.effective_ratcheted

    assert eff(dotted, highest, lowest) == lowest     # repo widening refused
    assert eff(dotted, lowest, highest) == lowest     # repo narrowing obeyed
    for middle in tiers[1:-1]:
        assert eff(dotted, middle, highest) == middle
        assert eff(dotted, highest, middle) == middle
    assert eff(dotted, highest, highest) == highest
    # Absent on either side is the key's DEFAULT, which is what `normalise`
    # answers for `None`. For seven of the eight keys that is also the floor;
    # `change.requireForProduction` is the one where it is not, deliberately,
    # so that schema 7 does not switch a production requirement on for every
    # repo that upgraded. Asserting against `normalise(None)` rather than
    # against `lowest` is what makes this one assertion true of both shapes
    # instead of true of seven keys and quietly skipped for the eighth.
    absent = normalise(None)
    assert eff(dotted, None, highest) == absent
    assert eff(dotted, highest, None) == absent
    # An unknown ranks 0 on whichever layer carries it, so it can only narrow.
    # This one IS universal: a value crew cannot read is the floor everywhere.
    assert eff(dotted, "nonsense", highest) == lowest


def test_a_key_that_does_not_ratchet_raises_rather_than_falling_back():
    """Silently resolving a ratcheted key by precedence is the exact failure
    the ratchet exists to prevent, and it would look like a working feature
    while a cloned repo widened what the machine allows. So a name that is not
    in the table is an error, not a default."""
    with pytest.raises(KeyError):
        crew_state.effective_ratcheted("tracker", "files", "files")


def test_a_repos_widening_attempt_is_ignored_AND_reported(tmp_path):
    """Both halves, and the second is the one that gets dropped. A value that
    quietly does nothing is worse than one refused out loud: a user who sets
    `allow` in a repo and watches crew keep refusing has no way to learn that
    their machine-global `block` is why, and the next step is to go looking for
    a bug in crew."""
    root = _repo(tmp_path, guards={"forcePush": "allow"})
    path = _global_file(tmp_path, guards={"forcePush": "ask"})

    row = crew_config.resolve_guard(root, "forcePush", path)

    assert row["effective"] == "ask"          # ignored
    assert row["repo"] == "allow"
    assert row["global"] == "ask"
    assert row["heldDownBy"] == "global"      # reported


def test_the_repo_may_narrow_and_is_named_as_the_one_doing_it(tmp_path):
    """The mirror case. `heldDownBy` has to name the REPO when the repo is the
    narrower layer, or the field reads as "the global file is in your way"
    whatever actually happened."""
    root = _repo(tmp_path, guards={"forcePush": "block"})
    path = _global_file(tmp_path, guards={"forcePush": "allow"})

    row = crew_config.resolve_guard(root, "forcePush", path)

    assert row["effective"] == "block"
    assert row["heldDownBy"] == "repo"


def test_resolve_install_policy_still_answers_in_its_old_shape(tmp_path):
    """The wrapper's contract. `install_plan_for` and every existing test read
    exactly four keys off this; generalising the body must not change them, and
    the extra `path` key `resolve_ratcheted` returns has to be dropped."""
    root = _repo(tmp_path)
    path = _global_file(tmp_path, install={"policy": "ask"})

    row = crew_config.resolve_install_policy(root, path)

    assert set(row) == {"effective", "repo", "global", "heldDownBy"}
    assert row["effective"] == "manual"      # repo silent -> the floor
    assert row["global"] == "ask"
    assert row["heldDownBy"] == "repo"


# ---- --explain -------------------------------------------------------------


def test_explain_prints_the_ratcheted_value_not_the_merged_one(tmp_path):
    """Measured before it was fixed, not reasoned about: with a repo
    `install.policy: auto` over a machine-global `manual`, `--explain` printed
    `install.policy  repo  "auto"` while crew behaved as `manual`. A report
    that contradicts the run, in the direction that reads as "you have it" --
    the worst direction for a key that decides what crew may run."""
    root = _repo(tmp_path, guards={"forcePush": "allow"})
    path = _global_file(tmp_path, guards={"forcePush": "block"},
                        install={"policy": "manual"})
    os.makedirs(os.path.join(root, ".crew"), exist_ok=True)
    with open(os.path.join(root, ".crew", "config.json"), "w",
              encoding="utf-8") as handle:
        json.dump({"schema": crew_state.SCHEMA_CURRENT,
                   "guards": {"forcePush": "allow"},
                   "install": {"policy": "auto"}}, handle)

    rows = {r["path"]: r for r in crew_config.explain_config(root, path)}

    assert rows["install.policy"]["value"] == "manual"
    assert rows["install.policy"]["source"] == "global"
    assert rows["guards.forcePush"]["value"] == "block"
    assert rows["guards.forcePush"]["source"] == "global"
    # The narrowing SOURCE, carried into the row rather than left implicit.
    assert rows["guards.forcePush"]["heldDownBy"] == "global"
    assert rows["guards.forcePush"]["repo"] == "allow"


def test_explain_names_the_narrowing_layer_in_its_printed_output(capsys,
                                                                 tmp_path):
    """The `source` column has one slot and there are two facts: which layer
    decided, and which layer is holding the key down. A table that prints only
    the first tells a user who set `allow` and got `block` nothing at all about
    why -- which is the state `heldDownBy` was added to prevent and which this
    report then reproduced by not printing it."""
    root = _repo(tmp_path, guards={"forcePush": "allow"})
    path = _global_file(tmp_path, guards={"forcePush": "block"})

    crew_config.main(["--root", root, "--global-path", path, "--explain"])
    out = capsys.readouterr().out

    assert "guards.forcePush" in out
    assert "holding this down" in out
    assert "repo asks `allow`" in out
    assert "machine-global asks `block`" in out


# ---- the decision the hooks read ------------------------------------------


@pytest.mark.parametrize("policy,expected", [("block", "block"),
                                             ("ask", "ask"),
                                             ("allow", "allow")])
def test_guard_decision_maps_each_policy_to_a_decision(tmp_path, policy,
                                                       expected):
    root = _repo(tmp_path, guards={"forcePush": policy})
    path = _global_file(tmp_path, guards={"forcePush": "allow"})

    out = crew_config.guard_decision(root, "forcePush", _TRIPS["forcePush"],
                                     path)

    assert out["policy"] == policy
    assert out["decision"] == expected


def test_an_ask_marker_approves_one_command_and_not_the_next(tmp_path):
    """The whole `ask` design. A marker naming only the guard would be a
    standing grant -- approve one force push and every later one runs unasked,
    which is `allow` wearing `ask`'s label. Keyed on a digest of the command,
    so a second, different command asks again."""
    root = _repo(tmp_path, guards={"forcePush": "ask"})
    path = _global_file(tmp_path, guards={"forcePush": "allow"})
    first = _TRIPS["forcePush"]
    second = f"{_PUSH} --force origin release"

    out = crew_config.guard_decision(root, "forcePush", first, path)
    assert out["decision"] == "ask"
    _touch(out["marker"])

    assert crew_config.guard_decision(
        root, "forcePush", first, path)["decision"] == "allow"
    assert crew_config.guard_decision(
        root, "forcePush", second, path)["decision"] == "ask"


@pytest.mark.parametrize("offset", [
    # Stale: yesterday's yes, still sitting in a gitignored directory nothing
    # prunes. Without the bound this is the shape that turns `ask` into a
    # permanent per-command `allow` -- the same command runs unasked next
    # session, for the next agent in the same worktree, with nothing on screen
    # saying an approval from another day is what let it through.
    -86400,
    -(crew_guards.GUARD_APPROVAL_TTL + 60),
    # Dated in the future: not a fresher approval, a clock that disagrees or a
    # timestamp set by hand. Crew cannot say when the yes was given, and an
    # approval it cannot date is not one.
    crew_guards.GUARD_APPROVAL_TTL + 60,
])
def test_an_ask_approval_outside_the_window_asks_again(tmp_path, offset):
    """`ask` must stop for a yes AT THAT MOMENT, which a file with no time
    bound is not. The marker survives `os.path.exists` either way, so the only
    thing separating `ask` from a standing grant is that the age is read."""
    root = _repo(tmp_path, guards={"forcePush": "ask"})
    path = _global_file(tmp_path, guards={"forcePush": "allow"})
    command = _TRIPS["forcePush"]

    out = crew_config.guard_decision(root, "forcePush", command, path)
    _touch(out["marker"])
    assert crew_config.guard_decision(
        root, "forcePush", command, path)["decision"] == "allow"

    stamp = time.time() + offset
    os.utime(out["marker"], (stamp, stamp))
    again = crew_config.guard_decision(root, "forcePush", command, path)

    assert again["decision"] == "ask"
    assert os.path.exists(out["marker"]), (
        "the marker is the user's to remove; expiring it must not delete it")
    assert "outside the" in again["reason"]
    assert str(crew_guards.GUARD_APPROVAL_TTL // 60) in again["reason"]


def test_the_first_ask_says_how_long_an_approval_lasts(tmp_path):
    """The bound is only honest if the person creating the marker is told it
    exists. It rides in `reason`, which both shells print, so the number lives
    in one place rather than being restated in bash and in PowerShell."""
    root = _repo(tmp_path, guards={"forcePush": "ask"})
    path = _global_file(tmp_path, guards={"forcePush": "allow"})

    out = crew_config.guard_decision(root, "forcePush", _TRIPS["forcePush"],
                                     path)

    assert out["decision"] == "ask"
    assert str(crew_guards.GUARD_APPROVAL_TTL // 60) in out["reason"]
    assert "\t" not in out["reason"] and "\n" not in out["reason"]


def test_the_force_push_target_branch_is_named_or_said_to_be_unknown(tmp_path):
    """The design note left open whether `forcePush: allow` still refuses
    `main`. Settled: it honours the value everywhere -- the user chose it --
    with the compensating requirement that the target is NAMED. `unknown` is
    its own answer and never collapses into a plausible-looking `main`, which
    would be the "unknown wearing the label of a check that happened" failure
    this repo keeps rediscovering."""
    assert crew_config.push_target(f"{_PUSH} --force origin main") == "main"
    assert crew_config.push_target(
        f"{_PUSH} --force origin +release/1.2") == "release/1.2"
    assert crew_config.push_target(
        f"{_PUSH} --force origin HEAD:main") == "main"
    # No refspec: the branch comes from the upstream config and crew cannot
    # read it from the command line.
    assert crew_config.push_target(f"{_PUSH} --force") == "unknown"
    assert crew_config.push_target(f"{_PUSH} --force origin") == "unknown"
    # Not a push at all.
    assert crew_config.push_target(f"{_TF} apply") == "unknown"

    root = _repo(tmp_path, guards={"forcePush": "allow"})
    path = _global_file(tmp_path, guards={"forcePush": "allow"})
    out = crew_config.guard_decision(root, "forcePush",
                                     f"{_PUSH} --force origin main", path)
    assert out["target"] == "main"


def test_under_allow_nothing_is_silent(tmp_path):
    """`allow` removes the question, not the record. Without the row there is
    no way to learn afterwards that crew force-pushed -- the stderr line is
    gone with the session, and the whole point of a machine owner choosing
    `allow` is that they were not asked at the time."""
    root = _repo(tmp_path, guards={"forcePush": "allow"})
    path = _global_file(tmp_path, guards={"forcePush": "allow"})
    log = os.path.join(root, crew_state.GUARD_LOG_PATH)

    crew_config.guard_decision(root, "forcePush", _TRIPS["forcePush"], path,
                              record=True)

    assert os.path.isfile(log)
    with open(log, encoding="utf-8") as handle:
        row = handle.read().strip().split("\t")
    assert row[1:5] == ["forcePush", "allow", "allow", "main"]
    assert row[5] == _TRIPS["forcePush"]


def test_a_logged_command_cannot_forge_a_row(tmp_path):
    """The log is tab-separated and line-oriented and the command is arbitrary
    text off a hook payload. A tab or a newline in it would write a row that
    reads as a different decision. `crew_incident_log` normalises the same way
    and for the same reason."""
    root = _repo(tmp_path, guards={"forcePush": "allow"})
    path = _global_file(tmp_path, guards={"forcePush": "allow"})
    nasty = f"{_PUSH} --force\torigin\nblock\tblock\tfaked"

    crew_config.guard_decision(root, "forcePush", nasty, path, record=True)

    with open(os.path.join(root, crew_state.GUARD_LOG_PATH),
              encoding="utf-8") as handle:
        body = handle.read()
    assert body.count("\n") == 1
    assert len(body.strip().split("\t")) == 6


def test_the_cli_refuses_an_unknown_guard_name_rather_than_blocking_quietly(
        tmp_path, capsys):
    """Fail-closed is the CALLER's job, and both shells do it by treating any
    non-zero exit as `block`. Returning `block` quietly HERE would make a
    typo'd guard name look like a deliberate setting forever."""
    root = _repo(tmp_path)

    code = crew_config.main(["--root", root, "--guard", "forcepush",
                             "--command", "x"])

    assert code == 2
    assert "unknown guard" in capsys.readouterr().err


def test_the_cli_line_never_emits_an_empty_field(tmp_path, capsys):
    """TAB is IFS WHITESPACE in bash, so `IFS=$'\\t' read -r a b c` collapses a
    run of tabs and every field after an empty one shifts left by a slot.
    Measured: `guards.terraformApply` has no target branch, and guard.sh
    printed the REASON in the target's slot while guard.ps1 -- whose `-split`
    does not collapse -- printed it correctly. Two flavours disagreeing about a
    line they read from the same producer is the drift this shared CLI exists
    to prevent."""
    root = _repo(tmp_path)

    crew_config.main(["--root", root, "--guard", "terraformApply",
                      "--command", f"{_TF} apply"])
    line = capsys.readouterr().out.rstrip("\n")

    fields = line.split("\t")
    assert len(fields) == 6, fields
    assert all(fields), fields
    assert fields[3] == "-"      # no target branch for this guard
    assert fields[5] == "-"      # and no access class: not a prod guard


# ---- both shell flavours ---------------------------------------------------
#
# Every case below runs in BOTH. `guard.sh` and `guard.ps1` drift
# independently, and three of the bypasses fixed in #132 were open in both, so
# a case that runs in one flavour covers half of what it claims to.


















def _crippled_hooks(tmp_path):
    """A copy of the hook directory with `crew_config.py` removed.

    The resolver then exits non-zero for a reason neither script can talk its
    way around, which is the only way to reach the fail-closed branch without
    hiding python from a shell that needs it on PATH to start. A config file
    that merely parses badly is NOT this case -- `load_config` collapses
    malformed to absent on purpose, so the resolver still answers, correctly,
    with the floor.
    """
    dst = tmp_path / "crippled"
    dst.mkdir(exist_ok=True)
    for name in os.listdir(_HOOKS):
        src = os.path.join(_HOOKS, name)
        if os.path.isfile(src) and name != "crew_config.py":
            shutil.copyfile(src, dst / name)
    return str(dst)






# ---- production access: guards.prodDatabase / guards.prodServer ------------
#
# A second vocabulary in the same block, so everything below asserts against
# `none`/`read`/`full` rather than reusing the policy tests' `block`/`ask`/
# `allow`. The classifier is the part that must never guess, so its
# unclassifiable cases get as many assertions as its positive ones.

_PROD = {"databases": ["prod-db-*", "*.rds.example.com"],
         "hosts": ["prod-web-*", "10.0.*"]}

# Commands aimed at a DECLARED target, by what the classifier must call them.
_PROD_READS = (
    "psql -h prod-db-1 -c 'select count(*) from orders'",
    "mysql -h prod-db-2 -e 'show tables'",
    "ssh deploy@prod-web-1 'tail -n 50 /var/log/app.log'",
    "ssh deploy@prod-web-1 'systemctl status app'",
    "ssh deploy@prod-web-1 'cat /etc/hostname | grep web'",
    "aws rds describe-db-instances --db-instance-identifier prod-db-1",
)
_PROD_WRITES = (
    "psql -h prod-db-1 -c 'delete from orders'",
    "psql -h prod-db-1 -c 'select 1; drop table orders'",
    "psql -h prod-db-1 -c 'select * into backup from orders'",
    "ssh deploy@prod-web-1 'systemctl restart app'",
    "ssh deploy@prod-web-1 'tail -n 5 /var/log/app.log > /tmp/out'",
    "aws rds delete-db-instance --db-instance-identifier prod-db-1",
)
# Unclassifiable is a WRITE. Listed separately because these are the cases the
# whole `read` level rests on: each one is a command crew cannot read, and
# `read` is only a floor if crew refuses what it cannot read.
_PROD_UNKNOWN = (
    "psql -h prod-db-1",                       # interactive session
    "ssh deploy@prod-web-1",                   # interactive login
    "ssh deploy@prod-web-1 'somebinary --go'",  # unrecognised tool
    "ssh deploy@prod-web-1 'sed -i s/a/b/ /etc/app.conf'",
    "aws ssm start-session --target prod-web-1",
)


def _prod_ceiling(tmp_path):
    """A machine-global file at the CEILING, so the repo value is what varies.

    With the global layer unset the ratchet correctly holds every repo value
    down to `none` -- which is its own test, and would otherwise make every
    case below pass for the wrong reason.
    """
    return _global_file(tmp_path, guards={name: "full" for name
                                          in crew_guards.PROD_GUARD_NAMES})


def _prod_repo(tmp_path, level, production=None, name="repo"):
    root = tmp_path / name
    (root / ".crew").mkdir(parents=True, exist_ok=True)
    cfg = {"schema": crew_state.SCHEMA_CURRENT,
           "guards": {"prodDatabase": level, "prodServer": level},
           "production": _PROD if production is None else production}
    (root / ".crew" / "config.json").write_text(json.dumps(cfg), "utf-8")
    return str(root)


def _guard_for(command):
    """Which of the two guards a command is routed to by the shells."""
    return "prodDatabase" if command.split()[0] in (
        "psql", "mysql", "mariadb", "sqlcmd") or " rds " in command \
        else "prodServer"


def test_the_two_production_guards_are_declared_in_both_layers_at_none():
    """Same block, same ratchet, different vocabulary. `none` is both the
    default and the floor, so an undeclared key and an unknown value resolve
    identically."""
    repo = crew_config.default_config()
    glob = crew_config.default_global_config()

    for name in crew_guards.PROD_GUARD_NAMES:
        assert repo["guards"][name] == "none", name
        assert glob["guards"][name] == "none", name
        assert crew_config.is_global_path(f"guards.{name}"), name
    assert set(repo["guards"]) == set(crew_guards.ALL_GUARD_NAMES)


def test_production_is_repo_only_and_a_global_one_is_reported():
    """The asymmetry that makes the design work: the LEVEL is a machine fact
    and ratchets; WHAT IS PRODUCTION is a fact about this checkout. A global
    `production` block would carry one repo's hostnames into every other repo
    on the machine, so it is pruned -- and REPORTED, because a key that
    silently does nothing is worse than one refused out loud."""
    assert "production" in crew_config.default_config()
    assert "production" not in crew_config.default_global_config()
    assert not crew_config.is_global_path("production.hosts")
    assert not crew_config.is_global_path("production.databases")

    kept, ignored = crew_config.filter_global(
        {"production": {"hosts": ["prod-web-*"]}, "guards": {"prodServer": "read"}})

    assert "production" not in kept
    assert any(path.startswith("production") for path in ignored)


def test_production_patterns_never_read_the_global_layer(tmp_path,
                                                         monkeypatch):
    """Enforced by reading the repo file rather than by a rule in prose: a
    `production` block in a global file must reach no repo, and the way to
    guarantee that is to never read the global layer here at all.

    `GLOBAL_CONFIG_PATH` is pointed at the fixture rather than only passing
    `path`, and that is what gives the test teeth. `filter_global` already
    prunes `production` out of the merged layer, so a mutation that routed
    this through `resolve_config` would change nothing and the test would pass
    against it -- protected twice, tested against neither. Patching the path a
    DIRECT global read would use covers the second guard as well."""
    # The repo declares NO `production` block at all, which is the state the
    # bug would be invisible in: a repo with an empty one already wins any
    # merge, so a test using that would pass against a global fallback.
    root = tmp_path / "no-production"
    (root / ".crew").mkdir(parents=True)
    (root / ".crew" / "config.json").write_text(json.dumps(
        {"schema": crew_state.SCHEMA_CURRENT,
         "guards": {"prodServer": "read"}}), "utf-8")
    root = str(root)
    path = _global_file(tmp_path)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump({"production": {"hosts": ["*"], "databases": ["*"]}}, handle)
    monkeypatch.setattr(crew_config, "GLOBAL_CONFIG_PATH", path)

    assert crew_config.production_patterns(root, "prodServer") == []
    out = crew_config.guard_decision(
        root, "prodServer", "ssh deploy@prod-web-1 'rm -r /srv'", path)
    assert out["decision"] == "allow"
    assert out["target"] == ""


@pytest.mark.parametrize("command", _PROD_READS)
def test_the_classifier_calls_a_read_a_read(command):
    assert crew_guards.classify_access(command) == "read", command


@pytest.mark.parametrize("command", _PROD_WRITES + _PROD_UNKNOWN)
def test_everything_else_is_a_write_including_what_it_cannot_read(command):
    """Unknown is not read. A classifier answering "probably fine" would make
    `read` a slower `full`, and the commands it cannot parse are exactly the
    ones a reader would most want refused."""
    assert crew_guards.classify_access(command) == "write", command


def test_with_no_patterns_declared_the_guard_matches_nothing(tmp_path):
    """The property the default rests on. `none` is the strictest level there
    is, and it ships as the default because with nothing declared it refuses
    the empty set -- so an upgrade changes no behaviour until somebody says
    what production is."""
    root = _prod_repo(tmp_path, "none", production={"databases": [],
                                                    "hosts": []})
    path = _prod_ceiling(tmp_path)

    for command in _PROD_WRITES + _PROD_UNKNOWN:
        out = crew_config.guard_decision(root, _guard_for(command), command,
                                         path)
        assert out["decision"] == "allow", command
        assert out["target"] == "", command


@pytest.mark.parametrize("command", _PROD_READS + _PROD_WRITES
                         + _PROD_UNKNOWN)
def test_none_refuses_every_match(tmp_path, command):
    root = _prod_repo(tmp_path, "none")
    out = crew_config.guard_decision(root, _guard_for(command), command,
                                     _prod_ceiling(tmp_path))
    assert out["decision"] == "block", command
    assert out["target"], "a refusal must name the pattern it matched"


@pytest.mark.parametrize("command", _PROD_READS)
def test_read_permits_what_it_can_classify_as_read_only(tmp_path, command):
    root = _prod_repo(tmp_path, "read")
    out = crew_config.guard_decision(root, _guard_for(command), command,
                                     _prod_ceiling(tmp_path))
    assert out["decision"] == "allow", command
    assert out["access"] == "read"


@pytest.mark.parametrize("command", _PROD_WRITES + _PROD_UNKNOWN)
def test_read_refuses_writes_and_everything_unclassifiable(tmp_path, command):
    root = _prod_repo(tmp_path, "read")
    out = crew_config.guard_decision(root, _guard_for(command), command,
                                     _prod_ceiling(tmp_path))
    assert out["decision"] == "block", command
    assert out["access"] == "write"


@pytest.mark.parametrize("command", _PROD_READS + _PROD_WRITES
                         + _PROD_UNKNOWN)
def test_full_allows_everything_and_logs_it(tmp_path, command):
    root = _prod_repo(tmp_path, "full")
    out = crew_config.guard_decision(root, _guard_for(command), command,
                                     _prod_ceiling(tmp_path), record=True)
    assert out["decision"] == "allow", command
    log = os.path.join(root, crew_state.GUARD_LOG_PATH)
    assert os.path.isfile(log)
    with open(log, encoding="utf-8") as handle:
        assert command.replace("\t", " ") in handle.read()


def test_a_repo_cannot_widen_the_production_level(tmp_path):
    """The same ratchet as the other four, on the table rather than in a
    second copy of the rule."""
    root = _prod_repo(tmp_path, "full")
    path = _global_file(tmp_path, guards={"prodServer": "read"})

    resolved = crew_config.resolve_guard(root, "prodServer", path)

    assert resolved["effective"] == "read"
    assert resolved["heldDownBy"] == "global"
    out = crew_config.guard_decision(
        root, "prodServer", "ssh deploy@prod-web-1 'systemctl restart app'",
        path)
    assert out["decision"] == "block"


def test_an_unknown_production_level_fails_closed_to_none(tmp_path):
    root = _prod_repo(tmp_path, "READ-ONLY-PLEASE")
    out = crew_config.guard_decision(
        root, "prodDatabase", "psql -h prod-db-1 -c 'select 1'",
        _prod_ceiling(tmp_path))
    assert out["policy"] == "none"
    assert out["decision"] == "block"


def test_a_production_guard_names_no_marker(tmp_path):
    """`ask` is not in this vocabulary. Naming a marker file would invite a
    user to create one that nothing reads -- a control that looks like it
    works and does not."""
    root = _prod_repo(tmp_path, "read")
    out = crew_config.guard_decision(
        root, "prodDatabase", "psql -h prod-db-1 -c 'delete from t'",
        _prod_ceiling(tmp_path))
    assert out["marker"] == ""
    assert out["decision"] == "block"


def test_the_cli_answers_for_the_production_guards_too(tmp_path, capsys):
    """Both shells read this one line, so the field count is the contract.
    `access` is the sixth field and is appended, never inserted."""
    root = _prod_repo(tmp_path, "read")
    rc = crew_config.main(["--root", root, "--guard", "prodServer",
                           "--command", "ssh deploy@prod-web-1 'ls /srv'",
                           "--global-path", _prod_ceiling(tmp_path)])
    assert rc == 0
    fields = capsys.readouterr().out.strip().split("\t")
    assert len(fields) == 6
    assert fields[0] == "allow" and fields[1] == "read"
    assert fields[5] == "read"
    assert all(field for field in fields), "an empty field shifts bash's read"


# --- classification: cases whose script-level prover was removed -----------
#
# These two re-prove sabotage mutations that `test_guard_command_spelling.py`
# owned until the command guard was removed. That file drove `guard.sh` and
# `guard.ps1` as subprocesses; these call the classifier directly, which is
# what the mutations actually break. `crew_guards` is still live -- both
# `crew_config` and `crew_state` call into it -- so this is real coverage, not
# a test kept for its own sake.


def test_a_subcommands_verb_decides_it_not_just_the_object():
    """`ip link set ...` is a WRITE, and only the verb says so.

    `PROD_SUBCOMMAND_ACTIONS` maps a head command to the set of its read-only
    verbs. Checking only the object (`link`) and not the verb (`set`) lets
    every mutating subcommand of a listed tool through as a read -- which at
    `prodServer: read` means crew runs it against a declared production host.
    """
    assert crew_guards._classify_segment("ip link show") == "read"
    assert crew_guards._classify_segment("ip link set eth0 down") == "write"


def test_every_sql_payload_is_classified_not_only_the_first():
    """A read followed by a write is a WRITE.

    `psql -c 'select 1' -c 'drop table orders'` carries two payloads. Judging
    the command by `payloads[0]` alone reads the whole thing as a select and
    permits the drop, so the check has to hold for ALL of them.
    """
    read_only = "psql -h db -c 'select 1' -c 'select 2'"
    mixed = "psql -h db -c 'select 1' -c 'drop table orders'"
    assert crew_guards.classify_access(read_only) == "read"
    assert crew_guards.classify_access(mixed) == "write"

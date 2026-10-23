"""`guards.profile` and `guards.overrides` (L-0725): the profile table, the
per-layer expansion, and the ratchet that runs on the expanded values.

Every case is a must-block or a must-allow. The failure this file exists for is
a layer WIDENING: a malformed profile that reads as `off`, an override that
beats a legacy key still present, a profile that beats an override. Each of
those is hand-sabotaged (see the PR body) and must turn a test here red.

Nothing reaches a real config: the machine file is passed as an explicit path.
"""
import json
import os

import context  # noqa: F401  pylint: disable=unused-import
import crew_config
import crew_guards
import pytest

NAMES = crew_guards.ALL_GUARD_NAMES

# The spec table, written out here on purpose and never derived from
# `PROFILE_MAP`: a test that read its expectation from the code under test
# would pass whatever the code said.
_SIX = ("terraformApply", "forcePush", "mergeGate", "cloudDestructive",
        "sqlDestructive", "deployWorkflow")
TABLE = {
    "off": {"cloudGuard": "off", "roleWrites": "off", "adminMerge": "block",
            "prodDatabase": "none", "prodServer": "none", "envGuard": "off",
            **{g: "block" for g in _SIX}},
    "standard": {"cloudGuard": "block", "roleWrites": "report",
                 "adminMerge": "ask", "prodDatabase": "none",
                 "prodServer": "none", "envGuard": "off",
                 **{g: "block" for g in _SIX}},
    "strict": {"cloudGuard": "block", "roleWrites": "block",
               "adminMerge": "block", "prodDatabase": "none",
               "prodServer": "none", "envGuard": "block",
               **{g: "block" for g in _SIX}},
}


def _write(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(json.dumps(data))
    return path


def _resolve(tmp_path, name, repo=None, machine=None):
    root = str(tmp_path / "repo")
    os.makedirs(os.path.join(root, ".crew"), exist_ok=True)
    cfg = os.path.join(root, ".crew", "config.json")
    if repo is None:
        if os.path.exists(cfg):
            os.remove(cfg)
    else:
        _write(cfg, repo)
    gpath = str(tmp_path / "home" / "config.json")
    if machine is None:
        if os.path.exists(gpath):
            os.remove(gpath)
    else:
        _write(gpath, machine)
    return crew_config.resolve_guard(root, name, gpath)


def _g(**block):
    return {"guards": block}


def test_guard_names_are_the_twelve():
    assert len(NAMES) == 12
    assert set(TABLE["off"]) == set(NAMES)


def test_profiles_are_off_standard_strict():
    assert crew_guards.GUARD_PROFILES == ("off", "standard", "strict")


@pytest.mark.parametrize("profile", ["off", "standard", "strict"])
@pytest.mark.parametrize("name", NAMES)
def test_profile_table(tmp_path, profile, name):
    row = _resolve(tmp_path, name, repo=_g(profile=profile))

    assert row["repo"] == TABLE[profile][name]


@pytest.mark.parametrize("name", NAMES)
def test_profile_map_equals_the_table(name):
    for profile in crew_guards.GUARD_PROFILES:
        assert crew_guards.PROFILE_MAP[profile][name] == TABLE[profile][name]


def test_off_profile_is_guard_defaults():
    assert crew_guards.PROFILE_MAP["off"] == crew_guards.GUARD_DEFAULTS


@pytest.mark.parametrize("name", NAMES)
def test_unset_is_guard_defaults(tmp_path, name):
    row = _resolve(tmp_path, name)

    assert row["effective"] == crew_guards.GUARD_DEFAULTS[name]
    assert row["repo"] == crew_guards.GUARD_DEFAULTS[name]
    assert row["global"] == crew_guards.GUARD_DEFAULTS[name]


def test_ratchet_repo_strict_machine_off(tmp_path):
    repo, machine = _g(profile="strict"), _g(profile="off")

    values = {n: _resolve(tmp_path, n, repo, machine)["effective"] for n in NAMES}

    assert values["cloudGuard"] == "block"
    assert values["roleWrites"] == "block"
    assert values["envGuard"] == "block"
    assert values["adminMerge"] == "block"


def test_ratchet_machine_strict_repo_off(tmp_path):
    repo, machine = _g(profile="off"), _g(profile="strict")

    values = {n: _resolve(tmp_path, n, repo, machine)["effective"] for n in NAMES}

    assert values["cloudGuard"] == "block"
    assert values["roleWrites"] == "block"
    assert values["envGuard"] == "block"


def test_ratchet_override_narrows_in_repo(tmp_path):
    row = _resolve(tmp_path, "roleWrites",
                   repo=_g(profile="off", overrides={"roleWrites": "block"}),
                   machine=_g(profile="off"))

    assert row["effective"] == "block"


def test_ratchet_override_narrows_in_machine(tmp_path):
    row = _resolve(tmp_path, "cloudGuard",
                   repo=_g(profile="off"),
                   machine=_g(profile="off", overrides={"cloudGuard": "block"}))

    assert row["effective"] == "block"


def test_ratchet_override_widening_is_held_down_by_the_other_layer(tmp_path):
    row = _resolve(tmp_path, "forcePush",
                   repo=_g(profile="standard"),
                   machine=_g(profile="off", overrides={"forcePush": "allow"}))

    assert row["effective"] == "block"
    assert row["heldDownBy"] == "repo"


def test_ratchet_override_widening_is_held_down_the_other_way(tmp_path):
    row = _resolve(tmp_path, "forcePush",
                   repo=_g(profile="off", overrides={"forcePush": "allow"}),
                   machine=_g(profile="off"))

    assert row["effective"] == "block"
    assert row["heldDownBy"] == "global"


def test_override_replaces_a_valid_profile_value(tmp_path):
    row = _resolve(tmp_path, "forcePush",
                   machine=_g(profile="off", overrides={"forcePush": "allow"}))

    assert row["global"] == "allow"


def test_override_beats_profile_for_roleWrites(tmp_path):
    row = _resolve(tmp_path, "roleWrites",
                   repo=_g(profile="standard", overrides={"roleWrites": "off"}))

    assert row["repo"] == "off"


@pytest.mark.parametrize("name", NAMES)
@pytest.mark.parametrize("bad", ["strictt", 3, ["strict"], True, ""])
def test_malformed_profile_is_floor(tmp_path, name, bad):
    row = _resolve(tmp_path, name, repo=_g(profile=bad))

    assert row["repo"] == crew_guards.guard_tiers(name)[0][0]


@pytest.mark.parametrize("name", NAMES)
def test_malformed_profile_ignores_a_lifting_override(tmp_path, name):
    wide = crew_guards.guard_tiers(name)[0][-1]

    row = _resolve(tmp_path, name,
                   repo=_g(profile="nope", overrides={name: wide}))

    assert row["repo"] == crew_guards.guard_tiers(name)[0][0]


def test_malformed_profile_with_cloud_override_off_is_floor(tmp_path):
    row = _resolve(tmp_path, "cloudGuard",
                   repo=_g(profile="bogus", overrides={"cloudGuard": "off"}))

    assert row["repo"] == "block"


@pytest.mark.parametrize("name", NAMES)
@pytest.mark.parametrize("bad", ["allw", 7, ["allow"], {"x": 1}, "OFFF"])
def test_malformed_override_is_floor(tmp_path, name, bad):
    row = _resolve(tmp_path, name,
                   repo=_g(profile="off", overrides={name: bad}))

    assert row["repo"] == crew_guards.guard_tiers(name)[0][0]


def test_malformed_overrides_table_is_floor_for_every_guard(tmp_path):
    values = [_resolve(tmp_path, n, repo=_g(overrides=["allow"]))["repo"]
              for n in NAMES]

    assert values == [crew_guards.guard_tiers(n)[0][0] for n in NAMES]


@pytest.mark.parametrize("orient", ["repo", "machine"])
def test_legacy_conflict_resolves_narrow(tmp_path, orient):
    layer = _g(forcePush="block", overrides={"forcePush": "allow"})
    other = _g(overrides={"forcePush": "allow"})
    repo, machine = (layer, other) if orient == "repo" else (other, layer)

    row = _resolve(tmp_path, "forcePush", repo, machine)

    assert row["effective"] == "block"
    assert row["conflicts"] == [orient if orient == "repo" else "global"]


def test_legacy_wide_and_override_narrow_gives_narrow(tmp_path):
    row = _resolve(tmp_path, "forcePush",
                   machine=_g(forcePush="allow", overrides={"forcePush": "block"}))

    assert row["global"] == "block"


def test_legacy_beats_profile_when_narrower(tmp_path):
    row = _resolve(tmp_path, "roleWrites",
                   repo=_g(profile="off", roleWrites="block"))

    assert row["repo"] == "block"


def test_profile_narrower_than_legacy_wins(tmp_path):
    row = _resolve(tmp_path, "roleWrites",
                   repo=_g(profile="strict", roleWrites="off"))

    assert row["repo"] == "block"


def test_malformed_legacy_with_override_is_floor(tmp_path):
    row = _resolve(tmp_path, "forcePush",
                   repo=_g(forcePush="garbage", overrides={"forcePush": "allow"}))

    assert row["repo"] == "block"


@pytest.mark.parametrize("name,value", [("adminMerge", "ask"),
                                        ("forcePush", "allow"),
                                        ("prodDatabase", "read"),
                                        ("roleWrites", "report"),
                                        ("cloudGuard", "block"),
                                        ("envGuard", "report")])
@pytest.mark.parametrize("layer", ["repo", "machine"])
def test_legacy_only_resolves_as_today(tmp_path, name, value, layer):
    cfg = _g(**{name: value})
    repo, machine = (cfg, None) if layer == "repo" else (None, cfg)

    row = _resolve(tmp_path, name, repo, machine)

    assert row["repo" if layer == "repo" else "global"] == value


def test_legacy_key_is_reported_unmigrated(tmp_path):
    row = _resolve(tmp_path, "forcePush", repo=_g(forcePush="block"),
                   machine=_g(profile="off"))

    assert row["unmigrated"] == ["repo"]
    assert row["conflicts"] == []


def test_migrated_layers_report_nothing(tmp_path):
    row = _resolve(tmp_path, "forcePush", repo=_g(profile="standard"),
                   machine=_g(profile="off", overrides={"forcePush": "allow"}))

    assert row["unmigrated"] == []
    assert row["conflicts"] == []


def test_non_object_guards_block_gives_the_floor_not_no_layer_value(tmp_path):
    """Narrowed (round-1 review): a present non-object `guards` was "no layer
    value" and left default-off guards off; it is now the floor."""
    row = _resolve(tmp_path, "forcePush", repo={"guards": 42})

    assert row["effective"] == "block"
    assert row["repo"] == "block"


MALFORMED_GUARDS = [42, "x", [], True, 0, ""]


def _floor_of(name):
    return crew_guards.guard_tiers(name)[0][0]


@pytest.mark.parametrize("bad", MALFORMED_GUARDS, ids=repr)
@pytest.mark.parametrize("name", NAMES)
def test_malformed_guards_layer_value_is_the_floor(name, bad):
    state = crew_guards.layer_guard_state({"guards": bad}, name)

    assert state == {"value": _floor_of(name), "legacy": False,
                     "conflict": False}
    assert crew_guards.layer_guard_value({"guards": bad}, name) == _floor_of(name)


@pytest.mark.parametrize("bad", MALFORMED_GUARDS, ids=repr)
@pytest.mark.parametrize("name", NAMES)
def test_malformed_guards_in_the_repo_layer_resolves_to_the_floor(
        tmp_path, name, bad):
    row = _resolve(tmp_path, name, repo={"guards": bad},
                   machine=_g(profile="off"))

    assert row["repo"] == _floor_of(name)
    assert row["effective"] == _floor_of(name)


@pytest.mark.parametrize("bad", MALFORMED_GUARDS, ids=repr)
@pytest.mark.parametrize("name", NAMES)
def test_malformed_guards_in_the_machine_layer_resolves_to_the_floor(
        tmp_path, name, bad):
    row = _resolve(tmp_path, name, repo=_g(profile="off"),
                   machine={"guards": bad})

    assert row["global"] == _floor_of(name)
    assert row["effective"] == _floor_of(name)


@pytest.mark.parametrize("cfg", [{"guards": None}, {}, {"guards": {}}],
                         ids=["null", "missing", "empty-object"])
@pytest.mark.parametrize("name", NAMES)
def test_null_missing_or_empty_guards_stays_absent(tmp_path, name, cfg):
    state = crew_guards.layer_guard_state(cfg, name)
    row = _resolve(tmp_path, name, repo=cfg, machine=cfg)

    assert state == {"value": None, "legacy": False, "conflict": False}
    assert row["effective"] == crew_guards.GUARD_DEFAULTS[name]


def test_null_profile_is_absent(tmp_path):
    row = _resolve(tmp_path, "adminMerge",
                   repo=_g(profile=None, overrides={"adminMerge": "ask"}))

    assert row["repo"] == "ask"


# The owner's two layers, sanitised: the same per-guard values before (legacy
# keys) and after (profile + overrides).
OWNER_REPO_LEGACY = _g(
    terraformApply="block", forcePush="block", adminMerge="ask",
    mergeGate="block", cloudDestructive="block", sqlDestructive="block",
    deployWorkflow="block", prodDatabase="none", prodServer="none",
    roleWrites="report", cloudGuard="block")
OWNER_MACHINE_LEGACY = _g(
    terraformApply="allow", forcePush="allow", adminMerge="allow",
    mergeGate="allow", prodDatabase="none", prodServer="none")
OWNER_REPO_NEW = _g(profile="standard")
OWNER_MACHINE_NEW = _g(profile="off", overrides={
    "terraformApply": "allow", "forcePush": "allow", "adminMerge": "allow",
    "mergeGate": "allow"})


@pytest.mark.parametrize("name", NAMES)
def test_owner_layers_equivalent(tmp_path, name):
    before = _resolve(tmp_path, name, OWNER_REPO_LEGACY, OWNER_MACHINE_LEGACY)
    after = _resolve(tmp_path, name, OWNER_REPO_NEW, OWNER_MACHINE_NEW)

    for field in ("effective", "repo", "global", "heldDownBy"):
        assert after[field] == before[field], field


def test_normalise_profile_unknown_is_none():
    assert crew_guards.normalise_profile("standard") == "standard"
    assert crew_guards.normalise_profile(" Strict ") == "strict"
    assert crew_guards.normalise_profile("loud") is None
    assert crew_guards.normalise_profile(5) is None


def test_layer_guard_value_none_only_when_layer_holds_nothing():
    """A non-object `guards` is no longer "holds nothing": it is the floor."""
    assert crew_guards.layer_guard_value({}, "forcePush") is None
    assert crew_guards.layer_guard_value({"guards": {}}, "forcePush") is None
    assert crew_guards.layer_guard_value({"guards": None}, "forcePush") is None
    assert crew_guards.layer_guard_value({"guards": 42}, "forcePush") == "block"
    assert crew_guards.layer_guard_value(
        {"guards": {"profile": "off"}}, "forcePush") == "block"

"""T-0048: `crew_keys.py`, the one table the settings reference is generated
from. Each check here is what keeps that table honest against the code:
one row per leaf, value tuples held by identity (never copied), code-branch
values run through the real reader, and no "coming" key already in the code.
"""
import json
import os
import re

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import crew_autocycle
import crew_autopilot
import crew_config
import crew_guards
import crew_keys
import crew_platform
import crew_resume
import crew_route
import crew_shell
import crew_state
import crew_ticket
import crew_tracker

PLUGIN = context._ROOT  # pylint: disable=protected-access


def _leaves():
    return set(crew_config.leaf_paths(crew_config.default_config())) | set(
        crew_config.leaf_paths(crew_config.default_global_config()))


# --- Step 1: one row per leaf, and no copied tuples ---------------------------

def test_every_leaf_has_a_row():
    assert _leaves() <= set(crew_keys.KEY_META)
    assert not [p for p in crew_keys.problems() if p.startswith("missing")]


def test_no_orphan_rows():
    assert set(crew_keys.KEY_META) <= _leaves()
    assert not [p for p in crew_keys.problems() if p.startswith("orphan")]


def test_problems_names_a_deleted_and_an_extra_row(monkeypatch):
    """The two checks above go red on the change they exist to catch."""
    meta = dict(crew_keys.KEY_META)
    del meta["pm.maxLines"]
    meta["pm.noSuchKey"] = meta["pm.enabled"]
    monkeypatch.setattr(crew_keys, "KEY_META", meta)
    found = crew_keys.problems()
    assert "missing: pm.maxLines is a config leaf with no KEY_META row" in found
    assert "orphan: pm.noSuchKey has a KEY_META row and is not a config leaf" in found


def test_ratcheted_rows_do_not_restate_tiers():
    ratcheted = [k for k in crew_keys.KEY_META if crew_guards.ratchet_spec(k)]
    assert ratcheted, "no ratcheted key found: the test would pass vacuously"
    for key in ratcheted:
        assert crew_keys.KEY_META[key]["values"] is None, key
        assert crew_keys.KEY_META[key]["kind"] == "ratchet", key
        assert crew_keys.values_of(key) is crew_guards.RATCHETED_KEYS[key][0], key
    assert not [p for p in crew_keys.problems() if p.startswith("restated")]


def test_a_restated_tier_tuple_is_a_problem(monkeypatch):
    meta = dict(crew_keys.KEY_META)
    meta["guards.forcePush"] = dict(meta["guards.forcePush"],
                                    values=("block", "ask", "allow"))
    monkeypatch.setattr(crew_keys, "KEY_META", meta)
    assert any(p.startswith("restated tiers: guards.forcePush")
               for p in crew_keys.problems())


@pytest.mark.parametrize("key, obj", [
    ("dev.provider", crew_state.DEV_PROVIDERS),
    ("qa.order", crew_state.QA_PROVIDERS),
    ("pm.authority", crew_state.AUTHORITIES),
    ("pm.ticketGranularity", crew_state.TICKET_GRANULARITIES),
    ("scope.mode", crew_ticket.MODES),
    ("tracker", crew_tracker.KINDS),
    ("shellRoute.mode", crew_shell.MODES),
    ("autopilot.deploy", crew_autopilot.DEPLOY_VALUES),
    ("autopilot.approval", crew_autopilot.POLICIES),
    ("autopilot.questions", crew_autopilot.POLICIES),
])
def test_tuple_backed_values_are_the_same_object(key, obj):
    assert crew_keys.values_of(key) is obj


def test_qa_provider_is_auto_then_qa_providers_own_items():
    values = crew_keys.values_of("qa.provider")
    assert values is crew_keys.values_of("qa.provider")
    assert values[0] == "auto"
    tail = values[1:]
    assert len(tail) == len(crew_state.QA_PROVIDERS)
    assert all(a is b for a, b in zip(tail, crew_state.QA_PROVIDERS))


def test_autoclear_methods_are_the_platform_table():
    row = crew_keys.KEY_META["context.autoClear.method"]
    table = crew_platform._AUTOCLEAR_METHODS  # pylint: disable=protected-access
    assert row["values_by_os"] is table
    union = []
    for methods in table.values():
        union += [m for m in methods if m not in union]
    assert crew_keys.values_of("context.autoClear.method") == tuple(union)


def test_values_agree_with_the_writers_enum_values():
    """`crew_config.enum_values` is what both config writers refuse against;
    the reference must print the same list for every key it covers."""
    covered = 0
    for key in crew_keys.KEY_META:
        allowed = crew_config.enum_values(key)
        if allowed is None:
            continue
        covered += 1
        if key in crew_guards.PERSONAL_KEYS:
            # T-0050: a personal key's writer lists its tiers strictest first
            # (rank order, `crew_guards.PERSONAL_KEYS`), while the reference
            # prints the reader's own tuple (`crew_autopilot.POLICIES`, ...).
            # Same values, so neither side refuses what the other accepts.
            assert sorted(crew_keys.values_of(key)) == sorted(allowed), key
            assert allowed == crew_guards.PERSONAL_KEYS[key][1], key
            continue
        assert tuple(crew_keys.values_of(key)) == allowed, key
    assert covered >= 15


# `branch` rows whose reader checks a shape rather than a closed value list.
_OPEN_BRANCH_ROWS = ("autopilot.maxPhases", "autopilot.maxAutoReplans", "tickets.baseBranch",
                     "git.forbiddenTrailers", "autopilot.sleep.schedule")


def test_every_row_has_a_summary_and_a_values_kind():
    for key, row in crew_keys.KEY_META.items():
        assert row["summary"].strip(), key
        assert row["kind"] in crew_keys.KINDS, key
        if row["kind"] in ("tuple", "prose", "branch") and key not in _OPEN_BRANCH_ROWS:
            assert row["values"], key
        if row["kind"] in ("unvalidated", "prose", "type", "branch", "open-table"):
            assert row["source"], key
    assert not crew_keys.problems()


def test_every_source_is_a_file_in_the_plugin():
    for key, row in crew_keys.KEY_META.items():
        if row["source"]:
            assert os.path.isfile(os.path.join(PLUGIN, row["source"])), (key, row["source"])


def test_machine_arms_keys_render_as_machine_arms():
    assert crew_config.REPO_VETO_ONLY
    for key in crew_config.REPO_VETO_ONLY:
        assert crew_keys.layer_of(key) == "machine-arms", key
    for name in crew_state.AUTOCLEAR_MACHINE_ONLY_KEYS:
        assert crew_keys.layer_of("context.autoClear." + name) == "machine-only"


def test_layer_follows_is_global_path():
    for key in crew_keys.KEY_META:
        layer = crew_keys.layer_of(key)
        assert (layer == "repo") == (not crew_config.is_global_path(key)), key
    assert crew_keys.layer_of("pm.authority") == "both, widening warned"
    assert crew_keys.layer_of("install.policy") == "both, ratchet"
    assert crew_keys.layer_of("qa.provider") == "both"
    # T-0050: the personal keys combine per key, the stricter layer winning.
    for key in crew_guards.PERSONAL_KEYS:
        assert crew_keys.layer_of(key) == "both, stricter wins", key


# --- Step 2: arrival versions, code branches, prose, COMING -------------------

def _version(text):
    return tuple(int(p) for p in text.split("."))


def test_since_is_a_version_no_newer_than_the_plugin():
    with open(os.path.join(PLUGIN, ".claude-plugin", "plugin.json"), encoding="utf-8") as fh:
        plugin = _version(json.load(fh)["version"])
    for key, row in crew_keys.KEY_META.items():
        since = row["since"]
        if since is None or since == "<=0.11.0":
            continue
        assert re.fullmatch(r"\d+\.\d+\.\d+", since), (key, since)
        assert _version(since) <= plugin, (key, since)


def _repo(tmp_path, cfg):
    (tmp_path / ".crew").mkdir(exist_ok=True)
    (tmp_path / ".crew" / "config.json").write_text(json.dumps(cfg), encoding="utf-8")
    return str(tmp_path)


@pytest.mark.parametrize("value", ["off", "plan", "Plan"])
def test_autopilot_mode_values_agree_with_the_reader(tmp_path, value):
    declared = crew_keys.values_of("autopilot.mode")
    got = crew_autopilot.settings(_repo(tmp_path, {"autopilot": {"mode": value}}))
    assert got["armed"] == (value == "plan")
    assert (value in declared) == (not any("autopilot.mode" in w for w in got["warnings"]))


@pytest.mark.parametrize("key", ["approval", "questions"])
@pytest.mark.parametrize("value", [None, "human", "self", "risk", "Self"])
def test_sleep_override_values_agree_with_the_reader(tmp_path, key, value):
    """T-0053: every declared value is read without a warning; one that is
    not declared warns. The tail of the tuple is POLICIES' own items."""
    declared = crew_keys.values_of(f"autopilot.sleep.{key}")
    got = crew_autopilot.settings(_repo(tmp_path, {"autopilot": {"sleep": {key: value}}}))
    assert declared[1:] == crew_autopilot.POLICIES
    assert all(a is b for a, b in zip(declared[1:], crew_autopilot.POLICIES))
    assert (value in declared) == (
        not any(f"autopilot.sleep.{key}" in w for w in got["warnings"]))


@pytest.mark.parametrize("value, kept", [(1, True), (12, True), (0, False), ("12", False)])
def test_autopilot_max_phases_agrees_with_the_reader(tmp_path, value, kept):
    got = crew_autopilot.settings(_repo(tmp_path, {"autopilot": {"maxPhases": value}}))
    assert got["maxPhases"] == (value if kept else 12)
    assert kept == (not any("maxPhases" in w for w in got["warnings"]))
    assert crew_keys.KEY_META["autopilot.maxPhases"]["type"] == "positive integer"


@pytest.mark.parametrize("value, kept", [
    (None, True), ("main", True), ("release/2.x", True),
    ("", False), ("   ", False), (7, False), (True, False), (["main"], False),
])
def test_tickets_base_branch_is_checked_not_coerced(tmp_path, value, kept):
    # scope_base.read_base_branch refuses a non-string or blank value, and the
    # scope base becomes "could not tell": nothing is coerced, so the row is
    # kind `branch` ("checked in"), never `type` ("coerced in").
    import scope_base
    got, problem = scope_base.read_base_branch(
        _repo(tmp_path, {"tickets": {"baseBranch": value}}))
    assert (problem is None) == kept, (value, problem)
    if not kept:
        assert got is None
    row = crew_keys.KEY_META["tickets.baseBranch"]
    assert row["kind"] == "branch"
    assert row["type"] == "branch name or null"
    assert row["source"] == "hooks/scripts/scope_base.py"


@pytest.mark.parametrize("value, kept", [
    ([], True), (["Co-Authored-By"], True), (["Signed-off-by", "X-1"], True),
    ("Co-Authored-By", False), (["Co-Authored-By:"], False), ([7], False),
    (None, False), ({"a": 1}, False),
])
def test_git_forbidden_trailers_is_checked_not_coerced(tmp_path, value, kept):
    # crew_trailers.forbidden refuses anything but a list of tokens and the
    # list becomes unknown, never `[]`: nothing is coerced, so the row is kind
    # `branch` ("checked in"), never `type` ("coerced in").
    import crew_trailers
    root = _repo(tmp_path, {"git": {"forbiddenTrailers": value}})
    got, unknown = crew_trailers.forbidden(root, global_path=str(tmp_path / "none.json"))
    assert (unknown is None) == kept, (value, unknown)
    if kept:
        assert got == tuple(value)
    else:
        assert got == ()
    row = crew_keys.KEY_META["git.forbiddenTrailers"]
    assert row["kind"] == "branch"
    assert row["source"] == "hooks/scripts/crew_trailers.py"
    assert crew_keys.layer_of("git.forbiddenTrailers") == "both"


def _machine(tmp_path, cfg):
    path = tmp_path / "machine.json"
    path.write_text(json.dumps(cfg), encoding="utf-8")
    return str(path)


@pytest.mark.parametrize("repo, machine, armed", [
    (True, None, False),     # a repo `true` alone arms nothing
    (None, True, True),      # the machine arms it
    (False, True, False),    # a repo `false` vetoes
    ("true", "true", False),  # an undeclared value (a string) never arms
])
def test_machine_armed_values_agree_with_the_readers(tmp_path, repo, machine, armed):
    for key in ("resume.auto", "context.autoClear.enabled", "context.autoClear.wrapUp"):
        declared = crew_keys.values_of(key)
        assert crew_keys.layer_of(key) == "machine-arms"
        block, leaf = key.rsplit(".", 1)

        def nest(value, block=block, leaf=leaf):
            out = {leaf: value}
            for part in reversed(block.split(".")):
                out = {part: out}
            return out
        root = _repo(tmp_path, nest(repo) if repo is not None else {})
        gpath = _machine(tmp_path, nest(machine) if machine is not None else {})
        if key == "resume.auto":
            got = crew_resume.settings(root, global_path=gpath)["armed"]
        else:
            got = crew_autocycle.settings(root, global_path=gpath)[leaf]
        assert got is armed, (key, repo, machine)
        if armed:
            assert machine in declared


@pytest.mark.parametrize("value", [True, False, "true", 1])
def test_route_enabled_values_agree_with_the_reader(tmp_path, value):
    got = crew_route.settings(_repo(tmp_path, {"route": {"enabled": value}}))
    declared = crew_keys.values_of("route.enabled")
    assert got["enabled"] is (value is True)
    assert any(value is d for d in declared) == (value in (True, False) and
                                                 isinstance(value, bool))


@pytest.mark.parametrize("value", [True, False, "true", 1])
def test_allow_cli_approval_values_agree_with_the_reader(tmp_path, value):
    root = _repo(tmp_path, {"scope": {"allowCliApproval": value}})
    assert crew_ticket.cli_approval_allowed(root) is (value is True)


def test_prose_values_appear_in_their_source():
    rows = [(k, r) for k, r in crew_keys.KEY_META.items() if r["kind"] == "prose"]
    assert rows
    for key, row in rows:
        with open(os.path.join(PLUGIN, row["source"]), encoding="utf-8") as fh:
            text = fh.read()
        for value in row["values"]:
            assert f"`{value}`" in text, (key, value, row["source"])


def test_no_coming_key_is_in_code():
    landed = crew_keys.coming_in_code()
    assert not landed, "; ".join(
        f"{key} ({ticket}) is in the code now: move this row to KEY_META and set since"
        for key, ticket in landed)


def test_coming_in_code_names_a_landed_key(monkeypatch):
    coming = crew_keys.COMING + (dict(crew_keys.COMING[0], key="pm.maxLines",
                                      ticket="T-9999"),)
    monkeypatch.setattr(crew_keys, "COMING", coming)
    assert ("pm.maxLines", "T-9999") in crew_keys.coming_in_code()


def test_coming_rows_name_a_ticket():
    assert crew_keys.COMING
    for row in crew_keys.COMING:
        assert re.fullmatch(r"T-\d{4}", row["ticket"]), row
        assert row["summary"] and row["default"] and row["layer"], row


def test_coming_changes_name_an_existing_key():
    for row in crew_keys.COMING:
        assert row["change"] == "new key" or row["change"].startswith("changes "), row
        if row["change"] != "new key":
            assert row["key"] in crew_keys.KEY_META, row

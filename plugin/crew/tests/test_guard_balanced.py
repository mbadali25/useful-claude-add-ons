"""R-35: the `balanced` guard profile and the `tiered` guard value.

Acceptance (docs/plans/crew-revamp-2026-11-18.md, R-35): dev/QA deploys are
allowed and logged; unknown is never unattended. Spec: the approved R-35 spec,
revision 3 (CLDDEV-48). Row names follow its section 4: A must-allow, B
must-block, then the guard_decision, note, menu, ratchet, comparator, inert,
migration and parity rows, and the in-file sabotage table at the end.

Every fixture is a temp directory: the machine file and the repo file are two
explicit arguments with no default (None writes no file), and
`crew_config.GLOBAL_CONFIG_PATH` is pointed at the temp machine file. Nothing
here reads or writes real config. Rows go through `cloud_guard.evaluate`, so
the flag, the root, `scan`, `dispatch_gate` and the verdict are all on the road.

The sabotage rows re-execute one mutated source file into its own module for
the length of one check (the `test_crew_policy.py` in-file pattern; the shared
`tests/sabotage*.py` files are review harness and are not edited here).
"""
import contextlib
import copy
import hashlib
import json
import os
import re
import subprocess
import sys

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import cloud_guard
import crew_config
import crew_config_menu
import crew_dispatch
import crew_guard_notes
import crew_guards
import crew_policy
import crew_protected
import crew_state
import crew_upgrade

SCRIPTS = os.path.dirname(os.path.abspath(crew_guards.__file__))
PLUGIN = os.path.dirname(os.path.dirname(SCRIPTS))

BAL = {"profile": "balanced"}
RUN = "gh workflow run deploy.yml"
API = ("gh api -X POST repos/o/r/actions/workflows/deploy.yml/dispatches "
       "-f ref=main")
STAGING = "gh workflow run deploy.yml -f environment=staging"
PLAN = "p.tfplan"
TF_APPLY = f"TF_WORKSPACE=dev terraform apply {PLAN}"
INPUT_MAP = {"workflows": {"deploy.yml": "input:environment"}}


def _layer(guards=None, tiers=None, environments=None, **extra):
    out = {}
    if guards is not None:
        out["guards"] = guards
    if tiers is not None:
        out["tiers"] = tiers
    if environments is not None:
        out["environments"] = environments
    out.update(extra)
    return out


def _dev(target="workflow:deploy.yml", tier="dev"):
    return {target: {"tier": tier}}


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for name in ("TF_WORKSPACE", "TF_VAR_environment", "TF_DATA_DIR", "CI"):
        monkeypatch.delenv(name, raising=False)


def _world(base, monkeypatch, machine, repo):
    """`root` for one case. `machine` and `repo` are each a dict (written as
    JSON), a str (written raw) or None (no file) -- always both given."""
    root = base / "repo"
    (root / ".crew").mkdir(parents=True, exist_ok=True)
    gpath = base / "machine.json"
    for path, data in ((gpath, machine), (root / ".crew" / "config.json", repo)):
        if data is None:
            continue
        path.write_text(data if isinstance(data, str) else json.dumps(data),
                        encoding="utf-8")
    monkeypatch.setattr(crew_config, "GLOBAL_CONFIG_PATH", str(gpath))
    monkeypatch.setattr(crew_state, "GLOBAL_CONFIG_PATH", str(gpath))
    return str(root)


def _eval(monkeypatch, root, command, attended, tool="Bash"):
    monkeypatch.setenv("CREW_UNATTENDED", "0" if attended else "1")
    return cloud_guard.evaluate(root, tool, command, data={"cwd": root})


def _rows(out, rule="deployWorkflow"):
    return [r for r in out["rows"] if r[0] == rule]


def _case(base, monkeypatch, machine, repo, command, tool="Bash"):
    """`(root, attended, unattended)` evaluations of `command`."""
    root = _world(base, monkeypatch, machine, repo)
    return (root, _eval(monkeypatch, root, command, True, tool),
            _eval(monkeypatch, root, command, False, tool))


def _allowed(base, monkeypatch, machine, repo, command, policy, tool="Bash"):
    _root, att, alone = _case(base, monkeypatch, machine, repo, command, tool)
    for out in (att, alone):
        assert out["decision"] == "allow", out
        rows = _rows(out)
        assert len(rows) == 1 and rows[0][2] == "allow", out["rows"]
        assert rows[0][1] == policy + ";account:unchecked", rows
    return att, alone


def _blocked(base, monkeypatch, machine, repo, command, policy=None, tool="Bash",
             rule="deployWorkflow"):
    """Denied unattended, never allowed attended; `policy` (exact, or a
    prefix ending in `*`) is the guard.log policy column of the row."""
    _root, att, alone = _case(base, monkeypatch, machine, repo, command, tool)
    assert alone["decision"] == "deny", alone
    assert att["decision"] in ("ask", "deny"), att
    for out in (att, alone):
        rows = _rows(out, rule)
        assert rows, out
        assert all(r[2] != "allow" for r in rows), rows
        if policy is not None:
            got = [r[1] for r in rows]
            if policy.endswith("*"):
                assert any(p.startswith(policy[:-1]) for p in got), got
            else:
                assert policy in got, got
    return att, alone


# --- A: must-allow ---------------------------------------------------------------------

@pytest.mark.parametrize("tier", ["dev", "qa"])
@pytest.mark.parametrize("command", [RUN, API], ids=["run", "api"])
def test_a1_machine_dev_qa_no_environments_block(tmp_path, monkeypatch, tier, command):
    _allowed(tmp_path, monkeypatch, _layer(BAL, _dev(tier=tier)), _layer(BAL), command,
             f"tier:{tier}:workflow:deploy.yml")


@pytest.mark.parametrize("environments", [{"workflows": {}}, {"nonProd": ["x"]}],
                         ids=["empty-workflows", "no-workflows-key"])
def test_a2_empty_or_missing_workflows(tmp_path, monkeypatch, environments):
    _allowed(tmp_path, monkeypatch, _layer(BAL, _dev()),
             _layer(BAL, environments=environments), RUN, "tier:dev:workflow:deploy.yml")


def test_a3_input_value_selects_the_at_entry(tmp_path, monkeypatch):
    _allowed(tmp_path, monkeypatch, _layer(BAL, _dev("workflow:deploy.yml@staging")),
             _layer(BAL, environments=INPUT_MAP), STAGING,
             "tier:dev:workflow:deploy.yml@staging")


def _marker_from(out):
    match = re.search(r"create (\S+) and re-run", out["reason"])
    assert match, out["reason"]
    return match.group(1)


@pytest.mark.parametrize("tiers", [_dev(), _dev(tier="prod"), {}],
                         ids=["dev", "prod", "unlisted"])
def test_a4_a_live_marker_allows_whatever_the_tier(tmp_path, monkeypatch, tiers):
    command = "gh workflow run other.yml" if tiers.get("workflow:deploy.yml") \
        == {"tier": "dev"} else RUN
    root = _world(tmp_path, monkeypatch, _layer(BAL, tiers), _layer(BAL))
    denied = _eval(monkeypatch, root, command, False)
    assert denied["decision"] == "deny", denied
    with open(_marker_from(denied), "w", encoding="utf-8"):
        pass
    for attended in (True, False):
        out = _eval(monkeypatch, root, command, attended)
        assert out["decision"] == "allow", out


def test_a5_override_tiered_in_both_layers(tmp_path, monkeypatch):
    over = {"profile": "off", "overrides": {"deployWorkflow": "tiered"}}
    _allowed(tmp_path, monkeypatch, _layer(over, _dev()), _layer(over), RUN,
             "tier:dev:workflow:deploy.yml")


# --- B: must-block ---------------------------------------------------------------------

def test_b1_empty_workflows_unlisted_target(tmp_path, monkeypatch):
    _blocked(tmp_path, monkeypatch, _layer(BAL, _dev("workflow:other.yml")),
             _layer(BAL, environments={"workflows": {}}), RUN,
             "tier:unknown:workflow:deploy.yml:unlisted")


def test_b2_absent_environments_unlisted_target(tmp_path, monkeypatch):
    _blocked(tmp_path, monkeypatch, _layer(BAL, {}), _layer(BAL), RUN,
             "tier:unknown:workflow:deploy.yml:unlisted")


def test_b3_repo_lists_another_workflow_only(tmp_path, monkeypatch):
    _blocked(tmp_path, monkeypatch, _layer(BAL, {}),
             _layer(BAL, environments={"workflows": {"other.yml": "staging"}}), RUN,
             "tier:unknown:workflow:deploy.yml:unlisted")


_B4 = {
    "machine-prod": (_layer(BAL, _dev(tier="prod")), _layer(BAL),
                     "tier:prod:workflow:deploy.yml"),
    "narrowed-by-repo": (_layer(BAL, _dev()), _layer(BAL, _dev(tier="prod")),
                         "tier:prod:workflow:deploy.yml"),
    "case-mismatch": (_layer(BAL, _dev("workflow:Deploy.yml")), _layer(BAL),
                      "tier:unknown:workflow:deploy.yml:unlisted"),
    "case-twins": ('{"guards": {"profile": "balanced"}, "tiers": {'
                   '"workflow:deploy.yml": {"tier": "dev"}, '
                   '"workflow:DEPLOY.yml": {"tier": "dev"}}}', _layer(BAL),
                   "tier:unknown:workflow:deploy.yml:conflicting"),
    "machine-unreadable": ('{"guards": {"profile": "balanced"}, "tiers": ', _layer(BAL),
                           None),
    "repo-unreadable": (_layer(BAL, _dev()), '{"guards": {"profile": "balanced"', None),
    "repo-only-dev": (_layer(BAL, {}), _layer(BAL, _dev()),
                      "tier:unknown:workflow:deploy.yml:unlisted"),
}


@pytest.mark.parametrize("name", sorted(_B4))
def test_b4_tier_map_cases(tmp_path, monkeypatch, name):
    machine, repo, policy = _B4[name]
    _blocked(tmp_path, monkeypatch, machine, repo, RUN, policy)


def test_b5_repo_cannot_widen_through_nonprod(tmp_path, monkeypatch):
    env = {"nonProd": ["*"], "prodUnattended": True,
           "workflows": {"deploy.yml": "staging"}}
    _blocked(tmp_path, monkeypatch,
             _layer(BAL, {}, environments={"prodUnattended": True}),
             _layer(BAL, environments=env), RUN,
             "tier:unknown:workflow:deploy.yml:unlisted")


def test_b6_at_entry_with_no_repo_mapping(tmp_path, monkeypatch):
    _blocked(tmp_path, monkeypatch, _layer(BAL, _dev("workflow:deploy.yml@staging")),
             _layer(BAL), STAGING, "tier:unknown:workflow:deploy.yml:unlisted")


def test_b7_a_fixed_repo_name_never_selects_an_at_entry(tmp_path, monkeypatch):
    _blocked(tmp_path, monkeypatch, _layer(BAL, _dev("workflow:deploy.yml@staging")),
             _layer(BAL, environments={"workflows": {"deploy.yml": "staging"}}), RUN,
             "tier:unknown:workflow:deploy.yml:unlisted")


def test_b8_bare_is_not_used_once_the_line_shows_a_value(tmp_path, monkeypatch):
    _blocked(tmp_path, monkeypatch, _layer(BAL, _dev()),
             _layer(BAL, environments=INPUT_MAP), "gh workflow run deploy.yml -f environment=prod",
             "tier:unknown:workflow:deploy.yml@prod:unlisted")


def test_b9_at_entry_listed_prod(tmp_path, monkeypatch):
    tiers = {**_dev(), **_dev("workflow:deploy.yml@prod", "prod")}
    _blocked(tmp_path, monkeypatch, _layer(BAL, tiers),
             _layer(BAL, environments=INPUT_MAP), "gh workflow run deploy.yml -f environment=prod",
             "tier:prod:workflow:deploy.yml@prod")


@pytest.mark.parametrize("command", [
    RUN, "gh workflow run deploy.yml -f environment=staging -f environment=prod"],
    ids=["missing", "twice"])
def test_b10_input_missing_or_conflicting(tmp_path, monkeypatch, command):
    tiers = {**_dev(), **_dev("workflow:deploy.yml@staging")}
    _blocked(tmp_path, monkeypatch, _layer(BAL, tiers),
             _layer(BAL, environments=INPUT_MAP), command,
             "tier:unknown:workflow:deploy.yml:unreadable")


@pytest.mark.parametrize("command,policy", [
    ("gh workflow run", "tier:unknown:workflow:-:no-target"),
    ("gh workflow run deploy.yml other.yml", "tier:unknown:workflow:deploy.yml:no-target"),
    ('gh workflow run "$WF"', "could-not-tell"),
    ("gh workflow run deploy.yml && gh workflow run other.yml", "*"),
], ids=["no-workflow", "second-workflow", "non-literal", "two-dispatches"])
def test_b11_unreadable_shapes(tmp_path, monkeypatch, command, policy):
    if policy != "*":
        _blocked(tmp_path, monkeypatch, _layer(BAL, _dev()), _layer(BAL), command, policy)
    else:
        # The line's verdict is the strictest of its dispatches: the dev one
        # is allowed on its own row, the unlisted one refuses the line.
        _root, att, alone = _case(tmp_path, monkeypatch, _layer(BAL, _dev()), _layer(BAL),
                                  command)
        assert (att["decision"], alone["decision"]) == ("ask", "deny"), (att, alone)
        rows = _rows(alone)
        assert ("deployWorkflow", "tier:dev:workflow:deploy.yml;account:unchecked", "allow",
                RUN) in rows, rows
        assert any(r[1] == "tier:unknown:workflow:other.yml:unlisted" for r in rows), rows


def test_b12_a_raising_lookup_is_unknown(tmp_path, monkeypatch):
    import crew_tiers  # pylint: disable=import-outside-toplevel

    def boom(*_a, **_k):
        raise RuntimeError("lookup broke")
    monkeypatch.setattr(crew_tiers, "resolve", boom)
    _blocked(tmp_path, monkeypatch, _layer(BAL, _dev()), _layer(BAL), RUN,
             "tier:unknown:workflow:deploy.yml:lookup-failed (RuntimeError)")


def test_b12_a_raising_flag_read_still_judges(tmp_path, monkeypatch):
    real = crew_config.resolve_guard
    calls = []

    def flaky(root, name, path=None):
        if name == "deployWorkflow" and not calls:
            calls.append(name)
            raise OSError("flag read broke")
        return real(root, name, path)
    root = _world(tmp_path, monkeypatch, _layer(BAL, {}), _layer(BAL))
    monkeypatch.setattr(crew_config, "resolve_guard", flaky)
    out = _eval(monkeypatch, root, RUN, False)
    assert calls and _rows(out), out
    assert out["decision"] == "deny", out


def _tf_world(base, monkeypatch, machine, repo, workspace="dev"):
    root = _world(base, monkeypatch, machine, repo)
    data = f"plan bytes for {base.name}".encode("utf-8")
    with open(os.path.join(root, PLAN), "wb") as handle:
        handle.write(data)
    folder = os.path.join(root, ".crew", "tfplan")
    os.makedirs(folder, exist_ok=True)
    body = {"plan": PLAN, "workspace": workspace, "environment": None,
            "deletes": [], "tool": "terraform", "created": 0}
    with open(os.path.join(folder, hashlib.sha256(data).hexdigest() + ".json"), "w",
              encoding="utf-8") as handle:
        handle.write(json.dumps(body))
    return root


_NONPROD_ALL = {"nonProd": ["*"], "prodUnattended": True}


def test_b13_named_terraform_dev_never_unattended(tmp_path, monkeypatch):
    """The named row: machine `workspace:dev: dev`, repo nonProd `*`,
    prodUnattended in both layers, a clean saved plan in workspace dev."""
    machine = _layer(BAL, _dev("workspace:dev"), environments={"prodUnattended": True})
    repo = _layer(BAL, environments=_NONPROD_ALL)
    root = _tf_world(tmp_path / "bal", monkeypatch, machine, repo)
    alone = _eval(monkeypatch, root, TF_APPLY, False)
    att = _eval(monkeypatch, root, TF_APPLY, True)
    assert (alone["decision"], att["decision"]) == ("deny", "ask"), (alone, att)
    for out in (alone, att):
        assert [r[1] for r in _rows(out, "terraformApply")] == [
            "tier:dev:workspace:dev:cost-unknown"], out["rows"]
    # The same fixture under `ask` in both layers reaches the nonProd allow, so
    # the row above is known to be on the branch it is about, not the destroy one.
    ask = {"profile": "off", "overrides": {"terraformApply": "ask"}}
    root = _tf_world(tmp_path / "ask", monkeypatch,
                     _layer(ask, _dev("workspace:dev"), environments={"prodUnattended": True}),
                     _layer(ask, environments=_NONPROD_ALL))
    out = _eval(monkeypatch, root, TF_APPLY, False)
    assert out["decision"] == "allow", out
    assert [r[1] for r in _rows(out, "terraformApply")] == ["env:nonProd:dev"], out["rows"]


@pytest.mark.parametrize("tiers,command,policy", [
    (_dev("workspace:dev", "qa"), TF_APPLY, "tier:qa:workspace:dev:cost-unknown"),
    (_dev("workspace:dev", "prod"), TF_APPLY, "tier:prod:workspace:dev"),
    ({}, TF_APPLY, "tier:unknown:workspace:dev:unlisted"),
    (_dev("workspace:dev"), "TF_WORKSPACE=dev terraform destroy -auto-approve", "destroy:ask"),
], ids=["qa", "prod", "unlisted", "destroy"])
def test_b13_terraform_never_unattended(tmp_path, monkeypatch, tiers, command, policy):
    root = _tf_world(tmp_path, monkeypatch, _layer(BAL, tiers),
                     _layer(BAL, environments=_NONPROD_ALL))
    for attended in (True, False):
        out = _eval(monkeypatch, root, command, attended)
        assert out["decision"] == ("ask" if attended else "deny"), out
        assert policy in [r[1] for r in _rows(out, "terraformApply")], out["rows"]


_ONE_LAYER_REPOS = {"no-file": None, "no-guards": {}, "standard": _layer({"profile": "standard"})}


@pytest.mark.parametrize("shape", sorted(_ONE_LAYER_REPOS))
def test_b14_balanced_in_the_machine_layer_only(tmp_path, monkeypatch, shape):
    machine = _layer(BAL, _dev())
    repo = _ONE_LAYER_REPOS[shape]
    mapped = dict(repo or {}, environments=INPUT_MAP)
    root = _world(tmp_path / "a", monkeypatch, machine, mapped)
    assert crew_config.resolve_guard(root, "deployWorkflow")["effective"] == "block"
    assert cloud_guard._deploy_tiered(root) is False  # pylint: disable=protected-access
    for attended in (True, False):
        out = _eval(monkeypatch, root, STAGING, attended)
        assert out["decision"] == "deny", out
        assert [r[1] for r in _rows(out)] == ["block"], out["rows"]
    _b14_unjudged(tmp_path, monkeypatch, machine, repo)


def _b14_unjudged(tmp_path, monkeypatch, machine, repo):
    root = _world(tmp_path / "b", monkeypatch, machine, repo)
    got = [_eval(monkeypatch, root, RUN, a) for a in (True, False)]
    off = {"profile": "off"}
    root = _world(tmp_path / "off", monkeypatch, _layer(off, _dev()), _layer(off))
    want = [_eval(monkeypatch, root, RUN, a) for a in (True, False)]
    assert got == want, (got, want)
    assert all(not _rows(out) and out["decision"] == "allow" for out in got), got


@pytest.mark.parametrize("machine", [_layer(None, _dev()), None], ids=["no-guards", "absent"])
def test_b15_balanced_in_the_repo_layer_only(tmp_path, monkeypatch, machine):
    root = _world(tmp_path, monkeypatch, machine, _layer(BAL))
    assert crew_config.resolve_guard(root, "deployWorkflow")["effective"] == "block"
    for attended in (True, False):
        out = _eval(monkeypatch, root, RUN, attended)
        assert not any(r[1].startswith("tier:") for r in out["rows"]), out["rows"]
        assert out["decision"] == "allow" and not _rows(out), out


@pytest.mark.parametrize("envs", [{}, {"root": None}, {"root": ""}, {"root": 7}],
                         ids=["absent", "none", "empty", "int"])
def test_b16_no_root_is_unknown_and_reads_no_map(tmp_path, monkeypatch, envs):
    import crew_tiers  # pylint: disable=import-outside-toplevel
    _world(tmp_path, monkeypatch, _layer(BAL, _dev()), _layer(BAL))

    def forbidden(*_a, **_k):
        raise AssertionError("crew_tiers.resolve was called with no root")
    monkeypatch.setattr(crew_tiers, "resolve", forbidden)
    scope = {"state": "unknown", "workflow": "deploy.yml", "extra": [], "unlisted": True,
             "value": None, "key": None}
    out = {"policy": "tiered", "marker": str(tmp_path / "m"), "reason": ""}
    got = crew_dispatch.deploy_verdict("w", dict(scope, dispatches=[("unknown", "", scope)]),
                                       out, dict(envs), lambda _m: False)
    assert got[0] == "ask" and got[2] == "tier:unknown:workflow:deploy.yml:no-root", got


def test_b16_evaluate_hands_its_root_to_deploy_verdict(tmp_path, monkeypatch):
    root = _world(tmp_path, monkeypatch, _layer(BAL, _dev()), _layer(BAL))
    seen = []
    real = crew_dispatch.deploy_verdict

    def spy(what, scope, out, envs, live):
        seen.append(envs.get("root"))
        return real(what, scope, out, envs, live)
    monkeypatch.setattr(crew_dispatch, "deploy_verdict", spy)
    assert _eval(monkeypatch, root, RUN, False)["decision"] == "allow"
    assert seen == [root], seen


# --- unchanged behaviour ---------------------------------------------------------------

@pytest.mark.parametrize("policy", ["block", "ask", "allow"])
def test_unchanged_an_unlisted_dispatch_is_not_judged(tmp_path, monkeypatch, policy):
    over = {"profile": "off", "overrides": {"deployWorkflow": policy}}
    root = _world(tmp_path, monkeypatch, _layer(over, _dev()),
                  _layer(over, environments={"workflows": {}}))
    for attended in (True, False):
        out = _eval(monkeypatch, root, RUN, attended)
        assert out["decision"] == "allow" and not _rows(out), out


def test_unchanged_ghdeploy_still_refuses_an_unmapped_workflow(tmp_path, monkeypatch):
    import crew_ghdeploy  # pylint: disable=import-outside-toplevel
    root = _world(tmp_path, monkeypatch, _layer(BAL, _dev()),
                  _layer(BAL, environments={"workflows": {"other.yml": "staging"}}))
    envs = cloud_guard.environments_config(root)
    assert "tiered" not in envs and "root" not in envs
    scope = {"workflow": "deploy.yml", "extra": [], "inputs": []}
    assert crew_dispatch.dispatch_environment(scope, dict(envs, tiered=True)) is None
    assert crew_dispatch.dispatch_environment(
        scope, {"workflows": {}, "tiered": True}) is None
    with pytest.raises(crew_ghdeploy.Refused) as refused:
        crew_ghdeploy.classify(root, "staging", RUN)
    assert refused.value.reason == "unmapped-workflow", refused.value.args


# --- guard_decision (D11) --------------------------------------------------------------

_ASK_REASONS = (
    "guards.{n} is `ask`: the approval at {m} is outside the {w}-minute window",
    "guards.{n} is `ask`: an approval is good for {w} minutes, so it cannot "
    "become a standing grant nobody revisits",
    "approved for this command: {m}",
)


@pytest.mark.parametrize("name", crew_guards.TIERED_GUARD_NAMES)
def test_guard_decision_under_tiered(tmp_path, monkeypatch, name):
    tiered = {"profile": "off", "overrides": {name: "tiered"}}
    root = _world(tmp_path, monkeypatch, _layer(tiered), _layer(tiered))
    command = "the command"
    out = crew_config.guard_decision(root, name, command)
    assert (out["policy"], out["decision"]) == ("tiered", "ask"), out
    assert "`tiered`" in out["reason"] and "tier map" in out["reason"], out
    marker = out["marker"]
    assert marker
    with open(marker, "w", encoding="utf-8"):
        pass
    live = crew_config.guard_decision(root, name, command)
    assert (live["policy"], live["decision"]) == ("tiered", "allow"), live
    assert live["reason"] == f"approved for this command: {marker}"
    old = os.path.getmtime(marker) - crew_state.GUARD_APPROVAL_TTL - 60
    os.utime(marker, (old, old))
    stale = crew_config.guard_decision(root, name, command)
    assert stale["decision"] == "ask" and "`tiered`" in stale["reason"] \
        and "window" in stale["reason"], stale


def test_guard_decision_tiered_in_one_layer_or_another_guard_is_block(tmp_path, monkeypatch):
    tiered = {"profile": "off", "overrides": {"deployWorkflow": "tiered"}}
    root = _world(tmp_path / "a", monkeypatch, _layer(tiered), _layer({"profile": "off"}))
    out = crew_config.guard_decision(root, "deployWorkflow", "x")
    assert (out["policy"], out["decision"]) == ("block", "block"), out
    fp = {"profile": "off", "overrides": {"forcePush": "tiered"}}
    root = _world(tmp_path / "b", monkeypatch, _layer(fp), _layer(fp))
    out = crew_config.guard_decision(root, "forcePush", "x")
    assert (out["policy"], out["decision"]) == ("block", "block"), out


def test_guard_decision_ask_reasons_are_byte_identical(tmp_path, monkeypatch):
    ask = {"profile": "off", "overrides": {"forcePush": "ask"}}
    root = _world(tmp_path, monkeypatch, _layer(ask), _layer(ask))
    window = crew_state.GUARD_APPROVAL_TTL // 60
    out = crew_config.guard_decision(root, "forcePush", "x")
    marker = out["marker"]
    assert out["reason"] == _ASK_REASONS[1].format(n="forcePush", w=window)
    with open(marker, "w", encoding="utf-8"):
        pass
    assert crew_config.guard_decision(root, "forcePush", "x")["reason"] == \
        _ASK_REASONS[2].format(m=marker)
    old = os.path.getmtime(marker) - crew_state.GUARD_APPROVAL_TTL - 60
    os.utime(marker, (old, old))
    assert crew_config.guard_decision(root, "forcePush", "x")["reason"] == \
        _ASK_REASONS[0].format(n="forcePush", m=marker, w=window)


# --- widening notes (D12) and the menu rank (D13) --------------------------------------

@pytest.mark.parametrize("name", crew_state.GUARD_NAMES)
def test_every_note_table_is_total_over_its_tiers(name):
    notes = crew_guard_notes.guard_widening_notes(name, "x")
    assert set(notes) == set(crew_state.guard_tiers(name)[0])


def test_widening_notes_for_tiered():
    deploy = crew_config.widening_note("guards.deployWorkflow", "tiered")
    assert deploy == crew_config.widening_note("guards.overrides.deployWorkflow", "tiered")
    assert "machine tier map" in deploy and "nonProd" not in deploy, deploy
    tf = crew_config.widening_note("guards.terraformApply", "tiered")
    assert "never run unattended" in tf, tf
    assert crew_config.widening_note("guards.deployWorkflow", "allow") == (
        "crew will run a `gh workflow run` or `gh api .../dispatches` of a workflow "
        "listed in `environments.workflows` WITHOUT asking when its environment is "
        f"nonProd, and write a row to `{crew_state.GUARD_LOG_PATH}`. It still asks -- and refuses "
        "when nobody is attending -- for production unless "
        "environments.prodUnattended is true in both config layers, and for an "
        "environment crew cannot identify, whatever this key says.")
    assert crew_config.widening_note("guards.forcePush", "tiered") == \
        crew_config.widening_note("guards.forcePush", "block")


_MENU = [("block", "tiered", True), ("tiered", "ask", True), ("ask", "tiered", False),
         ("tiered", "block", False)]


@pytest.mark.parametrize("name", crew_guards.TIERED_GUARD_NAMES)
@pytest.mark.parametrize("before,after,widens", _MENU)
def test_menu_ranks_tiered_between_block_and_ask(name, before, after, widens):
    dotted = f"guards.{name}"
    assert crew_config_menu._widens(dotted, before, after) is widens  # pylint: disable=protected-access
    rank = crew_config._RATCHETED[dotted][0]  # pylint: disable=protected-access
    assert (rank(after) > rank(before)) is widens


# --- ratchet ---------------------------------------------------------------------------

_RATCHET = {
    "standard+balanced": ({"profile": "standard"}, BAL, "block"),
    "balanced+balanced": (BAL, BAL, "tiered"),
    "balanced+absent": (BAL, None, "block"),
    "absent+balanced": (None, BAL, "block"),
    "balanced+override-ask": (BAL, {"overrides": {"deployWorkflow": "ask"}}, "tiered"),
    "override-ask+override-tiered": ({"overrides": {"deployWorkflow": "ask"}},
                                     {"overrides": {"deployWorkflow": "tiered"}}, "tiered"),
    "case-and-space": ({"profile": "Balanced "}, {"profile": "Balanced "}, "tiered"),
}


@pytest.mark.parametrize("name", sorted(_RATCHET))
def test_ratchet(tmp_path, monkeypatch, name):
    machine, repo, want = _RATCHET[name]
    root = _world(tmp_path, monkeypatch, None if machine is None else _layer(machine),
                  None if repo is None else _layer(repo))
    assert crew_config.resolve_guard(root, "deployWorkflow")["effective"] == want


# --- R-32 comparator (unchanged) -------------------------------------------------------

def _judge(before, after):
    enc = {k: json.dumps(_layer({"profile": v} if isinstance(v, str) else v)).encode()
           for k, v in before.items()}
    new = {k: json.dumps(_layer({"profile": v} if isinstance(v, str) else v)).encode()
           for k, v in after.items()}
    result = crew_protected.judge_change(enc, new)
    widened = {r["leaf"] for r in result["changed"] if r["outcome"] == "widening"}
    return result["status"], widened


_BOTH = ("machine", "repo")
_TIER_LEAVES = {"guards.terraformApply", "guards.deployWorkflow"}


def test_comparator_standard_to_balanced_widens_two_leaves():
    status, widened = _judge(dict.fromkeys(_BOTH, "standard"), dict.fromkeys(_BOTH, "balanced"))
    assert (status, widened) == ("would-refuse", _TIER_LEAVES)


def test_comparator_off_to_balanced_widens_three_leaves():
    status, widened = _judge(dict.fromkeys(_BOTH, "off"), dict.fromkeys(_BOTH, "balanced"))
    assert (status, widened) == ("would-refuse", _TIER_LEAVES | {"guards.adminMerge"})
    status, widened = _judge(dict.fromkeys(_BOTH, "off"), dict.fromkeys(_BOTH, "standard"))
    assert (status, widened) == ("would-refuse", {"guards.adminMerge"})


def test_comparator_overrides_and_narrowing():
    over = {"profile": "off", "overrides": {"terraformApply": "tiered",
                                            "deployWorkflow": "tiered"}}
    status, widened = _judge(dict.fromkeys(_BOTH, "off"), dict.fromkeys(_BOTH, over))
    assert (status, widened) == ("would-refuse", _TIER_LEAVES)
    status, widened = _judge(dict.fromkeys(_BOTH, "balanced"), dict.fromkeys(_BOTH, "standard"))
    assert status != "would-refuse" and widened == set(), (status, widened)


# --- inert -----------------------------------------------------------------------------

def test_inert_defaults_resolve_both_guards_to_block(tmp_path, monkeypatch):
    root = _world(tmp_path, monkeypatch, None, None)
    for name in crew_guards.TIERED_GUARD_NAMES:
        assert crew_config.resolve_guard(root, name)["effective"] == "block"
    assert crew_guards.GUARD_BLOCK_DEFAULTS["profile"] == "off"


def test_inert_no_shipped_file_sets_balanced_or_tiered():
    bad = []
    for top, _dirs, files in os.walk(PLUGIN):
        if os.sep + "tests" in top:
            continue
        for name in files:
            if not name.endswith(".json"):
                continue
            path = os.path.join(top, name)
            with open(path, encoding="utf-8", errors="replace") as handle:
                text = handle.read()
            if re.search(r'"(balanced|tiered)"', text) and "keys.json" not in name:
                bad.append(path)
    assert bad == [], bad


_INERT = """
import json, os, sys
sys.path.insert(0, sys.argv[1])
import crew_config, crew_state, cloud_guard
crew_config.GLOBAL_CONFIG_PATH = crew_state.GLOBAL_CONFIG_PATH = sys.argv[3]
os.environ["CREW_UNATTENDED"] = "1"
out = cloud_guard.evaluate(sys.argv[2], "Bash", sys.argv[4], data={"cwd": sys.argv[2]})
print(json.dumps([out["decision"], "crew_tiers" in sys.modules]))
"""


@pytest.mark.parametrize("policy", ["block", "ask", "allow"])
def test_inert_crew_tiers_is_not_loaded_off_the_tiered_path(tmp_path, monkeypatch, policy):
    over = {"profile": "off", "overrides": {"deployWorkflow": policy, "terraformApply": policy}}
    env = {"workflows": {"deploy.yml": "input:environment"}, "nonProd": ["staging"]}
    root = _world(tmp_path, monkeypatch, _layer(over, _dev()), _layer(over, environments=env))
    for command in (STAGING, f"TF_WORKSPACE=staging terraform apply {PLAN}"):
        done = subprocess.run(
            [sys.executable, "-c", _INERT, SCRIPTS, root, crew_config.GLOBAL_CONFIG_PATH,
             command], capture_output=True, text=True, timeout=120, check=False)
        assert done.returncode == 0, done.stderr
        assert json.loads(done.stdout.strip().splitlines()[-1])[1] is False, done.stdout


# --- migration (D9) --------------------------------------------------------------------

def test_migration_never_chooses_balanced():
    assert "balanced" not in crew_upgrade._PROFILE_TIE_ORDER  # pylint: disable=protected-access
    assert crew_upgrade.choose_profile(crew_guards.PROFILE_MAP["balanced"]) == (
        "standard", {"terraformApply": "tiered", "deployWorkflow": "tiered"})
    tables = [crew_guards.PROFILE_MAP[p] for p in crew_guards.GUARD_PROFILES]
    tables.append({**crew_guards.PROFILE_MAP["off"], "deployWorkflow": "tiered"})
    tables.append({**crew_guards.PROFILE_MAP["strict"], "terraformApply": "tiered"})
    for table in tables:
        assert crew_upgrade.choose_profile(table)[0] in ("off", "standard", "strict")


def test_migration_keeps_a_tiered_layers_values():
    layer = {"guards": dict(crew_guards.PROFILE_MAP["balanced"])}
    before = {n: crew_state.layer_guard_value(layer, n) for n in crew_guards.ALL_GUARD_NAMES}
    out = copy.deepcopy(layer)
    profile, _over = crew_upgrade.rewrite_guards(out, [])
    assert profile in ("off", "standard", "strict")
    after = {n: crew_state.layer_guard_value(out, n) for n in crew_guards.ALL_GUARD_NAMES}
    assert after == before


# --- parity with crew_policy (D7) ------------------------------------------------------

def _guard_allows(tmp_path, monkeypatch, tier):
    tiers = {} if tier == "unknown" else _dev(tier=tier)
    root = _world(tmp_path / tier, monkeypatch, _layer(BAL, tiers), _layer(BAL))
    return _eval(monkeypatch, root, RUN, False)["decision"] == "allow"


@pytest.mark.parametrize("tier", ["dev", "qa", "prod", "unknown"])
def test_parity_with_the_policy_table(tmp_path, monkeypatch, tier):
    """The guard's deploy rows equal `crew_policy.decide` for `start-deploy`
    with a verified write account and a clear machine layer. The one named
    divergence: the guard does not check the account (no registry until R-AB),
    so with NO account the table denies (rule 2) and the guard still allows."""
    request = {"operation": "start-deploy", "tier": tier, "presence": "unattended",
               "account": "write-verified", "machine_layer": "clear"}
    table = crew_policy.decide(request)["outcome"] == "allow"
    assert _guard_allows(tmp_path, monkeypatch, tier) is table
    if tier in ("dev", "qa"):
        unchecked = dict(request)
        del unchecked["account"]
        assert crew_policy.decide(unchecked)["outcome"] != "allow"  # the named divergence


@pytest.mark.parametrize("tier", ["dev", "qa", "prod"])
def test_parity_terraform_is_money_without_an_estimate(tier):
    request = {"operation": "terraform-apply", "tier": tier, "presence": "unattended",
               "account": "write-verified", "machine_layer": "clear"}
    assert crew_policy.decide(request)["outcome"] != "allow"


# --- sabotage (in-file; the shared harness is not edited) ------------------------------

@contextlib.contextmanager
def _mutated(module_name, old, new):
    """Re-execute `module_name`'s source with `old` replaced by `new`, inside
    its own module dict, and point every other loaded crew module's reference
    to a replaced object at the new one; undo both on exit."""
    mod = sys.modules[module_name]
    with open(mod.__file__, encoding="utf-8") as handle:
        source = handle.read()
    assert source.count(old) == 1, (module_name, old, source.count(old))
    snapshot = dict(mod.__dict__)
    swaps = []
    try:
        exec(compile(source.replace(old, new), mod.__file__, "exec"),  # pylint: disable=exec-used
             mod.__dict__)
        fresh = {id(v): mod.__dict__[k] for k, v in snapshot.items()
                 if k in mod.__dict__ and mod.__dict__[k] is not v
                 and (callable(v) or isinstance(v, (dict, tuple)))}
        for other in list(sys.modules.values()):
            path = getattr(other, "__file__", None) or ""
            if other is mod or not path.startswith(SCRIPTS):
                continue
            for attr, value in list(vars(other).items()):
                if id(value) in fresh and fresh[id(value)] is not value:
                    swaps.append((other, attr, value))
                    setattr(other, attr, fresh[id(value)])
        yield
    finally:
        for other, attr, value in reversed(swaps):
            setattr(other, attr, value)
        mod.__dict__.clear()
        mod.__dict__.update(snapshot)


def _ratchet_row(tmp_path, monkeypatch):
    test_ratchet(tmp_path, monkeypatch, "balanced+override-ask")
    test_menu_ranks_tiered_between_block_and_ask("deployWorkflow", "tiered", "ask", True)


def _decision_row(tmp_path, monkeypatch):
    test_guard_decision_under_tiered(tmp_path, monkeypatch, "deployWorkflow")


def _note_row(_tmp_path, _monkeypatch):
    test_menu_ranks_tiered_between_block_and_ask("deployWorkflow", "block", "tiered", True)


SABOTAGE = (
    ("tiered ranked above ask", "crew_guards",
     'TIERED_POLICIES = ("block", "tiered", "ask", "allow")',
     'TIERED_POLICIES = ("block", "ask", "tiered", "allow")', _ratchet_row),
    ("prod treated as allow", "crew_dispatch",
     '    if tier in ("dev", "qa"):\n        return "allow", (f"{lead}',
     '    if tier in ("dev", "qa", "prod"):\n        return "allow", (f"{lead}',
     lambda t, m: test_b4_tier_map_cases(t, m, "machine-prod")),
    ("unknown treated as allow", "crew_dispatch",
     '        return "unknown", target, reason or "unknown"',
     '        return "dev", target, reason or "unknown"', test_b1_empty_workflows_unlisted_target),
    ("repo nonProd consulted for a dispatch under tiered", "crew_dispatch",
     '    if policy == "tiered":\n        return _tiered_verdict(',
     '    if policy == "tiered" and klass != ENV_NONPROD:\n        return _tiered_verdict(',
     test_b5_repo_cannot_widen_through_nonprod),
    ("repo nonProd consulted for terraform under tiered", "cloud_guard",
     '    if policy == "tiered":\n        return _tiered_terraform(',
     '    if policy == "tiered" and klass != ENV_NONPROD:\n        return _tiered_terraform(',
     test_b13_named_terraform_dev_never_unattended),
    ("repo narrowing skipped", "crew_dispatch",
     "        found = crew_tiers.resolve(target, root)\n",
     "        found = crew_tiers.resolve(target, None)\n",
     lambda t, m: test_b4_tier_map_cases(t, m, "narrowed-by-repo")),
    ("the unengaged return kept under tiered", "crew_dispatch",
     "    if not tiered and not dispatch_engaged(envs):",
     "    if not dispatch_engaged(envs):", test_b2_absent_environments_unlisted_target),
    ("the unlisted drop kept under tiered", "crew_dispatch",
     "        elif tiered:\n            answers.append((ENV_UNKNOWN,",
     "        elif False:\n            answers.append((ENV_UNKNOWN,",
     test_b3_repo_lists_another_workflow_only),
    ("the allow row not logged", "crew_dispatch",
     'f"tier:{tier}:{target};account:unchecked"', '""',
     lambda t, m: test_a1_machine_dev_qa_no_environments_block(t, m, "dev", RUN)),
    ("terraform dev allowed unattended", "cloud_guard",
     '    if tier in ("dev", "qa"):\n        return "ask", (f"{lead}',
     '    if tier in ("dev", "qa"):\n        return "allow", (f"{lead}',
     test_b13_named_terraform_dev_never_unattended),
    ("a fixed repo name selects an at entry", "crew_dispatch",
     '    if isinstance(source, str) and source.startswith("input:"):',
     "    if isinstance(source, str):", test_b7_a_fixed_repo_name_never_selects_an_at_entry),
    ("bare used when the line shows a value", "crew_dispatch",
     '        return f"workflow:{wf}@{value}", None',
     '        return f"workflow:{wf}", None', test_b8_bare_is_not_used_once_the_line_shows_a_value),
    ("guard_decision's tiered branch removed", "crew_config",
     '    elif policy == "tiered":\n        decision, reason = _tiered_decision(name, marker)\n',
     "", _decision_row),
    ("_RATCHETED back on guard_policy_rank", "crew_config",
     "        crew_state.guard_tiers(_name)[2],\n        crew_state.guard_tiers(_name)[1],",
     "        crew_state.guard_policy_rank,\n        crew_state.normalise_guard_policy,",
     _note_row),
    ("the flag is False when its read raises", "cloud_guard",
     "    except Exception:  # pylint: disable=broad-exception-caught\n        return True",
     "    except Exception:  # pylint: disable=broad-exception-caught\n        return False",
     test_b12_a_raising_flag_read_still_judges),
    ("a missing root falls back to resolve(target, None)", "crew_dispatch",
     '    if not isinstance(root, str) or not root:\n        return "unknown", target, "no-root"',
     '    if False:\n        return "unknown", target, "no-root"',
     lambda t, m: test_b16_no_root_is_unknown_and_reads_no_map(t, m, {})),
    ("evaluate does not set the root", "cloud_guard",
     'envs["tiered"], envs["root"] = _deploy_tiered(root), root',
     'envs["tiered"] = _deploy_tiered(root)',
     lambda t, m: test_a1_machine_dev_qa_no_environments_block(t, m, "dev", RUN)),
    ("the flag read from the machine layer", "cloud_guard",
     '(root, DEPLOY_RULE)["effective"] == "tiered"',
     '(root, DEPLOY_RULE)["global"] == "tiered"',
     lambda t, m: test_b14_balanced_in_the_machine_layer_only(t, m, "standard")),
    ("the ratchet takes the higher layer", "crew_guards",
     "    return tiers[min(rank(repo_value), rank(global_value))]",
     "    return tiers[max(rank(repo_value), rank(global_value))]",
     lambda t, m: test_b15_balanced_in_the_repo_layer_only(t, m, _layer(None, _dev()))),
)


@pytest.mark.parametrize("label,module,old,new,row", SABOTAGE, ids=[s[0] for s in SABOTAGE])
def test_a_weakened_rule_turns_a_row_red(tmp_path, monkeypatch, label, module, old, new, row):
    row(tmp_path / "green", monkeypatch)  # green before the mutation
    with _mutated(module, old, new):
        with pytest.raises(AssertionError):
            row(tmp_path / "red", monkeypatch)
    row(tmp_path / "again", monkeypatch)  # and green again after it, label: label

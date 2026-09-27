"""T-0072: `autopilot.deploy` and `crew_autopilot.deploy_allowed`.

    python3 -m pytest plugin/crew/tests/test_crew_autopilot_deploy.py -q

The policy layer only: the decision a deploy dispatcher (T-0045) asks before
each dispatch. Production is `allow` only under `autopilot.deploy: all`, with
`environments.prodUnattended` true in BOTH config layers and the cloud guard
armed in `block`. Anything crew cannot tell asks; an emergency refuses.

Every must-block case starts from the fully armed fixture, where both `prod`
and `nonProd` allow, and changes one thing -- so the value a bug would
collapse to allows and the test can go red. `sabotage_autopilot.py`'s
DEPLOY_MUTATIONS proves each one can. Every repository and the machine-global
file are built under tmp_path; nothing reads the real ~/.claude.
"""
import copy
import itertools
import json
import os

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import cloud_guard
import crew_autopilot
import crew_config
import crew_state

PROD, NONPROD = "prod", "nonProd"
# A string, not object(): `copy.deepcopy` would clone an object() sentinel.
DROP = "<drop this key>"

ARMED_REPO = {
    "autopilot": {"mode": "plan", "deploy": "all"},
    "guards": {"cloudGuard": "block"},
    "environments": {"nonProd": ["dev", "qa"], "prodUnattended": True},
}
ARMED_MACHINE = {
    "guards": {"cloudGuard": "block"},
    "environments": {"prodUnattended": True},
}
ALLOW_REASON = ("autopilot.deploy=all and environments.prodUnattended=true in both "
                "config layers (repo and machine), guards.cloudGuard=block")


# --- fixture -----------------------------------------------------------------

def _merge(base, over):
    out = copy.deepcopy(base)
    for key, value in (over or {}).items():
        if value == DROP:
            out.pop(key, None)
        elif isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _merge(out[key], value)
        else:
            out[key] = copy.deepcopy(value)
    return out


def _machine_path(tmp_path):
    return str(tmp_path / "machine" / "config.json")


def _armed(tmp_path, monkeypatch, repo=None, machine=None):
    """The fully armed repo and machine layers, each deep-merged with its
    override (`DROP` removes a key). Returns the repo root as a string."""
    root = tmp_path / "repo"
    (root / ".crew").mkdir(parents=True)
    (root / ".crew" / "config.json").write_text(
        json.dumps(_merge(ARMED_REPO, repo)), encoding="utf-8")
    machine_path = _machine_path(tmp_path)
    os.makedirs(os.path.dirname(machine_path))
    with open(machine_path, "w", encoding="utf-8") as handle:
        handle.write(json.dumps(_merge(ARMED_MACHINE, machine)))
    monkeypatch.setattr(crew_config, "GLOBAL_CONFIG_PATH", machine_path)
    monkeypatch.setattr(crew_state, "GLOBAL_CONFIG_PATH", machine_path)
    return str(root)


def _replace_file(path, form):
    """Swap the file at `path` for a broken `form` of it."""
    os.remove(path)
    if form == "directory":
        os.makedirs(path)
    elif form == "dangling-symlink":
        os.symlink(path + ".gone", path)
    else:
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(form)


def _verdict(root, env_class, env="production"):
    return crew_autopilot.deploy_allowed(root, env, env_class)


# --- the armed fixture allows, so every case below can fail -------------------

def test_fully_armed_prod_allows(tmp_path, monkeypatch):
    root = _armed(tmp_path, monkeypatch)

    got = _verdict(root, PROD)

    assert (got["verdict"], got["reason"]) == ("allow", ALLOW_REASON)


def test_all_allows_nonprod(tmp_path, monkeypatch):
    root = _armed(tmp_path, monkeypatch)

    got = _verdict(root, NONPROD, env="dev")

    assert (got["verdict"], got["report"]) == ("allow", "")


def test_prod_allow_reports_by_name(tmp_path, monkeypatch):
    root = _armed(tmp_path, monkeypatch)

    got = _verdict(root, PROD, env="production")

    assert got["report"] == f"unattended production: production allow - {ALLOW_REASON}"


def test_nonprod_allows_nonprod(tmp_path, monkeypatch):
    root = _armed(tmp_path, monkeypatch, repo={"autopilot": {"deploy": "nonprod"}})

    got = _verdict(root, NONPROD, env="qa")

    assert (got["verdict"], got["report"], got["deploy"]) == ("allow", "", "nonprod")


def test_machine_only_cloud_guard_block_arms(tmp_path, monkeypatch):
    root = _armed(tmp_path, monkeypatch, repo={"guards": DROP})

    got = _verdict(root, PROD)

    assert got["verdict"] == "allow"


@pytest.mark.parametrize("case", ["ask", "refuse"])
def test_every_prod_decision_reports(tmp_path, monkeypatch, case):
    if case == "ask":
        root = _armed(tmp_path, monkeypatch, repo={"autopilot": {"deploy": "none"}})
    else:
        root = _armed(tmp_path, monkeypatch)
        (tmp_path / "repo" / ".crew" / "incident.json").write_text("{}", encoding="utf-8")

    got = _verdict(root, PROD, env="prod-eu-1")

    assert (got["verdict"], got["report"].startswith(
        f"unattended production: prod-eu-1 {case} - ")) == (case, True)


# --- must-block: an emergency refuses ----------------------------------------

def _incident_forms():
    now = 1_790_000_000
    return {
        "valid": json.dumps({"id": "INC-1", "declaredAt": now, "expiresAt": now + 7200,
                             "standDown": True}),
        "expired": json.dumps({"id": "INC-1", "declaredAt": 1, "expiresAt": 2,
                               "standDown": True}),
        "not-json": "{not json",
        "standdown-off": json.dumps({"id": "INC-1", "standDown": False}),
        "directory": "directory",
        "dangling-symlink": "dangling-symlink",
    }


@pytest.mark.parametrize("env_class", [PROD, NONPROD])
@pytest.mark.parametrize("form", list(_incident_forms()))
def test_incident_refuses(tmp_path, monkeypatch, form, env_class):
    root = _armed(tmp_path, monkeypatch)
    path = os.path.join(root, ".crew", "incident.json")
    with open(path, "w", encoding="utf-8") as handle:
        handle.write("{}")
    _replace_file(path, _incident_forms()[form])

    got = _verdict(root, env_class)

    assert (got["verdict"], "emergency" in got["reason"]) == ("refuse", True)


def test_incident_unreadable_path_refuses(tmp_path, monkeypatch):
    root = _armed(tmp_path, monkeypatch)
    real = os.lstat

    def lstat(path, *args, **kwargs):
        if str(path).endswith(os.path.join(".crew", "incident.json")):
            raise PermissionError(13, "Permission denied", str(path))
        return real(path, *args, **kwargs)

    monkeypatch.setattr(os, "lstat", lstat)

    got = _verdict(root, PROD)

    assert (got["verdict"], "PermissionError" in got["reason"]) == ("refuse", True)


# --- must-block: could not tell asks -----------------------------------------

@pytest.mark.parametrize("env", ["", "  ", None, 5, "prod\nverdict=allow"])
def test_env_name_not_usable_asks(tmp_path, monkeypatch, env):
    root = _armed(tmp_path, monkeypatch)

    got = _verdict(root, PROD, env=env)

    assert (got["verdict"], "could not tell which environment" in got["reason"]) == (
        "ask", True)


@pytest.mark.parametrize("env_class", ["unknown", "Prod", "production", "nonprod", "", None])
def test_class_not_known_asks(tmp_path, monkeypatch, env_class):
    root = _armed(tmp_path, monkeypatch)

    got = _verdict(root, env_class)

    assert (got["verdict"], "could not classify" in got["reason"]) == ("ask", True)


@pytest.mark.parametrize("form", ["{bad json", "directory", json.dumps({"guards": 42})])
def test_corrupt_machine_layer_asks(tmp_path, monkeypatch, form):
    root = _armed(tmp_path, monkeypatch)
    _replace_file(_machine_path(tmp_path), form)

    got = _verdict(root, NONPROD, env="dev")

    assert (got["verdict"], got["reason"]) == ("ask", "could not read the machine config layer")


def test_corrupt_repo_layer_names_could_not_tell(tmp_path, monkeypatch):
    root = _armed(tmp_path, monkeypatch)
    _replace_file(os.path.join(root, ".crew", "config.json"), "{bad json")

    got = _verdict(root, PROD)

    assert (got["verdict"], got["reason"]) == ("ask", "could not read the repo config layer")


@pytest.mark.parametrize("layer", ["repo", "machine"])
def test_malformed_environments_block_asks(tmp_path, monkeypatch, layer):
    bad = {"environments": {"prodUnattended": "true"}}
    root = _armed(tmp_path, monkeypatch, **{layer: bad})

    got = _verdict(root, NONPROD, env="dev")

    assert (got["verdict"], got["reason"]) == ("ask", f"could not read the {layer} config layer")


def test_exception_asks(tmp_path, monkeypatch):
    root = _armed(tmp_path, monkeypatch)

    def boom(*_args, **_kwargs):
        raise RuntimeError("ratchet exploded")

    monkeypatch.setattr(crew_config, "resolve_ratcheted", boom)

    got = _verdict(root, PROD)

    assert (got["verdict"], "RuntimeError: ratchet exploded" in got["reason"]) == ("ask", True)


# --- must-block: policy asks --------------------------------------------------

@pytest.mark.parametrize("env_class", [PROD, NONPROD])
@pytest.mark.parametrize("mode", ["off", "Plan", DROP])
def test_autopilot_not_armed_asks(tmp_path, monkeypatch, mode, env_class):
    root = _armed(tmp_path, monkeypatch, repo={"autopilot": {"mode": mode}})

    got = _verdict(root, env_class)

    assert (got["verdict"], got["reason"]) == ("ask", "autopilot.mode is not plan")


@pytest.mark.parametrize("env_class", [PROD, NONPROD])
def test_deploy_none_asks(tmp_path, monkeypatch, env_class):
    root = _armed(tmp_path, monkeypatch, repo={"autopilot": {"deploy": "none"}})

    got = _verdict(root, env_class)

    assert (got["verdict"], got["reason"]) == ("ask", "autopilot.deploy is none")


@pytest.mark.parametrize("value", ["All", "all ", "prod", "production", "NONPROD", True, 1, None])
def test_deploy_value_typo_reads_none(tmp_path, monkeypatch, value):
    root = _armed(tmp_path, monkeypatch, repo={"autopilot": {"deploy": value}})

    got = _verdict(root, NONPROD, env="dev")
    warned = [w for w in crew_autopilot.settings(root)["warnings"] if repr(value) in w]

    assert (got["verdict"], got["deploy"], len(warned)) == ("ask", "none", 1)


def test_deploy_only_in_machine_layer_reads_none(tmp_path, monkeypatch):
    root = _armed(tmp_path, monkeypatch, repo={"autopilot": {"deploy": DROP}},
                  machine={"autopilot": {"deploy": "all"}})

    got = _verdict(root, NONPROD, env="dev")

    assert (got["verdict"], got["deploy"]) == ("ask", "none")


def test_nonprod_never_allows_prod(tmp_path, monkeypatch):
    root = _armed(tmp_path, monkeypatch, repo={"autopilot": {"deploy": "nonprod"}})

    got = _verdict(root, PROD)

    assert (got["verdict"], got["reason"]) == (
        "ask", "autopilot.deploy is nonprod; production needs all")


@pytest.mark.parametrize("granted", ["repo-only", "machine-only"])
def test_prod_needs_both_layers(tmp_path, monkeypatch, granted):
    off = {"environments": {"prodUnattended": False}}
    missing = "machine" if granted == "repo-only" else "repo"
    root = _armed(tmp_path, monkeypatch, **{missing: off})

    got = _verdict(root, PROD)

    assert (got["verdict"], f"not true in the {missing} config layer" in got["reason"]) == (
        "ask", True)


@pytest.mark.parametrize("mode", ["off", "report"])
def test_cloud_guard_not_armed_asks(tmp_path, monkeypatch, mode):
    guards = {"guards": {"cloudGuard": mode}}
    root = _armed(tmp_path, monkeypatch, repo=guards, machine=guards)

    got = _verdict(root, PROD)

    assert (got["verdict"], got["reason"].startswith(f"guards.cloudGuard is {mode}")) == (
        "ask", True)


def test_cloud_guard_forced_block_is_not_armed(tmp_path, monkeypatch):
    guards = {"guards": {"cloudGuard": "report"}}
    root = _armed(tmp_path, monkeypatch, repo=dict(guards, cloud=None), machine=guards)
    mode, note = cloud_guard.resolve_mode(root)

    got = _verdict(root, PROD)

    assert (mode, bool(note), got["verdict"]) == ("block", True, "ask")


# --- the matrix and parity with cloud_guard -----------------------------------

LAYER_VALUES = ("absent", False, True, "true", 1, None)
MALFORMED = ("true", 1, None)


def _layer(value):
    if value == "absent" and isinstance(value, str):
        return {"environments": {"prodUnattended": DROP}}
    return {"environments": {"prodUnattended": value}}


def _is_malformed(value):
    return any(value is m or (value == m and type(value) is type(m)) for m in MALFORMED)


def _expected(repo, machine, deploy, env_class):
    """The rule from the spec's Acceptance, written from the rule and not from
    the function under test."""
    if _is_malformed(repo) or _is_malformed(machine):
        return "ask"
    if env_class not in (PROD, NONPROD) or deploy == "none":
        return "ask"
    if env_class == NONPROD:
        return "allow"
    both = repo is True and machine is True
    return "allow" if deploy == "all" and both else "ask"


MATRIX = list(itertools.product(LAYER_VALUES, LAYER_VALUES, ("none", "nonprod", "all"),
                                (NONPROD, PROD, "unknown")))


def test_matrix_is_324_cases():
    assert len(MATRIX) == 324


def test_prod_unattended_matrix(tmp_path, monkeypatch):
    wrong = []
    for index, (repo, machine, deploy, env_class) in enumerate(MATRIX):
        case = tmp_path / str(index)
        case.mkdir()
        root = _armed(case, monkeypatch, repo=_merge(_layer(repo), {
            "autopilot": {"deploy": deploy}}), machine=_layer(machine))

        got = _verdict(root, env_class)["verdict"]

        if got != _expected(repo, machine, deploy, env_class):
            wrong.append((repo, machine, deploy, env_class, got))
    assert wrong == []


def test_prod_allow_agrees_with_cloud_guard(tmp_path, monkeypatch):
    wrong = []
    for index, (repo, machine) in enumerate(itertools.product(LAYER_VALUES, LAYER_VALUES)):
        case = tmp_path / str(index)
        case.mkdir()
        root = _armed(case, monkeypatch, repo=_layer(repo), machine=_layer(machine))
        envs = cloud_guard.environments_config(root)
        corrupt = "corrupt" in (
            crew_config.layer_state(os.path.join(root, ".crew", "config.json"),
                                    environments=True),
            crew_config.layer_state(crew_config.GLOBAL_CONFIG_PATH, environments=True))

        got = _verdict(root, PROD)["verdict"]

        if (got == "allow") != (envs["prodUnattended"] is True and not corrupt):
            wrong.append((repo, machine, got, envs))
        if _is_malformed(repo) and (not envs["problem"] or got != "ask"):
            wrong.append(("problem", repo, machine, got, envs))
    assert wrong == []


# --- settings and the CLI -------------------------------------------------------

@pytest.mark.parametrize("value", ["none", "nonprod", "all"])
def test_deploy_value_reads(tmp_path, monkeypatch, value):
    root = _armed(tmp_path, monkeypatch, repo={"autopilot": {"deploy": value}})

    got = crew_autopilot.settings(root)

    assert (got["deploy"], got["deploySaw"]) == (value, value)


def test_deploy_armed_warns_inert(tmp_path, monkeypatch):
    root = _armed(tmp_path, monkeypatch)

    got = crew_autopilot.settings(root)

    assert [w for w in got["warnings"] if "T-0045" in w] == [
        "autopilot.deploy is 'all', but nothing in this crew version dispatches a deploy: "
        "T-0045 consumes it; deploy-allowed answers the policy only"]


def test_settings_line_names_deploy(tmp_path, monkeypatch, capsys):
    root = _armed(tmp_path, monkeypatch)

    code = crew_autopilot.main(["settings", "--root", root])

    assert (code, capsys.readouterr().out.splitlines()[0]) == (
        0, "mode=plan maxPhases=12 deploy=all")


def test_cli_prints_verdict_line(tmp_path, monkeypatch, capsys):
    root = _armed(tmp_path, monkeypatch)

    code = crew_autopilot.main(["deploy-allowed", "--root", root, "--env", "production",
                                "--class", PROD])

    assert (code, capsys.readouterr().out) == (
        0, f"verdict=allow env=production class=prod reason={ALLOW_REASON}\n")


def test_cli_prints_report_to_stderr(tmp_path, monkeypatch, capsys):
    root = _armed(tmp_path, monkeypatch)

    crew_autopilot.main(["deploy-allowed", "--root", root, "--env", "production",
                         "--class", PROD])

    assert capsys.readouterr().err == (
        f"unattended production: production allow - {ALLOW_REASON}\n")


def test_cli_json_carries_the_decision(tmp_path, monkeypatch, capsys):
    root = _armed(tmp_path, monkeypatch)

    crew_autopilot.main(["deploy-allowed", "--root", root, "--env", "dev",
                         "--class", NONPROD, "--json"])
    got = json.loads(capsys.readouterr().out)

    assert (got["verdict"], got["env"], got["envClass"], got["deploy"]) == (
        "allow", "dev", NONPROD, "all")


def test_cli_crash_prints_ask(tmp_path, monkeypatch, capsys):
    root = _armed(tmp_path, monkeypatch)

    def boom(*_args, **_kwargs):
        raise RuntimeError("decision exploded")

    monkeypatch.setattr(crew_autopilot, "deploy_allowed", boom)

    code = crew_autopilot.main(["deploy-allowed", "--root", root, "--env", "production",
                                "--class", PROD])

    assert (code, capsys.readouterr().out.startswith("verdict=ask ")) == (0, True)


@pytest.mark.parametrize("missing", ["--env", "--class"])
def test_cli_requires_env_and_class(tmp_path, monkeypatch, missing):
    root = _armed(tmp_path, monkeypatch)
    argv = {"--env": "production", "--class": PROD}
    argv.pop(missing)

    code = crew_autopilot.main(["deploy-allowed", "--root", root]
                               + [part for pair in argv.items() for part in pair])

    assert code == 2

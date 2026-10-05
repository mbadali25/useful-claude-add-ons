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
import errno
import itertools
import json
import os
import sys

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


def test_fully_armed_prod_names_the_checkout_it_judged(tmp_path, monkeypatch):
    root = _armed(tmp_path, monkeypatch)
    judged = crew_autopilot.crew_ticket.toplevel(root) or os.path.abspath(root)

    got = _verdict(root, PROD)

    assert (got["verdict"], got["root"]) == ("allow", judged)


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


@pytest.mark.parametrize("env_class", [PROD, NONPROD])
def test_machine_route_block_does_not_change_the_verdict(tmp_path, monkeypatch, env_class):
    """T-0023 put a `route` block in `default_global_config()`: a machine
    file that sets it beside the armed fixture is a well-formed layer, not
    a corrupt one, so the verdict stays `allow`."""
    root = _armed(tmp_path, monkeypatch, machine={"route": {"enabled": True}})

    got = _verdict(root, env_class, env="production" if env_class == PROD else "dev")

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


@pytest.mark.parametrize("env_class", [PROD, NONPROD])
def test_incident_unreadable_path_refuses(tmp_path, monkeypatch, env_class):
    root = _armed(tmp_path, monkeypatch)
    real = os.lstat

    def lstat(path, *args, **kwargs):
        if str(path).endswith(os.path.join(".crew", "incident.json")):
            raise PermissionError(13, "Permission denied", str(path))
        return real(path, *args, **kwargs)

    monkeypatch.setattr(os, "lstat", lstat)

    got = _verdict(root, env_class)

    assert (got["verdict"], "PermissionError" in got["reason"]) == ("refuse", True)


@pytest.mark.parametrize("env_class", [PROD, NONPROD])
def test_incident_check_that_raises_a_non_oserror_refuses(tmp_path, monkeypatch, env_class):
    root = _armed(tmp_path, monkeypatch)
    real = os.lstat

    def lstat(path, *args, **kwargs):
        if str(path).endswith(os.path.join(".crew", "incident.json")):
            raise RuntimeError("lstat exploded")
        return real(path, *args, **kwargs)

    monkeypatch.setattr(os, "lstat", lstat)

    got = _verdict(root, env_class)

    assert (got["verdict"], "RuntimeError" in got["reason"]) == ("refuse", True)


@pytest.mark.parametrize("env_class", [PROD, NONPROD])
def test_incident_path_that_cannot_be_found_refuses(tmp_path, monkeypatch, env_class):
    root = _armed(tmp_path, monkeypatch)

    def boom(*_args, **_kwargs):
        raise RuntimeError("toplevel exploded")

    monkeypatch.setattr(crew_autopilot.crew_ticket, "toplevel", boom)

    got = _verdict(root, env_class)

    assert (got["verdict"], "RuntimeError" in got["reason"]) == ("refuse", True)


@pytest.mark.parametrize("env_class", [PROD, NONPROD])
def test_incident_refuses_when_cloud_guard_import_fails(tmp_path, monkeypatch, env_class):
    root = _armed(tmp_path, monkeypatch)
    (tmp_path / "repo" / ".crew" / "incident.json").write_text("{}", encoding="utf-8")
    monkeypatch.setitem(sys.modules, "cloud_guard", None)

    got = _verdict(root, env_class)

    assert (got["verdict"], "emergency" in got["reason"]) == ("refuse", True)


def test_cloud_guard_import_failure_asks(tmp_path, monkeypatch):
    root = _armed(tmp_path, monkeypatch)
    monkeypatch.setitem(sys.modules, "cloud_guard", None)

    got = _verdict(root, PROD)

    assert (got["verdict"], "cloud_guard" in got["reason"]) == ("ask", True)


# --- review round 4: one root per answer ---------------------------------------

def _toplevel_returning(monkeypatch, *answers):
    """Patch `crew_ticket.toplevel` to return `answers` in turn (the last one
    repeated); returns the list of calls it saw."""
    calls = []

    def toplevel(root):
        calls.append(root)
        return answers[min(len(calls), len(answers)) - 1]

    monkeypatch.setattr(crew_autopilot.crew_ticket, "toplevel", toplevel)
    return calls


@pytest.mark.parametrize("env_class", [PROD, NONPROD])
def test_root_is_resolved_exactly_once(tmp_path, monkeypatch, env_class):
    root = _armed(tmp_path, monkeypatch)
    real = os.path.realpath(root)
    calls = _toplevel_returning(monkeypatch, real)

    got = _verdict(root, env_class)

    assert (len(calls), got["root"], got["verdict"]) == (1, real, "allow")


def test_root_swap_cannot_split_the_decision(tmp_path, monkeypatch):
    clean = _armed(tmp_path / "clean", monkeypatch)
    dirty = _armed(tmp_path / "dirty", monkeypatch)
    (tmp_path / "dirty" / "repo" / ".crew" / "incident.json").write_text("{}", encoding="utf-8")
    calls = _toplevel_returning(monkeypatch, clean, dirty)

    got = _verdict(clean, PROD)

    assert (got["verdict"], len(calls), got["root"]) == ("allow", 1, clean)


def test_root_swap_the_other_way_refuses(tmp_path, monkeypatch):
    clean = _armed(tmp_path / "clean", monkeypatch)
    dirty = _armed(tmp_path / "dirty", monkeypatch)
    (tmp_path / "dirty" / "repo" / ".crew" / "incident.json").write_text("{}", encoding="utf-8")
    _toplevel_returning(monkeypatch, dirty, clean)

    got = _verdict(clean, PROD)

    assert (got["verdict"], got["root"]) == ("refuse", dirty)


def test_machine_path_is_the_one_probed(tmp_path, monkeypatch):
    root = _armed(tmp_path, monkeypatch)
    real = crew_config.resolve_ratcheted
    seen = []

    def recorder(*args, **kwargs):
        # cloud_guard.resolve_mode reaches here too, through its own
        # environments_config (the spec's accepted risk): record crew_autopilot's.
        if sys._getframe(1).f_globals.get("__name__") == "crew_autopilot":  # pylint: disable=protected-access
            seen.append(kwargs.get("path"))
        return real(*args, **kwargs)

    monkeypatch.setattr(crew_config, "resolve_ratcheted", recorder)

    got = _verdict(root, PROD)

    assert (seen, got["verdict"]) == ([_machine_path(tmp_path)], "allow")


def test_outside_git_decides_from_abspath(tmp_path, monkeypatch):
    root = _armed(tmp_path, monkeypatch)
    _toplevel_returning(monkeypatch, None)

    got = _verdict(root, PROD)

    assert (got["root"], got["verdict"]) == (os.path.abspath(root), "allow")


@pytest.mark.parametrize("env_class", [PROD, NONPROD])
@pytest.mark.parametrize("error", [FileNotFoundError, NotADirectoryError, PermissionError,
                                   RuntimeError])
def test_checkout_lookup_that_raises_refuses(tmp_path, monkeypatch, error, env_class):
    root = _armed(tmp_path, monkeypatch)

    def toplevel(_root):
        raise error("lookup failed")

    monkeypatch.setattr(crew_autopilot.crew_ticket, "toplevel", toplevel)

    got = _verdict(root, env_class)

    assert (got["verdict"], error.__name__ in got["reason"]) == ("refuse", True)


@pytest.mark.parametrize("root", [None, 5, "a\x00b"], ids=["none", "int", "nul"])
def test_root_that_is_not_a_path_refuses(tmp_path, monkeypatch, root):
    _armed(tmp_path, monkeypatch)

    got = _verdict(root, PROD)

    assert got["verdict"] == "refuse"


# Review round 5: a bytes path is a valid path, but joining it with the str
# parts of the incident path raises before the probe runs; that asked instead
# of refusing. The checkout the decision judges is text, or it refuses.
@pytest.mark.parametrize("env_class", [PROD, NONPROD])
@pytest.mark.parametrize("case", ["bytes-root-outside-git", "bytes-root-toplevel-none",
                                  "str-root-toplevel-bytes"])
def test_root_that_is_not_text_refuses(tmp_path, monkeypatch, case, env_class):
    root = _armed(tmp_path, monkeypatch)
    if case == "bytes-root-outside-git":
        root = os.fsencode(str(tmp_path / "definitely-not-a-repo-t0072"))
    elif case == "bytes-root-toplevel-none":
        _toplevel_returning(monkeypatch, None)
        root = os.fsencode(root)
    else:
        _toplevel_returning(monkeypatch, os.fsencode(root))

    got = _verdict(root, env_class)

    assert (got["verdict"], "emergency" in got["reason"]) == ("refuse", True)


@pytest.mark.parametrize("env_class", [PROD, NONPROD])
def test_pathlike_root_is_decided(tmp_path, monkeypatch, env_class):
    """Round 5's neighbour: the text check refuses bytes, not every non-str
    argument - a `pathlib` root resolves to text and is decided."""
    _armed(tmp_path, monkeypatch)

    got = _verdict(tmp_path / "repo", env_class)

    assert (got["verdict"], isinstance(got["root"], str)) == ("allow", True)


# --- review round 4: every probe answers present, absent or could-not-tell ----

def _lstat_raising(error):
    def lstat(*_args, **_kwargs):
        raise error

    return lstat


@pytest.mark.parametrize("case", [
    "present", "absent-enoent", "absent-enotdir", "could-not-tell-permission",
    "could-not-tell-eloop", "could-not-tell-valueerror", "could-not-tell-runtimeerror",
    "present-join-is-not-the-probes"])
def test_probe_answers(tmp_path, monkeypatch, case):
    real_file = tmp_path / "file"
    real_file.write_text("x", encoding="utf-8")
    paths = {"present": real_file, "absent-enoent": tmp_path / "missing",
             "absent-enotdir": real_file / "under-a-file"}
    raised = {"could-not-tell-permission": PermissionError(errno.EACCES, "denied"),
              "could-not-tell-eloop": OSError(errno.ELOOP, "loop"),
              "could-not-tell-valueerror": ValueError("embedded null byte"),
              "could-not-tell-runtimeerror": RuntimeError("lstat exploded")}
    if case in raised:
        monkeypatch.setattr(os, "lstat", _lstat_raising(raised[case]))
    expected = {"present": ("present", ""), "absent-enoent": ("absent", ""),
                "absent-enotdir": ("absent", ""),
                "could-not-tell-permission": ("could-not-tell", "PermissionError"),
                "could-not-tell-eloop": ("could-not-tell", "OSError"),
                "could-not-tell-valueerror": ("could-not-tell", "ValueError"),
                "could-not-tell-runtimeerror": ("could-not-tell", "RuntimeError"),
                "present-join-is-not-the-probes": ("present", "")}[case]
    path = str(paths.get(case, real_file))

    # Round 5: the probe's try holds the stat alone. Building the path is the
    # caller's, so a join that raises is never the probe's "could-not-tell".
    with monkeypatch.context() as patch:
        if case == "present-join-is-not-the-probes":
            patch.setattr(os.path, "join", _lstat_raising(RuntimeError("join exploded")))
        got = crew_autopilot._probe(path)  # pylint: disable=protected-access

    assert got == expected


def _layer_path(tmp_path, root, layer):
    return (os.path.join(root, ".crew", "config.json") if layer == "repo"
            else _machine_path(tmp_path))


@pytest.mark.parametrize("env_class", [PROD, NONPROD])
@pytest.mark.parametrize("layer", ["repo", "machine"])
def test_layer_parent_unreadable_asks(tmp_path, monkeypatch, layer, env_class):
    root = _armed(tmp_path, monkeypatch)
    target = _layer_path(tmp_path, root, layer)
    real = os.lstat

    def lstat(path, *args, **kwargs):
        if os.fspath(path) == target:
            raise PermissionError(13, "Permission denied", target)
        return real(path, *args, **kwargs)

    monkeypatch.setattr(os, "lstat", lstat)

    got = _verdict(root, env_class)

    assert (got["verdict"], f"the {layer} config layer" in got["reason"],
            "PermissionError" in got["reason"], "guards.cloudGuard" in got["reason"]) == (
        "ask", True, True, False)


@pytest.mark.parametrize("env_class", [PROD, NONPROD])
@pytest.mark.parametrize("layer", ["repo", "machine"])
def test_layer_present_but_layer_state_says_absent_asks(tmp_path, monkeypatch, layer,
                                                        env_class):
    """Round 4's repro: `layer_state`'s `lexists` collapse (its `read_text`
    None and `os.path.lexists` False) calls a layer this module saw present
    `absent`; that must ask, never pass as unset. `layer_state` itself answers
    `absent` here: patching the `read_text` it reaches through `crew_state`
    is what test_module_split forbids."""
    root = _armed(tmp_path, monkeypatch)
    target = _layer_path(tmp_path, root, layer)
    real_state = crew_config.layer_state
    monkeypatch.setattr(crew_config, "layer_state", lambda path, *a, **k: (
        "absent" if os.fspath(path) == target else real_state(path, *a, **k)))

    got = _verdict(root, env_class)

    assert (got["verdict"], got["reason"]) == ("ask", f"could not read the {layer} config layer")


def test_layer_absent_is_permissive(tmp_path, monkeypatch):
    root = _armed(tmp_path, monkeypatch)
    os.remove(_machine_path(tmp_path))

    nonprod = _verdict(root, NONPROD, env="dev")
    prod = _verdict(root, PROD)

    assert (nonprod["verdict"], prod["verdict"],
            "not true in the machine config layer" in prod["reason"]) == ("allow", "ask", True)


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


class _Unprintable:
    """An environment name whose repr raises."""

    def __repr__(self):
        raise RuntimeError("no repr")


class _Uncomparable(str):
    """A class that is a `str` and raises on every comparison."""

    def __eq__(self, other):
        raise RuntimeError("no compare")

    __ne__ = __eq__
    __hash__ = str.__hash__


class _UnprintableError(RuntimeError):
    def __str__(self):
        raise ValueError("no str")


def test_env_name_repr_raises_asks(tmp_path, monkeypatch):
    root = _armed(tmp_path, monkeypatch)

    got = _verdict(root, PROD, env=_Unprintable())

    assert (got["verdict"], got["reason"]) == (
        "ask", "could not tell which environment: <unprintable _Unprintable>")


def test_env_name_repr_raises_reports(tmp_path, monkeypatch):
    root = _armed(tmp_path, monkeypatch)

    got = _verdict(root, PROD, env=_Unprintable())

    assert got["report"] == ("unattended production: <unprintable _Unprintable> ask - "
                             "could not tell which environment: <unprintable _Unprintable>")


def test_env_class_compare_raises_asks(tmp_path, monkeypatch):
    root = _armed(tmp_path, monkeypatch)

    got = _verdict(root, _Uncomparable("prod"))

    assert (got["verdict"], got["report"].startswith("unattended production: ")) == (
        "ask", True)


def test_exception_str_raises_asks(tmp_path, monkeypatch):
    root = _armed(tmp_path, monkeypatch)

    def boom(*_args, **_kwargs):
        raise _UnprintableError()

    monkeypatch.setattr(crew_config, "resolve_ratcheted", boom)

    got = _verdict(root, PROD)

    assert (got["verdict"], "_UnprintableError" in got["reason"]) == ("ask", True)


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


@pytest.mark.parametrize("value", ["All", "all ", "prod", "production", "NONPROD", True, 1])
def test_deploy_value_typo_reads_none(tmp_path, monkeypatch, value):
    root = _armed(tmp_path, monkeypatch, repo={"autopilot": {"deploy": value}})

    got = _verdict(root, NONPROD, env="dev")
    warned = [w for w in crew_autopilot.settings(root)["warnings"] if repr(value) in w]

    assert (got["verdict"], got["deploy"], len(warned)) == ("ask", "none", 1)


def test_deploy_null_in_the_repo_is_silent_and_reads_the_default(tmp_path, monkeypatch):
    """T-0050: a repo `null` is a silent layer, not a typo: the default `none`,
    with no warning to read."""
    root = _armed(tmp_path, monkeypatch, repo={"autopilot": {"deploy": None}})

    got = _verdict(root, NONPROD, env="dev")
    warned = [w for w in crew_autopilot.settings(root)["warnings"] if "deploy is None" in w]

    assert (got["verdict"], got["deploy"], warned) == ("ask", "none", [])


def test_deploy_only_in_machine_layer_is_the_default_since_t0050(tmp_path, monkeypatch):
    """T-0050 made `autopilot.deploy` personal: a machine value is the default
    for a repo that says nothing, and a repo value narrows it."""
    root = _armed(tmp_path, monkeypatch, repo={"autopilot": {"deploy": DROP}},
                  machine={"autopilot": {"deploy": "nonprod"}})

    got = _verdict(root, NONPROD, env="dev")

    assert (got["verdict"], got["deploy"]) == ("allow", "nonprod")


def test_repo_deploy_none_holds_a_machine_all_down(tmp_path, monkeypatch):
    root = _armed(tmp_path, monkeypatch, repo={"autopilot": {"deploy": "none"}},
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
        if (_is_malformed(repo) or _is_malformed(machine)) and got != "ask":
            wrong.append(("malformed", repo, machine, got, envs))
        if _is_malformed(repo) and not envs["problem"]:
            wrong.append(("problem", repo, machine, got, envs))
    assert wrong == []


def _problem_forms():
    """Every repo-layer input `environments_config` reports as a `problem`
    (`cloud_guard.py::environments_config`), each built on the armed repo."""
    armed = copy.deepcopy(ARMED_REPO)
    return {
        "unreadable": "directory",
        "bad-json": "{bad json",
        "non-object": "[]",
        "nonProd-not-a-list": json.dumps(_merge(armed, {"environments": {"nonProd": "dev"}})),
        "nonProd-blank": json.dumps(_merge(armed, {"environments": {"nonProd": [" "]}})),
        "prodUnattended-string": json.dumps(
            _merge(armed, {"environments": {"prodUnattended": "true"}})),
        "prodUnattended-null": json.dumps(
            _merge(armed, {"environments": {"prodUnattended": None}})),
    }


@pytest.mark.parametrize("env_class", [PROD, NONPROD])
@pytest.mark.parametrize("form", list(_problem_forms()))
def test_every_problem_fixture_reports_and_asks(tmp_path, monkeypatch, form, env_class):
    root = _armed(tmp_path, monkeypatch)
    _replace_file(os.path.join(root, ".crew", "config.json"), _problem_forms()[form])

    envs = cloud_guard.environments_config(root)
    got = _verdict(root, env_class, env="dev")

    assert (bool(envs["problem"]), got["verdict"]) == (True, "ask")


@pytest.mark.parametrize("env_class", [PROD, NONPROD])
@pytest.mark.parametrize("form", ["directory", "{bad json", "[]",
                                  json.dumps({"environments": {"prodUnattended": "true"}})])
def test_machine_problem_never_grants_and_asks(tmp_path, monkeypatch, form, env_class):
    root = _armed(tmp_path, monkeypatch)
    _replace_file(_machine_path(tmp_path), form)

    envs = cloud_guard.environments_config(root)
    got = _verdict(root, env_class, env="dev")

    assert (envs["prodUnattended"], got["verdict"]) == (False, "ask")


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
        0, "mode=plan maxPhases=12 deploy=all maxAutoReplans=0")


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


def _cli_prod(root, *extra):
    return crew_autopilot.main(["deploy-allowed", "--root", root, "--env", "production",
                                "--class", PROD, *extra])


def test_cli_crash_that_cannot_be_described_prints_ask(tmp_path, monkeypatch, capsys):
    """Round 4's repro: the exception's `__str__` raises inside the fallback."""
    root = _armed(tmp_path, monkeypatch)

    def boom(*_args, **_kwargs):
        raise _UnprintableError()

    monkeypatch.setattr(crew_autopilot, "deploy_allowed", boom)

    code = _cli_prod(root)
    out, err = capsys.readouterr()

    assert (code, len(out.splitlines()), out.startswith("verdict=ask "),
            len(err.splitlines()), err.startswith("unattended production: ")) == (
        0, 1, True, 1, True)


def test_cli_crash_whose_reason_cannot_be_built_prints_ask(tmp_path, monkeypatch, capsys):
    """Round 4's neighbour: describing the crash itself raises; stage 2 still
    prints the literal ask, with its constant reason."""
    root = _armed(tmp_path, monkeypatch)

    def boom(*_args, **_kwargs):
        raise RuntimeError("decision exploded")

    def no_reason(_exc):
        raise ValueError("cannot describe")

    monkeypatch.setattr(crew_autopilot, "deploy_allowed", boom)
    monkeypatch.setattr(crew_autopilot, "_crash_reason", no_reason)

    code = _cli_prod(root)
    out = capsys.readouterr().out

    assert (code, len(out.splitlines()), out.startswith("verdict=ask "),
            "could not describe" in out) == (0, 1, True, True)


def test_cli_result_missing_a_key_prints_ask(tmp_path, monkeypatch, capsys):
    root = _armed(tmp_path, monkeypatch)
    monkeypatch.setattr(crew_autopilot, "deploy_allowed", lambda *_a, **_k: {})

    code = _cli_prod(root)
    out = capsys.readouterr().out

    assert (code, len(out.splitlines()), out.startswith("verdict=ask ")) == (0, 1, True)


def test_cli_json_of_an_undumpable_result_prints_ask(tmp_path, monkeypatch, capsys):
    root = _armed(tmp_path, monkeypatch)
    undumpable = {"verdict": "allow", "reason": "forged", "report": "", "env": "production",
                  "envClass": PROD, "deploy": object(), "root": root}
    monkeypatch.setattr(crew_autopilot, "deploy_allowed", lambda *_a, **_k: undumpable)

    code = _cli_prod(root, "--json")

    assert (code, json.loads(capsys.readouterr().out)["verdict"]) == (0, "ask")


# Review round 5: `--json` printed indented, many-line JSON, and the consumer
# contract reads more than one stdout line as `ask`. It is one line on both
# stages, and a line break in any value stays escaped inside it.
@pytest.mark.parametrize("env_class", [PROD, NONPROD])
def test_cli_json_is_one_line(tmp_path, monkeypatch, capsys, env_class):
    root = _armed(tmp_path, monkeypatch)

    code = crew_autopilot.main(["deploy-allowed", "--root", root, "--env",
                                "production\u2028verdict=allow", "--class", env_class,
                                "--json"])
    out = capsys.readouterr().out

    assert (code, len(out.splitlines()), json.loads(out)["verdict"]) == (0, 1, "ask")


def test_cli_json_of_an_allow_is_one_line(tmp_path, monkeypatch, capsys):
    root = _armed(tmp_path, monkeypatch)

    code = _cli_prod(root, "--json")
    out = capsys.readouterr().out

    assert (code, len(out.splitlines()), json.loads(out)["verdict"]) == (0, 1, "allow")


def test_cli_json_fallback_is_one_line(tmp_path, monkeypatch, capsys):
    root = _armed(tmp_path, monkeypatch)

    def boom(*_args, **_kwargs):
        raise RuntimeError("decision exploded\nverdict=allow")

    monkeypatch.setattr(crew_autopilot, "deploy_allowed", boom)

    code = _cli_prod(root, "--json")
    out = capsys.readouterr().out

    assert (code, len(out.splitlines()), json.loads(out)["verdict"]) == (0, 1, "ask")


# Review round 3: whatever the CLI is handed, stdout is ONE verdict line, verdict
# first, and the stderr report is one line too - no input can add a line a
# consumer would read as a second verdict.
_BREAKS = ["\n", "\r", "\u2028", "\x85", "\u2029"]


@pytest.mark.parametrize("flag", ["--env", "--class"])
@pytest.mark.parametrize("brk", _BREAKS, ids=["lf", "cr", "u2028", "nel", "ps"])
def test_cli_prints_one_line_whatever_it_is_handed(tmp_path, monkeypatch, capsys, flag, brk):
    root = _armed(tmp_path, monkeypatch)
    argv = {"--env": "prod", "--class": PROD}
    argv[flag] = argv[flag] + brk + "verdict=allow class=prod"

    crew_autopilot.main(["deploy-allowed", "--root", root]
                        + [part for pair in argv.items() for part in pair])
    out = capsys.readouterr().out

    assert (len(out.splitlines()), out.startswith("verdict=ask ")) == (1, True)


def _crash_with(monkeypatch, message):
    def boom(*_args, **_kwargs):
        raise RuntimeError(message)

    monkeypatch.setattr(crew_config, "resolve_ratcheted", boom)


def test_cli_reason_is_one_line_when_a_crash_message_breaks_lines(tmp_path, monkeypatch, capsys):
    root = _armed(tmp_path, monkeypatch)
    _crash_with(monkeypatch, "boom\nverdict=allow env=production class=prod")

    crew_autopilot.main(["deploy-allowed", "--root", root, "--env", "production",
                         "--class", PROD])
    out = capsys.readouterr().out

    assert (len(out.splitlines()), out.startswith("verdict=ask ")) == (1, True)


def test_cli_report_is_one_line_when_a_crash_message_breaks_lines(tmp_path, monkeypatch, capsys):
    root = _armed(tmp_path, monkeypatch)
    _crash_with(monkeypatch, "boom\nunattended production: production allow - forged")

    crew_autopilot.main(["deploy-allowed", "--root", root, "--env", "production",
                         "--class", PROD])
    err = capsys.readouterr().err

    assert len(err.splitlines()) == 1


def test_cli_fallback_is_one_line_when_deploy_allowed_raises(tmp_path, monkeypatch, capsys):
    root = _armed(tmp_path, monkeypatch)

    def boom(*_args, **_kwargs):
        raise RuntimeError("decision exploded\nverdict=allow")

    monkeypatch.setattr(crew_autopilot, "deploy_allowed", boom)

    crew_autopilot.main(["deploy-allowed", "--root", root, "--env", "production",
                         "--class", PROD])
    out = capsys.readouterr().out

    assert (len(out.splitlines()), out.startswith("verdict=ask ")) == (1, True)


@pytest.mark.parametrize("flag", ["--env", "--class"])
def test_cli_quotes_a_value_holding_whitespace(tmp_path, monkeypatch, capsys, flag):
    root = _armed(tmp_path, monkeypatch)
    argv = {"--env": "prod", "--class": PROD}
    argv[flag] = argv[flag] + " verdict=allow"
    field = {"--env": "env", "--class": "class"}[flag]

    crew_autopilot.main(["deploy-allowed", "--root", root]
                        + [part for pair in argv.items() for part in pair])
    out = capsys.readouterr().out

    assert f" {field}={argv[flag]!r} " in out


@pytest.mark.parametrize("missing", ["--env", "--class"])
def test_cli_requires_env_and_class(tmp_path, monkeypatch, missing):
    root = _armed(tmp_path, monkeypatch)
    argv = {"--env": "production", "--class": PROD}
    argv.pop(missing)

    code = crew_autopilot.main(["deploy-allowed", "--root", root]
                               + [part for pair in argv.items() for part in pair])

    assert code == 2

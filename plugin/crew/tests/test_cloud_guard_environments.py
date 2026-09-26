"""T-0005: environment-scoped terraform apply, destroy and workspaces.

The must-block / must-allow suite CLAUDE.md requires for a change to a hook
that can block -- here, the LOOSENING the environment layer adds to
`guards.cloudGuard` (a non-destroying apply or workspace creation aimed at an
`environments.nonProd` target runs unattended under `terraformApply: ask`) and
the NEW refusal beside it (a destroy asks even under `terraformApply: allow`).

Every must-block case is built so that the value a bug would collapse to --
an unknown environment read as nonProd or as prod, a missing sidecar read as
"no deletes", a `cd` ignored -- would ALLOW. A case whose collapsed value also
denies is vacuous: its sabotage mutation cannot go red. The mutations live in
`sabotage_cloud.py`, each naming the case it must turn red.

Three drivers, as in `test_cloud_guard.py`: the python driver runs every case,
bash and pwsh a parity sample by default and the rest as `slow`. pwsh skips
where absent; native Windows is win-repo-2's.

Nothing here runs terraform. The plan files are a few bytes of fixture text;
the guard only hashes them and reads the sidecar JSON beside them.
"""
import copy
import hashlib
import json
import os
import re

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import crew_config
import crew_fixtures
import crew_state
import test_cloud_guard as tcg

import cloud_guard  # noqa: E402  pylint: disable=wrong-import-position

NONPROD = ["dev", "qa", "staging", "*-staging"]
BASE_REPO = {"guards": {"cloudGuard": "block", "terraformApply": "ask"},
             "environments": {"nonProd": NONPROD}}
BASE_GLOBAL = {"guards": {"terraformApply": "ask"}}
UNATTENDED = {"CREW_UNATTENDED": "1"}
PLAN = "p.tfplan"

# The environment variables the resolver reads from its own process as the
# last fallback. Cleared for every in-process test so the developer's shell
# cannot decide a case.
_TF_VARS = ("TF_WORKSPACE", "TF_VAR_environment", "TF_DATA_DIR")


@pytest.fixture(autouse=True)
def _no_ambient_terraform_env(monkeypatch):
    for name in _TF_VARS:
        monkeypatch.delenv(name, raising=False)


# --- fixture building -------------------------------------------------------


def _merge(base, over):
    out = copy.deepcopy(base)
    for key, value in (over or {}).items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _merge(out[key], value)
        else:
            out[key] = copy.deepcopy(value)
    return out


def _sidecar(repo, data, **fields):
    """A plan summary for `data`, as `crew_tfplan.py summarize` writes it."""
    body = {"plan": PLAN, "workspace": None, "environment": None,
            "deletes": [], "tool": "terraform", "created": 0}
    body.update(fields)
    digest = hashlib.sha256(data).hexdigest()
    folder = repo / ".crew" / "tfplan"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{digest}.json").write_text(json.dumps(body), encoding="utf-8")


def _build(tmp_path, opts):
    """The repo for one case. `opts`:

    repo/global     overrides merged over BASE_REPO/BASE_GLOBAL (`None` value
                    in `repo_env` replaces the whole `environments` block)
    plans           relative dirs holding an identical `p.tfplan` (default ["."])
    sidecar         dict of sidecar fields, or None for no sidecar
    stale           the sidecar describes earlier bytes of the plan
    wsfiles         {relative dir: workspace name} for `.terraform/environment`
    """
    repo_cfg = _merge(BASE_REPO, opts.get("repo"))
    if "environments" in opts:
        if opts["environments"] is None:
            repo_cfg.pop("environments", None)
        else:
            repo_cfg["environments"] = opts["environments"]
    global_cfg = _merge(BASE_GLOBAL, opts.get("global"))
    repo = tcg._fixture(tmp_path, repo_cfg, global_cfg)  # pylint: disable=protected-access
    data = f"plan bytes for {tmp_path.name}".encode("utf-8")
    for rel in opts.get("plans", ["."]):
        folder = repo / rel
        folder.mkdir(parents=True, exist_ok=True)
        (folder / PLAN).write_bytes(data)
    sidecar = opts.get("sidecar", {})
    if sidecar is not None:
        if opts.get("stale"):
            _sidecar(repo, b"the plan as it was when summarised", **sidecar)
        else:
            _sidecar(repo, data, **sidecar)
    for rel, name in opts.get("wsfiles", {}).items():
        folder = repo / rel / ".terraform"
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "environment").write_text(name, encoding="utf-8")
    for rel, body in opts.get("files", {}).items():
        path = repo / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(body)
    return repo


def _run(driver, tmp_path, case, env=None):
    _id, tool, command, opts = case
    repo = _build(tmp_path, opts)
    payload = None
    if opts.get("no_cwd"):
        payload = {"tool_name": tool, "tool_input": {"command": command}}
    for marked in opts.get("markers", ()):
        path = crew_config.guard_marker(str(repo), "terraformApply", marked)
        open(path, "w", encoding="utf-8").close()  # pylint: disable=consider-using-with
    result = tcg.run_hook(driver, tmp_path, tool, command,
                          extra_env=dict(env if env is not None else UNATTENDED),
                          payload=payload)
    return repo, result


def _log_rows(repo):
    path = repo / ".crew" / "guard.log"
    if not path.exists():
        return []
    return [line.split("\t") for line in
            path.read_text(encoding="utf-8").splitlines()]


# --- the cases --------------------------------------------------------------
#
# (id, tool, command, opts). Must-block: every one is DENIED unattended with a
# reason naming `[terraformApply]`, and `why` is a word the reason must carry
# (the environment or the destroy state).

TFW = "TF_WORKSPACE"
PU_BOTH = {"repo": {"environments": {"nonProd": NONPROD,
                                     "prodUnattended": True}},
           "global": {"environments": {"prodUnattended": True}}}


def _o(**kw):
    return kw


MUST_BLOCK_ENV = [
    ("prod-saved-plan", "Bash", f"{TFW}=production terraform apply {PLAN}",
     _o(sidecar={"workspace": "production"}, why="production")),
    ("prod-workspace-new", "Bash", "terraform workspace new production",
     _o(why="production")),
    ("prod-select-or-create", "Bash",
     "terraform workspace select -or-create production", _o(why="production")),
    # chdir ignored would read the ROOT's workspace file (staging) and the
    # identical root plan -- allowed. Read correctly it is production.
    ("prod-chdir-file", "Bash", f"terraform -chdir=infra apply {PLAN}",
     _o(plans=[".", "infra"], wsfiles={".": "staging", "infra": "production"},
        sidecar={"workspace": "staging"}, why="production")),
    ("prod-tofu", "Bash", f"{TFW}=production tofu apply {PLAN}",
     _o(sidecar={"workspace": "production"}, why="production")),
    # Two commands each (an assignment statement, a nested shell): a saved
    # plan is trusted only when the apply is the only command.
    ("prod-powershell", "PowerShell",
     f"$env:{TFW}='production'; terraform apply {PLAN}",
     _o(wsfiles={".": "staging"}, sidecar={"workspace": "staging"},
        why="rewrite")),
    ("prod-bash-c", "Bash", f"bash -c '{TFW}=production terraform apply {PLAN}'",
     _o(wsfiles={".": "staging"}, sidecar={"workspace": "staging"},
        why="rewrite")),
    ("prod-xargs", "Bash", "echo production | xargs terraform workspace new",
     _o(why="unknown")),
    ("prod-repo-only-unattended", "Bash",
     f"{TFW}=production terraform apply {PLAN}",
     _o(repo={"environments": {"nonProd": NONPROD, "prodUnattended": True}},
        sidecar={"workspace": "production"}, why="production")),
    # A string in the REPO layer is a malformed block (every environment
    # unknown), so the string sits in the global layer, where only the
    # normaliser stands between it and `true`.
    ("prod-unattended-string", "Bash",
     f"{TFW}=production terraform apply {PLAN}",
     _o(repo={"environments": {"nonProd": NONPROD, "prodUnattended": True}},
        global_={"environments": {"prodUnattended": "true"}},
        sidecar={"workspace": "production"}, why="production")),
    ("destroy-under-prod-unattended", "Bash",
     f"{TFW}=production terraform destroy -auto-approve",
     _o(pu=True, why="destroy")),
    ("nonprod-destroy", "Bash", f"{TFW}=staging terraform destroy -auto-approve",
     _o(why="destroy")),
    ("nonprod-apply-destroy-flag", "Bash",
     f"{TFW}=staging terraform apply -destroy {PLAN}",
     _o(sidecar={"workspace": "staging"}, why="destroy")),
    ("nonprod-replace", "Bash",
     f"{TFW}=staging terraform apply -replace=aws_instance.a {PLAN}",
     _o(sidecar={"workspace": "staging"}, why="destroy")),
    ("nonprod-plan-deletes", "Bash", f"{TFW}=staging terraform apply {PLAN}",
     _o(sidecar={"workspace": "staging", "deletes": ["aws_instance.a"]},
        why="aws_instance.a")),
    ("nonprod-no-sidecar", "Bash", f"{TFW}=staging terraform apply {PLAN}",
     _o(sidecar=None, why="no summary")),
    ("nonprod-stale-sidecar", "Bash", f"{TFW}=staging terraform apply {PLAN}",
     _o(sidecar={"workspace": "staging"}, stale=True, why="no summary")),
    # `deletes: null` read naively is falsy -- "nothing deleted".
    ("nonprod-malformed-sidecar", "Bash",
     f"{TFW}=staging terraform apply {PLAN}",
     _o(sidecar={"workspace": "staging", "deletes": None}, why="malformed")),
    ("nonprod-no-plan-apply", "Bash",
     f"{TFW}=staging terraform apply -auto-approve", _o(why="no saved plan")),
    ("nonprod-workspace-delete", "Bash", "terraform workspace delete qa",
     _o(why="destroy")),
    ("terragrunt-run-all", "Bash", f"{TFW}=staging terragrunt run-all apply",
     _o(why="terragrunt")),
    # No workspace file (not `default`), no signal in the sidecar: unknown.
    # `default` is listed nonProd and `prodUnattended` is on, so reading the
    # missing file as `default`, or the unknown as prod, would both allow.
    ("unknown-no-signal", "Bash", f"terraform apply {PLAN}",
     _o(repo={"environments": {"nonProd": NONPROD + ["default"],
                               "prodUnattended": True}},
        global_={"environments": {"prodUnattended": True}},
        sidecar={"workspace": "default"}, why="unknown")),
    ("unknown-variable", "Bash", f"{TFW}=$WS terraform apply {PLAN}",
     _o(wsfiles={".": "staging"}, sidecar={"workspace": "staging"},
        why="unknown")),
    ("unknown-variable-braces", "Bash", f"{TFW}=${{WS}} terraform apply {PLAN}",
     _o(wsfiles={".": "staging"}, sidecar={"workspace": "staging"},
        why="unknown")),
    ("unknown-conflict", "Bash", f"{TFW}=staging terraform apply {PLAN}",
     _o(pu=True, sidecar={"workspace": "staging",
                          "environment": "production"}, why="disagree")),
    # One command (env is unwrapped), so only the directory change stands
    # between the ROOT's clean staging plan and workspace file and an allow.
    ("unknown-cd", "Bash", f"env -C infra terraform apply {PLAN}",
     _o(plans=[".", "infra"], wsfiles={".": "staging"},
        sidecar={"workspace": "staging"}, why="unknown")),
    # With no payload cwd, the root (CLAUDE_PROJECT_DIR) holds a staging
    # workspace file and the plan: using it instead would allow.
    ("unknown-no-cwd", "Bash", f"terraform apply {PLAN}",
     _o(wsfiles={".": "staging"}, sidecar={"workspace": "staging"},
        no_cwd=True, why="cwd")),
    # The summary records the workspace the PLAN is bound to; null means
    # crew_tfplan could not read it, which is unknown, not absent.
    ("sidecar-unbound", "Bash", f"{TFW}=staging terraform apply {PLAN}",
     _o(wsfiles={".": "staging"}, sidecar={"workspace": None},
        why="bound")),
    ("unknown-malformed-block", "Bash",
     f"{TFW}=production terraform apply {PLAN}",
     _o(environments={"nonProd": "staging", "prodUnattended": True},
        global_={"environments": {"prodUnattended": True}},
        sidecar={"workspace": "production"}, why="environments")),
    ("block-not-loosened", "Bash", f"{TFW}=staging terraform apply {PLAN}",
     _o(repo={"guards": {"terraformApply": "block"}},
        global_={"guards": {"terraformApply": "block"}},
        sidecar={"workspace": "staging"}, why="block")),
]

# `terraformApply: allow` in both layers, environments at their defaults
# (absent), unattended: the BREAKING cases. Before 1.0.41 every one of these
# ran without a word.
ALLOW_POLICY = {"repo": {"guards": {"terraformApply": "allow"}},
                "global_": {"guards": {"terraformApply": "allow"}},
                "environments": None}
MUST_BLOCK_ALLOW_POLICY = [
    ("allow-destroy", "Bash", "terraform destroy -auto-approve",
     _o(**ALLOW_POLICY)),
    ("allow-apply-destroy-flag", "Bash", "terraform apply -destroy -auto-approve",
     _o(**ALLOW_POLICY)),
    ("allow-replace", "Bash",
     "terraform apply -replace=aws_instance.a -auto-approve",
     _o(**ALLOW_POLICY)),
    ("allow-no-plan-apply", "Bash", "terraform apply -auto-approve",
     _o(**ALLOW_POLICY)),
    ("allow-plan-deletes", "Bash", f"terraform apply {PLAN}",
     _o(sidecar={"deletes": ["aws_s3_bucket.logs"]}, **ALLOW_POLICY)),
    ("allow-workspace-delete", "Bash", "terraform workspace delete qa",
     _o(**{**ALLOW_POLICY, "environments": {"nonProd": ["dev"]}})),
]

# (id, tool, command, opts) with `log` naming the guard.log policy the allow
# must be recorded under.
MUST_ALLOW_ENV = [
    ("nonprod-saved-plan", "Bash", f"{TFW}=staging terraform apply {PLAN}",
     _o(sidecar={"workspace": "staging"}, log="env:nonProd:staging")),
    ("nonprod-file-workspace", "Bash", f"terraform apply {PLAN}",
     _o(sidecar={"workspace": "qa"}, wsfiles={".": "qa"},
        log="env:nonProd:qa")),
    ("nonprod-chdir", "Bash", f"terraform -chdir=infra apply {PLAN}",
     _o(plans=["infra"], sidecar={"workspace": "dev"},
        wsfiles={"infra": "dev"}, log="env:nonProd:dev")),
    ("nonprod-glob", "Bash", f"{TFW}=app-staging terraform apply {PLAN}",
     _o(sidecar={"workspace": "app-staging"}, log="env:nonProd:app-staging")),
    ("nonprod-workspace-new", "Bash", "terraform workspace new qa",
     _o(log="env:nonProd:qa")),
    ("nonprod-select-or-create", "Bash",
     "terraform workspace select -or-create=true dev",
     _o(log="env:nonProd:dev")),
    ("nonprod-powershell", "PowerShell", f"terraform apply {PLAN}",
     _o(sidecar={"workspace": "staging"}, wsfiles={".": "staging"},
        log="env:nonProd:staging")),
    ("nonprod-devnull", "Bash",
     f"{TFW}=staging terraform apply {PLAN} > /dev/null 2>&1",
     _o(sidecar={"workspace": "staging"}, log="env:nonProd:staging")),
    ("prod-unattended-both-layers", "Bash",
     f"{TFW}=production terraform apply {PLAN}",
     _o(pu=True, sidecar={"workspace": "production"},
        log="env:prod-unattended:production", said="production")),
    ("live-marker-prod", "Bash", f"{TFW}=production terraform apply {PLAN}",
     _o(sidecar={"workspace": "production"}, log="ask",
        markers=[f"terraform apply {PLAN}"])),
    ("live-marker-destroy-under-allow", "Bash",
     "terraform destroy -auto-approve",
     _o(log="allow", markers=["terraform destroy -auto-approve"],
        **ALLOW_POLICY)),
    ("allow-clean-saved-plan", "Bash", f"terraform apply {PLAN}",
     _o(log="allow", **ALLOW_POLICY)),
]

# Attended: the same stops ASK rather than deny.
ASK_ENV = [
    ("ask-prod-saved-plan", "Bash", f"{TFW}=production terraform apply {PLAN}",
     _o(sidecar={"workspace": "production"})),
    ("ask-nonprod-destroy", "Bash",
     f"{TFW}=staging terraform destroy -auto-approve", _o()),
    ("ask-unknown-env", "Bash", f"{TFW}=$WS terraform apply {PLAN}", _o()),
    ("ask-allow-destroy", "Bash", "terraform destroy -auto-approve",
     _o(**ALLOW_POLICY)),
]


def _normalise(cases):
    """`global_` is spelled with a trailing underscore above only because
    `global` is a keyword; `pu` is shorthand for prodUnattended in both
    layers."""
    out = []
    for case_id, tool, command, opts in cases:
        opts = dict(opts)
        if "global_" in opts:
            opts["global"] = opts.pop("global_")
        if opts.pop("pu", False):
            opts["repo"] = _merge(opts.get("repo") or {}, PU_BOTH["repo"])
            opts["global"] = _merge(opts.get("global") or {},
                                    PU_BOTH["global"])
        out.append((case_id, tool, command, opts))
    return out


MUST_BLOCK_ENV = _normalise(MUST_BLOCK_ENV)
MUST_BLOCK_ALLOW_POLICY = _normalise(MUST_BLOCK_ALLOW_POLICY)
MUST_ALLOW_ENV = _normalise(MUST_ALLOW_ENV)
ASK_ENV = _normalise(ASK_ENV)


def _ids(cases):
    return [c[0] for c in cases]


_B_SAMPLE = ("prod-saved-plan", "prod-powershell", "nonprod-plan-deletes",
             "unknown-no-signal")
_P_SAMPLE = ("allow-destroy", "allow-no-plan-apply")
_A_SAMPLE = ("nonprod-saved-plan", "nonprod-powershell",
             "prod-unattended-both-layers")


def _sample(cases, keep, marks):
    return crew_fixtures.parity_sample(cases, _ids(cases), keep, marks)


# --- the drivers -------------------------------------------------------------


def _deny(driver, tmp_path, case):
    _id, tool, _command, opts = case
    _repo, result = _run(driver, tmp_path, case)
    if tcg._stood_down(driver, tool, result):  # pylint: disable=protected-access
        return
    decision, reason, code, err = result
    assert code == 0, err
    assert decision == "deny", (case[0], decision, reason, err)
    assert "[terraformApply]" in reason, reason
    if opts.get("why"):
        assert opts["why"] in reason, (opts["why"], reason)


def _allow(driver, tmp_path, case):
    _id, tool, _command, opts = case
    repo, result = _run(driver, tmp_path, case)
    if tcg._stood_down(driver, tool, result):  # pylint: disable=protected-access
        return
    decision, said, code, err = result
    assert code == 0, err
    assert decision == "allow", (case[0], said, err)
    rows = [r for r in _log_rows(repo) if r[1] == "terraformApply"]
    assert rows, "an allow must leave a guard.log row"
    assert all(r[3] == "allow" for r in rows), rows
    assert any(r[2] == opts["log"] for r in rows), (opts["log"], rows)
    if opts.get("said"):
        assert opts["said"] in said, said
    else:
        assert not said, said


def _ask(driver, tmp_path, case):
    _id, tool, _command, _opts = case
    _repo, result = _run(driver, tmp_path, case, env={})
    if tcg._stood_down(driver, tool, result):  # pylint: disable=protected-access
        return
    decision, reason, code, err = result
    assert code == 0, err
    assert decision == "ask", (case[0], decision, reason, err)
    assert "[terraformApply]" in reason, reason


@pytest.mark.parametrize("case", MUST_BLOCK_ENV, ids=_ids(MUST_BLOCK_ENV))
def test_must_block_env_python(tmp_path, case):
    _deny("python", tmp_path, case)


@pytest.mark.parametrize("case", _sample(MUST_BLOCK_ENV, _B_SAMPLE,
                                         (tcg.needs_bash,)))
def test_must_block_env_bash(tmp_path, case):
    _deny("bash", tmp_path, case)


@pytest.mark.parametrize("case", _sample(MUST_BLOCK_ENV, _B_SAMPLE,
                                         (tcg.needs_pwsh,)))
def test_must_block_env_pwsh(tmp_path, case):
    _deny("pwsh", tmp_path, case)


@pytest.mark.parametrize("case", MUST_BLOCK_ALLOW_POLICY,
                         ids=_ids(MUST_BLOCK_ALLOW_POLICY))
def test_must_block_allow_policy_python(tmp_path, case):
    _deny("python", tmp_path, case)


@pytest.mark.parametrize("case", _sample(MUST_BLOCK_ALLOW_POLICY, _P_SAMPLE,
                                         (tcg.needs_bash,)))
def test_must_block_allow_policy_bash(tmp_path, case):
    _deny("bash", tmp_path, case)


@pytest.mark.parametrize("case", MUST_ALLOW_ENV, ids=_ids(MUST_ALLOW_ENV))
def test_must_allow_env_python(tmp_path, case):
    _allow("python", tmp_path, case)


@pytest.mark.parametrize("case", _sample(MUST_ALLOW_ENV, _A_SAMPLE,
                                         (tcg.needs_bash,)))
def test_must_allow_env_bash(tmp_path, case):
    _allow("bash", tmp_path, case)


@pytest.mark.parametrize("case", _sample(MUST_ALLOW_ENV, _A_SAMPLE,
                                         (tcg.needs_pwsh,)))
def test_must_allow_env_pwsh(tmp_path, case):
    _allow("pwsh", tmp_path, case)


@pytest.mark.parametrize("case", ASK_ENV, ids=_ids(ASK_ENV))
def test_ask_env_python(tmp_path, case):
    _ask("python", tmp_path, case)


def test_every_must_block_case_is_denied_for_the_reason_it_names():
    """The table's own shape: an id is never reused, and every must-block
    case names what its reason must carry."""
    ids = _ids(MUST_BLOCK_ENV + MUST_BLOCK_ALLOW_POLICY + MUST_ALLOW_ENV
               + ASK_ENV)
    assert len(ids) == len(set(ids))
    assert all(c[3].get("why") for c in MUST_BLOCK_ENV)
    assert all(c[3].get("log") for c in MUST_ALLOW_ENV)


# --- unchanged: environments at defaults -----------------------------------

_TF_WORDS = ("terraform", "tofu", "terragrunt")
_UNCHANGED_BLOCK = [c for c in tcg.MUST_BLOCK
                    if any(w in c[2] for w in _TF_WORDS)]
_UNCHANGED_ALLOW = [c for c in tcg.MUST_ALLOW
                    if any(w in c[2] for w in _TF_WORDS)]


@pytest.mark.parametrize("environments", [
    None, dict(crew_state.ENVIRONMENTS_DEFAULTS)], ids=["absent", "defaults"])
@pytest.mark.parametrize("case", _UNCHANGED_BLOCK,
                         ids=[c[0] for c in _UNCHANGED_BLOCK])
def test_unchanged_must_block_with_environments_at_defaults(tmp_path, case,
                                                            environments):
    _id, tool, command, rule = case
    cfg = dict(tcg.ARMED)
    if environments is not None:
        cfg["environments"] = environments
    tcg._fixture(tmp_path, cfg)  # pylint: disable=protected-access
    decision, reason, code, err = tcg.run_hook("python", tmp_path, tool,
                                               command)
    assert (decision, code) == ("deny", 0), (reason, err)
    assert f"[{rule}]" in reason, reason


@pytest.mark.parametrize("environments", [
    None, dict(crew_state.ENVIRONMENTS_DEFAULTS)], ids=["absent", "defaults"])
@pytest.mark.parametrize("case", _UNCHANGED_ALLOW,
                         ids=[c[0] for c in _UNCHANGED_ALLOW])
def test_unchanged_must_allow_with_environments_at_defaults(tmp_path, case,
                                                            environments):
    _id, tool, command = case
    cfg = dict(tcg.ARMED)
    if environments is not None:
        cfg["environments"] = environments
    tcg._fixture(tmp_path, cfg)  # pylint: disable=protected-access
    decision, reason, code, err = tcg.run_hook("python", tmp_path, tool,
                                               command)
    assert (decision, code) == ("allow", 0), (reason, err)


@pytest.mark.parametrize("environments", [
    None, dict(crew_state.ENVIRONMENTS_DEFAULTS)], ids=["absent", "defaults"])
def test_workspace_new_is_not_judged_until_environments_is_configured(
        tmp_path, environments):
    """At defaults the environment layer is not engaged, so `workspace new`
    yields no finding and no guard.log row -- exactly as before T-0005."""
    command = "terraform workspace new production"
    assert cloud_guard.scan("bash", command) == []
    cfg = {"guards": {"cloudGuard": "block"}}
    if environments is not None:
        cfg["environments"] = environments
    repo = tcg._fixture(tmp_path, cfg)  # pylint: disable=protected-access
    result = cloud_guard.evaluate(str(repo), "Bash", command,
                                  {"cwd": str(repo)})
    assert result["decision"] == "allow" and result["rows"] == [], result
    decision, reason, code, err = tcg.run_hook("python", tmp_path, "Bash",
                                               command, extra_env=UNATTENDED)
    assert (decision, code) == ("allow", 0), (reason, err)


@pytest.mark.parametrize("block", [{"nonProd": "staging"}, None, []],
                         ids=["nonprod-string", "null", "list"])
def test_a_malformed_environments_block_forces_block_mode(tmp_path, block):
    """`report` over a malformed block is not left as report: the layer is
    invalid, not unconfigured, and an armed guard fails closed."""
    tcg._fixture(tmp_path, {"guards": {"cloudGuard": "report"},  # pylint: disable=protected-access
                            "environments": block})
    mode, note = cloud_guard.resolve_mode(str(tmp_path / "repo"))
    assert mode == "block" and "environments" in note


def test_a_malformed_environments_block_leaves_an_unarmed_guard_off(tmp_path):
    tcg._fixture(tmp_path, {"environments": {"nonProd": "x"}})  # pylint: disable=protected-access
    assert cloud_guard.resolve_mode(str(tmp_path / "repo"))[0] == "off"


# --- the resolver, unit by unit --------------------------------------------


def _finding(shell, command, engaged=True):
    ctx = {"cd": False, "switch": False, "engaged": engaged}
    found = [f for f in cloud_guard.scan(shell, command, ctx=ctx) if f.scope]
    assert found, (command, "no terraform finding")
    return found[-1], ctx


def _files(root, files):
    for rel, text in (files or {}).items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(text, bytes):
            path.write_bytes(text)
        else:
            path.write_text(text, encoding="utf-8")


WSF = ".terraform/environment"

# (id, shell, command, files, sidecar, want class, want value)
RESOLVE = [
    ("w-inline", "bash", f"{TFW}=staging terraform apply {PLAN}", {}, None,
     "nonProd", "staging"),
    ("w-env-prefix", "bash", f"env {TFW}=qa terraform apply {PLAN}", {}, None,
     "nonProd", "qa"),
    ("w-export", "bash", f"export {TFW}=production; terraform apply {PLAN}",
     {}, None, "prod", "production"),
    ("w-local-var-substituted", "bash",
     f"WS=qa; {TFW}=$WS terraform apply {PLAN}", {}, None, "nonProd", "qa"),
    ("w-select-in-sequence", "bash",
     f"terraform workspace select qa && terraform apply {PLAN}",
     {WSF: "production"}, None, "nonProd", "qa"),
    ("w-new-in-sequence", "bash",
     f"terraform workspace new dev; terraform apply {PLAN}", {}, None,
     "nonProd", "dev"),
    ("w-switch-after-disables-file", "bash",
     f"terraform apply {PLAN}; terraform workspace select production",
     {WSF: "staging"}, None, "unknown", None),
    ("w-file", "bash", f"terraform apply {PLAN}", {WSF: "staging\n"}, None,
     "nonProd", "staging"),
    ("w-file-missing-is-not-default", "bash", f"terraform apply {PLAN}", {},
     None, "unknown", None),
    ("w-chdir-data-dir", "bash",
     f"TF_DATA_DIR=.tfdata terraform -chdir=infra apply {PLAN}",
     {"infra/.tfdata/environment": "qa"}, None, "nonProd", "qa"),
    ("w-data-dir-not-literal", "bash",
     f"TF_DATA_DIR=$D terraform apply {PLAN}", {WSF: "qa"}, None,
     "unknown", None),
    ("v-var-agrees", "bash",
     "terraform apply -var environment=staging -auto-approve", {WSF: "staging"},
     None, "nonProd", "staging"),
    ("v-var-equals-conflicts", "bash",
     "terraform apply -var=environment=production -auto-approve",
     {WSF: "staging"}, None, "unknown", None),
    ("v-var-last-wins", "bash",
     "terraform apply -var environment=production -var environment=qa",
     {WSF: "qa"}, None, "nonProd", "qa"),
    ("v-tf-var-env", "bash", "TF_VAR_environment=prod terraform apply",
     {WSF: "production"}, None, "prod", "production"),
    ("v-var-not-literal", "bash", "terraform apply -var environment=$E",
     {WSF: "qa"}, None, "unknown", None),
    ("p-sidecar-agrees", "bash", f"terraform apply {PLAN}", {WSF: "qa"},
     {"workspace": "qa", "environment": "qa"}, "nonProd", "qa"),
    ("p-sidecar-conflicts", "bash", f"terraform apply {PLAN}",
     {WSF: "staging"}, {"workspace": None, "environment": "production"},
     "unknown", None),
    ("agreeing-nonprod-names", "bash", f"{TFW}=staging terraform apply {PLAN}",
     {}, {"workspace": "staging", "environment": "dev"}, "nonProd", "staging"),
    ("two-prod-names", "bash", f"{TFW}=production terraform apply {PLAN}", {},
     {"workspace": "production", "environment": "prod-eu"}, "prod",
     "production"),
    ("var-dollar", "bash", f"{TFW}=$WS terraform apply {PLAN}", {WSF: "qa"},
     None, "unknown", None),
    ("var-braces", "bash", f"{TFW}=${{WS}} terraform apply {PLAN}",
     {WSF: "qa"}, None, "unknown", None),
    ("cd-with-workspace-file", "bash", f"cd infra && terraform apply {PLAN}",
     {WSF: "qa"}, None, "unknown", None),
    ("pushd-subshell", "bash", f"(pushd infra; terraform apply {PLAN})",
     {WSF: "qa"}, None, "unknown", None),
    ("env-chdir-wrapper", "bash", f"env -C infra terraform apply {PLAN}",
     {WSF: "qa"}, None, "unknown", None),
    ("powershell-env", "powershell",
     f"$env:{TFW}='qa'; terraform apply {PLAN}", {}, None, "nonProd", "qa"),
    ("powershell-set-location", "powershell",
     f"Set-Location infra; terraform apply {PLAN}", {WSF: "qa"}, None,
     "unknown", None),
    ("bash-c-nesting", "bash", f"bash -c '{TFW}=qa terraform apply {PLAN}'",
     {}, None, "nonProd", "qa"),
    ("tofu", "bash", f"{TFW}=qa tofu apply {PLAN}", {}, None, "nonProd", "qa"),
    ("terragrunt", "bash", f"{TFW}=qa terragrunt apply", {}, None,
     "unknown", None),
    ("xargs-fed", "bash", f"echo {PLAN} | xargs terraform apply", {WSF: "qa"},
     None, "unknown", None),
    ("ssh-remote", "bash", f"ssh ops 'terraform apply {PLAN}'", {WSF: "qa"},
     None, "unknown", None),
    ("workspace-new-name", "bash", "terraform workspace new app-staging", {},
     None, "nonProd", "app-staging"),
    ("workspace-new-not-literal", "bash", "terraform workspace new $NAME", {},
     None, "unknown", None),
    ("workspace-new-no-name", "bash", "terraform workspace new", {}, None,
     "unknown", None),
]


@pytest.mark.parametrize("case", RESOLVE, ids=[c[0] for c in RESOLVE])
def test_resolve_environment(tmp_path, case):
    _id, shell, command, files, sidecar, want, value = case
    _files(tmp_path, files)
    finding, ctx = _finding(shell, command)
    cfg = {"nonProd": NONPROD, "problem": ""}
    got = cloud_guard._tf_environment(finding.scope, str(tmp_path), ctx, cfg,  # pylint: disable=protected-access
                                      sidecar)
    assert got[:2] == (want, value), got
    if want == "unknown":
        assert got[2], "an unknown must say what crew could not tell"


def test_resolve_environment_from_the_hooks_own_environment(tmp_path,
                                                            monkeypatch):
    monkeypatch.setenv(TFW, "dev")
    finding, ctx = _finding("bash", f"terraform apply {PLAN}")
    got = cloud_guard._tf_environment(finding.scope, str(tmp_path), ctx,  # pylint: disable=protected-access
                                      {"nonProd": NONPROD, "problem": ""})
    assert got[:2] == ("nonProd", "dev")


def test_resolve_environment_without_a_payload_cwd(tmp_path):
    _files(tmp_path, {WSF: "qa"})
    finding, ctx = _finding("bash", f"terraform apply {PLAN}")
    got = cloud_guard._tf_environment(finding.scope, None, ctx,  # pylint: disable=protected-access
                                      {"nonProd": NONPROD, "problem": ""})
    assert got[0] == "unknown" and "cwd" in got[2]


def test_resolve_environment_under_an_unreadable_block(tmp_path):
    finding, ctx = _finding("bash", f"{TFW}=qa terraform apply {PLAN}")
    got = cloud_guard._tf_environment(finding.scope, str(tmp_path), ctx,  # pylint: disable=protected-access
                                      {"nonProd": [], "problem": "bad"})
    assert got[0] == "unknown"


_DATA = b"saved plan bytes"


def _plan_root(tmp_path, sidecar=None, data=_DATA, name=PLAN):
    """A root with `name` holding `data` and, unless None, a sidecar."""
    (tmp_path / ".crew").mkdir(exist_ok=True)
    (tmp_path / name).write_bytes(data)
    if sidecar is not None:
        digest = hashlib.sha256(data).hexdigest()
        folder = tmp_path / ".crew" / "tfplan"
        folder.mkdir(parents=True, exist_ok=True)
        text = sidecar if isinstance(sidecar, str) else json.dumps(sidecar)
        (folder / f"{digest}.json").write_text(text, encoding="utf-8")


_CLEAN = {"plan": PLAN, "workspace": "qa", "environment": None, "deletes": []}

# (id, command, sidecar, want)
DESTROY = [
    ("destroy", "terraform destroy -auto-approve", _CLEAN, "yes"),
    ("apply-destroy-flag", f"terraform apply -destroy {PLAN}", _CLEAN, "yes"),
    ("apply-replace-equals", f"terraform apply -replace=a.b {PLAN}", _CLEAN,
     "yes"),
    ("apply-replace-space", "terraform apply -replace a.b", None, "yes"),
    ("run-all-destroy", "terragrunt run-all destroy", None, "yes"),
    ("workspace-delete", "terraform workspace delete qa", None, "yes"),
    ("plan-deletes", f"terraform apply {PLAN}",
     dict(_CLEAN, deletes=["aws_instance.a"]), "yes"),
    ("no-plan", "terraform apply -auto-approve", None, "unknown"),
    ("run-all-apply", "terragrunt run-all apply", None, "unknown"),
    ("terragrunt-apply", "terragrunt apply", None, "unknown"),
    ("no-sidecar", f"terraform apply {PLAN}", None, "unknown"),
    ("deletes-not-a-list", f"terraform apply {PLAN}",
     dict(_CLEAN, deletes="aws_instance.a"), "unknown"),
    ("deletes-null", f"terraform apply {PLAN}", dict(_CLEAN, deletes=None),
     "unknown"),
    ("deletes-not-strings", f"terraform apply {PLAN}",
     dict(_CLEAN, deletes=[1]), "unknown"),
    ("sidecar-not-object", f"terraform apply {PLAN}", "[]", "unknown"),
    ("sidecar-not-json", f"terraform apply {PLAN}", "{nope", "unknown"),
    ("plan-not-literal", "terraform apply $PLAN", _CLEAN, "unknown"),
    ("two-operands", f"terraform apply {PLAN} other.tfplan", _CLEAN,
     "unknown"),
    ("plan-missing", "terraform apply missing.tfplan", _CLEAN, "unknown"),
    ("fed-apply", f"echo {PLAN} | xargs terraform apply", _CLEAN, "unknown"),
    ("clean-plan", f"terraform apply {PLAN}", _CLEAN, "no"),
    ("clean-plan-with-var-file", f"terraform apply -lock-timeout 5s {PLAN}",
     _CLEAN, "no"),
    ("workspace-new", "terraform workspace new qa", None, "no"),
    ("select-or-create", "terraform workspace select -or-create qa", None,
     "no"),
]


@pytest.mark.parametrize("case", DESTROY, ids=[c[0] for c in DESTROY])
def test_destroy_state(tmp_path, case):
    _id, command, sidecar, want = case
    _plan_root(tmp_path, sidecar)
    finding, ctx = _finding("bash", command)
    got = cloud_guard._tf_destroy(finding.scope, str(tmp_path), str(tmp_path),  # pylint: disable=protected-access
                                  ctx)
    assert got[0] == want, got
    if want != "no":
        assert got[1], "a destroy state must say why"


def test_destroy_state_for_a_sidecar_of_other_bytes(tmp_path):
    """Stale: the summary describes the plan as it was; the plan changed."""
    _plan_root(tmp_path, _CLEAN, data=b"before")
    (tmp_path / PLAN).write_bytes(b"after")
    finding, ctx = _finding("bash", f"terraform apply {PLAN}")
    got = cloud_guard._tf_destroy(finding.scope, str(tmp_path), str(tmp_path),  # pylint: disable=protected-access
                                  ctx)
    assert got[0] == "unknown" and "no summary" in got[1]


def test_destroy_state_for_an_unreadable_sidecar(tmp_path):
    _plan_root(tmp_path)
    digest = hashlib.sha256(_DATA).hexdigest()
    (tmp_path / ".crew" / "tfplan" / f"{digest}.json").mkdir(parents=True)
    finding, ctx = _finding("bash", f"terraform apply {PLAN}")
    got = cloud_guard._tf_destroy(finding.scope, str(tmp_path), str(tmp_path),  # pylint: disable=protected-access
                                  ctx)
    assert got[0] == "unknown"


def test_destroy_state_for_a_plan_over_64_mib(tmp_path):
    """A sparse file: the size is what is checked, before any byte is read,
    so a sidecar for its (zero) bytes never gets the chance to vouch."""
    (tmp_path / ".crew").mkdir()
    with open(tmp_path / PLAN, "wb") as handle:
        handle.truncate(cloud_guard.PLAN_MAX_BYTES + 1)
    digest = hashlib.sha256(b"\0" * (cloud_guard.PLAN_MAX_BYTES + 1)).hexdigest()
    folder = tmp_path / ".crew" / "tfplan"
    folder.mkdir(parents=True)
    (folder / f"{digest}.json").write_text(json.dumps(_CLEAN), encoding="utf-8")
    finding, ctx = _finding("bash", f"terraform apply {PLAN}")
    got = cloud_guard._tf_destroy(finding.scope, str(tmp_path), str(tmp_path),  # pylint: disable=protected-access
                                  ctx)
    assert got[0] == "unknown" and "64 MiB" in got[1]


def test_destroy_state_after_a_cd(tmp_path):
    _plan_root(tmp_path, _CLEAN)
    finding, ctx = _finding("bash", f"cd . && terraform apply {PLAN}")
    got = cloud_guard._tf_destroy(finding.scope, str(tmp_path), str(tmp_path),  # pylint: disable=protected-access
                                  ctx)
    assert got[0] == "unknown"


def test_the_hook_reads_only_the_plan_and_the_sidecar(tmp_path, monkeypatch):
    """No subprocess: `terraform show` does not fit a 15-second hook, and
    running terraform at all is not the hook's job."""
    import subprocess  # pylint: disable=import-outside-toplevel

    def refuse(*_a, **_k):
        raise AssertionError("the hook must never start a process")

    monkeypatch.setattr(subprocess, "run", refuse)
    monkeypatch.setattr(subprocess, "Popen", refuse)
    _plan_root(tmp_path, _CLEAN)
    finding, ctx = _finding("bash", f"terraform apply {PLAN}")
    assert cloud_guard._tf_destroy(finding.scope, str(tmp_path),  # pylint: disable=protected-access
                                   str(tmp_path), ctx)[0] == "no"
    assert os.path.isfile(tmp_path / PLAN)


# --- review round 1 (T-0005-Wajyct): six measured bypasses -----------------
#
# Each table below is the reviewer's reproduction, turned into must-block
# cases. The fixture is always the one the bypass needed: a CLEAN staging
# plan and summary where the hook looks, so a guard that looks in the wrong
# place, or at the plan before the command rewrites it, allows.

# BLOCK :1222. The hook hashes the plan when it runs, before the command
# does, so anything else in the command may replace the plan or its summary
# first. A saved plan is trusted only when the apply is the ONLY command in
# the invocation and nothing redirects output anywhere but /dev/null.
REWRITE = _normalise([
    ("rewrite-plan-destroy", "Bash",
     f"{TFW}=staging terraform plan -destroy -out {PLAN} && "
     f"{TFW}=staging terraform apply {PLAN}",
     _o(sidecar={"workspace": "staging"}, why="rewrite")),
    ("rewrite-cp", "Bash",
     f"cp other.tfplan {PLAN} && {TFW}=staging terraform apply {PLAN}",
     _o(sidecar={"workspace": "staging"}, why="rewrite")),
    ("rewrite-documented-flow", "Bash",
     f"terraform plan -out {PLAN} && python3 crew_tfplan.py summarize {PLAN}"
     f" && {TFW}=staging terraform apply {PLAN}",
     _o(sidecar={"workspace": "staging"}, why="rewrite")),
    ("rewrite-mv-semicolon", "Bash",
     f"mv new.tfplan {PLAN}; {TFW}=staging terraform apply {PLAN}",
     _o(sidecar={"workspace": "staging"}, why="rewrite")),
    ("rewrite-background", "Bash",
     f"cp other.tfplan {PLAN} & {TFW}=staging terraform apply {PLAN}",
     _o(sidecar={"workspace": "staging"}, why="rewrite")),
    ("rewrite-select-then-apply", "Bash",
     f"terraform workspace select staging && terraform apply {PLAN}",
     _o(sidecar={"workspace": "staging"}, why="rewrite")),
    ("rewrite-redirect-append", "Bash",
     f"{TFW}=staging terraform apply {PLAN} >> {PLAN}",
     _o(sidecar={"workspace": "staging"}, why="rewrite")),
    ("rewrite-redirect-stderr", "Bash",
     f"{TFW}=staging terraform apply {PLAN} 2> {PLAN}",
     _o(sidecar={"workspace": "staging"}, why="rewrite")),
    ("rewrite-ps-copy", "PowerShell",
     f"Copy-Item other.tfplan {PLAN}; terraform apply {PLAN}",
     _o(sidecar={"workspace": "staging"}, wsfiles={".": "staging"},
        why="rewrite")),
    ("rewrite-ps-redirect", "PowerShell", f"terraform apply {PLAN} > {PLAN}",
     _o(sidecar={"workspace": "staging"}, wsfiles={".": "staging"},
        why="rewrite")),
    ("rewrite-redirect-only", "Bash",
     f"> {PLAN}; {TFW}=staging terraform apply {PLAN}",
     _o(sidecar={"workspace": "staging"}, why="rewrite")),
    ("rewrite-redirect-both", "Bash",
     f"{TFW}=staging terraform apply {PLAN} >&{PLAN}",
     _o(sidecar={"workspace": "staging"}, why="rewrite")),
    ("rewrite-subshell", "Bash",
     f"(cp other.tfplan {PLAN}); {TFW}=staging terraform apply {PLAN}",
     _o(sidecar={"workspace": "staging"}, why="rewrite")),
])

# BLOCK :841 / :1514. A directory change terraform runs under but the hook
# did not see. Root: clean staging plan, summary and workspace file. infra/:
# a different plan the hook never summarised. Only the unwrapped wrappers are
# here -- `wsl` and `pwsh` run a second command, which the rewrite rule
# already refuses; their directory change is proved by `CHDIR_FORMS` below.
_CHDIR_FIXTURE = _o(sidecar={"workspace": "staging"},
                    wsfiles={".": "staging"},
                    files={f"infra/{PLAN}": b"a production destroy plan"},
                    why="unknown")
CHDIR_E2E = _normalise([
    (case_id, "Bash", f"{prefix} terraform apply {PLAN}", dict(_CHDIR_FIXTURE))
    for case_id, prefix in (
        ("env-chdir-equals", "env --chdir=infra"),
        ("env-chdir-space", "env --chdir infra"),
        ("env-C-attached", "env -Cinfra"),
        ("env-C-space", "env -C infra"),
        ("env-cluster", "env -iCinfra"),
        ("env-long-abbrev", "env --ch=infra"),
        ("sudo-D-attached", "sudo -Dinfra"),
        ("sudo-D-space", "sudo -D infra"),
        ("sudo-chdir-equals", "sudo --chdir=infra"),
        ("sudo-chdir-space", "sudo --chdir infra"),
        ("sudo-cluster", "sudo -EDinfra"),
        ("sudo-chroot", "sudo -R /jail"),
        ("sudo-env-chdir", "sudo env --chdir=infra"),
    )])

# FIX crew_tfplan.py:103, hook side. A TF_WORKSPACE the hook cannot read.
OPAQUE_E2E = _normalise([
    ("source-env-file", "Bash", f"source prod.env && terraform apply {PLAN}",
     _o(sidecar={"workspace": "staging"}, wsfiles={".": "staging"},
        why="unknown")),
    ("ps-set-item-env", "PowerShell",
     f"Set-Item env:{TFW} production; terraform apply {PLAN}",
     _o(sidecar={"workspace": "staging"}, wsfiles={".": "staging"},
        why="unknown")),
    ("or-chain", "Bash",
     f"terraform workspace select staging || terraform apply {PLAN}",
     _o(sidecar={"workspace": "staging"}, wsfiles={".": "staging"},
        why="unknown")),
])

# FIX :1535. `workspace delete` is a destroy in every armed state, with the
# environment layer off (no `environments` block at all).
_DEFAULTS_BLOCK = _o(environments=None,
                     repo={"guards": {"terraformApply": "block"}},
                     global_={"guards": {"terraformApply": "block"}},
                     why="block")
_DEFAULTS_ASK = _o(environments=None, why="destroy")
_DEFAULTS_ALLOW = _o(why="destroy", **ALLOW_POLICY)
WS_DELETE_DEFAULTS = _normalise([
    ("delete-block", "Bash", "terraform workspace delete -force production",
     dict(_DEFAULTS_BLOCK)),
    ("delete-ask", "Bash", "terraform workspace delete -force production",
     dict(_DEFAULTS_ASK)),
    ("delete-allow", "Bash", "terraform workspace delete -force production",
     dict(_DEFAULTS_ALLOW)),
    ("delete-tofu-allow", "Bash", "tofu workspace delete qa",
     dict(_DEFAULTS_ALLOW)),
    ("delete-bash-c-allow", "Bash",
     "bash -c 'terraform workspace delete production'", dict(_DEFAULTS_ALLOW)),
    ("delete-ps-allow", "PowerShell", "terraform workspace delete production",
     dict(_DEFAULTS_ALLOW)),
    ("delete-xargs-allow", "Bash",
     "echo production | xargs terraform workspace delete",
     dict(_DEFAULTS_ALLOW)),
    ("delete-xargs-sub-hidden", "Bash",
     "echo delete production | xargs terraform workspace",
     dict(_DEFAULTS_ALLOW)),
])

_ROUND1 = REWRITE + CHDIR_E2E + OPAQUE_E2E + WS_DELETE_DEFAULTS


@pytest.mark.parametrize("case", _ROUND1, ids=_ids(_ROUND1))
def test_round1_must_block_python(tmp_path, case):
    _deny("python", tmp_path, case)


@pytest.mark.parametrize("case", _sample(
    _ROUND1, ("rewrite-plan-destroy", "rewrite-ps-copy", "env-chdir-equals",
              "delete-allow"), (tcg.needs_bash,)))
def test_round1_must_block_bash(tmp_path, case):
    _deny("bash", tmp_path, case)


@pytest.mark.parametrize("case", _sample(
    _ROUND1, ("rewrite-ps-copy", "ps-set-item-env", "delete-ps-allow"),
    (tcg.needs_pwsh,)))
def test_round1_must_block_pwsh(tmp_path, case):
    _deny("pwsh", tmp_path, case)


@pytest.mark.parametrize("command", [
    "terraform workspace new production",
    "terraform workspace select -or-create production"])
def test_workspace_creation_stays_unjudged_at_defaults(tmp_path, command):
    """The delete fix does not drag creation in: with the layer off,
    creating a workspace is not a finding, as before T-0005."""
    tcg._fixture(tmp_path, {"guards": {"cloudGuard": "block"}})  # pylint: disable=protected-access
    decision, reason, code, err = tcg.run_hook("python", tmp_path, "Bash",
                                               command, extra_env=UNATTENDED)
    assert (decision, code) == ("allow", 0), (reason, err)


# Every spelling that moves terraform's working directory marks the command
# as having changed directory -- the unwrapped wrappers above and the ones
# that start a second shell. The negatives keep the rule from firing on a
# wrapper option that does not move anything.
CHDIR_FORMS = [
    ("bash", "env --chdir=infra terraform apply p.tfplan", True),
    ("bash", "env --chdir infra terraform apply p.tfplan", True),
    ("bash", "env -Cinfra terraform apply p.tfplan", True),
    ("bash", "env -C infra terraform apply p.tfplan", True),
    ("bash", "env -iCinfra terraform apply p.tfplan", True),
    ("bash", "env --ch=infra terraform apply p.tfplan", True),
    ("bash", "sudo -Dinfra terraform apply p.tfplan", True),
    ("bash", "sudo -D infra terraform apply p.tfplan", True),
    ("bash", "sudo --chdir=infra terraform apply p.tfplan", True),
    ("bash", "sudo --chdir infra terraform apply p.tfplan", True),
    ("bash", "sudo -EDinfra terraform apply p.tfplan", True),
    ("bash", "sudo -R /jail terraform apply p.tfplan", True),
    ("bash", "sudo --chroot=/jail terraform apply p.tfplan", True),
    ("bash", "wsl --cd infra terraform apply p.tfplan", True),
    ("bash", "wsl --cd=infra terraform apply p.tfplan", True),
    ("bash", "wsl ~ terraform apply p.tfplan", True),
    ("bash", "pwsh -WorkingDirectory infra -Command 'terraform apply p.tfplan'",
     True),
    ("bash", "powershell -wd infra -c 'terraform apply p.tfplan'", True),
    ("powershell", "pwsh -wd infra -c 'terraform apply p.tfplan'", True),
    ("powershell", "pwsh -work infra -c 'terraform apply p.tfplan'", True),
    ("bash", "parallel --wd infra terraform apply ::: p.tfplan", True),
    ("bash", "parallel --workdir=infra terraform apply ::: p.tfplan", True),
    ("bash", "cd infra && terraform apply p.tfplan", True),
    ("bash", "pushd infra; terraform apply p.tfplan", True),
    ("bash", "source env.sh; terraform apply p.tfplan", True),
    ("bash", ". ./env.sh && terraform apply p.tfplan", True),
    ("powershell", "Set-Location infra; terraform apply p.tfplan", True),
    ("powershell", "Push-Location infra; terraform apply p.tfplan", True),
    ("powershell", "sl infra; terraform apply p.tfplan", True),
    ("powershell",
     "[IO.Directory]::SetCurrentDirectory('infra'); terraform apply p.tfplan",
     True),
    ("powershell",
     "[Environment]::CurrentDirectory = 'infra'; terraform apply p.tfplan",
     True),
    ("bash", "ssh ops 'terraform apply p.tfplan'", True),
    # A PowerShell script runs in the caller's session: its Set-Location
    # moves the caller too.
    ("powershell", "./setup.ps1; terraform apply p.tfplan", True),
    ("powershell", "& ./setup.ps1; terraform apply p.tfplan", True),
    ("bash", "env TF_LOG=1 terraform apply p.tfplan", False),
    ("bash", "env -u AWS_PROFILE terraform apply p.tfplan", False),
    ("bash", "sudo -u deploy terraform apply p.tfplan", False),
    ("bash", "sudo -E terraform apply p.tfplan", False),
    ("bash", "wsl -e terraform apply p.tfplan", False),
    ("bash", "pwsh -NoProfile -c 'terraform apply p.tfplan'", False),
    ("bash", "terraform -chdir=infra apply p.tfplan", False),
]


def _slug_ids(commands):
    """Readable, unique ids from command text (pytest node ids that a
    sabotage entry can name without shell metacharacters in them)."""
    out = []
    for command in commands:
        slug = re.sub(r"[^A-Za-z0-9]+", "-", command).strip("-")[:44]
        while slug in out:
            slug += "-x"
        out.append(slug)
    return out


@pytest.mark.parametrize("shell,command,moved", CHDIR_FORMS,
                         ids=_slug_ids(c[1] for c in CHDIR_FORMS))
def test_chdir_forms_mark_the_directory_unknown(tmp_path, shell, command,
                                                 moved):
    _files(tmp_path, {WSF: "staging"})
    ctx = {"cd": False, "switch": False, "engaged": True}
    found = [f for f in cloud_guard.scan(shell, command, ctx=ctx) if f.scope]
    assert found, command
    assert bool(ctx["cd"]) is moved, (command, ctx)
    got = cloud_guard._tf_environment(found[-1].scope, str(tmp_path), ctx,  # pylint: disable=protected-access
                                      {"nonProd": NONPROD, "problem": ""})
    if moved:
        assert got[0] == "unknown", (command, got)


# Wrapper options that TAKE A VALUE, which the unwrapper used to read as the
# command: `env -a x terraform destroy` ran `x` as far as the guard could see,
# and `env -S'terraform destroy'` hid the whole command inside one word.
WRAPPER_BYPASS = [
    ("env-S-attached", "env -S'terraform destroy -auto-approve'"),
    ("env-split-string-equals",
     "env --split-string='terraform destroy -auto-approve'"),
    ("env-argv0", "env -a tf terraform destroy -auto-approve"),
    ("env-argv0-long", "env --argv0=tf terraform destroy -auto-approve"),
    ("env-bsd-P", "env -P /opt/bin terraform destroy -auto-approve"),
    ("sudo-chroot-value", "sudo -R /jail terraform destroy -auto-approve"),
    ("sudo-timeout-value", "sudo -T 60 terraform destroy -auto-approve"),
]


@pytest.mark.parametrize("case", WRAPPER_BYPASS,
                         ids=[c[0] for c in WRAPPER_BYPASS])
def test_wrapper_value_options_do_not_hide_the_command(tmp_path, case):
    _id, command = case
    tcg._fixture(tmp_path, tcg.ARMED)  # pylint: disable=protected-access
    decision, reason, code, err = tcg.run_hook("python", tmp_path, "Bash",
                                               command)
    assert (decision, code) == ("deny", 0), (reason, err)
    assert "[terraformApply]" in reason, reason


# FIX crew_tfplan.py:103, the hook's half: any environment change crew cannot
# read makes TF_WORKSPACE unknown, even where a workspace file says `qa`.
OPAQUE_RESOLVE = [
    ("bash", f"source prod.env && terraform apply {PLAN}"),
    ("bash", f". prod.env; terraform apply {PLAN}"),
    ("bash", f"eval \"$(cat prod.env)\"; terraform apply {PLAN}"),
    ("bash", f"export $(cat prod.env); terraform apply {PLAN}"),
    ("bash", f"terraform workspace select qa || true; terraform apply {PLAN}"),
    ("bash", f"false || terraform apply {PLAN}"),
    ("powershell", f"Set-Item env:{TFW} production; terraform apply {PLAN}"),
    ("powershell", f"si env:{TFW} production; terraform apply {PLAN}"),
    ("powershell", f"New-Item -Path env:{TFW} -Value production; "
                   f"terraform apply {PLAN}"),
    ("powershell", "[Environment]::SetEnvironmentVariable('TF_WORKSPACE',"
                   f"'production'); terraform apply {PLAN}"),
    ("powershell", f"${{env:{TFW}}} = 'production'; terraform apply {PLAN}"),
    ("powershell", f"$env:{TFW} += 'x'; terraform apply {PLAN}"),
    # PowerShell's eval, fed at run time: from a variable, or from the
    # pipeline, where it has no argument at all to read.
    ("powershell", f"iex $script; terraform apply {PLAN}"),
    ("powershell", f"Get-Content prod.ps1 | iex; terraform apply {PLAN}"),
    ("powershell", f"Get-Content prod.ps1 -Raw | Invoke-Expression; "
                   f"terraform apply {PLAN}"),
]


@pytest.mark.parametrize("shell,command", OPAQUE_RESOLVE,
                         ids=_slug_ids(c[1] for c in OPAQUE_RESOLVE))
def test_an_environment_change_crew_cannot_read_is_unknown(tmp_path, shell,
                                                           command):
    _files(tmp_path, {WSF: "qa"})
    finding, ctx = _finding(shell, command)
    got = cloud_guard._tf_environment(finding.scope, str(tmp_path), ctx,  # pylint: disable=protected-access
                                      {"nonProd": NONPROD, "problem": ""},
                                      {"workspace": "qa", "deletes": []})
    assert got[0] == "unknown", (command, got)


def test_a_sidecar_that_names_no_workspace_is_unknown(tmp_path):
    _files(tmp_path, {WSF: "qa"})
    finding, ctx = _finding("bash", f"terraform apply {PLAN}")
    for sidecar in ({"workspace": None, "deletes": []},
                    {"deletes": []}, {"workspace": "$WS", "deletes": []}):
        got = cloud_guard._tf_environment(finding.scope, str(tmp_path), ctx,  # pylint: disable=protected-access
                                          {"nonProd": NONPROD, "problem": ""},
                                          sidecar)
        assert got[0] == "unknown", (sidecar, got)


# FIX :1218. A plan, summary or workspace file that is not a regular file is
# never opened for reading: a FIFO blocks the read and /dev/zero never ends,
# and a hook past its 15 seconds is a non-blocking error -- the guard fails
# OPEN. Each must come back as a refusal, fast.

_special = pytest.mark.skipif(not hasattr(os, "mkfifo"),
                              reason="no mkfifo on this platform")


def _special_file(path, kind):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() or path.is_symlink():
        path.unlink()
    if kind == "fifo":
        os.mkfifo(path)
    else:
        os.symlink("/dev/zero", path)


def _run_bounded(tmp_path, command):
    """The python driver with a 30-second ceiling: a hang is a failure."""
    import subprocess  # pylint: disable=import-outside-toplevel
    body = {"tool_name": "Bash", "tool_input": {"command": command},
            "cwd": str(tmp_path / "repo")}
    try:
        proc = subprocess.run(
            [tcg.sys.executable, tcg._PY],  # pylint: disable=protected-access
            input=json.dumps(body).encode("utf-8"), capture_output=True,
            env=tcg._clean_env(tmp_path, UNATTENDED),  # pylint: disable=protected-access
            cwd=str(tmp_path), timeout=30, check=False)
    except subprocess.TimeoutExpired:
        pytest.fail(f"the hook hung on {command!r}: it would time out and "
                    "Claude Code would run the command anyway")
    lines = proc.stdout.decode("utf-8").strip().splitlines()
    if not lines:
        return "allow", proc.stderr.decode("utf-8", "replace")
    doc = json.loads(lines[-1])
    return doc["hookSpecificOutput"]["permissionDecision"], \
        doc["hookSpecificOutput"]["permissionDecisionReason"]


@_special
@pytest.mark.parametrize("target,kind", [
    (PLAN, "fifo"), (PLAN, "zero"), (WSF, "fifo"), (WSF, "zero"),
    ("sidecar", "fifo"), ("sidecar", "zero"), (".crew/config.json", "none")],
    ids=["plan-fifo", "plan-dev-zero", "wsfile-fifo", "wsfile-dev-zero",
         "sidecar-fifo", "sidecar-dev-zero", "control"])
def test_a_special_file_is_unknown_not_a_hang(tmp_path, target, kind):
    repo = _build(tmp_path, _o(sidecar={"workspace": "staging"},
                               wsfiles={".": "staging"}))
    if target == "sidecar":
        folder = repo / ".crew" / "tfplan"
        path = next(folder.iterdir())
    else:
        path = repo / target
    # The workspace file is read only when nothing names the workspace, so
    # its cases send no TF_WORKSPACE; the control proves the same fixture
    # allows with no special file in it.
    command = f"terraform apply {PLAN}" if target in (WSF, ".crew/config.json") \
        else f"{TFW}=staging terraform apply {PLAN}"
    if kind != "none":
        _special_file(path, kind)
    decision, reason = _run_bounded(tmp_path, command)
    assert decision == ("allow" if kind == "none" else "deny"), reason


@_special
@pytest.mark.parametrize("kind", ["fifo", "zero"])
def test_a_special_azure_profile_is_unknown_not_a_hang(tmp_path, kind):
    """The neighbour of the plan's FIX: `AZURE_CONFIG_DIR` is set by the
    command itself, so the profile the hook reads is a path the command
    chooses. A FIFO there hung the hook past its budget -- the guard failed
    open and `az group delete` ran. Unreadable, the default subscription is
    unknown, and the pinned identity rule refuses."""
    tcg._fixture(tmp_path, tcg.PINNED, tcg.PERMISSIVE_GLOBAL)  # pylint: disable=protected-access
    _special_file(tmp_path / "az" / "azureProfile.json", kind)
    decision, reason = _run_bounded(
        tmp_path, f"AZURE_CONFIG_DIR={tmp_path / 'az'} az group delete -n rg")
    assert decision == "deny", reason
    assert "unknown" in reason, reason


def test_env_i_clears_an_inherited_tf_workspace(tmp_path, monkeypatch):
    """`env -i` starts terraform with an empty environment, so the hook's
    own TF_WORKSPACE does not reach it: the workspace file decides."""
    monkeypatch.setenv(TFW, "production")
    _files(tmp_path, {WSF: "qa"})
    finding, ctx = _finding("bash", f"env -i terraform apply {PLAN}")
    got = cloud_guard._tf_environment(finding.scope, str(tmp_path), ctx,  # pylint: disable=protected-access
                                      {"nonProd": NONPROD, "problem": ""})
    assert got[:2] == ("nonProd", "qa"), got


def test_the_command_count_covers_every_depth():
    for command, want in (("terraform apply p.tfplan", 1),
                          ("sudo -E env X=1 terraform apply p.tfplan", 1),
                          ("terraform apply $(echo p.tfplan)", 2),
                          ("bash -c 'terraform apply p.tfplan'", 2),
                          ("> p.tfplan; terraform apply p.tfplan", 2),
                          ("a && b || c; d | e & f", 6)):
        ctx = {}
        cloud_guard.scan("bash", command, ctx=ctx)
        assert ctx.get("commands") == want, (command, ctx)


# --- review round 2 (T-0005-env-terraform--lt3l0F) ---------------------------
#
# BLOCK :1474. A substitution in an UNQUOTED heredoc body runs while the shell
# sets up the redirection, before terraform reads its plan, so it is another
# command and the saved plan is no longer the apply's alone. The fixture is
# the clean staging plan, summary and workspace file the bypass needed.
_R2_FIXTURE = _o(sidecar={"workspace": "staging"}, wsfiles={".": "staging"},
                 why="rewrite")
_SWAP = f"cp evil.tfplan {PLAN}"
HEREDOC_SUBST = _normalise([
    (case_id, "Bash", command, dict(_R2_FIXTURE))
    for case_id, command in (
        ("r2-heredoc-subst", f"terraform apply {PLAN} <<EOF\n$({_SWAP})\nEOF"),
        ("r2-heredoc-backtick",
         f"terraform apply {PLAN} <<EOF\n`{_SWAP}`\nEOF"),
        ("r2-heredoc-dash",
         f"terraform apply {PLAN} <<-EOF\n\t$({_SWAP})\n\tEOF"),
        ("r2-heredoc-param-default",
         f"terraform apply {PLAN} <<EOF\n${{x:=$({_SWAP})}}\nEOF"),
        ("r2-heredoc-arith",
         f"terraform apply {PLAN} <<EOF\n$(( $({_SWAP}) ))\nEOF"),
        ("r2-heredoc-second",
         f"terraform apply {PLAN} <<A <<B\nyes\nA\n$({_SWAP})\nB"),
        ("r2-heredoc-other-command",
         f"cat <<EOF; terraform apply {PLAN}\n$({_SWAP})\nEOF"),
        # The same shapes outside a heredoc, which the lexer skipped too.
        # Each rides in an option value, so the plan is still the only
        # operand and the substitution is the only thing wrong.
        ("r2-param-default",
         f"terraform apply -lock-timeout=0s${{x:=$({_SWAP})}} {PLAN}"),
        ("r2-arith-nested",
         f"terraform apply -parallelism=$(( $({_SWAP}) 10 )) {PLAN}"),
        ("r2-comsub-subshell",
         f"terraform apply -lock-timeout=0s$(({_SWAP}) ) {PLAN}"),
    )])

# FIX :1314. Terragrunt hands `workspace delete` to terraform in every
# module through `run-all`, `run --` and `run --all --`, and its own options
# may take a value. A destroy under `allow`, and under prodUnattended.
_TG_DELETES = (
    ("run-all", "terragrunt run-all workspace delete staging"),
    ("run", "terragrunt run -- workspace delete staging"),
    ("run-all-flag", "terragrunt run --all -- workspace delete staging"),
    ("valued-option", "terragrunt --working-dir infra workspace delete staging"),
)
TG_WS_DELETE = _normalise(
    [(f"tg-{name}-delete-allow", "Bash", command,
      _o(why="destroy", **ALLOW_POLICY)) for name, command in _TG_DELETES]
    + [(f"tg-{name}-delete-pu", "Bash", command, _o(pu=True, why="destroy"))
       for name, command in _TG_DELETES])

# NIT :588. PowerShell's `&` after a bare `2>` is part of `2>&1`; a `&` on
# its own is still a second command.
PS_SEPARATOR = _normalise([
    ("r2-ps-background", "PowerShell", f"terraform apply {PLAN} & whoami",
     dict(_R2_FIXTURE)),
    ("r2-ps-quoted-redirect", "PowerShell",
     f"terraform apply {PLAN} '2>'&1", dict(_R2_FIXTURE)),
])

_ROUND2 = HEREDOC_SUBST + TG_WS_DELETE + PS_SEPARATOR

_R2_LOG = "env:nonProd:staging"
ROUND2_ALLOW_ALL = _normalise([
    (case_id, tool, command,
     _o(sidecar={"workspace": "staging"}, wsfiles={".": "staging"},
        log=_R2_LOG))
    for case_id, tool, command in (
        ("r2-heredoc-quoted", "Bash",
         f"terraform apply {PLAN} <<'EOF'\n$({_SWAP})\nEOF"),
        ("r2-heredoc-dquoted", "Bash",
         f'terraform apply {PLAN} <<"EOF"\n$({_SWAP})\nEOF'),
        ("r2-heredoc-partly-quoted", "Bash",
         f'terraform apply {PLAN} <<E"O"F\n$({_SWAP})\nEOF'),
        ("r2-heredoc-backslash-delim", "Bash",
         f"terraform apply {PLAN} <<\\EOF\n$({_SWAP})\nEOF"),
        ("r2-heredoc-escaped-dollar", "Bash",
         f"terraform apply {PLAN} <<EOF\n\\$({_SWAP})\nEOF"),
        ("r2-heredoc-plain", "Bash", f"terraform apply {PLAN} <<EOF\nyes\nEOF"),
        ("r2-arith-plain", "Bash",
         f"terraform apply -parallelism=$((2 * 5)) {PLAN}"),
        ("r2-ps-2-to-1", "PowerShell", f"terraform apply {PLAN} 2>&1"),
        ("r2-ps-star-to-1", "PowerShell", f"terraform apply {PLAN} *>&1"),
        ("r2-ps-null", "PowerShell", f"terraform apply {PLAN} 2>$null"),
    )])

# Step 8: the rows that carry a quote, a heredoc, `$` or an escape are no
# longer plain, so they are "could not tell" now (`NOW_NOT_LITERAL`). The
# lexer still reads each of them as it did (`test_the_command_count_*`).
_R2_NOT_LITERAL = frozenset((
    "r2-heredoc-quoted", "r2-heredoc-dquoted", "r2-heredoc-partly-quoted",
    "r2-heredoc-backslash-delim", "r2-heredoc-escaped-dollar",
    "r2-heredoc-plain", "r2-arith-plain", "r2-ps-null"))
ROUND2_ALLOW = [c for c in ROUND2_ALLOW_ALL if c[0] not in _R2_NOT_LITERAL]


@pytest.mark.parametrize("case", _ROUND2, ids=_ids(_ROUND2))
def test_round2_must_block_python(tmp_path, case):
    _deny("python", tmp_path, case)


@pytest.mark.parametrize("case", _sample(
    _ROUND2, ("r2-heredoc-subst", "tg-run-all-delete-allow"),
    (tcg.needs_bash,)))
def test_round2_must_block_bash(tmp_path, case):
    _deny("bash", tmp_path, case)


@pytest.mark.parametrize("case", ROUND2_ALLOW, ids=_ids(ROUND2_ALLOW))
def test_round2_must_allow_python(tmp_path, case):
    _allow("python", tmp_path, case)


@pytest.mark.parametrize("case", _sample(
    ROUND2_ALLOW, ("r2-ps-2-to-1", "r2-ps-star-to-1"), (tcg.needs_pwsh,)))
def test_round2_must_allow_pwsh(tmp_path, case):
    _allow("pwsh", tmp_path, case)


@pytest.mark.parametrize("command", [
    "terragrunt run-all workspace list",
    "terragrunt run -- workspace show",
    "terragrunt run --all -- workspace select staging"])
def test_terragrunt_workspace_reads_stay_unjudged(tmp_path, command):
    """The wrapper fix does not make every terragrunt workspace call a
    finding: listing, showing and selecting are not destroys."""
    tcg._fixture(tmp_path, {"guards": {"cloudGuard": "block",  # pylint: disable=protected-access
                                       "terraformApply": "allow"}},
                 {"guards": {"terraformApply": "allow"}})
    decision, reason, code, err = tcg.run_hook("python", tmp_path, "Bash",
                                               command, extra_env=UNATTENDED)
    assert (decision, code) == ("allow", 0), (reason, err)


def test_the_command_count_covers_heredoc_substitutions():
    for command, want in (
            (f"terraform apply {PLAN} <<EOF\n$({_SWAP})\nEOF", 2),
            (f"terraform apply {PLAN} <<'EOF'\n$({_SWAP})\nEOF", 1),
            (f"terraform apply {PLAN} <<EOF\n$(a) `b` ${{c:-$(d)}}\nEOF", 4),
            (f"terraform apply {PLAN} <<EOF\nno substitution\nEOF", 1)):
        ctx = {}
        cloud_guard.scan("bash", command, ctx=ctx)
        assert ctx.get("commands") == want, (command, ctx)


@pytest.mark.parametrize("command, want", [
    (f"terraform apply {PLAN} 2>&1", [["terraform", "apply", PLAN]]),
    (f"terraform apply {PLAN} *>&1", [["terraform", "apply", PLAN]]),
    (f"terraform apply {PLAN} & whoami",
     [["terraform", "apply", PLAN], ["whoami"]]),
])
def test_powershell_fd_merge_is_a_redirection(command, want):
    cmds, _subs = cloud_guard._lex_ps(command)  # pylint: disable=protected-access
    assert [c.words for c in cmds] == want


# --- review round 3 (T-0005-env-terraform--ICP8KT) ---------------------------
#
# BLOCK/FIX :214. `"${x:-"'"}"` -- a double-quoted `${...}` holding its own
# double quotes -- ended the guard's string at the inner quote, and the `'`
# inside opened a single-quoted string that swallowed the rest of the
# command: a substitution after it was never counted (BLOCK) and a command
# after it was never judged (FIX). FIX :444: `\r#` read as a comment, which
# bash without igncr does not. FIX :1419: an option value `workspace` taken
# as terragrunt's workspace subcommand.
#
# The class, not the instance: wherever the lexer cannot be sure it read a
# command line the way bash will -- quoting inside `${...}`, an unterminated
# quote or substitution, a control character -- it counts one command more,
# so an unattended saved-plan apply is refused, and it re-reads the text the
# other way so nothing that bash would run goes unjudged.
_R3_FIXTURE = _o(sidecar={"workspace": "staging"}, wsfiles={".": "staging"},
                 why="rewrite")
_APPLY = f"terraform apply {PLAN}"

# (id, command). Every one would be ALLOWED if the fail-closed count were
# gone: most carry no substitution at all, so the only thing wrong with them
# is that crew cannot be sure how bash splits them.
HOSTILE_QUOTING = [
    ("r3q-sq-in-param-dq", f'{_APPLY} <<<"${{x:-"\'"}}"'),
    ("r3q-sq-in-param-dq-subst", f'{_APPLY} <<<"${{x:-"\'"}}$({_SWAP})"'),
    ("r3q-sq-pair-in-param-dq", f"{_APPLY} <<<\"${{x:-'}}'}}\""),
    ("r3q-sq-in-param-bare", f"{_APPLY} <<<${{x:-'a'}}"),
    ("r3q-dq-in-param-bare", f'{_APPLY} <<<${{x:-"a"}}'),
    ("r3q-escaped-dq-in-param", f'{_APPLY} <<<"${{x:-\\"}}"'),
    ("r3q-ansi-c-in-param", f"{_APPLY} <<<${{x:-$'\\''}}"),
    ("r3q-ansi-c-in-param-dq", f"{_APPLY} <<<\"${{x:-$'\\''}}\""),
    ("r3q-backslash-in-param", f"{_APPLY} <<<${{x:-\\}}}}"),
    ("r3q-nested-param-quote", f'{_APPLY} <<<"${{x:-${{y:-"\'"}}}}"'),
    ("r3q-nested-comsub", f'{_APPLY} <<<"$( echo "$( echo a )" )"'),
    ("r3q-herestring-sq-then-dq", f"{_APPLY} <<<'a'\"${{x:-\"'\"}}\""),
    ("r3q-herestring-ansi-c", f"{_APPLY} <<<$'\\''\"${{x:-'}}'}}\""),
    ("r3q-unterminated-sq", f"{_APPLY} <<<'abc"),
    ("r3q-unterminated-dq", f'{_APPLY} <<<"abc'),
    ("r3q-unterminated-ansi-c", f"{_APPLY} <<<$'abc"),
    ("r3q-unterminated-param", f"{_APPLY} <<<${{x:-abc"),
    ("r3q-cr-before-hash", f"true \r# ; {_APPLY}"),
    ("r3q-cr-before-semicolon", f"{_APPLY}\r;"),
    ("r3q-vt-before-hash", f"{_APPLY} <<<a\v#b"),
    ("r3q-vt-before-semicolon", f"{_APPLY} <<<a\v;"),
    ("r3q-cr-in-herestring", f'{_APPLY} <<<"a\r# b"'),
    ("r3q-nul-in-herestring", f'{_APPLY} <<<"a\0b"'),
    ("r3q-escape-char", f"{_APPLY} <<<a\x1b[0m"),
    ("r3q-comsub-ansi-c-paren", f"{_APPLY} <<<$(echo $'\\')')"),
    ("r3q-comsub-heredoc", f"{_APPLY} <<<\"$(cat <<E\n)\nE\n)\""),
]
HOSTILE_QUOTING_CASES = _normalise(
    [(case_id, "Bash", command, dict(_R3_FIXTURE))
     for case_id, command in HOSTILE_QUOTING])

# Commands the round-3 shapes hid from the guard entirely: each is a destroy
# that must be denied even under `terraformApply: allow`. Every one was run
# through bash 5.3 with `echo PWN` in place of terraform and printed PWN.
_DESTROY = "terraform destroy -auto-approve"
HIDDEN_DESTROY = _normalise(
    [(case_id, "Bash", command, _o(why="destroy", **ALLOW_POLICY))
     for case_id, command in (
         ("r3-param-dq-assignment", f'X="${{x:-"\'"}}" {_DESTROY}'),
         ("r3-param-ansi-c", f"X=${{x:-$'\\''}}; {_DESTROY}"),
         ("r3-param-ansi-c-balanced", f"X=${{x:-$'\\''}}; {_DESTROY}; echo '}}'"),
         ("r3-comsub-ansi-c", f"X=$(echo $'\\')'; {_DESTROY}; echo )"),
         # A heredoc inside `$( )`: bash does not count the body's `)`, the
         # matcher does, and the `'` after it then quotes the destroy.
         ("r3-comsub-heredoc-paren",
          f"X=$(cat <<E\n)'\nE\n); {_DESTROY} #'"),
         ("r3-cr-hash-destroy", f"true \r# ; {_DESTROY}"),
         ("r3-cr-hash-workspace-delete",
          "true \r# ; terraform workspace delete production"),
         ("r3-cr-hash-no-plan-apply", "true \r# ; terraform apply -auto-approve"),
         ("r3-cr-hash-next-line",
          f"true \r# '\n{_DESTROY}\n'"),
         ("r3-tg-working-dir-workspace",
          "terragrunt --working-dir workspace run-all workspace delete staging"),
         ("r3-tg-exclude-dir-workspace",
          "terragrunt run-all --queue-exclude-dir workspace workspace delete "
          "staging"),
     )]
    + [(case_id, "Bash", command, _o(why="destroy"))
       for case_id, command in (
           ("r3-param-dq-assignment-ask", f'X="${{x:-"\'"}}" {_DESTROY}'),
           ("r3-cr-hash-destroy-ask", f"true \r# ; {_DESTROY}"),
       )]
    # The same class in PowerShell, whose tokenizer takes the typographic
    # quotes as quotes and a bare CR as a line end (comments included).
    # Each was run through pwsh 7 with `Write-Output PWN` and printed PWN.
    + [(case_id, "PowerShell", command, _o(why="destroy", **ALLOW_POLICY))
       for case_id, command in (
           ("r3-ps-smart-single", f"Write-Output \u2018x' ; {_DESTROY} ; 'y\u2019"),
           ("r3-ps-smart-double", f'Write-Output \u201cx" ; {_DESTROY} ; "y\u201d'),
           ("r3-ps-cr-line", f"echo a\r{_DESTROY}"),
           ("r3-ps-cr-ends-comment", f"echo a # x\r{_DESTROY}"),
           ("r3-ps-cr-herestring", f"Write-Output @'\rabc\r'@\r{_DESTROY}"),
       )])

_ROUND3 = HOSTILE_QUOTING_CASES + HIDDEN_DESTROY

# Ordinary, clean command lines: the fail-closed rule must not touch them.
ROUND3_ALLOW_ALL = _normalise([
    (case_id, "Bash", command,
     _o(sidecar={"workspace": "staging"}, wsfiles={".": "staging"},
        log=_R2_LOG))
    for case_id, command in (
        ("r3a-plain", _APPLY),
        ("r3a-tf-workspace", f"{TFW}=staging {_APPLY}"),
        ("r3a-herestring-dq", f'{_APPLY} <<<"yes"'),
        ("r3a-herestring-sq", f"{_APPLY} <<<'yes'"),
        ("r3a-herestring-ansi-c", f"{_APPLY} <<<$'yes\\n'"),
        ("r3a-herestring-bare", f"{_APPLY} <<<yes"),
        ("r3a-param-dq", f'terraform apply -lock-timeout="${{LOCK:-0s}}" {PLAN}'),
        ("r3a-param-bare", f"terraform apply -lock-timeout=${{LOCK:-0s}} {PLAN}"),
        ("r3a-quoted-plan-dq", f'terraform apply "{PLAN}"'),
        ("r3a-quoted-plan-sq", f"terraform apply '{PLAN}'"),
        ("r3a-comment", f"{_APPLY} # apply the reviewed plan"),
        ("r3a-tab", f"{_APPLY}\t"),
        ("r3a-trailing-newline", f"{_APPLY}\n"),
        ("r3a-escaped-space", f"terraform apply -lock-timeout=0\\ s {PLAN}"),
        ("r3a-sq-with-dq-inside", f"{_APPLY} <<<'say \"yes\"'"),
        ("r3a-dq-with-sq-inside", f'{_APPLY} <<<"it\'s fine"'),
        ("r3a-devnull", f"{_APPLY} > /dev/null 2>&1"),
    )])

# Step 8: every row here but these five carries a quote, `$`, a comment, an
# escape or a here-string, so it is "could not tell" now; the lexer's count
# of one command still holds for all of them (`test_clean_commands_count_one`).
_R3_LITERAL = frozenset(("r3a-plain", "r3a-tf-workspace", "r3a-tab",
                         "r3a-trailing-newline", "r3a-devnull"))
ROUND3_ALLOW = [c for c in ROUND3_ALLOW_ALL if c[0] in _R3_LITERAL]


@pytest.mark.parametrize("case", _ROUND3, ids=_ids(_ROUND3))
def test_round3_must_block_python(tmp_path, case):
    _deny("python", tmp_path, case)


@pytest.mark.parametrize("case", _sample(
    _ROUND3, ("r3q-sq-in-param-dq-subst", "r3-param-dq-assignment",
              "r3-cr-hash-destroy"), (tcg.needs_bash,)))
def test_round3_must_block_bash(tmp_path, case):
    _deny("bash", tmp_path, case)


@pytest.mark.parametrize("case", ROUND3_ALLOW, ids=_ids(ROUND3_ALLOW))
def test_round3_must_allow_python(tmp_path, case):
    _allow("python", tmp_path, case)


@pytest.mark.parametrize("case", _sample(
    ROUND3_ALLOW, ("r3a-plain", "r3a-devnull"), (tcg.needs_bash,)))
def test_round3_must_allow_bash(tmp_path, case):
    _allow("bash", tmp_path, case)


def test_round3_tables_are_big_enough_and_distinct():
    """The owner asked for at least 15 hostile shapes; ids never repeat."""
    assert len(HOSTILE_QUOTING) >= 15
    ids = _ids(_ROUND3 + ROUND3_ALLOW_ALL)
    assert len(ids) == len(set(ids))


@pytest.mark.parametrize("command", [c for _i, c in HOSTILE_QUOTING],
                         ids=[i for i, _c in HOSTILE_QUOTING])
def test_hostile_quoting_counts_an_extra_command(command):
    """The mechanism itself, independent of the hook: the saved plan's
    apply is never the only command crew counts."""
    ctx = {}
    cloud_guard.scan("bash", command, ctx=ctx)
    assert ctx.get("commands", 0) >= 2, ctx


@pytest.mark.parametrize("command", [c for _i, _t, c, _o2 in ROUND3_ALLOW_ALL],
                         ids=_ids(ROUND3_ALLOW_ALL))
def test_clean_commands_count_one(command):
    ctx = {}
    cloud_guard.scan("bash", command, ctx=ctx)
    assert ctx.get("commands") == 1, ctx


@pytest.mark.parametrize("command, want", [
    ("terragrunt --working-dir workspace run-all workspace delete staging",
     ("ws-delete", "staging")),
    ("terragrunt run-all --queue-exclude-dir workspace workspace delete qa",
     ("ws-delete", "qa")),
    ("terragrunt --working-dir workspace workspace select -or-create dev",
     ("ws-create", "dev")),
    ("terragrunt run-all workspace delete staging", ("ws-delete", "staging")),
    ("terragrunt --working-dir workspace run-all workspace list",
     (None, None)),
])
def test_terragrunt_workspace_after_an_option_value(command, want):
    args = command.split()[1:]
    assert cloud_guard._tf_workspace(args, "terragrunt") == want  # pylint: disable=protected-access


@pytest.mark.parametrize("text, start, want", [
    ("${x:-$'\\''}; y }", 1, (10, True)),
    ('${x:-"}"}', 1, (8, True)),
    ("${x:-'}'}", 1, (8, True)),
    ("${x:-\\}}", 1, (7, True)),
    ("${x:-${y:-}}}", 1, (11, True)),
    ("$(echo \\))", 1, (9, True)),
    ("$(echo ')')", 1, (10, True)),
    ('$(echo "$(echo ")")")', 1, (20, True)),
    ("$(echo `echo )`)", 1, (15, True)),
    ("$(echo a # )\n)", 1, (13, True)),
    ("$(echo a#b)", 1, (10, True)),
    ("${x:-'}", 1, (7, False)),
    ("$(echo $'\\')", 1, (12, False)),
])
def test_bash_close_reads_like_bash(text, start, want):
    """Where `${ }` and `$( )` end, as bash 5.3 ends them."""
    assert cloud_guard._bash_close(text, start) == want  # pylint: disable=protected-access


def test_double_quoted_param_is_one_word():
    """The BLOCK itself, at the lexer: `"${x:-"'"}$(cmd)"` is one word whose
    substitution is a command, and the quoting inside `${}` is a doubt."""
    unsure = []
    cmds, subs = cloud_guard._lex_bash(  # pylint: disable=protected-access
        f'cat <<<"${{x:-"\'"}}$({_SWAP})"', unsure)
    assert [c.words for c in cmds] == [["cat"]]
    assert cmds[0].stdin == f'${{x:-"\'"}}$({_SWAP})'
    assert _SWAP in subs
    assert unsure


def test_a_redirection_without_a_target_does_not_take_the_next_command():
    """`<<<\r;`: the lexer found no target where bash found `\r`. The next
    command's head must stay a head, not become the missing target."""
    unsure = []
    cmds, _subs = cloud_guard._lex_bash(  # pylint: disable=protected-access
        f"cat <<<\r; {_DESTROY}", unsure)
    assert [c.words for c in cmds][-1] == _DESTROY.split()
    assert unsure


def test_a_cr_heredoc_delimiter_is_read_both_ways_by_the_lexer():
    """Round 2's `EOF\\r` rule, pinned at the lexer. Since round 3 `scan`
    also re-reads any CR line whole, which judges the hook-level case on its
    own, so the heredoc rule needs a check that only it can pass: the text
    after the next exact delimiter reaches `subs`."""
    text = f"cat <<EOF\nEOF\r\n'\nEOF\n{_DESTROY}\n'\n"
    _cmds, subs = cloud_guard._lex_bash(text)  # pylint: disable=protected-access
    assert any(sub.startswith(_DESTROY) for sub in subs), subs


# --- Step 8: the literal-word allowlist (review round 4, bl77wS) ------------
#
# Four rounds found a new bash quoting shape each time, so the approach
# changed instead of growing: a command line that names terraform, terragrunt
# or tofu ANYWHERE -- the name spotted after quote and escape characters are
# taken out of each word, so a quote cannot hide it -- is judged only when
# every word on it is a plain literal. Anything else on such a line is
# "could not tell": asked about when someone is attending, denied when not,
# never allowed. The check reads the raw text before the lexer does, so no
# lexer bug can turn a shape it misreads into an allow.
#
# Every row below is built so that the value a missing gate would collapse
# to is ALLOW: the clean staging plan, summary and workspace file, or a
# policy the row would otherwise slip past (`block`, `allow`).
GATE_WHY = "plain literal"
_STAGING = {"sidecar": {"workspace": "staging"}, "wsfiles": {".": "staging"}}
BLOCK_POLICY = {"repo": {"guards": {"terraformApply": "block"}},
                "global_": {"guards": {"terraformApply": "block"}}}


def _gate(**kw):
    return _o(**{**_STAGING, "why": GATE_WHY, **kw})


def _lexed(**kw):
    """A row the lexer judges on its own: the line is all plain literals, so
    the gate hands it on, and the reason names the destroy."""
    return _o(**{**_STAGING, "why": "destroy", **kw})


_ADESTROY = "destroy -auto-approve"
MUST_BLOCK_LITERAL = _normalise([
    # Round 2 (lt3l0F): an unquoted heredoc's substitution swaps the plan.
    ("s8-r2-heredoc-subst", "Bash",
     f"terraform apply {PLAN} <<EOF\n$({_SWAP})\nEOF", _gate()),
    ("s8-r2-heredoc-backtick", "Bash",
     f"terraform apply {PLAN} <<EOF\n`{_SWAP}`\nEOF", _gate()),
    ("s8-r2-heredoc-dash", "Bash",
     f"terraform apply {PLAN} <<-EOF\n\t$({_SWAP})\n\tEOF", _gate()),
    ("s8-r2-heredoc-dot-slash", "Bash",
     f"./terraform apply {PLAN} <<EOF\n$({_SWAP})\nEOF", _gate()),
    ("s8-r2-cat-heredoc-destroy", "Bash",
     f"cat <<EOF\n$(terraform {_ADESTROY})\nEOF", _gate()),
    ("s8-r2-cat-heredoc-ws-delete", "Bash",
     "cat <<EOF\n$(terraform workspace delete production)\nEOF", _gate()),
    ("s8-r2-tg-run-all-ws-delete", "Bash",
     "terragrunt run-all workspace delete staging",
     _lexed(**ALLOW_POLICY)),
    ("s8-r2-tg-run-ws-delete", "Bash",
     "terragrunt run -- workspace delete staging", _lexed(**ALLOW_POLICY)),
    ("s8-r2-tg-run-all-flag-ws-delete", "Bash",
     "terragrunt run --all -- workspace delete staging",
     _lexed(**ALLOW_POLICY)),
    # Round 3 (ICP8KT): quoting inside `${...}`, `\r#`, option values.
    ("s8-r3-herestring-nested-quote", "Bash",
     f'terraform apply {PLAN} <<<"${{x:-"\'"}}$({_SWAP})"', _gate()),
    ("s8-r3-assignment-nested-quote", "Bash",
     f'X="${{x:-"\'"}}" terraform {_ADESTROY}', _gate()),
    ("s8-r3-assignment-nested-quote-allow", "Bash",
     f'X="${{x:-"\'"}}" terraform {_ADESTROY}',
     _gate(**ALLOW_POLICY)),
    ("s8-r3-cr-hash-destroy", "Bash",
     f"true \r# ; terraform {_ADESTROY}", _gate()),
    ("s8-r3-cr-hash-ws-delete", "Bash",
     "true \r# ; terraform workspace delete production", _gate()),
    ("s8-r3-cr-hash-apply", "Bash",
     "true \r# ; terraform apply -auto-approve", _gate()),
    ("s8-r3-tg-working-dir-workspace", "Bash",
     "terragrunt --working-dir workspace run-all workspace delete staging",
     _lexed(**ALLOW_POLICY)),
    ("s8-r3-tg-exclude-dir-workspace", "Bash",
     "terragrunt run-all --queue-exclude-dir workspace workspace delete "
     "staging", _lexed(**ALLOW_POLICY)),
    # Round 4 (bl77wS): `$"..."` and `$'\xNN'`, and a non-literal subcommand.
    ("s8-r4-heredoc-locale-delim", "Bash",
     f'cat <<$"EOF"\nEOF\nterraform {_ADESTROY}', _gate()),
    ("s8-r4-heredoc-ansi-delim", "Bash",
     f"cat <<$'\\x45OF'\nEOF\nterraform {_ADESTROY}", _gate()),
    ("s8-r4-heredoc-on-apply", "Bash",
     f'terraform apply {PLAN} <<$"EOF"\nEOF\n{_SWAP}', _gate()),
    ("s8-r4-locale-subcommand-block", "Bash",
     'terraform $"destroy" -auto-approve', _gate(**BLOCK_POLICY)),
    ("s8-r4-ansi-hex-subcommand-block", "Bash",
     "terraform $'\\x64estroy' -auto-approve", _gate(**BLOCK_POLICY)),
    ("s8-r4-locale-ws-delete-block", "Bash",
     'terraform workspace $"delete" production', _gate(**BLOCK_POLICY)),
    ("s8-r4-nonliteral-subcommand", "Bash",
     "terraform destroy${x} -auto-approve", _gate()),
    # The neighbours Step 8 names.
    ("s8-locale-subcommand", "Bash", 'terraform $"destroy" -auto-approve',
     _gate()),
    ("s8-ansi-hex-subcommand", "Bash",
     "terraform $'\\x64estroy' -auto-approve", _gate()),
    ("s8-ansi-octal-subcommand", "Bash",
     "terraform $'\\144estroy' -auto-approve", _gate(**ALLOW_POLICY)),
    ("s8-quoted-name", "Bash", f'"terraform" {_ADESTROY}', _gate()),
    ("s8-escaped-letter", "Bash", f"terr\\aform {_ADESTROY}", _gate()),
    ("s8-escaped-space", "Bash", f"terraform\\ {_ADESTROY}", _gate()),
    ("s8-brace-name", "Bash", f"t{{erraform,x}} {_ADESTROY}", _gate()),
    ("s8-glob-subcommand", "Bash", "terraform de* -auto-approve", _gate()),
    ("s8-subst-subcommand", "Bash", "terraform $(echo destroy) -auto-approve",
     _gate()),
    ("s8-backtick-subcommand", "Bash",
     "terraform `echo destroy` -auto-approve", _gate()),
    ("s8-procsub", "Bash", f"terraform <(x) {_ADESTROY}", _gate()),
    ("s8-herestring", "Bash", f"terraform {_ADESTROY} <<<x", _gate()),
    ("s8-variable-subcommand", "Bash",
     "x=destroy; terraform $x -auto-approve", _gate()),
    # `$` is the only thing on these lines that is not plain.
    ("s8-dollar-only-subcommand", "Bash", "terraform destroy$x -auto-approve",
     _gate()),
    ("s8-dollar-only-verb", "Bash", "terraform $VERB -auto-approve", _gate()),
    ("s8-tab-between-words", "Bash", "terraform\tdestroy\t-auto-approve",
     _lexed()),
    ("s8-tab-in-ansi-word", "Bash",
     "eval $'terraform\\x09destroy -auto-approve'", _gate()),
    ("s8-cr-in-word", "Bash", "terraform destroy\r -auto-approve", _gate()),
    ("s8-cr-line-end", "Bash", f"terraform {_ADESTROY}\r", _gate()),
    # The name itself hidden, on a line that does not look like terraform.
    ("s8-name-part-quoted", "Bash", f"t'erraform' {_ADESTROY}", _gate()),
    ("s8-name-ansi", "Bash", f"$'\\x74erraform' {_ADESTROY}", _gate()),
    ("s8-name-locale", "Bash", f'$"terraform" {_ADESTROY}', _gate()),
    ("s8-name-empty-subst", "Bash", f"te$(true)rraform {_ADESTROY}", _gate()),
    ("s8-name-empty-var", "Bash", f"terraform${{x}} {_ADESTROY}", _gate()),
    ("s8-name-default-expansion", "Bash", f"${{x:-terraform}} {_ADESTROY}",
     _gate()),
    ("s8-name-glob-path", "Bash", f"/usr/bin/terr* {_ADESTROY}", _gate()),
    ("s8-name-line-continuation", "Bash", f"terra\\\nform {_ADESTROY}",
     _gate()),
    ("s8-name-in-variable", "Bash", f"x=terraform; $x {_ADESTROY}", _gate()),
    ("s8-name-bash-c-ansi", "Bash", f"bash -c $'\\x74erraform {_ADESTROY}'",
     _gate()),
    ("s8-tofu-locale", "Bash", 'tofu $"destroy" -auto-approve', _gate()),
    ("s8-terragrunt-ansi", "Bash", "terragrunt $'destroy' -auto-approve",
     _gate(**ALLOW_POLICY)),
    ("s8-quoted-name-and-ansi", "Bash",
     "'terraform' $'\\x64estroy' -auto-approve", _gate()),
    ("s8-ps-quoted-name", "PowerShell", f'& "terraform" {_ADESTROY}',
     _gate()),
    ("s8-ps-backtick-name", "PowerShell", f"terr`aform {_ADESTROY}", _gate()),
    ("s8-ps-subexpression", "PowerShell",
     'terraform $("destroy") -auto-approve', _gate()),
    # `@a` splats a variable an earlier call may have set.
    ("s8-ps-splat", "PowerShell", "terraform @a", _gate()),
])

# Plain commands users run, and lines that name no terraform at all however
# they quote. `log` names the guard.log row an allowed apply must leave; a
# row without one must leave no terraformApply row at all.
MUST_ALLOW_LITERAL = _normalise([
    ("s8a-plan-out", "Bash", "terraform plan -out=p.tfplan", _o(**_STAGING)),
    ("s8a-apply-saved-plan", "Bash", f"terraform apply {PLAN}",
     _o(**_STAGING, log="env:nonProd:staging")),
    ("s8a-workspace-list", "Bash", "terraform workspace list", _o()),
    ("s8a-workspace-show", "Bash", "terraform workspace show", _o()),
    ("s8a-chdir-plan", "Bash", "terraform -chdir=envs/staging plan", _o()),
    ("s8a-terragrunt-run-all-plan", "Bash", "terragrunt run-all plan", _o()),
    ("s8a-tofu-plan", "Bash", "tofu plan", _o()),
    ("s8a-init-validate", "Bash",
     "terraform init -upgrade && terraform validate", _o()),
    ("s8a-fmt-check", "Bash", "terraform fmt -check -recursive", _o()),
    ("s8a-output-redirect", "Bash",
     "terraform output -json > outputs.json 2>&1", _o()),
    ("s8a-plan-pipe", "Bash", "terraform plan -no-color | tee plan.log", _o()),
    ("s8a-var-plan", "Bash",
     f"{TFW}=staging terraform plan -var=environment=staging", _o()),
    ("s8a-multiline", "Bash", "terraform init\nterraform plan -out=p.tfplan",
     _o()),
    ("s8a-ps-plan", "PowerShell", "terraform plan -out=p.tfplan", _o()),
    ("s8a-ps-apply-merge", "PowerShell", f"terraform apply {PLAN} *>&1",
     _o(**_STAGING, log="env:nonProd:staging")),
    ("s8a-no-tf-echo-home", "Bash", 'echo "$HOME"', _o()),
    ("s8a-no-tf-commit", "Bash", 'git commit -m "x"', _o()),
    ("s8a-no-tf-commit-subst", "Bash", 'git commit -m "$(cat msg.txt)"', _o()),
    ("s8a-no-tf-log-format", "Bash", "git log --format='%H %s' -n 5", _o()),
    ("s8a-no-tf-find-exec", "Bash",
     "find . -name '*.py' -exec grep -l \"import os\" {} +", _o()),
    ("s8a-no-tf-heredoc", "Bash", "cat <<'EOF' > notes.txt\nhello $USER\nEOF",
     _o()),
    ("s8a-no-tf-for-loop", "Bash", 'for f in *.md; do echo "$f"; done', _o()),
    ("s8a-no-tf-ansi", "Bash", "printf $'a\\tb\\n'", _o()),
    ("s8a-no-tf-awk", "Bash", "awk '{print $1}' access.log | sort | uniq -c",
     _o()),
    ("s8a-no-tf-brace-seq", "Bash", "echo {1..500} {a,b}", _o()),
    ("s8a-no-tf-short-globs", "Bash", "ls * t* *.tf", _o()),
    ("s8a-no-tf-comment", "Bash", "ls -la  # list", _o()),
    ("s8a-no-tf-tf-files", "Bash", "grep -n 'resource' main.tf", _o()),
    ("s8a-no-tf-ps-env", "PowerShell", 'Write-Output "$env:HOME"', _o()),
    ("s8a-no-tf-ps-filter", "PowerShell",
     "Get-ChildItem -Filter '*.tf' | ForEach-Object { $_.Name }", _o()),
])

# Rows the round-2 and round-3 must-allow tables held until Step 8: a clean
# nonProd saved-plan apply, spelled with a quote, heredoc, here-string,
# comment, escape or `$`. Each is refused unattended now.
NOW_NOT_LITERAL = [
    ("s8-was-" + case_id, tool, command, _gate())
    for case_id, tool, command, _opts in ROUND2_ALLOW_ALL + ROUND3_ALLOW_ALL
    if case_id in _R2_NOT_LITERAL or case_id not in _R3_LITERAL
    and case_id.startswith("r3a-")]

# Unusual quoting on a terraform line is ASKED about when someone attends.
ASK_LITERAL = _normalise([
    ("s8q-locale-destroy", "Bash", 'terraform $"destroy" -auto-approve',
     _o(**_STAGING)),
    ("s8q-quoted-plan", "Bash", f'terraform apply "{PLAN}"', _o(**_STAGING)),
    ("s8q-quoted-name", "Bash", f'"terraform" {_ADESTROY}',
     _o(**ALLOW_POLICY)),
])


def _allow_literal(driver, tmp_path, case):
    _id, tool, _command, opts = case
    repo, result = _run(driver, tmp_path, case)
    if tcg._stood_down(driver, tool, result):  # pylint: disable=protected-access
        return
    decision, _said, code, err = result
    assert code == 0, err
    assert decision == "allow", (case[0], result)
    rows = [r for r in _log_rows(repo) if r[1] == "terraformApply"]
    assert all(r[3] == "allow" for r in rows), rows
    if opts.get("log"):
        assert any(r[2] == opts["log"] for r in rows), (opts["log"], rows)
    else:
        assert not rows, rows


@pytest.mark.parametrize("case", MUST_BLOCK_LITERAL,
                         ids=_ids(MUST_BLOCK_LITERAL))
def test_literal_must_block_python(tmp_path, case):
    _deny("python", tmp_path, case)


@pytest.mark.parametrize("case", _sample(
    MUST_BLOCK_LITERAL, ("s8-r4-heredoc-locale-delim", "s8-name-ansi"),
    (tcg.needs_bash,)))
def test_literal_must_block_bash(tmp_path, case):
    _deny("bash", tmp_path, case)


@pytest.mark.parametrize("case", _sample(
    MUST_BLOCK_LITERAL, ("s8-quoted-name", "s8-ps-quoted-name"),
    (tcg.needs_pwsh,)))
def test_literal_must_block_pwsh(tmp_path, case):
    _deny("pwsh", tmp_path, case)


@pytest.mark.parametrize("case", MUST_ALLOW_LITERAL,
                         ids=_ids(MUST_ALLOW_LITERAL))
def test_literal_must_allow_python(tmp_path, case):
    _allow_literal("python", tmp_path, case)


@pytest.mark.parametrize("case", _sample(
    MUST_ALLOW_LITERAL, ("s8a-apply-saved-plan", "s8a-no-tf-echo-home"),
    (tcg.needs_bash,)))
def test_literal_must_allow_bash(tmp_path, case):
    _allow_literal("bash", tmp_path, case)


@pytest.mark.parametrize("case", _sample(
    MUST_ALLOW_LITERAL, ("s8a-plan-out", "s8a-ps-plan"), (tcg.needs_pwsh,)))
def test_literal_must_allow_pwsh(tmp_path, case):
    _allow_literal("pwsh", tmp_path, case)


@pytest.mark.parametrize("case", NOW_NOT_LITERAL, ids=_ids(NOW_NOT_LITERAL))
def test_formerly_allowed_quoting_is_now_refused(tmp_path, case):
    _deny("python", tmp_path, case)


@pytest.mark.parametrize("case", ASK_LITERAL, ids=_ids(ASK_LITERAL))
def test_literal_asks_when_attended(tmp_path, case):
    _ask("python", tmp_path, case)


def test_literal_tables_are_big_enough_and_distinct():
    """Step 8 asks for at least 30 must-block rows; ids never repeat."""
    assert len(MUST_BLOCK_LITERAL) >= 30
    assert len(NOW_NOT_LITERAL) == 20
    ids = _ids(MUST_BLOCK_LITERAL + MUST_ALLOW_LITERAL + ASK_LITERAL
               + NOW_NOT_LITERAL)
    assert len(ids) == len(set(ids))


# --- Step 9: gate on the command being run ------------------------------------
#
# Step 8 gated every line on which ANY word dequoted to terraform, terragrunt
# or tofu, so `git commit -m "fix terraform apply"` was refused unattended and
# under the default `block` -- an over-block of ordinary work. The gate now
# applies when the COMMAND WORD (after assignments, reserved words and the
# wrappers `_unwrap` knows) dequotes to one of them, when a shell-evaluating
# construct (`bash -c`, `eval`, `pwsh -c`, a substitution) carries such a
# command, or when the command word cannot be read at all and the line names
# terraform, destroy, apply or workspace. Every Step 8 must-block row above
# still blocks; these add the rows the narrowing must not reopen.

S9_MUST_ALLOW = _normalise([
    # The eleven the plan names. Measured at a2807881, the first four and
    # `printf` were refused; `echo`, `jq`, `vim`, `cat | grep`, `gh pr` and
    # `$EDITOR` were already allowed (no word dequotes to a bare name, or
    # every word is plain), so they pin the narrowing from the other side.
    ("s9a-commit-message", "Bash", 'git commit -m "fix terraform apply"',
     _o(**_STAGING)),
    ("s9a-log-grep", "Bash", "git log --grep='terraform destroy'",
     _o(**_STAGING)),
    ("s9a-grep", "Bash", "grep -r 'terraform apply' .", _o(**_STAGING)),
    ("s9a-rg", "Bash", 'rg "tofu destroy"', _o(**_STAGING)),
    ("s9a-echo", "Bash", "echo terraform", _o(**_STAGING)),
    ("s9a-printf", "Bash", "printf '%s' terragrunt", _o(**_STAGING)),
    ("s9a-jq", "Bash", "jq '.terraform' f.json", _o(**_STAGING)),
    ("s9a-vim", "Bash", "vim terraform.tf", _o(**_STAGING)),
    ("s9a-cat-grep", "Bash", "cat main.tf | grep terraform", _o(**_STAGING)),
    ("s9a-gh-pr", "Bash", 'gh pr create --title "terraform: x"',
     _o(**_STAGING)),
    ("s9a-editor", "Bash", "$EDITOR notes.md", _o(**_STAGING)),
    # Neighbours: the commit form Claude Code itself writes, a message inside
    # `bash -c`, and a search fed through xargs.
    ("s9a-commit-heredoc", "Bash",
     "git commit -m \"$(cat <<'EOF'\nfix: don't let terraform destroy run "
     "(again)\nEOF\n)\"", _o(**_STAGING)),
    ("s9a-bash-c-commit", "Bash", "bash -c \"git commit -m 'terraform apply'\"",
     _o(**_STAGING)),
    ("s9a-xargs-grep", "Bash", "find . -name '*.tf' | xargs grep -l terraform",
     _o(**_STAGING)),
])

_TAINT = "taint aws_instance.a"
S9_MUST_BLOCK = _normalise([
    # The thirteen the plan names.
    ("s9-quoted-name", "Bash", '"terraform" destroy', _gate()),
    ("s9-partly-quoted-name", "Bash", "t'erraform' destroy", _gate()),
    ("s9-bash-c", "Bash", 'bash -c "terraform destroy"', _gate()),
    ("s9-sh-c-tofu", "Bash", "sh -c 'tofu destroy -auto-approve'", _gate()),
    ("s9-eval", "Bash", 'eval "terraform destroy"', _gate()),
    ("s9-env-i", "Bash", "env -i terraform destroy", _lexed()),
    ("s9-sudo-terragrunt", "Bash", "sudo -u x terragrunt run-all destroy",
     _lexed()),
    ("s9-xargs", "Bash", "xargs terraform destroy < f", _lexed()),
    ("s9-variable-name", "Bash", "x=terraform; $x destroy", _gate()),
    ("s9-subst-name", "Bash", "$(printf terraform) destroy", _gate()),
    ("s9-absolute-path", "Bash", "/usr/local/bin/terraform destroy",
     _lexed()),
    ("s9-dot-slash", "Bash", "./terraform destroy", _lexed()),
    ("s9-pwsh-c", "Bash", 'pwsh -c "terraform destroy"', _gate()),
    # Neighbours: where a narrower trigger could lose the command.
    ("s9-commit-subst-destroy", "Bash",
     f'git commit -m "$(terraform {_ADESTROY})"', _gate()),
    ("s9-commit-backtick-destroy", "Bash",
     f'git commit -m "`terraform {_ADESTROY}`"', _gate()),
    ("s9-commit-heredoc-subst", "Bash",
     f'git commit -m "$(cat <<EOF\n$(terraform {_ADESTROY})\nEOF\n)"',
     _gate()),
    ("s9-pipe-to-shell", "Bash", f'echo "terraform {_ADESTROY}" | bash',
     _gate()),
    ("s9-shell-heredoc", "Bash", f"bash <<'EOF'\nterraform {_ADESTROY}\nEOF",
     _gate()),
    ("s9-source-procsub", "Bash", f"source <(echo terraform {_ADESTROY})",
     _gate()),
    ("s9-nested-bash-c", "Bash", "bash -c 'bash -c \"terraform destroy\"'",
     _gate()),
    ("s9-unknown-wrapper", "Bash",
     "strace -f terraform $'\\x64estroy' -auto-approve", _gate()),
    ("s9-aws-vault", "Bash",
     'aws-vault exec prod -- terraform "destroy" -auto-approve', _gate()),
    ("s9-watch-string", "Bash", f'watch -n 5 "terraform {_ADESTROY}"',
     _gate()),
    ("s9-find-exec", "Bash",
     f'find . -maxdepth 0 -exec "terraform" {_ADESTROY} \\;', _gate()),
    ("s9-ssh", "Bash", f'ssh host "terraform {_ADESTROY}"', _gate()),
    ("s9-alias", "Bash", "alias tf=terraform\ntf \"destroy\" -auto-approve",
     _gate()),
    ("s9-function", "Bash", 'f() { terraform "$@"; }; f destroy', _gate()),
    ("s9-case", "Bash", f'case x in x) "terraform" {_ADESTROY};; esac',
     _gate()),
    ("s9-sudo-quoted", "Bash", f'sudo -u x "terraform" {_ADESTROY}',
     _gate()),
    ("s9-timeout-variable", "Bash", f'timeout "$T" terraform {_ADESTROY}',
     _gate()),
    ("s9-env-variable", "Bash", f'env "$X" terraform {_ADESTROY}', _gate()),
    ("s9-empty-prefix", "Bash", f"$NOTHING terraform {_ADESTROY}", _gate()),
    ("s9-group", "Bash", f'{{ "terraform" {_ADESTROY}; }}', _gate()),
    ("s9-subshell", "Bash", f'( cd . && "terraform" {_ADESTROY} )', _gate()),
    ("s9-if", "Bash", f'if true; then "terraform" {_ADESTROY}; fi', _gate()),
    ("s9-redirect-first", "Bash", f'>out.log "terraform" {_ADESTROY}',
     _gate()),
    ("s9-fd-redirect-first", "Bash", f'2>/dev/null "terraform" {_ADESTROY}',
     _gate()),
    ("s9-assignment-quoted", "Bash", f'X="a b" "terraform" {_ADESTROY}',
     _gate()),
    ("s9-eval-variable", "Bash", f'eval "$PREFIX" terraform {_ADESTROY}',
     _gate()),
    # Rows for one branch each: a verb-less subcommand behind a wrapper or a
    # redirection, which the argument-pair fallback does not catch, so only
    # that branch gates it; a delimiter bash and a naive dequote end apart;
    # an expansion glued to the name where the reader gives up; a short glob.
    # (`taint` since round 5: `plan` is read-only and no longer gated.)
    ("s9-env-quoted-plan", "Bash", f'env -i "terraform" {_TAINT}', _gate()),
    ("s9-redirect-plan", "Bash", f'>out.log "terraform" {_TAINT}', _gate()),
    ("s9-fd-redirect-plan", "Bash", f'2>/dev/null "terraform" {_TAINT}',
     _gate()),
    ("s9-heredoc-backslash-quoted-delim", "Bash",
     f"cat <<'E\\OF'\nE\\OF\n\"terraform\" {_ADESTROY}\nEOF", _gate()),
    ("s9-backquote-empty-prefix", "Bash",
     f'true `<<EOF;"$x"terraform {_ADESTROY}`', _gate()),
    ("s9-short-glob-destroy", "Bash", f"/usr/bin/t* {_ADESTROY}", _gate()),
])


@pytest.mark.parametrize("case", S9_MUST_ALLOW, ids=_ids(S9_MUST_ALLOW))
def test_command_word_must_allow_python(tmp_path, case):
    _allow_literal("python", tmp_path, case)


@pytest.mark.parametrize("case", _sample(
    S9_MUST_ALLOW, ("s9a-commit-message", "s9a-commit-heredoc"),
    (tcg.needs_bash,)))
def test_command_word_must_allow_bash(tmp_path, case):
    _allow_literal("bash", tmp_path, case)


@pytest.mark.parametrize("case", S9_MUST_BLOCK, ids=_ids(S9_MUST_BLOCK))
def test_command_word_must_block_python(tmp_path, case):
    _deny("python", tmp_path, case)


@pytest.mark.parametrize("case", _sample(
    S9_MUST_BLOCK, ("s9-variable-name", "s9-commit-subst-destroy"),
    (tcg.needs_bash,)))
def test_command_word_must_block_bash(tmp_path, case):
    _deny("bash", tmp_path, case)


def test_command_word_tables_are_distinct():
    """Step 9 names eleven must-allow and thirteen must-block rows; ids never
    repeat across the Step 8 and Step 9 tables."""
    assert len(S9_MUST_ALLOW) >= 11 and len(S9_MUST_BLOCK) >= 13
    ids = _ids(MUST_BLOCK_LITERAL + MUST_ALLOW_LITERAL + ASK_LITERAL
               + NOW_NOT_LITERAL + S9_MUST_ALLOW + S9_MUST_BLOCK)
    assert len(ids) == len(set(ids))


# --- Review round 5 (kF0AM1): lines the lexer does not follow, and read-only
# subcommands --------------------------------------------------------------
#
# Round 5 found two ways the gate's answer was thrown away. A line of plain
# words that runs terraform where the lexer does not look -- an alias, `hash
# -p`, a copied or linked binary, zsh's `=terraform`, a wrapper `_unwrap` does
# not strip, PowerShell's `Set-Alias` or `Start-Process` -- was handed to the
# lexer, which saw no terraform and allowed it. Such a command is now UNSEEN,
# and an unseen command makes the line "could not tell" even when every word
# is plain. And the other way: a read-only subcommand (`plan`, `show`,
# `output`, `fmt`, ...) and a data command's arguments (`cp -r terraform
# "$BACKUP_DIR"`) are no longer gated for their quoting, as before Step 8.
#
# Every must-block row is built so that the value the old reading collapsed
# to is ALLOW (measured at eae90e9b): the clean staging plan, summary and
# workspace file, under `ask`, unattended.
UNSEEN_WHY = "does not follow"


def _unseen(**kw):
    return _o(**{**_STAGING, "why": UNSEEN_WHY, **kw})


R5_MUST_BLOCK = _normalise([
    # BLOCK 1: the gate named the line, the lexer could not follow it.
    ("r5-hash-p", "Bash",
     f"hash -p /usr/bin/terraform ls; ls {_ADESTROY}", _unseen()),
    ("r5-alias", "Bash",
     f"shopt -s expand_aliases\nalias tf=terraform\ntf {_ADESTROY}",
     _unseen()),
    ("r5-alias-tofu-ws-delete", "Bash",
     "shopt -s expand_aliases\nalias tf=tofu\ntf workspace delete "
     "production", _unseen()),
    ("r5-ln-dot-slash", "Bash",
     f"ln -sf /usr/bin/terraform tf && ./tf {_ADESTROY}", _unseen()),
    # Neighbours: a copy under a data command's name, run from a PATH the
    # line sets; and a followed apply beside an unseen destroy, which a
    # line-wide "the lexer found a terraform command" check would pass.
    ("r5-cp-bare-name", "Bash",
     f"cp /usr/bin/terraform ./ls && PATH=.:/usr/bin ls {_ADESTROY}",
     _unseen()),
    ("r5-seen-apply-beside-unseen", "Bash",
     f"terraform apply {PLAN} && strace -f terraform destroy", _unseen()),
    ("r5-zsh-copy-bare-name", "Bash",
     f"cp =terraform ./ls && PATH=.:/usr/bin ls {_ADESTROY}", _unseen()),
    ("r5-sudo-ln-path", "Bash",
     f"sudo ln -s /usr/bin/terraform /usr/local/bin/tf; tf {_ADESTROY}",
     _unseen()),
    ("r5-container-image", "Bash",
     f"docker run --rm hashicorp/terraform:1.9 {_ADESTROY}", _unseen()),
    # A data command's exemption must not cover what it runs: `git bisect
    # run`, `rg --pre`; and a copy made inside `bash -c` still renames.
    ("r5-git-bisect-run", "Bash", "git bisect run terraform destroy",
     _unseen()),
    ("r5-git-dash-c-bisect-run", "Bash",
     "git -C infra bisect run terraform destroy", _unseen()),
    ("r5-git-dash-c-value-is-a-subcommand", "Bash",
     "git -C add bisect run terraform destroy", _unseen()),
    ("r5-rg-pre", "Bash", "rg --pre terraform destroy .", _unseen()),
    ("r5-nested-copy-bare-name", "Bash",
     "bash -c 'cp /usr/bin/terraform ./ls' && PATH=.:/usr/bin ls "
     f"{_ADESTROY}", _gate()),
    # FIX 1: wrappers the lexer does not strip.
    ("r5-flock", "Bash", "flock /tmp/l terraform destroy", _unseen()),
    ("r5-strace", "Bash", "strace -f terraform destroy", _unseen()),
    ("r5-aws-vault", "Bash", "aws-vault exec p -- terraform destroy",
     _unseen()),
    ("r5-unbuffer", "Bash", "unbuffer terraform destroy", _unseen()),
    ("r5-systemd-run", "Bash", "systemd-run terraform destroy", _unseen()),
    # FIX 4: zsh's `=terraform`, as the command word and behind wrappers.
    ("r5-zsh-equals", "Bash", f"=terraform {_ADESTROY}", _unseen()),
    ("r5-zsh-equals-tofu-ws-delete", "Bash",
     "=tofu workspace delete production", _unseen()),
    ("r5-zsh-equals-env", "Bash", "env =terraform destroy", _unseen()),
    ("r5-zsh-equals-strace", "Bash", "strace =terraform destroy", _unseen()),
    # With no verb on the line only the command-word branches gate these:
    # a read-only-or-not subcommand crew does not judge, behind a name only
    # zsh or a brace list makes.
    ("r5-zsh-equals-taint", "Bash", f"=terraform {_TAINT}", _unseen()),
    ("r5-brace-name-taint", "Bash", f"t{{erraform,x}} {_TAINT}", _gate()),
    # BLOCK 2: PowerShell aliases and launchers.
    ("r5-ps-set-alias", "PowerShell", "Set-Alias tf terraform; tf destroy",
     _unseen()),
    ("r5-ps-new-alias", "PowerShell", "New-Alias tf terraform; tf destroy",
     _unseen()),
    ("r5-ps-sal", "PowerShell", "sal tf terraform; tf destroy", _unseen()),
    ("r5-ps-set-item-alias", "PowerShell",
     "Set-Item alias:tf terraform; tf destroy", _unseen()),
    ("r5-ps-ni-alias", "PowerShell",
     "ni alias:tf -Value terraform; tf destroy", _unseen()),
    ("r5-ps-start-process", "PowerShell", "Start-Process terraform destroy",
     _unseen()),
    ("r5-ps-saps", "PowerShell", "saps terraform destroy -Wait", _unseen()),
    ("r5-ps-copied-binary", "PowerShell",
     "Copy-Item /usr/bin/terraform ./tf; ./tf destroy", _unseen()),
    ("r5-bash-pwsh-start-process", "Bash",
     "pwsh -c Start-Process terraform destroy", _unseen()),
    # FIX 2's neighbours: a subcommand spelled so it could be another one.
    ("r5-xargs-replaced-subcommand", "Bash",
     "echo destroy | xargs -I plan terraform plan -var 'x=1'", _gate()),
    ("r5-terragrunt-option-before", "Bash",
     "terragrunt --working-dir plan destroy -auto-approve "
     '--terragrunt-log-level "info"', _gate()),
    ("r5-find-exec-found-binary", "Bash",
     "find . -name terraform -exec {} destroy ';'", _gate()),
    # NIT 1: one row for each branch round 5 found no test for.
    ("r5-busybox-shell", "Bash", 'busybox sh -c "terraform destroy"',
     _gate()),
    ("r5-pwsh-expansion-payload", "Bash", 'x=terraform; pwsh -c "$x destroy"',
     _gate()),
    ("r5-cr-heredoc-delimiter", "Bash",
     f'cat <<EOF\nEOF\r\n"terraform" {_ADESTROY}\nEOF', _gate()),
    ("r5-quoted-newline-before-body", "Bash",
     f"cat <<EOF 'a\n\"terraform\" {_ADESTROY}\nEOF\n'\nEOF", _gate()),
])

R5_MUST_ALLOW = _normalise([
    # FIX 2: read-only subcommands, quoted, under `ask` and `block`.
    ("r5a-plan-var", "Bash", "terraform plan -var 'environment=staging'",
     _o(**_STAGING)),
    ("r5a-show-jq", "Bash",
     "terraform show -json p.tfplan | jq '.resource_changes'",
     _o(**_STAGING)),
    ("r5a-output-raw", "Bash", 'terraform output -raw "db_url"',
     _o(**_STAGING)),
    ("r5a-plan-var-block", "Bash", "terraform plan -var 'environment=staging'",
     _o(**_STAGING, **BLOCK_POLICY)),
    ("r5a-show-jq-block", "Bash",
     "terraform show -json p.tfplan | jq '.resource_changes'",
     _o(**_STAGING, **BLOCK_POLICY)),
    ("r5a-chdir-quoted", "Bash", 'terraform -chdir="envs/staging" plan',
     _o(**_STAGING)),
    ("r5a-init-backend", "Bash", 'terraform init -backend-config="key=$KEY"',
     _o(**_STAGING)),
    ("r5a-workspace-list-var", "Bash", 'terraform workspace list "$x"',
     _o(**_STAGING)),
    ("r5a-bash-c-plan", "Bash", "bash -c -- 'terraform plan'",
     _o(**_STAGING)),
    ("r5a-xargs-fmt-glob", "Bash", "ls *.tf | xargs terraform fmt",
     _o(**_STAGING)),
    ("r5a-terragrunt-plan-quoted", "Bash",
     'terragrunt plan --terragrunt-log-level "info"', _o(**_STAGING)),
    # FIX 3: data commands on a `terraform/` directory.
    ("r5a-cp-dir", "Bash", 'cp -r terraform "$BACKUP_DIR"', _o(**_STAGING)),
    ("r5a-mv-dir", "Bash", 'mv terraform "$HOME/old"', _o(**_STAGING)),
    ("r5a-git-add", "Bash", 'git add terraform "$f"', _o(**_STAGING)),
    ("r5a-git-dash-c-add", "Bash", 'git -C terraform add main.tf "$f"',
     _o(**_STAGING)),
    ("r5a-ls-dir", "Bash", "ls terraform $HOME", _o(**_STAGING)),
    ("r5a-find-dir", "Bash", "find terraform -name *.tf", _o(**_STAGING)),
    ("r5a-echo-next", "Bash", 'echo Next: terraform apply in "$dir"',
     _o(**_STAGING)),
    ("r5a-find-exec-grep", "Bash",
     "find . -name '*.tf' -exec grep -l terraform {} +", _o(**_STAGING)),
    # The new unseen rule's edges: a script file, a sourced file, a data
    # command whose operand is a verb.
    ("r5a-bash-script-file", "Bash", "terraform fmt && bash build.sh",
     _o(**_STAGING)),
    ("r5a-source-then-plan", "Bash", "source .env && terraform plan",
     _o(**_STAGING)),
    ("r5a-git-apply", "Bash", "cd terraform && git apply fix.patch",
     _o(**_STAGING)),
    ("r5a-alias-other", "Bash", "alias ll=ls; terraform plan", _o(**_STAGING)),
    ("r5a-hash-reset", "Bash", "hash -r; terraform plan", _o(**_STAGING)),
    ("r5a-which", "Bash", "which terraform", _o(**_STAGING)),
    ("r5a-container-plan", "Bash",
     "docker run --rm -v /w:/w hashicorp/terraform:1.9 plan", _o(**_STAGING)),
    ("r5a-ps-plan", "PowerShell", "Get-ChildItem; terraform plan",
     _o(**_STAGING)),
])


@pytest.mark.parametrize("case", R5_MUST_BLOCK, ids=_ids(R5_MUST_BLOCK))
def test_round5_must_block_python(tmp_path, case):
    _deny("python", tmp_path, case)


@pytest.mark.parametrize("case", _sample(
    R5_MUST_BLOCK, ("r5-alias", "r5-flock"), (tcg.needs_bash,)))
def test_round5_must_block_bash(tmp_path, case):
    _deny("bash", tmp_path, case)


@pytest.mark.parametrize("case", _sample(
    R5_MUST_BLOCK, ("r5-ps-set-alias", "r5-ps-start-process"),
    (tcg.needs_pwsh,)))
def test_round5_must_block_pwsh(tmp_path, case):
    _deny("pwsh", tmp_path, case)


@pytest.mark.parametrize("case", R5_MUST_ALLOW, ids=_ids(R5_MUST_ALLOW))
def test_round5_must_allow_python(tmp_path, case):
    _allow_literal("python", tmp_path, case)


@pytest.mark.parametrize("case", _sample(
    R5_MUST_ALLOW, ("r5a-plan-var", "r5a-cp-dir"), (tcg.needs_bash,)))
def test_round5_must_allow_bash(tmp_path, case):
    _allow_literal("bash", tmp_path, case)


@pytest.mark.parametrize("case", [
    c for c in R5_MUST_BLOCK if c[3].get("why") == UNSEEN_WHY][:3],
    ids=lambda c: c[0])
def test_round5_unseen_asks_when_attended(tmp_path, case):
    _ask("python", tmp_path, case)


def test_round5_tables_are_distinct():
    ids = _ids(MUST_BLOCK_LITERAL + MUST_ALLOW_LITERAL + ASK_LITERAL
               + NOW_NOT_LITERAL + S9_MUST_ALLOW + S9_MUST_BLOCK
               + R5_MUST_BLOCK + R5_MUST_ALLOW)
    assert len(ids) == len(set(ids))


def test_round5_unseen_reason_says_how_to_have_it_judged(tmp_path):
    """An unseen line is plain words, so the reason must not tell the user
    to 'spell it with plain words'; it names the way out that applies."""
    case = next(c for c in R5_MUST_BLOCK if c[0] == "r5-flock")
    _repo, result = _run("python", tmp_path, case)
    decision, reason, code, err = result
    assert (decision, code) == ("deny", 0), (reason, err)
    assert "run terraform by its own name" in reason, reason
    assert "plain words" not in reason, reason

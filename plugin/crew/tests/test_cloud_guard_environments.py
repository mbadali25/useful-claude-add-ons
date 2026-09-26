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

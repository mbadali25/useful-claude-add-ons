"""The cloud/destructive guard: must-block and must-allow, in every flavour.

CLAUDE.md requires a hook that can block to carry a committed regression suite
with must-block and must-allow cases, sabotage-tested. This is that suite for
`hooks/scripts/cloud_guard.py` and its two wrappers.

Every decision case runs three ways, each as its own test function so the
sabotage harness can aim at the fast one:

    python   `python3 cloud_guard.py`, the module the wrappers delegate to
    bash     `bash cloud-guard.sh`
    pwsh     `pwsh -File cloud-guard.ps1`, with `OS=Windows_NT` so its
             flavour guard (which stands it down off Windows) lets it run.
             Skipped, with the reason, where no pwsh exists.

Each case names the TOOL whose command it is (`Bash` or `PowerShell`), and the
same case runs through all three drivers: the tool decides the parser, never
the flavour of the wrapper that happened to run.

Isolation: every subprocess gets its own HOME/USERPROFILE (so the machine-
global crew config and `~/.azure` are fixtures), its own CLAUDE_PROJECT_DIR,
and an environment with every AWS_*/AZURE_*/CI/CREW_UNATTENDED variable
removed. Nothing here runs terraform, aws, az, git push or any SQL client --
the guard only reads the command text.
"""
import json
import os
import re
import subprocess
import sys
import time

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import crew_fixtures

import cloud_guard  # noqa: E402  pylint: disable=wrong-import-position
import verify_record  # noqa: E402  pylint: disable=wrong-import-position

_ROOT = context._ROOT  # pylint: disable=protected-access
_SCRIPTS = os.path.join(_ROOT, "hooks", "scripts")
_PY = os.path.join(_SCRIPTS, "cloud_guard.py")
_SH = os.path.join(_SCRIPTS, "cloud-guard.sh")
_PS1 = os.path.join(_SCRIPTS, "cloud-guard.ps1")

_BASH = crew_fixtures.resolve_bash()
_PWSH = crew_fixtures.resolve_pwsh()
needs_bash = pytest.mark.skipif(_BASH is None, reason="no MSYS/POSIX bash")
needs_pwsh = pytest.mark.skipif(
    _PWSH is None,
    reason="pwsh is not installed here, so cloud-guard.ps1 cannot be run; "
           "its cases are written and skipped, not passed")

ARMED = {"guards": {"cloudGuard": "block"}}

# A machine-global layer that widens every per-rule policy, so the identity
# rule is the only thing left that can refuse. The ratchet takes the LOWER of
# the two layers, so without this a repo's `allow` is held down to `block`.
PERMISSIVE_GLOBAL = {"guards": {"cloudDestructive": "allow",
                                "terraformApply": "allow",
                                "sqlDestructive": "allow"}}
PINNED = {"guards": {"cloudGuard": "block", "cloudDestructive": "allow",
                     "terraformApply": "allow", "sqlDestructive": "allow"},
          "cloud": {"awsProfiles": ["dev"], "awsRegions": ["eu-*"],
                    "azureSubscriptions": ["sub-dev"]}}


# --- harness ----------------------------------------------------------------


def _clean_env(tmp_path, extra=None):
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(("AWS_", "AZURE_", "ARM_"))
           and k not in ("CI", "CREW_UNATTENDED", "CLAUDE_PROJECT_DIR")}
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    env.update({"HOME": str(home), "USERPROFILE": str(home),
                "CLAUDE_PROJECT_DIR": str(tmp_path / "repo"),
                "OS": "Windows_NT", "PYTHONDONTWRITEBYTECODE": "1"})
    env.update(extra or {})
    return env


def _fixture(tmp_path, repo_cfg=None, global_cfg=None):
    repo = tmp_path / "repo"
    (repo / ".crew").mkdir(parents=True, exist_ok=True)
    if repo_cfg is not None:
        (repo / ".crew" / "config.json").write_text(json.dumps(repo_cfg),
                                                    encoding="utf-8")
    if global_cfg is not None:
        glob = tmp_path / "home" / ".claude" / "crew"
        glob.mkdir(parents=True, exist_ok=True)
        (glob / "config.json").write_text(json.dumps(global_cfg),
                                          encoding="utf-8")
    return repo


def _argv(driver):
    if driver == "python":
        return [sys.executable, _PY]
    if driver == "bash":
        return [_BASH, _SH]
    return [_PWSH, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", _PS1]


def run_hook(driver, tmp_path, tool, command, extra_env=None, payload=None):
    """(decision, reason, exit code, stderr) for one hook invocation.

    `decision` is `allow` when stdout is empty: the guard never PRINTS allow,
    so an empty stdout is the only spelling of it.
    """
    body = payload if payload is not None else {
        "tool_name": tool, "tool_input": {"command": command},
        "cwd": str(tmp_path / "repo")}
    proc = subprocess.run(
        _argv(driver), input=json.dumps(body).encode("utf-8"),
        capture_output=True, env=_clean_env(tmp_path, extra_env),
        cwd=str(tmp_path), timeout=120, check=False)
    out = proc.stdout.decode("utf-8", "replace").strip()
    err = proc.stderr.decode("utf-8", "replace")
    if not out:
        return "allow", "", proc.returncode, err
    lines = [ln for ln in out.splitlines() if ln.startswith("{")]
    assert lines, f"non-JSON stdout from {driver}: {out!r} / {err!r}"
    spec = json.loads(lines[-1])["hookSpecificOutput"]
    assert spec["hookEventName"] == "PreToolUse"
    # Printing `allow` would skip the user's own permission prompt for a
    # command the guard merely did not object to.
    assert spec["permissionDecision"] in ("deny", "ask"), spec
    return (spec["permissionDecision"], spec["permissionDecisionReason"],
            proc.returncode, err)


# --- the cases --------------------------------------------------------------
#
# (id, tool, command, rule the reason must name)

MUST_BLOCK = [
    ("tf-apply", "Bash", "terraform apply -auto-approve", "terraformApply"),
    ("tf-destroy", "Bash", "terraform destroy", "terraformApply"),
    ("tofu-apply", "Bash", "tofu apply", "terraformApply"),
    ("tf-chdir", "Bash", "terraform -chdir=infra destroy -auto-approve",
     "terraformApply"),
    ("tf-and-chain", "Bash", "cd infra && terraform apply", "terraformApply"),
    ("tf-semicolon", "Bash", "true; terraform destroy", "terraformApply"),
    ("tf-pipe", "Bash", "yes | terraform apply", "terraformApply"),
    ("tf-sudo", "Bash", "sudo -E -u deploy terraform destroy",
     "terraformApply"),
    ("tf-env-prefix", "Bash", "env TF_LOG=debug terraform apply",
     "terraformApply"),
    ("tf-assign-prefix", "Bash", "TF_LOG=1 /usr/local/bin/terraform apply",
     "terraformApply"),
    ("tf-time", "Bash", "time -p terraform destroy", "terraformApply"),
    ("tf-bash-c", "Bash", "bash -lc 'terraform destroy'", "terraformApply"),
    ("tf-subst", "Bash", 'echo "$(terraform destroy -auto-approve)"',
     "terraformApply"),
    ("aws-terminate", "Bash", "aws ec2 terminate-instances --instance-ids i-1",
     "cloudDestructive"),
    ("aws-delete", "Bash",
     "aws cloudformation delete-stack --stack-name app", "cloudDestructive"),
    ("aws-s3-rm-recursive", "Bash", "aws s3 rm s3://bucket/ --recursive",
     "cloudDestructive"),
    ("aws-s3-rb", "Bash", "aws s3 rb s3://bucket --force", "cloudDestructive"),
    ("aws-sudo-env", "Bash",
     "sudo env AWS_PROFILE=dev aws rds delete-db-instance "
     "--db-instance-identifier db1", "cloudDestructive"),
    ("az-group-delete", "Bash", "az group delete -n rg --yes",
     "cloudDestructive"),
    ("az-keyvault-purge", "Bash", "az keyvault purge --name kv",
     "cloudDestructive"),
    ("psql-c", "Bash", "psql -h db -c 'DROP TABLE users'", "sqlDestructive"),
    ("psql-e-then-c", "Bash", "psql -e -c 'truncate orders'",
     "sqlDestructive"),
    ("mysql-e", "Bash", 'mysql -e "TRUNCATE TABLE t" app', "sqlDestructive"),
    ("sqlcmd-Q", "Bash", 'sqlcmd -S srv -Q "DROP DATABASE d"',
     "sqlDestructive"),
    ("psql-heredoc", "Bash",
     "psql -h db <<'SQL'\nselect 1;\nDROP TABLE users;\nSQL",
     "sqlDestructive"),
    ("mysql-pipe", "Bash", "echo 'DROP TABLE t' | mysql app",
     "sqlDestructive"),
    ("sql-variable", "Bash", 'Q="DROP TABLE t"; psql -c "$Q"',
     "sqlDestructive"),
    ("mysql-dashdash-trick", "Bash", "mysql -e 'SELECT 1--1; DROP TABLE t'",
     "sqlDestructive"),
    ("git-force", "Bash", "git push --force origin main", "forcePush"),
    ("git-f", "Bash", "git push -f", "forcePush"),
    ("git-lease", "Bash", "git push --force-with-lease origin main",
     "forcePush"),
    ("git-plus-ref", "Bash", "git push origin +main", "forcePush"),
    ("git-chained", "Bash", "git add -A && git commit -m wip && git push -uf",
     "forcePush"),
    ("gh-admin", "Bash", "gh pr merge 12 --admin --squash", "adminMerge"),
    ("ps-tf-apply", "PowerShell", "terraform apply -auto-approve",
     "terraformApply"),
    ("ps-call-operator", "PowerShell",
     "& 'C:\\tools\\terraform.exe' destroy -auto-approve", "terraformApply"),
    ("ps-script-block", "PowerShell", "if ($true) { terraform destroy }",
     "terraformApply"),
    ("ps-aws-chain", "PowerShell",
     "Get-Date; aws ec2 terminate-instances --instance-ids i-1",
     "cloudDestructive"),
    ("ps-az-delete", "PowerShell", "az group delete -n rg --yes",
     "cloudDestructive"),
    ("ps-remove-az", "PowerShell", "Remove-AzResourceGroup -Name rg -Force",
     "cloudDestructive"),
    ("ps-invoke-sqlcmd", "PowerShell",
     'Invoke-Sqlcmd -Query "DROP TABLE t" -ServerInstance s',
     "sqlDestructive"),
    ("ps-invoke-sqlcmd-herestring", "PowerShell",
     'Invoke-Sqlcmd -ServerInstance s -Query @"\nTRUNCATE TABLE t\n"@',
     "sqlDestructive"),
    ("ps-sql-variable", "PowerShell",
     "$q = 'DROP TABLE t'; Invoke-Sqlcmd -Query $q", "sqlDestructive"),
    ("ps-sqlcmd", "PowerShell", 'sqlcmd -S s -Q "DROP DATABASE d"',
     "sqlDestructive"),
    ("ps-git-force", "PowerShell", "git push --force", "forcePush"),
]

MUST_ALLOW = [
    ("tf-plan", "Bash", "terraform plan -out plan.tfplan"),
    ("tf-init", "Bash", "terraform init && terraform validate"),
    ("aws-ls", "Bash", "aws s3 ls"),
    ("aws-describe", "Bash", "aws ec2 describe-instances"),
    ("az-list", "Bash", "az group list"),
    ("psql-select", "Bash", "psql -h db -c 'SELECT count(*) FROM users'"),
    ("sql-literal", "Bash", "psql -c \"SELECT 'DROP TABLE x' AS s\""),
    ("sql-comment", "Bash", "psql -c 'SELECT 1 -- DROP TABLE x'"),
    ("sql-block-comment", "Bash", "psql -c 'SELECT /* TRUNCATE t */ 1'"),
    ("sql-identifier", "Bash", "psql -c 'SELECT drop_count FROM stats'"),
    ("git-push", "Bash", "git push"),
    ("git-push-upstream", "Bash", "git push -u origin feature/x"),
    ("commit-message", "Bash",
     'git commit -m "terraform destroy, DROP TABLE, git push --force"'),
    ("echo-words", "Bash", "echo aws ec2 terminate-instances"),
    ("grep-words", "Bash", "grep -rn 'terraform apply' docs/"),
    # A `;` inside a comment would split off a command if the comment were
    # not read as one -- which is what makes these two cases load-bearing.
    ("bash-comment", "Bash", "ls  # then; terraform destroy"),
    ("gh-merge", "Bash", "gh pr merge 12 --squash"),
    ("ps-tf-plan", "PowerShell", "Get-ChildItem; terraform plan"),
    ("ps-comment", "PowerShell",
     'Write-Output "terraform destroy" # then; terraform destroy'),
    ("ps-select", "PowerShell",
     "Invoke-Sqlcmd -Query \"SELECT 'DROP' AS s\" -ServerInstance s"),
    ("ps-git-push", "PowerShell", "git push origin main"),
    ("ps-az-list", "PowerShell", "az group list"),
]

# Identity cases: (id, tool, command, repo cfg, global cfg, extra env,
# expected decision, rule the reason must name).
IDENTITY = [
    ("aws-wrong-profile", "Bash", "aws s3 ls --profile prod", PINNED,
     PERMISSIVE_GLOBAL, {}, "deny", "cloudIdentity"),
    ("aws-wrong-region", "Bash",
     "AWS_PROFILE=dev aws ec2 terminate-instances --region us-east-1",
     PINNED, PERMISSIVE_GLOBAL, {}, "deny", "cloudIdentity"),
    ("aws-wrong-profile-inherited", "Bash", "aws s3 ls --region eu-west-1",
     PINNED, PERMISSIVE_GLOBAL, {"AWS_PROFILE": "prod"}, "deny",
     "cloudIdentity"),
    ("az-wrong-sub", "Bash", "az group delete -n rg --subscription sub-prod",
     PINNED, PERMISSIVE_GLOBAL, {}, "deny", "cloudIdentity"),
    ("az-wrong-default-sub", "Bash", "az group list", PINNED,
     PERMISSIVE_GLOBAL, {"AZURE_SUBSCRIPTION_ID": "sub-prod"}, "deny",
     "cloudIdentity"),
    ("ps-env-wrong-profile", "PowerShell",
     "$env:AWS_PROFILE = 'prod'; aws s3 ls --region eu-west-1", PINNED,
     PERMISSIVE_GLOBAL, {}, "deny", "cloudIdentity"),
    ("aws-unknown-unattended", "Bash", "aws ec2 terminate-instances",
     PINNED, PERMISSIVE_GLOBAL, {"CREW_UNATTENDED": "1"}, "deny",
     "cloudIdentity"),
    ("aws-unknown-ci", "Bash", "aws s3 ls", PINNED, PERMISSIVE_GLOBAL,
     {"CI": "true"}, "deny", "cloudIdentity"),
    ("aws-unknown-attended", "Bash", "aws ec2 terminate-instances",
     PINNED, PERMISSIVE_GLOBAL, {}, "ask", "cloudIdentity"),
    ("aws-static-keys", "Bash",
     "AWS_PROFILE=dev aws ec2 terminate-instances --region eu-west-1",
     PINNED, PERMISSIVE_GLOBAL, {"AWS_ACCESS_KEY_ID": "AKIAEXAMPLE"},
     "ask", "cloudIdentity"),
    ("aws-nothing-pinned-destructive", "Bash",
     "AWS_PROFILE=dev aws ec2 terminate-instances",
     {"guards": PINNED["guards"]}, PERMISSIVE_GLOBAL,
     {"CREW_UNATTENDED": "1"}, "deny", "cloudIdentity"),
    ("az-unknown-unattended", "Bash", "az group delete -n rg", PINNED,
     PERMISSIVE_GLOBAL, {"CREW_UNATTENDED": "1"}, "deny", "cloudIdentity"),
    ("azps-unknown", "PowerShell", "Remove-AzResourceGroup -Name rg", PINNED,
     PERMISSIVE_GLOBAL, {}, "ask", "cloudIdentity"),
    ("aws-pinned-ok", "Bash",
     "AWS_PROFILE=dev aws ec2 terminate-instances --region eu-west-1",
     PINNED, PERMISSIVE_GLOBAL, {}, "allow", ""),
    ("aws-export-ok", "Bash",
     "export AWS_PROFILE=dev AWS_REGION=eu-west-1; aws ec2 "
     "terminate-instances", PINNED, PERMISSIVE_GLOBAL, {}, "allow", ""),
    ("az-pinned-ok", "Bash", "az group delete -n rg --subscription sub-dev",
     PINNED, PERMISSIVE_GLOBAL, {}, "allow", ""),
    ("aws-read-unpinned-ok", "Bash", "aws s3 ls",
     {"guards": PINNED["guards"]}, PERMISSIVE_GLOBAL, {}, "allow", ""),
    ("ps-env-pinned-ok", "PowerShell",
     "$env:AWS_PROFILE = 'dev'; aws ec2 terminate-instances --region "
     "eu-west-1", PINNED, PERMISSIVE_GLOBAL, {}, "allow", ""),
]


def _block(driver, tmp_path, case):
    _id, tool, command, rule = case
    _fixture(tmp_path, ARMED)
    decision, reason, code, err = run_hook(driver, tmp_path, tool, command)
    assert code == 0, err
    assert decision == "deny", (command, decision, err)
    assert f"[{rule}]" in reason, reason


def _allow(driver, tmp_path, case):
    _id, tool, command = case
    _fixture(tmp_path, ARMED)
    decision, reason, code, err = run_hook(driver, tmp_path, tool, command)
    assert code == 0, err
    assert decision == "allow", (command, reason, err)


def _identity(driver, tmp_path, case):
    _id, tool, command, repo_cfg, global_cfg, env, want, rule = case
    _fixture(tmp_path, repo_cfg, global_cfg)
    decision, reason, code, err = run_hook(driver, tmp_path, tool, command,
                                           extra_env=env)
    assert code == 0, err
    assert decision == want, (command, decision, reason, err)
    if rule:
        assert f"[{rule}]" in reason, reason


_B_IDS = [c[0] for c in MUST_BLOCK]
_A_IDS = [c[0] for c in MUST_ALLOW]
_I_IDS = [c[0] for c in IDENTITY]


@pytest.mark.parametrize("case", MUST_BLOCK, ids=_B_IDS)
def test_must_block_python(tmp_path, case):
    _block("python", tmp_path, case)


@needs_bash
@pytest.mark.parametrize("case", MUST_BLOCK, ids=_B_IDS)
def test_must_block_bash(tmp_path, case):
    _block("bash", tmp_path, case)


@needs_pwsh
@pytest.mark.parametrize("case", MUST_BLOCK, ids=_B_IDS)
def test_must_block_pwsh(tmp_path, case):
    _block("pwsh", tmp_path, case)


@pytest.mark.parametrize("case", MUST_ALLOW, ids=_A_IDS)
def test_must_allow_python(tmp_path, case):
    _allow("python", tmp_path, case)


@needs_bash
@pytest.mark.parametrize("case", MUST_ALLOW, ids=_A_IDS)
def test_must_allow_bash(tmp_path, case):
    _allow("bash", tmp_path, case)


@needs_pwsh
@pytest.mark.parametrize("case", MUST_ALLOW, ids=_A_IDS)
def test_must_allow_pwsh(tmp_path, case):
    _allow("pwsh", tmp_path, case)


@pytest.mark.parametrize("case", IDENTITY, ids=_I_IDS)
def test_identity_python(tmp_path, case):
    _identity("python", tmp_path, case)


@needs_bash
@pytest.mark.parametrize("case", IDENTITY, ids=_I_IDS)
def test_identity_bash(tmp_path, case):
    _identity("bash", tmp_path, case)


@needs_pwsh
@pytest.mark.parametrize("case", IDENTITY, ids=_I_IDS)
def test_identity_pwsh(tmp_path, case):
    _identity("pwsh", tmp_path, case)


# --- the switch, and what it does when on -----------------------------------

_DRIVERS = [
    pytest.param("python", id="python"),
    pytest.param("bash", id="bash", marks=needs_bash),
    pytest.param("pwsh", id="pwsh", marks=needs_pwsh),
]


@pytest.mark.parametrize("driver", _DRIVERS)
@pytest.mark.parametrize("repo_cfg", [None, {}, {"guards": {}},
                                      {"guards": {"cloudGuard": "off"}}],
                         ids=["no-config", "empty", "no-key", "off"])
def test_disabled_guard_allows_everything(tmp_path, driver, repo_cfg):
    """Off is the default: a repo that never set `guards.cloudGuard` runs
    `terraform destroy` exactly as it did before this hook existed."""
    _fixture(tmp_path, repo_cfg)
    decision, reason, code, err = run_hook(driver, tmp_path, "Bash",
                                           "terraform destroy -auto-approve")
    assert (decision, code) == ("allow", 0), (reason, err)


def test_default_config_ships_the_guard_off():
    import crew_config  # pylint: disable=import-outside-toplevel
    assert crew_config.default_config()["guards"]["cloudGuard"] == "off"
    assert crew_config.default_global_config()["guards"]["cloudGuard"] == "off"
    assert crew_config.default_config()["cloud"] == {
        "awsProfiles": [], "awsRegions": [], "azureSubscriptions": []}
    assert "cloud" not in crew_config.default_global_config()


@pytest.mark.parametrize("driver", _DRIVERS)
def test_a_global_block_cannot_be_turned_off_by_a_repo(tmp_path, driver):
    """The ratchet: a cloned repo's `off` does not disarm the machine's
    `block`."""
    _fixture(tmp_path, {"guards": {"cloudGuard": "off"}},
             {"guards": {"cloudGuard": "block"}})
    decision, _reason, _code, err = run_hook(driver, tmp_path, "Bash",
                                             "terraform destroy")
    assert decision == "deny", err


@pytest.mark.parametrize("driver", _DRIVERS)
def test_report_mode_refuses_nothing_and_logs_what_it_would_have(tmp_path,
                                                                   driver):
    repo = _fixture(tmp_path, {"guards": {"cloudGuard": "report"}})
    decision, _reason, code, err = run_hook(driver, tmp_path, "Bash",
                                            "terraform destroy")
    assert (decision, code) == ("allow", 0), err
    log = (repo / ".crew" / "guard.log").read_text(encoding="utf-8")
    assert "\tterraformApply\tblock\treport:deny\t" in log


@pytest.mark.parametrize("driver", _DRIVERS)
def test_a_corrupt_config_fails_closed(tmp_path, driver):
    repo = _fixture(tmp_path)
    (repo / ".crew" / "config.json").write_text("{not json", encoding="utf-8")
    decision, _reason, _code, err = run_hook(driver, tmp_path, "Bash",
                                             "terraform destroy")
    assert decision == "deny", err


@pytest.mark.parametrize("driver", _DRIVERS)
def test_ask_policy_prompts_when_attended(tmp_path, driver):
    _fixture(tmp_path, {"guards": {"cloudGuard": "block",
                                   "terraformApply": "ask"}},
             {"guards": {"terraformApply": "ask"}})
    decision, reason, _code, err = run_hook(driver, tmp_path, "Bash",
                                            "terraform apply")
    assert decision == "ask", err
    assert "[terraformApply]" in reason


@pytest.mark.parametrize("driver", _DRIVERS)
@pytest.mark.parametrize("how", [{"CREW_UNATTENDED": "1"}, {"CI": "1"},
                                 "bypassPermissions", "dontAsk"],
                         ids=["CREW_UNATTENDED", "CI", "bypass", "dontAsk"])
def test_ask_is_denied_when_nobody_is_attending(tmp_path, driver, how):
    _fixture(tmp_path, {"guards": {"cloudGuard": "block",
                                   "terraformApply": "ask"}},
             {"guards": {"terraformApply": "ask"}})
    env = how if isinstance(how, dict) else {}
    payload = {"tool_name": "Bash",
               "tool_input": {"command": "terraform apply"},
               "cwd": str(tmp_path / "repo")}
    if isinstance(how, str):
        payload["permission_mode"] = how
    decision, reason, _code, err = run_hook(driver, tmp_path, "Bash", "",
                                            extra_env=env, payload=payload)
    assert decision == "deny", err
    assert ".approved-guard-terraformApply-" in reason


@pytest.mark.parametrize("driver", _DRIVERS)
def test_a_live_approval_marker_lets_one_command_through(tmp_path, driver):
    repo = _fixture(tmp_path, {"guards": {"cloudGuard": "block",
                                          "terraformApply": "ask"}},
                    {"guards": {"terraformApply": "ask"}})
    env = {"CREW_UNATTENDED": "1"}
    decision, reason, _c, _e = run_hook(driver, tmp_path, "Bash",
                                        "terraform apply", extra_env=env)
    assert decision == "deny"
    marker = re.search(r"(\S*\.approved-guard-terraformApply-[0-9a-f]+)",
                       reason).group(1)
    assert os.path.dirname(marker) == str(repo / ".crew")
    with open(marker, "w", encoding="utf-8"):
        pass
    assert run_hook(driver, tmp_path, "Bash", "terraform apply",
                    extra_env=env)[0] == "allow"
    # The approval names ONE command: a different one still refuses.
    assert run_hook(driver, tmp_path, "Bash", "terraform destroy",
                    extra_env=env)[0] == "deny"
    # And it expires.
    old = time.time() - 3600
    os.utime(marker, (old, old))
    assert run_hook(driver, tmp_path, "Bash", "terraform apply",
                    extra_env=env)[0] == "deny"


@pytest.mark.parametrize("driver", _DRIVERS)
def test_azure_default_subscription_is_read_from_the_cli_profile(tmp_path,
                                                                driver):
    _fixture(tmp_path, PINNED, PERMISSIVE_GLOBAL)
    azure = tmp_path / "home" / ".azure"
    azure.mkdir(parents=True)
    profile = {"subscriptions": [
        {"id": "sub-prod", "name": "Production", "isDefault": False},
        {"id": "sub-dev", "name": "Dev", "isDefault": True}]}
    # utf-8-sig: the az CLI writes this file with a BOM.
    (azure / "azureProfile.json").write_text(json.dumps(profile),
                                             encoding="utf-8-sig")
    assert run_hook(driver, tmp_path, "Bash", "az group delete -n rg",
                    extra_env={"CREW_UNATTENDED": "1"})[0] == "allow"
    profile["subscriptions"][0]["isDefault"] = True
    profile["subscriptions"][1]["isDefault"] = False
    (azure / "azureProfile.json").write_text(json.dumps(profile),
                                             encoding="utf-8-sig")
    assert run_hook(driver, tmp_path, "Bash", "az group delete -n rg",
                    extra_env={"CREW_UNATTENDED": "1"})[0] == "deny"


@pytest.mark.parametrize("driver", _DRIVERS)
def test_malformed_pins_make_every_cloud_identity_unknown(tmp_path, driver):
    """`"awsProfiles": "dev"` -- a string where a list belongs -- is not
    "nothing pinned". Read as nothing pinned, `aws s3 ls` would run
    unchecked in the one repo whose owner tried to pin it."""
    cfg = {"guards": PINNED["guards"], "cloud": {"awsProfiles": "dev"}}
    _fixture(tmp_path, cfg, PERMISSIVE_GLOBAL)
    decision, reason, _c, err = run_hook(
        driver, tmp_path, "Bash", "aws s3 ls --profile dev",
        extra_env={"CREW_UNATTENDED": "1"})
    assert decision == "deny", err
    assert "could not read the identity pins" in reason


@pytest.mark.parametrize("driver", _DRIVERS)
def test_production_database_patterns_are_wired(tmp_path, driver):
    _fixture(tmp_path, {"guards": {"cloudGuard": "block"},
                        "production": {"databases": ["prod-db-*"]}})
    decision, reason, _c, err = run_hook(
        driver, tmp_path, "Bash", "psql -h prod-db-1 -c 'SELECT 1'")
    assert decision == "deny", err
    assert "[prodDatabase]" in reason
    assert run_hook(driver, tmp_path, "Bash",
                    "psql -h dev-db-1 -c 'SELECT 1'")[0] == "allow"


@pytest.mark.parametrize("driver", _DRIVERS)
def test_other_tools_are_not_judged(tmp_path, driver):
    _fixture(tmp_path, ARMED)
    payload = {"tool_name": "Write",
               "tool_input": {"file_path": "x", "content": "terraform destroy"}}
    assert run_hook(driver, tmp_path, "Write", "", payload=payload)[0] == \
        "allow"


# --- the wrappers' own fallback ---------------------------------------------

_NO_PYTHON = {"PYTHONHOME": "/nonexistent-python-home"}


@needs_bash
@pytest.mark.parametrize("armed", [True, False], ids=["armed", "not-armed"])
def test_bash_wrapper_without_python(tmp_path, armed):
    """No usable python: armed fails closed (exit 2), unarmed stays out of the
    way. `PYTHONHOME` pointing nowhere makes every interpreter fail to start,
    which is what the resolver's own probe sees."""
    _fixture(tmp_path, ARMED if armed else {"guards": {"cloudGuard": "off"}})
    proc = subprocess.run(
        [_BASH, _SH], input=b'{"tool_name":"Bash","tool_input":'
                            b'{"command":"terraform destroy"}}',
        capture_output=True, env=_clean_env(tmp_path, _NO_PYTHON),
        timeout=60, check=False)
    assert proc.returncode == (2 if armed else 0), proc.stderr


@needs_pwsh
@pytest.mark.parametrize("armed", [True, False], ids=["armed", "not-armed"])
def test_pwsh_wrapper_without_python(tmp_path, armed):
    _fixture(tmp_path, ARMED if armed else {"guards": {"cloudGuard": "off"}})
    proc = subprocess.run(
        _argv("pwsh"), input=b'{"tool_name":"Bash","tool_input":'
                             b'{"command":"terraform destroy"}}',
        capture_output=True, env=_clean_env(tmp_path, _NO_PYTHON),
        timeout=120, check=False)
    assert proc.returncode == (2 if armed else 0), proc.stderr


@needs_pwsh
def test_pwsh_wrapper_stands_down_off_windows(tmp_path):
    _fixture(tmp_path, ARMED)
    env = _clean_env(tmp_path)
    env.pop("OS")
    proc = subprocess.run(
        _argv("pwsh"), input=b'{"tool_name":"Bash","tool_input":'
                             b'{"command":"terraform destroy"}}',
        capture_output=True, env=env, timeout=120, check=False)
    assert (proc.returncode, proc.stdout) == (0, b"")


# --- the pieces, in-process -------------------------------------------------


@pytest.mark.parametrize("sql,want", [
    ("DROP TABLE t", True),
    ("truncate t", True),
    ("ALTER TABLE t DROP COLUMN c", True),
    ("SELECT 'DROP TABLE t'", False),
    ('SELECT "drop"', False),
    ("SELECT 1 -- DROP TABLE t", False),
    ("SELECT 1 /* DROP TABLE t */", False),
    ("SELECT drop_count FROM t", False),
    # MySQL reads `\'` as an escaped quote, so the DROP is live there.
    ("SELECT 'a\\'' ; DROP TABLE t; -- '", True),
    # MySQL needs a space after `--`: `1--1` is arithmetic.
    ("SELECT 1--1; DROP TABLE t", True),
    # MySQL executes `/*! ... */`.
    ("SELECT 1 /*!50000 DROP TABLE t */", True),
    ("", False),
])
def test_sql_is_destructive(sql, want):
    assert cloud_guard.sql_is_destructive(sql) is want


def test_pinned_vars_are_one_list_in_all_three_places():
    """verify_record.PINNED_VARS, verify-gate.sh (both spellings) and
    verify-gate.ps1 must name the same variables. The comment beside
    PINNED_VARS once claimed the gates read it; they never did, so this is
    what keeps the three from drifting."""
    want = set(verify_record.PINNED_VARS)
    for name in ("AWS_REGION", "AZURE_SUBSCRIPTION_ID", "ARM_SUBSCRIPTION_ID",
                 "AWS_DEFAULT_PROFILE"):
        assert name in want
    with open(os.path.join(_SCRIPTS, "verify-gate.sh"),
              encoding="utf-8") as handle:
        sh_text = handle.read()
    py_tuple = re.search(r'for v in \(("ENV".*?)\):', sh_text, re.S).group(1)
    assert set(re.findall(r'"(\w+)"', py_tuple)) == want
    bash_loop = re.search(r"for v in (ENV [^;]*?); do", sh_text, re.S).group(1)
    assert set(bash_loop.replace("\\", " ").split()) == want
    with open(os.path.join(_SCRIPTS, "verify-gate.ps1"),
              encoding="utf-8") as handle:
        ps_text = handle.read()
    ps_list = re.search(r'foreach \(\$v in @\(("ENV".*?)\)\)', ps_text,
                        re.S).group(1)
    assert set(re.findall(r'"(\w+)"', ps_list)) == want


def test_scan_does_not_judge_words_inside_arguments():
    """The reason the previous command guard was removed: it matched words
    anywhere. Nothing an argument SAYS is a finding."""
    for command in ('git commit -m "terraform destroy"',
                    "echo DROP TABLE users | tee notes.txt",
                    "gh pr comment 3 --body 'az group delete ran'"):
        rules = {f.rule for f in cloud_guard.scan("bash", command)}
        assert not rules & {"terraformApply", "cloudDestructive",
                            "sqlDestructive", "forcePush"}, command

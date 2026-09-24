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

The python driver runs every case by default. The bash and pwsh drivers run a
parity sample by default (`_B_SHELL`, `_A_SHELL`, `_I_SHELL`,
`_DRIVERS_SAMPLE`, and the wrapper tests at the end) and the rest of the
matrix as `slow` -- `pytest -m slow` or `--run-slow` (see conftest.py).

Each case names the TOOL whose command it is (`Bash` or `PowerShell`), and the
same case runs through all three drivers: the tool decides the parser, never
the flavour of the wrapper that happened to run. The tool also decides which
flavour judges on Windows, where both run: bash judges every Bash call and the
.ps1 every PowerShell call. So through the pwsh driver a Bash case asserts
that the .ps1 STOOD DOWN (no output, exit 0) -- bash judges it -- and the
switch tests below pick the tool the driver actually judges (`_tool`).

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


def _clean_env(tmp_path, extra=None, driver=None):
    """The subprocess environment. `OS=Windows_NT` goes to the pwsh driver
    ONLY: it is what lets the .ps1's flavour guard proceed, and it is also
    what stands the BASH wrapper down for PowerShell calls -- so handing it
    to every driver would turn each bash PowerShell case into a stand-down
    that passes every must-allow and fails every must-block for the wrong
    reason."""
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(("AWS_", "AZURE_", "ARM_"))
           and k not in ("CI", "CREW_UNATTENDED", "CLAUDE_PROJECT_DIR", "OS",
                         cloud_guard.FLAVOUR_VAR)}
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    env.update({"HOME": str(home), "USERPROFILE": str(home),
                "CLAUDE_PROJECT_DIR": str(tmp_path / "repo"),
                "PYTHONDONTWRITEBYTECODE": "1"})
    if driver == "pwsh":
        env["OS"] = "Windows_NT"
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


def run_hook(driver, tmp_path, tool, command, extra_env=None, payload=None,
             raw=None):
    """(decision, reason, exit code, stderr) for one hook invocation.

    `decision` is `allow` when stdout carries no permission decision: the
    guard never PRINTS allow, so its absence is the only spelling of it. A
    `systemMessage` with no decision (report mode, the one-time unpinned
    note) comes back as `reason`. `raw` sends those bytes verbatim.
    """
    body = payload if payload is not None else {
        "tool_name": tool, "tool_input": {"command": command},
        "cwd": str(tmp_path / "repo")}
    proc = subprocess.run(
        _argv(driver),
        input=raw if raw is not None else json.dumps(body).encode("utf-8"),
        capture_output=True, env=_clean_env(tmp_path, extra_env, driver),
        cwd=str(tmp_path), timeout=120, check=False)
    out = proc.stdout.decode("utf-8", "replace").strip()
    err = proc.stderr.decode("utf-8", "replace")
    if not out:
        return "allow", "", proc.returncode, err
    lines = [ln for ln in out.splitlines() if ln.startswith("{")]
    assert len(lines) == 1, f"want ONE JSON object from {driver}: {out!r}"
    doc = json.loads(lines[0])
    if "hookSpecificOutput" not in doc:
        assert set(doc) == {"systemMessage"}, doc
        return "allow", doc["systemMessage"], proc.returncode, err
    spec = doc["hookSpecificOutput"]
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
    # Review round 1 (Codex). Each was an allow before its fix.
    ("pipe-through-tee", "Bash", "echo 'DROP TABLE t;' | tee /tmp/q | psql",
     "sqlDestructive"),
    ("pipe-through-two", "Bash",
     "printf 'TRUNCATE t;' | cat | sort | mysql app", "sqlDestructive"),
    ("ps-pipe-through-tee", "PowerShell",
     "Write-Output 'DROP TABLE t' | Tee-Object -FilePath q | mysql app",
     "sqlDestructive"),
    ("xargs-terraform", "Bash", "echo destroy | xargs terraform",
     "terraformApply"),
    ("xargs-placeholder", "Bash", "echo push | xargs -I% git % --force",
     "forcePush"),
    ("xargs-git-push", "Bash", "echo --force | xargs git push", "forcePush"),
    ("xargs-aws", "Bash", "echo terminate-instances | xargs aws ec2",
     "cloudDestructive"),
    ("xargs-psql", "Bash", "echo 'DROP TABLE t' | xargs -0 psql -c",
     "sqlDestructive"),
    ("xargs-sh-placeholder", "Bash",
     "echo destroy | xargs -I{} sh -c 'terraform {}'", "cloudGuard"),
    ("parallel-terraform", "Bash", "parallel terraform ::: destroy",
     "terraformApply"),
    ("parallel-jobs", "Bash", "parallel ::: 'terraform destroy' 'ls'",
     "terraformApply"),
    ("az-option-before-verb", "Bash",
     "az group --subscription prod delete -n rg", "cloudDestructive"),
    ("ps-az-option-before-verb", "PowerShell",
     "az keyvault --subscription prod purge --name kv", "cloudDestructive"),
    ("bash-c-dashdash", "Bash", "bash -c -- 'terraform destroy'",
     "terraformApply"),
    ("bash-c-then-option", "Bash", "sh -c -e 'terraform destroy'",
     "terraformApply"),
    ("busybox-sh-c", "Bash", "busybox sh -c 'terraform destroy'",
     "terraformApply"),
    ("depth-exceeded", "Bash",
     "echo $(echo $(echo $(echo $(echo $(echo $(echo $(echo $(ls))))))))",
     "cloudGuard"),
    ("ps-depth-exceeded", "PowerShell", "(((((((((Get-Date)))))))))",
     "cloudGuard"),
    ("psql-e-string", "Bash", "psql -c \"SELECT E'\\'' ; DROP TABLE t; --'\"",
     "sqlDestructive"),
    ("azps-whatif-false", "PowerShell",
     "Remove-AzResourceGroup -Name rg -WhatIf:$false", "cloudDestructive"),
    # Review round 2 (Codex). Each was an allow before its fix.
    ("azps-whatif-quoted-value", "PowerShell",
     "Remove-AzResourceGroup -Name '-WhatIf'", "cloudDestructive"),
    ("azps-whatif-quoted-positional", "PowerShell",
     "Remove-AzResourceGroup '-WhatIf' -Force", "cloudDestructive"),
    ("azps-whatif-escaped", "PowerShell",
     "Remove-AzResourceGroup -Force `-WhatIf", "cloudDestructive"),
    ("azps-whatif-after-valued-param", "PowerShell",
     "Remove-AzResourceGroup -Name -WhatIf", "cloudDestructive"),
    ("bash-pwsh-whatif-quoted", "Bash",
     "pwsh -c \"Remove-AzResourceGroup -Name '-WhatIf'\"",
     "cloudDestructive"),
    ("xargs-exe-placeholder", "Bash", "xargs -a input -I CMD CMD destroy",
     "cloudGuard"),
    ("xargs-exe-bsd-J", "Bash", "echo terraform | xargs -J CMD CMD destroy",
     "cloudGuard"),
    ("xargs-exe-unknown-replacement", "Bash",
     "ls | xargs --replace-with=% % destroy", "cloudGuard"),
    ("parallel-exe-placeholder", "Bash", "parallel {} destroy ::: terraform",
     "cloudGuard"),
    ("mysql-no-backslash-escapes", "Bash",
     "mysql -e \"SELECT 'a\\\\' ; DROP TABLE t; -- '\"", "sqlDestructive"),
    ("mysql-escaped-quote-mode", "Bash",
     "mysql -e \"SELECT 'it\\\\'s' AS a, 'DROP' AS s\"", "sqlDestructive"),
    ("mariadb-executable-comment", "Bash",
     "mariadb -e 'SELECT 1 /*M!100000 DROP TABLE t */'", "sqlDestructive"),
    ("psql-scs-off", "Bash",
     "psql -c \"SELECT 'a\\\\', ' ; DROP TABLE t; -- '\"", "sqlDestructive"),
    ("psql-backslash-literal-scs-off", "Bash",
     "psql -c \"SELECT 'C:\\\\' AS p, 'DROP TABLE x' AS s\"",
     "sqlDestructive"),
    ("aws-dry-run-negated", "Bash",
     "aws ec2 terminate-instances --instance-ids i-1 --dry-run --no-dry-run",
     "cloudDestructive"),
    ("ps-aws-dry-run-negated", "PowerShell",
     "aws ec2 terminate-instances --dry-run --no-dry-run", "cloudDestructive"),
    ("tf-help-as-option-value", "Bash",
     "terraform destroy -auto-approve -var-file '--help'", "terraformApply"),
    ("tf-help-after-unknown-option", "Bash",
     "terraform apply -some-new-option -help", "terraformApply"),
    ("tf-help-after-dashdash", "Bash", "terraform apply -- -help",
     "terraformApply"),
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
    # Review round 1 (Codex): each was refused before its fix.
    ("aws-dry-run", "Bash",
     "aws ec2 terminate-instances --instance-ids i-1 --dry-run"),
    ("aws-s3-dryrun", "Bash", "aws s3 rm s3://bucket/ --recursive --dryrun"),
    ("tf-apply-help", "Bash", "terraform apply -help"),
    ("tf-help-destroy", "Bash", "terraform -help destroy"),
    ("azps-whatif", "PowerShell", "Remove-AzResourceGroup -Name rg -WhatIf"),
    ("sqlcmd-backslash-literal", "Bash",
     "sqlcmd -S s -Q \"SELECT 'C:\\' AS p, 'DROP TABLE x' AS s\""),
    ("ps-invoke-sqlcmd-backslash", "PowerShell",
     "Invoke-Sqlcmd -Query \"SELECT 'C:\\' AS p, 'DROP' AS s\""),
    ("bash-c-dashdash-plan", "Bash", "bash -c -- 'terraform plan'"),
    ("az-option-before-read-verb", "Bash",
     "az group --subscription dev show -n rg"),
    ("xargs-git-add", "Bash", "git ls-files -m | xargs git add"),
    ("xargs-rm", "Bash", "find . -name '*.tmp' | xargs rm"),
    ("xargs-terraform-fmt", "Bash", "ls *.tf | xargs terraform fmt"),
    ("xargs-sh-literal-script", "Bash",
     "ls | xargs sh -c 'echo \"$@\"' _"),
    ("shallow-nesting", "Bash", "echo $(echo $(echo $(ls)))"),
    # Review round 2 (Codex): the other side of each fix.
    ("azps-whatif-after-switch", "PowerShell",
     "Remove-AzResourceGroup -Name rg -Force -WhatIf"),
    ("azps-whatif-first", "PowerShell",
     "Remove-AzResourceGroup -WhatIf -Name rg"),
    ("bash-pwsh-whatif", "Bash",
     "pwsh -c 'Remove-AzResourceGroup -Name rg -WhatIf'"),
    ("xargs-abs-path", "Bash", "ls | xargs /usr/bin/rm"),
    ("xargs-placeholder-argument", "Bash", "xargs -a list -I F rm F"),
    ("mysql-comment-every-mode", "Bash",
     "mysql -e 'SELECT 1 -- DROP TABLE t'"),
    ("psql-dashdash-no-space", "Bash", "psql -c 'SELECT 1 --DROP TABLE x'"),
    ("aws-dry-run-last", "Bash",
     "aws ec2 terminate-instances --no-dry-run --dry-run"),
    ("tf-help-after-option-value", "Bash",
     "terraform apply -var-file x.tfvars -help"),
    ("tf-help-after-bool-option", "Bash",
     "terraform destroy -auto-approve -help"),
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
    # Review round 1 (Codex), the PM's rule: an identity crew cannot name is
    # unknown -- read-only included -- once ANY pin is configured.
    ("aws-read-regions-pinned-unknown-ci", "Bash",
     "aws s3 ls --region eu-west-1",
     {"guards": PINNED["guards"], "cloud": {"awsRegions": ["eu-*"]}},
     PERMISSIVE_GLOBAL, {"CI": "true"}, "deny", "cloudIdentity"),
    ("aws-read-azure-pinned-unknown-ci", "Bash", "aws s3 ls",
     {"guards": PINNED["guards"],
      "cloud": {"azureSubscriptions": ["sub-dev"]}},
     PERMISSIVE_GLOBAL, {"CI": "true"}, "deny", "cloudIdentity"),
    ("az-read-aws-pinned-unknown-ci", "Bash", "az group list",
     {"guards": PINNED["guards"], "cloud": {"awsProfiles": ["dev"]}},
     PERMISSIVE_GLOBAL, {"CI": "true"}, "deny", "cloudIdentity"),
    ("aws-read-regions-pinned-unknown-attended", "Bash",
     "aws s3 ls --region eu-west-1",
     {"guards": PINNED["guards"], "cloud": {"awsRegions": ["eu-*"]}},
     PERMISSIVE_GLOBAL, {}, "ask", "cloudIdentity"),
    # ...and the other side: nothing pinned anywhere, a read-only call with
    # no nameable identity passes, even in CI (the one-time note is below).
    ("aws-read-nothing-pinned-ci-ok", "Bash",
     "env -u AWS_PROFILE -u AWS_DEFAULT_PROFILE aws s3 ls",
     {"guards": PINNED["guards"]}, PERMISSIVE_GLOBAL, {"CI": "true"},
     "allow", ""),
    ("az-read-nothing-pinned-ci-ok", "Bash", "az group list",
     {"guards": PINNED["guards"]}, PERMISSIVE_GLOBAL, {"CI": "true"},
     "allow", ""),
    ("aws-read-known-profile-other-cloud-pinned-ok", "Bash",
     "aws s3 ls --profile dev",
     {"guards": PINNED["guards"],
      "cloud": {"azureSubscriptions": ["sub-dev"]}},
     PERMISSIVE_GLOBAL, {"CI": "true"}, "allow", ""),
]


def _tool(driver):
    """The tool whose calls `driver` judges: the .ps1 stands down for Bash
    calls (bash judges those), so a switch test run through it says
    PowerShell. Every command those tests send parses the same in both."""
    return "PowerShell" if driver == "pwsh" else "Bash"


def _stood_down(driver, tool, result):
    """True -- after asserting it stood down CLEANLY -- when `driver` is the
    .ps1 and `tool` is Bash: no output at all, exit 0."""
    if driver != "pwsh" or tool != "Bash":
        return False
    decision, reason, code, err = result
    assert (decision, reason, code) == ("allow", "", 0), (reason, err)
    return True


def _block(driver, tmp_path, case):
    _id, tool, command, rule = case
    _fixture(tmp_path, ARMED)
    result = run_hook(driver, tmp_path, tool, command)
    if _stood_down(driver, tool, result):
        return
    decision, reason, code, err = result
    assert code == 0, err
    assert decision == "deny", (command, decision, err)
    assert f"[{rule}]" in reason, reason


def _allow(driver, tmp_path, case):
    _id, tool, command = case
    _fixture(tmp_path, ARMED)
    result = run_hook(driver, tmp_path, tool, command)
    if _stood_down(driver, tool, result):
        return
    decision, reason, code, err = result
    assert code == 0, err
    assert decision == "allow", (command, reason, err)


def _identity(driver, tmp_path, case):
    _id, tool, command, repo_cfg, global_cfg, env, want, rule = case
    _fixture(tmp_path, repo_cfg, global_cfg)
    result = run_hook(driver, tmp_path, tool, command, extra_env=env)
    if _stood_down(driver, tool, result):
        return
    decision, reason, code, err = result
    assert code == 0, err
    assert decision == want, (command, decision, reason, err)
    if rule:
        assert f"[{rule}]" in reason, reason


_B_IDS = [c[0] for c in MUST_BLOCK]
_A_IDS = [c[0] for c in MUST_ALLOW]
_I_IDS = [c[0] for c in IDENTITY]

# The bash and pwsh drivers run a parity sample by default -- one Bash and one
# PowerShell case each, so the pwsh driver proves both its stand-down and a
# real decision -- and the rest of each table as `slow`. The python driver
# runs every case by default: that is where the decisions are made.
_B_SHELL = crew_fixtures.parity_sample(MUST_BLOCK, _B_IDS,
                                       {"tf-apply", "ps-tf-apply"})
_A_SHELL = crew_fixtures.parity_sample(MUST_ALLOW, _A_IDS,
                                       {"tf-plan", "ps-tf-plan"})
_I_SHELL = crew_fixtures.parity_sample(
    IDENTITY, _I_IDS, {"aws-unknown-attended", "ps-env-wrong-profile"})


@pytest.mark.parametrize("case", MUST_BLOCK, ids=_B_IDS)
def test_must_block_python(tmp_path, case):
    _block("python", tmp_path, case)


@needs_bash
@pytest.mark.parametrize("case", _B_SHELL)
def test_must_block_bash(tmp_path, case):
    _block("bash", tmp_path, case)


@needs_pwsh
@pytest.mark.parametrize("case", _B_SHELL)
def test_must_block_pwsh(tmp_path, case):
    _block("pwsh", tmp_path, case)


@pytest.mark.parametrize("case", MUST_ALLOW, ids=_A_IDS)
def test_must_allow_python(tmp_path, case):
    _allow("python", tmp_path, case)


@needs_bash
@pytest.mark.parametrize("case", _A_SHELL)
def test_must_allow_bash(tmp_path, case):
    _allow("bash", tmp_path, case)


@needs_pwsh
@pytest.mark.parametrize("case", _A_SHELL)
def test_must_allow_pwsh(tmp_path, case):
    _allow("pwsh", tmp_path, case)


@pytest.mark.parametrize("case", IDENTITY, ids=_I_IDS)
def test_identity_python(tmp_path, case):
    _identity("python", tmp_path, case)


@needs_bash
@pytest.mark.parametrize("case", _I_SHELL)
def test_identity_bash(tmp_path, case):
    _identity("bash", tmp_path, case)


@needs_pwsh
@pytest.mark.parametrize("case", _I_SHELL)
def test_identity_pwsh(tmp_path, case):
    _identity("pwsh", tmp_path, case)


# --- the switch, and what it does when on -----------------------------------

_DRIVERS = [
    pytest.param("python", id="python"),
    pytest.param("bash", id="bash", marks=(needs_bash, crew_fixtures.SLOW)),
    pytest.param("pwsh", id="pwsh", marks=(needs_pwsh, crew_fixtures.SLOW)),
]
# The same drivers with the shells in the default run, for the switch tests
# that form the per-shell parity sample: off, malformed input, ask, and a
# systemMessage passed through on stdout.
_DRIVERS_SAMPLE = [
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
    decision, reason, code, err = run_hook(driver, tmp_path, _tool(driver),
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
    decision, _reason, _code, err = run_hook(driver, tmp_path, _tool(driver),
                                             "terraform destroy")
    assert decision == "deny", err


@pytest.mark.parametrize("driver", _DRIVERS)
def test_report_mode_refuses_nothing_and_logs_what_it_would_have(tmp_path,
                                                                   driver):
    """Report mode prints NO decision -- never `allow`, which would skip the
    user's own prompt -- and a visible note of what `block` would do."""
    repo = _fixture(tmp_path, {"guards": {"cloudGuard": "report"}})
    decision, note, code, err = run_hook(driver, tmp_path, _tool(driver),
                                         "terraform destroy")
    assert (decision, code) == ("allow", 0), err
    assert "report mode" in note and "would deny" in note, note
    assert "[terraformApply]" in note, note
    log = (repo / ".crew" / "guard.log").read_text(encoding="utf-8")
    assert "\tterraformApply\tblock\treport:deny\t" in log


def test_report_mode_evaluates_to_no_decision(tmp_path):
    """In-process, because on stdout `allow` and "no decision" look the same
    (both print nothing) -- the invariant is that report mode never RESOLVES
    to allow, including for an unknown identity nobody is there to answer."""
    repo = _fixture(tmp_path, {"guards": {"cloudGuard": "report"},
                               "cloud": {"awsProfiles": ["dev"]}})
    for command in ("terraform destroy", "aws s3 ls", "terraform plan"):
        result = cloud_guard.evaluate(str(repo), "Bash", command,
                                      {"permission_mode": "dontAsk"},
                                      mode="report")
        assert result["decision"] is None, (command, result)


@pytest.mark.parametrize("driver", _DRIVERS)
@pytest.mark.parametrize("raw", [b"{not json", b"\xff\xfe", b"[1, 2]", b"",
                                 b'{"tool_name": "Bash", "tool_input": 7}',
                                 b'{"tool_name": "Bash", "tool_input": '
                                 b'{"command": ["terraform", "destroy"]}}'],
                         ids=["not-json", "not-utf8", "not-object", "empty",
                              "no-tool-input", "command-not-string"])
def test_malformed_input_is_refused_when_armed(tmp_path, driver, raw):
    _fixture(tmp_path, ARMED)
    decision, reason, code, err = run_hook(driver, tmp_path, _tool(driver), "",
                                           raw=raw)
    assert (decision, code) == ("deny", 0), (reason, err)
    assert "refusing" in reason


@pytest.mark.parametrize("driver", _DRIVERS_SAMPLE)
def test_malformed_input_is_not_judged_when_off(tmp_path, driver):
    _fixture(tmp_path, {"guards": {"cloudGuard": "off"}})
    assert run_hook(driver, tmp_path, _tool(driver), "", raw=b"{not json")[:3] == (
        "allow", "", 0)


@pytest.mark.parametrize("driver", _DRIVERS)
@pytest.mark.parametrize("cloud", [None, "dev", {"awsProfiles": "dev"},
                                   {"awsRegions": [7]}],
                         ids=["null", "string", "profiles-string",
                              "region-not-str"])
def test_a_malformed_cloud_block_fails_closed_when_armed(tmp_path, driver,
                                                         cloud):
    """`"cloud": null` is an invalid layer, not "nothing pinned": even REPORT
    mode escalates to block, and a read-only call's identity is unknown."""
    _fixture(tmp_path, {"guards": {"cloudGuard": "report"}, "cloud": cloud})
    decision, reason, _c, err = run_hook(driver, tmp_path, _tool(driver),
                                         "terraform destroy")
    assert decision == "deny", err
    assert "`cloud` block is malformed" in reason
    _fixture(tmp_path, {"guards": {"cloudGuard": "block"}, "cloud": cloud})
    decision, reason, _c, err = run_hook(driver, tmp_path, _tool(driver), "aws s3 ls",
                                         extra_env={"CI": "1"})
    assert decision == "deny", err
    assert "could not read the identity pins" in reason


@pytest.mark.parametrize("driver", _DRIVERS)
def test_a_malformed_cloud_block_leaves_an_unarmed_guard_off(tmp_path, driver):
    _fixture(tmp_path, {"guards": {"cloudGuard": "off"}, "cloud": None})
    assert run_hook(driver, tmp_path, _tool(driver), "terraform destroy")[0] == \
        "allow"


def test_layer_state_classifies_a_malformed_cloud_block(tmp_path):
    import crew_config  # pylint: disable=import-outside-toplevel
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"guards": {}, "cloud": None}),
                    encoding="utf-8")
    assert crew_config.layer_state(str(path), cloud=True) == "corrupt"
    # Without `cloud=True` the roleWrites read is untouched by it.
    assert crew_config.layer_state(str(path)) == "ok"
    path.write_text(json.dumps({"cloud": {"awsProfiles": ["dev"]}}),
                    encoding="utf-8")
    assert crew_config.layer_state(str(path), cloud=True) == "ok"


@pytest.mark.parametrize("driver", _DRIVERS_SAMPLE)
def test_unpinned_read_only_call_is_reported_once(tmp_path, driver):
    """The pass with nothing pinned is said -- once, as a visible note and a
    guard.log row -- and then not again."""
    repo = _fixture(tmp_path, ARMED)
    env = {"CI": "true"}
    decision, note, _c, err = run_hook(driver, tmp_path, _tool(driver), "aws s3 ls",
                                       extra_env=env)
    assert decision == "allow", err
    assert "nothing is pinned" in note, note
    log = (repo / ".crew" / "guard.log").read_text(encoding="utf-8")
    assert "\tcloudIdentity\tunpinned\tallow\taws s3 ls\t" in log
    assert run_hook(driver, tmp_path, _tool(driver), "aws s3 ls",
                    extra_env=env)[:2] == ("allow", "")
    assert (repo / ".crew" / "guard.log").read_text(encoding="utf-8") == log


@pytest.mark.parametrize("driver", _DRIVERS)
def test_unpinned_note_is_said_even_with_no_crew_dir(tmp_path, driver):
    """Armed from the machine-global layer in a repo with no `.crew/`: there
    is nowhere to record that the note was said, and the guard never creates
    `.crew/` -- so it is said every time rather than silently never."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _fixture_global = tmp_path / "home" / ".claude" / "crew"
    _fixture_global.mkdir(parents=True)
    (_fixture_global / "config.json").write_text(json.dumps(ARMED),
                                                 encoding="utf-8")
    env = {"CI": "true"}
    for _ in range(2):
        decision, note, _c, err = run_hook(driver, tmp_path, _tool(driver),
                                           "aws s3 ls", extra_env=env)
        assert decision == "allow", err
        assert "nothing is pinned" in note and "said every time" in note, \
            (note, err)
    assert not (repo / ".crew").exists()


@pytest.mark.parametrize("driver", _DRIVERS_SAMPLE)
def test_a_corrupt_config_fails_closed(tmp_path, driver):
    repo = _fixture(tmp_path)
    (repo / ".crew" / "config.json").write_text("{not json", encoding="utf-8")
    decision, _reason, _code, err = run_hook(driver, tmp_path, _tool(driver),
                                             "terraform destroy")
    assert decision == "deny", err


@pytest.mark.parametrize("driver", _DRIVERS_SAMPLE)
def test_ask_policy_prompts_when_attended(tmp_path, driver):
    _fixture(tmp_path, {"guards": {"cloudGuard": "block",
                                   "terraformApply": "ask"}},
             {"guards": {"terraformApply": "ask"}})
    decision, reason, _code, err = run_hook(driver, tmp_path, _tool(driver),
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
    payload = {"tool_name": _tool(driver),
               "tool_input": {"command": "terraform apply"},
               "cwd": str(tmp_path / "repo")}
    if isinstance(how, str):
        payload["permission_mode"] = how
    decision, reason, _code, err = run_hook(driver, tmp_path, _tool(driver), "",
                                            extra_env=env, payload=payload)
    assert decision == "deny", err
    assert ".approved-guard-terraformApply-" in reason


@pytest.mark.parametrize("driver", _DRIVERS)
def test_a_live_approval_marker_lets_one_command_through(tmp_path, driver):
    repo = _fixture(tmp_path, {"guards": {"cloudGuard": "block",
                                          "terraformApply": "ask"}},
                    {"guards": {"terraformApply": "ask"}})
    env = {"CREW_UNATTENDED": "1"}
    decision, reason, _c, _e = run_hook(driver, tmp_path, _tool(driver),
                                        "terraform apply", extra_env=env)
    assert decision == "deny"
    marker = re.search(r"(\S*\.approved-guard-terraformApply-[0-9a-f]+)",
                       reason).group(1)
    assert os.path.dirname(marker) == str(repo / ".crew")
    with open(marker, "w", encoding="utf-8"):
        pass
    assert run_hook(driver, tmp_path, _tool(driver), "terraform apply",
                    extra_env=env)[0] == "allow"
    # The approval names ONE command: a different one still refuses.
    assert run_hook(driver, tmp_path, _tool(driver), "terraform destroy",
                    extra_env=env)[0] == "deny"
    # And it expires.
    old = time.time() - 3600
    os.utime(marker, (old, old))
    assert run_hook(driver, tmp_path, _tool(driver), "terraform apply",
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
    assert run_hook(driver, tmp_path, _tool(driver), "az group delete -n rg",
                    extra_env={"CREW_UNATTENDED": "1"})[0] == "allow"
    profile["subscriptions"][0]["isDefault"] = True
    profile["subscriptions"][1]["isDefault"] = False
    (azure / "azureProfile.json").write_text(json.dumps(profile),
                                             encoding="utf-8-sig")
    assert run_hook(driver, tmp_path, _tool(driver), "az group delete -n rg",
                    extra_env={"CREW_UNATTENDED": "1"})[0] == "deny"


@pytest.mark.parametrize("driver", _DRIVERS)
def test_malformed_pins_make_every_cloud_identity_unknown(tmp_path, driver):
    """`"awsProfiles": "dev"` -- a string where a list belongs -- is not
    "nothing pinned". Read as nothing pinned, `aws s3 ls` would run
    unchecked in the one repo whose owner tried to pin it."""
    cfg = {"guards": PINNED["guards"], "cloud": {"awsProfiles": "dev"}}
    _fixture(tmp_path, cfg, PERMISSIVE_GLOBAL)
    decision, reason, _c, err = run_hook(
        driver, tmp_path, _tool(driver), "aws s3 ls --profile dev",
        extra_env={"CREW_UNATTENDED": "1"})
    assert decision == "deny", err
    assert "could not read the identity pins" in reason


@pytest.mark.parametrize("driver", _DRIVERS)
def test_production_database_patterns_are_wired(tmp_path, driver):
    _fixture(tmp_path, {"guards": {"cloudGuard": "block"},
                        "production": {"databases": ["prod-db-*"]}})
    decision, reason, _c, err = run_hook(
        driver, tmp_path, _tool(driver),
        "psql -h prod-db-1 -c 'SELECT 1'")
    assert decision == "deny", err
    assert "[prodDatabase]" in reason
    assert run_hook(driver, tmp_path, _tool(driver),
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
        capture_output=True, env=_clean_env(tmp_path, _NO_PYTHON, "pwsh"),
        timeout=120, check=False)
    assert proc.returncode == (2 if armed else 0), proc.stderr


@needs_pwsh
@pytest.mark.parametrize("tool,want", [("Bash", "stood-down"),
                                       ("PowerShell", "deny")])
def test_pwsh_wrapper_judges_by_tool(tmp_path, tool, want):
    """On Windows the .ps1 judges PowerShell calls and stands down for Bash
    ones -- cloud-guard.sh judges every Bash call, so nothing is lost and
    nothing is judged twice."""
    _fixture(tmp_path, ARMED)
    proc = subprocess.run(
        _argv("pwsh"),
        input=json.dumps({"tool_name": tool, "tool_input": {
            "command": "terraform destroy"}}).encode("utf-8"),
        capture_output=True, env=_clean_env(tmp_path, None, "pwsh"),
        timeout=120, check=False)
    assert proc.returncode == 0, proc.stderr
    got = "deny" if b'"permissionDecision": "deny"' in proc.stdout else (
        "stood-down" if not proc.stdout.strip() else proc.stdout)
    assert got == want, proc.stderr


@needs_pwsh
def test_pwsh_wrapper_stands_down_off_windows(tmp_path):
    _fixture(tmp_path, ARMED)
    env = _clean_env(tmp_path)
    env.pop("OS", None)
    proc = subprocess.run(
        _argv("pwsh"), input=b'{"tool_name":"Bash","tool_input":'
                             b'{"command":"terraform destroy"}}',
        capture_output=True, env=env, timeout=120, check=False)
    assert (proc.returncode, proc.stdout) == (0, b"")


def _bin_farm(tmp_path, with_powershell):
    """A PATH holding only what cloud-guard.sh runs -- plus, when asked, a
    `powershell.exe` that exits 99 if anything ever runs it. It is there to
    prove a same-named executable on PATH changes nothing: the old wrapper
    stood down for EVERY call when `command -v` found one."""
    import shutil  # pylint: disable=import-outside-toplevel
    farm = tmp_path / ("bin-ps" if with_powershell else "bin")
    farm.mkdir()
    for tool in ("cat", "dirname", "grep", "head", "sed", "tr"):
        found = shutil.which(tool)
        if found:
            os.symlink(found, farm / tool)
    os.symlink(sys.executable, farm / "python3")
    if with_powershell:
        fake = farm / "powershell.exe"
        fake.write_text("#!/bin/sh\nexit 99\n", encoding="utf-8")
        fake.chmod(0o755)
    return str(farm)


@needs_bash
@pytest.mark.skipif(os.name == "nt", reason="symlinks a POSIX bin farm")
@pytest.mark.parametrize("os_value,tool,with_ps,want", [
    ("Windows_NT", "Bash", True, "deny"),
    ("Windows_NT", "Bash", False, "deny"),
    ("Windows_NT", "PowerShell", True, "allow"),
    ("Windows_NT", "PowerShell", False, "allow"),
    (None, "PowerShell", True, "deny"),
    (None, "Bash", True, "deny"),
], ids=["windows-bash-with-powershell", "windows-bash",
        "windows-powershell-with-powershell", "windows-powershell",
        "not-windows-powershell", "not-windows-bash"])
def test_bash_wrapper_flavour_guard(tmp_path, os_value, tool, with_ps, want):
    """By the TOOL, not the OS (review round 2): bash judges every Bash call
    whatever `OS` says and whatever is on PATH -- the old wrapper stood down
    for all of them on `OS=Windows_NT` plus any `powershell.exe`, so both
    Windows flavours could be made no-ops. It stands down for a PowerShell
    call only where the .ps1 judges it (`OS=Windows_NT`), and judges
    PowerShell calls everywhere else, where the .ps1 exits at its first
    line."""
    _fixture(tmp_path, ARMED)
    env = _clean_env(tmp_path, {"PATH": _bin_farm(tmp_path, with_ps)})
    if os_value:
        env["OS"] = os_value
    proc = subprocess.run(
        [_BASH, _SH],
        input=json.dumps({"tool_name": tool, "tool_input": {
            "command": "terraform destroy"}}).encode("utf-8"),
        capture_output=True, env=env, timeout=60, check=False)
    assert proc.returncode == 0, proc.stderr
    got = "deny" if b'"permissionDecision": "deny"' in proc.stdout else (
        "allow" if not proc.stdout.strip() else proc.stdout)
    assert got == want, proc.stderr


@needs_bash
def test_bash_wrapper_ignores_an_inherited_flavour(tmp_path):
    """The wrapper names its OWN flavour: an inherited
    `CREW_CLOUD_GUARD_FLAVOUR=powershell` must not stand it down for Bash."""
    _fixture(tmp_path, ARMED)
    env = _clean_env(tmp_path, {cloud_guard.FLAVOUR_VAR: "powershell",
                                "OS": "Windows_NT"})
    proc = subprocess.run(
        [_BASH, _SH], input=b'{"tool_name":"Bash","tool_input":'
                            b'{"command":"terraform destroy"}}',
        capture_output=True, env=env, timeout=60, check=False)
    assert b'"permissionDecision": "deny"' in proc.stdout, proc.stderr


@pytest.mark.parametrize("flavour,tool,os_value,want", [
    ("bash", "Bash", "Windows_NT", False),
    ("bash", "PowerShell", "Windows_NT", True),
    ("bash", "PowerShell", None, False),
    ("powershell", "Bash", "Windows_NT", True),
    ("powershell", "PowerShell", "Windows_NT", False),
    (None, "Bash", "Windows_NT", False),
    (None, "PowerShell", "Windows_NT", False),
])
def test_stands_down_is_decided_by_the_tool(flavour, tool, os_value, want):
    environ = {}
    if flavour:
        environ[cloud_guard.FLAVOUR_VAR] = flavour
    if os_value:
        environ["OS"] = os_value
    assert cloud_guard.stands_down(tool, environ) is want


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


@pytest.mark.parametrize("sql,dialect,want", [
    # PostgreSQL: a backslash is an ordinary character in '...'...
    ("SELECT 'C:\\' AS p, 'DROP' AS s", "postgres", False),
    # ...and an escape inside E'...', where it can hide a statement.
    ("SELECT E'\\'' ; DROP TABLE t; --'", "postgres", True),
    ("SELECT 1 -- DROP TABLE t", "postgres", False),
    ("SELECT 1 /* DROP TABLE t */", "postgres", False),
    ("SELECT 1--1; DROP TABLE t", "postgres", False),
    # MySQL: `\'` escapes, `#` comments, `--` needs a space, `/*!` runs.
    ("SELECT 'it\\'s', 'DROP' AS s", "mysql", False),
    ("SELECT 1 # DROP TABLE t", "mysql", False),
    ("SELECT 1--1; DROP TABLE t", "mysql", True),
    ("SELECT 1 /*!50000 DROP TABLE t */", "mysql", True),
    # T-SQL: standard strings and both comment forms.
    ("SELECT 'C:\\' AS p, 'DROP' AS s", "tsql", False),
    ("SELECT 1 -- DROP TABLE t", "tsql", False),
    ("SELECT 1 /* TRUNCATE t */", "tsql", False),
    ("DROP TABLE t", "tsql", True),
    # Review round 2: the server MODES. MySQL under NO_BACKSLASH_ESCAPES and
    # PostgreSQL with standard_conforming_strings off read `\\'` the other
    # way from their defaults, and each can hide a DROP the other shows.
    ("SELECT 'a\\' ; DROP TABLE t; -- '", "mysql", False),
    ("SELECT 'a\\' ; DROP TABLE t; -- '", "mysql-no-escapes", True),
    ("SELECT 1 # DROP TABLE t", "mysql-no-escapes", False),
    ("SELECT 1 /*M!100000 DROP TABLE t */", "mysql", True),
    ("SELECT 'a\\', ' ; DROP TABLE t; -- '", "postgres", False),
    ("SELECT 'a\\', ' ; DROP TABLE t; -- '", "postgres-escapes", True),
    ("SELECT 1 -- DROP TABLE t", "postgres-escapes", False),
])
def test_sql_dialect_follows_the_client(sql, dialect, want):
    assert cloud_guard.sql_is_destructive(sql, dialect) is want


@pytest.mark.parametrize("client,sql,want", [
    ("mysql", "SELECT 'a\\' ; DROP TABLE t; -- '", True),
    ("mariadb", "SELECT 'a\\' ; DROP TABLE t; -- '", True),
    ("psql", "SELECT 'a\\', ' ; DROP TABLE t; -- '", True),
    # A comment every reading of the client agrees on is not flagged.
    ("mysql", "SELECT 1 -- DROP TABLE t", False),
    ("psql", "SELECT 1 --DROP TABLE t", False),
    # T-SQL and SQLite have no backslash-escape mode to read.
    ("sqlcmd", "SELECT 'C:\\' AS p, 'DROP' AS s", False),
    ("sqlite3", "SELECT 'C:\\' AS p, 'DROP' AS s", False),
])
def test_sql_client_is_read_under_every_mode(client, sql, want):
    """A DROP ANY of the client's readings sees counts: which mode the server
    runs in is not on the command line."""
    readings = cloud_guard._SQL_DIALECT[client]  # pylint: disable=protected-access
    assert cloud_guard.sql_is_destructive(sql, readings) is want


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

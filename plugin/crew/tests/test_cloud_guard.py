"""The cloud/destructive guard: must-block and must-allow, in every driver.

CLAUDE.md requires a hook that can block to carry a committed regression suite
with must-block and must-allow cases, sabotage-tested. This is that suite for
`hooks/scripts/cloud_guard.py` and its wrapper.

Every decision case runs two ways, each as its own test function so the
sabotage harness can aim at the fast one:

    python   `python3 cloud_guard.py`, the module the wrapper delegates to
    bash     `bash cloud-guard.sh`

The python driver runs every case by default. The bash driver runs a parity
sample by default (`_B_SHELL`, `_A_SHELL`, `_I_SHELL`, `_DRIVERS_SAMPLE`, and
the wrapper tests at the end) and the rest of the matrix as `slow` --
`pytest -m slow` or `--run-slow` (see conftest.py).

Each case names the TOOL whose command it is (`Bash` or `PowerShell`), and the
same case runs through both drivers: the tool decides the parser, never the
wrapper that happened to run. cloud-guard.sh judges a PowerShell-tool call
too, so the PowerShell cases run through it unchanged.

Isolation: every subprocess gets its own HOME/USERPROFILE (so the machine-
global crew config and `~/.azure` are fixtures), its own CLAUDE_PROJECT_DIR,
and an environment with every AWS_*/AZURE_*/CI/CREW_UNATTENDED variable
removed. Nothing here runs terraform, aws, az, git push or any SQL client --
the guard only reads the command text.
"""
import json
import os
import pathlib
import re
import subprocess
import sys
import time

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import crew_fixtures

import cloud_guard  # noqa: E402  pylint: disable=wrong-import-position
import crew_guards  # noqa: E402  pylint: disable=wrong-import-position
import verify_record  # noqa: E402  pylint: disable=wrong-import-position

_ROOT = context._ROOT  # pylint: disable=protected-access
_SCRIPTS = os.path.join(_ROOT, "hooks", "scripts")
_PY = os.path.join(_SCRIPTS, "cloud_guard.py")
_SH = os.path.join(_SCRIPTS, "cloud-guard.sh")

_BASH = crew_fixtures.resolve_bash()
needs_bash = pytest.mark.skipif(_BASH is None, reason="no MSYS/POSIX bash")

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
    """The subprocess environment: no cloud identity, no CI marker, and its
    own HOME and project directory."""
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(("AWS_", "AZURE_", "ARM_"))
           and k not in ("CI", "CREW_UNATTENDED", "CLAUDE_PROJECT_DIR", "OS",
                         cloud_guard.FLAVOUR_VAR)}
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    env.update({"HOME": str(home), "USERPROFILE": str(home),
                "CLAUDE_PROJECT_DIR": str(tmp_path / "repo"),
                "PYTHONDONTWRITEBYTECODE": "1"})
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
    raise AssertionError(driver)


KILLED_UNJUDGED = "could not tell"


def killed_by(code, driver, platform=sys.platform):
    """The signal that ended the hook process, or None when it exited.

    POSIX python reports a signal death as `-N`. A native Windows parent sees
    an MSYS bash.exe ended by signal N as `N << 8`: msys2-runtime's
    `pinfo::exit` byte-swaps the wait status of a process no Cygwin parent
    started, so SIGKILL reads 2304 (L-1512; measured in CI job 111538994343).
    A bash `exit` is 0..255, so a low byte of 0 with a signal number above
    it is a signal there and nothing else. 137 is an exit status -- bash
    reporting a child it saw killed -- and stays one."""
    if code < 0:
        return -code
    if (driver == "bash" and platform.startswith("win") and code & 0xFF == 0
            and 0 < code >> 8 < 65):
        return code >> 8
    return None


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
        capture_output=True, env=_clean_env(tmp_path, extra_env),
        cwd=str(tmp_path), timeout=120, check=False)
    out = proc.stdout.decode("utf-8", "replace").strip()
    err = proc.stderr.decode("utf-8", "replace")
    signal_no = killed_by(proc.returncode, driver)
    if signal_no is not None:
        # Silence from a hook that never finished is not its allow. PreToolUse
        # reads any status but 0 and 2 as non-blocking, so the agent would
        # have run the command unjudged: this run could not tell.
        return (KILLED_UNJUDGED, "", proc.returncode,
                f"{err}[harness] the {driver} hook was killed by signal "
                f"{signal_no} (exit {proc.returncode}) before it judged -- "
                "could not tell, which is not an allow")
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
    # T-0005 review round 2. An unquoted heredoc body is expanded by the
    # shell that reads it, so a substitution in it runs whatever the heredoc
    # is fed to -- `cat` included.
    ("heredoc-subst-destroy", "Bash",
     "cat <<EOF\n$(terraform destroy -auto-approve)\nEOF", "terraformApply"),
    ("heredoc-subst-ws-delete", "Bash",
     "cat <<EOF\n$(terraform workspace delete production)\nEOF",
     "terraformApply"),
    ("heredoc-backtick-destroy", "Bash",
     "cat <<EOF\n`terraform destroy -auto-approve`\nEOF", "terraformApply"),
    ("heredoc-param-default-destroy", "Bash",
     "cat <<EOF\n${x:=$(terraform destroy -auto-approve)}\nEOF",
     "terraformApply"),
    ("heredoc-arith-destroy", "Bash",
     "cat <<EOF\n$(( $(terraform destroy -auto-approve) ))\nEOF",
     "terraformApply"),
    # Bash joins a backslash-newline before it looks for the delimiter of an
    # unquoted heredoc, so `E\<newline>OF` ends it and the next line runs.
    ("heredoc-continued-delimiter", "Bash",
     "cat <<EOF\nE\\\nOF\nterraform destroy -auto-approve\nEOF\n",
     "terraformApply"),
    # `EOF\r` ends a heredoc only where bash ignores CR, so both readings
    # are judged: here the one that does not end it runs the destroy.
    ("heredoc-cr-delimiter", "Bash",
     "cat <<EOF\nEOF\r\n'\nEOF\nterraform destroy -auto-approve\n'\n",
     "terraformApply"),
    ("param-default-destroy", "Bash",
     "echo ${x:=$(terraform destroy -auto-approve)}", "terraformApply"),
    ("arith-nested-destroy", "Bash",
     "echo $(( $(terraform destroy -auto-approve) ))", "terraformApply"),
    ("comsub-of-subshell-destroy", "Bash",
     "echo $((terraform destroy -auto-approve) )", "terraformApply"),
    ("procsub-of-subshell-destroy", "Bash",
     "cat <((terraform destroy -auto-approve))", "terraformApply"),
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
     'git commit -m "aws ec2 terminate-instances, DROP TABLE, git push -f"'),
    ("echo-words", "Bash", "echo aws ec2 terminate-instances"),
    ("grep-words", "Bash", "grep -rn 'aws s3 rb' docs/"),
    # A `;` inside a comment would split off a command if the comment were
    # not read as one -- which is what makes these two cases load-bearing.
    ("bash-comment", "Bash", "ls  # then; aws s3 rb s3://bucket"),
    ("gh-merge", "Bash", "gh pr merge 12 --squash"),
    ("ps-tf-plan", "PowerShell", "Get-ChildItem; terraform plan"),
    ("ps-comment", "PowerShell",
     'Write-Output "git push --force" # then; git push --force'),
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
    ("bash-c-dashdash-plan-plain", "Bash", "bash -c -- terraform plan"),
    ("az-option-before-read-verb", "Bash",
     "az group --subscription dev show -n rg"),
    ("xargs-git-add", "Bash", "git ls-files -m | xargs git add"),
    ("xargs-rm", "Bash", "find . -name '*.tmp' | xargs rm"),
    ("xargs-terraform-fmt", "Bash", "ls *.tf | xargs terraform fmt"),
    ("xargs-terraform-fmt-plain", "Bash", "ls main.tf | xargs terraform fmt"),
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
    # A quoted heredoc delimiter -- any part of it -- keeps the body literal.
    ("heredoc-quoted-subst", "Bash",
     "cat <<'EOF'\n$(aws s3 rb s3://bucket)\nEOF"),
    ("heredoc-partly-quoted-subst", "Bash",
     'cat <<E"O"F\n$(aws s3 rb s3://bucket)\nEOF'),
    ("heredoc-escaped-subst", "Bash",
     "cat <<EOF\n\\$(aws s3 rb s3://bucket)\nEOF"),
    ("arith-plain", "Bash", "echo $(( (1 + 2) * 3 ))"),
]

# Step 8 (T-0005): these were in MUST_ALLOW until crew read terraform lines
# through the literal-word allowlist. Each names terraform on a line that
# carries a quote, a comment, a glob or a heredoc, so crew could not tell
# what it runs: refused under the default `block`, asked about under `ask`.
# MUST_ALLOW above keeps each shape with the terraform words swapped for
# another rule's, so the lexer behaviour it pinned is still pinned. Review
# round 5 moved `bash-c-dashdash-plan` and `xargs-terraform-fmt` back to
# MUST_ALLOW as they were: `plan` and `fmt` change nothing, so their quoting
# is not gated.
COULD_NOT_TELL = [
    # The same two shapes with a subcommand that is not read-only.
    ("was-bash-c-dashdash-taint", "Bash",
     "bash -c -- 'terraform taint aws_instance.a'"),
    ("was-xargs-terraform-taint", "Bash", "ls *.tf | xargs terraform taint"),
]

# Step 9 (T-0005): Step 8 refused these too, because a word on each dequoted
# to terraform. None RUNS terraform -- a message, a search, a comment, a
# heredoc body that stays literal -- so the gate, which now reads the command
# word, hands them back to the lexer, and the lexer allows them. Step 10 gave
# PowerShell the same command-word rule, so its comment case moved here.
NO_LONGER_GATED = [
    ("was-ps-comment", "PowerShell",
     'Write-Output "terraform destroy" # then; terraform destroy'),
    ("was-commit-message", "Bash",
     'git commit -m "terraform destroy, DROP TABLE, git push --force"'),
    ("was-grep-words", "Bash", "grep -rn 'terraform apply' docs/"),
    ("was-bash-comment", "Bash", "ls  # then; terraform destroy"),
    ("was-heredoc-quoted-subst", "Bash",
     "cat <<'EOF'\n$(terraform destroy -auto-approve)\nEOF"),
    ("was-heredoc-partly-quoted-subst", "Bash",
     'cat <<E"O"F\n$(terraform destroy -auto-approve)\nEOF'),
    ("was-heredoc-escaped-subst", "Bash",
     "cat <<EOF\n\\$(terraform destroy -auto-approve)\nEOF"),
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

# The bash driver runs a parity sample by default -- one Bash and one
# PowerShell case each -- and the rest of each table as `slow`. The python driver
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


@pytest.mark.parametrize("case", MUST_ALLOW, ids=_A_IDS)
def test_must_allow_python(tmp_path, case):
    _allow("python", tmp_path, case)


@needs_bash
@pytest.mark.parametrize("case", _A_SHELL)
def test_must_allow_bash(tmp_path, case):
    _allow("bash", tmp_path, case)


@pytest.mark.parametrize("case", MUST_BLOCK, ids=_B_IDS)
def test_the_lexer_still_judges_every_must_block_case(case):
    """Step 8's allowlist denies most unusual terraform lines before the
    lexer's answer matters, which would let a lexer regression hide behind
    it. So each must-block case is also judged by the lexer alone: the
    findings `scan` returns, the allowlist's own set aside."""
    _id, tool, command, rule = case
    shell = "powershell" if tool == "PowerShell" else "bash"
    ctx = {"cd": False, "switch": False, "engaged": False}
    rules = {f.rule for f in cloud_guard.scan(shell, command, ctx=ctx)
             if (f.scope or {}).get("op") != cloud_guard.OP_UNREADABLE_LINE}
    assert rule in rules, (command, rules)


@pytest.mark.parametrize("case", COULD_NOT_TELL,
                         ids=[c[0] for c in COULD_NOT_TELL])
def test_could_not_tell_is_refused_under_block(tmp_path, case):
    _block("python", tmp_path, case + ("terraformApply",))


@pytest.mark.parametrize("case", COULD_NOT_TELL,
                         ids=[c[0] for c in COULD_NOT_TELL])
def test_could_not_tell_is_asked_under_ask(tmp_path, case):
    _id, tool, command = case
    _fixture(tmp_path, {"guards": {"cloudGuard": "block",
                                   "terraformApply": "ask"}},
             {"guards": {"terraformApply": "ask"}})
    decision, reason, code, err = run_hook("python", tmp_path, tool, command)
    assert (decision, code) == ("ask", 0), (reason, err)
    assert "plain literal" in reason, reason


@pytest.mark.parametrize("case", NO_LONGER_GATED,
                         ids=[c[0] for c in NO_LONGER_GATED])
def test_a_line_that_runs_no_terraform_is_not_gated(tmp_path, case):
    _allow("python", tmp_path, case)


@pytest.mark.parametrize("case", IDENTITY, ids=_I_IDS)
def test_identity_python(tmp_path, case):
    _identity("python", tmp_path, case)


@needs_bash
@pytest.mark.parametrize("case", _I_SHELL)
def test_identity_bash(tmp_path, case):
    _identity("bash", tmp_path, case)


# --- the switch, and what it does when on -----------------------------------

_DRIVERS = [
    pytest.param("python", id="python"),
    pytest.param("bash", id="bash", marks=(needs_bash, crew_fixtures.SLOW)),
]
# The same drivers with the shells in the default run, for the switch tests
# that form the per-shell parity sample: off, malformed input, ask, and a
# systemMessage passed through on stdout.
_DRIVERS_SAMPLE = [
    pytest.param("python", id="python"),
    pytest.param("bash", id="bash", marks=needs_bash),
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
    """Report mode prints NO decision -- never `allow`, which would skip the
    user's own prompt -- and a visible note of what `block` would do."""
    repo = _fixture(tmp_path, {"guards": {"cloudGuard": "report"}})
    decision, note, code, err = run_hook(driver, tmp_path, "Bash",
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
    decision, reason, code, err = run_hook(driver, tmp_path, "Bash", "",
                                           raw=raw)
    assert (decision, code) == ("deny", 0), (reason, err)
    assert "refusing" in reason


@pytest.mark.parametrize("driver", _DRIVERS_SAMPLE)
def test_malformed_input_is_not_judged_when_off(tmp_path, driver):
    _fixture(tmp_path, {"guards": {"cloudGuard": "off"}})
    assert run_hook(driver, tmp_path, "Bash", "", raw=b"{not json")[:3] == (
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
    decision, reason, _c, err = run_hook(driver, tmp_path, "Bash",
                                         "terraform destroy")
    assert decision == "deny", err
    assert "`cloud` block is malformed" in reason
    _fixture(tmp_path, {"guards": {"cloudGuard": "block"}, "cloud": cloud})
    decision, reason, _c, err = run_hook(driver, tmp_path, "Bash", "aws s3 ls",
                                         extra_env={"CI": "1"})
    assert decision == "deny", err
    assert "could not read the identity pins" in reason


@pytest.mark.parametrize("driver", _DRIVERS)
def test_a_malformed_cloud_block_leaves_an_unarmed_guard_off(tmp_path, driver):
    _fixture(tmp_path, {"guards": {"cloudGuard": "off"}, "cloud": None})
    assert run_hook(driver, tmp_path, "Bash", "terraform destroy")[0] == \
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
    decision, note, _c, err = run_hook(driver, tmp_path, "Bash", "aws s3 ls",
                                       extra_env=env)
    assert decision == "allow", err
    assert "nothing is pinned" in note, note
    log = (repo / ".crew" / "guard.log").read_text(encoding="utf-8")
    assert "\tcloudIdentity\tunpinned\tallow\taws s3 ls\t" in log
    assert run_hook(driver, tmp_path, "Bash", "aws s3 ls",
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
        decision, note, _c, err = run_hook(driver, tmp_path, "Bash",
                                           "aws s3 ls", extra_env=env)
        assert decision == "allow", err
        assert "nothing is pinned" in note and "said every time" in note, \
            (note, err)
    assert not (repo / ".crew").exists()


@pytest.mark.parametrize("driver", _DRIVERS_SAMPLE)
def test_a_corrupt_config_fails_closed(tmp_path, driver):
    repo = _fixture(tmp_path)
    (repo / ".crew" / "config.json").write_text("{not json", encoding="utf-8")
    decision, _reason, _code, err = run_hook(driver, tmp_path, "Bash",
                                             "terraform destroy")
    assert decision == "deny", err


@pytest.mark.parametrize("driver", _DRIVERS_SAMPLE)
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
        driver, tmp_path, "Bash",
        "psql -h prod-db-1 -c 'SELECT 1'")
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


@pytest.mark.parametrize("tool,want", [("Bash", True), ("PowerShell", False)],
                         ids=["bash-call", "powershell-call"])
def test_pwsh_wrapper_judges_by_tool(tool, want):
    """A `powershell`-flavoured caller stands down for Bash calls (bash
    judges every one of those) and judges PowerShell calls itself."""
    environ = {cloud_guard.FLAVOUR_VAR: "powershell", "OS": "Windows_NT"}
    assert cloud_guard.stands_down(tool, environ) is want


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


def _hooks_farm(tmp_path, with_twin):
    """A directory of symlinks to every file beside cloud-guard.sh, plus,
    when asked, an empty `cloud-guard.ps1` beside them. cloud_guard.py reads
    where it lives from the path it was started by, so the farm is where it
    looks for a twin; the real directory holds none."""
    farm = tmp_path / ("hooks-twin" if with_twin else "hooks")
    farm.mkdir()
    for entry in os.listdir(_SCRIPTS):
        os.symlink(os.path.join(_SCRIPTS, entry), farm / entry)
    if with_twin:
        (farm / "cloud-guard.ps1").write_text("", encoding="utf-8")
    return str(farm / "cloud-guard.sh")


@needs_bash
@pytest.mark.skipif(os.name == "nt", reason="symlinks a POSIX bin farm")
@pytest.mark.parametrize("os_value,tool,with_ps,with_twin,want", [
    ("Windows_NT", "Bash", True, True, "deny"),
    ("Windows_NT", "Bash", False, True, "deny"),
    ("Windows_NT", "PowerShell", True, True, "allow"),
    ("Windows_NT", "PowerShell", False, True, "allow"),
    (None, "PowerShell", True, True, "deny"),
    (None, "Bash", True, True, "deny"),
    ("Windows_NT", "PowerShell", True, False, "deny"),
    ("Windows_NT", "PowerShell", False, False, "deny"),
], ids=["windows-bash-with-powershell", "windows-bash",
        "windows-powershell-with-powershell", "windows-powershell",
        "not-windows-powershell", "not-windows-bash",
        "windows-powershell-no-twin-with-powershell",
        "windows-powershell-no-twin"])
def test_bash_wrapper_flavour_guard(tmp_path, os_value, tool, with_ps,
                                    with_twin, want):
    """By the TOOL, not the OS (review round 2): bash judges every Bash call
    whatever `OS` says and whatever is on PATH -- the old wrapper stood down
    for all of them on `OS=Windows_NT` plus any `powershell.exe`, so both
    Windows flavours could be made no-ops. It stands down for a PowerShell
    call only when a `.ps1` twin sits beside it and `OS=Windows_NT`; with no
    twin on disk, which is how the plugin ships, it judges PowerShell calls
    itself."""
    _fixture(tmp_path, ARMED)
    env = _clean_env(tmp_path, {"PATH": _bin_farm(tmp_path, with_ps)})
    if os_value:
        env["OS"] = os_value
    proc = subprocess.run(
        [_BASH, _hooks_farm(tmp_path, with_twin)],
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


@pytest.mark.parametrize("flavour,tool,os_value,twin,want", [
    ("bash", "Bash", "Windows_NT", True, False),
    ("bash", "PowerShell", "Windows_NT", True, True),
    ("bash", "PowerShell", "Windows_NT", False, False),
    ("bash", "PowerShell", None, True, False),
    ("powershell", "Bash", "Windows_NT", False, True),
    ("powershell", "PowerShell", "Windows_NT", False, False),
    (None, "Bash", "Windows_NT", True, False),
    (None, "PowerShell", "Windows_NT", True, False),
])
def test_stands_down_is_decided_by_the_tool(tmp_path, monkeypatch, flavour,
                                            tool, os_value, twin, want):
    twin_path = tmp_path / "cloud-guard.ps1"
    if twin:
        twin_path.write_text("", encoding="utf-8")
    monkeypatch.setattr(cloud_guard, "_PS1_TWIN", str(twin_path))
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
    anywhere. Nothing an argument SAYS is a finding of the rule it names.
    Since T-0005 Step 8 a quoted terraform word does make the LINE one crew
    could not tell (`test_could_not_tell_is_refused_under_block`); that
    finding says the words were unreadable, never that a destroy was seen,
    so it is set aside here."""
    for command in ('git commit -m "terraform destroy"',
                    "echo DROP TABLE users | tee notes.txt",
                    "gh pr comment 3 --body 'az group delete ran'"):
        rules = {f.rule for f in cloud_guard.scan("bash", command)
                 if (f.scope or {}).get("op")
                 != cloud_guard.OP_UNREADABLE_LINE}
        assert not rules & {"terraformApply", "cloudDestructive",
                            "sqlDestructive", "forcePush"}, command


# --- L-1512: a hook killed by a signal is "could not tell", never an allow ---

@pytest.mark.parametrize("code,driver,platform,want", [
    (-9, "bash", "linux", 9),
    (2304, "bash", "win32", 9),
    (3840, "bash", "win32", 15),
    (2304, "bash", "linux", None),
    (2304, "python", "win32", None),
    (137, "bash", "win32", None),
    (2, "bash", "win32", None),
    (0, "bash", "linux", None),
])
def test_killed_by_reads_the_signal_from_each_platforms_status(code, driver, platform, want):
    assert killed_by(code, driver, platform) == want


def _bash_env(tmp_path, text):
    """A BASH_ENV file: non-interactive bash sources it before cloud-guard.sh."""
    path = tmp_path / "bash-env.sh"
    path.write_text(text, encoding="utf-8", newline="\n")
    return {"BASH_ENV": path.as_posix()}


@needs_bash
def test_a_hook_killed_by_sigkill_reads_as_could_not_tell_not_allow(tmp_path):
    """The flake's own shape, made deterministic: the hook's bash.exe dies of
    SIGKILL before printing a word (2304 on Windows, -9 here). Its empty
    stdout must not read as the guard's allow -- the harness used to return
    `allow` for it, and a case asserting only the decision would have passed
    on a hook that never ran."""
    _fixture(tmp_path, ARMED)
    decision, _reason, code, err = run_hook(
        "bash", tmp_path, "Bash", "echo hello",
        extra_env=_bash_env(tmp_path, "kill -9 $$\n"))
    assert decision == KILLED_UNJUDGED == "could not tell", (decision, code, err)
    assert "killed by signal 9" in err, err
    assert code != 0


@needs_bash
def test_a_sigkill_aimed_at_anything_live_during_the_probe_cannot_end_the_hook(tmp_path):
    """L-1512's model of the Windows failure, run on any host: every `kill`
    the hook sends to a target still alive is delivered to the hook's own
    bash instead (`$$`), as Cygwin's signal delivery did to the bash.exe in
    job 111538994343. The python probe used to SIGKILL its still-running
    watchdog on every call, so this ended the hook with no output; it now
    signals nothing live unless a candidate hangs, and the guard judges."""
    _fixture(tmp_path, ARMED)
    spy = (
        "kill() {\n"
        "  local a first=1\n"
        '  for a in "$@"; do\n'
        '    if [ "$first" = 1 ]; then first=0; continue; fi\n'
        '    [ "$a" = "--" ] && continue\n'
        '    builtin kill -0 -- "$a" 2>/dev/null && builtin kill -9 $$\n'
        "  done\n"
        '  builtin kill "$@"\n'
        "}\n")
    decision, reason, code, err = run_hook(
        "bash", tmp_path, "Bash", "aws s3 rm s3://bucket/ --recursive",
        extra_env=_bash_env(tmp_path, spy))
    assert code == 0, err
    assert decision == "deny", (decision, err)
    assert "[cloudDestructive]" in reason, reason


@needs_bash
@pytest.mark.skipif(os.name == "nt", reason=(
    "the stub answers with this python's POSIX path; Windows paths through "
    "the probe's cygpath fallback are covered by the resolver suite"))
@pytest.mark.wallclock
def test_the_guard_still_decides_inside_its_hook_timeout_with_a_lingering_python(tmp_path):
    """Must-block, review round 2: a `python3` that answers with the real
    interpreter and exits, but leaves a child holding its stdout for 30s, held
    the strict probe -- and so the hook -- past hooks.json's 15s cloud-guard
    timeout, which PreToolUse treats as non-blocking. The guard must still
    deny inside that bound."""
    _fixture(tmp_path, ARMED)
    bindir = tmp_path / "bin"
    bindir.mkdir()
    pidfile = bindir / "child.pid"
    stub = bindir / "python3"
    stub.write_text(
        "#!/bin/sh\n"
        "( sleep 30 ) &\n"
        f"echo $! > '{pidfile.as_posix()}'\n"
        f"echo '{sys.executable}'\nexit 0\n",
        encoding="ascii", newline="\n")
    os.chmod(stub, 0o755)
    env = _clean_env(tmp_path, {"PATH": crew_fixtures.shell_path("sh", [bindir])})
    body = {"tool_name": "Bash",
            "tool_input": {"command": "aws s3 rm s3://bucket/ --recursive"},
            "cwd": str(tmp_path / "repo")}
    try:
        proc = subprocess.run(
            _argv("bash"), input=json.dumps(body).encode("utf-8"),
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            env=env, cwd=str(tmp_path), timeout=15, check=False)
    finally:
        try:
            os.kill(int(pidfile.read_text(encoding="ascii").strip()), 9)
        except (OSError, ValueError):
            pass
    assert proc.returncode == 0
    doc = json.loads(proc.stdout.decode("utf-8"))
    assert doc["hookSpecificOutput"]["permissionDecision"] == "deny", doc


# --- SRL-2308: the two fallbacks read command words, not mentions ------------
#
# When the trigger's reader gave up on a line, or read a command word made at
# run time (a lone `W=$S/x` assignment is one), it used to gate on ANY word
# naming terraform -- or, for the second, destroy/apply/workspace -- anywhere
# on the line. Each SRL2308_NOT_GATED row was refused that way in real use (or
# is the same shape with the unreadable fallback): a Python heredoc, a
# send.md heredoc, a `sed`/`python3 -c` with a `$VAR`, an inline stub test,
# a heredoc after `W=...`, a `.ps1` copied into `$W/amut`. Each is a FAILING
# control on crew 1.2.35 (reverting either fallback turns it red), except the
# two `-verbatim` rows, which 1.2.35 already allowed. SRL2308_STILL_GATED
# pins that a real terraform/tofu invocation is still
# refused, both on a plain line and through each fallback (`A=(1)` makes the
# reader give up; `X=$W` makes a run-time command word).
SRL2308_NOT_GATED = [
    ("srl2308-a-python-heredoc", "Bash",
     "W=$S/wt1863r8\ncd $W && python3 -I - <<'EOF'\nimport re\n"
     "# apply the patch, then destroy the temp dir\nresult = apply(p)\n"
     "print(result)\nEOF"),
    ("srl2308-a-python-heredoc-unreadable", "Bash",
     "A=(1 2); cd $W && python3 -I - <<'EOF'\n"
     "print('terraform apply -auto-approve')\nEOF"),
    ("srl2308-b-send-md-heredoc", "Bash",
     "M=$W/send.md; cat > \"$M\" <<'EOF'\nReview round 2: apply the fixes, "
     "then destroy the old worktree.\nEOF"),
    ("srl2308-b-send-md-heredoc-unreadable", "Bash",
     "cat > send.md <<'EOF'\nPlease run terraform apply in staging.\nEOF\n"
     "echo $((n+$m))"),
    ("srl2308-c-sed-range", "Bash",
     "B=$W/plugin/crew/hooks/scripts/x.py; sed -n 1,30p $B | grep -n apply"),
    ("srl2308-c-python-c-unreadable", "Bash",
     "python3 -c \"print('terraform apply')\" $((1+$N))"),
    # `srl2308-d-inline-stub` (a stub written into `$T`, then run with
    # `apply`) moved to SRL2308_R4_REFUSE: r3-2's shape (review round 3).
    ("srl2308-d-stub-heredoc", "Bash",
     "S=$W/stub.sh; cat > $S <<EOF\necho \"apply \\$1\"\nEOF\nbash $S apply"),
    # (e), (f): two more refused in real use (manager, 2026-10-15). Each as
    # described -- allowed on 1.2.35 too, pinned so it stays allowed -- and
    # with "apply" in it, which 1.2.35 refused.
    ("srl2308-e-python-heredoc-verbatim", "Bash",
     "W=$S/wt1863r8\ncd $W/plugin/crew && python3 -I - <<'EOF'\nimport json\n"
     "print(json.load(open('../../.crew/verify.json'))['rules'][0])\nEOF"),
    ("srl2308-e-python-heredoc-apply", "Bash",
     "W=$S/wt1863r8\ncd $W/plugin/crew && python3 -I - <<'EOF'\n"
     "# apply round 8, then check\nprint(open('README.md').read()[:80])\nEOF"),
    ("srl2308-f-copy-ps1-verbatim", "Bash",
     "W=$S/wt1863r8; mkdir -p $W/amut && "
     "cp $W/plugin/crew/hooks/scripts/cloud-guard.ps1 $W/amut/"),
    ("srl2308-f-copy-ps1-apply", "Bash",
     "W=$S/wt1863r8; mkdir -p $W/amut && "
     "cp $W/plugin/crew/hooks/scripts/cloud-guard.ps1 $W/amut/ && "
     "ls $W/amut  # then apply the mutant"),
    # The tool and one read-only subcommand, nothing after it; and a bare
    # `apply`, which is a program of that name, not terraform.
    ("srl2308-ro-h-version-only", "Bash", "$S/bin/terraform version"),
    ("srl2308-ro-u-bare-apply", "Bash", "A=(1); terraform version; apply"),
]

_TF = "terraform apply"
SRL2308_STILL_GATED = [
    ("srl2308-tf-apply", "Bash", _TF),
    ("srl2308-tofu-destroy", "Bash", "tofu destroy -auto-approve"),
    ("srl2308-env", "Bash", "env TF_LOG=1 terraform apply"),
    ("srl2308-abs-path", "Bash", "/usr/local/bin/terraform apply"),
    ("srl2308-var", "Bash", "T=terraform; $T apply"),
    ("srl2308-xargs", "Bash", "ls | xargs terraform apply"),
    # The same through the unreadable-line fallback.
    ("srl2308-u-tf-apply", "Bash", f"A=(1); {_TF}"),
    ("srl2308-u-tofu-destroy", "Bash", "A=(1); tofu destroy -auto-approve"),
    ("srl2308-u-env", "Bash", "A=(1); env TF_LOG=1 terraform apply"),
    ("srl2308-u-abs-path", "Bash", "A=(1); /usr/local/bin/terraform apply"),
    ("srl2308-u-npx", "Bash", "A=(1); npx terraform apply"),
    ("srl2308-u-var", "Bash", "A=(1); T=terraform; $T apply"),
    ("srl2308-u-xargs", "Bash", "A=(1); ls | xargs terraform apply"),
    ("srl2308-u-unresolved-var", "Bash", "A=(1); $TF apply"),
    ("srl2308-u-bash-c", "Bash", "A=(1); bash -c 'terraform apply'"),
    ("srl2308-u-heredoc-to-bash", "Bash",
     "A=(1); bash <<'EOF'\nterraform apply\nEOF"),
    ("srl2308-u-subst", "Bash", "A=(1); echo $(terraform apply)"),
    ("srl2308-u-backquote", "Bash", "A=(1); echo `terraform apply`"),
    ("srl2308-u-heredoc-subst", "Bash",
     "A=(1); cat <<EOF\n$(terraform apply)\nEOF"),
    # The same through the run-time-command-word fallback.
    ("srl2308-h-npx", "Bash", "X=$W; npx terraform apply"),
    ("srl2308-h-var", "Bash", "X=$W; T=terraform; $T apply"),
    ("srl2308-h-which", "Bash", "$(command -v terraform) apply"),
    ("srl2308-h-unresolved-var", "Bash", "$TF apply"),
    ("srl2308-h-sudo", "Bash", "X=$W; sudo -u ops terraform apply"),
    # The read-only allowance (`<tool> version`, two words, nothing after)
    # cannot be stretched into an apply: on an unreadable line and behind a
    # run-time command word, any word after the subcommand, or a second
    # command that runs terraform, keeps the line refused.
    ("srl2308-ro-and-apply", "Bash", "terraform version && terraform apply"),
    ("srl2308-ro-semi-apply", "Bash", "terraform version; terraform apply"),
    ("srl2308-ro-u-and-apply", "Bash",
     "A=(1); terraform version && terraform apply"),
    ("srl2308-ro-u-semi-apply", "Bash",
     "A=(1); terraform version; terraform apply"),
    ("srl2308-ro-u-chdir-apply", "Bash",
     "A=(1); terraform version -chdir=x apply"),
    ("srl2308-ro-u-version-apply", "Bash", "A=(1); terraform version apply"),
    ("srl2308-ro-u-version-flag", "Bash", "A=(1); terraform version -json"),
    ("srl2308-ro-h-and-apply", "Bash",
     "$S/bin/terraform version && $S/bin/terraform apply"),
    ("srl2308-ro-h-semi-apply", "Bash",
     "$S/bin/terraform version; $S/bin/terraform apply"),
    ("srl2308-ro-h-chdir-apply", "Bash",
     "$S/bin/terraform version -chdir=x apply"),
    ("srl2308-ro-h-version-apply", "Bash", "$S/bin/terraform version apply"),
    ("srl2308-ro-h-version-flag", "Bash", "$S/bin/terraform version -json"),
    ("srl2308-ro-h-version-var", "Bash", "$S/bin/terraform version $X"),
    # A wildcard command word is still a command word crew cannot name.
    ("srl2308-glob-ext-command", "Bash", "X=$W; ./*.ps1 destroy"),
    ("srl2308-glob-stem-command", "Bash", "./terr*.ps1 destroy"),
]

# Real refusals (fixtures/srl2308_refused_tf.json, sanitised; see its
# `_about`): every `must_allow` row was refused by crew 1.2.30 and 1.2.35,
# and every one runs no terraform but real-05's `version`. `must_refuse` is
# real-24, a legitimate could-not-tell, and real-19, whose Python starts a
# process with a command it builds (review round 2, fail closed; each `why`).
_REAL = json.loads((pathlib.Path(__file__).parent / "fixtures"
                    / "srl2308_refused_tf.json").read_text(encoding="utf-8"))
SRL2308_REAL_ALLOW = [(r["id"], "Bash", r["command"])
                      for r in _REAL["must_allow"]]
SRL2308_REAL_REFUSE = [(r["id"], "Bash", r["command"])
                       for r in _REAL["must_refuse"]]


@pytest.mark.parametrize("case", SRL2308_NOT_GATED,
                         ids=[c[0] for c in SRL2308_NOT_GATED])
def test_srl2308_a_mention_is_not_a_terraform_command(tmp_path, case):
    _allow("python", tmp_path, case)
    assert cloud_guard._literal_gate("bash", case[2]) is None  # pylint: disable=protected-access


@pytest.mark.parametrize("case", SRL2308_STILL_GATED,
                         ids=[c[0] for c in SRL2308_STILL_GATED])
def test_srl2308_a_terraform_command_is_still_refused(tmp_path, case):
    _block("python", tmp_path, case + ("terraformApply",))


@pytest.mark.parametrize("case", SRL2308_REAL_ALLOW,
                         ids=[c[0] for c in SRL2308_REAL_ALLOW])
def test_srl2308_a_real_refusal_that_runs_no_terraform_is_allowed(tmp_path,
                                                                  case):
    _allow("python", tmp_path, case)


@pytest.mark.parametrize("case", SRL2308_REAL_REFUSE,
                         ids=[c[0] for c in SRL2308_REAL_REFUSE])
def test_srl2308_a_real_could_not_tell_stays_refused(tmp_path, case):
    _block("python", tmp_path, case + ("terraformApply",))


def test_srl2308_the_real_rows_are_all_there():
    """24 allowed, real-24 and real-19 refused: a row dropped from the
    fixture would otherwise pass silently."""
    assert len(SRL2308_REAL_ALLOW) == 24 and len(SRL2308_REAL_REFUSE) == 2


@pytest.mark.parametrize("case", [c for c in SRL2308_STILL_GATED
                                  if c[0].startswith(("srl2308-u-",
                                                      "srl2308-ro-u-"))],
                         ids=lambda c: c[0])
def test_srl2308_the_unreadable_fallback_finds_the_command_word(case):
    """Each `-u-` row is one the trigger's reader gives up on, so this pins
    the unreadable-line fallback itself, not the lexer behind it."""
    text = case[2]
    with pytest.raises(crew_guards._Unsure):  # pylint: disable=protected-access
        crew_guards._GateReader(text, 0, []).read()  # pylint: disable=protected-access
    assert crew_guards.command_trigger(
        text, cloud_guard.GATE_HELPERS) is not None, text


# --- SRL-2308 review round 1: lines that may run terraform, refused -------
#
# Codex r1 and the gate found the new fallback fail-open. Each row below is
# a must-refuse control, run through BOTH the python entry point and the
# real hook, `cloud-guard.sh` (block config). Every row marked `allowed@r1`
# was ALLOWED by the reviewed head 3212cde1 (crew 1.2.36 r1) through
# cloud-guard.sh; the r1-2/r1-3 rows were already refused end to end there
# by another layer, and the splitter defect itself is pinned by
# `test_srl2308_r2_the_splitter_gives_up_where_it_cannot_follow`.
_OS_TF = "import os; os.system('terraform apply')"
SRL2308_R2_REFUSE = [
    # r1-1: a glob as a loop variable or an assigned value (allowed@r1).
    ("r1-1-for-glob-exe", "Bash",
     "for f in /opt/tf/*.exe; do $f apply; done"),
    ("r1-1-for-glob-exe-quoted", "Bash",
     "for f in *.exe; do \"$f\" destroy; done"),
    ("r1-1-for-glob-ps1-pwsh", "Bash",
     "W=$S/x; for f in $W/bin/*.ps1; do pwsh -File $f apply; done"),
    ("r1-1-var-glob-exe", "Bash", "T=/opt/tf/*.exe; $T apply"),
    ("r1-1-for-glob-cmd", "Bash",
     "W=$S/x; for f in /opt/tf/*.cmd; do $f destroy -auto-approve; done"),
    ("r1-1-for-glob-stem", "Bash", "for f in /opt/tf/t*; do $f apply; done"),
    # The gate's worse case: a value that is not a literal word counted as
    # "resolved, not terraform" (allowed@r1).
    ("r1-v-from-var", "Bash", "T=$X; $T apply"),
    ("r1-v-from-subst", "Bash", "T=$(cat /tmp/toolname); $T apply"),
    ("r1-v-from-positional", "Bash", "T=$1; $T destroy -auto-approve"),
    ("r1-v-assigned-glob", "Bash", "T=/opt/tf/t*; $T apply"),
    # r1-4: interpreter code that runs terraform (allowed@r1; the plain
    # `python3 -c` rows were allowed by 1.2.35 as well).
    ("r1-4-python-c", "Bash", f"python3 -c \"{_OS_TF}\""),
    ("r1-4-python-c-u", "Bash", f"A=(1); python3 -c \"{_OS_TF}\""),
    ("r1-4-python-c-h", "Bash", f"W=$S/x; python3 -c \"{_OS_TF}\""),
    ("r1-4-python-subprocess-h", "Bash",
     "W=$S/x; python3 -c \"import subprocess; "
     "subprocess.run(['terraform','apply'])\""),
    ("r1-4-python-heredoc-h", "Bash",
     "W=$S/x; python3 - <<'EOF'\nimport os\n"
     "os.system('terraform apply -auto-approve')\nEOF"),
    ("r1-4-node-e-h", "Bash",
     "W=$S/x; node -e \"require('child_process').execSync('terraform "
     "apply')\""),
    ("r1-4-perl-e-h", "Bash", "W=$S/x; perl -e 'system(\"terraform apply\")'"),
    ("r1-4-ruby-e-h", "Bash", "W=$S/x; ruby -e 'system(\"terraform apply\")'"),
    # r1-2 / r1-3, Codex's exact forms.
    ("r1-2-arith-subst", "Bash", "A=(1); echo $(( $(terraform apply) + 1 ))"),
    ("r1-2-param-subst", "Bash", "A=(1); echo ${X:-$(terraform apply)}"),
    ("r1-3-mixed-delim", "Bash",
     "A=(1); cat <<\"'END'\"\n'END'\nterraform apply\nEND"),
    # Found while fixing round 1 (each allowed@r1 unless marked): how else a
    # variable gets a value the line does not show...
    ("r2-param-op", "Bash", "T=terrafxrm; ${T/x/o} apply"),
    ("r2-append", "Bash", "T=terra; T+=form; $T apply"),
    ("r2-conditional", "Bash", "false && T=echo; $T apply"),
    ("r2-prefix-only", "Bash", "T=echo $T apply"),
    ("r2-read", "Bash", "T=echo; read T; $T apply"),
    ("r2-subshell", "Bash", "(T=echo); $T apply"),
    ("r2-if-body", "Bash", "if false; then :; T=echo; fi; $T apply"),
    ("r2-nameref", "Bash", "declare -n T=TF; $T apply"),
    ("r2-printf-v", "Bash", "T=echo; printf -v T %s terraform; $T apply"),
    ("r2-printf-v-attached", "Bash",
     "T=echo; printf -vT %s terraform; $T apply"),
    ("r2-default-assign", "Bash",
     "T=echo; unset T; : ${T:=terraform}; $T apply"),
    ("r2-pipeline", "Bash", "T=echo | true; $T apply"),
    ("r2-background", "Bash", "T=echo & $T apply"),
    ("r2-select", "Bash", "select T in echo; do $T apply; done"),
    ("r2-mapfile", "Bash", "T=echo; mapfile -t T < /tmp/x; $T apply"),
    ("r2-case-arm", "Bash", "case $X in a) T=echo;; esac; $T apply"),
    ("r2-function-body", "Bash", "f() { T=echo; }; $T apply"),
    ("r2-function-keyword", "Bash", "function g { T=echo; }; $T apply"),
    ("r2-if-fi-as-word", "Bash",
     "if false; then echo fi; T=echo; fi; $T apply"),
    ("r2-for-empty-list", "Bash", "for f in; do :; done; $f apply"),
    ("r2-use-before-assign", "Bash", "W=$S/x; $T apply; T=echo"),
    ("r2-read-indirect", "Bash", "T=echo; read \"$N\" <<< terraform; $T apply"),
    ("r2-ifs", "Bash", "IFS=x; T=terraformxapply; $T"),
    ("r2-ifs-quoted", "Bash", "IFS=\" x\"; T=terraformxapply; $T"),
    ("r2-subst-command-word", "Bash", "W=$S/x; $(cat /tmp/toolname) apply"),
    # ...and code handed to an interpreter or a shell.
    ("r2-python-plain-subprocess", "Bash",
     "python3 -c \"import subprocess; subprocess.run(['terraform','apply'])\""),
    ("r2-python-heredoc-plain", "Bash",
     "python3 - <<'EOF'\nimport os\nos.system('terraform apply -auto-approve')"
     "\nEOF"),
    ("r2-python-herestring-h", "Bash", f"W=$S/x; python3 <<< \"{_OS_TF}\""),
    ("r2-python-pipe-h", "Bash", f"W=$S/x; echo \"{_OS_TF}\" | python3"),
    ("r2-heredoc-pipe-python", "Bash",
     "cat <<'EOF' | python3\nimport os\nos.system('terraform apply')\nEOF"),
    ("r2-php-r-h", "Bash", "W=$S/x; php -r 'system(\"terraform apply\");'"),
    ("r2-perl-pipe-open-u", "Bash",
     "A=(1); perl -e 'open(F, \"terraform apply |\"); print <F>'"),
    ("r2-node-p-u", "Bash",
     "A=(1); node -p \"require('child_process').execSync('terraform "
     "apply').toString()\""),
    ("r2-python-expansion-h", "Bash",
     "T=terraform; W=$S/x; python3 -c \"import os; os.system('$T apply')\""),
    ("r2-python-runtime-word-h", "Bash",
     "W=$S/x; python3 -c 'import os; os.system(\"$TF apply\")'"),
    ("r2-env-python-h", "Bash", f"W=$S/x; env FOO=1 python3 -c \"{_OS_TF}\""),
    ("r2-python-Ic-h", "Bash", f"W=$S/x; python3 -Ic \"{_OS_TF}\""),
    ("r2-python-W-value-h", "Bash",
     f"W=$S/x; python3 -W ignore -c \"{_OS_TF}\""),
    ("r2-xargs-python-c-h", "Bash",
     f"W=$S/x; echo \"{_OS_TF}\" | xargs -0 python3 -c"),
    ("r2-ruby-interpolation-h", "Bash",
     "W=$S/x; ruby -e 'puts \"#{system(\"terraform apply\")}\"'"),
    ("r2-python-fstring-h", "Bash",
     "W=$S/x; python3 -c \"print(f'{__import__(\\\"os\\\").system("
     "\\\"terraform apply\\\")}')\""),
    ("r2-bash-file-glob-h", "Bash",
     "W=$S/x; for f in /opt/tf/*.sh; do bash $f apply; done"),
    ("r2-bash-c-runtime-word-u", "Bash", "A=(1); bash -c '$TF apply'"),
    ("r2-heredoc-bash-runtime-word-u", "Bash",
     "A=(1); bash <<'EOF'\n$TF destroy\nEOF"),
    ("r2-node-precise", "Bash",
     "node -e \"require('child_process').execSync('terraform apply')\""),
    ("r2-perl-precise", "Bash", "perl -e 'system(\"terraform apply\")'"),
    ("r2-sudo-python-precise", "Bash", f"sudo python3 -c \"{_OS_TF}\""),
]

# Shapes the stricter reading must still allow: a literal value, a value
# whose program name is literal (`S=$W/stub.sh`), and interpreter code that
# only prints, or names terraform only as a path.
SRL2308_R2_ALLOW = [
    ("r2-ok-path-var-script", "Bash", "S=$W/stub.sh; bash $S apply"),
    ("r2-ok-python-print", "Bash", "python3 -c \"print('terraform apply')\""),
    ("r2-ok-python-print-u", "Bash",
     "A=(1); python3 -c \"print('terraform apply')\""),
    ("r2-ok-python-heredoc-print-h", "Bash",
     "W=$S/x; python3 - <<'EOF'\nprint('terraform apply -auto-approve')"
     "\nEOF"),
    ("r2-ok-node-console-h", "Bash",
     "W=$S/x; node -e \"console.log('terraform apply')\""),
    ("r2-ok-perl-print-h", "Bash",
     "W=$S/x; perl -e 'print \"terraform apply\\n\"'"),
    ("r2-ok-python-path-h", "Bash",
     "W=$S/x; python3 -c \"import json; "
     "print(json.load(open('terraform/x.json')))\""),
    ("r2-ok-arith-var-h", "Bash", "W=$S/x; echo $((n+$m)) apply"),
    ("r2-ok-param-default-h", "Bash", "W=$S/x; echo ${X:-$HOME} apply"),
    ("r2-ok-bash-c-literal-u", "Bash", "A=(1); bash -c 'echo apply'"),
    ("r2-ok-python-script-h", "Bash", "W=$S/x; python3 $W/tool.py apply"),
    ("r2-ok-ifs-read-h", "Bash",
     "W=$S/x; while IFS= read -r l; do echo \"$l\"; done < terraform/x.tf"),
]

_R2_DRIVERS = [pytest.param("python", id="python"),
               pytest.param("bash", id="bash", marks=needs_bash)]


@pytest.mark.parametrize("driver", _R2_DRIVERS)
@pytest.mark.parametrize("case", SRL2308_R2_REFUSE,
                         ids=[c[0] for c in SRL2308_R2_REFUSE])
def test_srl2308_r2_a_line_that_may_run_terraform_is_refused(tmp_path, driver,
                                                             case):
    _block(driver, tmp_path, case + ("terraformApply",))


@pytest.mark.parametrize("driver", _R2_DRIVERS)
@pytest.mark.parametrize("case", SRL2308_R2_ALLOW,
                         ids=[c[0] for c in SRL2308_R2_ALLOW])
def test_srl2308_r2_a_line_that_cannot_run_terraform_is_allowed(tmp_path,
                                                                driver, case):
    _allow(driver, tmp_path, case)


@needs_bash
@pytest.mark.parametrize("case", SRL2308_REAL_ALLOW + SRL2308_NOT_GATED,
                         ids=[c[0] for c in SRL2308_REAL_ALLOW
                              + SRL2308_NOT_GATED])
def test_srl2308_r2_the_allowed_rows_hold_through_the_bash_hook(tmp_path,
                                                                case):
    _allow("bash", tmp_path, case)


@needs_bash
@pytest.mark.parametrize("case", SRL2308_REAL_REFUSE + SRL2308_STILL_GATED,
                         ids=[c[0] for c in SRL2308_REAL_REFUSE
                              + SRL2308_STILL_GATED])
def test_srl2308_r2_the_refused_rows_hold_through_the_bash_hook(tmp_path,
                                                                case):
    _block("bash", tmp_path, case + ("terraformApply",))


# --- L-0871: interpreter code that names nothing is not could-not-tell -------
#
# `grep '^JIRA_' .env | python3 -c "import urllib.parse,sys; print(1)"` and a
# heredoc with `import os` were refused as could-not-tell, and the denial
# quoted `'^JIRA_'` or `'<<'`. Python and node code is now refused only when
# the code or the line names terraform/terragrunt/tofu, or the code reaches a
# process AND builds the name. Rows run through both entry points.
L0871_ALLOW = [
    ("l0871-ok-grep-pipe-python", "Bash",
     "grep '^JIRA_' .env | python3 -c \"import urllib.parse,sys; print(1)\""),
    ("l0871-ok-python-heredoc-os-environ", "Bash",
     "python3 - <<'PY'\nimport os\nprint(os.environ.get('JIRA_EMAIL'))\nPY"),
    ("l0871-ok-node-process-env", "Bash",
     "node -e \"console.log(process.env.JIRA_X)\""),
    ("l0871-ok-home-assign-import", "Bash",
     "HOME=$T/home python3 -c \"import x\""),
    ("l0871-ok-python-heredoc-requests", "Bash",
     "python3 - <<'PY'\nimport requests\n"
     "print(requests.get('https://example.com/rest').status_code)\nPY"),
    ("l0871-ok-u1-command-from-env", "Bash",
     "python3 -c \"import os; os.system(os.environ['CMD'])\""),
    ("l0871-ok-modulo-arithmetic", "Bash",
     "python3 -c \"import os; os.system('echo ok'); print(5 % 2)\""),
    ("l0871-ok-dollar-in-printed-text", "Bash",
     "python3 -c \"import os; os.system('echo ok'); print('$')\""),
    ("l0871-ok-dollar-var-in-printed-text", "Bash",
     "python3 -c 'import os; os.system(\"echo ok\"); print(\"$HOME\")'"),
    ("l0871-ok-separate-imports-not-a-name", "Bash",
     "python3 -c \"import ter, raform; import os; os.system('echo ok')\""),
    ("l0871-ok-separate-literals-not-a-name", "Bash",
     "python3 -c \"import os; os.system('echo ok'); print('ter'); "
     "x = 1; print('raform')\""),
    ("l0871-ok-literal-only-plus-chain", "Bash",
     """python3 -c "import os; msg='hello '+'world'; cmd=msg; os.system(cmd)\""""),
    ("l0871-ok-assigned-literal-command", "Bash",
     """python3 -c "import os; cmd='echo ok'; os.system(cmd)\""""),
    ("l0871-ok-plus-in-a-name-the-call-does-not-use", "Bash",
     """python3 -c "import os; x = a + b; os.system('echo ok')\""""),
    ("l0871-ok-command-from-env-through-a-name", "Bash",
     """python3 -c "import os; part=os.environ['A']; cmd=part; os.system(cmd)\""""),
    ("l0871-ok-ctypes-sizeof", "Bash",
     """python3 -c "import ctypes; print(ctypes.sizeof(ctypes.c_int))\""""),
    ("l0871-ok-node-module-typeof", "Bash",
     """node -e "var m=module; console.log(typeof m)\""""),
    ("l0871-ok-source-env-then-python", "Bash",
     "set -a; source .env; set +a; python3 - <<'PY'\nimport os\n"
     "print(os.environ.get('JIRA_EMAIL'))\nPY"),
]

L0871_REFUSE = [
    ("l0871-no-concat", "Bash",
     "python3 -c \"import os; os.system('ter'+'raform apply')\""),
    ("l0871-no-join", "Bash",
     "python3 -c 'import os; os.system(\"\".join([\"ter\",\"raform\"])"
     "+\" apply\")'"),
    ("l0871-no-chr", "Bash",
     "python3 -c \"import os; os.system(chr(116)+'erraform apply')\""),
    ("l0871-no-bytes-fromhex", "Bash",
     "python3 -c \"import subprocess; subprocess.run("
     "[bytes.fromhex('7465727261666f726d').decode(),'apply'])\""),
    ("l0871-no-escape", "Bash",
     r"""python3 -c 'import os; os.system("\x74erraform apply")'"""),
    ("l0871-no-tofu-concat", "Bash",
     "python3 -c \"import os; os.system('to'+'fu apply')\""),
    ("l0871-no-heredoc-concat", "Bash",
     "W=$S/x; python3 - <<'EOF'\nimport os\nos.system('ter'+'raform apply')"
     "\nEOF"),
    ("l0871-no-node-concat", "Bash",
     "node -e \"require('child_process').execSync('ter'+'raform apply')\""),
    ("l0871-no-node-template", "Bash",
     "node -e \"require('child_process').execSync(`${'ter'}raform apply`)\""),
    ("l0871-no-shell-var-in-code", "Bash",
     "T=terraform; python3 -c \"import os; os.system('$T apply')\""),
    ("l0871-no-pipe-heredoc-named", "Bash",
     "cat <<'EOF' | python3\nimport os\nos.system('terraform apply')\nEOF"),
    ("l0871-no-named-beside-grep", "Bash",
     "grep '^JIRA_' .env | python3 -c \"import os; "
     "os.system('terraform apply')\""),
    ("l0871-no-rf-string", "Bash",
     """python3 -c "import os; part=os.environ['CMD']; os.system(rf'{part} apply')\""""),
    ("l0871-no-fr-string", "Bash",
     """python3 -c "import os; part=os.environ['CMD']; os.system(fr'{part} apply')\""""),
    ("l0871-no-Rf-string", "Bash",
     """python3 -c "import os; part=os.environ['CMD']; os.system(Rf'{part} apply')\""""),
    ("l0871-no-fR-string", "Bash",
     """python3 -c "import os; part=os.environ['CMD']; os.system(fR'{part} apply')\""""),
    ("l0871-no-rb-fragments", "Bash",
     """python3 -c "import os; os.system(Rb'ter' rb'raform apply')\""""),
    ("l0871-no-percent-after-literal", "Bash",
     """python3 -c "import os; os.system('ter%sform apply' % 'ra')\""""),
    ("l0871-no-percent-var-format", "Bash",
     """python3 -c "import os; t='ter%sform'; os.system(t % 'ra')\""""),
    ("l0871-no-dollar-in-process-arg", "Bash",
     """python3 -c 'import os; os.system("$CMD")'"""),
    ("l0871-no-dollar-in-assigned-command", "Bash",
     """python3 -c 'import os; c="$TF apply"; os.system(c)'"""),
    ("l0871-no-adjacent-literals", "Bash",
     """python3 -c "import os; os.system('ter' 'raform apply')\""""),
    ("l0871-no-empty-literal-splice", "Bash",
     """python3 -c "import os; os.system('ter'""'raform apply')\""""),
    ("l0871-no-augmented-assign", "Bash",
     """python3 -c "import os; c='ter'; c+='raform'; os.system(c)\""""),
    ("l0871-no-variable-concat", "Bash",
     """python3 -c "import os; a='ter'; b='raform'; os.system(a+b+' apply')\""""),
    ("l0871-no-bytes-list", "Bash",
     """python3 -c "import os; os.system(bytes([116,101,114,114,97,102,111,114,109]).decode()+' apply')\""""),
    ("l0871-no-getattr-system", "Bash",
     """python3 -c "import os; getattr(os,'sys'+'tem')('ter'+'raform apply')\""""),
    ("l0871-no-dunder-import", "Bash",
     """python3 -c "__import__('os').system('ter'+'raform apply')\""""),
    ("l0871-no-heredoc-rf", "Bash",
     "python3 - <<'PY'\nimport os\np = os.environ['CMD']\nos.system(rf'{p} apply')\nPY"),
    ("l0871-no-heredoc-bytes", "Bash",
     "python3 - <<'PY'\nimport os\nos.system(bytes([116,101,114,114,97,102,111,114,109]).decode())\nPY"),
    ("l0871-no-node-split-module-name", "Bash",
     """node -e "require('child_'+'process').execSync('terra'+'form apply')\""""),
    ("l0871-no-node-variable-concat", "Bash",
     """node -e "const a='ter'; require('child_process').execSync(a+'raform apply')\""""),
    ("l0871-no-assigned-name-plus-literal", "Bash",
     """python3 -c "import os; part='ter'; cmd=part+'raform apply'; os.system(cmd)\""""),
    ("l0871-no-three-hop-chain", "Bash",
     """python3 -c "import os; a='ter'; b=a+'ra'; c=b+'form apply'; os.system(c)\""""),
    ("l0871-no-name-plus-name-chain", "Bash",
     """python3 -c "import os; a='ter'; b='raform'; c=a+b; os.system(c)\""""),
    ("l0871-no-name-plus-name-two-hops", "Bash",
     """python3 -c "import os; a='ter'; b='raform'; c=a+b; d=c; os.system(d)\""""),
    ("l0871-no-augmented-name-join", "Bash",
     """python3 -c "import os; a='ter'; b='raform'; c=a; c+=b; os.system(c)\""""),
    ("l0871-no-annotated-assignment", "Bash",
     """python3 -c "import os; part='ter'; cmd: str = part + 'raform'; os.system(cmd)\""""),
    ("l0871-no-fstring-chain", "Bash",
     """python3 -c "import os; a='ter'; c=f'{a}raform'; os.system(c)\""""),
    ("l0871-no-percent-chain", "Bash",
     """python3 -c "import os; t='ter%sform'; c=t % 'ra'; os.system(c)\""""),
    ("l0871-no-format-chain", "Bash",
     """python3 -c "import os; c='ter{}form'.format('ra'); os.system(c)\""""),
    ("l0871-no-join-chain", "Bash",
     """python3 -c "import os; c=''.join(['ter','raform']); os.system(c)\""""),
    ("l0871-no-heredoc-chain-over-lines", "Bash",
     "python3 - <<'PY'\nimport os\npart = 'ter'\ncmd = part + 'raform apply'\nos.system(cmd)\nPY"),
    ("l0871-no-node-chain", "Bash",
     """node -e "const a='ter'; const c=a+'raform'; require('child_process').execSync(c)\""""),
    ("l0871-no-ctypes-reach", "Bash",
     """python3 -c "import ctypes; ctypes.CDLL(None).go('ter'+'raform apply')\""""),
    ("l0871-no-importlib-reach", "Bash",
     """python3 -c "import importlib; importlib.import_module('x').go('ter'+'raform apply')\""""),
    ("l0871-no-runpy-reach", "Bash",
     """python3 -c "import runpy; runpy.run_path('x', {'a': 'ter'+'raform apply'})\""""),
    ("l0871-no-node-module-reach", "Bash",
     """node -e "module.require('x').go('ter'+'raform apply')\""""),
    ("l0871-no-line-names-tool-python", "Bash",
     "T=terraform; python3 -c \"import os; os.system(os.environ['CMD'])\""),
    ("l0871-no-line-names-tool-pipe", "Bash",
     "grep terraform main.tf | python3 -c \"import os; "
     "os.system(os.environ['CMD'])\""),
    ("l0871-no-line-names-tool-node", "Bash",
     "T=terraform; node -e \"require('child_process')"
     ".execSync(process.env.CMD)\""),
]


@pytest.mark.parametrize("driver", _R2_DRIVERS)
@pytest.mark.parametrize("case", L0871_ALLOW,
                         ids=[c[0] for c in L0871_ALLOW])
def test_l0871_interpreter_code_that_names_no_tool_is_allowed(tmp_path,
                                                              driver, case):
    _allow(driver, tmp_path, case)


@pytest.mark.parametrize("driver", _R2_DRIVERS)
@pytest.mark.parametrize("case", L0871_REFUSE,
                         ids=[c[0] for c in L0871_REFUSE])
def test_l0871_interpreter_code_that_builds_the_tool_name_is_refused(
        tmp_path, driver, case):
    _block(driver, tmp_path, case + ("terraformApply",))


L0871_MESSAGE = [
    ("l0871-msg-chr",
     "grep '^JIRA_' .env | python3 -c \"import os; "
     "os.system(chr(116)+'erraform apply')\"",
     "'chr('", "'^JIRA_'"),
    ("l0871-msg-join",
     "python3 - <<'PY'\nimport os\nos.system(''.join(['ter','raform']))\nPY",
     "spells 'terraform' out of fragments", "'<<'"),
    ("l0871-msg-named",
     "grep '^JIRA_' .env | python3 -c \"import os; "
     "os.system('terraform apply')\"",
     "names 'terraform' and may start a process", "'^JIRA_'"),
    ("l0871-msg-node-concat",
     "node -e \"require('child_process').execSync('ter'+'raform apply')\"",
     "node code that spells 'terraform' out of fragments", "'execSync'"),
]


@pytest.mark.parametrize("driver", _R2_DRIVERS)
@pytest.mark.parametrize("case", L0871_MESSAGE,
                         ids=[c[0] for c in L0871_MESSAGE])
def test_l0871_a_refusal_names_the_construct_that_caused_it(tmp_path, driver,
                                                            case):
    _id, command, construct, unrelated = case
    _fixture(tmp_path, ARMED)
    decision, reason, code, err = run_hook(driver, tmp_path, "Bash", command)
    assert code == 0, err
    assert decision == "deny", (command, reason)
    assert construct in reason, reason
    assert "not a plain literal" not in reason, reason
    assert unrelated not in reason, reason


# --- SRL-2308 review round 2: fail closed ---------------------------------
#
# Codex r2 and the gate found the r1 head (3edc97bf) fail-open: a command
# word made at run time was gated only before a literal changing verb, a
# variable holding a bare name (`T=ls`) counted as that program, and
# interpreter code that builds its command (`"terra"+"form"`, `sys.argv`)
# passed. Every row below is a must-refuse control run through BOTH entry
# points; each was ALLOWED by 3edc97bf through cloud-guard.sh (block), except
# `r2-4-perl-pe-h`, Codex's exact r2-4 form, which another layer refused
# there -- `r2-4-perl-lne` is its fail-open twin.
_SET_TF = "set -- terraform apply; "
SRL2308_R3_REFUSE = [
    # Codex r2-1..r2-5.
    ("r2-1-V-apply", "Bash", "V=apply; $TF $V"),
    ("r2-2-argv-join", "Bash",
     "W=$S/x; python3 -c 'import os,sys; os.system(\" \".join(sys.argv[1:]))'"
     " terraform apply"),
    ("r2-3-concat", "Bash",
     "W=$S/x; python3 -c 'import os; os.system(\"terra\"+\"form apply\")'"),
    ("r2-4-perl-pe-h", "Bash", "W=$S/x; perl -pe 'system(\"terraform apply\")'"),
    ("r2-4-perl-lne", "Bash",
     "perl -lne 'system(\"terraform apply\")' /dev/null"),
    ("r2-5-T-ls", "Bash", "T=ls; $T apply"),
    # The gate's fail-open class: any command word made at run time.
    ("r3-set-1-2", "Bash", _SET_TF + "$1 $2"),
    ("r3-set-at", "Bash", _SET_TF + "$@"),
    ("r3-set-star", "Bash", _SET_TF + "$*"),
    ("r3-set-quoted-at", "Bash", _SET_TF + "\"$@\""),
    ("r3-set-at-h", "Bash", "W=$S/x; " + _SET_TF + "\"$@\""),
    ("r3-set-destroy", "Bash",
     "set -- terraform destroy -auto-approve; $1 $2 $3"),
    ("r3-set-env-at", "Bash", _SET_TF + "env \"$@\""),
    ("r3-set-timeout-env-at", "Bash", _SET_TF + "timeout 30 env \"$@\""),
    ("r3-dollar0-c", "Bash", "$0 -c 'terraform apply'"),
    ("r3-dollar0-c-h", "Bash", "W=$S/x; $0 -c 'terraform apply'"),
    ("r3-bash-default-c", "Bash", "${BASH:-bash} -c 'terraform apply'"),
    ("r3-shell-c", "Bash", "$SHELL -c 'terraform apply'"),
    ("r3-subst-bash-c", "Bash", "$(command -v bash) -c 'terraform apply'"),
    ("r3-unresolved-c", "Bash", "B=$X; $B -c 'terraform apply'"),
    ("r3-shell-herestring", "Bash", "$SHELL <<< 'terraform apply'"),
    ("r3-unresolved-heredoc", "Bash",
     "B=$X; $B <<'EOF'\nterraform apply\nEOF"),
    ("r3-set-bash-c", "Bash",
     "set -- bash; $1 -c 'terraform destroy -auto-approve'"),
    ("r3-unresolved-both", "Bash", "T=$X; V=$Y; $T $V # terraform"),
    ("r3-T-ls-path", "Bash", "T=ls; PATH=/opt/tf-shim:$PATH; $T apply"),
    ("r3-path-then-ls", "Bash", "PATH=/opt/tf-shim:$PATH; ls apply"),
    # Interpreter code that builds its command.
    ("r3-py-concat", "Bash",
     "python3 -c 'import os; os.system(\"terra\"+\"form apply\")'"),
    ("r3-py-adjacent", "Bash",
     "python3 -c 'import os; print(os.system(\"terr\" \"aform apply\"))'"),
    ("r3-py-argv", "Bash",
     "python3 -c 'import os,sys; print(os.system(sys.argv[1]))' "
     "'terraform apply'"),
    ("r3-py-hex", "Bash",
     "python3 -c 'import os; print(os.system(\"\\x74erraform apply\"))'"),
    ("r3-py-comment-quote", "Bash",
     "python3 - <<'EOF'\n# it's here\n"
     "import os; os.system('terra' + 'form apply')\nEOF"),
    # Allowed by round 1 as must-allow rows, refused now: a variable whose
    # value is a bare name may be an inherited function (`T=echo`, as
    # `T=ls`), and a value made at run time inside interpreter code is code
    # (`print('$R')` with R=`'); os.system('...`). 1.2.35 refused all three.
    ("r3-bare-name-var", "Bash", "T=echo; $T apply"),
    ("r3-bare-name-for", "Bash", "for t in echo printf; do $t apply; done"),
    ("r3-python-c-run-time-value", "Bash",
     "R=$W; python3 -c \"import sys; print('apply'); print('$R')\""),
]

# Shapes the fail-closed reading must still allow: print-only code with a
# comment (r2-6), a run-time argument of the literal program `timeout` runs,
# the `[` builtin, and a placeholder string in Python that starts nothing.
SRL2308_R3_ALLOW = [
    ("r2-6-print-comment", "Bash",
     "python3 -c 'print(\"terraform apply\") # note'"),
    ("r3-ok-timeout-program", "Bash",
     "W=$S/x; timeout 1500 codex exec --skip-git-repo-check "
     "\"$(cat $W/prompt.txt)\" # apply"),
    ("r3-ok-test-builtin", "Bash", "W=$S/x; [ -z \"$X\" ] && echo apply"),
    ("r3-ok-py-placeholder", "Bash",
     "W=$S/x; python3 - <<'PY'\n"
     "s = open('a.md').read().replace('__COUNTS__', 'apply')\n"
     "open('a.md', 'w').write(s)\nPY"),
]


@pytest.mark.parametrize("driver", _R2_DRIVERS)
@pytest.mark.parametrize("case", SRL2308_R3_REFUSE,
                         ids=[c[0] for c in SRL2308_R3_REFUSE])
def test_srl2308_r3_a_run_time_command_word_is_refused(tmp_path, driver,
                                                       case):
    _block(driver, tmp_path, case + ("terraformApply",))


@pytest.mark.parametrize("driver", _R2_DRIVERS)
@pytest.mark.parametrize("case", SRL2308_R3_ALLOW,
                         ids=[c[0] for c in SRL2308_R3_ALLOW])
def test_srl2308_r3_a_line_that_cannot_run_terraform_is_allowed(tmp_path,
                                                                driver, case):
    _allow(driver, tmp_path, case)


# --- SRL-2308 review round 3: fail closed, cycle 4 --------------------------
#
# Codex r3 and the gate found the r3 head (533a9589) fail-open on the
# fallback lines: an awk program's `system()` and sed's `e` (r3-1), a
# program by path under a run-time directory (r3-2), and `read` behind
# `command`/`builtin` (r3-3). Every row below was ALLOWED by 533a9589
# through cloud-guard.sh (block) and is a must-refuse control through BOTH
# entry points. The first seven are the review's own rows, verbatim.
_AWK_TF = "awk 'BEGIN { system(\"terraform apply\") }'"
SRL2308_R4_REFUSE = [
    ("r3-1-awk-A", "Bash", "A=(1); " + _AWK_TF),
    ("r3-1b-awk-W", "Bash", "W=$S/x; " + _AWK_TF),
    ("r3-1c-sed-e-W", "Bash", "W=$S/x; echo x | sed 's/x/terraform apply/e'"),
    ("r3-2-mktemp-stub", "Bash",
     "T=$(mktemp -d); printf '#!/bin/sh\\nterraform \"$@\"\\n' > \"$T/stub\";"
     " chmod +x \"$T/stub\"; \"$T/stub\" apply"),
    ("r3-2b-W-stub", "Bash", "W=$S/x; \"$W/stub\" apply"),
    ("r3-3-command-read", "Bash",
     "A=(1); T=/bin/echo; command read \"$N\" <<< terraform; $T apply"),
    ("r3-3b-builtin-read", "Bash",
     "A=(1); T=/bin/echo; builtin read \"$N\" <<< terraform; $T apply"),
    # r3-1's class: other awks, every way awk starts a process, sed's `e`.
    ("r4-gawk-A", "Bash", "A=(1); g" + _AWK_TF),
    ("r4-mawk-concat-A", "Bash",
     "A=(1); mawk 'BEGIN { system(\"terra\" \"form apply\") }'"),
    ("r4-nawk-W", "Bash", "W=$S/x; n" + _AWK_TF),
    ("r4-busybox-awk-W", "Bash",
     "W=$S/x; busybox awk 'BEGIN { system(\"terra\" \"form apply\") }'"),
    ("r4-awk-in-bash-c-A", "Bash",
     "A=(1); bash -c \"awk 'BEGIN { system(\\\"terra\\\" "
     "\\\"form apply\\\") }'\""),
    ("r4-awk-print-pipe-W", "Bash",
     "W=$S/x; awk 'BEGIN { print \"apply\" | \"terraform\" }'"),
    ("r4-awk-getline-W", "Bash",
     "W=$S/x; awk 'BEGIN { \"terraform apply\" | getline x }'"),
    ("r4-gawk-coprocess-A", "Bash",
     "A=(1); gawk 'BEGIN { print \"\" |& \"terraform apply\" }'"),
    ("r4-awk-v-value-W", "Bash",
     "W=$S/x; awk -v c=\"terraform apply\" 'BEGIN { system(c) }'"),
    ("r4-awk-f-file-W", "Bash", "W=$S/x; awk -f $W/x.awk # apply"),
    ("r4-sed-e-command-A", "Bash", "A=(1); echo terraform apply | sed e"),
    ("r4-sed-address-e-W", "Bash", "W=$S/x; echo terraform apply | sed '1e'"),
    ("r4-sed-dash-e-flag-W", "Bash",
     "W=$S/x; echo x | sed -n -e 's/x/terraform apply/ep'"),
    ("r4-gsed-split-name-W", "Bash",
     "W=$S/x; echo x | gsed 's|x|terra''form apply|e'"),
    ("r4-sed-run-time-script-A", "Bash",
     "A=(1); echo x | sed \"s/x/$C/\" # terraform"),
    # r3-3's class: other setters behind a wrapper.
    ("r4-command-mapfile", "Bash",
     "A=(1); T=/bin/echo; command mapfile \"$N\" <<< terraform; $T apply"),
    # r3-2's class: a changing verb, or the line writing the program.
    ("r4-stub-destroy-W", "Bash", "W=$S/x; \"$W/stub\" destroy -auto-approve"),
    ("r4-stub-literal-dir-var-A", "Bash", "A=(1); D=/opt/x; $D/stub apply"),
    ("r4-stub-heredoc-write", "Bash",
     "T=$(mktemp -d); cat > \"$T/stub\" <<'EOF'\nterraform \"$@\"\nEOF\n"
     "chmod +x \"$T/stub\"; \"$T/stub\" plan # apply"),
    ("r4-stub-cp-into-W", "Bash",
     "W=$S/x; cp ./wrap.sh \"$W/stub\"; \"$W/stub\" fmt # apply"),
    # A must-allow row until review round 3 (`srl2308-d-inline-stub`): the
    # stub here echoes, but the line writes it into `$T` and runs it with
    # `apply`, so what it runs is not known -- Codex r3-2 made the same
    # line's stub delegate to terraform. 1.2.35 refused it too.
    ("r4-was-ok-inline-stub", "Bash",
     "T=$(mktemp -d); printf '#!/bin/sh\\necho apply\\n' > $T/stub; "
     "chmod +x $T/stub; $T/stub apply"),
]

# What the cycle-4 reading must still allow: awk and sed that start no
# process, a literal `read`, and a program by path under a run-time
# directory run with no changing verb on a line that writes nothing into it.
SRL2308_R4_ALLOW = [
    ("r4-ok-awk-print-W", "Bash",
     "W=$S/x; awk -F: '{print $1}' /etc/passwd # apply"),
    ("r4-ok-awk-sum-A", "Bash",
     "A=(1); git ls-files | awk '{s+=1} END{print s}' # apply"),
    ("r4-ok-awk-regex-alternation-W", "Bash",
     "W=$S/x; awk '/apply|destroy/ {n++} END{print n}' log.txt"),
    ("r4-ok-sed-print-W", "Bash",
     "W=$S/x; sed -n '1,/^cases=(/p' f | sed '$d' # apply"),
    ("r4-ok-sed-substitute-A", "Bash", "A=(1); sed 's|.*/||; s/e/E/g' f # apply"),
    ("r4-ok-sed-in-place-W", "Bash",
     "W=$S/x; sed -i.bak -e 's/old/new/' $W/notes.txt # apply"),
    ("r4-ok-command-read-literal", "Bash",
     "A=(1); command read -r line < f; echo \"$line\" apply"),
    ("r4-ok-stub-check-W", "Bash", "W=$S/x; \"$W/stub.sh\" --check"),
    ("r4-ok-stub-status-A", "Bash", "A=(1); S=$W/tool.sh; $S status # apply"),
    ("r4-ok-stub-other-write-W", "Bash",
     "W=$S/x; echo hi > $HOME/log.txt; \"$W/tool.sh\" run-tests"),
]


@pytest.mark.parametrize("driver", _R2_DRIVERS)
@pytest.mark.parametrize("case", SRL2308_R4_REFUSE,
                         ids=[c[0] for c in SRL2308_R4_REFUSE])
def test_srl2308_r4_a_fallback_line_that_may_run_terraform_is_refused(
        tmp_path, driver, case):
    _block(driver, tmp_path, case + ("terraformApply",))


@pytest.mark.parametrize("driver", _R2_DRIVERS)
@pytest.mark.parametrize("case", SRL2308_R4_ALLOW,
                         ids=[c[0] for c in SRL2308_R4_ALLOW])
def test_srl2308_r4_a_fallback_line_that_cannot_run_terraform_is_allowed(
        tmp_path, driver, case):
    _allow(driver, tmp_path, case)


@pytest.mark.parametrize(("script", "runs"), [
    ("s/x/y/e", True), ("1e", True), ("e date", True), ("/a/{e\n}", True),
    ("s/x/y/ge", True), ("$!N;e", True), ("\\%a%e", True),
    ("s/x/y/g", False), ("1,/^cases=(/p", False), ("$d", False),
    ("s|.*/||; s/e/E/g", False), ("/e/d", False), ("y/abe/xyz/", False),
    ("a hello e", False), ("s/a/b/w out.e", False), ("0,/x/s//e e/", False),
])
def test_srl2308_r4_sed_e_is_read_as_a_command(script, runs):
    """sed's `e` command and `s///e` flag start a process; an `e` in a
    pattern, a replacement, text or a file name does not."""
    assert crew_guards._sed_runs(script) is runs, script  # pylint: disable=protected-access


# --- SRL-2308 review round 4: fail closed, cycle 5 --------------------------
#
# Codex r4 and the gate found the r4 head (5cd547d5) fail-open on two
# fallback paths: a relative program run after the line changes directory
# (r4-1) and an awk pipe split by a backslash-newline (r4-2). Every row in
# SRL2308_R5_REFUSE was ALLOWED by 5cd547d5 through cloud-guard.sh (block)
# and is a must-refuse control through BOTH entry points. The first four
# are the review's own rows, verbatim (Codex r4-1, r4-2; gate g09, g10).
_CD_STUB = "T=$(mktemp -d); "
SRL2308_R5_REFUSE = [
    ("r4-1-cd-relative-stub", "Bash",
     _CD_STUB + "cd \"$T\"; printf '#!/bin/sh\\nterraform \"$@\"\\n' > stub;"
     " chmod +x stub; ./stub apply"),
    ("r4-2-awk-print-pipe-continuation", "Bash",
     "A=(1); awk 'BEGIN { print \"terraform apply\" \\\n | \"sh\" }'"),
    ("r4-g09-cd-and-stub", "Bash", _CD_STUB + "cd \"$T\" && ./stub apply"),
    ("r4-g10-pushd-stub", "Bash",
     _CD_STUB + "pushd \"$T\" >/dev/null; ./stub apply"),
    # r4-1's class: every directory change, every relative spelling.
    ("r5-builtin-cd-stub", "Bash", _CD_STUB + "builtin cd \"$T\"; ./stub apply"),
    ("r5-command-cd-stub", "Bash", _CD_STUB + "command cd \"$T\"; ./stub apply"),
    ("r5-popd-stub", "Bash", "A=(1); popd >/dev/null; ./stub apply"),
    ("r5-cd-subshell-stub", "Bash", _CD_STUB + "(cd \"$T\" && ./stub apply)"),
    ("r5-cd-parent-stub", "Bash", _CD_STUB + "cd \"$T\"; ../stub apply"),
    ("r5-cd-sub-path-stub", "Bash", _CD_STUB + "cd \"$T\"; bin/stub apply"),
    ("r5-cd-quoted-stub", "Bash", _CD_STUB + "cd \"$T\"; \"./stub\" apply"),
    ("r5-cd-verb-elsewhere", "Bash", _CD_STUB + "cd \"$T\"; ./stub plan # apply"),
    ("r5-cd-sudo-stub", "Bash", _CD_STUB + "cd \"$T\"; sudo ./stub apply"),
    ("r5-env-chdir-long-stub", "Bash",
     _CD_STUB + "env --chdir=\"$T\" ./stub apply"),
    ("r5-env-chdir-attached-stub", "Bash",
     _CD_STUB + "env -C\"$T\" ./stub plan # apply"),
    # A literal absolute directory is placed, but the line writes the
    # program there (rule (b)) or runs it with a changing verb (rule (a)).
    ("r5-cd-literal-write-stub", "Bash",
     "A=(1); cd /lit; printf '#!/bin/sh\\nterraform \"$@\"\\n' > stub;"
     " chmod +x stub; ./stub apply"),
    ("r5-cd-literal-write-stub-T", "Bash",
     _CD_STUB + "cd /lit; printf '#!/bin/sh\\nterraform \"$@\"\\n' > stub;"
     " chmod +x stub; ./stub apply"),
    ("r5-cd-literal-cp-stub", "Bash",
     "A=(1); cd /lit && cp x stub && ./stub apply"),
    ("r5-cd-literal-write-plan", "Bash",
     "A=(1); cd /lit && printf 'terraform \"$@\"' > bin/stub; bin/stub plan"
     " # apply"),
    ("r5-cd-literal-write-into-dir", "Bash",
     "A=(1); cd /lit; cp ./w.sh /lit/sub/stub; sub/stub fmt # apply"),
    ("r5-cd-literal-then-runtime", "Bash",
     _CD_STUB + "cd /lit; cd \"$T\"; ./stub plan # apply"),
    ("r5-cd-literal-then-popd", "Bash",
     "A=(1); pushd /lit; popd; ./stub plan # apply"),
    ("r5-cd-dash", "Bash", "A=(1); cd -; ./stub plan # apply"),
    ("r5-cd-home", "Bash", "A=(1); cd; ./stub plan # apply"),
    ("r5-eval-cd", "Bash", _CD_STUB + "eval 'cd \"$T\"'; ./stub plan # apply"),
    # Only a quoted heredoc fed to a bare `cat` is data; its redirection
    # still counts, and a body a shell runs is read as code.
    ("r5-cd-literal-cat-heredoc-stub", "Bash",
     "A=(1); cd /lit; cat > stub <<'EOF'\n#!/bin/sh\nterraform \"$@\"\nEOF\n"
     "chmod +x stub; ./stub plan # apply"),
    ("r5-cd-literal-source", "Bash",
     "A=(1); cd /lit; source ./env.sh; ./stub plan # apply"),
    ("r5-eval-run-time", "Bash",
     "A=(1); X=$(cat f); eval \"$X\"; ./stub apply"),
    # r4-2's class: awk code split by a continuation, and gawk's indirect
    # call (`@f(...)` with `f = "system"`).
    ("r5-awk-printf-pipe-continuation", "Bash",
     "W=$S/x; awk 'BEGIN { printf \"terraform apply\\n\" \\\n | \"sh\" }'"),
    ("r5-awk-system-continuation", "Bash",
     "A=(1); awk 'BEGIN { system \\\n (\"terraform apply\") }'"),
    ("r5-gawk-indirect-system", "Bash",
     "A=(1); gawk 'BEGIN { f = \"system\"; @f(\"terraform apply\") }'"),
]

# Rows 5cd547d5 already refused, kept as controls on the new readers: a
# division read as division (were it read as a regex, the code between the
# two slashes would be hidden), an escaped quote, a regex bracket holding
# `/`, continuations 5cd547d5's pattern happened to span, `env -C`, and the
# gate's r4 probes that held.
SRL2308_R5_HELD = [
    ("r5-awk-getline-continuation", "Bash",
     "A=(1); awk 'BEGIN { \"terraform apply\" \\\n | getline x }'"),
    ("r5-awk-coprocess-continuation", "Bash",
     "A=(1); gawk 'BEGIN { print \"\" \\\n |& \"terraform apply\" }'"),
    ("r5-env-chdir-stub", "Bash", _CD_STUB + "env -C \"$T\" ./stub apply"),
    ("r5-cd-literal-bash-heredoc-write", "Bash",
     "A=(1); cd /lit; bash <<'EOF'\nprintf 'terraform \"$@\"' > stub\n"
     "chmod +x stub\nEOF\n./stub plan # apply"),
    ("r5-awk-postfix-division", "Bash",
     "A=(1); awk 'BEGIN { i++ / 2; print \"terraform apply\" | \"sh\";"
     " j++ / 3 }'"),
    ("r5-awk-paren-division", "Bash",
     "A=(1); awk 'BEGIN { x = (4) / 2; print \"terraform apply\" | \"sh\";"
     " y = (6) / 3 }'"),
    ("r5-awk-escaped-quote", "Bash",
     "A=(1); awk 'BEGIN { print \"a\\\"b\" | \"terraform apply\" }'"),
    ("r5-awk-bracket-slash", "Bash",
     "A=(1); awk '/[/]/ { print | \"terraform apply\" }'"),
    ("r4-g01-gawk-e", "Bash",
     "A=(1); gawk -e 'BEGIN { system(\"terraform apply\") }'"),
    ("r4-g02-gawk-source", "Bash",
     "A=(1); gawk --source 'BEGIN { system(\"terraform apply\") }'"),
    ("r4-g03-awk-environ", "Bash",
     "A=(1); C='terraform apply' awk 'BEGIN { system(ENVIRON[\"C\"]) }'"),
    ("r4-g04-awk-v-var", "Bash",
     "W=$S/x; awk -v c='terraform apply' 'BEGIN { system(c) }'"),
    ("r4-g05-gawk-include", "Bash",
     "A=(1); gawk '@include \"/tmp/t.awk\"; BEGIN { f() }' # apply"),
    ("r4-g06-sed-ew-file", "Bash",
     "W=$S/x; echo x | sed 's/x/terraform apply/ew /dev/null'"),
    ("r4-g07-sed-e-cmd", "Bash", "W=$S/x; echo 'terraform apply' | sed -e e"),
    ("r4-g08-sed-expression-long", "Bash",
     "W=$S/x; echo x | sed --expression='s/x/terraform apply/e'"),
    ("r4-g11-install-stdin", "Bash",
     _CD_STUB + "install -m755 /dev/stdin \"$T/s\" <<< 'terraform \"$@\"';"
     " \"$T/s\" apply"),
    ("r4-g12-install-stdin-plan", "Bash",
     _CD_STUB + "install -m755 /dev/stdin \"$T/s\" <<< 'terraform \"$@\"';"
     " \"$T/s\" plan # apply"),
    ("r4-g13-command-mapfile", "Bash",
     "A=(1); T=/bin/echo; command mapfile \"$N\" <<< terraform; $T apply"),
    ("r4-g14-builtin-readarray", "Bash",
     "A=(1); T=/bin/echo; builtin readarray \"$N\" <<< terraform; $T apply"),
    ("r4-g15-command-p-read", "Bash",
     "A=(1); T=/bin/echo; command -p read \"$N\" <<< terraform; $T apply"),
    ("r4-g16-builtin-printf-v", "Bash",
     "A=(1); T=/bin/echo; builtin printf -v \"$N\" terraform; $T apply"),
    ("r4-g17-env-awk", "Bash",
     "A=(1); env awk 'BEGIN { system(\"terraform apply\") }'"),
    ("r4-g18-xargs-gawk", "Bash",
     "W=$S/x; echo | xargs gawk 'BEGIN { system(\"terraform apply\") }'"),
    ("r4-g19-awk-getline-cmd", "Bash",
     "A=(1); awk 'BEGIN { \"terraform apply\" | getline x }'"),
    ("r4-g20-stub-quoted-verb", "Bash", "W=$S/x; \"$W/stub\" ap''ply"),
    ("r4-g21-stub-dashdash-verb", "Bash", "W=$S/x; \"$W/stub\" -- apply"),
]

# What the cycle-5 reading must allow: Codex r4-3 (a string that only reads
# like a process call), awk strings, regex constants and division holding
# `|` or `/`, the gate's r4 must-allow rows, a relative program on a line
# that changes directory but names no changing verb, and a relative program
# on a line that changes no directory (1.2.36's reading, unchanged).
SRL2308_R5_ALLOW = [
    ("r4-3-awk-string-only", "Bash",
     "A=(1); awk 'BEGIN { print \"system(terraform apply)\" }'"),
    ("r5-ok-awk-string-pipe", "Bash", "A=(1); awk '{ print \"a|b\" }' f # apply"),
    ("r5-ok-awk-class-alternation", "Bash",
     "W=$S/x; awk '/^[[:space:]]*(apply|destroy)/ { n++ } END { print n }' f"),
    ("r5-ok-awk-division", "Bash", "A=(1); awk '{ print $1 / 2 }' f # apply"),
    ("r5-ok-awk-continuation", "Bash",
     "A=(1); awk '{ print $1, \\\n $2 }' f # apply"),
    ("r5-ok-awk-comment-pipe", "Bash",
     "A=(1); awk '{ n++ } # a | b\nEND { print n }' f # apply"),
    ("r4-a01-awk-print", "Bash", "A=(1); awk '{print $1}' f.txt"),
    ("r4-a02-sed-print", "Bash", "W=$S/x; sed -n '1,5p' f.txt"),
    ("r4-a03-stub-check", "Bash", "W=$S/x; \"$W/stub.sh\" --check"),
    ("r4-a04-command-read-r", "Bash",
     "W=$S/x; command read -r line < f.txt; echo \"$line\""),
    ("r5-ok-cd-relative-no-verb", "Bash",
     "W=$S/x; cd \"$W\" && ./run-tests.sh --fast"),
    # real-25's shape: files written under another literal directory, then
    # a relative program run, with no changing verb, after a `cd` to a
    # literal absolute path, on a line whose heredoc text names terraform.
    ("r5-ok-cd-literal-real-25-shape", "Bash",
     "S=/tmp/sp/k; cat > $S/w.sh <<'EOF'\n#!/usr/bin/env bash\n"
     "# wraps the reviewer; never runs terraform apply\nexec \"$@\"\nEOF\n"
     "chmod +x $S/w.sh\ncd /tmp/sp/wt/k-1; H=$(gh pr view 1 --json headRefOid"
     " -q .headRefOid); W=$S/w.sh tools/review.sh --spec $S/s.md --sha \"$H\""
     " --dry-run 2>&1 | tail -8"),
    ("r5-ok-pushd-literal", "Bash",
     "A=(1); pushd /opt/repo >/dev/null; ./scripts/check.sh plan # apply"),
    ("r5-ok-relative-no-cd", "Bash", "W=$S/x; ./scripts/check.sh plan # apply"),
]


@pytest.mark.parametrize("driver", _R2_DRIVERS)
@pytest.mark.parametrize("case", SRL2308_R5_REFUSE + SRL2308_R5_HELD,
                         ids=[c[0] for c in SRL2308_R5_REFUSE
                              + SRL2308_R5_HELD])
def test_srl2308_r5_a_fallback_line_that_may_run_terraform_is_refused(
        tmp_path, driver, case):
    _block(driver, tmp_path, case + ("terraformApply",))


@pytest.mark.parametrize("driver", _R2_DRIVERS)
@pytest.mark.parametrize("case", SRL2308_R5_ALLOW,
                         ids=[c[0] for c in SRL2308_R5_ALLOW])
def test_srl2308_r5_a_fallback_line_that_cannot_run_terraform_is_allowed(
        tmp_path, driver, case):
    _allow(driver, tmp_path, case)


@pytest.mark.parametrize(("program", "spawns"), [
    ("BEGIN { print \"x\" \\\n | \"sh\" }", True),
    ("BEGIN { \"date\" | getline d }", True),
    ("BEGIN { system(\"date\") }", True),
    ("BEGIN { f = \"system\"; @f(\"date\") }", True),
    ("BEGIN { i++ / 2; print | \"sh\"; j++ / 3 }", True),
    ("/[/]/ { print \"a|b\" }", True),  # not read cleanly, holds a `|`
    ("/[/]/ { print \"a\" }", False),   # not read cleanly, holds none
    ("BEGIN { print \"system(x)\" }", False),
    ("{ print \"a|b\" }", False),
    ("/a|b/ { n++ }", False),
    ("$1 ~ /^[[:alpha:]]+|x/ { n++ }", False),
    ("{ print $1 / 2 }", False),
    ("{ n++ } # x | y\nEND { print n }", False),
    ("{ s = \"a\\\"|b\" }", False),
])
def test_srl2308_r5_awk_code_is_read_without_its_strings(program, spawns):
    """`_awk_spawns` reads awk's code, not its strings, regex constants or
    comments; backslash-newline joins a line; a program it cannot read
    cleanly counts on any `|`, `@` or `system`."""
    found = crew_guards._awk_spawns(program)  # pylint: disable=protected-access
    assert (found is not None) is spawns, (program, found)


@pytest.mark.parametrize("text", [
    "A=(1); echo $(( $(terraform apply) + 1 ))",
    "A=(1); echo ${X:-$(terraform apply)}",
    "A=(1); echo ${X:-`terraform apply`}",
    "A=(1); echo ${X:-${Y:-$(terraform apply)}}",
    "A=(1); echo $(( `terraform apply` + 1 ))",
    "W=$S/x; cat <<EOF\n$(( $(terraform apply) + 1 ))\nEOF",
    "A=(1); cat <<\"'END'\"\n'END'\nterraform apply\nEND",
])
def test_srl2308_r2_the_splitter_gives_up_where_it_cannot_follow(text):
    """r1-2 and r1-3 at the splitter itself: a substitution inside
    `$((...))` or `${...}`, and a delimiter quoted both ways, make it give up
    (`_Unsure`) instead of skipping text bash runs."""
    with pytest.raises(crew_guards._Unsure):  # pylint: disable=protected-access
        crew_guards._CommandSplitter(text).split()  # pylint: disable=protected-access


def test_srl2308_r2_the_precise_reader_gives_up_on_a_mixed_delimiter():
    """r1-3 on the precise path: `<<"'END'"` ends at `'END'` in bash."""
    with pytest.raises(crew_guards._Unsure):  # pylint: disable=protected-access
        crew_guards._GateReader(  # pylint: disable=protected-access
            "cat <<\"'END'\"\n'END'\nterraform apply\nEND", 0, []).read()

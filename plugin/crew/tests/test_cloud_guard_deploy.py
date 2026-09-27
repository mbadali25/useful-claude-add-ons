"""T-0009: environment-scoped workflow dispatches in the cloud guard.

The must-block / must-allow / ask suite for `guards.deployWorkflow`, split out
of `test_cloud_guard_environments.py` when review round 1's rows took that
module past `.pylintrc`'s max-module-lines. It reuses that module's fixture
builder and hook runner (`_run`) rather than growing a second copy. The
mutations live in `sabotage_cloud.py`, each naming the case it must turn red.
"""
import copy
import re

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import crew_guards
import test_cloud_guard as tcg
from test_cloud_guard_environments import (  # pylint: disable=unused-import
    UNATTENDED, _ids, _log_rows, _no_ambient_terraform_env, _run, _sample)

import cloud_guard  # noqa: E402  pylint: disable=wrong-import-position


# --- T-0009: environment-scoped workflow dispatches -------------------------
#
# `gh workflow run <wf>` and its REST twin, `gh api -X POST
# repos/<o>/<r>/actions/workflows/<wf>/dispatches`, become a
# `guards.deployWorkflow` finding when `<wf>` matches a key of the repo-only
# `environments.workflows` map. Both forms are parsed into one dispatch shape
# and judged by ONE classifier (`crew_guards.dispatch_environment`), which is
# what `test_both_dispatch_forms_share_one_classifier` pins.
#
# Base: `deployWorkflow: ask` in both layers, three workflows, unattended.
# Every must-block case is built so that the value a bug collapses to -- an
# absent input read as nonProd, a non-literal read as a literal, an unlisted
# reading of an unknown workflow -- would ALLOW; several carry
# `prodUnattended` in both layers for exactly that reason (a `$ENV` read as
# the literal `$ENV` is production, which `prodUnattended` would allow).

DEPLOY_NONPROD = ["dev", "qa", "staging"]
WORKFLOWS = {"deploy.yml": "input:environment",
             "deploy-staging.yml": "staging",
             "deploy-prod.yml": "production"}
DEPLOY_ENVS = {"nonProd": DEPLOY_NONPROD, "workflows": WORKFLOWS}
DEPLOY_ASK = {"guards": {"deployWorkflow": "ask"}}
DEPLOY_ALLOW = {"guards": {"deployWorkflow": "allow"}}
DISPATCH = "repos/o/r/actions/workflows"


_BASE_ENVS = object()


def _d(policy=None, pu=False, repo_pu=False, environments=_BASE_ENVS, **kw):
    """Opts for one deploy case: `policy` in both layers (default `ask`),
    `pu` = prodUnattended in both layers, `repo_pu` = the repo layer only;
    `environments` defaults to DEPLOY_ENVS, and None removes the block."""
    guards = policy or DEPLOY_ASK
    if environments is _BASE_ENVS:
        environments = DEPLOY_ENVS
    envs = None if environments is None else dict(environments)
    if envs is not None and (pu or repo_pu):
        envs["prodUnattended"] = True
    glob = copy.deepcopy(guards)
    if pu:
        glob["environments"] = {"prodUnattended": True}
    return dict(kw, repo=copy.deepcopy(guards), **{"global": glob},
                environments=envs)


MUST_BLOCK_DEPLOY = [
    ("prod-input", "Bash", "gh workflow run deploy.yml -f environment=production",
     _d(why="production")),
    ("prod-fixed", "Bash", "gh workflow run deploy-prod.yml",
     _d(why="production")),
    ("prod-repo-only-unattended", "Bash",
     "gh workflow run deploy.yml -f environment=production",
     _d(repo_pu=True, why="production")),
    ("no-input", "Bash", "gh workflow run deploy.yml", _d(pu=True, why="unknown")),
    ("field-at-file", "Bash", "gh workflow run deploy.yml -F environment=@env.txt",
     _d(pu=True, why="unknown")),
    ("variable-input", "Bash", "gh workflow run deploy.yml -f environment=$ENV",
     _d(pu=True, why="unknown")),
    ("conflicting-fields", "Bash",
     "gh workflow run deploy.yml -f environment=staging -f environment=production",
     _d(pu=True, why="unknown")),
    ("json-non-literal", "Bash", "cat in.json | gh workflow run deploy.yml --json",
     _d(pu=True, why="unknown")),
    ("json-missing-input", "Bash",
     "echo '{\"region\":\"eu\"}' | gh workflow run deploy.yml --json",
     _d(pu=True, why="unknown")),
    ("no-workflow-arg", "Bash", "gh workflow run", _d(pu=True, why="unknown")),
    ("non-literal-workflow", "Bash",
     'gh workflow run "$WF" -f environment=staging', _d(pu=True, why="unknown")),
    ("block-not-loosened", "Bash",
     "gh workflow run deploy.yml -f environment=staging",
     _d(policy={"guards": {"deployWorkflow": "block"}}, why="block")),
    ("powershell-prod", "PowerShell",
     "gh workflow run deploy.yml -f environment=production", _d(why="production")),
    ("bash-c-prod", "Bash",
     "bash -c 'gh workflow run deploy.yml -f environment=production'",
     _d(why="production")),
    ("raw-field-long-prod", "Bash",
     "gh workflow run deploy.yml --raw-field environment=production",
     _d(why="production")),
    ("field-short-prod", "Bash",
     "gh workflow run deploy.yml -F environment=production", _d(why="production")),
    ("xargs-workflow", "Bash",
     "echo deploy.yml | xargs gh workflow run -f environment=staging",
     _d(pu=True, why="unknown")),
    ("xargs-placeholder-workflow", "Bash",
     "echo deploy.yml | xargs -I WF gh workflow run WF -f environment=staging",
     _d(pu=True, why="unknown")),
    ("xargs-subcommand", "Bash", "echo workflow run deploy.yml | xargs gh",
     _d(pu=True, why="unknown")),
    # Step 5: the REST form, judged by the same classifier.
    ("api-prod-input", "Bash",
     f"gh api -X POST {DISPATCH}/deploy.yml/dispatches -f ref=main "
     "-f 'inputs[environment]=production'", _d(why="production")),
    ("api-method-flag", "Bash",
     f"gh api --method POST {DISPATCH}/deploy.yml/dispatches -f ref=main "
     "-f 'inputs[environment]=production'", _d(why="production")),
    ("api-method-eq", "Bash",
     f"gh api --method=post {DISPATCH}/deploy.yml/dispatches "
     "-f 'inputs[environment]=production'", _d(why="production")),
    ("api-xpost-attached", "Bash",
     f"gh api -XPOST {DISPATCH}/deploy.yml/dispatches "
     "-f 'inputs[environment]=production'", _d(why="production")),
    ("api-implied-post", "Bash",
     f"gh api {DISPATCH}/deploy.yml/dispatches -f ref=main "
     "-f 'inputs[environment]=production'", _d(why="production")),
    ("api-input-file", "Bash",
     f"gh api -X POST {DISPATCH}/deploy.yml/dispatches --input body.json",
     _d(pu=True, why="unknown")),
    ("api-input-implied-post", "Bash",
     f"gh api {DISPATCH}/deploy.yml/dispatches --input body.json",
     _d(pu=True, why="unknown")),
    ("api-variable-input", "Bash",
     f"gh api -X POST {DISPATCH}/deploy.yml/dispatches -f ref=main "
     '-f "inputs[environment]=$ENV"', _d(pu=True, why="unknown")),
    ("api-leading-slash", "Bash",
     f"gh api -X POST /{DISPATCH}/deploy.yml/dispatches -f ref=main "
     "-f 'inputs[environment]=production'", _d(why="production")),
    ("api-fixed-prod", "Bash",
     f"gh api -X POST {DISPATCH}/deploy-prod.yml/dispatches -f ref=main",
     _d(why="production")),
    # The top-level `ref` is the branch the workflow file is read from, never
    # an input: read as one it would be `staging`, and allowed.
    ("api-ref-not-input", "Bash",
     f"gh api -X POST {DISPATCH}/deploy.yml/dispatches -f ref=staging",
     _d(pu=True, why="unknown")),
    ("api-field-at-file", "Bash",
     f"gh api -X POST {DISPATCH}/deploy.yml/dispatches "
     "-F 'inputs[environment]=@env.txt'", _d(pu=True, why="unknown")),
    ("api-non-literal-workflow", "Bash",
     f"gh api -X POST {DISPATCH}/$WF/dispatches "
     "-f 'inputs[environment]=staging'", _d(pu=True, why="unknown")),
    ("api-powershell-prod", "PowerShell",
     f"gh api -X POST {DISPATCH}/deploy.yml/dispatches -f ref=main "
     "-f 'inputs[environment]=production'", _d(why="production")),
    # Step 6: `allow` covers nonProd only; a malformed block is unknown.
    ("allow-prod-unattended", "Bash",
     "gh workflow run deploy.yml -f environment=production",
     _d(policy=DEPLOY_ALLOW, why="production")),
    ("allow-unknown-unattended", "Bash",
     "gh workflow run deploy.yml -f environment=$ENV",
     _d(policy=DEPLOY_ALLOW, why="unknown")),
    ("malformed-environments", "Bash",
     "gh workflow run deploy.yml -f environment=staging",
     _d(environments={"workflows": 1}, why="unknown")),
    ("malformed-environments-unlisted", "Bash", "gh workflow run ci.yml",
     _d(environments={"nonProd": "staging",
                      "workflows": {"deploy.yml": "staging"}}, why="unknown")),
]

# `log` is the guard.log policy the allow is recorded under; None means the
# dispatch is unclassified -- no deployWorkflow row at all.
MUST_ALLOW_DEPLOY = [
    ("staging-raw-field", "Bash", "gh workflow run deploy.yml -f environment=staging",
     _d(log="env:nonProd:staging")),
    ("staging-field-eq", "Bash",
     "gh workflow run deploy.yml --field=environment=staging",
     _d(log="env:nonProd:staging")),
    ("staging-short-attached", "Bash",
     "gh workflow run deploy.yml -fenvironment=staging",
     _d(log="env:nonProd:staging")),
    ("staging-twice", "Bash",
     "gh workflow run deploy.yml -f environment=staging -f environment=staging",
     _d(log="env:nonProd:staging")),
    ("staging-json-heredoc", "Bash",
     "gh workflow run deploy.yml --json <<'EOF'\n"
     '{"environment": "staging"}\nEOF', _d(log="env:nonProd:staging")),
    ("staging-json-echo", "Bash",
     "echo '{\"environment\":\"staging\"}' | gh workflow run deploy.yml --json",
     _d(log="env:nonProd:staging")),
    ("staging-fixed", "Bash", "gh workflow run deploy-staging.yml",
     _d(log="env:nonProd:staging")),
    ("prod-unattended-both-layers", "Bash",
     "gh workflow run deploy.yml -f environment=production",
     _d(pu=True, log="env:prod-unattended:production", said="production")),
    ("unlisted-workflow", "Bash", "gh workflow run ci.yml", _d(log=None)),
    ("defaults-nothing-classified", "Bash",
     "gh workflow run deploy.yml -f environment=production",
     _d(environments=None, log=None)),
    ("ref-and-repo-flags", "Bash",
     "gh workflow run -R org/app -r main deploy.yml -f environment=qa",
     _d(log="env:nonProd:qa")),
    ("other-gh-commands", "Bash",
     "gh workflow list && gh workflow view deploy.yml && gh run rerun 12 "
     "&& gh pr view 3", _d(log=None)),
    ("api-staging-input", "Bash",
     f"gh api -X POST {DISPATCH}/deploy.yml/dispatches -f ref=main "
     "-f 'inputs[environment]=staging'", _d(log="env:nonProd:staging")),
    ("api-json-stdin", "Bash",
     "echo '{\"ref\":\"main\",\"inputs\":{\"environment\":\"staging\"}}' | "
     f"gh api -X POST {DISPATCH}/deploy.yml/dispatches --input -",
     _d(log="env:nonProd:staging")),
    ("api-get-same-path", "Bash", f"gh api {DISPATCH}/deploy.yml", _d(log=None)),
    ("api-get-dispatches", "Bash",
     f"gh api -X GET {DISPATCH}/deploy.yml/dispatches "
     "-f 'inputs[environment]=production'", _d(log=None)),
    ("api-post-other-path", "Bash", "gh api -X POST repos/o/r/issues -f title=x",
     _d(log=None)),
    ("api-unlisted-workflow", "Bash",
     f"gh api -X POST {DISPATCH}/ci.yml/dispatches -f ref=main", _d(log=None)),
    ("allow-nonprod-unattended", "Bash",
     "gh workflow run deploy.yml -f environment=staging",
     _d(policy=DEPLOY_ALLOW, log="env:nonProd:staging")),
]

ASK_DEPLOY = [
    ("ask-prod-input", "Bash",
     "gh workflow run deploy.yml -f environment=production", _d()),
    ("ask-no-input", "Bash", "gh workflow run deploy.yml", _d()),
    ("ask-api-prod-input", "Bash",
     f"gh api -X POST {DISPATCH}/deploy.yml/dispatches "
     "-f 'inputs[environment]=production'", _d()),
    ("allow-prod-attended", "Bash",
     "gh workflow run deploy.yml -f environment=production",
     _d(policy=DEPLOY_ALLOW)),
    ("allow-unknown-attended", "Bash",
     "gh workflow run deploy.yml -f environment=$ENV", _d(policy=DEPLOY_ALLOW)),
]

# --- T-0009 review round 1: stdin, variables, gh flags, display names -------
#
# Each finding's exact repro from round 1's out.txt comes first (`r1-...`),
# then its neighbours. Measured before the fix: every R1_MUST_BLOCK row was
# allowed unattended (or, for `-iX POST`, not judged at all), and the two
# display-name must-allow rows were denied.
J_STAGING = "echo '{\"environment\":\"staging\"}'"
J_PROD = "echo '{\"environment\":\"production\"}'"
RUN_JSON = "gh workflow run deploy.yml --json"
API_PROD = (f"{DISPATCH}/deploy.yml/dispatches -f ref=main "
            "-f 'inputs[environment]=production'")
NAMED = dict(WORKFLOWS, **{"Deploy Staging": "staging",
                           "Deploy Prod": "production"})
NAMED_ENVS = {"nonProd": DEPLOY_NONPROD, "workflows": NAMED}

R1_MUST_BLOCK_DEPLOY = [
    # BLOCK 1: a filter between a literal source and gh rewrites stdin.
    ("r1-stdin-sed", "Bash",
     f"{J_STAGING} | sed s/staging/production/ | {RUN_JSON}",
     _d(pu=True, why="unknown")),
    ("stdin-tr", "Bash", f"{J_STAGING} | tr a-z a-z | {RUN_JSON}",
     _d(pu=True, why="unknown")),
    ("stdin-jq", "Bash", f"{J_STAGING} | jq -c . | {RUN_JSON}",
     _d(pu=True, why="unknown")),
    ("stdin-awk", "Bash", f"{J_STAGING} | awk '{{print}}' | {RUN_JSON}",
     _d(pu=True, why="unknown")),
    ("stdin-perl", "Bash", f"{J_STAGING} | perl -pe 1 | {RUN_JSON}",
     _d(pu=True, why="unknown")),
    ("stdin-python", "Bash",
     f"{J_STAGING} | python3 -c 'import sys; print(sys.stdin.read())' | "
     f"{RUN_JSON}", _d(pu=True, why="unknown")),
    ("stdin-subshell", "Bash", f"({J_STAGING}; true) | {RUN_JSON}",
     _d(pu=True, why="unknown")),
    ("stdin-group", "Bash", f"{{ {J_STAGING}; }} | {RUN_JSON}",
     _d(pu=True, why="unknown")),
    ("stdin-tee-procsub", "Bash",
     f"{J_STAGING} | tee >(sed s/staging/production/) | {RUN_JSON}",
     _d(pu=True, why="unknown")),
    ("stdin-cat-procsub", "Bash", f"cat <({J_STAGING}) | {RUN_JSON}",
     _d(pu=True, why="unknown")),
    ("stdin-echo-escape", "Bash",
     "echo -e '{\"environment\":\"sta\\x67ing\"}' | " + RUN_JSON,
     _d(pu=True, why="unknown")),
    ("stdin-xargs", "Bash", f"{J_STAGING} | xargs -0 {RUN_JSON}",
     _d(pu=True, why="unknown")),
    ("stdin-sed-then-cat", "Bash",
     f"{J_STAGING} | sed s/staging/production/ | cat | {RUN_JSON}",
     _d(pu=True, why="unknown")),
    ("stdin-printf-escape", "Bash",
     "printf '{\"environment\":\"sta\\u0067ing\"}' | " + RUN_JSON,
     _d(pu=True, why="unknown")),
    ("api-stdin-sed", "Bash",
     "echo '{\"ref\":\"main\",\"inputs\":{\"environment\":\"staging\"}}' | "
     f"sed s/staging/production/ | gh api -X POST {DISPATCH}/deploy.yml/"
     "dispatches --input -", _d(pu=True, why="unknown")),
    # BLOCK 2: a redirect on the gh command replaces the piped literal.
    ("r1-stdin-redirect", "Bash", f"{J_STAGING} | {RUN_JSON} < prod.json",
     _d(pu=True, why="unknown")),
    ("stdin-redirect-no-pipe", "Bash", f"{RUN_JSON} < staging.json",
     _d(pu=True, why="unknown")),
    ("stdin-redirect-procsub", "Bash", f"{RUN_JSON} < <({J_STAGING})",
     _d(pu=True, why="unknown")),
    ("stdin-redirect-fd0", "Bash", f"{J_STAGING} | {RUN_JSON} 0< prod.json",
     _d(pu=True, why="unknown")),
    ("stdin-dup-fd", "Bash", f"{J_STAGING} | {RUN_JSON} <&3",
     _d(pu=True, why="unknown")),
    ("stdin-herestring-wins", "Bash",
     f"{J_STAGING} | {RUN_JSON} <<< '{{\"environment\":\"production\"}}'",
     _d(why="production")),
    ("stdin-heredoc-wins", "Bash",
     f"{J_STAGING} | {RUN_JSON} <<'EOF'\n"
     '{"environment": "production"}\nEOF', _d(why="production")),
    ("stdin-other-fd-herestring", "Bash",
     f"{J_PROD} | {RUN_JSON} 3<<< '{{\"environment\":\"staging\"}}'",
     _d(pu=True, why="unknown")),
    ("stdin-herestring-then-file", "Bash",
     f"{RUN_JSON} <<< '{{\"environment\":\"staging\"}}' < prod.json",
     _d(pu=True, why="unknown")),
    # BLOCK 3: a variable is never resolved from an earlier assignment.
    ("r1-variable-case", "Bash",
     "ENV=production; env=staging; "
     "gh workflow run deploy.yml -f environment=$ENV",
     _d(pu=True, why="unknown")),
    ("r1-variable-read", "Bash",
     "ENV=staging; read ENV < prod.txt; "
     "gh workflow run deploy.yml -f environment=$ENV",
     _d(pu=True, why="unknown")),
    ("variable-braced", "Bash",
     "ENV=staging; gh workflow run deploy.yml -f environment=${ENV}",
     _d(pu=True, why="unknown")),
    ("variable-export", "Bash",
     "export ENV=staging; gh workflow run deploy.yml -f environment=$ENV",
     _d(pu=True, why="unknown")),
    ("variable-source", "Bash",
     "ENV=staging; source ./env.sh; "
     "gh workflow run deploy.yml -f environment=$ENV",
     _d(pu=True, why="unknown")),
    ("variable-cmd-subst", "Bash",
     "gh workflow run deploy.yml -f environment=$(echo staging)",
     _d(pu=True, why="unknown")),
    ("variable-backtick", "Bash",
     "gh workflow run deploy.yml -f environment=`echo staging`",
     _d(pu=True, why="unknown")),
    ("variable-workflow-case", "Bash",
     "WF=deploy.yml; wf=ci.yml; gh workflow run $WF -f environment=production",
     _d(why="unknown")),
    ("variable-head", "Bash",
     "GH=gh; $GH workflow run deploy.yml -f environment=staging",
     _d(pu=True, why="unknown")),
    ("variable-api-endpoint", "Bash",
     f"EP={DISPATCH}/deploy.yml/dispatches; ep=repos/o/r/issues; "
     "gh api -X POST $EP -f 'inputs[environment]=production'",
     _d(why="unknown")),
    ("variable-api-field", "Bash",
     "ENV=staging; gh api -X POST "
     f"{DISPATCH}/deploy.yml/dispatches -f \"inputs[environment]=$ENV\"",
     _d(pu=True, why="unknown")),
    ("variable-eval", "Bash",
     "ENV=staging; eval \"gh workflow run deploy.yml -f environment=$ENV\"",
     _d(pu=True, why="unknown")),
    ("variable-bash-c", "Bash",
     "ENV=staging; bash -c \"gh workflow run deploy.yml -f environment=$ENV\"",
     _d(pu=True, why="unknown")),
    ("variable-herestring", "Bash",
     "ENV=staging; " + RUN_JSON + " <<< \"{\\\"environment\\\":\\\"$ENV\\\"}\"",
     _d(pu=True, why="unknown")),
    # An unquoted expansion anywhere in the line can split into more flags
    # (`-f a=$Y`, Y='x -f environment=production'), and a glob can match a
    # file named like one; the lexer cannot tell quoted from unquoted.
    ("variable-other-field-splits", "Bash",
     "gh workflow run deploy.yml -f environment=staging -f note=$Y",
     _d(pu=True, why="unknown")),
    ("variable-unrelated-ref", "Bash",
     "BRANCH=main; gh workflow run deploy.yml -r $BRANCH "
     "-f environment=staging", _d(pu=True, why="unknown")),
    ("glob-argument", "Bash",
     "gh workflow run deploy.yml -f environment=staging *",
     _d(pu=True, why="unknown")),
    ("brace-argument", "Bash",
     "gh workflow run deploy.yml -f environment=staging "
     "{-f,environment=production}", _d(pu=True, why="unknown")),
    ("api-other-field-splits", "Bash",
     f"gh api -X POST {DISPATCH}/deploy.yml/dispatches "
     "-f 'inputs[environment]=staging' -f ref=$REF", _d(pu=True, why="unknown")),
    # A body carrying an expansion or an escape: an unquoted heredoc expands
    # `$Y` into another key (`","environment":"production`), and bash strips
    # a backslash before `$`, `` ` `` and `\`.
    ("stdin-heredoc-expansion", "Bash",
     RUN_JSON + " <<EOF\n{\"environment\": \"staging\", \"a\": \"$Y\"}\nEOF",
     _d(pu=True, why="unknown")),
    ("stdin-heredoc-backslash", "Bash",
     RUN_JSON + " <<EOF\n{\"environment\": \"stag\\\\u0069ng\"}\nEOF",
     _d(pu=True, why="unknown")),
    ("stdin-herestring-backtick", "Bash",
     RUN_JSON + " <<< \"{\\\"environment\\\":\\\"staging\\\",\\\"a\\\":\\\"`id`\\\"}\"",
     _d(pu=True, why="unknown")),
    ("variable-tilde", "Bash",
     "gh workflow run deploy.yml -f environment=~staging",
     _d(pu=True, why="unknown")),
    ("variable-powershell", "PowerShell",
     "$ENV = 'staging'; gh workflow run deploy.yml -f environment=$ENV",
     _d(pu=True, why="unknown")),
    # BLOCK 4: gh's own flag parser, clustered short flags included.
    ("r1-api-cluster-iX", "Bash", f"gh api -iX POST {API_PROD}",
     _d(why="production")),
    ("api-cluster-attached", "Bash", f"gh api -iXPOST {API_PROD}",
     _d(why="production")),
    ("api-short-eq", "Bash", f"gh api -X=POST {API_PROD}",
     _d(why="production")),
    ("api-cluster-eq", "Bash", f"gh api -iX=POST {API_PROD}",
     _d(why="production")),
    ("api-cluster-lower", "Bash", f"gh api -iXpost {API_PROD}",
     _d(why="production")),
    ("api-bool-then-x", "Bash", f"gh api -i -X POST {API_PROD}",
     _d(why="production")),
    ("api-endpoint-last", "Bash",
     "gh api -f ref=main -f 'inputs[environment]=production' -X POST "
     f"{DISPATCH}/deploy.yml/dispatches", _d(why="production")),
    ("api-paginate-first", "Bash", f"gh api --paginate -X POST {API_PROD}",
     _d(why="production")),
    ("api-cluster-field", "Bash",
     f"gh api -X POST {DISPATCH}/deploy.yml/dispatches "
     "-if 'inputs[environment]=production'", _d(why="production")),
    ("run-cluster-field", "Bash",
     "gh workflow run deploy.yml -fenvironment=production",
     _d(why="production")),
    # FIX: a quoted display name is matched literally.
    ("display-name-prod", "Bash", "gh workflow run 'Deploy Prod'",
     _d(environments=NAMED_ENVS, why="production")),
    ("display-name-glob", "Bash", "gh workflow run 'Deploy *'",
     _d(environments=NAMED_ENVS, pu=True, why="unknown")),
]

R1_MUST_ALLOW_DEPLOY = [
    ("r1-display-name-unlisted", "Bash", "gh workflow run 'CI Checks'",
     _d(log=None)),
    ("r1-display-name-listed", "Bash", "gh workflow run 'Deploy Staging'",
     _d(environments=NAMED_ENVS, log="env:nonProd:staging")),
    ("display-name-powershell", "PowerShell",
     "gh workflow run 'Deploy Staging'",
     _d(environments=NAMED_ENVS, log="env:nonProd:staging")),
    ("stdin-herestring-over-pipe", "Bash",
     f"{J_PROD} | {RUN_JSON} <<< '{{\"environment\":\"staging\"}}'",
     _d(log="env:nonProd:staging")),
    ("stdin-cat-passthrough", "Bash", f"{J_STAGING} | cat | {RUN_JSON}",
     _d(log="env:nonProd:staging")),
    ("stdin-printf", "Bash",
     "printf '%s' '{\"environment\":\"staging\"}' | " + RUN_JSON,
     _d(log="env:nonProd:staging")),
    ("stdin-echo-n", "Bash",
     "echo -n '{\"environment\":\"staging\"}' | " + RUN_JSON,
     _d(log="env:nonProd:staging")),
    ("api-cluster-get", "Bash",
     f"gh api -iX GET {DISPATCH}/deploy.yml/dispatches "
     "-f 'inputs[environment]=production'", _d(log=None)),
    ("api-owner-placeholder", "Bash",
     "gh api -X POST repos/{owner}/{repo}/actions/workflows/deploy.yml/"
     "dispatches -f 'inputs[environment]=staging'",
     _d(log="env:nonProd:staging")),
]

R1_ASK_DEPLOY = [
    ("ask-stdin-sed", "Bash",
     f"{J_STAGING} | sed s/staging/production/ | {RUN_JSON}", _d()),
    ("ask-variable-case", "Bash",
     "ENV=production; env=staging; "
     "gh workflow run deploy.yml -f environment=$ENV", _d()),
]

MUST_BLOCK_DEPLOY += R1_MUST_BLOCK_DEPLOY
MUST_ALLOW_DEPLOY += R1_MUST_ALLOW_DEPLOY
ASK_DEPLOY += R1_ASK_DEPLOY

_DB_SAMPLE = ("prod-input", "powershell-prod", "api-prod-input",
              "api-powershell-prod")
_DA_SAMPLE = ("staging-raw-field", "prod-unattended-both-layers",
              "api-staging-input")


def _deploy_deny(driver, tmp_path, case):
    _id, tool, _command, opts = case
    _repo, result = _run(driver, tmp_path, case)
    if tcg._stood_down(driver, tool, result):  # pylint: disable=protected-access
        return
    decision, reason, code, err = result
    assert code == 0, err
    assert decision == "deny", (case[0], decision, reason, err)
    assert "[deployWorkflow]" in reason, reason
    assert opts["why"] in reason, (opts["why"], reason)


def _deploy_allow(driver, tmp_path, case):
    _id, tool, _command, opts = case
    repo, result = _run(driver, tmp_path, case)
    if tcg._stood_down(driver, tool, result):  # pylint: disable=protected-access
        return
    decision, said, code, err = result
    assert code == 0, err
    assert decision == "allow", (case[0], said, err)
    rows = [r for r in _log_rows(repo) if r[1] == "deployWorkflow"]
    if opts["log"] is None:
        assert not rows, rows
    else:
        assert rows, "an allow must leave a guard.log row"
        assert all(r[3] == "allow" for r in rows), rows
        assert any(r[2] == opts["log"] for r in rows), (opts["log"], rows)
    if opts.get("said"):
        assert opts["said"] in said, said
    else:
        assert not said, said


@pytest.mark.parametrize("case", MUST_BLOCK_DEPLOY, ids=_ids(MUST_BLOCK_DEPLOY))
def test_must_block_deploy_python(tmp_path, case):
    _deploy_deny("python", tmp_path, case)


@pytest.mark.parametrize("case", _sample(MUST_BLOCK_DEPLOY, _DB_SAMPLE,
                                         (tcg.needs_bash,)))
def test_must_block_deploy_bash(tmp_path, case):
    _deploy_deny("bash", tmp_path, case)


@pytest.mark.parametrize("case", _sample(MUST_BLOCK_DEPLOY, _DB_SAMPLE,
                                         (tcg.needs_pwsh,)))
def test_must_block_deploy_pwsh(tmp_path, case):
    _deploy_deny("pwsh", tmp_path, case)


@pytest.mark.parametrize("case", MUST_ALLOW_DEPLOY, ids=_ids(MUST_ALLOW_DEPLOY))
def test_must_allow_deploy_python(tmp_path, case):
    _deploy_allow("python", tmp_path, case)


@pytest.mark.parametrize("case", _sample(MUST_ALLOW_DEPLOY, _DA_SAMPLE,
                                         (tcg.needs_bash,)))
def test_must_allow_deploy_bash(tmp_path, case):
    _deploy_allow("bash", tmp_path, case)


@pytest.mark.parametrize("case", _sample(MUST_ALLOW_DEPLOY, _DA_SAMPLE,
                                         (tcg.needs_pwsh,)))
def test_must_allow_deploy_pwsh(tmp_path, case):
    _deploy_allow("pwsh", tmp_path, case)


@pytest.mark.parametrize("case", ASK_DEPLOY, ids=_ids(ASK_DEPLOY))
def test_ask_deploy_python(tmp_path, case):
    _id, _tool, _command, _opts = case
    _repo, result = _run("python", tmp_path, case, env={})
    decision, reason, code, err = result
    assert code == 0, err
    assert decision == "ask", (case[0], decision, reason, err)
    assert "[deployWorkflow]" in reason, reason


def test_deploy_tables_are_distinct_and_complete():
    ids = _ids(MUST_BLOCK_DEPLOY + MUST_ALLOW_DEPLOY + ASK_DEPLOY)
    assert len(ids) == len(set(ids))
    assert all(c[3].get("why") for c in MUST_BLOCK_DEPLOY)
    assert all("log" in c[3] for c in MUST_ALLOW_DEPLOY)


def _dispatch_scopes(command, shell="bash"):
    return [f.scope for f in cloud_guard.scan(shell, command, ctx={})
            if f.rule == "deployWorkflow"]


def test_both_dispatch_forms_share_one_classifier(monkeypatch):
    """Step 5: the REST form is not a copy of the `gh workflow run` path.
    Both parse into the same dispatch shape, and `_judge_one` hands either to
    the one `crew_guards.dispatch_environment`; stubbing that function changes both."""
    run = _dispatch_scopes("gh workflow run deploy.yml -f environment=qa")
    api = _dispatch_scopes(f"gh api -X POST {DISPATCH}/deploy.yml/dispatches "
                           "-f ref=main -f 'inputs[environment]=qa'")
    assert len(run) == len(api) == 1
    assert run[0]["workflow"] == api[0]["workflow"] == "deploy.yml"
    assert run[0]["inputs"] == api[0]["inputs"] == [("environment", "qa", "")]
    envs = {"nonProd": ["qa"], "prodUnattended": False, "problem": "",
            "workflows": {"deploy.yml": "input:environment"}}
    assert crew_guards.dispatch_environment(run[0], envs) == \
        crew_guards.dispatch_environment(api[0], envs)
    seen = []
    monkeypatch.setattr(crew_guards, "dispatch_environment",
                        lambda scope, envs: seen.append(scope["form"]))
    for scope in run + api:
        finding = cloud_guard.Finding("deployWorkflow", "x", "x", None, True,
                                      None, scope)
        cloud_guard._judge_one("/nonexistent", finding, {}, "", envs)  # pylint: disable=protected-access
    assert seen == ["workflow run", "api"]


def test_workflows_alone_do_not_engage_the_environment_layer(tmp_path):
    """Step 6: `environments.workflows` does not count toward `engaged`, so a
    repo that lists workflows and nothing else keeps T-0005's pre-layer
    behaviour for `terraform workspace new` -- not judged."""
    case = ("workflows-only-not-engaged", "Bash", "terraform workspace new dev",
            _d(environments={"workflows": WORKFLOWS}))
    repo, result = _run("python", tmp_path, case)
    decision, said, code, err = result
    assert code == 0, err
    assert decision == "allow", (said, err)
    assert not [r for r in _log_rows(repo) if r[1] == "terraformApply"]
    envs = cloud_guard.environments_config(str(repo))
    assert envs["engaged"] is False
    assert envs["workflows"] == WORKFLOWS


def test_a_malformed_block_reads_every_dispatch_as_unknown(tmp_path):
    repo = tcg._fixture(tmp_path, {"environments": {"workflows": 1}})  # pylint: disable=protected-access
    envs = cloud_guard.environments_config(str(repo))
    assert envs["problem"] and envs["workflows"] == {}
    for command in ("gh workflow run ci.yml", "gh workflow run",
                    f"gh api -X POST {DISPATCH}/ci.yml/dispatches"):
        (scope,) = _dispatch_scopes(command)
        klass, _value, why, _key = crew_guards.dispatch_environment(scope, envs)
        assert klass == cloud_guard.ENV_UNKNOWN and "environments" in why, \
            (command, why)


def _deny_marker(reason):
    match = re.search(r"create (\S+) and re-run", reason)
    assert match, reason
    return match.group(1)


@pytest.mark.parametrize("first,second", [
    # BLOCK 5 repro: the same argv, only the stdin JSON's environment changed.
    ("echo '{\"environment\":\"production-one\"}' | " + RUN_JSON,
     "echo '{\"environment\":\"production-two\"}' | " + RUN_JSON),
    # The same argv with different stdin, heredoc form.
    (RUN_JSON + " <<'EOF'\n{\"environment\": \"production-one\"}\nEOF",
     RUN_JSON + " <<'EOF'\n{\"environment\": \"production-two\"}\nEOF"),
    # The REST body on stdin.
    ("echo '{\"ref\":\"main\",\"inputs\":{\"environment\":\"production-one\"}}'"
     f" | gh api -X POST {DISPATCH}/deploy.yml/dispatches --input -",
     "echo '{\"ref\":\"main\",\"inputs\":{\"environment\":\"production-two\"}}'"
     f" | gh api -X POST {DISPATCH}/deploy.yml/dispatches --input -"),
])
def test_r1_an_approval_covers_one_deployment_only(tmp_path, first, second):
    """Round 1 BLOCK 5: the marker is keyed on the argv AND the inputs judged
    (stdin, the environment value), so approving production-one never lets
    production-two run."""
    case = ("r1-marker", "Bash", first, _d(why="production"))
    repo, result = _run("python", tmp_path, case)
    decision, reason, code, err = result
    assert code == 0 and decision == "deny", (reason, err)
    marker = _deny_marker(reason)
    open(marker, "w", encoding="utf-8").close()  # pylint: disable=consider-using-with
    result = tcg.run_hook("python", tmp_path, "Bash", first,
                          extra_env=dict(UNATTENDED))
    assert result[0] == "allow", result
    result = tcg.run_hook("python", tmp_path, "Bash", second,
                          extra_env=dict(UNATTENDED))
    assert result[0] == "deny", result
    assert _deny_marker(result[1]) != marker
    assert (repo / ".crew").is_dir()


def test_r1_unknown_paths_block_under_block():
    """Could-not-tell is never permission: every round-1 unknown row is denied
    under `deployWorkflow: block` too (the scan finds a dispatch at all)."""
    for _id, tool, command, opts in R1_MUST_BLOCK_DEPLOY:
        shell = "powershell" if tool == "PowerShell" else "bash"
        if opts["why"] != "unknown":
            continue
        assert _dispatch_scopes(command, shell), _id


def test_r1_tables_are_distinct():
    ids = _ids(MUST_BLOCK_DEPLOY + MUST_ALLOW_DEPLOY + ASK_DEPLOY)
    assert len(ids) == len(set(ids))

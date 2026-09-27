"""T-0009: environment-scoped workflow dispatches in the cloud guard.

The must-block / must-allow / ask suite for `guards.deployWorkflow`, split out
of `test_cloud_guard_environments.py` when review round 1's rows took that
module past `.pylintrc`'s max-module-lines. It reuses that module's fixture
builder and hook runner (`_run`) rather than growing a second copy. The
mutations live in `sabotage_cloud.py`, each naming the case it must turn red.

THE DISPATCH GRAMMAR (successor plan, 2026-09-27). Every new row below was
run against the code at `b979d640` (round 2's head) before the grammar was
built, through the real hook, one process per case. What each got there:

  allowed unattended (RED): r2-bracket-glob, r2-fd-dup-0-from-3, r2-sed-bash,
    r2-fd-dup-0-alone, r2-fd-dup-1-from-3, r2-fd-dup-in-from-3, r2-bracket-quoted-positional,
    r2-inputs-unquoted, r2-bash-c-literal, r2-echo-bash, g-double-quotes,
    g-ansi-c, g-backslash, g-redirect-in, g-heredoc, g-herestring, g-dup-in,
    g-readwrite, g-clobber, g-procsub-in, g-procsub-out, g-pipe-in, g-pipe-out,
    g-json, g-input-dash, g-input-file, g-field-at-file, g-field-at-stdin,
    g-eval, g-sh-heredoc, g-alias-on-line, g-cp-on-line, g-cp-literal,
    g-parallel, g-owner-placeholder-unquoted, g-single-quote-inside,
    g-double-quotes-elsewhere, g-ansi-c-elsewhere,
    g-single-quote-inside-elsewhere,
    g-double-positional, g-find-exec, g-hole-command-env, g-ps-dot-source; and g-ask-could-not-tell (attended: no
    ask at all)
  denied, but as an environment or `unknown`, never "could not tell" (RED on
    the reason): g-var, g-braced-var, g-cmd-subst, g-backquote,
    g-brace-expansion, g-tilde, g-star, g-question, g-xargs, g-hole-command,
    g-xargs-placeholder-subcommand, g-control-char, g-cr-in-word; g-ask-help-nonliteral asked the same way
  denied as unknown where gh prints help (RED): g-help-standalone,
    g-help-short, g-help-first
  RED as functions: test_r2_a_marker_covers_exact_bytes_only (the marker for
    `< prod-one.json` allowed `< prod-two.json`),
    test_a_could_not_tell_marker_allows_that_text,
    test_dispatch_answer_is_the_only_road, test_dispatch_answer_contract (no
    `dispatch_answer`), test_dispatch_gate_refuses_a_disagreement
  already GREEN, kept as regression rows: g-block-literal-nonprod, every
    g- must-allow row but the three help rows, g-ask-prod,
    g-ask-unknown-no-input, g-ask-help-value, g-ask-dashdash-help,
    test_marker_does_not_survive_a_remap

Retabled by the grammar (old id kept, reason now "could not tell"): the
eight rows in `MOVED_MUST_BLOCK` left the must-allow tables, and every
round-1 stdin, variable, glob and xargs row, `bash-c-prod`, the `-F @file`
and `--input FILE` rows and both malformed-block rows kept their place with
the new reason. `powershell-prod` keeps "production": a literal PowerShell
line is judged (the plan's Step 2 listed it as could-not-tell; the spec's
must-allow table, which has `& gh ...` judged, decides). No row was
re-spelled: the display-name rows were single-quoted already.
"""
import copy
import inspect
import json
import re

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import crew_config
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
# The phrase every could-not-tell reason carries (THE DISPATCH GRAMMAR, in
# `crew_guards`) and no other dispatch reason does.
CNT = "could not tell"


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
     _d(pu=True, why=CNT)),
    ("variable-input", "Bash", "gh workflow run deploy.yml -f environment=$ENV",
     _d(pu=True, why=CNT)),
    ("conflicting-fields", "Bash",
     "gh workflow run deploy.yml -f environment=staging -f environment=production",
     _d(pu=True, why="unknown")),
    ("json-non-literal", "Bash", "cat in.json | gh workflow run deploy.yml --json",
     _d(pu=True, why=CNT)),
    ("json-missing-input", "Bash",
     "echo '{\"region\":\"eu\"}' | gh workflow run deploy.yml --json",
     _d(pu=True, why=CNT)),
    ("no-workflow-arg", "Bash", "gh workflow run", _d(pu=True, why="unknown")),
    ("non-literal-workflow", "Bash",
     'gh workflow run "$WF" -f environment=staging', _d(pu=True, why=CNT)),
    ("block-not-loosened", "Bash",
     "gh workflow run deploy.yml -f environment=staging",
     _d(policy={"guards": {"deployWorkflow": "block"}}, why="block")),
    ("powershell-prod", "PowerShell",
     "gh workflow run deploy.yml -f environment=production", _d(why="production")),
    ("bash-c-prod", "Bash",
     "bash -c 'gh workflow run deploy.yml -f environment=production'",
     _d(why=CNT)),
    ("raw-field-long-prod", "Bash",
     "gh workflow run deploy.yml --raw-field environment=production",
     _d(why="production")),
    ("field-short-prod", "Bash",
     "gh workflow run deploy.yml -F environment=production", _d(why="production")),
    ("xargs-workflow", "Bash",
     "echo deploy.yml | xargs gh workflow run -f environment=staging",
     _d(pu=True, why=CNT)),
    ("xargs-placeholder-workflow", "Bash",
     "echo deploy.yml | xargs -I WF gh workflow run WF -f environment=staging",
     _d(pu=True, why=CNT)),
    ("xargs-subcommand", "Bash", "echo workflow run deploy.yml | xargs gh",
     _d(pu=True, why=CNT)),
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
     _d(pu=True, why=CNT)),
    ("api-input-implied-post", "Bash",
     f"gh api {DISPATCH}/deploy.yml/dispatches --input body.json",
     _d(pu=True, why=CNT)),
    ("api-variable-input", "Bash",
     f"gh api -X POST {DISPATCH}/deploy.yml/dispatches -f ref=main "
     '-f "inputs[environment]=$ENV"', _d(pu=True, why=CNT)),
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
     "-F 'inputs[environment]=@env.txt'", _d(pu=True, why=CNT)),
    ("api-non-literal-workflow", "Bash",
     f"gh api -X POST {DISPATCH}/$WF/dispatches "
     "-f 'inputs[environment]=staging'", _d(pu=True, why=CNT)),
    ("api-powershell-prod", "PowerShell",
     f"gh api -X POST {DISPATCH}/deploy.yml/dispatches -f ref=main "
     "-f 'inputs[environment]=production'", _d(why="production")),
    # Step 6: `allow` covers nonProd only; a malformed block is unknown.
    ("allow-prod-unattended", "Bash",
     "gh workflow run deploy.yml -f environment=production",
     _d(policy=DEPLOY_ALLOW, why="production")),
    ("allow-unknown-unattended", "Bash",
     "gh workflow run deploy.yml -f environment=$ENV",
     _d(policy=DEPLOY_ALLOW, why=CNT)),
    ("malformed-environments", "Bash",
     "gh workflow run deploy.yml -f environment=staging",
     _d(environments={"workflows": 1}, why=CNT)),
    ("malformed-environments-unlisted", "Bash", "gh workflow run ci.yml",
     _d(environments={"nonProd": "staging",
                      "workflows": {"deploy.yml": "staging"}}, why=CNT)),
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
     "gh workflow run deploy.yml -f environment=$ENV", _d(policy=DEPLOY_ALLOW, cnt=True)),
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
     _d(pu=True, why=CNT)),
    ("stdin-tr", "Bash", f"{J_STAGING} | tr a-z a-z | {RUN_JSON}",
     _d(pu=True, why=CNT)),
    ("stdin-jq", "Bash", f"{J_STAGING} | jq -c . | {RUN_JSON}",
     _d(pu=True, why=CNT)),
    ("stdin-awk", "Bash", f"{J_STAGING} | awk '{{print}}' | {RUN_JSON}",
     _d(pu=True, why=CNT)),
    ("stdin-perl", "Bash", f"{J_STAGING} | perl -pe 1 | {RUN_JSON}",
     _d(pu=True, why=CNT)),
    ("stdin-python", "Bash",
     f"{J_STAGING} | python3 -c 'import sys; print(sys.stdin.read())' | "
     f"{RUN_JSON}", _d(pu=True, why=CNT)),
    ("stdin-subshell", "Bash", f"({J_STAGING}; true) | {RUN_JSON}",
     _d(pu=True, why=CNT)),
    ("stdin-group", "Bash", f"{{ {J_STAGING}; }} | {RUN_JSON}",
     _d(pu=True, why=CNT)),
    ("stdin-tee-procsub", "Bash",
     f"{J_STAGING} | tee >(sed s/staging/production/) | {RUN_JSON}",
     _d(pu=True, why=CNT)),
    ("stdin-cat-procsub", "Bash", f"cat <({J_STAGING}) | {RUN_JSON}",
     _d(pu=True, why=CNT)),
    ("stdin-echo-escape", "Bash",
     "echo -e '{\"environment\":\"sta\\x67ing\"}' | " + RUN_JSON,
     _d(pu=True, why=CNT)),
    ("stdin-xargs", "Bash", f"{J_STAGING} | xargs -0 {RUN_JSON}",
     _d(pu=True, why=CNT)),
    ("stdin-sed-then-cat", "Bash",
     f"{J_STAGING} | sed s/staging/production/ | cat | {RUN_JSON}",
     _d(pu=True, why=CNT)),
    ("stdin-printf-escape", "Bash",
     "printf '{\"environment\":\"sta\\u0067ing\"}' | " + RUN_JSON,
     _d(pu=True, why=CNT)),
    ("api-stdin-sed", "Bash",
     "echo '{\"ref\":\"main\",\"inputs\":{\"environment\":\"staging\"}}' | "
     f"sed s/staging/production/ | gh api -X POST {DISPATCH}/deploy.yml/"
     "dispatches --input -", _d(pu=True, why=CNT)),
    # BLOCK 2: a redirect on the gh command replaces the piped literal.
    ("r1-stdin-redirect", "Bash", f"{J_STAGING} | {RUN_JSON} < prod.json",
     _d(pu=True, why=CNT)),
    ("stdin-redirect-no-pipe", "Bash", f"{RUN_JSON} < staging.json",
     _d(pu=True, why=CNT)),
    ("stdin-redirect-procsub", "Bash", f"{RUN_JSON} < <({J_STAGING})",
     _d(pu=True, why=CNT)),
    ("stdin-redirect-fd0", "Bash", f"{J_STAGING} | {RUN_JSON} 0< prod.json",
     _d(pu=True, why=CNT)),
    ("stdin-dup-fd", "Bash", f"{J_STAGING} | {RUN_JSON} <&3",
     _d(pu=True, why=CNT)),
    ("stdin-herestring-wins", "Bash",
     f"{J_STAGING} | {RUN_JSON} <<< '{{\"environment\":\"production\"}}'",
     _d(why=CNT)),
    ("stdin-heredoc-wins", "Bash",
     f"{J_STAGING} | {RUN_JSON} <<'EOF'\n"
     '{"environment": "production"}\nEOF', _d(why=CNT)),
    ("stdin-other-fd-herestring", "Bash",
     f"{J_PROD} | {RUN_JSON} 3<<< '{{\"environment\":\"staging\"}}'",
     _d(pu=True, why=CNT)),
    ("stdin-herestring-then-file", "Bash",
     f"{RUN_JSON} <<< '{{\"environment\":\"staging\"}}' < prod.json",
     _d(pu=True, why=CNT)),
    # BLOCK 3: a variable is never resolved from an earlier assignment.
    ("r1-variable-case", "Bash",
     "ENV=production; env=staging; "
     "gh workflow run deploy.yml -f environment=$ENV",
     _d(pu=True, why=CNT)),
    ("r1-variable-read", "Bash",
     "ENV=staging; read ENV < prod.txt; "
     "gh workflow run deploy.yml -f environment=$ENV",
     _d(pu=True, why=CNT)),
    ("variable-braced", "Bash",
     "ENV=staging; gh workflow run deploy.yml -f environment=${ENV}",
     _d(pu=True, why=CNT)),
    ("variable-export", "Bash",
     "export ENV=staging; gh workflow run deploy.yml -f environment=$ENV",
     _d(pu=True, why=CNT)),
    ("variable-source", "Bash",
     "ENV=staging; source ./env.sh; "
     "gh workflow run deploy.yml -f environment=$ENV",
     _d(pu=True, why=CNT)),
    ("variable-cmd-subst", "Bash",
     "gh workflow run deploy.yml -f environment=$(echo staging)",
     _d(pu=True, why=CNT)),
    ("variable-backtick", "Bash",
     "gh workflow run deploy.yml -f environment=`echo staging`",
     _d(pu=True, why=CNT)),
    ("variable-workflow-case", "Bash",
     "WF=deploy.yml; wf=ci.yml; gh workflow run $WF -f environment=production",
     _d(why=CNT)),
    ("variable-head", "Bash",
     "GH=gh; $GH workflow run deploy.yml -f environment=staging",
     _d(pu=True, why=CNT)),
    ("variable-api-endpoint", "Bash",
     f"EP={DISPATCH}/deploy.yml/dispatches; ep=repos/o/r/issues; "
     "gh api -X POST $EP -f 'inputs[environment]=production'",
     _d(why=CNT)),
    ("variable-api-field", "Bash",
     "ENV=staging; gh api -X POST "
     f"{DISPATCH}/deploy.yml/dispatches -f \"inputs[environment]=$ENV\"",
     _d(pu=True, why=CNT)),
    ("variable-eval", "Bash",
     "ENV=staging; eval \"gh workflow run deploy.yml -f environment=$ENV\"",
     _d(pu=True, why=CNT)),
    ("variable-bash-c", "Bash",
     "ENV=staging; bash -c \"gh workflow run deploy.yml -f environment=$ENV\"",
     _d(pu=True, why=CNT)),
    ("variable-herestring", "Bash",
     "ENV=staging; " + RUN_JSON + " <<< \"{\\\"environment\\\":\\\"$ENV\\\"}\"",
     _d(pu=True, why=CNT)),
    # An unquoted expansion anywhere in the line can split into more flags
    # (`-f a=$Y`, Y='x -f environment=production'), and a glob can match a
    # file named like one; the lexer cannot tell quoted from unquoted.
    ("variable-other-field-splits", "Bash",
     "gh workflow run deploy.yml -f environment=staging -f note=$Y",
     _d(pu=True, why=CNT)),
    ("variable-unrelated-ref", "Bash",
     "BRANCH=main; gh workflow run deploy.yml -r $BRANCH "
     "-f environment=staging", _d(pu=True, why=CNT)),
    ("glob-argument", "Bash",
     "gh workflow run deploy.yml -f environment=staging *",
     _d(pu=True, why=CNT)),
    ("brace-argument", "Bash",
     "gh workflow run deploy.yml -f environment=staging "
     "{-f,environment=production}", _d(pu=True, why=CNT)),
    ("api-other-field-splits", "Bash",
     f"gh api -X POST {DISPATCH}/deploy.yml/dispatches "
     "-f 'inputs[environment]=staging' -f ref=$REF", _d(pu=True, why=CNT)),
    # A body carrying an expansion or an escape: an unquoted heredoc expands
    # `$Y` into another key (`","environment":"production`), and bash strips
    # a backslash before `$`, `` ` `` and `\`.
    ("stdin-heredoc-expansion", "Bash",
     RUN_JSON + " <<EOF\n{\"environment\": \"staging\", \"a\": \"$Y\"}\nEOF",
     _d(pu=True, why=CNT)),
    ("stdin-heredoc-backslash", "Bash",
     RUN_JSON + " <<EOF\n{\"environment\": \"stag\\\\u0069ng\"}\nEOF",
     _d(pu=True, why=CNT)),
    ("stdin-herestring-backtick", "Bash",
     RUN_JSON + " <<< \"{\\\"environment\\\":\\\"staging\\\",\\\"a\\\":\\\"`id`\\\"}\"",
     _d(pu=True, why=CNT)),
    ("variable-tilde", "Bash",
     "gh workflow run deploy.yml -f environment=~staging",
     _d(pu=True, why=CNT)),
    ("variable-powershell", "PowerShell",
     "$ENV = 'staging'; gh workflow run deploy.yml -f environment=$ENV",
     _d(pu=True, why=CNT)),
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
    ("api-cluster-get", "Bash",
     f"gh api -iX GET {DISPATCH}/deploy.yml/dispatches "
     "-f 'inputs[environment]=production'", _d(log=None)),
]

R1_ASK_DEPLOY = [
    ("ask-stdin-sed", "Bash",
     f"{J_STAGING} | sed s/staging/production/ | {RUN_JSON}", _d(cnt=True)),
    ("ask-variable-case", "Bash",
     "ENV=production; env=staging; "
     "gh workflow run deploy.yml -f environment=$ENV", _d(cnt=True)),
]

# Moved by the grammar from the must-allow tables (old id kept): each read a
# stdin body or an unquoted `{owner}` the lexer resolved, which the grammar
# refuses. Unattended they are denied as could-not-tell; attended they ask.
# README and CONFIG say how to write each as a literal (`-f` fields, a quoted
# endpoint).
MOVED_MUST_BLOCK = [
    ("staging-json-heredoc", "Bash",
     "gh workflow run deploy.yml --json <<'EOF'\n"
     '{"environment": "staging"}\nEOF', _d(why=CNT)),
    ("staging-json-echo", "Bash", f"{J_STAGING} | {RUN_JSON}", _d(why=CNT)),
    ("api-json-stdin", "Bash",
     "echo '{\"ref\":\"main\",\"inputs\":{\"environment\":\"staging\"}}' | "
     f"gh api -X POST {DISPATCH}/deploy.yml/dispatches --input -", _d(why=CNT)),
    ("stdin-herestring-over-pipe", "Bash",
     f"{J_PROD} | {RUN_JSON} <<< '{{\"environment\":\"staging\"}}'",
     _d(why=CNT)),
    ("stdin-cat-passthrough", "Bash", f"{J_STAGING} | cat | {RUN_JSON}",
     _d(why=CNT)),
    ("stdin-printf", "Bash",
     "printf '%s' '{\"environment\":\"staging\"}' | " + RUN_JSON, _d(why=CNT)),
    ("stdin-echo-n", "Bash",
     "echo -n '{\"environment\":\"staging\"}' | " + RUN_JSON, _d(why=CNT)),
    ("api-owner-placeholder", "Bash",
     "gh api -X POST repos/{owner}/{repo}/actions/workflows/deploy.yml/"
     "dispatches -f 'inputs[environment]=staging'", _d(why=CNT)),
]
MOVED_ASK = [("ask-" + c[0], c[1], c[2], _d(cnt=True)) for c in MOVED_MUST_BLOCK]

MUST_BLOCK_DEPLOY += R1_MUST_BLOCK_DEPLOY + MOVED_MUST_BLOCK
MUST_ALLOW_DEPLOY += R1_MUST_ALLOW_DEPLOY
ASK_DEPLOY += R1_ASK_DEPLOY + MOVED_ASK

# --- T-0009 successor plan: the dispatch grammar ----------------------------
#
# Review round 2 (Codex, head b979d640) found four more ways past the dispatch
# parser, each a shell construct the lexer read differently from bash. The
# owner rejected a fifth patch in favour of T-0005's answer: a dispatch line
# is judged only when every word is a plain literal (`_PLAIN_WORD_RE`) or a
# whole single-quoted word, and every other construct is "could not tell".
# `CNT` is the phrase every could-not-tell reason carries and no other
# dispatch reason does, so a row whose line collapses to a literal reading
# goes red on its reason even where the collapsed value also denies.
S_RUN = "gh workflow run deploy.yml -f environment=staging"
S_FIXED = "gh workflow run deploy-staging.yml"

R2_MUST_BLOCK_DEPLOY = [
    # BLOCK 1: a bracket-only glob matches a file named like a flag.
    ("r2-bracket-glob", "Bash", S_RUN + " [-]fenvironment=production",
     _d(pu=True, why=CNT, files={"-fenvironment=production": b""})),
    # BLOCK 2: an fd duplication after a here-string replaces stdin.
    ("r2-fd-dup-0-from-3", "Bash",
     "exec 3< <(echo '{\"environment\":\"production\"}'); "
     "gh workflow run deploy.yml --json <<< '{\"environment\":\"staging\"}' 0>&3",
     _d(pu=True, why=CNT)),
    # BLOCK 3: a script piped into a shell, rewritten on the way.
    ("r2-sed-bash", "Bash",
     "echo '" + S_RUN + "' | sed s/staging/production/ | bash",
     _d(pu=True, why=CNT)),
    # The repro's `0>&3` on its own: the line above also refuses `<<<`,
    # `<(` and `--json`, so only this row shows the fd rule by itself.
    ("r2-fd-dup-0-alone", "Bash", S_RUN + " 0>&3", _d(why=CNT)),
    ("r2-fd-dup-1-from-3", "Bash", S_RUN + " 1>&3", _d(why=CNT)),
    ("r2-fd-dup-in-from-3", "Bash", S_RUN + " <&3", _d(why=CNT)),
    # Quoted, the same word is a literal second positional: gh takes one.
    ("r2-bracket-quoted-positional", "Bash",
     S_RUN + " '[-]fenvironment=production'", _d(why="unknown")),
    ("r2-inputs-unquoted", "Bash",
     f"gh api -X POST {DISPATCH}/deploy.yml/dispatches "
     "-f inputs[environment]=staging", _d(why=CNT)),
    ("r2-bash-c-literal", "Bash", "bash -c '" + S_FIXED + "'", _d(why=CNT)),
    ("r2-echo-bash", "Bash", "echo '" + S_FIXED + "' | bash", _d(why=CNT)),
]

GRAMMAR_MUST_BLOCK = [
    ("g-double-quotes", "Bash",
     'gh workflow run deploy.yml -f environment="staging"', _d(why=CNT)),
    ("g-ansi-c", "Bash", "gh workflow run deploy.yml -f environment=$'staging'",
     _d(why=CNT)),
    # The same three quotings on a word the environment does not depend on:
    # the lexer and a grammar that accepted them would read these lines
    # alike, so only the word rule refuses them (the rows above are also
    # refused because the two readings of their value disagree).
    ("g-double-quotes-elsewhere", "Bash", S_FIXED + ' -f "note=x"', _d(why=CNT)),
    ("g-ansi-c-elsewhere", "Bash", S_FIXED + " -f note=$'x'", _d(why=CNT)),
    ("g-single-quote-inside-elsewhere", "Bash", S_FIXED + " -f 'note=it''s'",
     _d(why=CNT)),
    ("g-backslash", "Bash", "gh workflow run deploy.yml -f environment=stag\\ing",
     _d(why=CNT)),
    ("g-var", "Bash", "gh workflow run deploy.yml -f environment=$ENV",
     _d(pu=True, why=CNT)),
    ("g-braced-var", "Bash", "gh workflow run deploy.yml -f environment=${ENV}",
     _d(pu=True, why=CNT)),
    ("g-cmd-subst", "Bash",
     "gh workflow run deploy.yml -f environment=$(echo staging)", _d(why=CNT)),
    ("g-backquote", "Bash",
     "gh workflow run deploy.yml -f environment=`echo staging`", _d(why=CNT)),
    ("g-brace-expansion", "Bash",
     "gh workflow run deploy.yml -f {environment,x}=staging", _d(why=CNT)),
    ("g-tilde", "Bash", "gh workflow run deploy.yml -f environment=~staging",
     _d(pu=True, why=CNT)),
    ("g-star", "Bash", "gh workflow run deploy.yml -f environment=stag*",
     _d(pu=True, why=CNT)),
    ("g-question", "Bash", "gh workflow run deploy.yml -f environment=stagin?",
     _d(pu=True, why=CNT)),
    ("g-redirect-in", "Bash", S_RUN + " < f", _d(why=CNT)),
    ("g-heredoc", "Bash", S_RUN + " <<EOF\nx\nEOF", _d(why=CNT)),
    ("g-herestring", "Bash", S_RUN + " <<< x", _d(why=CNT)),
    ("g-dup-in", "Bash", S_RUN + " <&0", _d(why=CNT)),
    ("g-readwrite", "Bash", S_RUN + " <>f", _d(why=CNT)),
    ("g-clobber", "Bash", S_RUN + " >|f", _d(why=CNT)),
    ("g-procsub-in", "Bash", S_RUN + " <(true)", _d(why=CNT)),
    ("g-procsub-out", "Bash", S_RUN + " > >(cat)", _d(why=CNT)),
    ("g-pipe-in", "Bash", "echo x | " + S_RUN, _d(why=CNT)),
    ("g-pipe-out", "Bash", S_RUN + " | cat", _d(why=CNT)),
    ("g-json", "Bash", S_FIXED + " --json", _d(why=CNT)),
    ("g-input-dash", "Bash",
     f"gh api -X POST {DISPATCH}/deploy-staging.yml/dispatches --input -",
     _d(why=CNT)),
    ("g-input-file", "Bash",
     f"gh api -X POST {DISPATCH}/deploy-staging.yml/dispatches --input b.json",
     _d(why=CNT)),
    ("g-field-at-file", "Bash", S_FIXED + " -F note=@notes.txt", _d(why=CNT)),
    ("g-field-at-stdin", "Bash", S_FIXED + " -F environment=@-", _d(why=CNT)),
    ("g-eval", "Bash", "eval " + S_FIXED, _d(why=CNT)),
    ("g-sh-heredoc", "Bash", "sh <<EOF\n" + S_FIXED + "\nEOF", _d(why=CNT)),
    ("g-alias-on-line", "Bash", "alias g=gh; g workflow run deploy-staging.yml",
     _d(why=CNT)),
    ("g-cp-on-line", "Bash",
     "cp $(which gh) ./g; ./g workflow run deploy-staging.yml", _d(why=CNT)),
    ("g-cp-literal", "Bash",
     "cp /usr/bin/gh ./g; ./g workflow run deploy-staging.yml", _d(why=CNT)),
    ("g-xargs", "Bash", "xargs -a args.txt " + S_FIXED, _d(why=CNT)),
    ("g-parallel", "Bash", "parallel gh workflow run ::: deploy-staging.yml",
     _d(why=CNT)),
    ("g-hole-command", "Bash", "x=gh; $x workflow run deploy-staging.yml",
     _d(why=CNT)),
    # A command word nothing on the line resolves: only the reader's hole
    # rule sees a dispatch here (the lexer does not).
    ("g-hole-command-env", "Bash", "$GH workflow run deploy-staging.yml",
     _d(why=CNT)),
    ("g-xargs-placeholder-subcommand", "Bash",
     "xargs -a args.txt -I SUB gh SUB run deploy-staging.yml", _d(why=CNT)),
    # PowerShell dot-sources gh: the reader runs it, the lexer does not.
    ("g-ps-dot-source", "PowerShell", ". " + S_FIXED, _d(why=CNT)),
    ("g-owner-placeholder-unquoted", "Bash",
     "gh api -X POST repos/{owner}/{repo}/actions/workflows/deploy-staging.yml"
     "/dispatches -f ref=main", _d(why=CNT)),
    ("g-control-char", "Bash",
     "gh workflow run deploy.yml -f environment=stag\x01ing", _d(why=CNT)),
    ("g-cr-in-word", "Bash", S_RUN + "\r", _d(why=CNT)),
    ("g-block-literal-nonprod", "Bash", S_RUN,
     _d(policy={"guards": {"deployWorkflow": "block"}}, why="block")),
    ("g-single-quote-inside", "Bash",
     "gh workflow run deploy.yml -f 'environment=stag''ing'", _d(why=CNT)),
    ("g-double-positional", "Bash", "gh workflow run deploy.yml extra "
     "-f environment=staging", _d(why="unknown")),
    ("g-find-exec", "Bash",
     "find . -maxdepth 0 -exec gh workflow run deploy-staging.yml ';'",
     _d(why=CNT)),
]

GRAMMAR_MUST_ALLOW = [
    ("g-raw-field", "Bash", S_RUN, _d(log="env:nonProd:staging")),
    ("g-field-eq", "Bash",
     "gh workflow run deploy.yml --field=environment=staging",
     _d(log="env:nonProd:staging")),
    ("g-short-attached", "Bash",
     "gh workflow run deploy.yml -fenvironment=staging",
     _d(log="env:nonProd:staging")),
    ("g-repo-ref", "Bash",
     "gh workflow run -R o/r -r main deploy.yml -f environment=qa",
     _d(log="env:nonProd:qa")),
    ("g-dashdash-positional", "Bash", "gh workflow run -- deploy-staging.yml",
     _d(log="env:nonProd:staging")),
    ("g-display-name-single", "Bash", "gh workflow run 'Deploy Staging'",
     _d(environments=NAMED_ENVS, log="env:nonProd:staging")),
    ("g-rest-single-quoted", "Bash",
     f"gh api -X POST {DISPATCH}/deploy.yml/dispatches -f ref=main "
     "-f 'inputs[environment]=staging'", _d(log="env:nonProd:staging")),
    ("g-owner-placeholder-quoted", "Bash",
     "gh api -X POST 'repos/{owner}/{repo}/actions/workflows/deploy.yml/"
     "dispatches' -f 'inputs[environment]=staging'",
     _d(log="env:nonProd:staging")),
    ("g-assignment-prefix", "Bash", "GH_TOKEN=x " + S_RUN,
     _d(log="env:nonProd:staging")),
    ("g-stderr-dup", "Bash", S_RUN + " 2>&1", _d(log="env:nonProd:staging")),
    ("g-stdout-file", "Bash", S_RUN + " > log", _d(log="env:nonProd:staging")),
    ("g-stdout-append", "Bash", S_RUN + " >> log",
     _d(log="env:nonProd:staging")),
    ("g-all-streams", "Bash", S_RUN + " &> log", _d(log="env:nonProd:staging")),
    ("g-then-echo", "Bash", S_RUN + "; echo done",
     _d(log="env:nonProd:staging")),
    ("g-and-echo", "Bash", S_RUN + " && echo ok",
     _d(log="env:nonProd:staging")),
    ("g-gh-exe", "Bash", "gh.exe workflow run deploy.yml -f environment=staging",
     _d(log="env:nonProd:staging")),
    ("g-fixed-staging", "Bash", S_FIXED, _d(log="env:nonProd:staging")),
    ("g-prod-unattended-both-layers", "Bash",
     "gh workflow run deploy.yml -f environment=production",
     _d(pu=True, log="env:prod-unattended:production", said="production")),
    ("g-unlisted-literal", "Bash", "gh workflow run ci.yml", _d(log=None)),
    ("g-other-gh-quoted", "Bash", 'gh pr create --title "fix: x"',
     _d(log=None)),
    ("g-api-get", "Bash", f"gh api {DISPATCH}/deploy.yml/dispatches",
     _d(log=None)),
    ("g-empty-map", "Bash",
     'gh workflow run deploy.yml -f environment="production"',
     _d(environments={"nonProd": DEPLOY_NONPROD, "workflows": {}}, log=None)),
    ("g-help-standalone", "Bash", "gh workflow run deploy.yml --help",
     _d(log=None)),
    ("g-help-short", "Bash", "gh workflow run deploy.yml -h", _d(log=None)),
    ("g-help-first", "Bash", "gh workflow run --help", _d(log=None)),
    ("g-ps-call-operator", "PowerShell", "& " + S_FIXED,
     _d(log="env:nonProd:staging")),
    ("g-ps-call-quoted", "PowerShell",
     "& 'gh' workflow run deploy-staging.yml", _d(log="env:nonProd:staging")),
]

GRAMMAR_ASK = [
    ("g-ask-could-not-tell", "Bash",
     "gh workflow run deploy.yml --json <<'EOF'\n"
     '{"environment": "staging"}\nEOF', _d(cnt=True)),
    ("g-ask-prod", "Bash",
     "gh workflow run deploy.yml -f environment=production", _d()),
    ("g-ask-unknown-no-input", "Bash", "gh workflow run deploy.yml", _d()),
    # A value, not a flag: gh deploys to an environment called `--help`.
    ("g-ask-help-value", "Bash",
     "gh workflow run deploy.yml -f environment=--help", _d()),
    # After `--`, a second positional: gh takes one workflow.
    ("g-ask-dashdash-help", "Bash", "gh workflow run deploy.yml -- --help",
     _d()),
    ("g-ask-help-nonliteral", "Bash", 'gh workflow run deploy.yml --help "$X"',
     _d(cnt=True)),
]

MUST_BLOCK_DEPLOY += R2_MUST_BLOCK_DEPLOY + GRAMMAR_MUST_BLOCK
MUST_ALLOW_DEPLOY += GRAMMAR_MUST_ALLOW
ASK_DEPLOY += GRAMMAR_ASK

_DB_SAMPLE = ("prod-input", "powershell-prod", "api-prod-input",
              "api-powershell-prod", "r2-bracket-glob", "g-double-quotes")
_DA_SAMPLE = ("staging-raw-field", "prod-unattended-both-layers",
              "api-staging-input", "g-ps-call-operator", "g-ps-call-quoted")
# An approval marker's path, as a could-not-tell reason names it.
_MARKER_RE = re.compile(r"\.crew[/\\]\S*deployWorkflow-[0-9a-f]{16}")


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
    if _opts.get("cnt"):
        assert CNT in reason, reason
        assert _MARKER_RE.search(reason), reason


def test_deploy_tables_are_distinct_and_complete():
    """Every block row names the reason it expects -- an environment, unknown,
    could not tell, or the block policy -- so no row is loosened to "any
    deny"."""
    ids = _ids(MUST_BLOCK_DEPLOY + MUST_ALLOW_DEPLOY + ASK_DEPLOY)
    assert len(ids) == len(set(ids))
    assert all(c[3].get("why") in ("production", "unknown", CNT, "block")
               for c in MUST_BLOCK_DEPLOY)
    assert all("log" in c[3] for c in MUST_ALLOW_DEPLOY)


_QA_ENVS = {"nonProd": ["qa"], "prodUnattended": False, "problem": "",
            "workflows": {"deploy.yml": "input:environment"}}


def _dispatch_scopes(command, shell="bash", envs=None):
    ctx = {"dispatch": _QA_ENVS if envs is None else envs}
    return [f.scope for f in cloud_guard.scan(shell, command, ctx=ctx)
            if f.rule == "deployWorkflow"]


def test_both_dispatch_forms_share_one_classifier(monkeypatch):
    """Step 5: the REST form is not a copy of the `gh workflow run` path.
    Both parse into the same dispatch shape, and `dispatch_answer` hands
    either to the one `crew_guards.dispatch_environment`; stubbing that
    function changes both."""
    run = _dispatch_scopes("gh workflow run deploy.yml -f environment=qa")
    api = _dispatch_scopes(f"gh api -X POST {DISPATCH}/deploy.yml/dispatches "
                           "-f ref=main -f 'inputs[environment]=qa'")
    assert len(run) == len(api) == 1
    assert run[0]["workflow"] == api[0]["workflow"] == "deploy.yml"
    assert run[0]["inputs"] == api[0]["inputs"] == [("environment", "qa", "")]
    assert crew_guards.dispatch_environment(run[0], _QA_ENVS) == \
        crew_guards.dispatch_environment(api[0], _QA_ENVS)
    seen = []
    monkeypatch.setattr(crew_guards, "dispatch_environment",
                        lambda scope, envs: seen.append(scope["form"]))
    for command in ("gh workflow run deploy.yml -f environment=qa",
                    f"gh api -X POST {DISPATCH}/deploy.yml/dispatches "
                    "-f 'inputs[environment]=qa'"):
        crew_guards.dispatch_answer(command, "bash", _QA_ENVS)
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
    """A malformed block engages the gate with nothing listed: every
    dispatch-shaped line, literal or not, listed or not, is could-not-tell."""
    repo = tcg._fixture(tmp_path, {"environments": {"workflows": 1}})  # pylint: disable=protected-access
    envs = cloud_guard.environments_config(str(repo))
    assert envs["problem"] and envs["workflows"] == {}
    for command in ("gh workflow run ci.yml", "gh workflow run",
                    f"gh api -X POST {DISPATCH}/ci.yml/dispatches"):
        (scope,) = _dispatch_scopes(command, envs=envs)
        assert scope["state"] == cloud_guard.ENV_UNKNOWN, (command, scope)
        assert scope["op"] == "line-not-literal", (command, scope)
        assert "environments" in scope["why"], (command, scope)


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
    """Could-not-tell is never permission: every round-1 unknown or
    could-not-tell row is denied under `deployWorkflow: block` too (the scan
    finds a dispatch at all, and it is not classified)."""
    envs = dict(_QA_ENVS, nonProd=DEPLOY_NONPROD, workflows=WORKFLOWS)
    for _id, tool, command, opts in R1_MUST_BLOCK_DEPLOY:
        shell = "powershell" if tool == "PowerShell" else "bash"
        if opts["why"] not in ("unknown", CNT):
            continue
        scopes = _dispatch_scopes(command, shell, envs)
        assert scopes and all(s["state"] == "unknown" for s in scopes), _id


def test_r1_tables_are_distinct():
    ids = _ids(MUST_BLOCK_DEPLOY + MUST_ALLOW_DEPLOY + ASK_DEPLOY)
    assert len(ids) == len(set(ids))


# --- the grammar's marker, contract and road --------------------------------


def _write_workflows(repo, workflows):
    path = repo / ".crew" / "config.json"
    cfg = json.loads(path.read_text(encoding="utf-8"))
    cfg["environments"]["workflows"] = workflows
    path.write_text(json.dumps(cfg), encoding="utf-8")


def test_r2_a_marker_covers_exact_bytes_only(tmp_path):
    """Round 2 BLOCK 4: a marker issued for `--json < prod-one.json` covered
    `< prod-two.json`, because it was keyed on the argv and a stdin crew never
    read. A marker now covers exactly the command bytes it was issued for: a
    marker for the argv without its `<` path covers nothing, the one issued
    allows that text, and the other file's text is denied."""
    first = "gh workflow run deploy.yml --json < prod-one.json"
    second = "gh workflow run deploy.yml --json < prod-two.json"
    case = ("r2-marker", "Bash", first, _d(why=CNT))
    repo, result = _run("python", tmp_path, case)
    assert result[0] == "deny", result
    argv_only = crew_config.guard_marker(str(repo), "deployWorkflow",
                                         "gh workflow run deploy.yml --json")
    open(argv_only, "w", encoding="utf-8").close()  # pylint: disable=consider-using-with
    result = tcg.run_hook("python", tmp_path, "Bash", first,
                          extra_env=dict(UNATTENDED))
    assert result[0] == "deny", result
    marker = _deny_marker(result[1])
    assert marker != argv_only
    open(marker, "w", encoding="utf-8").close()  # pylint: disable=consider-using-with
    result = tcg.run_hook("python", tmp_path, "Bash", first,
                          extra_env=dict(UNATTENDED))
    assert result[0] == "allow", result
    result = tcg.run_hook("python", tmp_path, "Bash", second,
                          extra_env=dict(UNATTENDED))
    assert result[0] == "deny", result
    assert _deny_marker(result[1]) not in (marker, argv_only)


def test_marker_does_not_survive_a_remap(tmp_path):
    """A classified dispatch's marker is keyed on the command text AND the
    workflow key and environment judged, so an approval given for one
    environment does not carry across a config edit inside the TTL."""
    command = "gh workflow run deploy.yml -f environment=production"
    case = ("remap", "Bash", command, _d(why="production"))
    repo, result = _run("python", tmp_path, case)
    assert result[0] == "deny", result
    open(_deny_marker(result[1]), "w", encoding="utf-8").close()  # pylint: disable=consider-using-with
    result = tcg.run_hook("python", tmp_path, "Bash", command,
                          extra_env=dict(UNATTENDED))
    assert result[0] == "allow", result
    _write_workflows(repo, dict(WORKFLOWS, **{"deploy.yml": "production-eu"}))
    result = tcg.run_hook("python", tmp_path, "Bash", command,
                          extra_env=dict(UNATTENDED))
    assert result[0] == "deny", result
    assert "production-eu" in result[1], result


def test_a_could_not_tell_marker_allows_that_text(tmp_path):
    """Could-not-tell is asked about, never unreadable: the person's live
    marker for that exact text allows it, and only it."""
    command = 'gh workflow run deploy.yml -f environment="production"'
    case = ("cnt-marker", "Bash", command, _d(why=CNT))
    _repo, result = _run("python", tmp_path, case)
    assert result[0] == "deny" and CNT in result[1], result
    open(_deny_marker(result[1]), "w", encoding="utf-8").close()  # pylint: disable=consider-using-with
    result = tcg.run_hook("python", tmp_path, "Bash", command,
                          extra_env=dict(UNATTENDED))
    assert result[0] == "allow", result
    result = tcg.run_hook("python", tmp_path, "Bash", command + " ",
                          extra_env=dict(UNATTENDED))
    assert result[0] == "deny", result


_CONTRACT_ENVS = {"nonProd": DEPLOY_NONPROD, "prodUnattended": False,
                  "problem": "", "workflows": WORKFLOWS}


@pytest.mark.parametrize("text,state,op", [
    (S_RUN, "nonProd", "deploy"),
    ("gh workflow run deploy.yml -f environment=production", "prod", "deploy"),
    ("gh workflow run deploy.yml", "unknown", "deploy"),
    ("gh workflow run ci.yml", "unlisted", None),
    ('gh pr create --title "x"', "unlisted", None),
    (S_RUN + " | cat", "unknown", "line-not-literal"),
    ("echo '" + S_RUN + "' | bash", "unknown", "line-not-literal"),
    (S_FIXED + " --json", "unknown", "line-not-literal"),
    ("gh workflow run deploy.yml --help", "unlisted", None),
])
def test_dispatch_answer_contract(text, state, op):
    """T-0045/T-0072's contract: `(state, why, scope)`, `state` one of four,
    could-not-tell is `unknown` with `scope["op"] == "line-not-literal"`."""
    got, why, scope = crew_guards.dispatch_answer(text, "bash", _CONTRACT_ENVS)
    assert got == state, (got, why, scope)
    assert (scope or {}).get("op") == op, scope
    assert state in ("nonProd", "prod", "unlisted") or why


def test_dispatch_answer_is_the_only_road():
    """`_classify`'s `gh` branch reaches the dispatch parser only through
    `dispatch_answer`, and `dispatch_answer` gates before it parses."""
    classify = inspect.getsource(cloud_guard._classify)  # pylint: disable=protected-access
    assert "dispatch_answer(" in classify
    assert "dispatch_scopes(" not in classify
    answer = inspect.getsource(crew_guards.dispatch_answer)
    gate = answer.find("dispatch_first_non_literal(")
    parse = answer.find("dispatch_scopes(")
    assert -1 < gate < parse, (gate, parse)
    module = inspect.getsource(cloud_guard)
    assert "dispatch_scopes" not in module


def test_dispatch_gate_refuses_a_disagreement():
    """`cloud_guard.scan`'s last check: when the lexer's dispatch findings
    name something other than the literal reading of the raw line, neither is
    believed and the line is could-not-tell. Built directly because no line
    is known today on which the two literal readings disagree -- this is the
    backstop for the day one is."""
    staging = crew_guards.dispatch_answer(S_RUN, "bash", _CONTRACT_ENVS)[2]
    agreed = [dict(staging, state="nonProd")]
    assert crew_guards.dispatch_gate(S_RUN, "bash", _CONTRACT_ENVS, agreed) \
        is None
    other = [dict(staging, state="nonProd", value="qa")]
    cnt = crew_guards.dispatch_gate(S_RUN, "bash", _CONTRACT_ENVS, other)
    assert cnt is not None
    assert cnt["op"] == "line-not-literal" and cnt["state"] == "unknown", cnt
    assert crew_guards.dispatch_gate(S_RUN, "bash", _CONTRACT_ENVS, []) \
        is not None


def test_grammar_tables_are_distinct_and_complete():
    tables = (R2_MUST_BLOCK_DEPLOY + GRAMMAR_MUST_BLOCK + GRAMMAR_MUST_ALLOW
              + GRAMMAR_ASK)
    ids = _ids(tables)
    assert len(ids) == len(set(ids))
    assert all(c[3]["why"] in (CNT, "unknown", "block", "production")
               for c in R2_MUST_BLOCK_DEPLOY + GRAMMAR_MUST_BLOCK)
    assert sum(c[3]["why"] == CNT for c in GRAMMAR_MUST_BLOCK) >= 35
    assert [c for c in GRAMMAR_MUST_ALLOW if c[3]["log"]], "a vacuous table"

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

REVIEW ROUND 3 (Codex, head `6494d149`). Every `r3-` row and test was run
against `6494d149` in a detached worktree before the fix, python driver:

  allowed unattended (RED): r3-hole-both-words, r3-hole-whole-command,
    r3-hole-command-then-fields, r3-hole-command-then-workflow,
    r3-hole-command-then-run, r3-ps-start-process-hole,
    r3-ps-start-process-group, r3-ps-start-process-filepath,
    r3-ps-start-process-filepath-last, r3-ps-start-process-args-hole,
    r3-ps-alias-hole, r3-ps-alias-hole-named, r3-ps-alias-hole-arg,
    r3-ps-alias-value-first, r3-ps-alias-provider, r3-ps-hole-arg,
    r3-global-malformed, r3-global-null, r3-global-malformed-empty-map;
    attended, r3-ask-hole-both-words and r3-ask-ps-start-process-hole (no
    ask at all)
  denied as cloudGuard "unreadable", never deployWorkflow (RED on the
    reason): r3-xargs-placeholder-command, r3-xargs-brace-command; attended,
    r3-ask-xargs-placeholder-command (denied, not asked)
  RED as functions: test_r3_a_run_time_command_word_is_could_not_tell
    (seven of eight; `parallel-numbered` was already could-not-tell, the
    reader making any `{` word a hole), test_r3_the_xargs_placeholder_is_the_deploy_guards,
    test_r3_a_fed_command_word_on_the_classify_road,
    test_r3_a_malformed_global_block_is_a_problem (all four),
    test_r3_a_well_formed_global_block_is_not_a_problem (no
    `dispatchProblem` key)
  already GREEN, kept as over-block guards: r3-hole-other-shape,
    r3-ps-start-process-other, r3-global-well-formed

REVIEW ROUND 4 (Codex, head `6d0f5a69`). Every `r4-` row and test was run
against `6d0f5a69` in a detached worktree before the fix, python driver:

  allowed unattended (RED): r4-ps-switch-before-target,
    r4-ps-abbrev-filepath, r4-ps-switch-wait, r4-ps-saps-switch,
    r4-ps-common-param, r4-ps-switch-all-runtime, r4-ps-en-dash-switch,
    r4-ps-module-qualified-switch, r4-ps-abbrev-single, r4-ps-alias-abbrev,
    r4-ps-alias-switch, r4-ps-module-qualified-alias,
    r4-alias-then-hole-verb, r4-ps-switch-after-args,
    r4-ps-alias-switch-between, r4-ps-full-params-before-args,
    r4-ps-workdir-before-args, r4-ps-param-alias-pspath,
    r4-ps-redirect-stdin-runtime, r4-ps-new-item-alias-abbrev; attended,
    r4-ask-ps-switch-before-target, r4-ask-ps-abbrev-filepath,
    r4-ask-ps-switch-runtime-other and r4-ask-ps-alias-literal-switch (no
    ask at all)
  denied unattended as could-not-tell (RED, the over-block): r4-alias-then-echo,
    r4-alias-then-echo-dispatches, r4-hash-then-echo, r4-ps-alias-then-echo,
    r4-ps-new-item-alias-then-echo
  RED as a function: test_r4_ps_full_params_match_powershell (no
    `_PS_FULL_PARAMS`)
  already GREEN, kept as regression rows: r4-ps-switch-passthru-after,
    r4-ps-switch-colon-bound, r4-ps-switch-literal-gh,
    r4-ps-abbrev-argumentlist, r4-ps-param-alias, every r4-ps-args- row,
    r4-ps-full-lowercase, r4-ps-redirect-stdin, r4-ps-new-alias-abbrev,
    r4-ps-alias-provider-switch, r4-alias-then-dispatch-prod,
    r4-alias-quoted-both, r4-alias-wrapped-gh, r4-hash-p-copy,
    r4-source-procsub (the line-wide read the same-command rule narrows was
    what caught the bash ones), and the must-allow rows r4-alias-then-other-gh,
    r4-alias-other-target, r4-ps-launcher-switch-no-dispatch,
    r4-ps-launcher-colon-true-no-dispatch, r4-ps-full-params-other,
    r4-ps-saps-full-params-other; and r4-ps-new-item-alias-name and
    r4-ps-alias-path-backslash, which the same-command rule then OPENED (both
    were caught only by the line-wide read) until `ps_aliases` read an
    `alias:` path's name from `-Name` and past a leading backslash

REVIEW ROUND 5 (Codex, head `cc754aa0`). Every `r5-` row and test was run
against the unchanged code at `cc754aa0` before the fix, python driver:

  refused as cloud guard "internal error (TypeError)", never deployWorkflow
    (RED on the reason; the hook failed CLOSED, so unattended it was denied,
    not run, but `scan` and `dispatch_answer`'s gate raised): r5-two-unknown-
    dispatches, r5-two-unknown-reversed, r5-two-unknown-api; RED as a
    function, test_r5_two_unknown_dispatches_do_not_crash_the_scan
  allowed unattended (RED): r5-function-hash-after, r5-trap-hash-after,
    r5-trap-alias-before, r5-alias-dollar-value
  denied unattended as could-not-tell (RED, the over-block):
    r5-alias-after-dispatch-word, r5-hash-after-dispatch-word,
    r5-alias-echo-gh, r5-alias-gh-then-echo, r5-ps-comma-quoted,
    r5-ps-comma-quoted-api
  RED as a function: test_r5_a_marker_covers_every_dispatch_judged
  already GREEN, kept as regression rows: r5-loop-hash-after,
    r5-while-alias-after, r5-alias-command-gh, r5-alias-assign-gh,
    r5-alias-last-command-gh, r5-alias-dq-dollar, r5-ps-comma-bare,
    r5-ps-comma-quoted-array, r5-bash-comma-quoted, and
    test_r5_an_approval_does_not_survive_a_second_dispatchs_remap -- the
    hook keys each finding on its own dispatch, so BLOCK 2's repro did not
    reproduce through the hook; `dispatch_answer`'s public scope, the one
    T-0045 keys on, carried only the top-ranked dispatch

The function, trap, `alias g='$x'`, loop and alias-value rows are
neighbours found while checking the fixes, not rows the review named.
Checked and left as they are: a PowerShell `Set-Alias` still counts for its
whole line (`g workflow run x; Set-Alias g gh` asks) -- the PowerShell reader
does not order script blocks, so the whole-line read stays the conservative
one -- and terraform's `cp`/`ln` copies (`_copies_terraform`, T-0005) still
count for the whole line.

The en dash, module-qualified, `alias g=gh; g $W ...`, switch-after,
`-PSPath`, run-time `-RedirectStandardInput`, trusted-value, `saps` and
`New-Item`/`alias:\\` rows are neighbours found while checking each fix, not
rows the plan named. Two of them showed the plan's "trusted lines are read as
now" was not enough on its own: a trusted parameter's value (`-WindowStyle
Hidden`, `-WorkingDirectory C:\\`) was read as gh's first argument, so
`_ps_values` now passes on only the positional values and `-ArgumentList`.

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
import os
import re
import subprocess

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import crew_config
import crew_fixtures
import crew_guards
import test_cloud_guard as tcg
from test_cloud_guard_environments import (  # pylint: disable=unused-import
    UNATTENDED, _ids, _log_rows, _no_ambient_terraform_env, _run, _sample)  # noqa: F401 - autouse fixture

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

# --- T-0009 review round 3 (Codex, head 6494d149) ---------------------------
#
# BLOCK 1: a command word made at run time was gated from raw `gh`/`workflow`
# mentions, not from the shape of its argv, so building both words at run
# time dispatched unlisted. BLOCK 2: a PowerShell launcher or alias target was
# followed only when an argument literally named gh. FIX: an xargs/parallel
# placeholder in the executable position was not a command-word hole. BLOCK 3:
# a malformed MACHINE-GLOBAL `environments` block did not engage the gate.
# Neighbours checked with each: the whole command held in one run-time
# variable (bash splits it), a run-time word in PowerShell's own gh argv, an
# alias to a run-time target used with a run-time subcommand, `-FilePath`,
# `{}` as the placeholder, and a global block that is `null`.
R3_ARG = "'workflow run deploy-prod.yml'"
R3_PS_GH = "$x = 'g'+'h'; "
R3_GLOBAL = {"guards": {"deployWorkflow": "ask"}}


def _g(block, **kw):
    """`_d(**kw)` with the machine-global layer's `environments` set to
    `block`, which the hook reads from the fixture HOME."""
    opts = _d(**kw)
    opts["global"] = dict(copy.deepcopy(R3_GLOBAL), environments=block)
    return opts


R3_MUST_BLOCK_DEPLOY = [
    ("r3-hole-both-words", "Bash",
     "X=g; X+=h; Y=work; Y+=flow; $X $Y run deploy-prod.yml", _d(why=CNT)),
    ("r3-hole-whole-command", "Bash",
     'X=g; X+=h; Y=work; Y+=flow; C="$X $Y run deploy-prod.yml"; $C',
     _d(why=CNT)),
    ("r3-hole-command-then-fields", "Bash",
     'X=g; X+=h; Y=work; Y+=flow; C="$X $Y run deploy.yml"; '
     "$C -f environment=staging", _d(why=CNT)),
    ("r3-hole-command-then-workflow", "Bash",
     'X=g; X+=h; Y=work; Y+=flow; C="$X $Y run"; $C deploy-prod.yml',
     _d(why=CNT)),
    # A command word nothing on the line resolves, so the lexer cannot
    # rebuild `gh workflow` and only the hole's shape sees `run <wf>`.
    ("r3-hole-command-then-run", "Bash", "$GH_WORKFLOW run deploy-prod.yml",
     _d(why=CNT)),
    ("r3-xargs-placeholder-command", "Bash",
     "echo gh | xargs -I CMD CMD workflow run deploy-prod.yml", _d(why=CNT)),
    ("r3-xargs-brace-command", "Bash",
     "echo gh | xargs -I{} {} workflow run deploy-prod.yml", _d(why=CNT)),
    ("r3-ps-start-process-hole", "PowerShell",
     R3_PS_GH + "Start-Process $x -ArgumentList " + R3_ARG, _d(why=CNT)),
    ("r3-ps-start-process-filepath", "PowerShell",
     R3_PS_GH + "Start-Process -FilePath $x -ArgumentList " + R3_ARG,
     _d(why=CNT)),
    # A grouped target: the lexer keeps only a guess at its value.
    ("r3-ps-start-process-group", "PowerShell",
     "Start-Process (Get-Gh) -ArgumentList " + R3_ARG, _d(why=CNT)),
    # `-FilePath` last: the first value is the argument list, not the target.
    ("r3-ps-start-process-filepath-last", "PowerShell",
     R3_PS_GH + "Start-Process -ArgumentList " + R3_ARG + " -FilePath $x",
     _d(why=CNT)),
    ("r3-ps-start-process-args-hole", "PowerShell",
     R3_PS_GH + "$w = 'work'+'flow'; "
     "Start-Process $x -ArgumentList $w,'run','deploy-prod.yml'", _d(why=CNT)),
    ("r3-ps-alias-hole", "PowerShell",
     R3_PS_GH + "Set-Alias g $x; g workflow run deploy-prod.yml", _d(why=CNT)),
    ("r3-ps-alias-hole-named", "PowerShell",
     R3_PS_GH + "Set-Alias -Name g -Value $x; g workflow run deploy-prod.yml",
     _d(why=CNT)),
    ("r3-ps-alias-hole-arg", "PowerShell",
     R3_PS_GH + "$w = 'work'+'flow'; Set-Alias g $x; g $w run deploy-prod.yml",
     _d(why=CNT)),
    # `-Name` after the value: the positional binds to `-Value`.
    ("r3-ps-alias-value-first", "PowerShell",
     R3_PS_GH + "$w = 'work'+'flow'; Set-Alias $x -Name g; g $w run deploy-prod.yml",
     _d(why=CNT)),
    ("r3-ps-alias-provider", "PowerShell",
     R3_PS_GH + "$w = 'work'+'flow'; Set-Item alias:g $x; g $w run deploy-prod.yml",
     _d(why=CNT)),
    ("r3-ps-hole-arg", "PowerShell",
     "$w = 'work'+'flow'; gh $w run deploy-prod.yml", _d(why=CNT)),
    ("r3-global-malformed", "Bash", S_RUN,
     _g({"prodUnattended": "yes"}, why=CNT)),
    ("r3-global-null", "Bash", S_RUN, _g(None, why=CNT)),
    # Nothing listed: a malformed global block still engages the gate, as a
    # malformed repo block does (`dispatch_engaged`).
    ("r3-global-malformed-empty-map", "Bash", "gh workflow run ci.yml",
     _g({"prodUnattended": "yes"}, why=CNT,
        environments={"nonProd": DEPLOY_NONPROD, "workflows": {}})),
]

R3_MUST_ALLOW_DEPLOY = [
    # A command word made at run time whose arguments cannot follow any part
    # of a dispatch: `gh pr create` is never gated (Step 9's over-block).
    ("r3-hole-other-shape", "Bash", "X=g; X+=h; $X pr create --title x",
     _d(log=None)),
    # PowerShell does not split a variable into words: `Start-Process $exe`
    # with one literal argument that is not `workflow` is not a dispatch.
    ("r3-ps-start-process-other", "PowerShell",
     "Start-Process $exe -ArgumentList 'notes.txt'", _d(log=None)),
    ("r3-global-well-formed", "Bash", S_RUN,
     _g({"prodUnattended": False}, log="env:nonProd:staging")),
]

R3_ASK_DEPLOY = [
    # Attended, a could-not-tell dispatch asks: never cloudGuard's
    # unconditional "unreadable" deny.
    ("r3-ask-xargs-placeholder-command", "Bash",
     "echo gh | xargs -I CMD CMD workflow run deploy-prod.yml", _d(cnt=True)),
    ("r3-ask-hole-both-words", "Bash",
     "X=g; X+=h; Y=work; Y+=flow; $X $Y run deploy-prod.yml", _d(cnt=True)),
    ("r3-ask-ps-start-process-hole", "PowerShell",
     R3_PS_GH + "Start-Process $x -ArgumentList " + R3_ARG, _d(cnt=True)),
]

# --- review round 4 (Codex, head `6d0f5a69`) --------------------------------
#
# BLOCK 1: a PowerShell switch (`-NoNewWindow`) before a run-time gh target
# swallowed the target as its value. BLOCK 2: an abbreviation (`-Fi` for
# `-FilePath`) was not read as the target parameter. FIX: `alias g=gh; echo
# workflow` was denied, gh named by one command and `workflow` by another.
# The launcher rule: a PowerShell launcher or alias line holding a
# dispatch-shaped word is could-not-tell unless every parameter on it is a
# known FULL, value-taking parameter name. The same-command rule: gh and
# `workflow` must be in ONE command, and a bash alias or `hash -p` of gh makes
# its name a copy of gh. Each must-block row maps to `deploy-prod.yml`, which
# is production, so a collapse to "unlisted" allows and a collapse to a
# literal reading denies as production, never "could not tell".
R4_PS_GH = "$x = 'g'+'h'; "
R4_ARG = "'workflow run deploy-prod.yml'"
R4_PROD = "g workflow run deploy-prod.yml"

R4_MUST_BLOCK_DEPLOY = [
    ("r4-ps-switch-before-target", "PowerShell",
     R4_PS_GH + "Start-Process -NoNewWindow $x -ArgumentList " + R4_ARG,
     _d(why=CNT)),
    ("r4-ps-abbrev-filepath", "PowerShell",
     R4_PS_GH + "Start-Process -Fi $x -ArgumentList " + R4_ARG, _d(why=CNT)),
    ("r4-ps-switch-wait", "PowerShell",
     R4_PS_GH + "Start-Process -Wait $x -ArgumentList " + R4_ARG, _d(why=CNT)),
    ("r4-ps-switch-passthru-after", "PowerShell",
     R4_PS_GH + "Start-Process $x -PassThru -ArgumentList " + R4_ARG,
     _d(why=CNT)),
    ("r4-ps-switch-colon-bound", "PowerShell",
     R4_PS_GH + "Start-Process -NoNewWindow:$true $x -ArgumentList " + R4_ARG,
     _d(why=CNT)),
    ("r4-ps-switch-literal-gh", "PowerShell",
     "Start-Process -NoNewWindow gh -ArgumentList " + R4_ARG, _d(why=CNT)),
    ("r4-ps-saps-switch", "PowerShell",
     R4_PS_GH + "saps -NoNewWindow $x -ArgumentList " + R4_ARG, _d(why=CNT)),
    ("r4-ps-common-param", "PowerShell",
     R4_PS_GH + "Start-Process -Verbose $x -ArgumentList " + R4_ARG,
     _d(why=CNT)),
    # Every dispatch-shaped word is made at run time: no literal gh or
    # `workflow` on the line.
    ("r4-ps-switch-all-runtime", "PowerShell",
     R4_PS_GH + "$a = 'work'+'flow'; Start-Process -NoNewWindow $x "
     "-ArgumentList $a", _d(why=CNT)),
    # PowerShell reads an en dash as the dash of a parameter.
    ("r4-ps-en-dash-switch", "PowerShell",
     R4_PS_GH + "Start-Process –NoNewWindow $x -ArgumentList " + R4_ARG,
     _d(why=CNT)),
    ("r4-ps-module-qualified-switch", "PowerShell",
     R4_PS_GH + "Microsoft.PowerShell.Management\\Start-Process -NoNewWindow "
     "$x -ArgumentList " + R4_ARG, _d(why=CNT)),
    # A switch after the first value, before the value it swallows.
    ("r4-ps-switch-after-args", "PowerShell",
     R4_PS_GH + "Start-Process -ArgumentList " + R4_ARG + " -Wait $x",
     _d(why=CNT)),
    ("r4-ps-alias-switch-between", "PowerShell",
     R4_PS_GH + "Set-Alias g -Force $x; " + R4_PROD, _d(why=CNT)),
    # A trusted parameter's value is not gh's first argument.
    ("r4-ps-full-params-before-args", "PowerShell",
     R4_PS_GH + "Start-Process -FilePath $x -WindowStyle Hidden -ArgumentList "
     + R4_ARG, _d(why=CNT)),
    ("r4-ps-workdir-before-args", "PowerShell",
     R4_PS_GH + "Start-Process $x -WorkingDirectory C:\\ -ArgumentList "
     + R4_ARG, _d(why=CNT)),
    ("r4-ps-abbrev-single", "PowerShell",
     R4_PS_GH + "Start-Process -F $x -ArgumentList " + R4_ARG, _d(why=CNT)),
    ("r4-ps-abbrev-argumentlist", "PowerShell",
     R4_PS_GH + "Start-Process -FilePath $x -Arg " + R4_ARG, _d(why=CNT)),
    ("r4-ps-param-alias", "PowerShell",
     R4_PS_GH + "Start-Process -FilePath $x -Args " + R4_ARG, _d(why=CNT)),
    ("r4-ps-param-alias-pspath", "PowerShell",
     R4_PS_GH + "Start-Process -PSPath $x -ArgumentList " + R4_ARG,
     _d(why=CNT)),
    ("r4-ps-args-positional", "PowerShell",
     R4_PS_GH + "Start-Process $x " + R4_ARG, _d(why=CNT)),
    ("r4-ps-args-comma-bare", "PowerShell",
     R4_PS_GH + "Start-Process $x -ArgumentList workflow,run,deploy-prod.yml",
     _d(why=CNT)),
    ("r4-ps-args-array", "PowerShell",
     R4_PS_GH + "Start-Process $x -ArgumentList "
     "@('workflow','run','deploy-prod.yml')", _d(why=CNT)),
    ("r4-ps-args-colon", "PowerShell",
     R4_PS_GH + "Start-Process $x -ArgumentList:" + R4_ARG, _d(why=CNT)),
    # Full names in any case are trusted, read normally, and still caught.
    ("r4-ps-full-lowercase", "PowerShell",
     R4_PS_GH + "Start-Process -filepath $x -argumentlist " + R4_ARG,
     _d(why=CNT)),
    ("r4-ps-redirect-stdin", "PowerShell",
     "Start-Process gh -RedirectStandardInput in.json -ArgumentList "
     "'workflow run deploy-prod.yml --json'", _d(why=CNT)),
    ("r4-ps-redirect-stdin-runtime", "PowerShell",
     R4_PS_GH + "Start-Process $x -RedirectStandardInput in.json "
     "-ArgumentList " + R4_ARG, _d(why=CNT)),
    ("r4-ps-alias-abbrev", "PowerShell",
     R4_PS_GH + "Set-Alias -N g -Va $x; " + R4_PROD, _d(why=CNT)),
    ("r4-ps-alias-switch", "PowerShell",
     R4_PS_GH + "Set-Alias -Force g $x; " + R4_PROD, _d(why=CNT)),
    ("r4-ps-new-alias-abbrev", "PowerShell",
     "New-Alias -Na g -Val gh; " + R4_PROD, _d(why=CNT)),
    ("r4-ps-alias-provider-switch", "PowerShell",
     R4_PS_GH + "Set-Item -Force alias:g $x; " + R4_PROD, _d(why=CNT)),
    ("r4-ps-new-item-alias-name", "PowerShell",
     "New-Item -Path alias: -Name g -Value gh; " + R4_PROD, _d(why=CNT)),
    ("r4-ps-new-item-alias-abbrev", "PowerShell",
     R4_PS_GH + "New-Item -Path alias: -N g -Value $x; " + R4_PROD,
     _d(why=CNT)),
    ("r4-ps-alias-path-backslash", "PowerShell",
     "Set-Item alias:\\g gh; " + R4_PROD, _d(why=CNT)),
    ("r4-ps-module-qualified-alias", "PowerShell",
     R4_PS_GH + "Microsoft.PowerShell.Utility\\Set-Alias g $x; " + R4_PROD,
     _d(why=CNT)),
    ("r4-alias-then-dispatch-prod", "Bash", "alias g=gh; " + R4_PROD,
     _d(why=CNT)),
    ("r4-alias-quoted-both", "Bash",
     "alias g='gh workflow'; g run deploy-prod.yml", _d(why=CNT)),
    # gh behind a wrapper inside the alias's value.
    ("r4-alias-wrapped-gh", "Bash", "alias g='env gh'; " + R4_PROD,
     _d(why=CNT)),
    ("r4-alias-then-hole-verb", "Bash", "alias g=gh; g $W run deploy-prod.yml",
     _d(why=CNT)),
    ("r4-hash-p-copy", "Bash", "hash -p /usr/bin/gh g; " + R4_PROD,
     _d(why=CNT)),
    ("r4-source-procsub", "Bash",
     "source <(echo gh workflow run deploy-prod.yml)", _d(why=CNT)),
]

R4_MUST_ALLOW_DEPLOY = [
    ("r4-alias-then-echo", "Bash", "alias g=gh; echo workflow", _d(log=None)),
    ("r4-alias-then-echo-dispatches", "Bash", "alias g=gh; echo dispatches",
     _d(log=None)),
    ("r4-alias-then-other-gh", "Bash", "alias g=gh; g pr list", _d(log=None)),
    ("r4-alias-other-target", "Bash", "alias ll=ls; ll workflow run notes",
     _d(log=None)),
    ("r4-hash-then-echo", "Bash", "hash -p /usr/bin/gh g; echo workflow",
     _d(log=None)),
    ("r4-ps-alias-then-echo", "PowerShell", "Set-Alias g gh; echo workflow",
     _d(log=None)),
    ("r4-ps-new-item-alias-then-echo", "PowerShell",
     "New-Item -Path alias: -Name g -Value gh; echo workflow", _d(log=None)),
    # `saps` is Start-Process: its full names are trusted, not refused.
    ("r4-ps-saps-full-params-other", "PowerShell",
     "saps -FilePath $exe -WindowStyle Hidden -ArgumentList 'notes.txt'",
     _d(log=None)),
    ("r4-ps-launcher-switch-no-dispatch", "PowerShell",
     "Start-Process notepad -Wait -ArgumentList 'notes.txt'", _d(log=None)),
    # A switch bound to a constant is not a word made at run time.
    ("r4-ps-launcher-colon-true-no-dispatch", "PowerShell",
     "Start-Process notepad -Wait:$true -ArgumentList 'notes.txt'",
     _d(log=None)),
    ("r4-ps-full-params-other", "PowerShell",
     "Start-Process -FilePath $exe -WindowStyle Hidden -ArgumentList "
     "'notes.txt'", _d(log=None)),
]

R4_ASK_DEPLOY = [
    ("r4-ask-ps-switch-before-target", "PowerShell",
     R4_PS_GH + "Start-Process -NoNewWindow $x -ArgumentList " + R4_ARG,
     _d(cnt=True)),
    ("r4-ask-ps-abbrev-filepath", "PowerShell",
     R4_PS_GH + "Start-Process -Fi $x -ArgumentList " + R4_ARG, _d(cnt=True)),
    # The accepted cost: a run-time target and a switch ask, though this one
    # may send nothing.
    ("r4-ask-ps-switch-runtime-other", "PowerShell",
     "Start-Process $exe -Wait -ArgumentList 'notes.txt'", _d(cnt=True)),
    ("r4-ask-ps-alias-literal-switch", "PowerShell", "Set-Alias g gh -Force",
     _d(cnt=True)),
]

# --- T-0009 review round 5 (Codex, head cc754aa0) ----------------------------
# Two dispatches the literal reading leaves unknown; a bash alias or `hash -p`
# counts for the commands AFTER it (unless a loop, a function or a trap runs
# earlier text later), its VALUE's command decides, not any word in it; and a
# PowerShell comma inside one whole single-quoted word is literal.
R5_COMMA = {"nonProd": ["staging,*"] + DEPLOY_NONPROD, "workflows": WORKFLOWS}
R5_HASH = "hash -p /usr/bin/gh g"

R5_MUST_BLOCK_DEPLOY = [
    ("r5-two-unknown-dispatches", "Bash",
     "gh workflow run; gh workflow run deploy.yml", _d(pu=True, why="unknown")),
    ("r5-two-unknown-reversed", "Bash",
     "gh workflow run deploy.yml; gh workflow run", _d(pu=True, why="unknown")),
    ("r5-two-unknown-api", "Bash",
     f"gh api -X POST {DISPATCH}/deploy.yml/dispatches; gh workflow run",
     _d(pu=True, why="unknown")),
    # Text a loop, a function or a trap runs AFTER the alias or `hash -p`.
    ("r5-loop-hash-after", "Bash",
     "for i in 1 2; do " + R4_PROD + "; " + R5_HASH + "; done", _d(why=CNT)),
    ("r5-while-alias-after", "Bash",
     "while true; do " + R4_PROD + "; alias g=gh; done", _d(why=CNT)),
    ("r5-function-hash-after", "Bash",
     "function f { " + R4_PROD + "; }; " + R5_HASH + "; f", _d(why=CNT)),
    ("r5-trap-hash-after", "Bash",
     "trap '" + R4_PROD + "' EXIT; " + R5_HASH, _d(why=CNT)),
    ("r5-trap-alias-before", "Bash",
     "alias g=gh; trap '" + R4_PROD + "' EXIT", _d(why=CNT)),
    # The alias's value is text bash reads again: its last command runs with
    # the words after the name, through the wrappers `_unwrap` knows.
    ("r5-alias-dollar-value", "Bash", "alias g='$x'; " + R4_PROD, _d(why=CNT)),
    ("r5-alias-dq-dollar", "Bash", 'alias g="$x"; ' + R4_PROD, _d(why=CNT)),
    ("r5-alias-command-gh", "Bash", "alias g='command gh'; " + R4_PROD,
     _d(why=CNT)),
    ("r5-alias-assign-gh", "Bash", "alias g='GH_TOKEN=x gh'; " + R4_PROD,
     _d(why=CNT)),
    ("r5-alias-last-command-gh", "Bash", "alias g='cd /tmp; gh'; " + R4_PROD,
     _d(why=CNT)),
    # A bare comma is a PowerShell array; quotes joined by one are two words.
    ("r5-ps-comma-bare", "PowerShell",
     "gh workflow run deploy.yml -f environment=staging,west",
     _d(environments=R5_COMMA, why=CNT)),
    ("r5-ps-comma-quoted-array", "PowerShell",
     "gh workflow run deploy.yml -f 'environment=staging','west'",
     _d(environments=R5_COMMA, why=CNT)),
]

R5_MUST_ALLOW_DEPLOY = [
    ("r5-alias-after-dispatch-word", "Bash", R4_PROD + "; alias g=gh",
     _d(log=None)),
    ("r5-hash-after-dispatch-word", "Bash", R4_PROD + "; " + R5_HASH,
     _d(log=None)),
    ("r5-alias-echo-gh", "Bash", "alias g='echo gh'; " + R4_PROD, _d(log=None)),
    ("r5-alias-gh-then-echo", "Bash", "alias g='gh pr list; echo'; " + R4_PROD,
     _d(log=None)),
    ("r5-ps-comma-quoted", "PowerShell",
     "gh workflow run deploy.yml -f 'environment=staging,west'",
     _d(environments=R5_COMMA, log="env:nonProd:staging,west")),
    ("r5-ps-comma-quoted-api", "PowerShell",
     f"gh api -X POST {DISPATCH}/deploy.yml/dispatches -f ref=main "
     "-f 'inputs[environment]=staging,west'",
     _d(environments=R5_COMMA, log="env:nonProd:staging,west")),
    ("r5-bash-comma-quoted", "Bash",
     "gh workflow run deploy.yml -f 'environment=staging,west'",
     _d(environments=R5_COMMA, log="env:nonProd:staging,west")),
]

MUST_BLOCK_DEPLOY += R2_MUST_BLOCK_DEPLOY + GRAMMAR_MUST_BLOCK \
    + R3_MUST_BLOCK_DEPLOY + R4_MUST_BLOCK_DEPLOY + R5_MUST_BLOCK_DEPLOY
MUST_ALLOW_DEPLOY += GRAMMAR_MUST_ALLOW + R3_MUST_ALLOW_DEPLOY \
    + R4_MUST_ALLOW_DEPLOY + R5_MUST_ALLOW_DEPLOY
ASK_DEPLOY += GRAMMAR_ASK + R3_ASK_DEPLOY + R4_ASK_DEPLOY

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


_INVISIBLE_IN_NAMES = ["\u2028", "\u2029", "\u0085", "\u202e", "\u2066",
                       "\u200b", "\ufeff", "\u00a0", "\x7f"]


@pytest.mark.parametrize("name", ["Deploy{}Staging", "CI{}Checks"])
@pytest.mark.parametrize("char", _INVISIBLE_IN_NAMES,
                         ids=lambda c: f"U+{ord(c):04X}")
def test_r6_an_invisible_character_in_a_workflow_name_is_unknown(name, char):
    """Round-6 self-check: a single-quoted workflow name carrying a line or
    paragraph separator, a C1 control, a bidi or zero-width format character
    or a non-ASCII blank is not a name crew can read. It looks like a listed
    name (or like an unlisted one) and lands on the guard.log row verbatim,
    so it is `unknown`, never `unlisted` or a listed workflow's class."""
    envs = dict(_CONTRACT_ENVS, workflows=NAMED)
    text = "gh workflow run '" + name.format(char) + "'"
    got, why, scope = crew_guards.dispatch_answer(text, "bash", envs)
    assert got == "unknown", (got, why, scope)
    assert why


@pytest.mark.parametrize("name,state", [
    ("Deploy Staging", "nonProd"), ("CI Checks", "unlisted"),
    ("D\u00e9ploiement", "unlisted"), ("Deploy-\u00c9t\u00e9", "unlisted"),
])
def test_r6_a_printable_workflow_name_still_reads(name, state):
    """must-allow for the test above: an ASCII blank and printable
    non-ASCII letters are still a readable name."""
    envs = dict(_CONTRACT_ENVS, workflows=NAMED)
    got, why, scope = crew_guards.dispatch_answer(
        "gh workflow run '" + name + "'", "bash", envs)
    assert got == state, (got, why, scope)


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


@pytest.mark.parametrize("shell,text", [
    ("bash", "X=g; X+=h; Y=work; Y+=flow; $X $Y run deploy-prod.yml"),
    ("bash", 'X=g; X+=h; Y=work; Y+=flow; C="$X $Y run deploy-prod.yml"; $C'),
    ("bash", "echo gh | xargs -I CMD CMD workflow run deploy-prod.yml"),
    ("bash", "echo gh | parallel {} workflow run deploy-prod.yml"),
    ("bash", "echo gh | parallel {1} workflow run deploy-prod.yml"),
    ("powershell", R3_PS_GH + "Start-Process $x -ArgumentList " + R3_ARG),
    ("powershell", R3_PS_GH + "Set-Alias g $x; g workflow run deploy-prod.yml"),
    ("powershell", "$w = 'work'+'flow'; gh $w run deploy-prod.yml"),
], ids=["hole-both-words", "hole-whole-command", "xargs-placeholder",
        "parallel-placeholder", "parallel-numbered", "ps-start-process",
        "ps-alias", "ps-hole-arg"])
def test_r3_a_run_time_command_word_is_could_not_tell(shell, text):
    """Round 3: `dispatch_answer` reads a command word made at run time by the
    shape of its argv -- the hole standing for any words -- not by whether
    the raw line mentions gh or `workflow`."""
    got, why, scope = crew_guards.dispatch_answer(text, shell, _CONTRACT_ENVS)
    assert got == "unknown", (got, why, scope)
    assert (scope or {}).get("op") == "line-not-literal", scope


def test_r3_the_xargs_placeholder_is_the_deploy_guards():
    """Round 3 FIX: `xargs -I CMD CMD workflow run ...` is a dispatch the
    guard could not tell, not cloudGuard's unconditional unreadable finding:
    no gated tool but gh has a `workflow run` or a `dispatches` endpoint."""
    envs = dict(_CONTRACT_ENVS, engaged=True)
    findings = cloud_guard.scan(
        "bash", "echo gh | xargs -I CMD CMD workflow run deploy-prod.yml",
        ctx={"dispatch": envs, "engaged": True})
    assert [f.rule for f in findings] == ["deployWorkflow"], findings
    assert findings[0].scope["op"] == "line-not-literal", findings[0].scope
    other = cloud_guard.scan("bash", "echo gh | xargs -I CMD CMD destroy",
                             ctx={"dispatch": envs, "engaged": True})
    assert [f.rule for f in other] == ["cloudGuard"], other
    both = cloud_guard.scan(
        "bash", "echo gh | xargs -I CMD CMD workflow run deploy-prod.yml; "
        "echo terraform | xargs -I T T destroy",
        ctx={"dispatch": envs, "engaged": True})
    assert sorted(f.rule for f in both) == ["cloudGuard", "deployWorkflow"], \
        both


@pytest.mark.parametrize("block", [{"prodUnattended": "yes"}, None, [],
                                   {"workflows": 1}],
                         ids=["string-bool", "null", "list", "workflows-int"])
def test_r3_a_malformed_global_block_is_a_problem(tmp_path, monkeypatch,
                                                   block):
    """Round 3 BLOCK 3: a malformed MACHINE-GLOBAL `environments` block makes
    every dispatch "could not tell", as a malformed repo block does. The
    terraform layer keeps T-0005's reading of the global layer (its
    `prod-unattended-string` row: the normaliser holds a string down), so
    `problem` and `resolve_mode` are unchanged and only `dispatchProblem`
    carries it."""
    repo = tcg._fixture(tmp_path, {"guards": {"cloudGuard": "report"},  # pylint: disable=protected-access
                                   "environments": DEPLOY_ENVS},
                        {"environments": block})
    monkeypatch.setattr(crew_config, "GLOBAL_CONFIG_PATH",
                        str(tmp_path / "home" / ".claude" / "crew"
                            / "config.json"))
    envs = cloud_guard.environments_config(str(repo))
    assert "global" in envs["dispatchProblem"], envs
    assert envs["problem"] == "", envs
    state, why, scope = crew_guards.dispatch_answer(S_RUN, "bash", envs)
    assert (state, scope["op"]) == ("unknown", "line-not-literal"), why
    assert "global" in why, why
    assert cloud_guard.resolve_mode(str(repo))[0] == "report"


def test_r3_a_well_formed_global_block_is_not_a_problem(tmp_path, monkeypatch):
    repo = tcg._fixture(tmp_path, {"guards": {"cloudGuard": "report"},  # pylint: disable=protected-access
                                   "environments": DEPLOY_ENVS},
                        {"environments": {"prodUnattended": False}})
    monkeypatch.setattr(crew_config, "GLOBAL_CONFIG_PATH",
                        str(tmp_path / "home" / ".claude" / "crew"
                            / "config.json"))
    envs = cloud_guard.environments_config(str(repo))
    assert envs["dispatchProblem"] == "", envs
    assert crew_guards.dispatch_answer(S_RUN, "bash", envs)[0] == "nonProd"


def test_r3_a_fed_command_word_on_the_classify_road():
    """`_classify` hands `dispatch_answer` a text the lexer already unwrapped
    from `parallel`, with `fed` naming its placeholders: a `{1}` command word
    there is quoted by `dispatch_text`, so the reader sees no brace, and only
    the fed-placeholder rule makes it the hole it is."""
    text = crew_guards.dispatch_text(["{1}", "workflow", "run",
                                      "deploy-prod.yml"])
    state, why, scope = crew_guards.dispatch_answer(
        text, "bash", _CONTRACT_ENVS, ("parallel", ("{}",)))
    assert (state, (scope or {}).get("op")) == ("unknown", "line-not-literal"), \
        (state, why, scope)


# `_PS_FULL_PARAMS`, measured with pwsh 7 on this host (2026-09-27): each
# cmdlet's non-switch parameters, minus the common parameters and
# `RedirectStandardInput` (gh's stdin, which crew never reads).
R4_MEASURED = {
    "start-process": ("-argumentlist", "-credential", "-environment",
                      "-filepath", "-redirectstandarderror",
                      "-redirectstandardoutput", "-verb", "-windowstyle",
                      "-workingdirectory"),
    "set-alias": ("-description", "-name", "-option", "-scope", "-value"),
    "new-alias": ("-description", "-name", "-option", "-scope", "-value"),
}
_R4_PS_PARAMS = (
    "$c = [System.Management.Automation.PSCmdlet]::CommonParameters; "
    "(Get-Command {cmd}).Parameters.Values | ? {{ $_.ParameterType -ne "
    "[switch] -and $c -notcontains $_.Name }} | % Name")


def test_r4_ps_full_params_match_powershell(tmp_path):
    """The launcher rule's table is what PowerShell itself reports, where
    pwsh is on the host; the docstring's measurement stands in otherwise."""
    for cmd, names in R4_MEASURED.items():
        assert crew_guards._PS_FULL_PARAMS[cmd] == frozenset(names), cmd  # pylint: disable=protected-access
    pwsh = crew_fixtures.resolve_pwsh()
    if pwsh is None:
        pytest.skip("no pwsh on this host: R4_MEASURED is the record")
    # Its own home (round 6): conftest already gave this test its own
    # XDG_CACHE_HOME; HOME and USERPROFILE are the rest of what pwsh reads.
    env = dict(os.environ, HOME=str(tmp_path), USERPROFILE=str(tmp_path))
    for cmd, names in R4_MEASURED.items():
        out = subprocess.run(
            [pwsh, "-NoProfile", "-c", _R4_PS_PARAMS.format(cmd=cmd)],
            capture_output=True, text=True, encoding="utf-8",
            errors="strict", timeout=120, check=True, env=env).stdout
        got = {"-" + n.strip().lower() for n in out.split()} \
            - {"-redirectstandardinput"}
        assert got == set(names), (cmd, sorted(got))


# --- review round 5: the marker over every dispatch judged ------------------

R5_TWO = "gh workflow run a.yml; gh workflow run b.yml"
R5_TWO_ENVS = {"nonProd": ["staging"], "workflows": {"a.yml": "production",
                                                     "b.yml": "staging"}}


def test_r5_a_marker_covers_every_dispatch_judged():
    """Round 5 BLOCK 2: `dispatch_answer`'s scope for a line of two dispatches
    keys its marker on BOTH classified dispatches, so a config edit that
    reclassifies the lower-ranked one inside the TTL is a different key."""
    envs = dict(_CONTRACT_ENVS, **R5_TWO_ENVS)
    state, why, scope = crew_guards.dispatch_answer(R5_TWO, "bash", envs)
    before = crew_guards.dispatch_marker_key(R5_TWO, dict(scope, state=state,
                                                          why=why))
    envs["workflows"] = {"a.yml": "production", "b.yml": "production"}
    state, why, scope = crew_guards.dispatch_answer(R5_TWO, "bash", envs)
    after = crew_guards.dispatch_marker_key(R5_TWO, dict(scope, state=state,
                                                         why=why))
    assert state == "prod", (state, why)
    assert before != after


def test_r5_an_approval_does_not_survive_a_second_dispatchs_remap(tmp_path):
    """Round 5 BLOCK 2, through the hook: approve the two-dispatch line, then
    make its nonProd dispatch production inside the TTL -- denied."""
    case = ("r5-marker", "Bash", R5_TWO,
            _d(environments=R5_TWO_ENVS, why="production"))
    repo, result = _run("python", tmp_path, case)
    assert result[0] == "deny", result
    open(_deny_marker(result[1]), "w", encoding="utf-8").close()  # pylint: disable=consider-using-with
    result = tcg.run_hook("python", tmp_path, "Bash", R5_TWO,
                          extra_env=dict(UNATTENDED))
    assert result[0] == "allow", result
    _write_workflows(repo, {"a.yml": "production", "b.yml": "production"})
    result = tcg.run_hook("python", tmp_path, "Bash", R5_TWO,
                          extra_env=dict(UNATTENDED))
    assert result[0] == "deny", result


def test_r5_two_unknown_dispatches_do_not_crash_the_scan():
    """Round 5 BLOCK 1: the gate compares its rows sorted, and a row holds
    None where no workflow is named -- `scan` must not raise."""
    envs = dict(_CONTRACT_ENVS, engaged=True)
    for text in ("gh workflow run; gh workflow run deploy.yml",
                 "gh workflow run deploy.yml; gh workflow run"):
        findings = [f for f in cloud_guard.scan("bash", text,
                                                ctx={"dispatch": envs})
                    if f.rule == "deployWorkflow"]
        assert [f.scope["state"] for f in findings] == ["unknown"] * 2, text

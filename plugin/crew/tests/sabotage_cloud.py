"""The crew 1.0 T5 cloud/destructive guard mutations, appended to
`sabotage.py`'s MUTATIONS the way `sabotage_review.py`'s are, and kept apart
for the same reason: `sabotage.py` sits at `.pylintrc`'s max-module-lines. Run
that file, not this one.

One mutation per rule the guard enforces, plus its must-allow edges, the
switch, and the two wrappers' fail-closed fallback. All were run through this
harness's own apply/restore on 2026-09-23 (30 of 30 red), with each target
also copied aside with `cp` first and compared with `diff` afterwards. The
review-round-1 mutations were added later the same day and run by hand the
same way -- every entry in this tuple, old and new, mutated, its aimed test
run, restored with `cp` and checked with `diff`: all red. The review-round-2
entries (marked below) were run by hand the same way, each one alone. Three
earlier drafts came back STILL GREEN and were fixed rather than dropped: two
comment cases with no `;` inside (so reading a comment as code changed
nothing), and a `-f` mutation that a second pattern already covered. Most aim
at the `_python` driver because it runs in seconds; the bash and pwsh drivers
share its case tables.
"""
import os

CREW = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(CREW, "hooks", "scripts")
GUARD = os.path.join(SCRIPTS, "cloud_guard.py")
GUARD_SH = os.path.join(SCRIPTS, "cloud-guard.sh")
GUARD_PS1 = os.path.join(SCRIPTS, "cloud-guard.ps1")
GATE_PS1 = os.path.join(SCRIPTS, "verify-gate.ps1")
CONFIG = os.path.join(SCRIPTS, "crew_config.py")
# The allowlist's word-level helpers (T-0005 Step 8) live beside the guards.
GUARDS = os.path.join(SCRIPTS, "crew_guards.py")

_T = "tests/test_cloud_guard.py::"
_BLOCK = _T + "test_must_block_python"
_ALLOW = _T + "test_must_allow_python"
_IDENT = _T + "test_identity_python"
# Since T-0005 Step 8 the literal-word allowlist denies most unusual
# terraform lines by itself, so a mutation to the lexer shows only where the
# lexer is judged alone. The five retargeted here came back STILL GREEN (or
# unproven) against `_BLOCK` in the full run on 2026-09-26.
_LEXED = _T + "test_the_lexer_still_judges_every_must_block_case"

CLOUD_GUARD_MUTATIONS = (
    ("cloud guard: terraform destroy no longer recognised", GUARD,
     '    if sub in ("apply", "destroy"):\n',
     '    if sub in ("apply",):\n', _BLOCK),
    # Not the literal `-f` in the tuple beside it: that one is subsumed by
    # this pattern, and deleting it alone stayed green -- measured.
    ("cloud guard: clustered short flags (-uf) no longer a force push", GUARD,
     'if re.match(r"^-[a-zA-Z]*f[a-zA-Z]*$", arg):',
     'if re.match(r"^-[a-zA-Z]*F[a-zA-Z]*$", arg):', _BLOCK),
    ("cloud guard: gh pr merge --admin no longer recognised", GUARD,
     'if ("pr", "merge") in pairs and "--admin" in args:',
     'if ("pr", "merge") in pairs and "--admin-x" in args:', _BLOCK),
    ("cloud guard: aws terminate-* no longer destructive", GUARD,
     '_AWS_DESTRUCTIVE_PREFIXES = ("delete-", "terminate-", "purge-")',
     '_AWS_DESTRUCTIVE_PREFIXES = ("delete-", "purge-")', _BLOCK),
    ("cloud guard: az ... delete no longer destructive", GUARD,
     '    return word in ("delete", "purge") or',
     '    return word in ("purge",) or', _BLOCK),
    ("cloud guard: SQL DROP no longer destructive", GUARD,
     '_SQL_WORDS_RE = re.compile(r"\\b(drop|truncate)\\b"',
     '_SQL_WORDS_RE = re.compile(r"\\b(truncate)\\b"', _BLOCK),
    ("cloud guard: mysql read under the standard dialect", GUARD,
     '"mysql": ("mysql", "mysql-no-escapes"),',
     '"mysql": ("standard",),', _BLOCK),
    ("cloud guard: SQL string literals no longer stripped", GUARD,
     '        if c in "\'\\"":\n            escapes = ',
     '        if False:\n            escapes = ', _ALLOW),
    ("cloud guard: heredoc bodies no longer read", GUARD,
     '            if pending:\n                i = _read_heredocs(',
     '            if False:\n                i = _read_heredocs(', _BLOCK),
    ("cloud guard: bash $( ) inside quotes no longer scanned", GUARD,
     '            k, closed = _bash_close(text, j + 1)\n'
     '            subs.append(text[j + 2:k])\n',
     '            k, closed = _bash_close(text, j + 1)\n', _LEXED),
    ("cloud guard: bash ; & | no longer split commands", GUARD,
     '            finish(pipe=c == "|")\n',
     '            add(c)\n', _BLOCK),
    ("cloud guard: PowerShell script blocks no longer split", GUARD,
     '        if c in "{}":\n', '        if c in "":\n', _LEXED),
    ("cloud guard: sudo no longer unwrapped", GUARD,
     '        if head == "sudo":\n', '        if head == "sudo-x":\n', _BLOCK),
    ("cloud guard: env X=Y no longer unwrapped", GUARD,
     '        if head == "env":\n', '        if head == "env-x":\n', _BLOCK),
    ("cloud guard: bash comments judged as commands", GUARD,
     '            i = k + 1\n            continue\n'
     '        if c == "#" and state["word"] is None:\n',
     '            i = k + 1\n            continue\n'
     '        if False:\n', _ALLOW),
    ("cloud guard: PowerShell comments judged as commands", GUARD,
     '            i = n if j < 0 else j + 2\n            continue\n'
     '        if c == "#" and state["word"] is None:\n',
     '            i = n if j < 0 else j + 2\n            continue\n'
     '        if False:\n', _ALLOW),
    ("cloud guard: an unpinned AWS profile is let through", GUARD,
     '            if not _matches(ident["name"], profiles):\n',
     '            if False:\n', _IDENT),
    ("cloud guard: an unpinned Azure subscription is let through", GUARD,
     '    if _matches(ident["name"], subs) or (',
     '    if True or (', _IDENT),
    ("cloud guard: destructive with nothing pinned is not unknown", GUARD,
     '            if finding.destructive:\n'
     '                return "unknown", ("nothing is pinned in cloud.awsProfiles',
     '            if False:\n'
     '                return "unknown", ("nothing is pinned in cloud.awsProfiles',
     _IDENT),
    ("cloud guard: an unknown identity asks even unattended", GUARD,
     '        if decision == "ask" and alone:\n',
     '        if False:\n', _IDENT),
    ("cloud guard: bypassPermissions counted as attended", GUARD,
     '    return mode in ("bypassPermissions", "dontAsk")',
     '    return False',
     _T + "test_ask_is_denied_when_nobody_is_attending"),
    ("cloud guard: unreadable pins read as nothing pinned", GUARD,
     '    if problem:\n        return "unknown", f"crew could not read',
     '    if False:\n        return "unknown", f"crew could not read',
     _T + "test_malformed_pins_make_every_cloud_identity_unknown"),
    ("cloud guard: production.databases no longer consulted", GUARD,
     '        out.append(Finding("prodDatabase", text, head, None, False, '
     'None))\n',
     '', _T + "test_production_database_patterns_are_wired"),
    ("cloud guard: ships ON (the off switch ignored)", GUARD,
     '    if mode == "off":\n', '    if False:\n',
     _T + "test_disabled_guard_allows_everything"),
    ("cloud guard: report mode enforces", GUARD,
     '    if mode == "report":\n', '    if False:\n',
     _T + "test_report_mode_refuses_nothing_and_logs_what_it_would_have"),
    ("cloud guard: a corrupt config no longer fails closed", GUARD,
     '    if "corrupt" in (repo_state, global_state):\n',
     '    if False:\n', _T + "test_a_corrupt_config_fails_closed"),
    ("cloud guard: prints allow (skipping the user's own prompt)", GUARD,
     '    if decision not in ("allow", None):\n',
     '    if True:\n', _ALLOW),
    # Review round 1 (Codex), one per finding fixed, each aimed at the case
    # that was the wrong answer before the fix.
    ("cloud guard: unknown read-only identity passes with pins set", GUARD,
     '        if pinned_any:\n            return "unknown", ident["unknown"]\n',
     '        if False:\n            return "unknown", ident["unknown"]\n',
     _IDENT),
    ("cloud guard: nothing pinned makes read-only calls unknown", GUARD,
     '        return UNPINNED, ident["unknown"]\n',
     '        return "unknown", ident["unknown"]\n', _IDENT),
    ("cloud guard: the unpinned pass is never reported", GUARD,
     '    if not whats or os.path.exists(marker):\n',
     '    if True or os.path.exists(marker):\n',
     _T + "test_unpinned_read_only_call_is_reported_once"),
    ("cloud guard: nesting past MAX_DEPTH passes unread", GUARD,
     '    if depth > MAX_DEPTH:\n', '    if depth > MAX_DEPTH + 99:\n',
     _BLOCK),
    ("cloud guard: only the stage next door feeds a pipe", GUARD,
     'if not w.startswith("-"))\n    return cmd.stdin\n',
     'if not w.startswith("-"))\n    return None\n', _BLOCK),
    ("cloud guard: xargs/parallel unwrapped as plain wrappers", GUARD,
     '            if head in _ARGV_FEEDERS:\n                if fed is not None:',
     '            if head in ():\n                if fed is not None:',
     _BLOCK),
    ("cloud guard: an xargs placeholder read as a literal word", GUARD,
     'if not w.startswith("-") and not carries(w)]\n',
     'if not w.startswith("-") and "{" not in w]\n', _BLOCK),
    ("cloud guard: xargs git push treated as known", GUARD,
     '        if sub and seen([sub]) and sub != "push":\n',
     '        if sub and seen([sub]):\n', _BLOCK),
    ("cloud guard: xargs terraform fmt refused", GUARD,
     '        if words and seen(words[:1]) and words[0] in _TF_READ_ONLY:\n',
     '        if False:\n', _ALLOW),
    ("cloud guard: az parsing stops at the first option", GUARD,
     '        if arg.startswith("-"):\n            continue\n'
     '        path.append(arg.lower())\n',
     '        if arg.startswith("-"):\n            break\n'
     '        path.append(arg.lower())\n', _BLOCK),
    ("cloud guard: `bash -c --` runs `--`", GUARD,
     '        if arg == "--":\n            index += 1\n            break\n',
     '        if arg == "--":\n            break\n', _LEXED),
    ("cloud guard: report mode resolves to allow", GUARD,
     '        worst, reason = None, ""\n', '        worst, reason = "allow", ""\n',
     _T + "test_report_mode_evaluates_to_no_decision"),
    ("cloud guard: malformed input passes an armed guard", GUARD,
     '    if problem:\n        # Armed, and handed something',
     '    if False:\n        # Armed, and handed something',
     _T + "test_malformed_input_is_refused_when_armed"),
    ("cloud guard: a malformed cloud block leaves report mode as is", GUARD,
     '    if mode != "off" and crew_config.layer_state(repo_path, cloud=True)',
     '    if False and crew_config.layer_state(repo_path, cloud=True)',
     _T + "test_a_malformed_cloud_block_fails_closed_when_armed"),
    ("crew_config: a malformed cloud block validates as ok", CONFIG,
     '    if cloud and "cloud" in parsed and',
     '    if False and "cloud" in parsed and',
     _T + "test_layer_state_classifies_a_malformed_cloud_block"),
    # The PostgreSQL E'' reading has no mutation of its own since round 2:
    # the `postgres-escapes` reading escapes inside EVERY '...', E'' strings
    # included, so disabling the E'' rule alone stays green -- measured. The
    # mutation that removes that reading is below.
    ("cloud guard: psql read as MySQL", GUARD,
     '_SQL_DIALECT = {"psql": ("postgres", "postgres-escapes"),',
     '_SQL_DIALECT = {"psql": ("mysql",),', _ALLOW),
    ("cloud guard: sqlcmd read as MySQL", GUARD,
     '"sqlcmd": ("tsql",), "invoke-sqlcmd": ("tsql",),',
     '"sqlcmd": ("mysql",), "invoke-sqlcmd": ("tsql",),', _ALLOW),
    ("cloud guard: aws --dry-run destructive", GUARD,
     '    if dry and dry[-1] in ("--dry-run", "--dryrun"):\n',
     '    if False:\n', _ALLOW),
    ("cloud guard: terraform apply -help destructive", GUARD,
     '    if _tf_help_requested(args):\n', '    if False:\n', _ALLOW),
    ("cloud guard: Remove-Az* -WhatIf destructive", GUARD,
     '        if _whatif_requested(args):\n', '        if False:\n', _ALLOW),
    # Review round 2 (Codex), one or more per finding fixed, each aimed at
    # the case that was the wrong answer before the fix.
    ("cloud guard: a quoted -WhatIf read as the parameter", GUARD,
     '        if not isinstance(arg, _Bare) \\\n'
     '                or arg.lower() not in ("-whatif", "-whatif:$true"):\n',
     '        if arg.lower() not in ("-whatif", "-whatif:$true"):\n', _BLOCK),
    ("cloud guard: -WhatIf after a valued parameter still exempt", GUARD,
     '        if ":" in prev or prev.lower() in _AZPS_SWITCHES:\n'
     '            return True\n    return False\n',
     '        return True\n    return False\n', _BLOCK),
    ("cloud guard: PowerShell lexer marks every word bare", GUARD,
     '        state["bare"] = state["bare"] and bare\n',
     '        state["bare"] = True\n', _BLOCK),
    ("cloud guard: xargs executable placeholder not checked", GUARD,
     '    if carries(argv[0]) or "$" in argv[0] or "`" in argv[0] \\\n'
     '            or not _LITERAL_EXE_RE.match(argv[0]):\n',
     '    if not _LITERAL_EXE_RE.match(argv[0]):\n', _BLOCK),
    ("cloud guard: xargs executable shape not checked", GUARD,
     '            or not _LITERAL_EXE_RE.match(argv[0]):\n',
     '            or False:\n', _BLOCK),
    ("cloud guard: xargs -I lost behind a valued option", GUARD,
     '        index += 2 if arg in takes else 1\n    return tuple(',
     '        index += 1\n    return tuple(', _BLOCK),
    ("cloud guard: BSD xargs -J not a placeholder", GUARD,
     '        if arg in ("-I", "-J") and index + 1 < len(args):\n',
     '        if arg in ("-I",) and index + 1 < len(args):\n', _BLOCK),
    ("cloud guard: mysql read without NO_BACKSLASH_ESCAPES", GUARD,
     '"mysql": ("mysql", "mysql-no-escapes"),',
     '"mysql": ("mysql",),', _BLOCK),
    ("cloud guard: psql read without standard_conforming_strings off", GUARD,
     '                dialect == "postgres-escapes" and c == "\'") or (\n',
     '                False) or (\n', _BLOCK),
    ("cloud guard: MariaDB /*M! read as a comment", GUARD,
     'mysql and sql.startswith(("/*!", "/*M!"), i)):',
     'mysql and sql.startswith(("/*!",), i)):', _BLOCK),
    ("cloud guard: any --dry-run exempts, negation ignored", GUARD,
     '    if dry and dry[-1] in ("--dry-run", "--dryrun"):\n',
     '    if {"--dry-run", "--dryrun"} & set(dry):\n', _BLOCK),
    ("cloud guard: any -help token exempts terraform", GUARD,
     '    if _tf_help_requested(args):\n',
     '    if _HELP_FLAGS.intersection(args):\n', _BLOCK),
    ("cloud guard: an unknown terraform option cannot own -help", GUARD,
     '            if name not in _TF_BOOL_OPTS:\n                return False\n',
     '            if False:\n                return False\n', _BLOCK),
    ("cloud guard: bash stands down for Bash on Windows (OS-based)", GUARD,
     '        return tool_name == "PowerShell" \\\n',
     '        return tool_name in ("PowerShell", "Bash") \\\n',
     _T + "test_bash_wrapper_flavour_guard"),
    ("cloud guard: bash stands down for PowerShell off Windows", GUARD,
     '            and environ.get("OS") == "Windows_NT" \\\n',
     '            and True \\\n', _T + "test_bash_wrapper_flavour_guard"),
    ("cloud guard: the .ps1 judges Bash calls too (twice on Windows)", GUARD,
     '        return tool_name == "Bash"\n',
     '        return False\n', _T + "test_pwsh_wrapper_judges_by_tool"),
    ("cloud guard: the .ps1 stands down for PowerShell calls too", GUARD,
     '        return tool_name == "Bash"\n',
     '        return True\n', _T + "test_pwsh_wrapper_judges_by_tool"),
    ("cloud-guard.sh: no longer names its own flavour", GUARD_SH,
     'CREW_CLOUD_GUARD_FLAVOUR=bash PYTHONUTF8=1',
     'PYTHONUTF8=1', _T + "test_bash_wrapper_flavour_guard"),
    ("cloud-guard.ps1: no longer names its own flavour", GUARD_PS1,
     "  $env:CREW_CLOUD_GUARD_FLAVOUR = 'powershell'\n", "",
     _T + "test_pwsh_wrapper_judges_by_tool"),
    ("cloud guard: the unpinned note is dropped with no .crew/", GUARD,
     '    if not whats or os.path.exists(marker):\n',
     '    if not whats or os.path.exists(marker) \\\n'
     '            or not os.path.isdir(os.path.dirname(marker)):\n',
     _T + "test_unpinned_note_is_said_even_with_no_crew_dir"),
    ("cloud-guard.sh: no python + armed no longer fails closed", GUARD_SH,
     '    exit 2\n  fi\n  exit 0\nfi\n', '    exit 0\n  fi\n  exit 0\nfi\n',
     _T + "test_bash_wrapper_without_python"),
    ("cloud-guard.ps1: no python + armed no longer fails closed", GUARD_PS1,
     '    exit 2\n  }\n  exit 0\n}\n', '    exit 0\n  }\n  exit 0\n}\n',
     _T + "test_pwsh_wrapper_without_python"),
    ("verify-gate.ps1: pinned list drifts from PINNED_VARS", GATE_PS1,
     '"AZURE_SUBSCRIPTION_ID",\n                   "ARM_SUBSCRIPTION_ID", ',
     '"AZURE_SUBSCRIPTION_ID",\n                   ',
     _T + "test_pinned_vars_are_one_list_in_all_three_places"),
)

# T-0005 (crew 1.0.42): the environment layer and the destroy rule. Each entry
# names the case it must turn red, and every aimed case was built so that the
# value the mutation collapses to would ALLOW -- a must-block whose collapsed
# value also denies cannot go red. Each was run alone by hand first (target
# copied aside, mutated, aimed test run, restored, compared with `cmp`), then
# through this harness.
GUARDS = os.path.join(SCRIPTS, "crew_guards.py")
TFPLAN = os.path.join(SCRIPTS, "crew_tfplan.py")
_E = "tests/test_cloud_guard_environments.py::"
_EB = _E + "test_must_block_env_python"
_EP = _E + "test_must_block_allow_policy_python"
_EA = _E + "test_must_allow_env_python"

CLOUD_GUARD_MUTATIONS += (
    ("cloud guard env: every environment classifies nonProd", GUARD,
     "    return ENV_NONPROD if _matches(value, globs) else ENV_PROD\n",
     "    return ENV_NONPROD\n", _EB + "[prod-saved-plan]"),
    ("cloud guard env: the destroy check is gone (saved-plan deletes)", GUARD,
     '    if destroy != "no":\n        return "ask", (f"{head}, and this is',
     '    if False:\n        return "ask", (f"{head}, and this is',
     _EB + "[nonprod-plan-deletes]"),
    ("cloud guard env: the destroy check is gone (terraform destroy)", GUARD,
     '    if destroy != "no":\n        return "ask", (f"{head}, and this is',
     '    if False:\n        return "ask", (f"{head}, and this is',
     _EB + "[nonprod-destroy]"),
    ("cloud guard env: a destroy under `allow` runs (pre-1.0.42)", GUARD,
     '        if destroy in ("yes", "unknown"):\n',
     "        if False:\n", _EP + "[allow-destroy]"),
    ("cloud guard env: destroy unknown read as no under `allow`", GUARD,
     '        if destroy in ("yes", "unknown"):\n',
     '        if destroy in ("yes",):\n', _EP + "[allow-no-plan-apply]"),
    ("cloud guard env: an unknown environment collapses to prod", GUARD,
     '        return ENV_UNKNOWN, None, "; ".join(unknown)\n',
     '        return ENV_PROD, None, "; ".join(unknown)\n',
     _EB + "[unknown-no-signal]"),
    ("cloud guard env: an unknown environment collapses to nonProd", GUARD,
     '        return ENV_UNKNOWN, None, "; ".join(unknown)\n',
     '        return ENV_NONPROD, None, "; ".join(unknown)\n',
     _EB + "[unknown-variable]"),
    ("cloud guard env: a missing workspace file reads as `default`", GUARD,
     '    except FileNotFoundError:\n'
     '        return "workspace file", None, (f"{path} does not exist',
     '    except FileNotFoundError:\n'
     '        return "workspace file", "default", (f"{path} does not exist',
     _EB + "[unknown-no-signal]"),
    ("cloud guard env: a cd no longer turns the file fallback off", GUARD,
     '    if state.get("cd"):\n        return None, ("a cd/pushd',
     '    if False:\n        return None, ("a cd/pushd', _EB + "[unknown-cd]"),
    ("cloud guard env: conflicting signals resolve as nonProd", GUARD,
     "    if len(classes) > 1:\n        return ENV_UNKNOWN, None,",
     "    if len(classes) > 1:\n        return ENV_NONPROD, None,",
     _EB + "[unknown-conflict]"),
    ("cloud guard env: a missing sidecar reads as no deletes", GUARD,
     '    except FileNotFoundError:\n'
     '        return DESTROY_UNKNOWN, (f"no summary exists',
     '    except FileNotFoundError:\n'
     '        return DESTROY_NO, "", {}\n'
     '        return DESTROY_UNKNOWN, (f"no summary exists',
     _EB + "[nonprod-no-sidecar]"),
    ("cloud guard env: a malformed sidecar reads as no deletes", GUARD,
     "    problem = sidecar_problem(sidecar)\n    if problem:\n",
     "    problem = sidecar_problem(sidecar)\n    if False:\n",
     _EB + "[nonprod-malformed-sidecar]"),
    ("cloud guard env: the sidecar is found without its sha256", GUARD,
     '    sidecar_path = os.path.join(root, ".crew", "tfplan", digest + ".json")\n',
     '    sidecar_path = os.path.join(root, ".crew", "tfplan", sorted(\n'
     '        os.listdir(os.path.join(root, ".crew", "tfplan")))[0])\n',
     _EB + "[nonprod-stale-sidecar]"),
    ("cloud guard env: an apply with no saved plan destroys nothing", GUARD,
     '    if not operands:\n        return DESTROY_UNKNOWN, ("no saved plan',
     '    if not operands:\n        return DESTROY_NO, ("no saved plan',
     _EB + "[nonprod-no-plan-apply]"),
    ("cloud guard env: `apply -replace` is not a destroy", GUARD,
     '    if "replace" in flags:\n', "    if False:\n",
     _EB + "[nonprod-replace]"),
    ("cloud guard env: `workspace delete` is not a destroy", GUARD,
     '    if op == "ws-delete":\n        return DESTROY_YES,',
     '    if op == "ws-delete":\n        return DESTROY_NO,',
     _EB + "[nonprod-workspace-delete]"),
    ("cloud guard env: `workspace` read-only again behind xargs", GUARD,
     '                           "state", "test", "login", "logout"))\n',
     '                           "state", "test", "login", "logout",\n'
     '                           "workspace"))\n', _EB + "[prod-xargs]"),
    ("cloud guard env: the environment layer loosens `block`", GUARD,
     '    if out["policy"] == "block":\n        return "deny"',
     '    if out["policy"] == "block-x":\n        return "deny"',
     _EB + "[block-not-loosened]"),
    ("cloud guard env: prodUnattended read from the repo alone", GUARD,
     '    out["prodUnattended"] = crew_config.resolve_ratcheted(\n'
     '        root, "environments.prodUnattended")["effective"] is True\n',
     '    out["prodUnattended"] = crew_state.load_config(root).get(\n'
     '        "environments", {}).get("prodUnattended") is True\n',
     _EB + "[prod-repo-only-unattended]"),
    ("crew_guards: the ratchet takes the WIDER layer (prodUnattended)", GUARDS,
     "    return tiers[min(rank(repo_value), rank(global_value))]",
     "    return tiers[max(rank(repo_value), rank(global_value))]",
     "tests/test_crew_config.py::test_prod_unattended_ratchets"),
    ("crew_guards: prodUnattended normalised by truthiness", GUARDS,
     "    return value if isinstance(value, bool) else False\n",
     "    return bool(value)\n", _EB + "[prod-unattended-string]"),
    ("cloud guard env: a malformed environments block reads as empty", GUARD,
     '            out = {"nonProd": [], "problem": problem}\n',
     '            out = {"nonProd": [], "problem": ""}\n',
     _EB + "[unknown-malformed-block]"),
    ("cloud guard env: no payload cwd falls back to the project root", GUARD,
     '    envs["cwd"] = cwd if isinstance(cwd, str) and cwd else None\n',
     '    envs["cwd"] = cwd if isinstance(cwd, str) and cwd else root\n',
     _EB + "[unknown-no-cwd]"),
    ("cloud guard env: workspace creation judged with the layer off", GUARD,
     '                and (op == "ws-delete" or engaged):\n',
     '                and True:\n',
     _E + "test_workspace_new_is_not_judged_until_environments_is_configured"),
    ("cloud guard env: a malformed environments block leaves report as is",
     GUARD,
     '    if mode != "off" and crew_config.layer_state(\n'
     '            repo_path, environments=True) == "corrupt":\n',
     '    if False and crew_config.layer_state(\n'
     '            repo_path, environments=True) == "corrupt":\n',
     _E + "test_a_malformed_environments_block_forces_block_mode"),
    ("crew_tfplan: a failed `show` is summarised as no deletes", TFPLAN,
     "    if show.returncode != 0:\n"
     '        return 2, f"`{binary} show -json {plan}` exited {show.returncode}"\n',
     "    if show.returncode != 0:\n"
     "        show.stdout = b'{\"resource_changes\": []}'\n",
     "tests/test_crew_tfplan.py::test_show_failure_writes_nothing"),
    # The must-allow side: a suite that allows nothing passes every
    # must-block, so these prove the allows are real.
    ("cloud guard env: the sidecar sha never matches", GUARD,
     '    sidecar_path = os.path.join(root, ".crew", "tfplan", digest + ".json")\n',
     '    sidecar_path = os.path.join(root, ".crew", "tfplan", digest + "x.json")\n',
     _EA + "[nonprod-saved-plan]"),
    ("cloud guard env: every `workspace new` read as a destroy", GUARD,
     '    if op in ("ws-new", "ws-create"):\n        return DESTROY_NO, "", None\n',
     '    if op in ("ws-new", "ws-create"):\n        return DESTROY_YES, "", None\n',
     _EA + "[nonprod-workspace-new]"),
)

# T-0005 review round 1 (T-0005-Wajyct): three BLOCK and three FIX, each a
# measured bypass. Every entry was run alone by hand first, then here.
_R1 = _E + "test_round1_must_block_python"
_CH = _E + "test_chdir_forms_mark_the_directory_unknown"
_OP = _E + "test_an_environment_change_crew_cannot_read_is_unknown"
_WB = _E + "test_wrapper_value_options_do_not_hide_the_command"
# Two of those went STILL GREEN at review round 5: a misread wrapper value
# now makes the line unseen and the gate denies it by itself, so they aim at
# the lexer judged alone.
_WBL = _E + "test_the_lexer_alone_reads_the_wrapped_command"
_SP = _E + "test_a_special_file_is_unknown_not_a_hang"
_TP = "tests/test_crew_tfplan.py::"

CLOUD_GUARD_MUTATIONS += (
    # BLOCK :1222 -- the plan rewritten in the same command.
    ("cloud guard r1: a saved plan trusted beside other commands", GUARD,
     '    if state.get("commands", 0) != 1 or state.get("writes"):\n',
     '    if state.get("writes"):\n', _R1 + "[rewrite-plan-destroy]"),
    ("cloud guard r1: an output redirect no longer distrusts the plan", GUARD,
     '    if state.get("commands", 0) != 1 or state.get("writes"):\n',
     '    if state.get("commands", 0) != 1:\n',
     _R1 + "[rewrite-redirect-append]"),
    ("cloud guard r1: a redirect-only command is dropped", GUARD,
     "        return bool(self.words) or self.stdin is not None or self.writes\n",
     "        return bool(self.words) or self.stdin is not None\n",
     _R1 + "[rewrite-redirect-only]"),
    # Red on the REASON: before the fix `>&file` left the file as a second
    # operand, which was already refused as "not one literal path".
    ("cloud guard r1: `>&file` read as an fd duplication", GUARD,
     '                elif i == j and op == ">&":\n'
     '                    state["redirect"] = ">"\n',
     '                elif False:\n'
     '                    state["redirect"] = ">"\n',
     _R1 + "[rewrite-redirect-both]"),
    ("cloud guard r1: a PowerShell redirect is not a write", GUARD,
     '                if word.lower() != "$null":\n'
     "                    cmd.writes = True\n",
     '                if False:\n'
     "                    cmd.writes = True\n",
     _R1 + "[rewrite-ps-redirect]"),
    # BLOCK :841 / :1514 -- directory changes the hook did not see.
    ("cloud guard r1: env -C/-CDIR no longer moves the directory", GUARD,
     '                elif name in ("C", "chdir"):\n',
     '                elif name in ("chdir",):\n', _R1 + "[env-C-attached]"),
    ("cloud guard r1: env --chdir=DIR no longer moves the directory", GUARD,
     '                elif name in ("C", "chdir"):\n',
     '                elif name in ("C",):\n', _R1 + "[env-chdir-equals]"),
    ("cloud guard r1: sudo -D no longer moves the directory", GUARD,
     '_SUDO_MOVES = frozenset(("D", "chdir", "R", "chroot", "i", "login"))\n',
     '_SUDO_MOVES = frozenset(("chdir", "R", "chroot", "i", "login"))\n',
     _R1 + "[sudo-D-attached]"),
    ("cloud guard r1: sudo -R no longer moves the directory", GUARD,
     '_SUDO_MOVES = frozenset(("D", "chdir", "R", "chroot", "i", "login"))\n',
     '_SUDO_MOVES = frozenset(("D", "chdir", "chroot", "i", "login"))\n',
     _R1 + "[sudo-chroot]"),
    ("cloud guard r1: sudo -R/-T values read as the command", GUARD,
     '_SUDO_SHORT = dict({letter: "req" for letter in "aCcDgpRrTtUu"}, h="opt")\n',
     '_SUDO_SHORT = dict({letter: "req" for letter in "aCcDgprtUu"}, h="opt")\n',
     _WBL + "[sudo-timeout-value]"),
    ("cloud guard r1: env -S'cmd' hides the command again", GUARD,
     '                elif name in ("S", "split-string"):\n'
     '                    split = (value or "").split()\n',
     '                elif False:\n'
     '                    split = (value or "").split()\n',
     _WB + "[env-S-attached]"),
    ("cloud guard r1: env -a VALUE read as the command", GUARD,
     '_ENV_SHORT = {"C": "req", "S": "req", "u": "req", "a": "req",\n',
     '_ENV_SHORT = {"C": "req", "S": "req", "u": "req",\n',
     _WBL + "[env-argv0]"),
    ("cloud guard r1: wsl --cd / ~ no longer move the directory", GUARD,
     '            if flag == "~" or flag.split("=", 1)[0] == "--cd":\n',
     "            if False:\n", _CH + "[wsl-cd-infra-terraform-apply-p-tfplan]"),
    ("cloud guard r1: pwsh -WorkingDirectory no longer moves it", GUARD,
     "        if ctx is not None and _pwsh_moves(args):\n",
     "        if False:\n",
     _CH + "[powershell-wd-infra-c-terraform-apply-p-tfpl]"),
    ("cloud guard r1: parallel --wd no longer moves the directory", GUARD,
     '                    o.split("=", 1)[0] in ("--wd", "--workdir") for o in '
     "opts):\n",
     '                    o.split("=", 1)[0] in () for o in opts):\n',
     _CH + "[parallel-wd-infra-terraform-apply-p-tfplan]"),
    ("cloud guard r1: .NET CurrentDirectory no longer moves it", GUARD,
     '    if head in _CD_HEADS or "currentdirectory" in low:\n',
     '    if head in _CD_HEADS:\n',
     _CH + "[IO-Directory-SetCurrentDirectory-infra-terra]"),
    ("cloud guard r1: `source` no longer moves the directory", GUARD,
     '    if argv[0] in ("source", ".") or (shell == "powershell"\n',
     '    if False or (shell == "powershell"\n',
     _CH + "[source-env-sh-terraform-apply-p-tfplan]"),
    # FIX crew_tfplan.py:103 -- the plan's own workspace, and the hook's
    # reading of an environment it cannot see.
    ("crew_tfplan r1: the workspace is not read from the plan", TFPLAN,
     "    name = plan_workspace(data)\n", '    name = "staging"\n',
     _TP + "test_the_workspace_comes_from_the_plan_not_the_selected_one"),
    ("cloud guard r1: a summary naming no workspace is no signal", GUARD,
     '                signals.append(("the saved plan\'s workspace", None,\n'
     '                                "the plan summary names no workspace the "\n'
     '                                "plan is bound to"))\n',
     "                pass\n", _EB + "[sidecar-unbound]"),
    ("cloud guard r1: an unreadable environment keeps TF_WORKSPACE", GUARD,
     '    if state.get("opaque"):\n        return "TF_WORKSPACE", None,',
     '    if False:\n        return "TF_WORKSPACE", None,',
     # Not the `source` case: a sourced file also moves the directory, so
     # the file fallback is off there anyway -- measured green.
     _OP + "[export-cat-prod-env-terraform-apply-p-tfplan]"),
    ("cloud guard r1: an `||` chain no longer makes it unknown", GUARD,
     "    if cmd.or_next:\n        ctx[\"opaque\"] = True\n",
     "    if False:\n        ctx[\"opaque\"] = True\n",
     _OP + "[terraform-workspace-select-qa-true-terraform]"),
    ("cloud guard r1: an env: provider write is read as nothing", GUARD,
     '        w.lower().lstrip("${").startswith("env:") for w in argv)\n',
     '        w.lower().lstrip("${").startswith("\\0") for w in argv)\n',
     _OP + "[Set-Item-env-TF-WORKSPACE-production-terrafo]"),
    ("cloud guard r1: SetEnvironmentVariable is read as nothing", GUARD,
     '    if "setenvironmentvariable" in low:\n', "    if False:\n",
     _OP + "[Environment-SetEnvironmentVariable-TF-WORKSP]"),
    ("cloud guard r1: a dynamic export is read as nothing", GUARD,
     '                    if ctx is not None and ("$" in word or "`" in word):\n',
     "                    if False:\n",
     _OP + "[export-cat-prod-env-terraform-apply-p-tfplan]"),
    # FIX :1218 -- only regular files are opened. T-0080 measured: constant
    # memory (the plan is hashed in 1 MiB blocks, peak 58 MiB); the test's own
    # 30 s ceiling is what fails it.
    ("cloud guard r1: a FIFO or device is opened as a plan", GUARD,
     "    return stat.S_ISREG(mode)\n", "    return True\n",
     # Not the FIFO case: the non-blocking open makes a FIFO read as empty
     # (so unknown) even without the type check -- measured green. A device
     # that never ends is what only the type check stops.
     _SP + "[plan-dev-zero]"),
    # FIX :1535 -- `workspace delete` in every armed state.
    ("cloud guard r1: workspace delete judged only when engaged", GUARD,
     '                and (op == "ws-delete" or engaged):\n',
     "                and engaged:\n", _R1 + "[delete-block]"),
    ("cloud guard r1: xargs workspace delete judged only when engaged",
     GUARD,
     '            if wsub in ("new", "select") and not (ctx or {}).get("engaged"):\n',
     '            if not (ctx or {}).get("engaged"):\n',
     _R1 + "[delete-xargs-allow]"),
    # Neighbours: PowerShell's eval fed from the pipeline, and the other file
    # the command can point the hook at (AZURE_CONFIG_DIR).
    ("cloud guard r1: pipeline-fed iex no longer unknown", GUARD,
     '            if ctx is not None and not payload.strip():\n',
     "            if False:\n",
     _OP + "[Get-Content-prod-ps1-iex-terraform-apply-p-t]"),
    # T-0080: the unbounded reader (json.load on /dev/zero). It grew one
    # python3 to ~20 GB before sabotage_bound's per-entry RLIMIT_AS; under the
    # 4096 MiB default it goes RED on the test's "unknown" assertion (peak 3.7 GiB).
    ("cloud guard r1: azureProfile.json opened whatever it is", GUARD,
     "        data = json.loads(_read_small(path, _AZ_PROFILE_MAX_BYTES)\n"
     '                          .decode("utf-8-sig"))\n',
     '        with open(path, encoding="utf-8-sig") as handle:\n'
     "            data = json.load(handle)\n",
     _E + "test_a_special_azure_profile_is_unknown_not_a_hang[zero]"),
)

# T-0005 review round 2 (T-0005-env-terraform--lt3l0F): one BLOCK (a
# substitution in an unquoted heredoc body was never counted as a command),
# the terragrunt workspace wrappers, and PowerShell's `2>&1`. Run on
# 2026-09-26 through this harness's own apply/restore with MUTATIONS filtered
# to these entries (each restore checked against its pre-run digest): 11 of
# 11 red, then again in the full run.
_R2 = _E + "test_round2_must_block_python"
_R2A = _E + "test_round2_must_allow_python"

CLOUD_GUARD_MUTATIONS += (
    ("cloud guard r2: an unquoted heredoc's substitutions not counted", GUARD,
     "        if not quoted:\n            _expansion_subs(body, subs)\n",
     "        if False:\n            _expansion_subs(body, subs)\n",
     _R2 + "[r2-heredoc-subst]"),
    ("cloud guard r2: a quoted heredoc delimiter read as unquoted", GUARD,
     '                pending.append((value, redirect == "<<-", state["cur"],\n'
     "                                quoted))\n",
     '                pending.append((value, redirect == "<<-", state["cur"],\n'
     "                                False))\n",
     _E + "test_the_command_count_covers_heredoc_substitutions"),
    ("cloud guard r2: a heredoc's backslash-newline not joined", GUARD,
     "        if joins and trailing % 2 and i < n:\n",
     "        if False:\n", _LEXED + "[heredoc-continued-delimiter]"),
    ("cloud guard r2: a CR delimiter line read only as the end", GUARD,
     '            if check.rstrip("\\r") == delim:\n'
     "                alt, j = [line], i\n",
     '            if check.rstrip("\\r") == delim:\n'
     "                break\n",
     # Not the hook case any more: since round 3 `scan` re-reads every CR
     # line whole, which judges `[heredoc-cr-delimiter]` without this rule
     # -- measured STILL GREEN. The lexer-level check is this rule's alone.
     _E + "test_a_cr_heredoc_delimiter_is_read_both_ways_by_the_lexer"),
    ("cloud guard r2: ${...} no longer scanned for substitutions", GUARD,
     "            _expansion_subs(text[i + 2:k], subs)\n", "",
     _R2 + "[r2-param-default]"),
    ("cloud guard r2: $((...)) no longer scanned for substitutions", GUARD,
     "            _expansion_subs(text[i + 3:k], subs)\n", "",
     _R2 + "[r2-arith-nested]"),
    ("cloud guard r2: $((cmd) ) read as arithmetic", GUARD,
     '    return text[m + 1:m + 2] == ")"\n', "    return True\n",
     _R2 + "[r2-comsub-subshell]"),
    ("cloud guard r2: terragrunt workspace wrappers not recognised", GUARD,
     '            head == "terragrunt" or sub in ("run-all", "run")):\n',
     "            False):\n", _R2 + "[tg-run-all-delete-allow]"),
    ("cloud guard r2: a terragrunt valued option hides workspace", GUARD,
     '            head == "terragrunt" or sub in ("run-all", "run")):\n',
     '            sub in ("run-all", "run")):\n',
     _R2 + "[tg-valued-option-delete-allow]"),
    ("cloud guard r2: PowerShell 2>&1 split at the & again", GUARD,
     '            if state["word"] is not None and state["bare"] \\\n',
     '            if False and state["bare"] \\\n', _R2A + "[r2-ps-2-to-1]"),
    ("cloud guard r2: a quoted '2>' merged as a redirection", GUARD,
     '            if state["word"] is not None and state["bare"] \\\n',
     '            if state["word"] is not None \\\n',
     _R2 + "[r2-ps-quoted-redirect]"),
)

# T-0005 review round 3 (T-0005-env-terraform--ICP8KT): the lexer read
# `"${x:-"'"}"` as a string ending at the inner quote (BLOCK + FIX :214),
# `\r#` as a comment (FIX :444), and the first `workspace` word as
# terragrunt's subcommand (FIX :1419). The fix is a class -- bash's own
# delimiting, a fail-closed count wherever crew is unsure, a re-read of the
# text the other way -- so each piece has its own mutation, aimed at the
# case only that piece decides: the fail-closed count at a control
# character (no re-read happens there), the re-read at a heredoc inside
# `$( )` (the matcher cannot delimit it), the lexer pieces at the lexer.
_R3 = _E + "test_round3_must_block_python"

CLOUD_GUARD_MUTATIONS += (
    ("cloud guard r3: a doubt no longer counts a command (fail-open)", GUARD,
     "    if unsure and ctx is not None:\n",
     "    if False:\n", _R3 + "[r3q-vt-before-semicolon]"),
    ("cloud guard r3: a doubt no longer re-reads the rest", GUARD,
     '        if alt and alt.strip() and not state["reread"]:\n',
     "        if False:\n", _R3 + "[r3-comsub-heredoc-paren]"),
    ("cloud guard r3: quoting inside ${...} is no doubt", GUARD,
     '            if not closed or _PARAM_HARD_RE.search(text[i + 2:k]):\n',
     "            if not closed:\n",
     _E + "test_hostile_quoting_counts_an_extra_command[r3q-dq-in-param-bare]"),
    ("cloud guard r3: \"${...}\" ends at its own inner quote", GUARD,
     '        if text.startswith("${", j):\n'
     "            # Its own quotes do not end the string",
     "        if False:\n"
     "            # Its own quotes do not end the string",
     _E + "test_double_quoted_param_is_one_word"),
    ("cloud guard r3: $'...' read as a plain '...' when delimiting", GUARD,
     "        elif text.startswith(\"$'\", i):\n"
     "            skip = _skip_ansi_c(text, i)\n",
     "        elif False:\n"
     "            skip = _skip_ansi_c(text, i)\n",
     _E + "test_bash_close_reads_like_bash[${x:-$'\\\\''}; y }-1-want0]"),
    ("cloud guard r3: a CR line read only with CR as a blank", GUARD,
     '            subs.extend((text.replace("\\r", "\\x01"), '
     'text.replace("\\r", "")))\n',
     "            pass\n", _R3 + "[r3-cr-hash-destroy]"),
    ("cloud guard r3: a target-less redirection takes the next head", GUARD,
     '        if state["redirect"] is not None:\n'
     "            # A redirection with no target",
     "        if False:\n"
     "            # A redirection with no target",
     _E + "test_a_redirection_without_a_target_does_not_take_the_next_command"),
    ("cloud guard r3: terragrunt reads only its first `workspace`", GUARD,
     '                 for index, word in enumerate(args) if word == "workspace"]\n',
     '                 for index, word in enumerate(args) if word == "workspace"]'
     "[:1]\n", _R3 + "[r3-tg-working-dir-workspace]"),
    ("cloud guard r3: PowerShell typographic quotes read as letters", GUARD,
     '.replace("\\r", "\\n").translate(_PS_QUOTES)\n',
     '.replace("\\r", "\\n")\n', _R3 + "[r3-ps-smart-single]"),
    ("cloud guard r3: a PowerShell bare CR read as a blank", GUARD,
     '    out = text.replace("\\r\\n", "\\n").replace("\\r", "\\n")',
     '    out = text.replace("\\r\\n", "\\n")', _R3 + "[r3-ps-cr-line]"),
)

# T-0005 Step 8 (successor plan after review round 4, bl77wS): the
# literal-word allowlist. A line naming terraform, terragrunt or tofu is
# judged only when every word is a plain literal; anything else is "could not
# tell". One mutation per property the plan names: the gate exists, `$` is
# not plain, the gate reads the raw text rather than the lexer's words, and a
# quote cannot hide the name. Each aims at a row that is ALLOWED without the
# property (measured at 8ae0ddee), not one merely missing a reason word.
_S8 = _E + "test_literal_must_block_python"

CLOUD_GUARD_MUTATIONS += (
    ("cloud guard step 8: the allowlist gate dropped", GUARD,
     "    gated = _literal_gate(shell, text) if depth == 0 else None\n",
     "    gated = None\n", _S8 + "[s8-r4-heredoc-locale-delim]"),
    ("cloud guard step 8: `$` allowed in a plain literal", GUARDS,
     '_PLAIN_WORD_RE = re.compile(r"^[A-Za-z0-9_./:=@%+,-]+$")',
     '_PLAIN_WORD_RE = re.compile(r"^[A-Za-z0-9_./:=@%+,$-]+$")',
     _S8 + "[s8-dollar-only-subcommand]"),
    ("cloud guard step 8: the allowlist run on the lexer's words", GUARD,
     "    findings = [gated] if gated is not None else []\n",
     "    findings = [g for g in [_literal_gate(shell, ' '.join(\n"
     "        w for c in cmds for w in c.words))] if g is not None]\n",
     _S8 + "[s8-r4-heredoc-locale-delim]"),
    # Retargeted at Step 9: the command-word reader now dequotes
    # `'terraform'` itself, so this reading matters where the trigger falls
    # back to it (measured: STILL GREEN on `s8-quoted-name-and-ansi` after
    # Step 9). Retargeted again at round 5, from `s9-find-exec` to the
    # reader's give-up: `find -exec` is now read by the reader too.
    ("cloud guard step 8: a quote hides the terraform name", GUARDS,
     "                bare = re.sub(r\"['\\\"`]\", \"\", bare)\n",
     "                bare = bare\n",
     _E + "test_command_word_must_block_python[s9-case]"),
)

# T-0005 Step 9 (successor plan: gate on the command being run). The trigger
# reads the COMMAND WORD, so each branch that can make one terraform gets a
# mutation, aimed at a row only that branch gates. Rows spelled with `plan`
# carry no verb, so the argument-pair fallback cannot mask a lost wrapper or
# redirection; rows the lexer also denies go red on the reason (`why` is the
# gate's "plain literal"). The plan named `env -i terraform destroy` for the
# wrapper mutation, but every word of it is plain, so the lexer judges it and
# the gate's answer never shows: that mutation aims at `s9-env-quoted-plan`.
_S9 = _E + "test_command_word_must_block_python"
_S9A = _E + "test_command_word_must_allow_python"

CLOUD_GUARD_MUTATIONS += (
    ("cloud guard step 9: the gate triggered by any word again", GUARD,
     "        found = command_trigger(text, _GATE_HELPERS)\n",
     "        named = __import__(\"crew_guards\").names_terraform(text, "
     "shell)\n"
     "        found = None if named is None else (named, False)\n",
     _S9A + "[s9a-commit-message]"),
    ("cloud guard step 9: the gate run at every depth again", GUARD,
     "    gated = _literal_gate(shell, text) if depth == 0 else None\n",
     "    gated = _literal_gate(shell, text)\n", _S9A + "[s9a-commit-heredoc]"),
    ("cloud guard step 9: wrapper stripping dropped", GUARDS,
     '    argv = unwrap(argv, {}, fed, {"cd": False})\n',
     "    argv = list(argv)\n", _S9 + "[s9-env-quoted-plan]"),
    ("cloud guard step 9: a redirection target read as a word", GUARDS,
     '                if state["target"]:\n'
     '                    state["target"] = False\n'
     "                else:\n"
     "                    words.append(value)\n",
     '                state["target"] = False\n'
     "                words.append(value)\n", _S9 + "[s9-redirect-plan]"),
    ("cloud guard step 9: an fd number read as a word", GUARDS,
     r'_FD_WORD_RE = re.compile(r"^(?:\d+|\{[A-Za-z_][A-Za-z0-9_]*\})$")',
     r'_FD_WORD_RE = re.compile(r"^(?!)$")', _S9 + "[s9-fd-redirect-plan]"),
    ("cloud guard step 9: an unknown command word never gated", GUARDS,
     "        named = _verb_on_line(top)\n"
     "        return None if named is None else (named, True)\n",
     "        return None\n", _S9 + "[s9-variable-name]"),
    ("cloud guard step 9: `bash -c` payload not read", GUARDS,
     "            return _bash_trigger(positional[0], top, helpers, "
     "depth + 1,\n                                 line)\n",
     "            return None\n",
     _T + "test_could_not_tell_is_refused_under_block"
     "[was-bash-c-dashdash-taint]"),
    ("cloud guard step 9: a shell reading stdin not gated", GUARDS,
     '        named = names_terraform(top, "bash")\n'
     "        return None if named is None else (named, True)\n"
     "    if head in _GATE_PWSH:\n",
     "        return None\n    if head in _GATE_PWSH:\n",
     _S9 + "[s9-pipe-to-shell]"),
    ("cloud guard step 9: `pwsh -c` payload not read", GUARDS,
     "            return None if named is None else (named, True)\n"
     "        return ps_trigger(ps_normalise(payload)[0], helpers, depth + 1)\n",
     "            return None if named is None else (named, True)\n"
     "        return None\n", _S9 + "[s9-pwsh-c]"),
    ("cloud guard step 9: `eval` payload not read", GUARDS,
     '        return _bash_trigger(" ".join(args), top, helpers, depth + 1, '
     "line)\n", "        return None\n", _S9 + "[s9-eval]"),
    ("cloud guard step 9: a command word that is a script not read", GUARDS,
     '        return _bash_trigger(" ".join(argv), top, helpers, depth + 1, '
     "line)\n", "        return None\n", _S9 + "[s9-watch-string]"),
    ("cloud guard step 9: script runners read as programs", GUARDS,
     "    if head in _GATE_OPAQUE:\n", "    if False:\n", _S9 + "[s9-ssh]"),
    ("cloud guard step 9: the reader's give-up gates nothing", GUARDS,
     '        named = names_terraform(text, "bash") or '
     'names_terraform(top, "bash")\n'
     "        return None if named is None else (named, True)\n",
     "        return None\n", _S9 + "[s9-case]"),
    ("cloud guard step 9: `$(...)` commands dropped", GUARDS,
     '            self.pos += 2\n            self.read(")")\n'
     "            return _HOLE\n",
     '            self.pos += 2\n            kept = list(self.cmds)\n'
     '            self.read(")")\n            self.cmds[:] = kept\n'
     "            return _HOLE\n", _S9 + "[s9-commit-subst-destroy]"),
    ("cloud guard step 9: backquoted commands dropped", GUARDS,
     '        _GateReader("".join(body), self.depth + 1, self.cmds).read()\n',
     '        _GateReader("".join(body), self.depth + 1, []).read()\n',
     _S9 + "[s9-commit-backtick-destroy]"),
    ("cloud guard step 9: an unquoted heredoc body's commands dropped",
     GUARDS, "            if not quoted:\n                _GateReader(",
     "            if quoted:\n                _GateReader(",
     _S9 + "[s9-commit-heredoc-subst]"),
    ("cloud guard step 9: a backslash-and-quote delimiter dequoted", GUARDS,
     "        mixed = \"\\\\\" in raw and (\"'\" in raw or '\"' in raw)\n",
     "        mixed = False\n",
     _S9 + "[s9-heredoc-backslash-quoted-delim]"),
    ("cloud guard step 9: a glob read as a literal", GUARDS,
     '                if state["glob"] and value not in ("[", "[["):\n'
     "                    value += _HOLE\n", "",
     _S9 + "[s9-short-glob-destroy]"),
    ("cloud guard step 9: a brace list read as a literal", GUARDS,
     '                if state["brace"] and value not in ("{", "}", "{}"):\n'
     "                    value += _HOLE\n", "",
     _E + "test_round5_must_block_python[r5-brace-name-taint]"),
    ("cloud guard step 9: an expansion read only as a wildcard", GUARDS,
     '" ".join((wild, opened, emptied))', '" ".join((wild, opened))',
     _S9 + "[s9-backquote-empty-prefix]"),
)

# T-0005 review round 5 (kF0AM1): the gate's answer kept where the lexer
# cannot follow the line (UNSEEN), and read-only subcommands and data
# commands no longer gated for their quoting. One mutation per new branch,
# plus the five Step 9 branches round 5 found untested (busybox, the `pwsh`
# expansion fallback, the control-character give-up, `_no_body_across`, and
# eval's expansion fallback -- removed as unreachable: an expansion is
# `_HOLE`, a control character, so the reader gives up on it first). Each
# aims at a row the mutation turns from deny to allow, or from allow to deny,
# or -- where the lexer denies it too -- at a row whose `why` names the gate.
_R5 = _E + "test_round5_must_block_python"
_R5A = _E + "test_round5_must_allow_python"

CLOUD_GUARD_MUTATIONS += (
    ("cloud guard r5: an unseen command on a plain line handed on", GUARD,
     "    elif unseen:\n", "    elif False:\n", _R5 + "[r5-flock]"),
    ("cloud guard r5: the unseen reason replaced by the quoting one", GUARD,
     '        if finding.scope.get("unseen"):\n', "        if False:\n",
     _E + "test_round5_unseen_reason_says_how_to_have_it_judged"),
    ("cloud guard r5: PowerShell never unseen", GUARDS,
     "    return hits[0][0], any(h[1] for h in hits)\n",
     "    return hits[0][0], False\n", _R5 + "[r5-ps-set-alias]"),
    ("cloud guard r5: PowerShell launchers not read", GUARDS,
     "    if opaque or head in _PS_LAUNCHERS or any(\n",
     "    if opaque or any(\n", _R5 + "[r5-ps-start-process]"),
    ("cloud guard r5: a PowerShell alias: drive write not read", GUARDS,
     '            w.lower().startswith(("alias:", "function:")) for w in '
     "args):\n", "            False for w in args):\n",
     _R5 + "[r5-ps-set-item-alias]"),
    ("cloud guard r5: a PowerShell path run with a verb not read", GUARDS,
     "    if head in copies and verb is not None and verb.lower() in "
     "_GATE_VERBS:\n", "    if False:\n", _R5 + "[r5-ps-copied-binary]"),
    ("cloud guard r5: a bash command run with a verb not read", GUARDS,
     '    if head in line["copies"] and verb is not None \\\n',
     "    if False and verb is not None \\\n", _R5 + "[r5-ln-dot-slash]"),
    ("cloud guard r5: a copied binary not noticed", GUARDS,
     '    line["copies"] |= _copies_terraform(cmds, helpers[4])\n',
     '    line["copies"] |= set()\n', _R5 + "[r5-cp-bare-name]"),
    ("cloud guard r5: a copy inside `bash -c` forgotten", GUARDS,
     '    line = {"copies": set()} if line is None else line\n',
     '    line = {"copies": set()}\n', _R5 + "[r5-nested-copy-bare-name]"),
    ("cloud guard r5: read-only subcommands gated again", GUARDS,
     "        return None if _tf_read_only(argv, fed) else (first, False)\n",
     "        return first, False\n", _R5A + "[r5a-plan-var]"),
    ("cloud guard r5: an xargs placeholder read as the subcommand", GUARDS,
     '    if any(head != "xargs" or any(r in word for r in reps for word in '
     "argv)\n",
     '    if any(head != "xargs"\n', _R5 + "[r5-xargs-replaced-subcommand]"),
    ("cloud guard r5: any option skipped before the subcommand", GUARDS,
     '    if "terragrunt" not in _head_name(argv[0]):\n'
     '        while rest and rest[0].startswith("-chdir="):\n',
     "    if True:\n"
     '        while rest and rest[0].startswith("-"):\n',
     _R5 + "[r5-terragrunt-option-before]"),
    ("cloud guard r5: zsh's =terraform as the command word ignored", GUARDS,
     "    if _zsh_names_tool(first):\n        return first, True\n", "",
     _R5 + "[r5-zsh-equals-taint]"),
    ("cloud guard r5: zsh's =terraform as an argument ignored", GUARDS,
     "    return _names_tool(word) or _zsh_names_tool(word)\n",
     "    return _names_tool(word)\n", _R5 + "[r5-zsh-copy-bare-name]"),
    ("cloud guard r5: find -exec not read", GUARDS,
     "        return _find_exec_trigger(args, top, helpers, depth, line)\n",
     "        return None\n", _R5 + "[r5-find-exec-found-binary]"),
    ("cloud guard r5: find -exec read line-wide again", GUARDS,
     "        return _find_exec_trigger(args, top, helpers, depth, line)\n",
     '        named = names_terraform(top, "bash")\n'
     "        return None if named is None else (named, True)\n",
     _R5A + "[r5a-find-exec-grep]"),
    ("cloud guard r5: a script runner read line-wide again", GUARDS,
     "        own = names_terraform(top if any(_HOLE in a for a in args)\n"
     '                              else " ".join(args), "bash")\n',
     '        own = names_terraform(top, "bash")\n',
     _R5A + "[r5a-source-then-plan]"),
    ("cloud guard r5: a script runner's run-time words not read", GUARDS,
     "        own = names_terraform(top if any(_HOLE in a for a in args)\n"
     '                              else " ".join(args), "bash")\n',
     '        own = names_terraform(" ".join(args), "bash")\n',
     _S9 + "[s9-source-procsub]"),
    ("cloud guard r5: a shell running a script file gated", GUARDS,
     "        if not has_c and positional and _HOLE not in positional[0] \\\n"
     "                and not _names_tool(positional[0]):\n",
     "        if False:\n", _R5A + "[r5a-bash-script-file]"),
    ("cloud guard r5: an unseen command after a followed one lost", GUARDS,
     "            found = found or hit[0]\n"
     "            unseen = unseen or hit[1]\n",
     "            found, unseen = hit\n            break\n",
     _R5 + "[r5-seen-apply-beside-unseen]"),
    ("cloud guard r5: `busybox sh` read as busybox", GUARDS,
     '    if head == "busybox" and args and head_name(args[0]) in '
     "_GATE_SHELLS:\n"
     "        head, args = head_name(args[0]), args[1:]\n", "",
     _R5 + "[r5-busybox-shell]"),
    ("cloud guard r5: a `pwsh -c` payload made at run time read", GUARDS,
     "        if payload is None or _HOLE in payload:\n",
     "        if payload is None:\n", _R5 + "[r5-pwsh-substituted-payload]"),
    ("cloud guard r5: a control character read as bash reads it", GUARDS,
     "        if _GATE_CONTROL_RE.search(text):\n"
     '            raise _Unsure("a control character")\n', "",
     _R5 + "[r5-cr-heredoc-delimiter]"),
    ("cloud guard r5: a quoted newline before a heredoc body read", GUARDS,
     '        if self.pending and "\\n" in self.text[start:end]:\n',
     "        if False:\n", _R5 + "[r5-quoted-newline-before-body]"),
)

# T-0005 Step 10 (round 6, dqPiSn): direct use only. The guard catches the
# direct spellings; a disguise the Exclusions name is documented, not
# detected. One mutation per new branch, each aimed at a row it turns from
# deny to allow or from allow to deny.
#
# Deleted with their code, not re-anchored: "an unknown wrapper's terraform
# argument ignored" (the fallback is gone), "every git subcommand read as
# data", "git's -C value read as its subcommand", "rg read as data despite
# --pre" and both "data command" entries (the data-command exemption existed
# only to narrow that fallback, and went with it), and "a container image's
# tag hides terraform" (image names were read only by the fallback). Their
# rows are in DOCUMENTED_NOT_CAUGHT. The PowerShell and copy entries above
# were re-anchored because their branches moved into `ps_trigger` and the
# named-copy rule, not deleted.
_S10 = _E + "test_direct_spelling_is_denied_unattended"
_S10A = _E + "test_ordinary_command_is_allowed"

CLOUD_GUARD_MUTATIONS += (
    ("cloud guard s10: no option value skipped before the subcommand",
     GUARDS, "        index += 2 if takes else 1\n", "        index += 1\n",
     _S10 + "[s10-tg-working-dir-destroy-ask]"),
    ("cloud guard s10: a known value option's verb-shaped value read as the "
     "subcommand", GUARDS,
     "            name in _TF_GLOBAL_VALUE_OPTS or nxt not in _TF_OPS\n",
     "            nxt not in _TF_OPS\n", _S10A + "[s10a-tg-dir-named-destroy]"),
    ("cloud guard s10: an unknown option takes no value", GUARDS,
     "            name in _TF_GLOBAL_VALUE_OPTS or nxt not in _TF_OPS\n"
     "            and not nxt.startswith(\"-\") and _HOLE not in nxt)\n",
     "            name in _TF_GLOBAL_VALUE_OPTS)\n",
     _S10 + "[s10-tg-unknown-option-value-ask]"),
    ("cloud guard s10: an unknown option takes the verb as its value", GUARDS,
     "            name in _TF_GLOBAL_VALUE_OPTS or nxt not in _TF_OPS\n",
     "            name in _TF_GLOBAL_VALUE_OPTS or True\n",
     _S10 + "[s10-tg-unknown-option-verb-ask]"),
    ("cloud guard s10: options after run-all not skipped", GUARD,
     "        index = _tf_skip_options(args, index + 1)\n",
     "        index += 1\n", _S10 + "[s10-tg-run-all-option-value-ask]"),
    ("cloud guard s10: PowerShell's `. terraform` not run by the lexer", GUARD,
     '            if words[0] == "." and len(words) > 1 and '
     "_head_name(words[1]) in _TF_HEADS:\n",
     "            if False:\n", _S10 + "[s10-ps-dot-ask]"),
    ("cloud guard s10: the unknown-wrapper fallback reinstated", GUARDS,
     "        named = names_terraform(top, \"bash\")\n"
     "        if named is not None:\n"
     "            return named, True\n"
     "    return None\n",
     "        named = names_terraform(top, \"bash\")\n"
     "        if named is not None:\n"
     "            return named, True\n"
     "    for index, arg in enumerate(args):\n"
     "        if _HOLE in arg or not _arg_names_tool(arg):\n"
     "            continue\n"
     "        rest = [a for a in args[index + 1:] if not a.startswith(\"-\")]\n"
     "        if rest and (_HOLE in rest[0] or rest[0].lower() in _GATE_VERBS):\n"
     "            return arg, True\n"
     "    return None\n", _S10A + "[s10a-rg-var]"),
    ("cloud guard s10: PowerShell gets the any-word trigger again", GUARD,
     "        found = ps_trigger(_ps_normalise(text)[0], _GATE_HELPERS)\n",
     "        named = __import__(\"crew_guards\").names_terraform(\n"
     "            _ps_normalise(text)[0], shell)\n"
     "        found = None if named is None else (named, False)\n",
     _S10A + "[s10a-ps-commit-message]"),
    ("cloud guard s10: PowerShell's read-only subcommands gated", GUARDS,
     "        return None if _tf_read_only(argv, []) else (first, False)\n",
     "        return first, False\n", _S10A + "[s10a-ps-output-raw]"),
    ("cloud guard s10: PowerShell's command word naming terraform ignored",
     GUARDS,
     "        return None if _tf_read_only(argv, []) else (first, False)\n",
     "        return None\n", _S10 + "[s10-ps-call-quoted-plan-ask]"),
    ("cloud guard s10: PowerShell's `.` and `&` not stripped by the gate",
     GUARDS, '    if argv and argv[0] in ("&", "."):\n',
     "    if False:\n", _S10A + "[s10a-ps-dot-plan]"),
    ("cloud guard s10: a PowerShell assignment's right side not read", GUARDS,
     "        argv, words = argv[2:], words[2:]  # `$out = terraform destroy` "
     "runs\n", "        pass\n", _S10A + "[s10a-ps-assigned-output]"),
    ("cloud guard s10: a lone PowerShell `$x` read as a program", GUARDS,
     '    if not argv or len(argv) == 1 and (argv[0].startswith("$") or type(\n',
     '    if not argv or len(argv) == 1 and (False or type(\n', _S10A + "[s10a-ps-foreach-fmt]"),
    ("cloud guard s10: a PowerShell command word made at run time ignored",
     GUARDS,
     "        named = _ps_verb_on_line(normal)\n"
     "        return None if named is None else (named, True)\n",
     "        return None\n", _S10 + "[s10-ps-variable-command-ask]"),
    ("cloud guard s10: PowerShell's `pwsh -c` payload not read", GUARDS,
     "            return ps_trigger(ps_normalise(payload)[0], helpers, "
     "depth + 1)\n", "            return None\n",
     _S10 + "[s10-ps-pwsh-quoted-plan-ask]"),
    ("cloud guard s10: PowerShell's `bash -c` payload not read", GUARDS,
     "            return _bash_trigger(positional[0], positional[0], helpers,\n"
     "                                 depth + 1)\n",
     "            return None\n", _S10 + "[s10-ps-bash-c-quoted-plan-ask]"),
    ("cloud guard s10: PowerShell's Invoke-Expression string not read", GUARDS,
     "    if head in _PS_EVAL:\n", "    if False:\n",
     _S10 + "[s10-ps-iex-quoted-plan-ask]"),
    ("cloud guard s10: PowerShell's `$(...)` not read", GUARDS,
     "    hits = [ps_trigger(sub, helpers, depth + 1) for sub in subs]\n",
     "    hits = []\n", _S10 + "[s10-ps-subexpression-quoted-plan-ask]"),
    ("cloud guard s10: a verb after a mention read as a renamed terraform",
     GUARDS, '    if head in line["copies"] and verb is not None \\\n',
     "    if names_terraform(top, \"bash\") and verb is not None \\\n",
     _S10A + "[s10a-fmt-then-kubectl]"),
    ("cloud guard s10: find -exec's found path read as a literal", GUARDS,
     '            sub.append(word.replace("{}", _HOLE))  # a path found at '
     "run time\n", "            sub.append(word)\n",
     _R5 + "[r5-find-exec-found-binary]"),
)

# T-0005 review round 7 (GUjM5s): direct spellings the option readers lost,
# eval's `--`, PowerShell's colon-bound values, and three wrong refusals.
# One mutation per new branch, each aimed at a row it flips.
_R7 = _E + "test_round7_must_block_python"
_R7A = _E + "test_round7_must_allow_python"

CLOUD_GUARD_MUTATIONS += (
    ("cloud guard r7: an unknown option takes the next option as its value",
     GUARDS, '            and not nxt.startswith("-") and _HOLE not in nxt)\n',
     "            and _HOLE not in nxt)\n",
     _R7 + "[r7-tg-bool-then-working-dir-ask]"),
    ("cloud guard r7: an unknown option takes a run-time value", GUARDS,
     '            and not nxt.startswith("-") and _HOLE not in nxt)\n',
     '            and not nxt.startswith("-"))\n',
     _R7 + "[r7-tg-option-value-before-plan-destroy-ask]"),
    ("cloud guard r7: `--` no longer ends terraform's options", GUARDS,
     '        if args[index] == "--":\n            return index + 1\n'
     '        name, sep, _value = args[index].lstrip("-").partition("=")\n',
     '        name, sep, _value = args[index].lstrip("-").partition("=")\n',
     _R7A + "[r7a-tg-run-dashdash-plan]"),
    ("cloud guard r7: a wrapper's long value option takes nothing", GUARDS,
     '            index += "=" not in word and len(match) == 1\n',
     "            index += 0\n", _R7 + "[r7-stdbuf-long-value-ask]"),
    ("cloud guard r7: a wrapper's long option not read by its prefix", GUARDS,
     "            match = [t for t in longs if t.startswith(word)]\n",
     "            match = [t for t in longs if t == word]\n",
     _R7 + "[r7-stdbuf-long-abbrev-ask]"),
    ("cloud guard r7: a short cluster's value letter read only alone", GUARDS,
     "            if letter in shorts:\n",
     "            if letter in shorts and len(word) == 2:\n",
     _R7 + "[r7-xargs-cluster-ask]"),
    ("cloud guard r7: an attached short value takes the next word too",
     GUARDS, "                index += pos == len(word) - 1\n",
     "                index += 1\n", _R7 + "[r7-xargs-attached-ask]"),
    ("cloud guard r7: `command -v` read as running its operand", GUARD,
     "                return []\n            if head == \"timeout\" and rest:\n",
     "                pass\n            if head == \"timeout\" and rest:\n",
     _R7A + "[r7a-command-v]"),
    ("cloud guard r7: the lexer reads eval's `--` as the command", GUARD,
     '        args = args[1:] if args[:1] == ["--"] else args  # `eval -- ...`\n',
     "", _R7 + "[r7-eval-dashdash-ask]"),
    ("cloud guard r7: the gate reads eval's `--` as the command", GUARDS,
     '        args = args[1:] if args[:1] == ["--"] else args  # `eval -- ...`\n',
     "", _R7 + "[r7-eval-dashdash-quoted-plan-ask]"),
    ("cloud guard r7: a lone quoted PowerShell string read as a program",
     GUARDS, '            words[0]).__name__ != "_Bare"):\n',
     '            words[0]).__name__ == "never"):\n',
     _R7A + "[r7a-ps-assign-string]"),
    ("cloud guard r7: PowerShell's colon-bound values not read", GUARDS,
     '    values = [w.split(":", 1)[1] if w.startswith("-") and ":" in w else w\n'
     "              for w in args]\n", "    values = list(args)\n",
     _R7 + "[r7-ps-start-process-colon-ask]"),
    ("cloud guard r7: a string piped into Invoke-Expression not read", GUARDS,
     "        if not script:\n", "        if False:\n",
     _R7 + "[r7-ps-string-piped-to-iex-ask]"),
    ("cloud guard r7: terragrunt read-only only as its first word", GUARDS,
     "        rest = rest[tf_skip_options(rest, 0):]\n", "        pass\n",
     _R7A + "[r7a-tg-working-dir-plan]"),
    ("cloud guard r7: terragrunt run-all's subcommand not read", GUARDS,
     "            rest = rest[1:][tf_skip_options(rest[1:], 0):]\n",
     "            pass\n", _R7A + "[r7a-tg-run-all-plan]"),
)

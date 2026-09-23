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
run, restored with `cp` and checked with `diff`: all red. Three
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

_T = "tests/test_cloud_guard.py::"
_BLOCK = _T + "test_must_block_python"
_ALLOW = _T + "test_must_allow_python"
_IDENT = _T + "test_identity_python"

CLOUD_GUARD_MUTATIONS = (
    ("cloud guard: terraform destroy no longer recognised", GUARD,
     '    if words[0] in ("apply", "destroy"):\n',
     '    if words[0] in ("apply",):\n', _BLOCK),
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
     '"mysql": "mysql", "mariadb": "mysql",',
     '"mysql": "standard", "mariadb": "mysql",', _BLOCK),
    ("cloud guard: SQL string literals no longer stripped", GUARD,
     '        if c in "\'\\"":\n            escapes = ',
     '        if False:\n            escapes = ', _ALLOW),
    ("cloud guard: heredoc bodies no longer read", GUARD,
     '            if pending:\n                i = _read_heredocs(',
     '            if False:\n                i = _read_heredocs(', _BLOCK),
    ("cloud guard: bash $( ) inside quotes no longer scanned", GUARD,
     '            k = _match_close(text, j + 1)\n'
     '            subs.append(text[j + 2:k])\n',
     '            k = _match_close(text, j + 1)\n', _BLOCK),
    ("cloud guard: bash ; & | no longer split commands", GUARD,
     '            finish(pipe=c == "|")\n',
     '            add(c)\n', _BLOCK),
    ("cloud guard: PowerShell script blocks no longer split", GUARD,
     '        if c in "{}":\n', '        if c in "":\n', _BLOCK),
    ("cloud guard: sudo no longer unwrapped", GUARD,
     '    "sudo": frozenset((', '    "sudo-x": frozenset((', _BLOCK),
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
     '    if not whats or os.path.exists(marker) \\\n',
     '    if True or os.path.exists(marker) \\\n',
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
     '                and "{" not in w and placeholder not in w]\n',
     '                and "{" not in w]\n', _BLOCK),
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
     '        if arg == "--":\n            break\n', _BLOCK),
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
    ("cloud guard: psql read as MySQL", GUARD,
     '_SQL_DIALECT = {"psql": "postgres",',
     '_SQL_DIALECT = {"psql": "mysql",', _ALLOW),
    ("cloud guard: sqlcmd read as MySQL", GUARD,
     '"sqlcmd": "tsql", "invoke-sqlcmd": "tsql",',
     '"sqlcmd": "mysql", "invoke-sqlcmd": "tsql",', _ALLOW),
    ("cloud guard: PostgreSQL E'' strings read as standard", GUARD,
     '                dialect == "postgres" and c == "\'" and i > 0\n',
     '                False and c == "\'" and i > 0\n', _BLOCK),
    ("cloud guard: aws --dry-run destructive", GUARD,
     '    if "--dry-run" in args or "--dryrun" in args:\n',
     '    if False:\n', _ALLOW),
    ("cloud guard: terraform apply -help destructive", GUARD,
     '    if _HELP_FLAGS.intersection(args):\n', '    if False:\n', _ALLOW),
    ("cloud guard: Remove-Az* -WhatIf destructive", GUARD,
     '        if any(a.lower() in ("-whatif", "-whatif:$true") for a in args):\n',
     '        if False:\n', _ALLOW),
    ("cloud-guard.sh: runs beside its twin on Windows", GUARD_SH,
     'if [ "${OS:-}" = "Windows_NT" ] && [ -f "$DIR/cloud-guard.ps1" ]',
     'if false && [ -f "$DIR/cloud-guard.ps1" ]',
     _T + "test_bash_wrapper_flavour_guard"),
    ("cloud-guard.sh: stands down on Windows with no PowerShell", GUARD_SH,
     '   && { command -v powershell.exe',
     '   && { true || command -v powershell.exe',
     _T + "test_bash_wrapper_flavour_guard"),
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

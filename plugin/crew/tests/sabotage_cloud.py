"""The crew 1.0 T5 cloud/destructive guard mutations, appended to
`sabotage.py`'s MUTATIONS the way `sabotage_review.py`'s are, and kept apart
for the same reason: `sabotage.py` sits at `.pylintrc`'s max-module-lines. Run
that file, not this one.

One mutation per rule the guard enforces, plus its must-allow edges, the
switch, and the two wrappers' fail-closed fallback. All were run through this
harness's own apply/restore on 2026-09-23 (30 of 30 red), with each target
also copied aside with `cp` first and compared with `diff` afterwards. Three
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
     '    if verb in ("delete", "purge") or',
     '    if verb in ("purge",) or', _BLOCK),
    ("cloud guard: SQL DROP no longer destructive", GUARD,
     '_SQL_WORDS_RE = re.compile(r"\\b(drop|truncate)\\b"',
     '_SQL_WORDS_RE = re.compile(r"\\b(truncate)\\b"', _BLOCK),
    ("cloud guard: MySQL's reading of SQL dropped", GUARD,
     '               for mysql in (False, True))',
     '               for mysql in (False,))', _BLOCK),
    ("cloud guard: SQL string literals no longer stripped", GUARD,
     '        if c in "\'\\"":\n            j = i + 1\n',
     '        if False:\n            j = i + 1\n', _ALLOW),
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
     '    if decision == "allow":\n        return\n',
     '    if False:\n        return\n', _ALLOW),
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

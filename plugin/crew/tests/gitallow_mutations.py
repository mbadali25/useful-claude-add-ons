"""crew 1.3.61 `guards.git.allow` mutations, in `sabotage.py`'s tuple shape.

Each puts back one way the switch could let a git command through when it must
not, or stop judging something that is not git, and names the must-block or
must-allow case in `test_git_allow.py` that has to go red.

NOT wired into `sabotage.py`'s MUTATIONS: `sabotage*.py` is review harness
(`scripts/check-tooling-pr.py` `HARNESS`), and a harness change lands alone. Until
a harness-only change registers this table, run it with sabotage.py's own
machinery:

    cd plugin/crew/tests && python3 -c "import sabotage, gitallow_mutations as m; \
        sabotage.MUTATIONS = m.GITALLOW_MUTATIONS; raise SystemExit(sabotage.main())"

HOST-SPECIFIC, and therefore not in this table: promote-gate.ps1's
`allow<TAB>guards.git.allow` -> `exit 0` line. Its cases
(`test_gate_*[ps1]`) need PowerShell 7 and skip without it, and a skipped case
is not a red. The python half of that path (`_promote_dispatch._git_allowed`)
is here and runs on every host.
"""
import os

CREW = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SCRIPTS = os.path.join(CREW, "hooks", "scripts")
GA = os.path.join(_SCRIPTS, "crew_gitallow.py")
CG = os.path.join(_SCRIPTS, "cloud_guard.py")
PG = os.path.join(_SCRIPTS, "_promote_gate.py")
PD = os.path.join(_SCRIPTS, "_promote_dispatch.py")
CFG = os.path.join(_SCRIPTS, "crew_config.py")
CC = os.path.join(_SCRIPTS, "crew_confirm_config.py")
_T = "tests/test_git_allow.py::"

GITALLOW_MUTATIONS = (
    ("gitAllow: a value needs no double-confirmation receipt", GA,
     "        if backed != _canonical(value):\n",
     "        if False:\n",
     _T + "test_a_hand_edit_with_no_receipt_is_off"),
    ("gitAllow: a receipt for any value backs the file's value", GA,
     "        if backed != _canonical(value):\n",
     "        if backed is None:\n",
     _T + "test_a_receipt_for_another_value_does_not_back_it"),
    ("gitAllow: a newer revocation is ignored", GA,
     "and r.get(\"state\") in (crew_humanonly.APPLIED, \"revoked\")\n",
     "and r.get(\"state\") == crew_humanonly.APPLIED\n",
     _T + "test_a_revocation_newer_than_the_receipt_wins"),
    ("gitAllow: a repo \"off\" no longer vetoes", GA,
     "            if repo_setting == OFF:\n",
     "            if False:\n",
     _T + "test_a_repo_off_vetoes"),
    ("gitAllow: a malformed repo value is not a veto", GA,
     "            if repo_setting is None:\n",
     "            if False:\n",
     _T + "test_a_malformed_repo_value_is_a_veto"),
    ("gitAllow: \"ALL\" is read as all", GA,
     "    if value == ALL:\n",
     "    if str(value).lower() == ALL:\n",
     _T + "test_a_malformed_machine_value_is_off"),
    ("gitAllow: an unseen subcommand passes an allowlist", GA,
     "        return sub is not UNSEEN and sub in setting\n",
     "        return sub is UNSEEN or sub in setting\n",
     _T + "test_xargs_git_unseen_subcommand_passes_only_under_all"),
    ("gitAllow: the machine writer accepts \"all\"", GA,
     "        return None if value is None or value == OFF else _REFUSAL\n",
     "        return None\n",
     _T + "test_the_writers_refuse_turning_it_on"),
    ("gitAllow: the repo writer accepts \"all\"", GA,
     "    return None if value == OFF else _REPO_REFUSAL\n",
     "    return None\n",
     _T + "test_the_writers_refuse_turning_it_on"),
    ("gitAllow: a line exempts a command that is not git", GA,
     "        if not words or not _is_git_word(words[0]):\n",
     "        if not words:\n",
     _T + "test_line_exempt"),
    ("gitAllow: a line exempts an unlisted subcommand", GA,
     "        if not allows(setting, subcommand(words[1:])):\n",
     "        if False:\n",
     _T + "test_line_exempt"),
    ("gitAllow: a backtick substitution's commands are not read", GA,
     "    for sub in subs:\n        inner = _bash_commands(sub, depth + 1)\n",
     "    for sub in ():\n        inner = _bash_commands(sub, depth + 1)\n",
     _T + "test_line_exempt"),
    ("gitAllow: a PowerShell subexpression in double quotes is read as text", GA,
     "                if text.startswith(\"$(\", end) or text.startswith(\"@(\", end):\n"
     "                    return None\n",
     "                if False:\n                    return None\n",
     _T + "test_line_exempt"),
    ("gitAllow: a PowerShell pipe is read as a separator", GA,
     "            if c == \"|\" and text.startswith(\"||\", i):\n",
     "            if c == \"|\":\n",
     _T + "test_line_exempt"),
    ("gitAllow: a declared git deploy is exempted too", GA,
     "            if _GIT_IN_DEPLOY_RE.search(declared) and",
     "            if False and",
     _T + "test_gate_python_exemption_in_process"),
    ("cloud guard: every git finding passes, switch or not", CG,
     "            if crew_gitallow.allows(git_allow, scope[crew_gitallow.SCOPE_KEY]):\n",
     "            if True:\n",
     _T + "test_force_push_is_refused_with_the_switch_off"),
    ("cloud guard: every finding is tagged as git", CG,
     "SCOPE_KEY: crew_gitallow.subcommand(args)} if head == \"git\" else {}\n",
     "SCOPE_KEY: crew_gitallow.subcommand(args)} if True else {}\n",
     _T + "test_the_rest_of_the_line_is_still_judged"),
    ("cloud guard: xargs git's unseen subcommand is read as push", CG,
     "                        if sub and seen([sub]) else crew_gitallow.UNSEEN})\n",
     "                        if sub and seen([sub]) else \"push\"})\n",
     _T + "test_xargs_git_unseen_subcommand_passes_only_under_all"),
    ("promote gate (bash): the switch is not asked", PG,
     "        if self.git_allowed():\n            return 0\n",
     "        if False:\n            return 0\n",
     _T + "test_gate_passes_a_commit_naming_a_deploy_with_all"),
    ("promote gate (ps1's python): the switch is not asked", PD,
     "    if shell == \"powershell\" and command.strip() and _git_allowed(command):\n",
     "    if False:\n",
     _T + "test_dispatch_prints_the_allow_record_for_powershell"),
    ("promote gate (ps1's python): the allow record is printed for bash too", PD,
     "    if shell == \"powershell\" and command.strip() and _git_allowed(command):\n",
     "    if command.strip() and _git_allowed(command):\n",
     _T + "test_dispatch_prints_the_allow_record_for_powershell"),
    ("config: a crew write back to off does not revoke the receipt", CFG,
     " or change.get(\"path\") == crew_gitallow.KEY:\n",
     ":\n",
     _T + "test_a_crew_write_back_to_off_revokes_the_receipt"),
    ("config: apply writes a repo or off value", CFG,
     "        if layer != \"machine\" or crew_gitallow.normalise(value) in "
     "(None, crew_gitallow.OFF):\n",
     "        if False:\n",
     _T + "test_apply_refuses_a_repo_or_off_value"),
    ("confirm-config: propose accepts the repo layer", CC,
     "        if layer != \"machine\":\n            raise Refused(f\"{dotted} lives",
     "        if False:\n            raise Refused(f\"{dotted} lives",
     _T + "test_propose_refuses_what_it_cannot_confirm"),
)

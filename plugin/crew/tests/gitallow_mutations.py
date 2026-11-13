"""crew 1.3.73 `guards.git.allow` mutations, in `sabotage.py`'s tuple shape.

Each puts back one way the switch could let a git command through when it must
not, or stop judging something that is not git, and names the must-block or
must-allow case in `test_git_allow.py` that has to go red.

Grown from 24 to cover PR #769's review findings 1-6: the receipt's shape, its
binding to the file it left, an unreadable repo file, a git command carrying
config or a command of its own, PowerShell's single `&`, and the `git -C`
target repository's veto. A check that another check fully shadows has no
mutation (it could never go red alone): `receipt_problem`'s confirmation count,
value and binding-shape checks, `_repo_veto`'s could-not-tell source, and the
None branches of `settings` and `line_targets` (a TypeError there is caught
and read as off) are such belts.

Review round 2 (Codex gpt-6-sol) added one red mutation per fix (BLOCK 1-2,
FIX 3-6). It also DELETED "cloud guard: xargs git's unseen subcommand is read
as push": every `xargs git` finding is now held (`FED_HOLD`), so reading its
subcommand as `push` can no longer let anything through -- a shadowed check
with no red. `allows`' UNSEEN branch keeps its mutation, against `test_allows`.
Three more are shadowed belts now, measured green and deleted: `receipt_problem`'s
`appliedChangeNs` key and `read_layer`'s None binding for an unknown change time
(the binding equality in `settings` and the record's int check refuse the same
record first), and `_ps_commands`' refusal of `$(` inside double quotes (every
PowerShell word reaches `hold`, whose run-time rule refuses the `$` first). The
bash substitution reading keeps its mutation: a substitution in a redirection
target (`git status > "$(deploy-prod)"`) is in no word `hold` sees.

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
CFF = os.path.join(_SCRIPTS, "crew_config_files.py")
CC = os.path.join(_SCRIPTS, "crew_confirm_config.py")
_T = "tests/test_git_allow.py::"

_HOLD_CD = ("    if scope.get(HOLD_KEY, \"not read\") is not None or ctx.get(\"cd\") "
            "or ctx.get(\"opaque\"):\n")

GITALLOW_MUTATIONS = (
    # --- the receipt is a WHOLE double confirmation (review finding 1) ---
    ("gitAllow: a receipt naming another file backs this one", GA,
     "            or crew_humanonly.target_key(path) != target:\n",
     "            or False:\n",
     _T + "test_a_forged_receipt_is_not_honoured"),
    ("gitAllow: any proposal window is accepted", GA,
     "            or not created <= expires <= created + crew_humanonly.PROPOSAL_TTL_SECONDS:\n",
     "            or not created <= expires:\n",
     _T + "test_a_forged_receipt_is_not_honoured"),
    ("gitAllow: a confirmation need not come from a user prompt", GA,
     "        if confirmation.get(\"via\") != crew_humanonly.USER_PROMPT \\\n",
     "        if confirmation.get(\"via\") is None \\\n",
     _T + "test_a_forged_receipt_is_not_honoured"),
    ("gitAllow: a confirmation may fall outside the window", GA,
     "        if not created <= stamp <= expires:\n",
     "        if False:\n",
     _T + "test_a_forged_receipt_is_not_honoured"),
    ("gitAllow: one prompt may confirm twice", GA,
     "    if len(prompts) != 2:\n",
     "    if not prompts:\n",
     _T + "test_a_forged_receipt_is_not_honoured"),
    ("gitAllow: a record settled before its second confirmation counts", GA,
     "    if settled < max(stamps):\n",
     "    if False:\n",
     _T + "test_a_forged_receipt_is_not_honoured"),
    ("gitAllow: a receipt for any value backs the file's value", GA,
     "        if record is not None and _canonical(record.get(\"value\")) != _canonical(value):\n",
     "        if False:\n",
     _T + "test_a_receipt_tampered_to_another_value_does_not_back_it"),
    ("gitAllow: a newer revocation is ignored", GA,
     "and r.get(\"state\") in (crew_humanonly.APPLIED, \"revoked\")\n",
     "and r.get(\"state\") == crew_humanonly.APPLIED\n",
     _T + "test_a_revocation_newer_than_the_receipt_wins"),
    # --- the receipt is bound to the file it left (review finding 2) ---
    ("gitAllow: the file binding is not compared", GA,
     "        if record is not None and record.get(\"binding\") != binding:\n",
     "        if False:\n",
     _T + "test_a_hand_edit_to_off_and_back_is_off"),
    ("config: crew's machine writer does not re-bind the receipt", CFG,
     "        _carry_git_allow(real_path, out)\n",
     "        pass\n",
     _T + "test_a_crew_write_of_another_machine_key_keeps_it_on"),
    ("config: a machine humanOnly opt-out does not re-bind the receipt", CFG,
     "            _carry_git_allow(path, out)\n",
     "            pass\n",
     _T + "test_a_machine_humanonly_optout_keeps_it_on"),
    ("config: apply does not hand back the file binding", CFG,
     "                binding_out[\"binding\"] = crew_gitallow.file_binding(written)\n",
     "                pass\n",
     _T + "test_two_confirmations_turn_it_on"),
    ("config files: `after` is never run", CFF,
     "        if after is not None:\n            after(path)\n",
     "        pass\n",
     _T + "test_two_confirmations_turn_it_on"),
    ("confirm-config: the applied record carries no binding", CC,
     "        record[\"binding\"] = bound[\"binding\"]\n",
     "        pass\n",
     _T + "test_two_confirmations_turn_it_on"),
    ("config: a crew write back to off does not revoke the receipt", CFG,
     " or change.get(\"path\") == crew_gitallow.KEY:\n",
     ":\n",
     _T + "test_a_crew_write_back_to_off_revokes_the_receipt"),
    # --- the repo file (review finding 3) and the target repo (finding 6) ---
    ("gitAllow: a repo \"off\" no longer vetoes", GA,
     "    if repo_setting == OFF:\n",
     "    if False:\n",
     _T + "test_a_repo_off_vetoes"),
    ("gitAllow: a malformed repo value is not a veto", GA,
     "    if repo_setting is None:\n",
     "    if False:\n",
     _T + "test_a_malformed_repo_value_is_a_veto"),
    ("gitAllow: an unreadable repo file is not a veto", GA,
     "    if state == UNREADABLE:\n        return f\"{label_}'s config",
     "    if False:\n        return f\"{label_}'s config",
     _T + "test_an_unreadable_repo_file_is_a_veto"),
    ("gitAllow: the project's own repo file is not read", GA,
     "        veto = _repo_veto(project, \"the repo\")\n",
     "        veto = None\n",
     _T + "test_a_repo_off_vetoes"),
    ("gitAllow: a git -C target's repo file is not read", GA,
     "            veto = _repo_veto(top, f\"the target repo {top}\")\n",
     "            veto = None\n",
     _T + "test_a_target_repo_veto_holds_for_git_dash_c"),
    ("gitAllow: a git -C target that is not a work tree is skipped", GA,
     "            if top is None:\n",
     "            if top is None:\n                continue\n            if top is None:\n",
     _T + "test_a_target_crew_cannot_tell_is_not_exempt"),
    ("gitAllow: --git-dir / --work-tree read as no target", GA,
     "        if word.split(\"=\", 1)[0] in (\"--git-dir\", \"--work-tree\"):\n",
     "        if False:\n",
     _T + "test_a_target_crew_cannot_tell_is_not_exempt"),
    ("gitAllow: an unknown target reads as the project", GA,
     "    if dirs is UNSEEN:\n        return OFF\n",
     "    if False:\n        return OFF\n",
     _T + "test_a_target_crew_cannot_tell_is_not_exempt"),
    ("gitAllow: a line that changes directory is exempt", GA,
     _HOLD_CD,
     "    if scope.get(HOLD_KEY, \"not read\") is not None:\n",
     _T + "test_a_target_crew_cannot_tell_is_not_exempt"),
    ("promote gate: the line's git -C targets are not read", GA,
     "settings(root, global_path, store, line_targets(commands, root))",
     "settings(root, global_path, store)",
     _T + "test_promote_exempt_reads_the_target_repo_veto"),
    # --- config or a command of its own is never exempt (review finding 4) ---
    ("gitAllow: a held finding is exempt", GA,
     _HOLD_CD,
     "    if ctx.get(\"cd\") or ctx.get(\"opaque\"):\n",
     _T + "test_force_push_carrying_config_stays_refused_with_all"),
    ("gitAllow: a GIT_* environment assignment is not read", GA,
     "        if value is not None and isinstance(name, str) and name.upper().startswith(\"GIT_\"):\n",
     "        if False:\n",
     _T + "test_force_push_carrying_config_stays_refused_with_all"),
    ("gitAllow: a global -c / --config-env / --exec-path is not read", GA,
     "        if word != \"-C\" and _INJECT_GLOBAL_RE.match(word):\n",
     "        if False:\n",
     _T + "test_a_git_command_with_its_own_config_or_command_is_not_line_exempt"),
    ("gitAllow: filter-branch / instaweb are not held", GA,
     "    if sub in _RUNS_ALWAYS:\n",
     "    if False:\n",
     _T + "test_a_git_command_with_its_own_config_or_command_is_not_line_exempt"),
    ("gitAllow: submodule foreach / bisect run are not held", GA,
     "    if sub in _RUNS_WORD and _RUNS_WORD[sub] in rest:\n",
     "    if False:\n",
     _T + "test_a_git_command_with_its_own_config_or_command_is_not_line_exempt"),
    ("gitAllow: an option that runs a command is not held", GA,
     "            if _option_hit(word, option):\n",
     "            if False:\n",
     _T + "test_a_git_command_with_its_own_config_or_command_is_not_line_exempt"),
    ("gitAllow: a bundled short option is not read", GA,
     "    return word.startswith(\"-\") and not word.startswith(\"--\") and option[1] in word[1:]\n",
     "    return False\n",
     _T + "test_a_git_command_with_its_own_config_or_command_is_not_line_exempt"),
    ("gitAllow: a whole line ignores hold", GA,
     "        if hold(words[1:]) is not None:\n",
     "        if False:\n",
     _T + "test_a_git_command_with_its_own_config_or_command_is_not_line_exempt"),
    ("cloud guard: a git finding carries no hold", CG,
     "              else crew_gitallow.hold(args, env),\n",
     "              else None,\n",
     _T + "test_force_push_carrying_config_stays_refused_with_all"),
    ("cloud guard: a git finding's hold ignores the environment", CG,
     "              else crew_gitallow.hold(args, env),\n"
     "              crew_gitallow.DIRS_KEY",
     "              else crew_gitallow.hold(args, {}),\n"
     "              crew_gitallow.DIRS_KEY",
     _T + "test_force_push_carrying_config_stays_refused_with_all"),
    ("cloud guard: an xargs git finding is held only for what crew sees", CG,
     "                        crew_gitallow.HOLD_KEY: crew_gitallow.FED_HOLD,\n",
     "                        crew_gitallow.HOLD_KEY: crew_gitallow.hold(args, env),\n",
     _T + "test_xargs_git_is_never_exempt"),
    ("cloud guard: a git finding carries no -C target", CG,
     "crew_gitallow.DIRS_KEY: crew_gitallow.target_dirs(args)} if head == \"git\" else {}\n",
     "crew_gitallow.DIRS_KEY: ()} if head == \"git\" else {}\n",
     _T + "test_a_target_repo_veto_holds_for_git_dash_c"),
    # --- review round 2 (Codex gpt-6-sol): one red mutation per fix ---
    ("gitAllow: an abbreviated long option is not held (BLOCK 1)", GA,
     "        return len(name) > 2 and name.startswith(\"--\") and option.startswith(name)\n",
     "        return word.startswith(option + \"=\")\n",
     _T + "test_an_abbreviated_option_that_runs_a_command_is_held"),
    ("gitAllow: a word built at run time is not held (BLOCK 2)", GA,
     "        if not isinstance(word, str) or _RUNTIME_RE.search(word):\n",
     "        if not isinstance(word, str):\n",
     _T + "test_a_word_built_at_run_time_is_never_exempt"),
    ("gitAllow: a PowerShell splat is not read as run-time (BLOCK 2)", GA,
     "_RUNTIME_RE = re.compile(r\"[$`]|^@[A-Za-z_]\")\n",
     "_RUNTIME_RE = re.compile(r\"[$`]\")\n",
     _T + "test_a_word_built_at_run_time_is_never_exempt"),
    ("cloud guard: a git command xargs feeds is held only for what crew sees (BLOCK 2)", CG,
     "              crew_gitallow.HOLD_KEY: crew_gitallow.FED_HOLD if fed\n",
     "              crew_gitallow.HOLD_KEY: None if fed\n",
     _T + "test_a_force_push_crew_cannot_read_whole_stays_refused_with_all"),
    ("gitAllow: a dangling repo config reads as absent (FIX 3)", GA,
     "        if _dangles(path):\n",
     "        if False:\n",
     _T + "test_a_crew_path_that_is_a_file_is_a_veto"),
    ("gitAllow: a .crew that is no directory reads as absent (FIX 3)", GA,
     "    return probe == os.path.abspath(path) or not os.path.isdir(probe)\n",
     "    return probe == os.path.abspath(path)\n",
     _T + "test_a_crew_path_that_is_a_file_is_a_veto"),
    ("gitAllow: the binding drops the change time (FIX 4)", GA,
     "        \"appliedMtimeNs\": stat.st_mtime_ns, \"appliedChangeNs\": change}\n",
     "        \"appliedMtimeNs\": stat.st_mtime_ns, \"appliedChangeNs\": 0}\n",
     _T + "test_a_copy_put_back_with_its_mtime_is_off"),
    ("gitAllow: a line's words lose every quote character (FIX 5)", GA,
     "        out.append([crew_guards._shell_unquote(w)  # pylint: disable=protected-access\n",
     "        out.append([crew_guards._dequote(w)  # pylint: disable=protected-access\n",
     _T + "test_a_quote_inside_the_program_name_is_not_git"),
    ("cloud guard: a git finding is judged as terraform (FIX 6)", CG,
     "                and crew_gitallow.SCOPE_KEY not in finding.scope:\n",
     "                and True:\n",
     _T + "test_a_force_push_under_a_looser_policy_does_not_crash"),
    # --- PowerShell's single `&` (review finding 5) ---
    ("gitAllow: PowerShell's single & is read as a word", GA,
     "        if c == \"&\":\n",
     "        if False:\n",
     _T + "test_a_single_ampersand_is_never_line_exempt"),
    ("gitAllow: a PowerShell redirection's & is refused", GA,
     "            if word and word[-1] == \">\" and i + 1 < n and text[i + 1].isdigit():\n",
     "            if False:\n",
     _T + "test_an_ampersand_that_is_not_a_separator_is_line_exempt"),
    # --- the switch itself (the first table) ---
    ("gitAllow: \"ALL\" is read as all", GA,
     "    if value == ALL:\n",
     "    if str(value).lower() == ALL:\n",
     _T + "test_normalise"),
    ("gitAllow: an unseen subcommand passes an allowlist", GA,
     "        return sub is not UNSEEN and sub in setting\n",
     "        return sub is UNSEEN or sub in setting\n",
     _T + "test_allows"),
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
     "        if not allows(setting, subcommand(args)):\n",
     "        if False:\n",
     _T + "test_line_exempt"),
    ("gitAllow: a backtick substitution's commands are not read", GA,
     "    for sub in subs:\n        inner = _bash_commands(sub, depth + 1)\n",
     "    for sub in ():\n        inner = _bash_commands(sub, depth + 1)\n",
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
     "crew_gitallow.DIRS_KEY: crew_gitallow.target_dirs(args)} if head == \"git\" else {}\n",
     "crew_gitallow.DIRS_KEY: crew_gitallow.target_dirs(args)} if True else {}\n",
     _T + "test_the_rest_of_the_line_is_still_judged"),
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

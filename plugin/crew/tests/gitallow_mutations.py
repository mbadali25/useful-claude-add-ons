"""crew 1.3.85 `guards.git.allow` mutations, in `sabotage.py`'s tuple shape.

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

Review round 3 (Codex gpt-6-sol) added one red mutation per fix: a bash word
built by brace expansion, a glob or a leading tilde (`Expands`, in both
readers), the send-pack / fetch-pack program options, a name exported after a
plain assignment and the program variables beside `GIT_*`, and PowerShell's
`--%` / `%NAME%` / glob words. It also re-pointed the two `_dangles`
mutations: their old target, `test_a_crew_path_that_is_a_file_is_a_veto`,
goes red under them only on Windows (POSIX reports a file-as-directory as
NotADirectoryError, which never reaches `_dangles`), so they now name
`test_a_crew_file_windows_reports_missing_is_a_veto`, which stands Windows'
FileNotFoundError in on every host; a new mutation of the OSError branch names
its POSIX twin.

Review round 4 (Codex gpt-6-sol, crew 1.3.85) replaced the denylist with a
fail-closed allowlist read by ONE reader both paths ask (`plain_commands`), so
it DELETED every mutation of the code that is gone: the cloud guard's own
`hold` / `-C` / `Expands` marking, `finding_setting`, `_RUNTIME_RE`, the
`PROGRAM_VARS` and export reading, the PowerShell run-time and `&` checks (37
in all). It added one red mutation per allowlist rule (bash and PowerShell
characters, quotes, escapes, operators, heredocs, here-strings, the program
word, `git config` writes, `init --template`, `line_plan`). Shadowed belts with
no mutation: `finding_exempt`'s subcommand-membership check (a line
`line_exempt` passes has every finding's subcommand among its commands), the
cloud guard's `not fed` (an `xargs git` line is never only git), and
`_ps_commands`' dangling-redirection check (the target word, if read as an
argument instead, never makes a line exempt that dropping it would not).

Review round 5 (Codex gpt-6-sol, crew 1.3.85) made redirections a fail-closed
allowlist and taught the shared splitter bash's `>&-` and fd-prefix reading,
and added one red mutation per rule (25: the redirection rules, the PowerShell
parse-error refusals the differential test found, the splitter and the fd
prefix both readers share). It DELETED "a substitution anywhere on the line
is ignored" (`_bash_commands`' `if subs`): measured green, now a shadowed belt.
Its case, a substitution in a redirection target (`> "$(deploy-prod)"`), is
refused first by `_bash_redirect_problem`'s plain-target rule, and every other
place a substitution sits is refused by the word, nesting or heredoc-body
checks. `_fd_prefix`'s raw-text check is a belt too (no mutation): its boundary
check refuses every case it would, because raw text is never shorter than the
word read from it; so is `_bash_redirect_problem`'s ASCII check on the fd
(`_fd_prefix` never records a non-ASCII descriptor). The total is 109.

Review round 6 (Codex gpt-6-sol, crew 1.3.85) replaced the bash and PowerShell
readers with ONE plain command: no separator, redirection, heredoc,
here-string, continuation, comment or subshell is read at all. It DELETED the
mutations of the code that is gone (the splitter-driven `_bash_commands`,
`_bash_redirect_problem`, the PowerShell statement, redirection and here-string
parsing: 33 of round 4 and 5), plus "line_plan does not ask line_exempt" (a
shadowed belt now: with one command per line `finding_exempt` re-checks the same
subcommand), and added one red mutation per new rule (the blank characters, the
operator characters, a word-less redirect line, the PowerShell backtick lists,
and the two splitter fixes for BLOCK 2 and 3). Shadowed belts with no mutation:
`_bash_raw_words`' refusal of `;&|<>()#` and a newline outside quotes (each is
refused again by `_bash_plain_word`'s character list, so only the character-list
mutation above can go red) and its unclosed-quote returns. The total is 92.

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
GU = os.path.join(_SCRIPTS, "crew_guards.py")
_T = "tests/test_git_allow.py::"

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
    ("promote gate: the line's git -C targets are not read", GA,
     "settings(root, global_path, store, line_targets(commands, root))",
     "settings(root, global_path, store)",
     _T + "test_promote_exempt_reads_the_target_repo_veto"),
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
    # --- review round 2 (Codex gpt-6-sol): one red mutation per fix ---
    ("gitAllow: an abbreviated long option is not held (BLOCK 1)", GA,
     "        return len(name) > 2 and name.startswith(\"--\") and option.startswith(name)\n",
     "        return word.startswith(option + \"=\")\n",
     _T + "test_an_abbreviated_option_that_runs_a_command_is_held"),
    ("gitAllow: a dangling repo config reads as absent (FIX 3)", GA,
     "        if _dangles(path):\n",
     "        if False:\n",
     _T + "test_a_crew_file_windows_reports_missing_is_a_veto"),
    ("gitAllow: a .crew that is no directory reads as absent (FIX 3)", GA,
     "    return probe == os.path.abspath(path) or not os.path.isdir(probe)\n",
     "    return probe == os.path.abspath(path)\n",
     _T + "test_a_crew_file_windows_reports_missing_is_a_veto"),
    ("gitAllow: the binding drops the change time (FIX 4)", GA,
     "        \"appliedMtimeNs\": stat.st_mtime_ns, \"appliedChangeNs\": change}\n",
     "        \"appliedMtimeNs\": stat.st_mtime_ns, \"appliedChangeNs\": 0}\n",
     _T + "test_a_copy_put_back_with_its_mtime_is_off"),
    ("cloud guard: a git finding is judged as terraform (FIX 6)", CG,
     "                and crew_gitallow.SCOPE_KEY not in finding.scope:\n",
     "                and True:\n",
     _T + "test_a_force_push_under_a_looser_policy_does_not_crash"),
    ("gitAllow: an unopenable repo config other than missing reads as absent (round 3 FIX 4)", GA,
     "        return UNREADABLE, f\"cannot be read ({type(exc).__name__})\", None\n",
     "        return ABSENT, None, None\n",
     _T + "test_a_crew_file_posix_reports_as_no_directory_is_a_veto"),
    ("gitAllow: send-pack's program option is not held (round 3 FIX 2)", GA,
     "    \"send-pack\": (\"--receive-pack\", \"--exec\"),\n",
     "",
     _T + "test_plumbing_that_runs_a_program_is_held"),
    ("gitAllow: fetch-pack's program option is not held (round 3 FIX 2)", GA,
     "    \"fetch-pack\": (\"--upload-pack\", \"--exec\"),\n",
     "",
     _T + "test_plumbing_that_runs_a_program_is_held"),
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
    ("gitAllow: a line exempts an unlisted subcommand", GA,
     "        if not allows(setting, subcommand(args)):\n",
     "        if False:\n",
     _T + "test_line_exempt"),
    ("gitAllow: a declared git deploy is exempted too", GA,
     "            if _GIT_IN_DEPLOY_RE.search(declared) and",
     "            if False and",
     _T + "test_gate_python_exemption_in_process"),
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
    # --- review round 4 (Codex gpt-6-sol, crew 1.3.85): the fail-closed allowlist ---
    # bash reader (`_bash_plain_word`, `_bash_commands`)
    ("gitAllow r4: an unquoted $ is a plain character (BLOCK A)", GA,
     "_BASH_SAFE = frozenset(string.ascii_letters + string.digits + \"_-./:=+,@%^\")\n",
     "_BASH_SAFE = frozenset(string.ascii_letters + string.digits + \"_-./:=+,@%^$\")\n",
     _T + "test_round4_must_block_is_not_line_exempt"),
    ("gitAllow r4: a glob character is plain", GA,
     "_BASH_SAFE = frozenset(string.ascii_letters + string.digits + \"_-./:=+,@%^\")\n",
     "_BASH_SAFE = frozenset(string.ascii_letters + string.digits + \"_-./:=+,@%^*?[]\")\n",
     _T + "test_a_word_bash_expands_is_never_exempt"),
    ("gitAllow r4: a brace is plain", GA,
     "_BASH_SAFE = frozenset(string.ascii_letters + string.digits + \"_-./:=+,@%^\")\n",
     "_BASH_SAFE = frozenset(string.ascii_letters + string.digits + \"_-./:=+,@%^{}\")\n",
     _T + "test_a_word_bash_expands_is_never_exempt"),
    ("gitAllow r4: a $ inside double quotes is plain", GA,
     "                elif here in \"$`\":\n                    return None\n",
     "                elif False:\n                    return None\n",
     _T + "test_a_word_built_at_run_time_is_never_exempt"),
    ("gitAllow r4: a leading ~ is plain", GA,
     "            if pos == 0 or raw[pos - 1] in \"=:\":\n",
     "            if False:\n",
     _T + "test_a_word_bash_expands_is_never_exempt"),
    ("gitAllow r4: @{a..b} is read as reflog", GA,
     "            if not match or \"..\" in match.group(0):\n",
     "            if not match:\n",
     _T + "test_round4_must_block_is_not_line_exempt"),
    ("gitAllow r4: a single-quoted run keeps its quotes", GA,
     "            out.append(raw[pos + 1:end])\n            pos = end + 1\n",
     "            out.append(raw[pos:end + 1])\n            pos = end + 1\n",
     _T + "test_a_quote_inside_the_program_name_is_not_git"),
    ("gitAllow r4: a backslash escape keeps its backslash", GA,
     "            out.append(raw[pos + 1])\n            pos += 2\n",
     "            out.append(raw[pos:pos + 2])\n            pos += 2\n",
     _T + "test_round4_plain_git_lines_stay_exempt"),
    # the program word and hold (both shells)
    ("gitAllow r4: the program word need not be exactly git (FIX C)", GA,
     "        if not words or words[0] != \"git\":\n",
     "        if not words or not words[0].endswith(\"git\"):\n",
     _T + "test_round4_must_block_is_not_line_exempt"),
    ("gitAllow r4: a whole line ignores hold", GA,
     "        if hold(words[1:]) is not None:\n",
     "        if False:\n",
     _T + "test_a_git_command_with_its_own_config_or_command_is_not_line_exempt"),
    ("gitAllow r4: git config is never held (FIX D)", GA,
     "    if sub == \"config\" and not _config_is_read(rest):\n",
     "    if False:\n",
     _T + "test_round4_must_block_is_not_line_exempt"),
    ("gitAllow r4: an unknown git config option reads as a read (FIX D)", GA,
     "            elif word not in _CONFIG_READ_FLAGS:\n                return False\n",
     "            elif False:\n                return False\n",
     _T + "test_round6_a_config_or_program_command_alone_is_not_exempt"),
    ("gitAllow r4: a git config with a key and value reads as a read (FIX D)", GA,
     "    return action or len(positionals) == 1\n",
     "    return True\n",
     _T + "test_round4_must_block_is_not_line_exempt"),
    ("gitAllow r4: the git config edit/set subcommands read as a read (FIX D)", GA,
     "    if positionals and positionals[0] in (\"set\", \"unset\", \"rename-section\",\n",
     "    if False and positionals[0] in (\"set\", \"unset\", \"rename-section\",\n",
     _T + "test_round4_must_block_is_not_line_exempt"),
    ("gitAllow r4: git config get/list read as a write (FIX D)", GA,
     "    if positionals and positionals[0] in (\"get\", \"list\"):\n        return True\n",
     "    if positionals and positionals[0] in (\"get\", \"list\"):\n        return False\n",
     _T + "test_round4_plain_git_lines_stay_exempt"),
    ("gitAllow r4: git init --template is not held (FIX D)", GA,
     "    \"init\": (\"--template\",),\n",
     "",
     _T + "test_round6_a_config_or_program_command_alone_is_not_exempt"),
    # PowerShell reader (`_ps_commands`)
    ("gitAllow r4: a PowerShell curly quote is text (BLOCK B)", GA,
     "    if any(c in text for c in _PS_CURLY):\n",
     "    if False:\n",
     _T + "test_round4_must_block_is_not_line_exempt"),
    ("gitAllow r4: a PowerShell (expr) is plain (BLOCK B)", GA,
     "_PS_SAFE = frozenset(string.ascii_letters + string.digits + \"_-./:=+\\\\^%~@\")\n",
     "_PS_SAFE = frozenset(string.ascii_letters + string.digits + \"_-./:=+\\\\^%~@()\")\n",
     _T + "test_round4_must_block_is_not_line_exempt"),
    ("gitAllow r4: a PowerShell & or | is plain", GA,
     "_PS_SAFE = frozenset(string.ascii_letters + string.digits + \"_-./:=+\\\\^%~@\")\n",
     "_PS_SAFE = frozenset(string.ascii_letters + string.digits + \"_-./:=+\\\\^%~@&|\")\n",
     _T + "test_a_single_ampersand_is_never_line_exempt"),
    # the cloud guard asks the one reader
    ("cloud guard r4: every git finding passes, switch or not", CG,
     "            if crew_gitallow.finding_exempt(git_plan, scope):\n",
     "            if True:\n",
     _T + "test_force_push_is_refused_with_the_switch_off"),
    ("gitAllow r4: line_plan ignores the switch", GA,
     "        setting = settings(root, global_path, store, line_targets(commands, base))[\"allow\"]\n",
     "        setting = ALL\n",
     _T + "test_force_push_is_refused_with_the_switch_off"),
    ("gitAllow r4: line_plan reads no git -C target", GA,
     "settings(root, global_path, store, line_targets(commands, base))",
     "settings(root, global_path, store, ())",
     _T + "test_a_target_repo_veto_holds_for_git_dash_c"),
    # --- review round 5: redirections (one red per rule) ---
    # the splitter both paths read, and the fd prefix both readers strip alike
    ("splitter r5: >&- takes a word as its target", GU,
     "                    if redir[\"op\"] in (\">&\", \"<&\") and text[look:look + 1] == \"-\":\n",
     "                    if False:\n",
     _T + "test_round5_the_splitter_reads_redirections_as_bash_does"),
    ("splitter r5: an fd prefix stays a word", GU,
     "                if char in \"<>\" and _fd_prefix(text, self.pos, \"\".join(word)):\n",
     "                if False:\n",
     _T + "test_round5_the_splitter_reads_redirections_as_bash_does"),
    ("splitter r5: a dangling redirection takes the next command's word", GU,
     "            # target is never the next command's first word.\n            state[\"target\"] = None\n",
     "            # target is never the next command's first word.\n",
     _T + "test_round5_the_splitter_reads_redirections_as_bash_does"),
    ("gate reader r5: a quoted digit word is an fd prefix", GU,
     "                        _fd_prefix(self.text, self.pos, \"\".join(word)):",
     "                        _FD_WORD_RE.match(\"\".join(word)):",
     _T + "test_round5_the_gate_reader_strips_an_fd_prefix_as_the_splitter_does"),
    ("fd prefix r5: a digit word need not start a word", GU,
     "    return start == 0 or text[start - 1] in _FD_BOUNDARY\n",
     "    return True\n",
     _T + "test_round5_the_gate_reader_strips_an_fd_prefix_as_the_splitter_does"),
    ("fd prefix r5: a non-ASCII digit is a descriptor", GU,
     "    if not word or not word.isascii() or not _FD_WORD_RE.match(word) \\\n",
     "    if not word or not _FD_WORD_RE.match(word) \\\n",
     _T + "test_round5_the_gate_reader_strips_an_fd_prefix_as_the_splitter_does"),
    # --- review round 6: ONE plain command (one red per rule) ---
    ("gitAllow r6: a newline outside quotes is a blank (a second command)", GA,
     "        if char in \" \\t\":\n            if word:\n                words.append(\"\".join(word))\n",
     "        if char in \" \\t\\n\":\n            if word:\n                words.append(\"\".join(word))\n",
     _T + "test_round6_what_the_reader_does_not_follow_is_not_exempt"),
    ("gitAllow r6: bash separators and redirections are plain characters", GA,
     "_BASH_SAFE = frozenset(string.ascii_letters + string.digits + \"_-./:=+,@%^\")\n",
     "_BASH_SAFE = frozenset(string.ascii_letters + string.digits + \"_-./:=+,@%^;&|<>()#\\n\")\n",
     _T + "test_round6_what_the_reader_does_not_follow_is_not_exempt"),
    ("gitAllow r6: a bash line of redirects is read as plain", GA,
     "    raw = _bash_raw_words(text.strip())\n    if not raw:\n        return None\n",
     "    raw = _bash_raw_words(text.strip())\n    if not raw:\n        return [[\"git\"]]\n",
     _T + "test_round6_bash_blocks_are_not_exempt"),
    ("gitAllow r6: a PowerShell newline is a blank (a second statement)", GA,
     "        if char in \" \\t\":\n            if started:\n                words.append(\"\".join(word))\n",
     "        if char in \" \\t\\n\":\n            if started:\n                words.append(\"\".join(word))\n",
     _T + "test_round6_what_the_reader_does_not_follow_is_not_exempt"),
    ("gitAllow r6: PowerShell separators and redirections are plain characters", GA,
     "_PS_SAFE = frozenset(string.ascii_letters + string.digits + \"_-./:=+\\\\^%~@\")\n",
     "_PS_SAFE = frozenset(string.ascii_letters + string.digits + \"_-./:=+\\\\^%~@;>\")\n",
     _T + "test_round6_what_the_reader_does_not_follow_is_not_exempt"),
    ("gitAllow r6: a backtick may escape a wildcard (BLOCK 4)", GA,
     "_PS_ESCAPES = frozenset(\"-./:=_+\")\n",
     "_PS_ESCAPES = frozenset(\"-./:=_+*?[\")\n",
     _T + "test_round6_powershell_blocks_are_not_exempt"),
    ("gitAllow r6: a backtick may escape a letter or digit", GA,
     "_PS_ESCAPES = frozenset(\"-./:=_+\")\n",
     "_PS_ESCAPES = frozenset(\"-./:=_+n0\")\n",
     _T + "test_round6_powershell_blocks_are_not_exempt"),
    ("gitAllow r6: a double-quoted backtick may escape a wildcard (BLOCK 4)", GA,
     "_PS_DQ_ESCAPES = _PS_ESCAPES | frozenset('\"`')\n",
     "_PS_DQ_ESCAPES = _PS_ESCAPES | frozenset('\"`*?[')\n",
     _T + "test_round6_powershell_blocks_are_not_exempt"),
    ("gitAllow r6: a PowerShell $ inside double quotes is plain", GA,
     "                elif char == '\"' and here == \"$\":\n",
     "                elif False:\n",
     _T + "test_a_word_built_at_run_time_is_never_exempt"),
    ("gitAllow r6: a PowerShell quote may start mid-word", GA,
     "            if started or not words:\n",
     "            if not words:\n",
     _T + "test_round4_must_block_is_not_line_exempt"),
    ("gitAllow r6: a quoted PowerShell program word is a command", GA,
     "            if started or not words:\n",
     "            if started:\n",
     _T + "test_round5_a_powershell_line_pwsh_cannot_parse_is_not_exempt"),
    ("gitAllow r6: a PowerShell quote may end mid-word", GA,
     "        if closed and char not in \" \\t\":\n",
     "        if False:\n",
     _T + "test_round4_must_block_is_not_line_exempt"),
    ("gitAllow r6: a PowerShell leading ~ or @ is plain", GA,
     "        elif char in \"~@\" and not started:\n",
     "        elif False:\n",
     _T + "test_a_powershell_word_expanded_at_run_time_is_never_exempt"),
    ("gitAllow r6: PowerShell's --% alone is plain", GA,
     "    if not words or any(w == \"--%\" or _PS_PERCENT_RE.search(w) for w in words):\n",
     "    if not words or any(_PS_PERCENT_RE.search(w) for w in words):\n",
     _T + "test_a_powershell_word_expanded_at_run_time_is_never_exempt"),
    ("gitAllow r6: a PowerShell %NAME% word is plain", GA,
     "    if not words or any(w == \"--%\" or _PS_PERCENT_RE.search(w) for w in words):\n",
     "    if not words or any(w == \"--%\" for w in words):\n",
     _T + "test_a_powershell_word_expanded_at_run_time_is_never_exempt"),
    ("splitter r6: a continuation may split an fd prefix (BLOCK 3)", GU,
     "        raise _Unsure(\"a line continuation inside a redirection's fd prefix\")\n",
     "        return\n",
     _T + "test_round6_the_splitters_refuse_a_continuation_inside_an_fd_prefix"),
    ("splitter r6: a heredoc delimiter may end in a dangling backslash (BLOCK 2)", GU,
     "    return (len(raw) - len(raw.rstrip(\"\\\\\"))) % 2 == 1\n",
     "    return False\n",
     _T + "test_round6_the_splitters_refuse_a_heredoc_delimiter_with_a_dangling_backslash"),
)

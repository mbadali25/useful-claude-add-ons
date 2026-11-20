"""The owner-typed run approval mutations (crew 1.3.161). Same tuple shape as
`sabotage.py`'s MUTATIONS -- (label, target, find, replace, test) -- and
appended to it there. Run `sabotage.py`, not this file.

A receipt releases a command the guards keep for the owner, so each mutation
reintroduces one way a session could give itself that release or stretch one
it was given: the one use dropped, a binding dropped (command text, worktree,
class, session, the verify.json pin), the window dropped, a request answered
by an id nobody typed or by a payload that is not the owner's prompt, the
default-off dropped, a store left writable (its name spelled, or veiled by a
glob or a variable), the owner's command carried to another process, Claude
resumed on this session, a line break read as the end of a word, a store
check that raises read as an allow. Every target is a case in
`test_allow_run.py`.
"""
import os

CREW = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_S = os.path.join(CREW, "hooks", "scripts")
MODULE = os.path.join(_S, "crew_runapproval.py")
HOOK = os.path.join(_S, "approval_hook.py")
WRAPPER = os.path.join(_S, "approval-hook.sh")
DISPATCHER = os.path.join(_S, "crew_hook.py")
TRUST = os.path.join(_S, "verify_trust.py")
GUARD = os.path.join(_S, "scope_guard.py")
CHECKER = os.path.join(os.path.dirname(os.path.dirname(CREW)), "scripts", "check-tooling-pr.py")

_T = "tests/test_allow_run.py::"
_FALLBACK = ('    path = _file(cwd, "requests", ident)\n    record = _read(path)\n'
             '    if record is None and len(_records(cwd, "requests")) == 1:\n'
             '        path, record = _records(cwd, "requests")[0]\n'
             '        ident = record["id"] if isinstance(record, dict) else ident\n')

RUNAPPROVAL_MUTATIONS = (
    ("run approval: a receipt is read, not taken, so it can be used again", MODULE,
     '    receipt = _claim(_file(root, "receipts", ident))\n',
     '    receipt = _read(_file(root, "receipts", ident))\n',
     _T + "test_a_spent_receipt_is_refused_by_the_guard_and_by_the_tool"),
    ("run approval: the worktree is dropped from the receipt's binding", MODULE,
     '    if receipt["worktree"] != worktree:\n'
     '        return f"receipt {ident} belongs to another worktree"\n', "",
     _T + "test_a_receipt_is_refused_in_another_worktree"),
    ("run approval: the class is dropped from the receipt's binding", MODULE,
     '    if receipt["class"] != cls:\n', "    if False:\n",
     _T + "test_a_receipt_is_refused_for_another_class"),
    ("run approval: the receipt's window is not checked", MODULE,
     '    if not receipt["minted"] <= now <= receipt["expires"]:\n', "    if False:\n",
     _T + "test_a_receipt_outside_its_window_is_refused[expired]"),
    ("run approval: a receipt dated in the future is live", MODULE,
     '    if not receipt["minted"] <= now <= receipt["expires"]:\n',
     '    if now > receipt["expires"]:\n',
     _T + "test_a_receipt_outside_its_window_is_refused[future-dated]"),
    ("run approval: the request's window is not checked", MODULE,
     '    if not record["created"] <= now <= record["expires"]:\n', "    if False:\n",
     _T + "test_a_request_outside_its_window_mints_nothing[expired]"),
    ("run approval: an id nobody typed answers the only pending request", MODULE,
     '    path = _file(cwd, "requests", ident)\n    record = _read(path)\n', _FALLBACK,
     _T + "test_a_prompt_that_is_not_exactly_the_command_and_the_id_mints_nothing[mistyped]"),
    ("run approval: a prompt from another session (a child claude) mints", MODULE,
     '    if not isinstance(session, str) or not session or record["session_id"] != session:\n',
     "    if False:\n",
     _T + "test_a_prompt_from_another_session_mints_nothing"),
    ("run approval: an id raised in another worktree mints", MODULE,
     '    if record["worktree"] != worktree_of(cwd):\n', "    if False:\n",
     _T + "test_an_id_from_another_repo_mints_nothing"),
    ("run approval: a request can be answered more than once", MODULE,
     '    if _claim(path) is None:\n'
     '        raise Refused(f"request {ident} was answered a moment ago")\n', "",
     _T + "test_a_request_is_answered_once"),
    ("run approval: the verify.json pin is not held when the owner answers", MODULE,
     "    _check_pin(record)\n", "",
     _T + "test_a_verify_json_edited_after_the_request_mints_nothing"),
    ("run approval: the verify.json pin is not held at the spend", MODULE,
     '    if why is None and receipt.get("pin") != pin:\n', "    if False:\n",
     _T + "test_a_verify_json_edited_after_the_receipt_is_not_approved"),
    ("run approval: any live receipt releases any plain trust command", MODULE,
     '    if why is None and receipt["command_sha256"] != command_sha(command):\n', "    if False:\n",
     _T + "test_a_receipt_for_one_command_does_not_release_another"),
    ("run approval: the tool spends a receipt for other arguments", MODULE,
     '    if why is None and receipt["action"] != action:\n', "    if False:\n",
     _T + "test_the_tool_refuses_other_arguments_and_the_receipt_is_gone"),
    ("run approval: a receipt given in another session releases the command", MODULE,
     '    if why is None and receipt["session_id"] != session:\n', "    if False:\n",
     _T + "test_a_receipt_from_another_session_does_not_release_the_command"),
    ("run approval: a verb the owner closed is still spent", MODULE,
     '    if why is None and cls == CLASS_TRUST and action.get("verb") not in conf["verbs"]:\n',
     "    if False:\n",
     _T + "test_a_verb_closed_after_the_receipt_is_not_run"),
    ("run approval: a verb the owner did not open gets a request", MODULE,
     '    if action["verb"] not in conf["verbs"]:\n', "    if False:\n",
     _T + "test_anything_but_the_plain_opened_form_is_refused_with_no_request"
          "[verb-not-opened-revoke]"),
    ("run approval: with the class off the guard still records a request", MODULE,
     '    if CLASS_TRUST not in conf["classes"]:\n        return False, []\n',
     '    if False:\n        return False, []\n',
     _T + "test_with_the_class_off_the_refusal_is_unchanged_and_nothing_is_recorded"),
    ("run approval: with the class off the owner's command still mints", MODULE,
     '    if record["class"] not in conf["classes"]:\n', "    if False:\n",
     _T + "test_with_the_class_off_the_owners_command_mints_nothing"),
    ("run approval: with the class off a receipt is still spent", MODULE,
     '    conf = settings(root)\n    if cls not in conf["classes"]:\n',
     "    conf = settings(root)\n    if False:\n",
     _T + "test_with_the_class_off_a_receipt_spends_nothing"),
    ("run approval: a HOME inside the project is read as the machine's", MODULE,
     "        if folder and _inside(path, folder):\n            return None\n",
     "        if False:\n            return None\n",
     _T + "test_a_home_inside_the_repo_turns_nothing_on"),
    ("run approval: a duplicate key in the machine config is accepted", MODULE,
     "            parsed = json.load(handle, object_pairs_hook=_no_duplicate_keys)\n",
     "            parsed = json.load(handle)\n",
     _T + "test_a_machine_config_that_does_not_say_so_plainly_is_off[duplicate-run-on-last]"),
    ("run approval: a word a shell would split or expand passes as plain", MODULE,
     "    if any(not _whole(_PLAIN_RE, word) for word in words):\n        return None\n",
     "    if False:\n        return None\n",
     _T + "test_a_separator_glued_to_a_word_gets_no_request"),
    ("run approval: a copy of the trust script under another path gets a request", MODULE,
     "        if _canon(rest[0], cwd) != _canon(os.path.join(scripts, TRUST_SCRIPT)):\n"
     "            return None\n",
     "        if False:\n            return None\n",
     _T + "test_anything_but_the_plain_opened_form_is_refused_with_no_request[copied-script]"),
    ("run approval: with no class on the store refusals still apply", MODULE,
     '    if not settings(anywhere=True)["classes"]:\n        return None\n', "",
     _T + "test_with_the_class_off_no_store_refusal_applies[crew-dir-variable]"),
    ("run approval: with no class on a fault in the store check still refuses", MODULE,
     '    if not settings(anywhere=True)["classes"]:\n        return None\n', "",
     _T + "test_with_the_class_off_a_broken_store_check_is_never_reached"),
    ("run approval: the store check judges nothing with a class on either", MODULE,
     '    if not settings(anywhere=True)["classes"]:\n', "    if True:\n",
     _T + "test_a_shell_command_naming_the_store_is_refused_with_the_guard_off[touch-marker]"),
    ("run approval: standing in the machine's own crew directory turns the store check off",
     MODULE, '    if not settings(anywhere=True)["classes"]:\n',
     '    if not settings(data.get("cwd"))["classes"]:\n',
     _T + "test_a_relative_glob_is_read_from_the_directory_the_command_runs_in[in-crew-dir]"),
    ("run approval: a shell command naming the store is allowed", MODULE,
     "    if _STORE_NAME_RE.search(text) and not _read_rows_only(reading, tool):\n", "    if False:\n",
     _T + "test_a_shell_command_naming_the_store_is_refused_with_the_guard_off[touch-marker]"),
    ("run approval: a store name split by quotes is not read", MODULE,
     '            for text, undropped in ((dropped, reading),\n'
     '                                    (_QUOTE_RE.sub("", dropped), _QUOTE_RE.sub("", reading))):\n',
     "            for text, undropped in ((dropped, reading),):\n",
     _T + "test_a_shell_command_naming_the_store_is_refused_with_the_guard_off[quotes-in-name]"),
    ("run approval: a store command with a redirect passes as a read", MODULE,
     '                if reason and not read_only(_GLOB_RE.sub("_", reading)):\n',
     '                if reason and "cat " not in reading:\n',
     _T + "test_a_shell_command_naming_the_store_is_refused_with_the_guard_off"
          "[read-with-redirect]"),
    ("run approval: a store name veiled by a glob or a variable is not read", MODULE,
     '    if _veiled_store(text, data.get("cwd"), reading, tool):\n', "    if False:\n",
     _T + "test_a_shell_command_veiling_the_store_name_is_refused_with_the_guard_off[star]"),
    ("run approval: an unexpanded variable is read as a literal word", MODULE,
     '    veiled = _EXPANSION_RE.sub(_ANY, text)\n', "    veiled = text\n",
     _T + "test_a_shell_command_veiling_the_store_name_is_refused_with_the_guard_off"
          "[braced-variable]"),
    ("run approval: a bracket expression is read as literal characters", MODULE,
     '        elif char == "?" or close > 0:\n', '        elif char == "?":\n',
     _T + "test_a_shell_command_veiling_the_store_name_is_refused_with_the_guard_off[bracket]"),
    ("run approval: a glob spelling four letters of the store name passes on its own", MODULE,
     "            if literals >= 4:\n                four = True\n",
     "            if False:\n                four = True\n",
     _T + "test_with_a_class_on_a_shape_no_excuse_recognises_is_still_refused[O19]"),
    ("run approval: a variable beside a named crew dir is not read as the store", MODULE,
     "            if named and not inside:\n                return True\n",
     "            if False:\n                return True\n",
     _T + "test_a_shell_command_veiling_the_store_name_is_refused_with_the_guard_off"
          "[variable-beside-crew-dir]"),
    ("run approval: a variable before a store child is not read as the store", MODULE,
     "            if i + 1 < len(parts) and any(", "            if False and any(",
     _T + "test_a_shell_command_veiling_the_store_name_is_refused_with_the_guard_off"
          "[variable-before-receipts]"),
    ("run approval: a glob right under .claude/crew is not read as the store", MODULE,
     '            if i >= 2 and _could_be(parts[i - 1], "crew", 2)',
     '            if False and _could_be(parts[i - 1], "crew", 2)',
     _T + "test_a_shell_command_veiling_the_store_name_is_refused_with_the_guard_off[crew-dir-star]"),
    ("run approval: a relative glob is not read from the directory the command runs in", MODULE,
     "        parts = [] if rooted else list(base)\n", "        parts = []\n",
     _T + "test_a_relative_glob_is_read_from_the_directory_the_command_runs_in[in-crew-dir]"),
    ("run approval: with a class on, claude resumed with its prompt in a file is allowed", MODULE,
     "    if started and (_RESUME_RE.search(text[started.end():]) or _UNREAD_RE.search(text)):\n",
     "    if False:\n",
     _T + "test_with_a_class_on_claude_started_on_an_existing_session_is_refused_with_the_guard_off"
          "[resume-stdin]"),
    ("run approval: `$` reads a trailing line feed as the end of an id or a word", MODULE,
     "    return pattern.fullmatch(text) is not None\n",
     '    return re.match("^(?:" + pattern.pattern + ")$", text, pattern.flags) is not None\n',
     _T + "test_an_id_with_a_line_break_is_not_an_id[line-feed]"),
    ("run approval: a command holding a line break is read as one line", MODULE,
     '    if "\\n" in command or "\\r" in command:\n        return None\n', "",
     _T + "test_a_command_holding_a_line_break_gets_no_request[trailing-line-feed]"),
    ("run approval: a store check that raises is allowed outside block and auto", GUARD,
     "    except Exception as exc:  # pylint: disable=broad-except\n        unjudged = (",
     "    except Exception as exc:  # pylint: disable=broad-except\n        raise\n"
     "        unjudged = (",
     _T + "test_a_store_check_that_raises_refuses_the_call_with_the_guard_off[bash]"),
    ("run approval: a Write or Edit under the store is allowed", MODULE,
     "    for target in _targets(tool_input):\n", "    for target in []:\n",
     _T + "test_a_write_or_edit_under_the_store_is_refused_with_the_guard_off"),
    ("run approval: a command carrying the owner's command and an id is allowed", MODULE,
     "    if _OWNER_COMMAND_RE.search(undropped):\n", "    if False:\n",
     _T + "test_a_command_carrying_the_owners_command_and_an_id_is_refused[claude-p]"),
    ("run approval: the owner's command with a variable where the id goes is allowed", MODULE,
     r'(?:\bar-[0-9a-f]{12}\b|[$`%]))",', r'(?:\bar-[0-9a-f]{12}\b))",',
     _T + "test_a_command_carrying_the_owners_command_and_an_id_is_refused[variable-id]"),
    ("run approval: code run beside the module is allowed", MODULE,
     "    if (_MODULE_RE.search(text) and _RUNS_CODE_RE.search(text)\n"
     "            and not _named_excused(reading, tool)):\n", "    if False:\n",
     _T + "test_code_run_beside_the_module_is_refused[dash-m]"),
    ("run approval: with a class on, a command naming the prompt hook is allowed", MODULE,
     '        if settings(cwd)["classes"]:\n            return ("it names the prompt hook',
     '        if False:\n            return ("it names the prompt hook',
     _T + "test_with_a_class_on_a_command_naming_the_prompt_hook_is_refused_with_the_guard_off"
          "[approval-hook]"),
    ("run approval: a receipt may claim a life longer than the maximum", MODULE,
     '                and 0 < record["expires"] - record["minted"] <= MAX_TTL)\n',
     '                and 0 < record["expires"] - record["minted"])\n',
     _T + "test_a_receipt_claiming_a_longer_life_than_the_maximum_is_refused"),
    ("run approval: a record may show one command and carry the sha of another", MODULE,
     '    if record["command_sha256"] != command_sha(record["command"]):\n        return False\n',
     "",
     _T + "test_a_request_showing_one_command_and_carrying_the_sha_of_another_mints_nothing"),
    ("run approval: a request may claim a life longer than its window", MODULE,
     '    return 0 < record["expires"] - record["created"] <= REQUEST_TTL\n',
     "    return True\n",
     _T + "test_a_request_claiming_a_longer_life_than_its_window_mints_nothing"),
    ("run approval: a machine config nested too deep raises out of settings", MODULE,
     "    except (OSError, ValueError, RecursionError):  # RecursionError: a file nested too deep\n",
     "    except (OSError, ValueError):\n",
     _T + "test_a_machine_config_nested_too_deep_to_parse_is_off_and_refuses_nothing"),
    ("run approval: more requests than the cap may wait", MODULE,
     "    if len(pending) >= MAX_PENDING:\n", "    if False:\n",
     _T + "test_no_more_than_the_cap_of_requests_wait"),
    ("run approval: the hook mints from an event that is not the owner's prompt", HOOK,
     '    if not isinstance(data, dict) or data.get("hook_event_name") != "UserPromptSubmit":\n',
     "    if not isinstance(data, dict):\n",
     _T + "test_only_a_user_prompt_submit_payload_mints[PostToolUse]"),
    ("run approval: the hook takes the first of two ids", HOOK,
     "        if len(args.split()) != 1 or not crew_runapproval.valid_id(args):\n",
     "        args = (args.split() or [''])[0]\n        if not crew_runapproval.valid_id(args):\n",
     _T + "test_a_prompt_that_is_not_exactly_the_command_and_the_id_mints_nothing[two-ids]"),
    ("run approval: verify_trust --receipt confirms without spending a receipt", TRUST,
     "        return _spend_receipt(grant, pin)\n", "        return True\n",
     _T + "test_an_id_nobody_minted_changes_nothing[unknown]"),
    ("run approval: a receipt that fails falls through to --yes", TRUST,
     "        return _spend_receipt(grant, pin)\n",
     "        if _spend_receipt(grant, pin):\n            return True\n",
     _T + "test_a_receipt_is_the_whole_answer_even_outside_a_session"),
    ("run approval: revoke --receipt runs without spending a receipt", TRUST,
     "    if grant is not None and not _spend_receipt(grant, None):\n        return 1\n", "",
     _T + "test_a_verb_closed_after_the_receipt_is_not_run"),
    ("run approval: the bash wrapper drops a prompt with no `approve` in it", WRAPPER,
     'case "$INPUT" in *crew:allow-run*) ;; *)\n',
     'case "$INPUT" in *crew:never-typed*) ;; *)\n',
     _T + "test_the_owners_prompt_mints_through_each_hook_flavour[sh]"),
    ("run approval: the dispatcher's pre-filter drops the owner's command", DISPATCHER,
     '    if b"crew:allow-run" in raw:\n        return True\n', "",
     _T + "test_the_dispatchers_pre_filter_lets_the_owners_command_through"),
    ("tooling-pr: the run-approval module is feature work, so it cannot land with the hook",
     CHECKER, '    "plugin/crew/hooks/scripts/crew_runapproval.py",\n', "",
     _T + "test_the_module_is_harness_and_lands_with_the_hook"),
)


# --- R-20: the excuses of the store tripwire --------------------------------------------
#
# Each row reintroduces one too-loose reading of the R-20 excuses and must turn every id
# it names red. One entry per (row, id), so a row whose id stays green is seen as such;
# `sabotage.py` runs one pytest target per entry. A row that undoes TWO rules says so in
# its label. Rows S1-S26 of the spec's earlier revisions are withdrawn or restated here.

_BLOCK = _T + "test_with_a_class_on_a_shape_no_excuse_recognises_is_still_refused[{}]"
_ALLOW = _T + "test_with_a_class_on_a_recorded_everyday_command_is_allowed[{}]"
_CWD = _T + "test_with_a_class_on_a_relative_glob_is_placed_from_the_directory_it_runs_in[{}]"
_HOME = _T + "test_with_a_class_on_a_rooted_or_joined_word_built_from_the_home_is_refused[{}]"
_LINK = _T + "test_with_a_class_on_a_home_reached_through_a_link_is_read_in_both_forms"
_NATIVE = _T + "test_on_powershell_off_windows_cp_gets_no_copy_excuse"
_STORE_RE = 'r"(?<![\\w.-])run[-_]approvals(?![\\w-]|\\.\\w)", re.IGNORECASE)\n'
_SOURCE = "    return bool(variable.fullmatch(word) or literal.fullmatch(word))\n"
_SPLIT = '    words = re.split(r"[ \\t]+", reading.strip(" \\t"))\n'
_LAST_CREW = ('    reading = next((p for p in reversed(re.split(r";|&&|\\|\\||\\||\\n", reading))'
              ' if _CREW_DIR_RE.search(p)), reading)\n')
_SED_ALONE = '    if "sed" in rows and len(rows) != 1:\n        return False\n'
_SED_NAME = ('    if any(_sed_names_outside_files(cmd) for cmd, row in zip(cmds, rows) if row == "sed"):\n'
             "        return False\n")
_TABLE_CALL = "    return _all_on_table(_plain_commands(reading, tool), tool)\n"
_REV5_POLARITY = (
    '    return not any(re.fullmatch(r"python[0-9.]*|py|pypy[0-9.]*|bash|sh|zsh|dash|pwsh|powershell'
    '|node|\\.|source", (re.sub(r"^(?:(?:env|command|exec|nohup|time|sudo|xargs)\\s+)*", "", '
    'part.strip()).split() or [""])[0]) for part in re.split(r"[;&|\\n]", reading))\n')
_NAMED_ONLY = (
    "    cmds = _plain_commands(reading, tool)\n"
    "    return cmds is not None and all(_on_table(c, tool) for c in cmds if any("
    "_PROMPT_HOOK_RE.search(w.value) or _MODULE_RE.search(w.value) for w in c.words))\n")
_LINES_UP = (
    '        home = _segments(os.path.expanduser("~"), True) + [".claude", "crew", STORE_NAME]\n'
    "        return not (len(_segments(word, ps)) == len(home) and all("
    "fnmatch.fnmatch(t.lower(), w.lower()) for w, t in zip(_segments(word, ps), home)))\n")

_R20_ROWS = (
    ("S2 message dropping also drops double-quoted text holding $(",
     '                if "$" in bare or "`" in bare or (not ps and "\\\\" in body):\n',
     '                if "`" in bare or (not ps and "\\\\" in body):\n',
     [_BLOCK.format("message-substitution")]),
    ("S5 D7's last word may end at the crew dir itself",
     '_D7_LAST_RE = re.compile(r"~/\\.claude/crew(?:/[A-Za-z0-9_.-]+)+"',
     '_D7_LAST_RE = re.compile(r"~/\\.claude/crew(?:/[A-Za-z0-9_.-]+)*/?"',
     [_BLOCK.format("copy-into-crew-dir"), _BLOCK.format("copy-into-crew-dir-bare")]),
    ("S6 the store-name boundary needs a / or \\ after the name",
     "_STORE_NAME_RE = re.compile(" + _STORE_RE,
     '_STORE_NAME_RE = re.compile(r"(?<![\\w.-])run[-_]approvals(?=[/\\\\])", re.IGNORECASE)\n',
     [_BLOCK.format("python-join")]),
    ("S9 message dropping takes git wherever it stands, not only as the command word",
     "    head = 0\n",
     '    head = next((k for k in range(len(words) - 1) if words[k].value == "git"'
     ' and words[k + 1].value in ("commit", "tag")), 0)\n',
     [_BLOCK.format("git-after-another-word")]),
    ("S11 the store-name boundary is an enumerated list without ; and >",
     "_STORE_NAME_RE = re.compile(" + _STORE_RE,
     '_STORE_NAME_RE = re.compile(r"(?<![\\w.-])run[-_]approvals(?=[/\\\\\\s\'\\"]|$)", re.IGNORECASE)\n',
     [_BLOCK.format("semicolon-boundary")]),
    ("S14 D7's last word allows .. after the crew dir",
     '        if segment in (".", "..") or segment.endswith("."):\n',
     '        if segment == "." or (segment.endswith(".") and segment != ".."):\n',
     [_BLOCK.format("crew-dir-dotdot")]),
    ("S27 polarity: the hook and module excuses refuse only an interpreter first word (rev 5)",
     _TABLE_CALL, _REV5_POLARITY,
     [_BLOCK.format(i) for i in ("wrapper", "shell-keyword", "grouping", "variable-command-word",
                                 "find-exec", "ps-block", "module-wrapper")]),
    ("S28 only the simple commands that hold a name must be on the table",
     _TABLE_CALL, _NAMED_ONLY, [_BLOCK.format("cat-pipe-python")]),
    ("S29 a table command accepts any flag",
     "            return None  # an unlisted flag takes the command off the table\n",
     "            width = 1\n",
     [_BLOCK.format(i) for i in ("pylint-init-hook", "rg-pre", "pytest-p", "git-ext-diff")]),
    ("S30 a redirect and its target are read apart in a plain reading",
     '            elif self.loose and char in "<>" and self.target is None:\n',
     '            elif char in "<>" and self.target is None:\n',
     [_BLOCK.format("redirect-copy")]),
    ("S31 leading assignments are stripped before the command word is read",
     '    words = cmd.words\n    ps = tool == "PowerShell"\n    name = _program(words[0], tool)\n',
     '    words = cmd.words[next((k for k, w in enumerate(cmd.words) if not re.fullmatch('
     'r"[A-Za-z_][A-Za-z0-9_]*=.*", w.value)), 0):]\n'
     '    ps = tool == "PowerShell"\n    name = _program(words[0], tool)\n',
     [_BLOCK.format("assignment-prefix")]),
    ("S32 any sed script is accepted",
     "        if parts is None or not _sed_script_ok(parts[1].value):\n",
     "        if parts is None:\n",
     [_BLOCK.format("sed-exec-bare")]),
    ("S33 any -m module is on the table",
     "    if spec is None:  # a module not on the list is off the table\n        return None\n",
     '    if spec is None:\n        spec = _spec("")\n',
     [_BLOCK.format("runner-module")]),
    ("S34 a store name is excused beside any table row, not only RO",
     "    return rows is not None and all(row in _RO_ROWS for row in rows)\n",
     "    return rows is not None\n",
     [_BLOCK.format("rm-store-table")]),
    ("S35 a claude word that is not a command word is skipped",
     "            return False  # (2) a claude word that is not a whole command word\n",
     "            continue\n",
     [_BLOCK.format("claude-wrapper"), _BLOCK.format("claude-keyword")]),
    ("S36 a backslash escapes a double quote on PowerShell too",
     "            close = text.find(char, i + 1)\n",
     '            close = next((k for k in range(i + 1, len(text)) if text[k] == char'
     ' and text[k - 1] != "\\\\"), -1)\n',
     [_BLOCK.format("ps-backslash-quote")]),
    ("S37 a rooted word is placed unless it lines up with expanduser('~')",
     "        return False  # every other root form is not placed (/c/, //host, /proc, /opt ...)\n",
     _LINES_UP, [_HOME.format("msys-root")]),
    ("S38 a relative word holding .. is read as staying under the cwd",
     "            return False  # a climb leaves the directory the word is read from\n",
     "            continue\n",
     [_CWD.format("relative-climb")]),
    ("S39 a relative word with no string cwd is placed",
     "        return False  # a relative word with no string cwd is not placed\n",
     "        return True\n",
     [_CWD.format("relative-no-cwd")]),
    ("S40 the cwd test of the relative form is removed",
     '    return not above and not any(_under(form, os.path.join(home, ".claude"))\n'
     "                                 for form in forms for home in homes)\n",
     "    return True\n",
     [_CWD.format("cwd-home-rm"), _CWD.format("cwd-under-claude")]),
    ("S41 find's roots are not judged, only its pattern word",
     "        roots, patterns = (parts[0] or [_DOT], parts[1]) if parts else ((), set())\n",
     "        roots, patterns = (), set()\n",
     [_BLOCK.format("find-from-home-delete")]),
    ("S42 D6 (1) asks only the candidate's own command to be on the table",
     "    if not _all_on_table(cmds, tool):  # D6 (1)\n",
     "    if cmds is None or not all(_on_table(c, tool) for c in cmds"
     " if any(_holds_four(w.value) for w in c.words)):\n",
     [_BLOCK.format("cd-chain")]),
    ("S43 D7's shape accepts any first word made of letters",
     "    if kind is None:  # D7: only cp, mv, Copy-Item, Move-Item\n        return False\n",
     '    if kind is None and not head.isalpha():\n        return False\n    kind = kind or "copy"\n',
     [_BLOCK.format("rm-beside-crew-word")]),
    ("S44 D6 compares against the home as written only, never its real path",
     "    homes = {os.path.abspath(home), os.path.realpath(home)}\n",
     "    homes = {os.path.abspath(home)}\n",
     [_LINK]),
    ("S45 a placed word may hold , and :",
     '_PS_PLACED_RE = re.compile(r"[A-Za-z0-9_.*?\\[\\]/\\\\-]+", re.ASCII)\n',
     '_PS_PLACED_RE = re.compile(r"[A-Za-z0-9_.*?\\[\\]/\\\\,:-]+", re.ASCII)\n',
     [_HOME.format(i) for i in ("ps-comma-array", "ps-comma-array-fwd", "ps-provider")]),
    ("S46 D7's flag form accepts any word that starts with -",
     "    if ps:\n        return word.lower() in _D7_PS_FLAGS[kind]\n"
     "    return _D7_BASH_FLAGS[kind].fullmatch(word) is not None\n",
     "    return True\n",
     [_BLOCK.format(i) for i in ("cp-target-flag", "cp-target-long", "ps-destination-first",
                                 "ps-path-named-copy", "ps-literalpath-named-move", "cp-double-dash")]),
    ("S47 D5 reads the raw words, quotes kept",
     '        own = " ".join(word.value for word in args)\n',
     '        own = " ".join(reading[word.start:word.end] for word in args)\n',
     [_BLOCK.format("claude-quoted-flag"), _BLOCK.format("claude-quoted-flag-dq")]),
    ("S48 pylint --output-format= accepts any value",
     'checks={"--output-format=": lambda value: value in _PYLINT_FORMATS}',
     'checks={"--output-format=": lambda value: True}',
     [_BLOCK.format("pylint-output-file")]),
    ("S49 a non-RO row may stand after a PowerShell pipe",
     '        if tool == "PowerShell" and cmd.after == "|" and row not in _RO_ROWS:\n'
     "            return None\n",
     "        if False:\n            return None\n",
     [_BLOCK.format("ps-pipe-into-write")]),
    ("S50 D7 admits -Path and -LiteralPath on PowerShell",
     '_D7_PS_FLAGS = {"copy": ("-recurse", "-force"), "move": ("-force",)}\n',
     '_D7_PS_FLAGS = {"copy": ("-recurse", "-force", "-path", "-literalpath"),'
     ' "move": ("-force", "-path", "-literalpath")}\n',
     [_BLOCK.format(i) for i in ("ps-path-named-copy", "ps-literalpath-named-move",
                                 "ps-cp-alias-literalpath", "ps-mv-alias-path", "ps-path-first-copy")]),
    ("S52 on PowerShell cp and mv read the Bash letter lists",
     "    if ps:\n        return word.lower() in _D7_PS_FLAGS[kind]\n",
     '    if ps and head not in ("cp", "mv"):\n        return word.lower() in _D7_PS_FLAGS[kind]\n',
     [_BLOCK.format("ps-cp-bash-letters")]),
    ("S53 D7 reads a quoted or escaped Bash word as a source (rev 8)",
     '    for word in words[1:-1]:\n',
     '    for word in words[1:-1]:\n'
     '        word = word if ps or not set(word) & {"\'", \'"\', chr(92)} else "$Q"\n',
     [_BLOCK.format(i) for i in ("cp-quoted-target-flag", "cp-dquoted-target-flag",
                                 "cp-part-quoted-target-flag", "cp-escaped-target-flag",
                                 "cp-quoted-target-long", "mv-quoted-target-flag",
                                 "cp-dquoted-source")]),
    ("S54 a D7 source may hold characters outside ASCII",
     _SOURCE, '    word = word.encode("ascii", "ignore").decode() or "x"\n' + _SOURCE,
     [_BLOCK.format(i) for i in ("ps-endash-destination", "ps-emdash-destination-move",
                                 "ps-hbar-destination")]),
    ("S55 a comma is a D7 source character",
     _SOURCE, '    word = word.replace(",", "") or "x"\n' + _SOURCE,
     [_BLOCK.format("ps-comma-word-sources-alone")]),
    ("S56 D7 tests only the copy's own simple command, not the whole reading",
     _SPLIT, _LAST_CREW + _SPLIT,
     [_BLOCK.format(i) for i in ("cp-assignment-same-command", "ps-alias-shadow", "cp-after-mkdir",
                                 "ps-lone-operand", "ps-lone-operand-recurse")]),
    ("S57 two rules undone: a comma is a source and only the copy's own command is tested",
     _SPLIT, _LAST_CREW.replace("reading)\n", 'reading).replace(",", "")\n') + _SPLIT,
     [_BLOCK.format(i) for i in ("ps-comma-sources", "ps-comma-word-sources", "ps-comma-sources-move")]),
    ("S58 a glob is a D7 source character",
     _SOURCE, '    word = re.sub(r"[*?\\[\\]]", "", word) or "x"\n' + _SOURCE,
     [_BLOCK.format("cp-glob-source")]),
    ("S59 a D7 source may be a variable followed by literal characters",
     _SOURCE, ('    head = variable.match(word)\n    if head and literal.fullmatch(word[head.end():] or "x"):\n'
               '        return True\n') + _SOURCE,
     [_BLOCK.format("cp-mixed-word")]),
    ("S60 (b1) removed: a message is dropped whenever the reading is plain (rev 9)",
     "        if message is None and not _beside_message(cmd, tool):\n"
     "            return reading  # (b1): something beside the message could run it\n",
     "",
     [_BLOCK.format(i) for i in ("msg-launder-store", "msg-launder-hook", "msg-launder-module",
                                 "msg-launder-claude", "msg-launder-tag", "msg-launder-gh",
                                 "msg-launder-ps", "msg-launder-editmsg", "msg-launder-sed-pytest",
                                 "msg-launder-sed-doctest")]),
    ("S61 the message rows accept any flag",
     '        operands = _fit(words[first:], spec, tool == "PowerShell")\n',
     '        operands = [w for w in words[first:] if not w.value.startswith("-")]\n',
     [_BLOCK.format("msg-tag-sign")]),
    ("S62 cp and mv are Copy-Item / Move-Item on every PowerShell",
     '    if ps and head in ("cp", "mv") and not _ps_cp_is_alias():\n',
     '    if ps and head in ("cp", "mv") and not True:\n',
     [_NATIVE]),
    ("S63 any table row may stand beside a dropped message (rev 10)",
     "    return row in _BESIDE_MESSAGE\n", "    return row is not None\n",
     [_BLOCK.format(i) for i in ("msg-launder-sed-pytest", "msg-launder-sed-doctest",
                                 "msg-pytest-then-commit", "msg-sed-then-commit", "msg-commit-then-rm",
                                 "msg-ps-commit-then-remove")]),
    ("S64 two rules undone: sed stands beside other rows with any name (rev 11)",
     _SED_ALONE + _SED_NAME, "",
     [_BLOCK.format(i) for i in ("sed-guard-pytest-stdin", "sed-gitconfig-extdiff",
                                 "sed-gitconfig-fsmonitor", "sed-pyproject-pylint-inithook",
                                 "sed-script-names-hook", "sed-script-names-module",
                                 "sed-suffix-names-hook", "sed-then-add", "sed-two-seds",
                                 "sed-then-pytest-tests")]),
    ("S65 sed need not stand alone", _SED_ALONE, "",
     [_BLOCK.format(i) for i in ("sed-guard-pytest-stdin", "sed-gitconfig-extdiff", "sed-then-add",
                                 "sed-two-seds", "sed-then-pytest-tests")]),
    ("S66 a sed may name a hook or the module outside its file operands", _SED_NAME, "",
     [_BLOCK.format(i) for i in ("sed-script-names-hook", "sed-script-names-module",
                                 "sed-suffix-names-hook")]),
    ("S67 an @file operand on a python -m row is read as an operand",
     '    if any(word.value.startswith("@") for word in rest[2:]):\n', "    if False:\n",
     [_BLOCK.format(i) for i in ("argfile-pytest-trace", "argfile-pytest-earlier-state")]),
    ("S68 a hook name in a message D4 (b1) kept is excused beside table rows",
     "    if reading is None or _names_in_messages(reading, tool):\n", "    if reading is None:\n",
     [_BLOCK.format("msg-pytest-then-commit")]),
    ("S69 a claude word inside a quoted argument is not counted by D5",
     '    if len(_CLAUDE_RE.findall(_QUOTE_RE.sub("", reading))) != len(matches):\n',
     "    if False:\n",
     [_BLOCK.format("msg-launder-claude")]),
    ("S70 D4 (b) reads a message flag after git's `--` (review round 1)",
     '        if word.value == "--":\n'
     "            break  # every word after `--` is a pathspec or operand, never a message\n", "",
     [_BLOCK.format(i) for i in ("msg-after-double-dash", "msg-after-double-dash-eq")]),
    ("S71 a D7 source may name the crew dir (review round 1)",
     "        if _CREW_DIR_RE.search(word):\n"
     "            return False  # only the destination may name the crew dir\n", "",
     [_BLOCK.format(i) for i in ("cp-crew-source-relative", "cp-crew-source-nested",
                                 "ps-crew-source-relative")]),
    ("S72 PowerShell quote spans close only on ASCII quotes (review round 2)",
     "            if ps and any(quote in body for quote in _PS_QUOTES):\n"
     "                raise _NotPlain  # PowerShell closes a quote on any of these, not only the ASCII one\n",
     "",
     [_BLOCK.format(i) for i in ("msg-ps-typographic-single", "msg-ps-typographic-double",
                                 "msg-ps-typographic-low")]),
    ("S73 D4 (b) does not consume a non-message flag's value word (review round 2)",
     "        width = _flag_width(args, k, spec) or 1\n",
     "        width = (_flag_width(args, k, spec) or 1) if word.value in flags else 1\n",
     [_ALLOW.format(i) for i in ("msg-label-double-dash", "msg-ps-label-double-dash")]),
)

def _case(target):
    """The id a target names, or its test's name when it has none."""
    return target[:-1].rsplit("[", 1)[1] if target.endswith("]") else target.rsplit("::", 1)[1]


R20_MUTATIONS = tuple((f"run approval R-20 {label} [{_case(target)}]", MODULE, find, replace, target)
                      for label, find, replace, targets in _R20_ROWS for target in targets)

RUNAPPROVAL_MUTATIONS += R20_MUTATIONS

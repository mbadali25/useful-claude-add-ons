"""What the owner's-files shell check does past what it reads (crew 1.3.151). Same tuple shape as `sabotage.py`'s
MUTATIONS -- (label, target, find, replace, test) -- appended to it there. Run `sabotage.py`, not this file.

Every limit in that check used to end in an allow: text nested a fourth level down was passed unread, a command
the guard could not finish was killed by the dispatcher and allowed where the repo is not armed, and an exception
in the check reached `main`, which allows what it could not judge unless `scope.mode` is block. Each entry puts one
of those allows back; every target is a case in `tests/test_guards_master_depth.py` (one in the shell corpus), and
each label says what its mutation lets through.
"""
import os

CREW = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCOPE = os.path.join(CREW, "hooks", "scripts", "scope_guard.py")
_D = "tests/test_guards_master_depth.py::"
_M = "tests/test_guards_master_shell.py::"
_BROAD = "except Exception as exc:  # noqa: BLE001  pylint: disable=broad-except\n"
_NARROW = "except ZeroDivisionError as exc:  # noqa: BLE001  pylint: disable=broad-except\n"

GUARDS_DEPTH_MUTATIONS = (
    # (A) the depth limit
    ("text nested past the depth limit is passed unread (the review's repro)", SCOPE,
     '    if depth > _DEPTH_LIMIT:\n        return _unread(text, shell)\n    outer = shell.pipeline\n',
     '    if depth > _DEPTH_LIMIT:\n        return None\n    outer = shell.pipeline\n',
     _D + "test_a_write_nested_past_what_the_guard_reads_is_refused"),
    ("the dispatcher allows the write nested four deep, in both scope modes", SCOPE,
     '    if depth > _DEPTH_LIMIT:\n        return _unread(text, shell)\n    outer = shell.pipeline\n',
     '    if depth > _DEPTH_LIMIT:\n        return None\n    outer = shell.pipeline\n',
     _D + "test_the_dispatcher_refuses_the_nested_write_in_both_scope_modes"),
    ("a script block or an alias past the depth limit is passed unread", SCOPE,
     '        return _unread(" ".join(seg.words), shell)\n',
     '        return None\n',
     _D + "test_a_block_or_an_alias_past_the_limit_is_refused"),
    ("unread text that holds a variable is passed when nothing names the owner", SCOPE,
     '    if named or near or _UNREAD_RE.search(text):\n',
     '    if named or near:\n',
     _D + "test_a_variable_in_unread_text_is_refused_though_nothing_names_the_owner"),
    ("unread text is judged by the command as written, not by what its variables made of it", SCOPE,
     '    named = shell.deep or shell.hint or _plausible(text)\n',
     '    named = shell.deep or shell.hint\n',
     _D + "test_a_path_spelled_only_after_its_variables_are_filled_in_is_refused"),
    ("the owner's folder named in a read does not count beside unread text", SCOPE,
     '        shell.deep = _plausible(command)\n',
     '        shell.deep = False\n',
     _D + "test_a_read_of_the_owners_file_beside_an_unread_write_is_refused"),
    ("everything nested past the depth limit is refused, benign or not", SCOPE,
     '    if named or near or _UNREAD_RE.search(text):\n',
     '    if True:\n',
     _D + "test_deep_nesting_that_names_nothing_of_the_owners_is_allowed"),
    ("an alias of its own name is expanded until the depth limit, then refused", SCOPE,
     '    if stands and _command_name(_expand(stands[0], shell)) == name:\n',
     '    if False:\n',
     _M + "test_ordinary_read_only_and_worktree_commands_are_allowed"),
    ("a quote mark spelled with a backslash is split the way it was (`echo 'it'\\''s' > <owner file>`)", SCOPE,
     '        if shell.deep and "\\\\\'" in command:\n',
     '        if False:\n',
     _D + "test_a_quote_mark_spelled_with_a_backslash_does_not_hide_the_write"),
    ("that quoting is refused beside any file", SCOPE,
     '        if shell.deep and "\\\\\'" in command:\n',
     '        if "\\\\\'" in command:\n',
     _D + "test_the_same_quoting_beside_another_file_is_allowed"),
    # (B) the work the guard does for one command
    ("the dispatcher's entry reads a command longer than the guard reads", SCOPE,
     '    if isinstance(command, str) and len(command) > _COMMAND_LIMIT:   # before anything reads it',
     '    if False:   # before anything reads it',
     _D + "test_a_long_command_is_refused_before_anything_reads_it"),
    ("a command longer than the guard reads is judged as far as it goes", SCOPE,
     '    if len(command) > _COMMAND_LIMIT:\n        return _TOO_LONG\n',
     '    if False:\n        return _TOO_LONG\n',
     _D + "test_a_command_longer_than_the_guard_reads_is_refused"),
    ("the store rule reads a command longer than the guard reads", SCOPE,
     '    if len(command) > _COMMAND_LIMIT:\n        return True\n',
     '    if False:\n        return True\n',
     _D + "test_a_command_longer_than_the_guard_reads_is_refused"),
    ("a variable that doubles with every command is followed without end", SCOPE,
     '    if len(word) > _WORD_LIMIT:',
     '    if False:',
     _D + "test_a_variable_that_doubles_with_every_command_is_refused_in_time"),
    ("the number of commands judged is not bounded", SCOPE,
     '    if shell.work[0] > _STEP_LIMIT:\n',
     '    if False:\n',
     _D + "test_more_commands_than_the_guard_judges_are_refused_in_time"),
    ("a command the guard cannot finish is passed by the dispatcher", SCOPE,
     '    except _Unread as exc:\n        return f"{OWNER_REASON}: the guard cannot read all of it ({exc}), so it '
     'cannot tell that it does not"\n',
     '    except _Unread:\n        return None\n',
     _D + "test_the_dispatcher_refuses_what_the_guard_cannot_finish_in_both_scope_modes"),
    # (C) a check that fails on its own input
    ("a shell check that raises hands the exception on (allowed outside scope.mode block)", SCOPE,
     '    ' + _BROAD + '        return (f"{OWNER_REASON}: the guard could not judge it',
     '    ' + _NARROW + '        return (f"{OWNER_REASON}: the guard could not judge it',
     _D + "test_a_shell_check_that_raises_refuses_the_command"),
    ("the store rule passes a command its check raised on", SCOPE,
     '        return True   # unread (`_Unread`) or unjudged',
     '        return False   # unread (`_Unread`) or unjudged',
     _D + "test_a_shell_check_that_raises_refuses_the_command"),
    ("the owner's-files rule hands main its exception with scope.mode off", SCOPE,
     '        return _owner_files_decision(tool, data, root)\n    ' + _BROAD,
     '        return _owner_files_decision(tool, data, root)\n    ' + _NARROW,
     _D + "test_the_owner_file_check_refuses_when_it_cannot_judge_with_scope_mode_off"),
    ("a path that cannot be resolved is not the owner's", SCOPE,
     '        return True   # a path that cannot be resolved',
     '        return False   # a path that cannot be resolved',
     _D + "test_a_path_that_cannot_be_resolved_is_the_owners"),
    ("the trust check passes what it could not judge", SCOPE,
     '        return _trust_refusal(data)\n    ' + _BROAD,
     '        return _trust_refusal(data)\n    ' + _NARROW,
     _D + "test_the_trust_check_refuses_when_it_cannot_judge"),
    # found by the PR's own Linux run: a file sed reads was read as its script
    ("every word of a sed is read as a script again (a home with `1w` in its path refuses a read)", SCOPE,
     '        return scripts if scripts or named else plain[:1]\n',
     '        return scripts + plain\n',
     _M + "test_a_file_sed_reads_is_not_its_script_whatever_the_homes_path_spells"),
    ("the values of sed's `-e` are not its script (`sed -n -e p -e \"w <owner file>\" a` passes)", SCOPE,
     '                scripts += args[position + 1:position + 2]\n',
     '                pass\n',
     _M + "test_a_file_sed_reads_is_not_its_script_whatever_the_homes_path_spells"),
)

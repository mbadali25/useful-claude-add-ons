"""The T-0040 mutations: `crew_shell.py`, the Windows shell route. Same tuple
shape as `sabotage.py`'s MUTATIONS -- (label, target, find, replace, test) --
and appended to it there. Run `sabotage.py`, not this file.

Each one is a way the shell route could touch a machine it promised to leave
alone, fall back without saying so, read an unknown as an answer, or hand a
bash string to a shell that does not speak bash.
"""
import os

CREW = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHELL = os.path.join(CREW, "hooks", "scripts", "crew_shell.py")
CREW_HOOK = os.path.join(CREW, "hooks", "scripts", "crew_hook.py")
_T = "tests/test_crew_shell.py::"
_U = "tests/test_crew_gitbash_unknown.py::"
_K = "tests/test_crew_hook_gitbash_kind.py::"
_S = "tests/test_status.py::"

SHELL_MUTATIONS = (
    ("decide routes away from bash -c on a Linux host", SHELL,
     '    if not on_windows(host):\n        return "bash", "", None\n',
     '    if False:\n        return "bash", "", None\n',
     _T + "test_decide_off_windows_is_bash_c"),
    ("a raising probe reports not-installed", SHELL,
     '        return None, None, None, ("unknown", f"{shown} could not run: {exc}")\n',
     '        return None, None, None, ("not-installed", f"{shown} could not run: {exc}")\n',
     _T + "test_probe_failure_is_unknown_not_absent"),
    ("the UTF-16 decode is removed", SHELL,
     '    if b"\\x00" in data:\n',
     "    if False:\n",
     _T + "test_decode_utf16_and_utf8"),
    ("to_wsl_path accepts another distro's \\\\wsl$ path", SHELL,
     "        if distro and owner.casefold() != distro.casefold():\n",
     "        if False:\n",
     _T + "test_to_wsl_path_refuses"),
    ("status_line prints on Linux", SHELL,
     "    if not on_windows():\n        return None\n",
     "    if False:\n        return None\n",
     _S + "test_status_has_no_shell_line_off_windows"),
    ("run drops the exit code", SHELL,
     "    return execute(job, root)\n",
     "    execute(job, root)\n    return 0\n",
     _T + "test_run_passes_exit_code_through"),
    ("the classifier treats a bash-syntax job as plain argv", SHELL,
     "        if hit:\n",
     "        if False:\n",
     _T + "test_classify_must_bash"),
    ("pwsh is resolved by the bare name pwsh", SHELL,
     '            return path, f"PowerShell at {path}"\n',
     '            return "pwsh", f"PowerShell at {path}"\n',
     _T + "test_resolve_pwsh"),
    ("Git Bash resolves to C:\\Windows\\System32\\bash.exe", SHELL,
     "        if not _is_launcher(found):\n",
     "        if True:\n",
     _T + "test_resolve_gitbash_never_returns_wsl_launcher"),
    # Review round 1 (T-0040-Bdt4JE).
    ("the classifier accepts an embedded /c/ path", SHELL,
     "        if _embeds_posix_path(token):\n",
     "        if False:\n",
     _T + "test_classify_refuses_an_embedded_c_path"),
    # Review round 2 (T-0040-LVY6bE).
    ("a usable cache with no distro reaches the launcher", SHELL,
     '    if data["state"] == "usable" and not (isinstance(distro, str) and distro):\n',
     "    if False:\n",
     _T + "test_a_usable_cache_without_a_distro_is_unknown"),
    # A slow Git Bash is could-not-tell, never "not found" (crew 1.3.41/1.3.42).
    ("strict Git Bash: a self-test timeout is reported as a broken bash", SHELL,
     '        return "unknown", f"did not answer within {timeout}s"\n',
     '        return "broken", f"did not answer within {timeout}s"\n',
     _U + "test_a_present_but_slow_git_bash_is_allowed_once_a_retry_answers"),
    ("strict Git Bash: an unanswered self-test is never retried", SHELL,
     '        if state == "broken":\n            return state, detail\n',
     '        if state != "ok":\n            return state, detail\n',
     _U + "test_a_present_but_slow_git_bash_is_allowed_once_a_retry_answers"),
    ("strict Git Bash: a resource-failure exit counts as a broken bash", SHELL,
     "    if _LOAD_STDERR.search(text):\n",
     "    if False:\n",
     _U + "test_a_bash_that_dies_on_a_resource_failure_is_unknown_not_broken"),
    ("strict Git Bash: the last known good ignores a changed file", SHELL,
     "        return bool(now) and all(data.get(key) == now[key] for key in now)\n",
     "        return bool(now)\n",
     _U + "test_a_changed_bash_exe_is_not_trusted_from_the_last_known_good"),
    ("strict Git Bash: no answer after the retries is reported as absent", SHELL,
     "    unknown = [item for item in trouble if item[0] == \"unknown\"]\n    if unknown:\n",
     "    if False:\n",
     _U + "test_a_present_git_bash_that_never_answers_blocks_as_unknown_with_bounded_attempts"),
    ("strict Git Bash: a git --exec-path timeout counts as absent", SHELL,
     "        exec_path, git_unknown = \"\", True\n",
     "        exec_path, git_unknown = \"\", False\n",
     _U + "test_git_exec_path_timing_out_with_no_candidate_file_is_unknown_not_absent"),
    ("dispatcher: every strict Git Bash failure says Install Git for Windows", CREW_HOOK,
     '    if kind == "absent":\n',
     "    if True:\n",
     _K + "test_unknown_blocks_armed_calls_but_never_says_install_git"),
    ("dispatcher: an unknown Git Bash lets the armed call through", CREW_HOOK,
     '    if event in BLOCKING_EVENTS and armed_fn(root):\n        return 2, b"", (message + "\\n").encode("utf-8")\n',
     '    if event in BLOCKING_EVENTS and armed_fn(root) and kind != "unknown":\n'
     '        return 2, b"", (message + "\\n").encode("utf-8")\n',
     _K + "test_unknown_blocks_armed_calls_but_never_says_install_git"),
)

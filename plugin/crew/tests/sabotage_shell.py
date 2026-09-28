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
_T = "tests/test_crew_shell.py::"
_S = "tests/test_status.py::"

SHELL_MUTATIONS = (
    ("decide routes away from bash -c on a Linux host", SHELL,
     '    if not on_windows(host):\n        return "bash", "", None\n',
     '    if False:\n        return "bash", "", None\n',
     _T + "test_decide_off_windows_is_bash_c"),
    ("mode wsl silently falls back to Git Bash", SHELL,
     '            return "refuse", f"shellRoute.mode wsl but {_wsl_state(probe_result)} {REFUSED}, no fallback", 3\n',
     '            return "gitbash", "shellRoute.mode wsl -> gitbash", None\n',
     _T + "test_decide"),
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
    ("powershell mode hands a bash string to pwsh", SHELL,
     '"gitbash": lambda: gitbash_argv(cmd, bash),',
     '"gitbash": lambda: pwsh_argv([cmd], pwsh) if pwsh else gitbash_argv(cmd, bash),',
     _T + "test_powershell_mode_never_hands_bash_to_pwsh"),
    ("pwsh is resolved by the bare name pwsh", SHELL,
     '            return path, f"PowerShell at {path}"\n',
     '            return "pwsh", f"PowerShell at {path}"\n',
     _T + "test_resolve_pwsh"),
    ("Git Bash resolves to C:\\Windows\\System32\\bash.exe", SHELL,
     "        if not _is_launcher(found):\n",
     "        if True:\n",
     _T + "test_resolve_gitbash_never_returns_wsl_launcher"),
)

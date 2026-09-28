"""T-0040: `crew_shell.py`, the Windows shell route for crew's long-running jobs.

No test here calls a real `wsl.exe`, `pwsh` or Git Bash on a routed path.
Every probe and every job goes through an injected `runner` / `execute`,
shell resolution goes through an injected `exists`, and the cache path
resolves beside `crew_state.GLOBAL_CONFIG_PATH`, which the suite's conftest
already points at a scratch path. The one real subprocess is the off-Windows
`bash -c` comparison, which is the property it asserts.
"""
import sys

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import crew_shell

# Every `run` entry of `.crew/verify.json` at 6387ab49 that is not a bare
# `python3 ...` argv, copied verbatim: rules 1, 3, 12, 13, 14, 15, 17, 18, 19
# and 21. Rule 3 also carries four plain `python3` entries; those are below.
VERIFY_MAP_BASH = (
    'bash _verify/smoke.sh',
    './scripts/_test/menu-groups.sh',
    'bash scripts/_test/check-powershell.sh',
    'bash scripts/_test/ps-install-keys.sh',
    'bash scripts/_test/uv-install.sh',
    'bash -n scripts/install-prerequisites.sh',
    '(cd plugin/crew && python3 hooks/scripts/_test/validate-prompts.py)',
    'bash plugin/crew/skills/crew-diagrams/scripts/_test/render.sh',
    'sh -c \'for c in pwsh pwsh.exe "/c/Program Files/PowerShell/7/pwsh" "/c/Program Files/PowerShell/7/pwsh.exe" "/mnt/c/Program Files/PowerShell/7/pwsh.exe" "/mnt/c/Program Files/PowerShell/7/pwsh"; do if command -v "$c" >/dev/null 2>&1 || [ -x "$c" ]; then exec "$c" -NoProfile -File ./scripts/check-powershell.ps1; fi; done; echo "TOOL MISSING: pwsh (PowerShell 7) is on no PATH and at no known Windows location, so the .ps1 checks DID NOT RUN. This is a missing tool, not a failed check. Install PowerShell 7." >&2; exit 77\'',  # noqa: E501  pylint: disable=line-too-long
    'sh -c \'python3 -m ruff --version >/dev/null 2>&1 || { echo "TOOL MISSING: ruff is not importable by this python3, so the ruff pass DID NOT RUN. This is a missing tool, not a passing check and not a failing one. CI still runs it. Install ruff to check locally." >&2; exit 77; }; exec python3 -m ruff check .\'',  # noqa: E501  pylint: disable=line-too-long
    'sh -c \'python3 -m pylint --version >/dev/null 2>&1 || { echo "TOOL MISSING: pylint is not importable by this python3, so the pylint pass DID NOT RUN. This is a missing tool, not a passing check and not a failing one. CI (pylint.yml, 3.11/3.12/3.13) still runs it. Install pylint to check locally." >&2; exit 77; }; exec python3 -m pylint $(git ls-files "*.py")\'',  # noqa: E501  pylint: disable=line-too-long
    'sh -c \'command -v npm >/dev/null 2>&1 || { echo "TOOL MISSING: npm is not on PATH, so the mcp-servers suite DID NOT RUN. This is a missing tool, not a passing check and not a failing one." >&2; exit 77; }; [ -d mcp-servers/node_modules ] || { echo "DEPENDENCY MISSING: mcp-servers/node_modules is absent, so npm test would die on a missing tsc. Run: npm --prefix mcp-servers install. The suite DID NOT RUN - this is an unmet precondition, not a passing check and not a failing one." >&2; exit 77; }; exec npm --prefix mcp-servers test\'',  # noqa: E501  pylint: disable=line-too-long
    'bash skills/bitbucket/scripts/_test/merge_gate.sh',
    'bash skills/doc-builder/scripts/_test/checklist.sh',
)

# A sample of the plain `python3` entries, copied verbatim from the same map.
VERIFY_MAP_PLAIN = (
    'python3 scripts/check-marketplace.py',
    'python3 scripts/_test/self-claims.py',
    'python3 scripts/sync-updates.py --check',
    'python3 -m pytest plugin/crew/tests/test_crew_config.py -q',
    'python3 -m pytest plugin/crew/tests/test_guards.py plugin/crew/tests/test_malformed_production_never_permits.py -q',  # noqa: E501  pylint: disable=line-too-long
    'python3 -m pytest plugin/crew/tests/ -q',
    'python3 -m pytest plugin/gizmoduck/scripts/_test/ -q',
    'python3 plugin/crew/hooks/scripts/crew_instructions.py rules --root . --check',
    'python3 -m pytest plugin/crew/tests/test_crew_tracker.py -q',
)

# (command, the offending token its reason must name)
MUST_BASH = (
    ("sh -c 'x'", "sh"),
    ("bash x.sh", "bash"),
    ("cd a", "cd"),
    ("a > b", ">"),
    ("a >> b", ">"),
    ("a < b", "<"),
    ("a | b", "|"),
    ("a && b", "&"),
    ("a & b", "&"),
    ("a; b", ";"),
    ("$(a)", "$"),
    ("`a`", "`"),
    ("a *.py", "*"),
    ("a ?.py", "?"),
    ("a [ab].py", "["),
    ("FOO=1 a", "FOO=1"),
    ("a ~/x", "~"),
    ("a /c/x", "/c/x"),
    ("./x.sh", "./x.sh"),
    ("source x", "source"),
    (". x", "'.'"),
    ("a\nb", "newline"),
    ("a\r\nb", "control"),
)


def _which_all(name):
    return "C:/tools/" + name + ".exe"


# --- Step 2: host OS, path translation, output decoding, repo location --------

@pytest.mark.parametrize("path,expected", [
    (r"C:\repos\x", "/mnt/c/repos/x"),
    ("D:/a b/c", "/mnt/d/a b/c"),
    ("/c/repos/x", "/mnt/c/repos/x"),
    (r"\\wsl$\Ubuntu\home\u\r", "/home/u/r"),
    (r"\\wsl.localhost\Ubuntu\home\u\r", "/home/u/r"),
    (r"c:\repos\x", "/mnt/c/repos/x"),
    ("C:\\repos\\x\\", "/mnt/c/repos/x"),
    ("C:\\", "/mnt/c"),
    ("//wsl.localhost/Ubuntu/home/u/r/", "/home/u/r"),
])
def test_to_wsl_path(path, expected):
    assert crew_shell.to_wsl_path(path, distro="Ubuntu") == (expected, "")
    assert crew_shell.to_wsl_path(path)[0] == expected


@pytest.mark.parametrize("path", [
    r"\\wsl$\Debian\home\u\r",
    r"\\wsl.localhost\Debian\home\u\r",
    r"\\server\share\repo",
    r"repos\x",
    "",
])
def test_to_wsl_path_refuses(path):
    translated, reason = crew_shell.to_wsl_path(path, distro="Ubuntu")
    assert translated is None
    assert reason


def test_to_wsl_path_names_the_other_distro():
    _, reason = crew_shell.to_wsl_path(r"\\wsl.localhost\Debian\home\u", distro="Ubuntu")
    assert "Debian" in reason and "Ubuntu" in reason


@pytest.mark.parametrize("path,expected", [
    (r"C:\repos\x", "windows-drive"),
    ("d:/x", "windows-drive"),
    ("/c/repos/x", "windows-drive"),
    (r"\\wsl$\Ubuntu\home\u\r", "wsl-fs"),
    (r"\\wsl.localhost\Ubuntu\home\u\r", "wsl-fs"),
    (r"\\server\share\x", "unknown"),
    ("/home/u/r", "unknown"),
    ("relative", "unknown"),
])
def test_repo_location(path, expected):
    assert crew_shell.repo_location(path) == expected


@pytest.mark.parametrize("data", [
    b"\xff\xfe" + "Ubuntu-24.04\r\n".encode("utf-16-le"),
    "Ubuntu-24.04\r\n".encode("utf-16-le"),
    "Ubuntu-24.04\r\n".encode("utf-8"),
    b"\xef\xbb\xbf" + "Ubuntu-24.04\r\n".encode("utf-8"),
])
def test_decode_utf16_and_utf8(data):
    assert crew_shell.decode(data) == "Ubuntu-24.04\r\n"


def test_decode_empty_and_none():
    assert crew_shell.decode(b"") == ""
    assert crew_shell.decode(None) == ""


@pytest.mark.parametrize("system,env,osrelease,expected", [
    ("Windows", {}, None, "windows"),
    ("Windows", {"MSYSTEM": "MINGW64"}, None, "windows-bash"),
    ("MSYS_NT-10.0-26200", {}, None, "windows-bash"),
    ("Linux", {}, "6.8.0-45-generic", "linux"),
    ("Linux", {}, "5.15.167.4-microsoft-standard-WSL2", "wsl"),
    ("Darwin", {}, None, "macos"),
])
def test_host_os(system, env, osrelease, expected):
    assert crew_shell.host_os(system=system, env=env, osrelease=osrelease) == expected


# --- Step 3: the argv classifier and absolute shell resolution ----------------

@pytest.mark.parametrize("cmd", VERIFY_MAP_PLAIN)
def test_classify_must_plain(cmd):
    kind, argv, reason = crew_shell.classify(cmd, which=lambda _name: None)
    assert kind == "plain", reason
    assert argv == [sys.executable] + cmd.split()[1:]


def test_classify_plain_resolves_other_argv0_absolutely():
    kind, argv, _ = crew_shell.classify("graphify . --no-viz --code-only", which=_which_all)
    assert (kind, argv) == ("plain", ["C:/tools/graphify.exe", ".", "--no-viz", "--code-only"])


@pytest.mark.parametrize("cmd", VERIFY_MAP_BASH)
def test_classify_verify_map_bash_entries(cmd):
    kind, argv, reason = crew_shell.classify(cmd, which=_which_all)
    assert (kind, argv) == ("bash", None)
    assert reason


@pytest.mark.parametrize("cmd,token", MUST_BASH)
def test_classify_must_bash(cmd, token):
    kind, argv, reason = crew_shell.classify(cmd, which=_which_all)
    assert (kind, argv) == ("bash", None)
    assert token in reason, reason


@pytest.mark.parametrize("char", sorted(crew_shell.METACHARACTERS))
def test_classify_fails_toward_bash(char):
    base = "python3 scripts/check-marketplace.py"
    for cmd in (char + base, base + char, base + " " + char, "python3 " + char + "scripts/x.py",
                "python3 scripts/x" + char + "y.py", "python3" + char + " x"):
        kind, _, reason = crew_shell.classify(cmd, which=_which_all)
        assert kind == "bash", (cmd, reason)


@pytest.mark.parametrize("cmd", ["python3 'unbalanced", 'python3 "unbalanced', "", "   ", "\t"])
def test_classify_unparseable_or_empty_is_bash(cmd):
    assert crew_shell.classify(cmd, which=_which_all)[0] == "bash"


def test_classify_unresolvable_argv0_is_bash():
    kind, argv, reason = crew_shell.classify("nosuchtool x", which=lambda _name: None)
    assert (kind, argv) == ("bash", None)
    assert "nosuchtool" in reason


def test_classify_maps_python3_to_sys_executable():
    for word in ("python3", "python"):
        kind, argv, reason = crew_shell.classify(f"{word} -m pytest x.py -q", which=lambda _name: None)
        assert kind == "plain"
        assert argv == [sys.executable, "-m", "pytest", "x.py", "-q"]
        assert "sys.executable" in reason


PWSH7 = "C:/Program Files/PowerShell/7/pwsh.exe"
PWSH51 = "C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe"
ENV = {"SystemRoot": "C:\\Windows"}


def _absolute_windows(path):
    return len(path) > 3 and path[1] == ":" and path[2] in "\\/"


@pytest.mark.parametrize("present,expected", [
    ({PWSH7, PWSH51}, PWSH7),
    ({PWSH7}, PWSH7),
    ({PWSH51}, PWSH51),
])
def test_resolve_pwsh(present, expected):
    path, reason = crew_shell.resolve_pwsh(exists=present.__contains__, env=ENV)
    assert path == expected and reason
    assert _absolute_windows(path) and path != "pwsh"


def test_resolve_pwsh_none_names_both_tried_paths():
    path, reason = crew_shell.resolve_pwsh(exists=lambda _p: False, env=ENV)
    assert path is None
    assert PWSH7 in reason and PWSH51 in reason


def test_resolve_pwsh_defaults_systemroot():
    path, _ = crew_shell.resolve_pwsh(exists={PWSH51}.__contains__, env={})
    assert path == PWSH51


def _git_exec_path(out, rc=0):
    def runner(argv, timeout):
        assert argv == ["git", "--exec-path"] and timeout
        return rc, out, b""
    return runner


def _raising_runner(argv, timeout):
    raise OSError("git not found")


LAUNCHERS = ("C:\\Windows\\System32\\bash.exe",
             "C:\\Users\\u\\AppData\\Local\\Microsoft\\WindowsApps\\bash.exe")


@pytest.mark.parametrize("runner,present,which,expected", [
    (_git_exec_path(b"C:/Program Files/Git/mingw64/libexec/git-core\n"),
     {"C:/Program Files/Git/bin/bash.exe"}, None, "C:/Program Files/Git/bin/bash.exe"),
    (_git_exec_path(b"D:/Git/mingw64/libexec/git-core\r\n"),
     {"D:/Git/bin/bash.exe", "C:/Program Files/Git/bin/bash.exe"}, None, "D:/Git/bin/bash.exe"),
    (_git_exec_path(b"", rc=1), {"C:/Program Files/Git/bin/bash.exe"}, None,
     "C:/Program Files/Git/bin/bash.exe"),
    (_raising_runner, {"C:/Program Files/Git/bin/bash.exe"}, None, "C:/Program Files/Git/bin/bash.exe"),
    (_raising_runner, set(), "C:\\Program Files\\Git\\usr\\bin\\bash.exe",
     "C:\\Program Files\\Git\\usr\\bin\\bash.exe"),
])
def test_resolve_gitbash(runner, present, which, expected):
    path, reason = crew_shell.resolve_gitbash(runner=runner, exists=present.__contains__,
                                              which=lambda _name: which)
    assert path == expected, reason


@pytest.mark.parametrize("launcher", LAUNCHERS)
def test_resolve_gitbash_never_returns_wsl_launcher(launcher):
    path, reason = crew_shell.resolve_gitbash(runner=_raising_runner, exists=lambda _p: True,
                                              which=lambda _name: launcher)
    assert path == "C:/Program Files/Git/bin/bash.exe"
    path, reason = crew_shell.resolve_gitbash(runner=_raising_runner, exists=lambda _p: False,
                                              which=lambda _name: launcher)
    assert path is None
    assert "C:/Program Files/Git/bin/bash.exe" in reason


def test_resolve_gitbash_rejects_a_derived_system32_path():
    runner = _git_exec_path(b"C:/Windows/System32/a/b/c\n")
    path, _ = crew_shell.resolve_gitbash(runner=runner, exists=lambda p: "System32" in p,
                                         which=lambda _name: None)
    assert path is None

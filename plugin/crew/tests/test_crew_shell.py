"""T-0040: `crew_shell.py`, the Windows shell route for crew's long-running jobs.

No test here calls a real `wsl.exe`, `pwsh` or Git Bash on a routed path.
Every probe and every job goes through an injected `runner` / `execute`,
shell resolution goes through an injected `exists`, and the cache path
resolves beside `crew_state.GLOBAL_CONFIG_PATH`, which the suite's conftest
already points at a scratch path. The one real subprocess is the off-Windows
`bash -c` comparison, which is the property it asserts.
"""
import pytest

import context  # noqa: F401  pylint: disable=unused-import
import crew_shell


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

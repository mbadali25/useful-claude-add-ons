"""T-0040: `crew_shell.py`, the Windows shell route for crew's long-running jobs.

No test here calls a real `wsl.exe`, `pwsh` or Git Bash on a routed path.
Every probe and every job goes through an injected `runner` / `execute`,
shell resolution goes through an injected `exists`, and the cache path
resolves beside `crew_state.GLOBAL_CONFIG_PATH`, which the suite's conftest
already points at a scratch path. The one real subprocess is the off-Windows
`bash -c` comparison, which is the property it asserts.
"""
import json
import os
import re
import subprocess
import sys

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import crew_shell
import crew_state

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
    # An embedded POSIX path: MSYS converts it on the Git Bash route and direct
    # exec does not, so the same job would get a different argv per route.
    ("python3 x.py --root=/c/repos/x", "--root=/c/repos/x"),
    ("a -I/c/x", "-I/c/x"),
    ("a cache_dir=/tmp/y", "cache_dir=/tmp/y"),
    ("a --path=C:/x:/c/y", "--path=C:/x:/c/y"),
    ("a ab:/c/y", "ab:/c/y"),
    ("a --list=a,/c/y", "--list=a,/c/y"),
    ("a --isystem/usr/x", "--isystem/usr/x"),
)

# Tokens with `/`, `=` or `:` that MSYS leaves alone, so they stay plain: a
# drive letter, a URL scheme, a relative path.
MUST_PLAIN_WITH_SLASHES = (
    "python3 x.py --root=C:/repos/x",
    "python3 x.py C:/repos/x",
    "python3 x.py --python=C:/Users/u/AppData/Local/Python/python.exe",
    "python3 x.py --url=https://example.com/a/b",
    "python3 x.py file:///c/x",
    "python3 x.py plugin/crew/tests/x.py --out=build/x",
    "python3 x.py --paths=C:/a,D:/b",
    "python3 x.py x:/c/y",
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


@pytest.mark.parametrize("cmd", MUST_PLAIN_WITH_SLASHES)
def test_classify_keeps_drive_letters_and_urls_plain(cmd):
    kind, argv, reason = crew_shell.classify(cmd, which=_which_all)
    assert kind == "plain", reason
    assert argv == [sys.executable] + cmd.split()[1:]


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


# --- Step 4: the probe, its states, and the machine-local cache ----------------

def _utf16(text):
    return text.encode("utf-16-le")


def _listing(default="Ubuntu-24.04", version="2", extra=("Ubuntu-22.04", "docker-desktop")):
    rows = ["  NAME              STATE           VERSION"]
    for name in (default,) + tuple(extra):
        star = "*" if name == default else " "
        rows.append(f"{star} {name:<17} Stopped         {version if name == default else '2'}")
    return _utf16("\r\n".join(rows) + "\r\n")


# Copied from `wsl.exe --list --verbose` on dadeush-desktop, 2026-09-28.
DESKTOP_LISTING = _listing()
NO_DISTRO = _utf16("Windows Subsystem for Linux has no installed distributions.\r\n"
                   "Use 'wsl.exe --list --online' to list available distributions\r\n"
                   "and 'wsl.exe --install <Distro>' to install.\r\n")
NOT_INSTALLED = _utf16("The Windows Subsystem for Linux is not installed. "
                       "You can install by running 'wsl.exe --install'.\r\n")
TOOLS = b"/usr/bin/python3\n/usr/bin/git\n"


class FakeWsl:
    """`runner(argv, timeout)` for the two probe calls, recording each argv."""

    def __init__(self, listing=DESKTOP_LISTING, listing_rc=0, listing_err=b"", tools=TOOLS, tools_rc=0,
                 tools_err=b"", raise_on=None, exc=None):
        self.calls = []
        self.listing, self.listing_rc, self.listing_err = listing, listing_rc, listing_err
        self.tools, self.tools_rc, self.tools_err = tools, tools_rc, tools_err
        self.raise_on, self.exc = raise_on, exc

    def __call__(self, argv, timeout):
        self.calls.append(list(argv))
        which = "list" if "--list" in argv else "tools"
        if self.raise_on in (which, "any"):
            raise self.exc
        if which == "list":
            return self.listing_rc, self.listing, self.listing_err
        return self.tools_rc, self.tools, self.tools_err


def _has_wsl(name):
    return "C:\\Windows\\System32\\wsl.exe" if name == "wsl.exe" else None


@pytest.fixture(name="windows")
def _windows(monkeypatch):
    monkeypatch.setattr(crew_shell, "host_os", lambda *a, **k: "windows-bash")


PROBE_CASES = [
    ("usable", FakeWsl(), _has_wsl),
    ("not-installed", FakeWsl(), lambda _name: None),
    ("not-installed", FakeWsl(listing=NOT_INSTALLED, listing_rc=1), _has_wsl),
    ("no-distro", FakeWsl(listing=NO_DISTRO, listing_rc=-1), _has_wsl),
    ("wsl1-only", FakeWsl(listing=_listing(version="1")), _has_wsl),
    ("no-python3", FakeWsl(tools=b"/usr/bin/git\n", tools_rc=0), _has_wsl),
    ("no-git", FakeWsl(tools=b"/usr/bin/python3\n", tools_rc=1), _has_wsl),
    ("broken", FakeWsl(listing=b"", listing_rc=1,
                       listing_err=_utf16("Error code: Wsl/Service/0x8007273d\r\n")), _has_wsl),
    ("broken", FakeWsl(tools=b"", tools_rc=4294967295, tools_err=b"The virtual machine could not be started"),
     _has_wsl),
    ("broken", FakeWsl(raise_on="list", exc=subprocess.TimeoutExpired(["wsl.exe"], 15)), _has_wsl),
    ("broken", FakeWsl(raise_on="tools", exc=subprocess.TimeoutExpired(["wsl.exe"], 30)), _has_wsl),
    ("unknown", FakeWsl(raise_on="list", exc=OSError("[WinError 5] Access is denied")), _has_wsl),
    ("unknown", FakeWsl(raise_on="tools", exc=OSError("[WinError 5] Access is denied")), _has_wsl),
]


@pytest.mark.parametrize("expected,runner,which", PROBE_CASES)
def test_probe_classifies(windows, expected, runner, which):  # pylint: disable=unused-argument
    result = crew_shell.probe(runner=runner, which=which)
    assert result["state"] == expected, result
    assert result["detail"]
    assert set(result) >= {"state", "distro", "version", "python3", "git", "detail", "probedAt", "host"}


def test_probe_quotes_the_error_verbatim(windows):  # pylint: disable=unused-argument
    runner = FakeWsl(listing=b"", listing_rc=1, listing_err=_utf16("Error code: Wsl/Service/0x8007273d\r\n"))
    assert "Error code: Wsl/Service/0x8007273d" in crew_shell.probe(runner=runner, which=_has_wsl)["detail"]
    runner = FakeWsl(raise_on="list", exc=OSError("[WinError 5] Access is denied"))
    assert "[WinError 5] Access is denied" in crew_shell.probe(runner=runner, which=_has_wsl)["detail"]


def test_probe_usable_names_the_tools(windows):  # pylint: disable=unused-argument
    result = crew_shell.probe(runner=FakeWsl(), which=_has_wsl)
    assert (result["distro"], result["version"], result["python3"], result["git"]) == (
        "Ubuntu-24.04", "2", "/usr/bin/python3", "/usr/bin/git")


def test_probe_takes_the_default_distro(windows):  # pylint: disable=unused-argument
    runner = FakeWsl()
    result = crew_shell.probe(runner=runner, which=_has_wsl)
    assert (result["state"], result["distro"]) == ("usable", "Ubuntu-24.04")
    assert runner.calls[1][:3] == ["wsl.exe", "-d", "Ubuntu-24.04"]

    moved = FakeWsl(listing=_listing(default="docker-desktop", extra=("Ubuntu-24.04", "Ubuntu-22.04")),
                    tools=b"", tools_rc=127)
    result = crew_shell.probe(runner=moved, which=_has_wsl)
    assert (result["state"], result["distro"]) == ("no-python3", "docker-desktop")
    assert moved.calls[1][:3] == ["wsl.exe", "-d", "docker-desktop"]


def test_probe_honours_configured_distro(windows):  # pylint: disable=unused-argument
    runner = FakeWsl(listing=_listing(extra=("Debian", "docker-desktop")))
    result = crew_shell.probe(runner=runner, which=_has_wsl, distro="Debian")
    assert (result["state"], result["distro"]) == ("usable", "Debian")
    in_distro = [call for call in runner.calls if "--list" not in call]
    assert in_distro and all(call[1:3] == ["-d", "Debian"] for call in in_distro)


def test_probe_configured_distro_not_installed_is_no_distro(windows):  # pylint: disable=unused-argument
    result = crew_shell.probe(runner=FakeWsl(), which=_has_wsl, distro="Debian")
    assert result["state"] == "no-distro"
    assert "Debian" in result["detail"]


def test_probe_failure_is_unknown_not_absent(windows):  # pylint: disable=unused-argument
    for raise_on in ("list", "tools", "any"):
        result = crew_shell.probe(runner=FakeWsl(raise_on=raise_on, exc=OSError("boom")), which=_has_wsl)
        assert result["state"] == "unknown", result
        assert result["state"] not in ("not-installed", "usable")


def test_broken_never_reads_as_usable(windows):  # pylint: disable=unused-argument
    runner = FakeWsl(tools=TOOLS, tools_rc=4294967295, tools_err=b"catastrophic failure")
    assert crew_shell.probe(runner=runner, which=_has_wsl)["state"] == "broken"


def test_probe_never_installs(windows):  # pylint: disable=unused-argument
    seen = []
    for _, runner, which in PROBE_CASES:
        runner.calls.clear()
        crew_shell.probe(runner=runner, which=which)
        seen += runner.calls
    assert seen
    for argv in seen:
        for flag in ("--install", "--update", "--set-default-version"):
            assert flag not in argv, argv


def test_probe_off_windows_calls_nothing(monkeypatch):
    def forbidden(*_a, **_k):
        raise AssertionError("runner called off Windows")
    for host in ("linux", "macos", "wsl"):
        monkeypatch.setattr(crew_shell, "host_os", lambda *a, _h=host, **k: _h)
        assert crew_shell.probe(runner=forbidden, which=forbidden)["state"] == "n/a"


def test_cache_is_machine_local(tmp_path):
    path = crew_shell.probe_path()
    assert path == os.path.join(os.path.dirname(crew_state.GLOBAL_CONFIG_PATH), "shell-route.json")
    repo = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(crew_shell.__file__))))
    assert not os.path.abspath(path).startswith(repo + os.sep)
    # The suite's conftest points GLOBAL_CONFIG_PATH at a scratch path, so this
    # never names the developer's real ~/.claude/crew/.
    assert os.path.abspath(path).startswith(str(tmp_path))


def test_cache_write_is_atomic_and_lf(monkeypatch):
    crew_shell.write_cache({"state": "usable", "distro": "Ubuntu-24.04"})
    path = crew_shell.probe_path()
    with open(path, "rb") as handle:
        before = handle.read()
    assert b"\r" not in before and before.endswith(b"\n")
    assert crew_shell.load_cache()["state"] == "usable"

    def boom(*_a, **_k):
        raise ValueError("payload raised")
    monkeypatch.setattr(crew_shell.json, "dumps", boom)
    with pytest.raises(ValueError):
        crew_shell.write_cache({"state": "broken"})
    with open(path, "rb") as handle:
        assert handle.read() == before
    assert [name for name in os.listdir(os.path.dirname(path)) if name.endswith(".tmp")] == []


def test_cache_replace_failure_leaves_no_tmp(monkeypatch):
    crew_shell.write_cache({"state": "usable"})
    path = crew_shell.probe_path()

    def fail(*_a, **_k):
        raise OSError("replace failed")
    monkeypatch.setattr(crew_shell.os, "replace", fail)
    with pytest.raises(OSError):
        crew_shell.write_cache({"state": "broken"})
    assert crew_shell.load_cache()["state"] == "usable"
    assert [name for name in os.listdir(os.path.dirname(path)) if name.endswith(".tmp")] == []


def test_load_cache_absent_or_unreadable_is_unknown():
    assert crew_shell.load_cache() == {"state": "unknown", "detail": "never probed"}
    path = crew_shell.probe_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write("{not json")
    cache = crew_shell.load_cache()
    assert cache["state"] == "unknown" and "unreadable" in cache["detail"]


def test_not_installed_recommendation():
    text = crew_shell.recommendation({"state": "not-installed"})
    for needle in ("wsl --install -d Ubuntu", "elevated", "reboot", "never runs it",
                   "dadeush-desktop", "2026-09-28", "1.70 s", "0.03 s", "0.13 s", "0.007 s",
                   "dadeush-legion", "2026-09-22", "27.7-35.5 s", "0.19-0.20 s", "4.43 s", "0.062 s"):
        assert needle in text, needle
    assert crew_shell.recommendation({"state": "usable"}) is None


def test_probe_cli_writes_only_with_write_and_exits_zero(windows, monkeypatch, tmp_path, capsys):
    # pylint: disable=unused-argument
    monkeypatch.setattr(crew_shell, "capture", FakeWsl(raise_on="any", exc=OSError("boom")))
    monkeypatch.setattr(crew_shell, "locate", _has_wsl)
    assert crew_shell.main(["probe", "--json", "--root", str(tmp_path)]) == 0
    assert json.loads(capsys.readouterr().out)["state"] == "unknown"
    assert not os.path.exists(crew_shell.probe_path())
    assert crew_shell.main(["probe", "--write", "--root", str(tmp_path)]) == 0
    assert crew_shell.load_cache()["state"] == "unknown"


def test_probe_cli_not_installed_prints_recommendation(windows, monkeypatch, tmp_path, capsys):
    # pylint: disable=unused-argument
    monkeypatch.setattr(crew_shell, "locate", lambda _name: None)
    assert crew_shell.main(["probe", "--root", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "not-installed" in out and "wsl --install -d Ubuntu" in out


# --- Step 5: decide, run and measure ----------------------------------------------

STATES = ("usable", "not-installed", "no-distro", "wsl1-only", "no-python3", "no-git", "broken", "unknown", "n/a")
LOCATIONS = ("windows-drive", "wsl-fs", "unknown")
MEASURED = ("none", "wsl-faster", "gitbash-faster")
GITBASH = "C:/Program Files/Git/bin/bash.exe"
EXACT_POWERSHELL_BASH = "powershell requested; job is bash syntax -> gitbash"


def _expected_route(mode, state, location, measured, job, pwsh):
    """The spec's rules, restated independently of `decide`."""
    if mode == "gitbash":
        return "gitbash", None
    if mode == "powershell":
        if job == "bash":
            return "gitbash", None
        return ("powershell", None) if pwsh else ("refuse", 3)
    usable = state == "usable"
    if mode == "wsl":
        return ("wsl", None) if usable and location in ("windows-drive", "wsl-fs") else ("refuse", 3)
    if usable and (location == "wsl-fs" or (location == "windows-drive" and measured == "wsl-faster")):
        return "wsl", None
    return ("direct" if job == "plain" else "gitbash"), None


@pytest.mark.parametrize("mode", crew_shell.MODES + ("bogus",))
def test_decide(mode):
    for state in STATES:
        probe = {"state": state, "detail": "d", "distro": "Ubuntu-24.04"}
        for location in LOCATIONS:
            for measured in MEASURED:
                for job in ("plain", "bash"):
                    for pwsh in (PWSH7, None):
                        route, reason, code = crew_shell.decide(mode, probe, location, measured, "windows-bash",
                                                                job, pwsh)
                        cell = (mode, state, location, measured, job, pwsh, reason)
                        normal = "auto" if mode == "bogus" else mode
                        assert (route, code) == _expected_route(normal, state, location, measured, job, pwsh), cell
                        assert reason, cell
                        if mode in ("auto", "bogus"):
                            assert route != "powershell", cell
                            if route != "wsl":
                                assert state in reason, cell
                        if mode == "bogus":
                            assert "'bogus'" in reason, cell
                        if mode == "wsl" and route == "refuse" and state != "usable":
                            assert state in reason, cell
                        if mode == "powershell" and job == "bash":
                            assert reason == EXACT_POWERSHELL_BASH, cell


def test_decide_names_never_probed():
    route, reason, _ = crew_shell.decide("auto", {"state": "unknown", "detail": "never probed"}, "windows-drive",
                                         "none", "windows", "bash", None)
    assert route == "gitbash" and "never probed" in reason


@pytest.mark.parametrize("host", ["linux", "macos", "wsl", "other"])
def test_decide_off_windows_is_bash_c(host):
    for mode in crew_shell.MODES + ("bogus",):
        for state in STATES:
            for job in ("plain", "bash"):
                assert crew_shell.decide(mode, {"state": state}, "windows-drive", "wsl-faster", host, job,
                                         PWSH7) == ("bash", "", None)


def _forbidden(*_a, **_k):
    raise AssertionError("called off Windows")


@pytest.mark.parametrize("host", ["linux", "macos", "wsl"])
def test_off_windows_is_inert(host, monkeypatch, tmp_path, capfd):
    monkeypatch.setattr(crew_shell, "host_os", lambda *a, **k: host)
    for name in ("settings", "load_cache", "resolve_gitbash", "resolve_pwsh", "capture", "locate"):
        monkeypatch.setattr(crew_shell, name, _forbidden)
    assert crew_shell.probe(runner=_forbidden, which=_forbidden)["state"] == "n/a"
    assert crew_shell.status_line(str(tmp_path)) is None
    cmd = 'printf "a\\n"; echo b >&2; exit 3'
    code = crew_shell.run(cmd, root=".", runner=_forbidden)
    got = capfd.readouterr()
    want = subprocess.run(["bash", "-c", cmd], capture_output=True, check=False)
    assert (got.out.encode(), got.err.encode(), code) == (want.stdout, want.stderr, want.returncode)
    assert "crew-shell" not in got.err


class Recorder:
    """`execute(argv, cwd)` and `runner(argv, timeout)` in one: records every
    call, answers the WSL preflight, and exits the job with `rc`."""

    def __init__(self, rc=0, preflight_rc=0):
        self.rc, self.preflight_rc = rc, preflight_rc
        self.jobs, self.calls = [], []

    def execute(self, argv, cwd):
        self.jobs.append((list(argv), cwd))
        return self.rc

    def runner(self, argv, timeout):
        self.calls.append(list(argv))
        return self.preflight_rc, b"/usr/bin/x\n", b""


def _windows_run(monkeypatch, mode, cache=None, distro=None, pwsh=PWSH7, gitbash=GITBASH):
    monkeypatch.setattr(crew_shell, "host_os", lambda *a, **k: "windows-bash")
    monkeypatch.setattr(crew_shell, "settings", lambda _root: {"shellRoute": {"mode": mode, "distro": distro}})
    monkeypatch.setattr(crew_shell, "load_cache",
                        lambda: dict(cache or {"state": "usable", "distro": "Ubuntu-24.04", "detail": "ok"}))
    monkeypatch.setattr(crew_shell, "resolve_pwsh", lambda *a, **k: (pwsh, "pwsh reason"))
    monkeypatch.setattr(crew_shell, "resolve_gitbash", lambda *a, **k: (gitbash, "gitbash reason"))


REAL_LOAD_CACHE = crew_shell.load_cache
WIN_ROOT = "C:\\repos\\x"
WSL_ROOT = "\\\\wsl.localhost\\Ubuntu-24.04\\home\\u\\r"


def test_run_argv_for_wsl(monkeypatch):
    _windows_run(monkeypatch, "wsl")
    rec = Recorder()
    cmd = 'echo "$HOME" \'/c/x\' && ls /c/x'
    assert crew_shell.run(cmd, root=WIN_ROOT, runner=rec.runner, execute=rec.execute) == 0
    assert rec.jobs == [(["wsl.exe", "-d", "Ubuntu-24.04", "--cd", "/mnt/c/repos/x", "-e", "bash", "-lc", cmd],
                         WIN_ROOT)]
    # The preflight runs in the job's own shell, `bash -lc`: a non-login `sh -c`
    # misses the login-only PATH ($HOME/.local/bin) the job itself sees.
    assert rec.calls == [["wsl.exe", "-d", "Ubuntu-24.04", "-e", "bash", "-lc", "command -v echo"]]


def test_run_auto_routes_wsl_fs_repo_to_wsl(monkeypatch):
    _windows_run(monkeypatch, "auto")
    rec = Recorder()
    crew_shell.run("python3 -m pytest x.py", root=WSL_ROOT, runner=rec.runner, execute=rec.execute)
    assert rec.jobs[0][0][:5] == ["wsl.exe", "-d", "Ubuntu-24.04", "--cd", "/home/u/r"]


def test_run_argv_for_gitbash(monkeypatch):
    _windows_run(monkeypatch, "gitbash")
    rec = Recorder()
    cmd = "python3 -m pytest x.py -q"
    crew_shell.run(cmd, root=WIN_ROOT, runner=rec.runner, execute=rec.execute)
    assert rec.jobs == [([GITBASH, "-lc", cmd], WIN_ROOT)]


def test_run_argv_for_direct(monkeypatch):
    _windows_run(monkeypatch, "auto", cache={"state": "not-installed", "detail": "wsl.exe is not on PATH"})
    rec = Recorder()
    crew_shell.run("python3 -m pytest x.py -q", root=WIN_ROOT, runner=rec.runner, execute=rec.execute)
    assert rec.jobs == [([sys.executable, "-m", "pytest", "x.py", "-q"], WIN_ROOT)]
    assert rec.calls == []


def _pwsh_command(quoted):
    """The -Command string around a quoted argv: a program that cannot start is
    exit 1, never `exit $null` (which is 0)."""
    return ("$ErrorActionPreference = 'Stop'; try { & " + quoted + " } catch { "
            "[Console]::Error.WriteLine('crew-shell: ' + $_); exit 1 }; "
            "if ($null -eq $LASTEXITCODE) { exit 1 }; exit $LASTEXITCODE")


def test_pwsh_argv_quotes_each_element():
    assert crew_shell.pwsh_argv(["a", "b c", "it's"], PWSH7) == [
        PWSH7, "-NoProfile", "-NonInteractive", "-Command", _pwsh_command("'a' 'b c' 'it''s'")]


def test_run_argv_for_powershell(monkeypatch):
    _windows_run(monkeypatch, "powershell")
    rec = Recorder()
    crew_shell.run("python3 -m pytest x.py", root=WIN_ROOT, runner=rec.runner, execute=rec.execute)
    quoted = sys.executable.replace("'", "''")
    assert rec.jobs == [([PWSH7, "-NoProfile", "-NonInteractive", "-Command",
                          _pwsh_command(f"'{quoted}' '-m' 'pytest' 'x.py'")], WIN_ROOT)]


def test_run_powershell_without_pwsh_refuses(monkeypatch, capsys):
    _windows_run(monkeypatch, "powershell", pwsh=None)
    rec = Recorder()
    assert crew_shell.run("python3 x.py", root=WIN_ROOT, runner=rec.runner, execute=rec.execute) == 3
    assert rec.jobs == []
    assert "exit 3" in capsys.readouterr().err


@pytest.mark.parametrize("cmd", [cmd for cmd, _ in MUST_BASH] + list(VERIFY_MAP_BASH))
def test_powershell_mode_never_hands_bash_to_pwsh(monkeypatch, capsys, cmd):
    _windows_run(monkeypatch, "powershell")
    rec = Recorder()
    crew_shell.run(cmd, root=WIN_ROOT, runner=rec.runner, execute=rec.execute)
    for argv in [job for job, _ in rec.jobs] + rec.calls:
        assert argv[0] != PWSH7, argv
    assert rec.jobs == [([GITBASH, "-lc", cmd], WIN_ROOT)]
    assert capsys.readouterr().err == f"crew-shell: {EXACT_POWERSHELL_BASH}\n"


def test_gitbash_mode_with_a_plain_job_still_runs_gitbash(monkeypatch):
    _windows_run(monkeypatch, "gitbash")
    rec = Recorder()
    crew_shell.run("python3 x.py", root=WIN_ROOT, runner=rec.runner, execute=rec.execute)
    assert rec.jobs[0][0][0] == GITBASH


ROUTE_SETUPS = {
    "wsl": ("wsl", None),
    "gitbash": ("gitbash", None),
    "direct": ("auto", {"state": "not-installed", "detail": "x"}),
    "powershell": ("powershell", None),
}


@pytest.mark.parametrize("route", sorted(ROUTE_SETUPS))
@pytest.mark.parametrize("rc", [0, 1, 7])
def test_run_passes_exit_code_through(monkeypatch, route, rc):
    mode, cache = ROUTE_SETUPS[route]
    _windows_run(monkeypatch, mode, cache=cache)
    rec = Recorder(rc=rc)
    assert crew_shell.run("python3 x.py", root=WIN_ROOT, runner=rec.runner, execute=rec.execute) == rc
    assert len(rec.jobs) == 1


def test_run_prints_one_route_line_to_stderr(monkeypatch, capsys):
    _windows_run(monkeypatch, "auto", cache={"state": "not-installed", "detail": "wsl.exe is not on PATH"})
    rec = Recorder()
    crew_shell.run("python3 x.py", root=WIN_ROOT, runner=rec.runner, execute=rec.execute)
    out, err = capsys.readouterr()
    assert out == ""
    lines = err.splitlines()
    assert len(lines) == 1 and lines[0].startswith("crew-shell: ")
    assert "not-installed" in lines[0] and "direct" in lines[0] and "sys.executable" in lines[0]


def test_run_preflight_missing_tool(monkeypatch, capsys):
    _windows_run(monkeypatch, "auto")
    rec = Recorder(preflight_rc=1)
    crew_shell.run("python3 x.py", root=WSL_ROOT, runner=rec.runner, execute=rec.execute)
    assert rec.jobs == [([sys.executable, "x.py"], WSL_ROOT)]
    assert "python3 is not on PATH inside Ubuntu-24.04" in capsys.readouterr().err

    _windows_run(monkeypatch, "wsl")
    rec = Recorder(preflight_rc=1)
    assert crew_shell.run("python3 x.py", root=WSL_ROOT, runner=rec.runner, execute=rec.execute) == 3
    assert rec.jobs == []


def test_run_wsl_mode_refuses_another_distros_path(monkeypatch):
    _windows_run(monkeypatch, "wsl")
    rec = Recorder()
    root = "\\\\wsl.localhost\\Debian\\home\\u\\r"
    assert crew_shell.run("python3 x.py", root=root, runner=rec.runner, execute=rec.execute) == 3
    assert rec.jobs == []


def test_run_config_distro_disagreeing_with_the_cache_is_unknown(monkeypatch, capsys):
    _windows_run(monkeypatch, "wsl", distro="Debian")
    rec = Recorder()
    assert crew_shell.run("python3 x.py", root=WIN_ROOT, runner=rec.runner, execute=rec.execute) == 3
    assert "probe --write" in capsys.readouterr().err


def test_run_without_gitbash_refuses(monkeypatch):
    _windows_run(monkeypatch, "gitbash", gitbash=None)
    rec = Recorder()
    assert crew_shell.run("python3 x.py", root=WIN_ROOT, runner=rec.runner, execute=rec.execute) == 3
    assert rec.jobs == []


def test_mode_normalises_an_unrecognised_value():
    assert crew_shell.mode({"shellRoute": {"mode": "wsl"}}) == ("wsl", None)
    assert crew_shell.mode({}) == ("auto", None)
    normal, note = crew_shell.mode({"shellRoute": {"mode": "native"}})
    assert normal == "auto" and "'native'" in note


def test_run_cli_joins_argv_and_strips_dashdash(monkeypatch):
    seen = []
    monkeypatch.setattr(crew_shell, "run", lambda cmd, root=".", **_k: seen.append((cmd, root)) or 5)
    assert crew_shell.main(["run", "--", "python3 -m pytest x.py"]) == 5
    assert crew_shell.main(["run", "--root", "r", "--", "python3", "-m", "pytest"]) == 5
    assert seen == [("python3 -m pytest x.py", "."), ("python3 -m pytest", "r")]


def test_classify_cli(capsys):
    assert crew_shell.main(["classify", "--", "a | b"]) == 0
    assert capsys.readouterr().out.startswith("bash: ")


class Shells:
    """A `runner` standing in for Git Bash, pwsh and WSL. Each timing script
    measures itself inside its shell and prints `start end`; this prints a pair
    whose difference is the side's cost, so the numbers come out exactly and
    no launcher start-up can leak into them."""

    COSTS = {"gitbash": (1.70, 0.13), "pwsh": (0.93, 0.051), "wsl": (0.03, 0.70), "wsl-ext4": (0.03, 0.007)}

    def __init__(self, costs=None, decimal="."):
        self.calls = []
        self.costs = costs or self.COSTS
        self.decimal = decimal

    def runner(self, argv, timeout):
        self.calls.append(list(argv))
        script = argv[-1]
        if argv[0] == GITBASH:
            side = "gitbash"
        elif argv[0] == PWSH7:
            side = "pwsh"
        else:
            side = "wsl-ext4" if "mktemp" in script else "wsl"
        forks, writes = self.costs[side]
        cost = forks if "-lt 50" in script else writes
        pair = f"{1727000000.25:.6f} {1727000000.25 + cost:.6f}".replace(".", self.decimal)
        return 0, (pair + "\n").encode(), b""


def _measure_setup(monkeypatch, tmp_path):
    _windows_run(monkeypatch, "auto")
    monkeypatch.setattr(crew_shell, "repo_location", lambda _p: "windows-drive")
    monkeypatch.setattr(crew_shell, "to_wsl_path", lambda p, distro=None: ("/mnt/c/x/" + os.path.basename(p), ""))
    return str(tmp_path)


def test_measure_reports_every_side(monkeypatch, tmp_path):
    root = _measure_setup(monkeypatch, tmp_path)
    clock = Shells()
    result = crew_shell.measure(root, runner=clock.runner)
    assert result["host"] and result["date"] and result["location"] == "windows-drive"
    for side, (forks, writes) in Shells.COSTS.items():
        assert result["sides"][side] == {"forks": pytest.approx(forks), "writes": pytest.approx(writes)}, side
    assert result["verdict"] == "gitbash-faster"  # WSL on /mnt loses on writes
    assert not [name for name in os.listdir(root) if name.startswith(".crew-shell-measure")]
    for argv in clock.calls:
        assert argv[0] in (GITBASH, PWSH7, "wsl.exe")


def test_measure_wsl_faster_needs_both_forks_and_writes(monkeypatch, tmp_path):
    root = _measure_setup(monkeypatch, tmp_path)
    costs = dict(Shells.COSTS, wsl=(0.03, 0.05))
    clock = Shells(costs)
    assert crew_shell.measure(root, runner=clock.runner)["verdict"] == "wsl-faster"


def test_measure_write_stores_it_and_decide_reads_it(monkeypatch, tmp_path, capsys):
    root = _measure_setup(monkeypatch, tmp_path)
    monkeypatch.setattr(crew_shell, "load_cache", REAL_LOAD_CACHE)
    crew_shell.write_cache({"state": "usable", "distro": "Ubuntu-24.04", "detail": "seeded"})
    clock = Shells(dict(Shells.COSTS, wsl=(0.03, 0.05)))
    monkeypatch.setattr(crew_shell, "capture", clock.runner)
    assert crew_shell.main(["measure", "--write", "--root", root]) == 0
    assert "wsl-faster" in capsys.readouterr().out
    with open(crew_shell.probe_path(), encoding="utf-8") as handle:
        stored = json.load(handle)
    assert crew_shell.measured_verdict(stored, root) == "wsl-faster"
    assert stored["state"] == "usable"


def test_measure_off_windows_runs_nothing(monkeypatch, tmp_path):
    monkeypatch.setattr(crew_shell, "host_os", lambda *a, **k: "linux")
    assert crew_shell.measure(str(tmp_path), runner=_forbidden) == {
        "state": "n/a", "detail": "not native Windows"}


def test_measure_side_failure_is_an_error_not_a_number(monkeypatch, tmp_path):
    root = _measure_setup(monkeypatch, tmp_path)
    clock = Shells()

    def runner(argv, timeout):
        if argv[0] == "wsl.exe":
            raise OSError("wsl gone")
        return clock.runner(argv, timeout)
    result = crew_shell.measure(root, runner=runner)
    assert "wsl gone" in result["sides"]["wsl"]["error"]
    assert result["verdict"] == "unknown"


def test_measure_cli_names_a_root_it_cannot_reach(monkeypatch, tmp_path, capsys):
    """Found on dadeush-desktop: a `\\\\wsl.localhost\\` root that had gone away
    (WSL cleared /tmp on a VM restart) died in `tempfile.mkdtemp` with a
    traceback. It is reported and exits 2, and nothing is measured."""
    _measure_setup(monkeypatch, tmp_path)
    monkeypatch.setattr(crew_shell, "capture", _forbidden)
    assert crew_shell.main(["measure", "--root", str(tmp_path / "gone")]) == 2
    err = capsys.readouterr().err
    assert "gone" in err and "Traceback" not in err


def test_measure_times_inside_each_shell(monkeypatch, tmp_path):
    """The launcher's own start-up (wsl.exe's is larger and noisier than 50
    WSL forks) must never be subtracted into a result: each script reads its
    own clock, bash's `$EPOCHREALTIME` and pwsh's Stopwatch."""
    root = _measure_setup(monkeypatch, tmp_path)
    clock = Shells()
    crew_shell.measure(root, runner=clock.runner)
    for argv in clock.calls:
        script = argv[-1]
        assert ("Stopwatch" in script) if argv[0] == PWSH7 else (script.count("$EPOCHREALTIME") == 2), script


def test_measure_reads_a_comma_decimal_locale(monkeypatch, tmp_path):
    root = _measure_setup(monkeypatch, tmp_path)
    result = crew_shell.measure(root, runner=Shells(decimal=",").runner)
    assert result["sides"]["gitbash"] == {"forks": pytest.approx(1.70), "writes": pytest.approx(0.13)}


@pytest.mark.parametrize("out", [b"", b" \n", b"not a number\n", b"1727000001.0 1727000000.0\n"])
def test_measure_unreadable_timing_is_an_error_not_a_number(monkeypatch, tmp_path, out):
    """An empty `$EPOCHREALTIME` (bash older than 5), garbage, or a clock that
    ran backwards is `could not tell`, never zero, and the verdict is unknown."""
    root = _measure_setup(monkeypatch, tmp_path)
    clock = Shells()

    def runner(argv, timeout):
        if argv[0] == "wsl.exe":
            clock.calls.append(list(argv))
            return 0, out, b""
        return clock.runner(argv, timeout)
    result = crew_shell.measure(root, runner=runner)
    assert "error" in result["sides"]["wsl"]
    assert result["verdict"] == "unknown"


# --- review round 1 (T-0040-Bdt4JE) ----------------------------------------------

DEBIAN_ROOT = "\\\\wsl.localhost\\Debian\\home\\u\\r"
MEASURED_WIN = {"measured": {os.path.normcase(WIN_ROOT): {"verdict": "wsl-faster"}}}


def _run_route(rec):
    """The route `run` took, read off the argv it executed."""
    if not rec.jobs:
        return "refuse"
    program = rec.jobs[0][0][0]
    return {"wsl.exe": "wsl", sys.executable: "direct", GITBASH: "gitbash", PWSH7: "powershell"}[program]


def _status_route(line):
    """The route the `/crew:status` shell line names for a plain-argv job."""
    shown = line.split(" -> ", 1)[1]
    for prefix, route in (("wsl (", "wsl"), ("direct", "direct"), ("gitbash", "gitbash"), (PWSH7, "powershell"),
                          ("refused", "refuse")):
        if shown.startswith(prefix):
            return route
    raise AssertionError(line)


@pytest.mark.parametrize("mode", crew_shell.MODES)
@pytest.mark.parametrize("state", ["usable", "not-installed", "broken"])
@pytest.mark.parametrize("root", [WIN_ROOT, WSL_ROOT, DEBIAN_ROOT])
@pytest.mark.parametrize("measured", [False, True])
def test_status_line_and_run_take_the_same_route(monkeypatch, capsys, mode, state, root, measured):
    """`status_line` reads `run`'s own decision, the distro check included,
    so the two can never disagree about a plain-argv job."""
    cache = {"state": state, "distro": "Ubuntu-24.04", "detail": "d"}
    if measured:
        cache.update(MEASURED_WIN)
    _windows_run(monkeypatch, mode, cache=cache)
    line = crew_shell.status_line(root)
    rec = Recorder()
    crew_shell.run("python3 x.py", root=root, runner=rec.runner, execute=rec.execute)
    err = capsys.readouterr().err
    assert _status_route(line) == _run_route(rec), (line, err)


def test_status_line_names_another_distros_path(monkeypatch):
    """Found in review: the status line said `auto -> wsl` for a repo inside a
    distro other than the probed one, while `run` execs it directly."""
    _windows_run(monkeypatch, "auto")
    line = crew_shell.status_line(DEBIAN_ROOT)
    assert " -> wsl" not in line, line
    assert "Debian" in line and "Ubuntu-24.04" in line, line


def test_status_line_says_the_mode_forced_wsl_not_a_measurement(monkeypatch):
    _windows_run(monkeypatch, "wsl")
    line = crew_shell.status_line("C:/repos/x")
    assert " -> wsl (Ubuntu-24.04) - " in line, line
    assert "measured" not in line and "shellRoute.mode" in line, line


def test_status_line_says_a_measurement_chose_wsl(monkeypatch):
    _windows_run(monkeypatch, "auto", cache=dict({"state": "usable", "distro": "Ubuntu-24.04"}, **MEASURED_WIN))
    line = crew_shell.status_line(WIN_ROOT)
    assert " -> wsl (Ubuntu-24.04) - " in line and "measured faster" in line, line


MULTILINE_ERR = "Catastrophic failure\r\nError code: Wsl/Service/E_UNEXPECTED\r\n".encode("utf-16-le")


def test_a_multiline_wsl_error_stays_one_line(windows, monkeypatch, capsys):  # pylint: disable=unused-argument
    result = crew_shell.probe(runner=lambda _a, _t: (4294967295, b"", MULTILINE_ERR),
                              which=lambda _n: "C:/Windows/System32/wsl.exe")
    assert result["state"] == "broken"
    assert len(result["detail"].splitlines()) == 1, result["detail"]
    assert "Catastrophic failure" in result["detail"] and "Wsl/Service/E_UNEXPECTED" in result["detail"]
    # A cache written before the fix still carries the raw multi-line detail.
    for cache in (result, {"state": "broken", "detail": "Catastrophic failure\r\nError code: x\r\n"}):
        _windows_run(monkeypatch, "auto", cache=cache)
        line = crew_shell.status_line(WIN_ROOT)
        assert len(line.splitlines()) == 1, line
        crew_shell.run("python3 x.py", root=WIN_ROOT, runner=Recorder().runner, execute=Recorder().execute)
        err = capsys.readouterr().err
        assert len(err.splitlines()) == 1, err


def test_probe_checks_tools_in_the_jobs_login_shell(windows):  # pylint: disable=unused-argument
    runner = FakeWsl()
    crew_shell.probe(runner=runner, which=_has_wsl)
    assert runner.calls[1][:6] == ["wsl.exe", "-d", "Ubuntu-24.04", "-e", "bash", "-lc"]


def test_run_preflight_checks_a_python_module(monkeypatch, capsys):
    """Found on dadeush-desktop: `python3 -m pytest` routed to WSL, whose
    python3 had no pytest, and died with `No module named pytest`."""
    _windows_run(monkeypatch, "wsl")
    rec = Recorder(preflight_rc=2)
    assert crew_shell.run("python3 -m pytest x.py -q", root=WSL_ROOT, runner=rec.runner, execute=rec.execute) == 3
    assert rec.jobs == []
    assert len(rec.calls) == 1 and rec.calls[0][:6] == ["wsl.exe", "-d", "Ubuntu-24.04", "-e", "bash", "-lc"]
    assert "pytest" in rec.calls[0][6]
    err = capsys.readouterr().err
    assert "module pytest is not importable by python3 inside Ubuntu-24.04" in err, err

    _windows_run(monkeypatch, "auto")
    rec = Recorder(preflight_rc=2)
    crew_shell.run("python3 -m pytest x.py -q", root=WSL_ROOT, runner=rec.runner, execute=rec.execute)
    assert rec.jobs == [([sys.executable, "-m", "pytest", "x.py", "-q"], WSL_ROOT)]
    assert "not importable" in capsys.readouterr().err


@pytest.mark.parametrize("cmd,module", [
    ("python3 -m pytest x.py", "pytest"),
    ("python -m pytest", "pytest"),
    ("python3 -u -m graphify .", "graphify"),
    ("python3 -mpytest", "pytest"),
    ("python3 x.py -m pytest", None),
    ("graphify . -m x", None),
])
def test_preflight_names_the_module_only_for_python_dash_m(cmd, module):
    assert crew_shell.job_head(cmd) == (cmd.split()[0], module)


@pytest.mark.parametrize("module,code", [("json", 0), ("os.path", 0), ("no_such_mod_t0040", 2),
                                         ("no_such_pkg_t0040.sub", 2)])
def test_module_check_script_exit_codes(module, code):
    done = subprocess.run([sys.executable, "-c", crew_shell.MODULE_CHECK, module], capture_output=True,
                          check=False, timeout=60)
    assert done.returncode == code, done.stderr


def test_classify_refuses_an_embedded_c_path():
    kind, argv, reason = crew_shell.classify("python3 x.py --root=/c/repos/x", which=_which_all)
    assert (kind, argv) == ("bash", None)
    assert "--root=/c/repos/x" in reason and "POSIX path" in reason


def test_pwsh_launch_failure_is_not_exit_zero():
    """`exit $LASTEXITCODE` is `exit $null`, which is 0, when the program never
    started. The -Command string must catch that and exit 1."""
    command = crew_shell.pwsh_argv(["C:/nope/missing.exe", "x"], PWSH7)[-1]
    assert command.startswith("$ErrorActionPreference = 'Stop'; try { & ")
    assert "catch { [Console]::Error.WriteLine('crew-shell: ' + $_); exit 1 }" in command
    assert command.endswith("if ($null -eq $LASTEXITCODE) { exit 1 }; exit $LASTEXITCODE")


def test_pwsh_argv_doubles_every_single_quote_pwsh_knows():
    """PowerShell reads U+2018-U+201B as single quotes too; each is doubled
    like `'`, so it stays literal and never closes the quoted argument."""
    command = crew_shell.pwsh_argv(["it\u2019s", "a\u2018b", "\u201a", "\u201b'x"], PWSH7)[-1]
    assert "& 'it\u2019\u2019s' 'a\u2018\u2018b' '\u201a\u201a' '\u201b\u201b''x' }" in command


REAL_SHELLS = [path for path in (PWSH7, PWSH51) if sys.platform == "win32" and os.path.isfile(path)]


@pytest.mark.skipif(not REAL_SHELLS, reason="needs a real pwsh 7 or Windows PowerShell 5.1 on native Windows")
@pytest.mark.parametrize("shell", REAL_SHELLS)
def test_pwsh_argv_for_real(shell, tmp_path):
    """Measured on dadeush-desktop, 2026-09-30, with pwsh 7 and 5.1: a missing
    program and a zero-byte `.exe` both exited 0 before the fix."""
    bad = tmp_path / "bad.exe"
    bad.write_bytes(b"")
    for argv in (["C:/nope/missing.exe", "x"], [str(bad), "x"]):
        done = subprocess.run(crew_shell.pwsh_argv(argv, shell), capture_output=True, check=False, timeout=120)
        assert done.returncode == 1, (argv, done.stderr)
        assert b"crew-shell: " in done.stderr
    echo = [sys.executable, "-c", "import sys; print(ascii(sys.argv[1:])); sys.exit(7)",
            "it\u2019s", "a\u2018b", "\u201a", "\u201b'x", "o'k"]
    done = subprocess.run(crew_shell.pwsh_argv(echo, shell), capture_output=True, check=False, timeout=120)
    assert done.returncode == 7, done.stderr
    assert done.stdout.decode().strip() == ascii(echo[3:])


@pytest.mark.parametrize("host", ["linux", "macos", "wsl"])
@pytest.mark.parametrize("signal_number", [2, 9, 15])
def test_off_windows_signal_exit_is_128_plus_n(monkeypatch, host, signal_number):
    """subprocess reports a signal-killed child as -N; `bash -c` reports 128+N."""
    monkeypatch.setattr(crew_shell, "host_os", lambda *a, **k: host)
    assert crew_shell.run("kill -TERM $$", root=".", execute=lambda _argv, _cwd: -signal_number) == \
        128 + signal_number


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX signals")
def test_off_windows_signal_exit_matches_bash_for_real():
    want = subprocess.run(["bash", "-c", "bash -c 'kill -TERM $$'; echo $?"], capture_output=True, check=False)
    assert crew_shell.run("kill -TERM $$", root=".") == int(want.stdout.decode().strip())


def test_absolute_converts_a_git_bash_root():
    """Under MSYS_NO_PATHCONV=1 `--root /c/repos/x` arrives as-is; abspath made
    it `C:\\c\\repos\\x` and so `/mnt/c/c/repos/x` in WSL."""
    root = crew_shell._absolute("/c/repos/x")  # pylint: disable=protected-access
    assert root == "C:\\repos\\x"
    assert crew_shell.to_wsl_path(root) == ("/mnt/c/repos/x", "")
    assert crew_shell.repo_location(root) == "windows-drive"
    assert crew_shell._absolute("/d") == "D:\\"  # pylint: disable=protected-access


CREW_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(crew_shell.__file__))))


def _crew_markdown():
    for base, _dirs, files in os.walk(CREW_DIR):
        for name in files:
            if name.endswith(".md"):
                yield os.path.join(base, name)


def test_docs_invoke_crew_shell_the_way_git_bash_can_run():
    """Git Bash has no python3 (or it is the WindowsApps alias that exits
    9009), so every instruction to run crew_shell.py quotes the plugin root and
    names the `python`/`py -3` fallback, as commands/status.md does."""
    seen = 0
    for path in _crew_markdown():
        with open(path, encoding="utf-8") as handle:
            text = handle.read()
        for number, line in enumerate(text.splitlines(), 1):
            if not re.search(r'crew_shell\.py"?\s+run\b', line) or "python" not in line:
                continue
            seen += 1
            assert 'python3 "${CLAUDE_PLUGIN_ROOT}/hooks/scripts/crew_shell.py" run' in line, f"{path}:{number}"
            assert "use `python` or `py -3` with the same arguments" in text, path
    assert seen >= 3

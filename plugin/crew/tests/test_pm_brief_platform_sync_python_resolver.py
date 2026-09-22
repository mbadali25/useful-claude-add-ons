"""pm-brief.ps1 and platform-sync.ps1's python resolvers -- Windows audit
wave 3, .ps1 half.

Both carried `(Get-Command python3, python -ErrorAction SilentlyContinue |
Select-Object -First 1).Source` -- metadata only, no execute-to-verify probe,
and no WindowsApps filter at all. Their bash twins (`pm-brief.sh`,
`platform-sync.sh`) were converted in the same pass to call `_common.sh`'s
`crew_py_strict`, so these two now carry a BYTE-FOR-BYTE copy of
`role-write-guard.ps1`'s hardened `Resolve-CrewPython` instead, for the same
reason `role-write-guard.sh`'s bash resolver could not just become the
default `crew_py()` -- widening a shared resolver changes every OTHER caller's
behaviour for a bug specific to a few call sites.

`context-watch.ps1` is deliberately NOT covered here: unlike its bash twin it
never shells out to python at all (the transcript-usage arithmetic is native
PowerShell), so there is no resolver in that file to hardened or test.

Behavioural cases below need a real Windows host -- `Get-Command`'s
`CommandType -eq 'Application'` classification of an arbitrary stub is not
reliably reproducible under pwsh on Linux -- so they follow
`test_pm_pulse_python_resolver.py`'s own convention and are skipped off
Windows. The static parity and tripwire checks run everywhere.
"""
import os
import pathlib
import re
import shutil
import subprocess
import sys

import pytest

import context  # noqa: F401  pylint: disable=unused-import

_ROOT = context._ROOT  # pylint: disable=protected-access
_PM_BRIEF_PS1 = os.path.join(_ROOT, "hooks", "scripts", "pm-brief.ps1")
_PLATFORM_SYNC_PS1 = os.path.join(_ROOT, "hooks", "scripts", "platform-sync.ps1")
_GUARD_PS1 = os.path.join(_ROOT, "hooks", "scripts", "role-write-guard.ps1")

_PWSH = shutil.which("pwsh")

_WINDOWS_ONLY = pytest.mark.skipif(
    not sys.platform.startswith("win") or _PWSH is None,
    reason="Get-Command Application classification needs a real Windows host",
)


def _resolver_source(path):
    src = pathlib.Path(path).read_text(encoding="utf-8")
    start = src.find("function Resolve-CrewPython {")
    assert start != -1, (
        "Resolve-CrewPython is gone from " + path + ". If it was renamed, "
        "re-point this test rather than deleting it.")
    end = src.find("\n}\n", start)
    assert end != -1, "could not find the end of Resolve-CrewPython in " + path
    return src[start:end + 3]


def _resolver_code_lines(path):
    def code_lines(src):
        out = []
        for line in src.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            out.append(re.sub(r"\s+", " ", stripped))
        return out
    return code_lines(_resolver_source(path))


# --- Parity: both new copies must match role-write-guard.ps1's exactly -----

def test_pm_brief_resolver_matches_role_write_guard():
    guard = _resolver_code_lines(_GUARD_PS1)
    brief = _resolver_code_lines(_PM_BRIEF_PS1)
    assert guard == brief, (
        "pm-brief.ps1's Resolve-CrewPython has drifted from "
        "role-write-guard.ps1's. One hook would then resolve an interpreter "
        "the other refuses."
        + "\nrole-write-guard.ps1: " + repr(guard)
        + "\npm-brief.ps1:         " + repr(brief))


def test_platform_sync_resolver_matches_role_write_guard():
    guard = _resolver_code_lines(_GUARD_PS1)
    sync = _resolver_code_lines(_PLATFORM_SYNC_PS1)
    assert guard == sync, (
        "platform-sync.ps1's Resolve-CrewPython has drifted from "
        "role-write-guard.ps1's. A hook that WRITES config is the last "
        "place this should happen."
        + "\nrole-write-guard.ps1: " + repr(guard)
        + "\nplatform-sync.ps1:    " + repr(sync))


def test_pm_brief_and_platform_sync_resolvers_agree_with_each_other():
    brief = _resolver_code_lines(_PM_BRIEF_PS1)
    sync = _resolver_code_lines(_PLATFORM_SYNC_PS1)
    assert brief == sync


# --- Tripwire: the naive one-liner must not come back ----------------------

_OLD_ONE_LINER = (
    "$py = (Get-Command python3, python -ErrorAction SilentlyContinue |\n"
    "       Select-Object -First 1).Source")


@pytest.mark.parametrize("path", [_PM_BRIEF_PS1, _PLATFORM_SYNC_PS1])
def test_call_site_no_longer_uses_the_unhardened_one_liner(path):
    # Only the code lines outside Resolve-CrewPython, so the comment inside
    # that function explaining what it replaced does not trip this check --
    # it is prose ABOUT the old line, not the old line itself.
    src = pathlib.Path(path).read_text(encoding="utf-8")
    outside = src.replace(_resolver_source(path), "")
    assert _OLD_ONE_LINER not in outside, (
        path + " still calls the old unhardened one-liner, which trusts "
        "Get-Command metadata without executing the candidate and accepts a "
        "WindowsApps stub.")


# --- FIX: resolver failure must be LOUD on stderr, even though these two
#     stay non-blocking (exit 0). Driven for real, not just grepped for --
#     an empty PATH does not depend on Windows-specific `Get-Command`
#     Application/WindowsApps classification, so this runs on any platform
#     that has pwsh, matching `test_context_watch.py`'s own technique of
#     telling the script `$env:OS = 'Windows_NT'` to get past the flavour
#     guard on a non-Windows CI host.

_PWSH_ANY = pytest.mark.skipif(_PWSH is None, reason="no pwsh on PATH")


@_PWSH_ANY
@pytest.mark.parametrize("ps1_path,marker", [
    (_PM_BRIEF_PS1, "crew pm-brief: no usable python"),
    (_PLATFORM_SYNC_PS1, "crew platform-sync: no usable python"),
])
def test_resolver_failure_is_loud_on_stderr_and_still_exits_0(tmp_path, ps1_path, marker):
    empty_path = tmp_path / "empty-path"
    empty_path.mkdir()
    env = os.environ.copy()
    env["PATH"] = str(empty_path)
    env["OS"] = "Windows_NT"
    repo = tmp_path / "repo"
    (repo / ".crew").mkdir(parents=True)
    proc = subprocess.run(
        [_PWSH, "-NoProfile", "-NonInteractive", "-File", ps1_path],
        input="{}", cwd=str(repo), env=dict(env, CLAUDE_PROJECT_DIR=str(repo)),
        capture_output=True, text=True, check=False)
    assert proc.returncode == 0, (
        "a broken interpreter must stay non-blocking here (exit 0): "
        + proc.stderr)
    assert marker in proc.stderr, (
        f"resolver failure must be named on stderr, not silent. "
        f"got: {proc.stderr!r}")


@pytest.mark.parametrize("path", [_PM_BRIEF_PS1, _PLATFORM_SYNC_PS1])
def test_call_site_still_calls_the_hardened_resolver(path):
    src = pathlib.Path(path).read_text(encoding="utf-8")
    assert "$py = Resolve-CrewPython" in src, (
        path + " does not call the hardened resolver at its launch site; a "
        "hardened function the script never calls is not a fix.")


# --- Windows-only behavioural coverage (mirrors pm-pulse's suite) ----------

def _print_python(ps1_path, path_entries):
    env = os.environ.copy()
    env["PATH"] = os.pathsep.join(path_entries)
    result = subprocess.run(
        [_PWSH, "-NoProfile", "-NonInteractive", "-File", ps1_path,
         "-PrintPython"],
        env=env, stdin=subprocess.DEVNULL, capture_output=True, text=True,
        check=False)
    assert result.returncode == 0, "the probe must exit 0. stderr: " + result.stderr
    return result.stdout.strip()


def _stub(path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="ascii") as fh:
        fh.write("rem stub, never executed by -PrintPython" + chr(10))
    return path


@_WINDOWS_ONLY
@pytest.mark.parametrize("ps1_path", [_PM_BRIEF_PS1, _PLATFORM_SYNC_PS1])
def test_windowsapps_stub_is_never_returned(ps1_path, tmp_path):
    apps = tmp_path / "WindowsApps"
    _stub(str(apps / "python3.exe"))
    _stub(str(apps / "python.exe"))

    resolved = _print_python(ps1_path, [str(apps)])
    assert resolved == "", (
        "with only a WindowsApps stub on PATH there is no usable python. "
        "got: " + resolved)


@_WINDOWS_ONLY
@pytest.mark.parametrize("ps1_path", [_PM_BRIEF_PS1, _PLATFORM_SYNC_PS1])
def test_a_real_python_beside_a_stub_still_resolves(ps1_path, tmp_path):
    apps = tmp_path / "WindowsApps"
    real = tmp_path / "tools"
    _stub(str(apps / "python3.exe"))
    _stub(str(real / "python3.exe"))

    resolved = _print_python(ps1_path, [str(apps), str(real)])
    assert resolved.lower().startswith(str(real).lower()), (
        "the real python3.exe must win over the WindowsApps stub. got: "
        + resolved)

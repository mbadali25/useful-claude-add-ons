"""The one PowerShell python probe every crew .ps1 hook carries.

Windows burn-in FAIL 3 (docs/review/06-windows-burn-in.md, 2c): on a host
whose `python`, `python3` and `py` were all working WindowsApps App Execution
Aliases, the old `Resolve-CrewPython` rejected each by PATH before executing
it and took only the first match per name, so it never reached the real
python.exe further down PATH. completion-audit.ps1 then blocked every Stop
with "no usable python" while `_common.sh`'s `crew_py` accepted the alias and
its bash twin proceeded.

The fixtures model that host on Linux: directories of stub executables on a
PATH built for the test, with a directory named WindowsApps. pwsh runs the
.ps1 with `OS=Windows_NT` so the flavour guard proceeds. The bash resolvers
run against the SAME PATH, so each case states what both flavours conclude.
"""
import json
import os
import pathlib
import subprocess
import sys
import time

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import crew_fixtures

SCRIPTS = pathlib.Path(__file__).resolve().parent.parent / "hooks" / "scripts"
PWSH = crew_fixtures.resolve_pwsh()
BASH = crew_fixtures.resolve_bash()
REAL = os.path.realpath(sys.executable)

needs_pwsh = pytest.mark.skipif(PWSH is None, reason="pwsh not installed - the .ps1 probe was NOT run")
needs_bash = pytest.mark.skipif(BASH is None, reason="bash not installed - the parity half was NOT run")

# Every crew .ps1 that resolves python carries this function byte for byte.
_CARRIERS = ("role-write-guard", "completion-audit", "scope-guard", "approval-hook",
             "crew-context", "platform-sync", "cloud-guard", "verify-gate", "handoff-read",
             "notify", "handoff-write")
_NAMES = ("python3", "python", "py")


def _resolver(stem):
    src = (SCRIPTS / (stem + ".ps1")).read_text(encoding="utf-8")
    start = src.index("function Resolve-CrewPython {")
    return src[start:src.index("\n}\n", start) + 3]


def _stub(directory, name, body):
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    path.write_text("#!/bin/sh\n" + body + "\n", encoding="ascii", newline="\n")
    path.chmod(0o755)
    return path


def _working(directory, names=_NAMES):
    """An alias that forwards to a real interpreter, as a WindowsApps alias
    does when Python is installed."""
    for name in names:
        _stub(directory, name, f'exec "{REAL}" "$@"')


def _broken(directory, names=_NAMES):
    """An alias with nothing behind it: no output, exit 9009, as the Store
    placeholder does when run non-interactively."""
    for name in names:
        _stub(directory, name, "exit 9009")


def _hung(directory, names=("python3",)):
    for name in names:
        _stub(directory, name, f'exec "{REAL}" -c "import time; time.sleep(60)"')


def _tools(tmp_path):
    """Everything in /usr/bin and /bin EXCEPT python, so bash's resolvers have
    `tr`/`cut` and no fixture can be rescued by the host's own interpreter."""
    tools = tmp_path / "tools"
    tools.mkdir()
    for source in ("/usr/bin", "/bin"):
        if not os.path.isdir(source):
            continue
        for name in os.listdir(source):
            if name.startswith(("python", "py")) or (tools / name).exists():
                continue
            os.symlink(os.path.join(source, name), tools / name)
    return tools


def _print_python(path_entries, stem="completion-audit"):
    env = dict(os.environ, OS="Windows_NT", PATH=os.pathsep.join(map(str, path_entries)))
    done = subprocess.run([PWSH, "-NoProfile", "-NonInteractive", "-File",
                           str(SCRIPTS / (stem + ".ps1")), "-PrintPython"],
                          env=env, stdin=subprocess.DEVNULL, capture_output=True,
                          text=True, check=False, timeout=60)
    assert done.returncode == 0, done.stderr
    return done.stdout.strip()


def _bash_resolver(fn, path_entries):
    """`_common.sh`'s `crew_py` or `crew_py_strict`, sourced and run on the
    same PATH. Returns the path it printed, or "" when it found none."""
    env = dict(os.environ, PATH=os.pathsep.join(map(str, path_entries)))
    script = f'. "{SCRIPTS / "_common.sh"}"; {fn}'
    done = subprocess.run([BASH, "-c", script], env=env, stdin=subprocess.DEVNULL,
                          capture_output=True, text=True, check=False, timeout=60)
    return done.stdout.strip() if done.returncode == 0 else ""


def _runs(interpreter):
    done = subprocess.run([interpreter, "-c", "print(1)"], capture_output=True,
                          text=True, check=False, timeout=30)
    return done.returncode == 0 and done.stdout.strip() == "1"


# --- one probe, everywhere -----------------------------------------------------

@pytest.mark.parametrize("stem", _CARRIERS)
def test_every_ps1_carries_the_one_probe_byte_for_byte(stem):
    assert _resolver(stem) == _resolver("role-write-guard")


@pytest.mark.parametrize("stem", _CARRIERS)
def test_no_ps1_rejects_a_candidate_by_its_path_or_takes_only_the_first_match(stem):
    body = _resolver(stem)
    code = [line for line in body.splitlines() if not line.lstrip().startswith("#")]

    assert [line for line in code if "WindowsApps" in line or "-First 1" in line] == []


def test_no_crew_ps1_resolves_python_any_other_way():
    """A hook that finds python without the probe is the old bug in a new
    file. Every python lookup outside the shared function goes through it."""
    offenders = []
    for path in sorted(SCRIPTS.glob("*.ps1")):
        src = path.read_text(encoding="utf-8")
        if "function Resolve-CrewPython {" in src:
            start = src.index("function Resolve-CrewPython {")
            src = src[:start] + src[src.index("\n}\n", start) + 3:]
        for line in src.splitlines():
            if "Get-Command" in line and "python" in line and not line.lstrip().startswith("#"):
                offenders.append(f"{path.name}: {line.strip()}")

    assert offenders == []


# --- (a) a WindowsApps alias that works ---------------------------------------

@needs_pwsh
@needs_bash
def test_a_working_windowsapps_alias_is_accepted_like_bash_accepts_it(tmp_path):
    apps = tmp_path / "Microsoft" / "WindowsApps"
    _working(apps)
    path = [apps, _tools(tmp_path)]

    ps1 = _print_python(path)
    loose = _bash_resolver("crew_py", path)
    strict = _bash_resolver("crew_py_strict", path)

    assert (ps1, strict, bool(loose), _runs(loose)) == (REAL, REAL, True, True)


# --- (b) a broken alias first, a real interpreter later on PATH ----------------

@needs_pwsh
@needs_bash
def test_a_broken_alias_falls_through_to_a_real_python_of_another_name(tmp_path):
    apps = tmp_path / "Microsoft" / "WindowsApps"
    _broken(apps, ("python3",))
    real = tmp_path / "AppData" / "Local" / "Python" / "bin"
    _working(real, ("python",))
    path = [apps, real, _tools(tmp_path)]

    assert (_print_python(path), _bash_resolver("crew_py_strict", path)) == (REAL, REAL)


@needs_pwsh
def test_a_broken_alias_falls_through_to_a_real_python_of_the_same_name(tmp_path):
    """The burn-in host's shape with the aliases broken: every name resolves
    to WindowsApps first, the real python.exe sits further down PATH."""
    apps = tmp_path / "Microsoft" / "WindowsApps"
    _broken(apps)
    real = tmp_path / "AppData" / "Local" / "Python" / "bin"
    _working(real, ("python",))

    assert _print_python([apps, real, _tools(tmp_path)]) == REAL


@needs_pwsh
@needs_bash
def test_bash_strict_agrees_on_a_same_named_python_behind_a_broken_alias(tmp_path):
    """Was a strict xfail: `command -v` took only the first match per name.
    crew_py_strict now walks every match (`type -ap`), as the .ps1 does."""
    apps = tmp_path / "Microsoft" / "WindowsApps"
    _broken(apps)
    real = tmp_path / "AppData" / "Local" / "Python" / "bin"
    _working(real, ("python",))
    path = [apps, real, _tools(tmp_path)]

    assert _bash_resolver("crew_py_strict", path) == _print_python(path)


# --- (c) no python at all ------------------------------------------------------

@needs_pwsh
@needs_bash
def test_no_python_anywhere_is_empty_in_every_resolver(tmp_path):
    apps = tmp_path / "Microsoft" / "WindowsApps"
    _broken(apps)
    path = [apps, _tools(tmp_path)]

    resolved = (_print_python(path), _bash_resolver("crew_py_strict", path))

    assert resolved == ("", "")


def _stop_audit(tmp_path, config):
    """completion-audit.ps1 on a Stop with no usable python. Its documented
    behaviour: fail CLOSED (exit 2, "no usable python") unless scope.mode is
    provably off, and never twice in a row for the same session."""
    root = tmp_path / "repo"
    (root / ".crew").mkdir(parents=True)
    if config is not None:
        (root / ".crew" / "config.json").write_text(json.dumps(config), encoding="utf-8")
    apps = tmp_path / "Microsoft" / "WindowsApps"
    _broken(apps)
    env = dict(os.environ, OS="Windows_NT", CLAUDE_PROJECT_DIR=str(root),
               PATH=os.pathsep.join([str(apps), str(_tools(tmp_path))]))
    payload = json.dumps({"hook_event_name": "Stop", "stop_hook_active": False,
                          "session_id": f"probe-{tmp_path.name}", "cwd": str(root)})
    done = subprocess.run([PWSH, "-NoProfile", "-File", str(SCRIPTS / "completion-audit.ps1")],
                          input=payload, cwd=str(root), env=env, capture_output=True,
                          text=True, check=False, timeout=60)
    return done.returncode, done.stderr


@needs_pwsh
def test_no_python_fails_the_completion_audit_closed_when_scope_is_armed(tmp_path):
    code, err = _stop_audit(tmp_path, {"scope": {"mode": "block"}})

    assert (code, "COMPLETION AUDIT: no usable python" in err) == (2, True)


@needs_pwsh
def test_no_python_lets_the_stop_through_when_scope_is_provably_off(tmp_path):
    code, err = _stop_audit(tmp_path, None)

    assert (code, "no usable python - not audited (scope.mode is off)" in err) == (0, True)


# --- a hung candidate ----------------------------------------------------------

@needs_pwsh
def test_a_hung_candidate_is_killed_and_the_next_one_is_tried(tmp_path):
    hang = tmp_path / "Microsoft" / "WindowsApps"
    _hung(hang)
    real = tmp_path / "real"
    _working(real, ("python3",))
    began = time.monotonic()

    resolved = _print_python([hang, real, _tools(tmp_path)])

    assert (resolved, time.monotonic() - began < 30) == (REAL, True)


# --- the burn-in host, end to end ----------------------------------------------

@needs_pwsh
@needs_bash
def test_the_burn_in_host_audits_in_both_flavours_instead_of_blocking_in_one(tmp_path):
    """Same PATH, same Stop, same repo: both flavours reach python and agree.
    Before the fix the .ps1 exited 2 "no usable python" and the .sh exited 0."""
    root = tmp_path / "repo"
    (root / ".crew").mkdir(parents=True)
    (root / ".crew" / "config.json").write_text(json.dumps({"scope": {"mode": "block"}}),
                                                encoding="utf-8")
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    apps = tmp_path / "Microsoft" / "WindowsApps"
    _working(apps)
    real = tmp_path / "AppData" / "Local" / "Python" / "bin"
    _working(real, ("python",))
    path = os.pathsep.join([str(apps), str(real), str(_tools(tmp_path))])
    payload = json.dumps({"hook_event_name": "Stop", "stop_hook_active": False,
                          "session_id": "burn-in", "cwd": str(root)})
    results = []
    for cmd, extra in (([BASH, str(SCRIPTS / "completion-audit.sh")], {}),
                       ([PWSH, "-NoProfile", "-File", str(SCRIPTS / "completion-audit.ps1")],
                        {"OS": "Windows_NT"})):
        env = dict(os.environ, CLAUDE_PROJECT_DIR=str(root), PATH=path, **extra)
        done = subprocess.run(cmd, input=payload, cwd=str(root), env=env, capture_output=True,
                              text=True, check=False, timeout=60)
        results.append((done.returncode, "no usable python" in done.stderr))

    assert results == [(0, False), (0, False)]

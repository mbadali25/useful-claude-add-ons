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

**On a REAL Windows host (`os.name == "nt"`, not the faked `OS=Windows_NT`
env var above) an extensionless stub is invisible to this suite's own
target.** `Get-Command -CommandType Application` never matches a file with
no recognised extension, and `Resolve-CrewPython`'s own native-extension gate
would skip it even if it did -- CreateProcess cannot launch it either way,
by design (see the resolver's own comment). `_stub` therefore writes a
`.cmd` file with a `win_body` translation when actually running on Windows,
so a "working"/"broken" candidate is something the real resolver can find
and probe, exactly as a real WindowsApps alias or `python.exe` is.

**The mirror-image gap sits on the bash side, and it is why this module used
to pass for the wrong reason.** MEASURED on this host: `type -ap` (what
`_common.sh`'s `crew_py`/`crew_py_strict` walk PATH with) never matches a
`.cmd` file at all -- not by bare name, not by the full `name.cmd` form, chmod
or no chmod -- so a `.cmd`-only fixture is invisible to bash exactly the way
an extensionless one is invisible to `Get-Command`. `_stub` now delegates to
`crew_fixtures.write_shim`, which writes BOTH forms on Windows: the
extensionless POSIX shim (which bash's `type -ap` finds and execs by its
shebang) and the `.cmd` (which `Get-Command`/CreateProcess find), so each
flavour has a candidate it can actually reach. That also means
`_slow_fail`, `_hang_forever` and `_spoofed_version` -- which pass no
`win_body`, so their `.cmd` content stays the inert POSIX `body` text CMD
cannot run -- are no longer untranslated on the bash side either: bash now
finds and genuinely executes their POSIX shim, which is what their own
resolvers are supposed to bound or reject. Their tests still only assert
`""`, but for the real reason now (timeout or version-floor rejection)
rather than "bash found nothing to run".

**A found bash candidate answers in POSIX form, never `REAL`'s native
one.** `crew_py_strict`'s own DECIDED CONTRACT (`_common.sh`) returns the
probed interpreter path the way bash itself would exec it --
`/c/Users/...`, converted from the candidate's own `sys.executable` -- and
`crew_py` returns the raw PATH-hit candidate, unconverted. Comparing either
directly against `REAL`'s native form is comparing two different string
shapes to a bug that happens to look latent when nothing is found on either
side. `REAL_POSIX` (`crew_fixtures.windows_to_posix(REAL)`) is the fixed
point for the strict comparisons; `crew_py`'s raw candidate is meant to be
exec'd by the SAME bash, not handed to CreateProcess, which is what `_runs`
does on Windows now.
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
# MEASURED: `crew_py_strict` never returns `REAL`'s native `C:\...` form --
# its own DECIDED CONTRACT (`_common.sh`) converts to POSIX before printing.
# This is the fixed point every strict-resolver comparison compares against.
REAL_POSIX = crew_fixtures.windows_to_posix(REAL)

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


def _stub(directory, name, body, win_body=None):
    """Windows burn-in, win-repo (2f7f71f7): every extensionless fixture in
    this module models a WindowsApps alias / real python.exe, but on a
    genuine Windows host neither `Get-Command` nor `Resolve-CrewPython`'s own
    native-extension gate ever sees an extensionless file -- so the fixture
    that is supposed to be FOUND (working or broken) silently vanishes
    instead, and every assertion expecting it to resolve to REAL fails. A
    `.cmd` file is the smallest native-launchable stand-in: `Get-Command`
    matches it, the gate passes it, and `Resolve-CrewPython` already routes
    `.cmd`/`.bat` through `cmd.exe` for exactly this shape (a pyenv-win
    shim). `win_body` is the batch translation of `body`; when the caller has
    none, the sh `body` is still written into a `.cmd` on Windows -- inert,
    not silently wrong, since every caller that omits `win_body` only asserts
    non-resolution, which an unrunnable batch file still produces.

    MEASURED: the mirror-image gap is on the bash side -- `type -ap` (what
    `crew_py`/`crew_py_strict` walk PATH with) never matches a `.cmd` file at
    all on this host, so a `.cmd`-only fixture is invisible to bash exactly
    the way an extensionless one is invisible to `Get-Command`. Delegating to
    `crew_fixtures.write_shim` writes BOTH forms on Windows -- the
    extensionless POSIX shim bash finds by its shebang, and the `.cmd`
    `Get-Command`/CreateProcess find -- so a candidate this function writes
    is reachable by whichever flavour asks."""
    sh_body = "#!/bin/sh\n" + body + "\n"
    cmd_body = "@echo off\r\n" + (win_body if win_body is not None else body) + "\r\n"
    return pathlib.Path(crew_fixtures.write_shim(directory, name, sh_body=sh_body, cmd_body=cmd_body))


def _working(directory, names=_NAMES):
    """An alias that forwards to a real interpreter, as a WindowsApps alias
    does when Python is installed."""
    for name in names:
        _stub(directory, name, f'exec "{REAL}" "$@"', win_body=f'"{REAL}" %*')


def _broken(directory, names=_NAMES):
    """An alias with nothing behind it: no output, exit 9009, as the Store
    placeholder does when run non-interactively."""
    for name in names:
        _stub(directory, name, "exit 9009", win_body="exit /b 9009")


def _hung(directory, names=("python3",)):
    for name in names:
        _stub(directory, name, f'exec "{REAL}" -c "import time; time.sleep(60)"',
              win_body=f'"{REAL}" -c "import time; time.sleep(60)"')


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
    """True when `interpreter` answers `-c "print(1)"` with `1`.

    MEASURED: `crew_py`'s own DECIDED CONTRACT (`_common.sh`) is that its
    answer is POSIX-shaped and meant to be exec'd by the SAME bash ("a
    caller that only does `"$py" ...` needs nothing further") -- handing that
    string straight to `subprocess.run` on Windows hands CreateProcess a
    path it cannot open (`WinError 2`/`87`, reproduced against this exact
    shape while diagnosing this fix). Route through bash there, which is
    what every real caller of `crew_py` does."""
    if os.name == "nt" and BASH is not None:
        done = subprocess.run([BASH, "-c", f'"{interpreter}" -c "print(1)"'],
                              capture_output=True, text=True, check=False, timeout=30)
        return done.returncode == 0 and done.stdout.strip() == "1"
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


@pytest.mark.parametrize("stem", _CARRIERS)
def test_an_extensionless_candidate_is_refused_before_process_start_on_real_windows(stem):
    """Windows burn-in FAIL, win-repo: a fixture put an extensionless
    `#!/bin/bash` `python3` stub first on PATH; the old resolver executed it
    anyway, and the parked pwsh process (1.94s CPU, no children, no record
    written) matches CreateProcess failing to launch a file with no
    recognised extension, not a hung candidate the 3s-per-candidate bound
    already covers.

    CreateProcess (what UseShellExecute=$false hands the candidate to) can
    only start a real PE executable or route a `.cmd`/`.bat` through
    cmd.exe -- never an extensionless file. This is a STRING-level test, not
    a behavioural one: it cannot execute the true-Windows branch on a Linux
    runner ($IsWindows is genuinely $false here, same as production), so it
    asserts the source directly -- the native-extension allow-list exists,
    is checked before ProcessStartInfo is ever built, and is gated on real
    OS detection rather than the flavour guard's $env:OS seam, which this
    whole test module also sets to 'Windows_NT' while running pwsh on Linux
    to exercise every extensionless WindowsApps-alias fixture above. Gating
    on that seam instead of $IsWindows would make every one of those cases
    fail here, since a real seam-based gate cannot distinguish "really
    Windows" from "faked for this test"."""
    body = _resolver(stem)
    assert "IsWindows" in body, "no real-Windows detection found"
    for ext in (".exe", ".com", ".cmd", ".bat"):
        assert ext in body, f"native extension {ext!r} missing from the allow-list"
    launch_pos = body.index("ProcessStartInfo")
    assign_line = next(
        line for line in body.splitlines()
        if "IsWindows" in line and "=" in line and not line.lstrip().startswith("#"))
    gate_pos = body.index(assign_line)
    assert gate_pos < launch_pos, (
        "the extension gate must be checked before ProcessStartInfo is "
        "constructed, or a candidate this gate should refuse still reaches "
        "Process.Start")
    # The seam every fixture above relies on must NOT be what gates this: the
    # ASSIGNMENT line itself (not nearby prose explaining the contrast) must
    # not read $env:OS -- $env:OS is set to 'Windows_NT' for every case in
    # this file, so gating the real check on it would reject the
    # extensionless stubs _working/_broken/_hung write, on this very host,
    # which the parametrized cases above prove is not what happens.
    assert "$env:OS" not in assign_line, (
        "the extensionless-file gate's real-Windows detection reads $env:OS "
        "instead of real OS detection ($IsWindows / OSVersion) -- it would "
        "misfire on every Linux-run fixture in this file, which all rely on "
        "$env:OS='Windows_NT' to get past the flavour guard while running "
        "real, valid extensionless shims: " + assign_line)


@needs_pwsh
def test_an_extensionless_candidate_still_resolves_on_the_real_linux_this_suite_runs_on(tmp_path):
    """The other half of the same contract, proven by EXECUTION rather than
    by reading source: on this host, which is genuinely not Windows, the
    gate above must never fire, so an extensionless shim ahead of nothing
    else on PATH is still found and run -- exactly what _working() already
    depends on throughout this module, pinned here directly against the one
    new code path this ticket adds. Not parametrized over every carrier:
    `-PrintPython` is only wired on seven of the eleven (verify-gate,
    completion-audit, scope-guard, approval-hook, crew-context,
    platform-sync, role-write-guard); the byte-identical check above already
    proves the other four share this exact function body."""
    apps = tmp_path / "bin"
    _working(apps, ("python3",))
    assert _print_python([apps, _tools(tmp_path)]) == REAL


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

    assert (ps1, strict, bool(loose), _runs(loose)) == (REAL, REAL_POSIX, True, True)


# --- (b) a broken alias first, a real interpreter later on PATH ----------------

@needs_pwsh
@needs_bash
def test_a_broken_alias_falls_through_to_a_real_python_of_another_name(tmp_path):
    apps = tmp_path / "Microsoft" / "WindowsApps"
    _broken(apps, ("python3",))
    real = tmp_path / "AppData" / "Local" / "Python" / "bin"
    _working(real, ("python",))
    path = [apps, real, _tools(tmp_path)]

    assert (_print_python(path), _bash_resolver("crew_py_strict", path)) == (REAL, REAL_POSIX)


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
    crew_py_strict now walks every match (`type -ap`), as the .ps1 does.

    Both sides resolve to REAL here, but never in the same string shape --
    `crew_py_strict` answers POSIX (`_common.sh`'s DECIDED CONTRACT),
    `_print_python` answers native. `windows_to_posix` on the ps1 side is
    the fixed point, same as `REAL_POSIX` elsewhere in this module."""
    apps = tmp_path / "Microsoft" / "WindowsApps"
    _broken(apps)
    real = tmp_path / "AppData" / "Local" / "Python" / "bin"
    _working(real, ("python",))
    path = [apps, real, _tools(tmp_path)]

    assert _bash_resolver("crew_py_strict", path) == crew_fixtures.windows_to_posix(_print_python(path))


# --- (c) no python at all ------------------------------------------------------

@needs_pwsh
@needs_bash
def test_no_python_anywhere_is_empty_in_every_resolver(tmp_path):
    apps = tmp_path / "Microsoft" / "WindowsApps"
    _broken(apps)
    path = [apps, _tools(tmp_path)]

    resolved = (_print_python(path), _bash_resolver("crew_py_strict", path))

    assert resolved == ("", "")


# --- (d) a proven Python 3.7 -- Codex r1 finding 3's own reproduction ---------

def _spoofed_version(directory, version_tuple, names=_NAMES):
    """A real interpreter whose sys.version_info is monkeypatched to
    `version_tuple` before it runs whatever -c code it is handed -- the only
    way to fake an old CPython on a host that has none installed. DOUBLE
    quotes on the release level: repr()'s default single quotes would close
    the shell's own single-quoted -c argument early."""
    major, minor, micro, level, serial = version_tuple
    tuple_text = f'({major}, {minor}, {micro}, "{level}", {serial})'
    body = ('if [ "$1" = "-c" ]; then\n'
            f'  exec "{REAL}" -c \'import sys; sys.version_info={tuple_text}; '
            "exec(sys.argv[1])' \"$2\"\n"
            "fi\n"
            f'exec "{REAL}" "$@"\n')
    for name in names:
        _stub(directory, name, body)


@needs_pwsh
@needs_bash
def test_a_proven_python_37_is_rejected_by_both_flavours(tmp_path):
    """Before the fix: bash's crew_py_strict accepted this candidate (any
    real, executable sys.executable was enough) while the PowerShell probe's
    own floor rejected it -- exactly the review's reproduction, put only
    CPython 3.7 on PATH."""
    old = tmp_path / "py37"
    _spoofed_version(old, (3, 7, 9, "final", 0))
    path = [old, _tools(tmp_path)]

    assert (_print_python(path), _bash_resolver("crew_py_strict", path)) == ("", "")


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


# --- an overall deadline bounds several hung candidates -----------------------

def _many_hung(tmp_path, count, name="python3"):
    """`count` separate directories, each with ONE hung candidate named
    `name`, so Get-Command -All / `type -ap` finds all of them as distinct
    PATH matches -- the shape an overall deadline exists to bound, as
    opposed to the single hung candidate above."""
    dirs = []
    for i in range(count):
        directory = tmp_path / f"hang{i}"
        _hung(directory, (name,))
        dirs.append(directory)
    return dirs


@needs_pwsh
@needs_bash
def test_an_overall_deadline_bounds_several_hung_candidates(tmp_path):
    """Four candidates at the per-candidate 3s bound cost 12s+ before even
    reaching a real python further down PATH -- past the shortest hook
    timeout that resolves python this way (bridge-status.ps1's twin, 10s),
    even though each individual probe is bounded. An overall deadline must
    give up well inside that rather than pay the full per-candidate cost for
    every hung entry -- which can mean answering "no python" with a working
    one still further down PATH, the same honest-failure-over-budget-
    overrun tradeoff `event_claim.py` makes for a suppressed emission."""
    hangs = _many_hung(tmp_path, 4)
    real = tmp_path / "real"
    _working(real, ("python3",))
    path = [*hangs, real, _tools(tmp_path)]

    began = time.monotonic()
    ps1_resolved = _print_python(path)
    ps1_elapsed = time.monotonic() - began

    began = time.monotonic()
    bash_resolved = _bash_resolver("crew_py_strict", path)
    bash_elapsed = time.monotonic() - began

    assert (ps1_elapsed < 10, bash_elapsed < 10) == (True, True), (
        f"ps1={ps1_elapsed}s ({ps1_resolved!r}) bash={bash_elapsed}s "
        f"({bash_resolved!r}) -- an overall deadline should have given up "
        "well before paying the full per-candidate cost for every hung entry")


# --- FIX (Codex review of crew-1.0, item 2): the deadline was only checked
#     BEFORE launching a candidate; the wait itself was then a flat 3000ms
#     (ps1) / 3s (bash) regardless of how much budget was left. Several
#     candidates that each fail just under the per-candidate bound -- close
#     to, but under, the 8s deadline -- followed by one that hangs could
#     still overrun both the deadline and the 10s hook timeout that calls
#     this. Unlike the all-hung case above (each hung candidate is bounded
#     at its own 3s regardless, so four of them already sit close to the
#     10s ceiling on their own), this shape isolates the actual defect: the
#     slow candidates alone stay safely under 8s, so any elapsed time at or
#     past 10s can only come from the FINAL wait not being capped to what
#     remained.

def _slow_fail(directory, delay_seconds, names=("python3",)):
    """Ignores whatever it is asked and sleeps `delay_seconds` before
    exiting 1 -- a PATH entry that answers, eventually, but never as a
    usable interpreter."""
    for name in names:
        _stub(directory, name, f"sleep {delay_seconds}\nexit 1")


def _hang_forever(directory, names=("python3",)):
    for name in names:
        _stub(directory, name, "sleep 60")


@needs_pwsh
@needs_bash
def test_near_deadline_candidates_then_a_hang_stay_within_the_hook_timeout(tmp_path):
    """Four candidates that each fail after 1.8s (7.2s total, comfortably
    under the 8s deadline) followed by one that hangs. Before the fix the
    hung candidate's wait was a flat 3000ms/3s regardless of budget
    remaining, pushing the total past 10s. With the fix the wait is capped
    to whatever remains of the 8s budget. (Three candidates at 2.5s --
    closer to the boundary -- measured flakier: per-candidate overhead can
    tip the deadline check before the final candidate is even launched.)"""
    slow_dirs = []
    for i in range(4):
        d = tmp_path / f"slow{i}"
        _slow_fail(d, 1.8)
        slow_dirs.append(d)
    hang = tmp_path / "hang"
    _hang_forever(hang)
    path = [*slow_dirs, hang, _tools(tmp_path)]

    began = time.monotonic()
    ps1_resolved = _print_python(path)
    ps1_elapsed = time.monotonic() - began

    began = time.monotonic()
    bash_resolved = _bash_resolver("crew_py_strict", path)
    bash_elapsed = time.monotonic() - began

    assert (ps1_elapsed < 10, bash_elapsed < 10, ps1_resolved, bash_resolved) == (
        True, True, "", ""), (
        f"ps1={ps1_elapsed}s ({ps1_resolved!r}) bash={bash_elapsed}s "
        f"({bash_resolved!r}) -- the final candidate's wait must be capped "
        "to what remains of the 8s deadline, not a flat 3s/3000ms, or the "
        "total overruns the 10s hook timeout this bounds against")


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

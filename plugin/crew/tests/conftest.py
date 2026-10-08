"""Shared test isolation for the whole suite.

Every test that touches `crew_config` -- directly, through
`crew_state.collect`'s `cfg_override`, or through `pm_brief`'s layered brief
-- must not depend on whatever happens to be at the real, machine-global
`~/.claude/crew/config.json`. This autouse fixture points that path at
somewhere that provably does not exist, for every test, by default. A test
that specifically exercises the global layer overrides it again with its own
scratch file; `monkeypatch` allows a later `setattr` to win within the same
test and undoes everything at teardown regardless of ordering.
"""
import os
import pathlib
import re
import shutil
import site
import tempfile

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import crew_config
import crew_fixtures
import crew_state
# Re-exported so pytest discovers it as a fixture package-wide (fixture
# discovery is by name in a conftest module's namespace, not by definition
# site) -- see crew_fixtures.gate_processes's own docstring for what it does.
from crew_fixtures import gate_processes  # noqa: F401  pylint: disable=unused-import
from crew_fixtures import fixture_git_env


@pytest.fixture(autouse=True)
def _no_real_global_config(tmp_path, tmp_path_factory, monkeypatch):
    """Point every reader of the machine-global config at a path that does not
    exist, so no test can read or write the developer's real
    `~/.claude/crew/config.json`.

    BOTH names are patched, and that is not belt-and-braces. The path is
    canonical in `crew_state` and re-exported by `crew_config`; a module that
    reads it through `crew_state` -- `crew_upgrade` does, because it must not
    import `crew_config` -- is NOT isolated by patching `crew_config` alone.
    Patching one name silently left `crew_upgrade.global_theme_defeats_
    migration` reading the real file during the suite, which is exactly the
    "must never touch real config" rule this fixture exists to enforce.

    A monkeypatched attribute is per-name, not per-value: rebinding one module
    attribute does nothing to another module's binding of the same object.
    """
    unused = str(tmp_path / "unused-global-config.json")
    monkeypatch.setattr(crew_config, "GLOBAL_CONFIG_PATH", unused)
    monkeypatch.setattr(crew_state, "GLOBAL_CONFIG_PATH", unused)
    # T-0050: every crew config write takes a backup first. An ENVIRONMENT
    # variable rather than a patched attribute, so a test's subprocess (a
    # hook, the CLI) inherits it too and never writes under the real
    # `~/.claude/crew/backups`.
    monkeypatch.setenv("CREW_BACKUP_DIR", str(tmp_path / "crew-backups"))

    # Same rule, second environment channel. `pm_brief.main` resolves its root
    # as `payload["cwd"] or $CLAUDE_PROJECT_DIR or os.getcwd()`, so a test that
    # pins the fallback with `monkeypatch.chdir(tmp_path)` pins only the THIRD
    # rung -- the environment variable sits above it and wins. Claude Code sets
    # that variable to the repo you have open; CI does not set it at all.
    #
    # So `test_main_exits_zero_on_garbage_stdin` asserted "garbage in, nothing
    # out" and got it in CI while, under Claude Code with a crew repo open, the
    # same call produced a full 669-character brief. Green where nobody looks,
    # red on the maintainer's machine -- the mirror image of the bug its own
    # comment says the chdir pin was added to fix.
    #
    # Cleared for every test by default. A test that wants the variable sets it
    # afterwards (`monkeypatch.setenv`, or an explicit `env=` for a subprocess)
    # and that still wins; this only removes the ambient value nobody declared.
    monkeypatch.delenv("CLAUDE_PROJECT_DIR", raising=False)
    # Same rule for T-0016's session records: auto-clear reads
    # `${CLAUDE_CONFIG_DIR:-~/.claude}/sessions`, and every case points HOME at
    # a fixture -- so an ambient CLAUDE_CONFIG_DIR would be the one way left to
    # read the developer's real records. crew_fixtures.bind_session sets it
    # back, to the fixture, wherever a case wants a record.
    monkeypatch.delenv("CLAUDE_CONFIG_DIR", raising=False)
    monkeypatch.delenv("CREW_AUTOCLEAR_PROC_STUB", raising=False)

    # Third channel: the developer's GLOBAL git config reaches every fixture
    # `git commit`, and with `commit.gpgsign=true` each one runs their signing
    # program against their real key. Only context_fixtures.git opted out, by
    # `-c`. Measured once, on an ssh-signing Linux container (2026-09-29):
    # 83 ms a commit signed, 7 ms unsigned, paid by every module whose fixtures
    # commit -- and on a gpg host with a pinentry, a suite that can stop and
    # prompt for a passphrase. GIT_CONFIG_COUNT/KEY/VALUE
    # (git >= 2.31) outranks every config file, so this holds whatever the
    # global file says, and reaches any subprocess that inherits os.environ.
    # A test that needs signing sets its own `-c` or env and still wins. The
    # same pins stop git's background maintenance (see crew_fixtures).
    #
    # APPENDED after whatever GIT_CONFIG_COUNT the runner already carries,
    # never written from slot 0: a cloud container here exports three entries
    # of its own (URL rewrites, credential.interactive), and overwriting slots
    # 0-1 while setting the count to 2 silently dropped all three.
    for name, value in fixture_git_env(os.environ).items():
        monkeypatch.setenv(name, value)

    # Fourth channel (L-0557): pwsh's multicore-JIT startup profile,
    # `$XDG_CACHE_HOME/powershell/StartupProfileData-NonInteractive`. Every
    # pwsh reads it at start-up and rewrites it at exit, so concurrent pwsh
    # sharing the user's ~/.cache race on one file, and a reader that catches
    # it half-written dies before running a statement ("Stack overflow." -6,
    # or SIGSEGV -11) - about one `-m slow -n 12` run in 20-50. Each test gets
    # its own dir; the root moves with it, so the audit hook conftest installs
    # refuses a pwsh whose cache is anywhere else. A no-op for Windows pwsh
    # (LOCALAPPDATA).
    #
    # Created here, so the value names a directory that exists rather than one
    # that appears only if some pwsh runs first -- and created by
    # `tmp_path_factory.mktemp`, BESIDE tmp_path under the same basetemp, not
    # inside it: a `tmp_path / "xdg-cache"` made for every test showed up in
    # nine tests that assert exactly what their tmp_path holds
    # (test_config_files, test_crew_fixtures, test_webtest_scaffold). mktemp
    # numbers each one, so no two tests share it, and pytest removes it with
    # the basetemp.
    xdg_cache = tmp_path_factory.mktemp("xdg-cache")
    monkeypatch.setenv("XDG_CACHE_HOME", str(xdg_cache))
    monkeypatch.setattr(crew_fixtures, "_PWSH_CACHE_ROOT", str(xdg_cache))


@pytest.fixture(autouse=True)
def _isolated_home(tmp_path_factory, monkeypatch):
    """Sixth channel (L-0709): the home directory itself. Every test, and every
    subprocess that inherits `os.environ`, gets a home of its own as HOME,
    USERPROFILE and the XDG config/data/state directories.

    `_no_real_global_config` moves one path in this process. A spawned crew
    script recomputes `~/.claude/crew/config.json` from HOME, so it still read
    the operator's file: `crew_autopilot.py status` said `mode: plan` (L-0704)
    and crew-context.sh announced the operator's inert `autopilot.*` keys into
    a test that expects silence (L-0729). Green in CI, which has no user layer;
    red on the machine whose Stop hook runs the suite.

    `crew_fixtures.home_audit` is on from the start of the test's setup to
    the end of its teardown (`pytest_runtest_setup` / `_teardown` below), so a
    module or session fixture set up for it is audited too: an open under a
    real home, or a spawn handed a real HOME or a directory inside one, is
    refused and recorded, and the teardown fails the test naming each path.
    `CREW_TEST_REAL_HOME` is removed for the test, so nothing it spawns is
    handed the real home's path. A test that wants another home sets HOME
    afterwards, and that still wins.

    Made by `tmp_path_factory.mktemp`, BESIDE tmp_path, for the reason the XDG
    cache above is: tests assert exactly what their tmp_path holds."""
    home = tmp_path_factory.mktemp("home")
    for name, value in crew_fixtures.home_env(home).items():
        monkeypatch.setenv(name, value)
    monkeypatch.delenv(crew_fixtures.REAL_HOME_VAR, raising=False)
    return home


@pytest.hookimpl(wrapper=True)
def pytest_runtest_setup(item):  # pylint: disable=unused-argument
    """Turn the home audit on before any fixture of this test is set up."""
    del crew_fixtures.HOME_VIOLATIONS[:]
    crew_fixtures.set_home_guard(_REAL_HOMES, _HOME_ALLOWED)
    return (yield)


@pytest.hookimpl(wrapper=True)
def pytest_runtest_teardown(item, nextitem):  # pylint: disable=unused-argument
    """Turn it off after the last teardown, and fail the test with every path
    it recorded -- including those the code under test swallowed."""
    try:
        return (yield)
    finally:
        crew_fixtures.set_home_guard(None)
        found = list(crew_fixtures.HOME_VIOLATIONS)
        del crew_fixtures.HOME_VIOLATIONS[:]
        if found:
            pytest.fail("this test reached the operator's real home (L-0709):\n  "
                        + "\n  ".join(dict.fromkeys(found)), pytrace=False)


@pytest.fixture(autouse=True)
def _isolated_tmpdir(tmp_path_factory, monkeypatch):
    """Fifth channel (T-0065, item 7): the temp directory. Every test, and
    every subprocess that inherits `os.environ`, gets its own directory as
    `TMPDIR`/`TEMP`/`TMP` and as `tempfile`'s own cached directory.

    Measured on the host TSS shares: its `/tmp` held 7,798
    `crew-completion-audit.*` markers (each test's distinct project path
    leaves one, by design, in `${TMPDIR:-/tmp}`) and hundreds of auto-clear
    sender scripts that a test's `bash` shim reads and never runs. Together
    with other leftovers they exhausted the inodes, and the guard and the
    Stop verify-gate then failed closed. Under this fixture anything a test
    leaves behind goes away with pytest's basetemp.

    Made by `tmp_path_factory.mktemp`, BESIDE tmp_path rather than inside it,
    for the reason the XDG cache above is: tests assert exactly what their
    tmp_path holds, and a `tmp` subdirectory there failed twelve of them.

    `tempfile.tempdir` is patched too: `gettempdir()` caches its first answer
    for the life of the process, so the environment alone would not reach an
    in-process `mkstemp`. A test that wants another temp directory sets its
    own `TMPDIR` afterwards (or passes an explicit `env=`) and that wins."""
    tmp = tmp_path_factory.mktemp("tmpdir")
    for name in ("TMPDIR", "TEMP", "TMP"):
        monkeypatch.setenv(name, str(tmp))
    monkeypatch.setattr(tempfile, "tempdir", str(tmp))


# --- the `slow` marker: the full per-shell hook matrix ------------------------
#
# A conftest hook rather than `addopts = -m "not slow"`: this repo has no
# pytest ini, and one at the root would reach every suite CI collects in the
# same process (gizmoduck, the skills), while a `-m` given on the command line
# REPLACES an addopts `-m` rather than combining with it. The hook touches only
# items that carry the marker, and only crew's tests carry it.
#
#   pytest plugin/crew/tests               the slow set is deselected
#   pytest plugin/crew/tests -m slow       only the slow set
#   pytest plugin/crew/tests --run-slow    everything
#
# `-n auto` (pytest-xdist: optional, not a dependency) works with all three.


def pytest_addoption(parser):
    parser.addoption(
        "--run-slow", action="store_true", default=False,
        help="crew: also run tests marked `slow` (the full bash/pwsh hook "
             "matrix). `-m slow` runs only those.")


_XDG_PREVIOUS = "unset"
# Every variable the session home (below) sets, with the value it replaced
# (None = unset), restored at unconfigure.
_HOME_PREVIOUS = {}
_HOME_SESSION = None
_HOME_ALLOWED = ()
_REAL_HOMES = ()
# The checkout this conftest sits in. A CI checkout lives under the runner's
# home (/home/runner/work/...), so the home audit must allow it.
_REPO_ROOT = str(pathlib.Path(__file__).resolve().parents[3])


def _isolate_home():
    """Session half of the home isolation (L-0709): a session-wide home for
    spawns outside any test (collection, module fixtures), the record of the
    real homes for the audit and for xdist workers, then the audit hook. The
    autouse fixture narrows the home to each test.

    Two tool locations derive from HOME and are carried over, because they
    hold installed code rather than configuration: the Python user base (a
    `pip install --user` pytest must still import in a spawned interpreter or
    an xdist worker) and pwsh's CurrentUser module directory (the
    PSScriptAnalyzer the review-check tests run)."""
    global _HOME_SESSION, _HOME_ALLOWED, _REAL_HOMES  # pylint: disable=global-statement
    homes = _REAL_HOMES = crew_fixtures.real_homes()
    carry = {crew_fixtures.REAL_HOME_VAR: os.pathsep.join(homes)}
    if not os.environ.get("PYTHONUSERBASE"):
        carry["PYTHONUSERBASE"] = site.getuserbase()
    modules = [os.path.join(h, ".local", "share", "powershell", "Modules") for h in homes]
    modules = [m for m in modules if os.path.isdir(m)]
    if modules and os.name != "nt":
        current = os.environ.get("PSModulePath")
        carry["PSModulePath"] = os.pathsep.join(modules + ([current] if current else []))
    _HOME_ALLOWED = crew_fixtures.home_allowed_prefixes(_REPO_ROOT, homes)
    _HOME_SESSION = tempfile.mkdtemp(prefix="crew-home-")
    carry.update(crew_fixtures.home_env(_HOME_SESSION))
    for name, value in carry.items():
        _HOME_PREVIOUS.setdefault(name, os.environ.get(name))
        os.environ[name] = value
    crew_fixtures.install_home_audit()


def _restore_home():
    global _HOME_SESSION  # pylint: disable=global-statement
    crew_fixtures.set_home_guard(None)
    for name, value in _HOME_PREVIOUS.items():
        if value is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = value
    _HOME_PREVIOUS.clear()
    if _HOME_SESSION:
        shutil.rmtree(_HOME_SESSION, ignore_errors=True)
    _HOME_SESSION = None


def _isolate_pwsh_cache():
    """Session half of the pwsh cache isolation (L-0557): a session-wide
    XDG_CACHE_HOME for spawns outside any test (collection, module fixtures),
    then the audit hook. The autouse fixture narrows it to each test."""
    global _XDG_PREVIOUS  # pylint: disable=global-statement
    _XDG_PREVIOUS = os.environ.get("XDG_CACHE_HOME")
    session = tempfile.mkdtemp(prefix="crew-xdg-")
    os.environ["XDG_CACHE_HOME"] = session
    crew_fixtures.set_pwsh_cache_session(session)
    crew_fixtures.install_pwsh_cache_audit()


def pytest_unconfigure(config):  # pylint: disable=unused-argument
    _restore_home()
    session = crew_fixtures.pwsh_cache_session_dir()
    crew_fixtures.set_pwsh_cache_session(None)
    if _XDG_PREVIOUS is None:
        os.environ.pop("XDG_CACHE_HOME", None)
    elif _XDG_PREVIOUS != "unset":
        os.environ["XDG_CACHE_HOME"] = _XDG_PREVIOUS
    if session:
        shutil.rmtree(session, ignore_errors=True)


def pytest_configure(config):
    _isolate_pwsh_cache()
    _isolate_home()
    config.addinivalue_line(
        "markers",
        "slow: the full bash/pwsh driver matrix for a hook; deselected by "
        "default, run with -m slow or --run-slow")
    # A test that asserts ELAPSED WALL-CLOCK against a real bound (a hook's
    # timeout, a probe's deadline). Correct serially; under pytest-xdist the
    # workers beside it take the CPU it is timing, and in crew 1.0.62's first
    # CI run `test_near_deadline_candidates_then_a_hang_stay_within_the_hook_
    # timeout` read ps1=10.25s against its 10s bound on 2 of 6 jobs. The bound
    # is the hook's real timeout, so loosening it would weaken the check;
    # instead every parallel caller runs `-m "not wallclock"` and then this set
    # on its own, serially. Selected like any marker; `slow` handling is apart.
    config.addinivalue_line(
        "markers",
        "wallclock: asserts elapsed time against a real bound; run serially, "
        "never under -n (pytest-xdist)")
    config.addinivalue_line(
        "markers",
        "quarantine(owner, ticket, reason): a known timing flake, deselected by "
        "default until its ticket fixes it; owner and ticket are required. Run "
        "with -m quarantine")


_QUARANTINE_TOKEN_RE = re.compile(r"(?<!\w)quarantine(?!\w)")
_TICKET_RE = re.compile(r"^[A-Z]-\d{4}$")
# A skip whose reason says the test is unreliable is a quarantine without an
# owner. Matched on the marker's reason only; a test that skips at run time
# with pytest.skip() is not visible at collection.
_FLAKE_REASON_RE = re.compile(r"flak|timing|intermittent", re.IGNORECASE)


def _quarantine_problem(item):
    """None, or why `item`'s markers break the quarantine rule (L-0709)."""
    for mark in item.iter_markers("quarantine"):
        owner, ticket = mark.kwargs.get("owner"), mark.kwargs.get("ticket")
        if not (isinstance(owner, str) and owner.strip()):
            return "quarantine marker without an owner= naming who fixes it"
        if not (isinstance(ticket, str) and _TICKET_RE.match(ticket)):
            return f"quarantine marker without a ticket= id like L-0001 (got {ticket!r})"
    for name in ("skip", "skipif", "xfail"):
        for mark in item.iter_markers(name):
            reason = mark.kwargs.get("reason") or (
                mark.args[0] if name == "skip" and mark.args else "")
            if isinstance(reason, str) and _FLAKE_REASON_RE.search(reason):
                return (f"{name} with reason {reason!r}: an unreliable test is "
                        "quarantined with @pytest.mark.quarantine(owner=..., ticket=...), "
                        "never also skipped")
    return None


def _deselect_quarantined(config, items):
    """Validate every quarantine marker, refuse an ownerless flake skip, and
    deselect quarantined tests unless a `-m` expression names `quarantine`."""
    problems = [f"{item.nodeid}: {why}" for item in items
                for why in [_quarantine_problem(item)] if why]
    if problems:
        raise pytest.UsageError("crew quarantine rule (L-0709):\n  " + "\n  ".join(problems))
    if _QUARANTINE_TOKEN_RE.search(config.option.markexpr or ""):
        return
    keep, drop = [], []
    for item in items:
        (drop if item.get_closest_marker("quarantine") else keep).append(item)
    if drop:
        config.hook.pytest_deselected(items=drop)
        items[:] = keep


_SLOW_TOKEN_RE = re.compile(r"(?<!\w)slow(?!\w)")


def pytest_collection_modifyitems(config, items):
    """Deselect `slow` unless asked for, by `--run-slow` or by any `-m`
    expression naming it -- so `-m slow` and `-m "slow and not pwsh"` both
    select from the full set rather than from an already-emptied one.

    `_SLOW_TOKEN_RE` is a WORD match, not `"slow" in markexpr`: a bare
    substring check reads `slow` inside `slowfoo` too, so `-m "not slowfoo"`
    -- a marker that has nothing to do with this one -- read as "slow was
    named" and returned early, collecting the full set (including the
    deselected-by-default matrix) instead of applying the expression the
    caller actually asked for.

    Quarantined timing flakes (L-0709) are handled first, by
    `_deselect_quarantined`."""
    _deselect_quarantined(config, items)
    if config.getoption("--run-slow") or _SLOW_TOKEN_RE.search(config.option.markexpr or ""):
        return
    keep, drop = [], []
    for item in items:
        (drop if item.get_closest_marker("slow") else keep).append(item)
    if drop:
        config.hook.pytest_deselected(items=drop)
        items[:] = keep

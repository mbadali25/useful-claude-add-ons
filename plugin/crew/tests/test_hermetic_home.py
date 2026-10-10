"""No crew test reads or writes the operator's real home (L-0709, L-0729).

conftest's `_isolated_home` gives every test a home of its own, and
`crew_fixtures.home_audit` refuses an open under the real home, or a spawn
handed the real HOME, while a test runs. These cases hold both halves:

- the isolation: HOME, USERPROFILE and the XDG directories are the test's own,
  in this process and in a child it spawns;
- the regression: with a populated operator home -- the `autopilot.*` keys that
  turned `test_bash_flavour_emits_and_logs_nothing_when_inject_is_false` and
  `test_status_mode_line_reads_off_by_default` red on the owner's machine --
  those tests still pass. Remove the HOME override from conftest and this
  case goes red;
- the audit: must-block and must-allow cases, pure and end to end;
- the quarantine rule: a timing flake is deselected only through a marker that
  names an owner and a ticket.

The end-to-end cases run an inner pytest whose operator home is a planted
directory, so the real one is never read even when the check works.
"""
import json
import os
import pathlib
import subprocess
import sys

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import crew_fixtures

CREW_TESTS = pathlib.Path(__file__).resolve().parent
HOOK_SCRIPTS = CREW_TESTS.parent / "hooks" / "scripts"
INNER_TIMEOUT_S = 600

# What the owner's machine layer held when L-0729 was filed (2026-10-08).
OPERATOR_CONFIG = {
    "autopilot": {"approval": "self", "deploy": "all", "questions": "self", "mode": "plan",
                  "maxPhases": 100, "ship": "merge", "reviewPolicy": "fix-and-rereview",
                  "maxLanes": 3, "maxTicketsPerRun": 50},
    "memory": {"mode": "obsidian", "vaultPath": "/nonexistent-vault"},
}

# The tests that read the user layer on the owner's machine before L-0709.
USER_LAYER_TESTS = (
    "test_crew_context_wrappers.py::test_bash_flavour_emits_and_logs_nothing_when_inject_is_false",
    "test_crew_autopilot_status.py::test_status_mode_line_reads_off_by_default",
)


def _operator_home(tmp_path):
    home = tmp_path / "operator-home"
    config = home / ".claude" / "crew" / "config.json"
    config.parent.mkdir(parents=True)
    config.write_text(json.dumps(OPERATOR_CONFIG), encoding="utf-8")
    return home


def _inner_env(home, **extra):
    """os.environ as a fresh pytest would see it on a machine whose real home
    is `home`: no record of this run's real home, no xdist worker identity."""
    env = dict(os.environ)
    for name in (crew_fixtures.REAL_HOME_VAR, "PYTEST_CURRENT_TEST", "PYTEST_XDIST_WORKER",
                 "PYTEST_XDIST_WORKER_COUNT", "PYTEST_XDIST_TESTRUNUID", "PYTEST_ADDOPTS"):
        env.pop(name, None)
    for name, _rel in crew_fixtures.XDG_HOME_DIRS:
        env.pop(name, None)
    env["HOME"] = env["USERPROFILE"] = str(home)
    env.update(extra)
    return env


def _run_dir(tmp_path):
    """Where an inner run's probes, ini and cwd live: apart from the planted
    home, because the cwd and a probe's directory join sys.path, and the audit
    allows sys.path."""
    run = tmp_path / "run"
    run.mkdir(exist_ok=True)
    return run


def _pytest(tmp_path, args, env):
    """An inner pytest with an empty ini of its own, so no outer addopts apply."""
    run = _run_dir(tmp_path)
    ini = run / "inner.ini"
    ini.write_text("[pytest]\n", encoding="utf-8")
    return subprocess.run(
        [sys.executable, "-m", "pytest", "-c", str(ini), "--rootdir", str(run),
         "-p", "no:cacheprovider", "-p", "no:xdist", "-q", "-rA", *args],
        cwd=str(run), env=env, capture_output=True, text=True, check=False,
        stdin=subprocess.DEVNULL, timeout=INNER_TIMEOUT_S)


def _probe(tmp_path, name, body):
    """A test file outside the tree, run with crew's conftest loaded as a plugin."""
    path = _run_dir(tmp_path) / name
    path.write_text(body, encoding="utf-8")
    return path


def _conftest_env(home, **extra):
    return _inner_env(home, PYTHONPATH=os.pathsep.join(
        [str(CREW_TESTS)] + [p for p in [os.environ.get("PYTHONPATH")] if p]), **extra)


# --- the isolation ------------------------------------------------------------


def test_every_home_variable_is_this_test_s_own(tmp_path_factory):
    basetemp = tmp_path_factory.getbasetemp().resolve()
    names = list(crew_fixtures.HOME_VARS) + [n for n, _ in crew_fixtures.XDG_HOME_DIRS]
    real = set(crew_fixtures.guarded_homes())

    values = {name: os.environ[name] for name in names}

    assert (bool(real), all(pathlib.Path(v).resolve().is_relative_to(basetemp)
                            for v in values.values()),
            real & {os.path.normcase(os.path.abspath(v)) for v in values.values()}) == \
        (True, True, set()), (real, values)


def test_a_spawned_interpreter_sees_the_same_home():
    names = list(crew_fixtures.HOME_VARS) + [n for n, _ in crew_fixtures.XDG_HOME_DIRS]
    code = ("import json, os, sys; json.dump({n: os.environ.get(n) for n in sys.argv[1:]}"
            " | {'~': os.path.expanduser('~')}, sys.stdout)")

    done = subprocess.run([sys.executable, "-c", code, *names], capture_output=True, text=True,
                          check=True, stdin=subprocess.DEVNULL, timeout=60)

    expected = {name: os.environ[name] for name in names} | {"~": os.environ["HOME"]}
    if os.name == "nt":
        expected["~"] = os.environ["USERPROFILE"]
    assert json.loads(done.stdout) == expected


def test_the_planted_operator_home_is_one_a_crew_script_would_read(tmp_path):
    """The control for the regression below: a crew script spawned with the
    planted home as HOME resolves its global config inside it, so the
    regression's pass is not a pass on a home nothing reads."""
    home = _operator_home(tmp_path)
    code = ("import sys; sys.path.insert(0, sys.argv[1]); import crew_state, os;"
            " print(os.path.exists(crew_state.GLOBAL_CONFIG_PATH))")

    done = subprocess.run([sys.executable, "-c", code, str(HOOK_SCRIPTS)], capture_output=True,
                          text=True, check=False, env=_inner_env(home),
                          stdin=subprocess.DEVNULL, timeout=60)

    assert (done.returncode, done.stdout.strip()) == (0, "True"), done.stderr


@pytest.mark.skipif(crew_fixtures.resolve_bash() is None,
                    reason="bash not installed - the crew-context.sh case was NOT run")
def test_user_layer_tests_pass_with_a_populated_operator_home(tmp_path):
    """L-0729 regression. On the owner's machine both tests read the real
    `~/.claude/crew/config.json` and failed. Here that file is planted, with
    the same keys, as the inner run's real home; conftest must keep them out."""
    home = _operator_home(tmp_path)

    done = _pytest(tmp_path, [str(CREW_TESTS / node) for node in USER_LAYER_TESTS],
                   _inner_env(home))

    assert (done.returncode, "3 passed" in done.stdout) == (0, True), done.stdout + done.stderr


# --- the audit: pure ----------------------------------------------------------


HOME = os.path.abspath(os.sep + os.path.join("home", "operator"))
REPO = os.path.join(HOME, "work", "repo")
# The audit compares against roots it normalised once (`set_home_guard`,
# `home_allowed_prefixes`); the pure checks take them already normalised, so
# on Windows a drive letter's case is not a difference.
HOMES = (os.path.normcase(HOME),)
ALLOWED = (os.path.normcase(REPO),)


@pytest.mark.parametrize("path", [
    os.path.join(HOME, ".claude", "crew", "config.json"),
    os.path.join(HOME, ".gitconfig"),
    os.fsencode(os.path.join(HOME, ".config", "gh", "hosts.yml")),
    pathlib.Path(HOME, ".claude"),
    HOME,
], ids=["crew-config", "gitconfig", "bytes", "pathlike", "the-home-itself"])
def test_an_open_under_the_real_home_is_a_violation(path):
    assert crew_fixtures.home_open_violation(path, HOMES, ALLOWED) is not None


@pytest.mark.parametrize("path", [
    os.path.join(REPO, "plugin", "crew", "tests", "conftest.py"),
    os.path.abspath(os.sep + os.path.join("tmp", "x")),
    HOME + "-other",
    7,
    None,
], ids=["allowed-checkout", "outside", "sibling-prefix", "fd", "none"])
def test_an_open_elsewhere_is_allowed(path):
    assert crew_fixtures.home_open_violation(path, HOMES, ALLOWED) is None


@pytest.mark.parametrize("env,blocked", [
    ({"HOME": HOME}, True),
    ({"USERPROFILE": HOME + os.sep}, True),
    ({"HOME": os.path.join(HOME, "sandbox")}, True),
    ({"HOME": os.path.join(REPO, "fixture-home")}, False),
    ({"HOME": HOME + "-other"}, False),
    ({}, False),
], ids=["home", "userprofile", "inside-the-home", "inside-an-allowed-prefix", "sibling-prefix",
        "neither"])
def test_a_spawn_is_a_violation_only_when_handed_a_real_home(env, blocked):
    assert (crew_fixtures.home_spawn_violation(env, HOMES, ALLOWED) is not None) is blocked


@pytest.mark.skipif(not hasattr(os, "symlink") or os.name == "nt",
                    reason="symlinks need privileges on Windows - the symlink case was NOT run")
def test_an_open_through_a_symlink_into_the_real_home_is_a_violation(tmp_path):
    home = tmp_path / "operator-home"
    (home / ".claude").mkdir(parents=True)
    link = tmp_path / "elsewhere"
    link.symlink_to(home)

    reason = crew_fixtures.home_open_violation(str(link / ".claude" / "config.json"),
                                               (str(home),), ())

    assert reason is not None


@pytest.mark.parametrize("prefix", [HOME, os.path.dirname(HOME)], ids=["the-home", "its-parent"])
def test_an_import_path_that_holds_the_home_is_not_allowed(monkeypatch, prefix):
    monkeypatch.setattr(sys, "path", [prefix] + sys.path)

    allowed = crew_fixtures.home_allowed_prefixes(REPO, (HOME,))

    assert crew_fixtures.home_open_violation(
        os.path.join(HOME, ".claude", "crew", "config.json"), HOMES, allowed) is not None


@pytest.mark.skipif(not hasattr(os, "posix_spawn"), reason="no os.posix_spawn here - NOT run")
def test_a_posix_spawn_handed_the_real_home_is_refused():
    real = crew_fixtures.guarded_homes()[0]
    before = len(crew_fixtures.HOME_VIOLATIONS)

    with pytest.raises(RuntimeError, match="real home"):
        os.posix_spawn(sys.executable, [sys.executable, "-c", "pass"], dict(os.environ, HOME=real))
    found = crew_fixtures.HOME_VIOLATIONS[before:]
    del crew_fixtures.HOME_VIOLATIONS[before:]

    assert len(found) == 1, found


@pytest.mark.parametrize("prefix", [
    os.path.join(HOME, ".claude"),
    os.path.join(HOME, ".claude", "crew"),
], ids=["claude-dir", "inside-it"])
def test_an_import_path_at_or_inside_the_claude_dir_is_not_allowed(monkeypatch, prefix):
    """Round 4 BLOCK: `PYTHONPATH=~/.claude` is an ordinary setup, not an
    attack, and it used to exempt the crew config the audit exists for."""
    monkeypatch.setattr(sys, "path", [prefix] + sys.path)

    allowed = crew_fixtures.home_allowed_prefixes(REPO, (HOME,))

    assert crew_fixtures.home_open_violation(
        os.path.join(HOME, ".claude", "crew", "config.json"), HOMES, allowed) is not None


def test_an_import_path_elsewhere_in_the_home_stays_allowed(monkeypatch):
    """The must-allow side: a user site-packages under the home still imports."""
    site_dir = os.path.join(HOME, ".local", "lib", "python3", "site-packages")
    monkeypatch.setattr(sys, "path", [site_dir] + sys.path)

    allowed = crew_fixtures.home_allowed_prefixes(REPO, (HOME,))

    assert crew_fixtures.home_open_violation(
        os.path.join(site_dir, "pkg", "__init__.py"), HOMES, allowed) is None


def test_a_checkout_inside_the_claude_dir_stays_allowed():
    """A plugin cache checkout lives under `~/.claude`; its own files open."""
    repo = os.path.join(HOME, ".claude", "plugins", "cache", "crew")

    allowed = crew_fixtures.home_allowed_prefixes(repo, (HOME,))

    assert crew_fixtures.home_open_violation(
        os.path.join(repo, "tests", "conftest.py"), HOMES, allowed) is None


@pytest.mark.skipif(not hasattr(os, "symlink") or os.name == "nt",
                    reason="symlinks need privileges on Windows - the symlink case was NOT run")
def test_a_file_opened_under_the_home_is_a_violation_whatever_path_was_checked(tmp_path):
    """The post-open half, pure: the descriptor names a file under the home
    although the path given looked safe when it was checked."""
    home = tmp_path / "operator-home"
    secret = home / ".claude" / "crew" / "config.json"
    secret.parent.mkdir(parents=True)
    secret.write_text("{}", encoding="utf-8")
    homes = (os.path.normcase(str(home)),)
    fd = os.open(str(secret), os.O_RDONLY)
    try:
        reason = crew_fixtures.opened_file_violation(fd, str(tmp_path / "safe"), homes, ())
    finally:
        os.close(fd)

    assert reason is not None


def test_the_wrapped_os_open_keeps_its_dir_fd_support():
    """Code under test asks `os.open in os.supports_dir_fd` before passing
    dir_fd; the post-open wrapper must not turn that answer into a no and
    send it down a path-based fallback (48 crew_tracker/review_metrics cases
    went red that way)."""
    original = crew_fixtures._OPEN_ORIGINALS["os"]  # pylint: disable=protected-access

    assert (os.open is not original, (os.open in os.supports_dir_fd)
            == (original in os.supports_dir_fd)) == (True, True)


# --- the session and module fixtures: what they are handed --------------------

_FIXTURE_LEAK_PROBE = '''
import json, os, subprocess, sys

import pytest

import crew_config
import crew_state

NAMES = (os.environ["PROBE_REAL_HOME_VAR"], "CLAUDE_CONFIG_DIR", "CLAUDE_PROJECT_DIR")
CHILD = "import json, os, sys; json.dump({n: os.environ.get(n) for n in sys.argv[1:]}, sys.stdout)"


def _seen():
    done = subprocess.run([sys.executable, "-c", CHILD, *NAMES], capture_output=True, text=True,
                          check=True, stdin=subprocess.DEVNULL, timeout=60)
    return {"child": json.loads(done.stdout),
            "config": [crew_state.GLOBAL_CONFIG_PATH, crew_config.GLOBAL_CONFIG_PATH]}


@pytest.fixture(scope="session")
def in_session():
    return _seen()


@pytest.fixture(scope="module")
def in_module():
    return _seen()


def _under_real_home(path):
    real = os.path.normcase(os.path.join(os.environ["PROBE_REAL_HOME"], ""))
    return os.path.normcase(os.path.abspath(path)).startswith(real)


def test_record(in_session, in_module):
    assert [s["child"][NAMES[0]] for s in (in_session, in_module)] == [None, None]


def test_claude_dirs(in_session, in_module):
    assert [s["child"][n] for s in (in_session, in_module) for n in NAMES[1:]] == [None] * 4


def test_config_path(in_session, in_module):
    reached = [p for s in (in_session, in_module) for p in s["config"] if _under_real_home(p)]
    assert reached == []
'''


@pytest.mark.parametrize("case", ["test_record", "test_claude_dirs", "test_config_path"],
                         ids=["real-home-record", "claude-dirs", "global-config-path"])
def test_session_and_module_fixtures_are_handed_no_real_home(tmp_path, case):
    """Round 4 FIXes: these were checked from inside a test, after the
    per-test fixture had already cleaned up, so a session or module fixture
    could leak and they still passed. Here an inner run whose real home is a
    planted one, with CLAUDE_CONFIG_DIR and CLAUDE_PROJECT_DIR set into it,
    has a session and a module fixture each spawn a child and read
    `GLOBAL_CONFIG_PATH`; the planted home is HOME, so this holds on Windows,
    where `real_homes` has no password database to fall back on."""
    home = _operator_home(tmp_path)
    probe = _probe(tmp_path, "test_fixture_leak_probe.py", _FIXTURE_LEAK_PROBE)

    done = _pytest(tmp_path, ["-p", "conftest", f"{probe}::{case}"], _conftest_env(
        home, PROBE_REAL_HOME=str(home), PROBE_REAL_HOME_VAR=crew_fixtures.REAL_HOME_VAR,
        CLAUDE_CONFIG_DIR=str(home / ".claude"), CLAUDE_PROJECT_DIR=str(home / "project")))

    assert (done.returncode, f"PASSED test_fixture_leak_probe.py::{case}" in done.stdout) == \
        (0, True), done.stdout + done.stderr


# --- the audit: end to end ----------------------------------------------------

_AUDIT_PROBE = '''
import os, subprocess, sys

import pytest

REAL = os.environ["PROBE_REAL_HOME"]


@pytest.fixture(scope="module")
def reads_in_module_setup():
    try:
        open(os.path.join(REAL, ".gitconfig"), encoding="utf-8").close()
    except Exception:  # swallowed on purpose
        pass


def test_opens_the_real_crew_config():
    try:
        open(os.path.join(REAL, ".claude", "crew", "config.json"), encoding="utf-8").close()
    except Exception:  # swallowed on purpose: the teardown must still fail it
        pass


def test_spawns_with_the_real_home():
    try:
        subprocess.run([sys.executable, "-c", "pass"], env=dict(os.environ, HOME=REAL),
                       check=False)
    except Exception:
        pass


def test_uses_a_module_fixture_that_reads_the_real_home(reads_in_module_setup):
    pass


def test_stays_in_its_own_home():
    with open(os.path.join(os.environ["HOME"], "note"), "w", encoding="utf-8") as fh:
        fh.write("x")
    subprocess.run([sys.executable, "-c", "pass"], check=True)
'''


def test_the_audit_fails_a_test_that_reaches_the_real_home(tmp_path):
    home = _operator_home(tmp_path)
    probe = _probe(tmp_path, "test_audit_probe.py", _AUDIT_PROBE)

    (home / ".gitconfig").write_text("", encoding="utf-8")

    done = _pytest(tmp_path, ["-p", "conftest", str(probe)],
                   _conftest_env(home, PROBE_REAL_HOME=str(home)))

    out = done.stdout
    config = os.path.join(str(home), ".claude", "crew", "config.json")
    assert (done.returncode,
            "ERROR test_audit_probe.py::test_opens_the_real_crew_config" in out,
            config in out,
            "ERROR test_audit_probe.py::test_spawns_with_the_real_home" in out,
            "ERROR test_audit_probe.py::test_uses_a_module_fixture_that_reads_the_real_home" in out,
            "PASSED test_audit_probe.py::test_stays_in_its_own_home" in out) == \
        (1, True, True, True, True, True), out + done.stderr


_RACE_PROBE = '''
import os, sys

import pytest

REAL = os.environ["PROBE_REAL_HOME"]
SECRET = os.path.join(REAL, ".claude", "crew", "config.json")
SWAP = {}


def _swap_after_the_check(event, args):
    """Installed after crew's audit hook, so it runs after the check and
    before the open: the link is retargeted into the real home in between."""
    if event == "open" and SWAP and os.fspath(args[0]) == SWAP["link"]:
        link = SWAP.pop("link")
        os.remove(link)
        os.symlink(SECRET, link)


sys.addaudithook(_swap_after_the_check)


@pytest.mark.parametrize("how", ["open", "os.open"])
def test_reads_through_a_swapped_link(tmp_path, how):
    safe = tmp_path / "safe.json"
    safe.write_text("{}", encoding="utf-8")
    link = tmp_path / "link.json"
    link.symlink_to(safe)
    SWAP["link"] = str(link)
    try:
        if how == "open":
            open(str(link), encoding="utf-8").close()
        else:
            os.close(os.open(str(link), os.O_RDONLY))
    except Exception:  # swallowed on purpose: the teardown must still fail it
        pass
'''


@pytest.mark.skipif(not hasattr(os, "symlink") or os.name == "nt",
                    reason="symlinks need privileges on Windows - the swap case was NOT run")
def test_a_link_swapped_into_the_home_after_the_check_is_caught(tmp_path):
    """Round 4 FIX: the audit hook checks the path before the open, so a link
    retargeted between that check and the open reached the real home. The
    probe's own audit hook swaps it in exactly that window."""
    home = _operator_home(tmp_path)
    probe = _probe(tmp_path, "test_race_probe.py", _RACE_PROBE)

    done = _pytest(tmp_path, ["-p", "conftest", str(probe)],
                   _conftest_env(home, PROBE_REAL_HOME=str(home)))

    out = done.stdout
    assert (done.returncode,
            "ERROR test_race_probe.py::test_reads_through_a_swapped_link[open]" in out,
            "ERROR test_race_probe.py::test_reads_through_a_swapped_link[os.open]" in out,
            os.path.join(str(home), ".claude", "crew", "config.json") in out) == \
        (1, True, True, True), out + done.stderr


# --- the quarantine rule ------------------------------------------------------

_QUARANTINED = '''
import pytest


@pytest.mark.quarantine(owner="someone", ticket="L-0001", reason="timing flake")
def test_flaky():
    pass


def test_steady():
    pass
'''


def test_a_quarantined_test_is_deselected_by_default(tmp_path):
    probe = _probe(tmp_path, "test_quarantined.py", _QUARANTINED)

    done = _pytest(tmp_path, ["-p", "conftest", str(probe)], _conftest_env(tmp_path / "h"))

    assert (done.returncode, "1 passed, 1 deselected" in done.stdout) == (0, True), done.stdout


def test_a_quarantined_test_runs_when_named(tmp_path):
    probe = _probe(tmp_path, "test_quarantined.py", _QUARANTINED)

    done = _pytest(tmp_path, ["-p", "conftest", "-m", "quarantine", str(probe)],
                   _conftest_env(tmp_path / "h"))

    assert (done.returncode, "PASSED test_quarantined.py::test_flaky" in done.stdout) == \
        (0, True), done.stdout


def test_a_quarantined_test_runs_when_its_node_id_is_named(tmp_path):
    probe = _probe(tmp_path, "test_quarantined.py", _QUARANTINED)

    done = _pytest(tmp_path, ["-p", "conftest", f"{probe}::test_flaky", f"{probe}::test_steady"],
                   _conftest_env(tmp_path / "h"))

    assert (done.returncode, "2 passed" in done.stdout) == (0, True), done.stdout


def test_naming_another_test_in_the_file_keeps_the_quarantine(tmp_path):
    probe = _probe(tmp_path, "test_quarantined.py", _QUARANTINED)

    done = _pytest(tmp_path, ["-p", "conftest", f"{probe}::test_steady"],
                   _conftest_env(tmp_path / "h"))

    assert (done.returncode, "PASSED test_quarantined.py::test_flaky" in done.stdout) == \
        (0, False), done.stdout


@pytest.mark.parametrize("marker,complaint", [
    ('@pytest.mark.quarantine(ticket="L-0001")', "without an owner"),
    ('@pytest.mark.quarantine(owner="someone")', "without a ticket"),
    ('@pytest.mark.quarantine(owner="someone", ticket="soon")', "without a ticket"),
    ('@pytest.mark.skip(reason="flaky on CI")', "skip with reason 'flaky on CI'"),
    ('@pytest.mark.skipif(True, reason="timing-sensitive")', "skipif with reason"),
    ('@pytest.mark.xfail(reason="intermittent")', "xfail with reason"),
    ('@pytest.mark.quarantine(owner="someone", ticket="L-0001")\n@pytest.mark.skip(reason="flaky")',
     "never also skipped"),
], ids=["no-owner", "no-ticket", "bad-ticket", "skip-flaky", "skipif-timing", "xfail-intermittent",
        "quarantined-and-skipped"])
def test_an_ownerless_quarantine_fails_collection(tmp_path, marker, complaint):
    probe = _probe(tmp_path, "test_bad.py", f"import pytest\n\n\n{marker}\ndef test_x():\n    pass\n")

    done = _pytest(tmp_path, ["-p", "conftest", str(probe)], _conftest_env(tmp_path / "h"))

    assert (done.returncode, "crew quarantine rule" in done.stderr, complaint in done.stderr) == \
        (4, True, True), done.stdout + done.stderr


@pytest.mark.parametrize("call", ["skip", "xfail"])
def test_a_run_time_flaky_skip_fails_the_test(tmp_path, call):
    probe = _probe(tmp_path, "test_rt.py",
                   f'import pytest\n\n\ndef test_x():\n    pytest.{call}("flaky under load")\n')

    done = _pytest(tmp_path, ["-p", "conftest", str(probe)], _conftest_env(tmp_path / "h"))

    assert (done.returncode, "crew quarantine rule" in done.stdout) == (1, True), done.stdout


def test_a_run_time_xfail_for_another_reason_is_not_a_quarantine(tmp_path):
    probe = _probe(tmp_path, "test_rt_ok.py",
                   'import pytest\n\n\ndef test_x():\n    pytest.xfail("known bug, L-0001")\n')

    done = _pytest(tmp_path, ["-p", "conftest", str(probe)], _conftest_env(tmp_path / "h"))

    assert (done.returncode, "1 xfailed" in done.stdout) == (0, True), done.stdout + done.stderr


def test_a_skip_for_another_reason_is_not_a_quarantine(tmp_path):
    probe = _probe(tmp_path, "test_ok.py",
                   'import pytest\n\n\n@pytest.mark.skip(reason="pwsh not installed")\n'
                   "def test_x():\n    pass\n")

    done = _pytest(tmp_path, ["-p", "conftest", str(probe)], _conftest_env(tmp_path / "h"))

    assert (done.returncode, "1 skipped" in done.stdout) == (0, True), done.stdout + done.stderr


def test_a_test_that_undoes_its_monkeypatch_keeps_the_isolation(monkeypatch):
    """`monkeypatch.undo()` drops the test's own patches only: conftest's
    isolation is written through a MonkeyPatch of its own."""
    import crew_config  # pylint: disable=import-outside-toplevel
    home = os.environ["HOME"]
    monkeypatch.setenv("CREW_UNDO_PROBE", "1")

    monkeypatch.undo()

    assert (os.environ["HOME"], "CREW_UNDO_PROBE" in os.environ,
            os.path.exists(crew_config.GLOBAL_CONFIG_PATH),
            crew_fixtures.guarded_homes() != ()) == (home, False, False, True)

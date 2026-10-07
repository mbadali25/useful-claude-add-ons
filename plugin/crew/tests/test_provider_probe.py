"""`provider_probe.py`: one real provider call, from the repo root, with
review's own command line (T-0065, item 10).

A lane that improvised `codex exec` from a `/tmp` export got "Not inside a
trusted directory". The stub `codex` here fails exactly that way unless it
gets `--skip-git-repo-check`, `-C <root>` AND runs with `<root>` as its cwd,
and the probe is run from an unrelated directory.
"""
import os
import subprocess
import sys

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import review_run
from crew_fixtures import write_shim

SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir, "hooks", "scripts",
                      "provider_probe.py")
TRUST = "Not inside a trusted directory and --skip-git-repo-check was not specified."
OK_EVENTS = ('{"type":"item.completed","item":{"type":"agent_message","text":"OK"}}\n'
             '{"type":"turn.completed"}\n')
# The stub is Python behind a sh wrapper (POSIX) and a `.cmd` (Windows, the
# form `shutil.which` finds there), so the same checks run on both: a `.cmd`
# that only exits 0 printed nothing and read as "no completed turn".
STUB = """import os, sys, time
ROOT, BODY, SLEEP, TRUST = {root!r}, {body!r}, {sleep!r}, {trust!r}


def same(path):
    return os.path.normcase(os.path.realpath(path)) == os.path.normcase(os.path.realpath(ROOT))


args = sys.argv[1:]
flag = "--skip-git-repo-check" in args
dash_c = any(a == "-C" and same(b) for a, b in zip(args, args[1:]))
if not (flag and dash_c and same(os.getcwd())):
    sys.stderr.write(TRUST + "\\nsecond line\\n")
    sys.exit(1)
sys.stdout.write(BODY)
sys.stdout.flush()
time.sleep(SLEEP)
"""


def _stub(bindir, root, body=OK_EVENTS, sleep=0):
    os.makedirs(bindir, exist_ok=True)
    script = os.path.join(bindir, "codex_stub.py")
    with open(script, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(STUB.format(root=root, body=body, sleep=sleep, trust=TRUST))
    write_shim(bindir, "codex", f'#!/bin/sh\nexec "{sys.executable}" "{script}" "$@"\n',
               cmd_body=f'@"{sys.executable}" "{script}" %*\r\n@exit /b %ERRORLEVEL%\r\n')


@pytest.fixture(name="layout")
def _layout(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    return os.path.realpath(str(root)), str(elsewhere), str(tmp_path / "fakebin")


def _probe(cwd, bindir, *args):
    env = dict(os.environ, PATH=os.pathsep.join([bindir, "/usr/bin", "/bin"]))
    return subprocess.run([sys.executable, SCRIPT, *args], cwd=cwd, env=env,
                          capture_output=True, text=True, timeout=60, check=False)


def test_codex_probe_runs_from_the_repo_root(layout):
    root, elsewhere, bindir = layout
    _stub(bindir, root)

    done = _probe(elsewhere, bindir, "codex", "--root", root)

    assert done.returncode == 0, done.stdout + done.stderr
    assert done.stdout.startswith("codex: ok")


def test_codex_probe_takes_a_relative_root_absolute(layout):
    root, _, bindir = layout
    _stub(bindir, root)

    done = _probe(os.path.dirname(root), bindir, "codex", "--root", os.path.basename(root))

    assert done.returncode == 0, done.stdout + done.stderr


def test_codex_probe_reports_a_failed_call(layout):
    root, elsewhere, bindir = layout
    _stub(bindir, "/nowhere/at/all")

    done = _probe(elsewhere, bindir, "codex", "--root", root)

    assert done.returncode == 1
    assert done.stdout.strip() == f"codex: FAILED - {TRUST}"


def test_codex_probe_reports_an_incomplete_stream(layout):
    root, elsewhere, bindir = layout
    _stub(bindir, root, body=OK_EVENTS.splitlines(keepends=True)[0])

    done = _probe(elsewhere, bindir, "codex", "--root", root)

    assert done.returncode == 1
    assert "the Codex event stream has no completed turn" in done.stdout


def test_codex_probe_reports_a_non_string_message_as_failed(layout):
    root, elsewhere, bindir = layout
    _stub(bindir, root, body=OK_EVENTS.replace('"text":"OK"', '"text":{}'))

    done = _probe(elsewhere, bindir, "codex", "--root", root)

    assert (done.returncode, done.stdout.startswith("codex: FAILED")) == (1, True), done.stdout + done.stderr


def test_codex_probe_reports_a_timeout(layout):
    root, elsewhere, bindir = layout
    _stub(bindir, root, body="", sleep=30)

    done = _probe(elsewhere, bindir, "codex", "--root", root, "--timeout", "1")

    assert done.returncode == 1
    assert done.stdout.strip() == "codex: FAILED - timed out"


def test_probe_not_installed(layout):
    root, elsewhere, bindir = layout
    os.makedirs(bindir)

    env = dict(os.environ, PATH=bindir)
    done = subprocess.run([sys.executable, SCRIPT, "codex", "--root", root], cwd=elsewhere,
                          env=env, capture_output=True, text=True, timeout=60, check=False)

    assert done.returncode == 2
    assert done.stdout.strip() == "codex: not installed"


def test_copilot_probe_needs_a_model(layout):
    root, elsewhere, bindir = layout
    write_shim(bindir, "copilot")

    done = _probe(elsewhere, bindir, "copilot", "--root", root)

    assert done.returncode == 2
    assert "--model" in done.stdout + done.stderr


def test_review_command_keeps_the_trust_flags():
    cmd = review_run.command_for("codex", "codex", "/r", "p", "", "")

    assert "--skip-git-repo-check" in cmd
    assert cmd[cmd.index("-C"):cmd.index("-C") + 2] == ["-C", "/r"]

"""L-0868: a `.sh` hook that hands a script path to python must hand one that
NATIVE python.exe can open.

The defect (win-repo-2, 2026-10-22): Git Bash converts a POSIX argument
(`/d/repo/x.py`, `/tmp/...`) to a Windows path when it execs a native program,
but only while `MSYS_NO_PATHCONV` is unset. Set -- even to the empty string --
the argument reaches python.exe unconverted and Windows resolves `/tmp/...`
against the current drive: `can't open file 'D:\\tmp\\...'`. The fix is the
`crew_native_path` helper in `_common.sh` (`cygpath -m`, which does not depend
on argument conversion), wrapped around every non-harness `"$DIR/x.py"` caller.

This runs on Linux with a Windows-like fixture: an exported `OSTYPE=msys`
(crew 1.2.115 reads bash's `$OSTYPE` instead of forking `uname -s`, and bash
keeps an inherited value), a `cygpath` that maps `/p` to `D:/winfx/p`, and a `python3` that
refuses any `.py` argument still shaped like a POSIX path (what python.exe does
with an unconverted one) and maps `D:/winfx/p` back so the real script runs.
The stubs are found through PATH, never named in a case. The native-Windows
variant is requested of win-repo-2 separately and is NOT run here.
"""
import os
import pathlib
import re
import subprocess
import sys

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import crew_fixtures
from review_fixtures import init_repo

SCRIPTS = pathlib.Path(os.path.realpath(pathlib.Path(__file__).resolve().parent.parent / "hooks" / "scripts"))
BASH = crew_fixtures.resolve_bash()
needs_bash = pytest.mark.skipif(BASH is None, reason="bash not installed - the sh flavour was NOT run")
needs_linux_fixture = pytest.mark.skipif(
    os.name == "nt", reason="Linux-fixture test, skipped on nt: win-repo-2 runs the native variant there")
DRIVE = "D:/winfx"
PATHCONV = [pytest.param(None, id="unset"), pytest.param("", id="empty"), pytest.param("1", id="one")]

_PY_STUB = """#!/bin/bash
REAL=%(real)r
case "$*" in *"print(sys.executable)"*) echo "$0"; exit 0 ;; esac
args=()
for a in "$@"; do
  case "$a" in
    /dev/*) ;;
    /*) printf 'REJECT\\t%%s\\n' "$a" >> "$CREW_TEST_PY_LOG"
        echo "can't open file '$a': [Errno 2] No such file or directory" >&2; exit 2 ;;
    %(drive)s/*)
      case "$a" in *.py) kind=SCRIPT ;; *) kind=ARG ;; esac
      printf '%%s\\t%%s\\n' "$kind" "$a" >> "$CREW_TEST_PY_LOG"; a="${a#%(drive)s}" ;;
  esac
  args+=("$a")
done
exec "$REAL" "${args[@]}"
"""
_CYGPATH_STUB = """#!/bin/bash
while [ "${1#-}" != "$1" ]; do mode=$1; shift; done
case "$mode" in
  -u) printf '%%s\\n' "${1#%(drive)s}" ;;
  *) printf '%%s\\n' "%(drive)s$1" ;;
esac
"""
def _stubs(tmp_path, *, cygpath=True):
    bindir = tmp_path / "bin"
    bindir.mkdir()
    files = {"python3": _PY_STUB % {"real": os.path.realpath(sys.executable), "drive": DRIVE}}
    if cygpath:
        files["cygpath"] = _CYGPATH_STUB % {"drive": DRIVE}
    for name, body in files.items():
        (bindir / name).write_text(body, encoding="utf-8", newline="\n")
        (bindir / name).chmod(0o755)
    return bindir


class Run:
    def __init__(self, tmp_path, pathconv, ostype="msys", **stub_kw):
        self.root = pathlib.Path(init_repo(tmp_path / "repo"))
        (self.root / ".crew").mkdir(exist_ok=True)
        (self.root / ".crew" / "config.json").write_text('{"memory": {"inject": false}}', encoding="utf-8")
        self.log = tmp_path / "py.log"
        env = crew_fixtures.isolated_home_env(tmp_path / "home")
        env["PATH"] = str(_stubs(tmp_path, **stub_kw)) + os.pathsep + env["PATH"]
        env["OSTYPE"] = ostype
        env["CREW_TEST_PY_LOG"] = str(self.log)
        env["CLAUDE_PROJECT_DIR"] = str(self.root)
        env.pop("MSYS_NO_PATHCONV", None)
        if pathconv is not None:
            env["MSYS_NO_PATHCONV"] = pathconv
        self.env = env
        self.args = []

    def run(self, script, args=(), stdin=""):
        done = subprocess.run([BASH, str(SCRIPTS / script), *args], input=stdin, text=True, encoding="utf-8",
                              cwd=self.root, env=self.env, capture_output=True, timeout=120, check=False)
        lines = self.log.read_text(encoding="utf-8").splitlines() if self.log.exists() else []
        seen = [ln.split("\t", 1) for ln in lines]
        self.args = [p for k, p in seen if k == "ARG"]
        return done, [p for k, p in seen if k == "SCRIPT"], [p for k, p in seen if k == "REJECT"]


_PRETOOL = '{"hook_event_name":"PreToolUse","tool_name":"Bash","tool_input":{"command":"ls"},"session_id":"s1"}'
_WRITE = '{"hook_event_name":"PreToolUse","tool_name":"Write","tool_input":{"file_path":"x.txt"},"session_id":"s1"}'
_PRECOMPACT = '{"hook_event_name":"PreCompact","trigger":"manual","session_id":"s1"}'
_NOTIFY = ('{"session_id":"s1","hook_event_name":"Notification","message":"waiting",'
           '"notification_type":"permission_prompt","prompt_id":"p-1"}')
_CLEAR = '{"hook_event_name":"SessionStart","source":"clear","session_id":"s1"}'

# id -> (script, args, stdin, the scripts that must reach python, converted)
CALLERS = {
    "auto-clear-plan": ("auto-clear.sh", ["--session", "s1"], "", ["crew_autocycle.py"]),
    "auto-clear-resume-plan": ("auto-clear.sh", ["--resume", "--session", "s1", "--source", "compact"], "",
                               ["crew_autocycle.py"]),
    "handoff-write-claim": ("handoff-write.sh", [], _PRECOMPACT, ["event_claim.py"]),
    "notify-claim": ("notify.sh", ["hook"], _NOTIFY, ["event_claim.py", "crew_notify.py"]),
    "notify-by-hand": ("notify.sh", ["gate", "why"], "", ["crew_notify.py"]),
    "crew-context": ("crew-context.sh", [], _CLEAR, ["crew_context.py"]),
    "platform-sync": ("platform-sync.sh", [], "", ["crew_platform.py"]),
    "cloud-guard": ("cloud-guard.sh", [], _PRETOOL, ["cloud_guard.py"]),
    "env-guard": ("env-guard.sh", [], _PRETOOL, ["env_guard.py"]),
    "role-write-guard": ("role-write-guard.sh", [], _WRITE, ["role_write_guard.py"]),
}


@needs_bash
@needs_linux_fixture
@pytest.mark.parametrize("pathconv", PATHCONV)
@pytest.mark.parametrize("case", sorted(CALLERS))
def test_caller_hands_python_a_native_script_path(tmp_path, case, pathconv):
    script, args, stdin, expected = CALLERS[case]
    run = Run(tmp_path, pathconv)

    done, scripts, rejected = run.run(script, args, stdin)
    rejected = [path for path in rejected if (script, os.path.basename(path)) not in _DEFERRED]

    assert rejected == [], f"python was handed a POSIX script path: {rejected}\n{done.stderr}"
    for name in expected:
        assert f"{DRIVE}{SCRIPTS}/{name}" in scripts, f"{name} never reached python converted: {scripts}\n{done.stderr}"


# id -> (script, args, stdin, the path arguments that must reach python converted)
# L-0725: handoff-read.sh no longer calls python (the handoff is injected by crew-context.sh), and
# handoff-write.sh no longer reads a handoff path from config, so neither has a data-path case left.
PATH_ARGS = {
    "auto-clear-plan-root": ("auto-clear.sh", ["--session", "s1"], "", "root"),
    "auto-clear-resume-plan-root": ("auto-clear.sh", ["--resume", "--session", "s1", "--source", "compact"], "",
                                    "root"),
}


@needs_bash
@needs_linux_fixture
@pytest.mark.parametrize("pathconv", PATHCONV)
@pytest.mark.parametrize("case", sorted(PATH_ARGS))
def test_caller_hands_python_native_path_arguments(tmp_path, case, pathconv):
    script, args, stdin, want = PATH_ARGS[case]
    run = Run(tmp_path, pathconv)

    done, _, rejected = run.run(script, args, stdin)
    rejected = [path for path in rejected if (script, os.path.basename(path)) not in _DEFERRED]
    expected = f"{DRIVE}{run.root}" if want == "root" else f"{DRIVE}{SCRIPTS}"

    assert rejected == [], f"python was handed a POSIX path argument: {rejected}\n{done.stderr}"
    assert expected in run.args, f"{expected} never reached python as an argument: {run.args}\n{done.stderr}"


@needs_bash
@needs_linux_fixture
def test_helper_without_cygpath_hands_the_input_path_unchanged(tmp_path):
    run = Run(tmp_path, "", cygpath=False)

    _, scripts, rejected = run.run("crew-context.sh", [], _CLEAR)

    assert scripts == []
    assert rejected == [f"{SCRIPTS}/crew_context.py"]


@needs_bash
@needs_linux_fixture
def test_helper_on_a_posix_host_hands_the_input_path_unchanged(tmp_path):
    run = Run(tmp_path, "", ostype="linux-gnu")

    _, scripts, rejected = run.run("crew-context.sh", [], _CLEAR)

    assert scripts == []
    assert rejected == [f"{SCRIPTS}/crew_context.py"]


@needs_bash
@needs_linux_fixture
@pytest.mark.parametrize("given", ["/d/x/y.py", "/tmp/a b/y.py", "rel/y.py"])
def test_helper_is_identity_off_windows(tmp_path, given):
    script = f'. "{SCRIPTS}/_common.sh"; crew_native_path "$1"'

    done = subprocess.run([BASH, "-c", script, "_", given], capture_output=True, text=True, encoding="utf-8",
                          check=False)

    assert (done.returncode, done.stdout) == (0, given)


@needs_bash
@needs_linux_fixture
def test_helper_falls_back_to_the_input_when_cygpath_fails(tmp_path):
    bindir = _stubs(tmp_path, cygpath=False)
    (bindir / "cygpath").write_text("#!/bin/bash\nexit 1\n", encoding="utf-8", newline="\n")
    (bindir / "cygpath").chmod(0o755)
    env = dict(os.environ, PATH=str(bindir) + os.pathsep + os.environ["PATH"], OSTYPE="msys")
    script = f'. "{SCRIPTS}/_common.sh"; crew_native_path "$1"'

    done = subprocess.run([BASH, "-c", script, "_", "/d/x/y.py"], capture_output=True, text=True,
                          encoding="utf-8", env=env, check=False)

    assert (done.returncode, done.stdout) == (0, "/d/x/y.py")


@needs_bash
@needs_linux_fixture
@pytest.mark.parametrize("ostype", ["msys", "cygwin"])
@pytest.mark.parametrize("given,want", [
    ("D:/x/y.py", "D:/x/y.py"),          # mixed: printed as it is, cygpath never asked
    ("/d/x/y.py", f"{DRIVE}/d/x/y.py"),   # every other shape still goes through cygpath
], ids=["mixed", "posix"])
def test_helper_skips_cygpath_only_for_a_mixed_path(tmp_path, ostype, given, want):
    """crew_hook.py starts every .sh by its `D:/...` path, so a guard's `$DIR`
    is already mixed; asking cygpath for it was an MSYS process start per call."""
    bindir = _stubs(tmp_path)
    env = dict(os.environ, PATH=str(bindir) + os.pathsep + os.environ["PATH"], OSTYPE=ostype)
    script = f'. "{SCRIPTS}/_common.sh"; crew_native_path "$1"; crew_py_script "{SCRIPTS}/_common.sh" V; printf "|%s" "${{V:+set}}"'

    done = subprocess.run([BASH, "-c", script, "_", given], capture_output=True, text=True,
                          encoding="utf-8", env=env, check=False)

    assert (done.returncode, done.stdout) == (0, want + "|set")


@needs_bash
def test_bash_keeps_an_inherited_ostype():
    """The fixture above fakes Windows by exporting OSTYPE; that only works
    because bash sets OSTYPE only when it is not already set."""
    env = dict(os.environ, OSTYPE="crew-fixture-os")
    done = subprocess.run([BASH, "-c", 'printf %s "$OSTYPE"'], capture_output=True, text=True,
                          env=env, check=False)
    assert done.stdout == "crew-fixture-os"


# Callers a fixture cannot drive cheaply (context-watch needs a live transcript,
# promote-gate a declared deploy) are held to the same rule by reading the
# source: no interpreter call may take a `$DIR`-derived script path unwrapped.
_NON_HARNESS = ["auto-clear.sh", "handoff-write.sh", "notify.sh", "context-watch.sh", "handoff-read.sh",
                "crew-context.sh", "platform-sync.sh", "cloud-guard.sh", "env-guard.sh", "role-write-guard.sh",
                "promote-gate.sh"]
_SCRIPT_PATH = re.compile(r'(\$DIR|\$\(dirname [^)]*\))/\w+\.py')
# handoff-write.sh's `crew_resume.py precompact` call is the one deliberate gap:
# tests/sabotage_resume.py (a HARNESS path, T-0087) anchors on that line's exact
# text, so wrapping it belongs to the separate tooling PR that moves the anchor.
_DEFERRED = {("handoff-write.sh", "crew_resume.py")}



# `crew_py_script` wraps `crew_native_path` and refuses an empty or missing
# script (crew 1.2.109), so it is as good as the bare helper at a call site.
_ALLOWED_HELPERS = ('crew_native_path "', 'crew_py_script "')


def _unwrapped_script_paths(name, line):
    """The `$DIR`-derived script paths on `line` that no allowed helper wraps."""
    if line.lstrip().startswith("#"):
        return []
    return [found.group(0) for found in _SCRIPT_PATH.finditer(line)
            if not any(found.group(0).endswith("/" + script) and name == hook for hook, script in _DEFERRED)
            and not line[:found.start()].endswith(_ALLOWED_HELPERS)]


@pytest.mark.parametrize("name", _NON_HARNESS)
def test_every_script_path_in_a_non_harness_hook_goes_through_the_helper(name):
    offenders = []
    for number, line in enumerate((SCRIPTS / name).read_text(encoding="utf-8").splitlines(), 1):
        if _unwrapped_script_paths(name, line):
            offenders.append(f"{name}:{number}: {line.strip()}")

    assert offenders == []


@pytest.mark.parametrize("line", [
    'GUARD_PY=$(crew_py_script "$DIR/cloud_guard.py") || exit 2',
    'X=$(crew_py_script "$(dirname "${BASH_SOURCE[0]}")/_promote_tree.py")',
    '"$PY" "$(crew_native_path "$DIR/x.py")"',
], ids=["py-script-dir", "py-script-dirname", "native-path"])
def test_an_allowed_helper_wrapping_a_script_path_is_not_flagged(line):
    assert _unwrapped_script_paths("cloud-guard.sh", line) == []


@pytest.mark.parametrize("line", [
    '"$PY" "$DIR/cloud_guard.py"',
    'GUARD_PY="$DIR/cloud_guard.py"',
    '"$PY" "$(dirname "${BASH_SOURCE[0]}")/_promote_tree.py"',
    'GUARD_PY=$(crew_py_script_not "$DIR/cloud_guard.py")',
], ids=["bare-dir", "assigned-bare", "bare-dirname", "lookalike-helper"])
def test_a_bare_script_path_is_still_flagged(line):
    assert _unwrapped_script_paths("cloud-guard.sh", line) != []


@pytest.mark.parametrize("name", _NON_HARNESS)
def test_every_root_and_data_path_argument_goes_through_the_helper(name):
    unwrapped = re.compile(
        r'--root "\$PWD"|"\$PY" - "\$CREW_CFG"|"\$DIR" "\$PWD"'
        r'|json\.load\(open\(sys\.argv\[1\]\)\).*\' "\$CREW_CFG" 2>')
    offenders = []
    for number, line in enumerate((SCRIPTS / name).read_text(encoding="utf-8").splitlines(), 1):
        if line.lstrip().startswith("#"):
            continue
        if unwrapped.search(line) and 'bash "$(dirname' not in line:
            offenders.append(f"{name}:{number}: {line.strip()}")

    assert offenders == []


def test_the_deferred_caller_is_still_the_unwrapped_line():
    source = (SCRIPTS / "handoff-write.sh").read_text(encoding="utf-8")

    assert '"$CLAIM_PY" "$(dirname "${BASH_SOURCE[0]}")/crew_resume.py" precompact' in source, (
        "handoff-write.sh now wraps crew_resume.py: delete _DEFERRED and the filter in the two tests above")

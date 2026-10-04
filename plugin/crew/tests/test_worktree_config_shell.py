"""The shell and PowerShell config readers inherit the main checkout's repo
config in a linked worktree, by the same rules as the Python resolver (T-0096).

T-0088 routed every Python reader of `.crew/config.json` through
`crew_common.repo_config_dir`; the shell and PowerShell readers kept reading
the worktree's own file, which a lane never has (`.crew/*` is gitignored). In
the guards' no-python fallbacks "absent" is the proof of off, so a lane whose
main checkout armed the cloud guard let a command through unjudged. This file
holds the two shell resolvers to the Python one case by case, and the readers
this slice routes (`_common.sh`'s incident stand-down, both cloud-guard
fallbacks, promote-gate.ps1's stand-down, auto-clear.ps1's repo veto) to the
inherited layer, with must-block and must-allow cases. L-0680 adds the session
hooks (notify, handoff-read, handoff-write, context-watch, both flavours): they
read the resolved file, and everything they write stays in the lane.

Every case builds throwaway repositories under tmp_path; nothing reads the real
repository's config. bash cases skip where bash is absent, PowerShell cases
where pwsh is absent: written and skipped, not passed.
"""
import json
import os
import pathlib
import shutil
import subprocess
import time

import pytest

# isort: split
import context  # noqa: F401  pylint: disable=unused-import
import crew_common
import crew_fixtures
from review_fixtures import git, init_repo
from scope_fixtures import make_repo

SCRIPTS = os.path.join(context._ROOT, "hooks", "scripts")  # pylint: disable=protected-access
COMMON_SH = os.path.join(SCRIPTS, "_common.sh")

_BASH = crew_fixtures.resolve_bash()
_PWSH = crew_fixtures.resolve_pwsh()
needs_bash = pytest.mark.skipif(_BASH is None, reason="no MSYS/POSIX bash")
needs_pwsh = pytest.mark.skipif(
    _PWSH is None, reason="pwsh is not installed here; the .ps1 cases are written and skipped")

PS_COPIES = ("cloud-guard", "promote-gate", "auto-clear",
             "notify", "handoff-read", "handoff-write", "context-watch")  # L-0680: the last four
SHELL_SOURCE = {crew_common.SOURCE_OWN: "own", crew_common.SOURCE_MAIN: "main",
                crew_common.SOURCE_UNKNOWN: "unknown"}
NO_PYTHON = {"PYTHONHOME": "/nonexistent-python-home"}


def _lane(tmp_path, main_cfg, lane_name="wt"):
    """A main checkout whose `.crew/config.json` is `main_cfg` (none when None)
    and a linked worktree of it with no crew config."""
    main = make_repo(tmp_path, mode=None, name="main")
    if main_cfg is not None:
        (main / ".crew" / "config.json").write_text(json.dumps(main_cfg), encoding="utf-8")
    git(main, "worktree", "add", "-q", "-b", "lane", str(tmp_path / lane_name))
    return main, tmp_path / lane_name


def _own(root, name, data):
    (root / ".crew").mkdir(exist_ok=True)
    (root / ".crew" / name).write_text(json.dumps(data), encoding="utf-8")


# --- the resolver matrix -----------------------------------------------------------------

def _case_main_checkout(tmp_path):
    main, _wt = _lane(tmp_path, {"scope": {"mode": "block"}})
    return main


def _case_lane_no_config(tmp_path):
    return _lane(tmp_path, {"scope": {"mode": "block"}})[1]


def _case_lane_own_config(tmp_path):
    wt = _lane(tmp_path, {"scope": {"mode": "block"}})[1]
    _own(wt, "config.json", {})
    return wt


def _case_lane_own_crew_json_only(tmp_path):
    wt = _lane(tmp_path, {"scope": {"mode": "block"}})[1]
    _own(wt, "crew.json", {})
    return wt


def _case_lane_own_dangling_link(tmp_path):
    """A dangling link counts as an own file: Python tests it with `lexists`."""
    wt = _lane(tmp_path, {"scope": {"mode": "block"}})[1]
    (wt / ".crew").mkdir()
    try:
        os.symlink(tmp_path / "nowhere.json", wt / ".crew" / "config.json")
    except (OSError, NotImplementedError):
        pytest.skip("this machine cannot make a symlink")
    return wt


def _case_lane_main_has_no_config(tmp_path):
    return _lane(tmp_path, None)[1]


def _case_submodule(tmp_path):
    other = init_repo(tmp_path / "other")
    main = make_repo(tmp_path, mode="block", name="main")
    git(main, "-c", "protocol.file.allow=always", "submodule", "add", "-q", str(other), "sub")
    return main / "sub"


def _case_bare_worktree(tmp_path):
    seed = init_repo(tmp_path / "seed")
    bare = tmp_path / "repo.git"
    git(tmp_path, "clone", "-q", "--bare", str(seed), str(bare))
    (bare / ".crew").mkdir()  # a bare repository has no checkout to inherit from
    (bare / ".crew" / "config.json").write_text("{}", encoding="utf-8")
    git(bare, "worktree", "add", "-q", str(tmp_path / "wt"))
    return tmp_path / "wt"


def _case_git_file_naming_a_missing_dir(tmp_path):
    root = tmp_path / "broken"
    root.mkdir()
    (root / ".git").write_text("gitdir: " + str(tmp_path / "nowhere") + "\n", encoding="utf-8")
    return root


def _case_lane_with_a_space(tmp_path):
    return _lane(tmp_path, {"scope": {"mode": "block"}}, lane_name="a lane")[1]


CASES = {
    "main-checkout": _case_main_checkout,
    "lane-no-config": _case_lane_no_config,
    "lane-own-config": _case_lane_own_config,
    "lane-own-crew-json-only": _case_lane_own_crew_json_only,
    "lane-own-dangling-link": _case_lane_own_dangling_link,
    "lane-main-has-no-config": _case_lane_main_has_no_config,
    "submodule": _case_submodule,
    "bare-worktree": _case_bare_worktree,
    "git-file-missing-dir": _case_git_file_naming_a_missing_dir,
    "lane-with-space": _case_lane_with_a_space,
}
EXPECTED = {"main-checkout": "own", "lane-no-config": "main", "lane-own-config": "own",
            "lane-own-crew-json-only": "own", "lane-own-dangling-link": "own",
            "lane-main-has-no-config": "own",
            "submodule": "own", "bare-worktree": "own", "git-file-missing-dir": "unknown",
            "lane-with-space": "main"}


def _posix(path):
    return str(path).replace("\\", "/")


def bash_resolve(root):
    """(source, dir) from `_common.sh`'s `crew_repo_config_dir`."""
    snippet = ('. "$1" || exit 99; crew_repo_config_dir "$2"; d=$CREW_CFG_DIR; '
               'if command -v cygpath >/dev/null 2>&1; then d=$(cygpath -w "$d"); fi; '
               'printf "%s\\n%s\\n" "$CREW_CFG_SOURCE" "$d"')
    proc = subprocess.run([_BASH, "-c", snippet, "_", _posix(COMMON_SH), _posix(root)],
                          capture_output=True, text=True, check=False, timeout=60,
                          stdin=subprocess.DEVNULL)
    assert proc.returncode == 0, proc.stderr
    source, directory = proc.stdout.splitlines()
    return source, directory


def ps_function(stem, name="Get-CrewRepoConfigDir"):
    src = pathlib.Path(SCRIPTS, stem + ".ps1").read_text(encoding="utf-8")
    start = src.index(f"function {name}(")
    return src[start:src.index("\n}\n", start) + 3]


def pwsh_resolve(tmp_path, root):
    """(source, dir) from cloud-guard.ps1's copy of `Get-CrewRepoConfigDir`."""
    script = tmp_path / "resolve.ps1"
    script.write_text(ps_function("cloud-guard") +
                      "$r = Get-CrewRepoConfigDir $args[0]\n"
                      "Write-Output $r.Source\nWrite-Output $r.Dir\n", encoding="utf-8")
    proc = subprocess.run([_PWSH, "-NoProfile", "-NonInteractive", "-File", str(script),
                           str(root)], capture_output=True, text=True, check=False,
                          timeout=120, stdin=subprocess.DEVNULL)
    assert proc.returncode == 0, proc.stderr
    source, directory = proc.stdout.splitlines()[-2:]
    return source, directory


def _python(root):
    directory, source, _detail = crew_common.repo_config_dir(str(root))
    return SHELL_SOURCE[source], os.path.realpath(directory)


@needs_bash
@pytest.mark.parametrize("case", list(CASES))
def test_bash_resolver_agrees_with_python(tmp_path, case):
    root = CASES[case](tmp_path)
    source, directory = bash_resolve(root)

    assert _python(root)[0] == EXPECTED[case]
    assert (source, os.path.realpath(directory)) == _python(root)


@needs_pwsh
@pytest.mark.parametrize("case", list(CASES))
def test_powershell_resolver_agrees_with_python(tmp_path, case):
    root = CASES[case](tmp_path)
    source, directory = pwsh_resolve(tmp_path, root)

    assert (source, os.path.realpath(directory)) == _python(root)


@needs_pwsh
@pytest.mark.skipif(not hasattr(os, "symlink") or os.name == "nt",
                    reason="needs unprivileged symlinks")
def test_powershell_resolver_never_reads_main_through_a_symlinked_common_dir(tmp_path):
    """Windows PowerShell 5.1 cannot resolve a symlink the way realpath does,
    so a link in a path the resolver compares reads `unknown`, never `main`:
    here the common directory is a link named `.git` to a bare repository,
    which Python resolves to `own`."""
    wt = _case_bare_worktree(tmp_path)
    holder = tmp_path / "holder"
    holder.mkdir()
    os.symlink(tmp_path / "repo.git", holder / ".git")
    (holder / ".crew").mkdir()
    (holder / ".crew" / "config.json").write_text("{}", encoding="utf-8")
    (wt / ".git").write_text("gitdir: " + str(holder / ".git" / "worktrees" / "wt") + "\n",
                             encoding="utf-8")

    assert pwsh_resolve(tmp_path, wt)[0] in ("unknown", _python(wt)[0])
    assert pwsh_resolve(tmp_path, wt)[0] != "main"


@needs_pwsh
def test_powershell_resolver_reads_a_non_ascii_lane_path_whatever_the_console_encoding(tmp_path):
    """git prints paths as UTF-8; PowerShell decodes a native command's output
    with [Console]::OutputEncoding, the OEM code page on Windows. Under a
    Latin-1 console a lane below `José` read `unknown` until the resolver
    pinned UTF-8 around its git call."""
    base = tmp_path / "Jos\u00e9"
    base.mkdir()
    _main, wt = _lane(base, {"scope": {"mode": "block"}})
    script = tmp_path / "resolve_latin1.ps1"
    script.write_text("[Console]::OutputEncoding = [System.Text.Encoding]::GetEncoding(28591)\n" +
                      ps_function("cloud-guard") +
                      "$before = [Console]::OutputEncoding.CodePage\n"
                      "$r = Get-CrewRepoConfigDir $args[0]\n"
                      "Write-Output $r.Source\n"
                      "Write-Output ($before -eq [Console]::OutputEncoding.CodePage)\n",
                      encoding="utf-8-sig")
    proc = subprocess.run([_PWSH, "-NoProfile", "-NonInteractive", "-File", str(script), str(wt)],
                          capture_output=True, text=True, check=False, timeout=120,
                          stdin=subprocess.DEVNULL)
    assert proc.returncode == 0, proc.stderr
    source, restored = proc.stdout.splitlines()[-2:]
    assert (source, restored) == ("main", "True"), proc.stderr


def test_powershell_resolver_copies_are_identical():
    first = ps_function(PS_COPIES[0])
    for stem in PS_COPIES[1:]:
        assert ps_function(stem) == first, f"{stem}.ps1's Get-CrewRepoConfigDir differs"


@needs_bash
def test_bash_config_file_helper_prints_the_resolved_path(tmp_path):
    _main, wt = _lane(tmp_path, {"scope": {"mode": "block"}})
    proc = subprocess.run(
        [_BASH, "-c", '. "$1"; crew_repo_config_file crew.json "$2"', "_",
         _posix(COMMON_SH), _posix(wt)],
        capture_output=True, text=True, check=False, timeout=60, stdin=subprocess.DEVNULL)
    out = proc.stdout.strip()
    if shutil.which("cygpath"):
        out = subprocess.run(["cygpath", "-w", out], capture_output=True, text=True,
                             check=False).stdout.strip()
    assert os.path.realpath(out) == os.path.realpath(tmp_path / "main" / ".crew" / "crew.json")


# --- the cloud guard's no-python fallback ------------------------------------------------

def _guard_env(tmp_path, root, driver):
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(("AWS_", "AZURE_", "ARM_"))
           and k not in ("CI", "CREW_UNATTENDED", "CLAUDE_PROJECT_DIR", "OS",
                         "CREW_CLOUD_GUARD_FLAVOUR")}
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    env.update({"HOME": str(home), "USERPROFILE": str(home), "CLAUDE_PROJECT_DIR": str(root),
                "PYTHONDONTWRITEBYTECODE": "1"}, **NO_PYTHON)
    if driver == "ps1":
        env["OS"] = "Windows_NT"
    return env


def _run_guard(tmp_path, root, driver):
    argv = ([_BASH, os.path.join(SCRIPTS, "cloud-guard.sh")] if driver == "sh" else
            [_PWSH, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
             os.path.join(SCRIPTS, "cloud-guard.ps1")])
    return subprocess.run(argv, input=b'{"tool_name":"Bash","tool_input":'
                                      b'{"command":"terraform destroy"}}',
                          capture_output=True, env=_guard_env(tmp_path, root, driver),
                          cwd=str(root), timeout=120, check=False)


GUARD_DRIVERS = [pytest.param("sh", marks=needs_bash), pytest.param("ps1", marks=needs_pwsh)]


@pytest.mark.parametrize("driver", GUARD_DRIVERS)
def test_cloud_guard_without_python_is_armed_by_the_main_checkouts_config(tmp_path, driver):
    _main, wt = _lane(tmp_path, {"guards": {"cloudGuard": "block"}})
    proc = _run_guard(tmp_path, wt, driver)
    assert proc.returncode == 2, proc.stderr


@pytest.mark.parametrize("driver", GUARD_DRIVERS)
def test_cloud_guard_without_python_is_armed_when_git_cannot_tell(tmp_path, driver):
    root = _case_git_file_naming_a_missing_dir(tmp_path)
    proc = _run_guard(tmp_path, root, driver)
    assert proc.returncode == 2, proc.stderr


@pytest.mark.parametrize("driver", GUARD_DRIVERS)
def test_cloud_guard_without_python_follows_the_lanes_own_off(tmp_path, driver):
    _main, wt = _lane(tmp_path, {"guards": {"cloudGuard": "block"}})
    _own(wt, "config.json", {"guards": {"cloudGuard": "off"}})
    proc = _run_guard(tmp_path, wt, driver)
    assert proc.returncode == 0, proc.stderr


@pytest.mark.parametrize("driver", GUARD_DRIVERS)
@pytest.mark.parametrize("where", ["lane", "main-checkout"])
def test_cloud_guard_without_python_allows_when_no_layer_arms_it(tmp_path, driver, where):
    main, wt = _lane(tmp_path, None)
    proc = _run_guard(tmp_path, wt if where == "lane" else main, driver)
    assert proc.returncode == 0, proc.stderr


@needs_bash
def test_cloud_guard_without_common_sh_is_armed_in_a_main_checkout(tmp_path):
    """A `_common.sh` that cannot be sourced leaves no resolver: that is
    "could not tell", so the fallback refuses, as it did before T-0096."""
    main = make_repo(tmp_path, mode=None, name="main")
    (main / ".crew" / "config.json").write_text(json.dumps({"guards": {"cloudGuard": "block"}}),
                                                encoding="utf-8")
    hooks = tmp_path / "hooks"
    hooks.mkdir()
    shutil.copy(os.path.join(SCRIPTS, "cloud-guard.sh"), hooks / "cloud-guard.sh")
    proc = subprocess.run([_BASH, str(hooks / "cloud-guard.sh")],
                          input=b'{"tool_name":"Bash","tool_input":{"command":"terraform destroy"}}',
                          capture_output=True, env=_guard_env(tmp_path, main, "sh"),
                          cwd=str(main), timeout=120, check=False)
    assert proc.returncode == 2, proc.stderr


# --- the incident stand-down -------------------------------------------------------------

VERIFY_JSON = {"version": 1, "rules": [], "always": [], "default": [], "unmapped": "warn",
               "environments": {"production": {"deploy": ["./deploy.sh prod"],
                                               "requires": ["qa"]}}}


def _incident_lane(tmp_path, lane_cfg):
    """A lane with an open incident and a deploy map of its own; the main
    checkout forbids stand-downs. `lane_cfg` is the lane's own config, or None."""
    _main, wt = _lane(tmp_path, {"emergency": {"standDown": False}})
    _own(wt, "incident.json", {"id": "INC-T", "summary": "suite",
                               "expiresAtEpoch": int(time.time()) + 3600})
    _own(wt, "verify.json", VERIFY_JSON)
    if lane_cfg is not None:
        _own(wt, "config.json", lane_cfg)
    return wt


def _incident_active_sh(root):
    proc = subprocess.run([_BASH, "-c", '. "$1"; crew_incident_active; echo "rc=$?"', "_",
                           _posix(COMMON_SH)], capture_output=True, text=True, check=False,
                          cwd=str(root), timeout=60, stdin=subprocess.DEVNULL)
    return proc.stdout.strip().splitlines()[-1] == "rc=0"


def _promote_ps1(root):
    env = dict(os.environ, CLAUDE_PROJECT_DIR=str(root), OS="Windows_NT")
    proc = subprocess.run(
        [_PWSH, "-NoProfile", "-NonInteractive", "-File", os.path.join(SCRIPTS, "promote-gate.ps1")],
        input=json.dumps({"tool_name": "PowerShell", "tool_input": {"command": "./deploy.sh prod"}}),
        cwd=str(root), env=env, capture_output=True, text=True, check=False, timeout=120)
    assert proc.returncode in (0, 2), proc.stderr
    return proc.returncode == 0  # 0: stood down and recorded a skip; 2: blocked


@pytest.mark.parametrize("flavour", [pytest.param("sh", marks=needs_bash),
                                     pytest.param("promote-gate.ps1", marks=needs_pwsh)])
@pytest.mark.parametrize("lane_cfg,active", [(None, False), ({}, True)],
                         ids=["inherits-standDown-false", "own-config-without-the-key"])
def test_incident_stand_down_false_is_inherited(tmp_path, flavour, lane_cfg, active):
    wt = _incident_lane(tmp_path, lane_cfg)
    stood_down = _incident_active_sh(wt) if flavour == "sh" else _promote_ps1(wt)
    assert stood_down is active


# --- auto-clear.ps1's repo veto ----------------------------------------------------------

def _auto_clear(root, home, flavour):
    env = dict(os.environ, CLAUDE_PROJECT_DIR=str(root), CREW_AUTOCLEAR_INHIBIT="1",
               HOME=str(home), USERPROFILE=str(home))
    if flavour == "sh":
        argv = [_BASH, os.path.join(SCRIPTS, "auto-clear.sh")]
    else:
        env["OS"] = "Windows_NT"
        argv = [_PWSH, "-NoProfile", "-NonInteractive", "-File",
                os.path.join(SCRIPTS, "auto-clear.ps1"), "-Root", str(root)]
    return subprocess.run(argv, cwd=str(root), env=env, stdin=subprocess.DEVNULL,
                          capture_output=True, text=True, check=False, timeout=120)


@pytest.mark.parametrize("flavour", [pytest.param("sh", marks=needs_bash),
                                     pytest.param("ps1", marks=needs_pwsh)])
@pytest.mark.parametrize("main_enabled,armed", [(False, False), (None, True)],
                         ids=["main-vetoes", "main-silent"])
def test_auto_clear_ps1_reads_the_inherited_repo_veto(tmp_path, flavour, main_enabled, armed):
    """Machine opted in, main checkout's repo config vetoes, lane has `.crew/`
    but no config: both flavours are off, as crew_autocycle.py decides for
    auto-clear.sh. Armed, either reaches the session check and logs it."""
    main_cfg = {} if main_enabled is None else {"context": {"autoClear": {"enabled": main_enabled}}}
    _main, wt = _lane(tmp_path, main_cfg)
    (wt / ".crew").mkdir()
    home = tmp_path / "home"
    (home / ".claude" / "crew").mkdir(parents=True)
    (home / ".claude" / "crew" / "config.json").write_text(
        json.dumps({"context": {"autoClear": {"enabled": True}}}), encoding="utf-8")

    proc = _auto_clear(wt, home, flavour)

    assert proc.returncode == 0, proc.stderr
    assert (wt / ".crew" / ".autoclear.log").exists() is armed, proc.stderr


# --- the session hooks (L-0680) ----------------------------------------------------------
#
# notify, handoff-read, handoff-write and context-watch, both flavours, read the
# resolved repo config: a lane with none of its own reads the main checkout's,
# its own file wins whole, and `unknown` reads nothing. Every write stays in the
# lane. No test sends a real notification: the provider is `teams` pointed (via
# urlEnv) at a local HTTP stub that counts the posts.

SESSION_DRIVERS = [pytest.param("sh", marks=needs_bash), pytest.param("ps1", marks=needs_pwsh)]
SESSION_HOOKS = ("notify", "handoff-read", "handoff-write", "context-watch")
_URL_ENV = "CREW_L0680_STUB_URL"


def _session_env(tmp_path, root, flavour, extra=None):
    env = {k: v for k, v in os.environ.items()
           if k.lower() not in ("http_proxy", "https_proxy", "all_proxy", "no_proxy")
           and k not in ("CLAUDE_PROJECT_DIR", "OS", "CI", "CREW_UNATTENDED")}
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    env.update({"HOME": str(home), "USERPROFILE": str(home), "CLAUDE_PROJECT_DIR": str(root),
                "CREW_AUTOCLEAR_INHIBIT": "1", "PYTHONDONTWRITEBYTECODE": "1",
                "NO_PROXY": "127.0.0.1,localhost", "no_proxy": "127.0.0.1,localhost"})
    if flavour == "ps1":
        env["OS"] = "Windows_NT"
    env.update(extra or {})
    return env


def _run_session_hook(tmp_path, hook, flavour, root, payload=None, args=(), extra=None):
    if flavour == "sh":
        argv = [_BASH, _posix(os.path.join(SCRIPTS, hook + ".sh")), *args]
    else:
        argv = [_PWSH, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File",
                os.path.join(SCRIPTS, hook + ".ps1"), *args]
    data = b"" if payload is None else json.dumps(payload).encode("utf-8")
    return subprocess.run(argv, input=data, capture_output=True, cwd=str(root),
                          env=_session_env(tmp_path, root, flavour, extra), timeout=120,
                          check=False)


class _Stub:
    """A local HTTP endpoint that counts POSTs: the notify provider."""

    def __init__(self):
        import http.server  # pylint: disable=import-outside-toplevel
        import threading  # pylint: disable=import-outside-toplevel
        posts = self.posts = []

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_POST(self):  # noqa: N802  pylint: disable=invalid-name
                length = int(self.headers.get("Content-Length") or 0)
                posts.append(self.rfile.read(length))
                self.send_response(200)
                self.send_header("Content-Length", "2")
                self.end_headers()
                self.wfile.write(b"{}")

            def log_message(self, *_args):  # pylint: disable=arguments-differ
                return

        self.server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}/hook"
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()


@pytest.fixture
def stub():
    server = _Stub()
    yield server
    server.close()


NOTIFY_CFG = {"notify": {"provider": "teams", "urlEnv": _URL_ENV, "events": ["waiting"]}}


def _notify(tmp_path, flavour, root, stub_server):
    return _run_session_hook(tmp_path, "notify", flavour, root, args=("waiting", "suite ping"),
                             extra={_URL_ENV: stub_server.url})


@pytest.mark.parametrize("flavour", SESSION_DRIVERS)
def test_notify_in_a_lane_uses_the_main_checkouts_provider(tmp_path, flavour, stub):
    _main, wt = _lane(tmp_path, NOTIFY_CFG)
    proc = _notify(tmp_path, flavour, wt, stub)
    assert proc.returncode == 0, proc.stderr
    assert len(stub.posts) == 1, proc.stderr
    assert b"suite ping" in stub.posts[0]


@pytest.mark.parametrize("flavour", SESSION_DRIVERS)
def test_notify_in_a_lane_with_its_own_config_ignores_the_main_checkouts(tmp_path, flavour, stub):
    _main, wt = _lane(tmp_path, NOTIFY_CFG)
    _own(wt, "config.json", {"scope": {"mode": "block"}})
    proc = _notify(tmp_path, flavour, wt, stub)
    assert proc.returncode == 0, proc.stderr
    assert not stub.posts, proc.stderr


@pytest.mark.parametrize("flavour", SESSION_DRIVERS)
def test_notify_in_the_main_checkout_still_uses_its_own_provider(tmp_path, flavour, stub):
    main, _wt = _lane(tmp_path, NOTIFY_CFG)
    proc = _notify(tmp_path, flavour, main, stub)
    assert proc.returncode == 0, proc.stderr
    assert len(stub.posts) == 1, proc.stderr


HANDOFF_CFG = {"context": {"handoffPath": "notes/H.md"}, "memory": {"inject": False}}


def _note(root, text):
    (root / "notes").mkdir(exist_ok=True)
    (root / "notes" / "H.md").write_text(text + "\n", encoding="utf-8")


def _handoff_read(tmp_path, flavour, root, session="s-read"):
    return _run_session_hook(tmp_path, "handoff-read", flavour, root,
                             payload={"source": "clear", "cwd": str(root), "session_id": session})


@pytest.mark.parametrize("flavour", SESSION_DRIVERS)
def test_handoff_read_in_a_lane_prints_the_note_at_the_inherited_path(tmp_path, flavour):
    main, wt = _lane(tmp_path, HANDOFF_CFG)
    _note(main, "MAIN CHECKOUT NOTE")
    _note(wt, "LANE NOTE")
    proc = _handoff_read(tmp_path, flavour, wt)
    out = proc.stdout.decode("utf-8", "replace")
    assert proc.returncode == 0, proc.stderr
    assert "LANE NOTE" in out, proc.stderr
    assert "MAIN CHECKOUT NOTE" not in out


def _transcripts(root):
    return sorted((root / ".crew" / "transcripts").glob("*.jsonl"))


def _crew_listing(root):
    return sorted(str(p.relative_to(root)) for p in (root / ".crew").rglob("*"))


@pytest.mark.parametrize("flavour", SESSION_DRIVERS)
def test_handoff_write_in_a_lane_keeps_the_inherited_transcript_count(tmp_path, flavour):
    main, wt = _lane(tmp_path, {"context": {"keepTranscripts": 2}})
    before = _crew_listing(main)
    transcript = tmp_path / "session.jsonl"
    transcript.write_text('{"x": 1}\n', encoding="utf-8")
    for n in range(3):
        if n:
            time.sleep(1.1)  # the copy is named to the second
        proc = _run_session_hook(tmp_path, "handoff-write", flavour, wt, payload={
            "transcript_path": str(transcript), "trigger": "manual", "cwd": str(wt),
            "session_id": f"s-write-{n}"})
        assert proc.returncode == 0, proc.stderr
    assert len(_transcripts(wt)) == 2
    assert _crew_listing(main) == before


@pytest.mark.parametrize("flavour", SESSION_DRIVERS)
def test_handoff_write_in_the_main_checkout_keeps_its_own_transcript_count(tmp_path, flavour):
    """Own file. The .ps1 used to drop keepTranscripts on PowerShell 7, whose
    ConvertFrom-Json reads a JSON integer as Int64, not [int]."""
    main, _wt = _lane(tmp_path, {"context": {"keepTranscripts": 1}})
    transcript = tmp_path / "session.jsonl"
    transcript.write_text('{"x": 1}\n', encoding="utf-8")
    for n in range(2):
        if n:
            time.sleep(1.1)
        proc = _run_session_hook(tmp_path, "handoff-write", flavour, main, payload={
            "transcript_path": str(transcript), "trigger": "manual", "cwd": str(main),
            "session_id": f"s-own-{n}"})
        assert proc.returncode == 0, proc.stderr
    assert len(_transcripts(main)) == 1


def _context_cfg(**over):
    cfg = {"warnAt": 0.8, "budgetTokens": 100, "reserveTokens": 0, "autoWrapUp": False}
    cfg.update(over)
    return {"context": cfg}


def _context_watch(tmp_path, flavour, root, extra=None, session="s-watch"):
    transcript = root / "transcript.jsonl"
    transcript.write_bytes(b"x" * 500)  # over 0.8 of a 100-token budget
    return _run_session_hook(tmp_path, "context-watch", flavour, root, payload={
        "transcript_path": str(transcript), "cwd": str(root), "session_id": session,
        "stop_hook_active": False}, extra=extra)


CONTEXT_DRIVERS = [pytest.param("sh", marks=needs_bash), pytest.param("ps1", marks=needs_pwsh),
                   pytest.param("sh-no-python", marks=needs_bash)]


def _watch_flavour(driver):
    return ("sh", NO_PYTHON) if driver == "sh-no-python" else (driver, None)


def _markers(root):
    return list((root / ".crew").glob(".handoff-requested-*"))


@pytest.mark.parametrize("driver", CONTEXT_DRIVERS)
def test_context_watch_in_a_lane_follows_the_inherited_enabled_false(tmp_path, driver):
    _main, wt = _lane(tmp_path, _context_cfg(enabled=False))
    (wt / ".crew").mkdir()
    flavour, extra = _watch_flavour(driver)
    proc = _context_watch(tmp_path, flavour, wt, extra)
    assert proc.returncode == 0, proc.stderr
    assert not _markers(wt)


@pytest.mark.parametrize("driver", CONTEXT_DRIVERS)
def test_context_watch_in_a_lane_warns_at_the_inherited_threshold(tmp_path, driver):
    main, wt = _lane(tmp_path, _context_cfg())
    (wt / ".crew").mkdir()
    flavour, extra = _watch_flavour(driver)
    first = _context_watch(tmp_path, flavour, wt, extra)
    assert first.returncode == 2, first.stderr
    if driver == "sh-no-python":
        return  # the no-python branch asks once per turn and claims no marker, by design
    err = first.stderr.decode("utf-8", "replace")
    # the message names the file in force, the main checkout's, not the lane's
    shown = {str(main / ".crew" / "config.json"),
             os.path.join(os.path.realpath(main), ".crew", "config.json")}
    assert any(s in err for s in shown), err
    second = _context_watch(tmp_path, flavour, wt, extra)
    assert second.returncode == 0, second.stderr
    assert len(_markers(wt)) == 1
    assert not _markers(main)


@pytest.mark.parametrize("flavour", SESSION_DRIVERS)
def test_context_watch_in_the_main_checkout_keeps_its_message(tmp_path, flavour):
    """Own file: the message still says `.crew/config.json`, byte for byte."""
    main, _wt = _lane(tmp_path, _context_cfg())
    proc = _context_watch(tmp_path, flavour, main)
    err = proc.stderr.decode("utf-8", "replace")
    assert proc.returncode == 2, err
    assert "That came from .crew/config.json." in err


@pytest.mark.parametrize("flavour", SESSION_DRIVERS)
def test_session_hooks_read_only_their_own_file_when_git_cannot_tell(tmp_path, flavour, stub):
    """`.git` naming a missing directory: nothing is inherited (there is no
    main checkout to name) and each hook behaves as with no config."""
    root = _case_git_file_naming_a_missing_dir(tmp_path)
    (root / ".crew").mkdir()
    _note(root, "UNKNOWN NOTE")
    assert _notify(tmp_path, flavour, root, stub).returncode == 0
    assert not stub.posts
    read = _handoff_read(tmp_path, flavour, root)
    assert read.returncode == 0 and b"UNKNOWN NOTE" not in read.stdout
    transcript = tmp_path / "session.jsonl"
    transcript.write_text("{}\n", encoding="utf-8")
    write = _run_session_hook(tmp_path, "handoff-write", flavour, root, payload={
        "transcript_path": str(transcript), "trigger": "manual", "cwd": str(root),
        "session_id": "s-unknown"})
    assert write.returncode == 0 and not _transcripts(root)
    watch = _context_watch(tmp_path, flavour, root)
    assert watch.returncode == 0 and not _markers(root), watch.stderr


# Lines in the eight scripts that may still name the own file outside a comment:
# the user-facing default of the name a message shows. Exact text and count.
OWN_PATH_ALLOWED = {
    "context-watch.ps1": {
        "$cfgShown = if ($repoCfg.Source -eq 'main') { $cfgPath } else { '.crew/config.json' }": 1,
    },
}


def _executable_mentions(path):
    found = {}
    for line in pathlib.Path(path).read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if text.startswith("#") or not any(n in text for n in (".crew/config.json",
                                                                ".crew/crew.json")):
            continue
        found[text] = found.get(text, 0) + 1
    return found


def test_no_session_hook_names_the_own_config_path():
    for hook in SESSION_HOOKS:
        for ext in ("sh", "ps1"):
            name = f"{hook}.{ext}"
            assert _executable_mentions(os.path.join(SCRIPTS, name)) == \
                OWN_PATH_ALLOWED.get(name, {}), name

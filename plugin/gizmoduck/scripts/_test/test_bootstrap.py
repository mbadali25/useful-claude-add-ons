"""bootstrap.sh's modes, privilege decision and exit status (L-0685).

Nothing here installs anything or reaches the network. Every run is
`--dry-run`, `--help`, a refusal, or the sourced `finish` summary. PATH is a
temp directory holding fakes (`id`, `sudo`, `curl`, `git`, `unzip`,
`python3`) plus links to the system's coreutils, and bash is called by
absolute path, so a removed fake is really missing and a stray write really
happens. `sudo`, `curl` and `git` append to a log;
a test that expects no action asserts the log is empty. HOME, GIZMODUCK_HOME
and XDG_DATA_HOME live under tmp_path.
"""
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from scanners import base

_BOOTSTRAP = Path(__file__).resolve().parents[2] / "bootstrap.sh"
_BASH = shutil.which("bash")
_SED = shutil.which("sed")
_COREUTILS = ("mkdir", "rm", "mv", "cp", "ln", "chmod", "cat", "touch", "dirname", "basename",
              "readlink", "mktemp", "sed", "grep", "head", "tail", "cut", "sort", "awk", "tr",
              "uname", "find", "tar", "sha256sum", "date", "env", "tee", "ls")

pytestmark = pytest.mark.skipif(_BASH is None, reason="bash not available")

_LOGGING = '#!{bash}\necho "{name} $*" >> "$FAKE_LOG"\n'
_TOKEN = "ghp_marker_never_print_me_0123456789"


@pytest.fixture
def env(tmp_path):
    """A fake PATH and a clean home; returns (env dict, fakes dir, log path)."""
    fakes = tmp_path / "fakes"
    fakes.mkdir()
    log = tmp_path / "fakes.log"
    log.write_text("")
    for name in ("sudo", "curl", "git", "unzip", "python3"):
        _fake(fakes, name, _LOGGING.format(bash=_BASH, name=name))
    _fake(fakes, "id", f'#!{_BASH}\necho "${{FAKE_UID:-1000}}"\n')
    # The system's coreutils and text tools, so a stray write (a mkdir in
    # --dry-run, say) really happens and is caught; never curl, git, unzip,
    # python3, sudo or id, which are the fakes above.
    for tool in _COREUTILS:
        real = shutil.which(tool)
        if real:
            os.symlink(real, fakes / tool)
    home = tmp_path / "home"
    home.mkdir()
    e = {"PATH": str(fakes), "HOME": str(home), "FAKE_LOG": str(log), "FAKE_UID": "1000"}
    return e, fakes, log


def _fake(fakes, name, body):
    p = fakes / name
    p.write_text(body, newline="\n")
    p.chmod(0o755)
    return p


def _run(e, *args, stdin=subprocess.DEVNULL):
    return subprocess.run([_BASH, str(_BOOTSTRAP), *args], env=e, capture_output=True,
                          text=True, stdin=stdin, timeout=60, check=False)


def _plans(proc):
    return [ln for ln in proc.stdout.splitlines() if ln.startswith("plan:")]


def _tree(path):
    return sorted(str(p.relative_to(path)) for p in path.rglob("*"))


def test_unknown_option_is_exit_2_and_does_nothing(env):
    e, _fakes, log = env
    proc = _run(e, "--frobnicate")
    assert proc.returncode == 2
    assert "unknown option '--frobnicate'" in proc.stderr
    assert not _plans(proc) and ">> installing" not in proc.stdout
    assert log.read_text() == ""


@pytest.mark.skipif(_SED is None, reason="sed not available")
def test_help_exits_0_and_names_user_and_dry_run(env):
    e, _fakes, log = env
    proc = _run(e, "--help")
    assert proc.returncode == 0, proc.stderr
    assert "--user" in proc.stdout and "--dry-run" in proc.stdout
    assert log.read_text() == ""


@pytest.mark.parametrize("mode", [[], ["--user"]])
def test_dry_run_writes_nothing_and_calls_nothing(env, tmp_path, mode):
    e, _fakes, log = env
    e["GIZMODUCK_HOME"] = str(tmp_path / "toolhome")
    before = _tree(Path(e["HOME"]))
    proc = _run(e, *mode, "--dry-run")
    assert proc.returncode == 0, proc.stderr
    assert _plans(proc)
    assert _tree(Path(e["HOME"])) == before
    assert not (tmp_path / "toolhome").exists()
    assert log.read_text() == ""


def test_root_uses_no_sudo(env):
    e, _fakes, log = env
    e["FAKE_UID"] = "0"
    proc = _run(e, "--dry-run")
    assert proc.returncode == 0, proc.stderr
    plans = _plans(proc)
    assert plans and all(ln.endswith("(as root)") for ln in plans), plans
    assert not re.search(r"(^|\s)sudo(\s|$)", proc.stdout), proc.stdout
    assert log.read_text() == ""


def test_non_root_with_sudo_plans_via_sudo(env):
    e, _fakes, _log = env
    proc = _run(e, "--dry-run")
    assert proc.returncode == 0, proc.stderr
    assert any(ln.endswith("(via sudo)") for ln in _plans(proc))
    assert "/usr/local/bin/nuclei" in proc.stdout


def test_non_root_without_sudo_is_exit_2_and_points_at_user_mode(env):
    e, fakes, log = env
    (fakes / "sudo").unlink()
    proc = _run(e, "--dry-run")
    assert proc.returncode == 2
    assert "--user" in proc.stderr
    assert not _plans(proc)
    assert log.read_text() == ""


def test_sudo_is_non_interactive_without_a_terminal(env):
    e, _fakes, _log = env
    proc = _run(e, "--dry-run", stdin=subprocess.DEVNULL)
    assert "privilege: sudo -n" in proc.stdout


def test_user_mode_plans_every_tool_under_the_tool_home(env, tmp_path):
    e, _fakes, _log = env
    e["GIZMODUCK_HOME"] = str(tmp_path / "toolhome")
    proc = _run(e, "--user", "--dry-run")
    assert proc.returncode == 0, proc.stderr
    plans = _plans(proc)
    assert len(plans) >= 12
    for ln in plans:
        assert "/opt" not in ln and "/usr/local" not in ln, ln
        assert "sudo" not in ln, ln
    assert f"plan: nuclei             -> {tmp_path / 'toolhome' / 'bin' / 'nuclei'} (user)" in plans


@pytest.mark.parametrize("which", ["gizmoduck_home", "xdg", "neither"])
def test_user_mode_tool_home_matches_base_tool_home(env, tmp_path, monkeypatch, which):
    e, _fakes, _log = env
    monkeypatch.delenv("GIZMODUCK_HOME", raising=False)
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    monkeypatch.setenv("HOME", e["HOME"])
    monkeypatch.setattr(base.Path, "home", classmethod(lambda cls: Path(e["HOME"])))
    if which == "gizmoduck_home":
        e["GIZMODUCK_HOME"] = str(tmp_path / "gh")
        monkeypatch.setenv("GIZMODUCK_HOME", e["GIZMODUCK_HOME"])
    elif which == "xdg":
        e["XDG_DATA_HOME"] = str(tmp_path / "xdg")
        monkeypatch.setenv("XDG_DATA_HOME", e["XDG_DATA_HOME"])
    proc = _run(e, "--user", "--dry-run")
    assert proc.returncode == 0, proc.stderr
    printed = [ln for ln in proc.stdout.splitlines() if ln.startswith("tool home: ")]
    assert printed == [f"tool home: {base.tool_home()}"]


def test_user_mode_lists_package_only_tools_as_skipped(env, tmp_path):
    e, fakes, _log = env
    e["GIZMODUCK_HOME"] = str(tmp_path / "toolhome")
    proc = _run(e, "--user", "--dry-run")
    plans = _plans(proc)
    for tool in ("nmap", "wkhtmltopdf", "testssl.sh"):  # testssl.sh: no hexdump here
        line = next(ln for ln in plans if ln.startswith(f"plan: {tool} "))
        assert "SKIPPED" in line and "FAILED" not in line, line
    nmap = _fake(fakes, "nmap", f"#!{_BASH}\nexit 0\n")
    proc = _run(e, "--user", "--dry-run")
    line = next(ln for ln in _plans(proc) if ln.startswith("plan: nmap "))
    assert line.endswith("(present)") and str(nmap) in line, line


@pytest.mark.parametrize("missing", ["curl", "unzip", "git", "python3"])
def test_user_mode_missing_prerequisite_is_exit_2_naming_it(env, tmp_path, missing):
    e, fakes, log = env
    e["GIZMODUCK_HOME"] = str(tmp_path / "toolhome")
    (fakes / missing).unlink()
    proc = _run(e, "--user")
    assert proc.returncode == 2
    assert missing in proc.stderr
    assert ">> installing" not in proc.stdout
    assert log.read_text() == ""
    assert not (tmp_path / "toolhome").exists()


@pytest.mark.parametrize("mode", [[], ["--user"]])
def test_github_token_is_never_printed(env, tmp_path, mode):
    e, _fakes, _log = env
    e["GITHUB_TOKEN"] = _TOKEN
    e["GIZMODUCK_HOME"] = str(tmp_path / "toolhome")
    proc = _run(e, *mode, "--dry-run")
    assert proc.returncode == 0, proc.stderr
    assert _TOKEN not in proc.stdout and _TOKEN not in proc.stderr


def test_github_token_reaches_curl_as_a_header_file_not_an_argument(env, tmp_path):
    e, fakes, log = env
    # A curl that records its argv and what each `-H @file` holds.
    _fake(fakes, "curl", f'#!{_BASH}\necho "curl $*" >> "$FAKE_LOG"\n'
          'prev=""; for a in "$@"; do [[ "$prev" == -H && "$a" == @* ]] && '
          'while IFS= read -r l; do echo "$l"; done < "${a#@}" >> "$FAKE_LOG.hdr"; prev="$a"; done\nexit 22\n')
    e["GITHUB_TOKEN"] = _TOKEN
    proc = subprocess.run([_BASH, "-c", 'source "$0"; github_api https://api.github.com/x',
                           str(_BOOTSTRAP)], env=e, capture_output=True, text=True,
                          timeout=30, check=False)
    assert _TOKEN not in log.read_text(), "the token was on curl's command line"
    assert Path(str(log) + ".hdr").read_text() == f"Authorization: Bearer {_TOKEN}\n"
    assert _TOKEN not in proc.stdout + proc.stderr


def _finish(e, failed, skipped):
    script = (f"source \"$0\"; FAILED=({' '.join(failed)}); SKIPPED=({' '.join(skipped)}); "
              "finish; echo \"rc=$?\"")
    return subprocess.run([_BASH, "-c", script, str(_BOOTSTRAP)], env=e,
                          capture_output=True, text=True, timeout=30, check=False)


def test_script_exit_status_is_1_when_a_tool_failed(env):
    e, _fakes, _log = env
    failed = _finish(e, ["trivy"], ["nmap"])
    assert "rc=1" in failed.stdout, failed.stdout + failed.stderr
    assert "trivy" in failed.stderr
    skipped = _finish(e, [], ["nmap", "wkhtmltopdf"])
    lines = skipped.stdout.splitlines()
    assert lines[-1] == "rc=0"
    assert lines[-2] == "GIZMODUCK_BOOTSTRAP_SKIPPED: nmap wkhtmltopdf"
    clean = _finish(e, [], [])
    assert clean.stdout.splitlines()[-1] == "rc=0"
    assert "GIZMODUCK_BOOTSTRAP_SKIPPED" not in clean.stdout


def test_main_exits_with_finish_status():
    # The executed script must end on finish's status, not on a trailing cat.
    tail = [ln.strip() for ln in _BOOTSTRAP.read_text().splitlines() if ln.strip()][-2:]
    assert tail == ["finish", "exit $?"], tail


def test_no_install_step_calls_sudo_directly():
    # Every privileged command goes through as_root, so --user and root runs
    # never reach sudo; the only code lines naming sudo are the decision itself.
    allowed = re.compile(r'PRIV=\(sudo|command -v sudo|^\s*echo |PRIV_LABEL="via sudo"')
    offenders = []
    for n, line in enumerate(_BOOTSTRAP.read_text().splitlines(), 1):
        code = line.split(" #", 1)[0]
        if line.lstrip().startswith("#") or not re.search(r"(^|[\s;|&(])sudo\b", code):
            continue
        if not allowed.search(code):
            offenders.append(f"{n}: {line.strip()}")
    assert not offenders, offenders


def test_a_skip_inside_try_install_reaches_the_last_line(env, tmp_path):
    # try_install runs each install in a subshell: the skip must survive it.
    e, _fakes, _log = env
    e["GIZMODUCK_HOME"] = str(tmp_path / "toolhome")
    script = ('source "$0"; USER_MODE=1; SKIP_LOG=$(mktemp); '
              'try_install nmap install_nmap; try_install wkhtmltopdf install_prereqs; '
              'finish; echo "rc=$?"; rm -f -- "$SKIP_LOG"')
    proc = subprocess.run([_BASH, "-c", script, str(_BOOTSTRAP)], env=e, capture_output=True,
                          text=True, timeout=30, check=False)
    lines = proc.stdout.splitlines()
    assert lines[-1] == "rc=0", proc.stdout + proc.stderr
    assert lines[-2] == "GIZMODUCK_BOOTSTRAP_SKIPPED: nmap wkhtmltopdf (PDF reports)", lines


@pytest.mark.parametrize("works", [True, False])
def test_user_mode_cached_nikto_is_kept_only_when_it_runs(env, tmp_path, works):
    # A cached clone is kept with no network call only when perl runs it.
    e, fakes, log = env
    out = "Nikto 2.5.0" if works else "Can't locate object method"
    _fake(fakes, "perl", f'#!{_BASH}\necho "{out}"\n')
    opt = tmp_path / "opt"
    (opt / "nikto" / "program").mkdir(parents=True)
    (opt / "nikto" / "program" / "nikto.pl").write_text("#!/usr/bin/perl\n", newline="\n")
    script = f'source "$0"; USER_MODE=1; OPT_DIR={opt}; install_nikto_user; echo "rc=$?"'
    proc = subprocess.run([_BASH, "-c", script, str(_BOOTSTRAP)], env=e, capture_output=True,
                          text=True, timeout=30, check=False)
    calls = log.read_text()
    if works:
        assert "nikto: already installed" in proc.stdout, proc.stdout + proc.stderr
        assert proc.stdout.splitlines()[-1] == "rc=0"
        assert "git" not in calls, calls
    else:
        assert "fails its check - reinstalling" in proc.stdout, proc.stdout + proc.stderr
        assert "git" in calls and "clone" in calls, calls


@pytest.mark.parametrize("works", [True, False])
def test_user_mode_fresh_nikto_clone_must_run(env, tmp_path, works):
    # A fresh clone is an install only when perl runs it, like a cached one.
    e, fakes, _log = env
    out = "Nikto 2.5.0" if works else "Can't locate XML/Writer.pm"
    _fake(fakes, "perl", f'#!{_BASH}\necho "{out}"\n')
    _fake(fakes, "git", f'#!{_BASH}\nfor d; do :; done\nmkdir -p "$d/program"\n'
                        f'echo "#!/usr/bin/perl" > "$d/program/nikto.pl"\n')
    opt = tmp_path / "opt"
    script = (f'source "$0"; USER_MODE=1; OPT_DIR={opt}; '
              'install_nikto_user; echo "rc=$?"')
    proc = subprocess.run([_BASH, "-c", script, str(_BOOTSTRAP)], env=e, capture_output=True,
                          text=True, timeout=30, check=False)
    assert (opt / "nikto" / "program" / "nikto.pl").is_file(), proc.stdout + proc.stderr
    if works:
        assert proc.stdout.splitlines()[-1] == "rc=0", proc.stdout + proc.stderr
    else:
        assert proc.stdout.splitlines()[-1] == "rc=1", proc.stdout + proc.stderr
        assert "perl cannot run" in proc.stderr, proc.stderr

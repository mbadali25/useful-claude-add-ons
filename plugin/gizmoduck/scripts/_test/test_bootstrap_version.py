"""Tests for bootstrap.sh's resolve_latest_tag and already_installed (C-0008).

Some networks - the Claude Code cloud sandbox among them - answer
api.github.com with a 403 while git and the versioned
releases/download/<tag>/ assets still work. resolve_latest_tag tries the API
first, falls back to `git ls-remote --tags`, keeps only plain X.Y.Z tags, and
names the tool when both fail.

bootstrap.sh is SOURCED (it returns before installing anything when sourced),
and `curl`, `git` and `sudo` are stubs placed first on PATH, so nothing here
touches the network or the machine. Every stub logs its argv, which is how
the tests prove a fallback was (or was not) taken.

`sudo` really runs what it is given (except apt-get, which it only logs), and
GIZMODUCK_BIN_DIR / GIZMODUCK_OPT_DIR point the install at tmp_path, so the
real download -> verify -> unpack -> install steps run against fixtures. The
`curl` stub serves `-o` downloads from a per-test assets directory.
"""
import os
import platform
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

_BOOTSTRAP = Path(__file__).resolve().parents[2] / "bootstrap.sh"
_BASH = shutil.which("bash")

pytestmark = pytest.mark.skipif(_BASH is None, reason="bash not available")

_STUB = """#!/usr/bin/env bash
echo "{name} $*" >> "$STUB_LOG"
{body}
"""

_CURL_BODY = """
out=""; url=""; prev=""
for a in "$@"; do
  [[ "$prev" == -o ]] && out="$a"
  [[ "$a" == http* ]] && url="$a"
  prev="$a"
done
if [[ -n "$out" ]]; then
  f="$STUB_ASSETS/${url##*/}"
  if [[ -f "$f" ]]; then cp "$f" "$out"; exit 0; fi
  echo "curl: (22) The requested URL returned error: 404" >&2; exit 22
fi
if [[ "${STUB_CURL_MODE:-fail}" == ok && "$url" == https://api.github.com/* ]]; then
  printf '{\\n  "url": "x",\\n  "tag_name": "v9.9.9",\\n  "name": "v9.9.9"\\n}\\n'
  exit 0
fi
echo "curl: (22) The requested URL returned error: 403" >&2; exit 22
"""

_GIT_BODY = """
[[ -n "${GIT_HTTP_LOW_SPEED_LIMIT:-}" ]] && \\
  echo "git-env ${GIT_HTTP_LOW_SPEED_LIMIT} ${GIT_HTTP_LOW_SPEED_TIME:-}" >> "$STUB_LOG"
if [[ "$1" == -c ]]; then shift 2; fi
if [[ "${STUB_GIT_MODE:-fail}" == ok && "$1" == ls-remote ]]; then
  cat "$STUB_GIT_TAGS"
elif [[ "${STUB_GIT_MODE:-fail}" == ok && "$1" == clone ]]; then
  dest="${@: -1}"
  mkdir -p "$dest/http/cves" && echo "id: stub" > "$dest/http/cves/stub.yaml"
else
  echo "fatal: unable to access: The requested URL returned error: 403" >&2
  exit 128
fi
"""

_SUDO_BODY = """
if [[ "$1" == apt-get ]]; then
  [[ " $* " == *" install "* && -n "${STUB_APT_FAIL_INSTALL:-}" ]] && exit 100
  exit 0
fi
exec "$@"
"""


_TIMEOUT_BODY = 'shift\nexec "$@"\n'


def _sha(i: int) -> str:
    return f"{i:040x}"


@pytest.fixture
def stubs(tmp_path):
    bindir = tmp_path / "bin"
    bindir.mkdir()
    for name, body in (("curl", _CURL_BODY), ("git", _GIT_BODY), ("sudo", _SUDO_BODY),
                       ("timeout", _TIMEOUT_BODY)):
        p = bindir / name
        p.write_text(_STUB.format(name=name, body=body), newline="\n")
        p.chmod(0o755)
    log = tmp_path / "calls.log"
    log.write_text("")
    tags = tmp_path / "tags.txt"
    for d in ("assets", "inst-bin", "inst-opt", "apt-lists"):
        (tmp_path / d).mkdir()
    (tmp_path / "apt-lists" / "x_Packages").write_text("")
    return {"bin": bindir, "log": log, "tags": tags, "tmp": tmp_path,
            "assets": tmp_path / "assets", "inst_bin": tmp_path / "inst-bin",
            "inst_opt": tmp_path / "inst-opt", "apt_lists": tmp_path / "apt-lists"}


def _run(stubs, script, curl="fail", git="fail", tags=(), extra_env=None):
    stubs["tags"].write_text(
        "".join(f"{_sha(i)}\trefs/tags/{t}\n" for i, t in enumerate(tags, 1)))
    env = {
        "PATH": f"{stubs['bin']}{os.pathsep}{os.environ.get('PATH', '')}",
        "HOME": str(stubs["tmp"]),
        "STUB_LOG": str(stubs["log"]),
        "STUB_GIT_TAGS": str(stubs["tags"]),
        "STUB_CURL_MODE": curl,
        "STUB_GIT_MODE": git,
        "STUB_ASSETS": str(stubs["assets"]),
        "GIZMODUCK_BIN_DIR": str(stubs["inst_bin"]),
        "GIZMODUCK_OPT_DIR": str(stubs["inst_opt"]),
        "GIZMODUCK_APT_LISTS_DIR": str(stubs["apt_lists"]),
    }
    env.update(extra_env or {})
    proc = subprocess.run(
        [_BASH, "-c", f'source "$0"; {script}', str(_BOOTSTRAP)],
        capture_output=True, text=True, env=env, timeout=30, check=False)
    return proc, stubs["log"].read_text()


def test_sourcing_installs_nothing(stubs):
    proc, log = _run(stubs, "true", curl="ok", git="ok")
    assert proc.returncode == 0, proc.stderr
    assert log == "", f"sourcing bootstrap.sh ran commands: {log!r}"
    assert ">> installing" not in proc.stdout


def test_api_ok_uses_api_and_never_asks_git(stubs):
    proc, log = _run(stubs, "resolve_latest_tag acme/tool tool",
                     curl="ok", git="ok", tags=["v1.0.0"])
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == "v9.9.9"
    assert "https://api.github.com/repos/acme/tool/releases/latest" in log
    assert "--connect-timeout 20 --max-time 60" in log
    assert "git " not in log


def test_api_fails_then_highest_git_tag_is_used(stubs):
    tags = ["v1.2.0", "v1.10.0", "v1.9.3", "v1.10.0^{}", "v.1.0.0", "w2026-09-30", "svn_2.4"]
    proc, log = _run(stubs, "resolve_latest_tag acme/tool tool", tags=tags, git="ok")
    assert proc.returncode == 0, proc.stderr
    # 1.10.0 > 1.9.3 only under version order, not plain string order.
    assert proc.stdout.strip() == "v1.10.0"
    assert "git ls-remote --tags --refs https://github.com/acme/tool.git" in log
    assert "GitHub API lookup failed" in proc.stderr


def test_unprefixed_and_prefixed_tags_compare_by_number(stubs):
    proc, _ = _run(stubs, "resolve_latest_tag acme/tool tool",
                   tags=["9.0.0", "v10.0.0", "2.0.0"], git="ok")
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == "v10.0.0"


@pytest.mark.parametrize("pre", ["v3.0.0-rc1", "v3.0.0-beta.2", "v3.0.0-alpha",
                                 "v3.0.0rc1", "v3.0.0-pre", "3.0.0.dev1"])
def test_prerelease_tags_are_skipped(stubs, pre):
    proc, _ = _run(stubs, "resolve_latest_tag acme/tool tool",
                   tags=["v2.5.1", pre, "v2.4.0"], git="ok")
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == "v2.5.1"


def test_only_prerelease_tags_is_a_failure_not_a_prerelease(stubs):
    proc, _ = _run(stubs, "resolve_latest_tag acme/tool tool",
                   tags=["v3.0.0-rc1", "v3.0.0-beta"], git="ok")
    assert proc.returncode == 1
    assert proc.stdout.strip() == ""


def test_both_fail_gives_clear_error_naming_the_tool(stubs):
    proc, log = _run(stubs, "resolve_latest_tag acme/tool 'Widget Scanner'")
    assert proc.returncode == 1
    assert proc.stdout.strip() == ""
    assert "Widget Scanner: could not determine the latest version" in proc.stderr
    assert "api.github.com/repos/acme/tool/releases/latest" in proc.stderr
    assert "git ls-remote --tags https://github.com/acme/tool.git" in proc.stderr
    assert "curl " in log and "git ls-remote" in log


def test_both_fail_stays_isolated_in_try_install_and_downloads_nothing(stubs):
    script = ('try_install "nuclei" install_nuclei; '
              'echo "FAILED=${FAILED[*]}"; echo "after=still-running"')
    # FORCE: the skip-if-present branch must not hide this on a machine that
    # already has nuclei.
    proc, log = _run(stubs, script, extra_env={"GIZMODUCK_BOOTSTRAP_FORCE": "1"})
    assert proc.returncode == 0, proc.stderr
    assert "FAILED=nuclei" in proc.stdout
    assert "after=still-running" in proc.stdout
    assert "nuclei: could not determine the latest version" in proc.stderr
    assert "!! nuclei: install failed - continuing with the rest" in proc.stderr
    assert "sudo " not in log, f"a download/install ran with no version: {log!r}"


def test_git_fallback_version_reaches_the_download_url(stubs):
    # sudo is a no-op stub, so the download command is logged, never run; all
    # that matters is which tag the asset URL was built from.
    script = 'try_install "nuclei" install_nuclei'
    _, log = _run(stubs, script, git="ok", tags=["v3.11.1", "v3.12.0-rc1", "v3.9.0"],
                     extra_env={"GIZMODUCK_BOOTSTRAP_FORCE": "1"})
    assert "releases/download/v3.11.1/nuclei_3.11.1_linux_" in log, log


def test_already_installed_skips(stubs):
    fake = stubs["bin"] / "nuclei"
    fake.write_text("#!/usr/bin/env bash\necho nuclei-fake\n", newline="\n")
    fake.chmod(0o755)
    proc, log = _run(stubs, "install_nuclei")
    assert proc.returncode == 0, proc.stderr
    assert "nuclei: already installed" in proc.stdout
    assert log == "", f"a present tool was reinstalled: {log!r}"


def test_force_reinstalls_a_present_tool(stubs):
    fake = stubs["bin"] / "nuclei"
    fake.write_text("#!/usr/bin/env bash\necho nuclei-fake\n", newline="\n")
    fake.chmod(0o755)
    proc, log = _run(stubs, "install_nuclei", curl="ok",
                     extra_env={"GIZMODUCK_BOOTSTRAP_FORCE": "1"})
    assert "already installed" not in proc.stdout
    assert "releases/download/v9.9.9/" in log


def test_trivy_falls_back_to_the_release_asset_when_its_install_script_fails(stubs):
    # The official install.sh (fetched with curl) fails, as it does where
    # github.com/<repo>/releases/<tag> is refused; the asset fallback must
    # then resolve the tag via git and fetch the versioned tarball plus its
    # checksums file. sudo is a logging no-op, so nothing is downloaded.
    proc, log = _run(stubs, 'try_install "trivy" install_trivy', git="ok",
                     tags=["v0.75.0", "v0.76.0-rc1", "v0.9.0"],
                     extra_env={"GIZMODUCK_BOOTSTRAP_FORCE": "1"})
    assert "official install script failed" in proc.stderr
    assert "git ls-remote --tags --refs https://github.com/aquasecurity/trivy.git" in log
    asset = {"x86_64": "64bit", "amd64": "64bit", "aarch64": "ARM64", "arm64": "ARM64"}
    arch = asset.get(platform.machine().lower())
    if arch is None:
        pytest.skip(f"no trivy asset name known for {platform.machine()}")
    # The exact upstream asset name: Linux-64bit / Linux-ARM64, not amd64.
    assert f"releases/download/v0.75.0/trivy_0.75.0_Linux-{arch}.tar.gz" in log, log
    assert "releases/download/v0.75.0/trivy_0.75.0_checksums.txt" in log, log


def _fake_nuclei(stubs, writes_templates):
    body = 'echo "nuclei $*" >> "$STUB_LOG"\n'
    if writes_templates:
        body += 'mkdir -p "$HOME/nuclei-templates/dns" && echo "id: x" > "$HOME/nuclei-templates/dns/x.yaml"\n'
    p = stubs["bin"] / "nuclei"
    p.write_text("#!/usr/bin/env bash\n" + body + "exit 0\n", newline="\n")
    p.chmod(0o755)


def test_templates_from_nuclei_itself_need_no_git(stubs):
    _fake_nuclei(stubs, writes_templates=True)
    proc, log = _run(stubs, "update_nuclei_templates; echo rc=$?", git="ok", tags=["v10.4.9"])
    assert "rc=0" in proc.stdout, proc.stderr
    assert "nuclei -update-templates" in log
    assert "git " not in log


def test_update_that_exits_0_with_no_templates_falls_back_to_git_clone(stubs):
    # Measured in the cloud sandbox: rc 0 and an empty ~/nuclei-templates.
    _fake_nuclei(stubs, writes_templates=False)
    proc, log = _run(stubs, "update_nuclei_templates; echo rc=$?", git="ok",
                     tags=["v10.4.9", "v10.5.0-rc1", "v9.9.9"])
    assert "rc=0" in proc.stdout, proc.stderr
    assert "no templates in" in proc.stderr and "trying git clone" in proc.stderr
    assert "clone -q --depth 1 --branch v10.4.9 https://github.com/projectdiscovery/nuclei-templates.git" in log, log
    assert (stubs["tmp"] / "nuclei-templates" / "http" / "cves" / "stub.yaml").is_file()


def test_no_templates_anywhere_is_still_a_hard_failure(stubs):
    _fake_nuclei(stubs, writes_templates=False)
    proc, _ = _run(stubs, "update_nuclei_templates; echo reached-after")
    assert proc.returncode == 1
    assert "reached-after" not in proc.stdout
    assert "template download failed" in proc.stderr


# --- bootstrap.ps1's twin, Resolve-LatestTag -------------------------------
#
# Driven under pwsh with the script's function definitions loaded from its
# AST (nothing at top level runs), Invoke-RestMethod shadowed by a function
# and `git` a bash stub on PATH - so POSIX hosts only.

_PS1 = _BOOTSTRAP.with_name("bootstrap.ps1")
_PWSH = shutil.which("pwsh") or next(
    (p for p in ("/opt/microsoft/powershell/7/pwsh", "/usr/bin/pwsh") if os.path.isfile(p)), None)

_PS_DRIVER = r"""
$ErrorActionPreference = "Stop"
$t = $null; $e = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile($env:PS1_PATH, [ref]$t, [ref]$e)
if ($e.Count) { throw "parse errors in bootstrap.ps1: $($e.Count)" }
$ast.FindAll({ $args[0] -is [System.Management.Automation.Language.FunctionDefinitionAst] }, $true) |
  ForEach-Object { . ([scriptblock]::Create($_.Extent.Text)) }
function Invoke-RestMethod {
  Add-Content -Path $env:STUB_LOG -Value "irm $($args[0])"
  if ($env:STUB_CURL_MODE -eq "ok") { return [pscustomobject]@{ tag_name = "v9.9.9" } }
  throw "Response status code does not indicate success: 403 (Forbidden)."
}
if ($env:PS_BODY) {
  try { Invoke-Expression $env:PS_BODY } catch { Write-Output "ERR=$($_.Exception.Message)" }
  return
}
try {
  $v = Resolve-LatestTag -Repo "acme/tool" -Tool "Widget Scanner"
  Write-Output "TAG=$v"
} catch {
  Write-Output "ERR=$($_.Exception.Message)"
}
"""

ps_only = pytest.mark.skipif(_PWSH is None or os.name == "nt",
                             reason="needs pwsh and a POSIX shell for the git stub")


def _pwsh_cache_dir(tmp):
    """A fresh, empty startup-profile cache for one pwsh spawn (L-0557).

    pwsh reads and rewrites `$XDG_CACHE_HOME/powershell/StartupProfileData-*`,
    and concurrent pwsh sharing one copy can crash at start-up, so every spawn
    here gets a new mkdtemp dir. It is made INSIDE the ambient cache root when
    that is not the user's own ~/.cache: in CI this suite runs in the same
    pytest process as plugin/crew/tests, whose conftest points the variable at
    a session dir and audits that every pwsh cache sits under it. Otherwise
    (no ambient value, or the user default) it goes under the test's tmp."""
    ambient = os.environ.get("XDG_CACHE_HOME") or ""
    user_default = os.path.join(os.path.expanduser("~"), ".cache")
    usable = (ambient and os.path.isdir(ambient)
              and os.path.realpath(ambient) != os.path.realpath(user_default))
    return tempfile.mkdtemp(prefix="gizmoduck-pwsh-", dir=ambient if usable else str(tmp))


def _run_ps(stubs, curl="fail", git="fail", tags=(), body=""):
    stubs["tags"].write_text(
        "".join(f"{_sha(i)}\trefs/tags/{t}\n" for i, t in enumerate(tags, 1)))
    driver = stubs["tmp"] / "driver.ps1"
    driver.write_text(_PS_DRIVER)
    cache = _pwsh_cache_dir(stubs["tmp"])
    env = {
        "PATH": f"{stubs['bin']}{os.pathsep}{os.environ.get('PATH', '')}",
        "HOME": str(stubs["tmp"]),
        "PS1_PATH": str(_PS1),
        "STUB_LOG": str(stubs["log"]),
        "STUB_GIT_TAGS": str(stubs["tags"]),
        "STUB_CURL_MODE": curl,
        "STUB_GIT_MODE": git,
        "XDG_CACHE_HOME": cache,
        "PS_BODY": body,
    }
    try:
        proc = subprocess.run([_PWSH, "-NoProfile", "-NonInteractive", "-File", str(driver)],
                              capture_output=True, text=True, env=env, timeout=120, check=False)
    finally:
        shutil.rmtree(cache, ignore_errors=True)
    return proc, stubs["log"].read_text()


@ps_only
def test_ps1_api_ok_uses_api_and_never_asks_git(stubs):
    proc, log = _run_ps(stubs, curl="ok", git="ok", tags=["v1.0.0"])
    assert "TAG=v9.9.9" in proc.stdout, proc.stdout + proc.stderr
    assert "irm https://api.github.com/repos/acme/tool/releases/latest" in log
    assert "git " not in log


@ps_only
def test_ps1_api_fails_then_highest_stable_git_tag(stubs):
    tags = ["v1.2.0", "v1.10.0", "v1.11.0-rc1", "v1.9.3", "v.1.0.0", "w2026-09-30", "9.0.0-beta"]
    proc, log = _run_ps(stubs, git="ok", tags=tags)
    assert "TAG=v1.10.0" in proc.stdout, proc.stdout + proc.stderr
    assert "git ls-remote --tags --refs https://github.com/acme/tool.git" in log


@ps_only
def test_ps1_both_fail_throws_naming_the_tool(stubs):
    proc, _ = _run_ps(stubs)
    assert "ERR=Widget Scanner: could not determine the latest version" in proc.stdout, \
        proc.stdout + proc.stderr
    assert "TAG=" not in proc.stdout


# --- apt-get options (a /tmp at 755 breaks apt's `_apt` sandbox user) -------

_APT_OPTS = "apt-get -o APT::Sandbox::User=root -o DPkg::Lock::Timeout=600"


def test_apt_installs_run_the_sandbox_as_root_with_a_lock_timeout_then_clean(stubs):
    proc, log = _run(stubs, "install_nmap; install_nikto",
                     extra_env={"GIZMODUCK_BOOTSTRAP_FORCE": "1"})
    assert proc.returncode == 0, proc.stderr
    assert f"sudo {_APT_OPTS} install -y nmap\n" in log, log
    assert f"sudo {_APT_OPTS} install -y nikto\n" in log, log
    assert log.count(f"sudo {_APT_OPTS} clean\n") == 2, log


def test_a_failed_apt_install_is_not_masked_by_clean_even_with_set_e_off(stubs):
    # `|| apt_install` runs it with set -e suspended (install_depcheck's JRE).
    failing = stubs["bin"] / "sudo"
    failing.write_text('#!/usr/bin/env bash\necho "sudo $*" >> "$STUB_LOG"\n'
                       '[[ " $* " == *" install "* ]] && exit 100\nexit 0\n', newline="\n")
    failing.chmod(0o755)
    proc, log = _run(stubs, "false || apt_install default-jre; echo rc=$?")
    assert "rc=100" in proc.stdout, proc.stdout + proc.stderr
    assert "clean" not in log


def test_every_apt_get_call_goes_through_the_helper():
    calls = [ln for ln in _BOOTSTRAP.read_text().splitlines()
             if "apt-get " in ln and not ln.lstrip().startswith("#")
             and "command -v apt-get" not in ln and "echo" not in ln]
    assert calls == [f"  sudo {_APT_OPTS} \"$@\""], calls



# --- review round 1 (C-0008): templates never lose files ---------------------

def _fake_nuclei_rc(stubs, rc):
    p = stubs["bin"] / "nuclei"
    p.write_text('#!/usr/bin/env bash\necho "nuclei $*" >> "$STUB_LOG"\n'
                 f'exit {rc}\n', newline="\n")
    p.chmod(0o755)


def _tree(root):
    return sorted(str(p.relative_to(root)) for p in root.rglob("*") if p.is_file())


def test_failed_update_over_existing_templates_keeps_every_file(stubs):
    # Must-block: the clone fallback once ran on any non-zero exit and
    # replaced the directory, deleting a user's own templates.
    tdir = stubs["tmp"] / "nuclei-templates"
    (tdir / "custom").mkdir(parents=True)
    (tdir / "custom" / "mine.yaml").write_text("id: mine\n")
    (tdir / "notes.txt").write_text("keep me\n")
    before = _tree(tdir)
    _fake_nuclei_rc(stubs, 1)
    proc, log = _run(stubs, "update_nuclei_templates; echo rc=$?", git="ok", tags=["v10.4.9"])
    assert "rc=0" in proc.stdout, proc.stderr
    assert "keeping the existing templates" in proc.stderr
    assert _tree(tdir) == before
    assert "clone" not in log
    assert not list(stubs["tmp"].glob("nuclei-templates.gizmoduck-clone*"))


def test_files_but_no_templates_are_never_replaced(stubs):
    # Must-block: a directory with files but no *.yaml is refused, not wiped.
    tdir = stubs["tmp"] / "nuclei-templates"
    (tdir / "sub").mkdir(parents=True)
    (tdir / "sub" / "important.json").write_text("{}\n")
    _fake_nuclei_rc(stubs, 0)
    proc, _ = _run(stubs, "update_nuclei_templates; echo after", git="ok", tags=["v10.4.9"])
    assert proc.returncode == 1
    assert "holds files but no templates - not replacing it" in proc.stderr
    assert (tdir / "sub" / "important.json").read_text() == "{}\n"
    assert not list(tdir.rglob("*.yaml"))
    assert not list(stubs["tmp"].glob("nuclei-templates.gizmoduck-clone*"))


def test_empty_directories_are_replaced_by_the_clone(stubs):
    tdir = stubs["tmp"] / "nuclei-templates"
    (tdir / "github" / "empty").mkdir(parents=True)
    _fake_nuclei_rc(stubs, 0)
    proc, _ = _run(stubs, "update_nuclei_templates; echo rc=$?", git="ok", tags=["v10.4.9"])
    assert "rc=0" in proc.stdout, proc.stderr
    assert (tdir / "http" / "cves" / "stub.yaml").is_file()
    assert not list(stubs["tmp"].glob("nuclei-templates.gizmoduck-clone*"))


def test_missing_engine_is_a_hard_failure(stubs):
    # PATH without any directory holding a real nuclei.
    keep = [d for d in os.environ.get("PATH", "").split(os.pathsep)
            if d and not os.path.exists(os.path.join(d, "nuclei"))]
    proc, log = _run(stubs, "update_nuclei_templates; echo reached-after",
                     extra_env={"PATH": os.pathsep.join([str(stubs["bin"])] + keep)})
    assert proc.returncode == 1
    assert "reached-after" not in proc.stdout
    assert "nuclei engine is not installed" in proc.stderr
    assert "clone" not in log


def test_template_clone_runs_under_timeout_with_a_low_speed_limit(stubs):
    _fake_nuclei_rc(stubs, 0)
    _, log = _run(stubs, "update_nuclei_templates", git="ok", tags=["v10.4.9"])
    assert "timeout 900 git -c advice.detachedHead=false clone" in log, log
    assert "timeout 120 git ls-remote" in log, log
    assert "git-env 1000 30" in log, log


def test_ls_remote_still_runs_where_timeout_is_missing(stubs, tmp_path):
    # A PATH of only what resolve_latest_tag needs, and no `timeout`.
    lean = tmp_path / "lean"
    lean.mkdir()
    for tool in ("bash", "sed", "grep", "awk", "sort", "tail", "cut", "head", "cat"):
        real = shutil.which(tool)
        if real is None:
            pytest.skip(f"{tool} not found")
        (lean / tool).symlink_to(real)
    for tool in ("curl", "git"):
        (lean / tool).symlink_to(stubs["bin"] / tool)
    proc, log = _run(stubs, "resolve_latest_tag acme/tool tool", git="ok",
                     tags=["v1.2.3"], extra_env={"PATH": str(lean)})
    assert proc.stdout.strip() == "v1.2.3", proc.stderr
    assert "timeout 120" not in log
    assert "git-env 1000 30" in log


# --- review round 1: downloads are verified before anything is installed ----

posix_only = pytest.mark.skipif(os.name == "nt", reason="bootstrap.sh is Linux/WSL only")


def _need(*tools):
    missing = [t for t in tools if shutil.which(t) is None]
    if missing:
        pytest.skip(f"missing {missing}")


def _sha256(path):
    import hashlib  # pylint: disable=import-outside-toplevel
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _nuclei_assets(stubs, good=True, sums_line=True):
    import zipfile  # pylint: disable=import-outside-toplevel
    arch = {"x86_64": "amd64", "amd64": "amd64", "aarch64": "arm64",
            "arm64": "arm64"}.get(platform.machine().lower())
    if arch is None:
        pytest.skip(f"no nuclei asset name for {platform.machine()}")
    zpath = stubs["assets"] / f"nuclei_3.11.1_linux_{arch}.zip"
    with zipfile.ZipFile(zpath, "w") as z:
        info = zipfile.ZipInfo("nuclei")
        info.external_attr = 0o755 << 16
        z.writestr(info, "#!/usr/bin/env bash\necho 'Nuclei Engine Version: v3.11.1' >&2\n")
    digest = _sha256(zpath) if good else "0" * 64
    if sums_line is not None:
        name = zpath.name if sums_line else zpath.name + ".sig"
        (stubs["assets"] / "nuclei_3.11.1_checksums.txt").write_text(f"{digest}  {name}\n")
    return zpath


@posix_only
def test_nuclei_installs_when_its_checksum_matches(stubs):
    _need("unzip", "sha256sum")
    _nuclei_assets(stubs)
    proc, _ = _run(stubs, 'try_install nuclei install_nuclei; echo "FAILED=${FAILED[*]}"',
                   git="ok", tags=["v3.11.1"], extra_env={"GIZMODUCK_BOOTSTRAP_FORCE": "1"})
    assert "FAILED=\n" in proc.stdout, proc.stdout + proc.stderr
    assert "sha256 OK" in proc.stdout
    assert os.access(stubs["inst_bin"] / "nuclei", os.X_OK)
    assert not (stubs["inst_opt"] / "gizmoduck-nuclei-download").exists()


@posix_only
@pytest.mark.parametrize("case", ["mismatch", "no-line", "no-file"])
def test_nuclei_refuses_an_unverified_download(stubs, case):
    _need("unzip", "sha256sum")
    _nuclei_assets(stubs, good=(case != "mismatch"),
                   sums_line={"mismatch": True, "no-line": False, "no-file": None}[case])
    proc, _ = _run(stubs, 'try_install nuclei install_nuclei; echo "FAILED=${FAILED[*]}"',
                   git="ok", tags=["v3.11.1"], extra_env={"GIZMODUCK_BOOTSTRAP_FORCE": "1"})
    assert "FAILED=nuclei" in proc.stdout, proc.stdout + proc.stderr
    assert not (stubs["inst_bin"] / "nuclei").exists()
    if case == "mismatch":
        assert "sha256 mismatch" in proc.stderr
    if case == "no-line":
        assert "no checksum line" in proc.stderr


def _trivy_assets(stubs, good=True):
    import io  # pylint: disable=import-outside-toplevel
    import tarfile  # pylint: disable=import-outside-toplevel
    arch = {"x86_64": "64bit", "amd64": "64bit", "aarch64": "ARM64",
            "arm64": "ARM64"}.get(platform.machine().lower())
    if arch is None:
        pytest.skip(f"no trivy asset name for {platform.machine()}")
    tpath = stubs["assets"] / f"trivy_0.75.0_Linux-{arch}.tar.gz"
    body = b"#!/usr/bin/env bash\necho 'Version: 0.75.0'\n"
    with tarfile.open(tpath, "w:gz") as t:
        info = tarfile.TarInfo("trivy")
        info.size, info.mode = len(body), 0o755
        t.addfile(info, io.BytesIO(body))
    digest = _sha256(tpath) if good else "f" * 64
    (stubs["assets"] / "trivy_0.75.0_checksums.txt").write_text(
        f"{'1' * 64}  {tpath.name}.sig\n{digest}  {tpath.name}\n")


@posix_only
def test_trivy_asset_installs_when_its_checksum_matches(stubs):
    _need("tar", "sha256sum")
    _trivy_assets(stubs)
    proc, _ = _run(stubs, 'try_install trivy install_trivy; echo "FAILED=${FAILED[*]}"',
                   git="ok", tags=["v0.75.0"], extra_env={"GIZMODUCK_BOOTSTRAP_FORCE": "1"})
    assert "FAILED=\n" in proc.stdout, proc.stdout + proc.stderr
    assert "sha256 OK" in proc.stdout
    assert os.access(stubs["inst_bin"] / "trivy", os.X_OK)


@posix_only
def test_trivy_asset_with_a_bad_checksum_installs_nothing(stubs):
    # Must-fail: sha256 actually runs (the old no-op sudo stub hid it).
    _need("tar", "sha256sum")
    _trivy_assets(stubs, good=False)
    proc, _ = _run(stubs, 'try_install trivy install_trivy; echo "FAILED=${FAILED[*]}"',
                   git="ok", tags=["v0.75.0"], extra_env={"GIZMODUCK_BOOTSTRAP_FORCE": "1"})
    assert "FAILED=trivy" in proc.stdout, proc.stdout + proc.stderr
    assert "sha256 mismatch" in proc.stderr
    assert not (stubs["inst_bin"] / "trivy").exists()


# --- review round 1: skip-if-present probes, apt lists ----------------------

def test_a_present_but_broken_tool_is_reinstalled(stubs):
    broken = stubs["bin"] / "nuclei"
    broken.write_text("", newline="\n")   # zero-byte: exec fails
    broken.chmod(0o755)
    proc, log = _run(stubs, "install_nuclei", git="ok", tags=["v3.11.1"])
    assert "is empty - reinstalling" in proc.stdout, proc.stdout + proc.stderr
    assert "releases/download/v3.11.1/" in log


def test_zap_without_its_jar_is_reinstalled_and_with_it_is_skipped(stubs):
    zdir = stubs["tmp"] / "ZAP_2.17.0"
    zdir.mkdir()
    (zdir / "zap.sh").write_text("#!/usr/bin/env bash\n", newline="\n")
    (zdir / "zap.sh").chmod(0o755)
    (stubs["bin"] / "zap.sh").symlink_to(zdir / "zap.sh")
    script = "already_installed 'OWASP ZAP' zap.sh probe_zap; echo rc=$?"
    proc, _ = _run(stubs, script)
    assert "rc=1" in proc.stdout and "fails its check" in proc.stdout
    (zdir / "zap-2.17.0.jar").write_text("")
    proc, _ = _run(stubs, script)
    assert "rc=0" in proc.stdout and "already installed" in proc.stdout


def test_empty_apt_lists_are_refreshed_before_an_install(stubs):
    (stubs["apt_lists"] / "x_Packages").unlink()
    _, log = _run(stubs, "install_nmap", extra_env={"GIZMODUCK_BOOTSTRAP_FORCE": "1"})
    lines = [ln for ln in log.splitlines() if ln.startswith("sudo apt-get")]
    assert lines[0] == f"sudo {_APT_OPTS} update -y", lines
    assert lines[1] == f"sudo {_APT_OPTS} install -y nmap", lines


def test_present_apt_lists_skip_the_refresh(stubs):
    _, log = _run(stubs, "install_nmap", extra_env={"GIZMODUCK_BOOTSTRAP_FORCE": "1"})
    assert " update -y" not in log


def test_a_present_tool_whose_version_check_fails_is_reinstalled(stubs):
    _fake_nuclei_rc(stubs, 1)
    proc, _ = _run(stubs, "already_installed nuclei nuclei probe_nuclei; echo rc=$?")
    assert "rc=1" in proc.stdout and "fails its check - reinstalling" in proc.stdout



# --- review round 1: bootstrap.ps1 twins (checksum, safe template clone) -----

@ps_only
@pytest.mark.parametrize("case,expect", [
    ("good", "OK-INSTALLED"),
    ("mismatch", "ERR=nuclei_9.zip: sha256 mismatch"),
    ("sig-only", "ERR=nuclei_9.zip: no checksum line"),
])
def test_ps1_assert_sha256(stubs, case, expect):
    z = stubs["tmp"] / "nuclei_9.zip"
    z.write_bytes(b"payload")
    digest = _sha256(z) if case != "mismatch" else "0" * 64
    name = z.name + (".sig" if case == "sig-only" else "")
    sums = stubs["tmp"] / "sums.txt"
    sums.write_text(f"{digest}  {name}\n")
    body = f"Assert-Sha256 -File '{z}' -SumsFile '{sums}'; Write-Output OK-INSTALLED"
    proc, _ = _run_ps(stubs, body=body)
    assert expect in proc.stdout, proc.stdout + proc.stderr
    if case != "good":
        assert "OK-INSTALLED" not in proc.stdout


@ps_only
def test_ps1_template_clone_never_replaces_a_dir_with_files(stubs):
    tdir = stubs["tmp"] / "nuclei-templates"
    (tdir / "sub").mkdir(parents=True)
    (tdir / "sub" / "keep.json").write_text("{}\n")
    proc, _ = _run_ps(stubs, git="ok", tags=["v10.4.9"],
                      body=f"Install-NucleiTemplatesClone -Dir '{tdir}'")
    assert "holds files but no templates" in proc.stdout, proc.stdout + proc.stderr
    assert (tdir / "sub" / "keep.json").read_text() == "{}\n"
    assert not list(tdir.rglob("*.yaml"))
    assert not list(stubs["tmp"].glob("nuclei-templates.gizmoduck-clone*"))


@ps_only
def test_ps1_template_clone_replaces_only_empty_dirs(stubs):
    tdir = stubs["tmp"] / "nuclei-templates"
    (tdir / "github" / "empty").mkdir(parents=True)
    proc, log = _run_ps(stubs, git="ok", tags=["v10.4.9"],
                        body=f"Install-NucleiTemplatesClone -Dir '{tdir}'; Write-Output DONE")
    assert "DONE" in proc.stdout, proc.stdout + proc.stderr
    assert (tdir / "http" / "cves" / "stub.yaml").is_file()
    assert "git-env 1000 30" in log
    assert not list(stubs["tmp"].glob("nuclei-templates.gizmoduck-clone*"))


def test_a_failed_move_onto_a_dangling_symlink_leaks_no_temp_clone(stubs):
    tdir = stubs["tmp"] / "nuclei-templates"
    tdir.symlink_to(stubs["tmp"] / "gone")   # dangling: not -e, mv cannot replace it
    _fake_nuclei_rc(stubs, 0)
    proc, _ = _run(stubs, "update_nuclei_templates; echo after", git="ok", tags=["v10.4.9"])
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert tdir.is_symlink()
    assert not list(stubs["tmp"].glob("nuclei-templates.gizmoduck-clone*"))


@posix_only
def test_the_sqlmap_wrapper_quotes_its_path(stubs):
    opt = stubs["tmp"] / "opt with space"
    opt.mkdir()
    script = 'install_sqlmap; cat "$GIZMODUCK_BIN_DIR/sqlmap"'
    proc, _ = _run(stubs, script, git="ok",
                   extra_env={"GIZMODUCK_BOOTSTRAP_FORCE": "1", "GIZMODUCK_OPT_DIR": str(opt)})
    assert f'exec python3 "{opt}/sqlmap/sqlmap.py" "$@"' in proc.stdout, proc.stdout + proc.stderr

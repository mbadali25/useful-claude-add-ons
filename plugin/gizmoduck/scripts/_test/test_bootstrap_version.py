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
case "${STUB_CURL_MODE:-fail}" in
  ok)   printf '{\\n  "url": "x",\\n  "tag_name": "v9.9.9",\\n  "name": "v9.9.9"\\n}\\n' ;;
  *)    echo "curl: (22) The requested URL returned error: 403" >&2; exit 22 ;;
esac
"""

_GIT_BODY = """
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

_SUDO_BODY = "exit 0\n"


def _sha(i: int) -> str:
    return f"{i:040x}"


@pytest.fixture
def stubs(tmp_path):
    bindir = tmp_path / "bin"
    bindir.mkdir()
    for name, body in (("curl", _CURL_BODY), ("git", _GIT_BODY), ("sudo", _SUDO_BODY)):
        p = bindir / name
        p.write_text(_STUB.format(name=name, body=body), newline="\n")
        p.chmod(0o755)
    log = tmp_path / "calls.log"
    log.write_text("")
    tags = tmp_path / "tags.txt"
    return {"bin": bindir, "log": log, "tags": tags, "tmp": tmp_path}


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
    assert "curl -fsSL https://api.github.com/repos/acme/tool/releases/latest" in log
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
    assert "left no templates" in proc.stderr
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


def _run_ps(stubs, curl="fail", git="fail", tags=()):
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

"""crew-setup's `_verify` templates and its diagram case (T-0502).

`templates/cases/diagrams-render.sh` renders every Mermaid source with the
same `--no-sandbox` puppeteer config as crew-diagrams' render.sh, so it works
as root and in containers, and prints mmdc's own last lines when a render
fails. The two template runners (`templates/_verify/smoke.sh`, `run-all.sh`)
show a failing check's output tail and report exit 77 as SKIP.

Every test copies the templates into a throwaway repo under tmp_path and puts
a fake `mmdc` first on PATH; nothing here needs mermaid-cli or Chromium, and
real `mmdc` as root is not exercised. The lines setup-walkthrough.sh greps
(`SMOKE target: dev`, `SMOKE:`, `PASS read-orders`, `SKIP write-order`, the
production refusal) are asserted here too, because that walkthrough is run by
no rule.
"""
import json
import os
import shutil
import signal
import subprocess
import time

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import crew_fixtures

TEMPLATES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "skills", "crew-setup",
                         "templates")
CASE = os.path.join(TEMPLATES, "cases", "diagrams-render.sh")
_BASH = crew_fixtures.resolve_bash()

pytestmark = pytest.mark.skipif(_BASH is None, reason="needs a bash that runs scripts here")

ROOT_ERROR = "Running as root without --no-sandbox is not supported"

# Records its arguments and the -p config's contents; then behaves per FAKE_MODE.
FAKE_MMDC = """#!/usr/bin/env bash
out=""; cfg=""; args=("$@")
while [ $# -gt 0 ]; do
  case "$1" in -o) out="$2"; shift 2 ;; -p) cfg="$2"; shift 2 ;; *) shift ;; esac
done
printf '%s\\n' "${args[*]}" >> "$MMDC_LOG"
[ -n "$cfg" ] && cat "$cfg" > "$MMDC_LOG.cfg"
mode="${FAKE_MODE:-ok}"
if [ -n "${FAKE_FAIL_ON:-}" ]; then
  case "${args[*]}" in *"$FAKE_FAIL_ON"*) mode=root ;; *) mode=ok ;; esac
fi
case "$mode" in
  ok) echo "<svg/>" > "$out" ;;
  empty) : ;;
  root) echo "Generating single mermaid chart"
        echo "Error: Failed to launch the browser process!" >&2
        echo "[0101/000000.000:ERROR:zygote_host_impl_linux.cc(100)] ROOT_ERROR" >&2
        exit 1 ;;
esac
""".replace("ROOT_ERROR", ROOT_ERROR)


def _repo(tmp_path, sources=("flow",), fake=True):
    repo = tmp_path / "repo"
    (repo / "docs" / "diagrams").mkdir(parents=True)
    for name in sources:
        (repo / "docs" / "diagrams" / f"{name}.mmd").write_text("graph TD\n  a --> b\n",
                                                                 encoding="utf-8")
    shutil.copytree(os.path.join(TEMPLATES, "_verify"), repo / "_verify")
    (repo / "_verify" / "cases").mkdir()
    tools = tmp_path / "bin"
    tools.mkdir()
    if fake:
        (tools / "mmdc").write_text(FAKE_MMDC, encoding="utf-8", newline="\n")
        os.chmod(tools / "mmdc", 0o755)
    tmpdir = tmp_path / "tmp"
    tmpdir.mkdir()
    env = dict(os.environ, PATH=f"{tools}{os.pathsep}{os.environ['PATH']}",
               MMDC_LOG=str(tmp_path / "mmdc.log"), TMPDIR=str(tmpdir))
    return repo, env


def _run(argv, repo, env, **extra):
    return subprocess.run([_BASH, *argv], cwd=str(repo), env=dict(env, **extra),
                          capture_output=True, text=True, timeout=60, check=False)


def _case(repo, env, **extra):
    return _run([CASE.replace("\\", "/"), "--env", "dev"], repo, env, **extra)


def _add_case(repo, name, body):
    path = repo / "_verify" / "cases" / f"{name}.sh"
    path.write_text("#!/usr/bin/env bash\n" + body, encoding="utf-8", newline="\n")
    return path


def test_diagram_case_passes_a_no_sandbox_puppeteer_config(tmp_path):
    repo, env = _repo(tmp_path)
    proc = _case(repo, env)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "PASS flow" in proc.stdout
    calls = (tmp_path / "mmdc.log").read_text(encoding="utf-8")
    assert " -p " in f" {calls} ", calls
    cfg = json.loads((tmp_path / "mmdc.log.cfg").read_text(encoding="utf-8"))
    assert "--no-sandbox" in cfg["args"], cfg


def test_diagram_case_prints_mmdc_stderr_on_failure(tmp_path):
    repo, env = _repo(tmp_path)
    proc = _case(repo, env, FAKE_MODE="root")
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert "FAIL flow" in proc.stdout
    assert ROOT_ERROR in proc.stdout


def test_diagram_case_fails_on_an_empty_render(tmp_path):
    repo, env = _repo(tmp_path)
    proc = _case(repo, env, FAKE_MODE="empty")
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert "FAIL flow" in proc.stdout and "PASS flow" not in proc.stdout


def _path_without_mmdc(tmp_path):
    """A PATH holding only the tools the case uses, linked one by one, so a
    real mmdc installed on this host cannot be found."""
    tools = tmp_path / "bare"
    tools.mkdir()
    for tool in ("mktemp", "basename", "tail", "sed", "rm", "cat", "dirname"):
        real = shutil.which(tool)
        if real is None:
            pytest.skip(f"{tool} not on PATH")
        try:
            os.symlink(real, tools / tool)
        except OSError:
            pytest.skip("cannot create symlinks here")
    return str(tools)


def test_diagram_case_exits_77_without_mmdc(tmp_path):
    repo, env = _repo(tmp_path, fake=False)
    proc = _case(repo, env, PATH=_path_without_mmdc(tmp_path))
    assert proc.returncode == 77, proc.stdout + proc.stderr
    assert "npm install -g @mermaid-js/mermaid-cli" in proc.stderr


def test_diagram_case_fails_on_no_sources(tmp_path):
    repo, env = _repo(tmp_path, sources=())
    proc = _case(repo, env)
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert "no .mmd files" in proc.stdout


@pytest.mark.parametrize("mode", ["ok", "root"])
def test_diagram_case_cleans_up(tmp_path, mode):
    repo, env = _repo(tmp_path)
    before = sorted(os.listdir(repo / "docs" / "diagrams"))
    _case(repo, env, FAKE_MODE=mode)
    assert sorted(os.listdir(repo / "docs" / "diagrams")) == before
    assert not os.listdir(env["TMPDIR"]), os.listdir(env["TMPDIR"])


def test_run_all_shows_a_failing_case_tail_and_counts_a_skip(tmp_path):
    repo, env = _repo(tmp_path)
    _add_case(repo, "breaks", 'echo "line one"\necho "the last line" >&2\nexit 3\n')
    _add_case(repo, "absent", 'echo "no tool" >&2\nexit 77\n')
    proc = _run(["_verify/run-all.sh"], repo, env)
    out = proc.stdout
    assert proc.returncode == 1, out + proc.stderr
    lines = out.splitlines()
    fail = next(i for i, ln in enumerate(lines) if ln.startswith("FAIL breaks:"))
    assert "the last line" in "\n".join(lines[fail + 1:fail + 6]), out
    assert "SKIP absent (exit 77: tool or environment absent)" in out
    assert "1 skipped" in lines[-1], lines[-1]


def test_run_all_exit_77_alone_is_skip_not_pass(tmp_path):
    """A run whose only case exited 77 ran nothing: the runner exits 77 so
    crew's verify gate records SKIP, never a verified pass."""
    repo, env = _repo(tmp_path)
    _add_case(repo, "absent", "exit 77\n")
    proc = _run(["_verify/run-all.sh"], repo, env)
    assert proc.returncode == 77, proc.stdout + proc.stderr
    assert proc.stdout.splitlines()[-1].startswith("REGRESSION: 0 passed, 0 failed, 1 skipped")


def test_run_all_read_only_lines_and_production_refusal_unchanged(tmp_path):
    repo, env = _repo(tmp_path)
    _add_case(repo, "read-orders", "# readonly: yes\nexit 0\n")
    _add_case(repo, "write-order", "exit 0\n")
    proc = _run(["_verify/run-all.sh", "--env", "prod", "--read-only"], repo, env)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "PASS read-orders" in proc.stdout
    assert "SKIP write-order (not declared '# readonly: yes')" in proc.stdout
    refused = _run(["_verify/run-all.sh", "--env", "prod"], repo, env)
    assert refused.returncode == 1
    assert "refusing to run write checks against production" in refused.stderr


def _smoke_with(repo, checks):
    path = repo / "_verify" / "smoke.sh"
    text = path.read_text(encoding="utf-8")
    anchor = '# check "boots"'
    assert anchor in text
    path.write_text(text.replace(anchor, checks + "\n" + anchor), encoding="utf-8", newline="\n")


def test_smoke_shows_a_failing_check_tail_and_skips_77(tmp_path):
    repo, env = _repo(tmp_path)
    _smoke_with(repo, 'check "ok" true\n'
                      'check "absent" sh -c "exit 77"\n'
                      'check "breaks" sh -c "echo the cause >&2; exit 2"')
    proc = _run(["_verify/smoke.sh"], repo, env)
    lines = proc.stdout.splitlines()
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert lines[0].startswith("SMOKE target: dev -> "), lines[0]
    assert lines[-1].startswith("SMOKE: "), lines[-1]
    assert "SMOKE: 1/2 passed, 1 skipped" in lines[-1]
    assert "SKIP absent (exit 77: tool or environment absent)" in lines
    fail = next(i for i, ln in enumerate(lines) if ln.startswith("FAIL breaks:"))
    assert "the cause" in lines[fail + 1], lines


def test_smoke_exit_77_alone_is_skip_not_pass(tmp_path):
    repo, env = _repo(tmp_path)
    _smoke_with(repo, 'check "absent" sh -c "exit 77"')
    proc = _run(["_verify/smoke.sh"], repo, env)
    assert proc.returncode == 77, proc.stdout + proc.stderr


def test_smoke_a_pass_beside_a_77_skip_is_still_skip(tmp_path):
    """A pass does not cover for a check that never ran (fail closed)."""
    repo, env = _repo(tmp_path)
    _smoke_with(repo, 'check "ok" true\ncheck "absent" sh -c "exit 77"')
    proc = _run(["_verify/smoke.sh"], repo, env)
    assert proc.returncode == 77, proc.stdout + proc.stderr
    assert "PASS ok" in proc.stdout.splitlines()


def test_run_all_a_pass_beside_a_77_skip_is_still_skip(tmp_path):
    repo, env = _repo(tmp_path)
    _add_case(repo, "fine", "exit 0\n")
    _add_case(repo, "absent", "exit 77\n")
    proc = _run(["_verify/run-all.sh"], repo, env)
    assert proc.returncode == 77, proc.stdout + proc.stderr
    assert "PASS fine" in proc.stdout.splitlines()


def test_run_all_shows_the_mmdc_error(tmp_path):
    """The reported symptom: the diagram case run through run-all.sh with an
    mmdc that refuses to start as root. The cause must be in the log."""
    repo, env = _repo(tmp_path)
    shutil.copy(CASE, repo / "_verify" / "cases" / "diagrams-render.sh")
    proc = _run(["_verify/run-all.sh"], repo, env, FAKE_MODE="root")
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert "FAIL diagrams-render:" in proc.stdout
    assert ROOT_ERROR in proc.stdout, proc.stdout


def test_templates_are_lf_and_parse():
    for rel in (("cases", "diagrams-render.sh"), ("_verify", "smoke.sh"), ("_verify", "run-all.sh")):
        path = os.path.join(TEMPLATES, *rel)
        with open(path, "rb") as fh:
            assert b"\r\n" not in fh.read(), path
        proc = subprocess.run([_BASH, "-n", path.replace("\\", "/")], capture_output=True,
                              text=True, timeout=30, check=False)
        assert proc.returncode == 0, proc.stderr


def test_run_all_shows_an_early_diagram_failure_after_later_passes(tmp_path):
    """The first source fails and five later ones render: run-all.sh keeps only
    the last lines, and they must still carry mmdc's error."""
    repo, env = _repo(tmp_path, sources=("a-broken", "b1", "b2", "b3", "b4", "b5"))
    shutil.copy(CASE, repo / "_verify" / "cases" / "diagrams-render.sh")
    proc = _run(["_verify/run-all.sh"], repo, env, FAKE_FAIL_ON="a-broken")
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert ROOT_ERROR in proc.stdout, proc.stdout


@pytest.mark.parametrize("runner", ["run-all", "smoke"])
def test_a_background_child_does_not_hold_the_runner_open(tmp_path, runner):
    repo, env = _repo(tmp_path)
    if runner == "run-all":
        _add_case(repo, "spawns", "sleep 5 &\nexit 0\n")
    else:
        _smoke_with(repo, 'check "spawns" sh -c "sleep 5 & exit 0"')
    start = time.monotonic()
    proc = _run([f"_verify/{runner}.sh"], repo, env)
    took = time.monotonic() - start
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert took < 4, f"{runner}.sh took {took:.1f}s: it waited for the check's background child"


def test_diagram_case_rejects_env_without_a_value(tmp_path):
    repo, env = _repo(tmp_path)
    proc = subprocess.run([_BASH, CASE.replace("\\", "/"), "--env"], cwd=str(repo), env=env,
                          capture_output=True, text=True, timeout=10, check=False)
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert "--env needs a value" in proc.stdout


def test_diagram_case_fails_on_no_sources_even_without_mmdc(tmp_path):
    repo, env = _repo(tmp_path, sources=(), fake=False)
    proc = _case(repo, env, PATH=_path_without_mmdc(tmp_path))
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert "no .mmd files" in proc.stdout


def test_smoke_tail_survives_the_verify_gate_filter(tmp_path):
    """crew's verify gate, with no .crew/verify.json, relays only the lines of a
    failed smoke run that start `FAIL` or `SMOKE:` (verify-gate.sh, verify-gate.ps1).
    The cause must be among them."""
    repo, env = _repo(tmp_path)
    # The cause is printed by the check, not part of its command line, which
    # the FAIL line already shows.
    _add_case(repo, "breaks", 'echo "the cause" >&2\nexit 2\n')
    _smoke_with(repo, 'check "breaks" bash _verify/cases/breaks.sh')
    proc = _run(["_verify/smoke.sh"], repo, env)
    relayed = [ln for ln in proc.stdout.splitlines() if ln.startswith(("FAIL", "SMOKE:"))]
    assert any("the cause" in ln for ln in relayed), relayed


@pytest.mark.parametrize("runner", ["run-all", "smoke"])
def test_an_interrupted_runner_leaves_no_capture_file(tmp_path, runner):
    repo, env = _repo(tmp_path)
    marker = tmp_path / "started"
    body = f'touch "{marker.as_posix()}"\necho partial output\nsleep 2\nexit 0\n'
    _add_case(repo, "slow", body)
    if runner == "smoke":
        _smoke_with(repo, 'check "slow" bash _verify/cases/slow.sh')
    proc = subprocess.Popen([_BASH, f"_verify/{runner}.sh"], cwd=str(repo), env=env,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(100):
        if marker.exists():
            break
        time.sleep(0.05)
    proc.send_signal(signal.SIGTERM)
    proc.wait(timeout=20)
    assert proc.returncode != 0
    assert not os.listdir(env["TMPDIR"]), os.listdir(env["TMPDIR"])

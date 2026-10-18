"""`crew_codex_wrapper.py` and the shipped `templates/codex-review.sh` (L-0813).

Every fixture points CLAUDE_CONFIG_DIR at a tmp dir and disables the /root
fallback, so no test reads or writes the machine's real config. The wrapper is
run for real in bash against a stub `codex` on PATH.
"""
import os
import shutil
import stat
import subprocess
import sys

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import crew_codex_wrapper as cw

SCRIPT = os.path.join(os.path.dirname(cw.__file__), "crew_codex_wrapper.py")
BASH = shutil.which("bash")
needs_bash = pytest.mark.skipif(BASH is None or os.name == "nt", reason="the wrapper is bash")


@pytest.fixture(name="env")
def _env(tmp_path, monkeypatch):
    config = tmp_path / "config"
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(config))
    monkeypatch.setenv("CODEX_WRAPPER_FALLBACK", "")
    monkeypatch.delenv("CODEX_WRAPPER", raising=False)
    (tmp_path / "bin").mkdir()
    monkeypatch.setattr(cw.crew_common, "resolve_tool", lambda name: None)
    return config


def _put_codex(monkeypatch):
    monkeypatch.setattr(cw.crew_common, "resolve_tool", lambda name: "/usr/bin/codex")


def _wrapper_path(config):
    return config / "hooks" / "codex-review.sh"


def _place(config, text=None, mode=0o755):
    path = _wrapper_path(config)
    path.parent.mkdir(parents=True, exist_ok=True)
    if text is None:
        shutil.copyfile(cw.SHIPPED, path)
    else:
        path.write_bytes(text)
    path.chmod(mode)
    return path


def test_check_missing_names_every_path_when_codex_is_installed(env, monkeypatch):
    _put_codex(monkeypatch)
    monkeypatch.setenv("CODEX_WRAPPER_FALLBACK", "/nowhere/codex-review.sh")

    info = cw.measure()

    assert info["state"] == "missing"
    assert str(_wrapper_path(env)) in info["detail"] and "/nowhere/codex-review.sh" in info["detail"]
    assert "77" in info["detail"] and "install" in info["detail"]
    assert cw.EXIT["missing"] == 2


def test_check_not_applicable_when_neither_wrapper_nor_codex(env):
    info = cw.measure()

    assert info["state"] == "n/a"
    assert "codex is not on PATH" in info["detail"]


def test_check_ok_only_for_the_shipped_bytes(env):
    _place(env)

    assert cw.measure()["state"] == "ok"


def test_check_present_for_a_different_executable_file(env):
    _place(env, b"#!/bin/sh\necho mine\n")

    info = cw.measure()

    assert info["state"] == "present"
    assert "left as is" in info["detail"]


def test_check_not_executable_is_its_own_state(env):
    _place(env, mode=0o644)

    info = cw.measure()

    assert info["state"] == "not-executable"
    assert cw.EXIT["not-executable"] == 2


@pytest.mark.skipif(os.name == "nt" or os.geteuid() == 0, reason="root ignores directory permissions")
def test_check_unknown_when_the_path_cannot_be_examined(env):
    path = _place(env)
    hooks = path.parent
    hooks.chmod(0)
    try:
        info = cw.measure()
    finally:
        hooks.chmod(0o755)

    assert info["state"] == "unknown"
    assert cw.EXIT["unknown"] == 4


def test_check_unknown_survives_a_missing_codex(env, monkeypatch):
    monkeypatch.setattr(cw, "_probe", lambda path: ("unknown", "PermissionError: denied"))

    info = cw.measure()

    assert info["state"] == "unknown"
    assert "denied" in info["detail"]


def test_check_direct_when_the_caller_opted_out_of_the_wrapper(env, monkeypatch):
    monkeypatch.setenv("CODEX_WRAPPER", "none")

    assert cw.measure()["state"] == "direct"


def test_check_explicit_wrapper_must_be_an_executable_file(env, tmp_path, monkeypatch):
    mine = tmp_path / "mine.sh"
    mine.write_text("#!/bin/sh\n", encoding="utf-8")
    mine.chmod(0o644)
    monkeypatch.setenv("CODEX_WRAPPER", str(mine))

    assert cw.measure()["state"] == "not-executable"

    mine.chmod(0o755)

    assert cw.measure()["state"] == "present"


def test_install_writes_executable_copy_and_is_idempotent(env):
    code, message = cw.install()
    again_code, again = cw.install()

    assert code == 0 and message.startswith("installed:")
    assert again_code == 0 and again.startswith("already installed")
    assert cw.measure()["state"] == "ok"
    assert _wrapper_path(env).stat().st_mode & stat.S_IXUSR


def test_install_repairs_a_lost_executable_bit(env):
    path = _place(env, mode=0o644)

    code, message = cw.install()

    assert code == 0 and "executable bit" in message
    assert os.access(path, os.X_OK)


def test_install_refuses_to_overwrite_a_different_file(env):
    path = _place(env, b"#!/bin/sh\necho mine\n")

    code, message = cw.install()

    assert code == 3 and "--force" in message
    assert path.read_bytes() == b"#!/bin/sh\necho mine\n"


def test_install_force_keeps_the_old_file_as_a_backup(env):
    path = _place(env, b"#!/bin/sh\necho mine\n")

    code, message = cw.install(force=True)

    backups = list(path.parent.glob("codex-review.sh.bak-*"))
    assert code == 0 and "previous file kept" in message
    assert len(backups) == 1 and backups[0].read_bytes() == b"#!/bin/sh\necho mine\n"
    assert cw.measure()["state"] == "ok"


def test_cli_exit_codes_follow_the_state(env, tmp_path, monkeypatch):
    (tmp_path / "bin" / "codex").write_text("#!/bin/sh\n", encoding="utf-8")
    (tmp_path / "bin" / "codex").chmod(0o755)
    monkeypatch.setenv("PATH", str(tmp_path / "bin") + os.pathsep + os.environ["PATH"])

    missing = subprocess.run([sys.executable, SCRIPT, "check"], capture_output=True, text=True, check=False)
    installed = subprocess.run([sys.executable, SCRIPT, "install"], capture_output=True, text=True, check=False)
    ok = subprocess.run([sys.executable, SCRIPT, "check"], capture_output=True, text=True, check=False)

    assert missing.returncode == 2 and "MISSING" in missing.stdout
    assert installed.returncode == 0
    assert ok.returncode == 0 and ok.stdout.startswith("codex-wrapper ok (")


# --- the shipped wrapper, run for real against a stub codex ----------------------------

STUB = r'''#!/bin/sh
# stub codex: records stdin, argv and a per-run counter; behaviour set by STUB_MODE
dir="$STUB_DIR"
n=$(cat "$dir/count" 2>/dev/null || echo 0); n=$((n + 1)); echo $n > "$dir/count"
echo "$@" > "$dir/argv.$n"
cat > "$dir/stdin.$n"
out=""
while [ $# -gt 0 ]; do [ "$1" = "-o" ] && out=$2; shift; done
case "$STUB_MODE" in
  ok)        echo "model: gpt-test-1" >&2; echo "reasoning effort: high" >&2; echo "final answer" > "$out" ;;
  nohdr)     echo "final answer" > "$out" ;;
  hang-once) if [ "$n" = 1 ]; then sleep 30; fi; echo "model: gpt-test-1" >&2; echo "reasoning effort: high" >&2; echo "second try" > "$out" ;;
  fail)      echo "boom" >&2; exit 7 ;;
  empty)     : > "$out" ;;
  stale)     echo "stale" > "$out"; touch -d '2001-01-01' "$out" ;;
esac
'''


def _run_wrapper(tmp_path, monkeypatch, mode, prompt="review this\n", extra=None, args=None):
    stubdir = tmp_path / "stub"
    stubdir.mkdir(exist_ok=True)
    codex = tmp_path / "bin" / "codex"
    codex.write_text(STUB, encoding="utf-8")
    codex.chmod(0o755)
    promptfile = tmp_path / "prompt.md"
    promptfile.write_text(prompt, encoding="utf-8")
    out = tmp_path / "out" / "review.txt"
    env = dict(os.environ, STUB_DIR=str(stubdir), STUB_MODE=mode, CODEX_REVIEW_LOG=str(tmp_path / "w.log"),
               PATH=str(tmp_path / "bin") + os.pathsep + os.environ["PATH"], **(extra or {}))
    cmd = [BASH, cw.SHIPPED] + (args if args is not None else [str(promptfile), str(out), str(tmp_path)])
    done = subprocess.run(cmd, capture_output=True, text=True, env=env, check=False, timeout=60,
                          stdin=subprocess.DEVNULL)
    return done, out, stubdir


@needs_bash
def test_wrapper_success_writes_output_and_reports_model_and_effort(env, tmp_path, monkeypatch):
    done, out, stub = _run_wrapper(tmp_path, monkeypatch, "ok")

    assert done.returncode == 0
    assert out.read_text(encoding="utf-8") == "final answer\n"
    assert done.stderr.strip().splitlines()[-1] == (
        f"codex-review: OK - final message 13 bytes -> {out} (model: gpt-test-1, reasoning effort: high, attempt 1)")
    assert (stub / "stdin.1").read_text(encoding="utf-8") == "review this\n"


@needs_bash
def test_wrapper_passes_read_only_and_skips_the_git_check(env, tmp_path, monkeypatch):
    done, _, stub = _run_wrapper(tmp_path, monkeypatch, "ok")

    argv = (stub / "argv.1").read_text(encoding="utf-8").split()
    assert done.returncode == 0
    assert "--skip-git-repo-check" in argv and argv[argv.index("--sandbox") + 1] == "read-only"
    assert argv[-1] == "-"


@needs_bash
def test_wrapper_never_invents_a_model_when_codex_printed_none(env, tmp_path, monkeypatch):
    done, out, _ = _run_wrapper(tmp_path, monkeypatch, "nohdr")

    assert done.returncode == 0
    assert done.stderr.strip().splitlines()[-1] == f"codex-review: OK - final message 13 bytes -> {out}"
    assert "model:" not in done.stderr


@needs_bash
@pytest.mark.skipif(shutil.which("timeout") is None, reason="needs timeout(1)")
def test_wrapper_kills_a_hung_attempt_and_restarts_once(env, tmp_path, monkeypatch):
    done, out, stub = _run_wrapper(tmp_path, monkeypatch, "hang-once", extra={"CODEX_REVIEW_TIMEOUT": "1"})

    assert done.returncode == 0
    assert out.read_text(encoding="utf-8") == "second try\n"
    assert (stub / "count").read_text(encoding="utf-8").strip() == "2"
    assert "attempt 2)" in done.stderr and "hit the 1s cap" in done.stderr


@needs_bash
@pytest.mark.parametrize("mode", ["fail", "empty", "stale"])
def test_wrapper_failure_exits_3_after_two_attempts_and_leaves_no_output(env, tmp_path, monkeypatch, mode):
    done, out, stub = _run_wrapper(tmp_path, monkeypatch, mode)

    assert done.returncode == 3
    assert not out.exists()
    assert (stub / "count").read_text(encoding="utf-8").strip() == "2"
    assert "FAILED" in done.stderr


@needs_bash
def test_wrapper_removes_a_stale_output_file_before_running(env, tmp_path, monkeypatch):
    (tmp_path / "out").mkdir()
    (tmp_path / "out" / "review.txt").write_text("OLD VERDICT\n", encoding="utf-8")

    done, _, _ = _run_wrapper(tmp_path, monkeypatch, "fail")

    assert done.returncode == 3
    assert not (tmp_path / "out" / "review.txt").exists()


@needs_bash
@pytest.mark.parametrize("args", [[], ["only-one"], ["a", "b", "c", "d"]])
def test_wrapper_bad_argument_count_exits_2(env, tmp_path, monkeypatch, args):
    done, _, _ = _run_wrapper(tmp_path, monkeypatch, "ok", args=args)

    assert done.returncode == 2 and "usage" in done.stderr


@needs_bash
def test_wrapper_missing_or_empty_prompt_exits_2(env, tmp_path, monkeypatch):
    missing, _, _ = _run_wrapper(tmp_path, monkeypatch, "ok", args=[str(tmp_path / "nope.md"), str(tmp_path / "o")])
    empty, _, _ = _run_wrapper(tmp_path, monkeypatch, "ok", prompt="")

    assert missing.returncode == 2 and "not readable" in missing.stderr
    assert empty.returncode == 2 and "empty" in empty.stderr


def test_shipped_wrapper_is_lf_only_and_has_a_shebang():
    with open(cw.SHIPPED, "rb") as handle:
        data = handle.read()

    assert data.startswith(b"#!/usr/bin/env bash\n")
    assert b"\r" not in data

"""completion_audit.py and its .sh / .ps1 wrappers: the Stop-time whole-tree
scope audit, plus the `--check` form `/crew:done` calls. A BLOCKING hook, so
must-block and must-allow run through the module, bash and PowerShell (pwsh
with OS=Windows_NT; skipped, and said so, without pwsh).

The case the edit guard cannot see is the reason this exists: a file written
by the shell never reaches PreToolUse.
"""
import json
import os
import pathlib
import subprocess
import sys

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import completion_audit
import crew_fixtures
import crew_ticket
from review_fixtures import git
from scope_fixtures import (FLAVOUR_MATRIX, FLAVOURS, PWSH, SCRIPTS, make_repo, make_ticket,
                            needs_pwsh, ready, run_hook, stop)

# Per-shell parity sample, run by default: the FLAVOURS tests (a block, an
# allow, mode off, report mode's message on stdout), and a sample of each
# wrapper-only table below. Every other `sh`/`ps1` case is `slow`
# (FLAVOUR_MATRIX, crew_fixtures.sample_params; see conftest.py).

_AUDIT = os.path.join(SCRIPTS, "completion_audit.py")


def _audit(flavour, root, payload):
    return run_hook(flavour, "completion_audit", payload, root)


@pytest.fixture(name="repo")
def _repo(tmp_path):
    return make_repo(tmp_path, mode="block")


# --- must-block -----------------------------------------------------------------

@pytest.mark.parametrize("flavour", FLAVOURS)
def test_a_shell_made_out_of_scope_file_blocks_the_stop(flavour, repo):
    ready(repo)
    (repo / "other" / "made-by-sed.py").write_text("y = 2\n", encoding="utf-8")

    code, out, err = _audit(flavour, repo, stop(repo))

    assert (code, out, "other/made-by-sed.py" in err) == (2, "", True)
    assert len(err.strip().splitlines()) <= 6


@pytest.mark.parametrize("flavour", FLAVOUR_MATRIX)
def test_a_committed_out_of_scope_change_blocks_the_stop(flavour, repo):
    ready(repo)
    (repo / "other" / "keep.py").write_text("x = 2\n", encoding="utf-8")
    git(repo, "commit", "-qam", "sneak")

    code, _, err = _audit(flavour, repo, stop(repo))

    assert (code, "other/keep.py" in err) == (2, True)


@pytest.mark.parametrize("flavour", FLAVOUR_MATRIX)
def test_a_rename_out_of_scope_blocks_the_stop(flavour, repo):
    ready(repo)
    git(repo, "mv", "src/app.py", "other/app.py")

    code, _, err = _audit(flavour, repo, stop(repo))

    assert (code, "other/app.py" in err) == (2, True)


@pytest.mark.parametrize("flavour", FLAVOUR_MATRIX)
def test_a_rename_from_out_of_scope_into_scope_blocks_too(flavour, repo):
    ready(repo)
    git(repo, "mv", "other/keep.py", "src/keep.py")

    code, _, err = _audit(flavour, repo, stop(repo))

    assert (code, "other/keep.py" in err) == (2, True)


@pytest.mark.parametrize("flavour", FLAVOUR_MATRIX)
def test_changes_under_a_stale_approval_block(flavour, repo):
    ready(repo)
    (repo / "src" / "app.py").write_text("x = 3\n", encoding="utf-8")
    spec = repo / ".work" / "tickets" / "T-1" / "spec.md"
    spec.write_text(spec.read_text(encoding="utf-8").replace("`src/**`", "`**`"),
                    encoding="utf-8")

    code, _, err = _audit(flavour, repo, stop(repo))

    assert (code, "not approved" in err) == (2, True)


def test_a_staged_out_of_scope_deletion_blocks(repo):
    ready(repo)
    git(repo, "rm", "-q", "other/keep.py")

    code, _, err = _audit("module", repo, stop(repo))

    assert (code, "other/keep.py" in err) == (2, True)


@pytest.mark.parametrize("flavour", FLAVOUR_MATRIX)
def test_a_cli_approval_does_not_make_touch_approved(flavour, repo):
    make_ticket(repo)
    crew_ticket.approve(str(repo), "T-1", by="session")
    (repo / "src" / "app.py").write_text("x = 2\n", encoding="utf-8")

    code, _, err = _audit(flavour, repo, stop(repo))

    assert (code, "/crew:approve T-1" in err) == (2, True)


@pytest.mark.parametrize("flavour", FLAVOUR_MATRIX)
def test_a_broken_active_ticket_pointer_blocks_the_stop(flavour, repo):
    pointer = pathlib.Path(crew_ticket.common_dir(str(repo)), "crew", "active-ticket")
    pointer.parent.mkdir(parents=True, exist_ok=True)
    pointer.write_text(json.dumps({crew_ticket.toplevel(str(repo)): "T-404"}), encoding="utf-8")

    code, _, err = _audit(flavour, repo, stop(repo))

    assert (code, "pointer is broken" in err) == (2, True)


@pytest.mark.parametrize("flavour", FLAVOUR_MATRIX)
def test_a_filename_with_newlines_cannot_add_lines(flavour, repo):
    ready(repo)
    for number in range(12):
        (repo / "other" / f"a{number}\nb\nc.py").write_text("y\n", encoding="utf-8")

    code, _, err = _audit(flavour, repo, stop(repo))

    assert (code, len(err.splitlines()) <= 6, "\\x0a" in err) == (2, True, True)


def test_physical_caps_lines_whatever_they_contain():
    assert len(completion_audit.physical(["a\nb\nc"] * 4)) == 6


def test_the_audit_lists_paths_without_building_the_review_bundle(repo, monkeypatch):
    import review_patch  # pylint: disable=import-outside-toplevel
    ready(repo)
    (repo / "other" / "made-by-sed.py").write_text("y = 2\n", encoding="utf-8")

    def no_bundle(*_args, **_kwargs):
        raise AssertionError("the Stop audit built the review bundle")

    monkeypatch.setattr(review_patch, "compute", no_bundle)

    ok, lines = completion_audit.audit(str(repo), "T-1")

    assert (ok, "other/made-by-sed.py" in lines[1]) == (False, True)


@pytest.mark.parametrize("shell", ["sh", "ps1"])
@pytest.mark.parametrize("spacing", crew_fixtures.sample_params([
    pytest.param('"stop_hook_active":  true', id="two-spaces"),
    pytest.param('"stop_hook_active"\n:\ttrue', id="newline-tab"),
    pytest.param('"stop_hook_active" :\r\n true', id="crlf")], {"newline-tab"}))
def test_stop_hook_active_is_seen_in_any_json_whitespace_even_when_python_crashes(
        tmp_path, shell, spacing):
    if shell == "ps1" and PWSH is None:
        pytest.skip("pwsh not installed - the .ps1 flavour was NOT run")
    root = make_repo(tmp_path, mode="block")
    ready(root)
    raw = ('{"hook_event_name": "Stop", ' + spacing + ', "cwd": ' + json.dumps(str(root))
           + '}').encode()

    done = _wrapper(tmp_path, root, "completion-audit", shell, raw)

    assert done.returncode == 0, done.stderr


@pytest.mark.parametrize("shell", ["sh", "ps1"])
def test_a_crashed_python_never_blocks_two_stops_in_a_row(tmp_path, shell):
    if shell == "ps1" and PWSH is None:
        pytest.skip("pwsh not installed - the .ps1 flavour was NOT run")
    root = make_repo(tmp_path, mode="block")
    ready(root)
    raw = json.dumps(dict(stop(root), session_id=f"loop-{shell}")).encode()

    codes = [_wrapper(tmp_path, root, "completion-audit", shell, raw).returncode
             for _ in range(3)]

    assert codes == [2, 0, 2]


# --- must-allow -------------------------------------------------------------------

@pytest.mark.parametrize("flavour", FLAVOURS)
def test_in_scope_changes_pass_silently(flavour, repo):
    ready(repo)
    (repo / "src" / "app.py").write_text("x = 2\n", encoding="utf-8")
    (repo / "src" / "new.py").write_text("n = 1\n", encoding="utf-8")

    code, out, err = _audit(flavour, repo, stop(repo))

    assert (code, out, err) == (0, "", "")


@pytest.mark.parametrize("flavour", FLAVOUR_MATRIX)
def test_stop_hook_active_never_re_blocks(flavour, repo):
    ready(repo)
    (repo / "other" / "made-by-sed.py").write_text("y = 2\n", encoding="utf-8")

    code, out, err = _audit(flavour, repo, stop(repo, active=True))

    assert (code, out, err) == (0, "", "")


@pytest.mark.parametrize("flavour", FLAVOURS)
def test_mode_off_does_not_audit(flavour, tmp_path):
    root = make_repo(tmp_path, mode="off")
    ready(root)
    (root / "other" / "made-by-sed.py").write_text("y = 2\n", encoding="utf-8")

    code, out, err = _audit(flavour, root, stop(root))

    assert (code, out, err) == (0, "", "")


@pytest.mark.parametrize("flavour", FLAVOURS)
def test_report_mode_allows_the_stop_and_says_so(flavour, tmp_path):
    root = make_repo(tmp_path, mode="report")
    ready(root)
    (root / "other" / "made-by-sed.py").write_text("y = 2\n", encoding="utf-8")

    code, out, _ = _audit(flavour, root, stop(root))

    assert code == 0
    assert "other/made-by-sed.py" in json.loads(out)["systemMessage"]


@pytest.mark.parametrize("flavour", FLAVOUR_MATRIX)
def test_no_active_ticket_is_not_audited(flavour, repo):
    make_ticket(repo, activate=False)
    (repo / "other" / "made-by-sed.py").write_text("y = 2\n", encoding="utf-8")

    code, _, _ = _audit(flavour, repo, stop(repo))

    assert code == 0


def test_the_tickets_own_directory_is_not_a_violation(repo):
    ready(repo)
    (repo / ".work" / "tickets" / "T-1" / "review.json").write_text("{}", encoding="utf-8")

    code, _, _ = _audit("module", repo, stop(repo))

    assert code == 0


def test_a_clean_tree_passes_even_without_approval(repo):
    make_ticket(repo)

    code, _, _ = _audit("module", repo, stop(repo))

    assert code == 0


# --- the /crew:done form -------------------------------------------------------------

def _check(root, ticket="T-1"):
    return subprocess.run([sys.executable, _AUDIT, "--check", "--ticket", ticket,
                           "--root", str(root)], capture_output=True, text=True,
                          check=False, stdin=subprocess.DEVNULL)


def test_check_passes_on_in_scope_changes(repo):
    ready(repo)
    (repo / "src" / "app.py").write_text("x = 2\n", encoding="utf-8")

    assert _check(repo).returncode == 0


def test_check_refuses_out_of_scope_changes_whatever_the_mode(tmp_path):
    root = make_repo(tmp_path, mode="off")
    ready(root)
    (root / "other" / "keep.py").write_text("x = 2\n", encoding="utf-8")

    done = _check(root)

    assert (done.returncode, "other/keep.py" in done.stdout) == (1, True)


def test_check_refuses_a_bad_ticket_id(repo):
    assert _check(repo, "../x").returncode == 1


def test_check_is_a_failure_when_the_tree_cannot_be_diffed(tmp_path):
    plain = tmp_path / "plain"
    plain.mkdir()

    assert _check(plain).returncode == 1


def test_audit_diffs_from_the_tickets_recorded_base(repo):
    (repo / "other" / "keep.py").write_text("x = 5\n", encoding="utf-8")
    git(repo, "commit", "-qam", "before the ticket")
    ready(repo)

    ok, _ = completion_audit.audit(str(repo), "T-1")

    assert ok is True and crew_ticket.status(str(repo), "T-1")["status"] == "approved"


# --- the wrappers, both hooks ---------------------------------------------------------

_WRAPPERS = ("scope-guard", "completion-audit")


def _resolver(path):
    src = pathlib.Path(path).read_text(encoding="utf-8")
    start = src.index("function Resolve-CrewPython {")
    return src[start:src.index("\n}\n", start) + 3]


@pytest.mark.parametrize("stem", _WRAPPERS)
def test_the_powershell_resolver_is_byte_for_byte_role_write_guards(stem):
    assert _resolver(os.path.join(SCRIPTS, stem + ".ps1")) == \
        _resolver(os.path.join(SCRIPTS, "role-write-guard.ps1"))


@pytest.mark.parametrize("stem", _WRAPPERS)
def test_the_flavour_guard_is_the_first_executable_statement(stem):
    lines = pathlib.Path(SCRIPTS, stem + ".ps1").read_text(encoding="utf-8").splitlines()
    code = [l for l in lines if l.strip() and not l.lstrip().startswith("#")]

    assert code[code.index(")") + 1] == "if ($env:OS -ne 'Windows_NT') { exit 0 }"


@pytest.mark.parametrize("name", ["scope-guard.sh", "scope-guard.ps1", "scope_guard.py",
                                  "completion-audit.sh", "completion-audit.ps1",
                                  "completion_audit.py", "crew_ticket.py"])
def test_every_new_file_is_lf_only(name):
    assert b"\r" not in pathlib.Path(SCRIPTS, name).read_bytes()


@needs_pwsh
@pytest.mark.parametrize("stem", _WRAPPERS)
def test_the_powershell_flavour_stands_down_off_windows(stem, repo):
    ready(repo)
    (repo / "other" / "made-by-sed.py").write_text("y = 2\n", encoding="utf-8")
    env = dict(os.environ, CLAUDE_PROJECT_DIR=str(repo))
    env.pop("OS", None)
    payload = stop(repo) if stem == "completion-audit" else {
        "tool_name": "Write", "tool_input": {"file_path": str(repo / "other" / "x.py")},
        "cwd": str(repo)}

    done = subprocess.run([PWSH, "-NoProfile", "-File", os.path.join(SCRIPTS, stem + ".ps1")],
                          input=json.dumps(payload).encode(), cwd=str(repo),
                          capture_output=True, env=env, check=False, timeout=120)

    assert (done.returncode, done.stdout, done.stderr) == (0, b"", b"")


def _broken_python(tmp_path):
    """A `python3` that passes the interpreter probe and then crashes. The
    .ps1 probe demands a JSON proof (burn-in FAIL 3), so it answers that one
    with the JSON a real CPython 3.12 would print; bash's probe gets the bare
    path it asks for."""
    folder = tmp_path / "fakebin"
    folder.mkdir()
    fake = folder / "python3"
    fake.write_text('#!/bin/sh\nif [ "$1" = "-c" ]; then\n  case "$2" in\n'
                    '    *json.dumps*) printf \'{"v": [3, 12], "exe": "%s", "impl": "cpython"}\\n\' "$0" ;;\n'
                    '    *) echo "$0" ;;\n  esac\n  exit 0\nfi\nexit 1\n',
                    encoding="utf-8", newline="\n")
    fake.chmod(0o755)
    return folder


def _no_python(tmp_path):
    """A PATH folder with the tools the bash wrappers use and no python at all,
    so `crew_py_strict` finds nothing."""
    folder = tmp_path / "nopy"
    folder.mkdir()
    for tool in ("cat", "dirname", "tr", "sed", "grep", "wc", "cut", "cksum", "rm", "date"):
        for base in ("/usr/bin", "/bin"):
            if os.path.exists(os.path.join(base, tool)):
                os.symlink(os.path.join(base, tool), folder / tool)
                break
    return folder


def _wrapper(tmp_path, root, stem, shell, raw, python="crashed"):
    """Run one wrapper with a `python3` that passes the probe and crashes, or
    (`python="missing"`) with no python on PATH at all."""
    if python == "missing":
        path = str(_no_python(tmp_path))
    else:
        fake = tmp_path / "fakebin"
        folder = fake if fake.is_dir() else _broken_python(tmp_path)
        path = os.pathsep.join([str(folder), "/usr/bin", "/bin"])
    env = dict(os.environ, CLAUDE_PROJECT_DIR=str(root), OS="Windows_NT", PATH=path)
    cmd = ([PWSH, "-NoProfile", "-File", os.path.join(SCRIPTS, stem + ".ps1")]
           if shell == "ps1" else ["/bin/bash", os.path.join(SCRIPTS, stem + ".sh")])
    return subprocess.run(cmd, input=raw, cwd=str(root), capture_output=True, env=env,
                          check=False, timeout=120)


# Every shape the no-python readers cannot PROVE is off must fail closed;
# python itself reads a corrupt config or an unknown mode as block. bash has no
# JSON parser, so from bash ANY present config is unprovable (expected 2);
# PowerShell proves "off" with System.Text.Json. Columns: config, bash, pwsh.
_CONFIGS = [
    pytest.param('{"scope": {"mode": "block"}}', 2, 2, id="block"),
    pytest.param('{"scope": {"mode": "auto"}}', 2, 2, id="auto"),
    pytest.param('{"scope": {"mode": "report"}}', 2, 2, id="report"),
    pytest.param('{"scope": {"mode": "bogus"}}', 2, 2, id="bogus"),
    pytest.param('{"scope": {"mode": "off"}', 2, 2, id="unbalanced"),
    pytest.param('{"scope": {"mode": "off"}} trailing', 2, 2, id="trailing"),
    pytest.param('{"scope": {"mode": "off"}, "x": {"scope": 1}}', 2, 2, id="two-scopes"),
    pytest.param('{"scope": {"mode": "off", "mode": "block"}}', 2, 2, id="two-modes"),
    pytest.param('{"scope": "off"}', 2, 2, id="scope-not-object"),
    pytest.param('{"install": {}}', 2, 2, id="no-scope-key"),
    pytest.param('{', 2, 2, id="corrupt"),
    pytest.param('{"scope":{"mode":"off"},}', 2, 2, id="trailing-comma"),
    pytest.param('{"scope":{"mode":"off",}}', 2, 2, id="inner-trailing-comma"),
    pytest.param('{/* c */"scope":{"mode":"off"}}', 2, 2, id="comment"),
    pytest.param("{'scope':{'mode':'off'}}", 2, 2, id="single-quotes"),
    pytest.param('{scope:{mode:"off"}}', 2, 2, id="bare-keys"),
    pytest.param('{"scope":{"mode":"off"},"sc\\u006fpe":{"mode":"block"}}', 2, 2,
                 id="escaped-duplicate-scope"),
    pytest.param('{"scope":{"mode":["off"]}}', 2, 2, id="mode-not-string"),
    pytest.param('{"scope": {"mode": "off"}}', 2, 0, id="off"),
    pytest.param('\ufeff{\n  "scope": {\n    "mode": "off",\n    "allowCliApproval": false\n'
                 '  }\n}\n', 2, 0, id="off-template-bom"),
    pytest.param(None, 0, 0, id="absent"),
]
# By default: `off` (the one row bash and pwsh answer differently) and
# `corrupt` (fails closed in both); the other rows are `slow`.
_CONFIGS_SHELL = crew_fixtures.sample_params(_CONFIGS, {"off", "corrupt"})


def _run_config(tmp_path, stem, shell, config, python):
    root = make_repo(tmp_path, mode=None)
    config_path = root / ".crew" / "config.json"
    if config is None:
        config_path.unlink(missing_ok=True)
    else:
        config_path.write_text(config, encoding="utf-8")
    payload = stop(root) if stem == "completion-audit" else {
        "tool_name": "Write", "tool_input": {"file_path": str(root / "src" / "app.py")},
        "cwd": str(root)}
    return _wrapper(tmp_path, root, stem, shell, json.dumps(payload).encode(), python)


@pytest.mark.parametrize("stem", _WRAPPERS)
@pytest.mark.parametrize("shell", ["sh", "ps1"])
@pytest.mark.parametrize("config,sh_expected,ps1_expected", _CONFIGS_SHELL)
def test_a_crashed_python_fails_closed_unless_scope_is_provably_off(tmp_path, stem, shell,
                                                                    config, sh_expected,
                                                                    ps1_expected):
    if shell == "ps1" and PWSH is None:
        pytest.skip("pwsh not installed - the .ps1 flavour was NOT run")

    done = _run_config(tmp_path, stem, shell, config, "crashed")

    assert done.returncode == (sh_expected if shell == "sh" else ps1_expected), done.stderr


@pytest.mark.parametrize("stem", _WRAPPERS)
@pytest.mark.parametrize("shell", ["sh", "ps1"])
@pytest.mark.parametrize("config,sh_expected,ps1_expected", _CONFIGS_SHELL)
def test_no_python_fails_closed_unless_scope_is_provably_off(tmp_path, stem, shell, config,
                                                             sh_expected, ps1_expected):
    if shell == "ps1" and PWSH is None:
        pytest.skip("pwsh not installed - the .ps1 flavour was NOT run")

    done = _run_config(tmp_path, stem, shell, config, "missing")

    assert done.returncode == (sh_expected if shell == "sh" else ps1_expected), done.stderr


@pytest.mark.parametrize("stem", _WRAPPERS)
@pytest.mark.parametrize("shell", ["sh", "ps1"])
@pytest.mark.parametrize("mode,sh_expected,ps1_expected",
                         crew_fixtures.sample_params(
                             [pytest.param("block", 2, 2, id="block-2-2"),
                              pytest.param("auto", 2, 2, id="auto-2-2"),
                              pytest.param("off", 2, 0, id="off-2-0")], {"off-2-0"}))
def test_a_crashed_python_fails_closed_only_where_scope_is_armed(tmp_path, stem, shell,
                                                                 mode, sh_expected,
                                                                 ps1_expected):
    if shell == "ps1" and PWSH is None:
        pytest.skip("pwsh not installed - the .ps1 flavour was NOT run")
    root = make_repo(tmp_path, mode=mode)
    ready(root)
    payload = stop(root) if stem == "completion-audit" else {
        "tool_name": "Write", "tool_input": {"file_path": str(root / "src" / "app.py")},
        "cwd": str(root)}

    done = _wrapper(tmp_path, root, stem, shell, json.dumps(payload).encode())

    assert done.returncode == (sh_expected if shell == "sh" else ps1_expected), done.stderr


def _sh_function(stem, name):
    src = pathlib.Path(SCRIPTS, stem + ".sh").read_text(encoding="utf-8")
    start = src.index(name + "() {")
    return src[start:src.index("\n}\n", start) + 3]


def _ps_function(stem, name):
    src = pathlib.Path(SCRIPTS, stem + ".ps1").read_text(encoding="utf-8")
    start = src.index(f"function {name} {{")
    return src[start:src.index("\n}\n", start) + 3]


def test_the_provably_off_readers_are_byte_for_byte_twins():
    assert _sh_function("scope-guard", "_scope_provably_off") == \
        _sh_function("completion-audit", "_scope_provably_off")
    assert _ps_function("scope-guard", "Test-ScopeProvablyOff") == \
        _ps_function("completion-audit", "Test-ScopeProvablyOff")

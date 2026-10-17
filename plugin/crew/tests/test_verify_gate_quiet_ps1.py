"""L-0796: verify-gate.ps1 is quiet the same way verify-gate.sh is.

Two checks. A static one that needs no PowerShell: the two flavours demote the
same informational sites and carry the same notice allowlist, so a site added to
one cannot silently stay noisy (or be hidden) in the other. And a behavioural
one: the same fixture through both flavours gives the same verdict line, the
same failure span and the same unchanged-since-last-Stop line.

The behavioural run drives `pwsh` on a host that is not Windows by setting
OS=Windows_NT, which is all the flavour guard looks at. That is a simulation of
the native flavour, not a native Windows run; the PR names it as such. It is
skipped, never passed, when pwsh does not resolve.
"""
import json
import os
import re
import shutil
import subprocess

import pytest

import crew_fixtures

import context  # noqa: F401  pylint: disable=unused-import

_SCRIPTS = os.path.join(context._ROOT, "hooks", "scripts")  # pylint: disable=protected-access
_SH = os.path.join(_SCRIPTS, "verify-gate.sh")
_PS1 = os.path.join(_SCRIPTS, "verify-gate.ps1")
_BASH = crew_fixtures.resolve_bash()
_PWSH = shutil.which("pwsh")
_T = crew_fixtures.GATE_SUBPROCESS_TIMEOUT_S

_MAP = {
    "version": 1,
    "rules": [
        {"paths": ["a.py"], "seconds": 5, "reach": "local", "run": ["echo RAN-cheap"], "why": "cheap"},
        {"paths": ["a.py"], "seconds": 90, "reach": "local", "run": ["echo RAN-big"], "why": "over"},
        {"paths": ["a.py"], "seconds": 5, "reach": "network", "run": ["echo RAN-remote"], "why": "remote"},
        {"paths": ["a.py"], "seconds": 3, "reach": "local",
         "run": ["echo boom; echo second; exit 1"], "why": "fails"},
    ],
    "default": [],
    "unmapped": "ignore",
}


def _read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def _detail_sites_sh(text):
    return sorted(re.findall(r'gate_detail "(verify-gate: [A-Za-z ]{3,24})', text))


def _detail_sites_ps1(text):
    return sorted(re.findall(r'Write-CrewDetail\("(verify-gate: [A-Za-z ]{3,24})', text))


def test_both_flavours_demote_the_same_sites():
    sh_sites = _detail_sites_sh(_read(_SH))
    ps1_sites = _detail_sites_ps1(_read(_PS1))

    assert sh_sites
    assert sh_sites == ps1_sites


def test_both_flavours_carry_the_same_notice_allowlist():
    sh_text = _read(_SH)
    ps1_text = _read(_PS1)

    for fragment in ("priced from a cached measurement", "priced at ", "cost UNSTATED, ran anyway",
                     "RAN past the budget", "deferred to /crew:verify: ", "is permanently over budget",
                     "stop budget ", "declared reach: ", "requires a clean working tree",
                     "passed on this exact tree in an earlier run and are credited"):
        assert fragment in sh_text.split("gate_notice_is_info() {", 1)[1].split("}", 1)[0]
        ps1_pattern = fragment.replace("(", r"\(").replace(".", r"\.")
        ps1_list = ps1_text.split("CrewInfoNotice = @(", 1)[1].split(")\nfunction", 1)[0]
        assert ps1_pattern in ps1_list


def _repo(tmp_path, verify_map=None):
    root = tmp_path / "repo"
    (root / ".crew").mkdir(parents=True)
    for args in (("init", "-q"), ("config", "user.email", "t@example.invalid"), ("config", "user.name", "t")):
        subprocess.run(("git",) + args, cwd=root, check=True, capture_output=True, text=True, timeout=_T)
    (root / "README.md").write_text("committed", encoding="utf-8")
    subprocess.run(("git", "add", "-A"), cwd=root, check=True, capture_output=True, text=True, timeout=_T)
    subprocess.run(("git", "commit", "-q", "-m", "fixture"), cwd=root, check=True,
                   capture_output=True, text=True, timeout=_T)
    (root / "a.py").write_text("x = 1", encoding="utf-8")
    (root / ".crew" / "verify.json").write_text(json.dumps(verify_map or _MAP), encoding="utf-8")
    return root


def _run(flavour, root, session="s1", payload=None):
    env = crew_fixtures.isolated_home_env(root.parent / "home")
    env.update(CLAUDE_PROJECT_DIR=str(root), CREW_VERIFY_VERBOSE="0")
    if payload is None:
        payload = json.dumps({"session_id": session})
    if flavour == "ps1":
        env["OS"] = "Windows_NT"
    if flavour == "sh":
        cmd = [_BASH, _SH]
    else:
        cmd = [_PWSH, "-NoProfile", "-NonInteractive", "-File", _PS1]
    result = crew_fixtures.run_gate(cmd, input=payload, cwd=str(root), env=env,
                                    capture_output=True, text=True, check=False, timeout=_T)
    return result


def _normal(result):
    # "bash: <path>" is the .ps1's own failure-header line.
    lines = [ln for ln in result.stderr.splitlines() if not ln.startswith("bash: ")]
    return [re.sub(r"budget \d+s/", "budget Ns/", ln) for ln in lines]


@pytest.mark.skipif(_PWSH is None or _BASH is None, reason="needs pwsh and bash")
def test_ps1_matches_sh_verdict_failure_and_unchanged_lines(tmp_path):
    sh_root = _repo(tmp_path / "sh")
    ps1_root = _repo(tmp_path / "ps1")

    sh_first = _run("sh", sh_root)
    ps1_first = _run("ps1", ps1_root)
    sh_second = _run("sh", sh_root)
    ps1_second = _run("ps1", ps1_root)

    assert sh_first.returncode == ps1_first.returncode == 2
    assert sh_second.returncode == ps1_second.returncode == 2
    sh_lines, ps1_lines = _normal(sh_first), _normal(ps1_first)
    assert sh_lines[0] == ps1_lines[0]
    assert "FAILED 1 cmd | PASSED 1 cmd | NOT VERIFIED 2 item(s) " in sh_lines[0]
    assert [ln for ln in sh_lines if ln.startswith("VERIFY FAILED") or ln in ("boom", "second")] == \
        [ln for ln in ps1_lines if ln.startswith("VERIFY FAILED") or ln in ("boom", "second")]
    assert _normal(sh_second) == _normal(ps1_second)
    assert "unchanged since last Stop (1 failing, 2 NOT VERIFIED)" in sh_second.stderr


_FAIL_ONLY = {
    "version": 1,
    "rules": [{"paths": ["a.py"], "seconds": 3, "reach": "local",
               "run": ["echo boom; exit 1"], "why": "fails"}],
    "default": [],
    "unmapped": "ignore",
}
_needs_pwsh = pytest.mark.skipif(_PWSH is None or _BASH is None, reason="needs pwsh and bash")


@_needs_pwsh
def test_ps1_unknown_notice_line_still_prints(tmp_path):
    undeclared = {"paths": ["a.py"], "seconds": 5, "run": ["curl https://example.invalid/x"],
                  "why": "undeclared reach"}
    root = _repo(tmp_path, dict(_FAIL_ONLY, rules=[undeclared]))

    result = _run("ps1", root)

    assert "declare no `reach`" in result.stderr


@_needs_pwsh
def test_ps1_unwritable_log_degrades_to_full_output(tmp_path):
    root = _repo(tmp_path, _FAIL_ONLY)
    (root / ".crew" / ".verify-gate.log").mkdir()

    result = _run("ps1", root)

    assert result.returncode == 2
    assert _normal(result)[0].endswith("| detail: unavailable")
    assert "verify-gate: env pinned" in result.stderr
    assert "VERIFY FAILED: echo boom; exit 1" in result.stderr


@_needs_pwsh
def test_ps1_unchanged_repeat_with_unwritable_log_prints_failure_in_full(tmp_path):
    root = _repo(tmp_path, _FAIL_ONLY)
    (root / ".crew" / ".verify-gate.log").mkdir()

    _run("ps1", root)
    second = _run("ps1", root)

    assert second.returncode == 2
    assert "unchanged since last Stop" not in second.stderr
    assert "VERIFY FAILED: echo boom; exit 1" in second.stderr


@_needs_pwsh
def test_ps1_other_session_prints_full_block_and_unchanged_names_the_log(tmp_path):
    root = _repo(tmp_path, _FAIL_ONLY)
    _run("ps1", root)

    same = _run("ps1", root)
    other = _run("ps1", root, session="s2")

    assert _normal(same) == [
        "verify-gate: unchanged since last Stop (1 failing, 0 NOT VERIFIED): echo boom; exit 1"
        " | detail: .crew/.verify-gate.log | /crew:verify --all runs every rule"]
    assert other.returncode == 2
    assert "unchanged since last Stop" not in other.stderr
    assert "VERIFY FAILED: echo boom; exit 1" in other.stderr


@_needs_pwsh
def test_ps1_backed_off_run_leaves_the_lock_holders_log_alone(tmp_path):
    root = _repo(tmp_path, _FAIL_ONLY)
    (root / ".crew" / ".verify-gate.lock").mkdir()
    (root / ".crew" / ".verify-gate.log").write_text("HOLDER-LOG\n", encoding="utf-8")

    result = _run("ps1", root)

    assert result.returncode == 0
    assert "backed off, lock held by" in result.stderr
    assert _read(os.path.join(str(root), ".crew", ".verify-gate.log")) == "HOLDER-LOG\n"


@_needs_pwsh
def test_ps1_reach_excluded_always_command_counts_as_not_verified(tmp_path):
    root = _repo(tmp_path, dict(_FAIL_ONLY, rules=[], always=["curl https://example.invalid/a"]))

    result = _run("ps1", root)

    assert result.returncode == 0
    assert "NOT VERIFIED 1 item(s) (reach 1," in _normal(result)[0]


@_needs_pwsh
def test_ps1_repeat_check_follows_which_rules_were_not_run(tmp_path):
    net_a = {"paths": ["a.py"], "seconds": 5, "reach": "network", "run": ["echo RAN-a"], "why": "a"}
    net_b = {"paths": ["b.py"], "seconds": 5, "reach": "network", "run": ["echo RAN-b"], "why": "b"}
    fail = dict(_FAIL_ONLY["rules"][0], paths=["*.py"])
    root = _repo(tmp_path, dict(_FAIL_ONLY, rules=[net_a, net_b, fail]))
    (root / "b.py").write_text("y = 1", encoding="utf-8")
    for args in (("add", "-A"), ("commit", "-q", "-m", "map")):
        subprocess.run(("git",) + args, cwd=root, check=True, capture_output=True, text=True, timeout=_T)

    def touch(name):
        subprocess.run(("git", "checkout", "--", "a.py", "b.py"), cwd=root, check=True, capture_output=True,
                       text=True, timeout=_T)
        (root / name).write_text("z = 2", encoding="utf-8")
        return _run("ps1", root)

    touch("a.py")
    touch("b.py")
    third = touch("a.py")
    fourth = touch("b.py")

    assert third.returncode == fourth.returncode == 2
    assert "NOT VERIFIED 1 item(s) (reach 1," in _normal(third)[0]
    assert "unchanged since last Stop" not in fourth.stderr
    assert "VERIFY FAILED: echo boom; exit 1" in fourth.stderr


@_needs_pwsh
def test_ps1_exit_zero_stop_clears_the_repeat_state(tmp_path):
    root = _repo(tmp_path, _FAIL_ONLY)
    _run("ps1", root)
    for args in (("add", "-A"), ("commit", "-q", "-m", "map")):
        subprocess.run(("git",) + args, cwd=root, check=True, capture_output=True, text=True, timeout=_T)
    clean = _run("ps1", root)
    (root / "a.py").write_text("x = 2", encoding="utf-8")

    third = _run("ps1", root)

    assert clean.returncode == 0
    assert "VERIFY FAILED" not in clean.stderr
    assert third.returncode == 2
    assert "unchanged since last Stop" not in third.stderr
    assert "VERIFY FAILED: echo boom; exit 1" in third.stderr


@_needs_pwsh
@pytest.mark.parametrize("payload", [
    '{"meta":{"session_id":"nested"}}',
    '{"session_id":{"x":1}}',
    '{"session_id":"a","session_id":"b"}',
])
def test_ps1_a_session_id_that_is_not_a_top_level_string_prints_the_full_block(tmp_path, payload):
    root = _repo(tmp_path, _FAIL_ONLY)

    _run("ps1", root, payload=payload)
    second = _run("ps1", root, payload=payload)

    assert second.returncode == 2
    assert "unchanged since last Stop" not in second.stderr
    assert "VERIFY FAILED: echo boom; exit 1" in second.stderr

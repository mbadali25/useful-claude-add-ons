"""The role-write `PreToolUse` guard: `guards.roleWrites` and its hook.

`agents/pm.md:49-53` says, in prose, "You do not write application code,
tests, docs..." and on 2026-09-19 it did exactly that for four hours, because
prose is not enforcement. This is the harness doing what the prompt could
not -- see `hooks/scripts/role_write_guard.py`'s module docstring for the
full design.

Two halves are tested here: the pure-python decision logic (`classify`,
`_normalise_role`, the policy-table-matches-agent-files invariant) against
the module directly, and the two hook SCRIPTS (`role-write-guard.sh` /
`.ps1`) end to end as subprocesses, because a correct `classify()` behind a
shim that reads the wrong stdin field or swallows the exit code is not a
working hook -- see `promote-gate.sh`'s own test suite for the same
reasoning.

Every case here is sabotage-tested against `role_write_guard.py` by hand
before this file was committed: flipping `decision = "block"` to `"allow"` in
`main()`, and separately emptying `_DENY_ROLES`, both turned the must-block
cases in this file red while leaving the must-allow cases green -- proving
the tests actually exercise the refusal path rather than passing regardless
of it. Re-run that by hand rather than trusting this paragraph; it is a fact
about one commit.
"""
import json
import os
import pathlib
import re
import subprocess
import sys

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import crew_fixtures

import crew_config  # noqa: E402  pylint: disable=wrong-import-position
import crew_state  # noqa: E402  pylint: disable=wrong-import-position
import role_write_guard  # noqa: E402  pylint: disable=wrong-import-position

_ROOT = context._ROOT  # pylint: disable=protected-access
_AGENTS_DIR = os.path.join(_ROOT, "agents")
_SH = os.path.join(_ROOT, "hooks", "scripts", "role-write-guard.sh")
_PS1 = os.path.join(_ROOT, "hooks", "scripts", "role-write-guard.ps1")

_BASH = crew_fixtures.resolve_bash()
_PWSH = crew_fixtures.resolve_pwsh()
needs_bash = pytest.mark.skipif(_BASH is None, reason="no MSYS/POSIX bash")
needs_pwsh_windows = pytest.mark.skipif(
    not sys.platform.startswith("win") or _PWSH is None,
    reason="the .ps1 hook is the native-Windows flavour; needs Windows + pwsh",
)


# --- The policy table, measured from the agent files -----------------------

_TOOLS_RE = re.compile(r"^tools:\s*(.*)$", re.MULTILINE)


def _agent_tool_grants():
    """`{role_name: frozenset(tool_names)}` for every `agents/*.md`.

    Read from the `tools:` frontmatter line, split on commas -- the same
    shape every agent file uses (see `role_write_guard.py`'s own table,
    built the same way on 2026-09-19). Not a full YAML parse: the files
    never wrap this line, and a wrap would be its own kind of drift worth
    a loud failure rather than a silent partial read, which a strict
    single-line regex gives for free.
    """
    grants = {}
    for name in sorted(os.listdir(_AGENTS_DIR)):
        if not name.endswith(".md"):
            continue
        role = name[:-3]
        with open(os.path.join(_AGENTS_DIR, name), encoding="utf-8") as handle:
            text = handle.read()
        match = _TOOLS_RE.search(text)
        assert match, f"agents/{name} has no tools: frontmatter line"
        tools = frozenset(t.strip() for t in match.group(1).split(",") if t.strip())
        grants[role] = tools
    return grants


def test_policy_table_matches_the_agent_files():
    """The script's `_DENY_ROLES` / `pm` / `_UNRESTRICTED_ROLES` partition is
    EXACTLY what `agents/*.md`'s own `tools:` grants produce today.

    This is the test CLAUDE.md's "Adding a hook" rule asks for: a `tools:`
    grant added or removed in an agent file, with `role_write_guard.py`'s
    table left untouched, must fail here rather than silently stranding or
    over-granting a role.
    """
    grants = _agent_tool_grants()
    assert grants, "expected at least one agents/*.md file"

    computed_deny = set()
    computed_pm = set()
    computed_unrestricted = set()
    for role, tools in grants.items():
        has_write_edit = "Write" in tools and "Edit" in tools
        if role == "pm":
            computed_pm.add(role)
        elif has_write_edit:
            computed_unrestricted.add(role)
        else:
            computed_deny.add(role)

    assert computed_deny == role_write_guard._DENY_ROLES, (  # pylint: disable=protected-access
        f"deny-list drift: computed {sorted(computed_deny)} vs script "
        f"{sorted(role_write_guard._DENY_ROLES)}")  # pylint: disable=protected-access
    assert computed_pm == {"pm"}
    assert computed_unrestricted == role_write_guard._UNRESTRICTED_ROLES, (  # pylint: disable=protected-access
        f"unrestricted-list drift: computed {sorted(computed_unrestricted)} "
        f"vs script {sorted(role_write_guard._UNRESTRICTED_ROLES)}")  # pylint: disable=protected-access

    # Every agent file lands in exactly one bucket. A role in two, or in
    # none, is the partition failing to be a partition.
    all_roles = set(grants)
    partitioned = (role_write_guard._DENY_ROLES  # pylint: disable=protected-access
                   | {"pm"}
                   | role_write_guard._UNRESTRICTED_ROLES)  # pylint: disable=protected-access
    assert partitioned == all_roles, (
        f"not a partition: files {sorted(all_roles - partitioned)} are in no "
        f"bucket; table entries {sorted(partitioned - all_roles)} name no file")


def test_deny_roles_have_neither_write_nor_edit():
    grants = _agent_tool_grants()
    for role in role_write_guard._DENY_ROLES:  # pylint: disable=protected-access
        tools = grants[role]
        assert "Write" not in tools and "Edit" not in tools, (
            f"{role} is in _DENY_ROLES but its tools: line grants Write/Edit")


def test_unrestricted_roles_have_both_write_and_edit():
    grants = _agent_tool_grants()
    for role in role_write_guard._UNRESTRICTED_ROLES:  # pylint: disable=protected-access
        tools = grants[role]
        assert "Write" in tools and "Edit" in tools, (
            f"{role} is in _UNRESTRICTED_ROLES but its tools: line is missing "
            "Write or Edit")


# --- classify() and _normalise_role(), directly -----------------------------

def test_classify_pm_in_scope_paths():
    for rel in (".crew/config.json", "TODO.md", ".work/HANDOFF.md",
                "docs/diagrams/arch.mmd", ".crew/deep/nested/file.json"):
        in_scope, _ = role_write_guard.classify("pm", rel)
        assert in_scope, rel


def test_classify_pm_out_of_scope_paths():
    for rel in ("plugin/crew/agents/pm.md", "src/app.py", "README.md",
                "docsx/diagrams/x.mmd", "TODO.md.bak"):
        in_scope, _ = role_write_guard.classify("pm", rel)
        assert not in_scope, rel


def test_classify_deny_role_is_always_out_of_scope():
    in_scope, reason = role_write_guard.classify("analyst", "TODO.md")
    assert not in_scope
    assert "analyst" in reason


def test_classify_unrestricted_role_is_always_in_scope():
    in_scope, _ = role_write_guard.classify("developer", "plugin/crew/agents/pm.md")
    assert in_scope


def test_classify_missing_role_allows_as_no_agent_type():
    in_scope, reason = role_write_guard.classify(None, "src/app.py")
    assert in_scope
    assert reason == "no-agent-type"


def test_classify_unrecognised_role_allows_as_unknown():
    in_scope, reason = role_write_guard.classify("some-other-plugins-agent",
                                                   "src/app.py")
    assert in_scope
    assert reason == "unknown-role:some-other-plugins-agent"


@pytest.mark.parametrize("raw,expected", [
    ("crew:analyst", "analyst"), ("analyst", "analyst"),
    ("CREW:PM", "pm"), ("  pm  ", "pm"), ("", None), (None, None),
    ("a:b:c", "c"),
])
def test_normalise_role_strips_the_last_colon_prefix(raw, expected):
    assert role_write_guard._normalise_role(raw) == expected  # pylint: disable=protected-access


# --- guards.roleWrites resolves through the same ratchet as every guard ----

def test_role_writes_resolves_through_crew_config_resolve_guard(tmp_path):
    root = crew_fixtures.make_repo(tmp_path / "a", config={})
    resolved = crew_config.resolve_guard(str(root), "roleWrites")
    assert resolved["effective"] == "off"

    root2 = crew_fixtures.make_repo(
        tmp_path / "b", config={"guards": {"roleWrites": "block"}})
    resolved2 = crew_config.resolve_guard(str(root2), "roleWrites")
    assert resolved2["effective"] == "block"


def test_malformed_policy_value_fails_closed_to_block(tmp_path):
    root = crew_fixtures.make_repo(
        tmp_path, config={"guards": {"roleWrites": "yolo"}})
    resolved = crew_config.resolve_guard(str(root), "roleWrites")
    assert resolved["effective"] == "block", (
        "a malformed guards.roleWrites value must fail CLOSED (to block), "
        "not open -- an unknown must not wear the label of 'off'")


# --- The hook scripts, end to end -------------------------------------------

def _write_payload(tool_name, file_path, agent_type, cwd):
    payload = {"tool_name": tool_name, "cwd": cwd}
    if file_path is not None:
        payload["tool_input"] = {"file_path": file_path}
    if agent_type is not None:
        payload["agent_type"] = agent_type
    return json.dumps(payload)


def _run_sh(root, tool_name, file_path, agent_type):
    return subprocess.run(
        [_BASH, _SH], input=_write_payload(tool_name, file_path, agent_type, str(root)),
        capture_output=True, text=True, check=False,
        env=dict(os.environ, CLAUDE_PROJECT_DIR=str(root)), cwd=str(root),
    )


def _run_ps1(root, tool_name, file_path, agent_type):
    return subprocess.run(
        [_PWSH, "-NoProfile", "-NonInteractive", "-File", _PS1],
        input=_write_payload(tool_name, file_path, agent_type, str(root)),
        capture_output=True, text=True, check=False,
        env=dict(os.environ, CLAUDE_PROJECT_DIR=str(root)), cwd=str(root),
    )


@needs_bash
def test_off_by_default_never_blocks_bash(tmp_path):
    """The must-allow case CLAUDE.md requires for a hook that defaults OFF."""
    root = crew_fixtures.make_repo(tmp_path, config={})
    proc = _run_sh(root, "Write", str(root / "plugin/crew/agents/pm.md"), "pm")
    assert proc.returncode == 0, proc.stderr
    assert not (root / ".crew" / "guard.log").exists(), (
        "off must not log either -- the hook does not run its check at all")


@needs_bash
def test_block_mode_pm_outside_scope_is_refused_bash(tmp_path):
    """Must-block: pm writing application code under guards.roleWrites: block."""
    root = crew_fixtures.make_repo(
        tmp_path, config={"guards": {"roleWrites": "block"}})
    target = str(root / "plugin/crew/agents/pm.md")
    proc = _run_sh(root, "Write", target, "pm")
    assert proc.returncode == 2, proc.stdout
    assert "pm" in proc.stderr and "may not write" in proc.stderr
    log = (root / ".crew" / "guard.log").read_text(encoding="utf-8")
    assert "\tblock\tpm\t" in log


@needs_bash
def test_block_mode_pm_inside_scope_is_allowed_bash(tmp_path):
    """Must-allow twin of the case above: same role, in-scope path."""
    root = crew_fixtures.make_repo(
        tmp_path, config={"guards": {"roleWrites": "block"}})
    proc = _run_sh(root, "Write", str(root / "TODO.md"), "pm")
    assert proc.returncode == 0, proc.stderr
    log = (root / ".crew" / "guard.log").read_text(encoding="utf-8")
    assert "\tallow\tpm\t" in log


@needs_bash
def test_block_mode_deny_role_is_refused_bash(tmp_path):
    """Must-block: a role with no Write/Edit grant, any path."""
    root = crew_fixtures.make_repo(
        tmp_path, config={"guards": {"roleWrites": "block"}})
    proc = _run_sh(root, "Edit", str(root / "TODO.md"), "analyst")
    assert proc.returncode == 2, proc.stdout
    assert "analyst" in proc.stderr


@needs_bash
def test_block_mode_unrestricted_role_is_allowed_bash(tmp_path):
    """Must-allow: a developer-type role, any path."""
    root = crew_fixtures.make_repo(
        tmp_path, config={"guards": {"roleWrites": "block"}})
    proc = _run_sh(root, "Write", str(root / "src" / "app.py"), "developer")
    assert proc.returncode == 0, proc.stderr


@needs_bash
def test_block_mode_missing_agent_type_allows_and_logs_bash(tmp_path):
    root = crew_fixtures.make_repo(
        tmp_path, config={"guards": {"roleWrites": "block"}})
    proc = _run_sh(root, "Write", str(root / "src" / "app.py"), None)
    assert proc.returncode == 0, proc.stderr
    log = (root / ".crew" / "guard.log").read_text(encoding="utf-8")
    assert "\t-\t" in log, log  # role column is "-" when agent_type is absent


@needs_bash
def test_block_mode_prefixed_agent_type_still_matches_bash(tmp_path):
    """`crew:analyst` must be judged exactly like `analyst`."""
    root = crew_fixtures.make_repo(
        tmp_path, config={"guards": {"roleWrites": "block"}})
    proc = _run_sh(root, "Write", str(root / "src" / "app.py"), "crew:analyst")
    assert proc.returncode == 2, proc.stdout


@needs_bash
def test_report_mode_never_blocks_but_logs_the_would_be_refusal_bash(tmp_path):
    root = crew_fixtures.make_repo(
        tmp_path, config={"guards": {"roleWrites": "report"}})
    proc = _run_sh(root, "Write", str(root / "src" / "app.py"), "analyst")
    assert proc.returncode == 0, proc.stderr
    log = (root / ".crew" / "guard.log").read_text(encoding="utf-8")
    assert "\treport\treport\tanalyst\t" in log, log


@needs_bash
def test_non_write_edit_tool_is_ignored_bash(tmp_path):
    root = crew_fixtures.make_repo(
        tmp_path, config={"guards": {"roleWrites": "block"}})
    proc = subprocess.run(
        [_BASH, _SH],
        input=json.dumps({"tool_name": "Bash",
                          "tool_input": {"command": "ls"},
                          "agent_type": "analyst", "cwd": str(root)}),
        capture_output=True, text=True, check=False,
        env=dict(os.environ, CLAUDE_PROJECT_DIR=str(root)), cwd=str(root),
    )
    assert proc.returncode == 0
    assert not (root / ".crew" / "guard.log").exists()


@needs_bash
def test_no_crew_directory_never_crashes_and_never_creates_one_bash(tmp_path):
    """An unmanaged repo (no `.crew/`) must not be silently adopted into crew.

    Mirrors `crew_config._log_guard`'s own rule, which `role_write_guard._log`
    copies rather than imports -- see that function's docstring.
    """
    root = tmp_path / "plain"
    root.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    proc = _run_sh(root, "Write", str(root / "x.py"), "analyst")
    assert proc.returncode == 0, proc.stderr  # off by default: no .crew/config.json at all
    assert not (root / ".crew").exists()


# --- PowerShell twin, Windows + pwsh only -----------------------------------

@needs_pwsh_windows
def test_block_mode_pm_outside_scope_is_refused_powershell(tmp_path):
    root = crew_fixtures.make_repo(
        tmp_path, config={"guards": {"roleWrites": "block"}})
    target = str(root / "plugin/crew/agents/pm.md")
    proc = _run_ps1(root, "Write", target, "pm")
    assert proc.returncode == 2, proc.stdout
    assert "pm" in proc.stderr and "may not write" in proc.stderr


@needs_pwsh_windows
def test_block_mode_pm_inside_scope_is_allowed_powershell(tmp_path):
    root = crew_fixtures.make_repo(
        tmp_path, config={"guards": {"roleWrites": "block"}})
    proc = _run_ps1(root, "Write", str(root / "TODO.md"), "pm")
    assert proc.returncode == 0, proc.stderr


@needs_pwsh_windows
def test_off_by_default_never_blocks_powershell(tmp_path):
    root = crew_fixtures.make_repo(tmp_path, config={})
    proc = _run_ps1(root, "Write", str(root / "plugin/crew/agents/pm.md"), "pm")
    assert proc.returncode == 0, proc.stderr
    assert not (root / ".crew" / "guard.log").exists()


@needs_pwsh_windows
def test_block_mode_deny_role_is_refused_powershell(tmp_path):
    root = crew_fixtures.make_repo(
        tmp_path, config={"guards": {"roleWrites": "block"}})
    proc = _run_ps1(root, "Edit", str(root / "TODO.md"), "analyst")
    assert proc.returncode == 2, proc.stdout


# --- role-write-guard.ps1's own python resolver ------------------------------
#
# The first draft of this file resolved its interpreter with the un-hardened
# `(Get-Command python3, python | Select-Object -First 1).Source` -- the exact
# one-liner pm-pulse.ps1's and verify-gate.ps1's own headers name as the bug
# that silently dropped their checks. Fixed to the same hardened
# `Resolve-CrewPython` those two files carry, duplicated inline for the same
# reason (a dot-sourced function is invisible to
# scripts/check-powershell.ps1's static check). These three cases are that
# fix's own regression suite: the WindowsApps stub must never be returned, a
# real interpreter must still resolve past one, and the three copies of the
# resolver must not have drifted from each other.

_VERIFY_GATE_PS1 = os.path.join(_ROOT, "hooks", "scripts", "verify-gate.ps1")
_PM_PULSE_PS1 = os.path.join(_ROOT, "hooks", "scripts", "pm-pulse.ps1")


def _stub(path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="ascii") as handle:
        handle.write("rem stub, never executed by -PrintPython\n")
    return path


def _print_python(path_entries):
    env = os.environ.copy()
    env["PATH"] = os.pathsep.join(path_entries)
    result = subprocess.run(
        [_PWSH, "-NoProfile", "-NonInteractive", "-File", _PS1, "-PrintPython"],
        env=env, stdin=subprocess.DEVNULL, capture_output=True, text=True,
        check=False,
    )
    assert result.returncode == 0, "the probe must exit 0. stderr: " + result.stderr
    return result.stdout.strip()


@needs_pwsh_windows
def test_the_windowsapps_stub_is_never_returned(tmp_path):
    """Must-block. The old one-liner returned the Store alias and invoked it."""
    apps = tmp_path / "WindowsApps"
    _stub(str(apps / "python3.exe"))
    _stub(str(apps / "python.exe"))

    resolved = _print_python([str(apps)])
    assert "WindowsApps" not in resolved, (
        "the WindowsApps alias was returned as the interpreter: " + resolved)
    assert resolved == "", (
        "with only stubs on PATH there is no usable python and the resolver "
        "must answer empty rather than hand back a stub. got: " + resolved)


@needs_pwsh_windows
def test_a_real_python_beside_a_stub_still_resolves(tmp_path):
    """Must-allow: the fix must not become "never finds python"."""
    apps = tmp_path / "WindowsApps"
    real = tmp_path / "tools"
    _stub(str(apps / "python3.exe"))
    _stub(str(real / "python3.exe"))

    resolved = _print_python([str(apps), str(real)])
    assert resolved.lower().startswith(str(real).lower()), (
        "the real python3.exe must win over the WindowsApps stub. got: "
        + resolved)


def _resolver_source(path):
    src = pathlib.Path(path).read_text(encoding="utf-8")
    start = src.find("function Resolve-CrewPython {")
    assert start != -1, (
        "Resolve-CrewPython is gone from " + path + ". If it was renamed, "
        "re-point this test rather than deleting it.")
    end = src.find("\n}\n", start)
    assert end != -1, "could not find the end of Resolve-CrewPython in " + path
    return src[start:end + 3]


def test_the_three_copies_of_the_resolver_still_agree():
    """The guard the duplication needs, and it runs everywhere (no pwsh
    required -- this compares source text).

    verify-gate.ps1, pm-pulse.ps1 and role-write-guard.ps1 each carry their
    own Resolve-CrewPython for the reason each file's header gives: a
    dot-sourced function is invisible to check-powershell.ps1's static check.
    That decision is defensible; leaving three unguarded copies is not.
    Comments are allowed to differ -- they SHOULD, each file explains a
    different cost -- so this compares the executable lines only.
    """
    def code_lines(src):
        out = []
        for line in src.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            out.append(re.sub(r"\s+", " ", stripped))
        return out

    gate = code_lines(_resolver_source(_VERIFY_GATE_PS1))
    pulse = code_lines(_resolver_source(_PM_PULSE_PS1))
    guard = code_lines(_resolver_source(_PS1))
    assert gate == pulse == guard, (
        "the three copies of Resolve-CrewPython have drifted. One hook would "
        "then resolve an interpreter another refuses, which is the same "
        "class of defect as a .ps1 guard that stands down on Windows."
        + "\nverify-gate.ps1:      " + repr(gate)
        + "\npm-pulse.ps1:         " + repr(pulse)
        + "\nrole-write-guard.ps1: " + repr(guard))

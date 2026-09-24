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
import shutil
import subprocess
import sys

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import crew_fixtures

import crew_config  # noqa: E402  pylint: disable=wrong-import-position
import role_write_guard  # noqa: E402  pylint: disable=wrong-import-position

_ROOT = context._ROOT  # pylint: disable=protected-access
_AGENTS_DIR = os.path.join(_ROOT, "agents")
_SH = os.path.join(_ROOT, "hooks", "scripts", "role-write-guard.sh")
_PS1 = os.path.join(_ROOT, "hooks", "scripts", "role-write-guard.ps1")

_BASH = crew_fixtures.resolve_bash()
_PWSH = crew_fixtures.resolve_pwsh()
needs_bash = pytest.mark.skipif(_BASH is None, reason="no MSYS/POSIX bash")
needs_windows = pytest.mark.skipif(
    os.name != "nt",
    reason="asserts Windows path semantics (lexical .. collapse, backslash output); "
           "CI ran these on Ubuntu from 621d50dc and the workflow stayed red")
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


# The exact five paths `crew-pm` wrote to in this repo's own working tree,
# reported by the PM itself: "I wrote four files, all outside my write
# scope. role_write_guard.py did not stop me." (a fifth site,
# README.md:836, is the same file as the README.md:664 site below -- one
# path, two edits). `classify()` was never the problem -- see
# `test_the_incident_paths_were_never_reachable_because_the_repo_had_the_
# guard_off` below for the actual cause -- but these are the best possible
# regression fixture there is: a guard proven correct on invented paths and
# never checked against the paths that actually got past it is exactly the
# gap CLAUDE.md's "re-review the fix as hard as the guard" lesson is about.
_INCIDENT_PATHS = (
    ".claude-plugin/marketplace.json",
    "README.md",
    "scripts/install-prerequisites.sh",
    "scripts/install-prerequisites.ps1",
)


def test_classify_the_incident_paths_are_all_out_of_scope_for_pm():
    for rel in _INCIDENT_PATHS:
        in_scope, reason = role_write_guard.classify("pm", rel)
        assert not in_scope, f"{rel} classified in-scope: {reason}"


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
    # NOT "c". The first draft stripped up to the LAST colon unconditionally,
    # so "other-plugin:analyst" collapsed onto this table's own `analyst`
    # (a _DENY_ROLES member) and a totally unrelated plugin's agent was
    # refused under crew's policy. Only a LEADING `crew:` is stripped now;
    # anything else is returned whole (lowercased) so it cannot collide with
    # a bare crew role name and falls through to classify()'s unknown-role
    # branch instead. Reported and fixed 2026-09-19.
    ("a:b:c", "a:b:c"),
    ("other-plugin:analyst", "other-plugin:analyst"),
    ("CREW:Analyst", "analyst"),
])
def test_normalise_role_strips_only_a_leading_crew_prefix(raw, expected):
    assert role_write_guard._normalise_role(raw) == expected  # pylint: disable=protected-access


def test_classify_other_plugin_namespaced_role_is_unknown_not_deny():
    """Must-allow: the exact regression case. `other-plugin:analyst`
    normalises to the WHOLE string (see the parametrized test above), which
    is not `_DENY_ROLES`' bare `analyst`, so it falls through to
    unknown-role -- allowed and logged, never refused under a policy this
    table has no business applying to a different plugin's agent."""
    role = role_write_guard._normalise_role("other-plugin:analyst")  # pylint: disable=protected-access
    in_scope, reason = role_write_guard.classify(role, "TODO.md")
    assert in_scope
    assert reason == "unknown-role:other-plugin:analyst"


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
    return _run_ps1_at(_PS1, root, tool_name, file_path, agent_type)


def _run_ps1_at(script_path, root, tool_name, file_path, agent_type):
    """`_run_ps1`, against an explicit script path -- for a patched or
    relocated copy of role-write-guard.ps1 (BLOCK-1 and FIX-4's tests, both
    of which need to run a DELIBERATELY altered copy without touching the
    real, committed file)."""
    return subprocess.run(
        [_PWSH, "-NoProfile", "-NonInteractive", "-File", script_path],
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
@pytest.mark.parametrize("rel", _INCIDENT_PATHS)
def test_the_incident_paths_are_refused_once_the_guard_is_armed_bash(
    tmp_path, rel
):
    """Must-block, end to end, on the real paths from the real incident --
    not invented stand-ins. With `guards.roleWrites: block` armed, each of
    these is refused for `pm` exactly as `test_block_mode_pm_outside_scope_
    is_refused_bash` proves for a generic path."""
    root = crew_fixtures.make_repo(
        tmp_path, config={"guards": {"roleWrites": "block"}})
    target = str(root / rel)
    os.makedirs(os.path.dirname(target), exist_ok=True)
    proc = _run_sh(root, "Write", target, "pm")
    assert proc.returncode == 2, (
        f"{rel} was NOT refused under guards.roleWrites: block. "
        f"stdout={proc.stdout!r} stderr={proc.stderr!r}")
    assert "pm" in proc.stderr and "may not write" in proc.stderr


@needs_bash
@pytest.mark.parametrize("rel", _INCIDENT_PATHS)
def test_the_incident_paths_are_the_off_default_gap_not_a_classify_bug_bash(
    tmp_path, rel
):
    """Must-allow, and this is the actual incident, reproduced exactly: a
    repo with NO `guards` key at all -- what a repo that has never armed
    the guard looks like, and what THIS repo's own `.crew/config.json`
    carried (`"roleWrites": "off"`, the documented default) when `crew-pm`
    wrote these same five paths. The hook exits 0 before `classify()` ever
    runs -- see `role_write_guard.py`'s `main`, `elif policy == "off":
    return 0`, which is above the `classify()` call, not a branch of it.

    This is the must-allow half of the incident's own fixture, on purpose:
    the guard is CORRECT to let these through while off, exactly as
    CLAUDE.md requires ("a plugin registering a hook defaults to OFF in the
    menu"). Pairing it with the must-block case above is what proves the
    incident was a configuration gap, not a code defect -- flip only the
    config and the same path goes from allowed to refused with no code
    change, which `test_the_incident_paths_are_refused_once_the_guard_is_
    armed_bash` already demonstrated.
    """
    root = crew_fixtures.make_repo(tmp_path, config={})
    target = str(root / rel)
    os.makedirs(os.path.dirname(target), exist_ok=True)
    proc = _run_sh(root, "Write", target, "pm")
    assert proc.returncode == 0, (
        f"{rel}: expected the documented off-by-default allow, got "
        f"stdout={proc.stdout!r} stderr={proc.stderr!r}")
    assert not (root / ".crew" / "guard.log").exists(), (
        "off must not log either -- the hook does not run its check at all")


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


# --- bash's own python resolver must reject a WindowsApps stub (round-1 FIX)
#
# Reported 2026-09-19: `role-write-guard.sh` originally called `_common.sh`'s
# shared `crew_py()`, a bare `command -v python3 || python || py` with no
# WindowsApps filtering at all -- unlike `role-write-guard.ps1`'s hardened
# `Resolve-CrewPython`. With a WindowsApps python3 alias ahead of a real
# interpreter on PATH, the two shell flavours of the SAME hook enforced
# DIFFERENT decisions on the same machine. `_resolve_role_write_python` in
# the .sh is the fix; this drives it through the actual script, not just the
# function in isolation, per `promote-gate.sh`'s own test suite reasoning
# that a correct resolver behind an unwired call site is not a fix.

@needs_bash
def test_windowsapps_python_stub_does_not_silence_bash_enforcement(tmp_path):
    """Must-block: a WindowsApps python3 stub ahead of a real interpreter on
    PATH must not make bash silently skip enforcement."""
    apps = tmp_path / "fakepath" / "WindowsApps"
    apps.mkdir(parents=True)
    stub = apps / "python3"
    # newline="\n": pathlib.write_text is TEXT mode on Windows and would
    # otherwise corrupt the shebang into "#!/bin/sh\r\n" (CLAUDE.md).
    stub.write_text("#!/bin/sh\nexit 0\n", encoding="ascii", newline="\n")  # no output at all
    os.chmod(stub, 0o755)

    real = shutil.which("python3") or shutil.which("python")
    assert real, "this test needs a real python3/python on PATH to prove against"
    real_dir = os.path.dirname(real)

    root = crew_fixtures.make_repo(
        tmp_path, config={"guards": {"roleWrites": "block"}})

    env = os.environ.copy()
    env["PATH"] = os.pathsep.join([str(apps), real_dir, env.get("PATH", "")])
    env["CLAUDE_PROJECT_DIR"] = str(root)
    proc = subprocess.run(
        [_BASH, _SH],
        input=_write_payload("Write", str(root / "src" / "app.py"), "pm", str(root)),
        capture_output=True, text=True, check=False, env=env, cwd=str(root))
    assert proc.returncode == 2, (
        "the WindowsApps stub must be rejected and the real interpreter "
        "used, so block mode still enforces. stdout: " + proc.stdout
        + " stderr: " + proc.stderr)


# --- Corrupt config must not silently disarm an armed guard (round-1 BLOCK) -
#
# Reported 2026-09-19: with no global override, replacing a repo's
# `guards.roleWrites: block` config with invalid JSON (or with
# `{"guards": 42}`) made `crew_config.resolve_guard` fall back through
# `crew_state.load_config`'s "absent, malformed, or not a dict all become
# {}" collapse to the DEFAULT (`off`), not the FLOOR (`block`) -- exactly
# CLAUDE.md's "unknown collapsing into the safe-looking value", on the one
# guard here that can least afford it. `crew_config.repo_config_is_corrupt`
# now distinguishes "file absent" (stays `off`, unchanged) from "file
# present but unreadable" (forced to `block`) and role_write_guard.py acts
# on it.

@needs_bash
def test_corrupt_repo_config_forces_block_not_off_bash(tmp_path):
    """Must-block. `.crew/config.json` exists but is not valid JSON."""
    root = crew_fixtures.make_repo(tmp_path, config={"guards": {"roleWrites": "block"}})
    (root / ".crew" / "config.json").write_text("{not valid json", encoding="utf-8")
    proc = _run_sh(root, "Write", str(root / "src" / "app.py"), "pm")
    assert proc.returncode == 2, proc.stdout
    assert "could not be read as guards.roleWrites needs" in proc.stderr, proc.stderr


@needs_bash
def test_non_object_guards_block_forces_block_not_off_bash(tmp_path):
    """Must-block, the second shape: valid JSON, `guards` is not an object."""
    root = crew_fixtures.make_repo(tmp_path, config={"guards": 42})
    proc = _run_sh(root, "Write", str(root / "src" / "app.py"), "pm")
    assert proc.returncode == 2, proc.stdout
    assert "could not be read as guards.roleWrites needs" in proc.stderr, proc.stderr


@needs_bash
def test_absent_config_file_is_not_corrupt_stays_off_bash(tmp_path):
    """Must-allow: the twin case. No `.crew/config.json` at all is every
    off-by-default repo that exists, not a corrupt one -- must stay `off`."""
    root = tmp_path / "plain"
    root.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    proc = _run_sh(root, "Write", str(root / "src" / "app.py"), "pm")
    assert proc.returncode == 0, proc.stderr


@needs_bash
def test_valid_config_with_no_guards_key_is_not_corrupt_stays_off_bash(tmp_path):
    """Must-allow: a well-formed config that simply never set `guards` at
    all is not corrupt either -- `off` is the honest answer, not a forced
    `block`."""
    root = crew_fixtures.make_repo(tmp_path, config={"change": {"requester": "x"}})
    proc = _run_sh(root, "Write", str(root / "src" / "app.py"), "pm")
    assert proc.returncode == 0, proc.stderr


# --- crew_config.layer_state: the ONE rule, tested as the matrix Codex's
# round-2 guidance specified -- {absent, ok (three roleWrites values),
# corrupt-json, corrupt-not-object, guards-null, guards-list, guards-number,
# guards-string} -- against a bare path, so the SAME test matrix proves the
# function is correct for BOTH the repo layer and the global layer, which
# is the whole point of it taking a path rather than a root.

@pytest.mark.parametrize("label,body,expected", [
    ("ok-no-guards-key", "{}", "ok"),
    ("ok-off", json.dumps({"guards": {"roleWrites": "off"}}), "ok"),
    ("ok-report", json.dumps({"guards": {"roleWrites": "report"}}), "ok"),
    ("ok-block", json.dumps({"guards": {"roleWrites": "block"}}), "ok"),
    ("corrupt-json", "{not valid json", "corrupt"),
    ("corrupt-not-object", json.dumps([1, 2, 3]), "corrupt"),
    ("guards-null", json.dumps({"guards": None}), "corrupt"),
    ("guards-list", json.dumps({"guards": [1, 2]}), "corrupt"),
    ("guards-number", json.dumps({"guards": 42}), "corrupt"),
    ("guards-string", json.dumps({"guards": "block"}), "corrupt"),
])
def test_layer_state_matrix(tmp_path, label, body, expected):
    path = tmp_path / "config.json"
    path.write_text(body, encoding="utf-8")
    assert crew_config.layer_state(str(path)) == expected, label


def test_layer_state_absent():
    """No file at all -- a path that was never written, not even the
    parent directory."""
    assert crew_config.layer_state(
        r"C:\definitely\does\not\exist\config.json") == "absent"


def test_layer_state_directory_is_corrupt(tmp_path):
    """A directory at the config path -- PRESENT but unreadable as this
    key needs, not "absent". Must-block repro: BLOCK 1 (crew_config.py:886)."""
    path = tmp_path / "config.json"
    path.mkdir()
    assert crew_config.layer_state(str(path)) == "corrupt"


def test_layer_state_dangling_symlink_is_corrupt_not_absent(tmp_path):
    """A symlink AT the config path whose target does not exist -- PRESENT
    (something is configured here) but unreadable, not "absent". The
    first draft of this fix used `os.path.exists(path) or os.path.
    isdir(path)`, and BOTH follow a symlink to check its TARGET: a
    dangling link answers False to both, same as a path with nothing at
    it at all. `os.path.lexists` checks the link itself. Must-block
    repro: round-3 BLOCK 1 (crew_config.py:905)."""
    target = tmp_path / "moved-or-deleted-target.json"
    link = tmp_path / "config.json"
    if not _make_symlink(target, link):
        pytest.skip("could not create a symlink on this platform/user")
    assert not target.exists(), "the fixture must NOT create the target"
    assert crew_config.layer_state(str(link)) == "corrupt"


# --- The unified rule, end to end, over BOTH layers (round-2 BLOCK 1/2/5/6) -
#
# `crew_state.GLOBAL_CONFIG_PATH` is computed from `os.path.expanduser("~")`
# at IMPORT time, and a subprocess re-imports it fresh -- so isolating the
# global layer for a subprocess-driven test means pointing HOME/USERPROFILE
# at a scratch directory for that subprocess, the same technique
# test_guards.py uses, NOT `monkeypatch.setattr(crew_config,
# "GLOBAL_CONFIG_PATH", ...)`, which only rebinds the attribute in THIS
# (pytest's own) process and has no effect on a child process at all.

def _global_home(tmp_path, body_text=None, body_json=None):
    """A fake HOME/USERPROFILE carrying (or not) a machine-global crew
    config, for a SUBPROCESS's environment."""
    home = tmp_path / "home"
    (home / ".claude" / "crew").mkdir(parents=True, exist_ok=True)
    path = home / ".claude" / "crew" / "config.json"
    if body_text is not None:
        path.write_text(body_text, encoding="utf-8")
    elif body_json is not None:
        path.write_text(json.dumps(body_json), encoding="utf-8")
    return str(home)


def _run_sh_with_home(root, home, tool_name, file_path, agent_type):
    return subprocess.run(
        [_BASH, _SH],
        input=_write_payload(tool_name, file_path, agent_type, str(root)),
        capture_output=True, text=True, check=False, cwd=str(root),
        env=dict(os.environ, CLAUDE_PROJECT_DIR=str(root),
                  HOME=home, USERPROFILE=home),
    )


@needs_bash
def test_directory_at_repo_config_path_forces_block_bash(tmp_path):
    """Must-block: BLOCK 1. `.crew/config.json` is a DIRECTORY -- present
    but unreadable -- with no global override at all."""
    root = crew_fixtures.make_repo(tmp_path, config=None)
    (root / ".crew" / "config.json").mkdir()
    home = _global_home(tmp_path)
    proc = _run_sh_with_home(root, home, "Write",
                              str(root / "src" / "app.py"), "pm")
    assert proc.returncode == 2, proc.stdout


@needs_bash
def test_dangling_global_config_symlink_forces_block_bash(tmp_path):
    """Must-block: round-3 BLOCK 1's own repro. The GLOBAL config path is
    a symlink pointing at a target that does not exist; repo `roleWrites`
    is unset."""
    root = crew_fixtures.make_repo(tmp_path, config={})
    home = tmp_path / "home"
    (home / ".claude" / "crew").mkdir(parents=True, exist_ok=True)
    global_path = home / ".claude" / "crew" / "config.json"
    missing_target = tmp_path / "moved-or-deleted-global-config.json"
    if not _make_symlink(missing_target, global_path):
        pytest.skip("could not create a symlink on this platform/user")
    assert not missing_target.exists(), "the fixture must NOT create the target"

    proc = _run_sh_with_home(root, str(home), "Write",
                              str(root / "src" / "app.py"), "pm")
    assert proc.returncode == 2, proc.stdout


@needs_bash
def test_explicit_guards_null_forces_block_bash(tmp_path):
    """Must-block: BLOCK 2. Explicit `{"guards": null}`, no global
    override -- distinct from an absent `guards` key, which stays `off`
    (see test_valid_config_with_no_guards_key_is_not_corrupt_stays_off_bash)."""
    root = crew_fixtures.make_repo(tmp_path, config=None)
    (root / ".crew" / "config.json").write_text(
        json.dumps({"guards": None}), encoding="utf-8")
    home = _global_home(tmp_path)
    proc = _run_sh_with_home(root, home, "Write",
                              str(root / "src" / "app.py"), "pm")
    assert proc.returncode == 2, proc.stdout


@needs_bash
def test_corrupt_global_config_forces_block_even_with_valid_repo_bash(tmp_path):
    """Must-block: BLOCK 5. Repo config is valid and empty (`{}`); the
    machine-global config is present but corrupt."""
    root = crew_fixtures.make_repo(tmp_path, config={})
    home = _global_home(tmp_path, body_text="{not valid json")
    proc = _run_sh_with_home(root, home, "Write",
                              str(root / "src" / "app.py"), "pm")
    assert proc.returncode == 2, proc.stdout


@needs_bash
def test_corrupt_repo_config_forces_block_even_with_valid_global_report_bash(tmp_path):
    """Must-block: BLOCK 6, the gap the FIRST corruption fix could not
    see. Global policy is VALID at `report` (never blocks); repo config
    previously said `block` but is now corrupt. The ordinary ratchet
    alone would resolve to `report` from the surviving global layer --
    must NOT: any corrupt layer forces block unconditionally."""
    root = crew_fixtures.make_repo(
        tmp_path, config={"guards": {"roleWrites": "block"}})
    (root / ".crew" / "config.json").write_text(
        "{not valid json", encoding="utf-8")
    home = _global_home(tmp_path, body_json={"guards": {"roleWrites": "report"}})
    proc = _run_sh_with_home(root, home, "Write",
                              str(root / "src" / "app.py"), "pm")
    assert proc.returncode == 2, proc.stdout


@needs_bash
def test_valid_global_report_with_unset_repo_stays_report_bash(tmp_path):
    """Must-allow twin of BLOCK 6: BOTH layers VALID (repo unset -> off,
    global `report`) must resolve to `report` -- allowed, but logged --
    not swept into the corruption override just because a `report` write
    is technically "not blocked"."""
    root = crew_fixtures.make_repo(tmp_path, config={})
    home = _global_home(tmp_path, body_json={"guards": {"roleWrites": "report"}})
    proc = _run_sh_with_home(root, home, "Write",
                              str(root / "src" / "app.py"), "pm")
    assert proc.returncode == 0, proc.stderr
    log = (root / ".crew" / "guard.log").read_text(encoding="utf-8")
    assert "\treport\treport\t" in log, log


# --- BLOCK 7: the exception handler must never crash itself ---------------

@needs_bash
def test_malformed_cwd_array_does_not_crash_the_exception_handler_bash(tmp_path):
    """Must-not-crash: `CLAUDE_PROJECT_DIR` unset, `cwd` is a JSON array.
    An earlier draft let `root` become `[1]` unsanitised, and the
    exception handler's OWN `.crew/guard.log` logging call then raised a
    SECOND, uncaught `TypeError` building a path from it -- crashing with
    a non-blocking exit 1. `root="."` now resolves via the subprocess's
    cwd (the fixture repo), so this reaches a real decision: `pm` writing
    `app.py` (not under any permitted prefix) must BLOCK, not crash."""
    root = crew_fixtures.make_repo(
        tmp_path, config={"guards": {"roleWrites": "block"}})
    env = os.environ.copy()
    env.pop("CLAUDE_PROJECT_DIR", None)
    payload = json.dumps({
        "tool_name": "Write", "agent_type": "pm", "cwd": [1],
        "tool_input": {"file_path": "app.py"},
    })
    proc = subprocess.run(
        [_BASH, _SH], input=payload, capture_output=True, text=True,
        check=False, env=env, cwd=str(root))
    assert "Traceback" not in proc.stderr, proc.stderr
    assert proc.returncode == 2, (
        "root='.' resolves via cwd to the fixture repo; pm writing 'app.py' "
        "is out of scope and must block, not crash. stdout: " + proc.stdout
        + " stderr: " + proc.stderr)


# --- Round 5 BLOCK: a `\\?\` extended-length path must never be --------
# --- NORMALISED and classified -- it must not be classified at all -----
#
# The FIX-2 test this section used to contain proved the OPPOSITE of what
# it should have: `\\?\` exists so Win32 will SKIP its own path
# normalisation for one call -- trailing dots/spaces are kept, `..` is
# never collapsed -- so stripping the prefix and classifying the bare
# remainder answers a question about a DIFFERENT path than the one
# Windows actually opens. Codex round 5's repro: with `.crew.` (a
# trailing dot) an actual, distinct directory on disk, outside every
# scope `pm` is granted, `\\?\C:\repo\.crew.\app.py` stripped to
# `C:\repo\.crew.\app.py`, which this module's own path handling then
# further normalised to `C:\repo\.crew\app.py` -- in scope -- and
# allowed a write that really lands in `.crew.`, never `.crew`. Fixed by
# refusing to classify a `\\?\` path at all: `pm` and every `_DENY_ROLES`
# member fail CLOSED (block) unconditionally; every other role, and a
# call with no `agent_type`, allows, since Claude Code itself never
# emits this form for a `Write`/`Edit` call.

@needs_bash
@pytest.mark.skipif(not sys.platform.startswith("win"),
                     reason="\\\\?\\ extended-length paths are a Windows concept")
def test_extended_length_prefix_path_blocks_for_pm_bash(tmp_path):
    """Must-block: Codex round 5's exact repro. `.crew.` (trailing dot)
    is a real, distinct, out-of-scope directory; the extended-length
    form must never be normalised down to the in-scope `.crew`."""
    root = crew_fixtures.make_repo(
        tmp_path, config={"guards": {"roleWrites": "block"}})
    _make_dotted_dir(root / ".crew.")
    extended = "\\\\?\\" + str(root) + "\\.crew.\\app.py"
    proc = _run_sh(root, "Write", extended, "pm")
    assert proc.returncode == 2, (
        "a \\\\?\\ path must never be normalised and classified -- pm must "
        "be refused outright, not allowed via a stripped-and-renormalised "
        "form that silently drops the trailing dot. stdout: " + proc.stdout)


@needs_pwsh_windows
def test_extended_length_prefix_path_blocks_for_pm_powershell(tmp_path):
    """PowerShell twin of the bash must-block case above."""
    root = crew_fixtures.make_repo(
        tmp_path, config={"guards": {"roleWrites": "block"}})
    _make_dotted_dir(root / ".crew.")
    extended = "\\\\?\\" + str(root) + "\\.crew.\\app.py"
    proc = _run_ps1(root, "Write", extended, "pm")
    assert proc.returncode == 2, proc.stderr


@needs_bash
@pytest.mark.skipif(not sys.platform.startswith("win"),
                     reason="\\\\?\\ extended-length paths are a Windows concept")
def test_extended_length_prefix_path_allows_for_unrestricted_role_bash(tmp_path):
    """Must-allow: the SAME `.crew.` repro, for `developer` -- an
    unrestricted role. An extended-length `\\\\?\\` path is refused only
    for a role this
    table already restricts; it is not a blanket refusal."""
    root = crew_fixtures.make_repo(
        tmp_path, config={"guards": {"roleWrites": "block"}})
    _make_dotted_dir(root / ".crew.")
    extended = "\\\\?\\" + str(root) + "\\.crew.\\app.py"
    proc = _run_sh(root, "Write", extended, "developer")
    assert proc.returncode == 0, proc.stderr


@needs_pwsh_windows
def test_extended_length_prefix_path_allows_for_unrestricted_role_powershell(tmp_path):
    """PowerShell twin of the bash must-allow case above."""
    root = crew_fixtures.make_repo(
        tmp_path, config={"guards": {"roleWrites": "block"}})
    _make_dotted_dir(root / ".crew.")
    extended = "\\\\?\\" + str(root) + "\\.crew.\\app.py"
    proc = _run_ps1(root, "Write", extended, "developer")
    assert proc.returncode == 0, proc.stderr


@needs_bash
@pytest.mark.skipif(not sys.platform.startswith("win"),
                     reason="\\\\?\\ extended-length paths are a Windows concept")
def test_extended_length_prefix_path_allows_with_no_agent_type_bash(tmp_path):
    """Must-allow: a call with no `agent_type` at all is not `pm` and is
    not in `_DENY_ROLES` (`None` is neither), so it must allow exactly
    like an unrestricted role does."""
    root = crew_fixtures.make_repo(
        tmp_path, config={"guards": {"roleWrites": "block"}})
    _make_dotted_dir(root / ".crew.")
    extended = "\\\\?\\" + str(root) + "\\.crew.\\app.py"
    proc = _run_sh(root, "Write", extended, None)
    assert proc.returncode == 0, proc.stderr


# --- BLOCK 4: the BOM strip lives in Python, shared by both flavours ------

@needs_bash
def test_utf8_bom_on_stdin_does_not_bypass_bash_enforcement(tmp_path):
    """Must-block: a leading UTF-8 BOM plus an otherwise well-formed `pm`
    `Write` payload targeting an out-of-scope path must not read as
    unparseable JSON and allow unjudged. `role-write-guard.sh`'s
    `INPUT=$(cat)` was already byte-transparent -- the gap was entirely on
    the PYTHON side, which used to trust `sys.stdin.read()` without
    stripping a BOM first, so only role-write-guard.ps1 (which had its
    OWN BOM strip from round 2) was protected."""
    root = crew_fixtures.make_repo(
        tmp_path, config={"guards": {"roleWrites": "block"}})
    payload = json.dumps({"tool_name": "Write",
                           "tool_input": {"file_path": str(root / "src" / "app.py")},
                           "agent_type": "pm", "cwd": str(root)})
    bom = b"\xef\xbb\xbf"
    proc = subprocess.run(
        [_BASH, _SH], input=bom + payload.encode("utf-8"),
        capture_output=True, check=False,
        env=dict(os.environ, CLAUDE_PROJECT_DIR=str(root)), cwd=str(root))
    assert proc.returncode == 2, (
        "stdout: " + proc.stdout.decode("utf-8", "replace")
        + " stderr: " + proc.stderr.decode("utf-8", "replace"))


@needs_bash
def test_pythonutf8_forced_even_when_caller_env_disables_it_bash(tmp_path):
    """Must-block, verified via STDERR BYTES -- NOT `.crew/guard.log`,
    which `_log_row` writes with an explicit `encoding="utf-8"` regardless
    of PYTHONUTF8/PYTHONIOENCODING and so cannot distinguish this fix from
    its absence (an earlier draft of this test checked the log and passed
    whether the sabotage was applied or not, for exactly that reason).
    role_write_guard.py's stdout/stderr writes of a non-ASCII path DO
    depend on PYTHONUTF8/PYTHONIOENCODING -- only stdin READING is now
    environment-independent, via `sys.stdin.buffer` -- so
    role-write-guard.sh must force both in the CHILD's environment
    regardless of what the CALLER's environment already set."""
    root = crew_fixtures.make_repo(
        tmp_path, config={"guards": {"roleWrites": "block"}})
    target = str(root / "café" / "app.py")
    env = dict(os.environ, CLAUDE_PROJECT_DIR=str(root))
    env["PYTHONUTF8"] = "0"
    env.pop("PYTHONIOENCODING", None)
    proc = subprocess.run(
        [_BASH, _SH],
        input=_write_payload("Write", target, "pm", str(root)).encode("utf-8"),
        capture_output=True, check=False, env=env, cwd=str(root))
    stderr = proc.stderr.decode("utf-8", errors="replace")
    assert proc.returncode == 2, stderr
    assert "café" in stderr, (
        "the accented character in the refusal message was not written as "
        "UTF-8 -- PYTHONUTF8/PYTHONIOENCODING were not forced in the child "
        "environment. got: " + repr(stderr))


# --- BLOCK 3: PYTHONUTF8/PYTHONIOENCODING forced regardless of caller env -

@needs_pwsh_windows
def test_pythonutf8_forced_even_when_caller_env_disables_it_powershell(tmp_path):
    """Must-block: the CALLER's environment sets `PYTHONUTF8=0` and unsets
    `PYTHONIOENCODING` -- role-write-guard.ps1 must still force both in the
    CHILD's environment (and role_write_guard.py reads stdin as raw bytes
    regardless either way), so a junction with an ACCENTED name escaping
    to an in-repo-but-out-of-scope directory is still correctly resolved
    and refused, not silently misclassified through mojibake."""
    root = crew_fixtures.make_repo(
        tmp_path, config={"guards": {"roleWrites": "block"}})
    out_of_scope_dir = root / "src"
    out_of_scope_dir.mkdir()
    link = root / ".crew" / "caf\u00e9"
    if not _make_junction(out_of_scope_dir, link):
        pytest.skip("could not create a junction on this platform/user")

    target = str(link / "app.py")
    payload = json.dumps({"tool_name": "Write",
                           "tool_input": {"file_path": target},
                           "agent_type": "pm", "cwd": str(root)})
    env = dict(os.environ, CLAUDE_PROJECT_DIR=str(root))
    env["PYTHONUTF8"] = "0"
    env.pop("PYTHONIOENCODING", None)
    proc = subprocess.run(
        [_PWSH, "-NoProfile", "-NonInteractive", "-File", _PS1],
        input=payload.encode("utf-8"), capture_output=True, check=False,
        env=env, cwd=str(root))
    assert proc.returncode == 2, (
        "stdout: " + proc.stdout.decode("utf-8", "replace")
        + " stderr: " + proc.stderr.decode("utf-8", "replace"))


@needs_pwsh_windows
def test_pythonutf8_forced_writes_correct_utf8_stderr_powershell(tmp_path):
    """The bash twin's exact assertion, on role-write-guard.ps1: the
    junction-based test above proves the DECISION survives (primarily
    via role_write_guard.py's own `sys.stdin.buffer` read, which is
    environment-independent), but that alone does not prove
    PYTHONUTF8/PYTHONIOENCODING are actually forced -- only the STDERR
    BYTES prove that, since `.crew/guard.log` is written with an explicit
    `encoding="utf-8"` regardless of either variable."""
    root = crew_fixtures.make_repo(
        tmp_path, config={"guards": {"roleWrites": "block"}})
    target = str(root / "café" / "app.py")
    payload = json.dumps({"tool_name": "Write",
                           "tool_input": {"file_path": target},
                           "agent_type": "pm", "cwd": str(root)})
    env = dict(os.environ, CLAUDE_PROJECT_DIR=str(root))
    env["PYTHONUTF8"] = "0"
    env.pop("PYTHONIOENCODING", None)
    proc = subprocess.run(
        [_PWSH, "-NoProfile", "-NonInteractive", "-File", _PS1],
        input=payload.encode("utf-8"), capture_output=True, check=False,
        env=env, cwd=str(root))
    stderr = proc.stderr.decode("utf-8", errors="replace")
    assert proc.returncode == 2, stderr
    assert "café" in stderr, (
        "the accented character in the refusal message was not written as "
        "UTF-8 -- PYTHONUTF8/PYTHONIOENCODING were not forced in the child "
        "environment. got: " + repr(stderr))


# --- FIX 1: Resolve-CrewPython must check the candidate's exit status -----

# `_resolve_role_write_python` needs nothing beyond bash builtins (`command
# -v`, `[`, `printf`) to reject a candidate, but the SCRIPT AROUND it does
# not: `dirname` at the top (line 12) and `cat` (line 15, `INPUT=$(cat)`)
# run unconditionally before resolution even starts, and once resolution
# fails, `_role_write_fallback_role` reaches for `grep`, `head`, `sed` and
# `tr` to pull `agent_type` out of the raw JSON without python. Two tests
# below replace `$PATH` outright to prove "no usable python resolves" --
# and on this repo's own Windows/MSYS dev machine that was invisible,
# because MSYS bash still finds its own coreutils regardless of what $PATH
# says. Reported 2026-09-24 by CI (Ubuntu): with $PATH pointing at NOTHING
# but the fake python wrapper directory, `dirname`/`cat`/`grep`/`head`/`sed`/
# `tr` are ALL missing too, so the script never reaches a clean "no usable
# python found" decision at all -- it prints six "command not found" lines,
# `_role_write_fallback_role` silently returns empty because `grep`/`sed`
# aren't there to extract `pm` from the JSON, and the guard falls through to
# the UNRESTRICTED-role branch and exits 0. That is a gap in what these two
# tests hand the subprocess, not a resolver defect: a real Claude Code
# session's PATH always has coreutils on it (bash could not run hooks at
# all otherwise), so a PATH with fake pythons but no coreutils tests a
# situation that cannot occur in production.
#
# The fix is a PATH that supplies the six tools above and NOTHING else --
# specifically, nothing that could also resolve a real python. Simply
# re-appending the caller's real $PATH (the pattern used elsewhere in this
# file, e.g. `test_windowsapps_python_stub_does_not_silence_bash_enforcement`)
# does not work here: on the actual CI runner, `actions/setup-python` puts a
# directory on PATH with a WORKING `python` AND `python3`, so appending it
# would make one of the two "must find nothing" tests below resolve a real
# interpreter under the one name (`python`) their fake directories do not
# shadow, silently changing what the test proves. And on Ubuntu specifically,
# `dirname`/`cat`/`grep`/`sed`/`tr` and `python3` all live in the SAME
# directory (`/usr/bin`), so there is no real-PATH entry that offers one
# without the other -- filtering by directory cannot separate them.
#
# A thin shell wrapper per tool, each `exec`ing the tool's own real absolute
# path, sidesteps both problems: the wrapper directory contains only the six
# names below, so it can never resolve `python`/`python3`/`py`, and `exec`ing
# the ORIGINAL absolute path (not a copy) means a tool whose runtime depends
# on files alongside it (`dirname.exe` needing `msys-2.0.dll` next to it on
# Windows) still finds them, because it still runs from its real location.
_MINIMAL_COREUTILS = ("dirname", "cat", "grep", "head", "sed", "tr")


def _to_posix_path(path):
    """`C:\\Program Files\\Git\\usr\\bin\\dirname.exe` -> `/c/Program
    Files/Git/usr/bin/dirname.exe`, the same manual conversion
    `_resolve_role_write_python` itself falls back to when `cygpath` is not
    on PATH -- deliberately not shelling out to `cygpath` here, since the
    whole point of this helper is to build a PATH before any such tool is
    known to be reachable. A no-op on POSIX paths, which never match the
    drive-letter pattern."""
    text = str(path)
    if len(text) >= 2 and text[1] == ":" and text[0].isalpha():
        return "/" + text[0].lower() + text[2:].replace("\\", "/")
    return text.replace("\\", "/")


def _coreutils_only_path(tmp_path):
    """A PATH entry that can run `role-write-guard.sh` end to end but can
    never resolve a real python under any of the three names it tries --
    see the block comment above for why appending or filtering the real
    PATH cannot do both at once."""
    toolbin = tmp_path / "coreutils-only"
    toolbin.mkdir(exist_ok=True)
    for name in _MINIMAL_COREUTILS:
        real = shutil.which(name)
        assert real, (
            name + " is not on the real PATH -- cannot build a "
            "coreutils-only PATH for this test without it")
        wrapper = toolbin / name
        wrapper.write_text(
            '#!/bin/sh\nexec "' + _to_posix_path(real) + '" "$@"\n',
            encoding="ascii", newline="\n")
        os.chmod(wrapper, 0o755)
    return str(toolbin)


@needs_pwsh_windows
def test_candidate_nonzero_exit_status_is_rejected_powershell(tmp_path):
    """Must resolve to NOTHING (matching bash's `|| continue`): a python3
    wrapper that prints a real-looking interpreter path but exits 1 must
    be rejected, not accepted just because it produced output."""
    apps = tmp_path / "wrappers"
    apps.mkdir()
    wrapper = apps / "python3.cmd"
    wrapper.write_text(
        "@echo off\r\necho C:\\Fake\\python.exe\r\nexit /b 1\r\n",
        encoding="ascii")

    resolved = _print_python([str(apps)])
    assert resolved == "", (
        "a candidate that exits nonzero must be rejected even though it "
        "printed a plausible interpreter path. got: " + resolved)


@needs_bash
def test_bash_already_rejects_nonzero_exit_candidate(tmp_path):
    """The bash HALF of FIX 1's parity claim -- bash already gets this
    right via `real=$(...) || continue`; locked in here so a future change
    to `_resolve_role_write_python` cannot silently drop it.

    Asserted via the discriminating stderr message, not the exit code: since
    2026-09-24 total resolution failure fails closed for a restricted role
    (`pm`) exactly like a launch failure does, so both now exit 2 and only
    the message says which one actually happened -- "no usable python
    found" (resolver rejected the candidate) versus "could not launch the
    python interpreter" (resolver accepted, launch of role_write_guard.py
    itself failed). Pinning only the exit code here would make this test
    unable to tell those two apart."""
    apps = tmp_path / "wrappers"
    apps.mkdir()
    wrapper = apps / "python3"
    wrapper.write_text("#!/bin/sh\necho /fake/python\nexit 1\n",
                        encoding="ascii", newline="\n")
    os.chmod(wrapper, 0o755)

    root = crew_fixtures.make_repo(
        tmp_path, config={"guards": {"roleWrites": "block"}})
    env = os.environ.copy()
    # NOT `env["PATH"] = str(apps)` -- see `_coreutils_only_path`'s comment:
    # that used to strip out `dirname`/`cat`/`grep`/`head`/`sed`/`tr` along
    # with every real python, which is what turned this red on Linux CI
    # while passing locally on Windows/MSYS.
    env["PATH"] = os.pathsep.join([str(apps), _coreutils_only_path(tmp_path)])
    env["CLAUDE_PROJECT_DIR"] = str(root)
    proc = subprocess.run(
        [_BASH, _SH],
        input=_write_payload("Write", str(root / "src" / "app.py"), "pm", str(root)),
        capture_output=True, text=True, check=False, env=env, cwd=str(root))
    assert proc.returncode == 2, (
        "no usable python resolved (the only candidate exits nonzero) for "
        "restricted role 'pm', so the write must fail closed. stdout: "
        + proc.stdout + " stderr: " + proc.stderr)
    assert "no usable python found" in proc.stderr, (
        "expected the resolution-failure message, not the launch-failure "
        "one -- got: " + proc.stderr)


# --- Scope is judged on the REAL path, not the lexical one (round-1 BLOCK,
# redefined round-3 by a probe finding on the round-1 fix) -----------------
#
# Reported 2026-09-19: `.crew/link/app.py` fnmatches `.crew/**` on the
# STRING alone, so if `.crew/link` is a symlink or Windows junction pointing
# at `src/` (INSIDE the repo, just outside pm's permitted prefixes), `pm`
# was classified as writing in-scope while the write actually landed in
# `src/app.py`. That case is STILL refused -- see the "in-repo but
# out-of-scope" tests below.
#
# A SEPARATE probe on the round-1 fix found the real-path check had gone too
# far the other way for a target that resolves OUTSIDE the repo root
# entirely: the harness-sanctioned scratchpad under `AppData/Local/Temp/
# claude/<session>/scratchpad`, which every role including `pm` is told to
# use, was refused, because this guard's write-scope rule was never written
# to police anything outside the repo at all -- "outside every allowed
# prefix" and "outside the repo entirely" collapsed to the same "not in
# scope" answer. Fixed by judging `_is_outside_repo` on the REAL resolved
# path: `pm` writing to a target that resolves outside the repo root is
# `allow`, logged `outside-repo: ...`, WHETHER the tool call named that
# location directly (the scratchpad) or reached it through a symlink staged
# inside a path `pm` is trusted to write (`.crew/escape -> /elsewhere`) --
# see `classify`'s own docstring for why there is no separate "but the tool
# call NAMED a path inside the repo" carve-out.
#
# SKIP-labelled wherever this platform or this user cannot create the link
# kind being tested -- a link that could not be made proves nothing either
# way. `_make_symlink` (Python `os.symlink`), never bash `ln -s`: on the
# machine these were found on, bash's `ln -s` silently fell back to creating
# a PLAIN DIRECTORY rather than a real symlink, which would have made a
# must-block case here pass for the wrong reason -- `os.path.islink` guards
# every fixture that matters for a `block` assertion.

def _make_symlink(target, link):
    try:
        os.symlink(str(target), str(link), target_is_directory=True)
        return True
    except (OSError, NotImplementedError):
        return False


def _make_junction(target, link):
    if not sys.platform.startswith("win"):
        return False
    result = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(link), str(target)],
        capture_output=True, text=True, check=False)
    return result.returncode == 0


def _make_dotted_dir(path):
    """Create a directory whose name ends in a literal dot (e.g.
    `.crew.`) -- for real, on disk. An ORDINARY (non-extended-length)
    Win32 call strips a trailing dot at creation time, which would
    silently create `.crew` instead and defeat round 5's whole repro
    (that trailing dot is exactly what makes `.crew.` a DIFFERENT,
    genuinely out-of-scope directory from `.crew`). The `\\\\?\\` prefix
    makes Win32 skip that normalisation here too, the same way it does
    for the hook's own target path."""
    os.mkdir("\\\\?\\" + str(path))


@needs_bash
def test_symlink_escaping_the_repo_entirely_is_allowed_bash(tmp_path):
    """Must-allow: a symlink staged inside pm's own scope, whose target
    resolves OUTSIDE the repo root entirely, is not this guard's business --
    the write never touches anything under the repo."""
    root = crew_fixtures.make_repo(
        tmp_path, config={"guards": {"roleWrites": "block"}})
    outside = tmp_path / "outside"
    outside.mkdir()
    link = root / ".crew" / "link"
    if not _make_symlink(outside, link):
        pytest.skip("could not create a symlink on this platform/user")

    proc = _run_sh(root, "Write", str(link / "app.py"), "pm")
    assert proc.returncode == 0, proc.stderr
    log = (root / ".crew" / "guard.log").read_text(encoding="utf-8")
    assert "outside-repo" in log, log


@needs_pwsh_windows
def test_junction_escaping_the_repo_entirely_is_allowed_powershell(tmp_path):
    """PowerShell twin of the symlink case above, with a real Windows
    junction (`mklink /J`, no elevation needed)."""
    root = crew_fixtures.make_repo(
        tmp_path, config={"guards": {"roleWrites": "block"}})
    outside = tmp_path / "outside"
    outside.mkdir()
    link = root / ".crew" / "link"
    if not _make_junction(outside, link):
        pytest.skip("could not create a junction on this platform/user")

    proc = _run_ps1(root, "Write", str(link / "app.py"), "pm")
    assert proc.returncode == 0, proc.stderr


@needs_bash
def test_symlink_inside_scope_is_still_allowed_bash(tmp_path):
    """Must-allow twin: a link that stays INSIDE the permitted prefix must
    not become collateral damage of closing the in-repo escape."""
    root = crew_fixtures.make_repo(
        tmp_path, config={"guards": {"roleWrites": "block"}})
    inside_target = root / ".crew" / "real-subdir"
    inside_target.mkdir()
    link = root / ".crew" / "link"
    if not _make_symlink(inside_target, link):
        pytest.skip("could not create a symlink on this platform/user")

    proc = _run_sh(root, "Write", str(link / "app.py"), "pm")
    assert proc.returncode == 0, proc.stderr


@needs_bash
def test_repo_internal_symlink_to_an_out_of_scope_prefix_is_still_refused_bash(tmp_path):
    """Must-block: the case the outside-repo exception must NOT catch. The
    resolved target (`src/`) is still INSIDE the repo root, just outside
    pm's permitted prefixes -- `_is_outside_repo` is false for it, so the
    ordinary `_pm_in_scope` pattern match still runs and still refuses it."""
    root = crew_fixtures.make_repo(
        tmp_path, config={"guards": {"roleWrites": "block"}})
    out_of_scope_dir = root / "src"
    out_of_scope_dir.mkdir()
    link = root / ".crew" / "escape"
    if not _make_symlink(out_of_scope_dir, link):
        pytest.skip("could not create a symlink on this platform/user")
    assert os.path.islink(str(link)), (
        "the fixture must produce a REAL symlink, not a plain directory -- "
        "bash's `ln -s` silently falls back to one on this kind of host")

    proc = _run_sh(root, "Write", str(link / "app.py"), "pm")
    assert proc.returncode == 2, (
        "a symlink staged INSIDE pm's own scope, pointing at another "
        "IN-REPO directory outside that scope, must still be refused -- "
        "it never leaves the repo root, so the outside-repo exception must "
        "not apply. stdout: " + proc.stdout)


@needs_pwsh_windows
def test_repo_internal_junction_to_an_out_of_scope_prefix_is_still_refused_powershell(tmp_path):
    """PowerShell/junction twin of the symlink case above -- junction
    coverage for the still-refused, in-repo-but-out-of-scope escape, kept
    separate from the now-allowed outside-the-repo junction case above."""
    root = crew_fixtures.make_repo(
        tmp_path, config={"guards": {"roleWrites": "block"}})
    out_of_scope_dir = root / "src"
    out_of_scope_dir.mkdir()
    link = root / ".crew" / "escape"
    if not _make_junction(out_of_scope_dir, link):
        pytest.skip("could not create a junction on this platform/user")

    proc = _run_ps1(root, "Write", str(link / "app.py"), "pm")
    assert proc.returncode == 2, (
        "a junction staged INSIDE pm's own scope, pointing at another "
        "IN-REPO directory outside that scope, must still be refused. "
        "stdout: " + proc.stdout)


def test_resolve_real_target_walks_up_to_the_deepest_existing_ancestor(tmp_path):
    """Direct unit test of the walk-up, independent of the hook process --
    including the case that matters most: the FILE does not exist yet."""
    real_dir = tmp_path / "real"
    real_dir.mkdir()
    link = tmp_path / "link"
    if not _make_symlink(real_dir, link):
        pytest.skip("could not create a symlink on this platform/user")

    target = str(link / "brand-new-file.py")  # does not exist
    resolved = role_write_guard._resolve_real_target(target)  # pylint: disable=protected-access
    assert os.path.dirname(resolved) == os.path.realpath(str(real_dir))
    assert os.path.basename(resolved) == "brand-new-file.py"


# --- Round 3 BLOCK 3 / Round 4 BLOCK 1+2: `..` vs a symlink/junction is a
# --- REAL, OPPOSITE-DIRECTION platform difference --------------------------
#
# Round 3's fix made `..` apply AFTER symlink resolution everywhere
# (resolve-then-pop), matching POSIX kernel semantics. Codex round 4 found
# that this is *wrong on Windows*, not just imprecise: Win32's path
# canonicaliser collapses a literal `..` LEXICALLY, in the path string,
# before the filesystem/reparse-point layer ever sees it -- so a junction
# positioned where `..` pops past it is never traversed at all. The two
# platforms genuinely disagree, in both directions:
#   - `.crew/link/../app.py` (link -> src, i.e. IN scope popping OUT):
#     POSIX follows the symlink first, then pops `..` against the
#     resolved parent (src) -> lands OUTSIDE .crew -> must block.
#     Windows collapses `.crew/link/..` to `.crew` lexically, before the
#     junction is ever consulted -> really writes to `.crew/app.py` ->
#     must ALLOW. Blocking it, as round 3 did on this platform, refuses a
#     write Windows itself would have let land in scope.
#   - `src/link/../new.py` (link -> .crew/subdir, i.e. OUT of scope
#     popping IN): Windows collapses `src/link/..` to `src` lexically
#     -> really writes to `src/new.py`, out of scope -> must BLOCK.
#     Round 3's resolve-then-pop logic followed the junction first,
#     landed in `.crew`, and wrongly ALLOWED it.
# `_resolve_real_target` now dispatches on `os.name`: `_resolve_real_target_
# windows` collapses `..` lexically first (splitting on both `\` and `/`,
# fixing round 4 BLOCK 1's forward-slash gap in the same pass), then walks
# the `..`-free path resolving junctions/symlinks component by component;
# `_resolve_real_target_posix` keeps round 3's resolve-then-pop walk,
# splitting only on `/` (backslash is a legal POSIX filename character).

# There is deliberately no always-running direct unit test of
# `_resolve_real_target_posix`'s real symlink-mid-walk behaviour: its path
# arithmetic reconstructs each probe as `"/" + "/".join(parts)`, which
# assumes a POSIX root. On this Windows dev machine that reconstruction
# never matches a real disk path (a Windows drive letter like `C:` is not
# a valid POSIX root component), so `os.path.lexists` never fires true and
# the walk silently degrades to pure lexical popping -- the exact bug this
# function exists to fix, reproduced by the test harness itself rather
# than the code. Confirmed by hand: probing `_resolve_real_target_posix`
# directly against a real symlink on this machine returns the LEXICALLY
# popped answer even though the fix is correct, which would make a
# "passing" direct unit test here prove nothing. The only test that
# exercises this function's real symlink resolution is the end-to-end
# twin below, correctly skipped on Windows and real on a genuine POSIX
# host, where `tmp_path`, `os.getcwd()` and disk paths are natively
# forward-slash-rooted and the lexists/realpath checks fire as designed.


@needs_windows
def test_resolve_real_target_windows_collapses_dotdot_before_symlink(tmp_path):
    """Direct unit test of `_resolve_real_target_windows` ITSELF, proving
    the lexical-first algorithm in BOTH directions from Codex round 4's
    guidance -- runs on any host OS since it calls the platform-specific
    function directly rather than going through the `os.name` dispatch."""
    in_scope_target = tmp_path / "src"
    in_scope_target.mkdir()
    link_in_scope = tmp_path / ".crew" / "link"
    link_in_scope.parent.mkdir()
    if not _make_symlink(in_scope_target, link_in_scope):
        pytest.skip("could not create a symlink on this platform/user")

    # `.crew/link/../new.py`, link -> src: Windows collapses `link/..` to
    # `.crew` BEFORE the link/junction is ever consulted, so the link is
    # never followed and this lands back inside `.crew`.
    allow_target = str(link_in_scope) + "\\..\\new.py"
    # pylint: disable-next=protected-access
    allow_resolved = role_write_guard._resolve_real_target_windows(allow_target)
    assert os.path.dirname(allow_resolved) == os.path.realpath(
        str(tmp_path / ".crew")), (
        "Windows: `.crew/link/../new.py` with link -> src must resolve "
        "inside .crew (the .. cancels the link lexically before it is "
        "ever followed). got: " + allow_resolved)

    out_of_scope_target = tmp_path / ".crew" / "subdir"
    out_of_scope_target.mkdir()
    link_out_of_scope = tmp_path / "src2"
    if not _make_symlink(out_of_scope_target, link_out_of_scope):
        pytest.skip("could not create a symlink on this platform/user")

    # `src2/../new.py`, where `src2` is itself the link (-> an in-scope
    # directory): the `..` must pop the link's own lexical position
    # without ever resolving into what it points to. This is the same
    # shape as round 4 BLOCK 2's `src/link/../new.py` repro, simplified
    # to a link one level shallower.
    block_target = str(link_out_of_scope) + "\\..\\new.py"
    # pylint: disable-next=protected-access
    block_resolved = role_write_guard._resolve_real_target_windows(block_target)
    assert os.path.dirname(block_resolved) == os.path.realpath(str(tmp_path)), (
        "Windows: a `..` right after a link must pop the link's own "
        "lexical position, never resolve into the link's target first. "
        "got: " + block_resolved)


@needs_windows
def test_resolve_real_target_windows_splits_on_forward_slashes(tmp_path):
    """Direct unit test: round 4 BLOCK 1. A Windows target spelled with
    forward slashes must still walk and resolve a junction/symlink in
    it, not degrade to one opaque unresolved component."""
    real_dir = tmp_path / "real"
    real_dir.mkdir()
    link = tmp_path / "fwdlink"
    if not _make_symlink(real_dir, link):
        pytest.skip("could not create a symlink on this platform/user")

    forward = str(link).replace("\\", "/") + "/new.py"
    # pylint: disable-next=protected-access
    resolved = role_write_guard._resolve_real_target_windows(forward)
    assert os.path.dirname(resolved) == os.path.realpath(str(real_dir)), (
        "a forward-slash path must resolve the symlink/junction exactly "
        "like a backslash one. got: " + resolved)
    assert os.path.basename(resolved) == "new.py"


@needs_windows
def test_resolve_real_target_windows_splits_on_mixed_separators(tmp_path):
    """Direct unit test: a path mixing `\\` and `/` in the same string
    must still walk component by component and resolve the link."""
    real_dir = tmp_path / "real"
    real_dir.mkdir()
    link = tmp_path / "mixedlink"
    if not _make_symlink(real_dir, link):
        pytest.skip("could not create a symlink on this platform/user")

    mixed = str(tmp_path).replace("/", "\\") + "\\mixedlink/sub\\..\\new.py"
    # pylint: disable-next=protected-access
    resolved = role_write_guard._resolve_real_target_windows(mixed)
    assert os.path.dirname(resolved) == os.path.realpath(str(real_dir)), (
        "a mixed \\/-separator path must resolve identically to an "
        "all-backslash one. got: " + resolved)
    assert os.path.basename(resolved) == "new.py"


@needs_windows
@needs_bash
def test_windows_link_pointing_out_of_scope_with_dotdot_still_allows_bash(tmp_path):
    """Must-allow, end to end (corrects round 3's must-block expectation
    for this same repro). `.crew/link` is a symlink to `src/subdir`
    (in-repo, out-of-scope); the tool call names `.crew/link/../app.py`.
    On this machine the bash shim still resolves through a native Windows
    Python, so `os.name == "nt"` regardless of which shell launched it --
    `..` collapses lexically BEFORE the link is ever consulted, so the
    real write lands at `.crew/app.py`, in scope."""
    root = crew_fixtures.make_repo(
        tmp_path, config={"guards": {"roleWrites": "block"}})
    out_of_scope_dir = root / "src" / "subdir"
    out_of_scope_dir.mkdir(parents=True)
    link = root / ".crew" / "link"
    if not _make_symlink(out_of_scope_dir, link):
        pytest.skip("could not create a symlink on this platform/user")

    target = str(link / ".." / "app.py")
    proc = _run_sh(root, "Write", target, "pm")
    assert proc.returncode == 0, (
        "on Windows, `.crew/link/../app.py` really writes to .crew/app.py "
        "because .. collapses lexically before the link is followed -- "
        "this must be allowed, not blocked. stdout: " + proc.stdout)


@needs_pwsh_windows
def test_windows_link_pointing_out_of_scope_with_dotdot_still_allows_powershell(tmp_path):
    """PowerShell/junction twin of the bash case above."""
    root = crew_fixtures.make_repo(
        tmp_path, config={"guards": {"roleWrites": "block"}})
    out_of_scope_dir = root / "src" / "subdir"
    out_of_scope_dir.mkdir(parents=True)
    link = root / ".crew" / "link"
    if not _make_junction(out_of_scope_dir, link):
        pytest.skip("could not create a junction on this platform/user")

    target = str(link / ".." / "app.py")
    proc = _run_ps1(root, "Write", target, "pm")
    assert proc.returncode == 0, proc.stderr


@needs_windows
@needs_bash
def test_windows_link_staged_out_of_scope_escapes_via_dotdot_blocks_bash(tmp_path):
    """Must-block, end to end: round 4 BLOCK 2's own repro. `src/link` is
    a symlink to `.crew/subdir` (in scope); the tool call names
    `src/link/../new.py`. `..` collapses `src/link/..` to `src`
    lexically, before the link is ever consulted, so the real write
    lands at `src/new.py` -- out of scope."""
    root = crew_fixtures.make_repo(
        tmp_path, config={"guards": {"roleWrites": "block"}})
    in_scope_dir = root / ".crew" / "subdir"
    in_scope_dir.mkdir(parents=True)
    link = root / "src" / "link"
    link.parent.mkdir(parents=True)
    if not _make_symlink(in_scope_dir, link):
        pytest.skip("could not create a symlink on this platform/user")

    target = str(link / ".." / "new.py")
    proc = _run_sh(root, "Write", target, "pm")
    assert proc.returncode == 2, (
        "on Windows, src/link/../new.py really writes to src/new.py "
        "because .. collapses lexically before the link is followed -- "
        "resolving into the link's target (.crew) first is wrong and "
        "must not allow this write. stdout: " + proc.stdout)


@needs_pwsh_windows
def test_windows_link_staged_out_of_scope_escapes_via_dotdot_blocks_powershell(tmp_path):
    """PowerShell/junction twin of the bash case above."""
    root = crew_fixtures.make_repo(
        tmp_path, config={"guards": {"roleWrites": "block"}})
    in_scope_dir = root / ".crew" / "subdir"
    in_scope_dir.mkdir(parents=True)
    link = root / "src" / "link"
    link.parent.mkdir(parents=True)
    if not _make_junction(in_scope_dir, link):
        pytest.skip("could not create a junction on this platform/user")

    target = str(link / ".." / "new.py")
    proc = _run_ps1(root, "Write", target, "pm")
    assert proc.returncode == 2, proc.stderr


@needs_bash
def test_dotdot_without_a_symlink_still_resolves_normally_bash(tmp_path):
    """Must-allow: an ordinary `..` with NO symlink anywhere in the path
    must still resolve exactly as before -- the fix must not become
    "refuse every path containing .."."""
    root = crew_fixtures.make_repo(
        tmp_path, config={"guards": {"roleWrites": "block"}})
    (root / ".crew" / "subdir").mkdir(parents=True)
    target = str(root / ".crew" / "subdir" / ".." / "TODO.md")
    proc = _run_sh(root, "Write", target, "pm")
    assert proc.returncode == 0, proc.stderr


@pytest.mark.skipif(
    os.name == "nt",
    reason="this suite's bash runner still resolves through a native "
           "Windows python even when launched from Git Bash, so the "
           "POSIX resolve-then-pop branch of _resolve_real_target is "
           "never actually dispatched on this machine; this locks in "
           "the expectation for a real POSIX crew installation and is "
           "the direct-unit-test POSIX coverage's end-to-end twin")
@needs_bash
def test_posix_link_pointing_out_of_scope_with_dotdot_blocks_bash(tmp_path):
    """The POSIX twin of the two Windows end-to-end tests above. On a
    real POSIX host, `.crew/link/../app.py` (link -> src/subdir) resolves
    the symlink FIRST and pops `..` against the RESOLVED parent (src),
    landing in `src/app.py` -- out of scope, must block. This is the
    OPPOSITE outcome from the Windows case, which is exactly why
    `_resolve_real_target` dispatches on `os.name` rather than using one
    algorithm everywhere."""
    root = crew_fixtures.make_repo(
        tmp_path, config={"guards": {"roleWrites": "block"}})
    out_of_scope_dir = root / "src" / "subdir"
    out_of_scope_dir.mkdir(parents=True)
    link = root / ".crew" / "link"
    if not _make_symlink(out_of_scope_dir, link):
        pytest.skip("could not create a symlink on this platform/user")

    target = str(link / ".." / "app.py")
    proc = _run_sh(root, "Write", target, "pm")
    assert proc.returncode == 2, (
        "on a real POSIX host this must still block: resolve-then-pop "
        "lands in src/app.py, out of scope. stdout: " + proc.stdout)


# --- FIX: a different-drive target is PROVEN outside the repo, not -------
# --- "cannot classify" -----------------------------------------------------

@pytest.mark.skipif(not sys.platform.startswith("win"),
                     reason="drive letters are a Windows concept")
def test_real_repo_relative_different_drive_is_outside_repo():
    """Direct unit test: a target on a different drive than the repo root
    must resolve to the outside-repo sentinel (`".."`), not `None`
    ("cannot classify"), even though `os.path.relpath` raises
    `ValueError` for both cases identically."""
    rel = role_write_guard._real_repo_relative(  # pylint: disable=protected-access
        r"C:\some\repo", r"D:\scratch\file.py")
    assert rel == "..", (
        "a different-drive target must resolve to the outside-repo "
        "sentinel, not None (cannot classify). got: " + repr(rel))


@needs_bash
@pytest.mark.skipif(not os.path.exists("D:\\"),
                     reason="no D: drive on this machine to prove against")
def test_different_drive_target_is_allowed_as_outside_repo_bash(tmp_path):
    """Must-allow, end to end: the exact reported repro. Repo on C:
    (tmp_path is under C: in this session), pm Write to a D: target,
    guards.roleWrites: block. No directory needs to exist on D: for this
    -- Write creates a new file, and _resolve_real_target already handles
    a not-yet-existing target; this session's sandbox has no write
    permission at D:\\'s root, so the fixture must not depend on it."""
    root = crew_fixtures.make_repo(
        tmp_path, config={"guards": {"roleWrites": "block"}})
    target = "D:\\rwg_test_scratch_plan.md"

    proc = _run_sh(root, "Write", target, "pm")
    assert proc.returncode == 0, (
        "a target on a different drive is provably outside the repo and "
        "must be allowed, not refused as unclassifiable. stdout: "
        + proc.stdout + " stderr: " + proc.stderr)
    log = (root / ".crew" / "guard.log").read_text(encoding="utf-8")
    assert "outside-repo" in log, log


@needs_bash
def test_pm_write_outside_the_repo_entirely_is_allowed_bash(tmp_path):
    """Must-allow, no symlink involved: a scratchpad-style path with
    nothing under the repo at all in its ancestry -- the plain case the
    exception exists for."""
    root = crew_fixtures.make_repo(
        tmp_path, config={"guards": {"roleWrites": "block"}})
    outside = tmp_path / "scratchpad"
    outside.mkdir()
    target = outside / "plan.md"

    proc = _run_sh(root, "Write", str(target), "crew:pm")
    assert proc.returncode == 0, proc.stderr
    log = (root / ".crew" / "guard.log").read_text(encoding="utf-8")
    assert "outside-repo" in log, log


def test_is_outside_repo_directly():
    fn = role_write_guard._is_outside_repo  # pylint: disable=protected-access
    assert fn("..") is True
    assert fn("../elsewhere/plan.md") is True
    assert fn(".crew/config.json") is False
    assert fn("TODO.md") is False
    assert fn("..hidden-but-not-a-traversal.md") is False
    # None means "cannot resolve at all" (malformed/absent file_path), NOT
    # "known to be outside the repo" -- see the function's own docstring for
    # why conflating the two would let a malformed payload buy the same
    # exception a genuinely-resolved escape earns.
    assert fn(None) is False


def test_classify_pm_outside_repo_allows():
    """Direct unit test: a real resolved path outside the repo root allows,
    with the `outside-repo` reason, regardless of how it got there."""
    in_scope, reason = role_write_guard.classify("pm", "../elsewhere/plan.md")
    assert in_scope
    assert reason.startswith("outside-repo")


def test_classify_pm_none_path_does_not_get_the_outside_repo_exception():
    """`rel_path is None` (unresolvable, e.g. a malformed file_path) must
    stay in the ordinary not-in-scope branch, never the outside-repo one --
    see `_is_outside_repo`'s docstring."""
    in_scope, reason = role_write_guard.classify("pm", None)
    assert not in_scope
    assert "outside-repo" not in reason


def test_classify_deny_role_is_not_given_the_outside_repo_exception():
    """A deny-role's restriction is "no Write/Edit at all", not "confined to
    the repo" -- an outside-repo path must not exempt it."""
    in_scope, _ = role_write_guard.classify("analyst", "../elsewhere/plan.md")
    assert not in_scope


# --- Namespace collision: only `crew:` is a crew role (round-1 FIX) --------

@needs_bash
def test_other_plugin_namespaced_role_is_allowed_not_denied_bash(tmp_path):
    """Must-allow, the exact reported repro: `other-plugin:analyst` is not
    crew's own `analyst`, so it must be allowed (and logged unknown), never
    refused under crew's deny-list."""
    root = crew_fixtures.make_repo(
        tmp_path, config={"guards": {"roleWrites": "block"}})
    proc = _run_sh(root, "Write", str(root / "TODO.md"), "other-plugin:analyst")
    assert proc.returncode == 0, proc.stderr
    log = (root / ".crew" / "guard.log").read_text(encoding="utf-8")
    assert "unknown-role:other-plugin:analyst" in log, log


@needs_bash
def test_crew_prefixed_deny_role_is_still_refused_bash(tmp_path):
    """Must-block twin: `crew:analyst` must still be judged as crew's own
    `analyst` -- narrowing the strip must not also stop matching the real
    prefix."""
    root = crew_fixtures.make_repo(
        tmp_path, config={"guards": {"roleWrites": "block"}})
    proc = _run_sh(root, "Write", str(root / "TODO.md"), "crew:analyst")
    assert proc.returncode == 2, proc.stdout


# --- Malformed hook input must never crash (round-1 FIX) --------------------
#
# Reported 2026-09-19: a JSON array (`[]`) at the top level, or a non-string
# `file_path` (`42`) inside an otherwise well-formed payload, reached an
# uncaught exception -- `data.get(...)` on a list, or `os.path.relpath` on
# an int. The process then exited 1 from Python's default traceback
# handling, and `PreToolUse` treats any exit code other than 0 or 2 as a
# NON-BLOCKING failure: the write went through anyway, noisily, for a role
# (`pm`) that block mode should have refused.

@needs_bash
def test_json_array_top_level_does_not_crash_bash(tmp_path):
    root = crew_fixtures.make_repo(
        tmp_path, config={"guards": {"roleWrites": "block"}})
    proc = subprocess.run(
        [_BASH, _SH], input="[]", capture_output=True, text=True, check=False,
        env=dict(os.environ, CLAUDE_PROJECT_DIR=str(root)), cwd=str(root))
    assert proc.returncode == 0, (
        "a non-object JSON payload has no tool_name to read, so there is "
        "nothing to judge -- must allow cleanly, not crash. stderr: "
        + proc.stderr)
    assert "Traceback" not in proc.stderr, proc.stderr


@needs_bash
def test_non_string_file_path_for_pm_fails_closed_not_crashed_bash(tmp_path):
    """Must-block: `pm` with a malformed `file_path` cannot be VERIFIED as
    in scope, so it must fail toward block, not toward a crash that exits
    1 (non-blocking) and lets the write through unjudged."""
    root = crew_fixtures.make_repo(
        tmp_path, config={"guards": {"roleWrites": "block"}})
    proc = subprocess.run(
        [_BASH, _SH],
        input=json.dumps({"tool_name": "Write", "tool_input": {"file_path": 42},
                           "agent_type": "pm", "cwd": str(root)}),
        capture_output=True, text=True, check=False,
        env=dict(os.environ, CLAUDE_PROJECT_DIR=str(root)), cwd=str(root))
    assert proc.returncode == 2, (
        "a malformed file_path for a scope-restricted role must fail "
        "closed, not crash with a non-blocking exit. stdout: " + proc.stdout
        + " stderr: " + proc.stderr)
    assert "Traceback" not in proc.stderr, proc.stderr


@needs_bash
def test_non_string_file_path_for_unrestricted_role_still_allows_bash(tmp_path):
    """Must-allow twin: an unrestricted role's malformed file_path was
    always going to be allowed, so it must still exit 0, not crash."""
    root = crew_fixtures.make_repo(
        tmp_path, config={"guards": {"roleWrites": "block"}})
    proc = subprocess.run(
        [_BASH, _SH],
        input=json.dumps({"tool_name": "Write", "tool_input": {"file_path": 42},
                           "agent_type": "developer", "cwd": str(root)}),
        capture_output=True, text=True, check=False,
        env=dict(os.environ, CLAUDE_PROJECT_DIR=str(root)), cwd=str(root))
    assert proc.returncode == 0, proc.stderr
    assert "Traceback" not in proc.stderr, proc.stderr


# --- guard.log must carry the promised reason column (round-1 FIX) ---------
#
# Reported 2026-09-19: the module docstring and CONFIG.md Sec18 both promise
# `no-agent-type` and `unknown-role:<value>` are "named differently in
# .crew/guard.log rather than merged into one unreadable 'allow' row" --
# but the row-building code computed `reason` and never wrote it anywhere.

@needs_bash
def test_guard_log_carries_no_agent_type_reason_bash(tmp_path):
    root = crew_fixtures.make_repo(
        tmp_path, config={"guards": {"roleWrites": "block"}})
    proc = _run_sh(root, "Write", str(root / "src" / "app.py"), None)
    assert proc.returncode == 0, proc.stderr
    log = (root / ".crew" / "guard.log").read_text(encoding="utf-8")
    assert "no-agent-type" in log, log


@needs_bash
def test_guard_log_carries_unknown_role_reason_bash(tmp_path):
    root = crew_fixtures.make_repo(
        tmp_path, config={"guards": {"roleWrites": "block"}})
    proc = _run_sh(root, "Write", str(root / "src" / "app.py"), "Explore")
    assert proc.returncode == 0, proc.stderr
    log = (root / ".crew" / "guard.log").read_text(encoding="utf-8")
    assert "unknown-role:explore" in log, log


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
# scripts/check-powershell.ps1's static check).
#
# A PowerShell-focused review of THIS file specifically (2026-09-19, on top
# of the WindowsApps/profile-shadow fix above) found the copy had drifted
# from role-write-guard.sh's OWN resolver in two ways the three-way byte
# parity this section used to assert could never catch, because
# verify-gate.ps1/pm-pulse.ps1 do not share role-write-guard.sh's shape
# either: (1) it trusted `Get-Command` metadata instead of EXECUTING the
# candidate the way the .sh does, and (2) `Get-Command $name -All` walked
# every match for ONE name before moving to the next, while bash's
# `command -v` takes only the first match per name -- so role-write-
# guard.ps1 now deliberately DIVERGES from verify-gate.ps1's/pm-pulse.ps1's
# copies (see `Resolve-CrewPython`'s own comment) and the three-way parity
# test below became a two-way one, plus new cases specific to this file.

_VERIFY_GATE_PS1 = os.path.join(_ROOT, "hooks", "scripts", "verify-gate.ps1")
_PM_PULSE_PS1 = os.path.join(_ROOT, "hooks", "scripts", "pm-pulse.ps1")


def _stub(path, reports=None):
    """A REAL, launchable stub (a `.cmd` batch file) -- never a plain-text
    file merely wearing a `.exe` extension. This resolver now EXECUTES
    every candidate it considers before trusting it, so a file that cannot
    actually be launched no longer proves what an un-executing resolver's
    tests once could.

    `reports`, if given, is echoed to stdout when the stub is invoked --
    simulating a real interpreter's `sys.executable` answer. Omitted, the
    stub produces NO output at all when run, simulating a WindowsApps
    alias that does nothing in this non-interactive context -- as opposed
    to merely LOOKING like a real interpreter to `Get-Command`, which is
    the bug this section's header already names as fixed once before.
    """
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="ascii") as handle:
        handle.write("@echo off\r\n")
        if reports:
            handle.write("echo " + reports + "\r\n")
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
    """Must-block. The un-hardened one-liner returned the Store alias and
    invoked it; a stub that LOOKS real to Get-Command but produces no
    output when actually launched must also be rejected."""
    apps = tmp_path / "WindowsApps"
    _stub(str(apps / "python3.cmd"))  # no `reports` -- produces no output
    _stub(str(apps / "python.cmd"))

    resolved = _print_python([str(apps)])
    assert "WindowsApps" not in resolved, (
        "the WindowsApps alias was returned as the interpreter: " + resolved)
    assert resolved == "", (
        "with only stubs on PATH there is no usable python and the resolver "
        "must answer empty rather than hand back a stub. got: " + resolved)


@needs_pwsh_windows
def test_a_real_python_under_a_different_name_still_resolves(tmp_path):
    """Must-allow: the fix must not become "never finds python". Under the
    name-order semantics FIX 3 introduced, rejecting `python3` moves to
    the NEXT NAME -- so the real interpreter here is named `python`, a
    DIFFERENT name, not a second `python3` further down PATH (that
    scenario is the one the divergence test below proves must resolve to
    NOTHING, matching bash)."""
    apps = tmp_path / "WindowsApps"
    real = tmp_path / "tools"
    real_exe = str(real / "python.cmd")
    _stub(str(apps / "python3.cmd"))
    _stub(real_exe, reports=real_exe)

    resolved = _print_python([str(apps), str(real)])
    assert resolved.lower().startswith(str(real).lower()), (
        "the real python.cmd, under a DIFFERENT name than the rejected "
        "stub, must still resolve. got: " + resolved)


@needs_pwsh_windows
def test_windowsapps_stub_with_only_one_name_present_falls_through_like_bash(tmp_path):
    """The exact reported divergence. PATH = WindowsApps(python3 stub
    only); RealDir(python3, real) -- no `python`/`py` ANYWHERE. The old
    `Get-Command $name -All` walked past the stub to RealDir's python3
    WITHIN the same name and resolved it; bash's `command -v python3`
    takes only the first match, rejects it, and moves to the NEXT NAME --
    finding nothing, since `python`/`py` do not exist either. Both shell
    flavours must now agree that neither resolves an interpreter here."""
    apps = tmp_path / "WindowsApps"
    real = tmp_path / "tools"
    real_exe = str(real / "python3.cmd")
    _stub(str(apps / "python3.cmd"))       # the only WindowsApps stub
    _stub(real_exe, reports=real_exe)      # a REAL python3 further down PATH

    resolved = _print_python([str(apps), str(real)])
    assert resolved == "", (
        "role-write-guard.ps1 must take only the FIRST match for a name, "
        "matching role-write-guard.sh's `command -v` semantics -- walking "
        "past the WindowsApps stub to a SECOND python3 further down PATH "
        "is the divergence reported 2026-09-19. got: " + resolved)


@needs_bash
def test_bash_agrees_it_finds_nothing_in_the_same_layout(tmp_path):
    """The bash HALF of the parity claim above, driven through the actual
    .sh end to end (not just the .ps1's -PrintPython probe), so the
    assertion is about real behaviour, not the resolver in isolation."""
    apps = tmp_path / "WindowsApps"
    real = tmp_path / "tools"
    apps.mkdir(parents=True)
    real.mkdir(parents=True)
    # newline="\n" is load-bearing here -- pathlib.write_text on Windows is
    # TEXT mode and converts every "\n" to "\r\n" by default, which corrupts
    # a shebang line into "#!/bin/sh\r\n" and breaks execution. CLAUDE.md
    # names this exact landmine.
    stub = apps / "python3"
    stub.write_text("#!/bin/sh\nexit 0\n", encoding="ascii", newline="\n")
    os.chmod(stub, 0o755)
    real_py = real / "python3"
    real_py.write_text("#!/bin/sh\necho " + str(real_py) + "\n",
                        encoding="ascii", newline="\n")
    os.chmod(real_py, 0o755)

    root = crew_fixtures.make_repo(
        tmp_path, config={"guards": {"roleWrites": "block"}})
    env = os.environ.copy()
    # Exclude the rest of the ORIGINAL PATH deliberately, matching the
    # .ps1 comparison test's `_print_python`, which replaces PATH the same
    # way. Appending the real PATH here -- an earlier draft of this test
    # did -- reintroduces this machine's own real `python` binary under a
    # DIFFERENT name than the stubbed one, which the resolver legitimately
    # finds once `python3` is rejected; that is not a bug, but it also
    # proves nothing about the "only one name present" layout this test
    # means to construct. `_coreutils_only_path` is not "the real PATH" in
    # that sense -- it holds none of the three python names, only the
    # handful of external tools role-write-guard.sh needs to run at all
    # (see its own comment for why CI needs this and this repo's Windows/MSYS
    # dev machine never revealed the gap).
    env["PATH"] = os.pathsep.join(
        [str(apps), str(real), _coreutils_only_path(tmp_path)])
    env["CLAUDE_PROJECT_DIR"] = str(root)
    proc = subprocess.run(
        [_BASH, _SH],
        input=_write_payload("Write", str(root / "src" / "app.py"), "pm", str(root)),
        capture_output=True, text=True, check=False, env=env, cwd=str(root))
    # Since 2026-09-24, total resolution failure fails closed for a
    # restricted role ('pm') exactly like a launch failure does, so this
    # now exits 2 rather than 0 -- the resolution-failure message is what
    # actually proves "bash found nothing usable", not the exit code alone
    # (a launch failure would exit 2 too).
    assert proc.returncode == 2, (
        "bash must ALSO find nothing usable in this exact layout -- if "
        "this ever fails while the .ps1 test above still passes, the two "
        "shells have re-diverged. stdout: " + proc.stdout + " stderr: "
        + proc.stderr)
    assert "no usable python found" in proc.stderr, (
        "expected the resolution-failure message, not the launch-failure "
        "one -- got: " + proc.stderr)


def _resolver_source(path):
    src = pathlib.Path(path).read_text(encoding="utf-8")
    start = src.find("function Resolve-CrewPython {")
    assert start != -1, (
        "Resolve-CrewPython is gone from " + path + ". If it was renamed, "
        "re-point this test rather than deleting it.")
    end = src.find("\n}\n", start)
    assert end != -1, "could not find the end of Resolve-CrewPython in " + path
    return src[start:end + 3]


def _resolver_code_lines(path):
    def code_lines(src):
        out = []
        for line in src.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            out.append(re.sub(r"\s+", " ", stripped))
        return out
    return code_lines(_resolver_source(path))


def test_verify_gate_and_pm_pulse_resolvers_still_agree():
    """The two-way parity that remains. verify-gate.ps1 and pm-pulse.ps1
    both only need to match `_common.sh`'s bare `crew_py()`, so their
    copies of Resolve-CrewPython are UNCHANGED and must still be
    byte-identical to each other -- role-write-guard.ps1 is the one that
    now answers a different question (parity with its OWN, stricter bash
    sibling) and is deliberately excluded from this comparison; see
    `test_role_write_guard_resolver_documents_its_own_divergence` below."""
    gate = _resolver_code_lines(_VERIFY_GATE_PS1)
    pulse = _resolver_code_lines(_PM_PULSE_PS1)
    assert gate == pulse, (
        "verify-gate.ps1 and pm-pulse.ps1 have drifted. One hook would "
        "then resolve an interpreter the other refuses."
        + "\nverify-gate.ps1: " + repr(gate)
        + "\npm-pulse.ps1:    " + repr(pulse))


def test_role_write_guard_resolver_documents_its_own_divergence():
    """A cheap tripwire for the OPPOSITE mistake: if role-write-guard.ps1's
    copy ever silently becomes byte-identical to the other two again
    (e.g. a careless future hand-copy), the execute-to-verify and
    single-match-per-name behaviour this section's tests depend on would
    be gone without anything else here noticing, since those behaviours
    are asserted operationally (through -PrintPython), not textually."""
    guard = _resolver_code_lines(_PS1)
    gate = _resolver_code_lines(_VERIFY_GATE_PS1)
    assert guard != gate, (
        "role-write-guard.ps1's Resolve-CrewPython is now byte-identical "
        "to verify-gate.ps1's again -- it should NOT be: this file's "
        "resolver must execute each candidate and take only the first "
        "match per name, which the other two do not do. If this was a "
        "deliberate simplification, re-verify the WindowsApps-only-one-"
        "name-present test above still passes for the right reason before "
        "relaxing this tripwire.")


# --- BLOCK 1: a launch failure must not silently allow --------------------
#
# `$raw | & $py (Join-Path $dir 'role_write_guard.py')` had no try/catch and
# no check on `$LASTEXITCODE`. A native command that fails to LAUNCH (as
# opposed to one that launches and exits nonzero) never sets
# `$LASTEXITCODE` at all; a fresh `pwsh`/`powershell` process starts with it
# `$null`; `exit $LASTEXITCODE` on `$null` silently evaluates to 0 -- allow.
# Reproduced by the specialist under the exact hooks.json shape with `$py`
# pointed at a nonexistent path: outer exit 0, only a generic native-command
# error on stderr. Reported and fixed 2026-09-19.

def _patch_py_to_nonexistent(src):
    """Force `$py` to an unlaunchable path immediately after
    `Resolve-CrewPython` would normally set it -- the same technique the
    specialist's own repro used, reproducing a launch failure without
    depending on any particular machine's real interpreter breaking
    mid-session."""
    anchor = "$py = Resolve-CrewPython"
    assert anchor in src, "Resolve-CrewPython call site moved; re-point this patch"
    return src.replace(
        anchor,
        anchor + "\n$py = 'C:\\definitely-does-not-exist\\python.exe'",
        1)


def _patched_ps1_copy(tmp_path, patcher, filename="role-write-guard.ps1"):
    """A full copy of hooks/scripts/ under `tmp_path`, with
    role-write-guard.ps1 replaced by `patcher(original_source)` (or, for
    FIX 4's test, with a file removed instead). A patched copy dropped
    ANYWHERE else would fail FIX 4's own missing-role_write_guard.py check
    before ever reaching whatever the patch is testing, because `$dir` in
    the script is derived from its own path."""
    scripts_dir = os.path.join(_ROOT, "hooks", "scripts")
    dest = tmp_path / "scripts_copy"
    shutil.copytree(scripts_dir, dest, ignore=shutil.ignore_patterns("_test"))
    target = dest / filename
    if patcher is not None:
        target.write_text(patcher(target.read_text(encoding="utf-8")),
                           encoding="utf-8")
    return str(target)


@needs_pwsh_windows
def test_launch_failure_fails_closed_for_pm_powershell(tmp_path):
    """Must-block: a restricted role (pm) must fail closed when the
    resolved interpreter cannot actually be launched, rather than
    silently allow via a null $LASTEXITCODE."""
    root = crew_fixtures.make_repo(
        tmp_path, config={"guards": {"roleWrites": "block"}})
    patched = _patched_ps1_copy(tmp_path, _patch_py_to_nonexistent)

    proc = _run_ps1_at(patched, root, "Write", str(root / "src" / "app.py"), "pm")
    assert proc.returncode == 2, (
        "a restricted role must fail closed when the interpreter cannot "
        "be launched. stdout: " + proc.stdout + " stderr: " + proc.stderr)
    assert "pm" in proc.stderr, proc.stderr


@needs_pwsh_windows
def test_launch_failure_still_allows_unrestricted_role_powershell(tmp_path):
    """Must-allow twin: an unrestricted role was always going to be
    allowed, so a launch failure must not become a NEW refusal for it."""
    root = crew_fixtures.make_repo(
        tmp_path, config={"guards": {"roleWrites": "block"}})
    patched = _patched_ps1_copy(tmp_path, _patch_py_to_nonexistent)

    proc = _run_ps1_at(patched, root, "Write", str(root / "src" / "app.py"),
                        "developer")
    assert proc.returncode == 0, proc.stderr


# --- Round 3: role-write-guard.sh gets the SAME launch-failure fallback ---
#
# The .ps1 fix above only ever protected PowerShell. Reported 2026-09-19:
# deleting the resolved interpreter between `_resolve_role_write_python`'s
# successful probe and the actual invocation made bash's own `"$PY" ...`
# fail to exec (`No such file or directory`, exit 127) -- a status neither
# 0 nor 2, which `PreToolUse` treats as NON-BLOCKING, so `pm` writing an
# out-of-scope path went through unjudged with only a shell error on
# stderr.

def _patch_py_to_nonexistent_sh(src):
    """Force `$PY` to an unlaunchable path immediately after
    `_resolve_role_write_python` would normally set it -- same technique
    as the .ps1 twin's `_patch_py_to_nonexistent`.

    The anchor must be textually AFTER the `PY=$(_resolve_role_write_python)
    || { ... }` block, not before it -- since 2026-09-24 the deny-list
    helpers moved above that block (they are needed there too, for the
    resolution-failure fallback), so anchoring on them would overwrite $PY
    with the nonexistent path BEFORE resolution runs, only for the real
    resolver to immediately clobber it again with a genuine interpreter and
    silently defeat this patch."""
    anchor = "\n# PYTHONUTF8=1 / PYTHONIOENCODING=utf-8 in the CHILD's environment only --"
    assert anchor in src, "anchor moved; re-point this patch"
    return src.replace(
        anchor,
        '\nPY="/definitely/does/not/exist/python3"' + anchor,
        1)


def _patched_sh_copy(tmp_path, patcher, filename="role-write-guard.sh"):
    """The bash twin of `_patched_ps1_copy` -- a full copy of
    hooks/scripts/ under `tmp_path`, with role-write-guard.sh replaced by
    `patcher(original_source)`. `newline="\\n"` on the write is
    load-bearing: `pathlib.write_text` is TEXT mode on Windows and would
    otherwise corrupt the shebang into `#!/usr/bin/env bash\\r\\n`
    (CLAUDE.md's own named landmine)."""
    scripts_dir = os.path.join(_ROOT, "hooks", "scripts")
    dest = tmp_path / "scripts_copy_sh"
    shutil.copytree(scripts_dir, dest, ignore=shutil.ignore_patterns("_test"))
    target = dest / filename
    if patcher is not None:
        target.write_text(patcher(target.read_text(encoding="utf-8")),
                           encoding="utf-8", newline="\n")
    return str(target)


@needs_bash
def test_launch_failure_fails_closed_for_pm_bash(tmp_path):
    """Must-block: the bash twin of the .ps1 case above."""
    root = crew_fixtures.make_repo(
        tmp_path, config={"guards": {"roleWrites": "block"}})
    patched = _patched_sh_copy(tmp_path, _patch_py_to_nonexistent_sh)
    proc = subprocess.run(
        [_BASH, patched],
        input=_write_payload("Write", str(root / "src" / "app.py"), "pm", str(root)),
        capture_output=True, text=True, check=False,
        env=dict(os.environ, CLAUDE_PROJECT_DIR=str(root)), cwd=str(root))
    assert proc.returncode == 2, (
        "a restricted role must fail closed when the interpreter cannot "
        "be launched. stdout: " + proc.stdout + " stderr: " + proc.stderr)
    assert "pm" in proc.stderr, proc.stderr


@needs_bash
def test_launch_failure_still_allows_unrestricted_role_bash(tmp_path):
    """Must-allow twin."""
    root = crew_fixtures.make_repo(
        tmp_path, config={"guards": {"roleWrites": "block"}})
    patched = _patched_sh_copy(tmp_path, _patch_py_to_nonexistent_sh)
    proc = subprocess.run(
        [_BASH, patched],
        input=_write_payload("Write", str(root / "src" / "app.py"), "developer", str(root)),
        capture_output=True, text=True, check=False,
        env=dict(os.environ, CLAUDE_PROJECT_DIR=str(root)), cwd=str(root))
    assert proc.returncode == 0, proc.stderr


# --- BLOCK 2: stdin must round-trip as UTF-8, byte for byte ----------------
#
# `[Console]::In.ReadToEnd()` decodes using the OEM codepage (Windows
# PowerShell 5.1) or a version-dependent default (pwsh 7.x), silently
# mangling any character outside plain ASCII, and turns a leading UTF-8 BOM
# into garbage bytes that make the JSON unparseable at position 0 --
# role_write_guard.py's own `except ValueError` then allows the call
# UNJUDGED. role-write-guard.sh (`INPUT=$(cat)`) is byte-transparent, so the
# two shell flavours diverged on byte-identical input. Reported and fixed
# 2026-09-19.

@needs_pwsh_windows
def test_accented_character_in_path_round_trips_intact_powershell(tmp_path):
    """Must-block, verified via `.crew/guard.log` -- `_log` writes it with
    an EXPLICIT `encoding="utf-8"`, unlike a piped python subprocess's own
    stdout/stderr, whose default encoding when NOT attached to a real
    console is a separate, pre-existing concern this test deliberately
    does not exercise (found while writing this test: role_write_guard.py
    itself already mis-encodes a non-ASCII character in its OWN stderr
    write on this machine, regardless of which shell invoked it -- outside
    this finding's scope, which is what role-write-guard.ps1 does to
    stdin on the way IN, not what the python child does to its own output
    on the way out). Proof the character decoded correctly BEFORE
    reaching role_write_guard.py at all: mangling into `?` (5.1's OEM
    codepage) or multi-byte garbage (pwsh 7.x's default) would show up
    here just as it would in the refusal message."""
    root = crew_fixtures.make_repo(
        tmp_path, config={"guards": {"roleWrites": "block"}})
    target = str(root / "caf\u00e9" / "app.py")
    payload = json.dumps({"tool_name": "Write",
                           "tool_input": {"file_path": target},
                           "agent_type": "pm", "cwd": str(root)})
    proc = subprocess.run(
        [_PWSH, "-NoProfile", "-NonInteractive", "-File", _PS1],
        input=payload.encode("utf-8"), capture_output=True, check=False,
        env=dict(os.environ, CLAUDE_PROJECT_DIR=str(root)), cwd=str(root))
    assert proc.returncode == 2, (
        "stdout: " + proc.stdout.decode("utf-8", "replace")
        + " stderr: " + proc.stderr.decode("utf-8", "replace"))
    log = (root / ".crew" / "guard.log").read_text(encoding="utf-8")
    assert "caf\u00e9" in log, (
        "the accented character did not round-trip intact: " + repr(log))


@needs_pwsh_windows
def test_utf8_bom_on_stdin_does_not_break_the_payload_powershell(tmp_path):
    """Must-block (proving the BOM was stripped and the payload parsed): a
    leading UTF-8 BOM must not survive into the decoded JSON, where it
    would sit at position 0 and make an otherwise well-formed payload
    unparseable -- which fails OPEN (allow, unjudged) rather than reaching
    a real decision. An OUT-OF-SCOPE target is used deliberately: "BOM
    broke parsing" (allow) and "BOM stripped correctly" (block) then give
    DIFFERENT, distinguishable exit codes -- an in-scope target would exit
    0 either way and prove nothing."""
    root = crew_fixtures.make_repo(
        tmp_path, config={"guards": {"roleWrites": "block"}})
    payload = json.dumps({"tool_name": "Write",
                           "tool_input": {"file_path": str(root / "src" / "app.py")},
                           "agent_type": "pm", "cwd": str(root)})
    bom = b"\xef\xbb\xbf"
    proc = subprocess.run(
        [_PWSH, "-NoProfile", "-NonInteractive", "-File", _PS1],
        input=bom + payload.encode("utf-8"), capture_output=True, check=False,
        env=dict(os.environ, CLAUDE_PROJECT_DIR=str(root)), cwd=str(root))
    assert proc.returncode == 2, (
        "a leading UTF-8 BOM must be stripped before JSON parsing. "
        "stdout: " + proc.stdout.decode("utf-8", "replace")
        + " stderr: " + proc.stderr.decode("utf-8", "replace"))


# --- FIX 4: a missing role_write_guard.py must say so, and fail closed ----

@needs_pwsh_windows
def test_missing_role_write_guard_py_fails_closed_with_diagnostic_powershell(tmp_path):
    """Must-block, with a crew-specific message: a broken install
    (role_write_guard.py absent) must not read as a bare CPython
    "can't open file" -- identical, by exit code alone, to a real
    guards.roleWrites: block refusal."""
    scripts_dir = os.path.join(_ROOT, "hooks", "scripts")
    dest = tmp_path / "scripts_copy"
    shutil.copytree(scripts_dir, dest, ignore=shutil.ignore_patterns("_test"))
    os.remove(str(dest / "role_write_guard.py"))

    root = crew_fixtures.make_repo(
        tmp_path, config={"guards": {"roleWrites": "block"}})
    proc = _run_ps1_at(str(dest / "role-write-guard.ps1"), root, "Write",
                        str(root / "src" / "app.py"), "pm")
    assert proc.returncode == 2, proc.stdout
    assert "role_write_guard.py is missing" in proc.stderr, proc.stderr

"""The shape of hooks.json and its agreement with crew_hook.TABLE (L-0727, A8).

hooks.json registers 16 launcher commands: one per event per shell. `TABLE` in
crew_hook.py is the one contract for what those launchers run. These tests keep
the rest of the system on that contract:

  * hooks.json is exactly what `crew_instructions.claude_hooks()` renders from TABLE;
  * every TABLE row is a hook that was registered before the dispatcher, with the
    same event, matcher, script, argument and timeout (the recorded entry list);
  * every script TABLE names exists, and so does each PowerShell twin;
  * crew-hook.sh's no-python list, and both launchers' event timeouts, equal TABLE;
  * the Codex registrations are the HOOK_TABLE rows, through the launcher.
"""
import json
import os
import re
import subprocess

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import crew_hook
import crew_hook_harness as h
import crew_instructions as ci
import record_golden_hooks as rgh

PLUGIN = context._ROOT  # pylint: disable=protected-access
SCRIPTS = os.path.join(PLUGIN, "hooks", "scripts")
HOOKS_JSON = os.path.join(PLUGIN, "hooks", "hooks.json")
SH_TEXT = h.read_text(os.path.join(SCRIPTS, "crew-hook.sh"))
PS1_TEXT = h.read_text(os.path.join(SCRIPTS, "crew-hook.ps1"))
BASH = "bash"


def _hooks():
    with open(HOOKS_JSON, encoding="utf-8") as handle:
        return json.load(handle)["hooks"]


def _registrations():
    out = []
    for event, rows in _hooks().items():
        for row in rows:
            for hook in row["hooks"]:
                out.append((event, row.get("matcher", ""), hook))
    return out


def test_hooks_json_has_exactly_sixteen_registrations_two_per_event():
    registrations = _registrations()

    assert len(registrations) == 16
    assert sorted(set(e for e, _, _ in registrations)) == sorted(crew_hook.EVENTS)
    for event in crew_hook.EVENTS:
        shells = sorted(h.get("shell", "bash") for e, _, h in registrations if e == event)
        assert shells == ["bash", "powershell"], event


def test_every_registration_runs_a_launcher_and_names_its_event():
    for event, _, hook in _registrations():
        if hook.get("shell") == "powershell":
            assert hook["command"] == (f'& "${{CLAUDE_PLUGIN_ROOT}}/hooks/scripts/crew-hook.ps1" {event}; '
                                       "exit $LASTEXITCODE")
        else:
            assert hook["command"] == f'bash "${{CLAUDE_PLUGIN_ROOT}}/hooks/scripts/crew-hook.sh" {event}'


def _tool_names(matcher):
    """(plain tool names, whether the vault regex is part of it)."""
    vault = crew_hook.VAULT_MATCHER in matcher
    rest = matcher.replace(crew_hook.VAULT_MATCHER, "")
    return {name for name in rest.split("|") if name}, vault


def test_the_matchers_are_the_union_of_the_rows_tool_names():
    for event in crew_hook.EVENTS:
        rows = [row for row in crew_hook.TABLE if row.event == event]
        registered = crew_hook.REGISTERED_MATCHER[event]
        if any(not row.matcher for row in rows):
            assert registered == "", event
            continue
        names, vault = set(), False
        for row in rows:
            row_names, row_vault = _tool_names(row.matcher)
            names |= row_names
            vault = vault or row_vault
        assert _tool_names(registered) == (names, vault), event
    for event, matcher, _ in _registrations():
        assert matcher == crew_hook.REGISTERED_MATCHER[event]


def test_the_timeouts_are_the_largest_row_plus_ten_seconds():
    for event, _, hook in _registrations():
        assert hook["timeout"] == max(r.timeout for r in crew_hook.TABLE if r.event == event) + 10


def test_hooks_json_is_what_the_instruction_generator_renders_from_the_table():
    assert _hooks() == ci.claude_hooks()["hooks"]


def test_every_table_script_and_twin_exists():
    for row in crew_hook.TABLE:
        assert os.path.isfile(os.path.join(SCRIPTS, row.script)), row.script
        if row.twin:
            assert os.path.isfile(os.path.join(SCRIPTS, row.twin)), row.twin


def test_the_table_rows_are_the_hooks_that_were_registered_before_the_dispatcher():
    before = [e for e in rgh.registrations() if e["flavour"] == "bash"]

    now = [(r.event, r.matcher, r.script, list(r.extra), r.timeout) for r in crew_hook.TABLE]

    assert now == [(e["event"], e["matcher"], e["script"], e["extra"], e["timeout"]) for e in before]


def test_a_power_shell_twin_is_a_row_that_had_one_registered_for_the_power_shell_tool():
    before = rgh.registrations()
    twins = {r.script.replace(".sh", ".ps1") for r in crew_hook.TABLE if r.twin}
    registered_ps = {e["script"] for e in before if e["flavour"] == "powershell"}

    assert twins <= registered_ps
    assert {r.twin for r in crew_hook.TABLE if r.twin} == {"promote-gate.ps1", "cloud-guard.ps1", "env-guard.ps1"}


def test_the_table_covers_every_script_the_event_needs_and_dedupes_nothing_by_accident():
    keys = [(r.event, r.script, r.extra, r.matcher) for r in crew_hook.TABLE]

    assert len(keys) == len(set(keys)) == 18


def _rows_for_function():
    start = SH_TEXT.index("_rows_for() {")
    return SH_TEXT[start:SH_TEXT.index("\n}\n", start) + 3]


def _launcher_rows(event, harness):
    script = f'EVENT={event}\nHARNESS={harness}\n{_rows_for_function()}\n_rows_for\n'
    done = subprocess.run([BASH, "-c", script], capture_output=True, text=True, check=True)
    return done.stdout.splitlines()


def _table_rows(event, harness):
    lines = []
    for row in crew_hook.TABLE:
        if row.event != event:
            continue
        if harness == "codex":
            if row.codex is None:
                continue
            matcher = "@vault" if row.codex == crew_hook.VAULT_MATCHER else row.codex
            lines.append(f"{row.script};--harness codex;{matcher}")
        else:
            matcher = "@vault" if row.matcher == crew_hook.VAULT_MATCHER else row.matcher
            lines.append(f"{row.script};{' '.join(row.extra)};{matcher}")
    return lines


@pytest.mark.parametrize("harness", ["claude", "codex"])
@pytest.mark.parametrize("event", crew_hook.EVENTS)
def test_the_no_python_list_in_crew_hook_sh_equals_the_table(event, harness):
    assert _launcher_rows(event, harness) == _table_rows(event, harness)


def test_the_sh_launcher_timeouts_equal_the_registration_timeouts():
    block = SH_TEXT[SH_TEXT.index('case "$EVENT" in\n  SessionStart|UserPromptSubmit|PreToolUse) TIMEOUT'):]
    block = block[:block.index("esac")]
    found = {}
    for line in block.splitlines():
        match = re.match(r"\s*([A-Za-z|]+)\) TIMEOUT=(\d+)", line)
        if match:
            for event in match.group(1).split("|"):
                found[event] = int(match.group(2))

    assert found == {event: crew_hook.event_timeout(event) for event in crew_hook.EVENTS}


def test_the_ps1_launcher_timeouts_equal_the_registration_timeouts():
    table = PS1_TEXT[PS1_TEXT.index("$crewTimeouts = @{"):]
    table = table[:table.index("}")]
    found = {name: int(value) for name, value in re.findall(r"(\w+) = (\d+)", table)}

    assert found == {event: crew_hook.event_timeout(event) for event in crew_hook.EVENTS}


def test_the_ps1_restricted_roles_equal_role_write_guards():
    mine = re.search(r"\$crewRestrictedRoles = @\(([^)]*)\)", PS1_TEXT).group(1)
    theirs_text = h.read_text(os.path.join(SCRIPTS, "role-write-guard.ps1"))
    theirs = re.search(r"\$RestrictedRolesForFallback = @\(([^)]*)\)", theirs_text).group(1)

    assert re.findall(r"'([^']+)'", mine) == re.findall(r"'([^']+)'", theirs) == list(crew_hook.RESTRICTED_ROLES)


def test_the_codex_rows_are_the_five_crew_context_rows_registered_before_the_dispatcher():
    mine = sorted((r.event, r.script, r.codex) for r in crew_hook.TABLE if r.codex is not None)

    assert mine == sorted([
        ("SessionStart", "crew-context.sh", ""), ("UserPromptSubmit", "crew-context.sh", ""),
        ("PostToolUse", "crew-context.sh", "apply_patch|Edit|Write"),
        ("PostToolUse", "crew-context.sh", crew_hook.VAULT_MATCHER),
        ("SubagentStart", "crew-context.sh", "")])


def test_instruction_generator_codex_rows_are_derived_from_the_table_not_copied():
    derived = [(row["event"], row["codex"]) for row in ci.HOOK_TABLE]

    assert derived == [(r.event, r.codex or None) for r in crew_hook.TABLE if r.codex is not None]


def test_a_table_matcher_is_an_empty_string_the_vault_regex_or_a_plain_tool_list():
    """The no-python fallback in crew-hook.sh judges nothing else, and runs a row it cannot judge;
    a general regex in TABLE needs that fallback taught first."""
    plain = re.compile(r"[A-Za-z0-9_|]+\Z")

    odd = [(r.script, m) for r in crew_hook.TABLE for m in (r.matcher, r.codex or "")
           if m and m != crew_hook.VAULT_MATCHER and not plain.match(m)]

    assert odd == []


def test_codex_registrations_go_through_the_launcher_with_the_harness_flag():
    hooks = ci.codex_hooks("/opt/crew")["hooks"]

    for event, entries in hooks.items():
        for entry in entries:
            hook = entry["hooks"][0]
            assert hook["command"] == f'bash "/opt/crew/hooks/scripts/crew-hook.sh" {event} --harness codex'
            assert hook["commandWindows"] == ('powershell -NoProfile -ExecutionPolicy Bypass -File '
                                              f'"\\opt\\crew\\hooks\\scripts\\crew-hook.ps1" {event} -Harness codex')
            assert hook["timeout"] == crew_hook.event_timeout(event)


def test_no_registration_names_a_hook_script_directly():
    text = h.read_text(HOOKS_JSON)

    scripts = set(re.findall(r"hooks/scripts/([\w.-]+)", text))

    assert scripts == {"crew-hook.sh", "crew-hook.ps1"}


def test_the_ps1_launcher_catches_an_unexpected_error_and_exits_2_for_an_armed_blocking_event():
    """Security re-read (L-0850): without it a terminating error ends the script with no exit code and the
    registration's `exit $LASTEXITCODE` says 0. The try opens before the first statement that can fail and
    closes at the end of the file; the flavour guard stays outside it, as test_flavour_guard.py requires."""
    opened = PS1_TEXT.index("\ntry {\n# Registration timeout")
    catch = PS1_TEXT[PS1_TEXT.rindex("\n} catch {"):]

    assert PS1_TEXT.index("if ($env:OS -ne 'Windows_NT') { exit 0 }") < opened
    assert PS1_TEXT.index("function Resolve-CrewPython") < opened < PS1_TEXT.index("$crewTimeouts = @{")
    assert "Test-CrewArmed" in catch and "-and $crewCatchArmed) { exit 2 }" in catch and catch.rstrip().endswith("}")


def test_the_sh_watchdog_sets_its_trap_before_the_sleeper_starts_and_ends_it_through_the_job_table():
    start = SH_TEXT.index("_watchdog() {")
    body = SH_TEXT[start:SH_TEXT.index("\n}\n", start)]

    assert body.index("trap 'kill $(jobs -p)") < body.index('sleep "$secs"')
    assert 'sleep "$secs" >/dev/null 2>&1 &' in body


def test_the_ps1_flavour_guard_trusts_the_platform_not_only_the_environment():
    """Security pass (L-0850): on Windows this launcher is the only one that runs, so an unset or
    changed OS variable must not make it exit 0. Real Windows is told by the platform."""
    guard = [line for line in PS1_TEXT.splitlines() if line.startswith("if ($env:OS -ne")]
    default = ("[string]$CrewPlatformMarker = $(if ([System.Environment]::OSVersion.Platform -eq "
               "[System.PlatformID]::Win32NT) { $env:OS = 'Windows_NT' })")

    # the guard stays the exact line tests/test_flavour_guard.py holds every registered .ps1 to, and the
    # parameter default (which runs before it) puts OS back on a real Windows host
    assert guard == ["if ($env:OS -ne 'Windows_NT') { exit 0 }"]
    assert default in PS1_TEXT


@pytest.mark.parametrize("matcher,tool,runs", [
    ("Write|Edit", "Edit", True), ("Write|Edit", "Bash", False), ("", "Bash", True), ("Bash", "", True),
    ("@vault", "mcp__obsidian__search", True), ("@vault", "Read", False),
    ("mcp__.*(x|y)", "Read", True),  # a regex it cannot judge: the row runs and the script decides
])
def test_the_no_python_tool_matcher_runs_a_row_it_cannot_judge(matcher, tool, runs):
    start = SH_TEXT.index("_tool_matches() {")
    function = SH_TEXT[start:SH_TEXT.index("\n}\n", start) + 3]

    done = subprocess.run([BASH, "-c", f"{function}\n_tool_matches '{matcher}' '{tool}'; echo $?"],
                          capture_output=True, text=True, check=True)

    assert (done.stdout.strip() == "0") is runs

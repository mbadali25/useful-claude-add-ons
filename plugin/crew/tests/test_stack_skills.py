"""Doc tests for the seven `stack-*` skills (crew 1.0 T5 part 2, lane C2 fix round).

Each skill under `plugin/crew/skills/stack-<name>/SKILL.md` must: exist, stay
at or under 120 lines (the brief's budget - a skill this long stops loading
on demand and starts reading like the agent persona it replaced), carry
valid frontmatter with `name` and a `description` that actually names the
stack (not just any non-empty string), and propose at least one
`verify.json` rule that (a) parses as JSON with the shape the gate actually
reads (`paths`: list, `run`: list of command strings - see
`plugin/crew/hooks/scripts/verify-gate.sh` and `.crew/verify.json`) and (b)
names a missing-tool path that exits 77, the code this repo's own
`.crew/verify.json` and `verify-gate.sh` treat as UNVERIFIED rather than
PASS or FAIL (`plugin/crew/hooks/scripts/verify-gate.sh` reads `reach` and
treats a rule's own exit codes; 77 is the tool-missing convention already in
use for the `pwsh`, `ruff`/`pylint` and `npm` rules in this repo's
`.crew/verify.json`).

The exit-77 check is PER COMMAND, not per rule: a rule can name two `run`
commands (stack-powershell does, one per PowerShell edition), and a joined-
text search across both hides a missing branch in either one. Beyond the
string-search, `test_missing_tool_branch_actually_exits_77_for_real` runs
every command for real, in a scratch directory with PATH stripped to a stub
containing only `sh`/`bash` - the shape each rule's own tool-missing branch
has to survive, not just a static shape.

Sabotage-tested by hand, each against a `cp -r`'d scratch copy of the skill
dir with the mutation applied to the REAL file just long enough to run the
one test it should flip, then restored and confirmed byte-identical against
the scratch copy with `diff -u` before moving on:

- Push one skill over 120 lines -> red on `test_every_skill_is_at_most_120_lines`.
- Drop `paths`, or make `run` a string -> red on
  `test_every_proposed_rule_is_a_valid_verify_rule`.
- Remove the exit-77 branch from ONE of stack-powershell's two `run`
  commands, leaving the other intact -> red on
  `test_every_proposed_rule_names_a_missing_tool_path` (per-command) and on
  `test_missing_tool_branch_actually_exits_77_for_real` (the sabotaged
  command's subprocess no longer exits 77).
- Duplicate `-Settings` in a PowerShell `-Command` body -> red on
  `test_powershell_rule_commands_have_no_duplicate_parameters`.
- Shrink a skill's `description` to `"x"` -> red on
  `test_every_skill_has_valid_frontmatter_name_and_description`.

See the session report for the transcript of each run.
"""
import glob
import json
import os
import re
import shutil
import subprocess

import pytest
import yaml

import context  # noqa: F401  pylint: disable=unused-import

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, os.pardir, os.pardir))
SKILLS_DIR = os.path.join(ROOT, "plugin", "crew", "skills")

STACK_NAMES = [
    "stack-terraform",
    "stack-dotnet",
    "stack-angular",
    "stack-python",
    "stack-sql",
    "stack-powershell",
    "stack-bash",
]

MAX_LINES = 120
MIN_DESCRIPTION_LEN = 80

# One trigger term per skill: the stack's own tool/language name, lowercased.
# A description this short of a skill it names has stopped being findable by
# the "Use when the repo has ..." pattern crew's other skills rely on.
_TRIGGER_TERMS = {
    "stack-terraform": ("terraform",),
    "stack-dotnet": (".net", "dotnet", "c#"),
    "stack-angular": ("angular",),
    "stack-python": ("python",),
    "stack-sql": ("sql",),
    "stack-powershell": ("powershell",),
    "stack-bash": ("bash",),
}

_JSON_BLOCK_RE = re.compile(r"```json\n(.*?)\n```", re.S)
_CLOSING_DELIM_RE = re.compile(r"\n---(?:\n|\Z)")

_SH = shutil.which("sh")
_BASH = shutil.which("bash")
_PWSH = shutil.which("pwsh")


def _skill_path(name):
    return os.path.join(SKILLS_DIR, name, "SKILL.md")


def _read(path):
    with open(path, "r", encoding="utf-8") as fh:
        return fh.read()


def _frontmatter(text):
    assert text.startswith("---\n"), "SKILL.md must open with a --- frontmatter block"
    match = _CLOSING_DELIM_RE.search(text, 4)
    assert match, "frontmatter has no closing --- delimiter"
    return yaml.safe_load(text[4:match.start()])


def _json_rules(text):
    """Every fenced ```json block in the skill, parsed."""
    return [json.loads(block) for block in _JSON_BLOCK_RE.findall(text)]


def _all_rule_commands():
    """Yield (skill_name, rule_index, cmd_index, cmd) for every run command
    in every stack skill's proposed rule(s)."""
    for name in STACK_NAMES:
        for ri, rule in enumerate(_json_rules(_read(_skill_path(name)))):
            for ci, cmd in enumerate(rule.get("run") or []):
                yield name, ri, ci, cmd


def test_all_seven_stack_skills_exist():
    for name in STACK_NAMES:
        assert os.path.isfile(_skill_path(name)), f"{name}/SKILL.md is missing"


def test_no_stray_stack_skill_directories():
    """Catches a copy-paste that created an eighth dir nobody asked for."""
    found = sorted(
        os.path.basename(os.path.dirname(p))
        for p in glob.glob(os.path.join(SKILLS_DIR, "stack-*", "SKILL.md"))
    )
    assert found == sorted(STACK_NAMES)


def test_every_skill_is_at_most_120_lines():
    over = {}
    for name in STACK_NAMES:
        n = len(_read(_skill_path(name)).splitlines())
        if n > MAX_LINES:
            over[name] = n
    assert not over, f"skills over the {MAX_LINES}-line budget: {over}"


def test_every_skill_has_valid_frontmatter_name_and_description():
    """A nonempty description is not enough - `description = "x"` passed the
    old check. Require a minimum length and at least one concrete trigger
    term (the stack's own tool/language name) per skill."""
    for name in STACK_NAMES:
        fm = _frontmatter(_read(_skill_path(name)))
        assert isinstance(fm, dict), f"{name}: frontmatter did not parse to a mapping"
        assert fm.get("name") == name, f"{name}: frontmatter name is {fm.get('name')!r}"
        description = fm.get("description")
        assert isinstance(description, str) and description.strip(), (
            f"{name}: description is missing or empty"
        )
        stripped = description.strip()
        assert len(stripped) >= MIN_DESCRIPTION_LEN, (
            f"{name}: description is only {len(stripped)} chars "
            f"(minimum {MIN_DESCRIPTION_LEN}): {stripped!r}"
        )
        lowered = stripped.lower()
        terms = _TRIGGER_TERMS[name]
        assert any(t in lowered for t in terms), (
            f"{name}: description names none of its trigger terms {terms}"
        )


def test_every_skill_proposes_at_least_one_json_rule():
    for name in STACK_NAMES:
        rules = _json_rules(_read(_skill_path(name)))
        assert rules, f"{name}: no ```json rule block found"


def test_every_proposed_rule_is_a_valid_verify_rule():
    """Shape a verify-gate.sh rule actually needs: `paths` and `run`, both
    lists, `run` entries are single-line shell command strings (a rule with
    an embedded newline in `run` is rejected by this repo's own
    `map-audit.sh`, `reject_unrepresentable` - matching that rule here
    rather than a looser one)."""
    for name in STACK_NAMES:
        for rule in _json_rules(_read(_skill_path(name))):
            assert isinstance(rule.get("paths"), list) and rule["paths"], (
                f"{name}: rule.paths must be a non-empty list"
            )
            assert all(isinstance(p, str) for p in rule["paths"]), (
                f"{name}: every rule.paths entry must be a string glob"
            )
            run = rule.get("run")
            assert isinstance(run, list) and run, f"{name}: rule.run must be a non-empty list"
            for cmd in run:
                assert isinstance(cmd, str), f"{name}: rule.run entries must be strings"
                for ch in ("\n", "\r", "\x1d", "\x1e"):
                    assert ch not in cmd, f"{name}: rule.run entry embeds a framing character"
            if "reach" in rule:
                assert rule["reach"] in ("local",), f"{name}: unexpected reach {rule['reach']!r}"


def test_every_proposed_rule_names_a_missing_tool_path():
    """Each `run` COMMAND (not the rule's commands joined together) must
    contain the tool-missing convention this repo's gate already treats as
    UNVERIFIED: a probe that exits 77 with a message naming the missing
    tool. A joined-text search would stay green if only one of two commands
    lost its exit-77 branch; checking per command is what catches that."""
    for name, ri, ci, cmd in _all_rule_commands():
        assert "exit 77" in cmd, (
            f"{name} rule[{ri}].run[{ci}]: no exit-77 tool-missing branch"
        )
        assert "TOOL MISSING" in cmd, (
            f"{name} rule[{ri}].run[{ci}]: exit-77 branch does not name the missing tool"
        )


def _stub_bin_dir(tmp_path):
    """A PATH entry carrying only the shells these commands are written in -
    none of the tools any rule checks for (eslint, prettier, shellcheck,
    dotnet, terraform, tflint, sqlfluff, pwsh, powershell). `python3` is
    deliberately absent too: the python rule's probe is `python3 -m ruff
    --version || exit 77`, and a python3 that isn't found at all still
    fails with a nonzero exit that the same `||` catches, so leaving it out
    also exercises that "command not found" (127), not just "importable but
    absent module", reaches the same UNVERIFIED branch."""
    stub = tmp_path / "stubbin"
    stub.mkdir()
    for shell_name, real in (("sh", _SH), ("bash", _BASH)):
        if real:
            (stub / shell_name).symlink_to(real)
    return str(stub)


def _run_stripped(cmd, path_dir, cwd):
    env = {"PATH": path_dir}
    if os.environ.get("HOME"):
        env["HOME"] = os.environ["HOME"]
    return subprocess.run(
        [_BASH, "-c", cmd], env=env, cwd=str(cwd),
        capture_output=True, text=True, check=False, timeout=30,
    )


@pytest.mark.skipif(not (_SH and _BASH), reason="sh and bash are both required to run these rules")
def test_missing_tool_branch_actually_exits_77_for_real(tmp_path):
    """Structural checks above only look at the text. Actually run every
    proposed command with PATH stripped to a stub lacking every tool it
    checks for, and confirm it exits 77 with TOOL MISSING on stdout/stderr -
    the sabotage case this catches that the string search does not: a rule
    whose exit-77 branch is syntactically present but unreachable (wrong
    quoting, wrong `||`/`&&`, a typo in the tool name being probed)."""
    stub = _stub_bin_dir(tmp_path)
    for name, ri, ci, cmd in _all_rule_commands():
        work = tmp_path / f"{name}-{ri}-{ci}"
        work.mkdir()
        result = _run_stripped(cmd, stub, work)
        combined = result.stdout + result.stderr
        assert result.returncode == 77, (
            f"{name} rule[{ri}].run[{ci}] did not exit 77 with every tool stripped "
            f"from PATH: rc={result.returncode} stdout={result.stdout!r} "
            f"stderr={result.stderr!r}"
        )
        assert "TOOL MISSING" in combined, (
            f"{name} rule[{ri}].run[{ci}]: exit-77 branch produced no TOOL MISSING text"
        )


_PS_PARAM_RE = re.compile(r"(?<!\S)-([A-Za-z][A-Za-z]+)\b")


def _ps_command_body(cmd):
    """The text inside `-Command "..."` for a PowerShell rule command."""
    match = re.search(r'-Command "(.*)"\'$', cmd)
    assert match, f"no -Command \"...\" body found in: {cmd!r}"
    return match.group(1)


def test_powershell_rule_commands_have_no_duplicate_parameters():
    """PowerShell rejects a duplicate named parameter (`-Settings ...
    -Settings ...`) before analysis ever starts - a shape error a plain
    JSON/shape test cannot see because it lives inside one string. Parse
    each `-Command` body for `-Word` parameter tokens and require every
    name to appear at most once (case-insensitive - PowerShell parameter
    binding is case-insensitive)."""
    for ri, rule in enumerate(_json_rules(_read(_skill_path("stack-powershell")))):
        for ci, cmd in enumerate(rule.get("run") or []):
            if "-Command " not in cmd:
                continue
            body = _ps_command_body(cmd)
            params = [m.lower() for m in _PS_PARAM_RE.findall(body)]
            seen = set()
            dupes = set()
            for p in params:
                (dupes if p in seen else seen).add(p)
            assert not dupes, (
                f"stack-powershell rule[{ri}].run[{ci}] repeats parameter(s) "
                f"{sorted(dupes)} in one -Command invocation: {body!r}"
            )


def _pwsh_has_psscriptanalyzer():
    if not _PWSH:
        return False
    result = subprocess.run(
        [_PWSH, "-NoProfile", "-NonInteractive", "-Command",
         "if (Get-Module -ListAvailable -Name PSScriptAnalyzer) { exit 0 } else { exit 1 }"],
        capture_output=True, text=True, check=False, timeout=30,
    )
    return result.returncode == 0


def test_powershell_rule_exits_nonzero_on_a_real_analyzer_violation(tmp_path):
    """Invoke-ScriptAnalyzer finding results does not by itself make
    PowerShell's own process exit nonzero - the rule's script must capture
    $r and `exit 1` when it is non-empty, or a script with real violations
    PASSes. Runs the actual pwsh-targeted rule command (unmodified) against
    a script with a guaranteed-surfaced problem (a parse error, which
    PSScriptAnalyzer's docs say is always returned regardless of -Severity)
    - only where pwsh AND the PSScriptAnalyzer module are both present;
    skips with a reason otherwise rather than silently passing."""
    if not _pwsh_has_psscriptanalyzer():
        pytest.skip("pwsh with the PSScriptAnalyzer module is not available on this host")
    cmd = None
    for rule in _json_rules(_read(_skill_path("stack-powershell"))):
        for c in rule.get("run") or []:
            if 'TargetVersions=@(\\"7.0\\")' in c or "TargetVersions=@(\"7.0\")" in c:
                cmd = c
                break
    assert cmd is not None, "no pwsh (7.0-targeted) rule command found"
    (tmp_path / "bad.ps1").write_text(
        "function Test-Unterminated {\n    Write-Host 'missing a closing brace'\n",
        encoding="utf-8",
    )
    result = subprocess.run(
        [_BASH, "-c", cmd], cwd=str(tmp_path),
        capture_output=True, text=True, check=False, timeout=60,
    )
    assert result.returncode not in (0, 77), (
        f"expected a nonzero, non-77 exit on a script with a parse error; got "
        f"rc={result.returncode} stdout={result.stdout!r} stderr={result.stderr!r}"
    )

"""Doc tests for the seven `stack-*` skills (crew 1.0 T5 part 2, lane C2).

Each skill under `plugin/crew/skills/stack-<name>/SKILL.md` must: exist, stay
at or under 120 lines (the brief's budget - a skill this long stops loading
on demand and starts reading like the agent persona it replaced), carry
valid frontmatter with `name` and `description`, and propose at least one
`verify.json` rule that (a) parses as JSON with the shape the gate actually
reads (`paths`: list, `run`: list of command strings - see
`plugin/crew/hooks/scripts/verify-gate.sh` and `.crew/verify.json`) and (b)
names a missing-tool path that exits 77, the code this repo's own
`.crew/verify.json` and `verify-gate.sh` treat as UNVERIFIED rather than
PASS or FAIL (`plugin/crew/hooks/scripts/verify-gate.sh` reads `reach` and
treats a rule's own exit codes; 77 is the tool-missing convention already in
use for the `pwsh`, `ruff`/`pylint` and `npm` rules in this repo's
`.crew/verify.json`).

Sabotage-tested: push one skill over 120 lines and this suite goes red on
`test_every_skill_is_at_most_120_lines`; break a proposed rule's shape
(remove `paths`, make `run` a string instead of a list, or drop the exit-77
branch) and it goes red on `test_every_proposed_rule_is_a_valid_verify_rule`
or `test_every_proposed_rule_names_a_missing_tool_path`. Both were run by
hand against a scratch copy (`cp -r` the skill dir, mutate the copy, `diff`
against the original to confirm only the intended line changed) rather than
against the real files, and the real files were restored with `git checkout
--` immediately after - see the session report for the transcript.
"""
import glob
import json
import os
import re

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

_JSON_BLOCK_RE = re.compile(r"```json\n(.*?)\n```", re.S)
_CLOSING_DELIM_RE = re.compile(r"\n---(?:\n|\Z)")


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
    for name in STACK_NAMES:
        fm = _frontmatter(_read(_skill_path(name)))
        assert isinstance(fm, dict), f"{name}: frontmatter did not parse to a mapping"
        assert fm.get("name") == name, f"{name}: frontmatter name is {fm.get('name')!r}"
        description = fm.get("description")
        assert isinstance(description, str) and description.strip(), (
            f"{name}: description is missing or empty"
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
    """Each rule's `run` must contain the tool-missing convention this repo's
    gate already treats as UNVERIFIED: a probe that exits 77 with a message
    naming the missing tool, never a silent fall-through to PASS."""
    for name in STACK_NAMES:
        for rule in _json_rules(_read(_skill_path(name))):
            run_text = " ".join(rule["run"])
            assert "exit 77" in run_text, f"{name}: no exit-77 tool-missing branch in rule.run"
            assert "TOOL MISSING" in run_text, (
                f"{name}: exit-77 branch does not name the missing tool"
            )

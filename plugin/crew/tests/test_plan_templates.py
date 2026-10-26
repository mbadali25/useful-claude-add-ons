"""The plan step templates in crew's prompts must carry the `Lines:` label and a
kind tag, and must still pass the contract check /crew:approve runs.

L-0714 added `Lines:` per step and a kind tag on each production `Files:`
entry. The labels are additive: `crew_ticket.parse_plan` ignores `Lines:` and
reads a backticked path with the tag outside the backticks as one entry. This
test reads the templates themselves, as test_spec_templates_validate.py does
for the spec, so a template that drifts from the parser is caught here.
"""
import os
import re

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import crew_ticket

_PLUGIN = os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir)
_FILES = (
    "commands/plan.md",
    "skills/crew-plan/SKILL.md",
    "skills/crew-execute/SKILL.md",
    "skills/crew-standards/SKILL.md",
)
_FENCE_RE = re.compile(r"^```[^\n]*\n(.*?)^```", re.MULTILINE | re.DOTALL)
_LINES_RE = re.compile(r"^Lines:\s*\S", re.MULTILINE)
_FILES_RE = re.compile(r"^Files:\s*(.*)$", re.MULTILINE)
_TAG_RE = re.compile(r"`[^`]+`\s*\[(parser|guard|state-machine|other)\]")
_SPEC = """# T-0 template check          status: planned   risk: low

## Intent
x

## Exclusions
x

## Evidence
x

## Unknowns
x

## Touch
{touch}

## Acceptance checks
- [ ] x
"""


def _blocks(relative):
    with open(os.path.join(_PLUGIN, *relative.split("/")), encoding="utf-8") as handle:
        text = handle.read()
    return [b for b in _FENCE_RE.findall(text) if _FILES_RE.search(b)]


def _complete(block):
    """A fragment (crew-standards shows only Files, Lines and Standards) gets
    the Test and Risk labels it omits, so it can be validated as a step."""
    extra = "".join(f"{label}: x\n" for label in ("Test", "Risk")
                    if not re.search(rf"^{label}:", block, re.MULTILINE))
    return block.rstrip("\n") + "\n" + extra


@pytest.mark.parametrize("relative", _FILES)
def test_every_plan_template_in_the_docs_validates(relative, tmp_path):
    blocks = _blocks(relative)
    assert blocks, f"{relative}: no fenced plan step example (a block with a Files: line) found"
    for number, block in enumerate(blocks):
        assert _LINES_RE.search(block), f"{relative} block {number}: no Lines: label"
        files_line = _FILES_RE.search(block)
        assert files_line, f"{relative} block {number}: no Files: line"
        assert _TAG_RE.search(files_line.group(1)), (
            f"{relative} block {number}: no production Files entry carries a "
            f"kind tag in `path` [kind] form: {files_line.group(1)!r}")
        entries, _, problems = crew_ticket.parse_plan(_complete(block))
        assert not problems, f"{relative} block {number}: {problems}"
        touch = "\n".join(f"- `{entry}`" for entry in sorted(set(entries)))
        folder = tmp_path / f"b{number}" / ".work" / "tickets" / "T-0"
        folder.mkdir(parents=True)
        (folder / "spec.md").write_text(_SPEC.format(touch=touch), encoding="utf-8")
        (folder / "plan.md").write_text("# T-0 plan\n\n" + _complete(block), encoding="utf-8")

        found = crew_ticket.validate(str(tmp_path / f"b{number}"), "T-0")

        assert not found, f"{relative} block {number}: {found}"


def test_a_kind_tag_outside_backticks_does_not_split_the_path_entry():
    entries, _, problems = crew_ticket.parse_plan(
        "### Step 1: x\nFiles: `src/a.py` [parser], `tests/test_a.py`\nLines: 3\n"
        "Test: t\nRisk: low\n")

    assert entries == ["src/a.py", "tests/test_a.py"] and not problems

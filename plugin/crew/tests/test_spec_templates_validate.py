"""The spec templates that /crew:spec and /crew:fix tell the model to write
must pass the same section check /crew:approve runs.

crew 1.0.0-1.0.25 shipped spec.md's template with `## Acceptance` and fix.md's
with three sections on one line each (`## Intent      one sentence`), while
`crew_ticket.validate` requires six headings named exactly as in
`crew_ticket.SECTIONS`. A spec copied from either template was refused by
/crew:approve, so no ticket could get past plan approval. Every other test
built its spec from a hand-written fixture with the right headings, which is
why none of them saw it: this one reads the templates themselves.
"""
import os
import re

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import crew_ticket

_COMMANDS = os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir, "commands")
_FENCE_RE = re.compile(r"^```[^\n]*\n(.*?)^```", re.MULTILINE | re.DOTALL)


def _template(command):
    """The fenced block in commands/<command>.md that holds the spec.md
    template - the one containing an `## Intent` heading."""
    with open(os.path.join(_COMMANDS, command), encoding="utf-8") as handle:
        text = handle.read()
    blocks = [b for b in _FENCE_RE.findall(text) if re.search(r"^## Intent", b, re.MULTILINE)]
    assert len(blocks) == 1, f"{command}: expected one spec template block, found {len(blocks)}"
    return blocks[0]


@pytest.mark.parametrize("command", ["spec.md", "fix.md"])
def test_every_required_section_is_a_heading_in_the_template(command):
    found = crew_ticket.sections(_template(command))
    missing = [name for name in crew_ticket.SECTIONS if name.casefold() not in found]

    assert not missing, (
        f"commands/{command}'s spec template lacks ## {missing} - /crew:approve "
        f"(crew_ticket.validate) refuses a spec without them. Headings found: {sorted(found)}"
    )


@pytest.mark.parametrize("command", ["spec.md", "fix.md"])
def test_no_required_section_is_empty_in_the_template(command):
    found = crew_ticket.sections(_template(command))
    empty = [name for name in crew_ticket.SECTIONS if not found.get(name.casefold())]

    assert not empty, f"commands/{command}'s spec template leaves ## {empty} empty"

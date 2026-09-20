"""Every agent carries an `<example>` block - and its frontmatter survived it.

Two tests, and the second is the one that matters.

`test_every_agent_carries_an_example` is what was asked for: each
`agents/*.md` description holds at least one `<example>` block. On its own it
is not sufficient - it is a raw-text search, so it passes happily on 54 files
whose frontmatter has been destroyed, which is exactly what copying the
`plugin-dev` convention literally does. That convention writes the examples
as an unquoted multi-line plain scalar ending in a bare `Examples:`, and YAML
reads that trailing colon as a mapping-value indicator. `claude plugin
validate --strict` rejects it with "frontmatter: YAML frontmatter failed to
parse: YAML Parse error: Unexpected token. At runtime this agent loads with
its name taken from the filename and every other frontmatter field silently
dropped." A read-only role silently gains every tool; every agent drops to
the default model; the diff looks fine.

`test_frontmatter_survived_the_examples` is the backstop. It parses each
file's frontmatter with the same loader Claude Code uses and asserts it is a
mapping still carrying `name`, `description`, `model` and - where the file
had one before the change - a `tools` value byte-identical to the value
recorded in `agent_frontmatter_snapshot.json`. That snapshot was captured
from `git show 621d50dc:<path>` (origin/main, crew 0.19.92), NOT from the
rewritten files, so the comparison is against what was there rather than
against what the change wrote. A `tools:` grant that legitimately changes
later must be changed in the snapshot too, deliberately - the same shape as
`test_role_write_guard.py`'s policy table, and for the same reason: a grant
that drifts silently is the failure mode.

Sabotage, run by hand on 2026-09-20: converting one agent to the unquoted
form turned the backstop red (`parsed as NoneType`/ScannerError) while the
presence test stayed green. That contrast is the point of having two.

Run: python3 -m pytest plugin/crew/tests/test_agent_examples.py -q
"""
from __future__ import annotations

import glob
import json
import os
import re

import pytest
import yaml

_PLUGIN = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
_AGENTS = os.path.join(_PLUGIN, "agents")
_SNAPSHOT = os.path.join(os.path.dirname(__file__), "agent_frontmatter_snapshot.json")

# Same delimiter rule as scripts/check-marketplace.py's
# check_argument_hint_frontmatter: the closing `---` may sit at end of file.
_CLOSING = re.compile(r"\n---(?:\n|\Z)")


def _agent_paths():
    paths = sorted(glob.glob(os.path.join(_AGENTS, "*.md")))
    assert paths, f"no agent files under {_AGENTS}"
    return paths


def _raw_frontmatter(path):
    """The text between the opening and closing `---`, or None if absent.

    Text mode with universal newlines, so a CRLF checkout (core.autocrlf on
    Windows) and an LF one read identically - the loader does the same.
    """
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    if not text.startswith("---\n"):
        return None
    match = _CLOSING.search(text, 4)
    if not match:
        return None
    return text[4:match.start()]


def _snapshot():
    with open(_SNAPSHOT, encoding="utf-8") as fh:
        return json.load(fh)["agents"]


@pytest.mark.parametrize("path", _agent_paths(), ids=os.path.basename)
def test_every_agent_carries_an_example(path):
    """The request: at least one `<example>` block in the frontmatter.

    Deliberately a raw-text search, not a YAML parse - this test MUST stay
    green on a file whose frontmatter is broken, so that the backstop below
    is the one that names the real failure. Two tests that fail together on
    the same input tell the reader less than one that fails alone.
    """
    raw = _raw_frontmatter(path)
    assert raw is not None, f"{os.path.basename(path)}: no frontmatter block"
    assert "<example>" in raw and "</example>" in raw, (
        f"{os.path.basename(path)}: frontmatter carries no <example> block"
    )


@pytest.mark.parametrize("path", _agent_paths(), ids=os.path.basename)
def test_frontmatter_survived_the_examples(path):
    """The backstop: the frontmatter still loads as a mapping, and the fields
    the broken form would have destroyed are byte-identical to the fork point.
    """
    name = os.path.basename(path)
    raw = _raw_frontmatter(path)
    assert raw is not None, f"{name}: no frontmatter block"
    try:
        fields = yaml.safe_load(raw)
    except yaml.YAMLError as exc:
        pytest.fail(
            f"{name}: frontmatter is not valid YAML - at runtime every field "
            f"is silently dropped: {str(exc).splitlines()[0]}"
        )
    assert isinstance(fields, dict), (
        f"{name}: frontmatter parsed as {type(fields).__name__}, not a mapping"
    )
    for key in ("name", "description", "model"):
        assert key in fields and fields[key], f"{name}: `{key}` is missing or empty"
    assert isinstance(fields["description"], str)
    assert "<example>" in fields["description"], (
        f"{name}: <example> is in the file but not in the parsed description"
    )

    before = _snapshot()
    assert name in before, (
        f"{name}: not in agent_frontmatter_snapshot.json - a new agent needs "
        "a snapshot row so its tools grant is pinned like every other one"
    )
    for key in ("name", "model"):
        assert fields[key] == before[name][key], (
            f"{name}: `{key}` is {fields[key]!r}, was {before[name][key]!r}"
        )
    if "tools" in before[name]:
        assert "tools" in fields, (
            f"{name}: had a tools grant {before[name]['tools']!r} and now has "
            "none - that is the exact failure the block scalar exists to prevent"
        )
        assert fields["tools"] == before[name]["tools"], (
            f"{name}: tools is {fields['tools']!r}, was {before[name]['tools']!r}"
        )


def test_snapshot_covers_every_agent_and_nothing_else():
    """The snapshot and the directory name the same set, both directions.

    A file with no snapshot row would skip the tools comparison silently; a
    row with no file is a deleted agent whose pin nobody removed.
    """
    files = {os.path.basename(p) for p in _agent_paths()}
    rows = set(_snapshot())
    assert files == rows, (
        f"only in agents/: {sorted(files - rows)}; "
        f"only in snapshot: {sorted(rows - files)}"
    )

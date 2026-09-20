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
file's frontmatter with the same loader Claude Code uses and asserts, in
this order:

1. it is a mapping carrying non-empty `name`, `description`, `model` AND
   `tools` - judged against `_REQUIRED` here, never against what the
   snapshot happens to hold;
2. the snapshot row for that file carries the same required keys; and
3. the two agree, byte for byte, on `name`, `model` and `tools`.

Step 1 is separate from step 3 on purpose. The first version of this test
compared `tools` only `if "tools" in snapshot_row`, so a snapshot regenerated
from a tree that had already lost a `tools:` line produced a row without one
and the comparison silently skipped - Codex's review found it by deleting
`qa-reviewer.md`'s `tools:`, regenerating its row, and watching all 109 tests
pass. `test_regenerated_snapshot_without_tools_is_red` is that exact repro,
kept as a case so the gap cannot come back quietly.

The snapshot (`agent_frontmatter_snapshot.json`) was captured from
`git show 621d50dc:<path>` (origin/main, crew 0.19.92), NOT from the
rewritten files, so the comparison is against what was there rather than
against what the change wrote. A `tools:` grant that legitimately changes
later must be changed in the snapshot too, deliberately - the same shape as
`test_role_write_guard.py`'s policy table, and for the same reason: a grant
that drifts silently is the failure mode. What this file cannot catch is a
snapshot regenerated from a tree whose `tools:` was *changed* rather than
removed - a pin re-pinned to the wrong value looks like a pin. That is
`test_role_write_guard.py::test_policy_table_matches_the_agent_files`'s job,
which re-derives the write-scope partition from the same `tools:` lines
against a table nothing regenerates.

Sabotage, run by hand on 2026-09-20: converting one agent to the unquoted
form turned the backstop red (`mapping values are not allowed here`) while
the presence test stayed green. That contrast is the point of having two.

Run: python3 -m pytest plugin/crew/tests/test_agent_examples.py -q
"""
from __future__ import annotations

import glob
import json
import os
import re
import shutil

import pytest
import yaml

_PLUGIN = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
_AGENTS = os.path.join(_PLUGIN, "agents")
_SNAPSHOT = os.path.join(os.path.dirname(__file__), "agent_frontmatter_snapshot.json")

# Every agent file must carry all of these, non-empty. This tuple is the
# authority; the snapshot is only a record of the VALUES at the fork point.
_REQUIRED = ("name", "description", "model", "tools")
# The subset of _REQUIRED whose values are pinned in the snapshot.
_PINNED = ("name", "model", "tools")

# An agent that is meant to have no `model:` (inherit) or no `tools:` (all
# tools) goes here, keyed by filename, with the reason. Empty on purpose:
# every one of the 54 agents at 621d50dc carries both, and an entry here is a
# reviewed decision, not a way past the check.
_MAY_OMIT: dict[str, dict[str, str]] = {}

# Same delimiter rule as scripts/check-marketplace.py's
# check_argument_hint_frontmatter: the closing `---` may sit at end of file.
_CLOSING = re.compile(r"\n---(?:\n|\Z)")


def _agent_paths(agents_dir=_AGENTS):
    paths = sorted(glob.glob(os.path.join(agents_dir, "*.md")))
    assert paths, f"no agent files under {agents_dir}"
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


def _row_from_file(path):
    """A snapshot row regenerated from a file on disk - the SAME derivation
    that produced `agent_frontmatter_snapshot.json`, so the repro below can
    build the row a careless regeneration would have written."""
    fields = yaml.safe_load(_raw_frontmatter(path) or "") or {}
    return {k: fields[k] for k in _PINNED if k in fields}


def _problems(path, rows):
    """Everything wrong with one agent file against the snapshot rows.

    Returns a list of messages rather than asserting, so the repro test can
    run it against a temp copy and inspect what it says.
    """
    name = os.path.basename(path)
    found: list[str] = []
    raw = _raw_frontmatter(path)
    if raw is None:
        return [f"{name}: no frontmatter block"]
    try:
        fields = yaml.safe_load(raw)
    except yaml.YAMLError as exc:
        return [
            f"{name}: frontmatter is not valid YAML - at runtime every field "
            f"is silently dropped: {str(exc).splitlines()[0]}"
        ]
    if not isinstance(fields, dict):
        return [f"{name}: frontmatter parsed as {type(fields).__name__}, not a mapping"]

    # 1. The file, on its own terms. Not conditioned on the snapshot.
    for key in _REQUIRED:
        if key in _MAY_OMIT.get(name, {}):
            continue
        if not fields.get(key):
            found.append(
                f"{name}: `{key}` is missing or empty in the frontmatter - "
                "this is the exact field the unquoted form silently drops"
            )
    if isinstance(fields.get("description"), str) and "<example>" not in fields["description"]:
        found.append(f"{name}: <example> is in the file but not in the parsed description")

    # 2. The snapshot row, on its own terms.
    row = rows.get(name)
    if row is None:
        return found + [
            f"{name}: not in agent_frontmatter_snapshot.json - a new agent "
            "needs a snapshot row so its tools grant is pinned like every other"
        ]
    for key in _PINNED:
        if key in _MAY_OMIT.get(name, {}):
            continue
        if not row.get(key):
            found.append(
                f"{name}: snapshot row has no `{key}` - a snapshot regenerated "
                "from a tree that had already lost the field is not a baseline"
            )

    # 3. They agree.
    for key in _PINNED:
        if key in fields and key in row and fields[key] != row[key]:
            found.append(f"{name}: `{key}` is {fields[key]!r}, was {row[key]!r}")
    return found


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
    """The backstop: the frontmatter still loads as a mapping with every
    required field present, and the pinned fields are byte-identical to the
    fork point."""
    problems = _problems(path, _snapshot())
    assert not problems, "\n".join(problems)


def test_snapshot_rows_carry_every_pinned_key():
    """Judged on the snapshot alone, before any file is read: a row missing
    `tools` (or `model`, or `name`) is a broken baseline whatever the tree
    says, and the per-file test above would otherwise be the only thing
    naming it."""
    bad = {
        name: sorted(k for k in _PINNED if not row.get(k) and k not in _MAY_OMIT.get(name, {}))
        for name, row in _snapshot().items()
    }
    bad = {name: keys for name, keys in bad.items() if keys}
    assert not bad, f"snapshot rows missing pinned keys: {bad}"


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


def _copy_without_line(src, dst, prefix):
    with open(src, encoding="utf-8") as fh:
        lines = fh.read().split("\n")
    kept = [line for line in lines if not line.startswith(prefix)]
    assert len(kept) == len(lines) - 1, f"expected exactly one `{prefix}` line in {src}"
    with open(dst, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(kept))


def test_regenerated_snapshot_without_tools_is_red(tmp_path):
    """Codex's repro, verbatim: delete qa-reviewer.md's `tools:` line, then
    regenerate its snapshot row from that broken file. Every version of this
    check that trusts the snapshot's key set passes; this one must not.

    Runs on a temp copy so the real agent file and snapshot are untouched.
    """
    src = os.path.join(_AGENTS, "qa-reviewer.md")
    good = tmp_path / "good" / "qa-reviewer.md"
    broken = tmp_path / "broken" / "qa-reviewer.md"
    good.parent.mkdir()
    broken.parent.mkdir()
    shutil.copyfile(src, good)
    _copy_without_line(src, broken, "tools:")

    # Must-allow control: the untouched copy with a row regenerated from
    # itself is clean, so the failure below is about the missing field and
    # not about the harness.
    assert _problems(str(good), {"qa-reviewer.md": _row_from_file(str(good))}) == []

    # Must-block: the regenerated row has no `tools`, and neither does the
    # file. Both the file check and the row check must say so.
    row = _row_from_file(str(broken))
    assert "tools" not in row, "repro precondition: regenerated row must lack tools"
    problems = _problems(str(broken), {"qa-reviewer.md": row})
    assert any("`tools` is missing or empty in the frontmatter" in p for p in problems), problems
    assert any("snapshot row has no `tools`" in p for p in problems), problems

    # And the un-regenerated snapshot - the real one - catches the same file
    # by value, independently of the two checks above.
    problems = _problems(str(broken), _snapshot())
    assert any("`tools` is missing or empty in the frontmatter" in p for p in problems), problems


def test_regenerated_snapshot_without_model_is_red(tmp_path):
    """The same gap for `model`: an agent that silently lost its tier."""
    src = os.path.join(_AGENTS, "pm.md")
    broken = tmp_path / "pm.md"
    _copy_without_line(src, broken, "model:")
    row = _row_from_file(str(broken))
    assert "model" not in row
    problems = _problems(str(broken), {"pm.md": row})
    assert any("`model` is missing or empty in the frontmatter" in p for p in problems), problems
    assert any("snapshot row has no `model`" in p for p in problems), problems

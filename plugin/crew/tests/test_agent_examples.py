"""Every agent carries an `<example>` block - and its frontmatter survived it.

Two tests, and the second is the one that matters.

`test_every_agent_carries_an_example` is what was asked for: each
`agents/*.md` description holds at least one `<example>` block. On its own it
is not sufficient - it stays green on a file whose frontmatter has been
destroyed, which is exactly what copying the `plugin-dev` convention
literally does. That convention writes the examples as an unquoted
multi-line plain scalar ending in a bare `Examples:`, and YAML reads that
trailing colon as a mapping-value indicator. `claude plugin validate
--strict` rejects it with "frontmatter: YAML frontmatter failed to parse:
YAML Parse error: Unexpected token. At runtime this agent loads with its
name taken from the filename and every other frontmatter field silently
dropped." A read-only role silently gains every tool; every agent drops to
the default model; the diff looks fine.

`test_frontmatter_survived_the_examples` is the backstop. It parses each
file's frontmatter with the same loader Claude Code uses and asserts, in
this order:

1. it is a mapping carrying non-empty `name`, `description`, `model` AND
   `tools` - judged against `_REQUIRED` here, never against what the
   snapshot happens to hold - and `description` is a string whose
   `<example>` / `</example>` tags open and close in order;
2. the snapshot row for that file carries the same required keys; and
3. the two agree, byte for byte, on `name`, `model` and `tools`.

Step 1 is separate from step 3 on purpose. The first version of this test
compared `tools` only `if "tools" in snapshot_row`, so a snapshot regenerated
from a tree that had already lost a `tools:` line produced a row without one
and the comparison silently skipped - Codex's review found it by deleting
`qa-reviewer.md`'s `tools:`, regenerating its row, and watching every test
pass. `test_regenerated_snapshot_without_tools_is_red` is that exact repro,
kept as a case so the gap cannot come back quietly.

Codex's second round found two more ways past the example check and one
false alarm in the sabotage helper, all kept here as cases:

- a `description` that parses to a mapping (`{bad: value}`) with the tags
  hidden in a YAML comment passed, because the tags were searched in the raw
  file text and the type was never checked. Both tests now look for the
  tags inside the PARSED description string, in order, never in the raw
  text (`_example_problem`). The presence test falls back to the raw text
  only when the frontmatter does not parse at all - that fallback is what
  keeps it green on a broken file so the backstop is the one test that
  names the real failure;
- `"<example>unfinished"` with `</example>` in a comment passed for the
  same reason - now an ordering check, not two substring checks;
- the sabotage helper deleted the `tools:` LINE, so a legitimate multi-line
  `tools: >-` left an orphaned continuation and the helper raised
  ParserError on a correct tree. It now loads the mapping, deletes the key,
  and re-dumps (`_copy_without_key`), so any valid YAML shape works.

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
_EXAMPLE_TAG = re.compile(r"</?example>")


def _agent_paths(agents_dir=_AGENTS):
    paths = sorted(glob.glob(os.path.join(agents_dir, "*.md")))
    assert paths, f"no agent files under {agents_dir}"
    return paths


def _split(path):
    """(raw frontmatter text, body) - frontmatter is None when absent.

    Text mode with universal newlines, so a CRLF checkout (core.autocrlf on
    Windows) and an LF one read identically - the loader does the same.
    """
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    if not text.startswith("---\n"):
        return None, text
    match = _CLOSING.search(text, 4)
    if not match:
        return None, text
    return text[4:match.start()], text[match.end():]


def _raw_frontmatter(path):
    return _split(path)[0]


def _snapshot():
    with open(_SNAPSHOT, encoding="utf-8") as fh:
        return json.load(fh)["agents"]


def _row_from_file(path):
    """A snapshot row regenerated from a file on disk - the SAME derivation
    that produced `agent_frontmatter_snapshot.json`, so the repro below can
    build the row a careless regeneration would have written."""
    fields = yaml.safe_load(_raw_frontmatter(path) or "") or {}
    return {k: fields[k] for k in _PINNED if k in fields}


def _example_problem(description):
    """Why the PARSED description does not carry well-formed example blocks,
    or None. Judged on the parsed string only - a tag in a YAML comment, in a
    key name, or in raw text outside the value does not count."""
    if not isinstance(description, str):
        return f"description parsed as {type(description).__name__}, not a string"
    tags = _EXAMPLE_TAG.findall(description)
    if not tags:
        return "parsed description carries no <example> block"
    expect_open = True
    for tag in tags:
        if (tag == "<example>") != expect_open:
            return f"parsed description's example tags are out of order: {tags}"
        expect_open = not expect_open
    if not expect_open:
        return f"parsed description has an unclosed <example>: {tags}"
    return None


def _problems(path, rows):
    """Everything wrong with one agent file against the snapshot rows.

    Returns a list of messages rather than asserting, so the repro tests can
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
    if fields.get("description"):
        problem = _example_problem(fields["description"])
        if problem:
            found.append(f"{name}: {problem}")

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


def _presence_problem(path):
    """The request, judged on the parsed description when the frontmatter
    parses. When it does not parse at all, fall back to the raw text - on
    purpose, so this test stays green on a destroyed file and the backstop is
    the one that fails alone. Two tests that fail together on the same input
    tell the reader less than one that fails alone."""
    name = os.path.basename(path)
    raw = _raw_frontmatter(path)
    if raw is None:
        return f"{name}: no frontmatter block"
    try:
        fields = yaml.safe_load(raw)
    except yaml.YAMLError:
        if "<example>" in raw and "</example>" in raw:
            return None
        return f"{name}: frontmatter carries no <example> block"
    if not isinstance(fields, dict):
        return f"{name}: frontmatter parsed as {type(fields).__name__}, not a mapping"
    problem = _example_problem(fields.get("description"))
    return f"{name}: {problem}" if problem else None


@pytest.mark.parametrize("path", _agent_paths(), ids=os.path.basename)
def test_every_agent_carries_an_example(path):
    """The request: at least one well-formed `<example>` block in the parsed
    description."""
    problem = _presence_problem(path)
    assert problem is None, problem


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


# --- fixtures for the repro cases -------------------------------------------

def _write(path, text):
    payload = text  # materialised before open(): CLAUDE.md's truncate-at-open landmine
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(payload)


def _copy_without_key(src, dst, key):
    """Copy an agent file with one frontmatter key removed, by loading the
    mapping, deleting the key, and re-dumping - never by deleting a line, so
    a valid multi-line value (`tools: >-` with an indented continuation)
    does not leave an orphaned continuation behind."""
    raw, body = _split(src)
    fields = yaml.safe_load(raw)
    assert isinstance(fields, dict) and key in fields, f"{src}: no `{key}` to remove"
    del fields[key]
    dumped = yaml.safe_dump(fields, sort_keys=False, allow_unicode=True, width=10**6)
    assert yaml.safe_load(dumped) == fields, "re-dump must round-trip"
    _write(dst, f"---\n{dumped}---\n{body}")


def _real_qa_reviewer_fields():
    fields = yaml.safe_load(_raw_frontmatter(os.path.join(_AGENTS, "qa-reviewer.md")))
    assert isinstance(fields, dict)
    return fields


def _qa_reviewer_with_description(dst, description_line, comment_line):
    """qa-reviewer.md's real pinned fields around a substituted description,
    with a YAML comment line placed in the frontmatter."""
    fields = _real_qa_reviewer_fields()
    _write(dst, (
        "---\n"
        f"name: {fields['name']}\n"
        f"{comment_line}\n"
        f"description: {description_line}\n"
        f"tools: {fields['tools']}\n"
        f"model: {fields['model']}\n"
        "---\n\nbody\n"
    ))


def _qa_reviewer_with_folded_tools(dst):
    """qa-reviewer.md's fields with the description as a double-QUOTED scalar
    and `tools:` immediately after it as a folded block scalar (`>-`) with the
    same value indented underneath - Codex's exact shape. Every parsed value
    is identical to the real file's. The quoting is load-bearing: after a
    block-scalar description, a line-deleting helper's orphaned continuation
    is silently absorbed into the description and parses; after a quoted
    one it is a ParserError, which is the false alarm being reproduced."""
    raw, body = _split(os.path.join(_AGENTS, "qa-reviewer.md"))
    fields = yaml.safe_load(raw)
    quoted = json.dumps(fields["description"], ensure_ascii=False)  # JSON escapes are valid YAML "..." escapes
    _write(dst, (
        "---\n"
        f"name: {fields['name']}\n"
        f"description: {quoted}\n"
        "tools: >-\n"
        f"  {fields['tools']}\n"
        f"model: {fields['model']}\n"
        "---\n" + body
    ))
    assert yaml.safe_load(_raw_frontmatter(dst)) == fields, "folded form must parse identically"


# --- repro cases --------------------------------------------------------------

def test_regenerated_snapshot_without_tools_is_red(tmp_path):
    """Codex round 1, verbatim: delete qa-reviewer.md's `tools`, then
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
    _copy_without_key(src, broken, "tools")

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
    _copy_without_key(src, broken, "model")
    row = _row_from_file(str(broken))
    assert "model" not in row
    problems = _problems(str(broken), {"pm.md": row})
    assert any("`model` is missing or empty in the frontmatter" in p for p in problems), problems
    assert any("snapshot row has no `model`" in p for p in problems), problems


def test_mapping_description_with_tags_in_a_comment_is_red(tmp_path):
    """Codex round 2, repro 1: `description: {bad: value}` and a frontmatter
    comment carrying `<example></example>`, pinned fields unchanged. Both
    tests passed when the tags were searched in the raw text."""
    dst = tmp_path / "qa-reviewer.md"
    _qa_reviewer_with_description(dst, "{bad: value}", "# <example></example>")
    assert _row_from_file(str(dst)) == _snapshot()["qa-reviewer.md"], "pinned fields must be intact"

    presence = _presence_problem(str(dst))
    assert presence and "parsed as dict, not a string" in presence, presence
    problems = _problems(str(dst), _snapshot())
    assert any("parsed as dict, not a string" in p for p in problems), problems


def test_unclosed_example_with_closer_in_a_comment_is_red(tmp_path):
    """Codex round 2, repro 2: `description: "<example>unfinished"` and a
    separate comment carrying `</example>`. Two independent substring checks
    on the raw text found both tags; the ordered check on the parsed string
    finds an unclosed block."""
    dst = tmp_path / "qa-reviewer.md"
    _qa_reviewer_with_description(dst, '"<example>unfinished"', "# </example>")
    assert _row_from_file(str(dst)) == _snapshot()["qa-reviewer.md"], "pinned fields must be intact"

    presence = _presence_problem(str(dst))
    assert presence and "unclosed <example>" in presence, presence
    problems = _problems(str(dst), _snapshot())
    assert any("unclosed <example>" in p for p in problems), problems


def test_tags_out_of_order_is_red(tmp_path):
    """The neighbour of repro 2: a closer before the opener has both tags
    present and is still not a block."""
    dst = tmp_path / "qa-reviewer.md"
    _qa_reviewer_with_description(dst, '"</example> x <example>"', "# nothing")
    presence = _presence_problem(str(dst))
    assert presence and "out of order" in presence, presence


def test_folded_multiline_tools_is_a_correct_tree(tmp_path):
    """Codex round 2, repro 3 - the must-pass control: a valid multi-line
    `tools: >-` directly after the description parses to the identical value,
    so the backstop passes on it, and the sabotage helper removes the key
    cleanly instead of raising ParserError on an orphaned continuation."""
    folded = tmp_path / "folded" / "qa-reviewer.md"
    stripped = tmp_path / "stripped" / "qa-reviewer.md"
    folded.parent.mkdir()
    stripped.parent.mkdir()
    _qa_reviewer_with_folded_tools(folded)

    # Correct tree: clean against the real snapshot.
    assert _problems(str(folded), _snapshot()) == []
    assert _presence_problem(str(folded)) is None

    # The helper handles the multi-line shape - this line raised ParserError
    # with the old delete-the-line helper.
    _copy_without_key(str(folded), stripped, "tools")
    fields = yaml.safe_load(_raw_frontmatter(str(stripped)))
    assert isinstance(fields, dict) and "tools" not in fields
    problems = _problems(str(stripped), _snapshot())
    assert any("`tools` is missing or empty in the frontmatter" in p for p in problems), problems

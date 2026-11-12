"""Owner order 2026-11-10: crew never adds, or tells an agent to add, a
`Co-Authored-By` trailer or a "Generated with Claude Code" line to a commit or
PR body.

The instruction surfaces (commands, skills, agents, templates, the wave lane
prompt) may mention the trailer only to forbid it. A line that names it without
a negation or forbid word is an instruction to add it, and fails here.
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CREW = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(CREW, "hooks", "scripts"))

SURFACES = ("commands", "skills", "agents", "templates")
TRAILER = re.compile(r"co-?authored-?by|generated with \[?claude|noreply@anthropic", re.I)
FORBIDS = re.compile(
    r"\b(no|not|never|nor|without|forbid\w*|refus\w*|omit\w*|reports?|checks?|trailer tokens?|token)\b", re.I)


def offending(text):
    """Lines that name the trailer with no word that forbids, reports or checks it."""
    return [line.strip() for line in text.splitlines()
            if TRAILER.search(line) and not FORBIDS.search(line)]


def _surface_files():
    for top in SURFACES:
        for base, _dirs, names in os.walk(os.path.join(CREW, top)):
            if os.sep + "tests" in base or os.sep + "_test" in base:
                continue
            for name in names:
                if name.endswith((".md", ".json", ".txt", ".sh", ".ps1", ".py")):
                    yield os.path.join(base, name)


def test_no_crew_instruction_surface_tells_anyone_to_add_the_trailer():
    bad = []
    for path in _surface_files():
        with open(path, encoding="utf-8", errors="replace") as handle:
            bad += [f"{os.path.relpath(path, CREW)}: {line}" for line in offending(handle.read())]
    assert bad == []


def test_detector_flags_an_instruction_to_add_it():
    assert offending("End every commit with `Co-Authored-By: Claude <noreply@anthropic.com>`.")
    assert offending("Body ends: Generated with [Claude Code](https://claude.com/claude-code)")
    assert not offending("A dispatched prompt adds no `Co-Authored-By` trailer.")


def test_lane_prompt_tells_the_lane_to_add_no_trailer(tmp_path):
    import test_crew_wave as wave  # pylint: disable=import-outside-toplevel
    text = wave._prompt(wave._started(tmp_path))  # pylint: disable=protected-access

    assert "no Co-Authored-By trailer" in text
    assert not offending(text)


def test_implement_md_tells_the_developer_to_add_no_trailer():
    with open(os.path.join(CREW, "commands", "implement.md"), encoding="utf-8") as handle:
        text = " ".join(handle.read().split())

    assert "add no `Co-Authored-By` trailer" in text and "Generated with Claude Code" in text


def test_practices_md_states_the_owner_rule_and_where_the_harness_default_is_set():
    path = os.path.join(CREW, "skills", "crew-best-practices", "references", "practices.md")
    with open(path, encoding="utf-8") as handle:
        text = " ".join(handle.read().split())

    assert "crew never adds a `Co-Authored-By` trailer" in text
    assert "`attribution`" in text and "settings.json" in text

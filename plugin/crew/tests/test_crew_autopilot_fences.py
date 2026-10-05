"""L-0642: autopilot's open-questions stop sees through code fences, and stops
when it cannot tell (crew_autopilot_fences.py, called by
crew_autopilot._open_items).

The floor: `_MAIN_open_items` below is a verbatim, never-edited copy of main's
parser at 155fe6d8. For every text of a generated corpus, each item it returns
is in `_open_items`, and every text whose fence is not clean (computed from
the generator's parameters, never by parsing) and that names an Open-questions
section returns something.
"""

from __future__ import annotations

import itertools
import re

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import crew_autopilot
import crew_autopilot_fences


def _items(text):
    return crew_autopilot._open_items(text)  # pylint: disable=protected-access


# --- main's parser at 155fe6d8, verbatim: do not edit -------------------------------------------
# pylint: disable=invalid-name
_MAIN_BULLET = ("- ", "* ", "+ ")
_MAIN_HEADING = re.compile(r"^(#{1,6})\s+(.*)$")
# An answered item: `none` or `n/a` alone or followed by a separator and the
# answer (`none - postgres`), checked `[x]`, or struck `~~`. `None of the
# owners has decided` is an open question, not an answer.
_MAIN_ANSWERED = re.compile(r"^(?:(?:none|n/a)(?:$|\s*[-:,(–—])|\[x\]|~~|-$)")


def _MAIN_open_items(text):
    """Unanswered items under any `Open questions` heading, at any level, down
    to the next heading of the same or a higher level -- a sub-heading inside
    the section stays inside it. See `_ANSWERED` for what counts as answered."""
    items, depth = [], 0
    for line in (text or "").splitlines():
        heading = _MAIN_HEADING.match(line)
        if heading:
            level, title = len(heading.group(1)), heading.group(2).strip()
            if depth and level > depth:
                continue
            if title.lower().startswith("open questions"):
                depth, line = level, title[len("open questions"):]
            else:
                depth = 0
        if not depth:
            continue
        item = line.strip()
        for mark in _MAIN_BULLET:
            if item.startswith(mark):
                item = item[len(mark):].strip()
        item = re.sub(r"^\d+[.)]\s*", "", item)
        bare = item.strip("\"'`.: ").lower()
        if not bare or _MAIN_ANSWERED.match(bare):
            continue
        items.append(item)
    return items
# pylint: enable=invalid-name
# --- end of the verbatim copy -------------------------------------------------------------------


ROUND2_INDENTED_CLOSER = ("go\n```text\n    ```\n```\n\n## Open questions\n- which DB?\n"
                          "```sql\nselect 1;\n```\n")
ROUND2_LIST_NESTED = ("go\n- example\n  ```text\n  foo\n\n## Open questions\n- which DB?\n"
                      "```sql\nselect 1;\n```\n")


def _unclear(items):
    return [i for i in items if i.startswith(crew_autopilot.UNCLEAR_FENCE)]


@pytest.mark.parametrize("text", [
    "go\n## Open questions\n- none\n```\nfoo\n  ```\n```\n",
    "go\n- item\n  ```\n  code\n  ```\n## Open questions\n- none\n",
    "go\n## Open questions\n- none\n\n```\ncode\n",
    "go\n\t```\ncode\n\t```\n## Open questions\n- none\n",
    "go\n```example```\n\n## Open questions\n- none\n",
    "go\n````markdown\n```\n````\n## Open questions\n- none\n",
    "go\n  ```\n  ## Open questions\n  - which DB?\n  ```\n",
], ids=["indented-closer-in-section", "list-nested-pair-before", "unclosed-after-section",
        "tab-indented-opener", "inline-backticks", "shorter-run-inside", "section-only-indented"])
def test_open_questions_ambiguous_fence_could_not_tell(text):
    assert len(_unclear(_items(text))) == 1, _items(text)


def test_could_not_tell_names_the_first_unclear_line():
    assert _unclear(_items("go\n## Open questions\n- none\n```\nfoo\n  ```\n```\n"))[0].startswith(
        f"{crew_autopilot.UNCLEAR_FENCE} (line 6)")


@pytest.mark.parametrize("text", [
    "go\n## Open questions\n- none - settled\n```\n# how to check\n```\n",
    "go\n```\n# setup\n```\n## Open questions\n- none\n",
    "go\n~~~\n# setup\n~~~\n## Open questions\n- none\n",
], ids=["clean-after-answered", "clean-before", "clean-tilde-before"])
def test_open_questions_clean_fences_do_not_stop(text):
    assert _items(text) == []


@pytest.mark.parametrize("text", ["go\n  ```\n  # x\n  ```\n", "go\n```\nstill open\n"],
                         ids=["indented-pair", "unclosed"])
def test_open_questions_ambiguous_fence_without_a_section_does_not_stop(text):
    assert _items(text) == []


def test_a_fence_that_opens_the_section_is_an_item():
    """A tracked fence before any item line: nothing says what it asks."""
    assert _items("go\n## Open questions\n```\n# how to check\n```\n") == [
        crew_autopilot.UNEXPLAINED_FENCE]


def test_a_fence_after_an_item_is_not_unexplained():
    assert _items("go\n## Open questions\n- none - postgres\n```\n# psql\n```\n") == []


# --- the floor: a generated corpus --------------------------------------------------------------

OPENERS = ("```", "```text", "~~~", "````", "```a`b")
INDENTS = ("", "  ", "    ", "\t")
CLOSERS = ("same", "longer", "shorter", "other", "trailing", "none")
CLOSER_INDENTS = ("", "  ", "    ")
LEAD_INS = ("", "- none - settled\n", "- which DB?\n")
BODIES = ("# how to check", "select 1;", "")
POSITIONS = ("before", "inside", "after")
TAILS = ("- none\n", "- which port?\n")


def _closer(opener, kind):
    marker, run = opener[0], len(opener) - len(opener.lstrip(opener[0]))
    return {"same": marker * run, "longer": marker * (run + 1),
            "shorter": marker * (run - 1) if run > 3 else marker * 2 + " x",
            "other": ("~" if marker == "`" else "`") * run,
            "trailing": marker * run + " end", "none": None}[kind]


def _clean(opener, indent, closer, closer_indent):
    """From the parameters only: a column-0 opener (no backtick in a backtick
    info string) closed at column 0 by the same marker, at least as long,
    nothing after it."""
    info = opener.lstrip(opener[0])
    return (indent == "" and not (opener[0] == "`" and "`" in info)
            and closer in ("same", "longer") and closer_indent == "")


def _corpus():
    for opener, indent, closer, cind, lead, body, where, tail in itertools.product(
            OPENERS, INDENTS, CLOSERS, CLOSER_INDENTS, LEAD_INS, BODIES, POSITIONS, TAILS):
        close = _closer(opener, closer)
        if close is None and cind:
            continue
        block = f"{indent}{opener}\n" + (f"{indent}{body}\n" if body else "") \
            + (f"{cind}{close}\n" if close is not None else "")
        if where == "before":
            text = f"go\n{block}## Open questions\n{lead}{tail}"
        elif where == "inside":
            text = f"go\n## Open questions\n{lead}{block}{tail}"
        else:
            text = f"go\n## Open questions\n{lead}{tail}## Notes\n{block}"
        yield text, _clean(opener, indent, closer, cind) and (close is not None)
    yield ROUND2_INDENTED_CLOSER, False
    yield ROUND2_LIST_NESTED, False


def test_open_questions_fence_corpus_never_below_main():
    corpus = list(_corpus())
    below, silent, gained, quiet_clean = [], [], 0, 0
    for text, clean in corpus:
        main, got = _MAIN_open_items(text), _items(text)
        below += [text] if any(item not in got for item in main) else []
        silent += [text] if not clean and not got else []
        gained += bool(got) and not main
        quiet_clean += clean and not got
    texts = {text for text, _clean_ in corpus}
    assert (below[:3], silent[:3]) == ([], [])
    assert {ROUND2_INDENTED_CLOSER, ROUND2_LIST_NESTED} <= texts
    assert gained > 0 and quiet_clean > 0, (gained, quiet_clean)
    assert len(corpus) > 10000


def test_names_open_questions_sees_indented_and_fenced_headings():
    heading = crew_autopilot._HEADING  # pylint: disable=protected-access
    assert [crew_autopilot_fences.names_open_questions(t, heading) for t in (
        "  ## Open questions\n", "```\n## open questions: x\n```\n", "## Notes\n- a\n")] == [
            True, True, False]

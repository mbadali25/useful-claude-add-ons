"""T-0046: `crew_bookkeeping.claim_numbers_only`, the one predicate the scope
guard and the completion audit share for the `crew-markdown-lines` claim in
`plugin/*/BUDGETS.md`.

It is the whole allowance, so it is tested as a table: every must-block row
returns False AND names the rule that refused it (a row refused by a later
rule than the one it exists for is a vacuous row, and `sabotage_bookkeeping.py`
relies on the reason to tell them apart), and every must-allow row returns
True. The grammar is restated from `scripts/check-marketplace.py`, so a
lockstep test compares the two.
"""
import importlib.util
import os

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import crew_bookkeeping as cb

PATH = "plugin/crew/BUDGETS.md"
REPO = os.path.dirname(os.path.dirname(context._ROOT))  # pylint: disable=protected-access
CHECKER = os.path.join(REPO, "scripts", "check-marketplace.py")

# A copy of origin/main's plugin/crew/BUDGETS.md head (502cb137), fixed here so
# re-measuring the real file never moves a test. The marker is line 10, the
# bound line 11, and line 12 carries another `N lines` inside the window.
BUDGETS = """# Instruction-surface budgets (crew 1.0, T8)

Tracks the size targets `docs/review/04-redesign.md`'s "Instruction surface" table sets, and
what `scripts/check_instructions.py` actually measures. Refresh both the count below and
`.budget-allowance.json` together — a stale number here is worse than none, because it looks
checked.

## Plugin Markdown total

<!-- claim: crew-markdown-lines -->
`git ls-files 'plugin/crew/*.md'` currently totals 18,176 lines across 121 files (including this
file). Target: ≤6,000 lines (`docs/review/04-redesign.md`). This number moves every time a tracked
`plugin/crew/*.md` file is added, removed or resized — including this one — so re-measure rather
than trusting it; the marker above is what keeps that honest.

The crew 1.0 T2 deletions (the PM, pulse, journal and 51 retired agents) landed the "held" half of
this gap: 58 files and roughly 11,400 lines, as T8 estimated. What remains:

- **To trim** (`.budget-allowance.json`, reason `T8: to trim`): 9 command files still over the
  120-line command budget that T8 judged too large or too test-coupled to safely rewrite in
  this pass — `review.md` (551 lines, the brief's own example) foremost among them, since nine
  test files assert specific sentences inside it and moving that prose to a reference doc means
  updating every one of those assertions, not just the command file. Trimming all nine to exactly
  120 would save about 1,382 more lines. (`work.md` left the list in T2: it is a removal stub now.)
"""

FENCED = BUDGETS + """
```
<!-- claim: crew-markdown-lines -->
123 lines in the example
```
"""

LINES = BUDGETS.splitlines(keepends=True)


def _swap(text, old, new):
    assert text.count(old) == 1, old
    return text.replace(old, new)


def _lines(edit):
    lines = list(LINES)
    edit(lines)
    return "".join(lines)


def _move_marker_down(lines):
    lines[9], lines[10] = lines[10], lines[9]


def _remove_marker(lines):
    lines[9] = "\n"


def _add_line(lines):
    lines.insert(30, "One more line.\n")


def _remove_line(lines):
    del lines[20]


def _crlf(lines):
    lines[10] = lines[10].replace("\n", "\r\n")


MUST_BLOCK = [
    ("prose-edit", PATH, BUDGETS, _swap(BUDGETS, "currently totals", "now totals"),
     "more than its numbers"),
    ("number-to-word", PATH, BUDGETS, _swap(BUDGETS, "18,176 lines", "many lines"),
     "bind different lines"),
    ("number-outside-window", PATH, BUDGETS, _swap(BUDGETS, "about 1,382", "about 1,383"),
     "no crew-markdown-lines marker binds"),
    ("other-line-in-window", PATH, BUDGETS, _swap(BUDGETS, "≤6,000", "≤7,000"),
     "no crew-markdown-lines marker binds"),
    ("marker-removed", PATH, BUDGETS, _lines(_remove_marker), "bind different lines"),
    ("marker-moved", PATH, BUDGETS, _lines(_move_marker_down), "bind different lines"),
    ("line-added", PATH, BUDGETS, _lines(_add_line), "added or removed"),
    ("line-removed", PATH, BUDGETS, _lines(_remove_line), "added or removed"),
    ("crlf-changed", PATH, BUDGETS, _lines(_crlf), "more than its numbers"),
    ("marker-in-fence", PATH, FENCED, _swap(FENCED, "123 lines", "124 lines"),
     "no crew-markdown-lines marker binds"),
    ("other-path", "plugin/crew/README.md", BUDGETS,
     _swap(BUDGETS, "18,176 lines", "18,200 lines"), "not plugin/*/BUDGETS.md"),
    ("nested-path", "plugin/crew/docs/BUDGETS.md", BUDGETS,
     _swap(BUDGETS, "18,176 lines", "18,200 lines"), "not plugin/*/BUDGETS.md"),
    ("undecodable", PATH, BUDGETS.encode("utf-8") + b"\xff",
     _swap(BUDGETS, "18,176 lines", "18,200 lines"), "could not tell"),
]

MUST_ALLOW = [
    ("lines-and-files", BUDGETS,
     _swap(BUDGETS, "18,176 lines across 121 files", "18,200 lines across 122 files")),
    ("comma-added", _swap(BUDGETS, "18,176 lines", "9,999 lines"),
     _swap(BUDGETS, "18,176 lines", "10,000 lines")),
]


@pytest.mark.parametrize("case,path,before,after,reason", MUST_BLOCK,
                         ids=[row[0] for row in MUST_BLOCK])
def test_must_block(case, path, before, after, reason):
    ok, why = cb.claim_numbers_only(before, after, path)

    assert (ok, reason in why) == (False, True), (case, why)


@pytest.mark.parametrize("case,before,after", MUST_ALLOW, ids=[row[0] for row in MUST_ALLOW])
def test_must_allow(case, before, after):
    ok, why = cb.claim_numbers_only(before, after, PATH)

    assert ok is True, (case, why)


def test_identical_is_allowed_as_unchanged():
    assert cb.claim_numbers_only(BUDGETS, BUDGETS, PATH) == (True, "unchanged")


@pytest.mark.parametrize("before,after", [(None, ""), (object(), "x")])
def test_never_raises(before, after):
    assert cb.claim_numbers_only(before, after, PATH) == (False, "could not tell")


def test_the_marker_binds_the_first_matching_line_in_its_window():
    assert cb.bound_lines(LINES) == {9: 10}


def test_claim_grammar_matches_check_marketplace():
    if not os.path.isfile(CHECKER):
        pytest.skip("scripts/check-marketplace.py is absent (an installed plugin copy); "
                    "the lockstep was NOT checked")
    spec = importlib.util.spec_from_file_location("check_marketplace_lockstep", CHECKER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    theirs = (module.CLAIM_RE.pattern, module.CODE_SPAN_RE.pattern,
              module.MARKDOWN_LINES_RE.pattern, module.BIND_WINDOW)
    ours = (cb.CLAIM_RE.pattern, cb.CODE_SPAN_RE.pattern,
            cb.MARKDOWN_LINES_RE.pattern, cb.BIND_WINDOW)

    assert ours == theirs

"""`/crew:review` bundles from the ticket's START, not the default-branch
merge-base.

Codex FIX (`plugin/crew/commands/review.md:124`): the bundle base was
`git merge-base HEAD "$DEFAULT_BRANCH"`, so on a branch carrying more than
this ticket the reviewer read -- and the receipt bound -- everything since the
trunk, not the ticket's change. `scope_base.py` already records where a ticket
started (`/crew:work` step 1) and falls back to the merge-base itself, naming
the fallback. These are prompt-text assertions, the same shape as
`test_review_fallback_bundle.py`: a command file is not executable, so what can
regress mechanically is the instruction going missing.
"""
import pathlib
import re

import context  # noqa: F401  pylint: disable=unused-import

PLUGIN = pathlib.Path(__file__).resolve().parents[1]


def _step_1a():
    body = (PLUGIN / "commands" / "review.md").read_text(encoding="utf-8")
    start = body.index("**Step 1a")
    return body[start:body.index("```", body.index("```bash", start) + 7)]


def _base_assignments(section):
    return [m.group(0) for m in re.finditer(r"^\s*BASE=.*$", section, re.M)]


def test_review_base_comes_from_scope_base_first():
    first = _base_assignments(_step_1a())[0]

    assert "scope_base.py --root . --base \"$TICKET\"" in first


def test_review_merge_base_is_only_a_stated_fallback():
    section = _step_1a()
    fallback = section[section.index('if [ -z "$BASE" ]'):]

    assert "git merge-base HEAD" in fallback and "(fallback" in fallback

"""L-0679: every MEMORY_MUTATIONS anchor is in crew_memory.py exactly once, so
an edit that moves one fails here at once instead of at a full sabotage run."""
import context  # noqa: F401  pylint: disable=unused-import
from sabotage_context import MEMORY_MUTATIONS


def test_every_memory_sabotage_anchor_is_present_exactly_once():
    for label, target, find, _replace, test in MEMORY_MUTATIONS:
        with open(target, encoding="utf-8") as handle:
            assert handle.read().count(find) == 1, label
        assert test.startswith(("tests/test_crew_memory.py::", "tests/test_crew_memory_save.py::",
                                "tests/test_crew_memory_migrate.py::")), label

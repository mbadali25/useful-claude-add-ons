"""Shared test isolation for the whole suite.

Every test that touches `crew_config` -- directly, through
`crew_state.collect`'s `cfg_override`, or through `pm_brief`'s layered brief
-- must not depend on whatever happens to be at the real, machine-global
`~/.claude/crew/config.json`. This autouse fixture points that path at
somewhere that provably does not exist, for every test, by default. A test
that specifically exercises the global layer overrides it again with its own
scratch file; `monkeypatch` allows a later `setattr` to win within the same
test and undoes everything at teardown regardless of ordering.
"""
import pytest

import context  # noqa: F401  pylint: disable=unused-import
import crew_config
import crew_state


@pytest.fixture(autouse=True)
def _no_real_global_config(tmp_path, monkeypatch):
    """Point every reader of the machine-global config at a path that does not
    exist, so no test can read or write the developer's real
    `~/.claude/crew/config.json`.

    BOTH names are patched, and that is not belt-and-braces. The path is
    canonical in `crew_state` and re-exported by `crew_config`; a module that
    reads it through `crew_state` -- `crew_upgrade` does, because it must not
    import `crew_config` -- is NOT isolated by patching `crew_config` alone.
    Patching one name silently left `crew_upgrade.global_theme_defeats_
    migration` reading the real file during the suite, which is exactly the
    "must never touch real config" rule this fixture exists to enforce.

    A monkeypatched attribute is per-name, not per-value: rebinding one module
    attribute does nothing to another module's binding of the same object.
    """
    unused = str(tmp_path / "unused-global-config.json")
    monkeypatch.setattr(crew_config, "GLOBAL_CONFIG_PATH", unused)
    monkeypatch.setattr(crew_state, "GLOBAL_CONFIG_PATH", unused)

    # Same rule, second environment channel. `pm_brief.main` resolves its root
    # as `payload["cwd"] or $CLAUDE_PROJECT_DIR or os.getcwd()`, so a test that
    # pins the fallback with `monkeypatch.chdir(tmp_path)` pins only the THIRD
    # rung -- the environment variable sits above it and wins. Claude Code sets
    # that variable to the repo you have open; CI does not set it at all.
    #
    # So `test_main_exits_zero_on_garbage_stdin` asserted "garbage in, nothing
    # out" and got it in CI while, under Claude Code with a crew repo open, the
    # same call produced a full 669-character brief. Green where nobody looks,
    # red on the maintainer's machine -- the mirror image of the bug its own
    # comment says the chdir pin was added to fix.
    #
    # Cleared for every test by default. A test that wants the variable sets it
    # afterwards (`monkeypatch.setenv`, or an explicit `env=` for a subprocess)
    # and that still wins; this only removes the ambient value nobody declared.
    monkeypatch.delenv("CLAUDE_PROJECT_DIR", raising=False)


# --- the `slow` marker: the full per-shell hook matrix ------------------------
#
# A conftest hook rather than `addopts = -m "not slow"`: this repo has no
# pytest ini, and one at the root would reach every suite CI collects in the
# same process (gizmoduck, the skills), while a `-m` given on the command line
# REPLACES an addopts `-m` rather than combining with it. The hook touches only
# items that carry the marker, and only crew's tests carry it.
#
#   pytest plugin/crew/tests               the slow set is deselected
#   pytest plugin/crew/tests -m slow       only the slow set
#   pytest plugin/crew/tests --run-slow    everything
#
# `-n auto` (pytest-xdist: optional, not a dependency) works with all three.


def pytest_addoption(parser):
    parser.addoption(
        "--run-slow", action="store_true", default=False,
        help="crew: also run tests marked `slow` (the full bash/pwsh hook "
             "matrix). `-m slow` runs only those.")


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "slow: the full bash/pwsh driver matrix for a hook; deselected by "
        "default, run with -m slow or --run-slow")


def pytest_collection_modifyitems(config, items):
    """Deselect `slow` unless asked for, by `--run-slow` or by any `-m`
    expression naming it -- so `-m slow` and `-m "slow and not pwsh"` both
    select from the full set rather than from an already-emptied one."""
    if config.getoption("--run-slow") or "slow" in (config.option.markexpr or ""):
        return
    keep, drop = [], []
    for item in items:
        (drop if item.get_closest_marker("slow") else keep).append(item)
    if drop:
        config.hook.pytest_deselected(items=drop)
        items[:] = keep

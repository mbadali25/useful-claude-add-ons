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

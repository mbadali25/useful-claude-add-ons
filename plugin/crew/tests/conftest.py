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


@pytest.fixture(autouse=True)
def _no_real_global_config(tmp_path, monkeypatch):
    monkeypatch.setattr(
        crew_config, "GLOBAL_CONFIG_PATH",
        str(tmp_path / "unused-global-config.json"),
    )

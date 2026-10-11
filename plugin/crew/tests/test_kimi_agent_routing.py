"""The security family block and the agent role kinds (L-0777).

`security` reviews code, so `crew_state.resolve_role` bars a pin that speaks
as the family which wrote the diff, exactly as it does for every `qa` role. A
writer role never is: the guard governs who may judge a diff, not who may
write one.
"""
import pytest

import context  # noqa: F401  pylint: disable=unused-import
import crew_config
import crew_fixtures
import crew_state

KIMI = {"provider": "kimi", "model": "k3"}


def _cfg(**roles):
    return {"dev": {"provider": "claude", "roles": roles}}


def test_security_on_kimi_is_barred_on_kimi_authored_work():
    row = crew_state.resolve_role(_cfg(security=KIMI), "dev", "security", author="kimi")

    assert (row["barred"], row["barredBy"]) == (True, "kimi")


@pytest.mark.parametrize("author", ["claude", "gpt", None])
def test_security_on_kimi_runs_on_other_families_work(author):
    row = crew_state.resolve_role(_cfg(security=KIMI), "dev", "security", author=author)

    assert not row["barred"] and row["provider"] == "kimi"


@pytest.mark.parametrize("role", ["developer", "explorer", "researcher"])
def test_a_role_that_does_not_review_is_never_barred_by_author(role):
    row = crew_state.resolve_role(_cfg(**{role: KIMI}), "dev", role, author="kimi")

    assert not row["barred"]


def test_only_security_reviews_among_the_dev_roles():
    assert crew_state.REVIEWING_DEV_ROLES == ("security",)
    assert set(crew_state.REVIEWING_DEV_ROLES) <= set(crew_state.DEV_ROLE_KINDS)


def test_the_model_report_lists_the_agent_roles_and_bars_security(tmp_path):
    cfg = _cfg(security=KIMI, explorer=KIMI, researcher=KIMI)
    root = crew_fixtures.make_repo(tmp_path, config=cfg, git=False)
    crew_state.record_dispatch(str(root), "dev", "developer", "kimi", "k3")

    report = crew_config.model_report(str(root), which=lambda _name: None)

    rows = {r["role"]: r for r in report["dev"]}
    assert {"explorer", "researcher", "security"} <= set(rows)
    assert rows["security"]["barred"]
    assert not rows["explorer"]["barred"] and not rows["researcher"]["barred"]

"""Tests for codemap/graph reconciliation and the v1 -> v2 upgrade."""
import context  # noqa: F401  pylint: disable=unused-import
import graph_reconcile

V1_MAP = """# auth
anchor: repo@0000000
verified: 2026-01-01

## Does
Authenticates requests.

## Entry points
- `src/auth.py:10` — called by the router

## Calls out to
- billing at `src/auth.py:99`

## Landmines
- The session cache is not invalidated on password change.

## Unverified
- Whether the legacy path is still reachable.
"""


def test_split_sections_finds_every_heading():
    got = graph_reconcile.split_sections(V1_MAP)
    assert set(got) >= {"Does", "Entry points", "Calls out to",
                        "Landmines", "Unverified"}


def test_landmines_survive_byte_identical():
    out = graph_reconcile.reconcile(V1_MAP, {"Entry points": ["- `x.py:1` — new"]})
    assert "The session cache is not invalidated on password change." in out["body"]


def test_does_section_survives():
    out = graph_reconcile.reconcile(V1_MAP, {"Entry points": []})
    assert "Authenticates requests." in out["body"]


def test_derived_facts_are_added():
    out = graph_reconcile.reconcile(
        V1_MAP, {"Entry points": ["- `src/cli.py:7` — called by the CLI"]}
    )
    assert "src/cli.py:7" in out["body"]
    assert "Entry points" in out["touched"]


def test_a_line_number_shift_is_not_a_conflict():
    """The noise case. The map says src/auth.py:10, the graph says :44 --
    same file, moved line. Reporting that as a contradiction would make
    UPGRADE.md mostly line-drift noise on any repo that has been refactored,
    and a report nobody reads protects nothing.
    """
    out = graph_reconcile.reconcile(
        V1_MAP, {"Entry points": ["- `src/auth.py:44` — called by the cron"]}
    )
    assert out["conflicts"] == []
    assert "src/auth.py:10" in out["body"]   # the human's note is still there
    assert out["added"] == []                # and the graph added nothing new


def test_a_file_the_graph_does_not_know_is_a_conflict():
    # billing.py is claimed by the map and absent from the graph entirely.
    out = graph_reconcile.reconcile(
        V1_MAP, {"Calls out to": ["- payments at `src/pay.py:3`"]}
    )
    assert "src/billing.py" not in V1_MAP  # guard: the fixture says `src/auth.py:99`
    assert any("auth.py" in c for c in out["conflicts"])
    assert "src/auth.py:99" in out["body"]  # kept regardless


def test_a_new_file_from_the_graph_is_added():
    out = graph_reconcile.reconcile(
        V1_MAP, {"Entry points": ["- `src/cron.py:1` — called by the scheduler"]}
    )
    assert "src/cron.py:1" in out["body"]
    assert out["added"]
    assert "Entry points" in out["touched"]


def test_a_keep_section_is_never_touched_even_if_derived_is_supplied():
    out = graph_reconcile.reconcile(
        V1_MAP, {"Landmines": ["- graph says something"]}
    )
    assert "graph says something" not in out["body"]
    assert "Landmines" not in out["touched"]


def test_untouched_sections_are_not_in_touched():
    out = graph_reconcile.reconcile(V1_MAP, {"Entry points": []})
    assert "Calls out to" not in out["touched"]


def test_reconcile_is_idempotent():
    derived = {"Entry points": ["- `src/cli.py:7` — called by the CLI"]}
    once = graph_reconcile.reconcile(V1_MAP, derived)
    assert once["added"], "first pass must actually add something"
    twice = graph_reconcile.reconcile(once["body"], derived)
    assert twice["body"] == once["body"]
    assert twice["added"] == []

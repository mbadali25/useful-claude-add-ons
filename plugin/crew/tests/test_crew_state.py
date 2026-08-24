"""Tests for the crew state reader."""
import context  # noqa: F401  pylint: disable=unused-import
import crew_fixtures
import crew_state


def test_missing_config_is_empty_dict(tmp_path):
    root = crew_fixtures.make_repo(tmp_path)
    assert crew_state.load_config(str(root)) == {}


def test_malformed_config_is_empty_dict_not_an_exception(tmp_path):
    root = crew_fixtures.make_repo(tmp_path)
    (root / ".crew" / "config.json").write_text("{not json", encoding="utf-8")
    assert crew_state.load_config(str(root)) == {}


def test_config_list_at_top_level_is_rejected(tmp_path):
    root = crew_fixtures.make_repo(tmp_path)
    (root / ".crew" / "config.json").write_text("[1, 2]", encoding="utf-8")
    assert crew_state.load_config(str(root)) == {}


def test_metrics_rate_is_findings_over_tickets(tmp_path):
    root = crew_fixtures.make_repo(
        tmp_path, metrics=[("T-1", 1, 0), ("T-2", 0, 1), ("T-3", 1, 1)]
    )
    got = crew_state.read_metrics(str(root))
    assert got["tickets"] == 3
    assert got["findings"] == 4
    assert got["rate"] == 1.33
    assert got["verdict"] == "healthy"


def test_metrics_header_and_separator_rows_are_skipped(tmp_path):
    # make_repo always writes both; a rate of 0.0 would mean they were counted.
    root = crew_fixtures.make_repo(tmp_path, metrics=[("T-1", 2, 0)])
    assert crew_state.read_metrics(str(root))["tickets"] == 1


def test_metrics_window_keeps_only_the_last_n(tmp_path):
    rows = [(f"T-{i}", 5, 5) for i in range(12)] + [("T-last", 0, 0)]
    root = crew_fixtures.make_repo(tmp_path, metrics=rows)
    got = crew_state.read_metrics(str(root), window=2)
    assert got["tickets"] == 2
    assert got["findings"] == 10  # one 5+5 row and one 0+0 row


def test_low_rate_reports_review_not_catching(tmp_path):
    rows = [(f"T-{i}", 0, 0) for i in range(10)]
    root = crew_fixtures.make_repo(tmp_path, metrics=rows)
    assert crew_state.read_metrics(str(root))["verdict"] == (
        "review not catching defects"
    )


def test_high_rate_reports_tickets_too_large(tmp_path):
    rows = [(f"T-{i}", 3, 2) for i in range(10)]
    root = crew_fixtures.make_repo(tmp_path, metrics=rows)
    assert crew_state.read_metrics(str(root))["verdict"] == "tickets too large"


def test_absent_metrics_is_no_data_not_zero(tmp_path):
    # A repo that has run no reviews must not read as a broken review.
    root = crew_fixtures.make_repo(tmp_path)
    got = crew_state.read_metrics(str(root))
    assert got["rate"] is None
    assert got["verdict"] == "no data"


def test_work_reads_ticket_and_handoff(tmp_path):
    root = crew_fixtures.make_repo(tmp_path, work_ticket="T-0042", handoff=True)
    got = crew_state.read_work(str(root))
    assert got["ticket"] == "T-0042"
    assert got["handoffPending"] is True


def test_work_absent_is_none_and_false(tmp_path):
    root = crew_fixtures.make_repo(tmp_path)
    got = crew_state.read_work(str(root))
    assert got["ticket"] is None
    assert got["handoffPending"] is False


def test_work_skips_finished_tickets_above_the_open_one(tmp_path):
    """A real INDEX.md accumulates. Taking the first match names a closed
    ticket, in the brief, as fact, on every session.
    """
    root = crew_fixtures.make_repo(tmp_path)
    (root / ".work" / "INDEX.md").write_text(
        "# Work\n\n"
        "- [x] T-0001 — done\n"
        "- ~~T-0002~~ merged\n"
        "- T-0003 — in progress\n"
        "- T-0004 — queued\n",
        encoding="utf-8",
    )
    assert crew_state.read_work(str(root))["ticket"] == "T-0003"


def test_a_done_word_in_the_description_does_not_mark_it_finished(tmp_path):
    """A status marker is positional, not lexical. `merged` inside a
    description is what the work is about, not whether it is over.
    """
    root = crew_fixtures.make_repo(tmp_path)
    (root / ".work" / "INDEX.md").write_text(
        "# Work\n\n"
        "- [x] T-0001 — done\n"
        "- T-0002 — clean up after the merged branch\n",
        encoding="utf-8",
    )
    assert crew_state.read_work(str(root))["ticket"] == "T-0002"


def test_a_leading_status_word_does_mark_it_finished(tmp_path):
    root = crew_fixtures.make_repo(tmp_path)
    (root / ".work" / "INDEX.md").write_text(
        "# Work\n\n"
        "- done: T-0001 shipped last week\n"
        "- T-0002 — in progress\n",
        encoding="utf-8",
    )
    assert crew_state.read_work(str(root))["ticket"] == "T-0002"


def test_work_with_every_ticket_done_reports_none(tmp_path):
    # "no ticket open" is true; naming a closed ticket is not.
    root = crew_fixtures.make_repo(tmp_path)
    (root / ".work" / "INDEX.md").write_text(
        "# Work\n\n- [x] T-0001 — done\n- [x] T-0002 — closed\n",
        encoding="utf-8",
    )
    assert crew_state.read_work(str(root))["ticket"] is None


CODEMAP_BODY = """# auth
anchor: repo@{sha}
verified: 2026-08-01

## Does
Authenticates.

## Landmines
- Do not touch the session cache.
"""


def test_anchor_matching_head_is_not_behind(tmp_path):
    root = crew_fixtures.make_repo(tmp_path, codemap={"auth": "placeholder"})
    sha = crew_fixtures.head_sha(root)
    (root / ".crew" / "codemap" / "auth.md").write_text(
        CODEMAP_BODY.format(sha=sha), encoding="utf-8"
    )
    got = crew_state.read_knowledge(str(root), {})
    assert got["subsystems"] == 1
    assert got["behind"] == []


def test_anchor_behind_head_is_reported(tmp_path):
    root = crew_fixtures.make_repo(
        tmp_path, codemap={"auth": CODEMAP_BODY.format(sha="0000000")}
    )
    assert crew_state.read_knowledge(str(root), {})["behind"] == ["auth"]


def test_missing_anchor_counts_as_behind(tmp_path):
    root = crew_fixtures.make_repo(tmp_path, codemap={"auth": "# auth\nno anchor\n"})
    assert crew_state.read_knowledge(str(root), {})["behind"] == ["auth"]


def test_index_and_upgrade_reports_are_not_subsystems(tmp_path):
    root = crew_fixtures.make_repo(
        tmp_path,
        codemap={"INDEX": "# index\n", "UPGRADE": "# report\n",
                 "auth": CODEMAP_BODY.format(sha="0000000")},
    )
    assert crew_state.read_knowledge(str(root), {})["subsystems"] == 1


def test_absent_graph_is_not_present(tmp_path):
    root = crew_fixtures.make_repo(tmp_path)
    got = crew_state.read_knowledge(str(root), {})["graph"]
    assert got["present"] is False
    assert got["current"] is False


def test_graph_built_at_head_is_current(tmp_path):
    root = crew_fixtures.make_repo(tmp_path, graph=True, graph_sha="head")
    assert crew_state.read_knowledge(str(root), {})["graph"]["current"] is True


def test_graph_built_at_another_sha_is_not_current(tmp_path):
    root = crew_fixtures.make_repo(tmp_path, graph=True, graph_sha="0000000")
    assert crew_state.read_knowledge(str(root), {})["graph"]["current"] is False


def test_graph_with_no_sidecar_is_not_current(tmp_path):
    # Built outside crew, so its provenance is unknown. Unknown resolves to
    # stale: claiming freshness we cannot prove is the failure mode.
    root = crew_fixtures.make_repo(tmp_path, graph=True, graph_sha=None)
    got = crew_state.read_knowledge(str(root), {})["graph"]
    assert got["present"] is True
    assert got["current"] is False
    assert got["builtAt"] is None


def test_a_pull_of_older_commits_makes_the_graph_stale(tmp_path):
    """The regression a timestamp comparison gets wrong.

    `git pull` brings in commits authored before the graph was built, so any
    mtime-vs-commit-time check reports the graph current while it knows
    nothing about the pulled code.
    """
    root = crew_fixtures.make_repo(tmp_path, graph=True, graph_sha="head")
    assert crew_state.read_knowledge(str(root), {})["graph"]["current"] is True

    # A new commit backdated well before the graph was written.
    (root / "pulled.py").write_text("# from upstream\n", encoding="utf-8")
    crew_fixtures.commit_with_date(root, "pulled.py", "2020-01-01T00:00:00")

    got = crew_state.read_knowledge(str(root), {})["graph"]
    assert got["current"] is False, "backdated commit must invalidate the graph"


def test_graph_out_dir_comes_from_config(tmp_path):
    root = crew_fixtures.make_repo(tmp_path)
    (root / "custom-out").mkdir()
    (root / "custom-out" / "graph.json").write_text("{}", encoding="utf-8")
    cfg = {"graph": {"out": "custom-out"}}
    assert crew_state.read_knowledge(str(root), cfg)["graph"]["present"] is True


def test_knowledge_survives_a_non_git_directory(tmp_path):
    root = crew_fixtures.make_repo(
        tmp_path, codemap={"auth": CODEMAP_BODY.format(sha="0000000")},
        git=False,
    )
    got = crew_state.read_knowledge(str(root), {})
    assert got["subsystems"] == 1  # no crash, and no false freshness claim

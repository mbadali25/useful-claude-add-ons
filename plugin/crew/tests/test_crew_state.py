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


def test_bom_prefixed_config_still_parses(tmp_path):
    # Windows Notepad's default save. A BOM-prefixed file is otherwise valid
    # utf-8; treating it as malformed would make json.loads see a stray
    # U+FEFF and reject an otherwise well-formed config.
    root = crew_fixtures.make_repo(tmp_path)
    (root / ".crew" / "config.json").write_text(
        '{"tier": 2}', encoding="utf-8-sig"
    )
    assert crew_state.load_config(str(root)) == {"tier": 2}


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


def test_work_recognises_an_sdp_local_key(tmp_path):
    """`tracker: "sdp"` keys tickets `SDP-<request id>` rather than by the bare
    integer the desk returns, precisely so the rest of crew can see them: a
    ticket is recognised by its LETTERS-digits shape, and `40219` matches
    nothing. If this ever fails, the session brief silently reports "no ticket
    open" for every ServiceDesk Plus repo.
    """
    root = crew_fixtures.make_repo(tmp_path, work_ticket="SDP-40219")
    assert crew_state.read_work(str(root))["ticket"] == "SDP-40219"


def test_work_ignores_a_bare_request_number(tmp_path):
    # The other half of the same claim, so the convention is pinned rather than
    # assumed: a bare desk id in the index is invisible, which is why
    # /crew:sdp-sync rewrites it.
    root = crew_fixtures.make_repo(tmp_path)
    (root / ".work" / "INDEX.md").write_text(
        "# Work\n\n- 40219 - in progress\n", encoding="utf-8")
    assert crew_state.read_work(str(root))["ticket"] is None


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


def test_capitalised_status_keywords_are_recognised(tmp_path):
    """re.IGNORECASE is load-bearing; dropping it once already shipped a bug.

    A status keyword is written however the author felt at the time. If this
    test fails, someone removed the flag and finished tickets are being read
    as open.
    """
    for index, marker in enumerate(("DONE:", "Done:", "Shipped:", "CLOSED:", "Merged:")):
        root = crew_fixtures.make_repo(tmp_path / f"case{index}")
        lines = ["# Work", "", f"- {marker} T-0001", "- T-0002 in progress", ""]
        (root / ".work" / "INDEX.md").write_text(
            chr(10).join(lines), encoding="utf-8"
        )
        got = crew_state.read_work(str(root))["ticket"]
        assert got == "T-0002", f"{marker} was not treated as a done marker"


def test_a_leading_status_word_without_a_colon_is_still_open(tmp_path):
    """The three shapes that defeated the position-anchored version.

    Each leads with a status word and is open work, so a rule based on
    position reports "no ticket open" while a ticket is.
    """
    cases = (
        ("- Complete the T-5 setup", "T-5"),
        ("- Closed captions for T-7 need review", "T-7"),
        ("- Merged conflicts remain in T-8", "T-8"),
    )
    for index, (line, want) in enumerate(cases):
        root = crew_fixtures.make_repo(tmp_path / f"case{index}")
        body = "# Work" + chr(10) + chr(10) + line + chr(10)
        (root / ".work" / "INDEX.md").write_text(body, encoding="utf-8")
        assert crew_state.read_work(str(root))["ticket"] == want, line


def test_numbered_list_checkbox_is_recognised_as_done(tmp_path):
    """A numbered bullet did not match the old bullet class, so a finished
    ticket read as open.
    """
    root = crew_fixtures.make_repo(tmp_path)
    lines = ["# Work", "", "1. [x] T-0001 done", "2. T-0002 in progress", ""]
    (root / ".work" / "INDEX.md").write_text(
        chr(10).join(lines), encoding="utf-8"
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
    # not "not got['behind']": that also passes for None, which is not what
    # this test checks.
    assert got["behind"] == []  # pylint: disable=use-implicit-booleaness-not-comparison


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


def _state(**over):
    base = {
        "schema": 2,
        "health": {"rate": 1.0, "verdict": "healthy"},
        "work": {"ticket": None, "handoffPending": False},
        "knowledge": {"subsystems": 0, "behind": [],
                      "graph": {"present": True, "current": True}},
    }
    base.update(over)
    return base


def test_healthy_state_fires_no_triggers():
    assert crew_state.evaluate_triggers(_state()) == []


def test_v1_schema_fires_upgrade_needed():
    assert "upgradeNeeded" in crew_state.evaluate_triggers(_state(schema=1))


def test_absent_graph_fires_graph_stale():
    got = crew_state.evaluate_triggers(
        _state(knowledge={"subsystems": 0, "behind": [],
                          "graph": {"present": False, "current": False}})
    )
    assert "graphStale" in got


def test_behind_anchors_fire_knowledge_behind():
    got = crew_state.evaluate_triggers(
        _state(knowledge={"subsystems": 2, "behind": ["auth"],
                          "graph": {"present": True, "current": True}})
    )
    assert "knowledgeBehind" in got


def test_low_rate_fires_review_not_working():
    got = crew_state.evaluate_triggers(
        _state(health={"rate": 0.1, "verdict": "review not catching defects"})
    )
    assert "reviewNotWorking" in got


def test_no_data_does_not_fire_review_not_working():
    # A fresh repo has run no reviews. That is not a broken review.
    got = crew_state.evaluate_triggers(
        _state(health={"rate": None, "verdict": "no data"})
    )
    assert "reviewNotWorking" not in got


def test_high_rate_fires_tickets_too_large():
    got = crew_state.evaluate_triggers(
        _state(health={"rate": 3.0, "verdict": "tickets too large"})
    )
    assert "ticketsTooLarge" in got


def test_pending_handoff_fires():
    got = crew_state.evaluate_triggers(
        _state(work={"ticket": "T-1", "handoffPending": True})
    )
    assert "handoffPending" in got


def test_triggers_come_back_in_priority_order():
    got = crew_state.evaluate_triggers(
        _state(schema=1, work={"ticket": None, "handoffPending": True},
               health={"rate": 0.0, "verdict": "review not catching defects"})
    )
    assert got == ["upgradeNeeded", "handoffPending", "reviewNotWorking"]


def test_a_hand_edited_schema_does_not_crash_collect(tmp_path):
    """The crash that would break every session opened in the repo.

    .get(key, default) substitutes the default only when the KEY IS ABSENT, so
    a present `"schema": null` returns None and `None < 2` raises TypeError.
    """
    for bad in (None, "two", [], {}, True):
        root = crew_fixtures.make_repo(tmp_path / f"s{abs(hash(str(bad))) % 9999}",
                                      config={"schema": bad, "tier": 0})
        got = crew_state.collect(str(root))
        assert isinstance(got["schema"], int), bad
        assert isinstance(got["triggers"], list), bad


def test_a_hand_edited_graph_block_does_not_crash_collect(tmp_path):
    """The same failure as the schema Critical, reached through shape.

    `(cfg.get("graph") or {})` guards a missing or falsy value but passes a
    wrong-typed truthy one through to .get(), which raises AttributeError on a
    str/int/list -- and from a SessionStart hook that breaks every session.
    """
    for index, bad in enumerate(("oops", 123, ["a"], True, 3.5, {"out": 7})):
        root = crew_fixtures.make_repo(
            tmp_path / f"graph{index}", config={"schema": 2, "graph": bad}
        )
        got = crew_state.collect(str(root))
        assert isinstance(got["knowledge"]["graph"], dict), bad
        assert isinstance(got["triggers"], list), bad


def test_dict_or_empty_rejects_non_dicts():
    for value in ("s", 1, [], (), True, None, 0, 3.5, set()):
        assert crew_state.dict_or_empty(value) == {}
    assert crew_state.dict_or_empty({"a": 1}) == {"a": 1}


def test_a_numeric_string_schema_is_read_as_a_number(tmp_path):
    root = crew_fixtures.make_repo(tmp_path, config={"schema": "2"})
    assert crew_state.collect(str(root))["schema"] == 2
    assert "upgradeNeeded" not in crew_state.collect(str(root))["triggers"]


def test_hand_edited_pm_line_counts_do_not_crash(tmp_path):
    # Task 6 does int(pm["quietLines"]); an unvalidated "eight" would raise
    # there instead, and silently swallow the whole brief.
    root = crew_fixtures.make_repo(
        tmp_path, config={"schema": 2, "pm": {"quietLines": "eight",
                                              "maxLines": None}}
    )
    pm = crew_state.collect(str(root))["pm"]
    assert pm["quietLines"] == 8
    assert pm["maxLines"] == 40


def test_hand_edited_tier_and_roles_are_normalised(tmp_path):
    root = crew_fixtures.make_repo(
        tmp_path, config={"schema": 2, "tier": {}, "roles": "explorer"}
    )
    got = crew_state.collect(str(root))
    assert got["tier"] is None
    assert got["roles"] == []


def test_a_non_crew_directory_reports_no_triggers(tmp_path):
    """A directory with no crew has no findings.

    Without the isCrew gate every plain git repo reports graphStale, and
    /crew:pm calls collect() directly with no gate of its own.
    """
    plain = tmp_path / "plain"
    plain.mkdir()
    got = crew_state.collect(str(plain))
    assert got["isCrew"] is False
    assert got["triggers"] == []


def test_collect_on_a_non_crew_directory_is_not_crew(tmp_path):
    root = tmp_path / "plain"
    root.mkdir()
    assert crew_state.collect(str(root))["isCrew"] is False


def test_collect_defaults_schema_to_one_when_absent(tmp_path):
    root = crew_fixtures.make_repo(tmp_path, config={"tier": 0, "roles": []})
    assert crew_state.collect(str(root))["schema"] == 1


def test_collect_reads_pm_block_defaults(tmp_path):
    root = crew_fixtures.make_repo(tmp_path, config={"schema": 2})
    pm = crew_state.collect(str(root))["pm"]
    assert pm["enabled"] is True
    assert pm["mode"] == "adaptive"
    assert pm["quietLines"] == 8
    assert pm["maxLines"] == 40

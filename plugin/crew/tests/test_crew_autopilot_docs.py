"""T-0022 step 3: autopilot's docs phase.

    python3 -m pytest plugin/crew/tests/test_crew_autopilot_docs.py -q

`crew_autopilot.next_phase` runs `/crew:docs <id>` before the refresh and
every review round while `crew_docs_check` reports a document owed, stops
after two recorded runs, reads the check's `unknown` as owed, and stops
without writing when a document is owed after an accepted receipt. Every
repository is under tmp_path.
"""
import json
import os

import context  # noqa: F401  pylint: disable=unused-import
import crew_autopilot
import crew_docs_check
import scope_base
from review_fixtures import git
from test_crew_autopilot import (T, _approved, _ledger, _receipt, _receipt_ok, _refresh,
                                 _round, _snapshot)


def _docs(monkeypatch, status, *missing, reason="scope base abc (recorded)"):
    rows = [{"doc": doc, "verdict": "MISSING", "reason": "owed"} for doc in missing]
    monkeypatch.setattr(crew_docs_check, "ticket_docs", lambda root, ticket: {
        "status": status, "reason": reason, "documents": rows,
        "not_measured": ["adr", "runbooks"], "base_source": "record"})


def _before_review(tmp_path, monkeypatch, refresh="stale"):
    root = _approved(tmp_path)
    _ledger(root, [_round(1, "CLEAN")], state="ACCEPTED", receipt=_receipt(1))
    _receipt_ok(monkeypatch, False)
    _refresh(monkeypatch, refresh, command="graphify update .")
    return root


def _next(root, **kwargs):
    return crew_autopilot.next_phase(str(root), T, **kwargs)


def test_next_docs_before_refresh(tmp_path, monkeypatch):
    root = _before_review(tmp_path, monkeypatch)
    _docs(monkeypatch, "missing", "CHANGELOG.md (crew 1.0.1)")

    got = _next(root)

    assert (got["phase"], got["stop"], got["command"]) == ("docs", False, f"/crew:docs {T}")
    assert "CHANGELOG.md (crew 1.0.1)" in got["reason"]


def test_next_docs_ok_goes_on_to_refresh(tmp_path, monkeypatch):
    root = _before_review(tmp_path, monkeypatch)
    _docs(monkeypatch, "ok")

    assert _next(root)["phase"] == "refresh"


def test_next_docs_unknown_stops_at_once(tmp_path, monkeypatch):
    root = _before_review(tmp_path, monkeypatch, refresh="fresh")
    _docs(monkeypatch, "unknown", reason="no scope base for T-1 (none recorded)")

    got = _next(root)

    assert (got["phase"], got["stop"], got["command"]) == ("docs-unknown", True, "")
    assert "no scope base" in got["reason"] and "cannot settle" in got["reason"]


def test_next_docs_unknown_never_reruns_docs(tmp_path, monkeypatch):
    """No recorded attempt, and none would help: the first answer is the stop."""
    root = _before_review(tmp_path, monkeypatch, refresh="stale")
    _docs(monkeypatch, "unknown", reason="git could not read TODO.md at abc")
    record = os.path.join(str(root), ".work", "tickets", T, crew_autopilot.DOCS_RECORD)

    got = _next(root, phases_run=0, max_phases=12)

    assert (got["phase"], got["stop"], os.path.exists(record)) == ("docs-unknown", True, False)


def test_next_docs_check_that_raises_stops(tmp_path, monkeypatch):
    root = _before_review(tmp_path, monkeypatch, refresh="fresh")

    def boom(root, ticket):
        raise RuntimeError("git vanished")
    monkeypatch.setattr(crew_docs_check, "ticket_docs", boom)

    got = _next(root)

    assert (got["phase"], got["stop"], "git vanished" in got["reason"]) == (
        "docs-unknown", True, True)


def test_next_docs_two_attempts_then_stop(tmp_path, monkeypatch):
    root = _before_review(tmp_path, monkeypatch)
    _docs(monkeypatch, "missing", "SECURITY.md")
    command = f"/crew:docs {T}"

    first = _next(root, phases_run=0, max_phases=12)
    crew_autopilot.record_docs_attempt(str(root), T)
    second = _next(root, phases_run=1, last_command=command, max_phases=12)
    crew_autopilot.record_docs_attempt(str(root), T)
    third = _next(root, phases_run=2, last_command=command, max_phases=12)

    assert [(r["phase"], r["stop"]) for r in (first, second, third)] == [
        ("docs", False), ("docs", False), ("docs", True)]
    assert "still MISSING after 2" in third["reason"] and "SECURITY.md" in third["reason"]


def test_next_docs_rerun_without_a_recorded_attempt_is_no_progress(tmp_path, monkeypatch):
    root = _before_review(tmp_path, monkeypatch)
    _docs(monkeypatch, "missing", "SECURITY.md")

    got = _next(root, phases_run=1, last_command=f"/crew:docs {T}", max_phases=12)

    assert (got["stop"], got["reason"].startswith("no progress")) == (True, True)


def test_docs_attempts_count_since_the_latest_review_round(tmp_path, monkeypatch):
    root = _before_review(tmp_path, monkeypatch)
    _docs(monkeypatch, "missing", "SECURITY.md")
    record = os.path.join(str(root), ".work", "tickets", T, crew_autopilot.DOCS_RECORD)
    with open(record, "w", encoding="utf-8") as handle:
        json.dump({"attempts": [{"round": 0}, {"round": 0}]}, handle)

    assert _next(root)["stop"] is False


def test_docs_record_unreadable_reads_spent(tmp_path, monkeypatch):
    root = _before_review(tmp_path, monkeypatch)
    _docs(monkeypatch, "missing", "SECURITY.md")
    record = os.path.join(str(root), ".work", "tickets", T, crew_autopilot.DOCS_RECORD)
    with open(record, "w", encoding="utf-8") as handle:
        handle.write("{torn")

    got = _next(root)

    assert (got["phase"], got["stop"]) == ("docs", True)
    try:
        crew_autopilot.record_docs_attempt(str(root), T)
        raised = False
    except RuntimeError:
        raised = True
    with open(record, encoding="utf-8") as handle:
        assert (raised, handle.read()) == (True, "{torn")


def test_next_docs_after_review_stops_without_writing(tmp_path, monkeypatch):
    root = _approved(tmp_path)
    _ledger(root, [_round(1, "CLEAN")], state="ACCEPTED", receipt=_receipt(1))
    _receipt_ok(monkeypatch, True)
    _refresh(monkeypatch, "fresh")
    _docs(monkeypatch, "missing", "TODO.md")
    before = _snapshot(root)

    got = _next(root)

    assert ((got["phase"], got["stop"], got["command"]), _snapshot(root) == before) == (
        ("docs-after-review", True, ""), True)
    assert "stales the receipt" in got["reason"] and "TODO.md" in got["reason"]


def test_next_done_when_documents_ok_after_review(tmp_path, monkeypatch):
    root = _approved(tmp_path)
    _ledger(root, [_round(1, "CLEAN")], state="ACCEPTED", receipt=_receipt(1))
    _receipt_ok(monkeypatch, True)
    _refresh(monkeypatch, "fresh")
    _docs(monkeypatch, "ok")

    assert _next(root)["phase"] == "done"


def test_docs_stops_are_listed():
    ids = [slug for slug, _text in crew_autopilot.FIXED_STOPS]
    assert {"docs-missing", "docs-unknown", "docs-after-review", "tracker-failed",
            "tracker-unavailable"} <= set(ids)


# --- integration: the real ticket_docs through next_phase (review round 1 FIX) ----
# No stub of `_docs_state` or `ticket_docs` here: a field `_docs_state` reads
# that `ticket_docs` renamed or dropped shows up as a wrong phase.

def _write(root, rel, text):
    path = os.path.join(str(root), *rel.split("/"))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)


def test_real_docs_check_drives_next_from_missing_changelog_to_review(tmp_path, monkeypatch):
    root = _approved(tmp_path)
    _write(root, ".claude-plugin/marketplace.json", json.dumps({"name": "m", "plugins": [
        {"name": "widget", "source": "./plugin/widget", "version": "0.2.0"}]}))
    _write(root, "plugin/widget/app.py", "x = 1\n")
    _write(root, "CHANGELOG.md", "# Changelog\n\n## [Unreleased]\n\n## [0.1.0]\n")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "a marketplace with one plugin")
    scope_base.record(str(root), T)
    _ledger(root, [_round(1, "CLEAN")], state="ACCEPTED", receipt=_receipt(1))
    _receipt_ok(monkeypatch, False)
    _refresh(monkeypatch, "fresh")
    _write(root, "plugin/widget/app.py", "x = 2\n")

    owed = _next(root)
    _write(root, "CHANGELOG.md", "# Changelog\n\n## [Unreleased]\n\n"
           "- `widget` 0.2.0: app counts to two\n\n## [0.1.0]\n")
    written = _next(root)

    assert (owed["phase"], owed["stop"], owed["command"]) == ("docs", False, f"/crew:docs {T}")
    assert "CHANGELOG.md (widget 0.2.0)" in owed["reason"]
    assert (written["phase"], written["stop"]) == ("review", False), written

"""T-0098: `review_ledger.py --correct-acceptance` fixes who accepted a review.

    python3 -m pytest plugin/crew/tests/test_review_correct_acceptance.py -q

A peer recorded an owner decision under its own name, and no verb could fix
`accepted_by`. The correction rewrites that one field on an `owner-accepted`
receipt and appends a row (`round`, `was`, `now`, `reason`, `at`) to the
top-level `acceptance_corrections` list. It never touches the state, the
rounds, the bundle hash, the base or `accepted_at`, so `--check-receipt`
answers the same before and after. Every refusal leaves the ledger file
byte-identical and exits 1. `sabotage_review.py` flips each guard and names
the test here that goes red. Every repository is built under tmp_path.
"""
import json
import os
import subprocess
import sys
import threading

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import review_ledger as rl
import review_patch
from review_fixtures import git, init_repo

_LEDGER = os.path.join(context._ROOT, "hooks", "scripts",  # pylint: disable=protected-access
                       "review_ledger.py")
T = "T1"
REASON = "the owner accepted this in chat; a peer ran --accept under its own name"


@pytest.fixture(name="repo")
def _repo(tmp_path):
    root = init_repo(tmp_path / "r")
    (root / "feature.txt").write_text("feature v1\n", encoding="utf-8")
    return root


def _review(repo, verdict="FINDINGS"):
    base = git(repo, "rev-parse", "HEAD")
    manifest, _, _ = review_patch.compute(str(repo), base)
    ok, number, message = rl.reserve(str(repo), T, "codex")
    assert ok, message
    rl.record(str(repo), T, number, {
        "verdict": verdict, "counts": {}, "bundle_sha256": manifest["bundle_sha256"],
        "base": base, "head": manifest["head"], "provider": "codex", "model": None,
        "model_family": "gpt"})


def _accepted(repo, by="a peer"):
    _review(repo)
    rl.accept(str(repo), T, by)


def _cli(repo, *args):
    return subprocess.run([sys.executable, _LEDGER, "--root", str(repo), "--ticket", T]
                          + list(args), capture_output=True, text=True,
                          stdin=subprocess.DEVNULL, check=False)


def _correct_cli(repo, by="the owner", reason=REASON):
    args = ["--correct-acceptance"]
    if by is not None:
        args += ["--by", by]
    if reason is not None:
        args += ["--reason", reason]
    return _cli(repo, *args)


def _path(repo):
    return rl.ledger_path(str(repo), T)


def _data(repo):
    with open(_path(repo), encoding="utf-8") as fh:
        return json.load(fh)


def _edit(repo, change):
    data = _data(repo)
    change(data)
    text = json.dumps(data)
    with open(_path(repo), "w", encoding="utf-8") as fh:
        fh.write(text)


def _bytes(repo):
    try:
        with open(_path(repo), "rb") as fh:
            return fh.read()
    except FileNotFoundError:
        return None


# --- must-allow ----------------------------------------------------------------

def test_correction_rewrites_accepted_by_and_appends_a_row(repo):
    _accepted(repo)

    result = _correct_cli(repo)

    data = _data(repo)
    assert result.returncode == 0, result.stderr
    assert data["receipt"]["accepted_by"] == "the owner"
    [row] = data["acceptance_corrections"]
    assert ({k: row[k] for k in ("round", "was", "now", "reason")}, bool(row["at"])) == (
        {"round": 1, "was": "a peer", "now": "the owner", "reason": REASON}, True)
    assert result.stdout.strip() == (
        f"review-ledger: round 1 accepted_by corrected from a peer to the owner at "
        f"{row['at']} (1 correction(s) recorded)")


def test_correction_changes_only_the_name_and_the_history(repo):
    _accepted(repo)
    # An `accepted_at` from another second, so a refreshed one cannot match
    # by landing in the same second as the acceptance.
    _edit(repo, lambda data: data["receipt"].update(accepted_at="2026-01-01T00:00:00+00:00"))
    before = _data(repo)

    rl.correct_acceptance(str(repo), T, "the owner", REASON)

    after = _data(repo)
    assert {k for k in set(before) | set(after) if before.get(k) != after.get(k)} == {
        "receipt", "acceptance_corrections"}
    assert ({k: v for k, v in after["receipt"].items() if k != "accepted_by"}
            == {k: v for k, v in before["receipt"].items() if k != "accepted_by"})
    for key in ("accepted_at", "bundle_sha256", "base", "kind", "round"):
        assert after["receipt"][key] == before["receipt"][key], key
    assert (after["state"], after["rounds"]) == (before["state"], before["rounds"])


def test_check_receipt_is_unchanged_by_a_correction(repo):
    _accepted(repo)
    assert _cli(repo, "--check-receipt").returncode == 0

    assert _correct_cli(repo).returncode == 0
    assert _cli(repo, "--check-receipt").returncode == 0

    (repo / "feature.txt").write_text("feature v2, edited after review\n", encoding="utf-8")
    assert _cli(repo, "--check-receipt").returncode == 1
    result = _correct_cli(repo, by="the owner, again")
    assert result.returncode == 0, result.stderr
    assert _cli(repo, "--check-receipt").returncode == 1


def test_second_correction_appends_and_keeps_the_first_row(repo):
    _accepted(repo)
    rl.correct_acceptance(str(repo), T, "the owner", REASON)
    first = json.dumps(_data(repo)["acceptance_corrections"][0], sort_keys=True)

    rl.correct_acceptance(str(repo), T, "the owner (Ann)", "named in full")

    rows = _data(repo)["acceptance_corrections"]
    assert len(rows) == 2
    assert json.dumps(rows[0], sort_keys=True) == first
    assert (rows[1]["was"], rows[1]["now"]) == ("the owner", "the owner (Ann)")


def test_corrections_survive_a_successor_plan(repo, monkeypatch):
    _review(repo)
    _accepted(repo)
    rl.correct_acceptance(str(repo), T, "the owner", REASON)
    assert rl.reserve(str(repo), T, "codex")[0] is False
    assert rl.status(str(repo), T)["state"] == rl.NEEDS_REPLAN
    monkeypatch.setattr(rl, "_plan_approval_receipt", lambda root, ticket, plan_hash: (
        {"approved_by": "owner", "approved_at": "now"}, None))

    assert rl.continue_with_successor_plan(str(repo), T, "b" * 64)[0] is True

    data = _data(repo)
    assert data["receipt"] is None
    assert [r["now"] for r in data["acceptance_corrections"]] == ["the owner"]


def test_status_lists_corrections(repo):
    _accepted(repo)
    assert json.loads(_cli(repo, "--status").stdout)["acceptance_corrections"] == []

    rl.correct_acceptance(str(repo), T, "the owner", REASON)

    rows = json.loads(_cli(repo, "--status").stdout)["acceptance_corrections"]
    assert [(r["was"], r["now"]) for r in rows] == [("a peer", "the owner")]


def test_corrected_round_is_still_already_accepted(repo):
    _accepted(repo)
    rl.correct_acceptance(str(repo), T, "the owner", REASON)

    with pytest.raises(rl.LedgerError, match="already accepted by the owner"):
        rl.accept(str(repo), T, "someone else")


def test_correction_usage_errors(repo):
    _accepted(repo)
    before = _bytes(repo)

    with_accept = _cli(repo, "--accept", "--by", "x", "--reason", "y")
    with_follow = _cli(repo, "--correct-acceptance", "--by", "x", "--reason", "y",
                       "--follow-up", "L-1")

    assert (with_accept.returncode, with_follow.returncode, _bytes(repo)) == (2, 2, before)


def test_concurrent_corrections_lose_no_row(repo):
    _accepted(repo)
    results = {}

    def run(name):
        results[name] = _correct_cli(repo, by=name, reason="concurrent")

    threads = [threading.Thread(target=run, args=(n,)) for n in ("owner A", "owner B")]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    rows = _data(repo)["acceptance_corrections"]
    landed = sorted(n for n, r in results.items() if r.returncode == 0)
    assert sorted(r["now"] for r in rows) == landed
    assert len(landed) >= 1
    assert rows[0]["was"] == "a peer"
    for prev, row in zip(rows, rows[1:]):
        assert row["was"] == prev["now"]
    assert _data(repo)["receipt"]["accepted_by"] == rows[-1]["now"]


# --- must-block: every refusal exits 1 and leaves the file byte-identical --------

def _set(key, value):
    def build(repo):
        _accepted(repo)
        _edit(repo, lambda data: data.__setitem__(key, value))
    return build


def _set_receipt(key, value):
    def build(repo):
        _accepted(repo)
        _edit(repo, lambda data: data["receipt"].__setitem__(key, value))
    return build


def _corrupt(repo):
    _accepted(repo)
    with open(_path(repo), "w", encoding="utf-8") as fh:
        fh.write("{not json")


def _clean(repo):
    _review(repo, "CLEAN")


def _auto_kind(repo):
    _accepted(repo)
    _edit(repo, lambda data: data["receipt"].update(kind=rl.AUTO_KIND, accepted_by=rl.AUTO_BY))


def _accepted_then_reserved(repo):
    """A new round reserved after the acceptance: the state is IN_REVIEW and
    the old receipt is still in the file, but no longer stands."""
    _accepted(repo)
    ok, _, message = rl.reserve(str(repo), T, "codex")
    assert ok, message


REFUSALS = {
    "no_ledger": (lambda repo: None, {}),
    "corrupt_ledger": (_corrupt, {}),
    "no_receipt": (_set("receipt", None), {}),
    "string_receipt": (_set("receipt", "owner-accepted"), {}),
    "clean_receipt": (_clean, {}),
    "auto_accepted_receipt": (_auto_kind, {}),
    "unknown_kind": (_set_receipt("kind", "superseded-by-hand"), {}),
    "accepted_by_null": (_set_receipt("accepted_by", None), {}),
    "accepted_by_empty": (_set_receipt("accepted_by", ""), {}),
    "accepted_by_not_str": (_set_receipt("accepted_by", 7), {}),
    "history_dict": (_set("acceptance_corrections", {}), {}),
    "history_string": (_set("acceptance_corrections", "row"), {}),
    "history_non_dict_row": (_set("acceptance_corrections", [{"was": "x"}, "row"]), {}),
    "by_missing": (_accepted, {"by": None}),
    "by_empty": (_accepted, {"by": ""}),
    "by_spaces": (_accepted, {"by": "   "}),
    "by_newline": (_accepted, {"by": "the owner\nBLOCK|x"}),
    "by_cr": (_accepted, {"by": "the owner\rx"}),
    "by_surrogate": (_accepted, {"by": "the owner \udc80"}),
    "reason_missing": (_accepted, {"reason": None}),
    "reason_empty": (_accepted, {"reason": ""}),
    "reason_spaces": (_accepted, {"reason": "  "}),
    "reason_newline": (_accepted, {"reason": "line one\nline two"}),
    "reason_cr": (_accepted, {"reason": "line one\rline two"}),
    "reason_surrogate": (_accepted, {"reason": "why \udc80"}),
    "by_auto": (_accepted, {"by": "auto: x"}),
    "by_auto_upper": (_accepted, {"by": "AUTO: x"}),
    "by_same_name": (_accepted, {"by": "a peer"}),
    # Review of 24cb235c, N2: every Unicode line break, not only \n and \r.
    "by_vertical_tab": (_accepted, {"by": "the owner\vx"}),
    "by_form_feed": (_accepted, {"by": "the owner\fx"}),
    "by_nel": (_accepted, {"by": "the owner\x85x"}),
    "by_line_separator": (_accepted, {"by": "the owner\u2028x"}),
    "by_paragraph_separator": (_accepted, {"by": "the owner\u2029x"}),
    "reason_line_separator": (_accepted, {"reason": "one\u2028two"}),
    "reason_nel": (_accepted, {"reason": "one\x85two"}),
    # N1: a lookalike of the reserved prefix (NFKC + casefold, format
    # characters stripped) is the reserved prefix.
    # Review of 1b9ce429, FIX1: only the acceptance that stands is corrected.
    "new_round_reserved": (_accepted_then_reserved, {}),
    "state_reviewed": (_set("state", rl.REVIEWED), {}),
    "receipt_for_an_older_round": (_set_receipt("round", 0), {}),
    "receipt_round_bool": (_set_receipt("round", True), {}),
    "by_fullwidth_auto": (_accepted, {"by": "\uff41\uff55\uff54\uff4f: x"}),
    "by_zero_width_auto": (_accepted, {"by": "\u200bauto: x"}),
    "by_bom_auto": (_accepted, {"by": "\ufeffAuTo: x"}),
}


@pytest.mark.parametrize("case", sorted(REFUSALS))
def test_correction_refused(repo, case):
    build, kwargs = REFUSALS[case]
    build(repo)
    before = _bytes(repo)

    result = _correct_cli(repo, **kwargs)

    assert (result.returncode, _bytes(repo)) == (1, before), result.stdout + result.stderr
    assert result.stderr.startswith("review-ledger: "), result.stderr


@pytest.mark.parametrize("by, reason", [
    ("the owner \ud800", REASON), ("the owner", "why \ud800"),
    (b"bytes", REASON), ("the owner", 7)])
def test_correction_refuses_text_it_cannot_write(repo, by, reason):
    _accepted(repo)
    before = _bytes(repo)

    with pytest.raises(rl.LedgerError):
        rl.correct_acceptance(str(repo), T, by, reason)

    assert _bytes(repo) == before


@pytest.mark.parametrize("args", [
    ["--correct", "--by", "the owner", "--reason", "r"],
    ["--correct-acceptance", "--by", "the owner", "--reas", "r"]])
def test_an_abbreviated_flag_is_a_usage_error(repo, args):
    """Review of 24cb235c, N3: argparse prefix matching is off, so a shortened
    flag never reaches a verb."""
    _accepted(repo)
    before = _bytes(repo)

    result = _cli(repo, *args)

    assert (result.returncode, _bytes(repo)) == (2, before)


def test_a_superseded_receipt_is_not_corrected(repo):
    """T-0109 interplay: after --supersede-accepted the receipt is history in
    `superseded`, and the correction refuses rather than editing it."""
    _accepted(repo)
    rl.reject(str(repo), T, "the owner", supersede_accepted=True)
    before = _bytes(repo)

    result = _correct_cli(repo)

    assert (result.returncode, _bytes(repo)) == (1, before)
    assert _data(repo)["superseded"][0]["receipt"]["accepted_by"] == "a peer"

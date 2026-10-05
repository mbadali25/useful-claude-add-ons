"""T-0109: an owner-attributed rejection supersedes an accepted receipt.

    python3 -m pytest plugin/crew/tests/test_review_reject_accepted.py -q

`review_ledger.py --reject --by <who> --supersede-accepted` moves an ACCEPTED
ticket to NEEDS_REPLAN, keeps the receipt it replaced, whole, in the
append-only `superseded` list with who and when, and clears `receipt`. Plain
`--reject` still refuses an ACCEPTED ticket. The flag never falls back to a
plain rejection: on any state but ACCEPTED it refuses, and every ledger it
cannot read is a refusal that leaves the file byte-identical. `--by` is a
recorded name, not a check of who is calling; an `auto:` name is refused.
`sabotage_review.py` flips each guard and names the test here that goes red.
Every repository is built under tmp_path.
"""
import json
import os
import subprocess
import sys

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import review_ledger as rl
import review_patch
import sabotage_review
from review_fixtures import git, init_repo

_LEDGER = os.path.join(context._ROOT, "hooks", "scripts",  # pylint: disable=protected-access
                       "review_ledger.py")
T = "T1"


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


def _cli(repo, *args):
    return subprocess.run([sys.executable, _LEDGER, "--root", str(repo), "--ticket", T]
                          + list(args), capture_output=True, text=True,
                          stdin=subprocess.DEVNULL, check=False)


def _supersede(repo, by="the owner"):
    args = ["--reject", "--supersede-accepted"]
    if by is not None:
        args += ["--by", by]
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


def _owner_accepted_round_two(repo):
    _review(repo)
    _review(repo)
    rl.accept(str(repo), T, "the owner")


def _auto_accepted(repo):
    _review(repo)
    rl.accept(str(repo), T, "the owner")
    _edit(repo, lambda data: data["receipt"].update(kind=rl.AUTO_KIND, accepted_by=rl.AUTO_BY))


# --- must-allow ----------------------------------------------------------------

def test_supersede_moves_an_owner_accepted_ticket_to_needs_replan(repo):
    _owner_accepted_round_two(repo)
    old = _data(repo)["receipt"]

    result = _supersede(repo)

    data = _data(repo)
    assert result.returncode == 0, result.stderr
    assert (data["state"], data["receipt"]) == (rl.NEEDS_REPLAN, None)
    [row] = data["superseded"]
    assert (row["receipt"], row["by"], bool(row["at"])) == (old, "the owner", True)
    assert (data["rejected"]["by"], data["rejected"]["round"],
            data["rejected"]["superseded"]) == ("the owner", 2, "owner-accepted")
    assert result.stdout.strip() == (
        f"review-ledger: {T} is NEEDS_REPLAN, rejected by the owner at "
        f"{data['rejected']['at']}; superseded the round 2 owner-accepted receipt "
        f"(bundle {old['bundle_sha256'][:12]})")


@pytest.mark.parametrize("kind", ["clean", "auto-accepted"])
def test_supersede_takes_each_known_receipt_kind(repo, kind):
    if kind == "clean":
        _review(repo, "CLEAN")
    else:
        _auto_accepted(repo)
    old = _data(repo)["receipt"]

    result = _supersede(repo)

    data = _data(repo)
    assert result.returncode == 0, result.stderr
    assert (data["state"], data["receipt"], data["superseded"][0]["receipt"],
            data["rejected"]["superseded"]) == (rl.NEEDS_REPLAN, None, old, kind)


def test_supersede_with_budget_left_reserves_nothing(repo):
    _review(repo)
    rl.accept(str(repo), T, "the owner")

    assert _supersede(repo).returncode == 0

    data = _data(repo)
    assert (len(data["rounds"]), data["state"], data.get("refused")) == (1, rl.NEEDS_REPLAN, [])


def test_supersede_does_not_need_a_current_bundle(repo):
    _owner_accepted_round_two(repo)
    (repo / "feature.txt").write_text("feature v2, the head moved\n", encoding="utf-8")
    assert _cli(repo, "--check-receipt").returncode == 1

    result = _supersede(repo)

    assert (result.returncode, _data(repo)["state"]) == (0, rl.NEEDS_REPLAN), result.stderr


def test_after_supersede_only_a_successor_plan_continues(repo):
    _owner_accepted_round_two(repo)
    assert _supersede(repo).returncode == 0
    before = _bytes(repo)

    check = _cli(repo, "--check-receipt")
    assert (check.returncode, "no accepted review receipt" in check.stdout
            or "NEEDS_REPLAN; no receipt stands" in check.stdout) == (1, True), check.stdout
    assert _cli(repo, "--accept", "--by", "the owner").returncode == 1
    assert _cli(repo, "--auto-accept", "--follow-up", "L-1").returncode == 1
    assert _bytes(repo) == before
    assert _cli(repo, "--reserve").returncode == 1
    assert _supersede(repo).returncode == 1
    assert len(_data(repo)["superseded"]) == 1


def test_supersede_survives_a_successor_and_appends(repo, monkeypatch):
    _owner_accepted_round_two(repo)
    assert _supersede(repo).returncode == 0
    first = json.dumps(_data(repo)["superseded"][0], sort_keys=True)
    monkeypatch.setattr(rl, "_plan_approval_receipt", lambda root, ticket, plan_hash: (
        {"approved_by": "owner", "approved_at": "now"}, None))
    assert rl.continue_with_successor_plan(str(repo), T, "c" * 64)[0] is True

    _review(repo, "CLEAN")

    data = _data(repo)
    assert (data["state"], data["receipt"]["kind"], data["receipt"]["round"]) == (
        rl.ACCEPTED, "clean", 3)
    assert json.dumps(data["superseded"][0], sort_keys=True) == first
    assert _cli(repo, "--check-receipt").returncode == 0

    assert _supersede(repo, by="the owner, again").returncode == 0

    rows = _data(repo)["superseded"]
    assert len(rows) == 2
    assert json.dumps(rows[0], sort_keys=True) == first
    assert (rows[1]["receipt"]["round"], rows[1]["by"]) == (3, "the owner, again")


# --- must-block -----------------------------------------------------------------

def _reviewed(repo):
    _review(repo)


def _reviewed_with_a_receipt(repo):
    """A hand-edited state: everything else would pass, so only the state
    check refuses."""
    _owner_accepted_round_two(repo)
    _edit(repo, lambda data: data.__setitem__("state", rl.REVIEWED))


def _in_review(repo):
    _review(repo)
    rl.reserve(str(repo), T, "codex")


def _needs_replan(repo):
    _review(repo)
    _review(repo)
    rl.reserve(str(repo), T, "codex")


def _corrupt(repo):
    _owner_accepted_round_two(repo)
    with open(_path(repo), "w", encoding="utf-8") as fh:
        fh.write("{not json")


def _with(change):
    def build(repo):
        _owner_accepted_round_two(repo)
        _edit(repo, change)
    return build


def _receipt(key, value):
    return _with(lambda data: data["receipt"].__setitem__(key, value))


def _drop_kind(data):
    del data["receipt"]["kind"]


def _receipt_for_round_one(data):
    data["receipt"]["round"] = 1


def _latest_reserved(data):
    data["rounds"][-1]["status"] = "reserved"


def _latest_not_dict(data):
    data["rounds"][-1] = "round 2"


def _round_one(change):
    """An accepted ROUND 1 ledger, then `change`: with round 1, `True == 1`
    and `1.0 == 1`, so only the type checks can refuse (review of 24cb235c,
    FIX2)."""
    def build(repo):
        _review(repo)
        rl.accept(str(repo), T, "the owner")
        _edit(repo, change)
    return build


def _latest_round(value):
    def change(data):
        data["rounds"][-1]["round"] = value
    return change


def _owner_kind_on_clean(repo):
    _review(repo)
    _review(repo, "CLEAN")
    _edit(repo, lambda data: data["receipt"].update(kind="owner-accepted",
                                                     accepted_by="the owner"))


REFUSALS = {
    "no_by": (_owner_accepted_round_two, ["--reject", "--supersede-accepted"]),
    "by_spaces": (_owner_accepted_round_two, ["--reject", "--supersede-accepted", "--by", "  "]),
    "by_auto": (_owner_accepted_round_two,
                ["--reject", "--supersede-accepted", "--by", "auto: anything"]),
    "by_auto_upper": (_owner_accepted_round_two,
                      ["--reject", "--supersede-accepted", "--by", "AUTO:x"]),
    "plain_reject_on_accepted": (_owner_accepted_round_two, ["--reject", "--by", "x"]),
    "flag_on_reviewed": (_reviewed, None),
    "flag_on_reviewed_with_a_receipt": (_reviewed_with_a_receipt, None),
    "flag_on_in_review": (_in_review, None),
    "flag_on_needs_replan": (_needs_replan, None),
    "flag_with_no_ledger": (lambda repo: None, None),
    "corrupt_ledger": (_corrupt, None),
    "receipt_null": (_with(lambda data: data.__setitem__("receipt", None)), None),
    "receipt_string": (_with(lambda data: data.__setitem__("receipt", "owner-accepted")), None),
    "receipt_list": (_with(lambda data: data.__setitem__("receipt", [])), None),
    "receipt_kind_missing": (_with(_drop_kind), None),
    "receipt_kind_unknown": (_receipt("kind", "superseded-by-hand"), None),
    "receipt_round_bool": (_receipt("round", True), None),
    "receipt_round_string": (_receipt("round", "2"), None),
    "receipt_for_an_older_round": (_with(_receipt_for_round_one), None),
    "latest_round_reserved": (_with(_latest_reserved), None),
    "latest_round_not_dict": (_with(_latest_not_dict), None),
    # Review of 1b9ce429, FIX2: a receipt the round's verdict cannot carry,
    # or one naming no bundle, is unreadable.
    "clean_receipt_on_findings": (_receipt("kind", "clean"), None),
    "owner_receipt_on_clean": (_owner_kind_on_clean, None),
    "receipt_bundle_missing": (_with(lambda data: data["receipt"].pop("bundle_sha256")), None),
    "receipt_bundle_empty": (_receipt("bundle_sha256", ""), None),
    # Review of 2743f0d2: a bundle id that is not a sha256 (here a lone
    # surrogate the success line could not print) is unreadable.
    "receipt_bundle_surrogate": (_receipt("bundle_sha256", "\udc80"), None),
    "receipt_bundle_not_hex": (_receipt("bundle_sha256", "x" * 64), None),
    # Round 4: `$` matches before a final newline; fullmatch does not.
    "receipt_bundle_trailing_newline": (_receipt("bundle_sha256", "a" * 64 + "\n"), None),
    # Review of 4357247c, FIX1: a receipt not bound to the round's bundle and
    # base is not the round's receipt.
    "receipt_bundle_other": (_receipt("bundle_sha256", "a" * 64), None),
    "receipt_base_missing": (_with(lambda data: data["receipt"].pop("base")), None),
    "receipt_base_empty": (_receipt("base", ""), None),
    "receipt_base_other": (_receipt("base", "0" * 40), None),
    "superseded_dict": (_with(lambda data: data.__setitem__("superseded", {})), None),
    "superseded_string": (_with(lambda data: data.__setitem__("superseded", "x")), None),
    "round_one_receipt_round_bool": (
        _round_one(lambda data: data["receipt"].__setitem__("round", True)), None),
    "round_one_latest_round_bool": (_round_one(_latest_round(True)), None),
    "round_one_latest_round_float": (_round_one(_latest_round(1.0)), None),
    "round_one_latest_round_string": (_round_one(_latest_round("1")), None),
    # Review of 24cb235c, FIX1/N1/N2: --by goes through the same one-line,
    # UTF-8 and reserved-prefix checks as --correct-acceptance, before the lock.
    "by_surrogate": (_owner_accepted_round_two,
                     ["--reject", "--supersede-accepted", "--by", "the owner \udc80"]),
    "by_newline_auto": (_owner_accepted_round_two,
                        ["--reject", "--supersede-accepted", "--by", "x\nauto:y"]),
    "by_line_separator": (_owner_accepted_round_two,
                          ["--reject", "--supersede-accepted", "--by", "x\u2028y"]),
    "by_fullwidth_auto": (_owner_accepted_round_two,
                          ["--reject", "--supersede-accepted", "--by", "\uff41uto: x"]),
    "by_zero_width_auto": (_owner_accepted_round_two,
                           ["--reject", "--supersede-accepted", "--by", "\u200dauto:x"]),
    "abbreviated_flag": (_owner_accepted_round_two, ["--reject", "--by", "x", "--super"]),
    "superseded_non_dict_row": (
        _with(lambda data: data.__setitem__("superseded", [{"by": "x"}, 3])), None),
}


@pytest.mark.parametrize("case", sorted(REFUSALS))
def test_supersede_is_refused_and_changes_nothing(repo, case):
    build, args = REFUSALS[case]
    build(repo)
    before = _bytes(repo)

    result = _cli(repo, *args) if args else _supersede(repo)

    expected = 2 if case == "abbreviated_flag" else 1
    assert (result.returncode, _bytes(repo)) == (expected, before), result.stdout + result.stderr
    if expected == 1:
        assert result.stderr.startswith("review-ledger: "), result.stderr
    if case == "plain_reject_on_accepted":
        assert "--supersede-accepted" in result.stderr
    if case.startswith("flag_on_") and case != "flag_on_needs_replan":
        assert "nothing accepted to supersede" in result.stderr


@pytest.mark.parametrize("args", [
    ["--reject", "--by", "the owner \udc80"],
    ["--reject", "--by", "x\ny"],
    ["--accept", "--by", "the owner \udc80"],
    ["--accept", "--by", "x\u2028y"],
    ["--accept", "--by", "\uff41uto: x"]])
def test_plain_reject_and_accept_refuse_a_name_they_cannot_write(repo, args):
    """Review of 24cb235c, FIX1: plain --reject and --accept wrote a name the
    success line then crashed on (or a multi-line one); now refused first."""
    _review(repo)
    before = _bytes(repo)

    result = _cli(repo, *args)

    assert (result.returncode, _bytes(repo)) == (1, before), result.stdout + result.stderr
    assert result.stderr.startswith("review-ledger: "), result.stderr


@pytest.mark.parametrize("args", [
    ["--accept", "--by", "x", "--supersede-accepted"],
    ["--status", "--supersede-accepted"],
    ["--reserve", "--supersede-accepted"]])
def test_supersede_flag_needs_reject(repo, args):
    _owner_accepted_round_two(repo)
    before = _bytes(repo)

    result = _cli(repo, *args)

    assert (result.returncode, _bytes(repo)) == (2, before)


def test_status_shows_the_rejection_and_what_it_superseded(repo):
    _owner_accepted_round_two(repo)
    plain = json.loads(_cli(repo, "--status").stdout)
    assert (plain["rejected"], plain["superseded"]) == (None, [])

    assert _supersede(repo).returncode == 0

    after = json.loads(_cli(repo, "--status").stdout)
    assert set(plain) <= set(after)
    assert after["rejected"]["superseded"] == "owner-accepted"
    assert after["superseded"][0]["by"] == "the owner"


def test_every_reject_sabotage_anchor_is_present_exactly_once():
    with open(sabotage_review.REVIEW_LEDGER, encoding="utf-8") as fh:
        source = fh.read()
    anchors = [m[2] for m in sabotage_review.REVIEW_FIX_MUTATIONS
               if m[1] == sabotage_review.REVIEW_LEDGER
               and ("reject" in m[0] or "supersede" in m[0])]
    assert len(anchors) >= 9
    for anchor in anchors:
        assert source.count(anchor) == 1, anchor


@pytest.mark.parametrize("key", ["superseded", "acceptance_corrections"])
@pytest.mark.parametrize("value", [None, 0])
def test_status_shows_a_malformed_history_as_it_is(repo, key, value):
    """Review of 1b9ce429, FIX3: a history that is null or 0 is not an empty
    list; --status shows the value the file holds."""
    _owner_accepted_round_two(repo)
    _edit(repo, lambda data: data.__setitem__(key, value))

    assert json.loads(_cli(repo, "--status").stdout)[key] == value

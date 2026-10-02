"""L-0510: a final 0-BLOCK FINDINGS round auto-accepts through a ledger-guarded verb.

    python3 -m pytest plugin/crew/tests/test_review_auto_accept.py -q

`review_ledger.py --auto-accept --follow-up <id>` takes no `--by`. It accepts
only the latest completed round under the current plan when that round is the
last one the budget allows, its verdict is exactly FINDINGS, its counts read
BLOCK 0 (an int, never a bool), its finding lines agree with FIX + NIT, and
its webtest state is known and clean, and its reviewer is from another model
family than the author's: provider codex or kimi, with a recorded family
other than claude (owner decision 2026-10-01 #3). Every other case -- including every
case where the ledger cannot tell -- is a named refusal that leaves the ledger
byte-identical. The owner's `--accept` refuses a `--by` starting `auto:`, so
the auto string can come only from the guarded verb. Must-block and
must-allow pairs; `sabotage_review.py` flips each guard and names the test
here that goes red. Every repository is built under tmp_path.
"""
import hashlib
import json
import os
import re
import subprocess
import sys
import types

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import review_ledger as rl
import review_patch
import review_run
from review_fixtures import git, init_repo

_LEDGER = os.path.join(context._ROOT, "hooks", "scripts",  # pylint: disable=protected-access
                       "review_ledger.py")
T = "T1"
FOLLOW = "L-9999"
_ABSENT = object()
FIX_LINE = "FIX|src/a.py:12|the retry loop never stops|run it with no network"
NIT_LINE = "NIT|src/b.py:3|the name says list, it holds a set|read it"
BLOCK_LINE = "BLOCK|src/c.py:9|deletes the user's file|run --clean twice"
GOOD = {"counts": {"BLOCK": 0, "FIX": 1, "NIT": 1}, "findings": [FIX_LINE, NIT_LINE],
        "webtest_open": "not-applicable"}


@pytest.fixture(name="repo")
def _repo(tmp_path):
    root = init_repo(tmp_path / "r")
    (root / "feature.txt").write_text("feature v1\n", encoding="utf-8")
    return root


def _round(repo, verdict="FINDINGS", counts=_ABSENT, findings=_ABSENT, webtest_open=_ABSENT,
           provider="codex", failure_class=None, family="gpt", ignored=0):
    """Reserve and record one round through the real ledger, with a real
    bundle of the current tree. `_ABSENT` leaves a key out of the review dict.
    `ignored` is the row's `ignored_lines` as L-0576's `record` writes it (a
    count), mirrored in this round's review.json as L-0576's `review_run`
    writes it (`ignored_lines` the same int, `ignored_text` the lines);
    `_ABSENT` leaves both out, the shape of a round recorded before L-0576."""
    base = git(repo, "rev-parse", "HEAD")
    manifest, _, _ = review_patch.compute(str(repo), base)
    ok, number, message = rl.reserve(str(repo), T, provider)
    assert ok, message
    review = {"verdict": verdict, "bundle_sha256": manifest["bundle_sha256"], "base": base,
              "head": manifest["head"], "provider": provider, "model": None,
              "model_family": family, "failure_class": failure_class,
              "counts": GOOD["counts"] if counts is _ABSENT else counts}
    if findings is not _ABSENT:
        review["findings"] = findings
    if webtest_open is not _ABSENT:
        review["webtest_open"] = webtest_open
    rl.record(str(repo), T, number, review)
    if ignored is not _ABSENT:
        _edit(repo, lambda data: data["rounds"][-1].update(ignored_lines=ignored))
    on_disk = dict(review, round=number)
    if ignored is not _ABSENT:
        on_disk["ignored_lines"] = ignored
        if type(ignored) is int:  # pylint: disable=unidiomatic-typecheck
            on_disk["ignored_text"] = ["stray"] * max(ignored, 0)
    _review_json(repo, json.dumps(on_disk))
    return number


def _review_json(repo, text):
    folder = repo / ".work" / "tickets" / T
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "review.json").write_text(text, encoding="utf-8")


def _good(repo, **kw):
    merged = dict(GOOD, **kw)
    return _round(repo, **merged)


def _cli(repo, *args):
    return subprocess.run([sys.executable, _LEDGER, "--root", str(repo), "--ticket", T]
                          + list(args), capture_output=True, text=True,
                          stdin=subprocess.DEVNULL, check=False)


def _auto(repo, follow=FOLLOW):
    extra = ["--follow-up", follow] if follow is not None else []
    return _cli(repo, "--auto-accept", *extra)


def _edit(repo, change):
    path = rl.ledger_path(str(repo), T)
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    change(data)
    text = json.dumps(data)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


def _ledger_bytes(repo):
    with open(rl.ledger_path(str(repo), T), "rb") as fh:
        return fh.read()


# --- must-block: every case is a named refusal that changes nothing -----------

def _final_with(**kw):
    def build(repo):
        _good(repo)
        _round(repo, **dict(GOOD, **kw))
    return build


def _incomplete(failure):
    def build(repo):
        _good(repo)
        _round(repo, verdict="INCOMPLETE", failure_class=failure, **GOOD)
    return build


def _incomplete_unrefunded(repo):
    _round(repo, verdict="INCOMPLETE", failure_class="tool", **GOOD)
    _round(repo, verdict="INCOMPLETE", failure_class="tool", **GOOD)
    _good(repo)
    _round(repo, verdict="INCOMPLETE", failure_class="tool", **GOOD)
    assert rl.status(str(repo), T)["rounds"][-1]["refunded"] is False


def _clean(repo):
    _good(repo)
    _round(repo, verdict="CLEAN", counts={"BLOCK": 0, "FIX": 0, "NIT": 0}, findings=[],
           webtest_open="not-applicable")


def _final_without(key):
    def build(repo):
        _good(repo)
        values = {k: v for k, v in GOOD.items() if k != key}
        _round(repo, **values)
    return build


def _round_one_only(repo):
    _good(repo)


def _stale(repo):
    _good(repo)
    _good(repo)
    (repo / "feature.txt").write_text("feature v2, edited after review\n", encoding="utf-8")


def _needs_replan(repo):
    _good(repo)
    _good(repo)
    assert rl.reserve(str(repo), T, "codex")[0] is False


def _already(repo):
    _good(repo)
    _good(repo)
    assert _auto(repo).returncode == 0


def _pre_change(repo):
    _good(repo)
    _good(repo)

    def strip(data):
        del data["rounds"][-1]["findings"]
        del data["rounds"][-1]["webtest_open"]
    _edit(repo, strip)


def _superseded(repo):
    _good(repo)
    _good(repo)

    def successor(data):
        data["successors"] = [{"plan_sha256": "a" * 64, "after_round": 2}]
        data["state"] = rl.IN_REVIEW
        data["receipt"] = None
    _edit(repo, successor)


def _plain_final(repo):
    _good(repo)
    _good(repo)


def _final_by(provider, family):
    def build(repo):
        _good(repo)
        _good(repo, provider=provider, family=family)
    return build


def _review_json_with(**fields):
    """This round's review.json as `_round` wrote it, with `fields` replaced
    (a value `_ABSENT` removes its key)."""
    def change(repo):
        data = json.loads((repo / ".work" / "tickets" / T / "review.json").read_text(
            encoding="utf-8"))
        for key, value in fields.items():
            if value is _ABSENT:
                data.pop(key, None)
            else:
                data[key] = value
        _review_json(repo, json.dumps(data))
    return change


def _final_then(change):
    def build(repo):
        _good(repo)
        _good(repo)
        change(repo)
    return build


def _final_row_edit(change):
    def build(repo):
        _good(repo)
        _good(repo)
        _edit(repo, lambda data: change(data["rounds"][-1]))
    return build


REFUSALS = [
    ("block-1", _final_with(counts={"BLOCK": 1, "FIX": 1, "NIT": 1},
                            findings=[BLOCK_LINE, FIX_LINE, NIT_LINE]), FOLLOW, "1 BLOCK"),
    ("block-1-count-only", _final_with(counts={"BLOCK": 1, "FIX": 1, "NIT": 1}), FOLLOW,
     "1 BLOCK"),
    ("incomplete-tool-refunded", _incomplete("tool"), FOLLOW, "INCOMPLETE"),
    ("incomplete-tool-unrefunded", _incomplete_unrefunded, FOLLOW, "INCOMPLETE"),
    ("incomplete-reviewer", _incomplete("reviewer"), FOLLOW, "INCOMPLETE"),
    ("incomplete-tree", _incomplete("tree"), FOLLOW, "INCOMPLETE"),
    ("clean", _clean, FOLLOW, "CLEAN"),
    ("counts-missing", _final_with(counts=None), FOLLOW, "counts"),
    ("counts-list", _final_with(counts=[0, 1, 1]), FOLLOW, "counts"),
    ("block-missing", _final_with(counts={"FIX": 1, "NIT": 1}), FOLLOW, "BLOCK count"),
    ("block-false", _final_with(counts={"BLOCK": False, "FIX": 1, "NIT": 1}), FOLLOW,
     "BLOCK count"),
    ("block-true", _final_with(counts={"BLOCK": True, "FIX": 1, "NIT": 1}), FOLLOW,
     "BLOCK count"),
    ("block-negative", _final_with(counts={"BLOCK": -1, "FIX": 1, "NIT": 1}), FOLLOW,
     "BLOCK count"),
    ("block-string", _final_with(counts={"BLOCK": "0", "FIX": 1, "NIT": 1}), FOLLOW,
     "BLOCK count"),
    ("findings-missing", _final_without("findings"), FOLLOW, "finding lines"),
    ("findings-block-line", _final_with(findings=[BLOCK_LINE, NIT_LINE]), FOLLOW,
     "BLOCK line"),
    ("findings-disagree", _final_with(counts={"BLOCK": 0, "FIX": 2, "NIT": 1}), FOLLOW,
     "do not agree"),
    ("findings-fix-count-nit-line", _final_with(counts={"BLOCK": 0, "FIX": 1, "NIT": 0},
                                                findings=[NIT_LINE]), FOLLOW, "do not agree"),
    ("findings-nit-count-fix-line", _final_with(counts={"BLOCK": 0, "FIX": 0, "NIT": 1},
                                                findings=[FIX_LINE]), FOLLOW, "do not agree"),
    ("findings-unknown-severity", _final_with(counts={"BLOCK": 0, "FIX": 1, "NIT": 0},
                                              findings=["READ|src/a.py"]), FOLLOW,
     "neither a FIX nor a NIT"),
    # Review round 4 FIX 1: a FIX prefix hid a BLOCK-form line after a line break.
    ("finding-embedded-newline", _final_with(counts={"BLOCK": 0, "FIX": 1, "NIT": 0},
                                             findings=[FIX_LINE + "\n" + BLOCK_LINE]), FOLLOW,
     "line break"),
    ("finding-embedded-cr", _final_with(counts={"BLOCK": 0, "FIX": 1, "NIT": 0},
                                        findings=[FIX_LINE + "\r" + BLOCK_LINE]), FOLLOW,
     "line break"),
    # Owner decision 2026-10-01 #6: a verdict recovered from stray lines
    # (L-0576's ignored_lines) is the owner's; an unread count is could-not-tell.
    ("ignored-lines-3", _final_with(ignored=3), FOLLOW, "recovered from 3 stray line(s)"),
    ("ignored-lines-missing", _final_with(ignored=_ABSENT), FOLLOW,
     "no readable ignored_lines"),
    ("ignored-lines-string", _final_with(ignored="x"), FOLLOW, "no readable ignored_lines"),
    ("ignored-lines-bool", _final_with(ignored=True), FOLLOW, "no readable ignored_lines"),
    ("ignored-lines-negative", _final_with(ignored=-1), FOLLOW, "no readable ignored_lines"),
    ("review-json-unreadable", _final_then(lambda repo: _review_json(repo, "{not json")),
     FOLLOW, "review.json"),
    ("review-json-missing", _final_then(
        lambda repo: os.remove(repo / ".work" / "tickets" / T / "review.json")),
     FOLLOW, "review.json"),
    ("review-json-no-ignored-lines", _final_then(_review_json_with(ignored_lines=_ABSENT)),
     FOLLOW, "no readable ignored_lines count"),
    ("review-json-recovered", _final_then(_review_json_with(ignored_lines=1)), FOLLOW,
     "recovered from 1 stray line(s)"),
    # Review round 5 BLOCK: L-0576 writes an int count; any other shape --
    # a list, a string, a bool, a negative -- is could-not-tell, never 0.
    ("review-json-ignored-list", _final_then(_review_json_with(ignored_lines=[])), FOLLOW,
     "no readable ignored_lines count"),
    ("review-json-ignored-string", _final_then(_review_json_with(ignored_lines="0")), FOLLOW,
     "no readable ignored_lines count"),
    ("review-json-ignored-bool", _final_then(_review_json_with(ignored_lines=False)), FOLLOW,
     "no readable ignored_lines count"),
    ("review-json-ignored-negative", _final_then(_review_json_with(ignored_lines=-1)), FOLLOW,
     "no readable ignored_lines count"),
    ("review-json-other-round", _final_then(_review_json_with(round=1)), FOLLOW,
     "is not round 2's"),
    ("review-json-other-bundle", _final_then(_review_json_with(bundle_sha256="0" * 64)),
     FOLLOW, "is for bundle"),
    ("review-json-no-bundle", _final_then(_review_json_with(bundle_sha256=_ABSENT)), FOLLOW,
     "is for bundle"),
    ("webtest-open-missing", _final_without("webtest_open"), FOLLOW, "webtest"),
    ("webtest-open-none", _final_with(webtest_open=None), FOLLOW, "webtest"),
    ("webtest-open-false", _final_with(webtest_open=False), FOLLOW, "webtest"),
    ("webtest-open-1", _final_with(webtest_open=1), FOLLOW, "webtest"),
    ("round-1-of-2", _round_one_only, FOLLOW, "not the final round"),
    ("stale-tree", _stale, FOLLOW, "tree has changed"),
    ("needs-replan", _needs_replan, FOLLOW, rl.NEEDS_REPLAN),
    ("already-accepted", _already, FOLLOW, "already accepted"),
    ("pre-change-row", _pre_change, FOLLOW, "finding lines"),
    ("superseded-plan", _superseded, FOLLOW, "successor replaced"),
    ("same-family-claude", _final_by("claude", "claude"), FOLLOW, "same family"),
    ("provider-unknown-copilot", _final_by("copilot", "gpt"), FOLLOW, "unknown provider"),
    ("provider-unknown-name", _final_by("acme", "acme"), FOLLOW, "unknown provider"),
    ("provider-missing", _final_row_edit(lambda row: row.pop("provider")), FOLLOW,
     "no provider"),
    ("provider-none", _final_row_edit(lambda row: row.update(provider=None)), FOLLOW,
     "no provider"),
    ("family-missing", _final_row_edit(lambda row: row.pop("model_family")), FOLLOW,
     "no model family"),
    ("family-none", _final_by("codex", None), FOLLOW, "no model family"),
    ("family-empty", _final_by("codex", ""), FOLLOW, "no model family"),
    ("family-claude-on-codex", _final_by("codex", "claude"), FOLLOW, "same family"),
    ("follow-up-missing", _plain_final, None, "--follow-up"),
    ("follow-up-path", _plain_final, "../x", "not a plain id"),
    ("follow-up-is-the-ticket", _plain_final, T, "the ticket itself"),
]


@pytest.mark.parametrize("build, follow, named", [r[1:] for r in REFUSALS],
                         ids=[r[0] for r in REFUSALS])
def test_auto_accept_refuses(repo, build, follow, named):
    build(repo)
    before = _ledger_bytes(repo)

    result = _auto(repo, follow)

    assert (result.returncode, named in result.stderr, result.stderr.startswith("review-ledger:"),
            _ledger_bytes(repo) == before) == (1, True, True, True), result.stderr


# --- must-allow ---------------------------------------------------------------

def _receipt(repo):
    return rl.status(str(repo), T)["receipt"]


def test_auto_accept_writes_the_auto_receipt(repo):
    _good(repo, counts={"BLOCK": 1, "FIX": 0, "NIT": 0}, findings=[BLOCK_LINE])
    lines = [FIX_LINE, "FIX|src/d.py:1|second fix|read it", NIT_LINE]
    _good(repo, counts={"BLOCK": 0, "FIX": 2, "NIT": 1}, findings=lines)

    result = _auto(repo)

    receipt = _receipt(repo)
    assert result.returncode == 0, result.stderr
    assert ({k: receipt[k] for k in ("kind", "accepted_by", "round", "verdict", "findings",
                                     "follow_up", "model_family")},
            rl.status(str(repo), T)["state"]) == (
        {"kind": "auto-accepted", "accepted_by": "auto: 0 BLOCK, owner policy 2026-09-30",
         "round": 2, "verdict": "FINDINGS", "findings": lines, "follow_up": FOLLOW,
         "model_family": "gpt"}, rl.ACCEPTED)
    assert result.stdout.splitlines()[1:] == lines


def test_auto_accept_after_a_refunded_round(repo):
    _good(repo)
    assert "not the final round" in _auto(repo).stderr
    _round(repo, verdict="INCOMPLETE", failure_class="tool", **GOOD)
    _good(repo)

    result = _auto(repo)

    assert (result.returncode, _receipt(repo)["round"]) == (0, 3), result.stderr


def test_auto_accept_on_the_successor_plans_final_round(repo, monkeypatch):
    _good(repo, counts={"BLOCK": 1, "FIX": 0, "NIT": 0}, findings=[BLOCK_LINE])
    _good(repo, counts={"BLOCK": 1, "FIX": 0, "NIT": 0}, findings=[BLOCK_LINE])
    assert rl.reserve(str(repo), T, "codex")[0] is False
    monkeypatch.setattr(rl, "_plan_approval_receipt", lambda root, ticket, plan_hash: (
        {"approved_by": "owner", "approved_at": "now"}, None))
    assert rl.continue_with_successor_plan(str(repo), T, "b" * 64)[0] is True
    _good(repo)
    with pytest.raises(rl.LedgerError, match="not the final round"):
        rl.auto_accept(str(repo), T, FOLLOW)
    _good(repo)

    receipt = rl.auto_accept(str(repo), T, FOLLOW)

    assert (receipt["kind"], receipt["round"]) == ("auto-accepted", 4)


@pytest.mark.parametrize("provider, family", [("codex", "gpt"), ("kimi", "kimi")],
                         ids=["codex", "kimi"])
def test_auto_accept_cross_family_round(repo, provider, family):
    _good(repo)
    _good(repo, provider=provider, family=family)

    result = _auto(repo)

    assert (result.returncode, _receipt(repo)["model_family"]) == (0, family), result.stderr


@pytest.mark.parametrize("provider, family", [("codex", "gpt"), ("kimi", "kimi")],
                         ids=["codex", "kimi"])
def test_auto_receipt_names_the_rows_provider_and_family_and_stands(repo, provider, family):
    _good(repo)
    _good(repo, provider=provider, family=family)
    assert _auto(repo).returncode == 0

    result = _cli(repo, "--check-receipt")

    receipt = _receipt(repo)
    assert (result.returncode, receipt["provider"], receipt["model_family"]) == (
        0, provider, family), result.stderr


def test_auto_accept_takes_no_by(repo):
    _plain_final(repo)

    result = _cli(repo, "--auto-accept", "--follow-up", FOLLOW, "--by", "someone")

    assert (result.returncode, _receipt(repo)) == (2, None), result.stderr


# --- the owner's --accept: unchanged, except the auto: prefix is reserved ------

@pytest.mark.parametrize("by", ["auto: 0 BLOCK, owner policy 2026-09-30", "AUTO: x", "  auto:x"])
def test_owner_accept_refuses_the_auto_prefix(repo, by):
    _plain_final(repo)
    before = _ledger_bytes(repo)

    result = _cli(repo, "--accept", "--by", by)

    assert (result.returncode, "reserved for --auto-accept" in result.stderr,
            _ledger_bytes(repo) == before) == (1, True, True), result.stderr


def test_owner_accept_still_takes_a_block_round(repo):
    _good(repo)
    _good(repo, counts={"BLOCK": 1, "FIX": 0, "NIT": 0}, findings=[BLOCK_LINE])

    result = _cli(repo, "--accept", "--by", "Matthew Badali")

    assert (result.returncode, _receipt(repo)["kind"]) == (0, "owner-accepted"), result.stderr


# --- the receipt stands only while its row still passes the guard -------------

def _tamper_block(data):
    data["rounds"][-1]["counts"]["BLOCK"] = 1


def _tamper_lines(data):
    data["receipt"]["findings"] = data["receipt"]["findings"][:1]


def _tamper_by(data):
    data["receipt"]["accepted_by"] = "someone"


def _tamper_provider(data):
    data["rounds"][-1]["provider"] = "claude"


def _tamper_receipt_family(data):
    data["receipt"]["model_family"] = "claude"


def _tamper_receipt_family_missing(data):
    del data["receipt"]["model_family"]


def _tamper_receipt_provider(data):
    data["receipt"]["provider"] = "kimi"


def _tamper_receipt_provider_missing(data):
    del data["receipt"]["provider"]


@pytest.mark.parametrize("tamper", [None, _tamper_block, _tamper_lines, _tamper_by,
                                    _tamper_provider, _tamper_receipt_family,
                                    _tamper_receipt_family_missing, _tamper_receipt_provider,
                                    _tamper_receipt_provider_missing],
                         ids=["untouched", "row-block-1", "receipt-lines-differ",
                              "receipt-by-differs", "row-provider-claude",
                              "receipt-family-claude", "receipt-family-missing",
                              "receipt-provider-differs", "receipt-provider-missing"])
def test_check_receipt_requires_the_auto_rows_guard(repo, tamper):
    _plain_final(repo)
    assert _auto(repo).returncode == 0
    if tamper:
        _edit(repo, tamper)

    result = _cli(repo, "--check-receipt")

    expected = (0, True) if tamper is None else (1, False)
    assert (result.returncode, "auto-accepted" in result.stdout and result.returncode == 0) \
        == expected, result.stdout


def test_receipt_stands_owner_and_clean_unchanged(tmp_path):
    row = {"round": 1, "status": "completed", "verdict": "FINDINGS"}
    root = str(tmp_path)
    assert (rl.receipt_stands({"kind": "owner-accepted", "round": 1}, row, root, T),
            rl.receipt_stands({"kind": "auto-accepted", "round": 1}, row, root, T),
            rl.receipt_stands({"kind": "clean", "round": 1},
                              dict(row, verdict="CLEAN"), root, T)) == (True, False, True)


# --- review round 6 BLOCK 1: the auto receipt binds the review.json it read ---

def _review_json_path(repo):
    return repo / ".work" / "tickets" / T / "review.json"


def _accepted(repo):
    _good(repo)
    _good(repo)
    assert _auto(repo).returncode == 0


def test_auto_receipt_records_the_review_json_it_read(repo):
    _accepted(repo)

    receipt = _receipt(repo)

    digest = hashlib.sha256(_review_json_path(repo).read_bytes()).hexdigest()
    assert (receipt["review_json_sha256"], receipt["ignored_lines"]) == (digest, 0)


def _rj_recovered(repo):
    data = json.loads(_review_json_path(repo).read_text(encoding="utf-8"))
    data["ignored_lines"] = 3
    _review_json(repo, json.dumps(data))


def _rj_reformatted(repo):
    data = json.loads(_review_json_path(repo).read_text(encoding="utf-8"))
    _review_json(repo, json.dumps(data, indent=4))


def _rj_missing(repo):
    os.remove(_review_json_path(repo))


def _rj_unreadable(repo):
    _review_json(repo, "{not json")


def _rj_symlink(repo):
    path = _review_json_path(repo)
    copy = repo.parent / "elsewhere.json"
    copy.write_bytes(path.read_bytes())
    os.remove(path)
    try:
        os.symlink(copy, path)
    except (OSError, NotImplementedError):
        pytest.skip("this platform cannot create a symlink")


def _receipt_edit(change):
    def tamper(repo):
        _edit(repo, lambda data: change(data["receipt"]))
    return tamper


@pytest.mark.parametrize("tamper", [
    _rj_recovered, _rj_reformatted, _rj_missing, _rj_unreadable, _rj_symlink,
    _receipt_edit(lambda r: r.pop("review_json_sha256")),
    _receipt_edit(lambda r: r.update(review_json_sha256="ab" * 31)),
    _receipt_edit(lambda r: r.update(review_json_sha256="AB" * 32)),
    _receipt_edit(lambda r: r.update(review_json_sha256="0" * 64)),
    _receipt_edit(lambda r: r.update(review_json_sha256=None)),
    _receipt_edit(lambda r: r.pop("ignored_lines")),
    _receipt_edit(lambda r: r.update(ignored_lines=1)),
    _receipt_edit(lambda r: r.update(ignored_lines=False)),
], ids=["recovered", "reformatted", "missing", "unreadable", "symlink", "hash-missing",
        "hash-short", "hash-upper", "hash-other", "hash-none", "count-missing", "count-1",
        "count-false"])
def test_auto_receipt_does_not_stand_once_review_json_moves(repo, tamper):
    _accepted(repo)
    assert _cli(repo, "--check-receipt").returncode == 0
    tamper(repo)

    result = _cli(repo, "--check-receipt")

    assert result.returncode == 1, result.stdout


# --- review round 6 BLOCK 2: duplicate keys anywhere are could-not-tell -------

@pytest.mark.parametrize("text", [
    '{"round": 2, "ignored_lines": 3, "ignored_lines": 0}',
    '{"round": 2, "ignored_lines": 0, "counts": {"BLOCK": 1, "BLOCK": 0}}',
    '{"round": 2, "ignored_lines": 0, "rows": [{"a": 1}, {"a": 1, "a": 2}]}',
    '{"round": 1, "round": 2, "ignored_lines": 0}',
], ids=["top-level", "nested", "in-a-list", "round-key"])
def test_auto_accept_refuses_duplicate_keys_in_review_json(repo, text):
    _good(repo)
    _good(repo)
    data = json.loads(_review_json_path(repo).read_text(encoding="utf-8"))
    body = json.dumps({k: v for k, v in data.items() if k not in ("round", "ignored_lines")})
    _review_json(repo, text[:-1] + ", " + body[1:])
    before = _ledger_bytes(repo)

    result = _auto(repo)

    assert (result.returncode, "duplicate key" in result.stderr,
            _ledger_bytes(repo) == before) == (1, True, True), result.stderr


def test_auto_accept_refuses_a_symlinked_review_json(repo):
    _good(repo)
    _good(repo)
    _rj_symlink(repo)

    result = _auto(repo)

    assert (result.returncode, "link" in result.stderr) == (1, True), result.stderr


def test_auto_accept_refuses_a_bool_round_in_review_json(repo):
    """`True == 1`: review.json's round `true` must not pass as round 1."""
    _round_one = _good(repo)
    assert _round_one == 1
    _edit(repo, lambda data: data.update(state=rl.IN_REVIEW))
    data = json.loads(_review_json_path(repo).read_text(encoding="utf-8"))
    data["round"] = True
    _review_json(repo, json.dumps(data))

    problem, _ = rl._review_json_problem(str(repo), T, rl.status(str(repo), T)["rounds"][-1])  # pylint: disable=protected-access

    assert "is not round 1's" in (problem or ""), problem


def test_auto_accept_refuses_a_review_json_for_another_bundle(repo):
    _good(repo)
    _good(repo)
    data = json.loads(_review_json_path(repo).read_text(encoding="utf-8"))
    data["bundle_sha256"] = "0" * 64
    _review_json(repo, json.dumps(data))

    result = _auto(repo)

    assert (result.returncode, "bundle" in result.stderr) == (1, True), result.stderr


# --- review round 6 FIX 5: the step-3 closure commands survive a spaced path --

def _step3_closure_lines():
    path = os.path.join(context._ROOT, "commands", "review.md")  # pylint: disable=protected-access
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    start = text.index("3. **Closure (L-0510).**")
    block = text[start:text.index("\n4. ", start)]
    return [line for line in block.split("\n") if "CLAUDE_PLUGIN_ROOT" in line]


def test_step3_closure_commands_quote_the_plugin_root():
    lines = _step3_closure_lines()
    unquoted = [line for line in lines if re.search(r'(?<!")\$\{CLAUDE_PLUGIN_ROOT\}', line)]

    assert (len(lines) >= 2, unquoted) == (True, []), lines


# --- review round 6 FIX 4: only "\n" separates direction.md lines -------------

def _follow_two(repo, sep, end="\n"):
    _good(repo)
    _good(repo)
    assert _auto(repo).returncode == 0
    folder = repo / ".work" / "tickets" / FOLLOW
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "direction.md").write_bytes(
        (f"# {FOLLOW}{end}{FIX_LINE}{sep}{NIT_LINE}{end}").encode("utf-8"))


@pytest.mark.parametrize("sep, end, code", [
    ("\n", "\n", 0),
    ("\r\n", "\r\n", 0),
    ("\r", "\n", 1),
    ("\u2028", "\n", 1),
    ("\u2029", "\n", 1),
    ("\u0085", "\n", 1),
    ("\x0b", "\n", 1),
    ("\x0c", "\n", 1),
], ids=["lf", "crlf", "bare-cr", "u2028", "u2029", "nel", "vt", "ff"])
def test_check_follow_up_splits_direction_md_on_newline_only(repo, sep, end, code):
    _follow_two(repo, sep, end)

    result = _cli(repo, "--check-follow-up")

    assert result.returncode == code, result.stdout


# --- --check-follow-up: the follow-up ticket quotes every line verbatim -------

def _direction(repo, text, ticket=FOLLOW):
    folder = repo / ".work" / "tickets" / ticket
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "direction.md").write_text(text, encoding="utf-8")


def _whole(repo):
    _direction(repo, f"# {FOLLOW}\n\n```\n{FIX_LINE}\n{NIT_LINE}\n```\n")


def _one_missing(repo):
    _direction(repo, f"# {FOLLOW}\n\n```\n{FIX_LINE}\n```\n")


def _substring_only(repo):
    _direction(repo, f"# {FOLLOW}\n\n- {FIX_LINE}\n- {NIT_LINE}\n")


def _no_file(_repo):
    return None


@pytest.mark.parametrize("write, code, named", [
    (_whole, 0, "follow-up"),
    (_one_missing, 1, NIT_LINE),
    (_substring_only, 1, FIX_LINE),
    (_no_file, 1, "direction.md"),
], ids=["every-line", "one-line-missing", "substring-only", "no-file"])
def test_check_follow_up(repo, write, code, named):
    _plain_final(repo)
    assert _auto(repo).returncode == 0
    write(repo)

    result = _cli(repo, "--check-follow-up")

    assert (result.returncode, named in result.stdout) == (code, True), result.stdout


@pytest.mark.parametrize("kind", ["clean", "owner-accepted"])
def test_check_follow_up_not_applicable(repo, kind):
    _good(repo)
    if kind == "clean":
        _round(repo, verdict="CLEAN", counts={"BLOCK": 0, "FIX": 0, "NIT": 0}, findings=[],
               webtest_open="not-applicable")
    else:
        _good(repo)
        assert _cli(repo, "--accept", "--by", "Matthew Badali").returncode == 0

    result = _cli(repo, "--check-follow-up")

    assert (result.returncode, "not applicable" in result.stdout) == (0, True), result.stdout


@pytest.mark.parametrize("kind", ["garbage", None])
def test_check_follow_up_unknown_kind_is_could_not_tell(repo, kind):
    _clean(repo)
    _edit(repo, lambda data: data["receipt"].update(kind=kind))

    result = _cli(repo, "--check-follow-up")

    assert (result.returncode, "could not tell" in result.stdout) == (1, True), result.stdout


def test_check_receipt_refuses_a_clean_round_with_an_unknown_kind(repo):
    _clean(repo)
    _edit(repo, lambda data: data["receipt"].update(kind="garbage"))

    result = _cli(repo, "--check-receipt")

    assert result.returncode == 1, result.stdout


def _not_utf8(repo):
    folder = repo / ".work" / "tickets" / FOLLOW
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "direction.md").write_bytes(b"\xff")


def _indented(repo):
    _direction(repo, f"# {FOLLOW}\n\n```\n  {FIX_LINE}\n{NIT_LINE}\n```\n")


@pytest.mark.parametrize("write, named", [
    (_not_utf8, "UTF-8"),
    (_indented, FIX_LINE),
], ids=["not-utf8", "indented-line"])
def test_check_follow_up_refuses_by_name(repo, write, named):
    _plain_final(repo)
    assert _auto(repo).returncode == 0
    write(repo)

    result = _cli(repo, "--check-follow-up")

    assert (result.returncode, named in result.stdout, "Traceback" in result.stderr) == (
        1, True, False), result.stdout + result.stderr


@pytest.mark.parametrize("copies, code", [(1, 1), (2, 0)], ids=["one-copy", "two-copies"])
def test_check_follow_up_counts_duplicate_lines(repo, copies, code):
    _good(repo)
    _good(repo, counts={"BLOCK": 0, "FIX": 2, "NIT": 0}, findings=[FIX_LINE, FIX_LINE])
    assert _auto(repo).returncode == 0
    _direction(repo, f"# {FOLLOW}\n\n```\n" + f"{FIX_LINE}\n" * copies + "```\n")

    result = _cli(repo, "--check-follow-up")

    assert result.returncode == code, result.stdout


def test_check_follow_up_keeps_a_u2028_finding_on_one_line(repo):
    """Review round 4 FIX 2: only a newline separates the protocol's lines, so a
    finding carrying U+2028, quoted verbatim on one line, is quoted."""
    line = "FIX|src/a.py:12|left\u2028right|run it"
    _good(repo)
    _good(repo, counts={"BLOCK": 0, "FIX": 1, "NIT": 0}, findings=[line])
    assert _auto(repo).returncode == 0
    _direction(repo, f"# {FOLLOW}\n\n```\n{line}\n```\n")

    result = _cli(repo, "--check-follow-up")

    assert result.returncode == 0, result.stdout


# --- output on a non-UTF-8 console (Windows cp1252, win-repo-2 at 75bd0aea) ---

_NOT_CP1252 = "FIX|src/a.py:12|left\u2028right \u2192 \u4e2d|run it"


def _cp1252_cli(repo, *args):
    """The ledger CLI with stdout and stderr encoded cp1252, as a Windows
    console gives them; the bytes are decoded here as UTF-8."""
    env = dict(os.environ, PYTHONIOENCODING="cp1252", PYTHONUTF8="0")
    result = subprocess.run([sys.executable, _LEDGER, "--root", str(repo), "--ticket", T]
                            + list(args), capture_output=True, stdin=subprocess.DEVNULL,
                            check=False, env=env)
    return (result.returncode, result.stdout.decode("utf-8"),
            result.stderr.decode("utf-8"))


def test_auto_accept_prints_a_non_cp1252_finding_on_a_cp1252_console(repo):
    _good(repo)
    _good(repo, counts={"BLOCK": 0, "FIX": 1, "NIT": 0}, findings=[_NOT_CP1252])

    code, out, err = _cp1252_cli(repo, "--auto-accept", "--follow-up", FOLLOW)

    assert (code, _NOT_CP1252 in out.split("\n"), "Traceback" in err) == (
        0, True, False), out + err


def test_check_follow_up_names_a_non_cp1252_line_on_a_cp1252_console(repo):
    _good(repo)
    _good(repo, counts={"BLOCK": 0, "FIX": 1, "NIT": 0}, findings=[_NOT_CP1252])
    assert _auto(repo).returncode == 0
    _direction(repo, f"# {FOLLOW}\n")

    code, out, err = _cp1252_cli(repo, "--check-follow-up")

    assert (code, _NOT_CP1252 in out, "Traceback" in err) == (1, True, False), out + err


def test_a_refusal_quoting_a_non_cp1252_finding_reaches_a_cp1252_stderr(repo):
    _good(repo)
    _good(repo, counts={"BLOCK": 0, "FIX": 1, "NIT": 0}, findings=["READ|\u4e2d.py"])

    code, _, err = _cp1252_cli(repo, "--auto-accept", "--follow-up", FOLLOW)

    assert (code, "\u4e2d" in err, "Traceback" in err) == (1, True, False), err


def test_autopilot_main_switches_its_streams_to_utf8_first(monkeypatch, tmp_path):
    import crew_autopilot  # pylint: disable=import-outside-toplevel
    calls = []
    monkeypatch.setattr(rl, "utf8_stdio", lambda: calls.append("utf8"))

    crew_autopilot.main(["stops", "--root", str(tmp_path)])

    assert calls == ["utf8"]


def test_review_run_main_switches_its_streams_to_utf8_first(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(rl, "utf8_stdio", lambda: calls.append("utf8"))

    with pytest.raises(SystemExit):
        review_run.main(["--root", str(tmp_path), "--ticket", T, "--scratch", str(tmp_path),
                         "--provider", "codex", "--reserve-only"])

    assert calls == ["utf8"]


# --- review_run.finish records the evidence the guard reads -------------------

def _finish(repo, tmp_path, monkeypatch, webtest, name="s"):
    """One reserved round finished in-process with a FINDINGS answer (one
    FIX), the webtest check stood in for by `webtest`. Returns review.json."""
    scratch = str(tmp_path / name)
    os.makedirs(scratch, exist_ok=True)
    manifest_path = os.path.join(scratch, "manifest.json")
    base = git(repo, "rev-parse", "HEAD")
    manifest, _code = review_patch.build(str(repo), base, os.path.join(scratch, "diff.txt"),
                                         manifest_path)
    monkeypatch.setattr(review_run, "webtest_check", lambda root, ticket, man: webtest)
    _ok, number, _msg = rl.reserve(str(repo), T, "codex")
    output = "\n".join([f"READ|{p['name']}" for p in manifest["parts"]] + [FIX_LINE])
    args = types.SimpleNamespace(root=str(repo), ticket=T, manifest=manifest_path,
                                 provider="codex", model="", work_dir=None, scratch=scratch)
    review_run.finish(args, number, output, 0, False)
    with open(os.path.join(str(repo), ".work", "tickets", T, "review.json"),
              encoding="utf-8") as fh:
        return json.load(fh)


@pytest.mark.parametrize("webtest, expected", [
    ((None, None, []), "not-applicable"),
    (([], {"rerun_exit": 0}, []), 0),
    (([{"line": 3}], {"rerun_exit": 1}, []), 1),
    ((None, {"rerun_exit": 0}, []), None),
], ids=["not-applicable", "zero-open", "one-open", "could-not-read"])
def test_finish_records_findings_and_webtest_state(repo, tmp_path, monkeypatch, webtest,
                                                   expected):
    review = _finish(repo, tmp_path, monkeypatch, webtest)

    row = rl.status(str(repo), T)["rounds"][-1]
    assert (review["findings"], row["findings"], review["webtest_open"],
            row["webtest_open"]) == ([FIX_LINE], [FIX_LINE], expected, expected)


def _record_with_ignored_lines(monkeypatch, repo):
    """Stand in for L-0576's `record`, which writes the row's `ignored_lines`
    count; this branch's `record` does not, by design (owner decision #6)."""
    real = rl.record

    def record(root, ticket, number, review):
        state = real(root, ticket, number, review)
        _edit(repo, lambda data: data["rounds"][-1].update(ignored_lines=0))
        return state
    monkeypatch.setattr(rl, "record", record)


def test_finish_without_ignored_lines_cannot_tell(repo, tmp_path, monkeypatch, capsys):
    """Until L-0576 records the count, no round reads as eligible: the
    eligibility line names the missing field as could-not-tell."""
    _finish(repo, tmp_path, monkeypatch, (None, None, []), "one")
    _finish(repo, tmp_path, monkeypatch, (None, None, []), "two")
    out = capsys.readouterr().out

    assert ("no readable ignored_lines" in out, "auto-accept: eligible" in out) == (
        True, False), out


def test_finish_prints_the_auto_accept_eligibility(repo, tmp_path, monkeypatch, capsys):
    _record_with_ignored_lines(monkeypatch, repo)
    _finish(repo, tmp_path, monkeypatch, (None, None, []), "one")
    first = capsys.readouterr().out
    _finish(repo, tmp_path, monkeypatch, (None, None, []), "two")
    second = capsys.readouterr().out

    assert ("review: auto-accept: refused - not the final round" in first,
            "review: auto-accept: eligible" in second) == (True, True), first + second

"""L-0510: a final 0-BLOCK FINDINGS round auto-accepts through a ledger-guarded verb.

    python3 -m pytest plugin/crew/tests/test_review_auto_accept.py -q

`review_ledger.py --auto-accept --follow-up <id>` takes no `--by`. It accepts
only the latest completed round under the current plan when that round is the
last one the budget allows, its verdict is exactly FINDINGS, its counts read
BLOCK 0 (an int, never a bool), its finding lines agree with FIX + NIT, and
its webtest state is known and clean. Every other case -- including every
case where the ledger cannot tell -- is a named refusal that leaves the ledger
byte-identical. The owner's `--accept` refuses a `--by` starting `auto:`, so
the auto string can come only from the guarded verb. Must-block and
must-allow pairs; `sabotage_review.py` flips each guard and names the test
here that goes red. Every repository is built under tmp_path.
"""
import json
import os
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
           provider="codex", failure_class=None, family="gpt"):
    """Reserve and record one round through the real ledger, with a real
    bundle of the current tree. `_ABSENT` leaves a key out of the review dict."""
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
    return number


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


def test_auto_accept_same_family_round(repo):
    _good(repo, provider="claude", family="claude")
    _good(repo, provider="claude", family="claude")

    result = _auto(repo)

    assert (result.returncode, _receipt(repo)["model_family"]) == (0, "claude"), result.stderr


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


@pytest.mark.parametrize("tamper", [None, _tamper_block, _tamper_lines, _tamper_by],
                         ids=["untouched", "row-block-1", "receipt-lines-differ",
                              "receipt-by-differs"])
def test_check_receipt_requires_the_auto_rows_guard(repo, tamper):
    _plain_final(repo)
    assert _auto(repo).returncode == 0
    if tamper:
        _edit(repo, tamper)

    result = _cli(repo, "--check-receipt")

    expected = (0, True) if tamper is None else (1, False)
    assert (result.returncode, "auto-accepted" in result.stdout and result.returncode == 0) \
        == expected, result.stdout


def test_receipt_stands_owner_and_clean_unchanged():
    row = {"round": 1, "status": "completed", "verdict": "FINDINGS"}
    assert (rl.receipt_stands({"kind": "owner-accepted", "round": 1}, row),
            rl.receipt_stands({"kind": "auto-accepted", "round": 1}, row),
            rl.receipt_stands({"kind": "clean", "round": 1},
                              dict(row, verdict="CLEAN"))) == (True, False, True)


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


def test_finish_prints_the_auto_accept_eligibility(repo, tmp_path, monkeypatch, capsys):
    _finish(repo, tmp_path, monkeypatch, (None, None, []), "one")
    first = capsys.readouterr().out
    _finish(repo, tmp_path, monkeypatch, (None, None, []), "two")
    second = capsys.readouterr().out

    assert ("review: auto-accept: refused - not the final round" in first,
            "review: auto-accept: eligible" in second) == (True, True), first + second

"""review_gate.accepted_state: the local gate verdict, upgraded by a CI receipt.

A receipt (ci_receipt.check) that proves the gate passed on exactly this
committed tree lets a review round go ahead without a 17-20 minute local
`verify-gate --all`. It is only ever an upgrade: local VERIFIED and NO_GATE
never consult it, and anything but a receipt VERIFIED leaves the local verdict
standing. ci_receipt.build must keep asking the LOCAL gate_state, or a receipt
could vouch for itself.
"""
import ast
import os
import subprocess
import types

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import ci_receipt
import review_gate
import review_prompt
import review_run

_SCRIPTS = os.path.join(context._ROOT, "hooks", "scripts")  # pylint: disable=protected-access
V, U, K, N = review_gate.VERIFIED, review_gate.UNVERIFIED, review_gate.UNKNOWN, review_gate.NO_GATE


def _wire(monkeypatch, local, receipt):
    asked = []
    monkeypatch.setattr(review_gate, "gate_state", lambda root: local)

    def check(root, fetch=None):
        asked.append(root)
        return receipt[0], receipt[1], "abc"
    monkeypatch.setattr(ci_receipt, "check", check)
    return asked


@pytest.mark.parametrize("local", [(V, "clean pass"), (N, "no map")])
def test_a_verdict_that_needs_no_upgrade_never_asks_for_a_receipt(monkeypatch, local):
    asked = _wire(monkeypatch, local, (V, "would vouch"))

    assert review_gate.accepted_state("/r") == local
    assert asked == []


@pytest.mark.parametrize("local_state", [U, K])
def test_a_matching_receipt_upgrades_an_unverified_or_unknown_tree(monkeypatch, local_state):
    _wire(monkeypatch, (local_state, "marker behind HEAD"), (V, "CI receipt from run 7"))

    state, reason = review_gate.accepted_state("/r")

    assert state == V
    assert "CI receipt from run 7" in reason and "marker behind HEAD" in reason


@pytest.mark.parametrize("receipt", [(U, "no run for HEAD"), (K, "gh could not be read"),
                                     (N, "stood down")])
@pytest.mark.parametrize("local_state", [U, K])
def test_any_other_receipt_answer_leaves_the_local_verdict(monkeypatch, local_state, receipt):
    _wire(monkeypatch, (local_state, "local reason"), receipt)

    state, reason = review_gate.accepted_state("/r")

    assert state == local_state
    assert reason == f"local reason; CI receipt {receipt[0]}: {receipt[1]}"


@pytest.mark.parametrize("upgraded, refused", [(True, False), (False, True)])
def test_review_run_reserves_on_the_receipt_and_refuses_without_it(monkeypatch, capsys, tmp_path,
                                                                  upgraded, refused):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True, capture_output=True)
    _wire(monkeypatch, (U, "never gated here"), (V if upgraded else U, "receipt says"))
    monkeypatch.setattr(review_run.review_ledger, "check_receipt", lambda root, ticket: (False, "none"))
    monkeypatch.setattr(review_run.review_ledger, "_load", lambda path: ({}, "missing"))
    args = types.SimpleNamespace(root=str(tmp_path), ticket="T-1", provider="codex", allow_unverified=False)

    code = review_run.preflight(args)

    assert (code == review_run.EXIT_UNVERIFIED) is refused, capsys.readouterr().err
    assert review_run.gate_record(args)["state"] == (V if upgraded else U)


@pytest.mark.parametrize("at_record, overridden", [(U, True), (K, True), (V, False)])
def test_the_override_line_says_when_review_json_records_it(monkeypatch, at_record, overridden):
    """Review of 4357247c, FIX2: the prompt is built before the round, and
    gate_record reads the gate again when review.json is written, so a gate
    that passes meanwhile records no override. The prompt's line says when."""
    _wire(monkeypatch, (at_record, "at record time"), (U, "no receipt"))
    args = types.SimpleNamespace(root="/r", allow_unverified=True)

    assert review_run.gate_record(args)["overridden"] is overridden
    assert ("records gate.overridden when the gate still does not accept the tree"
            in review_prompt.OVERRIDE_LINE)


def test_the_receipt_builder_never_consults_receipts():
    """Self-vouching guard. ci_receipt.build records review_gate.gate_state on
    the runner; were it the receipt-aware accepted_state, a receipt from an
    earlier run could stand in for the gate it is supposed to record."""
    with open(os.path.join(_SCRIPTS, "ci_receipt.py"), encoding="utf-8") as fh:
        tree = ast.parse(fh.read())
    used = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)
            and isinstance(n.value, ast.Name) and n.value.id == "review_gate"}

    assert "accepted_state" not in used, used
    assert "gate_state" in used, used

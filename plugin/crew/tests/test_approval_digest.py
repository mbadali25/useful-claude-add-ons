"""The approval digest (T-0026): an approval survives the lifecycle commands
moving spec.md's header `status:` value, and nothing else.

`crew_ticket.approval_digest` normalises exactly one thing -- the value of the
single `status:` token on line 1, when line 1 is a `# ` header and the value is
one of `crew_ticket.STATUS_VALUES`. This loosens what a BLOCKING hook accepts,
so every must-allow case below has must-block neighbours, and each rule has a
mutation in sabotage_scope.py ("APPROVAL DIGEST: ...") that turns its test red.

Everything runs in throwaway repositories under pytest's tmp_path. The receipts
these tests edit are the fixture repository's, never this repository's.
"""
import hashlib
import json
import os
import pathlib
import subprocess
import sys

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import crew_metrics
import crew_ticket
import sabotage_scope
from scope_fixtures import (SCRIPTS, approve_as_user, common_dir, edit, make_repo,
                            make_ticket, run_hook)

HEADER = "# T-1 widget change   status: {status}   risk: {risk}"
DEFAULT_HEADER = HEADER.format(status="spec", risk="low")
BODY_STATUS = "- the header read status: spec at approval\n"


@pytest.fixture(name="repo")
def _repo(tmp_path):
    return make_repo(tmp_path, mode="block")


def _folder(repo):
    return repo / ".work" / "tickets" / "T-1"


def _ticket(repo, header=DEFAULT_HEADER, newline="\n",
            evidence_extra="", plan_header="# Plan"):
    """A valid ticket whose spec.md line 1 is `header`, written byte-exact."""
    folder = make_ticket(repo)
    spec = (folder / "spec.md").read_text(encoding="utf-8").split("\n", 1)[1]
    spec = spec.replace("- src/app.py:1\n", "- src/app.py:1\n" + evidence_extra)
    plan = (folder / "plan.md").read_text(encoding="utf-8").split("\n", 1)[1]
    for name, text in (("spec.md", header + "\n" + spec), ("plan.md", plan_header + "\n" + plan)):
        (folder / name).write_bytes(text.replace("\n", newline).encode("utf-8"))
    return folder


def _approved(repo, **kwargs):
    folder = _ticket(repo, **kwargs)
    crew_ticket.approve(str(repo), "T-1", by="owner")
    return folder


def _swap(path, old, new):
    data = path.read_bytes()
    assert data.count(old.encode("utf-8")) >= 1, f"{old!r} is not in {path}"
    path.write_bytes(data.replace(old.encode("utf-8"), new.encode("utf-8"), 1))


def _state(repo):
    return crew_ticket.status(str(repo), "T-1")["status"]


def _receipt_path(repo):
    return pathlib.Path(common_dir(repo), "crew", "tickets", "T-1", "approval.json")


def _edit_receipt(repo, change):
    path = _receipt_path(repo)
    receipt = json.loads(path.read_text(encoding="utf-8"))
    change(receipt)
    path.write_text(json.dumps(receipt), encoding="utf-8")


def _as_v1(receipt):
    """Strip the /2 fields, leaving the receipt a pre-T-0026 `approve` wrote."""
    for key in ("digest", "plan_digest", "spec_digest"):
        receipt.pop(key, None)


# --- must-allow -----------------------------------------------------------------

@pytest.mark.parametrize("header,newline,old,new", [
    (DEFAULT_HEADER, "\n", "status: spec", "status: review"),
    (DEFAULT_HEADER, "\n", "status: spec", "status: done"),
    (DEFAULT_HEADER, "\n", "status: spec", "status: planned"),
    ("# T-1 widget change   risk: low   status: spec", "\r\n", "status: spec", "status: review"),
    ("\ufeff" + DEFAULT_HEADER, "\n", "status: spec",
     "status: in-progress"),
    (DEFAULT_HEADER, "\r", "status: spec", "status: review"),
    ("\ufeff" + DEFAULT_HEADER, "\r", "status: spec", "status: done"),
], ids=["spec->review", "spec->done", "spec->planned", "crlf", "bom", "bare-cr", "bom-bare-cr"])
def test_status_value_change_keeps_approval(repo, header, newline, old, new):
    folder = _approved(repo, header=header, newline=newline)
    _swap(folder / "spec.md", old, new)

    assert _state(repo) == "approved"


def test_plan_status_value_change_keeps_approval(repo):
    folder = _approved(repo, plan_header="# T-1 plan   status: planned")
    _swap(folder / "plan.md", "status: planned", "status: review")

    assert _state(repo) == "approved"


# --- must-block -----------------------------------------------------------------

def test_risk_change_stales_approval(repo):
    folder = _approved(repo)
    _swap(folder / "spec.md", "risk: low", "risk: high")

    assert _state(repo) == "stale"


def test_title_change_stales_approval(repo):
    folder = _approved(repo)
    _swap(folder / "spec.md", "widget change", "widget rewrite")

    assert _state(repo) == "stale"


def test_body_line_change_stales_approval(repo):
    folder = _approved(repo)
    _swap(folder / "spec.md", "Change the widget.", "Change every widget.")

    assert _state(repo) == "stale"


@pytest.mark.parametrize("extra,old,new", [
    ("", "- src/app.py:1\n", "- src/app.py:1\n- status: review\n"),
    (BODY_STATUS, BODY_STATUS, BODY_STATUS.replace("status: spec", "status: review")),
], ids=["added", "value-changed"])
def test_second_status_line_in_body_stales_approval(repo, extra, old, new):
    folder = _approved(repo, evidence_extra=extra)
    _swap(folder / "spec.md", old, new)

    assert _state(repo) == "stale"


@pytest.mark.parametrize("newline,line", [
    ("\r", "- status: spec\n"),
    ("\r", "- status: spec \n"),
    ("\x0b", "- status: spec \n"),
    ("\x0c", "- status: spec \n"),
    ("\x85", "- status: spec \n"),
    ("\u2028", "- status: spec \n"),
], ids=["bare-cr", "bare-cr-trailing-space", "vt", "ff", "nel", "line-separator"])
def test_body_status_line_after_a_non_lf_break_stales_approval(repo, newline, line):
    folder = _approved(repo, header="# T-1 widget change   risk: low", newline=newline,
                       evidence_extra=line)
    _swap(folder / "spec.md", "- status: spec", "- status: done")

    assert _state(repo) == "stale"


@pytest.mark.parametrize("old,new,expected", [
    ("- status: spec", "- status: done", "stale"),
    ("   status: spec", "   status: review", "approved"),
], ids=["body-status", "header-status"])
def test_mixed_line_endings_split_line_one_where_the_parser_does(repo, old, new, expected):
    folder = _ticket(repo, header="# T-1 widget change   status: spec   risk: low",
                     evidence_extra="- status: spec\n")
    spec = folder / "spec.md"
    spec.write_bytes(spec.read_bytes().replace(b"\n", b"\r", 1))
    crew_ticket.approve(str(repo), "T-1", by="owner")
    _swap(spec, old, new)

    assert _state(repo) == expected


def _splitlines_breaks():
    return [chr(c) for c in range(0x110000) if len(("a" + chr(c) + "b").splitlines()) == 2]


def test_line_one_ends_at_every_break_the_parser_splits_on():
    breaks = _splitlines_breaks()
    normalised = [(crew_ticket.approval_digest(f"# T-1 x   status: spec {br}body".encode())
                   == crew_ticket.approval_digest(f"# T-1 x   status: done {br}body".encode()),
                   crew_ticket.approval_digest(f"# T-1 x {br}- status: spec {br}".encode())
                   == crew_ticket.approval_digest(f"# T-1 x {br}- status: done {br}".encode()))
                  for br in breaks]

    assert (len(breaks), normalised) == (10, [(True, False)] * len(breaks))


@pytest.mark.parametrize("data,digest", [
    (b"# T-1 x   status: spec   risk: low\nbody status: spec\n",
     "05fe05eda330d868dc238de1f95cfa854a9c5ac5d3d9bd9959114217b9f1e5a8"),
    (b"# T-1 x   status: spec   risk: low\r\nbody\r\n",
     "bec7afef2ff0b056549e07918be8720bd364031072da8e1ce2a3b30bd33d1d6e"),
    (b"\xef\xbb\xbf# T-1 x   status: done\nbody\n",
     "be60b607de9e69bb0b51a7ada76b8fa5e1ed1efb36e6db8223810264b433cf62"),
    (b"# T-1 x   status: review",
     "650a3ddcf739396ecf884c328a9f09c4b6f603e9e347c6c0062f72daa5146dd7"),
    (b"# T-1 x   risk: low\nbody status: spec\n",
     "8a30f8a89f540e2177b7e0fd9f589ff83c809478784f390614ff3bc39f4f1dfd"),
], ids=["lf", "crlf", "bom", "no-newline", "unnormalised"])
def test_digest_of_lf_and_crlf_files_is_unchanged_since_1_0_38(data, digest):
    assert crew_ticket.approval_digest(data) == digest


@pytest.mark.parametrize("new,expected", [
    (b"# T-1 x   status: done   risk: low", True),
    (b"# T-1 x   status: spec   risk: high", False),
], ids=["status", "risk"])
def test_file_with_no_line_break_normalises_only_its_status(new, expected):
    old = b"# T-1 x   status: spec   risk: low"

    assert (crew_ticket.approval_digest(old) == crew_ticket.approval_digest(new)) is expected


@pytest.mark.parametrize("header,old,new", [
    (DEFAULT_HEADER, "risk: low", "risk: low   Status: spec"),
    (DEFAULT_HEADER + "   (Status: spec)", "status: spec",
     "status: review"),
], ids=["added", "present-at-approval"])
def test_second_status_token_in_header_stales_approval(repo, header, old, new):
    folder = _approved(repo, header=header)
    _swap(folder / "spec.md", old, new)

    assert _state(repo) == "stale"


@pytest.mark.parametrize("status,old,new", [
    ("spec", "status: spec", "status: blocked"),
    ("done-ish", "status: done-ish", "status: review-ish"),
], ids=["unknown-value", "suffixed-value"])
def test_status_value_outside_vocabulary_stales_approval(repo, status, old, new):
    folder = _approved(repo, header=HEADER.format(status=status, risk="low"))
    _swap(folder / "spec.md", old, new)

    assert _state(repo) == "stale"


def test_crlf_to_lf_stales_approval(repo):
    folder = _approved(repo, newline="\r\n")
    spec = folder / "spec.md"
    spec.write_bytes(spec.read_bytes().replace(b"\r\n", b"\n"))

    assert _state(repo) == "stale"


def test_placeholder_literal_does_not_match_normalised(repo):
    folder = _approved(repo)
    _swap(folder / "spec.md", "status: spec", "status: <status>")

    assert _state(repo) == "stale"


@pytest.mark.parametrize("header", [
    "\n" + DEFAULT_HEADER,
    DEFAULT_HEADER[2:],
], ids=["blank-first-line", "no-hash"])
def test_header_not_on_line_one_is_not_normalised(repo, header):
    folder = _approved(repo, header=header)
    _swap(folder / "spec.md", "status: spec", "status: review")

    assert _state(repo) == "stale"


def test_status_token_glued_to_a_word_is_not_normalised(repo):
    folder = _approved(repo, header="# T-1 widget change   xstatus: spec   risk: low")
    _swap(folder / "spec.md", "xstatus: spec", "xstatus: review")

    assert _state(repo) == "stale"


# --- the receipt, and reading receipts from before /2 ----------------------------

def test_raw_sha_fields_are_the_file_sha256(repo):
    folder = _approved(repo)
    receipt = json.loads(_receipt_path(repo).read_text(encoding="utf-8"))

    assert (receipt["plan_sha256"], receipt["spec_sha256"]) == (
        hashlib.sha256((folder / "plan.md").read_bytes()).hexdigest(),
        hashlib.sha256((folder / "spec.md").read_bytes()).hexdigest())


def test_approve_digests_the_bytes_it_validated_not_a_later_version(repo, monkeypatch):
    folder = _ticket(repo)
    validated = {n: (folder / n).read_bytes() for n in ("plan.md", "spec.md")}
    real_validate = crew_ticket.validate

    def validate_then_edit(top, ticket, contract=None):
        problems = real_validate(top, ticket, contract)
        _swap(folder / "plan.md", "Test: pytest", "Test: pytest -q")
        _swap(folder / "spec.md", "Change the widget.", "Change every widget.")
        return problems

    monkeypatch.setattr(crew_ticket, "validate", validate_then_edit)

    receipt, _ = crew_ticket.approve(str(repo), "T-1", by="owner")

    assert (receipt["plan_digest"], receipt["spec_digest"]) == (
        crew_ticket.approval_digest(validated["plan.md"]),
        crew_ticket.approval_digest(validated["spec.md"]))


def test_approve_records_the_digest_in_the_entry_and_its_history(repo):
    _approved(repo)
    receipt = json.loads(_receipt_path(repo).read_text(encoding="utf-8"))
    fields = ("digest", "plan_digest", "spec_digest")

    assert ([receipt[k] for k in fields] == [receipt["history"][-1][k] for k in fields]
            and receipt["digest"] == crew_ticket.DIGEST_SCHEME)


def test_receipt_without_digest_verifies_unchanged_files(repo):
    _approved(repo)
    _edit_receipt(repo, _as_v1)

    assert _state(repo) == "approved"


def test_receipt_without_digest_stales_on_status_edit(repo):
    folder = _approved(repo)
    _edit_receipt(repo, _as_v1)
    _swap(folder / "spec.md", "status: spec", "status: review")

    assert _state(repo) == "stale"


@pytest.mark.parametrize("scheme", ["crew-approval/9", None, 2])
def test_unknown_digest_scheme_is_stale(repo, scheme):
    _approved(repo)
    _edit_receipt(repo, lambda r: r.update(digest=scheme))

    result = crew_ticket.status(str(repo), "T-1")

    assert (result["status"], repr(scheme) in result["why"]) == ("stale", True)


@pytest.mark.parametrize("change", [
    lambda r: r.pop("spec_digest"),
    lambda r: r.update(plan_digest=None),
    lambda r: r.update(spec_digest=["x"]),
], ids=["missing", "null", "not-a-string"])
def test_a_v2_receipt_without_a_usable_digest_is_stale_not_raw(repo, change):
    _approved(repo)
    _edit_receipt(repo, change)

    assert _state(repo) == "stale"


# --- the consumers, end to end ---------------------------------------------------

def _ready(repo):
    """A header-bearing ticket approved from the user's prompt, base recorded."""
    folder = _ticket(repo)
    approve_as_user(repo)
    subprocess.run([sys.executable, os.path.join(SCRIPTS, "scope_base.py"),
                    "--root", str(repo), "--record", "T-1"],
                   check=True, capture_output=True, stdin=subprocess.DEVNULL)
    return folder


def _check(repo):
    return subprocess.run([sys.executable, os.path.join(SCRIPTS, "completion_audit.py"),
                           "--check", "--ticket", "T-1", "--root", str(repo)],
                          capture_output=True, text=True, check=False,
                          stdin=subprocess.DEVNULL)


def test_guard_allows_touch_write_after_status_review(repo):
    folder = _ready(repo)
    _swap(folder / "spec.md", "status: spec", "status: review")

    code, _, err = run_hook("module", "scope_guard", edit(repo, repo / "src" / "app.py"), repo)

    assert (code, err) == (0, "")


def test_guard_refuses_touch_write_after_risk_change(repo):
    folder = _ready(repo)
    _swap(folder / "spec.md", "risk: low", "risk: high")

    code, _, err = run_hook("module", "scope_guard", edit(repo, repo / "src" / "app.py"), repo)

    assert (code, "spec.md changed since approval" in err) == (2, True)


def test_guard_refuses_touch_write_after_title_change(repo):
    folder = _ready(repo)
    _swap(folder / "spec.md", "widget change", "widget rewrite")

    code, _, err = run_hook("module", "scope_guard", edit(repo, repo / "src" / "app.py"), repo)

    assert (code, "spec.md changed since approval" in err) == (2, True)


def test_audit_passes_after_status_done(repo):
    folder = _ready(repo)
    (repo / "src" / "app.py").write_text("x = 2\n", encoding="utf-8")
    _swap(folder / "spec.md", "status: spec", "status: done")

    assert _check(repo).returncode == 0


def test_audit_refuses_after_risk_change(repo):
    folder = _ready(repo)
    (repo / "src" / "app.py").write_text("x = 2\n", encoding="utf-8")
    _swap(folder / "spec.md", "risk: low", "risk: high")

    done = _check(repo)

    assert (done.returncode, "changed since approval" in done.stdout) == (1, True)


def test_audit_refuses_after_title_change(repo):
    folder = _ready(repo)
    (repo / "src" / "app.py").write_text("x = 2\n", encoding="utf-8")
    _swap(folder / "spec.md", "widget change", "widget rewrite")

    done = _check(repo)

    assert (done.returncode, "changed since approval" in done.stdout) == (1, True)


def test_metrics_reads_approval_after_status_done(repo):
    folder = _ready(repo)
    _swap(folder / "spec.md", "status: spec", "status: done")

    phases = crew_metrics._phases(str(repo), "T-1")  # pylint: disable=protected-access

    assert ("specApproved" in [p["phase"] for p in phases],
            crew_ticket.status(str(repo), "T-1")["status"]) == (True, "approved")


# --- the sabotage table ------------------------------------------------------------

_DIGEST_MUTATIONS = [m for m in sabotage_scope.SCOPE_MUTATIONS
                     if m[0].startswith("APPROVAL DIGEST")]

# The exact set, so deleting a mutation fails here rather than silently
# dropping the rule it covered from sabotage coverage.
_DIGEST_LABELS = {"APPROVAL DIGEST: " + label for label in (
    "the whole first line is normalised",
    "every line's status value is normalised",
    "the bytes after line 1 are dropped",
    "line endings are normalised",
    "leading blank lines are skipped to find the header",
    "any value is normalised, not the closed list",
    "the value needs no boundary after it",
    "the token needs no boundary before it",
    "line 1 need not be a # header",
    "a header with two status tokens is normalised",
    "the preimage drops the normalised/raw flag",
    "a receipt with no digest is read as /2",
    "an unknown digest scheme is read as /2",
    "a /2 receipt missing a digest falls back to raw",
    "nothing is normalised",
    "approve digests a later read of plan.md than it validated",
    "approve digests a later read of spec.md than it validated",
    "line 1 split only on \\n",
)}


def test_the_approval_digest_mutations_are_exactly_the_pinned_set():
    labels = [m[0] for m in _DIGEST_MUTATIONS]

    assert (sorted(labels), len(set(labels))) == (sorted(_DIGEST_LABELS), len(labels))


def test_every_approval_digest_sabotage_anchor_is_present_exactly_once():
    source = pathlib.Path(sabotage_scope.TICKET).read_text(encoding="utf-8")

    assert [source.count(m[2]) for m in _DIGEST_MUTATIONS] == [1] * len(_DIGEST_MUTATIONS)


def test_every_approval_digest_mutation_names_a_test_in_this_file():
    names = {m[4].split("::")[1].split("[")[0] for m in _DIGEST_MUTATIONS}

    assert all(callable(globals().get(name)) for name in names)

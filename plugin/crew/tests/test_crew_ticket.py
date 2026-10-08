"""crew_ticket.py: the ticket contract, plan approval, the active ticket, the
scope mode and its ten-ticket ramp, and the successor-plan seam it drives in
review_ledger.py.
"""
import ast
import hashlib
import json
import os
import pathlib
import re
import subprocess
import sys

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import crew_common
import crew_ticket
import review_ledger as rl
import review_patch
import scope_report
from review_fixtures import git
from scope_fixtures import SCRIPTS, archive_ticket, common_dir, make_repo, make_ticket, ready

_CLI = os.path.join(SCRIPTS, "crew_ticket.py")


def _cli(root, *args):
    return subprocess.run([sys.executable, _CLI] + list(args) + ["--root", str(root)],
                          capture_output=True, text=True, check=False,
                          stdin=subprocess.DEVNULL)


@pytest.fixture(name="repo")
def _repo(tmp_path):
    return make_repo(tmp_path, mode="block")


def _plan(repo, text, ticket="T-1"):
    (repo / ".work" / "tickets" / ticket / "plan.md").write_text(text, encoding="utf-8")


# --- validate -------------------------------------------------------------------

def test_a_complete_contract_validates(repo):
    make_ticket(repo)

    assert crew_ticket.validate(str(repo), "T-1") == []


@pytest.mark.parametrize("section", crew_ticket.SECTIONS)
def test_a_missing_spec_section_fails(repo, section):
    folder = make_ticket(repo)
    spec = folder / "spec.md"
    spec.write_text(spec.read_text(encoding="utf-8").replace(f"## {section}\n", "## Other\n"),
                    encoding="utf-8")

    assert any(section in p for p in crew_ticket.validate(str(repo), "T-1"))


def test_plan_files_outside_touch_fail_validate(repo):
    make_ticket(repo, files=["src/app.py", "other/keep.py"])

    problems = crew_ticket.validate(str(repo), "T-1")

    assert any("'other/keep.py' is outside spec ## Touch" in p for p in problems)


@pytest.mark.parametrize("touch,files,ok", [
    (("src/**",), ["src/*.py"], True),
    (("src/",), ["src/deep/*.py"], True),
    (("src/*.py",), ["src/a*.py"], True),
    (("src/*.py",), ["src/*"], False),
    (("src/?",), ["src/*"], False),
    (("src/*x]",), ["src/[ab]x]"], False),
    (("src/app.py",), ["src/*.py"], False),
    (("src/**",), ["**/*.py"], False),
])
def test_a_plan_glob_is_accepted_only_when_it_cannot_widen_touch(repo, touch, files, ok):
    make_ticket(repo, touch=touch, files=files)

    assert (crew_ticket.validate(str(repo), "T-1") == []) is ok


@pytest.mark.parametrize("entry", ["/etc/passwd", "../outside.py", "src/../../x", "C:/x.py",
                                   "<paths>"])
def test_touch_entries_that_escape_the_repo_fail(repo, entry):
    make_ticket(repo, touch=(entry,))

    assert crew_ticket.validate(str(repo), "T-1") != []


def test_a_bare_bullet_with_prose_is_refused_not_guessed(repo):
    folder = make_ticket(repo)
    spec = folder / "spec.md"
    spec.write_text(spec.read_text(encoding="utf-8").replace("- `src/**`", "- src and docs"),
                    encoding="utf-8")

    assert any("not one path" in p for p in crew_ticket.validate(str(repo), "T-1"))


def test_a_step_missing_its_test_or_risk_fails(repo):
    make_ticket(repo)
    _plan(repo, "## Step 1\nFiles: src/app.py\nTest: pytest\nRisk: low\n"
                "## Step 2\nFiles: src/app.py\n")

    assert any("each list Files, Test and Risk" in p
               for p in crew_ticket.validate(str(repo), "T-1"))


def test_files_can_be_listed_as_bullets_under_the_label(repo):
    make_ticket(repo)
    _plan(repo, "## Step 1\n**Files:**\n- `src/a.py`\n- `other/keep.py`\nTest: t\nRisk: r\n")

    problems = crew_ticket.validate(str(repo), "T-1")

    assert [p for p in problems if "outside" in p] == [
        "plan Files entry 'other/keep.py' is outside spec ## Touch -- amend the spec's Touch "
        "(and approve again), the plan never widens it"]


def test_validate_cli_exits_one_on_an_invalid_plan(repo):
    make_ticket(repo, files=["other/keep.py"])

    done = _cli(repo, "validate", "--ticket", "T-1")

    assert (done.returncode, "INVALID" in done.stdout) == (1, True)


# --- approval -------------------------------------------------------------------

def test_approve_writes_the_receipt_in_the_common_git_dir(repo):
    make_ticket(repo)

    done = _cli(repo, "approve", "--ticket", "T-1", "--by", "owner")
    receipt = json.loads(pathlib.Path(common_dir(repo), "crew", "tickets", "T-1",
                                      "approval.json").read_text(encoding="utf-8"))

    assert done.returncode == 0
    assert set(receipt) >= {"plan_sha256", "spec_sha256", "approved_at", "approved_by"}
    assert receipt["approved_by"] == "owner"


def test_approve_refuses_an_invalid_contract(repo):
    make_ticket(repo, files=["other/keep.py"])

    done = _cli(repo, "approve", "--ticket", "T-1")

    assert (done.returncode, crew_ticket.status(str(repo), "T-1")["status"]) == (1, "none")


@pytest.mark.parametrize("name", ["spec.md", "plan.md"])
def test_editing_an_approved_file_makes_the_approval_stale(repo, name):
    ready(repo)
    target = repo / ".work" / "tickets" / "T-1" / name
    target.write_text(target.read_text(encoding="utf-8") + "\n", encoding="utf-8")

    done = _cli(repo, "status", "--ticket", "T-1")

    assert (done.returncode, done.stdout.split(":")[0]) == (1, "stale")


def test_amend_is_edit_and_approve_again(repo):
    ready(repo)
    target = repo / ".work" / "tickets" / "T-1" / "spec.md"
    target.write_text(target.read_text(encoding="utf-8").replace(
        "- `src/**`", "- `src/**`\n- `other/**`"), encoding="utf-8")
    crew_ticket.approve(str(repo), "T-1", by="owner")

    assert crew_ticket.status(str(repo), "T-1")["status"] == "approved"
    assert "other/**" in crew_ticket.touch_for(str(repo), "T-1")


def test_status_is_none_without_a_receipt(repo):
    make_ticket(repo)

    assert _cli(repo, "status", "--ticket", "T-1").stdout.startswith("none:")


def test_a_corrupt_receipt_is_none_and_blocks_reapproval(repo):
    ready(repo)
    path = pathlib.Path(common_dir(repo), "crew", "tickets", "T-1", "approval.json")
    path.write_text("{", encoding="utf-8")

    assert crew_ticket.status(str(repo), "T-1")["status"] == "none"
    with pytest.raises(crew_ticket.TicketError):
        crew_ticket.approve(str(repo), "T-1")


def test_approve_hashes_the_bytes_it_validated_not_a_later_version(repo, monkeypatch):
    make_ticket(repo)
    plan = repo / ".work" / "tickets" / "T-1" / "plan.md"
    validated = plan.read_bytes()
    real_validate = crew_ticket.validate

    def validate_then_edit(top, ticket, contract=None):
        problems = real_validate(top, ticket, contract)
        plan.write_text("## Step 1\nFiles: other/keep.py\nTest: x\nRisk: x\n",
                        encoding="utf-8")
        return problems

    monkeypatch.setattr(crew_ticket, "validate", validate_then_edit)

    receipt, _ = crew_ticket.approve(str(repo), "T-1", by="owner")

    assert receipt["plan_sha256"] == hashlib.sha256(validated).hexdigest()


def test_the_cli_writes_approved_via_cli(repo):
    make_ticket(repo)

    _cli(repo, "approve", "--ticket", "T-1", "--by", "owner")

    assert crew_ticket.status(str(repo), "T-1")["receipt"]["approved_via"] == "cli"


def test_a_cli_approval_is_unaccepted_unless_the_config_allows_it(repo):
    make_ticket(repo)
    crew_ticket.approve(str(repo), "T-1", by="owner")
    before = crew_ticket.accepted(str(repo), "T-1")["status"]
    (repo / ".crew" / "config.json").write_text(
        json.dumps({"scope": {"mode": "block", "allowCliApproval": True}}), encoding="utf-8")

    after = crew_ticket.accepted(str(repo), "T-1")["status"]

    assert (before, after) == ("unaccepted", "approved")


@pytest.mark.parametrize("value", ["true", 1, "yes", None])
def test_only_a_literal_true_allows_cli_approval(repo, value):
    (repo / ".crew" / "config.json").write_text(
        json.dumps({"scope": {"mode": "block", "allowCliApproval": value}}), encoding="utf-8")

    assert crew_ticket.cli_approval_allowed(str(repo)) is False


def test_a_receipt_from_before_approved_via_is_unaccepted(repo):
    ready(repo)
    path = pathlib.Path(common_dir(repo), "crew", "tickets", "T-1", "approval.json")
    receipt = json.loads(path.read_text(encoding="utf-8"))
    del receipt["approved_via"]
    path.write_text(json.dumps(receipt), encoding="utf-8")

    assert crew_ticket.accepted(str(repo), "T-1")["status"] == "unaccepted"


# --- T-0010: the autopilot receipt ----------------------------------------------

def _autopilot_config(repo, approval="risk", allow=True):
    (repo / ".crew" / "config.json").write_text(json.dumps(
        {"scope": {"mode": "block", "allowCliApproval": allow},
         "autopilot": {"mode": "plan", "approval": approval}}), encoding="utf-8")


def _autopilot_approved(repo, risk="low"):
    """T-1 with a `risk:` header, approved via autopilot; returns spec.md."""
    spec = make_ticket(repo) / "spec.md"
    first, rest = spec.read_text(encoding="utf-8").split("\n", 1)
    spec.write_text(f"{first} title   status: spec   risk: {risk}\n{rest}", encoding="utf-8")
    crew_ticket.approve(str(repo), "T-1", by="autopilot:risk", via=crew_ticket.AUTOPILOT)
    return spec


def test_autopilot_receipt_accepted_under_policy(repo):
    _autopilot_config(repo)
    _autopilot_approved(repo)

    got = crew_ticket.accepted(str(repo), "T-1")

    assert (got["status"], got["receipt"]["approved_via"]) == ("approved", "autopilot")


def test_autopilot_receipt_demoted_when_spec_becomes_high(repo):
    _autopilot_config(repo)
    spec = _autopilot_approved(repo)
    spec.write_text(spec.read_text(encoding="utf-8").replace("risk: low", "risk: high"),
                    encoding="utf-8")

    assert crew_ticket.accepted(str(repo), "T-1")["status"] in ("stale", "unaccepted")


@pytest.mark.parametrize("approval", ["human", "bogus"])
def test_autopilot_receipt_demoted_when_the_policy_no_longer_allows(repo, approval):
    _autopilot_config(repo)
    _autopilot_approved(repo)
    _autopilot_config(repo, approval=approval)

    got = crew_ticket.accepted(str(repo), "T-1")

    assert (got["status"], got["touch"], "autopilot" in got["why"]) == (
        "unaccepted", [], True)


@pytest.mark.parametrize("allow", [False, "true", None])
def test_autopilot_receipt_demoted_without_allow_cli(repo, allow):
    _autopilot_config(repo)
    _autopilot_approved(repo)
    _autopilot_config(repo, allow=allow)

    got = crew_ticket.accepted(str(repo), "T-1")

    assert (got["status"], "allowCliApproval" in got["why"]) == ("unaccepted", True)


def test_autopilot_receipt_needs_allow_cli_even_when_the_policy_says_yes(repo, monkeypatch):
    _autopilot_config(repo)
    _autopilot_approved(repo)
    _autopilot_config(repo, allow=False)
    monkeypatch.setattr(crew_ticket, "_autopilot_policy",
                        lambda top, ticket: {"allow": True, "reason": "stub"})

    got = crew_ticket.accepted(str(repo), "T-1")

    assert (got["status"], "allowCliApproval" in got["why"]) == ("unaccepted", True)


def test_autopilot_receipt_demoted_when_policy_module_missing(repo, monkeypatch):
    _autopilot_config(repo)
    _autopilot_approved(repo)
    monkeypatch.setitem(sys.modules, "crew_autopilot", None)

    got = crew_ticket.accepted(str(repo), "T-1")

    assert (got["status"], "could not be told" in got["why"]) == ("unaccepted", True)


@pytest.mark.parametrize("answer", [{"allow": "yes"}, {"allow": 1}, None, ["allow"]])
def test_autopilot_receipt_demoted_when_the_answer_is_not_a_plain_yes(repo, monkeypatch,
                                                                      answer):
    _autopilot_config(repo)
    _autopilot_approved(repo)
    monkeypatch.setattr(crew_ticket, "_autopilot_policy", lambda top, ticket: answer)

    assert crew_ticket.accepted(str(repo), "T-1")["status"] == "unaccepted"


def test_a_cli_receipt_is_not_held_to_the_autopilot_policy(repo):
    _autopilot_config(repo, approval="human")
    make_ticket(repo)
    crew_ticket.approve(str(repo), "T-1", by="ci")

    assert crew_ticket.accepted(str(repo), "T-1")["status"] == "approved"


def test_status_returns_touch_from_the_bytes_it_hashed(repo, monkeypatch):
    ready(repo)
    folder = repo / ".work" / "tickets" / "T-1"
    approved = {n: (folder / n).read_bytes() for n in ("spec.md", "plan.md")}
    spec = folder / "spec.md"
    spec.write_text(spec.read_text(encoding="utf-8").replace("`src/**`", "`**`"),
                    encoding="utf-8")
    monkeypatch.setattr(crew_ticket, "read_contract", lambda top, ticket: dict(approved))

    result = crew_ticket.status(str(repo), "T-1")

    assert (result["status"], result["touch"]) == ("approved", ["src/**"])


@pytest.mark.parametrize("bad", ["../x", "a/b", "", ".hidden"])
def test_ticket_ids_that_could_name_a_path_are_refused(repo, bad):
    assert _cli(repo, "status", "--ticket", bad).returncode in (1, 2)


# --- active ticket ----------------------------------------------------------------

def test_activate_is_per_worktree(repo, tmp_path):
    make_ticket(repo, "T-1")
    other = tmp_path / "wt"
    git(repo, "worktree", "add", "-q", str(other))
    make_ticket(other, "T-2")

    assert crew_ticket.active_ticket(str(repo))[0] == "T-1"
    assert crew_ticket.active_ticket(str(other))[0] == "T-2"


def test_index_md_is_the_fallback_only_for_a_1_0_ticket_directory(repo):
    make_ticket(repo, "T-3", activate=False)
    (repo / ".work" / "INDEX.md").write_text("- T-3 in progress\n", encoding="utf-8")
    first = crew_ticket.active_ticket(str(repo))
    (repo / ".work" / "INDEX.md").write_text("- T-4 in progress\n", encoding="utf-8")

    second = crew_ticket.active_ticket(str(repo))

    assert (first, second[0]) == (("T-3", ".work/INDEX.md"), None)


@pytest.mark.parametrize("entry", ["T-404", "../x", 7, None])
def test_a_pointer_to_a_missing_ticket_is_broken_not_absent(repo, entry):
    make_ticket(repo, "T-3", activate=False)
    (repo / ".work" / "INDEX.md").write_text("- T-3 in progress\n", encoding="utf-8")
    path = pathlib.Path(common_dir(repo), "crew", "active-ticket")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({crew_ticket.toplevel(str(repo)): entry}), encoding="utf-8")

    ticket, _source, broken = crew_ticket.resolve_active(str(repo))

    assert (ticket, broken) == (None, True)


def test_an_unparseable_pointer_is_broken(repo):
    path = pathlib.Path(common_dir(repo), "crew", "active-ticket")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{", encoding="utf-8")

    assert crew_ticket.resolve_active(str(repo))[2] is True


def test_deactivate_clears_only_this_worktree(repo):
    make_ticket(repo)
    crew_ticket.deactivate(str(repo))

    assert crew_ticket.active_ticket(str(repo))[0] is None


# --- scope mode and the ramp ----------------------------------------------------

@pytest.mark.parametrize("text,expected", [
    (None, "off"),
    ("{}", "off"),
    ('{"scope": {"mode": "report"}}', "report"),
    ('{"scope": {"mode": "blok"}}', "block"),
    ('{"scope": 3}', "block"),
    ("{", "block"),
])
def test_configured_mode(tmp_path, text, expected):
    root = make_repo(tmp_path, mode=None)
    if text is not None:
        (root / ".crew" / "config.json").write_text(text, encoding="utf-8")

    assert crew_ticket.configured_mode(str(root))[0] == expected


def test_auto_ramps_to_block_after_ten_tickets(tmp_path):
    root = make_repo(tmp_path, mode="auto")
    for number in range(1, 12):
        make_ticket(root, f"T-{number}", activate=False)
        crew_ticket.approve(str(root), f"T-{number}", by="t")

    modes = [crew_ticket.effective_mode(str(root), f"T-{n}")[0] for n in (1, 10, 11)]

    assert modes == ["report", "report", "block"]


def test_reapproving_a_ticket_does_not_advance_the_ramp(tmp_path):
    root = make_repo(tmp_path, mode="auto")
    make_ticket(root)
    for _ in range(12):
        crew_ticket.approve(str(root), "T-1", by="t")

    assert crew_ticket.effective_mode(str(root), "T-2")[0] == "report"


def test_the_default_config_declares_scope_off():
    import crew_config  # pylint: disable=import-outside-toplevel

    assert crew_config.default_config()["scope"] == {"mode": "off", "allowCliApproval": False}


# --- Touch globs are segment-aware ------------------------------------------------

@pytest.mark.parametrize("path,glob", [
    ("main.py", "**/*.py"), ("src/a.py", "src/**/a.py"), ("docs/x.md", "src/**"),
    ("src/x", "src"), ("src/a.py", "src/*.py"), ("src/a/b/c.py", "src/**"),
])
def test_matching_agrees_with_the_scope_report_where_no_star_crosses_a_slash(path, glob):
    assert crew_ticket.path_matches(path, glob) == scope_report.matches(path, glob)


@pytest.mark.parametrize("path,glob,expected", [
    ("src/a/b.py", "src/*.py", False),
    ("src/a/b.py", "src/*", False),
    ("src/a/b.py", "*/b.py", False),
    ("src/a/b.py", "s?c/*/b.py", True),
    ("src/a/b.py", "src/**/b.py", True),
    ("src/b.py", "src/**/b.py", True),
    ("src/a/b.py", "src", True),
    ("src/a/b.py", "src/", True),
    ("src/a/b.py", "src/a*", False),
    ("x/src/a.py", "src/**", False),
])
def test_a_star_never_crosses_a_slash(path, glob, expected):
    assert crew_ticket.path_matches(path, glob) is expected


@pytest.mark.parametrize("plan,touch,expected", [
    ("src/*/x.py", ("src/*",), False),
    ("src/**", ("src/*",), False),
    ("src/a/**", ("src/*",), False),
    ("src/*.py", ("src/*",), True),
    ("src/a/*.py", ("src/**",), True),
    ("src/**/x.py", ("src/**",), True),
])
def test_a_plan_glob_cannot_widen_touch_through_a_slash(plan, touch, expected):
    assert crew_ticket.covered_by(plan, list(touch)) is expected


# --- successor plans through the review ledger -------------------------------------

def _exhaust(repo):
    for _ in range(3):
        rl.reserve(str(repo), "T-1", "codex")
    assert rl.status(str(repo), "T-1")["state"] == rl.NEEDS_REPLAN


def _allow_cli(repo):
    (repo / ".crew" / "config.json").write_text(
        json.dumps({"scope": {"mode": "block", "allowCliApproval": True}}), encoding="utf-8")


def _approve_from_prompt(repo):
    return crew_ticket.approve(str(repo), "T-1", by="owner", via=crew_ticket.USER_PROMPT)


def test_an_approved_new_plan_continues_review_after_needs_replan(repo):
    ready(repo)
    _allow_cli(repo)
    _exhaust(repo)
    _plan(repo, "## Step 1\nFiles: src/app.py\nTest: new\nRisk: new\n")

    done = _cli(repo, "approve", "--ticket", "T-1", "--by", "owner")
    again = rl.reserve(str(repo), "T-1", "codex")

    assert (done.returncode, "may continue" in done.stdout, again[:2]) == (0, True, (True, 3))


def test_a_cli_approval_does_not_continue_needs_replan_without_allow_cli(repo):
    ready(repo)
    _exhaust(repo)
    _plan(repo, "## Step 1\nFiles: src/app.py\nTest: new\nRisk: new\n")

    done = _cli(repo, "approve", "--ticket", "T-1", "--by", "owner")

    assert (done.returncode, rl.status(str(repo), "T-1")["state"]) == (3, rl.NEEDS_REPLAN)


def test_a_prompt_approval_continues_needs_replan_without_allow_cli(repo):
    ready(repo)
    _exhaust(repo)
    _plan(repo, "## Step 1\nFiles: src/app.py\nTest: new\nRisk: new\n")

    _, successor = _approve_from_prompt(repo)

    assert (successor[0], rl.status(str(repo), "T-1")["state"] != rl.NEEDS_REPLAN) == (True, True)


def test_reapproving_the_same_plan_is_not_a_successor(repo):
    ready(repo)
    _allow_cli(repo)
    _exhaust(repo)

    done = _cli(repo, "approve", "--ticket", "T-1", "--by", "owner")

    assert (done.returncode, rl.status(str(repo), "T-1")["state"]) == (3, rl.NEEDS_REPLAN)


def test_a_successor_gets_two_rounds_and_no_more(repo):
    ready(repo)
    _exhaust(repo)
    _plan(repo, "## Step 1\nFiles: src/app.py\nTest: new\nRisk: new\n")
    _approve_from_prompt(repo)

    grants = [rl.reserve(str(repo), "T-1", "codex")[0] for _ in range(3)]

    assert grants == [True, True, False]


def test_the_seam_refuses_a_hash_that_is_not_the_approved_plan(repo):
    ready(repo)
    _exhaust(repo)

    ok, reason = rl.continue_with_successor_plan(str(repo), "T-1", "a" * 64)

    assert (ok, "not " + "a" * 12 in reason) == (False, True)


def test_findings_from_before_the_successor_cannot_be_accepted(repo):
    ready(repo)
    (repo / "src" / "app.py").write_text("x = 9\n", encoding="utf-8")
    head = git(repo, "rev-parse", "HEAD")
    bundle = review_patch.compute(str(repo), head)[0]["bundle_sha256"]
    for number in (1, 2):
        rl.reserve(str(repo), "T-1", "codex")
        rl.record(str(repo), "T-1", number, {"verdict": "FINDINGS", "provider": "codex",
                                             "bundle_sha256": bundle, "base": head})
    _exhaust_after_two(repo)
    _plan(repo, "## Step 1\nFiles: src/app.py\nTest: new\nRisk: new\n")
    _approve_from_prompt(repo)

    with pytest.raises(rl.LedgerError, match="successor replaced"):
        rl.accept(str(repo), "T-1", "owner")


def _exhaust_after_two(repo):
    rl.reserve(str(repo), "T-1", "codex")
    assert rl.status(str(repo), "T-1")["state"] == rl.NEEDS_REPLAN


def test_the_successor_approval_is_rechecked_under_the_ledger_lock(repo, monkeypatch):
    ready(repo)
    _exhaust(repo)
    _plan(repo, "## Step 1\nFiles: src/app.py\nTest: new\nRisk: new\n")
    seam = rl.continue_with_successor_plan
    monkeypatch.setattr(rl, "continue_with_successor_plan", lambda *_: (False, "later"))
    _approve_from_prompt(repo)
    monkeypatch.setattr(rl, "continue_with_successor_plan", seam)
    plan_hash = crew_ticket.status(str(repo), "T-1")["receipt"]["plan_sha256"]
    real_enter = rl._Lock.__enter__  # pylint: disable=protected-access

    def enter_after_an_edit(self):
        _plan(repo, "## Step 1\nFiles: src/app.py\nTest: newer\nRisk: new\n")
        return real_enter(self)

    monkeypatch.setattr(rl._Lock, "__enter__", enter_after_an_edit)  # pylint: disable=protected-access

    ok, reason = rl.continue_with_successor_plan(str(repo), "T-1", plan_hash)

    assert (ok, rl.status(str(repo), "T-1")["state"]) == (False, rl.NEEDS_REPLAN), reason


def test_a_round_from_before_the_successor_cannot_be_recorded(repo):
    ready(repo)
    _exhaust(repo)
    _plan(repo, "## Step 1\nFiles: src/app.py\nTest: new\nRisk: new\n")
    _approve_from_prompt(repo)

    with pytest.raises(rl.LedgerError):
        rl.record(str(repo), "T-1", 2, {"verdict": "CLEAN", "provider": "codex",
                                        "bundle_sha256": "x", "base": "y"})


# --- T-0024: approve bound to expected hashes, and precheck ----------------------------

def _shas(repo, ticket="T-1"):
    folder = repo / ".work" / "tickets" / ticket
    return (hashlib.sha256((folder / "plan.md").read_bytes()).hexdigest(),
            hashlib.sha256((folder / "spec.md").read_bytes()).hexdigest())


def _receipt_path(repo, ticket="T-1"):
    return pathlib.Path(common_dir(repo), "crew", "tickets", ticket, "approval.json")


def test_approve_with_matching_expect_records(repo):
    make_ticket(repo)

    receipt, _ = crew_ticket.approve(str(repo), "T-1", by="owner", expect=_shas(repo))

    assert (receipt["plan_sha256"], receipt["spec_sha256"]) == _shas(repo)


@pytest.mark.parametrize("name", ["spec.md", "plan.md"])
def test_approve_with_changed_spec_refuses_and_writes_nothing(repo, name):
    make_ticket(repo)
    expected = _shas(repo)
    target = repo / ".work" / "tickets" / "T-1" / name
    target.write_text(target.read_text(encoding="utf-8") + "\n", encoding="utf-8")

    with pytest.raises(crew_ticket.TicketError, match=f"{name} changed since the approval"):
        crew_ticket.approve(str(repo), "T-1", by="owner", expect=expected)

    assert not _receipt_path(repo).exists()


def test_approve_with_changed_plan_refuses_and_writes_nothing(repo):
    make_ticket(repo)
    expected = _shas(repo)
    _plan(repo, "## Step 1\nFiles: src/app.py\nTest: other\nRisk: low\n")

    with pytest.raises(crew_ticket.TicketError, match="T-1: plan.md changed"):
        crew_ticket.approve(str(repo), "T-1", by="owner", expect=expected)

    assert not _receipt_path(repo).exists()


@pytest.mark.parametrize("expect", [("a" * 64,), ["a" * 64, None], "ab"])
def test_approve_with_a_malformed_expect_refuses(repo, expect):
    make_ticket(repo)

    with pytest.raises(crew_ticket.TicketError, match="expect"):
        crew_ticket.approve(str(repo), "T-1", by="owner", expect=expect)

    assert not _receipt_path(repo).exists()


def test_approve_without_expect_is_unchanged(repo):
    make_ticket(repo)
    _plan(repo, "## Step 1\nFiles: src/app.py\nTest: other\nRisk: low\n")

    receipt, _ = crew_ticket.approve(str(repo), "T-1", by="owner")

    assert (receipt["plan_sha256"], receipt["spec_sha256"]) == _shas(repo)


def test_precheck_of_a_valid_ticket_has_no_problems(repo):
    make_ticket(repo)

    result = crew_ticket.precheck(str(repo), "T-1")

    assert result == {"ticket": "T-1", "problems": [], "plan_sha256": _shas(repo)[0],
                      "spec_sha256": _shas(repo)[1]}


def test_precheck_names_every_problem(repo):
    make_ticket(repo, files=["other/keep.py"])
    spec = repo / ".work" / "tickets" / "T-1" / "spec.md"
    spec.write_text(spec.read_text(encoding="utf-8").replace("## Unknowns\nNone.\n", ""),
                    encoding="utf-8")

    problems = crew_ticket.precheck(str(repo), "T-1")["problems"]

    assert [any("Unknowns" in p for p in problems),
            any("outside spec ## Touch" in p for p in problems)] == [True, True]


@pytest.mark.parametrize("ticket,needle", [("../x", "not a plain id"),
                                           ("T-9", "no ticket folder")])
def test_precheck_bad_id_or_missing_folder(repo, ticket, needle):
    result = crew_ticket.precheck(str(repo), ticket)

    assert (needle in " ".join(result["problems"]), result["plan_sha256"]) == (True, None)


@pytest.mark.parametrize("row,closed", [("| T-1 | done | x |", True),
                                        ("| T-1 | merged | x |", True),
                                        ("| T-1 | Closed | x |", True),
                                        ("| T-1 | cancelled | x |", True),
                                        ("| T-1 | Superseded | x |", True),
                                        ("- cancelled: T-1 widget", True),
                                        ("| T-1 | needs-owner | x |", False),
                                        ("- [x] T-1 widget", True),
                                        ("| T-1 | in-progress | x |", False),
                                        ("| T-2 | done | T-1 |", False),
                                        ("- T-1 widget", False)])
def test_precheck_closed_index_row(repo, row, closed):
    make_ticket(repo)
    (repo / ".work" / "INDEX.md").write_text(f"# Work\n\n{row}\n", encoding="utf-8")

    problems = crew_ticket.precheck(str(repo), "T-1")["problems"]

    assert any("closed in .work/INDEX.md" in p for p in problems) is closed


# Review round 2: the id is matched case-insensitively and whole, for every id
# `_TICKET_RE` accepts -- crew_state's matcher knows only upper-case
# prefix-number keys, so a lower-case or suffixed id read as open.
@pytest.mark.parametrize("ticket,row,closed", [
    ("t-0050", "T-0050 | done | high | x", True),
    ("t-0050", "| T-0050 | Merged | x |", True),
    ("t-0050", "- [x] T-0050 widget", True),
    ("T-0050", "t-0050 | closed | x", True),
    ("T-0050-fix", "T-0050-fix | done | x", True),
    ("T-0050-fix", "| t-0050-FIX | shipped | x |", True),
    ("rel.1", "REL.1 | complete | x", True),
    ("T-0050-fix", "T-0050 | done | x", False),
    ("t-0050", "T-0050-fix | done | x", False),
    ("t-0050", "T-0050 | in-progress | x", False),
    ("t-0050", "T-0051 | done | t-0050 follow-up", False),
    ("t-0050", "- T-0050 widget", False),
])
def test_precheck_closed_row_any_case_or_suffix(repo, ticket, row, closed):
    make_ticket(repo, ticket, activate=False)
    (repo / ".work" / "INDEX.md").write_text(f"# Work\n\n{row}\n", encoding="utf-8")

    problems = crew_ticket.precheck(str(repo), ticket)["problems"]

    assert (any("closed in .work/INDEX.md" in p for p in problems),
            any("could not tell" in p for p in problems)) == (closed, False)


@pytest.mark.parametrize("row", ["| T-0050 |", "t-0050 |", "| t-0050 |  | x |"])
def test_precheck_a_row_with_no_status_is_could_not_tell(repo, row):
    make_ticket(repo, "t-0050", activate=False)
    (repo / ".work" / "INDEX.md").write_text(f"{row}\n", encoding="utf-8")

    problems = crew_ticket.precheck(str(repo), "t-0050")["problems"]

    assert any("could not tell" in p and "t-0050" in p for p in problems), problems


# Review round 3: the row's id cell is its first single-token cell holding a
# letter and a digit (an index column such as `1` is skipped), matched whole --
# a trailing `-` or `.` is part of a valid id, never trimmed in a table. A row
# naming the ticket as a whole cell that is not its id cell cannot be told.
@pytest.mark.parametrize("ticket,row,closed", [
    ("T-1", "| 1 | T-1 | done |", True),
    ("T-1", "| 12 | t-1 | Merged | x |", True),
    ("T-1", "T-1- | done | x", False),
    ("T-1-", "T-1 | done | x", False),
    ("T-1-", "T-1- | done | x", True),
    ("T-1", "T-1. | done | x", False),
    ("T-1", "- [x] T-1. widget", True),
])
def test_precheck_the_id_cell_is_found_and_matched_whole(repo, ticket, row, closed):
    make_ticket(repo, ticket, activate=False)
    (repo / ".work" / "INDEX.md").write_text(f"{row}\n", encoding="utf-8")

    problems = crew_ticket.precheck(str(repo), ticket)["problems"]

    assert (any("closed in .work/INDEX.md" in p for p in problems),
            any("could not tell" in p for p in problems)) == (closed, False)


@pytest.mark.parametrize("row", ["| T-2 | done | T-1 |", "| v2 | T-1 | done |"])
def test_precheck_a_whole_cell_that_is_not_the_id_cell_is_could_not_tell(repo, row):
    make_ticket(repo, "T-1", activate=False)
    (repo / ".work" / "INDEX.md").write_text(f"{row}\n", encoding="utf-8")

    problems = crew_ticket.precheck(str(repo), "T-1")["problems"]

    assert any("could not tell" in p for p in problems), problems


def test_precheck_unreadable_index_is_a_problem_not_open(repo):
    make_ticket(repo)
    (repo / ".work" / "INDEX.md").mkdir()

    problems = crew_ticket.precheck(str(repo), "T-1")["problems"]

    assert any("could not read .work/INDEX.md" in p for p in problems)


def test_precheck_corrupt_receipt(repo):
    make_ticket(repo)
    _receipt_path(repo).parent.mkdir(parents=True)
    _receipt_path(repo).write_text("{", encoding="utf-8")

    problems = crew_ticket.precheck(str(repo), "T-1")["problems"]

    assert any("approval receipt" in p and "unreadable" in p for p in problems)


def test_precheck_outside_git_is_a_problem(tmp_path):
    result = crew_ticket.precheck(str(tmp_path), "T-1")

    assert "not a git repository" in " ".join(result["problems"])


def test_autopilot_receipt_demoted_when_autopilot_block_is_not_an_object(repo):
    _autopilot_config(repo)
    _autopilot_approved(repo)
    (repo / ".crew" / "config.json").write_text(json.dumps(
        {"scope": {"mode": "block", "allowCliApproval": True}, "autopilot": ["x"]}),
        encoding="utf-8")

    assert crew_ticket.accepted(str(repo), "T-1")["status"] == "unaccepted"

# --- T-0010 x T-0024: a group confirm is owner-only ----------------------------------
# The owner decided (2026-09-26) that autopilot's self-approval never uses T-0024's
# group confirm: `approve(via=AUTOPILOT, expect=...)` is refused, whatever the policy
# says, and writes nothing. The owner's confirm and autopilot's one-ticket route both
# still record. POLICY_MUTATIONS in sabotage_autopilot.py turn each of these red.

def _low_risk_ticket(repo):
    spec = make_ticket(repo) / "spec.md"
    first, rest = spec.read_text(encoding="utf-8").split("\n", 1)
    spec.write_text(f"{first} title   status: spec   risk: low\n{rest}", encoding="utf-8")


@pytest.mark.parametrize("which", ["matching", "malformed"])
def test_autopilot_approve_with_a_group_confirm_is_refused(repo, which):
    _autopilot_config(repo, approval="self")
    _low_risk_ticket(repo)
    expect = _shas(repo) if which == "matching" else ("a" * 64,)

    with pytest.raises(crew_ticket.TicketError, match="group confirm is owner-only"):
        crew_ticket.approve(str(repo), "T-1", by="autopilot:self", via=crew_ticket.AUTOPILOT,
                            expect=expect)

    assert not _receipt_path(repo).exists()


def test_owner_group_confirm_still_records_beside_the_autopilot_gate(repo):
    _autopilot_config(repo, approval="self")
    _low_risk_ticket(repo)

    receipt, _ = crew_ticket.approve(str(repo), "T-1", by="owner", via=crew_ticket.USER_PROMPT,
                                     session="s-1", prompt_id="p-1", expect=_shas(repo))

    assert (receipt["approved_via"], receipt["plan_sha256"], receipt["spec_sha256"]) == (
        "user-prompt", *_shas(repo))


def test_autopilot_single_ticket_approval_still_records_under_an_allowing_policy(repo):
    _autopilot_config(repo, approval="risk")
    _low_risk_ticket(repo)

    receipt, _ = crew_ticket.approve(str(repo), "T-1", by="autopilot:risk",
                                     via=crew_ticket.AUTOPILOT)

    assert (receipt["approved_via"], crew_ticket.accepted(str(repo), "T-1")["status"]) == (
        "autopilot", "approved")


# --- where a ticket lives: live or Complete/ (L-0509) ------------------------------


def _tickets(root):
    return os.path.join(str(root), ".work", "tickets")


def test_locate_live(tmp_path):
    os.makedirs(os.path.join(_tickets(tmp_path), "T-1"))

    assert crew_common.locate_ticket(str(tmp_path), "T-1") == (
        os.path.join(_tickets(tmp_path), "T-1"), "live", None)


def test_locate_complete(tmp_path):
    os.makedirs(os.path.join(_tickets(tmp_path), "Complete", "T-1"))

    assert crew_common.locate_ticket(str(tmp_path), "T-1") == (
        os.path.join(_tickets(tmp_path), "Complete", "T-1"), "complete", None)


def test_locate_absent_returns_the_live_path(tmp_path):
    assert crew_common.locate_ticket(str(tmp_path), "L-0509") == (
        os.path.join(_tickets(tmp_path), "L-0509"), "absent", None)


def test_locate_both_is_could_not_tell(tmp_path):
    os.makedirs(os.path.join(_tickets(tmp_path), "T-1"))
    os.makedirs(os.path.join(_tickets(tmp_path), "Complete", "T-1"))

    path, where, why = crew_common.locate_ticket(str(tmp_path), "T-1")

    assert (path, where) == (None, "could not tell")
    assert os.path.join(_tickets(tmp_path), "T-1") in why
    assert os.path.join(_tickets(tmp_path), "Complete", "T-1") in why


@pytest.mark.parametrize("which", ["live", "complete"])
def test_locate_stat_permission_error_is_could_not_tell(tmp_path, monkeypatch, which):
    os.makedirs(os.path.join(_tickets(tmp_path), "Complete", "T-1"))
    target = os.path.join(_tickets(tmp_path), *(("T-1",) if which == "live" else ("Complete", "T-1")))
    real = os.stat

    def stat(path, *args, **kwargs):
        if os.fspath(path) == target:
            raise PermissionError(13, "Permission denied", target)
        return real(path, *args, **kwargs)
    monkeypatch.setattr(crew_common.os, "stat", stat)

    path, where, why = crew_common.locate_ticket(str(tmp_path), "T-1")

    assert (path, where) == (None, "could not tell")
    assert "Permission denied" in why


def test_locate_not_a_directory_is_absent(tmp_path):
    os.makedirs(_tickets(tmp_path))
    pathlib.Path(_tickets(tmp_path), "Complete").write_text("a file, not the archive\n", encoding="utf-8")

    assert crew_common.locate_ticket(str(tmp_path), "T-1") == (
        os.path.join(_tickets(tmp_path), "T-1"), "absent", None)


@pytest.mark.parametrize("ticket", [None, 7, "", "../x", "a/b", "Complete", "complete", "COMPLETE"])
def test_locate_never_raises(tmp_path, ticket):
    path, where, why = crew_common.locate_ticket(str(tmp_path), ticket)

    assert (path, where, bool(why)) == (None, "could not tell", True)


def test_locate_with_an_unusable_top_never_raises():
    assert crew_common.locate_ticket("\0bad", "T-1")[1] == "could not tell"


def test_ticket_folder_raises_only_through_the_callers_error(tmp_path):
    os.makedirs(os.path.join(_tickets(tmp_path), "Complete", "T-1"))
    assert crew_common.ticket_folder(str(tmp_path), "T-1", ValueError) == os.path.join(
        _tickets(tmp_path), "Complete", "T-1")
    os.makedirs(os.path.join(_tickets(tmp_path), "T-1"))

    with pytest.raises(ValueError, match="could not tell where T-1 lives: both "):
        crew_common.ticket_folder(str(tmp_path), "T-1", ValueError)


@pytest.mark.parametrize("name", ["Complete", "complete", "COMPLETE"])
def test_complete_is_reserved(name):
    assert crew_common.reserved_id(name)
    assert crew_common.PLAIN_ID.match(name) and not crew_common.TICKET_ID.match(name)


@pytest.mark.parametrize("ticket", ["L-0509", "W-0001", "T-0001", "SDP-12"])
def test_ids_beyond_t_are_accepted(ticket):
    assert crew_common.TICKET_ID.match(ticket) and crew_common.PLAIN_ID.match(ticket)
    assert crew_common.TICKET_ID_SEARCH.search(f"| {ticket} | open |").group(1) == ticket
    assert not crew_common.reserved_id(ticket)


def test_ticket_id_digits_are_ascii():
    assert not crew_common.TICKET_ID.match("T-١٢")


def test_approval_survives_archive(tmp_path):
    """The receipt hashes spec.md/plan.md bytes, not their path, and lives under
    the git common dir, so a moved folder keeps it (direction finding 7)."""
    from scope_fixtures import approve_as_user  # pylint: disable=import-outside-toplevel
    root = make_repo(tmp_path, mode="block")
    make_ticket(root)
    approve_as_user(root)
    before = json.loads(pathlib.Path(crew_ticket.approval_path(str(root), "T-1")).read_text(encoding="utf-8"))
    folder = archive_ticket(root)

    after = json.loads(pathlib.Path(crew_ticket.approval_path(str(root), "T-1")).read_text(encoding="utf-8"))
    spec = pathlib.Path(folder, "spec.md").read_bytes()

    assert after == before
    assert hashlib.sha256(spec).hexdigest() == after["spec_sha256"]


# Modules that still keep their own copy of a ticket-id regex or build a ticket
# path themselves, each with why. Every one is a harness path
# (`scripts/check-tooling-pr.py` HARNESS), which T-0087 says changes in its own
# PR: L-0509's harness follow-up routes them and empties these lists.
_HARNESS_FOLLOW_UP = {
    "crew_ticket.py": "harness: ticket_dir/check_ticket move onto crew_common in the follow-up",
    "review_checks.py": "harness: its own plain-id regex",
    "review_ledger.py": "harness: review.json/direction.md paths and its id regex",
    "review_prompt.py": "harness: spec/plan/webtest blocks",
    "review_run.py": "harness: the default work_dir",
    "scope_guard.py": "harness: the own-files prefix (a guard blocking-decision change)",
}
_PATH_ALLOWED = dict(_HARNESS_FOLLOW_UP, **{
    "crew_common.py": "the resolver itself",
    "crew_status.py": "enumerates .work/tickets/ to count live and archived folders",
    "crew_migrate.py": "the 0.20 layout: legacy files and the live migration target",
    "crew_tracker.py": "_note_text writes the live folder's link once, at create",
    "crew_wave.py": "copies an eligible (so live, never archived) ticket folder into a lane "
                    "worktree and reads the lane's own copy there",
})
_SCRIPTS_DIR = os.path.dirname(crew_ticket.__file__)


def _script_trees():
    for name in sorted(os.listdir(_SCRIPTS_DIR)):
        if name.endswith(".py"):
            with open(os.path.join(_SCRIPTS_DIR, name), encoding="utf-8") as handle:
                yield name, ast.parse(handle.read())


def _builds_ticket_path(node):
    if isinstance(node, ast.Call) and node.args:
        consts = [a.value if isinstance(a, ast.Constant) else None for a in node.args]
        if any(consts[i] == ".work" and consts[i + 1] == "tickets" for i in range(len(consts) - 1)):
            return True
    if isinstance(node, ast.JoinedStr):
        for i, part in enumerate(node.values[:-1]):
            if isinstance(part, ast.Constant) and str(part.value).endswith(".work/tickets/") \
                    and isinstance(node.values[i + 1], ast.FormattedValue):
                return not _is_prose(node)
    return False


def _is_prose(node):
    """An f-string that only NAMES the folder in a message: it has words around it."""
    text = "".join(p.value for p in node.values if isinstance(p, ast.Constant))
    return " " in text.strip()


def test_no_module_builds_ticket_paths_itself():
    found = [f"{name}:{node.lineno}" for name, tree in _script_trees() if name not in _PATH_ALLOWED
             for node in ast.walk(tree) if _builds_ticket_path(node)]

    assert found == []


def test_the_ticket_path_check_sees_a_join_and_an_fstring():
    join = ast.parse('os.path.join(root, ".work", "tickets", t)').body[0].value
    fstr = ast.parse('f".work/tickets/{t}/"').body[0].value
    prose = ast.parse('f"no folder at .work/tickets/{t}/ here"').body[0].value

    assert (_builds_ticket_path(join), _builds_ticket_path(fstr), _builds_ticket_path(prose)) == (
        True, True, False)


_ID_SHAPES = ("[A-Z][A-Z0-9]*-", "[A-Za-z0-9][A-Za-z0-9._-]")
# A copy a harness sabotage row anchors on verbatim: aliasing it would lose
# that anchor, and the sabotage file is harness too. Same shape as TICKET_ID.
_REGEX_ANCHORED = {
    "crew_resume.py": "sabotage_resume.py's non-ASCII-digit row anchors _TICKET_ID_RE's line",
}
# A regex of the plain-id SHAPE that is not a ticket id at all.
_NOT_A_TICKET_ID = {
    "crew_coord.py": "_PART_RE is one part of a coordination repo key, not a ticket id",
    "crew_bridge.py": "LABEL_RE is a peer session's label for `ring --to`, not a ticket id",
}


def test_ticket_id_regexes_are_defined_once():
    found = []
    for name, tree in _script_trees():
        if name == "crew_common.py" or name in _HARNESS_FOLLOW_UP or name in _REGEX_ANCHORED \
                or name in _NOT_A_TICKET_ID:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str) \
                    and any(shape in node.value for shape in _ID_SHAPES):
                found.append(f"{name}:{node.lineno}")

    assert found == []


def test_an_anchored_copy_is_still_the_shared_shape():
    import crew_resume  # pylint: disable=import-outside-toplevel
    assert crew_resume._TICKET_ID_RE.pattern.replace("$", "") == (  # pylint: disable=protected-access
        crew_common.TICKET_ID.pattern.replace("\\Z", ""))


def test_the_shared_shapes_are_the_ones_the_check_looks_for():
    assert _ID_SHAPES[0] in crew_common.TICKET_ID_CORE
    assert _ID_SHAPES[1] in crew_common.PLAIN_ID.pattern
    assert re.compile(crew_common.TICKET_ID_CORE).fullmatch("L-0509")

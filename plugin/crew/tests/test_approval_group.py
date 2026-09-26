"""T-0024 group approval: several ids, ranges and one plain-text form in one
approval prompt, recorded only after the user's own `/crew:approve --confirm`.

The hook BLOCKS prompts, so this file carries the parser table, the must-block
cases (exit 2, no receipt, no pending list left behind) and the must-allow
cases (pending, then confirm, then one receipt per ticket). Every guard branch
has a mutation in sabotage_approval.py that turns a named test here red.
"""
import json
import pathlib

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import approval_hook
import crew_ticket
from scope_fixtures import common_dir, make_repo, make_ticket, prompt

GROUP, SINGLE, CONFIRM, REFUSE, NONE = "group", "single", "confirm", "refuse", "none"


@pytest.fixture(name="repo")
def _repo(tmp_path):
    return make_repo(tmp_path, mode="block")


# --- step 1: the parser -------------------------------------------------------------

@pytest.mark.parametrize("text,kind,ids,form", [
    ("/crew:approve T-1", SINGLE, ("T-1",), "slash"),
    ("  /crew:approve T-1  \n", SINGLE, ("T-1",), "slash"),
    ("/crew:approve T-1 T-2", GROUP, ("T-1", "T-2"), "slash"),
    ("/crew:approve T-1,T-2", GROUP, ("T-1", "T-2"), "slash"),
    ("/crew:approve T-1, T-2 ,T-3", GROUP, ("T-1", "T-2", "T-3"), "slash"),
    ("/crew:approve T-0010..T-0012", GROUP, ("T-0010", "T-0011", "T-0012"), "slash"),
    ("/crew:approve T-8..T-10", GROUP, ("T-8", "T-9", "T-10"), "slash"),
    ("/crew:approve T-1 T-0003..T-0004 T-1", GROUP, ("T-1", "T-0003", "T-0004"), "slash"),
    ("/crew:approve T-1..T-1", GROUP, ("T-1",), "slash"),
    ("/crew:approve --confirm", CONFIRM, (), "slash"),
    ("  /crew:approve   --confirm \n", CONFIRM, (), "slash"),
    ("<command-message>crew:approve is running</command-message>\n"
     "<command-name>/crew:approve</command-name>\n<command-args>T-1 T-2</command-args>",
     GROUP, ("T-1", "T-2"), "expanded"),
    ("<command-name>/crew:approve</command-name>\n<command-args>T-1</command-args>",
     SINGLE, ("T-1",), "expanded"),
    ("<command-name>/crew:approve</command-name>\n<command-args>--confirm</command-args>",
     CONFIRM, (), "expanded"),
    ("approve T-1", GROUP, ("T-1",), "plain-text"),
    ("Approve T-1.", GROUP, ("T-1",), "plain-text"),
    ("please approve T-1 and T-2!", GROUP, ("T-1", "T-2"), "plain-text"),
    ("PLEASE APPROVE T-1, T-2, and T-3", GROUP, ("T-1", "T-2", "T-3"), "plain-text"),
    ("approve T-1,T-2", GROUP, ("T-1", "T-2"), "plain-text"),
    ("approve T-0010 through T-0012", GROUP, ("T-0010", "T-0011", "T-0012"), "plain-text"),
    ("approve T-0010 thru T-0011", GROUP, ("T-0010", "T-0011"), "plain-text"),
    ("approve T-0010 to T-0011", GROUP, ("T-0010", "T-0011"), "plain-text"),
    ("  approve T-0010..T-0011  ", GROUP, ("T-0010", "T-0011"), "plain-text"),
])
def test_every_approval_shape_parses(text, kind, ids, form):
    request = approval_hook.parse(text)

    assert (request.kind, request.ids, request.form, request.error) == (kind, ids, form, None)


@pytest.mark.parametrize("text,reason", [
    ("/crew:approve T-1\nT-2", "one line"),
    ("/crew:approve\nT-1", "one line"),
    ("/crew:approve T-1\r/crew:approve T-2", "one line"),
    ("/crew:approve T-1 T-2", "one line"),
    ("<command-name>/crew:approve</command-name>\n<command-args>T-1\nT-2</command-args>",
     "one line"),
    ("approve T-1\napprove T-2", "one line"),
    ("approve T-1\nand also some notes", "one line"),
    ("\n\n approve T-1 through T-3\nthanks", "one line"),
    ("/crew:approve A-1..B-3", "prefix"),
    ("approve A-1 through B-3", "prefix"),
    ("/crew:approve T-5..T-3", "reversed"),
    ("approve T-5 through T-3", "reversed"),
    ("/crew:approve T-1..T-21", "more than 20"),
    ("/crew:approve T-1..T-999999999999", "more than 20"),
    ("/crew:approve T-1..T-15 T-16..T-30", "more than 20"),
    ("/crew:approve --confirm T-1", "--confirm"),
    ("/crew:approve T-1 --confirm", "--confirm"),
    ("/crew:approve --confirm --confirm", "--confirm"),
    ("/crew:approve T-1 T-1", "duplicate"),
    ("approve T-1 and T-1", "duplicate"),
    ("/crew:approve", "usage"),
    ("/crew:approve , ,", "usage"),
])
def test_malformed_requests_are_refused_with_a_named_reason(text, reason):
    request = approval_hook.parse(text)

    assert (request.kind, reason in (request.error or "")) == (REFUSE, True), request


def test_a_range_token_that_is_also_a_ticket_folder_is_ambiguous(repo):
    make_ticket(repo, "T-1..T-2", activate=False)

    request = approval_hook.parse("/crew:approve T-1..T-2", str(repo))

    assert (request.kind, "ambiguous" in request.error) == (REFUSE, True)


@pytest.mark.parametrize("text", [
    "does the reviewer approve T-1?",
    "should I run /crew:approve T-1 T-2 now?",
    "approve it",
    "approve this",
    "lgtm",
    "ship it",
    "I approve T-1 and T-2",
    "approve T-1 please",
    "approve T-1 T-2 and deploy",
    "approve T-1andT-2",
    "approve T-1 T-2",
    "`/crew:approve T-1 T-2`",
    "hello\napprove T-1",
    "notes\n/crew:approve T-1 T-2",
])
def test_mid_sentence_is_not_an_approval(text):
    assert approval_hook.parse(text).kind == NONE


@pytest.mark.parametrize("text", ["yes", "y", "confirm", "Yes, confirm", "--confirm",
                                  "approve --confirm", "/crew:approve  confirm"])
def test_yes_is_not_a_confirm(text):
    assert approval_hook.parse(text).kind != CONFIRM


@pytest.mark.parametrize("text", ["/crew:approve T-1\nT-2", "approve T-1\napprove T-2",
                                  "please approve T-1 and T-2\n\nthanks"])
def test_multiline_paste_with_ids_is_refused(text):
    request = approval_hook.parse(text)

    assert (request.kind, "one line" in (request.error or "")) == (REFUSE, True)


@pytest.mark.parametrize("text,ticket", [("/crew:approve T-1", "T-1"),
                                         ("/crew:approve ../x", "../x"),
                                         ("/crew:approve T-0010..", "T-0010..")])
def test_single_id_parse_is_unchanged(text, ticket):
    assert (approval_hook.parse(text).kind, approval_hook.parse(text).ids) == \
        (SINGLE, (ticket,))


# --- step 3: pending, confirm, refuse-all -------------------------------------------------

def _receipt(repo, ticket):
    path = pathlib.Path(common_dir(repo), "crew", "tickets", ticket, "approval.json")
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def _pending(repo):
    folder = pathlib.Path(common_dir(repo), "crew", "approval-pending")
    return sorted(folder.iterdir()) if folder.exists() else []


def _say(capsys, repo, text, session="sess-1", prompt_id="p-1"):
    payload = dict(prompt(repo, text, session=session), prompt_id=prompt_id)
    code = approval_hook.handle(payload)
    out, err = capsys.readouterr()
    return code, out, err


def _context(out):
    return json.loads(out)["hookSpecificOutput"]["additionalContext"]


def _tickets(repo, *ids, **kwargs):
    for ticket in ids:
        make_ticket(repo, ticket, activate=False, **kwargs)


def _sha(repo, ticket, name):
    import hashlib  # pylint: disable=import-outside-toplevel
    data = (repo / ".work" / "tickets" / ticket / name).read_bytes()
    return hashlib.sha256(data).hexdigest()


def _edit(repo, ticket, name):
    target = repo / ".work" / "tickets" / ticket / name
    target.write_text(target.read_text(encoding="utf-8") + "\n", encoding="utf-8")


def test_list_then_confirm_records_each_with_own_hashes(repo, capsys):
    _tickets(repo, "T-1", "T-2")

    first = _say(capsys, repo, "/crew:approve T-1 T-2")
    before = (_receipt(repo, "T-1"), _receipt(repo, "T-2"))
    code, out, _ = _say(capsys, repo, "/crew:approve --confirm", prompt_id="p-2")
    got = [(r["approved_via"], r["session_id"], r["prompt_id"], r["plan_sha256"],
            r["spec_sha256"]) for r in (_receipt(repo, "T-1"), _receipt(repo, "T-2"))]

    assert (first[0], "PENDING" in first[2], before) == (2, True, (None, None))
    assert (code, "approved T-1, T-2" in _context(out)) == (0, True)
    assert got == [("user-prompt", "sess-1", "p-2", _sha(repo, t, "plan.md"),
                    _sha(repo, t, "spec.md")) for t in ("T-1", "T-2")]


def test_the_pending_message_names_each_ticket_and_its_hashes(repo, capsys):
    _tickets(repo, "T-1", "T-2", "T-3")

    code, _, err = _say(capsys, repo, "/crew:approve T-1..T-3")

    assert code == 2
    for ticket in ("T-1", "T-2", "T-3"):
        line = (f"crew: approval PENDING, nothing recorded yet -- {ticket} plan "
                f"{_sha(repo, ticket, 'plan.md')[:12]} spec {_sha(repo, ticket, 'spec.md')[:12]}")
        assert line in err.splitlines(), line
    assert "/crew:approve --confirm" in err.splitlines()[-1]


def test_range_then_confirm(repo, capsys):
    _tickets(repo, "T-0001", "T-0002", "T-0003")

    _say(capsys, repo, "/crew:approve T-0001..T-0003")
    code, _, _ = _say(capsys, repo, "/crew:approve --confirm")

    assert (code, [bool(_receipt(repo, t)) for t in ("T-0001", "T-0002", "T-0003")]) == \
        (0, [True, True, True])


@pytest.mark.parametrize("text", ["approve T-1 and T-2", "please approve T-1 through T-2.",
                                  "approve T-1,T-2"])
def test_plain_text_then_confirm(repo, capsys, text):
    _tickets(repo, "T-1", "T-2")

    first = _say(capsys, repo, text)
    code, _, _ = _say(capsys, repo, "/crew:approve --confirm")

    assert (first[0], code, bool(_receipt(repo, "T-1")), bool(_receipt(repo, "T-2"))) == \
        (2, 0, True, True)


def test_plain_text_for_one_ticket_still_goes_pending(repo, capsys):
    _tickets(repo, "T-1")

    code, _, err = _say(capsys, repo, "approve T-1")

    assert (code, "PENDING" in err, _receipt(repo, "T-1"), len(_pending(repo))) == \
        (2, True, None, 1)


def test_second_request_replaces_pending(repo, capsys):
    _tickets(repo, "T-1", "T-2", "T-3")

    _say(capsys, repo, "/crew:approve T-1 T-2")
    _say(capsys, repo, "/crew:approve T-2 T-3")
    code, _, _ = _say(capsys, repo, "/crew:approve --confirm")

    assert (code, [bool(_receipt(repo, t)) for t in ("T-1", "T-2", "T-3")]) == \
        (0, [False, True, True])


def test_a_single_approval_clears_the_pending_list(repo, capsys):
    _tickets(repo, "T-1", "T-2", "T-3")

    _say(capsys, repo, "/crew:approve T-1 T-2")
    single = _say(capsys, repo, "/crew:approve T-3")
    code, _, err = _say(capsys, repo, "/crew:approve --confirm")

    assert (single[0], code, "no pending" in err, _receipt(repo, "T-1")) == (0, 2, True, None)


@pytest.mark.parametrize("text", ["yes", "y", "confirm", "does the reviewer approve T-1?",
                                  "hello"])
def test_an_unrelated_prompt_leaves_pending_untouched(repo, capsys, text):
    _tickets(repo, "T-1", "T-2")
    _say(capsys, repo, "/crew:approve T-1 T-2")
    before = [p.read_bytes() for p in _pending(repo)]

    code, out, err = _say(capsys, repo, text)

    assert (code, out, err, [p.read_bytes() for p in _pending(repo)]) == (0, "", "", before)
    assert (_receipt(repo, "T-1"), _receipt(repo, "T-2")) == (None, None)


# --- must-block: exit 2, no receipt, no pending left behind ----------------------------

def _nothing(repo, *ids):
    return all(_receipt(repo, t) is None for t in ids) and _pending(repo) == []


@pytest.mark.parametrize("text", ["/crew:approve T-1\n/crew:approve T-2",
                                  "/crew:approve T-1 T-2\nthanks",
                                  "approve T-1 and T-2\nthanks"])
def test_a_multiline_paste_blocks_and_leaves_nothing(repo, capsys, text):
    _tickets(repo, "T-1", "T-2")
    _say(capsys, repo, "/crew:approve T-1 T-2")

    code, _, err = _say(capsys, repo, text)

    assert (code, "one line" in err, _nothing(repo, "T-1", "T-2")) == (2, True, True)


def test_range_with_invalid_ticket_refuses_all_and_names_it(repo, capsys):
    _tickets(repo, "T-1", "T-3")
    make_ticket(repo, "T-2", files=["other/keep.py"], activate=False)

    code, _, err = _say(capsys, repo, "/crew:approve T-1..T-3")

    assert (code, "1 of 3" in err, "T-2:" in err, "T-1:" in err) == (2, True, True, False)
    assert ("nothing is recorded or pending" in err, _nothing(repo, "T-1", "T-2", "T-3")) == \
        (True, True)


def test_range_naming_every_failure(repo, capsys):
    _tickets(repo, "T-1")
    make_ticket(repo, "T-2", files=["other/keep.py"], activate=False)

    code, _, err = _say(capsys, repo, "/crew:approve T-1 T-2 T-3")

    assert (code, "2 of 3" in err, "T-2:" in err, "T-3:" in err) == (2, True, True, True)


def test_range_with_missing_folder_refuses_all(repo, capsys):
    _tickets(repo, "T-1", "T-3")

    code, _, err = _say(capsys, repo, "/crew:approve T-1..T-3")

    assert (code, "T-2: no ticket folder" in err, _nothing(repo, "T-1", "T-3")) == \
        (2, True, True)


def test_range_with_closed_ticket_refuses_all(repo, capsys):
    _tickets(repo, "T-1", "T-2", "T-3")
    (repo / ".work" / "INDEX.md").write_text("| T-2 | done | x |\n", encoding="utf-8")

    code, _, err = _say(capsys, repo, "approve T-1 through T-3")

    assert (code, "closed in .work/INDEX.md" in err, _nothing(repo, "T-1", "T-2", "T-3")) == \
        (2, True, True)


def test_a_failed_group_request_clears_an_earlier_pending_list(repo, capsys):
    _tickets(repo, "T-1", "T-2")
    _say(capsys, repo, "/crew:approve T-1 T-2")

    code, _, _ = _say(capsys, repo, "/crew:approve T-1 T-9")

    assert (code, _nothing(repo, "T-1", "T-2")) == (2, True)


def test_confirm_without_pending_refuses(repo, capsys):
    code, _, err = _say(capsys, repo, "/crew:approve --confirm")

    assert (code, "no pending group approval" in err) == (2, True)


@pytest.mark.parametrize("name", ["spec.md", "plan.md"])
def test_confirm_after_spec_changed_records_none(repo, capsys, name):
    _tickets(repo, "T-1", "T-2")
    _say(capsys, repo, "/crew:approve T-1 T-2")
    _edit(repo, "T-2", name)

    code, _, err = _say(capsys, repo, "/crew:approve --confirm")

    assert (code, f"T-2: {name} changed" in err, "T-1:" in err) == (2, True, False)
    assert _nothing(repo, "T-1", "T-2")


def test_confirm_after_plan_changed_records_none(repo, capsys):
    _tickets(repo, "T-1", "T-2")
    _say(capsys, repo, "/crew:approve T-1 T-2")
    _edit(repo, "T-1", "plan.md")

    code, _, err = _say(capsys, repo, "/crew:approve --confirm")

    assert (code, "T-1: plan.md changed" in err, _nothing(repo, "T-1", "T-2")) == \
        (2, True, True)


def test_confirm_after_a_ticket_became_invalid_records_none(repo, capsys):
    _tickets(repo, "T-1", "T-2")
    _say(capsys, repo, "/crew:approve T-1 T-2")
    (repo / ".work" / "INDEX.md").write_text("| T-1 | merged | x |\n", encoding="utf-8")

    code, _, err = _say(capsys, repo, "/crew:approve --confirm")

    assert (code, "T-1:" in err, _nothing(repo, "T-1", "T-2")) == (2, True, True)


def test_confirm_other_session_refuses(repo, capsys):
    _tickets(repo, "T-1", "T-2")
    _say(capsys, repo, "/crew:approve T-1 T-2", session="sess-1")

    code, _, err = _say(capsys, repo, "/crew:approve --confirm", session="sess-2")

    assert (code, "another session" in err, _nothing(repo, "T-1", "T-2")) == (2, True, True)


@pytest.mark.parametrize("session", [None, "", 7])
def test_a_group_request_without_a_session_is_refused(repo, capsys, session):
    _tickets(repo, "T-1", "T-2")

    code, _, err = _say(capsys, repo, "/crew:approve T-1 T-2", session=session)

    assert (code, "session" in err, _nothing(repo, "T-1", "T-2")) == (2, True, True)


@pytest.mark.parametrize("offset,ok", [(approval_hook.PENDING_TTL + 1, False),
                                       (approval_hook.PENDING_TTL - 5, True),
                                       (-120, False)])
def test_confirm_after_ttl_refuses(repo, capsys, monkeypatch, offset, ok):
    _tickets(repo, "T-1", "T-2")
    _say(capsys, repo, "/crew:approve T-1 T-2")
    now = approval_hook.time.time()
    monkeypatch.setattr(approval_hook.time, "time", lambda: now + offset)

    code, _, err = _say(capsys, repo, "/crew:approve --confirm")

    assert (code, bool(_receipt(repo, "T-1"))) == ((0, True) if ok else (2, False)), err
    assert _pending(repo) == []


@pytest.mark.parametrize("text", ["/crew:approve --confirm T-1", "/crew:approve --confirm now",
                                  "/crew:approve --confirm\nyes"])
def test_confirm_with_extra_text_refuses(repo, capsys, text):
    _tickets(repo, "T-1", "T-2")
    _say(capsys, repo, "/crew:approve T-1 T-2")

    code, _, _ = _say(capsys, repo, text)

    assert (code, _nothing(repo, "T-1", "T-2")) == (2, True)


def test_refused_confirm_deletes_pending(repo, capsys):
    _tickets(repo, "T-1", "T-2")
    _say(capsys, repo, "/crew:approve T-1 T-2", session="sess-1")
    _say(capsys, repo, "/crew:approve --confirm", session="sess-2")

    code, _, err = _say(capsys, repo, "/crew:approve --confirm", session="sess-1")

    assert (code, "no pending group approval" in err, _nothing(repo, "T-1", "T-2")) == \
        (2, True, True)


def test_a_confirm_is_single_use(repo, capsys):
    _tickets(repo, "T-1", "T-2")
    _say(capsys, repo, "/crew:approve T-1 T-2")
    _say(capsys, repo, "/crew:approve --confirm")

    code, _, err = _say(capsys, repo, "/crew:approve --confirm")

    assert (code, "no pending group approval" in err, _pending(repo)) == (2, True, [])


@pytest.mark.parametrize("mangle", [
    lambda d: "{",
    lambda d: json.dumps([d]),
    lambda d: json.dumps(dict(d, items=[])),
    lambda d: json.dumps(dict(d, items=[{"ticket": "T-1"}])),
    lambda d: json.dumps(dict(d, created_at="soon")),
    lambda d: json.dumps(dict(d, worktree="/somewhere/else")),
    lambda d: json.dumps({k: v for k, v in d.items() if k != "session_id"}),
], ids=["truncated", "array", "no-items", "item-without-hashes", "bad-time",
        "other-worktree", "no-session"])
def test_an_unusable_pending_list_refuses_and_is_deleted(repo, capsys, mangle):
    _tickets(repo, "T-1", "T-2")
    _say(capsys, repo, "/crew:approve T-1 T-2")
    path = _pending(repo)[0]
    path.write_text(mangle(json.loads(path.read_text(encoding="utf-8"))), encoding="utf-8")

    code, _, _ = _say(capsys, repo, "/crew:approve --confirm")

    assert (code, _nothing(repo, "T-1", "T-2")) == (2, True)


def test_a_write_failing_part_way_names_recorded_and_not_recorded(repo, capsys, monkeypatch):
    _tickets(repo, "T-1", "T-2", "T-3")
    _say(capsys, repo, "/crew:approve T-1 T-2 T-3")
    real = crew_ticket.approve

    def fail_on_t2(root, ticket, **kwargs):
        if ticket == "T-2":
            raise crew_ticket.TicketError("disk full")
        return real(root, ticket, **kwargs)

    monkeypatch.setattr(crew_ticket, "approve", fail_on_t2)

    code, _, err = _say(capsys, repo, "/crew:approve --confirm")

    assert (code, "recorded: T-1" in err, "NOT recorded: T-2, T-3" in err, "disk full" in err) \
        == (2, True, True, True)
    assert (bool(_receipt(repo, "T-1")), _receipt(repo, "T-3"), _pending(repo)) == \
        (True, None, [])


def test_the_confirm_passes_the_pending_hashes_to_approve(repo, capsys, monkeypatch):
    _tickets(repo, "T-1", "T-2")
    _say(capsys, repo, "/crew:approve T-1 T-2")
    seen = []
    real = crew_ticket.approve

    def spy(root, ticket, **kwargs):
        seen.append((ticket, kwargs.get("expect")))
        return real(root, ticket, **kwargs)

    monkeypatch.setattr(crew_ticket, "approve", spy)

    _say(capsys, repo, "/crew:approve --confirm")

    assert seen == [(t, (_sha(repo, t, "plan.md"), _sha(repo, t, "spec.md")))
                    for t in ("T-1", "T-2")]


def test_an_edit_between_check_and_write_is_refused_by_expect(repo, capsys, monkeypatch):
    _tickets(repo, "T-1", "T-2")
    _say(capsys, repo, "/crew:approve T-1 T-2")
    real = crew_ticket.precheck
    checked = []

    def check_then_edit(root, ticket):
        result = real(root, ticket)
        checked.append(ticket)
        if checked == ["T-1", "T-2"]:
            _edit(repo, "T-2", "spec.md")
        return result

    monkeypatch.setattr(crew_ticket, "precheck", check_then_edit)

    code, _, err = _say(capsys, repo, "/crew:approve --confirm")

    assert (code, "NOT recorded: T-2" in err, _receipt(repo, "T-2")) == (2, True, None)


def test_a_range_token_that_is_a_folder_blocks_the_prompt(repo, capsys):
    _tickets(repo, "T-1", "T-2", "T-1..T-2")

    code, _, err = _say(capsys, repo, "/crew:approve T-1..T-2")

    assert (code, "ambiguous" in err, _nothing(repo, "T-1", "T-2", "T-1..T-2")) == \
        (2, True, True)


def test_a_group_request_outside_git_is_refused_plainly(tmp_path, capsys):
    code, _, err = _say(capsys, tmp_path, "/crew:approve T-1 T-2")

    assert (code, err) == (2, f"crew: /crew:approve was NOT recorded -- {tmp_path} is not a "
                              "git repository\n")


def test_a_confirm_outside_git_is_refused(tmp_path, capsys):
    code, _, err = _say(capsys, tmp_path, "/crew:approve --confirm")

    assert (code, "not a git repository" in err) == (2, True)


def test_a_long_range_token_is_not_mistaken_for_a_folder(repo):
    token = "A" * 40 + "-1.." + "A" * 40 + "-2"

    request = approval_hook.parse(f"/crew:approve {token}", str(repo))

    assert (request.kind, request.ids) == (GROUP, ("A" * 40 + "-1", "A" * 40 + "-2"))


# --- NEEDS_REPLAN parity -------------------------------------------------------------

def _needs_replan(tmp_path, name, new_plan):
    import review_ledger as rl  # pylint: disable=import-outside-toplevel
    from scope_fixtures import approve_as_user  # pylint: disable=import-outside-toplevel
    root = make_repo(tmp_path, mode="block", name=name)
    make_ticket(root)
    approve_as_user(root)
    for _ in range(3):
        rl.reserve(str(root), "T-1", "codex")
    assert rl.status(str(root), "T-1")["state"] == rl.NEEDS_REPLAN
    if new_plan:
        (root / ".work" / "tickets" / "T-1" / "plan.md").write_text(
            "## Step 1\nFiles: src/app.py\nTest: new\nRisk: new\n", encoding="utf-8")
    return root


def _ledger_shape(root):
    import review_ledger as rl  # pylint: disable=import-outside-toplevel
    status = rl.status(str(root), "T-1")
    return status["state"], [(s["plan_sha256"], s["after_round"]) for s in status["successors"]]


@pytest.mark.parametrize("new_plan", [True, False], ids=["new-plan", "same-plan"])
def test_group_successor_matches_single(tmp_path, capsys, new_plan):
    single = _needs_replan(tmp_path, "single", new_plan)
    group = _needs_replan(tmp_path, "group", new_plan)
    capsys.readouterr()

    _, single_out, _ = _say(capsys, single, "/crew:approve T-1")
    _say(capsys, group, "approve T-1")
    _, group_out, _ = _say(capsys, group, "/crew:approve --confirm")
    single_text, group_text = _context(single_out), _context(group_out)

    assert _ledger_shape(single) == _ledger_shape(group)
    assert _ledger_shape(single)[0] == ("IN_REVIEW" if new_plan else "NEEDS_REPLAN")
    assert single_text[single_text.index(" Review "):] == \
        group_text[group_text.index(" Review "):]


# --- step 5: the sabotage anchors ------------------------------------------------------

def test_every_approval_sabotage_anchor_is_present_exactly_once():
    import sabotage  # pylint: disable=import-outside-toplevel
    import sabotage_approval  # pylint: disable=import-outside-toplevel
    import sabotage_scope  # pylint: disable=import-outside-toplevel
    hook_files = (sabotage_scope.HOOK, sabotage_scope.HOOK_SH)
    rows = list(sabotage_approval.APPROVAL_MUTATIONS) + [
        m for m in sabotage_scope.SCOPE_MUTATIONS if m[1] in hook_files]

    for label, target, find, _replace, test in rows:
        with open(target, encoding="utf-8") as handle:
            assert handle.read().count(find) == 1, label
        assert test.split("::")[0] in ("tests/test_approval_group.py",
                                       "tests/test_approval_hook.py",
                                       "tests/test_crew_ticket.py"), label
    assert len(rows) >= len(sabotage_approval.APPROVAL_MUTATIONS) + 4
    assert all(m in sabotage.MUTATIONS for m in sabotage_approval.APPROVAL_MUTATIONS)

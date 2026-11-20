"""The owner-typed run approval (crew 1.3.161): `crew_runapproval.py`, the
`/crew:allow-run` branch of `approval_hook.py`, the release and the store
protection in `scope_guard.py`, and `verify_trust.py --receipt`.

A receipt lets an agent run ONE command the guards keep for the owner. So the
suite is mostly must-block: every way a session could give itself a receipt or
stretch one it was given.

MUST-BLOCK
- default off: with no `approvals.run.classes` nothing is recorded, minted or
  spent, and the refusal reads as it did before; a repo file, a HOME inside the
  repo, a duplicate key or a malformed value never turns it on;
- minting: a bare command with exactly one request pending, a mistyped id, two
  ids, a multi-line prompt, an event that is not UserPromptSubmit, a prompt
  from another session (a child `claude -p`), from another worktree, an expired
  or future-dated request, a request answered twice, a hand-made request file,
  a verify.json edited after the request;
- using: a spent receipt (guard and tool), a receipt for another command text,
  other arguments, another worktree, another class, an expired or future-dated
  receipt, a verb the owner did not open, a verify.json edited after the
  receipt, a forged or unknown id, two spenders at once;
- the stores, WHILE A CLASS IS ON: a shell command naming the store, in full
  or through a glob or an unexpanded variable beside it, a Write/Edit under
  it, a command carrying `/crew:allow-run` with an id (a child `claude -p`, a
  piped payload, keys sent to a terminal), code run beside the module, a
  command naming the prompt hook or starting Claude on an existing session:
  all in `scope.mode: off` too, and a store check that raises refuses there;
- line breaks: an id, a word or a command followed by one is not the plain
  form, gets no request and spends nothing.

MUST-ALLOW
- the owner's exact prompt, raw and expanded, then one spend inside the window;
- `status` and `check`, a read of the store (a globbed one too), a commit
  message or grep that only mentions the command, a glob or a variable that
  is nowhere near the store, every shape the trust suite already allows;
- with NO class on (the default), every one of the store refusals above: a
  guard nobody turned on refuses nothing, and a fault in it is never reached.
"""
import importlib.util
import json
import os
import pathlib
import re
import tempfile
import threading

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import approval_hook
import crew_hook
import crew_runapproval as ra
import scope_guard
import verify_trust
from scope_fixtures import FLAVOURS, SCRIPTS, make_repo, prompt, run_hook

TRUST = os.path.join(SCRIPTS, "verify_trust.py").replace("\\", "/")
APPROVE = f"python3 {TRUST} approve --root ."
SESSION = "sess-1"
_ID = re.compile(r"ar-[0-9a-f]{12}")
OLD_REFUSAL = 2  # the two lines the trust refusal has always printed


def _home():
    return pathlib.Path(os.path.expanduser("~"))


def turn_on(classes=("verify-trust",), **run):
    """Write the MACHINE config (the isolated home) with the route on."""
    path = _home() / ".claude" / "crew" / "config.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"approvals": {"run": dict(run, classes=list(classes))}}),
                    encoding="utf-8")
    return path


def store(kind=None):
    base = _home() / ".claude" / "crew" / "run-approvals"
    return base / kind if kind else base


def records(kind):
    folder = store(kind)
    return sorted(p.name for p in folder.iterdir()) if folder.is_dir() else []


def audit_events():
    log = store() / "audit.log"
    if not log.is_file():
        return []
    return [json.loads(line)["event"] for line in log.read_text(encoding="utf-8").splitlines()]


def trusted():
    """The repos the (isolated) verify trust store holds an approval for."""
    return verify_trust.load_store(os.environ[verify_trust.ENV_STORE])["repos"]


@pytest.fixture(name="repo")
def _repo(tmp_path, monkeypatch):
    """A git repo in `scope.mode: off` with a verify map to approve. The
    process stands in it, as the tool's shell does."""
    root = make_repo(tmp_path, mode="off")
    (root / ".crew" / "verify.json").write_text('{"rules": []}\n', encoding="utf-8")
    monkeypatch.chdir(root)
    monkeypatch.setenv("CLAUDECODE", "1")
    monkeypatch.delenv("CREW_TEST_TRUST_ALL", raising=False)
    return root


def shell(root, command, session=SESSION, tool="Bash"):
    return {"tool_name": tool, "cwd": str(root), "session_id": session,
            "tool_input": {"command": command}}


def guard(capsys, payload):
    """(exit code, stderr) of scope_guard for one payload, in process."""
    capsys.readouterr()
    code = scope_guard.decide(payload)
    return code, capsys.readouterr().err


def typed(root, text, session=SESSION, event="UserPromptSubmit"):
    payload = prompt(root, text, session=session)
    payload["hook_event_name"] = event
    return approval_hook.handle(payload)


def ask(capsys, root, command=APPROVE, session=SESSION):
    """Run `command` through the guard and return the request id it printed."""
    code, err = guard(capsys, shell(root, command, session))
    found = _ID.search(err)
    assert code == 2 and found, err
    return found.group(0)


def receipt_for(capsys, root, command=APPROVE):
    """A request raised and answered by the owner: the receipt id."""
    ident = ask(capsys, root, command)
    assert typed(root, f"/crew:allow-run {ident}") == 0
    return ident


def tool(*argv):
    return verify_trust.main(list(argv))


# --- default off -------------------------------------------------------------------

def test_with_the_class_off_the_refusal_is_unchanged_and_nothing_is_recorded(repo, capsys):
    code, err = guard(capsys, shell(repo, APPROVE))

    assert (code, len(err.splitlines()), "ar-" in err, store().exists()) == \
        (2, OLD_REFUSAL, False, False)


def test_with_the_class_off_the_owners_command_mints_nothing(repo, capsys):
    turn_on()
    ident = ask(capsys, repo)
    turn_on(classes=())

    assert (typed(repo, f"/crew:allow-run {ident}"), records("receipts")) == (2, [])


def test_with_the_class_off_a_receipt_spends_nothing(repo, capsys):
    turn_on()
    ident = receipt_for(capsys, repo)
    turn_on(classes=())

    assert (tool("approve", "--root", ".", "--receipt", ident), trusted()) == (1, {})


@pytest.mark.parametrize("text", [
    '{"approvals": {"run": {"classes": "verify-trust"}}}',
    '{"approvals": {"run": {"classes": [1]}}}',
    '{"approvals": {"run": {"classes": ["verify-trust"]}, "run": {}}}',
    '{"approvals": {"run": {"classes": []}, "run": {"classes": ["verify-trust"]}}}',
    '{"approvals": {"run": {"classes": ["promote-human"]}}}',
    '{"approvals": ["verify-trust"]}',
    "not json",
], ids=["string", "number", "duplicate-run", "duplicate-run-on-last", "unknown-class",
        "list", "corrupt"])
def test_a_machine_config_that_does_not_say_so_plainly_is_off(repo, text):
    turn_on().write_text(text, encoding="utf-8")

    assert ra.settings(str(repo))["classes"] == frozenset()


def test_the_repo_config_file_cannot_turn_the_class_on(repo, capsys):
    (repo / ".crew" / "config.json").write_text(
        json.dumps({"scope": {"mode": "off"},
                    "approvals": {"run": {"classes": ["verify-trust"]}}}), encoding="utf-8")

    code, err = guard(capsys, shell(repo, APPROVE))

    assert (code, "ar-" in err, ra.settings(str(repo))["classes"]) == (2, False, frozenset())


def test_a_home_inside_the_repo_turns_nothing_on(repo, monkeypatch):
    fake = repo / "home"
    for name in ("HOME", "USERPROFILE"):
        monkeypatch.setenv(name, str(fake))
    turn_on()

    assert ra.settings(str(repo))["classes"] == frozenset()
    with pytest.raises(ra.Refused):
        ra.store_dir(str(repo))


@pytest.mark.parametrize("run,expected", [
    ({}, (900, ("approve",))),
    ({"ttlSeconds": 120}, (120, ("approve",))),
    ({"ttlSeconds": 59}, (900, ("approve",))),
    ({"ttlSeconds": 3601}, (900, ("approve",))),
    ({"ttlSeconds": True}, (900, ("approve",))),
    ({"verbs": {"verifyTrust": ["approve", "revoke"]}}, (900, ("approve", "revoke"))),
    ({"verbs": {"verifyTrust": ["approve", "delete-everything"]}}, (900, ("approve",))),
    ({"verbs": {"verifyTrust": "revoke"}}, (900, ("approve",))),
])
def test_ttl_and_verbs_fall_back_to_their_defaults(repo, run, expected):
    turn_on(**run)
    got = ra.settings(str(repo))

    assert (got["ttl"], got["verbs"]) == expected


# --- must-allow: the whole route ---------------------------------------------------

def test_the_owners_typed_id_lets_the_exact_command_run_once(repo, capsys):
    turn_on()
    code, err = guard(capsys, shell(repo, APPROVE))
    ident = _ID.search(err).group(0)

    minted = typed(repo, f"/crew:allow-run {ident}")
    released, _ = guard(capsys, shell(repo, f"{APPROVE} --receipt {ident}"))
    ran = tool("approve", "--root", ".", "--receipt", ident)

    assert (code, f"{APPROVE} --receipt {ident}" in err, minted, released, ran,
            len(trusted()), records("receipts"), audit_events()) == \
        (2, True, 0, 0, 0, 1, [], ["requested", "minted", "spent"])


def test_the_owner_is_shown_the_command_the_receipt_covers(repo, capsys):
    turn_on()
    ident = ask(capsys, repo)
    capsys.readouterr()

    typed(repo, f"/crew:allow-run {ident}")
    out = json.loads(capsys.readouterr().out)

    assert APPROVE in out["systemMessage"] and \
        out["systemMessage"] == out["hookSpecificOutput"]["additionalContext"]


def test_the_expanded_command_form_mints_too(repo, capsys):
    turn_on()
    ident = ask(capsys, repo)
    text = ("<command-message>crew:allow-run is running</command-message>\n"
            f"<command-name>/crew:allow-run</command-name>\n<command-args>{ident}</command-args>")

    assert (typed(repo, text), records("receipts")) == (0, [ident + ".json"])


def test_the_same_command_asked_twice_is_one_request(repo, capsys):
    turn_on()

    assert ask(capsys, repo) == ask(capsys, repo) and len(records("requests")) == 1


def test_a_verb_the_owner_opened_runs_with_its_receipt(repo, capsys):
    turn_on()
    tool("approve", "--root", ".", "--receipt", receipt_for(capsys, repo))
    turn_on(verbs={"verifyTrust": ["approve", "revoke"]})
    revoke = f"python3 {TRUST} revoke --root ."

    ident = receipt_for(capsys, repo, revoke)
    released, _ = guard(capsys, shell(repo, f"{revoke} --receipt {ident}"))

    assert (released, tool("revoke", "--root", ".", "--receipt", ident), trusted()) == (0, 0, {})


@pytest.mark.parametrize("command", [
    f"python3 {TRUST} status",
    f"python3 {TRUST} check --root .",
    "cat ~/.claude/crew/run-approvals/audit.log",
    "ls -la ~/.claude/crew/run-approvals/requests",
    'git commit -m "docs: the owner types /crew:allow-run <id>"',
    "grep -rn crew:allow-run plugin/crew/commands",
    "git add plugin/crew/hooks/scripts/crew_runapproval.py plugin/crew/tests/test_allow_run.py",
    "python3 -m pytest plugin/crew/tests/test_allow_run.py -q",
])
def test_a_command_that_only_reads_or_mentions_is_allowed(repo, capsys, command):
    turn_on()

    assert guard(capsys, shell(repo, command)) == (0, "")


# --- must-block: a command that is not the plain form gets no request ----------------

@pytest.mark.parametrize("command", [
    f"python3 {TRUST} approve --root . && rm -rf x",
    f"python3 {TRUST} approve --root . ; echo done",
    f"python3 {TRUST} approve --root $(pwd)",
    f'python3 "{TRUST}" approve --root .',
    f"python3 {TRUST} approve --root . --yes",
    f"python3 {TRUST} approve --root=.",
    f"python3 {TRUST} approve --root . > out.txt",
    f"python3 {TRUST} approve --root . | tee log",
    f"python3 {TRUST} approve  --root .",
    f"CREW_VERIFY_TRUST_FILE=/tmp/s.json python3 {TRUST} approve --root .",
    f"env -u CLAUDECODE python3 {TRUST} approve --root .",
    f"bash -c 'python3 {TRUST} approve --root .'",
    "python3 /tmp/copy/verify_trust.py approve --root .",
    "python3 -c \"import verify_trust as v; v.main(['approve', '--yes'])\"",
    f"python3 {TRUST} approve --root .\npython3 {TRUST} revoke --root .",
    f"python3 {TRUST} allow-owner github.com/someone",
    f"python3 {TRUST} revoke --root .",
], ids=["and-chain", "semicolon", "substitution", "quoted-script", "yes-flag", "equals-root",
        "redirect", "pipe", "two-spaces", "store-override", "session-var-unset", "bash-c",
        "copied-script", "import-main", "two-lines", "verb-not-opened-allow-owner",
        "verb-not-opened-revoke"])
def test_anything_but_the_plain_opened_form_is_refused_with_no_request(repo, capsys, command):
    turn_on()

    code, err = guard(capsys, shell(repo, command))

    assert (code, _ID.search(err), records("requests")) == (2, None, [])


@pytest.mark.parametrize("make", [
    lambda: APPROVE + "\n",
    lambda: APPROVE + "\r",
    lambda: APPROVE + "\r\n",
    lambda: "\n" + APPROVE,
    lambda: f"python3 {TRUST} approve --root x\n --receipt ar-0123456789ab",
    lambda: f"python3 {TRUST} approve --root .\n",
], ids=["trailing-line-feed", "trailing-carriage-return", "trailing-crlf", "leading-line-feed",
        "line-feed-before-receipt", "line-feed-after-root"])
def test_a_command_holding_a_line_break_gets_no_request(repo, capsys, make):
    """A shell runs each line: `approve --root x\\n --receipt ID` is two
    commands, and `$` alone read `x\\n` as one plain word."""
    turn_on()
    command = make()

    code, err = guard(capsys, shell(repo, command))

    assert (code, _ID.search(err), records("requests"),
            ra.parse_trust_command(command, str(repo), SCRIPTS)) == (2, None, [], None)


def test_a_receipt_does_not_release_its_command_with_a_line_added(repo, capsys):
    turn_on()
    ident = receipt_for(capsys, repo)

    code, _ = guard(capsys, shell(repo, f"{APPROVE} --receipt {ident}\nrm -rf x"))

    assert (code, records("receipts")) == (2, [ident + ".json"])


@pytest.mark.parametrize("ident", ["ar-0123456789ab\n", "ar-0123456789ab\r", "ar-0123456789ab\r\n",
                                   "\nar-0123456789ab", "ar-0123456789ab "],
                         ids=["line-feed", "carriage-return", "crlf", "leading", "space"])
def test_an_id_with_a_line_break_is_not_an_id(repo, ident):
    turn_on()

    assert (ra.valid_id(ident), tool("approve", "--root", ".", "--receipt", ident),
            trusted()) == (False, 1, {})


@pytest.mark.parametrize("pattern,text", [
    ("_ID_RE", "ar-0123456789ab\n"),
    ("_OWNER_RE", "github.com/someone\n"),
    ("_PYTHON_RE", "python3\n"),
    ("_PLAIN_RE", "x\n"),
])
def test_no_pattern_reads_a_trailing_line_feed_as_the_end(pattern, text):
    whole = ra._whole  # pylint: disable=protected-access

    assert (whole(getattr(ra, pattern), text), whole(getattr(ra, pattern), text[:-1])) == (False, True)


def test_a_separator_glued_to_a_word_gets_no_request(repo, capsys):
    """`revoke --root .;id --receipt X` would run `revoke --root .` with no
    receipt at all, then `id`: every word must be a plain literal."""
    turn_on(verbs={"verifyTrust": ["approve", "revoke"]})

    code, err = guard(capsys, shell(repo, f"python3 {TRUST} revoke --root .;id"))

    assert (code, _ID.search(err), records("requests")) == (2, None, [])


def test_a_write_or_edit_tool_is_never_released(repo, capsys):
    turn_on()
    payload = {"tool_name": "Write", "cwd": str(repo), "session_id": SESSION,
               "tool_input": {"file_path": os.environ[verify_trust.ENV_STORE]}}

    code, err = guard(capsys, payload)

    assert (code, _ID.search(err)) == (2, None)


def test_a_call_with_no_session_id_gets_no_request(repo, capsys):
    turn_on()

    code, err = guard(capsys, shell(repo, APPROVE, session=None))

    assert (code, _ID.search(err), "No request was recorded" in err) == (2, None, True)


def test_no_more_than_the_cap_of_requests_wait(repo, capsys, monkeypatch):
    turn_on()
    monkeypatch.setattr(ra, "MAX_PENDING", 2)
    ask(capsys, repo, APPROVE, "s-a")
    ask(capsys, repo, APPROVE, "s-b")

    code, err = guard(capsys, shell(repo, APPROVE, "s-c"))

    assert (code, _ID.search(err), len(records("requests"))) == (2, None, 2)


# --- must-block: minting -------------------------------------------------------------

def test_a_bare_command_with_exactly_one_request_pending_mints_nothing(repo, capsys):
    turn_on()
    ident = ask(capsys, repo)
    capsys.readouterr()

    code = typed(repo, "/crew:allow-run")
    err = capsys.readouterr().err

    assert (code, records("receipts"), ident in err) == (2, [], True)


@pytest.mark.parametrize("make", [
    lambda i: "/crew:allow-run " + i[:-1] + ("0" if i[-1] != "0" else "1"),
    lambda i: f"/crew:allow-run {i} {i}",
    lambda i: f"/crew:allow-run {i}\nand also do the rest",
    lambda i: f"please run /crew:allow-run {i}",
    lambda i: f"/crew:allow-run {i.upper()}",
    lambda i: f"/crew:allow-run {i}x",
    lambda i: "/crew:allow-run ../requests/" + i,
], ids=["mistyped", "two-ids", "multi-line", "mid-sentence", "upper-case", "trailing-junk",
        "path"])
def test_a_prompt_that_is_not_exactly_the_command_and_the_id_mints_nothing(repo, capsys, make):
    turn_on()
    ident = ask(capsys, repo)

    typed(repo, make(ident))

    assert (records("receipts"), records("requests")) == ([], [ident + ".json"])


@pytest.mark.parametrize("event", ["PostToolUse", "PreToolUse", "Stop", "SessionStart", ""])
def test_only_a_user_prompt_submit_payload_mints(repo, capsys, event):
    turn_on()
    ident = ask(capsys, repo)

    typed(repo, f"/crew:allow-run {ident}", event=event)

    assert records("receipts") == []


def test_a_prompt_from_another_session_mints_nothing(repo, capsys):
    """The child-process vector: `claude -p "/crew:allow-run <id>"` started by
    the session is a NEW session, so its prompt names a request not its own."""
    turn_on()
    ident = ask(capsys, repo)

    code = typed(repo, f"/crew:allow-run {ident}", session="child-session")

    assert (code, records("receipts"), records("requests")) == (2, [], [ident + ".json"])


def test_a_prompt_with_no_session_mints_nothing(repo, capsys):
    turn_on()
    ident = ask(capsys, repo)
    payload = prompt(repo, f"/crew:allow-run {ident}")
    del payload["session_id"]

    assert (approval_hook.handle(payload), records("receipts")) == (2, [])


def test_an_id_from_another_repo_mints_nothing(repo, capsys, tmp_path):
    turn_on()
    ident = ask(capsys, repo)
    other = make_repo(tmp_path, mode="off", name="other")

    assert (typed(other, f"/crew:allow-run {ident}"), records("receipts")) == (2, [])


@pytest.mark.parametrize("shift", [ra.REQUEST_TTL + 1, -5], ids=["expired", "future-dated"])
def test_a_request_outside_its_window_mints_nothing(repo, capsys, shift):
    turn_on()
    ident = ask(capsys, repo)
    path = store("requests") / (ident + ".json")
    record = json.loads(path.read_text(encoding="utf-8"))
    record["created"] -= shift
    record["expires"] -= shift
    path.write_text(json.dumps(record), encoding="utf-8")

    assert (typed(repo, f"/crew:allow-run {ident}"), records("receipts")) == (2, [])


def test_a_request_is_answered_once(repo, capsys):
    turn_on()
    ident = receipt_for(capsys, repo)
    tool("approve", "--root", ".", "--receipt", ident)

    assert (typed(repo, f"/crew:allow-run {ident}"), records("receipts")) == (2, [])


def test_an_unknown_id_mints_nothing(repo, capsys):
    turn_on()
    ask(capsys, repo)

    assert (typed(repo, "/crew:allow-run ar-0123456789ab"), records("receipts")) == (2, [])


@pytest.mark.parametrize("content", ["", "{}", "[]", '{"id": "ar-0123456789ab"}'],
                         ids=["touched-marker", "empty-object", "list", "id-only"])
def test_a_hand_made_request_file_mints_nothing(repo, content):
    turn_on()
    folder = store("requests")
    folder.mkdir(parents=True)
    (folder / "ar-0123456789ab.json").write_text(content, encoding="utf-8")

    assert (typed(repo, "/crew:allow-run ar-0123456789ab"), records("receipts")) == (2, [])


def test_a_verify_json_edited_after_the_request_mints_nothing(repo, capsys):
    turn_on()
    ident = ask(capsys, repo)
    (repo / ".crew" / "verify.json").write_text('{"rules": [{"run": ["rm -rf /"]}]}\n',
                                                 encoding="utf-8")

    assert (typed(repo, f"/crew:allow-run {ident}"), records("receipts")) == (2, [])


# --- must-block: using a receipt -----------------------------------------------------

def test_a_spent_receipt_is_refused_by_the_guard_and_by_the_tool(repo, capsys):
    turn_on()
    ident = receipt_for(capsys, repo)
    assert tool("approve", "--root", ".", "--receipt", ident) == 0
    tool("revoke", "--root", ".")

    code, err = guard(capsys, shell(repo, f"{APPROVE} --receipt {ident}"))

    assert (code, "receipt was refused" in err,
            tool("approve", "--root", ".", "--receipt", ident), trusted()) == (2, True, 1, {})


def test_a_receipt_for_one_command_does_not_release_another(repo, capsys, tmp_path):
    turn_on()
    ident = receipt_for(capsys, repo)
    other = make_repo(tmp_path, mode="off", name="other")
    (other / ".crew" / "verify.json").write_text('{"rules": []}\n', encoding="utf-8")

    for command in (f"python3 {TRUST} approve --root ../other --receipt {ident}",
                    f"python3 -B {TRUST} approve --root . --receipt {ident}",
                    f"python3 {TRUST} revoke --root . --receipt {ident}"):
        code, err = guard(capsys, shell(repo, command))
        assert (code, "receipt was refused" in err or _ID.search(err) is None) == (2, True), err
    assert records("receipts") == [ident + ".json"]


def test_the_tool_refuses_other_arguments_and_the_receipt_is_gone(repo, capsys, tmp_path):
    turn_on()
    ident = receipt_for(capsys, repo)
    other = make_repo(tmp_path, mode="off", name="other")
    (other / ".crew" / "verify.json").write_text('{"rules": []}\n', encoding="utf-8")

    first = tool("approve", "--root", str(other), "--receipt", ident)
    second = tool("approve", "--root", ".", "--receipt", ident)

    assert (first, second, trusted(), records("receipts"), audit_events()[-1]) == \
        (1, 1, {}, [], "spend-refused")


def test_a_receipt_is_refused_in_another_worktree(repo, capsys, tmp_path, monkeypatch):
    turn_on()
    ident = receipt_for(capsys, repo)
    other = make_repo(tmp_path, mode="off", name="other")
    (other / ".crew" / "verify.json").write_text('{"rules": []}\n', encoding="utf-8")

    code, err = guard(capsys, shell(other, f"{APPROVE} --receipt {ident}"))
    monkeypatch.chdir(other)

    assert (code, "another worktree" in err,
            tool("approve", "--root", str(repo), "--receipt", ident), trusted()) == \
        (2, True, 1, {})


def test_a_receipt_is_refused_for_another_class(repo, capsys, monkeypatch):
    turn_on()
    ident = receipt_for(capsys, repo)
    monkeypatch.setattr(ra, "CLASSES", ("verify-trust", "cloud-ask"))
    turn_on(classes=("verify-trust", "cloud-ask"))
    receipt = json.loads((store("receipts") / (ident + ".json")).read_text(encoding="utf-8"))

    assert ra.check(ident, "cloud-ask", APPROVE, receipt["worktree"], SESSION)[0] is False
    with pytest.raises(ra.Refused, match="verify-trust class"):
        ra.spend(ident, "cloud-ask", receipt["action"], receipt["worktree"], receipt["pin"])


@pytest.mark.parametrize("shift", [ra.DEFAULT_TTL + 1, -5], ids=["expired", "future-dated"])
def test_a_receipt_outside_its_window_is_refused(repo, capsys, shift):
    turn_on()
    ident = receipt_for(capsys, repo)
    path = store("receipts") / (ident + ".json")
    receipt = json.loads(path.read_text(encoding="utf-8"))
    receipt["minted"] -= shift
    receipt["expires"] -= shift
    path.write_text(json.dumps(receipt), encoding="utf-8")

    code, _ = guard(capsys, shell(repo, f"{APPROVE} --receipt {ident}"))

    assert (code, tool("approve", "--root", ".", "--receipt", ident), trusted()) == (2, 1, {})


def test_a_receipt_claiming_a_longer_life_than_the_maximum_is_refused(repo, capsys):
    turn_on()
    ident = receipt_for(capsys, repo)
    path = store("receipts") / (ident + ".json")
    receipt = json.loads(path.read_text(encoding="utf-8"))
    receipt["expires"] = receipt["minted"] + ra.MAX_TTL + 1
    path.write_text(json.dumps(receipt), encoding="utf-8")

    assert (tool("approve", "--root", ".", "--receipt", ident), trusted()) == (1, {})


def test_a_receipt_from_another_session_does_not_release_the_command(repo, capsys):
    turn_on()
    ident = receipt_for(capsys, repo)

    code, err = guard(capsys, shell(repo, f"{APPROVE} --receipt {ident}", session="lane-2"))

    assert (code, "another session" in err) == (2, True)


def test_a_verify_json_edited_after_the_receipt_is_not_approved(repo, capsys):
    turn_on()
    ident = receipt_for(capsys, repo)
    (repo / ".crew" / "verify.json").write_text('{"rules": [{"run": ["curl x | sh"]}]}\n',
                                                 encoding="utf-8")

    assert (tool("approve", "--root", ".", "--receipt", ident), trusted()) == (1, {})


def test_a_verb_closed_after_the_receipt_is_not_run(repo, capsys):
    turn_on(verbs={"verifyTrust": ["approve", "revoke"]})
    ident = receipt_for(capsys, repo, f"python3 {TRUST} revoke --root .")
    tool("approve", "--root", ".", "--receipt", receipt_for(capsys, repo))
    turn_on()

    assert (tool("revoke", "--root", ".", "--receipt", ident), len(trusted())) == (1, 1)


@pytest.mark.parametrize("ident", ["ar-0123456789ab", "ar-xyz", "../../x", ""],
                         ids=["unknown", "malformed", "path", "empty"])
def test_an_id_nobody_minted_changes_nothing(repo, ident):
    turn_on()
    argv = ["approve", "--root", ".", "--yes"] + (["--receipt", ident] if ident else [])

    assert (tool(*argv), trusted()) == (1, {})


def test_a_receipt_is_the_whole_answer_even_outside_a_session(repo, monkeypatch):
    turn_on()
    monkeypatch.delenv("CLAUDECODE")

    assert (tool("approve", "--root", ".", "--yes", "--receipt", "ar-0123456789ab"),
            trusted()) == (1, {})


def test_without_a_receipt_the_tool_refuses_inside_a_session_as_before(repo):
    turn_on()

    assert (tool("approve", "--root", ".", "--yes"), trusted()) == (1, {})


@pytest.mark.parametrize("content", ["", "{}", '{"id": "ar-0123456789ab", "class": "verify-trust"}'],
                         ids=["touched-marker", "empty-object", "partial"])
def test_a_hand_made_receipt_file_missing_a_binding_spends_nothing(repo, content):
    turn_on()
    folder = store("receipts")
    folder.mkdir(parents=True)
    (folder / "ar-0123456789ab.json").write_text(content, encoding="utf-8")

    assert (tool("approve", "--root", ".", "--receipt", "ar-0123456789ab"), trusted()) == (1, {})


def test_of_two_spenders_at_once_exactly_one_wins(repo, capsys):
    turn_on()
    ident = receipt_for(capsys, repo)
    receipt = json.loads((store("receipts") / (ident + ".json")).read_text(encoding="utf-8"))
    won, gate = [], threading.Barrier(8)

    def attempt():
        gate.wait()
        try:
            ra.spend(ident, ra.CLASS_TRUST, receipt["action"], receipt["worktree"],
                     receipt["pin"], root=str(repo))
            won.append(1)
        except ra.Refused:
            pass

    threads = [threading.Thread(target=attempt) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert len(won) == 1


# --- must-block: the stores, in every scope mode --------------------------------------

_STORE = "~/.claude/crew/run-approvals"


@pytest.mark.parametrize("tool_name,command", [
    ("Bash", f"echo '{{}}' > {_STORE}/receipts/ar-0123456789ab.json"),
    ("Bash", f"touch {_STORE}/receipts/ar-0123456789ab.json"),
    ("Bash", f"cp /tmp/r.json {_STORE}/receipts/ar-0123456789ab.json"),
    ("Bash", f"mv {_STORE}/requests/ar-0123456789ab.json {_STORE}/receipts/"),
    ("Bash", f"python3 -c \"open('{_STORE}/receipts/x.json', 'w').write('{{}}')\""),
    ("Bash", f"git -C {_STORE} checkout -- ."),
    ("Bash", f"cd {_STORE} && git init"),
    ("Bash", "tee ~/.claude/crew/run-appro''vals/receipts/x.json < r.json"),
    ("Bash", "touch ~/.claude/crew/run-app\\\nrovals/receipts/x.json"),
    ("Bash", f"rm -rf {_STORE}"),
    ("PowerShell", "Set-Content $HOME\\.claude\\crew\\run-approvals\\receipts\\x.json '{}'"),
    ("PowerShell", "New-Item -ItemType File $HOME/.claude/crew/run-approvals/receipts/x.json"),
    ("Bash", f"cat {_STORE}/audit.log > copy.txt"),
], ids=["redirect", "touch-marker", "cp", "mv-request-to-receipt", "python-c", "git-checkout",
        "git-init", "quotes-in-name", "continuation-in-name", "rm", "ps-set-content",
        "ps-new-item", "read-with-redirect"])
def test_a_shell_command_naming_the_store_is_refused_with_the_guard_off(repo, capsys, tool_name,
                                                                         command):
    turn_on()

    code, err = guard(capsys, shell(repo, command, tool=tool_name))

    assert (code, "run-approval store" in err) == (2, True)


_CREW = "~/.claude/crew"


@pytest.mark.parametrize("tool_name,command", [
    ("Bash", f"echo x > {_CREW}/run-*/receipts/a.json"),
    ("Bash", f"touch {_CREW}/run-appro[v]als/receipts/a.json"),
    ("Bash", f"touch {_CREW}/run-approva?s/receipts/a.json"),
    ("Bash", f"d={_CREW}/run; touch ${{d}}-approvals/receipts/a.json"),
    ("Bash", "d=run; touch $HOME/.claude/crew/$d-approvals/receipts/a.json"),
    ("Bash", f"touch {_CREW}/$(echo run)-approvals/receipts/a.json"),
    ("Bash", f"touch {_CREW}/`echo run`-approvals/receipts/a.json"),
    ("Bash", f"touch {_CREW}/*/receipts/a.json"),
    ("Bash", f"rm -rf {_CREW}/*"),
    ("Bash", f"rm -rf {_CREW}/r*"),
    ("Bash", f"cp r.json {_CREW}/{{run,x}}-approvals/receipts/"),
    ("Bash", f"touch {_CREW}/run-+(approvals)/receipts/a.json"),
    ("Bash", f"touch {_CREW}/r'u'n-*/receipts/a.json"),
    ("Bash", f"touch {_CREW}/x/../run-*/a.json"),
    ("Bash", f"d={_CREW}; touch $d/$n/a.json"),
    ("Bash", f"cd {_CREW} && rm -rf *"),
    ("Bash", "touch $X/receipts/ar-0123456789ab.json"),
    ("Bash", "cp r.json */requests/"),
    ("Bash", "touch *-approvals/receipts/a.json"),
    ("PowerShell", "Set-Content $HOME\\.claude\\crew\\run-*\\receipts\\x.json '{}'"),
    ("PowerShell", "Set-Content $env:USERPROFILE\\.claude\\crew\\$name\\receipts\\x.json '{}'"),
    ("PowerShell", "Remove-Item -Recurse %USERPROFILE%\\.claude\\crew\\run-app*"),
    ("Bash", f"cat {_CREW}/run-*/audit.log > copy.txt"),
], ids=["star", "bracket", "question-mark", "braced-variable", "bare-variable", "substitution",
        "backticks", "whole-segment-star", "crew-dir-star", "one-letter-star", "brace-list",
        "extended-glob", "quotes-in-glob", "dot-dot", "variable-beside-crew-dir", "cd-then-star",
        "variable-before-receipts", "star-before-requests", "star-approvals",
        "ps-star", "ps-variable-segment", "cmd-variable", "globbed-read-with-redirect"])
def test_a_shell_command_veiling_the_store_name_is_refused_with_the_guard_off(repo, capsys,
                                                                             tool_name, command):
    """The store's name need not be spelled: a glob or a variable the shell
    fills in reaches it. Unknown beside the store is read as the store."""
    turn_on()

    code, err = guard(capsys, shell(repo, command, tool=tool_name))

    assert (code, "run-approval store" in err) == (2, True)


@pytest.mark.parametrize("cwd,command", [
    (".claude/crew", "rm -rf *"),
    (".claude/crew", "touch r*/receipts/a.json"),
    (".claude", "rm -rf crew/*"),
    ("", "rm -rf .claude/crew/*"),
], ids=["in-crew-dir", "in-crew-dir-child", "in-claude-dir", "in-home"])
def test_a_relative_glob_is_read_from_the_directory_the_command_runs_in(repo, capsys, cwd, command):
    turn_on()
    payload = shell(repo, command)
    payload["cwd"] = str(_home() / cwd)

    code, err = guard(capsys, payload)

    assert (code, "run-approval store" in err) == (2, True)


@pytest.mark.parametrize("tool_name,command", [
    ("Bash", f"cat {_CREW}/run-*/audit.log"),
    ("Bash", f"ls -la {_CREW}/*"),
    ("Bash", f"mkdir -p {_CREW}"),
    ("Bash", "rm -rf build/*"),
    ("Bash", "rm -f *.pyc"),
    ("Bash", "rm plugin/crew/r*"),
    ("Bash", "git add plugin/crew/*"),
    ("Bash", "git add .claude-plugin/marketplace.json plugin/crew/*"),
    ("Bash", "cp $SRC/$NAME $DST"),
    ("Bash", "echo $HOME > out.txt"),
    ("Bash", "for f in *.md; do wc -l $f >> counts.txt; done"),
    ("Bash", "touch src/receipts/a.json"),
    ("PowerShell", "Remove-Item $a\\$b\\$c"),
    ("PowerShell", "Get-ChildItem *.py | ForEach-Object { $_.Name } | Set-Content names.txt"),
], ids=["globbed-read", "globbed-ls", "mkdir-crew-dir", "build-star", "pyc", "plugin-crew-r-star",
        "git-add-plugin-crew", "marketplace-and-plugin-crew", "variables", "home-redirect",
        "for-loop", "receipts-elsewhere", "ps-variables", "ps-pipeline"])
def test_a_glob_or_a_variable_nowhere_near_the_store_is_allowed(repo, capsys, tool_name, command):
    turn_on()

    assert guard(capsys, shell(repo, command, tool=tool_name)) == (0, "")


@pytest.mark.parametrize("tool_name,command", [
    ("Bash", "claude -p --resume 5f1c < prompt.txt"),
    ("Bash", "cat prompt.txt | claude --print -r 5f1c"),
    ("Bash", "claude -c -p < prompt.txt"),
    ("Bash", "claude --continue --print < prompt.txt"),
    ("Bash", "claude -p --session-id 5f1c0000-0000-4000-8000-000000000000 < prompt.txt"),
    ("Bash", "claude -p --fork-session --resume 5f1c < prompt.txt"),
    ("Bash", "claude -p '--res''ume' 5f1c < prompt.txt"),
    ("Bash", "claude -p $FLAGS < prompt.txt"),
    ("Bash", "npx @anthropic-ai/claude-code -p --resume=5f1c < prompt.txt"),
    ("PowerShell", "Get-Content prompt.txt | claude.exe -p --resume 5f1c"),
], ids=["resume-stdin", "short-r", "short-c", "continue", "session-id", "fork", "quotes-in-flag",
        "flags-in-a-variable", "npx", "powershell"])
def test_with_a_class_on_claude_started_on_an_existing_session_is_refused_with_the_guard_off(
        repo, capsys, tool_name, command):
    """Measured on claude 2.1.326: the prompt hook of `claude -p --resume
    <sid>` is handed <sid>, so the session binding does not tell that child
    from the owner. The prompt is in a file; the text shows only the flag."""
    turn_on()

    code, err = guard(capsys, shell(repo, command, tool=tool_name))

    assert (code, "existing session" in err) == (2, True)


@pytest.mark.parametrize("command", [
    "claude -p 'summarise the diff'",
    "claude --version",
    "git log --oneline -r -c | head",
    "ls ~/.claude/projects",
], ids=["new-session", "version", "flags-of-another-command", "claude-dir"])
def test_with_a_class_on_claude_started_fresh_is_allowed(repo, capsys, command):
    turn_on()

    assert guard(capsys, shell(repo, command)) == (0, "")


def _through_main(monkeypatch, capsys, payload):
    """(exit code, stderr) of `scope_guard.main` for one payload: the level
    at which an exception inside `decide` is allowed under warn and off."""
    monkeypatch.setattr(scope_guard, "_read_payload", lambda: payload)
    capsys.readouterr()
    return scope_guard.main(), capsys.readouterr().err


def _broken(*_args, **_kwargs):
    raise RuntimeError("forced")


@pytest.mark.parametrize("payload", [
    lambda root: shell(root, "touch notes.txt"),
    lambda root: shell(root, "Set-Content notes.txt x", tool="PowerShell"),
    lambda root: {"tool_name": "Write", "cwd": str(root), "tool_input": {"file_path": "notes.txt"}},
    lambda root: {"tool_name": "Edit", "cwd": str(root), "tool_input": {"file_path": "notes.txt"}},
], ids=["bash", "powershell", "write", "edit"])
def test_a_store_check_that_raises_refuses_the_call_with_the_guard_off(repo, capsys, monkeypatch,
                                                                       payload):
    """`main` allows a call `decide` could not judge when `scope.mode` is off
    or report. The store check is not one of those: it fails closed."""
    turn_on()
    monkeypatch.setattr(ra, "store_refusal", _broken)

    code, err = _through_main(monkeypatch, capsys, payload(repo))

    assert (code, "could not judge it (RuntimeError)" in err) == (2, True)


def test_a_store_check_that_raises_inside_the_module_refuses_too(repo, capsys, monkeypatch):
    turn_on()
    monkeypatch.setattr(ra, "_shell_reason", _broken)

    code, err = _through_main(monkeypatch, capsys, shell(repo, "touch notes.txt"))

    assert (code, "could not judge it (RuntimeError)" in err) == (2, True)


def test_with_the_class_off_a_broken_store_check_is_never_reached(repo, capsys, monkeypatch):
    """The setting is read before a word of the call: a fault in a check
    nobody turned on refuses nothing."""
    monkeypatch.setattr(ra, "_shell_reason", _broken)
    monkeypatch.setattr(ra, "_targets", _broken)

    assert _through_main(monkeypatch, capsys, shell(repo, "touch notes.txt")) == (0, "")
    assert _through_main(monkeypatch, capsys, {
        "tool_name": "Write", "cwd": str(repo), "tool_input": {"file_path": "notes.txt"}}) == (0, "")


def test_a_store_check_that_raises_still_lets_a_plain_read_through(repo, capsys, monkeypatch):
    turn_on()
    monkeypatch.setattr(ra, "store_refusal", _broken)

    assert _through_main(monkeypatch, capsys, shell(repo, "ls -la")) == (0, "")


@pytest.mark.parametrize("tool_name", ["Write", "Edit", "MultiEdit", "NotebookEdit"])
@pytest.mark.parametrize("tail", ["receipts/ar-0123456789ab.json", "requests/ar-0123456789ab.json",
                                  "audit.log"])
def test_a_write_or_edit_under_the_store_is_refused_with_the_guard_off(repo, capsys, tool_name,
                                                                       tail):
    turn_on()
    target = str(store() / tail)
    key = "notebook_path" if tool_name == "NotebookEdit" else "file_path"
    tool_input = {"edits": [{"file_path": target}]} if tool_name == "MultiEdit" else {key: target}

    code, err = guard(capsys, {"tool_name": tool_name, "cwd": str(repo), "tool_input": tool_input})

    assert (code, "run-approval store" in err) == (2, True)


def test_a_write_under_a_store_in_another_home_is_refused(repo, capsys, tmp_path):
    turn_on()
    target = str(tmp_path / "elsewhere" / ".claude" / "crew" / "run-approvals" / "receipts" / "x.json")

    code, _ = guard(capsys, {"tool_name": "Write", "cwd": str(repo),
                             "tool_input": {"file_path": target}})

    assert code == 2


@pytest.mark.parametrize("tool_name,command", [
    ("Bash", 'claude -p "/crew:allow-run ar-0123456789ab"'),
    ("Bash", "claude --resume 5f1c -p '/crew:allow-run ar-0123456789ab'"),
    ("Bash", 'claude -p "/crew:allow-run $ID"'),
    ("Bash", "ID=ar-0123456789ab; claude --print \"/crew:allow-run `echo $ID`\""),
    ("Bash", "echo '{\"hook_event_name\": \"UserPromptSubmit\", \"prompt\": "
             "\"/crew:allow-run ar-0123456789ab\"}' | python3 hooks/scripts/approval_hook.py"),
    ("Bash", "tmux send-keys -t owner '/crew:allow-run ar-0123456789ab' Enter"),
    ("Bash", "printf '/crew:allow-run ar-0123456789ab\\n' | claude"),
    ("PowerShell", "claude -p \"/crew:allow-run ar-0123456789ab\""),
    ("Bash", "claude -p '/crew:allow''-run ar-0123456789ab'"),
    ("Bash", "claude -p '<command-name>/crew:allow-run</command-name>"
             "<command-args>ar-0123456789ab</command-args>'"),
], ids=["claude-p", "claude-resume", "variable-id", "backtick-id", "piped-payload", "tmux-keys",
        "stdin-prompt", "powershell", "quotes-in-command", "expanded-form"])
def test_a_command_carrying_the_owners_command_and_an_id_is_refused(repo, capsys, tool_name,
                                                                    command):
    turn_on()

    code, err = guard(capsys, shell(repo, command, tool=tool_name))

    assert (code, "only the owner types" in err) == (2, True)


@pytest.mark.parametrize("command", [
    "python3 -c \"import crew_runapproval as r; r.mint('ar-0123456789ab', 's', 'p', '.')\"",
    "python3 -m crew_runapproval",
    "PYTHONPATH=plugin/crew/hooks/scripts python -c 'from crew_runapproval import _write'",
    "py -3 plugin/crew/hooks/scripts/crew_runapproval.py",
], ids=["import-mint", "dash-m", "from-import", "run-as-script"])
def test_code_run_beside_the_module_is_refused(repo, capsys, command):
    turn_on()

    code, err = guard(capsys, shell(repo, command))

    assert (code, "crew_runapproval" in err) == (2, True)


_HOOK_COMMANDS = ["python3 plugin/crew/hooks/scripts/approval_hook.py < payload.json",
                  "bash plugin/crew/hooks/scripts/crew-hook.sh UserPromptSubmit claude < payload.json",
                  "cat payload.json | python3 hooks/scripts/crew_hook.py UserPromptSubmit"]


@pytest.mark.parametrize("command", _HOOK_COMMANDS, ids=["approval-hook", "launcher", "dispatcher"])
def test_with_a_class_on_a_command_naming_the_prompt_hook_is_refused_with_the_guard_off(
        repo, capsys, command):
    turn_on()

    code, err = guard(capsys, shell(repo, command))

    assert (code, "prompt hook" in err) == (2, True)


@pytest.mark.parametrize("command", _HOOK_COMMANDS, ids=["approval-hook", "launcher", "dispatcher"])
def test_with_the_class_off_the_guard_off_repo_is_as_it_was(repo, capsys, command):
    assert guard(capsys, shell(repo, command)) == (0, "")


# --- must-allow: with no class on, none of the store refusals is judged ---------------

@pytest.mark.parametrize("tool_name,command", [
    ("Bash", "rm -rf run-*"),
    ("Bash", f"rm -rf {_CREW}/tmp-*"),
    ("Bash", f"d={_CREW}; ls $d > listing.txt"),
    ("Bash", f"cp $SRC {_CREW}/config.json.bak"),
    ("Bash", f"cd {_CREW} && rm -rf *"),
    ("Bash", "git commit -m 'docs: the run-approvals store and /crew:allow-run ar-0123456789ab'"),
    ("Bash", "git commit -m \"docs: /crew:allow-run costs $5\""),
    ("Bash", "python3 -m pylint plugin/crew/hooks/scripts/crew_runapproval.py"),
    ("Bash", "python3 -m pytest plugin/crew/tests/test_allow_run.py > run-approvals.log"),
    ("Bash", f"touch {_STORE}/receipts/ar-0123456789ab.json"),
    ("Bash", 'claude -p "/crew:allow-run $ID"'),
    ("Bash", "claude -p --resume 5f1c < prompt.txt"),
    ("PowerShell", "Remove-Item -Recurse $env:USERPROFILE\\.claude\\crew\\run-*"),
    ("PowerShell", "Set-Content $HOME\\.claude\\crew\\notes.txt $text"),
], ids=["bare-run-star", "crew-dir-glob", "crew-dir-variable", "variable-to-crew-dir",
        "cd-then-star", "commit-message", "commit-message-dollar", "pylint-the-module",
        "log-named-like-the-store", "store-named", "owner-command-variable", "claude-resume",
        "ps-glob", "ps-variable"])
def test_with_the_class_off_no_store_refusal_applies(repo, capsys, tool_name, command):
    """A guard nobody turned on refuses nothing: with `approvals.run.classes`
    empty no receipt is honoured, so there is no store to protect, and every
    command reads as it did before this module existed."""
    assert guard(capsys, shell(repo, command, tool=tool_name)) == (0, "")


@pytest.mark.parametrize("tool_name", ["Write", "Edit"])
def test_with_the_class_off_a_write_under_the_store_is_as_it_was(repo, capsys, tool_name):
    target = str(store() / "receipts" / "ar-0123456789ab.json")

    assert guard(capsys, {"tool_name": tool_name, "cwd": str(repo),
                          "tool_input": {"file_path": target}}) == (0, "")


def test_a_receipt_written_by_hand_cannot_claim_more_than_an_hour(repo, capsys):
    """What the class-off allowance leaves open, and the one bound on it: a
    forged receipt's window is MAX_TTL wide at most. WHEN it opens is the
    forger's choice (CONFIG.md says so), which no test here can close."""
    turn_on()
    ident = receipt_for(capsys, repo)
    path = store("receipts") / f"{ident}.json"
    forged = json.loads(path.read_text(encoding="utf-8"))
    forged["expires"] = forged["minted"] + ra.MAX_TTL + 1
    path.write_text(json.dumps(forged), encoding="utf-8")

    code, err = guard(capsys, shell(repo, f"{APPROVE} --receipt {ident}"))

    assert (code, "not one the owner's prompt wrote" in err) == (2, True)


def _forged_request(capsys, repo, **changes):
    """A real request, rewritten in place the way a session with a shell could."""
    ident = ask(capsys, repo)
    path = store("requests") / f"{ident}.json"
    record = json.loads(path.read_text(encoding="utf-8"))
    record.update(changes)
    path.write_text(json.dumps(record), encoding="utf-8")
    return ident


def test_a_request_showing_one_command_and_carrying_the_sha_of_another_mints_nothing(repo, capsys):
    """The owner is shown `command`; the guard releases `command_sha256`."""
    turn_on()
    ident = _forged_request(capsys, repo, command=f"python3 {TRUST} approve --root ./docs")

    assert typed(repo, f"/crew:allow-run {ident}") == 2
    assert "not a record crew wrote" in capsys.readouterr().err
    assert records("receipts") == []


def test_a_request_claiming_a_longer_life_than_its_window_mints_nothing(repo, capsys):
    turn_on()
    ident = _forged_request(capsys, repo)
    path = store("requests") / f"{ident}.json"
    record = json.loads(path.read_text(encoding="utf-8"))
    record["expires"] = record["created"] + ra.REQUEST_TTL + 1
    path.write_text(json.dumps(record), encoding="utf-8")

    assert typed(repo, f"/crew:allow-run {ident}") == 2
    assert records("receipts") == []


def test_a_receipt_showing_one_command_and_carrying_the_sha_of_another_releases_nothing(repo, capsys):
    turn_on()
    ident = receipt_for(capsys, repo)
    path = store("receipts") / f"{ident}.json"
    forged = json.loads(path.read_text(encoding="utf-8"))
    forged["command"] = f"python3 {TRUST} approve --root ./docs"
    path.write_text(json.dumps(forged), encoding="utf-8")

    code, err = guard(capsys, shell(repo, f"{APPROVE} --receipt {ident}"))

    assert (code, "not one the owner's prompt wrote" in err) == (2, True)


def test_a_machine_config_nested_too_deep_to_parse_is_off_and_refuses_nothing(repo, capsys):
    """`settings` never raises: a file `json` cannot walk is "off", not a
    store check that could not judge the call."""
    path = turn_on()
    path.write_text("[" * 100000 + "]" * 100000, encoding="utf-8")

    assert ra.settings(str(repo))["classes"] == frozenset()
    assert guard(capsys, shell(repo, "rm -rf run-*")) == (0, "")


# --- the wrappers reach the hook for a prompt with no `approve` in it ---------------

def test_the_dispatchers_pre_filter_lets_the_owners_command_through():
    wanted = crew_hook._approval_wanted  # pylint: disable=protected-access

    assert (wanted(b'{"prompt": "/crew:allow-run ar-0123456789ab"}'),
            wanted(b'{"prompt": "hello there"}')) == (True, False)


@pytest.mark.parametrize("flavour", FLAVOURS)
def test_the_owners_prompt_mints_through_each_hook_flavour(flavour, repo, capsys):
    turn_on()
    ident = ask(capsys, repo)

    code, out, _ = run_hook(flavour, "approval_hook", prompt(repo, f"/crew:allow-run {ident}"),
                            repo)

    assert (code, records("receipts"), ident in out) == (0, [ident + ".json"], True)


@pytest.mark.parametrize("flavour", FLAVOURS)
def test_a_refused_trust_command_prints_its_request_through_each_guard_flavour(flavour, repo):
    turn_on()

    code, _, err = run_hook(flavour, "scope_guard", shell(repo, APPROVE), repo)

    assert (code, bool(_ID.search(err)), len(records("requests"))) == (2, True, 1)


def test_a_payload_that_is_not_json_but_names_the_command_blocks_the_prompt(repo):
    code, _, err = run_hook("module", "approval_hook", b"/crew:allow-run ar-0123456789ab", repo)

    assert (code, "NOT recorded" in err) == (2, True)


# --- the plain form, word by word ----------------------------------------------------

@pytest.mark.parametrize("command,verb", [
    (f"python3 {TRUST} approve", "approve"),
    (f"python {TRUST} approve --root .", "approve"),
    (f"py -B {TRUST} revoke --root sub/dir", "revoke"),
    (f"python3.12 {TRUST} allow-owner GitHub.com/Someone --under . --under ..", "allow-owner"),
    (f"python3 {TRUST} disallow-owner github.com/someone", "disallow-owner"),
    (f"python3 {TRUST} approve --root . --receipt ar-0123456789ab", "approve"),
])
def test_the_plain_form_parses_to_its_action(repo, command, verb):
    action, _ident, base = ra.parse_trust_command(command, str(repo), SCRIPTS)

    assert (action["verb"], command.startswith(base)) == (verb, True)


@pytest.mark.parametrize("command", [
    f"python3 {TRUST} approve --receipt ar-0123456789ab --root .",
    f"python3 {TRUST} approve --root . --receipt",
    f"python3 {TRUST} approve --root . --receipt nope",
    f"python3 {TRUST} approve --root . --root ..",
    f"python3 {TRUST} approve extra",
    f"python3 {TRUST} allow-owner",
    f"python3 {TRUST} allow-owner not-an-owner",
    f"python3 {TRUST} disallow-owner github.com/someone --under .",
    f"python3 {TRUST} allow-owner github.com/someone --under",
    f"ruby {TRUST} approve",
    f"python3 -u {TRUST} approve",
    f"python3 {TRUST} status",
    "python3 verify_trust.py approve",
    "",
])
def test_anything_else_is_not_the_plain_form(repo, command):
    assert ra.parse_trust_command(command, str(repo), SCRIPTS) is None


def test_the_action_is_the_same_from_the_text_and_from_the_arguments(repo, monkeypatch):
    monkeypatch.chdir(repo)
    parsed = ra.parse_trust_command(f"python3 {TRUST} allow-owner GitHub.com/Me --under .",
                                    str(repo), SCRIPTS)[0]

    assert parsed == ra.trust_action("allow-owner", owner="github.com/me", under=["."])


# --- the harness rule knows the module -------------------------------------------------

def _checker():
    path = pathlib.Path(context._ROOT).parents[1] / "scripts" / "check-tooling-pr.py"  # pylint: disable=protected-access
    spec = importlib.util.spec_from_file_location("check_tooling_pr_allow_run", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_module_is_harness_and_lands_with_the_hook():
    code, _ = _checker().judge(["plugin/crew/hooks/scripts/crew_runapproval.py",
                                "plugin/crew/hooks/scripts/approval_hook.py",
                                "plugin/crew/tests/test_allow_run.py"], set())

    assert code == 0


def test_the_module_changed_beside_feature_code_is_refused():
    code, _ = _checker().judge(["plugin/crew/hooks/scripts/crew_runapproval.py",
                                "plugin/crew/hooks/scripts/cloud_guard.py"], set())

    assert code == 1


# --- R-20: the store tripwire stops refusing everyday commands ------------------------
#
# Every row runs with a class ON. A must-allow row is a recorded over-refusal (O1-O17
# of the R-20 spec, section 2) or a neighbour of one; a must-block row is a shape the
# excuses do not recognise and must keep refusing, and is also checked with the class
# OFF, where it must pass: that pins the refusal on the store tripwire and nothing else.
# Ids are the ones the R-20 sabotage rows (`sabotage_runapproval.py`) name.

_S = "plugin/crew/hooks/scripts"
_B = "~/.claude/crew/forged/a.json"
_C = "~\\.claude\\crew\\forged\\a.json"
_TAIL = " && git log -1 --oneline | cut -d ' ' -f 2- | bash"
_TOUCH = "touch ~/.claude/crew/run-approvals/receipts/a"
_PS_TOUCH = "ni ~/.claude/crew/run-approvals/receipts/a"

_R20_ALLOW = [
    # O1-O17, verbatim (section 2 of the spec)
    ("O1", "Bash", "python3 -m pytest plugin/crew/tests/test_approval_hook.py -q"),
    ("O2", "Bash", f"git add {_S}/crew_hook.py"),
    ("O3", "Bash", f"git add {_S}/approval_hook.py plugin/crew/CHANGELOG.md"),
    ("O4", "Bash", "git commit -m 'fix(crew): approval_hook reads the prompt id'"),
    ("O5", "Bash", f"python3 -m pylint {_S}/crew_hook.py"),
    ("O6", "Bash", f"sed -i 's/a/b/' {_S}/approval_hook.py"),
    ("O7", "PowerShell", f"git add {_S}/approval_hook.py"),
    ("O8", "Bash", "git commit -m 'docs: the run-approvals store'"),
    ("O9", "Bash", "python3 -m pytest plugin/crew/tests/test_allow_run.py > run-approvals.log"),
    ("O10", "Bash", f"python3 -m ruff check {_S}/crew_runapproval.py"),
    ("O11", "Bash", "claude -p 'summarise' --output-format json | jq -r .result"),
    ("O12", "Bash", "claude --version && rm -rf build"),
    ("O13", "Bash", "claude mcp list | head -c 200"),
    ("O14", "Bash", "claude -p 'summarise the diff' > $OUT"),
    ("O15", "Bash", "rm -rf run-*"),
    ("O16", "Bash", "rm -rf /tmp/run-*"),
    ("O17", "Bash", "cp $SRC ~/.claude/crew/config.json.bak"),
    ("bare-run-star", "Bash", "rm -rf run-*"),
    # the prompt hook and the module (D2, D3)
    ("hook-diff-then-add", "Bash", f"git diff --stat -- {_S}/approval_hook.py && git add -A"),
    ("pytest-k", "Bash", "python3 -m pytest plugin/crew/tests/test_crew_hook.py -k dispatch"),
    ("git-log-hook", "Bash", f"git log --oneline -- {_S}/approval_hook.py"),
    ("git-diff-dispatcher", "Bash", f"git diff -- {_S}/crew_hook.py"),
    ("rg-hook", "Bash", "rg -n approval_hook plugin/crew/hooks/hooks.json"),
    ("ps-get-content-hook", "PowerShell", f"Get-Content {_S}/crew_hook.py"),
    ("shellcheck-launcher", "Bash", f"shellcheck {_S}/crew-hook.sh"),
    ("pipe-table", "Bash", f"git diff | python3 -m pylint --from-stdin {_S}/crew_hook.py"),
    ("commit-import-word", "Bash", "git commit -m 'import crew_runapproval lazily in scope_guard'"),
    # the store's name (D4)
    ("gh-pr-create", "Bash", "gh pr create --title 'crew: run-approvals tripwire' --body 'see /crew:allow-run'"),
    ("commit-separators", "Bash", "git commit -m 'a; b | c'"),
    ("store-read-table", "Bash", "git grep -n run-approvals -- plugin/crew"),
    ("git-log-grep-store", "Bash", "git log --oneline --grep=run-approvals"),
    ("rg-store", "Bash", "rg -n run-approvals plugin/crew"),
    ("ps-select-string-store", "PowerShell", "Select-String -Path plugin/crew/CONFIG.md -Pattern run-approvals"),
    ("msg-add-then-commit", "Bash", "git add -A && git commit -m 'fix: approval_hook reads the prompt id'"),
    ("add-hook-then-commit-hook", "Bash",
     f"git add {_S}/approval_hook.py && git commit -m 'fix: approval_hook reads the prompt id'"),
    ("msg-commit-then-log", "Bash", "git commit -m 'docs: the run-approvals store' && git log -1 --oneline"),
    ("msg-separators-in-message", "Bash", "git commit -m 'a; b | c run-approvals'"),
    ("gh-pr-comment", "Bash", "gh pr comment 1 --body 'see run-approvals'"),
    ("tag-message", "Bash", "git tag -a v1 -m 'run-approvals tripwire'"),
    ("msg-add-commit-status", "Bash",
     "git add -A && git commit -m 'docs: the run-approvals store' && git status"),
    # review round 2: a flag's value word is consumed with its flag, so `--` there is a value
    ("msg-label-double-dash", "Bash", "gh pr create --label '--' --title 'run-approvals'"),
    ("msg-ps-label-double-dash", "PowerShell", "gh pr create --label '--' --title 'run-approvals'"),
    ("msg-commit-message-double-dash", "Bash", "git commit -m '--' -m 'run-approvals'"),
    # Claude started fresh (D5)
    ("claude-stream-json", "Bash", "claude -p 'x' --output-format stream-json | tee out.jsonl | jq -c ."),
    ("claude-plugin-list-ls", "Bash", "claude plugin list; ls -lrt"),
    ("cd-var-then-claude", "Bash", "cd \"$REPO\" && claude -p 'x'"),
    ("claude-mcp-then-git-c", "Bash", "claude mcp list && git -c core.pager=cat log -1"),
    # four letters of the name, placed away from the store (D6)
    ("rm-dot-build", "Bash", "rm -rf ./build/run-*"),
    ("rm-work-run-star", "Bash", "rm -rf .work/run-*"),
    ("find-repo", "Bash", "find . -name 'run-*' -delete"),
    ("ps-remove-build", "PowerShell", "Remove-Item -Recurse .\\build\\run-*"),
    ("tmp-grandparent", "Bash", "rm -rf /tmp/*/run-*"),
    ("var-tmp", "Bash", "rm -rf /var/tmp/run-*"),
    ("variable-script-no-name", "Bash", "python3 $SCRIPT --flag"),
    # one copy or move into the crew dir (D7)
    ("cp-recursive-dest", "Bash", "cp -r $SRC ~/.claude/crew/backup.d"),
    ("mv-plain", "Bash", "mv $SRC ~/.claude/crew/config.json.bak"),
    ("cp-braced-variable", "Bash", "cp ${SRC} ~/.claude/crew/config.json.bak"),
    ("ps-plain-copy", "PowerShell", f"Copy-Item $S {_C}"),
    ("ps-env-variable-copy", "PowerShell", f"Copy-Item $env:SRC {_C}"),
]

_R20_BLOCK = [
    # hook run (revs 2-5 groups; their commands are rebuilt from the ids, see the PR)
    ("script-path", "Bash", f"python3 {_S}/approval_hook.py"),
    ("python-X-flag", "Bash", f"python3 -X dev {_S}/approval_hook.py"),
    ("pwsh-execpolicy", "PowerShell", f"pwsh -ExecutionPolicy Bypass -File {_S}/approval-hook.ps1"),
    ("env-interpreter", "Bash", f"env python3 {_S}/approval_hook.py"),
    ("message-substitution", "Bash", f"git commit -m \"$(python3 {_S}/approval_hook.py < p.json)\""),
    ("module-crew-hook", "Bash", "python3 -m crew_hook UserPromptSubmit"),
    ("runner-module", "Bash", f"python3 -m runpy {_S}/approval_hook.py"),
    ("unlisted-module", "Bash", "python3 -m approval_hook"),
    ("unlisted-module-stdin", "Bash", "python3 -m approval_hook < p.json"),
    ("flag-cluster-ic", "Bash", "python3 -ic 'import approval_hook'"),
    ("flag-cluster-Ic", "Bash", "python3 -Ic 'import approval_hook'"),
    ("flag-cluster-sh-quoted", "Bash", f"bash -ec 'python3 {_S}/approval_hook.py'"),
    ("flag-cluster-sh-subst", "Bash", f"sh -c \"$(cat {_S}/crew-hook.sh)\""),
    ("flag-cluster-module", "Bash", "python3 -Im approval_hook"),
    ("pwsh-prefix", "PowerShell", f"& python {_S}/approval_hook.py"),
    ("unknown-flag", "Bash", f"python3 -m pytest --confcutdir=. {_S}/approval_hook.py"),
    ("dev-stdin", "Bash", f"python3 /dev/stdin < {_S}/approval_hook.py"),
    ("process-substitution", "Bash", f"python3 <(cat {_S}/approval_hook.py)"),
    ("variable-script", "Bash", f"H={_S}/approval_hook.py; python3 $H"),
    ("interpreter-env", "Bash", f"PYTHONSTARTUP={_S}/approval_hook.py python3 -m pytest -q"),
    # module run
    ("run-module-script", "Bash", f"python3 {_S}/crew_runapproval.py"),
    ("module-runapproval", "Bash", "python3 -m crew_runapproval"),
    ("stdin-heredoc-import", "Bash", "python3 - <<'EOF'\nimport crew_runapproval\nEOF"),
    # the store's name
    ("python-join", "Bash", "python3 -c \"import os; open(os.path.join(os.path.expanduser('~'), "
                            "'.claude', 'crew', 'run-approvals', 'receipts', 'a.json'), 'w')\""),
    ("semicolon-boundary", "Bash", "cd ~/.claude/crew/run-approvals;touch receipts/a.json"),
    ("git-inside-quoted-string", "Bash", f"echo \"git commit -m '\" ; {_TOUCH} ; echo \"'\""),
    ("git-after-another-word", "Bash", f"git add -- git commit -m '{_TOUCH}'"),
    # claude
    ("resume-after-redirect", "Bash", "claude > $OUT -r 5f1c"),
    ("resume-after-quoted-pipe", "Bash", "claude -p 'a | b' --resume 5f1c < p.txt"),
    ("claude-quoted-flag", "Bash", "claude -p x '--resume' 5f1c"),
    ("claude-quoted-flag-dq", "Bash", "claude -p x \"--resume=5f1c\""),
    ("claude-wrapper", "Bash", "timeout 600 claude -p 'x' --resume 5f1c"),
    ("claude-keyword", "Bash", "if true; then claude --resume 5f1c -p x < p.txt; fi"),
    ("claude-grouping", "Bash", "(claude -r 5f1c -p x < p.txt)"),
    ("claude-flags-variable", "Bash", "claude -p $FLAGS"),
    # veiled
    ("cd-then-run-star", "Bash", "cd ~/.claude/crew && rm -rf run-*"),
    ("copy-into-crew-dir", "Bash", "cp -r $SRC ~/.claude/crew/"),
    ("copy-into-crew-dir-bare", "Bash", "cp -r $SRC ~/.claude/crew"),
    ("crew-dir-dotdot", "Bash", "cp -r $SRC ~/.claude/crew/x/.."),
    ("O18", "Bash", "d=~/.claude/crew; ls $d > listing.txt"),
    ("O19", "PowerShell", "Remove-Item -Recurse $env:TEMP\\run-*"),
    ("veiled-grandparent", "Bash", "rm -rf ~/.claude/*/run-*"),
    ("tilde-user", "Bash", "rm -rf ~root/.claude/crew/run-*"),
    ("tilde-user-elsewhere", "Bash", "rm -rf ~owner/tmp/run-*"),
    ("tilde-stack", "Bash", "rm -rf ~+/run-*"),
    ("tilde-walker-root", "Bash", "find ~root -name 'run-*' -delete"),
    ("home-rooted", "Bash", "rm -rf ~/build/run-*"),
    ("other-rooted", "Bash", "rm -rf /opt/build/run-*"),
    ("cd-chain", "Bash", "cd ~ && cd .claude && cd crew && rm -rf run-*"),
    ("crew-dir-chdir-flag", "Bash", "git -C ~/.claude/crew/tmp rm -r $X"),
    # walkers
    ("find-claude-exec", "Bash", "find ~/.claude -name 'run-*' -exec rm -rf {} +"),
    ("find-from-home-delete", "Bash", "find ~ -name 'run-*' -delete"),
    ("gci-recurse", "PowerShell", "Get-ChildItem -Recurse ~ -Filter run-* | Remove-Item -Recurse"),
    ("code-glob", "Bash", "python3 -c \"import glob, shutil; [shutil.rmtree(p) for p in "
                          "glob.glob('/home/*/.claude/crew/run-*')]\""),
    # rev 6 classes
    ("wrapper", "Bash", f"timeout 10 python3 {_S}/approval_hook.py < p.json"),
    ("wrapper-nice", "Bash", f"nice python3 {_S}/crew_hook.py UserPromptSubmit"),
    ("uv-run", "Bash", f"uv run {_S}/approval_hook.py"),
    ("shell-keyword", "Bash", f"if true; then python3 {_S}/approval_hook.py < p.json; fi"),
    ("shell-keyword-for", "Bash", f"for i in 1; do bash {_S}/crew-hook.sh UserPromptSubmit; done"),
    ("negation", "Bash", f"! python3 {_S}/approval_hook.py"),
    ("grouping", "Bash", f"(python3 {_S}/approval_hook.py < p.json)"),
    ("grouping-brace", "Bash", f"{{ python3 {_S}/approval_hook.py; }} < p.json"),
    ("variable-command-word", "Bash", f"PY=python3; $PY {_S}/approval_hook.py"),
    ("find-exec", "Bash", "find plugin -name approval_hook.py -exec python3 {} \\;"),
    ("git-alias", "Bash", f"git -c alias.x='!python3 {_S}/approval_hook.py' x"),
    ("ps-block", "PowerShell", f"if ($true) {{ python {_S}/approval_hook.py }}"),
    ("ps-cmd-c", "PowerShell", f"cmd /c python {_S}/approval_hook.py"),
    ("ps-start-process", "PowerShell", f"Start-Process python -ArgumentList {_S}/approval_hook.py"),
    ("ps-set-alias", "PowerShell", f"Set-Alias p python; p {_S}/approval_hook.py"),
    ("module-wrapper", "Bash", f"timeout 10 python3 {_S}/crew_runapproval.py"),
    ("module-keyword", "Bash", "if true; then python3 -c 'import crew_runapproval'; fi"),
    # the table itself
    ("cat-pipe-python", "Bash", f"cat {_S}/approval_hook.py | python3"),
    ("pylint-init-hook", "Bash",
     "python3 -m pylint --init-hook='import approval_hook; approval_hook.main()' x.py"),
    ("rg-pre", "Bash", f"rg --pre {_S}/crew-hook.sh x ."),
    ("pytest-p", "Bash", "python3 -m pytest -p approval_hook"),
    ("git-ext-diff", "Bash", f"git diff --ext-diff -- {_S}/approval_hook.py"),
    ("redirect-copy", "Bash", f"git show HEAD:{_S}/approval_hook.py > x.py"),
    ("copy-then-run", "Bash", f"cp {_S}/approval_hook.py x.py && python3 x.py"),
    ("assignment-prefix", "Bash", f"GIT_EXTERNAL_DIFF=python3 git diff -- {_S}/approval_hook.py"),
    ("sed-exec", "Bash", f"sed -i '1e bash {_S}/crew-hook.sh' README.md"),
    ("sed-exec-bare", "Bash", f"sed -i e {_S}/crew-hook.sh"),
    ("function-shadow", "Bash", f"git() {{ python3 \"$2\"; }}; git add {_S}/approval_hook.py"),
    ("flags-before-m", "Bash", f"python3 -I -m pylint {_S}/approval_hook.py"),
    ("json-tool-outfile", "Bash",
     "python3 -m json.tool forged.json ~/.claude/crew/run-approvals/receipts/ar-0123456789ab.json"),
    ("rm-store-table", "Bash", "rm -rf ~/.claude/crew/run-approvals"),
    ("cd-then-add", "Bash", "cd plugin/crew && git add hooks/scripts/crew_hook.py"),
    ("diff-pipe-head", "Bash", f"git diff -- {_S}/crew_hook.py | head -20"),
    ("heredoc-commit", "Bash", "git commit -m \"$(cat <<'EOF'\ndocs: the run-approvals store\nEOF\n)\""),
    ("ps-backslash-quote", "PowerShell",
     "git commit -m \"a\\\" ; ni ~/.claude/crew/run-approvals/receipts/a ; echo \\\"b\""),
    # rev 7
    ("cp-target-flag", "Bash", "cp -t $DST ~/.claude/crew/forged/ar-0123456789ab.json"),
    ("cp-target-long", "Bash", f"cp --target-directory=$DST {_B}"),
    ("ps-destination-first", "PowerShell", f"Copy-Item -Destination $D {_C}"),
    ("pylint-output-file", "Bash", f"python3 -m pylint --output-format=json:out.json {_S}/approval_hook.py"),
    ("ps-pipe-into-write", "PowerShell", f"Get-Content {_S}/approval_hook.py | Remove-Item"),
    # rev 8
    ("ps-path-named-copy", "PowerShell", f"Copy-Item $S -Path {_C}"),
    ("ps-literalpath-named-move", "PowerShell", f"Move-Item $S -LiteralPath {_C}"),
    ("ps-cp-alias-literalpath", "PowerShell", f"cp $S -LiteralPath {_C}"),
    ("ps-mv-alias-path", "PowerShell", f"mv $S -Path {_C}"),
    ("ps-cp-bash-letters", "PowerShell", f"cp -r $S {_C}"),
    ("ps-path-first-copy", "PowerShell", f"Copy-Item -Path $S {_C}"),
    ("ps-lone-operand", "PowerShell", f"Set-Location $D; Copy-Item {_C}"),
    ("ps-lone-operand-recurse", "PowerShell", f"Set-Location $D; Copy-Item -Recurse {_C}"),
    # rev 9 (the dashes are written by code point, never pasted)
    ("cp-quoted-target-flag", "Bash", f"cp '-t' $DST {_B}"),
    ("cp-dquoted-target-flag", "Bash", f"cp \"-t\" $DST {_B}"),
    ("cp-part-quoted-target-flag", "Bash", f"cp -'t' $DST {_B}"),
    ("cp-escaped-target-flag", "Bash", f"cp \\-t $DST {_B}"),
    ("cp-quoted-target-long", "Bash", f"cp \"--target-directory=$DST\" x {_B}"),
    ("mv-quoted-target-flag", "Bash", f"mv '-t' $DST {_B}"),
    ("ps-endash-destination", "PowerShell", f"Copy-Item {chr(0x2013)}Destination $D {_C}"),
    ("ps-emdash-destination-move", "PowerShell", f"Move-Item {chr(0x2014)}Destination $D {_C}"),
    ("ps-hbar-destination", "PowerShell", f"Copy-Item {chr(0x2015)}Destination $D {_C}"),
    ("ps-comma-sources", "PowerShell", f"Set-Location $D; Copy-Item $A, {_C}"),
    ("ps-comma-word-sources", "PowerShell", f"Set-Location $D; Copy-Item $A , {_C}"),
    ("ps-comma-sources-move", "PowerShell", f"Set-Location $D; Move-Item $A, {_C}"),
    ("ps-comma-word-sources-alone", "PowerShell", f"Copy-Item $A , {_C}"),
    ("cp-assignment-same-command", "Bash", f"S=\"-t $DST\"; cp $S {_B}"),
    ("cp-function-shadow", "Bash", f"cp() {{ command cp -t $DST \"$2\"; }}; cp $SRC {_B}"),
    ("ps-function-shadow", "PowerShell",
     "function Copy-Item($a, $b) { Microsoft.PowerShell.Management\\Copy-Item $b $a }; "
     f"Copy-Item $D {_C}"),
    ("ps-alias-shadow", "PowerShell", f"Set-Alias cp Move-Item; cp $S {_C}"),
    ("cp-after-mkdir", "Bash", "mkdir -p ~/.claude/crew/bak && cp $SRC ~/.claude/crew/bak/x.json"),
    ("cp-glob-source", "Bash", f"cp * {_B}"),
    ("rm-beside-crew-word", "Bash", "rm $X ~/.claude/crew/tmp/a"),
    ("cp-crew-word-first", "Bash", f"cp {_B} $DST"),
    ("cp-crew-word-twice", "Bash", f"cp {_B} $X ~/.claude/crew/y.json"),
    ("cp-dquoted-source", "Bash", "cp \"$SRC\" ~/.claude/crew/config.json.bak"),
    ("cp-double-dash", "Bash", "cp -- $SRC ~/.claude/crew/config.json.bak"),
    ("cp-mixed-word", "Bash", "cp $SRC/a.json ~/.claude/crew/config.json.bak"),
    # review round 1: a source may not name the crew dir (only the destination may)
    ("cp-crew-source-relative", "Bash", "cp .claude/crew/example $SRC ~/.claude/crew/backup"),
    ("cp-crew-source-nested", "Bash", "cp -r x/.claude/crew/a $SRC ~/.claude/crew/bak"),
    ("ps-crew-source-relative", "PowerShell", "Copy-Item .claude\\crew\\example $S ~\\.claude\\crew\\backup"),
    # review round 1: after git's `--` every word is a pathspec, never a message D4 (b) drops
    ("msg-after-double-dash", "Bash", "git commit -m 'notes' -- -m 'run-approvals'"),
    ("msg-after-double-dash-eq", "Bash", "git commit -m 'notes' -- --message='run-approvals'"),
    ("msg-gh-after-double-dash", "Bash", "gh pr create --title 'notes' -- --body 'run-approvals'"),
    # review round 2: PowerShell ends an ASCII-opened quote on a typographic one as well
    ("msg-ps-typographic-single", "PowerShell",
     f"git commit -m 'x{chr(0x2019)}; {_PS_TOUCH}; git commit -m {chr(0x2018)}y'"),
    ("msg-ps-typographic-double", "PowerShell",
     f"git commit -m \"x{chr(0x201d)}; {_PS_TOUCH}; git commit -m {chr(0x201c)}y\""),
    ("msg-ps-typographic-low", "PowerShell",
     f"git commit -m 'x{chr(0x201a)}; {_PS_TOUCH}; git commit -m {chr(0x201b)}y'"),
    # rev 10: a dropped message read back and run (the owner's MUST-BLOCK)
    ("msg-launder-store", "Bash",
     "git commit --allow-empty -m 'cp forged.json "
     "~/.claude/crew/run-approvals/receipts/ar-0123456789ab.json'" + _TAIL),
    ("msg-launder-hook", "Bash", f"git commit --allow-empty -m 'python3 {_S}/approval_hook.py'" + _TAIL),
    ("msg-launder-module", "Bash",
     f"git commit --allow-empty -m 'python3 {_S}/crew_runapproval.py'" + _TAIL),
    ("msg-launder-claude", "Bash", "git commit --allow-empty -m 'claude --resume 5f1c -p x'" + _TAIL),
    ("msg-launder-tag", "Bash",
     f"git tag -a t1 -m '{_TOUCH}' ; git tag -l -n1 t1 | cut -d ' ' -f 2- | bash"),
    ("msg-launder-gh", "Bash",
     f"gh pr comment 1 --body '{_TOUCH}' ; gh pr view 1 --json body -q .body | bash"),
    ("msg-launder-ps", "PowerShell",
     "git commit --allow-empty -m 'ni ~/.claude/crew/run-approvals/receipts/a' ; "
     "git cat-file commit HEAD | Select-Object -Last 1 | iex"),
    ("msg-launder-editmsg", "Bash", f"git commit --allow-empty -m '{_TOUCH}' && bash .git/COMMIT_EDITMSG"),
    ("msg-tag-sign", "Bash", "git tag -s t1 -m 'run-approvals tripwire'"),
    # rev 11
    ("msg-launder-sed-pytest", "Bash",
     "git commit --allow-empty -m '__import__(\"os\").system(\"touch "
     "~/.claude/crew/run-approvals/receipts/a\")' && sed -i.py 's/q/q/' .git/COMMIT_EDITMSG "
     "&& python3 -m pytest -q .git/COMMIT_EDITMSG.py"),
    ("msg-launder-sed-doctest", "Bash",
     "git commit --allow-empty -m '>>> __import__(\"os\").system(\"touch "
     "~/.claude/crew/run-approvals/receipts/a\")' && sed -i.txt 's/q/q/' .git/COMMIT_EDITMSG "
     "&& python3 -m pytest -q .git/COMMIT_EDITMSG.txt"),
    ("msg-pytest-then-commit", "Bash",
     "python3 -m pytest -q plugin/crew/tests/test_allow_run.py && "
     "git commit -m 'fix: approval_hook reads the prompt id'"),
    ("msg-sed-then-commit", "Bash",
     "sed -i 's/a/b/' README.md && git commit -a -m 'docs: the run-approvals store'"),
    ("msg-commit-then-rm", "Bash", "git commit -m 'docs: the run-approvals store' && rm -rf build"),
    ("msg-ps-commit-then-remove", "PowerShell",
     "git commit -m 'docs: the run-approvals store' ; Remove-Item -Recurse build"),
    # rev 12: sed stands alone
    ("sed-guard-pytest-stdin", "Bash",
     f"sed -i 's/== \"__main__\"/== __name__/' {_S}/approval_hook.py && "
     f"cat forged.json | python3 -m pytest -s {_S}/approval_hook.py"),
    ("sed-gitconfig-extdiff", "Bash",
     "sed -i 's/^\\[core\\]$/[diff]\\n\\texternal = python3\\n[core]/' .git/config && "
     f"git diff -- {_S}/approval_hook.py"),
    ("sed-gitconfig-fsmonitor", "Bash",
     "sed -i 's/bare = false/fsmonitor = \"cat forged.json | python3 "
     "plugin\\/crew\\/hooks\\/scripts\\/approval_hook.py #\"/' .git/config && git status"),
    ("sed-pyproject-pylint-inithook", "Bash",
     "sed -i 's/^\\[tool.ruff\\]$/[tool.pylint.main]\\ninit-hook = \"import approval_hook; "
     "approval_hook.main()\"\\n[tool.ruff]/' pyproject.toml && "
     f"python3 -m pylint {_S}/approval_hook.py"),
    ("sed-script-names-hook", "Bash",
     "sed -i 's/bare = false/fsmonitor = \"cat forged.json | python3 "
     "plugin\\/crew\\/hooks\\/scripts\\/approval_hook.py #\"/' .git/config"),
    ("sed-script-names-module", "Bash", "sed -i 's/x/import crew_runapproval/' conftest.py"),
    ("sed-suffix-names-hook", "Bash", "sed -i.approval_hook.py 's/a/b/' README.md"),
    ("sed-then-add", "Bash", f"sed -i 's/a/b/' {_S}/approval_hook.py && git add {_S}/approval_hook.py"),
    ("sed-two-seds", "Bash", f"sed -i 's/a/b/' {_S}/approval_hook.py ; sed -i 's/c/d/' {_S}/crew_hook.py"),
    ("sed-then-pytest-tests", "Bash",
     f"sed -i 's/a/b/' {_S}/approval_hook.py && python3 -m pytest -q plugin/crew/tests/test_approval_hook.py"),
    # an `@file` operand: pytest, mypy and ruff read flags from it (the message file included)
    ("argfile-pytest-trace", "Bash",
     "git commit --allow-empty -m '--trace' && git log -1 --format='import sys, runpy; "
     "sys.stdin = open(\"forged.json\"); runpy.run_path(\"plugin/crew/hooks/scripts/approval_hook.py\", "
     "run_name=\"__main__\")' | python3 -m pytest @.git/COMMIT_EDITMSG plugin/crew/tests/test_crew_ticket.py"),
    ("argfile-pytest-plugin", "Bash",
     "git commit --allow-empty -m '-papproval_hook' && python3 -m pytest @.git/COMMIT_EDITMSG"),
    ("argfile-mypy-python-executable", "Bash",
     f"git commit --allow-empty -m '--python-executable={_S}/crew-hook.sh' && "
     "python3 -m mypy @.git/COMMIT_EDITMSG x.py"),
    ("argfile-pytest-earlier-state", "Bash", f"python3 -m pytest @args.txt {_S}/approval_hook.py"),
]


def _ids(rows):
    return [row[0] for row in rows]


@pytest.mark.parametrize("ident,tool_name,command", _R20_ALLOW, ids=_ids(_R20_ALLOW))
def test_with_a_class_on_a_recorded_everyday_command_is_allowed(repo, capsys, ident, tool_name,
                                                                command):
    """R-20 must-allow: a recorded over-refusal, or its neighbour, in a shape
    an excuse recognises. Every trigger still runs; only its own clause is
    excused (section 3 "Order")."""
    del ident
    turn_on()

    assert guard(capsys, shell(repo, command, tool=tool_name)) == (0, "")


@pytest.mark.parametrize("ident,tool_name,command", _R20_BLOCK, ids=_ids(_R20_BLOCK))
def test_with_a_class_on_a_shape_no_excuse_recognises_is_still_refused(repo, capsys, ident,
                                                                       tool_name, command):
    """R-20 must-block: not a recognised shape, so it is judged exactly as
    before R-20. With the class off it passes: the store tripwire, and
    nothing else, is what refuses it."""
    del ident
    turn_on(classes=())
    assert guard(capsys, shell(repo, command, tool=tool_name))[0] == 0
    turn_on()

    code, err = guard(capsys, shell(repo, command, tool=tool_name))

    assert (code, "SCOPE GUARD" in err) == (2, True)


def _cwd_payload(repo, command, where):
    payload = shell(repo, command)
    if where is None:
        del payload["cwd"]
    else:
        payload["cwd"] = str(where(_home()))
    return payload


@pytest.mark.parametrize("where,command,expected", [
    (lambda home: home / "src" / "repo", "rm -rf ./build/run-*", 0),
    (lambda home: home / "src" / "repo", "rm -rf run-*", 0),
    (lambda home: home, "find . -name 'run-*' -delete", 2),
    (lambda home: home, "rm -rf */*/run-*", 2),
    (lambda home: home / "src" / "repo", "rm -rf ../../*/*/run-*", 2),
    (None, "rm -rf run-*", 2),
    (lambda home: home / ".claude" / "x", "rm -rf build/run-*", 2),
], ids=["repo-relative", "repo-relative-bare", "cwd-home-find", "cwd-home-rm", "relative-climb",
        "relative-no-cwd", "cwd-under-claude"])
def test_with_a_class_on_a_relative_glob_is_placed_from_the_directory_it_runs_in(
        repo, capsys, where, command, expected):
    """D6: a relative word is placed elsewhere only under a cwd that is not
    above the store and not under `~/.claude`; a climb, no cwd, a cwd of the
    home or under `~/.claude` places nothing."""
    turn_on()

    code, _ = guard(capsys, _cwd_payload(repo, command, where))

    assert code == expected


def _store_lies_under_tmp():
    """Whether a store target lies under `/tmp` as D6 reads it on this host:
    the literal `/tmp`, its real path off Windows, the temp dir on Windows."""
    bases = ["/tmp", tempfile.gettempdir() if os.name == "nt" else os.path.realpath("/tmp")]
    home = os.path.expanduser("~")
    targets = {os.path.join(h, ".claude", "crew", "run-approvals")
               for h in (os.path.abspath(home), os.path.realpath(home))}
    return any(os.path.normcase(t).startswith(os.path.normcase(os.path.abspath(b)).rstrip(os.sep) + os.sep)
               for t in targets for b in bases)


def test_with_a_class_on_find_from_tmp_is_allowed_only_when_the_store_is_not_under_it(repo, capsys):
    """`find /tmp -name 'run-*' -delete` walks the store when the home is
    under `/tmp` (the Linux CI's isolated home, the Windows temp dir): then
    it is refused, otherwise allowed. The row never skips."""
    turn_on()
    expected = 2 if _store_lies_under_tmp() else 0

    code, _ = guard(capsys, shell(repo, "find /tmp -name 'run-*' -delete"))

    assert code == expected


def _home_rows(home):
    """Commands built from this test's own home (`<home>` in the spec)."""
    text = str(home)
    drive, rest = os.path.splitdrive(text)
    rest = rest.replace("\\", "/").strip("/")
    if drive:
        letter = drive[0]
        msys = f"rm -rf /{letter.lower()}/{rest}/*/crew/run-*"
    else:
        msys = f"rm -rf /proc/self/root{text}/*/crew/run-*"
    parent, last = os.path.split(text.rstrip("\\/"))
    short = os.path.join(parent, last[:6].upper() + "~1").replace("\\", "/")
    back = text.replace("/", "\\")
    return {"msys-root": ("Bash", msys),
            "short-name": ("Bash", f"rm -rf {short}/*/crew/run-*"),
            "ps-comma-array": ("PowerShell", f"Remove-Item -Recurse build\\x,{back}\\*\\*\\run-*"),
            "ps-comma-array-fwd": ("PowerShell",
                                   f"Remove-Item -Recurse build/x,{text.replace(chr(92), '/')}/*/*/run-*"),
            "ps-provider": ("PowerShell", f"Remove-Item -Recurse FileSystem::{back}\\*\\*\\run-*")}


@pytest.mark.parametrize("ident", ["msys-root", "short-name", "ps-comma-array", "ps-comma-array-fwd",
                                   "ps-provider"])
def test_with_a_class_on_a_rooted_or_joined_word_built_from_the_home_is_refused(repo, capsys, ident):
    """D6's root forms and placed-word characters: a drive spelled `/c/`, a
    short name, a PowerShell array or provider path is never placed."""
    tool_name, command = _home_rows(_home())[ident]
    turn_on()

    code, _ = guard(capsys, shell(repo, command, tool=tool_name))

    assert code == 2


def test_with_a_class_on_a_home_reached_through_a_link_is_read_in_both_forms(repo, capsys,
                                                                             monkeypatch, tmp_path):
    """D6 compares against the home as written AND as its real path: HOME
    points at a link to the real home, the command runs in the real home."""
    turn_on()
    real = _home()
    link = tmp_path / "home-link"
    if os.name == "nt":
        import _winapi  # pylint: disable=import-outside-toplevel,import-error
        _winapi.CreateJunction(str(real), str(link))
    else:
        link.symlink_to(real, target_is_directory=True)
    for name in ("HOME", "USERPROFILE"):
        monkeypatch.setenv(name, str(link))
    payload = shell(repo, "find . -name 'run-*' -delete")
    payload["cwd"] = os.path.realpath(str(link))

    code, _ = guard(capsys, payload)

    assert code == 2


def test_on_powershell_off_windows_cp_gets_no_copy_excuse(repo, capsys, monkeypatch):
    """`cp`/`mv` are Copy-Item / Move-Item only on Windows; elsewhere they are
    the native programs, and a `$S` holding `-t/dir` is a flag to them."""
    turn_on()
    monkeypatch.setattr(ra, "_ps_cp_is_alias", lambda: False)

    assert guard(capsys, shell(repo, f"cp $S {_C}", tool="PowerShell"))[0] == 2
    assert guard(capsys, shell(repo, f"Copy-Item $S {_C}", tool="PowerShell")) == (0, "")

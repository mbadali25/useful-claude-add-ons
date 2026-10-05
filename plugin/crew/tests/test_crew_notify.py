"""crew_notify.py: the config, the filter, the line, the transport and the dedupe (T-0051).

A local HTTP server stands in for api.telegram.org (`CREW_NOTIFY_TELEGRAM_BASE`),
so nothing here reaches a real chat. The notify skill's config and the
machine-global crew config are pointed at scratch paths for every test.
"""
import html
import http.server
import json
import os
import pathlib
import subprocess
import threading
import time
import urllib.parse

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import crew_config
import crew_notify
from review_fixtures import init_repo

TOKEN = "123456789:" + "AbCdEfGhIjKlMnOpQrStUvWxYz0123456789"
TOKEN_ENV = "CREW_TEST_TG_TOKEN"
CHAT = "4242"

# --- captured from a live Notification hook -------------------------------------------------
# Claude Code 2.1.285, captured 2026-09-30 in a throwaway interactive session whose only
# hook was `Notification` -> append the payload to a file (plan step 1). session_id, cwd,
# transcript_path and scratchpad_dir are replaced by fixture values; prompt_id,
# hook_event_name, message and notification_type are as captured. Seen: permission_prompt
# (a Bash permission, and an AskUserQuestion) and idle_prompt. NOT captured (documented
# only): elicitation_dialog, elicitation_url_dialog, agent_needs_input,
# worker_permission_prompt -- no MCP server offering elicitation was configured.
# Measured, against the spec's expectation: the AskUserQuestion payload is a
# permission_prompt whose message is the fixed "Claude needs your permission"; it does NOT
# name AskUserQuestion (nor does the Bash one name Bash). The transcript's pending
# tool_use is what tells them apart.
CAPTURED = {
    "bash-permission": {
        "session_id": "fixture-session", "transcript_path": "TRANSCRIPT_BASH",
        "cwd": "FIXTURE_CWD", "scratchpad_dir": "FIXTURE_SCRATCH",
        "prompt_id": "bcaf8c31-2a5d-44f1-81ca-be6c23fe5708", "hook_event_name": "Notification",
        "message": "Claude needs your permission", "notification_type": "permission_prompt"},
    "askuserquestion": {
        "session_id": "fixture-session", "transcript_path": "TRANSCRIPT_ASK",
        "cwd": "FIXTURE_CWD", "scratchpad_dir": "FIXTURE_SCRATCH",
        "prompt_id": "20f9cc4f-53f6-4e29-a9cd-db9a42e36516", "hook_event_name": "Notification",
        "message": "Claude needs your permission", "notification_type": "permission_prompt"},
    "idle": {
        "session_id": "fixture-session", "transcript_path": "TRANSCRIPT_ASK",
        "cwd": "FIXTURE_CWD", "scratchpad_dir": "FIXTURE_SCRATCH",
        "prompt_id": "20f9cc4f-53f6-4e29-a9cd-db9a42e36516", "hook_event_name": "Notification",
        "message": "Claude is waiting for your input", "notification_type": "idle_prompt"},
}

# The same session's transcript, trimmed to the lines that matter: one JSON object per
# line, each assistant content item on a line of its own (as captured).
_BASH_LINES = [
    {"type": "user", "uuid": "f6412030", "promptId": "bcaf8c31",
     "message": {"role": "user", "content": "Run exactly this bash command with the Bash "
                 "tool and nothing else: touch /tmp/probe.txt"}},
    {"type": "attachment", "uuid": "e09f2f37"},
    {"type": "assistant", "uuid": "ddad710c",
     "message": {"role": "assistant", "content": [{"type": "thinking", "thinking": "..."}]}},
    {"type": "assistant", "uuid": "0f469fbb",
     "message": {"role": "assistant", "content": [
         {"type": "tool_use", "id": "toolu_0127", "name": "Bash",
          "input": {"command": "touch /tmp/probe.txt",
                    "description": "Create probe.txt file in the working directory"}}]}},
]
_ASK_LINES = _BASH_LINES + [
    {"type": "user", "uuid": "0fe3a795",
     "message": {"role": "user", "content": [{"type": "tool_result", "content": ""}]}},
    {"type": "assistant", "uuid": "c3cad2b3",
     "message": {"role": "assistant", "content": [
         {"type": "text", "text": "Done - probe.txt created."}]}},
    {"type": "system", "uuid": "bef7f233"},
    {"type": "user", "uuid": "c5bbdb89",
     "message": {"role": "user", "content": "Use the AskUserQuestion tool to ask me one "
                 "question"}},
    {"type": "assistant", "uuid": "4ad0c87d",
     "message": {"role": "assistant", "content": [{"type": "thinking", "thinking": "..."}]}},
    {"type": "assistant", "uuid": "3de11264",
     "message": {"role": "assistant", "content": [
         {"type": "tool_use", "id": "toolu_01F8", "name": "AskUserQuestion",
          "input": {"questions": [{"question": "Which colour should the probe be?",
                                   "header": "Probe Color",
                                   "options": [{"label": "Red"}, {"label": "Blue"}],
                                   "multiSelect": False}]}}]}},
]


def _write_transcript(path, lines):
    path.write_text("".join(json.dumps(line) + "\n" for line in lines), encoding="utf-8")
    return str(path)


# --- fixtures ----------------------------------------------------------------------------------

class _FakeTelegram(http.server.BaseHTTPRequestHandler):
    requests = []
    responses = []

    def do_POST(self):  # pylint: disable=invalid-name
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length).decode("utf-8")
        form = {key: values[0] for key, values in urllib.parse.parse_qs(body).items()}
        _FakeTelegram.requests.append({"at": time.monotonic(), "path": self.path,
                                       "form": form, "raw": body})
        status, reply, delay = (_FakeTelegram.responses.pop(0) if _FakeTelegram.responses
                                else (200, {"ok": True, "result": {}}, 0))
        if delay:
            time.sleep(delay)
        data = reply if isinstance(reply, bytes) else json.dumps(reply).encode()
        try:
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        except OSError:
            pass

    def log_message(self, *_args):  # pylint: disable=arguments-differ
        pass


@pytest.fixture(name="telegram")
def _telegram(monkeypatch):
    _FakeTelegram.requests = []
    _FakeTelegram.responses = []
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _FakeTelegram)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    monkeypatch.setenv("CREW_NOTIFY_TELEGRAM_BASE", f"http://127.0.0.1:{server.server_address[1]}")
    yield _FakeTelegram
    server.shutdown()
    server.server_close()


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    monkeypatch.setattr(crew_notify, "SKILL_CONFIG_PATH", str(tmp_path / "no-skill.json"))
    monkeypatch.setattr(crew_notify, "PACE_SECONDS", 0.0)
    monkeypatch.setenv(TOKEN_ENV, TOKEN)
    # Never the real network and never this machine's own global config: a
    # test that does not ask for the fake Telegram gets a closed local port,
    # and one that does not call _global gets a scratch global layer naming
    # only the token's variable (tokenEnv is honoured from that layer alone).
    monkeypatch.setenv("CREW_NOTIFY_TELEGRAM_BASE", "http://127.0.0.1:9")
    _global(tmp_path, monkeypatch, {"tokenEnv": TOKEN_ENV})


def _repo(tmp_path, notify=None, ticket=("T-0042", "implement")):
    root = init_repo(tmp_path / "repo")
    block = {"provider": "telegram", "tokenEnv": TOKEN_ENV, "chatId": CHAT,
             "events": ["deploy", "question"]}
    if notify is not None:
        block = notify
    (root / ".crew").mkdir()
    (root / ".crew" / "config.json").write_text(json.dumps({"notify": block}), encoding="utf-8")
    if ticket:
        (root / ".work" / "tickets" / ticket[0]).mkdir(parents=True)
        (root / ".work" / "INDEX.md").write_text(
            f"{ticket[0]} | {ticket[1]} | high | repo | a fixture ticket\n", encoding="utf-8")
    return root


def _global(tmp_path, monkeypatch, notify):
    path = tmp_path / "global-config.json"
    path.write_text(json.dumps({"notify": notify}), encoding="utf-8")
    monkeypatch.setattr(crew_config, "GLOBAL_CONFIG_PATH", str(path))
    monkeypatch.setattr(crew_config.crew_state, "GLOBAL_CONFIG_PATH", str(path))


def _payload(ntype, root=None, message="Claude needs your permission", prompt="p-1",
             transcript=None, session="s-1"):
    out = {"session_id": session, "hook_event_name": "Notification", "message": message,
           "cwd": str(root or "."), "transcript_path": transcript or "/nonexistent/t.jsonl",
           "prompt_id": prompt}
    if ntype is not None:
        out["notification_type"] = ntype
    return out


def _hook(root, payload):
    return crew_notify.hook(str(root), json.dumps(payload).encode())


def _text(telegram, index=-1):
    """The line as the owner reads it: the wire text is HTML-escaped."""
    return html.unescape(telegram.requests[index]["form"]["text"])


def _state(root):
    return pathlib.Path(crew_notify.state_dir(str(root)))


# --- step 1: the captured payloads ----------------------------------------------------------

@pytest.mark.parametrize("name,expected,subject", [
    ("bash-permission", "question", "Needs permission"),
    ("askuserquestion", "question", "Question"),
    ("idle", "quiet", None),
])
def test_captured_payloads_classify_as_expected(tmp_path, name, expected, subject):
    payload = dict(CAPTURED[name])
    lines = _BASH_LINES if payload["transcript_path"] == "TRANSCRIPT_BASH" else _ASK_LINES
    payload["transcript_path"] = _write_transcript(tmp_path / "t.jsonl", lines)
    tool = crew_notify.context(payload["transcript_path"])["tool"]

    got = crew_notify.classify(payload, pending_tool=tool)

    assert (got[0], got[2]) == (expected, subject)


# --- step 2: must send ---------------------------------------------------------------------------

@pytest.mark.parametrize("ntype", crew_notify.QUESTION_TYPES)
def test_question_types_send(tmp_path, telegram, ntype):
    root = _repo(tmp_path)

    assert (_hook(root, _payload(ntype, root)), len(telegram.requests)) == ("sent", 1)


def test_askuserquestion_permission_prompt_is_a_question(tmp_path, telegram):
    root = _repo(tmp_path)

    _hook(root, _payload("permission_prompt", root,
                         message="Claude needs your permission to use AskUserQuestion"))

    assert _text(telegram).startswith("Question [")


def test_askuserquestion_pending_in_transcript_is_a_question(tmp_path, telegram):
    """The measured case: the message names nothing, the transcript does."""
    root = _repo(tmp_path)
    transcript = _write_transcript(tmp_path / "t.jsonl", _ASK_LINES)

    _hook(root, _payload("permission_prompt", root, transcript=transcript))

    assert _text(telegram).startswith("Question [")


def test_bash_permission_prompt_needs_permission(tmp_path, telegram):
    root = _repo(tmp_path)
    transcript = _write_transcript(tmp_path / "t.jsonl", _BASH_LINES)

    _hook(root, _payload("permission_prompt", root, transcript=transcript))

    line = _text(telegram)
    assert (line.startswith("Needs permission ["), "Bash" in line) == (True, True)


def test_legacy_waiting_maps_to_question(tmp_path, telegram, capsys):
    root = _repo(tmp_path, notify={"provider": "telegram", "tokenEnv": TOKEN_ENV,
                                   "chatId": CHAT, "events": ["waiting"]})

    result = crew_notify.send(str(root), "waiting", "context 90% - writing handoff")

    assert (result, "legacy 'waiting' read as 'question'" in capsys.readouterr().err) == (
        "sent", True)


def test_legacy_gate_maps_to_deploy(tmp_path, telegram, capsys):
    root = _repo(tmp_path, notify={"provider": "telegram", "tokenEnv": TOKEN_ENV,
                                   "chatId": CHAT, "events": ["gate"]})

    result = crew_notify.send(str(root), "gate", "staging abc123 - pass")

    assert (result, _text(telegram).split(" [")[0],
            "legacy 'gate' read as 'deploy'" in capsys.readouterr().err) == (
                "sent", "Promotion passed", True)


def test_legacy_phase_review_done_map_to_blocker(tmp_path):
    root = _repo(tmp_path, notify={"provider": "telegram", "events": ["phase", "review", "done"]})

    cfg, notices = crew_notify.effective_config(str(root))

    assert (cfg["events"], len(notices)) == (["blocker"], 3)


def test_global_provider_used_when_repo_null(tmp_path, monkeypatch, telegram):
    _global(tmp_path, monkeypatch, {"provider": "telegram", "tokenEnv": TOKEN_ENV,
                                    "chatId": CHAT})
    root = _repo(tmp_path, notify={"provider": None, "tokenEnv": None, "chatId": None})

    assert crew_notify.send(str(root), "deploy", "prod abc - pass", outcome="pass") == "sent"


def test_repo_value_overrides_global(tmp_path, monkeypatch):
    _global(tmp_path, monkeypatch, {"provider": "telegram", "chatId": "111"})
    root = _repo(tmp_path, notify={"provider": "teams", "chatId": "222"})

    cfg, _ = crew_notify.effective_config(str(root))

    assert (cfg["provider"], cfg["chatId"]) == ("teams", "222")


def test_skill_fallback_fills_null_chat_and_token_env(tmp_path, monkeypatch):
    skill = tmp_path / "skill.json"
    skill.write_text(json.dumps({"telegram": {"bot_token_env": "SKILL_TOKEN",
                                              "chat_id": 777}}), encoding="utf-8")
    monkeypatch.setattr(crew_notify, "SKILL_CONFIG_PATH", str(skill))
    _global(tmp_path, monkeypatch, {})
    root = _repo(tmp_path, notify={"provider": "telegram", "tokenEnv": None, "chatId": None})

    cfg, _ = crew_notify.effective_config(str(root))

    assert (cfg["tokenEnv"], cfg["chatId"]) == ("SKILL_TOKEN", "777")


def test_repo_token_env_is_ignored(tmp_path, monkeypatch, telegram, capsys):
    """A cloned repo must not pick which environment variable's value goes into
    the request URL: its tokenEnv is ignored, the global one is used, and a
    repo tokenEnv with no global one sends nothing."""
    monkeypatch.setenv("CREW_TEST_OTHER_SECRET", "s3cr3t-value-from-the-environment")
    root = _repo(tmp_path, notify={"provider": "telegram", "tokenEnv": "CREW_TEST_OTHER_SECRET",
                                   "chatId": CHAT, "events": ["deploy"]})

    first = crew_notify.send(str(root), "deploy", "prod abc - pass", outcome="pass")
    _global(tmp_path, monkeypatch, {})
    second = crew_notify.send(str(root), "deploy", "prod def - pass", outcome="pass")

    paths = [request["path"] for request in telegram.requests]
    assert (first, second, paths, "repo's notify.tokenEnv is ignored" in capsys.readouterr().err
            ) == ("sent", "missing-credentials", [f"/bot{TOKEN}/sendMessage"], True)


def test_repo_url_env_is_ignored(tmp_path, monkeypatch, telegram, capsys):
    """urlEnv is tokenEnv's twin: its variable's value IS the request URL, and a
    cloned repo's settings `env` can set any variable. A repo urlEnv is ignored
    (the global one is used), and with no global one nothing is sent."""
    base = os.environ["CREW_NOTIFY_TELEGRAM_BASE"]
    monkeypatch.setenv("CREW_TEST_REPO_URL", base + "/diverted")
    monkeypatch.setenv("CREW_TEST_TEAMS_URL", base + "/teams")
    root = _repo(tmp_path, notify={"provider": "teams", "urlEnv": "CREW_TEST_REPO_URL",
                                   "events": ["deploy"]})

    _global(tmp_path, monkeypatch, {"urlEnv": "CREW_TEST_TEAMS_URL"})
    first = crew_notify.send(str(root), "deploy", "prod abc - pass", outcome="pass")
    _global(tmp_path, monkeypatch, {})
    second = crew_notify.send(str(root), "deploy", "prod def - pass", outcome="pass")

    paths = [request["path"] for request in telegram.requests]
    assert (first, second, paths, "repo's notify.urlEnv is ignored" in capsys.readouterr().err
            ) == ("sent", "missing-credentials", ["/teams"], True)


def test_show_config_names_ignored_url_env(tmp_path, capsys):
    root = _repo(tmp_path, notify={"provider": "teams", "urlEnv": "REPO_PICKED"})

    crew_notify.show_config(str(root))

    out = capsys.readouterr().out
    shown = json.loads(out.splitlines()[-1])
    assert (shown["urlEnv"], "repo's notify.urlEnv is ignored" in out) == (None, True)


def test_show_config_masks_chat_id_and_names_ignored_token_env(tmp_path, capsys):
    root = _repo(tmp_path, notify={"provider": "telegram", "tokenEnv": "REPO_PICKED",
                                   "chatId": "-1009876543210"})

    crew_notify.show_config(str(root))

    out = capsys.readouterr().out
    shown = json.loads(out.splitlines()[-1])
    assert ("9876543210" in out, shown["chatId"], shown["tokenEnv"],
            "repo's notify.tokenEnv is ignored" in out) == (False, "***3210", TOKEN_ENV, True)


@pytest.mark.parametrize("value,shown", [(None, None), ("4242", "***42"),
                                         (-1009876543210, "***3210"), ("42", "***"),
                                         (7, "***"), ("", "***")])
def test_mask(value, shown):
    assert crew_notify.mask(value) == shown


# --- step 2: must stay quiet ------------------------------------------------------------------

@pytest.mark.parametrize("ntype", crew_notify.QUIET_TYPES)
def test_quiet_types_send_nothing(tmp_path, telegram, ntype):
    root = _repo(tmp_path)

    result = _hook(root, _payload(ntype, root))

    assert (result, len(telegram.requests),
            (_state(root) / "unrecognised.log").exists()) == ("quiet", 0, False)


def _log_lines(root):
    return (_state(root) / "unrecognised.log").read_text(encoding="utf-8").splitlines()


def test_missing_type_is_quiet_and_logged(tmp_path, telegram):
    root = _repo(tmp_path)

    result = _hook(root, _payload(None, root))

    assert (result, len(telegram.requests), _log_lines(root)[-1].endswith(" MISSING")) == (
        "quiet", 0, True)


def test_unknown_type_is_quiet_and_logged(tmp_path, telegram):
    root = _repo(tmp_path)

    result = _hook(root, _payload("brand_new_type", root))

    assert (result, len(telegram.requests), _log_lines(root)[-1].endswith(" brand_new_type")) == (
        "quiet", 0, True)


def test_unrecognised_log_is_capped(tmp_path, telegram):
    root = _repo(tmp_path)
    for index in range(crew_notify.UNRECOGNISED_CAP + 5):
        crew_notify._log_unrecognised(str(root), f"t{index}")  # pylint: disable=protected-access

    assert len(_log_lines(root)) == crew_notify.UNRECOGNISED_CAP


def test_repo_none_opts_out_with_notice(tmp_path, monkeypatch, telegram, capsys):
    _global(tmp_path, monkeypatch, {"provider": "telegram", "tokenEnv": TOKEN_ENV,
                                    "chatId": CHAT})
    root = _repo(tmp_path, notify={"provider": "none"})

    result = crew_notify.send(str(root), "deploy", "prod abc - pass", outcome="pass")

    err = capsys.readouterr().err
    assert (result, len(telegram.requests), "overrides the global provider 'telegram'" in err,
            "notify.provider is none" in err) == ("off", 0, True, True)


def test_example_chat_id_counts_as_unset(tmp_path, monkeypatch, telegram):
    skill = tmp_path / "skill.json"
    skill.write_text(json.dumps({"telegram": {"bot_token_env": TOKEN_ENV,
                                              "chat_id": crew_notify.EXAMPLE_CHAT_ID}}),
                     encoding="utf-8")
    monkeypatch.setattr(crew_notify, "SKILL_CONFIG_PATH", str(skill))
    root = _repo(tmp_path, notify={"provider": "telegram", "tokenEnv": None, "chatId": None,
                                   "events": ["deploy"]})

    result = crew_notify.send(str(root), "deploy", "prod abc - pass", outcome="pass")

    assert (result, len(telegram.requests)) == ("missing-credentials", 0)


def test_fallback_never_sets_provider(tmp_path, monkeypatch):
    skill = tmp_path / "skill.json"
    skill.write_text(json.dumps({"telegram": {"bot_token_env": TOKEN_ENV, "chat_id": 5}}),
                     encoding="utf-8")
    monkeypatch.setattr(crew_notify, "SKILL_CONFIG_PATH", str(skill))
    root = _repo(tmp_path, notify={"provider": None})

    cfg, _ = crew_notify.effective_config(str(root))

    assert (cfg["provider"], cfg["chatId"]) == (None, None)


def test_event_not_in_events_sends_nothing(tmp_path, telegram, capsys):
    root = _repo(tmp_path, notify={"provider": "telegram", "tokenEnv": TOKEN_ENV,
                                   "chatId": CHAT, "events": ["question"]})

    result = crew_notify.send(str(root), "deploy", "prod abc - FAILED at gate 2", outcome="fail")

    assert (result, len(telegram.requests), "not in notify.events" in capsys.readouterr().err) == (
        "filtered", 0, True)


def test_reserved_blocker_sends_nothing_and_names_t0060(tmp_path, telegram, capsys):
    root = _repo(tmp_path, notify={"provider": "telegram", "tokenEnv": TOKEN_ENV,
                                   "chatId": CHAT, "events": ["blocker", "deploy", "question"]})

    result = crew_notify.send(str(root), "blocker", "out of review rounds")

    assert (result, len(telegram.requests), "T-0060" in capsys.readouterr().err) == (
        "filtered", 0, True)


def test_missing_token_sends_nothing_and_says_why(tmp_path, telegram, monkeypatch, capsys):
    monkeypatch.delenv(TOKEN_ENV)
    root = _repo(tmp_path)

    result = crew_notify.send(str(root), "deploy", "prod abc - pass", outcome="pass")

    assert (result, len(telegram.requests), "missing" in capsys.readouterr().err) == (
        "missing-credentials", 0, True)


# --- step 3: send, state, dedupe -------------------------------------------------------------

def test_send_confirmed_advances_state(tmp_path, telegram):
    root = _repo(tmp_path)

    result = crew_notify.send(str(root), "deploy", "prod abc - pass", outcome="pass")

    sent = json.loads((_state(root) / "sent.json").read_text(encoding="utf-8"))
    assert (result, len(sent)) == ("sent", 1)


@pytest.mark.parametrize("reply", [
    pytest.param((500, {"ok": False, "description": "boom"}, 0), id="http-500"),
    pytest.param((200, {"ok": False, "description": "nope"}, 0), id="ok-false"),
    pytest.param((200, {"ok": True}, 1.5), id="timeout"),
])
def test_failed_send_does_not_advance_state(tmp_path, telegram, monkeypatch, reply):
    monkeypatch.setattr(crew_notify, "HTTP_TIMEOUT", 0.5)
    telegram.responses.append(reply)
    root = _repo(tmp_path)

    first = crew_notify.send(str(root), "deploy", "prod abc - pass", outcome="pass")
    second = crew_notify.send(str(root), "deploy", "prod abc - pass", outcome="pass")

    assert (first.startswith("failed:"), second, (_state(root) / "sent.json").exists()) == (
        True, "sent", True)
    assert len(json.loads((_state(root) / "sent.json").read_text(encoding="utf-8"))) == 1


def test_dedupe_inside_window_sends_once(tmp_path, telegram):
    root = _repo(tmp_path)

    results = [crew_notify.send(str(root), "deploy", "prod abc - pass", outcome="pass")
               for _ in range(2)]

    assert (results, len(telegram.requests)) == (["sent", "deduped"], 1)


def test_realert_after_window(tmp_path, telegram):
    root = _repo(tmp_path)
    crew_notify.send(str(root), "deploy", "prod abc - pass", outcome="pass")
    path = _state(root) / "sent.json"
    aged = {key: value - 7 * 3600 for key, value in
            json.loads(path.read_text(encoding="utf-8")).items()}
    path.write_text(json.dumps(aged), encoding="utf-8")

    result = crew_notify.send(str(root), "deploy", "prod abc - pass", outcome="pass")

    assert (result, len(telegram.requests)) == ("sent", 2)


def test_429_retry_after_honoured(tmp_path, telegram):
    telegram.responses.append((429, {"ok": False, "parameters": {"retry_after": 2}}, 0))
    root = _repo(tmp_path)

    result = crew_notify.send(str(root), "deploy", "prod abc - pass", outcome="pass")

    gap = telegram.requests[1]["at"] - telegram.requests[0]["at"]
    assert (result, len(telegram.requests), gap >= 1.9) == ("sent", 2, True)


def test_429_retry_after_zero_retries_at_once(tmp_path, telegram):
    telegram.responses.append((429, {"ok": False, "parameters": {"retry_after": 0}}, 0))
    root = _repo(tmp_path)

    result = crew_notify.send(str(root), "deploy", "prod abc - pass", outcome="pass")

    gap = telegram.requests[1]["at"] - telegram.requests[0]["at"]
    assert (result, len(telegram.requests), gap < 0.9) == ("sent", 2, True)


def test_429_over_budget_gives_up_without_advancing(tmp_path, telegram):
    telegram.responses.append((429, {"ok": False, "parameters": {"retry_after": 30}}, 0))
    root = _repo(tmp_path)
    began = time.monotonic()

    result = crew_notify.send(str(root), "deploy", "prod abc - pass", outcome="pass")

    assert (result.startswith("failed:"), len(telegram.requests),
            time.monotonic() - began < 5, (_state(root) / "sent.json").exists()) == (
                True, 1, True, False)


def test_html_escaped(tmp_path, telegram):
    root = _repo(tmp_path)

    crew_notify.send(str(root), "deploy", "prod <b>abc</b> & more - pass", outcome="pass")

    form = telegram.requests[0]["form"]
    assert (form["parse_mode"], "&lt;b&gt;abc&lt;/b&gt; &amp; more" in form["text"]) == (
        "HTML", True)


def test_pace_one_second(tmp_path, telegram, monkeypatch):
    monkeypatch.setattr(crew_notify, "PACE_SECONDS", 1.0)
    root = _repo(tmp_path)

    crew_notify.send(str(root), "deploy", "prod one - pass", outcome="pass")
    crew_notify.send(str(root), "deploy", "prod two - pass", outcome="pass")

    assert telegram.requests[1]["at"] - telegram.requests[0]["at"] >= 0.95


@pytest.mark.parametrize("override,base", [
    ("http://127.0.0.1:8080", "http://127.0.0.1:8080"),
    ("https://localhost:9/x/", "https://localhost:9/x/"),
    ("http://[::1]:7", "http://[::1]:7"),
    ("https://evil.example", crew_notify.TELEGRAM_BASE),
    ("http://localhost.evil.example", crew_notify.TELEGRAM_BASE),
    ("http://127.0.0.1@evil.example", crew_notify.TELEGRAM_BASE),
    ("http://127.0.0.1.evil.example:80", crew_notify.TELEGRAM_BASE),
    ("ftp://127.0.0.1", crew_notify.TELEGRAM_BASE),
    ("http://127.0.0.1:notaport", crew_notify.TELEGRAM_BASE),
])
def test_telegram_base_override_is_loopback_only(monkeypatch, override, base):
    monkeypatch.setenv("CREW_NOTIFY_TELEGRAM_BASE", override)

    assert crew_notify.telegram_base() == base


def test_non_loopback_override_never_receives_the_token(tmp_path, monkeypatch, capsys):
    """CREW_NOTIFY_TELEGRAM_BASE from a cloned repo's settings `env` names an
    attacker's host: the send goes to api.telegram.org, not there."""
    dialled = []

    class _Reply:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *_exc):
            return False

        def read(self):
            return b'{"ok": true}'

    def _open(request):
        dialled.append(request.full_url)
        return _Reply()

    monkeypatch.setattr(crew_notify, "_open", _open)
    monkeypatch.setenv("CREW_NOTIFY_TELEGRAM_BASE", "https://evil.example")
    root = _repo(tmp_path)

    result = crew_notify.send(str(root), "deploy", "prod abc - pass", outcome="pass")

    assert (result, dialled, "not a loopback" in capsys.readouterr().err) == (
        "sent", [f"https://api.telegram.org/bot{TOKEN}/sendMessage"], True)


@pytest.mark.parametrize("reason,kind", [
    ("prod abc - gate 3 broke", "unknown"), ("", "unknown"),
    ("prod abc - FAILED at gate 3", "fail"), ("prod abc - pass", "pass"),
    ("qa abc - passed", "pass"), ("prod abc - passed gate 1, FAILED at gate 2", "unknown"),
    ("prod bypass-abc - done", "unknown"),
])
def test_outcome_unknown_never_collapses_to_pass(reason, kind):
    assert crew_notify._outcome(None, reason) == kind  # pylint: disable=protected-access


def test_unknown_outcome_sends_loud_and_not_as_a_pass(tmp_path, telegram):
    root = _repo(tmp_path)

    crew_notify.send(str(root), "deploy", "prod abc - gate 3 broke")

    assert (_text(telegram).startswith("Promotion outcome unknown ["),
            telegram.requests[0]["form"]["disable_notification"]) == (True, "false")


def test_deploy_pass_is_silent_fail_is_loud(tmp_path, telegram):
    root = _repo(tmp_path)

    crew_notify.send(str(root), "deploy", "prod abc - pass", outcome="pass")
    crew_notify.send(str(root), "deploy", "prod abc - FAILED at gate 3", outcome="fail")

    flags = [request["form"]["disable_notification"] for request in telegram.requests]
    assert flags == ["true", "false"]


def test_question_is_loud(tmp_path, telegram):
    root = _repo(tmp_path)

    _hook(root, _payload("permission_prompt", root))

    assert telegram.requests[0]["form"]["disable_notification"] == "false"


# --- step 3: the line ------------------------------------------------------------------------

@pytest.mark.parametrize("key", sorted(crew_notify.SUBJECTS))
def test_subject_leads_every_line(tmp_path, telegram, key):
    root = _repo(tmp_path)
    event, kind = key
    if event == "deploy":
        crew_notify.send(str(root), "deploy", "prod abc - result", outcome=kind)
    else:
        crew_notify.send(str(root), "question", "Claude needs your permission", kind=kind)

    line = _text(telegram)
    assert line.startswith(crew_notify.SUBJECTS[key] + " [repo/")


def test_line_has_no_newline(tmp_path, telegram):
    root = _repo(tmp_path)

    crew_notify.send(str(root), "deploy", "prod\nabc\r\n- pass", outcome="pass",
                     unblock="run\nthis")

    assert ("\n" in _text(telegram), "\r" in _text(telegram)) == (False, False)


def test_reason_capped(tmp_path, telegram):
    root = _repo(tmp_path)

    crew_notify.send(str(root), "deploy", "x" * 1000, outcome="pass")

    assert "x" * crew_notify.MAX_REASON + "x" not in _text(telegram)


def test_line_never_says_waiting_on_you(tmp_path, telegram):
    root = _repo(tmp_path)
    transcript = _write_transcript(tmp_path / "t.jsonl", _BASH_LINES)

    _hook(root, _payload("permission_prompt", root, transcript=transcript))

    assert "waiting on you" not in _text(telegram)


def test_context_askuserquestion_question_text(tmp_path):
    transcript = _write_transcript(tmp_path / "t.jsonl", _ASK_LINES)

    got = crew_notify.context(transcript)

    assert (got["excerpt"], got["tool"]) == ("Which colour should the probe be?", "AskUserQuestion")


def test_context_last_assistant_text(tmp_path):
    lines = _ASK_LINES[:6]
    transcript = _write_transcript(tmp_path / "t.jsonl", lines + [
        {"type": "assistant", "uuid": "z1", "message": {"content": [
            {"type": "text", "text": "Shall I merge it?\nSecond line never shown."}]}},
        {"type": "user", "uuid": "z2", "message": {"content": "later"}}])

    assert crew_notify.context(transcript)["excerpt"] == "Shall I merge it?"


def test_context_excerpt_capped(tmp_path):
    transcript = _write_transcript(tmp_path / "t.jsonl", [
        {"type": "assistant", "uuid": "z1", "message": {"content": [
            {"type": "text", "text": "y" * 900}]}}])

    assert len(crew_notify.context(transcript)["excerpt"]) == crew_notify.MAX_EXCERPT


def test_context_unreadable_transcript_still_sends(tmp_path, telegram):
    root = _repo(tmp_path)

    result = _hook(root, _payload("permission_prompt", root,
                                  transcript=str(tmp_path / "missing.jsonl")))

    assert (result, "Claude needs your permission" in _text(telegram)) == ("sent", True)


def test_context_reads_the_tail_of_a_huge_transcript(tmp_path, monkeypatch):
    monkeypatch.setattr(crew_notify, "BIG_TRANSCRIPT", 1024)
    monkeypatch.setattr(crew_notify, "TAIL_BYTES", 2048)
    filler = [{"type": "user", "uuid": f"f{i}", "message": {"content": "z" * 200}}
              for i in range(100)]
    transcript = _write_transcript(tmp_path / "t.jsonl", filler + _ASK_LINES)

    assert crew_notify.context(transcript)["tool"] == "AskUserQuestion"


def test_detached_head_shows_ticket_not_HEAD(tmp_path, telegram):  # pylint: disable=invalid-name
    root = _repo(tmp_path)
    subprocess.run(["git", "checkout", "-q", "--detach"], cwd=root, check=True)

    crew_notify.send(str(root), "deploy", "prod abc - pass", outcome="pass")

    line = _text(telegram)
    assert ("[repo/T-0042]" in line, "HEAD" in line) == (True, False)


def test_line_names_ticket_and_phase(tmp_path, telegram):
    root = _repo(tmp_path)

    crew_notify.send(str(root), "deploy", "prod abc - pass", outcome="pass",
                     unblock="/crew:promote prod")

    assert _text(telegram) == ("Promotion passed [repo/main] T-0042 (implement) prod abc - pass"
                               " -> /crew:promote prod")


# --- step 3: episodes ------------------------------------------------------------------------

def test_same_prompt_id_pings_once_new_prompt_id_pings_again(tmp_path, telegram):
    root = _repo(tmp_path)
    bash = _write_transcript(tmp_path / "bash.jsonl", _BASH_LINES)
    ask = _write_transcript(tmp_path / "ask.jsonl", _ASK_LINES)

    results = [_hook(root, _payload("permission_prompt", root, prompt="p-1", transcript=bash)),
               _hook(root, _payload("permission_prompt", root, prompt="p-1", transcript=ask)),
               _hook(root, _payload("permission_prompt", root, prompt="p-2", transcript=ask))]

    assert (results, len(telegram.requests)) == (["sent", "episode", "sent"], 2)


def test_episode_falls_back_to_the_assistant_uuid(tmp_path, telegram):
    root = _repo(tmp_path)
    ask = _write_transcript(tmp_path / "ask.jsonl", _ASK_LINES)

    results = [_hook(root, _payload("permission_prompt", root, prompt=None, transcript=ask))
               for _ in range(2)]

    assert results == ["sent", "episode"]


def test_two_idle_prompts_send_nothing(tmp_path, telegram):
    root = _repo(tmp_path)

    results = [_hook(root, _payload("idle_prompt", root, message="Claude is waiting for your "
                                    "input")) for _ in range(2)]

    assert (results, len(telegram.requests)) == (["quiet", "quiet"], 0)


# --- redaction -------------------------------------------------------------------------------

def _all_state(root):
    folder = _state(root)
    return "".join(path.read_text(encoding="utf-8") for path in folder.glob("*")
                   if path.is_file()) if folder.exists() else ""


def test_redact_transcript_token_never_sent_or_stored(tmp_path, telegram):
    root = _repo(tmp_path)
    secret = "ghp_" + "Q" * 36
    transcript = _write_transcript(tmp_path / "t.jsonl", [
        {"type": "assistant", "uuid": "z1", "message": {"content": [
            {"type": "text", "text": f"I will push with {secret} and {TOKEN} now"}]}}])

    _hook(root, _payload("permission_prompt", root, transcript=transcript))

    sent = _text(telegram)
    assert (secret in sent, TOKEN in sent, "[redacted]" in sent,
            secret in _all_state(root), TOKEN in _all_state(root)) == (
                False, False, True, False, False)


@pytest.mark.parametrize("text,leaks", [
    ("Bearer abcdefghijklmnop", "abcdefghijklmnop"),
    ("key sk-" + "a" * 20, "sk-" + "a" * 20),
    ("xoxb-" + "1" * 20, "xoxb-" + "1" * 20),
    ("AKIA" + "B" * 16, "AKIA" + "B" * 16),
    ("github_pat_" + "c" * 30, "github_pat_" + "c" * 30),
])
def test_redact_deny_list(text, leaks):
    assert leaks not in crew_notify.redact(text)


def test_token_never_in_output_or_state(tmp_path, telegram, capsys, monkeypatch):
    root = _repo(tmp_path)
    transcript = _write_transcript(tmp_path / "t.jsonl", [
        {"type": "assistant", "uuid": "z1", "message": {"content": [
            {"type": "text", "text": f"token {TOKEN}"}]}}])
    _hook(root, _payload("permission_prompt", root, transcript=transcript, message=TOKEN))
    _hook(root, _payload(f"weird_{TOKEN}", root))
    _hook(root, _payload(None, root))
    crew_notify.send(str(root), "deploy", f"prod {TOKEN} - pass", outcome="pass")
    telegram.responses.append((500, {"ok": False, "description": TOKEN}, 0))
    crew_notify.send(str(root), "deploy", "prod other - FAILED", outcome="fail")
    monkeypatch.setenv("CREW_NOTIFY_TELEGRAM_BASE", "http://127.0.0.1:9")
    crew_notify.send(str(root), "deploy", "prod third - pass", outcome="pass")
    crew_notify.show_config(str(root))

    out = capsys.readouterr()
    sent = "".join(html.unescape(request["form"]["text"]) for request in telegram.requests)
    assert (TOKEN in out.out, TOKEN in out.err, TOKEN in sent, TOKEN in _all_state(root)) == (
        False, False, False, False)


# --- teams, and never failing ------------------------------------------------------------------

def test_teams_branch_posts_card(tmp_path, telegram, monkeypatch):
    base = os.environ["CREW_NOTIFY_TELEGRAM_BASE"]
    monkeypatch.setenv("CREW_TEST_TEAMS_URL", base + "/teams")
    _global(tmp_path, monkeypatch, {"tokenEnv": TOKEN_ENV, "urlEnv": "CREW_TEST_TEAMS_URL"})
    root = _repo(tmp_path, notify={"provider": "teams", "urlEnv": "CREW_TEST_TEAMS_URL",
                                   "events": ["deploy"]})

    result = crew_notify.send(str(root), "deploy", "prod abc - pass", outcome="pass")

    card = json.loads(telegram.requests[0]["raw"])
    text = card["attachments"][0]["content"]["body"][0]["text"]
    assert (result, telegram.requests[0]["path"], text.startswith("Promotion passed [")) == (
        "sent", "/teams", True)


class _Redirector(http.server.BaseHTTPRequestHandler):
    """Answers every POST with a 302 to `location` (the fake Telegram's port)."""
    location = ""
    hits = []

    def do_POST(self):  # pylint: disable=invalid-name
        _Redirector.hits.append(self.path)
        self.rfile.read(int(self.headers.get("Content-Length") or 0))
        self.send_response(302)
        self.send_header("Location", _Redirector.location + self.path)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def log_message(self, *_args):  # pylint: disable=arguments-differ
        pass


@pytest.fixture(name="redirector")
def _redirector_fixture(telegram):
    """A loopback server that 302s to the fake Telegram on another port; the
    fake Telegram counts any request that follows the redirect."""
    _Redirector.hits = []
    _Redirector.location = os.environ["CREW_NOTIFY_TELEGRAM_BASE"]
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Redirector)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
    server.server_close()


def test_telegram_redirect_is_not_followed(tmp_path, monkeypatch, telegram, redirector, capsys):
    """A 302 must not become a second request (a GET with the token in its path):
    it is a failed send, and the dedupe record does not advance."""
    monkeypatch.setenv("CREW_NOTIFY_TELEGRAM_BASE", redirector)
    root = _repo(tmp_path)

    result = crew_notify.send(str(root), "deploy", "prod abc - pass", outcome="pass")

    assert (result, _Redirector.hits, telegram.requests, "HTTP 302" in capsys.readouterr().err
            ) == ("failed:HTTP 302", [f"/bot{TOKEN}/sendMessage"], [], True)


def test_teams_redirect_is_not_followed(tmp_path, monkeypatch, telegram, redirector):
    monkeypatch.setenv("CREW_TEST_TEAMS_URL", redirector + "/teams")
    _global(tmp_path, monkeypatch, {"urlEnv": "CREW_TEST_TEAMS_URL"})
    root = _repo(tmp_path, notify={"provider": "teams", "events": ["deploy"]})

    result = crew_notify.send(str(root), "deploy", "prod abc - pass", outcome="pass")

    assert (result, _Redirector.hits, telegram.requests) == ("failed:HTTP 302", ["/teams"], [])


def test_redirected_send_still_exits_0(tmp_path, telegram, redirector):
    """The CLI hook path through a 302: exit 0, nothing reaches the redirect target."""
    root = _repo(tmp_path)
    home = tmp_path / "cli-home"
    (home / ".claude" / "crew").mkdir(parents=True)
    (home / ".claude" / "crew" / "config.json").write_text(
        json.dumps({"notify": {"tokenEnv": TOKEN_ENV}}), encoding="utf-8")

    run = _cli(root, "send", "--event", "deploy", "--outcome", "pass", "--reason", "prod - pass",
               env={"HOME": str(home), "USERPROFILE": str(home),
                    "CREW_NOTIFY_TELEGRAM_BASE": redirector})

    assert (run.returncode, len(_Redirector.hits), telegram.requests,
            b"HTTP 302" in run.stderr) == (0, 1, [], True)


def _cli(root, *args, stdin=b"", env=None):
    script = pathlib.Path(crew_notify.__file__)
    full = dict(os.environ, **(env or {}))
    return subprocess.run(["python3", str(script), *args, "--root", str(root)], input=stdin,
                          capture_output=True, check=False, timeout=60, env=full)


@pytest.mark.parametrize("case", ["bad-config", "unreadable-state", "network-down",
                                  "garbage-stdin", "bad-args"])
def test_every_entry_point_exits_0(tmp_path, case):
    root = _repo(tmp_path)
    env = {"HOME": str(tmp_path / "home"), "USERPROFILE": str(tmp_path / "home"),
           "CREW_NOTIFY_TELEGRAM_BASE": "http://127.0.0.1:9"}
    if case == "bad-config":
        (root / ".crew" / "config.json").write_text("{not json", encoding="utf-8")
    if case == "unreadable-state":
        state = pathlib.Path(crew_notify.state_dir(str(root)))
        state.parent.mkdir(parents=True, exist_ok=True)
        state.write_text("a file where a directory belongs", encoding="utf-8")
    runs = [_cli(root, "send", "--event", "deploy", "--reason", "prod - pass", env=env),
            _cli(root, "hook", stdin=b"\x00garbage" if case == "garbage-stdin" else
                 json.dumps(_payload("permission_prompt", root)).encode(), env=env),
            _cli(root, "config", env=env)]
    if case == "bad-args":
        runs.append(_cli(root, "send", "--outcome", "maybe", env=env))

    assert [run.returncode for run in runs] == [0] * len(runs)


def test_shipped_defaults_send_nothing(tmp_path, monkeypatch, telegram, capsys):
    """Off by default: a repo written from the shipped template under the
    shipped global template sends nothing, for a question or a deploy."""
    template = json.loads((pathlib.Path(crew_config.__file__).resolve().parent.parent.parent
                           / "templates" / "config.template.json").read_text(encoding="utf-8"))
    root = _repo(tmp_path, notify=template["notify"])
    _global(tmp_path, monkeypatch, crew_config.default_global_config()["notify"])

    words = (crew_notify.hook(str(root), json.dumps(_payload("permission_prompt", root)).encode()),
             crew_notify.send(str(root), "deploy", "qa abc - FAILED at gate 2", outcome="fail"))

    assert (words, telegram.requests, "notify.provider is none" in capsys.readouterr().err) == (
        ("off", "off"), [], True)


# --- credentials as a Windows host had them (2026-10-05) --------------------------------------

@pytest.mark.parametrize("raw", [TOKEN + "\r\n", TOKEN + " ", "  " + TOKEN + "\t\n"],
                         ids=["crlf", "space", "both-ends"])
def test_a_token_with_surrounding_whitespace_is_stripped_and_sent(tmp_path, telegram,
                                                                  monkeypatch, raw):
    monkeypatch.setenv(TOKEN_ENV, raw)
    root = _repo(tmp_path, {"provider": "telegram", "chatId": " " + CHAT + " ",
                            "events": ["deploy"]})

    result = crew_notify.send(str(root), "deploy", "prod abc - pass", outcome="pass")

    assert (result, [r["path"] for r in telegram.requests],
            telegram.requests[0]["form"]["chat_id"]) == ("sent", [f"/bot{TOKEN}/sendMessage"], CHAT)


@pytest.mark.parametrize("bad", ["123456:AB CD", "not-a-token", TOKEN + " " + TOKEN])
def test_a_value_that_cannot_be_a_bot_token_sends_nothing_and_says_so(tmp_path, telegram,
                                                                      monkeypatch, capsys, bad):
    monkeypatch.setenv(TOKEN_ENV, bad)
    root = _repo(tmp_path)

    result = crew_notify.send(str(root), "deploy", "prod abc - pass", outcome="pass")

    err = capsys.readouterr().err
    assert (result, len(telegram.requests)) == ("missing-credentials", 0)
    assert "does not look like a Telegram bot token" in err and "AB CD" not in err


@pytest.mark.parametrize("glob,env,repo_chat,says", [
    pytest.param({}, None, CHAT, "notify.tokenEnv is not set in ~/.claude/crew/config.json or",
                 id="no-token-env"),
    pytest.param({"tokenEnv": TOKEN_ENV}, "", CHAT, f"token missing: ${TOKEN_ENV} is empty",
                 id="empty-token"),
    pytest.param({"tokenEnv": TOKEN_ENV}, TOKEN, None, "chatId missing: set notify.chatId",
                 id="no-chat"),
])
def test_a_missing_credential_names_which_one_and_where(tmp_path, monkeypatch, capsys,
                                                       glob, env, repo_chat, says):
    _global(tmp_path, monkeypatch, glob)
    if env is None:
        monkeypatch.delenv(TOKEN_ENV)
    else:
        monkeypatch.setenv(TOKEN_ENV, env)
    root = _repo(tmp_path, {"provider": "telegram", "chatId": repo_chat, "events": ["deploy"]})

    result = crew_notify.send(str(root), "deploy", "prod abc - pass", outcome="pass")

    assert result == "missing-credentials"
    assert says in capsys.readouterr().err


@pytest.mark.parametrize("reply,why", [
    pytest.param((400, {"ok": False, "description": "Bad Request: chat not found"}, 0),
                 "HTTP 400: Bad Request: chat not found", id="http-400"),
    pytest.param((401, {"ok": False, "description": "Unauthorized"}, 0),
                 "HTTP 401: Unauthorized", id="http-401"),
    pytest.param((200, {"ok": False, "description": "Forbidden: bot was blocked"}, 0),
                 "ok: false: Forbidden: bot was blocked", id="ok-false"),
])
def test_a_refusal_names_telegrams_reason(tmp_path, telegram, capsys, reply, why):
    telegram.responses.append(reply)
    root = _repo(tmp_path)

    result = crew_notify.send(str(root), "deploy", "prod abc - pass", outcome="pass")

    err = capsys.readouterr().err
    assert result == f"failed:{why}" and f"send failed: {why}" in err
    assert TOKEN not in err

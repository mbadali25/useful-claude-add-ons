"""The wrappers, the hook entry and the callers around crew_notify.py (T-0051).

notify.sh and notify.ps1 are thin: every rule lives in crew_notify.py, once.
These hold the wrappers to that, hold hooks.json to one unfiltered entry per
flavour, hold the commands to the retired pings staying retired, and run one
payload set through each wrapper against a fake Telegram.
"""
import http.server
import json
import os
import pathlib
import re
import subprocess
import threading
import urllib.parse

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import crew_fixtures
from review_fixtures import init_repo
from sabotage_notify import NOTIFY_MUTATIONS

CREW = pathlib.Path(__file__).resolve().parent.parent
SCRIPTS = CREW / "hooks" / "scripts"
COMMANDS = CREW / "commands"
PWSH = crew_fixtures.resolve_pwsh()
BASH = crew_fixtures.resolve_bash()
TOKEN = "123456789:" + "AbCdEfGhIjKlMnOpQrStUvWxYz0123456789"


def _read(path):
    return pathlib.Path(path).read_text(encoding="utf-8")


def _ps1_without_python_probe():
    """notify.ps1 minus Resolve-CrewPython, whose shared probe legitimately
    parses JSON (tests/test_ps1_python_probe.py holds it byte for byte)."""
    text = _read(SCRIPTS / "notify.ps1")
    start = text.index("function Resolve-CrewPython")
    end = text.index("function Format-CrewProcessArgument")
    return text[:start] + text[end:]


def test_notify_ps1_has_no_send_logic():
    text = _ps1_without_python_probe()

    assert ("crew_notify.py" in text,
            [word for word in ("api.telegram.org", "Invoke-RestMethod", "ConvertFrom-Json",
                               "config.json") if word in text]) == (True, [])


def test_notify_sh_has_no_send_logic():
    text = _read(SCRIPTS / "notify.sh")

    assert ("crew_notify.py" in text,
            [word for word in ("curl", "config.json", "api.telegram.org") if word in text]) == (
                True, [])


def test_hooks_json_notification_passes_hook_and_no_matcher():
    entries = json.loads(_read(CREW / "hooks" / "hooks.json"))["hooks"]["Notification"]

    commands = [hook["command"] for entry in entries for hook in entry["hooks"]]
    assert ([("matcher" in entry) for entry in entries], len(commands),
            all(re.search(r'notify\.(sh|ps1)\\?" hook(;|$)', command) for command in commands)) == (
                [False, False], 2, True)


# --- the callers ------------------------------------------------------------------------------

_RETIRED = (COMMANDS / "review.md", COMMANDS / "done.md", COMMANDS / "init.md",
            SCRIPTS / "context-watch.sh", SCRIPTS / "context-watch.ps1")


def test_retired_callers_gone():
    calls = {path.name: [line for line in _read(path).splitlines()
                         if re.search(r"notify\.(sh|ps1)", line)] for path in _RETIRED}

    assert (calls, "--event deploy" in _read(COMMANDS / "promote.md")) == (
        {path.name: [] for path in _RETIRED}, True)


def test_promote_sends_deploy_for_every_result():
    """The deploy line carries --outcome and sits after both result branches,
    not inside the all-green one."""
    text = _read(COMMANDS / "promote.md")
    line = next(line for line in text.splitlines() if "crew_notify.py send" in line)
    after_pass = text.index("**All gates green:**")
    after_fail = text.index("**Any gate failed:**")

    assert ("--outcome <pass|fail>" in line, text.index(line) > max(after_pass, after_fail),
            "for every result" in text) == (True, True, True)


# --- sabotage anchors -------------------------------------------------------------------------

@pytest.mark.parametrize("mutation", NOTIFY_MUTATIONS, ids=[m[0] for m in NOTIFY_MUTATIONS])
def test_every_notify_sabotage_anchor_is_present_exactly_once(mutation):
    _label, target, find, _replace, test = mutation

    assert (_read(target).count(find), (CREW / test.split("::")[0]).is_file()) == (1, True)


# --- the wrappers against a fake Telegram ----------------------------------------------------

class _Fake(http.server.BaseHTTPRequestHandler):
    texts = []

    def do_POST(self):  # pylint: disable=invalid-name
        body = self.rfile.read(int(self.headers.get("Content-Length") or 0)).decode("utf-8")
        _Fake.texts.append(urllib.parse.parse_qs(body).get("text", [""])[0])
        data = b'{"ok": true, "result": {}}'
        self.send_response(200)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *_args):  # pylint: disable=arguments-differ
        pass


@pytest.fixture(name="fake")
def _fake_telegram():
    _Fake.texts = []
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Fake)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
    server.server_close()


def _repo(tmp_path, name):
    root = init_repo(tmp_path / name)
    (root / ".crew").mkdir()
    (root / ".crew" / "config.json").write_text(json.dumps({"notify": {
        "provider": "telegram", "tokenEnv": "CREW_TEST_TG_TOKEN", "chatId": "4242",
        "events": ["deploy", "question"], "realertHours": 6, "questionTypes": None}}),
        encoding="utf-8")
    return root


_PARITY = [("permission_prompt", "p-1"), ("elicitation_dialog", "p-2"),
           ("agent_needs_input", "p-3"), ("idle_prompt", "p-4"), (None, "p-5"),
           ("brand_new_type", "p-6")]


def _payload(root, ntype, prompt):
    out = {"session_id": "parity", "hook_event_name": "Notification", "cwd": str(root),
           "message": "Claude needs your permission", "prompt_id": prompt,
           "transcript_path": str(root / "missing.jsonl")}
    if ntype:
        out["notification_type"] = ntype
    return json.dumps(out).encode()


def _env(root, base, windows):
    env = dict(os.environ, CLAUDE_PROJECT_DIR=str(root), CREW_NOTIFY_TELEGRAM_BASE=base,
               CREW_TEST_TG_TOKEN=TOKEN)
    env.pop("OS", None)
    if windows:
        env["OS"] = "Windows_NT"
    return env


def _through(flavour, root, base):
    before = len(_Fake.texts)
    for ntype, prompt in _PARITY:
        if flavour == "sh":
            cmd = [BASH, str(SCRIPTS / "notify.sh"), "hook"]
        else:
            cmd = [PWSH, "-NoProfile", "-File", str(SCRIPTS / "notify.ps1"), "hook"]
        done = subprocess.run(cmd, input=_payload(root, ntype, prompt), cwd=str(root),
                              env=_env(root, base, flavour == "ps1"), capture_output=True,
                              check=False, timeout=120)
        assert done.returncode == 0, done.stderr
    return len(_Fake.texts) - before


@pytest.mark.skipif(BASH is None, reason="needs bash")
def test_notify_sh_hook_sends_the_question_types_only(tmp_path, fake):
    assert _through("sh", _repo(tmp_path, "sh"), fake) == 3


@pytest.mark.skipif(PWSH is None or BASH is None,
                    reason="needs pwsh and bash - the parity run was NOT made")
def test_wrapper_parity_under_pwsh(tmp_path, fake):
    counts = (_through("sh", _repo(tmp_path, "sh"), fake),
              _through("ps1", _repo(tmp_path, "ps1"), fake))

    assert counts == (3, 3)


@pytest.mark.skipif(BASH is None, reason="needs bash")
@pytest.mark.parametrize("legacy,subject", [("gate", "Promotion passed"),
                                            ("waiting", "Question")])
def test_legacy_cli_call_is_mapped_not_dropped(tmp_path, fake, legacy, subject):
    root = _repo(tmp_path, "legacy")

    done = subprocess.run([BASH, str(SCRIPTS / "notify.sh"), legacy, "qa abc - pass"],
                          cwd=str(root), env=_env(root, fake, False), capture_output=True,
                          stdin=subprocess.DEVNULL, check=False, timeout=60)

    assert (done.returncode, [text.split(" [")[0] for text in _Fake.texts]) == (0, [subject])


@pytest.mark.skipif(BASH is None, reason="needs bash")
def test_the_token_never_reaches_wrapper_output(tmp_path, fake):
    root = _repo(tmp_path, "leak")
    env = _env(root, "http://127.0.0.1:9", False)

    done = subprocess.run([BASH, str(SCRIPTS / "notify.sh"), "hook"],
                          input=_payload(root, "permission_prompt", "p-1"), cwd=str(root),
                          env=env, capture_output=True, check=False, timeout=60)

    assert TOKEN.encode() not in done.stdout + done.stderr

"""The Windows direction of the flavour guard: both flavours run.

test_flavour_guard.py proves each .ps1 stands down OFF Windows. Nothing
proved what happens ON Windows, where hooks.json's two registrations per
event (bash `command` + `shell: "powershell"` twin) both proceed -- no .sh
stands down there, and must not (CLAUDE.md: "Branch on the tool, not the
OS"). The burn-in report (docs/review/06-windows-burn-in.md, 2c) named that
as the necessary condition for a double fire.

The rule these cases hold the hooks to:

* A hook that only EMITS (a ping, a transcript copy, a handoff skeleton, an
  injected note) emits exactly ONCE per event across both flavours. They
  take a per-event claim -- event_claim.py, crew_context.py's claim, or
  hook_once.py for once-per-session SessionStart work.
* A hook that BLOCKS keeps running in both flavours and both reach the same
  verdict. Never loosened to save the second run.

Simulated here with `OS=Windows_NT` for the .ps1 (so its flavour guard
proceeds) and the .sh run as-is, on the same payload, in the same repo.
"""
import http.server
import json
import os
import pathlib
import subprocess
import threading
import time

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import crew_fixtures
import event_claim
from review_fixtures import init_repo
from scope_fixtures import edit, make_repo, ready, run_hook, stop

SCRIPTS = pathlib.Path(__file__).resolve().parent.parent / "hooks" / "scripts"
PWSH = crew_fixtures.resolve_pwsh()
BASH = crew_fixtures.resolve_bash()

pytestmark = pytest.mark.skipif(PWSH is None or BASH is None,
                                reason="needs pwsh and bash - the Windows direction was NOT run")


def _env(root, windows, **extra):
    env = dict(os.environ, CLAUDE_PROJECT_DIR=str(root))
    env.pop("OS", None)
    if windows:
        env["OS"] = "Windows_NT"
    env.update(extra)
    return env


def _run(flavour, stem, root, payload, args=(), **extra):
    data = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
    if flavour == "sh":
        cmd = [BASH, str(SCRIPTS / (stem + ".sh")), *args]
    else:
        cmd = [PWSH, "-NoProfile", "-File", str(SCRIPTS / (stem + ".ps1")), *args]
    return subprocess.run(cmd, input=data, cwd=str(root), capture_output=True,
                          env=_env(root, flavour == "ps1", **extra), check=False, timeout=120)


def _crew_repo(tmp_path, config):
    root = init_repo(tmp_path / "repo")
    (root / ".crew").mkdir()
    (root / ".crew" / "config.json").write_text(json.dumps(config), encoding="utf-8")
    return root


# --- emitting hooks: exactly one emission per event ------------------------------

class _Counter(http.server.BaseHTTPRequestHandler):
    hits = []

    def do_POST(self):  # pylint: disable=invalid-name
        length = int(self.headers.get("Content-Length") or 0)
        _Counter.hits.append(self.rfile.read(length))
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"{}")

    def log_message(self, *_args):  # pylint: disable=arguments-differ
        pass


@pytest.fixture(name="teams")
def _teams():
    _Counter.hits = []
    server = http.server.HTTPServer(("127.0.0.1", 0), _Counter)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}/hook"
    server.shutdown()


def _notify_repo(tmp_path):
    return _crew_repo(tmp_path, {"notify": {"provider": "teams", "urlEnv": "CREW_TEST_TEAMS_URL"}})


def _notification(root, message="Claude is waiting on you"):
    return {"hook_event_name": "Notification", "session_id": "win-1", "cwd": str(root),
            "message": message, "transcript_path": str(root / "t.jsonl")}


def _both_notify(root, url, payload):
    for flavour in ("sh", "ps1"):
        _run(flavour, "notify", root, payload, ("waiting", "Claude is waiting on you"),
             CREW_TEST_TEAMS_URL=url)
    return len(_Counter.hits)


def test_one_notification_sends_one_ping_across_both_flavours(tmp_path, teams):
    root = _notify_repo(tmp_path)

    assert _both_notify(root, teams, _notification(root)) == 1


def test_a_second_different_notification_is_its_own_event(tmp_path, teams):
    root = _notify_repo(tmp_path)
    _both_notify(root, teams, _notification(root))

    assert _both_notify(root, teams, _notification(root, "Permission needed")) == 2


def test_a_notify_call_with_no_payload_always_sends(tmp_path, teams):
    """A command calling notify.sh by hand (/crew:done, /crew:review) is not
    a hook event and has no twin to race."""
    root = _notify_repo(tmp_path)
    for _ in range(2):
        _run("sh", "notify", root, b"", ("done", "T-1 complete"), CREW_TEST_TEAMS_URL=teams)

    assert len(_Counter.hits) == 2


def test_one_precompact_writes_one_transcript_copy_across_both_flavours(tmp_path):
    """A second apart on purpose: the copy is named by the second it was
    taken, so two flavours in the SAME second would collapse to one file
    whether or not the claim works."""
    root = _crew_repo(tmp_path, {})
    transcript = root / "t.jsonl"
    transcript.write_text("{}\n", encoding="utf-8")
    payload = {"hook_event_name": "PreCompact", "session_id": "win-1", "cwd": str(root),
               "transcript_path": str(transcript), "trigger": "auto"}

    _run("sh", "handoff-write", root, payload)
    time.sleep(1.2)
    _run("ps1", "handoff-write", root, payload)

    assert len(list((root / ".crew" / "transcripts").glob("*.jsonl"))) == 1


def test_one_clear_prints_the_handoff_once_across_both_flavours(tmp_path):
    root = _crew_repo(tmp_path, {"memory": {"inject": False}})
    (root / ".work").mkdir()
    (root / ".work" / "HANDOFF.md").write_text("# Handoff\nnext: ship it\n", encoding="utf-8")
    payload = {"hook_event_name": "SessionStart", "session_id": "win-1", "cwd": str(root),
               "source": "clear"}

    outputs = [b"next: ship it" in _run(f, "handoff-read", root, payload).stdout
               for f in ("sh", "ps1")]

    assert outputs.count(True) == 1


def test_one_session_start_injects_context_once_across_both_flavours(tmp_path):
    root = _crew_repo(tmp_path, {})
    payload = {"hook_event_name": "SessionStart", "session_id": "win-1", "cwd": str(root),
               "source": "startup", "transcript_path": str(root / "t.jsonl")}

    outputs = [bool(_run(f, "crew-context", root, payload).stdout.strip()) for f in ("sh", "ps1")]

    assert outputs.count(True) == 1


def test_the_two_ps1_emitters_carry_the_one_claim_function_byte_for_byte():
    def claim_fn(stem):
        src = (SCRIPTS / (stem + ".ps1")).read_text(encoding="utf-8")
        start = src.index("function Test-CrewEventClaim(")
        return src[start:src.index("\n}\n", start) + 3]

    assert claim_fn("notify") == claim_fn("handoff-write")


# --- event_claim.py itself ------------------------------------------------------

def test_the_first_caller_emits_and_the_second_does_not(tmp_path):
    root = str(init_repo(tmp_path / "r"))
    raw = b'{"session_id":"s","hook_event_name":"Notification"}'

    assert (event_claim.claim(root, "notify", raw), event_claim.claim(root, "notify", raw)) \
        == (True, False)


def test_a_trailing_newline_or_bom_does_not_split_one_event_into_two(tmp_path):
    """bash's `$(cat)` drops trailing newlines; a PowerShell read can keep a
    BOM. Both flavours must land on the same key."""
    root = str(init_repo(tmp_path / "r"))
    raw = b'{"session_id":"s"}'
    event_claim.claim(root, "notify", raw + b"\n")

    assert event_claim.claim(root, "notify", b"\xef\xbb\xbf" + raw) is False


def test_an_identical_event_after_the_window_is_a_new_event(tmp_path):
    root = str(init_repo(tmp_path / "r"))
    raw = b'{"session_id":"s","message":"waiting"}'
    now = time.time()
    event_claim.claim(root, "notify", raw, now=now)
    later = now + event_claim.WINDOW + 1

    first = event_claim.claim(root, "notify", raw, now=later)
    second = event_claim.claim(root, "notify", raw, now=later + 0.5)

    assert (first, second) == (True, False)


def test_an_empty_payload_is_never_claimed(tmp_path):
    root = str(init_repo(tmp_path / "r"))

    assert [event_claim.claim(root, "notify", b"") for _ in range(2)] == [True, True]


def test_claims_live_in_the_git_common_dir_not_the_working_tree(tmp_path):
    root = init_repo(tmp_path / "r")
    event_claim.claim(str(root), "notify", b'{"session_id":"s"}')

    assert len(list((root / ".git" / "crew" / "event-claims").iterdir())) == 1


def test_a_lost_claim_exits_10_through_the_cli(tmp_path):
    root = init_repo(tmp_path / "r")
    cmd = [os.environ.get("PYTHON", "python3"), str(SCRIPTS / "event_claim.py"), "notify", "."]
    codes = [subprocess.run(cmd, input=b'{"session_id":"s"}', cwd=str(root), check=False,
                            capture_output=True, timeout=30).returncode for _ in range(2)]

    assert codes == [0, event_claim.LOST]


# --- blocking hooks: both flavours, same verdict --------------------------------

def _scope_repo(tmp_path):
    root = make_repo(tmp_path, mode="block")
    ready(root)
    return root


@pytest.mark.parametrize("stem,case,expected", [
    ("scope_guard", "in-scope edit", 0),
    ("scope_guard", "out-of-scope edit", 2),
    ("completion_audit", "clean stop", 0),
    ("completion_audit", "out-of-scope stop", 2),
])
def test_a_blocking_hook_reaches_the_same_verdict_in_both_flavours(tmp_path, stem, case, expected):
    root = _scope_repo(tmp_path)
    if case == "in-scope edit":
        payload = edit(root, root / "src" / "app.py", "Edit")
    elif case == "out-of-scope edit":
        payload = edit(root, root / "other" / "keep.py", "Edit")
    else:
        if case == "out-of-scope stop":
            (root / "other" / "keep.py").write_text("x = 2\n", encoding="utf-8")
        payload = stop(root)

    codes = [run_hook(flavour, stem, payload, root)[0] for flavour in ("sh", "ps1")]

    assert codes == [expected, expected]

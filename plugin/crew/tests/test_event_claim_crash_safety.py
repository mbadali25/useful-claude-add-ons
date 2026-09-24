"""Windows burn-in FAIL 3, Codex round 1: the per-event claim, the bash
resolvers and the PowerShell probe, each held to the reproduction the review
gave for it (.work/burnin-fix3-r1.txt).

* event_claim.py:137 (BLOCK) -- a claimant killed mid-takeover must not
  poison the key past the claim TTL.
* :121 -- a payload with its own unique field is never merged with another
  invocation; a byte-identical payload with none is one event inside WINDOW.
* :126 -- a winner that dies after exit 0 and before emitting must not cost
  the only emission: the twin waits out the grace, then emits.
* :129 -- an unusable claim store lets exactly ONE flavour emit.
* notify.sh:37 -- the burn-in PATH (failing WindowsApps python3 first, real
  python3 second, no python/py) sends one ping across both flavours.
* role-write-guard.ps1:58 / :66 -- the shared probe proves Python 3 and kills
  the whole process tree on its timeout; `_common.sh`'s bash resolver kills
  the tree too.
"""
import itertools
import json
import os
import pathlib
import subprocess
import sys
import threading
import time
from unittest import mock

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import crew_fixtures
import event_claim
from review_fixtures import init_repo

SCRIPTS = pathlib.Path(__file__).resolve().parent.parent / "hooks" / "scripts"
PWSH = crew_fixtures.resolve_pwsh()
BASH = crew_fixtures.resolve_bash()
REAL = os.path.realpath(sys.executable)
CLAIM = [sys.executable, str(SCRIPTS / "event_claim.py")]

needs_pwsh = pytest.mark.skipif(PWSH is None, reason="pwsh not installed - the .ps1 half was NOT run")
needs_bash = pytest.mark.skipif(BASH is None, reason="bash not installed - the bash half was NOT run")

NOTE = b'{"session_id":"s","hook_event_name":"Notification","message":"waiting"}'


def _repo(tmp_path):
    return str(init_repo(tmp_path / "r"))


def _generation_files(root):
    return sorted(pathlib.Path(event_claim.claims_dir(root)).iterdir())


def _claim_files(root):
    """`_generation_files`, minus the nonce-keyed "sent" markers `mark_sent`
    writes beside a claim (review round 3, crew-1.0-r4-scope) -- the count a
    test that cares about ORPHANED GENERATIONS, not marker bookkeeping,
    actually means."""
    return [f for f in _generation_files(root) if ".sent-" not in f.name]


# --- :137 BLOCK -- a crash mid-takeover never outlives the claim TTL -------------

_CRASH_AFTER_CREATE = """
import os, sys
sys.path.insert(0, sys.argv[1])
import event_claim
real_open = os.open
def open_then_die(path, flags, mode=0o777):
    handle = real_open(path, flags, mode)
    os._exit(9)          # killed after O_EXCL created the file, before a byte was written
event_claim.os.open = open_then_die
event_claim.claim(sys.argv[2], "notify", sys.argv[3].encode(), now=float(sys.argv[4]))
"""


def _crash_mid_claim(root, raw, now):
    done = subprocess.run([sys.executable, "-c", _CRASH_AFTER_CREATE, str(SCRIPTS), root,
                           raw.decode(), str(now)], capture_output=True, check=False, timeout=30)
    assert done.returncode == 9, done.stderr


def test_a_takeover_killed_after_its_create_does_not_suppress_the_next_event(tmp_path):
    """The review's reproduction: an expired marker, the winner of the
    takeover killed between its two steps, then the same payload again."""
    root = _repo(tmp_path)
    t0 = time.time() - 3 * event_claim.WINDOW
    event_claim.mark_sent(event_claim.decide(root, "notify", NOTE, now=t0)[1])
    _crash_mid_claim(root, NOTE, t0 + event_claim.WINDOW + 1)
    retry_at = time.time() + event_claim.WINDOW + 1

    assert event_claim.claim(root, "notify", NOTE, now=retry_at) is True


def test_an_orphaned_claim_is_taken_over_once_its_grace_is_spent(tmp_path):
    """Inside the TTL the orphan is an unsent claim, so the twin takes over
    after the grace instead of waiting out the whole window."""
    root = _repo(tmp_path)
    _crash_mid_claim(root, NOTE, time.time())

    assert event_claim.claim(root, "notify", NOTE, now=time.time() + event_claim.GRACE + 1) is True


def test_only_one_of_two_racing_takeovers_wins(tmp_path):
    root = _repo(tmp_path)
    t0 = time.time() - 3 * event_claim.WINDOW
    event_claim.mark_sent(event_claim.decide(root, "notify", NOTE, now=t0)[1])
    later = time.time()
    wins = []

    def contender():
        emit, token = event_claim.decide(root, "notify", NOTE, now=later)
        if emit:
            event_claim.mark_sent(token)
        wins.append((emit, token))

    threads = [threading.Thread(target=contender) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert [emit for emit, _ in wins].count(True) == 1


def test_a_loser_of_the_takeover_race_waits_instead_of_returning_false(tmp_path):
    """Codex r1 finding 1 (event_claim.py:230): a claimant that loses the
    O_EXCL race used to return False immediately. If the winner then
    crashes right after _create -- never marking its claim "sent" -- BOTH
    flavours emitted nothing. Reproduction: barrier two decide() calls so
    they hit _take at the same instant; the winner is never marked sent
    (standing in for a crash right after exit 0). The loser must wait out
    the grace and take over the next generation itself, not give up."""
    root = _repo(tmp_path)
    barrier = threading.Barrier(2)
    real_take = event_claim._take
    counter = itertools.count()
    lock = threading.Lock()

    def barriered_take(*args, **kwargs):
        with lock:
            idx = next(counter)
        if idx < 2:
            # Only the first call from each thread races through the
            # barrier -- a later takeover attempt (the fixed behaviour)
            # must run unimpeded, or this fixture would deadlock waiting
            # for a third party that never arrives.
            barrier.wait(timeout=10)
        return real_take(*args, **kwargs)

    results = []

    def contender():
        began = time.monotonic()
        emit, token = event_claim.decide(root, "notify", NOTE)
        results.append((emit, token, time.monotonic() - began))
        # Deliberately never mark_sent -- simulates a crash right after the
        # claim's own exit 0, before the caller reports "sent".

    with mock.patch.object(event_claim, "_take", side_effect=barriered_take):
        threads = [threading.Thread(target=contender) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=15)

    assert len(results) == 2
    emits = sorted(emit for emit, _, _ in results)
    elapsed = sorted(waited for _, _, waited in results)
    grace = event_claim._HOOK_GRACE["notify"]
    assert emits == [True, True], (
        "the loser must eventually take over and emit -- not return False "
        f"outright: {results}")
    assert elapsed[0] < 1, "the winner must not have waited: " + repr(elapsed)
    assert elapsed[1] >= grace - 0.5, (
        "the loser must WAIT for the takeover grace before winning the next "
        "generation, not return immediately: " + repr(elapsed))


# --- :121 identity -----------------------------------------------------------------

def test_two_invocations_with_different_unique_fields_are_two_events(tmp_path):
    root = _repo(tmp_path)
    one = b'{"session_id":"s","hook_event_name":"PreToolUse","tool_use_id":"toolu_1"}'
    two = b'{"session_id":"s","hook_event_name":"PreToolUse","tool_use_id":"toolu_2"}'
    event_claim.mark_sent(event_claim.decide(root, "notify", one)[1])

    assert event_claim.claim(root, "notify", two) is True


def test_a_byte_identical_payload_with_no_unique_field_is_one_event_inside_the_window(tmp_path):
    """Documented, not a defect: nothing in a Notification payload tells the
    other flavour's copy of THIS event from a second identical one."""
    root = _repo(tmp_path)
    event_claim.mark_sent(event_claim.decide(root, "notify", NOTE)[1])

    assert event_claim.claim(root, "notify", NOTE, now=time.time() + 10) is False


def test_the_key_names_the_event_and_the_unique_field(tmp_path):
    root = _repo(tmp_path)
    event_claim.claim(root, "notify", b'{"session_id":"s","hook_event_name":"Stop","prompt_id":"p"}')

    name = _generation_files(root)[0].name

    assert (name.startswith("notify-s-Stop-"), "-nouid-" in name) == (True, False)


# --- :126 intent, then sent --------------------------------------------------------

def test_a_winner_killed_after_exit_0_does_not_cost_the_only_emission(tmp_path):
    """The review's reproduction through the CLI: the winner is 'paused' --
    it got exit 0 and never reported sent -- and the twin runs."""
    root = _repo(tmp_path)
    cmd = CLAIM + ["notify", ".", "sh"]
    winner = subprocess.run(cmd, input=NOTE, cwd=root, capture_output=True, check=False, timeout=30)
    began = time.monotonic()
    twin = subprocess.run(CLAIM + ["notify", ".", "ps1"], input=NOTE, cwd=root,
                          capture_output=True, check=False, timeout=30)
    waited = time.monotonic() - began

    assert (winner.returncode, twin.returncode, 3 < waited < 10) == (0, 0, True)


def test_the_twin_stands_down_as_soon_as_the_winner_reports_sent(tmp_path):
    root = _repo(tmp_path)
    token = event_claim.decide(root, "notify", NOTE)[1]
    timer = threading.Timer(1.0, event_claim.mark_sent, args=(token,))
    timer.start()
    began = time.monotonic()

    lost = event_claim.claim(root, "notify", NOTE) is False
    timer.join()

    assert (lost, time.monotonic() - began < 3) == (True, True)


def test_sent_is_recorded_by_a_nonce_keyed_marker_not_a_mutation(tmp_path):
    """Review round 3 (crew-1.0-r4-scope): `mark_sent` no longer rewrites the
    generation file (no more temp-then-replace) -- it creates a separate
    marker keyed to (path, nonce). The generation file's own body is
    untouched forever; `_read` folds the marker's existence into the state
    it reports."""
    root = _repo(tmp_path)
    token = event_claim.decide(root, "notify", NOTE)[1]
    nonce, path = token.split(" ", 1)

    event_claim.mark_sent(token)

    files = _claim_files(root)
    assert [f.name.endswith(".g1") for f in files] == [True]
    assert json.loads(files[0].read_text())["state"] == "claimed", (
        "the generation file itself must never be mutated")
    assert os.path.exists(event_claim._sent_marker(path, nonce))
    assert event_claim._read(path)[0] == "sent"


# --- upgrade compat: a "sent" state written by the pre-marker release -------------

def test_a_legacy_sent_generation_with_no_marker_reads_as_sent(tmp_path):
    """Codex FIX (event_claim.py:215 at the previous anchor): the release
    before the nonce-keyed marker existed recorded "sent" by mutating the
    generation file's own "state" field in place, and wrote no separate
    marker at all. After upgrading to this code, `_read` used to check ONLY
    for the marker -- absent for every such file -- so a generation a prior
    release had already sent came back "claimed", `decide` waited out the
    grace against its (now long-past) "at", and then emitted a second time
    for an event the previous release had already reported. Reproduction:
    write that exact legacy shape by hand (no `mark_sent` call, since this
    process's own write path can no longer produce it), then call `decide`
    with the same payload."""
    root = _repo(tmp_path)
    directory = event_claim.claims_dir(root)
    os.makedirs(directory, exist_ok=True)
    key = event_claim.event_key("notify", event_claim.normalise(NOTE))
    path = os.path.join(directory, f"{key}.g1")
    legacy_at = time.time()
    with open(path, "wb") as handle:
        handle.write(json.dumps({"state": "sent", "nonce": "legacy", "at": legacy_at}).encode())

    assert event_claim._read(path)[0] == "sent"
    assert event_claim.claim(root, "notify", NOTE, now=legacy_at) is False


# --- mark_sent must check the NONCE, not just the generation file's name ---

def test_mark_sent_does_not_stamp_a_pruned_and_reused_generation(tmp_path):
    """g1 is created, ages past `_STALE_SECONDS` and is pruned, then g1 is
    RECREATED for an unrelated later claim -- `decide` reuses the same
    generation number once nothing about it remains on disk. A delayed
    owner of the FIRST g1 now calls mark_sent with its old token: the
    generation at that path is a DIFFERENT claim's now, with a different
    nonce, and the stale token's marker must never be read as marking IT
    sent (which would falsely suppress its twin's takeover).

    Review round 3 (crew-1.0-r4-scope): `mark_sent` no longer reads-then-
    writes `path`, so it no longer "refuses" a stale token by comparing
    nonces -- it just records its OWN (path, old-nonce) marker, which
    exists independently of whatever generation currently sits at `path`.
    `accepted` is therefore True (the marker was written); what matters,
    and is asserted here, is that the LIVE generation's own reported state
    is untouched by it."""
    root = _repo(tmp_path)
    old_now = time.time() - event_claim.WINDOW - 1
    old_token = event_claim.decide(root, "notify", NOTE, now=old_now)[1]
    _, old_path = old_token.split(" ", 1)
    old_cutoff_mtime = time.time() - event_claim._STALE_SECONDS - 1
    os.utime(old_path, (old_cutoff_mtime, old_cutoff_mtime))
    event_claim._prune(event_claim.claims_dir(root), time.time())
    assert not os.path.exists(old_path), "the aged g1 must actually be pruned"

    new_now = time.time()
    new_token = event_claim.decide(root, "notify", NOTE, now=new_now)[1]
    new_nonce, new_path = new_token.split(" ", 1)
    assert new_path == old_path, "the reused generation must share the old path"

    accepted = event_claim.mark_sent(old_token)

    on_disk = json.loads(pathlib.Path(new_path).read_text())
    assert (accepted, on_disk["state"], on_disk["nonce"]) == (True, "claimed", new_nonce)
    assert event_claim._read(new_path)[0] == "claimed", (
        "the stale token's marker must not make the LIVE, recycled "
        "generation read as sent")


def test_mark_sent_is_immune_to_a_prune_and_recreate_race_mid_call(tmp_path):
    """Codex final review, round 3 (crew-1.0-r4-scope): the OLD `mark_sent`
    read `path`, checked the nonce, and only THEN wrote "sent" back through
    a temp file and `os.replace` -- a real gap between the check and the
    write. Pausing exactly there (mocking `os.replace` to run the pause
    hook first) and, from inside the pause, pruning the aged generation and
    letting a brand-new `decide()` recreate the SAME generation number under
    a NEW nonce reproduced exactly what the review named: the resumed
    `os.replace` landed on the new file and stamped it "sent" under the OLD
    nonce, even though nobody had emitted for it. Verified against the
    pre-fix implementation in a standalone harness before this test was
    written (not committed -- the harness IS the reproduction step; this
    test is the regression it earns).

    Fixed, `mark_sent` makes exactly one filesystem call -- creating the
    nonce-keyed marker -- so this test injects the SAME pause hook at the
    one call it still makes (`os.open`, filtered to the marker path) and
    proves the live, recycled generation comes out unaffected regardless of
    how the race lands relative to it."""
    root = _repo(tmp_path)
    old_now = time.time() - event_claim.WINDOW - 1
    old_token = event_claim.decide(root, "notify", NOTE, now=old_now)[1]
    old_nonce, old_path = old_token.split(" ", 1)
    old_cutoff_mtime = time.time() - event_claim._STALE_SECONDS - 1
    os.utime(old_path, (old_cutoff_mtime, old_cutoff_mtime))

    marker = event_claim._sent_marker(old_path, old_nonce)
    real_open = event_claim.os.open
    new_token_box = []

    def racing_open(path, flags, mode=0o600):
        if path == marker:
            event_claim._prune(event_claim.claims_dir(root), time.time())
            assert not os.path.exists(old_path), "must actually be pruned mid-call"
            new_token_box.append(event_claim.decide(root, "notify", NOTE, now=time.time())[1])
        return real_open(path, flags, mode)

    with mock.patch.object(event_claim.os, "open", side_effect=racing_open):
        accepted = event_claim.mark_sent(old_token)

    assert accepted is True
    new_nonce, new_path = new_token_box[0].split(" ", 1)
    assert new_path == old_path, "the reused generation must share the old path"
    on_disk = json.loads(pathlib.Path(new_path).read_text())
    assert (on_disk["state"], on_disk["nonce"]) == ("claimed", new_nonce)
    assert event_claim._read(new_path)[0] == "claimed", (
        "the live, un-emitted claim must not read as sent no matter when "
        "the prune-and-recreate race lands relative to mark_sent's own "
        "filesystem call")


# --- handoff-write.sh:64 -- a failed write must not be marked sent ---------------

def _handoff_repo_with_broken_path(tmp_path):
    """`context.handoffPath` beneath a regular file, so the write can never
    land -- Codex r1 finding 2's own reproduction."""
    root = _repo(tmp_path)
    (pathlib.Path(root) / ".crew").mkdir()
    blocker = pathlib.Path(root) / ".work" / "blocker"
    blocker.parent.mkdir(parents=True, exist_ok=True)
    blocker.write_text("not a directory", encoding="utf-8")
    (pathlib.Path(root) / ".crew" / "config.json").write_text(
        json.dumps({"context": {"handoffPath": ".work/blocker/HANDOFF.md"}}),
        encoding="utf-8")
    return root


@needs_bash
def test_sh_does_not_mark_a_failed_handoff_write_sent(tmp_path):
    root = _handoff_repo_with_broken_path(tmp_path)
    payload = json.dumps({"hook_event_name": "PreCompact", "session_id": "s",
                          "cwd": root, "trigger": "auto"}).encode()

    done = subprocess.run([BASH, str(SCRIPTS / "handoff-write.sh")], input=payload,
                          cwd=root, env=dict(os.environ, CLAUDE_PROJECT_DIR=root),
                          capture_output=True, check=False, timeout=30)

    assert done.returncode == 0, done.stderr
    assert not (pathlib.Path(root) / ".work" / "blocker" / "HANDOFF.md").exists()
    claims = _generation_files(root)
    assert len(claims) == 1
    assert json.loads(claims[0].read_text())["state"] != "sent", (
        "a failed handoff write must not be marked sent -- a real twin "
        "would find 'sent' and stand down, losing the handoff for good")


@needs_pwsh
def test_ps1_does_not_mark_a_failed_handoff_write_sent(tmp_path):
    root = _handoff_repo_with_broken_path(tmp_path)
    payload = json.dumps({"hook_event_name": "PreCompact", "session_id": "s",
                          "cwd": root, "trigger": "auto"}).encode()
    env = dict(os.environ, CLAUDE_PROJECT_DIR=root, OS="Windows_NT")

    done = subprocess.run([PWSH, "-NoProfile", "-File", str(SCRIPTS / "handoff-write.ps1")],
                          input=payload, cwd=root, env=env, capture_output=True,
                          check=False, timeout=60)

    assert done.returncode == 0, done.stderr
    assert not (pathlib.Path(root) / ".work" / "blocker" / "HANDOFF.md").exists()
    claims = _generation_files(root)
    assert len(claims) == 1
    assert json.loads(claims[0].read_text())["state"] != "sent"


# --- :129 an unusable store --------------------------------------------------------

def _break_store(root):
    """A FILE where the claim directory's parent should be. chmod is no use
    here: the suite may run as root, which ignores it."""
    (pathlib.Path(root) / ".git" / "crew").write_text("not a directory", encoding="utf-8")


@pytest.mark.parametrize("os_env,expected", [
    ("Windows_NT", {"sh": False, "ps1": True, None: True}),
    (None, {"sh": True, "ps1": False, None: True}),
])
def test_an_unusable_store_lets_exactly_one_designated_flavour_emit(tmp_path, monkeypatch,
                                                                    os_env, expected):
    root = _repo(tmp_path)
    _break_store(root)
    if os_env:
        monkeypatch.setenv("OS", os_env)
    else:
        monkeypatch.delenv("OS", raising=False)

    got = {flavour: event_claim.claim(root, "notify", NOTE, flavour=flavour)
           for flavour in ("sh", "ps1", None)}

    assert got == expected


# --- end to end: both flavours of notify ---------------------------------------------

@pytest.fixture(name="teams")
def _teams():
    import http.server  # pylint: disable=import-outside-toplevel
    hits = []

    class Counter(http.server.BaseHTTPRequestHandler):
        def do_POST(self):  # pylint: disable=invalid-name
            length = int(self.headers.get("Content-Length") or 0)
            hits.append(self.rfile.read(length))
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"{}")

        def log_message(self, *_args):  # pylint: disable=arguments-differ
            pass

    server = http.server.HTTPServer(("127.0.0.1", 0), Counter)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}/hook", hits
    server.shutdown()


def _tools(tmp_path):
    """/usr/bin and /bin minus anything named python*/py*."""
    tools = tmp_path / "tools"
    tools.mkdir()
    for source in ("/usr/bin", "/bin"):
        if not os.path.isdir(source):
            continue
        for name in os.listdir(source):
            if name.startswith(("python", "py")) or (tools / name).exists():
                continue
            os.symlink(os.path.join(source, name), tools / name)
    return tools


def _stub(directory, name, body):
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    path.write_text("#!/bin/sh\n" + body + "\n", encoding="ascii", newline="\n")
    path.chmod(0o755)
    return path


def _notify_both(root, url, path=None):
    """sh then ps1, the same payload, OS=Windows_NT for BOTH -- on a real
    Windows host Git Bash inherits it too."""
    env = dict(os.environ, CLAUDE_PROJECT_DIR=root, OS="Windows_NT", CREW_TEST_TEAMS_URL=url)
    if path:
        env["PATH"] = path
    payload = json.dumps({"hook_event_name": "Notification", "session_id": "burn-in",
                          "cwd": root, "message": "Claude is waiting on you"}).encode()
    codes = []
    for cmd in ([BASH, str(SCRIPTS / "notify.sh")],
                [PWSH, "-NoProfile", "-File", str(SCRIPTS / "notify.ps1")]):
        done = subprocess.run(cmd + ["waiting", "Claude is waiting on you"], input=payload,
                              cwd=root, env=env, capture_output=True, check=False, timeout=120)
        codes.append(done.returncode)
    return codes


def _notify_repo(tmp_path):
    root = _repo(tmp_path)
    (pathlib.Path(root) / ".crew").mkdir()
    (pathlib.Path(root) / ".crew" / "config.json").write_text(
        json.dumps({"notify": {"provider": "teams", "urlEnv": "CREW_TEST_TEAMS_URL"}}),
        encoding="utf-8")
    return root


@needs_bash
@needs_pwsh
def test_the_burn_in_path_writes_one_transcript_copy_across_both_flavours(tmp_path):
    """notify.sh:37's reproduction, on the bash claimant that can act with
    no python at all: a failing WindowsApps python3 first, a real python3
    second, no python or py. crew_py_strict used to stop at the first match,
    so handoff-write.sh failed open and wrote; PowerShell then found the real
    one, won an empty claim store and wrote again. A second apart on purpose:
    copies are named by the second, so two in one second collapse to one
    file whether or not the claim works."""
    root = _repo(tmp_path)
    (pathlib.Path(root) / ".crew").mkdir()
    (pathlib.Path(root) / ".crew" / "config.json").write_text("{}", encoding="utf-8")
    transcript = pathlib.Path(root) / "t.jsonl"
    transcript.write_text("{}\n", encoding="utf-8")
    apps = tmp_path / "Microsoft" / "WindowsApps"
    _stub(apps, "python3", "exit 9009")
    real = tmp_path / "Python312"
    _stub(real, "python3", f'exec "{REAL}" "$@"')
    env = dict(os.environ, CLAUDE_PROJECT_DIR=root, OS="Windows_NT",
               PATH=os.pathsep.join([str(apps), str(real), str(_tools(tmp_path))]))
    payload = json.dumps({"hook_event_name": "PreCompact", "session_id": "burn-in", "cwd": root,
                          "transcript_path": str(transcript), "trigger": "auto"}).encode()

    codes = []
    for cmd in ([BASH, str(SCRIPTS / "handoff-write.sh")],
                [PWSH, "-NoProfile", "-File", str(SCRIPTS / "handoff-write.ps1")]):
        codes.append(subprocess.run(cmd, input=payload, cwd=root, env=env, capture_output=True,
                                    check=False, timeout=120).returncode)
        time.sleep(1.2)
    copies = list((pathlib.Path(root) / ".crew" / "transcripts").glob("*.jsonl"))

    assert (codes, len(copies)) == ([0, 0], 1)


def _notify_repo_bad_provider(tmp_path):
    """`notify.provider` set to a typo -- Codex r1 finding 4's own
    reproduction: neither the bash `case` nor the PowerShell `switch` had a
    default arm, so nothing ever called claim_sent/Complete-CrewEventClaim
    for it."""
    root = _repo(tmp_path)
    (pathlib.Path(root) / ".crew").mkdir()
    (pathlib.Path(root) / ".crew" / "config.json").write_text(
        json.dumps({"notify": {"provider": "tems"}}), encoding="utf-8")
    return root


@needs_bash
def test_sh_marks_an_unknown_provider_claim_sent_not_orphaned(tmp_path):
    root = _notify_repo_bad_provider(tmp_path)
    env = dict(os.environ, CLAUDE_PROJECT_DIR=root)

    done = subprocess.run([BASH, str(SCRIPTS / "notify.sh"), "waiting", "hi"], input=NOTE,
                          cwd=root, env=env, capture_output=True, check=False, timeout=30)

    assert done.returncode == 0, done.stderr
    claims = _claim_files(root)
    assert len(claims) == 1
    assert event_claim._read(str(claims[0]))[0] == "sent", (
        "an unknown provider must release the claim immediately, not leave "
        "it 'claimed' forever")


@needs_pwsh
def test_ps1_marks_an_unknown_provider_claim_sent_not_orphaned(tmp_path):
    root = _notify_repo_bad_provider(tmp_path)
    payload = json.dumps({"hook_event_name": "Notification", "session_id": "burn-in",
                          "cwd": root, "message": "hi"}).encode()
    env = dict(os.environ, CLAUDE_PROJECT_DIR=root, OS="Windows_NT")

    done = subprocess.run([PWSH, "-NoProfile", "-File", str(SCRIPTS / "notify.ps1"),
                           "waiting", "hi"], input=payload, cwd=root, env=env,
                          capture_output=True, check=False, timeout=60)

    assert done.returncode == 0, done.stderr
    claims = _claim_files(root)
    assert len(claims) == 1
    assert event_claim._read(str(claims[0]))[0] == "sent", (
        "an unknown provider must release the claim immediately, not leave "
        "it 'claimed' forever")


@needs_bash
@needs_pwsh
def test_an_unknown_provider_does_not_orphan_the_twin(tmp_path):
    """Both flavours, sequentially, the same nonempty payload: before the
    fix the second flavour waited out the whole grace (4s for notify) and
    then created a SECOND orphaned generation -- itself unsendable for the
    same reason. Fixed, the first flavour releases the claim immediately and
    the second stands down at once. PowerShell runs FIRST here -- with bash
    first the claim is already "sent" before ps1 ever reaches its own
    switch, which would prove only the bash half."""
    root = _notify_repo_bad_provider(tmp_path)
    payload = json.dumps({"hook_event_name": "Notification", "session_id": "burn-in",
                          "cwd": root, "message": "hi"}).encode()
    env = dict(os.environ, CLAUDE_PROJECT_DIR=root, OS="Windows_NT")

    began = time.monotonic()
    codes = []
    for cmd in ([PWSH, "-NoProfile", "-File", str(SCRIPTS / "notify.ps1")],
                [BASH, str(SCRIPTS / "notify.sh")]):
        done = subprocess.run(cmd + ["waiting", "hi"], input=payload, cwd=root, env=env,
                              capture_output=True, check=False, timeout=30)
        codes.append(done.returncode)
    elapsed = time.monotonic() - began

    claims = _claim_files(root)
    assert (codes, elapsed < 3) == ([0, 0], True), (
        "the twin must stand down immediately, not wait out the grace: "
        f"codes={codes} elapsed={elapsed}")
    assert len(claims) == 1, (
        "an unknown provider must not orphan a second generation: " +
        repr([c.name for c in claims]))
    assert event_claim._read(str(claims[0]))[0] == "sent"


@needs_bash
@needs_pwsh
def test_an_unusable_store_sends_one_ping_across_both_flavours(tmp_path, teams):
    url, hits = teams
    root = _notify_repo(tmp_path)
    _break_store(root)

    codes = _notify_both(root, url)

    assert (codes, len(hits)) == ([0, 0], 1)


# --- role-write-guard.ps1:58 -- the probe proves Python 3 ------------------------------

def _print_python(path_entries):
    env = dict(os.environ, OS="Windows_NT", PATH=os.pathsep.join(map(str, path_entries)))
    done = subprocess.run([PWSH, "-NoProfile", "-NonInteractive", "-File",
                           str(SCRIPTS / "completion-audit.ps1"), "-PrintPython"],
                          env=env, stdin=subprocess.DEVNULL, capture_output=True,
                          text=True, check=False, timeout=120)
    assert done.returncode == 0, done.stderr
    return done.stdout.strip()


def _answer(v, impl, exe):
    return json.dumps({"v": v, "exe": exe, "impl": impl}).replace('"', '\\"')


@needs_pwsh
@pytest.mark.parametrize("body", [
    pytest.param('echo "$0"', id="prints-its-own-path"),
    pytest.param('echo "{REAL}"', id="prints-a-real-interpreter-path"),
    pytest.param('echo "{answer_py2}"', id="python-2"),
    pytest.param('echo "{answer_py37}"', id="python-3.7"),
    pytest.param('echo "{answer_jython}"', id="unknown-implementation"),
    pytest.param('echo "{answer_missing}"', id="exe-does-not-exist"),
    pytest.param('echo "{answer_strings}"', id="version-not-numbers"),
])
def test_the_probe_rejects_anything_that_is_not_a_proven_python_3(tmp_path, body):
    """Each is the only candidate on PATH, so a rejection reads as ''."""
    body = body.format(
        REAL=REAL,
        answer_py2=_answer([2, 7], "cpython", REAL),
        answer_py37=_answer([3, 7], "cpython", REAL),
        answer_jython=_answer([3, 12], "jython", REAL),
        answer_missing=_answer([3, 12], "cpython", str(tmp_path / "missing.exe")),
        answer_strings=_answer(["3", "12"], "cpython", REAL))
    fake = tmp_path / "fake"
    _stub(fake, "python3", body)

    assert _print_python([fake, _tools(tmp_path)]) == ""


@needs_pwsh
def test_the_probe_accepts_a_real_python_3(tmp_path):
    real = tmp_path / "real"
    _stub(real, "python3", f'exec "{REAL}" "$@"')

    assert _print_python([real, _tools(tmp_path)]) == REAL


# --- role-write-guard.ps1:66 and the bash resolver -- the timeout kills the tree ----------

def _launcher(tmp_path, token):
    """A py.exe-shaped launcher: starts a child interpreter that inherits
    stdout/stderr, then waits on it. The child carries `token` in its argv so
    the test can find it afterwards."""
    launcher = tmp_path / "launcher"
    _stub(launcher, "python3",
          f'"{REAL}" -c "import time; time.sleep(120)" {token} &\nwait')
    return launcher


def _survivors(token):
    found = []
    for pid in os.listdir("/proc"):
        if not pid.isdigit():
            continue
        try:
            argv = pathlib.Path(f"/proc/{pid}/cmdline").read_bytes().split(b"\0")
        except OSError:
            continue
        if token.encode() in argv:
            found.append(int(pid))
    return found


def _reap(pids):
    for pid in pids:
        try:
            os.kill(pid, 9)
        except OSError:
            pass


@pytest.mark.skipif(not os.path.isdir("/proc"), reason="needs /proc to find the child")
@needs_pwsh
def test_the_ps1_probe_timeout_kills_the_launchers_child_too(tmp_path):
    token = f"crew-probe-child-{tmp_path.name}"
    launcher = _launcher(tmp_path, token)
    real = tmp_path / "real"
    _stub(real, "python3", f'exec "{REAL}" "$@"')

    resolved = _print_python([launcher, real, _tools(tmp_path)])
    time.sleep(0.5)
    left = _survivors(token)
    _reap(left)

    assert (resolved, left) == (REAL, [])


@pytest.mark.skipif(not os.path.isdir("/proc"), reason="needs /proc to find the child")
@needs_bash
def test_the_bash_probe_is_bounded_and_kills_the_launchers_child_too(tmp_path):
    token = f"crew-probe-child-{tmp_path.name}"
    launcher = _launcher(tmp_path, token)
    real = tmp_path / "real"
    _stub(real, "python3", f'exec "{REAL}" "$@"')
    env = dict(os.environ, PATH=os.pathsep.join([str(launcher), str(real), str(_tools(tmp_path))]))
    began = time.monotonic()

    done = subprocess.run([BASH, "-c", f'. "{SCRIPTS / "_common.sh"}"; crew_py_strict'],
                          env=env, stdin=subprocess.DEVNULL, capture_output=True, text=True,
                          check=False, timeout=60)
    elapsed = time.monotonic() - began
    left = _survivors(token)
    _reap(left)

    assert (done.stdout.strip(), elapsed < 10, left) == (REAL, True, [])


@needs_bash
def test_the_bash_probe_does_not_hang_on_a_candidate_that_never_exits(tmp_path):
    hang = tmp_path / "hang"
    _stub(hang, "python3", "exec sleep 120")
    env = dict(os.environ, PATH=os.pathsep.join([str(hang), str(_tools(tmp_path))]))
    began = time.monotonic()

    done = subprocess.run([BASH, "-c", f'. "{SCRIPTS / "_common.sh"}"; crew_py_strict'],
                          env=env, stdin=subprocess.DEVNULL, capture_output=True, text=True,
                          check=False, timeout=60)

    assert (done.returncode, done.stdout, time.monotonic() - began < 10) == (1, "", True)

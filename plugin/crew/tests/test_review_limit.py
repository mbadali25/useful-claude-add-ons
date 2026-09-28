"""A Codex usage, rate or quota limit sends the review round to Claude (T-0088).

Three layers, each against a throwaway repo under tmp_path and a fake `codex`
written by this file (not `review_fixtures.py`):

  * `review_limit.limit_line` classifies Codex's own limit messages, cited to
    `openai/codex@44fe510c` `codex-rs/protocol/src/error.rs`, and nothing else;
  * `review_run.py --probe` makes one minimal real call and reserves nothing;
  * a limit hit mid-round is recorded, and the next probe answers `limited`
    from that record without a call, for the next round only.
"""
import json
import os
import subprocess
import sys
import textwrap

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import review_ledger
import review_limit
import review_run
from review_fixtures import git, init_repo

LIMIT_MESSAGES = [
    pytest.param("You’ve hit your usage limit. Try again at 3:45 PM.", id="usage-curly"),
    pytest.param("You've hit your usage limit. Upgrade to Pro (https://chatgpt.com/explore/pro), "
                 "visit https://chatgpt.com/codex/settings/usage to purchase more credits or "
                 "try again later.", id="usage-ascii"),
    pytest.param("You’ve hit your usage limit for gpt-5.6-sol. Switch to another model now, "
                 "or try again later.", id="usage-model"),
    pytest.param("Your workspace is out of credits. Add credits to continue.",
                 id="credits-owner"),
    pytest.param("Your workspace is out of credits. Ask your workspace owner to refill in order "
                 "to continue.", id="credits-member"),
    pytest.param("You hit your spend cap set in your workspace. Increase your spend cap to "
                 "continue.", id="spend-cap"),
    pytest.param("rate limit exceeded: Rate limit reached for requests", id="rate"),
    pytest.param("Quota exceeded. Check your plan and billing details.", id="quota"),
    pytest.param("To use Codex with your ChatGPT plan, upgrade to Plus: "
                 "https://chatgpt.com/explore/plus.", id="not-included"),
    pytest.param("exceeded retry limit, last status: 429 Too Many Requests, request id: req_1",
                 id="retry-429"),
]

NOT_LIMITS = [
    pytest.param("Selected model is at capacity. Please try a different model.", id="capacity"),
    pytest.param("We’re currently experiencing high demand, which may cause temporary "
                 "errors.", id="high-demand"),
    pytest.param("Flex capacity unavailable.", id="flex"),
    pytest.param("unexpected status 401 Unauthorized", id="401"),
    pytest.param("exceeded retry limit, last status: 500 Internal Server Error", id="retry-500"),
    pytest.param("stream died", id="stream-died"),
    pytest.param("", id="empty"),
]


@pytest.mark.parametrize("message", LIMIT_MESSAGES)
def test_limit_line_matches_every_cited_codex_limit_message(message):
    text = f"codex exec started\n{message}\nexit 1"

    assert review_limit.limit_line(text) == message


@pytest.mark.parametrize("message", NOT_LIMITS)
def test_limit_line_ignores_errors_that_are_not_limits(message):
    assert review_limit.limit_line(message) is None


def test_limit_line_reads_every_text_given():
    line = review_limit.limit_line("", "boom\nQuota exceeded. Check your plan and billing details.")

    assert line == "Quota exceeded. Check your plan and billing details."


# --- review_run.py --probe: one minimal real call, before any reservation -----------------

_SCRIPTS = os.path.join(context._ROOT, "hooks", "scripts")  # pylint: disable=protected-access
_RUN = os.path.join(_SCRIPTS, "review_run.py")
_PATCH = os.path.join(_SCRIPTS, "review_patch.py")
_LIMIT_MESSAGE = "You’ve hit your usage limit. Try again at 3:45 PM."

# A fake `codex`, written here rather than in review_fixtures.py. One JSON line
# per invocation goes to $FAKE_CODEX_LOG; $FAKE_CODEX_MODE picks the behaviour.
_FAKE_CODEX = r'''
import json, os, re, sys, time
prompt = sys.argv[-1]
with open(os.environ["FAKE_CODEX_LOG"], "a", encoding="utf-8") as log:
    log.write(json.dumps({"argv": sys.argv[1:]}) + "\n")
mode = os.environ.get("FAKE_CODEX_MODE", "ok")
PROBE_PROMPT = os.environ["FAKE_CODEX_PROBE_PROMPT"]
if mode == "hang":
    time.sleep(120)
    sys.exit(0)
if mode == "quota_stderr":
    sys.stderr.write("ERROR: Quota exceeded. Check your plan and billing details.\n")
    sys.exit(1)
def emit(events):
    print("\n".join(json.dumps(e) for e in events))
if mode == "limit":
    message = os.environ["FAKE_CODEX_LIMIT"]
    emit([{"type": "thread.started"}, {"type": "error", "message": message},
          {"type": "turn.failed", "error": {"message": message}}])
    sys.exit(1)
if mode == "unauthorized":
    emit([{"type": "thread.started"},
          {"type": "turn.failed", "error": {"message": "unexpected status 401 Unauthorized"}}])
    sys.exit(1)
events = [{"type": "thread.started"}, {"type": "turn.started"}]
if mode == "retried_then_ok":
    events.append({"type": "error", "message": "rate limit exceeded: retrying in 1s"})
if prompt == PROBE_PROMPT:
    body = "OK"
else:
    parts = sorted(set(re.findall(r"part-\d{3}-of-\d{3}\.patch", prompt)))
    body = "\n".join("READ|" + p for p in parts) + "\nCLEAN"
events += [{"type": "item.completed", "item": {"type": "agent_message", "text": body}},
           {"type": "turn.completed"}]
emit(events)
'''


def _fake_codex(directory):
    directory.mkdir(parents=True, exist_ok=True)
    script = directory / "codex"
    script.write_text(f"#!{sys.executable}\n" + textwrap.dedent(_FAKE_CODEX), encoding="utf-8",
                      newline="\n")
    script.chmod(0o755)
    (directory / "codex.cmd").write_text(f'@"{sys.executable}" "%~dp0codex" %*\r\n',
                                         encoding="utf-8", newline="")
    return directory


def _env(bin_dir, mode, path=None):
    env = dict(os.environ)
    env["PATH"] = path if path is not None else str(bin_dir) + os.pathsep + env.get("PATH", "")
    env.update(FAKE_CODEX_MODE=mode, FAKE_CODEX_LOG=str(bin_dir / "calls.jsonl"),
               FAKE_CODEX_PROBE_PROMPT=review_run.PROBE_PROMPT, FAKE_CODEX_LIMIT=_LIMIT_MESSAGE)
    return env


def _calls(bin_dir):
    log = bin_dir / "calls.jsonl"
    if not log.exists():
        return []
    return [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines() if line]


def _bundle(repo, scratch):
    (repo / "change.txt").write_text("change\n", encoding="utf-8")
    base = git(repo, "rev-parse", "HEAD")
    scratch.mkdir(parents=True, exist_ok=True)
    subprocess.run([sys.executable, _PATCH, "--root", str(repo), "--base", base,
                    "--out", str(scratch / "diff.txt"),
                    "--manifest", str(scratch / "manifest.json")],
                   check=True, capture_output=True, stdin=subprocess.DEVNULL)
    (scratch / "prompt.txt").write_text(
        "Review. " + " ".join(p["name"] for p in json.loads(
            (scratch / "manifest.json").read_text(encoding="utf-8"))["parts"]),
        encoding="utf-8")


def _script(repo, scratch, env, *extra):
    return subprocess.run(
        [sys.executable, _RUN, "--root", str(repo), "--ticket", "T1",
         "--scratch", str(scratch)] + list(extra),
        capture_output=True, text=True, stdin=subprocess.DEVNULL, check=False,
        env=env, timeout=180)


def _review(repo, scratch, bin_dir, mode, *extra):
    return _script(repo, scratch, _env(bin_dir, mode), "--provider", "codex",
                   "--work-dir", str(scratch / "work"), *extra)


def _probe(repo, scratch, bin_dir, mode, *extra, path=None):
    return _script(repo, scratch, _env(bin_dir, mode, path), "--provider", "codex", "--probe",
                   *extra)


def _field(result, key):
    for line in result.stdout.splitlines():
        if line.startswith(key + "="):
            return line[len(key) + 1:]
    return None


def _rounds_used(repo):
    return review_ledger.status(str(repo), "T1")["rounds_used"]


@pytest.fixture(name="lane")
def _lane(tmp_path):
    return init_repo(tmp_path / "r"), tmp_path / "scratch", _fake_codex(tmp_path / "bin")


def test_probe_ok_exits_zero_and_reserves_nothing(lane):
    repo, scratch, bin_dir = lane

    result = _probe(repo, scratch, bin_dir, "ok")

    assert (result.returncode, _field(result, "PROBE"), _rounds_used(repo)) == (0, "ok", 0)


def test_probe_limit_error_is_limited_and_reserves_nothing(lane):
    repo, scratch, bin_dir = lane

    result = _probe(repo, scratch, bin_dir, "limit")

    assert (result.returncode, _field(result, "PROBE"), _rounds_used(repo)) == (5, "limited", 0)
    assert "hit your usage limit" in _field(result, "PROBE_DETAIL")


def test_probe_limit_on_stderr_is_limited(lane):
    repo, scratch, bin_dir = lane

    result = _probe(repo, scratch, bin_dir, "quota_stderr")

    assert result.returncode == 5


def test_probe_other_failure_is_failed_not_limited(lane):
    repo, scratch, bin_dir = lane

    result = _probe(repo, scratch, bin_dir, "unauthorized")

    assert (result.returncode, _field(result, "PROBE")) == (6, "failed")
    assert "401" in _field(result, "PROBE_DETAIL")


def test_probe_timeout_is_unknown_not_ok(lane):
    repo, scratch, bin_dir = lane

    result = _probe(repo, scratch, bin_dir, "hang", "--probe-timeout", "2")

    assert (result.returncode, _field(result, "PROBE")) == (7, "unknown")


def test_probe_retried_rate_limit_then_success_is_ok(lane):
    repo, scratch, bin_dir = lane

    result = _probe(repo, scratch, bin_dir, "retried_then_ok")

    assert result.returncode == 0


def test_probe_makes_exactly_one_minimal_call(lane):
    repo, scratch, bin_dir = lane

    _probe(repo, scratch, bin_dir, "ok", "--model", "m1", "--effort", "low")

    calls = _calls(bin_dir)
    argv = calls[0]["argv"] if calls else []
    assert len(calls) == 1 and argv[-1] == review_run.PROBE_PROMPT
    assert all(flag in " ".join(argv) for flag in (
        "--model m1", "-c model_reasoning_effort=low", "--sandbox read-only"))


def test_probe_codex_not_on_path_is_failed(lane, tmp_path):
    repo, scratch, bin_dir = lane
    empty = tmp_path / "empty"
    empty.mkdir()

    result = _probe(repo, scratch, bin_dir, "ok", path=str(empty))

    assert (result.returncode, _rounds_used(repo)) == (6, 0)


def test_probe_is_codex_only(lane):
    repo, scratch, bin_dir = lane

    result = _script(repo, scratch, _env(bin_dir, "ok"), "--provider", "claude", "--probe")

    assert result.returncode == 2 and "codex provider only" in result.stderr

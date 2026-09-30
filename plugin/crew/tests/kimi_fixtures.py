"""A fake `kimi` (the Kimi Code CLI) and a fixture KIMI_CODE_HOME for the Kimi
provider tests (T-0028). Everything is built under pytest's tmp_path: nothing
here reads the real `~/.kimi-code` or calls the real CLI.

Kept apart from review_fixtures.py on purpose: that module is part of the
review harness (scripts/check-tooling-pr.py's HARNESS), and the provider tests
are feature tests. The review launch (L-0527) imports these helpers."""
import sys
import textwrap

# The fake `kimi`: kimi_probe.py calls it now; review_run.py will (L-0527).
#
# The stream it prints follows the shape PromptJsonWriter in the Kimi Code
# 2.1.1 bundle writes -- one JSON object per line, `{"role": "assistant",
# "content": "<text>"}` for the assistant, `{"role": "meta", "type": ...}` for
# everything else. A successful call prints the three lines the owner's real
# run printed (`tests/fixtures/kimi-stream-2.1.1/ok.jsonl`): system.version,
# the assistant text, then a session.resume_hint whose `content` is a string.
# The tool-call, tool-result, retry, 401, quota and turn-failure records are
# NOT captured; that directory's README says which of its files are.
#
# Two knobs, because one review_run.py invocation calls `kimi` twice (the
# probe, then the review) with one environment:
#   FAKE_KIMI_PROBE  how the probe call (prompt == "Reply with exactly:
#                    PROBE_OK") answers: ok | 401 | nomodel | quota:<marker>
#                    | garbage | nomarker | hang
#   FAKE_KIMI_MODE   how a review call answers: clean | findings | turnfail
#                    | turnfail-secret (the failure message carries a bearer
#                    token) | write (appends to seed.txt, then answers clean)
#                    | fail
#   FAKE_KIMI_WRITES comma-separated repo-relative paths a review call appends
#                    to (parent dirs created) before it answers
#   FAKE_KIMI_PUT    a JSON object {repo-relative path: text}; a review call
#                    overwrites each path with its text, in order, before
#                    it answers (parent dirs created)
#   FAKE_KIMI_CHMOD  comma-separated repo-relative paths a review call sets
#                    executable (chmod +x) before it answers, contents untouched
#   FAKE_KIMI_PROBE_WRITE  an absolute path the PROBE call appends to
#   FAKE_KIMI_LATE / FAKE_KIMI_PROBE_LATE  an absolute path that a process the
#                    review (or probe) call leaves running in its own process
#                    group appends to LATE_WRITE_S after the call has answered
#   FAKE_KIMI_DUMP   when set, each call appends {argv, env, stdin, cwd,
#                    agent_file, skills} as one JSON line to this file --
#                    `agent_file` is the text --agent-file named AT CALL TIME,
#                    `skills` the listing of --skills-dir.
_FAKE_KIMI = r'''
import json, os, re, sys, time
argv = sys.argv[1:]
stdin_text = sys.stdin.read()
dump = os.environ.get("FAKE_KIMI_DUMP")
def flag(name):
    return argv[argv.index(name) + 1] if name in argv else None
if dump:
    agent = flag("--agent-file")
    skills = flag("--skills-dir")
    with open(dump, "a", encoding="utf-8") as fh:
        fh.write(json.dumps({"argv": argv, "stdin": stdin_text, "cwd": os.getcwd(),
                             "agent_file": open(agent, encoding="utf-8").read()
                             if agent and os.path.isfile(agent) else None,
                             "skills": sorted(os.listdir(skills))
                             if skills and os.path.isdir(skills) else None,
                             "env": {k: v for k, v in os.environ.items()
                                     if k.startswith("KIMI_")}}) + "\n")
prompt = argv[argv.index("-p") + 1] if "-p" in argv else ""
VERSION = {"role": "meta", "type": "system.version", "version": "2.1.1"}
RESUME = {"role": "meta", "type": "session.resume_hint",
          "session_id": "00000000-0000-0000-0000-fixture00001",
          "command": "kimi -r 00000000-0000-0000-0000-fixture00001",
          "content": "To resume this session: kimi -r 00000000-0000-0000-0000-fixture00001"}
def say(*events):
    print("\n".join(json.dumps(e) for e in events))
def late(path):
    if path:
        import subprocess
        subprocess.Popen(  # pylint: disable=consider-using-with
            [sys.executable, "-c", "import sys, time; time.sleep(float(sys.argv[2])); "
             "open(sys.argv[1], 'a').write('late fix')", path, "LATE_WRITE_S"],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
if prompt == "Reply with exactly: PROBE_OK":
    late(os.environ.get("FAKE_KIMI_PROBE_LATE"))
    mode = os.environ.get("FAKE_KIMI_PROBE", "ok")
    if os.environ.get("FAKE_KIMI_PROBE_WRITE"):
        with open(os.environ["FAKE_KIMI_PROBE_WRITE"], "a", encoding="utf-8") as fh:
            fh.write("the probe wrote this\n")
    if mode == "ok":
        say(VERSION, {"role": "assistant", "content": "PROBE_OK"}, RESUME)
    elif mode == "401":
        sys.stderr.write("Error: 401 invalid_authentication_error: Invalid Authentication\n")
        sys.exit(1)
    elif mode == "nomodel":
        sys.stderr.write("Error: No model configured. Run `kimi` and use /login to sign in, then retry\n")
        sys.exit(1)
    elif mode.startswith("quota:"):
        marker = mode.split(":", 1)[1]
        say({"role": "meta", "type": "turn.step.retrying", "status_code": 429,
             "error_message": marker})
        sys.stderr.write("Error: 429 " + marker + "\n")
        sys.exit(1)
    elif mode == "garbage":
        sys.stderr.write("something nobody has seen before\n")
        sys.exit(3)
    elif mode == "nomarker":
        say({"role": "assistant", "content": "Sure! Here you go."})
    elif mode == "hang":
        time.sleep(60)
    sys.exit(0)
mode = os.environ.get("FAKE_KIMI_MODE", "clean")
late(os.environ.get("FAKE_KIMI_LATE"))
if mode == "fail":
    sys.stderr.write("boom\n")
    sys.exit(1)
if mode == "write":
    with open("seed.txt", "a", encoding="utf-8") as fh:
        fh.write("fixed it instead of reporting it\n")
for rel in filter(None, os.environ.get("FAKE_KIMI_WRITES", "").split(",")):
    if os.path.dirname(rel):
        os.makedirs(os.path.dirname(rel), exist_ok=True)
    with open(rel, "a", encoding="utf-8") as fh:
        fh.write("written during the review\n")
for rel in filter(None, os.environ.get("FAKE_KIMI_CHMOD", "").split(",")):
    os.chmod(rel, os.stat(rel).st_mode | 0o111)
for rel, body in json.loads(os.environ.get("FAKE_KIMI_PUT") or "{}").items():
    if os.path.dirname(rel):
        os.makedirs(os.path.dirname(rel), exist_ok=True)
    with open(rel, "w", encoding="utf-8") as fh:
        fh.write(body)
text = prompt
if prompt.startswith("Your complete instructions are in the file "):
    path = prompt[len("Your complete instructions are in the file "):].split(". Read", 1)[0]
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
parts = sorted(set(re.findall(r"part-\d{3}-of-\d{3}\.patch", text)))
body = "\n".join("READ|" + p for p in parts)
body += "\nFIX|seed.txt:1|breaks|repro" if mode == "findings" else "\nCLEAN"
if mode == "turnfail":
    say({"role": "assistant", "content": body},
        {"role": "meta", "type": "turn.failed",
         "error": {"code": "provider.error", "message": "stream died"}})
    sys.exit(0)
if mode == "turnfail-secret":
    say({"role": "assistant", "content": body},
        {"role": "meta", "type": "turn.failed",
         "message": "Bearer eyJhbGciOi.eyJzdWIiOi.c2lnbmF0dXJl rejected"})
    sys.exit(0)
say(VERSION,
    {"role": "assistant", "content": None,
     "tool_calls": [{"type": "function", "id": "t1",
                     "function": {"name": "Read", "arguments": "{}"}}]},
    {"role": "tool", "tool_call_id": "t1", "content": "..."},
    {"role": "assistant", "content": body},
    RESUME)
'''


# How long a FAKE_KIMI_LATE process waits before it writes: long enough that
# the call has answered and review_run.py has moved on, short enough to wait for.
LATE_WRITE_S = 1.5


def fake_kimi_bin(directory):
    """Write an executable fake `kimi` into `directory` (plus a .cmd shim for
    Windows) and return the directory, for PATH."""
    directory.mkdir(parents=True, exist_ok=True)
    script = directory / "kimi"
    body = textwrap.dedent(_FAKE_KIMI).replace('"LATE_WRITE_S"', repr(str(LATE_WRITE_S)))
    script.write_text(f"#!{sys.executable}\n" + body, encoding="utf-8", newline="\n")
    script.chmod(0o755)
    (directory / "kimi.cmd").write_text(
        f'@"{sys.executable}" "%~dp0kimi" %*\r\n', encoding="utf-8", newline="")
    return directory


# The owner's three ids and the alias each is served under in a real
# `~/.kimi-code/config.toml` (Kimi Code 2.1.1, structure read 2026-09-25).
KIMI_ALIASES = {"kimi-code/k3": "k3",
                "kimi-code/kimi-for-coding": "kimi-for-coding",
                "kimi-code/kimi-for-coding-highspeed": "kimi-for-coding-highspeed"}


def kimi_home(directory, provider_type="kimi", credential=True, api_key="",
              default_model="kimi-code/kimi-for-coding", config=True,
              extra_models=None):
    """A fixture KIMI_CODE_HOME: `config.toml` with one provider and the three
    aliases, and (when `credential`) one file under `credentials/`. No value
    in it is a real secret."""
    directory.mkdir(parents=True, exist_ok=True)
    if config:
        lines = []
        if default_model:
            lines.append(f'default_model = "{default_model}"')
        lines += ['', '[providers."managed:kimi-code"]', f'type = "{provider_type}"',
                  f'api_key = "{api_key}"', 'base_url = "https://example.invalid/v1"',
                  '', '[providers."managed:kimi-code".oauth]', 'storage = "file"',
                  'key = "oauth/kimi-code"']
        models = dict(KIMI_ALIASES, **(extra_models or {}))
        for alias, model in models.items():
            lines += ['', f'[models."{alias}"]', 'provider = "managed:kimi-code"',
                      f'model = "{model}"']
        (directory / "config.toml").write_text("\n".join(lines) + "\n", encoding="utf-8",
                                               newline="\n")
    if credential:
        (directory / "credentials").mkdir(exist_ok=True)
        (directory / "credentials" / "kimi-code.json").write_text(
            '{"placeholder": true}\n', encoding="utf-8", newline="\n")
    return directory

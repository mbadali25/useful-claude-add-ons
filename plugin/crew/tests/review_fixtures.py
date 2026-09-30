"""Throwaway git repositories and a fake reviewer CLI for the review-adapter
tests. Everything is built under pytest's tmp_path: no test here touches the
real repository, its ledger directory, or ~/.claude."""
import json
import os
import subprocess
import sys
import textwrap

# conftest.py imports `context` (which puts hooks/scripts on sys.path) before
# any test module in this directory is collected, so this resolves whether or
# not the caller of THIS module happened to import `context` itself first.
import review_run

# FIX (Codex): the escaped grandchild used to sleep a bare 4s, one second
# under review_run.POST_KILL_TIMEOUT (5s) -- so the pipe it held open always
# closed before the bounded follow-up `communicate()` in review_run.launch
# could time out a second time, and
# test_run_timeout_survives_an_escaped_descendant_holding_the_pipe never
# exercised that second-TimeoutExpired path at all.
#
# FIX (Codex): +3 was enough to REACH the second-TimeoutExpired path but not
# enough to PROVE it is actually bounded -- a test ceiling loose enough to
# tolerate normal process overhead (20s) could not tell a 5s-bounded
# `communicate()` from an 8s-unbounded one that just waits out this same
# lifetime; both finish comfortably inside 20s. Widened so the two are
# clearly different durations: long enough that an unbounded second
# `communicate()` (the regression) takes many seconds longer than the bounded
# one, so a tight elapsed-time assertion can actually distinguish them,
# not just long enough to still be running when the bound is checked.
ESCAPE_CHILD_LIFETIME_S = review_run.POST_KILL_TIMEOUT + 15


def git(root, *args, check=True):
    return subprocess.run(
        ("git",) + args, cwd=root, check=check, capture_output=True,
        text=True, stdin=subprocess.DEVNULL,
    ).stdout.strip()


def init_repo(root):
    root.mkdir(parents=True, exist_ok=True)
    git(root, "init", "-q", "-b", "main")
    git(root, "config", "user.email", "t@example.com")
    git(root, "config", "user.name", "t")
    git(root, "config", "core.autocrlf", "false")
    (root / "seed.txt").write_text("seed line one\nseed line two\nseed line three\n",
                                   encoding="utf-8")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "seed")
    return root


# A fake `codex` for review_run.py. Behaviour is chosen by FAKE_REVIEWER_MODE:
#   clean     acknowledge every part named in the prompt, answer CLEAN
#   findings  acknowledge every part, report one FIX
#   fail      print nothing useful and exit 1
#   hang      sleep far past any test timeout
#   crash     kill the parent (review_run.py) -- an orchestrator crash
#   turnfail  a JSON stream whose turn failed, exit 0
#   prose     a completed turn whose only agent message is prose: no READ
#             lines, no verdict -- a reviewer that broke the contract (T-0087)
#   golden    replay a REAL `codex exec --json` stream from the golden corpus
#             (FAKE_REVIEWER_GOLDEN_STREAM) byte for byte, except its last
#             agent message, which becomes READ lines for the parts this
#             prompt lists -- full paths, or bare names with
#             FAKE_REVIEWER_READ_FORM=bare -- followed by the non-READ lines of
#             FAKE_REVIEWER_GOLDEN_OUT. The canary's mode (T-0087): it answers
#             the way reviewers do, not the way the parser wants.
#
# Whatever the mode, a prompt that says its instructions are in a file (the
# form review_run.prompt_argument passes when the prompt is over
# INLINE_PROMPT_LIMIT) is read from that file, as a real reviewer does.
#   escape    fork a detached `setsid` grandchild that inherits this
#             process's stdout/stderr and outlives it, then exit immediately
#             -- the leader-already-gone shape review_run.py's `launch` BLOCK
#             fix guards against: the grandchild keeps the pipe open long
#             after the leader (this process) has exited and been reaped, so
#             a bare `os.killpg(proc.pid, ...)` at that point would target a
#             pid the OS is free to have handed to something else, and an
#             unbounded follow-up `communicate()` would block on the pipe
#             for as long as the grandchild keeps running. Sleeps a bounded
#             few seconds, not the 60s an earlier version of this fixture
#             used -- that version left the grandchild running, detached
#             from the whole test's process tree, for up to a minute past
#             every test that exercised this mode, with nothing in the test
#             file reaping or even naming its pid. Bounded here -- sized
#             against review_run.POST_KILL_TIMEOUT (ESCAPE_CHILD_LIFETIME_S,
#             above) rather than a bare guess, so it actually outlives the
#             bounded follow-up `communicate()` it exists to hold open --
#             so a test that forgets to clean up still only leaks a handful
#             of seconds, and the pid is written to
#             FAKE_REVIEWER_ESCAPE_PIDFILE (when a caller sets it) so a test
#             that wants to confirm cleanup can watch it by identity.
_FAKE = r'''
import json, os, re, signal, subprocess, sys, time
prompt = sys.argv[-1]
sys.stdin.read()
m = re.search(r"instructions are in the file (.+?)\. Read that file", prompt)
if m:
    with open(m.group(1), encoding="utf-8") as fh:
        prompt = fh.read()
mode = os.environ.get("FAKE_REVIEWER_MODE", "clean")
if mode == "golden":
    listed = re.findall(r"^  (\S.*part-\d{3}-of-\d{3}\.patch)$", prompt, re.M)
    if os.environ.get("FAKE_REVIEWER_READ_FORM", "full") == "bare":
        listed = [p.replace("\\", "/").rsplit("/", 1)[-1] for p in listed]
    with open(os.environ["FAKE_REVIEWER_GOLDEN_OUT"], encoding="utf-8", newline="") as fh:
        body = [l for l in fh.read().split("\n") if l.strip() and not l.startswith("READ|")]
    with open(os.environ["FAKE_REVIEWER_GOLDEN_STREAM"], encoding="utf-8", newline="") as fh:
        lines = fh.read().split("\n")
    last = None
    for i, line in enumerate(lines):
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if not isinstance(event, dict):
            continue
        item = event.get("item")
        if event.get("type") == "item.completed" and isinstance(item, dict) \
                and item.get("type") == "agent_message":
            last = i
    lines[last] = json.dumps({"type": "item.completed", "item": {
        "id": "item_canary", "type": "agent_message",
        "text": "\n".join(["READ|" + p for p in listed] + body)}}, ensure_ascii=False)
    sys.stdout.buffer.write("\n".join(lines).encode("utf-8"))
    sys.exit(0)
if mode == "hang":
    time.sleep(120)
def _parent_of(pid):
    # Windows only: the .cmd shim's cmd.exe sits between this script and
    # review_run.py, so the parent to kill is the shim's own parent (T-0076).
    import ctypes
    from ctypes import wintypes
    class Entry(ctypes.Structure):
        _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD),
                    ("th32ProcessID", wintypes.DWORD), ("th32DefaultHeapID", ctypes.c_void_p),
                    ("th32ModuleID", wintypes.DWORD), ("cntThreads", wintypes.DWORD),
                    ("th32ParentProcessID", wintypes.DWORD), ("pcPriClassBase", ctypes.c_long),
                    ("dwFlags", wintypes.DWORD), ("szExeFile", ctypes.c_char * 260)]
    kernel = ctypes.windll.kernel32
    kernel.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    snap = kernel.CreateToolhelp32Snapshot(2, 0)
    entry = Entry()
    entry.dwSize = ctypes.sizeof(Entry)
    found = None
    more = kernel.Process32First(snap, ctypes.byref(entry))
    while more and found is None:
        if entry.th32ProcessID == pid:
            found = entry.th32ParentProcessID
        more = kernel.Process32Next(snap, ctypes.byref(entry))
    kernel.CloseHandle(snap)
    return found
if mode == "crash":
    target = os.getppid()
    if os.name == "nt":
        target = _parent_of(target) or target
    os.kill(target, getattr(signal, "SIGKILL", signal.SIGTERM))
    time.sleep(5)
    sys.exit(0)
if mode == "fail":
    sys.stderr.write("boom\n")
    sys.exit(1)
if mode == "escape":
    lifetime = os.environ["FAKE_REVIEWER_ESCAPE_LIFETIME"]
    grandchild = subprocess.Popen(["setsid", "sh", "-c", "sleep " + lifetime])
    pidfile = os.environ.get("FAKE_REVIEWER_ESCAPE_PIDFILE")
    if pidfile:
        with open(pidfile, "w", encoding="utf-8") as fh:
            fh.write(str(grandchild.pid))
    sys.exit(0)
parts = sorted(set(re.findall(r"part-\d{3}-of-\d{3}\.patch", prompt)))
body = "\n".join("READ|" + p for p in parts)
body += "\nFIX|seed.txt:1|breaks|repro" if mode == "findings" else "\nCLEAN"
if mode == "prose":
    body = "I reviewed the change and it looks fine."
events = [{"type": "thread.started"}, {"type": "turn.started"},
          {"type": "item.completed", "item": {"type": "agent_message", "text": body}}]
events.append({"type": "turn.failed", "error": {"message": "stream died"}}
              if mode == "turnfail" else {"type": "turn.completed"})
print("\n".join(json.dumps(e) for e in events))
'''


def fake_reviewer_bin(directory, name="codex"):
    """Write an executable fake reviewer called `name` into `directory` (plus
    a .cmd shim for Windows) and return the directory, for PATH."""
    directory.mkdir(parents=True, exist_ok=True)
    script = directory / name
    script.write_text(f"#!{sys.executable}\n" + textwrap.dedent(_FAKE), encoding="utf-8",
                      newline="\n")
    script.chmod(0o755)
    (directory / f"{name}.cmd").write_text(
        f'@"{sys.executable}" "%~dp0{name}" %*\r\n', encoding="utf-8", newline="")
    return directory


def env_with_path(directory, **extra):
    env = dict(os.environ)
    env["PATH"] = str(directory) + os.pathsep + env.get("PATH", "")
    # Only read by the fake reviewer's `escape` mode; harmless for every
    # other mode. Forced from the derived value, not `setdefault` -- `env`
    # already carries a copy of THIS process's environment, so `setdefault`
    # would leave an ambient `FAKE_REVIEWER_ESCAPE_LIFETIME` (set outside
    # this test run, e.g. by a CI job or a previous manual run) in place
    # instead of the value sized against `review_run.POST_KILL_TIMEOUT`
    # above -- defeating the coverage that constant exists for, and
    # potentially leaving a grandchild sleeping far longer than intended. A
    # caller that deliberately wants a different lifetime can still get it,
    # by passing it via `extra` below, which is applied after and so still
    # wins.
    env["FAKE_REVIEWER_ESCAPE_LIFETIME"] = str(ESCAPE_CHILD_LIFETIME_S)
    env.update(extra)
    return env


# A fake `kimi` (the Kimi Code CLI) for kimi_probe.py and review_run.py.
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


_SCRIPTS = os.path.dirname(os.path.abspath(review_run.__file__))


def bundle(repo, scratch):
    """Cut the review bundle for `repo`'s working tree against HEAD into
    `scratch` (diff, manifest, a prompt naming every part)."""
    base = git(repo, "rev-parse", "HEAD")
    scratch.mkdir(parents=True, exist_ok=True)
    subprocess.run([sys.executable, os.path.join(_SCRIPTS, "review_patch.py"),
                    "--root", str(repo), "--base", base,
                    "--out", str(scratch / "diff.txt"),
                    "--manifest", str(scratch / "manifest.json")],
                   check=True, capture_output=True, stdin=subprocess.DEVNULL)
    (scratch / "prompt.txt").write_text(
        "Review. " + " ".join(p["name"] for p in json.loads(
            (scratch / "manifest.json").read_text(encoding="utf-8"))["parts"]),
        encoding="utf-8")


def run_review(repo, scratch, fakes, mode, *extra, **env_extra):
    """Run review_run.py for ticket T1 with the fake codex in `mode`."""
    return subprocess.run(
        [sys.executable, os.path.join(_SCRIPTS, "review_run.py"), "--root", str(repo),
         "--ticket", "T1", "--scratch", str(scratch), "--provider", "codex"] + list(extra),
        capture_output=True, text=True, stdin=subprocess.DEVNULL, check=False,
        env=env_with_path(fakes, FAKE_REVIEWER_MODE=mode, **env_extra), timeout=120)

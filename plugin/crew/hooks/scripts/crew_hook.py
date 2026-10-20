#!/usr/bin/env python3
"""crew_hook.py <Event> [--harness codex]: the one dispatcher behind crew's hooks (L-0727).

hooks.json registers one launcher per event per shell (crew-hook.sh,
crew-hook.ps1). Each runs this file, which picks the event's hook scripts
from `TABLE`, runs them concurrently with the payload it read from stdin, and
merges their results into the single result Claude Code sees. It ports no hook
logic: every script is still the program that decides.

`TABLE` is the one contract for hooks.json, crew_instructions.py (which renders
both registrations from it), crew-hook.sh's no-python list and the tests.

Result merge (`merge`, pure, spec U2):
  * exit 2 from any child -> exit 2, stderr of each blocking child in order;
  * PreToolUse permissionDecision: deny > ask > allow > absent, winners' reasons joined;
  * `decision: "block"` and `continue: false` from any child win, reasons kept;
  * additionalContext and systemMessage are concatenated in registration order;
  * a child's plain stdout is folded into additionalContext when another child
    emitted JSON, and passed through as plain text otherwise;
  * suppressOutput only when every child set it;
  * stdout that starts with `{` and does not parse is plain text, never dropped.

Fail closed (B8): in an ARMED repo (`armed`), a guard row that times out, a
missing script, or an exception here is exit 2 with a named reason, on the
events where a child may block (PreToolUse, UserPromptSubmit, Stop). An
unarmed repo gets exit 0 for every such fault, as the scripts do today.
"""
import json
import os
import re
import signal
import subprocess
import sys
import threading
import time
from collections import namedtuple

SCRIPTS = os.path.dirname(os.path.abspath(__file__))
if SCRIPTS not in sys.path:
    sys.path.insert(0, SCRIPTS)

MAX_STDIN = 8 * 1024 * 1024
DEADLINE_MARGIN = 5       # seconds the launcher keeps back from the registration timeout
EVENT_SLACK = 10          # registration timeout = the largest row's timeout + this
DRAIN = 2.0               # seconds to wait for pipes after a child's own exit
POST_KILL = 3.0
BLOCKING_EVENTS = ("PreToolUse", "UserPromptSubmit", "Stop")
VAULT_MATCHER = "mcp__.*(obsidian|vault|basic[-_]memory).*"
RESTRICTED_ROLES = ("explorer", "researcher", "reviewer", "security", "pm")
WRITE_TOOLS = ("Write", "Edit", "MultiEdit", "NotebookEdit")
GLOBAL_CONFIG = os.path.join(".claude", "crew", "config.json")


# One logical hook. `codex` is None when the row is not registered for Codex, else
# the Codex matcher ("" = every payload). `twin` is the PowerShell-native script that
# judges a `PowerShell` tool call on Windows.
Row = namedtuple("Row", "event matcher script extra timeout guard twin codex")


def _row(event, matcher, script, timeout, guard=False, extra=(), twin="", codex=None):
    return Row(event, matcher, script, tuple(extra), timeout, guard, twin, codex)


# One row per logical hook, in hooks.json's registration order at the base SHA.
TABLE = (
    _row("SessionStart", "", "handoff-read.sh", 15),
    _row("SessionStart", "", "platform-sync.sh", 20),
    _row("SessionStart", "", "crew-context.sh", 20, codex=""),
    _row("UserPromptSubmit", "", "crew-context.sh", 15, codex=""),
    _row("UserPromptSubmit", "", "approval-hook.sh", 20, guard=True),
    _row("PreToolUse", "Bash", "promote-gate.sh", 20, guard=True, twin="promote-gate.ps1"),
    _row("PreToolUse", "Write|Edit", "role-write-guard.sh", 10, guard=True),
    _row("PreToolUse", "Bash|PowerShell", "cloud-guard.sh", 15, guard=True, twin="cloud-guard.ps1"),
    _row("PreToolUse", "Bash|PowerShell", "env-guard.sh", 15, guard=True, twin="env-guard.ps1"),
    _row("PreToolUse", "Write|Edit|MultiEdit|NotebookEdit|Bash|PowerShell", "scope-guard.sh", 15, guard=True),
    _row("PostToolUse", "Read|Edit|Write|MultiEdit", "crew-context.sh", 10, codex="apply_patch|Edit|Write"),
    _row("PostToolUse", VAULT_MATCHER, "crew-context.sh", 10, codex=VAULT_MATCHER),
    _row("SubagentStart", "", "crew-context.sh", 15, codex=""),
    _row("PreCompact", "", "handoff-write.sh", 30),
    _row("Notification", "", "notify.sh", 15, extra=("hook",)),
    _row("Stop", "", "verify-gate.sh", 600, guard=True),
    _row("Stop", "", "context-watch.sh", 20),
    _row("Stop", "", "completion-audit.sh", 60, guard=True),
)

# The registered matcher per event: the union of its rows' tool names. A
# test asserts it is exactly that union, so a row cannot be added without it.
REGISTERED_MATCHER = {
    "SessionStart": "",
    "UserPromptSubmit": "",
    "PreToolUse": "Bash|PowerShell|Write|Edit|MultiEdit|NotebookEdit",
    "PostToolUse": "Read|Edit|Write|MultiEdit|" + VAULT_MATCHER,
    "SubagentStart": "",
    "PreCompact": "",
    "Notification": "",
    "Stop": "",
}
EVENTS = tuple(REGISTERED_MATCHER)

_PLAIN = re.compile(r"[A-Za-z0-9_|]+\Z")


def event_timeout(event):
    """The registration timeout (seconds): the event's largest row plus slack."""
    return max(row.timeout for row in TABLE if row.event == event) + EVENT_SLACK


def matches(matcher, tool):
    """Claude Code's matcher rule: empty matches all; letters/digits/_/| is an
    exact list; anything else is a regex that must match the whole name. An
    unreadable tool name matches every matcher (cannot tell: run the row)."""
    if not matcher or tool is None:
        return True
    if _PLAIN.match(matcher):
        return tool in matcher.split("|")
    return re.fullmatch(matcher, tool) is not None


def tool_name(payload):
    name = payload.get("tool_name") if isinstance(payload, dict) else None
    return name if isinstance(name, str) else None


def select(event, harness, payload, windows=False, exists=os.path.isfile, scripts=SCRIPTS):
    """[(row, argv)] for one payload, pure. `payload` is the parsed JSON, or
    None when it did not parse (every row of the event then runs). argv is
    `[script, *extra]`, relative to the scripts directory; the interpreter and
    path are added by the runner. Identical (script, argv) pairs run once."""
    tool = tool_name(payload)
    chosen, seen = [], set()
    for row in TABLE:
        if row.event != event:
            continue
        if harness == "codex":
            if row.codex is None or not matches(row.codex, tool):
                continue
            argv = [row.script, "--harness", "codex"]
        else:
            argv = [row.script, *row.extra]
            twin_ok = bool(row.twin) and windows and tool == "PowerShell" and exists(os.path.join(scripts, row.twin))
            if twin_ok:
                argv = [row.twin]
            elif not matches(row.matcher, tool):
                continue
        key = tuple(argv)
        if key in seen:
            continue
        seen.add(key)
        chosen.append((row, argv))
    return chosen


# --------------------------------------------------------------------------
# merge

_RANK = {"deny": 3, "ask": 2, "allow": 1}


def _json_object(text):
    stripped = (text or "").strip()
    if not stripped.startswith("{"):
        return None
    try:
        obj = json.loads(stripped)
    except ValueError:
        return None
    return obj if isinstance(obj, dict) else None


def _join(values):
    seen = []
    for value in values:
        if isinstance(value, str) and value and value not in seen:
            seen.append(value)
    return "\n".join(seen)


def merge(event, results):
    """One result from several children's. `results` are dicts with `exit`,
    `stdout`, `stderr` (text) in registration order; returns the same keys.
    `exit` None means the child produced no exit code and counts as a failure
    the caller already turned into a decision; it is treated as exit 0 here."""
    blockers = [r for r in results if r.get("exit") == 2]
    if blockers:
        return {"exit": 2, "stdout": "",
                "stderr": "".join(_ensure_newline(r.get("stderr", "")) for r in blockers)}
    stderr = "".join(_ensure_newline(r.get("stderr", "")) for r in results if r.get("stderr"))
    live = [r for r in results if r.get("stdout", "").strip()]
    failed = [r for r in results if r.get("exit") not in (0, 2, None)]
    code = 1 if failed and not live else 0
    parsed = [(r, _json_object(r["stdout"])) for r in live]
    if len(live) == 1:
        return {"exit": code, "stdout": live[0]["stdout"], "stderr": stderr}
    if not any(obj is not None for _, obj in parsed):
        return {"exit": code, "stderr": stderr,
                "stdout": "\n".join(r["stdout"].rstrip("\n") for r in live) + ("\n" if live else "")}
    return {"exit": code, "stderr": stderr, "stdout": _merge_json(event, parsed)}


def _ensure_newline(text):
    return text if not text or text.endswith("\n") else text + "\n"


def _merge_json(event, parsed):
    top, hso = {}, {}
    decisions, reasons, contexts, messages = [], [], [], []
    block_reasons, stop_reasons, plain = [], [], []
    blocked = stopped = False
    suppress = []
    for result, obj in parsed:
        if obj is None:
            plain.append(result["stdout"].strip())
            continue
        suppress.append(obj.get("suppressOutput") is True)
        for key, value in obj.items():
            if key == "hookSpecificOutput" and isinstance(value, dict):
                _merge_hso(value, hso, decisions, reasons, contexts)
            elif key == "systemMessage":
                messages.append(value)
            elif key == "decision" and value == "block":
                blocked = True
                block_reasons.append(obj.get("reason"))
            elif key == "continue" and value is False:
                stopped = True
                stop_reasons.append(obj.get("stopReason"))
            elif key in ("reason", "stopReason", "suppressOutput"):
                continue
            else:
                top.setdefault(key, value)
    for key in ("decision", "reason", "continue", "stopReason"):
        top.pop(key, None)
    if blocked:
        top["decision"] = "block"
        if _join(block_reasons):
            top["reason"] = _join(block_reasons)
    if stopped:
        top["continue"] = False
        if _join(stop_reasons):
            top["stopReason"] = _join(stop_reasons)
    if plain:
        contexts.extend(plain)
    if decisions:
        best = max(_RANK.get(d, 0) for d in decisions)
        winners = [i for i, d in enumerate(decisions) if _RANK.get(d, 0) == best]
        hso["permissionDecision"] = decisions[winners[0]]
        joined = _join(reasons[i] for i in winners)
        if joined:
            hso["permissionDecisionReason"] = joined
    if _join(contexts):
        hso["additionalContext"] = _join(contexts)
    if hso:
        hso = {"hookEventName": hso.pop("hookEventName", event), **hso}
        top["hookSpecificOutput"] = hso
    if _join(messages):
        top["systemMessage"] = _join(messages)
    if suppress and all(suppress) and len(suppress) == len(parsed):
        top["suppressOutput"] = True
    return json.dumps(top, ensure_ascii=False) + "\n"


def _merge_hso(value, hso, decisions, reasons, contexts):
    for key, item in value.items():
        if key == "permissionDecision" and isinstance(item, str):
            decisions.append(item)
            reasons.append(value.get("permissionDecisionReason"))
        elif key == "permissionDecisionReason":
            continue
        elif key == "additionalContext":
            contexts.append(item)
        else:
            hso.setdefault(key, item)


# --------------------------------------------------------------------------
# armed (spec U8)

def armed(root, home=None):
    """True when crew governs this repo, or when that cannot be told. False only
    when both the repo config (own or the main checkout's) and the machine-global
    config are positively absent. Any error is armed."""
    try:
        import crew_common  # pylint: disable=import-outside-toplevel
        crew_dir, source, _ = crew_common.repo_config_dir(root)
        if source == crew_common.SOURCE_UNKNOWN:
            return True
        if any(os.path.lexists(os.path.join(crew_dir, name)) for name in crew_common.CONFIG_NAMES):
            return True
        home = home if home is not None else os.path.expanduser("~")
        return os.path.lexists(os.path.join(home, GLOBAL_CONFIG))
    except Exception:  # noqa: BLE001  pylint: disable=broad-exception-caught
        return True


# --------------------------------------------------------------------------
# running children

def now_ms():
    return int(time.time() * 1000)


def _windows():
    return os.name == "nt"


def _kill_tree(proc):
    if proc.poll() is not None:
        return
    if _windows():
        try:
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)], capture_output=True,
                           timeout=10, check=False)
        except (OSError, subprocess.SubprocessError):
            pass
        try:
            proc.kill()
        except OSError:
            pass
        return
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError, OSError):
        try:
            proc.kill()
        except OSError:
            pass


def _pump(stream, sink):
    """Collect `stream` chunk by chunk, so what arrived before a held-open pipe
    stopped the read is still there when the drain bound ends."""
    try:
        while True:
            block = stream.read1(65536)
            if not block:
                return
            sink.append(block)
    except (OSError, ValueError):
        pass


def run_child(argv, raw, timeout, env, cwd=None):
    """Run one child with `raw` on stdin, killed with its tree at `timeout`
    seconds. Returns {exit, stdout, stderr, timed_out, error, pid}; stdout and
    stderr are bytes. Pipes are drained for DRAIN seconds after the child
    exits, so a background grandchild holding one cannot hold this up."""
    flags = {"creationflags": getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)} if _windows() \
        else {"start_new_session": True}
    try:
        proc = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE,  # pylint: disable=consider-using-with
                                stderr=subprocess.PIPE, env=env, cwd=cwd, **flags)
    except OSError as exc:
        return {"exit": None, "stdout": b"", "stderr": b"", "timed_out": False, "pid": 0,
                "error": f"could not start {argv[0]}: {exc}"}
    out, err = [], []
    readers = [threading.Thread(target=_pump, args=(proc.stdout, out), daemon=True),
               threading.Thread(target=_pump, args=(proc.stderr, err), daemon=True)]

    def feed():
        try:
            proc.stdin.write(raw)
        except (OSError, ValueError):
            pass
        finally:
            try:
                proc.stdin.close()
            except (OSError, ValueError):
                pass

    writer = threading.Thread(target=feed, daemon=True)
    for thread in readers + [writer]:
        thread.start()
    # Popen.wait(timeout) polls with sleeps that grow to 50 ms, which would add up to that
    # much to every hook; a blocking wait in a thread, joined with the timeout, does not.
    waiter = threading.Thread(target=proc.wait, daemon=True)
    waiter.start()
    waiter.join(max(timeout, 0.001))
    timed_out = waiter.is_alive()
    if timed_out:
        _kill_tree(proc)
        waiter.join(POST_KILL)
    bound = time.monotonic() + (POST_KILL if timed_out else DRAIN)
    for thread in readers:
        thread.join(max(bound - time.monotonic(), 0.01))
    return {"exit": None if timed_out else proc.returncode,
            "stdout": b"".join(out), "stderr": b"".join(err),
            "timed_out": timed_out, "error": "", "pid": proc.pid}


def read_stdin(stream, deadline_ms):
    """All of stdin as bytes, at most MAX_STDIN, within the deadline. Returns
    (bytes, problem); a stdin that never closes is a problem, not a hang."""
    chunks, state = [], {"over": False}

    def pump():
        total = 0
        try:
            while True:
                block = stream.read(65536)
                if not block:
                    return
                total += len(block)
                if total > MAX_STDIN:
                    state["over"] = True
                    return
                chunks.append(block)
        except (OSError, ValueError):
            return

    thread = threading.Thread(target=pump, daemon=True)
    thread.start()
    thread.join(max((deadline_ms - now_ms()) / 1000.0, 0.001))
    if thread.is_alive():
        return b"".join(chunks), "stdin did not close before the deadline"
    if state["over"]:
        return b"".join(chunks), f"stdin is larger than {MAX_STDIN} bytes"
    return b"".join(chunks), ""


def parse_payload(raw):
    try:
        value = json.loads(raw.decode("utf-8-sig"))
    except (ValueError, UnicodeDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _text(data):
    return data.decode("utf-8", errors="replace") if isinstance(data, bytes) else (data or "")


def _argv_for(argv, scripts, bash, pwsh):
    """(command, flavour) for a selected argv: the twin through PowerShell, a
    `.sh` through bash (or the caller's resolved Git Bash)."""
    path = os.path.join(scripts, argv[0])
    if argv[0].endswith(".ps1"):
        shell = [pwsh or "powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File"]
        return [*shell, path, *argv[1:]], "powershell"
    if bash and bash != "bash":
        return [bash, path.replace("\\", "/"), *argv[1:]], "bash"
    return ["bash", path, *argv[1:]], "bash"


def _trace(path, event, argv, pid):
    if not path:
        return
    try:
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(f"{event} {' '.join(argv)} {pid}\n")
    except OSError:
        pass


def dispatch(event, harness, raw, deadline_ms, env, root, windows=None, resolve_bash=None,
             resolve_pwsh=None, scripts=SCRIPTS, armed_fn=None):
    """Run the event's rows; returns (exit, stdout bytes, stderr bytes). `deadline_ms` is
    the epoch deadline the launcher handed over; it is turned into a monotonic one here, so
    a clock that steps cannot stretch or shrink any bound after this point."""
    mono_end = time.monotonic() + (deadline_ms - now_ms()) / 1000.0
    windows = _windows() if windows is None else windows
    payload = parse_payload(raw)
    chosen = select(event, harness, payload, windows=windows, scripts=scripts)
    if not chosen:
        return 0, b"", b""
    armed_fn = armed_fn or armed
    bash, pwsh, bash_problem = "bash", None, ""
    if windows:
        needs_bash = any(argv[0].endswith(".sh") for _, argv in chosen)
        if needs_bash:
            if resolve_bash is None:
                import crew_shell  # pylint: disable=import-outside-toplevel
                resolve_bash = crew_shell.resolve_gitbash
            path, reason = resolve_bash(strict=True)
            if path is None:
                bash, bash_problem = None, reason
            else:
                bash = path
        if any(argv[0].endswith(".ps1") for _, argv in chosen):
            if resolve_pwsh is None:
                import crew_shell  # pylint: disable=import-outside-toplevel
                resolve_pwsh = crew_shell.resolve_pwsh
            pwsh = resolve_pwsh()[0]
    if bash is None:
        return _no_bash(event, bash_problem, root, armed_fn)
    trace = env.get("CREW_HOOK_TRACE_FILE", "")
    results = [None] * len(chosen)
    threads = []

    def work(index, row, argv):
        remaining = mono_end - time.monotonic()
        own = min(float(row.timeout), remaining)
        script = os.path.join(scripts, argv[0])
        if not os.path.isfile(script):
            results[index] = {"exit": None, "stdout": b"", "stderr": b"", "timed_out": False, "pid": 0,
                              "error": f"{argv[0]} is missing at {script}"}
            return
        if own <= 0:
            results[index] = {"exit": None, "stdout": b"", "stderr": b"", "timed_out": True, "pid": 0,
                              "error": ""}
            return
        command, flavour = _argv_for(argv, scripts, bash, pwsh)
        child_env = dict(env, CREW_HOOK_FLAVOUR=flavour)
        results[index] = run_child(command, raw, own, child_env, cwd=None)
        _trace(trace, event, argv, results[index]["pid"])

    for index, (row, argv) in enumerate(chosen):
        thread = threading.Thread(target=work, args=(index, row, argv), daemon=True)
        threads.append(thread)
        thread.start()
    for thread in threads:
        thread.join()
    return _settle(event, chosen, results, root, armed_fn)


def _no_bash(event, problem, root, armed_fn):
    message = ("crew hooks need Git for Windows (a strictly resolved Git Bash), and none was found: "
               f"{problem}. Install Git for Windows.")
    if event in BLOCKING_EVENTS and armed_fn(root):
        return 2, b"", (message + "\n").encode("utf-8")
    if event == "SessionStart":
        return 0, (json.dumps({"systemMessage": message}) + "\n").encode("utf-8"), b""
    return 0, b"", (message + "\n").encode("utf-8")


def _settle(event, chosen, results, root, armed_fn):
    """Turn the children's raw results into merge input, applying B8."""
    merge_in, notes, faults = [], [], []
    for (row, argv), res in zip(chosen, results):
        name = " ".join(argv)
        if res["error"] or res["timed_out"]:
            reason = res["error"] or (f"{name} timed out (its limit is {row.timeout}s, or the dispatch "
                                      "deadline) and was killed")
            if row.guard and event in BLOCKING_EVENTS:
                faults.append(f"crew-hook: {reason}")
            else:
                notes.append(f"crew-hook: {reason}\n")
            continue
        merge_in.append({"exit": res["exit"], "stdout": _text(res["stdout"]), "stderr": _text(res["stderr"])})
    if faults and armed_fn(root):
        text = "".join(f"{line}; failing closed (armed repo).\n" for line in faults)
        return 2, b"", text.encode("utf-8")
    notes.extend(f"{line}; the repo is not armed, so this is not a block.\n" for line in faults)
    merged = merge(event, merge_in)
    stderr = merged["stderr"] + "".join(notes)
    return merged["exit"], merged["stdout"].encode("utf-8"), stderr.encode("utf-8")


def parse_args(argv):
    event, harness, rest = None, "claude", list(argv)
    while rest:
        item = rest.pop(0)
        if item == "--harness":
            harness = rest.pop(0) if rest else "claude"
        elif event is None:
            event = item
    return event, harness


def main(argv=None, stdin=None, stdout=None, stderr=None, env=None):
    env = dict(os.environ) if env is None else env
    stdin = stdin if stdin is not None else sys.stdin.buffer
    stdout = stdout if stdout is not None else sys.stdout.buffer
    stderr = stderr if stderr is not None else sys.stderr.buffer
    event, harness = parse_args(sys.argv[1:] if argv is None else argv)
    root = env.get("CLAUDE_PROJECT_DIR") or os.getcwd()
    code, out, err = 0, b"", b""
    try:
        if event not in EVENTS:
            return 0
        try:
            deadline = int(env["CREW_HOOK_DEADLINE"])
        except (KeyError, ValueError):
            deadline = now_ms() + (event_timeout(event) - DEADLINE_MARGIN) * 1000
        raw, problem = read_stdin(stdin, deadline)
        if problem:
            code, err = _fault(event, root, f"crew-hook: {problem}")
        else:
            code, out, err = dispatch(event, harness, raw, deadline, env, root)
    except Exception as exc:  # noqa: BLE001  pylint: disable=broad-exception-caught
        code, err = _fault(event, root, f"crew-hook: dispatcher error {type(exc).__name__}: {exc}")
    for stream, data in ((stdout, out), (stderr, err)):
        if data:
            try:
                stream.write(data)
                stream.flush()
            except (OSError, ValueError):
                pass  # the reader is gone; the exit code is all that is left to give
    return code


def _fault(event, root, message):
    if event in BLOCKING_EVENTS and armed(root):
        return 2, f"{message}; failing closed (armed repo).\n".encode("utf-8")
    return 0, f"{message}; the repo is not armed, or this event cannot block, so nothing is blocked.\n".encode("utf-8")


if __name__ == "__main__":
    sys.exit(main())

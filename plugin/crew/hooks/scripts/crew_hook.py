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
import functools
import hashlib
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
RETRY_FLOOR = 2.0         # seconds a timed-out guard's one retry must be able to have
TASKKILL_BOUND = 2        # seconds _kill_tree gives taskkill on Windows (its subprocess timeout)
RETRY_MARGIN = 0.5
# The rows whose one timed-out attempt may be repeated: stateless judges whose only side effect
# is an appended guard.log row (cloud-guard also a said-once marker that only silences a notice).
# Anything else (approval-hook, promote-gate, verify-gate, completion-audit) is never retried.
RETRY_SAFE = frozenset({"role-write-guard.sh", "cloud-guard.sh", "env-guard.sh", "scope-guard.sh"})


# Windows direct route (crew 1.3.60). On Git Bash every process start is an MSYS fork (0.1-0.5 s, seconds under
# load), and a Bash tool call used to cost about thirty of them: each `.sh` row started a Git Bash, whose wrapper
# started `$(crew_py_strict)` and then python and git. These wrappers are only launchers - the decision is the
# Python file - so on Windows `dispatch` starts that file with its own interpreter, with the environment the
# wrapper would have given it. A direct run is believed ONLY when it exits with a code the wrapper would have
# passed through unchanged; any other exit, a failed launch or a missing file runs the original `.sh` wrapper, so
# the wrapper's fail-closed handling, `armed` logic and `scope.mode off` proof stay where they are. A timeout is
# never rerun through the wrapper (the retry rule below already covers it). `CREW_HOOK_DIRECT=0` takes the old route.
#   module   the Python file that holds the decision
#   args     argv between the module and the row's extra args
#   accept   exit codes the wrapper passes through as they are
#   env      what the wrapper sets for the child
Direct = namedtuple("Direct", "module args accept env")
_UTF8 = {"PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"}
DIRECT = {
    "scope-guard.sh": Direct("scope_guard.py", (), (0, 2), _UTF8),
    "cloud-guard.sh": Direct("cloud_guard.py", (), (0,), dict(_UTF8, CREW_CLOUD_GUARD_FLAVOUR="bash")),
    "env-guard.sh": Direct("env_guard.py", (), (0,), dict(_UTF8, CREW_ENV_GUARD_FLAVOUR="bash")),
    "role-write-guard.sh": Direct("role_write_guard.py", (), (0, 2), _UTF8),
    "approval-hook.sh": Direct("approval_hook.py", (), (0, 2), _UTF8),
    "promote-gate.sh": Direct("_promote_gate.py", (), (0, 2), {"PYTHONIOENCODING": "utf-8"}),
    "crew-context.sh": Direct("crew_context.py", ("--flavour", "sh"), (0,), {}),
}
GIT_PROBE_SECONDS = 5


def _retry_reserve(windows):
    """Seconds the dispatch deadline must still have, beyond the retry's own run, for a second
    timeout to clean up: run_child after a timeout spends up to taskkill (Windows) + the
    waiter join (POST_KILL) + the reader join (POST_KILL), plus a margin."""
    return (TASKKILL_BOUND if windows else 0) + 2 * POST_KILL + RETRY_MARGIN


def _excerpt(data, limit=160):
    """First non-empty line of a child's stderr, trimmed, for a line that must stay one line."""
    for line in (data.decode("utf-8", errors="replace") if isinstance(data, bytes) else data or "").splitlines():
        if line.strip():
            return line.strip()[:limit]
    return ""
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
    `stdout`, `stderr` (text) in registration order; returns the same keys, `exit`
    being 2 or 0 and nothing else: a child that exited otherwise never decided, and
    `_settle` has already turned that into a fault or a note before it gets here."""
    blockers = [r for r in results if r.get("exit") == 2]
    if blockers:
        return {"exit": 2, "stdout": "",
                "stderr": "".join(_ensure_newline(r.get("stderr", "")) for r in blockers)}
    stderr = "".join(_ensure_newline(r.get("stderr", "")) for r in results if r.get("stderr"))
    live = [r for r in results if r.get("stdout", "").strip()]
    code = 0
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
        if not root:
            return True
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

# --------------------------------------------------------------------------
# the guards master switch (`guards.enabled`, crew 1.3.89; the owner's confirmation, 1.3.92)
#
# `guards.enabled: false` in the MACHINE config layer (`~/.claude/crew/config.json`) stands every guard row
# down: none starts, so nothing is judged, refused, asked or logged, and a fault in one cannot fail closed.
# `context-watch.sh` (a Stop hook, not a guard row) stands down with them: with the switch off NOTHING blocks.
# Off wins over any profile, override, `scope.mode` or `verifyGate`. Three things must all hold:
#   1. ONLY the machine layer counts (owner decision, 2026-11-13): a repo file (`.crew/config.json`, tracked or
#      not) is a checkout anyone can hand you; a `false` there is IGNORED (`repo_switch_ignored` reports it).
#   2. ONLY the JSON literal `false` counts, in a file with no duplicate key: absent, null, true, a string, a
#      corrupt or unreadable file, a `guards` that is not an object, or `{"enabled": true, "enabled": false}`
#      (two parsers disagree on which wins) leave the guards ON. Could-not-tell is never the disabling value.
#   3. The `false` must be the OWNER's (owner decision, 2026-11-13): `owner_confirmed` must find an applied
#      `/crew:confirm-config` double confirmation for `guards.enabled` at this very file, recording two
#      confirmations from two typed prompts and the canonical digest of the file as the owner left it (crew
#      1.3.94). An agent, a hook-side write or a hand edit that only sets the `false` leaves the guards ON
#      (`machine_switch_unconfirmed` reports it), and so does a file edited after the owner applied it, or a bare
#      hand-written record. These are guardrails against accidents and drift, NOT a boundary: the receipt is a
#      file the same user can write, so an agent that forges the whole of it is not stopped here.
# The machine file must also be the machine's: a config path inside the project (or the process's working
# directory), which is what a `HOME` / `USERPROFILE` pointed at a fake home shipped in a repo yields, never counts.
# approval-hook.sh is the exception: it records `/crew:approve` and the `/crew:confirm-config` double
# confirmation and judges no command, so the humanOnly opt-out keeps working with the guards off.
# Read here, not in each guard, because every guard row passes through `dispatch`. With no usable python the
# bash launcher never reaches this and still fails closed in an armed repo (it has no JSON parser by design).
GUARDS_KEPT = frozenset({"approval-hook.sh"})
STOOD_DOWN = frozenset({"context-watch.sh"})
MASTER_KEY = "guards.enabled"


def _no_duplicate_keys(pairs):
    seen = {}
    for key, value in pairs:
        if key in seen:
            raise ValueError(f"duplicate key {key!r}")
        seen[key] = value
    return seen


def _read_strict(path):
    """`path` parsed as JSON with no duplicate key at any depth; OSError or ValueError when it cannot be."""
    with open(path, encoding="utf-8-sig") as handle:
        return json.load(handle, object_pairs_hook=_no_duplicate_keys)


def _layer_says_off(path):
    """True only when the file at `path` parses (no duplicate key at any depth) to an object whose `guards` is an
    object holding `enabled: false` (the JSON literal)."""
    try:
        parsed = _read_strict(path)
    except (OSError, ValueError):
        return False
    guards = parsed.get("guards") if isinstance(parsed, dict) else None
    return isinstance(guards, dict) and guards.get("enabled") is False


def _inside(path, folder):
    path, folder = os.path.normcase(os.path.realpath(path)), os.path.normcase(os.path.realpath(folder))
    return path == folder or path.startswith(folder.rstrip(os.sep) + os.sep)


def machine_config_path(root, home=None):
    """The machine config file the switch reads, or None when that path cannot be the machine's: it lies inside
    the project `root` or the working directory (a HOME redirected into a checkout)."""
    home = home if home is not None else os.path.expanduser("~")
    path = os.path.join(home, GLOBAL_CONFIG)
    for folder in (root, os.getcwd()):
        if folder and _inside(path, folder):
            return None
    return path


def canonical_digest(path):
    """sha256 over the file's parsed content in canonical JSON (sorted keys, no whitespace), or None when it does
    not parse or holds a duplicate key. Whitespace and key order do not move it; a changed value does."""
    try:
        parsed = _read_strict(path)
    except (OSError, ValueError):
        return None
    return hashlib.sha256(json.dumps(parsed, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def _double_confirmed(record):
    """True when the record carries two confirmations that came from two DIFFERENT typed prompts."""
    confirmations = record.get("confirmations")
    if not isinstance(confirmations, list):
        return False
    prompts = {c.get("prompt") for c in confirmations
               if isinstance(c, dict) and c.get("via") == "user-prompt"
               and isinstance(c.get("prompt"), str) and c["prompt"].strip()}
    return len(prompts) >= 2


def owner_confirmed(path):
    """True when an applied `/crew:confirm-config` double confirmation backs `guards.enabled: false` at `path`
    (crew 1.3.94): the newest settled record for this (layer, file, key) is an applied `false`, records two
    confirmations from two typed prompts, and its `appliedDigest` is the canonical digest of the file AS IT IS.
    A file edited after the owner applied it (a hand edit, a restore, a rebuild, an agent) no longer matches, so
    the receipt backs nothing, and a record written without the confirmations, or without the digest, backs
    nothing either. The digest and the confirmations live in files the same user can write, so a hostile agent
    can still forge all of it: this is a guardrail against accidents and drift, not a boundary (CONFIG.md)."""
    import crew_humanonly  # pylint: disable=import-outside-toplevel
    records, problems = crew_humanonly.all_records(crew_humanonly.store_dir(path))
    if problems:
        return False
    target = crew_humanonly.target_key(path)
    settled = [r for r in records
               if r.get("layer") == "machine" and r.get("target") == target and r.get("key") == MASTER_KEY
               and r.get("state") in ("applied", "revoked") and isinstance(r.get("settled"), (int, float))]
    newest = max(settled, key=lambda r: r["settled"]) if settled else None
    if newest is None or newest.get("state") != "applied" or newest.get("value") is not False:
        return False
    digest = canonical_digest(path)
    return digest is not None and newest.get("appliedDigest") == digest and _double_confirmed(newest)


def guards_switched_off(root, home=None):
    """`"machine"` when the machine layer switched the guards off and the owner confirmed it, else None. A repo
    file cannot switch the guards off. Never raises: a failure to look reads as ON."""
    try:
        path = machine_config_path(root, home)
        if path and _layer_says_off(path) and owner_confirmed(path):
            return "machine"
    except Exception:  # noqa: BLE001  pylint: disable=broad-exception-caught
        return None
    return None


def machine_switch_unconfirmed(root, home=None):
    """True when the machine file holds `guards.enabled: false` that stands nothing down because the owner's
    confirmation is missing (or the path cannot be the machine's). None when it could not tell."""
    try:
        path = os.path.join(home if home is not None else os.path.expanduser("~"), GLOBAL_CONFIG)
        return _layer_says_off(path) and guards_switched_off(root, home) is None
    except Exception:  # noqa: BLE001  pylint: disable=broad-exception-caught
        return None


def repo_switch_ignored(root):
    """True when a repo-layer file holds `guards.enabled: false`, which does NOT stand any guard down. Never
    raises; None when it could not tell."""
    try:
        if not root:
            return False
        import crew_common  # pylint: disable=import-outside-toplevel
        crew_dir = crew_common.repo_config_dir(root)[0]
        return any(_layer_says_off(os.path.join(crew_dir, name)) for name in crew_common.CONFIG_NAMES)
    except Exception:  # noqa: BLE001  pylint: disable=broad-exception-caught
        return None


def without_guards(chosen):
    """`chosen` (`[(row, argv)]`) minus every guard row except `GUARDS_KEPT`, and minus `STOOD_DOWN`."""
    return [(row, argv) for row, argv in chosen
            if row.script not in STOOD_DOWN and (not row.guard or row.script in GUARDS_KEPT)]


def _guards_off(root):
    return guards_switched_off(root) is not None


def _never_armed(_root):
    return False


def now_ms():
    return int(time.time() * 1000)


def _windows():
    return os.name == "nt"


def _kill_tree(proc):
    if proc.poll() is not None:
        return
    if _windows():
        taskkill = os.path.join(os.environ.get("SystemRoot") or "C:\\Windows", "System32", "taskkill.exe")
        try:
            subprocess.run([taskkill, "/T", "/F", "/PID", str(proc.pid)], capture_output=True,
                           timeout=2, check=False)  # bounded well inside the 5 s the deadline keeps back
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


_SKIP = "skip"


def _approval_wanted(raw):
    """approval-hook.sh's own pre-filter: the word `approve` in any case, or `crew:confirm-config`.
    A prompt with neither exits 0 before any python is looked for."""
    return re.search(rb"approve", raw, re.IGNORECASE) is not None or b"crew:confirm-config" in raw


def _promote_plan(tool, env):
    """promote-gate.sh's own routing, for a Bash call: (cwd, extra env, stdin suffix) when the python gate
    decides, _SKIP when the wrapper would exit 0 before python (no map in the checkout and none at HEAD),
    None when the wrapper has to judge. The wrapper `cd`s to CLAUDE_PROJECT_DIR (else `.`) and a failed `cd` is
    its own exit 0; an unusable directory or a map that is not a regular file is left to it."""
    if tool != "Bash":
        return None
    project = env.get("CLAUDE_PROJECT_DIR") or "."
    if not os.path.isdir(project):
        return None
    gate_env = {"CREW_GATE_START": str(int(time.time())), "CREW_HEAD_MAP": "", "CREW_MAP_DIRTY": ""}
    shape = os.path.join(project, ".crew", "verify.json")
    if os.path.lexists(shape):
        return (project, gate_env, b"\n") if os.path.isfile(shape) and not os.path.islink(shape) else None
    try:
        import crew_common  # pylint: disable=import-outside-toplevel
        probe = [crew_common.require_tool("git"), "rev-parse", "-q", "--verify", "HEAD:./.crew/verify.json"]
        got = subprocess.run(probe, cwd=project, capture_output=True, stdin=subprocess.DEVNULL, check=False,
                             timeout=GIT_PROBE_SECONDS)
    except (OSError, subprocess.SubprocessError):
        return None
    return _SKIP if not got.stdout.strip() else None


def direct_plan(argv, payload, raw, env, scripts, executable=None):
    """How to run one `.sh` row without its wrapper: None (use the wrapper), `_SKIP` (the wrapper would have
    exited 0 without python) or (command, child env, cwd, stdin, accept). Pure but for promote-gate's git probe."""
    spec = DIRECT.get(argv[0])
    executable = sys.executable if executable is None else executable
    if spec is None or not executable:
        return None
    module = os.path.join(scripts, spec.module)
    if not os.path.isfile(module):
        return None
    cwd, extra, stdin = None, {}, raw
    if argv[0] == "approval-hook.sh" and not _approval_wanted(raw):
        return _SKIP
    if argv[0] == "promote-gate.sh":
        got = _promote_plan(tool_name(payload), env)
        if got in (None, _SKIP):
            return got
        cwd, extra, suffix = got
        stdin = raw + suffix
    command = [executable, module, *spec.args, *argv[1:]]
    return command, dict(env, **spec.env, **extra), cwd, stdin, spec.accept


def _argv_for(argv, scripts, bash, pwsh):
    """(command, flavour) for a selected argv: the twin through PowerShell, a
    `.sh` through bash (or the caller's resolved Git Bash)."""
    path = os.path.join(scripts, argv[0])
    if argv[0].endswith(".ps1"):
        if not pwsh:
            return None, "powershell"  # never a bare name: CreateProcess searches the repo first
        return [pwsh, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", path, *argv[1:]], "powershell"
    if bash and bash != "bash":
        return [bash, path.replace("\\", "/"), *argv[1:]], "bash"
    return ["bash", path, *argv[1:]], "bash"


TRACE_SUFFIX = ".crew-trace"
_TRACE_LOCK = threading.Lock()  # children finish on their own threads; one line must not tear another


def _append_trace(path, line):
    """Append one line to a trace file. Only a path ending in `.crew-trace` is honoured and
    a symlink is refused only where the platform has `O_NOFOLLOW` (POSIX; on Windows the flag is
    absent, 0 is substituted, and only the suffix rule applies), so the variable cannot point the
    dispatcher at a file something else reads (security pass)."""
    if not path or not path.endswith(TRACE_SUFFIX):
        return
    flags = os.O_WRONLY | os.O_APPEND | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0)
    try:
        with _TRACE_LOCK:
            fd = os.open(path, flags, 0o600)
            with os.fdopen(fd, "a", encoding="utf-8") as handle:
                handle.write(line)
    except OSError:
        pass


def _trace(path, event, argv, pid):
    """Append `event argv pid` to the file CREW_HOOK_TRACE_FILE names, for the suites."""
    _append_trace(path, f"{event} {' '.join(argv)} {pid}\n")


def _timing(path, event, argv, res):
    """Append `event argv pid attempts=N start_ms=S end_ms=E ms=D outcome` to the file
    CREW_HOOK_TIMING_FILE names (opt-in, the same `.crew-trace` and no-symlink rules as
    _trace): the per-child timing that tells a slow guard from a wedged one. When a retry
    replaced the first attempt, `first_said=` keeps that attempt's first stderr line and the
    outcome stays the LAST word of the line."""
    if "start_ms" not in res:
        return
    outcome = "timeout" if res.get("timed_out") else f"exit={res.get('exit')}"
    first = f" first_said={json.dumps(res['first_said'])}" if res.get("first_said") else ""
    if res.get("fell_back"):
        first += f" fell_back={json.dumps(res['fell_back'])}"
    _append_trace(path, f"{event} {' '.join(argv)} {res.get('pid', 0)} attempts={res.get('attempts', 1)} "
                        f"start_ms={res['start_ms']} end_ms={res['end_ms']} "
                        f"ms={res['end_ms'] - res['start_ms']}{first} {outcome}\n")


def dispatch(event, harness, raw, deadline_ms, env, root, windows=None, resolve_bash=None,
             resolve_pwsh=None, scripts=SCRIPTS, armed_fn=None, direct=None):
    """Run the event's rows; returns (exit, stdout bytes, stderr bytes). `deadline_ms` is
    the epoch deadline the launcher handed over; it is turned into a monotonic one here, so
    a clock that steps cannot stretch or shrink any bound after this point. `direct` (default:
    on Windows unless CREW_HOOK_DIRECT=0) lets the rows in `DIRECT` run their Python file
    without the Git Bash wrapper; see the comment at `DIRECT`."""
    mono_end = time.monotonic() + (deadline_ms - now_ms()) / 1000.0
    windows = _windows() if windows is None else windows
    direct = (windows and env.get("CREW_HOOK_DIRECT") != "0") if direct is None else direct
    payload = parse_payload(raw)
    chosen = select(event, harness, payload, windows=windows, scripts=scripts)
    armed_fn = armed_fn or armed
    if chosen and _guards_off(root):
        # `guards.enabled: false` in the machine layer, owner-confirmed (crew 1.3.92): no guard row starts, so nothing is judged, logged or
        # refused, and a fault in what is left cannot fail closed either. approval-hook.sh stays.
        chosen = without_guards(chosen)
        armed_fn = _never_armed
    if not chosen:
        return 0, b"", b""
    bash, pwsh, bash_problem = "bash", None, ""
    bash_state = {"lock": threading.Lock(), "done": False}

    def get_bash():
        """(path or None, problem): Git Bash resolved once, on first need. A row the direct route
        runs never asks."""
        with bash_state["lock"]:
            if not bash_state["done"]:
                resolver = resolve_bash
                if resolver is None:
                    import crew_shell  # pylint: disable=import-outside-toplevel
                    resolver = functools.partial(crew_shell.resolve_gitbash, lkg=crew_shell.LastKnownGood())
                path, reason = resolver(strict=True)
                bash_state["value"] = (path, reason if path is None else "")
                bash_state["done"] = True
            return bash_state["value"]

    if windows:
        # A row with no direct route always needs Git Bash, so it is resolved up front and a missing one
        # refuses the event as before. A row that has one asks only if its direct run is not believed.
        needs_bash = any(argv[0].endswith(".sh") and not (direct and argv[0] in DIRECT) for _, argv in chosen)
        if needs_bash:
            path, reason = get_bash()
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
    timing = env.get("CREW_HOOK_TIMING_FILE", "")
    results = [None] * len(chosen)
    threads = []

    def attempt(row, command, child_env, stdin, cwd, own):
        """One run of `command` with the row's single bounded retry (RETRY_SAFE only)."""
        res = run_child(command, stdin, own, child_env, cwd=cwd)
        res["attempts"] = 1
        if res["timed_out"] and row.guard:
            # One bounded retry, only for the rows in RETRY_SAFE (the PreToolUse judges). What
            # a repeat can do there: cloud/env/scope-guard and role_write_guard append a
            # guard.log row per run, so a retried call can leave a duplicate row, and cloud-guard
            # may have written its said-once marker, so the repeat stays silent about it. The
            # decision is never changed by either. Every other guard row keeps its single
            # attempt: approval-hook records an approval, completion-audit's `_block_once`
            # writes a marker and then exits 2 (a kill between the two makes a repeat delete the
            # marker and exit 0), and promote-gate / verify-gate run longer than a retry could.
            # The retry also needs the dispatch deadline to leave room for the cleanup of a
            # second timeout (see _retry_reserve), so a retried guard cannot outlive the deadline.
            if row.script not in RETRY_SAFE:
                res["no_retry"] = "this row is not retry-safe"
            else:
                retry_for = min(float(row.timeout),
                                mono_end - time.monotonic() - _retry_reserve(windows))
                if retry_for >= RETRY_FLOOR:
                    first = res
                    res = run_child(command, stdin, retry_for, child_env, cwd=cwd)
                    res["attempts"] = 2
                    res["first_said"] = _excerpt(first["stderr"])
                else:
                    res["no_retry"] = "no room before the dispatch deadline"
        return res

    def run_wrapper(row, argv, own):
        use_bash = bash
        if windows and bash == "bash":  # not resolved up front: every row so far ran directly
            use_bash, problem = get_bash()
            if use_bash is None:
                return {"exit": None, "stdout": b"", "stderr": b"", "timed_out": False, "pid": 0,
                        "error": _no_bash_message(problem)}
        command, flavour = _argv_for(argv, scripts, use_bash, pwsh)
        if command is None:
            return {"exit": None, "stdout": b"", "stderr": b"", "timed_out": False, "pid": 0,
                    "error": f"no PowerShell was found to run {argv[0]}"}
        return attempt(row, command, dict(env, CREW_HOOK_FLAVOUR=flavour), raw, None, own)

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
                              "error": "", "attempts": 0, "no_retry": "the dispatch deadline had passed"}
            return
        started = now_ms()
        plan = direct_plan(argv, payload, raw, env, scripts) if direct and argv[0] in DIRECT else None
        if plan == _SKIP:
            res = {"exit": 0, "stdout": b"", "stderr": b"", "timed_out": False, "error": "", "pid": 0,
                   "attempts": 1}
        elif plan is not None:
            command, child_env, cwd, stdin, accept = plan
            res = attempt(row, command, dict(child_env, CREW_HOOK_FLAVOUR="bash"), stdin, cwd, own)
            if not res["timed_out"] and (res["error"] or res["exit"] not in accept):
                # not a decision the wrapper would have passed through: the wrapper judges, as it always did
                said = res["error"] or f"exit {res['exit']}"
                own = min(float(row.timeout), mono_end - time.monotonic())
                if own <= 0:
                    res = {"exit": None, "stdout": b"", "stderr": b"", "timed_out": True, "pid": 0, "error": "",
                           "attempts": 0, "no_retry": "the dispatch deadline had passed"}
                else:
                    res = run_wrapper(row, argv, own)
                res["fell_back"] = said
        else:
            res = run_wrapper(row, argv, own)
        res["start_ms"], res["end_ms"] = started, now_ms()
        results[index] = res
        _trace(trace, event, argv, res["pid"])
        _timing(timing, event, argv, res)

    for index, (row, argv) in enumerate(chosen):
        thread = threading.Thread(target=work, args=(index, row, argv), daemon=True)
        threads.append(thread)
        thread.start()
    for thread in threads:
        thread.join()
    return _settle(event, chosen, results, root, armed_fn)


def _no_bash_message(problem):
    # The wording follows what was actually established (a resolver that returns a bare str
    # means "absent"): a Git Bash that exists but did not answer is a busy host, not a missing
    # Git, and must never say "Install Git for Windows". Fail closed in every case.
    kind = getattr(problem, "kind", "absent")
    if kind == "absent":
        message = ("crew hooks need Git for Windows (a strictly resolved Git Bash), and none was found: "
                   f"{problem}. Install Git for Windows.")
    elif kind == "unknown":
        message = (f"crew hooks could not tell whether Git Bash works (could not tell, not 'missing'): {problem}. "
                   "This is not a missing-Git error: wait a few seconds and retry the same call. Nothing was "
                   "judged, so this call is blocked rather than let through unchecked.")
    else:
        message = (f"crew hooks found Git Bash but it failed its self-test: {problem}. "
                   "Repair or reinstall Git for Windows.")
    return message


def _no_bash(event, problem, root, armed_fn):
    message = _no_bash_message(problem)
    if event in BLOCKING_EVENTS and armed_fn(root):
        return 2, b"", (message + "\n").encode("utf-8")
    if event == "SessionStart":
        return 0, (json.dumps({"systemMessage": message}) + "\n").encode("utf-8"), b""
    return 0, b"", (message + "\n").encode("utf-8")


UNKNOWN_TIMEOUT = "crew-hook: UNKNOWN (guard timeout, not a policy deny)"
UNKNOWN_RESOURCE = "crew-hook: UNKNOWN (resource exhaustion, not a policy deny)"
UNKNOWN_PYTHON = "crew-hook: UNKNOWN (no usable python, not a policy deny)"
# Anchored to the diagnostic forms a failed fork or allocation really prints, one per line: a
# prefix of `word: ` labels (`bash: `, `env-guard: `), then the message, or an exception line. Text
# that merely QUOTES these words (a path such as C:\work\MemoryError-tests\guard.py in a traceback,
# a quoted command naming EAGAIN, a sentence mentioning errno 11) starts with none of them.
_LBL = r"(?:[\w.\-]+:[ \t]+)*"
_RESOURCE_RE = re.compile(
    r"^[ \t]*(?:\d+[ \t]+\[main\][ \t]+\S+[ \t]+\d+[ \t]+)?" + _LBL
    + r"(?:fork:[ \t]+(?:retry:[ \t]+)?(?:Resource temporarily unavailable|failed|cannot)\b"
    r"|dofork:[ \t]+child\b[^\n]*\berrno 11\b"
    r"|fork failed\b"
    r"|(?:can(?:'|no)t|unable to|could not|failed to)[ \t]+fork\b"
    r"|(?:\[Errno 12\][ \t]+)?Cannot allocate memory\b)"
    r"|^[ \t]*(?:\w*Error:[ \t]+)?\[Errno 11\][ \t]+Resource temporarily unavailable\b"
    r"|^could not start\b[^\n]*\[Errno 11\]"
    r"|^[ \t]*OSError:[ \t]+\[Errno 11\]"
    r"|^[ \t]*MemoryError\b"
    r"|^[ \t]*\w*Error:[ \t]+EAGAIN\b",
    re.IGNORECASE | re.MULTILINE)
# The guards' own fixed no-python refusals (each is the literal first words of the `echo ... >&2;
# exit 2` in the .sh named beside it; a test pins every one to its script). A refusal is the whole
# of that guard's stderr, so only a stderr that is exactly ONE line starting with one of these is
# relabelled: a real deny that merely quotes the words (a path such as notes/no usable python.md in
# scope-guard's `refused {tool} on {path}`) neither starts with them nor is a single such line.
NO_PYTHON_REFUSALS = (
    "SCOPE GUARD: no usable python - cannot judge",                        # scope-guard.sh
    "cloud-guard: no usable python, and",                                  # cloud-guard.sh
    "env-guard: no usable python, and",                                    # env-guard.sh
    "COMPLETION AUDIT: no usable python - the tree was not audited",       # completion-audit.sh
    "crew: /crew:approve was NOT recorded -- no usable python",            # approval-hook.sh
    "crew: /crew:confirm-config was NOT recorded -- no usable python",     # approval-hook.sh
    "PROMOTION BLOCKED: no usable python",                                 # promote-gate.sh
    "role-write-guard: no usable python found",                            # role-write-guard.sh
)


def _is_no_python_refusal(stderr):
    lines = stderr.strip().splitlines()
    return len(lines) == 1 and lines[0].startswith(NO_PYTHON_REFUSALS)


def _unknown_label(res):
    """The label naming WHY a guard did not decide, or "" when it is none of the known causes.
    It reads stderr in every branch that has no decision (error, timeout, undecided exit), because
    an undecided child never reaches the timeout branch. A label never changes the verdict: the
    caller still fails closed. Resource exhaustion is looked for first, since a guard that could
    not fork also tends to time out."""
    said = _text(res["stderr"])
    if _RESOURCE_RE.search(said) or _RESOURCE_RE.search(res["error"] or ""):
        return UNKNOWN_RESOURCE
    if res["timed_out"]:
        return UNKNOWN_TIMEOUT
    return ""


def _settle(event, chosen, results, root, armed_fn):
    """Turn the children's raw results into merge input, applying B8."""
    merge_in, notes, faults, heard = [], [], [], []
    for (row, argv), res in zip(chosen, results):
        name = " ".join(argv)
        undecided = not res["error"] and not res["timed_out"] and res["exit"] not in (0, 2)
        if res["error"] or res["timed_out"] or undecided:
            attempts = res.get("attempts", 1)
            why = f"; no retry: {res['no_retry']}" if res.get("no_retry") else ""
            first = f"; attempt 1 said: {res['first_said']!r}" if res.get("first_said") else ""
            reason = res["error"] or (f"{name} timed out (attempts={attempts}{why}{first}; its limit is "
                                      f"{row.timeout}s, or the dispatch deadline) and was killed")
            if undecided:
                reason = f"{name} exited {res['exit']} without a decision"
            label = _unknown_label(res)
            said = _text(res["stderr"])
            if said:
                heard.append(said if said.endswith("\n") else said + "\n")
            if row.guard and event in BLOCKING_EVENTS:
                faults.append((label, f"crew-hook: {reason}"))
            else:
                notes.append((f"{label}\n" if label else "") + f"crew-hook: {reason}\n")
            continue
        stderr = _text(res["stderr"])
        if res["exit"] == 2 and _is_no_python_refusal(stderr):
            # a guard's own "no usable python" refusal still blocks, but it is not a policy deny
            stderr = UNKNOWN_PYTHON + "\n" + stderr
        merge_in.append({"exit": res["exit"], "stdout": _text(res["stdout"]), "stderr": stderr})
    if faults and armed_fn(root):
        text = "".join((f"{label}\n" if label else "") + f"{line}; failing closed (armed repo).\n"
                       for label, line in faults)
        # a child that did block still gets to say why
        return 2, b"", (merge(event, merge_in)["stderr"] + "".join(heard) + text).encode("utf-8")
    notes.extend((f"{label}\n" if label else "") + f"{line}; the repo is not armed, so this is not a block.\n"
                 for label, line in faults)
    merged = merge(event, merge_in)
    stderr = merged["stderr"] + "".join(heard) + "".join(notes)
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
    root = env.get("CLAUDE_PROJECT_DIR") or ""
    code, out, err = 0, b"", b""
    try:
        root = root or os.getcwd()
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
    if event in BLOCKING_EVENTS and armed(root) and not _guards_off(root):
        return 2, f"{message}; failing closed (armed repo).\n".encode("utf-8")
    return 0, f"{message}; the repo is not armed, or this event cannot block, so nothing is blocked.\n".encode("utf-8")


if __name__ == "__main__":
    sys.exit(main())

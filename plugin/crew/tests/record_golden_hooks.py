#!/usr/bin/env python3
"""Record, and check, the per-script outputs of crew's hooks (L-0727, plan Step 6).

The hook dispatcher (`crew_hook.py`) must give the same decisions as the
registrations it replaced. This module records what each `.sh` hook script
does today for a matrix of payloads, in throwaway repos, armed and unarmed,
and `test_crew_hook_parity.py` replays the matrix through the real launcher.

    python3 record_golden_hooks.py --record     # (re)write golden_hooks/
    python3 record_golden_hooks.py --check      # re-run; "0 drift" or a diff
    python3 record_golden_hooks.py --latency before|after

Everything is recorded from real runs, never written by hand (GEN-10). A run
that exceeds its timeout is `timed_out: true` with no exit code, never exit 0
(GEN-01). Each script runs with a constructed environment and a temporary HOME
(PYTHON-07, PYTHON-08): nothing here reads or writes the real config.

`golden_hooks/registrations-before.json` is hooks.json as it stood before the
dispatcher: the entry list `test_hooks_json_shape.py` holds `crew_hook.TABLE`
against. `golden_hooks/no-python/` is the same matrix with every script run
under a PATH that holds bash and coreutils only.
"""
import argparse
import contextlib
import io
import json
import os
import re
import shutil
import statistics
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import context  # noqa: E402,F401  pylint: disable=wrong-import-position,unused-import
import crew_fixtures  # noqa: E402  pylint: disable=wrong-import-position
import scope_fixtures  # noqa: E402  pylint: disable=wrong-import-position

PLUGIN = os.path.dirname(HERE)
SCRIPTS = os.path.join(PLUGIN, "hooks", "scripts")
GOLDEN = os.path.join(HERE, "golden_hooks")
REGISTRATIONS = os.path.join(GOLDEN, "registrations-before.json")
RUN_CAP = 120
ARMED_CONFIG = {"scope": {"mode": "block"},
                "guards": {"cloudGuard": "block", "envGuard": "block", "roleWrites": "block"}}
VERIFY = {"environments": {
    "prod": {"deploy": "deploy-prod", "rollback": "runbook.md", "requireReview": False,
             "reviewReason": "fixture"},
    "dev": {"deploy": "deploy-dev", "rollback": "none", "rollbackReason": "fixture",
            "requireReview": False, "reviewReason": "fixture"}}}
CLOUD = "aws ec2 terminate-instances --instance-ids i-0123456789abcdef0"
UNICODE_FILE = "src/caf\u00e9.py"


def _tool(name, **tool_input):
    return {"hook_event_name": "PreToolUse", "tool_name": name, "tool_input": tool_input,
            "session_id": "s-1", "tool_use_id": "tu-1"}


def _post(name, **tool_input):
    return {"hook_event_name": "PostToolUse", "tool_name": name, "tool_input": tool_input,
            "tool_response": {"ok": True}, "session_id": "s-1", "tool_use_id": "tu-1"}


def _cases():
    """(event, case, payload, kind): kind 'tool' payloads get `cwd` filled in at run time.
    The matrix of plan Step 6."""
    cases = []

    def add(event, name, payload):
        cases.append((event, name, payload))

    add("PreToolUse", "bash-plain", _tool("Bash", command="ls -la"))
    add("PreToolUse", "bash-cloud-blocked", _tool("Bash", command=CLOUD))
    add("PreToolUse", "bash-env-dump", _tool("Bash", command="printenv"))
    add("PreToolUse", "bash-declared-deploy", _tool("Bash", command="deploy-prod"))
    add("PreToolUse", "bash-declared-deploy-allowed", _tool("Bash", command="deploy-dev"))
    add("PreToolUse", "bash-out-of-touch-redirect", _tool("Bash", command="echo hi > other/keep.py"))
    add("PreToolUse", "bash-approval-forgery",
        _tool("Bash", command="python3 hooks/scripts/crew_ticket.py approve --ticket T-1"))
    add("PreToolUse", "powershell-plain", _tool("PowerShell", command="Get-ChildItem"))
    add("PreToolUse", "powershell-cloud-blocked", _tool("PowerShell", command=CLOUD))
    add("PreToolUse", "powershell-declared-deploy", _tool("PowerShell", command="deploy-prod"))
    for tool in ("Write", "Edit", "MultiEdit", "NotebookEdit"):
        key = "notebook_path" if tool == "NotebookEdit" else "file_path"
        low = tool.lower()
        add("PreToolUse", f"{low}-in-touch", _tool(tool, **{key: "{ROOT}/src/app.py"}))
        add("PreToolUse", f"{low}-out-of-touch", _tool(tool, **{key: "{ROOT}/other/keep.py"}))
    for tool in ("Write", "Edit"):
        payload = _tool(tool, file_path="{ROOT}/src/app.py")
        payload["agent_type"] = "crew:reviewer"
        add("PreToolUse", f"{tool.lower()}-restricted-role", payload)
    add("PreToolUse", "read-no-match", _tool("Read", file_path="{ROOT}/src/app.py"))
    add("UserPromptSubmit", "plain", {"hook_event_name": "UserPromptSubmit", "prompt": "hello",
                                      "session_id": "s-1", "prompt_id": "p-1"})
    add("UserPromptSubmit", "approve-ticket", {"hook_event_name": "UserPromptSubmit",
                                               "prompt": "/crew:approve T-2", "session_id": "s-1",
                                               "prompt_id": "p-2"})
    add("UserPromptSubmit", "approve-unknown", {"hook_event_name": "UserPromptSubmit",
                                                "prompt": "/crew:approve T-404", "session_id": "s-1",
                                                "prompt_id": "p-3"})
    add("PostToolUse", "read", _post("Read", file_path="{ROOT}/src/app.py"))
    add("PostToolUse", "edit", _post("Edit", file_path="{ROOT}/src/app.py"))
    add("PostToolUse", "mcp-obsidian", _post("mcp__obsidian__search", query="x"))
    add("PostToolUse", "grep-no-match", _post("Grep", pattern="x"))
    add("SubagentStart", "reviewer", {"hook_event_name": "SubagentStart", "agent_type": "crew:reviewer",
                                      "session_id": "s-1"})
    for source in ("startup", "clear", "compact"):
        add("SessionStart", source, {"hook_event_name": "SessionStart", "source": source,
                                     "session_id": "s-1"})
    add("PreCompact", "manual", {"hook_event_name": "PreCompact", "trigger": "manual", "session_id": "s-1"})
    add("Notification", "permission", {"hook_event_name": "Notification",
                                       "notification_type": "permission_prompt",
                                       "message": "needs permission", "session_id": "s-1"})
    add("Notification", "idle", {"hook_event_name": "Notification", "notification_type": "idle_prompt",
                                 "message": "waiting", "session_id": "s-1"})
    add("Stop", "clean-tree", {"hook_event_name": "Stop", "stop_hook_active": False, "session_id": "s-1"})
    add("Stop", "unmapped-change", {"hook_event_name": "Stop", "stop_hook_active": False,
                                    "session_id": "s-1", "_dirty": "src/app.py"})
    return cases


CODEX_CASES = (
    ("SessionStart", "codex-session", {"hook_event_name": "SessionStart", "source": "startup",
                                       "session_id": "s-1"}),
    ("PostToolUse", "codex-apply-patch", _post("apply_patch", input="*** Begin Patch")),
    ("PostToolUse", "codex-vault", _post("mcp__vault__read", query="x")),
    ("PostToolUse", "codex-grep-no-match", _post("Grep", pattern="x")),
)

# (name, base case, transform) -- payload variants of plan Step 6.
VARIANTS = ("bom", "nonascii", "crlf", "malformed")
VARIANT_BASES = (("PreToolUse", "bash-cloud-blocked"), ("PreToolUse", "write-out-of-touch"),
                 ("UserPromptSubmit", "plain"))


def _encode(payload, variant, root):
    """The stdin bytes: JSON with {ROOT} filled in, then the variant applied."""
    if isinstance(payload, dict):
        payload = {k: v for k, v in payload.items() if not k.startswith("_")}
        payload.setdefault("cwd", root)
    text = json.dumps(payload, ensure_ascii=False) if not isinstance(payload, str) else payload
    text = text.replace("{ROOT}", root.replace("\\", "/"))
    if variant == "nonascii":
        text = text.replace("src/app.py", UNICODE_FILE)
    if variant == "crlf":
        text = json.dumps(json.loads(text), ensure_ascii=False, indent=1).replace("\n", "\r\n") + "\r\n"
    data = text.encode("utf-8")
    if variant == "bom":
        data = b"\xef\xbb\xbf" + data
    if variant == "malformed":
        data = text.rstrip().rstrip("}").encode("utf-8")
    return data


def build_repo(base, armed, dirty=None):
    """A fresh fixture repo under `base` (and its HOME). Armed: scope block, the
    cloud, env and role guards at block, an approved ticket T-1 touching src/**,
    an unapproved T-2, a declared prod deploy. Unarmed: a bare git repo."""
    home = os.path.join(base, "home")
    os.makedirs(os.path.join(home, ".claude"), exist_ok=True)
    pinned = ("HOME", "USERPROFILE", "GIT_AUTHOR_DATE", "GIT_COMMITTER_DATE")
    saved = {key: os.environ.get(key) for key in pinned}
    os.environ["GIT_AUTHOR_DATE"] = os.environ["GIT_COMMITTER_DATE"] = "2026-01-01T00:00:00+0000"
    os.environ["HOME"] = os.environ["USERPROFILE"] = home
    try:
        if armed:
            import pathlib  # pylint: disable=import-outside-toplevel
            root = scope_fixtures.make_repo(pathlib.Path(base), mode="block")
            (root / ".crew" / "config.json").write_text(json.dumps(ARMED_CONFIG), encoding="utf-8")
            (root / ".crew" / "verify.json").write_text(json.dumps(VERIFY), encoding="utf-8")
            for args in (("add", "-f", ".crew/verify.json"), ("commit", "-qm", "verify map")):
                subprocess.run(["git", *args], cwd=str(root), check=True, capture_output=True)
            with contextlib.redirect_stdout(io.StringIO()):
                scope_fixtures.ready(root, "T-1", touch=("src/**",))
            scope_fixtures.make_ticket(root, "T-2", touch=("src/**",), activate=False)
        else:
            import pathlib  # pylint: disable=import-outside-toplevel
            from review_fixtures import init_repo  # pylint: disable=import-outside-toplevel
            root = init_repo(pathlib.Path(base) / "r")
            (root / "src").mkdir()
            (root / "src" / "app.py").write_text("x = 1\n", encoding="utf-8")
    finally:
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
    if dirty:
        with open(os.path.join(str(root), dirty), "a", encoding="utf-8") as handle:
            handle.write("y = 2\n")
    return str(root), home


def env_for(root, home, path=None, plugin=PLUGIN):
    """A constructed environment, never a copy of the real one."""
    # What a process needs just to start: the platform's own variables on Windows
    # (they are absent on POSIX and so add nothing there).
    names = ("LANG", "LC_ALL", "TERM", "XDG_CACHE_HOME", "SystemRoot", "SYSTEMROOT", "windir", "COMSPEC",
             "PATHEXT", "TEMP", "TMP", "ProgramFiles", "ProgramFiles(x86)", "ProgramData", "APPDATA",
             "LOCALAPPDATA")
    keep = {key: os.environ[key] for key in names if key in os.environ}
    env = dict(keep, HOME=home, USERPROFILE=home, CLAUDE_PROJECT_DIR=root, CLAUDE_PLUGIN_ROOT=plugin,
               PATH=path if path is not None else os.environ.get("PATH", ""),
               PYTHONDONTWRITEBYTECODE="1", TMPDIR=os.path.join(os.path.dirname(home), "tmp"))
    os.makedirs(env["TMPDIR"], exist_ok=True)
    return env


def normalise(text, root, home, extra=()):
    """Stable text: the run-specific paths and clocks replaced by tokens."""
    pairs = [(os.path.realpath(root), "<ROOT>"), (root, "<ROOT>"), (home, "<HOME>"), (SCRIPTS, "<SCRIPTS>"),
             (PLUGIN, "<PLUGIN>"), (os.path.dirname(os.path.dirname(home)), "<TMP>")]
    pairs += list(extra)
    for old, new in sorted(pairs, key=lambda p: -len(p[0])):
        if old:
            text = text.replace(old, new).replace(old.replace("\\", "/"), new)
    text = re.sub(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(\.\d+)?Z?", "<TIME>", text)
    text = re.sub(r"column \d+", "column <N>", text)
    return re.sub(r"\b1[67]\d{8}\b", "<EPOCH>", text)


def registrations(path=REGISTRATIONS):
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)["entries"]


def _matches(matcher, tool):
    if not matcher:
        return True
    if re.fullmatch(r"[A-Za-z0-9_|]+", matcher):
        return tool in matcher.split("|")
    return re.fullmatch(matcher, tool or "") is not None


def flatten_hooks_json(text):
    """hooks.json -> [{event, matcher, flavour, script, extra, timeout}] in file order."""
    entries = []
    for event, rows in json.loads(text)["hooks"].items():
        for row in rows:
            for hook in row["hooks"]:
                command = hook["command"]
                match = re.search(r'hooks/scripts/([\w.-]+)"\s*(.*?)(?:;\s*exit \$LASTEXITCODE)?$', command)
                entries.append({"event": event, "matcher": row.get("matcher", ""),
                                "flavour": "powershell" if hook.get("shell") == "powershell" else "bash",
                                "script": match.group(1), "extra": match.group(2).split(),
                                "timeout": hook.get("timeout")})
    return entries


def rows_for(event, tool, entries):
    return [e for e in entries if e["event"] == event and e["flavour"] == "bash" and _matches(e["matcher"], tool)]


def run_script(argv, data, env, cwd, timeout):
    started = time.monotonic()
    try:
        done = subprocess.run(argv, input=data, capture_output=True, env=env, cwd=cwd, timeout=timeout,
                              check=False, stdin=None)
    except subprocess.TimeoutExpired as exc:
        return {"exit": None, "timed_out": True, "stdout": (exc.stdout or b"").decode("utf-8", "replace"),
                "stderr": (exc.stderr or b"").decode("utf-8", "replace"), "seconds": time.monotonic() - started}
    return {"exit": done.returncode, "timed_out": False, "stdout": done.stdout.decode("utf-8", "replace"),
            "stderr": done.stderr.decode("utf-8", "replace"), "seconds": time.monotonic() - started}


def no_python_path(base):
    """A PATH directory holding bash and coreutils only: /usr/bin and /bin minus every python."""
    bindir = os.path.join(base, "nopython-bin")
    os.makedirs(bindir, exist_ok=True)
    crew_fixtures.link_path_dirs(bindir, skip=lambda name: bool(re.match(r"(python|py\d?$|pip|uv|conda)", name)))
    return bindir


def case_key(event, name, armed, variant=""):
    return f"{event}/{name}{('+' + variant) if variant else ''}.{'armed' if armed else 'unarmed'}"


def all_runs():
    """[(event, name, variant, payload, harness)] for the whole matrix."""
    runs = []
    for event, name, payload in _cases():
        runs.append((event, name, "", payload, "claude"))
    for base_event, base_name in VARIANT_BASES:
        payload = next(p for e, n, p in _cases() if (e, n) == (base_event, base_name))
        for variant in VARIANTS:
            runs.append((base_event, base_name, variant, payload, "claude"))
    for event, name, payload in CODEX_CASES:
        runs.append((event, name, "", payload, "codex"))
    return runs


def record_one(event, name, variant, payload, harness, armed, entries, no_python=False):
    base = tempfile.mkdtemp(prefix="crew-golden-")
    try:
        dirty = payload.get("_dirty") if isinstance(payload, dict) else None
        root, home = build_repo(base, armed, dirty)
        path = no_python_path(base) if no_python else None
        env = env_for(root, home, path=path)
        data = _encode(payload, variant, root)
        tool = None
        try:
            tool = json.loads(data.decode("utf-8-sig")).get("tool_name")
        except (ValueError, UnicodeDecodeError, AttributeError):
            tool = None
        if harness == "codex":
            codex_ok = event == "SessionStart" or (event == "PostToolUse" and (
                _matches("apply_patch|Edit|Write", tool)
                or _matches("mcp__.*(obsidian|vault|basic[-_]memory).*", tool)))
            selected = [{"script": "crew-context.sh", "extra": ["--harness", "codex"], "timeout": 20}] \
                if codex_ok else []
        else:
            selected = rows_for(event, tool if tool is not None else None, entries) if tool is not None \
                else [e for e in entries if e["event"] == event and e["flavour"] == "bash"]
        bash = crew_fixtures.resolve_bash() or "bash"
        rows = []
        for entry in selected:
            argv = [bash, os.path.join(SCRIPTS, entry["script"]), *entry["extra"]]
            result = run_script(argv, data, env, root, min(entry["timeout"], RUN_CAP))
            rows.append({"script": entry["script"], "flavour": "bash", "argv": [entry["script"], *entry["extra"]],
                         "exit": result["exit"], "timed_out": result["timed_out"],
                         "stdout": normalise(result["stdout"], root, home),
                         "stderr": normalise(result["stderr"], root, home)})
        shown = data.decode("utf-8", "replace").replace(root.replace("\\", "/"), "{ROOT}")
        return {"event": event, "case": name, "variant": variant, "harness": harness, "armed": armed,
                "dirty": dirty or "", "no_python": no_python, "payload": shown,
                "rows": rows}
    finally:
        shutil.rmtree(base, ignore_errors=True)


def golden_path(record, no_python):
    folder = os.path.join(GOLDEN, "no-python") if no_python else GOLDEN
    return os.path.join(folder, case_key(record["event"], record["case"], record["armed"], record["variant"]) + ".json")


def matrix(no_python):
    entries = registrations()
    for event, name, variant, payload, harness in all_runs():
        for armed in (True, False):
            yield record_one(event, name, variant, payload, harness, armed, entries, no_python)


def write_all():
    for no_python in (False, True):
        for record in matrix(no_python):
            path = golden_path(record, no_python)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            text = json.dumps(record, indent=1, ensure_ascii=False, sort_keys=True) + "\n"
            with open(path, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(text)


def load_golden():
    out = {}
    for folder, flag in ((GOLDEN, False), (os.path.join(GOLDEN, "no-python"), True)):
        for event in sorted(os.listdir(folder)) if os.path.isdir(folder) else ():
            sub = os.path.join(folder, event)
            if not os.path.isdir(sub) or event == "no-python":
                continue
            for name in sorted(os.listdir(sub)):
                with open(os.path.join(sub, name), encoding="utf-8") as handle:
                    record = json.load(handle)
                out[(flag, record["event"], record["case"], record["variant"], record["armed"])] = record
    return out


def check():
    golden = load_golden()
    drift = []
    seen = set()
    for no_python in (False, True):
        for record in matrix(no_python):
            key = (no_python, record["event"], record["case"], record["variant"], record["armed"])
            seen.add(key)
            old = golden.get(key)
            if old is None:
                drift.append(f"unrecorded: {key}")
            elif old["rows"] != record["rows"]:
                was, now = json.dumps(old["rows"])[:600], json.dumps(record["rows"])[:600]
                drift.append(f"changed: {key}\n  recorded {was}\n  now      {now}")
    drift += [f"not run: {key}" for key in golden if key not in seen]
    print(f"{len(drift)} drift")
    for line in drift:
        print(line)
    return 1 if drift else 0


def measure(label):
    """Latency of PreToolUse(Bash) and Stop(clean): 3 warm runs through the registered bash
    commands (all of an event's matching entries, in parallel, as Claude Code runs them)."""
    out = {"label": label, "host": os.uname().nodename if hasattr(os, "uname") else "", "cpus": os.cpu_count(),
           "loadavg": list(os.getloadavg()) if hasattr(os, "getloadavg") else [], "runs": {}}
    base = tempfile.mkdtemp(prefix="crew-latency-")
    try:
        root, home = build_repo(base, True)
        env = env_for(root, home)
        for event, name, payload in (("PreToolUse", "Bash", _tool("Bash", command="ls")),
                                     ("Stop", "clean", {"hook_event_name": "Stop", "session_id": "s-1"})):
            data = _encode(payload, "", root)
            samples = []
            for _ in range(4):
                samples.append(_event_seconds(label, event, data, env, root))
            warm = samples[1:]
            out["runs"][f"{event}({name})"] = {"warm_seconds": warm, "median_ms": round(statistics.median(warm) * 1000)}
    finally:
        shutil.rmtree(base, ignore_errors=True)
    path = os.path.join(GOLDEN, f"latency-{label}.json")
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(out, indent=1) + "\n")
    print(json.dumps(out, indent=1))
    return 0


def _event_seconds(label, event, data, env, root):
    started = time.monotonic()
    if label == "before":
        tool = json.loads(data).get("tool_name")
        bash = crew_fixtures.resolve_bash() or "bash"
        procs = [subprocess.Popen([bash, os.path.join(SCRIPTS, e["script"]), *e["extra"]],  # pylint: disable=consider-using-with
                                  stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                  env=env, cwd=root)
                 for e in rows_for(event, tool, registrations())]
    else:
        launcher = [crew_fixtures.resolve_bash() or "bash", os.path.join(SCRIPTS, "crew-hook.sh"), event]
        procs = [subprocess.Popen(launcher, stdin=subprocess.PIPE, stdout=subprocess.PIPE,  # pylint: disable=consider-using-with
                                  stderr=subprocess.PIPE, env=env, cwd=root)]
    # Claude Code hands every hook its payload at once, so the payload goes to every
    # process before any is waited on; communicating one at a time would serialise them.
    for proc in procs:
        proc.stdin.write(data)
        proc.stdin.close()
    for proc in procs:
        proc.communicate(timeout=RUN_CAP)
    return time.monotonic() - started


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", maxsplit=1)[0])
    parser.add_argument("--record", action="store_true")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--latency", choices=("before", "after"))
    parser.add_argument("--registrations-from", metavar="REF", help="write registrations-before.json from git REF")
    args = parser.parse_args(argv)
    if args.registrations_from:
        text = subprocess.run(["git", "show", f"{args.registrations_from}:plugin/crew/hooks/hooks.json"],
                              capture_output=True, text=True, check=True, cwd=PLUGIN).stdout
        os.makedirs(GOLDEN, exist_ok=True)
        with open(REGISTRATIONS, "w", encoding="utf-8", newline="\n") as handle:
            entries = flatten_hooks_json(text)
            handle.write(json.dumps({"ref": args.registrations_from, "entries": entries}, indent=1) + "\n")
    if args.record:
        write_all()
    if args.latency:
        return measure(args.latency)
    if args.check:
        return check()
    return 0


if __name__ == "__main__":
    sys.exit(main())

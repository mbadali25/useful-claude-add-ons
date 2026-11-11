#!/usr/bin/env python3
"""crew orphan reaper: find hook and shell processes whose parent is gone and
that spin or hang, report them, and (only with --apply) end them.

Why: on one Windows host, hook and guard processes outlived the shell that
started them and ran for hours: a bash guard at 27,604 CPU-seconds, a
`python -` reading a program from stdin at 43,165 CPU-seconds, and 18 python
guards blocked 4.5 to 36.7 hours at zero CPU. Nothing cleaned them up.

The rule is deliberately conservative. A process is a CANDIDATE only when its
image is on the allow-list (bash, sh, python, python3, py, git, cygpath,
timeout, sleep, cat, tail, curl) or its command line names a crew hook script.
It is an ORPHAN only when its parent is gone (pid absent, or the pid was reused
by a younger process), or its parent chain is nothing but allow-listed shells
ending in a gone parent. An orphan is ended when
  (a) it is SPINNING (CPU over a short sample >= reaper.spinCpuPct of one
      core) and older than reaper.spinMinAgeMin minutes, or
  (b) it is BLOCKED (CPU under 1% of a core) and older than
      reaper.blockedMinAgeHours hours, or
  (c) its command line is a self-matching `until ! pgrep -f <pattern>`
      watcher (it matches its own command line, so it can never exit) and it
      is older than reaper.spinMinAgeMin minutes.
A process with a LIVE parent is never ended: it is reported with its owner
chain. A protected process (claude, node, MCP servers, ai-connect, psmux/tmux,
tailscale, language servers, obsidian, perplexity, vscode, wsl/docker/vm,
Defender, ssh, or anything matching reaper.protectedRegex) is never ended, and
neither is a process that has any live child that is not itself an orphan
candidate (a Teams window under a scope guard): that case is skipped, not
tree-killed.

Dry run is the default: nothing is ended without --apply (or, for scheduled
runs, reaper.dryRun false). Every decision is one JSON line in
~/.claude/crew/reaper.log (rotated at 1 MiB, three generations kept).

Scheduling is opt-in and never done by default: `--install-task` (Windows,
per-user, no admin) and `--print-schedule` (cron / systemd --user text). See
plugin/crew/CONFIG.md, "Orphan reaper".

Standard library only. Windows: one Get-CimInstance Win32_Process call per
snapshot (command line, creation time, CPU times; Toolhelp does not give them).
Linux and macOS: `ps`.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time

IS_WINDOWS = os.name == "nt"

ALLOW_IMAGES = frozenset({
    "bash", "sh", "python", "python3", "py", "pythonw", "git", "cygpath",
    "timeout", "sleep", "cat", "tail", "curl",
})
_PY_VERSIONED = re.compile(r"python3?\.\d+\Z")
SHELL_IMAGES = frozenset({"bash", "sh"})
# Console plumbing Windows gives every console process; it ends with its client, so it is neither
# a reason to skip a process nor something to end.
HELPER_IMAGES = frozenset({"conhost"})

# A command line naming one of these is a crew (or sibling plugin) hook process
# whatever its image is.
HOOK_SCRIPT_RE = re.compile(
    r"(?:^|[\\/\s\"'])(?:"
    r"cloud[-_]guard|env[-_]guard|scope[-_]guard|role[-_]write[-_]guard|"
    r"secrets[-_]guard|vault[-_]guard|promote[-_]gate|_promote_\w+|"
    r"approval[-_]hook|completion[-_]audit|crew_context|crew[-_]context|"
    r"crew_hook|crew[-_]hook|verify[-_]gate|context[-_]watch|codex-review"
    r")(?:\.py|\.sh|\.ps1)?(?=$|[\s\"'])", re.IGNORECASE)

# Protected: never ended, whatever the image. Matched against the image name and
# the scrubbed command line (a hook script's directory is cut to its basename
# first, so `.../.claude/plugins/.../obsidian-vault/vault_guard.py` is judged as
# `vault_guard.py`, not as an obsidian process).
DEFAULT_PROTECTED = (
    r"(?i)(?<![\w.-])(?:claude|node|nodejs|ms-teams|msedge|chrome|firefox|code|"
    r"obsidian|tailscaled?|psmux|pmux|tmux|ssh|sshd|ssh-agent|dockerd?|"
    r"wslhost|wsl|wslservice|vmmem|vmwp|msmpeng|nissrv)(?:\.exe)?(?![\w-])"
    r"|ai[-_]connect|mcp|language[-_ ]?server|\blsp\b|pyright|tsserver|gopls|"
    r"rust-analyzer|omnisharp|perplexity|vscode|docker|defender"
)

DEFAULTS = {
    "enabled": False,
    "dryRun": True,
    "spinCpuPct": 50,
    "spinMinAgeMin": 15,
    "blockedMinAgeHours": 2,
    "protectedRegex": None,
    "intervalMin": 10,
    "onSessionStart": False,
}
BLOCKED_CPU_PCT = 1.0
SAMPLE_SECONDS = 5.0
LOG_MAX_BYTES = 1024 * 1024
LOG_KEEP = 3
TASK_NAME = "CrewOrphanReaper"

_PGREP_RE = re.compile(r"pgrep\s+(?:-\w+\s+)*-f\s+(?:--\s+)?(?:'([^']*)'|\"([^\"]*)\"|(\S+))")
_WATCHER_RE = re.compile(r"\b(?:until|while)\b[^;|&]*\bpgrep\b")


# --------------------------------------------------------------------- config

def machine_config_path():
    return os.environ.get("CREW_REAPER_CONFIG") or os.path.join(
        os.path.expanduser("~"), ".claude", "crew", "config.json")


def log_path():
    return os.environ.get("CREW_REAPER_LOG") or os.path.join(
        os.path.expanduser("~"), ".claude", "crew", "reaper.log")


def _number(value, default, low=0.0):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return default
    return float(value) if value > low else default


def load_config(path=None):
    """The `reaper` block of the MACHINE config merged over DEFAULTS. A repo
    file is never read: this tool ends processes, so only the machine owner's
    file can arm it. A bad value reads as its default."""
    cfg = dict(DEFAULTS)
    try:
        with open(path or machine_config_path(), encoding="utf-8-sig") as fh:
            block = json.load(fh).get("reaper")
    except (OSError, ValueError, AttributeError):
        block = None
    if not isinstance(block, dict):
        return cfg
    for key in ("enabled", "onSessionStart"):
        if isinstance(block.get(key), bool):
            cfg[key] = block[key]
    if isinstance(block.get("dryRun"), bool):
        cfg["dryRun"] = block["dryRun"]
    cfg["spinCpuPct"] = _number(block.get("spinCpuPct"), DEFAULTS["spinCpuPct"])
    cfg["spinMinAgeMin"] = _number(block.get("spinMinAgeMin"), DEFAULTS["spinMinAgeMin"])
    cfg["blockedMinAgeHours"] = _number(block.get("blockedMinAgeHours"), DEFAULTS["blockedMinAgeHours"])
    cfg["intervalMin"] = int(_number(block.get("intervalMin"), DEFAULTS["intervalMin"], 0.999))
    regex = block.get("protectedRegex")
    if isinstance(regex, str) and regex.strip():
        try:
            re.compile(regex)
            cfg["protectedRegex"] = regex
        except re.error:
            cfg["protectedRegex"] = None
    return cfg


# ------------------------------------------------------------------ snapshots

def _norm_image(name):
    base = os.path.basename(str(name).replace("\\", "/")).lower()
    return base[:-4] if base.endswith(".exe") else base


def _parse_etime(text):
    """[[dd-]hh:]mm:ss -> seconds, or None."""
    try:
        days, _, rest = text.partition("-") if "-" in text else ("0", "", text)
        parts = [float(p) for p in rest.split(":")]
        total = 0.0
        for part in parts:
            total = total * 60 + part
        return total + float(days) * 86400
    except ValueError:
        return None


def snapshot_posix(now=None):
    """{pid: proc} from `ps`. proc keys: pid, ppid, name, cmd, age_s, cpu_s, start."""
    now = time.time() if now is None else now
    out = subprocess.run(["ps", "-axo", "pid=,ppid=,etime=,time=,comm=,args="],
                         capture_output=True, text=True, check=False, timeout=30,
                         stdin=subprocess.DEVNULL).stdout
    procs = {}
    for line in out.splitlines():
        parts = line.split(None, 5)
        if len(parts) < 5:
            continue
        try:
            pid, ppid = int(parts[0]), int(parts[1])
        except ValueError:
            continue
        age, cpu = _parse_etime(parts[2]), _parse_etime(parts[3])
        if age is None or cpu is None:
            continue
        procs[pid] = {"pid": pid, "ppid": ppid, "name": _norm_image(parts[4]),
                      "cmd": parts[5] if len(parts) > 5 else parts[4],
                      "age_s": age, "cpu_s": cpu, "start": now - age}
    return procs


_PS_SCRIPT = (
    "$ErrorActionPreference='Stop';"
    "Get-CimInstance Win32_Process | ForEach-Object {"
    "[pscustomobject]@{p=[int]$_.ProcessId;pp=[int]$_.ParentProcessId;n=$_.Name;c=$_.CommandLine;"
    "s=if($_.CreationDate){[int64](([datetimeoffset]$_.CreationDate).ToUnixTimeSeconds())}else{0};"
    "k=[int64]$_.KernelModeTime;u=[int64]$_.UserModeTime}} | ConvertTo-Json -Compress")


def _powershell():
    for name in ("pwsh", "powershell"):
        found = shutil.which(name)
        if found:
            return found
    root = os.environ.get("SystemRoot", r"C:\Windows")
    fallback = os.path.join(root, "System32", "WindowsPowerShell", "v1.0", "powershell.exe")
    return fallback if os.path.exists(fallback) else None


def snapshot_windows(now=None):
    """{pid: proc} from one Get-CimInstance Win32_Process call."""
    now = time.time() if now is None else now
    shell = _powershell()
    if not shell:
        raise OSError("no PowerShell found to read the process table")
    res = subprocess.run([shell, "-NoProfile", "-NonInteractive", "-Command", _PS_SCRIPT],
                         capture_output=True, text=True, check=False, timeout=60,
                         stdin=subprocess.DEVNULL, creationflags=0x08000000)
    if res.returncode != 0 or not res.stdout.strip():
        raise OSError("Get-CimInstance failed: " + (res.stderr or "").strip()[:300])
    rows = json.loads(res.stdout)
    if isinstance(rows, dict):
        rows = [rows]
    procs = {}
    for row in rows:
        start = float(row.get("s") or 0)
        procs[int(row["p"])] = {
            "pid": int(row["p"]), "ppid": int(row["pp"]), "name": _norm_image(row.get("n") or ""),
            "cmd": row.get("c") or "", "start": start,
            "age_s": (now - start) if start else 0.0,
            # 100 ns units
            "cpu_s": (int(row.get("k") or 0) + int(row.get("u") or 0)) / 1e7}
    return procs


def snapshot(now=None):
    return snapshot_windows(now) if IS_WINDOWS else snapshot_posix(now)


# ------------------------------------------------------------- classification

def image_allowed(proc):
    name = proc["name"]
    return (name in ALLOW_IMAGES or bool(_PY_VERSIONED.match(name))
            or bool(HOOK_SCRIPT_RE.search(proc["cmd"])))


def scrub(cmd):
    """The command line with each hook-script path cut to its basename, so a
    directory name inside a plugin cache path is not judged as a process."""
    def cut(match):
        token = match.group(0)
        base = re.split(r"[\\/]", token.strip("\"'"))[-1]
        return base if HOOK_SCRIPT_RE.search(" " + base) else token
    return re.sub(r"[^\s\"']*[\\/][^\s\"']+", cut, cmd)


def protected_re(cfg):
    return re.compile(cfg.get("protectedRegex") or DEFAULT_PROTECTED)


def is_protected(proc, rx):
    return bool(rx.search(proc["name"]) or rx.search(scrub(proc["cmd"])))


def parent_alive(proc, procs):
    """True when proc's parent pid is a process that started no later than proc
    (a younger process on the same pid is a reuse, not the parent)."""
    parent = procs.get(proc["ppid"])
    if parent is None or proc["ppid"] == proc["pid"]:
        return False
    if parent["start"] and proc["start"] and parent["start"] > proc["start"] + 2:
        return False
    return True


def owner_chain(proc, procs):
    """[(pid, name, alive)] from proc's parent upward (at most 12)."""
    chain, cur = [], proc
    for _ in range(12):
        if cur["ppid"] <= 0:
            break
        alive = parent_alive(cur, procs)
        parent = procs.get(cur["ppid"])
        chain.append((cur["ppid"], parent["name"] if parent else "?", alive))
        if not alive:
            break
        cur = parent
    return chain


def parent_state(proc, procs):
    """('dead'|'live'|'dead-shell-chain', chain). A parent chain of nothing but
    allow-listed shells that ends in a gone parent is a dead shell chain; any
    other live ancestor makes the process live."""
    chain = owner_chain(proc, procs)
    if not chain:
        return "dead", chain
    if not chain[0][2]:
        return "dead", chain
    for _pid, name, alive in chain:
        if not alive:
            return "dead-shell-chain", chain
        if name not in SHELL_IMAGES:
            return "live", chain
    return "live", chain


def self_matching_watcher(cmd):
    """True when cmd is an `until/while ... pgrep -f PATTERN` loop whose pattern
    matches cmd itself, so the loop's own shell keeps it true forever."""
    if not _WATCHER_RE.search(cmd):
        return False
    for match in _PGREP_RE.finditer(cmd):
        pattern = next((g for g in match.groups() if g), "")
        if not pattern:
            continue
        try:
            if re.search(pattern, cmd):
                return True
        except re.error:
            if pattern in cmd:
                return True
    return False


def cpu_pct(first, second, elapsed):
    if first is None or second is None or elapsed <= 0:
        return None
    return max(0.0, (second["cpu_s"] - first["cpu_s"]) / elapsed * 100.0)


def descendants(pid, procs):
    kids = {}
    for proc in procs.values():
        kids.setdefault(proc["ppid"], []).append(proc["pid"])
    out, stack = [], list(kids.get(pid, []))
    while stack:
        cur = stack.pop()
        if cur in out or cur == pid:
            continue
        out.append(cur)
        stack.extend(kids.get(cur, []))
    return out


def decide(proc, first, second, elapsed, procs, cfg, rx):
    """(decision, reason, extra) for one process in `procs`. Decisions:
    kill, skip (protected, protected child, still young), report (live parent),
    leave (orphan but under the limits). `first` is the earlier sample of proc."""
    state, chain = parent_state(proc, procs)
    pct = cpu_pct(first, second, elapsed)
    extra = {"parent": state, "chain": [f"{p}:{n}:{'live' if a else 'dead'}" for p, n, a in chain],
             "cpuPct": None if pct is None else round(pct, 1)}
    watcher = self_matching_watcher(proc["cmd"])
    extra["selfMatchingWatcher"] = watcher
    if is_protected(proc, rx):
        return ("ignore", "protected, live parent", extra) if state == "live" else ("skip", "protected", extra)
    age_min = proc["age_s"] / 60.0
    if state == "live":
        odd = watcher or (pct is not None and pct >= cfg["spinCpuPct"] and age_min >= cfg["spinMinAgeMin"])
        if odd:
            return "report", "live parent: never ended; owner chain shown", extra
        return "ignore", "live parent, nothing odd", extra
    kids = [procs[k] for k in descendants(proc["pid"], procs) if procs[k]["name"] not in HELPER_IMAGES]
    foreign = [k for k in kids if is_protected(k, rx) or not image_allowed(k)]
    if pct is None:
        return "leave", "could not tell: no CPU sample", extra
    spinning = pct >= cfg["spinCpuPct"] and age_min >= cfg["spinMinAgeMin"]
    blocked = pct < BLOCKED_CPU_PCT and age_min >= cfg["blockedMinAgeHours"] * 60.0
    stuck_watcher = watcher and age_min >= cfg["spinMinAgeMin"]
    if not (spinning or blocked or stuck_watcher):
        return "leave", "orphan but under the age or CPU limits", extra
    reason = ("spinning " + f"{pct:.0f}% of a core for {age_min:.0f} min" if spinning
              else "self-matching pgrep watcher, can never exit" if stuck_watcher
              else f"blocked (~0 CPU) for {age_min / 60:.1f} h")
    if foreign:
        extra["children"] = [f"{k['pid']}:{k['name']}" for k in foreign]
        return "skip", "has a protected or unlisted child (" + extra["children"][0] + "); not tree-killed", extra
    extra["tree"] = [k["pid"] for k in kids]
    return "kill", reason, extra


# -------------------------------------------------------------------- killing

def kill_pid(pid):
    """End one pid (no tree flag). True when the call succeeded."""
    if IS_WINDOWS:
        res = subprocess.run(["taskkill", "/PID", str(pid), "/F"], capture_output=True,
                             check=False, timeout=15, stdin=subprocess.DEVNULL,
                             creationflags=0x08000000)
        return res.returncode == 0
    import signal  # pylint: disable=import-outside-toplevel
    try:
        os.kill(pid, signal.SIGKILL)
        return True
    except OSError:
        return False


def same_process(proc, now_procs):
    """The pid still names the process we judged (same start time)."""
    cur = now_procs.get(proc["pid"])
    return bool(cur) and abs(cur["start"] - proc["start"]) <= 2


# ------------------------------------------------------------------------ log

def rotate(path, max_bytes=LOG_MAX_BYTES, keep=LOG_KEEP):
    try:
        if os.path.getsize(path) < max_bytes:
            return
    except OSError:
        return
    for i in range(keep - 1, 0, -1):
        older = f"{path}.{i}"
        if os.path.exists(older):
            os.replace(older, f"{path}.{i + 1}")
    os.replace(path, path + ".1")


def write_log(records, path=None):
    path = path or log_path()
    text = "".join(json.dumps(r, sort_keys=True) + "\n" for r in records)
    if not text:
        return
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        rotate(path)
        with open(path, "a", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
    except OSError as exc:
        sys.stderr.write(f"crew_reaper: could not write {path}: {exc}\n")


# ------------------------------------------------------------------------ run

def run(cfg, apply=False, sample_s=SAMPLE_SECONDS, snap=None, kill=None, sleeper=time.sleep,
        clock=time.time, pids=None):
    """One pass. Returns the list of decision records (also what is logged).
    `snap`, `kill`, `sleeper` and `clock` are seams for the tests. `pids`, when given, restricts
    the pass to those pids (`--pid`): the tests use it so they can never touch a real process."""
    snap = snap or snapshot
    kill = kill or kill_pid
    rx = protected_re(cfg)
    first = snap()
    t1 = clock()
    me = os.getpid()
    wanted = [p for p in first.values() if p["pid"] != me and image_allowed(p)
              and (pids is None or p["pid"] in pids)]
    if wanted:
        sleeper(sample_s)
    second = snap() if wanted else {}
    elapsed = max(clock() - t1, 0.001) if wanted else 0.0
    records = []
    for proc in sorted(wanted, key=lambda p: p["pid"]):
        cur = second.get(proc["pid"])
        if cur is None or abs(cur["start"] - proc["start"]) > 2:
            continue  # gone, or the pid was reused
        decision, reason, extra = decide(cur, proc, cur, elapsed, second, cfg, rx)
        if decision == "ignore":
            continue
        record = {"ts": int(clock()), "pid": cur["pid"], "image": cur["name"],
                  "ageS": int(cur["age_s"]), "cpuTotalS": round(cur["cpu_s"], 1),
                  "cmd": cur["cmd"][:200], "decision": decision, "reason": reason,
                  "applied": False, "dryRun": not apply}
        record.update(extra)
        if decision == "kill":
            record["decision"] = "kill" if apply else "would-kill"
            if apply:
                latest = snap()
                if not same_process(cur, latest):
                    record.update(decision="leave", reason="process changed before the kill")
                else:
                    ok = True
                    # children first, then the process; one pid at a time, no tree flag
                    for kid in extra.get("tree", []):
                        ok = kill(kid) and ok
                    ok = kill(cur["pid"]) and ok
                    record["applied"] = ok
                    if not ok:
                        record["reason"] += "; kill call failed"
        records.append(record)
    return records


# ------------------------------------------------------------------ scheduling

def task_command(script=None, python=None):
    """The schtasks argv that would install the per-user task (pure)."""
    script = os.path.abspath(script or __file__)
    python = python or sys.executable
    gui = os.path.join(os.path.dirname(python), "pythonw.exe")
    if os.path.exists(gui):
        python = gui
    cfg = load_config()
    run_cmd = f'"{python}" "{script}" --scheduled'
    return ["schtasks", "/Create", "/TN", TASK_NAME, "/SC", "MINUTE", "/MO",
            str(int(cfg["intervalMin"])), "/TR", run_cmd, "/F"]


def schedule_text(script=None):
    """cron and systemd --user text for Linux and macOS (never installed)."""
    script = os.path.abspath(script or __file__)
    interval = int(load_config()["intervalMin"])
    python = shutil.which("python3") or "python3"
    return (f"# crontab -e   (every {interval} minutes)\n"
            f"*/{interval} * * * * {python} {script} --scheduled\n\n"
            "# ~/.config/systemd/user/crew-reaper.service\n"
            "[Unit]\nDescription=crew orphan reaper\n[Service]\nType=oneshot\n"
            f"ExecStart={python} {script} --scheduled\n\n"
            "# ~/.config/systemd/user/crew-reaper.timer\n"
            f"[Unit]\nDescription=crew orphan reaper every {interval} min\n"
            f"[Timer]\nOnBootSec=5min\nOnUnitActiveSec={interval}min\n"
            "[Install]\nWantedBy=timers.target\n"
            "# then: systemctl --user enable --now crew-reaper.timer\n")


def maybe_spawn_for_session(cfg=None, marker=None, clock=time.time, popen=subprocess.Popen):
    """The SessionStart option: when reaper.enabled and reaper.onSessionStart
    are both true and the last run is older than intervalMin, start a detached
    scheduled pass and return at once. Never raises, never waits."""
    try:
        cfg = cfg or load_config()
        if not (cfg["enabled"] and cfg["onSessionStart"]):
            return False
        marker = marker or os.path.join(os.path.dirname(log_path()), "reaper.last")
        try:
            if clock() - os.path.getmtime(marker) < cfg["intervalMin"] * 60:
                return False
        except OSError:
            pass
        os.makedirs(os.path.dirname(marker), exist_ok=True)
        with open(marker, "w", encoding="utf-8") as fh:
            fh.write(str(int(clock())))
        flags = 0x00000008 | 0x00000200 | 0x08000000 if IS_WINDOWS else 0
        popen([sys.executable, os.path.abspath(__file__), "--scheduled"], stdin=subprocess.DEVNULL,
              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=True,
              creationflags=flags, **({} if IS_WINDOWS else {"start_new_session": True}))
        return True
    except (OSError, ValueError, KeyError):
        return False


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--apply", action="store_true",
                        help="really end the processes judged to be orphans")
    parser.add_argument("--scheduled", action="store_true",
                        help="a scheduled or session-start pass: needs reaper.enabled; "
                        "ends processes only if reaper.dryRun is false")
    parser.add_argument("--pid", type=int, action="append", help="only judge this pid (repeatable)")
    parser.add_argument("--json", action="store_true", help="print the decisions as JSON")
    parser.add_argument("--sample-seconds", type=float, default=SAMPLE_SECONDS)
    parser.add_argument("--print-schedule", action="store_true",
                        help="print cron and systemd --user text and exit")
    parser.add_argument("--install-task", action="store_true",
                        help="Windows: create the per-user scheduled task (needs --yes)")
    parser.add_argument("--uninstall-task", action="store_true",
                        help="Windows: remove the scheduled task (needs --yes)")
    parser.add_argument("--yes", action="store_true", help="confirm --install-task / --uninstall-task")
    args = parser.parse_args(argv)
    if args.print_schedule:
        print(schedule_text())
        return 0
    if args.install_task or args.uninstall_task:
        cmd = task_command() if args.install_task else ["schtasks", "/Delete", "/TN", TASK_NAME, "/F"]
        if not IS_WINDOWS:
            sys.stderr.write("crew_reaper: --install-task is Windows only; use --print-schedule\n")
            return 2
        if not args.yes:
            print("would run (add --yes to run it): " + subprocess.list2cmdline(cmd))
            return 0
        return subprocess.run(cmd, check=False).returncode
    cfg = load_config()
    if args.scheduled and not cfg["enabled"]:
        return 0
    apply = args.apply or (args.scheduled and not cfg["dryRun"])
    try:
        records = run(cfg, apply=apply, sample_s=args.sample_seconds,
                      pids=set(args.pid) if args.pid else None)
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        sys.stderr.write(f"crew_reaper: could not read the process table: {exc}\n")
        return 1
    write_log(records)
    if args.json:
        print(json.dumps(records, indent=2))
    else:
        for rec in records:
            print(f"{rec['decision']:10} pid {rec['pid']} {rec['image']} age {rec['ageS'] // 60} min "
                  f"cpu {rec['cpuPct']}% parent {rec['parent']}: {rec['reason']}")
        print(f"crew_reaper: {len(records)} candidate(s); {'applied' if apply else 'dry run, nothing ended'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

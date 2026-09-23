"""Gardener queue, bounded runner, backlog drain and scheduler units.

    queue       [--json] [--max N]                     pending items across every host's queue
    ack         --id ID --wrote PATH [...]             acknowledge ONE item, only after proof of a write
    garden-run  [--max N] [--processor JSON] [--commit] [--force-host]
    drain       [--batches K] [--apply]                the backlog in bounded batches; dry run first
    schedule    --os cron|systemd|windows [--time HH:MM] [--designate] [--apply]

Queue files. Capture writes `inbox/pending-reflect.<host>.md`, one per host,
so no two machines append to one synced file. The legacy single queue
`inbox/pending-reflect.md` is still read, so an old backlog drains. An item is
acknowledged by a line in `inbox/reflected.<host>.md` written by the host that
gardened it - every file here therefore has exactly one writer. A `- [x]`
check-off in the legacy file (the old gardener's way) also counts as done.

Bounds, enforced here rather than asked of a model:
  * at most MAX_ITEMS (5) items per run - --max may lower it, never raise it;
  * at most RUN_SECONDS (600) per run - each item's processor gets only what is
    left, and no item starts once it is spent;
  * an item is acknowledged only after its processor exited 0 AND every file it
    reported writing exists inside the vault, is non-empty, and is new or
    changed against a snapshot taken just before that item ran (a manual `ack`
    instead needs the file modified after the session was captured). Anything
    else leaves it queued for the next run;
  * one run at a time per vault (inbox/.garden.lock, stale after LOCK_STALE);
  * only on the designated host (config gardener.host), unless --force-host;
  * with --commit, only the files the run wrote and its own ack ledger are
    committed - `git commit -- <paths>`, never `git add -A` - and git, with
    the repository's own hooks, runs inside the same deadline.

An item whose transcript is not readable on this host is left queued and
reported as unresolved-here; it does not use up one of the five slots, or a
host that cannot read another host's transcripts would stall on them forever.
"""
import datetime
import glob
import hashlib
import json
import os
import re
import shlex
import shutil
import signal
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import obsidian_common  # noqa: E402  pylint: disable=wrong-import-position
import vault_setup  # noqa: E402  pylint: disable=wrong-import-position

EXIT_OK = 0
EXIT_PROBLEMS = 1
EXIT_USAGE = 2

MAX_ITEMS = 5
RUN_SECONDS = 600
LOCK_STALE = 900
WROTE_PREFIX = "GARDENER-WROTE:"
ITEM_RE = re.compile(r"^- \[( |x|X)\] (.*)$")
TS_RE = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2})")
LEDGER_ID_RE = re.compile(r"^- (\S+) \|")


# --- queue model ----------------------------------------------------------------

def _field(text, key):
    match = re.search(rf"(?:^|\| ){key}=([^|]*?)\s*(?:\||$)", text)
    return match.group(1).strip() if match else None


def item_id(text):
    sid = _field(text, "session")
    if sid and sid != "?":
        return sid
    return "line-" + hashlib.sha1(text.encode("utf-8")).hexdigest()[:12]


def queue_files(vault):
    inbox = os.path.join(vault, "inbox")
    files = sorted(glob.glob(os.path.join(inbox, "pending-reflect.*.md")))
    legacy = os.path.join(inbox, "pending-reflect.md")
    if os.path.isfile(legacy):
        files.append(legacy)
    return files


def ledger_path(vault):
    return os.path.join(vault, "inbox", f"reflected.{obsidian_common.host_id()}.md")


def acked_ids(vault):
    done = set()
    for path in glob.glob(os.path.join(vault, "inbox", "reflected.*.md")):
        try:
            with open(path, "r", encoding="utf-8") as fh:
                for line in fh:
                    match = LEDGER_ID_RE.match(line)
                    if match:
                        done.add(match.group(1))
        except OSError:
            continue
    return done


def read_queue(vault):
    """Every pending item, oldest first, de-duplicated by id across files."""
    done = acked_ids(vault)
    items, seen = [], set()
    for path in queue_files(vault):
        try:
            with open(path, "r", encoding="utf-8") as fh:
                lines = fh.read().splitlines()
        except OSError:
            continue
        for index, line in enumerate(lines):
            match = ITEM_RE.match(line)
            if not match:
                continue
            text = match.group(2)
            ident = item_id(text)
            if match.group(1) != " ":
                done.add(ident)
                continue
            if ident in seen:
                continue
            seen.add(ident)
            ts = TS_RE.match(text)
            items.append({"id": ident, "text": text, "file": os.path.relpath(path, vault),
                          "order": (ts.group(1) if ts else "9999", path, index),
                          "transcript": _field(text, "transcript"),
                          "cwd": _field(text, "cwd")})
    items = [i for i in items if i["id"] not in done]
    items.sort(key=lambda i: i["order"])
    for item in items:
        item.pop("order")
    return items


def transcript_readable(item):
    path = item.get("transcript")
    return bool(path and path != "?" and os.path.isfile(path) and os.access(path, os.R_OK))


# --- ack --------------------------------------------------------------------------

def _stat_key(full):
    try:
        st = os.stat(full)
    except OSError:
        return None
    return (st.st_mtime_ns, st.st_size)


def snapshot(vault):
    """{realpath: (mtime_ns, size)} for every file in the vault outside .git.

    Taken just before an item's processor runs, so that afterwards a file it
    reports can be checked against its own state from before - existing is not
    the same as having been written.
    """
    snap = {}
    for root, dirs, files in os.walk(vault):
        dirs[:] = [d for d in dirs if d != ".git"]
        for name in files:
            full = os.path.realpath(os.path.join(root, name))
            key = _stat_key(full)
            if key is not None:
                snap[full] = key
    return snap


def captured_at(item):
    """Epoch seconds of the item's capture stamp (local time, minute resolution), or None."""
    match = TS_RE.match(item.get("text") or "")
    if not match:
        return None
    try:
        return time.mktime(time.strptime(match.group(1), "%Y-%m-%d %H:%M"))
    except (ValueError, OverflowError):
        return None


def verify_writes(vault, wrote, before=None, since=None):
    """(ok, reason). Every path must be inside the vault, exist, be non-empty,
    and have been WRITTEN for this item.

    `before` (a snapshot() taken before the processor ran) proves a write: the
    file must be new, or its mtime/size must differ from the snapshot. Without
    a snapshot - a manual `ack` - `since` (the item's capture time) is the
    proof: a file last modified before the session was even captured cannot
    have been distilled from it. With neither, nothing proves the write and
    the ack is refused rather than assumed.
    """
    if not wrote:
        return False, "no written file reported - nothing proves the item was distilled"
    if before is None and since is None:
        return False, ("no before-state and no capture time - cannot tell whether "
                       "anything was written")
    root = os.path.normcase(os.path.realpath(vault))
    for rel in wrote:
        full = os.path.realpath(os.path.join(vault, rel))
        if not (os.path.normcase(full) + os.sep).startswith(root + os.sep):
            return False, f"{rel} is outside the vault"
        if not os.path.isfile(full):
            return False, f"{rel} does not exist"
        if os.path.getsize(full) == 0:
            return False, f"{rel} is empty"
        if before is not None:
            if full in before and before[full] == _stat_key(full):
                return False, f"{rel} is unchanged since before this item ran - not written by it"
        elif os.path.getmtime(full) < since:
            return False, (f"{rel} was last modified before this session was captured - "
                           "nothing proves it was written for this item")
    return True, None


def ack(vault, ident, wrote, today=None, before=None):
    """Append one ledger line for `ident`, but only when verify_writes passes."""
    item = next((i for i in read_queue(vault) if i["id"] == ident), None)
    if item is None:
        return False, f"{ident} is not a pending item"
    ok, reason = verify_writes(vault, wrote, before=before,
                               since=None if before is not None else captured_at(item))
    if not ok:
        return False, reason
    today = today or datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M")
    line = f"- {ident} | {today} | notes={', '.join(wrote)}\n"
    path = ledger_path(vault)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if not os.path.exists(path):
        line = ("# Reflected - gardener acknowledgements from this host\n\n"
                "One line per queue item distilled. Written only by vault_ops.py ack.\n\n"
                + line)
    with open(path, "a", encoding="utf-8", newline="\n") as fh:
        fh.write(line)
    return True, None


# --- lock ----------------------------------------------------------------------------

def lock_path(vault):
    return os.path.join(vault, "inbox", ".garden.lock")


def take_lock(vault, now=None):
    now = now or time.time()
    path = lock_path(vault)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    body = json.dumps({"pid": os.getpid(), "host": obsidian_common.host_id(), "at": now})
    for _ in range(2):
        try:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            try:
                age = now - os.path.getmtime(path)
            except OSError:
                continue
            if age > LOCK_STALE:
                os.remove(path)
                continue
            return False
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(body)
        return True
    return False


def release_lock(vault):
    try:
        os.remove(lock_path(vault))
    except OSError:
        pass


# --- processor -------------------------------------------------------------------------

PROMPT = """You are the obsidian-vault gardener, processing exactly ONE queued session.
Vault: {vault}
Queue item: {text}
Transcript: {transcript}

Follow the obsidian-vault:gardener agent's distillation rules and the vault's own
CLAUDE.md. Distil durable knowledge only; never invent a source, date or quote.
Always append a one-line digest for this session to today's daily note, so the
run leaves a written trace even when nothing else is worth keeping.
Do NOT edit anything under inbox/, and do NOT run git - the runner does both.
When done, print one line per file you created or modified, vault-relative:
{prefix} <path>
"""


def default_processor(vault, item):
    claude = shutil.which("claude") or "claude"
    argv = [claude, "-p", PROMPT.format(vault=vault, text=item["text"],
                                        transcript=item.get("transcript"), prefix=WROTE_PREFIX),
            "--permission-mode", "acceptEdits",
            "--allowedTools", "Read,Write,Edit,Grep,Glob",
            "--max-turns", "40"]
    if item.get("transcript") and item["transcript"] != "?":
        argv += ["--add-dir", os.path.dirname(item["transcript"])]
    return argv


def processor_argv(template, vault, item):
    if template is None:
        return default_processor(vault, item)
    return [part.replace("{item}", item["text"]).replace("{id}", item["id"])
            .replace("{vault}", vault).replace("{transcript}", item.get("transcript") or "")
            for part in template]


def run_processor(argv, vault, timeout):
    """(ok, wrote, detail)."""
    try:
        proc = subprocess.run(argv, cwd=vault, capture_output=True, text=True,
                              timeout=max(1, timeout), check=False)
    except subprocess.TimeoutExpired:
        return False, [], f"timed out after {int(timeout)}s"
    except OSError as exc:
        return False, [], f"could not start: {exc}"
    wrote = []
    for line in (proc.stdout or "").splitlines():
        line = line.strip()
        if line.startswith(WROTE_PREFIX):
            rel = line[len(WROTE_PREFIX):].strip().strip("`")
            if rel and rel not in wrote:
                wrote.append(rel)
    if proc.returncode != 0:
        return False, wrote, f"processor exited {proc.returncode}: {(proc.stderr or '').strip()[:300]}"
    return True, wrote, None


# --- run -------------------------------------------------------------------------------

def log_path():
    return os.path.join(os.path.dirname(obsidian_common.config_path()), "gardener.log")


def _log(line):
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    text = f"{stamp} {line}\n"
    try:
        os.makedirs(os.path.dirname(log_path()), exist_ok=True)
        with open(log_path(), "a", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
    except OSError:
        pass
    print(line)


def designated_host():
    gardener = obsidian_common.read_config().get("gardener")
    return gardener.get("host") if isinstance(gardener, dict) else None


def _run_bounded(argv, timeout):
    """(returncode, stdout, stderr), or (None, "", reason) when it could not finish.

    git runs the repository's own hooks, and a hook can take any time at all.
    The child gets its own process group so a timeout stops the hook's
    children too, not just git; SIGTERM first, so git can remove its
    index.lock on the way out, then SIGKILL.
    """
    if timeout <= 0:
        return None, "", "the run's time budget was already spent"
    posix = os.name == "posix"
    try:
        proc = subprocess.Popen(argv, stdout=subprocess.PIPE,  # pylint: disable=consider-using-with
                                stderr=subprocess.PIPE, text=True, start_new_session=posix)
    except OSError as exc:
        return None, "", f"could not start: {exc}"
    try:
        out, err = proc.communicate(timeout=timeout)
        return proc.returncode, out or "", err or ""
    except subprocess.TimeoutExpired:
        for sig in ((signal.SIGTERM, signal.SIGKILL) if posix else (None,)):
            try:
                if posix:
                    os.killpg(proc.pid, sig)
                else:
                    proc.kill()
            except OSError:
                pass
            try:
                proc.communicate(timeout=5)
                break
            except subprocess.TimeoutExpired:
                continue
        return None, "", f"timed out after {int(timeout)}s (the run's time bound)"


def commit_owned(vault, paths, deadline=None, clock=time.monotonic):
    """git add + commit ONLY `paths`, inside the run's deadline. (ok, detail).

    No-op without a .git. Repository hooks are not skipped (no --no-verify);
    they are bounded - a hook still running at the deadline is stopped and the
    commit reported as not made.
    """
    if not os.path.isdir(os.path.join(vault, ".git")):
        return True, "no .git in the vault - nothing committed"
    if not paths:
        return True, "nothing written - nothing committed"
    if deadline is None:
        deadline = clock() + RUN_SECONDS

    rc, _, err = _run_bounded(["git", "-C", vault, "add", "--"] + paths, deadline - clock())
    if rc is None:
        return False, f"git add not completed: {err} - nothing committed"
    if rc != 0:
        return False, f"git add failed: {err.strip()}"
    rc, out, err = _run_bounded(["git", "-C", vault, "commit", "-q", "-m",
                                 f"gardener: {len(paths)} file(s)", "--"] + paths,
                                deadline - clock())
    if rc is None:
        return False, f"git commit not completed: {err} - files are staged, not committed"
    if rc != 0:
        return False, f"git commit failed: {(err or out).strip()}"
    return True, f"committed {len(paths)} path(s)"


def garden_run(vault, max_items=MAX_ITEMS, processor=None, seconds=RUN_SECONDS,
               commit=False, clock=time.monotonic):
    """One bounded run. Returns a summary dict; never processes more than MAX_ITEMS."""
    max_items = max(0, min(int(max_items), MAX_ITEMS))
    deadline = clock() + min(seconds, RUN_SECONDS)
    summary = {"acked": [], "failed": [], "unresolved_here": [], "not_started": 0,
               "written": [], "commit": None}
    if not take_lock(vault):
        summary["locked"] = True
        return summary
    try:
        pending = read_queue(vault)
        runnable = []
        for item in pending:
            if transcript_readable(item):
                runnable.append(item)
            else:
                summary["unresolved_here"].append(item["id"])
        batch = runnable[:max_items]
        summary["not_started"] = len(runnable) - len(batch)
        for index, item in enumerate(batch):
            remaining = deadline - clock()
            if remaining <= 0:
                summary["not_started"] += len(batch) - index
                break
            before = snapshot(vault)
            ok, wrote, detail = run_processor(processor_argv(processor, vault, item),
                                              vault, remaining)
            if ok:
                ok, detail = ack(vault, item["id"], wrote, before=before)
            if ok:
                summary["acked"].append(item["id"])
                summary["written"].extend(w for w in wrote if w not in summary["written"])
                _log(f"acked {item['id']}: {', '.join(wrote)}")
            else:
                summary["failed"].append({"id": item["id"], "reason": detail})
                _log(f"left queued {item['id']}: {detail}")
        if commit and summary["acked"]:
            owned = summary["written"] + [os.path.relpath(ledger_path(vault), vault)]
            summary["commit"] = commit_owned(vault, owned, deadline, clock)
    finally:
        release_lock(vault)
    return summary


def _primary_or_fail():
    name, vault, problem = vault_setup.primary_vault()
    if not vault:
        print(problem or "no primary vault configured - run `adopt --role NAME=primary` first",
              file=sys.stderr)
    return name, vault


def cmd_queue(args, prober):  # pylint: disable=unused-argument
    _, vault = _primary_or_fail()
    if not vault:
        return EXIT_USAGE
    items = read_queue(vault)
    shown = items[:args.max] if args.max else items
    if args.json:
        print(json.dumps({"vault": vault, "pending": len(items), "items": shown}, indent=2))
    else:
        print(f"{len(items)} pending item(s) in {vault}")
        for item in shown:
            here = "" if transcript_readable(item) else "   [transcript not on this host]"
            print(f"  {item['id']}  {item['text'][:100]}{here}")
    return EXIT_OK


def cmd_ack(args, prober):  # pylint: disable=unused-argument
    _, vault = _primary_or_fail()
    if not vault:
        return EXIT_USAGE
    ok, reason = ack(vault, args.id, args.wrote or [])
    if not ok:
        print(f"not acknowledged, item stays queued: {reason}", file=sys.stderr)
        return EXIT_PROBLEMS
    print(f"acknowledged {args.id}")
    return EXIT_OK


def _host_ok(force):
    host = designated_host()
    here = obsidian_common.host_id()
    if force:
        return True
    if host is None:
        print("no gardener host designated (config gardener.host). Run "
              "`schedule --designate --apply` on the one host that should garden, "
              "or pass --force-host for an attended run.", file=sys.stderr)
        return False
    if host != here:
        print(f"this host is {here!r}; the designated gardener host is {host!r}. "
              "Nothing done.", file=sys.stderr)
        return False
    return True


def _print_summary(summary):
    if summary.get("locked"):
        print("another gardener run holds the lock - nothing done")
        return
    print(f"acked {len(summary['acked'])}, left queued {len(summary['failed'])}, "
          f"not started {summary['not_started']}, "
          f"unresolved on this host {len(summary['unresolved_here'])}")
    for fail in summary["failed"]:
        print(f"  left queued {fail['id']}: {fail['reason']}")
    if summary.get("commit"):
        print(f"  git: {summary['commit'][1]}")


def _processor_arg(raw):
    if raw is None:
        return None
    value = json.loads(raw)
    if not (isinstance(value, list) and value and all(isinstance(v, str) for v in value)):
        raise ValueError("--processor must be a JSON list of strings")
    return value


def cmd_garden_run(args, prober):  # pylint: disable=unused-argument
    if not _host_ok(args.force_host):
        return EXIT_PROBLEMS
    _, vault = _primary_or_fail()
    if not vault:
        return EXIT_USAGE
    try:
        processor = _processor_arg(args.processor)
    except ValueError as exc:
        print(exc, file=sys.stderr)
        return EXIT_USAGE
    summary = garden_run(vault, args.max, processor, commit=args.commit)
    if args.json:
        print(json.dumps(summary, indent=2))
    else:
        _print_summary(summary)
    return EXIT_PROBLEMS if summary.get("locked") or summary["failed"] else EXIT_OK


def cmd_drain(args, prober):  # pylint: disable=unused-argument
    _, vault = _primary_or_fail()
    if not vault:
        return EXIT_USAGE
    items = read_queue(vault)
    runnable = [i for i in items if transcript_readable(i)]
    batches_needed = -(-len(runnable) // MAX_ITEMS)
    print(f"backlog: {len(items)} pending, {len(runnable)} with a transcript readable here, "
          f"{len(items) - len(runnable)} unresolved on this host")
    print(f"at {MAX_ITEMS} per batch that is {batches_needed} batch(es); this run would "
          f"do {min(args.batches, batches_needed)}, each bounded to {MAX_ITEMS} items and "
          f"{RUN_SECONDS // 60} minutes")
    for item in runnable[:MAX_ITEMS]:
        print(f"  first batch: {item['id']}  {item['text'][:80]}")
    if not args.apply:
        print("\nDry run - nothing processed. Re-run with --apply.")
        return EXIT_PROBLEMS if runnable else EXIT_OK
    if not _host_ok(args.force_host):
        return EXIT_PROBLEMS
    try:
        processor = _processor_arg(args.processor)
    except ValueError as exc:
        print(exc, file=sys.stderr)
        return EXIT_USAGE
    failed = False
    for number in range(1, args.batches + 1):
        summary = garden_run(vault, MAX_ITEMS, processor, commit=args.commit)
        print(f"batch {number}:", end=" ")
        _print_summary(summary)
        failed = failed or bool(summary["failed"]) or bool(summary.get("locked"))
        if not summary["acked"]:
            break
    return EXIT_PROBLEMS if failed else EXIT_OK


# --- schedule ---------------------------------------------------------------------------

def run_command(python, script):
    return [python, script, "garden-run"]


def scheduler_path():
    """A PATH for the unit that can find `claude`.

    cron runs with PATH=/usr/bin:/bin and a systemd user unit with the
    manager's PATH; neither usually includes ~/.local/bin, where `claude`
    lives, so the processor would fail to start on every item and the whole
    queue would stay queued, nightly, with only the log saying why.
    """
    found = shutil.which("claude")
    base = "/usr/local/bin:/usr/bin:/bin"
    return f"{os.path.dirname(found)}:{base}" if found else base


def systemd_quote(value):
    """One systemd unit-file word: double-quoted, with `\\` `"` escaped, `$`
    doubled (no variable expansion) and `%` doubled (no specifier expansion)."""
    value = value.replace("\\", "\\\\").replace('"', '\\"')
    return '"' + value.replace("$", "$$").replace("%", "%%") + '"'


def ps_quote(value):
    """A PowerShell single-quoted literal: nothing inside is expanded; `'` doubles."""
    return "'" + value.replace("'", "''") + "'"


def unit_text(os_name, python, script, hhmm, log, path_env=None):
    """The unit, and the commands to install/verify/remove it, for one OS.

    Every path is quoted for the shell that will read it - shlex for cron's
    /bin/sh, systemd's own rules for a unit file, PowerShell literals (and
    Windows argv quoting inside -Argument) for Task Scheduler - so a path
    holding a quote, a space, `$(...)` or a backtick is passed through as
    text and never executed, neither at install time nor when the unit runs.
    """
    hour, minute = (int(x) for x in hhmm.split(":"))
    argv = run_command(python, script)
    path_env = path_env or scheduler_path()
    if os_name == "cron":
        command = (f"PATH={shlex.quote(path_env)} {shlex.join(argv)} "
                   f">> {shlex.quote(log)} 2>&1")
        # cron turns an unescaped % into a newline before the shell sees it.
        line = f"{minute} {hour} * * * " + command.replace("%", "\\%")
        return {"files": {}, "line": line,
                "install": [f"( crontab -l 2>/dev/null | grep -v 'vault_ops.py.*garden-run'; "
                            f"printf '%s\\n' {shlex.quote(line)} ) | crontab -"],
                "verify": ["crontab -l | grep garden-run", f"tail -n 20 {shlex.quote(log)}"],
                "remove": ["crontab -l | grep -v 'vault_ops.py.*garden-run' | crontab -"]}
    if os_name == "systemd":
        exec_start = " ".join(systemd_quote(a) for a in argv)
        service = ("[Unit]\nDescription=obsidian-vault gardener (bounded: 5 items / 10 min)\n\n"
                   f"[Service]\nType=oneshot\nEnvironment={systemd_quote('PATH=' + path_env)}\n"
                   f"ExecStart={exec_start}\n"
                   f"TimeoutStartSec={RUN_SECONDS + 120}\n")
        timer = ("[Unit]\nDescription=Daily obsidian-vault gardener\n\n"
                 f"[Timer]\nOnCalendar=*-*-* {hour:02d}:{minute:02d}:00\nPersistent=true\n\n"
                 "[Install]\nWantedBy=timers.target\n")
        unit_dir = "~/.config/systemd/user"
        return {"files": {f"{unit_dir}/obsidian-gardener.service": service,
                          f"{unit_dir}/obsidian-gardener.timer": timer},
                "install": ["systemctl --user daemon-reload",
                            "systemctl --user enable --now obsidian-gardener.timer"],
                "verify": ["systemctl --user list-timers obsidian-gardener.timer",
                           "journalctl --user -u obsidian-gardener.service -n 50"],
                "remove": ["systemctl --user disable --now obsidian-gardener.timer"]}
    exe, rest = argv[0], argv[1:]
    arg_text = subprocess.list2cmdline(rest)
    return {"files": {},
            "install": [
                f"$action = New-ScheduledTaskAction -Execute {ps_quote(exe)} "
                f"-Argument {ps_quote(arg_text)}",
                f"$trigger = New-ScheduledTaskTrigger -Daily -At '{hour:02d}:{minute:02d}'",
                "$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable "
                f"-ExecutionTimeLimit (New-TimeSpan -Minutes {RUN_SECONDS // 60 + 5})",
                "Register-ScheduledTask -TaskName 'Obsidian Gardener' -Action $action "
                "-Trigger $trigger -Settings $settings"],
            "verify": ["Get-ScheduledTask 'Obsidian Gardener' | Get-ScheduledTaskInfo",
                       f"Get-Content -Tail 20 {ps_quote(log)}"],
            "remove": ["Unregister-ScheduledTask -TaskName 'Obsidian Gardener' -Confirm:$false"]}


def cmd_schedule(args, prober):  # pylint: disable=unused-argument
    if not re.match(r"^\d{1,2}:\d{2}$", args.time) or int(args.time.split(":")[0]) > 23 \
            or int(args.time.split(":")[1]) > 59:
        print("--time is HH:MM, 24-hour", file=sys.stderr)
        return EXIT_USAGE
    python = args.python or sys.executable
    script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "vault_ops.py")
    unit = unit_text(args.os, python, script, args.time, log_path())
    here = obsidian_common.host_id()
    current = designated_host()
    print(f"Gardener schedule for {args.os}, daily at {args.time}, on host {here!r}.")
    print("NOTHING below is installed by this command. Run it yourself, once, on the "
          "designated host.\n")
    for path, text in unit.get("files", {}).items():
        print(f"--- write {path} ---\n{text}")
    if unit.get("line"):
        print(f"--- crontab line ---\n{unit['line']}\n")
    print("--- install ---")
    for cmd in unit["install"]:
        print(cmd)
    print("\n--- verify ---")
    for cmd in unit["verify"]:
        print(cmd)
    print("\n--- remove ---")
    for cmd in unit["remove"]:
        print(cmd)
    print(f"\nThe script path embeds the plugin version ({script}); re-run `schedule` "
          "after a plugin update.")
    if args.designate:
        if current == here:
            print(f"\ngardener.host is already {here!r}. Nothing to change.")
            return EXIT_OK
        print(f"\nPlanned config change: gardener.host {current!r} -> {here!r}")
        if not args.apply:
            print("Dry run. Re-run with --designate --apply to write it.")
            return EXIT_PROBLEMS
        config = obsidian_common.read_config()
        gardener = config.get("gardener") if isinstance(config.get("gardener"), dict) else {}
        gardener = dict(gardener, host=here)
        config["gardener"] = gardener
        obsidian_common.write_config(config)
        print(f"wrote gardener.host = {here!r}")
    elif current != here:
        print(f"\nThis host is not the designated gardener host (gardener.host = {current!r}); "
              "garden-run will refuse here until you pass --designate --apply.")
    return EXIT_OK


def add_parsers(sub):
    s = sub.add_parser("queue", help="pending gardener items across every host's queue")
    s.add_argument("--max", type=int)
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=cmd_queue)

    s = sub.add_parser("ack", help="acknowledge one item, only once its written notes exist")
    s.add_argument("--id", required=True)
    s.add_argument("--wrote", action="append", metavar="PATH",
                   help="vault-relative path written for this item (repeatable, required)")
    s.set_defaults(func=cmd_ack)

    for name, helptext in (("garden-run", "one bounded gardener run: <=5 items, <=10 minutes"),
                           ("drain", "work the backlog in bounded batches (dry run first)")):
        s = sub.add_parser(name, help=helptext)
        if name == "garden-run":
            s.add_argument("--max", type=int, default=MAX_ITEMS)
            s.add_argument("--json", action="store_true")
            s.set_defaults(func=cmd_garden_run)
        else:
            s.add_argument("--batches", type=int, default=1)
            s.add_argument("--apply", action="store_true")
            s.set_defaults(func=cmd_drain)
        s.add_argument("--processor", help="JSON argv list run per item instead of `claude -p`;"
                                           " {item} {id} {vault} {transcript} are substituted")
        s.add_argument("--commit", action="store_true",
                       help="commit only the files this run wrote, plus its ack ledger")
        s.add_argument("--force-host", action="store_true",
                       help="run even on a host that is not gardener.host (attended use)")

    s = sub.add_parser("schedule", help="print (never install) a daily gardener unit")
    s.add_argument("--os", required=True, choices=("cron", "systemd", "windows"))
    s.add_argument("--time", default="02:23")
    s.add_argument("--python", help="interpreter to put in the unit (default: this one)")
    s.add_argument("--designate", action="store_true",
                   help="also make THIS host the one gardener host (config gardener.host)")
    s.add_argument("--apply", action="store_true")
    s.set_defaults(func=cmd_schedule)

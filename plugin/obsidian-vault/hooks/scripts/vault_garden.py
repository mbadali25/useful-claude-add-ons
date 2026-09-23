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
    reported writing exists inside the vault and is non-empty. Anything else
    leaves it queued for the next run;
  * one run at a time per vault (inbox/.garden.lock, stale after LOCK_STALE);
  * only on the designated host (config gardener.host), unless --force-host;
  * with --commit, only the files the run wrote and its own ack ledger are
    committed - `git commit -- <paths>`, never `git add -A`.

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
import shutil
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

def verify_writes(vault, wrote):
    """(ok, reason). Every path must be inside the vault, exist, and be non-empty."""
    if not wrote:
        return False, "no written file reported - nothing proves the item was distilled"
    root = os.path.normcase(os.path.realpath(vault))
    for rel in wrote:
        full = os.path.realpath(os.path.join(vault, rel))
        if not (os.path.normcase(full) + os.sep).startswith(root + os.sep):
            return False, f"{rel} is outside the vault"
        if not os.path.isfile(full):
            return False, f"{rel} does not exist"
        if os.path.getsize(full) == 0:
            return False, f"{rel} is empty"
    return True, None


def ack(vault, ident, wrote, today=None):
    """Append one ledger line for `ident`, but only when verify_writes passes."""
    ok, reason = verify_writes(vault, wrote)
    if not ok:
        return False, reason
    pending = {i["id"] for i in read_queue(vault)}
    if ident not in pending:
        return False, f"{ident} is not a pending item"
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


def commit_owned(vault, paths):
    """git add + commit ONLY `paths`. (ok, detail). No-op without a .git."""
    if not os.path.isdir(os.path.join(vault, ".git")):
        return True, "no .git in the vault - nothing committed"
    if not paths:
        return True, "nothing written - nothing committed"
    add = subprocess.run(["git", "-C", vault, "add", "--"] + paths,
                         capture_output=True, text=True, check=False)
    if add.returncode != 0:
        return False, f"git add failed: {add.stderr.strip()}"
    commit = subprocess.run(["git", "-C", vault, "commit", "-q", "-m",
                             f"gardener: {len(paths)} file(s)", "--"] + paths,
                            capture_output=True, text=True, check=False)
    if commit.returncode != 0:
        return False, f"git commit failed: {(commit.stderr or commit.stdout).strip()}"
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
            ok, wrote, detail = run_processor(processor_argv(processor, vault, item),
                                              vault, remaining)
            if ok:
                ok, detail = ack(vault, item["id"], wrote)
            if ok:
                summary["acked"].append(item["id"])
                summary["written"].extend(w for w in wrote if w not in summary["written"])
                _log(f"acked {item['id']}: {', '.join(wrote)}")
            else:
                summary["failed"].append({"id": item["id"], "reason": detail})
                _log(f"left queued {item['id']}: {detail}")
        if commit and summary["acked"]:
            owned = summary["written"] + [os.path.relpath(ledger_path(vault), vault)]
            summary["commit"] = commit_owned(vault, owned)
    finally:
        release_lock(vault)
    return summary


def _primary_or_fail():
    name, vault = vault_setup.primary_vault()
    if not vault:
        print("no primary vault configured - run `adopt --role NAME=primary` first",
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


def unit_text(os_name, python, script, hhmm, log, path_env=None):
    hour, minute = (int(x) for x in hhmm.split(":"))
    argv = run_command(python, script)
    path_env = path_env or scheduler_path()
    if os_name == "cron":
        quoted = " ".join(f"'{a}'" for a in argv)
        line = f"{minute} {hour} * * * PATH='{path_env}' {quoted} >> '{log}' 2>&1"
        return {"files": {}, "line": line,
                "install": [f"( crontab -l 2>/dev/null | grep -v 'vault_ops.py.*garden-run'; "
                            f"echo \"{line}\" ) | crontab -"],
                "verify": ["crontab -l | grep garden-run", f"tail -n 20 '{log}'"],
                "remove": ["crontab -l | grep -v 'vault_ops.py.*garden-run' | crontab -"]}
    if os_name == "systemd":
        exec_start = " ".join(f'"{a}"' for a in argv)
        service = ("[Unit]\nDescription=obsidian-vault gardener (bounded: 5 items / 10 min)\n\n"
                   f"[Service]\nType=oneshot\nEnvironment=PATH={path_env}\n"
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
    arg_text = " ".join(f'"{a}"' for a in rest)
    return {"files": {},
            "install": [
                f"$action = New-ScheduledTaskAction -Execute '{exe}' -Argument '{arg_text}'",
                f"$trigger = New-ScheduledTaskTrigger -Daily -At '{hour:02d}:{minute:02d}'",
                "$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable "
                f"-ExecutionTimeLimit (New-TimeSpan -Minutes {RUN_SECONDS // 60 + 5})",
                "Register-ScheduledTask -TaskName 'Obsidian Gardener' -Action $action "
                "-Trigger $trigger -Settings $settings"],
            "verify": ["Get-ScheduledTask 'Obsidian Gardener' | Get-ScheduledTaskInfo",
                       f"Get-Content -Tail 20 '{log}'"],
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

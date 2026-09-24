"""Gardener queue, bounded runner, backlog drain and scheduler units.

    queue       [--json] [--max N]                     pending items across every host's queue
    ack         --id ID --wrote PATH [...]             acknowledge ONE item, only after proof of a write
    garden-run  [--max N] [--processor JSON] [--commit] [--force-host]
    drain       [--batches K] [--apply]                the backlog in bounded batches; dry run first
    reconcile   [--apply]                              ack items whose session page already exists
    schedule   --os cron|systemd|windows [--time HH:MM] [--designate] [--apply]

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
  * an item is acknowledged only after its processor exited 0 AND at least one
    file in the vault (outside dot-directories and inbox/) is new or changed in
    content between snapshots taken just before and just after it ran. What
    the processor REPORTS writing is logged as a hint and never decides the
    ack: a note can be moved by Obsidian before the processor exits. (A manual
    `ack` instead needs each named file modified after the session was
    captured.) Anything else leaves it queued, with the processor's bounded
    stdout and stderr in the reason;
  * an item whose session page already exists (`session_id:` in a page under
    wiki/sessions/) is acknowledged without running the processor again;
  * the processor runs with every hook off (`--settings {"disableAllHooks":
    true}`) and CREW_HOOKS=off / OBSIDIAN_VAULT_GARDENER=1 in its environment;
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
import threading
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

# Top-level directories a snapshot never enters, besides every dot-directory
# (.obsidian, .git, .trash, a stray .crew): `inbox/` is the queue and the ledger,
# which the runner writes itself.
SNAPSHOT_SKIP_TOP = ("inbox",)
# Bounds on one snapshot. A vault past MAX_SNAPSHOT_FILES is reported as
# incomplete and nothing is acknowledged on that partial picture. A file past
# HASH_MAX_BYTES is compared on mtime and size alone.
MAX_SNAPSHOT_FILES = 50000
HASH_MAX_BYTES = 4 * 1024 * 1024
# Where the vault contract files one page per session, carrying `session_id:`
# in its frontmatter. The dedupe guard and `reconcile` read these.
SESSIONS_DIR = "wiki/sessions"
SESSION_ID_RE = re.compile(r"""^session_id:\s*["']?([^"'\s]+)["']?\s*$""")


def _hash_file(full):
    digest = hashlib.sha1()
    with open(full, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 16), b""):
            digest.update(chunk)
    return digest.hexdigest()


def snapshot(vault, previous=None):
    """{"files": {relpath: (mtime_ns, size, sha1|None)}, "complete": bool, "detail": str|None}.

    Every file under the vault outside dot-directories and `inbox/`. Taken
    before and after an item's processor runs: what differs between the two is
    what that item wrote, whatever path the processor reported - a note it
    wrote may have been moved by Obsidian (auto-note-mover) before it exited.
    `previous` lets the second snapshot reuse a hash whose mtime and size did
    not move. Past MAX_SNAPSHOT_FILES the snapshot says it is incomplete rather
    than truncating quietly: an unknown must not read as "nothing changed".
    """
    files, prev = {}, (previous or {}).get("files", {})
    for root, dirs, names in os.walk(vault):
        rel_root = os.path.relpath(root, vault)
        dirs[:] = sorted(d for d in dirs if not d.startswith(".")
                         and not (rel_root == "." and d in SNAPSHOT_SKIP_TOP))
        for name in sorted(names):
            if len(files) >= MAX_SNAPSHOT_FILES:
                return {"files": files, "complete": False,
                        "detail": f"the vault holds more than {MAX_SNAPSHOT_FILES} files - "
                                  "too many to snapshot, so no write can be proven"}
            full = os.path.join(root, name)
            rel = os.path.normpath(os.path.join(rel_root, name)).replace(os.sep, "/")
            try:
                st = os.stat(full)
            except OSError:
                continue
            old = prev.get(rel)
            if old and old[0] == st.st_mtime_ns and old[1] == st.st_size:
                files[rel] = old
                continue
            digest = None
            if st.st_size <= HASH_MAX_BYTES:
                try:
                    digest = _hash_file(full)
                except OSError:
                    continue
            files[rel] = (st.st_mtime_ns, st.st_size, digest)
    return {"files": files, "complete": True, "detail": None}


def changed_files(before, after):
    """Vault-relative paths created, or whose content changed, between two snapshots.

    Touched-but-identical (same hash) is not a write, and neither is an empty
    file. A new path carrying exactly the content of a path that vanished is
    an existing note moved by someone else - not a write.
    """
    old, new = before["files"], after["files"]
    vanished = {key[2] for rel, key in old.items() if rel not in new and key[2]}
    out = []
    for rel, key in sorted(new.items()):
        if key[1] == 0:
            continue
        prior = old.get(rel)
        if prior is None:
            if key[2] is None or key[2] not in vanished:
                out.append(rel)
        elif prior[2] is not None and key[2] is not None:
            if prior[2] != key[2]:
                out.append(rel)
        elif prior[:2] != key[:2]:
            out.append(rel)
    return out


def _frontmatter_text(full):
    """The text between the opening and closing `---` markers, or None - no
    frontmatter, unreadable, or never closed. Best-effort: a decode error
    reads as no frontmatter rather than raising."""
    try:
        with open(full, "r", encoding="utf-8", errors="replace") as fh:
            lines = fh.read().splitlines()
    except OSError:
        return None
    if not lines or lines[0].strip() != "---":
        return None
    body = []
    for line in lines[1:]:
        if line.strip() == "---":
            return "\n".join(body)
        body.append(line)
    return None


def attributed_files(vault, written, ident):
    """The subset of `written` whose frontmatter carries `ident` - a
    `session_id:` field naming it, or `ident` appearing anywhere else in the
    frontmatter block (a `sources:` line naming its transcript, say).

    A changed file that never mentions the item proves nothing about it: an
    unrelated Obsidian sync, or another plugin, can touch a file in the same
    before/after window a processor ran in. Without this gate any such
    coincidence would ack (and, with --commit, commit) a file nobody wrote for
    this item. No frontmatter at all - a file with no opening `---`, or one
    never closed - counts as not attributed, the same as frontmatter that
    exists but never mentions `ident`.
    """
    out = []
    for rel in written:
        full = os.path.join(vault, *rel.split("/"))
        fm = _frontmatter_text(full)
        if fm and ident in fm:
            out.append(rel)
    return out


def session_notes(vault):
    """{session_id: [vault-relative session page, ...]} from wiki/sessions/, recursively.

    Reads frontmatter only. The gardener writes one session page per item it
    distils, so a page already carrying an item's id means the item was
    distilled - running the processor again would duplicate it.
    """
    index = {}
    base = os.path.join(vault, *SESSIONS_DIR.split("/"))
    for root, dirs, names in os.walk(base):
        dirs[:] = sorted(d for d in dirs if not d.startswith("."))
        for name in sorted(names):
            if not name.endswith(".md"):
                continue
            full = os.path.join(root, name)
            try:
                with open(full, "r", encoding="utf-8", errors="replace") as fh:
                    head = [fh.readline() for _ in range(80)]
            except OSError:
                continue
            if not head or head[0].strip() != "---":
                continue
            for line in head[1:]:
                if not line or line.strip() == "---":
                    break
                match = SESSION_ID_RE.match(line.rstrip("\r\n"))
                if match:
                    rel = os.path.relpath(full, vault).replace(os.sep, "/")
                    index.setdefault(match.group(1), []).append(rel)
                    break
    return index


def captured_at(item):
    """Epoch seconds of the item's capture stamp (local time, minute resolution), or None."""
    match = TS_RE.match(item.get("text") or "")
    if not match:
        return None
    try:
        return time.mktime(time.strptime(match.group(1), "%Y-%m-%d %H:%M"))
    except (ValueError, OverflowError):
        return None


def verify_writes(vault, wrote, since=None):
    """(ok, reason) for a MANUAL `ack`. Every path must be inside the vault,
    exist, be non-empty, and have been modified after `since` - the item's
    capture time: a file last modified before the session was even captured
    cannot have been distilled from it. Without `since` nothing proves the
    write, and the ack is refused rather than assumed.

    The runner does not use this. It acknowledges on a before/after snapshot
    of the vault (changed_files), never on the paths a processor reports.
    """
    if not wrote:
        return False, "no written file reported - nothing proves the item was distilled"
    if since is None:
        return False, "no capture time on the item - cannot tell whether anything was written"
    root = os.path.normcase(os.path.realpath(vault))
    for rel in wrote:
        full = os.path.realpath(os.path.join(vault, rel))
        if not (os.path.normcase(full) + os.sep).startswith(root + os.sep):
            return False, f"{rel} is outside the vault"
        if not os.path.isfile(full):
            return False, f"{rel} does not exist"
        if os.path.getsize(full) == 0:
            return False, f"{rel} is empty"
        if os.path.getmtime(full) < since:
            return False, (f"{rel} was last modified before this session was captured - "
                           "nothing proves it was written for this item")
    return True, None


def write_ledger(vault, ident, notes, how=None, today=None):
    """Append one ledger line for `ident`. The caller has already proven the write."""
    today = today or datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M")
    line = f"- {ident} | {today} | notes={', '.join(notes)}"
    line += f" | by={how}\n" if how else "\n"
    path = ledger_path(vault)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if not os.path.exists(path):
        line = ("# Reflected - gardener acknowledgements from this host\n\n"
                "One line per queue item distilled. Written only by vault_ops.py.\n\n"
                + line)
    with open(path, "a", encoding="utf-8", newline="\n") as fh:
        fh.write(line)


def ack(vault, ident, wrote, today=None):
    """Manual ack: one ledger line for `ident`, but only when verify_writes passes."""
    item = next((i for i in read_queue(vault) if i["id"] == ident), None)
    if item is None:
        return False, f"{ident} is not a pending item"
    ok, reason = verify_writes(vault, wrote, since=captured_at(item))
    if not ok:
        return False, reason
    write_ledger(vault, ident, wrote, today=today)
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
Every file this counts as YOUR work MUST carry this session's identity in its
frontmatter - at minimum the session page, with the literal line
`session_id: {ident}` in its frontmatter (quotes optional). A file that never
mentions {ident} in its frontmatter is not attributed to this item and will
never be acknowledged, however useful its content.
Do NOT edit anything under inbox/, and do NOT run git - the runner does both.
When done, print one line per file you created or modified, vault-relative:
{prefix} <path>
"""

# Every hook off for the processor's own session, by the documented mechanism:
# `--settings` JSON sits above user, project and local settings, and
# `disableAllHooks` there turns off user, project, local AND plugin hooks
# (managed hooks excepted). Without it, crew's SessionStart/Stop hooks ran
# inside the vault - one created `.crew/` there, the next session's
# platform-sync wrote a default `.crew/config.json` into it, a Stop hook
# injected a PM brief that replaced the processor's final GARDENER-WROTE lines
# and pushed another run past --max-turns - and this plugin's own capture hook
# queued each gardener session as new work.
HOOKS_OFF_SETTINGS = json.dumps({"disableAllHooks": True}, separators=(",", ":"))
# Set in the processor's environment whatever the processor is, so a hook that
# does run (a managed one, or a custom --processor) can recognise the
# gardener and stand down. `CREW_HOOKS=off` is for crew to honour; crew does
# not read it yet.
PROCESSOR_ENV = {"CREW_HOOKS": "off", "OBSIDIAN_VAULT_GARDENER": "1"}
# How much of each stream a failure reason and the run log keep.
STREAM_TAIL = 1500


def default_processor(vault, item):
    claude = shutil.which("claude") or "claude"
    argv = [claude, "-p", PROMPT.format(vault=vault, text=item["text"], ident=item["id"],
                                        transcript=item.get("transcript"), prefix=WROTE_PREFIX),
            "--settings", HOOKS_OFF_SETTINGS,
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


def processor_env():
    return dict(os.environ, **PROCESSOR_ENV)


def _tail(text):
    if isinstance(text, bytes):
        text = text.decode("utf-8", errors="replace")
    text = (text or "").strip()
    return text if len(text) <= STREAM_TAIL else "..." + text[-STREAM_TAIL:]


def _streams(stdout, stderr):
    """Both streams, bounded, for a reason or a log line. `claude -p` prints its
    own errors (max turns, for one) on STDOUT, so stderr alone can be empty."""
    parts = []
    for name, text in (("stderr", stderr), ("stdout", stdout)):
        tail = _tail(text)
        parts.append(f"{name}: {tail}" if tail else f"{name}: (empty)")
    return " | ".join(parts)


# How much of a stream is ever kept in memory while the processor runs. Only
# the last STREAM_TAIL *characters* are ever shown, but a runaway processor
# can print far more than that before it is stopped, and buffering all of it
# (as subprocess.run's capture_output does) holds every byte until exit. This
# is bytes, not characters, and comfortably above STREAM_TAIL so trimming
# never lands mid multi-byte sequence in a way `_tail` would notice.
STREAM_CAP_BYTES = 64 * 1024


class _BoundedStreamReader:
    """Reads one pipe in a background thread, keeping only its last
    STREAM_CAP_BYTES. Memory use is bounded by the cap, not by how much the
    child prints - trimmed in chunks rather than on every read so the common
    case (well under the cap) costs one append per chunk."""

    def __init__(self, stream):
        self._buf = bytearray()
        self._thread = threading.Thread(target=self._run, args=(stream,), daemon=True)
        self._thread.start()

    def _run(self, stream):
        try:
            for chunk in iter(lambda: stream.read(65536), b""):
                self._buf.extend(chunk)
                if len(self._buf) > STREAM_CAP_BYTES * 2:
                    del self._buf[:-STREAM_CAP_BYTES]
        except (OSError, ValueError):
            pass
        finally:
            try:
                stream.close()
            except OSError:
                pass

    def join(self, timeout=None):
        self._thread.join(timeout)

    def text(self):
        return bytes(self._buf[-STREAM_CAP_BYTES:]).decode("utf-8", errors="replace")


def run_processor(argv, vault, timeout):
    """(ok, reported, detail). `reported` is what the processor SAID it wrote -
    a hint for the log only; the ack decision is made on a vault snapshot.

    stdout and stderr are read by background threads into bounded buffers
    (_BoundedStreamReader) rather than accumulated whole, the way
    subprocess.run's capture_output does - a processor that prints without
    bound must not be able to grow this process's memory without bound.
    """
    try:
        proc = subprocess.Popen(argv, cwd=vault, stdout=subprocess.PIPE,  # pylint: disable=consider-using-with
                                stderr=subprocess.PIPE, env=processor_env())
    except OSError as exc:
        return False, [], f"could not start: {exc}"
    out_reader = _BoundedStreamReader(proc.stdout)
    err_reader = _BoundedStreamReader(proc.stderr)
    try:
        proc.wait(timeout=max(1, timeout))
    except subprocess.TimeoutExpired:
        proc.kill()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            pass
        out_reader.join(timeout=5)
        err_reader.join(timeout=5)
        return False, [], (f"timed out after {int(timeout)}s; "
                           + _streams(out_reader.text(), err_reader.text()))
    out_reader.join(timeout=5)
    err_reader.join(timeout=5)
    stdout_text = out_reader.text()
    reported = []
    for line in stdout_text.splitlines():
        line = line.strip()
        if line.startswith(WROTE_PREFIX):
            rel = line[len(WROTE_PREFIX):].strip().strip("`")
            if rel and rel not in reported:
                reported.append(rel)
    if proc.returncode != 0:
        return False, reported, (f"processor exited {proc.returncode}; "
                                 + _streams(stdout_text, err_reader.text()))
    return True, reported, None


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


def already_distilled(pending, index):
    """[(item, [session pages])] for pending items whose session page already exists."""
    return [(item, index[item["id"]]) for item in pending if item["id"] in index]


def _process_item(vault, item, processor, clock, deadline, before_snapshot=None):
    """(acked, written, detail, snapshot_after) for one item, decided on a
    before/after snapshot.

    `before_snapshot` is the previous item's after-snapshot (or None for the
    first item in a batch): passing it lets `snapshot()` reuse a hash for
    every file whose mtime and size have not moved, instead of re-hashing up
    to MAX_SNAPSHOT_FILES files again for each item in the batch. Taking the
    snapshot itself counts against `deadline` like everything else - if it
    alone spends what is left, the processor for this item never starts, and
    the item is left for the next run rather than given a shortened timeout
    with no way to tell it apart from a shortened run.
    """
    before = snapshot(vault, previous=before_snapshot)
    if not before["complete"]:
        return False, [], before["detail"], before
    remaining = deadline - clock()
    if remaining <= 0:
        return False, [], ("the run's time budget was spent snapshotting the vault before "
                           "this item's processor could start"), before
    ok, reported, detail = run_processor(processor_argv(processor, vault, item),
                                         vault, remaining)
    after = snapshot(vault, previous=before)
    if not after["complete"]:
        return False, [], after["detail"], after
    written = changed_files(before, after)
    unseen = [r for r in reported if r.replace("\\", "/") not in written]
    if unseen:
        _log(f"note {item['id']}: reported but not found changed: {', '.join(unseen)}")
    if not ok:
        if written:
            detail += f" (it changed {len(written)} file(s): {', '.join(written)})"
        return False, written, detail, after
    if not written:
        said = (f"; it reported {', '.join(reported)}, which is unchanged or absent"
                if reported else "; it reported nothing either")
        return False, [], ("no file in the vault was created or changed while it ran - "
                           "nothing proves the item was distilled" + said), after
    attributed = attributed_files(vault, written, item["id"])
    if not attributed:
        return False, [], (
            f"{len(written)} file(s) changed ({', '.join(written)}) but none carries this "
            f"item's identity ({item['id']!r} in frontmatter) - an unrelated vault change "
            "cannot acknowledge this item"), after
    write_ledger(vault, item["id"], written)
    return True, written, None, after


def garden_run(vault, max_items=MAX_ITEMS, processor=None, seconds=RUN_SECONDS,
               commit=False, clock=time.monotonic):
    """One bounded run. Returns a summary dict; never processes more than MAX_ITEMS.

    Before any processor starts, every pending item whose session page already
    exists is acknowledged instead of distilled again (`deduped`) - that costs
    no slot, since nothing runs for it.
    """
    max_items = max(0, min(int(max_items), MAX_ITEMS))
    deadline = clock() + min(seconds, RUN_SECONDS)
    summary = {"acked": [], "deduped": [], "failed": [], "unresolved_here": [],
               "not_started": 0, "written": [], "commit": None}
    if not take_lock(vault):
        summary["locked"] = True
        return summary
    try:
        pending = read_queue(vault)
        done = set()
        for item, pages in already_distilled(pending, session_notes(vault)):
            write_ledger(vault, item["id"], pages, how="dedupe")
            summary["deduped"].append(item["id"])
            done.add(item["id"])
            _log(f"acked {item['id']} without re-distilling: session page exists "
                 f"({', '.join(pages)})")
        runnable = []
        for item in pending:
            if item["id"] in done:
                continue
            if transcript_readable(item):
                runnable.append(item)
            else:
                summary["unresolved_here"].append(item["id"])
        batch = runnable[:max_items]
        summary["not_started"] = len(runnable) - len(batch)
        carry_snapshot = None
        for index, item in enumerate(batch):
            remaining = deadline - clock()
            if remaining <= 0:
                summary["not_started"] += len(batch) - index
                break
            ok, written, detail, carry_snapshot = _process_item(
                vault, item, processor, clock, deadline, carry_snapshot)
            if ok:
                summary["acked"].append(item["id"])
                summary["written"].extend(w for w in written if w not in summary["written"])
                _log(f"acked {item['id']}: {', '.join(written)}")
            else:
                summary["failed"].append({"id": item["id"], "reason": detail})
                _log(f"left queued {item['id']}: {detail}")
        if commit and (summary["acked"] or summary["deduped"]):
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
    print(f"acked {len(summary['acked'])}, "
          f"acked without re-distilling {len(summary.get('deduped', []))}, "
          f"left queued {len(summary['failed'])}, "
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
    distilled = {item["id"] for item, _ in already_distilled(items, session_notes(vault))}
    runnable = [i for i in items if transcript_readable(i) and i["id"] not in distilled]
    batches_needed = -(-len(runnable) // MAX_ITEMS)
    print(f"backlog: {len(items)} pending, {len(runnable)} with a transcript readable here, "
          f"{len(distilled)} already distilled (session page exists), "
          f"{len(items) - len(runnable) - len(distilled)} unresolved on this host")
    print(f"at {MAX_ITEMS} per batch that is {batches_needed} batch(es); this run would "
          f"do {min(args.batches, batches_needed)}, each bounded to {MAX_ITEMS} items and "
          f"{RUN_SECONDS // 60} minutes")
    if distilled:
        print(f"  the {len(distilled)} already distilled are acknowledged without "
              "re-distilling at the start of the first batch (`reconcile` lists them)")
    for item in runnable[:MAX_ITEMS]:
        print(f"  first batch: {item['id']}  {item['text'][:80]}")
    if not args.apply:
        print("\nDry run - nothing processed. Re-run with --apply.")
        return EXIT_PROBLEMS if runnable or distilled else EXIT_OK
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


def cmd_reconcile(args, prober):  # pylint: disable=unused-argument
    """Acknowledge queued items whose session page already exists. Dry run by default.

    For items a processor distilled that were never acknowledged - the runner
    checked a path the note no longer had, or the processor's final output lost
    its GARDENER-WROTE lines. The dry run reads and prints, and writes nothing.
    """
    _, vault = _primary_or_fail()
    if not vault:
        return EXIT_USAGE
    items = read_queue(vault)
    found = already_distilled(items, session_notes(vault))
    print(f"reconcile: {len(items)} pending in {vault}; {len(found)} already have a "
          f"session page in {SESSIONS_DIR}/")
    for item, pages in found:
        verb = "acking" if args.apply else "would ack"
        print(f"  {verb} {item['id']}  <- {', '.join(pages)}")
    if not found:
        print("Nothing to reconcile.")
        return EXIT_OK
    if not args.apply:
        print("\nDry run - nothing written. Re-run with --apply to append these to "
              f"{os.path.relpath(ledger_path(vault), vault)}.")
        return EXIT_PROBLEMS
    if not take_lock(vault):
        print("another gardener run holds the lock - nothing written", file=sys.stderr)
        return EXIT_PROBLEMS
    try:
        still = {i["id"] for i in read_queue(vault)}
        for item, pages in found:
            if item["id"] in still:
                write_ledger(vault, item["id"], pages, how="reconcile")
                _log(f"acked {item['id']} by reconcile: {', '.join(pages)}")
    finally:
        release_lock(vault)
    return EXIT_OK


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

    s = sub.add_parser("reconcile", help="acknowledge queued items whose session page already "
                                         "exists (dry run until --apply)")
    s.add_argument("--apply", action="store_true")
    s.set_defaults(func=cmd_reconcile)

    s = sub.add_parser("schedule", help="print (never install) a daily gardener unit")
    s.add_argument("--os", required=True, choices=("cron", "systemd", "windows"))
    s.add_argument("--time", default="02:23")
    s.add_argument("--python", help="interpreter to put in the unit (default: this one)")
    s.add_argument("--designate", action="store_true",
                   help="also make THIS host the one gardener host (config gardener.host)")
    s.add_argument("--apply", action="store_true")
    s.set_defaults(func=cmd_schedule)

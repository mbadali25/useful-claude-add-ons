"""One tracker interface for every lifecycle transition (T-0021).

    python3 crew_tracker.py resolve [--root .] [--json]
    python3 crew_tracker.py create  --ticket T-0042 --title "..." [--root .] [--json]
    python3 crew_tracker.py move    --ticket T-0042 --to spec [--root .] [--json]
    python3 crew_tracker.py read    --ticket T-0042 [--root .] [--json]

The lifecycle commands call this at their status transitions instead of each
restating, in prose, how a tracker is written. One line per backend is
printed; exit 0 updated/unchanged/not applicable, 1 could not update, 3
delegated (run the printed command), 2 usage.

## Which tracker

`resolve` reads BOTH config shapes: 1.0's `.crew/crew.json`
(`tracker: {"kind", "obsidian", "jira", "sdp"}`) and 0.20's
`.crew/config.json` (`tracker: "<kind>"`, the blocks at top level). When both
state a kind and the kinds differ, the answer is `could not tell`, naming both
files and both values -- never a pick. Picking either is the unknown that
collapses into a safe-looking value, and every write below refuses on it.

## Backends

- files: `.work/INDEX.md`, one row per ticket, `<id> | <status> | <risk> |
  <repo> | <title>`. `move` rewrites the status cell of the one row whose id
  cell matches exactly.
- obsidian: files, plus the Kanban board in the vault (below).
- jira, sdp: `delegated`, with the sync command to run. A script cannot call
  an MCP tool; the model running the lifecycle command can.

## Writes

Every write builds its full text first, writes a temp file beside the target,
re-reads the target, and only then `os.replace`s -- recomputing, at most
`WRITE_TRIES` times, when the target changed underneath it (another session
appending to INDEX.md, Obsidian saving the board). The temp is created
exclusively (`O_EXCL`), so a link planted at its name is never followed, and it
carries the target's mode and owner before it replaces it: sessions here run as
root, and a board handed to root 0644 is one Obsidian can no longer save. A failed tracker write never
undoes the lifecycle transition that called it: it prints `could not update:
<reason>` and exits 1, and the command's prose tells the human.
"""
import argparse
import datetime
import errno
import json
import ntpath
import os
import pathlib
import re
import secrets
import stat
import subprocess
import sys

KINDS = ("files", "obsidian", "jira", "sdp")
COULD_NOT_TELL = "could not tell"
NOT_CONFIGURED = "not configured"

UPDATED = "updated"
UNCHANGED = "unchanged"
FAILED = "could not update"
DELEGATED = "delegated"
NOT_APPLICABLE = "not applicable"
READ = "read"
UNREADABLE = "could not read"

# The ticket statuses a lifecycle command moves a ticket to, in order, and the
# `obsidian.columns` key of the lane each one lands in. Table-driven on
# purpose: a new status is a row here, not a branch in the code. A status
# absent from this table maps to no lane and is refused with nothing written.
STATUS_ORDER = ("direction", "ready", "spec", "planned", "in-progress", "review", "done")
LANE_FOR_STATUS = {
    "direction": "backlog",
    "ready": "backlog",
    "spec": "ready",
    "planned": "ready",
    "in-progress": "inProgress",
    "review": "review",
    "done": "done",
}
DEFAULT_COLUMNS = {
    "backlog": "Backlog",
    "ready": "Ready",
    "inProgress": "In Progress",
    "review": "Review",
    "done": "Done",
}
DEFAULT_BOARD = "Board.md"
WRITE_TRIES = 3
INDEX_REL = ".work/INDEX.md"

_TICKET_ID = re.compile(r"[A-Z][A-Z0-9]*-\d+\Z")
_SYNC = {"jira": "/crew:jira-sync", "sdp": "/crew:sdp-sync"}
_CREATE_DELEGATED = "create the tracker item through MCP, as brainstorm.md step 1 says"
_EXIT = {FAILED: 1, UNREADABLE: 1, DELEGATED: 3}


# --- resolve -----------------------------------------------------------------

def _load(root, name):
    """(dict or None, problem or None) for `.crew/<name>`; absent is (None, None)."""
    rel = f".crew/{name}"
    try:
        with open(os.path.join(root, ".crew", name), encoding="utf-8-sig") as handle:
            text = handle.read()
    except FileNotFoundError:
        return None, None
    except (OSError, ValueError) as exc:
        return None, f"{rel} unreadable ({exc})"
    try:
        data = json.loads(text)
    except ValueError:
        return None, f"{rel} is not valid JSON"
    if not isinstance(data, dict):
        return None, f"{rel} is not a JSON object"
    return data, None


def _side(name, data):
    """What one config file says: its kind, the key it said it under, its blocks."""
    rel = f".crew/{name}"
    memory = data.get("memory") if isinstance(data.get("memory"), dict) else {}
    if name == "crew.json":
        tracker = data.get("tracker")
        if tracker is None:
            return {"file": rel, "kind": None}
        if not isinstance(tracker, dict):
            return {"file": rel, "problem": f"{rel} tracker is not an object"}
        kind, key, holder = tracker.get("kind"), "tracker.kind", tracker
    else:
        kind, key, holder = data.get("tracker"), "tracker", data
    if kind is None:
        return {"file": rel, "kind": None}
    if kind not in KINDS:
        return {"file": rel, "problem": f"{rel} names tracker kind {kind!r}, which crew does not know"}
    blocks = {k: holder[k] for k in KINDS if isinstance(holder.get(k), dict)}
    return {"file": rel, "kind": kind, "key": key, "blocks": blocks, "memory": memory}


def _settings(kind, side):
    block = dict(side["blocks"].get(kind) or {})
    if kind != "obsidian":
        return block
    settings = {"vaultPath": None, "boardDir": None, "board": DEFAULT_BOARD}
    settings.update(block)
    columns = dict(DEFAULT_COLUMNS)
    if isinstance(block.get("columns"), dict):
        columns.update(block["columns"])
    settings["columns"] = columns
    if not settings.get("vaultPath") and side["memory"].get("vaultPath"):
        settings["vaultPath"] = side["memory"]["vaultPath"]
        settings["vaultPathFrom"] = "memory.vaultPath"
    return settings


def resolve(root):
    """`{"kind", "source", "settings", "problems"}` from both config shapes.

    kind is one of KINDS, `could not tell` or `not configured`; source is the
    config file's name the kind came from, or None.
    """
    problems, sides = [], []
    for name in ("crew.json", "config.json"):
        data, problem = _load(root, name)
        if problem:
            problems.append(problem)
        elif data is not None:
            side = _side(name, data)
            if "problem" in side:
                problems.append(side["problem"])
            elif side["kind"] is not None:
                sides.append(side)
    if len(sides) == 2:
        first, second = sides[0], sides[1]
        if first["kind"] != second["kind"]:
            problems.append(f"{first['file']} says {first['key']} {first['kind']!r}, "
                            f"{second['file']} says {second['key']} {second['kind']!r}")
        else:
            kind = first["kind"]
            if (kind in first["blocks"] and kind in second["blocks"]
                    and first["blocks"][kind] != second["blocks"][kind]):
                problems.append(f"{first['file']} and {second['file']} both say {kind!r} "
                                f"but disagree on its {kind} settings")
    if problems:
        return {"kind": COULD_NOT_TELL, "source": None, "settings": {}, "problems": problems}
    if not sides:
        return {"kind": NOT_CONFIGURED, "source": None, "settings": {}, "problems": []}
    side = sides[0]
    return {"kind": side["kind"], "source": os.path.basename(side["file"]),
            "settings": _settings(side["kind"], side), "problems": []}


# --- results -----------------------------------------------------------------

def _result(backend, state, reason=None, command=None, **extra):
    out = {"backend": backend, "state": state, "reason": reason, "command": command}
    out.update(extra)
    return out


def _report(info, results):
    return {"kind": info["kind"], "source": info["source"], "results": results}


def exit_code(report):
    """1 if any backend could not update, else 3 if any delegated, else 0."""
    codes = [_EXIT.get(r["state"], 0) for r in report["results"]]
    return 1 if 1 in codes else (3 if 3 in codes else 0)


def _gate(info):
    """A result that stops the call before anything is written, or None."""
    kind = info["kind"]
    if kind == COULD_NOT_TELL:
        return _result("tracker", FAILED, "tracker kind could not tell: " + "; ".join(info["problems"]))
    if kind == NOT_CONFIGURED:
        return _result("tracker", NOT_APPLICABLE,
                       "no tracker configured in .crew/crew.json or .crew/config.json")
    return None


# --- atomic replace ------------------------------------------------------------

def _read_bytes(path):
    """The file's bytes, or None when it does not exist."""
    try:
        with open(path, "rb") as handle:
            return handle.read()
    except FileNotFoundError:
        return None


def _discard(path):
    try:
        os.remove(path)
    except OSError:
        pass


# O_EXCL is the guard: with O_CREAT it refuses anything already at the name,
# a symlink included (dangling or not), so a link planted at a temp name is
# never followed. O_NOFOLLOW is belt and braces; O_BINARY stops Windows' CRT
# turning each LF into CRLF underneath `os.fdopen(fd, "wb")`.
_NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)
_BINARY = getattr(os, "O_BINARY", 0)
_TEMP_FLAGS = os.O_WRONLY | os.O_CREAT | os.O_EXCL | _NOFOLLOW | _BINARY


def _temp_name(name):
    return f".{name}.crew-{os.getpid()}-{secrets.token_hex(6)}.tmp"


def _is_root():
    return hasattr(os, "geteuid") and os.geteuid() == 0


def _ownership(path):
    """What a file written at `path` must carry: `(mode, uid, gid, replaces)`.

    An existing target's own mode and owner. A new file keeps the umask's mode
    and, only when running as root, takes its directory's owner -- a user who
    is not root cannot give a file away and creates it as themselves, which is
    what every other file they create does.
    """
    try:
        found = os.stat(path)
        return stat.S_IMODE(found.st_mode), found.st_uid, found.st_gid, True
    except FileNotFoundError:
        found = os.stat(os.path.dirname(path) or ".")
        return None, found.st_uid, found.st_gid, False


def _carry(fd, ownership):
    """Give the open file `ownership`'s owner, then its mode. A replacement
    that cannot keep the old owner is refused rather than handed to whoever
    ran crew; os.error's strerror carries why."""
    mode, uid, gid, replaces = ownership
    if hasattr(os, "fchown") and (replaces or _is_root()):
        now = os.fstat(fd)
        if (now.st_uid, now.st_gid) != (uid, gid):
            try:
                os.fchown(fd, uid, gid)
            except PermissionError as exc:
                raise OSError(exc.errno, f"cannot keep its owner {uid}:{gid} ({exc.strerror})") from exc
    if mode is not None and hasattr(os, "fchmod"):
        os.fchmod(fd, mode)


def _write_temp(path, data, ownership):
    """A new temp file beside `path` holding `data`, created exclusively."""
    folder, name = os.path.split(path)
    for _ in range(WRITE_TRIES):
        tmp = os.path.join(folder, _temp_name(name))
        try:
            fd = os.open(tmp, _TEMP_FLAGS, 0o666)
        except FileExistsError:
            continue
        try:
            with os.fdopen(fd, "wb") as handle:
                _carry(handle.fileno(), ownership)
                handle.write(data)
        except BaseException:
            _discard(tmp)
            raise
        return tmp
    raise OSError(errno.EEXIST, f"no free temp file name beside it after {WRITE_TRIES} tries")


def _atomic_update(path, label, backend, compute):
    """Replace `path` with `compute(old_bytes)`'s text, re-reading before replace.

    `compute` returns `(new_bytes or None, result)`; None means nothing to
    write and the result is returned as-is. When the file changed between
    the read and the replace, the temp is dropped and the text recomputed from
    the new bytes, at most WRITE_TRIES times.
    """
    for _ in range(WRITE_TRIES):
        try:
            before = _read_bytes(path)
            ownership = _ownership(path)
        except OSError as exc:
            return _result(backend, FAILED, f"{label}: {exc.strerror or exc}")
        new, result = compute(before)
        if new is None:
            return result
        tmp = None
        try:
            tmp = _write_temp(path, new, ownership)
            if _read_bytes(path) != before:
                _discard(tmp)
                continue
            os.replace(tmp, path)
        except OSError as exc:
            if tmp:
                _discard(tmp)
            return _result(backend, FAILED, f"{label}: {exc.strerror or exc}")
        return result
    return _result(backend, FAILED, f"{label} changed during write")


# --- files backend -------------------------------------------------------------

def _cells(line):
    body = line.strip()
    if "|" not in body:
        return []
    return [c.strip() for c in body.strip("|").split("|")]


def _rows(lines, ticket):
    return [i for i, line in enumerate(lines) if (_cells(line) or [None])[0] == ticket]


def _no_status_cell(ticket):
    return f"{INDEX_REL} row for {ticket} has no status cell"


def _set_status(line, status):
    """`line` with only its status cell's text replaced; padding and pipes kept.
    The caller has checked `_cells(line)` has a status cell."""
    body = line.rstrip("\r\n")
    ending = line[len(body):]
    parts = body.split("|")
    index = 2 if body.lstrip().startswith("|") else 1
    cell = parts[index]
    if cell.strip():
        lead = cell[:len(cell) - len(cell.lstrip())]
        trail = cell[len(cell.rstrip()):]
    else:
        lead, trail = cell, ""
    parts[index] = lead + status + trail
    return "|".join(parts) + ending


def _decode(data, label):
    if data is None:
        return "", None
    try:
        return data.decode("utf-8"), None
    except UnicodeDecodeError:
        return None, f"{label} is not UTF-8"


def repo_name(root):
    """The repository's name, the same in every worktree of it."""
    try:
        done = subprocess.run(["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
                              cwd=root, capture_output=True, text=True, check=False,
                              stdin=subprocess.DEVNULL, timeout=10)
        common = done.stdout.strip() if done.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        common = ""
    if common:
        common = os.path.normpath(common)
        if os.path.basename(common) == ".git":
            return os.path.basename(os.path.dirname(common))
        return os.path.basename(common)[:-4] if common.endswith(".git") else os.path.basename(common)
    return os.path.basename(os.path.realpath(root))


def title_ok(title):
    """A title fits one INDEX cell and one card line.

    One line by `str.splitlines`' own rule, which also splits on \x0b, \x0c,
    \x1c-\x1e, \x85, U+2028 and U+2029 -- every INDEX reader in crew splits
    that way, so a title holding one of them is two rows to them.
    """
    return bool(title) and "|" not in title and title.splitlines() == [title]


def _files_create(root, ticket, title):
    backend = "files"
    if not title_ok(title):
        return _result(backend, FAILED, "title must be one line with no '|'")
    row = f"{ticket} | direction | - | {repo_name(root)} | {title}\n"

    def compute(old):
        text, problem = _decode(old, INDEX_REL)
        if problem:
            return None, _result(backend, FAILED, problem)
        if _rows(text.splitlines(), ticket):
            return None, _result(backend, UNCHANGED, f"{INDEX_REL} already has {ticket}")
        if text and not text.endswith("\n"):
            text += "\n"
        return (text + row).encode("utf-8"), _result(backend, UPDATED, f"{INDEX_REL} row added")

    path = os.path.join(root, ".work", "INDEX.md")
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
    except OSError as exc:
        return _result(backend, FAILED, f".work: {exc.strerror or exc}")
    return _atomic_update(path, INDEX_REL, backend, compute)


def _files_move(root, ticket, status):
    backend = "files"

    def compute(old):
        text, problem = _decode(old, INDEX_REL)
        if problem:
            return None, _result(backend, FAILED, problem)
        lines = text.splitlines(keepends=True)
        found = _rows(lines, ticket)
        if not found:
            return None, _result(backend, FAILED, f"no {INDEX_REL} row for {ticket}")
        if len(found) > 1:
            return None, _result(backend, FAILED, f"{INDEX_REL} has {len(found)} rows for {ticket}")
        cells = _cells(lines[found[0]])
        if len(cells) < 2:
            return None, _result(backend, FAILED, _no_status_cell(ticket))
        current = cells[1]
        if current == status:
            return None, _result(backend, UNCHANGED, f"{INDEX_REL} already {status}")
        lines[found[0]] = _set_status(lines[found[0]], status)
        return "".join(lines).encode("utf-8"), _result(backend, UPDATED, f"{INDEX_REL} {current} -> {status}")

    return _atomic_update(os.path.join(root, ".work", "INDEX.md"), INDEX_REL, backend, compute)


def _files_read(root, ticket):
    try:
        raw = _read_bytes(os.path.join(root, ".work", "INDEX.md"))
    except OSError as exc:
        return _result("files", UNREADABLE, f"{INDEX_REL}: {exc.strerror or exc}")
    text, problem = _decode(raw, INDEX_REL)
    if problem:
        return _result("files", UNREADABLE, problem)
    found = _rows(text.splitlines(), ticket)
    if len(found) != 1:
        why = f"no {INDEX_REL} row for {ticket}" if not found else f"{len(found)} rows for {ticket}"
        return _result("files", UNREADABLE, why)
    cells = _cells(text.splitlines()[found[0]])
    if len(cells) < 2:
        return _result("files", UNREADABLE, _no_status_cell(ticket))
    return _result("files", READ, None, status=cells[1])


# --- the Kanban board ------------------------------------------------------------
#
# An Obsidian Kanban board is markdown the plugin round-trips, and three parts
# of it are load-bearing: `kanban-plugin: board` in the frontmatter, the
# trailing `%% kanban:settings` block, and `**Complete**` in the done lane. An
# archive is a `***` break followed by `## Archive`. A board that stops
# parsing opens as plain text in the human's window, so nothing here
# regenerates a board: it cuts one card's lines and inserts them elsewhere,
# and every other byte is the byte it read.

_HEADING = re.compile(r"## (.+?)[ \t]*\Z")
_KANBAN_KEY = re.compile(r"kanban-plugin:\s*['\"]?board['\"]?\s*\Z")
_CARD_START = re.compile(r"- ")
_CHECKED = re.compile(r"- \[[xX]\]")
_FIRST_ID = re.compile(r"\[\[([A-Z][A-Z0-9]*-\d+)(?:[|#][^\]]*)?\]\]"
                       r"|(?<![A-Za-z0-9-])([A-Z][A-Z0-9]*-\d+)(?![A-Za-z0-9])")
_COMPLETE = "**Complete**"


def _bare(line):
    return line.rstrip("\r\n")


def _board_lines(text):
    """The board's lines with their endings, split on LF alone.

    Not `str.splitlines`: it also splits on \x0b, \x0c, \x1c-\x1e, \x85,
    U+2028 and U+2029, which a Markdown editor keeps inside a line, so a card a
    human typed one of them into would be cut in two and moved by halves.
    """
    parts = text.split("\n")
    lines = [part + "\n" for part in parts[:-1]]
    return lines + [parts[-1]] if parts[-1] else lines


def _frontmatter_end(lines):
    """Index of the closing `---`, or a problem."""
    if not lines or _bare(lines[0]) != "---":
        return None, "not a Kanban board: no 'kanban-plugin: board' in its frontmatter"
    for index in range(1, len(lines)):
        if _bare(lines[index]) == "---":
            if any(_KANBAN_KEY.match(_bare(line)) for line in lines[1:index]):
                return index, None
            break
    return None, "not a Kanban board: no 'kanban-plugin: board' in its frontmatter"


def _region_end(lines, start):
    """(end of the lanes region, problem): the archive break or the settings block."""
    settings = next((i for i in range(start, len(lines))
                     if _bare(lines[i]).startswith("%% kanban:settings")), None)
    if settings is not None:
        close = next((i for i in range(settings + 1, len(lines)) if _bare(lines[i]) == "%%"), None)
        if close is None or any(_bare(line).strip() for line in lines[close + 1:]):
            return None, "the %% kanban:settings block is not the last thing on the board"
    end = len(lines) if settings is None else settings
    for index in range(start, end):
        if _bare(lines[index]).strip() == "***":
            following = next((_bare(line) for line in lines[index + 1:end] if _bare(line).strip()), "")
            if following == "## Archive":
                return index, None
    return end, None


def parse_board(text, columns):
    """`(board, None)` or `(None, problem)`. Never raises.

    The board is its lines (endings kept), the lanes above any archive break
    in order, and the configured lane names every lifecycle status needs.
    """
    lines = _board_lines(text)
    top, problem = _frontmatter_end(lines)
    if problem:
        return None, problem
    end, problem = _region_end(lines, top + 1)
    if problem:
        return None, problem
    headings = []
    for index in range(top + 1, end):
        found = _HEADING.match(_bare(lines[index]))
        if found:
            headings.append((found.group(1), index))
    lanes = []
    for position, (name, index) in enumerate(headings):
        stop = headings[position + 1][1] if position + 1 < len(headings) else end
        lanes.append({"name": name, "heading": index, "end": stop})
    for key in sorted(set(LANE_FOR_STATUS.values()), key=list(DEFAULT_COLUMNS).index):
        name = columns.get(key)
        count = sum(1 for lane in lanes if lane["name"] == name)
        if count == 0:
            return None, f"lane {name!r} (obsidian.columns.{key}) is not on the board"
        if count > 1:
            return None, f"lane {name!r} appears {count} times on the board"
    return {"lines": lines, "lanes": lanes, "columns": dict(columns)}, None


def _cards(board):
    """Every card above the archive: `{"start", "end", "lane", "id"}`."""
    lines, found = board["lines"], []
    for lane in board["lanes"]:
        index = lane["heading"] + 1
        while index < lane["end"]:
            if not _CARD_START.match(lines[index]):
                index += 1
                continue
            stop = index + 1
            while stop < lane["end"] and lines[stop][:1] in (" ", "\t") and _bare(lines[stop]).strip():
                stop += 1
            ident = _FIRST_ID.search(_bare(lines[index]))
            found.append({"start": index, "end": stop, "lane": lane["name"],
                          "id": (ident.group(1) or ident.group(2)) if ident else None})
            index = stop
    return found


def find_card(board, ticket):
    """`(card, None)` or `(None, problem)`. A card is the ticket's when the first
    id on its first line is the ticket's: `[[T-0009]] ... (depends on T-0005)` is
    T-0009's card, not a second T-0005 card."""
    matches = [card for card in _cards(board) if card["id"] == ticket]
    if not matches:
        return None, f"no card for {ticket} on the board"
    if len(matches) > 1:
        return None, (f"{len(matches)} cards for {ticket} on the board "
                      f"({', '.join(card['lane'] for card in matches)})")
    return matches[0], None


def _lane(board, key):
    name = board["columns"][key]
    return next(lane for lane in board["lanes"] if lane["name"] == name)


def _insertion(board, key):
    """Where a card becomes the first item of lane `key` (after `**Complete**` in done)."""
    lines, lane = board["lines"], _lane(board, key)
    anchor = lane["heading"]
    if key == "done":
        anchor = next((i for i in range(lane["heading"] + 1, lane["end"])
                       if _bare(lines[i]).strip() == _COMPLETE), anchor)
    for index in range(anchor + 1, lane["end"]):
        if _CARD_START.match(lines[index]):
            return index
    index = anchor + 1
    if index < lane["end"] and not _bare(lines[index]).strip():
        index += 1
    return index


def _ending(lines):
    return "\r\n" if lines and lines[0].endswith("\r\n") else "\n"


def _place(board, key, card_lines):
    """The board text with `card_lines` inserted as lane `key`'s first item."""
    lines = list(board["lines"])
    at = _insertion(board, key)
    if at > 0 and not lines[at - 1].endswith("\n"):
        lines[at - 1] += _ending(lines)
    lines[at:at] = card_lines
    return "".join(lines)


def move_card(board, ticket, key):
    """`(new_text, lane_it_was_in, None)` or `(None, None, problem)`."""
    card, problem = find_card(board, ticket)
    if problem:
        return None, None, problem
    target = board["columns"][key]
    lines = board["lines"]
    if card["lane"] == target:
        return "".join(lines), card["lane"], None
    moved = list(lines[card["start"]:card["end"]])
    ending = _ending(lines)
    moved = [line if line.endswith("\n") else line + ending for line in moved]
    first = moved[0]
    if key == "done" and first.startswith("- [ ]"):
        moved[0] = "- [x]" + first[5:]
    elif key != "done" and _CHECKED.match(first):
        moved[0] = "- [ ]" + first[5:]
    remaining = lines[:card["start"]] + lines[card["end"]:]
    rest, problem = parse_board("".join(remaining), board["columns"])
    if problem:
        return None, None, problem
    return _place(rest, key, moved), card["lane"], None


def add_card(board, ticket, title, key):
    """`(new_text, None)`: `- [ ] [[<id>]] <title>` first in lane `key`; unchanged
    when the ticket already has a card anywhere above the archive."""
    if any(card["id"] == ticket for card in _cards(board)):
        return "".join(board["lines"]), None
    return _place(board, key, [f"- [ ] [[{ticket}]] {title}{_ending(board['lines'])}"]), None


# --- the Obsidian backend --------------------------------------------------------
#
# The only crew code that writes outside the repository. Every path is
# resolved and confined before anything is written anywhere -- the INDEX half
# included -- so a refusal leaves the vault and the repo byte-identical. Once
# the checks pass, the INDEX half and the board half are written and reported
# separately, and a board write that fails does not roll the INDEX half back.

def _inside(parent, path):
    try:
        return os.path.commonpath([parent, path]) == parent
    except ValueError:
        return False


def _git_ignored(repo, path):
    """True/False from `git check-ignore`, None when git could not say."""
    try:
        done = subprocess.run(["git", "check-ignore", "-q", "--", path], cwd=repo,
                              capture_output=True, text=True, check=False,
                              stdin=subprocess.DEVNULL, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return None
    return {0: True, 1: False}.get(done.returncode)


def _vault_paths(root, settings, names):
    """`({"vault", "dir", <label>: real path}, None)` or `(None, problem)`.

    `names` is `[(label, file name)]`, each placed at `<vault>/<boardDir>/`.
    """
    raw = settings.get("vaultPath")
    if not raw or not isinstance(raw, str):
        return None, "obsidian.vaultPath is not set"
    vault = os.path.realpath(os.path.expanduser(raw))
    if not os.path.isdir(vault):
        return None, f"vault missing: {raw}"
    if not os.path.isdir(os.path.join(vault, ".obsidian")):
        return None, f"{raw} has no .obsidian/ - not an Obsidian vault"
    board_dir = settings.get("boardDir") or ""
    if not isinstance(board_dir, str):
        return None, "obsidian.boardDir must be a string"
    if os.path.isabs(board_dir) or ntpath.isabs(board_dir) or board_dir.startswith(("/", "\\")):
        return None, f"obsidian.boardDir {board_dir!r} must be relative to the vault"
    if ".." in re.split(r"[\\/]", board_dir):
        return None, f"obsidian.boardDir {board_dir!r} may not contain '..'"
    found = {"vault": vault, "dir": board_dir.replace("\\", "/").strip("/")}
    for label, name in names:
        if not isinstance(name, str):
            return None, f"obsidian.{label} {name!r} must be a bare file name"
        if not name or name in (".", "..") or any(sep in name for sep in "/\\"):
            return None, f"obsidian.{label} {name!r} must be a bare file name"
        shown = f"{found['dir']}/{name}" if found["dir"] else name
        real = os.path.realpath(os.path.join(vault, board_dir, name))
        if not _inside(vault, real):
            return None, f"{label} {shown} resolves outside the vault"
        if os.path.lexists(real) and not os.path.isfile(real):
            return None, f"{label} {shown} is not a regular file"
        found[label], found[label + "Shown"] = real, shown
    # Each file, not the vault: a vault that CONTAINS the repo, with boardDir
    # pointing into it, puts the board in the worktree while the vault is not.
    repo = os.path.realpath(root)
    for label, _ in names:
        if not _inside(repo, found[label]):
            continue
        ignored = _git_ignored(repo, found[label])
        if ignored is None:
            return None, f"could not tell whether git ignores {found[label + 'Shown']} in this worktree"
        if not ignored:
            return None, (f"{found[label + 'Shown']} is inside this worktree and git does not ignore "
                          f"it: the board would enter the review bundle")
    return found, None


def _load_board(paths, columns):
    """`(board, None)` or `(None, problem)` for the board at `paths["board"]`."""
    try:
        raw = _read_bytes(paths["board"])
    except OSError as exc:
        return None, f"{paths['boardShown']}: {exc.strerror or exc}"
    if raw is None:
        return None, f"no board at {paths['boardShown']}"
    text, problem = _decode(raw, paths["boardShown"])
    if problem:
        return None, problem
    return parse_board(text, columns)


def _board_write(paths, columns, edit):
    """Atomic board update: `edit(board) -> (text, result)`, recomputed per try."""
    def compute(old):
        text, problem = _decode(old, paths["boardShown"])
        board, problem = (None, problem) if problem else parse_board(text or "", columns)
        if problem:
            return None, _result("obsidian", FAILED, problem)
        new, result = edit(board)
        if new is None or new == text:
            return None, result
        return new.encode("utf-8"), result

    return _atomic_update(paths["board"], paths["boardShown"], "obsidian", compute)


def _note_text(root, ticket, title):
    folder = os.path.join(os.path.realpath(root), ".work", "tickets", ticket)
    return (f"---\ntitle: {json.dumps(title)}\ncreated: {datetime.date.today().isoformat()}\n---\n\n"
            f"# {ticket} {title}\n\n"
            f"- repo: {repo_name(root)}\n"
            f"- ticket: [.work/tickets/{ticket}/]({pathlib.Path(folder).as_uri()}/)\n")


def _create_note_once(paths, text):
    """The ticket note, written once and never rewritten. Exclusive create is the
    whole guard: the text is built before the open, and `x` refuses an existing
    note (or a dangling link) instead of truncating it. A note this call made
    and could not finish is removed, never left half-written."""
    data, created = text.encode("utf-8"), False
    try:
        ownership = _ownership(paths["note"])
        with open(paths["note"], "xb") as handle:
            created = True
            _carry(handle.fileno(), ownership)
            handle.write(data)
    except FileExistsError:
        return _result("obsidian-note", UNCHANGED, f"{paths['noteShown']} exists; never rewritten")
    except OSError as exc:
        if created:
            _discard(paths["note"])
        return _result("obsidian-note", FAILED, f"{paths['noteShown']}: {exc.strerror or exc}")
    return _result("obsidian-note", UPDATED, f"{paths['noteShown']} created")


# A card is `- [ ] [[T-0042]] <title>` and says nothing about which repo made
# it, and with boardDir unset every repo writes one `<vault>/Board.md`. The
# ticket note does say: `create` writes `- repo: <name>` into it. So the note is
# the card's owner, and a note naming another repo stops create, move and read.
# No note is `could not tell`, never "ours": create refuses on it (it is minting
# a new id, so a card already there is someone's), and move -- which must still
# work on a 0.20 board whose cards have no note -- says so on its line, after
# requiring this repo's own INDEX row for the ticket.
_NOTE_REPO = re.compile(r"^- repo: (.+?)[ \t]*$", re.M)


def _card_owner(paths):
    """`(repo name, None)` from the ticket note, or `(None, why it cannot be told)`."""
    try:
        raw = _read_bytes(paths["note"])
    except OSError as exc:
        return None, f"{paths['noteShown']}: {exc.strerror or exc}"
    if raw is None:
        return None, f"no {paths['noteShown']} note names its repo"
    text, problem = _decode(raw, paths["noteShown"])
    found = None if problem else _NOTE_REPO.search(text)
    return (found.group(1), None) if found else (None, problem or f"{paths['noteShown']} names no repo")


def _foreign(root, paths, ticket):
    """The problem when another repo owns `ticket` on this board, else None."""
    owner, _ = _card_owner(paths)
    here = repo_name(root)
    if owner is not None and owner != here:
        return (f"{ticket} on {paths['boardShown']} belongs to repo {owner!r} ({paths['noteShown']}), "
                f"not {here!r}: give this repo its own obsidian.boardDir")
    return None


def _obsidian_create(root, settings, ticket, title):
    columns = settings["columns"]
    paths, problem = _vault_paths(root, settings, [("board", settings["board"]), ("note", f"{ticket}.md")])
    board, problem = (None, problem) if problem else _load_board(paths, columns)
    if not problem:
        problem = _foreign(root, paths, ticket)
    if not problem and any(card["id"] == ticket for card in _cards(board)):
        owner, unknown = _card_owner(paths)
        if owner is None:
            problem = (f"{paths['boardShown']} already has a {ticket} card and could not tell whose: "
                       f"{unknown}")
    if problem:
        return [_result("obsidian", FAILED, problem)]
    files = _files_create(root, ticket, title)

    def edit(current):
        new, _ = add_card(current, ticket, title, LANE_FOR_STATUS["direction"])
        if new == "".join(current["lines"]):
            return None, _result("obsidian", UNCHANGED, f"{paths['boardShown']} already has {ticket}")
        return new, _result("obsidian", UPDATED, f"{paths['boardShown']} card added to {columns['backlog']}")

    return [files, _board_write(paths, columns, edit), _create_note_once(paths, _note_text(root, ticket, title))]


def _obsidian_move(root, settings, ticket, status):
    columns, key = settings["columns"], LANE_FOR_STATUS[status]
    paths, problem = _vault_paths(root, settings, [("board", settings["board"]), ("note", f"{ticket}.md")])
    if not problem and _files_read(root, ticket)["state"] != READ:
        problem = f"no {INDEX_REL} row for {ticket} in this repo"
    board, problem = (None, problem) if problem else _load_board(paths, columns)
    if not problem:
        _, _, problem = move_card(board, ticket, key)
    if not problem:
        problem = _foreign(root, paths, ticket)
    if problem:
        return [_result("obsidian", FAILED, problem)]
    _, unknown = _card_owner(paths)
    caveat = f" (whose card could not tell: {unknown})" if unknown else ""

    def edit(current):
        new, moved_from, why = move_card(current, ticket, key)
        if why:
            return None, _result("obsidian", FAILED, why)
        if moved_from == columns[key]:
            return None, _result("obsidian", UNCHANGED, f"{paths['boardShown']} already in {moved_from}{caveat}")
        return new, _result("obsidian", UPDATED, f"{paths['boardShown']} {moved_from} -> {columns[key]}{caveat}")

    return [_files_move(root, ticket, status), _board_write(paths, columns, edit)]


def _obsidian_read(root, settings, ticket):
    files = _files_read(root, ticket)
    paths, problem = _vault_paths(root, settings, [("board", settings["board"]), ("note", f"{ticket}.md")])
    board, problem = (None, problem) if problem else _load_board(paths, settings["columns"])
    card, problem = (None, problem) if problem else find_card(board, ticket)
    if not problem:
        problem = _foreign(root, paths, ticket)
    if problem:
        return [files, _result("obsidian", UNREADABLE, problem)]
    status = files.get("status")
    expected = settings["columns"].get(LANE_FOR_STATUS.get(status, ""), None)
    disagree = card["lane"] != expected
    _, unknown = _card_owner(paths)
    notes = [f"INDEX status {status} expects {expected}"] if disagree else []
    notes += [f"whose card could not tell: {unknown}"] if unknown else []
    return [files, _result("obsidian", READ, "; ".join(notes) or None, lane=card["lane"], disagree=disagree)]


# --- the interface -------------------------------------------------------------

def _delegated(kind, ticket, push):
    command = f"{_SYNC[kind]} {ticket}" + (" --push" if push else "")
    return _result(kind, DELEGATED, f"run {command}", command)


def create(root, ticket, title):
    """Mint the ticket in the tracker: the INDEX row, and for obsidian the card and note."""
    info = resolve(root)
    stop = _gate(info)
    if stop:
        return _report(info, [stop])
    kind = info["kind"]
    if kind in _SYNC:
        return _report(info, [_result(kind, DELEGATED, _CREATE_DELEGATED)])
    if not title_ok(title):
        return _report(info, [_result(kind, FAILED, "title must be one line with no '|'")])
    if kind == "obsidian":
        return _report(info, _obsidian_create(root, info["settings"], ticket, title))
    return _report(info, [_files_create(root, ticket, title)])


def move(root, ticket, status):
    """Move the ticket to `status` in every half of the configured tracker."""
    info = resolve(root)
    stop = _gate(info)
    if stop:
        return _report(info, [stop])
    kind = info["kind"]
    if status not in LANE_FOR_STATUS:
        return _report(info, [_result(kind, FAILED, f"status {status} maps to no lane")])
    if kind in _SYNC:
        return _report(info, [_delegated(kind, ticket, push=True)])
    if kind == "obsidian":
        return _report(info, _obsidian_move(root, info["settings"], ticket, status))
    return _report(info, [_files_move(root, ticket, status)])


def read(root, ticket):
    """The ticket's status in every half of the configured tracker."""
    info = resolve(root)
    kind = info["kind"]
    if kind == COULD_NOT_TELL:
        return _report(info, [_result("tracker", UNREADABLE, "tracker kind could not tell: "
                                      + "; ".join(info["problems"]))])
    if kind == NOT_CONFIGURED:
        return _report(info, [_gate(info)])
    if kind in _SYNC:
        return _report(info, [_delegated(kind, ticket, push=False)])
    if kind == "obsidian":
        return _report(info, _obsidian_read(root, info["settings"], ticket))
    return _report(info, [_files_read(root, ticket)])


# --- CLI -------------------------------------------------------------------------

def _line(result):
    if result["state"] == READ:
        extra = result.get("status") if "status" in result else result.get("lane")
        return f"{result['backend']}: {extra}" + (f" ({result['reason']})" if result["reason"] else "")
    text = f"{result['backend']}: {result['state']}"
    return text + (f": {result['reason']}" if result["reason"] else "")


def describe(info):
    """One human line for a resolve() answer."""
    if info["kind"] == COULD_NOT_TELL:
        return "could not tell - " + "; ".join(info["problems"])
    if info["kind"] == NOT_CONFIGURED:
        return "not configured (no tracker in .crew/crew.json or .crew/config.json)"
    return f"{info['kind']} (from .crew/{info['source']})"


def main(argv=None):
    parser = argparse.ArgumentParser(description="crew's one tracker interface")
    parser.add_argument("action", choices=("resolve", "create", "move", "read"))
    parser.add_argument("--root", default=".")
    parser.add_argument("--ticket")
    parser.add_argument("--title")
    parser.add_argument("--to", dest="status")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    root = os.path.abspath(args.root)
    if args.action == "resolve":
        info = resolve(root)
        print(json.dumps(info, indent=2, sort_keys=True) if args.json else "tracker " + describe(info))
        return 1 if info["kind"] == COULD_NOT_TELL else 0
    if not args.ticket or not _TICKET_ID.match(args.ticket):
        parser.error("--ticket must be a ticket id like T-0042")
    if args.action == "create":
        if not args.title:
            parser.error("create needs --title")
        report = create(root, args.ticket, args.title)
    elif args.action == "move":
        if not args.status:
            parser.error("move needs --to <status>")
        report = move(root, args.ticket, args.status)
    else:
        report = read(root, args.ticket)
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        for result in report["results"]:
            print(_line(result))
    return exit_code(report)


if __name__ == "__main__":
    sys.exit(main())

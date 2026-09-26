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
appending to INDEX.md, Obsidian saving the board). A failed tracker write never
undoes the lifecycle transition that called it: it prints `could not update:
<reason>` and exits 1, and the command's prose tells the human.
"""
import argparse
import json
import os
import re
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
STATUS_ORDER = ("direction", "spec", "planned", "in-progress", "review", "done")
LANE_FOR_STATUS = {
    "direction": "backlog",
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
        first, second = sides
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


def _atomic_update(path, label, backend, compute):
    """Replace `path` with `compute(old_bytes)`'s text, re-reading before replace.

    `compute` returns `(new_bytes or None, result)`; None means nothing to
    write and the result is returned as-is. When the file changed between
    the read and the replace, the temp is dropped and the text recomputed from
    the new bytes, at most WRITE_TRIES times.
    """
    folder, name = os.path.split(path)
    tmp = os.path.join(folder, f".{name}.crew-{os.getpid()}.tmp")
    for _ in range(WRITE_TRIES):
        before = _read_bytes(path)
        new, result = compute(before)
        if new is None:
            return result
        try:
            with open(tmp, "wb") as handle:
                handle.write(new)
            if _read_bytes(path) != before:
                _discard(tmp)
                continue
            os.replace(tmp, path)
        except OSError as exc:
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


def _set_status(line, status):
    """`line` with only its status cell's text replaced; padding and pipes kept."""
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


def _files_create(root, ticket, title):
    backend = "files"
    if not title or any(ch in title for ch in "|\r\n"):
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
    os.makedirs(os.path.dirname(path), exist_ok=True)
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
        current = _cells(lines[found[0]])[1] if len(_cells(lines[found[0]])) > 1 else ""
        if current == status:
            return None, _result(backend, UNCHANGED, f"{INDEX_REL} already {status}")
        lines[found[0]] = _set_status(lines[found[0]], status)
        return "".join(lines).encode("utf-8"), _result(backend, UPDATED, f"{INDEX_REL} {current} -> {status}")

    return _atomic_update(os.path.join(root, ".work", "INDEX.md"), INDEX_REL, backend, compute)


def _files_read(root, ticket):
    text, problem = _decode(_read_bytes(os.path.join(root, ".work", "INDEX.md")), INDEX_REL)
    if problem:
        return _result("files", UNREADABLE, problem)
    found = _rows(text.splitlines(), ticket)
    if len(found) != 1:
        why = f"no {INDEX_REL} row for {ticket}" if not found else f"{len(found)} rows for {ticket}"
        return _result("files", UNREADABLE, why)
    cells = _cells(text.splitlines()[found[0]])
    return _result("files", READ, None, status=cells[1] if len(cells) > 1 else "")


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
    if kind == "obsidian":
        return _report(info, [_result("obsidian", FAILED, "obsidian backend not built yet")])
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
        return _report(info, [_result("obsidian", FAILED, "obsidian backend not built yet")])
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

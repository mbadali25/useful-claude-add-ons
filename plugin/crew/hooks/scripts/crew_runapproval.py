"""Owner-typed run approvals: one request, one receipt, one use (crew 1.3.161).

A few commands are the owner's alone (today: the verify trust store's
`approve`, `revoke`, `allow-owner`, `disallow-owner`). Until now the only way
to run one was a person at a terminal. This module is the route an agent can
USE and cannot COMPLETE: the agent's refused command becomes a REQUEST, the
owner's own typed prompt `/crew:allow-run <id>` turns that request into a
RECEIPT, and the agent's re-run spends it. Harness: listed in `HARNESS`
(`scripts/check-tooling-pr.py`), because it decides what the guards release.

    request   scope_guard.py, on refusing a plain `verify_trust.py <verb>`:
              records the exact command text and prints the id. Records nothing
              unless the class is on (`approvals.run.classes`, machine file).
    receipt   approval_hook.py, UserPromptSubmit only, from the owner's typed
              `/crew:allow-run <id>`: one use, `approvals.run.ttlSeconds` (900).
    spend     verify_trust.py `--receipt <id>`: atomic, first use ends it.

WHAT A RECEIPT IS BOUND TO. The sha256 of the exact command text; the class;
the action the command parses to (verb, real `--root` or owner, `--under`);
the worktree the session stood in; the session that raised the request; and,
for `approve`, the digest of what the gate would run (`verify_trust.digest`,
the `.crew/verify.json` bytes), read when the request is raised, again when
the owner types the id, and again at the spend: a map edited after the request
ends the approval. A receipt is spent by its first use, matching or not.

DEFAULT OFF. Nothing here acts unless the machine file
`~/.claude/crew/config.json` holds `approvals.run.classes` naming the class.
Only the machine layer counts (a repo file is a checkout anyone can hand you),
only a file that parses with no duplicate key, and could-not-tell is OFF. With
the class off no request is recorded, `/crew:allow-run` mints nothing and
`--receipt` spends nothing: the guards behave as before.

UNKNOWN IS A REFUSAL. Every reader answers "refused" for anything it cannot
read, parse or match. An unanswered request is never an allow; it expires.

WHAT THIS IS NOT (README "Scope and approval"). The stores are files of the
same OS user the session runs as. While a class is on, and only then,
`scope_guard.py` refuses a command that names the store, in full or through a
glob or an unexpanded variable beside it (`run-*`, `run-appro[v]als`,
`${d}-approvals`), carries the owner's command text, names the prompt hook or
starts Claude on an existing session, and refuses a Write/Edit under the
store: a tripwire that stops drift. A check that raises refuses the call.
With no class on none of this is judged (`store_refusal`), so a receipt file
written by hand then is held back by nothing but what it must name: this
session's id, the worktree, the command's sha and a window an hour wide at
most, which its writer may date for any day. A session that sets out to forge
a receipt by a route the tripwire does not read (a whole path held in a
variable set by an earlier command, an encoded or concatenated string, a
script file) is not stopped here, and neither is one that types into the
owner's own terminal.
The binding to the requesting session stops a prompt submitted in ANOTHER
session, which is what a plain child `claude -p "/crew:allow-run <id>"` is.
It does NOT stop a child that RESUMES this session: measured on claude
2.1.326, the prompt hook of `claude -p --resume <sid>` (prompt as an argument
or on stdin) is handed <sid>. Only the tripwire stands in front of that.
"""
import hashlib
import json
import os
import re
import secrets
import time
import uuid

VERSION = 1
COMMAND = "crew:allow-run"
CLASS_TRUST = "verify-trust"
CLASSES = (CLASS_TRUST,)
TRUST_VERBS = ("approve", "revoke", "allow-owner", "disallow-owner")
DEFAULT_TRUST_VERBS = ("approve",)
DEFAULT_TTL = 900
MIN_TTL, MAX_TTL = 60, 3600
REQUEST_TTL = 900
MAX_PENDING = 20
USER_PROMPT = "user-prompt"
STORE_NAME = "run-approvals"
CONFIG = os.path.join(".claude", "crew", "config.json")
TRUST_SCRIPT = "verify_trust.py"

# Each of these four is asked through `_whole` (a fullmatch) and never through
# `.match` with a `$`: `$` also matches BEFORE a trailing newline, so
# `ar-0123456789ab\n` read as an id and `x\n` as a plain word.
_ID_RE = re.compile(r"ar-[0-9a-f]{12}")
_OWNER_RE = re.compile(r"[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?/[a-z0-9_][a-z0-9_.-]*")
_PYTHON_RE = re.compile(r"(?:python[0-9.]*|py)(?:\.exe)?", re.IGNORECASE)
# One plain literal word: nothing a shell expands, quotes, escapes or splits.
_PLAIN_RE = re.compile(r"[A-Za-z0-9_./:=,@%+-]+")
_STORE_NAME_RE = re.compile(r"run[-_]approvals", re.IGNORECASE)
_MODULE_RE = re.compile(r"crew[-_]runapproval", re.IGNORECASE)
# The owner's command WITH something that can stand for an id after it: a
# literal id, or a character a shell expands. A commit message or a grep that
# merely mentions `/crew:allow-run <id>` carries neither and passes.
_OWNER_COMMAND_RE = re.compile(r"crew:allow[-_]run(?=[\s\S]*(?:\bar-[0-9a-f]{12}\b|[$`%]))",
                               re.IGNORECASE)
# An interpreter standing as a command word (never the `.py` of a file name), or an import.
_RUNS_CODE_RE = re.compile(r"(?:^|[\s;&|(/\\])(?:python[0-9.]*|pypy[0-9.]*|py)(?:\.exe)?\s"
                           r"|\b(?:import|runpy)\b", re.IGNORECASE)
_PROMPT_HOOK_RE = re.compile(r"approval[_-]hook|crew[_-]hook(?:\.py|\.sh|\.ps1)?\b", re.IGNORECASE)
_QUOTE_RE = re.compile(r"[\"'\\`^]")
# What a shell replaces before the command runs, so the text does not say what
# the word will be: a variable, a substitution, a brace list, an extended glob.
_EXPANSION_RE = re.compile(r"\$\{[^}]*\}|\$\([^)]*\)|`[^`]*`|[?*+@!]\([^)]*\)|\{[^{}]*\}"
                           r"|\$(?:env:)?[A-Za-z_][A-Za-z0-9_]*|%[A-Za-z_][A-Za-z0-9_]*%|\$")
_WORD_SPLIT_RE = re.compile(r"[\s;&|<>()\"'=]+")
_ANY = "\x00"
_GLOB_RE = re.compile(r"[~*?\[\]]")
_STORE_PARENT = (".claude", "crew")
_STORE_CHILDREN = ("receipts", "requests", "audit.log")
_CREW_DIR_RE = re.compile(r"\.claude[/\\]+crew(?![\w.-])", re.IGNORECASE)
# Claude started as a command, and the flags that put its prompt in a session
# that already exists (measured, claude 2.1.326: the prompt hook of
# `claude -p --resume <sid>` is handed <sid> itself).
_CLAUDE_RE = re.compile(r"(?:^|[\s;&|(/\\])claude(?:-code)?(?:\.exe|\.cmd|\.bat|\.ps1)?(?=\s|$)",
                        re.IGNORECASE)
_RESUME_RE = re.compile(r"(?:^|\s)(?:--(?:resume|continue|session-id|fork-session|from-pr|teleport)"
                        r"|-[A-Za-z]*[rc][A-Za-z]*)(?=[\s=]|$)")
_UNREAD_RE = re.compile(r"[$`]|%[A-Za-z_][A-Za-z0-9_]*%")
_UNPRINTABLE_RE = re.compile(r"[\x00-\x1f\x7f-\x9f]")


class Refused(Exception):
    """Nothing was recorded, minted or spent; the text says why."""


# ------------------------------------------------------------------ settings

def _no_duplicate_keys(pairs):
    seen = {}
    for key, value in pairs:
        if key in seen:
            raise ValueError(f"duplicate key {key!r}")
        seen[key] = value
    return seen


def _inside(path, folder):
    path = os.path.normcase(os.path.realpath(path))
    folder = os.path.normcase(os.path.realpath(folder))
    return path == folder or path.startswith(folder.rstrip(os.sep) + os.sep)


def _machine_path(tail, root, anywhere=False):
    """`~/<tail>`, or None when that path lies inside the project `root` or the
    working directory: a HOME pointed at a directory a repo ships is not the
    machine's, so nothing there is read as the owner's. `anywhere` skips that
    test, for the one reader that only ever ADDS a refusal (`store_refusal`)."""
    path = os.path.join(os.path.expanduser("~"), tail)
    if not os.path.isabs(path):
        return None
    for folder in () if anywhere else (root, os.getcwd()):
        if folder and _inside(path, folder):
            return None
    return path


def settings(root=None, anywhere=False):
    """`{"classes", "ttl", "verbs"}` from the MACHINE config file alone. Never
    raises: a file that is missing, unreadable, not an object, or holds a
    duplicate key is "off" (no class). A `classes` that is not a list of
    strings is off; a name this version does not know is ignored. An invalid
    `ttlSeconds` or `verbs.verifyTrust` reads as its default."""
    off = {"classes": frozenset(), "ttl": DEFAULT_TTL, "verbs": DEFAULT_TRUST_VERBS}
    try:
        path = _machine_path(CONFIG, root, anywhere)
        if path is None:
            return off
        with open(path, encoding="utf-8-sig") as handle:
            parsed = json.load(handle, object_pairs_hook=_no_duplicate_keys)
    except (OSError, ValueError, RecursionError):  # RecursionError: a file nested too deep
        return off
    run = parsed.get("approvals") if isinstance(parsed, dict) else None
    run = run.get("run") if isinstance(run, dict) else None
    if not isinstance(run, dict):
        return off
    classes = run.get("classes")
    if not isinstance(classes, list) or not all(isinstance(c, str) for c in classes):
        return off
    ttl = run.get("ttlSeconds")
    if isinstance(ttl, bool) or not isinstance(ttl, int) or not MIN_TTL <= ttl <= MAX_TTL:
        ttl = DEFAULT_TTL
    verbs = run.get("verbs")
    verbs = verbs.get("verifyTrust") if isinstance(verbs, dict) else None
    if not isinstance(verbs, list) or not all(v in TRUST_VERBS for v in verbs):
        verbs = DEFAULT_TRUST_VERBS
    return {"classes": frozenset(c for c in classes if c in CLASSES), "ttl": ttl,
            "verbs": tuple(verbs)}


# --------------------------------------------------------------------- store

def store_dir(root=None):
    """The store directory, `~/.claude/crew/run-approvals`. Raises Refused when
    that path would lie inside the project (`_machine_path`)."""
    path = _machine_path(os.path.join(".claude", "crew", STORE_NAME), root)
    if path is None:
        raise Refused("the run-approval store would lie inside the project; a repo cannot "
                      "ship its own approvals")
    return path


def _file(root, kind, ident):
    if not valid_id(ident):
        raise Refused(f"{_clean(ident, 40)!r} is not a request id (an id looks like "
                      "ar-1a2b3c4d5e6f)")
    return os.path.join(store_dir(root), kind, ident + ".json")


def _whole(pattern, text):
    """True when `pattern` covers ALL of `text`, a trailing newline included."""
    return pattern.fullmatch(text) is not None


def valid_id(ident):
    return isinstance(ident, str) and _whole(_ID_RE, ident)


def _write(path, data):
    # The payload is built before anything is opened; a failed write costs the
    # temp file, never a record already there.
    text = json.dumps(data, indent=2, sort_keys=True) + "\n"
    os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
    tmp = f"{path}.{os.getpid()}.{uuid.uuid4().hex}.tmp"
    with open(tmp, "x", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
    os.replace(tmp, path)


def _read(path):
    """The JSON object at `path`, or None when it is absent, unreadable, not a
    regular file or not an object. Never a guess."""
    try:
        if os.path.islink(path) or not os.path.isfile(path):
            return None
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle, object_pairs_hook=_no_duplicate_keys)
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _claim(path):
    """Take `path` for this process alone (an atomic rename) and return its
    content, deleting it whatever it holds. None when there was nothing to
    take: of two takers exactly one gets the record."""
    claimed = f"{path}.claim-{os.getpid()}-{uuid.uuid4().hex}"
    try:
        os.rename(path, claimed)
    except OSError:
        return None
    try:
        return _read(claimed)
    finally:
        try:
            os.remove(claimed)
        except OSError:
            pass


def _clean(value, limit=300):
    text = _UNPRINTABLE_RE.sub("?", " ".join(str(value).split()))
    return text if len(text) <= limit else text[:limit - 3] + "..."


def _number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def audit(root, event, record, why=""):
    """One line per request, mint, spend and refused spend, appended to
    `<store>/audit.log`. Best effort: the log is evidence, never a gate."""
    try:
        line = json.dumps({"at": int(time.time()), "event": event, "id": record.get("id"),
                           "class": record.get("class"), "command": record.get("command"),
                           "worktree": record.get("worktree"),
                           "session_id": record.get("session_id"),
                           "prompt_id": record.get("prompt_id"), "why": why}, sort_keys=True)
        directory = store_dir(root)
        os.makedirs(directory, mode=0o700, exist_ok=True)
        with open(os.path.join(directory, "audit.log"), "a", encoding="utf-8",
                  newline="\n") as handle:
            handle.write(line + "\n")
    except (OSError, Refused, TypeError, ValueError):
        pass


# -------------------------------------------------------------------- binding

def command_sha(command):
    return hashlib.sha256(command.encode("utf-8", "surrogatepass")).hexdigest()


def _canon(path, cwd=None):
    joined = path if os.path.isabs(path) else os.path.join(cwd or os.getcwd(), path)
    return os.path.normcase(os.path.realpath(joined))


def worktree_of(cwd):
    """The worktree a session stands in: git's top level, else the real
    directory. One function for the guard, the hook and the tool."""
    import crew_ticket  # pylint: disable=import-outside-toplevel
    top = crew_ticket.toplevel(cwd)
    return os.path.normcase(top) if top else _canon(cwd)


def trust_action(verb, root=None, owner=None, under=(), cwd=None):
    """What a trust command DOES, in one canonical form, built the same way from
    the command text (the guard) and from the parsed arguments (the tool)."""
    if verb in ("approve", "revoke"):
        return {"verb": verb, "root": _canon(root or ".", cwd)}
    action = {"verb": verb, "owner": (owner or "").strip().lower()}
    if verb == "allow-owner":
        action["under"] = [_canon(d, cwd) for d in under]
    return action


def trust_pin(action):
    """The digest of what the gate would run at `action["root"]`, for `approve`
    alone; None for the other verbs. Raises Refused when it cannot be read or
    there is nothing to approve: an approval of unknown bytes is no approval."""
    if action.get("verb") != "approve":
        return None
    import verify_trust  # pylint: disable=import-outside-toplevel
    try:
        current, _targets = verify_trust.digest(action["root"])
    except verify_trust.TrustError as exc:
        raise Refused(f"could not read what the gate would run ({_clean(exc)})") from exc
    if current is None:
        raise Refused("there is nothing to approve there: no .crew/verify.json and no smoke "
                      "script")
    return current


def parse_trust_command(command, cwd, scripts):
    """`(action, receipt_id, base)` when `command` is the ONE plain form a
    receipt may cover, else None:

        <python> [-B] <path>/verify_trust.py approve|revoke [--root DIR] [--receipt ID]
        <python> [-B] <path>/verify_trust.py allow-owner HOST/OWNER [--under DIR]... [--receipt ID]
        <python> [-B] <path>/verify_trust.py disallow-owner HOST/OWNER [--receipt ID]

    one line (a command holding a line feed or a carriage return anywhere,
    its end included, is never this form: a shell runs each line), every word
    a plain literal (no quote, variable, substitution, redirect, pipe or
    separator), the script being THIS plugin's own
    `verify_trust.py`, `--receipt` last. `base` is the text without the
    trailing ` --receipt ID`: the request is recorded for it, so the first run
    and the re-run name the same command. Anything else is not requestable."""
    if not isinstance(command, str) or not isinstance(cwd, str):
        return None
    if "\n" in command or "\r" in command:
        return None
    text = command.strip()
    words = text.split(" ")
    if any(not _whole(_PLAIN_RE, word) for word in words):
        return None
    receipt = None
    if len(words) >= 2 and words[-2] == "--receipt":
        receipt = words[-1]
        if not valid_id(receipt):
            return None
        base = text[:-len(" --receipt " + receipt)]
        words = words[:-2]
    else:
        base = text
    if not words or not _whole(_PYTHON_RE, os.path.basename(words[0].replace("\\", "/"))):
        return None
    rest = words[1:]
    if rest[:1] == ["-B"]:
        rest = rest[1:]
    if len(rest) < 2 or os.path.basename(rest[0]) != TRUST_SCRIPT or rest[1] not in TRUST_VERBS:
        return None
    try:
        if _canon(rest[0], cwd) != _canon(os.path.join(scripts, TRUST_SCRIPT)):
            return None
    except (OSError, ValueError):
        return None
    verb, args = rest[1], rest[2:]
    if verb in ("approve", "revoke"):
        if args and (len(args) != 2 or args[0] != "--root"):
            return None
        return trust_action(verb, root=args[1] if args else ".", cwd=cwd), receipt, base
    if not args or not _whole(_OWNER_RE, args[0].lower()):
        return None
    under, tail = [], args[1:]
    if verb == "disallow-owner" and tail:
        return None
    while tail:
        if len(tail) < 2 or tail[0] != "--under":
            return None
        under.append(tail[1])
        tail = tail[2:]
    return trust_action(verb, owner=args[0], under=under, cwd=cwd), receipt, base


# ------------------------------------------------------------------- requests

def _well_formed(record, kind):
    """True for a record this module wrote: every bound field present and of
    its type, the sha the one of the command text it shows, and a life no
    longer than this module gives (REQUEST_TTL for a request, MAX_TTL for a
    receipt). A file with anything missing binds nothing and is refused; so
    is one whose shown command is not the command its sha releases."""
    if not isinstance(record, dict) or record.get("version") != VERSION:
        return False
    strings = ("id", "class", "command", "command_sha256", "worktree", "session_id")
    if not all(isinstance(record.get(k), str) and record.get(k) for k in strings):
        return False
    if not valid_id(record["id"]) or not isinstance(record.get("action"), dict):
        return False
    if record.get("pin") is not None and not isinstance(record.get("pin"), str):
        return False
    if record["command_sha256"] != command_sha(record["command"]):
        return False
    stamps = ("created", "expires") if kind == "requests" else ("minted", "expires")
    if not all(_number(record.get(k)) for k in stamps):
        return False
    if kind == "receipts":
        return (record.get("via") == USER_PROMPT and record.get("uses") == 1
                and 0 < record["expires"] - record["minted"] <= MAX_TTL)
    return 0 < record["expires"] - record["created"] <= REQUEST_TTL


def _records(root, kind):
    try:
        directory = os.path.join(store_dir(root), kind)
        names = sorted(os.listdir(directory))
    except (OSError, Refused):
        return []
    found = []
    for name in names:
        if name.endswith(".json") and valid_id(name[:-5]):
            path = os.path.join(directory, name)
            found.append((path, _read(path)))
    return found


def _prune(root, now):
    """Delete requests and receipts past their time, and records nobody can
    read. Run from `request` only, so reading a store never changes it."""
    for kind in ("requests", "receipts"):
        for path, record in _records(root, kind):
            if not _well_formed(record, kind) or now > record["expires"]:
                try:
                    os.remove(path)
                except OSError:
                    pass


def request(cls, command, action, worktree, session, pin=None, root=None, now=None):
    """Record a request for one refused command and return its id. The same
    command asked again in the same session, worktree and pin returns the id
    already pending, so a retry does not multiply what the owner is shown.
    Raises Refused when the class is off, the session is unknown, or
    MAX_PENDING requests are already waiting."""
    now = time.time() if now is None else now
    if cls not in settings(root)["classes"]:
        raise Refused(f"the {cls} class is not on (approvals.run.classes, machine file)")
    if not isinstance(session, str) or not session:
        raise Refused("the call carries no session id to bind a request to")
    _prune(root, now)
    sha = command_sha(command)
    pending = [r for _, r in _records(root, "requests") if _well_formed(r, "requests")]
    for record in pending:
        if (record["class"], record["command_sha256"], record["worktree"], record["session_id"],
                record.get("pin"), record["action"]) == (cls, sha, worktree, session, pin, action):
            return record["id"]
    if len(pending) >= MAX_PENDING:
        raise Refused(f"{MAX_PENDING} requests are already waiting for the owner; let them "
                      "be answered or expire")
    record = {"version": VERSION, "id": "ar-" + secrets.token_hex(6), "class": cls,
              "command": command, "command_sha256": sha, "action": action,
              "worktree": worktree, "session_id": session, "pin": pin,
              "created": now, "expires": now + REQUEST_TTL}
    _write(_file(root, "requests", record["id"]), record)
    audit(root, "requested", record)
    return record["id"]


def pending_text(session, root=None, now=None):
    """The owner-facing list of requests THIS session raised and may still be
    answered. Read-only."""
    now = time.time() if now is None else now
    mine = [r for _, r in _records(root, "requests")
            if _well_formed(r, "requests") and r["session_id"] == session
            and r["created"] <= now <= r["expires"]]
    if not mine:
        return ("No request from this session is waiting. A request exists only after an agent's "
                "command was refused with an id; it expires after "
                f"{REQUEST_TTL // 60} minutes and can be answered only in the session that "
                "raised it.")
    lines = ["Requests waiting in this session (type /crew:allow-run <id> to allow ONE run):"]
    for record in sorted(mine, key=lambda r: r["created"]):
        lines.append(f"  {record['id']}  [{_clean(record['class'], 40)}]  "
                     f"{_clean(record['command'])}")
    return "\n".join(lines)


def mint(ident, session, prompt_id, cwd, now=None):
    """Turn request `ident` into a one-use receipt. Called ONLY by the prompt
    hook, for the id the owner typed. Raises Refused, minting nothing, unless
    the request exists, is well formed, is inside its window, was raised in
    THIS session and worktree, its class is still on, and (for `approve`) what
    the gate would run is still what the request recorded. A request mints
    once: it is taken by rename before the receipt is written."""
    now = time.time() if now is None else now
    path = _file(cwd, "requests", ident)
    record = _read(path)
    if record is None:
        raise Refused(f"there is no request {ident} (answered, expired, or never raised here)")
    if not _well_formed(record, "requests") or record["id"] != ident:
        raise Refused(f"request {ident} is not a record crew wrote; nothing was allowed")
    conf = settings(cwd)
    if record["class"] not in conf["classes"]:
        raise Refused(f"the {_clean(record['class'], 40)} class is not on "
                      "(approvals.run.classes, machine file)")
    if not record["created"] <= now <= record["expires"]:
        raise Refused(f"request {ident} is outside its {REQUEST_TTL // 60} minute window; have "
                      "the command run again for a new id")
    if not isinstance(session, str) or not session or record["session_id"] != session:
        raise Refused(f"request {ident} was raised in another session; it can be answered "
                      "only in the session whose command was refused")
    if record["worktree"] != worktree_of(cwd):
        raise Refused(f"request {ident} belongs to another worktree ({_clean(record['worktree'])})")
    _check_pin(record)
    if _claim(path) is None:
        raise Refused(f"request {ident} was answered a moment ago")
    receipt = dict(record, minted=now, expires=now + conf["ttl"], via=USER_PROMPT, uses=1,
                   prompt_id=prompt_id if isinstance(prompt_id, str) else None,
                   request_created=record["created"])
    del receipt["created"]
    _write(_file(cwd, "receipts", ident), receipt)
    audit(cwd, "minted", receipt)
    return receipt


def _check_pin(record):
    if record["class"] != CLASS_TRUST or record["action"].get("verb") != "approve":
        return
    if not record.get("pin") or trust_pin(record["action"]) != record["pin"]:
        raise Refused("what the gate would run changed after the request was raised (or the "
                      "request pins nothing); have the command run again for a new id")


def _live(receipt, ident, cls, worktree, now):
    """Why `receipt` may not be used now, or None."""
    if receipt is None:
        return f"there is no receipt {ident} (spent, expired, or never given by the owner)"
    if not _well_formed(receipt, "receipts") or receipt["id"] != ident:
        return f"receipt {ident} is not one the owner's prompt wrote"
    if not receipt["minted"] <= now <= receipt["expires"]:
        return f"receipt {ident} is outside its window"
    if receipt["class"] != cls:
        return f"receipt {ident} is for the {_clean(receipt['class'], 40)} class, not {cls}"
    if receipt["worktree"] != worktree:
        return f"receipt {ident} belongs to another worktree"
    return None


def check(ident, cls, command, worktree, session, root=None, now=None):
    """`(True, receipt)` when a live receipt covers this exact command text in
    this worktree and session, else `(False, why)`. Spends nothing: the guard
    asks, the tool spends."""
    now = time.time() if now is None else now
    try:
        if cls not in settings(root)["classes"]:
            return False, f"the {cls} class is not on (approvals.run.classes, machine file)"
        receipt = _read(_file(root, "receipts", ident))
    except Refused as exc:
        return False, str(exc)
    why = _live(receipt, ident, cls, worktree, now)
    if why is None and receipt["command_sha256"] != command_sha(command):
        why = f"receipt {ident} is for another command"
    if why is None and receipt["session_id"] != session:
        why = f"receipt {ident} was given in another session"
    return (False, why) if why else (True, receipt)


def spend(ident, cls, action, worktree, pin=None, root=None, now=None):
    """Use receipt `ident` for `action`, once. The receipt is taken by an
    atomic rename BEFORE it is judged, so its first use ends it whatever the
    outcome and a second caller finds nothing. Returns the receipt; raises
    Refused when it does not cover this class, action, worktree and pin, is
    outside its window, or the class or verb is no longer on."""
    now = time.time() if now is None else now
    conf = settings(root)
    if cls not in conf["classes"]:
        raise Refused(f"the {cls} class is not on (approvals.run.classes, machine file)")
    receipt = _claim(_file(root, "receipts", ident))
    why = _live(receipt, ident, cls, worktree, now)
    if why is None and receipt["action"] != action:
        why = f"receipt {ident} is for another command"
    if why is None and cls == CLASS_TRUST and action.get("verb") not in conf["verbs"]:
        why = f"`{action.get('verb')}` is not a verb approvals.run.verbs.verifyTrust opens"
    if why is None and receipt.get("pin") != pin:
        why = "what the gate would run is not what the owner approved"
    if why is None and action.get("verb") == "approve" and not pin:
        why = f"receipt {ident} pins nothing"
    if why:
        if isinstance(receipt, dict):
            audit(root, "spend-refused", receipt, why)
        raise Refused(why)
    audit(root, "spent", receipt)
    return receipt


# ---------------------------------------------------------- the guard's seams

def guard_trust(data, scripts):
    """`(release, lines)` for a shell call `scope_guard.trust_refusal` refused.
    `release` is True only for the plain form re-run with a live receipt for
    this exact text. Otherwise the refusal stands and `lines` is what to add to
    it: with the class on and the form plain, a request id and the exact text
    to re-run; with the class off, nothing (the refusal reads as it always
    did). Never raises: anything unexpected leaves the refusal standing."""
    try:
        return _guard_trust(data, scripts)
    except Refused as exc:
        return False, [f"  No request was recorded: {_clean(exc)}."]
    except Exception as exc:  # noqa: BLE001  pylint: disable=broad-exception-caught
        return False, [f"  No request was recorded ({type(exc).__name__})."]


def _guard_trust(data, scripts):
    tool_input = data.get("tool_input")
    command = tool_input.get("command") if isinstance(tool_input, dict) else None
    cwd = data.get("cwd") if isinstance(data.get("cwd"), str) else None
    parsed = parse_trust_command(command, cwd, scripts)
    if parsed is None:
        return False, []
    conf = settings(cwd)
    if CLASS_TRUST not in conf["classes"]:
        return False, []
    action, ident, base = parsed
    if action["verb"] not in conf["verbs"]:
        return False, [f"  `{action['verb']}` is not a verb the owner opened for "
                       "/crew:allow-run (approvals.run.verbs.verifyTrust)."]
    session = data.get("session_id")
    worktree = worktree_of(cwd)
    if ident is not None:
        ok, got = check(ident, CLASS_TRUST, base, worktree, session, root=cwd)
        if ok:
            return True, []
        return False, [f"  The receipt was refused: {_clean(got)}.",
                       "  Run the command again WITHOUT --receipt for a new request id."]
    new = request(CLASS_TRUST, base, action, worktree, session, pin=trust_pin(action), root=cwd)
    return False, [f"  Request {new} records this exact command. Ask the owner to type "
                   f"`/crew:allow-run {new}`",
                   f"  (their own prompt, this session, within {REQUEST_TTL // 60} minutes), "
                   "then re-run exactly:",
                   f"  {base} --receipt {new}"]


def store_refusal(data, readings, read_only, real):
    """Why a tool call is refused for the run-approval stores ALONE, or None.
    Judged, like the trust refusal, before `scope.mode` is read. `readings`,
    `read_only` and `real` are scope_guard's own helpers (the continuation
    readings of a command, its read-only test, its real-path resolver), handed
    in so this module imports no guard.

    ONLY WHILE A CLASS IS ON (`approvals.run.classes` in the machine file).
    With none on -- the default -- this returns None before it reads a word of
    the call: no receipt is honoured then (`mint`, `check` and `spend` each
    read the same setting), so there is nothing here to protect, and a guard
    nobody turned on must not refuse `rm -rf run-*` or a commit message.
    What that leaves open is in CONFIG.md: a receipt file written by hand
    while the class is off, dated for the hour its writer expects the class
    to be on, and used in the session whose id it names.

    A shell command is refused when, in any reading, as written or with its
    quotes deleted, it is not a read-only command and it names the store
    (`run-approvals`), may name it through a glob or an unexpanded variable or
    substitution (`_veiled_store`: `run-*`, `run-appro[v]als`, `run-approva?s`,
    `${d}-approvals`, `.claude/crew/*`), carries the owner's command with an id
    or an expansion after it (`crew:allow-run ar-...`: a child `claude -p`, a
    piped hook payload, keys sent to a terminal), or runs code beside this
    module's name; and, while a class is on, when it names the prompt hook or
    the hook launcher, or starts Claude on an existing session
    (`claude -p --resume <sid> < prompt.txt`) or with arguments the text does
    not settle. A Write/Edit is refused when its real or named path lies under
    the store or has `run-approvals` as a segment. This function may raise;
    `scope_guard.decide` turns that into a refusal."""
    # `anywhere`: a session standing in `~` or `~/.claude/crew` has the machine file INSIDE its
    # working directory, where `settings` reads "off"; the store is no less the store there.
    if not settings(anywhere=True)["classes"]:
        return None
    tool_input = data.get("tool_input")
    if data.get("tool_name") in ("Bash", "PowerShell"):
        command = tool_input.get("command") if isinstance(tool_input, dict) else None
        if not isinstance(command, str):
            return None
        for reading in readings(command):
            for text in (reading, _QUOTE_RE.sub("", reading)):
                reason = _shell_reason(text, data)
                # `~` only expands to a home directory and a glob to file names: neither
                # makes a read a write, and the read-only parser has no word for them.
                if reason and not read_only(_GLOB_RE.sub("_", reading)):
                    return reason
        return None
    try:
        store = os.path.normcase(os.path.realpath(store_dir()))
    except Refused:
        store = None
    for target in _targets(tool_input):
        absolute = os.path.abspath(target)
        for path in (absolute, real(absolute)):
            folded = os.path.normcase(path)
            segments = folded.replace("\\", "/").lower().split("/")
            if STORE_NAME in segments or (store and (
                    folded == store or folded.startswith(store.rstrip(os.sep) + os.sep))):
                return ("it writes the run-approval store; only the owner's typed "
                        "/crew:allow-run gives a receipt")
    return None


def _shell_reason(text, data):
    if _STORE_NAME_RE.search(text):
        return ("it names the run-approval store; only the owner's typed /crew:allow-run "
                "gives a receipt")
    if _veiled_store(text, data.get("cwd")):
        return ("it may name the run-approval store through a glob or an unexpanded variable; "
                "only the owner's typed /crew:allow-run gives a receipt")
    if _OWNER_COMMAND_RE.search(text):
        return ("it carries `/crew:allow-run` with an id, which only the owner types, in "
                "their own prompt")
    if _MODULE_RE.search(text) and _RUNS_CODE_RE.search(text):
        return "it runs code beside crew_runapproval, the module that records the owner's receipts"
    if _PROMPT_HOOK_RE.search(text):
        cwd = data.get("cwd") if isinstance(data.get("cwd"), str) else None
        if settings(cwd)["classes"]:
            return ("it names the prompt hook, which only the owner's own prompt may drive "
                    "(approvals.run.classes is on)")
    started = _CLAUDE_RE.search(text)
    if started and (_RESUME_RE.search(text[started.end():]) or _UNREAD_RE.search(text)):
        cwd = data.get("cwd") if isinstance(data.get("cwd"), str) else None
        if settings(cwd)["classes"]:
            return ("it starts Claude on an existing session (--resume, --continue, "
                    "--session-id) or with arguments the text does not settle; a prompt "
                    "submitted there counts as this session's (approvals.run.classes is on)")
    return None


def _segment(segment):
    """`(regex, literals, veiled)` for one path segment read as a shell
    pattern. `*`, an expansion and anything unknown match any text, `?` and a
    bracket expression any one character: an over-reading, on purpose."""
    out, literals, veiled, i = [], 0, False, 0
    while i < len(segment):
        char = segment[i]
        close = segment.find("]", i + 2) if char == "[" else -1
        if char in (_ANY, "*"):
            out.append(".*")
        elif char == "?" or close > 0:
            out.append(".")
            i = max(i, close)
        else:
            out.append(re.escape(char))
            literals += 1
            i += 1
            continue
        veiled = True
        i += 1
    return "".join(out), literals, veiled


def _could_be(segment, name, least):
    """True when `segment` is `name`, or is a pattern that can expand to it and
    spells at least `least` of its characters."""
    if segment.lower() == name:
        return True
    pattern, literals, veiled = _segment(segment)
    return bool(veiled and literals >= least
                and re.fullmatch(pattern, name, re.IGNORECASE | re.DOTALL))


def _veiled_store(text, cwd=None):
    """True when a word of `text` may expand to the store's path although it
    does not spell `run-approvals`: a segment holding a glob character or an
    unexpanded variable or substitution that can stand for the store's name,
    AND one thing that puts it at the store: four or more of the name's own
    characters (`run-*`, `run-appro[v]als`, `${d}-approvals`), a store child
    after it (`$X/receipts/a.json`), `.claude/crew` before it (in the word, or
    as the directory the command runs in), or `.claude/crew` named anywhere
    else in the command. Unknown is read as "may": this over-refuses near the
    store and says nothing about a bare `rm *` elsewhere."""
    veiled = _EXPANSION_RE.sub(_ANY, text)
    named = bool(_CREW_DIR_RE.search(text))
    base = [s for s in re.split(r"[/\\]+", cwd) if s] if isinstance(cwd, str) else []
    for word in _WORD_SPLIT_RE.split(veiled):
        if not word:
            continue
        rooted = word[0] in "/\\~" + _ANY or word[1:2] == ":"
        parts = [] if rooted else list(base)
        for part in re.split(r"[/\\]+", word):
            if part == "..":
                del parts[-1:]
            elif part and part != ".":
                parts.append(part)
        lowered = [p.lower() for p in parts]
        inside = any(tuple(lowered[i:i + 2]) == _STORE_PARENT for i in range(len(lowered)))
        for i, part in enumerate(parts):
            pattern, literals, is_veiled = _segment(part)
            if not is_veiled or not re.fullmatch(pattern, STORE_NAME, re.IGNORECASE | re.DOTALL):
                continue
            if literals >= 4 or (named and not inside):
                return True
            if i + 1 < len(parts) and any(_could_be(parts[i + 1], c, 3) for c in _STORE_CHILDREN):
                return True
            if i >= 2 and _could_be(parts[i - 1], "crew", 2) and _could_be(parts[i - 2],
                                                                           ".claude", 3):
                return True
    return False


def _targets(tool_input):
    if not isinstance(tool_input, dict):
        return []
    found = [tool_input.get(key) for key in ("file_path", "notebook_path")]
    for edit in tool_input.get("edits") or []:
        if isinstance(edit, dict):
            found.append(edit.get("file_path"))
    return [p for p in dict.fromkeys(found) if isinstance(p, str) and p]

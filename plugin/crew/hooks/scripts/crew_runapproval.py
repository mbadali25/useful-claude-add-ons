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
Everyday work in a closed, plain shape is excused clause by clause (R-20,
`store_refusal`); anything the shape test cannot read is judged as before.
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
import collections
import fnmatch
import hashlib
import json
import os
import re
import secrets
import tempfile
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
# R-20 D4 (a): the name counts unless it is glued to another name character on the left
# (`my-run-approvals`) or goes on as a longer name on the right (`run-approvals2`,
# `run-approvals.log`). Every other neighbour, `/` `;` `>` `'` a space or the end, is a boundary.
_STORE_NAME_RE = re.compile(r"(?<![\w.-])run[-_]approvals(?![\w-]|\.\w)", re.IGNORECASE)
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
    `scope_guard.decide` turns that into a refusal.

    EXCUSES (R-20). The triggers above are unchanged; a reading of a closed,
    plain shape is excused, and an excuse clears its own clause only (every
    later clause still judges). D2/D3: the hook name or the module beside an
    interpreter, when every simple command is on the closed table
    (`_GIT_ROWS`, `_SIMPLE_ROWS`, `_MODULES`, closed flags; `sed` only alone, with the name only in a
    file operand, because `sed -i` writes chosen text into `.git/config`,
    `pyproject.toml`, `conftest.py` or the hook's own `__main__` guard, which
    the other rows read; no `@file` on a `python -m` row, which pytest, mypy
    and ruff read as more flags). D4: the name's boundary; a commit, tag or PR
    message dropped only when every other command is an RO row or `git add`
    (`sed -i<suffix>` copies the message file and pytest runs a `.py`, `.txt`
    or `.rst` operand; `git log | cut | bash` runs it back); a store name read
    by RO rows only. D5: `claude` as a whole command word with no resume flag
    in its own words. D6: `run-*` placed under a cwd not above the store, or
    under `/tmp`/`/var/tmp` at another depth. D7: one copy or move into the
    crew dir in one closed shape. Changing a table, row, flag or shape is a
    harness change. Kept over-refusals: O18, O19, a variable, redirect or `cd`
    beside a hook name, a heredoc commit message, a rooted word outside `/tmp`
    (`~/x/run-*`), a message naming the store or a hook beside a non-RO row,
    `sed` beside anything, and every copy into the crew dir that is not D7's
    shape (`"$SRC"`, `--`, a mixed word, a second command, `-Path`).
    Residuals, not closed here: R7 a hook imported by pytest or pylint without
    its `__main__` entry; R10 state an earlier call left (`git config`, a
    `conftest.py`, a `sed` into `.git/config`, an `@args.txt`); R1/R9 a stale
    payload cwd; R14 a flag inside a variable set outside the command (Bash);
    R15 `sed -i` on any hook copy, its `__main__` guard included, then a
    pytest run of it in the next call; R16 a copy onto the machine
    `config.json`; R17 a message dropped in one call and read back and run in
    the next."""
    # `anywhere`: a session standing in `~` or `~/.claude/crew` has the machine file INSIDE its
    # working directory, where `settings` reads "off"; the store is no less the store there.
    if not settings(anywhere=True)["classes"]:
        return None
    tool_input = data.get("tool_input")
    tool = data.get("tool_name")
    if tool in ("Bash", "PowerShell"):
        command = tool_input.get("command") if isinstance(tool_input, dict) else None
        if not isinstance(command, str):
            return None
        for reading in readings(command):
            # D4 (b): a commit, tag or PR message is dropped before the triggers read the
            # text, only when nothing beside it in the reading can run it (`_drop_messages`).
            dropped = _drop_messages(reading, tool)
            for text, undropped in ((dropped, reading),
                                    (_QUOTE_RE.sub("", dropped), _QUOTE_RE.sub("", reading))):
                reason = _shell_reason(text, data, reading, undropped)
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


def _shell_reason(text, data, reading=None, undropped=None):
    """Why `text` is refused, or None. `text` is one reading, as written or with its quotes
    deleted, with its messages dropped (D4 b); `undropped` is the same text before the drop,
    which only the owner-command clause reads (D4 c); `reading` is the reading as written, the
    only thing an excuse is read from (R-20). With no `reading` there is no excuse: every
    clause judges as it did before R-20. Each clause keeps its own trigger, and an excuse
    clears its own clause only (R-20 "Order"): judging goes on to every later clause."""
    tool = data.get("tool_name")
    undropped = text if undropped is None else undropped
    if _STORE_NAME_RE.search(text) and not _read_rows_only(reading, tool):
        return ("it names the run-approval store; only the owner's typed /crew:allow-run "
                "gives a receipt")
    if _veiled_store(text, data.get("cwd"), reading, tool):
        return ("it may name the run-approval store through a glob or an unexpanded variable; "
                "only the owner's typed /crew:allow-run gives a receipt")
    if _OWNER_COMMAND_RE.search(undropped):
        return ("it carries `/crew:allow-run` with an id, which only the owner types, in "
                "their own prompt")
    if (_MODULE_RE.search(text) and _RUNS_CODE_RE.search(text)
            and not _named_excused(reading, tool)):
        return "it runs code beside crew_runapproval, the module that records the owner's receipts"
    if _PROMPT_HOOK_RE.search(text) and not _named_excused(reading, tool):
        cwd = data.get("cwd") if isinstance(data.get("cwd"), str) else None
        if settings(cwd)["classes"]:
            return ("it names the prompt hook, which only the owner's own prompt may drive "
                    "(approvals.run.classes is on)")
    started = _CLAUDE_RE.search(text)
    if started and (_RESUME_RE.search(text[started.end():]) or _UNREAD_RE.search(text)):
        cwd = data.get("cwd") if isinstance(data.get("cwd"), str) else None
        if settings(cwd)["classes"] and not _claude_excused(reading, tool):
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


def _veiled_store(text, cwd=None, reading=None, tool=None):
    """True when a word of `text` may expand to the store's path although it
    does not spell `run-approvals`: a segment holding a glob character or an
    unexpanded variable or substitution that can stand for the store's name,
    AND one thing that puts it at the store: four or more of the name's own
    characters (`run-*`, `run-appro[v]als`, `${d}-approvals`), a store child
    after it (`$X/receipts/a.json`), `.claude/crew` before it (in the word, or
    as the directory the command runs in), or `.claude/crew` named anywhere
    else in the command. Unknown is read as "may": this over-refuses near the
    store and says nothing about a bare `rm *` elsewhere.

    R-20, two narrowings, each read from `reading` as written: `.claude/crew`
    named elsewhere is not counted when the whole reading is one copy or move
    INTO the crew dir in D7's closed shape (`_destination_only`); and four
    letters alone refuse only when D6 cannot place every such word away from
    the store (`_placed_reading`). The store child and `.claude/crew`-before
    tests are untouched."""
    veiled = _EXPANSION_RE.sub(_ANY, text)
    named = bool(_CREW_DIR_RE.search(text)) and not _destination_only(reading, tool)
    four = False
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
            if named and not inside:
                return True
            if i + 1 < len(parts) and any(_could_be(parts[i + 1], c, 3) for c in _STORE_CHILDREN):
                return True
            if i >= 2 and _could_be(parts[i - 1], "crew", 2) and _could_be(parts[i - 2],
                                                                           ".claude", 3):
                return True
            if literals >= 4:
                four = True
    # Four letters alone: refused unless D6 places every such word away from the store.
    return four and not _placed_reading(reading, tool, cwd)


def _targets(tool_input):
    if not isinstance(tool_input, dict):
        return []
    found = [tool_input.get(key) for key in ("file_path", "notebook_path")]
    for edit in tool_input.get("edits") or []:
        if isinstance(edit, dict):
            found.append(edit.get("file_path"))
    return [p for p in dict.fromkeys(found) if isinstance(p, str) and p]


# ------------------------------------------------------------------ R-20 excuses
#
# The store tripwire's triggers above are unchanged. What follows only EXCUSES
# a reading of a recognised, closed shape, and an excuse clears its own clause
# only. A reading this code cannot read is "not plain" and is judged exactly as
# before (could-not-tell stays a refusal). Every table, row, flag, module and
# shape here is CLOSED: adding one is a harness change with its own review.

_Word = collections.namedtuple("_Word", "value quoted start end")
_Cmd = collections.namedtuple("_Cmd", "words redirects after")


class _NotPlain(Exception):
    """The reading holds something the plain scan (G) does not read."""


_PLAIN_CHARS = frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_./:=,@+-*?[]")
_ENDS_WORD = " \t\n;&|"
_PIPES = ("&&", "||", "|")
_NAME_EQ_RE = re.compile(r"--[A-Za-z0-9][A-Za-z0-9_-]*=", re.ASCII)
_VARIABLE_RE = re.compile(r"\$(?:env:)?[A-Za-z_][A-Za-z0-9_]*|\$\{[A-Za-z_][A-Za-z0-9_]*\}", re.ASCII)
_DIGITS_RE = re.compile(r"[0-9]+", re.ASCII)


def _plain_commands(reading, tool, loose=False):
    """G. The simple commands of `reading` (one continuation reading, as
    written) as `_Cmd`s of `_Word`s (value with quotes removed, "was quoted",
    span), or None when the reading is not plain. Plain: words of
    `A-Z a-z 0-9 _ . / : = , @ + -` and `* ? [ ]`, a `~` first in a word,
    on PowerShell also `\\`; quoted spans that are a whole word or the whole
    value of a `--name=` word; the separators `&& || | ;` and newline. Escapes
    per tool: Bash backslash and PowerShell backtick are not plain; a Bash
    double-quoted span holds no `$`, backtick or backslash, a PowerShell one no
    `$` or backtick and ends at the next `"`. `loose` (D5 only) also admits a
    plain variable and the redirects `> >> 2> 2>> &> <` with one word, and
    `2>&1`, returned apart from the words."""
    try:
        return _Scan(reading, tool == "PowerShell", loose).commands()
    except _NotPlain:
        return None


class _Scan:
    """One strict pass over a reading (G). Raises _NotPlain on anything else."""

    def __init__(self, reading, ps, loose):
        if not isinstance(reading, str):
            raise _NotPlain
        self.text, self.ps, self.loose = reading, ps, loose
        self.out, self.words, self.redirects = [], [], []
        self.after = self.target = None

    def close(self, sep):
        if self.target is not None:
            raise _NotPlain
        if self.words:
            self.out.append(_Cmd(tuple(self.words), tuple(self.redirects), self.after))
        elif self.redirects or sep in _PIPES or self.after in _PIPES:
            raise _NotPlain
        self.words, self.redirects, self.after = [], [], sep

    def commands(self):
        text, i, n = self.text, 0, len(self.text)
        while i < n:
            char, pair = text[i], text[i:i + 2]
            if char in " \t":
                i += 1
            elif char in "\n;":
                self.close(char)
                i += 1
            elif pair in ("&&", "||"):
                self.close(pair)
                i += 2
            elif char == "|":
                self.close(char)
                i += 1
            elif self.loose and pair == "&>" and self.target is None:
                self.target, i = pair, i + 2
            elif self.loose and char in "<>" and self.target is None:
                self.target = ">>" if pair == ">>" else char
                i += len(self.target)
            else:
                i = self.word(i)
        self.close(None)
        if not self.out:
            raise _NotPlain
        return self.out

    def word(self, i):
        word, end = _scan_word(self.text, i, self.ps, self.loose)
        if self.target is not None:
            self.redirects.append((self.target, word))
            self.target = None
        elif self.loose and word.value == "2" and not word.quoted and self.text[end:end + 1] == ">":
            if self.text.startswith(">&1", end):
                self.redirects.append(("2>&1", None))
                return end + 3
            self.target = "2>>" if self.text.startswith(">>", end) else "2>"
            return end + len(self.target) - 1
        else:
            self.words.append(word)
        return end


def _scan_word(text, i, ps, loose):
    """One word of a plain reading, from `i`: `(_Word, end)`."""
    start, n, value, quoted = i, len(text), [], False
    stops = _ENDS_WORD + ("<>" if loose else "")
    while i < n and text[i] not in stops:
        char = text[i]
        if char in "'\"":
            if i != start and not _NAME_EQ_RE.fullmatch("".join(value)):
                raise _NotPlain
            close = text.find(char, i + 1)
            if close < 0:
                raise _NotPlain
            body = text[i + 1:close]
            if char == '"':
                bare = _VARIABLE_RE.sub("", body) if loose else body
                if "$" in bare or "`" in bare or (not ps and "\\" in body):
                    raise _NotPlain
            value.append(body)
            quoted, i = True, close + 1
            if i < n and text[i] not in _ENDS_WORD:
                raise _NotPlain  # a closing quote ends the word
            break
        if char == "$" and loose:
            match = _VARIABLE_RE.match(text, i)
            if not match:
                raise _NotPlain
            value.append(match.group())
            i = match.end()
            continue
        if not (char in _PLAIN_CHARS or (char == "~" and i == start) or (char == "\\" and ps)):
            raise _NotPlain
        value.append(char)
        i += 1
    word = "".join(value)
    if i == start or (ps and not quoted and word.startswith("@")):
        raise _NotPlain
    return _Word(word, quoted, start, i), i


# --- T: the command table (closed) ---------------------------------------------

_Spec = collections.namedtuple("_Spec", "flags letters fold checks")


def _any_value(_value):
    return True


def _spec(text, fold=False, checks=None):
    """A closed flag list written as the R-20 spec writes it: `-x` a flag,
    `-x <w>` a flag and its value word, `-x <n>` a value of digits only,
    `--x=` the attached form `--x=<value>`, `-<n>` a dash and digits.
    Single-letter flags that take no value may cluster (`-rf`); a PowerShell
    cmdlet's names (`fold`) are compared ignoring case and never cluster."""
    flags, tokens = {}, text.split()
    for j, token in enumerate(tokens):
        if token in ("<w>", "<n>"):
            continue
        following = tokens[j + 1] if j + 1 < len(tokens) else ""
        kind = following if following in ("<w>", "<n>") else ("=" if token.endswith("=") else "")
        flags[token.lower() if fold else token] = kind
    letters = "" if fold else "".join(name[1] for name, kind in flags.items()
                                      if len(name) == 2 and name[0] == "-" and name[1].isalnum()
                                      and not kind)
    return _Spec(flags, frozenset(letters), fold, checks or {})


def _flag_width(words, i, spec):
    """How many words the flag at `words[i]` takes (1 or 2), or 0 when the
    row does not list it in that form."""
    value = words[i].value
    name = value.lower() if spec.fold else value
    kind = spec.flags.get(name)
    if kind == "":
        return 1
    if kind in ("<w>", "<n>"):
        if i + 1 >= len(words):
            return 0
        given = words[i + 1].value
        if kind == "<n>" and not _DIGITS_RE.fullmatch(given):
            return 0
        return 2 if spec.checks.get(name, _any_value)(given) else 0
    key, equals, given = name.partition("=")
    if equals and spec.flags.get(key + "=") == "=":
        return 1 if spec.checks.get(key + "=", _any_value)(given) else 0
    if "-<n>" in spec.flags and re.fullmatch(r"-[0-9]+", value, re.ASCII):
        return 1
    if spec.letters and re.fullmatch(r"-[A-Za-z0-9]+", value, re.ASCII) and set(value[1:]) <= spec.letters:
        return 1
    return 0


def _fit(words, spec, ps):
    """The operands of `words` (a command's words after its name) when every
    flag fits `spec`, else None. A word whose value starts with `-` and stands
    before a bare `--` is a flag. On PowerShell a quoted word is never a
    parameter, so a quoted word starting with `-` takes the command off."""
    operands, i, ended = [], 0, False
    while i < len(words):
        word = words[i]
        if ended or not word.value.startswith("-"):
            operands.append(word)
            i += 1
            continue
        if ps and word.quoted:
            return None
        if word.value == "--":
            ended, i = True, i + 1
            continue
        width = _flag_width(words, i, spec)
        if not width:
            return None  # an unlisted flag takes the command off the table
        i += width
    return operands


_GIT_ROWS = {  # subcommand: (closed flags, RO)
    "status": (_spec("-s --short -b --branch --porcelain --porcelain= --ignored --untracked-files= "
                     "-uno -uall"), True),
    "diff": (_spec("--stat --cached --staged --name-only --name-status --numstat --shortstat "
                   "--unified= -w -b -p --color --no-color --no-ext-diff --no-textconv"), True),
    "log": (_spec("--oneline -<n> -n <n> --max-count= --stat --name-only --name-status --graph "
                  "--decorate --all --follow -p --patch -i --grep= --author= --since= --until= "
                  "--format= --pretty= --no-merges"), True),
    "show": (_spec("--stat --name-only --name-status --oneline -s --no-patch --format= --pretty="), True),
    "grep": (_spec("-n --line-number -i --ignore-case -l --files-with-matches -w -E -F -P -h -H "
                   "--count -e <w>"), True),
    "add": (_spec("-A --all -u --update -f --force -n --dry-run -v --verbose -N --intent-to-add"), False),
    "commit": (_spec("-m <w> --message= -a --all -s --signoff -q --quiet -v --amend --no-edit "
                     "--allow-empty"), False),
}
_BOTH, _BASH, _PWSH = ("Bash", "PowerShell"), ("Bash",), ("PowerShell",)
_SIMPLE_ROWS = {  # name (PowerShell: lower case): (tools, closed flags, RO)
    "rg": (_BOTH, _spec("-n -i -l -w -F -S -c --count --hidden --no-heading -e <w> -g <w> --glob= "
                        "-t <w> --type= -A <n> -B <n> -C <n>"), True),
    "grep": (_BASH, _spec("-n -i -l -w -E -F -r -R -c -h -H -o -v -q -s -e <w> --include= "
                          "--exclude= --exclude-dir= -A <n> -B <n> -C <n>"), True),
    "cat": (_BASH, _spec("-n"), True),
    "ls": (_BASH, _spec("-l -a -A -r -t -h -d -R -1"), True),
    "shellcheck": (_BOTH, _spec("-x --external-sources -s <w> --shell= -S <w> --severity= -e <w> "
                                "--exclude= -f <w> --format="), True),
    "get-content": (_PWSH, _spec("-Path <w> -LiteralPath <w> -Raw -TotalCount <n> -Tail <n> "
                                 "-Encoding <w>", fold=True), True),
    "select-string": (_PWSH, _spec("-Path <w> -LiteralPath <w> -Pattern <w> -SimpleMatch "
                                   "-CaseSensitive -List -NotMatch -AllMatches -Context <n>",
                                   fold=True), True),
    "rm": (_BASH, _spec("-r -R -f -v"), False),
    "remove-item": (_PWSH, _spec("-Recurse -Force -Path <w> -LiteralPath <w> -ErrorAction <w>",
                                 fold=True), False),
}
_PS_ALIASES = {"gc": "get-content", "sls": "select-string", "ri": "remove-item"}
_PYLINT_FORMATS = ("text", "parseable", "colorized", "json", "json2", "msvs", "github")
_MODULES = {  # `python -m <module>`, the full dotted name compared exactly
    "pytest": _spec("-q -v -vv -x -s -k <w> -m <w> --tb= --maxfail= -n <w> --co --collect-only "
                    "--lf --ff -p <w>", checks={"-p": lambda value: value.startswith("no:")
                                                and len(value) > 3}),
    "pylint": _spec("--from-stdin -E --errors-only --disable= --enable= -j <n> --output-format= "
                    "--score= --reports=",
                    checks={"--output-format=": lambda value: value in _PYLINT_FORMATS}),
    "ruff": _spec("--fix --diff --check -q --quiet --select= --ignore= --output-format= --no-cache"),
    "mypy": _spec("--strict --ignore-missing-imports --no-incremental"),
    "flake8": _spec("--max-line-length= --select= --ignore="),
    "pycodestyle": _spec("--max-line-length= --select= --ignore="),
    "black": _spec("--check --diff -q -l <n> --line-length="),
    "isort": _spec("--check --check-only --diff -q"),
    "pyflakes": _spec(""),
    "pyright": _spec(""),
    "json.tool": _spec("--sort-keys --indent <n>"),
}
_RO_ROWS = frozenset(["git " + sub for sub, (_flags, ro) in _GIT_ROWS.items() if ro]
                     + [name for name, (_tools, _flags, ro) in _SIMPLE_ROWS.items() if ro])
# D4 (b1): what may stand beside a dropped message. Read from T's RO column, plus `git add`;
# a non-RO row admitted here is a harness change with its own review.
_BESIDE_MESSAGE = _RO_ROWS | {"git add"}
_FIND_PRIMARIES = {"-name": "<w>", "-iname": "<w>", "-type": "<w>", "-maxdepth": "<n>",
                   "-mindepth": "<n>", "-print": "", "-delete": ""}


def _program(word, tool):
    """The command word as T compares it: exact on Bash; on PowerShell
    ignoring case, a trailing `.exe` dropped, a listed alias resolved. None
    for a quoted word."""
    if word.quoted:
        return None
    name = word.value
    if tool == "PowerShell":
        name = name.lower()
        name = name[:-4] if name.endswith(".exe") else name
        name = _PS_ALIASES.get(name, name)
    return name


def _on_table(cmd, tool):
    """T. The row `cmd` stands on (`git log`, `rg`, `sed`, `python -m pytest`
    ...), or None when it is off the table. No prefix is stripped: an
    assignment, a wrapper, a keyword or a path-qualified program leaves a
    first word that is not a row's name."""
    words = cmd.words
    ps = tool == "PowerShell"
    name = _program(words[0], tool)
    if name == "git":
        return _git_row(words, ps)
    if name in ("python3", "python", "py"):
        return _module_row(words, name, ps)
    if name == "sed" and not ps:
        parts = _sed_parts(words)
        if parts is None or not _sed_script_ok(parts[1].value):
            return None
        return "sed"
    if name == "find" and not ps:
        return "find" if _find_parts(words) is not None else None
    row = _SIMPLE_ROWS.get(name)
    if row is None or tool not in row[0] or _fit(words[1:], row[1], ps) is None:
        return None
    return name


def _git_row(words, ps):
    k = 2 if len(words) > 1 and words[1].value == "--no-pager" else 1
    if len(words) <= k or words[k].quoted:
        return None  # `git -c`, `git -C`, `--git-dir` ... stand where the subcommand must
    row = _GIT_ROWS.get(words[k].value)
    if row is None or _fit(words[k + 1:], row[0], ps) is None:
        return None
    return "git " + words[k].value


def _module_row(words, name, ps):
    rest = list(words[1:])
    if name == "py" and rest[:1] and rest[0].value == "-3":
        rest = rest[1:]
    if len(rest) < 2 or rest[0].value != "-m":
        return None  # `-m` second: no interpreter flag is admitted
    module = rest[1].value
    spec = _MODULES.get(module)
    if spec is None:  # a module not on the list is off the table
        return None
    if any(word.value.startswith("@") for word in rest[2:]):
        return None  # an `@file` operand is read as more flags (pytest, mypy, ruff response files)
    operands = _fit(rest[2:], spec, ps)
    if operands is None:
        return None
    if module == "ruff" and (not operands or operands[0].value not in ("check", "format")):
        return None
    if module == "json.tool" and len(operands) > 1:
        return None  # a second operand is an output file
    return "python -m " + module


def _sed_parts(words):
    """`(in-place word, script word, file operands)` of a `sed -i[<suffix>]
    [-E|-r] <script> <file>...` (or `-e <script>`), or None."""
    in_place = script = None
    extended = ended = False
    files, k = [], 1
    while k < len(words):
        word = words[k]
        if ended or not word.value.startswith("-"):
            if script is None:
                script = word
            else:
                files.append(word)
        elif word.value == "--":
            ended = True
        elif word.value.startswith("-i") and in_place is None:
            in_place = word
        elif word.value in ("-E", "-r") and not extended:
            extended = True
        elif word.value == "-e" and script is None and k + 1 < len(words):
            script, k = words[k + 1], k + 1
        else:
            return None
        k += 1
    if in_place is None or script is None or not files:
        return None
    return in_place, script, files


def _sed_script_ok(script):
    """One substitution and nothing else: `s`, a delimiter that is not a
    letter, digit, space or backslash, exactly three unescaped delimiters,
    then flags from `g I i` and digits. GNU sed's `e` and `w` run a command
    and write a file; neither fits."""
    if "\n" in script or len(script) < 4 or script[0] != "s":
        return False
    delimiter = script[1]
    if delimiter.isalnum() or delimiter in " \\" or ord(delimiter) > 127:
        return False
    count, last, k = 0, -1, 1
    while k < len(script):
        if script[k] == "\\":
            k += 2
            continue
        if script[k] == delimiter:
            count, last = count + 1, k
        k += 1
    return count == 3 and re.fullmatch(r"[gIi0-9]*", script[last + 1:], re.ASCII) is not None


def _sed_names_outside_files(cmd):
    """True when a word of this `sed` other than a file operand (its script,
    a `-e` script, its `-i<suffix>`) names a hook or this module."""
    parts = _sed_parts(cmd.words)
    files = {word.start for word in parts[2]} if parts else set()
    return any(_PROMPT_HOOK_RE.search(word.value) or _MODULE_RE.search(word.value)
               for word in cmd.words if word.start not in files)


def _find_parts(words):
    """`(roots, pattern word indexes)` of a `find <root>... <primaries>` on
    its row, or None."""
    k, roots, patterns = 1, [], set()
    while k < len(words) and not words[k].value.startswith("-"):
        roots.append(words[k])
        k += 1
    while k < len(words):
        kind = _FIND_PRIMARIES.get(words[k].value)
        if kind is None:
            return None
        if kind:
            if k + 1 >= len(words) or (kind == "<n>" and not _DIGITS_RE.fullmatch(words[k + 1].value)):
                return None
            if words[k].value in ("-name", "-iname"):
                patterns.add(k + 1)
            k += 2
        else:
            k += 1
    return roots, patterns


def _rows(cmds, tool):
    """The row of every simple command, or None when one is off the table.
    On PowerShell a pipe binds objects to the next cmdlet's parameters
    (`Get-Content list.txt | Remove-Item`), so what stands after `|` must be
    on an RO row."""
    if not cmds:
        return None
    rows = []
    for cmd in cmds:
        row = _on_table(cmd, tool)
        if row is None:
            return None
        if tool == "PowerShell" and cmd.after == "|" and row not in _RO_ROWS:
            return None
        rows.append(row)
    return rows


def _all_on_table(cmds, tool):
    """T's one test for D2, D3 and D6 (1): every simple command on the table,
    and `sed` stands alone. `sed -i` writes text the command chooses into any
    existing file, and the other rows read `.git/config`, `pyproject.toml`,
    `conftest.py` and the hook's own `__main__` guard, so a `sed` is excused
    only as the reading's only simple command, and only with a hook or module
    name in a file operand (never in its script or suffix)."""
    rows = _rows(cmds, tool)
    if rows is None:
        return False
    if "sed" in rows and len(rows) != 1:
        return False
    if any(_sed_names_outside_files(cmd) for cmd, row in zip(cmds, rows) if row == "sed"):
        return False
    return True


def _named_excused(reading, tool):
    """D2 and D3: a reading that names the prompt hook, or runs code beside
    this module, is excused when it is plain and every simple command of it
    is on the table (`_all_on_table`). A name that stands in a commit, tag or
    PR message is never excused here: a message D4 (b1) did not drop is
    judged as written, beside whatever stands with it."""
    if reading is None or _names_in_messages(reading, tool):
        return False
    return _all_on_table(_plain_commands(reading, tool), tool)


def _names_in_messages(reading, tool):
    """True when a message word of a message command in the reading names a
    hook or this module and D4 (b1) kept that message."""
    if _drop_messages(reading, tool) != reading:
        return False  # the messages were dropped: the triggers never read them
    for cmd in _plain_commands(reading, tool) or ():
        for start, end in _message_args(cmd, tool) or ():
            if _PROMPT_HOOK_RE.search(reading[start:end]) or _MODULE_RE.search(reading[start:end]):
                return True
    return False


def _read_rows_only(reading, tool):
    """D4 (d): a reading that names the store is excused when it is plain and
    every simple command of it stands on an RO row (it can only read)."""
    rows = _rows(_plain_commands(reading, tool), tool) if reading is not None else None
    return rows is not None and all(row in _RO_ROWS for row in rows)


# --- D4 (b): message dropping ---------------------------------------------------

_MESSAGE_ROWS = {  # closed; used by D4 (b1) only, so it excuses nothing on its own
    "git tag": (_spec("-a --annotate -m <w> --message= -f --force"), (1, 2)),
    "gh pr create": (_spec("--title <w> --title= -t <w> --body <w> --body= -b <w> --label <w> -l <w> "
                           "--base <w> -B <w> --head <w> -H <w> --draft -d"), (0, 0)),
    "gh issue create": (_spec("--title <w> --title= -t <w> --body <w> --body= -b <w> --label <w> "
                              "-l <w>"), (0, 0)),
    "gh pr edit": (_spec("--title <w> --title= -t <w> --body <w> --body= -b <w> --add-label <w> "
                         "--remove-label <w>"), (1, 1)),
    "gh issue edit": (_spec("--title <w> --title= -t <w> --body <w> --body= -b <w> --add-label <w> "
                            "--remove-label <w>"), (1, 1)),
    "gh pr comment": (_spec("--body <w> --body= -b <w>"), (1, 1)),
    "gh issue comment": (_spec("--body <w> --body= -b <w>"), (1, 1)),
}
_MESSAGE_FLAGS = {"git": ("-m", "--message="), "gh": ("--title", "-t", "--body", "-b", "--title=",
                                                      "--body=")}


def _message_args(cmd, tool):
    """D4 (b1) (iii). The spans of the quoted message words of a message
    command on its closed row (`git commit` on T's row, `git tag` and `gh` on
    `_MESSAGE_ROWS`), or None when `cmd` is not one. Only a command whose
    command word is `git` with `commit`/`tag` next, or `gh` with
    `pr|issue create|edit|comment` next, is one."""
    words = cmd.words
    if tool == "PowerShell" and cmd.after == "|":
        return None
    head = 0
    words = words[head:]
    name = _program(words[0], tool)
    sub = [word.value for word in words[1:3]]
    if name == "git" and sub[:1] == ["commit"]:
        if _git_row(words, tool == "PowerShell") != "git commit":
            return None
        key = None
    elif name == "git" and sub[:1] == ["tag"]:
        key = "git tag"
    elif name == "gh" and len(sub) == 2:
        key = "gh " + " ".join(sub)
        if key not in _MESSAGE_ROWS:
            return None
    else:
        return None
    if key is not None:
        spec, (least, most) = _MESSAGE_ROWS[key]
        operands = _fit(words[len(key.split()):], spec, tool == "PowerShell")
        if operands is None or not least <= len(operands) <= most:
            return None
        if most and key != "git tag" and not _DIGITS_RE.fullmatch(operands[0].value):
            return None
    flags, spans, k = _MESSAGE_FLAGS[name], [], 1
    while k < len(words):
        word = words[k]
        if word.value in flags and k + 1 < len(words):
            if words[k + 1].quoted:
                spans.append((words[k + 1].start, words[k + 1].end))
            k += 2
            continue
        for prefix in flags:
            if prefix.endswith("=") and word.quoted and word.value.startswith(prefix):
                spans.append((word.start + len(prefix), word.end))
        k += 1
    return spans


def _beside_message(cmd, tool):
    """D4 (b1) (i) and (ii): an RO row of T, or `git add`."""
    row = _on_table(cmd, tool)
    if tool == "PowerShell" and cmd.after == "|" and row not in _RO_ROWS:
        return False
    return row in _BESIDE_MESSAGE


def _drop_messages(reading, tool):
    """D4 (b). `reading` with each commit, tag or PR message (one quoted
    word) removed, when the reading is plain and EVERY simple command of it
    is an RO row of T, `git add`, or a message command on its closed row.
    Anything else anywhere in the reading, and nothing is dropped: git keeps
    the message, so a later command of the same reading could read it back
    and run it (`git log -1 --oneline | cut -d ' ' -f 2- | bash`), and
    `sed -i<suffix>` copies `.git/COMMIT_EDITMSG` to a name pytest runs
    (`.py`, or a `.txt`/`.rst` doctest)."""
    cmds = _plain_commands(reading, tool)
    if not cmds:
        return reading
    spans = []
    for cmd in cmds:
        message = _message_args(cmd, tool)
        if message is None and not _beside_message(cmd, tool):
            return reading  # (b1): something beside the message could run it
        spans.extend(message or ())
    for start, end in sorted(spans, reverse=True):
        reading = reading[:start] + reading[end:]
    return reading


# --- D5: Claude started fresh ---------------------------------------------------

_CLAUDE_WORD_RE = re.compile(r"claude(?:-code)?(?:\.exe|\.cmd|\.bat|\.ps1)?", re.IGNORECASE | re.ASCII)


def _claude_excused(reading, tool):
    """D5. Excused when the reading is plain under `loose`, every claude word
    in it is the whole command word of a simple command (or `npx
    <...>/claude-code`), and each such command's own words, read as values
    (quotes removed) and never its redirect targets, hold no resume flag and
    nothing the text does not settle."""
    cmds = _plain_commands(reading, tool, loose=True) if reading is not None else None
    if cmds is None:
        return False
    owned = {}
    for cmd in cmds:
        words = cmd.words
        if not words[0].quoted and _CLAUDE_WORD_RE.fullmatch(words[0].value):
            owned[words[0].end] = words[1:]
        elif (_program(words[0], tool) == "npx" and len(words) > 1 and not words[1].quoted
              and words[1].value.lower().endswith("/claude-code")):
            owned[words[1].end] = words[2:]
    matches = list(_CLAUDE_RE.finditer(reading))
    if len(_CLAUDE_RE.findall(_QUOTE_RE.sub("", reading))) != len(matches):
        return False  # (2) a claude word inside a quoted argument (`bash -c 'claude ...'`)
    for match in matches:
        args = owned.get(match.end())
        if args is None:
            return False  # (2) a claude word that is not a whole command word
        own = " ".join(word.value for word in args)
        if _RESUME_RE.search(own) or _UNREAD_RE.search(own):
            return False
    return True


# --- D6: four letters of the name, placed away from the store -------------------

_PLACED_RE = re.compile(r"[A-Za-z0-9_.*?\[\]/-]+", re.ASCII)
_PS_PLACED_RE = re.compile(r"[A-Za-z0-9_.*?\[\]/\\-]+", re.ASCII)
_TMP_ROOTS = ("/tmp/", "/var/tmp/")
_HAS_GLOB_RE = re.compile(r"[*?\[\]]")


def _store_targets():
    """The home in both forms (`expanduser`, as `_machine_path` places the
    store, literal and real) and the store under each."""
    home = os.path.expanduser("~")
    homes = {os.path.abspath(home), os.path.realpath(home)}
    return homes, [os.path.join(h, ".claude", "crew", STORE_NAME) for h in homes]


def _under(path, folder):
    path, folder = os.path.normcase(path), os.path.normcase(folder)
    return path == folder or path.startswith(folder.rstrip(os.sep) + os.sep)


def _segments(word, ps):
    return [s for s in re.split(r"[/\\]" if ps else "/", word) if s not in ("", ".")]


def _segments_ok(segments):
    for segment in segments:
        if segment == "..":
            return False  # a climb leaves the directory the word is read from
        if "**" in segment or segment.endswith(" ") or (segment.endswith(".") and segment != ".."):
            return False
    return True


def _holds_four(value):
    """True when `value` holds a glob or expansion that can stand for the
    store's name and spells four or more of its letters."""
    for piece in _WORD_SPLIT_RE.split(_EXPANSION_RE.sub(_ANY, value)):
        for part in re.split(r"[/\\]+", piece):
            pattern, literals, veiled = _segment(part)
            if veiled and literals >= 4 and re.fullmatch(pattern, STORE_NAME,
                                                         re.IGNORECASE | re.DOTALL):
                return True
    return False


def _cwd_clear(cwd):
    """The relative form's test: a string absolute cwd that, in both its
    forms, is neither an ancestor-or-self of a store target nor at or under
    `<home>/.claude` (in both its forms)."""
    if not isinstance(cwd, str) or not os.path.isabs(cwd):
        return False  # a relative word with no string cwd is not placed
    homes, targets = _store_targets()
    forms = {os.path.abspath(cwd), os.path.realpath(cwd)}
    above = any(_under(target, form) for target in targets for form in forms)
    return not above and not any(_under(form, os.path.join(home, ".claude"))
                                 for form in forms for home in homes)


def _tmp_bases(root):
    real = tempfile.gettempdir() if os.name == "nt" else os.path.realpath(root)
    return {root, real}


def _placed(word, tool, cwd):
    """D6: True when `word` (a value as G returns it) stays away from the
    store in one of two closed forms: relative under a cwd that is not above
    the store, or under `/tmp` / `/var/tmp` (Bash) at a depth the store cannot
    have. Every other start of a word is not placed."""
    ps = tool == "PowerShell"
    if not (_PS_PLACED_RE if ps else _PLACED_RE).fullmatch(word):
        return False
    if not ps and word.startswith(_TMP_ROOTS):
        root = "/var/tmp" if word.startswith("/var/tmp/") else "/tmp"
        rest = _segments(word[len(root):], False)
        if not rest or not _segments_ok(rest):
            return False
        _homes, targets = _store_targets()
        for base in _tmp_bases(root):
            path = _segments(base, True) + rest
            for target in targets:
                goal = _segments(target, True)
                if len(goal) == len(path) and all(fnmatch.fnmatchcase(t.lower(), w.lower())
                                                  for w, t in zip(path, goal)):
                    return False
        return True
    if word[0] in "/\\":
        return False  # every other root form is not placed (/c/, //host, /proc, /opt ...)
    segments = _segments(word, ps)
    return bool(segments) and _segments_ok(segments) and _cwd_clear(cwd)


def _placed_root(word, tool, cwd):
    """D6 (3): a `find` root, literal segments only, is placed when no store
    target lies at or under it."""
    if not _PLACED_RE.fullmatch(word) or _HAS_GLOB_RE.search(word):
        return False
    _homes, targets = _store_targets()
    if word in ("/tmp", "/var/tmp") or word.startswith(_TMP_ROOTS):
        root = "/var/tmp" if word.startswith("/var/tmp") else "/tmp"
        rest = _segments(word[len(root):], False)
        if not _segments_ok(rest):
            return False
        paths = [os.path.join(base, *rest) for base in _tmp_bases(root)]
    elif word.startswith("/"):
        return False
    else:
        segments = _segments(word, tool == "PowerShell")
        if not _segments_ok(segments) or not isinstance(cwd, str) or not os.path.isabs(cwd):
            return False
        paths = [os.path.join(form, *segments)
                 for form in (os.path.abspath(cwd), os.path.realpath(cwd))]
    return not any(_under(target, os.path.abspath(path)) for target in targets for path in paths)


_DOT = _Word(".", False, 0, 0)


def _placed_reading(reading, tool, cwd):
    """D6. A reading whose only store hint is four of the name's letters in a
    glob is excused when (1) it is plain and every simple command is on the
    table, (2) every word holding such a candidate is placed elsewhere (a
    `find -name` word is a pattern, not a path) and (3) every `find` root is
    placed elsewhere as a root (no root: the cwd)."""
    if reading is None:
        return False
    cmds = _plain_commands(reading, tool)
    if not _all_on_table(cmds, tool):  # D6 (1)
        return False
    for cmd in cmds:
        parts = _find_parts(cmd.words) if _program(cmd.words[0], tool) == "find" else None
        roots, patterns = (parts[0] or [_DOT], parts[1]) if parts else ((), set())
        for k, word in enumerate(cmd.words):
            if k not in patterns and _holds_four(word.value) and not _placed(word.value, tool, cwd):
                return False
        if not all(_placed_root(root.value, tool, cwd) for root in roots):
            return False
    return True


# --- D7: one copy or move INTO the crew dir, one closed shape --------------------

def _ps_cp_is_alias():
    """On a PowerShell payload `cp` and `mv` are Copy-Item / Move-Item only
    on Windows; elsewhere they are the native programs."""
    return os.name == "nt"


_D7_HEADS = {False: {"cp": "copy", "mv": "move"},
             True: {"copy-item": "copy", "move-item": "move", "cp": "copy", "mv": "move"}}
_D7_BASH_FLAGS = {"copy": re.compile(r"-[rRfpvani]+", re.ASCII), "move": re.compile(r"-[fvni]+", re.ASCII)}
_D7_PS_FLAGS = {"copy": ("-recurse", "-force"), "move": ("-force",)}
_D7_VARIABLE_RE = re.compile(r"\$[A-Za-z_][A-Za-z0-9_]*|\$\{[A-Za-z_][A-Za-z0-9_]*\}", re.ASCII)
_D7_PS_VARIABLE_RE = re.compile(r"\$(?:env:)?[A-Za-z_][A-Za-z0-9_]*|\$\{[A-Za-z_][A-Za-z0-9_]*\}",
                                re.ASCII)
_D7_LITERAL_RE = re.compile(r"[A-Za-z0-9_./][A-Za-z0-9_./-]*", re.ASCII)
_D7_PS_LITERAL_RE = re.compile(r"[A-Za-z0-9_./\\][A-Za-z0-9_./\\-]*", re.ASCII)
_D7_LAST_RE = re.compile(r"~/\.claude/crew(?:/[A-Za-z0-9_.-]+)+", re.IGNORECASE | re.ASCII)
_D7_PS_LAST_RE = re.compile(r"~[/\\]\.claude[/\\]crew(?:[/\\][A-Za-z0-9_.-]+)+", re.IGNORECASE | re.ASCII)


def _destination_only(reading, tool):
    """D7. True when the WHOLE reading is one copy or move into the crew dir,
    `<cp|mv> [<flag or source>...] ~/.claude/crew/<segment>[/<segment>...]`,
    every word matching its form in full. No quote, escape, glob, comma,
    separator or non-ASCII character is in any form, so the shell rewrites
    nothing and the last word is the destination."""
    if not isinstance(reading, str):
        return False
    ps = tool == "PowerShell"
    words = re.split(r"[ \t]+", reading.strip(" \t"))
    if len(words) < 2:
        return False
    head = words[0].lower() if ps else words[0]
    if ps and head in ("cp", "mv") and not _ps_cp_is_alias():
        return False
    kind = _D7_HEADS[ps].get(head)
    if kind is None:  # D7: only cp, mv, Copy-Item, Move-Item
        return False
    for word in words[1:-1]:
        if word.startswith("-"):
            if not _d7_flag(word, head, kind, ps):
                return False
        elif not _d7_source(word, ps):
            return False
    return _d7_last(words[-1], ps)


def _d7_flag(word, head, kind, ps):  # pylint: disable=unused-argument
    """A listed flag that takes no value: never a target, a destination or a
    source. The list is chosen by the tool, never by the spelling of `head`."""
    if ps:
        return word.lower() in _D7_PS_FLAGS[kind]
    return _D7_BASH_FLAGS[kind].fullmatch(word) is not None


def _d7_source(word, ps):
    """A plain variable or a literal, the whole word; never a mix of the two."""
    variable, literal = (_D7_PS_VARIABLE_RE, _D7_PS_LITERAL_RE) if ps else (_D7_VARIABLE_RE, _D7_LITERAL_RE)
    return bool(variable.fullmatch(word) or literal.fullmatch(word))


def _d7_last(word, ps):
    """`~/.claude/crew/<segment>...`, ending past the crew dir, no segment
    `.`/`..`, ending in `.`, or the store's name or a store child."""
    if not (_D7_PS_LAST_RE if ps else _D7_LAST_RE).fullmatch(word):
        return False
    for segment in re.split(r"[/\\]", word)[3:]:
        if segment in (".", "..") or segment.endswith("."):
            return False
        if _could_be(segment, STORE_NAME, 4) or any(_could_be(segment, c, 3) for c in _STORE_CHILDREN):
            return False
    return True

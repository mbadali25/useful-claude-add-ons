#!/usr/bin/env python3
"""crew's outbound notifier: one Python module behind notify.sh and notify.ps1.

Outbound only. Nothing here reads from a chat, nothing carries a reply back into
a session, and approvals stay a typed `/crew:approve`.

Three events send (T-0051, T-0060):

* `deploy` -- every `/crew:promote` result. A pass goes silent
  (`disable_notification`), a failure goes loud, and a result that says
  neither (no `--outcome`, a reason naming neither) goes loud as unknown.
* `question` -- Claude Code stopped and is waiting on the owner: the
  `Notification` hook, filtered on the payload's `notification_type`. An
  `idle_prompt` never pings.

* `blocker` (T-0060) -- work stopped and only the owner can move it. Loud,
  and one subject per kind: `Approval waiting` and `Lane stalled` / `Lane
  state unknown` from `run-stop` at `/crew:autopilot`'s report, `Review out
  of rounds` from `run-stop` (and `rounds_check`, for the review ledger), and
  `Stop gate refused` from `stop` (`stop_outcome`, for the Stop gates). A
  blocker with no kind, or one this module does not know, is `Blocked`.

The pre-1.0 names map in `notify.events`: `gate` -> `deploy`, `waiting` ->
`question`, `phase`/`review`/`done` -> `blocker`, each with a notice, never a
silent drop. A SEND under `phase`/`review`/`done` is a retired caller (the
per-phase and per-round pings T-0051 retired) and sends nothing, with a notice;
`gate` and `waiting` sends still map.

Every message is one line, led by a subject from `SUBJECTS`:

    <subject> [<repo>/<branch-or-ticket>] <ticket> (<phase>) <reason> -> <unblock>

A detached HEAD shows the ticket, never `HEAD`. A question's reason is the
payload's own `message` plus the first line of what Claude is waiting on, read
from `transcript_path` and passed through `redact`.

Measured 2026-09-30 on Claude Code 2.1.285 (a live `Notification` hook
capture): a Bash permission prompt AND an AskUserQuestion both arrive as
`permission_prompt` with the fixed message "Claude needs your permission" --
the message names neither the tool nor AskUserQuestion. So the tool is read
from the transcript: the last assistant line's pending `tool_use`. A message
that does name AskUserQuestion is still honoured.

Anti-spam: a fingerprint of event + ticket + reason is sent once per
`notify.realertHours` (default 6), and a question pings once per waiting
episode (`session_id` + `prompt_id`; approving a permission prompt does not
change `prompt_id`, only the owner's next typed message does). Both advance
ONLY on a confirmed send, under `<git-common-dir>/crew/notify/`.

Config: `crew_config.resolve_config` -- the machine-global `notify` block with
the repo layer over it; an explicit repo `"none"` opts out. The notify skill's
`~/.config/notify/config.json` `telegram` block fills a null `tokenEnv` /
`chatId`, read-only. The token is read from an environment variable only, and
`tokenEnv` and `urlEnv` (each a variable's NAME) are honoured from the
machine-global layer only: a repo's `.crew/config.json` could otherwise point
either at any variable (its settings `env` can set one) and pick the request URL.
Redirects are refused: a 3xx is a failed send, never a second request.

Every entry point exits 0. A reason goes to stderr when nothing was sent.

    crew_notify.py send --root . --event deploy --outcome fail --reason "<env> <sha> - FAILED at gate 3"
    crew_notify.py hook --root . < payload.json
    crew_notify.py config --root .
    crew_notify.py run-stop --root . --ticket <id> --phase <phase> --reason "<text>"
    crew_notify.py stop --root . --gate verify|audit --refused|--passed < payload.json
"""
import argparse
import datetime
import hashlib
import http.client
import json
import os
import re
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import crew_common  # noqa: E402  pylint: disable=wrong-import-position
import crew_config  # noqa: E402  pylint: disable=wrong-import-position
import crew_state  # noqa: E402  pylint: disable=wrong-import-position
import crew_ticket  # noqa: E402  pylint: disable=wrong-import-position

EVENTS = ("blocker", "deploy", "question")
# Accepted in notify.events, sending nothing: empty since T-0060 gave `blocker` a sender.
RESERVED = ()
# The blocker kinds (T-0060), each with its subject in SUBJECTS.
KINDS = ("approval", "rounds", "lane", "lane-unknown", "gate")
GATES = ("verify", "audit")
LEGACY = {"phase": "blocker", "review": "blocker", "done": "blocker",
          "gate": "deploy", "waiting": "question"}
QUESTION_TYPES = ("permission_prompt", "worker_permission_prompt", "elicitation_dialog",
                  "elicitation_url_dialog", "agent_needs_input")
# The types that are the owner being ASKED something rather than asked to allow a tool.
ASK_TYPES = ("elicitation_dialog", "elicitation_url_dialog", "agent_needs_input")
# Every other type Claude Code 2.1.285 is known to send. Quiet, and not logged:
# `unrecognised.log` is for a type nobody has classified yet.
QUIET_TYPES = ("idle_prompt", "auth_success", "agent_completed", "elicitation_complete",
               "elicitation_response", "quota_auto_resume_fired", "quota_auto_resume_stale",
               "quota_auto_resume_disabled", "push_notification", "computer_use_enter",
               "computer_use_exit")
# One table, plain ASCII, keyed by event and kind.
SUBJECTS = {
    ("blocker", "approval"): "Approval waiting",
    ("blocker", "rounds"): "Review out of rounds",
    ("blocker", "lane"): "Lane stalled",
    ("blocker", "lane-unknown"): "Lane state unknown",
    ("blocker", "gate"): "Stop gate refused",
    ("blocker", None): "Blocked",
    ("question", "ask"): "Question",
    ("question", "permission"): "Needs permission",
    ("deploy", "pass"): "Promotion passed",
    ("deploy", "fail"): "Deploy FAILED",
    ("deploy", "unknown"): "Promotion outcome unknown",
}
# The `notify` leaves honoured from the machine-global file ONLY, each with what it
# names: a repo's value is ignored with a notice (`effective_config`). Each names
# the variable whose value becomes the request URL. `crew_keys.layer_of` reads
# this table, so the configuration reference shows these keys as machine-only.
GLOBAL_ONLY_KEYS = {"tokenEnv": "(or the notify skill's config) names the token",
                    "urlEnv": "names the webhook URL"}
EXAMPLE_CHAT_ID = "-1001234567890"
# <digits>:<letters, digits, _ and ->. Anything else -- an inner space, a quote,
# two tokens pasted together -- cannot be a bot token.
_BOT_TOKEN = re.compile(r"\d+:[A-Za-z0-9_-]+")
MAX_REASON = 280
MAX_EXCERPT = 200
REALERT_HOURS = 6
PRUNE_SECONDS = 7 * 86400
SEND_BUDGET = 10.0
HTTP_TIMEOUT = 5.0
PACE_SECONDS = 1.0
LOCK_WAIT = 2.0
LOCK_STALE = 60.0
UNRECOGNISED_CAP = 200
BIG_TRANSCRIPT = 16 * 1024 * 1024
TAIL_BYTES = 256 * 1024
# None means `~/.config/notify/config.json`, resolved at call time; a test sets a path.
SKILL_CONFIG_PATH = None
TELEGRAM_BASE = "https://api.telegram.org"
# The only hosts CREW_NOTIFY_TELEGRAM_BASE may name: the bot token is in the URL path.
LOOPBACK_HOSTS = ("127.0.0.1", "::1", "localhost")

_SECRET_NAME = re.compile(r"TOKEN|SECRET|PASSWORD|PASS|KEY")
_SECRET_PATTERNS = (
    re.compile(r"\d{6,}:[A-Za-z0-9_-]{30,}"),
    re.compile(r"Bearer\s+\S+", re.IGNORECASE),
    re.compile(r"(?<![A-Za-z0-9])(?:sk-|ghp_|github_pat_|xox[abp]-)[A-Za-z0-9_-]{8,}"),
    re.compile(r"(?<![A-Za-z0-9])AKIA[A-Z0-9]{12,}"),
)


def redact(text):
    """`text` with every secret-shaped value replaced by `[redacted]`.

    A deny-list: the value of every environment variable whose name contains
    TOKEN, SECRET, PASSWORD, PASS or KEY (8+ characters), Telegram bot tokens,
    `Bearer <token>`, and `sk-`, `ghp_`, `github_pat_`, `xox[abp]-` and `AKIA`
    strings. The line and excerpt caps bound what a miss can leak."""
    out = "" if text is None else str(text)
    values = sorted({value for name, value in os.environ.items()
                     if _SECRET_NAME.search(name.upper()) and len(value) >= 8},
                    key=len, reverse=True)
    for value in values:
        out = out.replace(value, "[redacted]")
    for pattern in _SECRET_PATTERNS:
        out = pattern.sub("[redacted]", out)
    return out


def esc(text):
    """HTML-escape for Telegram's parse_mode=HTML (ported from the notify skill's tg.py)."""
    return (text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _say(message):
    print("crew-notify: " + redact(message), file=sys.stderr)


def _one_line(text):
    return re.sub(r"\s+", " ", str(text or "").replace("\r", " ").replace("\n", " ")).strip()


# --- state --------------------------------------------------------------------------------

def state_dir(root):
    """`<git-common-dir>/crew/notify`, or `<root>/.crew/notify` outside git."""
    common = crew_ticket.common_dir(root)
    if common:
        return os.path.join(common, "crew", "notify")
    return os.path.join(os.path.abspath(root), ".crew", "notify")


def _read_json(path):
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _read_stops(path):
    """`(stops, readable)`: a missing file is `({}, True)`; one that is there
    and does not parse to an object is `({}, False)`."""
    if not os.path.lexists(path):
        return {}, True
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return {}, False
    return (data, True) if isinstance(data, dict) else ({}, False)


def _stop_entry_ok(entry):
    return (isinstance(entry, dict) and isinstance(entry.get("at"), (int, float))
            and not isinstance(entry.get("at"), bool) and isinstance(entry.get("ids"), list)
            and all(isinstance(i, str) for i in entry["ids"]))


def _write_json(path, data):
    """Temp file + os.replace: a reader never sees half a file. Every value is
    redacted on the way out, so no secret reaches the state directory."""
    text = redact(json.dumps(data, sort_keys=True))
    directory = os.path.dirname(path)
    os.makedirs(directory, exist_ok=True)
    handle, temp = tempfile.mkstemp(prefix=".tmp-", dir=directory)
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as out:
            out.write(text)
        os.replace(temp, path)
    except OSError:
        try:
            os.remove(temp)
        except OSError:
            pass
        raise


def _log_unrecognised(root, ntype):
    """One line per unknown or missing `notification_type`, capped at 200 lines."""
    try:
        path = os.path.join(state_dir(root), "unrecognised.log")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        label = _one_line(ntype)[:80] if isinstance(ntype, str) and ntype else "MISSING"
        stamp = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
        try:
            with open(path, encoding="utf-8") as handle:
                lines = handle.read().splitlines()
        except OSError:
            lines = []
        lines = (lines + [redact(f"{stamp} {label}")])[-UNRECOGNISED_CAP:]
        text = "\n".join(lines) + "\n"
        handle, temp = tempfile.mkstemp(prefix=".tmp-", dir=os.path.dirname(path))
        with os.fdopen(handle, "w", encoding="utf-8") as out:
            out.write(text)
        os.replace(temp, path)
    except OSError as exc:
        _say(f"could not write unrecognised.log: {exc.__class__.__name__}")


class _Lock:
    """An O_CREAT|O_EXCL lock file. `held` is False when it could not be had
    inside LOCK_WAIT; the caller then sends without dedupe and says so."""

    def __init__(self, path):
        self.path = path
        self.held = False

    def __enter__(self):
        deadline = time.monotonic() + LOCK_WAIT
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
        except OSError:
            return self
        while True:
            try:
                os.close(os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600))
                self.held = True
                return self
            except FileExistsError:
                try:
                    if time.time() - os.path.getmtime(self.path) > LOCK_STALE:
                        os.remove(self.path)
                        continue
                except OSError:
                    pass
            except OSError:
                return self
            if time.monotonic() >= deadline:
                return self
            time.sleep(0.05)

    def __exit__(self, *_exc):
        if self.held:
            try:
                os.remove(self.path)
            except OSError:
                pass


# --- config --------------------------------------------------------------------------------

def _skill_telegram():
    """The notify skill's `telegram` block, or {} on any read error."""
    path = SKILL_CONFIG_PATH or os.path.join(
        os.path.expanduser("~"), ".config", "notify", "config.json")
    block = _read_json(path).get("telegram")
    return block if isinstance(block, dict) else {}


def _events(raw, notices):
    if raw is None:
        return list(RESERVED + EVENTS)
    if isinstance(raw, str):
        raw = [part.strip() for part in raw.split(",") if part.strip()]
    if not isinstance(raw, list):
        notices.append("notify.events is not a list; using the default "
                       f"{list(RESERVED + EVENTS)}")
        return list(RESERVED + EVENTS)
    out = []
    for name in raw:
        if name in EVENTS or name in RESERVED:
            mapped = name
        elif name in LEGACY:
            mapped = LEGACY[name]
            notices.append(f"notify.events: legacy '{name}' read as '{mapped}'")
        else:
            notices.append(f"notify.events: unknown event {name!r} dropped")
            continue
        if mapped not in out:
            out.append(mapped)
    return out


def effective_config(root):
    """`(cfg, notices)`: the `notify` block this repo runs with, and one line per
    thing worth saying about how it was reached."""
    notices = []
    try:
        cfg = dict(crew_config.resolve_config(root).get("notify") or {})
    except Exception as exc:  # pylint: disable=broad-except
        notices.append(f"config unreadable ({exc.__class__.__name__}); notify is off")
        cfg = {}
    repo = crew_state.load_config(root).get("notify")
    repo = repo if isinstance(repo, dict) else {}
    try:
        global_cfg, _ = crew_config.filter_global(crew_config.read_global_config())
    except Exception:  # pylint: disable=broad-except
        global_cfg = {}
    global_notify = global_cfg.get("notify") if isinstance(global_cfg.get("notify"), dict) else {}
    global_provider = global_notify.get("provider")
    # tokenEnv / urlEnv name the variable whose value becomes the request URL (the
    # bot token in its path, the Teams webhook itself): only the owner's own
    # machine-global file may name either, never a cloned repo's config.
    for key, names in GLOBAL_ONLY_KEYS.items():
        global_env = global_notify.get(key)
        cfg[key] = global_env if isinstance(global_env, str) and global_env else None
        if repo.get(key) is not None and repo.get(key) != cfg[key]:
            notices.append(f"the repo's notify.{key} is ignored: only the machine-global "
                           f"~/.claude/crew/config.json {names}")
    if repo.get("provider") == "none" and global_provider not in (None, "none"):
        notices.append(f"the repo's notify.provider \"none\" overrides the global provider "
                       f"'{global_provider}' (a repo opt-out)")
    if cfg.get("provider") == "telegram" and (cfg.get("tokenEnv") is None
                                              or cfg.get("chatId") is None):
        skill = _skill_telegram()
        if cfg.get("tokenEnv") is None and isinstance(skill.get("bot_token_env"), str):
            cfg["tokenEnv"] = skill["bot_token_env"]
            notices.append("notify.tokenEnv taken from the notify skill's config")
        if cfg.get("chatId") is None and isinstance(skill.get("chat_id"), (str, int)):
            cfg["chatId"] = str(skill["chat_id"])
            notices.append("notify.chatId taken from the notify skill's config")
    if cfg.get("chatId") is not None and str(cfg.get("chatId")) == EXAMPLE_CHAT_ID:
        cfg["chatId"] = None
        notices.append(f"notify.chatId {EXAMPLE_CHAT_ID} is the notify skill's example value; "
                       "treated as unset")
    cfg["events"] = _events(cfg.get("events"), notices)
    hours = cfg.get("realertHours")
    if isinstance(hours, bool) or not isinstance(hours, (int, float)) or hours < 0:
        cfg["realertHours"] = REALERT_HOURS
    types = cfg.get("questionTypes")
    cfg["questionTypes"] = (tuple(t for t in types if isinstance(t, str))
                            if isinstance(types, list) else None)
    return cfg, notices


# --- classification and context -----------------------------------------------------------

def classify(payload, question_types=None, pending_tool=None):
    """`("question", type, subject)`, `("quiet", type, None)` or `("unknown", None, None)`.

    `pending_tool` is the tool the transcript's last assistant line is waiting
    on: a `permission_prompt` for AskUserQuestion carries no tool name in its
    message (measured, Claude Code 2.1.285), so that is how it is told apart."""
    ntype = payload.get("notification_type") if isinstance(payload, dict) else None
    if not isinstance(ntype, str) or not ntype:
        return ("unknown", None, None)
    if ntype not in (question_types or QUESTION_TYPES):
        return ("quiet", ntype, None)
    message = payload.get("message")
    asked = (ntype in ASK_TYPES
             or (isinstance(message, str) and "AskUserQuestion" in message)
             or pending_tool == "AskUserQuestion")
    return ("question", ntype, SUBJECTS[("question", "ask" if asked else "permission")])


def _transcript_lines(path):
    size = os.path.getsize(path)
    with open(path, "rb") as handle:
        if size > BIG_TRANSCRIPT:
            handle.seek(size - TAIL_BYTES)
            data = handle.read()
            data = data.split(b"\n", 1)[1] if b"\n" in data else b""
        else:
            data = handle.read()
    return data.decode("utf-8", "replace").splitlines()


def _first_line(text):
    for line in str(text or "").splitlines():
        if line.strip():
            return _one_line(line)
    return ""


def context(transcript_path):
    """`{"excerpt", "tool", "uuid"}` from the transcript's last assistant line that
    says something: the pending AskUserQuestion's first question, else another
    pending tool's name (and its `description`), else the last text. First line
    only, redacted, then capped. Any failure gives empty values and a stderr note."""
    empty = {"excerpt": "", "tool": None, "uuid": None}
    if not isinstance(transcript_path, str) or not transcript_path:
        return empty
    try:
        lines = _transcript_lines(transcript_path)
    except (OSError, ValueError) as exc:
        _say(f"transcript unreadable ({exc.__class__.__name__}); sending the message alone")
        return empty
    for raw in reversed(lines):
        try:
            item = json.loads(raw)
        except ValueError:
            continue
        if not isinstance(item, dict) or item.get("type") != "assistant":
            continue
        message = item.get("message")
        content = message.get("content") if isinstance(message, dict) else None
        if not isinstance(content, list):
            continue
        uses = [c for c in content if isinstance(c, dict) and c.get("type") == "tool_use"]
        texts = [c.get("text") for c in content
                 if isinstance(c, dict) and c.get("type") == "text"
                 and isinstance(c.get("text"), str) and c.get("text").strip()]
        excerpt, tool = "", None
        asks = [u for u in uses if u.get("name") == "AskUserQuestion"]
        if asks:
            tool = "AskUserQuestion"
            try:
                excerpt = asks[-1]["input"]["questions"][0]["question"]
            except (KeyError, IndexError, TypeError):
                excerpt = ""
        elif uses:
            tool = uses[-1].get("name") if isinstance(uses[-1].get("name"), str) else None
            args = uses[-1].get("input")
            described = args.get("description") if isinstance(args, dict) else None
            excerpt = (tool or "") + (f": {described}" if isinstance(described, str) else "")
        elif texts:
            excerpt = texts[-1]
        else:
            continue
        uuid = item.get("uuid") if isinstance(item.get("uuid"), str) else None
        return {"excerpt": redact(_first_line(excerpt))[:MAX_EXCERPT], "tool": tool, "uuid": uuid}
    return empty


# --- the line -------------------------------------------------------------------------------

def _phase(top, ticket):
    if not ticket:
        return ""
    text = crew_state.read_text(os.path.join(top, ".work", "INDEX.md")) or ""
    for line in text.splitlines():
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) >= 2 and cells[0] == ticket:
            return cells[1]
    return ""


def where(root):
    """`{"repo", "place", "ticket", "phase"}`. `place` is the branch, or on a
    detached HEAD the ticket (or `detached`), never `HEAD`; None outside git."""
    top = crew_ticket.toplevel(root) or os.path.abspath(root)
    ticket = None
    try:
        ticket, _ = crew_ticket.active_ticket(root)
    except Exception:  # pylint: disable=broad-except
        ticket = None
    branch = crew_state.current_branch(root)
    if branch:
        place = branch
    elif crew_state.in_git_repo(root):
        place = ticket or "detached"
    else:
        place = None
    return {"repo": os.path.basename(top.rstrip("/\\")) or "repo", "place": place,
            "ticket": ticket, "phase": _phase(top, ticket)}


def format_line(subject, repo, place, ticket, phase, reason, unblock):
    """`<subject> [<repo>/<place>] <ticket> (<phase>) <reason> -> <unblock>`, one
    line, missing parts left out, the reason cut to MAX_REASON."""
    head = f"[{_one_line(repo)}/{_one_line(place)}]" if place else f"[{_one_line(repo)}]"
    parts = [_one_line(subject), head, _one_line(ticket),
             f"({_one_line(phase)})" if phase else "",
             _one_line(reason)[:MAX_REASON],
             f"-> {_one_line(unblock)}" if unblock else ""]
    return " ".join(part for part in parts if part)


# --- transports -----------------------------------------------------------------------------

def telegram_base():
    """`TELEGRAM_BASE`, or CREW_NOTIFY_TELEGRAM_BASE (for tests) when its scheme is
    http(s) and its host is exactly a loopback name. Rebuilt from the parsed parts,
    so what was checked is what is dialled. Anything else is ignored, with a note:
    the bot token rides in the URL path, so a cloned repo's settings `env` must
    not be able to send it to another host."""
    override = os.environ.get("CREW_NOTIFY_TELEGRAM_BASE")
    if not override:
        return TELEGRAM_BASE
    try:
        parts = urllib.parse.urlsplit(override)
        host, port = parts.hostname, parts.port
    except ValueError:
        host, port, parts = None, None, None
    if parts is None or parts.scheme not in ("http", "https") or host not in LOOPBACK_HOSTS:
        _say("CREW_NOTIFY_TELEGRAM_BASE is not a loopback http(s) URL; ignored")
        return TELEGRAM_BASE
    netloc = f"[{host}]" if ":" in host else host
    return f"{parts.scheme}://{netloc}" + (f":{port}" if port else "") + parts.path


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Follow no redirect: a 3xx surfaces as an HTTPError (a failed send). urllib
    would otherwise re-send to the Location -- a GET carrying the token in its path."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # pylint: disable=too-many-arguments,too-many-positional-arguments
        return None


def _open(request):
    """`urlopen` with redirects refused; the one way this module sends."""
    return urllib.request.build_opener(_NoRedirect).open(request, timeout=HTTP_TIMEOUT)


def _telegram(token, chat, text, loud):
    """POST sendMessage. `(ok, why)`; ok only on HTTP 200 with `ok: true`. A 429's
    `retry_after` is honoured once (0 means at once) unless the wait would push
    the send past SEND_BUDGET. `why` never carries the URL: the token is in it.
    `telegram_base` decides the host: api.telegram.org, or a loopback test server."""
    base = telegram_base()
    url = f"{base.rstrip('/')}/bot{token}/sendMessage"
    data = urllib.parse.urlencode({"chat_id": chat, "text": esc(text), "parse_mode": "HTML",
                                   "disable_notification": "false" if loud else "true"}).encode()
    started = time.monotonic()
    for attempt in (0, 1):
        try:
            with _open(urllib.request.Request(url, data=data)) as response:
                status, body = response.status, response.read()
        except urllib.error.HTTPError as exc:
            try:
                out = json.loads(exc.read().decode("utf-8", "replace"))
            except (ValueError, OSError):
                out = {}
            params = out.get("parameters") if isinstance(out, dict) else None
            retry_after = params.get("retry_after") if isinstance(params, dict) else None
            if exc.code == 429 and attempt == 0:
                # 'is not None', not truthiness: retry_after 0 means retry at once.
                wait = float(retry_after) if retry_after is not None else PACE_SECONDS
                if time.monotonic() - started + wait > SEND_BUDGET:
                    return False, "429 retry_after over the send budget"
                time.sleep(wait)
                continue
            return False, f"HTTP {exc.code}" + _because(out)
        except http.client.InvalidURL:
            # Its message quotes the request path, token included: never pass it on.
            return False, "the bot token is not usable in a URL"
        except (urllib.error.URLError, OSError, ValueError) as exc:
            return False, f"network error ({exc.__class__.__name__})"
        try:
            out = json.loads(body.decode("utf-8", "replace"))
        except ValueError:
            return False, "response is not JSON"
        if status == 200 and isinstance(out, dict) and out.get("ok") is True:
            return True, "ok"
        return False, "ok: false" + _because(out)
    return False, "429 twice"


def _because(reply):
    """`: <Telegram's description>` -- "Bad Request: chat not found",
    "Unauthorized" -- or nothing. The status alone never said which setting
    was wrong."""
    why = reply.get("description") if isinstance(reply, dict) else None
    return f": {redact(_one_line(why))[:120]}" if isinstance(why, str) and why.strip() else ""


def _teams(url, text):
    body = json.dumps({"type": "message", "attachments": [{
        "contentType": "application/vnd.microsoft.card.adaptive",
        "content": {"type": "AdaptiveCard", "version": "1.4",
                    "body": [{"type": "TextBlock", "text": text, "wrap": True}]}}]}).encode()
    request = urllib.request.Request(url, data=body,
                                     headers={"Content-Type": "application/json"})
    try:
        with _open(request) as response:
            status = response.status
    except urllib.error.HTTPError as exc:
        return False, f"HTTP {exc.code}"
    except (urllib.error.URLError, OSError, ValueError) as exc:
        return False, f"network error ({exc.__class__.__name__})"
    return (200 <= status < 300), f"HTTP {status}"


def _pace(state, chat_key):
    """Sleep until PACE_SECONDS have passed since this chat's last confirmed send."""
    last = _read_json(os.path.join(state, "last-send")).get(chat_key)
    if isinstance(last, (int, float)):
        gap = time.time() - last
        if 0 <= gap < PACE_SECONDS:
            time.sleep(PACE_SECONDS - gap)


def _pruned(mapping, now):
    return {key: value for key, value in mapping.items()
            if isinstance(value, (int, float)) and now - value < PRUNE_SECONDS}


# --- send and hook --------------------------------------------------------------------------

def _outcome(outcome, reason):
    """`pass`, `fail`, or `unknown`. With no explicit outcome the reason decides,
    and only when it says exactly one of pass / fail: a reason that says neither
    (or both) is `unknown`, never collapsed into a pass."""
    if outcome in ("pass", "fail"):
        return outcome
    failed = re.search(r"fail", reason or "", re.IGNORECASE)
    passed = re.search(r"(?<![A-Za-z])pass(?:ed)?(?![A-Za-z])", reason or "", re.IGNORECASE)
    if bool(failed) == bool(passed):
        return "unknown"
    return "fail" if failed else "pass"


def _credentials(cfg):
    """`(provider, token, target, None)`, or `(provider, None, None, word)` when
    nothing can be sent (`missing-credentials` or `off`), the reason said."""
    provider = cfg.get("provider")
    # Every credential is stripped: a token set with a trailing space or newline
    # (setx, a paste, the System Properties dialog) put it inside the URL, and the
    # send failed as a bare `failed (InvalidURL)` (2026-10-05, a Windows host).
    # And each missing value is named, with where it is read from: "token env or
    # chatId missing" sent the owner to set a chat id that was already there.
    if provider == "telegram":
        token_env = cfg.get("tokenEnv")
        token_env = token_env.strip() if isinstance(token_env, str) else ""
        token = (os.environ.get(token_env) or "").strip() if token_env else ""
        target = str(cfg.get("chatId")).strip() if cfg.get("chatId") is not None else ""
        if not token_env:
            _say("telegram notify.tokenEnv is not set in ~/.claude/crew/config.json or the notify "
                 "skill's bot_token_env (a repo's notify.tokenEnv is ignored); nothing sent")
            return provider, None, None, "missing-credentials"
        if not token:
            _say(f"telegram token missing: ${token_env} is empty or unset in this process's "
                 "environment; nothing sent")
            return provider, None, None, "missing-credentials"
        if not _BOT_TOKEN.fullmatch(token):
            _say(f"${token_env} does not look like a Telegram bot token (<digits>:<letters>); "
                 "nothing sent")
            return provider, None, None, "missing-credentials"
        if not target:
            _say("telegram chatId missing: set notify.chatId in this repo's crew config or the "
                 "machine-global one; nothing sent")
            return provider, None, None, "missing-credentials"
    elif provider == "teams":
        url_env = cfg.get("urlEnv")
        url_env = url_env.strip() if isinstance(url_env, str) else ""
        target = (os.environ.get(url_env) or "").strip() if url_env else ""
        token = None
        if not target:
            _say(f"teams url env ${url_env} not set; nothing sent")
            return provider, None, None, "missing-credentials"
    else:
        _say(f"unknown notify.provider {provider!r}; nothing sent")
        return provider, None, None, "off"

    return provider, token, target, None


# pylint: disable-next=too-many-arguments,too-many-positional-arguments
def _already_sent(root, cfg, event, reason, ticket, episode, dedupe):
    """Whether `_deliver` would send nothing for this ping as one already sent
    (the same waiting episode, or the same message inside realertHours), read
    without a lock: a held ping is then not counted (L-0656 review r3)."""
    state = state_dir(root)
    if episode:
        seen = _read_json(os.path.join(state, "episodes.json")).get(episode[0])
        if isinstance(seen, dict) and seen.get("key") == episode[1]:
            return True
    material = "|".join([event, ticket or where(root)["ticket"] or "", reason]
                        + (list(episode) if episode else []) + ([str(dedupe)] if dedupe else []))
    at = _read_json(os.path.join(state, "sent.json")).get(
        hashlib.sha256(material.encode("utf-8")).hexdigest())
    window = float(cfg.get("realertHours", REALERT_HOURS)) * 3600
    return isinstance(at, (int, float)) and time.time() - at < window


def _deliver(root, cfg, event, reason, ticket, unblock, kind, episode, dedupe=None):
    """Everything after the filters: credentials, line, episode, dedupe, transport."""
    provider, token, target, stop = _credentials(cfg)
    if stop:
        return stop
    place = where(root)
    ticket = ticket or place["ticket"]
    phase = place["phase"] if ticket == place["ticket"] else ""
    subject = SUBJECTS[(event, kind)]
    line = redact(format_line(subject, place["repo"], place["place"], ticket, phase,
                              redact(reason), unblock))
    loud = event in ("question", "blocker") or kind in ("fail", "unknown")

    state = state_dir(root)
    now = time.time()
    episodes = {}
    if episode:
        episodes = _read_json(os.path.join(state, "episodes.json"))
        seen = episodes.get(episode[0])
        if isinstance(seen, dict) and seen.get("key") == episode[1]:
            _say("same waiting episode as the last ping (no reply since); nothing sent")
            return "episode"
    # `dedupe` is episode material that is never shown (a plan hash, a round
    # number): a NEW blocker episode with the same words is not the old one.
    material = "|".join([event, ticket or "", reason] + (list(episode) if episode else [])
                        + ([str(dedupe)] if dedupe else []))
    fingerprint = hashlib.sha256(material.encode("utf-8")).hexdigest()
    window = float(cfg.get("realertHours", REALERT_HOURS)) * 3600

    with _Lock(os.path.join(state, "sent.lock")) as lock:
        sent = _read_json(os.path.join(state, "sent.json")) if lock.held else {}
        if not lock.held:
            _say("state lock busy; sending without dedupe")
        at = sent.get(fingerprint)
        if isinstance(at, (int, float)) and now - at < window:
            _say(f"same message sent inside notify.realertHours ({cfg.get('realertHours')}h); "
                 "nothing sent")
            return "deduped"
        chat_key = hashlib.sha256(str(target).encode()).hexdigest()[:16]
        _pace(state, chat_key)
        if provider == "telegram":
            ok, why = _telegram(token, target, line, loud)
        else:
            ok, why = _teams(target, line)
        if not ok:
            _say(f"send failed: {why}")
            return f"failed:{why}"
        if lock.held:
            try:
                stamp = time.time()
                sent = _pruned(sent, stamp)
                sent[fingerprint] = stamp
                _write_json(os.path.join(state, "sent.json"), sent)
                last = _read_json(os.path.join(state, "last-send"))
                last[chat_key] = stamp
                _write_json(os.path.join(state, "last-send"), last)
                if episode:
                    episodes = {key: value for key, value in episodes.items()
                                if isinstance(value, dict)
                                and isinstance(value.get("at"), (int, float))
                                and stamp - value["at"] < PRUNE_SECONDS}
                    episodes[episode[0]] = {"key": episode[1], "at": stamp}
                    _write_json(os.path.join(state, "episodes.json"), episodes)
            except OSError as exc:
                _say(f"sent, but state not written ({exc.__class__.__name__})")
    return "sent"


def _filter(cfg, event):
    """`(event, result_or_None)`: the mapped event, or the word to return."""
    if event in LEGACY and LEGACY[event] == "blocker":
        _say(f"legacy '{event}' is a retired caller (its per-phase or per-round ping was "
             "retired in T-0051; blocker sends with a --kind); nothing sent")
        return LEGACY[event], "filtered"
    if event in LEGACY:
        _say(f"legacy '{event}' read as '{LEGACY[event]}'")
        event = LEGACY[event]
    if event in RESERVED:
        _say(f"'{event}' is reserved; nothing sent")
        return event, "filtered"
    if event not in EVENTS:
        _say(f"unknown event {event!r}; nothing sent")
        return event, "filtered"
    provider = cfg.get("provider")
    if not provider or provider == "none":
        _say("notify.provider is none; nothing sent")
        return event, "off"
    if event not in cfg.get("events", ()):
        _say(f"'{event}' is not in notify.events; nothing sent")
        return event, "filtered"
    return event, None


def send(root, event, reason, ticket=None, unblock=None, outcome=None, kind=None,
         episode=None, cfg=None, dedupe=None):
    """Send one message. Returns `sent`, `deduped`, `episode`, `off`, `filtered`,
    `held` (asleep, L-0656: crew_notify_hold.py), `missing-credentials` or
    `failed:<why>`; never raises."""
    try:
        if cfg is None:
            cfg, notices = effective_config(root)
            for notice in notices:
                _say(notice)
        event, stop = _filter(cfg, event)
        if stop:
            return stop
        reason = str(reason or "")
        if event == "deploy":
            kind = _outcome(outcome, reason)
        elif event == "blocker":
            kind = kind if kind in KINDS else None
        elif kind not in ("ask", "permission"):
            kind = "ask"
        import crew_notify_hold  # pylint: disable=import-outside-toplevel  # L-0656, imports this
        if (event, kind) in crew_notify_hold.HOLDABLE:  # L-0656 review r4: config failures surface
            stop = _credentials(cfg)[3]
            if stop:
                return stop
            if not _already_sent(root, cfg, event, reason, ticket, episode, dedupe) and \
                    crew_notify_hold.holds(root, event, kind, "|".join(
                        [ticket or where(root)["ticket"] or "", reason, repr(episode),
                         str(dedupe or "")])):
                return "held"
        return _deliver(root, cfg, event, reason, ticket, unblock, kind, episode, dedupe)
    except Exception as exc:  # pylint: disable=broad-except
        _say(f"failed ({exc.__class__.__name__})")
        return "failed:error"


def hook(root, payload_bytes):
    """The `Notification` hook: classify the payload and send a `question` for
    the question types only. Returns the result word, or `quiet`; never raises."""
    try:
        try:
            payload = json.loads((payload_bytes or b"").decode("utf-8", "replace"))
        except ValueError:
            payload = None
        if not isinstance(payload, dict):
            _say("no JSON payload on stdin; nothing sent")
            _log_unrecognised(root, None)
            return "quiet"
        cfg, notices = effective_config(root)
        for notice in notices:
            _say(notice)
        found, ntype, _ = classify(payload, cfg.get("questionTypes"))
        if found != "question":
            if found == "unknown" or ntype not in QUESTION_TYPES + QUIET_TYPES:
                _log_unrecognised(root, ntype)
            _say(f"notification_type {ntype or 'MISSING'} is not a question; nothing sent")
            return "quiet"
        ctx = context(payload.get("transcript_path"))
        _, _, subject = classify(payload, cfg.get("questionTypes"), ctx["tool"])
        kind = "ask" if subject == SUBJECTS[("question", "ask")] else "permission"
        message = _one_line(redact(payload.get("message") or ""))
        reason = message + (f" - {ctx['excerpt']}" if ctx["excerpt"] and message
                            else ctx["excerpt"])
        session = payload.get("session_id")
        key = payload.get("prompt_id") or (f"uuid:{ctx['uuid']}" if ctx["uuid"] else None)
        episode = (str(session), str(key)) if session and key else None
        return send(root, "question", reason, kind=kind, episode=episode, cfg=cfg)
    except Exception as exc:  # pylint: disable=broad-except
        _say(f"hook failed ({exc.__class__.__name__})")
        return "failed:error"


# --- the blocker reasons (T-0060) ---------------------------------------------------------------

# The autopilot stops whose ping is decided here. Every other phase is filtered:
# `done`, `max-phases`, no-progress, `handover-elsewhere` and a live holder are
# not blockers.
ROUNDS_PHASES = ("accept-review", "replan", "auto-replan-cap")


def rounds_check(root, ticket):
    """`blocker` kind `rounds` when the review ledger's current plan has spent
    the last of its budget and its latest completed round carries a BLOCK;
    otherwise `filtered`. Read-only on the ledger; never raises. The review
    ledger calls this after `record` once its harness-only wiring lands, and
    `run_stop` calls it at autopilot's accept-review and replan stops."""
    try:
        import review_ledger  # pylint: disable=import-outside-toplevel
        ledger = review_ledger.status(root, ticket)
        spent, budget = ledger.get("rounds_spent"), ledger.get("budget")
        successors = ledger.get("successors") or []
        after = successors[-1].get("after_round", 0) if successors else 0
        rounds = (ledger.get("rounds") or [])[after if isinstance(after, int) else 0:]
        done = [r for r in rounds if isinstance(r, dict) and r.get("status") == "completed"]
        counts = done[-1].get("counts") if done else None
        number = done[-1].get("round") if done else None
        block = counts.get("BLOCK") if isinstance(counts, dict) else None
    except Exception as exc:  # pylint: disable=broad-except
        _say(f"review ledger unreadable ({exc.__class__.__name__}); no rounds ping")
        return "filtered"
    if not (isinstance(spent, int) and isinstance(budget, int) and spent >= budget):
        return "filtered"
    if isinstance(block, bool) or not isinstance(block, int) or block < 1:
        return "filtered"
    return send(root, "blocker", f"out of review rounds, {block} BLOCK open", ticket=ticket,
                unblock=f"/crew:plan {ticket}", kind="rounds", dedupe=f"round:{number}")


# What a `holds()` "unknown" may say in the chat: a fixed category, never its
# `why`, which carries absolute paths and exception text (the home directory, the
# user name). The detail is local: `/crew:status` prints it.
_UNKNOWN_CATEGORIES = (("heartbeat in the future", "heartbeat in the future"),
                       ("lock ", "lock held"), ("marker", "marker unreadable"))


def _category(why):
    """The fixed category for an unknown holder's `why`."""
    text = _one_line(why)
    for needle, category in _UNKNOWN_CATEGORIES:
        if text.startswith(needle):
            return category
    return "could not read state"


def _lane(root, ticket):
    """The in-flight stop: read T-0049's `holds()` and ping a stale or unknown
    holder. Writes nothing under the inflight directory."""
    try:
        import crew_inflight  # pylint: disable=import-outside-toplevel
        answer = crew_inflight.holds(root, ticket, runner="autopilot")
        state = answer.get("state") if isinstance(answer, dict) else None
    except Exception as exc:  # pylint: disable=broad-except
        _say(f"crew_inflight failed ({exc.__class__.__name__}); lane state unknown")
        answer, state = {}, "unknown"
    if state in ("live", "mine", "free", "elsewhere"):
        return "filtered"
    if state == "stale":
        return send(root, "blocker", f"lane stalled: {answer.get('runner') or 'a runner'} since "
                    f"{answer.get('since') or '?'}", ticket=ticket,
                    unblock=answer.get("clear") or "/crew:status", kind="lane")
    category = _category(answer.get("why") or "")
    return send(root, "blocker", f"lane state unknown: {category} (detail: /crew:status)",
                ticket=ticket, unblock="/crew:status", kind="lane-unknown")


def _plan_digest(root, ticket, name="plan.md"):
    """The approval episode: the sha256 of the ticket's `plan.md` (or, for a
    split, `split.md`), so a successor plan or decision (or an edit that
    staled the receipt) waiting again is a new ping."""
    top = crew_ticket.toplevel(root) or os.path.abspath(root)
    label = name.split(".", 1)[0]
    folder = crew_common.locate_ticket(top, ticket)[0]  # L-0509: live or archived
    if folder is None:
        return f"{label}:none"
    try:
        with open(os.path.join(folder, name), "rb") as handle:
            return f"{label}:" + hashlib.sha256(handle.read()).hexdigest()
    except OSError:
        return f"{label}:none"


def run_stop(root, ticket, phase, reason):
    """Decide whether `/crew:autopilot`'s stop pings. `approve` (a stale receipt
    included) and T-0058's `split-approval` are `Approval waiting`; `in-flight`
    reads the holder; an
    `accept-review`, `replan` or `auto-replan-cap` stop with the budget spent
    and a BLOCK open is
    `Review out of rounds`. Every other phase is `filtered`. Never raises."""
    try:
        try:
            crew_ticket.check_ticket(ticket)
        except Exception:  # pylint: disable=broad-except
            _say(f"run-stop: {ticket!r} is not a ticket id; nothing sent")
            return "failed:usage"
        # Logged locally, never sent: the message is this module's own words.
        _say(f"run-stop {ticket} {phase or '-'}: {_one_line(reason)[:MAX_REASON]}")
        if phase == "approve":
            return send(root, "blocker", "plan waiting on approval", ticket=ticket,
                        unblock=f"/crew:approve {ticket}", kind="approval",
                        dedupe=_plan_digest(root, ticket))
        if phase == "split-approval":
            # T-0058: a split decision autopilot may not apply waits on the owner.
            return send(root, "blocker", "split waiting on the owner", ticket=ticket,
                        unblock=f"/crew:split {ticket}", kind="approval",
                        dedupe=_plan_digest(root, ticket, "split.md"))
        if phase == "in-flight":
            return _lane(root, ticket)
        if phase in ROUNDS_PHASES:
            return rounds_check(root, ticket)
        return "filtered"
    except Exception as exc:  # pylint: disable=broad-except
        _say(f"run-stop failed ({exc.__class__.__name__})")
        return "failed:error"


def _stop_identity(payload, raw):
    """`prompt_id` when the payload has one, else the digest of the bytes both
    Windows flavours agree on (event_claim.normalise)."""
    prompt = payload.get("prompt_id") if isinstance(payload, dict) else None
    if isinstance(prompt, str) and prompt:
        return "prompt:" + prompt
    import event_claim  # pylint: disable=import-outside-toplevel
    return "sha256:" + hashlib.sha256(event_claim.normalise(raw or b"")).hexdigest()


def stop_outcome(root, gate, refused, payload_bytes):
    """Record one Stop gate verdict. A pass clears the (gate, session, ticket)
    key; a refusal adds its identity, a twin (the same identity: both Windows
    flavours) changes nothing, and the second distinct refusal in a row sends
    `blocker` kind `gate`. Returns `cleared`, `counted`, `twin`, `busy`, or a
    send's word; never raises."""
    try:
        if gate not in GATES:
            _say(f"unknown gate {gate!r}; nothing recorded")
            return "failed:usage"
        raw = payload_bytes or b""
        try:
            import event_claim  # pylint: disable=import-outside-toplevel
            payload = json.loads(event_claim.normalise(raw).decode("utf-8", "replace"))
        except ValueError:
            payload = None
        payload = payload if isinstance(payload, dict) else {}
        try:
            ticket = crew_ticket.resolve_active(root)[0]
        except Exception:  # pylint: disable=broad-except
            ticket = None
        session = payload.get("session_id") if isinstance(payload.get("session_id"), str) else ""
        key = f"{gate}|{session or 'nosession'}|{ticket or 'no-ticket'}"
        ident = _stop_identity(payload, raw)
        path = os.path.join(state_dir(root), "stops.json")
        with _Lock(os.path.join(state_dir(root), "stops.lock")) as lock:
            if not lock.held:
                _say("stops lock busy; this verdict is not counted")
                return "busy"
            now = time.time()
            raw_stops, readable = _read_stops(path)
            mine = raw_stops.get(key)
            # A history that is there and cannot be read (or this key's entry
            # out of shape) cannot say whether this refusal is the second:
            # unknown, never a fresh streak.
            unknown = not readable or (mine is not None and not _stop_entry_ok(mine))
            stops = {name: entry for name, entry in raw_stops.items()
                     if _stop_entry_ok(entry) and now - entry["at"] < PRUNE_SECONDS}
            if not refused:
                stops.pop(key, None)
                _write_json(path, stops)
                return "cleared"
            if unknown:
                stops[key] = {"ids": [ident], "first": ident, "at": now}
                _write_json(path, stops)
                _say("stops.json is unreadable or out of shape: whether this refusal is "
                     "the second cannot be told; pinging, and the streak restarts here")
                return send(root, "blocker", f"{gate} gate refused (refusal history "
                            "unreadable)", ticket=ticket, unblock="/crew:status",
                            kind="gate", dedupe=ident)
            entry = stops.get(key) or {}
            seen = entry.get("ids") or []
            if ident in seen:
                return "twin"
            # `first` is kept apart from the bounded `ids` window, so the
            # streak keeps one identity however long it runs.
            first = entry.get("first") if isinstance(entry.get("first"), str) else (
                seen[0] if seen else ident)
            count = len(seen) + 1
            seen = (seen + [ident])[-10:]
            stops[key] = {"ids": seen, "first": first, "at": now}
            _write_json(path, stops)
        if count < 2:
            return "counted"
        # The streak's first refusal names the episode: after a pass, a new
        # streak of two pings again inside realertHours.
        return send(root, "blocker", f"{gate} gate refused twice", ticket=ticket,
                    unblock="/crew:status", kind="gate", dedupe=first)
    except Exception as exc:  # pylint: disable=broad-except
        _say(f"stop failed ({exc.__class__.__name__})")
        return "failed:error"


def mask(value):
    """A chat id for display: its last 2 characters (4 when it is longer than 8);
    one of 2 characters or fewer is masked whole."""
    if value is None:
        return None
    text = str(value)
    if len(text) <= 2:
        return "***"
    return "***" + text[-(4 if len(text) > 8 else 2):]


def show_config(root):
    cfg, notices = effective_config(root)
    for notice in notices:
        print("notice: " + redact(notice))
    printable = dict(cfg)
    printable["chatId"] = mask(printable.get("chatId"))
    if isinstance(printable.get("questionTypes"), tuple):
        printable["questionTypes"] = list(printable["questionTypes"])
    print(redact(json.dumps(printable, sort_keys=True)))
    return "config"


def main(argv=None):
    parser = argparse.ArgumentParser(description="crew's outbound notifier")
    sub = parser.add_subparsers(dest="cmd")
    one = sub.add_parser("send")
    one.add_argument("--root", default=".")
    one.add_argument("--event", required=True)
    one.add_argument("--reason", default="")
    one.add_argument("--ticket")
    one.add_argument("--unblock")
    one.add_argument("--outcome", choices=("pass", "fail"))
    one.add_argument("--kind")
    sub.add_parser("hook").add_argument("--root", default=".")
    sub.add_parser("config").add_argument("--root", default=".")
    run = sub.add_parser("run-stop")
    run.add_argument("--root", default=".")
    run.add_argument("--ticket", required=True)
    run.add_argument("--phase", required=True)
    run.add_argument("--reason", default="")
    gate = sub.add_parser("stop")
    gate.add_argument("--root", default=".")
    gate.add_argument("--gate", required=True, choices=GATES)
    verdict = gate.add_mutually_exclusive_group(required=True)
    verdict.add_argument("--refused", action="store_true")
    verdict.add_argument("--passed", action="store_true")
    try:
        args = parser.parse_args(argv)
    except SystemExit:
        print("failed:usage")
        return 0
    try:
        if args.cmd == "send":
            word = send(args.root, args.event, args.reason, ticket=args.ticket,
                        unblock=args.unblock, outcome=args.outcome, kind=args.kind)
        elif args.cmd == "run-stop":
            word = run_stop(args.root, args.ticket, args.phase, args.reason)
        elif args.cmd == "stop":
            word = stop_outcome(args.root, args.gate, args.refused, sys.stdin.buffer.read())
        elif args.cmd == "hook":
            word = hook(args.root, sys.stdin.buffer.read())
        elif args.cmd == "config":
            word = show_config(args.root)
        else:
            parser.print_usage(sys.stderr)
            word = "failed:usage"
    except Exception as exc:  # pylint: disable=broad-except
        _say(f"failed ({exc.__class__.__name__})")
        word = "failed:error"
    print(word)
    return 0


if __name__ == "__main__":
    sys.exit(main())

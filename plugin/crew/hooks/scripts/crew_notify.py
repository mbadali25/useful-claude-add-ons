#!/usr/bin/env python3
"""crew's outbound notifier: one Python module behind notify.sh and notify.ps1.

Outbound only. Nothing here reads from a chat, nothing carries a reply back into
a session, and approvals stay a typed `/crew:approve`.

Two events send (T-0051):

* `deploy` -- every `/crew:promote` result. A pass goes silent
  (`disable_notification`), a failure goes loud, and a result that says
  neither (no `--outcome`, a reason naming neither) goes loud as unknown.
* `question` -- Claude Code stopped and is waiting on the owner: the
  `Notification` hook, filtered on the payload's `notification_type`. An
  `idle_prompt` never pings.

`blocker` is RESERVED: accepted in `notify.events` and sending nothing until
T-0060 gives it a sender. The pre-1.0 names map: `gate` -> `deploy`,
`waiting` -> `question`, `phase`/`review`/`done` -> `blocker`, each with a
notice, never a silent drop.

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
`tokenEnv` (the variable's NAME) is honoured from the machine-global layer only:
a repo's `.crew/config.json` could otherwise point it at any secret in the
environment and have it put into the request URL.

Every entry point exits 0. A reason goes to stderr when nothing was sent.

    crew_notify.py send --root . --event deploy --outcome fail --reason "<env> <sha> - FAILED at gate 3"
    crew_notify.py hook --root . < payload.json
    crew_notify.py config --root .
"""
import argparse
import datetime
import hashlib
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

import crew_config  # noqa: E402  pylint: disable=wrong-import-position
import crew_state  # noqa: E402  pylint: disable=wrong-import-position
import crew_ticket  # noqa: E402  pylint: disable=wrong-import-position

EVENTS = ("deploy", "question")
# T-0060 moves `blocker` into EVENTS when it gives it a sender.
RESERVED = ("blocker",)
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
# One table, plain ASCII, keyed by event and kind. T-0060 adds the blocker kinds.
SUBJECTS = {
    ("question", "ask"): "Question",
    ("question", "permission"): "Needs permission",
    ("deploy", "pass"): "Promotion passed",
    ("deploy", "fail"): "Deploy FAILED",
    ("deploy", "unknown"): "Promotion outcome unknown",
}
EXAMPLE_CHAT_ID = "-1001234567890"
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
    # tokenEnv names the variable whose value goes into the request URL: only the
    # owner's own machine-global file may name it, never a cloned repo's config.
    global_token_env = global_notify.get("tokenEnv")
    cfg["tokenEnv"] = global_token_env if isinstance(global_token_env, str) and global_token_env \
        else None
    if repo.get("tokenEnv") is not None and repo.get("tokenEnv") != cfg["tokenEnv"]:
        notices.append("the repo's notify.tokenEnv is ignored: only the machine-global "
                       "~/.claude/crew/config.json (or the notify skill's config) names the token")
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
            with urllib.request.urlopen(urllib.request.Request(url, data=data),
                                        timeout=HTTP_TIMEOUT) as response:
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
            return False, f"HTTP {exc.code}"
        except (urllib.error.URLError, OSError, ValueError) as exc:
            return False, f"network error ({exc.__class__.__name__})"
        try:
            out = json.loads(body.decode("utf-8", "replace"))
        except ValueError:
            return False, "response is not JSON"
        if status == 200 and isinstance(out, dict) and out.get("ok") is True:
            return True, "ok"
        return False, "ok: false"
    return False, "429 twice"


def _teams(url, text):
    body = json.dumps({"type": "message", "attachments": [{
        "contentType": "application/vnd.microsoft.card.adaptive",
        "content": {"type": "AdaptiveCard", "version": "1.4",
                    "body": [{"type": "TextBlock", "text": text, "wrap": True}]}}]}).encode()
    request = urllib.request.Request(url, data=body,
                                     headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT) as response:
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


def _deliver(root, cfg, event, reason, ticket, unblock, kind, episode):
    """Everything after the filters: credentials, line, episode, dedupe, transport."""
    provider = cfg.get("provider")
    if provider == "telegram":
        token_env = cfg.get("tokenEnv")
        token = os.environ.get(token_env) if isinstance(token_env, str) and token_env else None
        target = cfg.get("chatId")
        if not token or target in (None, ""):
            _say("telegram token env or chatId missing; nothing sent")
            return "missing-credentials"
    elif provider == "teams":
        url_env = cfg.get("urlEnv")
        target = os.environ.get(url_env) if isinstance(url_env, str) and url_env else None
        token = None
        if not target:
            _say(f"teams url env ${url_env} not set; nothing sent")
            return "missing-credentials"
    else:
        _say(f"unknown notify.provider {provider!r}; nothing sent")
        return "off"

    place = where(root)
    ticket = ticket or place["ticket"]
    phase = place["phase"] if ticket == place["ticket"] else ""
    subject = SUBJECTS[(event, kind)]
    line = redact(format_line(subject, place["repo"], place["place"], ticket, phase,
                              redact(reason), unblock))
    loud = event == "question" or kind in ("fail", "unknown")

    state = state_dir(root)
    now = time.time()
    episodes = {}
    if episode:
        episodes = _read_json(os.path.join(state, "episodes.json"))
        seen = episodes.get(episode[0])
        if isinstance(seen, dict) and seen.get("key") == episode[1]:
            _say("same waiting episode as the last ping (no reply since); nothing sent")
            return "episode"
    material = "|".join([event, ticket or "", reason] + (list(episode) if episode else []))
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
    if event in LEGACY:
        _say(f"legacy '{event}' read as '{LEGACY[event]}'")
        event = LEGACY[event]
    if event in RESERVED:
        _say(f"'{event}' is reserved until T-0060 gives it a sender; nothing sent")
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
         episode=None, cfg=None):
    """Send one message. Returns `sent`, `deduped`, `episode`, `off`, `filtered`,
    `missing-credentials` or `failed:<why>`; never raises."""
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
        elif kind not in ("ask", "permission"):
            kind = "ask"
        return _deliver(root, cfg, event, reason, ticket, unblock, kind, episode)
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


def mask(value):
    """A chat id for display: its last 2 characters (4 when it is longer than 8)."""
    if value is None:
        return None
    text = str(value)
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
    sub.add_parser("hook").add_argument("--root", default=".")
    sub.add_parser("config").add_argument("--root", default=".")
    try:
        args = parser.parse_args(argv)
    except SystemExit:
        print("failed:usage")
        return 0
    try:
        if args.cmd == "send":
            word = send(args.root, args.event, args.reason, ticket=args.ticket,
                        unblock=args.unblock, outcome=args.outcome)
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

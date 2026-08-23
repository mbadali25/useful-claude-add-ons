#!/usr/bin/env python3
"""tg.py - minimal Telegram Bot API helpers (stdlib only). Shared by notify.py and notifyd.py."""
import json
import time
import urllib.parse
import urllib.request

# sendMessage rejects text over 4096 characters outright, so anything longer has
# to go as several messages. Every budget here is measured against the
# HTML-escaped text, which is what actually goes on the wire.
TG_TEXT_LIMIT = 4096
# Each part is prefixed with "<b>{subject} (cont.) (12/34)</b>\n". The subject is
# caller-supplied and escaping can grow it 5x, so the overhead is computed per
# call rather than assumed -- a fixed reserve lets a long subject push the
# assembled message past the limit even when the body chunk fits.
MAX_HEADER = 256
# Whatever the subject costs, leave at least this much room for body text, so a
# pathological subject degrades to a truncated header instead of endless parts.
MIN_BODY_BUDGET = 512
# Telegram throttles sustained posting to roughly one message per second per
# chat; a multi-part body posted flat out earns a 429 and loses the tail.
CHUNK_PAUSE_SECONDS = 1.0


class TgError(RuntimeError):
    pass


def api(token, method, params=None, timeout=35):
    url = f"https://api.telegram.org/bot{token}/{method}"
    data = urllib.parse.urlencode({k: v for k, v in (params or {}).items() if v is not None}).encode()
    req = urllib.request.Request(url, data=data)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        out = json.loads(r.read().decode())
    if not out.get("ok"):
        raise TgError(out.get("description", f"{method} failed"))
    return out.get("result")


def esc(s):
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def inline_kb(labels, req_id):
    """One row of buttons; callback_data = '<req_id>|<index>' (<=64 bytes)."""
    row = [{"text": lab, "callback_data": f"{req_id}|{i}"} for i, lab in enumerate(labels or [])]
    return json.dumps({"inline_keyboard": [row]}) if row else None


def header_for(subject, index, total):
    """The '<b>...</b>\\n' prefix on part `index` (0-based) of `total`."""
    head = esc(subject) if index == 0 else f"{esc(subject)} (cont.)"
    if total > 1:
        head = f"{head} ({index + 1}/{total})"
    if len(head) > MAX_HEADER:
        head = head[:MAX_HEADER - 1] + "..."
    return f"<b>{head}</b>\n"


def body_budget(subject, parts_hint=99):
    """Room left for one escaped body chunk once the worst-case header is paid for.

    parts_hint only affects the width of the '(12/34)' counter, so overestimating
    it costs a couple of characters and never underestimates the header.
    """
    worst = header_for(subject, 1, max(parts_hint, 2))
    return max(TG_TEXT_LIMIT - len(worst), MIN_BODY_BUDGET)


def split_body(body, budget=None, subject=""):
    """Split raw (unescaped) body text into pieces that fit once escaped.

    Splitting before escaping is deliberate: cutting escaped text can land in the
    middle of an entity like &amp; and Telegram rejects the whole message as bad
    HTML. Breaks fall on a blank line, then a newline, then a hard slice.

    Whitespace is preserved exactly -- ''.join(split_body(x)) == x -- so a diff or
    a log keeps its blank lines across a part boundary.
    """
    body = body or ""
    if budget is None:
        budget = body_budget(subject)
    if len(esc(body)) <= budget:
        return [body] if body else []
    chunks, current = [], ""

    def flush():
        nonlocal current
        if current:
            chunks.append(current)
            current = ""

    for line in body.splitlines(keepends=True):
        if len(esc(current + line)) <= budget:
            current += line
            continue
        flush()
        # A single line can still be over budget on its own (an embedded URL, a
        # base64 blob, minified output with no newline to break on).
        while len(esc(line)) > budget:
            cut = len(line)
            while cut > 1 and len(esc(line[:cut])) > budget:
                cut = cut * budget // max(len(esc(line[:cut])), 1) or 1
            chunks.append(line[:cut])
            line = line[cut:]
        current = line
    flush()
    # Only genuinely empty strings are dropped. A whitespace-only chunk is still
    # content -- discarding it loses part of the body silently.
    return [c for c in chunks if c]


def send_message(token, chat_id, subject, body, thread_id=None, labels=None, req_id=None):
    """Send subject+body, splitting over several messages when body is too long.

    Returns the LAST message sent. notifyd correlates a reply by the message_id it
    gets back, and a reply lands on the message the user is looking at -- the final
    part, which is also the one carrying the buttons.
    """
    parts = split_body(body, subject=subject)
    total = max(len(parts), 1)
    sent = None
    for i in range(total):
        piece = esc(parts[i]) if parts else ""
        text = f"{header_for(subject, i, total)}{piece}" if piece else header_for(subject, i, total).rstrip("\n")
        params = {
            "chat_id": chat_id, "text": text, "parse_mode": "HTML",
            "disable_web_page_preview": "true", "message_thread_id": thread_id,
        }
        # Buttons go on the final part only -- one set of choices per question,
        # attached to the message that ends it.
        if labels and req_id and i == total - 1:
            params["reply_markup"] = inline_kb(labels, req_id)
        if i:
            time.sleep(CHUNK_PAUSE_SECONDS)
        sent = api(token, "sendMessage", params)
    return sent


def create_forum_topic(token, chat_id, name):
    r = api(token, "createForumTopic", {"chat_id": chat_id, "name": name[:128]})
    return r["message_thread_id"]


def close_forum_topic(token, chat_id, thread_id):
    try:
        api(token, "closeForumTopic", {"chat_id": chat_id, "message_thread_id": thread_id})
    except TgError:
        pass


def answer_callback(token, cbq_id, text=None):
    try:
        api(token, "answerCallbackQuery", {"callback_query_id": cbq_id, "text": text})
    except TgError:
        pass


def get_updates(token, offset=0, timeout=25):
    return api(token, "getUpdates", {"offset": offset, "timeout": timeout,
                                     "allowed_updates": json.dumps(["message", "callback_query"])},
               timeout=timeout + 10)

#!/usr/bin/env python3
"""tg.py — minimal Telegram Bot API helpers (stdlib only). Shared by notify.py and notifyd.py."""
import json
import time
import urllib.parse
import urllib.request

# sendMessage rejects text over 4096 characters outright, so anything longer has
# to go as several messages. Budget is measured against the HTML-escaped text,
# which is what actually goes on the wire, and leaves room for the "(2/3)" header.
TG_TEXT_LIMIT = 4096
CHUNK_BUDGET = TG_TEXT_LIMIT - 64
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


def split_body(body, budget=CHUNK_BUDGET):
    """Split raw (unescaped) body text into pieces that fit once escaped.

    Splitting before escaping is deliberate: cutting escaped text can land in the
    middle of an entity like &amp; and Telegram rejects the whole message as bad
    HTML. Breaks fall on a blank line, then a newline, then a hard slice.
    """
    body = body or ""
    if len(esc(body)) <= budget:
        return [body] if body else []
    chunks, current = [], ""

    def flush():
        nonlocal current
        if current:
            chunks.append(current.rstrip("\n"))
            current = ""

    for para in body.split("\n\n"):
        for line in (para + "\n\n").splitlines(keepends=True):
            if len(esc(current + line)) <= budget:
                current += line
                continue
            flush()
            # A single line can still be over budget on its own (an embedded URL,
            # a base64 blob, minified output with no newline to break on).
            while len(esc(line)) > budget:
                cut = len(line)
                while cut > 1 and len(esc(line[:cut])) > budget:
                    cut = cut * budget // max(len(esc(line[:cut])), 1) or 1
                chunks.append(line[:cut])
                line = line[cut:]
            current = line
    flush()
    return [c for c in chunks if c.strip()]


def send_message(token, chat_id, subject, body, thread_id=None, labels=None, req_id=None):
    """Send subject+body, splitting over several messages when body is too long.

    Returns the LAST message sent. notifyd correlates a reply by the message_id it
    gets back, and a reply lands on the message the user is looking at -- the final
    part, which is also the one carrying the buttons.
    """
    parts = split_body(body)
    total = max(len(parts), 1)
    sent = None
    for i in range(total):
        head = esc(subject) if i == 0 else f"{esc(subject)} (cont.)"
        if total > 1:
            head = f"{head} ({i + 1}/{total})"
        piece = esc(parts[i]) if parts else ""
        text = f"<b>{head}</b>\n{piece}" if piece else f"<b>{head}</b>"
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

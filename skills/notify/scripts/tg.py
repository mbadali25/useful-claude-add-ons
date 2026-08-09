#!/usr/bin/env python3
"""tg.py — minimal Telegram Bot API helpers (stdlib only). Shared by notify.py and notifyd.py."""
import json
import urllib.parse
import urllib.request


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


def send_message(token, chat_id, subject, body, thread_id=None, labels=None, req_id=None):
    text = f"<b>{esc(subject)}</b>\n{esc(body)}" if body else f"<b>{esc(subject)}</b>"
    params = {
        "chat_id": chat_id, "text": text, "parse_mode": "HTML",
        "disable_web_page_preview": "true", "message_thread_id": thread_id,
    }
    if labels and req_id:
        params["reply_markup"] = inline_kb(labels, req_id)
    return api(token, "sendMessage", params)


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

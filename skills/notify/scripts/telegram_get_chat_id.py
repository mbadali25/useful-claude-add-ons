#!/usr/bin/env python3
"""
telegram_get_chat_id.py — find your chat_id so notify.py knows where to message.

Steps:
  1. Create a bot: message @BotFather on Telegram, send /newbot, follow prompts,
     copy the token.
  2. Open a chat with your new bot and send it any message (e.g. "hi").
  3. Run:  TELEGRAM_BOT_TOKEN=123:abc python telegram_get_chat_id.py
It prints the chat_id(s) that have recently messaged the bot.

Note: the bot must be in polling mode (no webhook set). Personal bots are by default.
"""
import json, os, sys, urllib.request

def main():
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        print("Set TELEGRAM_BOT_TOKEN first.", file=sys.stderr); sys.exit(2)
    url = f"https://api.telegram.org/bot{token}/getUpdates?timeout=0"
    try:
        with urllib.request.urlopen(url, timeout=15) as r:
            data = json.loads(r.read().decode())
    except Exception as e:
        print(f"getUpdates failed: {e}", file=sys.stderr); sys.exit(3)
    if not data.get("ok"):
        print(f"telegram error: {data.get('description')}", file=sys.stderr); sys.exit(3)
    seen = {}
    for u in data.get("result", []):
        msg = u.get("message") or u.get("channel_post") or {}
        chat = msg.get("chat") or {}
        if chat.get("id") is not None:
            name = chat.get("title") or " ".join(x for x in [chat.get("first_name"), chat.get("last_name")] if x) or chat.get("username") or ""
            seen[chat["id"]] = f"{name} ({chat.get('type')})".strip()
    if not seen:
        print("No recent messages found. Send your bot a message, then re-run.")
        sys.exit(0)
    print("chat_id  ->  who")
    for cid, who in seen.items():
        print(f"{cid}  ->  {who}")

if __name__ == "__main__":
    main()

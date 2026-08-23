#!/usr/bin/env python3
"""
notify.py - notify a Claude session/job via Telegram and/or email.

Telegram routing:
  * Dispatcher mode (dispatcher.enabled, or telegram.mode == "topics"): the client
    drops a request in the spool and waits for the answer file. Run the daemon
    separately: `python notifyd.py`. Required for concurrent jobs and topic-per-job.
  * Direct mode (no dispatcher): the client sends and polls getUpdates itself. Fine
    for a single job; don't run concurrent direct questions on one bot.

Email: SMTP (this script) or `connector` (Claude sends via MCP; see SKILL.md).
Subject = event / what's happening; body = details. Stdlib only.
Exit: 0 sent/reply, 2 config, 3 send fail, 5 reply timeout.
"""
import argparse
import json
import os
import smtplib
import ssl
import sys
import time
import uuid
from email.message import EmailMessage
from pathlib import Path
import inbox
import tg

# Windows consoles default to cp1252, so printing a body that came from a UTF-8
# config or file (an em dash, an emoji, any non-Latin text) raises
# UnicodeEncodeError and takes the whole run down -- including --dry-run, whose
# only job is to print. Degrade unprintable characters instead of dying.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):  # already detached, or not a real stream
        pass

EVENT_LABEL = {"complete": "\u2705 Complete", "error": "\u274c Error",
               "question": "\u2753 Question", "info": "\u2139\ufe0f Info"}
SMTP_PRESETS = {"gmail": ("smtp.gmail.com", 587, True), "m365": ("smtp.office365.com", 587, True),
                "office365": ("smtp.office365.com", 587, True), "outlook": ("smtp-mail.outlook.com", 587, True)}


def eprint(*a): print(*a, file=sys.stderr)
def die(m, c=2): eprint(f"notify: {m}"); sys.exit(c)


def deep_merge(base, over):
    out = dict(base)
    for k, v in (over or {}).items():
        out[k] = deep_merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


def resolve_config(explicit):
    if explicit:
        try: return json.loads(Path(explicit).read_text(encoding="utf-8"))
        except Exception as e: die(f"could not read {explicit}: {e}")
    cfg = {}
    for p in [Path(os.path.expanduser("~/.config/notify/config.json")), Path.cwd() / ".notify.json"]:
        if p.exists():
            try: cfg = deep_merge(cfg, json.loads(p.read_text(encoding="utf-8")))
            except Exception as e: die(f"could not read {p}: {e}")
    return cfg


def spool_root(cfg):
    return Path(os.path.expanduser(cfg.get("dispatcher", {}).get("spool_dir", "~/.local/state/notify/spool")))


# ---------- Inbound: read what the user sent us ----------
def dispatcher_fresh(root):
    hb = root / "state" / "heartbeat"
    try:
        return hb.exists() and (int(time.time()) - int(hb.read_text() or 0) < 10)
    except (OSError, ValueError):
        return False


def poll_into_inbox(cfg, root, seconds):
    """Direct-mode fill: only safe when the daemon is not polling the same token.

    Telegram answers a second concurrent getUpdates with 409 Conflict, so when notifyd
    is up the daemon is the only reader and this must not run.
    """
    tgc = cfg.get("telegram", {})
    token = os.environ.get(tgc.get("bot_token_env", "TELEGRAM_BOT_TOKEN"))
    if not token:
        # Reading messages already on disk is still useful without a token, so warn and
        # fall through to the file rather than killing the run.
        eprint(f"notify: env {tgc.get('bot_token_env','TELEGRAM_BOT_TOKEN')} not set - "
               "reading the stored inbox only, not polling Telegram.")
        return
    chat_id = tgc.get("chat_id")
    topics = {}
    try:
        topics = json.loads((root / "state" / "topics.json").read_text())
    except (OSError, ValueError):
        # Absent or corrupt topics.json means "no topics", not a crash. Any
        # other exception is a real bug and should surface.
        pass
    offset = inbox.load_offset(root)
    deadline = time.time() + max(0, seconds)
    first = True
    while first or time.time() < deadline:
        first = False
        wait = 0 if seconds <= 0 else min(25, max(1, int(deadline - time.time())))
        try:
            updates = tg.get_updates(token, offset, timeout=wait)
        except Exception as e:
            eprint(f"getUpdates: {e}")
            break
        got = False
        for u in updates:
            offset = u["update_id"] + 1
            m = u.get("message")
            if m and m.get("text") and (not chat_id or
                                        str((m.get("chat") or {}).get("id")) == str(chat_id)):
                inbox.capture(root, m, topics=topics)
                got = True
        if updates:
            inbox.save_offset(root, offset)
        if got or seconds <= 0:
            break


def read_inbox(cfg, job, wait, peek, dry):
    """Hand Claude every message the user sent that wasn't already consumed."""
    root = spool_root(cfg)
    if dry:
        src = "dispatcher spool" if dispatcher_fresh(root) else "direct getUpdates"
        print(f"DRY-RUN inbox({src}) -> job {job or '(any)'}, wait {wait}s, peek={peek}")
        sys.exit(0)   # --inbox is a terminal action; do not fall through to the send path
    if not dispatcher_fresh(root):
        # No daemon: we are the only reader, so top the inbox up ourselves first.
        poll_into_inbox(cfg, root, wait)
        msgs = inbox.read(root, job=job, peek=peek)
    else:
        # The daemon owns the token. Wait for it to file something rather than polling
        # Telegram ourselves and colliding with it.
        deadline = time.time() + max(0, wait)
        msgs = inbox.read(root, job=job, peek=peek)
        while not msgs and time.time() < deadline:
            time.sleep(1)
            msgs = inbox.read(root, job=job, peek=peek)
    print(json.dumps({"messages": msgs, "count": len(msgs)}, ensure_ascii=False))
    sys.exit(0 if msgs else 5)


# ---------- Telegram via dispatcher (spool) ----------
def via_dispatcher(cfg, subject, body, event, job_id, want_reply, buttons, timeout, dry):
    root = spool_root(cfg)
    for sub in ("requests", "answers"):
        (root / sub).mkdir(parents=True, exist_ok=True)
    req_id = "r" + uuid.uuid4().hex[:10]
    req = {"req_id": req_id, "job_id": job_id, "event": event, "subject": subject, "body": body,
           "want_reply": want_reply, "buttons": buttons, "timeout": timeout, "created": int(time.time())}
    if dry:
        mode = cfg.get("telegram", {}).get("mode", "dm")
        tgt = f"topic '{job_id}'" if mode == "topics" else "shared chat"
        print(f"DRY-RUN telegram(dispatcher, {mode}) -> {tgt}")
        print(f"        subject: {subject}\n        body:    {body}")
        if want_reply: print(f"        buttons: {buttons or '(none)'} + free-text; wait {timeout}s")
        return
    hb = root / "state" / "heartbeat"
    fresh = hb.exists() and (int(time.time()) - int(hb.read_text() or 0) < 10)
    if want_reply and not fresh:
        die("dispatcher not running - start it with `python notifyd.py` "
            "(needed for topics and for waiting on replies).", 2)
    tmp = root / "requests" / (req_id + ".json.tmp")
    tmp.write_text(json.dumps(req)); os.replace(tmp, root / "requests" / (req_id + ".json"))
    print(f"queued telegram -> job '{job_id}' ({req_id})")
    if not want_reply:
        return
    ans = root / "answers" / (req_id + ".json")
    deadline = time.time() + timeout + 15
    while time.time() < deadline:
        if ans.exists():
            data = json.loads(ans.read_text()); ans.unlink(missing_ok=True)
            if data.get("timed_out"):
                print(json.dumps({"reply": None, "timed_out": True})); sys.exit(5)
            if data.get("error"):
                die(f"dispatcher send error: {data['error']}", 3)
            print(json.dumps({"reply": data.get("reply"), "via": data.get("via")})); sys.exit(0)
        time.sleep(0.5)
    print(json.dumps({"reply": None, "timed_out": True})); sys.exit(5)


# ---------- Telegram direct (no dispatcher) ----------
def direct_telegram(cfg, subject, body, want_reply, buttons, timeout, dry):
    tgc = cfg.get("telegram", {}); chat_id = tgc.get("chat_id")
    token = os.environ.get(tgc.get("bot_token_env", "TELEGRAM_BOT_TOKEN"))
    if not chat_id: die("telegram.chat_id required")
    if dry:
        parts = tg.split_body(body)
        print(f"DRY-RUN telegram(direct) -> chat {chat_id}")
        print(f"        subject: {subject}\n        body:    {body}")
        if len(parts) > 1:
            print(f"        split:   {len(parts)} messages (body is over Telegram's "
                  f"{tg.TG_TEXT_LIMIT}-char limit)")
        if want_reply: print(f"        buttons: {buttons or '(none)'} + free-text; wait {timeout}s")
        return
    if not token: die(f"env {tgc.get('bot_token_env','TELEGRAM_BOT_TOKEN')} not set")
    req_id = "r" + uuid.uuid4().hex[:8]
    try:
        tg.send_message(token, chat_id, subject, body, labels=buttons if want_reply else None, req_id=req_id)
    except Exception as e:
        die(f"telegram send failed: {e}", 3)
    print(f"sent telegram -> chat {chat_id}")
    if not want_reply:
        return
    root = spool_root(cfg)
    deadline = time.time() + timeout
    offset = inbox.load_offset(root)
    # Anything already queued predates the question, so it cannot be its answer - but it
    # is still something the user said, so file it in the inbox instead of discarding it
    # (which is what fast-forwarding the offset to 0-latest used to do).
    try:
        for u in tg.get_updates(token, offset, timeout=0):
            offset = max(offset, u["update_id"] + 1)
            m = u.get("message")
            if m and m.get("text") and str((m.get("chat") or {}).get("id")) == str(chat_id):
                inbox.capture(root, m)
        inbox.save_offset(root, offset)
    except Exception: pass
    while time.time() < deadline:
        try:
            for u in tg.get_updates(token, offset, timeout=min(25, max(1, int(deadline - time.time())))):
                offset = u["update_id"] + 1
                inbox.save_offset(root, offset)
                if "callback_query" in u:
                    cq = u["callback_query"]; rid, _, idx = cq.get("data", "").partition("|")
                    if rid == req_id:
                        picked = buttons and idx.isdigit() and int(idx) < len(buttons)
                        lab = buttons[int(idx)] if picked else cq.get("data")
                        tg.answer_callback(token, cq["id"], f"\u2713 {lab}")
                        print(json.dumps({"reply": lab, "via": "button"})); sys.exit(0)
                elif "message" in u:
                    m = u["message"]
                    if str((m.get("chat") or {}).get("id")) == str(chat_id) and m.get("text"):
                        print(json.dumps({"reply": m["text"], "via": "text"})); sys.exit(0)
        except Exception as e:
            eprint(f"getUpdates: {e}"); time.sleep(2)
    print(json.dumps({"reply": None, "timed_out": True})); sys.exit(5)


# ---------- Email ----------
def smtp_settings(ec):
    s = dict(ec.get("smtp", {})); prov = (s.get("provider") or "").lower()
    if prov in SMTP_PRESETS and not s.get("host"):
        s["host"], s["port"], s["starttls"] = SMTP_PRESETS[prov]
    return s


def send_email(ec, subject, body, dry):
    be = (ec.get("backend") or "smtp").lower()
    if dry:
        where = "connector (Claude via MCP)" if be == "connector" else f"smtp {smtp_settings(ec).get('host')}"
        print(f"DRY-RUN email({where}) -> {ec.get('to')}\n        subject: {subject}\n        body:    {body}"); return
    if be == "connector":
        die("email.backend 'connector' is sent by Claude via MCP, not this script (see SKILL.md). "
            "Use 'smtp' for detached jobs.", 2)
    s = smtp_settings(ec); host = s.get("host")
    if not host: die("email.smtp.host or a known provider required")
    to, frm = ec.get("to"), ec.get("from") or s.get("from")
    if not to: die("email.to required")
    if not frm: die("email.from required")
    user = os.environ.get(s.get("username_env", "SMTP_USER")); pw = os.environ.get(s.get("password_env", "SMTP_PASS"))
    msg = EmailMessage(); msg["From"], msg["To"], msg["Subject"] = frm, to, subject; msg.set_content(body or subject)
    with smtplib.SMTP(host, int(s.get("port", 587)), timeout=30) as srv:
        if s.get("starttls", True): srv.starttls(context=ssl.create_default_context())
        if user and pw: srv.login(user, pw)
        srv.send_message(msg)
    print(f"sent email -> {to}")


def main():
    ap = argparse.ArgumentParser(description="Notify a Claude session/job via Telegram / email.")
    # Not required: --inbox reads instead of sending, and has nothing to say.
    ap.add_argument("--message", "-m", default=None)
    ap.add_argument("--inbox", action="store_true",
                    help="read messages the user sent the bot and exit (5 if none)")
    ap.add_argument("--peek", action="store_true",
                    help="with --inbox: leave the messages unconsumed")
    ap.add_argument("--event", "-e", default="info", choices=list(EVENT_LABEL))
    ap.add_argument("--subject", "-s", default=None)
    ap.add_argument("--job", "--session", dest="job", default="default",
                    help="job id; also the topic name in topics mode")
    ap.add_argument("--channel", "-c", default=None, choices=["telegram", "email", "both"])
    ap.add_argument("--buttons", default=None, help="comma-separated labels for a question (default Yes,No)")
    ap.add_argument("--no-buttons", action="store_true")
    ap.add_argument("--wait", action="store_true", help="block for a reply (implied by --event question)")
    ap.add_argument("--timeout", type=int, default=None)
    ap.add_argument("--config"); ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    cfg = resolve_config(args.config)
    if not cfg: die("no config. See references/config.md")

    if args.inbox:
        # --inbox alone drains what is already there; add --wait to block for up to
        # --timeout seconds (or reply.timeout_seconds) for the user to say something.
        wait = (args.timeout or cfg.get("reply", {}).get("timeout_seconds", 3600)) if args.wait else 0
        read_inbox(cfg, None if args.job == "default" else args.job, wait, args.peek, args.dry_run)
    if not args.message:
        die("--message is required unless --inbox is given")

    if cfg.get("events", {}).get(args.event) is False:
        print(f"muted: '{args.event}' disabled; nothing sent"); sys.exit(0)

    subject = args.subject or EVENT_LABEL[args.event]
    body = args.message
    channel = args.channel or cfg.get("default_channel", "telegram")
    timeout = args.timeout or cfg.get("reply", {}).get("timeout_seconds", 3600)

    # Only a pure-telegram channel blocks for a reply; in 'both', telegram is fire-and-forget
    # so the email still goes out and we never double-block.
    tg_wait = (args.wait or args.event == "question") and channel == "telegram"
    tg_buttons = None
    if tg_wait and not args.no_buttons:
        tg_buttons = [b.strip() for b in (args.buttons.split(",") if args.buttons else ["Yes", "No"]) if b.strip()]

    if channel in ("telegram", "both"):
        use_disp = cfg.get("dispatcher", {}).get("enabled", False) or cfg.get("telegram", {}).get("mode") == "topics"
        if use_disp:
            via_dispatcher(cfg, subject, body, args.event, args.job, tg_wait, tg_buttons, timeout, args.dry_run)
        else:
            direct_telegram(cfg, subject, body, tg_wait, tg_buttons, timeout, args.dry_run)
        if channel == "telegram":
            return  # (a waiting call already exited; a non-waiting one is done)

    if channel in ("email", "both"):
        send_email(cfg.get("email", {}), subject, body, args.dry_run)


if __name__ == "__main__":
    main()

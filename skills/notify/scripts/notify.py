#!/usr/bin/env python3
"""
notify.py — notify a Claude session/job via Telegram and/or email.

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
import tg

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
        die("dispatcher not running — start it with `python notifyd.py` "
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
        print(f"DRY-RUN telegram(direct) -> chat {chat_id}")
        print(f"        subject: {subject}\n        body:    {body}")
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
    deadline = time.time() + timeout; offset = 0
    try:
        for u in tg.get_updates(token, 0, timeout=0): offset = max(offset, u["update_id"] + 1)
    except Exception: pass
    while time.time() < deadline:
        try:
            for u in tg.get_updates(token, offset, timeout=min(25, max(1, int(deadline - time.time())))):
                offset = u["update_id"] + 1
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
    ap.add_argument("--message", "-m", required=True)
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

#!/usr/bin/env python3
"""
notifyd.py — the notify dispatcher. One process owns the single Telegram poller so
any number of concurrent jobs can ask questions without fighting over getUpdates.

Modes (config.telegram.mode):
  dm     : all jobs post to one shared chat.
  topics : each job gets its own forum topic (message_thread_id) in a supergroup.

Jobs never call Telegram. They drop a request in the spool and wait for an answer
file. This daemon sends the message (buttons if requested), owns getUpdates, and
routes each button tap / reply / topic message back to the right job.

Run it:   python notifyd.py            # foreground loop (use nohup/systemd/pm2)
Status:   python notifyd.py status
Stop:     python notifyd.py stop

Correlation: inline buttons (callback_data=req_id) + reply-to (message_id->req_id)
+ topic free-text (newest open question in that topic). Reply-to and buttons are
always unambiguous; bare topic text answers the most recent open question there.
"""
import json
import os
import signal
import sys
import time
from pathlib import Path
import inbox
import tg

FINAL_EVENTS = {"complete", "error"}


def eprint(*a): print(*a, file=sys.stderr, flush=True)


def deep_merge(base, over):
    out = dict(base)
    for k, v in (over or {}).items():
        out[k] = deep_merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


def resolve_config(explicit=None):
    if explicit:
        return json.loads(Path(explicit).read_text(encoding="utf-8"))
    cfg = {}
    for p in [Path(os.path.expanduser("~/.config/notify/config.json")), Path.cwd() / ".notify.json"]:
        if p.exists():
            cfg = deep_merge(cfg, json.loads(p.read_text(encoding="utf-8")))
    return cfg


def atomic_write(path: Path, obj):
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj))
    os.replace(tmp, path)


class Spool:
    def __init__(self, root: Path):
        self.root = root
        self.requests = root / "requests"
        self.active = root / "active"
        self.answers = root / "answers"
        self.state = root / "state"
        for d in (self.requests, self.active, self.answers, self.state):
            d.mkdir(parents=True, exist_ok=True)
        self.pidfile = self.state / "notifyd.pid"
        self.heartbeat = self.state / "heartbeat"
        self.topics_file = self.state / "topics.json"

    def load_topics(self):
        try: return json.loads(self.topics_file.read_text())
        except Exception: return {}

    def save_topics(self, t): atomic_write(self.topics_file, t)


class Dispatcher:
    def __init__(self, cfg, spool: Spool):
        self.cfg = cfg
        self.sp = spool
        tgc = cfg.get("telegram", {})
        self.token = os.environ.get(tgc.get("bot_token_env", "TELEGRAM_BOT_TOKEN"))
        self.chat_id = tgc.get("chat_id")
        self.mode = tgc.get("mode", "dm")
        self.close_on_complete = cfg.get("dispatcher", {}).get("close_topic_on_complete", True)
        if not self.token: raise SystemExit("notifyd: bot token env not set")
        if not self.chat_id: raise SystemExit("notifyd: telegram.chat_id required")
        self.topics = spool.load_topics()          # job_id -> thread_id
        self.pending = {}                            # req_id -> {...}
        self.msg_index = {}                          # message_id -> req_id
        self.thread_open = {}                        # thread_id(str) -> [req_id,...]
        # Resume where the last run (daemon or client) stopped reading, so messages sent
        # while nothing was polling are still delivered.
        self.offset = inbox.load_offset(spool.root)

    # -- topic management --
    def thread_for(self, job_id):
        if self.mode != "topics":
            return None
        if job_id in self.topics:
            return self.topics[job_id]
        try:
            tid = tg.create_forum_topic(self.token, self.chat_id, job_id)
            self.topics[job_id] = tid
            self.sp.save_topics(self.topics)
            return tid
        except tg.TgError as e:
            eprint(f"warning: could not create topic for '{job_id}' ({e}); posting to General. "
                   "Is the group a forum with the bot as admin (Manage Topics)?")
            return None

    # -- request handling --
    def process_requests(self):
        for f in sorted(self.sp.requests.glob("*.json")):
            try:
                req = json.loads(f.read_text())
            except Exception:
                f.unlink(missing_ok=True); continue
            self._send(req)
            f.unlink(missing_ok=True)

    def _send(self, req):
        req_id = req["req_id"]; job_id = req.get("job_id", "default")
        tid = self.thread_for(job_id)
        labels = req.get("buttons") if req.get("want_reply") else None
        try:
            msg = tg.send_message(self.token, self.chat_id, req.get("subject", ""),
                                  req.get("body", ""), thread_id=tid, labels=labels, req_id=req_id)
        except tg.TgError as e:
            eprint(f"send failed for {req_id}: {e}")
            atomic_write(self.sp.answers / f"{req_id}.json",
                         {"req_id": req_id, "reply": None, "error": str(e)})
            return
        if req.get("want_reply"):
            deadline = time.time() + int(req.get("timeout", 3600))
            self.pending[req_id] = {"job_id": job_id, "thread_id": tid,
                                    "message_id": msg["message_id"], "labels": labels or [],
                                    "deadline": deadline}
            self.msg_index[msg["message_id"]] = req_id
            self.thread_open.setdefault(str(tid), []).append(req_id)
            atomic_write(self.sp.active / f"{req_id}.json", req)
        elif tid and self.close_on_complete and req.get("event") in FINAL_EVENTS:
            tg.close_forum_topic(self.token, self.chat_id, tid)
            self.topics.pop(job_id, None); self.sp.save_topics(self.topics)

    # -- update handling --
    def poll(self):
        try:
            updates = tg.get_updates(self.token, self.offset, timeout=3)
        except tg.TgError as e:
            eprint(f"getUpdates: {e}"); time.sleep(2); return
        for u in updates:
            self.offset = u["update_id"] + 1
            if "callback_query" in u:
                self._on_callback(u["callback_query"])
            elif "message" in u:
                self._on_message(u["message"])
        # Persist after the batch, not per update: a crash mid-batch replays a few
        # messages (they land in the inbox twice at worst), where not persisting at all
        # would replay the entire history on every restart.
        if updates:
            inbox.save_offset(self.sp.root, self.offset)

    def _on_callback(self, cbq):
        data = cbq.get("data", "")
        req_id, _, idx = data.partition("|")
        p = self.pending.get(req_id)
        if not p:
            tg.answer_callback(self.token, cbq["id"], "This question is closed."); return
        try: label = p["labels"][int(idx)]
        except Exception: label = data
        tg.answer_callback(self.token, cbq["id"], f"\u2713 {label}")
        self._answer(req_id, label, "button")

    def _on_message(self, m):
        text = m.get("text")
        if not text: return
        req_id = None
        rt = m.get("reply_to_message")
        if rt and rt.get("message_id") in self.msg_index:
            req_id = self.msg_index[rt["message_id"]]
        else:
            tkey = str(m.get("message_thread_id")) if m.get("message_thread_id") else None
            if self.mode == "topics" and tkey and self.thread_open.get(tkey):
                req_id = self.thread_open[tkey][-1]              # newest open question in topic
            elif self.mode == "dm" and self.pending:
                # newest open question overall
                req_id = max(self.pending, key=lambda r: self.pending[r]["deadline"])
        if req_id:
            self._answer(req_id, text, "text")
        else:
            # Not a reply to anything we asked - the user started the conversation. Store
            # it instead of dropping it, so `notify.py --inbox` can hand it to Claude
            # whenever it next looks.
            inbox.capture(self.sp.root, m, job="default", topics=self.topics)

    def _answer(self, req_id, reply, via):
        p = self.pending.pop(req_id, None)
        if not p: return
        self.msg_index.pop(p["message_id"], None)
        lst = self.thread_open.get(str(p["thread_id"]))
        if lst and req_id in lst: lst.remove(req_id)
        atomic_write(self.sp.answers / f"{req_id}.json",
                     {"req_id": req_id, "reply": reply, "via": via, "answered": int(time.time())})
        (self.sp.active / f"{req_id}.json").unlink(missing_ok=True)

    def check_deadlines(self):
        now = time.time()
        for req_id in [r for r, p in self.pending.items() if now > p["deadline"]]:
            p = self.pending.pop(req_id)
            self.msg_index.pop(p["message_id"], None)
            lst = self.thread_open.get(str(p["thread_id"]))
            if lst and req_id in lst: lst.remove(req_id)
            atomic_write(self.sp.answers / f"{req_id}.json",
                         {"req_id": req_id, "reply": None, "timed_out": True})
            (self.sp.active / f"{req_id}.json").unlink(missing_ok=True)

    def run(self):
        self.sp.pidfile.write_text(str(os.getpid()))
        eprint(f"notifyd up: mode={self.mode} chat={self.chat_id} spool={self.sp.root}")
        # reload any active (unanswered) requests left from a previous run
        for f in self.sp.active.glob("*.json"):
            try: self._send(json.loads(f.read_text())); f.unlink(missing_ok=True)
            except Exception: pass
        try:
            while True:
                self.sp.heartbeat.write_text(str(int(time.time())))
                self.process_requests()
                self.poll()
                self.check_deadlines()
                time.sleep(0.4)
        except KeyboardInterrupt:
            eprint("notifyd stopping")
        finally:
            self.sp.pidfile.unlink(missing_ok=True)


def spool_root(cfg):
    d = cfg.get("dispatcher", {}).get("spool_dir", "~/.local/state/notify/spool")
    return Path(os.path.expanduser(d))


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "start"
    cfg = resolve_config()
    sp = Spool(spool_root(cfg))
    if cmd == "status":
        hb = int(sp.heartbeat.read_text()) if sp.heartbeat.exists() else 0
        age = int(time.time()) - hb if hb else None
        pid = sp.pidfile.read_text() if sp.pidfile.exists() else None
        print(json.dumps({"pid": pid, "heartbeat_age_s": age,
                          "running": age is not None and age < 10}, indent=2))
        return
    if cmd == "stop":
        if sp.pidfile.exists():
            try: os.kill(int(sp.pidfile.read_text()), signal.SIGTERM); print("stopped")
            except Exception as e: print(f"could not stop: {e}")
        else: print("not running")
        return
    Dispatcher(cfg, sp).run()


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
inbox.py — the inbound half of two-way notify.

`notify.py --wait` already handles the *solicited* direction: ask a question, block,
take the answer. What it never had was the unsolicited one. A message you send the bot
while Claude is working matched no pending question, so the dispatcher dropped it and
direct mode fast-forwarded its update offset straight past it. Anything you typed
between questions was gone.

This module is the store that fixes it. Both the daemon and the client import it, so
there is one on-disk format and one update offset shared between them:

  <spool>/inbox.jsonl        one JSON object per line, oldest first
  <spool>/state/offset.json  the Telegram getUpdates offset, persisted

Telegram only lets **one** process long-poll a bot token (a second getUpdates gets
409 Conflict), which is why the offset has to be shared rather than per-process: the
daemon owns polling when it is up, the client polls only when it is not, and either way
the next read starts where the last one stopped.

Stdlib only.
"""
import json
import os
import time
from pathlib import Path

INBOX_NAME = "inbox.jsonl"
OFFSET_NAME = "offset.json"
# Keep the file bounded: a phone conversation is small, but a bot left in a busy group
# for a month is not, and nothing else prunes this.
MAX_KEEP = 500


def inbox_path(root):
    return Path(root) / INBOX_NAME


def offset_path(root):
    return Path(root) / "state" / OFFSET_NAME


def load_offset(root):
    try:
        return int(json.loads(offset_path(root).read_text()).get("offset", 0))
    except Exception:
        return 0


def save_offset(root, offset):
    p = offset_path(root)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps({"offset": int(offset)}))
    os.replace(tmp, p)


def append(root, entry):
    """Append one inbound message.

    A single short line opened in append mode is written whole by both POSIX and
    Windows, so concurrent daemon writes and client reads cannot interleave a partial
    record - which is why this is JSONL and not a JSON array that has to be rewritten.
    """
    p = inbox_path(root)
    p.parent.mkdir(parents=True, exist_ok=True)
    entry = dict(entry)
    entry.setdefault("ts", int(time.time()))
    # A previous write killed mid-line leaves no trailing newline, and appending onto it
    # would fuse the two records into one unparseable line - losing this message as well
    # as the broken one. Close the dangling line first; read() then drops only the
    # fragment.
    lead = "\n" if _needs_newline(p) else ""
    with p.open("a", encoding="utf-8") as fh:
        fh.write(lead + json.dumps(entry, ensure_ascii=False) + "\n")
    _trim(p)


def _needs_newline(p):
    try:
        if p.stat().st_size == 0:
            return False
        with p.open("rb") as fh:
            fh.seek(-1, os.SEEK_END)
            return fh.read(1) != b"\n"
    except OSError:
        return False


def _trim(p):
    try:
        lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return
    if len(lines) <= MAX_KEEP:
        return
    tmp = p.with_suffix(".tmp")
    tmp.write_text("\n".join(lines[-MAX_KEEP:]) + "\n", encoding="utf-8")
    os.replace(tmp, p)


def read(root, job=None, since=0, peek=False):
    """Return inbound messages, oldest first.

    job    - only messages attributed to that job id (topics mode); None for all.
    since  - only messages with ts >= this (unix seconds).
    peek   - leave them in the file. Default is to consume what is returned, so two
             reads never hand Claude the same message twice.
    """
    p = inbox_path(root)
    if not p.is_file():
        return []
    raw = p.read_text(encoding="utf-8", errors="replace").splitlines()
    kept, taken = [], []
    for line in raw:
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except ValueError:
            continue  # a truncated line from a killed write; drop it rather than crash
        match = (job is None or entry.get("job") == job) and entry.get("ts", 0) >= since
        (taken if match else kept).append(entry)
    if taken and not peek:
        tmp = p.with_suffix(".tmp")
        tmp.write_text("".join(json.dumps(e, ensure_ascii=False) + "\n" for e in kept),
                       encoding="utf-8")
        os.replace(tmp, p)
    return taken


def capture(root, message, job="default", topics=None):
    """Turn a Telegram message object into an inbox entry and store it.

    In topics mode the thread the message arrived on identifies the job, so reverse
    topics.json (job -> thread_id) to attribute it. Anything unattributable lands under
    the job passed in, which keeps a DM conversation working with no topics at all.
    """
    thread_id = message.get("message_thread_id")
    if thread_id and topics:
        for job_id, tid in topics.items():
            if str(tid) == str(thread_id):
                job = job_id
                break
    frm = message.get("from") or {}
    append(root, {
        "job": job,
        "text": message.get("text", ""),
        "from": frm.get("username") or frm.get("first_name") or str(frm.get("id", "")),
        "message_id": message.get("message_id"),
        "thread_id": thread_id,
        "date": message.get("date"),
    })

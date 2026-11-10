"""L-0656: the held-ping record, and the morning summary sent once.

L-0725: nothing holds a ping any more. `autopilot.sleep.notifyHold` is gone
(`crew_state.AUTOPILOT_NOTIFY_HOLD` is None: no ping is ever held), so every
ping sends as it is raised. What stays is the reading side: a record an earlier
version left in `.work/autopilot/held.json` (per worktree, one key per distinct
held message) is still counted, reported by the morning summary and then
removed, and one that cannot be read is said, never read as none.

The morning summary: crew_autopilot_sleep.sleep_summary, not asleep, appends
`held_line` to L-0653's summary and passes the text to `send_summary` once,
under SUMMARY_LOCK so two runs never both send; only a delivered summary (or
no notifier at all) removes the reported keys from the record (`take`).
`send_summary` uses the configured provider and credentials, silently, and only
when `question` or `blocker` is in `notify.events`: no new event exists.
"""
import json
import os

import crew_notify
import crew_ticket

# crew_notify's own helpers, so a held ping says and stores exactly what a sent one would.
# pylint: disable-next=protected-access
_say, _Lock, _write_json = crew_notify._say, crew_notify._Lock, crew_notify._write_json

HELD_FILE = "held.json"
HELD_LOCK = "held.lock"
SUMMARY_LOCK = "summary.lock"
MAX_SUMMARY = 3500


def _path(root, name):
    """`<worktree>/.work/autopilot/<name>`: each worktree has its own sleep
    state and sleep log, so it holds, reports and clears only its own pings
    (L-0656 review r5) -- never another worktree's, still asleep. Raises
    OSError (could not tell) when the folder resolves anywhere else
    (`check_dir`), so nothing is read or written through a link."""
    top = crew_ticket.toplevel(root) or os.path.abspath(root)
    check_dir(top)
    return os.path.join(top, ".work", "autopilot", name)


def check_dir(top):
    """Raise OSError unless `<top>/.work/autopilot` resolves to itself under
    the real `top` (review r7). A symlink or a Windows junction (which
    `os.path.islink` does not see and O_NOFOLLOW cannot refuse) at `.work`
    or `.work/autopilot` would otherwise read or write outside the
    worktree. It needs no folder to exist, so it runs before any makedirs;
    writers run it again after theirs."""
    folder = os.path.join(top, ".work", "autopilot")
    want = os.path.normcase(os.path.join(os.path.realpath(top), ".work", "autopilot"))
    if os.path.normcase(os.path.realpath(folder)) != want:
        raise OSError(".work/autopilot resolves outside the worktree (a link or a junction); "
                      "nothing is read or written through it")


def _write_guarded(root, name, data):
    """`_write_json` into `.work/autopilot`, re-checked once the folder exists."""
    path = _path(root, name)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    check_dir(os.path.dirname(os.path.dirname(os.path.dirname(path))))
    _write_json(path, data)


def read(root):
    """`(record, why)`: the held record (`{"keys": {...}, "first", "last"}`,
    empty when absent), or None with why for one that is there and cannot be
    read -- never read as nothing held."""
    try:
        path = _path(root, HELD_FILE)
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
    except FileNotFoundError:
        if os.path.lexists(path):
            return None, "it is a dangling link"
        return {"keys": {}}, ""
    except (OSError, ValueError) as exc:
        return None, type(exc).__name__
    if not isinstance(data, dict) or not isinstance(data.get("keys"), dict):
        return None, "it is not an object with a keys object"
    return data, ""


def count(root):
    """`(n, why)`: how many distinct pings are held, or None with why."""
    record, why = read(root)
    return (None, why) if record is None else (len(record["keys"]), "")


def held_line(n, why=""):
    """The summary's line for the held count; None means it could not be read."""
    if n is None:
        return f"held pings: could not be read ({why}); not read as none"
    return f"held pings: {n} (asked for your attention while asleep; not sent)"


def take(root, keys):
    """Remove `keys` (the held pings a delivered summary reported) from the
    record, keeping any held since. Returns how many were removed, or None
    when the record could not be read or written: it is then left as it is."""
    try:
        lock_path = _path(root, HELD_LOCK)
    except OSError:
        return None
    with _Lock(lock_path) as lock:
        if not lock.held:
            return None
        record, _ = read(root)
        if record is None:
            return None
        gone = [key for key in keys if key in record["keys"]]
        for key in gone:
            del record["keys"][key]
        try:
            if record["keys"]:
                _write_guarded(root, HELD_FILE, record)
            elif os.path.lexists(_path(root, HELD_FILE)):
                os.remove(_path(root, HELD_FILE))
        except OSError:
            return None
        return len(gone)


DELIVERED_FILE = "summary-delivered.json"
SENDING, SENT = "sending", "sent"


def read_delivered(root):
    """`(record, why)`: `{"upto": int, "keys": [...], "state", "text"}` for a
    summary whose send started (`sending`) or was confirmed (`sent`, or no
    notifier at all) and whose marker or held-key removal has not finished,
    `{}` when there is none, or None with why for one that cannot be read --
    never read as none, so a summary is never sent twice (review r7)."""
    try:
        path = _path(root, DELIVERED_FILE)
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
    except FileNotFoundError:
        return ({}, "") if not os.path.lexists(path) else (None, "it is a dangling link")
    except (OSError, ValueError) as exc:
        return None, type(exc).__name__
    if not isinstance(data, dict):
        data = {}
    upto, keys, state, text = (data.get(k) for k in ("upto", "keys", "state", "text"))
    shaped = (isinstance(upto, int) and not isinstance(upto, bool) and upto >= 0
              and isinstance(keys, list) and all(isinstance(k, str) for k in keys))
    if not shaped or state not in (SENDING, SENT) or not isinstance(text, str):
        return None, "it is not {upto: int, keys: [str], state: sending|sent, text: str}"
    return {"upto": upto, "keys": keys, "state": state, "text": text}, ""


def write_delivered(root, upto, keys, state=SENDING, text=""):
    """Record a summary: `sending` before the send, `sent` only once it is
    confirmed (review r7). Raises OSError."""
    _write_guarded(root, DELIVERED_FILE, {"upto": int(upto), "keys": sorted(keys),
                                          "state": state, "text": text})


def clear_delivered(root):
    """Remove the delivered record once its cleanup finished; False when it cannot."""
    try:
        os.remove(_path(root, DELIVERED_FILE))
    except FileNotFoundError:
        pass
    except OSError:
        return False
    return True


def summary_lock(root):
    """The lock one morning summary is reported and sent under."""
    return _Lock(_path(root, SUMMARY_LOCK))


def send_summary(root, text, keep=""):
    """Pass the morning summary to the notifier once. Returns `sent`, `off`,
    `filtered`, `missing-credentials` or `failed:<why>`; never raises. A text
    over MAX_SUMMARY is cut, and `keep` (the held-count line) is put back at
    its end, so the count always reaches the owner (review r1)."""
    try:
        cfg, notices = crew_notify.effective_config(root)
        for notice in notices:
            _say(notice)
        provider = cfg.get("provider")
        if not provider or provider == "none":
            return "off"
        if not {"question", "blocker"} & set(cfg.get("events") or ()):
            _say("neither question nor blocker is in notify.events; "
                             "the morning summary is not sent")
            return "filtered"
        if provider != "telegram":  # review r3: unknown is not "off"
            return "failed:unknown notify.provider"
        provider, token, target, stop = crew_notify._credentials(cfg)  # pylint: disable=protected-access
        if stop:
            return stop
        repo = crew_notify._one_line(crew_notify.where(root)["repo"])  # pylint: disable=protected-access
        body = crew_notify.redact(f"Morning summary [{repo}]\n{text}")
        if len(body) > MAX_SUMMARY:
            tail = "\n...\n" + crew_notify.redact(keep) if keep else "\n..."
            body = body[:MAX_SUMMARY - len(tail)] + tail
        ok, why = crew_notify._telegram(token, target, body, False)  # pylint: disable=protected-access
        return "sent" if ok else f"failed:{why}"
    except Exception as exc:  # pylint: disable=broad-except
        return f"failed:{type(exc).__name__}"

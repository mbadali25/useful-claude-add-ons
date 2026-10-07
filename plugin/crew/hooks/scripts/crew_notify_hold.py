"""L-0656: pings held while autopilot is asleep, and the morning summary sent once.

`autopilot.sleep.notifyHold: true` (crew_sleep.read_notify_hold) holds the
pings that only ask for attention while autopilot sleeps. `holds(root, event,
kind)` is asked by `crew_notify.send` after its filters and before anything is
sent; it answers True only when ALL of these hold:

- the event and kind are on HOLDABLE: every `question` and the `blocker` kinds
  `approval` and `rounds`. A positive list: every `deploy` result (a failure,
  an unknown outcome, a silent pass), a refused Stop gate (`gate`), a stalled
  or unknown lane, and a blocker of no or an unknown kind are never held;
- `crew_autopilot.settings` (the one reader of the sleep state) says armed,
  asleep and `notifyHold: true`, and the state is not `tightenOnly` -- a manual
  sleep outside the scheduled window may only tighten until L-1504, and hiding
  the owner's pings is not a tightening;
- the held ping was recorded in `<git-common-dir>/crew/notify/held.json`.

Anything that cannot be told -- a settings read that raises, a record that
cannot be read or written, a lock that cannot be had -- sends the ping as
before: what crew cannot tell never hides one.

A held ping is dropped and counted (the hand-off's recommended answer). The
record keeps one key per distinct message (event, kind, ticket, reason and the
episode/dedupe material `crew_notify._deliver` fingerprints), so a ping
repeated in one waiting episode counts once.

The morning summary: crew_autopilot_sleep.sleep_summary, not asleep, appends
`held_line` to L-0653's summary, empties the record (`take`) and passes the
text to `send_summary` once, under SUMMARY_LOCK so two runs never both send.
`send_summary` uses the configured provider and credentials, silently, and only
when `question` or `blocker` is in `notify.events`: no new event exists.
"""
import datetime
import hashlib
import json
import os

import crew_notify

# crew_notify's own helpers, so a held ping says and stores exactly what a sent one would.
# pylint: disable-next=protected-access
_say, _Lock, _write_json = crew_notify._say, crew_notify._Lock, crew_notify._write_json

HOLDABLE = (("question", "ask"), ("question", "permission"),
            ("blocker", "approval"), ("blocker", "rounds"))
HELD_FILE = "held.json"
HELD_LOCK = "held.lock"
SUMMARY_LOCK = "summary.lock"
MAX_KEYS = 1000
MAX_SUMMARY = 3500


def _path(root, name):
    return os.path.join(crew_notify.state_dir(root), name)


def read(root):
    """`(record, why)`: the held record (`{"keys": {...}, "first", "last"}`,
    empty when absent), or None with why for one that is there and cannot be
    read -- never read as nothing held."""
    path = _path(root, HELD_FILE)
    try:
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


def _asleep_and_holding(root):
    """Whether settings say armed, asleep (not tightenOnly) and notifyHold true."""
    import crew_autopilot  # pylint: disable=import-outside-toplevel
    conf = crew_autopilot.settings(root)
    sleep = conf.get("sleep") or {}
    return (conf.get("armed") is True and sleep.get("state") == "asleep"
            and not sleep.get("tightenOnly") and sleep.get("notifyHold") is True)


def holds(root, event, kind, material=""):
    """True when this ping is held and was recorded (module docstring); never raises."""
    try:
        if (event, kind) not in HOLDABLE or not _asleep_and_holding(root):
            return False
        return _record(root, "|".join([event, str(kind), str(material)]))
    except Exception as exc:  # pylint: disable=broad-except
        _say(f"could not tell whether to hold this ping "
                         f"({type(exc).__name__}); sending it")
        return False


def _record(root, material):
    """Add one key to the held record. False (send instead) when it cannot."""
    key = hashlib.sha256(material.encode("utf-8")).hexdigest()
    with _Lock(_path(root, HELD_LOCK)) as lock:
        if not lock.held:
            _say("held-ping lock busy; sending this ping")
            return False
        record, why = read(root)
        if record is None:
            _say(f"held-ping record could not be read ({why}); sending this ping")
            return False
        keys = record["keys"]
        if key not in keys and len(keys) >= MAX_KEYS:
            _say("held-ping record is full; sending this ping")
            return False
        stamp = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
        keys.setdefault(key, stamp)
        record.update(keys=keys, last=stamp)
        record.setdefault("first", stamp)
        try:
            _write_json(_path(root, HELD_FILE), record)
        except OSError as exc:
            _say(f"held-ping record not written ({type(exc).__name__}); "
                             "sending this ping")
            return False
    _say("asleep with autopilot.sleep.notifyHold: ping held for the morning summary")
    return True


def held_line(n, why=""):
    """The summary's line for the held count; None means it could not be read."""
    if n is None:
        return f"held pings: could not be read ({why}); not read as none"
    return f"held pings: {n} (asked for your attention while asleep; not sent)"


def take(root):
    """Empty the held record, returning how many it held. None when it could
    not be read or emptied: the record is then left as it is."""
    with _Lock(_path(root, HELD_LOCK)) as lock:
        if not lock.held:
            return None
        record, _ = read(root)
        if record is None:
            return None
        n = len(record["keys"])
        if n:
            try:
                os.remove(_path(root, HELD_FILE))
            except OSError:
                return None
        return n


def summary_lock(root):
    """The lock one morning summary is reported and sent under."""
    return _Lock(_path(root, SUMMARY_LOCK))


def send_summary(root, text):
    """Pass the morning summary to the notifier once. Returns `sent`, `off`,
    `filtered`, `missing-credentials` or `failed:<why>`; never raises."""
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
        provider, token, target, stop = crew_notify._credentials(cfg)  # pylint: disable=protected-access
        if stop:
            return stop
        repo = crew_notify._one_line(crew_notify.where(root)["repo"])  # pylint: disable=protected-access
        body = crew_notify.redact(f"Morning summary [{repo}]\n{text}")[:MAX_SUMMARY]
        if provider == "telegram":
            ok, why = crew_notify._telegram(token, target, body, False)  # pylint: disable=protected-access
        else:
            ok, why = crew_notify._teams(target, body)  # pylint: disable=protected-access
        return "sent" if ok else f"failed:{why}"
    except Exception as exc:  # pylint: disable=broad-except
        return f"failed:{type(exc).__name__}"

"""T-0053: autopilot sleep mode, slice 1 -- the nightly window and its
resolver. Pure and read-only: it opens no file and reads no variable of its
own (the clock follows the process time zone; see the last paragraph).

`autopilot.sleep` in `.crew/config.json` (repo only, like the rest of the
`autopilot` block) holds three keys, each default `null`:

- `schedule`: one `HH:MM-HH:MM` string, 24-hour, zero-padded, machine local
  time. Start inclusive, end exclusive; a start later than the end crosses
  midnight. Start equal to end is refused: it would be a 24-hour grant.
- `approval`, `questions`: one of crew_autopilot.POLICIES, or `null` for
  "not overridden". Inside the window each replaces the day value of
  `autopilot.approval` / `autopilot.questions`.

`resolve(block, now, policies)` answers `{"state", "schedule", "overrides",
"warnings"}`; `state` is `off` (no schedule), `awake`, `asleep` or
`unknown`. Anything that cannot be told -- a block that is not an object, a
schedule outside the grammar, a clock that is not a datetime -- is
`unknown`, and a warning names the key. `crew_autopilot` then applies only
an override STRICTER than the day value (human > risk > self), never a
looser one.
`crew_autopilot._settings_at` is the one caller; it calls `resolve` on every
settings read, so a run that crosses the window's end is back on the day
values at its next decision.

The clock is `now()`, nothing else: the machine's local wall-clock time as
the PROCESS sees it, so it follows that process's time zone (`TZ`). crew adds
no environment variable or flag of its own that moves it, and reads none;
tests monkeypatch `now` in-process. A process started with a different `TZ`
does see a different hour, which is the documented risk of local time.

L-0652: the manual state. `crew_autopilot.py sleep` and `wake` keep one
object in `<git-common-dir>/crew/autopilot-sleep.json` (MANUAL_FILE), `{"state":
"asleep"|"awake", "by", "at", "until"}`; that module does the file input and
output, this one only judges the record (`read_manual`) and computes `until`
(`next_edge`, MANUAL_SLEEP_HOURS). A valid, unexpired record beats the
schedule (`resolve`'s `manual`), and the result names its `source`. A record
that cannot be trusted is `unknown`, never "not set": what crew cannot read
never loosens a policy. An `asleep` record counts only while `sleep_allowed`
(`scope.allowCliApproval` exactly true); an `awake` one while the schedule is
asleep or cannot tell is `tightenOnly`: only a night value stricter than the
day value still applies, so neither `wake` nor a planted file can loosen one.
"""
import datetime
import re
import reprlib

OVERRIDES = ("approval", "questions")
MANUAL_FILE = "autopilot-sleep.json"
MANUAL_STATES = ("asleep", "awake")
MANUAL_FIELDS = ("state", "by", "at", "until")
MANUAL_SLEEP_HOURS = 12
MANUAL_MAX = datetime.timedelta(hours=24)
KEYS = ("schedule",) + OVERRIDES
OFF, AWAKE, ASLEEP, UNKNOWN = "off", "awake", "asleep", "unknown"
# What an override crew cannot read counts as: the strictest policy, the
# first of crew_autopilot.STRICTNESS (a test holds the two equal).
STRICTEST = "human"
_REPR = reprlib.Repr()
_REPR.maxlevel, _REPR.maxstring, _REPR.maxother = 3, 60, 60

# The whole string, ASCII digits only (`[0-9]`, never `\d`, which matches
# other scripts' digits too). Hours are range-checked after the match.
_SCHEDULE_RE = re.compile(r"([0-2][0-9]):([0-5][0-9])-([0-2][0-9]):([0-5][0-9])")


def now():
    """The machine's local wall-clock time, naive. The only clock here."""
    return datetime.datetime.now()


def parse_schedule(value):
    """`(start, end, "")` as minutes of the day, or `(None, None, reason)`."""
    if not isinstance(value, str):
        return None, None, f"it is {type(value).__name__}, not an HH:MM-HH:MM string"
    found = _SCHEDULE_RE.fullmatch(value)
    if found is None:
        return None, None, "it is not exactly HH:MM-HH:MM (24-hour, zero-padded, no spaces)"
    start_h, start_m, end_h, end_m = (int(part) for part in found.groups())
    if start_h > 23 or end_h > 23:
        return None, None, "an hour is past 23"
    start, end = start_h * 60 + start_m, end_h * 60 + end_m
    if start == end:
        return None, None, "its start equals its end, which would be a 24-hour window"
    return start, end, ""


def in_window(start, end, minute):
    """Whether `minute` (of the day) is inside `[start, end)`; a start later
    than the end crosses midnight."""
    if start < end:
        return start <= minute < end
    return minute >= start or minute < end


def render(value):
    """`value` for a warning, bounded: `reprlib` caps the nesting depth and
    the length, so a config value nested hundreds deep, or a huge string,
    never raises RecursionError or floods a line; anything that still cannot
    be rendered is named by its type."""
    try:
        return _REPR.repr(value)[:120]
    except Exception:  # pylint: disable=broad-except
        return f"<unprintable {type(value).__name__}>"


def read_overrides(block, policies):
    """`(overrides, warnings)`, each key read on its own: a valid override,
    None for null, or STRICTEST for a non-null value that is not a policy
    (with a warning; `"Human"` included). A key whose override cannot be
    read at all counts as STRICTEST too, and so does every key of a block
    that is not an object (review round 2): what crew cannot read never
    loosens a policy. `crew_autopilot` also calls this on
    its own when `resolve` raised, so a stricter night value still counts."""
    if not isinstance(block, dict):
        return {key: STRICTEST for key in OVERRIDES}, []
    found, warnings = {}, []
    for key in OVERRIDES:
        try:
            found[key], warning = _override(block, key, policies)
        except Exception as exc:  # pylint: disable=broad-except
            found[key] = STRICTEST
            warning = (f"autopilot.sleep.{key} could not be read ({type(exc).__name__}); it "
                       f"counts as {STRICTEST}, the strictest policy")
        warnings += [warning] if warning else []
    return found, warnings


def _override(block, key, policies):
    """`(override, warning)` for one key of a sleep block. A non-null value
    that is not a policy is a night value crew cannot read, so it counts as
    STRICTEST (landing decision, consistent with review round 2's N7): it
    applies asleep, and under unknown as the stricter value, never looser."""
    value = block.get(key)
    if value is None or (isinstance(value, str) and value in policies):
        return value, ""
    return STRICTEST, (f"autopilot.sleep.{key} is {render(value)}, not one of "
                       f"{'|'.join(policies)} or null; it counts as {STRICTEST}, the "
                       "strictest policy, inside the window")


_STRICTER = "per key the stricter of the day value and the night value applies"


def next_edge(minute, when):
    """The first datetime strictly after `when` (naive, truncated to the
    minute) whose time of day is `minute`. For a window's end this is the end
    of the current window when inside it, else the end of the next one."""
    base = when.replace(second=0, microsecond=0)
    edge = base.replace(hour=minute // 60, minute=minute % 60)
    return edge if edge > when else edge + datetime.timedelta(days=1)


def _when(value):
    """A naive datetime from an ISO string, or None."""
    if not isinstance(value, str):
        return None
    try:
        found = datetime.datetime.fromisoformat(value)
    except ValueError:
        return None
    return found if found.tzinfo is None else None


def read_manual(found, when):
    """`{"kind", "state", "by", "at", "until", "warning"}` for the manual
    record. `found` is `("absent", None)`, `("ok", parsed JSON)` or
    `("unreadable", why)`. `kind`: `none` (absent), `valid`, `expired` (well
    formed, `until` not after `when`) or `untrusted` (anything else)."""
    status, data = found
    out = {"kind": "none", "state": None, "by": None, "at": None, "until": None,
           "warning": ""}
    if status == "absent":
        return out
    why = _manual_problem(status, data, when)
    if why:
        kind = "expired" if why.startswith("expired") else "untrusted"
        tail = ("the schedule decides" if kind == "expired" else
                f"it counts as unknown: {_STRICTER}")
        return dict(out, kind=kind, warning=f"{MANUAL_FILE} {why}; {tail}")
    return dict(out, kind="valid", state=data["state"], by=data["by"],
                at=_when(data["at"]), until=_when(data["until"]))


def _manual_problem(status, data, when):
    """Why the record is not a valid, unexpired state, or ""."""
    if status != "ok":
        return f"could not be read ({render(data)})"
    if not isinstance(data, dict):
        return f"is {type(data).__name__}, not an object"
    missing = [key for key in MANUAL_FIELDS if key not in data]
    if missing:
        return f"has no {', '.join(missing)}"
    if data["state"] not in MANUAL_STATES:
        return f"state is {render(data['state'])}, not one of {'|'.join(MANUAL_STATES)}"
    if not isinstance(data["by"], str):
        return f"by is {render(data['by'])}, not text"
    at, until = _when(data["at"]), _when(data["until"])
    if at is None or until is None:
        bad = "at" if at is None else "until"
        return f"{bad} is {render(data[bad])}, not a local ISO time"
    if not isinstance(when, datetime.datetime):
        return f"cannot be judged: the clock read {render(when)}"
    if at > when:
        return f"at {data['at']} is in the future (the clock moved back?)"
    if until - at > MANUAL_MAX or until <= at:
        return f"until {data['until']} is not within 24 hours after at {data['at']}"
    if until <= when:
        return f"expired at {data['until']}"
    return ""


def resolve(block, when, policies, manual=None, sleep_allowed=True):
    """`{"state", "schedule", "overrides", "warnings", "source"}` for
    `autopilot.sleep` (`block`, after the defaults are merged) at the naive
    local datetime `when`. `schedule` is the string only when it parsed;
    `overrides` holds each key's override (`read_overrides`), whatever the
    state. `manual` is `read_manual`'s `found` (L-0652); a valid record adds
    `until` and `by` and wins over the schedule (module docstring)."""
    got = dict(_scheduled(block, when, policies), source="schedule")
    record = read_manual(manual, when) if manual is not None else {"kind": "none"}
    if record["kind"] == "none":
        return got
    got["warnings"] = got["warnings"] + ([record["warning"]] if record["warning"] else [])
    if record["kind"] == "expired":
        return got
    if record["kind"] == "untrusted":
        return dict(got, state=UNKNOWN, source="manual")
    got.update(source="manual", until=record["until"].isoformat(), by=record["by"])
    if record["state"] == ASLEEP and not sleep_allowed:
        got["warnings"].append(f"{MANUAL_FILE} says asleep (set by {render(record['by'])}), but "
                               "scope.allowCliApproval is not exactly true, so it is not "
                               f"honoured; it counts as unknown: {_STRICTER}")
        return dict(got, state=UNKNOWN)
    if record["state"] == AWAKE and got["state"] in (ASLEEP, UNKNOWN):
        return dict(got, state=AWAKE, tightenOnly=True)
    return dict(got, state=record["state"])


def _scheduled(block, when, policies):
    """T-0053's `resolve`: the schedule alone."""
    if not isinstance(block, dict):
        return {"state": UNKNOWN, "schedule": None,
                "overrides": read_overrides(block, policies)[0],
                "warnings": [f"autopilot.sleep is {render(block)}, not an object, so whether "
                             "autopilot is asleep cannot be told; no night value can be read, "
                             f"so both policies take the stricter of the day value and "
                             f"{STRICTEST}"]}
    warnings = [f"autopilot.sleep.{str(key)[:60]} is not available in this crew version; it "
                "has no effect" for key in sorted(k for k in block if k not in KEYS)]
    overrides, problems = read_overrides(block, policies)
    warnings += problems
    value = block.get("schedule")
    if value is None:
        return {"state": OFF, "schedule": None, "overrides": overrides, "warnings": warnings}
    start, end, reason = parse_schedule(value)
    if reason:
        warnings.append(f"autopilot.sleep.schedule is {render(value)}: {reason}, so whether "
                        f"autopilot is asleep cannot be told; {_STRICTER}")
        return {"state": UNKNOWN, "schedule": None, "overrides": overrides,
                "warnings": warnings}
    if not isinstance(when, datetime.datetime):
        warnings.append(f"autopilot.sleep.schedule: the clock read {render(when)}, not a "
                        f"time, so whether autopilot is asleep cannot be told; {_STRICTER}")
        return {"state": UNKNOWN, "schedule": value, "overrides": overrides,
                "warnings": warnings}
    state = ASLEEP if in_window(start, end, when.hour * 60 + when.minute) else AWAKE
    return {"state": state, "schedule": value, "overrides": overrides, "warnings": warnings}

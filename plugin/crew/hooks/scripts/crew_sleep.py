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
(`next_edge`, MANUAL_SLEEP_HOURS). `at` and `until` are UTC-aware ISO times
and are compared in UTC (`to_utc`); a naive one is not trusted. A valid,
unexpired record beats the schedule (`resolve`'s `manual`), and the result
names its `source`. A record that cannot be trusted is `unknown`, never "not
set": what crew cannot read never loosens a policy. An `asleep` record counts
only while `sleep_allowed` (`scope.allowCliApproval` exactly true), and then
only as `tightenOnly` outside the scheduled window: owner decision 2026-10-04
(review B1), until L-1504 lets the approval hook accept only the owner's typed
`/crew:autopilot sleep`, a manual sleep applies a night value only where it is
stricter than the day value, because the session can run the CLI itself. An
`awake` record while the schedule is asleep or cannot tell is `tightenOnly`
too, so neither `wake` nor a planted file can loosen a value.

L-0654: `deploy`, a fourth key, `null` or exactly `nonprod` or `none`
(DEPLOY_OVERRIDES). `resolve` reads it (`read_deploy`; `all` or anything
else is refused with a warning, and the day value stands) and
`deploy_overlay` applies it: asleep, a valid override replaces the day
value of `autopilot.deploy` (stricter-only under `tightenOnly`), and then an
effective `all` reads as `nonprod` -- production never runs unattended
asleep. A manual wake inside the window (`awake` with `tightenOnly`) is
treated the same way, so `wake` never loosens it. Otherwise awake, off or
`unknown`, the day value stands. `deploy_allowed`
reads the result through `crew_autopilot._settings_at`, and its reason
names the sleep state when that changed the answer.

L-0656: `notifyHold`, a fifth key, `null` or exactly `true`
(`read_notify_hold`; anything else warns and holds nothing). `resolve`
passes it through as `notifyHold`; crew_notify_hold.py decides, at send
time, whether a ping is held.

L-0653: the sleep log's text. `log_line` builds one entry,
`- <ISO local time> | <ticket> | <kind> | <text> | <setting>`, every field
folded to one printable line with `|` replaced, so no field can start a
second entry or a `- reported <ISO> upto <n>` marker (`marker_line`). `unreported`
reads the entries after the last marker; `summary_text` groups them by
ticket. The file itself is crew_autopilot_sleep.py's: this module still
opens nothing.
"""
import datetime
import re
import reprlib

OVERRIDES = ("approval", "questions")
MANUAL_FILE = "autopilot-sleep.json"
MANUAL_STATES = ("asleep", "awake")
MANUAL_FIELDS = ("state", "by", "at", "until")
MANUAL_SLEEP_HOURS = 12
# A record may span at most 24 wall-clock hours (one window cycle) and, as a
# backstop, 25 real ones: across a fall-back one cycle is 25 real hours
# (review round 2 FIX-2).
MANUAL_MAX = datetime.timedelta(hours=24)
MANUAL_MAX_REAL = datetime.timedelta(hours=25)
KEYS = ("schedule",) + OVERRIDES + ("deploy", "notifyHold")
DEPLOY_OVERRIDES = ("nonprod", "none")
# crew_autopilot.DEPLOY_VALUES' order, loosest last (a test holds the two equal).
DEPLOY_ORDER = ("none", "nonprod", "all")
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


def to_utc(when):
    """The naive local datetime `when` as an aware UTC one. A wall-clock time
    that does not exist (the hour a spring-forward skips) resolves forward to
    the later instant, so an `until` there never ends an hour early (review
    round 2 NIT 1); an ambiguous one keeps the fold it was given."""
    found = when.astimezone(datetime.timezone.utc)
    if found.astimezone().replace(tzinfo=None, fold=0) == when.replace(fold=0):
        return found
    return max(when.replace(fold=fold).astimezone(datetime.timezone.utc) for fold in (0, 1))


def _wall(when):
    """The aware `when` as a naive local wall-clock time."""
    return when.astimezone().replace(tzinfo=None, fold=0)


def _when(value):
    """An aware UTC datetime from a UTC-aware ISO string; None for anything
    else, a naive time included (review N1)."""
    if not isinstance(value, str):
        return None
    try:
        found = datetime.datetime.fromisoformat(value)
    except ValueError:
        return None
    return None if found.tzinfo is None else found.astimezone(datetime.timezone.utc)


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
        return f"{bad} is {render(data[bad])}, not a UTC-aware ISO time"
    if not isinstance(when, datetime.datetime):
        return f"cannot be judged: the clock read {render(when)}"
    when = to_utc(when)
    if at > when:
        return f"at {data['at']} is in the future (the clock moved back?)"
    wall = _wall(until) - _wall(at)
    if until - at > MANUAL_MAX_REAL or wall > MANUAL_MAX or until <= at:
        return (f"until {data['until']} is not within 24 hours (24 wall-clock and 25 real) "
                f"after at {data['at']}")
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
    deploy, refused = read_deploy(block)
    hold, unheld = read_notify_hold(block)
    got = dict(_scheduled(block, when, policies), source="schedule", deploy=deploy,
               notifyHold=hold)
    got["warnings"] = got["warnings"] + [w for w in (refused, unheld) if w]
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
    if record["state"] == ASLEEP:
        return dict(got, state=ASLEEP, tightenOnly=got["state"] != ASLEEP)
    if got["state"] in (ASLEEP, UNKNOWN):
        return dict(got, state=AWAKE, tightenOnly=True)
    return dict(got, state=AWAKE)


def read_deploy(block):
    """`(override, warning)` for `autopilot.sleep.deploy` (L-0654): None for
    null or a block that is not an object, the value when it is exactly one
    of DEPLOY_OVERRIDES, else None with a warning -- the day value stands, and
    production is never unattended asleep."""
    value = block.get("deploy") if isinstance(block, dict) else None
    if value is None or (isinstance(value, str) and value in DEPLOY_OVERRIDES):
        return value, ""
    return None, (f"autopilot.sleep.deploy is {render(value)}, not null, nonprod or none; the "
                  "day value of autopilot.deploy stands, and production never runs unattended "
                  "asleep")


def read_notify_hold(block):
    """`(hold, warning)` for `autopilot.sleep.notifyHold` (L-0656): True only
    for exactly `true`; None for null or a block that is not an object; None
    with a warning for anything else (`false`, `"true"` and `1` included) --
    a value crew cannot read never hides a ping."""
    value = block.get("notifyHold") if isinstance(block, dict) else None
    if value is None or value is True:
        return value, ""
    return None, (f"autopilot.sleep.notifyHold is {render(value)}, not null or true; no ping is "
                  "held")


def deploy_overlay(deploy, sleep, day):
    """The effective `autopilot.deploy` for `resolve`'s answer `sleep`, given
    the day value `deploy` (already one of DEPLOY_ORDER). Notes the day value
    in `day["deploy"]`; when sleep changed it, adds `deploy` to
    `sleep["applied"]` and a `deployNote` for `deploy_allowed`'s reason."""
    day["deploy"] = deploy
    # A manual wake inside the window (or beside a schedule that cannot be
    # told) is tightenOnly: it never loosens the night's deploy (review r2).
    woke = sleep.get("state") == AWAKE and sleep.get("tightenOnly")
    if sleep.get("state") != ASLEEP and not woke:
        return deploy
    value, override = deploy, sleep.get("deploy")
    if override in DEPLOY_OVERRIDES and not (
            sleep.get("tightenOnly") and DEPLOY_ORDER.index(override) > DEPLOY_ORDER.index(deploy)):
        value = override
    value = "nonprod" if value == "all" else value
    if value != deploy:
        sleep["applied"] = list(sleep.get("applied") or []) + ["deploy"]
        if woke:
            why = "awake by hand inside the sleep window, which only tightens"
        elif sleep.get("source") == "manual":
            why = f"asleep by hand until {sleep.get('until')}"
        else:
            why = f"asleep {sleep.get('schedule')}"
        sleep["deployNote"] = f" ({why}; day value {deploy})"
    return value


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


# --- L-0653: the sleep log's text (the file is crew_autopilot_sleep.py's) --------

LOG_NAME = "sleep-log.md"
LOG_KINDS = ("approved", "answered", "note")
LOG_FIELD_MAX = 300
_ENTRY_RE = re.compile(r"^- (\S+) \| (.*?) \| (approved|answered|note) \| (.*?) \| (.*)$")
_MARK_RE = re.compile(r"^- reported (\S+)(?: upto ([0-9]{1,15}))?$")


def log_field(value):
    """One field: printable, one line, no `|`, at most LOG_FIELD_MAX, `-` when empty."""
    text = value if isinstance(value, str) else render(value)
    text = " ".join("".join(c if c.isprintable() else " " for c in text).split())
    return text.replace("|", "/")[:LOG_FIELD_MAX] or "-"


def log_line(when, ticket, kind, text, setting):
    """One log entry, newline included. `when` is a naive local datetime."""
    if kind not in LOG_KINDS:
        raise ValueError(f"kind {kind!r} is not one of {'|'.join(LOG_KINDS)}")
    stamp = when.replace(microsecond=0).isoformat()
    return " | ".join([f"- {stamp}", log_field(ticket), kind, log_field(text),
                       log_field(setting)]) + "\n"


def marker_line(when, upto):
    """The `- reported <ISO> upto <n>` line `sleep-summary` appends after
    reporting: `n` is the byte length of the log it read, so an entry another
    process appended after that read and before this marker is still
    unreported (L-0653 review r1). A marker with no `upto` covers every line
    above it."""
    return f"- reported {when.replace(microsecond=0).isoformat()} upto {int(upto)}\n"


def unreported(text):
    """The entries the last marker does not cover, as `{"at", "ticket",
    "kind", "text", "setting"}`, in order: those starting at or after its
    `upto` byte offset (UTF-8, "\n"-split lines, as crew_autopilot_sleep appends them).
    A line that is neither is not an entry."""
    entries, cutoff, offset = [], 0, 0
    for raw in (text or "").split("\n"):
        line = raw[:-1] if raw.endswith("\r") else raw
        mark = _MARK_RE.match(line)
        if mark:
            cutoff = int(mark.group(2)) if mark.group(2) else offset
        else:
            found = _ENTRY_RE.match(line)
            if found:
                entries.append((offset, dict(zip(("at", "ticket", "kind", "text", "setting"),
                                                 found.groups()))))
        offset += len(raw.encode("utf-8")) + 1
    return [entry for start, entry in entries if start >= cutoff]


def malformed(text):
    """The 1-based numbers of the non-blank lines that are neither an entry
    nor a marker (a truncated or hand-edited line): the log then cannot be
    read as "no decisions" (L-0653 review r2)."""
    return [n for n, raw in enumerate((text or "").split("\n"), 1)
            if raw.strip() and not _MARK_RE.match(raw.rstrip("\r"))
            and not _ENTRY_RE.match(raw.rstrip("\r"))]


def summary_text(entries):
    """The morning summary: a heading line, then the entries grouped by ticket."""
    tickets = []
    for entry in entries:
        if entry["ticket"] not in tickets:
            tickets.append(entry["ticket"])
    lines = [f"sleep summary: {len(entries)} decision(s) while asleep"]
    for ticket in tickets:
        lines.append(f"{ticket}:")
        lines += [f"  {e['at']} {e['kind']}: {e['text']} ({e['setting']})"
                  for e in entries if e["ticket"] == ticket]
    return "\n".join(lines)

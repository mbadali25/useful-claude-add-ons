"""T-0053: autopilot sleep mode, slice 1 -- the nightly window and its
resolver. Pure and read-only: it opens no file and reads no environment.

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
`unknown`, which applies no override, and a warning names the key.
`crew_autopilot._settings_at` is the one caller; it calls `resolve` on every
settings read, so a run that crosses the window's end is back on the day
values at its next decision.

The clock is `now()`, nothing else. There is deliberately no environment
variable or flag that moves it: one the session could set would let it grant
itself the night values. Tests monkeypatch `now` in-process.
"""
import datetime
import re

OVERRIDES = ("approval", "questions")
KEYS = ("schedule",) + OVERRIDES
OFF, AWAKE, ASLEEP, UNKNOWN = "off", "awake", "asleep", "unknown"

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


def _overrides(block, policies, warnings):
    found = {}
    for key in OVERRIDES:
        value = block.get(key)
        if value is None or (isinstance(value, str) and value in policies):
            found[key] = value
            continue
        found[key] = None
        warnings.append(f"autopilot.sleep.{key} is {value!r}, not one of "
                        f"{'|'.join(policies)} or null; autopilot.{key} keeps its day value")
    return found


def resolve(block, when, policies):
    """`{"state", "schedule", "overrides", "warnings"}` for `autopilot.sleep`
    (`block`, after the defaults are merged) at the naive local datetime
    `when`. `schedule` is the string only when it parsed; `overrides` holds
    each valid override or None, whatever the state."""
    none = {key: None for key in OVERRIDES}
    if not isinstance(block, dict):
        return {"state": UNKNOWN, "schedule": None, "overrides": none,
                "warnings": [f"autopilot.sleep is {block!r}, not an object, so whether "
                             "autopilot is asleep cannot be told; the day values apply"]}
    warnings = [f"autopilot.sleep.{key} is not available in this crew version; it has no "
                "effect" for key in sorted(k for k in block if k not in KEYS)]
    overrides = _overrides(block, policies, warnings)
    value = block.get("schedule")
    if value is None:
        return {"state": OFF, "schedule": None, "overrides": overrides, "warnings": warnings}
    start, end, reason = parse_schedule(value)
    if reason:
        warnings.append(f"autopilot.sleep.schedule is {value!r}: {reason}, so whether "
                        "autopilot is asleep cannot be told; the day values apply")
        return {"state": UNKNOWN, "schedule": None, "overrides": overrides,
                "warnings": warnings}
    if not isinstance(when, datetime.datetime):
        warnings.append(f"autopilot.sleep.schedule: the clock read {when!r}, not a time, so "
                        "whether autopilot is asleep cannot be told; the day values apply")
        return {"state": UNKNOWN, "schedule": value, "overrides": overrides,
                "warnings": warnings}
    state = ASLEEP if in_window(start, end, when.hour * 60 + when.minute) else AWAKE
    return {"state": state, "schedule": value, "overrides": overrides, "warnings": warnings}

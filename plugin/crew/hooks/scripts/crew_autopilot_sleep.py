"""L-0652: the manual sleep state behind `crew_autopilot.py sleep` and `wake`,
split out of `crew_autopilot.py` (pylint's module-length limit) when the
1.2.0 feature rush ported T-0022 onto it. The code is unchanged: it writes or
removes only `<git-common-dir>/crew/autopilot-sleep.json` (`sleep` only
where `scope.allowCliApproval` is exactly true), and `crew_autopilot`'s
settings read it through `_manual_found`. `crew_autopilot` is reached
through `ap`, a lazy handle, so importing this module never imports it back.

    python3 crew_autopilot.py sleep --root . [--by <text>]
    python3 crew_autopilot.py wake --root .
    python3 crew_autopilot.py sleep-note --root . --ticket <id> --kind answered|note --text <t>
    python3 crew_autopilot.py sleep-summary --root .

L-0653: the sleep log, `.work/autopilot/sleep-log.md` (local: `.work/` is
ignored; never read to decide anything). Every write is one `os.write` of one
whole line to a descriptor opened with O_APPEND, so nothing is truncated and
two writers cannot interleave inside a line. `approve` appends an `approved`
entry while asleep (`log_approval`; a log that cannot be written leaves the
approval standing and says so); `sleep-note` appends an `answered` or `note`
entry, only while asleep (exit 2 and nothing written awake); `sleep-summary`
prints the entries not yet reported, grouped by ticket, and -- not while
asleep -- appends a `- reported` marker; `wake` prints it after its state
line; `settings` warns while unreported entries wait (`log_warnings`). A log
that is there and cannot be read is said so, never "nothing to report".

L-0656: the summary also carries the pings `autopilot.sleep.notifyHold` held
(crew_notify_hold.py), `settings` warns while any are held and not asleep,
and a summary reported awake is passed to the notifier once, under a lock,
and empties the held record.
"""
import datetime
import importlib
import json
import os
import re
import stat
import sys

import crew_config
import crew_notify_hold
import crew_sleep
import crew_ticket


class _Lazy:  # pylint: disable=too-few-public-methods
    """`crew_autopilot`'s attributes, looked up when used (it imports this module)."""

    def __getattr__(self, name):
        return getattr(importlib.import_module("crew_autopilot"), name)


ap = _Lazy()


def _manual_path(top):
    """`<git-common-dir>/crew/autopilot-sleep.json` (L-0652): shared by every
    worktree of the repository, never read from a worktree or `.work/`."""
    state = crew_ticket.state_dir(top)
    if state is None:
        raise crew_ticket.TicketError("not a git repository, so there is no "
                                      "<git-common-dir>/crew/ for the sleep state")
    return os.path.join(state, crew_sleep.MANUAL_FILE)


def _manual_found(top):
    """`crew_sleep.read_manual`'s `found`: `("absent", None)`, `("ok", data)`
    or `("unreadable", why)`. A directory with no `.git` entry at all has no
    `<git-common-dir>` where `sleep` could have written, so it is absent; a
    checkout whose state directory git cannot name raises, which `_sleep_at`
    takes as could-not-tell."""
    if not os.path.lexists(os.path.join(top, ".git")) and crew_ticket.state_dir(top) is None:
        return "absent", None
    path = _manual_path(top)
    try:
        mode = os.lstat(path).st_mode
    except FileNotFoundError:
        return "absent", None
    except OSError as exc:
        return "unreadable", f"{type(exc).__name__} on lstat"
    if not stat.S_ISREG(mode):
        return "unreadable", "it is not a regular file"
    text = _read_regular(path)
    if text is None:
        return "unreadable", "it is not a regular file, or could not be read"
    try:
        return "ok", json.loads(text)
    except ValueError:
        return "unreadable", "not JSON"


MANUAL_MAX_BYTES = 65536


def _read_regular(path):
    """The text of `path` when it is still a regular file once opened (review
    N3): opened without following a final symlink and without blocking on a
    FIFO, re-checked with `fstat`, read up to MANUAL_MAX_BYTES. None
    otherwise."""
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    try:
        handle = os.open(path, flags)
    except OSError:
        return None
    try:
        if not stat.S_ISREG(os.fstat(handle).st_mode):
            return None
        data = os.read(handle, MANUAL_MAX_BYTES + 1)
    except OSError:
        return None
    finally:
        os.close(handle)
    if len(data) > MANUAL_MAX_BYTES:
        return None
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return None


def sleep_now(root, by="cli"):
    """(exit code, text) for `crew_autopilot.py sleep` (L-0652): write an
    `asleep` record until the end of the current or next window, or for
    MANUAL_SLEEP_HOURS with no schedule. Exit 2, writing nothing, unless
    `scope.allowCliApproval` is exactly true, autopilot is armed, the config
    can be told and at least one `autopilot.sleep` override is set: the
    manual state grants only what the night values already configure."""
    top = crew_ticket.toplevel(root) or os.path.abspath(root)
    cause = ap._unreadable_autopilot(top)
    if cause:
        return 2, f"refused: {cause}, so sleep mode cannot be told"
    if not crew_ticket.cli_approval_allowed(top):
        return 2, (f"refused: {ap.ALLOW_CLI} is not exactly true in .crew/config.json, so only "
                   "the schedule puts autopilot to sleep")
    conf = ap._settings_at(top)
    if not conf["armed"]:
        return 2, "refused: autopilot.mode is not plan, so there is nothing to put to sleep"
    block = ap._sleep_block(top, crew_config.resolve_config(top).get("autopilot") or {})
    when = crew_sleep.now()
    found = crew_sleep.resolve(block, when, ap.POLICIES)
    if found["state"] == crew_sleep.UNKNOWN:
        return 2, (f"refused: autopilot.sleep.schedule or the block cannot be read "
                   f"({'; '.join(found['warnings'])[:200]})")
    tightens = [key for key in crew_sleep.OVERRIDES if _stricter(
        found["overrides"].get(key), conf["day"].get(key))]
    day_deploy = conf["day"].get("deploy", conf["deploy"])  # L-0654: deploy tightens too
    if crew_sleep.deploy_overlay(day_deploy, {"state": crew_sleep.ASLEEP, "tightenOnly": True,
                                              "deploy": found.get("deploy")}, {}) != day_deploy:
        tightens.append("deploy")
    if found["state"] != crew_sleep.ASLEEP and not tightens:
        return 2, ("refused: no autopilot.sleep override is stricter than its day value, and "
                   "until L-1504 a manual sleep only tightens, so it would change nothing")
    if found["schedule"]:
        until = crew_sleep.next_edge(crew_sleep.parse_schedule(found["schedule"])[1], when)
    else:
        until = when + datetime.timedelta(hours=crew_sleep.MANUAL_SLEEP_HOURS)
    record = {"state": crew_sleep.ASLEEP, "by": by,
              "at": crew_sleep.to_utc(when).replace(microsecond=0).isoformat(),
              "until": crew_sleep.to_utc(until).replace(microsecond=0).isoformat()}
    check = crew_sleep.read_manual(("ok", record), when)
    if check["kind"] != "valid":
        # Review round 2 FIX-2: never report a sleep the reader would distrust.
        return 2, ap._one_line(f"refused: the record sleep would write is not trusted by its own "
                            f"reader ({check['warning'][:200]}); nothing written")
    crew_ticket._write_json(_manual_path(top), record)  # pylint: disable=protected-access
    what = ("the scheduled night" if found["state"] == crew_sleep.ASLEEP
            else f"tightens {','.join(tightens)}")
    return 0, (f"asleep until {ap._hhmm(record['until'])} (set by {ap._cli_value(by)[:60]}; {what}); "
               f"{ap.AUTOPILOT} wake undoes it")


def _stricter(night, day):
    """Whether the night override `night` is stricter than the day value."""
    return night in ap.STRICTNESS and day in ap.STRICTNESS and (
        ap.STRICTNESS.index(night) < ap.STRICTNESS.index(day))


def wake_now(root):
    """(exit code, text) for `crew_autopilot.py wake` (L-0652). Never refuses
    for policy. Inside the scheduled window it writes an `awake` record until
    the window's end; otherwise it removes any record, since the schedule
    already says awake. Nothing to undo: `already awake`, nothing written."""
    top = crew_ticket.toplevel(root) or os.path.abspath(root)
    path, when = _manual_path(top), crew_sleep.now()
    state, schedule, why = crew_sleep.UNKNOWN, None, ap._unreadable_autopilot(top)
    if not why:
        block = ap._sleep_block(top, crew_config.resolve_config(top).get("autopilot") or {})
        found = crew_sleep.resolve(block, when, ap.POLICIES)
        state, schedule = found["state"], found["schedule"]
        why = "; ".join(found["warnings"])
    if state == crew_sleep.ASLEEP:
        until = crew_sleep.next_edge(crew_sleep.parse_schedule(schedule)[1], when)
        record = {"state": crew_sleep.AWAKE, "by": "cli",
                  "at": crew_sleep.to_utc(when).replace(microsecond=0).isoformat(),
                  "until": crew_sleep.to_utc(until).replace(microsecond=0).isoformat()}
        crew_ticket._write_json(path, record)  # pylint: disable=protected-access
        return 0, f"awake; the schedule resumes at {ap._hhmm(record['until'])}"
    if not os.path.lexists(path):
        return 0, "already awake"
    os.unlink(path)
    if state == crew_sleep.UNKNOWN:
        # Review N2: never "resumes at <now>" for a schedule that cannot be told.
        return 0, ap._one_line(f"awake; whether the schedule is asleep cannot be told "
                            f"({ap._safe_text(why or 'unreadable', str)[:160]})")
    if state == crew_sleep.OFF:
        return 0, "awake; no schedule is set"
    return 0, f"awake; the schedule resumes at {when.strftime('%H:%M')}"


# --- L-0653: the sleep log --------------------------------------------------------

NOTHING = "no unreported sleep decisions"


def log_path(top):
    return os.path.join(top, ".work", "autopilot", crew_sleep.LOG_NAME)


def _read_log(top):
    """`(text, why)`: the log's text ("" when absent), or None with why for a
    log that is there and cannot be read -- never read as empty."""
    path = log_path(top)
    try:
        with open(path, encoding="utf-8", newline="") as handle:  # byte-exact for `upto`
            return handle.read(), ""
    except FileNotFoundError:
        return ("", "") if not os.path.lexists(path) else (None, "it is a dangling link")
    except (OSError, ValueError) as exc:
        return None, f"{type(exc).__name__}"


def _append(top, line):
    """One whole line, one `os.write`, O_APPEND: never truncates, never splits.
    Under `sleep-log.lock` too: on Windows O_APPEND is a seek then a write,
    not one step, so two writers could overwrite each other's line (Windows
    CI, 2026-10-07); a lock that cannot be had there refuses the append."""
    path = log_path(top)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    data = line.encode("utf-8")
    with crew_notify_hold._Lock(path[:-len(".md")] + ".lock") as lock:  # pylint: disable=protected-access
        if not lock.held and os.name == "nt":
            raise OSError("the sleep log lock is busy")
        fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT | getattr(os, "O_BINARY", 0),
                     0o644)
        try:
            if os.write(fd, data) != len(data):
                raise OSError("short write to the sleep log")
        finally:
            os.close(fd)


def _setting(conf, key):
    """`sleep.<key>=<night> (day <day>)` when the night value applied, else `<key>=<value>`."""
    if key in (conf["sleep"].get("applied") or []):
        return f"sleep.{key}={conf[key]} (day {conf['day'].get(key)})"
    return f"{key}={conf[key]}"


def log_approval(top, ticket, decision):
    """`approve`'s entry, after its receipt (L-0653): "" when awake or written,
    else a warning line -- an approval is never undone by its log. Judged by
    the pinned `decision` the receipt was written under, never a second
    settings read (review r2: the window may end in between)."""
    try:
        if not decision.get("asleep"):
            return ""
        day = re.search(r"day value (\w+)", decision.get("sleep") or "")
        setting = (f"sleep.approval={decision['policy']} (day {day.group(1)})" if day
                   else f"approval={decision['policy']}")
        _append(top, crew_sleep.log_line(crew_sleep.now(), ticket, "approved",
                                         "plan approved by autopilot", setting))
    except Exception as exc:  # noqa: BLE001  # pylint: disable=broad-except
        return "\n" + ap._one_line(f"warning: sleep log not written ({ap._failure(exc)})")
    return ""


def sleep_note(root, ticket, kind, text):
    """(exit code, text) for `sleep-note`: one entry, only while asleep."""
    crew_ticket.check_ticket(ticket)
    top = crew_ticket.toplevel(root) or os.path.abspath(root)
    if kind not in ("answered", "note"):
        return 2, "refused: --kind is answered or note"
    conf = ap.settings(top)
    if conf["sleep"]["state"] != crew_sleep.ASLEEP:
        return 2, f"refused: autopilot is not asleep ({conf['sleep']['state']}); nothing written"
    setting = _setting(conf, "questions") if kind == "answered" else (
        "sleep=manual" if conf["sleep"].get("source") == "manual"  # review r5
        else f"sleep={conf['sleep'].get('schedule') or 'manual'}")
    _append(top, crew_sleep.log_line(crew_sleep.now(), ticket, kind, text, setting))
    return 0, "noted"


def sleep_summary(root):
    """(exit code, text) for `sleep-summary`: the unreported entries and the
    held pings (L-0656), then -- only in a known awake or off state, never
    asleep or `unknown` (review r3) -- the text passed to the notifier once
    and, once delivered (or with no notifier), one marker and the reported
    held pings removed, all under one lock taken before anything is read. A
    failed send keeps both pending. A delivered summary is recorded
    (`summary-delivered.json`) before its cleanup, so a cleanup that fails is
    finished by the next run and the summary is never sent twice."""
    top = crew_ticket.toplevel(root) or os.path.abspath(root)
    state = ap.settings(top)["sleep"]["state"]
    if state not in (crew_sleep.AWAKE, crew_sleep.OFF):
        code, out, _, _, _ = _summary(top)
        why = ("still asleep" if state == crew_sleep.ASLEEP
               else "whether autopilot is asleep cannot be told")
        return code, out + ("" if code or out == NOTHING else
                            f"\n({why}: reported again once it is awake)")
    with crew_notify_hold.summary_lock(top) as lock:
        if not lock.held:
            return 1, ("refused: another run is reporting the sleep summary (the summary lock "
                       "is held); nothing marked or sent")
        unfinished = _finish_delivered(top)
        if unfinished:
            return 1, unfinished
        code, out, text, held, upto = _summary(top)
        if code or out == NOTHING:
            return code, out
        word = crew_notify_hold.send_summary(
            top, out, crew_notify_hold.held_line(len(held)) if held else "")
        if word not in ("sent", "off", "filtered"):
            return 1, out + (f"\nnotify: {word}; nothing marked reported - the summary is "
                             "reported and sent again next run")
        if word == "sent":
            try:
                crew_notify_hold.write_delivered(top, upto, held)
            except OSError as exc:
                return 1, out + (f"\nnotify: sent, but the delivery could not be recorded "
                                 f"({type(exc).__name__}); nothing marked, so it may be sent "
                                 "again")
        left = _cleanup(top, text, upto, held)
        if left is None and word == "sent" and not crew_notify_hold.clear_delivered(top):
            left = "the delivered record could not be removed"
        return 0, out + ("" if word == "off" else f"\nnotify: {word}") + (
            "" if left is None else f"\n({left}; finished by the next run, never sent again)")


def _cleanup(top, text, upto, held):
    """Mark the log reported up to `upto` and remove the `held` keys: None
    when both are done, else what is left."""
    try:
        if crew_sleep.unreported(text) and crew_sleep.last_cutoff(text) < upto:
            _append(top, crew_sleep.marker_line(crew_sleep.now(), upto))
    except OSError as exc:
        return f"the reported marker could not be written ({type(exc).__name__})"
    if held and crew_notify_hold.take(top, held) is None:
        return "the held record could not be emptied"
    return None


def _finish_delivered(top):
    """"" once no delivered summary is left half cleaned; else why not (exit 1)."""
    record, why = crew_notify_hold.read_delivered(top)
    if record is None:
        return (f"refused: {crew_notify_hold.DELIVERED_FILE} could not be read ({why}); "
                "nothing sent, so a delivered summary is never sent twice")
    if not record:
        return ""
    text, why = _read_log(top)
    left = (f"the sleep log could not be read ({why})" if text is None
            else _cleanup(top, text, record["upto"], record["keys"]))
    if left is None and crew_notify_hold.clear_delivered(top):
        return ""
    return (f"refused: a delivered summary's cleanup is not finished ({left or 'its record '
            'could not be removed'}); nothing sent")


SUMMARY_BUDGET = 3000  # characters of decisions in one summary; the rest waits for the next


def _summary(top):
    """(exit code, text, log text, held keys, upto): the summary of what is
    unreported and held, or why not; the log text and the held keys are what
    the summary was made from, and `upto` is the end of the last decision it
    shows. Decisions past SUMMARY_BUDGET wait for the next summary, so a
    message the notifier must cut never marks a decision it did not carry
    (L-0656 review r4)."""
    text, why = _read_log(top)
    if text is None:
        return 1, f"refused: the sleep log could not be read ({why}); it is not empty", None, [], 0
    bad = crew_sleep.malformed(text)
    if bad:
        return 1, (f"refused: the sleep log has {len(bad)} line(s) that are not entries (line "
                   f"{', '.join(map(str, bad[:5]))}); it is not read as empty - fix or remove "
                   f"them in {log_path(top)}"), None, [], 0
    record, held_why = crew_notify_hold.read(top)
    held = sorted(record["keys"]) if record is not None else []
    spans = crew_sleep.unreported_spans(text)
    if not spans and record is not None and not held:
        return 0, NOTHING, text, [], 0
    if not spans and record is None:
        return 1, f"refused: {crew_notify_hold.held_line(None, held_why)}", text, [], 0
    shown = []
    for span in spans:
        if shown and len(crew_sleep.summary_text([e for _s, _e, e in shown + [span]])) > SUMMARY_BUDGET:
            break
        shown.append(span)
    out = crew_sleep.summary_text([e for _s, _e, e in shown])
    if len(shown) < len(spans):
        out += f"\n({len(spans) - len(shown)} more decision(s): reported in the next summary)"
    upto = shown[-1][1] if shown else crew_sleep.last_cutoff(text)
    return 0, out + ("" if record is not None and not held else "\n" + crew_notify_hold.held_line(
        None if record is None else len(held), held_why)), text, held, upto


def with_log_warnings(top, conf):
    """`conf` (`settings`' answer) with `log_warnings` added to its warnings."""
    conf["warnings"] = list(conf["warnings"]) + log_warnings(top, conf)
    return conf


def log_warnings(top, conf):
    """`settings`' warnings about the log (L-0653) and the held pings (L-0656):
    unreported entries or held pings while not asleep, or a log or held
    record that cannot be read. Never raises."""
    found, state = [], conf["sleep"]["state"]
    # Awake (or off): run the summary. Unknown: say so, but it reports only once
    # the state can be told (review r3). Asleep: nothing to do yet.
    tail = ("run crew_autopilot.py sleep-summary" if state in (crew_sleep.AWAKE, crew_sleep.OFF)
            else "whether autopilot is asleep cannot be told, so sleep-summary reports them "
                 "once it can" if state == crew_sleep.UNKNOWN else "")
    try:
        text, why = _read_log(top)
        if text is not None and crew_sleep.malformed(text):
            text, why = None, "it has lines that are not entries"
        if text is None:
            found.append(f"sleep log could not be read ({why}); {log_path(top)} is not read as "
                         "empty")
        elif crew_sleep.unreported(text) and tail:
            found.append(f"{len(crew_sleep.unreported(text))} sleep decisions are unreported - "
                         + tail)
    except Exception as exc:  # noqa: BLE001  # pylint: disable=broad-except
        found.append(f"sleep log could not be read ({ap._failure(exc)})")
    try:
        held, why = crew_notify_hold.count(top)
        if held is None:
            found.append(f"held pings could not be read ({why}); not read as none - run "
                         "crew_autopilot.py sleep-summary")
        elif held and tail:
            found.append(f"{held} pings were held while asleep - " + tail)
    except Exception as exc:  # noqa: BLE001  # pylint: disable=broad-except
        found.append(f"held pings could not be read ({ap._failure(exc)})")
    return found


def main(args):
    """`sleep`, `wake` (L-0652), `sleep-note` and `sleep-summary` (L-0653).
    `wake` prints the summary after its state line. A crash is a refusal (exit 1)."""
    try:
        if args.action == "sleep-note":
            code, text = sleep_note(args.root, args.ticket, args.kind, args.text)
        elif args.action == "sleep-summary":
            code, text = sleep_summary(args.root)
        elif args.action == "sleep":
            code, text = sleep_now(args.root, args.by)
        else:
            code, text = wake_now(args.root)
            summary_code, summary = sleep_summary(args.root) if code == 0 else (0, NOTHING)
            text += "" if summary == NOTHING else "\n" + summary
            code = code or summary_code  # awake either way; a failed summary is not hidden
    except Exception as exc:  # noqa: BLE001  # pylint: disable=broad-except
        code, text = 1, ap._one_line(f"refused: {ap._failure(exc)}")
    sys.stdout.write(text + "\n")
    return code


def add_parsers(sub):
    """`sleep`, `wake`, `sleep-note` and `sleep-summary` on crew_autopilot.py's subparsers."""
    for name in ("sleep", "wake", "sleep-note", "sleep-summary"):
        sub.add_parser(name).add_argument("--root", default=".")
    sub.choices["sleep"].add_argument("--by", default="cli")
    note = sub.choices["sleep-note"]
    note.add_argument("--ticket", required=True)
    note.add_argument("--kind", required=True)
    note.add_argument("--text", required=True)

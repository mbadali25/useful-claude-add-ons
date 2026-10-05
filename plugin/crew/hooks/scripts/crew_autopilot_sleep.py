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
"""
import datetime
import importlib
import json
import os
import stat
import sys

import crew_config
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
        with open(path, encoding="utf-8") as handle:
            return handle.read(), ""
    except FileNotFoundError:
        return ("", "") if not os.path.lexists(path) else (None, "it is a dangling link")
    except (OSError, ValueError) as exc:
        return None, f"{type(exc).__name__}"


def _append(top, line):
    """One whole line, one `os.write`, O_APPEND: never truncates, never splits."""
    path = log_path(top)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    data = line.encode("utf-8")
    fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT | getattr(os, "O_BINARY", 0), 0o644)
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


def log_approval(top, ticket):
    """`approve`'s entry, after its receipt (L-0653): "" when awake or written,
    else a warning line -- an approval is never undone by its log."""
    try:
        conf = ap.settings(top)
        if conf["sleep"]["state"] != crew_sleep.ASLEEP:
            return ""
        _append(top, crew_sleep.log_line(crew_sleep.now(), ticket, "approved",
                                         "plan approved by autopilot", _setting(conf, "approval")))
    except Exception as exc:  # noqa: BLE001  # pylint: disable=broad-except
        return ap._one_line(f"\nwarning: sleep log not written ({ap._failure(exc)})")
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
        f"sleep={conf['sleep'].get('schedule') or conf['sleep'].get('source', 'manual')}")
    _append(top, crew_sleep.log_line(crew_sleep.now(), ticket, kind, text, setting))
    return 0, "noted"


def sleep_summary(root):
    """(exit code, text) for `sleep-summary`: the unreported entries, then --
    not while asleep -- one marker. Nothing unreported writes nothing."""
    top = crew_ticket.toplevel(root) or os.path.abspath(root)
    text, why = _read_log(top)
    if text is None:
        return 1, f"refused: the sleep log could not be read ({why}); it is not empty"
    entries = crew_sleep.unreported(text)
    if not entries:
        return 0, NOTHING
    out = crew_sleep.summary_text(entries)
    if ap.settings(top)["sleep"]["state"] == crew_sleep.ASLEEP:
        return 0, out + "\n(still asleep: reported again after the window ends)"
    _append(top, crew_sleep.marker_line(crew_sleep.now()))
    return 0, out


def with_log_warnings(top, conf):
    """`conf` (`settings`' answer) with `log_warnings` added to its warnings."""
    conf["warnings"] = list(conf["warnings"]) + log_warnings(top, conf)
    return conf


def log_warnings(top, conf):
    """`settings`' warnings about the log (L-0653): unreported entries while
    not asleep, or a log that cannot be read. Never raises."""
    try:
        text, why = _read_log(top)
        if text is None:
            return [f"sleep log could not be read ({why}); {log_path(top)} is not read as empty"]
        count = len(crew_sleep.unreported(text))
        if count and conf["sleep"]["state"] != crew_sleep.ASLEEP:
            return [f"{count} sleep decisions are unreported - run crew_autopilot.py sleep-summary"]
    except Exception as exc:  # noqa: BLE001  # pylint: disable=broad-except
        return [f"sleep log could not be read ({ap._failure(exc)})"]
    return []


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
            summary = sleep_summary(args.root)[1] if code == 0 else NOTHING
            text += "" if summary == NOTHING else "\n" + summary
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
